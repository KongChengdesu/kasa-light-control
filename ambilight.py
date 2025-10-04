import asyncio
import os
import json
import colorsys
import time
from datetime import datetime
import logging
from kasa import Discover
import kasa

# Screen capture imports
from PIL import Image
import mss
import numpy as np

# Try GPU libraries for averaging: prefer CuPy, then PyTorch (CUDA), else fall back to NumPy
GPU_BACKEND = None
try:
    import cupy as cp
    GPU_BACKEND = "cupy"
except Exception:
    try:
        import torch
        if torch.cuda.is_available():
            GPU_BACKEND = "torch"
        else:
            GPU_BACKEND = None
    except Exception:
        GPU_BACKEND = None

CACHE_FILE = "kasa_device_cache.json"

# Configuration
INTERVAL_SECONDS = 5
MIN_UPDATE_DELTA = 5  # minimum change in H/S/V to send update
TRANSITION_MS = 500  # transition time sent to the bulb
DOWNSCALE = (160, 90)  # capture downscale for speed (width, height)
# Brightness control: scale the screen value (0-100) down so the bulb is dimmer than the screen
BRIGHTNESS_SCALE = 0.55  # fraction of screen value to use for bulb brightness (0..1)
MIN_BRIGHTNESS = 6       # minimum brightness to send to bulb (0..100)


def load_cached_ip():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as file:
            return json.load(file).get("ip")
    return None


def save_cached_ip(ip):
    with open(CACHE_FILE, "w") as file:
        json.dump({"ip": ip}, file)


# configure simple logging with timestamps
logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
    level=logging.INFO,
)


async def get_light():
    """Discover or reuse a cached Kasa bulb device and return it (with Light module)."""
    ip = load_cached_ip()
    light = None

    if ip:
        try:
            light = await kasa.Device.connect(host=ip)
            await light.update()
            return light
        except Exception:
            logging.warning("Cached IP is invalid, rediscovering...")

    logging.info("Discovering Kasa devices on the network...")
    devices = await Discover.discover(target="192.168.3.255")
    for dev in devices.values():
        try:
            await dev.update()
        except Exception:
            continue
        # device_type check is best effort; fallback to checking modules
        if getattr(dev, "device_type", None) == kasa.DeviceType.Bulb or "Light" in dev.modules:
            save_cached_ip(dev.host)
            return dev

    logging.warning("No Kasa lightbulb found.")
    return None


def average_screen_color():
    """Capture the screen, downscale and return the average (R, G, B) tuple (0-255)."""
    with mss.mss() as sct:
        monitor = sct.monitors[0]
        # capture full screen then convert to PIL image and downscale
        sct_img = sct.grab(monitor)
        img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
        img = img.resize(DOWNSCALE, Image.Resampling.BILINEAR)
        # Convert to average by resizing to 1x1
        tiny = img.resize((1, 1), Image.Resampling.BILINEAR)
        r, g, b = tiny.getpixel((0, 0))
        return (r, g, b)


def rgb_to_hsv_kasa(r, g, b):
    """Convert 0-255 RGB to Kasa HSV integers: hue 0-360, sat 0-100, value 0-100."""
    rf, gf, bf = r / 255.0, g / 255.0, b / 255.0
    h, s, v = colorsys.rgb_to_hsv(rf, gf, bf)  # h in 0..1
    return (int(h * 360), int(s * 100), int(v * 100))


async def run_ambilight(interval=INTERVAL_SECONDS):
    logging.info("Starting ambilight loop. Press Ctrl+C to stop.")
    # Log which averaging backend will be used
    if GPU_BACKEND == "cupy":
        logging.info("Using CuPy GPU backend for averaging")
    elif GPU_BACKEND == "torch":
        logging.info("Using PyTorch CUDA backend for averaging")
    else:
        logging.info("Using NumPy (CPU) backend for averaging")

    def get_average_rgb():
        """Capture the screen with mss and compute average RGB using GPU backend if available."""
        with mss.mss() as sct:
            monitor = sct.monitors[0]
            sct_img = sct.grab(monitor)
            img = Image.frombytes("RGB", sct_img.size, sct_img.rgb)
            # downscale for speed
            img = img.resize(DOWNSCALE, Image.Resampling.BILINEAR)
            arr = np.array(img)

        # arr shape: (h, w, 3)
        if GPU_BACKEND == "cupy":
            try:
                garr = cp.asarray(arr)
                # compute mean across height and width for each channel
                means = cp.mean(cp.mean(garr, axis=0), axis=0)
                means = cp.asnumpy(means)
                return (int(means[0]), int(means[1]), int(means[2]))
            except Exception:
                logging.exception("CuPy averaging failed, falling back to NumPy")
                GPU_BACKEND_LOCAL = None
        elif GPU_BACKEND == "torch":
            try:
                t = torch.from_numpy(arr).float().cuda()
                means = t.mean(dim=0).mean(dim=0)
                means = means.cpu().numpy()
                return (int(means[0]), int(means[1]), int(means[2]))
            except Exception:
                logging.exception("PyTorch averaging failed, falling back to NumPy")

        # Fallback to NumPy
        means = arr.mean(axis=0).mean(axis=0)
        return (int(means[0]), int(means[1]), int(means[2]))

    light = await get_light()
    if not light:
        return

    module = light.modules.get("Light")
    if not module:
        logging.warning("Found device does not expose Light module.")
        return

    prev_hsv = None
    last_heartbeat = time.time()
    try:
        while True:
            try:
                # Heartbeat log every 60s so we know the loop is alive
                if time.time() - last_heartbeat > 60:
                    logging.info("ambilight heartbeat: running")
                    last_heartbeat = time.time()

                # Use GPU-backed averaging when available (get_average_rgb does capture)
                rgb = await asyncio.to_thread(get_average_rgb)

                h, s, raw_v = rgb_to_hsv_kasa(*rgb)
                # scale down brightness for ambience (use lower brightness than screen)
                scaled_v = max(MIN_BRIGHTNESS, int(raw_v * BRIGHTNESS_SCALE))

                should_update = False
                if prev_hsv is None:
                    should_update = True
                else:
                    dh = abs(h - prev_hsv[0])
                    ds = abs(s - prev_hsv[1])
                    dv = abs(scaled_v - prev_hsv[2])
                    if dh >= MIN_UPDATE_DELTA or ds >= MIN_UPDATE_DELTA or dv >= MIN_UPDATE_DELTA:
                        should_update = True

                if should_update:
                    try:
                        # send HSV to the bulb - log hex color and timestamp
                        hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
                        now = datetime.now().isoformat(sep=' ', timespec='seconds')
                        logging.info(
                            f"Sending color {hex_color} HSV=({h},{s},{scaled_v}) at {now} (scaled from {raw_v}%)"
                        )
                        # send HSV with scaled brightness
                        await module.set_hsv(h, s, scaled_v, transition=TRANSITION_MS)
                        prev_hsv = (h, s, scaled_v)
                        logging.info(f"Sent color {hex_color} successfully at brightness {scaled_v}%")
                    except Exception as e:
                        logging.error("Error sending color to bulb: %s", e)
                        # try to reconnect once
                        light = await get_light()
                        if not light:
                            logging.error("Could not reconnect to light, exiting loop")
                            return
                        module = light.modules.get("Light")

                await asyncio.sleep(interval)
            except Exception:
                # Catch unexpected errors in the iteration so the loop keeps running
                logging.exception("Unhandled exception in ambilight loop iteration; continuing")
                # small delay to avoid hot loop on persistent errors
                await asyncio.sleep(1)
    except asyncio.CancelledError:
        pass
    except KeyboardInterrupt:
        logging.info("Interrupted by user, exiting.")
    finally:
        logging.info("ambilight loop exiting")


if __name__ == "__main__":
    # Allow optional interval arg
    import sys
    interval_arg = INTERVAL_SECONDS
    if len(sys.argv) > 1:
        try:
            interval_arg = float(sys.argv[1])
        except Exception:
            print("Invalid interval arg, using default", INTERVAL_SECONDS)

    asyncio.run(run_ambilight(interval=interval_arg))
