(function () {
    var CLAVE = 'calidad-afiliaciones-tema';
    var boton = document.getElementById('alternar-tema');

    function temaActual() {
        return document.documentElement.getAttribute('data-tema') === 'oscuro' ? 'oscuro' : 'claro';
    }

    function aplicar(tema) {
        document.documentElement.setAttribute('data-tema', tema);
        if (boton) boton.textContent = tema === 'oscuro' ? '☀️' : '🌙';
        try {
            localStorage.setItem(CLAVE, tema);
        } catch (e) {}
    }

    try {
        var guardado = localStorage.getItem(CLAVE);
        aplicar(guardado === 'oscuro' ? 'oscuro' : temaActual());
    } catch (e) {
        aplicar(temaActual());
    }

    if (boton) {
        boton.addEventListener('click', function () {
            aplicar(temaActual() === 'oscuro' ? 'claro' : 'oscuro');
        });
    }
})();
