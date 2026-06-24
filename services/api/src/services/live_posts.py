import asyncio
import json
import logging
import uuid
from collections import deque
from datetime import datetime, timezone

from aiokafka import AIOKafkaConsumer

from preprocessing import preprocess

logger = logging.getLogger("api.live_posts")


class LivePostsFeed:
    """Keeps an in-memory, most-recent-first buffer of raw posts from Kafka.

    This reads the same `bluesky-posts` topic the Spark job consumes, but as
    an independent consumer group starting from "latest" - it never commits
    offsets and is free to fall behind or restart without affecting (or
    being affected by) the trend-scoring pipeline.

    Each buffered post is run through the same shared `preprocessing` module
    spark-processor uses, so the buffer holds both the raw post (the "before")
    and its cleaned text + extracted terms (the "after") for the dashboard's
    before/after preview - computed once here rather than on every poll.
    """

    def __init__(self, bootstrap_servers: str, topic: str, buffer_size: int, min_term_length: int):
        self._bootstrap_servers = bootstrap_servers
        self._topic = topic
        self._min_term_length = min_term_length
        self._buffer: deque[dict] = deque(maxlen=buffer_size)
        self._task: asyncio.Task | None = None
        self._stopped = False

    def recent(self, limit: int) -> list[dict]:
        return list(self._buffer)[-limit:][::-1]

    def start(self) -> None:
        self._task = asyncio.create_task(self._run_forever())

    async def stop(self) -> None:
        self._stopped = True
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass

    async def _run_forever(self) -> None:
        while not self._stopped:
            try:
                await self._consume()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                logger.warning("live posts consumer error, retrying in 5s: %s", exc)
                await asyncio.sleep(5)

    async def _consume(self) -> None:
        consumer = AIOKafkaConsumer(
            self._topic,
            bootstrap_servers=self._bootstrap_servers,
            group_id=f"api-live-feed-{uuid.uuid4().hex}",
            auto_offset_reset="latest",
            enable_auto_commit=False,
        )
        await consumer.start()
        logger.info("live posts consumer connected (topic=%s)", self._topic)
        try:
            async for message in consumer:
                try:
                    post = json.loads(message.value.decode("utf-8"))
                except (json.JSONDecodeError, UnicodeDecodeError):
                    continue
                post["received_at"] = datetime.now(timezone.utc).isoformat()
                result = preprocess(post.get("text", ""), self._min_term_length)
                post["cleaned_text"] = result.cleaned_text
                post["hashtags"] = result.hashtags
                post["words"] = result.words
                self._buffer.append(post)
        finally:
            await consumer.stop()
