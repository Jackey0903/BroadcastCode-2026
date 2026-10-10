// One geometry owner: every frame reserves the court rectangle before fitting video.
export const clamp=(n,a=0,b=1)=>Math.max(a,Math.min(b,n));
export const mix=(a,b,t)=>a+(b-a)*t;
export function fitContain(width,height,aspect){const w=Math.min(width,height*aspect);return {width:w,height:w/aspect};}
export function geometry(width,height,aspect,open,half,config){
 const {padding,gap,dockWidth,fullWidth,halfWidth}=config.layout;
 const panelWidth=width*mix(fullWidth,halfWidth,half)*open;
 const left=(padding+dockWidth+12)*open;
 const right=(padding+gap)*open+panelWidth;
 const top=110*open, bottom=116*open;
 const slotWidth=Math.max(1,width-left-right),slotHeight=Math.max(1,height-top-bottom);
 const fitted=fitContain(slotWidth,slotHeight,aspect);
 const video={x:left+(slotWidth-fitted.width)/2,y:top+(slotHeight-fitted.height)/2,...fitted};
 const panel={x:width-padding*open-panelWidth,y:padding,width:panelWidth,height:height-2*padding};
 // Reserve the left corner for the 120px ambient character plus a 20px gap.
 const controlLeft=Math.max(156,mix(Math.max(24,width*.065),left,open));
 const controlRight=mix(width*.935,width-right,open);
 const controls={x:controlLeft,y:mix(height-190,height-100,open),width:Math.max(1,Math.min(controlRight,panel.x-gap*open)-controlLeft),height:config.controls?.height||66};
 return {video,panel,controls,open,half,width,height};
}
export function createStageLayout({stage,video,surface,panel,controls,onFrame,config}){
 let open=0,half=0,raf=0,destroyed=false,current=null,mode='immersive',phase='closed';
 const reduced=matchMedia('(prefers-reduced-motion: reduce)');
 function draw(){
  current=geometry(stage.clientWidth,stage.clientHeight,video.videoWidth/video.videoHeight||16/9,open,half,config());
  for(const [el,rect] of [[surface,current.video],[panel,current.panel],[controls,current.controls]]){el.style.left=rect.x+'px';el.style.top=rect.y+'px';el.style.width=rect.width+'px';el.style.height=rect.height+'px';}
  panel.style.opacity=String(clamp(open*4));panel.inert=open<.01;panel.style.visibility=open<.001?'hidden':'visible';
  stage.style.setProperty('--open',open);stage.dataset.layout=mode;stage.dataset.phase=phase;
  onFrame?.(current);
 }
 function to(target,{automatic=false,immediate=false}={}){
  cancelAnimationFrame(raf);mode=target;const o=target==='immersive'?0:1,h=target==='halfCourt'?1:0;
  const startO=open,startH=half,start=performance.now();phase=o?'opening':'closing';
  const duration=immediate||reduced.matches?0:target==='immersive'?config().motion.close:automatic?config().motion.open:config().motion.morph;
  function tick(now){if(destroyed)return;const t=duration?clamp((now-start)/duration):1,e=1-Math.pow(1-t,3);
   // First ~80ms reveals a tall full court. The same clock then continuously zooms it.
   if(automatic&&startO<.01){open=1-Math.pow(1-clamp(t/.70),3);const z=clamp(t/.95);half=z*z*(3-2*z);}else {open=mix(startO,o,e);half=mix(startH,h,e);}
   if(t>=1){open=o;half=h;phase=o?'open':'closed';}draw();if(t<1)raf=requestAnimationFrame(tick);
  }raf=requestAnimationFrame(tick);
 }
 const observer=new ResizeObserver(draw);observer.observe(stage);video.addEventListener('loadedmetadata',draw);draw();
 return {to,draw,get rects(){return current},get mode(){return mode},get phase(){return phase},destroy(){destroyed=true;cancelAnimationFrame(raf);observer.disconnect();video.removeEventListener('loadedmetadata',draw);}};
}
