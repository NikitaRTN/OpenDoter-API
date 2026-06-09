import json
import socket
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler

from .config import CONSTANTS
from .matches import get_match_dir, get_match_metadata, parse_status, start_parse_thread
from .players import (
    get_player_heroes,
    get_player_matches,
    get_player_profile,
    get_player_totals,
    get_player_wl,
    rebuild_players_index,
    search_players,
    search_players_local,
)
from .utils import read_json

# Константы (heroes/items/abilities/ability_ids) меняются крайне редко, но
# запрашиваются на КАЖДОЙ загрузке страницы матча. Раньше файл читался с диска
# и заново парсился + сериализовался на каждый запрос. Кэшируем сырые байты в
# памяти (с проверкой mtime, чтобы подхватывать обновления) и отдаём напрямую.
_CONSTANTS_BYTES_CACHE = {}
_MATCH_RESPONSE_BYTES_CACHE = {}


def load_match_response_bytes(match_id, metadata_path, blob_path):
    key = str(match_id)
    try:
        mtime = (metadata_path.stat().st_mtime, blob_path.stat().st_mtime)
    except OSError:
        return None
    cached = _MATCH_RESPONSE_BYTES_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]

    payload = b'{"match":' + metadata_path.read_bytes() + b',"parsed":' + blob_path.read_bytes() + b'}'
    _MATCH_RESPONSE_BYTES_CACHE[key] = (mtime, payload)
    return payload


def load_constant_bytes(key):
    path = CONSTANTS.get(key)
    if path is None:
        return None
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return None
    cached = _CONSTANTS_BYTES_CACHE.get(key)
    if cached is not None and cached[0] == mtime:
        return cached[1]
    payload = path.read_bytes()
    _CONSTANTS_BYTES_CACHE[key] = (mtime, payload)
    return payload


class Handler(BaseHTTPRequestHandler):
    def send_json(self, data, status=200):
        try:
            payload = json.dumps(data, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, socket.error):
            # Клиент уже отвалился — дальше пытаться нечего.
            raise

    def send_raw_json(self, payload, status=200):
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(payload)))
            self.send_header("Cache-Control", "public, max-age=3600")
            self.end_headers()
            self.wfile.write(payload)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, socket.error):
            raise

    def _send_error_json(self, message, status=500, label="API error"):
        try:
            self.send_json({"error": label, "message": message}, status)
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, socket.error):
            pass

    def log_message(self, format, *args):
        # Чтобы не дублировать записи (у BaseHTTPRequestHandler уже есть формат).
        return

    def do_GET(self):
        try:
            self._handle_get()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, socket.error):
            # Клиент отвалился — молча завершаем обработку.
            return
        except Exception as exc:
            # Последний рубеж: не дать одному кривому запросу уронить сервер.
            self._send_error_json(str(exc), 500, "Internal error")

    def _handle_get(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path

        if path.startswith("/api/status/"):
            match_id = path.rsplit("/", 1)[-1]
            self.send_json(parse_status.get(match_id, {"state": "idle", "message": "Not started"}))
            return

        if path.startswith("/api/match/"):
            # /api/match/{id}/metadata — лёгкие данные для страницы необработанного матча
            if path.endswith("/metadata"):
                match_id = path.rsplit("/", 2)[-2]
                if not match_id.isdigit():
                    self._send_error_json("match_id must be numeric", 400, "Bad request")
                    return
                try:
                    self.send_json(get_match_metadata(match_id))
                except urllib.error.HTTPError as exc:
                    status = 404 if exc.code == 404 else 502
                    label = "Not found" if exc.code == 404 else "OpenDota error"
                    self._send_error_json(f"OpenDota returned HTTP {exc.code}", status, label)
                except Exception as exc:
                    self._send_error_json(str(exc), 502, "OpenDota error")
                return

            # /api/match/{id} и /api/match/{id}?full=1 — полные распарсенные данные
            match_id = path.rsplit("/", 1)[-1]
            folder = get_match_dir(match_id)
            blob = folder / "parsed_blob.json"
            metadata = folder / "match.json"
            if not blob.exists() or not metadata.exists():
                self.send_json({"error": "Match is not parsed"}, 404)
                return
            payload = load_match_response_bytes(match_id, metadata, blob)
            if payload is None:
                self.send_json({"error": "Match is not parsed"}, 404)
                return
            self.send_raw_json(payload)
            return

        # /api/players/{id} и /api/players/{id}/matches?limit=20
        if path.startswith("/api/players/"):
            sub = path[len("/api/players/"):]
            if "/" in sub:
                account_id, tail = sub.split("/", 1)
                if not account_id.isdigit():
                    self._send_error_json("account_id must be numeric", 400, "Bad request")
                    return
                if tail.startswith("matches"):
                    limit = 20
                    offset = 0
                    include_turbo = False
                    qs = urllib.parse.parse_qs(parsed.query)
                    if "limit" in qs and qs["limit"]:
                        try:
                            limit = max(1, min(100, int(qs["limit"][0])))
                        except (TypeError, ValueError):
                            pass
                    if "offset" in qs and qs["offset"]:
                        try:
                            offset = max(0, int(qs["offset"][0]))
                        except (TypeError, ValueError):
                            pass
                    if "turbo" in qs and qs["turbo"]:
                        include_turbo = str(qs["turbo"][0]).lower() in ("1", "true", "yes", "on")
                    try:
                        self.send_json(get_player_matches(account_id, limit, offset, include_turbo))
                    except Exception as exc:
                        self._send_error_json(str(exc), 502, "OpenDota error")
                    return
                if tail.startswith("wl"):
                    qs = urllib.parse.parse_qs(parsed.query)
                    include_turbo = bool(qs.get("turbo") and str(qs["turbo"][0]).lower() in ("1", "true", "yes", "on"))
                    self.send_json(get_player_wl(account_id, include_turbo))
                    return
                if tail.startswith("heroes"):
                    qs = urllib.parse.parse_qs(parsed.query)
                    include_turbo = bool(qs.get("turbo") and str(qs["turbo"][0]).lower() in ("1", "true", "yes", "on"))
                    self.send_json(get_player_heroes(account_id, include_turbo))
                    return
                if tail.startswith("totals"):
                    self.send_json(get_player_totals(account_id))
                    return
                self._send_error_json("Unknown players subpath: " + tail, 404, "Not found")
                return
            if not sub.isdigit():
                self._send_error_json("account_id must be numeric", 400, "Bad request")
                return
            try:
                self.send_json(get_player_profile(sub))
            except Exception as exc:
                self._send_error_json(str(exc), 502, "OpenDota error")
            return

        if path == "/api/search":
            qs = urllib.parse.parse_qs(parsed.query)
            query = (qs.get("q") or [""])[0]
            # Сначала ищем в локальном индексе (мгновенно, офлайн).
            # OpenDota — медленный и часто пустой, дёргаем только если локально ничего.
            local_results = search_players_local(query)
            if local_results:
                self.send_json(local_results)
                return
            try:
                self.send_json(search_players(query))
            except Exception as exc:
                self._send_error_json(str(exc), 502, "OpenDota error")
            return

        if path == "/api/players_index/rebuild":
            try:
                index = rebuild_players_index()
                self.send_json({
                    "players": len(index["players"]),
                    "sources": index["sources"],
                    "built_at": index["built_at"],
                })
            except Exception as exc:
                self._send_error_json(str(exc), 500, "Rebuild error")
            return

        if path.startswith("/constants/") and path.endswith(".json"):
            key = path[len("/constants/"):-len(".json")]
            if key in CONSTANTS:
                payload = load_constant_bytes(key)
                if payload is None:
                    self._send_error_json("Constant file not found: " + key, 404, "Not found")
                else:
                    self.send_raw_json(payload)
                return

        self.send_json({"error": "Not found"}, 404)

    def do_POST(self):
        try:
            self._handle_post()
        except (ConnectionAbortedError, ConnectionResetError, BrokenPipeError, socket.error):
            return
        except Exception as exc:
            self._send_error_json(str(exc), 500, "Internal error")

    def _handle_post(self):
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path == "/api/parse":
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b"{}"
            payload = json.loads(body.decode("utf-8"))
            match_id = str(payload.get("match_id", "")).strip()
            if not match_id.isdigit():
                self.send_json({"error": "match_id must be numeric"}, 400)
                return
            start_parse_thread(match_id)
            self.send_json({"match_id": match_id, "state": parse_status[match_id]["state"]})
            return
        self.send_json({"error": "Not found"}, 404)
