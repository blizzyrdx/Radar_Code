import serial, struct, time

MAGIC = bytes([0x02, 0x01, 0x04, 0x03, 0x06, 0x05, 0x08, 0x07])
ser = serial.Serial("COM4", 921600, timeout=0.5)
buf = bytearray()
good = bad = shown_bad = 0
end = time.time() + 10

def parse(packet, hdr_len):
    if len(packet) < hdr_len:
        return None
    num_obj, num_tlv = struct.unpack_from("<II", packet, 28)
    off, tlvs = hdr_len, []
    for _ in range(num_tlv):
        if off + 8 > len(packet):
            return None
        t, l = struct.unpack_from("<II", packet, off)
        if off + 8 + l > len(packet):
            return None
        tlvs.append((t, off + 8, l))   # payload starts after the 8-byte block header
        off += 8 + l                    # length excludes the header
    return num_obj, tlvs

print("Reading COM4 for 10 seconds...")
while time.time() < end:
    buf += ser.read(max(ser.in_waiting, 1))
    i = buf.find(MAGIC)
    if i < 0:
        buf = buf[-7:]
        continue
    buf = buf[i:]
    if len(buf) < 16:
        continue
    total = struct.unpack_from("<I", buf, 12)[0]
    if total < 36 or total > 65536:
        buf = buf[8:]
        continue
    if len(buf) < total:
        continue
    packet = bytes(buf[:total])
    buf = buf[total:]

    hdr, result = None, None
    for hdr in (40, 36):
        result = parse(packet, hdr)
        if result:
            break
    if not result:
        bad += 1
        if shown_bad < 2:
            shown_bad += 1
            print("Could not parse packet. First 48 bytes:")
            print(packet[:48].hex(" "))
        continue

    good += 1
    num_obj, tlvs = result
    pts = None
    for t, off, l in tlvs:
        if t == 1 and l >= 24:
            pts = struct.unpack_from("<4f", packet, off)
            break
    if good <= 5 or good % 20 == 0:
        types = [t for t, _, _ in tlvs]
        print(f"frame {good}: len={total} header={hdr} objects={num_obj} types={types} first_point={pts}")

print(f"Parsed frames: {good}   Unparsed: {bad}")
ser.close()