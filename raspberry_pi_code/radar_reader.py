
import serial
import struct
import math

PORT = "/dev/ttyUSB1"
BAUD = 921600

MAGIC = bytes.fromhex("02 01 04 03 06 05 08 07")
HEADER_FORMAT = "<8s8I"
HEADER_SIZE = 40

buffer = bytearray()

print("AWR1843AOP Radar Reader")
print("Listening for live radar data...")
print("Press Ctrl+C to stop.\n")

try:
    with serial.Serial(PORT, BAUD, timeout=0.1) as radar:

        while True:
            buffer.extend(radar.read(4096))

            while True:
                start = buffer.find(MAGIC)

                if start < 0:
                    buffer = buffer[-7:]
                    break

                if start > 0:
                    del buffer[:start]

                if len(buffer) < HEADER_SIZE:
                    break

                header = struct.unpack_from(
                    HEADER_FORMAT, buffer
                )

                packet_length = header[2]
                frame_number = header[4]
                detected_points = header[6]
                num_tlvs = header[7]

                if not HEADER_SIZE <= packet_length <= 1048576:
                    del buffer[0]
                    continue

                if len(buffer) < packet_length:
                    break

                packet = bytes(buffer[:packet_length])
                del buffer[:packet_length]

                offset = HEADER_SIZE
                points = []

                for _ in range(num_tlvs):

                    if offset + 8 > len(packet):
                        break

                    tlv_type, tlv_length = struct.unpack_from(
                        "<II", packet, offset
                    )

                    offset += 8

                    if offset + tlv_length > len(packet):
                        break

                    if tlv_type == 1:
                        for i in range(tlv_length // 16):
                            x, y, z, velocity = struct.unpack_from(
                                "<ffff", packet, offset + i * 16
                            )

                            distance = math.sqrt(
                                x*x + y*y + z*z
                            )

                            points.append(
                                (x, y, z, velocity, distance)
                            )

                    offset += tlv_length

                print(
                    f"\nFrame: {frame_number} | "
                    f"Reported points: {detected_points} | "
                    f"Decoded points: {len(points)}"
                )

                for i, (x, y, z, v, d) in enumerate(points, 1):
                    print(
                        f"Point {i:02d}: "
                        f"X={x:6.2f} m | "
                        f"Y={y:6.2f} m | "
                        f"Z={z:6.2f} m | "
                        f"V={v:6.2f} m/s | "
                        f"Range={d:6.2f} m"
                    )

except KeyboardInterrupt:
    print("\nRadar reader stopped.")
