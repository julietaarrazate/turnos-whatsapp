-- Roles de base de datos (ver ARCHITECTURE §7.2).
--   app_migrator: dueño del esquema; solo lo usan las migraciones.
--   app_runtime : rol de la aplicación; NO es dueño de las tablas, no hace bypass de RLS.
-- Las contraseñas de este archivo son SOLO para desarrollo local y CI.
CREATE ROLE app_migrator LOGIN PASSWORD 'app_migrator' NOSUPERUSER NOBYPASSRLS;
CREATE ROLE app_runtime  LOGIN PASSWORD 'app_runtime'  NOSUPERUSER NOBYPASSRLS;

CREATE DATABASE app OWNER app_migrator;
CREATE DATABASE app_test OWNER app_migrator;
