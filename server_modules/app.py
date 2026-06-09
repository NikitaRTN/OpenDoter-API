from http.server import ThreadingHTTPServer

from .config import DATA_DIR, WEB_PORT
from .constants import ensure_constants
from .handler import Handler
from .utils import log


def main():
    ensure_constants()
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    server = ThreadingHTTPServer(("0.0.0.0", WEB_PORT), Handler)
    log(f"Open http://localhost:{WEB_PORT}/")
    server.serve_forever()
