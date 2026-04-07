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


def main() -> None:
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
