
from pathlib import Path

from pyspark.sql import DataFrame, SparkSession, Window
from pyspark.sql import functions as F
from pyspark.sql.types import (
    DoubleType,
    IntegerType,
    StringType,
    StructField,
    StructType,
)


RAW_SCHEMA = StructType([
    StructField("source_row_id", StringType(), False),
    StructField("song_id", StringType(), True),
    StructField("title", StringType(), True),
    StructField("artist", StringType(), True),
    StructField("genre", StringType(), True),
    StructField("bpm", StringType(), True),
    StructField("energy", StringType(), True),
    StructField("valence", StringType(), True),
    StructField("instrumentalness", StringType(), True),
])

SILVER_COLUMNS = [
    "song_id",
    "title",
    "artist",
    "genre",
    "bpm",
    "energy",
    "valence",
    "instrumentalness",
]

QUARANTINE_COLUMNS = [
    "source_row_id",
    *SILVER_COLUMNS,
    "rejection_reason",
]


def read_bronze(spark: SparkSession, raw_file: Path) -> DataFrame:
    """Lee el CSV original y persiste Bronze en Parquet."""
    df = (
        spark.read
        .option("header", True)
        .schema(RAW_SCHEMA)
        .csv(str(raw_file))
    )

    df.write.mode("overwrite").parquet(
        str(raw_file.parent.parent / "bronze" / "songs")
    )
    return df


def cast_columns(df: DataFrame) -> DataFrame:
    """Normaliza textos y convierte las variables numéricas."""
    df = df.withColumn("song_id", F.trim("song_id"))

    for column in ["title", "artist", "genre"]:
        df = df.withColumn(column, F.trim(F.col(column)))

    df = df.withColumn("bpm", F.col("bpm").cast(IntegerType()))

    for column in ["energy", "valence", "instrumentalness"]:
        df = df.withColumn(column, F.col(column).cast(DoubleType()))

    return df


def validate_records(df: DataFrame) -> tuple[DataFrame, DataFrame]:
    """Separa registros válidos e inválidos y documenta los errores."""
    checks = [
        (
            F.col("song_id").isNull() | (F.col("song_id") == ""),
            "missing_song_id",
        ),
        (
            F.col("title").isNull() | (F.col("title") == ""),
            "missing_title",
        ),
        (
            F.col("artist").isNull() | (F.col("artist") == ""),
            "missing_artist",
        ),
        (
            F.col("genre").isNull() | (F.col("genre") == ""),
            "missing_genre",
        ),
        (
            F.col("bpm").isNull()
            | (F.col("bpm") < 1)
            | (F.col("bpm") > 300),
            "invalid_bpm",
        ),
    ]

    for column in ["energy", "valence", "instrumentalness"]:
        checks.append((
            F.col(column).isNull()
            | (F.col(column) < 0.0)
            | (F.col(column) > 1.0),
            f"invalid_{column}",
        ))

    reasons = F.filter(
        F.array(*[
            F.when(condition, F.lit(reason))
            .otherwise(F.lit(None).cast("string"))
            for condition, reason in checks
        ]),
        lambda reason: reason.isNotNull(),
    )

    checked = (
        df.withColumn("_reasons", reasons)
        .withColumn(
            "rejection_reason",
            F.concat_ws("; ", F.col("_reasons")),
        )
    )

    invalid = (
        checked.filter(F.size("_reasons") > 0)
        .select(*QUARANTINE_COLUMNS)
    )

    valid = checked.filter(F.size("_reasons") == 0).drop(
        "_reasons", "rejection_reason"
    )

    return valid, invalid


def deduplicate_records(
    valid: DataFrame,
) -> tuple[DataFrame, DataFrame]:
    """Conserva la primera aparición y separa duplicados."""
    window = Window.partitionBy("song_id").orderBy("source_row_id")

    ranked = valid.withColumn(
        "_row_number", F.row_number().over(window)
    )

    silver = ranked.filter(
        F.col("_row_number") == 1
    ).select(*SILVER_COLUMNS)

    duplicates = (
        ranked.filter(F.col("_row_number") > 1)
        .withColumn(
            "rejection_reason", F.lit("duplicate_song_id")
        )
        .select(*QUARANTINE_COLUMNS)
    )

    return silver, duplicates


def build_gold(silver: DataFrame) -> DataFrame:
    """Genera indicadores musicales agregados por género."""
    return (
        silver.groupBy("genre")
        .agg(
            F.count("*").alias("song_count"),
            F.round(F.avg("bpm"), 2).alias("avg_bpm"),
            F.round(F.avg("energy"), 3).alias("avg_energy"),
            F.round(F.avg("valence"), 3).alias("avg_valence"),
            F.round(
                F.avg("instrumentalness"), 3
            ).alias("avg_instrumentalness"),
        )
        .withColumn(
            "instrumental_profile",
            F.when(
                F.col("avg_instrumentalness") >= 0.8,
                F.lit("mostly_instrumental"),
            ).otherwise(F.lit("mixed_or_vocal")),
        )
    )


def run_pipeline(
    spark: SparkSession,
    base_path: str | Path,
) -> dict[str, int]:
    """Ejecuta el pipeline completo y persiste sus resultados."""
    base = Path(base_path)
    raw_file = base / "raw" / "songs.csv"

    if not raw_file.is_file():
        raise FileNotFoundError(f"No existe el archivo: {raw_file}")

    bronze = read_bronze(spark, raw_file)
    typed = cast_columns(bronze)
    valid, invalid = validate_records(typed)
    silver, duplicates = deduplicate_records(valid)

    quarantine = invalid.unionByName(duplicates)
    gold = build_gold(silver)

    outputs = {
        "silver": base / "silver" / "songs",
        "quarantine": base / "quarantine" / "songs",
        "gold": base / "gold" / "genre_metrics",
    }

    for name, df in [
        ("silver", silver),
        ("quarantine", quarantine),
        ("gold", gold),
    ]:
        df.write.mode("overwrite").parquet(str(outputs[name]))

    return {
        "bronze": bronze.count(),
        "invalid": invalid.count(),
        "silver": silver.count(),
        "quarantine": quarantine.count(),
        "gold_genres": gold.count(),
    }
