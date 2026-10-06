"""Prepare local deployment assets. No cloud writes, no CDK bootstrap."""
import hashlib,json,shutil,subprocess,tarfile,urllib.request
from pathlib import Path
import sys

HERE=Path(__file__).resolve().parent
build=HERE/'build';build.mkdir(exist_ok=True)
def run(*args):subprocess.run(args,cwd=HERE,check=True)
run(sys.executable,str(HERE/'agent/build_package.py'),str(build/'agent.zip'))
worker=build/'worker';worker.mkdir(exist_ok=True)
run(sys.executable,'-m','pip','install','--target',str(worker),'boto3==1.43.108','--upgrade')
shutil.copyfile(HERE/'worker/handler.py',worker/'handler.py')
tool_sources=[
    ('@ffmpeg-installer/linux-x64@4.1.0','ffmpeg-installer-linux-x64-4.1.0.tgz','package/ffmpeg','bin/ffmpeg'),
    ('ffprobe-static@3.1.0','ffprobe-static-3.1.0.tgz','package/bin/linux/x64/ffprobe','bin/ffprobe'),
]
for package,archive,member,destination in tool_sources:
    if not (build/archive).exists():run('npm','pack',package,'--pack-destination',str(build))
    target=build/'layer'/destination;target.parent.mkdir(parents=True,exist_ok=True)
    with tarfile.open(build/archive) as source:
        with source.extractfile(member) as data,target.open('wb') as output:shutil.copyfileobj(data,output)
    target.chmod(0o755)
fontdir=build/'layer/fonts';fontdir.mkdir(parents=True,exist_ok=True)
for filename,url in [
    ('NotoSansCJKsc-Regular.otf','https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/OTF/SimplifiedChinese/NotoSansCJKsc-Regular.otf'),
    ('LICENSE.txt','https://raw.githubusercontent.com/notofonts/noto-cjk/main/Sans/LICENSE')]:
    target=fontdir/filename
    if not target.exists():urllib.request.urlretrieve(url,target)
manifest={str(p.relative_to(build)):hashlib.sha256(p.read_bytes()).hexdigest()
    for p in sorted((build/'layer').rglob('*')) if p.is_file()}
expected=json.loads((HERE/'tool-fingerprints.json').read_text())
if manifest!=expected:raise RuntimeError('Media tool/font hashes differ from the reviewed asset fingerprints')
(build/'tool-sha256.json').write_text(json.dumps(manifest,indent=2))
print('Local deployment assets prepared. Resource deployment is a separate step.')
