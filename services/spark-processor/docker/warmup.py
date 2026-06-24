# Run once at image build time so `spark-submit --packages` resolves the
# Kafka connector jars into the build container - the Dockerfile then copies
# them onto the classpath so the running container needs no network access.
from pyspark.sql import SparkSession

if __name__ == "__main__":
    spark = SparkSession.builder.master("local[1]").appName("warmup").getOrCreate()
    spark.stop()
