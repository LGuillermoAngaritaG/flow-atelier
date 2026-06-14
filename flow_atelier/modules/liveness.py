"""Derive a ``crashed`` display sense for flows whose runner process died.

A flow that is hard-killed (SIGKILL, OOM, reboot, lid-close) never runs the
engine's failure handler, so its ``progress.json`` stays frozen at
``status: running`` forever. These helpers reclassify such a flow as
``crashed`` for display only — never mutating the persisted status — and only
when the runner is *provably* dead on this same host. Every uncertain case
(foreign host, missing pid, live pid, permission error) stays ``running``, so a
genuinely-live or remote flow is never false-accused.
"""
from __future__ import annotations

import os
import socket

from flow_atelier.schemas.progress import FlowStatus, Progress


def is_crashed(progress: Progress) -> bool:
    """Return True only when a ``running`` flow's local runner is provably dead.

    :param progress: the flow's progress snapshot.
    :returns: True iff status is ``running``, the runner pid/host are recorded,
        the host matches this machine, and ``os.kill(pid, 0)`` proves the pid
        is gone. Any other case returns False (treated as still running).
    """
    if progress.status != FlowStatus.running:
        return False
    if progress.runner_pid is None:
        return False
    if progress.runner_host != socket.gethostname():
        return False
    try:
        os.kill(progress.runner_pid, 0)
    except ProcessLookupError:
        return True
    except (PermissionError, OSError):
        # Pid exists (possibly owned by another user) or the probe failed for
        # another reason — stay conservative and report still running.
        return False
    return False


def display_status(progress: Progress) -> str:
    """Return the display status string, mapping a dead runner to ``crashed``.

    :param progress: the flow's progress snapshot.
    :returns: ``"crashed"`` when :func:`is_crashed`, else the raw status value.
    """
    return "crashed" if is_crashed(progress) else progress.status.value
