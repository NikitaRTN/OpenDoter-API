from .config import CONSTANT_URLS, CONSTANTS
from .utils import download, log


def ensure_constants():
    for key, path in CONSTANTS.items():
        if not path.exists() or path.stat().st_size < 1000:
            log(f"Downloading constants: {key}")
            download(CONSTANT_URLS[key], path)
