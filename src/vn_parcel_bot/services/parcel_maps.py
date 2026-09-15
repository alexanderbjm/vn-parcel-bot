"""Place lines, distances and map pictures for parcel messages."""

from html import escape

from vn_parcel_bot import texts
from vn_parcel_bot.config import Settings
from vn_parcel_bot.db.repo import Parcel, Repository, User
from vn_parcel_bot.services.formatting import parcel_title
from vn_parcel_bot.services.geo import Geocoder, clean_place, format_distance, haversine_km
from vn_parcel_bot.services.maps import TileSource, render_map


def _home(user: User) -> tuple[float, float] | None:
    if user.home_lat is None or user.home_lon is None:
        return None
    return user.home_lat, user.home_lon


class ParcelMaps:
    def __init__(
        self, repo: Repository, geocoder: Geocoder, tiles: TileSource, settings: Settings
    ) -> None:
        self._repo = repo
        self._geocoder = geocoder
        self._tiles = tiles
        self._settings = settings

    def _shown_place(self, parcel: Parcel) -> tuple[str, str] | None:
        """The cache key and the escaped display name of the parcel's hub."""
        if not self._settings.maps_enabled or not parcel.place:
            return None
        parts = clean_place(parcel.place)
        display = parts.display
        return (parts.key, escape(display, quote=False)) if display else None

    async def prepare(self, place: str) -> None:
        """Look a newly seen hub up, so place lines can show the distance."""
        if self._settings.maps_enabled:
            await self._geocoder.coordinates(place)

    async def place_line(self, parcel: Parcel, user: User) -> str | None:
        """The 📍 line for cards and updates. Reads cached coordinates only, never the network."""
        shown = self._shown_place(parcel)
        if shown is None:
            return None
        key, name = shown
        home = _home(user)
        cached = await self._repo.get_place(key) if home is not None else None
        if home is None or cached is None or cached.lat is None or cached.lon is None:
            return texts.PLACE_ONLY_LINE.format(place=name)
        km = haversine_km(home, (cached.lat, cached.lon))
        return texts.PLACE_LINE.format(place=name, distance=format_distance(km))

    async def photo(self, parcel: Parcel, user: User) -> tuple[bytes, str] | None:
        """The map picture and its caption; may look the hub up. Drawing failures raise MapError."""
        shown = self._shown_place(parcel)
        home = _home(user)
        if shown is None or home is None or parcel.place is None:
            return None
        point = await self._geocoder.coordinates(parcel.place)
        if point is None:
            return None
        png = await render_map(home, point, self._tiles)
        caption = texts.MAP_CAPTION.format(
            title=parcel_title(parcel),
            place=shown[1],
            distance=format_distance(haversine_km(home, point)),
        )
        return png, caption
