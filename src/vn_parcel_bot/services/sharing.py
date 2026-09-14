import secrets

from vn_parcel_bot.db.repo import Parcel, Repository

SHARE_KEY = "share:"
SHARE_OF_KEY = "share-of:"


async def share_token(repo: Repository, parcel_id: int) -> str:
    existing = await repo.get_meta(f"{SHARE_OF_KEY}{parcel_id}")
    if existing and await repo.get_meta(f"{SHARE_KEY}{existing}") == str(parcel_id):
        return existing
    token = secrets.token_urlsafe(9)
    await repo.set_meta(f"{SHARE_KEY}{token}", str(parcel_id))
    await repo.set_meta(f"{SHARE_OF_KEY}{parcel_id}", token)
    return token


async def shared_parcel(repo: Repository, token: str) -> Parcel | None:
    value = await repo.get_meta(f"{SHARE_KEY}{token}")
    if value is None or not value.isdigit():
        return None
    return await repo.get_parcel(int(value))
