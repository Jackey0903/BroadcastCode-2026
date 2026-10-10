"""Bounded Doubao v3 HTTP TTS adapter; credentials never enter receipts.

Official API: https://docs.volcengine.com/docs/DoubaoVoice/unidirectional-streaming-text-to-speech-http
v3 is the transport version; the verified expressive model is TTS 2.0.
"""
import base64
import hashlib
import json
import urllib.error
import urllib.request
import uuid

ENDPOINT = 'https://openspeech.bytedance.com/api/v3/tts/unidirectional'
RESOURCE = 'seed-tts-2.0'
MODEL = 'seed-tts-2.0-expressive'
VOICES = {'A': 'zh_male_m191_uranus_bigtts', 'B': 'zh_female_vv_uranus_bigtts'}
MAX_AUDIO_BYTES = 8 * 1024 * 1024


class SpeechError(RuntimeError):
    """Provider failures expose only status codes, never request headers."""


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise SpeechError('TTS redirects are refused')


def decode_stream(lines):
    audio, codes, usage, size = bytearray(), set(), {}, 0
    for line in lines:
        size += len(line)
        if size > MAX_AUDIO_BYTES * 2:
            raise SpeechError('TTS response exceeds budget')
        line = line.strip()
        if not line or line.startswith(b':'):
            continue
        if line.startswith(b'data:'):
            line = line[5:].strip()
        if line == b'[DONE]':
            continue
        try:
            event = json.loads(line)
            code = event.get('code')
            if code not in (0, 20000000):
                raise SpeechError(f'TTS provider status {code}')
            codes.add(code)
            if event.get('data'):
                audio.extend(base64.b64decode(event['data'], validate=True))
            if len(audio) > MAX_AUDIO_BYTES:
                raise SpeechError('TTS audio exceeds budget')
            if isinstance(event.get('usage'), dict):
                usage = {key: value for key, value in event['usage'].items()
                         if key == 'text_words' and isinstance(value, int)}
        except (ValueError, TypeError, KeyError) as error:
            raise SpeechError('Malformed TTS response') from error
    if not audio:
        raise SpeechError('TTS returned no audio')
    return bytes(audio), {'codes': sorted(codes), 'usage': usage}


def synthesize(text, role, api_key, *, instruction='', speech_rate=0, opener=None):
    if role not in VOICES or not isinstance(text, str) or not 1 <= len(text) <= 120:
        raise SpeechError('Invalid bounded speech request')
    if not isinstance(api_key, str) or not api_key.strip():
        raise SpeechError('DOUBAO_API_KEY is required on the backend')
    if not isinstance(speech_rate, int) or not -20 <= speech_rate <= 30:
        raise SpeechError('Speech rate exceeds production budget')
    if not isinstance(instruction, str) or len(instruction) > 200:
        raise SpeechError('Invalid voice direction')
    request_id = str(uuid.uuid4())
    params = {'text': text, 'speaker': VOICES[role], 'model': MODEL,
              'audio_params': {'format': 'mp3', 'sample_rate': 24000, 'bit_rate': 160000,
                               'speech_rate': speech_rate},
              'additions': json.dumps({'context_texts': [instruction],
                                      'aigc_metadata': {'enable': True, 'content_producer': 'GameBuddy'}}, ensure_ascii=False)}
    request = urllib.request.Request(ENDPOINT, json.dumps({'req_params': params}).encode(),
        headers={'X-Api-Key': api_key, 'X-Api-Resource-Id': RESOURCE,
                 'X-Api-Request-Id': request_id, 'Content-Type': 'application/json'})
    opener = opener or urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request, timeout=35) as response:
            audio, metadata = decode_stream(response)
            metadata.update(logId=response.headers.get('X-Tt-Logid'), requestId=request_id)
    except urllib.error.HTTPError as error:
        raise SpeechError(f'TTS HTTP {error.code}') from None
    except (OSError, TimeoutError) as error:
        raise SpeechError(f'TTS transport {type(error).__name__}') from None
    metadata.update(provider='doubao', apiVersion='v3', resource=RESOURCE, model=MODEL,
                    role=role, speaker=VOICES[role], audioSha256=hashlib.sha256(audio).hexdigest(),
                    audioBytes=len(audio))
    return audio, metadata
