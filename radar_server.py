"""
radar_server.py  (v3: noise filtering + object detection)

Configures the AWR1843 over its CLI port, reads the point cloud from the data
port, cleans it up (range/height/SNR gates and a persistence filter), groups the
remaining points into objects, and streams everything to index.html over WebSocket.

Usage:
    1. Put your radar config file next to this script.
    2. Check the settings below.
    3. python radar_server.py
    4. Open index.html in your browser.
"""
import asyncio
import json
import math
import struct
import threading
import time
from collections import deque

import serial
import websockets

# ----- PORTS -----
CLI_PORT = "COM5"          # enhanced COM port (configuration commands)
DATA_PORT = "COM4"         # standard COM port (point data stream)
CFG_FILE = "profile.cfg"   # radar config file copied from your TI install
WS_HOST = "localhost"
WS_PORT = 8765
PRINT_EVERY = 20           # print a status line every N frames

# ----- NOISE FILTERS (tune these) -----
MIN_RANGE = 0.3            # m. Drops leakage right at the antenna.
MAX_RANGE = 6.0            # m. Ignore anything farther than this.
MAX_SIDE = 4.0             # m. Ignore points farther than this to the left or right.
MIN_HEIGHT = -1.5          # m below the radar.
MAX_HEIGHT = 2.0           # m above the radar.
MIN_SNR_DB = 10.0          # Only applies if the radar sends SNR side info.
PERSIST_FRAMES = 3         # How many past frames the persistence filter looks at.
PERSIST_MIN_HITS = 1       # A point needs a nearby point in this many past frames. 0 = off.
VOXEL = 0.25               # m. Grid size for the persistence check.

# ----- OBJECT GROUPING -----
CLUSTER_EPS = 0.4          # m. Points closer than this belong to the same object.
CLUSTER_MIN_PTS = 3        # Groups smaller than this are not counted as objects.

MAGIC = bytes([2, 1, 4, 3, 6, 5, 8, 7])
HEADER_LEN = 40
TLV_DETECTED_POINTS = 1
TLV_SIDE_INFO = 7          # per-point SNR and noise, in 0.1 dB steps

lock = threading.Lock()
latest_payload = {"raw": 0, "points": [], "clusters": []}
latest_frame_id = 0
parse_stats = {"layout": None, "bad": 0, "bad_shown": 0}


def send_config():
    """Send each line of the .cfg file to the radar's CLI port."""
    cli = serial.Serial(CLI_PORT, 115200, timeout=0.1)
    errors = 0
    with open(CFG_FILE) as f:
        for raw in f:
            line = raw.strip()
            if not line or line.startswith("%"):
                continue
            cli.write((line + "\n").encode())
            out, t0 = b"", time.time()
            while time.time() - t0 < 1.5 and b"mmwDemo:/>" not in out:
                out += cli.read(256)
            text = out.decode(errors="ignore")
            if "not recognized" in text or "rror" in text:
                errors += 1
                print(f"CONFIG ERROR on line: {line}\n{text}")
    cli.close()
    if errors:
        print(f"Config finished with {errors} error(s). Check that the cfg matches your firmware.")
    else:
        print("Config sent, no errors.")


# ---------------------------------------------------------------- parsing

def _walk_tlvs(buf, start, end, num_tlvs, length_includes_header):
    """Walk the TLV chain. Returns [(type, body_offset, body_len), ...] only if
    the chain ends exactly at `end`; otherwise None."""
    off, out = start, []
    for _ in range(num_tlvs):
        if off + 8 > end:
            return None
        t, l = struct.unpack_from("<II", buf, off)
        size = l if length_includes_header else 8 + l
        if size < 8 or off + size > end:
            return None
        out.append((t, off + 8, size - 8))
        off += size
    return out if off == end else None


def extract_frames(buf):
    """Pull every complete frame out of buf.
    Returns (frames, leftover). Each frame is (frame_number, points, snrs) where
    points = [(x, y, z, velocity), ...] and snrs is a list of dB values or None."""
    frames = []
    while True:
        i = buf.find(MAGIC)
        if i < 0 or len(buf) - i < HEADER_LEN:
            break
        _, _, total_len, _, frame_no, _, _, num_tlvs, _ = struct.unpack_from("<8s8I", buf, i)
        if total_len < HEADER_LEN or total_len > 100_000:
            buf = buf[i + len(MAGIC):]          # false magic match
            continue
        if len(buf) - i < total_len:
            break                               # frame not fully received yet
        end = i + total_len

        # The TLV length field may or may not include its own 8-byte header.
        # Try both and keep whichever fills the frame exactly.
        tlvs = _walk_tlvs(buf, i + HEADER_LEN, end, num_tlvs, True)
        layout = "TLV length includes the 8-byte header"
        if tlvs is None:
            tlvs = _walk_tlvs(buf, i + HEADER_LEN, end, num_tlvs, False)
            layout = "TLV length excludes the 8-byte header"
        if tlvs is not None and parse_stats["layout"] is None:
            parse_stats["layout"] = layout
            print("TLV layout detected:", layout)

        if tlvs is None:
            parse_stats["bad"] += 1
            if parse_stats["bad_shown"] < 2:
                parse_stats["bad_shown"] += 1
                print(f"Unparsable frame {frame_no} ({total_len} bytes, {num_tlvs} TLVs). Header:")
                print(buf[i:i + HEADER_LEN].hex(" "))
            buf = buf[end:]
            continue

        points, snrs = [], None
        for t, body, n in tlvs:
            if t == TLV_DETECTED_POINTS:
                for k in range(n // 16):
                    points.append(struct.unpack_from("<4f", buf, body + 16 * k))
            elif t == TLV_SIDE_INFO:
                snrs = [struct.unpack_from("<hh", buf, body + 4 * k)[0] * 0.1 for k in range(n // 4)]
        if snrs is not None and len(snrs) != len(points):
            snrs = None                         # mismatch: don't trust it
        frames.append((frame_no, points, snrs))
        buf = buf[end:]
    return frames, buf


# ---------------------------------------------------------------- cleanup

class Processor:
    """Gates out-of-range points and keeps only points that show up near the
    same spot across consecutive frames (single-frame speckle gets dropped)."""

    def __init__(self):
        self.history = deque(maxlen=PERSIST_FRAMES)

    @staticmethod
    def gate(points, snrs):
        kept = []
        for idx, (x, y, z, v) in enumerate(points):
            r = math.sqrt(x * x + y * y + z * z)
            if not (MIN_RANGE <= r <= MAX_RANGE):
                continue
            if abs(x) > MAX_SIDE or not (MIN_HEIGHT <= z <= MAX_HEIGHT):
                continue
            snr = snrs[idx] if snrs is not None else -1.0
            if snrs is not None and snr < MIN_SNR_DB:
                continue
            kept.append((x, y, z, v, snr))
        return kept

    @staticmethod
    def voxel(p):
        return (math.floor(p[0] / VOXEL), math.floor(p[1] / VOXEL), math.floor(p[2] / VOXEL))

    def persist(self, pts):
        current = {self.voxel(p) for p in pts}
        if PERSIST_MIN_HITS <= 0:
            out = pts
        else:
            out = []
            for p in pts:
                vx, vy, vz = self.voxel(p)
                hits = 0
                for past in self.history:
                    if any((vx + dx, vy + dy, vz + dz) in past
                           for dx in (-1, 0, 1) for dy in (-1, 0, 1) for dz in (-1, 0, 1)):
                        hits += 1
                if hits >= PERSIST_MIN_HITS:
                    out.append(p)
        self.history.append(current)
        return out


def cluster(pts):
    """DBSCAN. Returns (labels, clusters). labels[i] = object index or -1 for noise.
    clusters = [[cx, cy, cz, mean_velocity, num_points, radius], ...]"""
    n = len(pts)
    labels = [-1] * n
    eps2 = CLUSTER_EPS * CLUSTER_EPS

    def neighbors(i):
        xi, yi, zi = pts[i][0], pts[i][1], pts[i][2]
        return [j for j in range(n)
                if (pts[j][0] - xi) ** 2 + (pts[j][1] - yi) ** 2 + (pts[j][2] - zi) ** 2 <= eps2]

    cid = 0
    for i in range(n):
        if labels[i] != -1:
            continue
        nb = neighbors(i)
        if len(nb) < CLUSTER_MIN_PTS:
            continue
        labels[i] = cid
        queue = [j for j in nb if j != i]
        while queue:
            j = queue.pop()
            if labels[j] != -1:
                continue
            labels[j] = cid
            nb_j = neighbors(j)
            if len(nb_j) >= CLUSTER_MIN_PTS:
                queue.extend(k for k in nb_j if labels[k] == -1)
        cid += 1

    clusters = []
    for c in range(cid):
        members = [pts[i] for i in range(n) if labels[i] == c]
        k = len(members)
        cx = sum(p[0] for p in members) / k
        cy = sum(p[1] for p in members) / k
        cz = sum(p[2] for p in members) / k
        v = sum(p[3] for p in members) / k
        radius = max(0.15, max(math.dist((cx, cy, cz), p[:3]) for p in members))
        clusters.append([round(cx, 3), round(cy, 3), round(cz, 3), round(v, 3), k, round(radius, 3)])
    return labels, clusters


def process(proc, points, snrs):
    kept = proc.persist(proc.gate(points, snrs))
    labels, clusters = cluster(kept)
    out_points = [[round(x, 3), round(y, 3), round(z, 3), round(v, 3), round(s, 1), lab]
                  for (x, y, z, v, s), lab in zip(kept, labels)]
    return {"raw": len(points), "points": out_points, "clusters": clusters}


# ---------------------------------------------------------------- I/O

def read_data_forever(port):
    global latest_payload, latest_frame_id
    proc = Processor()
    buf = b""
    count = 0
    bytes_seen = 0
    last_heartbeat = time.time()
    while True:
        chunk = port.read(4096)
        bytes_seen += len(chunk)
        buf += chunk
        frames, buf = extract_frames(buf)
        for frame_no, points, snrs in frames:
            payload = process(proc, points, snrs)
            with lock:
                latest_payload = payload
                latest_frame_id += 1
            count += 1
            if count == 1:
                print("SNR side info:", "yes" if snrs is not None else "no (SNR filter is off)")
            if count == 1 or count % PRINT_EVERY == 0:
                print(f"frame {frame_no}: raw {payload['raw']} -> kept {len(payload['points'])} points, "
                      f"{len(payload['clusters'])} objects")
        if len(buf) > 200_000:
            buf = buf[-40_000:]                 # never found a valid frame; keep the buffer bounded
        if count == 0 and time.time() - last_heartbeat > 5:
            last_heartbeat = time.time()
            if bytes_seen == 0:
                print(f"No data on {DATA_PORT} yet. Check the port number, press reset on the board, "
                      "and check the guiMonitor line in the cfg.")
            else:
                print(f"{bytes_seen} bytes received on {DATA_PORT}, but no complete frames yet "
                      f"(unparsable frames: {parse_stats['bad']}).")


async def stream(ws):
    """Send the newest processed frame to the browser each time a new frame arrives."""
    last_sent = -1
    try:
        while True:
            with lock:
                frame_id, payload = latest_frame_id, latest_payload
            if frame_id != last_sent:
                await ws.send(json.dumps(payload))
                last_sent = frame_id
            await asyncio.sleep(0.02)
    except websockets.ConnectionClosed:
        pass


async def main():
    async with websockets.serve(stream, WS_HOST, WS_PORT):
        print(f"WebSocket running on ws://{WS_HOST}:{WS_PORT}")
        print("Now open index.html in your browser. Ctrl+C to stop.")
        await asyncio.Future()


if __name__ == "__main__":
    data_port = serial.Serial(DATA_PORT, 921600, timeout=0.1)   # fails fast if the port is wrong
    threading.Thread(target=read_data_forever, args=(data_port,), daemon=True).start()
    time.sleep(0.5)                              # let the data port settle before sensorStart
    send_config()
    asyncio.run(main())
