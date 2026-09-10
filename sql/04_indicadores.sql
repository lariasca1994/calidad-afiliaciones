-- =====================================================================
-- 04 · INDICADORES
--
-- Cada consulta responde a una pregunta del caso. Se devuelven siempre
-- el valor absoluto y el porcentaje: un 4% no dice nada si no se sabe
-- sobre cuantos registros se calcula.
-- =====================================================================


-- ---------------------------------------------------------------------
-- A · Tablero: las cifras de portada
-- ---------------------------------------------------------------------
SELECT
    'Producción consolidada'   AS indicador,
    COUNT(*)                   AS valor,
    NULL                       AS porcentaje
FROM consolidado

UNION ALL
SELECT 'Registros brutos (antes de depurar)',
       (SELECT COUNT(*) FROM vw_universo_tramites),
       NULL

UNION ALL
SELECT 'Producción efectiva (radicada)',
       SUM(es_produccion_efectiva),
       ROUND(SUM(es_produccion_efectiva) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Duplicidad multicanal',
       SUM(marca_duplicado_multicanal),
       ROUND(SUM(marca_duplicado_multicanal) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Duplicidad interna (mismo canal)',
       SUM(marca_duplicado_interno),
       ROUND(SUM(marca_duplicado_interno) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Documentos no homologados',
       SUM(marca_no_homologado),
       ROUND(SUM(marca_no_homologado) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Territorio incompleto',
       SUM(marca_territorio_incompleto),
       ROUND(SUM(marca_territorio_incompleto) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Registros críticos',
       SUM(marca_registro_critico),
       ROUND(SUM(marca_registro_critico) / COUNT(*) * 100, 2)
FROM consolidado

UNION ALL
SELECT 'Novedades laborales (fuera de producción)',
       (SELECT COUNT(*) FROM PROCESO_IRL),
       NULL

UNION ALL
SELECT 'Inconsistencia operativa IRL',
       (SELECT COUNT(*) FROM PROCESO_IRL WHERE TRIM(LOG_ERRORES) <> 'CARGUE_EXITOSO'),
       (SELECT ROUND(SUM(TRIM(LOG_ERRORES) <> 'CARGUE_EXITOSO') / COUNT(*) * 100, 2)
        FROM PROCESO_IRL);


-- ---------------------------------------------------------------------
-- B · Clasificación del trámite
-- ---------------------------------------------------------------------
SELECT
    clasificacion_tramite,
    COUNT(*) AS tramites,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2) AS participacion
FROM consolidado
GROUP BY clasificacion_tramite
ORDER BY tramites DESC;


-- ---------------------------------------------------------------------
-- C · Producción por fuente
--
-- Se muestran los registros aportados y los que sobreviven a la
-- depuracion. La diferencia es lo que cada canal pierde por duplicidad,
-- y explica por que la suma de canales no da la produccion total.
-- ---------------------------------------------------------------------
SELECT
    u.canal                    AS fuente,
    COUNT(*)                   AS registros_aportados,
    COALESCE(c.consolidados, 0) AS registros_consolidados,
    COUNT(*) - COALESCE(c.consolidados, 0) AS descartados_por_duplicidad,
    ROUND(COALESCE(c.consolidados, 0) / COUNT(*) * 100, 2) AS pct_sobrevive
FROM vw_universo_tramites u
LEFT JOIN (
    SELECT canal_origen, COUNT(*) AS consolidados
    FROM consolidado
    GROUP BY canal_origen
) c ON u.canal = c.canal_origen
GROUP BY u.canal, c.consolidados
ORDER BY registros_consolidados DESC;


-- ---------------------------------------------------------------------
-- D · Producción por régimen
-- ---------------------------------------------------------------------
SELECT
    regimen,
    COUNT(*) AS tramites,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2) AS participacion
FROM consolidado
GROUP BY regimen
ORDER BY tramites DESC;


-- ---------------------------------------------------------------------
-- E · Producción por asesor, con acumulado de Pareto
--
-- Responde a la concentracion 80/20 que pide el tablero: cuantos
-- asesores concentran el grueso de la produccion.
-- ---------------------------------------------------------------------
SELECT
    codigo_asesor,
    tramites,
    ROUND(tramites / SUM(tramites) OVER () * 100, 2) AS participacion,
    ROUND(SUM(tramites) OVER (ORDER BY tramites DESC) / SUM(tramites) OVER () * 100, 2) AS acumulado
FROM (
    SELECT
        COALESCE(codigo_asesor, 'SIN ASESOR') AS codigo_asesor,
        COUNT(*) AS tramites
    FROM consolidado
    GROUP BY COALESCE(codigo_asesor, 'SIN ASESOR')
) t
ORDER BY tramites DESC
LIMIT 30;


-- ---------------------------------------------------------------------
-- F · Producción por territorio
-- ---------------------------------------------------------------------
SELECT
    COALESCE(codigo_departamento, 'SIN DATO') AS departamento,
    COUNT(*) AS tramites,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2) AS participacion
FROM consolidado
GROUP BY COALESCE(codigo_departamento, 'SIN DATO')
ORDER BY tramites DESC;


-- ---------------------------------------------------------------------
-- G · Tendencia de producción
-- ---------------------------------------------------------------------
SELECT
    periodo,
    COUNT(*) AS tramites,
    SUM(clasificacion_tramite = 'Afiliación Nueva') AS afiliaciones_nuevas,
    SUM(clasificacion_tramite = 'Traslado')         AS traslados,
    SUM(clasificacion_tramite = 'Reinscripción')    AS reinscripciones
FROM consolidado
WHERE periodo IS NOT NULL
GROUP BY periodo
ORDER BY periodo;


-- ---------------------------------------------------------------------
-- H · Calidad por fuente
--
-- Se calcula sobre el universo bruto y no sobre el consolidado: el
-- objetivo es saber que canal envia datos sucios, y si se mira solo el
-- consolidado los registros descartados desaparecen del analisis.
-- ---------------------------------------------------------------------
SELECT
    canal AS fuente,
    COUNT(*) AS registros,
    ROUND(SUM(tipo_doc <> 'NO_HOMOLOGADO') / COUNT(*) * 100, 2) AS pct_homologacion,
    ROUND(SUM(NULLIF(num_doc, '') IS NOT NULL) / COUNT(*) * 100, 2) AS pct_documento_presente,
    ROUND(SUM(depto_id IS NOT NULL AND muni_id IS NOT NULL) / COUNT(*) * 100, 2) AS pct_territorio_completo,
    ROUND(SUM(fecha_radicacion IS NOT NULL) / COUNT(*) * 100, 2) AS pct_fecha_valida,
    COUNT(DISTINCT llave_afiliado) AS afiliados_distintos,
    COUNT(*) - COUNT(DISTINCT llave_afiliado) AS duplicados_internos
FROM vw_universo_tramites
GROUP BY canal
ORDER BY registros DESC;


-- ---------------------------------------------------------------------
-- I · Tipos de documento fuera de catálogo
--
-- Lista concreta de lo que hay que corregir en origen. Es el entregable
-- mas accionable del analisis de calidad.
-- ---------------------------------------------------------------------
SELECT
    canal AS fuente,
    tipo_doc_origen AS tipo_documento_recibido,
    COUNT(*) AS registros
FROM vw_universo_tramites
WHERE tipo_doc = 'NO_HOMOLOGADO'
GROUP BY canal, tipo_doc_origen
ORDER BY registros DESC;


-- ---------------------------------------------------------------------
-- J · Detalle de la duplicidad multicanal
-- ---------------------------------------------------------------------
SELECT
    CASE
        WHEN en_fisico AND en_digital AND en_sat THEN 'Físico + Digital + SAT'
        WHEN en_digital AND en_sat               THEN 'Digital + SAT'
        WHEN en_fisico  AND en_sat               THEN 'Físico + SAT'
        WHEN en_fisico  AND en_digital           THEN 'Físico + Digital'
        ELSE 'Un solo canal'
    END AS combinacion,
    COUNT(*) AS afiliados
FROM vw_duplicidad_multicanal
GROUP BY combinacion
ORDER BY afiliados DESC;


-- ---------------------------------------------------------------------
-- K · Novedades laborales: motivos de fallo
-- ---------------------------------------------------------------------
SELECT
    TRIM(LOG_ERRORES) AS resultado_cargue,
    COUNT(*) AS novedades,
    ROUND(COUNT(*) / SUM(COUNT(*)) OVER () * 100, 2) AS participacion
FROM PROCESO_IRL
GROUP BY TRIM(LOG_ERRORES)
ORDER BY novedades DESC;
