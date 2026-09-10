-- =====================================================================
-- 05 · USUARIOS DEL PANEL WEB
--
-- A propósito, NO se incluye en 01_esquema.sql: ese archivo empieza con
-- DROP TABLE/DROP VIEW porque cada corrida de "python setup.py" reconstruye
-- el pipeline de datos desde cero. La cuenta del panel no debe desaparecer
-- cada vez que se recarga el consolidado, así que vive en su propio
-- script, y solo la ejecuta scripts/crear_admin.py (CREATE TABLE IF NOT
-- EXISTS: nunca se borra ni se recrea).
-- =====================================================================

CREATE TABLE IF NOT EXISTS usuarios (
    id INT AUTO_INCREMENT PRIMARY KEY,
    email VARCHAR(255) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    creado_en DATETIME DEFAULT CURRENT_TIMESTAMP
);
