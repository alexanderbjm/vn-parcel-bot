import math
import re
from dataclasses import dataclass

from vn_parcel_bot import texts
from vn_parcel_bot.services.geo_provinces import PROVINCES

_LEADING_NUMBER = re.compile(r"^\d{1,3}-")
_POST_OFFICE = re.compile(r"^bưu cục\s+", re.IGNORECASE)
_HUB_WORDS = frozenset({"hub", "soc", "mega", "lm", "kho", "bc"})
EARTH_RADIUS_KM = 6371.0


@dataclass(frozen=True)
class PlaceParts:
    code: str | None
    district: str | None

    @property
    def key(self) -> str:
        return f"{self.code or ''}|{self.district or ''}"

    @property
    def display(self) -> str | None:
        if self.code is not None:
            return f"Kho {self.district or PROVINCES[self.code][0]}"
        return self.district


def _is_hub_suffix(token: str) -> bool:
    return token.isdigit() or (len(token) == 1 and token.isalpha())


def clean_place(raw: str) -> PlaceParts:
    """Split hub text like "21-HNI Thanh Tri 2 Hub" into a province code and a district."""
    text = _POST_OFFICE.sub("", _LEADING_NUMBER.sub("", " ".join(raw.split())))
    tokens = text.split(" ") if text else []
    code = tokens.pop(0) if tokens and tokens[0] in PROVINCES else None
    dropped = False
    while tokens and tokens[-1].casefold() in _HUB_WORDS:
        tokens.pop()
        dropped = True
    while dropped and tokens and _is_hub_suffix(tokens[-1]):
        tokens.pop()
    return PlaceParts(code, " ".join(tokens) or None)


def haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    lat1, lon1, lat2, lon2 = map(math.radians, (*a, *b))
    h = (
        math.sin((lat2 - lat1) / 2) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin((lon2 - lon1) / 2) ** 2
    )
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(h))


def format_distance(km: float) -> str:
    if km < 1:
        return texts.DISTANCE_UNDER_1KM
    if km < 10:
        return f"~{km:.1f} km"
    return f"~{round(km)} km"
