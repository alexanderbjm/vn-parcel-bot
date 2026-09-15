from tests.test_formatting import make_parcel
from vn_parcel_bot import texts
from vn_parcel_bot.keyboards import (
    admin_keyboard,
    admin_sub_keyboard,
    back_keyboard,
    card_keyboard,
    check_done_keyboard,
    confirm_remove_keyboard,
    help_keyboard,
    history_keyboard,
    list_back_keyboard,
    list_keyboard,
    share_open_keyboard,
    start_keyboard,
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
    assert [b.callback_data for b in markup.inline_keyboard[-1]] == ["r:3", "m:on:3"]
    assert list_keyboard([], page=1, pages=1, recheck=True) is None


def test_card_keyboard_with_maps_moves_the_link_to_its_own_row():
    rows = card_keyboard(make_parcel(id=4), maps=True).inline_keyboard
    assert [button.callback_data for button in rows[2]] == ["p:4:shr", "p:4:map"]
    assert rows[2][1].text == "🗺 Bản đồ"
    assert rows[3][0].url is not None
    assert len(rows) == 4
    assert len(card_keyboard(make_parcel(id=4)).inline_keyboard) == 3
    with_page = card_keyboard(make_parcel(id=4), page=1, maps=True).inline_keyboard
    assert with_page[2][1].callback_data == "p:4:map:1"
    assert with_page[-1][0].callback_data == "l:1"


def test_start_and_help_keyboards():
    start_kb = start_keyboard()
    assert cells(start_kb) == [
        ["l:1", "r:1"],
        ["cmd:loc", "cmd:help"],
    ]
    assert labels(start_kb) == [
        ["📋 Danh sách đơn", "🔄 Kiểm tra tất cả"],
        ["📍 Vị trí nhận hàng", "📖 Hướng dẫn"],
    ]

    help_kb = help_keyboard()
    assert cells(help_kb) == [
        ["l:1", "r:1"],
        ["cmd:loc"],
    ]
    assert labels(help_kb) == [
        ["📋 Danh sách đơn", "🔄 Kiểm tra tất cả"],
        ["📍 Vị trí nhận hàng"],
    ]


def test_check_done_and_history_keyboards():
    done_kb = check_done_keyboard()
    assert cells(done_kb) == [["l:1", "r:1"]]
    assert labels(done_kb) == [["📋 Xem danh sách đơn", "🔄 Kiểm tra lại"]]

    his_kb = history_keyboard(42, page=2, maps=True)
    assert cells(his_kb) == [["p:42:card:2", "p:42:map:2", "l:2"]]
    assert labels(his_kb) == [[texts.BTN_BACK, texts.BTN_MAP, texts.BTN_BACK_LIST]]

    his_no_map = history_keyboard(42)
    assert cells(his_no_map) == [["p:42:card", "l:1"]]


def test_admin_keyboards():
    adm_kb = admin_keyboard()
    assert cells(adm_kb) == [
        ["adm:health", "adm:users"],
        ["r:1", "adm:sticker"],
    ]
    assert labels(adm_kb) == [
        ["🩺 Tình trạng bot", "👥 Người dùng"],
        ["🔄 Kiểm tra tất cả", "🏷 Quản lý sticker"],
    ]

    sub_kb = admin_sub_keyboard()
    assert cells(sub_kb) == [
        ["adm:health", "adm:users"],
        ["adm:hozk"],
    ]


def test_button_styles():
    markup = card_keyboard(make_parcel(id=42))
    # Check button has SUCCESS style (green)
    check_btn = markup.inline_keyboard[1][0]
    assert check_btn.text == "🔄 Kiểm tra"
    assert check_btn.style == "success"

    # Delete button has DANGER style (red)
    del_btn = markup.inline_keyboard[1][1]
    assert del_btn.text == "🗑 Xóa"
    assert del_btn.style == "danger"

    # Confirm remove button has DANGER style
    confirm_kb = confirm_remove_keyboard(42)
    assert confirm_kb.inline_keyboard[0][0].style == "danger"
    assert confirm_kb.inline_keyboard[0][1].style == "primary"
