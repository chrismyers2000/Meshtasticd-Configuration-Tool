"""
core/actions.py — systemctl operations, Python CLI install, set region, send message.
"""

from __future__ import annotations

import os
import re
import shutil
from typing import Callable, Optional

from core.utils import run_command, run_sudo, run_sudo_streaming, CommandResult

SERVICE = "meshtasticd"

# meshtasticd listens on TCP 4403 on localhost. Always talk to it explicitly:
# without --host the CLI scans USB serial ports first and would configure a
# plugged-in USB node (or hang on a USB-serial adapter) instead of the daemon.
CLI_HOST = "localhost"

# Connecting over TCP, fetching the node DB, and waiting for the node to
# reboot after a --set all take longer than a few seconds on a Pi.
CLI_TIMEOUT = 60

# Config.LoRaConfig.RegionCode, in enum order (index == numeric value).
# Source: meshtastic protobufs, verified against the installed CLI.
REGIONS = [
    "UNSET",    # 0
    "US",       # 1
    "EU_433",   # 2
    "EU_868",   # 3
    "CN",       # 4
    "JP",       # 5
    "ANZ",      # 6
    "KR",       # 7
    "TW",       # 8
    "RU",       # 9
    "IN",       # 10
    "NZ_865",   # 11
    "TH",       # 12
    "LORA_24",  # 13
    "UA_433",   # 14
    "UA_868",   # 15
    "MY_433",   # 16
    "MY_919",   # 17
    "SG_923",   # 18
    "PH_433",   # 19
    "PH_868",   # 20
    "PH_915",   # 21
    "ANZ_433",  # 22
    "KZ_433",   # 23
    "KZ_863",   # 24
    "NP_865",   # 25
    "BR_902",   # 26
]

_REGION_BY_NUMBER = {str(i): name for i, name in enumerate(REGIONS)}
_KNOWN_REGIONS = set(REGIONS)


# ---------------------------------------------------------------------------
# systemctl
# ---------------------------------------------------------------------------

def service_enable() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "enable", SERVICE])
    return result.success, result.output


def service_disable() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "disable", SERVICE])
    return result.success, result.output


def service_start() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "start", SERVICE])
    return result.success, result.output


def service_stop() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "stop", SERVICE])
    return result.success, result.output


def service_reset_failed() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "reset-failed", SERVICE + ".service"])
    return result.success, result.output


def service_status() -> tuple[bool, str]:
    result = run_sudo(["systemctl", "status", SERVICE, "--no-pager", "-l"])
    return result.success, result.output


def service_is_enabled() -> bool:
    result = run_command(["systemctl", "is-enabled", SERVICE], timeout=5)
    return result.stdout.strip() == "enabled"


def service_is_active() -> bool:
    result = run_command(["systemctl", "is-active", SERVICE], timeout=5)
    return result.stdout.strip() == "active"


# ---------------------------------------------------------------------------
# Python CLI install
# ---------------------------------------------------------------------------

def is_python3_available() -> bool:
    result = run_command(["python3", "--version"], timeout=5)
    return result.success


def is_pip3_available() -> bool:
    result = run_command(["pip3", "--version"], timeout=5)
    return result.success


def find_meshtastic_cli() -> Optional[str]:
    """
    Return the path of the meshtastic CLI executable, or None.

    Checks PATH first, then pipx's install location (~/.local/bin), which is
    not on PATH for a GUI launched from the desktop menu or for a shell that
    predates `pipx ensurepath`.
    """
    found = shutil.which("meshtastic")
    if found:
        return found
    candidate = os.path.expanduser("~/.local/bin/meshtastic")
    if os.path.isfile(candidate) and os.access(candidate, os.X_OK):
        return candidate
    return None


def is_meshtastic_cli_installed() -> bool:
    return find_meshtastic_cli() is not None


def _cli_cmd(*args: str) -> Optional[list[str]]:
    """Build a meshtastic CLI command line targeting the local daemon, or None if not installed."""
    cli = find_meshtastic_cli()
    if cli is None:
        return None
    return [cli, "--host", CLI_HOST, *args]


def _run_cli(*args: str) -> CommandResult:
    cmd = _cli_cmd(*args)
    if cmd is None:
        return CommandResult(
            returncode=-1, stdout="",
            stderr="meshtastic CLI not installed. Use 'Install Python CLI' first.",
        )
    return run_command(cmd, timeout=CLI_TIMEOUT)


def install_python_cli(
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Install meshtastic[cli] via pip3 with pipx fallback.
    Skips virtualenv (known to be problematic on Pi).
    Package-manager output is streamed to `log` as it happens.
    """
    _log(log, "Checking Python 3...")
    if not is_python3_available():
        _log(log, "Python 3 not found. Installing...")
        if not _apt_install_streaming(["python3"], log):
            _log(log, "ERROR: Failed to install python3.")
            return False
        _log(log, "Python 3 installed.")

    _log(log, "Checking pip3...")
    if not is_pip3_available():
        _log(log, "pip3 not found. Installing...")
        if not _apt_install_streaming(["python3-pip"], log):
            _log(log, "ERROR: Failed to install python3-pip.")
            return False
        _log(log, "pip3 installed.")

    _log(log, "Installing meshtastic[cli] via pip3...")
    result = _run_streaming_as_user(
        ["pip3", "install", "--upgrade", "meshtastic[cli]"], log,
    )

    if result.success:
        _log(log, "meshtastic CLI installed successfully.")
        return True

    # Check for externally-managed-environment error
    combined = (result.stdout + result.stderr).lower()
    if "externally-managed-environment" in combined or "externally managed" in combined:
        _log(log, "pip3 blocked by system. Trying pipx fallback...")
        return _install_via_pipx(log)

    _log(log, "ERROR: pip3 install failed.")
    return False


def _install_via_pipx(log: Optional[Callable[[str], None]] = None) -> bool:
    if shutil.which("pipx") is None:
        _log(log, "Installing pipx...")
        if not _apt_install_streaming(["pipx"], log):
            _log(log, "ERROR: Failed to install pipx.")
            return False

    _log(log, "Installing meshtastic[cli] via pipx...")
    result = _run_streaming_as_user(["pipx", "install", "meshtastic[cli]"], log)
    if not result.success:
        _log(log, "ERROR: pipx install failed.")
        return False

    _log(log, "Running pipx ensurepath...")
    run_command(["pipx", "ensurepath"], timeout=30)

    cli = find_meshtastic_cli()
    if cli:
        _log(log, f"meshtastic CLI installed via pipx at {cli}.")
    else:
        _log(log, "meshtastic CLI installed via pipx. You may need to restart your shell.")
    return True


def _apt_install_streaming(packages: list[str], log: Optional[Callable[[str], None]]) -> bool:
    result = run_sudo_streaming(
        ["apt-get", "install", "-y"] + packages,
        log=log,
        env={"DEBIAN_FRONTEND": "noninteractive"},
    )
    return result.success


def _run_streaming_as_user(cmd: list[str], log: Optional[Callable[[str], None]]) -> CommandResult:
    """Stream a non-sudo command's output to `log` (pip/pipx can run for minutes)."""
    import subprocess

    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            bufsize=1,
        )
        assert proc.stdout is not None
        for line in proc.stdout:
            line = line.rstrip("\n")
            lines.append(line)
            if log and line.strip():
                log(line)
        return CommandResult(returncode=proc.wait(), stdout="\n".join(lines), stderr="")
    except FileNotFoundError:
        return CommandResult(returncode=-1, stdout="", stderr=f"Command not found: {cmd[0]}")
    except Exception as exc:
        return CommandResult(returncode=-1, stdout="\n".join(lines), stderr=str(exc))


# ---------------------------------------------------------------------------
# Meshtastic CLI commands
# ---------------------------------------------------------------------------

def get_current_region() -> str:
    """Return the currently configured region, or 'Unknown'.

    The meshtastic CLI often exits non-zero even on success (connection warnings,
    etc.), so we parse the output regardless of exit code.
    Handles "lora.region: US", "lora.region: RegionCode.US" and "lora.region: 1".
    """
    result = _run_cli("--get", "lora.region")
    combined = result.stdout + result.stderr
    m = re.search(r"lora\.region:\s*(?:RegionCode\.)?([A-Za-z0-9_]+)", combined)
    if not m:
        return "Unknown"
    value = m.group(1).upper()
    if value.isdigit():
        return _REGION_BY_NUMBER.get(value, "Unknown")
    if value in _KNOWN_REGIONS:
        return value
    # A region newer than this tool's list: show it rather than hiding it.
    return value


def set_region(region: str, log: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """Set the Meshtastic lora region using the CLI."""
    _log(log, f"Setting region to {region}...")
    result = _run_cli("--set", "lora.region", region)
    if result.success:
        _log(log, f"Region set to {region}. The node will reboot to apply it.")
    else:
        _log(log, f"ERROR setting region.\n{result.output}")
    return result.success, result.output


def send_test_message(
    text: str = "Test message from MeshAdv Config Tool",
    log: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Send a text message to the default channel via the meshtastic CLI."""
    _log(log, f"Sending message: {text}")
    result = _run_cli("--sendtext", text)
    if result.success:
        _log(log, "Message sent.")
    else:
        _log(log, f"ERROR sending message.\n{result.output}")
    return result.success, result.output


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _log(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        callback(message)
