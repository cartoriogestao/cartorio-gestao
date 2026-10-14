/* FECHAR O AVISO DA TELA — relato #62, de 15/09/2026, construido em 17/09/2026.

   O aviso sai da frente de quem ja o leu e VOLTA quando a pagina for carregada
   de novo. Nao ha «excluir para sempre», e este arquivo nao guarda nada em
   lugar nenhum — quem desenha o aviso e o servidor, a cada carregamento. Por
   isso ele reaparece sozinho enquanto o fato que o acende existir, e some
   sozinho quando o fato passar — sem ninguem clicar em nada.

   ELE NAO DESENHA O BOTAO: ele ja vem no HTML, pela macro `_aviso.html`, e este
   script so escuta o clique — a mesma forma da janela da ajuda e da gaveta do
   agente, que tambem vem prontas no HTML.

   Sem JavaScript o aviso continua inteiro na tela, e a tela continua certa: o
   que se perde e o conforto, e nao a informacao. */
(function () {
  "use strict";

  /* Um ouvinte so, no documento, em vez de um por botao: os avisos entram e
     saem do HTML a cada tela, e amarrar o ouvinte a cada um deles seria
     amarrar a cada carregamento. */
  document.addEventListener("click", function (evento) {
    var expandir = evento.target.closest("[data-aviso-expand]");
    if (expandir) {
      var id = expandir.getAttribute("aria-controls");
      var detalhe = id ? document.getElementById(id) : null;
      if (!detalhe) return;
      var aberto = expandir.getAttribute("aria-expanded") === "true";
      aberto = !aberto;
      expandir.setAttribute("aria-expanded", aberto ? "true" : "false");
      expandir.textContent = aberto ? "Ocultar detalhes" : "Ver detalhes";
      detalhe.hidden = !aberto;
      return;
    }

    var botao = evento.target.closest("[data-aviso-fechar]");
    if (!botao) return;
    var aviso = botao.closest("[data-aviso]");
    /* O aviso e quem tem a marca; sem ela o clique nao esconde nada — e melhor
       nao esconder nada do que esconder o bloco errado. */
    if (!aviso) return;
    aviso.hidden = true;
  });
})();
