import asyncio
import time

from copytrade_pm.pm_forward_continuous_transport import SerialWriter


def test_cancelled_waiter_does_not_cancel_writer_commit():
    async def run():
        completed = []

        def commit():
            time.sleep(0.03)
            completed.append("committed")

        async with SerialWriter(max_pending=1) as writer:
            job = asyncio.create_task(writer.submit(commit))
            await asyncio.sleep(0.01)
            job.cancel()
            await asyncio.gather(job, return_exceptions=True)
            assert completed == ["committed"]  # Safe to reopen a projection now.
        assert completed == ["committed"]

    asyncio.run(run())
