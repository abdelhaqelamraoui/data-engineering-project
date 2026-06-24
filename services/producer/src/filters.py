from config import Config


def extract_post(message: dict, config: Config) -> dict | None:
    """Map a raw Jetstream commit message to a Kafka post record, or None to drop it."""
    if message.get("kind") != "commit":
        return None

    commit = message.get("commit") or {}
    if commit.get("operation") != "create":
        return None
    if commit.get("collection") != "app.bsky.feed.post":
        return None

    record = commit.get("record") or {}
    text = record.get("text", "").strip()
    if not text:
        return None

    langs = record.get("langs") or []
    if config.lang_filter and not any(lang in config.lang_filter for lang in langs):
        return None

    return {
        "id": commit.get("rkey", message.get("did", "")),
        # kept alongside id so the processor can count distinct authors per
        # term, used as a spam/noise guard before something is called "trending"
        "did": message.get("did", ""),
        "text": text,
        "timestamp": record.get("createdAt"),
        "lang": langs[0] if langs else None,
    }
