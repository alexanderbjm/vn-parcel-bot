"""Chinese carrier updates in Vietnamese.

Cross-border parcels (STO, YT, China Post and the like, read through 17TRACK) describe their
journey in Chinese and pad it with courier names, phone numbers and promotional notes. This
turns a line into short Vietnamese, drops the padding, and removes any Chinese that is left
over, so a status never reaches a reader untranslated.
"""

import re

_CHINESE = re.compile(r"[㐀-鿿]")
# Bracketed notes that are advertising or support details, not status.
_PROMO_WORDS = ("投诉", "客服", "物流问题", "请致电", "关注", "公众号", "专属渠道", "平台")
_PROMO_BLOCK = re.compile(r"[【\[]([^】\]]*)[】\]]")
_PARENTHESES = re.compile(r"[（(][^）)]*[）)]")
_LONG_DIGITS = re.compile(r"\d{5,}")
_SPACES = re.compile(r"\s+")
_LEFTOVER_PUNCTUATION = re.compile(r"\s*[，、。；：,;:]\s*")
_EDGE_PUNCTUATION = re.compile(r"^[\s,;:.\-–—/]+|[\s,;:\-–—/]+$")
_FULL_WIDTH = "！？。，、：；（）「」［］"

# Longest first: "快件已到达" must win over "到达".
PHRASES: tuple[tuple[str, str], ...] = (
    ("快件已到达", "đã đến"),
    ("快件已发往", "đã gửi đi"),
    ("快件已签收", "đã ký nhận"),
    ("正在为您派送", "đang giao hàng"),
    ("已由", "được"),
    ("您的快件", "Kiện hàng của bạn"),
    ("已发往", "đã gửi đi"),
    ("已到达", "đã đến"),
    ("已签收", "đã ký nhận"),
    ("已揽收", "đã lấy hàng"),
    ("已收件", "đã lấy hàng"),
    ("已代收", "đã nhận"),
    ("代收", "đã nhận"),
    ("揽收", "đã lấy hàng"),
    ("派送", "đang giao hàng"),
    ("转运中心", "trung tâm trung chuyển"),
    ("集散中心", "trung tâm phân loại"),
    ("分拨中心", "trung tâm phân loại"),
    ("快递员", "nhân viên giao hàng"),
    ("配送员", "nhân viên giao hàng"),
    ("仓库", "kho"),
    ("网点", "bưu cục"),
    ("公司", "bưu cục"),
    ("预计", "dự kiến"),
    ("到达", "đến"),
    ("发往", "gửi đi"),
    ("出库", "rời kho"),
    ("入库", "vào kho"),
    ("清关", "thông quan"),
    ("海关", "hải quan"),
    ("航班", "chuyến bay"),
    ("运输中", "đang vận chuyển"),
    ("运输", "vận chuyển"),
    ("快件", "kiện hàng"),
    ("包裹", "kiện hàng"),
    ("订单", "đơn hàng"),
    ("两地距离", "khoảng cách"),
    ("上午", "buổi sáng"),
    ("下午", "buổi chiều"),
)

# Places seen on cross-border routes into Vietnam.
PLACES: tuple[tuple[str, str], ...] = (
    ("上海市", "Thượng Hải"),
    ("深圳市", "Thâm Quyến"),
    ("东莞市", "Đông Quản"),
    ("广州市", "Quảng Châu"),
    ("北京市", "Bắc Kinh"),
    ("南宁市", "Nam Ninh"),
    ("昆明市", "Côn Minh"),
    ("义乌市", "Nghĩa Ô"),
    ("杭州市", "Hàng Châu"),
    ("泉州市", "Tuyền Châu"),
    ("广东", "Quảng Đông"),
    ("广西", "Quảng Tây"),
    ("福建", "Phúc Kiến"),
    ("浙江", "Chiết Giang"),
    ("云南", "Vân Nam"),
    ("上海", "Thượng Hải"),
    ("深圳", "Thâm Quyến"),
    ("东莞", "Đông Quản"),
    ("广州", "Quảng Châu"),
    ("北京", "Bắc Kinh"),
    ("南宁", "Nam Ninh"),
    ("昆明", "Côn Minh"),
    ("义乌", "Nghĩa Ô"),
    ("杭州", "Hàng Châu"),
    ("泉州", "Tuyền Châu"),
    ("凭祥", "Bằng Tường"),
    ("友谊关", "Hữu Nghị Quan"),
    ("香港", "Hồng Kông"),
    ("河内", "Hà Nội"),
    ("越南", "Việt Nam"),
    ("中国", "Trung Quốc"),
)


def has_chinese(text: str) -> bool:
    return bool(_CHINESE.search(text))


def _drop_padding(text: str) -> str:
    """Remove advertising blocks, courier details in brackets and long digit runs."""

    def bracket(match: re.Match[str]) -> str:
        inner = match.group(1)
        if any(word in inner for word in _PROMO_WORDS):
            return " "
        return f" {inner} "

    text = _PROMO_BLOCK.sub(bracket, text)
    text = _PARENTHESES.sub(" ", text)
    return _LONG_DIGITS.sub(" ", text)


def _collapse_repeats(text: str) -> str:
    """Drop a phrase that repeats itself straight away ("Đông Quản Đông Quản")."""
    kept: list[str] = []
    for word in text.split(" "):
        kept.append(word)
        for size in (3, 2, 1):
            if len(kept) >= 2 * size:
                tail = [w.casefold() for w in kept[-size:]]
                before = [w.casefold() for w in kept[-2 * size : -size]]
                if tail == before:
                    del kept[-size:]
                    break
    return " ".join(kept)


def _tidy(text: str) -> str:
    for mark in _FULL_WIDTH:
        text = text.replace(mark, " ")
    text = _LEFTOVER_PUNCTUATION.sub(" ", text)
    text = _SPACES.sub(" ", text)
    return _collapse_repeats(_EDGE_PUNCTUATION.sub("", text).strip())


def translate_cn(text: str) -> str:
    """A Chinese status line in Vietnamese; text without Chinese is returned unchanged."""
    if not text or not has_chinese(text):
        return text
    working = _drop_padding(text)
    for chinese, vietnamese in PLACES:
        working = working.replace(chinese, f" {vietnamese} ")
    for chinese, vietnamese in PHRASES:
        working = working.replace(chinese, f" {vietnamese} ")
    # Anything still in Chinese is a name or a detail with no translation: drop it.
    working = _CHINESE.sub(" ", working)
    working = working.replace("“", " ").replace("”", " ").replace("‘", " ").replace("’", " ")
    return _tidy(working)
