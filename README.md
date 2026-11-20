# Wifite3

**Современный TUI-аудитор Wi-Fi для Linux.** Внутри — движок
[Wifite2](https://github.com/kimocoder/wifite2) (WPA/WPA2/WPA3, PMKID, WPS,
WEP, OWE, Evil Twin, dual-interface), снаружи — удобный интерфейс и установка
без изменений системного Python.

> ⚠️ **Только для своих сетей.** Используйте Wifite3 только на сетях, которыми
> владеете или на тестирование которых есть письменное разрешение.
> Несанкционированный перехват трафика незаконен.

```
  ██╗    ██╗██╗███████╗██╗████████╗███████╗██████╗      ██████╗
  ██║    ██║██║██╔════╝██║╚══██╔══╝╔════╝╚════██╗    ╚════██║
  ██║ █╗ ██║██║█████╗  ██║   ██║   █████╗    █████╔╝      █████╔╝
  ██║███╗██║██║██╔══╝   ██║   ██║   ██╔══╝   ██╔═══╝      ╚════██║
  ╚███╔███╔╝██║██╔══╝   ██║   ██║   ███████╗██████╗      ██████╔╝
   ╚══╝╚══╝  ╚═╝ ╚═════╝╚═╝   ╚═╝   ╚══════╝╚══════╝     ╚═════╝
```

## Скриншоты

Главный экран: сканирование, фильтр, сортировка, выбор целей и карточка сети.

![Главный экран Wifite3](docs/screenshots/dashboard.png)

Атака: прогресс по целям и живой вывод движка (PMKID, handshake, cracking).

![Экран атаки Wifite3](docs/screenshots/attack.png)

## Что уже есть

- **Движок Wifite2** — WPA/WPA2/WPA3, PMKID, WPS, WEP, OWE, Evil Twin и
  dual-interface. Оригинальные компоненты и лицензия указаны в [NOTICE](NOTICE).
- **Textual TUI** — таблица сетей с сортировкой и фильтром, выбор целей,
  live-лог атаки, панель деталей и progress bar.
- **Живой ввод** — запросы движка (`wordlist`, подтверждение) открываются
  в модальном окне.
- **Остановка атаки** — Stop отправляет событие остановки, прерывает worker
  и завершает дочерние процессы.
- **`--doctor`** — диагностика Linux, root, адаптеров, monitor mode,
  `rfkill`, инструментов и данных.
- **Безопасная установка** — `install.sh` определяет Fedora / Ubuntu / Debian /
  Arch / openSUSE и ставит Python-приложение в изолированный root-owned venv
  `/opt/wifite3` (PEP 668).
- **`--demo`** — интерфейс и симуляция без Wi-Fi-карты; работает также на macOS.
- **`--classic`** — классический консольный режим Wifite2 со старыми флагами.

## Установка в Linux

### Рекомендуемый способ — установщик

Один и тот же установщик подходит для Fedora, Ubuntu, Debian, Kali, Linux Mint,
Arch, Manjaro, EndeavourOS, openSUSE и Alpine. Он определяет семейство
дистрибутива, ставит доступные системные инструменты и устанавливает Wifite3
в root-owned окружение `/opt/wifite3/venv` (не затрагивая системный Python).

Сначала убедитесь, что установлен Python 3.10 или новее, затем выполните:

```bash
git clone https://github.com/s0ld4t1k/wifite3.git
cd wifite3
./install.sh

sudo wifite3            # запустить TUI
wifite3 --demo          # попробовать интерфейс без Wi-Fi-адаптера
sudo wifite3 --doctor   # проверить готовность Linux и адаптеров
```

Установщик запросит `sudo` для системной установки, если он запущен не от root.
Опциональные инструменты для отдельных режимов (например, WPS, Evil Twin и
cracking) могут отсутствовать в репозиториях конкретного дистрибутива; в таком
случае установщик предупредит, а `--doctor` покажет, какие команды доступны.

### Установка системных зависимостей вручную

Если не хотите, чтобы установщик ставил системные пакеты, установите основной
toolchain командой для своего дистрибутива, затем выполните `./install.sh --no-deps`
для установки приложения в `/opt/wifite3`.

**Fedora / RHEL / CentOS:**

```bash
sudo dnf install -y python3 aircrack-ng iw iproute wireless-regdb \
  usbutils pciutils rfkill wpa_supplicant
```

**Ubuntu / Debian / Kali / Linux Mint** (включая другие Debian-based системы):

```bash
sudo apt update
sudo apt install -y python3 python3-venv aircrack-ng iw iproute2 \
  wireless-regdb usbutils pciutils rfkill wpasupplicant
```

**Arch Linux / Manjaro / EndeavourOS:**

```bash
sudo pacman -Syu --needed python aircrack-ng iw iproute2 wireless-regdb \
  usbutils pciutils rfkill wpa_supplicant
```

**openSUSE:**

```bash
sudo zypper refresh
sudo zypper install -y python3 python3-pip aircrack-ng iw iproute2 \
  wireless-regdb usbutils pciutils rfkill wpa_supplicant
```

**Alpine Linux:**

```bash
sudo apk update
sudo apk add python3 py3-pip aircrack-ng iw iproute2 wireless-regdb \
  usbutils pciutils rfkill wpa_supplicant
```

Затем из папки репозитория:

```bash
./install.sh --no-deps
sudo wifite3
```

Некоторые необязательные пакеты имеют другие имена или не входят в основные
репозитории. Для WPS, PMKID, Evil Twin и cracking инструменты устанавливаются
по мере необходимости; проверьте доступность через `sudo wifite3 --doctor`.
Не запускайте `sudo pip install` в системный Python (PEP 668).

### Разработка и запуск demo

На Linux можно создать редактируемое dev-окружение:

```bash
./install.sh --dev
.venv/bin/wifite3 --demo
.venv/bin/pytest
```

На macOS `install.sh` не используется — он предназначен для установки Linux-
зависимостей. Для разработки создайте venv напрямую:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -e '.[dev]'
.venv/bin/wifite3 --demo
.venv/bin/pytest
```

Demo не требует root или Wi-Fi-адаптера. Реальное сканирование доступно только
на Linux с подходящим адаптером.

## Управление

| Клавиша | Действие |
|---|---|
| `s` | старт / стоп сканирования |
| `space` | выбрать / снять выбор цели |
| `a` / `n` | выбрать все / снять всё |
| `enter` | атаковать выбранные (или все видимые) |
| `f` | фильтр по SSID / BSSID / вендору |
| `esc` | сбросить фильтр |
| `d` | полная карточка цели и клиенты |
| `r` | перечитать адаптеры |
| `?` | помощь |
| `q` | выход |

Клик по заголовку колонки — сортировка. В экране атаки `s` — остановить,
`esc` — назад (с подтверждением).

## Особенности установки

1. **Безопасно для PEP 668** — системный Python не используется для установки
   приложения. Wifite3 устанавливается в изолированный `/opt/wifite3/venv`;
   системные Wi-Fi-инструменты устанавливаются пакетным менеджером дистрибутива.
2. **Имя пакета** — Python-пакет называется `wifite3`, поэтому не конфликтует
   с установленным `wifite2`.
3. **Системные инструменты** — `install.sh` ставит основной toolchain, а
   `--doctor` объясняет, чего не хватает.
4. **Пути к данным** — OUI-база и wordlist входят в пакет и доступны вне папки
   репозитория.
5. **Терминал** — без интерактивного TTY программа переключается в classic;
   `--classic` можно указать явно.

## Документация

- [docs/INSTALL.md](docs/INSTALL.md) — установка и решение проблем.
- [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) — устройство проекта.
- [docs/ROADMAP.md](docs/ROADMAP.md) — план развития.
- [NOTICE](NOTICE) — происхождение движка и атрибуция.
