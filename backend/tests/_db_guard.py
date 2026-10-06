"""
Refuses to run suites that delete whole tables on the project's real database.

contentos_dev holds the user's real publications and job history. A suite that
runs a global DELETE must point at a scratch copy instead, e.g.:

    DATABASE_URL=<same URL with /contentos_scratch> python -m unittest ...

Set CONTENTOS_ALLOW_GLOBAL_DELETE=1 only when you have confirmed the target.
"""
import os
import unittest

from app.config import settings


def refuse_if_real_database() -> None:
    if os.environ.get("CONTENTOS_ALLOW_GLOBAL_DELETE") == "1":
        return
    url = settings.database_url
    if "/contentos_dev" in url and "/contentos_scratch" not in url:
        raise unittest.SkipTest(
            "Refusing to run: this suite deletes scheduled_jobs globally and the "
            "target is contentos_dev. Point DATABASE_URL at a scratch copy."
        )
