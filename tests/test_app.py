"""Tests for nts.app — main application state machine."""

import os
from unittest.mock import MagicMock, patch, PropertyMock

import pytest

from tests.conftest import SAMPLE_LIVE_RESPONSE, SAMPLE_MIXTAPES_RESPONSE


def _make_app():
    """Create an NTSRadioApp with mocked components."""
    from nts.app import NTSRadioApp

    app = NTSRadioApp()
    app._api = MagicMock()
    app._player = MagicMock()
    app._display = MagicMock()
    app._buttons = MagicMock()

    # Set up default API behavior
    app._api.get_channel_info.return_value = {
        "channel_name": "NTS 1",
        "title": "Test Show",
        "artist": "DJ Test",
        "artwork_url": None,
        "start_timestamp": "2026-07-23T10:00:00Z",
        "end_timestamp": "2026-07-23T12:00:00Z",
    }
    app._api.get_stream_url.return_value = "https://stream-relay-geo.ntslive.net/stream"
    app._api.get_mixtapes.return_value = SAMPLE_MIXTAPES_RESPONSE["results"]
    app._api.get_mixtape_stream_url.return_value = "https://stream-mixtape.ntslive.net/mixtape-poolside"
    app._player.is_playing.return_value = True
    app._player.get_current_url.return_value = "https://stream-relay-geo.ntslive.net/stream"

    return app


class TestConfigLoading:
    """Tests for environment-based config loading."""

    def test_default_config(self):
        from nts.app import NTSRadioApp

        app = NTSRadioApp()
        assert app._config["default_channel"] == 1
        assert app._config["display_brightness"] == 80
        assert app._config["button_debounce_ms"] == 200

    def test_config_from_env(self, monkeypatch):
        from nts.app import NTSRadioApp

        monkeypatch.setenv("NTS_DEFAULT_CHANNEL", "2")
        monkeypatch.setenv("NTS_DISPLAY_BRIGHTNESS", "50")
        monkeypatch.setenv("NTS_BUTTON_DEBOUNCE_MS", "300")

        app = NTSRadioApp()
        assert app._config["default_channel"] == 2
        assert app._config["display_brightness"] == 50
        assert app._config["button_debounce_ms"] == 300

    def test_config_invalid_env_uses_default(self, monkeypatch):
        from nts.app import NTSRadioApp

        monkeypatch.setenv("NTS_DEFAULT_CHANNEL", "not_a_number")

        app = NTSRadioApp()
        assert app._config["default_channel"] == 1


class TestStateMachine:
    """Tests for state transitions."""

    def test_initial_state_is_live(self):
        from nts.app import AppState

        app = _make_app()
        assert app._get_state() == AppState.LIVE

    def test_button_y_opens_menu(self):
        from nts.app import AppState

        app = _make_app()
        app._on_button_y()
        assert app._get_state() == AppState.MENU
        assert app._menu_selection == 0

    def test_button_y_closes_menu(self):
        from nts.app import AppState

        app = _make_app()
        app._on_button_y()  # open menu
        assert app._get_state() == AppState.MENU

        app._on_button_y()  # close menu -> back to live
        assert app._get_state() == AppState.LIVE

    def test_menu_select_live_radio(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MENU)
        app._menu_selection = 0  # "Live Radio"

        app._on_button_x()  # select
        assert app._get_state() == AppState.LIVE
        app._player.play.assert_called()

    def test_menu_select_mixtapes(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MENU)
        app._menu_selection = 1  # "Mixtapes"

        app._on_button_x()  # select
        assert app._get_state() == AppState.MIXTAPE

    def test_menu_navigation_wraps(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MENU)
        app._menu_selection = 0

        app._on_button_a()  # scroll up from top -> wraps to bottom
        assert app._menu_selection == len(app.MENU_ITEMS) - 1

        app._on_button_b()  # scroll down from bottom -> wraps to top
        assert app._menu_selection == 0


class TestLiveChannelSwitching:
    """Tests for live channel switching."""

    def test_button_a_toggles_channel(self):
        app = _make_app()
        assert app._current_channel == 1

        app._on_button_a()
        assert app._current_channel == 2

        app._on_button_a()
        assert app._current_channel == 1

    def test_button_b_toggles_channel(self):
        app = _make_app()
        assert app._current_channel == 1

        app._on_button_b()
        assert app._current_channel == 2

    def test_channel_switch_triggers_playback(self):
        app = _make_app()
        app._on_button_a()
        app._player.play.assert_called()

    def test_play_pause_in_live(self):
        app = _make_app()
        app._on_button_x()
        app._player.toggle_pause.assert_called_once()


class TestMixtapeNavigation:
    """Tests for mixtape browsing."""

    def test_mixtape_scroll(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MIXTAPE)
        app._mixtapes = SAMPLE_MIXTAPES_RESPONSE["results"]
        app._current_mixtape_idx = 0

        app._on_button_b()  # next
        assert app._current_mixtape_idx == 1

        app._on_button_b()  # wraps
        assert app._current_mixtape_idx == 0

        app._on_button_a()  # prev wraps
        assert app._current_mixtape_idx == 1

    def test_play_pause_in_mixtape(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MIXTAPE)
        app._on_button_x()
        app._player.toggle_pause.assert_called_once()


class TestDisplayUpdate:
    """Tests for display rendering dispatch."""

    def test_live_display_renders_channel_info(self):
        from nts.app import AppState

        app = _make_app()
        app._channel_info = {
            "channel_name": "NTS 1",
            "title": "Test",
            "artwork_url": None,
        }
        app._display_dirty = True
        app._update_display()

        app._display.render_live.assert_called_once()

    def test_mixtape_display_renders(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MIXTAPE)
        app._mixtapes = SAMPLE_MIXTAPES_RESPONSE["results"]
        app._display_dirty = True
        app._update_display()

        app._display.render_mixtape.assert_called_once()

    def test_menu_display_renders(self):
        from nts.app import AppState

        app = _make_app()
        app._set_state(AppState.MENU)
        app._display_dirty = True
        app._update_display()

        app._display.render_menu.assert_called_once()

    def test_display_not_updated_when_clean(self):
        app = _make_app()
        app._channel_info = {"channel_name": "NTS 1", "title": "Test", "artwork_url": None}
        app._display_dirty = False
        app._update_display()

        app._display.render_live.assert_not_called()

    def test_loading_screen_when_no_channel_info(self):
        app = _make_app()
        app._channel_info = None
        app._display_dirty = True
        app._update_display()

        app._display.render_message.assert_called_with("NTS RADIO", "Loading...")


class TestReturnFromMenu:
    """Tests for returning to the correct screen from menu."""

    def test_returns_to_live_for_stream1(self):
        from nts.app import AppState

        app = _make_app()
        app._player.get_current_url.return_value = "https://stream-relay-geo.ntslive.net/stream"
        app._set_state(AppState.MENU)
        app._return_from_menu()
        assert app._get_state() == AppState.LIVE

    def test_returns_to_live_for_stream2(self):
        from nts.app import AppState

        app = _make_app()
        app._player.get_current_url.return_value = "https://stream-relay-geo.ntslive.net/stream2"
        app._set_state(AppState.MENU)
        app._return_from_menu()
        assert app._get_state() == AppState.LIVE
        assert app._current_channel == 2

    def test_returns_to_mixtape_when_playing_mixtape(self):
        from nts.app import AppState

        app = _make_app()
        app._mixtapes = SAMPLE_MIXTAPES_RESPONSE["results"]
        app._player.get_current_url.return_value = "https://stream-mixtape.ntslive.net/mixtape-poolside"
        app._set_state(AppState.MENU)
        app._return_from_menu()
        assert app._get_state() == AppState.MIXTAPE
        assert app._current_mixtape_idx == 0
