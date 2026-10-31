import os
import unittest
from unittest.mock import patch

from job.compilation_tasks import _shell_environment


class CompilationEnvironmentTest(unittest.TestCase):
    def test_esp8266_fallback_contains_sdk_warnings_and_esptool(self):
        with patch.dict(os.environ, {}, clear=True):
            command = _shell_environment("ESP8266")

        self.assertIn("ESP_SDK=", command)
        self.assertIn("CFLAGS_EXTRA=-Wno-error", command)
        self.assertIn("idf5.0_py3.9_env/bin", command)
        self.assertIn("esp-open-sdk/xtensa-lx106-elf/bin", command)


if __name__ == "__main__":
    unittest.main()
