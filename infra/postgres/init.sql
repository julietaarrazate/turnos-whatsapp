-- Roles de base de datos (ver ARCHITECTURE §7.2).
--   app_migrator: dueño del esquema; solo lo usan las migraciones.
--   app_runtime : rol de la aplicación; NO es dueño de las tablas, no hace bypass de RLS.
-- Local y CI usan autenticación `trust` (solo localhost), así que no hay contraseñas en el
-- repo. En staging/producción los roles se crean en Neon con contraseñas reales.
CREATE ROLE app_migrator LOGIN NOSUPERUSER NOBYPASSRLS;
CREATE ROLE app_runtime  LOGIN NOSUPERUSER NOBYPASSRLS;

CREATE DATABASE app OWNER app_migrator;
CREATE DATABASE app_test OWNER app_migrator;
