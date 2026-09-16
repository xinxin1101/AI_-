import asyncio
import json

from app.core.config import Settings
from app.services.persistence import PostgresRepository


async def _main() -> int:
    settings = Settings(persistence_enabled=True, database_auto_create=False)
    repository = PostgresRepository(settings)
    await repository.start()
    try:
        result = await repository.cleanup_retention()
        print(json.dumps(result, ensure_ascii=False, indent=2))
    finally:
        await repository.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
