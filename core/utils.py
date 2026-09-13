"""
core/utils.py — Shared utilities: subprocess wrappers, file helpers, logging.
"""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, Optional


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
    """
    Prepend sudo and run. Uses -n so a missing passwordless-sudo rule fails
    immediately with a clear error instead of hanging on a password prompt
    the user can never see (e.g. GUI launched from the desktop menu).
    """
    return run_command(["sudo", "-n"] + cmd, timeout=timeout, input_text=input_text)


def check_sudo_available() -> bool:
    """Return True if the current user can run sudo without a password prompt."""
    result = run_command(["sudo", "-n", "true"], timeout=5)
    return result.success


def run_sudo_streaming(
    cmd: list[str],
    log: Optional[Callable[[str], None]] = None,
    env: Optional[dict] = None,
) -> CommandResult:
    """
    Run a command under sudo and stream its combined stdout/stderr to `log`
    line by line as it is produced. No timeout: long-running package
    operations (apt-get, pip) must never be killed part-way through.

    `env` entries are passed through `sudo env VAR=value ...` so they reach
    the root process (sudo strips the caller's environment by default).
    """
    full_cmd = ["sudo", "-n"]
    if env:
        full_cmd += ["env"] + [f"{k}={v}" for k, v in env.items()]
    full_cmd += cmd

    lines: list[str] = []
    try:
        proc = subprocess.Popen(
            full_cmd,
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
        returncode = proc.wait()
        return CommandResult(returncode=returncode, stdout="\n".join(lines), stderr="")
    except FileNotFoundError:
        return CommandResult(returncode=-1, stdout="", stderr=f"Command not found: {full_cmd[0]}")
    except Exception as exc:
        return CommandResult(returncode=-1, stdout="\n".join(lines), stderr=str(exc))


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
    Copy path to path.bak.<timestamp> using sudo (the files this tool edits
    live in root-owned directories). Returns the backup path, or None on
    failure. Safe to call even if the file does not exist (returns None).
    """
    if not os.path.isfile(path):
        return None
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = f"{path}.bak.{timestamp}"
    # Plain cp (not -p): preserving mode/owner fails on the vfat boot partition.
    result = run_sudo(["cp", path, backup_path], timeout=30)
    return backup_path if result.success else None


def write_file_sudo(path: str, content: str) -> bool:
    """
    Atomically replace `path` with `content` using sudo.

    The content is staged in a temp file, copied next to the target as
    `<path>.tmp.new`, given the target's owner/mode where the filesystem
    allows it, then renamed over the target. A crash part-way through never
    leaves a truncated config.txt or config.yaml behind.
    """
    fd, staged = tempfile.mkstemp(prefix="meshadv-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(content)
        # Stage next to the target so the final mv is a same-filesystem rename.
        staged_target = f"{path}.tmp.new"
        if not run_sudo(["cp", staged, staged_target], timeout=30).success:
            return False
        if os.path.exists(path):
            # Best effort: vfat (/boot/firmware) refuses chown/chmod, and that is fine.
            run_sudo(["chown", f"--reference={path}", staged_target], timeout=10)
            run_sudo(["chmod", f"--reference={path}", staged_target], timeout=10)
        else:
            run_sudo(["chmod", "644", staged_target], timeout=10)
        if not run_sudo(["mv", "-f", staged_target, path], timeout=30).success:
            run_sudo(["rm", "-f", staged_target], timeout=10)
            return False
        return True
    finally:
        try:
            os.unlink(staged)
        except OSError:
            pass


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


def get_local_ip() -> str:
    """Return the device's primary local IP address, or 127.0.0.1 on failure."""
    import socket
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"
