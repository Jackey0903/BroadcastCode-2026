#!/usr/bin/env python3
"""Independently verify a completed product render; optionally select it for the showcase.

This script never starts cloud work and never claims browser or visual verification.
"""
import argparse
import datetime
import hashlib
import json
from pathlib import Path
import subprocess
import urllib.request
from deployment import load_outputs

ROOT = Path(__file__).resolve().parents[2]
HERE = ROOT / 'product'
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('job_id')
parser.add_argument('--promote', action='store_true')
args=parser.parse_args()
if len(args.job_id)!=32 or any(c not in '0123456789abcdef' for c in args.job_id):
    raise SystemExit('Invalid job id')
outputs=load_outputs()
base=outputs['Website']
with urllib.request.urlopen(base+'/api/jobs/'+args.job_id,timeout=30) as response:
    job=json.load(response)
assert job['status']=='completed', job
analysis=job['analysis']
assert job.get('mode')=='story'
assert analysis['modelId']=='global.anthropic.claude-sonnet-4-6'
assert analysis['usage']['inputTokens']>0
assert analysis['preservesSourceTimeline'] is True
assert analysis['runtimeArn']==outputs['RuntimeArn']
video=analysis['outputVideo']
target=HERE/'build/verified'/args.job_id
target.mkdir(parents=True,exist_ok=True)
local=target/'enhanced.mp4'
with urllib.request.urlopen(job['videoUrl'],timeout=60) as response, local.open('wb') as dest:
    assert response.status==200 and 'video/mp4' in response.headers['Content-Type']
    while True:
        chunk=response.read(1024*1024)
        if not chunk:break
        dest.write(chunk)
sha=hashlib.sha256(local.read_bytes()).hexdigest()
assert sha==video['sha256']
probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height,codec_name','-of','json',str(local)]))
v=next(x for x in probe['streams'] if x['codec_type']=='video')
assert v['width']==1280 and v['height']==900 and v['codec_name']=='h264'
assert any(x['codec_type']=='audio' for x in probe['streams'])
duration=float(probe['format']['duration'])
assert abs(duration-analysis['sourceVideo']['duration_ms']/1000)<.25
with urllib.request.urlopen(urllib.request.Request(job['videoUrl'],headers={'Range':'bytes=0-1023'}),timeout=30) as response:
    assert response.status==206 and len(response.read())==1024
for seconds in (3,15,18):
    subprocess.run(['ffmpeg','-v','error','-y','-ss',str(seconds),'-i',str(local),'-frames:v','1',str(target/f'{seconds}s.jpg')],check=True)
report={'verifiedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'jobId':args.job_id,
    'sample':job['sample'],'mode':job['mode'],'videoUrl':job['videoUrl'],'analysisUrl':job['analysisUrl'],
    'outputSha256':sha,'bytes':local.stat().st_size,'durationSeconds':duration,'width':1280,'height':900,
    'audioPresent':True,'rangeStatus':206,'modelId':analysis['modelId'],'usage':analysis['usage'],
    'elapsedSeconds':job.get('elapsedSeconds'),'browserPlaybackVerified':False,'burnedOverlayVisuallyVerified':False,
    'analysis':analysis}
(HERE/'evidence'/f'run-{args.job_id}.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
if args.promote:
    path=HERE/'data/stories.json'
    stories=json.loads(path.read_text())
    story=next(s for s in stories['stories'] if s['id']==job['sample'])
    story.update({'enhancedVideo':job['videoUrl'],'analysisUrl':job['analysisUrl'],
                  'showcaseJobId':args.job_id,'showcaseOutputSha256':sha})
    path.write_text(json.dumps(stories,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({'verified':True,'jobId':args.job_id,'durationSeconds':duration,
                  'localVideo':str(local),'promoted':args.promote},ensure_ascii=False))
