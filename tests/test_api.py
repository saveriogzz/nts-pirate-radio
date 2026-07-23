"""Tests for nts.api — NTS Radio API client."""

import io
import time
from unittest.mock import patch, MagicMock

import pytest
from PIL import Image

from tests.conftest import SAMPLE_LIVE_RESPONSE, SAMPLE_MIXTAPES_RESPONSE


class TestNTSClientLive:
    """Tests for live channel data fetching and parsing."""

    def test_get_live_returns_data(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            data = client.get_live()

            assert data is not None
            assert "results" in data
            assert len(data["results"]) == 2

    def test_get_live_caches_response(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            client.get_live()
            client.get_live()

            # Should only call the API once (second is cached)
            assert MockSession.return_value.get.call_count == 1

    def test_get_live_force_refresh_bypasses_cache(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            client.get_live()
            client.get_live(force_refresh=True)

            assert MockSession.return_value.get.call_count == 2

    def test_get_live_returns_stale_cache_on_error(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            client.get_live()

            # Expire cache
            client._live_cache_time = 0

            # Make next request fail
            MockSession.return_value.get.side_effect = Exception("Network error")
            data = client.get_live()

            # Should return stale cache
            assert data is not None
            assert data["results"][0]["channel_name"] == "NTS 1"

    def test_get_channel_info_parses_correctly(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            info = client.get_channel_info(1)

            assert info is not None
            assert info["channel_name"] == "NTS 1"
            assert info["title"] == "Test Show One"
            assert info["artist"] == "DJ Test"
            assert info["artwork_url"] == "https://media.ntslive.co.uk/test1.jpg"
            assert info["start_timestamp"] == "2026-07-23T10:00:00Z"
            assert info["end_timestamp"] == "2026-07-23T12:00:00Z"

    def test_get_channel_info_channel2(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            info = client.get_channel_info(2)

            assert info is not None
            assert info["channel_name"] == "NTS 2"
            assert info["title"] == "Test Show Two"

    def test_get_channel_info_invalid_channel_returns_none(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_LIVE_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            assert client.get_channel_info(0) is None
            assert client.get_channel_info(3) is None

    def test_get_channel_info_with_list_details(self):
        """Test parsing when embeds.details is a list instead of a dict."""
        from nts.api import NTSClient

        response = {
            "results": [{
                "channel_name": "NTS 1",
                "now": {
                    "broadcast_title": "List Show",
                    "start_timestamp": "2026-07-23T10:00:00Z",
                    "end_timestamp": "2026-07-23T12:00:00Z",
                    "embeds": {
                        "details": [{
                            "name": "Artist",
                            "media": {"background_large": "https://example.com/art.jpg"},
                        }]
                    },
                },
            }]
        }

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = response
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            info = client.get_channel_info(1)

            assert info["artwork_url"] == "https://example.com/art.jpg"


class TestNTSClientMixtapes:
    """Tests for mixtape listing and stream URLs."""

    def test_get_mixtapes_returns_list(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_MIXTAPES_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            # Need to set up live endpoint too for constructor
            mixtapes = client.get_mixtapes()

            assert len(mixtapes) == 2
            assert mixtapes[0]["title"] == "Poolside"
            assert mixtapes[1]["mixtape_alias"] == "slow-focus"

    def test_get_mixtapes_caches(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.json.return_value = SAMPLE_MIXTAPES_RESPONSE
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            client.get_mixtapes()
            client.get_mixtapes()

            # Only one call to the mixtapes endpoint
            assert MockSession.return_value.get.call_count == 1

    def test_get_mixtape_stream_url(self):
        from nts.api import NTSClient

        client = NTSClient.__new__(NTSClient)
        mixtape = {"audio_stream_endpoint": "https://stream.example.com/mix"}
        assert client.get_mixtape_stream_url(mixtape) == "https://stream.example.com/mix"

    def test_get_mixtape_stream_url_missing(self):
        from nts.api import NTSClient

        client = NTSClient.__new__(NTSClient)
        assert client.get_mixtape_stream_url({}) is None


class TestNTSClientStreamURLs:
    """Tests for stream URL mapping."""

    def test_stream_url_channel_1(self):
        from nts.api import NTSClient

        client = NTSClient.__new__(NTSClient)
        url = client.get_stream_url(1)
        assert "stream-relay-geo.ntslive.net/stream" in url
        assert "stream2" not in url

    def test_stream_url_channel_2(self):
        from nts.api import NTSClient

        client = NTSClient.__new__(NTSClient)
        url = client.get_stream_url(2)
        assert "stream2" in url

    def test_stream_url_invalid_defaults_to_1(self):
        from nts.api import NTSClient

        client = NTSClient.__new__(NTSClient)
        url = client.get_stream_url(99)
        assert url == client.get_stream_url(1)


class TestNTSClientArtwork:
    """Tests for artwork download and caching."""

    def test_download_artwork_returns_none_for_no_url(self):
        from nts.api import NTSClient

        with patch("nts.api.requests.Session"):
            client = NTSClient()
            assert client.download_artwork(None) is None
            assert client.download_artwork("") is None

    def test_download_artwork_resizes(self):
        from nts.api import NTSClient

        # Create a test image
        test_img = Image.new("RGB", (500, 500), (255, 0, 0))
        buf = io.BytesIO()
        test_img.save(buf, "PNG")
        buf.seek(0)

        with patch("nts.api.requests.Session") as MockSession:
            mock_resp = MagicMock()
            mock_resp.content = buf.getvalue()
            mock_resp.raise_for_status = MagicMock()
            MockSession.return_value.get.return_value = mock_resp

            client = NTSClient()
            result = client.download_artwork("https://example.com/art.jpg", size=120)

            assert result is not None
            assert result.size == (120, 120)
