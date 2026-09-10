-- =====================================================================
-- 03b · MATERIALIZACION DEL CONSOLIDADO
--
-- vw_consolidado encadena tres vistas y una funcion de ventana sobre mas
-- de 76.000 registros. Consultarla ocho veces —una por indicador— obliga
-- al motor a rehacer el calculo cada vez y a escribir resultados
-- intermedios en disco temporal, hasta agotarlo en servicios de plan
-- gratuito.
--
-- Materializarla resuelve las dos cosas: el calculo ocurre una sola vez
-- y los indicadores leen de una tabla indexada. El costo es que no se
-- actualiza sola: hay que recrearla tras cada carga, aceptable en un
-- proceso que corre por lotes.
--
-- Ademas es la tabla a la que se conecta Power Query desde Excel: una
-- consulta a tabla indexada responde al instante, una vista encadenada
-- haria lenta cada actualizacion del libro.
-- =====================================================================

DROP TABLE IF EXISTS consolidado;

CREATE TABLE consolidado (
    fila_id BIGINT AUTO_INCREMENT PRIMARY KEY,

    llave_afiliado             VARCHAR(30),
    canal_origen                VARCHAR(20),
    id_radicado                 VARCHAR(50),
    tipo_documento_homologado   VARCHAR(15),
    tipo_documento_recibido     VARCHAR(5),
    numero_documento            VARCHAR(20),
    fecha_radicacion            DATE,
    periodo                     VARCHAR(7),
    codigo_asesor                VARCHAR(20),
    codigo_departamento          VARCHAR(5),
    codigo_municipio             VARCHAR(15),
    nombre_ips                   VARCHAR(200),
    tipo_afiliado                VARCHAR(50),
    estado_registro               VARCHAR(50),
    regimen                      VARCHAR(20),
    clasificacion_tramite        VARCHAR(20),

    marca_no_homologado          TINYINT,
    marca_documento_vacio        TINYINT,
    marca_territorio_incompleto  TINYINT,
    marca_fecha_invalida         TINYINT,
    marca_duplicado_multicanal   TINYINT,
    marca_duplicado_interno      TINYINT,
    marca_registro_critico       TINYINT,
    es_produccion_efectiva       TINYINT,

    canales_en_que_aparece      INT,
    veces_radicado               INT,

    INDEX idx_con_canal  (canal_origen),
    INDEX idx_con_clas   (clasificacion_tramite),
    INDEX idx_con_per    (periodo),
    INDEX idx_con_reg    (regimen),
    INDEX idx_con_asesor (codigo_asesor)
);

INSERT INTO consolidado (
    llave_afiliado, canal_origen, id_radicado, tipo_documento_homologado,
    tipo_documento_recibido, numero_documento, fecha_radicacion, periodo,
    codigo_asesor, codigo_departamento, codigo_municipio, nombre_ips,
    tipo_afiliado, estado_registro, regimen, clasificacion_tramite,
    marca_no_homologado, marca_documento_vacio, marca_territorio_incompleto,
    marca_fecha_invalida, marca_duplicado_multicanal, marca_duplicado_interno,
    marca_registro_critico, es_produccion_efectiva,
    canales_en_que_aparece, veces_radicado
)
SELECT
    llave_afiliado, canal_origen, id_radicado, tipo_documento_homologado,
    tipo_documento_recibido, numero_documento, fecha_radicacion, periodo,
    codigo_asesor, codigo_departamento, codigo_municipio, nombre_ips,
    tipo_afiliado, estado_registro, regimen, clasificacion_tramite,
    marca_no_homologado, marca_documento_vacio, marca_territorio_incompleto,
    marca_fecha_invalida, marca_duplicado_multicanal, marca_duplicado_interno,
    marca_registro_critico, es_produccion_efectiva,
    canales_en_que_aparece, veces_radicado
FROM vw_consolidado;
