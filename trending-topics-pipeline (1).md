# Trending Topics Detection Pipeline

A real-time data pipeline that ingests a stream of text, detects which topics
are *spiking* right now, and serves the ranked results for dashboards and
historical lookup.

> **Decisions locked in:**
> - **Source:** Bluesky Jetstream firehose (real public posts, no auth required)
> - **Dashboard:** Next.js web app
> - **No** Elasticsearch / Kibana — HBase serves trends directly, dashboard reads via API

---

## 1. Goal

Surface the topics, hashtags, or keywords that are trending **now** — meaning
terms whose frequency is rising abnormally fast compared to their recent
baseline, not simply the most frequent terms overall.

**"Frequent" vs "trending":**
- *Frequent* = appears a lot (often boring, stable, common words).
- *Trending* = appears unusually more than its own recent history (acceleration).

The pipeline ranks by acceleration, not raw count.

---

## 2. Architecture Overview

```
[ Bluesky Jetstream ]    <- WebSocket firehose of public posts (JSON, no auth)
      |
      v
( Producer / Connector )  <- WebSocket client -> filter posts -> push to Kafka
      |
      v
   ( Kafka )              <- ingestion + buffering, topic: bluesky-posts
      |
      v
( Spark Streaming )       <- tokenize, clean, count per window, score trend
      |
      +--> compare current window vs baseline (state / HBase)
      |
      v
   ( HBase )              <- store ranked trending terms by time bucket
      |
      v
( REST API )              <- reads HBase, exposes /trending endpoints
      |
      v
[ Next.js Dashboard ]     <- "what's trending now" + "what was trending at 3pm"
```

---

## 3. Components & Why Each Is Used

| Stage | Tool | Responsibility |
|-------|------|----------------|
| Data source | **Bluesky Jetstream** | Real-time WebSocket firehose of public posts as JSON (no auth) |
| Producer | **WebSocket client** (Python/Node) | Connect to Jetstream, filter post events, publish to Kafka |
| Ingestion | **Apache Kafka** | Buffer the post stream, decouple producer from processing, replay on failure |
| Processing | **Apache Spark (Structured Streaming)** | Tokenize, clean, count terms per sliding window, compute trend scores |
| NLP / features | **Spark MLlib** (Tokenizer, StopWordsRemover, HashingTF) or **Spark NLP** | Break text into terms, drop noise words, optional lemmatization |
| Storage / serving | **Apache HBase** | Low-latency store for ranked trends keyed by time bucket; holds baseline counts |
| API | **REST API** (FastAPI / Node) | Read trends from HBase, expose JSON endpoints to the dashboard |
| Dashboard | **Next.js** | Display current + historical trending topics |
| Orchestration (batch parts) | **Airflow** _(optional)_ | Schedule baseline recomputation, cleanup jobs |

---

## 4. Data Flow in Detail

### 4.1 Ingestion (Bluesky Jetstream → Kafka)

**Source — Bluesky Jetstream:** a simplified JSON WebSocket firehose. No
authentication required. Public instances (pick one nearest you, with failover):
- `wss://jetstream2.us-east.bsky.network/subscribe`
- `wss://jetstream1.us-east.bsky.network/subscribe`
- `wss://jetstream2.us-west.bsky.network/subscribe`

Filter to posts only with the `wantedCollections` parameter so you don't receive
likes, follows, etc:
```
wss://jetstream2.us-east.bsky.network/subscribe?wantedCollections=app.bsky.feed.post
```

**Sample Jetstream message** (post creation — fields trimmed):
```json
{
  "did": "did:plc:...",
  "time_us": 1725911162329308,
  "kind": "commit",
  "commit": {
    "operation": "create",
    "collection": "app.bsky.feed.post",
    "record": {
      "$type": "app.bsky.feed.post",
      "text": "the actual post text goes here",
      "createdAt": "2024-09-09T19:46:02.102Z",
      "langs": ["en"]
    }
  }
}
```

**Producer responsibilities:**
- Open the WebSocket, keep it alive, reconnect on drop.
- Use `time_us` as a **cursor** — on reconnect pass `?cursor=<last time_us>`
  (rewind a few seconds) for gapless playback.
- Keep only `kind == "commit"`, `operation == "create"`,
  `collection == "app.bsky.feed.post"`.
- Optionally filter `langs` (e.g. English only) to simplify NLP.
- Map each post into a Kafka record: `{ id, text, timestamp, lang }` where
  `timestamp` comes from `record.createdAt` (or `time_us`).
- Publish to Kafka topic `bluesky-posts`.

> **Note:** Jetstream is not formally part of the AT Protocol and may change; it
> also skips cryptographic verification. That's fine for this analytics use case.
> Volume is high (hundreds–thousands of posts/sec network-wide) — language and
> count-threshold filters keep it manageable. **Tip:** request `compress=true`
> (zstd) to cut bandwidth ~56%.

### 4.2 Processing (Spark Structured Streaming)
1. **Read** from Kafka topic `bluesky-posts`.
2. **Clean**: lowercase, strip URLs / punctuation / mentions, drop empty records.
3. **Tokenize**: split into terms, or extract **hashtags** specifically (a strong
   signal of topics on social media), or both.
4. **Remove stopwords**: drop common filler words.
5. **Count** terms per **sliding window** (e.g. 5-min window, sliding every 1 min).
6. **Score trend**: compare current-window count to baseline (see Section 5).
7. **Rank**: take top N by trend score per window.

### 4.3 Storage (HBase)
- Write ranked results keyed by time bucket.
- Suggested row key: `yyyyMMddHHmm` (reverse-timestamp optional for recent-first scans).
- Column family `trends`: `rank`, `term`, `count`, `score`.
- Also maintain a baseline table: term → trailing average count.

### 4.4 Serving (REST API → Next.js)

**REST API** (FastAPI or a Node/Express server) reads from HBase:
- `GET /trending` → latest time-bucket row, top N trending terms.
- `GET /trending?at=yyyyMMddHHmm` → historical trends for any past bucket.
- `GET /trending/history?term=...` → a single term's count over time (for a chart).

**Next.js dashboard** consumes those endpoints:
- A "Trending Now" list/board that auto-refreshes (poll every ~30–60s, or push
  via WebSocket/SSE if you want it live).
- A time selector to view past buckets.
- Per-term detail with a sparkline of its recent activity.
- Use Next.js **route handlers** (`app/api/...`) as a thin proxy to the REST API,
  or call the API directly from server components — keeps HBase off the public web.

---

## 5. Defining "Trending" (the core logic)

Pick one scoring method:

**Option A — Ratio to baseline (simple)**
```
score = current_window_count / (baseline_avg_count + smoothing)
```
Rank terms by score descending. `smoothing` (e.g. +1) avoids divide-by-zero and
suppresses ultra-rare terms.

**Option B — Z-score (statistically cleaner)**
```
score = (current_count - baseline_mean) / baseline_stddev
```
Captures "how many standard deviations above normal" — better at ignoring noise.

**Baseline** = trailing average of each term's count over a longer window
(e.g. last 1–24 hours), held in Spark state or refreshed in HBase.

**Filters to avoid junk:**
- Minimum count threshold (a term must appear at least K times to qualify).
- Stopword + spam list.
- Optional: minimum number of distinct users/sources mentioning it.

---

## 6. Tech Stack Summary

**Core**
- Bluesky Jetstream — real-time data source (WebSocket JSON firehose)
- Apache Kafka — streaming ingestion
- Apache Spark (Structured Streaming) — processing engine
- Apache HBase — low-latency serving store
- HDFS / object storage — underlying storage for HBase + checkpoints

**NLP**
- Spark MLlib feature tools, or Spark NLP for richer tokenization/NER

**Serving**
- REST API — FastAPI (Python) or Node/Express
- **Next.js** — dashboard UI

**Supporting (optional)**
- ZooKeeper — coordination (Kafka/HBase dependency)
- Airflow — orchestration for batch/baseline jobs

**Language**
- Producer: Python (`websockets`) or Node (`ws`)
- Spark jobs: PySpark or Scala
- Dashboard: TypeScript / React (Next.js)

---

## 7. Open Questions (still to decide)

Resolved: source is Bluesky Jetstream (posts have `createdAt` timestamps),
dashboard is Next.js, streaming pipeline. Remaining choices:

- [ ] Unit of "topic": individual words, **hashtags**, n-grams, or named entities?
- [ ] Language filter — English only, or multi-language?
- [ ] Window size and slide interval (e.g. 5-min window / 1-min slide)?
- [ ] Trend scoring method: ratio-to-baseline (A) or z-score (B)?
- [ ] How long to retain historical trends in HBase?
- [ ] Dashboard refresh: polling vs WebSocket/SSE push?

---

## 8. Suggested Build Order

1. Write the producer: connect to Jetstream, print post text to console.
2. Producer → push filtered posts to Kafka topic `bluesky-posts`.
3. Spark job: read Kafka → print token counts per window (verify the basics).
4. Add cleaning + stopword removal (and/or hashtag extraction).
5. Add windowed counting and top-N ranking (raw frequency first).
6. Add baseline tracking and switch ranking to a trend score.
7. Wire output to HBase with the time-bucket schema.
8. Build the REST API over HBase.
9. Build the Next.js dashboard against the API.
10. Tune thresholds, window sizes, and the scoring method.

Start simple (raw frequency) and only add the baseline/acceleration scoring once
the end-to-end flow works — it's much easier to debug in that order. Likewise,
get the producer printing posts before you wire in Kafka.
