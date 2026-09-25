import socket
import time

HOST = "0.0.0.0"
PORT = 5555

with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
    s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    s.bind((HOST, PORT))
    s.listen()

    print(f"Local OCC time server listening on {HOST}:{PORT}")

    while True:
        conn, addr = s.accept()
        with conn:
            epoch_ms = int(time.time() * 1000)
            conn.sendall(f"{epoch_ms}\n".encode())
            print(addr, epoch_ms)
