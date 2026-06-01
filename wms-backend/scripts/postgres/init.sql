-- ─── WMS Panama — PostgreSQL Init Script ─────────────────────────────────────
-- Se ejecuta una sola vez al crear el container PostgreSQL por primera vez.
-- Crea extensiones necesarias y configura la BD.
-- ──────────────────────────────────────────────────────────────────────────────

-- Extensión para UUIDs (gen_random_uuid())
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";

-- Extensión para búsqueda full-text en español
CREATE EXTENSION IF NOT EXISTS "unaccent";

-- pg_trgm para búsqueda por similitud (LIKE con índice)
CREATE EXTENSION IF NOT EXISTS "pg_trgm";

-- Configuración de locale para búsqueda en español
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_ts_config WHERE cfgname = 'spanish_unaccent'
    ) THEN
        CREATE TEXT SEARCH CONFIGURATION spanish_unaccent (COPY = spanish);
        ALTER TEXT SEARCH CONFIGURATION spanish_unaccent
            ALTER MAPPING FOR hword, hword_part, word WITH unaccent, spanish_stem;
    END IF;
END $$;

-- Zona horaria por defecto: Panama (UTC-5, sin horario de verano)
SET timezone = 'America/Panama';
ALTER DATABASE wms_db SET timezone TO 'America/Panama';

-- Configuración de performance básica
ALTER SYSTEM SET shared_preload_libraries = 'pg_stat_statements';
ALTER SYSTEM SET log_min_duration_statement = '1000';  -- Log queries > 1 segundo

\echo 'WMS Panama — PostgreSQL init completado'
