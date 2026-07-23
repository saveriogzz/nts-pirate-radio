#!/usr/bin/env python3
"""NTS Radio main application.

State machine that ties together the API client, mpv player,
ST7789 display, and GPIO buttons into a cohesive radio experience.
"""

import logging
import os
import signal

import sys
import threading
import time
from enum import Enum, auto
from typing import Optional

from nts.api import NTSClient
from nts.player import MPVPlayer
from nts.display import Display
from nts.buttons import (
    ButtonHandler,
    BUTTON_A,
    BUTTON_B,
    BUTTON_X,
    BUTTON_Y,
)

logger = logging.getLogger(__name__)

# Default config values — overridden by environment variables (Balena device vars)
# NTS_DEFAULT_CHANNEL, NTS_DISPLAY_BRIGHTNESS, NTS_BUTTON_DEBOUNCE_MS
DEFAULT_CONFIG = {
    "default_channel": 1,
    "display_brightness": 80,
    "button_debounce_ms": 200,
}

# Refresh intervals (seconds)
LIVE_REFRESH_INTERVAL = 30
DISPLAY_REFRESH_INTERVAL = 5  # For progress bar updates


class AppState(Enum):
    """Application screen states."""
    LIVE = auto()
    MIXTAPE = auto()
    MENU = auto()


class NTSRadioApp:
    """Main application class for NTS Radio on Pirate Audio."""

    # Menu items
    MENU_ITEMS = ["Live Radio", "Mixtapes"]

    def __init__(self):
        self._config = self._load_config()
        self._state = AppState.LIVE
        self._lock = threading.Lock()
        self._running = False

        # Current selections
        self._current_channel = self._config.get("default_channel", 1)
        self._current_mixtape_idx = 0
        self._menu_selection = 0

        # Cached data
        self._channel_info: Optional[dict] = None
        self._mixtapes: list = []
        self._artwork_cache: dict[str, "Image.Image"] = {}
        self._current_artwork = None

        # Components (initialized in start())
        self._api: Optional[NTSClient] = None
        self._player: Optional[MPVPlayer] = None
        self._display: Optional[Display] = None
        self._buttons: Optional[ButtonHandler] = None

        # Track what changed for display updates
        self._display_dirty = True

    def _load_config(self) -> dict:
        """Load configuration from environment variables (balena device vars).

        Environment variables:
            NTS_DEFAULT_CHANNEL: 1 or 2
            NTS_DISPLAY_BRIGHTNESS: 0-100
            NTS_BUTTON_DEBOUNCE_MS: debounce time in ms
        """
        config = DEFAULT_CONFIG.copy()

        if os.environ.get("NTS_DEFAULT_CHANNEL"):
            try:
                config["default_channel"] = int(os.environ["NTS_DEFAULT_CHANNEL"])
            except ValueError:
                pass
        if os.environ.get("NTS_DISPLAY_BRIGHTNESS"):
            try:
                config["display_brightness"] = int(os.environ["NTS_DISPLAY_BRIGHTNESS"])
            except ValueError:
                pass
        if os.environ.get("NTS_BUTTON_DEBOUNCE_MS"):
            try:
                config["button_debounce_ms"] = int(os.environ["NTS_BUTTON_DEBOUNCE_MS"])
            except ValueError:
                pass

        logger.info("Config loaded from environment variables")
        return config

    # ── State machine ────────────────────────────────────────

    def _set_state(self, new_state: AppState):
        """Thread-safe state transition."""
        with self._lock:
            old_state = self._state
            self._state = new_state
            self._display_dirty = True
            logger.info("State: %s -> %s", old_state.name, new_state.name)

    def _get_state(self) -> AppState:
        """Thread-safe state read."""
        with self._lock:
            return self._state

    # ── Button handlers ──────────────────────────────────────

    def _on_button_a(self):
        """Button A (top-left): Previous channel/item or scroll up."""
        state = self._get_state()

        if state == AppState.LIVE:
            # Toggle between channel 1 and 2
            self._current_channel = 1 if self._current_channel == 2 else 2
            self._play_current()
            self._fetch_and_update_live()

        elif state == AppState.MIXTAPE:
            # Previous mixtape
            if self._mixtapes:
                self._current_mixtape_idx = (
                    (self._current_mixtape_idx - 1) % len(self._mixtapes)
                )
                self._display_dirty = True

        elif state == AppState.MENU:
            # Scroll up in menu
            self._menu_selection = (self._menu_selection - 1) % len(self.MENU_ITEMS)
            self._display_dirty = True

    def _on_button_b(self):
        """Button B (bottom-left): Next channel/item or scroll down."""
        state = self._get_state()

        if state == AppState.LIVE:
            self._current_channel = 1 if self._current_channel == 2 else 2
            self._play_current()
            self._fetch_and_update_live()

        elif state == AppState.MIXTAPE:
            if self._mixtapes:
                self._current_mixtape_idx = (
                    (self._current_mixtape_idx + 1) % len(self._mixtapes)
                )
                self._display_dirty = True

        elif state == AppState.MENU:
            self._menu_selection = (self._menu_selection + 1) % len(self.MENU_ITEMS)
            self._display_dirty = True

    def _on_button_x(self):
        """Button X (top-right): Play/Pause or select in menu."""
        state = self._get_state()

        if state == AppState.LIVE or state == AppState.MIXTAPE:
            self._player.toggle_pause()
            self._display_dirty = True

        elif state == AppState.MENU:
            self._select_menu_item()

    def _on_button_y(self):
        """Button Y (bottom-right): Open/close menu."""
        state = self._get_state()

        if state == AppState.MENU:
            # Go back to previous state based on what's playing
            self._return_from_menu()

        else:
            # Open menu
            self._set_state(AppState.MENU)
            self._menu_selection = 0

    # ── Menu actions ─────────────────────────────────────────

    def _select_menu_item(self):
        """Handle menu item selection."""
        item = self.MENU_ITEMS[self._menu_selection]

        if item == "Live Radio":
            self._set_state(AppState.LIVE)
            self._play_current()
            self._fetch_and_update_live()

        elif item == "Mixtapes":
            self._set_state(AppState.MIXTAPE)
            if not self._mixtapes:
                self._mixtapes = self._api.get_mixtapes()


    def _return_from_menu(self):
        """Return to the appropriate screen from menu."""
        # Determine what to go back to based on what's playing
        url = self._player.get_current_url() if self._player else None
        if url and "stream2" in url:
            self._current_channel = 2
            self._set_state(AppState.LIVE)
        elif url and "stream" in url and "mixtape" not in url.lower():
            self._set_state(AppState.LIVE)
        elif url:
            # Check if it's a mixtape URL
            for i, m in enumerate(self._mixtapes):
                if m.get("audio_stream_endpoint") == url:
                    self._current_mixtape_idx = i
                    self._set_state(AppState.MIXTAPE)
                    return
            self._set_state(AppState.LIVE)
        else:
            self._set_state(AppState.LIVE)

    # ── Playback ─────────────────────────────────────────────

    def _play_current(self):
        """Play the current live channel."""
        url = self._api.get_stream_url(self._current_channel)
        self._player.play(url)
        self._display_dirty = True

    def _play_mixtape(self, idx: int):
        """Play a specific mixtape by index."""
        if 0 <= idx < len(self._mixtapes):
            mixtape = self._mixtapes[idx]
            url = self._api.get_mixtape_stream_url(mixtape)
            if url:
                self._player.play(url)
                self._current_mixtape_idx = idx
                self._display_dirty = True

    # ── Data fetching ────────────────────────────────────────

    def _fetch_and_update_live(self):
        """Fetch live channel info and update artwork."""
        info = self._api.get_channel_info(self._current_channel)
        if info:
            self._channel_info = info
            self._display_dirty = True

            # Fetch artwork in background
            artwork_url = info.get("artwork_url")
            if artwork_url and artwork_url not in self._artwork_cache:
                threading.Thread(
                    target=self._fetch_artwork,
                    args=(artwork_url,),
                    daemon=True,
                    name="artwork-fetch",
                ).start()
            elif artwork_url:
                self._current_artwork = self._artwork_cache.get(artwork_url)

    def _fetch_artwork(self, url: str):
        """Fetch artwork in a background thread."""
        img = self._api.download_artwork(url)
        if img:
            # Limit cache size to save memory on Pi Zero
            if len(self._artwork_cache) > 10:
                # Remove oldest entries
                oldest = list(self._artwork_cache.keys())[:5]
                for key in oldest:
                    del self._artwork_cache[key]

            self._artwork_cache[url] = img
            self._current_artwork = img
            self._display_dirty = True

    # ── Display update ───────────────────────────────────────

    def _update_display(self):
        """Render the current state to the display."""
        if not self._display_dirty:
            return

        state = self._get_state()

        try:
            if state == AppState.LIVE:
                if self._channel_info:
                    artwork_url = self._channel_info.get("artwork_url")
                    artwork = self._artwork_cache.get(artwork_url) if artwork_url else None
                    self._display.render_live(
                        self._channel_info,
                        self._player.is_playing(),
                        artwork=artwork,
                    )
                else:
                    self._display.render_message(
                        "NTS RADIO", "Loading..."
                    )

            elif state == AppState.MIXTAPE:
                if self._mixtapes:
                    mixtape = self._mixtapes[self._current_mixtape_idx]
                    self._display.render_mixtape(
                        mixtape,
                        self._player.is_playing(),
                    )
                else:
                    self._display.render_message("MIXTAPES", "Loading...")

            elif state == AppState.MENU:
                self._display.render_menu(self.MENU_ITEMS, self._menu_selection)

            self._display_dirty = False
        except Exception:
            logger.exception("Display update failed")

    def _cleanup(self):
        """Clean up all resources."""
        self._running = False

        if self._buttons:
            self._buttons.cleanup()
        if self._player:
            self._player.shutdown()
        if self._display:
            self._display.shutdown()

    # ── Main loop ────────────────────────────────────────────

    def start(self):
        """Initialize components and start the main loop."""
        # Set up logging
        logging.basicConfig(
            level=logging.INFO,
            format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
            datefmt="%H:%M:%S",
        )
        logger.info("NTS Radio starting up")

        # Register signal handlers
        signal.signal(signal.SIGTERM, lambda *_: self._signal_handler())
        signal.signal(signal.SIGINT, lambda *_: self._signal_handler())

        # Initialize components
        try:
            self._api = NTSClient()
            self._player = MPVPlayer()
            self._display = Display(
                brightness=self._config.get("display_brightness", 80)
            )
            self._buttons = ButtonHandler(
                debounce_ms=self._config.get("button_debounce_ms", 200)
            )
        except Exception:
            logger.exception("Failed to initialize components")
            self._cleanup()
            sys.exit(1)

        # Show loading screen
        self._display.render_message("NTS RADIO", "Starting up...")

        # Register button callbacks
        self._buttons.on_press(BUTTON_A, self._on_button_a)
        self._buttons.on_press(BUTTON_B, self._on_button_b)
        self._buttons.on_press(BUTTON_X, self._on_button_x)
        self._buttons.on_press(BUTTON_Y, self._on_button_y)
        self._buttons.start()

        # Pre-fetch data
        self._mixtapes = self._api.get_mixtapes()
        self._fetch_and_update_live()

        # Start playing default channel
        self._play_current()

        # Enter main loop
        self._running = True
        self._run_loop()

    def _run_loop(self):
        """Main event loop."""
        last_live_refresh = time.time()
        last_display_refresh = time.time()

        while self._running:
            try:
                now = time.time()

                # Periodic live data refresh
                if now - last_live_refresh >= LIVE_REFRESH_INTERVAL:
                    if self._get_state() == AppState.LIVE:
                        self._fetch_and_update_live()
                    last_live_refresh = now

                # Periodic display refresh (for progress bar)
                if now - last_display_refresh >= DISPLAY_REFRESH_INTERVAL:
                    if self._get_state() == AppState.LIVE:
                        self._display_dirty = True
                    last_display_refresh = now

                # Update display if needed
                self._update_display()

                # Sleep to avoid busy-waiting (100ms tick)
                time.sleep(0.1)

            except Exception:
                logger.exception("Error in main loop")
                time.sleep(1)  # Back off on error

    def _signal_handler(self):
        """Handle SIGTERM/SIGINT for graceful shutdown."""
        logger.info("Signal received, shutting down")
        self._running = False
        self._cleanup()
        sys.exit(0)


def main():
    """Entry point."""
    app = NTSRadioApp()
    app.start()


if __name__ == "__main__":
    main()
