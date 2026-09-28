-- 01_crear_base.sql
-- Crea la base ClimaSDQ, los esquemas por capa y las tablas del pipeline.
-- Es idempotente: se puede ejecutar varias veces sin error.
IF DB_ID('ClimaSDQ') IS NULL CREATE DATABASE ClimaSDQ;
GO
USE ClimaSDQ;
GO
-- Capas del pipeline
IF SCHEMA_ID('raw')   IS NULL EXEC('CREATE SCHEMA raw');
IF SCHEMA_ID('clean') IS NULL EXEC('CREATE SCHEMA clean');
IF SCHEMA_ID('agg')   IS NULL EXEC('CREATE SCHEMA agg');
IF SCHEMA_ID('ops')   IS NULL EXEC('CREATE SCHEMA ops');
GO

-- Datos tal como llegan de la API
IF OBJECT_ID('raw.lectura_clima') IS NULL
CREATE TABLE raw.lectura_clima (
    id_raw           BIGINT IDENTITY PRIMARY KEY,
    fecha_hora       DATETIME2(0) NULL,
    temperatura_c    DECIMAL(5,2) NULL,
    humedad_pct      DECIMAL(5,2) NULL,
    precipitacion_mm DECIMAL(6,2) NULL,
    fecha_carga      DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    id_carga         INT NULL
);

-- Datos validados (una fila por hora)
IF OBJECT_ID('clean.lectura_clima') IS NULL
CREATE TABLE clean.lectura_clima (
    fecha_hora       DATETIME2(0) NOT NULL PRIMARY KEY,
    temperatura_c    DECIMAL(5,2) NOT NULL,
    humedad_pct      DECIMAL(5,2) NOT NULL,
    precipitacion_mm DECIMAL(6,2) NOT NULL,
    fecha_carga      DATETIME2(0) NOT NULL DEFAULT SYSDATETIME()
);

-- Resumen diario
IF OBJECT_ID('agg.clima_diario') IS NULL
CREATE TABLE agg.clima_diario (
    fecha            DATE PRIMARY KEY,
    temp_min_c       DECIMAL(5,2),
    temp_max_c       DECIMAL(5,2),
    temp_prom_c      DECIMAL(5,2),
    humedad_prom_pct DECIMAL(5,2),
    lluvia_total_mm  DECIMAL(7,2),
    lecturas         INT,
    dia_completo     BIT,
    calor_extremo    BIT
);

-- Operación del pipeline
IF OBJECT_ID('ops.log_carga') IS NULL
CREATE TABLE ops.log_carga (
    id_carga         INT IDENTITY PRIMARY KEY,
    inicio           DATETIME2(0) NOT NULL DEFAULT SYSDATETIME(),
    fin              DATETIME2(0) NULL,
    tipo             VARCHAR(20)  NOT NULL,  -- 'historica' | 'incremental'
    filas_leidas     INT NULL,
    filas_validas    INT NULL,
    filas_rechazadas INT NULL,
    estado           VARCHAR(20)  NOT NULL,  -- 'ok' | 'error'
    mensaje          NVARCHAR(500) NULL
);

IF OBJECT_ID('ops.rechazos') IS NULL
CREATE TABLE ops.rechazos (
    id_rechazo  BIGINT IDENTITY PRIMARY KEY,
    id_carga    INT NOT NULL,
    fecha_hora  DATETIME2(0) NULL,
    motivo      VARCHAR(100) NOT NULL,
    valor_crudo NVARCHAR(200) NULL
);
GO
