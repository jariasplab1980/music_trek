
import csv

import pytest
from pyspark.sql import SparkSession

from music_lab.pipeline import run_pipeline


@pytest.fixture(scope="session")
def spark():
    session = (
        SparkSession.builder
        .master("local[2]")
        .appName("MusicDiscoveryLab-Tests")
        .getOrCreate()
    )
    session.sparkContext.setLogLevel("ERROR")
    yield session
    session.stop()


@pytest.fixture
def dataset(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    rows = [
        ["001", "S001", "Moon Waltz", "Artist A",
         "Classical", "92", "0.42", "0.30", "0.98"],
        ["002", "S002", "Silent Forest", "Artist B",
         "Ambient", "70", "0.25", "0.18", "1.00"],
        ["003", "S001", "Moon Waltz", "Artist A",
         "Classical", "92", "0.42", "0.30", "0.98"],
        ["004", "S003", "Broken Tempo", "Artist C",
         "Soundtrack", "350", "0.50", "0.40", "0.85"],
        ["005", "S004", "", "Artist D",
         "Ambient", "75", "0.30", "0.20", "0.95"],
    ]

    with (raw_dir / "songs.csv").open(
        "w", newline="", encoding="utf-8"
    ) as file:
        writer = csv.writer(file)
        writer.writerow([
            "source_row_id", "song_id", "title", "artist",
            "genre", "bpm", "energy", "valence",
            "instrumentalness",
        ])
        writer.writerows(rows)

    return tmp_path


def test_pipeline_counts(spark, dataset):
    result = run_pipeline(spark, dataset)

    assert result == {
        "bronze": 5,
        "invalid": 2,
        "silver": 2,
        "quarantine": 3,
        "gold_genres": 2,
    }


def test_silver_has_unique_ids(spark, dataset):
    run_pipeline(spark, dataset)

    silver = spark.read.parquet(
        str(dataset / "silver" / "songs")
    )

    assert silver.count() == silver.select("song_id").distinct().count()


def test_parquet_outputs_exist(spark, dataset):
    run_pipeline(spark, dataset)

    for relative_path in [
        "bronze/songs",
        "silver/songs",
        "quarantine/songs",
        "gold/genre_metrics",
    ]:
        assert (dataset / relative_path).is_dir()


def test_missing_input_fails(spark, tmp_path):
    with pytest.raises(FileNotFoundError):
        run_pipeline(spark, tmp_path)
