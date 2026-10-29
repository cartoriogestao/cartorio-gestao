/* O ATALHO DO WHATSAPP COM O ALERTA (27/10/2026) E O AVISO DE MENSAGEM NOVA
 * (29/10/2026) — `_whatsapp_atalho.html`.
 *
 * «preciso que atualize em tempo real (se nao possivel com frequencia de 30s
 *  (se abrir uma janela ou aviso no windows)» — o oficial, 29/10/2026.
 *
 * Pergunta ao servidor quantas conversas esperam resposta e qual é a última
 * mensagem de cliente: de 15 em 15 s com a aba visível e de 30 em 30 s com ela
 * escondida (o relógio da aba escondida é um Worker, `whatsapp_relogio.js`,
 * porque o navegador freia o da página). A rota manda tudo pronto, e aqui só
 * se copia, por `textContent` e `setAttribute`: a regra mora no servidor
 * (`wa_fila.nao_respondidas` e `wa_fila.ultima_entrada`).
 *
 * MENSAGEM NOVA → TRÊS AVISOS
 *   1. o aviso do Windows (Notification), se a pessoa liberou — o botão
 *      «Ligar os avisos do Windows» da tela do WhatsApp pede a licença;
 *   2. um som curto (gerado aqui, sem arquivo);
 *   3. o título da aba piscando e um cartão no canto da tela, com o nome e o
 *      começo da mensagem, que leva à conversa.
 * Cada aba guarda no navegador o id da última mensagem avisada: duas abas
 * abertas não avisam a mesma mensagem duas vezes, e a primeira pergunta depois
 * de abrir a tela só anota, sem avisar o que já estava lá.
 *
 * A pergunta não renova a sessão. Vencida a sessão, a resposta vem
 * redirecionada ao login: aí este arquivo PARA de perguntar, e só isso — quem
 * leva ao login é a própria tela, quando a pessoa clicar.
 */
(function () {
  "use strict";

  var VISIVEL_MS = 15000;
  var ESCONDIDA_MS = 30000;
  var CHAVE = "cg.whatsapp.ultimo_avisado";
  var avisos = document.querySelector("[data-wa-avisos]");
  var atalho = document.querySelector("[data-wa-atalho]");
  if (!avisos && !atalho) {
    return;
  }
  var url = (avisos || atalho).getAttribute("data-url");
  // O ENDEREÇO DA CONVERSA É MONTADO AQUI, de um caminho fixo e do NÚMERO que
  // a rota mandou — e não lido da página (revisão do CodeQL no #94).
  var CAMINHO_DA_CONVERSA = "/whatsapp/";
  var parado = false;
  var perguntando = false;
  var relogio = null;
  var worker = null;
  var tituloOriginal = document.title;
  var piscando = null;

  function lerUltimo() {
    try {
      return Number(window.localStorage.getItem(CHAVE) || "0");
    } catch (e) {
      return 0;
    }
  }

  function gravarUltimo(id) {
    try {
      window.localStorage.setItem(CHAVE, String(id));
    } catch (e) { /* sem armazenamento, avisa de novo: melhor que calar */ }
  }

  function parar() {
    parado = true;
    if (relogio) {
      window.clearInterval(relogio);
    }
    if (worker) {
      worker.terminate();
    }
  }

  function mostrar(dados) {
    if (!atalho) {
      return;
    }
    atalho.setAttribute("aria-label", dados.rotulo);
    atalho.setAttribute("title", dados.rotulo);
    var alerta = atalho.querySelector("[data-wa-atalho-n]");
    if (dados.n > 0) {
      if (!alerta) {
        alerta = document.createElement("span");
        alerta.className = "wa-atalho-alerta";
        alerta.setAttribute("data-wa-atalho-n", "");
        atalho.appendChild(alerta);
      }
      alerta.textContent = dados.texto;
    } else if (alerta) {
      alerta.remove();
    }
  }

  function tocar() {
    try {
      var Contexto = window.AudioContext || window.webkitAudioContext;
      if (!Contexto) {
        return;
      }
      var ctx = new Contexto();
      [0, 0.18].forEach(function (atraso) {
        var osc = ctx.createOscillator();
        var vol = ctx.createGain();
        osc.frequency.value = 880;
        vol.gain.value = 0.08;
        osc.connect(vol);
        vol.connect(ctx.destination);
        osc.start(ctx.currentTime + atraso);
        osc.stop(ctx.currentTime + atraso + 0.12);
      });
      window.setTimeout(function () { ctx.close(); }, 800);
    } catch (e) { /* sem som, os outros avisos continuam */ }
  }

  function piscar(texto) {
    if (piscando) {
      return;
    }
    var ligado = false;
    piscando = window.setInterval(function () {
      ligado = !ligado;
      document.title = ligado ? texto : tituloOriginal;
    }, 1000);
  }

  function pararDePiscar() {
    if (piscando) {
      window.clearInterval(piscando);
      piscando = null;
      document.title = tituloOriginal;
    }
  }

  function cartao(ultima, endereco) {
    var antigo = document.querySelector("[data-wa-cartao]");
    if (antigo) {
      antigo.remove();
    }
    var a = document.createElement("a");
    a.className = "wa-cartao-aviso";
    a.setAttribute("data-wa-cartao", "");
    a.setAttribute("role", "status");
    a.href = endereco;
    var titulo = document.createElement("strong");
    titulo.textContent = "WhatsApp · " + ultima.nome;
    var corpo = document.createElement("span");
    corpo.textContent = ultima.trecho;
    var fechar = document.createElement("button");
    fechar.type = "button";
    fechar.className = "wa-cartao-fechar";
    fechar.setAttribute("aria-label", "fechar o aviso");
    fechar.textContent = "×";
    fechar.addEventListener("click", function (ev) {
      ev.preventDefault();
      a.remove();
    });
    a.appendChild(titulo);
    a.appendChild(corpo);
    a.appendChild(fechar);
    document.body.appendChild(a);
    window.setTimeout(function () { a.remove(); }, 60000);
  }

  function avisar(ultima) {
    var numero = Math.floor(Number(ultima.conversa_id));
    if (!(numero > 0)) {
      return;
    }
    var endereco = CAMINHO_DA_CONVERSA + String(numero);
    tocar();
    if (document.visibilityState !== "visible") {
      piscar("(nova) WhatsApp · " + ultima.nome);
    }
    cartao(ultima, endereco);
    if ("Notification" in window && Notification.permission === "granted") {
      try {
        var n = new Notification("WhatsApp · " + ultima.nome, {
          body: ultima.trecho, tag: "cg-whatsapp-" + ultima.conversa_id, renotify: true,
          requireInteraction: false
        });
        n.onclick = function () {
          window.focus();
          window.location.href = endereco;
          n.close();
        };
      } catch (e) { /* o cartão e o som já avisaram */ }
    }
  }

  function conferirNova(ultima) {
    if (!ultima || typeof ultima.id !== "number") {
      return;
    }
    var visto = lerUltimo();
    if (!visto) {
      gravarUltimo(ultima.id);        // a primeira pergunta só anota
      return;
    }
    if (ultima.id > visto) {
      gravarUltimo(ultima.id);
      avisar(ultima);
    }
  }

  function perguntar() {
    if (parado || perguntando) {
      return;
    }
    perguntando = true;
    fetch(url, {credentials: "same-origin", headers: {"Accept": "application/json"}})
      .then(function (r) {
        var tipo = r.headers.get("Content-Type") || "";
        if (r.redirected || (r.ok && tipo.indexOf("application/json") !== 0)) {
          parar();
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (dados) {
        if (dados && !parado && typeof dados.n === "number") {
          mostrar(dados);
          conferirNova(dados.ultima);
        }
      })
      .catch(function () { /* a próxima pergunta tenta de novo */ })
      .then(function () { perguntando = false; });
  }

  // O relógio da aba visível é o da página; o da escondida, o do Worker.
  relogio = window.setInterval(function () {
    if (document.visibilityState === "visible") {
      perguntar();
    }
  }, VISIVEL_MS);
  try {
    worker = new Worker("/static/whatsapp_relogio.js");
    worker.onmessage = function () {
      if (document.visibilityState !== "visible") {
        perguntar();
      }
    };
    worker.postMessage(ESCONDIDA_MS);
  } catch (e) {
    worker = null;
    window.setInterval(function () {
      if (document.visibilityState !== "visible") {
        perguntar();
      }
    }, ESCONDIDA_MS);
  }
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      pararDePiscar();
      perguntar();
    }
  });
  window.addEventListener("focus", pararDePiscar);

  // O BOTÃO «LIGAR OS AVISOS DO WINDOWS» (na tela do WhatsApp). O navegador só
  // libera o aviso do sistema em endereço seguro (https, ou o próprio
  // servidor); no balcão em http, a tela diz o que fazer em vez de falhar calada.
  var botao = document.querySelector("[data-wa-ligar-avisos]");
  var situacao = document.querySelector("[data-wa-avisos-situacao]");
  function dizer(texto) {
    if (situacao) {
      situacao.textContent = texto;
    }
  }
  function situacaoAtual() {
    if (!("Notification" in window)) {
      dizer("Este navegador não tem aviso do Windows; o som e o cartão no canto avisam.");
    } else if (!window.isSecureContext) {
      dizer("Neste computador o navegador só libera o aviso do Windows com o endereço " +
            "seguro do sistema (peça à TI o ajuste do Chrome). O som e o cartão no canto avisam.");
    } else if (Notification.permission === "granted") {
      dizer("Avisos do Windows ligados neste computador.");
    } else if (Notification.permission === "denied") {
      dizer("O navegador bloqueou os avisos: libere no cadeado ao lado do endereço.");
    } else {
      dizer("");
    }
  }
  if (botao) {
    situacaoAtual();
    botao.addEventListener("click", function () {
      if (!("Notification" in window) || !window.isSecureContext) {
        situacaoAtual();
        return;
      }
      Notification.requestPermission().then(function () {
        situacaoAtual();
        tocar();
      });
    });
  }

  perguntar();
})();
