/* A casca do layout novo: busca, Novo, sino e coluna de apoio.
 *
 * NADA DEPENDE DESTE ARQUIVO PARA FUNCIONAR. Novo, sino e menu do usuário são
 * <details> do próprio HTML; os links são links e os formulários postam. Sem script,
 * perde-se o conforto: a busca por teclado e o fechar sozinho.
 *
 * ELE NÃO GUARDA NADA, e não monta endereço nenhum: aciona os links e os formulários
 * que o servidor pôs na página. */
(function () {
  "use strict";

  var corpo = document.querySelector(".cg-app");
  if (!corpo) return;

  function semAcento(texto) {
    return String(texto || "").normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
  }

  /* Plural do balcão: «certidões» e «procuracoes» têm de achar «certidão». */
  function raiz(palavra) {
    return palavra.replace(/coes$/, "cao").replace(/oes$/, "ao").replace(/aes$/, "ao")
      .replace(/ns$/, "m").replace(/res$/, "r").replace(/s$/, "");
  }

  function digitando(alvo) {
    return alvo && (alvo.tagName === "INPUT" || alvo.tagName === "TEXTAREA" ||
                    alvo.tagName === "SELECT" || alvo.isContentEditable);
  }

  /* ---------------------------------------------------- o que abre por cima */
  var popovers = Array.prototype.slice.call(document.querySelectorAll("[data-cg-pop]"));

  function fecharPopovers(menos) {
    popovers.forEach(function (p) { if (p !== menos) p.open = false; });
  }

  popovers.forEach(function (p) {
    p.addEventListener("toggle", function () {
      if (!p.open) return;
      fecharPopovers(p);
      var filtro = p.querySelector("[data-cg-novo-filtro]");
      if (filtro) { filtro.value = ""; filtrarNovo(); filtro.focus(); }
    });
  });

  document.addEventListener("click", function (ev) {
    var abrir = ev.target.closest("[data-cg-abrir]");
    if (abrir) {
      var alvo = document.getElementById(abrir.getAttribute("data-cg-abrir"));
      if (alvo) { ev.preventDefault(); ev.stopPropagation(); alvo.open = true; return; }
    }
    if (!ev.target.closest("[data-cg-pop]")) fecharPopovers();
  });

  /* ---------------------------------------------------- o sino conta o que tem */
  var sinoCorpo = document.querySelector("[data-cg-sino-corpo]");
  if (sinoCorpo) {
    var conta = document.querySelector("[data-cg-sino-conta]");
    var vazio = document.querySelector("[data-cg-sino-vazio]");
    var quantos = sinoCorpo.querySelectorAll(".barra-fixa, .flash, [data-cg-aviso]").length;
    if (conta && quantos) { conta.textContent = quantos; conta.hidden = false; }
    if (vazio && !quantos) vazio.hidden = false;
  }

  /* ---------------------------------------------------- o botão Novo */
  var novo = document.getElementById("cg-novo");
  var filtroNovo = document.querySelector("[data-cg-novo-filtro]");
  var marcado = null;

  function itensNovo() {
    return Array.prototype.slice.call(document.querySelectorAll("[data-cg-novo-item]"))
      .filter(function (i) { return !i.hidden; });
  }

  function marcar(item) {
    document.querySelectorAll(".cg-pi.at").forEach(function (x) { x.classList.remove("at"); });
    marcado = item;
    if (!item) return;
    var botao = item.matches(".cg-pi") ? item : item.querySelector(".cg-pi");
    if (botao) { botao.classList.add("at"); botao.scrollIntoView({ block: "nearest" }); }
  }

  function filtrarNovo() {
    if (!filtroNovo) return;
    var q = semAcento(filtroNovo.value).trim();
    document.querySelectorAll("[data-cg-novo-item]").forEach(function (i) {
      i.hidden = Boolean(q) && semAcento(i.getAttribute("data-rotulo")).indexOf(q) === -1;
    });
    document.querySelectorAll("[data-cg-novo-grupo]").forEach(function (g) {
      g.hidden = !g.querySelector("[data-cg-novo-item]:not([hidden])");
    });
    var visiveis = itensNovo();
    var alvo = null;
    /* A letra marca, e o Enter confirma: abrir na primeira tecla atrapalharia quem digita. */
    if (q.length === 1) {
      alvo = visiveis.filter(function (i) {
        return semAcento(i.getAttribute("data-letra")) === q;
      })[0] || null;
    }
    marcar(q ? (alvo || visiveis[0] || null) : null);
  }

  function acionar(item) {
    if (!item) return;
    if (item.tagName === "FORM") item.submit();
    else item.click();
  }

  if (filtroNovo) {
    filtroNovo.addEventListener("input", filtrarNovo);
    filtroNovo.addEventListener("keydown", function (ev) {
      if (ev.key === "Enter") { ev.preventDefault(); acionar(marcado); return; }
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        var lista = itensNovo();
        if (!lista.length) return;
        var i = lista.indexOf(marcado);
        var passo = ev.key === "ArrowDown" ? 1 : -1;
        marcar(lista[i < 0 ? (passo > 0 ? 0 : lista.length - 1) : (i + passo + lista.length) % lista.length]);
      }
    });
  }

  /* ---------------------------------------------------- a busca */
  var paleta = document.querySelector("[data-cg-paleta]");
  var fundo = document.querySelector("[data-cg-paleta-fundo]");
  var entrada = document.querySelector("[data-cg-paleta-q]");
  var listaBusca = document.querySelector("[data-cg-paleta-l]");
  var indice = Array.prototype.slice.call(document.querySelectorAll("[data-cg-indice] > a"));
  var ondeProcurar = Array.prototype.slice.call(document.querySelectorAll("[data-cg-procurar]"));
  var achados = [];
  var selecionado = 0;

  function achar(q) {
    var termos = semAcento(q).split(/\s+/).filter(Boolean).map(raiz);
    var fazer = [];
    var ir = [];
    if (termos.length) {
      indice.forEach(function (x) {
        var palavras = (x.getAttribute("data-t") || "").split(/[^a-z0-9]+/).map(raiz);
        var casa = termos.every(function (t) {
          return palavras.some(function (p) { return p.indexOf(t) === 0; });
        });
        if (casa) (x.getAttribute("data-k") === "novo" ? fazer : ir).push(x);
      });
    }
    return { fazer: fazer.slice(0, 6), ir: ir.slice(0, 8) };
  }

  function desenhar() {
    var q = entrada.value.trim();
    var r = achar(q);
    achados = [];
    listaBusca.textContent = "";

    function grupo(titulo) {
      var g = document.createElement("div");
      g.className = "cg-pop-g";
      g.textContent = titulo;
      listaBusca.appendChild(g);
    }

    function linha(alvo, rotulo, nota) {
      var i = achados.length;
      achados.push(alvo);
      var b = document.createElement("button");
      b.type = "button";
      b.className = "cg-pi" + (i === selecionado ? " at" : "");
      b.setAttribute("data-indice", String(i));
      b.appendChild(document.createTextNode(rotulo));
      if (nota) {
        var s = document.createElement("small");
        s.textContent = nota;
        b.appendChild(s);
      }
      listaBusca.appendChild(b);
    }

    if (r.fazer.length) {
      grupo("Fazer");
      r.fazer.forEach(function (x) { linha(x, x.textContent, ""); });
    }
    if (r.ir.length) {
      grupo("Ir para");
      r.ir.forEach(function (x) { linha(x, x.textContent, x.getAttribute("data-s")); });
    }
    if (q) {
      grupo("Procurar «" + q + "» em");
      ondeProcurar.forEach(function (f) { linha(f, f.getAttribute("data-rotulo"), ""); });
    }
    if (!achados.length) {
      var v = document.createElement("p");
      v.className = "cg-paleta-vazio";
      v.textContent = "Digite o que quer fazer, um nome ou um número.";
      listaBusca.appendChild(v);
    }
  }

  function abrirBusca() {
    if (!paleta) return;
    fecharPopovers();
    paleta.hidden = false;
    fundo.hidden = false;
    entrada.value = "";
    selecionado = 0;
    desenhar();
    entrada.focus();
  }

  function fecharBusca() {
    if (!paleta) return;
    paleta.hidden = true;
    fundo.hidden = true;
  }

  function executar(alvo) {
    if (!alvo) return;
    if (alvo.tagName === "FORM") {
      /* O que se digitou vai só como valor do campo: o endereço é o do formulário. */
      alvo.querySelector("input").value = entrada.value.trim();
      alvo.submit();
      return;
    }
    var idDoForm = alvo.getAttribute("data-form");
    var form = idDoForm ? document.getElementById(idDoForm) : null;
    /* Procuração e irmãs abrem direto: é o mesmo formulário do botão Novo. */
    if (form) form.submit();
    else alvo.click();
  }

  if (paleta) {
    document.querySelectorAll("[data-cg-busca]").forEach(function (b) {
      b.addEventListener("click", abrirBusca);
    });
    fundo.addEventListener("click", fecharBusca);
    entrada.addEventListener("input", function () { selecionado = 0; desenhar(); });
    entrada.addEventListener("keydown", function (ev) {
      if (ev.key === "ArrowDown" || ev.key === "ArrowUp") {
        ev.preventDefault();
        if (!achados.length) return;
        selecionado = (selecionado + (ev.key === "ArrowDown" ? 1 : -1) + achados.length) % achados.length;
        desenhar();
        var at = listaBusca.querySelector(".cg-pi.at");
        if (at) at.scrollIntoView({ block: "nearest" });
      } else if (ev.key === "Enter") {
        ev.preventDefault();
        executar(achados[selecionado]);
      }
    });
    listaBusca.addEventListener("click", function (ev) {
      var b = ev.target.closest("[data-indice]");
      if (b) executar(achados[Number(b.getAttribute("data-indice"))]);
    });
  }

  /* ---------------------------------------------------- a coluna de apoio */
  /* UMA GAVETA DE CADA VEZ: quem fecha é o botão de fechar de cada uma, para o
     script dela saber que fechou. */
  var FECHAR = ["[data-ajuda-fechar]", "[data-agente-fechar]", "[data-prod-fechar]"];
  var ABRIR = [".ajuda-chamar", ".agente-chamar", ".prod-rapida-btn"];
  var PAINEL = ["[data-ajuda-gaveta]", "[data-agente-gaveta]", "[data-prod-painel]"];

  ABRIR.forEach(function (seletor, n) {
    var botao = document.querySelector(".cg-apoio " + seletor);
    if (!botao) return;
    botao.addEventListener("click", function () {
      PAINEL.forEach(function (outro, m) {
        if (m === n) return;
        var painel = document.querySelector(outro);
        var fechar = document.querySelector(".cg-apoio " + FECHAR[m]);
        if (painel && !painel.hidden && fechar) fechar.click();
      });
    }, true);
  });

  /* ---------------------------------------------------- o teclado */
  document.addEventListener("keydown", function (ev) {
    var tecla = (ev.key || "").toLowerCase();
    if ((ev.ctrlKey || ev.metaKey) && tecla === "k") {
      ev.preventDefault();
      abrirBusca();
      return;
    }
    if (ev.key === "Escape") {
      if (paleta && !paleta.hidden) { fecharBusca(); return; }
      if (popovers.some(function (p) { return p.open; })) { fecharPopovers(); return; }
      return;
    }
    if (ev.key === "F1") {
      var ajuda = document.querySelector(".cg-apoio .ajuda-chamar");
      if (ajuda) { ev.preventDefault(); ajuda.click(); }
      return;
    }
    if (ev.altKey && tecla === "p") {
      var prod = document.querySelector(".cg-apoio .prod-rapida-btn");
      if (prod) { ev.preventDefault(); prod.click(); }
      return;
    }
    if (ev.altKey && tecla === "w") {
      var wa = document.querySelector(".cg-apoio .wa-atalho");
      if (wa) { ev.preventDefault(); wa.click(); }
      return;
    }
    if (tecla === "n" && !ev.ctrlKey && !ev.altKey && !ev.metaKey && !digitando(ev.target)
        && novo && (!paleta || paleta.hidden)) {
      ev.preventDefault();
      novo.open = true;
    }
  });
})();
