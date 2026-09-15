import pytest

from vn_parcel_bot.bot.parsing import parse_coordinates

PLACE_LINK = (
    "https://www.google.com/maps/place/Ho+Guom/@21.1,105.9,17z/"
    "data=!3m1!4b1!4m6!3m5!1s0x0:0x0!8m2!3d21.0285!4d105.8542"
)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("21.028511, 105.854222", (21.028511, 105.854222)),
        ("21.0285 105.8542", (21.0285, 105.8542)),
        (" 10.7769,106.7009 ", (10.7769, 106.7009)),
        ("-33.8688, 151.2093", (-33.8688, 151.2093)),
        ("https://www.google.com/maps/@21.0285,105.8542,15z", (21.0285, 105.8542)),
        ("https://maps.google.com/?q=21.0285,105.8542", (21.0285, 105.8542)),
        (
            "https://www.google.com/maps/search/?api=1&query=21.0285%2C105.8542",
            (21.0285, 105.8542),
        ),
        (PLACE_LINK, (21.0285, 105.8542)),
    ],
)
def test_coordinates_are_read_from_pasted_text_and_links(text, expected):
    assert parse_coordinates(text) == expected


@pytest.mark.parametrize(
    "text",
    [
        "",
        "xin chào",
        "841000072647",
        "SPXVN000000000001",
        "95.0, 105.0",
        "21.0, 190.0",
        "21, 105",
        "https://maps.app.goo.gl/AbCdEf123",
    ],
)
def test_other_text_is_not_a_location(text):
    assert parse_coordinates(text) is None
