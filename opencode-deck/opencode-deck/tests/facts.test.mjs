import test from 'node:test';
import assert from 'node:assert/strict';
import {Facts} from '../plugins/core.mjs';
const emit=(f,type,properties)=>f.event({type,properties});
test('pending requests survive idle and clear independently',()=>{
 const f=new Facts();
 emit(f,'permission.asked',{sessionID:'a',id:'p'});
 emit(f,'question.asked',{sessionID:'a',id:'q'});
 emit(f,'session.idle',{sessionID:'a'});
 assert.equal(f.snapshot().pending,2);
 emit(f,'permission.replied',{sessionID:'a',requestID:'p'});
 assert.equal(f.snapshot().pending,1);
 emit(f,'question.rejected',{sessionID:'a',requestID:'q'});
 assert.equal(f.snapshot().pending,0);
});
test('child idle cannot hide parent activity',()=>{
 const f=new Facts();
 emit(f,'session.status',{sessionID:'parent',status:{type:'busy'}});
 emit(f,'session.idle',{sessionID:'child'});
 assert.equal(f.snapshot().status,'busy');
});
test('duplicate requests do not increase count',()=>{
 const f=new Facts();
 for(let i=0;i<3;i++)emit(f,'question.asked',{sessionID:'a',id:'q'});
 assert.equal(f.snapshot().pending,1);
});
test('session error does not invent human input',()=>{
 const f=new Facts();emit(f,'session.error',{sessionID:'a'});
 assert.equal(f.snapshot().pending,0);
});
test('deleted sessions remove request state',()=>{
 const f=new Facts();emit(f,'question.asked',{sessionID:'a',id:'q'});
 emit(f,'session.deleted',{info:{id:'a'}});assert.equal(f.snapshot().pending,0);
});
