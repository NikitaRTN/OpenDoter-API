# Detailed profiles and OD Impact v1

- Default profile history includes Turbo (`significant=0`). Hero, side, result, lane, patch, mode, lobby, rolling days, and region filters are passed to OpenDota before pagination; filters are not limited to loaded rows.
- `GET /api/players/{id}/insights` returns 25 rows, has-next, a fixed recent-100 filtered summary, patch labels and explicit cache age/staleness. Same-origin PHP proxy: `/players/{id}?data=insights&...`.
- All played heroes are listed from the lifetime heroes endpoint. Search, sortable games/wins/winrate and click-to-filter; hero totals include all modes and do not change with history filters.
- Pagination/filtering updates the history workspace via fetch and History API, with abort/sequence guards, back/forward support, bounded 5-minute sessionStorage cache, loading/error/empty states. Profile header is unchanged during pagination.
- Existing backend cache: profile 1 hour, history 5 minutes; existing PHP profile-context cache 5 minutes. New history cache keys include all filters, offset, limit and projection. `refresh=1` bypasses the history TTL. Failed refresh uses stale backend cache with an explicit warning. A history refresh does not claim to refresh lifetime hero/profile totals.

## Rating contract

Experimental heuristic, **not MMR, percentile, calibrated skill ranking or intent detection**. Winner gets no automatic bonus. Not role-adjusted: lane_role identifies a lane/roaming, never core vs support. Unknown metrics are excluded, not imputed as zero. Unparsed profiles can lack control/wards, which is reflected in coverage. No tanking score is inferred from armor or from one parsed match.

Per-match component f(x,b)=x/(x+b), points=round(1000*sum(weight*component)/sum(available weights)):

| Component | Weight | Input and reference |
|---|---:|---|
| Combat |20|KDA=(K+A)/max(1,D), reference 3|
| Survival |20|1/(1+(deaths/10 minutes)/1.5)|
| Hero damage |20|Damage/min, reference 600 (Turbo 900)|
| Push |15|Building damage/min, reference 75 (Turbo 150)|
| Economy |15|Mean f(GPM,450), f(XPM,600); double references in Turbo|
| Support |10|Mean f(healing/min,100), f(stun seconds/min,1.5), f(observer wards/min,0.2)|

Economy/support weights scale by availability (out of 2/3 fields). At least 60 available weight and K/D/A required. Duration must be at least 5 minutes. Score bounds 0–1000. Approximately 500 means proximity to chosen references, not population median. References are hand-selected v1 and need later validation on hero/position/mode/rank cohorts. Coverage measures field availability, **not accuracy**.

Profile score is the mean of eligible match scores among the most recent 100 filtered matches, not lifetime. Component averages can have different denominators, shown by the API. The summary is independent of the current pagination page. Do not use this score as proof a player intentionally ruined a game, or compare mixed Turbo/normal aggregates as if game conditions matched.

## Tests

API: `python -m unittest discover -s tests` from parser-master. Tests cover score bounds, missing vs zero, short games, no win bonus, monotonicity, Turbo reference, lane-vs-role, filter zero values/validation, weighted rates and partial metric coverage.

Browser QA at 1440/390: real profile 1112027560; pagination without document reload, back navigation, Turbo+result filters, 114 lifetime heroes, hero search/sort/click, score breakdown, no page overflow/JS errors, deterministic empty/stale source fixtures.
