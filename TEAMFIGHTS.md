# Teamfight detail schema

The parsed blob stores episode-scoped `damage_taken` (actual post-reduction damage from opposing heroes) and ally-only `combat_healing` per participant. Damage received is not a measure of tanking quality.

`teamfights[].actions_version = 1` identifies the chronological combat-log list `actions`, with `actions_time_precision = "second"`. Each entry contains `time`, original expanded-stream `sequence`, positional `slot` (0–9) or null, `kind` (`ability`, `item`, `kill`, `buyback`), `key` for uses, and `target_slot` (0–9) or null. Events are ordered by time then stream sequence. Logged applications need not equal keyboard presses. Participant filtering and fight window boundaries still apply.

Legacy blobs have no event order; totals cannot reconstruct it. The teamfight page can request a refresh from the match's saved `parsed.jsonl`. The server rebuilds into temporary files and atomically replaces only the `teamfights` field after validation, preserving the rest of the blob. If the saved event stream is absent or processing fails, the existing blob remains unchanged and the page reports the error. Normal parse requests still use the cache.
