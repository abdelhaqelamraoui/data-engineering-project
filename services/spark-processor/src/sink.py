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


def _baseline_row_key(term: str) -> str:
    # HBase's REST gateway treats a handful of literal row segments as
    # reserved sub-resources ("schema", "regions", "scanner", "multiget").
    # A bare term as the row key collides with those whenever a real word
    # matches one (e.g. someone posts about a database "schema") and 404s
    # or - worse - 200s with the wrong payload. Prefixing sidesteps it.
    return f"t#{term}"


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
    # One multiget for every candidate's baseline instead of one GET per
    # candidate - see HBaseRestClient.get_rows for why this matters once a
    # window has more than a couple hundred candidates.
    baseline_keys = {row.term: _baseline_row_key(row.term) for row in rows}
    baselines = hbase.get_rows(config.table_baseline, list(baseline_keys.values()))

    candidates = []
    for row in rows:
        baseline_row = baselines.get(baseline_keys[row.term])
        baseline_avg = float(baseline_row["baseline:avg"]) if baseline_row else None
        score = compute_score(row.cnt, baseline_avg or 0.0, config.trend_smoothing)
        candidates.append((row.term, row.cnt, row.distinct_authors, score, baseline_avg))

    candidates.sort(key=lambda c: c[3], reverse=True)
    top = candidates[: config.top_n]

    trend_writes = []
    history_writes = []
    for rank, (term, cnt, distinct_authors, score, baseline_avg) in enumerate(top, start=1):
        trend_writes.append((
            f"{bucket}#{rank:03d}",
            "trends",
            {"rank": rank, "term": term, "count": cnt, "score": round(score, 4), "distinct_authors": distinct_authors},
        ))
        history_writes.append((f"{term}#{bucket}", "history", {"count": cnt, "score": round(score, 4)}))
    hbase.put_rows(config.table_trends, trend_writes)
    hbase.put_rows(config.table_term_history, history_writes)

    # Baseline is updated from every qualifying candidate (not just the top
    # N) so a term's trailing average keeps tracking it even while it isn't
    # ranked highly enough to be displayed.
    baseline_writes = [
        (_baseline_row_key(term), "baseline", {"avg": round(update_baseline(baseline_avg, cnt, config.baseline_ema_alpha), 4)})
        for term, cnt, _distinct_authors, _score, baseline_avg in candidates
    ]
    hbase.put_rows(config.table_baseline, baseline_writes)

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
