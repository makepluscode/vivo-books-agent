"""웹 데모가 동봉한 심사 자료를 API 호출 없이 보여주는지 확인해요."""
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from drift import web


class PackagedSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.empty = tempfile.TemporaryDirectory()
        patches = [mock.patch.object(web, "LIVING_OUT", Path(self.empty.name)),
                   mock.patch.object(web, "PACKAGED_ONLY", False)]
        for patch in patches:
            patch.start()
            self.addCleanup(patch.stop)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), web.H)
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.addCleanup(self.server.server_close)
        self.addCleanup(self.server.shutdown)
        self.addCleanup(self.empty.cleanup)
        self.base = f"http://127.0.0.1:{self.server.server_port}"

    def get(self, path):
        with urllib.request.urlopen(self.base + path) as res:
            return res.status, res.headers["Content-Type"], res.read()

    def snapshot(self):
        return json.loads(self.get("/api/living/snapshot")[2])

    def test_falls_back_to_packaged_evidence_without_local_runs(self):
        data = self.snapshot()
        self.assertTrue(data["recorded"])
        self.assertEqual(data["reader"], "/living-out/packaged/reader.html")
        packaged = json.loads((web.DEMO_SNAPSHOT / "revision.json").read_text())
        self.assertEqual(data["result"]["trace"], packaged["trace"])
        for key, ctype in (("reader", "text/html"), ("epub", "application/epub+zip"), ("diff", "text/plain")):
            status, got, body = self.get(data[key])
            self.assertEqual(status, 200)
            self.assertTrue(got.startswith(ctype))
            self.assertTrue(body)

    def test_local_run_wins_unless_packaged_only(self):
        run = Path(self.empty.name) / "demo"
        run.mkdir()
        (run / "revision.json").write_text(json.dumps({"preview_created": False, "trace": []}))
        self.assertEqual(self.snapshot()["reader"], "/living-out/demo/reader.html")
        with mock.patch.object(web, "PACKAGED_ONLY", True):
            self.assertEqual(self.snapshot()["reader"], "/living-out/packaged/reader.html")

    def test_packaged_route_serves_only_listed_files(self):
        for path in ("/living-out/packaged/pr.md", "/living-out/packaged/../../README.md",
                     "/living-out/../demo/snapshot/revision.json"):
            with self.subTest(path=path), self.assertRaises(urllib.error.HTTPError) as caught:
                self.get(path)
            self.assertEqual(caught.exception.code, 404)
            caught.exception.close()


if __name__ == "__main__":
    unittest.main()
