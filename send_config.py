import serial, time, os

CFG = os.path.join(os.path.expanduser("~"), "Desktop", "Radar",
    "mmwave_sdk_03_06_02_00-LTS", "packages", "ti", "demo", "xwr18xx", "mmw",
    "profiles", "profile_2d_aop.cfg")

cli = serial.Serial("COM5", 115200, timeout=0.5)
time.sleep(0.5)

def send(line):
    cli.write((line + "\n").encode())
    time.sleep(0.15)
    reply = cli.read(cli.in_waiting or 1).decode(errors="ignore").strip()
    print(f"{line} -> {reply.splitlines()[-1] if reply else '(no reply)'}")

send("sensorStop")
for raw in open(CFG):
    line = raw.strip()
    if not line or line.startswith("%"):
        continue
    send(line)
send("sensorStart")

cli.close()
print("Finished sending config.")