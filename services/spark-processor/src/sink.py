import logging
from collections import defaultdict
from collections.abc import Callable
from datetime import datetime, timezone

from pyspark.sql import DataFrame

from config import Config
from hbase_client import HBaseRestClient
from trend_scoring import compute_score, update_baseline

logger = logging.getLogger("spark_processor.sink")

BUCKET_FORMAT = "%Y%m%d%H%M"


def ensure_tables(hbase: HBaseRestClient, config: Config) -> None:
    retention_seconds = config.retention_hours * 3600
    hbase.ensure_table(config.table_trends, {"trends": {"TTL": str(retention_seconds)}})
    hbase.ensure_table(config.table_term_history, {"history": {"TTL": str(retention_seconds)}})
    hbase.ensure_table(config.table_baseline, {"baseline": {}})
    hbase.ensure_table(config.table_meta, {"meta": {}})


def _to_bucket(window_start: datetime) -> str:
    return window_start.strftime(BUCKET_FORMAT)


def _update_latest_bucket_pointer(hbase: HBaseRestClient, config: Config, bucket: str) -> None:
    current = hbase.get_row(config.table_meta, "latest_bucket")
    current_value = current.get("meta:value") if current else None
    if current_value is None or bucket > current_value:
        hbase.put_row(
            config.table_meta,
            "latest_bucket",
            "meta",
            {"value": bucket, "updated_at": datetime.now(timezone.utc).isoformat()},
        )


def _process_window(hbase: HBaseRestClient, config: Config, bucket: str, rows: list) -> None:
    candidates = []
    for row in rows:
        baseline_row = hbase.get_row(config.table_baseline, row.term)
        baseline_avg = float(baseline_row["baseline:avg"]) if baseline_row else None
        score = compute_score(row.cnt, baseline_avg or 0.0, config.trend_smoothing)
        candidates.append((row.term, row.cnt, row.distinct_authors, score, baseline_avg))

    candidates.sort(key=lambda c: c[3], reverse=True)
    top = candidates[: config.top_n]

    for rank, (term, cnt, distinct_authors, score, baseline_avg) in enumerate(top, start=1):
        hbase.put_row(
            config.table_trends,
            f"{bucket}#{rank:03d}",
            "trends",
            {"rank": rank, "term": term, "count": cnt, "score": round(score, 4), "distinct_authors": distinct_authors},
        )
        hbase.put_row(
            config.table_term_history,
            f"{term}#{bucket}",
            "history",
            {"count": cnt, "score": round(score, 4)},
        )

    # Baseline is updated from every qualifying candidate (not just the top
    # N) so a term's trailing average keeps tracking it even while it isn't
    # ranked highly enough to be displayed.
    for term, cnt, _distinct_authors, _score, baseline_avg in candidates:
        new_avg = update_baseline(baseline_avg, cnt, config.baseline_ema_alpha)
        hbase.put_row(config.table_baseline, term, "baseline", {"avg": round(new_avg, 4)})

    if top:
        _update_latest_bucket_pointer(hbase, config, bucket)

    logger.info("bucket=%s candidates=%d top=%d", bucket, len(candidates), len(top))


def make_batch_writer(config: Config) -> Callable[[DataFrame, int], None]:
    def write_batch(batch_df: DataFrame, batch_id: int) -> None:
        rows = batch_df.collect()
        if not rows:
            logger.info("batch_id=%d empty", batch_id)
            return

        by_bucket = defaultdict(list)
        for row in rows:
            by_bucket[_to_bucket(row.window_start)].append(row)

        hbase = HBaseRestClient(config.hbase_rest_url)
        for bucket, bucket_rows in sorted(by_bucket.items()):
            _process_window(hbase, config, bucket, bucket_rows)

    return write_batch
