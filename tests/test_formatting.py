from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tests.fakes import ev, found
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import CarrierError, TrackingResult
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.services.formatting import (
    carrier_name,
    carrier_names,
    format_add_outcome,
    format_carrier_alert,
    format_event_update,
    format_expired,
    format_health,
    format_help,
    format_history,
    format_link_only,
    format_links,
    format_needs_phone_multi,
    format_parcel_list,
    format_stale,
    format_time,
    format_users,
    parcel_carrier_label,
    parcel_title,
    seventeen_track_url,
    truncate_message,
)
from vn_parcel_bot.services.parcels import AddOutcome

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
T0 = datetime(2026, 9, 1, 1, 30, tzinfo=UTC)
SPX = "SPXVN000000000001"


def make_parcel(**overrides) -> Parcel:
    values = {
        "id": 1,
        "user_id": 1,
        "carrier": "spx",
        "candidates": ("spx",),
        "tracking_number": SPX,
        "phone_last4": None,
        "label": None,
        "state": "in_transit",
        "last_status_text": None,
        "last_event_at": None,
        "consecutive_failures": 0,
        "next_check_at": T0,
        "delivered_at": None,
        "created_at": T0,
        "updated_at": T0,
    }
    values.update(overrides)
    return Parcel(**values)


def unresolved(**overrides) -> Parcel:
    return make_parcel(
        carrier=None,
        candidates=("ghn", "ninjavan"),
        tracking_number="GA0000000001",
        state="pending",
        **overrides,
    )


def bullet_lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.startswith("• ")]


def test_title_prefers_escaped_label():
    assert parcel_title(make_parcel(label="<Áo & quần>")) == "&lt;Áo &amp; quần&gt;"
    assert parcel_title(make_parcel()) == SPX


def test_carrier_labels():
    assert carrier_name("jt") == "J&amp;T"
    assert carrier_names(["spx", "jt"]) == "SPX / J&amp;T"
    assert parcel_carrier_label(make_parcel(carrier="jt", candidates=("jt",))) == "J&amp;T"
    assert parcel_carrier_label(unresolved()) == "GHN / Ninja Van"


def test_format_time_local():
    assert format_time(T0, TZ) == "01/09 08:30"


def test_format_links_official_then_17track():
    lines = format_links("EB123456789VN", ["vnpost"]).split("\n")
    assert len(lines) == 2
    assert lines[0].startswith('• <a href="https://vnpost.vn/')
    assert "&amp;code=EB123456789VN" in lines[0]
    assert lines[0].endswith(">VNPost</a>")
    assert lines[1] == '• <a href="https://t.17track.net/vi#nums=EB123456789VN">17TRACK</a>'


def test_format_links_template_without_code_and_tracked_skipped():
    viettel = format_links("841000072647", ["viettelpost"]).split("\n")
    assert 'href="https://viettelpost.com.vn/tra-cuu-hanh-trinh-don/"' in viettel[0]
    assert len(format_links(SPX, ["spx"]).split("\n")) == 1


def test_format_link_only():
    text = format_link_only("EB123456789VN", ["vnpost"])
    assert "<code>EB123456789VN</code>" in text
    assert "Mình chưa tự theo dõi được hãng này" in text
    assert "VNPost" in text
    assert "17TRACK" in text


def test_event_update_lines_and_location():
    text = format_event_update(
        make_parcel(),
        [ev(0, "A", "Kho HCM"), ev(10, "B", None)],
        TZ,
        delivered=False,
        returned=False,
    )
    assert text.split("\n")[0] == f"📦 <b>{SPX}</b> · SPX"
    assert bullet_lines(text) == ["• 01/09 15:00 — A (Kho HCM)", "• 01/09 15:10 — B"]


def test_event_update_escapes_description():
    text = format_event_update(
        make_parcel(), [ev(0, "<script>")], TZ, delivered=False, returned=False
    )
    assert "&lt;script&gt;" in text
    assert "<script>" not in text


def test_event_update_more_than_ten():
    events = [ev(i, f"E{i}") for i in range(13)]
    text = format_event_update(make_parcel(), events, TZ, delivered=False, returned=False)
    assert "… và 3 cập nhật trước đó" in text
    bullets = bullet_lines(text)
    assert len(bullets) == 10
    assert "E12" in bullets[-1]
    assert "E3" in bullets[0]


def test_event_update_delivered_footer():
    events = [ev(0)]
    assert format_event_update(make_parcel(), events, TZ, delivered=True, returned=False).endswith(
        texts.UPDATE_DELIVERED
    )
    assert format_event_update(make_parcel(), events, TZ, delivered=False, returned=True).endswith(
        texts.UPDATE_RETURNED
    )
    plain = format_event_update(make_parcel(), events, TZ, delivered=False, returned=False)
    assert texts.UPDATE_DELIVERED not in plain
    assert texts.UPDATE_RETURNED not in plain


def test_event_update_resolved_note():
    text = format_event_update(
        unresolved(), [ev(0)], TZ, delivered=False, returned=False, resolved_carrier="ninjavan"
    )
    assert text.split("\n")[0] == "📦 <b>GA0000000001</b> · Ninja Van"
    assert "🔎 Đã xác định hãng vận chuyển: <b>Ninja Van</b>" in text


def test_parcel_list_empty():
    assert format_parcel_list([], TZ) == texts.LIST_EMPTY


def test_parcel_list_items():
    parcels = [
        make_parcel(label="Áo", last_status_text="Đang giao", last_event_at=T0),
        unresolved(id=2),
    ]
    text = format_parcel_list(parcels, TZ)
    assert text.startswith(texts.LIST_HEADER + "\n\n")
    assert "1. 🚚 <b>Áo</b> · SPX\n    Đang giao · 🕒 01/09 08:30" in text
    assert (
        "2. ⏳ <b>GA0000000001</b> · Đang xác định hãng\n    Chưa có thông tin vận chuyển" in text
    )


def test_history_newest_first_and_empty():
    text = format_history(make_parcel(), [ev(0, "A"), ev(5, "B")], TZ)
    assert text.startswith(f"<b>📦 {SPX}</b> · SPX · <code>{SPX}</code>")
    assert text.index("B") < text.index("— A")
    assert texts.HISTORY_EMPTY in format_history(make_parcel(), [], TZ)


def outcome_text(outcome: AddOutcome) -> str:
    return format_add_outcome(outcome, TZ, max_parcels=30)


def test_add_outcome_jt_cross_border_hint():
    code = "JNTXB0000000001"
    pending = make_parcel(carrier="jt", candidates=("jt",), tracking_number=code, state="pending")
    text = outcome_text(
        AddOutcome("added", code=code, parcel=pending, result=TrackingResult("jt", code, False))
    )
    assert "app Lazada" in text
    assert texts.ADDED_PENDING_PHONE_HINT.strip() in text
    asked = outcome_text(AddOutcome("needs_phone", code=code, candidates=("jt",)))
    assert "app Lazada" in asked

    domestic_code = "841000072647"
    domestic = make_parcel(
        carrier="jt", candidates=("jt",), tracking_number=domestic_code, state="pending"
    )
    plain = outcome_text(
        AddOutcome(
            "added",
            code=domestic_code,
            parcel=domestic,
            result=TrackingResult("jt", domestic_code, False),
        )
    )
    assert "app Lazada" not in plain


def test_add_outcome_lazada_cainiao_hint():
    code = "YT0000000000001"
    pending = make_parcel(
        carrier="cainiao", candidates=("cainiao",), tracking_number=code, state="pending"
    )
    text = outcome_text(
        AddOutcome(
            "added", code=code, parcel=pending, result=TrackingResult("cainiao", code, False)
        )
    )
    assert "app Lazada" in text

    lp_code = "LP00000000000001"
    other = make_parcel(
        carrier="cainiao", candidates=("cainiao",), tracking_number=lp_code, state="pending"
    )
    plain = outcome_text(
        AddOutcome(
            "added", code=lp_code, parcel=other, result=TrackingResult("cainiao", lp_code, False)
        )
    )
    assert "app Lazada" not in plain


def test_add_outcome_found_and_delivered():
    result = found("spx", SPX, ev(0, "Đang giao hàng"))
    text = outcome_text(AddOutcome("added", code=SPX, parcel=make_parcel(), result=result))
    assert "Đã theo dõi" in text
    assert "Đang giao hàng" in text
    assert "01/09 15:00" in text
    delivered = outcome_text(
        AddOutcome("added", code=SPX, parcel=make_parcel(state="delivered"), result=result)
    )
    assert "đã giao thành công" in delivered


def test_add_outcome_error():
    error = CarrierError("spx", "network", "ConnectTimeout")
    text = outcome_text(
        AddOutcome("added", code=SPX, parcel=make_parcel(state="pending"), error=error)
    )
    assert "chưa kết nối được với SPX" in text
    assert "Nếu đây là đơn" not in text
    jt_parcel = make_parcel(carrier="jt", candidates=("jt",), tracking_number="841000072647")
    with_links = outcome_text(
        AddOutcome(
            "added",
            code="841000072647",
            parcel=jt_parcel,
            error=CarrierError("jt", "network"),
            link_carriers=("best", "viettelpost"),
        )
    )
    assert "Nếu đây là đơn BEST Express / Viettel Post" in with_links


def test_add_outcome_pending_variants():
    not_found = TrackingResult("spx", SPX, False)
    plain = outcome_text(
        AddOutcome("added", code=SPX, parcel=make_parcel(state="pending"), result=not_found)
    )
    assert "mình sẽ kiểm tra lại định kỳ" in plain
    assert "4 số cuối SĐT" not in plain

    jt_parcel = make_parcel(
        carrier="jt", candidates=("jt",), tracking_number="841000072647", state="pending"
    )
    jt_text = outcome_text(
        AddOutcome(
            "added",
            code="841000072647",
            parcel=jt_parcel,
            result=TrackingResult("jt", "841000072647", False),
            link_carriers=("best", "viettelpost"),
        )
    )
    assert "kiểm tra lại 4 số cuối SĐT" in jt_text
    assert "Nếu đây là đơn BEST Express / Viettel Post, xem tại:" in jt_text
    assert "17TRACK" in jt_text

    auto = outcome_text(
        AddOutcome(
            "added",
            code="GA0000000001",
            parcel=unresolved(),
            result=TrackingResult("ninjavan", "GA0000000001", False),
        )
    )
    assert "Mình sẽ tự kiểm tra mã này ở GHN / Ninja Van" in auto
    assert "kiểm tra lại 4 số cuối SĐT" in auto


def test_add_outcome_other_kinds():
    ask = outcome_text(AddOutcome("needs_phone", code="841000072647", candidates=("jt",)))
    assert "<code>841000072647</code> (J&amp;T) cần 4 số cuối SĐT" in ask
    link = outcome_text(AddOutcome("link_only", code="EB123456789VN", link_carriers=("vnpost",)))
    assert "Mình chưa tự theo dõi được hãng này" in link
    assert "Bạn đã theo dõi đơn" in outcome_text(AddOutcome("duplicate", code=SPX))
    assert "tối đa 30 đơn" in outcome_text(AddOutcome("limit", code=SPX))
    assert outcome_text(AddOutcome("invalid_code")) == texts.UNKNOWN_CODE
    assert outcome_text(AddOutcome("invalid_phone", code=SPX)) == texts.INVALID_PHONE


def test_add_outcome_unknown_carrier():
    unknown = outcome_text(AddOutcome("unknown_carrier", code="ABC1234567890DEF"))
    assert "chưa nhận ra hãng vận chuyển" in unknown
    assert 'href="https://t.17track.net/vi#nums=ABC1234567890DEF"' in unknown
    assert texts.UNKNOWN_CODE not in unknown


def test_add_outcome_seller_fleet():
    text = outcome_text(AddOutcome("seller_fleet", code="84000000000001"))
    assert "<code>84000000000001</code>" in text
    assert "người bán tự giao" in text
    assert "TikTok Shop" in text
    assert 'href="https://t.17track.net/vi#nums=84000000000001"' in text
    assert "J&amp;T" not in text


def test_help_and_usage_do_not_mention_carrier_names_argument():
    assert "[hãng]" not in texts.HELP
    assert "[hãng]" not in texts.USAGE_TRACK
    assert "&lt;hãng&gt;" not in texts.UNKNOWN_CODE


def test_needs_phone_multi_expired_and_stale():
    multi = format_needs_phone_multi(["840000000001", "GA0000000001"])
    assert "<code>840000000001</code>\n<code>GA0000000001</code>" in multi
    assert "<code>SPXVN000000000001</code>" in format_expired(make_parcel())
    assert f"<b>{SPX}</b>" in format_stale(make_parcel())


def test_carrier_alert_escapes_and_cuts():
    text = format_carrier_alert("jt", 5, "<x>" * 100)
    assert "<b>J&amp;T</b>: 5 lỗi" in text
    assert "&lt;x&gt;" in text
    assert "<x>" not in text
    assert text.count("&lt;x&gt;") <= 67


def test_users_roles():
    users = [
        User(111, "Admin", None, True, True, T0),
        User(2, None, None, False, True, T0),
        User(3, "<Bị khóa>", None, False, False, T0),
    ]
    text = format_users(users, {111: 2, 2: 0}, 111)
    assert "• <code>111</code> Admin — quản lý · 2 đơn đang theo dõi" in text
    assert "• <code>2</code> — — thành viên · 0 đơn đang theo dõi" in text
    assert "&lt;Bị khóa&gt; — đã khóa" in text


def test_health_never_and_with_report():
    never = format_health(None, None, 0, 1, TZ)
    assert "chưa chạy" in never
    assert "lỗi: 0" in never
    report = {"fetches": 5, "new_events": 2, "failures": {"spx": 2, "ghn": 1}}
    text = format_health(T0, report, 3, 2, TZ)
    assert "01/09 08:30" in text
    assert "5 lượt tra cứu, 2 cập nhật mới, lỗi: spx=2, ghn=1" in text


def test_truncate_message():
    assert truncate_message("short") == "short"
    long_text = "line\n" * 2000
    cut = truncate_message(long_text)
    assert len(cut) <= 4000
    assert cut.endswith("…")
    assert cut[:-1].endswith("line")
    single = truncate_message("x" * 5000)
    assert len(single) == 4000
    assert single.endswith("…")


def test_seventeen_track_url():
    assert seventeen_track_url("EB123456789VN") == "https://t.17track.net/vi#nums=EB123456789VN"


def test_help_lists_carriers_from_modules():
    text = format_help()
    assert "Tự động theo dõi: SPX, J&amp;T, Cainiao, 4PX, Ninja Van, GHN\n" in text
    assert (
        "Gửi link tra cứu: BEST Express, YunExpress, GHTK, Viettel Post, VNPost, LEX VN, "
        "SF Express\n"
    ) in text
