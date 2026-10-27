
import argparse
import logging
import time
import sys
from pathlib import Path
from datetime import timezone

from pyspark.sql import SparkSession

from music_lab.logging_config import configure_logging
from music_lab.pipeline import run_pipeline
from music_lab.run_metrics import utc_now, write_run_metrics


def main() -> int:
    configure_logging()
    logger = logging.getLogger("music_lab")
    parser = argparse.ArgumentParser(
        description="Pipeline de descubrimiento musical con PySpark"
    )
    parser.add_argument(
        "--data-dir",
        default="/home/jovyan/data",
        help="Directorio base de datos del laboratorio",
    )
    args = parser.parse_args()

    base_path = Path(args.data_dir)
    metrics_dir = base_path / "metrics"
    started_at = utc_now()
    start_time = time.perf_counter()
    spark = None
    status = "FAILED"
    results = {}
    error_message = None

    logger.info("Inicio del pipeline de descubrimiento musical")
    logger.info("Directorio de datos: %s", base_path)

    try:
        spark = (
                SparkSession.builder
                .appName("MusicDiscoveryLab")
                .getOrCreate()
            )
        logger.info("Sesión Spark inicializada")
        results = run_pipeline(spark, base_path)

        status = "SUCCESS"

        duration = time.perf_counter() - start_time
        logger.info("Pipeline finalizado correctamente")

        for name, value in results.items():
            logger.info("Métrica | %s=%s", name, value)

        logger.info("Métrica | duration_seconds=%.2f", duration)
        logger.info("Estado final: SUCCESS")

        return 0
    except Exception as exc:
        duration = time.perf_counter() - start_time
        error_message = str(exc)
        logger.exception("Error durante la ejecución del pipeline")
        logger.error("Métrica | duration_seconds=%.2f", duration)
        logger.error("Estado final: FAILED")
        
        return 1
    finally:
        if spark is not None:
            try:
                spark.stop()
                finished_at = utc_now()
                logger.info("Sesión Spark detenida")
            except Exception:
                logger.exception("Error al detener la sesión Spark")
                if status == "SUCCESS":
                    status = "FAILED"
                    error_message = "Error al detener la sesión Spark"

        duration = time.perf_counter() - start_time

        metrics = {
            "status": status,
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "duration_seconds": round(duration, 2),
            **results,
        }

        if error_message:
            metrics["error_message"] = error_message

        try:
            write_run_metrics(metrics, metrics_dir)
            logger.info("Estado final: %s", status)
            logger.info("Duración total: %.2f segundos", duration)
        except Exception:
            logger.exception("No se pudieron persistir las métricas")
            return 1

    return 0 if status == "SUCCESS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
