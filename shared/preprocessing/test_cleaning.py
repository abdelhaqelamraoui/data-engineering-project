"""Run with: python -m unittest shared.preprocessing.test_cleaning -v
No Spark, no FastAPI, no network - just the rules in cleaning.py.
"""

import unittest

from .cleaning import preprocess


class PreprocessTests(unittest.TestCase):
    def test_hashtags_are_lowercased_and_kept_with_prefix(self):
        result = preprocess("Loving the new #Spark release today")
        self.assertIn("#spark", result.hashtags)

    def test_contractions_collapse_instead_of_splitting(self):
        result = preprocess("don't can't won't all collapse")
        self.assertNotIn("don", result.words)
        self.assertNotIn("can", result.words)
        self.assertNotIn("t", result.words)

    def test_urls_and_bare_domains_are_stripped(self):
        result = preprocess("check out https://example.com/x and www.example.com now")
        self.assertNotIn("example", result.words)
        self.assertNotIn("com", result.words)
        self.assertNotIn("www", result.words)

    def test_mentions_are_stripped(self):
        result = preprocess("hello @someone.bsky.social how are you")
        self.assertNotIn("someone", result.words)

    def test_short_and_stopword_tokens_are_dropped(self):
        result = preprocess("a to of it is the and but")
        self.assertEqual(result.words, [])

    def test_terms_combines_hashtags_and_words(self):
        result = preprocess("#Trending happens because people notice patterns")
        self.assertEqual(result.terms, result.hashtags + result.words)

    def test_min_term_length_is_configurable(self):
        result = preprocess("big small huge", min_term_length=4)
        self.assertNotIn("big", result.words)
        self.assertIn("small", result.words)


if __name__ == "__main__":
    unittest.main()
