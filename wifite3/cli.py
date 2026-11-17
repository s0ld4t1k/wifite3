#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Command line entry point.

Design rule: ``wifite3`` with no arguments opens the new TUI.  Every original
Wifite2 flag keeps working, and ``--classic`` gives the exact old console flow
for scripts.  TUI-only switches are stripped before the engine's argparse sees
them.
"""

from __future__ import annotations

import os
import sys

VERSION = "0.1.0"
BANNER = r"""
  ██╗    ██╗██╗███████╗██╗████████╗███████╗██████╗
  ██║    ██║██║██╔════╝██║╚══██╔══╝██╔════╝╚════██╗
  ██║ █╗ ██║██║█████╗  ██║   ██║   █████╗    █████╔╝
  ██║███╗██║██║██╔══╝  ██║   ██║   ██╔══╝   ██╔═══╝
  ╚███╔███╔╝██║██║     ██║   ██║   ███████╗███████╗
   ╚══╝╚══╝ ╚═╝╚═╝     ╚═╝   ╚═╝   ╚══════╝╚══════╝
"""

HELP = f"""{BANNER}
  Wifite3 {VERSION} — modern TUI wireless auditor for Linux
  full Wifite2 attack engine underneath

USAGE
  sudo wifite3                     open the TUI (recommended)
  sudo wifite3 --interface wlan0   preselect an adapter
  sudo wifite3 --classic [flags]   classic Wifite2 console mode
  wifite3 --doctor                 check host, drivers and tools (Linux-only readiness)
  wifite3 --demo                   explore the TUI without a radio
  wifite3 --classic --help         every engine flag (full Wifite2 docs)

TUI KEYS
  s        scan / stop          space    select target
  a / n    select all / none    enter    attack
  f        filter               d        details
  r        refresh adapters     ?        help
  q        quit

TUI FLAGS
  -i, --interface IFACE        preselect a wireless adapter
  -w, --wordlist FILE          default wordlist
  -v / -vv / -vvv              verbose engine output in the live log

CLASSIC MODE FLAGS (→ --classic --help for the full list)
  --kill                       kill interfering processes
  -ab / --allbands             scan 2.4 + 5 GHz
  -2 / --2ghz / -5 / --5ghz    select a single band
  --pmkid / --no-pmkid         toggle PMKID
  --wps-only / --no-wps        WPS behaviour
  --wpa3 / --wpa3-only         WPA3/SAE behaviour
  --skip-crack                 capture only, crack later
  --update-db                  refresh the OUI vendor database

LEGAL
  Use Wifite3 only on networks you own or have explicit written permission to
  test. Unauthorised interception is illegal in most countries.
"""


def _take_flag(argv: list[str], *names: str) -> bool:
    found = False
    for name in names:
        while name in argv:
            argv.remove(name)
            found = True
    return found


def _take_value(argv: list[str], *names: str) -> str:
    value = ""
    for index, token in enumerate(list(argv)):
        for name in names:
            if token == name:
                if index + 1 < len(argv):
                    value = argv[index + 1]
                    del argv[index : index + 2]
                else:
                    argv.pop(index)
                return value or _take_value(argv, *names)
            if token.startswith(name + "="):
                value = token.split("=", 1)[1]
                del argv[index]
                return value
    return value


def _classic(argv: list[str]) -> int:
    argv = [arg for arg in argv if arg not in {"--classic", "--no-tui", "--demo", "--deep"}]
    sys.argv = [sys.argv[0]] + argv
    from .wifite import main as engine_main

    engine_main()
    return 0


def _print_help() -> None:
    print(HELP)


def main() -> int:
    argv = sys.argv[1:]
    want_classic = any(arg in {"--classic", "--no-tui"} for arg in argv)
    want_tui = any(arg in {"--tui"} for arg in argv)
    want_demo = any(arg in {"--demo"} for arg in argv)
    want_doctor = any(arg in {"--doctor", "--syscheck"} for arg in argv)
    deep = any(arg in {"--deep"} for arg in argv)
    want_help = any(arg in {"--help", "-h"} for arg in argv)
    want_version = any(arg in {"--version", "-V"} for arg in argv)

    if want_classic:
        return _classic(argv)

    # Help/version are handled before importing the engine so they also work
    # on machines where the attack toolchain is not installed yet.
    if want_version and not want_doctor:
        print(f"wifite3 {VERSION}  (engine: Wifite2, GPL-2.0)")
        return 0
    if want_help and not want_doctor:
        _print_help()
        return 0

    # Strip TUI-only switches from the args the engine will parse.
    clean = [arg for arg in argv if arg not in {"--tui", "--demo", "--doctor", "--deep"}]
    interface = _take_value(clean, "-i", "--interface")
    wordlist = _take_value(clean, "-w", "--wordlist")
    verbose = sum(1 for arg in clean if arg in {"-v", "--verbose"} or arg in {"-vv", "-vvv"})
    sys.argv = [sys.argv[0]] + clean

    if want_doctor:
        from .doctor import main as doctor_main

        return doctor_main(deep=deep)

    if not sys.stdin.isatty() or not sys.stdout.isatty():
        if want_demo:
            print(
                "[!] --demo needs an interactive terminal (stdin and stdout must be a TTY).\n"
                "    For screenshots/CI use Textual's run_test(), or allocate a PTY.",
                file=sys.stderr,
            )
            return 2
        print(
            "[!] No interactive terminal: falling back to classic mode.\n"
            "    Use `wifite3 --classic` explicitly in scripts.",
            file=sys.stderr,
        )
        return _classic(argv)

    try:
        from .tui.app import Wifite3App
    except ImportError as exc:
        print(
            f"[!] The Textual TUI is not installed ({exc}).\n"
            "    Install dependencies: python3 -m pip install 'textual>=0.80'\n"
            "    Or use classic mode: wifite3 --classic",
            file=sys.stderr,
        )
        return 1

    os.environ.setdefault("TEXTUAL_ANIMATIONS", "none")
    from .bridge import EngineOptions

    app = Wifite3App(
        demo=want_demo,
        interface=interface,
        wordlist=wordlist,
        options=EngineOptions(interface=interface, wordlist=wordlist, verbose=verbose),
    )
    app.run()
    return 0


def classic_main() -> int:
    """Console-script shim used by the ``wifite3-classic`` entry point."""
    return _classic(["--classic"] + sys.argv[1:])


if __name__ == "__main__":
    raise SystemExit(main())
