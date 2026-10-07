"""Build the two reviewed editorial cases from immutable factual snapshots.

No online access, model call, scoring certification or automatic video analysis.
Run: python3 product/data/build_stories.py
"""
import json
from pathlib import Path
from match_events import bind_clip

ROOT = Path(__file__).resolve().parents[2]
HERE = Path(__file__).resolve().parent
SOURCES = ROOT / 'product/research/sources'
TRAINING_URL = 'https://comfile.csdnimg.cn/file/train_video.zip'
METRIC_DEFINITION_URL = 'https://china.nba.cn/inside-the-game/glossary'
load = lambda p: json.loads(p.read_text())
anchors = {a['sample']: a for a in load(HERE / 'video-anchors.json')['anchors']}
bindings = {}


def make_story(sample, text):
    a = anchors[sample]
    page = load(SOURCES / f'nba-page-{sample}.json')
    shots = load(SOURCES / f'gpshot-{sample}.json')
    binding = bind_clip(page, shots, a)
    if not binding['verified']:
        raise ValueError(f'{sample}: official event does not pass: {binding}')
    bindings[sample] = binding
    m = binding['matched']; event = m['eventId']; ratio = m['expectedFg']
    pbp_url = page['extraction']['sourceUrl']
    metric_url = f'https://api.nba.cn/nba-web/api/web/inside/gpShot?gameId={a["gameId"]}&playerId={a["playerId"]}'
    identity = {'gameId': a['gameId'], 'eventId': event, 'playerId': a['playerId']}
    source_video = f'/samples/{sample}.mp4'
    evidence = []
    for frame in a['frames']:
        fid = f'{sample}-frame-{str(frame["videoTime"]).replace(".", "-")}'
        evidence.append({
            'id': fid, 'kind': 'observation', 'title': f'画面 · {frame["videoTime"]:g} 秒',
            'body': frame['observation'], 'sourceLabel': '主办方公开训练视频 · 已查看抽帧',
            'sourceUrl': f'{source_video}#t={frame["videoTime"]}', 'originalSourceUrl': TRAINING_URL,
            'videoTime': frame['videoTime'], 'frameUrl': f'/frames/{frame["file"]}',
            'annotationMethod': a['annotationMethod'], 'humanExpertReviewed': False,
            'scoreboard': {key: frame[key] for key in ('clock', 'shotClock', 'score') if key in frame}
        })
    pbp_id, metric_id, roster_id = f'{sample}-pbp-{event}', f'{sample}-xfg-{event}', f'{sample}-roster'
    evidence += [
        {'id': pbp_id, 'kind': 'official', 'title': 'NBA 官方逐回合记录',
         'body': text['pbpBody'], 'sourceLabel': 'NBA.com · Play-by-Play', 'sourceUrl': pbp_url,
         **identity, 'officialClock': text['clock'], 'period': a['period'],
         'actionNumber': event, 'actionId': m['actionId'], 'videoTime': text['metricTime'],
         'sourcePath': f'playByPlay.actions[actionNumber={event} & isFieldGoal=1]',
         'videoTimeMeaning': '编辑选择的数据揭示节点，不是官方出手时钟的逐帧换算。'},
        {'id': metric_id, 'kind': 'official', 'title': '这次出手的预期投篮命中率',
         'body': f'NBA 中国官网这次出手的原始数值为 {ratio}，换算显示为 {ratio:.1%}。这是机会质量的参考，不是球员的个人命中保证。',
         'sourceLabel': 'NBA 中国 · 逐次出手数据', 'sourceUrl': metric_url,
         **identity, 'value': ratio, 'unit': 'ratio', 'display': f'{ratio:.1%}',
         'videoTime': text['metricTime'], 'sourcePath': f'data.shotList[eventId={event}].value',
         'definitionUrl': METRIC_DEFINITION_URL},
        {'id': roster_id, 'kind': 'official', 'title': '本场身份与号码核对',
         'body': text['rosterBody'], 'sourceLabel': 'NBA.com · 本场名单',
         'sourceUrl': pbp_url, 'gameId': a['gameId'], 'playerId': a['playerId'],
         'sourcePath': 'game.homeTeamPlayers / game.awayTeamPlayers'}
    ]
    choices = []
    for key, label, title, body, time, ids in text['choices']:
        choices.append({'id': key, 'label': label, 'revealTitle': title, 'revealBody': body,
                        'focusTime': time, 'evidenceIds': [f'{sample}-{i}' for i in ids]})
    chapters = []
    for key, start, end, title, caption, kind, ids in text['chapters']:
        chapters.append({'id': key, 'start': start, 'end': end, 'title': title, 'caption': caption,
                         'kind': kind, 'evidenceIds': [f'{sample}-{i}' for i in ids]})
    return {
        'id': sample, 'sample': sample, 'title': text['title'], 'subtitle': text['subtitle'], 'kicker': text['kicker'],
        'player': text['player'], 'opponent': text['opponent'],
        'game': {'date': text['date'], 'dateTimezone': 'Asia/Shanghai', 'localDate': text['localDate'],
                 'period': a['period'], 'clock': text['clock'], 'score': text['score'],
                 'scoreBefore': a['scoreBefore'], 'scoreAfter': a['scoreAfter'],
                 'homeTeam': text['homeTeam'], 'awayTeam': text['awayTeam'], 'gameId': a['gameId']},
        'durationSeconds': a['durationSeconds'], 'sourceVideo': source_video,
        'sourceVideoSha256': text['sha256'], 'originalSourceUrl': TRAINING_URL,
        'poster': f'/frames/{text["poster"]}',
        'hook': {'question': '这一拍，你先看谁？', 'choiceMode': 'attention', 'isQuiz': False,
                 'choices': choices, 'answerId': 'defender', 'answerMeaning': '编辑推荐的关注视角；没有唯一正确选择。',
                 'revealTitle': choices[1]['revealTitle'], 'revealBody': choices[1]['revealBody']},
        'storyOptions': [{'id': c['id'], 'label': c['label'], 'description': c['revealBody'],
                          'focusTime': c['focusTime'], 'evidenceIds': c['evidenceIds']} for c in choices],
        'chapters': chapters,
        'chapterMode': '已核查的编辑候选段落，供 Agent 按观众视角选择和组织；不是 Agent 已生成的结果。',
        'keyMoment': {'start': text['slowStart'], 'end': text['slowEnd'], 'freezeAt': text['freezeAt'],
                      'playbackRate': 0.4, 'annotationMethod': a['annotationMethod'], 'kind': 'observation'},
        'evidence': evidence,
        'officialEvent': {'verified': True, **identity, 'expectedFg': ratio, 'made': m['made'],
            'period': a['period'], 'clock': text['clock'], 'description': text['pbpBody'],
            'actionNumber': event, 'actionId': m['actionId'], 'shotValue': m['shotValue'],
            'method': 'AI 助手实际查看抽帧后编辑锚定球员号码、节次、时钟区间与前后比分；确定性程序唯一匹配 NBA.com 出手，再以 gpShot.eventId = PBP.actionNumber 关联，并交叉校验球员、节次、命中及两分类型。',
            'evidenceUrls': [pbp_url, metric_url], 'bindingFile': 'event-bindings.json',
            'shotLocation': {k: m['officialShot'][k] for k in ('side','locX','locY')},
            'locationLimitation': '官网出手点位，不是视频像素或逐帧轨迹；当前产品未把这些点位贴到球员脚下。'},
        'shotMetric': {'id': f'{sample}-shot-metric', 'label': '预期投篮命中率', 'rawValue': ratio,
            'unit': 'ratio', 'display': f'{ratio:.1%}', 'evidenceId': metric_id, 'sourceUrl': metric_url, **identity,
            'definition': 'NBA 官方对本次出手机会的概率型参考值；不是这个球员的个人命中率或胜率。',
            'revealAt': text['metricTime']},
        'takeaway': text['takeaway'],
        'limitations': ['关键帧由 AI 助手实际查看后编辑选定，尚无人类篮球专家复核。',
            '官方事件时钟、转播时钟和视频秒数分别保留，不声称精确离手帧自动对齐。',
            '没有本事件可核准的引力、防守压力或胜率变化；不显示这些指标。',
            '已进球不等于此前防守没有影响，也不能从单次结果判断出手选择必然好坏。']
    }

flagg = make_story('flagg', {
    'title': '球进了，防守就消失了吗？', 'subtitle': '从持球推进到篮下终结，换个焦点再看这一球。', 'kicker': '末节 · 突破终结',
    'player': {'name': '库珀·弗拉格', 'number': '32', 'team': '独行侠', 'teamAbbreviation': 'DAL'}, 'opponent': '火箭',
    'date': '2026-02-01', 'localDate': '2026-01-31', 'clock': '1:34', 'score': '独行侠 105 — 107 火箭', 'homeTeam': 'HOU', 'awayTeam': 'DAL',
    'sha256': '9c3e4606d04e7f79e29a112952fcf069ebab202af207af500bfbc3338bc079ce',
    'poster': 'flagg-16.5s.jpg', 'metricTime': 18.5, 'slowStart': 15.4, 'slowEnd': 17.4, 'freezeAt': 16.5,
    'pbpBody': '末节 1:34，弗拉格突破挑篮命中两分，独行侠追至 105 比 107。',
    'rosterBody': 'NBA 本场名单：独行侠 32 号为库珀·弗拉格，与所查看画面号码一致。',
    'choices': [
        ('player','持球的弗拉格','先看他怎样接近篮筐','从外线推进到篮下，再看起跳时球与防守人的相对位置。',15.5,['frame-9','frame-15-5','frame-16-5','roster']),
        ('defender','篮下的防守人','看那双举起的手','把目光放在篮下：弗拉格起跳时，正面防守人双臂举起，终结动作就在防守面前完成。',16.5,['frame-16-5','frame-17']),
        ('data','这一球的数据','结果与机会，分开看','这球得到两分。再看官方的预期投篮命中率，把已经发生的结果和这次机会的质量一起读懂。',18.5,['pbp-666','xfg-666','frame-21'])
    ],
    'chapters': [
        ('context',0,9,'先看局面','末节，独行侠落后四分。','observation',['frame-0-2']),
        ('approach',9,15.4,'从外线到篮下','弗拉格持球推进，身前仍有防守。','observation',['frame-9','frame-15-5','roster']),
        ('key-beat',15.4,17.4,'慢看这一拍','起跳这一帧，正面防守人双臂举起。','observation',['frame-16-5']),
        ('record',17.4,21.548118,'用数据回看机会','官方确认两分命中；机会质量与结果分开看。','official',['pbp-666','xfg-666','frame-21'])
    ],
    'takeaway': '弗拉格起跳时，正面防守人的双臂还在。把这一帧与两分命中的结果连起来看，就能读懂终结的细节。'
})
amen = make_story('amen', {
    'title': '先起跳的，是谁？', 'subtitle': '投篮前的一小段时间，藏着转播里容易漏看的先后顺序。', 'kicker': '第三节 · 出手节奏',
    'player': {'name': '阿门·汤普森', 'number': '1', 'team': '火箭', 'teamAbbreviation': 'HOU'}, 'opponent': '独行侠',
    'date': '2026-01-04', 'localDate': '2026-01-03', 'clock': '7:25', 'score': '火箭 62 — 63 独行侠', 'homeTeam': 'DAL', 'awayTeam': 'HOU',
    'sha256': '7ec745f5f1e75b0c6d6dd27d409875f67c2ac3ab76c73f7123794c96be5aee22',
    'poster': 'amen-17.5s.jpg', 'metricTime': 19.5, 'slowStart': 16.8, 'slowEnd': 18.5, 'freezeAt': 17.5,
    'pbpBody': '第三节 7:25，阿门·汤普森急停跳投命中两分，官方记录杜兰特助攻；火箭追至 62 比 63。',
    'rosterBody': 'NBA 本场名单：火箭 1 号为阿门·汤普森，7 号为凯文·杜兰特；独行侠 00 号为马克斯·克里斯蒂。',
    'choices': [
        ('player','接球的阿门','先看球到了谁手里','球从杜兰特来到阿门手中。先看阿门接球后的推进，再看他与防守人的起跳顺序。',16,['frame-15','frame-16','roster']),
        ('defender','先起跳的防守人','他先离开了地面','克里斯蒂已经起跳，阿门还把球握在手里。接着看阿门起跳出手，两人的节奏在这里错开。',17.5,['frame-17-5','frame-18','roster']),
        ('data','这一球的数据','进球之后，再看机会','阿门投进两分，杜兰特记一次助攻。再看预期投篮命中率，为这次进攻补上机会质量这一层信息。',19.5,['pbp-396','xfg-396','frame-21'])
    ],
    'chapters': [
        ('context',0,15,'先看局面','第三节，火箭落后三分。','observation',['frame-0']),
        ('transfer',15,16.8,'球来到阿门手中','持球人发生变化，进攻时钟所剩不多。','observation',['frame-15','frame-16','roster']),
        ('key-beat',16.8,18.5,'慢看这一拍','防守人先起跳时，阿门仍持球。','observation',['frame-17-5','frame-18']),
        ('record',18.5,22.894875,'用数据回看机会','官方确认跳投命中，并记录杜兰特助攻。','official',['pbp-396','xfg-396','frame-21'])
    ],
    'takeaway': '防守人先起跳，阿门随后出手。把目光从球移到两个人身上，同一球的节奏就清楚了。'
})

stories = {'version': 'keyplay-stories-v1', 'updatedAt': '2026-10-07',
           'purpose': '主办方公开训练素材的已核验案例；内部产品数据，不是赛事统一输入协议。',
           'stories': [flagg, amen]}
for story in stories['stories']:
    ids = {e['id'] for e in story['evidence']}
    assert len(ids) == len(story['evidence'])
    for segment in story['chapters'] + story['hook']['choices']:
        assert set(segment['evidenceIds']) <= ids, segment
    assert all(0 <= e.get('videoTime',0) < story['durationSeconds'] for e in story['evidence'])
    assert all(0 <= c['start'] < c['end'] <= story['durationSeconds'] for c in story['chapters'])
    assert story['shotMetric']['rawValue'] == story['officialEvent']['expectedFg']
# Preserve only independently verified showcase renders for the same source clip.
previous_path = HERE / 'stories.json'
if previous_path.exists():
    previous = {item['id']: item for item in json.loads(previous_path.read_text()).get('stories', [])}
    for story in stories['stories']:
        old = previous.get(story['id'], {})
        job_id = old.get('showcaseJobId', '')
        if (len(job_id) != 32 or any(c not in '0123456789abcdef' for c in job_id)
                or old.get('sourceVideoSha256') != story['sourceVideoSha256']):
            continue
        receipt_path = HERE.parent / 'evidence' / f'run-{job_id}.json'
        if not receipt_path.exists():
            continue
        receipt = json.loads(receipt_path.read_text())
        if receipt.get('sample') == story['id'] and receipt.get('outputSha256') == old.get('showcaseOutputSha256'):
            for field in ('enhancedVideo', 'analysisUrl', 'showcaseJobId', 'showcaseOutputSha256'):
                if field in old:
                    story[field] = old[field]
(HERE / 'stories.json').write_text(json.dumps(stories,ensure_ascii=False,indent=2)+'\n')
(HERE / 'event-bindings.json').write_text(json.dumps({'version': 'nba-event-bindings-v1', 'results': bindings}, ensure_ascii=False, indent=2)+'\n')
print('Saved two verified stories with distinct audience perspectives.')
