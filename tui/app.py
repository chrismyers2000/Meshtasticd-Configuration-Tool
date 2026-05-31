"""
tui/app.py — Textual TUI for the Meshtasticd Configuration Tool.
Works over SSH, PuTTY, and Windows SSH.
"""

from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    Footer,
    Header,
    Label,
    ListItem,
    ListView,
    RadioButton,
    RadioSet,
    RichLog,
    Static,
)
from textual.reactive import reactive
from textual import work

from core import actions, config_editor, hardware, installer
from core.actions import REGIONS
from core.hardware import SystemInfo, get_system_info


# ---------------------------------------------------------------------------
# CSS
# ---------------------------------------------------------------------------

CSS = """
Screen {
    background: #1a1a2e;
}

#hardware-panel {
    height: 1;
    background: #16213e;
    padding: 0 2;
    color: #00d4ff;
    content-align: left middle;
}

#main-area {
    height: 1fr;
}

#left-panel {
    width: 40;
    background: #16213e;
    border: solid #0f3460;
    padding: 1;
}

#right-panel {
    width: 1fr;
    background: #0d0d1a;
    border: solid #0f3460;
    padding: 1;
}

.section-title {
    color: #00d4ff;
    text-style: bold;
    margin-top: 1;
}

.btn-row {
    height: 3;
    margin-bottom: 0;
}

.btn-row Button {
    width: 22;
    height: 3;
    min-height: 3;
}

.status-ok    { color: #2ecc71; }
.status-warn  { color: #e74c3c; }
.status-amber { color: #f39c12; }

#reboot-bar {
    background: #e67e22;
    color: white;
    height: 1;
    padding: 0 2;
    display: none;
}

#reboot-bar.visible {
    display: block;
}

#config-bar {
    background: #e67e22;
    color: white;
    height: 1;
    padding: 0 2;
    display: none;
}

#config-bar.visible {
    display: block;
}

ModalScreen {
    background: #000000 60%;
    align: center middle;
}

#modal-box {
    background: #1a1a2e;
    border: solid #00d4ff;
    padding: 2;
    width: 60;
    height: auto;
    max-height: 40;
}

#status-popup {
    background: #1a1a2e;
    border: solid #00d4ff;
    padding: 2;
    width: 80;
    height: 30;
}
"""


# ---------------------------------------------------------------------------
# Helper: status row
# ---------------------------------------------------------------------------

class StatusRow(Static):
    """A label + status label pair."""

    def __init__(self, label: str, key: str, **kwargs):
        super().__init__(**kwargs)
        self._label_text = label
        self._key = key

    def compose(self) -> ComposeResult:
        with Horizontal(classes="btn-row"):
            yield Button(self._label_text, id=f"btn-{self._key}", variant="default")
            yield Label("—", id=f"status-{self._key}", classes="status-amber")


# ---------------------------------------------------------------------------
# Modal Screens
# ---------------------------------------------------------------------------

class InstallScreen(ModalScreen):
    """Channel selection for install."""

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Select install channel:", classes="section-title")
            with RadioSet(id="channel-set"):
                for ch in installer.CHANNELS:
                    yield RadioButton(ch.capitalize(), value=(ch == "beta"))
            with Horizontal():
                yield Button("Install", variant="primary", id="btn-confirm")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-confirm":
            radio_set = self.query_one("#channel-set", RadioSet)
            selected = radio_set.pressed_button
            channel = selected.label.plain.lower() if selected else "beta"
            self.dismiss(channel)


class RemoveScreen(ModalScreen):
    """Confirm removal."""

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Remove meshtasticd?", classes="section-title")
            yield Label("This will purge the package and its configuration.")
            with Horizontal():
                yield Button("Remove", variant="error", id="btn-confirm")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(event.button.id == "btn-confirm")


class DownloadYamlScreen(ModalScreen):
    """Choose which HAT YAML to download: Mini or Pro."""

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Download YAML:", classes="section-title")
            with RadioSet(id="yaml-set"):
                yield RadioButton("MeshAdv Mini  (lora-MeshAdv-Mini-900M22S.yaml)", value=True)
                yield RadioButton("MeshAdv Pro   (lora-MeshAdv-Pro-915M30S.yaml)")
            with Horizontal():
                yield Button("Download", variant="primary", id="btn-confirm")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-confirm":
            radio_set = self.query_one("#yaml-set", RadioSet)
            selected = radio_set.pressed_button
            label = selected.label.plain if selected else ""
            self.dismiss("pro" if "Pro" in label else "mini")


class HatConfigScreen(ModalScreen):
    """File browser for available.d configs."""

    def __init__(self, configs: list, hat=None, **kwargs) -> None:
        super().__init__(**kwargs)
        self._configs = configs
        self._hat = hat

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Select Hat Config:", classes="section-title")
            yield ListView(*self._build_items(self._configs), id="config-list")
            with Horizontal():
                yield Button("Download YAML", variant="warning", id="btn-download")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def _build_items(self, configs: list) -> list:
        items = []
        for i, cfg in enumerate(configs):
            prefix = f"[{cfg.subdir_name}] " if cfg.in_subdir else ""
            star = " ★" if cfg.is_default_for_hat else ""
            items.append(ListItem(Label(f"{prefix}{cfg.name}{star}"), id=f"cfg-{i}"))
        return items

    def on_list_view_selected(self, event: ListView.Selected) -> None:
        item_id = event.item.id or ""
        idx = int(item_id.removeprefix("cfg-"))
        filename = self._configs[idx].name
        self.dismiss(("select", filename))

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        elif event.button.id == "btn-download":
            self.app.push_screen(DownloadYamlScreen(), self._handle_download_choice)

    def _handle_download_choice(self, choice: str | None) -> None:
        if choice is None:
            return
        def _work():
            if choice == "pro":
                config_editor.download_pro_yaml()
            else:
                config_editor.download_mini_yaml()
            new_configs = config_editor.list_available_configs(self._hat)
            self.call_from_thread(self._refresh_list, new_configs)

        threading.Thread(target=_work, daemon=True).start()

    def _refresh_list(self, configs: list) -> None:
        list_view = self.query_one("#config-list", ListView)
        list_view.clear()
        for item in self._build_items(configs):
            list_view.append(item)



class RegionScreen(ModalScreen):
    """Region picker."""

    def compose(self) -> ComposeResult:
        with Container(id="modal-box"):
            yield Label("Select Region:", classes="section-title")
            with ScrollableContainer(id="region-scroll"):
                with RadioSet(id="region-set"):
                    for region in REGIONS:
                        yield RadioButton(region, value=(region == "US"))
            with Horizontal():
                yield Button("Set Region", variant="primary", id="btn-confirm")
                yield Button("Cancel", variant="default", id="btn-cancel")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        if event.button.id == "btn-cancel":
            self.dismiss(None)
        else:
            radio_set = self.query_one("#region-set", RadioSet)
            selected = radio_set.pressed_button
            region = selected.label.plain if selected else "US"
            self.dismiss(region)


class StatusOutputScreen(ModalScreen):
    """Display long text output (e.g. systemctl status)."""

    def __init__(self, title: str, content: str, **kwargs) -> None:
        super().__init__(**kwargs)
        self._title = title
        self._content = content

    def compose(self) -> ComposeResult:
        with Container(id="status-popup"):
            yield Label(self._title, classes="section-title")
            log = RichLog(highlight=False, markup=False, id="status-log")
            yield log
            yield Button("Close", variant="default", id="btn-close")

    def on_mount(self) -> None:
        log = self.query_one("#status-log", RichLog)
        log.write(self._content)

    def on_button_pressed(self, event: Button.Pressed) -> None:
        self.dismiss(None)


# ---------------------------------------------------------------------------
# Main TUI App
# ---------------------------------------------------------------------------

class MeshAdvTUI(App):
    CSS = CSS
    TITLE = "Meshtasticd Configuration Tool - by Frequency Labs"
    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("r", "refresh", "Refresh"),
    ]

    reboot_required: reactive[bool] = reactive(False)

    def __init__(self) -> None:
        super().__init__()
        self.sysinfo: Optional[SystemInfo] = None

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("Detecting hardware...", id="hardware-panel")

        with Horizontal(id="main-area"):
            with ScrollableContainer(id="left-panel"):
                yield Label("Configuration Options", classes="section-title")
                yield StatusRow("Install/Remove",    "install")
                yield StatusRow("Enable SPI",        "spi")
                yield StatusRow("Enable I2C",        "i2c")
                yield StatusRow("Enable GPS/UART",   "uart")
                yield StatusRow("Set Hat Config",    "hat_config")
                yield StatusRow("Edit Config",       "edit_config")

                yield Label("Actions", classes="section-title")
                yield StatusRow("Enable on Boot",    "svc_enable")
                yield StatusRow("Start Service",     "svc_start")
                yield StatusRow("Stop Service",      "svc_stop")
                yield StatusRow("Service Status",    "svc_status")
                yield StatusRow("Install Python CLI","python_cli")
                yield StatusRow("Set Region",        "region")
                yield StatusRow("Send Test Message", "send_msg")

                yield Label("Extras", classes="section-title")
                yield StatusRow("Enable Web Server",    "web_enable")
                yield StatusRow("Launch Web Interface", "web_launch")

            with Container(id="right-panel"):
                yield Label("Output", classes="section-title")
                yield RichLog(highlight=False, markup=False, id="output-log")

        yield Static("  Reboot required for changes to take effect.", id="reboot-bar")
        yield Static("  A service restart is required after making changes to config.yaml.", id="config-bar")
        yield Footer()

    def on_mount(self) -> None:
        self._load_hardware()

    # ------------------------------------------------------------------
    # Hardware detection
    # ------------------------------------------------------------------

    @work(thread=True)
    def _load_hardware(self) -> None:
        self.log_output("Detecting hardware...")
        info = get_system_info()
        self.call_from_thread(self._apply_hardware, info)

    def _apply_hardware(self, info: SystemInfo) -> None:
        self.sysinfo = info
        hw_panel = self.query_one("#hardware-panel", Static)
        hw_panel.update(
            f"Pi: {info.pi}  |  HAT: {info.hat}  |  meshtasticd: {info.meshtasticd_version}  |  OS: {info.os}"
        )
        self.log_output(f"Pi: {info.pi}")
        self.log_output(f"HAT: {info.hat}")
        self.log_output(f"OS: {info.os}")
        self._refresh_status()

    # ------------------------------------------------------------------
    # Button dispatch
    # ------------------------------------------------------------------

    def on_button_pressed(self, event: Button.Pressed) -> None:
        btn_id = event.button.id or ""
        dispatch = {
            "btn-install":      self.action_install_remove,
            "btn-spi":          self.action_enable_spi,
            "btn-i2c":          self.action_enable_i2c,
            "btn-uart":         self.action_enable_gps_uart,
            "btn-hat_config":   self.action_set_hat_config,
            "btn-edit_config":  self.action_edit_config,
            "btn-svc_enable":   self.action_service_enable,
            "btn-svc_start":    self.action_service_start,
            "btn-svc_stop":     self.action_service_stop,
            "btn-svc_status":   self.action_service_status,
            "btn-python_cli":   self.action_install_cli,
            "btn-region":       self.action_set_region,
            "btn-send_msg":     self.action_send_message,
            "btn-web_enable":   self.action_enable_webserver,
            "btn-web_launch":   self.action_launch_web_interface,
        }
        handler = dispatch.get(btn_id)
        if handler:
            handler()

    # ------------------------------------------------------------------
    # Actions
    # ------------------------------------------------------------------

    def action_install_remove(self) -> None:
        if installer.is_installed():
            self.push_screen(RemoveScreen(), self._handle_remove_confirm)
        else:
            self.push_screen(InstallScreen(), self._handle_install_channel)

    def _handle_remove_confirm(self, confirmed: Optional[bool]) -> None:
        if confirmed:
            self._run_worker(installer.remove, log=self.log_output)

    def _handle_install_channel(self, channel: Optional[str]) -> None:
        if channel and self.sysinfo:
            self._run_worker(installer.install, channel, self.sysinfo.os, log=self.log_output)

    def action_enable_spi(self) -> None:
        if config_editor.is_spi_enabled():
            self.log_output("SPI is already enabled.")
            return
        self._run_worker(config_editor.enable_spi, log=self.log_output, reboot=True)

    def action_enable_i2c(self) -> None:
        if config_editor.is_i2c_enabled():
            self.log_output("I2C is already enabled.")
            return
        self._run_worker(config_editor.enable_i2c, log=self.log_output, reboot=True)

    def action_enable_gps_uart(self) -> None:
        if self.sysinfo is None:
            return
        self._run_worker(
            config_editor.enable_gps_uart,
            self.sysinfo.pi,
            self.sysinfo.hat,
            log=self.log_output,
            reboot=True,
        )

    def action_set_hat_config(self) -> None:
        if self.sysinfo is None:
            return
        if self.sysinfo.hat.name.startswith("MeshAdv Pro"):
            if config_editor._find_in_available_d(config_editor.PRO_YAML_FILENAME) is None:
                self.log_output("MeshAdv Pro detected — downloading Pro config YAML...")
                config_editor.ensure_pro_yaml_available(log=self.log_output)
        configs = config_editor.list_available_configs(self.sysinfo.hat)
        if not configs:
            self.log_output(f"No config files found in {config_editor.AVAILABLE_D}.")
            return
        self.push_screen(HatConfigScreen(configs, hat=self.sysinfo.hat), self._handle_hat_config)

    def _handle_hat_config(self, result) -> None:
        if result is None:
            return
        action, filename = result
        if action == "select" and filename:
            def _do():
                ok, reboot_needed = config_editor.set_hat_config(filename, log=self.log_output)
                if reboot_needed:
                    self.call_from_thread(self.log_output, "GPIO change applied — reboot required.")
                    self.call_from_thread(setattr, self, "reboot_required", True)
                self.call_from_thread(self._refresh_status)
            threading.Thread(target=_do, daemon=True).start()

    def action_edit_config(self) -> None:
        import os
        if not os.path.isfile(config_editor.CONFIG_YAML):
            self.log_output("config.yaml not found. Is meshtasticd installed?")
            return
        with self.suspend():
            subprocess.run(["sudo", "nano", config_editor.CONFIG_YAML])

    def action_service_enable(self) -> None:
        self._run_worker(actions.service_enable)

    def action_service_start(self) -> None:
        def _do_start():
            ok, out = actions.service_start()
            if not ok:
                self.call_from_thread(self.log_output, "Start failed — running reset-failed and retrying...")
                actions.service_reset_failed()
                ok2, out2 = actions.service_start()
                if not ok2:
                    self.call_from_thread(self.log_output, "Retry also failed.")
            self.call_from_thread(self._refresh_status)
        threading.Thread(target=_do_start, daemon=True).start()

    def action_service_stop(self) -> None:
        self._run_worker(actions.service_stop)

    def action_service_status(self) -> None:
        def _do():
            ok, output = actions.service_status()
            self.call_from_thread(
                self.push_screen, StatusOutputScreen("Service Status", output)
            )
        self._run_background(_do)

    def action_install_cli(self) -> None:
        self._run_worker(actions.install_python_cli, log=self.log_output)

    def action_set_region(self) -> None:
        self.push_screen(RegionScreen(), self._handle_region)

    def _handle_region(self, region: Optional[str]) -> None:
        if region:
            self._run_worker(actions.set_region, region, log=self.log_output)

    def action_send_message(self) -> None:
        self._run_worker(actions.send_test_message, log=self.log_output)

    def action_enable_webserver(self) -> None:
        self.query_one("#config-bar", Static).add_class("visible")
        self._run_worker(config_editor.enable_webserver, log=self.log_output)

    def action_launch_web_interface(self) -> None:
        from core.utils import get_local_ip
        from rich.text import Text
        ip = get_local_ip()
        port = config_editor.get_webserver_port()
        url = f"https://{ip}:{port}"
        self.log_output(f"Web interface URL: {url}")
        try:
            log = self.query_one("#output-log", RichLog)
            note = Text("  (you may need to hold Ctrl while clicking)", style="dim")
            log.write(note)
        except Exception:
            pass

    def action_refresh(self) -> None:
        self.log_output("Refreshing status...")
        self._load_hardware()

    # ------------------------------------------------------------------
    # Status refresh
    # ------------------------------------------------------------------

    @work(thread=True)
    def _refresh_status(self) -> None:
        sysinfo = self.sysinfo
        if sysinfo is None:
            return

        installed = installer.is_installed()
        self.call_from_thread(self._set_status, "install",
                              "Installed" if installed else "Not installed",
                              "ok" if installed else "warn")

        spi = config_editor.is_spi_enabled()
        self.call_from_thread(self._set_status, "spi",
                              "Enabled" if spi else "Disabled",
                              "ok" if spi else "warn")

        i2c = config_editor.is_i2c_enabled()
        self.call_from_thread(self._set_status, "i2c",
                              "Enabled" if i2c else "Disabled",
                              "ok" if i2c else "warn")

        uart = config_editor.is_uart_enabled(sysinfo.pi)
        self.call_from_thread(self._set_status, "uart",
                              "Enabled" if uart else "Disabled",
                              "ok" if uart else "warn")

        hat_cfg = config_editor.get_hat_config_in_use()
        self.call_from_thread(self._set_status, "hat_config",
                              hat_cfg or "Not set",
                              "ok" if hat_cfg else "warn")

        import os
        cfg_exists = os.path.isfile(config_editor.CONFIG_YAML)
        self.call_from_thread(self._set_status, "edit_config",
                              "Available" if cfg_exists else "Not installed",
                              "ok" if cfg_exists else "warn")

        enabled = actions.service_is_enabled()
        active = actions.service_is_active()

        self.call_from_thread(self._set_status, "svc_enable",
                              "Enabled" if enabled else "Disabled",
                              "ok" if enabled else "warn")
        self.call_from_thread(self._set_status, "svc_start",
                              "Running" if active else "Stopped",
                              "ok" if active else "warn")
        self.call_from_thread(self._set_status, "svc_stop",
                              "Stopped" if not active else "Running",
                              "ok" if not active else "warn")
        self.call_from_thread(self._set_status, "svc_status",
                              "Active" if active else "Inactive",
                              "ok" if active else "warn")

        cli = actions.is_meshtastic_cli_installed()
        self.call_from_thread(self._set_status, "python_cli",
                              "Installed" if cli else "Not installed",
                              "ok" if cli else "warn")

        if cli:
            region = actions.get_current_region()
            self.call_from_thread(self._set_status, "region", region, "ok")
        else:
            self.call_from_thread(self._set_status, "region", "CLI not installed", "amber")

        self.call_from_thread(self._set_status, "send_msg",
                              "Ready" if cli else "CLI not installed",
                              "ok" if cli else "amber")

        web = config_editor.is_webserver_enabled()
        self.call_from_thread(self._set_status, "web_enable",
                              "Enabled" if web else "Disabled",
                              "ok" if web else "warn")
        self.call_from_thread(self._set_status, "web_launch", "Prints URL", "amber")

    def _set_status(self, key: str, text: str, state: str) -> None:
        try:
            lbl = self.query_one(f"#status-{key}", Label)
            css_class = {"ok": "status-ok", "warn": "status-warn", "amber": "status-amber"}.get(state, "status-amber")
            lbl.set_classes(css_class)
            lbl.update(text)
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Output log
    # ------------------------------------------------------------------

    def log_output(self, message: str) -> None:
        try:
            log = self.query_one("#output-log", RichLog)
            log.write(message.rstrip())
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Reactive: reboot warning
    # ------------------------------------------------------------------

    def watch_reboot_required(self, value: bool) -> None:
        bar = self.query_one("#reboot-bar", Static)
        if value:
            bar.add_class("visible")
        else:
            bar.remove_class("visible")

    # ------------------------------------------------------------------
    # Worker helpers
    # ------------------------------------------------------------------

    def _run_worker(self, func: Callable, *args, log=None, reboot: bool = False, **kwargs) -> None:
        """Run a core function in a background thread."""
        def _work():
            if log:
                result = func(*args, log=log, **kwargs)
            else:
                result = func(*args, **kwargs)
            self.call_from_thread(self._refresh_status)
            if reboot:
                self.call_from_thread(setattr, self, "reboot_required", True)

        threading.Thread(target=_work, daemon=True).start()

    def _run_background(self, func: Callable) -> None:
        """Run an arbitrary function in a background thread (no status refresh)."""
        threading.Thread(target=func, daemon=True).start()
