/*
  NEGRITO NO TEOR, SEM DIGITAR ETIQUETA.

  «Negrito é fundamental para o layout da escritura, preciso de uma solução
   perfeita, é a atividade fim do cartório» — o oficial, em 28/08/2026.

  A ida e volta com o LibreOffice já preserva a ênfase. Faltava a outra metade:
  quem escreve o teor DENTRO do sistema não pode ter de digitar `<b>` à mão —
  campo que exige o operador saber marcação é campo que sai sem marcação.

  POR QUE ENVOLVER A SELEÇÃO, E NÃO UM EDITOR RICO
    Um editor de texto rico no navegador produz HTML que ninguém controla:
    `<span style="font-weight:700">`, `<div>` no meio do parágrafo, atributos de
    cor que vieram de um colar. O teor desta casa é `<p>` com `<b>`, `<i>` e
    `<u>` — as três marcas que o `.odt` sabe levar e trazer. Envolver a seleção
    produz exatamente essas três, e mais nada.

    É menos vistoso e é o que fecha o ciclo. Marca que o sistema cria e o
    LibreOffice não entende volta perdida.

  SEM ISTO A TELA CONTINUA FUNCIONANDO: o `<textarea>` é o mesmo, e quem
  souber escrever `<b>` continua podendo. O script só acrescenta os botões.
*/
(function () {
  "use strict";

  var MARCAS = [
    { abre: "<b>", fecha: "</b>", rotulo: "Negrito", atalho: "b", titulo: "Ctrl+B" },
    { abre: "<i>", fecha: "</i>", rotulo: "Itálico", atalho: "i", titulo: "Ctrl+I" },
    { abre: "<u>", fecha: "</u>", rotulo: "Sublinhado", atalho: "u", titulo: "Ctrl+U" },
    { abre: "<s style=\"color:#c62828\">", fecha: "</s>", rotulo: "Tachado vermelho",
      atalho: null, titulo: "Riscar em vermelho" },
    { abre: "<mark style=\"background:#fff59d\">", fecha: "</mark>", rotulo: "Destaque amarelo",
      atalho: null, titulo: "Marcar em amarelo" },
    { abre: "<mark style=\"background:#ffcdd2\">", fecha: "</mark>", rotulo: "Destaque vermelho",
      atalho: null, titulo: "Marcar em vermelho" }
  ];

  function envolver(campo, marca) {
    var inicio = campo.selectionStart;
    var fim = campo.selectionEnd;
    var texto = campo.value;
    var dentro = texto.slice(inicio, fim);
    var abre = marca.abre;
    var fecha = marca.fecha;

    // JÁ MARCADO, DESMARCA. Apertar negrito duas vezes na mesma seleção tem de
    // desfazer — senão o teor acumula `<b><b>`, que o LibreOffice até aceita e
    // que ninguém consegue mais limpar à mão.
    if (dentro.indexOf(abre) === 0 && dentro.lastIndexOf(fecha) === dentro.length - fecha.length) {
      var limpo = dentro.slice(abre.length, dentro.length - fecha.length);
      campo.value = texto.slice(0, inicio) + limpo + texto.slice(fim);
      campo.selectionStart = inicio;
      campo.selectionEnd = inicio + limpo.length;
    } else if (texto.slice(inicio - abre.length, inicio) === abre &&
               texto.slice(fim, fim + fecha.length) === fecha) {
      // A marca está POR FORA da seleção — foi assim que ela foi criada antes.
      campo.value = texto.slice(0, inicio - abre.length) + dentro +
                    texto.slice(fim + fecha.length);
      campo.selectionStart = inicio - abre.length;
      campo.selectionEnd = campo.selectionStart + dentro.length;
    } else {
      campo.value = texto.slice(0, inicio) + abre + dentro + fecha + texto.slice(fim);
      // O CURSOR FICA DENTRO DA MARCA quando não havia seleção: quem apertou
      // negrito antes de escrever quer escrever em negrito.
      campo.selectionStart = inicio + abre.length;
      campo.selectionEnd = campo.selectionStart + dentro.length;
    }
    campo.focus();
    campo.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function montarBarra(campo) {
    var barra = document.createElement("div");
    barra.className = "teor-marcas";
    MARCAS.forEach(function (m) {
      var botao = document.createElement("button");
      botao.type = "button";           // dentro de <form>: não submete
      botao.textContent = m.rotulo;
      botao.title = m.titulo;
      botao.className = "small";
      if (m.rotulo.indexOf("Tachado") === 0) botao.className += " marca-tachado";
      if (m.rotulo.indexOf("Destaque amarelo") === 0) botao.className += " marca-amarelo";
      if (m.rotulo.indexOf("Destaque vermelho") === 0) botao.className += " marca-vermelho";
      botao.addEventListener("click", function () { envolver(campo, m); });
      barra.appendChild(botao);
    });
    var dica = document.createElement("span");
    dica.className = "small muted";
    dica.textContent = "selecione o trecho e marque — a prévia ao lado mostra como fica";
    barra.appendChild(dica);
    campo.parentNode.insertBefore(barra, campo);

    campo.addEventListener("keydown", function (evento) {
      if (!evento.ctrlKey && !evento.metaKey) return;
      for (var i = 0; i < MARCAS.length; i++) {
        if (evento.key.toLowerCase() === MARCAS[i].atalho) {
          evento.preventDefault();
          envolver(campo, MARCAS[i]);
          return;
        }
      }
    });
  }

  // A PRÉVIA ACOMPANHA O QUE SE DIGITA, sem recarregar a tela.
  //
  //   Era a pergunta do oficial — «como isto vai ficar completo». Responder só
  //   depois de gravar faria a resposta chegar tarde demais para servir.
  //
  // E ELA MOSTRA O TEOR COMO A FICHA O DESENHA, e não de um jeito parecido.
  //
  //   O teor das Notas é HTML (`teor_formato='html'`) e sai com `innerHTML`.
  //   O do Registro de Imóveis é TEXTO: `teor_seguro` o escapa e o envolve num
  //   `<pre>`. Usar `innerHTML` nos dois faria a prévia do RI perder toda
  //   quebra de linha — e transformar um `<` digitado em etiqueta, mostrando
  //   uma coisa e gravando outra. `textContent` é o `escape` do lado do
  //   navegador, e o `white-space` do CSS é o `<pre>`.
  function ligarPrevia(campo, formato) {
    var previa = document.querySelector("[data-teor-previa]");
    if (!previa) return;
    var atualizar = (formato === "texto")
      ? function () { previa.textContent = campo.value; }
      : function () { previa.innerHTML = campo.value; };
    campo.addEventListener("input", atualizar);
  }

  document.addEventListener("DOMContentLoaded", function () {
    var campo = document.querySelector("textarea[data-teor]");
    if (!campo) return;
    // O FORMATO É DECLARADO PELA TELA, que é quem sabe qual é o dela. Sem
    // atributo vale `html`, que era o único caso quando isto nasceu — assim a
    // tela da escritura não muda de comportamento por causa desta linha.
    var formato = campo.getAttribute("data-teor") || "html";
    // A BARRA DE MARCAS SÓ SERVE AO TEOR HTML. No teor de texto ela escreveria
    // `<b>` literal dentro do ato — e o `<b>` sairia impresso na ficha, porque
    // ali a marca não é marca: é texto.
    if (formato !== "texto") montarBarra(campo);
    ligarPrevia(campo, formato);
  });
})();
