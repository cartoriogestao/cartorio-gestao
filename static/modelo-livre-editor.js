(() => {
  "use strict";
  const campo = document.querySelector("[data-modelo-livre]");
  const previa = document.querySelector("[data-modelo-livre-previa]");
  if (!previa) return;
  const rotulos = {};
  document.querySelectorAll("[data-claro]").forEach(botao => {
    const nome = botao.dataset.claro.slice(1, -1);
    rotulos[nome] = botao.dataset.rotulo;
    botao.addEventListener("click", () => {
      if (!campo) return;
      campo.setRangeText(botao.dataset.claro, campo.selectionStart, campo.selectionEnd, "end");
      campo.focus(); atualizar();
    });
  });
  function escapar(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }
  function atualizar() {
    const fonte = campo ? campo.value : "";
    const preenchido = fonte.replace(/\{([A-Za-z_][A-Za-z0-9_]*)\}/g, (_, nome) =>
      `<span class="modelo-dado-exemplo">${escapar(rotulos[nome] || nome.replaceAll("_", " "))}</span>`);
    previa.innerHTML = preenchido.split(/\n\n+/).map(p => `<p>${p.replaceAll("\n", "<br>")}</p>`).join("");
  }
  if (campo) campo.addEventListener("input", atualizar);
  atualizar();
})();
