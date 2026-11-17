# Roadmap

## 0.1.x — alpha (сейчас)

- [x] Vendored Wifite2 engine (WPA/WEP/WPS/PMKID/WPA3/OWE/Evil Twin)
- [x] Textual TUI: dashboard, scan, selection, details, attack log
- [x] Engine output/input bridge
- [x] Stop attack (event + async interrupt + child cleanup)
- [x] `--doctor`, `--demo`, `--classic`
- [x] Distro-aware `install.sh`
- [x] Bundled OUI + wordlist, package-data safe paths

## 0.2 — polish

- [ ] Resume session из TUI (`--resume` уже есть в classic)
- [ ] Настройки в `~/.config/wifite3/config.toml`
- [ ] Экспорт scan/attack отчёта (JSON/HTML)
- [ ] Улучшенный per-target прогресс для реальных атак
- [x] Скриншоты в README
- [ ] GIF-демонстрация в README
- [x] CI: pytest + headless Textual на Linux
- [ ] PyPI-релиз

## 0.3 — дальше

- [ ] Плагины/профили атак (например, «только PMKID», «только WPS Pixie»)
- [ ] Параллельный скан нескольких адаптеров
- [ ] Интеграция wpa-sec upload из TUI
- [ ] Локализация интерфейса (ru/en)
- [ ] Пакеты `.rpm`, `.deb`, AUR

## Идеи, которые не входят в ядро

- Веб-интерфейс (отдельный проект)
- Android-обёртка
- Автоматическое скачивание драйверов (опасно и непереносимо)
