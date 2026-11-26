# AWR1843 live point cloud

## Files
- `radar_server.py`: configures the radar, reads and parses the point data, and streams it over WebSocket
- `index.html`: 3D viewer. Open it in Chrome or Edge.
- `requirements.txt`: Python packages
- Your radar config file (`profile.cfg`). It is not included. See step 4.

## 1. Set the switches (power off first)
For USB mode on the AWR1843AoP EVM (TI user guide, Table 2-8, "Modular (USB)" row):
S1.1 OFF, S1.3 OFF, S1.4 OFF, S3 OFF. Then press the reset switch.

Close the TI visualizer before running this script. Only one program can use each COM port.

## 2. Install the Python packages
    pip install -r requirements.txt

## 3. Find your COM ports
Open Device Manager, then Ports (COM & LPT). The enhanced COM port is the CLI port (CLI_PORT). The standard COM port is the data port (DATA_PORT).

## 4. Find your config file
The config has to match your board and firmware, so copy it from your own TI install. In PowerShell, run:

    Get-ChildItem C:\ti -Recurse -Filter *.cfg | Select-String -Pattern "sensorStart" -List | Select-Object Path

If TI installed somewhere other than `C:\ti`, change the path. Choose the people-detection config (the name often includes "people" or "profile") and copy it into this folder as `profile.cfg`. If the Demo Visualizer has a save option for its current configuration, that gives you the exact file it's using.

## 5. Edit the settings
Open `radar_server.py` and set `CLI_PORT`, `DATA_PORT`, and `CFG_FILE`.

## 6. Run the server
    python radar_server.py

You should see "Config sent, no errors." followed by "WebSocket running", then frame counts as points arrive.

## 7. View it
Double-click `index.html`. The status line should read "connected". Walk in front of the radar.

## Tuning
- Trail length: `FADE` in `index.html`. Closer to 1 means longer trails.
- Colors: `velocityColor()` in `index.html`. Swap the two branches if approaching objects show as blue.
- Point size and ring buffer: `POINT_SIZE` and `MAX_POINTS` in `index.html`.

## Troubleshooting
- **Could not open port:** wrong COM number, or the TI visualizer is still open.
- **"not recognized" config errors:** the cfg file doesn't match your firmware. Use the cfg from the same SDK or visualizer.
- **Status says "can't connect":** `radar_server.py` isn't running, or the port isn't 8765.
- **No points:** check that the switches are in USB mode, press reset, then move in front of the radar.
