import socket
import struct
import sys
import time

bind_ip = sys.argv[1]
EPOCH = 2208988800

def ntp_stamp(value):
    sec = int(value) + EPOCH
    frac = int((value - int(value)) * (1 << 32))
    return struct.pack(
        "!II",
        sec & 0xffffffff,
        frac & 0xffffffff,
    )

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((bind_ip, 123))

print(f"[ntp] LISTENING {bind_ip}:123", flush=True)

while True:
    data, peer = sock.recvfrom(1024)

    if len(data) < 48:
        continue

    now = time.time()
    version = (data[0] >> 3) & 7

    if version < 3:
        version = 4

    reply = bytearray(48)

    reply[0] = (version << 3) | 4
    reply[1] = 2
    reply[2] = data[2]
    reply[3] = 0xEC

    reply[12:16] = b"LOCL"
    reply[16:24] = ntp_stamp(now - 1)
    reply[24:32] = data[40:48]
    reply[32:40] = ntp_stamp(now)
    reply[40:48] = ntp_stamp(time.time())

    sock.sendto(reply, peer)

    print(
        f"[ntp] reply -> {peer[0]}:{peer[1]}",
        flush=True,
    )
