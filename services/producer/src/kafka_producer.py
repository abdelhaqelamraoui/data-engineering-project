import json
import logging

from confluent_kafka import Producer

logger = logging.getLogger("producer.kafka")


class PostPublisher:
    def __init__(self, bootstrap_servers: str, topic: str):
        self._topic = topic
        self._producer = Producer({
            "bootstrap.servers": bootstrap_servers,
            "client.id": "bluesky-jetstream-producer",
            "linger.ms": 200,
            "compression.type": "lz4",
        })

    def publish(self, record: dict) -> None:
        self._producer.produce(
            self._topic,
            key=record["id"].encode("utf-8"),
            value=json.dumps(record).encode("utf-8"),
            callback=self._delivery_callback,
        )
        self._producer.poll(0)

    def _delivery_callback(self, err, msg) -> None:
        if err is not None:
            logger.warning("Delivery failed for record %s: %s", msg.key(), err)

    def flush(self, timeout: float = 10.0) -> None:
        self._producer.flush(timeout)
