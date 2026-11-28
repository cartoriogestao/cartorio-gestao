/* A COMUNICAÇÃO DA CASA (T028, 28/11/2026) — o script de toda tela e o do mensageiro.
 *
 * NA MOLDURA (toda tela): o botão da coluna da direita abre e fecha a gaveta (Alt+M,
 * Esc fecha); a cada 30 s pergunta `estado.json` e redesenha o contador, a faixa e o
 * cartão dos avisos sem recarregar a tela; diz ao servidor quais avisos mostrou (o
 * «vi», que GET não grava); e mostra um aviso discreto de mensagem nova — sem som.
 *
 * NO MENSAGEIRO (gaveta e tela cheia): as mensagens novas chegam a cada 4 s como HTML
 * que o servidor já escapou (o script nunca monta texto de mensagem); Enter envia e
 * Shift+Enter quebra a linha; o rascunho fica por conversa; responder, editar e apagar;
 * o «li até aqui» vai ao servidor quando a conversa está à vista.
 *
 * NADA DISTO É NECESSÁRIO PARA FUNCIONAR: sem script, os botões são formulários e os
 * links são links. O script só tira a recarga do caminho.
 */
(function () {
  "use strict";

  var ORIGEM = window.location.origin;

  function csrf() {
    var i = document.querySelector('input[name="csrf_token"]');
    return i ? i.value : "";
  }

  function postar(url, dados) {
    var fd = dados instanceof FormData ? dados : new FormData();
    if (!(dados instanceof FormData) && dados) {
      Object.keys(dados).forEach(function (k) {
        var v = dados[k];
        if (Array.isArray(v)) { v.forEach(function (x) { fd.append(k, x); }); }
        else { fd.append(k, v); }
      });
    }
    if (!fd.has("csrf_token")) { fd.append("csrf_token", csrf()); }
    return fetch(url, {
      method: "POST", body: fd, credentials: "same-origin",
      headers: { "X-Requested-With": "fetch", "X-CSRF-Token": csrf() }
    }).then(function (r) {
      return r.json().catch(function () {
        return { ok: false, erro: "O servidor não respondeu como esperado. Tente de novo." };
      }).then(function (j) { j.status = r.status; return j; });
    });
  }

  function buscar(url) {
    return fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) { if (!r.ok) { throw new Error(String(r.status)); } return r.json(); });
  }

  function lerGuardado(chave) {
    try { return window.localStorage.getItem(chave); } catch (e) { return null; }
  }
  function guardar(chave, valor) {
    try {
      if (valor) { window.localStorage.setItem(chave, valor); }
      else { window.localStorage.removeItem(chave); }
    } catch (e) { /* navegação privada: segue sem rascunho */ }
  }
  function sessao(chave, valor) {
    try {
      if (valor === undefined) { return window.sessionStorage.getItem(chave); }
      if (valor === null) { window.sessionStorage.removeItem(chave); }
      else { window.sessionStorage.setItem(chave, valor); }
    } catch (e) { return null; }
    return null;
  }

  function semAcento(t) {
    return String(t || "").toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
  }

  var EMBUTIDO = document.body && document.body.classList.contains("cm-corpo-embutido");

  function avisarMoldura(msg) {
    if (EMBUTIDO && window.parent && window.parent !== window) {
      try { window.parent.postMessage(msg, ORIGEM); } catch (e) { /* nada */ }
    }
  }

  /* =================================================================== A MOLDURA */

  function ligarMoldura() {
    var caixa = document.querySelector("[data-cm-atalho-caixa]");
    var botao = caixa && caixa.querySelector("[data-cm-abrir]");
    var gaveta = caixa && caixa.querySelector("[data-cm-gaveta]");
    var quadro = caixa && caixa.querySelector("[data-cm-quadro]");
    var conta = caixa && caixa.querySelector("[data-cm-conta]");
    var tituloBase = document.title.replace(/^\(\d+\)\s+/, "");
    var naComunicacao = /^\/comunicacao(\/|$)/.test(window.location.pathname);
    var versao = null;
    var vistosEnviados = {};

    function abrir(url) {
      if (!gaveta) { if (url) { window.location.href = url.replace("/comunicacao/painel", "/comunicacao"); } return; }
      gaveta.hidden = false;
      botao.setAttribute("aria-expanded", "true");
      document.documentElement.classList.add("cm-gaveta-aberta");
      if (url) { quadro.src = url; }
      else if (!quadro.getAttribute("src")) { quadro.src = quadro.getAttribute("data-src"); }
      try { quadro.focus(); } catch (e) { /* nada */ }
    }

    function fechar() {
      if (!gaveta || gaveta.hidden) { return; }
      gaveta.hidden = true;
      botao.setAttribute("aria-expanded", "false");
      document.documentElement.classList.remove("cm-gaveta-aberta");
      botao.focus();
    }

    function paraPainel(href) {
      try {
        var u = new URL(href, ORIGEM);
        if (u.pathname === "/comunicacao") { u.pathname = "/comunicacao/painel"; }
        return u.pathname + u.search + u.hash;
      } catch (e) { return null; }
    }

    if (botao) {
      botao.addEventListener("click", function () {
        if (gaveta.hidden) { abrir(); } else { fechar(); }
      });
      caixa.querySelector("[data-cm-fechar]").addEventListener("click", fechar);
    }

    document.addEventListener("keydown", function (e) {
      if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyM") {
        e.preventDefault();
        if (gaveta && gaveta.hidden) { abrir(); } else { fechar(); }
      } else if (e.key === "Escape" && gaveta && !gaveta.hidden) {
        fechar();
      }
    });

    window.addEventListener("message", function (e) {
      if (e.origin !== ORIGEM || !e.data || typeof e.data !== "object") { return; }
      if (e.data.cm === "atualizar") { atualizar(); }
      else if (e.data.cm === "fechar") { fechar(); }
    });

    /* A insistência: os botões vão por trás, e a tela não recarrega. */
    document.addEventListener("submit", function (e) {
      var f = e.target;
      if (!f.matches || !f.matches("[data-cm-insistencia] form[data-cm-acao]")) { return; }
      e.preventDefault();
      var b = f.querySelector("button");
      if (b) { b.disabled = true; }
      postar(f.action, new FormData(f)).then(function (j) {
        if (!j.ok && j.erro) { window.alert(j.erro); }
        versao = null;
        atualizar();
        if (quadro && quadro.getAttribute("src")) {
          try { quadro.contentWindow.location.reload(); } catch (err) { /* nada */ }
        }
      }).catch(function () { if (b) { b.disabled = false; } });
    });

    document.addEventListener("click", function (e) {
      var a = e.target.closest && e.target.closest("[data-cm-ver-aviso]");
      if (!a || !gaveta || e.ctrlKey || e.metaKey || e.shiftKey) { return; }
      var destino = paraPainel(a.getAttribute("href"));
      if (!destino) { return; }
      e.preventDefault();
      abrir(destino);
    });

    function idsNaTela() {
      return Array.prototype.map.call(
        document.querySelectorAll("[data-cm-insistencia] [data-cm-aviso]"),
        function (el) { return el.getAttribute("data-cm-aviso") + ":" + el.getAttribute("data-cm-grau"); });
    }

    function contarVisto() {
      var novos = idsNaTela().filter(function (k) { return !vistosEnviados[k]; });
      if (!novos.length) { return; }
      novos.forEach(function (k) { vistosEnviados[k] = true; });
      postar("/comunicacao/avisos/visto", { ids: novos.map(function (k) { return k.split(":")[0]; }) })
        .catch(function () { novos.forEach(function (k) { delete vistosEnviados[k]; }); });
    }

    function redesenhar(html) {
      var atual = document.querySelector("[data-cm-insistencia]");
      if (!atual) { return; }
      var molde = document.createElement("div");
      molde.innerHTML = html;
      var novo = molde.querySelector("[data-cm-insistencia]");
      if (!novo) { return; }
      var antes = {};
      atual.querySelectorAll("[data-cm-aviso]").forEach(function (el) { antes[el.getAttribute("data-cm-aviso")] = 1; });
      var anuncio = atual.querySelector("[data-cm-anuncio]");
      Array.prototype.slice.call(atual.childNodes).forEach(function (n) { if (n !== anuncio) { atual.removeChild(n); } });
      Array.prototype.slice.call(novo.childNodes).forEach(function (n) {
        if (!(n.matches && n.matches("[data-cm-anuncio]"))) { atual.appendChild(n); }
      });
      var chegou = Array.prototype.filter.call(atual.querySelectorAll("[data-cm-aviso]"),
        function (el) { return !antes[el.getAttribute("data-cm-aviso")]; });
      if (chegou.length && anuncio) {
        var t = chegou[0].querySelector("h2, strong");
        anuncio.textContent = "Aviso da gerência: " + (t ? t.textContent : "") + ".";
      }
    }

    function mostrarContagem(j) {
      var n = (j.nao_lidas || 0) + (j.esperando || 0);
      if (conta) {
        conta.textContent = String(n);
        conta.hidden = !n;
        conta.setAttribute("aria-label", (j.esperando || 0) + " aviso(s) esperando você e " +
          (j.nao_lidas || 0) + " mensagem(ns) não lida(s)");
      }
      if (botao) {
        botao.classList.toggle("cm-com-aviso", !!j.esperando);
        botao.classList.toggle("cm-com-mensagem", !j.esperando && !!j.nao_lidas);
      }
      document.title = (n ? "(" + n + ") " : "") + tituloBase;
    }

    var toast = null;
    function avisoDeMensagem(u) {
      if (!u || naComunicacao || (gaveta && !gaveta.hidden)) { return; }
      var visto = parseInt(sessao("cm-toast") || "0", 10);
      if (u.id <= visto) { return; }
      sessao("cm-toast", String(u.id));
      if (!toast) {
        toast = document.createElement("div");
        toast.className = "cm-toast";
        toast.setAttribute("role", "status");
        toast.hidden = true;
        document.body.appendChild(toast);
        toast.addEventListener("click", function () {
          toast.hidden = true;
          abrir(toast.getAttribute("data-url"));
        });
      }
      toast.textContent = "";
      var b = document.createElement("b");
      b.textContent = u.autor + (u.onde ? " · " + u.onde : "");
      var s = document.createElement("span");
      s.textContent = u.texto;
      toast.appendChild(b);
      toast.appendChild(s);
      toast.setAttribute("data-url", u.url);
      toast.hidden = false;
      window.clearTimeout(toast._fim);
      toast._fim = window.setTimeout(function () { toast.hidden = true; }, 8000);
    }

    var ocupado = false;
    function atualizar() {
      if (ocupado) { return; }
      ocupado = true;
      buscar("/comunicacao/estado.json").then(function (j) {
        mostrarContagem(j);
        if (j.versao !== versao) { redesenhar(j.html); versao = j.versao; posicionar(); }
        contarVisto();
        avisoDeMensagem(j.ultima);
      }).catch(function () { /* sem rede: tenta na próxima */ })
        .then(function () { ocupado = false; });
    }

    /* O cartão fica logo abaixo da barra de busca: as barras vermelhas da casa (FERJ/FERC
       e as outras que não se fecham) continuam inteiras à vista, com os campos delas. */
    var quadroPedido = false;
    function posicionar() {
      quadroPedido = false;
      /* Layout novo: logo abaixo da barra de busca. Antigo: logo abaixo das barras, à
         altura do título da tela (a faixa da direita do título costuma estar vazia). */
      var busca = document.querySelector(".cg-topo");
      var titulo = document.querySelector(".main > .topbar");
      var y = busca ? busca.getBoundingClientRect().bottom + 8
        : (titulo ? titulo.getBoundingClientRect().top + 8 : 12);
      y = Math.round(y);
      document.documentElement.style.setProperty("--cm-topo", Math.max(8, y) + "px");
    }
    function pedirPosicao() {
      if (!quadroPedido) { quadroPedido = true; window.requestAnimationFrame(posicionar); }
    }
    window.addEventListener("resize", pedirPosicao);
    window.addEventListener("scroll", pedirPosicao, { passive: true });

    if (!caixa && !document.querySelector("[data-cm-insistencia]")) { return; }
    posicionar();
    contarVisto();
    window.setInterval(function () { if (!document.hidden) { atualizar(); } }, 30000);
    document.addEventListener("visibilitychange", function () { if (!document.hidden) { atualizar(); } });
    /* A gaveta NÃO reabre sozinha na tela seguinte: ela ocupa a lateral, e quem
       abre é a pessoa (o clique, o Alt+M, o «Ler» da faixa ou o aviso de mensagem). */
  }

  /* =================================================================== O MENSAGEIRO */

  function ligarMensageiro(app) {
    var lista = app.querySelector("[data-cm-mensagens]");
    var form = app.querySelector("[data-cm-compor]");
    var conversa = lista && lista.getAttribute("data-conversa");
    var ultimo = lista ? parseInt(lista.getAttribute("data-ultimo") || "0", 10) : 0;
    var primeiro = lista ? parseInt(lista.getAttribute("data-primeiro") || "0", 10) : 0;
    var desde = app.getAttribute("data-agora") || "";
    var lidaEnviada = 0;

    function visivel() {
      if (document.hidden) { return false; }
      if (EMBUTIDO && window.frameElement) {
        return window.frameElement.offsetParent !== null || window.frameElement.getClientRects().length > 0;
      }
      return true;
    }

    function pertoDoFim() {
      return lista.scrollHeight - lista.scrollTop - lista.clientHeight < 80;
    }
    function irAoFim() { lista.scrollTop = lista.scrollHeight; }

    function marcarLida() {
      if (!conversa || !visivel() || ultimo <= lidaEnviada || !pertoDoFim()) { return; }
      var ate = ultimo;
      lidaEnviada = ate;
      postar(lista.getAttribute("data-url-lida"), { ate: ate }).then(function () {
        avisarMoldura({ cm: "atualizar" });
      }).catch(function () { lidaEnviada = 0; });
    }

    function tirarDiaRepetido(fragmento) {
      var dias = lista.querySelectorAll(".cm-dia");
      var ultimoDia = dias.length ? dias[dias.length - 1].getAttribute("data-dia") : null;
      var primeiroDia = fragmento.querySelector(".cm-dia");
      if (primeiroDia && primeiroDia.getAttribute("data-dia") === ultimoDia) { primeiroDia.remove(); }
    }

    function juntar(html) {
      var molde = document.createElement("template");
      molde.innerHTML = html;
      var frag = molde.content;
      tirarDiaRepetido(frag);
      frag.querySelectorAll("[data-cm-msg]").forEach(function (li) {
        var id = li.getAttribute("data-cm-msg");
        var ja = document.getElementById("cm-m-" + id);
        if (ja) { ja.remove(); }
      });
      var vazio = lista.querySelector(".cm-vazio");
      if (vazio) { vazio.remove(); }
      lista.appendChild(frag);
    }

    function trocar(id, html) {
      var velho = document.getElementById("cm-m-" + id);
      if (!velho) { return; }
      var molde = document.createElement("template");
      molde.innerHTML = html;
      var novo = molde.content.querySelector("[data-cm-msg]");
      if (novo) { velho.replaceWith(novo); }
    }

    var perguntando = false;
    function novas() {
      if (!conversa || perguntando) { return Promise.resolve(); }
      perguntando = true;
      var url = lista.getAttribute("data-url-novas") + "?depois=" + ultimo + "&desde=" + encodeURIComponent(desde);
      return buscar(url).then(function (j) {
        var estavaNoFim = pertoDoFim();
        if (j.html) { juntar(j.html); }
        Object.keys(j.alteradas || {}).forEach(function (id) { trocar(id, j.alteradas[id]); });
        var rec = app.querySelector("[data-cm-recibo]");
        if (rec && typeof j.recibo === "string") { rec.innerHTML = j.recibo; }
        if (j.ultimo_id > ultimo) {
          ultimo = j.ultimo_id;
          if (estavaNoFim) { irAoFim(); }
        }
        desde = j.agora || desde;
        marcarLida();
      }).catch(function () { /* tenta na próxima */ })
        .then(function () { perguntando = false; });
    }

    if (lista && conversa) {
      var alvo = window.location.hash && document.getElementById(window.location.hash.slice(1));
      var linhaNova = lista.querySelector("[data-cm-linha-nova]");
      if (alvo) { alvo.classList.add("cm-alvo"); alvo.scrollIntoView({ block: "center" }); }
      else if (linhaNova) { linhaNova.scrollIntoView({ block: "start" }); }
      else { irAoFim(); }
      lista.addEventListener("scroll", function () { if (pertoDoFim()) { marcarLida(); } });
      window.addEventListener("focus", marcarLida);
      document.addEventListener("visibilitychange", function () { if (!document.hidden) { novas(); } });
      window.setInterval(function () { if (visivel()) { novas(); } }, 4000);
      window.setTimeout(marcarLida, 600);

      var maisAntigas = lista.querySelector("[data-cm-anteriores]");
      if (maisAntigas) {
        maisAntigas.addEventListener("click", function () {
          maisAntigas.disabled = true;
          buscar(lista.getAttribute("data-url-anteriores") + "?antes=" + primeiro).then(function (j) {
            var altura = lista.scrollHeight;
            var molde = document.createElement("template");
            molde.innerHTML = j.html;
            var primeiroDia = lista.querySelector(".cm-dia");
            var dias = molde.content.querySelectorAll(".cm-dia");
            if (primeiroDia && dias.length &&
                dias[dias.length - 1].getAttribute("data-dia") === primeiroDia.getAttribute("data-dia")) {
              primeiroDia.remove();
            }
            maisAntigas.parentNode.after(molde.content);
            lista.scrollTop += lista.scrollHeight - altura;
            primeiro = j.primeiro_id || primeiro;
            if (!j.tem_mais) { maisAntigas.parentNode.remove(); } else { maisAntigas.disabled = false; }
          }).catch(function () { maisAntigas.disabled = false; });
        });
      }
    }

    /* ---- responder, editar, apagar */
    var editando = null;
    var campo = form && form.querySelector("[data-cm-texto]");
    var citacao = form && form.querySelector("[data-cm-citacao]");
    var editandoAviso = form && form.querySelector("[data-cm-editando]");
    var respostaId = form && form.querySelector("[data-cm-resposta-id]");

    function tirarCitacao() {
      if (!form) { return; }
      respostaId.value = "";
      citacao.hidden = true;
    }
    function pararEdicao() {
      editando = null;
      if (editandoAviso) { editandoAviso.hidden = true; }
    }

    app.addEventListener("click", function (e) {
      var r = e.target.closest("[data-cm-responder]");
      if (r && form) {
        var li = r.closest("[data-cm-msg]");
        pararEdicao();
        respostaId.value = li.getAttribute("data-cm-msg");
        citacao.querySelector("[data-cm-citacao-texto]").textContent =
          "Respondendo a " + r.getAttribute("data-autor-nome") + ": " + r.getAttribute("data-trecho");
        citacao.hidden = false;
        campo.focus();
        return;
      }
      var ed = e.target.closest("[data-cm-editar]");
      if (ed && form) {
        var li2 = ed.closest("[data-cm-msg]");
        var orig = li2.querySelector("[data-cm-texto-original]");
        tirarCitacao();
        editando = ed.getAttribute("data-url");
        campo.value = orig ? orig.getAttribute("data-cm-texto-original") : "";
        editandoAviso.hidden = false;
        campo.focus();
        crescer();
        return;
      }
      if (e.target.closest("[data-cm-citacao-tirar]")) { tirarCitacao(); return; }
      if (e.target.closest("[data-cm-editar-cancelar]")) { pararEdicao(); campo.value = ""; crescer(); return; }
      if (e.target.closest("[data-cm-link-da-tela]") && campo) {
        try {
          var pai = window.parent.document;
          var texto = (pai.title || "").replace(/^\(\d+\)\s+/, "") + " — " + window.parent.location.href;
          campo.value = (campo.value ? campo.value.replace(/\s*$/, "") + "\n" : "") + texto;
          campo.focus();
          crescer();
          guardarRascunho();
        } catch (err) { /* outra origem: não acontece na casa */ }
      }
    });

    app.addEventListener("submit", function (e) {
      var f = e.target;
      if (f.matches("[data-cm-apagar]")) {
        e.preventDefault();
        if (!window.confirm("Apagar esta mensagem para todos?")) { return; }
        postar(f.action, new FormData(f)).then(function (j) {
          if (!j.ok && j.erro) { window.alert(j.erro); }
          novas();
        });
        return;
      }
      if (f.matches("[data-cm-acao]")) {
        e.preventDefault();
        var b = f.querySelector("button");
        if (b) { b.disabled = true; }
        postar(f.action, new FormData(f)).then(function (j) {
          if (!j.ok && j.erro) { window.alert(j.erro); }
          avisarMoldura({ cm: "atualizar" });
          window.location.reload();
        }).catch(function () { if (b) { b.disabled = false; } });
      }
    });

    /* avisos abertos na gaveta contam como vistos */
    app.querySelectorAll("[data-cm-aviso-detalhe]").forEach(function (d) {
      function abriu() {
        if (!d.open || d._contou || !d.getAttribute("data-url-abri")) { return; }
        d._contou = true;
        postar(d.getAttribute("data-url-abri"), {}).then(function () { avisarMoldura({ cm: "atualizar" }); });
      }
      d.addEventListener("toggle", abriu);
      abriu();
    });

    /* ---- o compositor */
    if (!form) { return; }
    var chave = "cm-rascunho-" + form.getAttribute("data-rascunho");
    var enviar = form.querySelector("[data-cm-enviar]");
    var erro = form.querySelector("[data-cm-erro]");
    var arquivo = form.querySelector("[data-cm-arquivo]");
    var anexoNome = form.querySelector("[data-cm-anexo-nome]");
    var token = form.querySelector("[data-cm-token]");

    function crescer() {
      campo.style.height = "auto";
      campo.style.height = Math.min(campo.scrollHeight + 2, 140) + "px";
    }
    var tempoRascunho = null;
    function guardarRascunho() {
      window.clearTimeout(tempoRascunho);
      tempoRascunho = window.setTimeout(function () {
        if (!editando) { guardar(chave, campo.value.trim() ? campo.value : ""); }
      }, 300);
    }
    function mostrarErro(texto) {
      erro.textContent = texto || "";
      erro.hidden = !texto;
    }

    var rascunho = lerGuardado(chave);
    if (rascunho && !campo.value) { campo.value = rascunho; }
    crescer();
    campo.addEventListener("input", function () { crescer(); guardarRascunho(); mostrarErro(""); });
    campo.addEventListener("keydown", function (e) {
      if (e.key === "Enter" && !e.shiftKey && !e.isComposing && e.keyCode !== 229) {
        e.preventDefault();
        if (typeof form.requestSubmit === "function") { form.requestSubmit(); }
        else { form.dispatchEvent(new Event("submit", { cancelable: true, bubbles: true })); }
      } else if (e.key === "Escape") {
        e.stopPropagation();
        if (editando) { pararEdicao(); campo.value = ""; crescer(); }
        else if (!citacao.hidden) { tirarCitacao(); }
        else { avisarMoldura({ cm: "fechar" }); }
      }
    });
    arquivo.addEventListener("change", function () {
      var f = arquivo.files && arquivo.files[0];
      if (!f) { anexoNome.hidden = true; return; }
      if (f.size > 10 * 1024 * 1024) {
        arquivo.value = "";
        anexoNome.hidden = true;
        mostrarErro("O arquivo passou de 10 MB.");
        return;
      }
      anexoNome.textContent = "";
      var s = document.createElement("span");
      s.textContent = "📎 " + f.name;
      var x = document.createElement("button");
      x.type = "button";
      x.className = "cm-x";
      x.setAttribute("aria-label", "Tirar o anexo");
      x.textContent = "×";
      x.addEventListener("click", function () { arquivo.value = ""; anexoNome.hidden = true; });
      anexoNome.appendChild(s);
      anexoNome.appendChild(x);
      anexoNome.hidden = false;
      campo.focus();
    });

    var enviando = false;
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      if (enviando) { return; }
      var texto = campo.value;
      var temAnexo = arquivo.files && arquivo.files.length;
      if (!texto.trim() && !temAnexo && !editando) { campo.focus(); return; }
      enviando = true;
      enviar.disabled = true;
      mostrarErro("");
      var pedido;
      if (editando) {
        pedido = postar(editando, { texto: texto });
      } else {
        if (!token.value) {
          token.value = (window.crypto && window.crypto.randomUUID) ? window.crypto.randomUUID()
            : String(Date.now()) + Math.random().toString(16).slice(2);
        }
        pedido = postar(form.action, new FormData(form));
      }
      pedido.then(function (j) {
        if (!j.ok) { mostrarErro(j.erro || "Não foi possível enviar. Tente de novo."); return; }
        var eraEdicao = !!editando;
        campo.value = "";
        crescer();
        token.value = "";
        arquivo.value = "";
        anexoNome.hidden = true;
        tirarCitacao();
        pararEdicao();
        if (!eraEdicao) { guardar(chave, ""); }
        if (!conversa && j.url) { window.location.href = j.url; return; }
        return novas().then(function () { irAoFim(); marcarLida(); });
      }).catch(function () {
        /* a rede caiu: o texto fica, e o mesmo token não deixa sair em dobro */
        mostrarErro("Sem conexão com o servidor. A mensagem não saiu; tente de novo.");
      }).then(function () {
        enviando = false;
        enviar.disabled = false;
        if (document.activeElement === document.body || document.activeElement === enviar) { campo.focus(); }
      });
    });
    /* Na gaveta, o compositor só pega o foco se a pessoa está nela (clicou). */
    if (!EMBUTIDO || document.hasFocus()) { campo.focus({ preventScroll: true }); }
  }

  /* =================================================================== filtro de nomes */
  function ligarFiltros() {
    document.querySelectorAll("[data-cm-filtro]").forEach(function (f) {
      var caixa = f.closest("fieldset");
      f.addEventListener("input", function () {
        var q = semAcento(f.value);
        caixa.querySelectorAll("[data-cm-nome]").forEach(function (l) {
          l.hidden = q && semAcento(l.getAttribute("data-cm-nome")).indexOf(q) < 0;
        });
      });
    });
  }

  function iniciar() {
    if (!EMBUTIDO) { ligarMoldura(); }
    else {
      document.addEventListener("keydown", function (e) {
        if (e.key === "Escape") { avisarMoldura({ cm: "fechar" }); }
        if (e.altKey && !e.ctrlKey && !e.metaKey && e.code === "KeyM") {
          e.preventDefault();
          avisarMoldura({ cm: "fechar" });
        }
      });
    }
    var app = document.querySelector("[data-cm-app]");
    if (app) { ligarMensageiro(app); }
    ligarFiltros();
  }

  if (document.readyState === "loading") { document.addEventListener("DOMContentLoaded", iniciar); }
  else { iniciar(); }
})();
