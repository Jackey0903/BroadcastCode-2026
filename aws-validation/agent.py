import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import boto3

class Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path != '/ping':
            self.send_error(404)
            return
        self.reply({'status': 'Healthy'})

    def do_POST(self):
        if self.path != '/invocations':
            self.send_error(404)
            return
        request = json.loads(self.rfile.read(int(self.headers.get('Content-Length', 0))))
        response = boto3.client('bedrock-runtime', region_name='us-east-1').converse(
            modelId='global.anthropic.claude-sonnet-4-6',
            messages=[{'role': 'user', 'content': [{'text': request.get('prompt', 'Reply with exactly AGENT_CHECK_OK.')}]}],
            inferenceConfig={'maxTokens': 24, 'temperature': 0},
        )
        self.reply({'status': 'AGENT_CHECK_OK', 'model_response': response['output']['message']['content'][0]['text']})

    def reply(self, data):
        payload = json.dumps(data).encode()
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

ThreadingHTTPServer(('0.0.0.0', 8080), Handler).serve_forever()
