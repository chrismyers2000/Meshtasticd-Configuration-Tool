"""
core/actions.py — systemctl operations, Python CLI install, set region, send message.
"""

from __future__ import annotations

import re
from typing import Callable, Optional

from core.utils import run_command, run_sudo, CommandResult

SERVICE = "meshtasticd"

REGIONS = [
    "UNSET", "US", "EU_433", "EU_868", "CN", "JP", "ANZ", "KR", "TW",
    "RU", "IN", "NZ_865", "TH", "UA_433", "UA_868", "MY_433", "MY_919", "SG_923",
]


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


def is_meshtastic_cli_installed() -> bool:
    result = run_command(["meshtastic", "--version"], timeout=10)
    return result.success


def install_python_cli(
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Install meshtastic[cli] via pip3 with pipx fallback.
    Skips virtualenv (known to be problematic on Pi).
    """
    _log(log, "Checking Python 3...")
    if not is_python3_available():
        _log(log, "Python 3 not found. Installing...")
        result = run_sudo(["apt-get", "install", "-y", "python3"], timeout=120)
        if not result.success:
            _log(log, f"ERROR: Failed to install python3.\n{result.stderr}")
            return False
        _log(log, "Python 3 installed.")

    _log(log, "Checking pip3...")
    if not is_pip3_available():
        _log(log, "pip3 not found. Installing...")
        result = run_sudo(["apt-get", "install", "-y", "python3-pip"], timeout=120)
        if not result.success:
            _log(log, f"ERROR: Failed to install python3-pip.\n{result.stderr}")
            return False
        _log(log, "pip3 installed.")

    _log(log, "Installing meshtastic[cli] via pip3...")
    result = run_command(
        ["pip3", "install", "--upgrade", "meshtastic[cli]"],
        timeout=120,
    )

    if result.success:
        _log(log, "meshtastic CLI installed successfully.")
        return True

    # Check for externally-managed-environment error
    combined = (result.stdout + result.stderr).lower()
    if "externally-managed-environment" in combined or "externally managed" in combined:
        _log(log, "pip3 blocked by system. Trying pipx fallback...")
        return _install_via_pipx(log)

    _log(log, f"ERROR: pip3 install failed.\n{result.output}")
    return False


def _install_via_pipx(log: Optional[Callable[[str], None]] = None) -> bool:
    _log(log, "Installing pipx...")
    result = run_sudo(["apt-get", "install", "-y", "pipx"], timeout=120)
    if not result.success:
        _log(log, f"ERROR: Failed to install pipx.\n{result.stderr}")
        return False

    _log(log, "Installing meshtastic[cli] via pipx...")
    result = run_command(["pipx", "install", "meshtastic[cli]"], timeout=120)
    if not result.success:
        _log(log, f"ERROR: pipx install failed.\n{result.output}")
        return False

    _log(log, "Running pipx ensurepath...")
    run_command(["pipx", "ensurepath"], timeout=30)

    _log(log, "meshtastic CLI installed via pipx. You may need to restart your shell.")
    return True


# ---------------------------------------------------------------------------
# Meshtastic CLI commands
# ---------------------------------------------------------------------------

_REGION_MAP = {
    "0": "UNSET", "1": "US", "2": "EU_433", "3": "EU_868",
    "4": "CN", "5": "JP", "6": "ANZ", "7": "KR", "8": "TW",
    "9": "RU", "10": "IN", "11": "NZ_865", "12": "TH",
    "13": "UA_433", "14": "UA_868", "15": "MY_433",
    "16": "MY_919", "17": "SG_923",
}


def get_current_region() -> str:
    """Return the currently configured region, or 'Unknown'.

    The meshtastic CLI often exits non-zero even on success (connection warnings,
    etc.), so we parse the output regardless of exit code.
    Handles both numeric codes (lora.region: 1) and name strings (RegionCode.US).
    """
    result = run_command(["meshtastic", "--get", "lora.region"], timeout=15)
    combined = result.stdout + result.stderr
    for line in combined.splitlines():
        if "lora.region" not in line and "region" not in line.lower():
            continue
        # Try numeric match first (e.g. "lora.region: 1")
        m = re.search(r":\s*(\d+)", line)
        if m:
            return _REGION_MAP.get(m.group(1), "Unknown")
        # Try name match (e.g. "RegionCode.US" or plain "US")
        if "UNSET" in line:
            return "UNSET"
        for region in REGIONS:
            if region == "UNSET":
                continue
            if region in line:
                return region
    return "Unknown"


def set_region(region: str, log: Optional[Callable[[str], None]] = None) -> tuple[bool, str]:
    """Set the Meshtastic lora region using the CLI."""
    _log(log, f"Setting region to {region}...")
    result = run_command(
        ["meshtastic", "--set", "lora.region", region],
        timeout=15,
    )
    if result.success:
        _log(log, f"Region set to {region}.")
    else:
        _log(log, f"ERROR setting region.\n{result.output}")
    return result.success, result.output


def send_test_message(
    text: str = "Test message from MeshAdv Config Tool",
    log: Optional[Callable[[str], None]] = None,
) -> tuple[bool, str]:
    """Send a text message to the default channel via the meshtastic CLI."""
    _log(log, f"Sending message: {text}")
    result = run_command(
        ["meshtastic", "--sendtext", text],
        timeout=15,
    )
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
