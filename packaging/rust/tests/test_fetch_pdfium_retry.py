"""Offline fail-closed tests for pinned native PDFium release downloads."""

from __future__ import annotations

import hashlib
import importlib.util
import io
from pathlib import Path
import tarfile
import tempfile
import unittest
from unittest.mock import patch
from urllib.error import HTTPError, URLError


MODULE_PATH = Path(__file__).resolve().parents[1] / "fetch-pdfium.py"
SPEC = importlib.util.spec_from_file_location("verified_pdfium_fetch", MODULE_PATH)
assert SPEC is not None and SPEC.loader is not None
fetcher = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(fetcher)


class Response(io.BytesIO):
    def __init__(self, data: bytes, url: str) -> None:
        super().__init__(data)
        self._url = url

    def geturl(self) -> str:
        return self._url


def archived_library() -> bytes:
    output = io.BytesIO()
    with tarfile.open(fileobj=output, mode="w:gz") as archive:
        payload = b"not-a-real-library-but-exact-test-content"
        entry = tarfile.TarInfo("lib/libpdfium.dylib")
        entry.size = len(payload)
        entry.mode = 0o644
        archive.addfile(entry, io.BytesIO(payload))
    return output.getvalue()


class PdfiumDownloadTests(unittest.TestCase):
    def test_transient_errors_retry_with_full_hash_and_no_partial_extract(self) -> None:
        archive = archived_library()
        expected = hashlib.sha256(archive).hexdigest()
        origin = (
            "https://github.com/firecrawl/pdfium-rs/releases/download/"
            "native-v7988/firecrawl-pdfium-mac-x64.tgz"
        )
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(
                fetcher,
                "urlopen",
                side_effect=[URLError("temporary timeout"), TimeoutError("tls"), Response(archive, origin)],
            ) as request, patch.object(fetcher.time, "sleep") as sleep:
                fetcher.fetch("macos-x64", expected, Path(temporary) / "install")
            self.assertEqual(request.call_count, 3)
            self.assertEqual([call.args[0] for call in sleep.call_args_list], [1, 2])
            installed = Path(temporary) / "install/lib/libpdfium.dylib"
            self.assertEqual(installed.read_bytes(), b"not-a-real-library-but-exact-test-content")

    def test_hash_mismatch_is_terminal_not_a_retry(self) -> None:
        archive = archived_library()
        origin = (
            "https://github.com/firecrawl/pdfium-rs/releases/download/"
            "native-v7988/firecrawl-pdfium-mac-x64.tgz"
        )
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(fetcher, "urlopen", return_value=Response(archive, origin)) as request:
                with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                    fetcher.fetch("macos-x64", "0" * 64, Path(temporary) / "install")
            self.assertEqual(request.call_count, 1)
            self.assertFalse((Path(temporary) / "install/lib").exists())

    def test_untrusted_redirect_is_terminal(self) -> None:
        archive = archived_library()
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(
                fetcher,
                "urlopen",
                return_value=Response(archive, "https://unexpected.example/private-file"),
            ) as request:
                with self.assertRaisesRegex(ValueError, "Unexpected PDFium download redirect"):
                    fetcher.fetch(
                        "macos-x64", hashlib.sha256(archive).hexdigest(), Path(temporary) / "install"
                    )
            self.assertEqual(request.call_count, 1)

    def test_auth_or_missing_asset_fails_immediately(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(
                fetcher,
                "urlopen",
                side_effect=HTTPError("https://github.com/", 404, "not found", {}, None),
            ) as request, patch.object(fetcher.time, "sleep") as sleep:
                with self.assertRaises(HTTPError):
                    fetcher.fetch("macos-x64", "a" * 64, Path(temporary) / "install")
            self.assertEqual(request.call_count, 1)
            sleep.assert_not_called()


if __name__ == "__main__":
    unittest.main()
