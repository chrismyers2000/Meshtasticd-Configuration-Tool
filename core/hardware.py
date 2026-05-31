"""
core/hardware.py — Detect Raspberry Pi model, MeshAdv HAT, OS info, and meshtasticd version.
"""

from __future__ import annotations

import os
import re
import struct
from dataclasses import dataclass, field
from typing import Callable, Optional

from core.utils import read_file, run_command, run_sudo, file_exists


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


@dataclass
class EepromReadResult:
    success: bool
    vendor: str       # empty string on failure
    product: str      # empty string on failure
    raw_output: str   # full eepdump text for display
    error: str        # description on failure, empty on success


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
        name="MeshAdv Pro",
        has_eeprom=True,
        has_gps=True,
        config_yaml_name="lora-MeshAdv-Pro-915M30S.yaml",
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


def _match_hat_from_strings(vendor: str, product: str, raw_output: str = "") -> HatInfo:
    """
    Map raw vendor/product strings (from EEPROM) to a known HatInfo.
    Falls back to scanning the full eepdump output if targeted field extraction
    yielded empty strings (handles variation in eepdump output formats).
    """
    # Use the full raw output as a fallback search surface if fields are empty
    search_text = f"{vendor} {product} {raw_output}".lower()

    is_meshadv = "meshadv" in search_text or "frequency labs" in search_text

    if is_meshadv and re.search(r'\bpro\b', search_text):
        return HAT_DEFINITIONS["MeshAdv Pro"]
    if is_meshadv and re.search(r'\bmini\b', search_text):
        return HAT_DEFINITIONS["MeshAdv Mini"]
    if is_meshadv:
        return HAT_DEFINITIONS["MeshAdv Pi Hat v1.1"]

    # Unknown model — use the actual product string from the EEPROM as the name
    display_name = product.strip() or vendor.strip() or "Unknown HAT"
    return HatInfo(
        detected=True,
        name=display_name,
        has_eeprom=True,
        has_gps=False,
        config_yaml_name="lora-MeshAdv-900M30S.yaml",
    )


def read_hat_eeprom_manual(
    log: Optional[Callable[[str], None]] = None,
) -> EepromReadResult:
    """
    Manually read the HAT EEPROM by creating a temporary I2C bus on GPIO 0/1.
    Steps: load dtoverlay → read EEPROM with eepflash.sh → parse with eepdump → cleanup.
    """
    def _log(msg: str) -> None:
        if log:
            log(msg)

    tmp_path = f"/tmp/hat_detect_{os.getpid()}.eep"

    # Step 1: load I2C overlay
    _log("Loading i2c-gpio overlay on GPIO 0/1 (bus 9)...")
    result = run_sudo(
        ["dtoverlay", "i2c-gpio", "i2c_gpio_sda=0", "i2c_gpio_scl=1", "bus=9"],
        timeout=15,
    )
    if not result.success:
        return EepromReadResult(
            success=False, vendor="", product="", raw_output="",
            error=f"dtoverlay failed: {result.output}",
        )
    _log("  I2C bus 9 created.")

    # Step 2: read EEPROM
    _log("Reading EEPROM via eepflash.sh (this may take a moment)...")
    result = run_sudo(
        ["eepflash.sh", "-r", "-t=24c64", "-d=9", f"-f={tmp_path}"],
        input_text="yes\n",
        timeout=30,
    )
    if not result.success:
        _cleanup(tmp_path, _log)
        no_eeprom = (
            "no such file or directory" in result.output.lower()
            or "error doing i/o operation" in result.output.lower()
        )
        if no_eeprom:
            return EepromReadResult(
                success=False, vendor="", product="", raw_output="",
                error="Hat not detected, this is normal for the MeshAdv Pi Hat v1.1",
            )
        return EepromReadResult(
            success=False, vendor="", product="", raw_output=result.output,
            error=f"eepflash.sh failed: {result.output}",
        )
    _log("  EEPROM read complete.")

    # Step 3: parse vendor/product by running the parser as root (avoids
    # permission issues — eepflash.sh writes the file owned by root)
    _log("Parsing EEPROM data...")
    vendor, product, parse_error = _read_eep_strings_sudo(tmp_path)
    if not vendor and not product:
        _cleanup(tmp_path, _log)
        return EepromReadResult(
            success=False, vendor="", product="", raw_output="",
            error=f"Could not parse vendor info: {parse_error}",
        )
    raw_output = f"vendor: {vendor}\nproduct: {product}"

    _cleanup(tmp_path, _log)

    return EepromReadResult(
        success=True,
        vendor=vendor,
        product=product,
        raw_output=raw_output,
        error="",
    )


def _read_eep_strings_sudo(path: str) -> tuple[str, str, str]:
    """
    Parse a HAT EEPROM .eep binary file as root and return (vendor, product, error).
    Runs via sudo python3 to avoid file-permission issues with root-owned .eep files.
    """
    script = (
        "import struct,sys\n"
        "data=open(" + repr(path) + ",'rb').read()\n"
        "sig=struct.unpack_from('>I',data,0)[0]\n"
        "assert sig==0x522d5069,'bad_sig:0x%08x'%sig\n"
        "_v,_r,n,_l=struct.unpack_from('<BBHI',data,4)\n"
        "o=12\n"
        "for _ in range(n):\n"
        " t,_c,d=struct.unpack_from('<HHI',data,o)\n"
        " s=o+8\n"
        " if t==1:\n"
        "  vl,pl=struct.unpack_from('BB',data,s+20)\n"
        "  p=s+22\n"
        "  print(data[p:p+vl].decode('utf-8',errors='replace').rstrip('\\x00').strip())\n"
        "  print(data[p+vl:p+vl+pl].decode('utf-8',errors='replace').rstrip('\\x00').strip())\n"
        "  sys.exit(0)\n"
        " o=s+d\n"
        "print('no vendor atom found',file=sys.stderr)\n"
        "sys.exit(1)\n"
    )
    result = run_sudo(["python3"], input_text=script, timeout=10)
    if result.success:
        lines = result.stdout.strip().splitlines()
        vendor  = lines[0] if len(lines) > 0 else ""
        product = lines[1] if len(lines) > 1 else ""
        return vendor, product, ""
    error = (result.stderr.strip() or result.stdout.strip() or "unknown error")
    return "", "", error


def _cleanup(tmp_path: str, log: Callable[[str], None]) -> None:
    """Remove temp .eep file and unload the i2c-gpio overlay."""
    run_sudo(["rm", "-f", tmp_path])
    log("Removing i2c-gpio overlay...")
    run_sudo(["dtoverlay", "-r", "i2c-gpio"], timeout=15)
