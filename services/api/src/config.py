import os
from dataclasses import dataclass


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    hbase_rest_url: str
    table_trends: str
    table_term_history: str
    table_baseline: str
    table_meta: str
    top_n_default: int
    cors_origins: list[str]

    kafka_bootstrap_servers: str
    kafka_topic: str
    live_posts_buffer_size: int

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            hbase_rest_url=os.environ.get("HBASE_REST_URL", "http://hbase:8080"),
            table_trends=os.environ.get("TABLE_TRENDS", "trends"),
            table_term_history=os.environ.get("TABLE_TERM_HISTORY", "term_history"),
            table_baseline=os.environ.get("TABLE_BASELINE", "term_baseline"),
            table_meta=os.environ.get("TABLE_META", "pipeline_meta"),
            top_n_default=int(os.environ.get("TOP_N_DEFAULT", "20")),
            cors_origins=_split_csv(os.environ.get("CORS_ORIGINS", "http://localhost:3000")),
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            kafka_topic=os.environ.get("KAFKA_TOPIC", "bluesky-posts"),
            live_posts_buffer_size=int(os.environ.get("LIVE_POSTS_BUFFER_SIZE", "200")),
        )
