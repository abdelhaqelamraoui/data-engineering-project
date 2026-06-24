FROM apache/spark-py:v3.4.0

USER root

COPY requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Pre-resolve the Spark<->Kafka connector jars at build time and copy the
# ones missing from the base image onto the Spark classpath, so the running
# container needs no network access to start the stream.
COPY docker/warmup.py /tmp/warmup.py
RUN /opt/spark/bin/spark-submit \
      --packages org.apache.spark:spark-sql-kafka-0-10_2.12:3.4.0 \
      --conf spark.jars.ivy=/tmp/.ivy2 \
      /tmp/warmup.py \
    && cp /tmp/.ivy2/jars/org.apache.spark_spark-sql-kafka-0-10_2.12-3.4.0.jar /opt/spark/jars/ \
    && cp /tmp/.ivy2/jars/org.apache.spark_spark-token-provider-kafka-0-10_2.12-3.4.0.jar /opt/spark/jars/ \
    && cp /tmp/.ivy2/jars/org.apache.kafka_kafka-clients-3.3.2.jar /opt/spark/jars/ \
    && cp /tmp/.ivy2/jars/org.apache.commons_commons-pool2-2.11.1.jar /opt/spark/jars/ \
    && rm -rf /tmp/.ivy2 /tmp/warmup.py

RUN mkdir -p /checkpoints && chmod -R 777 /checkpoints
VOLUME ["/checkpoints"]

COPY src/ /opt/spark/work-dir/src/
ENV HOME=/opt/spark/work-dir
RUN chmod -R g+rwX /opt/spark/work-dir
WORKDIR /opt/spark/work-dir/src

USER 185

CMD ["/opt/spark/bin/spark-submit", "--master", "local[*]", "main.py"]
