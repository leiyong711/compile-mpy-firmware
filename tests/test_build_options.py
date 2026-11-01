import json
import tempfile
import unittest
from pathlib import Path

from app.v1.firmware.build_options import (
    discover_build_options,
    normalize_device_type,
    normalize_flash_size,
    validate_selection,
)


class BuildOptionsTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        fixtures = {
            "esp8266/ESP8266_GENERIC": {
                "mcu": "esp8266",
                "product": "Generic ESP8266",
                "variants": {"FLASH_1M": "1 MiB"},
            },
            "esp32/ESP32_GENERIC": {
                "mcu": "esp32",
                "product": "ESP32 / WROOM",
                "variants": {"SPIRAM": "SPIRAM", "OTA": "OTA"},
            },
            "esp32/ESP32_GENERIC_C3": {
                "mcu": "esp32c3",
                "product": "ESP32-C3",
            },
            "esp32/ESP32_GENERIC_C6": {
                "mcu": "esp32c6",
                "product": "ESP32-C6",
            },
        }
        for relative, metadata in fixtures.items():
            port, board = relative.split("/")
            board_dir = self.root / "ports" / port / "boards" / board
            board_dir.mkdir(parents=True)
            (board_dir / "board.json").write_text(json.dumps(metadata), encoding="utf-8")
            (board_dir / "mpconfigboard.h").write_text("// test\n", encoding="utf-8")
            (board_dir / "mpconfigboard.cmake").write_text(
                "set(SDKCONFIG_DEFAULTS boards/sdkconfig.base)\n",
                encoding="utf-8",
            )

    def tearDown(self):
        self.temporary.cleanup()

    def test_discovers_only_real_boards_and_new_chip_families(self):
        options = discover_build_options(self.root)
        devices = {item["value"]: item for item in options["devices"]}
        self.assertEqual({"ESP8266", "ESP32", "ESP32_C3", "ESP32_C6"}, set(devices))
        self.assertEqual([], devices["ESP8266"]["boards"][0]["variants"])
        variant = devices["ESP32"]["boards"][0]["variants"][0]
        self.assertEqual("SPIRAM", variant["value"])
        self.assertIn("外部内存", variant["guidance"]["name"])
        self.assertIn("标准版", variant["guidance"]["beginner_choice"])
        c3_variant = devices["ESP32_C3"]["boards"][0]["variants"][0]
        self.assertEqual("OTA", c3_variant["value"])
        self.assertTrue(c3_variant["platform_extension"])
        self.assertIn("至少有 4MiB Flash", c3_variant["guidance"]["warning"])

    def test_normalizes_legacy_values(self):
        self.assertEqual("ESP32", normalize_device_type("ESP32_S"))
        self.assertEqual("2MB", normalize_flash_size("2M"))

    def test_flash_size_changes_the_effective_board(self):
        selection = validate_selection(
            "ESP32", "8MB", micropython_dir=self.root, prepare_board=True
        )
        self.assertEqual("WEB_ESP32_GENERIC_8M", selection.effective_board)
        config = (
            self.root
            / "ports"
            / "esp32"
            / "boards"
            / selection.effective_board
            / "sdkconfig.web"
        ).read_text(encoding="utf-8")
        self.assertIn("CONFIG_ESPTOOLPY_FLASHSIZE_8MB=y", config)
        self.assertIn('partitions-8MiB.csv', config)

    def test_variant_and_explicit_flash_cannot_conflict(self):
        with self.assertRaisesRegex(ValueError, "Flash"):
            validate_selection(
                "ESP32",
                "8MB",
                board_variant="SPIRAM",
                micropython_dir=self.root,
            )

    def test_c3_platform_ota_generates_real_board_config(self):
        selection = validate_selection(
            "ESP32_C3",
            "AUTO",
            board="ESP32_GENERIC_C3",
            board_variant="OTA",
            micropython_dir=self.root,
            prepare_board=True,
        )
        self.assertEqual("WEB_ESP32_GENERIC_C3_OTA", selection.effective_board)
        self.assertEqual("", selection.effective_variant)
        config = (
            self.root
            / "ports"
            / "esp32"
            / "boards"
            / selection.effective_board
            / "sdkconfig.web"
        ).read_text(encoding="utf-8")
        self.assertIn('partitions-4MiB-ota-c3.csv', config)
        self.assertIn("CONFIG_COMPILER_OPTIMIZATION_SIZE=y", config)
        self.assertIn("CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y", config)
        cmake = (
            self.root
            / "ports"
            / "esp32"
            / "boards"
            / selection.effective_board
            / "mpconfigboard.cmake"
        ).read_text(encoding="utf-8")
        self.assertIn("${MICROPY_BOARD_DIR}/sdkconfig.web", cmake)
        partition_table = (
            self.root / "ports" / "esp32" / "partitions-4MiB-ota-c3.csv"
        ).read_text(encoding="utf-8")
        self.assertIn("0x1a0000", partition_table)
        self.assertIn("0x0b0000", partition_table)

    def test_native_ota_variant_enables_bootloader_rollback(self):
        source = self.root / "ports" / "esp32" / "boards" / "ESP32_GENERIC"
        (source / "sdkconfig.ota").write_text(
            'CONFIG_PARTITION_TABLE_CUSTOM_FILENAME="partitions-4MiB-ota.csv"\n',
            encoding="utf-8",
        )
        selection = validate_selection(
            "ESP32",
            "AUTO",
            board="ESP32_GENERIC",
            board_variant="OTA",
            micropython_dir=self.root,
            prepare_board=True,
        )
        self.assertEqual("WEB_ESP32_GENERIC_OTA", selection.effective_board)
        self.assertEqual("OTA", selection.effective_variant)
        config = (
            self.root
            / "ports"
            / "esp32"
            / "boards"
            / selection.effective_board
            / "sdkconfig.web"
        ).read_text(encoding="utf-8")
        self.assertIn("CONFIG_BOOTLOADER_APP_ROLLBACK_ENABLE=y", config)
        cmake = (
            self.root
            / "ports"
            / "esp32"
            / "boards"
            / selection.effective_board
            / "mpconfigboard.cmake"
        ).read_text(encoding="utf-8")
        self.assertIn("${MICROPY_BOARD_DIR}/sdkconfig.web", cmake)


if __name__ == "__main__":
    unittest.main()

