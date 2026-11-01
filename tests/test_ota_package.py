import tempfile
import unittest
import zipfile
from pathlib import Path

from job.compilation_tasks import _save_firmware_artifact


class OtaPackageTest(unittest.TestCase):
    def test_ota_package_contains_first_flash_and_update_images(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            output = root / "output"
            build.mkdir()
            output.mkdir()
            (build / "firmware.bin").write_bytes(b"complete-image")
            (build / "micropython.bin").write_bytes(b"application-image")

            artifact = _save_firmware_artifact(build, output, "OTA")

            self.assertEqual("firmware-ota-package.zip", artifact.name)
            with zipfile.ZipFile(artifact) as archive:
                self.assertEqual(
                    {"firmware.bin", "ota-application.bin", "OTA流程说明.txt"},
                    set(archive.namelist()),
                )
                self.assertEqual(b"application-image", archive.read("ota-application.bin"))
                readme = archive.read("OTA流程说明.txt").decode("utf-8")
                self.assertIn("不要把 firmware.bin 整包写进 OTA 应用分区", readme)

    def test_standard_variant_still_returns_firmware_bin(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            output = root / "output"
            build.mkdir()
            output.mkdir()
            (build / "firmware.bin").write_bytes(b"complete-image")

            artifact = _save_firmware_artifact(build, output, "")

            self.assertEqual("firmware.bin", artifact.name)
            self.assertEqual(b"complete-image", artifact.read_bytes())


if __name__ == "__main__":
    unittest.main()
