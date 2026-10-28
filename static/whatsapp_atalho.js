/* O ATALHO DO WHATSAPP COM O ALERTA (27/10/2026) — `_whatsapp_atalho.html`.
 *
 * Pergunta a cada 30 s, só com a aba visível (e quando ela volta a ficar
 * visível), quantas conversas esperam resposta. A rota manda tudo pronto — o
 * número, o texto do alerta («99+») e o rótulo por extenso —, e aqui só se
 * copia, por `textContent` e `setAttribute`: a regra mora no servidor
 * (`wa_fila.nao_respondidas`).
 *
 * A pergunta não renova a sessão. Vencida a sessão, a resposta vem
 * redirecionada ao login: aí este arquivo PARA de perguntar, e só isso — quem
 * leva ao login é a própria tela, quando a pessoa clicar.
 */
(function () {
  "use strict";

  var INTERVALO_MS = 30000;
  var atalho = document.querySelector("[data-wa-atalho]");
  if (!atalho) {
    return;
  }
  var parado = false;
  var perguntando = false;
  var relogio = null;

  function parar() {
    parado = true;
    if (relogio) {
      window.clearInterval(relogio);
    }
  }

  function mostrar(dados) {
    atalho.setAttribute("aria-label", dados.rotulo);
    atalho.setAttribute("title", dados.rotulo);
    var alerta = atalho.querySelector("[data-wa-atalho-n]");
    if (dados.n > 0) {
      if (!alerta) {
        alerta = document.createElement("span");
        alerta.className = "wa-atalho-alerta";
        alerta.setAttribute("data-wa-atalho-n", "");
        atalho.appendChild(alerta);
      }
      alerta.textContent = dados.texto;
    } else if (alerta) {
      alerta.remove();
    }
  }

  function perguntar() {
    if (parado || perguntando || document.visibilityState !== "visible") {
      return;
    }
    perguntando = true;
    fetch(atalho.getAttribute("data-url"), {credentials: "same-origin",
                                            headers: {"Accept": "application/json"}})
      .then(function (r) {
        var tipo = r.headers.get("Content-Type") || "";
        if (r.redirected || (r.ok && tipo.indexOf("application/json") !== 0)) {
          parar();
          return null;
        }
        return r.ok ? r.json() : null;
      })
      .then(function (dados) {
        if (dados && !parado && typeof dados.n === "number") {
          mostrar(dados);
        }
      })
      .catch(function () { /* a próxima pergunta tenta de novo */ })
      .then(function () { perguntando = false; });
  }

  relogio = window.setInterval(perguntar, INTERVALO_MS);
  document.addEventListener("visibilitychange", function () {
    if (document.visibilityState === "visible") {
      perguntar();
    }
  });
})();
