from pyspark.sql import DataFrame, functions as F

from config import Config
from stopwords import ENGLISH_STOPWORDS

URL_PATTERN = r"https?://\S+"
# bare domains without a scheme (e.g. "bsky.app/profile/x", "example.com")
BARE_DOMAIN_PATTERN = r"\b(?:www\.)?[\w-]+\.(?:com|net|org|io|co|app|gov|edu|info|ly|me|tv|xyz|social)(?:/\S*)?\b"
MENTION_PATTERN = r"@\S+"
APOSTROPHE_PATTERN = r"['’]"
HASHTAG_TOKEN_PATTERN = r"#\w+"
HASHTAG_VALID_PATTERN = r"^#[A-Za-z0-9_]{2,}$"


def extract_terms(posts: DataFrame, config: Config) -> DataFrame:
    """Explode each post into one row per (term, timestamp, author) it contains.

    `term` is either a hashtag (kept with its leading '#') or a stopword-
    filtered alphabetic word - both signal "topics" per the project brief.
    """
    hashtags = (
        posts.select("timestamp", "did", F.explode(F.split(F.col("text"), r"\s+")).alias("raw_token"))
        .where(F.col("raw_token").rlike(HASHTAG_VALID_PATTERN))
        .select("timestamp", "did", F.lower(F.col("raw_token")).alias("term"))
    )

    lowered = F.lower(F.col("text"))
    text_without_hashtags = F.regexp_replace(lowered, HASHTAG_TOKEN_PATTERN, " ")
    text_without_urls = F.regexp_replace(text_without_hashtags, URL_PATTERN, " ")
    text_without_domains = F.regexp_replace(text_without_urls, BARE_DOMAIN_PATTERN, " ")
    text_without_mentions = F.regexp_replace(text_without_domains, MENTION_PATTERN, " ")
    # drop apostrophes rather than turning them into spaces, so "don't" stays
    # one token ("dont") instead of splitting into "don" + "t"
    text_without_apostrophes = F.regexp_replace(text_without_mentions, APOSTROPHE_PATTERN, "")
    cleaned = F.regexp_replace(text_without_apostrophes, r"[^a-z0-9\s]", " ")

    words = (
        posts.select("timestamp", "did", F.explode(F.split(cleaned, r"\s+")).alias("term"))
        .where(F.col("term").rlike(rf"^[a-z]{{{config.min_term_length},}}$"))
        .where(~F.col("term").isin(ENGLISH_STOPWORDS))
    )

    return hashtags.unionByName(words)
