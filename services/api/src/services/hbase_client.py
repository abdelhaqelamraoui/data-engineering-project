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
            json={"startRow": _b64(start_row), "endRow": _b64(end_row), "batch": limit},
            headers={"Content-Type": "application/json"},
        )
        if create_resp.status_code == 404:
            return []
        create_resp.raise_for_status()
        scanner_url = create_resp.headers["Location"]

        results: list[tuple[str, dict[str, str]]] = []
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
                    results.append((key, cells))
                if len(results) >= limit:
                    break
        finally:
            await self._client.delete(scanner_url)
        return results

    async def scan_bucket_prefix(self, table: str, bucket: str, limit: int = 1000) -> list[tuple[str, dict[str, str]]]:
        return await self.scan_range(table, bucket, increment_numeric_string(bucket), limit=limit)

    async def scan_term_prefix(self, table: str, term: str, limit: int = 1000) -> list[tuple[str, dict[str, str]]]:
        # Bracket on the "term#" delimiter, not just the term, so a term like
        # "data" doesn't also match "database#<bucket>" rows.
        return await self.scan_range(table, f"{term}#", f"{term}$", limit=limit)
