"""Filtered player history and transparent, heuristic OD Impact v1 (not MMR)."""
import hashlib
import math
import time
import urllib.parse
from collections import Counter
from .players import get_player_dir, _read_cached_or_fetch

FIELDS = ('match_id player_slot radiant_win hero_id start_time duration game_mode lobby_type patch region kills deaths assists gold_per_min xp_per_min hero_damage tower_damage hero_healing lane_role stuns obs_placed sen_placed').split()
FILTERS = {'hero_id': (1, 2000), 'is_radiant': (0, 1), 'win': (0, 1), 'lane_role': (1, 4), 'patch': (1, 1000), 'game_mode': (1, 100), 'lobby_type': (0, 20), 'date': (1, 3650), 'region': (1, 50)}
WEIGHTS = {'combat': 20, 'survival': 20, 'damage': 20, 'push': 15, 'economy': 15, 'support': 10}

def number(row, field):
    v = row.get(field)
    return float(v) if isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v) and v >= 0 else None

def impact_score(row):
    """Missing is not zero; unknown role explicitly lowers confidence, not score."""
    duration = number(row, 'duration')
    if not duration or duration < 300:
        return {'score': None, 'coverage': 0, 'components': {}, 'version': 'v1', 'role_known': False}
    minutes = duration / 60
    turbo = row.get('game_mode') == 23
    role = row.get('lane_role')
    weights = dict(WEIGHTS)
    parts = {}
    k, d, a = (number(row, x) for x in ('kills', 'deaths', 'assists'))
    if None not in (k, d, a):
        ratio = (k + a) / max(1, d)
        parts['combat'] = ratio / (ratio + 3)
        parts['survival'] = 1 / (1 + (10 * d / minutes) / 1.5)
    hd, td = number(row, 'hero_damage'), number(row, 'tower_damage')
    if hd is not None:
        rate = hd / minutes
        parts['damage'] = rate / (rate + (900 if turbo else 600))
    if td is not None:
        rate = td / minutes
        parts['push'] = rate / (rate + (150 if turbo else 75))
    econ = []
    for field, baseline in [('gold_per_min', 450), ('xp_per_min', 600)]:
        v = number(row, field)
        if v is not None:
            econ.append(v / (v + baseline * (2 if turbo else 1)))
    if econ:
        parts['economy'] = sum(econ) / len(econ)
        weights['economy'] *= len(econ) / 2
    support = []
    for field, baseline in [('hero_healing', 100), ('stuns', 1.5), ('obs_placed', .2)]:
        v = number(row, field)
        if v is not None:
            rate = v / minutes
            support.append(rate / (rate + baseline))
    if support:
        parts['support'] = sum(support) / len(support)
        weights['support'] *= len(support) / 3
    coverage = sum(weights[k] for k in parts)
    score = round(1000 * sum(parts[k] * weights[k] for k in parts) / coverage) if coverage >= 60 and 'combat' in parts else None
    return {'score': score, 'coverage': round(coverage), 'role_known': role in (1, 2, 3, 4), 'components': {k: {'score': round(1000*v), 'weight': weights[k]} for k, v in parts.items()}, 'version': 'v1'}

def parse_filters(qs):
    out = {}
    for key, (low, high) in FILTERS.items():
        raw = qs.get(key, [''])[0]
        if raw in ('', None):
            continue
        try:
            value = int(raw)
        except (TypeError, ValueError):
            raise ValueError('Invalid filter: ' + key)
        if not low <= value <= high:
            raise ValueError('Filter out of range: ' + key)
        out[key] = value
    return out

def summarize(rows):
    scores = [impact_score(x) for x in rows]
    rated = [x for x in scores if x['score'] is not None]
    total_minutes = sum((number(x, 'duration') or 0) / 60 for x in rows)
    out = {'games': len(rows), 'wins': sum(bool(x.get('radiant_win')) == (int(x.get('player_slot', 0)) < 128) for x in rows), 'minutes': total_minutes, 'rated_games': len(rated), 'impact': round(sum(x['score'] for x in rated)/len(rated)) if rated else None, 'coverage': round(sum(x['coverage'] for x in rated)/len(rated)) if rated else 0, 'roles_known': sum(x['role_known'] for x in scores), 'components': {}, 'modes': dict(Counter(str(x.get('game_mode')) for x in rows))}
    for metric, field in [('hero_dpm', 'hero_damage'), ('tower_dpm', 'tower_damage')]:
        eligible = [x for x in rows if number(x, field) is not None and (number(x, 'duration') or 0) > 0]
        minutes = sum(x['duration']/60 for x in eligible)
        out[metric] = sum(x[field] for x in eligible)/minutes if minutes else None
        out[metric + '_games'] = len(eligible)
    for key in WEIGHTS:
        vals = [s['components'][key]['score'] for s in rated if key in s['components']]
        out['components'][key] = {'score': round(sum(vals)/len(vals)) if vals else None, 'games': len(vals)}
    return out

def get_player_insights(account_id, qs):
    filters = parse_filters(qs)
    try:
        page = min(10000, max(1, int(qs.get('page', ['1'])[0])))
    except (ValueError, TypeError):
        raise ValueError('Invalid page')
    folder = get_player_dir(account_id)
    refresh = qs.get('refresh', ['0'])[0] == '1'
    def fetch_batch(offset, limit):
        args = [('significant', 0), ('limit', limit), ('offset', offset)] + sorted(filters.items()) + [('project', x) for x in FIELDS]
        encoded = urllib.parse.urlencode(args)
        path = folder / ('insights_v1_' + hashlib.sha256(encoded.encode()).hexdigest()[:24] + '.json')
        data = _read_cached_or_fetch(path, 'https://api.opendota.com/api/players/' + str(account_id) + '/matches?' + encoded, 0 if refresh else 300, 'filtered profile history')
        if not isinstance(data, list):
            raise RuntimeError('Unexpected OpenDota history response')
        return data, path
    sample, cache_path = fetch_batch(0, 100)
    offset = (page - 1) * 25
    if offset + 25 < len(sample) or len(sample) < 100:
        batch = sample[offset:offset+26]
    else:
        batch, _ = fetch_batch(offset, 26)
    rows = []
    for m in batch[:25]:
        row = dict(m)
        row['impact'] = impact_score(row)
        rows.append(row)
    patches = []
    try:
        patches = _read_cached_or_fetch(folder.parent / '_patches.json', 'https://api.opendota.com/api/constants/patch', 21600, 'patch names')
        if not isinstance(patches, list):
            patches = []
    except Exception:
        pass
    age = max(0, time.time() - cache_path.stat().st_mtime) if cache_path.exists() else None
    return {'account_id': str(account_id), 'page': page, 'per_page': 25, 'has_next': len(batch) > 25, 'matches': rows, 'summary': summarize(sample), 'filters': filters, 'patches': [{'id': x.get('id'), 'name': x.get('name')} for x in patches if isinstance(x, dict)], 'cache': {'age_seconds': round(age) if age is not None else None, 'ttl_seconds': 300, 'stale': age is not None and age >= 300}, 'rating_version': 'OD Impact v1', 'sample_limit': 100}
