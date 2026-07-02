-- WMS Panamá — inicialización de PostgreSQL
-- Se ejecuta una sola vez al crear el volumen de datos (docker-entrypoint-initdb.d).
-- El esquema lo gestiona Alembic (alembic upgrade head); aquí solo extensiones base.

CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "pg_trgm";    -- búsquedas por similitud
