import hashlib
import logging
from pathlib import Path

import asyncpg

from history.app.core.config import PROJECT_ROOT

logger = logging.getLogger(__name__)
MIGRATIONS_DIR = PROJECT_ROOT / "database" / "migrations"
MIGRATION_LOCK_ID = 714_203_811


async def run_migrations(
    dsn: str,
    migrations_dir: Path = MIGRATIONS_DIR,
    storage_backend: str = "standalone",
) -> None:
    migrations = sorted(migrations_dir.glob("*.sql"))
    if storage_backend != "postgres_native":
        migrations = [
            migration
            for migration in migrations
            if migration.name != "003_postgres_native_backends.sql"
        ]
    if storage_backend == "postgres_extensions":
        migrations.extend(sorted((migrations_dir / "extensions").glob("*.sql")))
    if not migrations:
        raise RuntimeError(f"No database migrations found in {migrations_dir}")

    connection = await asyncpg.connect(dsn=dsn, command_timeout=30)
    try:
        await connection.execute("SELECT pg_advisory_lock($1)", MIGRATION_LOCK_ID)
        await _apply_migrations(connection, migrations)
    finally:
        try:
            await connection.execute("SELECT pg_advisory_unlock($1)", MIGRATION_LOCK_ID)
        finally:
            await connection.close()


async def _apply_migrations(
    connection: asyncpg.Connection,
    migrations: list[Path],
) -> None:
    await connection.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            checksum TEXT
        )
        """
    )
    await connection.execute("ALTER TABLE schema_migrations ADD COLUMN IF NOT EXISTS checksum TEXT")

    for migration in migrations:
        contents = migration.read_text(encoding="utf-8")
        checksum = hashlib.sha256(contents.encode("utf-8")).hexdigest()
        async with connection.transaction():
            applied_checksum = await connection.fetchval(
                "SELECT checksum FROM schema_migrations WHERE version = $1",
                migration.name,
            )
            if applied_checksum is not None:
                if applied_checksum != checksum:
                    raise RuntimeError(
                        f"Applied migration {migration.name} was modified; "
                        "create a new migration instead"
                    )
                continue

            await connection.execute(contents)
            await connection.execute(
                """
                INSERT INTO schema_migrations (version, checksum)
                VALUES ($1, $2)
                ON CONFLICT (version) DO UPDATE SET checksum = EXCLUDED.checksum
                """,
                migration.name,
                checksum,
            )
            logger.info("applied database migration %s", migration.name)
