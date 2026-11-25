/*
  O SINAL DO SELO NA TELA DO ATO (P008, 24/11/2026) — ver `selo_sinal.py`.

  Só age onde existe `[data-selo-sinal]` (macro `_sinal_do_selo.html`), dentro
  do formulário do ato. Manda o formulário, como está, para `/selo/sinal`, que
  SÓ LÊ, e põe o resultado no lugar. Refaz a conta quando um campo muda e
  quando a pessoa volta de outra aba (o caixa abre em outra aba).

  NÃO BLOQUEIA. Com o sinal vermelho, o botão de lavrar mostra o que falta e
  duas saídas: resolver primeiro, ou lavrar assim mesmo. Quem decide é quem
  lavra; o servidor faz o que sempre fez (o selo sai depois do ato, ou o ato
  fica aguardando cobertura). Não grava nada no navegador.
*/
(function () {
  "use strict";

  var ESPERA_CAMPO = 300;
  var ESPERA_DIGITACAO = 700;

  function csrfDaPagina() {
    var campo = document.querySelector('input[name="csrf_token"]');
    return campo ? campo.value : "";
  }

  function corAtual(el) {
    var corpo = el.querySelector("[data-cor]");
    return corpo ? corpo.getAttribute("data-cor") : "";
  }

  function atualizar(el) {
    var form = el.closest("form");
    if (!form) return;
    var dados = new FormData(form);
    dados.set("_sinal_tabela", el.getAttribute("data-tabela") || "");
    dados.delete("_sinal_pedido");
    (el.getAttribute("data-pedidos") || "").split(/\s+/).forEach(function (p) {
      if (p) dados.append("_sinal_pedido", p);
    });
    if (!dados.get("csrf_token")) dados.set("csrf_token", csrfDaPagina());
    var vez = (el._seloVez || 0) + 1;
    el._seloVez = vez;
    fetch(el.getAttribute("data-url"), {
      method: "POST", body: dados, credentials: "same-origin",
      headers: {"X-CSRF-Token": dados.get("csrf_token") || ""}
    }).then(function (r) {
      return r.ok ? r.text() : null;
    }).then(function (html) {
      if (vez !== el._seloVez) return;          // chegou uma resposta mais nova
      if (html === null) { el.hidden = true; return; }
      el.innerHTML = html;
      el.hidden = false;
    }).catch(function () {
      if (vez === el._seloVez) el.hidden = true;
    });
  }

  function adiar(el, ms) {
    clearTimeout(el._seloTimer);
    el._seloTimer = setTimeout(function () { atualizar(el); }, ms);
  }

  // O botão que LAVRA: o marcado com `data-selo-lavra`; sem marca na tela, o
  // botão principal («primary») ou o único botão do formulário. Guardar
  // rascunho e os botões de outra ação passam sem aviso.
  function lavra(form, botao) {
    if (!botao) return false;
    if (/rascunho/i.test((botao.name || "") + " " + (botao.value || "")
                        + " " + (botao.getAttribute("formaction") || ""))) {
      return false;
    }
    var marcados = form.querySelectorAll("[data-selo-lavra]");
    if (marcados.length) return botao.hasAttribute("data-selo-lavra");
    if (botao.classList.contains("primary")) return true;
    return form.querySelectorAll('button:not([type="button"]), input[type="submit"]').length === 1;
  }

  function avisar(el, form, botao) {
    var velho = el.querySelector(".selo-sinal-aviso");
    if (velho) velho.remove();
    var rotulo = el.getAttribute("data-rotulo") || "Lavrar";
    var aviso = document.createElement("div");
    aviso.className = "selo-sinal-aviso";
    aviso.setAttribute("role", "alert");
    var p = document.createElement("p");
    p.textContent = "O selo não vai sair assim. Se continuar agora, "
      + (el.getAttribute("data-se-nao-sair") || "a tela mostra o que falta") + ".";
    aviso.appendChild(p);
    var escolha = document.createElement("div");
    escolha.className = "selo-sinal-escolha";
    var resolver = document.createElement("button");
    resolver.type = "button";
    resolver.className = "primary";
    resolver.textContent = "Resolver primeiro";
    resolver.addEventListener("click", function () {
      aviso.remove();
      var primeiro = el.querySelector(".selo-sinal-botoes a");
      (primeiro || el).focus && (primeiro || el).focus();
    });
    var assim = document.createElement("button");
    assim.type = "button";
    assim.textContent = rotulo + " assim mesmo";
    assim.addEventListener("click", function () {
      aviso.remove();
      form.setAttribute("data-selo-assim-mesmo", "1");
      if (form.requestSubmit) form.requestSubmit(botao);
      else botao.click();
    });
    escolha.appendChild(resolver);
    escolha.appendChild(assim);
    aviso.appendChild(escolha);
    el.appendChild(aviso);
    el.scrollIntoView({block: "center", behavior: "smooth"});
    resolver.focus();
  }

  function ligar(el) {
    var form = el.closest("form");
    if (!form || el._seloLigado) return;
    el._seloLigado = true;
    form.addEventListener("change", function () { adiar(el, ESPERA_CAMPO); });
    form.addEventListener("input", function (ev) {
      var alvo = ev.target;
      // Só os campos que mudam o selo (código, folhas, quantidade): o teor do
      // ato e os nomes não refazem a conta a cada letra.
      if (alvo && alvo.tagName === "INPUT"
          && (alvo.type === "number" || /codigo|folhas|qtd/.test(alvo.name || ""))) {
        adiar(el, ESPERA_DIGITACAO);
      }
    });
    form.addEventListener("submit", function (ev) {
      if (form.getAttribute("data-selo-assim-mesmo") === "1") {
        form.removeAttribute("data-selo-assim-mesmo");
        return;
      }
      if (corAtual(el) !== "vermelho" || !lavra(form, ev.submitter)) return;
      ev.preventDefault();
      ev.stopImmediatePropagation();
      avisar(el, form, ev.submitter);
    }, true);
    atualizar(el);
  }

  function todos() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-selo-sinal]"));
  }

  function iniciar() {
    todos().forEach(ligar);
    // A pessoa foi ao caixa (outra aba) e voltou: o sinal se refaz.
    document.addEventListener("visibilitychange", function () {
      if (document.visibilityState === "visible") todos().forEach(atualizar);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", iniciar);
  } else {
    iniciar();
  }
})();
