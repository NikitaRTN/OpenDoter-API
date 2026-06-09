"""
Прокси-эндпоинты профилей игроков.

PHP-фронтенд не умеет ходить в OpenDota напрямую (нет ext/openssl), поэтому
этот модуль вытягивает данные с api.opendota.com и кэширует на диск, чтобы
последующие запросы не зависели от сети.
"""
import concurrent.futures
import json
import threading
import time
import urllib.error
import urllib.parse
import urllib.request

from .config import DATA_DIR, PLAYERS_DIR
from .utils import log, read_json, write_json


OPENDOTA_BASE = "https://api.opendota.com/api"
PROFILE_CACHE_TTL = 3600   # 1 час — профиль почти не меняется
MATCHES_CACHE_TTL = 300    # 5 минут — свежие матчи должны быстро подтягиваться

PLAYERS_INDEX_PATH = PLAYERS_DIR / "_index.json"
_index_lock = threading.Lock()


def get_player_dir(account_id):
    return PLAYERS_DIR / str(account_id)


def http_get_json(url, timeout=30):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 DotaLocalParser/1.0",
            "Accept": "application/json",
        },
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def normalize_profile(data):
    """Привести плоский ответ OpenDota к формату, который ждёт render_player_profile.

    Сохраняем больше полей (computed_mmr, plus, steamid, aliases), чтобы
    фронтенд мог показать подробный профиль в стиле OpenDota.
    """
    inner = data.get("profile") if isinstance(data.get("profile"), dict) else data
    return {
        "profile": {
            "account_id": inner.get("account_id"),
            "personaname": inner.get("personaname", ""),
            "name": inner.get("name", ""),
            "avatarfull": inner.get("avatarfull", ""),
            "avatarmedium": inner.get("avatarmedium", ""),
            "avatar": inner.get("avatar", ""),
            "profileurl": inner.get("profileurl", ""),
            "last_login": inner.get("last_login"),
            "loccountrycode": inner.get("loccountrycode", ""),
            "plus": inner.get("plus"),
            "steamid": inner.get("steamid"),
            "is_contributor": inner.get("is_contributor"),
            "is_subscriber": inner.get("is_subscriber"),
        },
        "rank_tier": data.get("rank_tier"),
        "leaderboard_rank": data.get("leaderboard_rank"),
        "competitive_rank": data.get("competitive_rank"),
        "computed_mmr": data.get("computed_mmr"),
        "computed_mmr_turbo": data.get("computed_mmr_turbo"),
        "mmr_estimate": data.get("mmr_estimate"),
        "aliases": data.get("aliases") or [],
    }


def _read_cached_or_fetch(cache_path, url, ttl, label):
    folder = cache_path.parent
    folder.mkdir(parents=True, exist_ok=True)
    now = time.time()

    if cache_path.exists():
        age = now - cache_path.stat().st_mtime
        if age < ttl:
            return read_json(cache_path)

    log(f"OpenDota fetch: {label} -> {url}")
    try:
        data = http_get_json(url)
        write_json(cache_path, data)
        return data
    except urllib.error.HTTPError as e:
        if e.code == 404:
            # 404 не кэшируем — перебрасываем наверх, чтобы вернуть 404 клиенту.
            raise
        log(f"OpenDota error for {label} ({url}): HTTP {e.code}")
        if cache_path.exists():
            log(f"Returning stale cache for {label}")
            return read_json(cache_path)
        raise
    except Exception as e:
        log(f"OpenDota error for {label} ({url}): {e}")
        if cache_path.exists():
            log(f"Returning stale cache for {label}")
            return read_json(cache_path)
        raise


def get_player_profile(account_id):
    """Вернуть нормализованный профиль игрока (с кэшем на диске)."""
    folder = get_player_dir(account_id)
    cache_path = folder / "profile.json"
    raw = _read_cached_or_fetch(
        cache_path,
        f"{OPENDOTA_BASE}/players/{account_id}",
        PROFILE_CACHE_TTL,
        f"profile {account_id}",
    )
    return normalize_profile(raw)


def get_player_matches(account_id, limit=20, offset=0, include_turbo=False):
    """Вернуть страницу матчей игрока (с кэшем на диске).

    По умолчанию Turbo (game_mode=23) скрыт, как на профиле. Когда
    include_turbo=True — отдаём историю вместе с Turbo-матчами. Для скрытого
    Turbo добираем несколько батчей, чтобы страницы не становились пустыми
    из-за отфильтрованных Turbo-игр.
    """
    limit = max(1, min(100, int(limit)))
    offset = max(0, int(offset))
    folder = get_player_dir(account_id)

    if include_turbo:
        cache_path = folder / f"matches_{limit}_{offset}_turbo.json"
        return _read_cached_or_fetch(
            cache_path,
            f"{OPENDOTA_BASE}/players/{account_id}/matches?limit={limit}&offset={offset}&significant=0",
            MATCHES_CACHE_TTL,
            f"matches {account_id} offset {offset} turbo",
        )

    wanted = limit
    logical_skipped = 0
    api_offset = 0
    results = []
    batch_size = 100

    # Верхний предел защищает от бесконечного цикла, если OpenDota меняет ответ.
    while len(results) < wanted and api_offset < offset + 1000:
        cache_path = folder / f"matches_{batch_size}_{api_offset}_no_turbo.json"
        batch = _read_cached_or_fetch(
            cache_path,
            f"{OPENDOTA_BASE}/players/{account_id}/matches?limit={batch_size}&offset={api_offset}&significant=0",
            MATCHES_CACHE_TTL,
            f"matches {account_id} offset {api_offset}",
        )
        if not isinstance(batch, list) or not batch:
            break

        for match in batch:
            if not isinstance(match, dict) or int(match.get("game_mode") or 0) == 23:
                continue
            if logical_skipped < offset:
                logical_skipped += 1
                continue
            results.append(match)
            if len(results) >= wanted:
                break

        if len(batch) < batch_size:
            break
        api_offset += batch_size

    return results


def get_player_wl(account_id, include_turbo=False):
    """Общая статистика побед/поражений.

    include_turbo=True добавляет significant=0, чтобы Turbo тоже попадал
    в победы/поражения.
    """
    folder = get_player_dir(account_id)
    suffix = "turbo" if include_turbo else "default"
    cache_path = folder / f"wl_{suffix}.json"
    query = "?significant=0" if include_turbo else ""
    try:
        return _read_cached_or_fetch(
            cache_path,
            f"{OPENDOTA_BASE}/players/{account_id}/wl{query}",
            MATCHES_CACHE_TTL,
            f"wl {account_id} {suffix}",
        )
    except Exception as e:
        log(f"OpenDota wl error for {account_id}: {e}")
        return {}


def get_player_heroes(account_id, include_turbo=False):
    """Статистика по героям (игры, победы, KDA). [] при ошибке."""
    folder = get_player_dir(account_id)
    suffix = "turbo" if include_turbo else "default"
    cache_path = folder / f"heroes_{suffix}.json"
    query = "?significant=0" if include_turbo else ""
    try:
        data = _read_cached_or_fetch(
            cache_path,
            f"{OPENDOTA_BASE}/players/{account_id}/heroes{query}",
            MATCHES_CACHE_TTL,
            f"heroes {account_id} {suffix}",
        )
        return data if isinstance(data, list) else []
    except Exception as e:
        log(f"OpenDota heroes error for {account_id}: {e}")
        return []


def get_player_totals(account_id):
    """Суммарные показатели (kills, gpm, xpm и т.д.). [] при ошибке."""
    folder = get_player_dir(account_id)
    cache_path = folder / "totals.json"
    try:
        data = _read_cached_or_fetch(
            cache_path,
            f"{OPENDOTA_BASE}/players/{account_id}/totals",
            MATCHES_CACHE_TTL,
            f"totals {account_id}",
        )
        return data if isinstance(data, list) else []
    except Exception as e:
        log(f"OpenDota totals error for {account_id}: {e}")
        return []



def get_player_page_data(account_id, include_turbo=False):
    """Aggregated profile payload for the PHP player page.

    The frontend used to call profile, matches, wl and heroes as separate local
    HTTP requests. This endpoint prepares the same data in one API request and
    fetches independent OpenDota-backed resources concurrently on cold cache.
    """
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
        future_profile = executor.submit(get_player_profile, account_id)
        future_matches = executor.submit(get_player_matches, account_id, 100, 0, include_turbo)
        future_wl = executor.submit(get_player_wl, account_id, include_turbo)
        future_heroes = executor.submit(get_player_heroes, account_id, include_turbo)

        profile = future_profile.result()
        matches = future_matches.result()
        try:
            wl = future_wl.result()
        except Exception as exc:
            log(f"OpenDota wl page-data error for {account_id}: {exc}")
            wl = {}
        try:
            heroes = future_heroes.result()
        except Exception as exc:
            log(f"OpenDota heroes page-data error for {account_id}: {exc}")
            heroes = []

    return {
        "profile": profile,
        "matches": matches if isinstance(matches, list) else [],
        "wl": wl if isinstance(wl, dict) else {},
        "heroes": heroes if isinstance(heroes, list) else [],
    }

def search_players(query):
    """Поиск игроков по нику. Без кэша — каждый запрос уникален."""
    if not query:
        return []
    log(f"OpenDota fetch: search -> {query}")
    try:
        # Поиск OpenDota часто отвечает по 20+ секунд, поэтому
        # ставим короткий таймаут: лучше вернуть [], чем держать клиента.
        return http_get_json(f"{OPENDOTA_BASE}/search?q={urllib.parse.quote(query)}", timeout=8)
    except Exception as e:
        log(f"OpenDota search error: {e}")
        return []


# ----------------------------------------------------------------------
# Локальный индекс игроков, собранный из распарсенных матчей.
# OpenDota-поиск ненадёжен (медленный, часто пустой, рейт-лимитит),
# поэтому ищем по тому, что ��же есть на диске — мгновенно и офлайн.
# ----------------------------------------------------------------------

def _empty_index():
    return {"players": {}, "built_at": 0, "sources": 0}


def get_players_index():
    """Вернуть индекс, собирая его при первом обращении."""
    with _index_lock:
        if not PLAYERS_INDEX_PATH.exists():
            log("Players index missing, building from parsed matches…")
            index = _build_players_index()
            write_json(PLAYERS_INDEX_PATH, index)
            return index
        try:
            return read_json(PLAYERS_INDEX_PATH)
        except Exception as e:
            log(f"Failed to read players index ({e}), rebuilding…")
            index = _build_players_index()
            write_json(PLAYERS_INDEX_PATH, index)
            return index


def rebuild_players_index():
    """Принудительно пересобрать индекс (например, по запросу админа)."""
    with _index_lock:
        index = _build_players_index()
        write_json(PLAYERS_INDEX_PATH, index)
        log(f"Players index rebuilt: {len(index['players'])} players from {index['sources']} matches")
        return index


def _build_players_index():
    """Пройтись по data/matches/*/match.json и собрать account_id → personaname."""
    index = _empty_index()
    if not DATA_DIR.exists():
        return index

    for match_dir in DATA_DIR.iterdir():
        if not match_dir.is_dir():
            continue
        match_json = match_dir / "match.json"
        if not match_json.exists():
            continue
        try:
            match = read_json(match_json)
        except Exception as e:
            log(f"Skip {match_dir.name}: {e}")
            continue

        match_id = str(match.get("match_id") or match_dir.name)
        start_time = int(match.get("start_time") or 0)
        for player in match.get("players") or []:
            account_id = player.get("account_id")
            if not account_id:
                continue
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                continue
            if account_id <= 0:
                # Анонимный игрок без account_id — пропускаем.
                continue

            key = str(account_id)
            personaname = (player.get("personaname") or "").strip()
            name = (player.get("name") or "").strip()
            existing = index["players"].get(key)
            if existing is None or start_time >= existing.get("last_seen", 0):
                index["players"][key] = {
                    "account_id": account_id,
                    "personaname": personaname or (existing["personaname"] if existing else ""),
                    "name": name or (existing["name"] if existing else ""),
                    "last_match_id": match_id,
                    "last_seen": start_time,
                }
        index["sources"] += 1

    index["built_at"] = int(time.time())
    return index


def update_index_with_match(match_id, match_data):
    """Добавить в индекс игроков из только что распарсенного матча."""
    with _index_lock:
        if PLAYERS_INDEX_PATH.exists():
            try:
                index = read_json(PLAYERS_INDEX_PATH)
            except Exception:
                index = _empty_index()
        else:
            index = _empty_index()

        start_time = int(match_data.get("start_time") or 0)
        players = match_data.get("players") or []
        for player in players:
            account_id = player.get("account_id")
            if not account_id:
                continue
            try:
                account_id = int(account_id)
            except (TypeError, ValueError):
                continue
            if account_id <= 0:
                continue

            key = str(account_id)
            personaname = (player.get("personaname") or "").strip()
            name = (player.get("name") or "").strip()
            existing = index["players"].get(key)
            if existing is None or start_time >= existing.get("last_seen", 0):
                index["players"][key] = {
                    "account_id": account_id,
                    "personaname": personaname or (existing["personaname"] if existing else ""),
                    "name": name or (existing["name"] if existing else ""),
                    "last_match_id": str(match_id),
                    "last_seen": start_time,
                }

        index["built_at"] = int(time.time())
        index["sources"] = (index.get("sources") or 0) + 1
        write_json(PLAYERS_INDEX_PATH, index)


def _score_player(player, query_lower, query_raw):
    """Чем больше очков, тем выше в выдаче."""
    pid = str(player.get("account_id") or "")
    name = (player.get("personaname") or "").strip()
    name_lower = name.lower()
    score = 0

    if query_raw.isdigit() and pid == query_raw:
        return 1000  # точный account_id — наивысший приоритет

    if name_lower == query_lower:
        score += 500
    if name_lower.startswith(query_lower):
        score += 200
    if query_lower in name_lower:
        score += 50
    if name and name[0].lower() == query_lower[:1]:
        score += 5
    return score


def search_players_local(query, limit=20):
    """Поиск по локальному индексу. Возвращает список в формате OpenDota-поиска."""
    query = (query or "").strip()
    if not query:
        return []
    index = get_players_index()
    query_lower = query.lower()

    scored = []
    for key, player in index.get("players", {}).items():
        score = _score_player(player, query_lower, query)
        if score > 0:
            scored.append((score, player))
    scored.sort(key=lambda x: (-x[0], -(x[1].get("last_seen") or 0)))

    results = []
    for score, player in scored[:limit]:
        results.append({
            "account_id": player.get("account_id"),
            "personaname": player.get("personaname", ""),
            "name": player.get("name", ""),
            "avatarfull": None,
            "last_match_time": player.get("last_seen") or None,
            "last_match_id": player.get("last_match_id"),
            "similarity": min(1.0, score / 200.0),
            "source": "local",
        })
    return results
