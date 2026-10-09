"use strict";

(() => {
  const $ = (id) => document.getElementById(id);
  const KNOWN = new Set(["flagg", "amen"]);
  const KINDS = { observation: "画面观察", official: "官方数据", interpretation: "篮球解读" };
  const STORE = "hidden-play-studio-job-v1";
  const state = { stories: [], story: null, version: "source", phase: "watch", choice: null, panel: "story", view: "watch", theater: false, mediaToken: 0, serviceReady: false, available: new Set(), sampleListKnown: false, busy: false, submitting: false, polling: false, jobId: null, jobSample: null, timer: null, pollErrors: 0, pollStart: 0, resultUrl: null, offline: false };
  const video = $("story-video");
  const text = (value, fallback = "") => ["string", "number", "boolean"].includes(typeof value) ? String(value) : fallback;
  const array = (value) => Array.isArray(value) ? value : [];
  const number = (value) => value !== null && value !== "" && Number.isFinite(Number(value)) ? Number(value) : null;
  const time = (value) => { const n = Math.max(0, number(value) || 0); return `${String(Math.floor(n / 60)).padStart(2, "0")}:${String(Math.floor(n % 60)).padStart(2, "0")}`; };
  const node = (tag, className, content) => { const el = document.createElement(tag); if (className) el.className = className; if (content !== undefined) el.textContent = text(content); return el; };
  const announce = (message) => { $("page-announcement").textContent = message; };
  function url(value) {
    if (typeof value !== "string" || !value.trim()) return null;
    try { const parsed = new URL(value, location.origin); return ["http:", "https:"].includes(parsed.protocol) ? parsed.href : null; } catch { return null; }
  }
  function link(label, href) { const a = node("a", "text-link", label); const safe = url(href); if (!safe) return null; a.href = safe; a.target = "_blank"; a.rel = "noopener noreferrer"; return a; }
  function normalise(raw) {
    const story = raw && typeof raw === "object" ? raw : {};
    return { ...story, title: text(story.title, "回到关键一拍"), subtitle: text(story.subtitle), player: story.player || {}, game: story.game || {}, hook: story.hook || {}, chapters: array(story.chapters).filter((c) => c && number(c.start) !== null && number(c.end) !== null && Number(c.end) > Number(c.start)).sort((a,b) => Number(a.start) - Number(b.start)), evidence: array(story.evidence).filter((e) => e && typeof e === "object"), officialEvent: story.officialEvent || {} };
  }
  function setView(name, focus = false) {
    const view = name === "create" ? "create" : "watch";
    state.view = view;
    $("watch-view").hidden = view !== "watch";
    $("create-view").hidden = view !== "create";
    document.querySelectorAll(".main-nav [data-view]").forEach((button) => { const active = button.dataset.view === view; button.classList.toggle("active", active); if (active) button.setAttribute("aria-current", "page"); else button.removeAttribute("aria-current"); });
    if (view === "create") { video.pause(); if (!state.serviceReady) checkService(); }
    else $("generated-video").pause();
    if (focus) { const heading = view === "create" ? $("create-title") : $("story-title"); heading.tabIndex = -1; heading.focus({ preventScroll: true }); window.scrollTo({ top: 0, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "instant" : "smooth" }); }
  }
  function renderSelectors() {
    $("story-selector").replaceChildren(); $("create-samples").replaceChildren();
    $("case-count").textContent = `${String(state.stories.length).padStart(2, "0")} STORIES / 真实比赛`;
    state.stories.forEach((story, index) => {
      const button = node("button", "story-select"); button.type = "button"; button.dataset.story = story.id; button.setAttribute("aria-pressed", "false");
      const image = node("img"); const poster = url(story.poster); if (poster) image.src = poster; image.alt = ""; image.loading = "eager";
      const copy = node("span"); copy.append(node("span", "case-meta", `${String(index + 1).padStart(2, "0")} / ${text(story.player.team, "NBA")} · ${time(story.durationSeconds)}`), node("span", "case-title", story.title));
      button.append(image, copy, node("span", "case-arrow", "↗")); button.addEventListener("click", () => selectStory(story.id)); $("story-selector").append(button);
      const label = node("label", "create-sample"); const input = node("input"); input.type = "radio"; input.name = "sample"; input.value = story.id; input.checked = index === 0; input.addEventListener("change", syncCreate);
      const thumb = image.cloneNode(); const words = node("span"); words.append(node("strong", "", `${text(story.player.name, story.id)} · ${text(story.player.team, "比赛片段")}`), node("small", "", `${time(story.durationSeconds)} / ${story.game.date ? `${text(story.game.date)} 北京时间` : "真实比赛画面"}`));
      label.append(input, thumb, words); $("create-samples").append(label);
    });
    syncCreate();
  }
  function selectStory(id) {
    const story = state.stories.find((item) => item.id === id); if (!story) return;
    state.story = story; state.choice = null; state.phase = "watch";
    $("court-lab-link").hidden = !(state.offline && id === "flagg");
    document.querySelectorAll(".story-select").forEach((button) => { const active = button.dataset.story === id; button.classList.toggle("active", active); button.setAttribute("aria-pressed", String(active)); });
    $("story-index").textContent = `PLAY ${String(state.stories.indexOf(story) + 1).padStart(2,"0")} / ${text(story.player.team, "NBA")}`;
    $("story-title").textContent = story.title; $("story-subtitle").textContent = story.subtitle;
    $("story-kicker").textContent = text(story.kicker, "NBA · THE HIDDEN PLAY");
    const g = story.game; const eventTime = [number(g.period) !== null ? `第${Number(g.period)}节` : text(g.period), text(g.clock)].filter(Boolean).join(" "); $("story-game").textContent = [`${story.officialEvent.verified === true ? "官方事件" : "比赛片段"}${eventTime ? ` ${eventTime}` : ""}`, g.score ? `得分后 ${text(g.score)}` : ""].filter(Boolean).join(" · ");
    $("hook-question").textContent = text(story.hook.question, "这次进攻，你首先关注谁？");
    $("takeaway").textContent = text(story.takeaway, "回到画面，分别核对观察、数据和解读。");
    $("evidence-count").textContent = String(story.evidence.length);
    $("source-download").hidden = !url(story.sourceVideo); if (url(story.sourceVideo)) $("source-download").href = url(story.sourceVideo);
    const input = $("create-form").querySelector(`input[value="${id}"]`); if (input && !state.busy) input.checked = true;
    renderChoices(); renderChapters(); renderOfficial(); renderEvidence(); setPanel("story"); renderPhase(); setMedia("source", 0, false); syncCreate();
    try { const address = new URL(location.href); address.searchParams.set("story", id); history.replaceState(null,"",address); } catch {}
  }
  function setMedia(version, seek = video.currentTime || 0, shouldPlay = !video.paused) {
    if (!state.story) return;
    const enhanced = version === "enhanced"; const source = url(enhanced ? state.story.enhancedVideo : state.story.sourceVideo);
    if (!source) { if (enhanced) announce("这个案例尚无完整增强成片。"); return; }
    state.version = enhanced ? "enhanced" : "source"; video.dataset.version = state.version;
    $("source-mode").classList.toggle("active", !enhanced); $("source-mode").setAttribute("aria-pressed", String(!enhanced));
    $("enhanced-mode").classList.toggle("active", enhanced); $("enhanced-mode").setAttribute("aria-pressed", String(enhanced)); $("enhanced-mode").disabled = !url(state.story.enhancedVideo);
    $("version-note").textContent = url(state.story.enhancedVideo) ? enhanced ? "成片由 Agent 生成，标注已烧录；侧栏为编辑观看指引。切换版本保留时点。" : "正在播放原始比赛画面。完整增强成片可切换观看。" : "正在播放原始画面；这个案例的完整增强成片尚未提供。";
    $("source-download").href = source; $("source-download").hidden = false; $("source-download").textContent = enhanced ? "打开完整成片 ↗" : "打开原片 ↗";
    $("video-alert").hidden = true; $("video-empty").hidden = false; $("chapter-caption").hidden = true;
    const rate = video.playbackRate || 1; const token = ++state.mediaToken; video.pause();
    const poster = url(state.story.poster); if (poster) video.poster = poster; else video.removeAttribute("poster");
    video.onloadedmetadata = () => { if (token !== state.mediaToken) return; $("video-empty").hidden = true; video.currentTime = Math.max(0, Math.min(seek, Number.isFinite(video.duration) ? Math.max(0,video.duration - .01) : seek)); video.playbackRate = rate; updateTimeline(); if (shouldPlay) playVideo(); };
    video.src = source; video.load();
  }
  function playVideo() { const pending = video.play(); if (pending?.catch) pending.catch(() => { announce("请使用播放器的播放按钮继续。"); }); }
  function seekTo(seconds, play = true) {
    if (!state.story || number(seconds) === null) return;
    const target = Math.max(0, Number(seconds));
    if (video.readyState > 0) { video.currentTime = Math.min(target, Math.max(0,(video.duration || state.story.durationSeconds || target + 1) - .01)); if (play) playVideo(); updateTimeline(); }
    else setMedia(state.version,target,play);
  }
  function renderChoices() {
    $("choice-options").replaceChildren();
    const choices = array(state.story.hook.choices);
    choices.forEach((choice) => { const button = node("button", "choice-option", text(choice.label, "选择视角")); button.type = "button"; button.setAttribute("aria-pressed", String(state.choice === choice.id)); button.addEventListener("click", () => { state.choice = choice.id; renderChoices(); $("reveal-play").disabled = false; }); $("choice-options").append(button); });
    $("reveal-play").disabled = choices.length > 0 && !state.choice;
  }
  function renderPhase() {
    $("attention-intro").hidden = state.phase !== "watch"; $("attention-choice").hidden = state.phase !== "choose"; $("reveal-panel").hidden = state.phase !== "reveal";
    ["watch","choose","reveal"].forEach((phase,index) => { const step = $(`step-${phase}`); const current = ["watch","choose","reveal"].indexOf(state.phase); step.classList.toggle("active", index === current); step.classList.toggle("done", index < current); });
    updateTimeline();
  }
  function reveal() {
    if (!state.story || $("reveal-play").disabled) return;
    const choice = array(state.story.hook.choices).find((item) => item.id === state.choice);
    $("reveal-title").textContent = text(choice?.revealTitle, text(state.story.hook.revealTitle, "再看一次，留意关键细节。"));
    $("reveal-body").textContent = text(choice?.revealBody, text(state.story.hook.revealBody, state.story.takeaway));
    $("reveal-panel").querySelector(".eyebrow").textContent = choice?.label ? `你的关注点 / ${text(choice.label)}` : "THE HIDDEN PLAY";
    state.phase = "reveal"; renderPhase(); renderEvidence(); renderFrameComparison(); announce("已揭示关键一拍，可以回到对应时刻核对。");
  }
  function renderFrameComparison() {
    const container=$("comparison-frames");container.replaceChildren();$("frame-comparison").hidden=true;
    // Editorial selection of existing evidence only; these frames imply no inferred motion path or cause.
    const selections={
      flagg:[{id:"flagg-frame-15-5",caption:"接近篮下"},{id:"flagg-frame-16-5",caption:"起跳时，正面防守人举臂"}],
      amen:[{id:"amen-frame-17-5",caption:"防守人已起跳，阿门仍持球"},{id:"amen-frame-18",caption:"阿门起跳出手"}],
    };
    const selected=array(selections[state.story?.id]).map((selection)=>({selection,evidence:array(state.story?.evidence).find((entry)=>entry.id===selection.id)}));
    if(selected.length!==2||selected.some(({evidence})=>!evidence||!url(evidence.frameUrl)||number(evidence.videoTime)===null||Number(evidence.videoTime)<0||Number(evidence.videoTime)>Number(state.story.durationSeconds)))return;
    selected.forEach(({selection,evidence},index)=>{
      const seconds=Number(evidence.videoTime);const button=node("button","comparison-frame");button.type="button";button.dataset.evidenceId=evidence.id;button.setAttribute("aria-pressed","false");button.setAttribute("aria-label",`${seconds.toFixed(1)} 秒，${selection.caption}。定位原片并暂停。`);
      const image=node("img");image.src=url(evidence.frameUrl);image.alt=selection.caption;image.loading="lazy";image.decoding="async";
      const label=node("span","comparison-time");label.append(node("span","",`0${index+1}`),node("span","",`${seconds.toFixed(1)} s`));
      button.append(image,label,node("strong","",selection.caption));
      button.addEventListener("click",()=>{
        video.pause();if(state.version!=="source")setMedia("source",seconds,false);else seekTo(seconds,false);
        Array.from(container.children).forEach((item)=>item.setAttribute("aria-pressed",String(item===button)));
        announce(`已定位原片 ${seconds.toFixed(1)} 秒并暂停。${selection.caption}。`);
      });
      image.addEventListener("error",()=>{image.hidden=true;button.classList.add("frame-unavailable");image.alt="关键帧暂未加载";});
      container.append(button);
    });
    $("frame-comparison").hidden=false;
  }
  function keyTime() {
    const choice = array(state.story?.hook?.choices).find((item) => item.id === state.choice);
    if (number(choice?.focusTime) !== null) return Number(choice.focusTime);
    if (number(choice?.videoTime) !== null) return Number(choice.videoTime);
    const chapter = state.story?.chapters.find((item) => item.id === choice?.chapterId) || state.story?.chapters.find((item) => item.kind === "interpretation") || state.story?.chapters[0];
    return number(state.story?.hook?.videoTime) ?? number(chapter?.start) ?? 0;
  }
  function renderChapters() {
    $("chapter-timeline").replaceChildren(); $("chapter-details").replaceChildren();
    if (!state.story.chapters.length) { $("chapter-timeline").append(node("p","timeline-empty","章节资料尚未加载，仍可完整观看原片。")); return; }
    state.story.chapters.forEach((chapter,index) => {
      const button = node("button","timeline-chapter"); button.type="button"; button.dataset.chapter = chapter.id; button.style.flexGrow = String(Math.max(1, Number(chapter.end) - Number(chapter.start))); button.setAttribute("aria-label", `${time(chapter.start)}，${text(chapter.title)}`); button.append(node("span","mono",`${String(index+1).padStart(2,"0")} / ${time(chapter.start)}`),node("strong","",chapter.title)); button.addEventListener("click",()=>seekTo(chapter.start)); $("chapter-timeline").append(button);
      const detail=node("article","chapter-detail"); const label=node("div","detail-label"); const title=node("button","",chapter.title); title.type="button"; title.addEventListener("click",()=>seekTo(chapter.start)); label.append(title,node("span","detail-time",time(chapter.start))); const copy=node("div"); copy.append(node("p","",chapter.caption)); const kind=node("span","eyebrow",KINDS[chapter.kind]||KINDS.observation); kind.style.cssText="display:block;font-size:10px;color:var(--muted);margin-top:8px"; copy.append(kind); detail.append(label,copy); $("chapter-details").append(detail);
    });
  }
  function updateTimeline() {
    if (!state.story) return;
    const current=video.currentTime||0; const duration=Number.isFinite(video.duration)?video.duration:Number(state.story.durationSeconds)||0;
    $("playback-clock").textContent=`${time(current)} / ${time(duration)}`;
    const active=state.story.chapters.find((chapter)=>current>=Number(chapter.start)&&current<Number(chapter.end));
    document.querySelectorAll(".timeline-chapter").forEach((button)=>{const chapter=state.story.chapters.find((c)=>c.id===button.dataset.chapter);const isActive=active?.id===chapter?.id;button.classList.toggle("active",isActive);button.setAttribute("aria-pressed",String(isActive)); if(chapter)button.style.setProperty("--progress",`${Math.max(0,Math.min(100,(current-Number(chapter.start))/(Number(chapter.end)-Number(chapter.start))*100))}%`);});
    const show=Boolean(active&&state.phase==="reveal"&&state.version==="source"); $("chapter-caption").hidden=!show;
    if(show){$("caption-kind").textContent=`${KINDS[active.kind]||KINDS.observation} / ${time(active.start)}`;$("caption-text").textContent=text(active.caption);}
  }
  function setPanel(name, focus=false) {
    state.panel=name;
    ["story","official","evidence"].forEach((panel)=>{const active=panel===name;const tab=$(`tab-${panel}`);tab.setAttribute("aria-selected",String(active));tab.tabIndex=active?0:-1;$(`detail-${panel}`).hidden=!active;if(active&&focus)tab.focus();});
  }
  function renderOfficial() {
    const panel=$("detail-official");panel.replaceChildren(); const event=state.story.officialEvent;const verified=event.verified===true;
    panel.append(node("div",`official-status${verified?" verified":""}`,verified?"已核对比赛事件":"事件对应仍待核对"));
    const probability=number(event.expectedFg);
    if(verified&&probability!==null&&probability>=0&&probability<=1){const value=node("div","official-number");value.append(node("strong","",(probability*100).toFixed(1)),node("span","","%"));panel.append(value,node("p","official-label","这次出手的预期命中率 · xFG"),node("p","official-description","官方对这次出手情境的评估，不是球员个人的投篮命中率。"));}
    if(verified&&probability!==null&&probability>=0&&probability<=1){const scale=node("div","probability-scale");const track=node("div","probability-track");const marker=node("span");marker.style.width=`${probability*100}%`;track.append(marker);scale.append(track);const labels=node("div","probability-labels");labels.append(node("span","","0%"),node("span","","预期命中率"),node("span","","100%"));scale.append(labels);panel.append(scale);}
    if(verified&&typeof event.made==="boolean")panel.append(node("p","official-label",`本次实际结果：${event.made?"命中":"未中"}`));
    if(verified)renderShotLocation(panel,event.shotLocation);
    if(event.description)panel.append(node("p","official-description",event.description));
    if(!verified)panel.append(node("p","empty-detail","只有与画面中的具体事件完成对应，官方数值才会在这里呈现。"));
    const meta=node("dl","official-meta");[["比赛",event.gameId],["事件",event.eventId],["球员",event.playerId]].forEach(([key,value])=>{if(value!==undefined&&value!==null){meta.append(node("dt","",key),node("dd","",value));}});if(meta.childNodes.length)panel.append(meta);
    if(event.method)panel.append(node("p","official-method",`核对方式：${text(event.method)}`));const links=node("div","source-links");array(event.evidenceUrls).forEach((href,index)=>{const item=link(`依据 ${index+1} ↗`,typeof href==="object"?href.url:href);if(item)links.append(item);});if(links.childNodes.length)panel.append(links);
  }
  function renderShotLocation(panel,location){
    // Full-court reference coordinates from the NBA site's 94 × 50 display convention.
    // Unlike its half-court view, a full court does not mirror the left/right shot side.
    const x=number(location?.locX),y=number(location?.locY);if(x===null||y===null||x<0||x>100||y<0||y>100)return;
    const figure=node("figure","shot-location");const svg=document.createElementNS("http://www.w3.org/2000/svg","svg");svg.setAttribute("viewBox","-2 -2 98 54");svg.setAttribute("role","img");svg.setAttribute("aria-label",`官方记录的本次出手点位，${location.side==="left"?"左":location.side==="right"?"右":""}半场。不是视频像素坐标或运动轨迹。`);
    const shape=(tag,attributes)=>{const el=document.createElementNS("http://www.w3.org/2000/svg",tag);Object.entries(attributes).forEach(([key,value])=>el.setAttribute(key,String(value)));svg.append(el);return el;};
    const line={fill:"none",stroke:"currentColor","stroke-width":.5};shape("rect",{x:0,y:0,width:94,height:50,...line});shape("path",{d:"M47 0V50 M0 17H19V33H0 M94 17H75V33H94 M4 22V28 M90 22V28",...line});shape("circle",{cx:47,cy:25,r:6,...line});shape("circle",{cx:19,cy:25,r:6,...line});shape("circle",{cx:75,cy:25,r:6,...line});shape("circle",{cx:5.25,cy:25,r:.75,...line});shape("circle",{cx:88.75,cy:25,r:.75,...line});shape("path",{d:"M0 3H14 A23.75 23.75 0 0 1 14 47H0 M94 3H80 A23.75 23.75 0 0 0 80 47H94",...line});shape("circle",{cx:x/100*94,cy:y/100*50,r:2.5,fill:"var(--accent, #cefa58)",stroke:"var(--ink)","stroke-width":.6});shape("circle",{cx:x/100*94,cy:y/100*50,r:.65,fill:"var(--ink)"});
    figure.append(svg,node("figcaption","","官方出手点位 · 非运动轨迹"),node("p","shot-location-note","按官网坐标比例示意，仅标示本次出手。"));panel.append(figure);
  }
  function renderEvidence() {
    const panel=$("detail-evidence");panel.replaceChildren();
    if(!state.story.evidence.length){panel.append(node("p","empty-detail","这个案例尚未提供可展开的来源资料。"));return;}
    const choice=array(state.story.hook.choices).find((item)=>item.id===state.choice);const selectedEvidence=new Set(state.phase==="reveal"?array(choice?.evidenceIds):[]);
    state.story.evidence.forEach((evidence)=>{const focused=selectedEvidence.has(evidence.id);const item=node("article",`evidence-item${focused?" perspective-evidence":""}`);item.id=`evidence-${text(evidence.id)}`;item.append(node("p","eyebrow",`${KINDS[evidence.kind]||"来源资料"}${focused?" / 当前关注点":""}`),node("h4","",evidence.title),node("p","",evidence.body));const actions=node("div","evidence-actions");const seconds=number(evidence.videoTime);if(seconds!==null){const button=node("button","",`↺ ${time(seconds)} 回到画面`);button.type="button";button.addEventListener("click",()=>{seekTo(seconds,false);video.focus();});actions.append(button);}const source=link(`${text(evidence.sourceLabel,"原始来源")} ↗`,evidence.sourceUrl);if(source)actions.append(source);item.append(actions);panel.append(item);});
  }
  async function loadStories() {
    try{const response=await fetch("/product/data/stories.json",{cache:"no-store"});if(!response.ok)throw new Error(`资料请求返回 ${response.status}`);const data=await response.json();configurePreview(data.preview);state.stories=array(data.stories).filter((s)=>s&&KNOWN.has(s.id)).map(normalise);if(!state.stories.length)throw new Error("案例资料暂未提供");renderSelectors();const selected=new URL(location.href).searchParams.get("story");selectStory(state.stories.find((s)=>s.id===selected)?.id||state.stories[0].id);}
    catch(error){$("data-notice").hidden=false;$("data-notice").textContent=`影片资料暂时未能加载。${error.message}，请稍后刷新页面。`;$("case-count").textContent="资料暂不可用";$("video-empty").querySelector("p").textContent="等待案例资料";$("watch-original").disabled=true;$("enter-choice").disabled=true;}
  }
  async function api(path,options={}) {
    const controller=new AbortController();const timer=setTimeout(()=>controller.abort(),options.method==="POST"?30000:20000);
    try{const headers={Accept:"application/json",...(options.body?{"Content-Type":"application/json"}:{}),...options.headers};
      if(options.method==="POST"&&typeof options.body==="string"){const digest=await crypto.subtle.digest("SHA-256",new TextEncoder().encode(options.body));headers["x-amz-content-sha256"]=Array.from(new Uint8Array(digest),(byte)=>byte.toString(16).padStart(2,"0")).join("");}
      const response=await fetch(path,{...options,headers,cache:"no-store",credentials:"same-origin",signal:controller.signal});const raw=await response.text();let data;try{data=JSON.parse(raw);}catch{const error=new Error(`服务响应暂时无法读取（${response.status}）`);error.status=response.status;throw error;}if(!response.ok){const error=new Error(text(data.message,text(data.error?.message,text(data.error,`服务返回 ${response.status}`))));error.status=response.status;throw error;}if(!data||typeof data!=="object"||Array.isArray(data))throw new Error("服务没有返回有效任务信息");return data;
    }catch(error){if(error.name==="AbortError")throw new Error("请求等待超时，后台可能仍在处理。");throw error;}finally{clearTimeout(timer);}
  }
  function syncCreate() {
    const chosen=$("create-form").querySelector('input[name="sample"]:checked');const permitted=chosen&&(!state.sampleListKnown||state.available.has(chosen.value));$("generate-button").disabled=state.offline||!state.serviceReady||state.busy||state.submitting||!permitted;$("generate-label").textContent=state.offline?"本地回看 · 暂不生成":state.submitting?"正在提交…":state.busy?"本次任务处理中…":"生成新的增强成片";
    $("create-form").querySelectorAll('input[name="sample"]').forEach((input)=>{input.disabled=state.busy||state.submitting||(state.sampleListKnown&&!state.available.has(input.value));});$("refresh-job").disabled=state.polling||!state.jobId;
    $("local-history-actions").querySelectorAll("button").forEach((button)=>{button.disabled=state.polling;});
  }
  function configurePreview(preview) {
    if(preview?.mode!=="offline")return;
    state.offline=true;state.serviceReady=false;
    $("local-preview-notice").hidden=false;$("local-preview-notice").textContent="本地开发预览 · 原片、增强成片和证据均从本机读取。Agent 记录来自 10 月 7 日真实运行，当前不发起新推理。";
    $("creation-note").textContent="本地模式可回看已保存的创作结果。新的 Agent 推理须在赛事服务恢复后验证。";
    $("studio-description").textContent="回看两份真实 Agent 生成的作品，以及图像读取、官方数据与章节校验记录。这里展示的是已保存结果。";
    if(!state.jobId){$("job-badge").textContent="历史回看";$("job-message").textContent="选择左侧历史记录，查看已验收的成片和依据。";}
    if(Array.isArray(preview.jobs)){
      const jobs=preview.jobs.filter((job)=>KNOWN.has(job.sample)&&/^[a-f0-9]{32}$/.test(job.jobId));
      $("local-history").hidden=!jobs.length;$("local-history-actions").replaceChildren();
      jobs.forEach((job)=>{const button=node("button","",`${job.sample==="flagg"?"弗拉格":"阿门"} · 历史成片与处理记录 ↗`);button.type="button";button.addEventListener("click",()=>openHistory(job));$("local-history-actions").append(button);});
    }
    if(array(preview.issues).length){$("data-notice").hidden=false;$("data-notice").textContent=array(preview.issues).map((item)=>text(item)).join(" ");}
    syncCreate();
  }
  function openHistory(job){if(state.polling)return;stopPoll();resetGeneration();state.jobId=job.jobId;state.jobSample=job.sample;state.busy=true;state.pollStart=Date.now();state.pollErrors=0;rememberJob();$("job-message").textContent="正在读取本地历史结果，没有启动新创作。";pollJob();}
  async function checkService() {
    $("check-service").disabled=true;$("service-status").textContent="检查创作服务…";
    try{const data=await api("/api/status");configurePreview(data.preview);const supportsStory=array(data.modes).includes("story");state.serviceReady=!state.offline&&supportsStory&&data.ready!==false&&!["failed","offline","unavailable","error"].includes(String(data.status).toLowerCase());state.sampleListKnown=Array.isArray(data.samples);state.available=new Set(array(data.samples).filter((s)=>typeof s==="string"||(s&&s.available!==false&&s.enabled!==false)).map((s)=>typeof s==="string"?s:s.id||s.sample||s.key));$("service-status").textContent=state.offline?"本地历史回看 · 新生成暂不可用":state.serviceReady?"故事创作服务已就绪":!supportsStory?"故事创作服务尚未开放，暂不能生成":"创作服务暂未就绪";}
    catch(error){state.serviceReady=false;$("service-status").textContent=`服务暂不可达：${error.message}`;}
    finally{$("service-dot").className=`service-dot ${state.serviceReady?"ready":"unavailable"}`;$("check-service").disabled=false;syncCreate();}
  }
  function jobError(message){$("job-error").hidden=!message;$("job-error").textContent=message||"";}
  function rememberJob(){try{sessionStorage.setItem(STORE,JSON.stringify({jobId:state.jobId,sample:state.jobSample}));const address=new URL(location.href);address.searchParams.set("job",state.jobId);history.replaceState(null,"",address);}catch{}}
  function forgetJob(){try{sessionStorage.removeItem(STORE);const address=new URL(location.href);address.searchParams.delete("job");history.replaceState(null,"",address);}catch{}}
  function resetGeneration(){state.resultUrl=null;$("generated-video").pause();$("generated-video").removeAttribute("src");$("generated-video").load();$("generated-video").hidden=true;$("generation-placeholder").hidden=false;$("generation-actions").hidden=true;$("actual-analysis").hidden=true;$("technical-details").hidden=true;$("actual-summary").textContent="";$("actual-observations").replaceChildren();jobError("");}
  function stopPoll(){clearTimeout(state.timer);state.timer=null;}
  function schedulePoll(delay=3000){stopPoll();if(Date.now()-state.pollStart>20*60*1000){$("job-message").textContent="自动查询已暂停。任务可能仍在继续，可重新查询同一编号。";return;}state.timer=setTimeout(pollJob,delay);}
  async function submitJob(event){event.preventDefault();if($("generate-button").disabled)return;const sample=$("create-form").querySelector('input[name="sample"]:checked')?.value;if(!KNOWN.has(sample))return;stopPoll();resetGeneration();state.busy=true;state.submitting=true;state.jobId=null;state.jobSample=sample;forgetJob();$("job-reference").hidden=true;$("job-badge").textContent="正在提交";$("job-badge").className="job-badge running";$("job-message").textContent="正在向服务提交这次创作请求…";syncCreate();
    try{const data=await api("/api/jobs",{method:"POST",body:JSON.stringify({sample,mode:"story"})});if(typeof data.jobId!=="string"||!data.jobId)throw new Error("服务未返回任务编号，提交结果尚未确认。");state.jobId=data.jobId;rememberJob();renderJob(data);state.pollStart=Date.now();state.pollErrors=0;pollJob();}
    catch(error){state.busy=false;$("job-badge").textContent="提交未确认";$("job-badge").className="job-badge failed";$("job-message").textContent="没有获得可查询的任务编号。";jobError(`${error.message} 页面没有自动重提；如果请求已被服务接收，后台可能仍在执行，请核对后再重新启动。`);}
    finally{state.submitting=false;syncCreate();}}
  async function pollJob(){if(!state.jobId||state.polling)return;const id=state.jobId;state.polling=true;syncCreate();try{const data=await api(`/api/jobs/${encodeURIComponent(id)}`);if(id!==state.jobId)return;state.pollErrors=0;jobError("");renderJob(data);if(!["completed","failed","cancelled","canceled","error"].includes(String(data.status).toLowerCase()))schedulePoll();else stopPoll();}
    catch(error){if(id!==state.jobId)return;state.pollErrors+=1;if([400,404].includes(error.status)){state.busy=false;stopPoll();forgetJob();$("job-badge").textContent="任务不可用";$("job-badge").className="job-badge failed";$("job-message").textContent="任务可能已经过期，或编号不正确。";jobError(error.message);}else{jobError(`${error.message} 这不代表任务失败，页面只重试读取状态，不会再次提交。`);if(state.pollErrors<=3)schedulePoll(3000*2**state.pollErrors);else{$("job-message").textContent="状态查询已暂停；恢复连接后可以重新查询。";stopPoll();}}}
    finally{state.polling=false;syncCreate();}}
  function renderJob(data){
    // A restoring/in-flight task owns its sample selection only until it settles.
    if(state.busy&&KNOWN.has(data.sample)){
      state.jobSample=data.sample;
      $("create-form").querySelectorAll('input[name="sample"]').forEach((input)=>{input.checked=input.value===data.sample;});
    }
    const status=String(data.status||"unknown").toLowerCase();
    const returnedCompleted=status==="completed";
    const productResult=data.mode==="story"&&data.analysis?.protocol_version==="product-story-v1";
    const incompatible=returnedCompleted&&!productResult;
    const completed=returnedCompleted&&productResult;
    const failed=incompatible||["failed","error","canceled","cancelled"].includes(status);
    state.busy=!completed&&!failed;$("job-reference").hidden=false;$("job-id").textContent=state.jobId;
    $("job-badge").className=`job-badge ${completed?"completed":failed?"failed":"running"}`;
    $("job-badge").textContent=completed?"成片就绪":incompatible?"任务版本不匹配":failed?"处理未完成":status==="queued"?"等待处理":"正在处理";
    $("job-message").textContent=incompatible?"服务返回了其他类型的结果，尚未获得本次故事成片。":text(({queued:"任务已排队，正在准备本次创作。",loading_inputs:"正在读取比赛视频和对应资料。",analyzing:"正在观察比赛画面，组织有依据的解读。",rendering:"正在把解读与官方数据烧录到完整视频。",publishing:"成片已生成，正在发布可播放文件。",completed:"本次视频已生成。播放成片，查看这一次的解读。",failed:"本次创作未完成，请查看下面的原因。"})[typeof data.stage==="string"?data.stage:""],completed?"本次视频已生成。播放成片，查看这一次的解读。":failed?"服务报告本次处理未能完成。":"正在执行画面分析与完整视频烧录，状态来自真实任务。");
    if(completed&&data.preview?.historical===true){$("job-badge").textContent="历史成片";$("job-message").textContent=text(data.preview.notice,"历史结果，仅供本地回看，没有发起新推理。");}
    $("actual-analysis-label").textContent=data.preview?.historical===true?"ARCHIVED RUN / 历史解读":"THIS RUN / 本次解读";
    $("generated-video").setAttribute("aria-label",data.preview?.historical===true?"历史生成的完整增强成片":"本次生成的完整增强成片");
    const idx=completed?2:status==="queued"?0:1;document.querySelectorAll("[data-stage]").forEach((el,index)=>{el.classList.toggle("active",index===idx&&!failed);el.classList.toggle("done",index<idx&&!failed);});
    $("technical-details").hidden=false;$("actual-json").textContent=JSON.stringify(data,null,2);renderRunFacts(data);
    if(incompatible){state.resultUrl=null;$("generated-video").pause();$("generated-video").removeAttribute("src");$("generated-video").hidden=true;$("generation-actions").hidden=true;$("actual-analysis").hidden=true;$("generation-placeholder").hidden=false;jobError("该结果不是 story / product-story-v1 任务，不能作为本产品成片。服务升级完成后，请重新检查服务并启动新任务。");forgetJob();syncCreate();return;}
    if(failed)jobError(text(data.error?.message,text(data.error,"请查看处理记录，修复原因后重新启动。")));
    if(productResult)renderActualAnalysis(data.analysis,data);
    if(completed){const media=url(data.videoUrl);if(media){if(state.resultUrl!==media){state.resultUrl=media;$("generated-video").src=media;$("generated-video").load();}$("generated-video").hidden=false;$("generation-placeholder").hidden=true;$("generation-actions").hidden=false;$("generated-download").href=media;const analysisUrl=url(data.analysisUrl);$("generated-analysis-link").hidden=!analysisUrl;if(analysisUrl)$("generated-analysis-link").href=analysisUrl;}else jobError("任务已完成，但服务没有返回有效成片地址。请重新查询或查看处理记录。");}syncCreate();
  }
  function renderActualAnalysis(analysis,job){$("actual-analysis").hidden=false;$("actual-observations").replaceChildren();$("actual-summary").textContent=typeof analysis==="string"?analysis:text(analysis.plan?.summary,text(analysis.summary,text(analysis.description,"本次分析已返回，详见处理记录。")));const observations=array(analysis.plan?.chapters).length?analysis.plan.chapters:array(analysis.observations);
    observations.forEach((item)=>{const section=node("div","actual-observation");section.append(node("p","",typeof item==="string"?item:text(item.caption,text(item.text,text(item.observation)))));const seconds=number(item.start)??number(item.timeSeconds);if(seconds!==null&&(job.preservesSourceTimeline===true||analysis.preservesSourceTimeline===true)){const button=node("button","text-link",`回看 ${time(seconds)} ↗`);button.type="button";button.addEventListener("click",()=>{const media=$("generated-video");if(media.readyState>0){media.currentTime=Math.min(seconds,Math.max(0,media.duration-.01));media.focus();}});section.append(button);}$("actual-observations").append(section);});}
  function renderRunFacts(job){
    const analysis=job.analysis&&typeof job.analysis==="object"?job.analysis:{};const facts=$("run-facts");facts.replaceChildren();
    const citedIds=new Set(array(analysis.plan?.chapters).flatMap((chapter)=>array(chapter.evidenceIds)));
    const entries=[["调用模型",analysis.model_id||analysis.modelId||job.modelId],["端到端处理耗时",number(analysis.elapsedSeconds)!==null?`${Number(analysis.elapsedSeconds).toFixed(1)} 秒`:number(job.elapsedSeconds)!==null?`${Number(job.elapsedSeconds).toFixed(1)} 秒`:null],["故事引用",analysis.plan?`${citedIds.size} 条独立依据`:Array.isArray(analysis.evidence)?`${analysis.evidence.length} 条来源资料`:null]];
    entries.forEach(([label,value])=>{if(value===null||value===undefined)return;const row=node("div");row.append(node("span","",label),node("strong","",value));facts.append(row);});
    const list=$("run-trace");list.replaceChildren();const trace=Array.isArray(analysis.trace)?analysis.trace:array(analysis.trace?.steps);
    const toolNames={inspect_frames:"读取真实比赛画面",read_official_event:"核对官方事件与数据",validate_story:"校验故事计划"};
    const statuses={succeeded:"已完成",completed:"已完成",running:"处理中",rejected:"需要修订",failed:"未完成"};
    trace.forEach((step,index)=>{const item=node("li");const title=typeof step==="string"?step:toolNames[step.tool]||text(step.label,text(step.name,text(step.tool,`步骤 ${index+1}`)));item.append(node("strong","",title));
      if(step&&typeof step==="object"){const notes=[];const result=step.result||{};if(step.status)notes.push(statuses[step.status]||text(step.status));if(step.tool==="inspect_frames"&&Array.isArray(result.frames))notes.push(`实际读取 ${result.frames.length} 帧`);if(step.tool==="read_official_event"){if(result.officialEvent?.eventId!==undefined)notes.push(`事件 ${result.officialEvent.eventId}`);if(Array.isArray(result.evidence))notes.push(`${result.evidence.length} 条来源依据`);}if(step.tool==="validate_story"&&result.passed===true)notes.push("结构与来源检查通过");if(result.error)notes.push(text(result.error));const description=text(step.summary,text(step.message,text(step.description)));if(description)notes.push(description);if(notes.length)item.append(node("p","",notes.join(" · ")));const elapsed=number(step.durationMs)??number(step.elapsedMs);if(elapsed!==null)item.append(node("span","mono",`${elapsed.toLocaleString()} ms${number(step.round)!==null?` / ROUND ${step.round}`:""}`));}list.append(item);
    });list.hidden=!trace.length;
    const validation=analysis.validation||job.validation;const validationLabel=$("run-validation");
    if(validation&&typeof validation==="object"){const names={known_evidence_ids:"依据编号可回溯",cited_frames_actually_inspected:"本轮输入帧已读取，另含预先整理的画面依据",source_time_bounds:"时码位于原片内",nonoverlapping_chapters:"章节无重叠",no_model_authored_numbers:"无模型自造数值",official_metrics_copied_verbatim:"官方数值原样引用"};const checks=array(validation.checks).map((check)=>names[check]||text(check));validationLabel.textContent=`${validation.passed===true?"结构与来源校验通过":validation.passed===false?"结构与来源校验未通过":"服务返回校验记录"}${checks.length?`：${checks.join("、")}`:""}。这些检查不等于独立的篮球事实认证。`;}else validationLabel.textContent=typeof validation==="string"?validation:"服务尚未返回结构与来源校验记录。";
  }
  function restoreJob(){let stored;try{stored=JSON.parse(sessionStorage.getItem(STORE)||"null");}catch{}const id=new URL(location.href).searchParams.get("job")||stored?.jobId;if(typeof id!=="string"||!/^[a-zA-Z0-9_-]{1,128}$/.test(id))return;state.jobId=id;state.jobSample=stored?.sample;state.busy=true;state.pollStart=Date.now();setView("create");$("job-message").textContent="正在恢复上次任务，只查询状态，不会重新生成。";pollJob();}
  function theater(force){const active=typeof force==="boolean"?force:!state.theater;state.theater=active;document.body.classList.toggle("is-theater",active);$("theater-toggle").setAttribute("aria-pressed",String(active));$("theater-toggle").setAttribute("title",active?"退出剧场模式（Esc）":"切换剧场模式（T）");document.querySelectorAll(".masthead,.site-footer,#watch-view > :not(#film-room),#create-view").forEach((el)=>{el.inert=active;});if(active){$("film-room").setAttribute("role","dialog");$("film-room").setAttribute("aria-modal","true");$("theater-toggle").focus();}else{$("film-room").removeAttribute("role");$("film-room").removeAttribute("aria-modal");$("theater-toggle").focus();}}

  document.querySelectorAll("[data-view]").forEach((button)=>button.addEventListener("click",()=>setView(button.dataset.view,true)));
  document.querySelectorAll("[data-panel]").forEach((button)=>{button.addEventListener("click",()=>setPanel(button.dataset.panel));button.addEventListener("keydown",(event)=>{const names=["story","official","evidence"];let index=names.indexOf(button.dataset.panel);if(event.key==="ArrowRight")index=(index+1)%names.length;else if(event.key==="ArrowLeft")index=(index+names.length-1)%names.length;else if(event.key==="Home")index=0;else if(event.key==="End")index=names.length-1;else return;event.preventDefault();setPanel(names[index],true);});});
  $("watch-original").addEventListener("click",()=>{if(state.version!=="source")setMedia("source",0,true);else{seekTo(0,false);playVideo();}$("watch-original").querySelector("span").textContent="重新观看原片";});
  $("enter-choice").addEventListener("click",()=>{state.phase="choose";renderPhase();});
  $("reveal-play").addEventListener("click",reveal);$("change-perspective").addEventListener("click",()=>{state.phase="choose";renderPhase();});$("replay-key").addEventListener("click",()=>{video.playbackRate=.5;$("slow-motion").setAttribute("aria-pressed","true");seekTo(Math.max(0,keyTime()-.4));announce("从关键时刻前 0.4 秒开始半速回放，可点击慢放按钮恢复正常速度。");});
  $("source-mode").addEventListener("click",()=>{if(state.version!=="source")setMedia("source");});$("enhanced-mode").addEventListener("click",()=>{if(state.version!=="enhanced")setMedia("enhanced");});
  $("slow-motion").addEventListener("click",()=>{video.playbackRate=video.playbackRate===.5?1:.5;$("slow-motion").setAttribute("aria-pressed",String(video.playbackRate===.5));announce(video.playbackRate===.5?"已切换至半速播放":"已恢复正常速度");});$("theater-toggle").addEventListener("click",()=>theater());
  video.addEventListener("timeupdate",updateTimeline);video.addEventListener("ended",()=>{if(state.phase==="watch"){state.phase="choose";renderPhase();announce(`${state.version==="enhanced"?"增强成片":"原片"}播放结束。现在选择你的关注点。`);}});video.addEventListener("error",()=>{if(!video.getAttribute("src"))return;$("video-empty").hidden=true;$("video-alert").hidden=false;$("video-alert").textContent="画面暂时无法加载。请检查网络，或使用下方的原片链接。";});
  $("court-lab-link").addEventListener("click",()=>video.pause());
  $("create-form").addEventListener("submit",submitJob);$("check-service").addEventListener("click",checkService);$("refresh-job").addEventListener("click",()=>{state.pollErrors=0;state.pollStart=Date.now();stopPoll();pollJob();});$("generated-video").addEventListener("error",()=>{if(state.resultUrl)jobError("成片暂时无法播放，任务结果仍已保存。可打开完整 MP4 检查，或重新查询。 ");});
  document.addEventListener("keydown",(event)=>{if(event.key==="Escape"&&state.theater){theater(false);return;}if(event.ctrlKey||event.metaKey||event.altKey||event.target.closest("input,textarea,select,button,a,summary,[contenteditable]"))return;if(state.view!=="watch")return;if(event.key.toLowerCase()==="t"){event.preventDefault();theater();}else if(event.key===" "&&event.target!==video){event.preventDefault();video.paused?playVideo():video.pause();}else if(event.key==="ArrowRight"&&event.target!==video){event.preventDefault();seekTo((video.currentTime||0)+5,!video.paused);}else if(event.key==="ArrowLeft"&&event.target!==video){event.preventDefault();seekTo(Math.max(0,(video.currentTime||0)-5),!video.paused);}});
  window.addEventListener("online",()=>{if(state.jobId&&state.busy&&!state.polling){state.pollStart=Date.now();pollJob();}});window.addEventListener("pagehide",stopPoll);
  loadStories().then(()=>{restoreJob();});
})();
