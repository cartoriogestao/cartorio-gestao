import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs/promises';
import os from 'node:os';
import path from 'node:path';
import { executar, origemSistema } from '../tools/portal_selo_worker.mjs';
import { navegadorFicticio } from './apoio_portal_selo_worker.mjs';

async function caso(t) {
  const pasta = await fs.mkdtemp(path.join(os.tmpdir(), 'portal-ficticio-'));
  t.after(() => fs.rm(pasta, { recursive: true, force: true }));
  return { sistema: 'http://127.0.0.1:8765', httpRedePrivada: true, pastaDados: pasta, producaoLiberada: true };
}
const linha = () => ({ fundo: 'FERJ' });
const resposta = data => ({ ok: () => true, headers: () => ({ 'content-type': 'application/json' }), json: async () => data });
function apiFicticia({ divergir = false, expirar = false } = {}) {
  return async (_url, { multipart }) => {
    if (expirar) return { ok: () => false, status: () => 302 };
    return resposta(multipart.conferir === '1' ? { fundo: 'FERJ', inicio: '2026-10-01', fim: '2026-10-31',
      vencimento: '2026-11-10', valor_centavos: divergir ? 1 : 12345 } :
      { id: 1, novo: true, situacao: 'AUTORIZADA', envio_solicitado: true });
  };
}

test('origem privada é exata e não aceita domínio parecido ou credencial na URL', () => {
  for (const sistema of ['http://localhost.exemplo.test', 'http://127.0.0.1.exemplo.test',
    'http://100.128.0.1', 'http://100.64.0.1.exemplo.test', 'https://usuario:senha@example.test',
    'https://example.test/rota', 'ftp://127.0.0.1'])
    assert.throws(() => origemSistema({ sistema, httpRedePrivada: true }));
  assert.equal(origemSistema({ sistema: 'http://100.65.0.1:8765', httpRedePrivada: true }), 'http://100.65.0.1:8765');
});

test('produção desligada barra inclusive chamada direta do executor', async t => {
  const cfg = await caso(t);
  const r = await executar({ ...cfg, producaoLiberada: false }, '--executar', { abrir: () => assert.fail('não abrir') });
  assert.equal(r.concluido, false);
});

test('portal sem guias ou ainda sem botão retoma em vez de concluir o dia', async t => {
  const cfg = await caso(t);
  for (const linhas of [[], [{ fundo: 'FERJ', disponivel: false }]]) {
    const nav = navegadorFicticio({ linhas, post: () => assert.fail('não cadastrar') });
    assert.equal((await executar(cfg, '--executar', nav)).concluido, false);
    assert.equal(nav.dados.posts, 0);
  }
});

test('emite uma vez, guarda PDF, confere, cadastra e retoma sem duplicar', async t => {
  const cfg = await caso(t), linhas = [linha()];
  const nav = navegadorFicticio({ linhas, post: apiFicticia() });
  const r = await executar(cfg, '--executar', nav);
  assert.equal(r.concluido, true); assert.equal(nav.dados.emissoes, 1); assert.equal(nav.dados.posts, 2);
  const deNovo = navegadorFicticio({ linhas, post: () => assert.fail('já cadastrado') });
  assert.equal((await executar(cfg, '--executar', deNovo)).concluido, true);
  assert.equal(deNovo.dados.emissoes + deNovo.dados.posts, 0);
  assert.equal(await fs.readFile(path.join(cfg.pastaDados, 'FERJ_2026-10-01_2026-10-31.pdf'), 'utf8'), '%PDF-ficticio');
});

test('guia existente usa somente segunda via', async t => {
  const nav = navegadorFicticio({ linhas: [{ ...linha(), existente: true }], post: apiFicticia() });
  assert.equal((await executar(await caso(t), '--executar', nav)).concluido, true);
  assert.equal(nav.dados.emissoes, 0); assert.equal(nav.dados.segundasVias, 1);
});

test('intenção anterior a clique interrompido impede nova emissão incerta', async t => {
  const cfg = await caso(t), linhas = [linha()];
  const nav = navegadorFicticio({ linhas, falharClique: true, post: () => assert.fail('sem PDF') });
  await assert.rejects(executar(cfg, '--executar', nav), /CLIQUE_INTERROMPIDO/);
  const outra = navegadorFicticio({ linhas, post: () => assert.fail('sem PDF') });
  const r = await executar(cfg, '--executar', outra);
  assert.equal(r.concluido, false); assert.equal(outra.dados.emissoes, 0);
});

test('PDF diferente da linha não cadastra; sessão vencida retoma do PDF salvo', async t => {
  const cfg = await caso(t), linhas = [linha()];
  const ruim = navegadorFicticio({ linhas, post: apiFicticia({ divergir: true }) });
  await assert.rejects(executar(cfg, '--executar', ruim), /PDF difere/);
  assert.equal(ruim.dados.posts, 1);
  const vencida = navegadorFicticio({ linhas, post: apiFicticia({ expirar: true }) });
  await assert.rejects(executar(cfg, '--executar', vencida), /HTTP 302/);
  assert.equal(vencida.dados.emissoes + vencida.dados.segundasVias, 0);
  const renovada = navegadorFicticio({ linhas, post: apiFicticia() });
  assert.equal((await executar(cfg, '--executar', renovada)).concluido, true);
  assert.equal(renovada.dados.emissoes, 0);
});

test('diário cadastrado que diverge da linha exige conferência', async t => {
  const cfg = await caso(t), linhas = [linha()];
  await executar(cfg, '--executar', navegadorFicticio({ linhas, post: apiFicticia() }));
  linhas[0].valor = 'R$ 123,46';
  await assert.rejects(executar(cfg, '--executar', navegadorFicticio({ linhas, post: apiFicticia() })), /DIARIO_DIVERGE/);
});

test('origem de sessão diferente e login pendente não emitem nem enviam PDF', async t => {
  const cfg = await caso(t);
  for (const opcoes of [{ autenticado: false }, { origem: 'https://exemplo.test' }]) {
    const nav = navegadorFicticio({ ...opcoes, linhas: [linha()], post: () => assert.fail('sem sessão') });
    const r = await executar(cfg, '--executar', nav);
    assert.equal(r.estado, 'AGUARDANDO_AUTORIZACAO');
    assert.equal(nav.dados.emissoes + nav.dados.posts, 0);
  }
});
