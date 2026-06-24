# Trending Topics Detection Pipeline

Real-time pipeline that ingests the Bluesky Jetstream firehose, detects which
hashtags/keywords are *spiking* (not just frequent), and serves the ranked
results to a Next.js dashboard. See [`trending-topics-pipeline (1).md`](<trending-topics-pipeline (1).md>)
for the original design brief.

## Architecture

```
Bluesky Jetstream (wss, public firehose)
        |
        v
  producer (Python)  --publishes-->  Kafka topic "bluesky-posts"
        |
        +-----------------------------------------+
        v                                          v
  spark-processor (PySpark Structured Streaming)   indexer (Python)
        | tokenize, extract hashtags/keywords,     | preprocess + bulk upsert
        | windowed counts, ratio-to-baseline score |
        v                                          v
  HBase (REST gateway)                       Elasticsearch  <--queries-- Kibana (:5601)
   4 tables: trends, term_history,
   term_baseline, pipeline_meta
        |
        v
  api (FastAPI)  --read-only REST-->  dashboard (Next.js)
```

The Elasticsearch/Kibana branch is additive: it's a separate, independent
reader of the same Kafka topic for full-text search and ad-hoc exploration
of the raw firehose. It does not feed the trending pipeline and the
trending pipeline does not feed it - HBase still serves trends directly,
unchanged, exactly as originally decided (see
[Search and exploration with Kibana](#search-and-exploration-with-kibana-additive-not-on-the-trending-path)
below for why both exist).

Each box is its own container, its own Dockerfile, and its own `.env` file -
see [Services](#services) below. Everything is wired together by the root
[`docker-compose.yml`](docker-compose.yml).

**For the full picture, read [`docs/components.md`](docs/components.md)** -
a component-by-component reference covering what each piece does, exactly
where its input comes from, exactly where its output goes, and how it's
configured. The diagrams (system architecture, step-by-step flowchart, and
a service-to-service sequence diagram) are in the same [`docs/`](docs/architecture.md)
folder.

## Decisions made (resolving the brief's open questions)

| Question | Decision |
|---|---|
| Unit of "topic" | Hashtags (`#tag`) **and** stopword-filtered keywords, unioned into one `term` stream |
| Language filter | English only (`langs` contains `en`), filtered at the producer |
| Window / slide | 5-minute sliding window, 1-minute slide |
| Trend scoring | Option A - ratio to baseline: `score = count / (baseline_avg + smoothing)`, baseline kept as an EMA per term |
| Retention | 24h, enforced via HBase column-family TTL (no separate cleanup job needed) |
| Dashboard refresh | Polling every 30s |

## Running it

```bash
cp .env.example .env                                  # shared compose vars
for svc in producer spark-processor api dashboard indexer; do
  cp services/$svc/.env.example services/$svc/.env
done

# .env needs a real KAFKA_CLUSTER_ID - generate one:
docker run --rm apache/kafka:3.7.0 /opt/kafka/bin/kafka-storage.sh random-uuid

docker compose up -d --build
```

Then open:
- **Dashboard:** http://localhost:3000 - "Trending" board, a **"Live posts"**
  page (`/live`) streaming raw firehose posts as they're published, and a
  **"Preprocessing"** page (`/preprocessing`) showing each post's raw text
  next to its cleaned text and extracted terms, all polled every 2s
- **API:** http://localhost:8000/trending, http://localhost:8000/trending/history?term=...,
  http://localhost:8000/posts/recent
- **Kibana:** http://localhost:5601 - Discover app, data view "Bluesky Posts"
  is pre-created automatically; full-text search over raw posts, facet on
  `hashtags`/`words`/`lang`, see volume over time
- **Elasticsearch REST API:** http://localhost:9200
- **HBase master UI:** http://localhost:16010
- **HBase REST gateway:** http://localhost:8080

First trending results take a few minutes to appear (5-min windows need a
2-minute watermark to close, plus the baseline needs at least one prior
observation before scores are meaningful).

## Services

| Service | Tech | Responsibility |
|---|---|---|
| `producer` | Python, `websockets` + `confluent-kafka` | Connects to Jetstream with failover/reconnect/cursor-resume, filters to English `app.bsky.feed.post` creates, publishes `{id, did, text, timestamp, lang}` to Kafka |
| `kafka` | Apache Kafka 3.7 (KRaft, single broker) | Buffers/decouples ingestion from processing |
| `spark-processor` | PySpark 3.4 Structured Streaming | Cleans text, extracts hashtags + keywords, windowed counts, distinct-author filter, ratio-to-baseline scoring, writes to HBase over its REST gateway |
| `hbase` | HBase 1.2.6 standalone + REST gateway | Serving store: `trends` (by time bucket), `term_history` (by term, for sparklines), `term_baseline` (EMA state), `pipeline_meta` (latest-bucket pointer) |
| `api` | FastAPI | `GET /trending`, `GET /trending?at=`, `GET /trending/history?term=` over HBase; `GET /posts/recent` over an in-memory buffer fed by its own Kafka consumer |
| `dashboard` | Next.js (App Router) | Light-themed UI: trending board (polling), historical time selector, per-term sparkline page, live raw-post feed, and a preprocessing before/after view; route handlers proxy the browser to the internal API so the dashboard never needs a public API URL |
| `indexer` | Python, `confluent-kafka` + `elasticsearch` | A third, independent Kafka consumer (commits offsets, unlike `api`'s live feed) that preprocesses and bulk-upserts every post into Elasticsearch, and bootstraps a matching Kibana data view on startup |
| `elasticsearch` | Elasticsearch 8.15, single-node, security disabled | Full-text searchable archive of every post (index `bluesky-posts`) - separate from and additive to the HBase-based trending store |
| `kibana` | Kibana 8.15 | Web UI for exploring `elasticsearch`: full-text search, faceting on hashtags/words/lang, a post-volume histogram |

### Live posts feed and the preprocessing preview

`api` runs a second, independent Kafka consumer (its own consumer group,
`auto_offset_reset=latest`, no offset commits) that just tails the raw
`bluesky-posts` topic into a bounded in-memory deque - completely separate
from the Spark job's consumption of the same topic. As each post lands in
that buffer, `api` also runs it through the same `preprocess()` function the
Spark job uses (see below) and stores the cleaned text + extracted terms
alongside the raw post. `GET /posts/recent` serves that buffer as-is:
- the dashboard's `/live` page polls it every 2s and renders the raw text,
  language badge, relative time, and highlighted hashtags;
- the `/preprocessing` page polls the *same* endpoint and renders the raw
  text next to the cleaned text and extracted term chips, side by side.

### The preprocessing module is shared, not duplicated

`shared/preprocessing/` is the one place that defines what counts as a
"term" - hashtag rules, stopwords, URL/mention/punctuation stripping. Both
`spark-processor` (the real scoring pipeline, via a Spark UDF) and `api`
(the before/after preview, calling it directly) run the literal same code,
vendored into each image at build time. Edit that one module and rebuild
those two services; nothing else changes. Full details, including how to
test it standalone and how the Docker build context is wired for this, are
in [`docs/preprocessing.md`](docs/preprocessing.md).

### Search and exploration with Kibana (additive, not on the trending path)

The brief that started this project explicitly decided **against**
Elasticsearch/Kibana for serving trends - HBase does that, and still does,
unchanged. Kibana was added afterward for a need HBase was never meant to
cover: full-text search and ad-hoc exploration over the raw firehose.
Neither the dashboard's `/live` page (a 200-post rolling window) nor the
trending API (ranked terms only) let you search arbitrary post text or
facet over an arbitrary time range - `indexer` → `elasticsearch` → `kibana`
does, as a separate branch off the same Kafka topic that the trending
pipeline neither feeds nor depends on.

`indexer` preprocesses each post with the same shared `preprocess()`
function as `spark-processor` and `api`, then bulk-upserts (`_bulk`,
flushed every `BULK_FLUSH_SIZE` documents or `BULK_FLUSH_INTERVAL_SECONDS`,
not one call per post) into the `bluesky-posts` index, and on startup
auto-creates a matching Kibana data view (best-effort, retried - Kibana
starting slowly never blocks indexing). Unlike `api`'s live-feed consumer,
`indexer` commits its Kafka offsets, since it's building a durable archive
rather than a "right now" snapshot.

### Why HBase over REST instead of the Java client

The Spark job and the API both talk to HBase over its REST (Stargate)
gateway with plain HTTP instead of the HBase Java client / `hbase-spark`
connector. That avoids pulling Hadoop/HBase jars with strict version pinning
into the Spark image - the data volume being written per micro-batch is just
the ranked top-N terms, so REST calls are fast enough.

### Why no separate Zookeeper

Kafka runs in KRaft mode (no Zookeeper needed). HBase runs in standalone
mode, which starts its own embedded Zookeeper inside the same container -
appropriate for this single-node deployment.

## Project layout

```
docker-compose.yml          # wires every service together
.env.example                 # shared ports / Kafka cluster id
docs/                        # components reference, architecture/flowchart/sequence diagrams, preprocessing
infra/
  kafka/Dockerfile           # apache/kafka + writable data dir for the named volume
  hbase/Dockerfile           # bde2020/hbase-standalone + REST gateway startup script
shared/
  preprocessing/             # cleaning/term-extraction rules - see docs/preprocessing.md
services/
  producer/                  # Jetstream -> Kafka
  spark-processor/           # Kafka -> trend scoring -> HBase (vendors shared/preprocessing/)
  api/                       # HBase + Kafka -> REST API (vendors shared/preprocessing/)
  dashboard/                 # REST API -> Next.js UI
  indexer/                   # Kafka -> Elasticsearch + Kibana data view (vendors shared/preprocessing/)
```

Every service directory has its own `Dockerfile`, `.env.example`, and
(Python services) a `src/` package split into `config.py`, the I/O clients,
and the business logic - kept separate so each service can be built, run,
and reasoned about independently. The one exception is `shared/preprocessing/`:
`spark-processor`, `api`, and `indexer` all build with the repo root as
their Docker build context specifically so they can each `COPY` it in -
see [`docs/preprocessing.md`](docs/preprocessing.md) for why and how.
`elasticsearch` and `kibana` use their stock images directly (no
`Dockerfile`/custom build), configured entirely through environment
variables in `docker-compose.yml` - the same pattern already used for
`kafka`'s and `hbase`'s topology-level config.
