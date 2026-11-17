# Архитектура Wifite3

```text
wifite3/
├── cli.py            # wifite3 / wifite3 --classic / --doctor / --demo
├── bridge.py         # движок <-> TUI: вывод, ввод, скан, атака, cleanup
├── system.py         # Linux: дистрибутив, адаптеры, iw/airmon данные
├── doctor.py         # проверки и команды установки
├── tui/
│   ├── app.py        # главный Textual App: dashboard, selection
│   ├── screens.py    # AttackScreen, DoctorScreen, модалки
│   ├── widgets.py    # форматирование целей, таблица
│   └── theme.tcss    # тёмная тема
├── attack/           # Wifite2: WPA/WEP/WPS/PMKID/WPA3/OWE/EvilTwin
├── tools/            # Wifite2: airmon/airodump/reaver/hashcat/...
├── util/             # Wifite2: scanner, session, crack, process, ...
├── config/           # Wifite2: Configuration, defaults, parsers
├── model/            # Wifite2: Target, Client, Result
├── native/           # Wifite2: scapy-based fallbacks
└── data/             # OUI-база и wordlist (package data)
```

## Почему движок не переписан

Атакующий код Wifite2 — это 50k строк, сотни граничных случаев с драйверами,
`airodump-ng`, `reaver`, `hashcat`, PMKID и dual-interface. Переписывание
с нуля означало бы потерять функции и стабильность. Wifite3 сохраняет
движок и меняет только две границы:

1. **Вывод.** `Color.p/pl/pe` и `print()` патчатся на время атаки и
   превращаются в аккуратные строки в `RichLog`. ANSI-коды и `\r`-перерисовки
   обрабатываются `LineBuffer`, поэтому progress-строки не спамят лог.
2. **Ввод.** `builtins.input` маршрутизируется в `InputScreen`. Рабочий поток
   движка блокируется, UI остаётся отзывчивым; после ответа поток продолжает
   работу.

## Потоки

- **UI thread** — Textual event loop.
- **scan worker** (`@work thread=True`) — `Configuration.get_monitor_mode_interface()`,
  затем `Airodump` и цикл чтения CSV. Обновления уходят в UI через
  `call_from_thread`.
- **attack worker** (`@work thread=True`) — `AttackAll.attack_multiple`.
  Кнопка Stop выставляет событие, шлёт `KeyboardInterrupt` в поток через
  `PyThreadState_SetAsyncExc` и убивает дочерние процессы.
- **cleanup** — `ProcessManager`, `InterfaceManager`, `Airmon.stop`,
  восстановление managed-интерфейсов при выходе.

## Сканирование

TUI не использует `Scanner.find_targets()` (он завязан на интерактивный
терминал). Вместо этого `bridge.ScanRunner` напрямую работает с
`tools.airodump.Airodump`:

```python
with Airodump(output_file_prefix="wifite3_scan") as airodump:
    while not stop:
        targets = airodump.get_targets(old_targets=..., target_archives=...)
        emit(ScanUpdate(targets, ...))
```

`Target` — тот же объект, что и в Wifite2, поэтому все поля (WPS, WPA3,
клиенты, honeypot score, PMF) доступны без конвертации.

## Демо-режим

`bridge.demo_targets()` создаёт настоящие `Target`/`Client` объекты с
синтетическими BSSID. `AttackScreen` в demo-режиме имитирует фазы
PMKID → deauth → handshake → cracking, обновляет статусы и лог. Это
позволяет разрабатывать и тестировать UI на macOS и в CI.

## Совместимость с Wifite2

- Пакет называется `wifite3`, поэтому не конфликтует с `wifite2`.
- Относительные импорты движка сохранены; абсолютные `wifite.` заменены на
  `wifite3.`.
- `--classic` вызывает `wifite3.wifite.main()` — тот же код, что и раньше,
  включая все флаги, сессии, updater и cleanup.
