CREATE TABLE IF NOT EXISTS fetcher_responses (
    correlation_id TEXT PRIMARY KEY,
    response JSONB NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS fetcher_responses_expiration_idx
ON fetcher_responses (expires_at);

CREATE OR REPLACE FUNCTION notify_pgmq_fetcher_response() RETURNS trigger AS $$
BEGIN
    PERFORM pg_notify('fetcher_responses', NEW.correlation_id);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS fetcher_responses_notify ON fetcher_responses;
CREATE TRIGGER fetcher_responses_notify
AFTER INSERT OR UPDATE OF response ON fetcher_responses
FOR EACH ROW
EXECUTE FUNCTION notify_pgmq_fetcher_response();

SELECT pgmq.create('flight_tracker_tasks');

CREATE OR REPLACE FUNCTION cleanup_flight_tracker_storage() RETURNS void AS $$
BEGIN
    DELETE FROM app_cache WHERE expires_at <= NOW();
    DELETE FROM fetcher_responses WHERE expires_at <= NOW();
    PERFORM pgmq.delete('flight_tracker_tasks', msg_id)
    FROM pgmq.q_flight_tracker_tasks
    WHERE enqueued_at <= NOW() - INTERVAL '1 minute'
      AND vt <= NOW();
END
$$ LANGUAGE plpgsql;

SELECT cron.schedule(
    'flight-tracker-storage-cleanup',
    '*/1 * * * *',
    'SELECT cleanup_flight_tracker_storage()'
);
