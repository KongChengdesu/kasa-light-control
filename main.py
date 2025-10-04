import asyncio
import sys
import json
import os
import colorsys
from kasa import Discover
import kasa

CACHE_FILE = "kasa_device_cache.json"

def print_usage():
    print("Usage: python script.py <command> [color_hex]")
    print("Commands:")
    print("  toggle           - Toggle light on/off")
    print("  increase        - Increase brightness")
    print("  decrease        - Decrease brightness")
    print("  color <hexcode> - Change color (e.g., #FF5733)")

def load_cached_ip():
    if os.path.exists(CACHE_FILE):
        with open(CACHE_FILE, "r") as file:
            return json.load(file).get("ip")
    return None

def save_cached_ip(ip):
    with open(CACHE_FILE, "w") as file:
        json.dump({"ip": ip}, file)

async def get_light():

    ip = load_cached_ip()
    light = None

    if ip:
        try:
            light = await kasa.Device.connect(host=ip)
            await light.update()
            return light
        except Exception:
            print("Cached IP is invalid, rediscovering...")

    devices = await Discover.discover(target="192.168.1.255")
    for dev in devices.values():
        await dev.update()
        if dev.device_type == kasa.DeviceType.Bulb:
            save_cached_ip(dev.host)
            return dev
    
    print("No Kasa lightbulb found.")
    return None

async def control_light(command, hsv_values=None):
    
    light = await get_light()
    if not light:
        return
    
    module = light.modules["Light"]

    if command == "toggle":
        await light.set_state(not light.is_on)
    elif command == "increase":
        await module.set_brightness(min(100, module.brightness + 10), transition=100)
    elif command == "decrease":
        await module.set_brightness(max(0, module.brightness - 10), transition=100)
    elif command == "brightness" and parameters:
        brightness = int(parameters[0])
        await module.set_brightness(brightness, transition=100)
    elif command == "color" and parameters:
        await module.set_hsv(int(parameters[0]), int(parameters[1]), int(parameters[2]), transition=100)
    else:
        print_usage()
        return
    
    print("Command executed successfully.")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print_usage()
        sys.exit(1)

    command = sys.argv[1]
    parameters = sys.argv[2:] if len(sys.argv) > 2 else None
    asyncio.run(control_light(command, parameters))
