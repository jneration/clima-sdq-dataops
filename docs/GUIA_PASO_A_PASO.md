# Guía paso a paso: Pipeline DataOps de clima de Santo Domingo

Guía para reproducir el proyecto y documentar cada paso. Los scripts **ya existen** en este repositorio; aquí se indica qué hace cada uno, dónde ejecutarlo y qué evidencia capturar para el documento.

Cifras y salidas de esta guía provienen de ejecuciones reales del 28/09/2026. Al cargar datos nuevos cambian; recalcúlalas antes de entregar (sección 11.2).

## 0. Estado y convenciones

| Paso | Qué se hace | Estado |
|---|---|---|
| 0 | Carpeta, Git y entorno de Python | Hecho y verificado |
| 1 | Base de datos `ClimaSDQ` | Hecho y verificado |
| 2 | Extracción desde la API | Hecho y verificado |
| 3 | Validación y carga | Hecho y verificado |
| 4 | Agregados, orquestador y pruebas | Hecho y verificado |
| 5 | Ejecución diaria programada | Hecho y verificado |
| 6 | Vistas para Power BI | Hecho y verificado |
| 7 | Publicar en GitHub | **Pendiente: lo haces tú** |
| 8 | Demostración de calidad (opcional) | Script listo; lo ejecutas tú |
| 9 | Dashboard en Power BI | **Pendiente: lo armas tú** |
| 10 | Documento final | **Pendiente: lo redactas tú** |

- Todo el proyecto vive en `G:\My Drive\Universidad\46\proyecto-clima`. Los comandos asumen que estás en esa carpeta.
- El entorno de Python está fuera de Drive, en `C:\venvs\clima`. Los comandos usan `C:\venvs\clima\Scripts\python.exe` para no depender de activar el entorno.
- SQL Server: instancia `localhost\SQLEXPRESS`, autenticación de Windows.
- Herramientas: Python 3.14, pandas, requests, pyodbc y pytest; SQL Server Express y sqlcmd; SSMS 22; Git; Power BI Desktop.

**Mapa de commits.** El historial agrupa los pasos así (`git log --oneline`):

| Commit | Pasos que incluye |
|---|---|
| `1a81390` Paso 1 | 0 y 1: estructura, `.gitignore`, `requirements.txt`, base de datos |
| `da24e72` Paso 2 | 2: `config.py` y `extraer.py` |
| `d2458c8` Paso 3 | 3: `validar.py`, `cargar.py`, pruebas y un workflow de CI (retirado después, ver paso 7) |
| `1b70f3b` Paso 4 | 4: agregados y `pipeline.py` |
| `7f9e0d8` Paso 5 | 5 y 6: tarea programada, vistas para Power BI y README |

---

## Paso 0. Carpeta, Git y entorno de Python

**Dónde:** PowerShell, en cualquier carpeta.

```powershell
$raiz = "G:\My Drive\Universidad\46\proyecto-clima"
New-Item -ItemType Directory -Force -Path "$raiz\sql","$raiz\src","$raiz\tests","$raiz\datos\raw","$raiz\logs","$raiz\docs","$raiz\scripts" | Out-Null
cd $raiz
git init
git config user.name  "Jason Crisostomo"
git config user.email "jason.crisostomo.rg@gmail.com"

python -m venv C:\venvs\clima          # fuera de Drive: evita sincronizar miles de archivos
C:\venvs\clima\Scripts\python.exe -m pip install requests pandas pyodbc pytest
C:\venvs\clima\Scripts\python.exe -m pip freeze | Out-File -Encoding ascii requirements.txt
```

**Resultado esperado:** `git status` funciona y `C:\venvs\clima\Scripts\python.exe -c "import pyodbc, pandas"` no da error.
**Evidencia:** captura de la estructura de carpetas.

## Paso 1. Base de datos `ClimaSDQ`

**Archivo:** `sql/01_crear_base.sql`. Crea la base, los esquemas `raw`, `clean`, `agg` y `ops`, y 5 tablas. Es idempotente (se puede repetir sin error).

**Dónde:** PowerShell (o SSMS, conectado a `localhost\SQLEXPRESS` con autenticación de Windows).

```powershell
sqlcmd -S "localhost\SQLEXPRESS" -E -C -b -i sql\01_crear_base.sql
```

| Esquema | Tabla | Función |
|---|---|---|
| `raw` | `lectura_clima` | Datos tal como llegan; solo se agrega, nunca se corrige |
| `clean` | `lectura_clima` | Datos validados; clave primaria `fecha_hora` (una fila por hora) |
| `agg` | `clima_diario` | Resumen diario |
| `ops` | `log_carga` | Una fila por ejecución del pipeline |
| `ops` | `rechazos` | Una fila por dato rechazado, con su motivo |

**Resultado esperado:** en SSMS, `ClimaSDQ` con 4 esquemas y 5 tablas. Las bases `Principal` y `SIGNE` no se tocan.
**Evidencia:** captura del Explorador de objetos y un diagrama del modelo (SSMS: clic derecho en *Diagramas de base de datos*, o dibújalo).

## Paso 2. Extracción desde la API

**Archivos:** `src/config.py` (parámetros) y `src/extraer.py`.

- **Fuente:** Open-Meteo, punto 18,4861 / -69,9312 (Santo Domingo), zona horaria `America/Santo_Domingo`. Variables horarias: temperatura a 2 m, humedad relativa y precipitación.
- **Carga histórica:** servicio de archivo, 12 meses hasta 6 días atrás (el servicio publica con retraso).
- **Carga incremental:** servicio de pronóstico con `past_days = 7`, descartando horas futuras. La ventana debe ser mayor que el retraso del archivo; con 3 días quedaban 48 horas sin datos (defecto detectado y corregido).
- Reintentos: 3 intentos con espera creciente; si la API no responde, lanza un error claro.
- Cada respuesta se guarda como JSON crudo en `datos\raw\` con fecha y hora (evidencia y reprocesamiento).

**Dónde:**

```powershell
cd src
C:\venvs\clima\Scripts\python.exe extraer.py      # prueba: imprime las primeras filas del incremental
cd ..
```

**Resultado esperado:** unas 90 a 190 filas y un archivo `incremental_*.json` en `datos\raw\`. El histórico trae 8.784 filas.
**Evidencia:** captura de la salida y del JSON crudo.

## Paso 3. Validación y carga

**Archivos:** `src/validar.py` y `src/cargar.py`.

**Reglas de calidad** (`validar.py`). Cada fila rechazada recibe el primer motivo que le aplica, en este orden:

| # | Motivo registrado | Criterio |
|---|---|---|
| 1 | `campo_nulo` | Algún campo vacío |
| 2 | `temperatura_fuera_de_rango` | Fuera de 10 a 45 °C |
| 3 | `humedad_fuera_de_rango` | Fuera de 0 a 100 % |
| 4 | `precipitacion_negativa` | Menor que 0 |
| 5 | `duplicado_en_lote` | `fecha_hora` repetida en el lote; se conserva la última recibida |

**Alerta de frescura:** en cargas incrementales, si la última lectura válida tiene más de 72 horas.
**Completitud:** el día con menos de 24 lecturas se guarda como `dia_completo = 0` (paso 4).

**Carga** (`cargar.py`), en una sola transacción:
1. Inserta todo lo recibido en `raw`.
2. Inserta los rechazos en `ops.rechazos`.
3. Hace `MERGE` de las filas válidas en `clean`: inserta las nuevas y actualiza las que cambiaron (gana el último recibido). Repetir una carga no duplica nada.
4. Cierra la fila de `ops.log_carga` con filas leídas, válidas y rechazadas.

Si algo falla, hace rollback y registra `estado = 'error'` con el mensaje.

**Dónde:** se ejecuta desde el orquestador (paso 4).

**Evidencia:** fragmento de `validar.py`; consulta de `ops.log_carga` tras una carga.

## Paso 4. Agregados, orquestador y pruebas

**Archivos:** `sql/02_agregar_diario.sql`, `src/pipeline.py` y `tests/test_validar.py`.

- **Agregados:** el procedimiento `agg.sp_actualizar_diario` calcula, por día, mínima, máxima y promedio de temperatura, humedad promedio, lluvia total, número de lecturas, `dia_completo` (24 lecturas) y `calor_extremo` (máxima ≥ 32 °C). Con `@dias_atras = NULL` recalcula todo; con un número, los últimos N días.
- **Umbral de calor extremo:** 32 °C. Con 33 °C solo habría 4 días en el año (indicador casi vacío); con 32 °C son 33 días.
- **Orquestador:** `pipeline.py historica` o `pipeline.py incremental`. Escribe el log en `logs\pipeline_AAAAMMDD.log` y termina con código 0 (ok) o 1 (error).
- **Pruebas:** 11 pruebas de pytest sobre las reglas de calidad (límites inclusivos, cada motivo de rechazo, prioridad del nulo, duplicados, frescura).

**Dónde:**

```powershell
sqlcmd -S "localhost\SQLEXPRESS" -E -C -b -i sql\02_agregar_diario.sql
C:\venvs\clima\Scripts\python.exe -m pytest -q
C:\venvs\clima\Scripts\python.exe src\pipeline.py historica
C:\venvs\clima\Scripts\python.exe src\pipeline.py incremental
```

**Resultado esperado:** `11 passed`; ambas cargas terminan con "Pipeline ... terminó correctamente". Una segunda carga idéntica devuelve `nuevas_o_actualizadas: 0`.
**Evidencia:** captura de pytest en verde, salida del pipeline y `SELECT TOP 5 * FROM agg.clima_diario ORDER BY fecha DESC`.

**Cómo comprobar que no hay huecos:**

```sql
WITH h AS (SELECT fecha_hora, LEAD(fecha_hora) OVER (ORDER BY fecha_hora) sig FROM clean.lectura_clima)
SELECT COUNT(*) AS huecos FROM h WHERE sig IS NOT NULL AND DATEDIFF(HOUR, fecha_hora, sig) > 1;
```

Debe devolver 0. El día en curso aparece con menos de 24 lecturas y `dia_completo = 0`.

## Paso 5. Ejecución diaria programada (6:00 a.m.)

**Archivo:** `scripts/registrar_tarea.ps1`. Registra la tarea `ClimaSDQ-Incremental` en el Programador de tareas de Windows: diaria a las 6:00, corre con tu usuario y solo con la sesión iniciada, no pide administrador, y si el equipo estaba apagado a esa hora se ejecuta al volver.

**Dónde:**

```powershell
powershell -ExecutionPolicy Bypass -File scripts\registrar_tarea.ps1
Start-ScheduledTask -TaskName 'ClimaSDQ-Incremental'      # disparo manual de prueba
Get-ScheduledTask -TaskName 'ClimaSDQ-Incremental' | Get-ScheduledTaskInfo
```

**Resultado esperado:** `LastTaskResult = 0` y una fila nueva en `ops.log_carga`. El código 267011 antes de la primera ejecución solo significa "aún no ha corrido".
**Evidencia:** captura de la tarea en el Programador de tareas (pestañas *Desencadenadores* y *Acciones*) y de `ops.log_carga`.
**Limitación a documentar:** requiere equipo encendido, sesión iniciada y Google Drive montado; un día perdido se recupera solo por la ventana de 7 días.

## Paso 6. Vistas para Power BI

**Archivo:** `sql/03_vistas_bi.sql`. El dashboard lee solo el esquema `bi`, no las tablas.

| Vista | Contenido |
|---|---|
| `bi.v_clima_horario` | Lecturas horarias con fecha, hora, año, mes y `anio_mes` |
| `bi.v_clima_diario` | Agregado diario, **solo días completos**, con mes, día de la semana, `calor_extremo` y `dia_lluvioso` (lluvia ≥ 1 mm) |
| `bi.v_calidad_datos` | Cargas con filas leídas, válidas, rechazadas, `pct_valido` y estado |
| `bi.v_rechazos` | Cada fila rechazada con su motivo y la carga de origen |

```powershell
sqlcmd -S "localhost\SQLEXPRESS" -E -C -b -f 65001 -i sql\03_vistas_bi.sql
```

**Resultado esperado:** `bi.v_clima_horario` con 8.922 filas y `bi.v_clima_diario` con 371 (53 de cada día de la semana).
**Nota:** si en la consola de `sqlcmd` los acentos salen rotos, es solo la pantalla; el dato se guarda bien. Agrega `-f 65001`.

## Paso 7. Publicar en GitHub (lo haces tú)

1. En github.com: **New repository**, nombre `clima-sdq-dataops`, **Public**. No marques "Add README" ni `.gitignore`.
2. Actualiza tu usuario en el comando y ejecuta:

```powershell
cd "G:\My Drive\Universidad\46\proyecto-clima"
git remote add origin https://github.com/TU_USUARIO/clima-sdq-dataops.git
git push -u origin main
```

Git Credential Manager abre el navegador para autenticarte.

**Resultado esperado:** el repositorio se ve con el README y el diagrama de arquitectura dibujado.
**Evidencia:** captura de la página del repositorio y de *Commits*.
**Sin CI:** se probó GitHub Actions, pero la cuenta tuvo un bloqueo de facturación y el job no llegó a ejecutarse (fallaba en 2 segundos, sin pasos). El workflow se retiró para no dejar una marca roja en el repositorio. Las pruebas se ejecutan en local con `pytest` (11 passed). Puedes mencionarlo como limitación y como mejora futura.
**Seguridad:** el repositorio es público y no contiene credenciales (autenticación de Windows). Los JSON crudos y los logs están en `.gitignore`.

## Paso 8. Demostración de calidad (opcional)

**Por qué:** los datos reales son limpios, así que la página de Calidad del dashboard mostraría cero rechazos. Este script inyecta 6 filas 100 % inválidas para que el gráfico de rechazos tenga contenido.

**Qué hace y qué no:** las filas llegan a `raw`, `ops.rechazos` y `ops.log_carga` (con `tipo = 'demo_calidad'`). **No** entran a `clean` ni a `agg`, porque ninguna es válida (verificado: `clean` seguía en 8.922 filas y `agg` en 372).

```powershell
C:\venvs\clima\Scripts\python.exe scripts\demo_calidad.py
```

**Resultado esperado:** `leidas: 6, validas: 0, rechazadas: 6`; en `bi.v_rechazos` aparecen `precipitacion_negativa` (3), `temperatura_fuera_de_rango` (1), `campo_nulo` (1) y `humedad_fuera_de_rango` (1).
**Regla del documento:** preséntala como *prueba de calidad con datos sintéticos*, nunca como datos reales. Las medidas DAX del paso 9 excluyen `demo_calidad` de los indicadores reales.
**Ejecútala una sola vez.** Ya se ejecutó en tu equipo el 28/09/2026 (carga #7); repetirla duplica los rechazos de la demostración.

## Paso 9. Dashboard en Power BI

Power BI Desktop no se automatiza; se arma con clics. Guarda el archivo como `docs\ClimaSDQ.pbix`.

### 9.1 Conectar y cargar

1. **Inicio > Obtener datos > SQL Server**.
2. Servidor: `localhost\SQLEXPRESS`. Base de datos: `ClimaSDQ`. Modo: **Importar**. Aceptar.
3. Credenciales: **Windows > Usar mis credenciales actuales**.
4. Si aparece un error de certificado, en la ventana de credenciales desmarca *Cifrar conexiones*. (No lo probé: no puedo abrir Power BI desde aquí.)
5. En el navegador, marca las cuatro vistas `bi.*` y pulsa **Transformar datos**.
6. En Power Query renombra: `v_clima_horario` a `Horario`, `v_clima_diario` a `Diario`, `v_calidad_datos` a `Calidad`, `v_rechazos` a `Rechazos`. **Cerrar y aplicar**.

### 9.2 Modelo

**Vista de modelo**, crear relaciones (uno a varios, dirección única):
- `Diario[fecha]` a `Horario[fecha]`
- `Calidad[id_carga]` a `Rechazos[id_carga]`

**Ordenar por columna** (Vista de datos, seleccionar columna, *Herramientas de columna > Ordenar por columna*):
- `Diario[mes_nombre]` por `mes_num`
- `Horario[mes_nombre]` por `mes_num`
- `Diario[dia_semana]` por `dia_semana_num`

### 9.3 Medidas DAX

Crea una tabla vacía (*Inicio > Especificar datos*, nómbrala `Medidas`) y agrega estas medidas (*Nueva medida*):

```dax
Temp Promedio = AVERAGE ( Diario[temp_prom_c] )

Temp Máxima = MAX ( Diario[temp_max_c] )

Temp Mínima = MIN ( Diario[temp_min_c] )

Humedad Promedio = AVERAGE ( Diario[humedad_prom_pct] )

Lluvia Total (mm) = SUM ( Diario[lluvia_total_mm] )

Días de Calor Extremo = SUM ( Diario[calor_extremo] )

Días Lluviosos = SUM ( Diario[dia_lluvioso] )

Temp Horaria Prom = AVERAGE ( Horario[temperatura_c] )

Humedad Horaria Prom = AVERAGE ( Horario[humedad_pct] )

% Filas Válidas (cargas reales) =
VAR leidas  = CALCULATE ( SUM ( Calidad[filas_leidas] ),  Calidad[tipo] <> "demo_calidad" )
VAR validas = CALCULATE ( SUM ( Calidad[filas_validas] ), Calidad[tipo] <> "demo_calidad" )
RETURN DIVIDE ( validas, leidas )

Última Carga Exitosa =
CALCULATE ( MAX ( Calidad[inicio] ), Calidad[estado] = "ok", Calidad[tipo] <> "demo_calidad" )

Cargas con Error =
CALCULATE ( COUNTROWS ( Calidad ), Calidad[estado] = "error" ) + 0

Filas Rechazadas = COUNTROWS ( Rechazos ) + 0
```

Formatos: `% Filas Válidas` como porcentaje (1 decimal); `Última Carga Exitosa` como fecha y hora; temperaturas con 1 decimal.

### 9.4 Páginas

**Página 1: Resumen**
| Visual | Configuración |
|---|---|
| Segmentador | `Diario[anio_mes]` (estilo lista o desplegable) |
| 4 Tarjetas | `Temp Promedio`, `Temp Máxima`, `Lluvia Total (mm)`, `Días de Calor Extremo` |
| Gráfico de líneas | Eje `Diario[fecha]`; valores `Temp Máxima`, `Temp Promedio`, `Temp Mínima` |
| Gráfico de columnas | Eje `Diario[anio_mes]`; valores `Lluvia Total (mm)` |

**Página 2: Patrones**
| Visual | Configuración |
|---|---|
| Matriz (mapa de calor) | Filas `Horario[hora]`; columnas `Horario[mes_nombre]`; valores `Temp Horaria Prom`. *Formato condicional > Color de fondo > Escala de colores* |
| Gráfico de líneas | Eje `Horario[hora]`; valores `Humedad Horaria Prom` |
| Gráfico de columnas | Eje `Diario[mes_nombre]`; valores `Días de Calor Extremo` |

**Página 3: Calidad de datos**
| Visual | Configuración |
|---|---|
| 3 Tarjetas | `% Filas Válidas (cargas reales)`, `Última Carga Exitosa`, `Cargas con Error` |
| Gráfico de barras | Eje `Rechazos[motivo]`; valores `Filas Rechazadas` |
| Tabla | `Calidad[id_carga]`, `inicio`, `tipo`, `filas_leidas`, `filas_validas`, `filas_rechazadas`, `pct_valido`, `estado` |

Pon títulos en español a cada visual y a cada página.

### 9.5 Actualizar y guardar

- Después de cada carga: **Inicio > Actualizar**. La actualización automática exige Power BI Service y un gateway; queda fuera del alcance y se documenta como mejora futura.
- Guarda `docs\ClimaSDQ.pbix`. Si pesa poco, súbelo al repositorio; si no, exporta las tres páginas a PDF (*Archivo > Exportar > PDF*).
- **Evidencia:** una captura por página.

---

## Paso 10. Documento final

Extensión sugerida: 8 a 10 páginas, más anexos. Ajusta al formato que pida el profesor. Los textos son base; adáptalos con tus palabras.

### 10.1 Metodología: cómo se aplicó DataOps

| Principio DataOps | Cómo se aplicó | Evidencia |
|---|---|---|
| Control de versiones | Todo el código y los SQL en Git y GitHub | Historial de commits |
| Calidad de datos automatizada | 5 reglas de validación y 11 pruebas de pytest ejecutadas en local | `validar.py`, salida de pytest |
| Automatización del pipeline | `pipeline.py` y tarea diaria programada | Programador de tareas, logs |
| Monitoreo | `ops.log_carga`, alerta de frescura y página de Calidad | Dashboard, página 3 |
| Entregas incrementales | Cuatro iteraciones con objetivo y entregable | Tabla de sprints |
| Entorno reproducible | `requirements.txt`, scripts SQL idempotentes y README | Repositorio |

**Sprints.** Describe cada iteración por su objetivo y por los commits de `git log`. Usa las fechas reales de los commits y no inventes fechas: el trabajo se hizo en pocos días, así que no lo presentes como sprints de una semana si eso no ocurrió.

| Sprint | Objetivo | Entregables |
|---|---|---|
| 1. Definición y base | Definir problema y crear la base | Pasos 0 y 1: repositorio, `ClimaSDQ` |
| 2. Ingesta | Extraer y guardar datos | Paso 2: `extraer.py`, carga histórica |
| 3. Calidad y transformación | Validar, cargar y agregar | Pasos 3 y 4: reglas, MERGE, agregados, pruebas |
| 4. Visualización y cierre | Dashboard, programación y documentación | Pasos 5 a 9 |

### 10.2 Esqueleto y texto base

**Portada e índice.** Título: *Sistema de recolección, procesamiento y visualización de datos climáticos de Santo Domingo con enfoque DataOps*. Nombre, matrícula (A00148991), asignatura, profesor y fecha.

**1. Introducción y problema.**
> Los datos climáticos horarios se generan de forma continua, pero su uso para el análisis exige recogerlos, validarlos y almacenarlos de manera confiable. Este trabajo desarrolla un pipeline que extrae datos horarios de temperatura, humedad y precipitación de Santo Domingo, los valida con reglas de calidad, los almacena en SQL Server y los presenta en un dashboard de Power BI. El proyecto se desarrolló con metodología DataOps.

Objetivo general: desarrollar un sistema que recoja, almacene, procese y visualice datos climáticos aplicando DataOps. Objetivos específicos: automatizar la extracción diaria; garantizar la calidad de los datos con reglas verificables; modelar los datos en capas; y visualizar indicadores climáticos y de calidad.

**2. Metodología.** Explica por qué DataOps (es la que más se ajusta a un pipeline de datos: automatiza, prueba y monitorea) y presenta la tabla del punto 10.1 con los sprints. Descarta CRISP-DM en una frase: está orientada a proyectos de minería o modelado predictivo, que este trabajo no incluye.

**3. Fuente de datos.**
> Los datos provienen de la API de Open-Meteo, que integra observaciones de estaciones meteorológicas, satélites y modelos numéricos de reanálisis. Por lo tanto, no son mediciones de un sensor propio: se consumen como datos de redes de observación ambiental a través de una API REST.

Añade licencia (CC BY 4.0) y las variables. Indica el punto geográfico y la zona horaria. Si el profesor exige IoT estricto, dilo en las limitaciones y propón sumar un sensor propio (por ejemplo, ESP32 con DHT22 publicando por MQTT) como trabajo futuro.

**4. Arquitectura y herramientas.** Inserta el diagrama Mermaid del README como imagen (exporta desde GitHub o mermaid.live). Tabla: Python (extracción y validación), SQL Server (almacenamiento y agregados), Power BI (visualización), Git y GitHub (control de versiones), pytest (pruebas), Programador de tareas (automatización).

**5. Modelo de datos.** Tabla de esquemas del paso 1 y explicación de las capas: `raw` conserva lo recibido, `clean` contiene datos validados, `agg` resume por día y `ops` audita cada carga. Justifica: separar capas permite reprocesar sin volver a llamar a la API.

**6. Implementación.** Un apartado por paso (2 a 6), con un fragmento corto de código y una captura. Fragmentos recomendados: `_pedir` (reintentos) de `extraer.py`; `validar` de `validar.py`; el `MERGE` de `cargar.py`; `sp_actualizar_diario`. Deja el código completo en el anexo o en el repositorio.

**7. Calidad de datos y monitoreo.** Tabla de reglas (paso 3), resultados de la carga real (8.784 filas históricas sin rechazos) y la prueba de calidad con datos sintéticos del paso 8 (6 filas, 6 rechazos con su motivo). Incluye los dos defectos que detectó y corrigió el proceso:
- **Hueco de 48 horas:** la ventana incremental de 3 días no cubría el retraso del servicio de archivo. Se detectó al comprobar la continuidad y se corrigió con una ventana de 7 días.
- **Falsa alerta de frescura:** saltaba en la carga histórica, que es antigua por diseño. Ahora aplica solo a cargas incrementales.

**8. Resultados.** Capturas de las 3 páginas del dashboard y estas cifras (371 días completos, del 22/09/2025 al 27/09/2026; recalcúlalas antes de entregar):

| Indicador | Valor |
|---|---|
| Horas almacenadas (`clean`) | 8.922 |
| Temperatura promedio | 25,49 °C |
| Temperatura mínima / máxima horaria | 16,5 °C / 33,6 °C |
| Humedad relativa promedio | 81,10 % |
| Lluvia acumulada | 1.382,4 mm |
| Días lluviosos (lluvia ≥ 1 mm) | 224 de 371 |
| Días de calor extremo (máxima ≥ 32 °C) | 33 |
| Mes más cálido / más fresco | Agosto 2026 (27,54 °C) / Febrero 2026 (23,62 °C) |
| Mes más lluvioso | Octubre 2025 (309,1 mm) |
| Hora más cálida / más fresca (promedio) | 14:00 (29,13 °C) / 06:00 (22,42 °C) |

**9. Conclusiones, limitaciones y trabajo futuro.**
Limitaciones (verificadas):
- Los datos combinan observaciones y modelos; no son un sensor propio.
- El archivo publica con retraso; el incremental usa una ventana solapada.
- La tarea programada requiere equipo encendido, sesión iniciada y Google Drive montado.
- La actualización del dashboard es manual.
- El umbral de calor extremo (32 °C) se fijó a partir de la distribución observada; no es un estándar oficial.

Trabajo futuro: sensor propio por MQTT, actualización automática en Power BI Service, alertas por correo y un modelo de pronóstico (ahí sí encajaría CRISP-DM).

**10. Referencias (APA 7).** Verifica cada una antes de entregar.
- Zippenfenig, P. (2023). *Open-Meteo.com Weather API* [Software]. Zenodo. https://doi.org/10.5281/zenodo.7970649
- Open-Meteo. (s.f.). *Historical Weather API* y *Weather Forecast API*. https://open-meteo.com/en/docs
- The DataOps Manifesto. (s.f.). https://dataopsmanifesto.org/
- Más las referencias que exija la asignatura (Microsoft para SQL Server y Power BI, si las citas).

**Anexos.** A: repositorio (URL). B: scripts SQL. C: bitácora de commits (`git log --oneline`). D: capturas completas.

---

## 11. Anexos de la guía

### 11.1 Checklist de capturas

| # | Captura | Paso |
|---|---|---|
| 1 | Estructura de carpetas | 0 |
| 2 | SSMS: base, esquemas y tablas | 1 |
| 3 | Salida de `extraer.py` y JSON crudo | 2 |
| 4 | pytest: 11 passed | 4 |
| 5 | Salida del pipeline y `ops.log_carga` | 4 |
| 6 | `agg.clima_diario` (últimos días) | 4 |
| 7 | Programador de tareas (desencadenador y acción) | 5 |
| 8 | Repositorio en GitHub y commits | 7 |
| 9 | Rechazos por motivo (demo) | 8 |
| 10 | Las 3 páginas del dashboard | 9 |

### 11.2 Recalcular las cifras del documento

```sql
SELECT COUNT(*) dias, MIN(fecha) desde, MAX(fecha) hasta,
       CAST(AVG(temp_prom_c) AS DECIMAL(5,2)) temp_prom, MIN(temp_min_c) t_min, MAX(temp_max_c) t_max,
       CAST(AVG(humedad_prom_pct) AS DECIMAL(5,2)) hum_prom,
       CAST(SUM(lluvia_total_mm) AS DECIMAL(8,1)) lluvia_mm,
       SUM(dia_lluvioso) dias_lluviosos, SUM(calor_extremo) dias_calor
FROM bi.v_clima_diario;
```

### 11.3 Solución de problemas

| Síntoma | Causa y solución |
|---|---|
| `ModuleNotFoundError: pyodbc` | Falta instalar: `C:\venvs\clima\Scripts\python.exe -m pip install pyodbc` |
| Error de certificado al conectar con Python | La cadena de conexión ya incluye `TrustServerCertificate=yes` (ODBC Driver 18 exige cifrado) |
| `sqlcmd`: "Named Pipes ... not found" | Instancia mal escrita; usa `"localhost\SQLEXPRESS"` entre comillas |
| Acentos rotos en la consola de sqlcmd | Solo es la pantalla; usa `-f 65001` |
| La tarea programada no corre | Comprueba que Google Drive esté montado y la sesión iniciada; revisa `logs\` y `LastTaskResult` |
| Un día sin datos por apagado | Se recupera solo en la siguiente carga (ventana de 7 días) |
| Power BI no ve datos nuevos | Pulsa **Actualizar**; la vista `bi.v_clima_diario` excluye el día en curso hasta que esté completo |
| La API falla | El pipeline reintenta 3 veces; si persiste, registra `estado = 'error'` en `ops.log_carga` y sale con código 1 |

### 11.4 Mapa de archivos

```
proyecto-clima/
├─ docs/GUIA_PASO_A_PASO.md       esta guía
├─ scripts/registrar_tarea.ps1    programa la carga diaria (paso 5)
├─ scripts/demo_calidad.py        demostración de calidad (paso 8)
├─ sql/01_crear_base.sql          base, esquemas y tablas (paso 1)
├─ sql/02_agregar_diario.sql      procedimiento de agregados (paso 4)
├─ sql/03_vistas_bi.sql           vistas para Power BI (paso 6)
├─ src/config.py                  parámetros y umbrales
├─ src/extraer.py                 extracción desde la API (paso 2)
├─ src/validar.py                 reglas de calidad (paso 3)
├─ src/cargar.py                  carga a SQL Server (paso 3)
├─ src/pipeline.py                orquestador (paso 4)
├─ tests/test_validar.py          pruebas de calidad (paso 4)
├─ datos/raw/                     JSON crudo (no versionado)
├─ logs/                          logs del pipeline (no versionados)
├─ requirements.txt
└─ README.md
```
