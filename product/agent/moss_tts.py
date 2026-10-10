"""Official MOSS API adapter for original two-host commentary.

Model audio is generated remotely; media editing and rendering stay local.
Credentials are read by the CLI and never returned in receipts. Reference
voices are created from descriptions, without recordings of real announcers.
"""
import hashlib
import ipaddress
import json
from pathlib import Path
import socket
from urllib.parse import urlsplit
import urllib.error
import urllib.request

API = 'https://api.mosi.cn'
MODELS = ('moss-ttsd-1.0', 'moss-tts-1.5-flash', 'moss-tts-1.0-pro')
MAX_AUDIO_BYTES = 16 * 1024 * 1024


class MossError(RuntimeError):
    """Report bounded status codes, never headers, keys or signed URLs."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise MossError('Authenticated MOSS redirects are refused')


def download_audio(url):
    parsed = urlsplit(url)
    if (parsed.scheme != 'https' or not parsed.hostname or parsed.username
            or parsed.password or parsed.port not in (None, 443)):
        raise MossError('Invalid MOSS audio delivery URL')
    for address in socket.getaddrinfo(parsed.hostname, 443, type=socket.SOCK_STREAM):
        if not ipaddress.ip_address(address[4][0]).is_global:
            raise MossError('MOSS audio delivery must use a public address')
    # Deliberately use a new unauthenticated request for signed delivery URLs.
    opener = urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(url, timeout=45) as response:
            data = response.read(MAX_AUDIO_BYTES + 1)
    except (OSError, urllib.error.HTTPError) as error:
        raise MossError(f'Audio delivery failed: {type(error).__name__}') from None
    if not data or len(data) > MAX_AUDIO_BYTES:
        raise MossError('Audio delivery exceeds its size budget')
    return data


class MossTTS:
    def __init__(self, api_key, directory):
        if not isinstance(api_key, str) or not api_key.strip():
            raise MossError('MOSS_API_KEY is required in the local backend')
        self.key = api_key
        self.directory = Path(directory)
        self.directory.mkdir(parents=True, exist_ok=True)
        self.opener = urllib.request.build_opener(NoRedirect())

    def request(self, route, payload):
        if route not in ('/v1/audio/voice/generations', '/v1/audio/speech',
                         '/v1/audio/speech/speakers'):
            raise MossError('Unsupported official MOSS route')
        request = urllib.request.Request(API + route,
            data=json.dumps(payload, ensure_ascii=False).encode(),
            headers={'Authorization': 'Bearer ' + self.key,
                     'Content-Type': 'application/json'})
        try:
            with self.opener.open(request, timeout=150) as response:
                data = response.read(MAX_AUDIO_BYTES + 1)
                content_type = response.headers.get('Content-Type', '')
                request_id = response.headers.get('X-Request-Id')
        except urllib.error.HTTPError as error:
            raise MossError(f'MOSS HTTP {error.code}') from None
        except (OSError, TimeoutError) as error:
            raise MossError(f'MOSS transport {type(error).__name__}') from None
        if not data or len(data) > MAX_AUDIO_BYTES:
            raise MossError('MOSS response exceeds its size budget')
        if 'json' in content_type:
            result = json.loads(data)
            if result.get('status') not in (None, 'SUCCESS', 'succeeded', 'completed'):
                raise MossError('MOSS request did not return a completed result')
            return result, request_id
        return data, request_id

    def voices(self, roles):
        voices = {}
        for role in ('A', 'B'):
            path = self.directory / f'voice-{role}.json'
            if not path.is_file():
                text = ('Christie drives. He steps back, lets it fly. Off the glass! Three!'
                        if role == 'A' else
                        'That rebound gives Dallas another chance. Watch the screen and the space on the right.')
                result, _ = self.request('/v1/audio/voice/generations', {
                    'model': 'moss-voice-generator-1.0', 'input': text,
                    'instruction': roles[role], 'response_format': 'wav',
                    'delivery_method': 'url', 'create_voice': True})
                if not isinstance(result, dict) or not result.get('voice_id'):
                    raise MossError('MOSS did not create an original voice')
                result['gamebuddyDesign'] = {
                    'instructionSha256': hashlib.sha256(roles[role].encode()).hexdigest(),
                    'instruction': roles[role], 'text': text, 'referencePerson': None}
                path.write_text(json.dumps(result, ensure_ascii=False, indent=2))
                path.chmod(0o600)
            result = json.loads(path.read_text())
            if result.get('status') != 'SUCCESS' or not isinstance(result.get('voice_id'), str):
                raise MossError('Invalid saved MOSS voice result')
            if result.get('gamebuddyDesign', {}).get('instructionSha256') != hashlib.sha256(roles[role].encode()).hexdigest():
                raise MossError('Voice description changed; use a new casting workdir')
            voices[role] = result['voice_id']
            preview = self.directory / f'voice-{role}.wav'
            if not preview.is_file() and result.get('url'):
                preview.write_bytes(download_audio(result['url']))
        return voices

    def synthesize(self, text, role, voices, *, model='moss-ttsd-1.0', duration=None):
        if model not in MODELS or role not in ('A', 'B') or not 1 <= len(text) <= 180:
            raise MossError('Invalid bounded MOSS speech request')
        payload = {'model': model, 'response_format': 'wav', 'delivery_method': 'audio'}
        if model == 'moss-ttsd-1.0':
            route = '/v1/audio/speech/speakers'
            payload.update(speakers=[{'id': name, 'voice_id': voices[name]} for name in ('A', 'B')],
                           segments=[{'speaker': role, 'text': text}])
        else:
            route = '/v1/audio/speech'
            payload.update(input=text, voice_id=voices[role])
            if model == 'moss-tts-1.5-flash':
                payload['language'] = 'English'
            if duration is not None:
                payload['expected_duration_sec'] = float(duration)
        audio, request_id = self.request(route, payload)
        if isinstance(audio, dict):
            request_id = audio.get('id') or request_id
            audio = download_audio(audio['url'])
        if not audio.startswith(b'RIFF') or audio[8:12] != b'WAVE':
            raise MossError('MOSS did not return the requested WAV container')
        return audio, {'provider': 'MOSS', 'model': model, 'role': role,
                       'voiceId': voices[role], 'requestId': request_id,
                       'textSha256': hashlib.sha256(text.encode()).hexdigest(),
                       'requestedDurationSeconds': duration,
                       'audioSha256': hashlib.sha256(audio).hexdigest(),
                       'audioBytes': len(audio), 'voiceDesignModel': 'moss-voice-generator-1.0',
                       'referencePerson': None, 'remoteSynthesis': True}
