from datetime import UTC, datetime

import pytest

from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.sharing import share_token, shared_parcel

T0 = datetime(2026, 9, 1, tzinfo=UTC)


@pytest.fixture
async def repo():
    r = await Repository.open(":memory:")
    await r.upsert_user(1, now=T0, is_allowed=True)
    yield r
    await r.close()


async def add(repo):
    return await repo.add_parcel(
        user_id=1,
        carrier="spx",
        candidates=("spx",),
        tracking_number="SPXVN000000000001",
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )


async def test_share_token_is_reused_and_resolves(repo):
    parcel = await add(repo)
    token = await share_token(repo, parcel.id)
    assert len(token) == 12
    assert await share_token(repo, parcel.id) == token
    assert (await shared_parcel(repo, token)).id == parcel.id
    assert await shared_parcel(repo, "missing") is None


async def test_token_of_removed_parcel_resolves_to_none(repo):
    parcel = await add(repo)
    token = await share_token(repo, parcel.id)
    await repo.delete_parcel(parcel.id)
    assert await shared_parcel(repo, token) is None
