"""
core/installer.py — Install and remove meshtasticd via apt.
Supports 32-bit (Raspbian) and 64-bit (Debian) repos, multiple channels.
"""

from __future__ import annotations

import glob
import os
import tempfile
from typing import Callable, Optional

from core.hardware import OsInfo
from core.utils import run_command, run_sudo, run_sudo_streaming

# apt must never be interrupted by a timeout (a killed dpkg leaves the package
# database half-updated), and debconf must never wait on a prompt nobody can see.
_APT_ENV = {"DEBIAN_FRONTEND": "noninteractive"}

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

    # Download → dearmor → install, each step checked separately so the user
    # sees the real cause (a 404 for an unsupported OS label, no network, ...)
    # rather than gpg complaining about empty input.
    tmp_dir = tempfile.mkdtemp(prefix="meshadv-key-")
    armored = os.path.join(tmp_dir, "Release.key")
    dearmored = os.path.join(tmp_dir, "Release.gpg")
    try:
        result = run_command(["curl", "-fsSL", "-o", armored, key_url], timeout=60)
        if not result.success:
            _log(log, f"  ERROR: Could not download the repository key.\n{result.stderr.strip()}")
            _log(log, f"  Check that {arch_label} is a supported OS for the {channel} channel.")
            return False

        result = run_command(
            ["gpg", "--batch", "--yes", "--dearmor", "-o", dearmored, armored],
            timeout=30,
        )
        if not result.success:
            _log(log, f"  ERROR: gpg --dearmor failed.\n{result.stderr.strip()}")
            return False

        result = run_sudo(["cp", dearmored, gpg_file], timeout=15)
        if not result.success:
            _log(log, f"  ERROR: Could not write {gpg_file}.\n{result.stderr.strip()}")
            return False
        run_sudo(["chmod", "644", gpg_file], timeout=10)
    finally:
        for path in (armored, dearmored):
            try:
                os.unlink(path)
            except OSError:
                pass
        try:
            os.rmdir(tmp_dir)
        except OSError:
            pass

    _log(log, "  GPG key added.")
    return True


def _apt_update(log: Optional[Callable[[str], None]] = None) -> bool:
    _log(log, "Running apt-get update...")
    result = run_sudo_streaming(["apt-get", "update"], log=log, env=_APT_ENV)
    if not result.success:
        _log(log, "ERROR: apt-get update failed.")
        return False
    return True


def _apt_install(log: Optional[Callable[[str], None]] = None) -> bool:
    _log(log, "Installing meshtasticd (this can take several minutes on a slow connection)...")
    result = run_sudo_streaming(
        ["apt-get", "install", "-y", "meshtasticd"], log=log, env=_APT_ENV,
    )
    if not result.success:
        _log(log, "ERROR: apt-get install failed.")
        return False
    return True


def _apt_purge(log: Optional[Callable[[str], None]] = None) -> bool:
    result = run_sudo_streaming(
        ["apt-get", "purge", "-y", "meshtasticd"], log=log, env=_APT_ENV,
    )
    if not result.success:
        _log(log, "ERROR: apt-get purge failed.")
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
