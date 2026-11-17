import os
import subprocess
import sys

from wifite3 import cli


def run_cli(*args):
    env = dict(os.environ)
    env["PYTHONPATH"] = os.getcwd()
    return subprocess.run(
        [sys.executable, "-m", "wifite3", *args],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        env=env,
        timeout=60,
    )


def test_version():
    result = run_cli("--version")
    assert result.returncode == 0
    assert "wifite3 0.1.0" in result.stdout


def test_help_mentions_tui_and_classic():
    result = run_cli("--help")
    assert result.returncode == 0
    assert "--classic" in result.stdout
    assert "--demo" in result.stdout
    assert "--doctor" in result.stdout
    assert "TUI KEYS" in result.stdout


def test_demo_without_tty_fails_fast():
    result = run_cli("--demo")
    assert result.returncode == 2
    assert "interactive terminal" in result.stderr


def test_take_value_forms():
    argv = ["--interface", "wlan0", "-w", "/tmp/list.txt"]
    assert cli._take_value(argv, "-i", "--interface") == "wlan0"
    assert cli._take_value(argv, "-w", "--wordlist") == "/tmp/list.txt"
    assert argv == []


def test_take_value_equals():
    argv = ["--interface=wlp2s0", "--verbose"]
    assert cli._take_value(argv, "-i", "--interface") == "wlp2s0"
    assert argv == ["--verbose"]


def test_take_flag_removes_all():
    argv = ["--demo", "-v", "--demo"]
    assert cli._take_flag(argv, "--demo") is True
    assert argv == ["-v"]
