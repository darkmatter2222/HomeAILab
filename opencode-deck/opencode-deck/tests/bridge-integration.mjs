import assert from 'node:assert/strict';
import {Bridge, Facts} from '../plugins/core.mjs';
const facts = new Facts();
const bridge = new Bridge({registration:{id:'node-live',process:JSON.parse(process.env.TEST_PROCESS),label:'Node test'},
  readSnapshot:()=>facts.snapshot(),onError:error=>{throw Error(error)}});
await bridge.flush();
let status=await bridge.call('GET','/v1/status');
assert.equal(status.slots[0].state,'idle');
facts.event({type:'session.status',properties:{sessionID:'s',status:{type:'busy'}}});
facts.event({type:'permission.asked',properties:{sessionID:'s',id:'permission1'}});
await bridge.flush();
status=await bridge.call('GET','/v1/status');assert.equal(status.slots[0].state,'input');
// Losing broker registry is equivalent to a fresh broker's empty state;
// unchanged unresolved request must reappear from a full snapshot.
await bridge.call('DELETE','/v1/instances/node-live');
await bridge.flush();
status=await bridge.call('GET','/v1/status');assert.equal(status.slots[0].state,'input');
facts.event({type:'permission.replied',properties:{sessionID:'s',requestID:'permission1'}});
await bridge.flush();
status=await bridge.call('GET','/v1/status');assert.equal(status.slots[0].state,'running');
await bridge.close();
console.log('Real Node bridge -> HTTP -> Python registry: PASS');
// Exercise the actual conventional plugin entrypoint, not only its transport.
const fs = await import('node:fs/promises');
const path = await import('node:path');
const binding = path.join(process.env.OCDECK_HOME, 'integration.binding.json');
await fs.writeFile(binding, JSON.stringify({id:'server-plugin',process:JSON.parse(process.env.TEST_PROCESS),label:'Plugin test'}));
process.env.OCDECK_BINDING=binding;
const {DeckBridge}=await import('../plugins/server.mjs');
const hooks=await DeckBridge({client:{},directory:process.cwd()});
async function waitState(expected) {
 for(let i=0;i<100;i++){
   const value=await bridge.call('GET','/v1/status');
   if(value.slots[0].state===expected)return;
   await new Promise(r=>setTimeout(r,30));
 }
 assert.fail(`Plugin did not reach ${expected}`);
}
await waitState('idle');
await hooks.event({event:{type:'session.status',properties:{sessionID:'s',status:{type:'busy'}}}});
await waitState('running');
await hooks.event({event:{type:'question.asked',properties:{sessionID:'s',id:'q'}}});
await waitState('input');
await hooks.event({event:{type:'question.replied',properties:{sessionID:'s',requestID:'q'}}});
await hooks.event({event:{type:'session.idle',properties:{sessionID:'s'}}});
await waitState('idle');
await hooks.dispose();
await bridge.call('DELETE','/v1/instances/server-plugin');
console.log('Actual server plugin hooks -> broker colors: PASS');
// A reachable bridge must not turn a failed OpenCode snapshot into false idle.
let snapshotFails = true;
const recoveringHooks = await DeckBridge({client:{session:{status:async()=> {
  if(snapshotFails) return {error:{message:'temporary SDK failure'}};
  return {data:{s:{type:'busy'}}};
}}},directory:process.cwd()});
await waitState('unknown');
snapshotFails = false;
await new Promise(r=>setTimeout(r,4100));
await recoveringHooks.event({event:{type:'session.created',properties:{info:{id:'s'}}}});
await waitState('running');
await recoveringHooks.dispose();
await bridge.call('DELETE','/v1/instances/server-plugin');
console.log('Snapshot failure is unknown and recovers: PASS');
