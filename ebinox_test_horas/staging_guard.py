"""Fail-closed staging database names for the Ebinox Odoo.sh project.

Odoo.sh names staging builds `{project}-{branch}-{id}`, e.g. ebinox-staging-36784685.
Production of this project is the database `ebinox`. That name must never pass.
"""

from __future__ import annotations

import re

STAGING_DB_PATTERN = re.compile(r"^ebinox-staging-\d+$")
BLOCKED_DATABASES = frozenset({"ebinox"})


def is_allowed_staging_database(name: str | None) -> bool:
    database = (name or "").strip()
    if not database or database in BLOCKED_DATABASES:
        return False
    return STAGING_DB_PATTERN.fullmatch(database) is not None
