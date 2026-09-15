from types import SimpleNamespace

import pytest

from tests.test_callback_handler import (  # noqa: F401
    CHAT,
    SPX,
    T0,
    USER,
    Msg,
    env,
    tap,
    user_update,
)
from tests.test_maps import blank_tile
from tests.test_parcel_maps import FakeGeocoder
from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_user import PENDING_LOCATION, location_message
from vn_parcel_bot.services.maps import MapError
from vn_parcel_bot.services.parcel_maps import ParcelMaps

HUB = "21-HNI Thanh Tri 2 Hub"


async def tiles(z, x, y):
    return blank_tile()


@pytest.fixture
def maps_env(env):  # noqa: F811
    env.deps.maps = ParcelMaps(env.repo, FakeGeocoder(), tiles, env.settings)
    return env


async def add_parcel(env, place=HUB):  # noqa: F811
    parcel = await env.repo.add_parcel(
        user_id=USER,
        carrier="spx",
        candidates=("spx",),
        tracking_number=SPX,
        phone_last4=None,
        now=T0,
        next_check_at=T0,
    )
    if place is not None:
        await env.repo.set_place(parcel.id, place)
    return await env.repo.get_parcel(parcel.id)


def callback_data(markup):
    return [button.callback_data for row in markup.inline_keyboard for button in row]


async def test_card_shows_the_place_line_and_the_map_button(maps_env):
    parcel = await add_parcel(maps_env)
    query = await tap(maps_env, f"p:{parcel.id}:card")
    text, markup = query.edits[-1]
    assert text.endswith("\n" + texts.PLACE_ONLY_LINE.format(place="Kho Thanh Tri"))
    assert f"p:{parcel.id}:map" in callback_data(markup)


async def test_card_without_maps_keeps_the_old_layout(env):  # noqa: F811
    parcel = await add_parcel(env)
    query = await tap(env, f"p:{parcel.id}:card")
    text, markup = query.edits[-1]
    assert "📍" not in text
    assert f"p:{parcel.id}:map" not in callback_data(markup)


async def test_map_without_home_asks_for_the_location(maps_env):
    parcel = await add_parcel(maps_env)
    query = await tap(maps_env, f"p:{parcel.id}:map")
    assert query.answers == [None]
    assert maps_env.bot.sent[-1][1] == texts.LOCATION_ASK
    assert maps_env.context.user_data[PENDING_LOCATION] == {"map_parcel": parcel.id}
    assert maps_env.deps.notifier.photos == []


async def test_map_is_sent_as_a_photo_with_a_cooldown(maps_env):
    parcel = await add_parcel(maps_env)
    await maps_env.repo.set_home(USER, 21.03, 105.85)
    query = await tap(maps_env, f"p:{parcel.id}:map")
    assert query.answers == [None]
    chat_id, png, caption, silent = maps_env.deps.notifier.photos[-1]
    assert (chat_id, silent) == (CHAT, False)
    assert png.startswith(b"\x89PNG")
    assert "Kho Thanh Tri" in caption
    again = await tap(maps_env, f"p:{parcel.id}:map")
    assert again.answers == [texts.MAP_TOO_SOON]
    assert len(maps_env.deps.notifier.photos) == 1


async def test_map_without_a_place_or_when_drawing_fails(maps_env, monkeypatch):
    parcel = await add_parcel(maps_env, place=None)
    await maps_env.repo.set_home(USER, 21.03, 105.85)
    assert (await tap(maps_env, f"p:{parcel.id}:map")).answers == [texts.MAP_NO_PLACE]
    await maps_env.repo.set_place(parcel.id, HUB)

    async def broken(*args, **kwargs):
        raise MapError("tile")

    monkeypatch.setattr(maps_env.deps.maps, "photo", broken)
    assert (await tap(maps_env, f"p:{parcel.id}:map")).answers == [texts.MAP_FAILED]
    assert maps_env.deps.notifier.photos == []


async def test_map_of_another_users_parcel_is_refused(maps_env):
    parcel = await add_parcel(maps_env)
    query = await tap(maps_env, f"p:{parcel.id}:map", user_id=222)
    assert query.answers == [texts.CARD_NOT_FOUND]


async def test_location_shared_for_a_map_sends_that_map(maps_env):
    parcel = await add_parcel(maps_env)
    await tap(maps_env, f"p:{parcel.id}:map")
    message = Msg(90, None, [])
    message.location = SimpleNamespace(latitude=21.03, longitude=105.85)
    await location_message(user_update(message), maps_env.context)
    assert message.sent[0][0] == texts.LOCATION_SAVED
    assert len(maps_env.deps.notifier.photos) == 1
    assert PENDING_LOCATION not in maps_env.context.user_data
