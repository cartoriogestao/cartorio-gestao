/* O RELÓGIO DO AVISO DO WHATSAPP (29/10/2026) — um Worker, e só isso.
 *
 * O navegador segura o `setInterval` da aba que está escondida: depois de
 * alguns minutos em segundo plano, o Chrome só deixa a pergunta sair uma vez
 * por minuto, e o aviso de mensagem nova chegava atrasado. O relógio de um
 * Worker não sofre esse freio. Ele não pergunta nada ao servidor: só avisa a
 * página (`whatsapp_atalho.js`) de quanto em quanto tempo perguntar.
 */
"use strict";

var relogio = null;

self.onmessage = function (evento) {
  var ms = Number(evento.data) || 30000;
  if (relogio) {
    clearInterval(relogio);
  }
  relogio = setInterval(function () { self.postMessage("tique"); }, ms);
};
