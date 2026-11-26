
import serial
import time
from pathlib import Path

CLI_PORT = "/dev/ttyUSB0"
CLI_BAUD = 115200
CFG_PATH = Path.home() / "radar.cfg"

with serial.Serial(CLI_PORT, CLI_BAUD, timeout=0.2) as cli:
    time.sleep(0.5)

    commands = [
        line.strip()
        for line in CFG_PATH.read_text().splitlines()
        if line.strip() and not line.strip().startswith("%")
    ]

    for i, command in enumerate(commands, 1):
        cli.reset_input_buffer()

        print(f"[{i}/{len(commands)}] {command}")

        cli.write((command + "\n").encode())
        cli.flush()

        deadline = time.monotonic() + 10
        response = b""

        while time.monotonic() < deadline:
            response += cli.read(cli.in_waiting or 1)

            if b"mmwDemo:/>" in response:
                break

        text = response.decode(errors="replace")
        print(text)

        already_stopped = (
            command == "sensorStop"
            and "Sensor is already stopped" in text
        )

        if already_stopped:
            continue

        if "Error" in text or "Ignored" in text:
            raise SystemExit(f"Command rejected: {command}")

        if "Done" not in text:
            raise SystemExit(f"No confirmation: {command}")

        time.sleep(0.1)

print("\nRadar started successfully.")
