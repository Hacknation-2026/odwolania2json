import json
from pathlib import Path

import pytest

from app import cli
from app.cli import clear_previous_outputs, run

DANE = Path(__file__).resolve().parents[2] / "data" / "hacknation-2026" / "dane"


def test_clear_previous_outputs_removes_old_json_only(tmp_path):
    output = tmp_path / "output"
    (output / "case1").mkdir(parents=True)
    (output / "case1" / "old.json").write_text("{}", encoding="utf-8")
    (output / "stale.json").write_text("{}", encoding="utf-8")
    (output / ".gitkeep").write_text("", encoding="utf-8")

    assert clear_previous_outputs(output) == 2
    assert sorted(p.name for p in output.iterdir()) == [".gitkeep"]


def test_run_mirrors_input_tree_and_leaves_input_untouched(tmp_path, monkeypatch):
    input_dir = tmp_path / "input"
    (input_dir / "case1").mkdir(parents=True)
    (input_dir / "case1" / "przelew_nr_1.pdf").write_bytes(b"%PDF known")
    (input_dir / "case1" / "ogloszenie.pdf").write_bytes(b"%PDF other")
    (input_dir / "case1" / "broken.pdf").write_bytes(b"%PDF broken")

    def fake_process(data: bytes, name: str) -> dict:
        if name == "broken.pdf":
            raise ValueError("unreadable")
        known = name == "przelew_nr_1.pdf"
        return {
            "document_type": "przelew" if known else "brak",
            "data": {"przelew_bankowy": {"kwota": 1.0}} if known else None,
            "trace": {"classification": {"confidence": 0.9}, "seconds": 0.0},
        }

    monkeypatch.setattr(cli, "process_pdf", fake_process)
    errors = run(input_dir, tmp_path / "output", trace_dir=None)

    out = tmp_path / "output" / "case1"
    assert errors == 1
    assert json.loads((out / "przelew_nr_1.json").read_text(encoding="utf-8"))["przelew_bankowy"]["kwota"] == 1.0
    assert (out / "ogloszenie.json").read_bytes() == b""
    assert (out / "broken.json").read_bytes() == b""
    assert len(list(input_dir.rglob("*.pdf"))) == 3


@pytest.mark.skipif(not DANE.exists(), reason="brak danych UZP")
def test_real_case_end_to_end(tmp_path):
    case = tmp_path / "input" / "case1"
    case.mkdir(parents=True)
    for pdf in (DANE / "przyklad_05").glob("*.pdf"):
        (case / pdf.name).write_bytes(pdf.read_bytes())
    assert run(tmp_path / "input", tmp_path / "output", trace_dir=None) == 0
    gold = json.loads((DANE / "przyklad_05" / "przelew.json").read_text(encoding="utf-8"))
    pred = next((tmp_path / "output" / "case1").glob("*przelew*.json"))
    assert json.loads(pred.read_text(encoding="utf-8")) == gold
