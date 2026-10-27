# HOWTO --- Music Discovery Lab

Guía de trabajo del laboratorio local de descubrimiento musical con
PySpark. Resume la configuración y los pasos realizados hasta esta
sesión, incluyendo logging, métricas de ejecución y validación de
errores.

## 1. Estructura del proyecto

Ubicación del proyecto:

``` text
/lab/kingdom_of_science/projects/music-discovery-lab/
```

Estructura relevante:

``` text
music-discovery-lab/
├── .env
├── docker/
│   ├── compose.yaml
│   └── Dockerfile
├── notebooks/
├── data/
│   ├── raw/songs.csv
│   ├── bronze/songs/
│   ├── silver/songs/
│   ├── gold/genre_metrics/
│   ├── quarantine/songs/
│   └── metrics/run_metrics.jsonl
├── src/music_lab/
│   ├── __init__.py
│   ├── __main__.py
│   ├── logging_config.py
│   ├── pipeline.py
│   └── run_metrics.py
└── tests/
    ├── test_pipeline.py
    └── test_run_metrics.py
```

**Seguridad:** `.env` contiene `JUPYTER_TOKEN`. No publiques ni
compartas su valor.

## 2. Ejecutar Docker Compose

Ejecuta los comandos desde `docker/`, porque Compose utiliza rutas
relativas. El archivo `.env` está en la raíz del proyecto, por lo que se
pasa explícitamente:

``` bash
cd /lab/kingdom_of_science/projects/music-discovery-lab/docker
docker compose --env-file ../.env ps
```

Iniciar los servicios si todavía no están activos:

``` bash
docker compose --env-file ../.env up -d
```

Consultar logs:

``` bash
docker compose --env-file ../.env logs -f music-lab
```

Spark puede mostrar avisos como el nivel predeterminado `WARN` o
mensajes de `NativeCodeLoader` aunque el pipeline termine correctamente.

## 3. Configuración del logging

Archivo `src/music_lab/logging_config.py`:

``` python
import logging
import os
import sys


def configure_logging() -> None:
    """Configura el registro de eventos del laboratorio."""
    log_level = os.getenv("LOG_LEVEL", "INFO").upper()
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        handlers=[logging.StreamHandler(sys.stdout)],
        force=True,
    )
```

La variable `LOG_LEVEL=INFO` se configura en `.env`. Esto configura el
logging de Python; los mensajes internos de Spark pueden tener una
configuración independiente.

## 4. Métricas de ejecución

El módulo `src/music_lab/run_metrics.py` persiste un registro JSON por
línea en `run_metrics.jsonl`. El archivo se abre en modo append (`"a"`),
por lo que las ejecuciones anteriores se conservan.

La función `write_run_metrics(metrics, output_dir)` genera un `run_id`
único, identifica el pipeline, añade `recorded_at` en UTC y escribe las
métricas recibidas. La función `utc_now()` permite obtener marcas de
tiempo con zona horaria UTC.

Campos registrados por la ejecución integrada:

-   `run_id`: identificador único de la ejecución.
-   `pipeline`: nombre del pipeline (`music_discovery`).
-   `recorded_at`: momento en que se registran las métricas.
-   `status`: `SUCCESS` o `FAILED`.
-   `started_at` y `finished_at`: inicio y finalización en UTC.
-   `duration_seconds`: duración medida con `time.perf_counter()`.
-   Métricas del pipeline, como `bronze`, `invalid`, `silver`,
    `quarantine` y `gold_genres`.
-   `error_message`: se incluye cuando se captura una excepción con
    mensaje.

En `src/music_lab/__main__.py`, la construcción de las métricas debe
incluir una estructura equivalente a esta:

``` python
metrics = {
    "status": status,
    "started_at": started_at.isoformat(),
    "finished_at": finished_at.isoformat(),
    "duration_seconds": round(duration, 2),
    **results,
}

if error_message:
    metrics["error_message"] = error_message
```

El bloque de captura de errores debe guardar y registrar la excepción:

``` python
except Exception as exc:
    error_message = str(exc)
    logger.exception("Error durante la ejecución del pipeline")
```

El bloque `finally` calcula la duración, prepara las métricas e intenta
persistirlas incluso si el pipeline falla. La función principal devuelve
código `0` si termina correctamente y `1` cuando falla la ejecución o no
se pueden guardar las métricas.

## 5. Ejecutar el pipeline

Desde `docker/`:

``` bash
docker compose --env-file ../.env exec music-lab \
  python -m music_lab --data-dir /home/jovyan/data
```

Rutas de salida configuradas:

-   Bronze: `/home/jovyan/data/bronze/songs/`
-   Silver: `/home/jovyan/data/silver/songs/`
-   Cuarentena: `/home/jovyan/data/quarantine/songs/`
-   Métricas por género (Gold): `/home/jovyan/data/gold/genre_metrics/`
-   Métricas de ejecución: `/home/jovyan/data/metrics/run_metrics.jsonl`

**Importante:** las salidas del pipeline se escriben en modo overwrite
según la implementación actual. Respalda cualquier resultado que
necesites conservar antes de volver a ejecutar el proceso.

## 6. Consultar el historial de métricas

Ver las últimas tres ejecuciones:

``` bash
docker compose --env-file ../.env exec music-lab \
  tail -n 3 /home/jovyan/data/metrics/run_metrics.jsonl
```

Cada línea debe ser un objeto JSON independiente. Una ejecución exitosa
debe registrar `status: SUCCESS` y las métricas calculadas. Una
ejecución fallida debe registrar `status: FAILED` y, si se capturó una
excepción con mensaje, `error_message`.

## 7. Probar un fallo controlado

Se verificó el manejo de errores utilizando un directorio que no
contiene `raw/songs.csv`:

``` bash
docker compose --env-file ../.env exec music-lab \
  python -m music_lab --data-dir /home/jovyan/data/no_existe
```

Esta ejecución debe fallar porque no existe el archivo de entrada. Como
el directorio de métricas se deriva de `--data-dir`, el registro se
guarda en:

``` text
/home/jovyan/data/no_existe/metrics/run_metrics.jsonl
```

Consultar las últimas ejecuciones de esta prueba:

``` bash
docker compose --env-file ../.env exec music-lab \
  tail -n 3 /home/jovyan/data/no_existe/metrics/run_metrics.jsonl
```

Ejemplo de resultado observado:

``` json
{
  "run_id": "66a98009-c5ad-49c8-bea3-7c4dcd25d9c4",
  "pipeline": "music_discovery",
  "recorded_at": "2026-10-27T01:24:25.324525+00:00",
  "status": "FAILED",
  "started_at": "2026-10-27T01:24:14.932147+00:00",
  "finished_at": "2026-10-27T01:24:25.324102+00:00",
  "duration_seconds": 10.39,
  "error_message": "No existe el archivo: /home/jovyan/data/no_existe/raw/songs.csv"
}
```

Este resultado confirma que el error queda registrado con su causa. La
ruta `no_existe` se usa solo para la prueba, no para los datos normales.

## 8. Ejecutar las pruebas automatizadas

Desde `docker/`:

``` bash
docker compose --env-file ../.env exec music-lab \
  python -m pytest -v /home/jovyan/tests
```

Las pruebas del proyecto cubren, entre otros aspectos:

-   Conteos de registros por etapa del pipeline.
-   Unicidad de identificadores en Silver.
-   Existencia de salidas Parquet.
-   Error cuando falta el archivo de entrada.
-   Identificadores únicos para cada ejecución.
-   Escritura de JSONL válido.
-   Conservación del historial mediante append.
-   Persistencia de las métricas recibidas.

**Pendiente de confirmar:** no se ha compartido todavía la salida final
de `pytest` después de los últimos cambios. Confirma que todas las
pruebas pasan antes de considerar validada la suite.

## 9. Resultados de referencia

Para el CSV de 12 registros usado en el laboratorio, la ejecución
exitosa más reciente produjo:

  Métrica                      Resultado
  --------------------- ----------------
  Bronze                              12
  Registros inválidos                  2
  Silver                              10
  Cuarentena                           2
  Géneros en Gold                      3
  Duración aproximada     24,58 segundos

La relación de conteos esperada es `12 - 2 = 10`: los dos registros
inválidos se separan y los diez restantes pasan a Silver.

## 10. Cierre y siguiente sesión

Durante esta sesión se completó y verificó:

-   Configuración del logging de Python.
-   Persistencia de métricas en JSONL sin sobrescribir el historial.
-   Identificación única de ejecuciones.
-   Marcas de tiempo de inicio, finalización y registro.
-   Medición de duración.
-   Registro del estado `SUCCESS` o `FAILED`.
-   Persistencia de `error_message` para un fallo controlado por archivo
    inexistente.

**Primer paso para la próxima sesión:** ejecutar la suite completa y
revisar el resultado:

``` bash
docker compose --env-file ../.env exec music-lab \
  python -m pytest -v /home/jovyan/tests
```

Si todas las pruebas pasan, podemos continuar mejorando la
observabilidad y la calidad del pipeline, por ejemplo, con pruebas
específicas del registro de errores y validaciones adicionales de datos.
