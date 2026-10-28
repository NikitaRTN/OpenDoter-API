import socket
from http.server import ThreadingHTTPServer

from .config import DATA_DIR, WEB_PORT
from .constants import ensure_constants
from .handler import Handler
from .utils import log


class APIHTTPServer(ThreadingHTTPServer):
    # On Windows SO_REUSEADDR permits multiple servers on the same port,
    # leaving requests routed to an old API instance. Reject duplicates.
    allow_reuse_address = not hasattr(socket, "SO_EXCLUSIVEADDRUSE")

    def server_bind(self):
        if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
            self.socket.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
        super().server_bind()


def main():
    ensure_constants()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    try:
        server = APIHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    except OSError as exc:
        raise SystemExit(f"Cannot start OpenDoter API on port {WEB_PORT}: {exc}. Stop the previous OpenDoter API instance or choose another PORT.") from exc
    log(f"OpenDoter API: http://localhost:{WEB_PORT}/ (health: /health). The PHP site is a separate server.")
    server.serve_forever()
