import os
from dataclasses import dataclass, field


def _split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


@dataclass(frozen=True)
class Config:
    jetstream_urls: list[str] = field(default_factory=list)
    wanted_collections: str = "app.bsky.feed.post"
    lang_filter: list[str] = field(default_factory=list)
    kafka_bootstrap_servers: str = "kafka:9092"
    kafka_topic: str = "bluesky-posts"
    reconnect_backoff_seconds: float = 2.0
    max_reconnect_backoff_seconds: float = 30.0
    cursor_rewind_us: int = 5_000_000
    cursor_file: str = "/data/cursor.txt"
    log_level: str = "INFO"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            jetstream_urls=_split_csv(os.environ.get(
                "JETSTREAM_URLS",
                "wss://jetstream2.us-east.bsky.network/subscribe,"
                "wss://jetstream1.us-east.bsky.network/subscribe,"
                "wss://jetstream2.us-west.bsky.network/subscribe",
            )),
            wanted_collections=os.environ.get("WANTED_COLLECTIONS", "app.bsky.feed.post"),
            lang_filter=_split_csv(os.environ.get("LANG_FILTER", "en")),
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            kafka_topic=os.environ.get("KAFKA_TOPIC", "bluesky-posts"),
            reconnect_backoff_seconds=float(os.environ.get("RECONNECT_BACKOFF_SECONDS", "2")),
            max_reconnect_backoff_seconds=float(os.environ.get("MAX_RECONNECT_BACKOFF_SECONDS", "30")),
            cursor_rewind_us=int(os.environ.get("CURSOR_REWIND_US", "5000000")),
            cursor_file=os.environ.get("CURSOR_FILE", "/data/cursor.txt"),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
