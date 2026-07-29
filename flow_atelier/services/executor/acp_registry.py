"""The ACP agent registry — a name instead of a launch command.

Every ACP agent is started by spawning a process, so a client has to know
some argv for each one. Upstream publishes that argv as data: the ACP
Registry (https://agentclientprotocol.com/get-started/registry) is a single
JSON document listing each agent's id and how to launch it. This module
turns that document into :class:`LaunchSpec` values, so a conduit can say
``tool: harness:gemini`` and never mention ``npx``.

A trimmed snapshot ships with flow-atelier (:data:`SNAPSHOT_PATH`) so the
lookup is offline and reproducible. ``atelier harness sync`` refreshes it
into the user's global atelier dir, which then takes precedence — the
network is opt-in, never on the run path.

Only the launch-relevant fields are kept, because a registry entry is a
launch command here and nothing more. flow-atelier is not an installer and
not a credential store: the user installs their agent and logs into it with
its own CLI, and we run the command they selected.

That still means running each agent the way it documents itself. An
``npx``/``uvx`` entry is the agent's own package manager fetching it on
first use — the same thing that happens when the user types the command in
a shell — so those are used as published. A ``binary`` entry names an
archive to download per platform; we never download or extract it, so the
spec becomes "run the CLI the user installed", found on PATH.
"""
from __future__ import annotations

import json
import platform
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.request import Request, urlopen

REGISTRY_URL = "https://cdn.agentclientprotocol.com/registry/v1/latest/registry.json"

# The snapshot shipped in the wheel. Read-only: `atelier harness sync` writes
# to the user's global dir instead, so a refresh never needs write access to
# an installed package.
SNAPSHOT_PATH = Path(__file__).with_name("acp_registry.json")
SNAPSHOT_FILENAME = "acp_registry.json"

# npx and uvx fetch the agent themselves on first use, so they work with no
# prior install; a binary distribution only runs if the user already put the
# CLI on PATH. Prefer the ones that can bootstrap themselves.
DISTRIBUTION_PREFERENCE = ("npx", "uvx", "binary")

# flow-atelier named three harnesses before the registry existed. Conduits in
# the wild use these names, so they stay as aliases for the registry ids.
LEGACY_HARNESS_ALIASES: dict[str, str] = {
    "claude-code": "claude-acp",
    "codex": "codex-acp",
    "copilot": "github-copilot-cli",
}


@dataclass(frozen=True)
class LaunchSpec:
    """How to start one ACP agent, resolved for the current platform.

    :param id: registry agent id, used as the ``harness:<id>`` tool name.
    :param name: human-readable agent name.
    :param version: the version the registry pins.
    :param description: one-line description from the registry.
    :param argv: the command to spawn.
    :param env: extra environment variables the agent needs.
    :param kind: which distribution this came from (npx/uvx/binary).
    """

    id: str
    name: str
    version: str
    description: str
    argv: tuple[str, ...]
    env: dict[str, str]
    kind: str


def platform_key() -> str:
    """Return this machine's registry platform key, e.g. ``darwin-aarch64``.

    :returns: ``<os>-<arch>`` using the registry's spelling; the parts stay
        unmapped when unrecognized, which simply finds no binary entry.
    """
    system = {"darwin": "darwin", "linux": "linux", "windows": "windows"}.get(
        platform.system().lower(), platform.system().lower()
    )
    machine = platform.machine().lower()
    arch = {
        "arm64": "aarch64",
        "aarch64": "aarch64",
        "x86_64": "x86_64",
        "amd64": "x86_64",
    }.get(machine, machine)
    return f"{system}-{arch}"


def _binary_argv(entry: dict[str, Any]) -> list[str]:
    """Build argv for a binary distribution from an already-installed CLI.

    The registry's ``cmd`` is a path inside the archive it would have you
    download (``./dist-package/cursor-agent``). Since we never download,
    only its basename is meaningful — the name the CLI installs itself as.

    :param entry: the platform's binary distribution entry.
    :returns: argv naming the binary and its ACP arguments.
    """
    # ponytail: basename heuristic. It matches for ~15 of the 17 binary
    # agents; the odd one embeds the platform in the filename
    # (`pool-darwin-arm64`) and needs an ATELIER_HARNESSES override.
    cmd = str(entry.get("cmd", "")).replace("\\", "/").rstrip("/")
    return [cmd.rsplit("/", 1)[-1], *entry.get("args", [])]


def _launch_spec(agent: dict[str, Any], plat: str) -> LaunchSpec | None:
    """Resolve one registry entry to a :class:`LaunchSpec`, if launchable here.

    :param agent: a registry agent record.
    :param plat: the platform key to resolve binary distributions against.
    :returns: the spec, or ``None`` when the agent ships no distribution this
        platform can start (e.g. binary-only, with no build for this arch).
    """
    distribution = agent.get("distribution") or {}
    for kind in DISTRIBUTION_PREFERENCE:
        entry = distribution.get(kind)
        if not entry:
            continue
        if kind == "binary":
            entry = entry.get(plat)
            if not entry:
                continue
            argv = _binary_argv(entry)
        else:
            # `package` is what npx/uvx actually run, and a snapshot can
            # reach here without one: trim_registry keeps an entry that has
            # only `args`/`env`. Indexing it would raise out of
            # `Atelier.__init__`, killing every command — including the
            # `atelier harness sync` that would replace the bad snapshot.
            package = entry.get("package")
            if not package:
                continue
            prefix = ["npx", "-y"] if kind == "npx" else ["uvx"]
            argv = [*prefix, package, *entry.get("args", [])]
        return LaunchSpec(
            id=agent["id"],
            name=agent.get("name", agent["id"]),
            version=agent.get("version", ""),
            description=agent.get("description", ""),
            argv=tuple(argv),
            env=dict(entry.get("env") or {}),
            kind=kind,
        )
    return None


def load_registry(user_snapshot: Path | None = None) -> dict[str, LaunchSpec]:
    """Load the agent registry, newest snapshot first.

    :param user_snapshot: optional path to a synced snapshot that supersedes
        the bundled one when it exists and parses.
    :returns: mapping of agent id -> :class:`LaunchSpec`, in registry order,
        excluding agents with nothing launchable on this platform.
    """
    raw: dict[str, Any] | None = None
    for path in (user_snapshot, SNAPSHOT_PATH):
        if path is None or not path.is_file():
            continue
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
            break
        except (OSError, ValueError):
            # A corrupt user snapshot must not take the bundled one down
            # with it; fall through and try the next candidate.
            continue
    if raw is None:
        return {}
    plat = platform_key()
    specs = {}
    for agent in raw.get("agents", []):
        spec = _launch_spec(agent, plat)
        if spec is not None:
            specs[spec.id] = spec
    return specs


def fetch_registry(url: str = REGISTRY_URL, timeout: float = 30.0) -> dict[str, Any]:
    """Download the live registry and trim it to the launch-relevant fields.

    :param url: registry JSON endpoint.
    :param timeout: socket timeout in seconds.
    :returns: a snapshot document ready to write.
    :raises OSError: when the download fails.
    :raises ValueError: when the response is not the expected JSON shape.
    """
    # The CDN 403s urllib's default User-Agent, so identify ourselves.
    from flow_atelier import __version__

    request = Request(url, headers={"User-Agent": f"flow-atelier/{__version__}"})
    with urlopen(request, timeout=timeout) as response:  # noqa: S310 — https URL
        raw = json.loads(response.read().decode("utf-8"))
    if not isinstance(raw, dict) or not isinstance(raw.get("agents"), list):
        raise ValueError(f"unexpected registry shape from {url}")
    return trim_registry(raw, source=url)


def trim_registry(raw: dict[str, Any], source: str = REGISTRY_URL) -> dict[str, Any]:
    """Keep only the fields needed to launch an agent.

    Drops archive URLs, checksums, icons and project metadata: we never
    download an agent, so carrying its release artifacts would be a large
    file that goes stale for no gain.

    :param raw: the full registry document.
    :param source: the URL it came from, recorded in the snapshot.
    :returns: the trimmed snapshot document.
    """
    agents = []
    for agent in raw["agents"]:
        distribution: dict[str, Any] = {}
        for kind, entry in (agent.get("distribution") or {}).items():
            if kind in ("npx", "uvx"):
                distribution[kind] = {
                    k: v for k, v in entry.items() if k in ("package", "args", "env")
                }
            elif kind == "binary":
                distribution[kind] = {
                    plat: {k: v for k, v in per.items() if k in ("cmd", "args", "env")}
                    for plat, per in entry.items()
                }
        if not distribution:
            continue
        agents.append(
            {
                "id": agent["id"],
                "name": agent.get("name", agent["id"]),
                "version": agent.get("version", ""),
                "description": agent.get("description", ""),
                "distribution": distribution,
            }
        )
    return {"source": source, "version": raw.get("version", ""), "agents": agents}


def write_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    """Write a snapshot document to ``path``, creating parent dirs.

    :param path: destination file.
    :param snapshot: the trimmed snapshot to serialize.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(snapshot, indent=2) + "\n", encoding="utf-8")
