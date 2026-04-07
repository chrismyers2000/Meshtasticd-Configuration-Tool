# ToDo — Meshtasticd Configuration Tool

Loose ends that need to be resolved before the tool is ready for public release.

---






## 6. Test TUI nano/suspend on Pi
**File:** `tui/app.py` line ~192 (`action_edit_config`)
Test that `with self.suspend(): subprocess.run(["nano", CONFIG_YAML])` restores
the terminal cleanly after nano exits on Raspberry Pi OS.



---

## 8. App icon asset missing
**File:** `install.sh` line ~68 (`desktop shortcut`)
No icon file exists yet. Create a PNG icon and add the `Icon=` line to the
`.desktop` file. Update `install.sh` to download the icon alongside the app files.

---

## 9. MeshAdv Pro — config file and EEPROM product string
**File:** `core/hardware.py` line ~68 (`HAT_DEFINITIONS`)
MeshAdv Pro is not yet released. When available:
- Confirm the EEPROM `product` string (used for detection)
- Create a dedicated `lora-MeshAdv-Pro-*.yaml` config file
- Update `HAT_DEFINITIONS["MeshAdv Pro"].config_yaml_name`

---

## 10. Pi Zero 2W UART device
**File:** `core/config_editor.py` `enable_gps_uart`
Confirm that the Pi Zero 2W uses `/dev/ttyS0` (not Pi5-class).
Currently `is_pi5_class` returns False for model_num=0, so `/dev/ttyS0` is used.
Verify this is correct for Zero 2W hardware.
