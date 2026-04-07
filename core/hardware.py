"""
core/hardware.py — Detect Raspberry Pi model, MeshAdv HAT, OS info, and meshtasticd version.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from core.utils import read_file, run_command, file_exists


# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PiModel:
    raw_string: str
    model_num: int          # 2, 3, 4, 5, 400, 500, 0 (Zero), -1 (unknown)
    is_pi5_class: bool      # True for Pi 5 or Pi 500 (affects UART overlay)
    display_name: str       # Human-readable name shown in UI

    def __str__(self) -> str:
        return self.display_name


@dataclass
class HatInfo:
    detected: bool
    name: str               # "MeshAdv Pi Hat v1.1" | "MeshAdv Mini" | "MeshAdv Pro" | "Unknown" | "None"
    has_eeprom: bool
    has_gps: bool           # True for Mini and Pro (GPS-capable hats)
    config_yaml_name: str   # Default yaml filename for this hat

    def __str__(self) -> str:
        return self.name


@dataclass
class OsInfo:
    name: str               # "Raspbian" or "Debian" (or raw NAME value)
    version_id: int         # 12 (bookworm) or 13 (trixie), 0 if unknown
    version_name: str       # "bookworm", "trixie", etc.
    is_32bit: bool          # True if Raspbian
    arch_label: str         # e.g. "Raspbian_12", "Debian_13"

    def __str__(self) -> str:
        bits = "32-bit" if self.is_32bit else "64-bit"
        return f"{self.name} {self.version_name} ({bits})"


@dataclass
class SystemInfo:
    pi: PiModel
    hat: HatInfo
    os: OsInfo
    meshtasticd_version: str    # "Not installed" or version string like "2.3.14.abcd1234"


# ---------------------------------------------------------------------------
# HAT definitions
# ---------------------------------------------------------------------------

HAT_DEFINITIONS = {
    "MeshAdv Mini": HatInfo(
        detected=True,
        name="MeshAdv Mini",
        has_eeprom=True,
        has_gps=True,
        config_yaml_name="lora-MeshAdv-Mini-900M22S.yaml",
    ),
    "MeshAdv Pro": HatInfo(
        detected=True,
        name="MeshAdv Pro (Coming Soon)",
        has_eeprom=True,
        has_gps=True,
        config_yaml_name="lora-MeshAdv-Mini-900M22S.yaml",  # Uses Mini config until Pro config is available
    ),
    "MeshAdv Pi Hat v1.1": HatInfo(
        detected=False,
        name="MeshAdv Pi Hat v1.1",
        has_eeprom=False,
        has_gps=False,
        config_yaml_name="lora-MeshAdv-900M30S.yaml",
    ),
}

HAT_NONE = HatInfo(
    detected=False,
    name="No hat detected",
    has_eeprom=False,
    has_gps=False,
    config_yaml_name="lora-MeshAdv-900M30S.yaml",
)

# Default when EEPROM is absent — assume Pi Hat v1.1
# Separate instance so the display name can differ from the EEPROM-detected entry.
HAT_DEFAULT = HatInfo(
    detected=False,
    name="Not Detected: This is normal for MeshAdv Pi Hat v1.1",
    has_eeprom=False,
    has_gps=False,
    config_yaml_name="lora-MeshAdv-900M30S.yaml",
)


# ---------------------------------------------------------------------------
# Detection functions
# ---------------------------------------------------------------------------

def detect_pi_model() -> PiModel:
    """Read /proc/device-tree/model to identify the Pi."""
    raw = read_file("/proc/device-tree/model") or ""
    raw = raw.rstrip("\x00").strip()

    model_num = _parse_pi_model_number(raw)
    is_5_class = _is_pi5_class(model_num)

    if raw:
        display_name = raw
    else:
        display_name = "Unknown Raspberry Pi"

    return PiModel(
        raw_string=raw,
        model_num=model_num,
        is_pi5_class=is_5_class,
        display_name=display_name,
    )


def _parse_pi_model_number(raw: str) -> int:
    """Extract numeric model (2, 3, 4, 5, 400, 500, 0) from the model string."""
    # Check for multi-digit models first (400, 500)
    for candidate in (500, 400):
        if str(candidate) in raw:
            return candidate
    # Check Pi 5
    if re.search(r'\bPi\s*5\b', raw, re.IGNORECASE):
        return 5
    # Zero 2 W
    if re.search(r'Zero\s*2', raw, re.IGNORECASE):
        return 0
    # Zero (original)
    if re.search(r'\bZero\b', raw, re.IGNORECASE):
        return 0
    # Pi 4, 3, 2
    for n in (4, 3, 2):
        if re.search(rf'\bPi\s*{n}\b', raw, re.IGNORECASE):
            return n
    return -1


def _is_pi5_class(model_num: int) -> bool:
    """Pi 5 and Pi 500 use dtoverlay=uart0 and /dev/ttyAMA0."""
    return model_num in (5, 500)


def detect_hat() -> HatInfo:
    """
    Read the HAT EEPROM info from /proc/device-tree/hat/.
    If no EEPROM is found, default to MeshAdv Pi Hat v1.1 (which has no EEPROM).
    """
    product_path = "/proc/device-tree/hat/product"
    vendor_path = "/proc/device-tree/hat/vendor"

    product = read_file(product_path)
    if product is None:
        # No EEPROM detected — assume Pi Hat v1.1
        return HAT_DEFAULT

    product = product.rstrip("\x00").strip()
    vendor = (read_file(vendor_path) or "").rstrip("\x00").strip()

    product_lower = product.lower()

    if "pro" in product_lower:
        return HAT_DEFINITIONS["MeshAdv Pro"]
    if "mini" in product_lower:
        return HAT_DEFINITIONS["MeshAdv Mini"]
    if "meshadv" in product_lower or "frequency labs" in vendor.lower():
        # Recognized vendor but unknown specific model
        return HAT_DEFINITIONS["MeshAdv Pi Hat v1.1"]

    # Unknown HAT
    return HatInfo(
        detected=True,
        name=f"Unknown HAT: {product}",
        has_eeprom=True,
        has_gps=False,
        config_yaml_name="lora-MeshAdv-900M30S.yaml",
    )


def detect_os_info() -> OsInfo:
    """Parse /etc/os-release to get distro name, version, and architecture."""
    content = read_file("/etc/os-release") or ""

    name = _parse_os_release_field(content, "NAME") or "Unknown"
    version_codename = _parse_os_release_field(content, "VERSION_CODENAME") or ""
    version_id_str = _parse_os_release_field(content, "VERSION_ID") or "0"

    try:
        version_id = int(version_id_str)
    except ValueError:
        version_id = 0

    # Raspbian = 32-bit; Debian (including 64-bit Pi OS) = 64-bit
    is_32bit = name.startswith("Raspbian")
    os_base = "Raspbian" if is_32bit else "Debian"
    arch_label = f"{os_base}_{version_id}" if version_id else os_base

    version_name = version_codename or str(version_id) or "unknown"

    return OsInfo(
        name=name,
        version_id=version_id,
        version_name=version_name,
        is_32bit=is_32bit,
        arch_label=arch_label,
    )


def _parse_os_release_field(content: str, field_name: str) -> Optional[str]:
    """Extract a field value from /etc/os-release content."""
    match = re.search(rf'^{field_name}="?([^"\n]*)"?', content, re.MULTILINE)
    if match:
        return match.group(1).strip()
    return None


def detect_meshtasticd_version() -> str:
    """Return installed meshtasticd version string, or 'Not installed'."""
    result = run_command(
        ["dpkg-query", "-W", "-f=${Version}", "meshtasticd"],
        timeout=10,
    )
    if result.success and result.stdout.strip():
        return result.stdout.strip()
    return "Not installed"


def get_system_info() -> SystemInfo:
    """Detect all hardware and system info in one call."""
    pi = detect_pi_model()
    hat = detect_hat()
    os_info = detect_os_info()
    version = detect_meshtasticd_version()
    return SystemInfo(pi=pi, hat=hat, os=os_info, meshtasticd_version=version)
