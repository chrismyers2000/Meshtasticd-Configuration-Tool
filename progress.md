# Progress

## Core Modules
- [x] core/utils.py — subprocess wrappers, file helpers, logging
- [x] core/hardware.py — Pi model, HAT, OS, meshtasticd detection
- [x] core/config_editor.py — SPI, I2C, UART, GPS, hat config
- [x] core/actions.py — systemctl, Python CLI install, region, send message
- [x] core/installer.py — apt install/remove meshtasticd

## UI
- [x] gui/app.py — CustomTkinter GUI
- [x] tui/app.py — Textual TUI

## Entry Point & Packaging
- [x] meshadv-config.py — auto-detect GUI vs TUI, --gui/--tui flags
- [x] install.sh — curl-installable bootstrap (GitHub URL TBD)

## Documentation
- [x] ToDo.md — loose ends with file/line references
- [x] progress.md — this file

## Testing (to do on Pi hardware)
- [ ] GUI launches on Pi desktop with DISPLAY set
- [ ] TUI launches over SSH (no DISPLAY)
- [ ] Hardware detection reads correct Pi model, HAT, version
- [ ] SPI/I2C/UART enable writes correct lines to config.txt
- [ ] GPS config.yaml SerialPath set correctly for Pi model
- [ ] Hat config selection copies yaml to config.d
- [ ] Install/remove meshtasticd works for 32-bit and 64-bit
- [ ] All systemctl commands work
- [ ] Python CLI install (pip3 + pipx fallback)
- [ ] Set region + send message via CLI
- [ ] install.sh runs clean on fresh Pi OS Bookworm and Trixie
