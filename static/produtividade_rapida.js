/* Produtividade rápida — botão global (lançar / cronômetro). Sem libs externas. */
(function () {
  "use strict";

  var caixa = null;
  var painel = null;
  var tickTimer = null;
  var cronoBaseSeg = 0;
  var cronoPausado = false;
  var cronoTickStart = 0;
  var catsCache = null;
  var STORAGE_MODO = "prod_rapida_modo";

  var CATS_PADRAO = [
    "1 - Operacional",
    "2 - Administrativo",
    "3 - Não relacionada ao cartório"
  ];

  function csrfDe(form) {
    var el = form && form.querySelector('input[name="csrf_token"]');
    return el ? el.value : "";
  }

  function postForm(url, form, extra) {
    var dados = new FormData(form);
    if (extra) {
      Object.keys(extra).forEach(function (k) {
        if (extra[k] !== undefined && extra[k] !== null) dados.set(k, extra[k]);
      });
    }
    return fetch(url, {
      method: "POST",
      body: dados,
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfDe(form) || dados.get("csrf_token") || "" }
    }).then(function (r) {
      return r.json().then(function (j) {
        if (!r.ok && (!j || j.ok !== false)) {
          return { ok: false, erro: "Falha HTTP " + r.status };
        }
        return j;
      });
    });
  }

  function getJson(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      return r.json();
    });
  }

  function msg(texto, tipo) {
    var el = caixa.querySelector("[data-prod-msg]");
    if (!el) return;
    if (!texto) {
      el.hidden = true;
      el.textContent = "";
      el.className = "prod-rapida-msg";
      return;
    }
    el.hidden = false;
    el.textContent = texto;
    el.className = "prod-rapida-msg" + (tipo ? " " + tipo : "");
  }

  function selectsCategoria() {
    return [
      caixa.querySelector("[data-prod-categorias]"),
      caixa.querySelector("[data-prod-categorias-crono]")
    ].filter(Boolean);
  }

  function preencherSelect(sel, cats, valor) {
    if (!sel) return;
    var lista = (cats && cats.length) ? cats : CATS_PADRAO;
    var preferido = valor || sel.value || CATS_PADRAO[0];
    if (preferido && lista.indexOf(preferido) < 0) {
      for (var i = 0; i < lista.length; i++) {
        if (lista[i].indexOf(preferido) >= 0 || preferido.indexOf(lista[i].replace(/^\d+ - /, "")) >= 0) {
          preferido = lista[i];
          break;
        }
      }
    }
    if (lista.indexOf(preferido) < 0) preferido = lista[0];
    sel.innerHTML = "";
    lista.forEach(function (c) {
      var o = document.createElement("option");
      o.value = c;
      o.textContent = c;
      if (c === preferido) o.selected = true;
      sel.appendChild(o);
    });
  }

  function preencherTodosCats(cats, valor) {
    catsCache = (cats && cats.length) ? cats : (catsCache || CATS_PADRAO);
    selectsCategoria().forEach(function (sel) {
      preencherSelect(sel, catsCache, valor);
    });
  }

  function escolherPorTecla(digito) {
    var lista = catsCache || CATS_PADRAO;
    var want = String(digito) + " - ";
    var alvo = null;
    for (var i = 0; i < lista.length; i++) {
      if (lista[i].indexOf(want) === 0) { alvo = lista[i]; break; }
    }
    if (!alvo) return;
    selectsCategoria().forEach(function (sel) {
      sel.value = alvo;
    });
  }

  function preencherDatalist(itens) {
    var dl = caixa.querySelector("[data-prod-datalist]");
    if (!dl) return;
    dl.innerHTML = "";
    (itens || []).forEach(function (it) {
      var o = document.createElement("option");
      o.value = it.tarefa || it;
      if (it.categoria) o.label = it.categoria;
      dl.appendChild(o);
    });
  }

  function fmtSeg(seg) {
    seg = Math.max(0, Math.floor(seg || 0));
    var h = Math.floor(seg / 3600);
    var m = Math.floor((seg % 3600) / 60);
    var s = seg % 60;
    if (h > 0) {
      return h + ":" + String(m).padStart(2, "0") + ":" + String(s).padStart(2, "0");
    }
    return m + ":" + String(s).padStart(2, "0");
  }

  function atualizarBotaoTempo(seg, pausado) {
    var el = caixa.querySelector("[data-prod-tempo]");
    var rot = caixa.querySelector("[data-prod-rotulo]");
    if (!el) return;
    if (seg == null) {
      el.hidden = true;
      el.textContent = "";
      if (rot) rot.textContent = "Produtividade";
      caixa.classList.remove("correndo");
      return;
    }
    el.hidden = false;
    el.textContent = (pausado ? "⏸ " : "") + fmtSeg(seg);
    if (rot) rot.textContent = "Cronômetro";
    caixa.classList.add("correndo");
  }

  function pararTick() {
    if (tickTimer) {
      clearInterval(tickTimer);
      tickTimer = null;
    }
  }

  function iniciarTick() {
    pararTick();
    cronoTickStart = Date.now();
    tickTimer = setInterval(function () {
      if (cronoPausado) return;
      var decorrido = cronoBaseSeg + Math.floor((Date.now() - cronoTickStart) / 1000);
      atualizarBotaoTempo(decorrido, false);
      var rel = caixa.querySelector("[data-prod-crono-relogio]");
      if (rel) rel.textContent = fmtSeg(decorrido);
    }, 1000);
  }

  function mostrarCrono(crono) {
    var idle = caixa.querySelector("[data-prod-crono-idle]");
    var ativo = caixa.querySelector("[data-prod-crono-ativo]");
    var btnPausar = caixa.querySelector("[data-prod-pausar]");
    var btnRetomar = caixa.querySelector("[data-prod-retomar]");
    if (!crono) {
      if (idle) idle.hidden = false;
      if (ativo) ativo.hidden = true;
      pararTick();
      atualizarBotaoTempo(null);
      preencherTodosCats(catsCache);
      return;
    }
    if (idle) idle.hidden = true;
    if (ativo) ativo.hidden = false;
    var t = caixa.querySelector("[data-prod-crono-tarefa]");
    var c = caixa.querySelector("[data-prod-crono-cat]");
    if (t) t.textContent = crono.tarefa || "";
    if (c) c.textContent = crono.categoria || "";
    cronoPausado = crono.status === "Pausada";
    cronoBaseSeg = crono.decorrido_seg || (crono.decorrido_min || 0) * 60;
    if (btnPausar) btnPausar.hidden = cronoPausado;
    if (btnRetomar) btnRetomar.hidden = !cronoPausado;
    atualizarBotaoTempo(cronoBaseSeg, cronoPausado);
    var rel = caixa.querySelector("[data-prod-crono-relogio]");
    if (rel) rel.textContent = fmtSeg(cronoBaseSeg);
    if (!cronoPausado) iniciarTick();
    else pararTick();
  }

  function lerModoSalvo() {
    try {
      var m = localStorage.getItem(STORAGE_MODO);
      if (m === "crono" || m === "lancar") return m;
    } catch (e) {}
    return "lancar";
  }

  function gravarModo(modo) {
    try { localStorage.setItem(STORAGE_MODO, modo); } catch (e) {}
  }

  function setModo(modo) {
    var formL = caixa.querySelector("[data-prod-form-lancar]");
    var formC = caixa.querySelector("[data-prod-form-crono]");
    var botoes = caixa.querySelectorAll("[data-prod-modo]");
    botoes.forEach(function (b) {
      var ativo = b.getAttribute("data-prod-modo") === modo;
      b.classList.toggle("ativo", ativo);
      b.setAttribute("aria-selected", ativo ? "true" : "false");
    });
    if (formL) formL.hidden = modo !== "lancar";
    if (formC) formC.hidden = modo !== "crono";
    msg("");
    if (modo === "crono") {
      preencherTodosCats(catsCache || CATS_PADRAO);
      var selC = caixa.querySelector("[data-prod-categorias-crono]");
      if (selC && !selC.value) selC.value = (catsCache || CATS_PADRAO)[0];
    }
    gravarModo(modo);
  }

  function escolherAbaAoAbrir(cronometro) {
    // Cronômetro ativo/pausado no servidor → sempre aba Cronômetro
    if (cronometro) {
      setModo("crono");
      return;
    }
    setModo(lerModoSalvo());
  }

  function carregarContexto() {
    return getJson(caixa.getAttribute("data-url-contexto")).then(function (j) {
      if (!j || !j.ok) {
        preencherTodosCats(CATS_PADRAO);
        return null;
      }
      preencherTodosCats(j.categorias && j.categorias.length ? j.categorias : CATS_PADRAO);
      preencherDatalist(j.tarefas_recentes);
      mostrarCrono(j.cronometro);
      var form = caixa.querySelector("[data-prod-form-lancar]");
      if (form && j.ultimo_fim_hoje && !form.hora_inicio.value) {
        form.hora_inicio.placeholder = j.ultimo_fim_hoje;
      }
      return j;
    }).catch(function () {
      preencherTodosCats(CATS_PADRAO);
      return null;
    });
  }

  function abrir() {
    if (!painel) return;
    painel.hidden = false;
    caixa.classList.add("aberta");
    var btn = caixa.querySelector("[data-prod-abrir]");
    if (btn) btn.setAttribute("aria-expanded", "true");
    msg("");
    preencherTodosCats(catsCache || CATS_PADRAO);
    carregarContexto().then(function (j) {
      escolherAbaAoAbrir(j && j.cronometro);
      var modo = (j && j.cronometro) ? "crono" : lerModoSalvo();
      var formSel = modo === "crono"
        ? "[data-prod-form-crono] select, [data-prod-form-crono] input:not([type=hidden])"
        : "[data-prod-form-lancar] select, [data-prod-form-lancar] input:not([type=hidden])";
      var campo = painel.querySelector(formSel);
      var idle = caixa.querySelector("[data-prod-crono-idle]");
      if (campo && (modo !== "crono" || (idle && !idle.hidden))) {
        try { campo.focus(); } catch (e) {}
      }
    });
  }


  function parseHM(v) {
    if (!v) return null;
    var p = String(v).split(":");
    if (p.length < 2) return null;
    var h = parseInt(p[0], 10), m = parseInt(p[1], 10);
    if (isNaN(h) || isNaN(m)) return null;
    return h * 60 + m;
  }

  function validarLancamentoForm(form) {
    var durEl = form.duracao_min;
    var iniEl = form.hora_inicio;
    var fimEl = form.hora_fim;
    var dur = durEl && durEl.value !== "" ? parseInt(durEl.value, 10) : null;
    if (durEl && durEl.value !== "" && (isNaN(dur) || dur < 1 || dur > 1440)) {
      alert("Duração deve ser entre 1 e 1440 minutos.");
      return false;
    }
    var a = iniEl ? parseHM(iniEl.value) : null;
    var b = fimEl ? parseHM(fimEl.value) : null;
    if (a != null && b != null && b < a) {
      alert("Hora início deve ser anterior à hora fim (no mesmo dia).");
      return false;
    }
    if (a != null && b != null && (b - a) > 1440) {
      alert("Intervalo início–fim não pode passar de 1440 minutos.");
      return false;
    }
    if (dur != null && a != null && b != null && (b - a) !== dur) {
      alert("Duração informada não fecha com início–fim. Ajuste os campos.");
      return false;
    }
    return true;
  }

  function fechar() {
    if (!painel || painel.hidden) return;
    // NÃO para o tick: o botão continua mostrando o tempo com o painel minimizado
    painel.hidden = true;
    caixa.classList.remove("aberta");
    var btn = caixa.querySelector("[data-prod-abrir]");
    if (btn) btn.setAttribute("aria-expanded", "false");
  }

  function digitandoOuAutocomplete() {
    var ae = document.activeElement;
    if (!ae || !painel) return false;
    if (!painel.contains(ae)) return false;
    var tag = ae.tagName;
    if (tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT") return true;
    return false;
  }

  function cliqueForaDeveFechar(ev) {
    if (!caixa || !painel || painel.hidden) return false;
    var t = ev.target;
    if (!t) return false;
    // Cliques no botão ⏱ ou dentro do painel/caixa não fecham
    if (caixa.contains(t)) return false;
    // Não fecha no meio de digitação / select / autocomplete (foco no campo)
    if (digitandoOuAutocomplete()) return false;
    return true;
  }

  // ---------------------------------------------- o fim do expediente
  var alertaEl = null;

  function formAlerta() { return alertaEl && alertaEl.querySelector("[data-prod-form-alerta]"); }

  function mostrarAlerta(texto, botoes) {
    if (!alertaEl) return;
    alertaEl.querySelector("[data-prod-alerta-texto]").textContent = texto;
    ["confirmar", "parar", "ciencia"].forEach(function (b) {
      var el = alertaEl.querySelector("[data-prod-alerta-" + b + "]");
      if (el) el.hidden = botoes.indexOf(b) < 0;
    });
    alertaEl.hidden = false;
  }

  function esconderAlerta() { if (alertaEl) alertaEl.hidden = true; }

  function dataBr(iso) {
    var p = String(iso || "").slice(0, 10).split("-");
    return p.length === 3 ? p[2] + "/" + p[1] + "/" + p[0] : String(iso || "");
  }

  function avisarEncerrados(lista) {
    if (!lista || !lista.length) return false;
    var partes = lista.map(function (r) {
      return "«" + (r.tarefa || "") + "» de " + dataBr(r.data_registro) + " (" +
        (r.hora_inicio || "?") + " às " + (r.hora_fim || "?") + ")";
    });
    mostrarAlerta("Cronômetro esquecido: " + partes.join("; ") +
      (lista.length > 1 ? " foram encerrados" : " foi encerrado") +
      " automaticamente. Confira no painel de produtividade e corrija se precisar.", ["ciencia"]);
    return true;
  }

  function tratarExpediente(j) {
    var crono = j.cronometro;
    var exp = crono && crono.expediente;
    if (exp && exp.situacao === "ENCERRAR") {
      var f = formAlerta();
      if (!f) return;
      postForm(caixa.getAttribute("data-url-encerrar"), f).then(function (r) {
        if (!r || !r.ok) return;
        mostrarCrono(r.cronometro || null);
        avisarEncerrados(r.encerrados_sem_ciencia);
      }).catch(function () {});
      return;
    }
    if (exp && exp.situacao === "AVISO") {
      mostrarAlerta("Fim do expediente: o cronômetro «" + (crono.tarefa || "") +
        "» continua aberto. Se você não confirmar, ele será encerrado às " +
        (exp.encerra_as || "14:30") + " com horário de " + (exp.retroativo || "14:15") + ".",
        ["confirmar", "parar"]);
      return;
    }
    if (avisarEncerrados(j.encerrados_sem_ciencia)) return;
    esconderAlerta();
  }

  function ligarAlerta() {
    alertaEl = caixa.querySelector("[data-prod-alerta]");
    if (!alertaEl) return;
    function acao(attrUrl, depois) {
      postForm(caixa.getAttribute(attrUrl), formAlerta()).then(function (r) {
        if (r && r.cronometro !== undefined) mostrarCrono(r.cronometro || null);
        if (r && r.aviso) { mostrarAlerta(r.aviso, ["ciencia"]); return; }
        if (r && !r.ok && r.erro) { mostrarAlerta(r.erro, ["ciencia"]); return; }
        if (depois) depois(r);
      }).catch(function () {});
    }
    var bc = alertaEl.querySelector("[data-prod-alerta-confirmar]");
    if (bc) bc.addEventListener("click", function () { acao("data-url-confirmar", esconderAlerta); });
    var bp = alertaEl.querySelector("[data-prod-alerta-parar]");
    if (bp) bp.addEventListener("click", function () { acao("data-url-parar", esconderAlerta); });
    var bi = alertaEl.querySelector("[data-prod-alerta-ciencia]");
    if (bi) bi.addEventListener("click", function () { acao("data-url-ciencia", esconderAlerta); });
  }

  function ligar() {
    caixa = document.querySelector("[data-prod-rapida]");
    if (!caixa) return;
    painel = caixa.querySelector("[data-prod-painel]");

    preencherTodosCats(CATS_PADRAO);

    caixa.querySelector("[data-prod-abrir]").addEventListener("click", function (ev) {
      ev.stopPropagation();
      if (painel.hidden) abrir(); else fechar();
    });
    caixa.querySelector("[data-prod-fechar]").addEventListener("click", function (ev) {
      ev.stopPropagation();
      fechar();
    });

    caixa.querySelectorAll("[data-prod-modo]").forEach(function (b) {
      b.addEventListener("click", function () {
        setModo(b.getAttribute("data-prod-modo"));
      });
    });

    document.addEventListener("keydown", function (ev) {
      if (!caixa.classList.contains("aberta")) return;
      if (ev.key === "Escape") {
        fechar();
        return;
      }
      var tag = ev.target && ev.target.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA") return;
      if (ev.key === "1" || ev.key === "2" || ev.key === "3") {
        escolherPorTecla(ev.key);
      }
    });

    // Minimizar ao clicar fora (mousedown captura antes do blur do autocomplete)
    document.addEventListener("mousedown", function (ev) {
      if (cliqueForaDeveFechar(ev)) fechar();
    });

    var formL = caixa.querySelector("[data-prod-form-lancar]");
    formL.addEventListener("submit", function (ev) {
      ev.preventDefault();
      if (!validarLancamentoForm(formL)) return;
      msg("Salvando…");
      postForm(caixa.getAttribute("data-url-lancar"), formL).then(function (j) {
        if (!j || !j.ok) {
          msg((j && j.erro) || "Não foi possível salvar.", "erro");
          return;
        }
        msg("Atividade lançada.", "ok");
        formL.tarefa.value = "";
        formL.duracao_min.value = "";
        formL.hora_inicio.value = "";
        formL.hora_fim.value = "";
        carregarContexto();
      }).catch(function () {
        msg("Falha de rede ao salvar.", "erro");
      });
    });

    var formC = caixa.querySelector("[data-prod-form-crono]");
    formC.addEventListener("submit", function (ev) {
      ev.preventDefault();
      var sel = formC.querySelector("[data-prod-categorias-crono]");
      if (sel && !sel.value) {
        sel.value = (catsCache || CATS_PADRAO)[0];
      }
      if (!sel || !sel.value) {
        msg("Escolha a categoria.", "erro");
        return;
      }
      msg("Iniciando…");
      postForm(caixa.getAttribute("data-url-iniciar"), formC, {
        categoria: sel.value
      }).then(function (j) {
        if (!j || !j.ok) {
          msg((j && j.erro) || "Não foi possível iniciar.", "erro");
          return;
        }
        msg("");
        mostrarCrono(j.cronometro);
        setModo("crono");
      }).catch(function () {
        msg("Falha de rede ao iniciar.", "erro");
      });
    });

    function acaoCrono(urlAttr, okMsg) {
      postForm(caixa.getAttribute(urlAttr), formC).then(function (j) {
        if (!j || !j.ok) {
          msg((j && j.erro) || "Falha na operação.", "erro");
          return;
        }
        if (okMsg) msg(okMsg, "ok");
        mostrarCrono(j.cronometro || null);
        if (!j.cronometro) carregarContexto();
      }).catch(function () {
        msg("Falha de rede.", "erro");
      });
    }

    var bp = caixa.querySelector("[data-prod-pausar]");
    if (bp) bp.addEventListener("click", function () { acaoCrono("data-url-pausar"); });
    var br = caixa.querySelector("[data-prod-retomar]");
    if (br) br.addEventListener("click", function () { acaoCrono("data-url-retomar"); });
    var bs = caixa.querySelector("[data-prod-parar]");
    if (bs) bs.addEventListener("click", function () {
      acaoCrono("data-url-parar", "Cronômetro finalizado.");
    });

    // Status na carga: tempo no botão mesmo com painel fechado — e, a cada
    // minuto, a regra do expediente (aviso às 14h15; sem confirmação, fecha às
    // 14h30 com horário de 14h15). Ordem do oficial, 11/10/2026.
    function lerStatus() {
      return getJson(caixa.getAttribute("data-url-status")).then(function (j) {
        if (!j || !j.ok) return;
        if (j.cronometro) mostrarCrono(j.cronometro);
        tratarExpediente(j);
      }).catch(function () {});
    }
    lerStatus();
    setInterval(lerStatus, 60000);
    ligarAlerta();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", ligar);
  } else {
    ligar();
  }
})();
