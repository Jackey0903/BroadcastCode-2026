#!/usr/bin/env python3
"""Render the frozen competition showcase; publish only its explicit public assets.

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
from capture_readme_frames import FRAMES, SOURCE_SHA256

ROOT = Path(__file__).resolve().parents[2]
SHOWCASE_SOURCE = ROOT / 'SHOWCASE.md'
BUILD = ROOT / 'product/build/readme'
REPOSITORY = 'https://github.com/Jackey0903/BroadcastCode-2026/blob/main/'
IMAGE_SOURCE = 'product/broadcast-fx/formal/previews/contact.jpg'
IMAGE_KEY = 'readme-assets/overview.jpg'
IMAGE_ASSETS = {IMAGE_SOURCE: IMAGE_KEY} | {
    'docs/assets/readme-55s/' + name: 'readme-assets/55s-' + name
    for name, _, _ in FRAMES
}
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
            if image_path not in IMAGE_ASSETS:
                raise ValueError('README image is outside the public asset whitelist.')
            key = IMAGE_ASSETS[image_path]
            result.append(f'<a class="frame-link" href="/{key}" target="_blank" rel="noopener" title="查看完整配图" aria-label="查看大图：{html.escape(image_label, quote=True)}">'
                          f'<img src="/{key}" alt="{html.escape(image_label, quote=True)}" loading="lazy" decoding="async" width="1280" height="720"></a>')
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
            value = ' '.join(paragraph)
            picture = re.fullmatch(r'!\[([^\]]*)\]\(([^)]+)\)', value)
            if picture:
                blocks.append('<figure>' + inline(value) + '<figcaption>' +
                              html.escape(picture[1]) + '</figcaption></figure>')
            else:
                blocks.append('<p>' + inline(value) + '</p>')
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
            title_html = inline(title)
            if section:
                title_html = f'<span class="chapter-number">{section[1]}</span><span>{inline(title[section.end():].strip())}</span>'
            blocks.append(f'<h{level}{anchor}>{title_html}</h{level}>')
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
    # Adjacent frames form a comparison row; mobile keeps the reading order.
    grouped, pair = [], []
    for block in blocks + ['']:
        if block.startswith('<figure>'):
            pair.append(block)
            continue
        if pair:
            grouped.append('<div class="visual-pair">' + '\n'.join(pair) + '</div>' if len(pair) > 1 else pair[0])
            pair.clear()
        if block:
            grouped.append(block)
    body = '\n'.join(grouped)
    quick_links = ''.join(f'<a href="#innovation-{number}"><span>{number}</span>{label}</a>'
                          for number, label in [('01', '三层数据融合'), ('02', 'RL 数据球探'),
                                                ('06', '关键回合可视化'), ('11', 'AI 解说'),
                                                ('16', 'AWS 托管协同')]
                          if f'id="innovation-{number}"' in body)
    return '''<!doctype html>
<html lang="zh-CN"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="description" content="GameBuddy · Team02：强化学习数据球探、三层篮球数据融合与关键回合视觉解读。">
<meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'; form-action 'none'">
<title>GameBuddy · Team02 | README</title>
<link rel="icon" href="/readme-assets/55s-recap.jpg" type="image/jpeg">
<style>
:root{color-scheme:dark;--paper:#0d1214;--ink:#e7eceb;--muted:#a9b8b6;--line:#2b383b;--accent:#ff733f;--blue:#8bd7e8}*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:17px/1.9 system-ui,-apple-system,"PingFang SC","Microsoft YaHei",sans-serif}
main{max-width:1080px;margin:auto;padding:46px 30px 88px}.team{color:var(--blue);font-size:13px;font-weight:650;letter-spacing:.08em}.site-nav{display:flex;gap:12px;flex-wrap:wrap;font-size:14px;margin:20px 0 36px}.site-nav a{padding:6px 15px;border:1px solid var(--line);border-radius:6px;text-decoration:none}.site-nav a:first-child{color:#12191b;background:var(--blue);border-color:var(--blue);font-weight:650}
a{color:var(--blue);text-underline-offset:4px}a:hover{color:#fff}a:focus-visible{outline:2px solid var(--accent);outline-offset:5px}h1{font-size:clamp(44px,7vw,76px);letter-spacing:-.04em;line-height:1.12;margin:26px 0 14px}h3{font-size:clamp(17px,2vw,21px);color:#b9d2d7;font-weight:450;margin:0 0 26px}h2{display:flex;gap:18px;align-items:baseline;font-size:25px;line-height:1.55;margin:70px 0 22px;padding-top:28px;border-top:1px solid var(--line);scroll-margin-top:28px}.chapter-number{color:var(--accent);font:500 18px/1.5 ui-monospace,monospace;flex-shrink:0}p,ul{max-width:880px}p{margin:18px 0}strong{color:#fff}em{color:var(--muted);font-size:14px}li{margin:8px 0}code{font-size:.9em}
.quick-links{display:flex;flex-wrap:wrap;gap:9px;margin:0 0 34px}.quick-links a{display:inline-flex;gap:9px;align-items:center;border:1px solid var(--line);padding:6px 12px;border-radius:5px;font-size:13px;text-decoration:none;color:#c7d3d4}.quick-links span{color:var(--accent);font-family:ui-monospace,monospace}.quick-links a:hover{border-color:var(--blue)}
figure{margin:30px 0 28px;border:1px solid var(--line);border-radius:10px;overflow:hidden;background:#151f22;box-shadow:0 18px 38px #0004}.frame-link{display:block;line-height:0}.frame-link img{display:block;width:100%;height:auto;aspect-ratio:16/9;object-fit:contain}.frame-link:hover{outline:1px solid var(--blue);outline-offset:-1px}figcaption{padding:13px 18px;font-size:14px;line-height:1.75;color:#c4d2d3}.visual-pair{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:18px;margin:30px 0}.visual-pair figure{margin:0;box-shadow:none}.visual-pair figcaption{font-size:13px}.image-note{font-size:13px;color:var(--muted);margin-top:0}footer{margin-top:60px;padding-top:24px;border-top:1px solid var(--line);font-size:13px;color:var(--muted)}
@media(max-width:700px){main{padding:28px 18px 56px}body{font-size:16px}h2{font-size:21px;gap:12px;margin-top:52px}.visual-pair{grid-template-columns:1fr;gap:18px}figcaption{padding:11px 14px}.quick-links{gap:7px}.quick-links a{font-size:12px;padding:5px 9px}}@media(prefers-reduced-motion:reduce){html{scroll-behavior:auto}}
</style></head><body><main>
<div class="team">NBA × AWS BroadcastCode · TEAM 02</div>
<nav class="site-nav" aria-label="作品导航"><a href="/product/">打开 GameBuddy 作品 ↗</a><a href="/readme.md" download="GameBuddy-Team02-README.md">下载 README</a></nav>
''' + ('<nav class="quick-links" aria-label="创新点快捷阅读">' + quick_links + '</nav>' if quick_links else '') + body + '''
<p class="image-note">配图直接截自55.055秒确定版成片，点击画面可查看大图。</p>
<footer>GameBuddy · Team02。源码资料链接指向团队参赛仓库，需相应仓库访问权限。</footer>
</main></body></html>
'''


def build_assets(source):
    page = render_readme(source).encode('utf-8')
    assets = [{'key': key, 'body': page, 'contentType': 'text/html; charset=utf-8'} for key in PAGE_KEYS]
    assets.append({'key': 'readme.md', 'body': source.encode('utf-8'), 'contentType': 'text/markdown; charset=utf-8'})
    capture_manifest = None
    for image_source, key in IMAGE_ASSETS.items():
        if f'/{key}"' not in page.decode('utf-8'):
            continue
        image_body = (ROOT / image_source).read_bytes()
        if image_source.startswith('docs/assets/readme-55s/'):
            capture_manifest = capture_manifest or read_capture_manifest()
            capture = next((item for item in capture_manifest['captures'] if item['path'] == image_source), None)
            if capture_manifest['sourceSha256'] != SOURCE_SHA256 or not capture or capture['sha256'] != digest(image_body):
                raise ValueError('README picture differs from its frozen movie-frame manifest.')
        assets.append({'key': key, 'body': image_body, 'contentType': 'image/jpeg'})
    return assets


def read_capture_manifest():
    return json.loads((ROOT / 'docs/assets/readme-55s/manifest.json').read_text(encoding='utf-8'))


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
    source = SHOWCASE_SOURCE.read_text(encoding='utf-8')
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
              'source': 'SHOWCASE.md', 'sourceSha256': digest(source.encode('utf-8')),
              'bucket': outputs['Bucket'], 'distribution': outputs['Distribution'],
              'invalidationId': invalidation['Id'], 'assets': manifest, 'publicChecks': checks,
              'illustrations': read_capture_manifest(),
              'scope': 'Static README and explicit confirmed-movie frames only; existing application and media are unchanged.'}
    evidence = ROOT / 'product/evidence/readme-publication-20261010.json'
    evidence.write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(json.dumps({'website': report['website'], 'verifiedAssets': len(checks), 'evidence': str(evidence)}, ensure_ascii=False))


if __name__ == '__main__':
    main()
