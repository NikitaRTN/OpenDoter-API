import bz2
from pathlib import Path
import tempfile
import unittest
import zstandard
from server_modules.replays import ReplayDecodeError, unpack_replay

DEMO = b"PBDEMS2\x00" + bytes(range(256)) * 1000


class ReplayTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.archive = Path(self.temp.name) / "match.dem.bz2"
        self.target = Path(self.temp.name) / "match.dem"

    def decode(self, payload):
        self.archive.write_bytes(payload)
        unpack_replay(self.archive, self.target)
        self.assertEqual(self.target.read_bytes(), DEMO)
        self.assertFalse(self.target.with_suffix(".dem.tmp").exists())

    def assert_invalid(self, payload):
        self.archive.write_bytes(payload)
        self.target.write_bytes(b"existing-good-file")
        with self.assertRaises(ReplayDecodeError):
            unpack_replay(self.archive, self.target)
        self.assertEqual(self.target.read_bytes(), b"existing-good-file")
        self.assertEqual(self.archive.read_bytes(), payload)
        self.assertFalse(self.target.with_suffix(".dem.tmp").exists())

    def test_bzip2(self):
        self.decode(bz2.compress(DEMO))

    def test_zstandard_with_bz2_extension(self):
        self.decode(zstandard.ZstdCompressor().compress(DEMO))

    def test_zstandard_unknown_content_size(self):
        self.decode(zstandard.ZstdCompressor(write_content_size=False).compress(DEMO))

    def test_zstandard_multiple_frames(self):
        compressor = zstandard.ZstdCompressor()
        self.decode(compressor.compress(DEMO[:2000]) + compressor.compress(DEMO[2000:]))

    def test_uncompressed_demo(self):
        self.decode(DEMO)

    def test_truncated_zstandard(self):
        self.assert_invalid(zstandard.ZstdCompressor().compress(DEMO)[:-4])

    def test_truncated_bzip2(self):
        self.assert_invalid(bz2.compress(DEMO)[:-4])

    def test_html_response(self):
        self.assert_invalid(b"<html>Replay unavailable</html>")

    def test_compressed_non_demo(self):
        self.assert_invalid(zstandard.ZstdCompressor().compress(b"<html>Error</html>"))


if __name__ == "__main__":
    unittest.main()
