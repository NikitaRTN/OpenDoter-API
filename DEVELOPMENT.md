# Local API startup

Run `python server.py` (Python 3.10+). The default API port is 8080; override it with `PORT`.

- `GET /health`: HTTP 200 JSON with `service: OpenDoter API` and `status: ok`.
- `GET /`: the same service identity plus instructions for opening the separate PHP site.
- Unknown paths still return HTTP 404 JSON. Existing API endpoints are unchanged.

These endpoints check HTTP-server liveness only, not OpenDota connectivity or parser readiness. They do not download data or invoke the parser.

The API is not the PHP frontend. Start `run-all.bat` in the OpenDoter site repository and use the exact site URL printed by its launcher. The launcher can select another port if Windows reserves port 8000.

Regression tests (standard library only, no external API requests):

```bash
python -m unittest discover -s tests -v
```

On Windows the API uses an exclusive listening socket. A second API instance fails with a clear startup error instead of silently sharing the port with an older instance. Restart the previous OpenDoter API process before running the updated version.

## Replay compression

Before parsing replays, install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

Valve replay URLs may end with `.dem.bz2` even when their contents use Zstandard. The API detects BZip2, Zstandard and uncompressed demos from their signatures, not filenames. Decoding is incremental and the `.dem` is replaced atomically only after successful decompression and demo-header validation. Cached archives are reused; a format mismatch does not require downloading the replay again.

A truncated archive, unknown response format or decoded non-demo produces a specific error and never replaces a previously valid `.dem`. Original archives remain available for diagnostics. Restart the API after updating its code or dependencies.
## Teamfight participation

`processors/teamfightParticipation.mjs` adds `participated`, `damage_taken` and `combat_healing` to each teamfight player. Participation requires a hero kill/death, damage dealt/received against an enemy hero, a targeted enemy ability, or healing another engaged ally. Passive gold/XP, buybacks, generic casts and self-healing alone are not evidence. Healing-only groups cannot seed participation.

The PHP frontend hides players with `participated: false` before computing displayed team totals. Existing matches must be reprocessed to populate the new fields; older blobs use a conservative kills/deaths/damage fallback. Fight boundaries remain the existing death-cluster heuristic and can span separate locations.

Run the focused processor regression tests with Node.js:

```bash
node --test tests/teamfightParticipation.test.mjs
```

## Native damage-reduction counters

The Java extractor now reads `m_vecDataTeam.<teamSlot>.m_flDamageByTypeReceivedPreReduction.<type>` and `...PostReduction.<type>` from the Radiant/Dire data entities at each interval. It preserves the three original fractional counters. Both the Node blob builder and direct Java blob builder select the latest complete snapshot for each player, convert each type counter to an integer before summing, and export `damage_received_pre_reduction`, `damage_received_post_reduction`, `damage_prevented`, `damage_reduction_pct`, source and snapshot time. Do not sum intervals or substitute combat-log damage/ending armor. Missing values stay unavailable; a zero denominator has a null percentage; amplification is not silently clamped.

Rebuild the Java jar and restart the Java parser after pulling these changes. Already cached JSONL/blob files must be regenerated from the `.dem` to acquire the new counters; no replay re-download is needed. The client-reference fixture for match 9064491290 is 131612 / 58490 for Dragon Knight, yielding 55.6%, with no match-specific correction factor.

```bash
node --test tests/damageReduction.test.mjs tests/teamfightParticipation.test.mjs
javac -proc:none -cp target/stats-0.1.0.jar -d target/test-classes tests/java/opendota/DamageReductionTest.java
java -cp "target/test-classes:target/stats-0.1.0.jar" opendota.DamageReductionTest
```

Use `;` instead of `:` in the Java classpath on Windows.
