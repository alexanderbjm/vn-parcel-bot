from collections.abc import Callable, Sequence

from telegram import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
)

from vn_parcel_bot import texts
from vn_parcel_bot.db.repo import Parcel
from vn_parcel_bot.services.formatting import parcel_link
from vn_parcel_bot.tracking_codes import mask_code

NUMBERS_PER_ROW = 5


def _button(text: str, data: str) -> InlineKeyboardButton:
    return InlineKeyboardButton(text, callback_data=data)


def _page(page: int | None) -> str:
    return "" if page is None else f":{page}"


def _rows(buttons: list[InlineKeyboardButton]) -> list[list[InlineKeyboardButton]]:
    return [buttons[i : i + NUMBERS_PER_ROW] for i in range(0, len(buttons), NUMBERS_PER_ROW)]


def _nav_row(data: Callable[[int], str], page: int, pages: int) -> list[InlineKeyboardButton]:
    previous = page - 1 if page > 1 else pages
    following = page + 1 if page < pages else 1
    return [
        _button(texts.BTN_PREV, data(previous)),
        _button(f"{page}/{pages}", data(page)),
        _button(texts.BTN_NEXT, data(following)),
    ]


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
    numbered: Sequence[tuple[int, Parcel]], page: int, pages: int, *, recheck: bool = False
) -> InlineKeyboardMarkup | None:
    if not numbered:
        return None
    rows = _rows(
        [_button(str(number), f"p:{parcel.id}:card:{page}") for number, parcel in numbered]
    )
    if pages > 1:
        rows.append(_nav_row(lambda target: f"l:{target}", page, pages))
    if recheck:
        rows.append(
            [
                _button(texts.BTN_RECHECK, f"r:{page}"),
                _button(texts.BTN_SELECT_REMOVE, f"m:on:{page}"),
            ]
        )
    return InlineKeyboardMarkup(rows)


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
            _button(texts.BTN_REMOVE_SELECTED.format(count=len(selected)), f"m:go:{page}"),
            _button(texts.BTN_CANCEL, f"m:off:{page}"),
        ]
    )
    return InlineKeyboardMarkup(rows)


def remove_confirm_keyboard(count: int) -> InlineKeyboardMarkup:
    confirm = (
        texts.BTN_CONFIRM_REMOVE
        if count == 1
        else texts.BTN_CONFIRM_REMOVE_MANY.format(count=count)
    )
    return InlineKeyboardMarkup([[_button(confirm, "rm:ok"), _button(texts.BTN_CANCEL, "rm:no")]])


def label_prompt_keyboard(has_label: bool) -> InlineKeyboardMarkup:
    row = [_button(texts.BTN_CANCEL, "lb:no")]
    if has_label:
        row.insert(0, _button(texts.BTN_CLEAR_LABEL, "lb:clr"))
    return InlineKeyboardMarkup([row])


def label_pick_keyboard(parcels: Sequence[Parcel]) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [_button(parcel.label or mask_code(parcel.tracking_number), f"lb:p:{parcel.id}")]
            for parcel in parcels
        ]
    )


def phone_prompt_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup([[_button(texts.BTN_CANCEL, "ph:no")]])


def share_open_keyboard(token: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                _button(texts.BTN_TRACK_SHARED, f"s:{token}:ok"),
                _button(texts.BTN_SKIP, f"s:{token}:no"),
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
