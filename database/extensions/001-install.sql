CREATE EXTENSION IF NOT EXISTS pgmq;
CREATE EXTENSION IF NOT EXISTS pg_cron;

\getenv application_username APP_DB_USER

SELECT format('GRANT USAGE ON SCHEMA pgmq TO %I', :'application_username') \gexec
SELECT format('GRANT CREATE ON SCHEMA pgmq TO %I', :'application_username') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA pgmq TO %I', :'application_username') \gexec
SELECT format('GRANT USAGE ON SCHEMA cron TO %I', :'application_username') \gexec
SELECT format('GRANT EXECUTE ON ALL FUNCTIONS IN SCHEMA cron TO %I', :'application_username') \gexec

SELECT format('GRANT ALL ON ALL TABLES IN SCHEMA pgmq TO %I', :'application_username') \gexec
SELECT format('GRANT ALL ON ALL SEQUENCES IN SCHEMA pgmq TO %I', :'application_username') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA pgmq GRANT ALL ON TABLES TO %I', :'application_username') \gexec
SELECT format('ALTER DEFAULT PRIVILEGES IN SCHEMA pgmq GRANT ALL ON SEQUENCES TO %I', :'application_username') \gexec
