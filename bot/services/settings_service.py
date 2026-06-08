from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete
from ..models import Setting

_DEFAULTS = {
    "cryptobot_token": "",
    "rollypay_api_key": "",
    "rollypay_terminal_id": "",
    "rollypay_signing_secret": "",
    "webhook_host": "",
    "support_username": "support",
    "required_channel": "",
    "shop_name": "RINN STORE",
    "backup_interval": "6",
    "pp_url": "https://telegra.ph/Politika-konfidencialnosti--RINN-STORE-06-05",
    "tos_url": "https://telegra.ph/Polzovatelskoe-soglashenie--RINN-STORE-06-05",
}

_cache: dict[str, str] = {}


async def load_all_settings(session: AsyncSession) -> None:
    result = await session.execute(select(Setting))
    for row in result.scalars().all():
        _cache[row.key] = row.value


async def get_setting(session: AsyncSession, key: str, default: str = "") -> str:
    if key in _cache:
        return _cache[key]
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        _cache[key] = row.value
        return row.value
    return _DEFAULTS.get(key, default)


async def set_setting(session: AsyncSession, key: str, value: str) -> None:
    result = await session.execute(select(Setting).where(Setting.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = value
    else:
        session.add(Setting(key=key, value=value))
    await session.commit()
    _cache[key] = value


async def get_all_settings(session: AsyncSession) -> dict[str, str]:
    result = await session.execute(select(Setting))
    db_settings = {row.key: row.value for row in result.scalars().all()}
    merged = dict(_DEFAULTS)
    merged.update(db_settings)
    return merged


def get_cached(key: str) -> str:
    return _cache.get(key, _DEFAULTS.get(key, ""))
