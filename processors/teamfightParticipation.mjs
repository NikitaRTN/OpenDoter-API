/** Confirm participation from hero interactions, not income or self-healing. */
export default function annotateTeamfightParticipation(fight, entries, meta) {
  const slotFor = (name) => meta.hero_to_slot[name];
  const valid = (slot) => Number.isInteger(slot) && !!fight.players[slot];
  const enemies = (a, b) => valid(a) && valid(b) && Math.floor(a / 5) !== Math.floor(b / 5);
  const mark = (slot) => { if (valid(slot)) fight.players[slot].participated = true; };
  for (const p of fight.players) {
    p.participated = p.deaths > 0 || Object.values(p.killed || {}).some(n => n > 0);
    p.damage_taken = 0;
    p.combat_healing = 0;
  }
  const heals = [];
  for (const e of entries) {
    if (e.time < fight.start || e.time > fight.end) continue;
    const target = slotFor(e.key);
    if (e.type === 'damage' && e.targethero && !e.targetillusion && e.value > 0 && enemies(e.slot, target)) {
      mark(e.slot); mark(target);
      fight.players[target].damage_taken += e.value;
    } else if (e.type === 'killed' && e.targethero && !e.targetillusion) {
      mark(e.slot); mark(target);
    } else if (e.type === 'ability_targets' && Array.isArray(e.key)) {
      const victim = slotFor(e.key[1]);
      if (enemies(e.slot, victim)) { mark(e.slot); mark(victim); }
    } else if (e.type === 'healing' && e.targethero && !e.targetillusion && e.value > 0
      && valid(e.slot) && valid(target) && e.slot !== target && Math.floor(e.slot / 5) === Math.floor(target / 5)) {
      heals.push({source: e.slot, target, value: e.value});
    }
  }
  // A healer supporting an engaged ally participates too. No disconnected
  // self-healing / healing-only group can seed participation on its own.
  for (let pass = 0; pass < fight.players.length; pass++) {
    let changed = false;
    for (const h of heals) {
      if (fight.players[h.target].participated && !fight.players[h.source].participated) {
        mark(h.source); changed = true;
      }
    }
    if (!changed) break;
  }
  for (const h of heals) {
    if (fight.players[h.target].participated) fight.players[h.source].combat_healing += h.value;
  }
}
