import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kafka_bootstrap_servers: str
    kafka_topic: str
    hbase_rest_url: str

    window_duration: str
    slide_duration: str
    watermark_delay: str

    min_count_threshold: int
    min_distinct_authors: int
    trend_smoothing: float
    baseline_ema_alpha: float
    top_n: int
    min_term_length: int

    retention_hours: int
    checkpoint_dir: str

    table_trends: str
    table_term_history: str
    table_baseline: str
    table_meta: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            kafka_topic=os.environ.get("KAFKA_TOPIC", "bluesky-posts"),
            hbase_rest_url=os.environ.get("HBASE_REST_URL", "http://hbase:8080"),
            window_duration=os.environ.get("WINDOW_DURATION", "5 minutes"),
            slide_duration=os.environ.get("SLIDE_DURATION", "1 minute"),
            watermark_delay=os.environ.get("WATERMARK_DELAY", "2 minutes"),
            min_count_threshold=int(os.environ.get("MIN_COUNT_THRESHOLD", "3")),
            min_distinct_authors=int(os.environ.get("MIN_DISTINCT_AUTHORS", "2")),
            trend_smoothing=float(os.environ.get("TREND_SMOOTHING", "1.0")),
            baseline_ema_alpha=float(os.environ.get("BASELINE_EMA_ALPHA", "0.3")),
            top_n=int(os.environ.get("TOP_N", "20")),
            min_term_length=int(os.environ.get("MIN_TERM_LENGTH", "3")),
            retention_hours=int(os.environ.get("RETENTION_HOURS", "24")),
            checkpoint_dir=os.environ.get("CHECKPOINT_DIR", "/checkpoints/trending"),
            table_trends=os.environ.get("TABLE_TRENDS", "trends"),
            table_term_history=os.environ.get("TABLE_TERM_HISTORY", "term_history"),
            table_baseline=os.environ.get("TABLE_BASELINE", "term_baseline"),
            table_meta=os.environ.get("TABLE_META", "pipeline_meta"),
        )
