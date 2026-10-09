(function () {
  'use strict';
  const C = window.CourtLab;
  const $ = id => document.getElementById(id);
  const video = $('source-video');
  const xmlns = 'http://www.w3.org/2000/svg';
  let dataset = null, mediaTime = 0, stopAtWindowEnd = false, loadVersion = 0, pendingSeek = null, followHolder = false;
  const statusNames = {observed:'采样点', estimated:'估计', inferred:'粗略站位', 'last-known':'最近位置', occluded:'遮挡', offscreen:'画外', unknown:'无数据'};
  const reasonNames = {'outside-window':'分析区间外', 'sampling-gap':'采样间隔过大', 'scene-cut':'镜头切换', 'no-data':'尚未入镜'};
  function element(tag, attrs, text) {
    const node = document.createElementNS(xmlns, tag);
    for (const [key,value] of Object.entries(attrs || {})) node.setAttribute(key,String(value));
    if (text !== undefined) node.textContent = text;
    return node;
  }
  function clock(t) {
    const totalMs = Math.max(0, Math.round((Number.isFinite(t) ? t : 0) * 1000));
    return `${String(Math.floor(totalMs / 60000)).padStart(2,'0')}:${String(Math.floor(totalMs / 1000)%60).padStart(2,'0')}.${String(totalMs%1000).padStart(3,'0')}`;
  }
  function showError(message) { $('load-error').textContent = message; $('load-error').hidden = false; }
  function clearData(message) {
    dataset = null; stopAtWindowEnd = false; pendingSeek = null;
    $('replay-window').disabled = true; $('seek-window').disabled = true;
    $('player-filter').replaceChildren(new Option('全部球员','all'));
    $('data-warning').textContent = message;
    $('data-method').textContent = '';
    $('source-hash').textContent = 'SOURCE SHA-256 / 等待核对';
    render(video.currentTime);
  }
  function useDataset(data, imported) {
    dataset = C.validateDataset(data); stopAtWindowEnd = false; pendingSeek = null;
    const schematic = dataset.presentation === 'schematic';
    $('presentation-title').textContent = schematic ? '战术示意回放 · 依据画面编辑 · 非官方追踪数据' : '实验功能 · 人工初始化 + 视频估计 · 非官方追踪数据';
    $('presentation-warning').textContent = schematic ? '全片编辑站位与球权同步回放。淡色空心点保留最近位置；篮球与虚线为战术示意。' : '人工初始化与视频估计同步呈现，画外和遮挡位置留空。';
    $('legend-estimate').textContent = schematic ? '虚线：示意轨迹' : '虚线：插值 / 估计';
    $('interpolation-note').textContent = schematic ? `同镜头、相邻编辑锚点间隔不超过 ${dataset.schematic?.maxGapSeconds || 0.6} 秒时显示示意插值；遮挡与切镜处不连接轨迹。${dataset.schematic?.holdLastKnown ? '淡色空心点只保留过去的最近位置，不表示仍在原处，也不延长轨迹。' : '未记录位置保持空白。'}篮球图标只表示战术球路，编号未经过人类专家身份核对。` : '采样点与估计点分别呈现。遮挡、画外、镜头切换及超过 0.15 秒的采样间隔会断开。稀疏关键帧只在前后 0.05 秒显示快照；未核对编号不代表已识别 NBA 球员姓名。';
    $('load-error').hidden = true;
    $('data-warning').textContent = dataset.provenance.warning;
    const method = dataset.provenance.method.replace(/[。.!！]+\s*$/,'');
    $('data-method').textContent = `${imported ? '本地导入' : '本地样片'} · ${method}。匿名编号仅用于区分跟踪对象；所有坐标均为实验记录。`;
    $('source-hash').textContent = `SOURCE SHA-256 / ${dataset.sourceSha256}`;
    $('seek-window').textContent = `↶ 回到 ${dataset.window[0].toFixed(3)} 秒`;
    $('replay-window').textContent = dataset.window[0] === 0 ? '▶ 回放整段视频' : '▶ 播放分析片段';
    $('chapter-jumps').replaceChildren();
    if (dataset.window[0] === 0 && dataset.possession) {
      for (const [label, time] of [['推进',0.2002],['掩护',6.006011],['突破',13.013],['出手',16.8],['发球',20.6],['换边',21.2]]) {
        if (time > dataset.window[1]) continue;
        const button = document.createElement('button'); button.textContent = label;
        button.addEventListener('click',()=>{stopAtWindowEnd=false;video.pause();video.currentTime=time;if(time<4)setCourtView(false);render(time);});
        $('chapter-jumps').append(button);
      }
    }
    setCourtView(dataset.window[0] !== 0);
    const options = [new Option('全部球员','all')];
    for (const track of dataset.tracks) options.push(new Option(`${track.label}${track.identityStatus==='anonymous' ? ' · 匿名编号':''}`, String(track.id)));
    $('player-filter').replaceChildren(...options);
    if (!imported) { video.pause(); pendingSeek = dataset.window[0]; }
    syncMediaReady();
    render(video.currentTime);
  }
  function syncMediaReady() {
    const ready = video.readyState >= 1 && Number.isFinite(video.duration) && video.duration > 0;
    $('replay-window').disabled = !dataset || !ready;
    $('seek-window').disabled = !dataset || !ready;
    if (!dataset || !ready) return;
    if (dataset.window[1] > video.duration + 0.01) {
      clearData('记录的分析区间超过了已加载原片的时长；球场留空。');
      showError('分析时段与实际原片时长不一致。');
      return;
    }
    if (pendingSeek !== null) {
      video.pause();
      video.currentTime = Math.min(pendingSeek,video.duration);
      pendingSeek = null;
    }
  }
  async function loadDefault() {
    const version = ++loadVersion;
    clearData('正在读取本地实验记录。真实记录加载前不生成位置或轨迹。');
    $('load-error').hidden = true;
    try {
      const response = await fetch('./flagg.json',{cache:'no-store'});
      if (!response.ok) throw new Error(`实验记录暂不可用（HTTP ${response.status}）。`);
      const data = await response.json();
      if (version !== loadVersion) return;
      useDataset(data,false);
    } catch (error) {
      if (version !== loadVersion) return;
      clearData('尚未加载可用的真实实验记录。你可以播放原片，或导入经过核对的位置 JSON。');
      showError(`${error.message} 球场保持空白，未生成模拟数据。`);
    }
  }
  function visibleTrack(track) {
    return $('team-filter').value === 'all' || track.team === $('team-filter').value;
  }
  function render(t) {
    if (dataset && stopAtWindowEnd && t >= dataset.window[1]) {
      stopAtWindowEnd = false;
      video.pause();
      video.currentTime = dataset.window[1];
      t = dataset.window[1];
    }
    mediaTime = t;
    $('video-clock').textContent = clock(t);
    $('trail-layer').replaceChildren(); $('player-layer').replaceChildren(); $('ball-layer').replaceChildren(); $('foot-overlay').replaceChildren();
    $('player-status').replaceChildren();
    if (!dataset) {
      $('court-empty').hidden = false; $('court-empty').textContent = '等待真实位置记录';
      $('position-count').textContent = '等待站位';
      $('trail-caption').textContent = 'TRAIL / 等待回合';
      $('possession-title').textContent = '等待球权记录'; $('possession-note').textContent = '与原片同步更新'; $('scene-state').textContent = ''; $('tactic-heading').textContent = '等待回合解析'; $('tactic-copy').textContent = '播放视频，逐段查看站位与球权。'; $('chapter-jumps').replaceChildren();
      $('window-state').textContent = '分析区间：等待数据';
      $('player-status').textContent = '没有加载球员记录。不会补齐十人或推测画外位置。';
      return;
    }
    const inWindow = t >= dataset.window[0] - 1e-6 && t <= dataset.window[1] + 1e-6;
    const schematic = dataset.presentation === 'schematic';
    const samples = C.samplePositions(dataset,t).filter(visibleTrack);
    const ball = C.sampleBall(dataset,t);
    const scene = C.sceneAt(dataset,t);
    const route = C.trailFocus(dataset,t,$('player-filter').value);
    const focus = followHolder && route.id !== null ? route.id : $('player-filter').value;
    const length = $('trail-length').value;
    const seconds = length === 'all' ? dataset.window[1]-dataset.window[0] : Number(length)||3;
    const trailSeconds = route.start === null ? 0 : Math.min(seconds,Math.max(0,t-route.start));
    $('trail-caption').textContent = !$('show-trails').checked ? 'TRAIL / 已隐藏' : route.id === null ? 'TRAIL / 无球员主线 · 可点选单人' : `TRAIL / ${route.id} · ${length==='all'?'ALL':seconds+' SEC'} · ${route.mode==='possession'?'球权主线':'单人路线'}`;
    let count = 0, interpolated = 0, snapshots = 0, held = 0;
    const stateLabel = point => point.status === 'last-known' ? `最近位置 · ${Math.max(0,t-point.sourceTime).toFixed(1)} 秒前` : point.snapshot ? `快照 ${clock(point.t)}` : point.interpolated ? (schematic ? '示意插值' : '插值') : reasonNames[point.reason] || statusNames[point.status] || '无数据';
    for (const point of samples) {
      const hasPoint = point.x !== null && point.y !== null;
      const focused = focus === 'all' || String(point.id) === focus;
      const color = point.team === 'dark' ? '#f18143' : '#f7f0e2';
      if (hasPoint) {
        count++; if (point.status === 'last-known') held++; if (point.interpolated) interpolated++; if (point.snapshot) snapshots++;
        if ($('show-trails').checked && String(point.id) === route.id && trailSeconds > 0) {
          const track = dataset.tracks.find(item => String(item.id) === String(point.id));
          for (const line of C.collectTrails(track,t,trailSeconds,dataset)) {
            const age = Math.max(0,t-(line.points[0].t+line.points[1].t)/2);
            const opacity = 0.22+0.5*Math.max(0,1-age/trailSeconds);
            $('trail-layer').append(element('polyline',{points:line.points.map(item=>C.courtToSvg(item.x,item.y).join(',')).join(' '),stroke:color,class:`trail ${line.status}`,style:`opacity:${opacity.toFixed(3)}`,'data-player':String(point.id),'data-start':line.points[0].t,'data-end':line.points[1].t}));
          }
        }
        const [x,y] = C.courtToSvg(point.x,point.y);
        const isHolder = ball.phase === 'held' && ball.holder !== null && String(ball.holder) === String(point.id);
        const pointStatus = stateLabel(point);
        const dot = element('g',{class:`player-dot ${point.status}${focused?'':' is-dim'}`,transform:`translate(${x} ${y})`,role:'button',tabindex:'0','aria-label':`${point.label}，${pointStatus}${isHolder?'，持球人':''}`});
        dot.append(element('circle',{r:13,fill:color,stroke:point.status==='last-known'?color:'#22231f','stroke-width':2}));
        if (isHolder) dot.append(element('circle',{r:23,class:'holder-ring'}));
        if (focus !== 'all' && focused) dot.append(element('circle',{r:19,class:'dot-ring'}));
        const shortId = String(point.id);
        dot.append(element('text',{'text-anchor':'middle',dy:4,fill:'#22231f'},shortId));
        dot.append(element('title',{},`${point.label} · ${point.x.toFixed(1)}, ${point.y.toFixed(1)} ft · ${pointStatus}${point.reviewed ? ' · 已核对' : ' · 未核对'}`));
        const select = () => { $('player-filter').value = String(point.id); followHolder=false; $('focus-holder').setAttribute('aria-pressed','false'); render(mediaTime); };
        dot.addEventListener('click',select); dot.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}});
        $('player-layer').append(dot);
        if (point.image && focused) {
          const [ix,iy] = point.image;
          $('foot-overlay').append(element('ellipse',{cx:ix,cy:iy,rx:16,ry:5,stroke:isHolder?'#ffc85c':color,class:'foot-mark','stroke-dasharray':point.status==='estimated'?'4 3':'none'}));
          $('foot-overlay').append(element('text',{x:ix+20,y:iy-7,class:'foot-label'},shortId));
        }
      }
      const chip = document.createElement('span');
      chip.className = `status-chip${hasPoint?'':' is-missing'}${point.status==='last-known'?' is-ghost':''}${ball.phase==='held'&&ball.holder!==null&&String(ball.holder)===String(point.id)?' is-held':''}${focus!=='all'&&focused?' is-focus':''}`;
      const name = document.createElement('span'); name.textContent = `${point.label}${ball.phase==='held'&&ball.holder!==null&&String(ball.holder)===String(point.id)?' · 持球':''}`;
      const state = document.createElement('em'); state.textContent = stateLabel(point);
      chip.append(name,state); $('player-status').append(chip);
    }
    if (!samples.length) $('player-status').textContent = '当前筛选没有球员记录。';
    $('position-count').textContent = `${count-held} 更新 / ${held} 最近位置`;
    const phases = {held:'持球',pass:'传球中',shot:'出手 · 球在空中',score:'命中',change:'球权交接',unknown:'暂未确认持球'};
    const holderLabel = dataset.tracks.find(item=>ball.holder!==null&&String(item.id)===String(ball.holder))?.label;
    $('possession-title').textContent = `${holderLabel ? holderLabel+' · ' : ''}${phases[ball.phase] || phases.unknown}`;
    $('possession-note').textContent = `${ball.label || '尚未编辑这一时段的球权'}${ball.status==='last-known' ? ' · 持球位置使用最近站位' : ''}`;
    const chapter = dataset.window[0]===0 && dataset.possession ? (
      t<0.0667334 ? ['片头 / 回到现场','特写不提供球场坐标。宽镜头出现后，站位与原片同步展开。'] :
      t<6 ? ['01 / 持球推进','D5 从后场推进；两侧球员逐渐进入画面。全场视窗可以看清推进距离与队伍展开。'] :
      t<12 ? ['02 / 掩护与空间','D4 来到持球人附近，D5 在外线控球。对照原片观察两人的相对站位与防守移动。'] :
      t<16.8 ? ['03 / 向篮筐突破','D5 从外线向左侧篮筐移动。关注持球高亮和队友站位，看这一回合的空间如何变化。'] :
      t<17.35 ? ['04 / 出手','D5 完成上篮出手，球权状态切为“球在空中”。图标向篮筐的路线是战术示意。'] :
      t<17.75 ? ['05 / 命中与换边','篮球进入篮网，随后由白色队收球。此时没有继续给进攻球员显示持球高亮。'] :
      t<20.6 ? ['06 / 底线发球准备','W3 收球并准备从底线发球。端线外的位置以端线示意点呈现。'] :
      t<21.2 ? ['07 / 发球传递','W3 向 W2 发球；球在传递中，两人都不会同时显示为持球人。'] :
      ['08 / 新的进攻开始','W2 接球并开始推进，持球高亮随球权转换到白色队。']
    ) : ['站位回放','观察匿名编号与原片的相对站位；轨迹为编辑示意。'];
    $('tactic-heading').textContent = chapter[0]; $('tactic-copy').textContent = chapter[1];
    $('scene-state').textContent = scene ? (scene.type==='closeup' ? `${scene.label || '片头特写'} · 等待宽镜头站位` : `${scene.label || '比赛宽镜头'} · 球权依据原片编辑核对`) : '';
    if (ball.x !== null && ball.y !== null && Number.isFinite(ball.x) && Number.isFinite(ball.y)) {
      const [bx,by] = C.courtToSvg(ball.x,ball.y);
      const attached = ball.phase === 'held' && ball.holder !== null;
      const symbol = element('g',{class:`ball-mark${ball.status==='last-known'?' is-ghost':''}`,transform:`translate(${bx+(attached?23:0)} ${by-(attached?23:0)})`,'aria-label':`${phases[ball.phase]}，${holderLabel || '篮球球路示意'}`});
      symbol.append(element('circle',{r:9}));
      symbol.append(element('path',{d:'M-9 0H9 M0-9V9 M-6-6Q4 0-6 6 M6-6Q-4 0 6 6'}));
      symbol.append(element('text',{x:14,y:-4},attached?'BALL':phases[ball.phase]));
      $('ball-layer').append(symbol);
      if (!attached && ['shot','pass'].includes(ball.phase)) $('ball-layer').append(element('circle',{cx:bx,cy:by,r:17,class:'ball-target'}));
    }
    $('court-empty').hidden = count > 0;
    $('court-empty').textContent = !inWindow ? '当前时间超出分析区间' : scene?.type==='closeup' ? '片头特写 · 等待宽镜头' : '尚无已记录的站位';
    $('window-state').textContent = `分析区间 ${clock(dataset.window[0])} — ${clock(dataset.window[1])} · ${inWindow ? `${interpolated} 个${schematic ? '示意插值' : '插值点'} / ${snapshots} 个关键帧快照 / ${count-held-interpolated-snapshots} 个${schematic ? '编辑锚点' : '采样点'} / ${held} 个最近位置` : '区间外不延续轨迹'}`;
  }
  $('team-filter').addEventListener('change',()=>render(mediaTime));
  $('player-filter').addEventListener('change',()=>{followHolder=false;$('focus-holder').setAttribute('aria-pressed','false');render(mediaTime);});
  $('show-trails').addEventListener('change',()=>render(mediaTime));
  $('trail-length').addEventListener('change',()=>render(mediaTime));
  $('focus-holder').addEventListener('click',()=>{followHolder=!followHolder;if(followHolder)$('player-filter').value='all';$('focus-holder').setAttribute('aria-pressed',String(followHolder));render(mediaTime);});
  function setCourtView(half) {
    $('court-map').setAttribute('viewBox',half ? '6 6 552 550' : '0 0 1000 560');
    $('court-map').setAttribute('data-view',half ? 'half' : 'full');
    $('court-map').setAttribute('aria-label',half ? 'NBA 俯视球场，进攻半场视窗' : 'NBA 94 × 50 英尺俯视全场');
    $('view-half').setAttribute('aria-pressed',String(half));
    $('view-full').setAttribute('aria-pressed',String(!half));
    $('court-dimension').setAttribute('x',half ? '280' : '500');
    $('court-dimension').textContent = half ? '0–50 FT / ATTACKING HALF' : '94 FT / FULL COURT';
  }
  $('view-half').addEventListener('click',()=>setCourtView(true));
  $('view-full').addEventListener('click',()=>setCourtView(false));
  setCourtView(true);
  $('seek-window').addEventListener('click',()=>{if(!dataset)return;stopAtWindowEnd=false;video.pause();if(dataset.window[0]===0)setCourtView(false);video.currentTime=dataset.window[0];render(video.currentTime);});
  $('replay-window').addEventListener('click',async()=>{if(!dataset)return;stopAtWindowEnd=true;if(dataset.window[0]===0)setCourtView(false);video.currentTime=dataset.window[0];try{await video.play();}catch(error){stopAtWindowEnd=false;showError(`视频播放失败：${error.message}`);}});
  $('half-speed').addEventListener('click',()=>{const half=video.playbackRate!==0.5;video.playbackRate=half?0.5:1;$('half-speed').setAttribute('aria-pressed',String(half));});
  $('restore-data').addEventListener('click',loadDefault);
  $('import-file').addEventListener('change',async event=>{
    const file = event.target.files[0]; if(!file)return;
    const version=++loadVersion;
    try{
      if(file.size>10*1024*1024)throw new Error('记录文件超过 10 MB，请缩短分析时段。');
      const parsed=JSON.parse(await file.text());
      if(version!==loadVersion)return;
      useDataset(parsed,true);
    }catch(error){if(version!==loadVersion)return;clearData('导入记录没有通过校验；球场留空。');showError(`无法导入：${error.message}`);}
    event.target.value='';
  });
  video.addEventListener('error',()=>showError('原片暂不可读取。请保持本地预览服务运行，并核对媒体存档。'));
  video.addEventListener('loadedmetadata',()=>{syncMediaReady();render(video.currentTime);});
  for(const event of ['seeked','pause','timeupdate','ended'])video.addEventListener(event,()=>render(video.currentTime));
  if(typeof video.requestVideoFrameCallback==='function'){
    const frame = (now,metadata) => {render(metadata.mediaTime);video.requestVideoFrameCallback(frame);};
    video.requestVideoFrameCallback(frame);
  }
  // Without requestVideoFrameCallback, video events remain the only clock.
  loadDefault();
})();
