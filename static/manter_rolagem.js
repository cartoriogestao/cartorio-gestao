/* O BOTÃO CONTINUA EMBAIXO DO MOUSE (oficial, 02/11/2026: «cada vez que clica num botão no sistema ele volta
 * pra parte de cima da tela»).
 *
 * Gravar é formulário de verdade: o servidor responde com um redirecionamento, e a página recarrega no
 * topo. Por isso, no envio, guarda-se QUAL botão foi clicado e A QUE ALTURA DA JANELA ele estava; ao abrir
 * de novo a MESMA tela, a página rola até aquele botão voltar à mesma altura. Pela altura do botão, e não
 * pelo número de pixels rolados: o aviso verde que aparece no alto empurra tudo para baixo, e a conta em
 * pixels deixaria o botão longe do mouse.
 *
 * Fica como era: a outra tela (o caminho mudou), o endereço com âncora (`#quadro`, quem respondeu quis
 * levar a outro lugar), o que passou do prazo, e a página sem `sessionStorage`. A ordenação das listas
 * tem o seu (`ordenar_rolagem.js`).
 */
(function () {
  "use strict";
  var GUARDA = "cg-botao-rolagem";
  var PRAZO = 30 * 1000;

  // No layout novo rola `.cg-rolagem`; no antigo, e na tela estreita do novo, rola a própria página.
  function quemRola() {
    var r = document.querySelector(".cg-rolagem");
    if (r && getComputedStyle(r).overflowY !== "visible" && r.scrollHeight > r.clientHeight) return r;
    return document.scrollingElement || document.documentElement;
  }

  // Como achar o mesmo botão na página nova: o destino do formulário, o rótulo do botão e a ordem
  // entre os iguais (a lista tem um «Excluir» por linha).
  function assinatura(botao) {
    var form = botao.form || botao.closest("form");
    var destino = form ? (form.getAttribute("action") || location.pathname) : "";
    var rotulo = (botao.name || "") + "|" + (botao.value || "") + "|" + (botao.textContent || "").trim();
    return destino + "§" + rotulo;
  }

  function iguais(alvo) {
    var lista = [];
    document.querySelectorAll("button, input[type=submit]").forEach(function (b) {
      if (assinatura(b) === alvo) lista.push(b);
    });
    return lista;
  }

  var clicado = null;
  document.addEventListener("click", function (ev) {
    var b = ev.target.closest ? ev.target.closest("button, input[type=submit]") : null;
    clicado = b && (b.type || "submit").toLowerCase() === "submit" ? b : null;
  }, true);

  document.addEventListener("submit", function (ev) {
    var form = ev.target;
    // Formulário que abre em outra aba deixa esta onde está.
    if (!form || (form.getAttribute("target") || "").toLowerCase() === "_blank") return;
    var botao = ev.submitter || (clicado && clicado.form === form ? clicado : null);
    var dados = { caminho: location.pathname, em: Date.now(), tela: quemRola().scrollTop };
    if (botao) {
      var alvo = assinatura(botao);
      dados.alvo = alvo;
      dados.ordem = iguais(alvo).indexOf(botao);
      dados.altura = botao.getBoundingClientRect().top;
    }
    try { sessionStorage.setItem(GUARDA, JSON.stringify(dados)); } catch (erro) { /* abre no topo */ }
  });

  // O guardado se consome sempre: sem isto, reabriria rolada numa visita seguinte.
  var salvo = null;
  try {
    salvo = JSON.parse(sessionStorage.getItem(GUARDA) || "null");
    sessionStorage.removeItem(GUARDA);
  } catch (erro) { return; }
  if (!salvo || salvo.caminho !== location.pathname || location.hash) return;
  var idade = Date.now() - salvo.em;
  if (!(idade >= 0 && idade < PRAZO)) return;

  function devolver() {
    var rola = quemRola();
    var candidatos = salvo.alvo ? iguais(salvo.alvo) : [];
    var botao = candidatos[salvo.ordem] || (candidatos.length === 1 ? candidatos[0] : null);
    // "instant": `app.css` tem `scroll-behavior:smooth`, e a tela deslizaria a partir do topo.
    if (botao && botao.getClientRects().length) {
      var desvio = botao.getBoundingClientRect().top - salvo.altura;
      rola.scrollTo({ top: rola.scrollTop + desvio, behavior: "instant" });
      try { botao.focus({ preventScroll: true }); } catch (erro) { /* foco é cortesia */ }
    } else {
      rola.scrollTo({ top: salvo.tela, behavior: "instant" });
    }
  }
  // Os quadros recolhidos e as fases se arrumam no carregamento: espera-se o fim dele.
  if (document.readyState === "complete") devolver();
  else window.addEventListener("load", devolver, { once: true });
})();
