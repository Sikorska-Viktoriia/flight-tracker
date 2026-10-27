\getenv application_username APP_DB_USER
\getenv application_password APP_DB_PASSWORD


SELECT format(
    CASE WHEN EXISTS (SELECT FROM pg_catalog.pg_roles WHERE rolname = :'application_username')
        THEN 'ALTER ROLE %I WITH LOGIN PASSWORD %L'
        ELSE 'CREATE ROLE %I WITH LOGIN PASSWORD %L'
    END,
    :'application_username',
    :'application_password'
) \gexec


SELECT format(
    'GRANT CONNECT ON DATABASE %I TO %I',
    current_database(),
    :'application_username'
) \gexec

SELECT format(
    'GRANT USAGE, CREATE ON SCHEMA public TO %I',
    :'application_username'
) \gexec


SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON TABLES TO %I',
    :'application_username'
) \gexec

SELECT format(
    'ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT ALL ON SEQUENCES TO %I',
    :'application_username'
) \gexec