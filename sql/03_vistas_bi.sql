-- 03_vistas_bi.sql
-- Capa de consumo para Power BI. El dashboard lee solo estas vistas.
USE ClimaSDQ;
GO
IF SCHEMA_ID('bi') IS NULL EXEC('CREATE SCHEMA bi');
GO

CREATE OR ALTER VIEW bi.v_clima_horario AS
SELECT fecha_hora,
       CAST(fecha_hora AS DATE)                AS fecha,
       DATEPART(HOUR, fecha_hora)              AS hora,
       YEAR(fecha_hora)                        AS anio,
       MONTH(fecha_hora)                       AS mes_num,
       CHOOSE(MONTH(fecha_hora), 'Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio',
              'Agosto','Septiembre','Octubre','Noviembre','Diciembre') AS mes_nombre,
       FORMAT(fecha_hora, 'yyyy-MM')           AS anio_mes,
       temperatura_c, humedad_pct, precipitacion_mm
FROM clean.lectura_clima;
GO

-- Solo días completos (24 lecturas): un día parcial cambiaría de valor durante el día.
-- El día de la semana se calcula con una fecha ancla (1900-01-01 fue lunes), sin depender de DATEFIRST.
CREATE OR ALTER VIEW bi.v_clima_diario AS
SELECT fecha,
       YEAR(fecha)                             AS anio,
       MONTH(fecha)                            AS mes_num,
       CHOOSE(MONTH(fecha), 'Enero','Febrero','Marzo','Abril','Mayo','Junio','Julio',
              'Agosto','Septiembre','Octubre','Noviembre','Diciembre') AS mes_nombre,
       FORMAT(fecha, 'yyyy-MM')                AS anio_mes,
       (DATEDIFF(DAY, '19000101', fecha) % 7) + 1 AS dia_semana_num,
       CHOOSE((DATEDIFF(DAY, '19000101', fecha) % 7) + 1,
              'Lunes','Martes','Miércoles','Jueves','Viernes','Sábado','Domingo') AS dia_semana,
       temp_min_c, temp_max_c, temp_prom_c, humedad_prom_pct, lluvia_total_mm,
       CAST(calor_extremo AS INT)              AS calor_extremo,
       CAST(CASE WHEN lluvia_total_mm >= 1 THEN 1 ELSE 0 END AS INT) AS dia_lluvioso
FROM agg.clima_diario
WHERE dia_completo = 1;
GO

CREATE OR ALTER VIEW bi.v_calidad_datos AS
SELECT id_carga, inicio, fin, tipo, filas_leidas, filas_validas, filas_rechazadas,
       CAST(100.0 * filas_validas / NULLIF(filas_leidas, 0) AS DECIMAL(5,2)) AS pct_valido,
       estado, mensaje
FROM ops.log_carga;
GO

CREATE OR ALTER VIEW bi.v_rechazos AS
SELECT r.id_rechazo, r.id_carga, l.inicio AS fecha_carga, r.fecha_hora, r.motivo, r.valor_crudo
FROM ops.rechazos r
JOIN ops.log_carga l ON l.id_carga = r.id_carga;
GO
