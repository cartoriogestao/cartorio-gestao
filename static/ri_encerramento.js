/* HOTFIX-2026-10-08-08 — «Encerrar matrícula» pelo formulário de lavrar.
 *
 * O botão «Encerrar matrícula» abre o formulário de sempre com o modelo do
 * encerramento no texto. Aqui: trocar de modelo (pergunta se o texto já foi
 * editado), levar a matrícula de destino para o trecho «PREENCHER…» do texto
 * e não deixar enviar enquanto sobrar «PREENCHER…» (a rota também recusa).
 * A natureza acompanha o modelo: é ela que a ficha imprime como título do ato.
 */
(function () {
  "use strict";
  var MARCA = "\u00abPREENCHER";
  var DESTINO = /\u00abPREENCHER: (?:nova matr\u00edcula|matr\u00edcula de destino|matr\u00edculas abertas)\u00bb/g;

  function avisar(el) {
    try { el.dispatchEvent(new Event("input", { bubbles: true })); } catch (e) { /* navegador antigo */ }
  }

  function iniciar() {
    var sel = document.querySelector("[data-encerramento-modelo]");
    if (!sel) { return; }
    var form = sel.closest("form");
    if (!form) { return; }
    var teor = form.querySelector('textarea[name="teor"]');
    var motivo = form.querySelector('input[name="encerra_motivo"]');
    var destino = form.querySelector('input[name="encerra_destino"]');
    var natureza = form.querySelector('input[name="natureza_titulo"]');
    var original = teor ? teor.value : "";
    var anterior = sel.value;

    sel.addEventListener("change", function () {
      var t = form.querySelector('template[data-encerramento-teor="' + sel.value + '"]');
      if (!t || !teor) { return; }
      if (teor.value !== original &&
          !window.confirm("Trocar o modelo substitui o texto do ato que você já editou. Continuar?")) {
        sel.value = anterior;
        return;
      }
      teor.value = t.content ? t.content.textContent : t.textContent;
      original = teor.value;
      anterior = sel.value;
      if (motivo) { motivo.value = t.getAttribute("data-motivo") || ""; }
      if (natureza && t.getAttribute("data-natureza")) { natureza.value = t.getAttribute("data-natureza"); }
      if (destino && (destino.value || "").trim()) { levarDestino(); }
      avisar(teor);
    });

    function levarDestino() {
      var v = (destino.value || "").trim();
      if (!v || !teor) { return; }
      DESTINO.lastIndex = 0;
      if (DESTINO.test(teor.value)) {
        DESTINO.lastIndex = 0;
        var mudou = teor.value === original;
        teor.value = teor.value.replace(DESTINO, v);
        if (mudou) { original = teor.value; }
        avisar(teor);
      }
    }
    if (destino) { destino.addEventListener("change", levarDestino); }

    form.addEventListener("submit", function (ev) {
      if (teor && teor.value.indexOf(MARCA) >= 0) {
        ev.preventDefault();
        window.alert("O texto do ato ainda tem trechos «PREENCHER…» do modelo de encerramento. " +
                     "Troque-os pelo texto definitivo antes de lavrar.");
        teor.focus();
      }
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
