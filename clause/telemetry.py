"""What this protocol writes down about itself.

Nothing in `clause/` ever configured logging. Uvicorn configures its own
loggers and nobody else's, so every `logger.info` in this codebase fell
through to Python's last resort handler: level WARNING, and a format that is
the message and nothing else -- no time, no level, no logger name. The service
also runs uvicorn at ``--log-level warning``, which reads as though it were
turning this protocol's logging down, and was in fact the only thing anyone
had ever set.

So none of it was written anywhere. Not "book restored", not "forgot %d
settled policies", not a carrier being vetted, not an operator signing in,
not a refusal. The error reference the interface hands a person on a 500 was
generated and then never printed against anything.

That matters most for the one question this product has to be able to answer
six months later: why did policy X not pay. The chain's readings are
deliberately not persisted, so the answer has to come from what was written
down at the time or it does not come at all.

Configured here rather than in cli.py so that the same call serves the
service, a script, and anyone importing the package -- and so that the level
this protocol writes at is its own setting and not a side effect of uvicorn's.
"""

from __future__ import annotations

import logging
import logging.config
import os
import sys

#: What a line looks like. The logger's name is in it because "clause.chain"
#: and "clause.api" answer very different questions and a bare message does
#: not say which one is speaking.
FORMAT = "%(asctime)s %(levelname)-7s %(name)s %(message)s"
WHEN = "%Y-%m-%dT%H:%M:%S%z"

#: The default. INFO because the lines this codebase writes at INFO are the
#: record of what it did -- a book restored, a policy forgotten, a company
#: activated -- and a record kept at WARNING is a record of failures only.
DEFAULT_LEVEL = "INFO"

_configured = False


def configure(level: str | None = None, *, force: bool = False) -> str:
    """Set this package's logging up once. Returns the level in force.

    ``CLAUSE_LOG_LEVEL`` overrides the default, and an unreadable value is
    reported and ignored rather than silently dropping the service to a level
    nobody chose.
    """
    global _configured
    if _configured and not force:
        return logging.getLevelName(logging.getLogger("clause").getEffectiveLevel())

    wanted = (level or os.environ.get("CLAUSE_LOG_LEVEL") or DEFAULT_LEVEL).upper()
    if wanted not in ("CRITICAL", "ERROR", "WARNING", "INFO", "DEBUG"):
        print(f"clause: CLAUSE_LOG_LEVEL={wanted!r} is not a level; using "
              f"{DEFAULT_LEVEL}", file=sys.stderr)
        wanted = DEFAULT_LEVEL

    handler = logging.StreamHandler(sys.stderr)
    handler.setFormatter(logging.Formatter(FORMAT, datefmt=WHEN))

    logger = logging.getLogger("clause")
    # Replace rather than add, so calling this twice does not double every line.
    for existing in list(logger.handlers):
        logger.removeHandler(existing)
    logger.addHandler(handler)
    logger.setLevel(wanted)
    # This package's lines are its own. Letting them propagate would print them
    # a second time wherever the root logger has a handler, which under uvicorn
    # it does.
    logger.propagate = False

    _configured = True
    return wanted
