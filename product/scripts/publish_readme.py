#!/usr/bin/env python3
"""Render the root innovation README; publish only its explicit public assets.

Preview: python3 product/scripts/publish_readme.py
Publish: readiness-lab/.venv/bin/python product/scripts/publish_readme.py --publish

Extensionless HTML objects work with the existing CloudFront S3 origin. No
infrastructure deployment, model invocation or broad website upload is required.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import re
from urllib.parse import quote, urlsplit
from urllib.request import Request, urlopen

from deployment import load_deployment, load_outputs, validate_identity

ROOT = Path(__file__).resolve().parents[2]
BUILD = ROOT / 'product/build/readme'
REPOSITORY = 'https://github.com/Jackey0903/BroadcastCode-2026/blob/main/'
IMAGE_SOURCE = 'product/broadcast-fx/formal/previews/contact.jpg'
IMAGE_KEY = 'readme-assets/overview.jpg'
PAGE_KEYS = ('readme', 'product/readme', 'readme/index.html', 'product/readme/index.html')
TOKEN = re.compile(r'!\[([^\]]*)\]\(([^)]+)\)|\[([^\]]+)\]\(([^)]+)\)|'
                   r'\*\*(.+?)\*\*|\*([^*]+)\*|`([^`]+)`')


def safe_link(value):
    """Keep HTTPS links; resolve repository references without publishing files."""
    parsed = urlsplit(value)
    if parsed.scheme:
        if parsed.scheme != 'https' or not parsed.hostname or parsed.username or parsed.password:
            raise ValueError('README links must use HTTPS without credentials.')
        return value
    if parsed.netloc or value.startswith('/') or '..' in Path(parsed.path).parts:
        raise ValueError('README references must stay within the repository.')
    if parsed.path and not (ROOT / parsed.path).is_file():
        raise ValueError('README references a missing source file.')
    if not parsed.path:
        return value
    return REPOSITORY + quote(parsed.path, safe='/') + ('#' + quote(parsed.fragment) if parsed.fragment else '')


def inline(value):
    result = []
    offset = 0
    for match in TOKEN.finditer(value):
        result.append(html.escape(value[offset:match.start()]))
        image_label, image_path, label, target, strong, emphasis, code = match.groups()
        if image_path is not None:
            if image_path != IMAGE_SOURCE:
                raise ValueError('README image is outside the public asset whitelist.')
            result.append(f'<img src="/{IMAGE_KEY}" alt="{html.escape(image_label, quote=True)}" loading="lazy">')
        elif target is not None:
            result.append(f'<a href="{html.escape(safe_link(target), quote=True)}">{html.escape(label)}</a>')
        elif strong is not None:
            result.append(f'<strong>{html.escape(strong)}</strong>')
        elif emphasis is not None:
            result.append(f'<em>{html.escape(emphasis)}</em>')
        else:
            result.append(f'<code>{html.escape(code)}</code>')
        offset = match.end()
    result.append(html.escape(value[offset:]))
    return ''.join(result)


def render_readme(source):
    """Support this README's headings, paragraphs, lists and inline Markdown.

    Repository handoff notices before the product title are intentionally omitted
    from the visitor page; the downloadable Markdown retains the complete source.
    """
    match = re.search(r'^# GameBuddy\s*$', source, re.M)
    if not match:
        raise ValueError('The GameBuddy product title is missing.')
    content = source[match.start():]
    blocks, paragraph, list_open = [], [], False

    def flush():
        if paragraph:
            blocks.append('<p>' + inline(' '.join(paragraph)) + '</p>')
            paragraph.clear()

    for line in content.splitlines():
        line = line.strip()
        heading = re.fullmatch(r'(#{1,6})\s+(.+)', line)
        if not line or heading or line.startswith('- '):
            flush()
        if list_open and not line.startswith('- '):
            blocks.append('</ul>')
            list_open = False
        if not line:
            continue
        if heading:
            level = len(heading[1])
            title = heading[2]
            section = re.match(r'(\d{2})\s*·', title)
            anchor = f' id="innovation-{section[1]}"' if section else ''
            blocks.append(f'<h{level}{anchor}>{inline(title)}</h{level}>')
        elif line.startswith('- '):
            if not list_open:
                blocks.append('<ul>')
                list_open = True
            blocks.append('<li>' + inline(line[2:]) + '</li>')
        elif line.startswith(('```', '>', '|')):
            raise ValueError('Unsupported README block; update the renderer before publication.')
        else:
            paragraph.append(line)
    flush()
    if list_open:
        blocks.append('</ul>')
    body = '\n'.join(blocks)
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="GameBuddy · Team02：强化学习数据球探、三层篮球数据融合与关键回合视觉解读。">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'">
<title>GameBuddy · Team02 | README</title>
<style>
:root{color-scheme:dark}*{box-sizing:border-box}body{margin:0;background:#101416;color:#edf0ee;font:17px/1.85 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:960px;margin:auto;padding:40px 24px 80px}.team{color:#91cfa6;font-size:14px;font-weight:650;letter-spacing:.04em}
nav{display:flex;gap:24px;flex-wrap:wrap;font-size:14px;margin:12px 0 36px}a{color:#9addb1;text-underline-offset:4px}h1{font-size:clamp(38px,6vw,60px);line-height:1.2;margin:20px 0}h2{font-size:25px;line-height:1.5;margin:56px 0 18px;padding-top:24px;border-top:1px solid #344139}h3{font-size:20px;color:#bedbc9;font-weight:500}p{margin:18px 0}strong{color:#fff}em{color:#b6c0ba;font-size:15px}li{margin:7px 0}img{display:block;width:100%;height:auto;margin:28px 0;border:1px solid #344139;border-radius:8px}code{font-size:.9em}footer{margin-top:48px;font-size:14px;color:#b6c0ba}
@media(max-width:600px){main{padding:28px 18px 56px}body{font-size:16px}h2{font-size:22px}}
</style></head><body><main>
<div class="team">NBA × AWS BroadcastCode · TEAM 02</div>
<nav aria-label="作品导航"><a href="/product/">打开 GameBuddy 作品</a><a href="/readme.md" download="GameBuddy-Team02-README.md">下载 README</a></nav>
''' + body + '''
<footer>GameBuddy · Team02。源码资料链接指向团队参赛仓库，需相应仓库访问权限。</footer>
</main></body></html>
'''


def build_assets(source):
    page = render_readme(source).encode('utf-8')
    assets = [{'key': key, 'body': page, 'contentType': 'text/html; charset=utf-8'} for key in PAGE_KEYS]
    assets.append({'key': 'readme.md', 'body': source.encode('utf-8'), 'contentType': 'text/markdown; charset=utf-8'})
    if f'/{IMAGE_KEY}' in page.decode('utf-8'):
        assets.append({'key': IMAGE_KEY, 'body': (ROOT / IMAGE_SOURCE).read_bytes(), 'contentType': 'image/jpeg'})
    return assets


def digest(body):
    return hashlib.sha256(body).hexdigest()


def verify_public(website, assets):
    checks = []
    for asset in assets:
        url = website.rstrip('/') + '/' + asset['key']
        request = Request(url, headers={'User-Agent': 'GameBuddy-Team02-README-verifier/1.0'})
        with urlopen(request, timeout=30) as response:
            body = response.read()
            actual_type = response.headers.get_content_type()
            expected_type = asset['contentType'].split(';')[0]
            if response.status != 200 or digest(body) != digest(asset['body']) or actual_type != expected_type:
                raise ValueError('Public README response does not match the published asset.')
            checks.append({'url': url, 'httpStatus': response.status, 'contentType': actual_type,
                           'sha256': digest(body), 'bytes': len(body)})
    return checks


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--publish', action='store_true', help='Upload the README whitelist to the verified formal account.')
    args = parser.parse_args()
    target = load_deployment()
    outputs = load_outputs(target=target)
    source = (ROOT / 'README.md').read_text(encoding='utf-8')
    assets = build_assets(source)
    BUILD.mkdir(parents=True, exist_ok=True)
    (BUILD / 'index.html').write_bytes(assets[0]['body'])
    manifest = [{k: v for k, v in asset.items() if k != 'body'} | {'sha256': digest(asset['body']), 'bytes': len(asset['body'])} for asset in assets]
    (BUILD / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    if not args.publish:
        print(json.dumps({'preview': str(BUILD / 'index.html'), 'website': outputs['Website'] + '/readme', 'assets': manifest}, ensure_ascii=False, indent=2))
        return

    import boto3
    from botocore.config import Config
    session = boto3.Session(profile_name=target['profile'], region_name=target['region'])
    config = Config(connect_timeout=10, read_timeout=30, retries={'mode': 'standard', 'total_max_attempts': 2})
    validate_identity(session.client('sts', config=config).get_caller_identity(), target)
    s3 = session.client('s3', config=config)
    # Ownership is checked before mutation and for every individual object.
    s3.head_bucket(Bucket=outputs['Bucket'], ExpectedBucketOwner=target['account'])
    cloudfront = session.client('cloudfront', config=config)
    distribution = cloudfront.get_distribution(Id=outputs['Distribution'])['Distribution']
    if distribution['ARN'].split(':')[4] != target['account'] or distribution['DomainName'] != urlsplit(outputs['Website']).hostname:
        raise ValueError('CloudFront distribution does not match the verified product target.')
    for asset in assets:
        checksum = base64.b64encode(hashlib.sha256(asset['body']).digest()).decode('ascii')
        s3.put_object(Bucket=outputs['Bucket'], Key=asset['key'], Body=asset['body'],
                      ContentType=asset['contentType'], CacheControl='no-store, max-age=0',
                      ServerSideEncryption='AES256', ChecksumSHA256=checksum,
                      Metadata={'sha256': digest(asset['body'])}, ExpectedBucketOwner=target['account'])
        print('Published ' + asset['key'], flush=True)
    invalidation = cloudfront.create_invalidation(DistributionId=outputs['Distribution'], InvalidationBatch={
        'Paths': {'Quantity': len(assets), 'Items': ['/' + asset['key'] for asset in assets]},
        'CallerReference': 'team02-readme-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%f')})['Invalidation']
    checks = verify_public(outputs['Website'], assets)
    report = {'publishedAt': datetime.now(timezone.utc).isoformat(), 'team': '02', 'product': 'GameBuddy',
              'account': target['account'], 'website': outputs['Website'] + '/readme',
              'source': 'README.md', 'sourceSha256': digest(source.encode('utf-8')),
              'bucket': outputs['Bucket'], 'distribution': outputs['Distribution'],
              'invalidationId': invalidation['Id'], 'assets': manifest, 'publicChecks': checks,
              'scope': 'Static README and explicit overview image only; existing application and media are unchanged.'}
    evidence = ROOT / 'product/evidence/readme-publication-20261010.json'
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'website': report['website'], 'verifiedAssets': len(checks), 'evidence': str(evidence)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
