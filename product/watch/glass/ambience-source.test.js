import test from 'node:test';
import assert from 'node:assert/strict';
import {softenAmbiencePixels} from './ambience-source.js';
const fill = (w,h,r,g,b) => { const a=new Uint8ClampedArray(w*h*4);for(let i=0;i<a.length;i+=4)a.set([r,g,b,255],i);return a; };
test('software backdrop bakes brightness into uniform pixels including edges',()=>{
 const data=fill(12,8,255,255,255);softenAmbiencePixels(data,12,8,2);
 for(let i=0;i<data.length;i+=4){assert.ok(data[i]>=76&&data[i]<=77);assert.equal(data[i],data[i+1]);assert.equal(data[i+3],255);}
});
test('software backdrop bakes saturation without leaving sharp source colors',()=>{
 const data=fill(9,7,255,0,0);softenAmbiencePixels(data,9,7,2);
 assert.ok(data[0]>=55&&data[0]<=56);assert.ok(data[1]>=5&&data[1]<=6);assert.equal(data[1],data[2]);
});
test('software blur spreads a source edge across both axes and does not wrap edges',()=>{
 const data=fill(21,21,0,0,0);data.set([255,255,255,255],(10*21+10)*4);
 softenAmbiencePixels(data,21,21,2);
 assert.ok(data[(10*21+10)*4]>0&&data[(10*21+10)*4]<10);
 assert.ok(data[(10*21+11)*4]>0);assert.ok(data[(11*21+10)*4]>0);
 assert.equal(data[0],0);assert.equal(data[(20*21+20)*4],0);
});
