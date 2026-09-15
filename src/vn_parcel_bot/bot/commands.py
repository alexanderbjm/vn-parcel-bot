BOT_COMMANDS: list[tuple[str, str]] = [
    ("start", "Bắt đầu"),
    ("help", "Hướng dẫn"),
    ("track", "Theo dõi đơn: /track <mã> [4 số cuối SĐT]"),
    ("list", "Danh sách đơn"),
    ("status", "Hành trình đơn"),
    ("label", "Đặt tên cho đơn"),
    ("remove", "Ngừng theo dõi"),
    ("phone", "4 số cuối SĐT cho đơn J&T, GHN"),
    ("check", "Kiểm tra ngay và nhận diện lại hãng"),
    ("cancel", "Hủy thao tác"),
]

# Shown only in the admin's command menu, after BOT_COMMANDS.
ADMIN_COMMANDS: list[tuple[str, str]] = [
    ("hozk", "Lệnh quản lý"),
    ("users", "Người dùng"),
    ("allow", "Cấp quyền: /allow <id> [tên]"),
    ("revoke", "Thu hồi quyền: /revoke <id>"),
    ("health", "Tình trạng bot"),
    ("sticker", "Sticker cho hãng: /sticker <hãng> [off]"),
]
