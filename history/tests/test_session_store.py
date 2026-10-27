import pytest

from history.app.services.postgres_cache import PostgresCache


@pytest.mark.asyncio
async def test_postgres_session_store_reads_and_sets_expiring_values() -> None:
    class FakePool:
        calls = 0

        async def fetchval(self, query: str, *args: object) -> str | int:
            assert query.lstrip().startswith("SELECT value")
            assert args == ("flight-tracker:session:abc",)
            return '{"theme":"light"}'

        async def execute(self, query: str, *args: object) -> str:
            self.calls += 1
            if self.calls == 1:
                assert query == "DELETE FROM app_cache WHERE expires_at <= NOW()"
                assert not args
            else:
                assert "INSERT INTO app_cache" in query
                assert args == ("flight-tracker:session:abc", '{"theme":"light"}', 3600)
                assert "ON CONFLICT (cache_key)" in query
            return "INSERT 0 1"

    store = PostgresCache(FakePool())
    key = "flight-tracker:session:abc"
    value = '{"theme":"light"}'

    await store.set(key, value, ex=3600)

    assert await store.get(key) == value


@pytest.mark.asyncio
async def test_postgres_cache_deletes_a_key() -> None:
    class FakePool:
        async def execute(self, query: str, *args: object) -> str:
            assert query == "DELETE FROM app_cache WHERE cache_key = $1"
            assert args == ("flight-tracker:session:abc",)
            return "DELETE 1"

    await PostgresCache(FakePool()).delete("flight-tracker:session:abc")
