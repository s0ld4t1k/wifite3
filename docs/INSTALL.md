# Установка Wifite3

## TL;DR

```bash
git clone https://github.com/s0ld4t1k/wifite3.git wifite3
cd wifite3
chmod +x install.sh
./install.sh
sudo wifite3
```

`install.sh`:

1. проверяет Linux и Python;
2. определяет дистрибутив (`dnf`, `apt`, `pacman`, `zypper`, `apk`);
3. ставит обязательные и опциональные пакеты;
4. устанавливает Python-часть в изолированное окружение `/opt/wifite3/venv`;
5. создаёт ссылку `/usr/local/bin/wifite3`, доступную из `sudo` с типичным
   `secure_path`;
6. запускает `wifite3 --doctor`.

Установка в `/opt` выполняется даже при запуске скрипта обычным пользователем:
это защищает от выполнения root-кодом пользовательского pipx-окружения.
Если что-то пошло не так, установщик сообщит, какие пакеты поставить вручную.

## Fedora

Для полной установки зависимостей используйте `./install.sh`. Если ставите
вручную, сначала установите системные инструменты:

```bash
sudo dnf install -y aircrack-ng iw iproute wireless-regdb usbutils pciutils \
  rfkill wpa_supplicant
sudo dnf install -y hashcat hcxdumptool hcxtools wireshark-cli macchanger \
  hostapd dnsmasq john cowpatty || true
```

`reaver` и `bully` (WPS) могут быть недоступны в официальных репозиториях —
включите [RPM Fusion](https://rpmfusion.org/) или соберите из исходников.
Без них работают WPA/PMKID/WPA3/WEP.

Python-часть устанавливайте так:

```bash
./install.sh --no-deps
sudo wifite3 --doctor
```

> Не используйте `sudo pip install .` на Fedora 38+. Системный Python
> помечен как externally managed (PEP 668). Установщик создаёт изолированный
> venv в `/opt/wifite3` и root-owned ссылку `/usr/local/bin/wifite3`.

## Ubuntu / Debian / Kali

```bash
./install.sh
```

## Arch / Manjaro

```bash
./install.sh
```

Установщик ставит системные зависимости через `apt` или `pacman`, а само
приложение — в root-owned venv под `/opt/wifite3`, не затрагивая системный
Python и не привязывая запуск `sudo` к окружению пользователя.

## Разработка

На Linux установщик может подготовить dev-окружение:

```bash
./install.sh --dev
.venv/bin/wifite3 --demo
.venv/bin/pytest
```

На macOS `install.sh` не используется (он устанавливает Linux-системные
зависимости); создайте виртуальное окружение напрямую:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/wifite3 --demo
.venv/bin/pytest
```

`--demo` не требует root и Wi-Fi карты. На macOS TUI тоже запускается в
demo-режиме, но реальное сканирование доступно только на Linux.

## Проверка

```bash
sudo wifite3 --doctor
sudo wifite3 --doctor --deep   # + aireplay-ng --test
```

Что должно быть `ok`:

- Linux host;
- root (для реального сканирования);
- `airmon-ng`, `airodump-ng`, `aireplay-ng`, `aircrack-ng`, `iw`, `ip`;
- хотя бы один адаптер с monitor mode;
- `rfkill` не блокирует Wi-Fi.

## Частые проблемы

### `airodump-ng not found`

Установите `aircrack-ng`:

```bash
sudo dnf install aircrack-ng     # Fedora
sudo apt install aircrack-ng     # Debian/Ubuntu
sudo pacman -S aircrack-ng       # Arch
```

### `monitor mode not supported`

Смотрите `--doctor`: у адаптера должно быть `monitor` в capabilities.
Встроенные карты Intel/Realtek часто не умеют monitor mode или делают это
нестабильно. Внешний USB-адаптер на Atheros/MediaTek (например, AR9271,
MT7612U) обычно работает лучше.

### `rfkill` блокирует Wi-Fi

```bash
sudo rfkill unblock wifi
```

### NetworkManager переключает карту обратно

Wifite3 останавливает конфликтующие процессы при необходимости. Можно
форсировать:

```bash
sudo wifite3 --classic --kill
```

Или в TUI включить `Kill interfering processes`.

### `Interface wlan0mon does not exist`

После сканирования имя интерфейса может измениться (`wlan0` → `wlan0mon`).
Нажмите `r` в TUI, чтобы перечитать адаптеры, либо запускайте с
`-i wlan0` и дайте Wifite3 самому включить monitor mode.

### `pip: externally-managed-environment`

Не запускайте `pip install` в системный Python. Используйте `./install.sh`
для root-owned установки или `python3 -m venv .venv` для разработки.

### TUI не открывается / «No interactive terminal»

TUI требует настоящий TTY. В cron/CI/скриптах используйте:

```bash
sudo wifite3 --classic ...
```

### Хочу старый интерфейс Wifite2

```bash
sudo wifite3 --classic
sudo wifite3 --classic --help
```

### Где лежат сессии и логи

```text
~/.wifite3/sessions/
~/.wifite3/wifite.log
~/.wifite3/ieee-oui.txt   # после --update-db
```

## Удаление

```bash
./uninstall.sh
rm -rf ~/.wifite3
```

Системные пакеты (`aircrack-ng`, `hashcat`, …) не удаляются.
