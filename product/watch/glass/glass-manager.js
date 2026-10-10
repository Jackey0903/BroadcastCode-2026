import liquidGL from '../vendor/liquid-gl/liquidGL.js';
// All library-specific behavior and inspection is isolated here.
export class GlassManager {
 constructor(stage,getConfig,{enabled=false,onModeChange=()=>{}}={}){this.stage=stage;this.getConfig=getConfig;this.lenses=new Map();this.errors=[];this.ready=false;this.enabled=enabled;this.onModeChange=onModeChange;}
 start(){
  if(!this.enabled){this.ready=true;this.stage.dataset.glass='css';this.apply();return;}
  if(this.lenses.size)return;this.ready=false;
  try{
   for(const el of this.stage.querySelectorAll('.glass-target')){
    if(!el.id)el.id='glass-'+this.lenses.size;
    const lens=liquidGL({target:'#'+el.id,snapshot:'#scene',engine:'auto',resolution:1,content:false,zIndex:25,refraction:.012,aberration:0,bevelDepth:.08,bevelWidth:.15,frost:2,tint:'rgba(20,24,34,.38)',shadow:false,specular:true,reveal:'none',tilt:false,draggable:false,interaction:'none',on:{init:()=>{if(!this.enabled||this.ready)return;this.ready=true;this.stage.dataset.glass='gpu';this.onModeChange(true);}}});
    this.lenses.set(el,lens);
   }
   liquidGL.registerDynamic('#ambience');this.apply();
  }catch(error){this.errors.push(String(error));this.stage.dataset.glass='css-fallback';}
 }
 scope(el){if(el.closest('.content-sheet'))return 'content';if(el.closest('.popover,.rate-menu'))return 'menus';if(el.closest('.left-drawer'))return 'dock';if(el.closest('#court-shell'))return el.closest('#court-shell').dataset.component==='fullCourt'?'fullCourt':'halfCourt';if(el.closest('#controls-host'))return 'controls';if(el.closest('#moment-heading'))return 'heading';if(el.closest('#top-tabs'))return 'topbar';return 'glass';}
 apply(){const c=this.getConfig();
  // CSS uses a lighter tint mapping; saved liquidGL presets remain untouched.
  for(const el of this.stage.querySelectorAll('.glass-target')){
   const scope=this.scope(el),group=c[scope]||c.glass,base=c.glass;
   const hex=/^#[0-9a-f]{6}$/i.test(group.tint||'')?group.tint:'#141822';
   const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));
   const alpha=group.tintAlpha??base.tintAlpha;
   el.style.setProperty('--material-tint',`rgba(${rgb.join(',')},${alpha*.28})`);
   el.style.setProperty('--material-solid',`rgba(${rgb.join(',')},${scope==='content'?Math.max(.42,alpha*.85):alpha*.65})`);
   el.style.setProperty('--material-accent',group.paintColor||'#52658a');
   el.style.setProperty('--material-blur',`${Math.min(10,6+(group.frost??base.frost))}px`);
  }
 for(const [el,lens] of this.lenses){const group=c[this.scope(el)]||c.glass;const base=c.glass;const color=group.tint||'#141822';const hex=/^#[0-9a-f]{6}$/i.test(color)?color:'#141822';const rgb=[1,3,5].map(i=>parseInt(hex.slice(i,i+2),16));lens?.setOptics?.({refraction:group.refraction??base.refraction,frost:group.frost??base.frost,bevelDepth:group.bevelDepth??base.bevelDepth,bevelWidth:group.bevelWidth??base.bevelWidth});lens?.setTint?.(`rgba(${rgb.join(',')},${group.tintAlpha??base.tintAlpha})`);}}
 status(){const reports=[...this.lenses.values()].map(l=>l?.getRenderStatus?.()||{backend:'css-fallback'});const backends=[...new Set(reports.map(r=>r.backend))];return {library:'liquid-gl',version:'3.0.0',sourceCommit:'88f681ab7035fd55b04f63edff1841e32c4199e9',vendorPatch:'broadcastcode-optics-smooth-v5',mode:this.enabled?(reports.some(r=>r.textureReady&&r.backend!=='css-fallback')?'liquid':'css-fallback'):'css',backend:this.enabled?(backends.join(',')||'css-fallback'):'css',ambience:this.enabled?'video-derived':'static-gradient',initialized:[...this.lenses.values()].some(l=>!!l?.renderer?.backend),renderers:new Set([...this.lenses.values()].map(l=>l?.renderer).filter(r=>r&&!r._destroyed&&r.backend)).size,ready:this.ready,enabled:this.enabled,lenses:this.lenses.size,canvases:this.stage.querySelectorAll('canvas[data-liquid-ignore]').length,reports,errors:this.errors,devicePixelRatio:devicePixelRatio,viewport:[innerWidth,innerHeight],userAgent:navigator.userAgent};}
 setEnabled(enabled){if(enabled===this.enabled)return;this.enabled=enabled;if(enabled){this.start();}else{this.destroy();this.start();}this.onModeChange(this.enabled);}
 destroy(){for(const lens of this.lenses.values())lens?.destroy?.();this.lenses.clear();}
}
