import os
import sys

import pytest

from wifite3 import system


def test_distro_shape():
    distro = system.detect_distro()
    assert distro.id
    assert distro.family in {"fedora", "debian", "arch", "suse", "alpine", "unknown"}
    assert isinstance(distro.package_manager, (str, type(None)))


def test_install_command_known_families():
    for family, manager in (
        ("fedora", "dnf"),
        ("debian", "apt"),
        ("arch", "pacman"),
        ("suse", "zypper"),
        ("alpine", "apk"),
    ):
        command = system.install_command(family)
        assert command
        assert manager in command
        assert "aircrack-ng" in command


def test_install_command_unknown_is_empty():
    assert system.install_command("unknown") == []


def test_list_adapters_returns_list():
    assert isinstance(system.list_adapters(), list)


def test_environment_helpers():
    assert isinstance(system.is_linux(), bool)
    assert isinstance(system.is_root(), bool)
    assert isinstance(system.is_tty(), bool)
    assert system.command_exists("python3") in {True, False}


@pytest.mark.skipif(not sys.platform.startswith("linux"), reason="Linux only")
def test_interface_names_on_linux():
    names = system.interface_names()
    assert isinstance(names, list)
    for name in names:
        assert isinstance(name, str)
