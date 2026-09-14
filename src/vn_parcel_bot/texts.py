TIME_FORMAT = "%d/%m %H:%M"

CARRIER_UNRESOLVED = "Đang xác định hãng"
CARRIER_SEPARATOR = " / "

STATE_EMOJI = {
    "pending": "⏳",
    "in_transit": "🚚",
    "delivered": "✅",
    "returned": "↩️",
    "expired": "⌛",
    "stale": "⚠️",
}
STATE_TEXT = {
    "pending": "Chưa có thông tin vận chuyển",
    "in_transit": "Đang vận chuyển",
    "delivered": "Đã giao",
    "returned": "Hoàn hàng",
    "expired": "Đã ngừng theo dõi (không có dữ liệu)",
    "stale": "Đã ngừng theo dõi (quá lâu không cập nhật)",
}

WELCOME = (
    "Xin chào {name}! 👋\n"
    "Mình sẽ nhắn cho bạn mỗi khi đơn hàng có cập nhật mới.\n"
    "Gửi mã vận đơn để bắt đầu, mình sẽ tự nhận diện hãng vận chuyển."
)
HELP = (
    "<b>📦 Hướng dẫn</b>\n"
    "• Gửi mã vận đơn để theo dõi, mình tự nhận diện hãng\n"
    "• Gửi ảnh chụp đơn hàng – mình tự đọc mã vận đơn và tên sản phẩm\n"
    "• Tự động theo dõi: {tracked}\n"
    "• Gửi link tra cứu: {link_only}\n"
    "• /track &lt;mã&gt; [4 số cuối SĐT] – theo dõi đơn\n"
    "• /list – các đơn đang theo dõi\n"
    "• /status &lt;mã hoặc số thứ tự&gt; – xem hành trình\n"
    "• /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; – đặt tên cho đơn\n"
    "• /remove &lt;mã hoặc số thứ tự&gt; – ngừng theo dõi\n"
    "• /phone &lt;4 số&gt; – lưu 4 số cuối SĐT cho đơn J&amp;T, GHN (/phone clear để xóa)\n"
    "• /check – kiểm tra ngay\n"
    "• /cancel – hủy thao tác đang chờ"
)
NOT_ALLOWED = (
    "🔒 Bạn chưa có quyền dùng bot này.\nHãy gửi ID sau cho người quản lý: <code>{user_id}</code>"
)
ADMIN_ONLY = "🔒 Lệnh này chỉ dành cho người quản lý."
UNKNOWN_COMMAND = "Mình không hiểu lệnh này. Gõ /help để xem hướng dẫn."
UNKNOWN_CODE = "🤔 Mình không nhận ra mã vận đơn nào.\nGõ /help để xem các hãng được hỗ trợ."
ERROR_GENERIC = "😵 Có lỗi xảy ra, bạn thử lại sau nhé."

USAGE_TRACK = "Cách dùng: /track &lt;mã&gt; [4 số cuối SĐT]"
SELLER_FLEET = (
    "🛵 <code>{code}</code> có vẻ là mã đơn <b>người bán tự giao</b> (TikTok Shop…), "
    "không có trang tra cứu công khai.\n"
    "Hãy xem hành trình trong app nơi bạn đặt hàng. Hoặc thử tra cứu tại:\n{links}"
)
UNKNOWN_CARRIER = (
    "🔍 Mình chưa nhận ra hãng vận chuyển của mã <code>{code}</code>.\n"
    "Bạn có thể tra cứu tại:\n{links}"
)
USAGE_REF = "Cách dùng: /{command} &lt;mã hoặc số thứ tự trong /list&gt;"
USAGE_LABEL = "Cách dùng: /label &lt;mã hoặc số thứ tự&gt; &lt;tên&gt; (bỏ trống tên để xóa)"

ASK_PHONE = (
    "📱 Mã <code>{code}</code> ({carriers}) cần 4 số cuối SĐT người nhận.\n"
    "Gửi 4 số đó, hoặc /cancel để hủy."
)
INVALID_PHONE = "Vui lòng nhập đúng 4 chữ số."
NEEDS_PHONE_MULTI = (
    "📱 Các đơn sau cần 4 số cuối SĐT người nhận. "
    "Hãy thêm từng đơn bằng /track &lt;mã&gt; &lt;4 số&gt;:\n{codes}"
)

ADDED_FOUND = "✅ Đã theo dõi <b>{title}</b> · {carrier}\nTrạng thái hiện tại: {status}\n🕒 {time}"
ADDED_DELIVERED = "✅ Đã thêm <b>{title}</b> · {carrier} — đơn này đã giao thành công.\n🕒 {time}"
ADDED_PENDING = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa có thông tin vận chuyển, mình sẽ kiểm tra lại định kỳ."
)
ADDED_PENDING_AUTO = (
    "✅ Đã thêm <b>{title}</b>\n"
    "Hiện chưa có thông tin vận chuyển. Mình sẽ tự kiểm tra mã này ở {carriers}."
)
ADDED_PENDING_PHONE_HINT = "\nNếu vài giờ nữa vẫn chưa có dữ liệu, hãy kiểm tra lại 4 số cuối SĐT."
ADDED_ERROR = (
    "✅ Đã thêm <b>{title}</b> · {carrier}\n"
    "Hiện chưa kết nối được với {carrier}, mình sẽ thử lại sau."
)
DUPLICATE = "Bạn đã theo dõi đơn <code>{code}</code> rồi."
LIMIT_REACHED = "Bạn đang theo dõi tối đa {max} đơn. Hãy /remove bớt đơn cũ nhé."

LINK_ONLY = (
    "🔗 Mã <code>{code}</code> có thể là đơn {carriers}.\n"
    "Mình chưa tự theo dõi được hãng này, bạn xem hành trình tại:\n{links}"
)
LINK_EXTRA = "\n\nNếu đây là đơn {carriers}, xem tại:\n{links}"
LINK_ITEM = '• <a href="{url}">{name}</a>'
LINK_17TRACK_NAME = "17TRACK"

LIST_HEADER = "<b>📋 Đơn của bạn</b>"
LIST_EMPTY = "Bạn chưa theo dõi đơn nào. Gửi mã vận đơn để bắt đầu."
LIST_ITEM = "{index}. {emoji} <b>{title}</b> · {carrier}\n    {status}{time_suffix}"
LIST_TIME_SUFFIX = " · 🕒 {time}"

HISTORY_HEADER = "<b>📦 {title}</b> · {carrier} · <code>{code}</code>"
HISTORY_EMPTY = "Chưa có thông tin vận chuyển."
PARCEL_NOT_FOUND = "Không tìm thấy đơn <code>{ref}</code> trong danh sách của bạn."

REMOVED = "🗑 Đã ngừng theo dõi <b>{title}</b>."
LABEL_SET = "🏷 Đã đặt tên: <b>{label}</b>"
LABEL_CLEARED = "🏷 Đã xóa tên của đơn <code>{code}</code>."

PHONE_SET = "📱 Đã lưu 4 số cuối mặc định: <code>{last4}</code>"
PHONE_SHOW = "📱 4 số cuối mặc định: <code>{last4}</code>"
PHONE_NONE = "Bạn chưa lưu 4 số cuối nào. Dùng /phone &lt;4 số&gt; để lưu."
PHONE_CLEARED = "📱 Đã xóa 4 số cuối mặc định."

CANCELLED = "Đã hủy."
NOTHING_TO_CANCEL = "Không có thao tác nào đang chờ."

CHECK_TOO_SOON = "⏱ Bạn vừa kiểm tra xong. Thử lại sau {minutes} phút nhé."
CHECK_STARTED = "🔄 Đang kiểm tra các đơn của bạn…"
CHECK_DONE = "✔️ Đã kiểm tra {checked} đơn, có {new_events} cập nhật mới."

UPDATE_HEADER = "📦 <b>{title}</b> · {carrier}"
UPDATE_RESOLVED = "🔎 Đã xác định hãng vận chuyển: <b>{carrier}</b>"
UPDATE_LINE = "• {time} — {description}"
UPDATE_LOCATION = " ({location})"
UPDATE_MORE = "… và {count} cập nhật trước đó"
UPDATE_DELIVERED = "✅ <b>Đã giao thành công!</b>"
UPDATE_RETURNED = "↩️ <b>Đơn đang được hoàn về người gửi.</b>"

EXPIRED = (
    "⌛ Sau 7 ngày vẫn chưa có dữ liệu cho <code>{code}</code>, mình đã ngừng theo dõi.\n"
    "Hãy kiểm tra lại mã vận đơn (và 4 số cuối SĐT nếu là đơn J&amp;T hoặc GHN)."
)
STALE = "⚠️ Đơn <b>{title}</b> không có cập nhật nào trong 30 ngày, mình đã ngừng theo dõi."

USAGE_ALLOW = "Cách dùng: /allow &lt;telegram_id&gt; [tên]"
USAGE_REVOKE = "Cách dùng: /revoke &lt;telegram_id&gt;"
ALLOWED = "✅ Đã cấp quyền cho <code>{user_id}</code>{name_suffix}."
ALLOWED_NOTICE = "🎉 Bạn đã được cấp quyền dùng bot! Gõ /help để xem hướng dẫn."
REVOKED = "🚫 Đã thu hồi quyền của <code>{user_id}</code>."
CANNOT_REVOKE_ADMIN = "Không thể thu hồi quyền của người quản lý."
USERS_HEADER = "<b>👥 Người dùng</b>"
USERS_ITEM = "• <code>{user_id}</code> {name} — {role} · {active} đơn đang theo dõi"
ROLE_ADMIN = "quản lý"
ROLE_MEMBER = "thành viên"
ROLE_BLOCKED = "đã khóa"

HEALTH = (
    "<b>🩺 Tình trạng</b>\n"
    "Lần kiểm tra gần nhất: {last_poll}\n"
    "Đơn đang theo dõi: {active}\n"
    "Người dùng: {users}\n"
    "Chu kỳ gần nhất: {fetches} lượt tra cứu, {new_events} cập nhật mới, lỗi: {failures}"
)
HEALTH_NEVER = "chưa chạy"

ALERT_CARRIER = (
    "⚠️ <b>{carrier}</b>: {count} lỗi liên tiếp khi tra cứu.\n"
    "Có thể trang tra cứu đã thay đổi hoặc đang chặn. Lỗi gần nhất: <code>{detail}</code>"
)
ALERT_ERROR = "⚠️ Bot gặp lỗi: <code>{detail}</code>"

VISION_NOT_CONFIGURED = (
    "📷 Tính năng đọc ảnh chưa sẵn sàng trên máy chạy bot. Bạn gửi mã vận đơn trực tiếp nhé."
)
VISION_NO_DATA = (
    "🤔 Mình không tìm thấy mã vận đơn hay mã đơn hàng nào trong ảnh này.\n"
    "Bạn thử chụp màn hình <b>Thông tin vận chuyển</b> rõ hơn hoặc gửi mã trực tiếp nhé."
)
VISION_DETECTED_HEADER = "📷 <b>Nhận diện từ hình ảnh:</b>"
VISION_PRODUCT = "• Sản phẩm: <b>{name}</b>"
VISION_DETECTED_ITEM = "• Mã vận đơn: <code>{code}</code>{carrier_suffix}"
VISION_DETECTED_PHONE = "• SĐT người nhận: <code>***{phone}</code>"
VISION_ORDER_ONLY = (
    "🧾 Tìm thấy mã đơn hàng: <code>{order_id}</code>\n"
    "Đây là <b>mã đơn hàng</b>, không phải mã vận đơn.\n"
    "Trong app (Shopee, Lazada, TikTok Shop…) mở đơn → <b>Thông tin vận chuyển</b> "
    "rồi gửi ảnh chụp hoặc mã vận đơn cho mình nhé! Hoặc thử tra cứu tại:\n{links}"
)
VISION_ERROR = (
    "⚠️ Không phân tích được hình ảnh lúc này. Bạn thử lại sau hoặc gửi mã vận đơn trực tiếp nhé."
)
VISION_UNSUPPORTED_IMAGE = (
    "📷 Ảnh này quá lớn hoặc không đúng định dạng. Bạn gửi lại dưới dạng ảnh (không phải tệp) nhé."
)

DIGEST_HEADER = "🗓 <b>Tóm tắt đơn hàng</b> · {time}"
DIGEST_NEW_MARK = " 🆕"
DIGEST_FOOTER = "Đang theo dõi {active} đơn"
DIGEST_FOOTER_FINISHED = " · {finished} đơn vừa kết thúc"
