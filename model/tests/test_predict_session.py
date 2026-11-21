import json
import tempfile
import unittest
from pathlib import Path

from src.predict import clear_previous_outputs, write_json_outputs


class OutputFolderTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def test_clear_previous_outputs_removes_old_json_only(self) -> None:
        output = self.root / "output"
        (output / "case1").mkdir(parents=True)
        (output / "case1" / "old.json").write_text("{}", encoding="utf-8")
        (output / "stale.json").write_text("{}", encoding="utf-8")
        (output / ".gitkeep").write_text("", encoding="utf-8")

        self.assertEqual(clear_previous_outputs(output), 2)
        self.assertEqual(sorted(p.name for p in output.iterdir()), [".gitkeep"])

    def test_outputs_mirror_input_tree_and_unsupported_is_empty_file(self) -> None:
        input_dir = self.root / "input"
        (input_dir / "case1").mkdir(parents=True)
        known = input_dir / "case1" / "przelew_nr_1.pdf"
        other = input_dir / "case1" / "ogloszenie.pdf"
        results = [
            {"file": str(known), "json": {"przelew_bankowy": {"kwota": 1.0}}},
            {"file": str(other), "json": {}},
        ]

        outputs = write_json_outputs(results, [input_dir], self.root / "output")

        self.assertEqual(outputs[0], self.root / "output" / "case1" / "przelew_nr_1.json")
        self.assertEqual(json.loads(outputs[0].read_text(encoding="utf-8"))["przelew_bankowy"]["kwota"], 1.0)
        self.assertEqual(outputs[1].read_bytes(), b"")


if __name__ == "__main__":
    unittest.main()
