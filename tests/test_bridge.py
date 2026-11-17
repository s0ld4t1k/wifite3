import io
import sys
import threading
from types import SimpleNamespace

import pytest

from wifite3.bridge import AttackRunner, LineBuffer, demo_targets, strip_ansi


def test_strip_ansi():
    assert strip_ansi("\x1b[31mred\x1b[0m") == "red"
    assert strip_ansi("plain") == "plain"
    assert strip_ansi("\x1b[2K\rline") == "\rline"


def test_line_buffer_flushes_and_handles_carriage_return():
    lines = []
    buffer = LineBuffer(lines.append)
    buffer.write("progress 1\r")
    buffer.write("progress 2\n")
    buffer.write("done")
    buffer.flush()
    assert lines == ["progress 2", "done"]


def test_line_buffer_take_pending_prompt():
    lines = []
    buffer = LineBuffer(lines.append)
    buffer.write("Continue attacking? [Y/n]: ")
    assert buffer.take_pending() == "Continue attacking? [Y/n]:"
    buffer.flush()
    assert lines == []


def test_line_buffer_truncates():
    lines = []
    buffer = LineBuffer(lines.append, max_line=10)
    buffer.write("x" * 50 + "\n")
    assert lines and len(lines[0]) <= 10


def test_output_tap_captures_engine_output_and_mutes_cursor_rewind(capsys):
    from wifite3.bridge import TAP, install_output_tap
    from wifite3.util.color import Color

    install_output_tap()
    lines = []
    tap = TAP.start(lines.append)
    try:
        Color.clear_line()
        Color.pl("{G}hello engine{W}")
        print("plain print")
    finally:
        TAP.stop()
        tap.flush()

    assert any("hello engine" in line for line in lines)
    assert any("plain print" in line for line in lines)
    assert capsys.readouterr().out == ""


def test_demo_targets_are_real_targets():
    targets = demo_targets()
    assert len(targets) >= 6
    assert all(target.bssid for target in targets)
    assert any(target.essid_known is False for target in targets)
    assert any(target.clients for target in targets)
    assert any(getattr(target, "wpa3_info", None) for target in targets)
    assert any(target.primary_encryption == "WEP" for target in targets)


def test_demo_target_bands():
    from wifite3.tui.widgets import band_label

    targets = demo_targets()
    bands = {band_label(target) for target in targets}
    assert "2.4" in bands
    assert "5" in bands


# --------------------------------------------------------------------------- #
# AttackRunner integration (engine mocked, no radio required)
# --------------------------------------------------------------------------- #


class _FakeSessionManager:
    def __init__(self, *args, **kwargs) -> None:
        self.saved = []

    def create_session(self, targets, config):
        return SimpleNamespace(session_id="session_test", attacked=0)

    def save_session(self, session) -> None:
        self.saved.append(session.session_id)


@pytest.fixture
def fake_engine(monkeypatch):
    """Replace the engine entry points used by AttackRunner.run()."""
    import wifite3.attack.all as all_mod
    import wifite3.bridge as bridge
    import wifite3.util.session as session_mod

    calls = {"ensure": None, "attack": None}
    monkeypatch.setattr(bridge, "ensure_engine", lambda options=None: calls.update(ensure=options))
    monkeypatch.setattr(session_mod, "SessionManager", _FakeSessionManager)

    def attack_multiple(targets, session=None, session_mgr=None):
        calls["attack"] = (list(targets), session, session_mgr)
        return len(targets)

    monkeypatch.setattr(all_mod.AttackAll, "attack_multiple", staticmethod(attack_multiple))
    return calls


def test_attack_runner_reports_success(fake_engine):
    targets = demo_targets()[:2]
    lines: list[str] = []
    results: list[tuple[bool, str]] = []
    runner = AttackRunner(targets, on_line=lines.append, on_finished=lambda ok, msg: results.append((ok, msg)))

    runner.run()

    assert runner.attacked == 2
    assert results == [(True, "Finished: 2 target(s) processed")]
    assert fake_engine["attack"][0] == targets
    assert any("Session session_test created" in line for line in lines)


def test_attack_runner_stopped_before_start(fake_engine):
    targets = demo_targets()[:1]
    results: list[tuple[bool, str]] = []
    stop = threading.Event()
    stop.set()
    runner = AttackRunner(
        targets,
        on_line=lambda line: None,
        on_finished=lambda ok, msg: results.append((ok, msg)),
        stop_event=stop,
    )

    runner.run()

    assert results == [(False, "Stopped by user")]
    assert fake_engine["attack"] is None


def test_attack_runner_reports_engine_error(fake_engine, monkeypatch):
    import wifite3.attack.all as all_mod

    def boom(*args, **kwargs):
        raise RuntimeError("radio on fire")

    monkeypatch.setattr(all_mod.AttackAll, "attack_multiple", staticmethod(boom))
    lines: list[str] = []
    results: list[tuple[bool, str]] = []
    runner = AttackRunner(
        demo_targets()[:1],
        on_line=lines.append,
        on_finished=lambda ok, msg: results.append((ok, msg)),
    )

    runner.run()

    assert runner.error == "radio on fire"
    assert results == [(False, "Attack error: radio on fire")]
    assert any("RuntimeError: radio on fire" in line for line in lines)


def test_attack_runner_stop_sets_event():
    runner = AttackRunner(demo_targets()[:1], on_line=lambda line: None, on_finished=lambda ok, msg: None)
    assert not runner.stop_event.is_set()
    runner.stop()
    assert runner.stop_event.is_set()
