CREATE TABLE IF NOT EXISTS fetcher_tasks (
    correlation_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    response JSONB,
    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    expires_at TIMESTAMPTZ NOT NULL,
    claimed_at TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS fetcher_tasks_pending_idx
ON fetcher_tasks (created_at)
WHERE response IS NULL;

CREATE INDEX IF NOT EXISTS fetcher_tasks_expiration_idx
ON fetcher_tasks (expires_at);

CREATE TABLE IF NOT EXISTS app_cache (
    cache_key TEXT PRIMARY KEY,
    value TEXT NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL
);

CREATE INDEX IF NOT EXISTS app_cache_expiration_idx
ON app_cache (expires_at);
