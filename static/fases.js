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

  // A fase guardada se consome sempre: sem isto, ela reabriria sozinha numa visita seguinte.
  var salva = guardada();
  var pedido = doEndereco();
  if (pedido) abrir(pedido.fase, pedido.alvo);
  else abrir(salva || regua.getAttribute("data-inicial"));
  if (ficha) ficha.classList.remove("cg-esperando");
})();

/* Os passos de um formulário longo. É UM FORMULÁRIO SÓ: o que está escondido vai junto no envio.
 *
 * O CAMPO OBRIGATÓRIO NUM PASSO ESCONDIDO É A ARMADILHA. O navegador recusa o envio, não tem
 * onde pôr o foco, e o botão parece não fazer nada. Por isso o aviso de campo inválido abre o
 * passo dele. Numa recarga de verdade (escolher a prenotação, ou uma recusa do servidor), a
 * ficha volta ao passo em que estava; numa abertura nova, começa do começo. */
(function () {
  "use strict";

  var nav = document.querySelector("[data-cg-passos]");
  if (!nav) return;
  var form = document.getElementById(nav.getAttribute("data-cg-passos"));
  if (!form) return;
  var botoes = Array.prototype.slice.call(nav.querySelectorAll("[data-passo-ir]"));
  var chaves = botoes.map(function (b) { return b.getAttribute("data-passo-ir"); });
  var blocos = Array.prototype.slice.call(form.querySelectorAll("[data-passo]"));
  var fim = form.querySelector("[data-cg-passos-fim]");
  var voltar = form.querySelector("[data-passo-voltar]");
  var avancar = form.querySelector("[data-passo-avancar]");
  var guarda = "cg-passo:" + form.id + ":" + form.getAttribute("action");
  var PRAZO = 2 * 60 * 1000;
  var aberto = "";

  function rotulo(chave) {
    var b = botoes[chaves.indexOf(chave)];
    return b ? b.textContent.replace(/^\s*\d+/, "").trim() : "";
  }

  function abrir(chave) {
    if (chaves.indexOf(chave) < 0) return;
    aberto = chave;
    blocos.forEach(function (b) { b.hidden = b.getAttribute("data-passo") !== chave; });
    botoes.forEach(function (b) {
      if (b.getAttribute("data-passo-ir") === chave) b.setAttribute("aria-current", "step");
      else b.removeAttribute("aria-current");
    });
    var i = chaves.indexOf(chave);
    if (fim) fim.hidden = false;
    if (voltar) {
      voltar.hidden = i === 0;
      voltar.textContent = i > 0 ? "\u2190 " + rotulo(chaves[i - 1]) : "";
    }
    if (avancar) {
      avancar.hidden = i === chaves.length - 1;
      avancar.textContent = i < chaves.length - 1 ? "Avançar: " + rotulo(chaves[i + 1]) : "";
    }
    try { sessionStorage.setItem(guarda, chave + "|" + Date.now()); } catch (erro) { /* só não volta ao passo */ }
  }

  function guardado() {
    try {
      var partes = (sessionStorage.getItem(guarda) || "").split("|");
      return Date.now() - Number(partes[1]) < PRAZO ? partes[0] : "";
    } catch (erro) {
      return "";
    }
  }

  nav.addEventListener("click", function (ev) {
    var b = ev.target.closest("[data-passo-ir]");
    if (b) abrir(b.getAttribute("data-passo-ir"));
  });
  if (voltar) voltar.addEventListener("click", function () { abrir(chaves[chaves.indexOf(aberto) - 1]); });
  if (avancar) avancar.addEventListener("click", function () { abrir(chaves[chaves.indexOf(aberto) + 1]); });

  // O navegador avisa de todos os campos inválidos de uma vez, e o cursor vai para o primeiro.
  // Só o primeiro conta: sem isto, abriria o passo do último, longe de onde o cursor ficou.
  var avisado = false;
  form.addEventListener("invalid", function (ev) {
    if (avisado) return;
    avisado = true;
    setTimeout(function () { avisado = false; }, 0);
    var bloco = ev.target.closest("[data-passo]");
    if (!bloco || !bloco.hidden) return;
    abrir(bloco.getAttribute("data-passo"));
    setTimeout(function () { ev.target.reportValidity(); }, 0);
  }, true);

  var recarga = /[?&](prenotacao_id|protocolo_id)=/.test(location.search)
    || document.querySelector(".flash.danger, .flash.warning");
  abrir((recarga && guardado()) || nav.getAttribute("data-inicial"));
})();
