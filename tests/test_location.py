import logging
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest
from telegram import ReplyKeyboardMarkup, ReplyKeyboardRemove

from vn_parcel_bot import texts
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LOCATION,
    cancel_cmd,
    location_cmd,
    location_message,
    text_message,
)
from vn_parcel_bot.db.repo import Repository

T0 = datetime(2026, 9, 15, 3, 0, tzinfo=UTC)


class Msg:
    def __init__(self, sent, text=None, location=None):
        self.sent = sent
        self.text = text
        self.location = location
        self.message_id = 70
        self.caption = None
        self.reply_to_message = None

    async def reply_text(self, text, **kwargs):
        self.sent.append((text, kwargs.get("reply_markup")))
        return SimpleNamespace(message_id=71)


async def _no_delete(*args, **kwargs):
    return None


@pytest.fixture
async def env(tmp_path, settings):
    repo = await Repository.open(tmp_path / "bot.sqlite3")
    try:
        await repo.upsert_user(1, now=T0, is_allowed=True)
        deps = SimpleNamespace(repo=repo, settings=settings, maps=None)
        context = SimpleNamespace(
            bot_data={"deps": deps, "settings": settings},
            user_data={},
            args=[],
            bot=SimpleNamespace(delete_message=_no_delete),
        )
        yield SimpleNamespace(repo=repo, context=context, sent=[])
    finally:
        await repo.close()


def update(message):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=1, full_name="U", first_name="U", username=None),
        effective_chat=SimpleNamespace(id=1),
        effective_message=message,
    )


async def test_location_command_offers_the_location_button(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    text, markup = env.sent[-1]
    assert text == texts.LOCATION_ASK
    assert isinstance(markup, ReplyKeyboardMarkup)
    assert markup.keyboard[0][0].request_location is True
    assert markup.keyboard[0][0].text == texts.BTN_SEND_LOCATION
    assert markup.keyboard[1][0].text == texts.BTN_CANCEL_TEXT
    assert env.context.user_data[PENDING_LOCATION] == {"map_parcel": None}


async def test_shared_location_is_rounded_saved_and_not_logged(env, caplog):
    caplog.set_level(logging.DEBUG)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    shared = SimpleNamespace(latitude=21.028511, longitude=105.854222)
    await location_message(update(Msg(env.sent, location=shared)), env.context)
    user = await env.repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    assert env.sent[-1][0] == texts.LOCATION_SAVED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)
    assert PENDING_LOCATION not in env.context.user_data
    # Only the bot's own records: aiosqlite's DEBUG lines echo SQL parameters.
    ours = " | ".join(
        record.getMessage() for record in caplog.records if record.name.startswith("vn_parcel_bot")
    )
    assert "home location saved user=1" in ours
    assert "21.0" not in ours
    assert "105.8" not in ours


async def test_status_and_off(env):
    await env.repo.set_home(1, 21.03, 105.85)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_STATUS
    env.context.args = ["off"]
    await location_cmd(update(Msg(env.sent, "/location off")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_CLEARED
    assert (await env.repo.get_user(1)).home_lat is None
    await location_cmd(update(Msg(env.sent, "/location off")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_NONE


async def test_cancel_text_button_and_cancel_command_remove_the_keyboard(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    await text_message(update(Msg(env.sent, texts.BTN_CANCEL_TEXT)), env.context)
    assert env.sent[-1][0] == texts.CANCELLED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)
    assert PENDING_LOCATION not in env.context.user_data
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    await cancel_cmd(update(Msg(env.sent, "/cancel")), env.context)
    assert env.sent[-1][0] == texts.CANCELLED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)


async def test_pasted_coordinates_are_saved_while_waiting_for_a_location(env, caplog):
    caplog.set_level(logging.DEBUG)
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    await text_message(update(Msg(env.sent, "21.028511, 105.854222")), env.context)
    user = await env.repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    assert env.sent[-1][0] == texts.LOCATION_SAVED
    assert isinstance(env.sent[-1][1], ReplyKeyboardRemove)
    assert PENDING_LOCATION not in env.context.user_data
    ours = " | ".join(
        record.getMessage() for record in caplog.records if record.name.startswith("vn_parcel_bot")
    )
    assert "home location saved user=1" in ours
    assert "21.0" not in ours
    assert "105.8" not in ours


async def test_google_maps_link_is_accepted(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    link = "https://www.google.com/maps/@21.0287,105.8523,17z"
    await text_message(update(Msg(env.sent, link)), env.context)
    user = await env.repo.get_user(1)
    assert (user.home_lat, user.home_lon) == (21.03, 105.85)
    assert env.sent[-1][0] == texts.LOCATION_SAVED


async def test_button_text_or_short_link_explains_how_to_paste_coordinates(env):
    await location_cmd(update(Msg(env.sent, "/location")), env.context)
    await text_message(update(Msg(env.sent, texts.BTN_SEND_LOCATION)), env.context)
    assert env.sent[-1][0] == texts.LOCATION_TYPE_HINT
    assert PENDING_LOCATION in env.context.user_data
    await text_message(update(Msg(env.sent, "https://maps.app.goo.gl/AbCdEf123")), env.context)
    assert env.sent[-1][0] == texts.LOCATION_TYPE_HINT
    assert PENDING_LOCATION in env.context.user_data
    assert (await env.repo.get_user(1)).home_lat is None


async def test_coordinates_without_a_location_prompt_are_not_saved(env):
    await text_message(update(Msg(env.sent, "21.03, 105.85")), env.context)
    assert (await env.repo.get_user(1)).home_lat is None
    assert env.sent[-1][0] != texts.LOCATION_SAVED


def test_location_prompt_explains_the_desktop_way():
    assert "21.03, 105.85" in texts.LOCATION_ASK
    assert "Google Maps" in texts.LOCATION_ASK
