import asyncio
import json
import logging
import gzip
from datetime import datetime
from pathlib import Path
from decimal import Decimal

logger = logging.getLogger(__name__)

BACKUP_DIR = Path("/backups")

TABLES = [
    "users", "admins", "categories", "products", "product_items",
    "orders", "order_items", "delivered_items", "payments",
    "payment_events", "promo_codes", "audit_logs", "settings",
]


class _Encoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, Decimal):
            return str(obj)
        if hasattr(obj, "isoformat"):
            return obj.isoformat()
        return super().default(obj)


async def create_backup(database_url: str) -> str | None:
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M")
    out_file = BACKUP_DIR / f"rinnstore_{timestamp}.json.gz"

    try:
        import asyncpg
        url = database_url.replace("postgresql+asyncpg://", "postgresql://").replace("postgresql+psycopg2://", "postgresql://")
        conn = await asyncio.wait_for(asyncpg.connect(url), timeout=30)

        dump = {"timestamp": timestamp, "tables": {}}
        for table in TABLES:
            try:
                rows = await conn.fetch(f"SELECT * FROM {table}")
                dump["tables"][table] = [dict(r) for r in rows]
            except Exception as e:
                logger.warning(f"Backup skip {table}: {e}")
                dump["tables"][table] = []

        await conn.close()

        data = json.dumps(dump, cls=_Encoder, ensure_ascii=False, indent=2).encode("utf-8")
        with gzip.open(out_file, "wb") as f:
            f.write(data)

        size_kb = out_file.stat().st_size // 1024
        logger.info(f"Backup created: {out_file} ({size_kb} KB)")
        _cleanup_old_backups(keep=7)
        return str(out_file)

    except Exception as e:
        logger.error(f"Backup error: {e}")
        return None


def _cleanup_old_backups(keep: int = 7) -> None:
    files = sorted(BACKUP_DIR.glob("rinnstore_*.json.gz"), key=lambda f: f.stat().st_mtime)
    for f in files[:-keep]:
        try:
            f.unlink()
        except Exception:
            pass


def list_backups() -> list[dict]:
    if not BACKUP_DIR.exists():
        return []
    files = sorted(BACKUP_DIR.glob("rinnstore_*.json.gz"), key=lambda f: f.stat().st_mtime, reverse=True)
    result = []
    for f in files[:10]:
        size_kb = f.stat().st_size // 1024
        result.append({"name": f.name, "size_kb": size_kb})
    return result


async def backup_scheduler(database_url: str, interval_hours: int = 6) -> None:
    logger.info(f"Backup scheduler started (every {interval_hours}h)")
    await asyncio.sleep(300)
    while True:
        try:
            await create_backup(database_url)
        except Exception as e:
            logger.error(f"Scheduler backup error: {e}")
        await asyncio.sleep(interval_hours * 3600)
