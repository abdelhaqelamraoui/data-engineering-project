import base64
import logging
from collections.abc import Iterator
from typing import TypeVar

import requests

logger = logging.getLogger("spark_processor.hbase")

T = TypeVar("T")

# A row's worth of (row_key, family, values) for a multi-row PUT.
RowWrite = tuple[str, str, dict[str, object]]

# GET row keys ride in the URL's query string (`multiget?row=...&row=...`),
# so this is sized conservatively against typical HTTP server request-line
# limits. PUT rows ride in the request body, which tolerates a much larger
# batch comfortably.
_MULTIGET_CHUNK_SIZE = 200
_MULTIPUT_CHUNK_SIZE = 500


def _b64(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def _unb64(value: str) -> str:
    return base64.b64decode(value).decode("utf-8")


def _chunked(items: list[T], size: int) -> Iterator[list[T]]:
    for start in range(0, len(items), size):
        yield items[start : start + size]


class HBaseRestClient:
    """Thin wrapper around the HBase REST (Stargate) gateway.

    Talking HTTP to the REST gateway avoids pulling the HBase Java client /
    hbase-spark connector (and their strict version pinning) into the Spark
    image - the data volume written per micro-batch is small (ranked terms),
    so plain REST calls are fast enough here.
    """

    def __init__(self, base_url: str, timeout: float = 20.0):
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._session = requests.Session()

    def ensure_table(self, table: str, families: dict[str, dict]) -> None:
        schema_url = f"{self._base_url}/{table}/schema"
        resp = self._session.get(schema_url, headers={"Accept": "application/json"}, timeout=self._timeout)
        if resp.status_code == 200:
            return

        column_schema = [{"name": name, **attrs} for name, attrs in families.items()]
        payload = {"name": table, "ColumnSchema": column_schema}
        resp = self._session.put(
            schema_url,
            json=payload,
            headers={"Content-Type": "application/json"},
            timeout=self._timeout,
        )
        resp.raise_for_status()
        logger.info("Created HBase table '%s' with families %s", table, list(families))

    def put_row(self, table: str, row_key: str, family: str, values: dict[str, str]) -> None:
        cells = [
            {"column": _b64(f"{family}:{col}"), "$": _b64(str(val))}
            for col, val in values.items()
        ]
        payload = {"Row": [{"key": _b64(row_key), "Cell": cells}]}
        url = f"{self._base_url}/{table}/{requests.utils.quote(row_key, safe='')}"
        resp = self._session.put(
            url, json=payload, headers={"Content-Type": "application/json"}, timeout=self._timeout
        )
        resp.raise_for_status()

    def get_row(self, table: str, row_key: str) -> dict[str, str] | None:
        url = f"{self._base_url}/{table}/{requests.utils.quote(row_key, safe='')}"
        resp = self._session.get(url, headers={"Accept": "application/json"}, timeout=self._timeout)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        data = resp.json()
        if "Row" not in data:
            # Row keys that collide with one of the REST gateway's reserved
            # sub-resources (e.g. literally "schema") land here with a 200
            # but a completely different payload shape - treat as not-found
            # rather than crashing the whole streaming query over one term.
            logger.warning("Unexpected response shape for %s (no 'Row' key) - treating as missing", url)
            return None
        row = data["Row"][0]
        return {_unb64(c["column"]): _unb64(c["$"]) for c in row["Cell"]}

    def get_rows(self, table: str, row_keys: list[str]) -> dict[str, dict[str, str]]:
        """Multi-row GET via HBase REST's `multiget` - one HTTP round trip per
        chunk instead of one per row key. Missing keys are simply absent from
        the result (no per-key 404 to handle).

        This is what makes per-candidate baseline lookups in `sink.py`
        affordable - doing one `get_row` per term was the main reason large
        windows fell behind their trigger interval.
        """
        result: dict[str, dict[str, str]] = {}
        for chunk in _chunked(row_keys, _MULTIGET_CHUNK_SIZE):
            query = "&".join(f"row={requests.utils.quote(key, safe='')}" for key in chunk)
            url = f"{self._base_url}/{table}/multiget?{query}"
            resp = self._session.get(url, headers={"Accept": "application/json"}, timeout=self._timeout)
            if resp.status_code == 404:
                continue
            resp.raise_for_status()
            data = resp.json()
            for row in data.get("Row", []):
                key = _unb64(row["key"])
                result[key] = {_unb64(c["column"]): _unb64(c["$"]) for c in row["Cell"]}
        return result

    def put_rows(self, table: str, rows: list[RowWrite]) -> None:
        """Multi-row PUT - one HTTP round trip per chunk instead of one per row.

        HBase REST accepts multiple `Row` entries in a single PUT body; the
        row key in the URL path is only required syntactically and is
        ignored once the body carries its own per-row keys, so any
        placeholder works.
        """
        for chunk in _chunked(rows, _MULTIPUT_CHUNK_SIZE):
            row_payloads = [
                {
                    "key": _b64(row_key),
                    "Cell": [{"column": _b64(f"{family}:{col}"), "$": _b64(str(val))} for col, val in values.items()],
                }
                for row_key, family, values in chunk
            ]
            url = f"{self._base_url}/{table}/_multiput"
            resp = self._session.put(
                url, json={"Row": row_payloads}, headers={"Content-Type": "application/json"}, timeout=self._timeout
            )
            resp.raise_for_status()
