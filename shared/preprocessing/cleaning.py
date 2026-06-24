"""Text-cleaning and term-extraction rules for one post's text.

This is the single place that decides what counts as a "term" - edit the
patterns/constants here and every consumer (the Spark scoring pipeline and
the API's live before/after preview) picks up the change on its next
rebuild. See docs/preprocessing.md for how to extend this safely.

Pure stdlib only (just `re`) so it has no Spark/FastAPI dependency and can
be unit-tested or run standalone - see test_cleaning.py.
"""

import re
from dataclasses import dataclass, field

from .stopwords import ENGLISH_STOPWORDS

URL_PATTERN = re.compile(r"https?://\S+")
# bare domains without a scheme (e.g. "bsky.app/profile/x", "example.com")
BARE_DOMAIN_PATTERN = re.compile(
    r"\b(?:www\.)?[\w-]+\.(?:com|net|org|io|co|app|gov|edu|info|ly|me|tv|xyz|social)(?:/\S*)?\b"
)
MENTION_PATTERN = re.compile(r"@\S+")
APOSTROPHE_PATTERN = re.compile(r"['’]")
HASHTAG_TOKEN_PATTERN = re.compile(r"#\w+")
HASHTAG_VALID_PATTERN = re.compile(r"^#[A-Za-z0-9_]{2,}$")
NON_ALNUM_PATTERN = re.compile(r"[^a-z0-9\s]")
WHITESPACE_PATTERN = re.compile(r"\s+")
WORD_PATTERN_TEMPLATE = r"^[a-z]{{{min_length},}}$"


@dataclass(frozen=True)
class PreprocessResult:
    cleaned_text: str
    hashtags: list[str] = field(default_factory=list)
    words: list[str] = field(default_factory=list)

    @property
    def terms(self) -> list[str]:
        """Hashtags and words combined - exactly what feeds the trend scorer."""
        return [*self.hashtags, *self.words]


def extract_hashtags(raw_text: str) -> list[str]:
    return [
        token.lower()
        for token in raw_text.split()
        if HASHTAG_VALID_PATTERN.match(token)
    ]


def clean_for_words(raw_text: str) -> str:
    """Lowercase and strip everything that isn't a candidate word token."""
    lowered = raw_text.lower()
    no_hashtags = HASHTAG_TOKEN_PATTERN.sub(" ", lowered)
    no_urls = URL_PATTERN.sub(" ", no_hashtags)
    no_domains = BARE_DOMAIN_PATTERN.sub(" ", no_urls)
    no_mentions = MENTION_PATTERN.sub(" ", no_domains)
    # drop apostrophes rather than turning them into spaces, so "don't"
    # stays one token ("dont") instead of splitting into "don" + "t"
    no_apostrophes = APOSTROPHE_PATTERN.sub("", no_mentions)
    no_punctuation = NON_ALNUM_PATTERN.sub(" ", no_apostrophes)
    return WHITESPACE_PATTERN.sub(" ", no_punctuation).strip()


def extract_words(cleaned_text: str, min_term_length: int) -> list[str]:
    word_pattern = re.compile(WORD_PATTERN_TEMPLATE.format(min_length=min_term_length))
    return [
        token
        for token in cleaned_text.split()
        if word_pattern.match(token) and token not in ENGLISH_STOPWORDS
    ]


def preprocess(raw_text: str, min_term_length: int = 3) -> PreprocessResult:
    """Run the full pipeline for one post: hashtags + cleaned words."""
    hashtags = extract_hashtags(raw_text)
    cleaned_text = clean_for_words(raw_text)
    words = extract_words(cleaned_text, min_term_length)
    return PreprocessResult(cleaned_text=cleaned_text, hashtags=hashtags, words=words)
