
import datetime as _dt

# A departure two weeks out: flight subjects must name a date that is still
# ahead, whenever the suite runs.
FLIGHT_DATE = (_dt.date.today() + _dt.timedelta(days=14)).isoformat()


def start_cover(chain, policy) -> None:
    """Run the chain forward to the day a policy's cover starts.

    Every peril waits out its own forecast before the cover begins, so a test
    that attests a reading the moment it has bought would be measuring the
    waiting period rather than the thing it means to measure. The wait itself
    is tested in tests/test_waiting.py.
    """
    while chain.world_now(policy) < policy.starts_at:
        chain.produce_block()


def cover_has_started(policy) -> None:
    """Move a policy's start back to the day it was bought.

    Cover waits out its peril's forecast before it begins, and for a policy a
    person bought that wait runs in real days rather than the demonstration's
    accelerated ones. A test about what happens once the cover has started says
    so here instead of waiting a week for it.
    """
    policy.starts_at = policy.bought_at
