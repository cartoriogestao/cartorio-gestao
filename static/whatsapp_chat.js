/* A TELA DE CONVERSA DO WHATSAPP (27/10/2026) — `whatsapp_chat.html`.
 *
 * O QUE ELA FAZ AQUI, E SÓ ISTO:
 *   - abre rolada na última mensagem;
 *   - pergunta ao servidor, a cada 5 s, pelas mensagens novas da conversa
 *     aberta e, a cada 15 s, pela lista — só com a aba visível. O servidor só
 *     lê o banco: a mensagem chega a ele pela caixa-postal (o botão ou a
 *     automação), e não por esta tela;
 *   - a busca da lista, no navegador;
 *   - Ctrl+Enter envia (Enter só pula linha: num cartório, mensagem enviada
 *     sem querer não se desfaz), e o envio em dobro é barrado;
 *   - o painel de detalhes.
 *
 * O TEXTO DO CLIENTE NUNCA VIRA HTML AQUI. Um cliente pode mandar `<script>`
 * pelo WhatsApp. Os balões e a lista chegam já desenhados pelo parcial do
 * Jinja, com o escape automático, e este arquivo só os pendura; o que ele
 * escreve por conta própria vai por `textContent`.
 */
(function () {
  "use strict";

  var CONVERSA_MS = 5000;
  var LISTA_MS = 15000;
  var FOLGA_DO_FIM = 40;

  function visivel() {
    return document.visibilityState === "visible";
  }

  /* Os nós de um HTML que O SERVIDOR já escapou (o parcial do Jinja). */
  function nosDoServidor(html) {
    var molde = document.createElement("template");
    molde.innerHTML = html;
    return molde.content;
  }

  // ------------------------------------------------------------ a conversa
  var caixa = document.querySelector("[data-wa-mensagens]");

  function noFim() {
    return caixa.scrollHeight - caixa.scrollTop - caixa.clientHeight < FOLGA_DO_FIM;
  }

  function rolarParaOFim() {
    caixa.scrollTop = caixa.scrollHeight;
  }

  function atualizarEstado(dados) {
    var status = document.querySelector("[data-wa-status]");
    if (status && dados.status && status.textContent !== dados.status) {
      status.textContent = dados.status;
    }
    var modo = document.querySelector("[data-wa-modo]");
    if (modo && dados.modo && modo.getAttribute("data-modo") !== dados.modo) {
      modo.setAttribute("data-modo", dados.modo);
      modo.textContent = dados.modo === "pessoa"
        ? modo.getAttribute("data-texto-pessoa")
        : modo.getAttribute("data-texto-ia");
    }
    // O aviso da janela de 24 h só vem na página quando ela já estava fora; se
    // o cliente responder com a tela aberta, a janela reabre e ele some.
    var janela = document.querySelector("[data-wa-janela]");
    if (janela && dados.janela_fora === false) {
      janela.hidden = true;
    }
  }

  var perguntandoConversa = false;

  function perguntarConversa() {
    if (!caixa || perguntandoConversa || !visivel()) {
      return;
    }
    perguntandoConversa = true;
    var url = caixa.getAttribute("data-novas-url") + "?depois=" +
      encodeURIComponent(caixa.getAttribute("data-ultimo") || "0");
    fetch(url, {credentials: "same-origin", headers: {"Accept": "application/json"}})
      .then(function (r) { return r.ok ? r.json() : null; })
      .then(function (dados) {
        if (!dados) {
          return;
        }
        if (dados.html) {
          var estavaNoFim = noFim();
          var vazio = caixa.querySelector(".wa-sem-mensagem");
          if (vazio) {
            vazio.remove();
          }
          caixa.appendChild(nosDoServidor(dados.html));
          // Quem subiu para ler o histórico não é puxado de volta.
          if (estavaNoFim) {
            rolarParaOFim();
          }
        }
        if (dados.ultimo) {
          caixa.setAttribute("data-ultimo", String(dados.ultimo));
        }
        atualizarEstado(dados);
      })
      .catch(function () { /* a próxima pergunta tenta de novo */ })
      .then(function () { perguntandoConversa = false; });
  }

  // -------------------------------------------------------------- a lista
  var lista = document.querySelector("[data-wa-lista]");
  var busca = document.querySelector("[data-wa-busca]");

  function semAcento(texto) {
    return (texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  function aplicarBusca() {
    if (!lista || !busca) {
      return;
    }
    var procura = semAcento(busca.value.trim());
    var itens = lista.querySelectorAll(".wa-item");
    for (var i = 0; i < itens.length; i++) {
      var alvo = semAcento(itens[i].getAttribute("data-busca"));
      itens[i].hidden = procura !== "" && alvo.indexOf(procura) === -1;
    }
  }

  var perguntandoLista = false;

  function perguntarLista() {
    if (!lista || perguntandoLista || !visivel()) {
      return;
    }
    perguntandoLista = true;
    fetch(lista.getAttribute("data-url"), {credentials: "same-origin"})
      .then(function (r) { return r.ok ? r.text() : null; })
      .then(function (html) {
        if (html === null) {
          return;
        }
        var rolagem = lista.scrollTop;
        lista.replaceChildren(nosDoServidor(html));
        lista.scrollTop = rolagem;
        aplicarBusca();
      })
      .catch(function () { /* a próxima pergunta tenta de novo */ })
      .then(function () { perguntandoLista = false; });
  }

  // ----------------------------------------------- a caixa de escrever
  var formulario = document.querySelector("form[data-wa-envio-unico]");
  var botaoEnviar = formulario && formulario.querySelector("[data-wa-enviar]");
  var texto = formulario && formulario.querySelector("[data-wa-caixa]");

  function enviando() {
    return formulario.getAttribute("data-wa-enviando") === "1";
  }

  if (formulario && botaoEnviar) {
    formulario.addEventListener("submit", function (evento) {
      // O «guardar rascunho» (formaction) não envia nada à Meta: segue livre.
      var quem = evento.submitter;
      if (quem && quem !== botaoEnviar) {
        return;
      }
      // CONTRA O ENVIO EM DOBRO: o primeiro envio desliga o botão até a página
      // recarregar; um segundo clique ou Ctrl+Enter não sai.
      if (enviando() || botaoEnviar.disabled) {
        evento.preventDefault();
        return;
      }
      formulario.setAttribute("data-wa-enviando", "1");
      botaoEnviar.textContent = "enviando…";
      window.setTimeout(function () { botaoEnviar.disabled = true; }, 0);
    });
  }

  if (texto && formulario && botaoEnviar) {
    texto.addEventListener("keydown", function (evento) {
      if (evento.key !== "Enter" || !(evento.ctrlKey || evento.metaKey)) {
        return;
      }
      evento.preventDefault();
      if (enviando() || botaoEnviar.disabled) {
        return;
      }
      if (formulario.requestSubmit) {
        formulario.requestSubmit(botaoEnviar);
      } else {
        botaoEnviar.click();
      }
    });
  }

  // ---------------------------------------------------- os detalhes
  var botaoDetalhes = document.querySelector("[data-wa-detalhes]");
  var painel = document.querySelector("[data-wa-painel]");
  if (botaoDetalhes && painel) {
    botaoDetalhes.addEventListener("click", function () {
      var abrir = painel.hidden;
      painel.hidden = !abrir;
      botaoDetalhes.setAttribute("aria-expanded", abrir ? "true" : "false");
      botaoDetalhes.textContent = abrir ? "detalhes ◂" : "detalhes ▸";
    });
  }

  // ------------------------------------------------------------- começo
  if (caixa) {
    rolarParaOFim();
    window.setInterval(perguntarConversa, CONVERSA_MS);
  }
  if (lista) {
    window.setInterval(perguntarLista, LISTA_MS);
  }
  if (busca) {
    busca.addEventListener("input", aplicarBusca);
  }
  document.addEventListener("visibilitychange", function () {
    if (visivel()) {
      perguntarConversa();
      perguntarLista();
    }
  });
})();
