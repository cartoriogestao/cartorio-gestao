import test from 'node:test';
import assert from 'node:assert/strict';
import { centavos, periodo, confereLinha, janelaSegunda, localizarPortalAutenticado,
  tentarLoginSalvo, PORTAL } from '../tools/portal_selo_worker.mjs';

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
  senha = true, autofill = false } = {}) {
  const p = { cliques: 0, consultas: 0, isClosed: () => fechado, url: () => url };
  p.getByRole = (papel, { name }) => ({
    count: async () => { p.consultas++; return sair === papel && name.test('SAIR') ? 1 : 0; },
    click: async () => { assert.equal(papel, 'button'); assert.equal(name, 'Entrar'); p.cliques++; }
  });
  p.getByPlaceholder = () => ({ count: async () => 1,
    evaluate: async fn => fn({ value: usuario ? 'preenchido' : '' }) });
  p.locator = () => ({ count: async () => 1,
    evaluate: async fn => fn({ value: senha ? 'preenchida' : '', matches: () => autofill }) });
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
