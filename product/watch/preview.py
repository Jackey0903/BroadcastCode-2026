#!/usr/bin/env python3
"""Frontend-only loopback preview. No credentials, task API, or cloud access."""
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import unquote,urlsplit
import argparse,mimetypes,os
ROOT=Path(__file__).resolve().parent
def default_media_dir():
 configured=os.environ.get('BROADCASTCODE_MEDIA_DIR')
 if configured:return Path(configured).expanduser().resolve()
 # Both locations are local, known source-media folders. Copying this frontend
 # into product/watch must not copy the MP4 files or trigger a remote download.
 candidates=[ROOT.parent/'local-media',Path.home()/'Desktop/NBADRAFT/broadcastcode-ui/local-media']
 for candidate in candidates:
  if all((candidate/name).is_file() for name in ('flagg.mp4','amen.mp4')):return candidate.resolve()
 for candidate in candidates:
  if any((candidate/name).is_file() for name in ('flagg.mp4','amen.mp4')):return candidate.resolve()
 return candidates[-1].resolve()
parser=argparse.ArgumentParser(description='Local-only BroadcastCode frontend preview; binds 127.0.0.1.')
parser.add_argument('--port',type=int,default=4178)
parser.add_argument('--media-dir',help='Directory containing flagg.mp4 and amen.mp4; overrides BROADCASTCODE_MEDIA_DIR.')
args=parser.parse_args()
if not 1<=args.port<=65535:parser.error('--port must be between 1 and 65535')
MEDIA=Path(args.media_dir).expanduser().resolve() if args.media_dir is not None else default_media_dir()
class Handler(SimpleHTTPRequestHandler):
 def log_message(self,*args):pass
 def do_GET(self):self.send_file(False)
 def do_HEAD(self):self.send_file(True)
 def send_file(self,head):
  path=unquote(urlsplit(self.path).path)
  if path.startswith('/samples/') and path.rsplit('/',1)[-1] in ('flagg.mp4','amen.mp4'):
   target=MEDIA/path.rsplit('/',1)[-1]
  else:
   target=(ROOT/path.lstrip('/')).resolve()
   if target.is_dir():target=target/'index.html'
   if not target.is_relative_to(ROOT) or target.suffix not in ('.html','.js','.css','.json','.svg','.png','.jpg','.md','.txt'):
    self.send_error(404);return
  if not target.is_file():self.send_error(404);return
  size=target.stat().st_size;start=0;end=size-1;status=200
  r=self.headers.get('Range','')
  if r.startswith('bytes='):
   try:
    a,b=r[6:].split('-',1);start=int(a or 0);end=min(int(b) if b else end,end);status=206
    if start>end or start<0:raise ValueError()
   except ValueError:self.send_error(416);return
  self.send_response(status);self.send_header('Content-Type',mimetypes.guess_type(target)[0] or 'application/octet-stream');self.send_header('Accept-Ranges','bytes');self.send_header('Cache-Control','no-cache');self.send_header('Content-Length',str(end-start+1))
  if status==206:self.send_header('Content-Range',f'bytes {start}-{end}/{size}')
  self.end_headers()
  if head:return
  try:
   with target.open('rb') as f:
    f.seek(start);remaining=end-start+1
    while remaining:
     block=f.read(min(1024*1024,remaining))
     if not block:break
     self.wfile.write(block);remaining-=len(block)
  except (BrokenPipeError,ConnectionResetError):pass
print(f'BroadcastCode UI: http://127.0.0.1:{args.port}/',flush=True)
print(f'Local media: {MEDIA}',flush=True)
for name in ('flagg.mp4','amen.mp4'):
 print(f'  {name}: {"available" if (MEDIA/name).is_file() else "missing (the UI will show its missing-media state)"}',flush=True)
class PreviewServer(ThreadingHTTPServer):
 request_queue_size=128
 daemon_threads=True
PreviewServer(('127.0.0.1',args.port),Handler).serve_forever()
