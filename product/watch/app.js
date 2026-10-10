import {baseline,getConfig,subscribe,updateConfig} from './config/config.js';
import {createStageLayout} from './stage/layout.js';
import {GlassManager} from './glass/glass-manager.js';
import {paintAmbienceSource} from './glass/ambience-source.js';
import {createPlayerControls} from './media/player-controls.js';
import {createDrawer} from './navigation/drawer.js';
import {loadCatalog} from './adapters/catalog.js';
import {createContentPanel} from './content/content-panel.js';
import {createCourtPanel} from './court/court-panel.js';
import {getCourtTheme} from './court/themes.js';
import {mascotSVG,createAnnotationLayer} from './annotations/annotations.js';
import {createInspector} from './dev/inspector.js';

const $=s=>document.querySelector(s),stage=$('#stage'),video=$('#match-video');
let catalog=[],story=null,mediaVariant='source',courtData=null,focusId=null,activeMenu=null,manual=false,rightTimer=0,leftTimer=0,idleTimer=0,noticeTimer=0;
let layout,glass,inspector,lastFrame=NaN,mediaCallback=0,lastChapter='';
let clipPlayback=null,seekRequest=0,mediaLoad=0,destroyed=false,dockPinned=false;
const showNotice=message=>{const el=$('#notice');el.textContent=message;el.hidden=false;clearTimeout(noticeTimer);noticeTimer=setTimeout(()=>el.hidden=true,3400);};
const content=createContentPanel({onSeek:seekContent,onStory:(s,variant)=>{selectStory(s,variant);content.close();},onClose:()=>{activeMenu=inspector?.isOpen?'inspector':null;}});
stage.append(content.element);content.element.dataset.component='content';
const court=createCourtPanel({onMode:mode=>setMode(mode,true),onSelect:id=>{focusId=id;syncContent();},onEvidence:()=>openContent('sources')});
$('#court-foreground').append(court.element);
const annotations=createAnnotationLayer({video,onSelect:id=>{focusId=id;syncContent();}});$('#annotation-host').append(annotations.element);
const controls=createPlayerControls({video,stage,onSettings:()=>toggleSettings(),onError:showNotice,onMenuChange:value=>{activeMenu=value;showControls();}});$('#controls-host').append(controls.element);
const drawer=createDrawer({onAction:action=>{if(action==='watch')setMode('immersive');else if(action==='settings')toggleSettings();else if(action==='annotations')toggleAnalysis();else if(action==='creator')location.assign('/product/index.html#creator');else openContent(action);},mascot:mascotSVG(44)});$('#drawer-host').append(drawer.element);drawer.element.dataset.component='dock';
$('#heading-mascot').innerHTML=mascotSVG(43);
function componentConfig(){const c=getConfig();return {...c,layout:{...c.layout,dockWidth:c.dock?.width??c.layout.dockWidth,fullWidth:c.fullCourt?.width??c.layout.fullWidth,halfWidth:c.halfCourt?.width??c.layout.halfWidth}};}
layout=createStageLayout({stage,video,surface:$('#video-surface'),panel:$('#court-shell'),controls:$('#controls-host'),config:componentConfig,onFrame:r=>{
 court.setView(r.half);const h=$('#moment-heading');h.style.left=(r.video.x+(1-r.open)*54+r.open*26)+'px';h.style.top=(r.video.y+(1-r.open)*46+r.open*24)+'px';h.style.maxWidth=Math.max(240,r.video.width-(1-r.open)*600-70)+'px';
 $('#top-tabs').style.right=(112+r.panel.width+r.open*12)+'px';$('#more-button').style.right=(44+r.panel.width+r.open*12)+'px';
 $('#annotation-host').style.cssText=`left:${r.video.x}px;top:${r.video.y}px;width:${r.video.width}px;height:${r.video.height}px`;
 const panel=$('#court-shell'),scope=r.half<.5?'fullCourt':'halfCourt',scopeChanged=panel.dataset.component!==scope;
 panel.dataset.component=scope;if(getConfig().fullCourt)applyCourtStyle(r.half);if(scopeChanged)glass?.apply();
 syncAnnotations();
}});
function setMode(mode,pinned=false){clearTimeout(rightTimer);manual=pinned&&mode!=='immersive';layout.to(mode);$('#analysis-button').setAttribute('aria-pressed',String(mode!=='immersive'));if(mode==='immersive'){manual=false;$('#court-shell').blur();}glass?.apply();updateModeButtons();showControls();}
function updateModeButtons(){document.querySelectorAll('[data-mode]').forEach(b=>b.classList.toggle('active',b.dataset.mode===layout.mode));}
function openAutomatic(){clearTimeout(rightTimer);if(layout.mode!=='immersive'&&layout.phase!=='closing')return;manual=false;layout.to('halfCourt',{automatic:true});showControls();glass?.apply();}
function holdRight(){return manual||activeMenu||content.isOpen||$('#court-shell').contains(document.activeElement)||inspector?.isOpen;}
function closeRightLater(){clearTimeout(rightTimer);if(!holdRight())rightTimer=setTimeout(()=>{if(!holdRight())layout.to('immersive');},getConfig().motion.hideDelay);}
function showControls(){stage.classList.remove('controls-hidden');clearTimeout(idleTimer);idleTimer=setTimeout(()=>{if(!activeMenu&&!content.isOpen&&!inspector?.isOpen&&!stage.querySelector(':focus-visible')&& !video.paused)stage.classList.add('controls-hidden');},getConfig().motion.controlsIdle);}
function toggleSettings(force){const el=$('#settings'),open=force??el.hidden;el.hidden=!open;activeMenu=open?'settings':null;$('#more-button').setAttribute('aria-expanded',String(open));updateModeButtons();showControls();}
function openContent(kind){if(!story){showNotice('比赛目录尚未载入，请稍后重试。');return;}toggleSettings(false);activeMenu='content';drawer.setOpen(true);content.open(kind,story,catalog);showControls();}
function toggleAnalysis(){const c=getConfig();updateConfig({annotations:{enabled:!c.annotations.enabled}});}
function syncAnnotations(){if(!story)return;annotations.update({time:video.currentTime,anchors:mediaVariant==='source'?(story.videoHeadAnchors||[]):[],focusId,enabled:mediaVariant==='source'&&getConfig().annotations.enabled,rect:layout?.rects?.video});}
function displayedCourtTime(){
 // A container's end can be later than its last decoded frame. At ended, retain
 // the actual displayed frame PTS; never relabel an offscreen point as current.
 const t=video.currentTime;
 return video.ended&&Number.isFinite(lastFrame)&&lastFrame<=t&&t-lastFrame<=.1?lastFrame:t;
}
function syncContent(){if(!story)return;court.update(story.sample==='flagg'?courtData:null,displayedCourtTime(),focusId);syncAnnotations();const chapters=story.chapters||[];const current=[...chapters].reverse().find(c=>video.currentTime>=(c.start??c.time??0))||chapters[0];const key=current?JSON.stringify(current):story.id;if(key!==lastChapter){lastChapter=key;$('#moment-kicker').textContent=current?.title||'GameBuddy · 原片';$('#moment-title').textContent=current?.headline||current?.title||story.title||'看懂这一拍';$('#moment-subtitle').textContent=current?.caption||current?.description||current?.text||story.subtitle||'';}$('#moment-heading').hidden=mediaVariant==='enhanced'||!getConfig().annotations.enabled;}
function paintAmbience(){paintAmbienceSource($('#ambience'),video,stage);}
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
  const failed=()=>{cleanup();reject(new Error('视频暂时无法播放，请检查素材地址后重试。'));};
  video.addEventListener('loadedmetadata',ready);video.addEventListener('error',failed);
  timer=setTimeout(()=>{cleanup();reject(new Error('等待视频超时，请检查网络或素材后重试。'));},8000);
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
  const start=Math.max(0,Math.min(video.duration,Number(time)||0));
  const requestedEnd=Number.isFinite(meta.end)?meta.end:typeof meta.chapter==='object'?meta.chapter?.end:NaN;
  const end=Number.isFinite(requestedEnd)?Math.min(video.duration,requestedEnd):NaN;
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
 if(activeMedia())activeMedia().status='loading';video.src=mediaVariant==='enhanced'?next.enhancedVideo:next.sourceVideo;video.setAttribute('aria-label',mediaVariant==='enhanced'?'已烧录解读的比赛成片':'真实比赛原片');video.load();court.setStory(next);court.setTheme(courtThemeId());syncContent();layout.draw();
}
function courtThemeId(c=getConfig()){
 const home=story?.game?.homeTeam;const source=home==='DAL'?'dallas':home==='HOU'?'houston':story?.sample==='amen'?'dallas':'houston';
 return ({source,rockets:'houston',mavericks:'dallas',neutral:'neutral'})[c.courtTheme?.preset||'source']||source;
}
function applyCourtStyle(half){
 const c=getConfig(),a=c.fullCourt,b=c.halfCourt;if(!a||!b)return;
 const group=half<.5?'fullCourt':'halfCourt',chosen=c[group],effective={...chosen},themeId=courtThemeId(c),theme=getCourtTheme(themeId);
 // Preserve the supplied Houston baseline. Other skins replace baseline colors,
 // while an explicitly changed component color remains its independent override.
 if(themeId!=='houston')for(const [key,themeKey] of [['woodColor','wood'],['paintColor','paint'],['lineColor','line']])if(String(chosen[key]).toLowerCase()===String(baseline[group][key]).toLowerCase())effective[key]=theme[themeKey];
 $('#court-shell').style.borderRadius=(a.radius+(b.radius-a.radius)*half)+'px';$('#court-foreground').style.fontSize=(chosen.fontSize||16)+'px';$('#court-foreground').style.color=chosen.color||'#f6f7fa';court.setStyle?.(effective);
}
function applyConfig(){const c=getConfig();court.setTheme(courtThemeId(c));layout.draw();glass?.apply();syncContent();$('#analysis-toggle').checked=c.annotations.enabled;const d=c.dock;if(d){drawer.element.style.width=d.width+'px';drawer.element.style.borderRadius=d.radius+'px';drawer.element.style.color=d.color;drawer.element.querySelectorAll('button').forEach(b=>b.style.color=d.color);drawer.element.querySelector('.glass-content').style.gap=d.gap+'px';drawer.element.querySelectorAll('svg:not(.mascot-svg)').forEach(el=>{el.style.width=d.iconSize+'px';el.style.height=d.iconSize+'px';});}if(c.heading){$('#moment-heading').style.setProperty('--title-size',c.heading.fontSize+'px');$('#moment-title').style.color=c.heading.color;$('#moment-title').style.fontSize=c.heading.fontSize+'px';}if(c.topbar){$('#top-tabs').style.borderRadius=c.topbar.radius+'px';$('#top-tabs').style.color=c.topbar.color;$('#top-tabs .glass-content').style.gap=c.topbar.gap+'px';$('#top-tabs').querySelectorAll('button').forEach(b=>b.style.color=c.topbar.color);$('#top-tabs').querySelectorAll('button').forEach(b=>b.style.fontSize=c.topbar.fontSize+'px');}if(c.controls){controls.element.style.borderRadius=c.controls.radius+'px';controls.element.style.fontSize=c.controls.fontSize+'px';controls.element.style.color=c.controls.color;}if(c.mascot){$('#heading-mascot').innerHTML=mascotSVG(c.mascot.size,c.mascot);drawer.element.querySelector('.dock-mascot').innerHTML=mascotSVG(c.mascot.size,c.mascot);court.setMascotStyle?.(c.mascot);annotations.setStyle?.(c.mascot);}}
const unsubscribeConfig=subscribe(applyConfig);
$('#analysis-button').onclick=()=>layout.mode==='immersive'?setMode('halfCourt',true):setMode('immersive');$('#court-close').onclick=()=>{document.activeElement?.blur();setMode('immersive');};$('#more-button').onclick=()=>toggleSettings();
document.querySelectorAll('[data-content]').forEach(b=>b.onclick=()=>openContent(b.dataset.content));document.querySelectorAll('[data-mode]').forEach(b=>b.onclick=()=>{setMode(b.dataset.mode,true);toggleSettings(false);});$('#analysis-toggle').onchange=e=>updateConfig({annotations:{enabled:e.target.checked}});
$('#left-edge').addEventListener('pointerenter',()=>{clearTimeout(leftTimer);drawer.setOpen(true);});$('#left-edge').onclick=()=>drawer.setOpen(true);$('#right-edge').addEventListener('pointerenter',openAutomatic);$('#right-edge').onclick=openAutomatic;
drawer.element.addEventListener('pointerenter',()=>clearTimeout(leftTimer));drawer.element.addEventListener('pointerleave',()=>{leftTimer=setTimeout(()=>{if(!dockPinned&&!content.isOpen&&!inspector?.isOpen&&!drawer.element.contains(document.activeElement))drawer.setOpen(false);},getConfig().motion.hideDelay);});
stage.addEventListener('pointermove',event=>{showControls();const x=event.clientX-stage.getBoundingClientRect().left,r=layout.rects;if(layout.mode!=='immersive'){if(x>=r.panel.x-getConfig().layout.gap)clearTimeout(rightTimer);else closeRightLater();}});stage.addEventListener('pointerleave',()=>{closeRightLater();});stage.addEventListener('focusin',showControls);
stage.addEventListener('keydown',e=>{if(e.key==='Escape'){if(inspector?.isOpen){inspector.close();return;}if(!$('#settings').hidden){toggleSettings(false);return;}if(content.isOpen){content.close();activeMenu=null;return;}document.activeElement?.blur();dockPinned=false;drawer.setOpen(false);setMode('immersive');}if(e.target.matches('input,select,textarea,button'))return;if(e.key===' '){e.preventDefault();video.paused?video.play().catch(showNotice):video.pause();}if(e.key.toLowerCase()==='f')document.fullscreenElement?document.exitFullscreen():stage.requestFullscreen();});
for(const name of ['seeked','loadeddata','pause','ended'])video.addEventListener(name,()=>{checkClipEnd(video.currentTime);if(name==='pause'&&video.paused)cancelClipPlayback();paintAmbience();syncContent();showControls();});
video.addEventListener('timeupdate',()=>checkClipEnd(video.currentTime));
video.addEventListener('seeking',()=>{if(clipPlayback&&(video.currentTime<clipPlayback.start-.05||video.currentTime>clipPlayback.end+.05))cancelClipPlayback();});
video.addEventListener('loadedmetadata',()=>{layout.draw();});
video.addEventListener('loadeddata',()=>{$('#load-error').hidden=true;if(activeMedia())activeMedia().status='available';glass?.apply();});
video.addEventListener('error',()=>{cancelClipPlayback();if(activeMedia())activeMedia().status='missing';$('#load-error').hidden=false;showControls();});
$('#retry-media').onclick=()=>{seekRequest++;mediaLoad++;cancelClipPlayback();lastFrame=NaN;$('#load-error').hidden=true;if(activeMedia())activeMedia().status='loading';video.load();};

function revealComponent(group){
 clearTimeout(leftTimer);clearTimeout(rightTimer);showControls();
 if(group==='dock'){dockPinned=true;drawer.setOpen(true);}
 else if(group==='fullCourt'||group==='halfCourt')setMode(group,true);
 else if(group==='courtTheme')setMode(layout.mode==='immersive'?'halfCourt':layout.mode,true);
 else if(group==='content')openContent('moments');
 else if(group==='menus')toggleSettings(true);
}
inspector=createInspector();stage.append(inspector.element);$('#style-inspector').hidden=false;$('#style-inspector').onclick=()=>{toggleSettings(false);inspector.open();};
for(const [selector,group] of [['#controls-host','controls'],['#top-tabs','topbar'],['#moment-heading','heading']])$(selector).dataset.component=group;
window.addEventListener('broadcast-config-select',e=>revealComponent(e.detail?.component));
window.addEventListener('broadcast-layout-request',e=>{if(!['immersive','fullCourt','halfCourt'].includes(e.detail?.layout))return;setMode(e.detail.layout,true);if(e.detail.layout!=='immersive')drawer.setOpen(true);});
window.addEventListener('broadcast-inspector-state',e=>{activeMenu=e.detail.open?'inspector':null;showControls();});
window.addEventListener('broadcast-config-pick',e=>{activeMenu=e.detail.active?'inspector-pick':null;showControls();});
$('#heading-mascot').dataset.component='mascot';
window.broadcastDiagnostics=()=>({glass:glass?.status(),layout:layout.rects,mode:layout.mode,media:{src:video.currentSrc,time:video.currentTime,displayedCourtTime:displayedCourtTime(),lastDecodedFrameTime:Number.isFinite(lastFrame)?lastFrame:null,variant:mediaVariant,status:activeMedia()?.status||'unloaded',duration:video.duration,paused:video.paused,ended:video.ended,videoWidth:video.videoWidth,videoHeight:video.videoHeight,quality:(()=>{const q=video.getVideoPlaybackQuality?.();return q?{totalVideoFrames:q.totalVideoFrames,droppedVideoFrames:q.droppedVideoFrames,corruptedVideoFrames:q.corruptedVideoFrames}:null;})()},annotations:{validHeadAnchors:mediaVariant==='source'?(story?.videoHeadAnchors?.length||0):0},config:getConfig()});
window.broadcastUI={setMode,openAutomatic,openDrawer:()=>drawer.setOpen(true),openInspector:()=>inspector.open(),selectStory:(id,variant='source')=>selectStory(catalog.find(s=>s.sample===id),variant),video,layout,getConfig,updateConfig,showControls,glass:()=>glass};
// Glass and the inspector are independent of successful media decoding. Their
// controls remain usable when a local MP4 is missing, and loadeddata can recover.
glass=new GlassManager(stage,getConfig);glass.start();applyConfig();
if(video.requestVideoFrameCallback)mediaCallback=video.requestVideoFrameCallback(frame);else video.addEventListener('timeupdate',frame);
$('#load-error h2').textContent='视频暂时无法播放';$('#load-error p').textContent='请检查素材与网络后重试。';
const initialMode=new URLSearchParams(location.search).get('mode');if(['fullCourt','halfCourt'].includes(initialMode))setMode(initialMode,true);showControls();
try{
 catalog=await loadCatalog();
 try{const response=await fetch('./data/flagg.json');if(!response.ok)throw new Error(`HTTP ${response.status}`);const data=await response.json();courtData=globalThis.CourtLab.validateDataset(data);}
 catch(error){courtData=null;showNotice('战术示意暂不可用：'+error.message);}
 const params=new URLSearchParams(location.search),selected=catalog.find(s=>s.sample===params.get('story'))||catalog[0];
 selectStory(selected,params.get('version')==='enhanced'&&selected?.enhancedAvailable?'enhanced':'source');
}catch(error){showNotice('载入失败：'+error.message);$('#load-error').hidden=false;console.error(error);}
window.addEventListener('pagehide',event=>{if(event.persisted)return;destroyed=true;seekRequest++;cancelClipPlayback();clearTimeout(rightTimer);clearTimeout(leftTimer);clearTimeout(idleTimer);clearTimeout(noticeTimer);unsubscribeConfig();inspector?.destroy();glass?.destroy();layout.destroy();controls.destroy();court.destroy();annotations.destroy();video.cancelVideoFrameCallback?.(mediaCallback);video.removeEventListener('timeupdate',frame);});
