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

    def test_queue_has_retry_and_delete_actions(self):
        template = (ROOT / "templates" / "firmwareWaitCompiled.html").read_text(
            encoding="utf-8"
        )
        self.assertIn("retryTask(scope.row)", template)
        self.assertIn("deleteTask(scope.row)", template)
        self.assertIn("/api/tasks/${row.id}/retry", template)
        self.assertIn("axios.delete(`/api/tasks/${row.id}`)", template)
        self.assertIn("编译中不可删除", template)
        self.assertIn("编译失败，点击“错误详情”查看原因", template)


if __name__ == "__main__":
    unittest.main()
