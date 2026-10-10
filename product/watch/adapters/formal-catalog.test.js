import test from 'node:test';
import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import {normalizeStory,sourceToOutputTime,outputToSourceTime,loadStoryRecord} from './catalog.js';

const source=JSON.parse(await readFile(new URL('../../data/formal-story.json',import.meta.url),'utf8')).stories[0];
const production={mode:'editorial',status:'local-render-ready',sourceSha256:source.sourceVideoSha256,
 outputSha256:'a'.repeat(64),durationSeconds:30,agentCoreUsedForThisRender:false,rlModelUsedForThisRender:false,
 preservesSourceTimeline:false,fullVideoAudioDecode:true,manifestUrl:'/product/media/formal/manifest.json',
 timeline:[{outputStart:0,outputEnd:2,sourceStart:0,sourceEnd:0,kind:'freeze'},
 {outputStart:2,outputEnd:10,sourceStart:0,sourceEnd:8,kind:'play'},
 {outputStart:10,outputEnd:14,sourceStart:8,sourceEnd:8,kind:'freeze'},
 {outputStart:14,outputEnd:26,sourceStart:8,sourceEnd:20,kind:'play'},
 {outputStart:26,outputEnd:30,sourceStart:12,sourceEnd:14,kind:'replay'}]};
const bound={...source,production,enhancedVideo:'/product/media/formal/enhanced.mp4'};
const base='http://127.0.0.1:4173/product/watch/';

test('formal movie separates official final shot from practice results and cloud jobs',()=>{
 const story=normalizeStory({...bound,scout:{trainedModelUsed:true},showcaseJobId:'b'.repeat(32)},base);
 assert.equal(story.enhancedAvailable,true);assert.equal(story.officialEvent.eventId,273);
 assert.equal(story.officialEvent.expectedFg,.3);assert.equal(story.scout,undefined);assert.equal(story.showcaseJobId,undefined);
 for(const patch of [{enhancedVideo:'https://example.com/video.mp4'},{production:{...production,agentCoreUsedForThisRender:true}},{production:{...production,sourceSha256:'c'.repeat(64)}}])assert.equal(normalizeStory({...bound,...patch},base).enhancedAvailable,false);
});
test('source anchors account for title and freeze without jumping to replay',()=>{
 const story=normalizeStory(bound,base);
 assert.equal(sourceToOutputTime(story,8),14);assert.equal(sourceToOutputTime(story,13),19);
 assert.equal(outputToSourceTime(story,12),8);assert.equal(outputToSourceTime(story,29),13.5);
});
test('editorial receipt cannot borrow an accepted job or different source identity',async()=>{
 const saved=globalThis.fetch,story=normalizeStory(bound,base);
 try{globalThis.fetch=async()=>({ok:true,json:async()=>production});assert.equal((await loadStoryRecord(story)).mode,'editorial');
 globalThis.fetch=async()=>({ok:true,json:async()=>({...production,sourceSha256:'f'.repeat(64)})});await assert.rejects(loadStoryRecord(story),/身份不一致/);
 }finally{globalThis.fetch=saved;}
});
