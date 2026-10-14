/* UMA GAVETA ABERTA DE CADA VEZ.
 *
 * Relato #37, item 6, de 31/08/2026: «quando abrir um campo, como filiação 2,
 * guardar, por exemplo, os outros — como filiação 1 e dados do registrado —
 * para a tela não ficar muito comprida».
 *
 * A tela de lavrar um nascimento tem oito gavetas de pessoas (registrado, duas
 * filiações, dois grupos de avós, declarante, testemunha). Abertas todas, ela
 * passa de dez telas de altura e quem preenche perde de vista onde estava.
 *
 * POR QUE ISTO É JAVASCRIPT, E NÃO CSS
 *   Dá para fazer «um de cada vez» só com HTML, pondo o mesmo `name` em todos
 *   os `<details>` — é o comportamento de acordeão que o navegador já tem. Mas
 *   ele **fecha a gaveta aberta mesmo quando há campo preenchido dentro**, e
 *   aqui isso esconderia dado digitado no meio de um formulário longo. Este
 *   arquivo fecha só as gavetas VAZIAS.
 *
 * E SEM JAVASCRIPT A TELA CONTINUA INTEIRA: cada `<details>` abre e fecha
 * sozinho, como antes. O que se perde é o fechar automático, e não o campo.
 */
(function () {
  "use strict";

  function temAlgoEscrito(gaveta) {
    var campos = gaveta.querySelectorAll("input, textarea, select");
    for (var i = 0; i < campos.length; i++) {
      var c = campos[i];
      if (c.type === "checkbox" || c.type === "radio") {
        if (c.checked) return true;
      } else if (String(c.value || "").trim()) {
        return true;
      }
    }
    return false;
  }

  function ligar(grupo) {
    var gavetas = grupo.querySelectorAll("details.panel");
    if (gavetas.length < 3) return;   /* com duas, fechar não ajuda ninguém */

    Array.prototype.forEach.call(gavetas, function (gaveta) {
      gaveta.addEventListener("toggle", function () {
        if (!gaveta.open) return;
        Array.prototype.forEach.call(gavetas, function (outra) {
          /* NUNCA FECHA O QUE TEM DADO DENTRO — é o motivo de este arquivo
             existir em vez do acordeão de fábrica do navegador. */
          if (outra !== gaveta && outra.open && !temAlgoEscrito(outra)) {
            outra.open = false;
          }
        });
      });
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-gavetas]"), ligar);
  });
})();
