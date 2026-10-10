#!/usr/bin/env python3
"""Publish only hash-verified formal media and the existing watch asset allowlist.

Does not rewrite old Agent job records, official evidence or the creator API.
The public narration proof includes provider/model/timing, never credentials.
"""
from datetime import datetime, timezone
import argparse
import hashlib
import json
import io
import mimetypes
from pathlib import Path

from deployment import load_deployment, load_outputs, validate_identity
from serve import Catalog, ROOT
from watch_assets import WATCH_PUBLIC_FILES


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--media-only',action='store_true',help='Replace final media/catalog/root after the watch assets have already been published')
    parser.add_argument('--web-only',action='store_true',help='Publish player assets, root and verified catalog without uploading video again')
    args=parser.parse_args()
    import boto3
    from boto3.s3.transfer import TransferConfig
    from botocore.config import Config
    catalog=Catalog(ROOT)
    if catalog.issues:raise ValueError('Formal catalog verification failed')
    story=catalog.manifest['stories'][0]
    production=story['production']
    if not story.get('enhancedVideo') or not production.get('aiNarrationUsed'):
        raise ValueError('Verified narrated formal movie is required')
    files={f'product/watch/{name}':ROOT/'product/watch'/name for name in WATCH_PUBLIC_FILES}
    files['product/watch/index.html']=ROOT/'product/watch/index.html'
    for uri in ('/product/media/formal/source.mp4','/product/media/formal/enhanced.mp4'):
        files[uri[1:]]=catalog.files[uri]
    objects={key:(path.read_bytes(),mimetypes.guess_type(key)[0] or 'application/octet-stream')
             for key,path in files.items()}
    objects['product/watch/']=(objects['product/watch/index.html'][0],'text/html; charset=utf-8')
    # Root serves the same glass player. The base resolves its relative assets;
    # the original pixel creator remains intact under /product/.
    html=objects['product/watch/index.html'][0].decode()
    root_html=html.replace('<head>', '<head>\n    <base href="/product/watch/">',1)
    objects['index.html']=(root_html.encode(),'text/html; charset=utf-8')
    def add_json(key,value):objects[key]=(json.dumps(value,ensure_ascii=False,indent=2).encode(),'application/json; charset=utf-8')
    manifest={'version':'gamebuddy-formal-narrated-v1','purpose':'正式素材与AI双人解说','stories':[story]}
    add_json('product/watch/data/stories.json',manifest)
    add_json('product/media/formal/manifest.json',production)
    if args.media_only:
        keys={'product/media/formal/enhanced.mp4','product/media/formal/manifest.json',
              'product/watch/data/stories.json','index.html'}
        objects={key:value for key,value in objects.items() if key in keys}
    if args.web_only:
        objects={key:value for key,value in objects.items() if not key.endswith('.mp4')}
    # Commit the public root after every dependent asset/catalog is ready.
    root=objects.pop('index.html',None)
    if root:objects['index.html']=root
    target=load_deployment();outputs=load_outputs(target=target)
    session=boto3.Session(profile_name='nba',region_name='us-east-1')
    sdk=Config(connect_timeout=8,read_timeout=120,retries={'total_max_attempts':2})
    validate_identity(session.client('sts',config=sdk).get_caller_identity(),target)
    s3=session.client('s3',config=sdk);uploaded=[]
    for key,(data,content_type) in objects.items():
        digest=hashlib.sha256(data).hexdigest()
        extra={'ContentType':content_type,'ExpectedBucketOwner':target['account'],
               'ServerSideEncryption':'AES256','CacheControl':'no-store' if not key.endswith('.mp4') else 'public, max-age=300',
               'Metadata':{'sha256':digest}}
        if len(data)>8*1024*1024:
            s3.upload_fileobj(io.BytesIO(data),outputs['Bucket'],key,ExtraArgs=extra,
                Config=TransferConfig(multipart_threshold=8*1024*1024,multipart_chunksize=8*1024*1024,max_concurrency=4))
        else:
            s3.put_object(Bucket=outputs['Bucket'],Key=key,Body=data,**extra)
        head=s3.head_object(Bucket=outputs['Bucket'],Key=key,ExpectedBucketOwner=target['account'])
        if head['ContentLength']!=len(data) or head['Metadata'].get('sha256')!=digest:
            raise ValueError('Published object identity differs')
        uploaded.append({'key':key,'sha256':digest,'sizeBytes':len(data)})
        print(json.dumps({'published':key,'bytes':len(data)}),flush=True)
    result={'publishedAt':datetime.now(timezone.utc).isoformat(),'account':target['account'],
            'website':outputs['Website'],'bucket':outputs['Bucket'],'objects':uploaded,
            'watchUrl':outputs['Website']+'/product/watch/index.html?story=formal&version=enhanced',
            'outputSha256':production['outputSha256'],'sourceSha256':production['sourceSha256'],
            'aiNarrationUsed':True,'agentCoreNarration':production.get('narration',{}).get('agentCore',{}).get('invoked') is True,
            'rootUrl':outputs['Website'],'cloudFrontPlaybackVerified':False}
    evidence_name='watch-prd-v2-publication-20261010.json' if args.web_only else 'formal-narrated-publication-20261010.json'
    (ROOT/'product/evidence'/evidence_name).write_text(json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({'watchUrl':result['watchUrl'],'publishedObjects':len(uploaded)},ensure_ascii=False),flush=True)


if __name__=='__main__':main()
