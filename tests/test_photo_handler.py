import asyncio
from datetime import UTC, datetime
from types import SimpleNamespace

import httpx
import pytest
from telegram.error import TelegramError

from tests.fakes import FakeCarrier, fake_registry
from vn_parcel_bot import texts
from vn_parcel_bot.bot.deps import Deps
from vn_parcel_bot.bot.handlers_user import (
    PENDING_LOCATION,
    PENDING_PHONE,
    photo_message,
    text_message,
)
from vn_parcel_bot.config import Settings
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller
from vn_parcel_bot.services.vision import VisionResult

T0 = datetime(2026, 9, 1, tzinfo=UTC)
SPX = "SPXVN000000000001"
JT = "840000000001"
ORDER = "500000000000001"


class FakeFile:
    def __init__(self, data: bytes):
        self.data = data

    async def download_as_bytearray(self) -> bytearray:
        return bytearray(self.data)


class FakeBot:
    def __init__(self, data: bytes = b"fake-image-bytes", fail: bool = False):
        self.data = data
        self.fail = fail
        self.requested: list[str] = []

    async def get_file(self, file_id: str) -> FakeFile:
        self.requested.append(file_id)
        if self.fail:
            raise TelegramError("download failed")
        return FakeFile(self.data)


class FakeNotifier:
    async def send(self, *args, **kwargs):
        pass


class FakeVisionEngine:
    def __init__(self, is_configured=True, result=None, delay=0.0):
        self._is_configured = is_configured
        self._result = result or VisionResult()
        self.delay = delay
        self.analyzed: list[tuple[bytes, str]] = []
        self.active = 0
        self.max_active = 0

    @property
    def is_configured(self) -> bool:
        return self._is_configured

    async def analyze_image(self, image_bytes: bytes, media_type: str = "image/jpeg"):
        self.analyzed.append((image_bytes, media_type))
        self.active += 1
        self.max_active = max(self.max_active, self.active)
        try:
            if self.delay:
                await asyncio.sleep(self.delay)
            return self._result
        finally:
            self.active -= 1


class FakeChat:
    async def send_action(self, action):
        pass


class MessageRecorder:
    def __init__(self, photo=None, document=None, caption=None, text=None):
        self.photo = photo
        self.document = document
        self.caption = caption
        self.text = text
        self.texts: list[str] = []

    async def reply_text(self, text, **kwargs):
        self.texts.append(text)


def photo(caption=None):
    return MessageRecorder(photo=[SimpleNamespace(file_id="p1")], caption=caption)


@pytest.fixture
async def deps(settings: Settings):
    repo = await Repository.open(":memory:")
    await repo.upsert_user(111, now=T0, is_allowed=True, is_admin=True)
    carriers = {"spx": FakeCarrier("spx"), "jt": FakeCarrier("jt", needs_phone=True)}
    http = httpx.AsyncClient()
    registry = fake_registry(carriers)
    parcels = ParcelService(repo, registry, http, settings, lambda: T0)
    poller = Poller(repo, registry, http, FakeNotifier(), settings, lambda: T0)
    yield Deps(settings, repo, http, parcels, poller, FakeNotifier(), vision=FakeVisionEngine())
    await http.aclose()
    await repo.close()


def make_update(message: MessageRecorder, user_id: int = 111):
    return SimpleNamespace(
        effective_user=SimpleNamespace(id=user_id, full_name="User"),
        effective_message=message,
        effective_chat=FakeChat(),
    )


def make_context(deps: Deps, bot: FakeBot | None = None):
    return SimpleNamespace(
        bot_data={"deps": deps, "settings": deps.settings}, user_data={}, bot=bot or FakeBot()
    )


async def test_photo_codes_drop_a_waiting_location_request(deps):
    deps.vision = FakeVisionEngine(result=VisionResult(tracking_codes=(SPX, JT)))
    context = make_context(deps)
    context.user_data[PENDING_LOCATION] = {"map_parcel": 1}
    await photo_message(make_update(photo()), context)
    assert PENDING_LOCATION not in context.user_data


async def test_photo_engine_missing_or_not_configured(deps):
    deps.vision = FakeVisionEngine(is_configured=False)
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert msg.texts == [texts.VISION_NOT_CONFIGURED]
    assert deps.vision.analyzed == []


async def test_photo_engine_reports_not_configured(deps):
    deps.vision = FakeVisionEngine(result=VisionResult(error="not_configured"))
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert msg.texts == [texts.VISION_NOT_CONFIGURED]


async def test_photo_error_reply_is_generic(deps):
    deps.vision = FakeVisionEngine(result=VisionResult(error="cli_error"))
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert msg.texts == [texts.VISION_ERROR]


async def test_photo_download_failure(deps):
    msg = photo()
    await photo_message(make_update(msg), make_context(deps, FakeBot(fail=True)))
    assert msg.texts == [texts.VISION_ERROR]
    assert deps.vision.analyzed == []


async def test_photo_result_summary_is_logged_without_codes(deps, caplog):
    caplog.set_level("INFO")
    deps.vision = FakeVisionEngine(result=VisionResult(order_ids=(ORDER,), product_name="Ốp lưng"))
    await photo_message(make_update(photo()), make_context(deps))
    deps.vision = FakeVisionEngine()
    await photo_message(make_update(photo()), make_context(deps))
    assert "photo read codes=0 order_ids=1 product=yes" in caplog.text
    assert "photo read codes=0 order_ids=0 product=no" in caplog.text
    assert ORDER not in caplog.text
    assert "Ốp lưng" not in caplog.text


async def test_photo_no_data(deps):
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert msg.texts == [texts.VISION_NO_DATA]


async def test_photo_code_added_with_product_label(deps):
    deps.vision = FakeVisionEngine(
        result=VisionResult(
            tracking_codes=(SPX,), carrier="SPX Express", product_name="Tai nghe Bluetooth +1"
        )
    )
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert len(msg.texts) == 1
    reply = msg.texts[0]
    assert "Nhận diện từ hình ảnh" in reply
    assert "Tai nghe Bluetooth +1" in reply
    assert f'<span class="tg-spoiler">{SPX}</span>' in reply
    parcel = await deps.repo.find_parcel(111, SPX)
    assert parcel.label == "Tai nghe Bluetooth +1"


async def test_photo_duplicate_fills_missing_label(deps):
    user = await deps.repo.get_user(111)
    await deps.parcels.add(user, SPX)
    deps.vision = FakeVisionEngine(
        result=VisionResult(tracking_codes=(SPX,), product_name="Ốp lưng")
    )
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert (await deps.repo.find_parcel(111, SPX)).label == "Ốp lưng"
    assert "Bạn đã theo dõi đơn" in msg.texts[0]


async def test_photo_needs_phone_keeps_label_for_pending_reply(deps):
    deps.vision = FakeVisionEngine(
        result=VisionResult(tracking_codes=(JT,), product_name="Ốp lưng")
    )
    context = make_context(deps)
    await photo_message(make_update(photo()), context)
    pending = context.user_data[PENDING_PHONE]
    assert (pending["code"], pending["label"]) == (JT, "Ốp lưng")
    await text_message(make_update(MessageRecorder(text="1234")), context)
    parcel = await deps.repo.find_parcel(111, JT)
    assert parcel.label == "Ốp lưng"
    assert parcel.phone_last4 == "1234"


async def test_photo_caption_supplies_phone(deps):
    deps.vision = FakeVisionEngine(result=VisionResult(tracking_codes=(JT,), carrier="J&T"))
    msg = photo(caption="SĐT 1234")
    await photo_message(make_update(msg), make_context(deps))
    assert "***1234" in msg.texts[0]
    assert (await deps.repo.find_parcel(111, JT)).phone_last4 == "1234"


async def test_photo_several_codes(deps):
    deps.vision = FakeVisionEngine(
        result=VisionResult(tracking_codes=(SPX, JT), product_name="Tai nghe")
    )
    msg = photo()
    context = make_context(deps)
    await photo_message(make_update(msg), context)
    assert len(msg.texts) == 2
    assert SPX in msg.texts[0]
    assert JT in msg.texts[1]
    assert PENDING_PHONE not in context.user_data
    assert (await deps.repo.find_parcel(111, SPX)).label == "Tai nghe"


async def test_photo_order_number_only_stores_nothing(deps):
    deps.vision = FakeVisionEngine(result=VisionResult(order_ids=(ORDER,), product_name="Ốp lưng"))
    msg = photo()
    await photo_message(make_update(msg), make_context(deps))
    assert len(msg.texts) == 1
    assert ORDER in msg.texts[0]
    assert "mã đơn hàng" in msg.texts[0]
    assert "Ốp lưng" in msg.texts[0]
    assert "17track" in msg.texts[0].lower()
    assert await deps.repo.find_parcel(111, ORDER) is None


@pytest.mark.parametrize(
    "document",
    [
        SimpleNamespace(file_id="d1", mime_type="application/pdf", file_size=100),
        SimpleNamespace(file_id="d1", mime_type="image/png", file_size=6 * 1024 * 1024),
        SimpleNamespace(file_id="d1", mime_type=None, file_size=100),
    ],
    ids=["pdf", "too-big", "no-mime"],
)
async def test_document_rejected_without_download(deps, document):
    bot = FakeBot()
    msg = MessageRecorder(document=document)
    await photo_message(make_update(msg), make_context(deps, bot))
    assert msg.texts == [texts.VISION_UNSUPPORTED_IMAGE]
    assert bot.requested == []
    assert deps.vision.analyzed == []


async def test_document_image_is_analyzed_with_its_type(deps):
    document = SimpleNamespace(file_id="d1", mime_type="image/png", file_size=1000)
    await photo_message(make_update(MessageRecorder(document=document)), make_context(deps))
    assert deps.vision.analyzed == [(b"fake-image-bytes", "image/png")]


async def test_photos_from_one_user_run_one_at_a_time(deps):
    deps.vision = FakeVisionEngine(delay=0.05)
    context = make_context(deps)
    await asyncio.gather(
        photo_message(make_update(photo()), context), photo_message(make_update(photo()), context)
    )
    assert len(deps.vision.analyzed) == 2
    assert deps.vision.max_active == 1
