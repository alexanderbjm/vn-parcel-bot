"""Carrier module scripts: load changed files now and alert the admin about rejected ones."""

import asyncio
import logging
from collections.abc import Sequence
from html import escape

from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.carriers.registry import Rejection

log = logging.getLogger(__name__)


async def alert_rejections(deps: Deps, rejections: Sequence[Rejection]) -> None:
    for rejection in rejections:
        key = f"module-rejected:{rejection.code}"
        if await deps.repo.get_meta(key) == rejection.file_hash:
            continue
        text = texts.MODULE_REJECTED.format(
            code=escape(rejection.code), error=escape(rejection.error)
        )
        try:
            await deps.notifier.send(deps.settings.admin_telegram_id, text, silent=False)
        except Exception:
            log.warning("module rejection alert failed code=%s", rejection.code, exc_info=True)
            continue
        await deps.repo.set_meta(key, rejection.file_hash)


async def reload_carrier_scripts(deps: Deps) -> int:
    """Load changed carrier module files at once (no second read); returns how many loaded."""
    if deps.registry is None:
        return 0
    report = await asyncio.to_thread(deps.registry.refresh, True)
    await alert_rejections(deps, report.rejected)
    return len(report.reloaded)
