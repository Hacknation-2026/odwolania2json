"""GUI launcher: picks a free port, starts the API server and opens the browser once it is ready."""

import socket
import threading
import time
import urllib.request
import webbrowser

import uvicorn

from app.config import get_settings


def _free_port(start: int, attempts: int = 20) -> int:
    for port in range(start, start + attempts):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:  # nothing listening there
                return port
    raise SystemExit(f"Brak wolnego portu w zakresie {start}-{start + attempts - 1}")


def _open_when_ready(url: str, timeout: float = 30) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        try:
            with urllib.request.urlopen(f"{url}/api/health", timeout=1) as r:
                if r.status == 200:
                    webbrowser.open(url)
                    return
        except OSError:
            time.sleep(0.3)
    print(f"Serwer nie odpowiada - otwórz ręcznie {url}")


def main() -> None:
    s = get_settings()
    port = _free_port(s.gui_port)
    url = f"http://localhost:{port}"
    print(f"Odwołania2json GUI: {url}  (Ctrl+C kończy)")
    if s.gui_host not in ("127.0.0.1", "localhost"):
        print(f"Dostępne też z innych komputerów: http://<adres-tej-maszyny>:{port}")
    threading.Thread(target=_open_when_ready, args=(url,), daemon=True).start()
    uvicorn.run("app.main:app", host=s.gui_host, port=port, log_level="warning")


if __name__ == "__main__":
    main()
