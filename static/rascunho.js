/* SALVAR O PREENCHIMENTO DE UMA TELA, PARA CONTINUAR DEPOIS.
 *
 * Relato #36, de 31/08/2026: «em todos os atos do cartório, durante o
 * preenchimento, é preciso ter um campo para salvar o progresso e continuar
 * depois».
 *
 * O QUE ESTE ARQUIVO RESOLVE
 *   O botão de rascunho é um formulário PEQUENO, e o que ele precisa guardar
 *   está no formulário GRANDE, o do ato. Um formulário não envia os campos do
 *   outro — então, ao clicar, este script copia os campos do grande para
 *   dentro do pequeno, como campos escondidos.
 *
 *   Fazer isso com `<form>` aninhado não existe em HTML; fazer com `form=`
 *   apontando para o outro formulário mandaria os campos para a rota do ATO,
 *   e não para a do rascunho.
 *
 * POR QUE ELE É UM ARQUIVO, E NÃO UM `<script>` EM CADA TELA
 *   Porque são dez telas de ato novo. Escrito em cada uma, ele viraria dez
 *   cópias divergindo no primeiro conserto — é a lição de `_cobrar.html` e da
 *   macro do alerta de fraude, e este projeto já a pagou mais de uma vez.
 *
 * SEM JAVASCRIPT O BOTÃO NÃO GUARDA NADA, e por isso a macro o esconde
 * quando o script não roda: botão que parece salvar e não salva é pior que
 * botão nenhum — o escrevente vai embora achando que guardou.
 */
(function () {
  "use strict";

  function primeiroNomePreenchido(dados, candidatos) {
    for (var i = 0; i < candidatos.length; i++) {
      var v = dados.get(candidatos[i]);
      if (v && String(v).trim()) return String(v).trim();
    }
    return "";
  }

  function ligar(botao) {
    var alvo = document.getElementById(botao.getAttribute("data-do-ato"));
    if (!alvo) return;

    /* O botão só aparece quando este arquivo rodou: ver o comentário acima. */
    botao.hidden = false;

    botao.addEventListener("submit", function () {
      /* Limpa a cópia anterior — o escrevente pode clicar duas vezes, e a
         segunda não pode mandar o valor da primeira junto. */
      Array.prototype.forEach.call(
        botao.querySelectorAll("[data-copiado]"),
        function (x) { x.remove(); });

      var dados = new FormData(alvo);
      var candidatos = (botao.getAttribute("data-nome-em") || "")
        .split(",").map(function (s) { return s.trim(); })
        .filter(Boolean);
      var nome = primeiroNomePreenchido(dados, candidatos);

      dados.forEach(function (valor, chave) {
        /* O TOKEN DO FORMULÁRIO GRANDE NÃO VAI JUNTO: o pequeno tem o dele, e
           dois com o mesmo nome fariam a rota ler o errado. */
        if (chave === "csrf_token") return;
        /* ARQUIVO NÃO CABE NO RASCUNHO. Um campo escondido só guardaria o texto
           «[object File]», e a tela reaberta pede o arquivo de novo. */
        if (typeof File !== "undefined" && valor instanceof File) return;
        /* O VAZIO VAI JUNTO — 31/10/2026. No campo repetido é a posição que diz
           de quem é cada valor: sem o documento vazio do primeiro devedor, o do
           segundo reabriria no primeiro. E no campo único é o vazio que impede a
           tela reaberta de trazer de volta o valor de fábrica que a pessoa tirou:
           quem deixou o motivo do protesto em branco não pode reabrir com
           «falta de pagamento» marcado. */
        var i = document.createElement("input");
        i.type = "hidden";
        i.name = chave;
        i.value = valor;
        i.setAttribute("data-copiado", "1");
        botao.appendChild(i);
      });

      var titulo = botao.querySelector("[data-titulo]");
      if (titulo) {
        var assunto = botao.getAttribute("data-assunto") || "Rascunho";
        titulo.value = nome ? (assunto + " — " + nome)
                            : (assunto + " sem nome ainda");
      }
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    Array.prototype.forEach.call(
      document.querySelectorAll("form[data-rascunho]"), ligar);
  });
})();
