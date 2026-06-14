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
from enum import Enum

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


class StopDecision(str, Enum):
    """Verdict for whether a flow can be safely stopped from this host.

    Only ``stoppable`` means "send SIGTERM"; every other value is a refusal
    that the caller turns into a plain message and a non-zero exit.
    """

    stoppable = "stoppable"
    not_running = "not_running"
    crashed = "crashed"
    foreign_host = "foreign_host"
    no_pid = "no_pid"
    shared_runner = "shared_runner"


def stop_decision(progress: Progress, others: list[Progress]) -> StopDecision:
    """Decide whether ``progress``'s flow can be stopped by signalling its runner.

    Conservative by design: signalling ``runner_pid`` is coarse (it hits the
    whole process), so every case where that would be unsafe or pointless
    refuses rather than guesses. Checks run in order so the most specific
    reason wins.

    :param progress: the target flow's progress snapshot.
    :param others: progress snapshots of every *other* known flow, used to
        detect a runner process shared by more than one running flow (the
        scheduler-daemon case, where one PID owns several flows).
    :returns: a :class:`StopDecision`; only ``stoppable`` authorises a signal.
    """
    if progress.status != FlowStatus.running:
        return StopDecision.not_running
    if is_crashed(progress):
        return StopDecision.crashed
    if progress.runner_host != socket.gethostname():
        return StopDecision.foreign_host
    if progress.runner_pid is None:
        return StopDecision.no_pid
    try:
        os.kill(progress.runner_pid, 0)
    except ProcessLookupError:
        return StopDecision.crashed
    except (PermissionError, OSError):
        # Pid exists but we can't probe it cleanly — treat as foreign rather
        # than risk signalling a process we don't actually own.
        return StopDecision.foreign_host
    for other in others:
        if other.status != FlowStatus.running:
            continue
        if (
            other.runner_pid == progress.runner_pid
            and other.runner_host == progress.runner_host
        ):
            return StopDecision.shared_runner
    return StopDecision.stoppable
