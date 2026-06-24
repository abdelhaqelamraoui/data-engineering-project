# System architecture

Static view of every service, the Docker network that connects them, and
where each one persists state. See [`components.md`](components.md) for
the prose write-up of each box below (what it does, exact input/output,
configuration), [`flowchart.md`](flowchart.md) for the step-by-step
processing logic, [`sequence-diagram.md`](sequence-diagram.md) for the
request/response timing between services, and
[`preprocessing.md`](preprocessing.md) for the shared cleaning module shown
below as `PREP`.

```mermaid
flowchart TB
    Jetstream(["Bluesky Jetstream<br/>wss firehose, public, no auth"])
    Browser(["Browser / User"])
    PREP["shared/preprocessing/<br/>(repo root, pure Python)<br/>vendored into both images at build time"]

    subgraph NET["Docker network: trending-net"]
        direction TB

        subgraph ING["Ingestion"]
            PROD["producer<br/>Python · websockets + confluent-kafka"]
        end

        KAFKA[("kafka<br/>Apache Kafka 3.7 · KRaft, 1 broker<br/>topic: bluesky-posts")]

        subgraph PROC["Processing"]
            SPARK["spark-processor<br/>PySpark 3.4 Structured Streaming"]
        end

        HBASE[("hbase<br/>HBase 1.2.6 standalone + REST :8080<br/>tables: trends, term_history,<br/>term_baseline, pipeline_meta")]

        subgraph SERVE["Serving"]
            API["api<br/>FastAPI :8000"]
            DASH["dashboard<br/>Next.js :3000"]
        end

        subgraph SEARCH["Search & exploration (additive, not on the trending path)"]
            INDEXER["indexer<br/>Python · confluent-kafka + elasticsearch"]
            ES[("elasticsearch<br/>single-node 8.15 · REST :9200<br/>index: bluesky-posts")]
            KIBANA["kibana<br/>web UI :5601"]
        end

        VOLP[("volume<br/>producer-data")]
        VOLK[("volume<br/>kafka-data")]
        VOLH[("volume<br/>hbase-data")]
        VOLS[("volume<br/>spark-checkpoints")]
        VOLE[("volume<br/>elasticsearch-data")]
    end

    Jetstream -->|"wss JSON events"| PROD
    PROD -->|"publish {id, did, text,<br/>timestamp, lang}"| KAFKA
    KAFKA -->|"consume micro-batches<br/>(spark consumer group)"| SPARK
    KAFKA -->|"tail raw topic<br/>(api's own consumer group)"| API
    KAFKA -->|"consume + commit offsets<br/>(indexer's own consumer group)"| INDEXER
    SPARK -->|"REST PUT<br/>ranked trends + baseline"| HBASE
    HBASE -->|"REST GET / Scan"| API
    API -->|"JSON over HTTP :8000"| DASH
    Browser -->|"HTTP :3000"| DASH
    Browser -->|"HTTP :5601"| KIBANA
    DASH -.->|"server-side proxy<br/>/api/trending*, /api/posts/recent"| API
    INDEXER -->|"_bulk upsert"| ES
    KIBANA -->|"queries"| ES
    INDEXER -.->|"bootstrap data view<br/>(best-effort, retried)"| KIBANA

    PREP -.->|"COPY at build time"| SPARK
    PREP -.->|"COPY at build time"| API
    PREP -.->|"COPY at build time"| INDEXER

    PROD -.-> VOLP
    KAFKA -.-> VOLK
    HBASE -.-> VOLH
    SPARK -.-> VOLS
    ES -.-> VOLE
```

## Notes

- **Solid arrows** are the live data path; **dashed arrows** are
  proxying/persistence relationships.
- `dashboard` never talks to `api` from the browser directly - its own
  Next.js route handlers (`/api/trending`, `/api/trending/history`,
  `/api/posts/recent`) proxy server-side to `api` over the docker network,
  so only `dashboard`'s port needs to be public.
- `kafka` runs in KRaft mode (no Zookeeper container). `hbase` runs in
  standalone mode, which starts an embedded Zookeeper inside its own
  container - neither needs a separate coordination service here.
- `api` and `spark-processor` both talk to HBase over its REST gateway
  (port 8080) instead of the HBase Java client, so no Hadoop/HBase jars
  need to ship inside the Spark image.
- `api` reads `kafka` twice over: once as the source for `/trending`'s
  upstream data (indirectly, via what Spark writes to HBase) and once
  directly, tailing the raw topic for the `/live` and `/preprocessing`
  pages' post feed. The two consumers are independent - same topic,
  different consumer groups.
- `PREP` is source code, not a running service - `spark-processor`, `api`,
  and `indexer` each get their own copy baked into their image at build
  time (see [`preprocessing.md`](preprocessing.md)). They don't call each
  other or a shared process for this; they just all started from the same
  file.
- The `SEARCH` subgraph is a parallel branch off the same Kafka topic, not
  a later stage of the trending pipeline - `indexer`/`elasticsearch`/`kibana`
  never feed into `hbase`, `api`'s trending endpoints, or `dashboard`, and
  nothing in the trending path reads from them either. The project's
  original design brief explicitly chose HBase over Elasticsearch/Kibana
  *for serving trends*; this branch exists for a different job
  (full-text search and ad-hoc exploration of the raw firehose) that the
  trending path was never meant to cover.
- `indexer` commits its Kafka offsets (unlike `api`'s live-feed consumer,
  which never does) because it's building a durable archive - a restart
  should resume, not skip data.
