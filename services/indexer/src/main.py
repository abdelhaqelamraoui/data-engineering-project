import json
import logging
import signal
import threading
import time
from datetime import datetime, timezone

from confluent_kafka import Consumer

from config import Config
from es_client import ElasticsearchIndexer
from kibana_client import ensure_data_view
from preprocessing import preprocess

logger = logging.getLogger("indexer.main")

DATA_VIEW_RETRY_ATTEMPTS = 6
DATA_VIEW_RETRY_DELAY_SECONDS = 10


def build_document(raw: dict, config: Config) -> dict:
    result = preprocess(raw.get("text") or "", config.min_term_length)
    return {
        "id": raw.get("id"),
        "did": raw.get("did"),
        "text": raw.get("text"),
        "lang": raw.get("lang"),
        "timestamp": raw.get("timestamp"),
        "indexed_at": datetime.now(timezone.utc).isoformat(),
        "cleaned_text": result.cleaned_text,
        "hashtags": result.hashtags,
        "words": result.words,
    }


def _bootstrap_kibana_data_view(config: Config) -> None:
    """Runs in a background thread so a slow-starting Kibana never delays
    the consume loop below from starting promptly.
    """
    for attempt in range(1, DATA_VIEW_RETRY_ATTEMPTS + 1):
        if ensure_data_view(config.kibana_url, config.es_index, "Bluesky Posts", time_field="timestamp"):
            return
        time.sleep(DATA_VIEW_RETRY_DELAY_SECONDS)
    logger.warning(
        "Giving up creating the Kibana data view after %d attempts - "
        "create it manually in Kibana (Index pattern: %s)",
        DATA_VIEW_RETRY_ATTEMPTS,
        config.es_index,
    )


def run(config: Config) -> None:
    es = ElasticsearchIndexer(config.elasticsearch_url, config.es_index)
    es.ensure_index()
    threading.Thread(target=_bootstrap_kibana_data_view, args=(config,), daemon=True).start()

    consumer = Consumer({
        "bootstrap.servers": config.kafka_bootstrap_servers,
        "group.id": config.consumer_group_id,
        "auto.offset.reset": "latest",
        "enable.auto.commit": False,
    })
    consumer.subscribe([config.kafka_topic])

    buffer: list[dict] = []
    last_flush = time.monotonic()
    stopped = False

    def handle_signal(_signum, _frame) -> None:
        nonlocal stopped
        stopped = True

    signal.signal(signal.SIGTERM, handle_signal)
    signal.signal(signal.SIGINT, handle_signal)

    logger.info("Consuming %s -> indexing into %s", config.kafka_topic, config.es_index)

    while not stopped:
        msg = consumer.poll(timeout=1.0)
        if msg is not None and msg.error() is None:
            try:
                raw = json.loads(msg.value().decode("utf-8"))
                buffer.append(build_document(raw, config))
            except (json.JSONDecodeError, UnicodeDecodeError):
                pass

        due_by_size = len(buffer) >= config.bulk_flush_size
        due_by_time = bool(buffer) and time.monotonic() - last_flush >= config.bulk_flush_interval_seconds
        if due_by_size or due_by_time:
            try:
                es.bulk_index(buffer)
                consumer.commit(asynchronous=False)
                buffer = []
            except Exception as exc:
                # Leave the buffer and the Kafka position alone and retry
                # next loop - a transient ES outage shouldn't drop posts,
                # and re-indexing the same buffer later is a harmless upsert.
                logger.warning("flush failed, will retry: %s", exc)
            last_flush = time.monotonic()

    if buffer:
        es.bulk_index(buffer)
        consumer.commit(asynchronous=False)
    consumer.close()


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(level=config.log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    run(config)


if __name__ == "__main__":
    main()
