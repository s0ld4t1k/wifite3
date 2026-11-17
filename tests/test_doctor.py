from pathlib import Path

from wifite3.doctor import collect_report
from wifite3.util.paths import data_dir, find_data_file, wordlist_paths


def test_bundled_data_exists():
    assert (data_dir() / "ieee-oui.txt").is_file()
    assert (data_dir() / "wordlists" / "wordlist-probable.txt").is_file()
    assert find_data_file("ieee-oui.txt") is not None


def test_wordlists_found():
    lists = wordlist_paths()
    assert lists
    assert all(path.suffix == ".txt" for path in lists)


def test_doctor_report_structure():
    report = collect_report()
    assert report.checks
    assert isinstance(report.adapters, list)
    assert report.distro.id
    statuses = {check.status for check in report.checks}
    assert statuses <= {"ok", "warn", "fail", "info"}
    assert any(check.title == "Linux host" for check in report.checks)


def test_doctor_ready_property():
    report = collect_report()
    assert report.ready == (len(report.failures) == 0)
