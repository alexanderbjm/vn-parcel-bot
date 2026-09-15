from dataclasses import dataclass

import httpx
from telegram.ext import ContextTypes

from vn_parcel_bot.bot.notifier import TelegramNotifier
from vn_parcel_bot.carriers.registry import CarrierRegistry
from vn_parcel_bot.config import Settings
from vn_parcel_bot.db.repo import Repository
from vn_parcel_bot.services.digest import DigestService
from vn_parcel_bot.services.parcel_maps import ParcelMaps
from vn_parcel_bot.services.parcels import ParcelService
from vn_parcel_bot.services.poller import Poller
from vn_parcel_bot.services.vision import VisionEngine


@dataclass
class Deps:
    settings: Settings
    repo: Repository
    http: httpx.AsyncClient
    parcels: ParcelService
    poller: Poller
    notifier: TelegramNotifier
    vision: VisionEngine | None = None
    digests: DigestService | None = None
    registry: CarrierRegistry | None = None
    maps: ParcelMaps | None = None


def get_deps(context: ContextTypes.DEFAULT_TYPE) -> Deps:
    return context.bot_data["deps"]
