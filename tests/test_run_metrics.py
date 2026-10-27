
import json

from music_lab.run_metrics import write_run_metrics


def test_generates_unique_run_ids(tmp_path):
    first = write_run_metrics(
        {"status": "SUCCESS"},
        tmp_path,
    )
    second = write_run_metrics(
        {"status": "SUCCESS"},
        tmp_path,
    )

    assert first["run_id"] != second["run_id"]


def test_writes_valid_jsonl(tmp_path):
    write_run_metrics(
        {"status": "SUCCESS", "bronze": 12},
        tmp_path,
    )

    metrics_file = tmp_path / "run_metrics.jsonl"
    lines = metrics_file.read_text(encoding="utf-8").splitlines()

    assert len(lines) == 1

    record = json.loads(lines[0])
    assert record["pipeline"] == "music_discovery"
    assert record["status"] == "SUCCESS"
    assert record["bronze"] == 12


def test_appends_without_overwriting_history(tmp_path):
    write_run_metrics(
        {"status": "SUCCESS", "bronze": 12},
        tmp_path,
    )
    write_run_metrics(
        {"status": "FAILED", "bronze": 5},
        tmp_path,
    )

    metrics_file = tmp_path / "run_metrics.jsonl"
    records = [
        json.loads(line)
        for line in metrics_file.read_text(encoding="utf-8").splitlines()
    ]

    assert len(records) == 2
    assert records[0]["status"] == "SUCCESS"
    assert records[1]["status"] == "FAILED"


def test_preserves_execution_metrics(tmp_path):
    expected = {
        "status": "SUCCESS",
        "bronze": 12,
        "invalid": 2,
        "silver": 10,
        "quarantine": 2,
        "gold_genres": 3,
        "duration_seconds": 24.8,
    }

    record = write_run_metrics(expected, tmp_path)

    for key, value in expected.items():
        assert record[key] == value
