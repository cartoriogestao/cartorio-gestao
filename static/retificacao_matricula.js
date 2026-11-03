/*
  A MATRÍCULA DA RETIFICAÇÃO, ENQUANTO SE DIGITA — 03/11/2026.

  A tela nova não carrega mais as matrículas: são milhares, e a lista de 500
  deixava as de número baixo de fora. Este script pede um punhado ao servidor
  e mostra para escolher. Sem ele, o formulário segue inteiro: escreve-se o
  número (e o livro, se houver outro igual) e autua — quem resolve é a rota.
*/
(function () {
  "use strict";

  var ESPERA_MS = 250;

  function ligar() {
    var campo = document.querySelector("[data-busca-matricula]");
    if (!campo) { return; }
    var url = campo.getAttribute("data-url");
    var lista = document.getElementById(campo.getAttribute("aria-controls") || "");
    var oculto = campo.form && campo.form.querySelector('input[name="matricula_id"]');
    if (!url || !lista) { return; }

    var recado = document.querySelector("[data-busca-matricula-recado]");
    if (recado) { recado.hidden = false; }

    var relogio = null;
    var pedido = 0;

    function esconder() {
      lista.hidden = true;
      lista.replaceChildren();
    }

    function escolher(item) {
      campo.value = item.rotulo;
      if (oculto) { oculto.value = String(item.id); }
      esconder();
      campo.focus();
    }

    function desenhar(itens, haMais) {
      lista.replaceChildren();
      if (!itens.length) { esconder(); return; }
      itens.forEach(function (item) {
        var li = document.createElement("li");
        var botao = document.createElement("button");
        botao.type = "button";
        botao.textContent = item.rotulo;
        botao.addEventListener("click", function () { escolher(item); });
        li.appendChild(botao);
        lista.appendChild(li);
      });
      if (haMais) {
        var mais = document.createElement("li");
        mais.className = "small muted";
        mais.textContent = "Há mais. Continue o número.";
        lista.appendChild(mais);
      }
      lista.hidden = false;
    }

    function buscar() {
      var termo = campo.value.trim();
      var meu = ++pedido;
      if (!termo) { esconder(); return; }
      fetch(url + "?q=" + encodeURIComponent(termo), {
        headers: { "Accept": "application/json", "X-Requested-With": "fetch" }
      }).then(function (resposta) {
        if (!resposta.ok) { throw new Error(String(resposta.status)); }
        return resposta.json();
      }).then(function (corpo) {
        if (meu !== pedido) { return; }
        desenhar(corpo.itens || [], !!corpo.ha_mais);
      }).catch(function () {
        if (meu !== pedido) { return; }
      });
    }

    campo.addEventListener("input", function () {
      // O id escondido era de outra escolha. O que vale é o que está escrito.
      if (oculto) { oculto.value = ""; }
      if (relogio) { clearTimeout(relogio); }
      relogio = setTimeout(buscar, ESPERA_MS);
    });

    campo.addEventListener("keydown", function (evento) {
      if (evento.key === "Escape") { esconder(); }
    });

    document.addEventListener("click", function (evento) {
      if (evento.target === campo || lista.contains(evento.target)) { return; }
      esconder();
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ligar);
  } else {
    ligar();
  }
})();
