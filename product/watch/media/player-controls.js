const ICONS = {
  play: '<path d="m9 5 11 7-11 7Z"/>', pause: '<path d="M8 5v14M16 5v14"/>',
  volume: '<path d="m11 5-6 4H2v6h3l6 4Z"/><path d="M15 8a6 6 0 0 1 0 8m3-11a10 10 0 0 1 0 14"/>',
  mute: '<path d="m11 5-6 4H2v6h3l6 4Z"/><path d="m16 9 6 6m0-6-6 6"/>',
  fullscreen: '<path d="M8 3H3v5m13-5h5v5M3 16v5h5m13-5v5h-5"/>',
  settings: '<circle cx="12" cy="12" r="3"/><path d="m9 3-1 3-3 1-2 3 2 2-1 3 2 3 3-1 3 3 3-2 3 1 2-3-1-3 2-3-3-2-1-3-3 1Z"/>',
};
const svg = name => `<svg viewBox="0 0 24 24" aria-hidden="true" fill="none" stroke="currentColor" stroke-width="1.65" stroke-linecap="round" stroke-linejoin="round">${ICONS[name]}</svg>`;
const time = seconds => {
  if (!Number.isFinite(seconds) || seconds < 0) return '--:--';
  const s = Math.floor(seconds), h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60);
  return `${h ? h + ':' : ''}${String(m).padStart(h ? 2 : 1, '0')}:${String(s % 60).padStart(2, '0')}`;
};

export function createPlayerControls({ video, stage, onSettings, onError = () => {}, onMenuChange = () => {} }) {
  if (!video || !stage) throw new TypeError('PlayerControls 需要同一 video 与 stage。');
  const element = document.createElement('div');
  element.className = 'player-controls';
  element.dataset.component = 'controls';
  element.setAttribute('role', 'group'); element.setAttribute('aria-label', '播放控制');
  element.innerHTML = `<div class="glass-target player-controls-glass" data-glass="controlBar"></div>
    <div class="glass-content player-controls-content">
      <button class="control-button play-toggle" type="button" aria-label="播放">${svg('play')}</button>
      <span class="media-time" aria-live="off"><span class="current-time">0:00</span><span class="time-divider"> / </span><span class="duration-time">--:--</span></span>
      <label class="seek-control"><span class="sr-only">播放进度</span><input class="seek-slider" type="range" min="0" max="0" step="0.01" value="0" aria-label="播放进度" disabled></label>
      <span class="media-resolution" title="源视频实际分辨率">载入中</span>
      <div class="rate-control"><button class="control-button rate-toggle" type="button" aria-haspopup="menu" aria-expanded="false" aria-label="播放速度">1×</button><div class="rate-menu" data-component="menus" role="menu" aria-label="播放速度" hidden><div class="glass-target"></div><div class="glass-content">${[.5, .75, 1, 1.25, 1.5, 2].map(rate => `<button type="button" role="menuitemradio" data-rate="${rate}" aria-checked="${rate === 1}">${rate}×</button>`).join('')}</div></div></div>
      <div class="volume-control"><button class="control-button mute-toggle" type="button" aria-label="静音">${svg('volume')}</button><label class="volume-slider-label"><span class="sr-only">音量</span><input class="volume-slider" type="range" min="0" max="1" step="0.01" value="1" aria-label="音量"></label></div>
      ${onSettings ? `<button class="control-button settings-toggle" type="button" aria-label="显示设置">${svg('settings')}</button>` : ''}
      <button class="control-button fullscreen-toggle" type="button" aria-label="进入全屏">${svg('fullscreen')}</button>
    </div>`;
  const $ = selector => element.querySelector(selector);
  const play = $('.play-toggle'), seek = $('.seek-slider'), volume = $('.volume-slider'), mute = $('.mute-toggle'), rate = $('.rate-toggle'), menu = $('.rate-menu'), fullscreen = $('.fullscreen-toggle');
  const listeners = [];
  let dragging = false, dragPointer = null, activeMenu = false, previousPlaying = false, destroyed = false;
  const listen = (target, event, handler, options) => { target.addEventListener(event, handler, options); listeners.push(() => target.removeEventListener(event, handler, options)); };
  const report = error => onError(error instanceof Error ? error.message : String(error));
  function emitInteraction() {
    const detail = { menu: activeMenu, dragging };
    element.dispatchEvent(new CustomEvent('controls-interaction', { bubbles: true, detail }));
    onMenuChange(activeMenu || dragging ? 'player-controls' : null);
  }
  function setMenu(open) { activeMenu = open; menu.hidden = !open; rate.setAttribute('aria-expanded', String(open)); emitInteraction(); }
  function paintRange(input) { const min = +input.min || 0, max = +input.max || 1; input.style.setProperty('--range-progress', `${Math.max(0, Math.min(100, (+input.value - min) / (max - min || 1) * 100))}%`); }
  function refresh() {
    if (destroyed) return;
    const paused = video.paused || video.ended;
    play.innerHTML = svg(paused ? 'play' : 'pause'); play.setAttribute('aria-label', paused ? '播放' : '暂停'); play.dataset.paused = String(paused);
    const duration = Number.isFinite(video.duration) && video.duration > 0 ? video.duration : 0;
    seek.disabled = !duration; seek.max = String(duration);
    if (!dragging) seek.value = String(video.currentTime || 0);
    $('.current-time').textContent = time(dragging ? +seek.value : video.currentTime || 0);
    $('.duration-time').textContent = duration ? time(duration) : '--:--';
    seek.setAttribute('aria-valuetext', `${time(+seek.value)}，总时长 ${time(duration)}`); paintRange(seek);
    const isMuted = video.muted || video.volume === 0;
    mute.innerHTML = svg(isMuted ? 'mute' : 'volume'); mute.setAttribute('aria-label', isMuted ? '取消静音' : '静音'); mute.setAttribute('aria-pressed', String(isMuted));
    volume.value = String(video.muted ? 0 : video.volume); paintRange(volume);
    rate.textContent = `${video.playbackRate}×`;
    menu.querySelectorAll('[data-rate]').forEach(button => button.setAttribute('aria-checked', String(+button.dataset.rate === video.playbackRate)));
    const resolution = $('.media-resolution'); resolution.textContent = video.videoHeight ? `${video.videoHeight}P` : '载入中';
    resolution.title = video.videoWidth ? `源视频 ${video.videoWidth} × ${video.videoHeight}，无转码画质选项` : '等待真实媒体元信息';
    fullscreen.setAttribute('aria-label', document.fullscreenElement ? '退出全屏' : '进入全屏');
  }
  async function togglePlay() { try { if (video.paused || video.ended) await video.play(); else video.pause(); } catch (error) { report(error); } refresh(); }
  function seekToInput() { if (Number.isFinite(video.duration)) { try { video.currentTime = Math.max(0, Math.min(video.duration, +seek.value)); } catch (error) { report(error); } } }
  function finishDrag() {
    if (!dragging) return;
    seekToInput(); dragging = false;
    if (dragPointer !== null && seek.hasPointerCapture?.(dragPointer)) seek.releasePointerCapture(dragPointer);
    dragPointer = null; emitInteraction();
    if (previousPlaying) video.play().catch(report);
    previousPlaying = false; refresh();
  }
  listen(play, 'click', togglePlay);
  listen(seek, 'pointerdown', event => { if (seek.disabled) return; dragging = true; dragPointer = event.pointerId; previousPlaying = !video.paused; video.pause(); seek.setPointerCapture?.(event.pointerId); emitInteraction(); });
  listen(seek, 'input', () => { seekToInput(); $('.current-time').textContent = time(+seek.value); paintRange(seek); seek.setAttribute('aria-valuetext', `${time(+seek.value)}，总时长 ${time(video.duration)}`); });
  listen(seek, 'pointerup', finishDrag); listen(seek, 'pointercancel', finishDrag); listen(seek, 'lostpointercapture', finishDrag);
  listen(seek, 'change', () => { if (!dragging) seekToInput(); });
  listen(mute, 'click', () => { if (video.muted || video.volume === 0) { video.muted = false; if (video.volume === 0) video.volume = .5; } else video.muted = true; refresh(); });
  listen(volume, 'input', () => { video.volume = +volume.value; video.muted = +volume.value === 0; refresh(); });
  listen(rate, 'click', () => setMenu(!activeMenu));
  listen(menu, 'click', event => { const choice = event.target.closest('[data-rate]'); if (!choice) return; video.playbackRate = +choice.dataset.rate; setMenu(false); rate.focus(); refresh(); });
  listen(document, 'pointerdown', event => { if (activeMenu && !$('.rate-control').contains(event.target)) setMenu(false); });
  listen(element, 'keydown', event => { if (event.key === 'Escape' && activeMenu) { event.preventDefault(); event.stopPropagation(); setMenu(false); rate.focus(); } });
  listen(menu, 'keydown', event => { if (!['ArrowDown', 'ArrowUp', 'Home', 'End'].includes(event.key)) return; event.preventDefault(); const choices = [...menu.querySelectorAll('button')]; let index = choices.indexOf(document.activeElement); index = event.key === 'Home' ? 0 : event.key === 'End' ? choices.length - 1 : (index + (event.key === 'ArrowDown' ? 1 : -1) + choices.length) % choices.length; choices[index].focus(); });
  listen(fullscreen, 'click', async () => { try { if (document.fullscreenElement) await document.exitFullscreen(); else if (stage.requestFullscreen) await stage.requestFullscreen(); else throw new Error('此浏览器暂不支持舞台全屏。'); } catch (error) { report(error); } });
  if (onSettings) listen($('.settings-toggle'), 'click', onSettings);
  for (const event of ['timeupdate', 'loadedmetadata', 'durationchange', 'resize', 'play', 'pause', 'ended', 'volumechange', 'ratechange', 'seeked', 'emptied']) listen(video, event, refresh);
  listen(document, 'fullscreenchange', refresh);
  refresh();
  return { element, refresh, destroy() { destroyed = true; listeners.forEach(remove => remove()); if (dragging && dragPointer !== null && seek.hasPointerCapture?.(dragPointer)) seek.releasePointerCapture(dragPointer); onMenuChange(null); element.remove(); } };
}
