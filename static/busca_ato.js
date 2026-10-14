/*
  A LISTA DE ATOS DA TABELA ENQUANTO SE DIGITA — RELATO #53 do oficial.

  «itens da tabela ao procurar o ato poderiam ser listados automaticamente —
   para procurar um item para acrescentar da tabela no protocolo precisa clicar
   em pesquisar, daí recarrega a página e vai lá pra cima, fazendo perder
   tempo».

  O QUE ELE FAZ: espera a digitação parar, pede a lista ao servidor e troca só
  a lista. A página não recarrega, e a posição da tela não se perde — que era a
  segunda metade da queixa.

  O QUE ELE NÃO FAZ: não procura por conta própria. Quem responde é a mesma
  consulta de sempre (`emolumentos.buscar`), pela mesma macro que monta a lista
  do formulário. O formulário continua funcionando sem este script, e a tecla
  Enter recarrega com o resultado — é o caminho de volta se o pedido falhar.

  Só age onde existe `[data-busca-ato]`; nas outras telas não faz nada.
*/
(function () {
  "use strict";

  // A ESPERA É CURTA E EXISTE POR UM MOTIVO SÓ: sem ela, «certidão» são oito
  // pedidos ao servidor em vez de um. Curta demais não economiza nada; longa
  // demais faz o balcão achar que a tela travou.
  var ESPERA_MS = 250;

  function ligarBusca() {
    var campo = document.querySelector("[data-busca-ato]");
    if (!campo) { return; }
    var url = campo.getAttribute("data-url");
    var alvo = document.querySelector(campo.getAttribute("data-alvo") || "");
    if (!url || !alvo) { return; }

    // A FRASE SÓ APARECE COM O SCRIPT VIVO. Ela promete que a lista sai
    // enquanto se digita, e quem está sem JavaScript precisa clicar.
    var recado = document.querySelector("[data-busca-ato-recado]");
    if (recado) { recado.hidden = false; }

    var relogio = null;
    var pedidoAtual = 0;

    function desenhar(html) {
      alvo.innerHTML = html;
    }

    function buscar() {
      var termo = campo.value;
      var meu = ++pedidoAtual;
      var endereco = url + "?busca=" + encodeURIComponent(termo);
      fetch(endereco, { headers: { "X-Requested-With": "fetch" } })
        .then(function (resposta) {
          if (!resposta.ok) { throw new Error(String(resposta.status)); }
          return resposta.text();
        })
        .then(function (html) {
          // RESPOSTA VELHA NÃO DESENHA: se a pessoa continuou digitando
          // enquanto o pedido anterior viajava, quem manda é o último termo.
          if (meu !== pedidoAtual) { return; }
          desenhar(html);
        })
        .catch(function () {
          // NÃO SE TROCA A LISTA POR UM ERRO MUDO. O formulário continua ali:
          // quem quiser a resposta aperta o botão, que recarrega a página pelo
          // caminho de sempre.
          if (meu !== pedidoAtual) { return; }
        });
    }

    campo.addEventListener("input", function () {
      if (relogio) { clearTimeout(relogio); }
      relogio = setTimeout(buscar, ESPERA_MS);
    });

    // O FORMULÁRIO NÃO RECARREGA QUANDO O SCRIPT ESTÁ VIVO — é justamente o
    // «vai lá pra cima» que o relato pede para acabar. Sem o script, o
    // `submit` acontece como sempre aconteceu.
    var formulario = campo.form;
    if (formulario) {
      formulario.addEventListener("submit", function (evento) {
        evento.preventDefault();
        if (relogio) { clearTimeout(relogio); }
        buscar();
      });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ligarBusca);
  } else {
    ligarBusca();
  }
})();
