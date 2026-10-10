"""Render a hook, action replay, metric reveal, and return to the finish.

No AWS requests. Official values come from the existing verified story manifest.
The appended edit has its own time map; it does not preserve a single source clock.
"""
import argparse, hashlib, json, shutil, subprocess
from pathlib import Path
from serve import ROOT, source_file

def run(command, cwd):
    subprocess.run(command, cwd=cwd, check=True)

def render(sample, ffmpeg, font):
    story = next(s for s in json.loads((ROOT / 'product/data/stories.json').read_text(encoding='utf-8'))['stories'] if s['sample'] == sample)
    source = source_file(sample)
    if not source: raise ValueError('Restore the original practice video first.')
    with source.open('rb') as stream: source_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    if source_hash != story['sourceVideoSha256']: raise ValueError('Source hash mismatch.')
    if not story['officialEvent']['verified'] or story['shotMetric']['rawValue'] != story['officialEvent']['expectedFg']:
        raise ValueError('The corresponding official shot is not verified.')
    out = ROOT / f'product/build/mlb-rhythm/{sample}'; out.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(font, out / 'font.ttc')
    start, end, freeze = 15.4, 17.8, 16.5
    hook_end, hold = 17.9, 4.0
    # The improved Mavericks cut has a shorter replay, then longer explanation.
    rate = .5
    duration = story['durationSeconds']
    captions = [
        ('01  这一球，怎么进的？', '突破，起跳，挑篮命中。', '先看终结 · 比赛原声'),
        ('02  回到他起跳的那一刻', '跟着球，看他如何接近篮筐。', '0.5× 慢放 · 突破 → 起跳 → 挑篮'),
        ('03  进了。但这次机会有多大？', f"本次出手 xFG  {story['shotMetric']['display']}    /    实际结果：命中", 'NBA 官方单次出手 · 事件 ' + str(story['officialEvent']['eventId'])),
        ('04  再看一次，这次带着答案', '一次突破挑篮，完成这次进攻。', f"官方 xFG {story['shotMetric']['display']} · 模型参考不等于个人命中保证或胜率。"),
    ]
    files = []
    for index, lines in enumerate(captions):
        for n, text in enumerate(lines): (out / f'text-{index}-{n}.txt').write_text(text, encoding='utf-8')
        base = 'scale=1280:720,pad=1280:900:0:0:color=0x10100e,setsar=1,fps=30'
        for n, (y, size, color) in enumerate([(745, 27, '0xff974f'), (794, 30, '0xf3f0e8'), (850, 20, '0xa5a397')]):
            if index == 1 and n == 1:
                boundaries = [(0, (16.5-start)/rate, lines[1]), ((16.5-start)/rate, (end-start)/rate, '他起跳挑篮，正面防守人双臂举起。')]
                for part, (first, last, text) in enumerate(boundaries):
                    (out / f'replay-{part}.txt').write_text(text, encoding='utf-8')
                    base += f",drawtext=fontfile=font.ttc:textfile=replay-{part}.txt:expansion=none:x=36:y={y}:fontsize={size}:fontcolor={color}:enable='gte(t,{first:.6f})*lt(t,{last:.6f})'"
            else:
                base += f",drawtext=fontfile=font.ttc:textfile=text-{index}-{n}.txt:expansion=none:x=36:y={y}:fontsize={size}:fontcolor={color}"
        output = f'part-{index}.mp4'
        command = [ffmpeg, '-hide_banner', '-loglevel', 'error', '-y']
        if index == 0:
            command += ['-ss', str(start), '-i', str(source), '-vf', base, '-map', '0:v:0', '-map', '0:a:0', '-af', 'aresample=48000', '-t', str(hook_end-start)]
        elif index == 1:
            command += ['-ss', str(start), '-t', str(end-start), '-i', str(source), '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-vf', f'setpts=(PTS-STARTPTS)/{rate},' + base, '-map', '0:v:0', '-map', '1:a:0', '-t', str((end-start)/rate)]
        elif index == 2:
            still = out / f'still-{index}.jpg'
            run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-ss', str(freeze), '-i', str(source), '-frames:v', '1', str(still)], out)
            command += ['-loop', '1', '-i', str(still), '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-vf', base, '-map', '0:v:0', '-map', '1:a:0', '-t', str(hold)]
        else:
            command += ['-ss', str(start), '-t', str(19.5-start), '-i', str(source), '-f', 'lavfi', '-i', 'anullsrc=r=48000:cl=stereo', '-vf', base, '-map', '0:v:0', '-map', '1:a:0', '-t', str(19.5-start)]
        command += ['-c:v', 'libx264', '-preset', 'fast', '-crf', '20', '-pix_fmt', 'yuv420p', '-c:a', 'aac', '-b:a', '128k', '-ar', '48000', '-ac', '2', output]
        run(command, out); files.append(output)
    (out / 'concat.txt').write_text(''.join(f"file '{file}'\n" for file in files), encoding='utf-8')
    run([ffmpeg, '-hide_banner', '-loglevel', 'error', '-y', '-f', 'concat', '-safe', '0', '-i', 'concat.txt', '-c', 'copy', '-movflags', '+faststart', 'enhanced.mp4'], out)
    with (out / 'enhanced.mp4').open('rb') as stream: output_hash = hashlib.file_digest(stream, 'sha256').hexdigest()
    evidence = {'sample': sample, 'sourceSha256': source_hash, 'outputSha256': output_hash,
                'officialEvent': story['officialEvent'], 'metric': story['shotMetric'],
                'sourceTimeMap': [{'stage': 'hook', 'sourceStart': start, 'sourceEnd': hook_end, 'rate': 1},
                    {'stage': 'replay', 'sourceStart': start, 'sourceEnd': end, 'rate': rate},
                    {'stage': 'metric', 'sourceFrame': freeze, 'duration': hold},
                    {'stage': 'explanation', 'sourceStart': start, 'sourceEnd': 19.5, 'rate': 1}],
                'metricAppearsAfterSeconds': hook_end-start + (end-start)/rate,
                'newAgentInvocation': False, 'preservesSourceTimeline': False,
                'provenance': 'Local deterministic Mavericks story edit; complete source remains available separately.'}
    (out / 'evidence.json').write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'video': str(out / 'enhanced.mp4'), 'metricAfterSeconds': evidence['metricAppearsAfterSeconds']}, ensure_ascii=False))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--sample', choices=['flagg'], default='flagg')
    parser.add_argument('--ffmpeg', required=True); parser.add_argument('--font', required=True)
    args = parser.parse_args(); render(args.sample, str(Path(args.ffmpeg).resolve()), Path(args.font).resolve())
