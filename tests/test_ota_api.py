import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from app.v1.firmware import api
from utils.exception_handling import UnicornException


class OtaApiTest(unittest.TestCase):
    def test_reads_application_and_computes_sha256(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package_path = root / "firmware-ota-package.zip"
            with zipfile.ZipFile(package_path, "w") as package:
                package.writestr("ota-application.bin", b"ota-image")
            firmware = SimpleNamespace(
                board_variant="OTA",
                firmware_file_path="/firmware-ota-package.zip",
            )
            with patch.object(api, "RUNTIME_PATH", str(root)):
                application, sha256 = api._read_ota_application(firmware)
            self.assertEqual(b"ota-image", application)
            self.assertEqual(
                "bac0d8034e82f5f02fcb5275251e13b0f5d70bb878006650c79d03ffd72e5ed3",
                sha256,
            )

    def test_rejects_non_ota_record(self):
        firmware = SimpleNamespace(board_variant="", firmware_file_path="/firmware.bin")
        with self.assertRaises(UnicornException):
            api._read_ota_application(firmware)


if __name__ == "__main__":
    unittest.main()
