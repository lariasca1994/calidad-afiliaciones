// Página "Sin conexión": cada 8 s pregunta (HEAD, el service worker no lo intercepta) si el sitio
// responde y recarga cuando vuelve la red.
(function () {
  var TOTAL = 8, resto = TOTAL, revisando = false;
  var valor = document.getElementById("valor");
  var texto = document.getElementById("texto");
  var boton = document.getElementById("reintentar");
  if (!valor || !texto || !boton) return;
  function pintar() {
    valor.style.strokeDashoffset = revisando ? 0 : 1 - resto / TOTAL;
    texto.textContent = revisando ? "Comprobando…" : "Reintento automático en " + resto + " s";
  }
  function revisar() {
    if (revisando) return;
    revisando = true;
    boton.disabled = true;
    pintar();
    fetch("/login", { method: "HEAD", cache: "no-store" })
      .then(function (r) { if (r.status < 500) { location.reload(); return; } throw new Error("sin respuesta"); })
      .catch(function () { revisando = false; boton.disabled = false; resto = TOTAL; pintar(); });
  }
  boton.addEventListener("click", revisar);
  window.addEventListener("online", revisar);
  setInterval(function () { if (revisando) return; resto = resto > 0 ? resto - 1 : 0; if (resto === 0) revisar(); else pintar(); }, 1000);
  pintar();
})();
