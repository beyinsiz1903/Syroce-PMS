"""Small process-role helpers shared by Celery entry points.

Celery Beat only needs the static task names in ``beat_schedule``. Importing
``celery_tasks`` in that process loads the complete worker dependency graph for
no operational benefit, which is expensive on the 4 GiB Droplet profile.
"""

from __future__ import annotations

import os
from collections.abc import Mapping


def should_import_task_implementations(
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Return whether this process must register executable task bodies."""

    source = os.environ if environ is None else environ
    return source.get("CELERY_PROCESS_ROLE", "worker").strip().lower() != "beat"
