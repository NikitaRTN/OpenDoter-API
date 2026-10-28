import test from 'node:test';
import assert from 'node:assert/strict';
import details from '../processors/teamfightDetails.mjs';
const meta={hero_to_slot:{hero0:0,hero5:5}};
const fight=()=>({start:10,end:20,players:Array.from({length:10},()=>({participated:true}))});
test('uses retain timestamps, targets and equal-second source order; no aggregate inference',()=>{
 const f=fight();details(f,[{type:'item_uses',time:11,slot:5,player_slot:128,key:'blink'},{type:'ability_uses',time:11,slot:5,player_slot:128,key:'stun',targetname:'hero0'},{type:'item_uses',time:21,slot:0,key:'wand'},{type:'ability_targets',time:11,slot:5,key:['stun','hero0']}],meta);
 assert.equal(f.actions.length,2);assert.equal(f.actions[0].key,'blink');assert.equal(f.actions[1].target_slot,0);assert.equal(f.actions[0].slot,5);assert.ok(f.actions[0].sequence<f.actions[1].sequence);
});
test('incoming sources exclude illusions, allies and out-of-window hits',()=>{
 const f=fight();const hit={type:'damage',time:12,slot:0,key:'hero5',value:55,targethero:true};
 details(f,[hit,{...hit,targetillusion:true},{...hit,time:9},{...hit,slot:5}],meta);
 assert.deepEqual(f.players[5].damage_sources,{'0':55});assert.deepEqual(f.players[0].damage_targets,{'5':55});
});
test('nonparticipants and illusion casts absent, unattributed death retained',()=>{
 const f=fight();f.players[0].participated=false;
 details(f,[{type:'item_uses',time:11,slot:0,key:'tango'},{type:'ability_uses',time:11,slot:5,key:'stun',attackerillusion:true},{type:'killed',time:12,key:'hero5',targethero:true}],meta);
 assert.equal(f.actions.length,1);assert.equal(f.actions[0].slot,null);assert.equal(f.actions[0].target_slot,5);
});
