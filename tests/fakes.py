from collections.abc import Mapping
from datetime import UTC, datetime, timedelta

from vn_parcel_bot.carriers.models import CarrierCode, CarrierError, TrackingEvent, TrackingResult
from vn_parcel_bot.carriers.registry import CarrierRegistry, CarrierSnapshot, current_snapshot

BASE_TIME = datetime(2026, 9, 1, 8, 0, tzinfo=UTC)


class FakeClock:
    def __init__(self, start: datetime) -> None:
        if start.tzinfo is None:
            raise ValueError("FakeClock needs an aware datetime")
        self._now = start

    def __call__(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta

    def set(self, value: datetime) -> None:
        self._now = value


class FakeCarrier:
    def __init__(
        self,
        code: CarrierCode,
        *,
        needs_phone: bool | None = None,
        display_name: str | None = None,
    ) -> None:
        info = current_snapshot().get(code)
        assert info is not None, code
        self.code = code
        self.needs_phone = info.needs_phone if needs_phone is None else needs_phone
        self.display_name = info.display_name if display_name is None else display_name
        self.results: dict[tuple[str, str | None], TrackingResult | CarrierError] = {}
        self.calls: list[tuple[str, str | None]] = []

    async def fetch(
        self, http: object, tracking_number: str, phone_last4: str | None = None
    ) -> TrackingResult:
        self.calls.append((tracking_number, phone_last4))
        value = self.results.get((tracking_number, phone_last4))
        if isinstance(value, CarrierError):
            raise value
        if value is None:
            return TrackingResult(carrier=self.code, tracking_number=tracking_number, found=False)
        return value


def fake_registry(clients: Mapping[str, object]) -> CarrierRegistry:
    # Keep the caller's dict (not a copy) so tests can swap a fake client mid-test.
    return CarrierRegistry(CarrierSnapshot(current_snapshot().modules, clients))


class FakeNotifier:
    def __init__(self, fail_with: Exception | None = None) -> None:
        self.fail_with = fail_with
        self.sent: list[tuple[int, str, bool]] = []

    async def send(self, chat_id: int, text: str, *, silent: bool = False) -> None:
        self.sent.append((chat_id, text, silent))
        if self.fail_with is not None:
            raise self.fail_with


def ev(
    minutes: int,
    description: str = "Đang vận chuyển",
    location: str | None = "Kho HCM",
    base: datetime = BASE_TIME,
) -> TrackingEvent:
    return TrackingEvent(
        time=base + timedelta(minutes=minutes), description=description, location=location
    )


def found(
    code: CarrierCode,
    tracking_number: str,
    *events: TrackingEvent,
    delivered: bool = False,
    returned: bool = False,
) -> TrackingResult:
    return TrackingResult(
        carrier=code,
        tracking_number=tracking_number,
        found=True,
        events=tuple(events),
        delivered=delivered,
        returned=returned,
    )
