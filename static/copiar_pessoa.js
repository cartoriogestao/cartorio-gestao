/*
  PREENCHER UMA PESSOA COM OS DADOS DE OUTRA JÁ DIGITADA NO MESMO FORMULÁRIO.

  «dar a opçao de inserir os dados de algum da filiacao como declarante no
   registro de nascimento, facilitar o preenchimento automatico» — o oficial.

  Na prática o declarante costuma ser o pai ou a mãe, e o balcão redigitava o
  que já tinha escrito duas gavetas acima. O botão copia os campos de uma
  pessoa já preenchida (mãe, pai...) para outra (o declarante) — não inventa
  nada, só evita repetir o que já foi digitado. Só age onde existe
  `[data-copiar-de]`; sem o script, os dois blocos continuam preenchíveis à
  mão como sempre foram.

  A CÓPIA SOBRESCREVE, DE PROPÓSITO: "usar os dados de" só faz sentido assim,
  e o botão fica no bloco de quem ainda não foi preenchido. Depois de copiar o
  escrevente confere e edita o que for diferente — o botão preenche, não
  decide quem é o declarante.
*/
(function () {
  "use strict";

  window.copiarDadosDaPessoa = function (dePrefixo, paraPrefixo) {
    var prefixoOrigem = dePrefixo + "_";
    var camposDeOrigem = document.querySelectorAll(
      '[name^="' + prefixoOrigem + '"]'
    );
    camposDeOrigem.forEach(function (campoOrigem) {
      var sufixo = campoOrigem.name.slice(prefixoOrigem.length);
      var campoDestino = document.querySelector(
        '[name="' + paraPrefixo + "_" + sufixo + '"]'
      );
      if (!campoDestino) { return; }
      campoDestino.value = campoOrigem.value;
    });
  };
})();
