from vn_parcel_bot.carriers.http import DEFAULT_HEADERS, make_http_client


async def test_client_defaults(settings):
    async with make_http_client(settings) as client:
        assert client.timeout.connect == settings.http_timeout_seconds
        assert client.headers["User-Agent"] == DEFAULT_HEADERS["User-Agent"]
        assert client.headers["Accept-Language"].startswith("vi-VN")
        assert client.follow_redirects is True
