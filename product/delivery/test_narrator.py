"""Offline boundaries for optional real AWS media clients; no cloud/inference."""
import copy
import io
import json
from pathlib import Path
import subprocess
import unittest
from unittest.mock import patch

import narrator
import test_delivery as fixture_module


class MediaS3(fixture_module.FakeS3):
    def __init__(self, objects):
        super().__init__(objects)
        self.puts = []
        self.metadata_records = {}

    def metadata(self, bucket, key):
        return {**super().metadata(bucket, key), "Metadata": self.metadata_records.get(key, {})}

    def put_object(self, **request):
        self.puts.append(copy.deepcopy(request))
        self.objects[request["Key"]] = request["Body"]
        self.metadata_records[request["Key"]] = request["Metadata"]


class Polly:
    def __init__(self, fail=False):
        self.calls, self.fail, self.stream = [], fail, None

    def synthesize_speech(self, **request):
        self.calls.append(request)
        if self.fail:
            raise OSError("Polly unavailable")
        self.stream = io.BytesIO(b"synthetic-mp3-for-boundary-test")
        return {"AudioStream": self.stream}


class Rekognition:
    def __init__(self, fail=False):
        self.calls, self.fail = [], fail

    def detect_labels(self, **request):
        self.calls.append(request)
        if self.fail:
            raise OSError("Rekognition unavailable")
        return {"Labels": [{"Name": "Basketball", "Confidence": 98.3}]}


def accepted_fixture():
    _, original, table = fixture_module.fixture()
    table.item["analysis"]["plan"]["chapters"] = [
        {"start": 0, "end": .4, "caption": "持球人<&>向篮下移动"},
        {"start": .4, "end": 1, "caption": "官方确认命中；机会质量见指标。"}]
    original.objects[fixture_module.PREFIX + "/analysis.json"] = json.dumps(table.item["analysis"]).encode()
    registry = json.loads(original.objects["product/config/samples.json"])
    registry["flagg"]["frames"] = [{"s3_uri": f"s3://{fixture_module.CONFIG.bucket}/frames/flagg.jpg", "format": "jpeg"}]
    original.objects["product/config/samples.json"] = json.dumps(registry).encode()
    receipt = narrator.delivery.verify_delivery({"jobId": fixture_module.JOB}, original, table,
                                               fixture_module.CONFIG, inspector=fixture_module.media)
    assert receipt["verified"]
    return MediaS3(original.objects), table, Polly(), Rekognition()


def mix_fixture(source, audio, output, budget):
    assert source.read_bytes() == fixture_module.VIDEO
    output.write_bytes(fixture_module.VIDEO + b"synthetic-narrated-boundary-fixture")


def narrated_probe(path, budget):
    return {"durationMs": 1024, "width": 1280, "height": 900, "audioStreams": 2,
            "fullDecodeVerified": True, "videoCodec": "h264", "audioCodec": "aac"}


def compose_fixture(clips, audio, duration, budget):
    assert all(segment["start"] + segment["audioDurationSeconds"] <= segment["end"] for _, segment in clips)
    audio.write_bytes(b"synthetic-composed-timeline-mp3")


class NarratorBoundaries(unittest.TestCase):
    def run_media(self, s3, table, polly, rekognition, **overrides):
        options = {"audio_probe": lambda *_: .2, "audio_composer": compose_fixture,
                   "mixer": mix_fixture, "inspector": narrated_probe, **overrides}
        return narrator.produce_native_media({"jobId": fixture_module.JOB}, s3, table, polly,
                                            rekognition, fixture_module.CONFIG, **options)

    def test_verified_job_produces_declared_speech_and_scene_without_changing_originals(self):
        s3, table, polly, rekognition = accepted_fixture()
        originals = {key: s3.objects[key] for key in (fixture_module.PREFIX + "/enhanced.mp4",
                                                    fixture_module.PREFIX + "/analysis.json")}
        result = self.run_media(s3, table, polly, rekognition)
        self.assertTrue(result["available"])
        self.assertEqual(result["officialMetric"]["rawValue"], .51)
        self.assertIn("51.0%", result["text"])
        self.assertIn("&lt;&amp;&gt;", polly.calls[0]["Text"])
        self.assertEqual((polly.calls[0]["VoiceId"], polly.calls[0]["Engine"]), ("Zhiyu", "standard"))
        self.assertTrue(polly.stream.closed)
        self.assertEqual(result["scene"]["labels"], [{"Name": "Basketball", "Confidence": 98.3}])
        self.assertEqual(rekognition.calls[0]["Image"]["S3Object"]["Name"], "frames/flagg.jpg")
        self.assertEqual({key: s3.objects[key] for key in originals}, originals)
        self.assertEqual({item["Key"].split("/")[-1] for item in s3.puts},
                         {"narration.mp3", "narrated.mp4", "narration.json"})

    def test_unverified_task_and_wrong_actual_hash_never_call_native_services(self):
        for mutation in ("unverified", "hash"):
            with self.subTest(mutation=mutation):
                s3, table, polly, rekognition = accepted_fixture()
                if mutation == "unverified":
                    table.item["deliveryVerification"]["verified"] = False
                else:
                    s3.objects[fixture_module.PREFIX + "/enhanced.mp4"] = fixture_module.VIDEO[:-1] + b"X"
                result = self.run_media(s3, table, polly, rekognition)
                self.assertFalse(result["available"])
                self.assertFalse(polly.calls or rekognition.calls or s3.puts)

    def test_replay_checks_receipt_metadata_and_actual_hash_without_native_calls_or_uploads(self):
        s3, table, polly, rekognition = accepted_fixture()
        first = self.run_media(s3, table, polly, rekognition)
        self.assertTrue(first["available"])
        polly.calls.clear(); rekognition.calls.clear(); s3.puts.clear()
        repeat = self.run_media(s3, table, polly, rekognition,
                                mixer=lambda *_: self.fail("must not render an accepted snapshot twice"))
        self.assertTrue(repeat["idempotent"])
        self.assertEqual(repeat["videoSha256"], first["videoSha256"])
        self.assertFalse(polly.calls or rekognition.calls or s3.puts)
        key = fixture_module.PREFIX + "/narrated.mp4"
        # Matching claimed SHA metadata cannot disguise changed payload bytes.
        s3.objects[key] = s3.objects[key][:-1] + b"X"
        rejected = self.run_media(s3, table, polly, rekognition)
        self.assertEqual(rejected["code"], "cached_narration_mismatch")
        self.assertFalse(polly.calls or rekognition.calls or s3.puts)

    def test_long_speech_is_rejected_without_truncation_or_media_upload(self):
        s3, table, polly, rekognition = accepted_fixture()
        mixer = lambda *_: self.fail("must not mix or truncate overlong speech")
        result = self.run_media(s3, table, polly, rekognition, audio_probe=lambda *_: 1.1, mixer=mixer)
        self.assertEqual(result["code"], "speech_exceeds_window")
        self.assertTrue(result["scene"]["available"])
        self.assertEqual([item["Key"].split("/")[-1] for item in s3.puts], ["narration.json"])

    def test_polly_failure_falls_back_and_scene_failure_does_not_block_speech(self):
        s3, table, _, rekognition = accepted_fixture()
        result = self.run_media(s3, table, Polly(fail=True), rekognition)
        self.assertFalse(result["available"])
        self.assertTrue(result["scene"]["available"])
        self.assertEqual(result["originalVideoUrl"], table.item["videoUrl"])
        self.assertEqual([item["Key"].split("/")[-1] for item in s3.puts], ["narration.json"])
        s3, table, polly, _ = accepted_fixture()
        result = self.run_media(s3, table, polly, Rekognition(fail=True))
        self.assertTrue(result["available"])
        self.assertFalse(result["scene"]["available"])

    def test_complete_decode_failure_never_uploads_unverified_audio_or_video(self):
        s3, table, polly, rekognition = accepted_fixture()
        def corrupt(*_):
            raise subprocess.CalledProcessError(1, ["ffmpeg"])
        result = self.run_media(s3, table, polly, rekognition, inspector=corrupt)
        self.assertFalse(result["available"])
        self.assertEqual([item["Key"].split("/")[-1] for item in s3.puts], ["narration.json"])
        self.assertNotIn(fixture_module.PREFIX + "/narrated.mp4", s3.objects)

    def test_text_budget_and_real_mixer_preserve_original_tracks_without_shortest(self):
        with self.assertRaises(narrator.delivery.Rejected):
            narrator.narration_text({"chapters": [{"caption": "长" * 121}], "metrics": []})
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            output = Path(directory) / "narrated.mp4"
            with patch.object(narrator.Path, "is_file", return_value=True), \
                    patch.object(narrator.subprocess, "run") as runner:
                narrator.mix_video(Path(directory) / "source.mp4", Path(directory) / "speech.mp3", output,
                                   narrator.delivery.Budget())
            command = runner.call_args.args[0]
            self.assertNotIn("-shortest", command)
            self.assertNotIn("-t", command)
            self.assertIn("0:a", command)
            self.assertIn("duration=first", command[command.index("-filter_complex") + 1])
            self.assertEqual((Path(directory) / "ai-speech.txt").read_text(), narrator.DECLARATION)

    def test_late_metric_is_scheduled_after_reveal_and_result_cannot_play_from_opening(self):
        plan = {"chapters": [
            {"start": 0, "end": 9, "caption": "末节，独行侠落后，弗拉格持球。"},
            {"start": 9, "end": 15.5, "caption": "弗拉格向禁区附近推进，防守在其身前。"},
            {"start": 15.5, "end": 17.4, "caption": "篮下起跳，防守双臂举起。"},
            {"start": 17.4, "end": 21.548, "caption": "官方确认命中；出手机会质量见官方指标。"}],
            "metrics": [{"revealAt": 18.5, "display": "51.0%"}]}
        segments, _ = narrator.narration_segments(plan, 21.548)
        metric = next(item for item in segments if item["kind"] == "official_metric")
        self.assertEqual(metric["start"], 18.5)
        self.assertAlmostEqual(metric["end"] - metric["start"], 3.048)
        self.assertTrue(all("51.0%" not in item["text"] and "命中" not in item["text"]
                            for item in segments if item["start"] < 17.4))
        self.assertEqual(next(item for item in segments if item.get("chapterIndex") == 2)["text"], "篮下起跳。")
        without_metric, _ = narrator.narration_segments({**plan, "metrics": []}, 21.548)
        result = next(item for item in without_metric if "命中" in item["text"])
        self.assertEqual(result["start"], 17.4)

    def test_oversize_late_segment_falls_back_before_composition_or_upload(self):
        s3, table, polly, rekognition = accepted_fixture()
        durations = iter([.2, .6])  # Late metric has only a .5-second window.
        result = self.run_media(s3, table, polly, rekognition, audio_probe=lambda *_: next(durations),
                                audio_composer=lambda *_: self.fail("Must not cut an overlong late segment"))
        self.assertEqual(result["code"], "speech_exceeds_window")
        self.assertFalse(result["available"])
        self.assertEqual([item["Key"].split("/")[-1] for item in s3.puts], ["narration.json"])

    def test_real_source_output_pts_tail_difference_bounds_window_without_cutting_speech(self):
        plan = {"chapters": [{"start": 17.4, "end": 21.548118, "caption": "官方确认命中。"}],
                "metrics": [{"revealAt": 18.5, "display": "51.0%"}]}
        segments, _ = narrator.narration_segments(plan, 21.548005)
        self.assertEqual(segments[0]["start"], 18.5)
        self.assertEqual(segments[0]["end"], 21.548005)
        plan["chapters"][0]["end"] = 21.9
        with self.assertRaises(narrator.delivery.Rejected):
            narrator.narration_segments(plan, 21.548005)

    def test_audio_composer_delays_clips_and_only_bounds_silent_input(self):
        import tempfile
        with tempfile.TemporaryDirectory() as directory:
            with patch.object(narrator.subprocess, "run") as runner:
                narrator.compose_audio([(Path(directory) / "late.mp3", {"start": 18.5})],
                                       Path(directory) / "narration.mp3", 21.548, narrator.delivery.Budget())
            command = runner.call_args.args[0]
            graph = command[command.index("-filter_complex") + 1]
            self.assertIn("adelay=18500", graph)
            self.assertLess(command.index("-t"), command.index("anullsrc=channel_layout=stereo:sample_rate=24000"))
            self.assertNotIn("atrim", graph)
            self.assertNotIn("-shortest", command)

    def test_previous_continuous_speech_version_is_regenerated(self):
        s3, table, polly, rekognition = accepted_fixture()
        self.assertTrue(self.run_media(s3, table, polly, rekognition)["available"])
        key = fixture_module.PREFIX + "/narration.json"
        receipt = json.loads(s3.objects[key]);receipt["version"] = "native-media-v1"
        s3.objects[key] = json.dumps(receipt).encode()
        polly.calls.clear()
        replay = self.run_media(s3, table, polly, rekognition)
        self.assertTrue(replay["available"])
        self.assertEqual(replay["version"], "native-media-v2")
        self.assertTrue(polly.calls)


if __name__ == "__main__":
    unittest.main()
