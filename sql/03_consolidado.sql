-- =====================================================================
-- 03 · CONSOLIDADO: CLASIFICACION Y MARCAS DE CALIDAD
--
-- Aqui se resuelven las dos cosas que definen la cifra:
--
--   1. Que tipo de tramite es cada registro.
--   2. Cual registro sobrevive cuando el mismo afiliado aparece en
--      varios canales.
--
-- Decision de diseno: la clasificacion y la calidad son dimensiones
-- SEPARADAS. Un traslado con el municipio vacio sigue siendo un
-- traslado; lo que tiene es una marca de calidad. Mezclarlas —devolver
-- 'Rechazado' como clasificacion— impide contar la produccion y medir
-- la calidad al mismo tiempo, que es justo lo que pide el caso.
-- =====================================================================

CREATE OR REPLACE VIEW vw_consolidado AS
WITH priorizado AS (
    SELECT
        u.*,
        -- Prioridad de canal ante duplicidad. Ver docs/decisiones.md:
        -- SAT prevalece por ser el registro oficial ante el Ministerio;
        -- el digital sobre el fisico por tener trazabilidad completa.
        ROW_NUMBER() OVER (
            PARTITION BY u.llave_afiliado
            ORDER BY
                CASE u.canal
                    WHEN 'SAT'          THEN 1
                    WHEN 'DIGITAL'      THEN 2
                    WHEN 'AFILIACIONES' THEN 3
                    ELSE 9
                END,
                -- Ante empate dentro del mismo canal, la radicacion mas
                -- antigua: es la que origino el tramite.
                u.fecha_radicacion ASC,
                u.id_origen ASC
        ) AS orden_prioridad
    FROM vw_universo_tramites u
)
SELECT
    p.llave_afiliado,
    p.canal                       AS canal_origen,
    p.id_origen                   AS id_radicado,
    p.tipo_doc                    AS tipo_documento_homologado,
    p.tipo_doc_origen             AS tipo_documento_recibido,
    p.num_doc                     AS numero_documento,
    p.fecha_radicacion,
    DATE_FORMAT(p.fecha_radicacion, '%Y-%m') AS periodo,
    p.codigo_asesor,
    p.depto_id                    AS codigo_departamento,
    p.muni_id                     AS codigo_municipio,
    p.nombre_ips,
    p.tipo_afiliado,
    p.estado_registro,

    -- Regimen normalizado: cada fuente lo escribe distinto.
    CASE
        WHEN p.regimen LIKE '%CONTRIBUTIVO%' THEN 'CONTRIBUTIVO'
        WHEN p.regimen LIKE '%SUBSIDIADO%'   THEN 'SUBSIDIADO'
        WHEN NULLIF(p.regimen, '') IS NULL   THEN 'SIN DATO'
        ELSE 'OTRO'
    END AS regimen,

    -- -----------------------------------------------------------------
    -- Clasificacion del tramite
    --
    -- El orden importa: se evalua el antecedente historico antes que la
    -- ausencia de antecedente. Las novedades laborales no llegan hasta
    -- aqui porque PROCESO_IRL nunca entra al universo de tramites.
    -- -----------------------------------------------------------------
    CASE
        WHEN x.estuvo_en_nueva_eps = 1 THEN 'Reinscripción'
        WHEN x.estuvo_en_otra_eps  = 1 THEN 'Traslado'
        ELSE 'Afiliación Nueva'
    END AS clasificacion_tramite,

    -- -----------------------------------------------------------------
    -- Marcas de calidad. Se acumulan; no reemplazan la clasificacion.
    -- -----------------------------------------------------------------
    CASE WHEN p.tipo_doc = 'NO_HOMOLOGADO' THEN 1 ELSE 0 END AS marca_no_homologado,

    CASE WHEN NULLIF(p.num_doc, '') IS NULL THEN 1 ELSE 0 END AS marca_documento_vacio,

    CASE WHEN p.depto_id IS NULL OR p.muni_id IS NULL THEN 1 ELSE 0 END AS marca_territorio_incompleto,

    CASE WHEN p.fecha_radicacion IS NULL THEN 1 ELSE 0 END AS marca_fecha_invalida,

    CASE WHEN COALESCE(d.canales_distintos, 1) > 1 THEN 1 ELSE 0 END AS marca_duplicado_multicanal,

    CASE WHEN COALESCE(d.repeticiones_internas, 0) > 0 THEN 1 ELSE 0 END AS marca_duplicado_interno,

    COALESCE(d.canales_distintos, 1)   AS canales_en_que_aparece,
    COALESCE(d.registros_totales, 1)   AS veces_radicado,

    -- Solo el canal digital reporta estado. Los estados anulado,
    -- rechazado y sin prerradicar corresponden a tramites que nunca
    -- llegaron a radicarse: cuentan como gestion, no como produccion.
    CASE
        WHEN p.canal <> 'DIGITAL' THEN 1
        WHEN p.estado_registro = 'RADICADO' THEN 1
        ELSE 0
    END AS es_produccion_efectiva,

    -- Registro critico: le falta algo imprescindible para operar.
    CASE
        WHEN p.tipo_doc = 'NO_HOMOLOGADO'
          OR NULLIF(p.num_doc, '') IS NULL
          OR p.fecha_radicacion IS NULL
        THEN 1 ELSE 0
    END AS marca_registro_critico

FROM priorizado p
LEFT JOIN vw_antecedente_xml x
       ON p.tipo_doc = x.tipo_doc
      AND p.num_doc  = x.num_doc
LEFT JOIN vw_duplicidad_multicanal d
       ON p.llave_afiliado = d.llave_afiliado
WHERE p.orden_prioridad = 1;
