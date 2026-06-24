"""Wires the shared preprocessing rules into Spark.

All the actual cleaning/tokenizing decisions (what counts as a hashtag, a
stopword, a URL, ...) live in `preprocessing` (vendored from shared/, see
docs/preprocessing.md) - this module's only job is to run that pure-Python
logic as a Spark UDF and explode the result into one row per term.
"""

from pyspark.sql import DataFrame, functions as F
from pyspark.sql.types import ArrayType, StringType

from config import Config
from preprocessing import preprocess


def _terms_udf(min_term_length: int):
    def extract(text: str) -> list[str]:
        return preprocess(text, min_term_length).terms

    return F.udf(extract, ArrayType(StringType()))


def extract_terms(posts: DataFrame, config: Config) -> DataFrame:
    """Explode each post into one row per (term, timestamp, author) it contains."""
    return (
        posts.withColumn("term", F.explode(_terms_udf(config.min_term_length)(F.col("text"))))
        .select("timestamp", "did", "term")
    )
