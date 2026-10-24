"""Recording failures must retry file I/O without replaying model/business work."""
import json
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

from run_d07 import atomic_write_text, retry_file_operation, write


class D07RecordingTests(unittest.TestCase):
    def setUp(self):
        temporary = TemporaryDirectory(dir=Path(__file__).resolve().parent)
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)

    def test_transient_sharing_error_retries_replace_and_keeps_valid_json(self):
        path = self.root / "events.json"
        path.write_text('{"old": true}', encoding="utf-8")
        original = Path.replace
        attempts = []

        def occupied_then_available(source, target):
            attempts.append(source)
            self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
            if len(attempts) < 3:
                raise PermissionError("simulated Windows file sharing violation")
            return original(source, target)

        with patch.object(Path, "replace", occupied_then_available), patch("run_d07.sleep") as sleep:
            write(path, {"new": [1, 2, 3]})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"new": [1, 2, 3]})
        self.assertEqual(len(attempts), 3)
        self.assertEqual(sleep.call_count, 2)
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_permanent_denial_propagates_and_preserves_previous_record(self):
        path = self.root / "events.json"
        path.write_text('{"old": true}', encoding="utf-8")
        with patch.object(Path, "replace", side_effect=PermissionError("permanent denial")), \
                patch("run_d07.monotonic", side_effect=[0, 0, 4]):
            with self.assertRaises(PermissionError):
                write(path, {"new": True})
        self.assertEqual(json.loads(path.read_text(encoding="utf-8")), {"old": True})
        self.assertFalse(list(self.root.glob("*.tmp")))

    def test_non_permission_error_is_not_retried(self):
        operation = Mock(side_effect=OSError("disk full"))
        with patch("run_d07.sleep") as sleep:
            with self.assertRaises(OSError):
                retry_file_operation(operation)
        operation.assert_called_once()
        sleep.assert_not_called()

    def test_html_writer_also_retries_and_uses_new_staging_file(self):
        path = self.root / "report.html"
        original = Path.replace
        sources = []

        def replace(source, target):
            sources.append(source)
            return original(source, target)

        with patch.object(Path, "replace", replace):
            atomic_write_text(path, "first")
            atomic_write_text(path, "second")
        self.assertEqual(path.read_text(encoding="utf-8"), "second")
        self.assertNotEqual(sources[0], sources[1])


if __name__ == "__main__":
    unittest.main()
