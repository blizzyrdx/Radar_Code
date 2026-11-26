import serial, time

cli = serial.Serial("COM5", 115200, timeout=0.5)
time.sleep(0.5)

def send(line):
    cli.write((line + "\n").encode())
    time.sleep(0.2)
    reply = cli.read(cli.in_waiting or 1).decode(errors="ignore").strip()
    print(f"{line} -> {reply.splitlines()[-1] if reply else '(no reply)'}")

for c in [
    "sensorStop",
    "clutterRemoval -1 0",
    "cfarCfg -1 0 2 8 4 3 0 15.0 0",
    "cfarCfg -1 1 0 4 2 3 1 15.0 0",
    "aoaFovCfg -1 -90 90 -90 90",
    "cfarFovCfg -1 0 0.25 8.64",
    "cfarFovCfg -1 1 -10.59 10.59",
    "sensorStart",
]:
    send(c)

cli.close()
print("Original settings restored.")