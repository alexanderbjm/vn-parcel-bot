from collections.abc import Callable, Sequence

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)
from telegram.constants import KeyboardButtonStyle

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.services.formatting import DEFAULT_SORT, next_sort, parcel_link
from vn_parcel_bot.tracking_codes import mask_code

NUMBERS_PER_ROW = 5


def _button(text: str, data: str, style: str | None = None) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data, style=style)


def _page(page: int | None) -> str:
    return "" if page is None else f":{page}"


def _rows(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + NUMBERS_PER_ROW] for i in range(0, len(buttons), NUMBERS_PER_ROW)]


def _list_data(page: int, sort: str) -> str:
    """List callback data; the default order stays plain `l:<page>` for older buttons."""
    return f"l:{page}" if sort == DEFAULT_SORT else f"l:{page}:{sort}"


def _sort_row(sort: str, page: int) -> list[InlineKeyboardButton]:
    """One button showing the order in force; tapping it moves to the next one."""
    following = next_sort(sort)
    label = texts.SORT_LABELS.get(sort, texts.SORT_LABELS[DEFAULT_SORT])
    return [_button(label, f"so:{following}:{page}", style=KeyboardButtonStyle.PRIMARY)]


def _nav_row(data: Callable[[int], str], page: int, pages: int) -> list[InlineKeyboardButton]:
    previous = page - 1 if page > 1 else pages
    following = page + 1 if page < pages else 1
    return [
        _button(texts.BTN_PREV, data(previous)),
        _button(f"{page}/{pages}", data(page)),
        _button(texts.BTN_NEXT, data(following)),
    ]


def card_keyboard(
    parcel: Parcel, *, page: int | None = None, maps: bool = False
) -> InlineKeyboardMarkup:
    prefix, suffix = f"p:{parcel.id}", _page(page)
    name, url = parcel_link(parcel)
    share = _button(texts.BTN_SHARE, f"{prefix}:shr{suffix}")
    link = InlineKeyboardButton(texts.BTN_LINK.format(name=name), url=url)
    rows = [
        [
            _button(texts.BTN_RENAME, f"{prefix}:ren{suffix}"),
            _button(texts.BTN_HISTORY, f"{prefix}:his{suffix}"),
        ],
        [
            _button(texts.BTN_CHECK, f"{prefix}:chk{suffix}", style=KeyboardButtonStyle.SUCCESS),
            _button(texts.BTN_REMOVE, f"{prefix}:del{suffix}", style=KeyboardButtonStyle.DANGER),
        ],
    ]
    if maps:
        rows += [
            [
                share,
                _button(texts.BTN_MAP, f"{prefix}:map{suffix}", style=KeyboardButtonStyle.PRIMARY),
            ],
            [link],
        ]
    else:
        rows.append([share, link])
    if page is not None:
        rows.append([_button(texts.BTN_BACK_LIST, f"l:{page}", style=KeyboardButtonStyle.PRIMARY)])
    return InlineKeyboardMarkup(rows)


def back_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    data = f"p:{parcel_id}:card{_page(page)}"
    btn = _button(texts.BTN_BACK, data, style=KeyboardButtonStyle.PRIMARY)
    return InlineKeyboardMarkup([[btn]])


def confirm_remove_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    suffix = _page(page)
    return InlineKeyboardMarkup(
        [
            [
                _button(
                    texts.BTN_CONFIRM_REMOVE,
                    f"p:{parcel_id}:dok{suffix}",
                    style=KeyboardButtonStyle.DANGER,
                ),
                _button(
                    texts.BTN_CANCEL,
                    f"p:{parcel_id}:dno{suffix}",
                    style=KeyboardButtonStyle.PRIMARY,
                ),
            ]
        ]
    )


def list_back_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_button(texts.BTN_BACK_LIST, f"l:{page}", style=KeyboardButtonStyle.PRIMARY)]]
    )


def list_keyboard(
    numbered: Sequence[tuple[int, Parcel]],
    page: int,
    pages: int,
    *,
    recheck: bool = False,
    sort: str = DEFAULT_SORT,
) -> InlineKeyboardMarkup | None:
    if not numbered:
        return None
    rows = _rows(
        [_button(str(number), f"p:{parcel.id}:card:{page}") for number, parcel in numbered]
    )
    if pages > 1:
        rows.append(_nav_row(lambda target: _list_data(target, sort), page, pages))
    if recheck:
        recheck_data = f"r:{page}" if sort == DEFAULT_SORT else f"r:{page}:{sort}"
        rows.append(
            [
                _button(texts.BTN_RECHECK, recheck_data, style=KeyboardButtonStyle.SUCCESS),
                _button(texts.BTN_SELECT_REMOVE, f"m:on:{page}", style=KeyboardButtonStyle.DANGER),
            ]
        )
        rows.append(_sort_row(sort, page))
    return InlineKeyboardMarkup(rows)


def updates_keyboard(parcels: Sequence[Parcel]) -> InlineKeyboardMarkup | None:
    """Detail buttons under the update notice, which has no numbers to point a digit at.

    The list keyboard labels a parcel with its row number, which only reads as a parcel
    because the list is numbered. This message is not, so a lone "1" said nothing. One
    parcel needs no name -- the message above it names it; several do, one button each.
    """
    if not parcels:
        return None
    single = len(parcels) == 1
    return InlineKeyboardMarkup(
        [
            [
                _button(
                    texts.BTN_DETAIL
                    if single
                    else texts.BTN_DETAIL_NAMED.format(
                        name=parcel.label or mask_code(parcel.tracking_number)
                    ),
                    f"p:{parcel.id}:card:1",
                    style=KeyboardButtonStyle.PRIMARY if single else None,
                )
            ]
            for parcel in parcels
        ]
    )


def select_keyboard(
    numbered: Sequence[tuple[int, Parcel]], page: int, pages: int, selected: set[int]
) -> InlineKeyboardMarkup:
    """Toggle buttons for choosing parcels to remove from the list."""
    rows = _rows(
        [
            _button(
                texts.SELECT_MARK.format(number=number) if parcel.id in selected else str(number),
                f"m:t:{parcel.id}:{page}",
            )
            for number, parcel in numbered
        ]
    )
    if pages > 1:
        rows.append(_nav_row(lambda target: f"m:pg:{target}", page, pages))
    rows.append(
        [
            _button(
                texts.BTN_REMOVE_SELECTED.format(count=len(selected)),
                f"m:go:{page}",
                style=KeyboardButtonStyle.DANGER,
            ),
            _button(texts.BTN_CANCEL, f"m:off:{page}", style=KeyboardButtonStyle.PRIMARY),
        ]
    )
    return InlineKeyboardMarkup(rows)


def remove_confirm_keyboard(count: int) -> InlineKeyboardMarkup:
    confirm = (
        texts.BTN_CONFIRM_REMOVE
        if count == 1
        else texts.BTN_CONFIRM_REMOVE_MANY.format(count=count)
    )
    return InlineKeyboardMarkup(
        [
            [
                _button(confirm, "rm:ok", style=KeyboardButtonStyle.DANGER),
                _button(texts.BTN_CANCEL, "rm:no", style=KeyboardButtonStyle.PRIMARY),
            ]
        ]
    )


def label_prompt_keyboard(has_label: bool) -> InlineKeyboardMarkup:
    row = [_button(texts.BTN_CANCEL, "lb:no", style=KeyboardButtonStyle.PRIMARY)]
    if has_label:
        row.insert(0, _button(texts.BTN_CLEAR_LABEL, "lb:clr", style=KeyboardButtonStyle.DANGER))
    return InlineKeyboardMarkup([row])


def label_pick_keyboard(parcels: Sequence[Parcel]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_button(parcel.label or mask_code(parcel.tracking_number), f"lb:p:{parcel.id}")]
            for parcel in parcels
        ]
    )


def phone_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[_button(texts.BTN_CANCEL, "ph:no", style=KeyboardButtonStyle.PRIMARY)]]
    )


def share_open_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _button(texts.BTN_TRACK_SHARED, f"s:{token}:ok", style=KeyboardButtonStyle.SUCCESS),
                _button(texts.BTN_SKIP, f"s:{token}:no", style=KeyboardButtonStyle.PRIMARY),
            ]
        ]
    )


def location_request_keyboard() -> ReplyKeyboardMarkup:
    """A one-time reply keyboard: share the location, or cancel."""
    return ReplyKeyboardMarkup(
        [
            [KeyboardButton(texts.BTN_SEND_LOCATION, request_location=True)],
            [KeyboardButton(texts.BTN_CANCEL_TEXT)],
        ],
        resize_keyboard=True,
        one_time_keyboard=True,
    )


def start_keyboard() -> InlineKeyboardMarkup:
    """Navigation keyboard attached to /start welcome."""
    return InlineKeyboardMarkup(
        [
            [
                _button("📋 Danh sách đơn", "l:1", style=KeyboardButtonStyle.PRIMARY),
                _button("🔄 Kiểm tra tất cả", "r:1", style=KeyboardButtonStyle.SUCCESS),
            ],
            [
                _button("📍 Vị trí nhận hàng", "cmd:loc", style=KeyboardButtonStyle.PRIMARY),
                _button("📖 Hướng dẫn", "cmd:help"),
            ],
        ]
    )


def help_keyboard() -> InlineKeyboardMarkup:
    """Quick action keyboard attached to /help guide."""
    return InlineKeyboardMarkup(
        [
            [
                _button("📋 Danh sách đơn", "l:1", style=KeyboardButtonStyle.PRIMARY),
                _button("🔄 Kiểm tra tất cả", "r:1", style=KeyboardButtonStyle.SUCCESS),
            ],
            [
                _button("📍 Vị trí nhận hàng", "cmd:loc", style=KeyboardButtonStyle.PRIMARY),
            ],
        ]
    )


def check_done_keyboard() -> InlineKeyboardMarkup:
    """Action buttons after completing /check cycle."""
    return InlineKeyboardMarkup(
        [
            [
                _button("📋 Xem danh sách đơn", "l:1", style=KeyboardButtonStyle.PRIMARY),
                _button("🔄 Kiểm tra lại", "r:1", style=KeyboardButtonStyle.SUCCESS),
            ],
        ]
    )


def history_keyboard(
    parcel_id: int, page: int | None = None, *, maps: bool = False
) -> InlineKeyboardMarkup:
    """Buttons on parcel history / status view."""
    suffix = _page(page)
    row = [
        _button(texts.BTN_BACK, f"p:{parcel_id}:card{suffix}", style=KeyboardButtonStyle.PRIMARY)
    ]
    if maps:
        row.append(
            _button(texts.BTN_MAP, f"p:{parcel_id}:map{suffix}", style=KeyboardButtonStyle.PRIMARY)
        )
    row.append(_button(texts.BTN_BACK_LIST, f"l:{page or 1}"))
    return InlineKeyboardMarkup([row])


def admin_keyboard() -> InlineKeyboardMarkup:
    """Action dashboard for admin command menu /hozk."""
    return InlineKeyboardMarkup(
        [
            [
                _button("🩺 Tình trạng bot", "adm:health", style=KeyboardButtonStyle.PRIMARY),
                _button("👥 Người dùng", "adm:users", style=KeyboardButtonStyle.PRIMARY),
            ],
            [
                _button("🔄 Kiểm tra tất cả", "r:1", style=KeyboardButtonStyle.SUCCESS),
                _button("🏷 Quản lý sticker", "adm:sticker"),
            ],
        ]
    )


def admin_sub_keyboard() -> InlineKeyboardMarkup:
    """Sub-menu keyboard for /health and /users views."""
    return InlineKeyboardMarkup(
        [
            [
                _button("🩺 Tình trạng", "adm:health", style=KeyboardButtonStyle.PRIMARY),
                _button("👥 Người dùng", "adm:users", style=KeyboardButtonStyle.PRIMARY),
            ],
            [
                _button("🛠 Menu quản lý", "adm:hozk", style=KeyboardButtonStyle.PRIMARY),
            ],
        ]
    )
