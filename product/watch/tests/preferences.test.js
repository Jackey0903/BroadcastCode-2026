import test from 'node:test';
import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import { followPlayers, followEvents, reminderAt, followMapping, readPreferences, savePreferences, validatePreferences } from '../adapters/catalog.js';
const stories = JSON.parse(await readFile(new URL('../data/stories.json',import.meta.url))).stories;
const flagg=stories.find(s=>s.sample==='flagg'), amen=stories.find(s=>s.sample==='amen');
const defaults={player:'all',familiarity:'beginner',purpose:'enjoy'};
test('current source roster supports both teams without guessing anonymous court identities',()=>{
 assert.equal(followPlayers(flagg).length,1);
 assert.deepEqual(followPlayers(amen).map(p=>p.name),['阿门·汤普森','凯文·杜兰特','马克斯·克里斯蒂']);
 assert.equal(followPlayers({}).length,0);
 assert.equal(followMapping(flagg,'1642843',16),null);
});
test('real attack and defense reminders preserve source words and start no earlier than source frames',()=>{
 const events=followEvents(amen),defender=followPlayers(amen).find(p=>p.number==='00');
 const pref={...defaults,player:defender.id};
 assert.equal(reminderAt(events,17.49,pref),null);
 assert.equal(reminderAt(events,17.5,pref).text,'深衣 00 号已起跳');
 assert.equal(reminderAt(events,17.5,pref).category,'defense');
 assert.equal(reminderAt(events,16,{...defaults,player:'1641708'}).text,'白衣 1 号持球');
 for(const event of events)assert.ok(amen.evidence.find(e=>event.evidenceIds.includes(e.id)).body.includes(event.text));
 assert.equal(events.some(e=>e.category==='offball'),false);
});
test('one sparse reminder at a time; future results never become chapter-start alerts',()=>{
 const events=followEvents(flagg);
 for(const t of [0,1,8.9])assert.equal(reminderAt(events,t,defaults),null);
 assert.equal(reminderAt(events,9,defaults).text,'深衣 32 号持球');
 assert.equal(reminderAt(events,12,defaults),null);
 assert.ok(!reminderAt(events,17.4,defaults)?.text.includes('命中'));
 assert.equal(reminderAt([{id:'off',time:1,text:'无球掩护',category:'offball',playerIds:['p']}],1,{...defaults,player:'p'}).category,'offball');
});
test('preferences persist independently and invalid player resets only the selection',()=>{
 const data=new Map(),storage={getItem:k=>data.get(k),setItem:(k,v)=>data.set(k,v)};
 const pref={player:'1642843',familiarity:'familiar',purpose:'analyze'};savePreferences(pref,storage);
 assert.deepEqual(readPreferences(storage),pref);
 assert.deepEqual(validatePreferences(pref,amen),{...pref,player:'all'});
 assert.equal(data.size,1);assert.ok([...data.keys()][0].includes('preferences'));
});
test('explicit mappings expire; absent, future, unverified and unsupported references cannot attach',()=>{
 const mapping={playerId:'1642843',verified:true,sourceEvidenceIds:['flagg-roster'],start:9,end:10,courtPlayerId:'D5',videoPlayerId:'1642843'};
 const fixture={...flagg,playerIdentityMappings:[mapping]};
 assert.equal(followMapping(fixture,'1642843',9),mapping);
 for(const t of [8.9,10.1])assert.equal(followMapping(fixture,'1642843',t),null);
 assert.equal(followMapping({...fixture,playerIdentityMappings:[{...mapping,verified:false}]},'1642843',9),null);
});
