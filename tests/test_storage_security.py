import os
import stat

from wifite3.model.result import CrackResult
from wifite3.util.logger import Logger
from wifite3.util.session import SessionManager, SessionState, TargetState
from wifite3.util.tui_logger import TUILogger


def _mode(path):
    return stat.S_IMODE(os.stat(path).st_mode)


def test_session_storage_permissions_and_round_trip(tmp_path):
    session_dir = tmp_path / "sessions"
    session_dir.mkdir(mode=0o777)
    os.chmod(session_dir, 0o777)
    manager = SessionManager(str(session_dir))

    assert _mode(session_dir) == 0o700

    session = SessionState(
        session_id="session_test",
        created_at=1.0,
        updated_at=1.0,
        config={"wordlist": "test.txt"},
        targets=[TargetState("00:11:22:33:44:55", "test", 1, "WPA2", -40, False)],
    )
    manager.save_session(session)
    session_file = session_dir / "session_test.json"

    assert _mode(session_file) == 0o600
    assert manager.load_session("session_test").config == session.config


def test_session_loader_rejects_group_or_world_accessible_file(tmp_path):
    manager = SessionManager(str(tmp_path / "sessions"))
    session = SessionState(
        "session_test",
        1.0,
        1.0,
        {},
        targets=[TargetState("00:11:22:33:44:55", "test", 1, "WPA2", -40, False)],
    )
    manager.save_session(session)
    session_file = tmp_path / "sessions" / "session_test.json"
    os.chmod(session_file, 0o640)

    try:
        manager.load_session("session_test")
    except PermissionError:
        pass
    else:
        raise AssertionError("world-readable session should not load")


def test_main_logger_restricts_existing_file(tmp_path):
    log_file = tmp_path / "wifite.log"
    log_file.write_text("old log\n")
    os.chmod(log_file, 0o644)

    Logger.initialize(log_file=str(log_file), verbose=3)
    Logger.debug("test", "safe message")

    assert _mode(log_file) == 0o600
    assert "safe message" in log_file.read_text()


def test_tui_logger_restricts_existing_file(tmp_path):
    log_file = tmp_path / "tui.log"
    log_file.write_text("old log\n")
    os.chmod(log_file, 0o644)

    TUILogger.initialize(enabled=True, log_file=str(log_file))
    TUILogger.info("safe message")

    assert _mode(log_file) == 0o600
    assert "safe message" in log_file.read_text()


def test_crack_result_is_atomically_saved_with_private_permissions(tmp_path, monkeypatch):
    class ExampleResult(CrackResult):
        essid = "test-network"
        bssid = "00:11:22:33:44:55"

        def to_dict(self):
            return {"type": "WPA", "date": self.date, "key": "sensitive-test-key"}

    output = tmp_path / "cracked.json"
    output.write_text("[]")
    os.chmod(output, 0o644)
    monkeypatch.setattr(CrackResult, "cracked_file", str(output))

    ExampleResult().save()

    assert _mode(output) == 0o600
    assert "sensitive-test-key" in output.read_text()
    assert not list(tmp_path.glob(".cracked_*.tmp"))


def test_crack_result_replaces_existing_sensitive_file(tmp_path, monkeypatch):
    class ExampleResult(CrackResult):
        essid = "test-network"
        bssid = "00:11:22:33:44:55"

        def to_dict(self):
            return {"type": "WPA", "date": self.date, "key": "new-key"}

    output = tmp_path / "cracked.json"
    output.write_text('[{"type":"WPA","date":0,"key":"old-key"}]')
    os.chmod(output, 0o644)
    monkeypatch.setattr(CrackResult, "cracked_file", str(output))

    ExampleResult().save()

    assert _mode(output) == 0o600
    assert "old-key" in output.read_text()
    assert "new-key" in output.read_text()
