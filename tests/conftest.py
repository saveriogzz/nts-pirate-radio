"""Shared fixtures for NTS Radio tests.

Mocks hardware dependencies (GPIO, ST7789, mpv) so tests run on any machine.
"""

import sys
import types
from unittest.mock import MagicMock, patch

import pytest


# ── Mock RPi.GPIO before any nts module imports it ──────────────

def _build_mock_gpio():
    """Create a mock RPi.GPIO module with the constants buttons.py needs."""
    gpio = MagicMock()
    gpio.BCM = 11
    gpio.IN = 1
    gpio.OUT = 0
    gpio.PUD_UP = 22
    gpio.FALLING = 32
    gpio.RISING = 31
    gpio.setmode = MagicMock()
    gpio.setwarnings = MagicMock()
    gpio.setup = MagicMock()
    gpio.input = MagicMock(return_value=1)  # default: button released
    gpio.add_event_detect = MagicMock()
    gpio.remove_event_detect = MagicMock()
    gpio.cleanup = MagicMock()
    return gpio


@pytest.fixture(autouse=True)
def mock_gpio(monkeypatch):
    """Inject a mock RPi.GPIO into sys.modules for every test."""
    gpio = _build_mock_gpio()
    rpi_pkg = types.ModuleType("RPi")
    rpi_pkg.GPIO = gpio
    monkeypatch.setitem(sys.modules, "RPi", rpi_pkg)
    monkeypatch.setitem(sys.modules, "RPi.GPIO", gpio)
    return gpio


# ── Mock ST7789 ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_st7789(monkeypatch):
    """Inject a mock st7789 module."""
    st = MagicMock()
    st.ST7789.return_value = MagicMock()
    monkeypatch.setitem(sys.modules, "st7789", st)
    return st


# ── Mock spidev ──────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_spidev(monkeypatch):
    spidev = MagicMock()
    monkeypatch.setitem(sys.modules, "spidev", spidev)
    return spidev


# ── Sample API responses ────────────────────────────────────────

SAMPLE_LIVE_RESPONSE = {
    "results": [
        {
            "channel_name": "NTS 1",
            "now": {
                "broadcast_title": "Test Show One",
                "start_timestamp": "2026-07-23T10:00:00Z",
                "end_timestamp": "2026-07-23T12:00:00Z",
                "embeds": {
                    "details": {
                        "name": "DJ Test",
                        "description": "A great show",
                        "media": {
                            "background_large": "https://media.ntslive.co.uk/test1.jpg",
                        },
                    }
                },
            },
        },
        {
            "channel_name": "NTS 2",
            "now": {
                "broadcast_title": "Test Show Two",
                "start_timestamp": "2026-07-23T11:00:00Z",
                "end_timestamp": "2026-07-23T13:00:00Z",
                "embeds": {
                    "details": {
                        "name": "DJ Two",
                        "description": "Another show",
                        "media": {
                            "background_large": "https://media.ntslive.co.uk/test2.jpg",
                        },
                    }
                },
            },
        },
    ]
}

SAMPLE_MIXTAPES_RESPONSE = {
    "results": [
        {
            "title": "Poolside",
            "subtitle": "Sun-kissed selections",
            "description": "Warm vibes for warm days",
            "mixtape_alias": "poolside",
            "path": "/infinite-mixtapes/poolside",
            "audio_stream_endpoint": "https://stream-mixtape.ntslive.net/mixtape-poolside",
        },
        {
            "title": "Slow Focus",
            "subtitle": "Deep concentration",
            "description": "Music for focus",
            "mixtape_alias": "slow-focus",
            "path": "/infinite-mixtapes/slow-focus",
            "audio_stream_endpoint": "https://stream-mixtape.ntslive.net/mixtape-slow-focus",
        },
    ]
}
