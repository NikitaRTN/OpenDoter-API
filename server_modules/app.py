from http.server import ThreadingHTTPServer

from .config import DATA_DIR, WEB_PORT
from .constants import ensure_constants
from .handler import Handler
from .utils import log


def main():
    ensure_constants()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    log(f"OpenDoter API: http://localhost:{WEB_PORT}/ (health: /health). The PHP site is a separate server.")
    server.serve_forever()
