import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    kafka_bootstrap_servers: str
    kafka_topic: str
    consumer_group_id: str

    elasticsearch_url: str
    es_index: str
    kibana_url: str

    min_term_length: int
    bulk_flush_size: int
    bulk_flush_interval_seconds: float

    log_level: str

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            kafka_bootstrap_servers=os.environ.get("KAFKA_BOOTSTRAP_SERVERS", "kafka:9092"),
            kafka_topic=os.environ.get("KAFKA_TOPIC", "bluesky-posts"),
            consumer_group_id=os.environ.get("CONSUMER_GROUP_ID", "indexer"),
            elasticsearch_url=os.environ.get("ELASTICSEARCH_URL", "http://elasticsearch:9200"),
            es_index=os.environ.get("ES_INDEX", "bluesky-posts"),
            kibana_url=os.environ.get("KIBANA_URL", "http://kibana:5601"),
            min_term_length=int(os.environ.get("MIN_TERM_LENGTH", "3")),
            bulk_flush_size=int(os.environ.get("BULK_FLUSH_SIZE", "200")),
            bulk_flush_interval_seconds=float(os.environ.get("BULK_FLUSH_INTERVAL_SECONDS", "5")),
            log_level=os.environ.get("LOG_LEVEL", "INFO"),
        )
