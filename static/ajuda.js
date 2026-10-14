/* =========================================================================
   A JANELA DA AJUDA — perguntar sem sair da tela.

   O PROBLEMA, EM UMA LINHA
       A ajuda era uma tela do menu Administrativo. Quem tinha duvida no meio
       de um ato precisava sair do que estava fazendo para chegar ate ela — e
       perder o que ja tinha digitado.

   POR QUE ISSO IMPORTA NO BALCAO
       A duvida do escrevente nasce COM o cliente na frente e com a ficha meio
       preenchida. Ajuda que cobra o abandono da tarefa e ajuda que ninguem usa
       na hora em que precisa; ele desiste, chuta, e o chute vira ato.

   O QUE ESTE ARQUIVO FAZ, E O QUE ELE NAO FAZ
       Ele NAO desenha a janela: o botao, a gaveta e os dois formularios ja vem
       prontos em `templates/_ajuda.html`. O que ele faz e trocar a NAVEGACAO
       por abrir e fechar, e mandar o formulario por tras da tela.

       Sem este arquivo — script bloqueado, navegador antigo, arquivo que nao
       carregou — o botao continua sendo um link para a tela inteira e os dois
       formularios continuam sendo formularios que respondem pagina. Nada
       depende daqui para funcionar; daqui depende so o conforto.

   POR QUE SEM BIBLIOTECA DE FORA
       A mesma razao da lupa: o sistema roda na rede da serventia e ha maquina
       que nao alcanca a internet. Biblioteca de CDN seria uma ajuda que
       funciona no escritorio e falha no balcao.

   O TEXTO DA RESPOSTA ENTRA POR `textContent`, E POR MAIS NADA.
       O que volta da API e texto de fora. Escrever texto de fora como HTML e
       deixar a resposta desenhar na tela do cartorio.

       (A outra forma de escrever nao esta citada aqui de proposito: o teste
       que guarda esta regra le o arquivo inteiro, comentario incluido, e
       contaria a citacao como se fosse uso. E a terceira vez que isto
       acontece neste projeto — foi assim no teto de portabilidade, duas
       vezes. **Regra que se aplica ao arquivo inteiro alcanca tambem o
       comentario que fala dela.**)
   ========================================================================= */
(function () {
  "use strict";

  var caixa = null;      // o `[data-ajuda]` inteiro
  var gaveta = null;     // a parte que abre e fecha

  function abrir() {
    if (!gaveta) return;
    gaveta.hidden = false;
    caixa.classList.add("aberta");
    var campo = gaveta.querySelector("textarea, input[type=text], input:not([type])");
    if (campo) campo.focus();
  }

  function fechar() {
    if (!gaveta) return;
    gaveta.hidden = true;
    caixa.classList.remove("aberta");
  }

  function alternar() {
    if (gaveta && gaveta.hidden) abrir(); else fechar();
  }

  // O QUADRO DA RESPOSTA. Uma funcao so, porque a resposta, o erro e o
  // "perguntando..." sao o mesmo lugar da tela — e tres lugares diferentes
  // fariam a pessoa procurar onde a resposta saiu desta vez.
  function mostrar(texto, classe, endereco) {
    var quadro = gaveta.querySelector("[data-ajuda-resposta]");
    if (!quadro) return;
    quadro.hidden = false;
    quadro.className = "ajuda-resposta" + (classe ? " " + classe : "");
    quadro.textContent = texto;
    if (endereco) {
      var link = document.createElement("a");
      link.href = endereco;
      link.textContent = "Ver o que foi enviado";
      quadro.appendChild(document.createElement("br"));
      quadro.appendChild(link);
    }
  }

  function mandar(formulario, destino, aoVoltar) {
    var dados = new FormData(formulario);
    dados.append("formato", "json");
    fetch(destino, {
      method: "POST",
      body: dados,
      credentials: "same-origin",
      headers: { "X-CSRF-Token": dados.get("csrf_token") || "" }
    }).then(function (r) {
      return r.json();
    }).then(aoVoltar).catch(function () {
      // A REDE DAQUI ATE O PROPRIO SERVIDOR. Isto nao e a API: e o servidor da
      // serventia, na mesma sala. Cair aqui quer dizer outra coisa, e por isso
      // a mensagem e outra.
      mostrar("Nao consegui falar com o servidor do cartorio. Isso nao impede "
              + "nenhum ato: siga o atendimento.", "ruim");
    });
  }

  function ligarPergunta() {
    var formulario = gaveta.querySelector("[data-ajuda-perguntar]");
    if (!formulario) return;
    formulario.addEventListener("submit", function (evento) {
      var destino = caixa.getAttribute("data-url-janela");
      if (!destino) return;                 // sem rota, o formulario segue sozinho
      evento.preventDefault();
      var botao = formulario.querySelector("button[type=submit]");
      if (botao) botao.disabled = true;
      mostrar("Perguntando… isto costuma levar alguns segundos.", "esperando");
      mandar(formulario, destino, function (resposta) {
        if (botao) botao.disabled = false;
        if (resposta && resposta.ok) {
          mostrar(resposta.resposta, "", resposta.endereco);
          // O CAMPO SE ESVAZIA DEPOIS DA RESPOSTA.
          //
          //   Relatado pelo oficial em 27/08/2026: «quando quero mandar uma
          //   nova ajuda, preciso apagar o texto da anterior, que segue no
          //   campo mesmo apos a resposta». Ele estava certo: sem limpar, a
          //   segunda pergunta nasce dentro da primeira, e quem nao apagar
          //   manda as duas juntas.
          //
          //   So se limpa quando a resposta VEIO. Se a ajuda recusou ou a
          //   rede caiu, o texto fica — apagar a pergunta de quem vai tentar
          //   de novo e faze-la digitar tudo outra vez.
          var campo = formulario.querySelector("textarea, input[type=text]");
          if (campo) campo.value = "";
        } else {
          mostrar((resposta && resposta.erro) || "A ajuda nao respondeu.", "ruim");
        }
      });
    });
  }

  function ligarProblema() {
    var formulario = gaveta.querySelector("[data-ajuda-problema]");
    if (!formulario) return;
    formulario.addEventListener("submit", function (evento) {
      var destino = caixa.getAttribute("data-url-problema");
      if (!destino) return;
      evento.preventDefault();
      var botao = formulario.querySelector("button[type=submit]");
      if (botao) botao.disabled = true;
      mandar(formulario, destino, function (resposta) {
        if (botao) botao.disabled = false;
        var recado = formulario.querySelector(".ajuda-recado");
        if (!recado) {
          recado = document.createElement("p");
          recado.className = "ajuda-recado";
          formulario.appendChild(recado);
        }
        if (resposta && resposta.ok) {
          recado.textContent = resposta.recado;
          formulario.reset();
        } else {
          recado.textContent = (resposta && resposta.erro)
            || "Nao consegui anotar o problema.";
        }
      });
    });
  }

  function comecar() {
    caixa = document.querySelector("[data-ajuda]");
    if (!caixa) return;
    gaveta = caixa.querySelector("[data-ajuda-gaveta]");
    if (!gaveta) return;

    var chamar = caixa.querySelector("[data-ajuda-abrir]");
    if (chamar) {
      chamar.addEventListener("click", function (evento) {
        evento.preventDefault();          // sem script, este link ABRE A TELA
        alternar();
      });
    }
    var fecharBotao = caixa.querySelector("[data-ajuda-fechar]");
    if (fecharBotao) fecharBotao.addEventListener("click", fechar);

    document.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape" && gaveta && !gaveta.hidden) fechar();
    });

    ligarPergunta();
    ligarProblema();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", comecar);
  } else {
    comecar();
  }
})();
