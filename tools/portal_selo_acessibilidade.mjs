// Acessibilidade nativa e metadados CSS: não consulta valores de campos.
const PORTAL = 'https://portalselo.tjma.jus.br';
const exato = (n, papel, nome) => !n.ignored && n.role?.value === papel &&
  String(n.name?.value || '').trim() === nome;

async function comPrazo(promessa) {
  let timer;
  try {
    return await Promise.race([promessa, new Promise((_, rejeitar) => {
      timer = setTimeout(() => rejeitar(Error('O navegador não respondeu à conferência de acesso.')), 5000);
    })]);
  } finally { clearTimeout(timer); }
}

export async function examinarPortal(pagina, solicitarLogin = false) {
  if (pagina.isClosed() || new URL(pagina.url()).origin !== PORTAL)
    return { autenticado: false, fora_do_portal: true };
  const cdp = await comPrazo(pagina.context().newCDPSession(pagina));
  const enviar = (metodo, parametros) => comPrazo(cdp.send(metodo, parametros));
  try {
    const { nodes } = await enviar('Accessibility.getFullAXTree');
    // No portal, Sair é uma âncora sem href. A árvore nativa a reconhece.
    if (nodes.some(n => !n.ignored && ['link', 'button'].includes(n.role?.value) &&
        /\bSAIR\b/i.test(n.name?.value || ''))) return { autenticado: true };
    const usuario = nodes.filter(n => exato(n, 'textbox', 'Usuário'));
    const senha = nodes.filter(n => exato(n, 'textbox', 'Senha'));
    const entrar = nodes.filter(n => exato(n, 'button', 'Entrar'));
    if (usuario.length !== 1 || senha.length !== 1 || entrar.length !== 1)
      return { autenticado: false, formulario_login: false };
    // Consulta apenas quais seletores CSS estão efetivamente aplicados.
    await enviar('DOM.enable');
    await enviar('DOM.getDocument', { depth: 0 });
    await enviar('CSS.enable');
    async function autofill(no) {
      const { nodeIds } = await enviar('DOM.pushNodesByBackendIdsToFrontend',
        { backendNodeIds: [no.backendDOMNodeId] });
      const estilos = await enviar('CSS.getMatchedStylesForNode', { nodeId: nodeIds[0] });
      const seletores = (estilos.matchedCSSRules || []).flatMap(r =>
        (r.matchingSelectors || []).map(i => r.rule.selectorList.selectors[i].text));
      return seletores.some(s => /:-webkit-autofill\b|:autofill\b|:-internal-autofill-selected\b/.test(s));
    }
    const usuarioSalvo = await autofill(usuario[0]), senhaSalva = await autofill(senha[0]);
    const resultado = { autenticado: false, formulario_login: true,
      usuario_autofill: usuarioSalvo, senha_autofill: senhaSalva, login_enviado: false };
    if (solicitarLogin && usuarioSalvo && senhaSalva) {
      const { model } = await enviar('DOM.getBoxModel', { backendNodeId: entrar[0].backendDOMNodeId });
      const q = model.content, x = (q[0] + q[2] + q[4] + q[6]) / 4,
        y = (q[1] + q[3] + q[5] + q[7]) / 4;
      const v = pagina.viewportSize();
      if (!(model.width > 0 && model.height > 0 && x >= 0 && y >= 0 &&
          (!v || (x < v.width && y < v.height)))) throw Error('ENTRAR_FORA_DA_TELA');
      await comPrazo(pagina.mouse.click(x, y));
      resultado.login_enviado = true;
    }
    return resultado;
  } finally { await comPrazo(cdp.detach()).catch(() => {}); }
}
