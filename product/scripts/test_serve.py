"""Exercise the offline preview through real loopback HTTP requests, with no AWS."""
import copy
import hashlib
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch

from serve import Catalog, SOURCES, handler_for

JOB = "a" * 32
MEDIA = b"test-only-mp4-bytes" * 10
SHA = hashlib.sha256(MEDIA).hexdigest()


class PreviewTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.write("product/web/index.html", b"<h1>Local product</h1>")
        self.write("product/web/app.js", b"/* local */")
        self.write("product/web/styles.css", b"body{}")
        self.write("product/web/broadcast.css", b"/* retro */")
        self.write("product/web/atmosphere.js", b"/* points */")
        self.write("product/web/arcade.css", b"/* arcade */")
        self.write("product/web/arcade.js", b"/* pixels */")
        self.write("product/web/assets/grain.svg", b"<svg/>")
        self.write("product/web/assets/fonts/OFL.txt", b"SIL OPEN FONT LICENSE")
        self.write("product/web/assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2", b"font")
        for name, value in (("index.html", b"<h1>Court experiment</h1>"),
                            ("lab.css", b"body{}"), ("lab.js", b"/* local court */"),
                            ("viewer.js", b"/* temporal coordinates */"),
                            ("flagg.json", b'{"schema":"court-lab-v1"}')):
            self.write("product/court-lab/" + name, value)
        self.write("data/reference/frames/flagg-16.5s.jpg", b"frame")
        self.write(SOURCES["flagg"], MEDIA)
        self.write(f"product/build/verified/{JOB}/enhanced.mp4", MEDIA)
        self.manifest = {"stories": [{"sample": "flagg", "sourceVideo": "/samples/flagg.mp4",
            "sourceVideoSha256": SHA, "showcaseJobId": JOB, "showcaseOutputSha256": SHA,
            "enhancedVideo": "https://old.invalid/enhanced.mp4", "analysisUrl": "https://old.invalid/analysis.json"}]}
        self.analysis = {"protocol_version": "product-story-v1", "preservesSourceTimeline": True,
                         "trace": [{"tool": "inspect_frames", "result": {"sourceUrl": "https://real.source/frame"}}]}
        self.report = {"contentReview": {"acceptedForShowcase": True}, "jobId": JOB, "sample": "flagg",
            "mode": "story", "outputSha256": SHA, "analysis": self.analysis,
            "elapsedSeconds": 62.81, "verifiedAt": "2026-10-07T12:02:10+00:00",
            "videoUrl": "https://old.invalid/enhanced.mp4", "analysisUrl": "https://old.invalid/analysis.json"}
        self.save_json("product/data/stories.json", self.manifest)
        self.save_json(f"product/evidence/run-{JOB}.json", self.report)
        self.catalog = Catalog(self.root)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), handler_for(self.catalog))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()
        self.temp.cleanup()

    def write(self, name, value):
        file = self.root / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(value)

    def save_json(self, name, value):
        self.write(name, json.dumps(value).encode())

    def request(self, path, method="GET", headers=None):
        connection = HTTPConnection("127.0.0.1", self.server.server_port, timeout=2)
        # Old preview proxied via urllib. This regression guard forbids that path.
        with patch("urllib.request.urlopen", side_effect=AssertionError("No cloud calls allowed")):
            connection.request(method, path, headers=headers or {})
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_manifest_uses_local_media_without_mutating_original_records(self):
        status, _, body = self.request("/product/data/stories.json")
        self.assertEqual(status, 200)
        story = json.loads(body)["stories"][0]
        self.assertEqual(story["enhancedVideo"], f"/product/outputs/{JOB}/enhanced.mp4")
        self.assertEqual(json.loads((self.root / "product/data/stories.json").read_text()), self.manifest)
        status, _, body = self.request(f"/api/jobs/{JOB}")
        job = json.loads(body)
        self.assertEqual(status, 200)
        self.assertTrue(job["preview"]["historical"])
        self.assertTrue(job["preservesSourceTimeline"])
        self.assertEqual(job["analysis"], self.analysis)
        self.assertEqual(job["preview"]["originalVideoUrl"], self.report["videoUrl"])
        self.assertEqual(json.loads(self.request(f"/product/outputs/{JOB}/analysis.json")[2]), self.analysis)

    def test_entry_aliases_keep_relative_assets_under_product(self):
        for path in ("/", "/product"):
            status, headers, body = self.request(path + "?story=amen")
            self.assertEqual(status, 301)
            self.assertEqual(headers["Location"], "/product/?story=amen")
            self.assertEqual(body, b"")
        self.assertEqual(self.request("/product/")[0], 200)
        self.assertEqual(self.request("/product/styles.css")[0], 200)

    def test_offline_status_and_post_never_create_jobs(self):
        status, _, body = self.request("/api/status")
        data = json.loads(body)
        self.assertEqual(status, 200)
        self.assertFalse(data["ready"])
        self.assertEqual(data["modes"], [])
        before = copy.deepcopy(self.catalog.jobs)
        status, _, body = self.request("/api/jobs", "POST")
        self.assertEqual(status, 503)
        self.assertEqual(json.loads(body)["error"], "offline_preview")
        self.assertEqual(before, self.catalog.jobs)
        self.assertEqual(self.request("/api/jobs/unknown")[0], 404)

    def test_visual_assets_are_local_and_have_browser_mime_types(self):
        for name, mime, expected in (
            ("broadcast.css", "text/css", b"/* retro */"),
            ("atmosphere.js", "text/javascript", b"/* points */"),
            ("arcade.css", "text/css", b"/* arcade */"),
            ("arcade.js", "text/javascript", b"/* pixels */"),
            ("assets/grain.svg", "image/svg+xml", b"<svg/>"),
            ("assets/fonts/OFL.txt", "text/plain", b"SIL OPEN FONT LICENSE"),
            ("assets/fonts/fusion-pixel-12px-monospaced-zh_hans.otf.woff2", "font/woff2", b"font"),
        ):
            with self.subTest(name=name):
                status, headers, body = self.request("/product/" + name)
                self.assertEqual(status, 200)
                self.assertEqual(headers["Content-Type"].split(";")[0], mime)
                self.assertEqual(body, expected)

    def test_court_experiment_serves_only_named_local_assets(self):
        status, headers, body = self.request("/product/court-lab?view=half")
        self.assertEqual(status, 301)
        self.assertEqual(headers["Location"], "/product/court-lab/?view=half")
        self.assertEqual(body, b"")
        self.assertEqual(self.request("/product/court-lab/")[0], 200)
        for name, mime in (("index.html", "text/html"), ("lab.css", "text/css"),
                           ("lab.js", "text/javascript"), ("viewer.js", "text/javascript"),
                           ("flagg.json", "application/json")):
            status, headers, _ = self.request("/product/court-lab/" + name)
            self.assertEqual(status, 200)
            self.assertEqual(headers["Content-Type"].split(";")[0], mime)
        self.write("product/court-lab/generate.py", b"not public")
        self.write("product/court-lab/imported.json", b"not public")
        for name in ("generate.py", "imported.json", "../.env"):
            self.assertEqual(self.request("/product/court-lab/" + name)[0], 404)

    def test_original_and_enhanced_have_byte_exact_seekable_ranges(self):
        for path in ("/samples/flagg.mp4", f"/product/outputs/{JOB}/enhanced.mp4"):
            for value, start, end in (("bytes=10-19", 10, 19), ("bytes=-7", len(MEDIA)-7, len(MEDIA)-1),
                                      ("bytes=170-", 170, len(MEDIA)-1), ("bytes=0-9999", 0, len(MEDIA)-1)):
                with self.subTest(path=path, value=value):
                    status, headers, body = self.request(path, headers={"Range": value})
                    self.assertEqual(status, 206)
                    self.assertEqual(body, MEDIA[start:end+1])
                    self.assertEqual(headers["Content-Range"], f"bytes {start}-{end}/{len(MEDIA)}")
                    self.assertEqual(headers["Content-Type"], "video/mp4")
                    self.assertEqual(int(headers["Content-Length"]), len(body))

    def test_invalid_ranges_are_bounded_and_return_416(self):
        for value in ("bytes=9999-", "bytes=10-9", "bytes=-0", "bytes=-", "bytes=0-1,3-4", "garbage"):
            with self.subTest(value=value):
                status, headers, body = self.request("/samples/flagg.mp4", headers={"Range": value})
                self.assertEqual(status, 416)
                self.assertEqual(headers["Content-Range"], f"bytes */{len(MEDIA)}")
                self.assertEqual(body, b"")

    def test_head_does_not_send_video_body(self):
        status, headers, body = self.request("/samples/flagg.mp4", "HEAD", {"Range": "bytes=10-19"})
        self.assertEqual(status, 200)
        self.assertEqual(int(headers["Content-Length"]), len(MEDIA))
        self.assertEqual(body, b"")

    def test_unknown_paths_traversal_and_directory_listing_never_expose_repo(self):
        self.write(".env", b"private")
        for path in ("/.env", "/product/data/", "/product/data/event-bindings.json", "/product/../.env",
                     "/product/%2e%2e/.env", "/frames/", "/product/outputs/" + "b"*32 + "/enhanced.mp4"):
            with self.subTest(path=path):
                status, _, body = self.request(path)
                self.assertEqual(status, 404)
                self.assertNotIn(b"private", body)

    def test_symlink_replacement_after_start_is_not_followed(self):
        file = self.root / "product/web/app.js"
        file.unlink()
        self.write(".env", b"private")
        file.symlink_to(self.root / ".env")
        self.assertEqual(self.request("/product/app.js")[0], 404)
        self.assertNotIn("/product/app.js", Catalog(self.root).files)

    def test_corrupt_media_is_not_promoted_or_served(self):
        self.write(f"product/build/verified/{JOB}/enhanced.mp4", b"corrupt")
        catalog = Catalog(self.root)
        self.assertFalse(catalog.jobs)
        self.assertIsNone(catalog.manifest["stories"][0]["enhancedVideo"])
        self.assertNotIn(f"/product/outputs/{JOB}/enhanced.mp4", catalog.files)
        self.assertTrue(catalog.issues)

    def test_content_rejected_output_is_not_available_as_history(self):
        self.report["contentReview"]["acceptedForShowcase"] = False
        self.save_json(f"product/evidence/run-{JOB}.json", self.report)
        catalog = Catalog(self.root)
        self.assertFalse(catalog.jobs)
        self.assertIsNone(catalog.manifest["stories"][0]["enhancedVideo"])

    def test_missing_original_warns_without_exposing_another_file(self):
        (self.root / SOURCES["flagg"]).unlink()
        catalog = Catalog(self.root)
        self.assertIsNone(catalog.manifest["stories"][0]["sourceVideo"])
        self.assertNotIn("/samples/flagg.mp4", catalog.files)
        self.assertTrue(catalog.jobs)
        self.assertTrue(catalog.status()["preview"]["issues"])


    def test_watch_serves_only_runtime_and_shared_verified_records(self):
        for name in ('index.html', 'app.js', 'glass/optics-model.js'):
            self.write('product/watch/' + name, b'watch-runtime')
        self.write('product/watch/preview.py', b'private')
        self.write('product/watch/dev/references/private.png', b'private')
        catalog = Catalog(self.root)
        self.server.RequestHandlerClass = handler_for(catalog)
        self.assertEqual(self.request('/product/watch/')[0], 200)
        self.assertEqual(self.request('/product/watch/glass/optics-model.js')[2], b'watch-runtime')
        for name in ('preview.py', 'dev/references/private.png'):
            self.assertEqual(self.request('/product/watch/' + name)[0], 404)
        status, _, body = self.request('/product/watch/data/stories.json')
        self.assertEqual(status, 200)
        self.assertEqual(json.loads(body), catalog.manifest)
        records = json.loads(self.request('/product/watch/data/history.json')[2])['records']
        self.assertEqual(records[0]['jobId'], JOB)
        self.assertEqual(records[0]['contentReview'], self.report['contentReview'])
        self.assertEqual(records[0]['analysis'], self.report['analysis'])

    def test_watch_symlink_is_not_served(self):
        self.write('product/watch/app.js', b'watch-runtime')
        self.write('.env', b'private')
        file = self.root / 'product/watch/app.js'
        catalog = Catalog(self.root)
        self.server.RequestHandlerClass = handler_for(catalog)
        file.unlink()
        file.symlink_to(self.root / '.env')
        self.assertEqual(self.request('/product/watch/app.js')[0], 404)


if __name__ == "__main__":
    unittest.main()
