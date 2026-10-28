import test from 'node:test';
import assert from 'node:assert/strict';
import processDamageReduction from '../processors/processDamageReduction.mjs';
const entry = (pre,post,time=1,slot=0) => ({type:'interval',slot,time,damage_received_pre_reduction_by_type:pre,damage_received_post_reduction_by_type:post});
const run = entries => {const players=[{},{}];processDamageReduction(entries,players);return players;};
test('native Dragon Knight counters match the client reference without calibration',()=>{
 const p=run([entry([66578.9453125,62826.953125,2208.75],[19503,36985,2002])])[0];
 assert.equal(p.damage_received_pre_reduction,131612);assert.equal(p.damage_received_post_reduction,58490);
 assert.equal(p.damage_prevented,73122);assert.equal(p.damage_reduction_pct.toFixed(1),'55.6');
});
test('latest cumulative snapshot wins, not sum of snapshots or input order',()=>{
 const p=run([entry([100,0,0],[50,0,0],2),entry([20,0,0],[10,0,0],1)])[0];
 assert.equal(p.damage_received_pre_reduction,100);assert.equal(p.damage_reduction_time,2);
});
test('zero damage is available but percentage is undefined',()=>{
 const p=run([entry([0,0,0],[0,0,0])])[0];assert.equal(p.damage_prevented,0);assert.equal(p.damage_reduction_pct,null);
});
test('missing, partial and invalid snapshots cannot become a fabricated percentage',()=>{
 for(const pre of [undefined,[1,2],[1,null,2],[1,NaN,2],[-1,0,0],[1,Infinity,2]])assert.equal(run([entry(pre,[0,0,0])])[0].damage_reduction_pct,undefined);
});
test('invalid later snapshot preserves last complete data, slots are independent',()=>{
 const p=run([entry([100,0,0],[80,0,0]),entry([200,0,0],[50,0,0],2,1),entry([300,0],[60,0,0],3)]);
 assert.equal(p[0].damage_received_pre_reduction,100);assert.equal(p[1].damage_reduction_pct,75);
});
test('amplification remains negative rather than silently clamped',()=>{
 assert.ok(Math.abs(run([entry([100,0,0],[120,0,0])])[0].damage_reduction_pct+20)<1e-10);
});
test('no source fields in old events remains unavailable',()=>{
 assert.equal(run([{type:'interval',time:1,slot:0}])[0].damage_reduction_pct,undefined);
});
