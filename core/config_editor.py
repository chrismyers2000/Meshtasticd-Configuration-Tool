"""
core/config_editor.py — Manage /boot/firmware/config.txt and /etc/meshtasticd/config.yaml.
Handles SPI, I2C, UART/GPS config, HAT config selection.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Optional

from core.hardware import HatInfo, PiModel
from core.utils import (
    append_line_sudo,
    backup_file,
    download_file,
    file_exists,
    get_local_ip,
    read_file,
    run_command,
    run_sudo,
    write_file_sudo,
)


# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------

CONFIG_TXT = "/boot/firmware/config.txt"
CONFIG_YAML = "/etc/meshtasticd/config.yaml"
AVAILABLE_D = "/etc/meshtasticd/available.d"
CONFIG_D = "/etc/meshtasticd/config.d"

MINI_YAML_URL = (
    "https://raw.githubusercontent.com/chrismyers2000/MeshAdv-Mini"
    "/main/Data/lora-MeshAdv-Mini-900M22S.yaml"
)

PRO_YAML_FILENAME = "lora-MeshAdv-Pro-915M30S.yaml"
PRO_YAML_DOWNLOADED_FILENAME = "lora-MeshAdv-Pro-915M30S-downloaded.yaml"
PRO_YAML_URL = (
    "https://raw.githubusercontent.com/chrismyers2000/MeshAdv-Pro"
    "/main/Data/Misc/lora-MeshAdv-Pro-915M30S.yaml"
)
PRO_GPIO_LINE = "gpio=12=op,dh"

# Default config filenames per HAT
HAT_DEFAULT_CONFIGS = {
    "MeshAdv Pi Hat v1.1": "lora-MeshAdv-900M30S.yaml",
    "MeshAdv Mini": "lora-MeshAdv-Mini-900M22S.yaml",
    "MeshAdv Pro": "lora-MeshAdv-Pro-915M30S.yaml",
}


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class AvailableConfig:
    name: str               # Filename only (e.g. lora-MeshAdv-900M30S.yaml)
    path: str               # Full absolute path
    is_default_for_hat: bool
    in_subdir: bool
    subdir_name: Optional[str]


# ---------------------------------------------------------------------------
# Status checks (read-only)
# ---------------------------------------------------------------------------

def _config_txt_has_active_line(line: str) -> bool:
    """
    Return True if the line exists in config.txt in active (uncommented) form.
    Allows optional trailing inline comments (e.g. "dtparam=spi=on # some note").
    """
    content = read_file(CONFIG_TXT) or ""
    pattern = re.compile(
        r"^\s*" + re.escape(line.strip()) + r"(\s*(#.*)?)?\s*$",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def _config_txt_has_line_any_form(line: str) -> bool:
    """
    Return True if the line is present in config.txt in any form
    (active or commented out).
    """
    content = read_file(CONFIG_TXT) or ""
    pattern = re.compile(
        r"^\s*#?\s*" + re.escape(line.strip()) + r"\s*$",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def is_spi_enabled() -> bool:
    return (
        _config_txt_has_active_line("dtparam=spi=on")
        and _config_txt_has_active_line("dtoverlay=spi0-0cs")
    )


def is_i2c_enabled() -> bool:
    return _config_txt_has_active_line("dtparam=i2c_arm=on")


def is_uart_enabled(pi: PiModel) -> bool:
    if not _config_txt_has_active_line("enable_uart=1"):
        return False
    if pi.is_pi5_class and not _config_txt_has_active_line("dtoverlay=uart0"):
        return False
    return True


def is_gps_configured_in_yaml(pi: PiModel) -> bool:
    """Return True if the GPS SerialPath is uncommented and set in config.yaml."""
    content = read_file(CONFIG_YAML) or ""
    expected_path = "/dev/ttyAMA0" if pi.is_pi5_class else "/dev/ttyS0"
    # Look for an uncommented SerialPath line with the correct path
    pattern = re.compile(
        r"^\s{0,10}SerialPath:\s*" + re.escape(expected_path) + r"\s*$",
        re.MULTILINE,
    )
    return bool(pattern.search(content))


def is_webserver_enabled() -> bool:
    """Return True if the Webserver Port line is uncommented in config.yaml."""
    content = read_file(CONFIG_YAML) or ""
    in_webserver_block = False
    for line in content.splitlines():
        if re.match(r"^\s*Webserver\s*:", line):
            in_webserver_block = True
            continue
        if in_webserver_block:
            # An uncommented top-level key ends the block
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            if re.match(r"^\s+Port\s*:", line) and not line.strip().startswith("#"):
                return True
    return False


def get_webserver_port() -> int:
    """Read the Webserver Port from config.yaml. Returns 9443 if not found or unreadable."""
    content = read_file(CONFIG_YAML) or ""
    in_webserver_block = False
    for line in content.splitlines():
        if re.match(r"^\s*Webserver\s*:", line):
            in_webserver_block = True
            continue
        if in_webserver_block:
            if line and not line.startswith(" ") and not line.startswith("#"):
                break
            m = re.match(r"^\s+Port\s*:\s*(\d+)", line)
            if m:
                return int(m.group(1))
    return 9443


def enable_webserver(log: Optional[Callable[[str], None]] = None) -> bool:
    """Uncomment the Webserver block (Port, RootPath, SSLKey, SSLCert) in config.yaml."""
    content = read_file(CONFIG_YAML)
    if content is None:
        _log(log, f"config.yaml not found at {CONFIG_YAML}")
        return False

    if is_webserver_enabled():
        _log(log, "Web server is already enabled in config.yaml.")
        return True

    backup_file(CONFIG_YAML)
    new_lines = []
    in_webserver_block = False
    found_block = False

    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")
        if re.match(r"^\s*Webserver\s*:", stripped):
            in_webserver_block = True
            found_block = True
            new_lines.append(line)
            continue

        if in_webserver_block:
            # End of block: non-indented, non-comment, non-empty line
            if stripped and not stripped.startswith(" ") and not stripped.startswith("#"):
                in_webserver_block = False
            else:
                # Replace leading "#  " with "  " to preserve YAML indentation
                uncommented = re.sub(r"^#  ", "  ", line)
                new_lines.append(uncommented)
                continue

        new_lines.append(line)

    if not found_block:
        _log(log, "Webserver block not found in config.yaml.")
        return False

    ok = write_file_sudo(CONFIG_YAML, "".join(new_lines))
    if ok:
        _log(log, "Web server enabled in config.yaml. Restart meshtasticd to apply.")
    else:
        _log(log, "ERROR: Failed to write config.yaml.")
    return ok


def get_hat_config_in_use() -> Optional[str]:
    """Return the filename of the config currently in /etc/meshtasticd/config.d, or None."""
    if not os.path.isdir(CONFIG_D):
        return None
    try:
        files = [
            f for f in os.listdir(CONFIG_D)
            if f.endswith(".yaml") and os.path.isfile(os.path.join(CONFIG_D, f))
        ]
        return files[0] if files else None
    except OSError:
        return None


def list_available_configs(hat: Optional[HatInfo] = None) -> list[AvailableConfig]:
    """
    Walk /etc/meshtasticd/available.d and return all .yaml config files.
    Marks the HAT's default config with is_default_for_hat=True.
    """
    configs: list[AvailableConfig] = []
    if not os.path.isdir(AVAILABLE_D):
        return configs

    default_name = hat.config_yaml_name if hat else None

    try:
        for root, dirs, files in os.walk(AVAILABLE_D):
            dirs.sort()
            subdir = os.path.relpath(root, AVAILABLE_D)
            in_subdir = subdir != "."
            subdir_name = subdir if in_subdir else None

            for fname in sorted(files):
                if not fname.endswith(".yaml"):
                    continue
                full_path = os.path.join(root, fname)
                configs.append(AvailableConfig(
                    name=fname,
                    path=full_path,
                    is_default_for_hat=(fname == default_name),
                    in_subdir=in_subdir,
                    subdir_name=subdir_name,
                ))
    except OSError:
        pass

    return configs


# ---------------------------------------------------------------------------
# Write actions
# ---------------------------------------------------------------------------

def _ensure_line_in_config_txt(line: str) -> bool:
    """
    Add `line` to config.txt if it is not already present in active form.
    Returns True if the line was added or already present.
    """
    if _config_txt_has_active_line(line):
        return True
    return append_line_sudo(CONFIG_TXT, line)


def enable_spi(log: Optional[Callable[[str], None]] = None) -> bool:
    """Add SPI overlay lines to /boot/firmware/config.txt if not present."""
    _log(log, "Checking SPI configuration...")
    backup_file(CONFIG_TXT)

    ok = True
    for line in ("dtparam=spi=on", "dtoverlay=spi0-0cs"):
        if _config_txt_has_active_line(line):
            _log(log, f"  Already present: {line}")
        else:
            _log(log, f"  Adding: {line}")
            if not append_line_sudo(CONFIG_TXT, line):
                _log(log, f"  ERROR: Failed to add {line}")
                ok = False
    if ok:
        _log(log, "SPI configuration complete. Reboot required.")
    return ok


def enable_i2c(log: Optional[Callable[[str], None]] = None) -> bool:
    """Add I2C parameter to /boot/firmware/config.txt if not present."""
    _log(log, "Checking I2C configuration...")
    backup_file(CONFIG_TXT)

    line = "dtparam=i2c_arm=on"
    if _config_txt_has_active_line(line):
        _log(log, "  I2C already enabled.")
        return True

    _log(log, f"  Adding: {line}")
    if append_line_sudo(CONFIG_TXT, line):
        _log(log, "I2C configuration complete. Reboot required.")
        return True
    else:
        _log(log, "ERROR: Failed to add I2C line.")
        return False


def enable_gps_uart(
    pi: PiModel,
    hat: HatInfo,
    log: Optional[Callable[[str], None]] = None,
) -> bool:
    """
    Add UART and GPS overlay lines to config.txt and update config.yaml SerialPath.
    - enable_uart=1 for all Pi models
    - dtoverlay=uart0 for Pi 5 and Pi 500 only
    - PPS + GPIO lines for MeshAdv Mini and Pro only
    - Set GPS SerialPath in config.yaml
    """
    _log(log, "Configuring GPS/UART...")
    backup_file(CONFIG_TXT)

    ok = True

    # Always add enable_uart=1
    if not _config_txt_has_active_line("enable_uart=1"):
        _log(log, "  Adding: enable_uart=1")
        if not append_line_sudo(CONFIG_TXT, "enable_uart=1 # Needed for all Pi devices."):
            _log(log, "  ERROR: Failed to add enable_uart=1")
            ok = False
    else:
        _log(log, "  enable_uart=1 already present.")

    # Pi 5 / Pi 500 only
    if pi.is_pi5_class:
        if not _config_txt_has_active_line("dtoverlay=uart0"):
            _log(log, "  Adding: dtoverlay=uart0 (Pi 5/500 only)")
            if not append_line_sudo(CONFIG_TXT, "dtoverlay=uart0 # Needed for Pi 5 or 500."):
                _log(log, "  ERROR: Failed to add dtoverlay=uart0")
                ok = False
        else:
            _log(log, "  dtoverlay=uart0 already present.")

    # GPS-capable HATs (Mini and Pro)
    if hat.has_gps:
        for line, comment in [
            ("dtoverlay=pps-gpio,gpiopin=17", "# Enables PPS"),
            ("gpio=4=op,dh", "# Enables GPS Enable pin"),
        ]:
            if not _config_txt_has_active_line(line):
                entry = f"{line} {comment}"
                _log(log, f"  Adding: {entry}")
                if not append_line_sudo(CONFIG_TXT, entry):
                    _log(log, f"  ERROR: Failed to add {line}")
                    ok = False
            else:
                _log(log, f"  {line} already present.")

    # Update config.yaml GPS SerialPath
    serial_path = "/dev/ttyAMA0" if pi.is_pi5_class else "/dev/ttyS0"
    _log(log, f"  Setting GPS SerialPath to {serial_path} in config.yaml...")
    if not _update_yaml_serial_path(serial_path, log):
        _log(log, "  WARNING: Could not update config.yaml GPS SerialPath.")
        ok = False

    if ok:
        _log(log, "GPS/UART configuration complete. Reboot required.")
    return ok


def _update_yaml_serial_path(serial_path: str, log: Optional[Callable[[str], None]] = None) -> bool:
    """
    In /etc/meshtasticd/config.yaml, uncomment and set the GPS SerialPath.
    Handles both commented-out and active forms of the GPS block.
    """
    content = read_file(CONFIG_YAML)
    if content is None:
        _log(log, f"  config.yaml not found at {CONFIG_YAML}")
        return False

    backup_file(CONFIG_YAML)
    new_lines = []
    in_gps_block = False
    gps_block_done = False

    for line in content.splitlines(keepends=True):
        stripped = line.rstrip("\n\r")
        # Detect GPS: section header (commented or not)
        if re.match(r"^\s*#?\s*GPS\s*:", stripped):
            in_gps_block = True
            gps_block_done = False
            new_lines.append("GPS:\n")
            continue

        if in_gps_block and not gps_block_done:
            # Look for SerialPath line (commented or not)
            if re.match(r"^\s*#?\s*SerialPath\s*:", stripped):
                new_lines.append(f"  SerialPath: {serial_path}\n")
                gps_block_done = True
                in_gps_block = False
                continue
            # A non-comment, non-empty line that isn't SerialPath ends the GPS block scan
            if stripped and not stripped.strip().startswith("#"):
                in_gps_block = False

        new_lines.append(line)

    new_content = "".join(new_lines)

    # If GPS block was never found, append it
    if not gps_block_done:
        _log(log, "  GPS block not found in config.yaml — appending.")
        new_content += f"\nGPS:\n  SerialPath: {serial_path}\n"

    return write_file_sudo(CONFIG_YAML, new_content)


def set_hat_config(
    yaml_filename: str,
    log: Optional[Callable[[str], None]] = None,
) -> tuple[bool, bool]:
    """
    Copy the selected yaml file from available.d to config.d.
    Clears any existing .yaml files in config.d first.
    Manages gpio=12=op,dh in config.txt: adds it for Pro configs, removes it for all others.
    Returns (success, reboot_needed).
    """
    # Find source file
    source_path = _find_in_available_d(yaml_filename)
    if source_path is None:
        _log(log, f"ERROR: {yaml_filename} not found in {AVAILABLE_D}")
        return False, False

    # Ensure config.d exists
    if not os.path.isdir(CONFIG_D):
        result = run_sudo(["mkdir", "-p", CONFIG_D])
        if not result.success:
            _log(log, f"ERROR: Could not create {CONFIG_D}")
            return False, False

    # Remove any existing yaml files in config.d
    try:
        existing = [
            f for f in os.listdir(CONFIG_D)
            if f.endswith(".yaml")
        ]
        for fname in existing:
            _log(log, f"  Removing existing config: {fname}")
            run_sudo(["rm", "-f", os.path.join(CONFIG_D, fname)])
    except OSError:
        pass

    # Copy the selected file
    dest_path = os.path.join(CONFIG_D, yaml_filename)
    _log(log, f"  Copying {yaml_filename} to {CONFIG_D}")
    result = run_sudo(["cp", source_path, dest_path])
    if not result.success:
        _log(log, f"ERROR: Failed to copy config file.\n{result.stderr}")
        return False, False

    _log(log, f"Hat config set to: {yaml_filename}")

    # Manage GPIO 12 pin for MeshAdv Pro
    reboot_needed = False
    if yaml_filename.startswith("lora-MeshAdv-Pro"):
        if not _config_txt_has_active_line(PRO_GPIO_LINE):
            backup_file(CONFIG_TXT)
            _log(log, f"  Adding {PRO_GPIO_LINE} to {CONFIG_TXT} (required for MeshAdv Pro)")
            append_line_sudo(CONFIG_TXT, f"{PRO_GPIO_LINE} # MeshAdv Pro power enable")
            reboot_needed = True
        else:
            _log(log, f"  {PRO_GPIO_LINE} already present in {CONFIG_TXT}")
    else:
        if _config_txt_has_active_line(PRO_GPIO_LINE):
            backup_file(CONFIG_TXT)
            _log(log, f"  Removing {PRO_GPIO_LINE} from {CONFIG_TXT} (not needed for {yaml_filename})")
            _remove_line_from_config_txt(PRO_GPIO_LINE)
            reboot_needed = True

    return True, reboot_needed


def _find_in_available_d(filename: str) -> Optional[str]:
    """Walk available.d and return the full path of the first matching filename."""
    if not os.path.isdir(AVAILABLE_D):
        return None
    for root, _dirs, files in os.walk(AVAILABLE_D):
        if filename in files:
            return os.path.join(root, filename)
    return None


def _remove_line_from_config_txt(line: str) -> bool:
    """
    Remove all active (uncommented) occurrences of `line` from config.txt.
    Returns True if at least one line was removed, False if nothing changed.
    """
    content = read_file(CONFIG_TXT)
    if content is None:
        return False
    pattern = re.compile(
        r"^\s*" + re.escape(line.strip()) + r"(\s*(#.*)?)?\s*$",
        re.MULTILINE,
    )
    new_content, count = pattern.subn("", content)
    if count == 0:
        return False
    # Clean up blank lines left behind (collapse multiple blank lines to one)
    new_content = re.sub(r"\n{3,}", "\n\n", new_content)
    write_file_sudo(CONFIG_TXT, new_content)
    return True


def ensure_pro_yaml_available(log: Optional[Callable[[str], None]] = None) -> bool:
    """
    Ensure a Pro YAML config is present in available.d (canonical or downloaded form).
    Downloads from GitHub if neither is found. Returns True if available, False on failure.
    """
    if (_find_in_available_d(PRO_YAML_FILENAME) is not None
            or _find_in_available_d(PRO_YAML_DOWNLOADED_FILENAME) is not None):
        _log(log, f"Pro YAML already present in {AVAILABLE_D}")
        return True
    return download_pro_yaml(log)


def download_mini_yaml(log: Optional[Callable[[str], None]] = None) -> bool:
    """Download lora-MeshAdv-Mini-900M22S.yaml from GitHub into available.d, saved with a -downloaded suffix."""
    filename = "lora-MeshAdv-Mini-900M22S-downloaded.yaml"
    dest = os.path.join(AVAILABLE_D, filename)

    if not os.path.isdir(AVAILABLE_D):
        _log(log, f"ERROR: {AVAILABLE_D} does not exist. Is meshtasticd installed?")
        return False

    _log(log, f"Downloading {filename} from GitHub...")
    if download_file(MINI_YAML_URL, dest):
        _log(log, f"Download complete: {dest}")
        return True
    else:
        _log(log, "ERROR: Download failed. Check your internet connection.")
        return False


def download_pro_yaml(log: Optional[Callable[[str], None]] = None) -> bool:
    """Download lora-MeshAdv-Pro-915M30S-downloaded.yaml from GitHub into available.d."""
    dest = os.path.join(AVAILABLE_D, PRO_YAML_DOWNLOADED_FILENAME)

    if not os.path.isdir(AVAILABLE_D):
        _log(log, f"ERROR: {AVAILABLE_D} does not exist. Is meshtasticd installed?")
        return False

    _log(log, f"Downloading {PRO_YAML_DOWNLOADED_FILENAME} from GitHub...")
    if download_file(PRO_YAML_URL, dest):
        _log(log, f"Download complete: {dest}")
        return True
    else:
        _log(log, "ERROR: Download failed. Check your internet connection.")
        return False


# ---------------------------------------------------------------------------
# Internal helper
# ---------------------------------------------------------------------------

def _log(callback: Optional[Callable[[str], None]], message: str) -> None:
    if callback:
        callback(message)
