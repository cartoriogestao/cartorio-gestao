// O PAPEL TI NÃO SELA ATOS (T015, decisão do titular de 24/11/2026).
//
// Carregado só para quem é TI (base.html e base_novo.html). Desabilita o que
// sela: o botão «Selar…», o formulário que posta para uma rota de selar e o
// campo do selo digitado. É a cortesia da tela — quem RECUSA é o servidor
// (`papeis.barrar_selo`, no ponto mais baixo do selo); aqui só se evita o
// clique que vai dar na recusa.
(function () {
  "use strict";
  var MSG = "O papel TI não sela atos.";
  var TEXTO = /\bselar\b/i;
  var CAMPOS = 'input[name="selo"], input[name="selo_texto"], textarea[name="selo_texto"], ' +
               'input[name="selo_a_mao"], textarea[name="selo_a_mao"]';

  function marcar(el) {
    if (el.dataset.tiNaoSela) { return; }
    el.dataset.tiNaoSela = "1";
    el.setAttribute("aria-disabled", "true");
    el.setAttribute("title", MSG);
    if ("disabled" in el) { el.disabled = true; }
    el.style.opacity = "0.5";
    el.style.cursor = "not-allowed";
  }

  function formDeSelar(form) {
    var acao = (form.getAttribute("action") || "").toLowerCase();
    return (form.method || "").toLowerCase() === "post" && acao.indexOf("selar") !== -1;
  }

  function varrer(raiz) {
    raiz.querySelectorAll("button, input[type=submit], summary, a.button").forEach(function (el) {
      var texto = (el.textContent || el.value || "").trim();
      if (TEXTO.test(texto)) { marcar(el); }
    });
    raiz.querySelectorAll("form").forEach(function (form) {
      if (formDeSelar(form)) {
        form.querySelectorAll("button, input[type=submit]").forEach(marcar);
      }
      if (form.method && form.method.toLowerCase() === "post") {
        form.querySelectorAll(CAMPOS).forEach(marcar);
      }
    });
  }

  document.addEventListener("click", function (ev) {
    var el = ev.target && ev.target.closest ? ev.target.closest("[data-ti-nao-sela]") : null;
    if (el) { ev.preventDefault(); ev.stopPropagation(); window.alert(MSG); }
  }, true);
  document.addEventListener("submit", function (ev) {
    if (ev.target && formDeSelar(ev.target)) { ev.preventDefault(); window.alert(MSG); }
  }, true);
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", function () { varrer(document); });
  } else {
    varrer(document);
  }
})();
