import test from 'node:test';
import assert from 'node:assert/strict';
import { centavos, periodo, confereLinha, janelaSegunda, localizarPortalAutenticado,
  tentarLoginSalvo, novaPaginaAposClique, PORTAL } from '../tools/portal_selo_worker.mjs';

test('centavos sem arredondamento e período na virada do ano', () => {
  assert.equal(centavos('R$ 1.234,56'), 123456);
  assert.deepEqual(periodo('29/12 a 04/01 (Janeiro/2027)'), { inicio: '2026-12-29', fim: '2027-01-04' });
  assert.throws(() => centavos('sem valor'));
});
test('agenda segunda 08h no fuso da serventia', () => {
  assert.equal(janelaSegunda(new Date('2026-11-09T10:59:00Z')).aberta, false);
  assert.equal(janelaSegunda(new Date('2026-11-09T11:00:00Z')).aberta, true);
  assert.equal(janelaSegunda(new Date('2026-11-10T11:00:00Z')).aberta, false);
});
test('PDF precisa coincidir com fundo, período, vencimento e valor da linha', () => {
  const linha = { fundo: 'FERJ', inicio: '2026-10-01', fim: '2026-10-31', vencimento: '2026-11-10', valor: 100 };
  const g = { ...linha, valor_centavos: 100 };
  assert.equal(confereLinha(g, linha), true);
  for (const alterado of [{ fundo: 'FERC' }, { valor_centavos: 101 }, { vencimento: '2026-11-11' }])
    assert.equal(confereLinha({ ...g, ...alterado }, linha), false);
});

function pagina({ url = PORTAL, fechado = false, sair = '', usuario = true,
  senha = true, autofill = false, ambiguo = false, foraTela = false } = {}) {
  const p = { cliques: 0, consultas: 0, desanexadas: 0, isClosed: () => fechado, url: () => url };
  const no = (papel, nome, id) => {
    const n = { role: { value: papel }, name: { value: nome }, backendDOMNodeId: id };
    Object.defineProperty(n, 'value', { get() { throw Error('Não ler valores dos campos'); } });
    return n;
  };
  const nodes = sair ? [no(sair, ' SAIR', 4)] :
    [no('textbox', 'Usuário', 1), no('textbox', 'Senha', 2), no('button', 'Entrar', 3)];
  if (ambiguo) nodes.push(no('button', 'Entrar', 5));
  p.context = () => ({ newCDPSession: async () => {
    p.consultas++;
    return {
      send: async (metodo, dados) => {
        if (metodo === 'Accessibility.getFullAXTree') return { nodes };
        if (['DOM.enable', 'DOM.getDocument', 'CSS.enable'].includes(metodo)) return {};
        if (metodo === 'DOM.pushNodesByBackendIdsToFrontend') return { nodeIds: dados.backendNodeIds };
        if (metodo === 'CSS.getMatchedStylesForNode') {
          const salvo = autofill && (dados.nodeId === 1 ? usuario : senha);
          return { matchedCSSRules: [{ matchingSelectors: [salvo ? 1 : 0], rule: {
            selectorList: { selectors: [{ text: 'input' }, { text: 'input:-internal-autofill-selected' }] }
          } }] };
        }
        if (metodo === 'DOM.getBoxModel') return { model: { width: 20, height: 20,
          content: foraTela ? [2000, 2000, 2020, 2000, 2020, 2020, 2000, 2020] : [20, 20, 40, 20, 40, 40, 20, 40] } };
        throw Error('Comando não permitido no teste: ' + metodo);
      },
      detach: async () => { p.desanexadas++; }
    };
  } });
  p.viewportSize = () => ({ width: 1280, height: 720 });
  p.mouse = { click: async (x, y) => { assert.equal(x, 30); assert.equal(y, 30); p.cliques++; } };
  return p;
}

test('login em outra aba do mesmo perfil é reconhecido, incluindo Sair como botão', async () => {
  const inicial = pagina(), autenticada = pagina({ sair: 'button' });
  assert.equal(await localizarPortalAutenticado({ pages: () => [inicial, autenticada] }, inicial), autenticada);
  const outra = pagina({ sair: 'link' });
  assert.equal(await localizarPortalAutenticado({ pages: () => [outra, autenticada] }, autenticada), autenticada);
});

test('não consulta sessão de outro site, contexto ou aba fechada', async () => {
  const externo = pagina({ url: 'https://example.com', sair: 'link' });
  const fechado = pagina({ fechado: true, sair: 'link' });
  const outroContexto = pagina({ sair: 'link' });
  const inicial = pagina();
  assert.equal(await localizarPortalAutenticado({ pages: () => [externo, fechado, inicial] }, outroContexto), null);
  assert.equal(externo.consultas + fechado.consultas + outroContexto.consultas, 0);
});

test('aguarda digitação manual e exige usuário antes de enviar senha salva', async () => {
  for (const dados of [{ autofill: false }, { autofill: true, usuario: false },
    { autofill: true, senha: false }, { autofill: true, url: 'https://example.com' }]) {
    const p = pagina(dados);
    assert.equal(await tentarLoginSalvo(p), false);
    assert.equal(p.cliques, 0);
  }
  const salvo = pagina({ autofill: true });
  assert.equal(await tentarLoginSalvo(salvo), true);
  assert.equal(await tentarLoginSalvo(salvo, true), false);
  assert.equal(salvo.cliques, 1);
});

test('não envia login com botão ambíguo ou fora da tela; libera a sessão de diagnóstico', async () => {
  const ambiguo = pagina({ autofill: true, ambiguo: true });
  assert.equal(await tentarLoginSalvo(ambiguo), false);
  assert.equal(ambiguo.cliques, 0);
  assert.equal(ambiguo.desanexadas, 1);
  const fora = pagina({ autofill: true, foraTela: true });
  await assert.rejects(tentarLoginSalvo(fora), /ENTRAR_FORA_DA_TELA/);
  assert.equal(fora.cliques, 0);
  assert.equal(fora.desanexadas, 1);
});

test('abertura da segunda via aguarda o clique e devolve a página', async () => {
  const pagina = {}, contexto = { waitForEvent: async evento => { assert.equal(evento, 'page'); return pagina; } };
  let cliques = 0;
  assert.equal(await novaPaginaAposClique(contexto, async () => { cliques++; }), pagina);
  assert.equal(cliques, 1);
});

test('falha do clique não deixa rejeição de nova aba sem tratamento', async () => {
  let expirar;
  const evento = new Promise((_, rejeitar) => { expirar = rejeitar; });
  await assert.rejects(novaPaginaAposClique({ waitForEvent: () => evento },
    () => { throw Error('clique indisponível'); }), /clique indisponível/);
  expirar(Error('nova aba não chegou'));
  await new Promise(r => setImmediate(r));
});
