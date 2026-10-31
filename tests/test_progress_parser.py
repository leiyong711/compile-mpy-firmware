import unittest
from unittest.mock import patch

from job.build_progress import BuildOutputParser


class ProgressParserTest(unittest.TestCase):
    @patch("job.build_progress.set_progress")
    def test_esp32_uses_ninja_fraction(self, update):
        parser = BuildOutputParser(12, "ESP32")
        parser.feed("[50/100] Building C object")
        args = update.call_args.args
        self.assertEqual(12, args[0])
        self.assertEqual(52, args[1])
        self.assertEqual(50, update.call_args.kwargs["current_step"])
        self.assertEqual(100, update.call_args.kwargs["total_steps"])

    @patch("job.build_progress.set_progress")
    def test_esp32_ignores_nested_bootloader_ninja(self, update):
        parser = BuildOutputParser(12, "ESP32")
        parser.feed("[400/1200] Building main firmware")
        parser.feed("[20/100] Building nested bootloader")
        parser.feed("[420/1200] Building main firmware")
        percentages = [call.args[1] for call in update.call_args_list]
        self.assertEqual(sorted(percentages), percentages)
        self.assertEqual(2, update.call_count)
        self.assertEqual(420, update.call_args.kwargs["current_step"])

    @patch("job.build_progress.set_progress")
    def test_esp8266_counts_real_make_actions(self, update):
        parser = BuildOutputParser(13, "ESP8266", total_steps=4)
        parser.feed("CC ../../py/runtime.c")
        parser.feed("一条普通日志")
        parser.feed("LINK build/firmware.elf")
        self.assertEqual(2, update.call_args.kwargs["current_step"])
        self.assertEqual(4, update.call_args.kwargs["total_steps"])


if __name__ == "__main__":
    unittest.main()
