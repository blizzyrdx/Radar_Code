import serial, time

cli = serial.Serial("COM5", 115200, timeout=0.5)
time.sleep(0.5)

def send(line):
    cli.write((line + "\n").encode())
    time.sleep(0.2)
    reply = cli.read(cli.in_waiting or 1).decode(errors="ignore").strip()
    print(f"{line} -> {reply.splitlines()[-1] if reply else '(no reply)'}")

commands = [
    "sensorStop",
    "cfarCfg -1 0 2 8 4 3 0 25.0 1",    # higher threshold, peak grouping on (range)
    "cfarCfg -1 1 0 4 2 3 1 25.0 1",    # same for Doppler
    "clutterRemoval -1 1",              # remove stationary reflections (walls, floor)
    "aoaFovCfg -1 -45 45 -30 30",       # narrower angle window
    "cfarFovCfg -1 0 0.5 8.64",         # ignore returns closer than 0.5 m
    "sensorStart",
]
for c in commands:
    send(c)

cli.close()
print("Tuning sent.")