#!/usr/bin/env python3
"""Local product preview; media and the real bounded API use the retained deployment.

No browser credentials or AWS secrets are served. POST /api/jobs is a real cloud run.
"""
import argparse
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument('--port', type=int, default=4173)
args = parser.parse_args()
outputs = json.loads((ROOT/'readiness-lab/outputs.json').read_text())['BroadcastCodeTeam02Readiness20261006']
ORIGIN = outputs['Website']

class Preview(SimpleHTTPRequestHandler):
    def translate_path(self, path):
        path = path.split('?',1)[0]
        if path.startswith('/product/data/'):
            base = ROOT / 'product/data'
            relative = path.removeprefix('/product/data/')
        else:
            base = ROOT / 'product/web'
            relative = path.removeprefix('/product/').lstrip('/')
            if relative in ('','product'):
                relative='index.html'
        target = (base / relative).resolve()
        if not target.is_relative_to(base.resolve()):
            return str(base/'__missing__')
        return str(target)

    def do_GET(self):
        if self.path.startswith('/api/'):
            self.proxy()
        elif self.path.startswith(('/samples/','/frames/','/outputs/')):
            self.send_response(302)
            self.send_header('Location', ORIGIN + self.path)
            self.end_headers()
        else:
            super().do_GET()

    def do_POST(self):
        if self.path != '/api/jobs':
            self.send_error(404)
            return
        self.proxy()

    def proxy(self):
        try:
            size=int(self.headers.get('Content-Length','0'))
            if size>4096:
                self.send_error(413)
                return
            data = self.rfile.read(size) if self.command=='POST' else None
            headers = {'Content-Type':'application/json'}
            if self.headers.get('x-amz-content-sha256'):
                headers['x-amz-content-sha256']=self.headers['x-amz-content-sha256']
            request=urllib.request.Request(ORIGIN+self.path,data=data,headers=headers,method=self.command)
            try:
                response=urllib.request.urlopen(request,timeout=25)
            except urllib.error.HTTPError as error:
                response=error
            with response:
                payload=response.read()
                self.send_response(response.status)
                self.send_header('Content-Type','application/json; charset=utf-8')
                self.send_header('Cache-Control','no-store')
                self.end_headers()
                self.wfile.write(payload)
        except (OSError,ValueError):
            self.send_error(502,'Cloud API is unavailable')

print(f'Preview: http://127.0.0.1:{args.port}/product/', flush=True)
ThreadingHTTPServer(('127.0.0.1',args.port),Preview).serve_forever()
