/* ORDENAR SEM VOLTAR AO TOPO (of-0143).
 *
 * Ordenar continua sendo um link (ver `templates/_ordenar.html`): a página recarrega de verdade.
 * Por isso a posição é guardada no clique e devolvida ao abrir, nas duas rolagens que existem:
 * a da tela e a da tabela, porque `.table-wrap` tem altura máxima e a lista longa rola por dentro dela.
 *
 * O prazo e o caminho impedem que uma visita seguinte abra rolada sozinha.
 * Sem `sessionStorage`, a página só abre no topo, como antes.
 */
(function () {
  "use strict";
  var GUARDA = "cg-ordenar-rolagem";
  var PRAZO = 30 * 1000;

  // No layout novo rola `.cg-rolagem`; no antigo, e na tela estreita do novo, rola a própria página.
  function quemRola() {
    var r = document.querySelector(".cg-rolagem");
    if (r && getComputedStyle(r).overflowY !== "visible" && r.scrollHeight > r.clientHeight) return r;
    return document.scrollingElement || document.documentElement;
  }

  document.addEventListener("click", function (ev) {
    // Ctrl, Shift ou o botão do meio abrem outra aba: esta fica onde está, e nada pode sobrar guardado.
    if (ev.defaultPrevented || ev.button !== 0 || ev.ctrlKey || ev.shiftKey || ev.metaKey || ev.altKey) return;
    var link = ev.target.closest ? ev.target.closest("a.ordenar") : null;
    if (!link) return;
    var tabela = link.closest(".table-wrap");
    try {
      sessionStorage.setItem(GUARDA, JSON.stringify({
        caminho: location.pathname,
        em: Date.now(),
        tela: quemRola().scrollTop,
        tabelaTopo: tabela ? tabela.scrollTop : 0,
        tabelaLado: tabela ? tabela.scrollLeft : 0
      }));
    } catch (erro) { /* sem isto, abre no topo */ }
  });

  // O guardado se consome sempre: sem isto, reabriria rolada numa visita seguinte.
  var salvo = null;
  try {
    salvo = JSON.parse(sessionStorage.getItem(GUARDA) || "null");
    sessionStorage.removeItem(GUARDA);
  } catch (erro) { return; }
  if (!salvo || salvo.caminho !== location.pathname) return;
  var idade = Date.now() - salvo.em;
  if (!(idade >= 0 && idade < PRAZO)) return;

  // "instant": `app.css` tem `scroll-behavior:smooth`, e a tela deslizaria a partir do topo.
  // Se a lista ficou mais curta, o navegador para no fim.
  var link = document.querySelector("a.ordenar");
  var tabela = link ? link.closest(".table-wrap") : null;
  if (tabela) tabela.scrollTo({ top: salvo.tabelaTopo, left: salvo.tabelaLado, behavior: "instant" });
  quemRola().scrollTo({ top: salvo.tela, behavior: "instant" });
})();
