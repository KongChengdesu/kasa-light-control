# Kasa Light Control (Kasa bulb helpers)

This repository provides small scripts and Windows wrappers to control TP-Link Kasa smart bulbs from the command line and to run an "ambilight" style program that samples the screen color and updates a Kasa bulb to match.

This README documents all available functionality, command-line arguments, and examples for the included batch/vbs wrappers.

## Contents

- `main.py` - simple CLI to control a Kasa bulb (toggle, brightness, color, increase, decrease).
- `ambilight.py` - continuously sample the screen and send averaged color/brightness to the bulb.
- `*.bat` / `*.vbs` - convenience wrappers for Windows to call the Python scripts with common arguments.
- `requirements.txt` - required Python packages.
- `kasa_device_cache.json` - runtime cache file (created by the scripts) that stores the last discovered device IP.

## Quick setup

1. Install Python 3.8+ and ensure `python` (or `py`) is available in your PATH.
2. (Recommended) Create and activate a virtual environment.
3. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

Optional GPU/acceleration packages (improve ambilight averaging performance):
- `cupy` (for CuPy GPU arrays) or `torch` with CUDA available, though these are optional fallbacks in `ambilight.py`.

Note: On Windows you may prefer `py -3` to choose a specific Python installation; the bundled .bat files already try to prefer `py` when present.

## Device discovery and caching

Both `main.py` and `ambilight.py` attempt to reuse a cached device IP saved in `kasa_device_cache.json`. If the cached IP is invalid they run a local network discovery and will update the cache with the discovered device's IP.

If you move the bulb to another network or the IP changes, delete `kasa_device_cache.json` or let the script rediscover automatically (it falls back when the cached IP fails).

## `main.py` — CLI usage

Usage:

```bash
python main.py <command> [arguments...]
```

Available commands:

- toggle
	- Toggle the bulb on/off.
	- Example: `python main.py toggle`

- increase
	- Increase brightness by 10 (clamped to 100). Sends the change with a short transition.
	- Example: `python main.py increase`

- decrease
	- Decrease brightness by 10 (clamped to 0).
	- Example: `python main.py decrease`

- brightness \<value\>
	- Set an explicit brightness value (0-100).
	- Example: `python main.py brightness 65`

- color \<h\> \<s\> \<v\>
	- Set the bulb color using Kasa HSV integers: hue 0–360, saturation 0–100, value/brightness 0–100.
	- Example: `python main.py color 0 100 51` (red-ish)

Notes about `main.py` implementation
- The CLI operates by discovering (or reusing cached) Kasa bulbs and using the `Light` module for color/brightness changes.
- The `color` command accepts HSV integers (not hex or RGB) because the project uses `module.set_hsv(h, s, v)` under the hood. Several `.bat` wrappers provide commonly used colors.

If you prefer hex or RGB input you can easily convert and call the HSV form (examples below).

## `ambilight.py` — usage and options

Run directly:

```bash
python ambilight.py [interval_seconds]
```

- interval_seconds (optional, float) — seconds between samples. Default is 5.

What it does:

- Captures the primary screen using `mss` and downsamples (configured by `DOWNSCALE` in the script) to compute an average color.
- Converts average RGB to Kasa HSV and scales brightness down (configurable via `BRIGHTNESS_SCALE` and `MIN_BRIGHTNESS`) so the bulb is dimmer than the screen.
- Sends HSV updates to the bulb when the change in H, S, or V exceeds `MIN_UPDATE_DELTA`. This avoids flooding the bulb with tiny updates.
- Attempts to use GPU-backed averaging if `cupy` or `torch` with CUDA are available; otherwise falls back to NumPy.

Example:

```bash
python ambilight.py 2.5
```

This runs the ambilight loop sampling every 2.5 seconds.

Windows wrapper: `ambilight.bat` accepts the same optional interval and prefers `py -3` if available.

## Included helper wrappers

Several `.bat` files are included for one-click actions in Windows. They call `main.py` with common arguments. Examples:

- `toggle.bat` — toggles the bulb on/off (calls `python main.py toggle`).
- `brightness100.bat` — sets brightness to 100 (calls `python main.py brightness 100`).
- `red.bat`, `green.bat`, `blue.bat`, `yellow.bat`, `purple.bat`, `orange.bat`, `cyan.bat` — set preset HSV color values; they call `python main.py color <h> <s> <v>` with values chosen by the author.

Also `.vbs` wrappers exist for launching scripts without a console window; they mirror the same calls as the .bat files.

## Examples and conversions

Convert hex or RGB to Kasa HSV (manual example using Python):

```python
import colorsys

def rgb_to_hsv_kasa(r, g, b):
		rf, gf, bf = r/255.0, g/255.0, b/255.0
		h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)
		return int(h*360), int(s*100), int(v*100)

# Example: #FF5733
print(rgb_to_hsv_kasa(255, 87, 51))  # -> (something like 14, 80, 100)

# Then call the script:
# python main.py color <h> <s> <v>
```

## Troubleshooting

- No bulb found: Ensure your bulb and the machine running the scripts are on the same local network. The scripts use a broadcast discovery target; if your network uses a different subnet, you may need to edit the `Discover.discover(target=...)` call in the scripts to match (look for the `target=` argument in the file).
- Cached IP issues: Delete `kasa_device_cache.json` and re-run to force discovery.
- Permissions: Screen capture on some systems requires elevated permissions or particular Windows privacy settings. If `ambilight.py` fails to capture the screen, try running from an elevated prompt or check Windows privacy settings for screen capture.
- Slow updates: Reduce `DOWNSCALE` in `ambilight.py` or increase interval. Optionally install `cupy` or use a machine with CUDA+PyTorch for faster GPU averaging.

## Development notes / how it works

- The `kasa` library is used to interact with TP-Link Kasa devices. Discovery finds devices on the LAN and returns `kasa.Device` instances.
- `ambilight.py` uses `mss` + Pillow to capture and downscale the screen; it computes an average color and sends it via `module.set_hsv(...)` to the bulb's `Light` module.
- Both scripts attempt to reconnect automatically when commands fail and write informational logs to the console.

## Safety and behavior

- The scripts only interact with devices discovered on the local network and are read/write operations to your owned devices. There is no cloud access by design — everything runs locally.