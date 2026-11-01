import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.v1.firmware import api
from app.v1.firmware.db_model import (
    Base,
    FirmwareBuildProgress,
    FirmwareWaitCompiled,
)
from utils.exception_handling import UnicornException


class TaskActionApiTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        engine = create_engine(
            "sqlite:///{}".format(self.root / "test.db"),
            connect_args={"check_same_thread": False},
        )
        Base.metadata.create_all(engine)
        self.session = sessionmaker(bind=engine)()
        self.upload_dir = self.root / "res_pack" / "upload"
        self.upload_dir.mkdir(parents=True)

    def tearDown(self):
        self.session.close()
        self.temporary.cleanup()

    def _add_task(self, task_id=1, status=1):
        archive = self.upload_dir / f"task-{task_id}.zip"
        archive.write_bytes(b"source")
        task = FirmwareWaitCompiled(
            id=task_id,
            email="retry@example.com",
            device_type="ESP32_C3",
            flash_size="AUTO",
            board="ESP32_GENERIC_C3",
            board_variant="OTA",
            custom_source_code_file_path=f"/res_pack/upload/{archive.name}",
            status=status,
            err_log="old error",
        )
        self.session.add(task)
        self.session.add(
            FirmwareBuildProgress(
                task_id=task_id,
                percentage=100,
                stage="failed",
                message="old error",
                status="failed",
            )
        )
        self.session.commit()
        return task, archive

    def test_retry_requeues_failed_task_when_source_exists(self):
        task, archive = self._add_task()
        with patch.object(api, "RUNTIME_PATH", str(self.root)), patch.object(
            api, "set_progress"
        ) as set_progress:
            result = asyncio.run(api.retry_compilation_task(task.id, self.session))
        self.session.refresh(task)
        self.assertEqual(2000, result["code"])
        self.assertEqual(3, task.status)
        self.assertIsNone(task.err_log)
        self.assertTrue(archive.is_file())
        set_progress.assert_called_once_with(
            task.id, 0, "queued", "用户已重试，任务正在排队", status="queued"
        )

    def test_retry_rejects_missing_source(self):
        task, archive = self._add_task()
        archive.unlink()
        with patch.object(api, "RUNTIME_PATH", str(self.root)):
            with self.assertRaises(UnicornException):
                asyncio.run(api.retry_compilation_task(task.id, self.session))

    def test_delete_removes_task_progress_and_source(self):
        task, archive = self._add_task()
        task_id = task.id
        with patch.object(api, "RUNTIME_PATH", str(self.root)):
            result = asyncio.run(api.delete_compilation_task(task_id, self.session))
        self.assertEqual(2000, result["code"])
        self.assertIsNone(
            self.session.query(FirmwareWaitCompiled).filter_by(id=task_id).first()
        )
        self.assertIsNone(
            self.session.query(FirmwareBuildProgress).filter_by(task_id=task_id).first()
        )
        self.assertFalse(archive.exists())

    def test_delete_rejects_running_task(self):
        task, archive = self._add_task(status=2)
        with patch.object(api, "RUNTIME_PATH", str(self.root)):
            with self.assertRaises(UnicornException):
                asyncio.run(api.delete_compilation_task(task.id, self.session))
        self.assertTrue(archive.exists())


if __name__ == "__main__":
    unittest.main()
