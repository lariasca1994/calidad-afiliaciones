-- =====================================================================
-- 01 · ESQUEMA
-- Tablas de origen (staging) tal como llegan de cada canal.
--
-- Criterio: en staging los campos entran como texto y sin restricciones.
-- Un archivo real trae fechas en tres formatos distintos, documentos con
-- espacios y valores fuera de catalogo; rechazarlos en la carga
-- impediria justamente medir la calidad, que es el objeto del ejercicio.
-- La conversion y la validacion ocurren despues, en las vistas.
-- =====================================================================

-- Aiven entrega la base ya creada, asi que no se usa CREATE DATABASE.
--
-- Nota: cada tabla salvo HOMOLOGACION_DOCUMENTOS lleva una clave primaria
-- tecnica (fila_id). No forma parte del modelo de negocio: los servicios
-- gestionados exigen clave primaria en toda tabla por requisitos de
-- replicacion. De paso permite rastrear una fila hasta su archivo de
-- origen.

DROP VIEW  IF EXISTS vw_consolidado;
DROP VIEW  IF EXISTS vw_duplicidad_multicanal;
DROP VIEW  IF EXISTS vw_universo_tramites;
DROP VIEW  IF EXISTS vw_antecedente_xml;
DROP VIEW  IF EXISTS vw_homologacion_sat;

DROP TABLE IF EXISTS HOMOLOGACION_DOCUMENTOS;
DROP TABLE IF EXISTS AFILIACIONES;
DROP TABLE IF EXISTS DIGITAL;
DROP TABLE IF EXISTS SAT;
DROP TABLE IF EXISTS PROCESO_IRL;
DROP TABLE IF EXISTS XML_HISTORICO;


-- ---------------------------------------------------------------------
-- Catalogo maestro de tipos de documento
--
-- Ojo: CODIGO NO es unico. 'NIT' aparece dos veces, con abreviaturas NI
-- y NT y el mismo codigo 4. Por eso la llave primaria es Abreviatura, y
-- por eso el cruce de SAT contra CODIGO se hace sobre una vista que
-- deduplica (ver 02_homologacion.sql): sin ella, un documento de tipo 4
-- generaria dos filas y duplicaria la produccion.
-- ---------------------------------------------------------------------
CREATE TABLE HOMOLOGACION_DOCUMENTOS (
    Tipo_Documento_Afiliado VARCHAR(100),
    CODIGO                  INT,
    Abreviatura             VARCHAR(5) PRIMARY KEY,
    INDEX idx_hom_codigo (CODIGO)
);


-- ---------------------------------------------------------------------
-- Canal fisico
-- ---------------------------------------------------------------------
CREATE TABLE AFILIACIONES (
    fila_id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    ID                       INT,
    CODIGOASESOR             VARCHAR(20),
    SOLICITUD                VARCHAR(50),
    TIPODOCUMENTO            VARCHAR(5),
    NUMERODOCUMENTO          VARCHAR(20),
    DEPARTAMENTOID           VARCHAR(5),
    MUNICIPIOID              VARCHAR(5),
    CODIGOAFILIACION         VARCHAR(20),
    NOMBREIPS                VARCHAR(200),
    CANTBENEFICIARIO         VARCHAR(10),
    TIPODOCUMENTOEMPLEADOR   VARCHAR(5),
    NUMERODOCUMENTOEMPLEADOR VARCHAR(20),
    FECHARADICACION          VARCHAR(30),
    REGIMEN                  VARCHAR(50),
    TIPOAFILIACION           VARCHAR(100),
    SISBEN                   VARCHAR(10),
    POBLACIONESPECIAL        VARCHAR(500),
    EXCEPCIONTRASLADO        VARCHAR(5),
    CAUSALEXCEPCION          VARCHAR(255),
    INDEX idx_afi_doc (TIPODOCUMENTO, NUMERODOCUMENTO),
    INDEX idx_afi_id  (ID)
);


-- ---------------------------------------------------------------------
-- Canal digital
--
-- La granularidad es por persona, no por tramite: un grupo familiar
-- comparte IDPRODUCCION y genera una fila por cotizante y por
-- beneficiario. Ver docs/decisiones.md.
-- ---------------------------------------------------------------------
CREATE TABLE DIGITAL (
    fila_id                      BIGINT AUTO_INCREMENT PRIMARY KEY,
    IDPRODUCCION                 INT,
    ESTADOAFILIACION             VARCHAR(50),
    DESCRIPCIONESTADO            VARCHAR(100),
    FECHASOLICITUD               VARCHAR(30),
    FECHARADICACION              VARCHAR(30),
    TIPOREGIMEN                  VARCHAR(50),
    CODIGOASESOR                 VARCHAR(20),
    TIPOAFILIACION               VARCHAR(100),
    CONTRIBUSOLIDARIA            VARCHAR(5),
    TIPOCOTIZANTE                VARCHAR(50),
    INTERNOMEDICINA              VARCHAR(20),
    CARGO                        VARCHAR(50),
    TIPOAFILIADO                 VARCHAR(50),
    PARENTESCO                   VARCHAR(50),
    TIPODOCUMENTOAFILIADO        VARCHAR(5),
    NUM_AFILIADO                 VARCHAR(20),
    NOMBRE1                      VARCHAR(100),
    NOMBRE2                      VARCHAR(100),
    APELLIDO1                    VARCHAR(100),
    APELLIDO2                    VARCHAR(100),
    FECHANACIMIENTO              VARCHAR(30),
    SEXO_IDENTIFICACION          VARCHAR(5),
    NACIONALIDAD                 VARCHAR(50),
    PAISNACIMIENTO               VARCHAR(50),
    DANE_NACIMIENTO              VARCHAR(15),
    DEPARTAMENTONACIMIENTO       VARCHAR(100),
    MUNICIPIONACIMIENTO          VARCHAR(100),
    ZONA                         VARCHAR(50),
    DANE_RESIDENCIA              VARCHAR(15),
    CODIGOIPS                    VARCHAR(20),
    COMUNIDADINDIGENA            VARCHAR(100),
    ENCUESTASISBEN               VARCHAR(20),
    NIVELSISBEN                  VARCHAR(10),
    SUBGRUPOSISBEN               VARCHAR(10),
    TIPODOCUMENTOEMPLEADOR       VARCHAR(5),
    NUMERODOCUMENTOEMPLEADOR     VARCHAR(20),
    TARIFACONTRIBUCIONSOLIDARIA  VARCHAR(20),
    METODOLOGIAGRUPOPOBLACIONAL  VARCHAR(100),
    TIPOPOBLACIONESPECIAL        VARCHAR(20),
    DISCAPACIDAD                 VARCHAR(5),
    TIPODECONDICION              VARCHAR(10),
    FECHANOVEDAD                 VARCHAR(30),
    NOFORMULARIOVIRTUAL          VARCHAR(50),
    RUTAARCHIVOS                 VARCHAR(255),
    CAUSALEXCEPCION              VARCHAR(50),
    DESCRIPCIONCAUSALEXCEPCION   VARCHAR(255),
    CERTIFICACION_GRUPO_FAMILIAR VARCHAR(5),
    SOPORTE_QUEJA_SUPER_SALUD    VARCHAR(5),
    TRASLADO                     VARCHAR(5),
    VALOREPSANTERIOR             VARCHAR(100),
    INDEX idx_dig_doc (TIPODOCUMENTOAFILIADO, NUM_AFILIADO),
    INDEX idx_dig_id  (IDPRODUCCION),
    INDEX idx_dig_est (ESTADOAFILIACION)
);


-- ---------------------------------------------------------------------
-- Canal SAT (MinSalud). El tipo de documento viene como codigo numerico,
-- a diferencia del resto de fuentes, que usan la abreviatura.
-- ---------------------------------------------------------------------
CREATE TABLE SAT (
    fila_id                  BIGINT AUTO_INCREMENT PRIMARY KEY,
    ID                       INT,
    NORADICADOSAT            VARCHAR(100),
    CODIGOASESOR             VARCHAR(20),
    TIPODOCUMENTO            VARCHAR(5),
    NUMERODOCUMENTOAFILIADO  VARCHAR(20),
    SOLICITUD                VARCHAR(100),
    FECHARADICACION          VARCHAR(30),
    REGIMEN                  VARCHAR(50),
    TIPODOCUMENTOEMPLEADOR   VARCHAR(5),
    NUMERODOCUMENTOEMPLEADOR VARCHAR(20),
    TIPOCOTIZANTE            VARCHAR(50),
    CANTBENEFICIARIO         VARCHAR(10),
    DEPARTAMENTOID           VARCHAR(5),
    MUNICIPIOID              VARCHAR(5),
    CODIGOAFILIACION         VARCHAR(20),
    NOMBREIPS                VARCHAR(200),
    CODIGOOCUPACION          VARCHAR(20),
    NOMBREOCUPACION          VARCHAR(200),
    INDEX idx_sat_doc (TIPODOCUMENTO, NUMERODOCUMENTOAFILIADO),
    INDEX idx_sat_id  (ID)
);


-- ---------------------------------------------------------------------
-- Novedades de relaciones laborales. NO son afiliaciones: quedan fuera
-- del conteo de produccion y se reportan aparte.
-- ---------------------------------------------------------------------
CREATE TABLE PROCESO_IRL (
    fila_id           BIGINT AUTO_INCREMENT PRIMARY KEY,
    TIPO_DOC          VARCHAR(5),
    NUMDOC            VARCHAR(20),
    CARGO             VARCHAR(100),
    TIPO_DOC_EMP      VARCHAR(5),
    NUMEMP            VARCHAR(20),
    FECHADEINGRESO    VARCHAR(30),
    ASESOR            VARCHAR(50),
    TIPO_DE_EMPLEADOR VARCHAR(100),
    TIPO_DE_RESPUESTA VARCHAR(100),
    N_ARCHIVO         VARCHAR(255),
    F_RECIBIDO        VARCHAR(30),
    F_PROCESO         VARCHAR(30),
    ORIGEN            VARCHAR(100),
    LOG_ERRORES       VARCHAR(255),
    ID_TRAMITE        VARCHAR(50),
    INDEX idx_irl_doc (TIPO_DOC, NUMDOC),
    INDEX idx_irl_log (LOG_ERRORES)
);


-- ---------------------------------------------------------------------
-- Radicacion historica. Determina si el afiliado ya estuvo en la EPS y
-- en cual entidad, que es lo que separa reinscripcion de traslado.
-- ---------------------------------------------------------------------
CREATE TABLE XML_HISTORICO (
    fila_id                   BIGINT AUTO_INCREMENT PRIMARY KEY,
    IDENTIFICADOR             VARCHAR(50),
    SERIAL                    VARCHAR(50),
    TIPO_IDENTIFICACION       VARCHAR(5),
    NUMERO_IDENTIFICACION     VARCHAR(20),
    PRIMER_NOMBRE             VARCHAR(100),
    SEGUNDO_NOMBRE            VARCHAR(100),
    PRIMER_APELLIDO           VARCHAR(100),
    SEGUNDO_APELLIDO          VARCHAR(100),
    NACIMIENTO_FECHA          VARCHAR(30),
    DEPTO                     VARCHAR(60),
    MUNI                      VARCHAR(80),
    ESTADO                    VARCHAR(50),
    ENT_ID                    VARCHAR(20),
    ENTIDAD                   VARCHAR(150),
    REGIMEN                   VARCHAR(50),
    FECHA_CONTRATO            VARCHAR(60),
    FECHA_FIN_CONTRATO        VARCHAR(30),
    AFILIACION_ENTIDAD_FECHA  VARCHAR(30),
    ESTADO_FECHA              VARCHAR(30),
    TIPO_AFILIADO             VARCHAR(50),
    FECHA_AFILIACION_EFECTIVA VARCHAR(30),
    cantidad_grp_fml          VARCHAR(10),
    cruce_bdex_rnec           VARCHAR(20),
    fecha_novedad             VARCHAR(30),
    CANAL                     VARCHAR(50),
    ID_TRAMITE_RADICADO       VARCHAR(50),
    FECHA_CONSULTA            VARCHAR(30),
    INDEX idx_xml_doc (TIPO_IDENTIFICACION, NUMERO_IDENTIFICACION),
    INDEX idx_xml_ent (ENTIDAD)
);
