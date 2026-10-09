(function () {
  'use strict';
  const C = window.CourtLab;
  const $ = id => document.getElementById(id);
  const video = $('source-video');
  const xmlns = 'http://www.w3.org/2000/svg';
  let dataset = null, mediaTime = 0, stopAtWindowEnd = false, loadVersion = 0, pendingSeek = null;
  const statusNames = {observed:'采样点', estimated:'估计', occluded:'遮挡', offscreen:'画外', unknown:'无数据'};
  const reasonNames = {'outside-window':'分析区间外', 'sampling-gap':'采样间隔过大', 'scene-cut':'镜头切换', 'no-data':'无对应采样'};
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
    $('presentation-warning').textContent = schematic ? '站位取自比赛关键帧，虚线为示意轨迹。编号用于区分两队球员。' : '人工初始化与视频估计同步呈现，画外和遮挡位置留空。';
    $('legend-estimate').textContent = schematic ? '虚线：示意轨迹' : '虚线：插值 / 估计';
    $('interpolation-note').textContent = schematic ? '同镜头、两端可见且间隔不超过 0.6 秒的编辑锚点之间显示示意插值。遮挡、画外或镜头切换会断开，不推测锚点范围外的位置。未核对编号不代表球员姓名。' : '采样点与估计点分别呈现。遮挡、画外、镜头切换及超过 0.15 秒的采样间隔会断开。稀疏关键帧只在前后 0.05 秒显示快照；未核对编号不代表已识别 NBA 球员姓名。';
    $('load-error').hidden = true;
    $('data-warning').textContent = dataset.provenance.warning;
    const method = dataset.provenance.method.replace(/[。.!！]+\s*$/,'');
    $('data-method').textContent = `${imported ? '本地导入' : '本地样片'} · ${method}。匿名编号仅用于区分跟踪对象；所有坐标均为实验记录。`;
    $('source-hash').textContent = `SOURCE SHA-256 / ${dataset.sourceSha256}`;
    $('seek-window').textContent = `↶ 回到 ${dataset.window[0].toFixed(3)} 秒`;
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
    $('trail-layer').replaceChildren(); $('player-layer').replaceChildren(); $('foot-overlay').replaceChildren();
    $('player-status').replaceChildren();
    if (!dataset) {
      $('court-empty').hidden = false; $('court-empty').textContent = '等待真实位置记录';
      $('position-count').textContent = '0 / 可见';
      $('window-state').textContent = '分析区间：等待数据';
      $('player-status').textContent = '没有加载球员记录。不会补齐十人或推测画外位置。';
      return;
    }
    const inWindow = t >= dataset.window[0] - 1e-6 && t <= dataset.window[1] + 1e-6;
    const schematic = dataset.presentation === 'schematic';
    const samples = C.samplePositions(dataset,t).filter(visibleTrack);
    const focus = $('player-filter').value;
    let count = 0, interpolated = 0, snapshots = 0;
    for (const point of samples) {
      const hasPoint = point.x !== null && point.y !== null;
      const focused = focus === 'all' || String(point.id) === focus;
      const color = point.team === 'dark' ? '#f18143' : '#f7f0e2';
      if (hasPoint) {
        count++; if (point.interpolated) interpolated++; if (point.snapshot) snapshots++;
        if ($('show-trails').checked && focused) {
          const track = dataset.tracks.find(item => String(item.id) === String(point.id));
          for (const line of C.collectTrails(track,t,1,dataset.presentation)) {
            $('trail-layer').append(element('polyline',{points:line.points.map(item=>C.courtToSvg(item.x,item.y).join(',')).join(' '),stroke:color,class:`trail ${line.status}`}));
          }
        }
        const [x,y] = C.courtToSvg(point.x,point.y);
        const pointStatus = point.snapshot ? `关键帧快照 ${clock(point.t)}` : (point.interpolated ? (schematic ? '示意插值' : '插值估计') : (schematic ? '编辑锚点' : statusNames[point.status]));
        const dot = element('g',{class:`player-dot ${point.status}${focused?'':' is-dim'}`,transform:`translate(${x} ${y})`,role:'button',tabindex:'0','aria-label':`${point.label}，${pointStatus}`});
        dot.append(element('circle',{r:13,fill:color,stroke:'#22231f','stroke-width':2}));
        if (focus !== 'all' && focused) dot.append(element('circle',{r:19,class:'dot-ring'}));
        const shortId = String(point.id);
        dot.append(element('text',{'text-anchor':'middle',dy:4,fill:'#22231f'},shortId));
        dot.append(element('title',{},`${point.label} · ${point.x.toFixed(1)}, ${point.y.toFixed(1)} ft · ${pointStatus}${point.reviewed ? ' · 已核对' : ' · 未核对'}`));
        const select = () => { $('player-filter').value = String(point.id); render(mediaTime); };
        dot.addEventListener('click',select); dot.addEventListener('keydown',event=>{if(event.key==='Enter'||event.key===' '){event.preventDefault();select();}});
        $('player-layer').append(dot);
        if (point.image && focused) {
          const [ix,iy] = point.image;
          $('foot-overlay').append(element('ellipse',{cx:ix,cy:iy,rx:16,ry:5,stroke:color,class:'foot-mark','stroke-dasharray':point.status==='estimated'?'4 3':'none'}));
          $('foot-overlay').append(element('text',{x:ix+20,y:iy-7,class:'foot-label'},shortId));
        }
      }
      const chip = document.createElement('span');
      chip.className = `status-chip${hasPoint?'':' is-missing'}${focus!=='all'&&focused?' is-focus':''}`;
      const name = document.createElement('span'); name.textContent = point.label;
      const state = document.createElement('em'); state.textContent = point.snapshot ? `快照 ${clock(point.t)}` : (point.interpolated ? (schematic ? '示意插值' : '插值') : (reasonNames[point.reason] || (schematic && hasPoint ? '编辑锚点' : statusNames[point.status]) || '无数据'));
      chip.append(name,state); $('player-status').append(chip);
    }
    if (!samples.length) $('player-status').textContent = '当前筛选没有球员记录。';
    $('position-count').textContent = `${count} / ${samples.length} 可见`;
    $('court-empty').hidden = count > 0;
    $('court-empty').textContent = !inWindow ? '当前时间超出分析区间' : '当前帧没有可投影的位置';
    $('window-state').textContent = `分析区间 ${clock(dataset.window[0])} — ${clock(dataset.window[1])} · ${inWindow ? `${interpolated} 个${schematic ? '示意插值' : '插值点'} / ${snapshots} 个关键帧快照 / ${count-interpolated-snapshots} 个${schematic ? '编辑锚点' : '采样点'}` : '区间外不延续轨迹'}`;
  }
  $('team-filter').addEventListener('change',()=>render(mediaTime));
  $('player-filter').addEventListener('change',()=>render(mediaTime));
  $('show-trails').addEventListener('change',()=>render(mediaTime));
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
  $('seek-window').addEventListener('click',()=>{if(!dataset)return;stopAtWindowEnd=false;video.pause();video.currentTime=dataset.window[0];render(video.currentTime);});
  $('replay-window').addEventListener('click',async()=>{if(!dataset)return;stopAtWindowEnd=true;video.currentTime=dataset.window[0];try{await video.play();}catch(error){stopAtWindowEnd=false;showError(`视频播放失败：${error.message}`);}});
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
