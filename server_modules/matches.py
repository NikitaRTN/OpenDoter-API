import bz2
import json
import subprocess
import threading
import time
import urllib.error
import urllib.request

from .config import DATA_DIR, PARSER_PORT, ROOT
from .constants import ensure_constants
from .parser_process import ensure_parser
from .utils import download, log, read_json, write_json

parse_locks = {}
parse_status = {}


def get_match_dir(match_id):
    return DATA_DIR / str(match_id)


def fetch_match_metadata(match_id, folder):
    path = folder / "match.json"
    if path.exists():
        return read_json(path)
    log(f"Fetching match metadata: {match_id}")
    request = urllib.request.Request(
        f"https://api.opendota.com/api/matches/{match_id}",
        headers={
            "User-Agent": "Mozilla/5.0 DotaLocalParser/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=60) as response:
        metadata = json.loads(response.read().decode("utf-8"))
    write_json(path, metadata)
    return metadata


def request_match_parse(match_id):
    """
    Отправляет команду координатору OpenDota на парсинг свежего матча.
    """
    url = f"https://api.opendota.com/api/request/{match_id}"
    try:
        log(f"Реплей еще не обработан. Отправляем запрос на парсинг {match_id}...")
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": "Mozilla/5.0 DotaLocalParser/1.0",
                "Accept": "application/json",
            },
            method="POST"
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            if response.status == 200:
                log("Запрос успешно отправлен. Ждем 30 секунд...")
                time.sleep(30)
                return True
            else:
                log(f"Не удалось запустить парсинг. Код ответа: {response.status}")
                return False
    except Exception as e:
        log(f"Ошибка сети при запросе парсинга: {e}")
        return False


def get_replay_url(match_id, folder, auto_request=True):
    """
    Получает URL реплея через основной эндпоинт матча OpenDota.
    """
    api_url = f"https://api.opendota.com/api/matches/{match_id}"
    
    try:
        request = urllib.request.Request(
            api_url,
            headers={
                "User-Agent": "Mozilla/5.0 DotaLocalParser/1.0",
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = json.loads(response.read().decode("utf-8"))
        
        # Сохраняем метаданные
        write_json(folder / "match.json", data)
        
        # В основном API OpenDota уже отдает готовую ссылку
        replay_url = data.get("replay_url")
        
        # Фоллбэк: если ссылки почему-то нет, но есть cluster и replay_salt
        if not replay_url:
            cluster = data.get("cluster")
            replay_salt = data.get("replay_salt")
            if cluster and replay_salt:
                replay_url = f"http://replay{cluster}.valve.net/570/{match_id}_{replay_salt}.dem.bz2"
        
        # Если ссылка все еще не сформирована (матч есть, но реплей не спаршен)
        if not replay_url and auto_request:
            if request_match_parse(match_id):
                return get_replay_url(match_id, folder, auto_request=False)
        
        if not replay_url:
            raise RuntimeError("No replay URL or replay_salt in match metadata")
        
        return replay_url
        
    except urllib.error.HTTPError as e:
        if e.code == 404 and auto_request:
            if request_match_parse(match_id):
                return get_replay_url(match_id, folder, auto_request=False)
        raise RuntimeError(f"Failed to fetch match metadata: {e}")


def post_dem_to_parser(dem_path, jsonl_path):
    import http.client
    ensure_parser()
    conn = http.client.HTTPConnection("127.0.0.1", PARSER_PORT, timeout=900)
    with dem_path.open("rb") as file:
        conn.request("POST", "/", body=file.read(), headers={"Content-Type": "application/octet-stream"})
    response = conn.getresponse()
    payload = response.read()
    conn.close()
    if response.status >= 400:
        raise RuntimeError(f"Parser HTTP {response.status}: {payload[:500]!r}")
    jsonl_path.write_bytes(payload)


def build_blob(match_id, jsonl_path, blob_path):
    command = ["node", str(ROOT / "processors" / "createParsedDataBlob.mjs"), str(match_id)]
    with jsonl_path.open("rb") as stdin, blob_path.open("wb") as stdout:
        result = subprocess.run(command, cwd=ROOT, stdin=stdin, stdout=stdout, stderr=subprocess.PIPE)
    if result.returncode:
        raise RuntimeError(result.stderr.decode("utf-8", "replace"))


def parse_match(match_id):
    match_id = str(match_id).strip()
    if not match_id.isdigit():
        raise ValueError("match_id must be numeric")
    lock = parse_locks.setdefault(match_id, threading.Lock())
    with lock:
        folder = get_match_dir(match_id)
        folder.mkdir(parents=True, exist_ok=True)
        blob_path = folder / "parsed_blob.json"
        if blob_path.exists() and (folder / "match.json").exists():
            parse_status[match_id] = {"state": "done", "message": "Loaded from cache"}
            _refresh_players_index_after_parse(match_id)
            return
        parse_status[match_id] = {"state": "running", "message": "Preparing constants"}
        ensure_constants()
        parse_status[match_id] = {"state": "running", "message": "Fetching replay URL"}
        replay_url = get_replay_url(match_id, folder)
        bz2_path = folder / f"{match_id}.dem.bz2"
        dem_path = folder / f"{match_id}.dem"
        jsonl_path = folder / "parsed.jsonl"
        if not bz2_path.exists():
            parse_status[match_id] = {"state": "running", "message": "Downloading replay"}
            download(replay_url, bz2_path)
        if not dem_path.exists():
            parse_status[match_id] = {"state": "running", "message": "Decompressing replay"}
            dem_path.write_bytes(bz2.decompress(bz2_path.read_bytes()))
        if not jsonl_path.exists():
            parse_status[match_id] = {"state": "running", "message": "Parsing replay"}
            post_dem_to_parser(dem_path, jsonl_path)
        parse_status[match_id] = {"state": "running", "message": "Building parsed blob"}
        build_blob(match_id, jsonl_path, blob_path)
        parse_status[match_id] = {"state": "done", "message": "Done"}
        _refresh_players_index_after_parse(match_id)


def _refresh_players_index_after_parse(match_id):
    """Ленивое обновление индекса после парсинга — чтобы поиск сразу видел новых игроков."""
    try:
        from .players import update_index_with_match
        from .utils import read_json
        match_path = get_match_dir(match_id) / "match.json"
        if not match_path.exists():
            return
        update_index_with_match(match_id, read_json(match_path))
    except Exception as exc:
        log(f"players index refresh after {match_id} failed: {exc}")


def get_match_metadata(match_id):
    """Лёгкие метаданные матча с OpenDota (без тяжёлого парсинга .dem).

    Нужно фронту, чтобы показать «главную» страницу необработанного матча:
    герои, длительность, победителя — и кнопку «Запросить обработку».
    Кэшируется в data/matches/{id}/opendota_meta.json.
    """
    folder = get_match_dir(match_id)
    folder.mkdir(parents=True, exist_ok=True)
    cache_path = folder / "opendota_meta.json"
    if cache_path.exists():
        return read_json(cache_path)

    # Внутрикластерный импорт, чтобы не тянуть urllib на старте
    from .players import http_get_json

    log(f"OpenDota fetch: match metadata {match_id}")
    try:
        data = http_get_json(
            f"https://api.opendota.com/api/matches/{match_id}",
            timeout=30,
        )
        write_json(cache_path, data)
        return data
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            raise RuntimeError(f"OpenDota: матч {match_id} не найден") from exc
        log(f"OpenDota match metadata HTTP {exc.code} for {match_id}")
        if cache_path.exists():
            return read_json(cache_path)
        raise
    except Exception as exc:
        log(f"OpenDota match metadata error for {match_id}: {exc}")
        if cache_path.exists():
            return read_json(cache_path)
        raise


def start_parse_thread(match_id):
    if parse_status.get(match_id, {}).get("state") == "running":
        return
    parse_status[match_id] = {"state": "queued", "message": "Queued"}
    def worker():
        try:
            parse_match(match_id)
        except Exception as exc:
            parse_status[match_id] = {"state": "error", "message": str(exc)}
            log(f"parse error {match_id}: {exc}")
    threading.Thread(target=worker, daemon=True).start()
