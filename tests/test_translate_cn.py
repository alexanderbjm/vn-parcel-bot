import pytest

from vn_parcel_bot.carriers.translate_cn import has_chinese, translate_cn


@pytest.mark.parametrize(
    ("chinese", "expected_parts"),
    [
        ("【上海市】快件已到达 上海转运中心", ["Thượng Hải", "đã đến", "trung tâm trung chuyển"]),
        ("【深圳市】快件已发往 广东东莞沙田镇公司", ["Thâm Quyến", "đã gửi đi"]),
        ("【东莞市】快件已到达 广东东莞沙田镇公司", ["đã đến"]),
        ("您的快件已由【仓库】代收", ["kho", "đã nhận"]),
        ("正在为您派送", ["đang giao hàng"]),
        ("已揽收", ["đã lấy hàng"]),
        ("快件已签收", ["đã ký nhận"]),
    ],
)
def test_common_status_lines_become_vietnamese(chinese, expected_parts):
    vietnamese = translate_cn(chinese)
    for part in expected_parts:
        assert part in vietnamese
    assert not has_chinese(vietnamese)


def test_courier_phone_numbers_and_promos_are_dropped():
    line = (
        "东莞市 511845, 【东莞市】广东东莞沙田镇公司 的快递员(3号库7垛口/15876434514)正在为您派送，"
        "【物流问题无需找商家或平台，请致电（076933557172）或专属渠道95543更快解决】，"
        "可关注“申通快递”官方微信公众号获取实时物流信息"
    )
    text = translate_cn(line)
    assert "15876434514" not in text
    assert "076933557172" not in text
    assert "95543" not in text
    assert "đang giao hàng" in text
    assert len(text) < len(line)


def test_pickup_line_drops_the_courier_name_and_number():
    line = "上海市 200374, 【上海市】上海杨浦区平凉公司(02138185757)的翁纪飞(16651868924) 已揽收"
    text = translate_cn(line)
    assert "翁纪飞" not in text
    assert "16651868924" not in text
    assert "02138185757" not in text
    assert "đã lấy hàng" in text


def test_text_without_chinese_is_left_alone():
    assert translate_cn("Đơn hàng đã đến kho BN A Mega SOC") == "Đơn hàng đã đến kho BN A Mega SOC"
    assert translate_cn("") == ""
    assert has_chinese("Đơn hàng") is False
    assert has_chinese("快件") is True


def test_unknown_chinese_words_do_not_break_the_line():
    text = translate_cn("【上海市】某些未知状态 快件已到达")
    assert "Thượng Hải" in text
    assert "đã đến" in text


def test_repeated_places_and_full_width_punctuation_are_tidied():
    text = translate_cn("【东莞市】广东东莞沙田镇公司 已签收！")
    assert "！" not in text
    assert "đã ký nhận" in text
    assert text.count("Đông Quản") <= 2
    assert "  " not in text


def test_a_location_field_becomes_a_place_name():
    assert translate_cn("东莞市") == "Đông Quản"
    assert translate_cn("上海市") == "Thượng Hải"
