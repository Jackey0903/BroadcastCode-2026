import { safeSourceUrl, formatVideoTime, formatBeijingDate } from '../adapters/catalog.js';

const TITLES = { moments: ['关键时刻', 'MOMENTS'], data: ['这一球的数据', 'SHOT DATA'], sources: ['画面与出处', 'SOURCES'], library: ['选择比赛', 'MATCH LIBRARY'], history: ['历史成片记录', 'HISTORY'] };
const KINDS = { official: '官方记录', observation: '画面观察', video_frame: '实际输入帧' };
let nextPanelId = 0;

function node(tag, className, text) {
  const element = document.createElement(tag);
  if (className) element.className = className;
  if (text !== undefined && text !== null) element.textContent = String(text);
  return element;
}
function button(label, className, action) {
  const element = node('button', className, label);
  element.type = 'button';
  element.addEventListener('click', action);
  return element;
}
function sourceLink(label, value) {
  const href = safeSourceUrl(value);
  if (!href) return null;
  const link = node('a', 'content-link', label);
  link.href = href; link.target = '_blank'; link.rel = 'noopener noreferrer';
  return link;
}
function appendLink(parent, label, value) { const link = sourceLink(label, value); if (link) parent.append(link); }
function paragraph(text, className = 'content-copy') { return node('p', className, text); }
function section(title) {
  const element = node('section', 'content-section');
  if (title) element.append(node('h3', 'content-section-title', title));
  return element;
}
function detail(label, value) {
  const row = node('div', 'content-detail');
  row.append(node('dt', '', label), node('dd', '', value ?? '未记录'));
  return row;
}

/** A floating non-modal drawer. Opening it never changes the media clock. */
export function createContentPanel({ onSeek = () => {}, onStory = () => {}, onClose = () => {} } = {}) {
  const uid = `content-sheet-${++nextPanelId}`;
  const element = node('aside', 'content-sheet');
  element.id = uid;
  element.hidden = true;
  element.setAttribute('role', 'dialog');
  element.setAttribute('aria-modal', 'false');
  element.setAttribute('aria-labelledby', `${uid}-title`);
  element.tabIndex = -1;
  const header = node('header', 'content-sheet-header');
  const heading = node('div', 'content-sheet-heading');
  const eyebrow = node('span', 'content-eyebrow');
  const title = node('h2', 'content-sheet-title'); title.id = `${uid}-title`;
  heading.append(eyebrow, title);
  const closeButton = button('×', 'content-close', () => close());
  closeButton.setAttribute('aria-label', '关闭内容抽屉');
  header.append(heading, closeButton);
  const body = node('div', 'content-sheet-body');
  const glass = node('div', 'glass-target');
  const foreground = node('div', 'glass-content content-sheet-foreground');
  foreground.append(header, body); element.append(glass, foreground);
  let openState = false;
  let lastFocus = null;
  let activeStory = null;

  function seek(time, metadata = {}) {
    const value = Number(time);
    if (!Number.isFinite(value) || !activeStory) return;
    onSeek(Math.min(Math.max(0, value), Number(activeStory.durationSeconds) || value), { story: activeStory, ...metadata });
  }
  function evidenceDetails(evidenceIds = [], story = activeStory) {
    const sources = story?.evidence || [];
    const names = evidenceIds.map(id => sources.find(item => item.id === id)?.title).filter(Boolean);
    return names.length ? names.join(' · ') : '来源随历史记录保存';
  }
  function moments(story) {
    body.append(paragraph('回看同一回合，选择你想看的这一拍。', 'content-lead'));
    const chapterList = section();
    for (const [index, chapter] of (story.chapters || []).entries()) {
      const card = button('', 'content-moment', () => seek(chapter.start, { chapter, playbackRate: 1 }));
      card.append(node('span', 'content-moment-index', String(index + 1).padStart(2, '0')));
      const copy = node('span', 'content-moment-copy');
      copy.append(node('strong', '', chapter.title), node('span', '', chapter.caption), node('small', '', `${formatVideoTime(chapter.start)} — ${formatVideoTime(chapter.end)} · ${KINDS[chapter.kind] || '编辑章节'}`));
      card.append(copy, node('span', 'content-moment-arrow', '↗'));
      card.title = evidenceDetails(chapter.evidenceIds);
      chapterList.append(card);
    }
    body.append(chapterList);
    if (story.keyMoment) {
      const key = story.keyMoment;
      const replay = button(`慢看关键一拍 · ${formatVideoTime(key.start)}`, 'content-primary', () => seek(key.start, { playbackRate: key.playbackRate || 0.5, end: key.end, chapter: 'keyMoment' }));
      body.append(replay);
    }
    if (story.storyOptions?.length) {
      const options = section('换个关注点');
      for (const option of story.storyOptions) {
        const item = button('', 'content-focus-option', () => seek(option.focusTime, { focus: option.id }));
        item.append(node('strong', '', option.label), node('span', '', option.description));
        options.append(item);
      }
      body.append(options);
    }
    body.append(paragraph('时间码为视频时间。章节与慢看节点来自已核查的编辑素材；官方比赛时钟单独保留。', 'content-note'));
  }
  function data(story) {
    const event = story.officialEvent || {};
    const xfg = (story.evidence || []).find(item => item.unit === 'ratio' && Number.isFinite(item.value));
    const metric = section('预期投篮命中率 · xFG');
    metric.classList.add('content-metric');
    metric.append(node('div', 'content-metric-value', xfg?.display || (Number.isFinite(event.expectedFg) ? `${(event.expectedFg * 100).toFixed(1)}%` : '未提供')));
    metric.append(paragraph(xfg?.body || '这次出手机会的参考值。'));
    if (xfg) {
      metric.append(paragraph(`原始值 ${xfg.value} · 单位 ratio · 事件 ${xfg.eventId}`, 'content-note'));
      appendLink(metric, '查看 NBA 原始出手记录 ↗', xfg.sourceUrl);
      appendLink(metric, '指标定义 ↗', xfg.definitionUrl);
    }
    body.append(metric);
    const eventSection = section('官方事件');
    eventSection.append(paragraph(event.description || '当前素材没有已核对的官方事件。'));
    const details = node('dl', 'content-details');
    details.append(detail('比赛', event.gameId), detail('比赛时钟', event.period ? `第 ${event.period} 节 · ${event.clock}` : null), detail('事件编号', event.actionNumber ?? event.eventId), detail('结果', event.made === true ? `${event.shotValue || 2} 分命中` : event.made === false ? '未命中' : '未记录'));
    eventSection.append(details);
    for (const [index, url] of (event.evidenceUrls || []).entries()) appendLink(eventSection, index ? '逐次出手数据 ↗' : '逐回合记录 ↗', url);
    body.append(eventSection);
    if (xfg && Number.isFinite(xfg.videoTime)) body.append(button(`回看数据节点 · ${formatVideoTime(xfg.videoTime)}`, 'content-primary', () => seek(xfg.videoTime, { evidence: xfg })));
    body.append(paragraph('xFG 描述这次出手机会；它不是球员赛季命中率、比赛胜率或命中保证。回看节点由编辑选择，不是比赛时钟的逐帧换算。', 'content-note'));
    const court = section('战术板的数据');
    court.append(paragraph(story.sample === 'flagg' ? '弗拉格样片使用编辑站位与球权示意。D / W 是匿名编号；空心点是过去的最近位置。' : '这段阿门样片没有配套的逐帧战术示意，战术板保持空白。'));
    court.append(paragraph('示意点、移动线路和篮球位置未经人类专家核准，不是官方追踪数据。', 'content-note'));
    body.append(court);
  }
  function evidenceCard(evidence, story = activeStory) {
    const card = section();
    card.classList.add('content-evidence');
    const row = node('div', 'content-evidence-heading');
    row.append(node('span', `content-badge is-${evidence.kind || 'observation'}`, KINDS[evidence.kind] || '来源记录'), node('h3', '', evidence.title));
    card.append(row, paragraph(evidence.body || evidence.description || ''), paragraph(evidence.sourceLabel || '', 'content-note'));
    if (Number.isFinite(evidence.videoTime)) card.append(button(`回看 ${formatVideoTime(evidence.videoTime)}`, 'content-text-button', () => seek(evidence.videoTime, { evidence, story })));
    if (evidence.officialClock) card.append(paragraph(`官方时钟：第 ${evidence.period} 节 ${evidence.officialClock}`, 'content-note'));
    if (evidence.videoTimeMeaning) card.append(paragraph(evidence.videoTimeMeaning, 'content-note'));
    if (evidence.sourcePath) card.append(node('code', 'content-source-path', evidence.sourcePath));
    const isVideo = typeof evidence.sourceUrl === 'string' && evidence.sourceUrl.startsWith('/samples/');
    if (!isVideo) appendLink(card, '打开出处 ↗', evidence.sourceUrl);
    if (evidence.humanExpertReviewed === false) card.append(paragraph('画面记录由 AI 助手编辑，未经人类专家认证。', 'content-note'));
    return card;
  }
  function sources(story) {
    body.append(paragraph('每条观察与数值，都保留原有来源。', 'content-lead'));
    for (const evidence of story.evidence || []) body.append(evidenceCard(evidence, story));
    const original = section('素材来源');
    appendLink(original, '主办方公开训练视频包 ↗', story.originalSourceUrl);
    original.append(paragraph('原转播比分牌保留在画面内。', 'content-note'));
    original.append(node('code', 'content-source-path', `SHA-256 ${story.sourceVideoSha256 || '未记录'}`));
    body.append(original);
  }
  function library(story, catalog) {
    body.append(paragraph('公开训练样片', 'content-lead'));
    for (const item of catalog) {
      const card = section();
      card.classList.add('content-library-card');
      if (item.id === story.id) card.classList.add('is-selected');
      card.append(node('span', 'content-eyebrow', item.id === story.id ? '正在观看' : '本地素材'), node('h3', '', `${item.player?.team || ''} · ${item.opponent || ''}`), paragraph(item.title));
      card.append(paragraph(`${item.player?.name || ''} · ${Number(item.durationSeconds || 0).toFixed(2)} 秒 · ${item.game?.date || ''} 北京时间`, 'content-note'));
      const sourceStatus = item.media?.source?.status;
      card.append(paragraph(sourceStatus === 'missing' || sourceStatus === 'error' ? '原片未加载，请恢复本地素材。' : sourceStatus === 'available' || sourceStatus === 'ready' ? '原片已就绪' : '打开后从本机读取原片', 'content-media-status'));
      const choose = button(item.id === story.id ? '重新观看' : '观看原片', 'content-primary', () => { onStory(item); close(false); });
      card.append(choose);
      const enhanced = button('增强成片 · 本机未恢复', 'content-secondary', () => {});
      enhanced.disabled = true; card.append(enhanced);
      if (item.history) card.append(button('查看历史验收记录', 'content-text-button', () => open('history', item, catalog)));
      body.append(card);
    }
    body.append(paragraph('原片从本机读取。历史增强视频尚未恢复，当前仅可查看其记录。', 'content-note'));
  }
  function history(story) {
    const record = story.history;
    if (!record) { body.append(paragraph('当前素材没有已保存的历史成片记录。')); return; }
    body.append(node('span', 'content-badge', '历史记录 · 2026.10.07'), paragraph(record.analysis?.summary || '', 'content-lead'));
    const status = section('验收状态');
    status.append(paragraph(record.contentReview?.acceptedForShowcase ? '当时的 AI 内容复核已接受为展示版本。' : '当时记录未标记为接受展示。'));
    status.append(paragraph('这份记录来自之前的真实运行；本轮没有发起新推理。本机尚无增强 MP4，历史验收不等于当前已恢复播放。', 'content-note'));
    const details = node('dl', 'content-details');
    details.append(detail('核验时间', formatBeijingDate(record.verifiedAt)), detail('时长', `${Number(record.durationSeconds).toFixed(3)} 秒`), detail('画面', `${record.width} × ${record.height}`), detail('音轨', record.audioPresent ? '保留' : '未记录'), detail('历史播放', record.browserPlaybackVerified ? '已核对至片尾' : '见原记录'), detail('处理耗时', `${record.elapsedSeconds} 秒`));
    status.append(details); body.append(status);
    const chapters = section('历史成片中的章节');
    for (const chapter of record.analysis?.plan?.chapters || []) {
      const row = section(chapter.title);
      row.append(paragraph(chapter.caption), button(`在原片回看 ${formatVideoTime(chapter.start)}`, 'content-text-button', () => { if (story.id !== activeStory?.id) onStory(story); seek(chapter.start, { chapter, historical: true }); }));
      chapters.append(row);
    }
    body.append(chapters);
    const trace = section('当时的处理步骤');
    const names = { inspect_frames: '读取实际视频帧', read_official_event: '读取官方事件', validate_story: '校验章节与来源' };
    for (const step of record.analysis?.trace || []) trace.append(paragraph(`${step.step}. ${names[step.tool] || step.tool} · ${step.status === 'succeeded' ? '完成' : step.status}`, 'content-history-step'));
    body.append(trace);
    const archive = section('记录标识');
    archive.append(node('code', 'content-source-path', `Job ${record.jobId}`), node('code', 'content-source-path', `MP4 SHA-256 ${record.outputSha256}`), node('code', 'content-source-path', record.recordSource));
    body.append(archive, paragraph('历史内容复核由 AI 助手完成，未经人类篮球专家认证。', 'content-note'));
  }
  function open(kind, story, catalog = []) {
    if (!TITLES[kind]) throw new Error(`未知抽屉类型：${kind}`);
    if (!story) throw new Error('打开内容抽屉需要比赛素材。');
    if (!openState) lastFocus = document.activeElement;
    activeStory = story;
    const [label, english] = TITLES[kind];
    title.textContent = label; eyebrow.textContent = english;
    element.dataset.kind = kind;
    body.replaceChildren();
    ({ moments, data, sources, library, history })[kind](story, catalog);
    element.hidden = false; openState = true;
    body.scrollTop = 0;
    requestAnimationFrame(() => { if (openState) closeButton.focus({ preventScroll: true }); });
  }
  function close(restoreFocus = true) {
    if (!openState) return;
    element.hidden = true; openState = false;
    if (restoreFocus && lastFocus?.isConnected) lastFocus.focus({ preventScroll: true });
    onClose();
  }
  element.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
  });
  return { element, open, close, get isOpen() { return openState; } };
}
