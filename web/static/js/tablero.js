/* Tablero gerencial: indicadores, hallazgos, origen de los datos y gráficos.
 *
 * Todo sale del JSON que el servidor deja en #datos-tablero (ver
 * web/tablero_datos.py): cada consulta trae el canal como dimensión, así
 * que el filtro "Ver canal" recalcula aquí, sin volver al servidor. Los
 * colores se leen de las variables CSS de tablero.css, y los gráficos se
 * redibujan al cambiar de tema. */
(function () {
    "use strict";

    var nodoDatos = document.getElementById("datos-tablero");
    if (!nodoDatos || typeof Chart === "undefined") return;
    var DATOS = JSON.parse(nodoDatos.textContent);

    var CANALES = { DIGITAL: "Digital", AFILIACIONES: "Físico", SAT: "SAT" };
    var ORDEN_CANALES = ["DIGITAL", "AFILIACIONES", "SAT"];
    var FUENTES_ORIGEN = {
        AFILIACIONES: ["Canal físico", "Puntos de atención presencial", "--t-canal-fisico"],
        DIGITAL: ["Canal digital", "Portal y aplicación", "--t-canal-digital"],
        SAT: ["SAT", "Radicación oficial ante el Ministerio", "--t-canal-sat"],
        XML_HISTORICO: ["Radicación histórica", "Antecedente de cada afiliado", "--t-suave"],
        PROCESO_IRL: ["Novedades laborales", "Contexto: no son afiliaciones", "--t-suave"],
        HOMOLOGACION_DOCUMENTOS: ["Catálogo de documentos", "Traduce los tipos de documento", "--t-suave"],
    };
    var MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"];

    var canal = "";          // "" = todos
    var graficos = {};

    // ───── utilidades ─────
    function css(variable) {
        return getComputedStyle(document.documentElement).getPropertyValue(variable).trim();
    }
    var numero = new Intl.NumberFormat("es-CO");
    function n(valor) { return numero.format(Math.round(valor || 0)); }
    function pct(parte, total, decimales) {
        if (!total) return 0;
        return Math.round((parte / total) * 100 * Math.pow(10, decimales || 1)) / Math.pow(10, decimales || 1);
    }
    function fpct(valor) { return String(valor).replace(".", ",") + " %"; }
    function mes(periodo) {
        var partes = String(periodo).split("-");
        return MESES[Number(partes[1]) - 1] + " " + partes[0];
    }
    function delCanal(filas) {
        return canal ? filas.filter(function (f) { return f.canal === canal; }) : filas;
    }
    function sumar(filas, campo) {
        return filas.reduce(function (t, f) { return t + (Number(f[campo]) || 0); }, 0);
    }
    function agrupar(filas, clave, campo) {
        var mapa = {};
        filas.forEach(function (f) { mapa[f[clave]] = (mapa[f[clave]] || 0) + (Number(f[campo]) || 0); });
        return mapa;
    }
    function el(etiqueta, clase, texto) {
        var nodo = document.createElement(etiqueta);
        if (clase) nodo.className = clase;
        if (texto != null) nodo.textContent = texto;
        return nodo;
    }
    function semaforo(valor, bueno, regular, mayorEsMejor) {
        var ok = mayorEsMejor ? valor >= bueno : valor <= bueno;
        var medio = mayorEsMejor ? valor >= regular : valor <= regular;
        return ok ? ["bien", "Bien"] : medio ? ["alerta", "Revisar"] : ["mal", "Atención"];
    }

    // ───── indicadores ─────
    function calcular() {
        var k = delCanal(DATOS.kpis);
        var fuentes = canal ? DATOS.fuentes.filter(function (f) { return f.fuente === canal; }) : DATOS.fuentes;
        return {
            consolidados: sumar(k, "consolidados"),
            efectiva: sumar(k, "efectiva"),
            dupMulti: sumar(k, "dup_multicanal"),
            dupInterna: sumar(k, "dup_interna"),
            noHomologado: sumar(k, "no_homologado"),
            territorio: sumar(k, "territorio_incompleto"),
            fecha: sumar(k, "fecha_invalida"),
            critico: sumar(k, "critico"),
            recibidos: sumar(fuentes, "aportados"),
            descartados: sumar(fuentes, "descartados"),
        };
    }

    function pintarKpis(t) {
        var calidad = pct(t.consolidados - t.noHomologado - t.territorio, t.consolidados);
        var tarjetas = [
            ["Producción consolidada", n(t.consolidados), "de " + n(t.recibidos) + " registros recibidos", ["neutro", "Cifra única"],
             "Afiliaciones únicas: una por persona, aunque haya radicado por varios canales o varias veces. Es la cifra en la que se puede confiar."],
            ["Producción efectiva", fpct(pct(t.efectiva, t.consolidados)), n(t.efectiva) + " trámites radicados", semaforo(pct(t.efectiva, t.consolidados), 90, 80, true),
             "Parte del consolidado que quedó radicada. Lo anulado, rechazado o sin prerradicar no cuenta como producción. Referencia: 90 % o más."],
            ["Duplicidad multicanal", fpct(pct(t.dupMulti, t.consolidados)), n(t.dupMulti) + " personas en más de un canal", semaforo(pct(t.dupMulti, t.consolidados), 1, 3, false),
             "Personas que radicaron por más de un canal. Sumar los canales sin depurar las contaría dos veces. Referencia: hasta 1 %."],
            ["Duplicidad interna", fpct(pct(t.dupInterna, t.consolidados)), n(t.dupInterna) + " radicaciones repetidas", semaforo(pct(t.dupInterna, t.consolidados), 5, 8, false),
             "La misma persona aparece varias veces dentro de un mismo canal. Suele venir de reenvíos o reprocesos. Referencia: hasta 5 %."],
            ["Calidad del dato", fpct(calidad), "documento y territorio completos", semaforo(calidad, 97, 92, true),
             "Registros con tipo de documento reconocido y con departamento y municipio. Referencia: 97 % o más."],
            ["Registros críticos", fpct(pct(t.critico, t.consolidados)), n(t.critico) + " no se pueden contar con confianza", semaforo(pct(t.critico, t.consolidados), 1, 3, false),
             "Registros con un problema que impide contarlos con confianza, como documento vacío o fuera de catálogo. Referencia: hasta 1 %."],
        ];
        var cont = document.getElementById("kpis");
        cont.textContent = "";
        tarjetas.forEach(function (d, i) {
            var tarjeta = el("article", "tb-tarjeta tb-kpi estado-" + d[3][0]);
            var titulo = el("p", "tb-kpi-titulo");
            var nombre = el("span", null, d[0]);
            var info = el("button", "tb-info", "?");
            info.type = "button";
            info.setAttribute("aria-label", "Qué significa " + d[0]);
            info.setAttribute("aria-expanded", "false");
            var globo = el("div", "tb-globo", d[4]);
            globo.hidden = true;
            globo.id = "globo-" + i;
            info.setAttribute("aria-controls", globo.id);
            info.addEventListener("click", function () {
                var abrir = globo.hidden;
                document.querySelectorAll(".tb-globo").forEach(function (g) { g.hidden = true; });
                document.querySelectorAll(".tb-info").forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
                globo.hidden = !abrir;
                info.setAttribute("aria-expanded", String(abrir));
            });
            titulo.append(nombre, el("span", "tb-semaforo", d[3][1]), info);
            tarjeta.append(titulo, el("p", "tb-kpi-valor", d[1]), el("p", "tb-kpi-detalle", d[2]), globo);
            cont.append(tarjeta);
        });
        document.getElementById("nota-filtro").textContent =
            canal ? "Solo el canal " + CANALES[canal] + "." : "Todos los canales.";
    }

    // ───── hallazgos en lenguaje sencillo ─────
    function pintarHallazgos(t) {
        var lista = [];
        var efectiva = pct(t.efectiva, t.consolidados);
        lista.push([efectiva >= 90 ? "bien" : efectiva >= 80 ? "alerta" : "mal",
            "De cada 100 afiliaciones únicas, " + Math.round(efectiva) + " quedaron radicadas" +
            (efectiva < 90 ? ": hay más anulados o rechazados de lo habitual." : ".")]);

        if (!canal) {
            var porCanal = agrupar(DATOS.kpis, "canal", "consolidados");
            var mayor = Object.keys(porCanal).sort(function (a, b) { return porCanal[b] - porCanal[a]; })[0];
            if (mayor) lista.push(["neutro", "El canal " + CANALES[mayor] + " aporta el " +
                fpct(pct(porCanal[mayor], t.consolidados, 0)) + " de la producción consolidada."]);
        }

        var recibidosDe = t.recibidos ? pct(t.descartados, t.recibidos) : 0;
        if (t.descartados) lista.push([recibidosDe > 8 ? "alerta" : "neutro",
            "Se descartaron " + n(t.descartados) + " registros repetidos (" + fpct(recibidosDe) +
            " de lo recibido): sin depurar, la producción se habría inflado en esa cantidad."]);

        var interna = pct(t.dupInterna, t.consolidados);
        if (interna > 5) lista.push(["mal", "La duplicidad interna (" + fpct(interna) +
            ") supera la referencia de 5 %: conviene revisar reenvíos dentro del mismo canal."]);

        var tendencia = agrupar(delCanal(DATOS.tendencia), "periodo", "tramites");
        var meses = Object.keys(tendencia).sort();
        if (meses.length > 1) {
            var pico = meses.reduce(function (a, b) { return tendencia[b] > tendencia[a] ? b : a; });
            var promedio = sumar(meses.map(function (m) { return { v: tendencia[m] }; }), "v") / meses.length;
            lista.push(["neutro", "El mes con más trámites fue " + mes(pico) + " (" + n(tendencia[pico]) +
                "), " + Math.round(pct(tendencia[pico] - promedio, promedio, 0)) + " % por encima del promedio mensual."]);
        }

        var peor = DATOS.calidad.slice().sort(function (a, b) { return a.territorio - b.territorio; })[0];
        if (peor && peor.territorio < 97) lista.push([peor.territorio < 92 ? "mal" : "alerta",
            CANALES[peor.fuente] + " es la fuente con menos territorio completo (" + fpct(peor.territorio) +
            "): faltan departamento o municipio."]);

        var fuera = sumar(DATOS.sin_homologar, "registros");
        if (fuera) lista.push(["alerta", "Llegaron " + n(fuera) + " registros con un tipo de documento fuera de catálogo. " +
            "Se corrige agregando la equivalencia al catálogo, no borrando datos."]);

        var cont = document.getElementById("hallazgos");
        cont.textContent = "";
        lista.forEach(function (h) {
            var item = el("li", "estado-" + h[0]);
            item.append(el("span", null, h[1]));
            cont.append(item);
        });
    }

    // ───── origen de los datos y embudo ─────
    function pintarOrigen(t) {
        var cont = document.getElementById("fuentes-origen");
        cont.textContent = "";
        DATOS.origen.forEach(function (f) {
            var info = FUENTES_ORIGEN[f.fuente] || [f.fuente, "", "--t-suave"];
            var fila = el("div", "tb-fuente");
            fila.style.setProperty("--color", css(info[2]));
            var texto = el("span", null, info[0]);
            texto.append(el("small", null, info[1]));
            fila.append(texto, el("strong", null, n(f.filas)));
            cont.append(fila);
        });

        var total = sumar(DATOS.kpis, "consolidados");
        var resultado = document.getElementById("resultado-origen");
        resultado.textContent = "";
        resultado.append(el("strong", null, n(total)), el("span", null, "afiliaciones únicas en el consolidado"));

        var pasos = [
            ["Registros recibidos (3 canales)", t.recibidos, "--t-canal-sat"],
            ["Descartados por estar repetidos", t.descartados, "--t-mal"],
            ["Consolidado: una fila por afiliado", t.consolidados, "--t-acento"],
            ["Producción efectiva (radicada)", t.efectiva, "--t-bien"],
        ];
        var embudo = document.getElementById("embudo");
        embudo.textContent = "";
        pasos.forEach(function (p) {
            var fila = el("div", "tb-embudo-fila");
            var barra = el("div", "tb-embudo-barra");
            var relleno = el("span");
            relleno.style.width = Math.max(pct(p[1], t.recibidos), 0.5) + "%";
            relleno.style.setProperty("--color", css(p[2]));
            barra.append(relleno);
            fila.append(el("span", null, p[0]), barra, el("strong", null, n(p[1])));
            embudo.append(fila);
        });
    }

    // ───── gráficos ─────
    function base() {
        Chart.defaults.font.family = "system-ui, -apple-system, 'Segoe UI', sans-serif";
        Chart.defaults.color = css("--t-suave");
        Chart.defaults.borderColor = css("--t-rejilla");
        Chart.defaults.plugins.legend.labels.usePointStyle = true;
        Chart.defaults.plugins.tooltip.backgroundColor = css("--t-texto");
        Chart.defaults.plugins.tooltip.titleColor = css("--t-tarjeta");
        Chart.defaults.plugins.tooltip.bodyColor = css("--t-tarjeta");
        Chart.defaults.plugins.tooltip.padding = 10;
        Chart.defaults.maintainAspectRatio = false;
        Chart.defaults.animation = window.matchMedia("(prefers-reduced-motion: reduce)").matches ? false : { duration: 700 };
    }

    function dibujar(id, config) {
        if (graficos[id]) graficos[id].destroy();
        graficos[id] = new Chart(document.getElementById(id), config);
    }

    function colorCanal(c) {
        return css({ DIGITAL: "--t-canal-digital", AFILIACIONES: "--t-canal-fisico", SAT: "--t-canal-sat" }[c] || "--t-suave");
    }

    function graficoTendencia() {
        var filas = delCanal(DATOS.tendencia);
        var tramites = agrupar(filas, "periodo", "tramites");
        var efectiva = agrupar(filas, "periodo", "efectiva");
        var duplicados = agrupar(filas, "periodo", "duplicados");
        var meses = Object.keys(tramites).sort();

        // Un último mes con muy pocos trámites suele estar incompleto (el
        // periodo cerró a mitad de mes o solo entraron radicaciones tardías):
        // en la línea parece un desplome que no lo es. Se avisa debajo.
        var nota = document.getElementById("nota-tendencia");
        var valores = meses.map(function (m) { return tramites[m]; }).sort(function (a, b) { return a - b; });
        var mediana = valores[Math.floor(valores.length / 2)] || 0;
        var ultimo = meses[meses.length - 1];
        var incompleto = meses.length > 2 && tramites[ultimo] < mediana * 0.25;
        nota.hidden = !incompleto;
        if (incompleto) {
            nota.textContent = "El último mes (" + mes(ultimo) + ") está incompleto: solo tiene " + n(tramites[ultimo]) +
                " trámites, de radicaciones que cayeron después del cierre del periodo. No es una caída de la producción.";
        }
        dibujar("grafico-tendencia", {
            data: {
                labels: meses.map(mes),
                datasets: [
                    { type: "line", label: "Trámites", data: meses.map(function (m) { return tramites[m]; }),
                      borderColor: css("--t-acento"), backgroundColor: css("--t-acento-suave"), fill: true,
                      tension: 0.3, pointRadius: 3, yAxisID: "y",
                      // El tramo hacia un mes incompleto va punteado.
                      segment: { borderDash: function (ctx) { return incompleto && ctx.p1DataIndex === meses.length - 1 ? [4, 4] : undefined; } } },
                    { type: "line", label: "Producción efectiva", data: meses.map(function (m) { return efectiva[m] || 0; }),
                      borderColor: css("--t-bien"), borderDash: [6, 4], tension: 0.3, pointRadius: 2, yAxisID: "y" },
                    { type: "bar", label: "Duplicados", data: meses.map(function (m) { return duplicados[m] || 0; }),
                      backgroundColor: css("--t-canal-sat"), borderRadius: 4, yAxisID: "y", barPercentage: 0.5 },
                ],
            },
            options: {
                interaction: { mode: "index", intersect: false },
                scales: { y: { beginAtZero: true, ticks: { precision: 0 } }, x: { grid: { display: false } } },
                plugins: { tooltip: { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + n(c.parsed.y); } } } },
            },
        });
    }

    function graficoFuentes() {
        var filas = ORDEN_CANALES.map(function (c) {
            return DATOS.fuentes.filter(function (f) { return f.fuente === c; })[0] || { fuente: c, consolidados: 0, descartados: 0 };
        });
        dibujar("grafico-fuentes", {
            type: "bar",
            data: {
                labels: filas.map(function (f) { return CANALES[f.fuente]; }),
                datasets: [
                    { label: "Quedaron en el consolidado", data: filas.map(function (f) { return f.consolidados; }),
                      backgroundColor: filas.map(function (f) { return colorCanal(f.fuente) + (canal && f.fuente !== canal ? "55" : ""); }),
                      borderRadius: 6 },
                    { label: "Descartados (repetidos)", data: filas.map(function (f) { return f.descartados; }),
                      backgroundColor: css("--t-rejilla"), borderRadius: 6 },
                ],
            },
            options: {
                indexAxis: "y",
                scales: { x: { stacked: true, beginAtZero: true }, y: { stacked: true, grid: { display: false } } },
                plugins: { tooltip: { callbacks: { label: function (c) { return " " + c.dataset.label + ": " + n(c.parsed.x); } } } },
            },
        });
    }

    function dona(id, mapa, colores) {
        var claves = Object.keys(mapa).sort(function (a, b) { return mapa[b] - mapa[a]; });
        var total = claves.reduce(function (t, k) { return t + mapa[k]; }, 0);
        dibujar(id, {
            type: "doughnut",
            data: {
                labels: claves,
                datasets: [{ data: claves.map(function (k) { return mapa[k]; }),
                             backgroundColor: claves.map(function (k, i) { return colores[i % colores.length]; }),
                             borderColor: css("--t-tarjeta"), borderWidth: 2 }],
            },
            options: {
                cutout: "62%",
                plugins: {
                    legend: { position: window.innerWidth < 760 ? "bottom" : "right" },
                    tooltip: { callbacks: { label: function (c) { return " " + c.label + ": " + n(c.parsed) + " (" + fpct(pct(c.parsed, total)) + ")"; } } },
                },
            },
        });
    }

    function graficoClasificacion() {
        dona("grafico-clasificacion", agrupar(delCanal(DATOS.clasificacion), "clasificacion", "tramites"),
             [css("--t-acento"), css("--t-canal-fisico"), css("--t-canal-sat"), css("--t-alerta")]);
        document.getElementById("nota-clasificacion").textContent =
            canal ? "Solo el canal " + CANALES[canal] + "." : "Todos los canales.";
    }

    function graficoEstados() {
        var mapa = agrupar(delCanal(DATOS.estados), "estado", "tramites");
        var claves = Object.keys(mapa).sort(function (a, b) { return mapa[b] - mapa[a]; });
        // Físico y SAT no reportan estado: lo que llega por ellos ya está
        // radicado y cuenta como producción efectiva (ver sql/03_consolidado.sql).
        var radicado = { RADICADO: "Radicado (digital)", "SIN ESTADO": "Radicado (físico y SAT)" };
        dibujar("grafico-estados", {
            type: "bar",
            data: {
                labels: claves.map(function (k) { return radicado[k] || k.charAt(0) + k.slice(1).toLowerCase(); }),
                datasets: [{ label: "Trámites", data: claves.map(function (k) { return mapa[k]; }),
                             backgroundColor: claves.map(function (k) { return radicado[k] ? css("--t-bien") : css("--t-alerta"); }),
                             borderRadius: 5 }],
            },
            options: { indexAxis: "y", plugins: { legend: { display: false } },
                       scales: { x: { type: "logarithmic", title: { display: true, text: "escala logarítmica" } }, y: { grid: { display: false } } } },
        });
    }

    function graficoRegimen() {
        var mapa = agrupar(delCanal(DATOS.regimen), "regimen", "tramites");
        var claves = Object.keys(mapa).sort();
        dibujar("grafico-regimen", {
            type: "bar",
            data: {
                labels: claves.map(function (k) { return k.charAt(0) + k.slice(1).toLowerCase(); }),
                datasets: [{ label: "Trámites", data: claves.map(function (k) { return mapa[k]; }),
                             backgroundColor: [css("--t-acento"), css("--t-canal-fisico"), css("--t-canal-sat")], borderRadius: 6 }],
            },
            options: { plugins: { legend: { display: false } }, scales: { y: { beginAtZero: true }, x: { grid: { display: false } } } },
        });
    }

    function graficoTerritorio() {
        var mapa = agrupar(delCanal(DATOS.territorio), "depto", "tramites");
        var claves = Object.keys(mapa).sort(function (a, b) { return mapa[b] - mapa[a]; }).slice(0, 10);
        dibujar("grafico-territorio", {
            type: "bar",
            data: {
                labels: claves,
                datasets: [{ label: "Trámites", data: claves.map(function (k) { return mapa[k]; }),
                             backgroundColor: claves.map(function (k) { return k === "Sin dato" ? css("--t-mal") : css("--t-acento"); }),
                             borderRadius: 5 }],
            },
            options: { indexAxis: "y", plugins: { legend: { display: false } },
                       scales: { x: { beginAtZero: true }, y: { grid: { display: false } } } },
        });
    }

    // ───── tablas ─────
    function tablaCalidad() {
        var tabla = document.getElementById("tabla-calidad");
        tabla.textContent = "";
        var cabecera = el("tr");
        ["Canal", "Homologación", "Territorio", "Fecha válida"].forEach(function (t) { cabecera.append(el("th", null, t)); });
        tabla.append(cabecera);
        DATOS.calidad.forEach(function (f) {
            var fila = el("tr");
            if (canal && f.fuente !== canal) fila.style.opacity = "0.4";
            fila.append(el("td", null, CANALES[f.fuente] || f.fuente));
            ["homologacion", "territorio", "fecha_valida"].forEach(function (campo) {
                var valor = Number(f[campo]);
                var estado = semaforo(valor, 95, 85, true)[0];
                var celda = el("td", "estado-" + estado, fpct(Math.round(valor * 10) / 10));
                celda.style.background = "var(--estado-suave)";
                celda.style.color = "var(--estado)";
                fila.append(celda);
            });
            tabla.append(fila);
        });
    }

    function tablaSinHomologar() {
        var tabla = document.getElementById("tabla-sin-homologar");
        tabla.textContent = "";
        if (!DATOS.sin_homologar.length) {
            var fila = el("tr");
            fila.append(el("td", null, "Ninguno: todos los tipos de documento están en el catálogo."));
            tabla.append(fila);
            return;
        }
        var cabecera = el("tr");
        ["Canal", "Tipo recibido", "Registros"].forEach(function (t) { cabecera.append(el("th", null, t)); });
        tabla.append(cabecera);
        DATOS.sin_homologar.forEach(function (f) {
            var fila = el("tr");
            fila.append(el("td", null, CANALES[f.fuente] || f.fuente), el("td", null, f.recibido || "(vacío)"), el("td", null, n(f.registros)));
            tabla.append(fila);
        });
    }

    // ───── orquestación ─────
    function todo() {
        var t = calcular();
        pintarKpis(t);
        pintarHallazgos(t);
        pintarOrigen(t);
        tablaCalidad();
        tablaSinHomologar();
        base();
        graficoTendencia();
        graficoFuentes();
        graficoClasificacion();
        graficoEstados();
        graficoRegimen();
        graficoTerritorio();
    }

    document.getElementById("filtro-canal").addEventListener("click", function (e) {
        var boton = e.target.closest("button[data-canal]");
        if (!boton) return;
        canal = boton.dataset.canal;
        this.querySelectorAll("button").forEach(function (b) { b.setAttribute("aria-pressed", String(b === boton)); });
        todo();
    });

    // Los globos de ayuda se cierran al tocar fuera o con Escape.
    document.addEventListener("click", function (e) {
        if (!e.target.closest(".tb-kpi")) document.querySelectorAll(".tb-globo").forEach(function (g) { g.hidden = true; });
    });
    document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") document.querySelectorAll(".tb-globo").forEach(function (g) { g.hidden = true; });
    });

    // Resalta en la barra la sección visible.
    if ("IntersectionObserver" in window) {
        var enlaces = document.querySelectorAll(".tb-secciones a");
        var observador = new IntersectionObserver(function (entradas) {
            entradas.forEach(function (entrada) {
                if (!entrada.isIntersecting) return;
                enlaces.forEach(function (a) {
                    a.setAttribute("aria-current", String(a.getAttribute("href") === "#" + entrada.target.id));
                });
            });
        }, { rootMargin: "-40% 0px -55% 0px" });
        document.querySelectorAll(".tb-seccion").forEach(function (s) { observador.observe(s); });
    }

    // Al cambiar el tema, los colores salen de otras variables: se redibuja.
    new MutationObserver(todo).observe(document.documentElement, { attributes: true, attributeFilter: ["data-tema"] });

    todo();
})();
