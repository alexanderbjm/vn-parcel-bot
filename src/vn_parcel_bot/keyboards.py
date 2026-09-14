from collections.abc import Sequence

from telegram import InlineKeyboardButton, InlineKeyboardMarkup

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.services.formatting import parcel_link

NUMBERS_PER_ROW = 5


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _page(page: int | None) -> str:
    return "" if page is None else f":{page}"


def card_keyboard(parcel: Parcel, *, page: int | None = None) -> InlineKeyboardMarkup:
    prefix, suffix = f"p:{parcel.id}", _page(page)
    name, url = parcel_link(parcel)
    rows = [
        [
            _button(texts.BTN_RENAME, f"{prefix}:ren{suffix}"),
            _button(texts.BTN_HISTORY, f"{prefix}:his{suffix}"),
        ],
        [
            _button(texts.BTN_CHECK, f"{prefix}:chk{suffix}"),
            _button(texts.BTN_REMOVE, f"{prefix}:del{suffix}"),
        ],
        [
            _button(texts.BTN_SHARE, f"{prefix}:shr{suffix}"),
            InlineKeyboardButton(texts.BTN_LINK.format(name=name), url=url),
        ],
    ]
    if page is not None:
        rows.append([_button(texts.BTN_BACK_LIST, f"l:{page}")])
    return InlineKeyboardMarkup(rows)


def back_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(texts.BTN_BACK, f"p:{parcel_id}:card{_page(page)}")]])


def confirm_remove_keyboard(parcel_id: int, page: int | None = None) -> InlineKeyboardMarkup:
    suffix = _page(page)
    return InlineKeyboardMarkup(
        [
            [
                _button(texts.BTN_CONFIRM_REMOVE, f"p:{parcel_id}:dok{suffix}"),
                _button(texts.BTN_CANCEL, f"p:{parcel_id}:dno{suffix}"),
            ]
        ]
    )


def list_back_keyboard(page: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(texts.BTN_BACK_LIST, f"l:{page}")]])


def list_keyboard(
    numbered: Sequence[tuple[int, Parcel]], page: int, pages: int
) -> InlineKeyboardMarkup | None:
    if not numbered:
        return None
    buttons = [_button(str(number), f"p:{parcel.id}:card:{page}") for number, parcel in numbered]
    rows = [buttons[i : i + NUMBERS_PER_ROW] for i in range(0, len(buttons), NUMBERS_PER_ROW)]
    if pages > 1:
        previous = page - 1 if page > 1 else pages
        following = page + 1 if page < pages else 1
        rows.append(
            [
                _button(texts.BTN_PREV, f"l:{previous}"),
                _button(f"{page}/{pages}", f"l:{page}"),
                _button(texts.BTN_NEXT, f"l:{following}"),
            ]
        )
    return InlineKeyboardMarkup(rows)


def share_open_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _button(texts.BTN_TRACK_SHARED, f"s:{token}:ok"),
                _button(texts.BTN_SKIP, f"s:{token}:no"),
            ]
        ]
    )
