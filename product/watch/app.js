import {baseline,getConfig,subscribe,updateConfig} from './config/config.js';
import {createStageLayout} from './stage/layout.js';
import {GlassManager} from './glass/glass-manager.js';
import {paintAmbienceSource,stopAmbienceSource,ambienceSourceStatus} from './glass/ambience-source.js';
import {createPlayerControls} from './media/player-controls.js';
import {createDrawer} from './navigation/drawer.js';
import {loadCatalog,sourceToOutputTime,outputToSourceTime,followPlayers,followEvents,reminderAt,readPreferences,savePreferences,validatePreferences,followMapping} from './adapters/catalog.js';
import {createContentPanel} from './content/content-panel.js';
import {createCourtPanel} from './court/court-panel.js';
import {getCourtTheme} from './court/themes.js';
import {createAnnotationLayer} from './annotations/annotations.js';
import {createInspector} from './dev/inspector.js';
import {mountGameBuddyAmbient} from './companions/game-buddy/game-buddy-embed.js';
import {validateFormalCourt} from './court/formal-court.js';

const $=s=>document.querySelector(s),stage=$('#stage'),video=$('#match-video');
// User-requested ambient character only; independent of voice and match events.
const buddy=mountGameBuddyAmbient($('#game-buddy-slot'),{width:120,sequence:['idle','running-right','running-left','waving','jumping','failed','waiting','running','review']});
let catalog=[],story=null,mediaVariant='source',courtData=null,formalCourtData=null,focusId=null,activeMenu=null,leftTimer=0,idleTimer=0,noticeTimer=0;
let layout,glass,inspector,lastFrame=NaN,mediaCallback=0,lastChapter='';
let clipPlayback=null,seekRequest=0,mediaLoad=0,destroyed=false,dockPinned=false;
const showNotice=message=>{const el=$('#notice');el.textContent=message;el.hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>el.hidden=true,3400);};
const content=createContentPanel({onSeek:seekContent,onStory:(s,variant)=>{selectStory(s,variant);content.close();},onClose:()=>{activeMenu=inspector?.isOpen?'inspector':null;}});
stage.append(content.element);content.element.dataset.component='content';
const court=createCourtPanel({onMode:mode=>setMode(mode,true),onSelect:id=>{focusId=id;syncContent();},onTheme:preset=>updateConfig({courtTheme:{preset}})});
$('#court-foreground').append(court.element);
const annotations=createAnnotationLayer({video,onSelect:id=>{focusId=id;syncContent();}});$('#annotation-host').append(annotations.element);
const controls=createPlayerControls({video,stage,onError:showNotice,onMenuChange:value=>{activeMenu=value;showControls();}});$('#controls-host').append(controls.element);
const drawer=createDrawer({onAction:action=>{if(action==='settings')toggleSettings();else openContent(action);}});$('#drawer-host').append(drawer.element);drawer.element.dataset.component='dock';
function componentConfig(){const c=getConfig();return {...c,layout:{...c.layout,dockWidth:c.dock?.width??c.layout.dockWidth,fullWidth:c.fullCourt?.width??c.layout.fullWidth,halfWidth:c.halfCourt?.width??c.layout.halfWidth}};}
layout=createStageLayout({stage,video,surface:$('#video-surface'),panel:$('#court-shell'),controls:$('#controls-host'),config:componentConfig,onFrame:r=>{
 court.setView(r.half);const h=$('#moment-heading');h.style.left=(r.video.x+(1-r.open)*54+r.open*26)+'px';h.style.top=(r.video.y+(1-r.open)*46+r.open*24)+'px';h.style.maxWidth=Math.max(240,r.video.width-(1-r.open)*600-70)+'px';
 $('#annotation-host').style.cssText=`left:${r.video.x}px;top:${r.video.y}px;width:${r.video.width}px;height:${r.video.height}px`;
 const panel=$('#court-shell'),scope=r.half<.5?'fullCourt':'halfCourt',scopeChanged=panel.dataset.component!==scope;
 panel.dataset.component=scope;if(getConfig().fullCourt)applyCourtStyle(r.half);if(scopeChanged)glass?.apply();
 syncAnnotations();
}});
function setMode(mode){layout.to(mode);$('#right-edge').setAttribute('aria-expanded',String(mode!=='immersive'));glass?.apply();showControls();}
function openAutomatic(){if(layout.mode!=='immersive'&&layout.phase!=='closing')return;layout.to('halfCourt',{automatic:true});$('#right-edge').setAttribute('aria-expanded','true');showControls();glass?.apply();}
function showControls(){stage.classList.remove('controls-hidden');clearTimeout(idleTimer);idleTimer=setTimeout(()=>{if(!activeMenu&&!content.isOpen&&!inspector?.isOpen&&!stage.querySelector(':focus-visible')&& !video.paused)stage.classList.add('controls-hidden');},getConfig().motion.controlsIdle);}
function toggleSettings(force){const el=$('#settings'),open=force??el.hidden;el.hidden=!open;activeMenu=open?'settings':null;drawer.element.querySelector('[data-action="settings"]').setAttribute('aria-expanded',String(open));if(open){content.close(false);activeMenu='settings';drawer.setOpen(true);renderPreferences();}showControls();}
function openContent(kind){if(!story){showNotice('比赛目录尚未载入，请稍后重试。');return;}toggleSettings(false);activeMenu='content';drawer.setOpen(true);content.open(kind,story,catalog,{preferences,events:reminders,media:{width:video.videoWidth,height:video.videoHeight,variant:mediaVariant}});showControls();}
function syncAnnotations(){if(!story)return;const mapping=followMapping(story,preferences.player,video.currentTime);annotations.update({time:video.currentTime,anchors:mediaVariant==='source'?(story.videoHeadAnchors||[]):[],focusId:preferences.player==='all'?focusId:(mapping?.videoPlayerId||'unmapped'),enabled:mediaVariant==='source'&&getConfig().annotations.enabled,rect:layout?.rects?.video});}
function displayedCourtTime(){
 // A container's end can be later than its last decoded frame. At ended, retain
 // the actual displayed frame PTS; never relabel an offscreen point as current.
 const t=mediaVariant==='enhanced'?outputToSourceTime(story,video.currentTime):video.currentTime;
 return video.ended&&Number.isFinite(lastFrame)&&lastFrame<=t&&t-lastFrame<=.1?lastFrame:t;
}
let preferences=readPreferences(),reminders=[],titleUntil=0,titleTimer=0,lastReminder='';
function renderPreferences(){
 const select=$('#follow-player');select.replaceChildren(new Option('全队','all'));
 for(const p of followPlayers(story))select.add(new Option(`${p.name} · ${p.team||'球队未记录'}`,p.id));
 select.value=preferences.player;$('#familiarity').value=preferences.familiarity;$('#watch-purpose').value=preferences.purpose;
 const hasDefense=reminders.some(e=>e.category==='defense'),hasOffBall=reminders.some(e=>e.category==='offball');
 $('#preference-status').textContent=`仅列来源可核验球员。${hasDefense?'防守观察已接入；':'防守事件待联调；'}${hasOffBall?'无球观察已接入；':'无球事件待联调；'}球员位置映射／视频锚点待联调。缺少分难度文案时沿用原文。`;
}
function changePreferences(){preferences={player:$('#follow-player').value,familiarity:$('#familiarity').value,purpose:$('#watch-purpose').value};try{savePreferences(preferences);}catch{showNotice('本机存储不可用，本次偏好仅在当前页面生效。');}lastReminder='';syncContent();}
for(const id of ['follow-player','familiarity','watch-purpose'])$('#'+id).addEventListener('change',changePreferences);
$('#follow-reminder').onclick=()=>openContent('moments');
$('#settings a[href="/product/index.html#creator"]').onclick=async e=>{
 e.preventDefault();
 try{const response=await fetch('/product/index.html',{method:'HEAD',credentials:'same-origin',redirect:'error'});if(!response.ok)throw new Error();location.assign('/product/index.html#creator');}
 catch{showNotice('当前独立本地预览未挂载创作台，待主产品联调。观看与历史记录仍可使用。');}
};
function syncContent(){
 if(!story)return;
 const mapping=followMapping(story,preferences.player,video.currentTime);
 court.update(story.sample==='formal'?formalCourtData:story.sample==='flagg'?courtData:null,displayedCourtTime(),preferences.player==='all'?focusId:(mapping?.courtPlayerId||null));syncAnnotations();
 const heading=$('#moment-heading');heading.hidden=mediaVariant==='enhanced'||!getConfig().annotations.enabled||performance.now()>titleUntil;
 const reminder=mediaVariant==='source'&&getConfig().annotations.enabled?reminderAt(reminders,video.currentTime,preferences):null;
 const key=reminder?.id||'';const el=$('#follow-reminder');const safeSpace=(layout?.rects?.video.y||0)>=44;el.hidden=!reminder||!safeSpace;el.style.top=Math.max(8,((layout?.rects?.video.y||0)-40)/2)+'px';
 if(key!==lastReminder){lastReminder=key;el.querySelector('.glass-content').textContent=reminder?.text||'';el.title=reminder?`${reminder.sourceLabel} · 点击回看依据`:'';}
}
function paintAmbience(){if(!glass?.enabled)return;paintAmbienceSource($('#ambience'),video,stage);}
function frame(now,meta){if(destroyed)return;if(Number.isFinite(meta?.mediaTime))lastFrame=meta.mediaTime;checkClipEnd(video.currentTime);paintAmbience();syncContent();mediaCallback=video.requestVideoFrameCallback?.(frame)||0;}
function cancelClipPlayback(){const clip=clipPlayback;clipPlayback=null;if(clip&&Number.isFinite(clip.restoreRate))video.playbackRate=clip.restoreRate;}
function checkClipEnd(t){
 if(!clipPlayback||t<clipPlayback.end-.001)return;
 const end=clipPlayback.end;cancelClipPlayback();video.pause();
 if(Math.abs(video.currentTime-end)>.002)video.currentTime=end;
 showControls();
}
function waitForMetadata(load){
 if(load!==mediaLoad)return Promise.reject(new Error('素材已切换。'));
 if(video.readyState>=1)return Promise.resolve();
 return new Promise((resolve,reject)=>{
  let timer;
  const cleanup=()=>{clearTimeout(timer);video.removeEventListener('loadedmetadata',ready);video.removeEventListener('error',failed);};
  const ready=()=>{cleanup();load===mediaLoad?resolve():reject(new Error('素材已切换。'));};
  const failed=()=>{cleanup();reject(new Error('原片暂时无法播放，请恢复本地素材后重试。'));};
  video.addEventListener('loadedmetadata',ready);video.addEventListener('error',failed);
  timer=setTimeout(()=>{cleanup();reject(new Error('等待原片超时，请检查本地素材后重试。'));},8000);
  if(video.error)failed();
 });
}
async function seekContent(time,meta={}){
 cancelClipPlayback();
 if(meta.story&&meta.story.sample!==story?.sample)selectStory(meta.story);
 const request=++seekRequest,load=mediaLoad;
 content.close();showControls();
 try{
  await waitForMetadata(load);if(request!==seekRequest||destroyed)return;
  const target=mediaVariant==='enhanced'?sourceToOutputTime(story,Number(time)||0):Number(time)||0;
  const start=Math.max(0,Math.min(video.duration,target));
  const requestedEnd=Number.isFinite(meta.end)?meta.end:typeof meta.chapter==='object'?meta.chapter?.end:NaN;
  const mappedEnd=mediaVariant==='enhanced'&&Number.isFinite(requestedEnd)?sourceToOutputTime(story,requestedEnd):requestedEnd;
  const end=Number.isFinite(mappedEnd)?Math.min(video.duration,mappedEnd):NaN;
  const restoreRate=video.playbackRate;video.pause();video.currentTime=start;
  if(Number.isFinite(end)&&end>start){
   const playbackRate=Number.isFinite(meta.playbackRate)&&meta.playbackRate>0?meta.playbackRate:restoreRate;
   clipPlayback={start,end,restoreRate,request};video.playbackRate=playbackRate;
   await video.play();
  }
  // Evidence and attention-point jumps stay paused so the referenced frame is inspectable.
 }catch(error){if(request===seekRequest&&!destroyed){cancelClipPlayback();showNotice(error.message||String(error));}}
}
function activeMedia(){return story?.media?.[mediaVariant];}
function selectStory(next,variant='source'){
 if(!next)return;if(variant==='enhanced'&&!next.enhancedAvailable){showNotice('此素材尚无可核验的同源增强成片。');return;}
 seekRequest++;mediaLoad++;cancelClipPlayback();story=next;mediaVariant=variant==='enhanced'?'enhanced':'source';lastFrame=NaN;lastChapter='';focusId=null;video.pause();$('#load-error').hidden=true;
 const validated=validatePreferences(preferences,next);if(validated.player!==preferences.player){showNotice('关注球员不在当前可核验名单中，已回到全队。');preferences=validated;try{savePreferences(preferences);}catch{}}
 reminders=followEvents(next);renderPreferences();lastReminder='';
 $('#moment-kicker').textContent='GameBuddy · '+(mediaVariant==='enhanced'?'增强成片':'原片');$('#moment-title').textContent=next.title;$('#moment-subtitle').textContent='';
 titleUntil=performance.now()+getConfig().motion.controlsIdle;clearTimeout(titleTimer);titleTimer=setTimeout(syncContent,getConfig().motion.controlsIdle+20);
 if(activeMedia())activeMedia().status='loading';video.src=mediaVariant==='enhanced'?next.enhancedVideo:next.sourceVideo;video.setAttribute('aria-label',mediaVariant==='enhanced'?'已烧录解读的比赛成片':'真实比赛原片');video.load();court.setStory(next);court.setTheme(courtThemeId());syncContent();layout.draw();
}
function courtThemeId(c=getConfig()){
 return c.courtTheme?.preset==='rockets'?'houston':'dallas';
}
function applyCourtStyle(half){
 const c=getConfig(),a=c.fullCourt,b=c.halfCourt;if(!a||!b)return;
 const group=half<.5?'fullCourt':'halfCourt',chosen=c[group],effective={...chosen},themeId=courtThemeId(c),theme=getCourtTheme(themeId);
 // Preserve the supplied Houston baseline. Other skins replace baseline colors,
 // while an explicitly changed component color remains its independent override.
 if(themeId!=='houston')for(const [key,themeKey] of [['woodColor','wood'],['paintColor','paint'],['lineColor','line']])if(String(chosen[key]).toLowerCase()===String(baseline[group][key]).toLowerCase())effective[key]=theme[themeKey];
 $('#court-shell').style.borderRadius=(a.radius+(b.radius-a.radius)*half)+'px';$('#court-foreground').style.fontSize=(chosen.fontSize||16)+'px';$('#court-foreground').style.color=chosen.color||'#f6f7fa';court.setStyle?.(effective);
}
function applyConfig(){const c=getConfig();court.setTheme(courtThemeId(c));court.setThemeChoice(c.courtTheme.preset);layout.draw();glass?.apply();syncContent();$('#analysis-toggle').checked=c.annotations.enabled;const d=c.dock;if(d){drawer.element.style.width=d.width+'px';drawer.element.style.borderRadius=d.radius+'px';drawer.element.style.color=d.color;drawer.element.querySelectorAll('button').forEach(b=>b.style.color=d.color);drawer.element.querySelector('.glass-content').style.gap=d.gap+'px';drawer.element.querySelectorAll('svg').forEach(el=>{el.style.width=d.iconSize+'px';el.style.height=d.iconSize+'px';});}if(c.heading){$('#moment-heading').style.setProperty('--title-size',c.heading.fontSize+'px');$('#moment-title').style.color=c.heading.color;$('#moment-title').style.fontSize=c.heading.fontSize+'px';}if(c.controls){controls.element.style.borderRadius=c.controls.radius+'px';controls.element.style.fontSize=c.controls.fontSize+'px';controls.element.style.color=c.controls.color;}annotations.setStyle(c.annotations);}
const unsubscribeConfig=subscribe(applyConfig);
$('#court-close').onclick=()=>{setMode('immersive');stage.focus();setTimeout(()=>$('#right-edge').focus(),getConfig().motion.close+30);};
document.querySelectorAll('[data-content]').forEach(b=>b.onclick=()=>openContent(b.dataset.content));$('#analysis-toggle').onchange=e=>updateConfig({annotations:{enabled:e.target.checked}});
$('#left-edge').addEventListener('pointerenter',()=>{clearTimeout(leftTimer);drawer.setOpen(true);});$('#left-edge').onclick=()=>{drawer.setOpen(true);drawer.element.querySelector('button').focus();};$('#right-edge').onclick=openAutomatic;
function closeLeftLater(){clearTimeout(leftTimer);leftTimer=setTimeout(()=>{if(!dockPinned&&!content.isOpen&&!inspector?.isOpen&&$('#settings').hidden&&!drawer.element.matches(':hover')&&!drawer.element.contains(document.activeElement))drawer.setOpen(false);},getConfig().motion.hideDelay);}
drawer.element.addEventListener('pointerenter',()=>clearTimeout(leftTimer));drawer.element.addEventListener('pointerleave',closeLeftLater);drawer.element.addEventListener('focusout',closeLeftLater);
$('#left-edge').addEventListener('pointerleave',closeLeftLater);$('#left-edge').addEventListener('focus',()=>drawer.setOpen(true));
$('#settings').addEventListener('pointerenter',()=>clearTimeout(leftTimer));$('#settings').addEventListener('pointerleave',closeLeftLater);
stage.addEventListener('pointermove',showControls);stage.addEventListener('focusin',showControls);
stage.addEventListener('keydown',e=>{if(e.key==='Escape'){if(inspector?.isOpen){inspector.close();return;}if(!$('#settings').hidden){const inner=$('#settings details[open]');if(inner){inner.open=false;inner.querySelector('summary').focus();}else {toggleSettings(false);drawer.element.querySelector('[data-action="settings"]').focus();}return;}if(content.isOpen){content.close();activeMenu=null;return;}document.activeElement?.blur();dockPinned=false;drawer.setOpen(false);setMode('immersive');}if(e.target.matches('input,select,textarea,button'))return;if(e.key===' '){e.preventDefault();video.paused?video.play().catch(showNotice):video.pause();}if(e.key.toLowerCase()==='f')document.fullscreenElement?document.exitFullscreen():stage.requestFullscreen();});
for(const name of ['seeked','loadeddata','pause','ended'])video.addEventListener(name,()=>{checkClipEnd(video.currentTime);if(name==='pause'&&video.paused)cancelClipPlayback();paintAmbience();syncContent();showControls();});
video.addEventListener('timeupdate',()=>checkClipEnd(video.currentTime));
video.addEventListener('seeking',()=>{if(clipPlayback&&(video.currentTime<clipPlayback.start-.05||video.currentTime>clipPlayback.end+.05))cancelClipPlayback();});
video.addEventListener('loadedmetadata',()=>{layout.draw();$('#media-info').textContent=`${mediaVariant==='enhanced'?'增强成片':'原片'} · ${video.videoWidth} × ${video.videoHeight} · ${video.duration.toFixed(2)} 秒`;});
video.addEventListener('loadeddata',()=>{$('#load-error').hidden=true;if(activeMedia())activeMedia().status='available';glass?.apply();});
video.addEventListener('error',()=>{cancelClipPlayback();if(activeMedia())activeMedia().status='missing';$('#load-error').hidden=false;showControls();});
$('#retry-media').onclick=()=>{seekRequest++;mediaLoad++;cancelClipPlayback();lastFrame=NaN;$('#load-error').hidden=true;if(activeMedia())activeMedia().status='loading';video.load();};

function revealComponent(group){
 clearTimeout(leftTimer);showControls();
 if(group==='dock'){dockPinned=true;drawer.setOpen(true);}
 else if(group==='fullCourt'||group==='halfCourt')setMode(group,true);
 else if(group==='courtTheme')setMode(layout.mode==='immersive'?'halfCourt':layout.mode,true);
 else if(group==='content')openContent('moments');
 else if(group==='menus')toggleSettings(true);
}
inspector=createInspector();stage.append(inspector.element);$('#style-inspector').hidden=false;$('#style-inspector').onclick=()=>{toggleSettings(false);inspector.open();};
for(const [selector,group] of [['#controls-host','controls'],['#moment-heading','heading']])$(selector).dataset.component=group;
window.addEventListener('broadcast-config-select',e=>revealComponent(e.detail?.component));
window.addEventListener('broadcast-layout-request',e=>{if(!['immersive','fullCourt','halfCourt'].includes(e.detail?.layout))return;setMode(e.detail.layout,true);if(e.detail.layout!=='immersive')drawer.setOpen(true);});
window.addEventListener('broadcast-inspector-state',e=>{activeMenu=e.detail.open?'inspector':null;showControls();});
window.addEventListener('broadcast-config-pick',e=>{activeMenu=e.detail.active?'inspector-pick':null;showControls();});
window.broadcastDiagnostics=()=>({glass:glass?.status(),ambience:ambienceSourceStatus($('#ambience')),layout:layout.rects,mode:layout.mode,media:{src:video.currentSrc,time:video.currentTime,displayedCourtTime:displayedCourtTime(),lastDecodedFrameTime:Number.isFinite(lastFrame)?lastFrame:null,variant:mediaVariant,status:activeMedia()?.status||'unloaded',duration:video.duration,paused:video.paused,ended:video.ended,videoWidth:video.videoWidth,videoHeight:video.videoHeight,quality:(()=>{const q=video.getVideoPlaybackQuality?.();return q?{totalVideoFrames:q.totalVideoFrames,droppedVideoFrames:q.droppedVideoFrames,corruptedVideoFrames:q.corruptedVideoFrames}:null;})()},annotations:{validHeadAnchors:story?.videoHeadAnchors?.length||0},config:getConfig()});
window.broadcastUI={setMode,openAutomatic,openDrawer:()=>drawer.setOpen(true),openInspector:()=>inspector.open(),selectStory:(id,variant='source')=>selectStory(catalog.find(s=>s.sample===id),variant),video,layout,getConfig,updateConfig,showControls,glass:()=>glass};
// Glass and the inspector are independent of successful media decoding. Their
// controls remain usable when a local MP4 is missing, and loadeddata can recover.
glass=new GlassManager(stage,getConfig,{enabled:new URLSearchParams(location.search).get('glass')==='liquid',onModeChange:enabled=>{if(enabled)paintAmbience();else stopAmbienceSource($('#ambience'));}});glass.start();applyConfig();
if(video.requestVideoFrameCallback)mediaCallback=video.requestVideoFrameCallback(frame);else video.addEventListener('timeupdate',frame);
$('#load-error h2').textContent='视频暂时无法播放';$('#load-error p').textContent='请检查本地素材是否存在，再重新加载。';
const initialMode=new URLSearchParams(location.search).get('mode');if(['fullCourt','halfCourt'].includes(initialMode))setMode(initialMode,true);showControls();
try{
 catalog=await loadCatalog();
 if(catalog.some(s=>s.sample==='formal')){const response=await fetch(new URL('./data/formal-court.json',import.meta.url),{cache:'no-store'});if(!response.ok)throw new Error('正式战术示意暂不可用');formalCourtData=validateFormalCourt(await response.json(),catalog.find(s=>s.sample==='formal'));}
 if(catalog.some(s=>s.sample==='flagg'))try{const response=await fetch('./data/flagg.json');if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json();courtData=globalThis.CourtLab.validateDataset(data);}
 catch(error){courtData=null;showNotice('战术示意暂不可用：'+error.message);}
 const params=new URLSearchParams(location.search),selected=catalog.find(s=>s.sample===(params.get('story')||params.get('sample')))||catalog[0];const version=params.get('version')||params.get('variant');selectStory(selected,(version==='enhanced'||(!version&&selected?.sample==='formal'))&&selected?.enhancedAvailable?'enhanced':'source');
}catch(error){showNotice('载入失败：'+error.message);$('#load-error').hidden=false;console.error(error);}
window.addEventListener('pagehide',event=>{if(event.persisted)return;destroyed=true;buddy.destroy();seekRequest++;cancelClipPlayback();clearTimeout(leftTimer);clearTimeout(idleTimer);clearTimeout(noticeTimer);clearTimeout(titleTimer);unsubscribeConfig();inspector?.destroy();glass?.destroy();stopAmbienceSource($('#ambience'));layout.destroy();controls.destroy();court.destroy();annotations.destroy();video.cancelVideoFrameCallback?.(mediaCallback);video.removeEventListener('timeupdate',frame);});
