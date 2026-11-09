"""Contrato das guias e barreiras financeiras, sem rede e sem banco real."""
import unittest
from contextlib import nullcontext
from datetime import datetime
from unittest.mock import Mock, patch

import despesas as DP
import despesas_inter as INTER
import despesas_portal_selo as PS


def dv(s):
    soma = 0
    for i, c in enumerate(reversed(s)):
        n = int(c) * (2 if i % 2 == 0 else 1)
        soma += n // 10 + n % 10
    return str(-soma % 10)


def codigo(valor=12345):
    sem = '816' + f'{valor:011d}' + '0' * 29
    barras = sem[:3] + dv(sem) + sem[3:]
    return ' '.join(barras[i:i+11] + '-' + dv(barras[i:i+11]) for i in range(0, 44, 11))


def texto(fundo='FERJ'):
    return ('Guia de Arrecação do Tribunal de Justiça do Maranhão\n'
            '26.000.000.000.000.001-0\n10/11/2026\n09/11/2026\n'
            f'Fundo de Cidade Exemplo - {fundo}\n00.000.010/0001-27\nR$ 123,45\n'
            f'Referente à {fundo}\nPeríodo de apuração: 01/10/2026 a 31/10/2026\n{codigo()}')


class Guias(unittest.TestCase):
    def test_campos_e_codigo_coerentes(self):
        g = PS.ler_texto(texto())
        self.assertEqual((g['fundo'], g['valor_centavos'], g['inicio'], g['fim'], g['vencimento']),
                         ('FERJ', 12345, '2026-10-01', '2026-10-31', '2026-11-10'))

    def test_recusa_valor_ou_fundo_ambiguo_e_codigo_alterado(self):
        for s in [texto().replace('123,45', '123,46'), texto() + '\nReferente à FERC',
                  texto().replace('Guia de Arrecação', 'Outro documento'),
                  texto() + '\n26.000.000.000.000.002-0',
                  texto().replace(codigo(), codigo()[:-1] + ('1' if codigo()[-1] != '1' else '2'))]:
            with self.subTest(texto=s[-20:]), self.assertRaises(DP.DespesaError):
                PS.ler_texto(s)

    def test_esperado_e_calculado_no_servidor_e_falta_de_base_nao_vira_zero(self):
        g = PS.ler_texto(texto())
        receita = {'dia': '2026-10-02', 'tipo': PS.LD.NORMAL, 'sem_valor': False, 'fundos': {'FERJ': 100}}
        with patch.object(PS.LD, 'receitas_do_mes', return_value=[receita]):
            self.assertEqual(PS.esperado_dos_selos(None, g), 100)
        with patch.object(PS.LD, 'receitas_do_mes', return_value=[]):
            self.assertIsNone(PS.esperado_dos_selos(None, g))
        with patch.object(PS.LD, 'receitas_do_mes', return_value=[{**receita, 'sem_valor': True}]):
            self.assertIsNone(PS.esperado_dos_selos(None, g))

    def test_regra_so_autoriza_ferj_e_ferc(self):
        for fundo in PS.FUNDOS:
            bd = Mock()
            bd.um.return_value = None
            bd.escrever.return_value = [{'id': 1}]
            with self.subTest(fundo=fundo), patch.object(DP, 'banco', return_value=bd), \
                    patch.object(DP, 'configuracao', return_value=DP.PADRAO), patch.object(DP, '_evento'):
                DP.cadastrar(None, agora=datetime(2026, 11, 9), por='automação',
                             origem=DP.ORIGEM_PORTAL_SELO, chave_origem='guia-ficticia',
                             beneficiario_nome='Fundo de Cidade Exemplo', beneficiario_documento='00000010000127',
                             valor_centavos=12345, valor_esperado_centavos=12345, vencimento='2026-11-10',
                             forma=DP.ARRECADACAO, codigo=codigo(), descricao='Guia fictícia de outubro',
                             categoria='FUNDO_' + fundo, documento_especie='Guia')
                params = bd.escrever.call_args.args[1]
                self.assertEqual(params[0], DP.AUTORIZADA if fundo in ('FERJ', 'FERC') else DP.AGUARDANDO)

    def test_inter_nao_envia_fundos_do_bb_mesmo_se_ja_estiverem_autorizados(self):
        for categoria in DP.FUNDOS_SOMENTE_BANCO_DO_BRASIL:
            db = Mock()
            db.transaction.return_value = nullcontext(object())
            cliente = Mock(ambiente='sandbox')
            with self.subTest(categoria=categoria), patch.object(INTER, 'banco'), \
                    patch.object(DP, '_prender', return_value={'situacao': DP.AUTORIZADA, 'categoria': categoria}), \
                    patch.object(DP, 'configuracao', return_value={**DP.PADRAO, 'despesas_pagamento_ligado': '1'}), \
                    patch.object(INTER, '_enviar') as enviar:
                r = INTER.pagar(db, 1, cliente=cliente, por='automação')
                self.assertIn('Banco do Brasil', r['mensagem'])
                enviar.assert_not_called()

    def test_retomada_reconhece_cadastro_manual_sem_elevar_autorizacao(self):
        bd = Mock()
        g = {'fundo': 'FERJ', 'existente': {'id': 3, 'situacao': DP.AGUARDANDO}}
        with patch.object(PS, 'banco', return_value=bd), patch.object(PS, 'conferir', return_value=g), \
                patch.object(DP, 'cadastrar') as cadastrar:
            r = PS.importar(None, b'%PDF', agora=datetime(2026, 11, 9), por='automação', pasta=None, usuario_id=None)
            self.assertFalse(r['novo'])
            self.assertEqual(r['situacao'], DP.AGUARDANDO)
            cadastrar.assert_not_called()


if __name__ == '__main__':
    unittest.main()
