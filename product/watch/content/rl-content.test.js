import test from 'node:test';
import assert from 'node:assert/strict';
import { rlMovieState, evidenceScope } from './content-panel.js';
const scout = {available:true,trainedModelUsed:true,selectionVerified:true,lineageVerified:true,actualRL:true,modelInvoked:true,modelInvokedThisRequest:true,invocationMode:'live',threeLayersCovered:true,evidence:[{evidenceId:'basic'},{evidenceId:'advanced'},{evidenceId:'depth'}]};
const story = {enhancedAvailable:true,scout,rlVideoUse:{narrativeUsed:true,burnedIntoVideo:true,evidenceIdsUsed:['basic','advanced','depth']}};
test('standalone model success and legacy movies cannot claim burned RL',()=>{
 assert.equal(rlMovieState({}).inMovie,false);
 assert.equal(rlMovieState({...story,rlVideoUse:{}}).inMovie,false);
 assert.equal(rlMovieState({...story,rlVideoUse:{...story.rlVideoUse,evidenceIdsUsed:['basic']}}).inMovie,false);
 assert.equal(rlMovieState(story).inMovie,true);
});
test('replayed service and real current model call have distinct provenance',()=>{
 assert.match(rlMovieState(story).invocation,/实时调用/);
 assert.match(rlMovieState({...story,scout:{...scout,invocationMode:'recorded_live_replay',modelInvokedThisRequest:false}}).invocation,/回放/);
 assert.equal(rlMovieState({...story,scout:{...scout,lineageVerified:false}}).verified,false);
});
test('whole-game and season cards retain distinct statistical scopes',()=>{
 assert.match(evidenceScope({grain:'player-game',gameId:'game'},{}),/本场赛后统计/);
 assert.match(evidenceScope({grain:'player-season',periodRef:'p'},{rlEvidencePeriods:{p:{season:'2025-26'}}}),/2025-26.*非本回合测量/);
});
