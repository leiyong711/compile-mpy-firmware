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
                "variants": {"SPIRAM": "SPIRAM"},
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

    def tearDown(self):
        self.temporary.cleanup()

    def test_discovers_only_real_boards_and_new_chip_families(self):
        options = discover_build_options(self.root)
        devices = {item["value"]: item for item in options["devices"]}
        self.assertEqual({"ESP8266", "ESP32", "ESP32_C6"}, set(devices))
        self.assertEqual([], devices["ESP8266"]["boards"][0]["variants"])

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
            / "sdkconfig.board"
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


if __name__ == "__main__":
    unittest.main()

