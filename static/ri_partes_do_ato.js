/* ACRESCENTAR PARTE NO ATO — RELATO #86, de 18/09/2026.
 *
 * O relato, nas palavras dele: «a parte de partes que participam do ato precisa
 * ser revista, precisa ser possivel incluir tantas quantas as partes do ato».
 *
 * O QUE ELE ACRESCENTA
 *   Clona o bloco que está no `<template data-modelo-parte>` e o põe no fim da
 *   lista. Não conta, não limita e não reordena: o pedido é «tantas quantas as
 *   partes do ato», e um teto aqui seria a tela escolhendo por quem lavra.
 *
 *   E O TETO DE TRÊS NÃO ERA TEÓRICO: medido na produção em 18/09/2026, **44
 *   atos desta casa têm mais de três partes** e o maior tem **22** (R-1 da
 *   matrícula 3.757, de 1984). O formulário desenhava três blocos e mais
 *   nenhum.
 *
 * E ELE NÃO GUARDA NADA
 *   Quem grava é a rota, que lê os `getlist("parte_nome")` — este arquivo só
 *   põe campos no formulário. É por isso que o botão NASCE ESCONDIDO e é
 *   revelado aqui: botão que parece acrescentar e não acrescenta é pior que
 *   botão nenhum, e o escrevente só descobriria no fim do ato. A mesma razão
 *   do botão de rascunho, em `rascunho.js`.
 *
 * SEM JAVASCRIPT A TELA CONTINUA SERVINDO
 *   O primeiro bloco em branco vem desenhado pelo servidor, e as partes
 *   guardadas na minuta também: sem este arquivo, o ato é lavrado com o que
 *   está na tela — o que se perde é só o caminho de acrescentar.
 *
 * POR QUE O MOLDE É UM ARQUIVO SEPARADO DA TELA
 *   Porque o desenho da parte é um só (`_parte_do_ato.html`), e a minuta
 *   suspensa pelo selo volta com as partes nos mesmos blocos. Escrever o bloco
 *   aqui dentro faria o bloco acrescentado divergir do primeiro no dia em que a
 *   tela ganhasse um campo.
 */
(function () {
  "use strict";

  function recontar(raiz) {
    var contagem = raiz.querySelector("[data-contagem]");
    if (!contagem) return;

    var todos = raiz.querySelectorAll("[data-parte]");
    var comNome = 0;
    Array.prototype.forEach.call(todos, function (bloco) {
      var nome = bloco.querySelector('input[name="parte_nome"]');
      if (nome && nome.value.trim()) comNome += 1;
    });

    /* A CONTA É SOBRE O QUE ESTÁ PREENCHIDO, e por isso ela acompanha a
       digitação: o bloco em branco não é gravado, e quem lê o número precisa
       saber quantas partes o ato vai ter de fato. */
    var frase = comNome + (comNome === 1 ? " parte com nome" : " partes com nome");
    var vazios = todos.length - comNome;
    if (vazios > 0) frase += " · " + vazios + " em branco";
    contagem.textContent = frase + " — bloco em branco não é gravado";
  }

  function ligar(raiz) {
    var caixa = raiz.querySelector("[data-partes-vazias]");
    var molde = raiz.querySelector("[data-modelo-parte]");
    var botao = raiz.querySelector("[data-acrescentar-parte]");
    if (!caixa || !molde || !botao) return;

    botao.hidden = false;

    botao.addEventListener("click", function () {
      caixa.appendChild(molde.content.cloneNode(true));
      var novo = caixa.lastElementChild;
      var primeiro = novo && novo.querySelector("input");
      /* O FOCO VAI PARA O CAMPO NOVO: quem clicou em «acrescentar parte» vai
         digitar — e sem isto o cursor ficaria onde estava, três blocos acima. */
      if (primeiro) primeiro.focus();
      recontar(raiz);
    });

    /* QUEM DIGITA TAMBÉM MUDA A CONTA: apagar o nome de uma das partes
       guardadas tem de refletir no número, senão ele diria «cinco partes com
       nome» sobre um ato de quatro. */
    raiz.addEventListener("input", function () { recontar(raiz); });
    recontar(raiz);
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-partes-do-ato]"), ligar);
  });
})();
