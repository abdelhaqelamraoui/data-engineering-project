# Preprocessing module

`shared/preprocessing/` is the single place that decides what counts as a
"term": hashtag rules, stopwords, URL/mention/punctuation stripping, the
minimum word length. Both `spark-processor` (the real scoring pipeline) and
`api` (the dashboard's before/after preview) run the exact same code from
this module - edit it once, both consumers pick up the change on their next
rebuild. Nothing else in either service needs to change.

See [`components.md`](components.md) for how this fits into the rest of
the system end to end.

```
shared/preprocessing/
  __init__.py          # public API: preprocess(), PreprocessResult, ENGLISH_STOPWORDS
  cleaning.py           # the actual regex rules
  stopwords.py          # the stopword list
  test_cleaning.py      # unit tests - no Spark, no FastAPI, no Docker needed
```

It's plain stdlib Python (`re` + `dataclasses`, nothing else) on purpose:
no Spark or web framework dependency, so it runs and tests the same way
everywhere it's used.

## The API

```python
from preprocessing import preprocess

result = preprocess("Loving the new #Spark release! https://example.com", min_term_length=3)
result.cleaned_text   # "loving the new release"
result.hashtags       # ["#spark"]
result.words          # ["loving", "release"]
result.terms          # ["#spark", "loving", "release"]  (hashtags + words)
```

`preprocess()` runs two independent extractions over the raw text and
returns both:

- **Hashtags** - any whitespace-delimited token matching `#[A-Za-z0-9_]{2,}`,
  lowercased, kept with its `#`.
- **Words** - the text lowercased, then hashtags/URLs/bare domains/mentions/
  apostrophes/punctuation stripped, then split on whitespace and filtered to
  alphabetic tokens of at least `min_term_length` characters that aren't in
  `ENGLISH_STOPWORDS`.

## Who consumes it, and how

- **`spark-processor`** (`services/spark-processor/src/cleaning.py`) wraps
  `preprocess()` in a Spark UDF and explodes the resulting `terms` list into
  one DataFrame row per term. This is the only place Spark-specific code
  touches preprocessing - the rules themselves never import `pyspark`.
- **`api`** (`services/api/src/services/live_posts.py`) calls `preprocess()`
  directly (no Spark needed) on every post as it's read off Kafka for the
  live feed, and stores the result (`cleaned_text`, `hashtags`, `words`)
  alongside the raw post in its in-memory buffer. `GET /posts/recent` serves
  both the "before" (raw `text`) and "after" (`cleaned_text`/`hashtags`/
  `words`) for the same post.
- **dashboard** renders that before/after side by side on the
  **Preprocessing** page (`/preprocessing`), via `BeforeAfterCard.tsx`.

See [`architecture.md`](architecture.md) for where this sits relative to
the rest of the system.

## How the module reaches each service's image

`shared/preprocessing/` lives at the repo root, outside any one service's
directory, because it's vendored into *two* otherwise-independent Docker
images at build time:

```dockerfile
# services/api/Dockerfile and services/spark-processor/Dockerfile
COPY shared/preprocessing/ ./src/preprocessing/   # (path differs slightly per image)
```

For the `COPY` to reach a path outside `services/api/` or
`services/spark-processor/`, those two services build with the **repo root**
as their Docker build context (see `docker-compose.yml` - `context: .`,
`dockerfile: services/api/Dockerfile`), instead of the per-service context
the other services use. This keeps the source of truth as one file without
making the services share a runtime process, a network call, or a Python
package dependency - each container still only has its own code on disk
once built, just copied from a common origin.

## Making a change

1. Edit `shared/preprocessing/cleaning.py` or `stopwords.py`.
2. Sanity-check it in isolation, no Docker needed:
   ```bash
   python -m unittest shared.preprocessing.test_cleaning -v
   ```
3. Rebuild and restart the two consumers:
   ```bash
   docker compose build api spark-processor
   docker compose up -d api spark-processor
   ```
4. Watch it live on the **Preprocessing** page (`/preprocessing`) - it polls
   every 2s, so a real post will show the new behavior almost immediately.

Nothing under `services/spark-processor/src/` besides `cleaning.py`'s one
import, and nothing under `services/api/src/` besides
`services/live_posts.py`'s one import, needs to know this module changed.

## Known limitation (a real example, not hypothetical)

The bare-domain stripper only recognizes a fixed TLD list (`com`, `net`,
`org`, `io`, `co`, `app`, `gov`, `edu`, `info`, `ly`, `me`, `tv`, `xyz`,
`social`). A URL like `share.google/...` isn't in that list, so `google`
leaks through as an extracted word - visible directly on the Preprocessing
page. Extending `BARE_DOMAIN_PATTERN` in `cleaning.py` is the fix; this is
exactly the kind of thing the before/after page exists to surface.
