# Sequence diagram

Who calls whom, in order, across one full ingest-to-display cycle. See
[`components.md`](components.md) for what each participant below actually
does in prose, [`architecture.md`](architecture.md) for the static
topology, [`flowchart.md`](flowchart.md) for the decision logic inside
each step, and [`preprocessing.md`](preprocessing.md) for what
`preprocess()` actually does.

```mermaid
sequenceDiagram
    autonumber
    participant JS as Bluesky Jetstream
    participant P as producer
    participant K as kafka
    participant S as spark-processor
    participant H as hbase (REST :8080)
    participant A as api (FastAPI :8000)
    participant D as dashboard (Next.js :3000)
    participant I as indexer
    participant ES as elasticsearch (:9200)
    participant KB as kibana (:5601)
    participant U as Browser

    Note over JS,P: Ingestion (continuous)
    JS->>P: wss JSON commit event
    P->>P: filter kind/operation/collection + language
    P->>K: publish {id, did, text, timestamp, lang}

    Note over K,H: Processing (every ~30s trigger, windows close on watermark)
    K->>S: consume micro-batch
    S->>S: clean text, extract hashtags + words
    S->>S: windowed count + distinct authors
    S->>H: GET term_baseline/{term}
    H-->>S: baseline avg (or 404)
    S->>S: score = count / (baseline_avg + smoothing)
    S->>H: PUT trends/{bucket}#{rank}
    S->>H: PUT term_history/{term}#{bucket}
    S->>H: PUT term_baseline/{term} (EMA update)
    S->>H: PUT pipeline_meta/latest_bucket

    Note over U,A: Serving - "Trending now" (polls every 30s)
    U->>D: GET /
    D->>U: server-rendered page
    loop every 30s while live
        U->>D: GET /api/trending
        D->>A: GET /trending
        A->>H: GET pipeline_meta/latest_bucket
        H-->>A: bucket
        A->>H: Scan trends start=bucket end=bucket+1
        H-->>A: ranked rows
        A-->>D: JSON TrendingResponse
        D-->>U: JSON TrendingResponse
    end

    Note over U,A: Serving - term detail page
    U->>D: GET /term/{term}
    D->>A: GET /trending/history?term={term}
    A->>H: Scan term_history start=term# end=term$
    H-->>A: history rows
    A-->>D: JSON TermHistoryResponse
    D-->>U: page with Sparkline

    Note over K,A: Live posts feed (independent of the processing above)
    A->>K: subscribe to bluesky-posts (own consumer group, latest offset)
    loop continuously
        K->>A: raw post message
        A->>A: preprocess(text) - same shared module S uses
        A->>A: append {raw, cleaned_text, hashtags, words} to ring buffer
    end

    Note over U,A: Serving - "Live posts" page (polls every 2s)
    U->>D: GET /live
    D->>U: server-rendered page
    loop every 2s while on page
        U->>D: GET /api/posts/recent
        D->>A: GET /posts/recent
        A-->>D: JSON RecentPostsResponse (from buffer)
        D-->>U: JSON RecentPostsResponse
    end

    Note over U,A: Serving - "Preprocessing" before/after page (polls every 2s)
    U->>D: GET /preprocessing
    D->>U: server-rendered page
    loop every 2s while on page
        U->>D: GET /api/posts/recent
        D->>A: GET /posts/recent
        A-->>D: JSON RecentPostsResponse (raw + cleaned_text + terms)
        D-->>U: JSON RecentPostsResponse
    end

    Note over K,ES: Indexing (independent of everything above - own consumer group, commits offsets)
    I->>ES: HEAD bluesky-posts (create index with mapping if missing)
    I->>KB: GET /api/data_views, then POST one if missing (best-effort, retried)
    loop continuously
        K->>I: raw post message
        I->>I: preprocess(text) - same shared module S and A use
        I->>I: append {raw, cleaned_text, hashtags, words} to buffer
        alt buffer full or flush interval elapsed
            I->>ES: PUT _bulk (upsert by post id)
            I->>K: commit offsets
        end
    end

    Note over U,KB: Exploration - Kibana Discover / visualizations (ad hoc, not polled by anything)
    U->>KB: GET /app/discover
    KB->>ES: search query (full text, filters, aggregations)
    ES-->>KB: matching documents
    KB-->>U: rendered results / histogram
```

## Reading this diagram

- The first two `Note` blocks happen independently and continuously - the
  producer never waits for Spark, and Spark never waits for a dashboard
  request.
- The dashboard's home page is a client component that polls
  `/api/trending` (its own Next.js route handler) rather than calling
  `api` directly; the route handler is the only thing that knows `api`'s
  internal address.
- The term detail page (`/term/{term}`) is server-rendered, so it calls
  `api` directly during the server-side render instead of going through
  the proxy route.
- The live posts feed has its own always-on consume loop inside `api`,
  completely decoupled from the request/response cycle - a page poll just
  reads whatever is currently in the buffer, it never blocks on Kafka.
- `/live` and `/preprocessing` poll the exact same endpoint and buffer -
  they just render different fields of the same `PostItem`. There's no
  separate "preprocessing" service or extra Kafka read for that page.
- The indexing block is a third, fully independent reader of `kafka` -
  it doesn't wait for or block on `spark-processor` or `api`'s live feed,
  and they don't wait on it either. Unlike `api`'s live-feed consumer, it
  commits offsets, so a restart resumes instead of skipping data.
- `I->>KB` (the data-view bootstrap) happens once at `indexer` startup and
  is best-effort - if `kibana` isn't reachable yet it retries a bounded
  number of times in the background and gives up quietly, it never blocks
  or affects the indexing loop above it.
- The Kibana exploration block has no polling loop and no fixed interval -
  it only happens when a person opens Kibana, unlike every other "Serving"
  block in this diagram.
