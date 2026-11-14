// Mantenimiento: un anillo cuenta 60 s y la página se reintenta sola, a lo sumo 5 veces seguidas
// (la base sin servidor no debe despertarse en bucle); después queda el botón "Reintentar".
(function () {
    var TOTAL = 60, MAX = 5, CLAVE = "calidad-reintentos";
    var valor = document.getElementById("valor");
    var texto = document.getElementById("texto");
    if (!valor || !texto) return;
    var hechos = 0;
    try { hechos = parseInt(sessionStorage.getItem(CLAVE) || "0", 10) || 0; } catch (e) { /* sin almacenamiento */ }
    if (hechos >= MAX) {
        valor.style.strokeDashoffset = 1;
        texto.textContent = "Sin reintentos automáticos: prueba más tarde";
        return;
    }
    var resto = TOTAL;
    function pintar() {
        valor.style.strokeDashoffset = 1 - resto / TOTAL;
        texto.textContent = resto > 0 ? "Nuevo intento en " + resto + " s" : "Comprobando…";
    }
    pintar();
    setInterval(function () {
        if (resto <= 0) return;
        resto--;
        pintar();
        if (resto === 0) {
            try { sessionStorage.setItem(CLAVE, String(hechos + 1)); } catch (e) { /* sin almacenamiento */ }
            location.reload();
        }
    }, 1000);
})();
