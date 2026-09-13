-- =====================================================================
-- 02 · HOMOLOGACION DOCUMENTAL Y LLAVE UNICA
--
-- Cada fuente identifica el tipo de documento a su manera: SAT usa el
-- codigo numerico del catalogo y las demas usan la abreviatura. Sin
-- unificarlo no hay forma de saber que 'CC' y '3' son la misma persona,
-- y la duplicidad entre canales queda invisible.
--
-- usuario_id viaja por todas estas vistas a partir de aqui. Es lo que
-- permite que dos cuentas puedan generar y ver datos de ejemplo al mismo
-- tiempo sin mezclarse: sin esta columna, dos personas que por azar
-- generan un mismo numero de documento apareceriamos como el mismo
-- afiliado duplicado entre ellas, lo cual seria incorrecto y ademas
-- filtraria informacion de una cuenta a otra.
-- =====================================================================


-- ---------------------------------------------------------------------
-- Catalogo deduplicado por codigo. Sin usuario_id: es el mismo catalogo
-- para todo el mundo (ver 01_esquema.sql).
--
-- 'NIT' figura dos veces con el mismo CODIGO 4 y abreviaturas distintas
-- (NI y NT). Un cruce directo contra CODIGO devolveria dos filas por
-- cada documento de ese tipo y duplicaria la produccion. Se toma la
-- primera abreviatura por orden alfabetico y se deja constancia.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_homologacion_sat AS
SELECT
    CODIGO,
    MIN(Abreviatura) AS Abreviatura,
    COUNT(*)         AS abreviaturas_en_catalogo
FROM HOMOLOGACION_DOCUMENTOS
WHERE CODIGO IS NOT NULL
GROUP BY CODIGO;


-- ---------------------------------------------------------------------
-- Universo de tramites de afiliacion, normalizado.
--
-- PROCESO_IRL queda deliberadamente fuera: son novedades laborales, no
-- afiliaciones. Incluirlas inflaria la produccion en mas de 167.000
-- registros. Se analizan aparte, en 04_indicadores.sql.
--
-- La fecha se convierte aqui porque cada fuente trae un formato
-- distinto: dd/mm/aa en el canal fisico y en SAT, y aaaa-mm-dd hh:mm:ss
-- en el digital. Sin normalizarla no hay serie de tiempo posible.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_universo_tramites AS

-- Canal fisico
SELECT
    a.usuario_id                                     AS usuario_id,
    'AFILIACIONES'                                   AS canal,
    CAST(a.ID AS CHAR)                               AS id_origen,
    COALESCE(h.Abreviatura, 'NO_HOMOLOGADO')         AS tipo_doc,
    TRIM(a.NUMERODOCUMENTO)                          AS num_doc,
    CONCAT(COALESCE(h.Abreviatura, 'NO_HOMOLOGADO'), '-', TRIM(a.NUMERODOCUMENTO)) AS llave_afiliado,
    a.TIPODOCUMENTO                                  AS tipo_doc_origen,
    STR_TO_DATE(NULLIF(TRIM(a.FECHARADICACION), ''), '%d/%m/%y') AS fecha_radicacion,
    UPPER(TRIM(a.REGIMEN))                           AS regimen,
    NULLIF(TRIM(a.DEPARTAMENTOID), '')               AS depto_id,
    NULLIF(TRIM(a.MUNICIPIOID), '')                  AS muni_id,
    NULLIF(TRIM(a.CODIGOASESOR), '')                 AS codigo_asesor,
    NULLIF(TRIM(a.NOMBREIPS), '')                    AS nombre_ips,
    NULL                                             AS estado_registro,
    NULL                                             AS tipo_afiliado,
    a.TIPOAFILIACION                                 AS tipo_afiliacion_origen
FROM AFILIACIONES a
LEFT JOIN HOMOLOGACION_DOCUMENTOS h
       ON TRIM(a.TIPODOCUMENTO) = h.Abreviatura

UNION ALL

-- Canal digital
SELECT
    d.usuario_id,
    'DIGITAL',
    CAST(d.IDPRODUCCION AS CHAR),
    COALESCE(h.Abreviatura, 'NO_HOMOLOGADO'),
    TRIM(d.NUM_AFILIADO),
    CONCAT(COALESCE(h.Abreviatura, 'NO_HOMOLOGADO'), '-', TRIM(d.NUM_AFILIADO)),
    d.TIPODOCUMENTOAFILIADO,
    -- Si no hay radicacion se usa la solicitud: los estados anulado,
    -- rechazado y sin prerradicar no llegan a radicarse, pero si tienen
    -- fecha de solicitud. Sin esto perderian toda referencia temporal.
    COALESCE(
        STR_TO_DATE(NULLIF(TRIM(d.FECHARADICACION), ''), '%Y-%m-%d %H:%i:%s'),
        STR_TO_DATE(NULLIF(TRIM(d.FECHASOLICITUD), ''),  '%Y-%m-%d %H:%i:%s')
    ),
    UPPER(TRIM(d.TIPOREGIMEN)),
    NULLIF(LEFT(TRIM(d.DANE_RESIDENCIA), 2), ''),
    NULLIF(TRIM(d.DANE_RESIDENCIA), ''),
    NULLIF(TRIM(d.CODIGOASESOR), ''),
    NULLIF(TRIM(d.CODIGOIPS), ''),
    UPPER(TRIM(d.ESTADOAFILIACION)),
    UPPER(TRIM(d.TIPOAFILIADO)),
    d.TIPOAFILIACION
FROM DIGITAL d
LEFT JOIN HOMOLOGACION_DOCUMENTOS h
       ON TRIM(d.TIPODOCUMENTOAFILIADO) = h.Abreviatura

UNION ALL

-- Canal SAT: cruce por codigo numerico, contra el catalogo deduplicado
SELECT
    s.usuario_id,
    'SAT',
    CAST(s.ID AS CHAR),
    COALESCE(hs.Abreviatura, 'NO_HOMOLOGADO'),
    TRIM(s.NUMERODOCUMENTOAFILIADO),
    CONCAT(COALESCE(hs.Abreviatura, 'NO_HOMOLOGADO'), '-', TRIM(s.NUMERODOCUMENTOAFILIADO)),
    s.TIPODOCUMENTO,
    STR_TO_DATE(NULLIF(TRIM(s.FECHARADICACION), ''), '%d/%m/%y'),
    UPPER(TRIM(s.REGIMEN)),
    NULLIF(TRIM(s.DEPARTAMENTOID), ''),
    NULLIF(TRIM(s.MUNICIPIOID), ''),
    NULLIF(TRIM(s.CODIGOASESOR), ''),
    NULLIF(TRIM(s.NOMBREIPS), ''),
    NULL,
    NULL,
    s.SOLICITUD
FROM SAT s
LEFT JOIN vw_homologacion_sat hs
       ON NULLIF(TRIM(s.TIPODOCUMENTO), '') = CAST(hs.CODIGO AS CHAR);


-- ---------------------------------------------------------------------
-- Antecedente en la radicacion historica.
--
-- Es lo que separa reinscripcion de traslado, y por eso no basta con
-- saber si el afiliado existe: hay que saber en que entidad estuvo.
--
-- 'NUEVA EPS S.A. -CM' tambien es Nueva EPS, de modo que la comparacion
-- va por prefijo y no por igualdad.
--
-- Se agrupa por usuario_id + documento porque un mismo afiliado puede
-- tener varios registros historicos, y porque dos cuentas distintas no
-- deben cruzarse aunque compartan un numero de documento por azar.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_antecedente_xml AS
SELECT
    usuario_id,
    TRIM(TIPO_IDENTIFICACION) AS tipo_doc,
    TRIM(NUMERO_IDENTIFICACION) AS num_doc,
    MAX(CASE WHEN UPPER(ENTIDAD) LIKE 'NUEVA EPS%' THEN 1 ELSE 0 END) AS estuvo_en_nueva_eps,
    MAX(CASE WHEN UPPER(ENTIDAD) NOT LIKE 'NUEVA EPS%'
              AND NULLIF(TRIM(ENTIDAD), '') IS NOT NULL THEN 1 ELSE 0 END) AS estuvo_en_otra_eps,
    COUNT(*) AS registros_historicos
FROM XML_HISTORICO
WHERE NULLIF(TRIM(NUMERO_IDENTIFICACION), '') IS NOT NULL
GROUP BY usuario_id, TRIM(TIPO_IDENTIFICACION), TRIM(NUMERO_IDENTIFICACION);


-- ---------------------------------------------------------------------
-- Presencia de cada afiliado en los canales.
--
-- Se separan dos fenomenos que suelen confundirse y que tienen causas
-- distintas:
--
--   - Duplicidad MULTICANAL: el mismo afiliado radica por vias
--     diferentes. Es un problema de integracion entre sistemas.
--   - Duplicidad INTERNA: radica varias veces por la misma via. Es un
--     problema de control en el punto de captura.
--
-- Sumarlas en una sola cifra oculta cual de los dos hay que atacar.
-- Igual que arriba, se agrupa tambien por usuario_id para no mezclar la
-- duplicidad de una cuenta con la de otra.
-- ---------------------------------------------------------------------
CREATE OR REPLACE VIEW vw_duplicidad_multicanal AS
SELECT
    usuario_id,
    llave_afiliado,
    COUNT(DISTINCT canal)       AS canales_distintos,
    COUNT(*)                    AS registros_totales,
    COUNT(*) - COUNT(DISTINCT canal) AS repeticiones_internas,
    MAX(canal = 'AFILIACIONES') AS en_fisico,
    MAX(canal = 'DIGITAL')      AS en_digital,
    MAX(canal = 'SAT')          AS en_sat
FROM vw_universo_tramites
WHERE tipo_doc <> 'NO_HOMOLOGADO'
  AND NULLIF(num_doc, '') IS NOT NULL
GROUP BY usuario_id, llave_afiliado;
