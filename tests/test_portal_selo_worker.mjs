import test from 'node:test';
import assert from 'node:assert/strict';
import { centavos, periodo, confereLinha, janelaSegunda } from '../tools/portal_selo_worker.mjs';

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
