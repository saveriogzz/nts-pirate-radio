# NTS Radio for Raspberry Pi

Stream NTS Radio (live channels + infinite mixtapes) on a Raspberry Pi with a Pimoroni Pirate Audio Line-out HAT. Deployed via Balena Cloud.

[![balena deploy button](https://www.balena.io/deploy.svg)](https://dashboard.balena-cloud.com/deploy?repoUrl=https://github.com/saveriogzz/nts-balena)

## Hardware

- Raspberry Pi with a 40-pin header (Zero 2W recommended; Pi 2/3/4/5 also supported)
- [Pimoroni Pirate Audio Line-out](https://shop.pimoroni.com/products/pirate-audio-line-out) — ST7789 240x240 display, 4 buttons, I2S DAC

## Deploy

### One-click (recommended)

Click the **Deploy with balena** button above. It creates a fleet with everything preconfigured from `balena.yml` — hardware config (SPI, I2S DAC overlay, GPU memory) and default environment variables. No dashboard setup needed: add a device, flash the image, and the radio starts playing NTS 1 on boot.

### Manual (balena CLI)

Create a fleet on [Balena Cloud](https://dashboard.balena-cloud.com) (device type **Raspberry Pi Zero 2 W** or any supported model), then:

```bash
balena login
balena push <fleet-name>
```

### Environment variables

These are set as fleet defaults in `balena.yml` and can be overridden per-device in the dashboard:

| Variable | Default | Description |
|----------|---------|-------------|
| `NTS_DEFAULT_CHANNEL` | `1` | Start on channel 1 or 2 |
| `NTS_DISPLAY_BRIGHTNESS` | `80` | Backlight brightness 0-100 |
| `NTS_BUTTON_DEBOUNCE_MS` | `200` | Button debounce in ms |

## Controls

| Button | Normal | Menu |
|--------|-------------|-----------|
| A (top-left) | Prev channel | Scroll up |
| B (bottom-left) | Next channel | Scroll down |
| X (top-right) | Play/Pause | Select |
| Y (bottom-right) | Open menu | Back |

## Screens

- **Live** — NTS 1 / NTS 2 with show artwork, title, and progress bar
- **Mixtapes** — Browse and play all NTS infinite mixtapes
- **Menu** — Switch between modes, adjust brightness

## Project structure

```
nts-radio/
├── nts/
│   ├── api.py         # NTS API client (live, mixtapes)
│   ├── player.py      # mpv wrapper with IPC socket control
│   ├── display.py     # ST7789 240x240 display rendering
│   ├── buttons.py     # GPIO button handler with debounce
│   └── app.py         # Main app state machine
├── Dockerfile.template
├── docker-compose.yml
├── balena.yml
└── requirements.txt
```

## Local development (without Balena)

For testing on a Pi directly, the `install.sh` script and `nts-radio.service` are also included as an alternative to the Balena deployment.
