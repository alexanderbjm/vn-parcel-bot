import re
import string

from vn_parcel_bot import texts

ALLOWED_MARKUP = ("<b>", "</b>", "<code>", "</code>", '<a href="{url}">', "</a>")


def all_strings():
    for name, value in vars(texts).items():
        if not name.isupper():
            continue
        if isinstance(value, str):
            yield name, value
        elif isinstance(value, dict):
            for key, item in value.items():
                yield f"{name}[{key}]", item


def test_all_texts_are_html_safe():
    for name, value in all_strings():
        stripped = value
        for markup in ALLOWED_MARKUP:
            stripped = stripped.replace(markup, "")
        assert "<" not in stripped, name
        assert ">" not in stripped, name
        for match in re.finditer("&", stripped):
            assert re.match(r"&(amp|lt|gt);", stripped[match.start() :]), name


def test_placeholders_format_without_error():
    for name, value in all_strings():
        fields = {field for _, field, _, _ in string.Formatter().parse(value) if field}
        assert value.format(**dict.fromkeys(fields, "x")), name


def test_state_maps_cover_all_states():
    states = {"pending", "in_transit", "delivered", "returned", "expired", "stale"}
    assert set(texts.STATE_EMOJI) == states
    assert set(texts.STATE_TEXT) == states
