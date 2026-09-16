from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest

from tests.fakes import FakeCarrier, FakeNotifier, fake_registry
from vn_parcel_bot import texts
from vn_parcel_bot.bot import app as app_module
from vn_parcel_bot.bot.app import UPDATE_META_KEY, announce_update
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller

T0 = datetime(2026, 9, 1, 5, 0, tzinfo=UTC)
REVISION = "abc1234 · 01/01/2026"


@pytest.fixture
async def env(settings, monkeypatch):
    repo = await Repository.open(":memory:")
    http = httpx.AsyncClient()
    notifier = FakeNotifier()
    registry = fake_registry({"spx": FakeCarrier("spx")})
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(repo, registry, http, notifier, settings, lambda: T0)
    deps = Deps(settings, repo, http, parcels, poller, notifier)

    revision = {"value": REVISION}

    async def fake_revision():
        return revision["value"]

    monkeypatch.setattr(app_module, "deployed_revision_async", fake_revision)
    yield SimpleNamespace(
        deps=deps, repo=repo, notifier=notifier, settings=settings, revision=revision
    )
    await http.aclose()
    await repo.close()


async def test_the_admin_is_told_once_per_revision(env):
    await announce_update(env.deps)
    assert env.notifier.sent == [
        (env.settings.admin_telegram_id, texts.BOT_UPDATED.format(revision=REVISION), False)
    ]
    assert await env.repo.get_meta(UPDATE_META_KEY) == REVISION

    await announce_update(env.deps)
    assert len(env.notifier.sent) == 1


async def test_a_changed_revision_is_announced_again(env):
    await announce_update(env.deps)
    env.revision["value"] = "def5678 · 02/01/2026"
    await announce_update(env.deps)

    assert len(env.notifier.sent) == 2
    assert "def5678 · 02/01/2026" in env.notifier.sent[-1][1]


async def test_nothing_is_sent_when_git_cannot_answer(env):
    env.revision["value"] = None
    await announce_update(env.deps)

    assert env.notifier.sent == []
    # Nothing recorded, so a later start with a working git still announces.
    assert await env.repo.get_meta(UPDATE_META_KEY) is None


async def test_a_failed_send_is_retried_on_the_next_start(env):
    env.notifier.fail_with = RuntimeError("telegram is down")
    await announce_update(env.deps)
    assert await env.repo.get_meta(UPDATE_META_KEY) is None

    env.notifier.fail_with = None
    await announce_update(env.deps)
    assert await env.repo.get_meta(UPDATE_META_KEY) == REVISION
    assert len(env.notifier.sent) == 2
