"""Offline speech guards; fixtures never claim a real provider invocation."""
import base64
import copy
import json
from pathlib import Path
import unittest
from doubao_tts import SpeechError, decode_stream, synthesize
from narration_agent import NarrationAgent, validate_dialogue
from readiness_agent import ModelOutputError, ValidationError


class SpeechTests(unittest.TestCase):
    def setUp(self):
        self.plan=json.loads((Path(__file__).resolve().parents[1]/'data/formal-dialogue.json').read_text())

    def test_registered_dialogue_passes_and_contains_two_roles(self):
        self.assertEqual(validate_dialogue(self.plan),self.plan)

    def test_unknown_identity_overlap_early_result_and_uncited_claim_rejected(self):
        changes=[('sourceSha256','0'*64),('visualSha256','1'*64)]
        for field,value in changes:
            plan=copy.deepcopy(self.plan);plan[field]=value
            with self.subTest(field=field),self.assertRaises(ValidationError):validate_dialogue(plan)
        for change in ({'start':1.0},{'text':'三分命中！'},{'evidenceIds':['invented']},{'text':'犯规罚球！'}):
            plan=copy.deepcopy(self.plan);plan['cues'][2].update(change)
            with self.subTest(change=change),self.assertRaises(ValidationError):validate_dialogue(plan)

    def test_audio_chunk_stream_reassembles_without_provider_messages(self):
        lines=[b'data: '+json.dumps({'code':0,'data':base64.b64encode(b'fake-audio').decode()}).encode(),
               b'{"code":20000000}']
        audio,receipt=decode_stream(lines)
        self.assertEqual(audio,b'fake-audio');self.assertEqual(receipt['codes'],[0,20000000])

    def test_empty_malformed_or_failed_stream_cannot_be_marked_complete(self):
        for lines in ([b'{"code":20000000}'],[b'not-json'],[b'{"code":45000000,"data":"ZmFrZQ=="}']):
            with self.subTest(lines=lines),self.assertRaises(SpeechError):decode_stream(lines)

    def test_invalid_voice_and_missing_key_never_open_network(self):
        for role,key in (('C','secret'),('A','')):
            with self.subTest(role=role),self.assertRaises(SpeechError):synthesize('解说',role,key)

    def test_approval_without_optional_notes_succeeds_only_after_real_source_read(self):
        plan=self.plan
        class Reader:
            bucket='synthetic-test-bucket'
            model_id='synthetic-model'
            def __init__(self):self.bedrock=self;self.calls=0;self.reads=0
            def read_bytes(self,key,limit):
                self.reads+=1
                return json.dumps(plan).encode()
            def converse(self,**kwargs):
                self.calls+=1
                name='read_narration_source' if self.calls==1 else 'approve_dialogue'
                value={} if self.calls==1 else {'approved':True,'checkedCueIds':[x['id'] for x in plan['cues']]}
                return {'output':{'message':{'role':'assistant','content':[{'toolUse':{
                    'toolUseId':str(self.calls),'name':name,'input':value}}]}}}
        reader=Reader();result=NarrationAgent(reader).run({'mode':'narration','request_id':'synthetic-test'})
        self.assertTrue(result['approved']);self.assertEqual(reader.reads,1)
        self.assertEqual([x['tool'] for x in result['trace']],['read_narration_source','approve_dialogue'])

    def test_unsupported_request_is_rejected_before_source_read(self):
        with self.assertRaises(ValidationError):
            NarrationAgent(None).run({'mode':'narration','request_id':'test','url':'https://example.com'})


if __name__=='__main__':unittest.main()
