"""
gui/app.py — CustomTkinter GUI for the Meshtasticd Configuration Tool.
"""

from __future__ import annotations

import subprocess
import threading
from typing import Callable, Optional

import customtkinter as ctk

from core import actions, config_editor, hardware, installer
from core.actions import REGIONS
from core.hardware import SystemInfo, get_system_info


# ---------------------------------------------------------------------------
# Theme
# ---------------------------------------------------------------------------

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")

COLOR_OK      = "#2ecc71"   # green — enabled/installed
COLOR_WARN    = "#e74c3c"   # red — disabled/not installed
COLOR_UNKNOWN = "#f39c12"   # amber — unknown/partial
COLOR_REBOOT  = "#e67e22"   # orange — reboot required


def _safe_grab(window) -> None:
    """Grab input focus safely — ignores errors if the window was already closed."""
    try:
        window.wait_visibility()
        window.grab_set()
    except Exception:
        pass


def _bind_scroll_to_frame(scroll_frame: ctk.CTkScrollableFrame) -> None:
    """Forward mouse-wheel events on child widgets to the scrollable frame's canvas.

    CTkScrollableFrame doesn't propagate scroll events from child widgets,
    so the scroll wheel stops working when the cursor is over a button or label.
    This helper binds the events recursively so scrolling always works.
    """
    canvas = scroll_frame._parent_canvas

    def _scroll(event):
        if event.num == 4:
            canvas.yview_scroll(-1, "units")
        elif event.num == 5:
            canvas.yview_scroll(1, "units")
        elif event.delta:
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")

    def _bind_recursive(widget):
        widget.bind("<Button-4>", _scroll, add="+")
        widget.bind("<Button-5>", _scroll, add="+")
        widget.bind("<MouseWheel>", _scroll, add="+")
        for child in widget.winfo_children():
            _bind_recursive(child)

    _bind_recursive(scroll_frame)


# ---------------------------------------------------------------------------
# Main App Window
# ---------------------------------------------------------------------------

class MeshAdvApp(ctk.CTk):
    def __init__(self) -> None:
        super().__init__()
        self.title("Meshtasticd Configuration Tool - by Frequency Labs")
        # Tall enough to show all buttons without scrolling
        self.geometry("1000x820")
        self.minsize(900, 750)
        self.resizable(True, True)

        self.sysinfo: Optional[SystemInfo] = None
        self.reboot_required: bool = False
        self._status_labels: dict[str, ctk.CTkLabel] = {}

        self._build_ui()
        self._load_system_info()

    # ------------------------------------------------------------------
    # UI construction
    # ------------------------------------------------------------------

    def _build_ui(self) -> None:
        # Two columns: left (fixed ~360px) and right (expanding output log)
        self.grid_columnconfigure(0, weight=0, minsize=360)
        self.grid_columnconfigure(1, weight=1)
        # Main content row expands
        self.grid_rowconfigure(0, weight=1)
        # Reboot bar row fixed height
        self.grid_rowconfigure(1, weight=0)
        # Service restart bar row fixed height
        self.grid_rowconfigure(2, weight=0)

        self._build_left_column()
        self._build_output_panel()
        self._build_status_bar()

    def _build_left_column(self) -> None:
        """Build the entire left column: title + hardware info + all buttons."""
        left = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        left.grid(row=0, column=0, sticky="nsew", padx=(10, 4), pady=10)
        left.grid_columnconfigure(0, weight=1)

        row = 0

        # --- Title ---
        ctk.CTkLabel(
            left,
            text="Meshtasticd Config Tool",
            font=ctk.CTkFont(size=17, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=4, pady=(0, 8))
        row += 1

        # --- Hardware Info (stacked) ---
        row = self._build_hardware_panel(left, row)

        # --- Configuration Options ---
        ctk.CTkLabel(
            left,
            text="Configuration Options",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=4, pady=(14, 4))
        row += 1

        config_buttons = [
            ("Install / Remove meshtasticd", "install",     self.on_install_remove),
            ("Enable SPI",                   "spi",         self.on_enable_spi),
            ("Enable I2C",                   "i2c",         self.on_enable_i2c),
            ("Enable GPS / UART",            "uart",        self.on_enable_gps_uart),
            ("Set Hat Config",               "hat_config",  self.on_set_hat_config),
            ("Edit Config",                  "edit_config", self.on_edit_config),
        ]
        buttons_frame = ctk.CTkFrame(left, corner_radius=8)
        buttons_frame.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
        buttons_frame.grid_columnconfigure(1, weight=1)
        row += 1

        btn_row = 0
        for label, key, cmd in config_buttons:
            btn_row = self._add_button_row(buttons_frame, btn_row, label, key, cmd)

        # --- Actions ---
        ctk.CTkLabel(
            left,
            text="Actions",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=4, pady=(14, 4))
        row += 1

        action_buttons = [
            ("Services",             "services",    self.on_services),
            ("Install Python CLI",   "python_cli",  self.on_install_python_cli),
            ("Set Region",           "region",      self.on_set_region),
            ("Send Test Message",    "send_msg",    self.on_send_message),
        ]
        actions_frame = ctk.CTkFrame(left, corner_radius=8)
        actions_frame.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
        actions_frame.grid_columnconfigure(1, weight=1)
        row += 1

        btn_row = 0
        for label, key, cmd in action_buttons:
            btn_row = self._add_button_row(actions_frame, btn_row, label, key, cmd)

        # --- Extras ---
        ctk.CTkLabel(
            left,
            text="Extras",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=row, column=0, sticky="w", padx=4, pady=(14, 4))
        row += 1

        web_buttons = [
            ("Enable Web Server",    "web_enable", self.on_enable_webserver),
            ("Launch Web Interface", "web_launch", self.on_launch_web_interface),
        ]
        web_frame = ctk.CTkFrame(left, corner_radius=8)
        web_frame.grid(row=row, column=0, sticky="ew", padx=0, pady=0)
        web_frame.grid_columnconfigure(1, weight=1)
        row += 1

        btn_row = 0
        for label, key, cmd in web_buttons:
            btn_row = self._add_button_row(web_frame, btn_row, label, key, cmd)

    def _build_hardware_panel(self, parent, start_row: int) -> int:
        """Build stacked hardware info rows. Returns the next available row index."""
        frame = ctk.CTkFrame(parent, corner_radius=8)
        frame.grid(row=start_row, column=0, sticky="ew", padx=0, pady=0)
        frame.grid_columnconfigure(1, weight=1)
        frame.grid_columnconfigure(2, weight=0)

        info_items = [
            ("Pi Model:",    "hw_pi_model"),
            ("Hat:",         "hw_hat"),
            ("meshtasticd:", "hw_version"),
        ]
        for i, (label_text, key) in enumerate(info_items):
            ctk.CTkLabel(
                frame,
                text=label_text,
                font=ctk.CTkFont(weight="bold"),
                anchor="w",
                width=110,
            ).grid(row=i, column=0, padx=(12, 6), pady=5, sticky="w")

            val_label = ctk.CTkLabel(frame, text="Detecting...", anchor="w")
            val_label.grid(row=i, column=1, padx=(0, 4), pady=5, sticky="w")
            self._status_labels[key] = val_label

            if key == "hw_hat":
                ctk.CTkButton(
                    frame, text="Detect HAT", width=100,
                    command=self.on_detect_hat_manual,
                ).grid(row=i, column=2, padx=(0, 12), pady=5, sticky="w")

        # Grey note below the Hat row
        ctk.CTkLabel(
            frame,
            text="Note: Hat needs to be installed at time of boot for detection",
            text_color="gray60",
            font=ctk.CTkFont(size=11),
            anchor="w",
        ).grid(row=3, column=0, columnspan=3, padx=(16, 12), pady=(0, 6), sticky="w")

        return start_row + 1

    def _add_button_row(
        self,
        parent,
        row: int,
        label: str,
        key: str,
        command: Callable,
    ) -> int:
        btn = ctk.CTkButton(
            parent,
            text=label,
            command=command,
            width=200,
            anchor="w",
        )
        btn.grid(row=row, column=0, padx=(10, 6), pady=4, sticky="w")

        status_lbl = ctk.CTkLabel(parent, text="—", anchor="w")
        status_lbl.grid(row=row, column=1, padx=(0, 10), pady=4, sticky="w")
        self._status_labels[key] = status_lbl

        return row + 1

    def _build_output_panel(self) -> None:
        frame = ctk.CTkFrame(self, corner_radius=8)
        frame.grid(row=0, column=1, padx=(4, 10), pady=10, sticky="nsew")
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        ctk.CTkLabel(
            frame,
            text="Output",
            font=ctk.CTkFont(size=13, weight="bold"),
        ).grid(row=0, column=0, padx=10, pady=(8, 2), sticky="w")

        self._output_box = ctk.CTkTextbox(frame, wrap="word", state="disabled")
        self._output_box.grid(row=1, column=0, padx=8, pady=(0, 8), sticky="nsew")

    def _build_status_bar(self) -> None:
        self._reboot_bar = ctk.CTkLabel(
            self,
            text="  ⚠  Reboot required for changes to take effect.",
            fg_color=COLOR_REBOOT,
            text_color="white",
            corner_radius=0,
            anchor="w",
            height=28,
        )
        self._service_bar = ctk.CTkLabel(
            self,
            text="  ⚠  A service restart is required after making changes to config.yaml",
            fg_color=COLOR_REBOOT,
            text_color="white",
            corner_radius=0,
            anchor="w",
            height=28,
        )
        # Gridded only when needed

    # ------------------------------------------------------------------
    # Data loading
    # ------------------------------------------------------------------

    def _load_system_info(self) -> None:
        self.log("Detecting hardware...")
        self._run_in_thread(self._detect_hardware)

    def _detect_hardware(self) -> None:
        info = get_system_info()
        self.after(0, self._apply_system_info, info)

    def _apply_system_info(self, info: SystemInfo) -> None:
        self.sysinfo = info
        self._set_label("hw_pi_model", str(info.pi))
        self._set_label("hw_hat",      str(info.hat))
        self._set_label("hw_version",  info.meshtasticd_version)
        self.log(f"Pi: {info.pi}")
        self.log(f"HAT: {info.hat}")
        self.log(f"OS: {info.os}")
        self.log(f"meshtasticd: {info.meshtasticd_version}")
        self.refresh_all_status()

    def _refresh_everything(self) -> None:
        """Re-detect hardware (updates version label) then refresh all status labels."""
        self._run_in_thread(self._detect_hardware)

    # ------------------------------------------------------------------
    # Status management
    # ------------------------------------------------------------------

    def refresh_all_status(self) -> None:
        self._run_in_thread(self._refresh_status_worker)

    def _refresh_status_worker(self) -> None:
        sysinfo = self.sysinfo
        if sysinfo is None:
            return

        installed = installer.is_installed()
        self.after(0, self._set_status, "install",
                   "Installed" if installed else "Not installed",
                   COLOR_OK if installed else COLOR_WARN)

        spi = config_editor.is_spi_enabled()
        self.after(0, self._set_status, "spi",
                   "Enabled" if spi else "Disabled",
                   COLOR_OK if spi else COLOR_WARN)

        i2c = config_editor.is_i2c_enabled()
        self.after(0, self._set_status, "i2c",
                   "Enabled" if i2c else "Disabled",
                   COLOR_OK if i2c else COLOR_WARN)

        uart = config_editor.is_uart_enabled(sysinfo.pi)
        self.after(0, self._set_status, "uart",
                   "Enabled" if uart else "Disabled",
                   COLOR_OK if uart else COLOR_WARN)

        hat_cfg = config_editor.get_hat_config_in_use()
        self.after(0, self._set_status, "hat_config",
                   hat_cfg or "Not set",
                   COLOR_OK if hat_cfg else COLOR_WARN)

        import os
        cfg_exists = os.path.isfile(config_editor.CONFIG_YAML)
        self.after(0, self._set_status, "edit_config",
                   "Available" if cfg_exists else "Not installed",
                   COLOR_OK if cfg_exists else COLOR_WARN)

        enabled = actions.service_is_enabled()
        active = actions.service_is_active()
        if active:
            svc_text, svc_color = "Running", COLOR_OK
        elif enabled:
            svc_text, svc_color = "Stopped (boot enabled)", COLOR_UNKNOWN
        else:
            svc_text, svc_color = "Stopped", COLOR_WARN
        self.after(0, self._set_status, "services", svc_text, svc_color)

        cli = actions.is_meshtastic_cli_installed()
        self.after(0, self._set_status, "python_cli",
                   "Installed" if cli else "Not installed",
                   COLOR_OK if cli else COLOR_WARN)

        if cli:
            region = actions.get_current_region()
            self.after(0, self._set_status, "region", region, COLOR_OK)
        else:
            self.after(0, self._set_status, "region", "CLI not installed", COLOR_UNKNOWN)

        self.after(0, self._set_status, "send_msg",
                   "Ready" if cli else "CLI not installed",
                   COLOR_OK if cli else COLOR_UNKNOWN)

        web = config_editor.is_webserver_enabled()
        self.after(0, self._set_status, "web_enable",
                   "Enabled" if web else "Disabled",
                   COLOR_OK if web else COLOR_WARN)

    def _set_status(self, key: str, text: str, color: str) -> None:
        lbl = self._status_labels.get(key)
        if lbl:
            lbl.configure(text=text, text_color=color)

    def _set_label(self, key: str, text: str) -> None:
        lbl = self._status_labels.get(key)
        if lbl:
            lbl.configure(text=text)

    def _show_reboot_warning(self) -> None:
        self.reboot_required = True
        self._reboot_bar.grid(row=1, column=0, columnspan=2, sticky="ew")

    def _show_service_warning(self) -> None:
        self._service_bar.grid(row=2, column=0, columnspan=2, sticky="ew")

    # ------------------------------------------------------------------
    # Output log
    # ------------------------------------------------------------------

    def log(self, message: str) -> None:
        self.after(0, self._append_log, message)

    def _append_log(self, message: str) -> None:
        self._output_box.configure(state="normal")
        self._output_box.insert("end", message.rstrip() + "\n")
        self._output_box.see("end")
        self._output_box.configure(state="disabled")

    # ------------------------------------------------------------------
    # Button handlers
    # ------------------------------------------------------------------

    def on_install_remove(self) -> None:
        if self.sysinfo is None:
            return
        installed = installer.is_installed()
        if installed:
            if not self._confirm("Remove meshtasticd?\nThis will purge the package and its config."):
                return
            self._run_in_thread(
                self._do_remove,
                done_callback=lambda: (self._refresh_everything(), self.log("Done.")),
            )
        else:
            result = self._show_install_dialog()
            if result is None:
                return
            channel = result
            sysinfo = self.sysinfo
            self._run_in_thread(
                lambda: installer.install(channel, sysinfo.os, log=self.log),
                done_callback=lambda: (self._refresh_everything(), self.log("Done.")),
            )

    def _do_remove(self) -> None:
        installer.remove(log=self.log)

    def on_enable_spi(self) -> None:
        if config_editor.is_spi_enabled():
            self.log("SPI is already enabled.")
            return
        self._run_in_thread(
            lambda: config_editor.enable_spi(log=self.log),
            done_callback=lambda: (self.refresh_all_status(), self._show_reboot_warning()),
        )

    def on_enable_i2c(self) -> None:
        if config_editor.is_i2c_enabled():
            self.log("I2C is already enabled.")
            return
        self._run_in_thread(
            lambda: config_editor.enable_i2c(log=self.log),
            done_callback=lambda: (self.refresh_all_status(), self._show_reboot_warning()),
        )

    def on_enable_gps_uart(self) -> None:
        if self.sysinfo is None:
            return
        pi, hat = self.sysinfo.pi, self.sysinfo.hat
        self._run_in_thread(
            lambda: config_editor.enable_gps_uart(pi, hat, log=self.log),
            done_callback=lambda: (self.refresh_all_status(), self._show_reboot_warning()),
        )

    def on_detect_hat_manual(self) -> None:
        HatDetectDialog(self, self._on_hat_detect_result, log_callback=self.log)

    def _on_hat_detect_result(self, hat_info) -> None:
        if hat_info is not None and self.sysinfo is not None:
            self.sysinfo.hat = hat_info
            self._set_label("hw_hat", str(hat_info))
            self.refresh_all_status()

    def on_set_hat_config(self) -> None:
        if self.sysinfo is None:
            return
        if self.sysinfo.hat.name.startswith("MeshAdv Pro"):
            if config_editor._find_in_available_d(config_editor.PRO_YAML_FILENAME) is None:
                self.log("MeshAdv Pro detected — downloading Pro config YAML...")
                def _download_then_open():
                    config_editor.ensure_pro_yaml_available(log=self.log)
                    self.after(0, self._open_hat_config_dialog)
                threading.Thread(target=_download_then_open, daemon=True).start()
                return
        self._open_hat_config_dialog()

    def _open_hat_config_dialog(self) -> None:
        if self.sysinfo is None:
            return
        configs = config_editor.list_available_configs(self.sysinfo.hat)
        if not configs:
            self._show_error(
                f"No config files found in\n{config_editor.AVAILABLE_D}\n\n"
                "Is meshtasticd installed?"
            )
            return
        HatConfigDialog(self, configs, self._on_hat_config_selected, hat=self.sysinfo.hat, log_callback=self.log)

    def _on_hat_config_selected(self, filename: str) -> None:
        def _do():
            ok, reboot_needed = config_editor.set_hat_config(filename, log=self.log)
            self.after(0, self.refresh_all_status)
            if reboot_needed:
                self.after(0, self.log, "GPIO change applied — reboot required.")
                self.after(0, self._show_reboot_warning)
        threading.Thread(target=_do, daemon=True).start()

    def on_edit_config(self) -> None:
        import os
        if not os.path.isfile(config_editor.CONFIG_YAML):
            self._show_error("config.yaml not found.\nIs meshtasticd installed?")
            return
        path = config_editor.CONFIG_YAML
        for term in ["x-terminal-emulator", "lxterminal", "xterm", "gnome-terminal"]:
            try:
                subprocess.Popen([term, "-e", f"sudo nano {path}"])
                self._show_service_warning()
                return
            except FileNotFoundError:
                continue
        self._show_error(
            "No terminal emulator found.\n"
            f"Edit manually:\n  nano {path}"
        )

    def on_services(self) -> None:
        self._service_bar.grid_remove()
        ServicesDialog(self, log_callback=self.log, refresh_callback=self.refresh_all_status)

    def on_install_python_cli(self) -> None:
        self._run_in_thread(
            lambda: actions.install_python_cli(log=self.log),
            done_callback=self.refresh_all_status,
        )

    def on_set_region(self) -> None:
        RegionDialog(self, self._on_region_selected)

    def _on_region_selected(self, region: str) -> None:
        self._run_in_thread(
            lambda: actions.set_region(region, log=self.log),
            done_callback=self.refresh_all_status,
        )

    def on_send_message(self) -> None:
        self._run_in_thread(
            lambda: actions.send_test_message(log=self.log),
            done_callback=self.refresh_all_status,
        )

    def on_enable_webserver(self) -> None:
        self._show_service_warning()
        self._run_in_thread(
            lambda: config_editor.enable_webserver(log=self.log),
            done_callback=self.refresh_all_status,
        )

    def on_launch_web_interface(self) -> None:
        import webbrowser
        from core.utils import get_local_ip
        ip = get_local_ip()
        port = config_editor.get_webserver_port()
        webbrowser.open(f"https://{ip}:{port}")
        self.log(f"Opening https://{ip}:{port} in browser...")

    # ------------------------------------------------------------------
    # Dialogs
    # ------------------------------------------------------------------

    def _show_install_dialog(self) -> Optional[str]:
        dialog = InstallDialog(self)
        self.wait_window(dialog)
        return dialog.result

    def _show_status_popup(self, title: str, content: str) -> None:
        popup = ctk.CTkToplevel(self)
        popup.title(title)
        popup.geometry("620x440")
        popup.transient(self)
        popup.after(50, lambda: _safe_grab(popup))

        tb = ctk.CTkTextbox(popup, wrap="word")
        tb.pack(fill="both", expand=True, padx=12, pady=12)
        tb.insert("end", content)
        tb.configure(state="disabled")

        ctk.CTkButton(popup, text="Close", command=popup.destroy).pack(pady=(0, 12))

    def _show_error(self, message: str) -> None:
        popup = ctk.CTkToplevel(self)
        popup.title("Error")
        popup.geometry("420x220")
        popup.transient(self)
        popup.after(50, lambda: _safe_grab(popup))
        ctk.CTkLabel(popup, text=message, wraplength=380).pack(padx=16, pady=24, expand=True)
        ctk.CTkButton(popup, text="OK", command=popup.destroy).pack(pady=(0, 16))

    def _confirm(self, message: str) -> bool:
        dialog = ConfirmDialog(self, message)
        self.wait_window(dialog)
        return dialog.result

    # ------------------------------------------------------------------
    # Threading
    # ------------------------------------------------------------------

    def _run_in_thread(
        self,
        func: Callable,
        *args,
        done_callback: Optional[Callable] = None,
    ) -> None:
        def _worker():
            func(*args)
            if done_callback:
                self.after(0, done_callback)

        threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# Dialog windows
# ---------------------------------------------------------------------------

class InstallDialog(ctk.CTkToplevel):
    """Channel selection for install."""

    def __init__(self, parent) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Install meshtasticd")
        self.geometry("340x280")
        self.result: Optional[str] = None
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(self, text="Select channel:", font=ctk.CTkFont(size=13)).pack(padx=16, pady=(16, 8))

        self._channel_var = ctk.StringVar(value="beta")
        for ch in installer.CHANNELS:
            ctk.CTkRadioButton(
                self, text=ch.capitalize(), variable=self._channel_var, value=ch
            ).pack(anchor="w", padx=36, pady=3)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=16, fill="x", padx=16)
        ctk.CTkButton(btn_frame, text="Install", command=self._on_install).pack(
            side="left", expand=True, padx=4
        )
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray40", command=self.destroy).pack(
            side="left", expand=True, padx=4
        )

    def _on_install(self) -> None:
        self.result = self._channel_var.get()
        self.destroy()


class HatConfigDialog(ctk.CTkToplevel):
    """File browser for /etc/meshtasticd/available.d."""

    def __init__(
        self,
        parent,
        configs: list,
        callback: Callable[[str], None],
        hat=None,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Select Hat Config")
        self.geometry("440x460")
        self._callback = callback
        self._hat = hat
        self._log = log_callback
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(self, text="Select a config file:", font=ctk.CTkFont(size=13)).pack(
            padx=16, pady=(12, 6)
        )

        self._list_frame = ctk.CTkScrollableFrame(self, height=340)
        self._list_frame.pack(padx=12, pady=4, fill="both", expand=True)

        self._populate_list(configs)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10, fill="x", padx=16)
        ctk.CTkButton(
            btn_frame, text="Download YAML", fg_color="#8e44ad",
            command=self._on_download,
        ).pack(side="left", padx=4)
        ctk.CTkButton(
            btn_frame, text="Cancel", fg_color="gray40", command=self.destroy
        ).pack(side="right", padx=4)

    def _populate_list(self, configs: list) -> None:
        """Clear and repopulate the scrollable config list."""
        for widget in self._list_frame.winfo_children():
            widget.destroy()
        for cfg in configs:
            prefix = f"[{cfg.subdir_name}]  " if cfg.in_subdir else ""
            text = prefix + cfg.name
            if cfg.is_default_for_hat:
                text += "  ★ recommended"
            ctk.CTkButton(
                self._list_frame,
                text=text,
                anchor="w",
                fg_color="#2a6db5" if cfg.is_default_for_hat else "transparent",
                hover_color="#3a7dc5",
                command=lambda c=cfg: self._select(c),
            ).pack(fill="x", padx=4, pady=2)
        _bind_scroll_to_frame(self._list_frame)

    def _select(self, cfg) -> None:
        self._callback(cfg.name)
        self.destroy()

    def _on_download(self) -> None:
        DownloadYamlDialog(self, self._do_download)

    def _do_download(self, choice: str) -> None:
        log = self._log

        def _work():
            if choice == "pro":
                config_editor.download_pro_yaml(log=log)
            else:
                config_editor.download_mini_yaml(log=log)
            new_configs = config_editor.list_available_configs(self._hat)
            self.after(0, self._populate_list, new_configs)

        threading.Thread(target=_work, daemon=True).start()


_HAT_DETECT_WARNING = (
    "WARNING: This process will temporarily create an I2C bus on GPIO 0 and GPIO 1.\n\n"
    "Ensure nothing is connected to or using these pins before proceeding.\n\n"
    "The I2C bus will be removed automatically when detection is complete."
)


class HatDetectDialog(ctk.CTkToplevel):
    """Two-phase dialog: warning → live detection log."""

    def __init__(
        self,
        parent,
        callback: Callable,
        log_callback: Optional[Callable[[str], None]] = None,
    ) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Manual HAT Detection")
        self.geometry("520x300")
        self._callback = callback
        self._log_cb = log_callback
        self._result = None
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(
            self, text="Manual HAT Detection",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=16, pady=(14, 6))

        self._warn_label = ctk.CTkLabel(
            self, text=_HAT_DETECT_WARNING,
            wraplength=460, justify="left",
            text_color="orange",
        )
        self._warn_label.pack(padx=16, pady=(0, 12))

        self._log_box = ctk.CTkTextbox(self, wrap="word", state="disabled", height=160)

        self._btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        self._btn_frame.pack(pady=10, fill="x", padx=16)
        ctk.CTkButton(
            self._btn_frame, text="Proceed", fg_color="#e67e22",
            command=self._on_proceed,
        ).pack(side="left", expand=True, padx=4)
        ctk.CTkButton(
            self._btn_frame, text="Cancel", fg_color="gray40",
            command=self.destroy,
        ).pack(side="left", expand=True, padx=4)

        self._close_btn = ctk.CTkButton(self, text="Close", command=self._on_close)

    def _on_proceed(self) -> None:
        self._warn_label.pack_forget()
        self._btn_frame.pack_forget()
        self.geometry("520x400")
        self._log_box.pack(padx=12, pady=(0, 8), fill="both", expand=True)
        self._close_btn.configure(state="disabled")
        self._close_btn.pack(pady=(0, 12))
        threading.Thread(target=self._run_detection, daemon=True).start()

    def _run_detection(self) -> None:
        result = hardware.read_hat_eeprom_manual(log=self._log_to_box)
        if result.success:
            self._result = hardware._match_hat_from_strings(
                result.vendor, result.product, result.raw_output
            )
            self._log_to_box(f"\nDetected: {self._result.name}")
        else:
            self._result = None
            self._log_to_box(f"\nERROR: {result.error}")
        self.after(0, lambda: self._close_btn.configure(state="normal"))

    def _log_to_box(self, msg: str) -> None:
        def _append():
            self._log_box.configure(state="normal")
            self._log_box.insert("end", msg.rstrip() + "\n")
            self._log_box.see("end")
            self._log_box.configure(state="disabled")
        self.after(0, _append)

    def _on_close(self) -> None:
        self._callback(self._result)
        self.destroy()


class DownloadYamlDialog(ctk.CTkToplevel):
    """Ask which HAT YAML to download: Mini or Pro."""

    def __init__(self, parent, callback: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Download YAML")
        self.geometry("360x220")
        self._callback = callback
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(self, text="Select YAML to download:", font=ctk.CTkFont(size=13)).pack(
            padx=16, pady=(16, 8)
        )

        self._var = ctk.StringVar(value="mini")
        ctk.CTkRadioButton(
            self, text="MeshAdv Mini  (lora-MeshAdv-Mini-900M22S.yaml)",
            variable=self._var, value="mini",
        ).pack(anchor="w", padx=36, pady=4)
        ctk.CTkRadioButton(
            self, text="MeshAdv Pro   (lora-MeshAdv-Pro-915M30S.yaml)",
            variable=self._var, value="pro",
        ).pack(anchor="w", padx=36, pady=4)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=16, fill="x", padx=16)
        ctk.CTkButton(btn_frame, text="Download", command=self._confirm).pack(
            side="left", expand=True, padx=4
        )
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray40", command=self.destroy).pack(
            side="left", expand=True, padx=4
        )

    def _confirm(self) -> None:
        self._callback(self._var.get())
        self.destroy()


class RegionDialog(ctk.CTkToplevel):
    """Region picker."""

    def __init__(self, parent, callback: Callable[[str], None]) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Set Region")
        self.geometry("300x460")
        self._callback = callback
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(self, text="Select your region:", font=ctk.CTkFont(size=13)).pack(
            padx=16, pady=(12, 6)
        )

        self._var = ctk.StringVar(value="US")
        scroll = ctk.CTkScrollableFrame(self, height=340)
        scroll.pack(padx=12, pady=4, fill="both", expand=True)

        for region in REGIONS:
            ctk.CTkRadioButton(
                scroll, text=region, variable=self._var, value=region
            ).pack(anchor="w", padx=16, pady=3)
        _bind_scroll_to_frame(scroll)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=10, fill="x", padx=16)
        ctk.CTkButton(btn_frame, text="Set Region", command=self._confirm).pack(
            side="left", expand=True, padx=4
        )
        ctk.CTkButton(btn_frame, text="Cancel", fg_color="gray40", command=self.destroy).pack(
            side="left", expand=True, padx=4
        )

    def _confirm(self) -> None:
        self._callback(self._var.get())
        self.destroy()


class ServicesDialog(ctk.CTkToplevel):
    """Popup for all systemctl operations: enable on boot, start, stop, status."""

    def __init__(
        self,
        parent,
        log_callback: Callable[[str], None],
        refresh_callback: Callable,
    ) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Services — meshtasticd")
        self.geometry("400x340")
        self._log = log_callback
        self._refresh = refresh_callback
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(
            self,
            text="meshtasticd Service Control",
            font=ctk.CTkFont(size=14, weight="bold"),
        ).pack(padx=16, pady=(14, 10))

        # Status display
        self._status_lbl = ctk.CTkLabel(self, text="Checking...", text_color=COLOR_UNKNOWN)
        self._status_lbl.pack(pady=(0, 10))

        # Button grid
        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(padx=16, fill="x")
        btn_frame.grid_columnconfigure((0, 1), weight=1)

        ctk.CTkButton(btn_frame, text="Enable on Boot",  command=self._enable).grid(row=0, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Disable on Boot", fg_color="gray40", command=self._disable).grid(row=0, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Start Service",   command=self._start).grid(row=1, column=0, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="Stop Service",    fg_color="gray40", command=self._stop).grid(row=1, column=1, padx=4, pady=4, sticky="ew")
        ctk.CTkButton(btn_frame, text="View Status Output", width=200, command=self._status_output).grid(row=2, column=0, columnspan=2, padx=4, pady=(8, 4), sticky="ew")

        ctk.CTkButton(self, text="Close", fg_color="gray30", command=self.destroy).pack(pady=12)

        # Refresh status immediately
        self._poll_status()

    def _poll_status(self) -> None:
        threading.Thread(target=self._update_status_label, daemon=True).start()

    def _update_status_label(self) -> None:
        enabled = actions.service_is_enabled()
        active = actions.service_is_active()
        if active:
            text, color = "Running  |  Boot: " + ("Enabled" if enabled else "Disabled"), COLOR_OK
        else:
            text, color = "Stopped  |  Boot: " + ("Enabled" if enabled else "Disabled"), COLOR_WARN
        self.after(0, lambda: self._status_lbl.configure(text=text, text_color=color))

    def _run(self, func: Callable) -> None:
        def _worker():
            func()
            self._refresh()
            self._poll_status()
        threading.Thread(target=_worker, daemon=True).start()

    def _enable(self) -> None:
        self._log("Enabling meshtasticd on boot...")
        self._run(lambda: actions.service_enable())

    def _disable(self) -> None:
        self._log("Disabling meshtasticd on boot...")
        self._run(lambda: actions.service_disable())

    def _start(self) -> None:
        self._log("Starting meshtasticd...")
        def _do_start():
            ok, out = actions.service_start()
            if not ok:
                self._log("Start failed — running reset-failed and retrying...")
                actions.service_reset_failed()
                ok2, out2 = actions.service_start()
                if not ok2:
                    self._log("Retry also failed.")
        self._run(_do_start)

    def _stop(self) -> None:
        self._log("Stopping meshtasticd...")
        self._run(lambda: actions.service_stop())

    def _status_output(self) -> None:
        def _do():
            ok, output = actions.service_status()
            self.after(0, self._show_output, output)
        threading.Thread(target=_do, daemon=True).start()

    def _show_output(self, content: str) -> None:
        popup = ctk.CTkToplevel(self)
        popup.title("Service Status")
        popup.geometry("640x440")
        popup.transient(self)
        popup.after(50, lambda: _safe_grab(popup))
        tb = ctk.CTkTextbox(popup, wrap="word")
        tb.pack(fill="both", expand=True, padx=12, pady=12)
        tb.insert("end", content)
        tb.configure(state="disabled")
        ctk.CTkButton(popup, text="Close", command=popup.destroy).pack(pady=(0, 12))


class ConfirmDialog(ctk.CTkToplevel):
    def __init__(self, parent, message: str) -> None:
        super().__init__(parent)
        self.transient(parent)
        self.title("Confirm")
        self.geometry("380x200")
        self.result = False
        self.after(50, lambda: _safe_grab(self))

        ctk.CTkLabel(self, text=message, wraplength=340).pack(padx=16, pady=24, expand=True)

        btn_frame = ctk.CTkFrame(self, fg_color="transparent")
        btn_frame.pack(pady=(0, 16), fill="x", padx=16)
        ctk.CTkButton(btn_frame, text="Yes", command=self._yes).pack(
            side="left", expand=True, padx=4
        )
        ctk.CTkButton(btn_frame, text="No", fg_color="gray40", command=self.destroy).pack(
            side="left", expand=True, padx=4
        )

    def _yes(self) -> None:
        self.result = True
        self.destroy()
