/** Native cumulative hero-damage counters: use the latest complete snapshot, never sum intervals. */
export default function processDamageReduction(entries, players) {
  const latest = new Map();
  const valid = v => Array.isArray(v) && v.length === 3 && v.every(n => typeof n === 'number' && Number.isFinite(n) && n >= 0);
  for (const e of entries) {
    if (e.type !== 'interval' || !Number.isInteger(e.slot) || !players[e.slot] || !Number.isFinite(e.time)) continue;
    const pre = e.damage_received_pre_reduction_by_type;
    const post = e.damage_received_post_reduction_by_type;
    if (!valid(pre) || !valid(post)) continue;
    if (latest.has(e.slot) && latest.get(e.slot).time > e.time) continue;
    latest.set(e.slot, {time: e.time, pre, post});
  }
  for (const [slot, e] of latest) {
    // Convert each type before summing; preserve original fractional arrays for auditing.
    const pre = e.pre.reduce((a,b) => a+Math.trunc(b), 0);
    const post = e.post.reduce((a,b) => a+Math.trunc(b), 0);
    Object.assign(players[slot], {
      damage_received_pre_reduction_by_type: e.pre,
      damage_received_post_reduction_by_type: e.post,
      damage_received_pre_reduction: pre,
      damage_received_post_reduction: post,
      damage_prevented: pre-post,
      damage_reduction_pct: pre > 0 ? 100*(1-post/pre) : null,
      damage_reduction_source: 'replay_team_damage_counters',
      damage_reduction_time: e.time,
    });
  }
}
