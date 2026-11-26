import serial, struct, socket, json, math
from collections import deque, Counter

DATA_PORT = "COM4"
BAUD = 921600
MAGIC = bytes([0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x08, 0x07])
HEADER_LEN = 40
POINT_TLV = 1

WINDOW = 5      # look at the last 5 frames
MIN_HITS = 3    # keep a point only if its cell was hit in 3 of them
CELL = 0.25     # cell size in meters

sock = socket.create_connection(("127.0.0.1", 5555))
ser = serial.Serial(DATA_PORT, BAUD, timeout=0.1)
buf = bytearray()
recent = deque(maxlen=WINDOW)

def to_spherical(x, y, z):
    r = math.sqrt(x*x + y*y + z*z)
    az = math.degrees(math.atan2(x, y))
    el = math.degrees(math.atan2(z, math.hypot(x, y)))
    return r, az, el

def cell_of(p):
    return tuple(math.floor(c / CELL) for c in p)

def send_points(pts):
    sph = [to_spherical(x, y, z) for x, y, z in pts]
    msg = {"sph": [[round(r, 3), round(a, 2), round(e, 2)] for r, a, e in sph]}
    sock.sendall((json.dumps(msg) + "\n").encode())

def parse_points(packet):
    num_tlv = struct.unpack_from("<I", packet, 32)[0]
    off = HEADER_LEN
    points = []
    for _ in range(num_tlv):
        if off + 8 > len(packet):
            break
        tlv_type, tlv_len = struct.unpack_from("<II", packet, off)
        if off + 8 + tlv_len > len(packet):
            break
        if tlv_type == POINT_TLV:
            for k in range(tlv_len // 16):
                x, y, z, v = struct.unpack_from("<4f", packet, off + 8 + k * 16)
                points.append((x, y, z))
        off += 8 + tlv_len
    return points

print("Streaming filtered radar points to Blender. Press Ctrl+C to stop.")
while True:
    buf += ser.read(max(ser.in_waiting, 1))
    i = buf.find(MAGIC)
    if i < 0:
        buf = buf[-7:]
        continue
    buf = buf[i:]
    if len(buf) < 16:
        continue
    total_len = struct.unpack_from("<I", buf, 12)[0]
    if total_len < HEADER_LEN or total_len > 65536:
        buf = buf[8:]
        continue
    if len(buf) < total_len:
        continue
    packet = bytes(buf[:total_len])
    buf = buf[total_len:]

    pts = parse_points(packet)
    recent.append({cell_of(p) for p in pts})
    counts = Counter(c for frame in recent for c in frame)
    kept = [p for p in pts if counts[cell_of(p)] >= MIN_HITS]
    send_points(kept)