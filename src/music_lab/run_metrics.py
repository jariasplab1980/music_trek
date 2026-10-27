
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4


logger = logging.getLogger("music_lab.metrics")

def utc_now() -> datetime:
    """Devuelve la fecha y hora actual en UTC."""
    return datetime.now(timezone.utc)

def write_run_metrics(
    metrics: dict[str, Any],
    output_dir: str | Path,
) -> dict[str, Any]:
    """Persiste las métricas de una ejecución en formato JSONL."""

    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    now = datetime.now(timezone.utc)

    record = {
        "run_id": str(uuid4()),
        "pipeline": "music_discovery",
        "recorded_at": utc_now().isoformat(),
        **metrics,
    }

    metrics_file = output_path / "run_metrics.jsonl"

    try:
        with metrics_file.open("a", encoding="utf-8") as file:
            file.write(
                json.dumps(record, ensure_ascii=False, default=str)
                + "\n"
            )

        logger.info("Métricas guardadas en %s", metrics_file)

    except OSError:
        logger.exception(
            "No fue posible guardar las métricas en %s",
            metrics_file,
        )
        raise

    return record
