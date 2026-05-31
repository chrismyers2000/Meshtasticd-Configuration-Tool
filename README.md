# Meshtasticd Configuration Tool
**by Frequency Labs**

A graphical and terminal-based tool for installing and configuring [meshtasticd](https://meshtastic.org/) on Raspberry Pi hardware with MeshAdv Pi Hats.

---
![](https://github.com/chrismyers2000/Meshtasticd-Configuration-Tool/blob/7631016758dd2cac8d7d936a6e8e82dc870ac2d1/gui/GUI.png)
---

## Supported Hardware

**Raspberry Pi models:**
- Raspberry Pi 2, 3, 4, 5
- Raspberry Pi 400, 500
- Raspberry Pi Zero 2W

**Operating Systems:**
- Raspberry Pi OS Bookworm (32-bit and 64-bit)
- Raspberry Pi OS Trixie (32-bit and 64-bit)

**MeshAdv Pi Hats:**
- MeshAdv Pi Hat v1.1
- MeshAdv Mini
- MeshAdv Pro

---

## Installation

Run the following command on your Raspberry Pi to download and install the tool:

```bash
curl -fsSL https://raw.githubusercontent.com/chrismyers2000/Meshtasticd-Configuration-Tool/refs/heads/main/install.sh | bash
```


---

## Running the Tool

Navigate to the install directory and run:

```bash
python3 ~/meshadv-config/meshadv-config.py
```

### Display mode auto-detection

The tool automatically selects the right interface based on your environment:

| Environment | Interface launched |
|---|---|
| Raspberry Pi desktop (with display) | GUI (CustomTkinter) |
| SSH / PuTTY / headless | TUI (terminal, Textual) |

### Command-line flags

You can force a specific interface regardless of environment:

```bash
# Force the graphical GUI
python3 meshadv-config.py --gui

# Force the terminal TUI (useful over SSH or on a Pi with a desktop)
python3 meshadv-config.py --tui
```

---

## Interface Overview

Both the GUI and TUI offer identical features. The layout consists of three areas:

1. **Hardware Information** — shows detected Pi model, HAT, and meshtasticd version at the top
2. **Configuration Options** — buttons for installing and configuring the system (left panel)
3. **Actions** — buttons for controlling the meshtasticd service and CLI tools (below Configuration Options)
4. **Output log** — real-time output from all operations (right panel)

Status indicators appear next to each button showing the current state (e.g. Enabled / Disabled, Installed / Not installed).

---

## Hardware Information Panel

Displayed automatically at startup. Shows:

- **Pi Model** — detected from `/proc/device-tree/model`
- **Hat** — detected from the HAT EEPROM. If no EEPROM is found, defaults to *MeshAdv Pi Hat v1.1* (which has no EEPROM by design). In the GUI, a **Detect HAT** button is available to manually read the HAT EEPROM at any time, without needing to reboot with the HAT connected.
- **meshtasticd** — installed version, or *Not installed*
- **OS** — distro name, version codename, and bit-width (TUI only)

---

## Configuration Options

### Install / Remove meshtasticd

Opens a dialog to install or remove meshtasticd.

**Installing:**
- Select a release channel: **Stable**, **Beta**, **Alpha**, or **Daily**
- The tool automatically detects your OS version (Bookworm/Trixie) and architecture (32/64-bit) and uses the correct repository
- Adds the apt source, imports the GPG key, runs `apt-get update`, then installs the package

**Removing:**
- Confirms before proceeding
- Runs `apt-get purge meshtasticd` and cleans up the apt source and GPG key files

> The status label shows **Installed** or **Not installed**.

---

### Enable SPI

Checks `/boot/firmware/config.txt` for the following lines and adds them if missing:

```
dtparam=spi=on
dtoverlay=spi0-0cs
```

A **Reboot required** warning appears at the bottom of the window after this change. Reboot your Pi for SPI to activate.

> The status label shows **Enabled** or **Disabled**.

---

### Enable I2C

Checks `/boot/firmware/config.txt` for the following line and adds it if missing:

```
dtparam=i2c_arm=on
```

A **Reboot required** warning appears after this change.

> The status label shows **Enabled** or **Disabled**.

---

### Enable GPS / UART

Configures UART and GPS support in `/boot/firmware/config.txt` and `/etc/meshtasticd/config.yaml`.

What gets added depends on your hardware:

| Setting | When added |
|---|---|
| `enable_uart=1` | All Pi models |
| `dtoverlay=uart0` | Pi 5 and Pi 500 only |
| `dtoverlay=pps-gpio,gpiopin=17` | MeshAdv Mini and Pro only |
| `gpio=4=op,dh` | MeshAdv Mini and Pro only |

In `config.yaml`, the GPS `SerialPath` is uncommented and set to:
- `/dev/ttyAMA0` — Pi 5 and Pi 500
- `/dev/ttyS0` — all other Pi models

A **Reboot required** warning appears after this change.

> The status label shows **Enabled** or **Disabled**.

---

### Set Hat Config

Opens a file browser showing all available config files from `/etc/meshtasticd/available.d/`, including any subdirectories.

- The recommended file for your detected HAT is highlighted with a **★** marker
- Select a file to copy it into `/etc/meshtasticd/config.d/` (replacing any existing config)
- A **Download YAML** button is available to download either the Mini or Pro config YAML directly from the Frequency Labs GitHub if the file is missing or needs to be refreshed

Default config files by HAT:

| HAT | Default config file |
|---|---|
| MeshAdv Pi Hat v1.1 | `lora-MeshAdv-900M30S.yaml` |
| MeshAdv Mini | `lora-MeshAdv-Mini-900M22S.yaml` |
| MeshAdv Pro | `lora-MeshAdv-Pro-915M30S.yaml` |

When a MeshAdv Pro config is selected, `gpio=12=op,dh` is automatically added to `/boot/firmware/config.txt` to enable the required GPIO pin. This line is removed automatically if you switch to a non-Pro config. A **Reboot required** warning will appear after either change.

> The status label shows the filename currently in use, or **Not set**.

---

### Edit Config

Opens `/etc/meshtasticd/config.yaml` in `nano` for manual editing.

- **GUI mode:** Opens nano in a new terminal window (`x-terminal-emulator`)
- **TUI mode:** Suspends the TUI, opens nano in the current terminal, then restores the TUI when you exit nano

> The status label shows **Available** if `config.yaml` exists, or **Not installed** otherwise.

---

## Actions

### Enable on Boot

Runs `sudo systemctl enable meshtasticd` so the service starts automatically after every reboot.

> The status label shows **Enabled** or **Disabled**.

---

### Start Service

Runs `sudo systemctl start meshtasticd` to start the service immediately without rebooting.

> The status label shows **Running** or **Stopped**.

---

### Stop Service

Runs `sudo systemctl stop meshtasticd` to stop the running service.

> The status label shows **Stopped** or **Running**.

---

### Service Status

Runs `sudo systemctl status meshtasticd` and displays the full output in a scrollable popup window. Use this to check for errors or confirm the service is running correctly.

---

### Install Python CLI

Installs the meshtastic Python CLI (`meshtastic[cli]`), which is required for the **Set Region** and **Send Test Message** features.

Install steps:
1. Checks for Python 3 (installs via apt if missing)
2. Checks for pip3 (installs via apt if missing)
3. Runs `pip3 install --upgrade "meshtastic[cli]"`
4. If pip3 is blocked by a system-managed environment, automatically falls back to `pipx`

Progress is shown in real time in the output log.

> The status label shows **Installed** or **Not installed**.

---

### Set Region

Opens a region picker and sets the Meshtastic LoRa region using the CLI.

Available regions:

| | | | |
|---|---|---|---|
| UNSET | US | EU_433 | EU_868 |
| CN | JP | ANZ | KR |
| TW | RU | IN | NZ_865 |
| TH | UA_433 | UA_868 | MY_433 |
| MY_919 | SG_923 | | |

> Requires the meshtastic Python CLI to be installed and meshtasticd to be running.
> The status label shows your currently configured region.

---

### Send Test Message

Sends a test text message (`Test message from MeshAdv Config Tool`) to the default Meshtastic channel using the CLI.

> Requires the meshtastic Python CLI to be installed and meshtasticd to be running.

---

## TUI Keyboard Shortcuts

These shortcuts are available when running in TUI mode (over SSH or with `--tui`):

| Key | Action |
|---|---|
| `Q` | Quit the application |
| `R` | Refresh all status indicators and re-detect hardware |
| `Tab` | Move focus between elements |
| `Enter` | Activate the focused button |
| Arrow keys | Navigate lists and radio buttons in dialogs |

---

## Reboot Required Warning

After making any changes to `/boot/firmware/config.txt` (SPI, I2C, GPS/UART, or selecting/deselecting a MeshAdv Pro HAT config), a **Reboot required** banner appears at the bottom of the window. These changes only take effect after a reboot.

To reboot:
```bash
sudo reboot
```

---

## File Locations

| File | Purpose |
|---|---|
| `/boot/firmware/config.txt` | Pi hardware configuration (SPI, I2C, UART overlays) |
| `/etc/meshtasticd/config.yaml` | meshtasticd main configuration |
| `/etc/meshtasticd/available.d/` | Available HAT config files |
| `/etc/meshtasticd/config.d/` | Active HAT config (one file placed here) |
| `/etc/apt/sources.list.d/` | meshtasticd apt repository source |
| `/etc/apt/trusted.gpg.d/` | meshtasticd apt GPG key |

---

## Troubleshooting

**"No config files found in available.d"**
meshtasticd is either not installed or the available.d directory is missing. Install meshtasticd first, then try again. You can also use the **Download YAML** button in the Set Hat Config dialog to fetch the Mini config from GitHub.

**"Command not found: meshtastic"**
The meshtastic Python CLI is not installed. Use the **Install Python CLI** button. If you installed via pipx, you may need to close and reopen your terminal, or run `pipx ensurepath` and start a new session.

**Service fails to start**
Use **Service Status** to view the full error output from `systemctl`. Common causes:
- HAT config not set (use **Set Hat Config**)
- SPI not enabled (use **Enable SPI** then reboot)
- Incorrect serial path in `config.yaml` (use **Enable GPS/UART** to set it automatically)

**GUI doesn't open over SSH**
SSH sessions don't have a display. Either run with `--tui` for the terminal interface, or use SSH X11 forwarding (`ssh -X`) if you need the GUI remotely.

**pip3 install fails with "externally managed environment"**
This is normal on newer Raspberry Pi OS versions. The tool automatically falls back to `pipx`. If you're running **Install Python CLI** manually, use:
```bash
sudo apt install pipx && pipx install "meshtastic[cli]" && pipx ensurepath
```


```

