#!/usr/bin/env python3
"""
meshadv-config.py — Meshtasticd Configuration Tool entry point.
Auto-detects display mode:
  - DISPLAY env var set  → launches CustomTkinter GUI
  - No DISPLAY (SSH)     → launches Textual TUI
"""

import os
import sys


def detect_mode() -> str:
    """Return 'gui' if a display is available, else 'tui'."""
    return "gui" if os.environ.get("DISPLAY") else "tui"


def check_dependency(module: str) -> bool:
    try:
        __import__(module)
        return True
    except ImportError:
        return False


def run_gui() -> None:
    if not check_dependency("customtkinter"):
        print("CustomTkinter is not installed.")
        print("Install it with:  pip3 install customtkinter")
        print("Falling back to TUI...")
        run_tui()
        return

    from gui.app import MeshAdvApp
    app = MeshAdvApp()
    app.mainloop()


def run_tui() -> None:
    if not check_dependency("textual"):
        print("ERROR: Textual is not installed.")
        print("Install it with:  pip3 install textual")
        sys.exit(1)

    from tui.app import MeshAdvTUI
    app = MeshAdvTUI()
    app.run()


def check_not_root() -> None:
    """
    Refuse to run as root. The tool runs as the normal user and calls sudo
    itself for each privileged command. Under sudo, root's Python cannot see
    the user's pip/pipx packages (customtkinter, textual, the meshtastic CLI),
    which shows up as misleading "not installed" errors.
    """
    if hasattr(os, "geteuid") and os.geteuid() == 0:
        invoked_as = os.environ.get("SUDO_USER")
        print("ERROR: Do not run this tool with sudo or as root.")
        print("It runs as your normal user and asks for sudo only where needed.")
        if invoked_as:
            print(f"Run it again as '{invoked_as}' without sudo:")
        else:
            print("Run it again as your normal user:")
        print(f"  python3 {os.path.abspath(sys.argv[0])}")
        sys.exit(1)


def main() -> None:
    check_not_root()

    # Allow forcing a mode via command-line flag
    if "--tui" in sys.argv:
        run_tui()
        return
    if "--gui" in sys.argv:
        run_gui()
        return

    mode = detect_mode()
    if mode == "gui":
        run_gui()
    else:
        run_tui()


if __name__ == "__main__":
    main()
