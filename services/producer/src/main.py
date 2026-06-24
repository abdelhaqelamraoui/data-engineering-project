import asyncio
import logging
import os
import signal

from config import Config
from filters import extract_post
from jetstream_client import stream_posts
from kafka_producer import PostPublisher

logger = logging.getLogger("producer.main")

CURSOR_PERSIST_EVERY = 200


def load_cursor(path: str) -> int | None:
    try:
        with open(path) as f:
            return int(f.read().strip())
    except (FileNotFoundError, ValueError):
        return None


def save_cursor(path: str, cursor: int) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(str(cursor))


async def run(config: Config, publisher: PostPublisher) -> None:
    cursor = load_cursor(config.cursor_file)
    seen = 0
    published = 0

    async for message in stream_posts(config, cursor):
        seen += 1
        post = extract_post(message, config)
        if post is not None:
            publisher.publish(post)
            published += 1

        if seen % CURSOR_PERSIST_EVERY == 0:
            time_us = message.get("time_us")
            if time_us is not None:
                save_cursor(config.cursor_file, time_us)
            logger.info("seen=%d published=%d", seen, published)


def main() -> None:
    config = Config.from_env()
    logging.basicConfig(
        level=config.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    logger.info("Starting Bluesky Jetstream producer -> kafka topic %s", config.kafka_topic)

    publisher = PostPublisher(config.kafka_bootstrap_servers, config.kafka_topic)
    loop = asyncio.new_event_loop()
    main_task = loop.create_task(run(config, publisher))
    for sig in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(sig, main_task.cancel)

    try:
        loop.run_until_complete(main_task)
    except asyncio.CancelledError:
        logger.info("Shutdown requested, flushing producer")
    finally:
        publisher.flush()
        loop.close()


if __name__ == "__main__":
    main()
