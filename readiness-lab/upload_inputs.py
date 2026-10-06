"""Upload the two previously downloaded official practice clips to this lab only."""
import hashlib,json,mimetypes
from pathlib import Path
import boto3

ROOT=Path(__file__).resolve().parents[1]
HERE=Path(__file__).resolve().parent
outputs=json.loads((HERE/'outputs.json').read_text())['BroadcastCodeTeam02Readiness20261006']
session=boto3.Session(profile_name='nba',region_name='us-east-1')
identity=session.client('sts').get_caller_identity()
assert identity['Account']=='962768510637' and 'NBAHackathonParticipantRole' in identity['Arn']
bucket=outputs['Bucket'];s3=session.client('s3')
manifest={}
for sample,name in [('flagg','训练_弗拉格2月1日.mp4'),('amen','训练_阿门1月4日 .mp4')]:
    source=ROOT/'data/reference/train_video/train_video'/name
    metadata=json.loads((ROOT/'data/reference/train-video-metadata.json').read_text())[str(source.relative_to(ROOT))]
    video=next(stream for stream in metadata['streams'] if stream['codec_type']=='video')
    sha=hashlib.sha256(source.read_bytes()).hexdigest()
    key=f'samples/{sample}.mp4'
    s3.upload_file(str(source),bucket,key,ExtraArgs={'ContentType':'video/mp4','Metadata':{'sha256':sha}})
    frames=[]
    for seconds in (3,6,15,18):
        image=ROOT/f'data/reference/frames/{sample}-{seconds:02d}s.jpg'
        image_key=f'frames/{sample}-{seconds:02d}s.jpg'
        s3.upload_file(str(image),bucket,image_key,ExtraArgs={'ContentType':'image/jpeg'})
        frames.append({'timestamp_ms':seconds*1000,'s3_uri':f's3://{bucket}/{image_key}','format':'jpeg'})
    manifest[sample]={'video':{'id':sample,'name':name,'s3_uri':f's3://{bucket}/{key}',
        'duration_ms':float(metadata['format']['duration'])*1000,'sha256':sha,
        'width':video['width'],'height':video['height']},'frames':frames}
s3.put_object(Bucket=bucket,Key='config/samples.json',Body=json.dumps(manifest,ensure_ascii=False).encode(),ContentType='application/json')
for source in sorted((HERE/'web').iterdir()):
    if source.suffix not in ('.html','.css','.js'):continue
    s3.upload_file(str(source),bucket,source.name,ExtraArgs={'ContentType':mimetypes.guess_type(source.name)[0] or 'application/octet-stream','CacheControl':'no-cache'})
(HERE/'build/upload-manifest.json').write_text(json.dumps(manifest,ensure_ascii=False,indent=2))
print(json.dumps({'uploaded_samples':list(manifest),'website':outputs['Website']},ensure_ascii=False))
