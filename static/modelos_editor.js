/* Editor de modelos — Marco 1 (RCPN). Debounce ~500 ms, sem POST duplicado. */
(function () {
  "use strict";
  var root = document.getElementById("me-root");
  if (!root) return;

  var csrf = root.getAttribute("data-csrf") || "";
  var area = root.getAttribute("data-area") || "RCPN";
  var templateId = root.getAttribute("data-template") || "";
  var podePublicar = root.getAttribute("data-pode-publicar") === "1";
  var DEBOUNCE_MS = 500;
  var previaTimer = null;
  var previaSeq = 0;
  var previaInflight = null;

  function $(sel, el) { return (el || document).querySelector(sel); }
  function $all(sel, el) { return Array.prototype.slice.call((el || document).querySelectorAll(sel)); }

  // Busca na lista
  var busca = $("[data-modelo-busca]", root);
  if (busca) {
    busca.addEventListener("input", function () {
      var q = (busca.value || "").toLowerCase();
      $all("[data-modelo-item]", root).forEach(function (a) {
        var nome = a.getAttribute("data-modelo-nome") || "";
        a.style.display = !q || nome.indexOf(q) >= 0 ? "" : "none";
      });
    });
  }

  // Abas
  $all("[data-parte-aba]", root).forEach(function (btn) {
    btn.addEventListener("click", function () {
      var p = btn.getAttribute("data-parte-aba");
      $all("[data-parte-aba]", root).forEach(function (b) {
        b.classList.toggle("ativo", b === btn);
      });
      $all("[data-parte-painel]", root).forEach(function (painel) {
        painel.hidden = painel.getAttribute("data-parte-painel") !== p;
      });
      agendarPrevia();
    });
  });

  function parteAtiva() {
    var ativo = $("[data-parte-aba].ativo", root);
    return ativo ? ativo.getAttribute("data-parte-aba") : "CORPO";
  }

  function coletarConteudo() {
    var out = {};
    $all("[data-me-texto]", root).forEach(function (ta) {
      out[ta.getAttribute("data-me-texto")] = ta.value;
    });
    return out;
  }

  function headersJson() {
    return {
      "Content-Type": "application/json",
      "Accept": "application/json",
      "X-CSRF-Token": csrf
    };
  }

  function setEstado(msg) {
    var el = $("[data-me-estado]", root);
    if (el) el.textContent = msg;
  }

  function mostrarErros(erros, avisos) {
    var box = $("[data-me-erros]", root);
    if (!box) return;
    var msgs = [];
    (erros || []).forEach(function (e) { msgs.push((e.msg || e.codigo || e)); });
    (avisos || []).forEach(function (a) { msgs.push("aviso: " + a); });
    if (!msgs.length) { box.hidden = true; box.textContent = ""; return; }
    box.hidden = false;
    box.textContent = msgs.join("\n");
  }

  function agendarPrevia() {
    if (!templateId) return;
    if (previaTimer) clearTimeout(previaTimer);
    previaTimer = setTimeout(pedirPrevia, DEBOUNCE_MS);
  }

  function pedirPrevia() {
    if (!templateId) return;
    var seq = ++previaSeq;
    var papel = ($("[data-me-papel]", root) || {}).value || "a4";
    var body = {
      area: area,
      template_id: templateId,
      conteudo: coletarConteudo(),
      papel: papel,
      formato: "html"
    };
    // Cancela lógica de duplicata: só a última seq vale
    if (previaInflight && previaInflight.abort) {
      try { previaInflight.abort(); } catch (e) {}
    }
    var ctrl = typeof AbortController !== "undefined" ? new AbortController() : null;
    previaInflight = ctrl;
    setEstado("Atualizando prévia…");
    fetch("/modelos/editor/api/previa", {
      method: "POST",
      headers: headersJson(),
      body: JSON.stringify(body),
      signal: ctrl ? ctrl.signal : undefined,
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (data) {
      if (seq !== previaSeq) return;
      var iframe = $("[data-me-previa]", root);
      var aviso = $("[data-me-aviso-previa]", root);
      if (data && data.html && iframe) {
        iframe.srcdoc = data.html;
      }
      if (aviso) {
        var avisos = (data && data.avisos) || [];
        if (avisos.length) {
          aviso.hidden = false;
          aviso.textContent = avisos.join(" · ");
        } else {
          aviso.hidden = true;
          aviso.textContent = "";
        }
      }
      mostrarErros((data && data.erros) || [], []);
      setEstado(data && data.aproximada ? "Prévia aproximada" : "Prévia atualizada");
    }).catch(function (err) {
      if (err && err.name === "AbortError") return;
      if (seq !== previaSeq) return;
      setEstado("Falha na prévia");
    });
  }

  $all("[data-me-texto]", root).forEach(function (ta) {
    ta.addEventListener("input", agendarPrevia);
  });
  var selPapel = $("[data-me-papel]", root);
  if (selPapel) selPapel.addEventListener("change", agendarPrevia);

  // Ferramentas de inserção
  $all("[data-inserir]", root).forEach(function (btn) {
    btn.addEventListener("click", function () {
      var ta = $("[data-parte-painel]:not([hidden]) [data-me-texto]", root);
      if (!ta) return;
      var snip = btn.getAttribute("data-inserir") || "";
      var start = ta.selectionStart || 0;
      var end = ta.selectionEnd || 0;
      var before = ta.value.slice(0, start);
      var after = ta.value.slice(end);
      var pipe = snip.indexOf("|");
      if (pipe >= 0) {
        ta.value = before + snip.slice(0, pipe) + snip.slice(pipe + 1) + after;
        ta.selectionStart = ta.selectionEnd = start + pipe;
      } else {
        ta.value = before + snip + after;
        ta.selectionStart = ta.selectionEnd = start + snip.length;
      }
      ta.focus();
      agendarPrevia();
    });
  });

  function inserirCampo(rotulo) {
    var ta = $("[data-parte-painel]:not([hidden]) [data-me-texto]", root);
    if (!ta) return;
    var texto = rotulo || "";
    if (texto.charAt(0) !== "{" && texto.charAt(0) !== "@") {
      texto = "{{" + texto + "}}";
    }
    var start = ta.selectionStart || 0;
    var end = ta.selectionEnd || 0;
    ta.value = ta.value.slice(0, start) + texto + ta.value.slice(end);
    ta.selectionStart = ta.selectionEnd = start + texto.length;
    ta.focus();
    agendarPrevia();
  }


  // Trechos bloqueados do motor
  var bloqueadosCache = [];

  function carregarBloqueados() {
    if (!templateId) return;
    var lista = $("[data-me-bloqueados-lista]", root);
    var aviso = $("[data-me-bloqueados-aviso]", root);
    if (!lista) return;
    fetch("/modelos/editor/api/trechos-bloqueados?area=" + encodeURIComponent(area)
          + "&tipo=" + encodeURIComponent(templateId), {
      headers: { "Accept": "application/json", "X-CSRF-Token": csrf },
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (data) {
      bloqueadosCache = data.trechos || [];
      lista.innerHTML = "";
      if (!bloqueadosCache.length) {
        if (aviso) {
          aviso.hidden = false;
          aviso.textContent = (data.avisos && data.avisos[0])
            || "Nenhum trecho bloqueado para este modelo (motor).";
        }
        return;
      }
      if (aviso) { aviso.hidden = true; aviso.textContent = ""; }
      bloqueadosCache.forEach(function (b) {
        var el = document.createElement("div");
        el.className = "me-bloco-travado";
        el.setAttribute("data-bloqueado-id", b.id || "");
        el.title = (b.base_legal || "") + " — não editável";
        el.innerHTML = "<span class='me-cadeado' aria-hidden='true'>🔒</span>"
          + "<code>{{#bloqueado " + (b.id || "") + "}}</code>"
          + "<div class='me-bloco-texto'></div>"
          + "<small></small>";
        el.querySelector(".me-bloco-texto").textContent = b.texto || "";
        el.querySelector("small").textContent = b.base_legal || "";
        // Impede edição / exclusão por seleção no painel
        el.setAttribute("contenteditable", "false");
        el.addEventListener("keydown", function (ev) { ev.preventDefault(); });
        lista.appendChild(el);
      });
      protegerTextareas();
    }).catch(function () {
      if (aviso) {
        aviso.hidden = false;
        aviso.textContent = "Não foi possível carregar trechos bloqueados.";
      }
    });
  }

  function protegerTextareas() {
    $all("[data-me-texto]", root).forEach(function (ta) {
      if (ta._meBloqBound) return;
      ta._meBloqBound = true;
      ta.addEventListener("beforeinput", function (ev) {
        if (bloqueadoSobCursor(ta)) {
          ev.preventDefault();
          setEstado("Trecho bloqueado — não é possível editar.");
        }
      });
      ta.addEventListener("keydown", function (ev) {
        if (ev.key === "Backspace" || ev.key === "Delete") {
          if (bloqueadoSobCursor(ta) || selecaoAtingeBloqueado(ta)) {
            ev.preventDefault();
            setEstado("Trecho bloqueado — não é possível remover.");
          }
        }
      });
      ta.addEventListener("paste", function (ev) {
        if (bloqueadoSobCursor(ta) || selecaoAtingeBloqueado(ta)) {
          ev.preventDefault();
          setEstado("Trecho bloqueado — colar recusado.");
        }
      });
    });
  }

  function intervalosBloqueados(texto) {
    var re = /\{\{#bloqueado\s+([A-Za-z0-9_\-]+)\}\}([\s\S]*?)\{\{\/bloqueado\}\}/g;
    var out = [];
    var m;
    while ((m = re.exec(texto || "")) !== null) {
      out.push({ id: m[1], start: m.index, end: m.index + m[0].length, miolo: m[2] });
    }
    return out;
  }

  function bloqueadoSobCursor(ta) {
    var pos = ta.selectionStart || 0;
    return intervalosBloqueados(ta.value).some(function (b) {
      return pos > b.start && pos < b.end;
    });
  }

  function selecaoAtingeBloqueado(ta) {
    var a = ta.selectionStart || 0;
    var b = ta.selectionEnd || 0;
    if (a === b) {
      // backspace just before / delete just after
      return intervalosBloqueados(ta.value).some(function (blk) {
        return a === blk.end || a === blk.start;
      });
    }
    return intervalosBloqueados(ta.value).some(function (blk) {
      return a < blk.end && b > blk.start;
    });
  }


  // Carregar campos
  function carregarCampos() {
    if (!templateId) return;
    var lista = $("[data-me-campos-lista]", root);
    if (!lista) return;
    fetch("/modelos/editor/api/campos?area=" + encodeURIComponent(area)
          + "&tipo=" + encodeURIComponent(templateId), {
      headers: { "Accept": "application/json", "X-CSRF-Token": csrf },
      credentials: "same-origin"
    }).then(function (r) { return r.json(); }).then(function (data) {
      lista.innerHTML = "";
      (data.campos || []).forEach(function (c) {
        var btn = document.createElement("button");
        btn.type = "button";
        var rotulo = c.rotulo || ("{{" + c.nome + "}}");
        btn.innerHTML = "<code></code><small></small>";
        btn.querySelector("code").textContent = rotulo;
        btn.querySelector("small").textContent = c.grupo || c.nome || "";
        btn.addEventListener("click", function () { inserirCampo(rotulo); });
        lista.appendChild(btn);
      });
    }).catch(function () {});
  }

  // Salvar rascunho
  var btnSalvar = $("[data-me-salvar]", root);
  if (btnSalvar) {
    btnSalvar.addEventListener("click", function () {
      var parte = parteAtiva();
      var conteudos = coletarConteudo();
      setEstado("Salvando…");
      fetch("/modelos/editor/api/salvar", {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({
          area: area,
          template_id: templateId,
          parte: parte,
          conteudo: conteudos[parte] || ""
        }),
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (!data.ok) {
          mostrarErros([{ msg: data.erro || "falha" }], []);
          setEstado("Erro ao salvar");
          return;
        }
        setEstado("Rascunho salvo");
        mostrarErros([], []);
      }).catch(function (e) {
        setEstado("Erro ao salvar");
        mostrarErros([{ msg: String(e) }], []);
      });
    });
  }

  // Upload ODT
  $all("[data-me-odt]", root).forEach(function (inp) {
    inp.addEventListener("change", function () {
      if (!inp.files || !inp.files[0]) return;
      var fd = new FormData();
      fd.append("csrf_token", csrf);
      fd.append("area", area);
      fd.append("template_id", templateId);
      fd.append("parte", inp.getAttribute("data-me-odt") || "MOLDE");
      fd.append("arquivo", inp.files[0]);
      setEstado("Enviando ODT…");
      fetch("/modelos/editor/api/salvar", {
        method: "POST",
        headers: { "X-CSRF-Token": csrf },
        body: fd,
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(function (data) {
        if (!data.ok) {
          mostrarErros([{ msg: data.erro || "falha" }], []);
          return;
        }
        setEstado("Rascunho ODT salvo");
        var sha = $("[data-me-sha]", root);
        if (sha && data.versao) sha.textContent = data.versao.sha256 || "";
      });
    });
  });

  // Publicar
  var btnPub = $("[data-me-publicar]", root);
  if (btnPub) {
    btnPub.addEventListener("click", function () {
      if (!podePublicar) {
        mostrarErros([{ msg: "Somente ADMIN ou MANAGER podem publicar." }], []);
        return;
      }
      var parte = parteAtiva();
      var conteudos = coletarConteudo();
      setEstado("Publicando…");
      fetch("/modelos/editor/api/publicar", {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({
          area: area,
          template_id: templateId,
          parte: parte,
          conteudo: conteudos[parte]
        }),
        credentials: "same-origin"
      }).then(function (r) { return r.json().then(function (d) { return { status: r.status, data: d }; }); })
        .then(function (res) {
          if (!res.data.ok) {
            mostrarErros([{ msg: res.data.erro || "recusado" }], []);
            setEstado("Publicação recusada");
            return;
          }
          setEstado("Publicado");
          mostrarErros([], []);
        });
    });
  }

  // Histórico
  var dlg = document.getElementById("me-hist-dialog");
  var btnHist = $("[data-me-historico]", root);
  if (btnHist && dlg) {
    btnHist.addEventListener("click", function () {
      var parte = parteAtiva();
      fetch("/modelos/editor/api/historico?area=" + encodeURIComponent(area)
            + "&template_id=" + encodeURIComponent(templateId)
            + "&parte=" + encodeURIComponent(parte), {
        headers: { "Accept": "application/json", "X-CSRF-Token": csrf },
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(function (data) {
        var lista = $("[data-me-hist-lista]", dlg);
        var diffEl = $("[data-me-hist-diff]", dlg);
        lista.innerHTML = "";
        diffEl.textContent = "";
        var ids = [];
        (data.historico || []).forEach(function (h) {
          ids.push(h.id);
          var row = document.createElement("div");
          row.className = "me-hist-row";
          row.innerHTML = "<code>#" + h.id + "</code> <span>" + (h.status || "") +
            "</span> <small>" + (h.criado_em || "") + " · " + (h.autor || "") +
            "</small> <button type='button' data-rest='" + h.id + "'>Restaurar</button>";
          lista.appendChild(row);
        });
        if (ids.length >= 2) {
          fetch("/modelos/editor/api/diff?a=" + ids[1] + "&b=" + ids[0], {
            headers: { "Accept": "application/json", "X-CSRF-Token": csrf },
            credentials: "same-origin"
          }).then(function (r) { return r.json(); }).then(function (d) {
            diffEl.textContent = d.diff || (d.iguais ? "(idênticas)" : "");
          });
        }
        $all("[data-rest]", lista).forEach(function (b) {
          b.addEventListener("click", function () {
            fetch("/modelos/editor/api/restaurar", {
              method: "POST",
              headers: headersJson(),
              body: JSON.stringify({ versao_id: Number(b.getAttribute("data-rest")) }),
              credentials: "same-origin"
            }).then(function (r) { return r.json(); }).then(function (d) {
              if (d.ok) location.reload();
              else alert(d.erro || "falha");
            });
          });
        });
        if (typeof dlg.showModal === "function") dlg.showModal();
        else dlg.setAttribute("open", "open");
      });
    });
  }

  function b64ParaBlob(b64, mime) {
    var bin = atob(b64);
    var len = bin.length;
    var bytes = new Uint8Array(len);
    for (var i = 0; i < len; i++) bytes[i] = bin.charCodeAt(i);
    return new Blob([bytes], { type: mime || "application/pdf" });
  }

  function mostrarPdfOuMensagem(data) {
    var iframeHtml = $("[data-me-previa]", root);
    var iframePdf = $("[data-me-pdf-view]", root);
    var aviso = $("[data-me-aviso-previa]", root);
    var erros = (data && data.erros) || [];
    var avisos = (data && data.avisos) || [];
    if (erros.length) {
      mostrarErros(erros, avisos);
      if (aviso) {
        aviso.hidden = false;
        aviso.textContent = erros.map(function (e) { return e.msg || e.codigo; }).join(" · ");
      }
    }
    // Marco 2b: preferir arquivo_base64; pdf_base64 só como alias/fallback
    var arqB64 = (data && (data.arquivo_base64 || data.pdf_base64)) || null;
    if (arqB64) {
      var mime = data.mime || "application/pdf";
      var blob = b64ParaBlob(arqB64, mime);
      var url = URL.createObjectURL(blob);
      if (mime.indexOf("pdf") >= 0 && iframePdf) {
        if (iframeHtml) iframeHtml.style.display = "none";
        iframePdf.hidden = false;
        iframePdf.style.display = "block";
        iframePdf.src = url;
        setEstado("PDF fiel do motor");
      } else {
        // ODT ou outro: download
        var a = document.createElement("a");
        a.href = url;
        a.download = (templateId || "modelo").toLowerCase() +
          (mime.indexOf("opendocument") >= 0 ? ".odt" : ".bin");
        a.click();
        setEstado("Arquivo do motor baixado (" + mime + ")");
      }
      return;
    }
    // Motor não suportou: mostrar mensagem, NÃO gerar PDF próprio
    var msg = (erros[0] && (erros[0].msg || erros[0].codigo))
      || (avisos[0])
      || (data && data.erro)
      || "Motor não devolveu PDF/ODT para este modelo.";
    if (aviso) { aviso.hidden = false; aviso.textContent = msg; }
    setEstado("Sem PDF fiel — " + msg);
    if (data && data.html && iframeHtml) {
      iframeHtml.style.display = "block";
      if (iframePdf) { iframePdf.hidden = true; iframePdf.style.display = "none"; }
      iframeHtml.srcdoc = data.html;
    }
  }

  // Ver como sai (PDF) — só o que o motor devolver
  var btnPdf = $("[data-me-pdf]", root);
  if (btnPdf) {
    btnPdf.addEventListener("click", function () {
      var papel = ($("[data-me-papel]", root) || {}).value || "a4";
      setEstado("Pedindo PDF ao motor…");
      fetch("/modelos/editor/api/previa", {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({
          area: area,
          template_id: templateId,
          conteudo: coletarConteudo(),
          papel: papel,
          formato: "pdf"
        }),
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(mostrarPdfOuMensagem)
        .catch(function (e) { setEstado("Falha ao pedir PDF: " + e); });
    });
  }

  // Baixar ODT (moldes) — formato odt no motor
  var btnOdt = $("[data-me-odt]", root);
  if (btnOdt) {
    var tipo = root.getAttribute("data-tipo") || "";
    if (tipo === "molde" || (templateId && templateId.indexOf("MOLDE") >= 0)) {
      btnOdt.hidden = false;
    }
    btnOdt.addEventListener("click", function () {
      var papel = ($("[data-me-papel]", root) || {}).value || "a4";
      setEstado("Pedindo ODT ao motor…");
      fetch("/modelos/editor/api/previa", {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({
          area: area,
          template_id: templateId,
          conteudo: coletarConteudo(),
          papel: papel,
          formato: "odt"
        }),
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(mostrarPdfOuMensagem)
        .catch(function (e) { setEstado("Falha ao pedir ODT: " + e); });
    });
  }

  // Semear v1
  var btnSemear = document.getElementById("me-semear");
  if (btnSemear) {
    btnSemear.addEventListener("click", function () {
      if (!confirm("Semear a v1 publicada de todos os modelos RCPN a partir do vigente?")) return;
      fetch("/modelos/editor/api/semear", {
        method: "POST",
        headers: headersJson(),
        body: JSON.stringify({ area: area }),
        credentials: "same-origin"
      }).then(function (r) { return r.json(); }).then(function (d) {
        alert(d.ok ? ("Semeados: " + (d.feitos || []).length) : (d.erro || "falha"));
        if (d.ok) location.reload();
      });
    });
  }

  carregarCampos();
  carregarBloqueados();
  agendarPrevia();
})();
