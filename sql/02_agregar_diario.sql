-- 02_agregar_diario.sql
-- Procedimiento que (re)calcula agg.clima_diario a partir de clean.lectura_clima.
--   @dias_atras NULL  -> recalcula todos los días (carga histórica)
--   @dias_atras N     -> recalcula los últimos N días (carga incremental)
USE ClimaSDQ;
GO
CREATE OR ALTER PROCEDURE agg.sp_actualizar_diario
    @dias_atras          INT          = NULL,
    @umbral_calor_c      DECIMAL(5,2) = 32.0,
    @lecturas_por_dia    INT          = 24
AS
BEGIN
    SET NOCOUNT ON;
    DECLARE @desde DATE = CASE WHEN @dias_atras IS NULL THEN '1900-01-01'
                               ELSE DATEADD(DAY, -@dias_atras, CAST(SYSDATETIME() AS DATE)) END;

    MERGE agg.clima_diario AS d
    USING (
        SELECT CAST(fecha_hora AS DATE)                       AS fecha,
               CAST(MIN(temperatura_c)  AS DECIMAL(5,2))      AS temp_min_c,
               CAST(MAX(temperatura_c)  AS DECIMAL(5,2))      AS temp_max_c,
               CAST(AVG(temperatura_c)  AS DECIMAL(5,2))      AS temp_prom_c,
               CAST(AVG(humedad_pct)    AS DECIMAL(5,2))      AS humedad_prom_pct,
               CAST(SUM(precipitacion_mm) AS DECIMAL(7,2))    AS lluvia_total_mm,
               COUNT(*)                                       AS lecturas,
               CAST(CASE WHEN COUNT(*) = @lecturas_por_dia THEN 1 ELSE 0 END AS BIT) AS dia_completo,
               CAST(CASE WHEN MAX(temperatura_c) >= @umbral_calor_c THEN 1 ELSE 0 END AS BIT) AS calor_extremo
        FROM clean.lectura_clima
        WHERE CAST(fecha_hora AS DATE) >= @desde
        GROUP BY CAST(fecha_hora AS DATE)
    ) AS s ON d.fecha = s.fecha
    WHEN MATCHED THEN UPDATE SET
        temp_min_c = s.temp_min_c, temp_max_c = s.temp_max_c, temp_prom_c = s.temp_prom_c,
        humedad_prom_pct = s.humedad_prom_pct, lluvia_total_mm = s.lluvia_total_mm,
        lecturas = s.lecturas, dia_completo = s.dia_completo, calor_extremo = s.calor_extremo
    WHEN NOT MATCHED THEN INSERT
        (fecha, temp_min_c, temp_max_c, temp_prom_c, humedad_prom_pct, lluvia_total_mm,
         lecturas, dia_completo, calor_extremo)
        VALUES (s.fecha, s.temp_min_c, s.temp_max_c, s.temp_prom_c, s.humedad_prom_pct,
                s.lluvia_total_mm, s.lecturas, s.dia_completo, s.calor_extremo);
END;
GO
