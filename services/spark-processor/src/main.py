import logging
import time

from pyspark.sql import SparkSession, functions as F
from pyspark.sql.types import StringType, StructField, StructType

from cleaning import extract_terms
from config import Config
from hbase_client import HBaseRestClient
from sink import ensure_tables, make_batch_writer

logger = logging.getLogger("spark_processor.main")

POST_SCHEMA = StructType([
    StructField("id", StringType()),
    StructField("did", StringType()),
    StructField("text", StringType()),
    StructField("timestamp", StringType()),
    StructField("lang", StringType()),
])


def wait_for_hbase(config: Config, attempts: int = 10, delay_seconds: float = 5.0) -> None:
    hbase = HBaseRestClient(config.hbase_rest_url)
    for attempt in range(1, attempts + 1):
        try:
            ensure_tables(hbase, config)
            return
        except Exception as exc:
            logger.warning("HBase not ready yet (attempt %d/%d): %s", attempt, attempts, exc)
            time.sleep(delay_seconds)
    raise RuntimeError("HBase REST gateway never became ready")


def build_query(spark: SparkSession, config: Config):
    raw = (
        spark.readStream.format("kafka")
        .option("kafka.bootstrap.servers", config.kafka_bootstrap_servers)
        .option("subscribe", config.kafka_topic)
        .option("startingOffsets", "latest")
        .option("failOnDataLoss", "false")
        .load()
    )

    # `timestamp` is the post's self-reported `createdAt` from Bluesky - a
    # client with a skewed clock (seen in practice, not hypothetical: a real
    # post arrived claiming to be ~6.5 hours in the future) can set this to
    # anything. Structured Streaming's watermark is the max event-time seen
    # so far and never decreases, so a single far-future timestamp would
    # otherwise jump it forward permanently and silently start dropping
    # every normal, correctly-timed event as "too late" from then on.
    future_cutoff = F.current_timestamp() + F.expr(f"INTERVAL {config.max_future_skew_seconds} SECONDS")
    posts = (
        raw.select(F.from_json(F.col("value").cast("string"), POST_SCHEMA).alias("post"))
        .select("post.*")
        .where(F.col("text").isNotNull() & F.col("did").isNotNull())
        .withColumn("timestamp", F.to_timestamp("timestamp"))
        .where(F.col("timestamp").isNotNull())
        .where(F.col("timestamp") <= future_cutoff)
    )

    terms = extract_terms(posts, config)

    aggregated = (
        terms.withWatermark("timestamp", config.watermark_delay)
        .groupBy(
            F.window(F.col("timestamp"), config.window_duration, config.slide_duration).alias("w"),
            F.col("term"),
        )
        .agg(
            F.count(F.lit(1)).alias("cnt"),
            F.approx_count_distinct("did").alias("distinct_authors"),
        )
        .select(
            F.col("w.start").alias("window_start"),
            F.col("w.end").alias("window_end"),
            "term",
            "cnt",
            "distinct_authors",
        )
        .where(F.col("cnt") >= config.min_count_threshold)
        .where(F.col("distinct_authors") >= config.min_distinct_authors)
    )

    return (
        aggregated.writeStream.outputMode("append")
        .foreachBatch(make_batch_writer(config))
        .option("checkpointLocation", config.checkpoint_dir)
        .trigger(processingTime="30 seconds")
        .start()
    )


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(level="INFO", format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    wait_for_hbase(config)

    spark = SparkSession.builder.appName("trending-topics-processor").getOrCreate()
    spark.sparkContext.setLogLevel("WARN")

    logger.info(
        "Starting structured streaming: topic=%s window=%s slide=%s",
        config.kafka_topic,
        config.window_duration,
        config.slide_duration,
    )
    query = build_query(spark, config)
    query.awaitTermination()


if __name__ == "__main__":
    main()
