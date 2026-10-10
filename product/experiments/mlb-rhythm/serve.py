"""Loopback-only narrative experiment with verified, range-readable sources."""
import argparse, hashlib, json, mimetypes, re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[2]

def source_file(sample):
    names = {'flagg': ['训练_弗拉格2月1日.mp4', 'flagg.mp4']}
    base = ROOT / 'data/reference/train_video/train_video'
    return next((base / name for name in names[sample] if (base / name).is_file()), None)

def catalog():
    manifest = ROOT / 'product/data/stories.json'
    stories = json.loads(manifest.read_text(encoding='utf-8'))
    files = {'/': HERE / 'index.html', '/index.html': HERE / 'index.html', '/stories.json': manifest, '/story-plan.json': HERE / 'story-plan.json', '/data-plan.md': HERE / 'DATA-PLAN.md'}
    for story in stories['stories']:
        sample = story['sample']
        if sample != 'flagg': continue
        source = source_file(sample)
        if source:
            with source.open('rb') as stream: actual = hashlib.file_digest(stream, 'sha256').hexdigest()
            if actual == story['sourceVideoSha256']: files[f'/samples/{sample}.mp4'] = source
        rendered = ROOT / f'product/build/mlb-rhythm/{sample}/enhanced.mp4'
        files[f'/rendered-{sample}.mp4'] = rendered
        files['/reverse.mp4'] = rendered.parent / 'reverse.mp4'
        files['/focus-14.png'] = rendered.parent / 'overlay-07/static.png'
        files['/focus-16.5.png'] = rendered.parent / 'overlay-09/static.png'
    voice = ROOT / 'product/build/mlb-rhythm/flagg-voice'
    files['/voice-preview.wav'] = voice / 'preview.wav'
    files['/voice-preview.json'] = voice / 'preview.json'
    files['/rendered-flagg-voice.mp4'] = voice / 'enhanced.mp4'
    files['/voice-captions.vtt'] = voice / 'captions.vtt'
    files['/voice-auditions.json'] = voice / 'auditions.json'
    files['/original-commentary.wav'] = voice / 'original-commentary.wav'
    return files

class Handler(BaseHTTPRequestHandler):
    def do_HEAD(self): self.send_file(False)
    def do_GET(self): self.send_file(True)
    def send_file(self, body):
        request_path = urlsplit(self.path).path
        path = self.server.files.get(request_path)
        audition_match = re.fullmatch(r'/audition-([a-z0-9-]{1,40})\.wav', request_path)
        if audition_match:
            path = ROOT / 'product/build/mlb-rhythm/flagg-voice' / f'audition-{audition_match[1]}.wav'
        frame_match = re.fullmatch(r'/frames/frame-(\d{4})\.jpg', request_path)
        if frame_match and int(frame_match[1]) < 1291:
            path = ROOT / 'product/build/mlb-rhythm/flagg/frames' / f'frame-{frame_match[1]}.jpg'
        if not path or not path.is_file(): self.send_error(404); return
        size = path.stat().st_size
        start, end, status = 0, size - 1, 200
        request = self.headers.get('Range')
        if request:
            match = re.fullmatch(r'bytes=(\d+)-(\d*)', request)
            if not match: self.send_error(416); return
            start = int(match[1]); end = min(int(match[2]) if match[2] else size - 1, size - 1)
            if start > end: self.send_error(416); return
            status = 206
        self.send_response(status)
        self.send_header('Content-Type', mimetypes.guess_type(path)[0] or 'application/octet-stream')
        self.send_header('Content-Length', str(end - start + 1))
        self.send_header('Accept-Ranges', 'bytes')
        self.send_header('Cache-Control', 'no-store')
        if status == 206: self.send_header('Content-Range', f'bytes {start}-{end}/{size}')
        self.end_headers()
        if body:
            try:
                with path.open('rb') as stream:
                    stream.seek(start); remaining = end - start + 1
                    while remaining:
                        block = stream.read(min(remaining, 256 * 1024))
                        if not block: break
                        self.wfile.write(block); remaining -= len(block)
            except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError): pass

if __name__ == '__main__':
    parser = argparse.ArgumentParser(); parser.add_argument('--port', type=int, default=4180)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), Handler); server.files = catalog()
    print(f'Narrative preview: http://127.0.0.1:{args.port}/', flush=True)
    server.serve_forever()
