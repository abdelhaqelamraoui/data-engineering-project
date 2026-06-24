import logging

from elasticsearch import Elasticsearch
from elasticsearch.helpers import bulk

logger = logging.getLogger("indexer.es")

INDEX_MAPPING = {
    "mappings": {
        "properties": {
            "id": {"type": "keyword"},
            "did": {"type": "keyword"},
            "text": {"type": "text"},
            "lang": {"type": "keyword"},
            "timestamp": {"type": "date"},
            "indexed_at": {"type": "date"},
            # "after" preprocessing - same shared rules spark-processor scores
            # with, so Kibana can facet on the exact terms that feed trending
            "cleaned_text": {"type": "text"},
            "hashtags": {"type": "keyword"},
            "words": {"type": "keyword"},
        }
    }
}


class ElasticsearchIndexer:
    def __init__(self, url: str, index: str):
        self._client = Elasticsearch(url)
        self._index = index

    def ensure_index(self) -> None:
        if self._client.indices.exists(index=self._index):
            return
        self._client.indices.create(index=self._index, body=INDEX_MAPPING)
        logger.info("Created Elasticsearch index '%s'", self._index)

    def bulk_index(self, documents: list[dict]) -> None:
        """Upsert by post id (not auto-generated _id) so an at-least-once
        redelivery after a restart overwrites instead of duplicating.
        """
        if not documents:
            return
        actions = [{"_index": self._index, "_id": doc["id"], "_source": doc} for doc in documents]
        success, errors = bulk(self._client, actions, raise_on_error=False, stats_only=False)
        if errors:
            logger.warning("bulk index: %d ok, %d errors (showing up to 3): %s", success, len(errors), errors[:3])
