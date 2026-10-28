import test from 'node:test';
import assert from 'node:assert/strict';
import annotate from '../processors/teamfightParticipation.mjs';
import processTeamfights from '../processors/processTeamfights.mjs';
const meta = {hero_to_slot:Object.fromEntries(Array.from({length:10},(_,i)=>['hero'+i,i]))};
const makeFight = () => ({start:0,end:30,players:Array.from({length:10},()=>({deaths:0,killed:{},damage:0}))});
const damage = {type:'damage',time:10,slot:0,key:'hero5',value:100,targethero:true,targetillusion:false};
test('passive gold, XP, self-healing, buyback and generic uses do not establish participation',()=>{
 const f=makeFight(); annotate(f,[{type:'gold_reasons',time:10,slot:1,value:100},{type:'healing',time:10,slot:1,key:'hero1',targethero:true,value:400},{type:'item_uses',time:10,slot:1,key:'tango'},{type:'buyback_log',time:10,slot:1}],meta);
 assert.equal(f.players[1].participated,false);
});
test('attacker and incoming-damage-only victim both participate',()=>{
 const f=makeFight(); annotate(f,[damage],meta); assert.equal(f.players[0].participated,true); assert.equal(f.players[5].participated,true); assert.equal(f.players[5].damage_taken,100);
});
test('healing an engaged ally includes the support, excluding self-healing',()=>{
 const f=makeFight(); annotate(f,[damage,{type:'healing',time:9,slot:1,key:'hero0',targethero:true,value:60},{type:'healing',time:11,slot:1,key:'hero1',targethero:true,value:200}],meta);
 assert.equal(f.players[1].participated,true); assert.equal(f.players[1].combat_healing,60);
});
test('healing a disconnected ally does not seed participation',()=>{
 const f=makeFight(); annotate(f,[damage,{type:'healing',time:9,slot:2,key:'hero3',targethero:true,value:60}],meta); assert.equal(f.players[2].participated,false);
});
test('targeted enemy ability confirms zero-damage support',()=>{
 const f=makeFight(); annotate(f,[{type:'ability_targets',time:10,slot:2,key:['stun','hero6']}],meta); assert.equal(f.players[2].participated,true); assert.equal(f.players[6].participated,true);
});
test('out-of-window events and illusion hits do not count',()=>{
 const f=makeFight(); annotate(f,[{...damage,time:31},{...damage,targetillusion:true}],meta); assert.equal(f.players[0].participated,false);
});
test('deaths count even without position samples',()=>{
 const entries=[5,6,7].map((slot,i)=>({type:'killed',time:20+i,slot:0,key:'hero'+slot,targethero:true,targetillusion:false,value:1}));
 entries.push({type:'interval',time:37,slot:0,x:0,y:0});
 const fights=processTeamfights(entries,meta); assert.equal(fights.length,1); assert.equal(fights[0].players[5].deaths,1); assert.equal(fights[0].players[5].participated,true);
});
