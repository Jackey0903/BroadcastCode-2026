#!/usr/bin/env python3
"""Build source-backed technical presentation figures without cloud calls."""
from collections import Counter
import csv
import hashlib
import json
from pathlib import Path
import subprocess

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import numpy as np

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]
RESULTS = ROOT / 'product/rl/results/evidence-v1'
FIGURES = HERE / 'figures'
FONT_PATH = Path('/System/Library/Fonts/Supplemental/Arial Unicode.ttf')
if FONT_PATH.is_file():
    font_manager.fontManager.addfont(str(FONT_PATH))
    plt.rcParams['font.family'] = font_manager.FontProperties(fname=str(FONT_PATH)).get_name()
plt.rcParams.update({'svg.fonttype': 'none', 'axes.unicode_minus': False, 'font.size': 18})


def read_json(path):
    return json.loads(path.read_text(encoding='utf-8'))


def write_csv(name, rows):
    with (HERE / name).open('w', newline='', encoding='utf-8-sig') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def theme(dark):
    return {'background': '#10171c' if dark else '#ffffff',
            'text': '#eaf2f6' if dark else '#17242e',
            'muted': '#abbcc8' if dark else '#5b6b78',
            'grid': '#33434f' if dark else '#dae2e8',
            'blue': '#69c5ff' if dark else '#1472c4',
            'orange': '#ffaf72' if dark else '#d55f16',
            'green': '#81dfb2' if dark else '#08794a'}


def style_axes(ax, colors):
    ax.set_facecolor(colors['background'])
    for spine in ('top', 'right'):
        ax.spines[spine].set_visible(False)
    for spine in ('left', 'bottom'):
        ax.spines[spine].set_color(colors['grid'])
    ax.tick_params(colors=colors['muted'], labelsize=17)
    ax.xaxis.label.set_color(colors['text'])
    ax.yaxis.label.set_color(colors['text'])
    ax.grid(axis='y', color=colors['grid'], linewidth=.8, alpha=.7)
    ax.set_axisbelow(True)


def save_plot(fig, stem, dark):
    name = stem + ('-dark' if dark else '-light')
    fig.savefig(FIGURES / (name + '.png'), dpi=180, facecolor=fig.get_facecolor())
    fig.savefig(FIGURES / (name + '.svg'), facecolor=fig.get_facecolor())
    plt.close(fig)


def draw_rl_curve(audit, dark):
    c = theme(dark)
    fig = plt.figure(figsize=(16, 9), facecolor=c['background'])
    ax = fig.add_axes([.09, .27, .86, .49])
    style_axes(ax, c)
    rows = audit['steps']
    x = [row['step'] for row in rows]
    y = [row['meanReward'] for row in rows]
    updated = [row for row in rows if row['updateGroups'] > 0]
    ax.plot(x, y, color=c['blue'], linewidth=2.4, marker='o', markersize=5,
            label='当轮8条轨迹的平均奖励')
    ax.scatter([row['step'] for row in updated], [row['meanReward'] for row in updated],
               color=c['orange'], edgecolor=c['background'], s=130, zorder=5,
               label='发生策略权重更新的轮次')
    ax.set(xlim=(.5, 30.5), ylim=(-.12, 1.12), xlabel='RL采样轮次', ylabel='当轮平均奖励')
    ax.set_xticks([1, 5, 10, 15, 20, 25, 30])
    ax.set_yticks([0, .25, .5, .75, 1])
    legend = ax.legend(loc='lower left', frameon=False, fontsize=17)
    for label in legend.get_texts(): label.set_color(c['text'])
    fig.text(.08, .9, 'Agentic RL采样与策略更新', fontsize=29, color=c['text'], weight='bold')
    fig.text(.08, .825, '30轮采样 · 240条轨迹 · 7次真实权重更新', fontsize=24, color=c['orange'])
    fig.text(.09, .14, '每轮2个任务 × 每题4条轨迹；60组中9组有奖励差异，51组奖励相同', fontsize=17, color=c['muted'])
    fig.text(.09, .085, '各轮任务变化，曲线表示采样过程；模型效果由固定验证／测试题另行比较', fontsize=17, color=c['muted'])
    fig.text(.09, .035, '来源：冻结RL更新审计；单随机种子31；保留全部30轮', fontsize=14, color=c['muted'])
    save_plot(fig, '01-rl-training-curve', dark)


def draw_comparison(rows, dark):
    c = theme(dark)
    fig = plt.figure(figsize=(16, 9), facecolor=c['background'])
    ax = fig.add_axes([.1, .26, .82, .5])
    style_axes(ax, c)
    lookup = {(row['stage'], row['split']): row for row in rows}
    stages, x, width = ['base', 'sft', 'rl'], np.arange(3), .29
    for split, offset, color, label in [('val', -width / 2, c['blue'], '验证集（16题）'),
                                         ('test', width / 2, c['green'], '测试集（16题）')]:
        values = [lookup[stage, split]['successes'] / 16 * 100 for stage in stages]
        bars = ax.bar(x + offset, values, width, color=color, label=label)
        for bar, stage in zip(bars, stages):
            row = lookup[stage, split]
            percentage = row['successes'] / row['n'] * 100
            text = f'{percentage:g}%\n{row["successes"]}/{row["n"]}'
            ax.text(bar.get_x() + bar.get_width() / 2, bar.get_height() + 3,
                    text, ha='center', va='bottom', fontsize=20, color=c['text'])
    ax.set_ylim(0, 125)
    ax.set_yticks([0, 25, 50, 75, 100], ['0%', '25%', '50%', '75%', '100%'])
    ax.set_xticks(x, ['训练前 Base', '监督训练 SFT', '强化学习后 RL'])
    ax.set_ylabel('结构化证据任务成功率')
    legend = ax.legend(loc='upper left', frameon=False, fontsize=17)
    for label in legend.get_texts(): label.set_color(c['text'])
    fig.text(.08, .9, '固定题目上的模型效果对比', fontsize=29, color=c['text'], weight='bold')
    fig.text(.08, .825, 'SFT改善验证成功率93.75个百分点；本轮RL相对SFT增量为0', fontsize=22, color=c['orange'])
    fig.text(.1, .145, '三个阶段使用同一组题目；成功要求证据、指标、范围、格式与受控关系同时通过', fontsize=17, color=c['muted'])
    fig.text(.1, .09, '单种子、每组16题；此指标衡量工具任务，不是视频识别准确率或新比赛泛化', fontsize=17, color=c['muted'])
    fig.text(.1, .035, '基线为0，相对百分比提升无定义；图中显示绝对成功率与准确分母', fontsize=14, color=c['muted'])
    save_plot(fig, '02-model-comparison', dark)


ARCHITECTURE = r'''
digraph architecture {
 graph [rankdir=LR, bgcolor="BACKGROUND", pad=.45, nodesep=.35, ranksep=.55,
        fontname="Arial Unicode MS", fontsize=22, label="GameBuddy 技术架构与已验证路径", labelloc=t, fontcolor="INK"];
 node [shape=box, style="rounded,filled", fontname="Arial Unicode MS", fontsize=18,
       color="LINE", fillcolor="NODE", fontcolor="INK", margin=".18,.14"];
 edge [color="MUTED", arrowsize=.8, fontname="Arial Unicode MS", fontsize=14, fontcolor="MUTED"];
 sources [label="真实比赛视频 + 官方数据\n基础统计 / 派生效率 / 深度赛场"];
 evidence [label="统一证据层\n主体 · 事件 · 单位 · 时期 · 来源"];
 subgraph cluster_automatic {
  label="自动生成路径：弗拉格RL样片已验收"; fontcolor="BLUE"; color="LINE";
  queue [label="Lambda API → SQS → Worker\nDynamoDB任务状态"];
  scout [label="SageMaker 数据球探\nQwen2.5-3B\nQLoRA SFT + Agentic RL"];
  agent [label="视觉与叙事Agent\nAgentCore + Bedrock\n读图 / 取证 / 校验 / 修订"];
  burn [label="FFmpeg完整成片\n数据卡片 + 来源约束"];
  queue -> scout [label="按关注维度取证"];
  scout -> agent [label="已核验证据"];
  agent -> burn;
 }
 subgraph cluster_showcase {
  label="55秒正式作品：编辑视觉 + Agent审核 + 双人解说"; fontcolor="ORANGE"; color="LINE";
  edit [label="回合视觉编辑\n定格 / 战术板 / 慢放 / 命中动效"];
  review [label="AgentCore审核15段稿件\n外部TTS生成双人语音"];
  mix [label="55.055秒影音合成\n双音轨 / 双时间轴"];
  edit -> review -> mix;
 }
 delivery [label="S3持久化 → CloudFront\n原片 / 增强片 / 可核对产物"];
 viewer [label="陪伴式观赛体验\n沉浸 / 全场 / 半场\n回看 / 档案 / 来源与关注点"];
 verifier [label="EventBridge → Step Functions\n独立媒体验收\n可选Polly / Rekognition"];
 sources -> evidence;
 evidence -> scout;
 sources -> queue [label="登记素材"];
 evidence -> edit [label="正式事件与数据"];
 burn -> delivery;
 mix -> delivery;
 burn -> verifier [style=dashed, label="成片完成事件"];
 delivery -> viewer;
 foundation [label="工程支撑\nAWS CDK / IAM边界\nCloudWatch观测", shape=plaintext, fillcolor="BACKGROUND"];
 {rank=sink; viewer; foundation;}
}
'''

OVERVIEW = r'''
digraph overview {
 graph [rankdir=LR, bgcolor="BACKGROUND", pad=.45, nodesep=.4, ranksep=.4,
        fontname="Arial Unicode MS", fontsize=25, label="GameBuddy 系统能力总览", labelloc=t, fontcolor="INK"];
 node [shape=box, style="rounded,filled", fontname="Arial Unicode MS", fontsize=22,
       color="LINE", fillcolor="NODE", fontcolor="INK", margin=".18,.16"];
 edge [color="MUTED", arrowsize=.8];
 data [label="真实数据与视频\n基础 / 高阶 / 深度\n统一证据语义"];
 intelligence [label="多模型Agent协作\n3B数据球探\nAgentCore / Bedrock\n工具调用与事实校验"];
 production [label="回合视觉与解说\nFFmpeg / 双时间轴\n战术定格与慢放\n数据烧录 / 双人TTS"];
 cloud [label="AWS托管交付\nLambda / SQS / DDB\nS3 / CloudFront\n事件验收与观测"];
 experience [label="陪伴式观赛\n三态布局\n关注点与数据回看\n人物、战术与来源"];
 data -> intelligence -> production -> cloud -> experience;
}
'''

DATA_FUSION = r'''
digraph fusion {
 graph [rankdir=LR, bgcolor="BACKGROUND", pad=.5, nodesep=.4, ranksep=.65,
        fontname="Arial Unicode MS", fontsize=24, label="同一套真实证据贯穿训练、调用与展示", labelloc=t, fontcolor="INK"];
 node [shape=box, style="rounded,filled", fontname="Arial Unicode MS", fontsize=19,
       color="LINE", fillcolor="NODE", fontcolor="INK", margin=".2,.16"];
 edge [color="MUTED", arrowsize=.8, fontname="Arial Unicode MS", fontsize=14, fontcolor="MUTED"];
 basic [label="基础数据：1,513条\n得分 / 篮板 / 助攻等官方计数"];
 advanced [label="高阶派生：166条\neFG / TS\n保留官方操作数与公式"];
 depth [label="深度赛场：314条\nGravity / Leverage / Shot Difficulty"];
 schema [label="1,993条统一证据\n33名球员 · 4场比赛\n赛季背景分别标注\n身份 / 粒度 / 单位\n时期 / 来源哈希"];
 train [label="训练\n867道构建任务\n工具协议、证据选择与边界拒答"];
 invoke [label="Agent按关注维度取证\nspacing → Gravity\ncreation → Leverage\nshot_quality →\nShot Difficulty"];
 show [label="叙事与展示\n34分 · eFG54%\n赛季引力6.217\n分时卡片 / 来源 / 比较"];
 boundary [label="单次出手xFG独立标注\n赛季背景不等于\n本回合动作因果", shape=plaintext, fillcolor="BACKGROUND", fontsize=16];
 basic -> schema; advanced -> schema; depth -> schema;
 schema -> train; schema -> invoke; schema -> show;
 {rank=same; schema; boundary;}
}
'''


def draw_diagram(source, stem, dark):
    c = theme(dark)
    values = {'BACKGROUND': c['background'], 'INK': c['text'], 'LINE': c['grid'],
              'NODE': '#18242d' if dark else '#f4f7fa', 'MUTED': c['muted'],
              'BLUE': c['blue'], 'ORANGE': c['orange']}
    for key, value in values.items(): source = source.replace('"' + key + '"', '"' + value + '"')
    name = stem + ('-dark' if dark else '-light')
    file = FIGURES / (name + '.dot')
    file.write_text(source, encoding='utf-8')
    for kind in ('svg', 'png'):
        subprocess.run(['dot', '-T' + kind, '-Gdpi=150', str(file), '-o', str(FIGURES / (name + '.' + kind))], check=True)


def main():
    FIGURES.mkdir(parents=True, exist_ok=True)
    report = read_json(RESULTS / 'training-report.json')
    comparison = read_json(RESULTS / 'comparison.json')
    audit = read_json(RESULTS / 'rl-update-audit-20261010.json')
    sources = [RESULTS / name for name in ('training-report.json', 'comparison.json', 'rl-update-audit-20261010.json')]
    for split in ('val', 'test'):
        ids = None
        for stage in ('base', 'sft', 'rl'):
            path = RESULTS / f'evaluation-{stage}-{split}.jsonl'
            sources.append(path)
            rows = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
            current = [row['taskId'] for row in rows]
            assert len(rows) == len(set(current)) == 16
            if ids is None: ids = current
            assert current == ids
            successes = sum(bool(row['score'].get('valid')) and not row['score'].get('criticalErrors')
                            and row['score'].get('coverage', 0) >= .999 and row['score']['total'] >= .97 for row in rows)
            summary = next(row for row in comparison['rows'] if row['stage'] == stage and row['split'] == split)
            assert successes == summary['successes']
    assert [row['step'] for row in audit['steps']] == list(range(1, 31))
    assert sum(row['updateGroups'] > 0 for row in audit['steps']) == 7
    assert sum(row['updateGroups'] for row in audit['steps']) == 9
    assert sum(row['flatGroups'] for row in audit['steps']) == 51
    assert report['sftExamplesOptimized'] == 640 and report['rlSteps'] == 30
    write_csv('model-comparison.csv', comparison['rows'])
    write_csv('rl-training-curve.csv', audit['steps'])
    store = read_json(ROOT / 'product/rl/data/evidence/store.json')
    sources.extend([ROOT / 'product/rl/data/evidence/store.json', ROOT / 'product/app.js',
                    ROOT / 'product/rl/train_evidence.py', ROOT / 'product/rl/evidence_env.py',
                    ROOT / 'product/rl/product_bridge.py'])
    family_counts = dict(Counter(row['family'] for row in store['records']))
    assert family_counts == {'advanced': 166, 'basic': 1513, 'gravity': 90, 'leverage': 160, 'shotdifficulty': 64}
    for dark in (False, True):
        draw_rl_curve(audit, dark)
        draw_comparison(comparison['rows'], dark)
        draw_diagram(OVERVIEW, '03-technical-architecture', dark)
        draw_diagram(DATA_FUSION, '04-data-centric-design', dark)
        draw_diagram(ARCHITECTURE, '05-verified-system-paths', dark)
    manifest = {'sourceFiles': [{'path': str(path.relative_to(ROOT)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest()} for path in sources],
                'dataCoverage': family_counts, 'checkedSameQuestionIds': True,
                'modelEvaluation': comparison['rows'],
                'limits': ['One seed; 16 validation and 16 test tasks.', 'RL increment over SFT is zero.',
                           'RL sampling rewards use changing tasks, not a fixed validation curve.',
                           'Complete SFT loss history is not locally available; no SFT loss curve was fabricated.'],
                'files': [str(path.relative_to(HERE)) for path in sorted(FIGURES.iterdir())]}
    (HERE / 'figure-manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'figureFiles': len(manifest['files']), 'sameFrozenIds': True,
                      'optimizerUpdates': 7, 'directory': str(HERE)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
