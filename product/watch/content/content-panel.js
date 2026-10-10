import { safeSourceUrl, formatVideoTime, formatBeijingDate, loadStoryRecord } from '../adapters/catalog.js';

const TITLES = { moments: ['关键时刻', 'MOMENTS'], data: ['这一球的数据', 'SHOT DATA'], sources: ['画面与出处', 'SOURCES'], library: ['选择比赛', 'MATCH LIBRARY'], history: ['成片与验收记录', 'RUN RECORD'] };
const KINDS = { official: '官方记录', observation: '画面观察', video_frame: '实际输入帧' };
const RL_LAYERS = { basic: '基础表现', advanced: '派生效率', gravity: '深度 · 引力', leverage: '深度 · 影响力', shotdifficulty: '深度 · 机会质量' };
const PROFILE_SECTIONS = { gameOffense: '本场进攻', gameEfficiency: '本场效率', gameDefense: '本场防守', gameGeneral: '本场通用', seasonOffense: '赛季进攻背景', seasonDefense: '赛季防守背景', seasonShooting: '赛季投篮背景', seasonOverall: '赛季综合影响力' };
let nextPanelId = 0;

/** Service verification and use in this movie are independent claims. */
export function rlMovieState(story) {
  const scout = story?.scout;
  const verified = !!scout && ['available', 'trainedModelUsed', 'selectionVerified', 'lineageVerified', 'actualRL', 'modelInvoked'].every(key => scout[key] === true);
  const evidence = verified && Array.isArray(scout.evidence) ? scout.evidence : [];
  const selectedIds = evidence.map(item => item.evidenceId).filter(Boolean);
  const used = new Set(story?.rlVideoUse?.evidenceIdsUsed || []);
  const inMovie = verified && story.enhancedAvailable === true && scout.threeLayersCovered === true
    && story.rlVideoUse?.narrativeUsed === true && story.rlVideoUse?.burnedIntoVideo === true
    && selectedIds.length >= 3 && selectedIds.every(id => used.has(id));
  return { verified, evidence, inMovie, invocation: verified ? scout.invocationMode === 'live' && scout.modelInvokedThisRequest === true ? '成片任务实时调用 · 选证已核验' : '已保存模型调用回放 · 选证已核验' : '模型选证不可用或尚未核验' };
}

export function evidenceScope(evidence, story) {
  const period = story?.rlEvidencePeriods?.[evidence?.periodRef];
  if (evidence?.grain === 'player-game') return `本场赛后统计${period?.gameDate ? ` · ${period.gameDate}（NBA 东部日期）` : ''}${evidence.gameId ? ` · 比赛 ${evidence.gameId}` : ''}`;
  if (evidence?.grain === 'player-season') return `${period?.season || '时期未记录'} 赛季来源快照 · 非本回合测量`;
  return `统计粒度 ${evidence?.grain || '未记录'} · 时期 ${evidence?.periodRef || '未记录'}`;
}

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
  let historyRequest = 0;

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
    rlData(story);
    playerData(story);
    const court = section('战术板的数据');
    court.append(paragraph(story.sample === 'flagg' ? '弗拉格样片使用编辑站位与球权示意。D / W 是匿名编号；空心点是过去的最近位置。' : story.sample === 'formal' ? '本片战术定格与俯视图已烧录到特效版本。右侧战术板没有正式素材的连续追踪点位。' : '这段阿门样片没有配套的逐帧战术示意，战术板保持空白。'));
    court.append(paragraph('示意点、移动线路和篮球位置未经人类专家核准，不是官方追踪数据。', 'content-note'));
    body.append(court);
  }
  function rlData(story) {
    if (!story.scout) return;
    const state = rlMovieState(story), scout = story.scout;
    const block = section('RL 数据球探');
    block.classList.add('content-scout');
    block.append(node('span', `content-badge${state.inMovie ? ' is-rl-movie' : ''}`, state.inMovie ? '三层证据已进入本片' : '本片 RL 烧录尚未验收'));
    block.append(paragraph(state.invocation, 'content-copy'));
    if (state.verified) {
      block.append(paragraph(`${scout.model || '模型未记录'} · AWS SageMaker`, 'content-note'));
      block.append(paragraph(`叙事采用 ${story.rlVideoUse?.narrativeUsed === true ? '是' : '否'} · 成片烧录 ${story.rlVideoUse?.burnedIntoVideo === true ? '是' : '否'}`, 'content-note'));
      const cards = node('div', 'content-scout-cards');
      for (const evidence of state.evidence) {
        const card = node('article', 'content-scout-card');
        card.append(node('span', 'content-eyebrow', RL_LAYERS[evidence.family] || evidence.family), node('h4', '', evidence.label || evidence.metric), node('strong', 'content-scout-value', evidence.display ?? '未记录'));
        card.append(paragraph(evidenceScope(evidence, story), 'content-note'), paragraph(`原始值 ${evidence.value ?? '未记录'} · 单位 ${evidence.unit || '未记录'}`, 'content-note'));
        const source = story.rlEvidenceSources?.[evidence.sourceRef];
        appendLink(card, 'NBA 数据出处 ↗', source?.url);
        card.append(node('code', 'content-source-path', evidence.evidenceId || '证据 ID 未记录'));
        cards.append(card);
      }
      block.append(cards);
      block.append(paragraph('RL 模型选择数据证据；程序核对来源与口径。赛季背景不证明这次防守的原因或这一球的胜负。', 'content-note'));
    } else block.append(paragraph('当前成片继续使用原有官方数据；模型调用成功与烧录成功分别核验。', 'content-note'));
    body.append(block);
  }
  function profileData(profile, label, story) {
    if (!profile?.player) return null;
    const block = section(`${label} · ${profile.player.displayName || profile.player.playerId}`);
    block.classList.add('content-player-profile');
    const facts = new Map((profile.facts || []).map(item => [item.evidenceId, item]));
    block.append(paragraph(`球员 ${profile.player.playerId} · 比赛 ${profile.gameId || '未记录'}`, 'content-note'));
    for (const [key, label] of Object.entries(PROFILE_SECTIONS)) {
      const selected = (profile.sections?.[key] || []).map(id => facts.get(id)).filter(Boolean);
      if (!selected.length) continue;
      const group = node('details', 'content-profile-group');
      group.append(node('summary', '', label));
      const list = node('dl', 'content-profile-facts');
      for (const fact of selected) {
        const row = detail(fact.label || fact.metric, fact.display ?? '未记录');
        row.title = `${evidenceScope(fact, story)} · 单位 ${fact.unit} · ${fact.evidenceId}`;
        list.append(row);
      }
      group.append(list, paragraph(evidenceScope(selected[0], story), 'content-note'));
      block.append(group);
    }
    if (profile.derived?.length) {
      const group = node('details', 'content-profile-group'); group.append(node('summary', '', '同场计算与公式'));
      for (const row of profile.derived) {
        const item = section(row.label || row.metric);
        item.append(paragraph(row.available === true ? row.displayValue : row.reasonCode === 'zero_denominator' ? '分母为零，未计算' : '不可计算'), paragraph(`${row.formula || '公式未记录'} · ${evidenceScope(row, story)}`, 'content-note'));
        group.append(item);
      }
      block.append(group);
    }
    if (profile.missingMetrics?.length) block.append(paragraph(`未提供：${profile.missingMetrics.map(item => typeof item === 'string' ? item : item.metric || item.label).join(' · ')}`, 'content-note'));
    return block;
  }
  function playerData(story) {
    const comparison = story.playerComparison;
    if (!comparison?.attacker) return;
    const block = section('攻防背景与同场比较');
    block.append(node('span', 'content-badge', '官方数据 + 确定性计算'), paragraph('两人的本场与赛季背景独立保留；这些比较由算术计算，不能记作 RL 推理。', 'content-note'));
    const attacker = profileData(comparison.attacker, '进攻球员背景', story), opponent = profileData(comparison.opponent, '所选对手背景', story);
    if (attacker) block.append(attacker);
    if (opponent) block.append(opponent);
    block.append(paragraph(comparison.matchupVerified === true ? '直接防守身份已另行核验；统计仍按各自范围展示。' : '所选对手是同场出场球员；未核验该时刻在场或直接防守身份。', 'content-note'));
    if (comparison.opponentChoices?.length) {
      const roster = node('details', 'content-profile-group');
      roster.append(node('summary', '', `同场对手名单 · ${comparison.opponentChoices.length} 人`));
      roster.append(paragraph(comparison.opponentChoices.map(player => `${player.displayName || player.playerId}${String(player.playerId) === String(comparison.selectedOpponentId) ? '（当前比较）' : ''}`).join(' · ')));
      roster.append(paragraph('其他对手需重新生成其档案后比较；页面不以当前两人的统计替换。', 'content-note'));
      block.append(roster);
    }
    const facts = new Map([...(comparison.attacker.facts || []), ...(comparison.opponent?.facts || [])].map(item => [item.evidenceId, item]));
    const rows = comparison.comparisons || [];
    if (rows.length) {
      const group = node('details', 'content-profile-group'); group.open = true;
      group.append(node('summary', '', '同口径差值 · 左侧减右侧'));
      for (const row of rows) {
        const card = node('article', 'content-comparison-row');
        const [left, right] = (row.evidenceIds || []).map(id => facts.get(id));
        card.append(node('h4', '', row.label || row.metric));
        card.append(paragraph(`${left?.display ?? '未记录'}  /  ${right?.display ?? '未记录'}`, 'content-comparison-pair'));
        card.append(paragraph(`差值 ${row.displayDifference ?? '未记录'} · ${row.differenceUnit === 'percentage_points' ? '百分点' : row.differenceUnit === 'count' ? '计数' : '来源分数'}`, 'content-note'));
        card.append(paragraph(evidenceScope(row, story), 'content-note'));
        group.append(card);
      }
      block.append(group);
    }
    block.append(paragraph('两人分数或效率差不等于直接对位优势；防守影响力、引力和机会质量保留来源分数，不换算为胜率。', 'content-note'));
    body.append(block);
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
    appendLink(original, story.sample === 'formal' ? '主办方正式比赛素材 ↗' : '主办方公开训练视频包 ↗', story.originalSourceUrl);
    original.append(paragraph('原转播比分牌保留在画面内。', 'content-note'));
    original.append(node('code', 'content-source-path', `SHA-256 ${story.sourceVideoSha256 || '未记录'}`));
    body.append(original);
    rlSources(story);
  }
  function rlSources(story) {
    const facts = [...(rlMovieState(story).evidence || []), ...(story.playerComparison?.attacker?.facts || []), ...(story.playerComparison?.opponent?.facts || [])];
    const refs = [...new Set(facts.map(item => item.sourceRef).filter(Boolean))];
    if (!refs.length) return;
    const block = section('RL 选证与球员档案出处');
    block.append(paragraph('选证卡、球员档案和算术结果分别保留证据 ID；统计时期与画面时间不混用。', 'content-note'));
    for (const ref of refs) {
      const source = story.rlEvidenceSources?.[ref];
      const card = node('details', 'content-profile-group'); card.append(node('summary', '', source?.rowKey || ref));
      if (!source) card.append(paragraph(`来源引用 ${ref} 未提供原始记录。`, 'content-note'));
      else {
        appendLink(card, '打开 NBA 原始来源 ↗', source.url);
        card.append(node('code', 'content-source-path', source.path), node('code', 'content-source-path', `SHA-256 ${source.sha256 || '未记录'}`));
        card.append(paragraph(`取得于 ${formatBeijingDate(source.retrievedAt)}`, 'content-note'));
      }
      for (const fact of facts.filter(item => item.sourceRef === ref)) card.append(paragraph(`${fact.evidenceId} · ${fact.label || fact.metric} · ${evidenceScope(fact, story)}`, 'content-note'));
      block.append(card);
    }
    body.append(block);
  }
  function library(story, catalog) {
    body.append(paragraph(story.sample === 'formal' ? '正式比赛素材' : '公开训练样片', 'content-lead'));
    for (const item of catalog) {
      const card = section();
      card.classList.add('content-library-card');
      if (item.id === story.id) card.classList.add('is-selected');
      card.append(node('span', 'content-eyebrow', item.id === story.id ? '正在观看' : '已登记素材'), node('h3', '', `${item.player?.team || ''} · ${item.opponent || ''}`), paragraph(item.title));
      card.append(paragraph(`${item.player?.name || ''} · ${Number(item.durationSeconds || 0).toFixed(2)} 秒 · ${item.game?.date || ''} 北京时间`, 'content-note'));
      const sourceStatus = item.media?.source?.status;
      card.append(paragraph(sourceStatus === 'missing' || sourceStatus === 'error' ? '原片未加载，请检查素材与网络。' : sourceStatus === 'available' || sourceStatus === 'ready' ? '原片已就绪' : '打开后读取同源原片', 'content-media-status'));
      const choose = button(item.id === story.id ? '重新观看' : '观看原片', 'content-primary', () => { onStory(item, 'source'); close(false); });
      card.append(choose);
      const enhanced = button(item.enhancedAvailable ? '观看增强成片' : '增强成片暂不可用', 'content-secondary', () => { onStory(item, 'enhanced'); close(false); });
      enhanced.disabled = !item.enhancedAvailable; card.append(enhanced);
      if (item.history || item.enhancedAvailable) card.append(button('查看成片验收记录', 'content-text-button', () => open('history', item, catalog)));
      body.append(card);
    }
    body.append(paragraph(story.sample === 'formal' ? '正式原片与特效成片分开播放；特效版包含定格与回放，回看节点按编辑时间线定位。' : '原片与增强成片均使用已登记的同源媒体。增强成片保留原视频时间轴；编辑战术板不是官方逐帧追踪。', 'content-note'));
  }
  function renderHistory(story, record) {
    body.replaceChildren();
    if (!record) { body.append(paragraph('当前素材没有已保存的成片记录。')); return; }
    if (record.mode === 'editorial') {
      body.append(node('span', 'content-badge', '正式素材 · 本地特效成片'));
      body.append(paragraph('复用 GameBuddy 视觉资产：球员高亮、战术定格、俯视示意、慢放与官方数据揭示。', 'content-lead'));
      const facts = node('dl', 'content-details');
      facts.append(detail('时长', `${record.durationSeconds.toFixed(3)} 秒`), detail('画面', `${record.width} × ${record.height}`), detail('完整解码', record.fullVideoAudioDecode ? '通过' : '待完成'), detail('声音', record.aiNarrationUsed ? 'AI 配音' : '正式原片广播与提示音'));
      body.append(facts, node('code', 'content-source-path', `源片 SHA-256 ${record.sourceSha256}`), node('code', 'content-source-path', `成片 SHA-256 ${record.outputSha256}`), paragraph('本轮为视觉联调版本。正式素材的 Agent 与豆包解说接入分别记录进度。', 'content-note'));
      return;
    }
    const historical = record.historical === true || !story.enhancedAvailable;
    body.append(node('span', 'content-badge', historical ? '历史运行 · 原始验收' : '正式账号运行 · 原始验收'), paragraph(record.analysis?.summary || '', 'content-lead'));
    const status = section('验收状态');
    status.append(paragraph(record.contentReview?.acceptedForShowcase === true ? '原始 AI 内容复核已接受为展示版本。' : '此记录没有已接受展示的内容复核标志。'));
    status.append(paragraph('记录来自实际运行，本面板不会发起新推理。原始播放验收只描述当时结果；当前能否播放以播放器为准。', 'content-note'));
    const details = node('dl', 'content-details');
    details.append(detail('核验时间', formatBeijingDate(record.verifiedAt)), detail('时长', Number.isFinite(record.durationSeconds) ? `${record.durationSeconds.toFixed(3)} 秒` : null), detail('画面', record.width && record.height ? `${record.width} × ${record.height}` : null), detail('音轨', record.audioPresent === true ? '保留' : '未记录'), detail('原始播放', record.browserPlaybackVerified === true ? '已核对至片尾' : '未记录'), detail('处理耗时', Number.isFinite(record.elapsedSeconds) ? `${record.elapsedSeconds} 秒` : null));
    status.append(details); body.append(status);
    const chapters = section('实际成片中的章节');
    for (const chapter of record.analysis?.plan?.chapters || []) {
      const row = section(chapter.title);
      row.append(paragraph(chapter.caption), button(`在原片回看 ${formatVideoTime(chapter.start)}`, 'content-text-button', () => { onStory(story, 'source'); seek(chapter.start, { chapter, historical }); }));
      chapters.append(row);
    }
    body.append(chapters);
    const actualStory = { ...story, scout: record.analysis?.scout, playerComparison: record.analysis?.playerComparison, rlEvidenceSources: record.analysis?.rlEvidenceSources, rlEvidencePeriods: record.analysis?.rlEvidencePeriods, rlVideoUse: record.analysis?.rlVideoUse };
    rlData(actualStory);
    playerData(actualStory);
    rlSources(actualStory);
    const trace = section('实际处理步骤');
    const names = { inspect_frames: '读取实际视频帧', read_official_event: '读取官方事件', validate_story: '校验章节与来源' };
    for (const step of record.analysis?.trace || []) trace.append(paragraph(`${step.step}. ${names[step.tool] || step.tool} · ${step.status === 'succeeded' ? '完成' : step.status}`, 'content-history-step'));
    body.append(trace);
    const archive = section('记录标识');
    archive.append(node('code', 'content-source-path', `Job ${record.jobId}`), node('code', 'content-source-path', `MP4 SHA-256 ${record.outputSha256}`), node('code', 'content-source-path', record.recordSource));
    body.append(archive, paragraph('内容复核由 AI 助手完成，未经人类篮球专家认证；记录时间不会改写为页面打开时间。', 'content-note'));
  }
  function history(story) {
    const request = historyRequest;
    if (!story.enhancedAvailable) { renderHistory(story, story.history); return; }
    body.append(paragraph('正在读取同源成片验收记录……', 'content-lead'));
    loadStoryRecord(story).then(record => {
      if (request === historyRequest && openState && activeStory === story && element.dataset.kind === 'history') renderHistory(story, record);
    }).catch(error => {
      if (request !== historyRequest || !openState || activeStory !== story || element.dataset.kind !== 'history') return;
      body.replaceChildren(paragraph(error.message || '成片记录暂不可用。'), paragraph('原片与增强成片播放不受此记录读取失败影响。', 'content-note'));
    });
  }
  function open(kind, story, catalog = []) {
    if (!TITLES[kind]) throw new Error(`未知抽屉类型：${kind}`);
    if (!story) throw new Error('打开内容抽屉需要比赛素材。');
    if (!openState) lastFocus = document.activeElement;
    activeStory = story; historyRequest++;
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
    element.hidden = true; openState = false; historyRequest++;
    if (restoreFocus && lastFocus?.isConnected) lastFocus.focus({ preventScroll: true });
    onClose();
  }
  element.addEventListener('keydown', event => {
    if (event.key === 'Escape') { event.preventDefault(); event.stopPropagation(); close(); }
  });
  return { element, open, close, get isOpen() { return openState; } };
}
