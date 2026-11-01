import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class WebTemplateRegressionTest(unittest.TestCase):
    def test_queue_progress_is_keyed_by_task_id(self):
        template = (ROOT / "templates" / "firmwareWaitCompiled.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("progressById", template)
        self.assertIn("this.$set(this.progressById, id, progress)", template)
        self.assertIn("refreshProgressFallback", template)
        self.assertNotIn("this.$set(row, 'progress', progress)", template)

    def test_code_block_overrides_inline_code_background(self):
        template = (ROOT / "templates" / "variantHelp.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("pre code {", template)
        self.assertIn("background: transparent", template)
        self.assertIn("{{ ota_updater_code }}", template)


if __name__ == "__main__":
    unittest.main()
