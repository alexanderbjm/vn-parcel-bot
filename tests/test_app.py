from dataclasses import replace

from telegram.ext import CallbackQueryHandler, CommandHandler, MessageHandler, TypeHandler

from vn_parcel_bot.bot.app import build_application
from vn_parcel_bot.bot.commands import BOT_COMMANDS

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
    "check",
    "cancel",
    "allow",
    "revoke",
    "users",
    "health",
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
        "track",
        "list",
        "status",
        "label",
        "remove",
        "phone",
        "check",
        "cancel",
    ]
    assert all(0 < len(description) <= 256 for _, description in BOT_COMMANDS)
