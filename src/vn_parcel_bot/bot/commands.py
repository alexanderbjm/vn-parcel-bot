# Everything else a parcel needs is a button on its card or under /list, so the menu keeps
# only what you cannot reach by tapping. /track /status /label /remove /phone /check /cancel
# are still registered and still work when typed; /help lists them.
BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "Bắt đầu"),
    ("help", "Hướng dẫn"),
    ("list", "Danh sách đơn"),
    ("location", "Vị trí của bạn cho bản đồ"),
]

# Shown only in the admin's command menu, after BOT_COMMANDS.
ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("hozk", "Lệnh quản lý"),
    ("users", "Người dùng"),
    ("allow", "Cấp quyền: /allow <id> [tên]"),
    ("revoke", "Thu hồi quyền: /revoke <id>"),
    ("health", "Tình trạng bot"),
    ("sticker", "Sticker cho trạng thái: /sticker <trạng thái> [off]"),
]
