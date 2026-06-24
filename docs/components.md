# Components reference

A prose, component-by-component walkthrough of the whole system: what each
piece is, exactly where its input comes from, exactly where its output
goes, how it's configured, and which files implement it. The goal is that
nothing here is a black box - every arrow in [`architecture.md`](architecture.md)
is explained by a paragraph below.

For the visual versions of the same system, see:
- [`architecture.md`](architecture.md) - static topology diagram
- [`flowchart.md`](flowchart.md) - step-by-step decision logic
- [`sequence-diagram.md`](sequence-diagram.md) - who calls whom, in order
- [`preprocessing.md`](preprocessing.md) - deep dive on the shared cleaning rules

## The journey, in one paragraph

A public Bluesky post is created → **producer** receives it over a
WebSocket, filters it, and republishes it as a small JSON record onto
**Kafka** → **spark-processor** reads Kafka in micro-batches, cleans the
text, counts how often each resulting term occurs in a sliding time window,
compares that count to the term's own recent history, and writes the
ranked result into **HBase** → **api** reads HBase (for trends) and Kafka
directly (for the raw live feed) and exposes both over plain JSON REST
endpoints → **dashboard** polls those endpoints and renders three views.
Nothing in this chain talks to anything two steps away - each arrow below
is one hop.

---

## Bluesky Jetstream *(external, not a container in this stack)*

**What it is:** Bluesky's public WebSocket firehose. It streams every
public event on the network (post creates/deletes, likes, follows, ...) as
JSON, with no authentication required.

**Output (consumed by `producer`):** a continuous stream of JSON
"commit" messages. The one field shape this whole project cares about:

```json
{
  "did": "did:plc:...",
  "time_us": 1725911162329308,
  "kind": "commit",
  "commit": {
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "rkey": "3kp...",
    "record": {
      "text": "the actual post text",
      "createdAt": "2024-09-09T19:46:02.102Z",
      "langs": ["en"]
    }
  }
}
```

**Endpoints used (with failover):**
`wss://jetstream2.us-east.bsky.network/subscribe`,
`wss://jetstream1.us-east.bsky.network/subscribe`,
`wss://jetstream2.us-west.bsky.network/subscribe`
(configurable via `producer`'s `JETSTREAM_URLS`).

---

## `producer`

**What it does:** the only component that talks to the outside internet.
Connects to Jetstream, keeps the connection alive, filters the firehose
down to what this project needs, and republishes each surviving post as a
small Kafka record.

**Input:** the Jetstream WebSocket stream described above.

**Filtering logic** (`src/filters.py`, `src/jetstream_client.py`) - a
message survives only if **all** of:
- `kind == "commit"`
- `commit.operation == "create"`
- `commit.collection == "app.bsky.feed.post"`
- the post's text is non-empty
- the post's `langs` intersects `LANG_FILTER` (default: `en` only)

**Output → Kafka topic `bluesky-posts`** (one JSON record per surviving
post, keyed by post id):

```json
{"id": "3kp...", "did": "did:plc:...", "text": "...", "timestamp": "2024-09-09T19:46:02.102Z", "lang": "en"}
```

**Resilience:**
- Reconnects with exponential backoff on disconnect, rotating across the
  configured Jetstream mirrors (`src/jetstream_client.py`).
- Persists the last-seen Jetstream cursor (`time_us`) to a file on the
  `producer-data` volume every 200 messages, and on reconnect resumes from
  `cursor - CURSOR_REWIND_US` (a few seconds back) so a restart doesn't
  lose events from the gap.
- On `SIGTERM`/`SIGINT` (`docker stop`), cancels its run loop and calls
  `Producer.flush()` before exiting, so buffered-but-undelivered Kafka
  messages aren't silently dropped (`src/main.py`).

**Configuration:** `services/producer/.env` - `JETSTREAM_URLS`,
`WANTED_COLLECTIONS`, `LANG_FILTER`, `KAFKA_BOOTSTRAP_SERVERS`,
`KAFKA_TOPIC`, `RECONNECT_BACKOFF_SECONDS`, `MAX_RECONNECT_BACKOFF_SECONDS`,
`CURSOR_REWIND_US`, `CURSOR_FILE`, `LOG_LEVEL`.

**Tech:** Python, `websockets` (async WebSocket client), `confluent-kafka`
(producer, `compression.type=lz4`).

**Code:** `services/producer/src/` - `main.py` (orchestration + signal
handling), `jetstream_client.py` (connection/reconnect), `filters.py`
(message → Kafka record), `kafka_producer.py` (thin Kafka publish wrapper),
`config.py`.

**Depends on:** Jetstream (internet), `kafka` (must be reachable; compose
waits for the `kafka-init` job to finish creating the topic first).
**Depended on by:** `kafka` (its only writer of real post data).

---

## `kafka`

**What it is:** the message broker that decouples ingestion from
processing. A single Apache Kafka 3.7 broker running in **KRaft mode**
(no separate Zookeeper container - the broker is also its own controller).

**Input:** writes from `producer` (one topic: `bluesky-posts`, 3
partitions, replication factor 1 since it's a single broker).

**Output:** reads from two independent consumers, each with its own
consumer group and offsets - neither affects the other:
- `spark-processor`'s Structured Streaming Kafka source (offsets tracked
  via its own checkpoint directory, not a classic consumer group)
- `api`'s `LivePostsFeed` consumer (group `api-live-feed-<random>`,
  `auto_offset_reset=latest`, **never commits offsets** - it's a
  best-effort tail, not an exactly-once consumer)

**Persistence:** topic data lives on the `kafka-data` volume
(`KAFKA_LOG_DIRS=/var/lib/kafka/data`), so a container restart doesn't
lose buffered messages.

**Companion one-shot job - `kafka-init`:** runs `kafka-topics.sh --create
--if-not-exists` for `bluesky-posts` once, after `kafka` reports healthy,
then exits. `producer` and `spark-processor` both wait on this job
completing successfully before they start, so the topic is guaranteed to
exist before anyone tries to read or write it.

**Configuration:** `docker-compose.yml` environment block (not a `.env`
file, since these are topology constants, not secrets) -
`KAFKA_NODE_ID`, `KAFKA_PROCESS_ROLES=broker,controller`,
`KAFKA_ADVERTISED_LISTENERS=PLAINTEXT://kafka:9092`,
`KAFKA_CONTROLLER_QUORUM_VOTERS`, etc. Root `.env`'s `KAFKA_CLUSTER_ID`
(generate with `kafka-storage.sh random-uuid`) and `KAFKA_TOPIC`.

**Code:** `infra/kafka/Dockerfile` - just the stock `apache/kafka:3.7.0`
image plus a writable `/var/lib/kafka/data` directory (a fresh named
volume mounted there needs to inherit write permission from *something*,
since the image runs as a non-root `appuser`).

**Depends on:** nothing (first thing to start).
**Depended on by:** `producer` (writer), `spark-processor` and `api`
(both readers).

---

## `spark-processor`

**What it does:** the trend-scoring engine. A PySpark **Structured
Streaming** job, running continuously, that turns a stream of raw posts
into ranked "what's trending" snapshots.

**Input:** reads micro-batches from Kafka topic `bluesky-posts`
(`startingOffsets=latest` - it only scores posts published after it
started; `failOnDataLoss=false` so a Kafka retention rollover doesn't
crash the query). Each micro-batch fires on a 30-second trigger
(`src/main.py`, `.trigger(processingTime="30 seconds")`).

**Processing pipeline** (see [`flowchart.md`](flowchart.md) for the full
decision tree):
1. Parse each Kafka record's JSON value against a fixed schema
   (`id, did, text, timestamp, lang`); drop anything with a null
   `text`/`did` or an unparseable `timestamp` - **or a `timestamp` more
   than `MAX_FUTURE_SKEW_SECONDS` (default 120s) ahead of the processing
   clock**, since that field is the post's self-reported `createdAt` and a
   client with a skewed clock can set it to anything (see
   [Known operational characteristics](#known-operational-characteristics)).
2. Run `preprocessing.preprocess(text)` (the [shared module](preprocessing.md))
   as a Spark UDF, explode the resulting list of terms into one row per
   `(timestamp, did, term)` (`src/cleaning.py`).
3. Group by a sliding window (`WINDOW_DURATION=5 minutes`,
   `SLIDE_DURATION=1 minute`, `WATERMARK_DELAY=2 minutes`) and `term`;
   count occurrences and `approx_count_distinct(did)`.
4. Drop candidates below `MIN_COUNT_THRESHOLD` or `MIN_DISTINCT_AUTHORS`
   (spam/noise guard).
5. Fetch every surviving candidate's trailing baseline average from HBase
   **in one batched `multiget` call** (`HBaseRestClient.get_rows`), compute
   `score = count / (baseline_avg + TREND_SMOOTHING)` for each, sort by
   score, keep the top `TOP_N`.
6. Update every surviving candidate's baseline via an exponential moving
   average (`BASELINE_EMA_ALPHA`) - not just the top N, so a term that
   drops out of the rankings doesn't lose its history. Written back **in
   one batched multi-row `PUT`** (`HBaseRestClient.put_rows`), chunked to
   stay within safe request-size limits rather than one HTTP call per term.

All of step 5-6's HBase I/O happens inside `foreachBatch`
(`src/sink.py`), on the Spark driver, via plain HTTP (see `hbase_client.py`)
rather than the HBase Java client - see
["Why HBase over REST"](#why-hbase-over-rest-instead-of-the-java-client)
below. The batching in steps 5-6 is what keeps this affordable even when a
window has thousands of candidate terms - see
[Known operational characteristics](#known-operational-characteristics).

**Output → HBase** (table details in the [`hbase`](#hbase) section below):
writes to `trends`, `term_history`, and `term_baseline` every batch that
has data, and to `pipeline_meta` whenever a new bucket produces a
non-empty top-N.

**State / checkpoint:** Spark's own checkpoint (Kafka offsets + windowed
aggregation state) lives on the `spark-checkpoints` volume
(`CHECKPOINT_DIR=/checkpoints/trending`). Deleting that volume resets the
stream to start consuming from `latest` again with no prior window state -
useful after a logic change that's incompatible with old state, expected
to be unnecessary for ordinary restarts.

**Configuration:** `services/spark-processor/.env` - Kafka connection,
`HBASE_REST_URL`, window/slide/watermark, `MAX_FUTURE_SKEW_SECONDS`,
`MIN_COUNT_THRESHOLD`, `MIN_DISTINCT_AUTHORS`, `MIN_TERM_LENGTH`,
`TREND_SMOOTHING`, `BASELINE_EMA_ALPHA`, `TOP_N`, `RETENTION_HOURS`,
`CHECKPOINT_DIR`, and the four HBase table names.

**Tech:** PySpark 3.4 (Structured Streaming), running `local[*]` inside a
single container (no separate Spark master/worker cluster - appropriate at
this data volume), `requests` for the HBase REST calls.

**Code:** `services/spark-processor/src/` - `main.py` (build + run the
streaming query), `cleaning.py` (Spark UDF wrapper around the shared
preprocessing module), `sink.py` (`foreachBatch` - scoring, ranking, HBase
writes), `trend_scoring.py` (the two pure-math functions: ratio-to-baseline
score, EMA update), `hbase_client.py`, `config.py`.

**Depends on:** `kafka` (reader), `hbase` (writer, via REST).
**Depended on by:** `hbase` (its only writer of trend data), indirectly
`api`/`dashboard` (they only ever see what this job decided was
trending).

### Why HBase over REST instead of the Java client

Both `spark-processor` and `api` talk to HBase over its REST (Stargate)
gateway with plain HTTP instead of the HBase Java client / `hbase-spark`
connector. That avoids pulling Hadoop/HBase jars with strict version
pinning into the Spark image - the data volume written per micro-batch is
just the ranked top-N terms plus baseline updates, so REST calls are fast
enough (with one caveat - see [Known operational characteristics](#known-operational-characteristics)
below).

---

## `preprocessing` *(shared code, not its own container)*

**What it does:** decides what counts as a "term" - hashtag rules,
stopwords, URL/mention/punctuation stripping, minimum word length. The
*one* place this logic lives; both `spark-processor` and `api` run the
literal same code. Full writeup, including how to change it safely and a
known limitation, in [`preprocessing.md`](preprocessing.md).

**Input:** one post's raw `text` string (plus a configurable
`min_term_length`).

**Output:** a `PreprocessResult` - `cleaned_text` (lowercased, stripped of
URLs/mentions/punctuation/apostrophes), `hashtags` (list), `words` (list),
and `.terms` (hashtags + words combined - what actually feeds the scorer).

**Where it physically lives:** `shared/preprocessing/` at the repo root,
vendored (via Docker `COPY`) into both `spark-processor`'s and `api`'s
images at build time. It is plain stdlib Python (`re` + `dataclasses`
only) - no Spark, no FastAPI - so it can be unit-tested standalone:
`python -m unittest shared.preprocessing.test_cleaning -v`.

**Depends on:** nothing.
**Depended on by:** `spark-processor` (via a Spark UDF, `cleaning.py`) and
`api` (called directly per post in `live_posts.py`).

---

## `hbase`

**What it is:** the serving store - holds ranked trends, per-term
history, per-term baselines, and a "what's the latest bucket" pointer. A
single HBase 1.2.6 node running in **standalone mode** (its own embedded
Zookeeper, no separate Zookeeper container) with the REST (Stargate)
gateway enabled alongside the master.

**Input:** writes from `spark-processor` only (`PUT`s over REST).
**Output:** reads from `api` only (`GET`s and range `Scan`s over REST).

**Persistence:** `hbase.rootdir` and the embedded Zookeeper's data dir
both point under `/hbase-data`, backed by the `hbase-data` volume.

**Tables** (all created lazily by `spark-processor` on first startup -
see `ensure_tables()` in `sink.py`):

| Table | Row key | Column family : columns | Written by | Read by |
|---|---|---|---|---|
| `trends` | `{bucket}#{rank:03d}` e.g. `202406091946#001` | `trends`: `rank, term, count, score, distinct_authors` | spark-processor | api (`GET /trending`) |
| `term_history` | `{term}#{bucket}` | `history`: `count, score` | spark-processor | api (`GET /trending/history`) |
| `term_baseline` | `t#{term}` *(prefixed - see note)* | `baseline`: `avg` | spark-processor | spark-processor only |
| `pipeline_meta` | fixed key `latest_bucket` | `meta`: `value, updated_at` | spark-processor | api (to find "now" without scanning) |

`bucket` is always `yyyyMMddHHmm` (UTC, minute granularity). TTL on
`trends`/`term_history` column families is set to `RETENTION_HOURS * 3600`
seconds at table-creation time, so old rows expire on their own - no
separate cleanup job.

> **Why `term_baseline` row keys are prefixed with `t#`:** HBase's REST
> gateway treats a handful of literal row-key segments as reserved
> sub-resources - `schema`, `regions`, `scanner`, `multiget`. A bare term
> as the row key collides with those whenever a real word matches one
> (a post about a database "schema" was enough to crash the pipeline in
> testing). The `t#` prefix can never collide with a fixed reserved word.

**Configuration:** `docker-compose.yml` environment block -
`HBASE_CONF_hbase_rootdir`, `HBASE_CONF_hbase_zookeeper_property_dataDir`,
`HBASE_CONF_hbase_cluster_distributed=false`. Table/column-family names
themselves are configured per-consumer (`TABLE_TRENDS` etc. in both
`spark-processor`'s and `api`'s `.env`) rather than hardcoded.

**Code:** `infra/hbase/Dockerfile` (wraps `bde2020/hbase-standalone` to
also start the REST gateway), `infra/hbase/start-hbase-with-rest.sh`.

**Ports:** `8080` (REST gateway - used by both `spark-processor` and
`api`), `16010` (Master web UI, for human debugging only - see
http://localhost:16010 once running).

**Depends on:** nothing externally (self-contained single-node cluster).
**Depended on by:** `spark-processor` (writer), `api` (reader).

---

## `api`

**What it does:** the only HTTP-facing service besides the dashboard
itself. A FastAPI app with two unrelated jobs bolted onto one process:
serving ranked trends out of HBase, and tailing the raw Kafka topic for a
live preview. They share nothing except the process they run in.

### Job 1 - trending endpoints (reads HBase)

**Input:** HBase, via `services/hbase_client.py` (`GET`/`Scan` over REST).

**Output - `GET /trending`** (optional `?at=yyyyMMddHHmm&limit=20`):
looks up `pipeline_meta/latest_bucket` if `at` is omitted, then scans
`trends` for that bucket's rows.
```json
{"bucket": "202406091946", "items": [{"rank": 1, "term": "#example", "count": 39, "score": 1.26, "distinct_authors": 35}]}
```

**Output - `GET /trending/history?term=...&limit=288`**: scans
`term_history` for that term's full row-key prefix range (`term#` to
`term$` - see the [comment in `hbase_client.py`](../services/api/src/services/hbase_client.py)
for why the boundary is exactly that, not just the bare term).
```json
{"term": "#example", "points": [{"bucket": "202406091946", "count": 39, "score": 1.26}]}
```

### Job 2 - live posts feed (reads Kafka directly)

**What it does:** on startup, launches a background `asyncio` task
(`LivePostsFeed`, `src/services/live_posts.py`) that subscribes to
`bluesky-posts` as its own consumer group and keeps the most recent
`LIVE_POSTS_BUFFER_SIZE` posts (default 200) in an in-memory
`collections.deque`. Every post is run through `preprocessing.preprocess()`
*once*, when it enters the buffer, and the result is stored alongside the
raw post.

**Input:** Kafka topic `bluesky-posts` directly (not HBase, not Spark's
output - a completely independent read path).

**Output - `GET /posts/recent?limit=50`**: the buffer, most-recent-first,
each item carrying both the raw post and its preprocessed form:
```json
{"items": [{
  "id": "3kp...", "did": "did:plc:...", "text": "raw text #tag", "lang": "en",
  "timestamp": "2024-09-09T19:46:02.102Z", "received_at": "2024-09-09T19:46:03.4Z",
  "cleaned_text": "raw text", "hashtags": ["#tag"], "words": ["raw", "text"]
}]}
```
This single endpoint backs *two* dashboard pages (`/live` and
`/preprocessing`) - they just render different fields of the same item.

**Other endpoints:** `GET /health` (used by Docker's healthcheck and by
`dashboard`'s `depends_on`).

**Configuration:** `services/api/.env` - `HBASE_REST_URL`, the four table
names, `TOP_N_DEFAULT`, `CORS_ORIGINS`, `KAFKA_BOOTSTRAP_SERVERS`,
`KAFKA_TOPIC`, `LIVE_POSTS_BUFFER_SIZE`, `MIN_TERM_LENGTH` (must match
`spark-processor`'s value for the preview to reflect reality).

**Tech:** FastAPI, `httpx` (async HBase REST client), `aiokafka` +
`cramjam` (async Kafka consumer; `cramjam` is what `aiokafka` actually
needs to decompress the producer's lz4-compressed messages - the separate
`lz4` PyPI package is *not* what it looks for).

**Code:** `services/api/src/` - `main.py` (app + lifespan: starts/stops
the live feed, owns the HBase client), `routers/trending.py`,
`routers/posts.py`, `services/hbase_client.py`, `services/live_posts.py`,
`schemas/` (Pydantic response models), `config.py`. Plus
`src/preprocessing/` - the vendored copy of `shared/preprocessing/`.

**Depends on:** `hbase` (reader), `kafka` (reader, for the live feed).
**Depended on by:** `dashboard` (its only data source).

---

## `dashboard`

**What it does:** the UI. A Next.js (App Router) app with three pages,
all polling `api` and rendering plain HTML/CSS - no charting library, no
client-side state management beyond `useState`/`useEffect`.

**Input:** exclusively `api`, over two different paths:
- **Server-rendered pages** (the term detail page) call `api` directly,
  server-side, using `API_INTERNAL_URL` (`http://api:8000` on the docker
  network) - the browser never sees this address.
- **Client-rendered, polling pages** (home, `/live`, `/preprocessing`)
  call *this app's own* Next.js route handlers (`/api/trending`,
  `/api/trending/history`, `/api/posts/recent`), which then proxy
  server-side to `api`. This is why the browser only ever needs to know
  `dashboard`'s own address, never `api`'s.

**Output:** HTML/JSON to the browser, on port `3000`.

### Pages

| Route | Polls | Renders |
|---|---|---|
| `/` (home) | `GET /api/trending` every 30s | "Trending now" ranked table + a historical time picker (`TrendingBoard.tsx`, `TimeSelector.tsx`, `TrendList.tsx`) |
| `/term/[term]` | `api`'s `/trending/history` directly (server component, one-shot per page load) | a sparkline + table of one term's count/score over time (`Sparkline.tsx`) |
| `/live` | `GET /api/posts/recent` every 2s | raw post cards: text with hashtags highlighted inline, language badge, relative time, shortened author DID (`LivePostsFeed.tsx`, `PostCard.tsx`) |
| `/preprocessing` | `GET /api/posts/recent` every 2s (same endpoint as `/live`) | the same posts as before/after cards: raw text next to cleaned text + extracted-term chips (`PreprocessingFeed.tsx`, `BeforeAfterCard.tsx`) |

**Configuration:** `services/dashboard/.env` - just `API_INTERNAL_URL`
(server-side only; nothing here is `NEXT_PUBLIC_*` because the browser
never needs to reach `api` directly).

**Tech:** Next.js 14 (App Router), TypeScript, React, plain CSS (light
theme, `app/globals.css`) - no UI framework, no charting library, no
state-management library.

**Code:** `services/dashboard/` - `app/` (pages + API route handlers),
`components/` (the pieces listed above plus `NavBar.tsx`), `lib/types.ts`
(shared TS interfaces mirroring `api`'s Pydantic schemas), `lib/format.ts`
(bucket formatting, relative time, DID shortening - small pure functions).

**Depends on:** `api` (its only data source).
**Depended on by:** nothing (it's the end of the chain - a human).

---

## Cross-cutting topics

### Docker network and ports

Every service is on one user-defined bridge network, `trending-net`
(`docker-compose.yml`). Only four ports are published to the host -
everything else is container-to-container only:

| Port | Service | Purpose |
|---|---|---|
| `3000` | `dashboard` | the app itself |
| `8000` | `api` | direct API access / debugging |
| `8080` | `hbase` | REST gateway - direct HBase access / debugging |
| `16010` | `hbase` | Master web UI |

`kafka` publishes no host port - nothing outside the docker network ever
needs to reach it directly.

### Volumes (what persists across `docker compose down`)

| Volume | Mounted on | Holds |
|---|---|---|
| `kafka-data` | `kafka:/var/lib/kafka/data` | topic log segments |
| `hbase-data` | `hbase:/hbase-data` | all four tables' data + embedded Zookeeper state |
| `producer-data` | `producer:/data` | the Jetstream resume cursor |
| `spark-checkpoints` | `spark-processor:/checkpoints` | Kafka offsets + windowed-aggregation state |

`docker compose down -v` removes all four (full reset). Removing just
`spark-checkpoints` is the documented way to force `spark-processor` to
restart its stream from scratch after an incompatible logic change.

### Env file strategy

Every service directory has its own `.env.example` (committed) and
`.env` (gitignored, created by copying the example). The root directory
has the same pattern for variables `docker-compose.yml` itself needs
(`KAFKA_CLUSTER_ID`, shared host ports). No service reads another
service's env file - `docker-compose.yml`'s `env_file:` directive scopes
each `.env` to exactly one container.

### Startup order

`docker-compose.yml`'s `depends_on` with `condition: service_healthy` /
`service_completed_successfully` enforces:

```
kafka, hbase  (no dependencies, start first)
  └─ kafka-init  (waits for kafka healthy, creates the topic, exits)
       ├─ producer  (waits for kafka-init to finish)
       └─ spark-processor  (waits for kafka-init + hbase healthy)
  └─ api  (waits for kafka + hbase healthy)
       └─ dashboard  (waits for api healthy)
```

### Known operational characteristics

Three real bugs were found by running this stack against the live Bluesky
firehose for an extended period (not by code review) and are recorded here
with what was actually observed, not just the fix:

- **HBase REST round-trips inside `spark-processor`'s `foreachBatch` were
  sequential and synchronous - fixed, but worth knowing why.** The original
  version did one GET (baseline lookup) plus up to two PUTs per *candidate*
  term, one at a time. In a live run, candidate counts climbing into the
  thousands per window pushed batch processing time past the 30s trigger
  interval (`ProcessingTimeExecutor: Current batch is falling behind`), and
  once a batch fell behind, the next one had even more Kafka backlog to
  work through, compounding - left running, this stalled new trending
  output entirely (the container kept running and looked "healthy"; it was
  just not keeping up). **Fix:** `HBaseRestClient.get_rows`/`put_rows`
  batch many terms into one HTTP call each (HBase REST's `multiget` for
  reads, multiple `Row` entries in one `PUT` body for writes - both
  verified directly against the REST gateway before relying on them),
  chunked to stay within safe request-size limits. Verified after the fix:
  a window with **5241 candidates** (versus 5197 at the point the
  unbatched version started failing) processed cleanly, with steady
  bucket-over-bucket progress and zero container restarts over an extended
  run.
- **A single clock-skewed client could permanently freeze trend output -
  fixed.** `timestamp` is each post's self-reported `createdAt`; nothing
  about Bluesky guarantees it reflects real time. A real post arrived
  during testing claiming to be created **~6.5 hours in the future**,
  pushing Spark's watermark (max event-time seen, which only ever
  increases) 56 minutes ahead of the actual wall clock. Every normal,
  correctly-timed post arriving after that was then "older than the
  watermark" and silently dropped before it could contribute to any
  window - no error, no crash, just zero new trending output forever
  (until a restart, which only delays the next occurrence). **Fix:**
  `spark-processor` now drops any post whose timestamp is more than
  `MAX_FUTURE_SKEW_SECONDS` (default 120s) ahead of the processing clock,
  *before* it reaches the watermark calculation. Verified by replaying the
  same scenario with a synthetic `timestamp: "2030-01-01T00:00:00Z"`
  message: the watermark stayed within a minute of the real wall clock
  instead of jumping forward.
- **`api`'s HBase scanner client merged cells across pages incorrectly -
  fixed.** HBase REST's scanner `batch` parameter caps *cells* returned per
  page, not rows. A row with 5 columns (like a `trends` row) can have its
  cells split across two scanner pages, and the original `scan_range`
  (`services/api/src/services/hbase_client.py`) treated each page's
  entries as already-complete rows, occasionally returning a row missing
  fields and crashing the endpoint with a `KeyError` (reproduced with
  `GET /trending?limit=2` - 2 doesn't divide 5 evenly, so the row-cell
  split landed mid-row; the default `limit=20` happened to divide evenly,
  which is why it went unnoticed initially). **Fix:** decoupled the
  scanner's page size from the caller's row limit and merged cells by row
  key across pages before truncating to the requested limit.
- **The live posts buffer is best-effort, by design, not a bug.** `api`'s
  Kafka consumer for `/posts/recent` never commits offsets and starts at
  `latest` on every restart - if `api` restarts, it briefly shows an empty
  feed until new posts arrive, rather than replaying history. This is
  intentional: it's a "what's happening right now" view, not a durable log.
