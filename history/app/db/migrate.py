import asyncio

from history.app.core.config import get_settings
from history.app.core.logging_config import configure_logging
from history.app.db.migrations import run_migrations


async def main() -> None:
    settings = get_settings()
    await run_migrations(settings.database_url, storage_backend=settings.selected_storage_backend)


if __name__ == "__main__":
    configure_logging()
    asyncio.run(main())
