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
  var CABECALHO_DO_PARCIAL = "X-Wa-Parcial";

  /* A SESSÃO ACABOU (revisão do #72). Com o login vencido, o servidor redireciona
   * ao login, e o `fetch` segue o redirecionamento calado: a resposta vira a
   * página do login. Ela nunca vai parar dentro da lista. As perguntas param
   * e a página recarrega, e quem está diante dela cai no login de verdade. */
  var parado = false;
  var relogios = [];

  function pararERecarregar() {
    if (parado) {
      return;
    }
    parado = true;
    relogios.forEach(function (relogio) { window.clearInterval(relogio); });
    window.location.reload();
  }

  /* A resposta é a esperada? Redirecionada nunca é; a do `/novas` tem de ser
   * JSON, e a da lista tem de trazer o cabeçalho do parcial. */
  function respostaEsperada(r, tipo) {
    if (r.redirected) {
      return false;
    }
    if (tipo === "json") {
      return (r.headers.get("Content-Type") || "").indexOf("application/json") === 0;
    }
    return r.headers.get(CABECALHO_DO_PARCIAL) === "lista";
  }

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

  /* A ENTREGA AO VIVO (29/10/2026): o servidor manda o estado das últimas
   * enviadas, com a marca e o título prontos; aqui só se troca o atributo, o
   * título e o `textContent` do span que o balão já tem. */
  function atualizarEntregas(entregas) {
    (entregas || []).forEach(function (e) {
      var marca = document.querySelector('[data-wa-entrega-de="' + Number(e.id) + '"]');
      if (!marca) {
        return;
      }
      marca.setAttribute("data-wa-entrega", e.entrega || "");
      if (e.titulo) {
        marca.setAttribute("title", e.titulo);
      } else {
        marca.removeAttribute("title");
      }
      if (marca.textContent !== (e.marca || "")) {
        marca.textContent = e.marca || "";
      }
    });
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
    if (!caixa || parado || perguntandoConversa || !visivel()) {
      return;
    }
    perguntandoConversa = true;
    // A vista do histórico já leva `?historico=1` no endereço.
    var base = caixa.getAttribute("data-novas-url");
    var url = base + (base.indexOf("?") === -1 ? "?" : "&") + "depois=" +
      encodeURIComponent(caixa.getAttribute("data-ultimo") || "0");
    fetch(url, {credentials: "same-origin", headers: {"Accept": "application/json"}})
      .then(function (r) {
        if (r.redirected || (r.ok && !respostaEsperada(r, "json"))) {
          pararERecarregar();
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (dados) {
        if (!dados || parado) {
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
        atualizarEntregas(dados.entregas);
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
    if (!lista || parado || perguntandoLista || !visivel()) {
      return;
    }
    perguntandoLista = true;
    fetch(lista.getAttribute("data-url"), {credentials: "same-origin"})
      .then(function (r) {
        if (r.redirected || (r.ok && !respostaEsperada(r, "lista"))) {
          pararERecarregar();
          return null;
        }
        return r.ok ? r.text() : null;
      })
      .then(function (html) {
        if (html === null || parado) {
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
  // A JANELINHA FLUTUANTE (segunda revisão do #73): abre e fecha pela seta, e
  // fecha também pelo Esc e pelo clique fora dela.
  var botaoDetalhes = document.querySelector("[data-wa-detalhes]");
  var painel = document.querySelector("[data-wa-painel]");

  function mostrarDetalhes(abrir) {
    painel.hidden = !abrir;
    botaoDetalhes.setAttribute("aria-expanded", abrir ? "true" : "false");
  }

  if (botaoDetalhes && painel) {
    botaoDetalhes.addEventListener("click", function () {
      mostrarDetalhes(painel.hidden);
    });
    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && !painel.hidden) {
        mostrarDetalhes(false);
        botaoDetalhes.focus();
      }
    });
    document.addEventListener("click", function (evento) {
      if (!painel.hidden && !painel.contains(evento.target) &&
          !botaoDetalhes.contains(evento.target)) {
        mostrarDetalhes(false);
      }
    });
  }

  // O «OK» só liga quando algum campo difere do que estava (`data-inicial`);
  // a pessoa que volta o campo ao valor de antes o desliga de novo.
  var formDetalhes = document.querySelector("form[data-wa-detalhes-form]");
  var botaoOk = formDetalhes && formDetalhes.querySelector("[data-wa-detalhes-ok]");

  function valorDoCampo(campo) {
    if (campo.type === "checkbox") {
      return campo.checked ? "1" : "";
    }
    return campo.value || "";
  }

  function conferirOk() {
    var campos = formDetalhes.querySelectorAll("[data-inicial]");
    var mudou = false;
    for (var i = 0; i < campos.length; i++) {
      if (valorDoCampo(campos[i]) !== campos[i].getAttribute("data-inicial")) {
        mudou = true;
      }
    }
    botaoOk.disabled = !mudou;
  }

  if (formDetalhes && botaoOk) {
    formDetalhes.addEventListener("change", conferirOk);
    formDetalhes.addEventListener("input", conferirOk);
  }

  // ------------------------------------------------------------- respostas prontas
  // (29/10/2026) Escolher uma põe o texto na caixa — no fim do que já estiver
  // escrito —, com {nome} trocado pelo primeiro nome do cliente. Não envia.
  var respostas = document.querySelector("[data-wa-respostas]");
  if (respostas && texto) {
    respostas.addEventListener("change", function () {
      var opcao = respostas.options[respostas.selectedIndex];
      var modelo = opcao && opcao.getAttribute("data-texto");
      if (!modelo) {
        return;
      }
      var nome = respostas.getAttribute("data-nome") || "";
      var pronto = modelo.split("{nome}").join(nome).replace(/\s+([,.!?])/g, "$1");
      texto.value = texto.value.trim() ? texto.value.replace(/\s+$/, "") + "\n" + pronto
                                       : pronto;
      respostas.selectedIndex = 0;
      texto.focus();
    });
  }

  // O ARQUIVO SAI UMA VEZ SÓ (29/10/2026): o botão desliga no primeiro clique.
  var anexar = document.querySelector("form.wa-anexar-form");
  if (anexar) {
    anexar.addEventListener("submit", function () {
      var b = anexar.querySelector("button");
      if (b) {
        window.setTimeout(function () { b.disabled = true; b.textContent = "Mandando…"; }, 0);
      }
    });
  }

  // ------------------------------------------------------------- começo
  if (caixa) {
    rolarParaOFim();
    relogios.push(window.setInterval(perguntarConversa, CONVERSA_MS));
  }
  if (lista) {
    relogios.push(window.setInterval(perguntarLista, LISTA_MS));
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
