"""NTS Radio API client.

Handles fetching live channel info, mixtape listings, and artwork.
"""

import io
import json
import logging
import os
import time
import hashlib
from pathlib import Path
from typing import Optional

import requests
from PIL import Image

logger = logging.getLogger(__name__)

# API endpoints
LIVE_URL = "https://www.nts.live/api/v2/live"
MIXTAPES_URL = "https://www.nts.live/api/v2/mixtapes"
# Stream URLs
STREAM_URLS = {
    1: "https://stream-relay-geo.ntslive.net/stream",
    2: "https://stream-relay-geo.ntslive.net/stream2",
}

# Artwork cache directory
ARTWORK_CACHE_DIR = Path("/tmp/nts-artwork")


class NTSClient:
    """Client for the NTS Radio API."""

    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "User-Agent": "NTSRadioPi/1.0",
            "Accept": "application/json",
        })

        # Caches
        self._live_cache: Optional[dict] = None
        self._live_cache_time: float = 0
        self._mixtapes_cache: Optional[list] = None

        # Cache TTLs (seconds)
        self.live_ttl = 30

        # Ensure artwork cache dir exists
        ARTWORK_CACHE_DIR.mkdir(parents=True, exist_ok=True)

    def get_live(self, force_refresh: bool = False) -> Optional[dict]:
        """Fetch live channel data. Returns cached data if fresh enough."""
        now = time.time()
        if (
            not force_refresh
            and self._live_cache is not None
            and (now - self._live_cache_time) < self.live_ttl
        ):
            return self._live_cache

        try:
            resp = self.session.get(LIVE_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._live_cache = data
            self._live_cache_time = now
            return data
        except Exception:
            logger.exception("Failed to fetch live data")
            # Return stale cache if available
            return self._live_cache

    def get_channel_info(self, channel: int) -> Optional[dict]:
        """Get info for a specific live channel (1 or 2).

        Returns dict with keys:
            channel_name, title, description, artwork_url,
            start_timestamp, end_timestamp
        """
        data = self.get_live()
        if not data or "results" not in data:
            return None

        idx = channel - 1
        if idx < 0 or idx >= len(data["results"]):
            return None

        result = data["results"][idx]
        now_block = result.get("now", {})

        # Extract artwork URL from embeds
        artwork_url = None
        embeds = now_block.get("embeds", {})
        details = embeds.get("details", {})
        if isinstance(details, dict):
            media = details.get("media", {})
            artwork_url = media.get("background_large")
        elif isinstance(details, list) and details:
            media = details[0].get("media", {})
            artwork_url = media.get("background_large")

        return {
            "channel_name": result.get("channel_name", f"NTS {channel}"),
            "title": now_block.get("broadcast_title", "Unknown Show"),
            "description": details.get("description", "") if isinstance(details, dict) else "",
            "artist": details.get("name", "") if isinstance(details, dict) else "",
            "artwork_url": artwork_url,
            "start_timestamp": now_block.get("start_timestamp"),
            "end_timestamp": now_block.get("end_timestamp"),
        }

    def get_mixtapes(self, force_refresh: bool = False) -> list:
        """Fetch all available infinite mixtapes. Cached after first call."""
        if not force_refresh and self._mixtapes_cache is not None:
            return self._mixtapes_cache

        try:
            resp = self.session.get(MIXTAPES_URL, timeout=10)
            resp.raise_for_status()
            data = resp.json()
            self._mixtapes_cache = data.get("results", [])
            return self._mixtapes_cache
        except Exception:
            logger.exception("Failed to fetch mixtapes")
            return self._mixtapes_cache or []

    def get_mixtape_stream_url(self, mixtape: dict) -> Optional[str]:
        """Get the stream URL for a mixtape."""
        return mixtape.get("audio_stream_endpoint")

    def download_artwork(self, url: Optional[str], size: int = 120) -> Optional[Image.Image]:
        """Download and cache artwork, resized to size x size.

        Returns a PIL Image or None on failure.
        """
        if not url:
            return None

        # Create a cache key from the URL
        url_hash = hashlib.md5(url.encode()).hexdigest()
        cache_path = ARTWORK_CACHE_DIR / f"{url_hash}_{size}.png"

        # Check cache
        if cache_path.exists():
            try:
                return Image.open(cache_path).copy()
            except Exception:
                pass  # Re-download if cache is corrupt

        try:
            resp = self.session.get(url, timeout=15)
            resp.raise_for_status()
            img = Image.open(io.BytesIO(resp.content))
            img = img.convert("RGB")
            img = img.resize((size, size), Image.LANCZOS)
            img.save(cache_path, "PNG")
            return img
        except Exception:
            logger.warning("Failed to download artwork: %s", url)
            return None

    def get_stream_url(self, channel: int) -> str:
        """Get the stream URL for a live channel."""
        return STREAM_URLS.get(channel, STREAM_URLS[1])
