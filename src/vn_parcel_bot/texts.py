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
    "• /label &lt;mã hoặc số thứ tự&gt; [tên] – đặt tên cho đơn "
    "(hoặc trả lời tin nhắn của đơn bằng /label)\n"
    "• /remove &lt;số thứ tự hoặc mã&gt; … – ngừng theo dõi (nhiều đơn: /remove 1 2 3)\n"
    "• /phone &lt;4 số&gt; – lưu 4 số cuối SĐT cho đơn J&amp;T, GHN (/phone clear để xóa)\n"
    "• /location – lưu khu vực của bạn (làm tròn ~1 km) để xem khoảng cách; /location off để xóa\n"
    "• /check – kiểm tra ngay tất cả đơn và nhận diện lại hãng\n"
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
    "🛵 {code} có vẻ là mã đơn <b>người bán tự giao</b> (TikTok Shop…), "
    "không có trang tra cứu công khai.\n"
    "Hãy xem hành trình trong app nơi bạn đặt hàng. Hoặc thử tra cứu tại:\n{links}"
)
UNKNOWN_CARRIER = (
    "🔍 Mình chưa nhận ra hãng vận chuyển của mã {code}.\nBạn có thể tra cứu tại:\n{links}"
)
USAGE_REF = "Cách dùng: /{command} &lt;mã hoặc số thứ tự trong /list&gt;"
USAGE_LABEL = (
    "Cách dùng: /label &lt;mã hoặc số thứ tự&gt; [tên], "
    "hoặc trả lời tin nhắn của đơn bằng /label [tên]"
)

ASK_PHONE = "📱 Mã {code} ({carriers}) cần 4 số cuối SĐT người nhận.\nGửi 4 số đó."
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
DUPLICATE = "Bạn đã theo dõi đơn {code} rồi."
LIMIT_REACHED = "Bạn đang theo dõi tối đa {max} đơn. Hãy /remove bớt đơn cũ nhé."

LINK_ONLY = (
    "🔗 Mã {code} có thể là đơn {carriers}.\n"
    "Mình chưa tự theo dõi được hãng này, bạn xem hành trình tại:\n{links}"
)
LINK_EXTRA = "\n\nNếu đây là đơn {carriers}, xem tại:\n{links}"
LINK_ITEM = '• <a href="{url}">{name}</a>'
LINK_17TRACK_NAME = "17TRACK"

LIST_HEADER = "<b>📋 Đơn của bạn</b>"
LIST_EMPTY = "Bạn chưa theo dõi đơn nào. Gửi mã vận đơn để bắt đầu."
LIST_ITEM = "{index}. {emoji} <b>{title}</b> · {carrier}\n    {body}{time_suffix}{bar}"
LIST_TIME_SUFFIX = " · 🕒 {time}"
LIST_PLACE_LINE = "📦 Kiện hàng đã tới {place} · cách bạn {distance}"
LIST_PLACE_ONLY = "📦 Kiện hàng đã tới {place}"
LIST_SECTION_ACTIVE = "🚚 <b>Đang vận chuyển</b>"
LIST_SECTION_DONE = "✅ <b>Đã xong</b>"
PROGRESS_SUFFIX = " · {percent}%"
PROGRESS_BAR_LINE = "\n    {bar}"

HISTORY_HEADER = "<b>📦 {title}</b> · {carrier} · {code}"
HISTORY_EMPTY = "Chưa có thông tin vận chuyển."
PARCEL_NOT_FOUND = "Không tìm thấy đơn {ref} trong danh sách của bạn."

REMOVED = "🗑 Đã ngừng theo dõi <b>{title}</b>."
LABEL_SET = "🏷 Đã đặt tên: <b>{label}</b> · {code}"
LABEL_CLEARED = "🏷 Đã xóa tên của đơn {code}."
LABEL_ASK = "🏷 Gửi tên cho đơn {code}."
LABEL_PICK = "Tin nhắn này có nhiều đơn. Chọn đơn muốn đặt tên:"
LABEL_REPLY_NOT_FOUND = "Không tìm thấy đơn nào của bạn trong tin nhắn đó."
REMOVE_CONFIRM = "🗑 Ngừng theo dõi <b>{title}</b>?"
REMOVE_CONFIRM_MANY = "🗑 Ngừng theo dõi {count} đơn?\n{items}"
REMOVE_ITEM = "• <b>{title}</b>"
REMOVE_MISSING = "\nKhông tìm thấy: {refs}"
REMOVED_MANY = "🗑 Đã ngừng theo dõi {count} đơn:\n{items}"
SELECT_HEADER = "🗑 <b>Chọn các đơn muốn xóa</b> · đã chọn {count}"
SELECT_NONE = "Bạn chưa chọn đơn nào."
BUTTON_EXPIRED = "Nút này không còn dùng được."

PHONE_SET = "📱 Đã lưu 4 số cuối mặc định: <code>{last4}</code>"
PHONE_SHOW = "📱 4 số cuối mặc định: <code>{last4}</code>"
PHONE_NONE = "Bạn chưa lưu 4 số cuối nào. Dùng /phone &lt;4 số&gt; để lưu."
PHONE_CLEARED = "📱 Đã xóa 4 số cuối mặc định."

CANCELLED = "Đã hủy."
LOCATION_ASK = (
    "📍 Trên điện thoại, bấm nút <b>Gửi vị trí</b> bên dưới. "
    "Mình chỉ lưu khu vực làm tròn ~1 km để tính khoảng cách tới đơn hàng.\n"
    "💻 Trên máy tính, dán tọa độ (ví dụ <code>21.03, 105.85</code>) hoặc link Google Maps.\n"
    "✍️ Hoặc gõ khu vực của bạn, ví dụ <code>Cầu Giấy, Hà Nội</code>."
)
LOCATION_STATUS = (
    "📍 Đã lưu khu vực của bạn (~1 km). Bấm <b>Gửi vị trí</b> để cập nhật, "
    "hoặc /location off để xóa."
)
LOCATION_SAVED = "📍 Đã lưu khu vực của bạn (làm tròn ~1 km)."
LOCATION_CLEARED = "📍 Đã xóa khu vực của bạn."
LOCATION_NONE = "Bạn chưa lưu khu vực nào. Gửi /location để lưu."
LOCATION_TYPE_HINT = (
    "💻 Ứng dụng Telegram này không gửi được vị trí. Hãy dán tọa độ khu vực của bạn, "
    "ví dụ <code>21.03, 105.85</code> (trên Google Maps: bấm chuột phải vào bản đồ rồi bấm "
    "dòng tọa độ để sao chép), hoặc link Google Maps có tọa độ. Link rút gọn "
    "<code>maps.app.goo.gl</code> không dùng được. Bạn cũng có thể gõ khu vực, "
    "ví dụ <code>Cầu Giấy, Hà Nội</code>. Bấm ↩ Hủy để thôi."
)
LOCATION_AREA_SAVED = (
    "📍 Đã lưu khu vực: <b>{area}</b> (làm tròn ~1 km). "
    "Nếu sai chỗ, gửi /location rồi gõ rõ hơn (phường, quận, tỉnh)."
)
LOCATION_AREA_NOT_FOUND = (
    "Không tìm thấy khu vực <b>{area}</b>. Thử ghi rõ hơn, ví dụ "
    "<code>Dịch Vọng, Cầu Giấy, Hà Nội</code>, hoặc dán tọa độ. Bấm ↩ Hủy để thôi."
)
LOCATION_LOOKUP_FAILED = "Không tra được khu vực lúc này. Bạn thử lại sau hoặc dán tọa độ nhé."
BTN_SEND_LOCATION = "📍 Gửi vị trí"
BTN_CANCEL_TEXT = "↩ Hủy"
BTN_MAP = "🗺 Bản đồ"
MAP_NO_PLACE = "Đơn này chưa có vị trí kho để vẽ bản đồ."
MAP_TOO_SOON = "Bạn vừa xem bản đồ đơn này, thử lại sau ít phút nhé."
MAP_FAILED = "Không vẽ được bản đồ lúc này, bạn thử lại sau nhé."
MAP_OFF = "Tính năng bản đồ đang tắt."
NOTHING_TO_CANCEL = "Không có thao tác nào đang chờ."

CHECK_TOO_SOON = "⏱ Bạn vừa kiểm tra xong. Thử lại sau {minutes} phút nhé."
CHECK_STARTED = "🔄 Đang làm mới các đơn của bạn bằng script mới nhất…"
CHECK_DONE = "✔️ Đã kiểm tra {checked} đơn · {new_events} cập nhật mới"
CHECK_REDETECTED = " · {count} đơn nhận diện lại hãng"
CHECK_REBUILT = " · làm mới dữ liệu {count} đơn"
CHECK_RELOADED = " · nạp {count} script hãng mới"

DISTANCE_UNDER_1KM = "dưới 1 km"
PLACE_LINE = "📍 {place} · cách bạn {distance}"
PLACE_ONLY_LINE = "📍 {place}"
MAP_CAPTION = "🗺 <b>{title}</b>\n📍 {place} → khu vực của bạn · {distance}"

UPDATE_HEADER = "📦 <b>{title}</b> · {carrier}"
UPDATE_RESOLVED = "🔎 Đã xác định hãng vận chuyển: <b>{carrier}</b>"
UPDATE_LINE = "• {time} — {description}"
UPDATE_LOCATION = " ({location})"
UPDATE_MORE = "… và {count} cập nhật trước đó"
UPDATE_DELIVERED = "✅ <b>Đã giao thành công!</b>"
UPDATE_RETURNED = "↩️ <b>Đơn đang được hoàn về người gửi.</b>"

EXPIRED = (
    "⌛ Sau 7 ngày vẫn chưa có dữ liệu cho {code}, mình đã ngừng theo dõi.\n"
    "Hãy kiểm tra lại mã vận đơn (và 4 số cuối SĐT nếu là đơn J&amp;T hoặc GHN)."
)
STALE = "⚠️ Đơn <b>{title}</b> không có cập nhật nào trong 30 ngày, mình đã ngừng theo dõi."

ADMIN_HELP = (
    "<b>🛠 Lệnh quản lý</b>\n"
    "• /users – danh sách người dùng và số đơn\n"
    "• /allow &lt;id&gt; [tên] – cấp quyền (người đó nhận thông báo)\n"
    "• /revoke &lt;id&gt; – thu hồi quyền\n"
    "• /health – tình trạng bot và lần kiểm tra gần nhất\n"
    "• /sticker &lt;hãng&gt; [off] – trả lời một sticker để gắn cho hãng; /sticker để xem\n"
    "• /check – kiểm tra ngay và nhận diện lại hãng các đơn của bạn"
)
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
HEALTH_REVISION = "Bản cập nhật: {revision}"

ALERT_CARRIER = (
    "⚠️ <b>{carrier}</b>: {count} lỗi liên tiếp khi tra cứu.\n"
    "Có thể trang tra cứu đã thay đổi hoặc đang chặn. Lỗi gần nhất: <code>{detail}</code>"
)
ALERT_ERROR = "⚠️ Bot gặp lỗi: <code>{detail}</code>"
MODULE_REJECTED = "⚠️ Module <code>{code}</code> lỗi, vẫn dùng bản cũ: {error}"
BOT_UPDATED = "🔄 <b>Cập nhật bot</b>\nPhiên bản: <code>{revision}</code>"

VISION_NOT_CONFIGURED = (
    "📷 Tính năng đọc ảnh chưa sẵn sàng trên máy chạy bot. Bạn gửi mã vận đơn trực tiếp nhé."
)
VISION_NO_DATA = (
    "🤔 Mình không tìm thấy mã vận đơn hay mã đơn hàng nào trong ảnh này.\n"
    "Bạn thử chụp màn hình <b>Thông tin vận chuyển</b> rõ hơn hoặc gửi mã trực tiếp nhé."
)
VISION_DETECTED_HEADER = "📷 <b>Nhận diện từ hình ảnh:</b>"
VISION_PRODUCT = "• Sản phẩm: <b>{name}</b>"
VISION_DETECTED_ITEM = "• Mã vận đơn: {code}{carrier_suffix}"
VISION_DETECTED_PHONE = "• SĐT người nhận: <code>***{phone}</code>"
VISION_ORDER_ONLY = (
    "🧾 Tìm thấy mã đơn hàng: {order_id}\n"
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

CARD_HEADER = "{emoji} <b>{title}</b> · {carrier}"
CARD_NOT_FOUND = "Không tìm thấy đơn này."
LIST_PAGE = "Trang {page}/{pages}"
BTN_RENAME = "✏️ Đổi tên"
BTN_HISTORY = "📜 Hành trình"
BTN_CHECK = "🔄 Kiểm tra"
BTN_REMOVE = "🗑 Xóa"
BTN_SHARE = "📤 Chia sẻ"
BTN_LINK = "🔗 Tra cứu {name} ↗"
BTN_BACK = "⬅ Quay lại"
BTN_BACK_LIST = "⬅ Danh sách"
BTN_CONFIRM_REMOVE = "✅ Xóa"
BTN_CANCEL = "↩ Hủy"
BTN_TRACK_SHARED = "✅ Theo dõi"
BTN_SKIP = "↩ Bỏ qua"
BTN_PREV = "⬅️"
BTN_NEXT = "➡️"
BTN_RECHECK = "🔄 Kiểm tra tất cả"
BTN_SORT_NEAR = "📍 Gần bạn nhất"
BTN_SORT_CARRIER = "🚚 Theo hãng"
BTN_SORT_NAME = "🔤 Theo tên"
SORT_LABELS = {
    "n": BTN_SORT_NEAR,
    "c": BTN_SORT_CARRIER,
    "a": BTN_SORT_NAME,
}
BTN_SELECT_REMOVE = "🗑 Xóa nhiều"
BTN_REMOVE_SELECTED = "✅ Xóa đã chọn ({count})"
BTN_CONFIRM_REMOVE_MANY = "✅ Xóa {count} đơn"
BTN_CLEAR_LABEL = "🗑 Xóa tên"
SELECT_MARK = "☑ {number}"
SHARE_LINK = "📤 Gửi link này để người khác theo dõi <b>{title}</b>:\n{link}"
SHARE_OPEN = "📦 Bạn được chia sẻ đơn <b>{title}</b> · {carrier}. Theo dõi đơn này?"
SHARE_NOT_FOUND = "Link chia sẻ này không còn dùng được."
STICKER_SET = "🎨 Đã lưu sticker cho {carrier}."
STICKER_REMOVED = "🎨 Đã xóa sticker của {carrier}."
STICKER_LIST = "🎨 Hãng có sticker: {carriers}"
STICKER_USAGE = (
    "Cách dùng: trả lời một sticker bằng /sticker &lt;hãng&gt;, hoặc /sticker &lt;hãng&gt; off"
)
STICKER_UNKNOWN = "Không có hãng này. Các hãng: {carriers}"
