import os
import shutil
import subprocess
import tempfile
import threading
import time
from pathlib import Path

from .config import JAR_PATH, PARSER_PORT, ROOT
from .utils import download, log

parser_process = None


def ensure_temp_maven():
    version = "3.9.11"
    base = Path(tempfile.gettempdir()) / "cascade-maven"
    archive = base / f"apache-maven-{version}-bin.zip"
    folder = base / f"apache-maven-{version}"
    mvn = folder / "bin" / ("mvn.cmd" if os.name == "nt" else "mvn")
    if mvn.exists():
        return str(mvn)
    base.mkdir(parents=True, exist_ok=True)
    if not archive.exists():
        log("Downloading temporary Maven")
        download(f"https://archive.apache.org/dist/maven/maven-3/{version}/binaries/apache-maven-{version}-bin.zip", archive)
    shutil.unpack_archive(str(archive), str(base))
    return str(mvn)


def ensure_jar():
    if JAR_PATH.exists():
        return
    mvn = shutil.which("mvn") or ensure_temp_maven()
    log("Building parser jar")
    subprocess.run([mvn, "package", "-DskipTests"], cwd=ROOT, check=True)


def port_open(port):
    import socket
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(0.4)
        return sock.connect_ex(("127.0.0.1", port)) == 0


def drain_parser_stderr():
    if not parser_process or not parser_process.stderr:
        return
    for line in parser_process.stderr:
        log(f"parser: {line.rstrip()}")


def ensure_parser():
    global parser_process
    ensure_jar()
    if port_open(PARSER_PORT):
        return
    if parser_process and parser_process.poll() is None:
        return
    log("Starting Java parser on port 5600")
    parser_process = subprocess.Popen(
        ["java", "-jar", str(JAR_PATH)],
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )
    threading.Thread(target=drain_parser_stderr, daemon=True).start()
    for _ in range(40):
        if port_open(PARSER_PORT):
            return
        if parser_process.poll() is not None:
            raise RuntimeError("Java parser exited during startup")
        time.sleep(0.25)
    raise RuntimeError("Java parser did not start on port 5600")
