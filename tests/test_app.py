from dataclasses import replace

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler

from vn_parcel_bot.bot.app import build_application
from vn_parcel_bot.bot.commands import ADMIN_COMMANDS, BOT_COMMANDS

ALL_COMMANDS = {
    "start",
    "sticker",
    "help",
    "track",
    "list",
    "status",
    "label",
    "remove",
    "phone",
    "location",
    "check",
    "cancel",
    "allow",
    "revoke",
    "users",
    "health",
    "hozk",
}

# Still registered, deliberately kept off the menu: every one of them is a button now.
HIDDEN_COMMANDS = {
    "track",
    "status",
    "label",
    "remove",
    "phone",
    "check",
    "cancel",
}


def test_build_application_registers_handlers(settings):
    app = build_application(settings)
    gate_group = app.handlers[-1]
    assert len(gate_group) == 1
    assert isinstance(gate_group[0], TypeHandler)
    group = app.handlers[0]
    commands = set().union(*(h.commands for h in group if isinstance(h, CommandHandler)))
    assert commands == ALL_COMMANDS
    assert isinstance(group[-1], CallbackQueryHandler)
    assert isinstance(group[-2], MessageHandler)
    assert len(app.error_handlers) == 1
    assert app.bot_data["settings"] is settings


def test_build_application_with_proxy(settings):
    app = build_application(replace(settings, telegram_proxy_url="socks5h://127.0.0.1:1080"))
    assert app.bot_data["settings"].telegram_proxy_url == "socks5h://127.0.0.1:1080"


def test_bot_commands_match_spec():
    assert [name for name, _ in BOT_COMMANDS] == [
        "start",
        "help",
        "list",
        "location",
    ]
    assert [name for name, _ in ADMIN_COMMANDS] == [
        "hozk",
        "users",
        "allow",
        "revoke",
        "health",
        "sticker",
    ]
    every = BOT_COMMANDS + ADMIN_COMMANDS
    assert all(0 < len(description) <= 256 for _, description in every)
    listed = {name for name, _ in every}
    assert listed <= ALL_COMMANDS, "every menu entry is a real handler"
    assert listed == ALL_COMMANDS - HIDDEN_COMMANDS, "the menu hides exactly these"


def test_hidden_commands_still_work_when_typed(settings):
    """Hidden means unadvertised, not removed: old habits and saved messages keep working."""
    app = build_application(settings)
    group = app.handlers[0]
    registered = set().union(*(h.commands for h in group if isinstance(h, CommandHandler)))
    assert registered >= HIDDEN_COMMANDS


def test_location_messages_have_a_handler(settings):
    app = build_application(settings)
    handlers = [handler for group in app.handlers.values() for handler in group]
    assert any(
        isinstance(handler, MessageHandler) and "LOCATION" in str(handler.filters).upper()
        for handler in handlers
    )
