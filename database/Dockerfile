FROM postgres:16-bookworm

ARG PGMQ_VERSION=v1.10.0

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        git \
        make \
        postgresql-16-cron \
        postgresql-server-dev-16 \
    && git clone --depth 1 --branch "${PGMQ_VERSION}" \
        https://github.com/pgmq/pgmq.git /tmp/pgmq \
    && make -C /tmp/pgmq/pgmq-extension \
    && make -C /tmp/pgmq/pgmq-extension install \
    && rm -rf /tmp/pgmq \
    && apt-get purge -y --auto-remove git make postgresql-server-dev-16 \
    && rm -rf /var/lib/apt/lists/*

COPY database/docker-entrypoint.sh /usr/local/bin/flight-tracker-entrypoint.sh
RUN chmod 755 /usr/local/bin/flight-tracker-entrypoint.sh

ENTRYPOINT ["/usr/local/bin/flight-tracker-entrypoint.sh"]
CMD ["postgres"]
