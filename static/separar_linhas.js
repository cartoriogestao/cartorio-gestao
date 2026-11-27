/*
  «UMA LINHA COM N» OU «N LINHAS DE 1» — T023, pedido da operadora em
  27/11/2026.

  No protocolo do caixa, ao acrescentar um item com quantidade maior que 1, o
  balcão escolhe o que a quantidade quer dizer: uma linha com N (como sempre:
  as folhas de um ato só, ou várias unidades no RI) ou N linhas de 1, uma para
  cada ato. A escolha está no HTML de cada formulário (`[data-separar]`).

  O QUE ELE FAZ: esconde a escolha enquanto a quantidade do mesmo formulário
  for 1, e troca o «N» do texto pelo número digitado. Só isso.

  O QUE ELE NÃO FAZ: não escolhe nada. «Uma linha com N» vem marcada no HTML,
  e sem este script a escolha aparece sempre. As linhas da busca chegam depois
  (`busca_ato.js` troca a lista), e por isso o ajuste também roda quando a
  página muda.

  Só age onde existe `[data-separar]`; nas outras telas não faz nada.
*/
(function () {
  "use strict";

  function quantidadeDo(formulario) {
    var campo = formulario && formulario.querySelector('input[name="quantidade"]');
    var n = campo ? parseInt(String(campo.value || "").replace(/\D/g, ""), 10) : 1;
    return isNaN(n) ? 1 : n;
  }

  function ajustar(escolha) {
    var n = quantidadeDo(escolha.closest("form"));
    escolha.hidden = n <= 1;
    var nomes = escolha.querySelectorAll("[data-separar-n]");
    var texto = n > 1 ? String(n) : "N";
    // Só escreve o que mudou: escrever o mesmo texto também avisaria o
    // observador da lista, que chamaria isto de novo, sem fim.
    for (var i = 0; i < nomes.length; i++) {
      if (nomes[i].textContent !== texto) { nomes[i].textContent = texto; }
    }
  }

  function ajustarTodas(raiz) {
    var escolhas = (raiz || document).querySelectorAll("[data-separar]");
    for (var i = 0; i < escolhas.length; i++) { ajustar(escolhas[i]); }
  }

  function ligar() {
    if (!document.querySelector("[data-separar]") &&
        !document.querySelector("[data-atos-da-tabela]")) { return; }
    ajustarTodas(document);
    document.addEventListener("input", function (evento) {
      var alvo = evento.target;
      if (!alvo || alvo.name !== "quantidade" || !alvo.form) { return; }
      var escolhas = alvo.form.querySelectorAll("[data-separar]");
      for (var i = 0; i < escolhas.length; i++) { ajustar(escolhas[i]); }
    });
    // A LISTA DA BUSCA É TROCADA INTEIRA enquanto se digita: as linhas novas
    // chegam com a escolha à vista, e é aqui que ela se esconde.
    var lista = document.querySelector("[data-atos-da-tabela]");
    if (lista && window.MutationObserver) {
      new MutationObserver(function () { ajustarTodas(lista); })
        .observe(lista, { childList: true, subtree: true });
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ligar);
  } else {
    ligar();
  }
})();
