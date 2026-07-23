"""ST7789 display rendering for Pimoroni Pirate Audio.

Renders 240x240 frames using PIL and pushes them to the
ST7789 SPI display. Uses a dark theme with NTS orange accents.
Bundled assets: NTS logo SVG and 16 infinite mixtape icons.
"""

import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

# Asset paths — resolved relative to this file's parent directory
_ASSETS_DIR = Path(__file__).resolve().parent.parent / "assets"
_MIXTAPE_ICONS_DIR = _ASSETS_DIR / "mixtapes"
_LOGO_SVG_PATH = _ASSETS_DIR / "NTS_Radio_logo.svg"

# Display dimensions
WIDTH = 240
HEIGHT = 240

# Theme colors
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)
NTS_ORANGE = (255, 77, 0)
DARK_GRAY = (40, 40, 40)
MID_GRAY = (100, 100, 100)
LIGHT_GRAY = (180, 180, 180)

# Font paths (Raspberry Pi OS)
FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

# Pirate Audio SPI config
SPI_PORT = 0
SPI_CS = 1
SPI_DC = 9
BACKLIGHT_PIN = 13
SPI_SPEED_MHZ = 80


class Display:
    """Manages the ST7789 240x240 SPI display."""

    def __init__(self, brightness: int = 80):
        """Initialize the display.

        Args:
            brightness: Backlight brightness 0-100.
        """
        self._display = None
        self._brightness = brightness
        self._last_frame_hash: Optional[int] = None

        # Load fonts with fallback to default
        try:
            self._font_large = ImageFont.truetype(FONT_BOLD, 18)
            self._font_medium = ImageFont.truetype(FONT_REGULAR, 14)
            self._font_small = ImageFont.truetype(FONT_REGULAR, 12)
            self._font_header = ImageFont.truetype(FONT_BOLD, 16)
        except OSError:
            logger.warning("DejaVu fonts not found, using default")
            self._font_large = ImageFont.load_default()
            self._font_medium = ImageFont.load_default()
            self._font_small = ImageFont.load_default()
            self._font_header = ImageFont.load_default()

        # Load bundled assets
        self._nts_logo = self._load_logo()
        self._mixtape_icons: dict[str, Image.Image] = self._load_mixtape_icons()

        self._init_hardware()

    def _init_hardware(self):
        """Initialize the ST7789 display hardware."""
        try:
            import st7789

            self._display = st7789.ST7789(
                port=SPI_PORT,
                cs=SPI_CS,
                dc=SPI_DC,
                backlight=BACKLIGHT_PIN,
                width=WIDTH,
                height=HEIGHT,
                spi_speed_hz=SPI_SPEED_MHZ * 1000000,
                rotation=90,
                offset_left=0,
                offset_top=0,
            )
            self._display.begin()
            self.set_brightness(self._brightness)
            logger.info("ST7789 display initialized")
        except ImportError:
            logger.warning("st7789 library not available (not on Pi?)")
            self._display = None
        except Exception:
            logger.exception("Failed to initialize display")
            self._display = None

    def _load_logo(self) -> Optional[Image.Image]:
        """Load and rasterize the NTS logo SVG to a white-on-black image."""
        if not _LOGO_SVG_PATH.exists():
            logger.warning("NTS logo not found at %s", _LOGO_SVG_PATH)
            return None
        try:
            import cairosvg
            png_data = cairosvg.svg2png(
                url=str(_LOGO_SVG_PATH), output_width=120, output_height=120,
            )
            import io
            logo = Image.open(io.BytesIO(png_data)).convert("RGBA")
            # The SVG is black paths on white — invert for dark theme:
            # make white pixels black, black pixels white
            r, g, b, a = logo.split()
            from PIL import ImageOps
            r = ImageOps.invert(r)
            g = ImageOps.invert(g)
            b = ImageOps.invert(b)
            logo = Image.merge("RGBA", (r, g, b, a))
            logger.info("NTS logo loaded (cairosvg)")
            return logo
        except ImportError:
            logger.info("cairosvg not available, using PIL SVG fallback")
        except Exception:
            logger.exception("Failed to rasterize logo with cairosvg")

        # Fallback: parse the SVG path manually is too complex,
        # so create a simple text-based logo
        try:
            logo = Image.new("RGBA", (120, 120), (0, 0, 0, 0))
            draw = ImageDraw.Draw(logo)
            font = ImageFont.truetype(FONT_BOLD, 48)
            bbox = draw.textbbox((0, 0), "NTS", font=font)
            tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
            x = (120 - tw) // 2
            y = (120 - th) // 2 - bbox[1]
            draw.text((x, y), "NTS", font=font, fill=WHITE)
            return logo
        except Exception:
            return None

    def _load_mixtape_icons(self) -> dict[str, Image.Image]:
        """Load all bundled mixtape icons, keyed by alias."""
        icons = {}
        if not _MIXTAPE_ICONS_DIR.exists():
            logger.warning("Mixtape icons dir not found at %s", _MIXTAPE_ICONS_DIR)
            return icons
        for path in _MIXTAPE_ICONS_DIR.glob("*.png"):
            alias = path.stem  # e.g. "poolside", "slow-focus"
            try:
                icon = Image.open(path).convert("RGBA")
                # Scale to 120x120 for the artwork area
                icon = icon.resize((120, 120), Image.LANCZOS)
                icons[alias] = icon
                logger.debug("Loaded mixtape icon: %s", alias)
            except Exception:
                logger.warning("Failed to load mixtape icon: %s", path)
        logger.info("Loaded %d mixtape icons", len(icons))
        return icons

    def _get_mixtape_icon(self, mixtape_info: dict) -> Optional[Image.Image]:
        """Look up a mixtape icon by alias, path slug, or title slug."""
        # Try direct alias field
        alias = mixtape_info.get("mixtape_alias", "")
        if alias and alias in self._mixtape_icons:
            return self._mixtape_icons[alias]

        # Try extracting alias from the path field (e.g. "/infinite-mixtapes/poolside")
        path = mixtape_info.get("path", "")
        if path:
            slug = path.rstrip("/").rsplit("/", 1)[-1]
            if slug in self._mixtape_icons:
                return self._mixtape_icons[slug]

        # Try slugifying the title (e.g. "Slow Focus" -> "slow-focus")
        title = mixtape_info.get("title", "")
        if title:
            slug = title.lower().replace(" ", "-").replace("&", "and")
            if slug in self._mixtape_icons:
                return self._mixtape_icons[slug]

        return None

    def set_brightness(self, brightness: int):
        """Set backlight brightness (0-100)."""
        self._brightness = max(0, min(100, brightness))
        if self._display is not None:
            try:
                self._display.set_backlight(self._brightness / 100.0)
            except Exception:
                pass

    def _push_image(self, img: Image.Image):
        """Push a PIL image to the display, skipping if unchanged."""
        frame_hash = hash(img.tobytes())
        if frame_hash == self._last_frame_hash:
            return  # No change, skip update
        self._last_frame_hash = frame_hash

        if self._display is not None:
            try:
                self._display.display(img)
            except Exception:
                logger.exception("Failed to update display")
        else:
            # Debug: save to file when no hardware
            logger.debug("Display update (no hardware)")

    def _new_frame(self) -> tuple[Image.Image, ImageDraw.Draw]:
        """Create a new blank frame."""
        img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
        draw = ImageDraw.Draw(img)
        return img, draw

    def _draw_header(self, draw: ImageDraw.Draw, left_text: str, right_text: str):
        """Draw the header bar (20px tall)."""
        # Background strip
        draw.rectangle([(0, 0), (WIDTH, 22)], fill=DARK_GRAY)
        # Left text
        draw.text((6, 3), left_text, font=self._font_header, fill=WHITE)
        # Right text (right-aligned)
        bbox = draw.textbbox((0, 0), right_text, font=self._font_small)
        rw = bbox[2] - bbox[0]
        draw.text((WIDTH - rw - 6, 5), right_text, font=self._font_small, fill=NTS_ORANGE)

    def _draw_progress_bar(
        self, draw: ImageDraw.Draw, y: int, progress: float, time_text: str
    ):
        """Draw a progress bar with time remaining text.

        Args:
            draw: ImageDraw instance.
            y: Y position for the bar.
            progress: 0.0 to 1.0 progress value.
            time_text: Text to show after the bar (e.g. "45:12").
        """
        bar_x = 10
        bar_w = 170
        bar_h = 8

        # Background
        draw.rectangle(
            [(bar_x, y), (bar_x + bar_w, y + bar_h)],
            fill=DARK_GRAY,
        )
        # Fill
        fill_w = int(bar_w * max(0, min(1, progress)))
        if fill_w > 0:
            draw.rectangle(
                [(bar_x, y), (bar_x + fill_w, y + bar_h)],
                fill=NTS_ORANGE,
            )
        # Time text
        draw.text(
            (bar_x + bar_w + 8, y - 2),
            time_text,
            font=self._font_small,
            fill=LIGHT_GRAY,
        )

    def _draw_button_hints(self, draw: ImageDraw.Draw, hints: list[str]):
        """Draw button hint text at the bottom of the screen.

        Args:
            hints: List of 4 strings for buttons [A, B, X, Y].
        """
        y = HEIGHT - 16
        draw.rectangle([(0, y - 2), (WIDTH, HEIGHT)], fill=DARK_GRAY)

        labels = hints[:4]
        spacing = WIDTH // 4
        for i, label in enumerate(labels):
            x = i * spacing + 4
            draw.text((x, y), label, font=self._font_small, fill=MID_GRAY)

    def _truncate_text(self, draw: ImageDraw.Draw, text: str, font, max_width: int) -> str:
        """Truncate text with ellipsis if it exceeds max_width."""
        bbox = draw.textbbox((0, 0), text, font=font)
        if (bbox[2] - bbox[0]) <= max_width:
            return text
        while len(text) > 1:
            text = text[:-1]
            test = text + "..."
            bbox = draw.textbbox((0, 0), test, font=font)
            if (bbox[2] - bbox[0]) <= max_width:
                return test
        return text

    def render_live(
        self,
        channel_info: dict,
        is_playing: bool,
        artwork: Optional[Image.Image] = None,
    ):
        """Render the live channel screen.

        Args:
            channel_info: Dict with channel_name, title, artist,
                         start_timestamp, end_timestamp.
            is_playing: Whether audio is currently playing.
            artwork: Optional PIL Image for show artwork (120x120).
        """
        img, draw = self._new_frame()

        # Header
        status = "> LIVE" if is_playing else "|| LIVE"
        self._draw_header(draw, channel_info.get("channel_name", "NTS"), status)

        # Artwork area (centered, below header)
        artwork_size = 120
        artwork_x = (WIDTH - artwork_size) // 2
        artwork_y = 28

        if artwork is not None:
            img.paste(artwork, (artwork_x, artwork_y))
        elif self._nts_logo is not None:
            # Use bundled NTS logo as placeholder
            img.paste(self._nts_logo, (artwork_x, artwork_y), self._nts_logo)
        else:
            # Last-resort placeholder
            draw.rectangle(
                [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                fill=DARK_GRAY,
                outline=MID_GRAY,
            )
            draw.text(
                (artwork_x + 30, artwork_y + 50),
                "NTS",
                font=self._font_large,
                fill=MID_GRAY,
            )

        # Show title
        title = channel_info.get("title", "Unknown Show")
        title = self._truncate_text(draw, title, self._font_large, WIDTH - 20)
        draw.text((10, 155), title, font=self._font_large, fill=WHITE)

        # Artist / description
        artist = channel_info.get("artist", "")
        if artist:
            artist = self._truncate_text(draw, artist, self._font_medium, WIDTH - 20)
            draw.text((10, 178), artist, font=self._font_medium, fill=LIGHT_GRAY)

        # Progress bar
        progress, time_remaining = self._calc_progress(
            channel_info.get("start_timestamp"),
            channel_info.get("end_timestamp"),
        )
        self._draw_progress_bar(draw, 200, progress, time_remaining)

        # Button hints
        self._draw_button_hints(draw, ["A<", "B>", "X ||", "Y ="])

        self._push_image(img)

    def render_mixtape(
        self,
        mixtape_info: dict,
        is_playing: bool,
        artwork: Optional[Image.Image] = None,
    ):
        """Render the mixtape screen.

        Args:
            mixtape_info: Dict with title, subtitle, description.
            is_playing: Whether audio is currently playing.
            artwork: Optional PIL Image for mixtape artwork.
        """
        img, draw = self._new_frame()

        # Header
        status = "> MIX" if is_playing else "|| MIX"
        self._draw_header(draw, "MIXTAPE", status)

        # Artwork
        artwork_size = 120
        artwork_x = (WIDTH - artwork_size) // 2
        artwork_y = 30

        if artwork is not None:
            img.paste(artwork, (artwork_x, artwork_y))
        else:
            # Try bundled mixtape icon
            icon = self._get_mixtape_icon(mixtape_info)
            if icon is not None:
                img.paste(icon, (artwork_x, artwork_y), icon)
            else:
                # Fallback placeholder
                draw.rectangle(
                    [(artwork_x, artwork_y), (artwork_x + artwork_size, artwork_y + artwork_size)],
                    fill=DARK_GRAY,
                    outline=NTS_ORANGE,
                )
                label = mixtape_info.get("mixtape_alias", mixtape_info.get("title", "MIX"))
                draw.text(
                    (artwork_x + 10, artwork_y + 50),
                    label[:10],
                    font=self._font_medium,
                    fill=NTS_ORANGE,
                )

        # Title
        title = mixtape_info.get("title", "Mixtape")
        title = self._truncate_text(draw, title, self._font_large, WIDTH - 20)
        draw.text((10, 158), title, font=self._font_large, fill=WHITE)

        # Subtitle
        subtitle = mixtape_info.get("subtitle", "")
        if subtitle:
            subtitle = self._truncate_text(draw, subtitle, self._font_medium, WIDTH - 20)
            draw.text((10, 180), subtitle, font=self._font_medium, fill=LIGHT_GRAY)

        # Description (one line)
        desc = mixtape_info.get("description", "")
        if desc:
            desc = self._truncate_text(draw, desc, self._font_small, WIDTH - 20)
            draw.text((10, 200), desc, font=self._font_small, fill=MID_GRAY)

        # Button hints
        self._draw_button_hints(draw, ["A<", "B>", "X ||", "Y ="])

        self._push_image(img)

    def render_menu(self, items: list[str], selected: int):
        """Render a menu overlay.

        Args:
            items: List of menu item labels.
            selected: Index of the currently selected item.
        """
        img, draw = self._new_frame()

        # Header
        self._draw_header(draw, "MENU", "")

        # Menu items
        y_start = 40
        item_height = 36

        for i, item in enumerate(items):
            y = y_start + i * item_height

            if i == selected:
                # Selected item: orange highlight
                draw.rectangle(
                    [(4, y), (WIDTH - 4, y + item_height - 4)],
                    fill=NTS_ORANGE,
                )
                draw.text((16, y + 8), item, font=self._font_large, fill=WHITE)
            else:
                draw.rectangle(
                    [(4, y), (WIDTH - 4, y + item_height - 4)],
                    fill=DARK_GRAY,
                )
                draw.text((16, y + 8), item, font=self._font_large, fill=LIGHT_GRAY)

        # Button hints
        self._draw_button_hints(draw, ["A ^", "B v", "X Sel", "Y Back"])

        self._push_image(img)

    def render_message(self, title: str, message: str):
        """Render a simple message screen (for errors, loading, etc.)."""
        img, draw = self._new_frame()

        self._draw_header(draw, title, "")
        draw.text((20, 100), message, font=self._font_medium, fill=LIGHT_GRAY)

        self._push_image(img)

    def clear(self):
        """Clear the display to black."""
        img = Image.new("RGB", (WIDTH, HEIGHT), BLACK)
        self._last_frame_hash = None
        if self._display is not None:
            try:
                self._display.display(img)
            except Exception:
                pass

    def _calc_progress(
        self, start_ts: Optional[str], end_ts: Optional[str]
    ) -> tuple[float, str]:
        """Calculate progress and time remaining from timestamps.

        Returns (progress_fraction, time_remaining_string).
        """
        if not start_ts or not end_ts:
            return 0.0, "--:--"

        try:
            # Parse ISO timestamps
            start = datetime.fromisoformat(start_ts.replace("Z", "+00:00"))
            end = datetime.fromisoformat(end_ts.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)

            total = (end - start).total_seconds()
            elapsed = (now - start).total_seconds()

            if total <= 0:
                return 0.0, "--:--"

            progress = max(0.0, min(1.0, elapsed / total))
            remaining = max(0, int(total - elapsed))
            mins = remaining // 60
            secs = remaining % 60

            return progress, f"{mins}:{secs:02d}"
        except (ValueError, TypeError):
            return 0.0, "--:--"

    def shutdown(self):
        """Clean shutdown of the display."""
        self.clear()
        self.set_brightness(0)
        logger.info("Display shut down")
