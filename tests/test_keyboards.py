from tests.test_formatting import make_parcel
from vn_parcel_bot.keyboards import (
    back_keyboard,
    card_keyboard,
    confirm_remove_keyboard,
    list_back_keyboard,
    list_keyboard,
    share_open_keyboard,
)


def cells(markup):
    return [
        [button.callback_data or button.url for button in row] for row in markup.inline_keyboard
    ]


def labels(markup):
    return [[button.text for button in row] for row in markup.inline_keyboard]


def test_card_keyboard_buttons_and_data():
    markup = card_keyboard(make_parcel(id=42))
    assert labels(markup) == [
        ["✏️ Đổi tên", "📜 Hành trình"],
        ["🔄 Kiểm tra", "🗑 Xóa"],
        ["📤 Chia sẻ", "🔗 Tra cứu 17TRACK ↗"],
    ]
    data = cells(markup)
    assert data[0] == ["p:42:ren", "p:42:his"]
    assert data[1] == ["p:42:chk", "p:42:del"]
    assert data[2][0] == "p:42:shr"
    assert data[2][1].startswith("https://t.17track.net/vi#nums=")
    callbacks = [d for row in data for d in row if not d.startswith("https")]
    assert all(len(d.encode()) < 64 for d in callbacks)


def test_card_keyboard_from_list_has_back_row_and_page():
    data = cells(card_keyboard(make_parcel(id=7), page=2))
    assert data[0] == ["p:7:ren:2", "p:7:his:2"]
    assert data[-1] == ["l:2"]


def test_link_only_carrier_uses_its_page():
    parcel = make_parcel(
        id=3, carrier="vnpost", candidates=("vnpost",), tracking_number="EB123456789VN"
    )
    row = card_keyboard(parcel).inline_keyboard[2]
    assert row[1].text == "🔗 Tra cứu VNPost ↗"
    assert row[1].url.startswith("https://vnpost.vn/")


def test_small_keyboards():
    assert cells(back_keyboard(5)) == [["p:5:card"]]
    assert cells(back_keyboard(5, 3)) == [["p:5:card:3"]]
    assert cells(confirm_remove_keyboard(5, 1)) == [["p:5:dok:1", "p:5:dno:1"]]
    assert labels(confirm_remove_keyboard(5)) == [["✅ Xóa", "↩ Hủy"]]
    assert cells(list_back_keyboard(4)) == [["l:4"]]
    assert cells(share_open_keyboard("AbC-123_xyz0")) == [
        ["s:AbC-123_xyz0:ok", "s:AbC-123_xyz0:no"]
    ]


def test_list_keyboard_numbers_and_navigation():
    numbered = [(index, make_parcel(id=10 + index)) for index in range(6, 11)]
    markup = list_keyboard(numbered, page=2, pages=3)
    assert labels(markup)[0] == ["6", "7", "8", "9", "10"]
    assert cells(markup)[0][0] == "p:16:card:2"
    assert cells(markup)[-1] == ["l:1", "l:2", "l:3"]
    assert labels(markup)[-1] == ["⬅️", "2/3", "➡️"]
    assert list_keyboard([], page=1, pages=1) is None
    assert cells(list_keyboard([(1, make_parcel(id=1))], page=1, pages=1)) == [["p:1:card:1"]]


def test_list_keyboard_recheck_row():
    markup = list_keyboard([(1, make_parcel(id=1))], page=3, pages=4, recheck=True)
    assert markup.inline_keyboard[-1][0].callback_data == "r:3"
    assert list_keyboard([], page=1, pages=1, recheck=True) is None
