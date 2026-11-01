import tempfile
import unittest
import zipfile
from pathlib import Path
from types import SimpleNamespace

from job.compilation_tasks import _ota_partition_capacity, _save_firmware_artifact


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

            artifact = _save_firmware_artifact(
                build, output, "OTA", ota_partition_size=1024
            )

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

    def test_rejects_application_larger_than_ota_partition(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            build = root / "build"
            output = root / "output"
            build.mkdir()
            output.mkdir()
            (build / "firmware.bin").write_bytes(b"complete-image")
            (build / "micropython.bin").write_bytes(b"12345")

            with self.assertRaisesRegex(RuntimeError, "超出分区容量"):
                _save_firmware_artifact(
                    build, output, "OTA", ota_partition_size=4
                )

    def test_reads_capacity_from_effective_web_partition_config(self):
        with tempfile.TemporaryDirectory() as temporary:
            port = Path(temporary)
            board = port / "boards" / "WEB_ESP32_GENERIC_C3_OTA"
            board.mkdir(parents=True)
            (board / "sdkconfig.web").write_text(
                'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-c3.csv"\n',
                encoding="utf-8",
            )
            (port / "partitions-c3.csv").write_text(
                "ota_0,app,ota_0,0x10000,0x1a0000,\n"
                "ota_1,app,ota_1,0x1b0000,0x1a0000,\n",
                encoding="utf-8",
            )
            selection = SimpleNamespace(
                effective_board="WEB_ESP32_GENERIC_C3_OTA",
                effective_variant="",
            )
            self.assertEqual(0x1A0000, _ota_partition_capacity(port, selection))


if __name__ == "__main__":
    unittest.main()
