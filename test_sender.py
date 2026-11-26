import socket, json, time, math

s = socket.create_connection(("127.0.0.1", 5555))
t = 0.0
while True:
    x = 0.5 * math.sin(t)
    y = 2.0 + 0.5 * math.cos(t)
    z = 0.0
    s.sendall((json.dumps({"x": x, "y": y, "z": z}) + "\n").encode())
    t += 0.1
    time.sleep(0.1)