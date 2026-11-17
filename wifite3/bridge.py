#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Glue between the vendored Wifite2 attack engine and the Textual TUI.

The engine is a console program at heart: it prints through ``Color`` and asks
questions through ``input()``.  Instead of rewriting ~50k lines of battle-tested
attack code, Wifite3 keeps the engine intact and redirects those two edges:

* ``Color.p/pl/pe`` and ``print()`` are routed into a line queue while an
  attack is running, so the TUI can display them in a log panel without
  corrupting the screen;
* ``input()`` is routed to a modal input box in the TUI.

Everything here is stdlib-only until an engine function is actually called.
"""

from __future__ import annotations

import builtins
import queue
import re
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime
from typing import Callable, Iterable

ANSI_RE = re.compile(r"\x1b\[[0-9;?]*[ -/]*[@-~]")
CONTROL_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


def strip_ansi(text: str) -> str:
    return ANSI_RE.sub("", text)


# --------------------------------------------------------------------------- #
# Output capture
# --------------------------------------------------------------------------- #


class LineBuffer:
    """Translate terminal-ish output into clean log lines."""

    def __init__(self, emit: Callable[[str], None], max_line: int = 800):
        self.emit = emit
        self.max_line = max_line
        self._current = ""
        self._lock = threading.Lock()

    def write(self, text: str) -> None:
        if not text:
            return
        text = strip_ansi(text).replace("\x00", "")
        with self._lock:
            text = text.replace("\r\n", "\n")
            # Carriage return means "redraw this line" in the engine. Keep the
            # newest segment; discard stale redraw noise.
            for chunk in re.split(r"(\r|\n)", text):
                if not chunk:
                    continue
                if chunk == "\r":
                    self._current = ""
                    continue
                if chunk == "\n":
                    line = self._current.rstrip()
                    self._current = ""
                    if line:
                        self.emit(line[: self.max_line])
                    continue
                if "\r" in chunk:
                    chunk = chunk.rsplit("\r", 1)[-1]
                self._current += chunk
                if len(self._current) > self.max_line:
                    self._current = self._current[-self.max_line :]

    def flush(self) -> None:
        with self._lock:
            line = self._current.rstrip()
            self._current = ""
        if line:
            self.emit(line[: self.max_line])

    def take_pending(self) -> str:
        """Take the unfinished line (usually an engine input prompt)."""
        with self._lock:
            line = self._current.strip()
            self._current = ""
        return line[: self.max_line]


class OutputTap:
    """Global capture sink used by the patched Color/print functions."""

    def __init__(self) -> None:
        self.sink: LineBuffer | None = None
        self._lock = threading.Lock()

    def start(self, emit: Callable[[str], None]) -> LineBuffer:
        buffer = LineBuffer(emit)
        with self._lock:
            self.sink = buffer
        return buffer

    def stop(self) -> None:
        with self._lock:
            buffer = self.sink
            self.sink = None
        if buffer:
            buffer.flush()

    def write(self, text: str) -> bool:
        with self._lock:
            buffer = self.sink
        if buffer is None:
            return False
        buffer.write(text)
        return True

    def active(self) -> bool:
        with self._lock:
            return self.sink is not None

    def take_pending(self) -> str:
        with self._lock:
            buffer = self.sink
        return buffer.take_pending() if buffer else ""


TAP = OutputTap()
_PATCHED = False


def install_output_tap() -> None:
    """Patch engine output once. Safe to call repeatedly."""
    global _PATCHED
    if _PATCHED:
        return
    _PATCHED = True

    from .util.color import Color

    original_p = Color.p
    original_pe = Color.pe
    original_clear_line = Color.clear_line

    def tapped_clear_line():
        # WEP uses a raw cursor rewind, which would scribble over Textual.
        if TAP.active():
            Color.last_sameline_length = 0
            return None
        return original_clear_line()

    def tapped_p(text):
        if TAP.write(Color.s(text)):
            return
        return original_p(text)

    def tapped_pe(text):
        if TAP.write(Color.s("%s\n" % text)):
            return
        return original_pe(text)

    Color.p = staticmethod(tapped_p)
    Color.pe = staticmethod(tapped_pe)
    Color.clear_line = staticmethod(tapped_clear_line)

    original_print = builtins.print

    def tapped_print(*args, **kwargs):
        if TAP.active() and not kwargs.get("file"):
            sep = kwargs.get("sep", " ")
            end = kwargs.get("end", "\n")
            text = sep.join(str(arg) for arg in args) + end
            if TAP.write(text):
                return
        return original_print(*args, **kwargs)

    builtins.print = tapped_print


# --------------------------------------------------------------------------- #
# Interactive input bridge
# --------------------------------------------------------------------------- #


class InputBridge:
    """Route engine ``input()`` calls to a UI callback running on the app thread."""

    def __init__(self) -> None:
        self.handler: Callable[[str], str] | None = None
        self._lock = threading.Lock()
        self._installed = False

    def install(self) -> None:
        if self._installed:
            return
        self._installed = True
        original = builtins.input

        def bridged(prompt=""):
            with self._lock:
                handler = self.handler
            if handler is None:
                return original(prompt)
            return handler(prompt)

        builtins.input = bridged

    def set_handler(self, handler: Callable[[str], str] | None) -> None:
        with self._lock:
            self.handler = handler


INPUT_BRIDGE = InputBridge()


# --------------------------------------------------------------------------- #
# Engine options / lifecycle
# --------------------------------------------------------------------------- #


@dataclass
class EngineOptions:
    interface: str = ""
    wordlist: str = ""
    bands: str = "2.4"  # 2.4 | 5 | all
    min_power: int = 0
    scan_time: int = 0
    pmkid: bool = True
    handshake: bool = True
    wps: bool = True
    wep: bool = True
    wpa3: bool = True
    skip_crack: bool = False
    kill_conflicts: bool = False
    verbose: int = 0
    target_timeout: int = 900
    pmkid_timeout: int = 300
    wpa_timeout: int = 300
    wps_only: bool = False
    pmkid_only: bool = False
    no_deauth: bool = False
    random_mac: bool = False


_ENGINE_READY = False


def ensure_engine(options: EngineOptions | None = None) -> None:
    """Initialise Configuration once and apply the TUI options."""
    global _ENGINE_READY
    from .config import Configuration

    if not _ENGINE_READY:
        Configuration.initialize(load_interface=False)
        _ENGINE_READY = True

    if options is None:
        return

    Configuration.interface = options.interface or Configuration.interface
    Configuration.verbose = options.verbose
    Configuration.min_power = options.min_power
    Configuration.scan_time = options.scan_time
    Configuration.target_timeout = options.target_timeout
    Configuration.pmkid_timeout = options.pmkid_timeout
    Configuration.wpa_attack_timeout = options.wpa_timeout
    Configuration.kill_conflicting_processes = options.kill_conflicts
    Configuration.random_mac = options.random_mac
    Configuration.no_deauth = options.no_deauth
    Configuration.skip_crack = options.skip_crack
    Configuration.wps_only = options.wps_only
    if options.pmkid_only:
        Configuration.use_pmkid_only = True
        Configuration.dont_use_pmkid = False
    elif options.pmkid and not options.handshake:
        Configuration.use_pmkid_only = True
        Configuration.dont_use_pmkid = False
    elif options.handshake and not options.pmkid:
        Configuration.use_pmkid_only = False
        Configuration.dont_use_pmkid = True
    elif options.pmkid and options.handshake:
        Configuration.use_pmkid_only = False
        Configuration.dont_use_pmkid = False
    else:
        Configuration.use_pmkid_only = False
        Configuration.dont_use_pmkid = True
    Configuration.use_pmkid = options.pmkid
    Configuration.no_wps = not options.wps

    if options.wordlist:
        Configuration.wordlist = options.wordlist
        Configuration.wordlists = [options.wordlist]

    # Bands.
    Configuration.all_bands = options.bands in {"all", "abg"}
    Configuration.two_ghz = options.bands in {"2.4", "bg"}
    Configuration.five_ghz = options.bands in {"5", "a"}
    if options.bands == "all":
        Configuration.all_bands = True


def enable_monitor(interface: str, emit: Callable[[str], None] | None = None) -> str:
    """Put *interface* into monitor mode and return the capture interface name."""
    ensure_engine()
    from .config import Configuration

    Configuration.interface = interface
    if emit:
        emit(f"Preparing monitor mode on {interface}…")
    Configuration.get_monitor_mode_interface()
    if emit:
        emit(f"Capture interface: {Configuration.interface}")
    return Configuration.interface


# --------------------------------------------------------------------------- #
# Scanning
# --------------------------------------------------------------------------- #


@dataclass
class ScanUpdate:
    targets: list
    decloaking: bool
    elapsed: float
    capture_interface: str = ""


class ScanRunner:
    """Runs airodump-ng in a worker thread and reports Target objects."""

    def __init__(
        self,
        interface: str,
        on_update: Callable[[ScanUpdate], None],
        on_log: Callable[[str], None],
        stop_event: threading.Event | None = None,
        scan_time: int = 0,
        options: EngineOptions | None = None,
    ) -> None:
        self.interface = interface
        self.on_update = on_update
        self.on_log = on_log
        self.stop_event = stop_event or threading.Event()
        self.scan_time = scan_time
        self.options = options
        self.capture_interface = ""
        self.error: str | None = None

    def stop(self) -> None:
        self.stop_event.set()

    def run(self) -> None:
        from .tools.airodump import Airodump

        started = time.time()
        try:
            ensure_engine(self.options)
            self.capture_interface = enable_monitor(self.interface, self.on_log)
            from .config import Configuration

            Configuration.interface = self.capture_interface

            with Airodump(output_file_prefix="wifite3_scan") as airodump:
                self.on_log(f"Scanning on {self.capture_interface} ({self._band_text()})")
                old_targets: list = []
                archives: dict = {}
                while not self.stop_event.is_set():
                    if airodump.pid.poll() is not None:
                        self.error = "airodump-ng exited unexpectedly (driver or permission problem)"
                        self.on_log(self.error)
                        break
                    try:
                        targets = airodump.get_targets(
                            old_targets=old_targets, target_archives=archives
                        )
                    except Exception as exc:  # keep scanning on a bad CSV row
                        self.on_log(f"Scan warning: {exc}")
                        targets = old_targets
                    old_targets = targets
                    elapsed = time.time() - started
                    self.on_update(
                        ScanUpdate(
                            targets=list(targets),
                            decloaking=bool(getattr(airodump, "decloaking", False)),
                            elapsed=elapsed,
                            capture_interface=self.capture_interface,
                        )
                    )
                    if self.scan_time and elapsed >= self.scan_time:
                        self.on_log("Scan timer finished")
                        break
                    self.stop_event.wait(0.75)
        except Exception as exc:
            self.error = str(exc)
            self.on_log(f"Scan failed: {exc}")
        finally:
            self.on_log("Scan stopped")

    def _band_text(self) -> str:
        from .config import Configuration

        if Configuration.all_bands:
            return "2.4 + 5 GHz"
        if Configuration.five_ghz:
            return "5 GHz"
        return "2.4 GHz"


# --------------------------------------------------------------------------- #
# Attack
# --------------------------------------------------------------------------- #


@dataclass
class AttackUpdate:
    line: str
    timestamp: datetime = field(default_factory=datetime.now)


class AttackRunner:
    """Runs AttackAll in a worker thread with output captured for the TUI."""

    def __init__(
        self,
        targets: list,
        on_line: Callable[[str], None],
        on_finished: Callable[[bool, str], None],
        stop_event: threading.Event | None = None,
        options: EngineOptions | None = None,
    ) -> None:
        self.targets = targets
        self.on_line = on_line
        self.on_finished = on_finished
        self.stop_event = stop_event or threading.Event()
        self.options = options
        self.error: str | None = None
        self.attacked = 0
        self._thread_ident: int | None = None

    def stop(self) -> None:
        self.stop_event.set()
        self._interrupt_thread()

    def _interrupt_thread(self) -> None:
        """Best-effort KeyboardInterrupt in the engine worker thread.

        The engine checks Ctrl+C at target/loop boundaries; injecting the
        exception makes the Stop button feel immediate instead of waiting for
        a multi-minute attack phase to finish. Child processes are killed too.
        """
        ident = self._thread_ident
        if ident and ident != threading.get_ident():
            try:
                import ctypes

                ctypes.pythonapi.PyThreadState_SetAsyncExc(
                    ctypes.c_ulong(ident), ctypes.py_object(KeyboardInterrupt)
                )
            except Exception:
                pass
        try:
            from .util.process import ProcessManager

            ProcessManager().cleanup_all()
        except Exception:
            pass

    def _emit(self, line: str) -> None:
        if line.strip():
            self.on_line(line)

    def run(self) -> None:
        from .attack.all import AttackAll
        from .config import Configuration
        from .util.session import SessionManager

        install_output_tap()
        self._thread_ident = threading.get_ident()
        tap = TAP.start(self._emit)
        session = None
        session_mgr = None
        try:
            ensure_engine(self.options)
            if self.stop_event.is_set():
                # Stop was pressed before this worker got scheduled.
                self.on_finished(False, "Stopped by user")
                return
            try:
                session_mgr = SessionManager()
                session = session_mgr.create_session(self.targets, Configuration)
                session_mgr.save_session(session)
                self._emit(f"Session {session.session_id} created")
            except Exception as exc:
                self._emit(f"Session persistence disabled: {exc}")
                session = None
                session_mgr = None

            self.attacked = AttackAll.attack_multiple(self.targets, session, session_mgr)
            if self.stop_event.is_set():
                self.on_finished(False, "Stopped by user")
            else:
                self.on_finished(True, f"Finished: {self.attacked} target(s) processed")
        except KeyboardInterrupt:
            self.on_finished(False, "Interrupted")
        except Exception as exc:
            self.error = str(exc)
            import traceback

            self._emit(traceback.format_exc())
            self.on_finished(False, f"Attack error: {exc}")
        finally:
            TAP.stop()
            tap.flush()


# --------------------------------------------------------------------------- #
# Demo data (works on macOS/dev machines without a radio)
# --------------------------------------------------------------------------- #


def demo_targets() -> list:
    """Build realistic Target objects for UI development and screenshots."""
    from .model.client import Client
    from .model.target import Target, WPSState

    samples = [
        ("C0:FF:EE:12:34:01", "Keenetic-4821", 6, "WPA2", "PSK", 78, 3, WPSState.LOCKED, 2412, False, "2.4"),
        ("C0:FF:EE:12:34:02", "TP-Link_9F2A", 1, "WPA2", "PSK", 66, 0, WPSState.UNLOCKED, 2412, False, "2.4"),
        ("C0:FF:EE:12:34:03", "MTS_Router_5G", 44, "WPA3", "SAE", 52, 1, WPSState.NONE, 5220, True, "5"),
        ("C0:FF:EE:12:34:04", "office-guest", 11, "WPA2", "PSK", 41, 5, WPSState.NONE, 2462, False, "2.4"),
        ("C0:FF:EE:12:34:05", "FreeWiFi", 3, "OWE", "OWE", 34, 2, WPSState.NONE, 2422, False, "2.4"),
        ("C0:FF:EE:12:34:06", "old-dlink", 9, "WEP", "", 28, 0, WPSState.NONE, 2452, False, "2.4"),
        ("C0:FF:EE:12:34:07", "", 149, "WPA2", "PSK", 22, 0, WPSState.NONE, 5745, False, "5"),
        ("C0:FF:EE:12:34:08", "Home_5G_EXT", 36, "WPA2/WPA3", "PSK SAE", 61, 2, WPSState.NONE, 5180, True, "5"),
    ]
    targets = []
    now = time.strftime("%Y-%m-%d %H:%M:%S")
    for idx, (bssid, essid, channel, enc, auth, power, clients, wps, freq, wpa3, band) in enumerate(samples):
        fields = [
            bssid,
            now,
            now,
            str(channel),
            "130",
            enc,
            "CCMP",
            auth,
            str(power - 100),
            "42",
            "0",
            "0.0.0.0",
            str(len(essid)),
            essid,
            "",
        ]
        target = Target(fields)
        target.frequency = freq
        target.wps = wps
        target.band_name = band
        target.max_power = max(power, 40)
        for client_idx in range(clients):
            client = Client(
                [
                    f"AA:BB:CC:{idx:02X}:{client_idx:02X}:FF",
                    now,
                    now,
                    "-55",
                    "12",
                    bssid,
                    essid or "(hidden)",
                ]
            )
            target.clients.append(client)
        if wpa3 and target.wpa3_info is None:
            class _WPA3:
                has_wpa3 = True
                is_transition = enc == "WPA2/WPA3"
                pmf_status = "required" if not is_transition else "optional"
                dragonblood_vulnerable = False

            target.wpa3_info = _WPA3()
        targets.append(target)
    return targets


# --------------------------------------------------------------------------- #
# Cleanup
# --------------------------------------------------------------------------- #


def graceful_cleanup(restore_interface: bool = True) -> None:
    """Kill child processes and restore managed interfaces (no sys.exit)."""
    try:
        from .util.process import ProcessManager

        ProcessManager().cleanup_all()
    except Exception:
        pass

    try:
        from .config import Configuration

        if Configuration.interface_manager is not None:
            Configuration.interface_manager.cleanup_all()
    except Exception:
        pass

    if not restore_interface:
        return

    try:
        from .config import Configuration
        from .tools.airmon import Airmon
        from .tools.iw import Iw

        if Configuration.interface and Airmon.base_interface and not Configuration.daemon:
            if Iw.is_monitor(Configuration.interface):
                Airmon.stop(Configuration.interface)
                Airmon.put_interface_up(Airmon.base_interface)
    except Exception:
        pass

    try:
        from .config import Configuration

        Configuration.delete_temp()
    except Exception:
        pass


def ensure_utf8_console() -> None:
    """Make sure captured engine output never trips over the terminal encoding."""
    import io
    import sys

    for stream_name in ("stdout", "stderr"):
        stream = getattr(sys, stream_name, None)
        if stream is None:
            continue
        encoding = getattr(stream, "encoding", "") or ""
        if encoding.lower() in {"utf-8", "utf8"}:
            continue
        try:
            buffer = getattr(stream, "buffer", None)
            if buffer is not None:
                setattr(sys, stream_name, io.TextIOWrapper(buffer, encoding="utf-8", errors="replace"))
        except Exception:
            pass
