ALTER TABLE app_cache SET UNLOGGED;

CREATE OR REPLACE FUNCTION notify_fetcher_task() RETURNS TRIGGER AS $$
BEGIN
    PERFORM pg_notify('fetcher_tasks', NEW.correlation_id);
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS fetcher_task_notify ON fetcher_tasks;
CREATE TRIGGER fetcher_task_notify
AFTER INSERT ON fetcher_tasks
FOR EACH ROW
EXECUTE FUNCTION notify_fetcher_task();

CREATE OR REPLACE FUNCTION notify_fetcher_response() RETURNS TRIGGER AS $$
BEGIN
    IF TG_OP = 'INSERT' AND NEW.response IS NOT NULL THEN
        PERFORM pg_notify('fetcher_responses', NEW.correlation_id);
    ELSIF NEW.response IS NOT NULL AND OLD.response IS DISTINCT FROM NEW.response THEN
        PERFORM pg_notify('fetcher_responses', NEW.correlation_id);
    END IF;
    RETURN NEW;
END
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS fetcher_response_notify ON fetcher_tasks;
CREATE TRIGGER fetcher_response_notify
AFTER INSERT OR UPDATE OF response ON fetcher_tasks
FOR EACH ROW
EXECUTE FUNCTION notify_fetcher_response();
