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
 *     sem querer não se desfaz), e o balão sobe na hora, numa fila por conversa;
 *   - a sugestão em cinza, que só o TAB torna texto;
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
    guardarACaixa();
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
  var perguntarDeNovo = false;

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
          pendurarNovas(dados.html);
          // Quem subiu para ler o histórico não é puxado de volta.
          if (estavaNoFim) {
            rolarParaOFim();
          }
        }
        if (dados.ultimo) {
          caixa.setAttribute("data-ultimo", String(dados.ultimo));
        }
        atualizarEstado(dados);
        conferirTokens(dados.entregas);
        atualizarEntregas(dados.entregas);
        trocarSugestao(dados.sugestao);
      })
      .catch(function () { /* a próxima pergunta tenta de novo */ })
      .then(function () {
        perguntandoConversa = false;
        if (perguntarDeNovo) {
          perguntarDeNovo = false;
          perguntarConversa();
        }
      });
  }

  /* Depois do envio, sem esperar o relógio; com uma pergunta no ar, logo depois dela. */
  function perguntarConversaAgora() {
    if (perguntandoConversa) {
      perguntarDeNovo = true;
    } else {
      perguntarConversa();
    }
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
  var formulario = document.querySelector("form[data-wa-fila]");
  var botaoEnviar = formulario && formulario.querySelector("[data-wa-enviar]");
  var texto = formulario && formulario.querySelector("[data-wa-caixa]");
  var moldeDoBalao = document.querySelector("template[data-wa-molde-balao]");

  /* O TEXTO NÃO SE PERDE COM A SESSÃO VENCIDA (30/10/2026). A chave leva o usuário e
   * a conversa: na volta do login, o texto volta à caixa de quem o escreveu, e o de
   * outro usuário é descartado sem aparecer. */
  var PREFIXO_DA_CAIXA = "wa-caixa-";
  var areaDoChat = document.querySelector("[data-wa-usuario]");
  var usuarioDaTela = areaDoChat ? areaDoChat.getAttribute("data-wa-usuario") : "";

  function chaveDaCaixa() {
    return PREFIXO_DA_CAIXA + usuarioDaTela + "-" + formulario.getAttribute("data-wa-conversa");
  }

  function guardarACaixa() {
    if (!formulario || !texto) {
      return;
    }
    var partes = filaDeEnvio.map(function (item) { return item.texto; });
    if (texto.value.trim()) {
      partes.push(texto.value);
    }
    if (!partes.length) {
      return;
    }
    texto.value = partes.join("\n");
    try {
      window.sessionStorage.setItem(chaveDaCaixa(), texto.value);
    } catch (e) { /* sem o armazenamento, o aviso de sair da página não muda */ }
  }

  function recuperarACaixa() {
    try {
      var guardadas = window.sessionStorage;
      for (var i = guardadas.length - 1; i >= 0; i--) {
        var chave = guardadas.key(i);
        if (chave.indexOf(PREFIXO_DA_CAIXA) === 0 &&
            chave.indexOf(PREFIXO_DA_CAIXA + usuarioDaTela + "-") !== 0) {
          guardadas.removeItem(chave);
        }
      }
      if (!formulario || !texto) {
        return;
      }
      var guardado = guardadas.getItem(chaveDaCaixa());
      if (guardado) {
        texto.value = texto.value ? texto.value + "\n" + guardado : guardado;
        guardadas.removeItem(chaveDaCaixa());
      }
    } catch (e) { /* sem o armazenamento, não há o que recuperar */ }
  }

  /* A FILA DA CONVERSA (30/10/2026): o balão aparece na hora, e o envio de verdade
   * vai uma mensagem de cada vez, na ordem em que foram escritas. Se uma falhar, as
   * seguintes esperam. Cada página tem uma conversa aberta, logo uma fila. O servidor
   * segue o mesmo caminho: nada é gravado antes de a Graph responder. */
  var RELOGIO = "🕓";
  var ESPERA_DO_EM_CURSO_MS = 2000;
  var filaDeEnvio = [];
  var postando = false;

  /* `crypto.randomUUID` só existe em https; o servidor da casa é `http://`. */
  function novoToken() {
    if (window.crypto && window.crypto.randomUUID) {
      return window.crypto.randomUUID();
    }
    var bytes = new Uint8Array(16);
    if (window.crypto && window.crypto.getRandomValues) {
      window.crypto.getRandomValues(bytes);
    } else {
      for (var i = 0; i < bytes.length; i++) {
        bytes[i] = Math.floor(Math.random() * 256);
      }
    }
    return Array.prototype.map.call(bytes, function (b) {
      return ("0" + b.toString(16)).slice(-2);
    }).join("");
  }

  function marcarBalao(item, entrega, marca, titulo) {
    var span = item.balao.querySelector("[data-wa-prov-marca]");
    span.setAttribute("data-wa-entrega", entrega);
    span.textContent = marca;
    span.setAttribute("title", titulo || "");
    item.balao.querySelector("[data-wa-prov-acoes]").hidden = item.estado !== "falhou";
  }

  function mostrarOsQueEsperam() {
    var travada = filaDeEnvio.length > 0 && filaDeEnvio[0].estado === "falhou";
    filaDeEnvio.forEach(function (item, posicao) {
      if (posicao > 0) {
        marcarBalao(item, "", travada ? RELOGIO + " esperando a anterior" : RELOGIO,
                    travada ? "sai depois que a anterior for resolvida" : "ainda indo");
      }
    });
  }

  function tirarDaFila(item) {
    var posicao = filaDeEnvio.indexOf(item);
    if (posicao !== -1) {
      filaDeEnvio.splice(posicao, 1);
    }
  }

  function falhar(item, motivo) {
    item.estado = "falhou";
    marcarBalao(item, "failed", "⚠ não saiu: " + motivo, motivo);
    mostrarOsQueEsperam();
  }

  /* O balão fica provisório até o `/novas` trazer o do servidor, mas já tem o id:
   * a marca de entrega passa a valer. `data-ultimo` NÃO anda aqui: uma mensagem do
   * cliente com id menor, ainda não mostrada, se perderia. */
  function confirmar(item, dados) {
    tirarDaFila(item);
    item.balao.setAttribute("data-id", String(dados.id));
    var span = item.balao.querySelector("[data-wa-prov-marca]");
    span.setAttribute("data-wa-entrega-de", String(dados.id));
    span.setAttribute("data-wa-entrega", dados.entrega || "");
    span.setAttribute("title", dados.titulo || "");
    span.textContent = dados.marca || "";
    item.balao.querySelector("[data-wa-prov-acoes]").hidden = true;
    mostrarOsQueEsperam();
    perguntarConversaAgora();
  }

  function postarOProximo() {
    var item = filaDeEnvio[0];
    if (postando || parado || !item || item.estado === "falhou") {
      return;
    }
    postando = true;
    item.estado = "indo";
    marcarBalao(item, "", RELOGIO, "ainda indo");
    mostrarOsQueEsperam();
    var campos = new URLSearchParams();
    campos.set("csrf_token", formulario.querySelector('[name="csrf_token"]').value);
    campos.set("rascunho", item.texto);
    campos.set("envio_token", item.token);
    var esperar = 0;
    // `keepalive`: o que já saiu da fila termina, mesmo que a pessoa troque de tela.
    fetch(formulario.getAttribute("action"), {
      method: "POST",
      credentials: "same-origin",
      keepalive: true,
      headers: {"Accept": "application/json",
                "Content-Type": "application/x-www-form-urlencoded"},
      body: campos.toString()
    }).then(function (r) {
      if (r.redirected || (r.ok && !respostaEsperada(r, "json"))) {
        // A SESSÃO VENCIDA: o balão vira ⚠, e o texto volta à caixa e vai guardado.
        falhar(item, "a sessão venceu");
        pararERecarregar();
        return null;
      }
      if (!respostaEsperada(r, "json")) {
        falhar(item, "o servidor recusou o envio (HTTP " + r.status + ")");
        return null;
      }
      return r.json();
    }).then(function (dados) {
      if (!dados || parado) {
        return;
      }
      if (dados.ok) {
        confirmar(item, dados);
      } else if (dados.em_curso) {
        esperar = ESPERA_DO_EM_CURSO_MS;
        item.estado = "espera";
      } else {
        falhar(item, dados.motivo || "falhou");
      }
    }).catch(function () {
      // A resposta se perdeu: a mensagem pode ter saído, e o token protege a nova tentativa.
      falhar(item, "sem resposta do servidor");
    }).then(function () {
      postando = false;
      window.setTimeout(postarOProximo, esperar);
    });
  }

  function acrescentarBalao(item) {
    var no = moldeDoBalao.content.firstElementChild.cloneNode(true);
    no.setAttribute("data-wa-token", item.token);
    no.querySelector("[data-wa-prov-texto]").textContent = item.texto;
    var agora = new Date();
    no.querySelector("[data-wa-prov-hora]").textContent =
      ("0" + agora.getHours()).slice(-2) + ":" + ("0" + agora.getMinutes()).slice(-2);
    no.querySelector("[data-wa-tentar]").addEventListener("click", function () {
      item.estado = "espera";
      postarOProximo();
    });
    no.querySelector("[data-wa-descartar]").addEventListener("click", function () {
      tirarDaFila(item);
      no.remove();
      if (texto.value === "") {
        texto.value = item.texto;
        mostrarSugestao();
      }
      mostrarOsQueEsperam();
      postarOProximo();
    });
    item.balao = no;
    var vazio = caixa.querySelector(".wa-sem-mensagem");
    if (vazio) {
      vazio.remove();
    }
    caixa.appendChild(no);
    rolarParaOFim();
  }

  /* A caixa vazia não envia, e a sugestão nunca sai sem o TAB. */
  function enfileirar() {
    var escrito = texto.value.trim();
    if (!escrito || botaoEnviar.disabled) {
      texto.focus();
      return;
    }
    var item = {token: novoToken(), texto: escrito, estado: "espera", balao: null};
    texto.value = "";
    mostrarSugestao();
    filaDeEnvio.push(item);
    acrescentarBalao(item);
    marcarBalao(item, "", RELOGIO, "ainda indo");
    texto.focus();
    postarOProximo();
  }

  /* O BALÃO DO SERVIDOR TOMA O LUGAR DO PROVISÓRIO, seja qual for a resposta que
   * chegar primeiro: a mesma mensagem nunca fica em dois balões. O resto entra antes
   * dos provisórios, que ainda não têm lugar definitivo na conversa. */
  function provisorioDoToken(token) {
    var todos = caixa.querySelectorAll("[data-wa-provisorio]");
    for (var i = 0; i < todos.length; i++) {
      if (token && todos[i].getAttribute("data-wa-token") === token) {
        return todos[i];
      }
    }
    return null;
  }

  function itemDoToken(token) {
    return filaDeEnvio.filter(function (item) { return item.token === token; })[0];
  }

  function pendurarNovas(html) {
    var nos = nosDoServidor(html);
    Array.prototype.forEach.call(nos.querySelectorAll(".wa-balao"), function (balao) {
      var token = balao.getAttribute("data-wa-token");
      var provisorio = provisorioDoToken(token);
      if (!provisorio) {
        return;
      }
      var item = itemDoToken(token);
      if (item) {
        tirarDaFila(item);
      }
      var antes = balao.previousElementSibling;
      if (antes && antes.classList.contains("wa-dia")) {
        provisorio.parentNode.insertBefore(antes, provisorio);
      }
      provisorio.parentNode.replaceChild(balao, provisorio);
    });
    caixa.insertBefore(nos, caixa.querySelector("[data-wa-provisorio]"));
    mostrarOsQueEsperam();
    postarOProximo();
  }

  /* Se a resposta do POST se perdeu e a mensagem já está gravada, a entrega traz o
   * token, e o balão com ⚠ não fica pedindo uma nova tentativa. */
  function conferirTokens(entregas) {
    (entregas || []).forEach(function (e) {
      var item = e.token ? itemDoToken(e.token) : null;
      if (item && item.estado !== "indo") {
        confirmar(item, e);
        postarOProximo();
      }
    });
  }

  if (formulario && botaoEnviar && texto && moldeDoBalao && caixa) {
    formulario.addEventListener("submit", function (evento) {
      // O «guardar rascunho» (formaction) não envia nada à Meta: segue livre.
      var quem = evento.submitter;
      if (quem && quem !== botaoEnviar) {
        return;
      }
      evento.preventDefault();
      enfileirar();
    });
    texto.addEventListener("keydown", function (evento) {
      if (evento.key === "Enter" && (evento.ctrlKey || evento.metaKey)) {
        evento.preventDefault();
        enfileirar();
      }
    });
    window.addEventListener("beforeunload", function (evento) {
      if (filaDeEnvio.length && !parado) {
        evento.preventDefault();
        evento.returnValue = "";
      }
    });
  }

  // ------------------------------------------------------------- a sugestão
  // A SUGESTÃO NÃO É TEXTO ESCRITO (30/10/2026): fica no `placeholder`, que o
  // navegador já mostra só com a caixa vazia. O TAB a torna texto; qualquer outro
  // TAB muda de campo, porque o teclado não pode ficar preso na caixa.
  var avisoDaSugestao = document.querySelector("[data-wa-sugestao-aviso]");

  function sugestaoDaCaixa() {
    return texto.getAttribute("data-wa-sugestao") || "";
  }

  function mostrarSugestao() {
    texto.placeholder = sugestaoDaCaixa() || texto.getAttribute("data-wa-placeholder") || "";
    if (avisoDaSugestao) {
      avisoDaSugestao.hidden = !sugestaoDaCaixa() || texto.value !== "";
    }
  }

  /* Ao vivo: só o atributo e a propriedade. O que a pessoa digita fica como está. */
  function trocarSugestao(sugestao) {
    if (!texto || typeof sugestao !== "string" || sugestao === sugestaoDaCaixa()) {
      return;
    }
    texto.setAttribute("data-wa-sugestao", sugestao);
    mostrarSugestao();
  }

  if (texto) {
    texto.addEventListener("input", mostrarSugestao);
    texto.addEventListener("keydown", function (evento) {
      if (evento.key !== "Tab" || evento.shiftKey || evento.ctrlKey || evento.altKey ||
          evento.metaKey || texto.value !== "" || !sugestaoDaCaixa()) {
        return;
      }
      evento.preventDefault();
      texto.value = sugestaoDaCaixa();
      texto.selectionStart = texto.selectionEnd = texto.value.length;
      mostrarSugestao();
    });
    mostrarSugestao();
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
      mostrarSugestao();
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
  recuperarACaixa();
  if (texto) {
    mostrarSugestao();
  }
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
