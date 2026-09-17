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
SHA = "abc1234"
REVISION = "abc1234 · 01/01/2026"
SUBJECTS = ["feat: hang each list row off branches", "fix: keep stale parcels stale"]


@pytest.fixture
async def env(settings, monkeypatch):
    repo = await Repository.open(":memory:")
    http = httpx.AsyncClient()
    notifier = FakeNotifier()
    registry = fake_registry({"spx": FakeCarrier("spx")})
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(repo, registry, http, notifier, settings, lambda: T0)
    deps = Deps(settings, repo, http, parcels, poller, notifier)

    state = {"sha": SHA, "revision": REVISION, "subjects": list(SUBJECTS), "since": "unset"}

    async def fake_revision():
        return state["revision"]

    async def fake_sha():
        return state["sha"]

    async def fake_commits(since):
        state["since"] = since
        return state["subjects"]

    monkeypatch.setattr(app_module, "deployed_revision_async", fake_revision)
    monkeypatch.setattr(app_module, "deployed_revision_sha_async", fake_sha)
    monkeypatch.setattr(app_module, "revision_commits_async", fake_commits)
    yield SimpleNamespace(deps=deps, repo=repo, notifier=notifier, settings=settings, state=state)
    await http.aclose()
    await repo.close()


async def test_the_notice_carries_the_revision_and_what_changed(env):
    await announce_update(env.deps)

    ((chat_id, body, silent),) = env.notifier.sent
    assert chat_id == env.settings.admin_telegram_id
    assert silent is False
    assert REVISION in body
    assert "<b>Thay đổi:</b>" in body
    for subject in SUBJECTS:
        assert subject in body
    assert await env.repo.get_meta(UPDATE_META_KEY) == SHA


async def test_the_first_notice_lists_the_most_recent_commits(env):
    # No recorded sha: there is no range to bound, so it must still say something.
    await announce_update(env.deps)

    assert env.state["since"] is None
    assert SUBJECTS[0] in env.notifier.sent[-1][1]


async def test_a_later_notice_bounds_the_range_to_the_last_reported_sha(env):
    await announce_update(env.deps)
    env.state["sha"] = "def5678"
    env.state["revision"] = "def5678 · 02/01/2026"
    await announce_update(env.deps)

    assert env.state["since"] == SHA
    assert len(env.notifier.sent) == 2


async def test_the_same_revision_is_not_announced_twice(env):
    await announce_update(env.deps)
    await announce_update(env.deps)
    assert len(env.notifier.sent) == 1


async def test_an_older_recording_of_sha_plus_date_is_still_recognised(env):
    # Releases before this change wrote "sha · date" into the same meta key.
    await env.repo.set_meta(UPDATE_META_KEY, REVISION)

    await announce_update(env.deps)

    assert env.notifier.sent == []


async def test_no_subjects_still_sends_the_revision(env):
    env.state["subjects"] = []
    await announce_update(env.deps)

    ((_, body, _),) = env.notifier.sent
    assert REVISION in body
    assert "Thay đổi" not in body


async def test_nothing_is_sent_when_git_cannot_answer(env):
    env.state["revision"] = None
    await announce_update(env.deps)

    assert env.notifier.sent == []
    assert await env.repo.get_meta(UPDATE_META_KEY) is None


async def test_a_failed_send_is_retried_on_the_next_start(env):
    env.notifier.fail_with = RuntimeError("telegram is down")
    await announce_update(env.deps)
    assert await env.repo.get_meta(UPDATE_META_KEY) is None

    env.notifier.fail_with = None
    await announce_update(env.deps)
    assert await env.repo.get_meta(UPDATE_META_KEY) == SHA
    assert len(env.notifier.sent) == 2


def test_the_notice_body_is_escaped():
    from vn_parcel_bot.services.formatting import format_update_notice

    body = format_update_notice("abc <b>", ["fix: <script> & </b>"])
    assert "<code>abc &lt;b&gt;</code>" in body
    assert "&lt;script&gt; &amp; &lt;/b&gt;" in body


def test_only_the_newest_changes_are_listed():
    from vn_parcel_bot.constants import MAX_UPDATE_NOTES
    from vn_parcel_bot.services.formatting import format_update_notice

    subjects = [f"feat: change {index}" for index in range(MAX_UPDATE_NOTES + 5)]
    body = format_update_notice(REVISION, subjects)

    assert "feat: change 0" in body
    assert f"feat: change {MAX_UPDATE_NOTES}" not in body
    assert texts.BOT_UPDATED_MORE.format(count=5) in body
