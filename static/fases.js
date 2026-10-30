/* A ficha em fases: mostra os quadros da fase aberta, e só eles.
 *
 * É SÓ APRESENTAÇÃO. Nenhum quadro nasce nem some daqui, as rotas e os formulários são os
 * mesmos, e sem este script a página sai inteira, como sempre saiu.
 *
 * O ENDEREÇO DIZ A FASE (#teor), e por isso voltar, recarregar e colar o link funcionam.
 * Depois de gravar, a ficha volta à fase em que estava: o formulário que tem endereço
 * próprio perde o #, e a fase fica guardada por dois minutos nesta aba do navegador. */
(function () {
  "use strict";

  var regua = document.querySelector("[data-cg-regua]");
  if (!regua) return;
  var ficha = document.querySelector(".cg-ficha");
  var abas = Array.prototype.slice.call(regua.querySelectorAll("[data-cg-fase]"));
  var quadros = Array.prototype.slice.call(document.querySelectorAll("[data-fase]"));
  var app = document.querySelector(".cg-app");
  var rolagem = document.getElementById("conteudo");
  var guarda = "cg-fase:" + regua.getAttribute("data-chave");
  var PRAZO = 2 * 60 * 1000;
  var aberta = "";

  function aba(chave) {
    return abas.filter(function (a) { return a.getAttribute("data-cg-fase") === chave; })[0] || null;
  }

  function abrir(chave, alvo) {
    var escolhida = aba(chave);
    if (!escolhida) return;
    aberta = chave;
    var travada = escolhida.hasAttribute("data-travada");
    quadros.forEach(function (q) {
      var dela = q.getAttribute("data-fase") === chave;
      if (q.hasAttribute("data-cg-so-trava")) q.hidden = !(dela && travada);
      else if (q.hasAttribute("data-cg-barra")) q.hidden = !dela;
      else q.hidden = !dela || travada;
    });
    abas.forEach(function (a) {
      if (a === escolhida) a.setAttribute("aria-current", "step");
      else a.removeAttribute("aria-current");
    });
    if (app) app.classList.toggle("cg-foco", chave === regua.getAttribute("data-foco"));
    if (alvo) alvo.scrollIntoView({ block: "start" });
    else if (rolagem) rolagem.scrollTop = 0;
  }

  function doEndereco() {
    var pedido = "";
    try { pedido = decodeURIComponent(location.hash.slice(1)); } catch (erro) { return null; }
    if (!pedido) return null;
    if (aba(pedido)) return { fase: pedido };
    var alvo = document.getElementById(pedido);
    var quadro = alvo && alvo.closest("[data-fase]");
    return quadro ? { fase: quadro.getAttribute("data-fase"), alvo: alvo } : null;
  }

  function guardada() {
    try {
      var valor = sessionStorage.getItem(guarda);
      sessionStorage.removeItem(guarda);
      if (!valor) return "";
      var partes = valor.split("|");
      return Date.now() - Number(partes[1]) < PRAZO && aba(partes[0]) ? partes[0] : "";
    } catch (erro) {
      return "";
    }
  }

  document.addEventListener("submit", function (ev) {
    if (!ev.target.closest("[data-fase]")) return;
    try { sessionStorage.setItem(guarda, aberta + "|" + Date.now()); } catch (erro) { /* sem isto, abre na fase pendente */ }
  }, true);

  window.addEventListener("hashchange", function () {
    var pedido = doEndereco();
    if (pedido) abrir(pedido.fase, pedido.alvo);
  });

  var pedido = doEndereco();
  if (pedido) abrir(pedido.fase, pedido.alvo);
  else abrir(guardada() || regua.getAttribute("data-inicial"));
  if (ficha) ficha.classList.remove("cg-esperando");
})();
