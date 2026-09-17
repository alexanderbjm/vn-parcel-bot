from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from tests.fakes import ev, found
from vn_parcel_bot import texts
from vn_parcel_bot.carriers.models import CarrierError, TrackingResult
from vn_parcel_bot.db.repo import Parcel, User
from vn_parcel_bot.services.formatting import (
    Moved,
    carrier_name,
    carrier_names,
    format_add_outcome,
    format_carrier_alert,
    format_check_done,
    format_digest,
    format_event_update,
    format_expired,
    format_health,
    format_help,
    format_history,
    format_link_only,
    format_links,
    format_needs_phone_multi,
    format_parcel_card,
    format_parcel_list,
    format_stale,
    format_time,
    format_updates,
    format_users,
    list_pages,
    parcel_carrier_label,
    parcel_link,
    parcel_title,
    ref_text,
    seventeen_track_url,
    sort_parcels,
    spoiler,
    truncate_message,
)
from vn_parcel_bot.services.parcels import AddOutcome

TZ = ZoneInfo("Asia/Ho_Chi_Minh")
T0 = datetime(2026, 9, 1, 1, 30, tzinfo=UTC)
SPX = "SPXVN000000000001"


def blurred(code: str) -> str:
    return f'<span class="tg-spoiler">{code}</span>'


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
    assert parcel_title(make_parcel(label="<Áo & quần>")) == "&lt;Áo &amp; quần&gt; · " + blurred(
        SPX
    )
    assert parcel_title(make_parcel()) == blurred(SPX)


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
    assert blurred("EB123456789VN") in text
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
    assert text.split("\n")[0] == f"📦 <b>{blurred(SPX)}</b> · SPX"
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
    assert text.split("\n")[0] == f"📦 <b>{blurred('GA0000000001')}</b> · Ninja Van"
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
    assert f"1. <b>Áo</b> · SPX\n    {blurred(SPX)}\n    Đang giao\n    🕒 01/09 08:30" in text
    assert (
        f"2. <b>{blurred('GA0000000001')}</b> · Đang xác định hãng\n"
        "    Chưa có thông tin vận chuyển" in text
    )


def test_history_newest_first_and_empty():
    text = format_history(make_parcel(), [ev(0, "A"), ev(5, "B")], TZ)
    assert text.startswith(f"<b>📦 {blurred(SPX)}</b> · SPX · {blurred(SPX)}")
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
    assert f"{blurred('841000072647')} (J&amp;T) cần 4 số cuối SĐT" in ask
    link = outcome_text(AddOutcome("link_only", code="EB123456789VN", link_carriers=("vnpost",)))
    assert "Mình chưa tự theo dõi được hãng này" in link
    duplicate = outcome_text(AddOutcome("duplicate", code=SPX))
    assert "Bạn đã theo dõi đơn" in duplicate
    assert blurred(SPX) in duplicate
    assert "tối đa 30 đơn" in outcome_text(AddOutcome("limit", code=SPX))
    assert outcome_text(AddOutcome("invalid_code")) == texts.UNKNOWN_CODE
    assert outcome_text(AddOutcome("invalid_phone", code=SPX)) == texts.INVALID_PHONE


def test_add_outcome_unknown_carrier():
    unknown = outcome_text(AddOutcome("unknown_carrier", code="ABC1234567890DEF"))
    assert "chưa nhận ra hãng vận chuyển" in unknown
    assert blurred("ABC1234567890DEF") in unknown
    assert 'href="https://t.17track.net/vi#nums=ABC1234567890DEF"' in unknown
    assert texts.UNKNOWN_CODE not in unknown


def test_add_outcome_seller_fleet():
    text = outcome_text(AddOutcome("seller_fleet", code="84000000000001"))
    assert blurred("84000000000001") in text
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
    assert f"{blurred('840000000001')}\n{blurred('GA0000000001')}" in multi
    assert blurred(SPX) in format_expired(make_parcel())
    assert f"<b>{blurred(SPX)}</b>" in format_stale(make_parcel())


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


def test_health_shows_the_deployed_revision_when_known():
    text = format_health(None, None, 0, 1, TZ, "1258faf · 16/09/2026")
    assert text.endswith("\nBản cập nhật: 1258faf · 16/09/2026")


def test_health_omits_the_revision_line_when_unknown():
    assert "Bản cập nhật" not in format_health(None, None, 0, 1, TZ)
    assert "Bản cập nhật" not in format_health(None, None, 0, 1, TZ, None)


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


def test_spoiler_escapes_and_labels_stay_readable():
    assert spoiler("<a&b>") == '<span class="tg-spoiler">&lt;a&amp;b&gt;</span>'
    assert parcel_title(make_parcel(label="Áo")) == "Áo · " + blurred(SPX)


def test_ref_text_blurs_codes_but_not_list_numbers():
    assert ref_text("12") == "12"
    assert ref_text(SPX) == blurred(SPX)
    assert ref_text("<x>") == blurred("&lt;x&gt;")


def test_list_item_shows_progress_and_bar():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0, progress=80)
    text = format_parcel_list([parcel], TZ)
    assert (
        "1. <b>Áo</b> · SPX · 80%\n"
        "    " + blurred(SPX) + "\n    Đã đến kho\n    🕒 01/09 08:30"
        "\n    🟩🟩🟩🟩🟩🟩🟩🟩🟥🟥" in text
    )


def test_list_item_hides_progress_for_returned_and_unknown():
    returned = make_parcel(label="Áo", state="returned", progress=80)
    assert "80%" not in format_parcel_list([returned], TZ)
    assert "%" not in format_parcel_list([make_parcel(label="Áo")], TZ)


def test_digest_puts_new_mark_after_progress():
    text = format_digest([make_parcel(label="Áo", progress=50)], {1}, T0, TZ)
    assert "<b>Áo</b> · SPX · 50% 🆕" in text


def test_event_update_header_shows_progress_and_bar():
    text = format_event_update(
        make_parcel(label="Áo"), [ev(0)], TZ, delivered=False, returned=False, progress=95
    )
    lines = text.split("\n")
    assert lines[0] == f"📦 <b>Áo · {blurred(SPX)}</b> · SPX · 95%"
    assert lines[1] == "🟩🟩🟩🟩🟩🟩🟩🟩🟩🟥"


def test_delivered_parcel_shows_100_percent_without_a_bar():
    parcel = make_parcel(label="Áo", state="delivered", progress=95)
    text = format_parcel_list([parcel], TZ)
    assert "<b>Áo</b> · SPX · 100%" in text, "the code sits on its own line now"
    assert "🟩" not in text and "🟥" not in text
    card = format_parcel_card(parcel, TZ)
    assert card.startswith(f"✅ <b>Áo · {blurred(SPX)}</b> · SPX · 100%\n")
    assert "🟩" not in card and "🟥" not in card


def test_delivered_update_shows_100_percent_without_a_bar():
    text = format_event_update(
        make_parcel(label="Áo"), [ev(0)], TZ, delivered=True, returned=False, progress=100
    )
    assert text.split("\n")[0] == f"📦 <b>Áo · {blurred(SPX)}</b> · SPX · 100%"
    assert "🟩" not in text


def test_parcel_card_shows_title_progress_bar_and_status():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0, progress=50)
    assert format_parcel_card(parcel, TZ) == (
        f"🚚 <b>Áo · {blurred(SPX)}</b> · SPX · 50%\n"
        "🟩🟩🟩🟩🟩🟥🟥🟥🟥🟥\nĐã đến kho · 🕒 01/09 08:30"
    )
    pending = format_parcel_card(unresolved(), TZ)
    assert pending.startswith(f"⏳ <b>{blurred('GA0000000001')}</b> · GHN / Ninja Van\n")


def test_parcel_link_prefers_module_link():
    assert parcel_link(make_parcel()) == ("17TRACK", f"https://t.17track.net/vi#nums={SPX}")
    vnpost = make_parcel(carrier="vnpost", candidates=("vnpost",), tracking_number="EB123456789VN")
    name, url = parcel_link(vnpost)
    assert name == "VNPost"
    assert url.startswith("https://vnpost.vn/")


def test_parcel_list_pages():
    parcels = [
        make_parcel(id=i, label=f"Đơn {i}", tracking_number=f"SPXVN00000000000{i}")
        for i in range(1, 8)
    ]
    assert list_pages(7) == 2
    assert list_pages(0) == 1
    first = format_parcel_list(parcels, TZ)
    assert "5. " in first
    assert "6. " not in first
    assert first.endswith("Trang 1/2")
    second = format_parcel_list(parcels, TZ, page=2)
    assert "6. " in second
    assert "7. " in second
    assert "1. " not in second


def test_parcel_card_appends_the_place_line():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0, progress=50)
    card = format_parcel_card(parcel, TZ, "📍 Kho Thanh Tri")
    assert card.endswith("Đã đến kho · 🕒 01/09 08:30\n📍 Kho Thanh Tri")
    assert format_parcel_card(parcel, TZ, None) == format_parcel_card(parcel, TZ)


def test_check_done_mentions_rebuilt_parcels_and_new_scripts():
    assert format_check_done(3, 1, 0) == texts.CHECK_DONE.format(checked=3, new_events=1)
    assert format_check_done(3, 1, 2, rebuilt=2, reloaded=1) == (
        texts.CHECK_DONE.format(checked=3, new_events=1)
        + texts.CHECK_REDETECTED.format(count=2)
        + texts.CHECK_REBUILT.format(count=2)
        + texts.CHECK_RELOADED.format(count=1)
    )


def test_place_texts_do_not_say_straight_line():
    assert "chim bay" not in texts.PLACE_LINE
    assert "chim bay" not in texts.MAP_CAPTION


def test_list_row_shows_where_the_parcel_is_and_how_far():
    parcel = make_parcel(label="Áo", last_status_text="Đã đến kho", last_event_at=T0)
    line = texts.LIST_PLACE_LINE.format(place="Quảng Đông", distance="~1960 km")
    text = format_parcel_list([parcel], TZ, places={1: line})
    assert "📦 Kiện hàng đã tới Quảng Đông · cách bạn ~1960 km" in text
    assert "Đã đến kho" not in text, "the hub line takes the place of the older status text"
    assert "🕒 01/09 08:30" in text, "the time of that last move stays"


def test_list_sections_split_finished_orders_from_the_rest():
    active = make_parcel(id=1, label="Áo")
    done = make_parcel(id=2, label="Quần", state="delivered")
    both = format_parcel_list([active, done], TZ)
    assert texts.LIST_SECTION_ACTIVE in both
    assert both.index(texts.LIST_SECTION_ACTIVE) < both.index(texts.LIST_SECTION_DONE)
    assert texts.LIST_SECTION_ACTIVE not in format_parcel_list([active], TZ), "one kind, no headers"


def test_sorting_keeps_finished_orders_last_in_every_mode():
    active = make_parcel(id=1, label="Zulu")
    done = make_parcel(id=2, label="Alpha", state="delivered")
    for mode in ("n", "c", "a"):
        assert sort_parcels([done, active], mode, {}) == [active, done]


def test_nearest_first_puts_unknown_distances_at_the_end():
    near = make_parcel(id=1, label="Gần")
    far = make_parcel(id=2, label="Xa")
    unknown = make_parcel(id=3, label="Không rõ")
    ordered = sort_parcels([far, unknown, near], "n", {1: 12.0, 2: 900.0})
    assert [parcel.id for parcel in ordered] == [1, 2, 3]


def test_alphabetical_and_carrier_sorts():
    spx = make_parcel(id=1, label="Zulu")
    ghn = make_parcel(id=2, label="Alpha", carrier="ghn", candidates=("ghn",))
    assert [p.id for p in sort_parcels([spx, ghn], "a", {})] == [2, 1]
    assert [p.id for p in sort_parcels([spx, ghn], "c", {})] == [2, 1], "GHN before SPX"


def test_status_sort_follows_the_stage_ladder():
    """Moving, then nearly there, then still being identified, then quiet, then finished."""
    new = unresolved(id=1, label="Mã mới")
    moving = make_parcel(id=2, label="Sạc", progress=50)
    near = make_parcel(id=3, label="Áo", progress=95)
    quiet = make_parcel(id=4, label="Cũ", state="stale")
    done = make_parcel(id=5, label="Xong", state="delivered")
    ordered = sort_parcels([done, quiet, near, moving, new], "s", {})
    assert [parcel.id for parcel in ordered] == [2, 3, 1, 4, 5]


def test_status_sort_puts_the_newest_movement_first_inside_a_stage():
    from datetime import timedelta

    older = make_parcel(id=1, label="A", progress=50, last_event_at=T0)
    newer = make_parcel(id=2, label="B", progress=50, last_event_at=T0 + timedelta(hours=5))
    silent = make_parcel(id=3, label="C", progress=50)
    ordered = sort_parcels([silent, older, newer], "s", {})
    assert [parcel.id for parcel in ordered] == [2, 1, 3]


def test_status_sort_heads_each_stage_that_has_parcels():
    moving = make_parcel(id=1, label="Sạc", progress=50)
    near = make_parcel(id=2, label="Áo", progress=95)
    text = format_parcel_list([moving, near], TZ, sort="s")
    assert text.index(texts.LIST_STAGE_MOVING) < text.index(texts.LIST_STAGE_NEAR)
    assert texts.LIST_STAGE_QUIET not in text, "a stage with nothing in it earns no heading"
    assert texts.LIST_SECTION_ACTIVE not in text, "stage headings replace the two-part split"


def test_the_other_sorts_keep_the_two_part_split():
    moving = make_parcel(id=1, label="Sạc", progress=50)
    done = make_parcel(id=2, label="Xong", state="delivered")
    text = format_parcel_list([moving, done], TZ)
    assert texts.LIST_SECTION_ACTIVE in text
    assert texts.LIST_STAGE_MOVING not in text


def test_grouped_updates_list_each_parcel_with_one_line():
    """One message, one update per parcel: no history dump, no per-parcel notification."""
    first = make_parcel(id=1, label="Áo", progress=95)
    second = make_parcel(id=2, label="Quần", carrier="ghn", candidates=("ghn",))
    text = format_updates(
        [
            Moved(first, ev(0, "Đang giao hàng", "Hà Nội")),
            Moved(second, ev(5, "Đã đến kho")),
        ],
        TZ,
    )
    assert text.startswith(texts.UPDATES_HEADER)
    assert "Đang giao hàng" in text
    assert "Đã đến kho" in text
    assert text.count("—") == 2, "exactly one update line per parcel"
    assert "Áo" in text and "Quần" in text


def test_grouped_updates_show_the_newest_event_only():
    parcel = make_parcel(id=1, label="Áo")
    text = format_updates([Moved(parcel, ev(30, "Mới nhất"))], TZ)
    assert "Mới nhất" in text
    assert texts.UPDATE_MORE.split("{")[0] not in text, "no 'and N earlier updates' tail"


def test_grouped_updates_carry_the_location_when_there_is_one():
    parcel = make_parcel(id=1, label="Áo")
    text = format_updates([Moved(parcel, ev(0, "Đã đến kho", "Đông Quản"))], TZ)
    assert "Đông Quản" in text
