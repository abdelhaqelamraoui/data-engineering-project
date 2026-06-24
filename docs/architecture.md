# System architecture

Static view of every service, the Docker network that connects them, and
where each one persists state. See [`flowchart.md`](flowchart.md) for the
step-by-step processing logic, [`sequence-diagram.md`](sequence-diagram.md)
for the request/response timing between services, and
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

        VOLP[("volume<br/>producer-data")]
        VOLK[("volume<br/>kafka-data")]
        VOLH[("volume<br/>hbase-data")]
        VOLS[("volume<br/>spark-checkpoints")]
    end

    Jetstream -->|"wss JSON events"| PROD
    PROD -->|"publish {id, did, text,<br/>timestamp, lang}"| KAFKA
    KAFKA -->|"consume micro-batches<br/>(spark consumer group)"| SPARK
    KAFKA -->|"tail raw topic<br/>(api's own consumer group)"| API
    SPARK -->|"REST PUT<br/>ranked trends + baseline"| HBASE
    HBASE -->|"REST GET / Scan"| API
    API -->|"JSON over HTTP :8000"| DASH
    Browser -->|"HTTP :3000"| DASH
    DASH -.->|"server-side proxy<br/>/api/trending*, /api/posts/recent"| API

    PREP -.->|"COPY at build time"| SPARK
    PREP -.->|"COPY at build time"| API

    PROD -.-> VOLP
    KAFKA -.-> VOLK
    HBASE -.-> VOLH
    SPARK -.-> VOLS
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
- `PREP` is source code, not a running service - `spark-processor` and
  `api` each get their own copy baked into their image at build time (see
  [`preprocessing.md`](preprocessing.md)). They don't call each other or a
  shared process for this; they just both started from the same file.
