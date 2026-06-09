import json
import shutil
import subprocess
import time
import urllib.request

from .config import ROOT


def log(message):
    print(f"[{time.strftime('%H:%M:%S')}] {message}", flush=True)


def download(url, target):
    target.parent.mkdir(parents=True, exist_ok=True)
    tmp = target.with_suffix(target.suffix + ".tmp")
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DotaLocalParser/1.0",
            "Accept": "*/*",
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=90) as response, tmp.open("wb") as out:
            shutil.copyfileobj(response, out)
    except Exception:
        curl = shutil.which("curl.exe") or shutil.which("curl")
        if not curl:
            raise
        subprocess.run(
            [curl, "-f", "-L", "-A", "Mozilla/5.0 DotaLocalParser/1.0", url, "-o", str(tmp)],
            cwd=ROOT,
            check=True,
        )
    tmp.replace(target)


def read_json(path):
    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False)
