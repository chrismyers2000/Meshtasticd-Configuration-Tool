"""
core/utils.py — Shared utilities: subprocess wrappers, file helpers, logging.
"""

from __future__ import annotations

import logging
import os
import shutil
import subprocess
from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional


# ---------------------------------------------------------------------------
# Data types
# ---------------------------------------------------------------------------

@dataclass
class CommandResult:
    returncode: int
    stdout: str
    stderr: str

    @property
    def success(self) -> bool:
        return self.returncode == 0

    @property
    def output(self) -> str:
        """Combined stdout + stderr for display."""
        parts = []
        if self.stdout.strip():
            parts.append(self.stdout)
        if self.stderr.strip():
            parts.append(self.stderr)
        return "\n".join(parts)


# ---------------------------------------------------------------------------
# Subprocess helpers
# ---------------------------------------------------------------------------

def run_command(
    cmd: list[str],
    timeout: int = 30,
    input_text: Optional[str] = None,
    env: Optional[dict] = None,
    cwd: Optional[str] = None,
) -> CommandResult:
    """Run a command without sudo. Never uses shell=True."""
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            input=input_text,
            env=env,
            cwd=cwd,
        )
        return CommandResult(
            returncode=result.returncode,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    except subprocess.TimeoutExpired:
        return CommandResult(returncode=-1, stdout="", stderr=f"Command timed out after {timeout}s: {' '.join(cmd)}")
    except FileNotFoundError:
        return CommandResult(returncode=-1, stdout="", stderr=f"Command not found: {cmd[0]}")
    except Exception as exc:
        return CommandResult(returncode=-1, stdout="", stderr=str(exc))


def run_sudo(
    cmd: list[str],
    timeout: int = 120,
    input_text: Optional[str] = None,
) -> CommandResult:
    """Prepend sudo and run. Passes -n to avoid interactive password prompts."""
    return run_command(["sudo"] + cmd, timeout=timeout, input_text=input_text)


def check_sudo_available() -> bool:
    """Return True if the current user can run sudo without a password prompt."""
    result = run_command(["sudo", "-n", "true"], timeout=5)
    return result.success


# ---------------------------------------------------------------------------
# File helpers
# ---------------------------------------------------------------------------

def read_file(path: str) -> Optional[str]:
    """Read a file and return its contents, or None if unreadable."""
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except (OSError, IOError):
        return None


def file_contains(path: str, text: str) -> bool:
    """Return True if the file exists and contains the given text string."""
    content = read_file(path)
    return content is not None and text in content


def file_exists(path: str) -> bool:
    return os.path.isfile(path)


def dir_exists(path: str) -> bool:
    return os.path.isdir(path)


def backup_file(path: str) -> Optional[str]:
    """
    Copy path to path.bak.<timestamp>. Returns the backup path, or None on failure.
    Safe to call even if the file does not exist (returns None).
    """
    if not os.path.isfile(path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.bak.{timestamp}"
    try:
        shutil.copy2(path, backup_path)
        return backup_path
    except OSError:
        return None


def write_file_sudo(path: str, content: str) -> bool:
    """Write content to a file that requires sudo (uses tee)."""
    result = run_command(
        ["sudo", "tee", path],
        input_text=content,
        timeout=30,
    )
    return result.success


def append_line_sudo(path: str, line: str) -> bool:
    """Append a single line (with trailing newline) to a file via sudo tee -a."""
    result = run_command(
        ["sudo", "tee", "-a", path],
        input_text=line if line.endswith("\n") else line + "\n",
        timeout=30,
    )
    return result.success


def download_file(url: str, dest: str) -> bool:
    """Download a file using curl (no requests dependency). Returns True on success."""
    result = run_sudo(
        ["curl", "-fsSL", "-o", dest, url],
        timeout=60,
    )
    return result.success


# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

_logger: Optional[logging.Logger] = None


def setup_logging(log_path: str = "/tmp/meshadv-config.log") -> logging.Logger:
    global _logger
    logger = logging.getLogger("meshadv")
    logger.setLevel(logging.DEBUG)

    fmt = logging.Formatter("%(asctime)s [%(levelname)s] %(message)s")

    # Console handler (INFO and above)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    ch.setFormatter(fmt)
    logger.addHandler(ch)

    # File handler (DEBUG and above)
    try:
        fh = logging.FileHandler(log_path)
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(fmt)
        logger.addHandler(fh)
    except OSError:
        pass  # Can't write log file; continue without it

    _logger = logger
    return logger


def get_logger() -> logging.Logger:
    global _logger
    if _logger is None:
        _logger = setup_logging()
    return _logger
