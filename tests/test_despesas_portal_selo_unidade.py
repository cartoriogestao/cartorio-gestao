"""Contrato das guias e barreiras financeiras, sem rede e sem banco real."""
import unittest
from functools import lru_cache
from contextlib import nullcontext
from datetime import date, datetime
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


# Recebedor fictício do Pix dos fundos (o CNPJ de teste dos favorecidos).
CHAVE_DO_FUNDO = '00000010000127'
DOMINIO_DO_QR = 'qrpix.banco-exemplo.test'
PADRAO = 'padrão'


def pix(valor=12345, chave=CHAVE_DO_FUNDO, url=None):
    """Pix copia e cola fictício, com CRC válido (estático com chave, ou dinâmico com URL)."""
    def tlv(campo, v):
        return f'{campo}{len(v):02d}{v}'
    conta = tlv('00', 'br.gov.bcb.pix') + (tlv('25', url) if url else tlv('01', chave))
    corpo = (tlv('00', '01') + tlv('26', conta) + tlv('52', '0000') + tlv('53', '986')
             + (tlv('54', f'{valor / 100:.2f}') if valor is not None else '')
             + tlv('58', 'BR') + tlv('59', 'FUNDO EXEMPLO') + tlv('60', 'CIDADE EXEMPLO')
             + tlv('62', tlv('05', '***')) + '6304')
    return corpo + DP._crc16(corpo.encode())


@lru_cache(maxsize=32)
def pdf_original(fundo='FERJ', qr=PADRAO, *qrs):
    """A guia fictícia; FERJ e FERC trazem o QR code do Pix, como imagem (o leitor o lê
    pela câmera virtual, e não pelo texto). `qr=None` tira o QR; `qrs` põe outros."""
    import fitz
    import io
    import segno
    if qr == PADRAO:
        qr = pix() if fundo in ('FERJ', 'FERC') else None
    with fitz.open() as documento:
        pagina = documento.new_page()
        pagina.insert_text((40, 40), texto(fundo), fontsize=10)
        for i, conteudo in enumerate(q for q in (qr, *qrs) if q):
            png = io.BytesIO()
            segno.make(conteudo, error='m').save(png, kind='png', scale=3, border=4)
            pagina.insert_image(fitz.Rect(380, 40 + 200 * i, 560, 220 + 200 * i), stream=png.getvalue())
        return documento.tobytes()


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

    def _situacao_do_cadastro(self, fundo, forma, codigo_pago, cfg):
        bd = Mock()
        bd.um.return_value = None
        bd.escrever.return_value = [{'id': 1}]
        with patch.object(DP, 'banco', return_value=bd), \
                patch.object(DP, 'configuracao', return_value=cfg), patch.object(DP, '_evento'):
            DP.cadastrar(None, agora=datetime(2026, 11, 9), por='automação',
                         origem=DP.ORIGEM_PORTAL_SELO, chave_origem='guia-ficticia',
                         beneficiario_nome='Fundo de Cidade Exemplo', beneficiario_documento='00000010000127',
                         valor_centavos=12345, valor_esperado_centavos=12345, vencimento='2026-11-10',
                         forma=forma, codigo=codigo_pago, descricao='Guia fictícia de outubro',
                         categoria='FUNDO_' + fundo, documento_especie='Guia')
        return bd.escrever.call_args.args[1][0]

    def test_regra_so_autoriza_ferj_e_ferc_pelo_pix_do_recebedor_conferido(self):
        cfg = {**DP.PADRAO, 'despesas_pix_ferj': CHAVE_DO_FUNDO, 'despesas_pix_ferc': CHAVE_DO_FUNDO}
        for fundo in PS.FUNDOS:
            with self.subTest(fundo=fundo):
                self.assertEqual(self._situacao_do_cadastro(fundo, DP.PIX_COPIA_E_COLA, pix(), cfg),
                                 DP.AUTORIZADA if fundo in ('FERJ', 'FERC') else DP.AGUARDANDO)
                # O código de barras não sai mais sozinho: espera o oficial.
                self.assertEqual(self._situacao_do_cadastro(fundo, DP.ARRECADACAO, codigo(), cfg), DP.AGUARDANDO)
        for outro in ({**cfg, 'despesas_pix_ferj': ''}, {**cfg, 'despesas_pix_ferj': '+5599985274255'}):
            with self.subTest(cfg=outro['despesas_pix_ferj']):
                self.assertEqual(self._situacao_do_cadastro('FERJ', DP.PIX_COPIA_E_COLA, pix(), outro),
                                 DP.AGUARDANDO)

    def test_recebedor_do_pix_por_chave_ou_dominio(self):
        cfg = {'despesas_pix_ferj': CHAVE_DO_FUNDO, 'despesas_pix_ferc': DOMINIO_DO_QR}
        dinamico = pix(valor=None, url=DOMINIO_DO_QR + '/cobv/abc123')
        self.assertEqual(DP.pix_do_fundo_confere(cfg, 'FUNDO_FERJ', pix()), '')
        self.assertEqual(DP.pix_do_fundo_confere(cfg, 'FUNDO_FERC', dinamico), '')
        self.assertEqual(DP.pix_do_fundo_confere(cfg, 'FUNDO_FERC', pix(valor=None, url='https://' + DOMINIO_DO_QR + ':443/x')), '')
        for categoria, payload in (('FUNDO_FERJ', pix(chave='fundo@outro.test')),
                                   ('FUNDO_FERJ', dinamico),
                                   ('FUNDO_FERC', pix(valor=None, url='qrpix.banco-exemplo.test.golpe.test/cobv/1')),
                                   ('FUNDO_FERC', pix()),
                                   ('FUNDO_FADEP', pix()),
                                   ('FUNDO_FERJ', pix()[:-1] + '0')):
            with self.subTest(categoria=categoria, payload=payload[-30:]):
                self.assertTrue(DP.pix_do_fundo_confere(cfg, categoria, payload))
        self.assertIn('Falta conferir', DP.pix_do_fundo_confere({}, 'FUNDO_FERJ', pix()))

    def test_recebedor_configurado_normaliza_chave_e_dominio(self):
        self.assertEqual(DP.recebedor_pix_configurado(' 00.000.010/0001-27 '), CHAVE_DO_FUNDO)
        self.assertEqual(DP.recebedor_pix_configurado('QRPix.Banco-Exemplo.test'), DOMINIO_DO_QR)
        self.assertEqual(DP.recebedor_pix_configurado('Fundo@Exemplo.test'), 'fundo@exemplo.test')
        self.assertEqual(DP.recebedor_pix_configurado(''), '')
        with self.assertRaises(DP.DespesaError):
            DP.recebedor_pix_configurado('00.000.010/0001-28')

    def test_qr_da_guia(self):
        hoje = date(2026, 11, 9)
        self.assertEqual(PS.ler_pix(pdf_original('FERJ'), hoje=hoje), pix())
        self.assertIsNone(PS.ler_pix(pdf_original('FERJ', None), hoje=hoje))
        self.assertIsNone(PS.ler_pix(pdf_original('FADEP'), hoje=hoje))
        with self.assertRaises(DP.DespesaError):
            PS.ler_pix(pdf_original('FERJ', pix(), pix(chave='fundo@outro.test')), hoje=hoje)

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
                patch.object(DP, 'cadastrar') as cadastrar, \
                patch.object(DP, 'anexos', return_value=[]), patch.object(DP, 'guardar_anexo') as guardar:
            r = PS.importar(None, b'%PDF', agora=datetime(2026, 11, 9), por='automação', pasta=None, usuario_id=None)
            self.assertFalse(r['novo'])
            self.assertEqual(r['situacao'], DP.AGUARDANDO)
            cadastrar.assert_not_called()
            guardar.assert_called_once()


if __name__ == '__main__':
    unittest.main()
