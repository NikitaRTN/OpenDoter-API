/** Real combat-log uses in source order; aggregate maps cannot reconstruct a sequence. */
export default function addTeamfightDetails(fight, entries, meta) {
  fight.actions = [];
  fight.actions_version = 1;
  fight.actions_time_precision = 'second';
  for (const p of fight.players) { p.damage_sources = {}; p.damage_targets = {}; }
  const valid = s => Number.isInteger(s) && !!fight.players[s];
  for (let sequence = 0; sequence < entries.length; sequence++) {
    const e = entries[sequence];
    if (!Number.isFinite(e.time) || e.time < fight.start || e.time > fight.end) continue;
    const target = meta.hero_to_slot[e.key];
    if (e.type === 'damage' && e.targethero && !e.targetillusion && e.value > 0 && valid(e.slot) && valid(target) && Math.floor(e.slot / 5) !== Math.floor(target / 5)) {
      const p = fight.players[target], a = fight.players[e.slot];
      p.damage_sources[e.slot] = (p.damage_sources[e.slot] || 0) + e.value;
      a.damage_targets[target] = (a.damage_targets[target] || 0) + e.value;
    }
    let kind, slot = e.slot, name = e.key, victim = null;
    if (e.type === 'ability_uses' || e.type === 'item_uses') {
      if (e.attackerillusion) continue;
      kind = e.type === 'ability_uses' ? 'ability' : 'item';
      if (Number.isInteger(e.player_slot)) slot = e.player_slot >= 128 ? e.player_slot - 123 : e.player_slot;
      if (typeof name !== 'string' || !name) continue;
      if (!e.targetillusion && Number.isInteger(meta.hero_to_slot[e.targetname])) victim = meta.hero_to_slot[e.targetname];
    } else if (e.type === 'killed' && e.targethero && !e.targetillusion) {
      kind = 'kill'; victim = target; name = null;
    } else if (e.type === 'buyback_log') { kind = 'buyback'; name = null; }
    else continue;
    // Include an unattributed death if the victim is a participant (e.g. tower kill).
    if (!(valid(slot) && fight.players[slot].participated) && !(kind === 'kill' && valid(victim) && fight.players[victim].participated)) continue;
    fight.actions.push({time:e.time, sequence, slot:valid(slot) ? slot : null, kind, key:name, target_slot:valid(victim) ? victim : null});
  }
  fight.actions.sort((a,b) => a.time - b.time || a.sequence - b.sequence);
}
