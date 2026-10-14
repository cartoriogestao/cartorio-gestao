// A revisão antes da lavratura (06/10/2026). Manda o formulário, pergunta o
// andamento a cada 3 segundos e mostra o apontamento ao lado do texto. Quem
// trava ou libera a lavratura é o servidor; aqui só se mostra.
//
// 07/10/2026, pedido do oficial: «se atualiza a página perde a resposta». A
// resposta ficava gravada; agora a tela a busca ao abrir (data-ultima-url) e,
// se a leitura ainda corre, volta a acompanhar.
(function () {
  function esc(t) {
    var d = document.createElement("div");
    d.textContent = t == null ? "" : String(t);
    return d.innerHTML;
  }

  function quando(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})[T ](\d{2}):(\d{2})/.exec(iso || "");
    return m ? m[3] + "/" + m[2] + " às " + m[4] + ":" + m[5] : "";
  }

  function mostrar(caixa, r, prefixo) {
    var estado = caixa.querySelector("[data-revisao-estado]");
    var saida = caixa.querySelector("[data-revisao-resultado]");
    var justificar = caixa.querySelector("[data-revisao-justificar]");
    prefixo = prefixo || "";
    if (r.situacao === "PENDENTE" || r.situacao === "LENDO") {
      estado.textContent = prefixo + " lendo… (com anexos, pode levar alguns minutos)";
      return false;
    }
    if (r.situacao === "ERRO") {
      estado.textContent = prefixo + " a IA não respondeu — pode lavrar; o ato entra na revisão diária.";
      return true;
    }
    var achados = r.achados || [];
    // HOTFIX-2026-10-08-07: graves PENDENTES (os supridos não contam).
    var pendentes = (typeof r.graves_pendentes === "number") ? r.graves_pendentes : (r.graves || 0);
    estado.textContent = prefixo + (achados.length
      ? " " + achados.length + " apontamento(s), " + (r.graves || 0) + " grave(s)" +
        ((r.graves || 0) > pendentes ? " (" + pendentes + " pendente(s))" : "") + "."
      : " nada apontado.");
    var html = "";
    if (r.texto_mudou) {
      html += "<p class='small' style='color:#b00'><strong>O texto mudou depois desta revisão:</strong> " +
        "ela vale para o texto antigo — clique em «Revisar com IA» de novo.</p>";
    }
    html += r.parecer ? "<p><em>" + esc(r.parecer) + "</em></p>" : "";
    // OS ANEXOS (07/10/2026): o que a revisão leu, o que a triagem deixou de
    // fora e por quê, e o aviso das 40 páginas. Quem lavra precisa saber o que
    // NÃO foi conferido, para conferir à mão.
    if (r.aviso_anexos) {
      html += "<p class='small' style='color:#a35a00'><strong>Anexos:</strong> " +
        esc(r.aviso_anexos) + "</p>";
    }
    var anexos = r.anexos || [];
    if (anexos.length) {
      var lidos = anexos.filter(function (x) { return x.lidas > 0; }).length;
      html += "<details class='small'><summary>Anexos: " + lidos + " lido(s) de " +
        anexos.length + "</summary><ul>";
      anexos.forEach(function (x) {
        var como = x.lidas > 0
          ? "lido (" + x.lidas + " de " + x.paginas + " pág.)" + (x.reaproveitado ? ", leitura já guardada" : "")
          : (x.importante === false ? "deixado de fora" : "não lido");
        html += "<li><strong>" + esc(x.tipo || "documento") + "</strong> — " + esc(x.nome) +
          ": " + como + (x.motivo ? " — " + esc(x.motivo) : "") + "</li>";
      });
      html += "</ul></details>";
    }
    // HOTFIX-2026-10-08-07: cada apontamento pode ser marcado «já verificado/
    // suprido» (GRAVE só o gerente, com observação); atenção NÃO bloqueia.
    var podeGrave = caixa.dataset.podeSuprirGrave === "1";
    var marcavel = false;
    if (achados.length) {
      html += "<ul>";
      achados.forEach(function (a, i) {
        var grave = a.gravidade === "GRAVE";
        html += "<li style='margin-bottom:6px'><strong>" + (grave ? "GRAVE" : "atenção") +
          ":</strong> " + esc(a.o_que) +
          (a.trecho ? "<br><small>«" + esc(a.trecho) + "»</small>" : "") +
          (a.por_que ? "<br><small>" + esc(a.por_que) + "</small>" : "");
        if (a.suprido) {
          var s = a.suprido;
          html += "<br><small style='color:#1b6e2a'><strong>✔ Já verificado/suprido</strong>" +
            (s.por ? " por " + esc(s.por) : "") + (s.em ? " em " + quando(s.em) : "") +
            (s.herdado ? " (marcado numa revisão anterior deste ato)" : "") +
            (s.obs ? " — " + esc(s.obs) : "") + "</small>";
        } else if (r.id && (!grave || podeGrave)) {
          marcavel = true;
          html += "<br><label class='small' style='display:inline'><input type='checkbox' data-suprir-indice='" + i +
            "'> Já verificado/suprido</label> <input type='text' class='small' data-suprir-obs='" + i +
            "' style='width:55%' placeholder='" + (grave ? "como foi suprido (obrigatório, mín. 10 letras)"
                                                          : "observação (opcional)") + "'>";
        } else if (grave) {
          html += "<br><small class='muted'>Só o gerente ou o administrador marca GRAVE como suprido.</small>";
        }
        html += "</li>";
      });
      html += "</ul>";
      if (marcavel) {
        html += "<button type='button' class='button' data-suprir>Marcar selecionados como supridos</button>" +
          " <span class='small' data-suprir-estado></span>";
      }
    }
    if (!r.texto_mudou) {
      if (pendentes > 0) {
        html += "<p class='small' style='color:#b00'><strong>" + pendentes +
          " apontamento(s) GRAVE(s) pendente(s).</strong> Marque como suprido (gerente) ou escreva abaixo por que lavrar assim mesmo.</p>";
      } else {
        html += "<div class='notice ok small' style='margin-top:6px'><strong>Nada impede a lavratura.</strong> " +
          (achados.length ? "Os avisos de «atenção» não bloqueiam. " : "") +
          "<button type='button' class='button' data-prosseguir>Prosseguir mesmo assim</button></div>";
      }
    }
    saida.innerHTML = html;
    caixa.dataset.revisaoId = r.id ? String(r.id) : "";
    justificar.hidden = !(pendentes > 0) || !!r.texto_mudou;
    return true;
  }

  function acompanhar(caixa, id, botao, prefixo) {
    var url = caixa.dataset.andamentoUrl.replace(/0$/, String(id));
    var perguntar = function () {
      fetch(url, { credentials: "same-origin" })
        .then(function (x) { return x.json(); })
        .then(function (a) {
          if (mostrar(caixa, a, prefixo)) { if (botao) botao.disabled = false; }
          else { setTimeout(perguntar, 3000); }
        })
        .catch(function () { setTimeout(perguntar, 5000); });
    };
    perguntar();
  }

  function trazerAUltima(caixa) {
    var url = caixa.dataset.ultimaUrl;
    if (!url) return;
    fetch(url, { credentials: "same-origin" })
      .then(function (x) { return x.json(); })
      .then(function (r) {
        if (!r || !r.id) return;
        var prefixo = " Última revisão (" + quando(r.pedido_em) +
          (r.pedido_por ? ", por " + r.pedido_por : "") + "):";
        if (!mostrar(caixa, r, prefixo)) {
          var botao = caixa.querySelector("[data-revisar]");
          if (botao) botao.disabled = true;
          acompanhar(caixa, r.id, botao, prefixo);
        }
      })
      .catch(function () { /* sem a última, a tela segue como antes */ });
  }

  function aoAbrir() {
    document.querySelectorAll(".revisao-previa").forEach(trazerAUltima);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", aoAbrir);
  } else {
    aoAbrir();
  }

  document.addEventListener("click", function (ev) {
    var botao = ev.target.closest("[data-revisar]");
    if (!botao) return;
    var caixa = botao.closest(".revisao-previa");
    var form = botao.closest("form");
    var estado = caixa.querySelector("[data-revisao-estado]");
    botao.disabled = true;
    estado.textContent = " enviando…";
    fetch(caixa.dataset.revisaoUrl, { method: "POST", body: new FormData(form),
                                      credentials: "same-origin" })
      .then(function (resp) { return resp.json(); })
      .then(function (r) {
        if (r.erro) { estado.textContent = " " + r.erro; botao.disabled = false; return; }
        if (r.desligada) { estado.textContent = " a revisão está desligada nesta instalação."; return; }
        acompanhar(caixa, r.id, botao, "");
      })
      .catch(function () { estado.textContent = " não consegui falar com o servidor."; botao.disabled = false; });
  });
  // ---- HOTFIX-2026-10-08-07: «já verificado/suprido», «Prosseguir mesmo assim»
  // e o aviso de texto mudado depois da revisão.
  document.addEventListener("click", function (ev) {
    var botao = ev.target.closest("[data-suprir]");
    if (botao) {
      var caixa = botao.closest(".revisao-previa");
      var form = botao.closest("form");
      var estado = caixa.querySelector("[data-suprir-estado]");
      var fd = new FormData();
      var tok = form && form.querySelector("input[name=csrf_token]");
      if (tok) fd.append("csrf_token", tok.value);
      var n = 0;
      caixa.querySelectorAll("[data-suprir-indice]").forEach(function (cb) {
        if (!cb.checked) return;
        var i = cb.getAttribute("data-suprir-indice");
        var obs = caixa.querySelector("[data-suprir-obs='" + i + "']");
        fd.append("indice", i);
        fd.append("obs_" + i, obs ? obs.value : "");
        n++;
      });
      if (!n) { if (estado) estado.textContent = " marque ao menos um apontamento."; return; }
      botao.disabled = true;
      fetch(caixa.dataset.suprirUrl.replace("999999999", caixa.dataset.revisaoId),
            { method: "POST", body: fd, credentials: "same-origin" })
        .then(function (x) { return x.json(); })
        .then(function (r) {
          if (r.erro) { if (estado) estado.textContent = " " + r.erro; botao.disabled = false; return; }
          mostrar(caixa, r, " revisão:");
        })
        .catch(function () { if (estado) estado.textContent = " não consegui falar com o servidor."; botao.disabled = false; });
      return;
    }
    var seguir = ev.target.closest("[data-prosseguir]");
    if (seguir) {
      var f = seguir.closest("form");
      var alvo = null;
      if (f) {
        f.querySelectorAll("button.primary").forEach(function (b) {
          if (!b.hasAttribute("formaction")) alvo = b;
        });
      }
      if (alvo) {
        alvo.scrollIntoView({ behavior: "smooth", block: "center" });
        alvo.focus();
        alvo.style.outline = "3px solid #1b6e2a";
        setTimeout(function () { alvo.style.outline = ""; }, 4000);
      }
      return;
    }
    var revisar = ev.target.closest("[data-revisar]");
    if (revisar) {
      var velho = revisar.closest(".revisao-previa").querySelector("[data-texto-mudou]");
      if (velho) velho.remove();
    }
  });

  document.addEventListener("input", function (ev) {
    var t = ev.target;
    if (!t || t.name !== "teor") return;
    var form = t.closest("form");
    var caixa = form && form.querySelector(".revisao-previa");
    if (!caixa || !caixa.dataset.revisaoId || caixa.querySelector("[data-texto-mudou]")) return;
    var aviso = document.createElement("p");
    aviso.className = "small";
    aviso.style.color = "#b00";
    aviso.setAttribute("data-texto-mudou", "");
    aviso.innerHTML = "<strong>O texto mudou depois da revisão.</strong> Clique em «Revisar com IA» de novo antes de lavrar" +
      (caixa.dataset.podeSuprirGrave === "1"
        ? " — ou, se a mudança foi pequena, use «Lavrar com a revisão anterior», logo abaixo." : ".");
    caixa.insertBefore(aviso, caixa.querySelector("[data-revisao-resultado]"));
  });
})();
