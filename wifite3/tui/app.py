#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Wifite3 Textual application."""

from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from rich.text import Text
from textual import work
from textual.app import App, ComposeResult
from textual.containers import Horizontal, Vertical, VerticalScroll
from textual.widgets import (
    Button,
    Checkbox,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Select,
    Static,
)

from .. import system
from ..bridge import (
    INPUT_BRIDGE,
    TAP,
    EngineOptions,
    ScanRunner,
    ScanUpdate,
    demo_targets,
    ensure_engine,
    graceful_cleanup,
    install_output_tap,
)
from .screens import (
    AttackScreen,
    ConfirmScreen,
    DetailsScreen,
    DoctorScreen,
    HelpScreen,
    InputScreen,
)
from .widgets import (
    COLUMNS,
    add_target_row,
    power_dbm,
    short_time,
    sort_targets,
    target_details,
    vendor_for,
)


@dataclass
class InputRequest:
    prompt: str
    event: threading.Event = field(default_factory=threading.Event)
    value: str | None = None


class Wifite3App(App[None]):
    """Main TUI. Scan, select, attack without leaving the keyboard."""

    TITLE = "WIFITE3"
    SUB_TITLE = "wireless network auditor"
    CSS_PATH = "theme.tcss"

    BINDINGS = [
        ("s", "scan", "Scan / Stop"),
        ("space", "toggle_selection", "Select"),
        ("a", "select_all", "All"),
        ("n", "clear_selection", "None"),
        ("enter", "attack", "Attack"),
        ("f", "focus_filter", "Filter"),
        ("escape", "clear_filter", "Clear"),
        ("d", "details", "Details"),
        ("r", "refresh_interfaces", "Adapters"),
        ("question_mark", "help", "Help"),
        ("q", "quit", "Quit"),
    ]

    def __init__(
        self,
        demo: bool = False,
        interface: str = "",
        wordlist: str = "",
        options: EngineOptions | None = None,
    ) -> None:
        super().__init__()
        self.demo = demo
        self.initial_interface = interface
        self.initial_wordlist = wordlist
        self.options = options or EngineOptions()
        self.targets: dict[str, object] = {}
        self.selected: set[str] = set()
        self.visible_bssids: list[str] = []
        self.adapters: list[system.Adapter] = []
        self.scan_runner: ScanRunner | None = None
        self.scanning = False
        self.scan_started = 0.0
        self.scan_elapsed = 0.0
        self.capture_interface = ""
        self.filter_text = ""
        self.sort_column = "pwr"
        self.sort_reverse = True
        self.current_bssid: str | None = None
        self._pending_input: InputRequest | None = None
        self._pending_attack: list | None = None
        self._last_status = ""
        self._demo_index = 0
        self._demo_stop = threading.Event()

    # -- layout ----------------------------------------------------------- #

    def compose(self) -> ComposeResult:
        yield Header(show_clock=True)
        with Horizontal(id="body"):
            with Vertical(id="sidebar"):
                with VerticalScroll(id="sidebar-scroll"):
                    yield Static("◈  WIFITE3", id="logo")
                    yield Static("modern wireless auditor", id="tagline")

                    yield Static("ADAPTER", classes="section-title")
                    yield Select([], id="interface", prompt="detect…", allow_blank=True)
                    yield Static("searching for wireless interfaces…", id="adapter-info", classes="hint")
                    yield Button("Refresh adapters", id="refresh-ifaces", variant="default")

                    yield Static("SCAN", classes="section-title")
                    yield Label("Band", classes="field-label")
                    yield Select(
                        [
                            ("2.4 GHz", "2.4"),
                            ("5 GHz", "5"),
                            ("2.4 + 5 GHz", "all"),
                        ],
                        value="2.4",
                        id="band",
                        allow_blank=False,
                    )
                    yield Label("Duration", classes="field-label")
                    yield Select(
                        [
                            ("until stopped", "0"),
                            ("30 seconds", "30"),
                            ("60 seconds", "60"),
                            ("2 minutes", "120"),
                            ("5 minutes", "300"),
                        ],
                        value="0",
                        id="scan-time",
                        allow_blank=False,
                    )
                    yield Label("Minimum signal (0-99)", classes="field-label")
                    yield Input(value="0", id="min-power", type="integer", compact=True)

                    yield Static("ATTACKS", classes="section-title")
                    yield Checkbox("PMKID capture", value=True, id="opt-pmkid")
                    yield Checkbox("WPA handshake", value=True, id="opt-handshake")
                    yield Checkbox("WPS (Pixie / PIN)", value=True, id="opt-wps")
                    yield Checkbox("WEP", value=True, id="opt-wep")
                    yield Checkbox("WPA3 / SAE", value=True, id="opt-wpa3")
                    yield Checkbox("PMKID only", value=False, id="opt-pmkid-only")
                    yield Checkbox("No deauth", value=False, id="opt-no-deauth")
                    yield Checkbox("Random MAC", value=False, id="opt-random-mac")
                    yield Checkbox("Kill conflicting processes", value=False, id="opt-kill")

                    yield Static("WORDLIST", classes="section-title")
                    yield Input(
                        value=self.initial_wordlist,
                        placeholder="/path/to/wordlist.txt",
                        id="wordlist",
                    )
                    yield Static("", id="status", classes="status")

                with Vertical(id="sidebar-actions"):
                    yield Button("Start scan  [s]", variant="primary", id="scan")
                    yield Button("Stop scan", variant="warning", id="stop", disabled=True)
                    yield Button("Doctor", id="doctor")
                    yield Button("Help", id="help")

            with Vertical(id="main"):
                yield Static("", id="stats")
                with Horizontal(id="toolbar"):
                    yield Input(placeholder="filter: ssid / bssid / vendor", id="filter")
                    yield Button("Attack selected", variant="success", id="attack-top", disabled=True)
                yield DataTable(id="targets", zebra_stripes=True, cursor_type="row")
                with Vertical(id="detail-wrap"):
                    yield Static("Select a target to inspect it.", id="detail")
                yield Static("", id="activity")

        yield Footer()

    def on_mount(self) -> None:
        install_output_tap()
        INPUT_BRIDGE.install()
        INPUT_BRIDGE.set_handler(self.ask_engine_input)

        table = self.query_one("#targets", DataTable)
        for key, label, width in COLUMNS:
            table.add_column(label, key=key, width=width)
        table.focus()

        self._update_stats()
        if self.demo:
            self.query_one("#interface", Select).set_options([("demo0  simulated adapter", "demo0")])
            self.query_one("#interface", Select).value = "demo0"
            self.query_one("#adapter-info", Static).update(
                "[green]demo mode[/] · no radio is touched · synthetic targets"
            )
            self.query_one("#status", Static).update("demo mode ready")
            self.set_timer(0.4, self._start_demo_scan)
        else:
            self.refresh_interfaces()
            if not system.is_linux():
                self.notify(
                    "Wifite3 scans on Linux only. Explore the UI with `wifite3 --demo`.",
                    severity="warning",
                    timeout=8,
                )
            elif not system.is_root():
                self.notify(
                    "Monitor mode needs root. Start with: sudo wifite3",
                    severity="warning",
                    timeout=8,
                )
            self.refresh()
        self.set_interval(1.0, self._tick)

    def on_unmount(self) -> None:
        self._demo_stop.set()
        self._pending_attack = None
        if self.scan_runner:
            self.scan_runner.stop()
        # Release any engine thread blocked in ask_engine_input().
        pending = self._pending_input
        if pending is not None:
            pending.value = ""
            pending.event.set()
            self._pending_input = None
        INPUT_BRIDGE.set_handler(None)
        graceful_cleanup(restore_interface=not self.demo)

    def _post(self, callback, *args) -> None:
        """call_from_thread that is safe after the app has started exiting."""
        try:
            self.call_from_thread(callback, *args)
        except Exception:
            pass

    # -- engine -> TUI input bridge --------------------------------------- #

    def ask_engine_input(self, prompt: str) -> str:
        """Called from an engine worker thread; blocks that thread only."""
        # Most engine prompts are printed via Color.p() and then input() is
        # called without arguments. Use that unfinished line as the question.
        prompt = (prompt or "").strip() or TAP.take_pending()
        request = InputRequest(prompt=prompt or "The engine needs input to continue.")
        self._pending_input = request
        try:
            self.call_from_thread(self._show_input, request)
        except Exception:
            # App is shutting down; do not leave the engine thread blocked.
            self._pending_input = None
            return ""
        if not request.event.wait(timeout=600):
            return ""
        return request.value or ""

    def _show_input(self, request: InputRequest) -> None:
        def complete(value: str | None) -> None:
            request.value = value
            request.event.set()
            self._pending_input = None

        self.push_screen(InputScreen(request.prompt), callback=complete)

    # -- adapters --------------------------------------------------------- #

    @work(thread=True, exclusive=True, group="interfaces")
    def refresh_interfaces(self) -> None:
        adapters = system.list_adapters()
        self._post(self._apply_adapters, adapters)

    def _apply_adapters(self, adapters: list[system.Adapter]) -> None:
        self.adapters = adapters
        select = self.query_one("#interface", Select)
        current = select.value if select.value != Select.NULL else None
        if adapters:
            options = [(adapter.label, adapter.name) for adapter in adapters]
            select.set_options(options)
            names = [adapter.name for adapter in adapters]
            chosen = self.initial_interface if self.initial_interface in names else None
            if chosen:
                select.value = chosen
            elif current in names:
                select.value = current
            else:
                # Prefer a monitor-capable radio, then the strongest name.
                monitor = [a for a in adapters if a.supports_monitor]
                select.value = (monitor or adapters)[0].name
            self._update_adapter_info()
        else:
            select.set_options([("no wireless adapter", Select.BLANK)])
            select.value = Select.BLANK
            info = "[yellow]no wireless adapter found[/]\n"
            if system.is_linux():
                info += "[dim]check `ip link`, `rfkill list`, driver/firmware[/dim]"
            else:
                info += "[dim]Linux is required for scanning; use --demo here[/dim]"
            self.query_one("#adapter-info", Static).update(info)
        self._update_attack_button()

    def _adapter(self) -> system.Adapter | None:
        if self.demo:
            return None
        select = self.query_one("#interface", Select)
        if select.value in (Select.NULL, Select.BLANK, None):
            return None
        for adapter in self.adapters:
            if adapter.name == select.value:
                return adapter
        return None

    def _update_adapter_info(self) -> None:
        adapter = self._adapter()
        if adapter is None:
            return
        lines = [
            f"[bold]{adapter.name}[/]  [dim]{adapter.driver or 'driver?'}[/]",
            f"[dim]mode[/] {adapter.mode}   [dim]phy[/] {adapter.phy or '?'}   "
            f"[dim]state[/] {adapter.state}",
            f"[dim]caps[/] {adapter.capability_text}",
        ]
        if adapter.connected_ssid:
            lines.append(f"[dim]linked to[/] {adapter.connected_ssid}")
        if adapter.supports_monitor is False:
            lines.append("[yellow]⚠ monitor mode not advertised by this phy[/]")
        self.query_one("#adapter-info", Static).update("\n".join(lines))

    # -- widget events ---------------------------------------------------- #

    def on_select_changed(self, event: Select.Changed) -> None:
        if event.select.id == "interface":
            self._update_adapter_info()
            self._update_attack_button()

    def on_input_changed(self, event: Input.Changed) -> None:
        if event.input.id == "filter":
            self.filter_text = event.value
            self._rebuild_table()

    def on_checkbox_changed(self, event: Checkbox.Changed) -> None:
        # Keep the PMKID-only switch coherent with the PMKID checkbox.
        if event.checkbox.id == "opt-pmkid-only" and event.value:
            self.query_one("#opt-pmkid", Checkbox).value = True

    def on_button_pressed(self, event: Button.Pressed) -> None:
        button_id = event.button.id
        if button_id == "scan":
            self.action_scan()
        elif button_id == "stop":
            self._stop_scan()
        elif button_id == "attack-top":
            self.action_attack()
        elif button_id == "refresh-ifaces":
            self.refresh_interfaces()
        elif button_id == "doctor":
            self.push_screen(DoctorScreen())
        elif button_id == "help":
            self.push_screen(HelpScreen())

    def on_data_table_row_highlighted(self, event: DataTable.RowHighlighted) -> None:
        if event.data_table.id == "targets":
            self.current_bssid = str(event.row_key.value)
            self._update_detail()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        if event.data_table.id == "targets":
            self.current_bssid = str(event.row_key.value)
            self.action_attack()

    def on_data_table_header_selected(self, event: DataTable.HeaderSelected) -> None:
        if event.data_table.id != "targets":
            return
        key = str(event.column_key.value or "")
        if key in {"sel"}:
            return
        if self.sort_column == key:
            self.sort_reverse = not self.sort_reverse
        else:
            self.sort_column = key
            self.sort_reverse = key in {"pwr", "cli", "ch"}
        self._rebuild_table()

    # -- actions ---------------------------------------------------------- #

    def action_scan(self) -> None:
        if self.scanning:
            self._stop_scan()
            return
        if self.demo:
            self._start_demo_scan()
            return
        if not system.is_linux():
            self.notify("Scanning requires Linux. Use --demo to explore.", severity="error")
            return
        if not system.is_root():
            self.notify("Root is required for monitor mode: sudo wifite3", severity="error", timeout=6)
            return
        adapter = self._adapter()
        if adapter is None:
            self.notify("No wireless adapter selected.", severity="error")
            return
        if adapter.supports_monitor is False:
            self.notify(
                f"{adapter.name}: monitor mode not advertised. Try another adapter.",
                severity="warning",
                timeout=8,
            )

        # A previous scan may already have put the radio into monitor mode and
        # renamed it (wlan0 -> wlan0mon). Reuse that interface instead of
        # trying to start monitor mode on the now-missing managed name.
        interface = self.capture_interface or adapter.name
        options = self._engine_options(interface)
        self.options = options
        runner = ScanRunner(
            interface=interface,
            on_update=lambda update: self._post(self._apply_scan_update, update),
            on_log=lambda line: self._post(self._set_status, line),
            scan_time=int(self.query_one("#scan-time", Select).value),
            options=options,
        )
        self.scan_runner = runner
        self.scanning = True
        self.scan_started = time.time()
        self.scan_elapsed = 0.0
        self._set_scan_ui(True)
        self._set_status(f"starting scan on {interface}…")
        self.run_scan(runner)

    @work(thread=True, exclusive=True, group="scan")
    def run_scan(self, runner: ScanRunner) -> None:
        install_output_tap()
        tap = TAP.start(lambda line: self._post(self._set_status, line))
        try:
            runner.run()
        finally:
            TAP.stop()
            tap.flush()
            self._post(self._scan_finished, runner.error)

    def _apply_scan_update(self, update: ScanUpdate) -> None:
        self.scan_elapsed = update.elapsed
        if update.capture_interface:
            self.capture_interface = update.capture_interface
        new_targets: dict[str, object] = {target.bssid: target for target in update.targets}
        added = len(new_targets) - len(self.targets)
        self.targets = new_targets
        self._update_stats()
        self._rebuild_table()
        self._update_attack_button()
        if update.decloaking:
            self._set_status("scanning + decloaking hidden SSIDs…")
        elif added > 0:
            self._set_status(f"+{added} new target(s) · {len(self.targets)} total")

    def _scan_finished(self, error: str | None) -> None:
        self.scanning = False
        self.scan_runner = None
        self._set_scan_ui(False)
        if error:
            self.notify(f"Scan error: {error}", severity="error", timeout=10)
            self._set_status(f"scan failed: {error}")
        else:
            self._set_status(f"scan stopped · {len(self.targets)} target(s)")
        self._update_stats()

        pending, self._pending_attack = self._pending_attack, None
        if pending:
            if error:
                self.notify("Attack cancelled: the scan failed.", severity="error")
            else:
                # airodump has released the interface by now.
                self._launch_attack(pending)

    def _stop_scan(self) -> None:
        if self.scan_runner:
            self.scan_runner.stop()
            self._set_status("stopping scan…")
        self._demo_stop.set()

    def _set_scan_ui(self, scanning: bool) -> None:
        self.query_one("#scan", Button).disabled = scanning
        self.query_one("#stop", Button).disabled = not scanning
        self.query_one("#scan", Button).label = "Scanning…" if scanning else "Start scan  [s]"
        for widget_id in ("#interface", "#band", "#scan-time", "#min-power", "#wordlist", "#refresh-ifaces"):
            self.query_one(widget_id).disabled = scanning

    def action_toggle_selection(self) -> None:
        if not self.current_bssid or self.current_bssid not in self.targets:
            return
        row = self._cursor_row()
        if self.current_bssid in self.selected:
            self.selected.discard(self.current_bssid)
        else:
            self.selected.add(self.current_bssid)
        self._rebuild_table()
        if row is not None:
            self._restore_cursor(row)
        self._update_detail()
        self._update_attack_button()

    def action_select_all(self) -> None:
        self.selected.update(self.visible_bssids)
        self._rebuild_table()
        self._update_detail()
        self._update_attack_button()

    def action_clear_selection(self) -> None:
        self.selected.clear()
        self._rebuild_table()
        self._update_detail()
        self._update_attack_button()

    def action_focus_filter(self) -> None:
        self.query_one("#filter", Input).focus()

    def action_clear_filter(self) -> None:
        field = self.query_one("#filter", Input)
        if field.value:
            field.value = ""
            self.filter_text = ""
            self._rebuild_table()

    def action_details(self) -> None:
        target = self._current_target()
        if target is None:
            return
        self.push_screen(DetailsScreen(target, selected=target.bssid in self.selected))

    def action_help(self) -> None:
        self.push_screen(HelpScreen())

    def action_refresh_interfaces(self) -> None:
        if not self.demo:
            self.refresh_interfaces()

    def action_quit(self) -> None:
        if self.scanning:
            self.push_screen(
                ConfirmScreen("A scan is running. Stop it and quit?", yes="Stop & quit"),
                callback=lambda confirmed: self.exit() if confirmed else None,
            )
        else:
            self.exit()

    def action_attack(self) -> None:
        if not self.targets:
            self.notify("No targets yet — run a scan first.", severity="warning")
            return

        targets = [self.targets[bssid] for bssid in self.selected if bssid in self.targets]
        if not targets:
            visible = [self.targets[bssid] for bssid in self.visible_bssids if bssid in self.targets]
            if not visible:
                self.notify("Nothing visible to attack (check the filter).", severity="warning")
                return
            self.push_screen(
                ConfirmScreen(
                    f"No target selected. Attack all {len(visible)} visible target(s)?",
                    yes=f"Attack {len(visible)}",
                ),
                callback=lambda confirmed: self._request_attack(visible) if confirmed else None,
            )
            return
        self._request_attack(targets)

    def _request_attack(self, targets: list) -> None:
        """Start now, or after a running scan releases the interface."""
        if self.scanning:
            self._pending_attack = targets
            self._stop_scan()
            self.notify("Scan stopped. Attack starts as soon as airodump exits.", timeout=5)
            return
        self._launch_attack(targets)

    def _launch_attack(self, targets: list) -> None:
        # Respect the attack toggles even if the engine would handle more.
        wanted: list = []
        for target in targets:
            enc = getattr(target, "primary_encryption", getattr(target, "encryption", ""))
            wpa3 = getattr(target, "wpa3_info", None) is not None or enc == "WPA3"
            wps_available = self.options.wps and getattr(target, "wps", 0) in (1, 2)
            if enc == "WEP":
                if self.options.wep:
                    wanted.append(target)
                continue
            if enc == "OWE":
                wanted.append(target)
                continue
            if wpa3 and not self.options.wpa3:
                continue
            if not (self.options.pmkid or self.options.handshake or wps_available):
                continue
            wanted.append(target)
        if not wanted:
            self.notify("Selected targets are excluded by the attack toggles.", severity="warning")
            return
        targets = wanted

        if not self.demo:
            if not system.is_linux() or not system.is_root():
                self.notify("Attacks require Linux + root. Use --demo to preview.", severity="error")
                return
            adapter = self._adapter()
            interface = self.capture_interface or (adapter.name if adapter else "")
            self.options = self._engine_options(interface)
        self.push_screen(AttackScreen(targets, demo=self.demo, options=self.options))

    # -- details / table -------------------------------------------------- #

    def _cursor_row(self) -> int | None:
        try:
            table = self.query_one("#targets", DataTable)
            return table.cursor_row
        except Exception:
            return None

    def _restore_cursor(self, row: int) -> None:
        try:
            table = self.query_one("#targets", DataTable)
            if table.row_count:
                table.move_cursor(row=min(row, table.row_count - 1))
        except Exception:
            pass

    def _current_target(self):
        if self.current_bssid:
            return self.targets.get(self.current_bssid)
        return None

    def _rebuild_table(self) -> None:
        table = self.query_one("#targets", DataTable)
        table.clear(columns=False)
        visible = sort_targets(
            list(self.targets.values()),
            column=self.sort_column,
            reverse=self.sort_reverse,
            query=self.filter_text,
        )
        self.visible_bssids = [target.bssid for target in visible]
        for target in visible:
            add_target_row(table, target, target.bssid in self.selected)
        if table.row_count:
            if self.current_bssid in self.visible_bssids:
                row = self.visible_bssids.index(self.current_bssid)
            else:
                row = 0
                self.current_bssid = self.visible_bssids[0]
            table.move_cursor(row=row)
        else:
            self.current_bssid = None
        self._update_detail()
        self._update_attack_button()

    def _update_detail(self, expanded: bool = False) -> None:
        target = self._current_target()
        detail = self.query_one("#detail", Static)
        if target is None:
            detail.update("Select a target to inspect it.")
            return
        detail.update(target_details(target, target.bssid in self.selected))

    def _update_stats(self) -> None:
        targets = list(self.targets.values())
        clients = sum(len(getattr(target, "clients", []) or []) for target in targets)
        wps = sum(
            1
            for target in targets
            if getattr(target, "wps", 0) in (1, 2)
        )
        wpa3 = sum(1 for target in targets if getattr(target, "wpa3_info", None) is not None)
        elapsed = self.scan_elapsed if not self.scanning else time.time() - self.scan_started
        scan_state = "[bold green]scanning[/]" if self.scanning else "[dim]idle[/]"
        self.query_one("#stats", Static).update(
            f"  {scan_state}   [dim]│[/]   "
            f"[bold]{len(targets)}[/] targets   "
            f"[bold]{clients}[/] clients   "
            f"[bold]{wps}[/] WPS   "
            f"[bold]{wpa3}[/] WPA3   "
            f"[dim]│[/]   [cyan]{short_time(elapsed)}[/]   "
            f"[dim]│[/]   sort: {self.sort_column} {'↓' if self.sort_reverse else '↑'}"
        )

    def _update_attack_button(self) -> None:
        count = len(self.selected)
        button = self.query_one("#attack-top", Button)
        button.disabled = not self.targets
        button.label = f"Attack selected ({count})" if count else "Attack all visible"

    def _set_status(self, message: str) -> None:
        message = message.strip()
        if not message or message == self._last_status:
            return
        self._last_status = message
        try:
            self.query_one("#status", Static).update(Text(message[-160:], style="dim"))
            self.query_one("#activity", Static).update(Text(message[-200:], style="dim"))
        except Exception:
            pass

    def _tick(self) -> None:
        if self.scanning:
            self._update_stats()
        self._update_detail()

    # -- demo ------------------------------------------------------------- #

    def _start_demo_scan(self) -> None:
        if not self.demo:
            return
        if self.scanning:
            self._stop_scan()
            return
        self._demo_stop.clear()
        self.targets = {}
        self.selected.clear()
        self._demo_index = 0
        self.scanning = True
        self.scan_started = time.time()
        self.scan_elapsed = 0.0
        self._set_scan_ui(True)
        self._set_status("demo scan started…")
        self._demo_worker()

    @work(thread=True, exclusive=True, group="demo-scan")
    def _demo_worker(self) -> None:
        samples = demo_targets()
        for index, target in enumerate(samples, start=1):
            if self._demo_stop.is_set():
                break
            self._post(self._demo_add, target, index)
            if self._demo_stop.wait(0.45):
                break
        self._post(self._demo_finished)

    def _demo_add(self, target, index: int) -> None:
        self.targets[target.bssid] = target
        self._update_stats()
        self._rebuild_table()
        self._set_status(f"demo scan: found {target.essid or target.bssid} · {len(self.targets)} targets")

    def _demo_finished(self) -> None:
        if not self.scanning:
            return
        self.scanning = False
        self.scan_elapsed = max(1.0, time.time() - self.scan_started)
        self._set_scan_ui(False)
        self._update_stats()
        self._set_status(f"demo scan complete · {len(self.targets)} targets")
        self._update_attack_button()

        pending, self._pending_attack = self._pending_attack, None
        if pending:
            self._launch_attack(pending)

    def _engine_options(self, interface: str) -> EngineOptions:
        band = str(self.query_one("#band", Select).value or "2.4")
        scan_time = int(self.query_one("#scan-time", Select).value or 0)
        try:
            min_power = int(self.query_one("#min-power", Input).value or 0)
        except ValueError:
            min_power = 0
        return EngineOptions(
            interface=interface,
            wordlist=self.query_one("#wordlist", Input).value.strip(),
            bands=band,
            scan_time=scan_time,
            min_power=min_power,
            pmkid=self.query_one("#opt-pmkid", Checkbox).value,
            handshake=self.query_one("#opt-handshake", Checkbox).value,
            wps=self.query_one("#opt-wps", Checkbox).value,
            wep=self.query_one("#opt-wep", Checkbox).value,
            wpa3=self.query_one("#opt-wpa3", Checkbox).value,
            pmkid_only=self.query_one("#opt-pmkid-only", Checkbox).value,
            no_deauth=self.query_one("#opt-no-deauth", Checkbox).value,
            random_mac=self.query_one("#opt-random-mac", Checkbox).value,
            kill_conflicts=self.query_one("#opt-kill", Checkbox).value,
            verbose=self.options.verbose,
        )
