import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import test from 'node:test';
import vm from 'node:vm';

const script = readFileSync(new URL('../static/despesas_codigo.js', import.meta.url), 'utf8');
const leitura = {forma: 'BOLETO', forma_nome: 'Boleto', valor: '123,45',
  vencimento: '2026-11-10', aviso: 'Confira a fatura.'};

function tela(fetch) {
  const botao = {addEventListener: (tipo, acao) => { botao[tipo] = acao; }};
  const usar = {hidden: true, addEventListener: (tipo, acao) => { usar[tipo] = acao; }};
  const resultado = {};
  const form = {elements: {codigo: {value: 'codigo-ficticio'}, csrf_token: {value: 'csrf-ficticio'},
    forma: {value: 'PIX_CHAVE'}, valor: {value: '100,00'}, vencimento: {value: '2026-11-09'}}};
  const leitor = {dataset: {url: '/administrativo/despesas/ler-codigo'}, closest: () => form,
    querySelector: (seletor) => ({'[data-ler-codigo]': botao, '[data-usar-codigo]': usar,
      '[data-resultado-codigo]': resultado})[seletor]};
  vm.runInNewContext(script, {document: {querySelectorAll: () => [leitor]}, fetch, URLSearchParams});
  return {botao, usar, resultado, form};
}

test('ler nao altera o formulario; somente o clique explicito preenche os dados', async () => {
  const t = tela(async (url, pedido) => {
    assert.equal(url, '/administrativo/despesas/ler-codigo');
    assert.equal(pedido.method, 'POST');
    assert.equal(pedido.body.get('csrf_token'), 'csrf-ficticio');
    return {ok: true, json: async () => leitura};
  });
  await t.botao.click();
  assert.equal(t.form.elements.valor.value, '100,00');
  assert.equal(t.usar.hidden, false);
  t.usar.click();
  assert.equal(t.form.elements.valor.value, '123,45');
  assert.equal(t.form.elements.vencimento.value, '2026-11-10');
});

test('codigo alterado enquanto a leitura esta pendente invalida a resposta', async () => {
  let responder;
  const t = tela(() => new Promise((r) => { responder = r; }));
  const pendente = t.botao.click();
  t.form.elements.codigo.value = 'outro-codigo';
  responder({ok: true, json: async () => leitura});
  await pendente;
  assert.equal(t.usar.hidden, true);
  assert.match(t.resultado.textContent, /código mudou/);
  assert.equal(t.form.elements.valor.value, '100,00');
});

test('pix sem valor embutido preserva o valor digitado e nao inventa vencimento', async () => {
  const t = tela(async () => ({ok: true, json: async () => ({...leitura,
    forma: 'PIX_COPIA_E_COLA', valor: '', vencimento: ''})}));
  await t.botao.click(); t.usar.click();
  assert.equal(t.form.elements.forma.value, 'PIX_COPIA_E_COLA');
  assert.equal(t.form.elements.valor.value, '100,00');
  assert.equal(t.form.elements.vencimento.value, '2026-11-09');
});

test('sessao expirada impede aplicar dados e libera o botao para nova leitura', async () => {
  const t = tela(async () => ({redirected: true}));
  await t.botao.click();
  assert.match(t.resultado.textContent, /sessão expirou/);
  assert.equal(t.usar.hidden, true);
  assert.equal(t.botao.disabled, false);
});
