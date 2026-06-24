import asyncio
import json
import logging
from collections.abc import AsyncIterator

import websockets

from config import Config

logger = logging.getLogger("producer.jetstream")


def _build_url(base_url: str, config: Config, cursor: int | None) -> str:
    url = f"{base_url}?wantedCollections={config.wanted_collections}"
    if cursor is not None:
        # Rewind a few seconds so we don't lose events that arrived during the
        # reconnect gap (Jetstream cursor is the time_us of the last event seen).
        rewound = max(cursor - config.cursor_rewind_us, 0)
        url += f"&cursor={rewound}"
    return url


async def stream_posts(config: Config, cursor: int | None) -> AsyncIterator[dict]:
    """Connect to Jetstream with failover across mirrors and automatic reconnect.

    Yields raw decoded JSON messages indefinitely. Never raises on connection
    errors - it retries with backoff instead, rotating through the configured
    Jetstream hosts.
    """
    backoff = config.reconnect_backoff_seconds
    host_index = 0

    while True:
        base_url = config.jetstream_urls[host_index % len(config.jetstream_urls)]
        url = _build_url(base_url, config, cursor)
        try:
            logger.info("Connecting to %s", url)
            async with websockets.connect(url, ping_interval=20, ping_timeout=20) as ws:
                backoff = config.reconnect_backoff_seconds
                async for raw in ws:
                    message = json.loads(raw)
                    cursor = message.get("time_us", cursor)
                    yield message
        except (websockets.exceptions.WebSocketException, OSError) as exc:
            logger.warning("Jetstream connection lost (%s), retrying in %.1fs", exc, backoff)
            host_index += 1
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, config.max_reconnect_backoff_seconds)
