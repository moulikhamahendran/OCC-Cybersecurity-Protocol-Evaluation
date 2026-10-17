import socket
import sys
import threading
import time

listen_ip = sys.argv[1]
target_ip = sys.argv[2]

PORTS = (1883, 1884, 8883)

def pump(src, dst):
    try:
        while True:
            data = src.recv(65536)

            if not data:
                break

            dst.sendall(data)

    except Exception:
        pass

    finally:
        try:
            dst.shutdown(socket.SHUT_WR)
        except Exception:
            pass


def handle(client, peer, port):
    upstream = None

    try:
        upstream = socket.create_connection(
            (target_ip, port),
            timeout=10,
        )

        print(
            f"[relay {port}] forwarding "
            f"{peer[0]}:{peer[1]} -> "
            f"{target_ip}:{port}",
            flush=True,
        )

        a = threading.Thread(
            target=pump,
            args=(client, upstream),
            daemon=True,
        )

        b = threading.Thread(
            target=pump,
            args=(upstream, client),
            daemon=True,
        )

        a.start()
        b.start()

        a.join()
        b.join()

    except Exception as exc:
        print(
            f"[relay {port}] ERROR {exc}",
            flush=True,
        )

    finally:
        try:
            client.close()
        except Exception:
            pass

        if upstream:
            try:
                upstream.close()
            except Exception:
                pass


def listener(port):
    server = socket.socket(
        socket.AF_INET,
        socket.SOCK_STREAM,
    )

    server.setsockopt(
        socket.SOL_SOCKET,
        socket.SO_REUSEADDR,
        1,
    )

    server.bind((listen_ip, port))
    server.listen(32)

    print(
        f"[relay {port}] LISTENING "
        f"{listen_ip}:{port} -> {target_ip}:{port}",
        flush=True,
    )

    while True:
        client, peer = server.accept()

        threading.Thread(
            target=handle,
            args=(client, peer, port),
            daemon=True,
        ).start()


for port in PORTS:
    threading.Thread(
        target=listener,
        args=(port,),
        daemon=True,
    ).start()

while True:
    time.sleep(3600)
