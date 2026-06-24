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
        v
  spark-processor (PySpark Structured Streaming)
        | tokenize, extract hashtags/keywords, windowed counts,
        | ratio-to-baseline trend score
        v
  HBase (REST gateway)  <- 4 tables: trends, term_history, term_baseline, pipeline_meta
        |
        v
  api (FastAPI)  --read-only REST-->  dashboard (Next.js)
```

Each box is its own container, its own Dockerfile, and its own `.env` file -
see [Services](#services) below. Everything is wired together by the root
[`docker-compose.yml`](docker-compose.yml).

For diagrams (system architecture, step-by-step flowchart, and a
service-to-service sequence diagram), see [`docs/`](docs/architecture.md).

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
for svc in producer spark-processor api dashboard; do
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
docs/                        # architecture, flowchart, sequence, preprocessing docs
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
```

Every service directory has its own `Dockerfile`, `.env.example`, and
(Python services) a `src/` package split into `config.py`, the I/O clients,
and the business logic - kept separate so each service can be built, run,
and reasoned about independently. The one exception is `shared/preprocessing/`:
`spark-processor` and `api` both build with the repo root as their Docker
build context specifically so they can each `COPY` it in - see
[`docs/preprocessing.md`](docs/preprocessing.md) for why and how.
