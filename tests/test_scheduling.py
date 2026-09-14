from dataclasses import replace
from datetime import time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from vn_parcel_bot.bot.app import carrier_modules_job, digest_job, poll_job, schedule_jobs


class FakeJobQueue:
    def __init__(self):
        self.repeating = []
        self.daily = []

    def run_repeating(self, callback, **kwargs):
        self.repeating.append((callback, kwargs))

    def run_daily(self, callback, **kwargs):
        self.daily.append((callback, kwargs))


def test_schedule_jobs_registers_poll_and_four_digests(settings):
    queue = FakeJobQueue()
    schedule_jobs(queue, settings)
    assert [(callback, kwargs["name"]) for callback, kwargs in queue.repeating] == [
        (poll_job, "poll"),
        (carrier_modules_job, "carrier modules"),
    ]
    assert queue.repeating[1][1]["interval"] == 30
    tz = ZoneInfo("Asia/Ho_Chi_Minh")
    assert [kwargs["time"] for _, kwargs in queue.daily] == [
        time(7, tzinfo=tz),
        time(12, tzinfo=tz),
        time(19, tzinfo=tz),
        time(22, tzinfo=tz),
    ]
    assert all(kwargs["time"].tzinfo == tz for _, kwargs in queue.daily)
    assert all(callback is digest_job for callback, _ in queue.daily)
    assert [kwargs["name"] for _, kwargs in queue.daily] == [
        "digest 07:00",
        "digest 12:00",
        "digest 19:00",
        "digest 22:00",
    ]


def test_schedule_jobs_without_digests(settings):
    queue = FakeJobQueue()
    schedule_jobs(queue, replace(settings, digest_times=()))
    assert queue.daily == []
    assert len(queue.repeating) == 2


async def test_digest_job_runs_the_service():
    calls = []

    class Digests:
        async def send_all(self):
            calls.append(True)
            return 1

    context = SimpleNamespace(bot_data={"deps": SimpleNamespace(digests=Digests())})
    await digest_job(context)
    assert calls == [True]
