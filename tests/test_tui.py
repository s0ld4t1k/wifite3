import asyncio

from wifite3.bridge import EngineOptions, demo_targets
from wifite3.tui.app import Wifite3App
from wifite3.tui.screens import AttackScreen, DetailsScreen, DoctorScreen, HelpScreen


def test_demo_app_mounts_and_selects():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            table = app.query_one("#targets")
            assert len(table.columns) == 10
            for index, target in enumerate(demo_targets(), start=1):
                app._demo_add(target, index)
            app._demo_finished()
            await pilot.pause()
            assert table.row_count == len(demo_targets())

            await pilot.press("space")
            await pilot.pause()
            assert len(app.selected) == 1

            await pilot.press("a")
            await pilot.pause()
            assert len(app.selected) == table.row_count

            await pilot.press("n")
            await pilot.pause()
            assert app.selected == set()

    asyncio.run(scenario())


def test_filter_and_sort():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            for index, target in enumerate(demo_targets(), start=1):
                app._demo_add(target, index)
            await pilot.pause()
            app.query_one("#filter").value = "TP-Link"
            await pilot.pause()
            assert len(app.visible_bssids) == 1
            app.query_one("#filter").value = ""
            await pilot.pause()
            app.sort_column = "ssid"
            app.sort_reverse = False
            app._rebuild_table()
            await pilot.pause()
            assert len(app.visible_bssids) == len(demo_targets())

    asyncio.run(scenario())


def test_details_and_help_screens_open():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            for index, target in enumerate(demo_targets(), start=1):
                app._demo_add(target, index)
            await pilot.pause()
            app.action_details()
            await pilot.pause()
            assert isinstance(app.screen, DetailsScreen)
            await pilot.press("escape")
            await pilot.pause()

            app.push_screen(HelpScreen())
            await pilot.pause()
            assert isinstance(app.screen, HelpScreen)
            await pilot.press("escape")
            await pilot.pause()

    asyncio.run(scenario())


def test_input_screen_escapes_engine_prompt():
    from wifite3.tui.screens import InputScreen

    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(120, 36)) as pilot:
            await pilot.pause()
            app.push_screen(InputScreen("Continue? [Y/n] {raw}"))
            await pilot.pause()
            assert isinstance(app.screen, InputScreen)
            assert app.screen.prompt == "Continue? [Y/n] {raw}"
            assert app.screen.query_one("#input-field") is not None

    asyncio.run(scenario())


def test_doctor_screen_mounts():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            app.push_screen(DoctorScreen())
            await pilot.pause(1.0)
            assert isinstance(app.screen, DoctorScreen)
            assert app.screen.query_one("#doctor-table").row_count > 0

    asyncio.run(scenario())


def test_rebuild_keeps_current_target():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            for index, target in enumerate(demo_targets(), start=1):
                app._demo_add(target, index)
            await pilot.pause()
            chosen = app.visible_bssids[3]
            app.current_bssid = chosen
            app._rebuild_table()
            await pilot.pause()
            assert app.current_bssid == chosen
            assert app.query_one("#targets").cursor_row == 3

    asyncio.run(scenario())


def test_attack_defers_until_scan_finishes():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            targets = demo_targets()[:1]
            launched = []
            app._launch_attack = lambda chosen: launched.append(chosen)

            app.scanning = True
            app._request_attack(targets)
            await pilot.pause()
            assert launched == []
            assert app._pending_attack == targets
            assert app.scanning is True  # still true until the worker reports back

            app._scan_finished(None)
            await pilot.pause()
            assert launched == [targets]
            assert app._pending_attack is None

    asyncio.run(scenario())


def test_attack_toggles_exclude_targets():
    async def scenario():
        options = EngineOptions(pmkid=False, handshake=False, wps=False, wep=True)
        app = Wifite3App(demo=True, options=options)
        async with app.run_test(size=(140, 44)) as pilot:
            await pilot.pause()
            targets = demo_targets()
            wep = next(target for target in targets if target.primary_encryption == "WEP")
            wpa = next(
                target
                for target in targets
                if target.primary_encryption == "WPA2" and getattr(target, "wps", 0) == 0
            )
            pushed = []
            app.push_screen = lambda screen: pushed.append(screen)

            app._launch_attack([wep, wpa])
            await pilot.pause()
            assert len(pushed) == 1
            assert isinstance(pushed[0], AttackScreen)
            assert pushed[0].targets == [wep]

    asyncio.run(scenario())


def test_attack_screen_demo_runs():
    async def scenario():
        app = Wifite3App(demo=True)
        async with app.run_test(size=(150, 46)) as pilot:
            await pilot.pause()
            targets = demo_targets()[:2]
            for index, target in enumerate(targets, start=1):
                app._demo_add(target, index)
            app._demo_finished()
            await pilot.pause()
            app.push_screen(AttackScreen(targets, demo=True))
            await pilot.pause(6.0)
            assert isinstance(app.screen, AttackScreen)
            assert app.screen.finished is True
            table = app.screen.query_one("#attack-targets")
            assert table.row_count == 2

    asyncio.run(scenario())
