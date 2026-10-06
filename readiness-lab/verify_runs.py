"""Read and independently verify completed browser runs. Does not start jobs."""
import argparse,datetime,hashlib,json,subprocess,urllib.request,urllib.error
from pathlib import Path

HERE=Path(__file__).resolve().parent
parser=argparse.ArgumentParser();parser.add_argument('jobs',nargs='+');args=parser.parse_args()
outputs=json.loads((HERE/'outputs.json').read_text())['BroadcastCodeTeam02Readiness20261006']
base=outputs['Website'];target=HERE/'build/verified';target.mkdir(parents=True,exist_ok=True)
visual_path=HERE/'browser-observations.json'
visual_runs={item['jobId']:item for item in json.loads(visual_path.read_text()).get('runs',[])} if visual_path.exists() else {}
def request(path,body=None):
    raw=json.dumps(body,separators=(',',':')).encode() if body is not None else None
    headers={'content-type':'application/json'} if raw else {}
    if raw:headers['x-amz-content-sha256']=hashlib.sha256(raw).hexdigest()
    return urllib.request.urlopen(urllib.request.Request(base+path,data=raw,headers=headers),timeout=30)
report={'verifiedAt':datetime.datetime.now(datetime.timezone.utc).isoformat(),'website':base,
    'stack':'BroadcastCodeTeam02Readiness20261006','deployment':outputs,'httpChecks':[],'runs':[]}
with request('/api/status') as response:
    status=json.loads(response.read());assert response.status==200 and status['status']=='ready'
report['httpChecks'].append({'path':'/api/status','status':200,'samples':[s['id'] for s in status['samples']]})
for path,body,wanted in [('/api/jobs/invalid',None,400),('/api/jobs/'+'0'*32,None,404),('/api/jobs',{'sample':'external-url'},400)]:
    try:
        response=request(path,body);code=response.status
    except urllib.error.HTTPError as error:code=error.code
    assert code==wanted,(path,code)
    report['httpChecks'].append({'path':path,'status':code,'expected':wanted})
for job in args.jobs:
    with request('/api/jobs/'+job) as response:result=json.loads(response.read())
    assert result['status']=='completed',result
    analysis=result['analysis'];media=analysis['outputVideo']
    assert analysis['inferenceSource']=='bedrock_converse' and analysis['usage']['inputTokens']>0
    assert analysis['modelId']=='global.anthropic.claude-sonnet-4-6'
    assert result['runtimeArn']==outputs['RuntimeArn'] and result['preservesSourceTimeline']
    assert len(result['evidence'])==4
    video=target/(result['sample']+'.mp4')
    with urllib.request.urlopen(result['videoUrl'],timeout=60) as response,video.open('wb') as destination:
        assert response.status==200 and 'video/mp4' in response.headers['Content-Type']
        while True:
            data=response.read(1024*1024)
            if not data:break
            destination.write(data)
    sha=hashlib.sha256(video.read_bytes()).hexdigest();assert sha==media['sha256']
    probe=json.loads(subprocess.check_output(['ffprobe','-v','error','-show_entries','format=duration:stream=codec_type,width,height,codec_name','-of','json',str(video)]))
    stream=next(s for s in probe['streams'] if s['codec_type']=='video')
    duration=float(probe['format']['duration'])
    assert stream['width']==1280 and stream['height']==720 and stream['codec_name']=='h264'
    assert any(s['codec_type']=='audio' for s in probe['streams'])
    assert abs(duration-analysis['sourceVideo']['duration_ms']/1000)<.25
    with urllib.request.urlopen(urllib.request.Request(result['videoUrl'],headers={'Range':'bytes=0-1023'}),timeout=30) as response:
        assert response.status==206 and len(response.read())==1024
    subprocess.run(['ffmpeg','-v','error','-y','-ss','3','-i',str(video),'-frames:v','1',str(target/(result['sample']+'.jpg'))],check=True)
    report['runs'].append({'jobId':job,'sample':result['sample'],'status':'completed',
        'videoUrl':result['videoUrl'],'analysisUrl':result['analysisUrl'],'runtimeArn':result['runtimeArn'],
        'modelId':analysis['modelId'],'usage':analysis['usage'],'summary':analysis['summary'],'subtitle':analysis['subtitle'],
        'durationSeconds':duration,'sourceDurationSeconds':analysis['sourceVideo']['duration_ms']/1000,
        'outputSha256':sha,'outputBytes':video.stat().st_size,'videoCodec':stream['codec_name'],
        'width':stream['width'],'height':stream['height'],'audioPresent':True,'rangeStatus':206,
        'elapsedSeconds':result['elapsedSeconds'],'evidence':result['evidence'],
        'sourceFrameTimesMs':analysis['source_frame_times_ms'],
        'browserPlaybackVerified':False,'burnedCaptionVisuallyVerified':False})
    visual=visual_runs.get(job,{})
    if visual.get('outputSha256')==sha:
        for field in ('browserPlaybackVerified','burnedCaptionVisuallyVerified','startedViaBrowserButton','browserEndTimeSeconds','pageRefreshRestoredJob'):
            if field in visual:report['runs'][-1][field]=visual[field]
        report['runs'][-1]['visualEvidence']='browser-observations.json'
    print(json.dumps({'sample':result['sample'],'complete':True,'duration':duration,'model':analysis['modelId'],'range':206},ensure_ascii=False))
(HERE/'e2e-results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('Saved evidence to e2e-results.json; visual checks require recorded observations matching the output SHA-256.')
