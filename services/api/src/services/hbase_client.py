import base64
import logging
from urllib.parse import quote

import httpx

logger = logging.getLogger("api.hbase")


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _unb64(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def increment_numeric_string(value: str) -> str:
    return str(int(value) + 1).zfill(len(value))


# HBase's REST "batch" scanner parameter caps *cells* per page, not rows -
# a row with N columns can have its cells split across page boundaries.
# This is deliberately independent of the caller's row `limit`, and large
# enough that the bounded ranges this client ever scans (one bucket's
# top-N rows, or one term's retention-window history) fit in very few
# pages regardless of how many rows the caller actually wants back.
_SCANNER_CELL_BATCH = 2000


class HBaseRestClient:
    """Read-only HBase REST (Stargate) client used by the API layer.

    Returns empty results instead of raising when a table doesn't exist yet -
    the Spark processor creates tables lazily, so the API may start before
    any data (or even the schema) exists.
    """

    def __init__(self, base_url: str, timeout: float = 10.0):
        self._base_url = base_url.rstrip("/")
        self._client = httpx.AsyncClient(timeout=timeout)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def get_row(self, table: str, row_key: str) -> dict[str, str] | None:
        url = f"{self._base_url}/{table}/{quote(row_key, safe='')}"
        resp = await self._client.get(url, headers={"Accept": "application/json"})
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if "Row" not in data:
            # A row key that collides with one of the REST gateway's
            # reserved sub-resources (e.g. literally "schema") lands here
            # with a 200 but a totally different payload shape.
            logger.warning("Unexpected response shape for %s (no 'Row' key) - treating as missing", url)
            return None
        row = data["Row"][0]
        return {_unb64(c["column"]): _unb64(c["$"]) for c in row["Cell"]}

    async def scan_range(self, table: str, start_row: str, end_row: str, limit: int = 1000) -> list[tuple[str, dict[str, str]]]:
        create_resp = await self._client.put(
            f"{self._base_url}/{table}/scanner",
            json={"startRow": _b64(start_row), "endRow": _b64(end_row), "batch": _SCANNER_CELL_BATCH},
            headers={"Content-Type": "application/json"},
        )
        if create_resp.status_code == 404:
            return []
        create_resp.raise_for_status()
        scanner_url = create_resp.headers["Location"]

        # Accumulate by row key and merge cells across pages - a row's
        # cells can arrive split across multiple pages (see _SCANNER_CELL_BATCH),
        # so a page's "Row" entry is not necessarily that row's full cell set
        # yet. Rows arrive in key order, so it's safe to scan to completion
        # (the 204) before truncating to `limit`, since these ranges are
        # always small (one bucket's top-N, or one term's retention window).
        rows: dict[str, dict[str, str]] = {}
        order: list[str] = []
        try:
            while True:
                resp = await self._client.get(scanner_url, headers={"Accept": "application/json"})
                if resp.status_code == 204:
                    break
                resp.raise_for_status()
                data = resp.json()
                for row in data.get("Row", []):
                    key = _unb64(row["key"])
                    cells = {_unb64(c["column"]): _unb64(c["$"]) for c in row["Cell"]}
                    if key not in rows:
                        order.append(key)
                    rows.setdefault(key, {}).update(cells)
        finally:
            await self._client.delete(scanner_url)
        return [(key, rows[key]) for key in order[:limit]]

    async def scan_bucket_prefix(self, table: str, bucket: str, limit: int = 1000) -> list[tuple[str, dict[str, str]]]:
        return await self.scan_range(table, bucket, increment_numeric_string(bucket), limit=limit)

    async def scan_term_prefix(self, table: str, term: str, limit: int = 1000) -> list[tuple[str, dict[str, str]]]:
        # Bracket on the "term#" delimiter, not just the term, so a term like
        # "data" doesn't also match "database#<bucket>" rows.
        return await self.scan_range(table, f"{term}#", f"{term}$", limit=limit)
