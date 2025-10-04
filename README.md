Ambilight

This script captures the screen average color and sends it to a TP-Link Kasa smart bulb every few seconds for ambient lighting.

Files
- ambilight.py - main ambilight loop
- requirements.txt - Python dependencies

Usage
1. Install dependencies into your Python environment:

```bash
pip install -r requirements.txt
```

2. Run the ambilight script (optional interval seconds):

```bash
python ambilight.py 5
```

Notes
- The script uses a small downscale capture for speed. Adjust `DOWNSCALE` in `ambilight.py` if you need higher fidelity.
- It stores a discovered bulb IP in `kasa_device_cache.json` to speed up future runs.
