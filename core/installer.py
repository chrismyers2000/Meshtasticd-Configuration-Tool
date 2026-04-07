"""
core/installer.py — Install and remove meshtasticd via apt.
Supports 32-bit (Raspbian) and 64-bit (Debian) repos, multiple channels.
"""

from __future__ import annotations

import glob
import os
from typing import Callable, Optional

from core.hardware import OsInfo
from core.utils import run_command, run_sudo, CommandResult

CHANNELS = ["beta", "alpha", "daily"]

# OBS repository base URLs
REPO_URL_TEMPLATE = (
    "http://download.opensuse.org/repositories/network:/Meshtastic:/{channel}/{arch_label}/"
)
KEY_URL_TEMPLATE = (
    "https://download.opensuse.org/repositories/network:Meshtastic:{channel}/{arch_label}/Release.key"
)
SOURCES_DIR = "/etc/apt/sources.list.d"
GPG_DIR = "/etc/apt/trusted.gpg.d"


def _sources_file(channel: str) -> str:
    return os.path.join(SOURCES_DIR, f"network:Meshtastic:{channel}.list")


def _gpg_file(channel: str) -> str:
    return os.path.join(GPG_DIR, f"network_Meshtastic_{channel}.gpg")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def is_installed() -> bool:
    """Return True if meshtasticd is currently installed."""
    result = run_command(
        ["dpkg-query", "-W", "-f=${Status}", "meshtasticd"],
        timeout=10,
    )
    return "install ok installed" in result.stdout


def install(
    channel: str,
    os_info: OsInfo,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Full install sequence:
    1. Remove any stale apt source files for other channels
    2. Add the apt source list
    3. Add the GPG key
    4. apt-get update
    5. apt-get install meshtasticd
    """
    if channel not in CHANNELS:
        _log(log, f"ERROR: Unknown channel '{channel}'. Valid: {CHANNELS}")
        return False

    arch_label = os_info.arch_label
    _log(log, f"Installing meshtasticd ({channel}) for {arch_label}...")

    # Step 1: clean up stale sources for other channels
    _remove_stale_sources(channel, log)

    # Step 2: add apt source
    if not _add_apt_source(channel, arch_label, log):
        return False

    # Step 3: add GPG key
    if not _add_gpg_key(channel, arch_label, log):
        return False

    # Step 4: apt-get update
    if not _apt_update(log):
        _log(log, "Cleaning up due to apt update failure...")
        _remove_apt_artifacts(channel)
        return False

    # Step 5: apt-get install
    if not _apt_install(log):
        _log(log, "Install failed.")
        return False

    _log(log, "meshtasticd installed successfully.")
    return True


def remove(log: Optional[Callable[[str], None]] = None) -> bool:
    """Purge meshtasticd and remove apt source artifacts."""
    _log(log, "Removing meshtasticd (purge)...")
    if not _apt_purge(log):
        return False

    _log(log, "Cleaning up apt sources...")
    # Remove sources for all channels
    for channel in CHANNELS:
        _remove_apt_artifacts(channel)

    _log(log, "meshtasticd removed.")
    return True


# ---------------------------------------------------------------------------
# Internal steps
# ---------------------------------------------------------------------------

def _remove_stale_sources(
    keep_channel: str,
    log: Optional[Callable[[str], None]] = None,
) -> None:
    """Remove apt source files for any channel other than keep_channel."""
    pattern = os.path.join(SOURCES_DIR, "network:Meshtastic:*.list")
    for path in glob.glob(pattern):
        if f"network:Meshtastic:{keep_channel}.list" not in path:
            _log(log, f"  Removing stale source: {os.path.basename(path)}")
            run_sudo(["rm", "-f", path])


def _add_apt_source(
    channel: str,
    arch_label: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    repo_url = REPO_URL_TEMPLATE.format(channel=channel, arch_label=arch_label)
    deb_line = f"deb {repo_url} /"
    sources_file = _sources_file(channel)

    _log(log, f"  Adding apt source: {repo_url}")
    result = run_command(
        ["sudo", "tee", sources_file],
        input_text=deb_line + "\n",
        timeout=15,
    )
    if not result.success:
        _log(log, f"  ERROR: Could not write {sources_file}\n{result.stderr}")
        return False
    return True


def _add_gpg_key(
    channel: str,
    arch_label: str,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    key_url = KEY_URL_TEMPLATE.format(channel=channel, arch_label=arch_label)
    gpg_file = _gpg_file(channel)

    _log(log, f"  Fetching GPG key from {key_url}")

    # curl | gpg --dearmor | sudo tee
    # We chain this via shell=False by using subprocess pipes manually
    import subprocess

    try:
        curl_proc = subprocess.Popen(
            ["curl", "-fsSL", key_url],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        gpg_proc = subprocess.Popen(
            ["gpg", "--dearmor"],
            stdin=curl_proc.stdout,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        curl_proc.stdout.close()
        gpg_out, gpg_err = gpg_proc.communicate(timeout=30)

        if gpg_proc.returncode != 0:
            _log(log, f"  ERROR: gpg --dearmor failed.\n{gpg_err.decode()}")
            return False

        # Write via sudo tee
        tee_proc = subprocess.Popen(
            ["sudo", "tee", gpg_file],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
        )
        _, tee_err = tee_proc.communicate(input=gpg_out, timeout=15)
        if tee_proc.returncode != 0:
            _log(log, f"  ERROR: Could not write GPG file.\n{tee_err.decode()}")
            return False

    except Exception as exc:
        _log(log, f"  ERROR during GPG key setup: {exc}")
        return False

    _log(log, "  GPG key added.")
    return True


def _apt_update(log: Optional[Callable[[str], None]] = None) -> bool:
    _log(log, "Running apt-get update...")
    result = run_sudo(["apt-get", "update"], timeout=180)
    if result.stdout.strip():
        _log(log, result.stdout)
    if not result.success:
        _log(log, f"ERROR: apt-get update failed.\n{result.stderr}")
        return False
    return True


def _apt_install(log: Optional[Callable[[str], None]] = None) -> bool:
    _log(log, "Installing meshtasticd...")
    result = run_sudo(
        ["apt-get", "install", "-y", "meshtasticd"],
        timeout=300,
    )
    if result.stdout.strip():
        _log(log, result.stdout)
    if not result.success:
        _log(log, f"ERROR: apt-get install failed.\n{result.stderr}")
        return False
    return True


def _apt_purge(log: Optional[Callable[[str], None]] = None) -> bool:
    result = run_sudo(
        ["apt-get", "purge", "-y", "meshtasticd"],
        timeout=120,
    )
    if result.stdout.strip():
        _log(log, result.stdout)
    if not result.success:
        _log(log, f"ERROR: apt-get purge failed.\n{result.stderr}")
        return False
    return True


def _remove_apt_artifacts(channel: str) -> None:
    """Remove the apt .list and .gpg files for the given channel."""
    for path in [_sources_file(channel), _gpg_file(channel)]:
        run_sudo(["rm", "-f", path])


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _log(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        callback(message)
