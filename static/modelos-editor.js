(() => {
  "use strict";
  const raiz = document.querySelector("[data-modelo-editor]");
  const busca = document.querySelector("[data-modelo-busca]");
  if (busca) busca.addEventListener("input", () => {
    const termo = busca.value.trim().toLocaleLowerCase("pt-BR");
    document.querySelectorAll("[data-modelo-item]").forEach(item => {
      item.hidden = !item.dataset.modeloNome.includes(termo);
    });
  });
  if (!raiz) return;
  const abas = [...raiz.querySelectorAll("[data-parte-aba]")];
  const paineis = [...raiz.querySelectorAll("[data-parte-painel]")];
  const campos = [...raiz.querySelectorAll("[data-modelo-parte]")];
  const iframe = raiz.querySelector("[data-modelo-previa]");
  const erro = raiz.querySelector("[data-modelo-erro]");
  let relogio;
  function abrir(parte) {
    abas.forEach(a => { const ativo = a.dataset.parteAba === parte; a.classList.toggle("ativo", ativo); a.setAttribute("aria-selected", ativo ? "true" : "false"); });
    paineis.forEach(p => { p.hidden = p.dataset.partePainel !== parte; });
  }
  abas.forEach(a => a.addEventListener("click", () => abrir(a.dataset.parteAba)));
  raiz.querySelectorAll("[data-inserir]").forEach(botao => botao.addEventListener("click", () => {
    const campo = botao.closest("[data-parte-painel]").querySelector("textarea");
    const molde = botao.dataset.inserir, inicio = campo.selectionStart, fim = campo.selectionEnd;
    const texto = molde.includes("|") ? molde.replace("|", campo.value.slice(inicio, fim)) : molde;
    campo.setRangeText(texto, inicio, fim, "end"); campo.focus(); campo.dispatchEvent(new Event("input", {bubbles: true}));
  }));
  raiz.querySelectorAll("[data-marcador]").forEach(botao => botao.addEventListener("click", () => {
    const painel = botao.closest("[data-parte-painel]");
    const campo = painel.querySelector("textarea");
    campo.setRangeText(botao.dataset.marcador, campo.selectionStart, campo.selectionEnd, "end");
    campo.focus(); campo.dispatchEvent(new Event("input", {bubbles:true}));
  }));
  async function atualizar() {
    const fd = new FormData(), primeiro = paineis[0];
    fd.set("csrf_token", primeiro.querySelector('[name="csrf_token"]').value);
    fd.set("ato", primeiro.querySelector('[name="ato"]').value);
    campos.forEach(c => fd.set(`parte_${c.dataset.modeloParte.toLowerCase()}`, c.value));
    raiz.querySelectorAll("[data-modelo-estado]").forEach(e => e.textContent = "Atualizando prévia…");
    try {
      const resposta = await fetch(raiz.dataset.previaUrl, {method:"POST", body:fd, headers:{"X-Requested-With":"XMLHttpRequest"}});
      const dados = await resposta.json();
      if (!resposta.ok || !dados.ok) throw new Error(dados.erro || "Não foi possível montar a prévia.");
      iframe.srcdoc = dados.html; erro.hidden = true;
      raiz.querySelectorAll("[data-modelo-estado]").forEach(e => e.textContent = "Prévia atualizada");
    } catch (e) {
      erro.textContent = e.message; erro.hidden = false;
      raiz.querySelectorAll("[data-modelo-estado]").forEach(x => x.textContent = "Revise o erro indicado");
    }
  }
  campos.forEach(c => c.addEventListener("input", () => { clearTimeout(relogio); relogio = setTimeout(atualizar, 320); }));
  atualizar();
})();
