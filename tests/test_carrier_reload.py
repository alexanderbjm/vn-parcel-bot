import asyncio
import textwrap
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

from tests.fakes import FakeClock, FakeNotifier
from vn_parcel_bot.bot.app import alert_rejections, carrier_modules_job
from vn_parcel_bot.carriers.registry import CarrierRegistry
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)

TRACKER = r"""
from datetime import UTC, datetime

from vn_parcel_bot.carriers.api import CarrierModule, Rule
from vn_parcel_bot.carriers.models import TrackingEvent, TrackingResult

DESCRIPTION = "version one"


class TrackerCarrier:
    code = "tracker"
    display_name = "Tracker"
    needs_phone = False

    async def fetch(self, http, tracking_number, phone_last4=None):
        event = TrackingEvent(time=datetime(2026, 9, 1, tzinfo=UTC), description=DESCRIPTION)
        return TrackingResult(
            carrier="tracker", tracking_number=tracking_number, found=True, events=(event,)
        )


MODULE = CarrierModule(
    code="tracker",
    display_name="Tracker",
    rules=(Rule(r"TR\d{8}", 100),),
    examples=(("TR00000001", True),),
    build_client=TrackerCarrier,
)
"""


def write(directory, name, source):
    (directory / f"{name}.py").write_text(textwrap.dedent(source), encoding="utf-8")


async def no_sleep(seconds):
    return None


async def test_poller_picks_up_a_reloaded_module(tmp_path, settings):
    modules = tmp_path / "modules"
    await asyncio.to_thread(modules.mkdir)
    await asyncio.to_thread(write, modules, "tracker", TRACKER)
    registry = await asyncio.to_thread(CarrierRegistry.load, modules)
    repo = await Repository.open(tmp_path / "t.sqlite3")
    try:
        await repo.upsert_user(2, now=T0, is_allowed=True)
        await repo.add_parcel(
            user_id=2,
            carrier="tracker",
            candidates=("tracker",),
            tracking_number="TR00000001",
            phone_last4=None,
            now=T0,
            next_check_at=T0,
        )
        clock = FakeClock(T0)
        quiet_free = replace(settings, quiet_hours=None)
        poller = Poller(
            repo, registry, None, FakeNotifier(), quiet_free, clock, no_sleep, lambda: 0.0
        )
        await poller.run_cycle()
        new_source = TRACKER.replace("version one", "version two")
        await asyncio.to_thread(write, modules, "tracker", new_source)
        await asyncio.to_thread(registry.refresh)
        await asyncio.to_thread(registry.refresh)
        clock.advance(timedelta(hours=1))
        await poller.run_cycle()
        descriptions = {event.description for event in await repo.list_events(1, 10)}
        assert descriptions == {"version one", "version two"}
    finally:
        await repo.close()


async def test_rejections_alert_admin_once_per_version(tmp_path, settings):
    modules = tmp_path / "modules"
    await asyncio.to_thread(modules.mkdir)
    await asyncio.to_thread(write, modules, "broken", "MODULE = 1 / 0\n")
    registry = await asyncio.to_thread(CarrierRegistry.load, modules)
    repo = await Repository.open(tmp_path / "t.sqlite3")
    notifier = FakeNotifier()
    deps = SimpleNamespace(registry=registry, repo=repo, notifier=notifier, settings=settings)
    context = SimpleNamespace(bot_data={"deps": deps})
    try:
        await alert_rejections(deps, registry.startup_rejections)
        await alert_rejections(deps, registry.startup_rejections)
        assert len(notifier.sent) == 1
        chat_id, text, silent = notifier.sent[0]
        assert chat_id == settings.admin_telegram_id
        assert "<code>broken</code>" in text
        assert "ZeroDivisionError line 1" in text
        assert silent is False
        await asyncio.to_thread(write, modules, "broken", "MODULE = 2 / 0\n")
        await carrier_modules_job(context)
        await carrier_modules_job(context)
        assert len(notifier.sent) == 2
    finally:
        await repo.close()
