/* =========================================================================
   O AGENTE — a gaveta em toda tela, e a sessão que cresce sozinha.

   O PROBLEMA, EM UMA LINHA
       A pergunta que se faz ao agente nasce no meio de outro trabalho —
       «por que o ato 3728 da 3110 ficou sem selo?» —, e ir até o console para
       perguntar custa o que estava sendo feito. É a mesma razão da janela da
       ajuda, com uma diferença que muda o desenho: esta OPERA.

   UM MOTOR, DOIS LUGARES
       A gaveta e a tela da sessão fazem a mesma coisa — pedem ao servidor «o
       que veio depois», anexam o HTML que ele mandou e andam com os cursores.
       O que muda é o ritmo e o que se faz com o resto da resposta: a gaveta
       CONTA as mudanças e leva ao console, a sessão as DESENHA, porque é lá que
       o botão de desfazer mora. Escrito duas vezes, o segundo motor divergiria
       no primeiro conserto — e a página que ficasse para trás mostraria a
       conversa parada sem avisar. É a mesma decisão do `_agente_passos.html`.

   POR QUE NADA ESPERA A RESPOSTA
       Um turno do agente leva dezenas de segundos e uma sessão inteira pode
       levar minutos. O `POST` abre a sessão e responde na hora com o id; o que
       a rodada produziu chega depois, aos pedaços, em `/agente/andamento/<id>`.
       Nada aqui fica parado esperando — quem espera é o balcão, e ele tem
       cliente na frente.

   POR QUE OS CURSORES ANDAM PARA A FRENTE
       Cada resposta traz `proximo` e `mudanca_proxima`, que são o ponto até
       onde já se leu, e a resposta seguinte traz SÓ o que veio depois. Sem
       isso, a cada segundo a tela releria a conversa inteira para descobrir que
       nada mudou — e o resultado de uma tabela pode ter dezenas de linhas.

   O QUE ENTRA NA TELA ENTRA COMO HTML MONTADO PELO SERVIDOR
       `_agente_passos.html` e `_agente_mudancas.html`, os mesmos que desenham a
       sessão inteira. Montar a conversa aqui em JavaScript faria dois desenhos
       da mesma coisa — e o segundo traria a linha da mudança sem o botão de
       desfazer, que é justamente o que a torna defensável. O texto do modelo
       fica entre o `<pre>` e o `<div>`, que é onde o escapamento do Jinja já
       aconteceu.

   A RODADA CONTINUA QUANDO A GAVETA FECHA
       Fechar a gaveta não cancela nada: a linha de execução é do servidor. O
       que muda é o ritmo — fechada e com trabalho em curso, ela pergunta de
       3 em 3 segundos só para o ponto verde não mentir; aberta, pergunta de
       segundo em segundo.

       O PONTO SÓ ACENDE DEPOIS DA PRIMEIRA ABERTURA, e isso é deliberado: a
       alternativa era perguntar ao servidor em TODA tela do sistema, para
       desenhar um enfeite que a maioria das pessoas não olha.

   SEM ESTE ARQUIVO TUDO CONTINUA FUNCIONANDO
       O botão é um link para o console, o formulário posta em `agente_pedir`, e
       a página da sessão desenha a conversa até onde ela estava quando abriu.
       Daqui depende só o conforto — e o tempo real.
   ========================================================================= */
(function () {
  "use strict";

  // --------------------------------------------------------------- o motor

  /* UMA SUPERFÍCIE É UMA COISA QUE MOSTRA A CONVERSA. Duas existem: a gaveta,
     em toda tela, e o quadro da sessão. O que elas têm em comum mora aqui; o
     que as separa mora no `aoChegar` e no `ritmo` de cada uma. */
  function superficie(opcoes) {
    return {
      conversa: opcoes.conversa,
      sessao: opcoes.sessao,
      url: opcoes.url,
      desde: opcoes.desde || 0,
      mudancaDesde: opcoes.mudancaDesde || 0,
      ritmo: opcoes.ritmo,
      aoChegar: opcoes.aoChegar || null,
      perguntando: false,
      relogio: null
    };
  }

  /* OS ENDEREÇOS VÊM DO SERVIDOR COM `-1` NO LUGAR DO ID, e é aqui que ele
     entra. Montar o caminho à mão seria escrever a regra de rotas num segundo
     lugar — e no dia em que a rota mudasse de forma, a gaveta chamaria o
     endereço velho sem ninguém para avisar. O `-1` é trocado ANTES dos
     cursores: com o id ainda por substituir, a pergunta iria para a sessão
     errada. */
  function comId(modelo, id) {
    return String(modelo || "").replace("-1", String(id));
  }

  function comCursores(sup) {
    var modelo = comId(sup.url, sup.sessao);
    return modelo + (modelo.indexOf("?") >= 0 ? "&" : "?")
      + "desde=" + sup.desde + "&mudanca_desde=" + sup.mudancaDesde;
  }

  function anexar(onde, html) {
    if (!onde || !html) return;
    var pedaco = document.createElement("div");
    pedaco.innerHTML = html;              // vem montado e escapado pelo Jinja
    while (pedaco.firstChild) onde.appendChild(pedaco.firstChild);
    onde.scrollTop = onde.scrollHeight;
  }

  /* A PERGUNTA É UMA SÓ, E NÃO DUAS AO MESMO TEMPO. Duas em voo somariam os
     mesmos cursores duas vezes e desenhariam o mesmo passo em duplicata — o
     passo apareceria duas vezes na conversa, e ninguém saberia qual apagar. */
  function perguntar(sup) {
    if (sup.relogio) { clearTimeout(sup.relogio); sup.relogio = null; }
    if (!sup.sessao || sup.perguntando) return;
    sup.perguntando = true;
    fetch(comCursores(sup), { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        sup.perguntando = false;
        if (!d || !d.ok) {
          if (sup.aoChegar) sup.aoChegar({ falha: true, erro: (d && d.erro) || "" });
          return;
        }
        anexar(sup.conversa, d.html);
        sup.desde = d.proximo || sup.desde;
        sup.mudancaDesde = d.mudanca_proxima || sup.mudancaDesde;
        if (sup.aoChegar) sup.aoChegar(d);
        if (d.rodando) {
          sup.relogio = setTimeout(function () { perguntar(sup); }, sup.ritmo());
        }
      })
      .catch(function () {
        sup.perguntando = false;
        if (sup.aoChegar) sup.aoChegar({ falha: true, erro: "" });
      });
  }

  var PERDI_A_LIGACAO = "Perdi a ligação com o servidor do cartório. "
    + "Ele continua trabalhando — reabra a gaveta para ver.";

  // ------------------------------------------------------------- a gaveta

  var caixa = null;          // o `[data-agente]` inteiro
  var painel = null;         // a parte que abre e fecha
  var conversa = null;       // onde os passos entram
  var formulario = null;
  var campo = null;
  var botao = null;
  var linhaEstado = null;
  var ponto = null;
  var carregada = false;     // a gaveta já buscou o resumo uma vez?
  var mudancas = 0;          // quantas ele já fez nesta conversa
  var urls = {};
  var gaveta = null;         // a superfície da gaveta

  function estadoGaveta(texto, classe) {
    if (!linhaEstado) return;
    linhaEstado.textContent = texto || "";
    linhaEstado.className = "agente-estado" + (classe ? " " + classe : "");
  }

  function ligarPonto(aceso) {
    if (!ponto) return;
    ponto.hidden = !aceso;
  }

  /* UMA LINHA SÓ PARA DIZER COMO ELE ESTÁ, e não três: o texto da espera, o do
     fim e o do erro são o mesmo lugar da tela. Três lugares fariam quem opera
     procurar onde a notícia saiu desta vez. */
  function desenharGaveta(d) {
    if (!d) { ligarPonto(false); return; }
    if (d.falha) {
      estadoGaveta(d.erro || PERDI_A_LIGACAO, "ruim");
      ligarPonto(false);
      return;
    }
    if (d.rodando) {
      estadoGaveta("trabalhando… " + d.turnos + " turno(s), " + d.tokens
                   + " tokens"
                   + (mudancas ? ", " + mudancas + " mudança(s)" : ""));
      ligarPonto(true);
    } else if (d.recado) {
      estadoGaveta(d.recado.texto,
                   d.recado.tom === "success" ? "feito"
                     : (d.recado.tom === "danger" ? "ruim" : ""));
      ligarPonto(false);
    } else {
      estadoGaveta("");
      ligarPonto(false);
    }
  }

  function trocarPelaSessao(dados) {
    gaveta.sessao = dados.sessao ? dados.sessao.id : 0;
    if (conversa) conversa.innerHTML = "";
    anexar(conversa, dados.html);
    gaveta.desde = dados.proximo || 0;
    gaveta.mudancaDesde = dados.mudanca_proxima || 0;
    mudancas = 0;
    var escondido = formulario.querySelector("[data-agente-sessao-id]");
    if (escondido) escondido.value = gaveta.sessao ? String(gaveta.sessao) : "";
    formulario.action = gaveta.sessao
      ? comId(urls.responder, gaveta.sessao) : urls.pedir;
    if (botao) botao.textContent = gaveta.sessao ? "Continuar" : "Pedir";
  }

  function buscarGaveta() {
    estadoGaveta("carregando…");
    fetch(urls.gaveta, { credentials: "same-origin" })
      .then(function (r) { return r.json(); })
      .then(function (d) {
        if (!d.ok) {
          estadoGaveta(d.erro || "Não consegui carregar.", "ruim");
          return;
        }
        var cabecalho = caixa.querySelector("[data-agente-provedor]");
        if (cabecalho) {
          var c = d.config || {};
          cabecalho.textContent = (c.provedor_padrao || "—")
            + (c.modelo_padrao ? " · " + c.modelo_padrao : "")
            + (c.escrita_ligada ? " · escrita ligada" : " · só leitura");
        }
        var quadro = caixa.querySelector("[data-agente-avisos]");
        if (quadro) {
          if (d.avisos && d.avisos.length) {
            quadro.hidden = false;
            quadro.textContent = "";        // aviso do servidor vira TEXTO
            var lista = document.createElement("ul");
            d.avisos.forEach(function (a) {
              var li = document.createElement("li");
              li.textContent = a;
              lista.appendChild(li);
            });
            quadro.appendChild(lista);
          } else {
            quadro.hidden = true;
          }
        }
        trocarPelaSessao(d);
        desenharGaveta(d);
        /* A RODADA PODE TER SIDO ABERTA NUMA VISITA ANTERIOR — ou estar em
           curso agora, pedida da tela do console. Se está, a gaveta passa a
           acompanhar; se não, ela mostra o fim e para. */
        if (d.rodando) perguntar(gaveta);
      })
      .catch(function () {
        estadoGaveta("Não consegui falar com o servidor do cartório.", "ruim");
      });
  }

  // -------------------------------------------------------- a sessão viva

  /* AQUI A BUSCA É NO DOCUMENTO INTEIRO, E NA GAVETA É DENTRO DA CAIXA — e a
     diferença é deliberada. O que a sessão atualiza não está só no quadro da
     conversa: o SELO, os turnos e os tokens moram no cabeçalho, três painéis
     acima. Procurá-los a partir do quadro da conversa não acharia nada. É
     seguro porque o cabeçalho da sessão é desenhado por um modelo que só existe
     nesta tela, e porque a gaveta NÃO aparece nas telas do agente
     (`agente_web.TELAS_DO_AGENTE`) — não há dois `[data-agente-selo]` na mesma
     página. */
  var pagina = null;         // { raiz, sup }

  function desenharPagina(d) {
    var linha = document.querySelector("[data-agente-estado]");
    if (!linha) return;
    if (!d) return;
    if (d.falha) {
      linha.textContent = d.erro
        || "Perdi a ligação com o servidor do cartório. Ele continua "
           + "trabalhando — recarregue a página para ver.";
      linha.className = "agente-estado ruim";
      return;
    }
    /* O CABEÇALHO ANDA JUNTO. Ele diz «parou no teto · 3 turnos · 4.000
       tokens», e é o preço do que está rodando; deixá-lo parado enquanto a
       conversa cresce faria a tela dizer duas coisas diferentes sobre a mesma
       sessão — e a que se acredita é o selo. A palavra e a cor vêm do servidor
       (`agente_schema.selo_do_estado`), e não de uma tradução escrita aqui. */
    var selo = document.querySelector("[data-agente-selo]");
    if (selo && d.selo) {
      selo.textContent = d.selo.texto;
      selo.className = "badge" + (d.selo.classe ? " " + d.selo.classe : "");
    }
    var turnos = document.querySelector("[data-agente-turnos]");
    if (turnos && d.turnos !== undefined) turnos.textContent = d.turnos;
    if (d.rodando) {
      linha.textContent = "ele está trabalhando… " + d.total_de_passos
        + " passo(s) até agora";
      linha.className = "agente-estado";
    } else if (d.recado) {
      linha.textContent = d.recado.texto;
      linha.className = "agente-estado "
        + (d.recado.tom === "success" ? "feito"
           : (d.recado.tom === "danger" ? "ruim" : ""));
    } else {
      linha.textContent = "";
      linha.className = "agente-estado";
    }
  }

  /* A SESSÃO NÃO RECEBE O NÚMERO DE MUDANÇAS: ela recebe as LINHAS. É aqui que
     a diferença com a gaveta aparece — a gaveta conta e leva ao console, porque
     desfazer é ato com consequência e ela é estreita; a sessão é o lugar onde o
     botão de desfazer mora, e ali a mudança tem de aparecer com ele. */
  function anexarMudancas(html) {
    if (!html) return;
    var corpo = document.querySelector("[data-agente-mudancas]");
    if (!corpo) return;
    var vazio = corpo.querySelector("[data-agente-mudancas-vazio]");
    if (vazio) vazio.remove();
    anexar(corpo, html);
    /* A CONTA É CONTADA, E NÃO SOMADA DE UM EM UM: a resposta pode trazer três
       linhas de uma vez, e um contador que somasse um diria «1» com três
       mudanças à vista. */
    var conta = document.querySelector("[data-agente-mudancas-conta]");
    if (conta) conta.textContent = String(corpo.querySelectorAll("tr").length);
  }

  function aoChegarNaPagina(d) {
    if (d && d.mudancas_html) anexarMudancas(d.mudancas_html);
    desenharPagina(d);
  }

  function montarPagina() {
    var e = document.querySelector("[data-agente-vivo]");
    if (!e) return;
    var quadro = e.querySelector("[data-agente-conversa]");
    if (!quadro) return;
    pagina = {
      raiz: e,
      sup: superficie({
        conversa: quadro,
        sessao: Number(e.getAttribute("data-sessao") || 0),
        url: e.getAttribute("data-url-andamento"),
        desde: Number(e.getAttribute("data-desde") || 0),
        mudancaDesde: Number(e.getAttribute("data-mudanca-desde") || 0),
        /* A SESSÃO É O QUE ALGUÉM ESTÁ OLHANDO, e enquanto ela roda o que se
           quer é ver acontecer: um segundo é o ritmo. A gaveta fechada é que
           afrouxa, porque lá o que importa é só o ponto verde não mentir. */
        ritmo: function () { return 1000; },
        aoChegar: aoChegarNaPagina
      })
    };
    /* SEM JAVASCRIPT A PÁGINA NÃO PERDE NADA: ela mostra a conversa até onde
       estava quando abriu, e quem quiser ver o resto recarrega. O que este
       arquivo ganha é não precisar recarregar. */
    if (e.getAttribute("data-rodando") === "1") perguntar(pagina.sup);
  }

  // ------------------------------------------------------- abrir e fechar

  function abrir() {
    if (!painel) return;
    painel.hidden = false;
    caixa.classList.add("aberta");
    if (campo) campo.focus();
    if (!carregada) {
      carregada = true;
      buscarGaveta();
    }
  }

  function fechar() {
    if (!painel) return;
    painel.hidden = true;
    caixa.classList.remove("aberta");
    /* FECHAR NÃO CANCELA NADA. A rodada é uma linha de execução do servidor, e
       o que muda aqui é só o ritmo da pergunta seguinte — quem o decide é o
       `ritmo`, olhando se a gaveta está à vista. Sem reagendar, o ponto verde
       ficaria aceso dizendo o que ninguém mais vai atualizar. */
    if (gaveta && gaveta.sessao && ponto && !ponto.hidden
        && !gaveta.relogio && !gaveta.perguntando) {
      gaveta.relogio = setTimeout(function () { perguntar(gaveta); }, 3000);
    }
  }

  function alternar() {
    if (painel && painel.hidden) abrir(); else fechar();
  }

  // ------------------------------------------------------------- o pedido

  function enviar(evento) {
    evento.preventDefault();
    if (!campo || !campo.value.trim()) {
      estadoGaveta("Escreva o que você quer que ele apure.", "ruim");
      if (campo) campo.focus();
      return;
    }
    var dados = new FormData(formulario);
    dados.append("formato", "json");
    var destino = gaveta.sessao
      ? comId(urls.responder, gaveta.sessao) : urls.pedir;
    if (botao) botao.disabled = true;
    estadoGaveta("mandando…");

    fetch(destino, {
      method: "POST",
      body: dados,
      credentials: "same-origin",
      headers: { "X-CSRF-Token": dados.get("csrf_token") || "" }
    }).then(function (r) {
      return r.json();
    }).then(function (d) {
      if (botao) botao.disabled = false;
      if (!d || !d.ok) {
        /* A RECUSA ACONTECE ANTES DE GASTAR TURNO — sem chave, escrita
           desligada, pedido vazio, teto do dia. E O TEXTO NÃO SE PERDE: quem
           escreveu quatro linhas e levou um «não» precisa delas de volta, e o
           campo continua com o que estava escrito. */
        estadoGaveta((d && d.erro) || "Ele não aceitou o pedido.", "ruim");
        return;
      }
      gaveta.sessao = d.sessao_id;
      var escondido = formulario.querySelector("[data-agente-sessao-id]");
      if (escondido) escondido.value = String(gaveta.sessao);
      formulario.action = comId(urls.responder, gaveta.sessao);
      if (botao) botao.textContent = "Continuar";
      campo.value = "";
      estadoGaveta("ele está trabalhando…");
      ligarPonto(true);
      /* O PRIMEIRO PASSO JÁ ESTÁ GRAVADO quando esta resposta chega — a sessão
         é gravada antes de a rodada começar. Buscar agora evita o segundo de
         gaveta vazia logo depois de alguém clicar em «Pedir». */
      perguntar(gaveta);
    }).catch(function () {
      if (botao) botao.disabled = false;
      estadoGaveta("Não consegui mandar o pedido ao servidor do cartório.", "ruim");
    });
  }

  /* A CONVERSA ANTERIOR NÃO SE PERDE: ela fica em `ag_sessoes` e o console a
     lista. O que este botão faz é abrir espaço para outro assunto — misturar
     dois assuntos na mesma sessão faria o histórico contar duas histórias. */
  function outra() {
    if (gaveta.relogio) { clearTimeout(gaveta.relogio); gaveta.relogio = null; }
    gaveta.sessao = 0;
    if (conversa) conversa.innerHTML = "";
    gaveta.desde = 0;
    gaveta.mudancaDesde = 0;
    mudancas = 0;
    var escondido = formulario.querySelector("[data-agente-sessao-id]");
    if (escondido) escondido.value = "";
    formulario.action = urls.pedir;
    if (botao) botao.textContent = "Pedir";
    estadoGaveta("");
    ligarPonto(false);
    if (campo) { campo.value = ""; campo.focus(); }
  }

  function comecar() {
    caixa = document.querySelector("[data-agente]");
    if (caixa) {
      painel = caixa.querySelector("[data-agente-gaveta]");
      conversa = caixa.querySelector("[data-agente-conversa]");
      formulario = caixa.querySelector("[data-agente-form]");
    }
    if (painel && conversa && formulario) {
      campo = formulario.querySelector("textarea[name=pedido]");
      botao = formulario.querySelector("[data-agente-enviar]");
      linhaEstado = caixa.querySelector("[data-agente-estado]");
      ponto = caixa.querySelector("[data-agente-ponto]");
      urls = {
        gaveta: caixa.getAttribute("data-url-gaveta"),
        responder: caixa.getAttribute("data-url-responder"),
        pedir: caixa.getAttribute("data-url-pedir")
      };
      gaveta = superficie({
        conversa: conversa,
        sessao: 0,
        url: caixa.getAttribute("data-url-andamento"),
        /* O RITMO DA GAVETA DEPENDE DE ELA ESTAR À VISTA. Aberta, de segundo em
           segundo — quem está olhando quer ver acontecer. Fechada e com
           trabalho em curso, de 3 em 3: só o suficiente para o ponto verde não
           mentir. */
        ritmo: function () { return painel.hidden ? 3000 : 1000; },
        aoChegar: function (d) {
          if (d && d.mudancas_novas) mudancas += d.mudancas_novas;
          desenharGaveta(d);
        }
      });

      var chamar = caixa.querySelector("[data-agente-abrir]");
      if (chamar) {
        chamar.addEventListener("click", function (evento) {
          evento.preventDefault();     // sem script, este link ABRE o console
          alternar();
        });
      }
      var fecharBotao = caixa.querySelector("[data-agente-fechar]");
      if (fecharBotao) fecharBotao.addEventListener("click", fechar);
      var botaoOutra = caixa.querySelector("[data-agente-parar]");
      if (botaoOutra) {
        botaoOutra.hidden = false;
        botaoOutra.addEventListener("click", outra);
      }

      formulario.addEventListener("submit", enviar);

      document.addEventListener("keydown", function (evento) {
        if (evento.key === "Escape" && painel && !painel.hidden) fechar();
      });
    }
    montarPagina();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", comecar);
  } else {
    comecar();
  }
})();
