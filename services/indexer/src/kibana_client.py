import logging

import requests

logger = logging.getLogger("indexer.kibana")


def ensure_data_view(kibana_url: str, index_pattern: str, name: str, time_field: str, timeout: float = 5.0) -> bool:
    """Best-effort: pre-create a Kibana data view so the index is immediately
    browsable in Discover, with no manual setup step. Returns whether it's
    confirmed to exist now (true on success or if it already existed).

    Kibana is a separate, slower-starting container and is not on the
    indexer's critical path - indexing into Elasticsearch must keep working
    even if Kibana is temporarily unavailable, so failures here are logged
    and swallowed rather than raised.
    """
    try:
        resp = requests.get(f"{kibana_url}/api/data_views", headers={"kbn-xsrf": "true"}, timeout=timeout)
        resp.raise_for_status()
        existing_titles = {dv["title"] for dv in resp.json().get("data_view", [])}
        if index_pattern in existing_titles:
            return True

        resp = requests.post(
            f"{kibana_url}/api/data_views/data_view",
            headers={"kbn-xsrf": "true", "Content-Type": "application/json"},
            json={"data_view": {"title": index_pattern, "name": name, "timeFieldName": time_field}},
            timeout=timeout,
        )
        resp.raise_for_status()
        logger.info("Created Kibana data view '%s' for index pattern '%s'", name, index_pattern)
        return True
    except Exception as exc:
        logger.warning("Could not create Kibana data view (Kibana may still be starting up): %s", exc)
        return False
