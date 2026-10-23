"""OS MODELOS DO REGISTRO DE IMÓVEIS ABARCAM O QUE A LEI EXIGE — LT03, 20/10/2026.

O PEDIDO DO OFICIAL (20/10/2026): «os modelos têm de abarcar o que a LEI e as
NORMAS exigem». A fonte, nesta ordem de prevalência: a Lei 6.015/1973 (LRP),
o Código Nacional de Normas (Prov. CNJ 149/2023, «CNN») e o Código de Normas
Extrajudicial do MA (Prov. COGEX 28/2026, «CN-MA»). Os textos estão em
`migracao-pg/referencia/` (o do MA) e `referencia/normas/` (LRP compilada e
CNN, baixados do Planalto e do CNJ em 20/10/2026).

COMO ESTE ARQUIVO MEDE
    `MATRIZ` é a matriz desta atribuição — a mesma que está escrita em
    `docs/REQUISITOS_LEGAIS.md`, seção do Registro de Imóveis: para cada papel
    e cada elemento obrigatório, o artigo que o exige, o CAMPO que o modelo
    precisa ter e o que o papel montado precisa dizer (o rótulo e o valor).

    Três conferências, uma por teste:
      1. o padrão da casa (`modelos_padrao/ri/*.txt`) tem o campo;
      2. o papel montado com um contexto de ensaio COMPLETO (sem dado de
         ninguém) diz o rótulo e o valor — o termo e a certidão de cada tipo;
      3. a matriz do código é a do documento, e vice-versa.

    E uma quarta, para os 25 modelos de ato (`ri_modelos_atos`), que moram no
    código e não na pasta: cada registro tem as partes, a forma do título e o
    valor do art. 176, § 1º, III; cada averbação, o rótulo e o protocolo.

    Elemento que o modelo não tem é DEFEITO: o que se consertou aqui está
    explicado no próprio elemento; o que ficou para a casa decidir está
    `xfail(strict=True)` com o artigo.
"""
from __future__ import annotations

import json
import re
import sys
from collections import namedtuple
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as MOD  # noqa: E402
import ri_modelos_atos as MODELOS_DE_ATO  # noqa: E402

DOC = RAIZ / "docs" / "REQUISITOS_LEGAIS.md"

R = namedtuple("R", "papel ato elemento artigo campo diz defeito")


def r(papel, ato, elemento, artigo, campo, *diz, defeito=None):
    """Um elemento obrigatório: onde mora, quem exige e o que o papel diz."""
    return R(papel, ato, elemento, artigo, campo, tuple(diz), defeito)


# ------------------------------------------------ o contexto de ensaio

CONFRONTACOES = ("frente para a Rua Exemplo, 12,00 m; fundos com o lote 31; "
                 "lados com os lotes 28 e 32")
QUALIFICACAO = ("brasileiro, solteiro, lavrador, residente e domiciliado na Rua "
                "Exemplo, 10, Centro, Cidade Exemplo/MA")
TEOR_R1 = ("R-01/4100 — COMPRA E VENDA. Pela escritura pública lavrada em 02 de "
           "outubro de 2026, no Livro 12-N, folhas 45 a 47, do Tabelionato de Notas "
           "de Cidade Exemplo/MA, PEDRO EXEMPLO DOS SANTOS, " + QUALIFICACAO
           + ", CPF 000.000.001-91, vendeu a BEATRIZ EXEMPLO DE SOUZA o imóvel "
           "desta matrícula pelo preço de R$ 100.000,00 (cem mil reais).")
TEOR_R2 = ("R-02/4100 — HIPOTECA de primeiro grau em favor de BANCO EXEMPLO S.A., "
           "para garantia da dívida de R$ 80.000,00 (oitenta mil reais).")
FECHO = "Cidade Exemplo/MA, 20 de outubro de 2026. Dou fé. A Escrevente Autorizada (CARLA EXEMPLO)."
SELO_ATO = "SELO DE REGISTRO REGAVD000000TESTE00000000003 Emol R$ 1636,01"
SELO_ABERTURA = "SELO DE ABERTURA MATRIC000000TESTE00000000002 Emol R$ 91,20"

SERVENTIA = {"nome": "Ofício Único de Cidade Exemplo/MA", "cns": "000000",
             "cidade": "Cidade Exemplo", "uf": "MA",
             "registrador": "Mario Exemplo dos Santos",
             "substituta": "Beatriz Exemplo de Souza",
             "titulo_registrador": "Tabelião Registrador",
             "titulo_substituta": "Tabeliã Registradora Substituta",
             "unit_name": "Ofício Único de Cidade Exemplo/MA"}
MATRICULA = {"numero": "4100", "livro": "2", "folha": "1", "cnm": "000000.2.0004100-49",
             "tipo_ficha": "ESTRUTURADA", "logradouro": "Rua Exemplo",
             "numero_predial": "30", "bairro": "Centro", "cidade": "Cidade Exemplo",
             "uf": "MA", "area_valor": "360,00", "area_unidade": "m2",
             "confrontacoes": CONFRONTACOES, "descricao_perimetro": None,
             "registro_anterior": "Matrícula 3.900 deste Ofício, de 10/01/2000",
             "inscricao_municipal": "01.02.003.0004", "ccir": "950.000.000.000-0",
             "cib": "12345678", "teor": None}
DONO = {"nome": "PEDRO EXEMPLO DOS SANTOS", "qualificacao": QUALIFICACAO,
        "documento_tipo": "CPF", "documento_numero": "000.000.001-91"}
COMPRADORA = {"nome": "BEATRIZ EXEMPLO DE SOUZA", "qualificacao": "brasileira, solteira",
              "documento_tipo": "CPF", "documento_numero": "000.000.002-72"}
ATO_R1 = {"rotulo": "R-01/4100", "tipo": "R", "numero": 1,
          "natureza_titulo": "Compra e venda", "protocolo": "11570",
          "protocolo_cab": "11.570", "protocolo_data_cab": "20 DE OUTUBRO DE 2026",
          "data_ato": "2026-10-20", "data_extenso": "20 de outubro de 2026",
          "teor": TEOR_R1, "teor_odf": f"<p>{TEOR_R1}</p>",
          "teor_certidao_odf": f"<p>{TEOR_R1}</p>", "fecho": FECHO,
          "selo_odf": f"<p>{SELO_ATO}</p>", "cancelado": 0}
ATO_R2_CANCELADO = {**ATO_R1, "rotulo": "R-02/4100", "numero": 2,
                    "natureza_titulo": "Hipoteca", "teor": TEOR_R2,
                    "teor_odf": f"<p>{TEOR_R2}</p>",
                    "teor_certidao_odf": f"<p>{TEOR_R2}</p>", "cancelado": 1}
CLAUSULA = ("<p>CERTIFICO ainda que, nesta data, há título prenotado em aberto "
            "referente a esta matrícula: Protocolo nº 11.571.</p>")

FICHA = {"m": MATRICULA, "serventia": SERVENTIA, "data_abertura_br": "20/10/2026",
         "uf_extenso": "Maranhão", "protocolo_atual": "11.570",
         "proprietarios": [COMPRADORA], "proprietarios_abertura": [DONO],
         "abertura_fecho": "Cidade Exemplo/MA, 20 de outubro de 2026. O referido é verdade e dou fé.",
         "abertura_assinatura": "CARLA EXEMPLO, Escrevente Autorizada.",
         "selo_abertura_odf": f"<p>{SELO_ABERTURA}</p>", "teor_odf": "",
         "separador": "<p>* * *</p>", "atos": [ATO_R1, ATO_R2_CANCELADO]}

CERTIDAO = {**FICHA, "atos": [ATO_R1], "requerente": "BEATRIZ EXEMPLO DE SOUZA",
            "requerente_documento": "000.000.002-72",
            "finalidade": "Para fins de financiamento",
            "hoje_extenso": "20 de outubro de 2026",
            "clausula_prenotacoes_abertas": CLAUSULA,
            "resultado_onus": "POSITIVA", "resultado_acoes": "NEGATIVA",
            "itens_onus": [{"rotulo": "R-02/4100", "natureza": "Hipoteca",
                            "data_extenso": "20 de outubro de 2026", "texto": TEOR_R2}],
            "itens_acoes": [],
            "cadeia_matriculas": [{"numero": "4100", "papel": "atual",
                                   "registro_anterior": "", "atos": [ATO_R1]}],
            "anos_periodo": 20, "desde_periodo": "20/10/2006",
            "ate_periodo": "20/10/2026", "dominio_periodo": [ATO_R1],
            "onus_periodo": [{"rotulo": "R-02/4100", "natureza_titulo": "Hipoteca",
                              "data_extenso": "20 de outubro de 2026"}]}
NEGATIVA = {"serventia": SERVENTIA, "requerente": "BEATRIZ EXEMPLO DE SOUZA",
            "requerente_documento": "000.000.002-72",
            "criterio_rotulo": "pelo imóvel «Avenida Inexistente, 999»",
            "pesquisado": "", "pesquisado_documento": "",
            "imovel_busca": "Avenida Inexistente, 999",
            "finalidade": "Para fins de financiamento", "protocolo": "2026.10.3",
            "hoje_extenso": "20 de outubro de 2026", "hora_emissao": "10:15",
            "lavrou_nome": "CARLA EXEMPLO", "lavrou_funcao": "Escrevente Autorizada"}
NEGATIVA_PESSOA = {**NEGATIVA, "criterio_rotulo": "pelo nome «JOÃO INEXISTENTE»",
                   "pesquisado": "JOÃO INEXISTENTE", "imovel_busca": ""}
NOTA = {"serventia": SERVENTIA, "hoje_extenso": "20 de outubro de 2026",
        "nota": {"numero": 1, "prazo_ate": "17/11/2026",
                 "fundamentacao": "Lei 6.015/1973, arts. 198 e 221; CN-MA art. 41."},
        "protocolo": {"numero": 11570, "data_prenotacao": "20/10/2026",
                      "apresentante": "BEATRIZ EXEMPLO DE SOUZA",
                      "apresentante_documento": "000.000.002-72",
                      "matricula_numero": "4100",
                      "objeto": "Imóvel urbano na Rua Exemplo, 30"},
        "exigencias_odf": ("<p><b>1.</b> Apresentar a certidão negativa de débitos "
                           "municipais (CN-MA art. 475).</p><p><b>2.</b> Reconhecer "
                           "a firma do vendedor (CC, art. 221).</p>")}
PRENOTACAO = {"sv": {"unit_name": "Ofício Único de Cidade Exemplo/MA",
                     "serventia_titulo": "Tabelião e Oficial de Registro",
                     "serventia_titular": "Mario Exemplo dos Santos",
                     "serventia_cnpj": "00.000.001/0000-55", "ri_cns": "000000",
                     "serventia_telefone": "(99) 3000-0000",
                     "endereco_completo": "Rua Exemplo, 100, Centro, Cidade Exemplo-MA",
                     "cidade_uf": "Cidade Exemplo/MA"},
              "p": {"numero": 77, "apresentante": "PEDRO EXEMPLO DOS SANTOS",
                    "natureza_titulo": "Escritura pública de compra e venda",
                    "documento_descricao": "Traslado da escritura",
                    "objeto": "Imóvel urbano na Rua Exemplo, 30",
                    "matricula_numero": "4100", "hora": "09:30:00", "livro_destino": "2"},
              "documento": "000.***.***-91", "telefone": "(99) 9****-0000", "email": "",
              "data": "20/10/2026", "limite": "17/11/2026", "faltam": 20, "prazo": 20,
              "hoje_extenso": "20 de outubro de 2026", "emitido_por": "CARLA EXEMPLO",
              "funcao": "Escrevente Autorizada"}
FECHO_DO_ATO = {"cidade": "Cidade Exemplo", "uf": "MA",
                "data_extenso": "20 de outubro de 2026", "artigo": "A",
                "titulo": "Escrevente Autorizada", "nome": "CARLA EXEMPLO"}
CABECALHO = {"m": MATRICULA, "serventia": SERVENTIA, "ficha_numero": "1",
             "livro_ficha": "2", "usuario_impressao": "CARLA EXEMPLO"}
LIVRO3 = {"numero": "12", "natureza": "PACTO ANTENUPCIAL", "situacao": "ATIVO",
          "titulo_tipo": "Escritura pública de pacto antenupcial",
          "titulo_numero": "Livro 12-N, folhas 50 a 52", "prenotacao": "11572",
          "valor": "—", "partes": "  PEDRO EXEMPLO DOS SANTOS — OUTORGANTE (00000000191)",
          "teor": "Os nubentes adotaram o regime da SEPARAÇÃO TOTAL DE BENS.",
          "atos": "  (nenhum ato posterior informado)", "folha": "", "data_titulo": "01/10/2026",
          "parcelas": "—", "vencimento_inicial": "—", "vencimento": "—", "juros": "—",
          "cnm": "000000.3.0000012-11", "garantia": "  —", "condicoes": "  —",
          "impresso_em": "20/10/2026 10:15",
          "_atos_ficha": "  R-1 – 20/10/2026 – selo REGTOR000000TESTE00000000009"}
# O R-1 do Livro 3 como a lavratura o grava depois do LH13: a data com a hora
# (`db.now()`) e quem estava logado, congelado no ato.
ATO_DO_LIVRO3 = {"tipo": "R", "numero": 1, "data_ato": "2026-10-20T10:15:00",
                 "teor": LIVRO3["teor"], "lavrado_nome": "CARLA EXEMPLO",
                 "lavrado_titulo": "Escrevente Autorizada", "lavrado_tratamento": "A"}
LIVRO3_FECHO = {"finalidade": "Para fins de financiamento", "valida_ate": "19/11/2026",
                "quando": "20 de outubro de 2026", "cidade": "Cidade Exemplo", "uf": "MA",
                "quem": "CARLA EXEMPLO", "funcao": "Escrevente Autorizada", "numero": 5,
                "ano": 2026, "emitida_em": "20/10/2026 10:15",
                "hash_certidao": "0123456789abcdef"}

# -------------------------------------------------------------- A MATRIZ

PRE = "Prenotação — comprovante do Livro 1"
ABE = "Matrícula — termo de abertura (Livro 2)"
ATO = "Registro (R) e averbação (AV) — termo na matrícula"
FEC = "Fecho do registro e da averbação"
CAB = "Timbre da ficha da matrícula"
CIT = "Certidão de inteiro teor da matrícula"
CON = "Certidão de ônus reais e de ações reipersecutórias"
CPR = "Certidão de propriedade"
CDO = "Certidão da cadeia dominial"
CVI = "Certidão vintenária"
CNE = "Certidão negativa (Indicadores Real e Pessoal)"
NOT = "Nota devolutiva"
L3C = "Certidão de inteiro teor do Livro 3"
L3F = "Registro no Livro 3 — a ficha"

# A VALIDADE PELO ART. 553 — LH13, «14 a» (o oficial, 21/10/2026). Era
# `xfail` (`VALIDADE_553`): os padrões citavam «art. 53 do Código de Normas da
# CGJ/TJMA», e no Código vigente (Prov. COGEX 28/2026) a validade de 30 dias da
# certidão do RI é o art. 553 — o art. 53 trata da sentença na suscitação de
# dúvida. Os quatro padrões passaram a citar o 553; as certidões já emitidas
# guardam o teor que tinham (o corpo e o hash são congelados na emissão).

MATRIZ = [
    # -- Livro 1
    r("RI_PRENOTACAO", PRE, "número de ordem", "LRP art. 175, I; art. 183", "p.numero",
      "Protocolo nº 77"),
    r("RI_PRENOTACAO", PRE, "livro de protocolo", "LRP art. 173, I", "Livro 1-A",
      "Livro 1-A de Protocolo"),
    r("RI_PRENOTACAO", PRE, "data da apresentação", "LRP art. 175, II; art. 183", "{{ data }}",
      "Prenotado em", "20/10/2026"),
    r("RI_PRENOTACAO", PRE, "hora da apresentação", "LRP art. 182; CN-MA art. 447", "p.hora",
      "às 09:30:00"),
    r("RI_PRENOTACAO", PRE, "apresentante", "LRP art. 175, III; CN-MA art. 444, IV",
      "p.apresentante", "Apresentante", "PEDRO EXEMPLO DOS SANTOS"),
    r("RI_PRENOTACAO", PRE, "natureza formal do título", "LRP art. 175, IV; CN-MA art. 444, V",
      "p.natureza_titulo", "Natureza do título", "Escritura pública de compra e venda"),
    r("RI_PRENOTACAO", PRE, "ato que o título formaliza (objeto)", "LRP art. 175, V",
      "p.objeto", "Objeto", "Imóvel urbano na Rua Exemplo, 30"),
    r("RI_PRENOTACAO", PRE, "prazo da prenotação", "LRP art. 205; CN-MA arts. 436 e 452",
      "{{ limite", "Prazo da prenotação", "17/11/2026", "20 dias úteis"),
    r("RI_PRENOTACAO", PRE, "a serventia que recebe", "CN-MA art. 443, § 2º", "sv.unit_name",
      "Ofício Único de Cidade Exemplo/MA", "CNS 000000"),
    r("RI_PRENOTACAO", PRE, "quem emitiu, com a função", "Lei 8.935/1994, arts. 20 e 21",
      "emitido_por", "CARLA EXEMPLO", "Escrevente Autorizada"),
    # -- Livro 2: a abertura
    r("RI_FICHA", ABE, "data da abertura", "LRP art. 176, § 1º, II, 2", "data_abertura_br",
      "DATA DE ABERTURA DA FICHA", "20/10/2026"),
    r("RI_FICHA", ABE, "logradouro e número", "LRP art. 176, § 1º, II, 3, b", "m.numero_predial",
      "IMÓVEL", "Rua Exemplo, nº 30"),
    r("RI_FICHA", ABE, "localização", "LRP art. 176, § 1º, II, 3", "m.bairro",
      "Centro", "Cidade Exemplo/MA"),
    r("RI_FICHA", ABE, "área", "LRP art. 176, § 1º, II, 3", "m.area_valor",
      "área de 360,00 m2"),
    r("RI_FICHA", ABE, "confrontações", "LRP art. 176, § 1º, II, 3", "m.confrontacoes",
      "CONFRONTAÇÕES", CONFRONTACOES),
    r("RI_FICHA", ABE, "designação cadastral (inscrição municipal)",
      "LRP art. 176, § 1º, II, 3, b", "m.inscricao_municipal",
      "INSCRIÇÃO MUNICIPAL", "01.02.003.0004"),
    r("RI_FICHA", ABE, "imóvel rural: código do imóvel (CIB) e CCIR",
      "LRP art. 176, § 1º, II, 3, a", "m.cib", "CIB", "12345678", "CCIR", "950.000.000.000-0"),
    r("RI_FICHA", ABE, "proprietário: nome e CPF", "LRP art. 176, § 1º, II, 4",
      "p.documento_numero", "PROPRIETÁRIO(S)", "PEDRO EXEMPLO DOS SANTOS", "000.000.001-91"),
    r("RI_FICHA", ABE, "proprietário: nacionalidade, estado civil, profissão, domicílio",
      "LRP art. 176, § 1º, II, 4; CN-MA art. 479, I", "p.qualificacao", QUALIFICACAO),
    r("RI_FICHA", ABE, "registro anterior", "LRP art. 176, § 1º, II, 5; CN-MA art. 479, III",
      "m.registro_anterior", "REGISTRO ANTERIOR", "Matrícula 3.900 deste Ofício, de 10/01/2000"),
    r("RI_FICHA", ABE, "fecho e subscrição da abertura", "CN-MA art. 458", "abertura_fecho",
      "O referido é verdade e dou fé", "CARLA EXEMPLO, Escrevente Autorizada"),
    r("RI_FICHA", ABE, "selo da abertura", "CN-MA arts. 130, § 2º, e 131", "selo_abertura_odf",
      "MATRIC000000TESTE00000000002"),
    # -- Livro 2: os atos
    r("RI_FICHA", ATO, "R-/AV- com o número de ordem e o da matrícula", "LRP art. 232",
      "a.rotulo", "R-01/4100"),
    r("RI_FICHA", ATO, "título da transmissão ou do ônus (natureza)",
      "LRP art. 176, § 1º, III, 3", "a.natureza_titulo", "COMPRA E VENDA"),
    r("RI_FICHA", ATO, "número e data do protocolo no início do ato",
      "CN-MA arts. 443, § 1º, e 458", "a.protocolo_cab",
      "PROTOCOLO Nº 11.570", "DE 20 DE OUTUBRO DE 2026"),
    r("RI_FICHA", ATO, "partes, forma do título e valor (no teor)",
      "LRP art. 176, § 1º, III, 2, 4 e 5", "a.teor_odf",
      "escritura pública lavrada em 02 de outubro de 2026", "R$ 100.000,00 (cem mil reais)"),
    r("RI_FICHA", ATO, "data e subscrição de quem praticou", "CN-MA art. 458", "a.fecho",
      FECHO),
    r("RI_FICHA", ATO, "selo do ato", "CN-MA arts. 130, § 2º, e 131", "a.selo_odf",
      "REGAVD000000TESTE00000000003"),
    r("RI_FICHA", ATO, "ato cancelado marcado, sem apagar", "LRP arts. 248 e 250",
      "a.cancelado", "(ATO CANCELADO)"),
    r("RI_FECHO_DO_ATO", FEC, "lugar e data por extenso", "CN-MA art. 458", "data_extenso",
      "Cidade Exemplo/MA, 20 de outubro de 2026"),
    r("RI_FECHO_DO_ATO", FEC, "a fé do ato", "Lei 8.935/1994, art. 3º", "Dou fé", "Dou fé"),
    r("RI_FECHO_DO_ATO", FEC, "quem subscreve, com a função",
      "CN-MA art. 458; Lei 8.935/1994, arts. 20 e 21", "{{ nome }}",
      "A Escrevente Autorizada (CARLA EXEMPLO)"),
    r("RI_CABECALHO", CAB, "a serventia e os delegatários", "Lei 8.935/1994, art. 20",
      "serventia.registrador", "OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA",
      "MARIO EXEMPLO DOS SANTOS", "Tabelião Registrador"),
    r("RI_CABECALHO", CAB, "a matrícula e o CNM no alto da ficha", "CNN arts. 330 e 331",
      "m.cnm", "MATRÍCULA Nº 4100", "CNM Nº 000000.2.0004100-49"),
    r("RI_CABECALHO", CAB, "o livro", "LRP art. 173, II", "livro_ficha",
      "LIVRO Nº 2 - REGISTRO GERAL"),
    # -- certidões da matrícula
    r("INTEIRO_TEOR", CIT, "a forma", "LRP art. 19, caput e § 1º", "tipo_certidao_nome",
      "CERTIDÃO DE INTEIRO TEOR"),
    r("INTEIRO_TEOR", CIT, "o requerente", "CN-MA art. 551", "requerente",
      "BEATRIZ EXEMPLO DE SOUZA", "000.000.002-72"),
    r("INTEIRO_TEOR", CIT, "a matrícula, o livro e o CNM", "LRP art. 18; CNN art. 330",
      "m.cnm", "MATRÍCULA Nº 4100", "Livro 2", "CNM 000000.2.0004100-49"),
    r("INTEIRO_TEOR", CIT, "a abertura da ficha estruturada, como o termo",
      "LRP art. 19, § 11", "abertura_estruturada", "Rua Exemplo, nº 30", CONFRONTACOES,
      QUALIFICACAO, "Matrícula 3.900 deste Ofício"),
    r("INTEIRO_TEOR", CIT, "o teor de cada ato", "LRP art. 19, § 11", "a.teor_certidao_odf",
      "escritura pública lavrada em 02 de outubro de 2026"),
    r("INTEIRO_TEOR", CIT, "o fecho de cada ato", "LRP art. 19, § 11; CN-MA art. 458",
      "a.fecho", FECHO),
    r("INTEIRO_TEOR", CIT, "o selo de cada ato e o da abertura", "CN-MA art. 131",
      "a.selo_odf", "REGAVD000000TESTE00000000003", "MATRIC000000TESTE00000000002"),
    r("INTEIRO_TEOR", CIT, "o encerramento do teor", "LRP art. 19", "Era o que nela continha",
      "Era o que nela continha"),
    r("INTEIRO_TEOR", CIT, "os títulos prenotados em aberto", "LRP art. 21; CN-MA art. 553, § 4º",
      "clausula_prenotacoes_abertas", "há título prenotado em aberto"),
    r("INTEIRO_TEOR", CIT, "a finalidade", "CN-MA arts. 549 e 551", "finalidade",
      "FINALIDADE", "Para fins de financiamento"),
    r("INTEIRO_TEOR", CIT, "a validade de 30 dias", "CN-MA art. 553", "30 (trinta) dias",
      "30 (trinta) dias"),
    r("INTEIRO_TEOR", CIT, "a validade com o artigo vigente", "CN-MA art. 553", "art. 553",
      "art. 553"),
    r("INTEIRO_TEOR", CIT, "a data da emissão", "LRP art. 19", "hoje_extenso",
      "Certidão emitida em 20 de outubro de 2026"),
    r("ONUS", CON, "a serventia", "Lei 8.935/1994, art. 20", "serventia.cns",
      "OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA", "CNS 000000"),
    r("ONUS", CON, "o imóvel", "LRP art. 19, § 9º", "m.logradouro", "IMÓVEL", "Rua Exemplo"),
    r("ONUS", CON, "o proprietário vigente", "LRP art. 19, § 9º", "proprietarios",
      "PROPRIETÁRIO(S) ATUAL(IS)", "BEATRIZ EXEMPLO DE SOUZA"),
    r("ONUS", CON, "os ônus: ato, natureza, data e texto", "LRP art. 19, § 9º", "itens_onus",
      "HÁ ÔNUS REAIS", "R-02/4100", "(Hipoteca)", "20 de outubro de 2026",
      "R$ 80.000,00 (oitenta mil reais)"),
    r("ONUS", CON, "as ações reais e pessoais reipersecutórias", "CN-MA art. 558",
      "resultado_acoes", "AÇÕES REAIS E PESSOAIS REIPERSECUTÓRIAS", "NÃO CONSTA"),
    r("ONUS", CON, "a validade com o artigo vigente", "CN-MA art. 553", "art. 553",
      "art. 553"),
    r("PROPRIEDADE", CPR, "o imóvel", "LRP art. 19, § 9º", "m.logradouro", "Rua Exemplo"),
    r("PROPRIEDADE", CPR, "o proprietário vigente", "LRP art. 19, § 9º", "proprietarios",
      "PROPRIETÁRIO(S) ATUAL(IS)", "BEATRIZ EXEMPLO DE SOUZA"),
    r("PROPRIEDADE", CPR, "a afirmação da propriedade", "LRP art. 19, § 9º",
      "encontra-se registrada", "encontra-se registrada em nome do(s) titular(es)"),
    r("DOMINIAL", CDO, "as transmissões em ordem, com ato, data, natureza e teor",
      "LRP art. 19; CN-MA art. 556", "cadeia_matriculas", "CADEIA DOMINIAL", "R-01/4100",
      "Compra e venda", "R$ 100.000,00 (cem mil reais)"),
    r("VINTENARIA", CVI, "o período e as transmissões e ônus nele",
      "LRP art. 19; CN-MA art. 556", "anos_periodo", "ÚLTIMOS 20 ANOS", "20/10/2006",
      "R-01/4100", "R-02/4100"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "a serventia", "Lei 8.935/1994, art. 20",
      "serventia.nome", "OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA", "CNS 000000"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "o requerente", "CN-MA arts. 549, III, e 551",
      "requerente", "BEATRIZ EXEMPLO DE SOUZA"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "o parâmetro da busca no texto",
      "CN-MA arts. 554, parágrafo único, e 557", "criterio_rotulo",
      "Avenida Inexistente, 999"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "o resultado total da busca", "CN-MA art. 555",
      "NADA CONSTA", "NADA CONSTA"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE,
      "a ressalva da matrícula ou transcrição de descrição diversa (busca pelo Indicador Real)",
      "CN-MA art. 554", "descrição diversa", "descrição diversa"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "a finalidade", "CN-MA art. 549, III", "finalidade",
      "FINALIDADE", "Para fins de financiamento"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "data e hora da emissão e validade",
      "CN-MA art. 553", "hora_emissao", "às 10:15", "30 (trinta) dias"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "quem lavrou, com a função", "LRP art. 19",
      "lavrou_nome", "CARLA EXEMPLO", "Escrevente Autorizada"),
    r("RI_CERTIDAO_NEGATIVA_IMOVEL", CNE, "a validade com o artigo vigente", "CN-MA art. 553",
      "art. 553", "art. 553"),
    # -- nota devolutiva
    r("RI_NOTA", NOT, "o número da nota", "CN-MA art. 41", "nota.numero",
      "NOTA DEVOLUTIVA Nº 1"),
    r("RI_NOTA", NOT, "o papel timbrado da serventia", "CN-MA art. 41", "serventia.nome",
      "OFÍCIO ÚNICO DE CIDADE EXEMPLO/MA", "CNS 000000"),
    r("RI_NOTA", NOT, "o título devolvido: protocolo e data", "LRP art. 198; CN-MA art. 44",
      "protocolo.numero", "PROTOCOLO Nº 11570", "20/10/2026"),
    r("RI_NOTA", NOT, "o apresentante, a matrícula e o objeto", "LRP art. 198",
      "protocolo.apresentante", "BEATRIZ EXEMPLO DE SOUZA", "MATRÍCULA", "OBJETO"),
    r("RI_NOTA", NOT, "as exigências, de uma só vez e articuladas",
      "LRP art. 198; CN-MA art. 41, § 3º", "exigencias_odf", "1.", "2."),
    r("RI_NOTA", NOT, "a fundamentação", "CN-MA art. 41, §§ 1º e 2º", "nota.fundamentacao",
      "FUNDAMENTAÇÃO", "Lei 6.015/1973, arts. 198 e 221"),
    r("RI_NOTA", NOT, "o procedimento: reapresentar no prazo, mesmo número",
      "CN-MA arts. 41, § 1º, e 44", "art. 44", "reapresentar o título", "art. 44",
      "17/11/2026"),
    r("RI_NOTA", NOT, "a ressalva da suscitação de dúvida", "LRP art. 198, VI",
      "suscitação de dúvida", "suscitação de dúvida"),
    r("RI_NOTA", NOT, "a data", "LRP art. 198", "hoje_extenso",
      "Cidade Exemplo/MA, 20 de outubro de 2026"),
    r("RI_NOTA", NOT, "identificação e assinatura do oficial ou preposto",
      "LRP art. 198; CN-MA art. 41", "serventia.substituta", "Beatriz Exemplo de Souza",
      "Tabeliã Registradora Substituta"),
    # -- Livro 3
    r("RI_LIVRO3_CERTIDAO", L3C, "o livro e o número do registro", "LRP arts. 177 e 19",
      "{numero}", "Livro 3 Auxiliar", "registro n.12"),
    r("RI_LIVRO3_CERTIDAO", L3C, "a natureza", "LRP art. 178", "{natureza}",
      "NATUREZA: PACTO ANTENUPCIAL"),
    r("RI_LIVRO3_CERTIDAO", L3C, "o título", "LRP art. 178", "{titulo_tipo}",
      "Escritura pública de pacto antenupcial"),
    r("RI_LIVRO3_CERTIDAO", L3C, "a prenotação", "CN-MA art. 443, § 1º", "{prenotacao}",
      "PRENOTAÇÃO: 11572"),
    r("RI_LIVRO3_CERTIDAO", L3C, "as partes", "LRP art. 176, § 1º, III, 2", "{partes}",
      "PEDRO EXEMPLO DOS SANTOS"),
    r("RI_LIVRO3_CERTIDAO", L3C, "o teor", "LRP art. 19, § 1º", "{teor}",
      "SEPARAÇÃO TOTAL DE BENS"),
    r("RI_LIVRO3_CERTIDAO", L3C, "os atos posteriores", "LRP art. 21", "{atos}",
      "ATOS POSTERIORES AO REGISTRO"),
    r("RI_LIVRO3_CERTIDAO_FECHO", L3C, "o encerramento, a finalidade e a validade",
      "LRP art. 19; CN-MA arts. 549 e 553", "valida_ate", "Era o que nela continha",
      "FINALIDADE", "30 (trinta) dias", "19/11/2026"),
    r("RI_LIVRO3_CERTIDAO_FECHO", L3C, "lugar, data e quem expediu", "LRP art. 19",
      "{{ quem }}", "Cidade Exemplo/MA, 20 de outubro de 2026", "CARLA EXEMPLO",
      "Escrevente Autorizada"),
    r("RI_LIVRO3_CERTIDAO_FECHO", L3C, "a autenticidade", "LRP art. 19, § 5º",
      "hash_certidao", "Autenticidade: 0123456789abcdef"),
    r("RI_LIVRO3_CERTIDAO_FECHO", L3C, "a validade com o artigo vigente", "CN-MA art. 553",
      "art. 553", "art. 553"),
    r("RI_LIVRO3_FICHA", L3F, "o número de ordem, a natureza e o título",
      "LRP arts. 177 e 178", "{natureza}", "REGISTRO Nº 12", "NATUREZA: PACTO ANTENUPCIAL",
      "Escritura pública de pacto antenupcial"),
    r("RI_LIVRO3_FICHA", L3F, "as partes e o teor", "LRP art. 178", "{teor}",
      "PEDRO EXEMPLO DOS SANTOS", "SEPARAÇÃO TOTAL DE BENS"),
    r("RI_LIVRO3_FICHA", L3F, "a prenotação e o CNM", "CN-MA art. 443, § 1º; CNN art. 330",
      "{prenotacao}", "PRENOTAÇÃO: 11572", "CNM: 000000.3.0000012-11"),
    r("RI_LIVRO3_FICHA", L3F, "cada ato com a data e o selo", "CN-MA arts. 131 e 458",
      "{atos}", "R-1 – 20/10/2026", "REGTOR000000TESTE00000000009"),
    # consertado no LH13 (21/10/2026), «15 a»: era `xfail` («decisão de
    # desenho, para o oficial») — `ra_atos` só guardava `criado_por`. Agora o
    # ato grava o nome, a função e o artigo de quem estava logado
    # (`ra_atos.lavrado_*`) e cada ato fecha como no Livro 2, dentro do claro
    # `{atos}` (`ra_ficha_odt.fecho_do_ato`, a régua do `RI_FECHO_DO_ATO`).
    r("RI_LIVRO3_FICHA", L3F, "quem praticou o ato (subscrição)", "CN-MA art. 458",
      "{atos}", "Cidade Exemplo/MA, 20 de outubro de 2026. Dou fé. "
      "A Escrevente Autorizada (CARLA EXEMPLO)."),
]

MIOLOS = {"INTEIRO_TEOR": "RI_CERTIDAO_INTEIRO_TEOR", "ONUS": "RI_CERTIDAO_ONUS",
          "PROPRIEDADE": "RI_CERTIDAO_PROPRIEDADE", "DOMINIAL": "RI_CERTIDAO_DOMINIAL",
          "VINTENARIA": "RI_CERTIDAO_VINTENARIA"}
NOMES = {"INTEIRO_TEOR": "Certidão de inteiro teor",
         "ONUS": "Certidão positiva de ônus e negativa de registro de ações reais e "
                 "pessoais reipersecutórias",
         "PROPRIEDADE": "Certidão de propriedade",
         "DOMINIAL": "Certidão dominial / cadeia dominial",
         "VINTENARIA": "Certidão vintenária (20 anos)"}


# -------------------------------------------------------------- a montagem

def _padrao(chave: str) -> str:
    """O texto de fábrica, da pasta `modelos_padrao/` — o que a casa recebe."""
    return (RAIZ / MOD.POR_CHAVE[chave]["arquivo"]).read_bytes().decode("utf-8")


def _jinja(corpo: str, contexto: dict) -> str:
    from jinja2.sandbox import SandboxedEnvironment
    return SandboxedEnvironment(autoescape=False).from_string(corpo).render(**contexto)


def _sem_tags(html: str) -> str:
    from html import unescape
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", html)).split())


def _montado(papel: str) -> str:
    """O papel montado com o contexto de ensaio completo, em texto corrido."""
    if papel in MIOLOS:
        contexto = dict(CERTIDAO)
        miolo = _jinja(_padrao(MIOLOS[papel]), contexto)
        return _sem_tags(_jinja(_padrao("RI_CERTIDAO"), contexto | {
            "tipo_certidao": papel, "tipo_certidao_nome": NOMES[papel],
            "miolo_do_tipo": miolo}))
    if papel == "RI_LIVRO3_CERTIDAO":
        return " ".join(_padrao(papel).format(**LIVRO3).split())
    if papel == "RI_LIVRO3_FICHA":
        # o fecho do ato pela regra da ficha, com as frases da pasta (o mesmo
        # «lido» que a ficha passa, sem banco)
        import ra_ficha_odt
        lido = {c: _padrao(c) for c in ("RI_FECHO_DO_ATO", "RI_FECHO_DO_ATO_SEM_TITULO")}
        fecho = ra_ficha_odt.fecho_do_ato(ATO_DO_LIVRO3, cidade="Cidade Exemplo",
                                          uf="MA", lido=lido)
        claros = LIVRO3 | {"atos": LIVRO3["_atos_ficha"] + "\n  " + fecho}
        try:
            return " ".join(_padrao(papel).format(**claros).split())
        except KeyError as erro:
            return f"(o modelo pede um claro que o código não preenche: {erro})"
    contexto = {"RI_PRENOTACAO": PRENOTACAO, "RI_FICHA": FICHA,
                "RI_FECHO_DO_ATO": FECHO_DO_ATO, "RI_CABECALHO": CABECALHO,
                "RI_CERTIDAO_NEGATIVA_IMOVEL": NEGATIVA, "RI_NOTA": NOTA,
                "RI_LIVRO3_CERTIDAO_FECHO": LIVRO3_FECHO}[papel]
    return _sem_tags(_jinja(_padrao(papel), contexto))


def _onde_mora(papel: str) -> str:
    """O texto em que o campo tem de estar: o padrão do papel (e, nas
    certidões da matrícula, o molde junto com o miolo do tipo)."""
    if papel in MIOLOS:
        return _padrao("RI_CERTIDAO") + _padrao(MIOLOS[papel])
    return _padrao(papel)


def _ids(req: R) -> str:
    return f"{req.papel}:{req.elemento}"


def _parametros():
    for req in MATRIZ:
        marcas = ([pytest.mark.xfail(strict=True, reason=req.defeito)]
                  if req.defeito else [])
        yield pytest.param(req, id=_ids(req), marks=marcas)


# -------------------------------------------------------------- os testes

@pytest.mark.parametrize("req", list(_parametros()))
def test_o_modelo_da_casa_tem_o_campo_do_elemento_obrigatorio(req):
    """O padrão da pasta tem o campo que leva o elemento ao papel."""
    assert req.campo in _onde_mora(req.papel), (
        f"{req.ato}: o modelo {req.papel} não tem «{req.campo}» — sem ele o "
        f"papel não diz «{req.elemento}» ({req.artigo})")


@pytest.mark.parametrize("req", list(_parametros()))
def test_o_papel_montado_diz_o_rotulo_e_o_valor_do_elemento(req):
    """Com um contexto de ensaio completo, o papel diz o que a lei exige."""
    papel = _montado(req.papel)
    faltam = [d for d in req.diz if d not in papel]
    assert not faltam, (f"{req.ato} — {req.elemento} ({req.artigo}): o papel não diz "
                        f"{faltam}\n--- o papel montado ---\n{papel}")


def test_nenhum_papel_montado_sobra_claro_none_ou_modelo_cru():
    """O papel montado não traz «None», `{{ }}` nem claro do formato CHAVES."""
    for papel in sorted({req.papel for req in MATRIZ}):
        texto = _montado(papel)
        for sobra in ("None", "{{", "}}", "{%", "%}"):
            assert sobra not in texto, f"{papel}: sobrou «{sobra}»"
        assert not re.search(r"\{[a-z_]+\}", texto), f"{papel}: sobrou um claro {texto}"


def _secao_do_ri() -> str:
    texto = DOC.read_text(encoding="utf-8")
    inicio = texto.find("## Registro de Imóveis")
    assert inicio >= 0, "docs/REQUISITOS_LEGAIS.md não tem a seção do Registro de Imóveis"
    fim = texto.find("\n## ", inicio + 5)
    return texto[inicio:fim if fim > 0 else len(texto)]


def test_a_matriz_do_codigo_e_a_do_documento():
    """O que o teste mede está escrito para o oficial ler — com o artigo."""
    secao = _secao_do_ri()
    faltam = [f"{req.ato} — {req.elemento} — {req.artigo}" for req in MATRIZ
              if req.elemento not in secao or req.artigo not in secao]
    assert not faltam, "a matriz do documento não traz:\n  " + "\n  ".join(faltam)


# ------------------------------------------- os 25 modelos de ato da casa

FORMA_DO_TITULO = re.compile(
    r"(escritura|carta|formal|c[eé]dula|contrato|t[ií]tulo|sentenca|ata notarial|"
    r"instrumento|testamento)", re.I)


@pytest.mark.parametrize("codigo", [m["codigo"] for m in MODELOS_DE_ATO.MODELOS
                                    if m["tipo"] == "R"])
def test_cada_modelo_de_registro_tem_o_que_o_art_176_III_exige(codigo):
    """LRP art. 176, § 1º, III: as partes (2), o título (3), a forma do título
    e a procedência (4), o valor (5) — a data e a subscrição vêm do fecho do
    ato (`RI_FECHO_DO_ATO`), e o protocolo da frase do protocolo (CN-MA art.
    458). O rótulo é o do art. 232."""
    corpo = MODELOS_DE_ATO.por_codigo(codigo)["corpo"]
    faltam = [nome for nome, achou in (
        ("o rótulo (art. 232)", "{{ rotulo }}" in corpo),
        ("o protocolo (CN-MA art. 458)", "{{ protocolo_frase }}" in corpo),
        ("as partes (III, 2)", "{{ adquirentes }}" in corpo
         or "{{ proprietarios_frase }}" in corpo),
        ("a forma do título (III, 4)", bool(FORMA_DO_TITULO.search(corpo))),
        ("o valor (III, 5)", bool(re.search(r"\[[^\]]*(VALOR|PRECO)[^\]]*\]", corpo))),
    ) if not achou]
    assert not faltam, f"{codigo} não tem: {faltam}"


@pytest.mark.parametrize("codigo", [m["codigo"] for m in MODELOS_DE_ATO.MODELOS
                                    if m["tipo"] == "AV"])
def test_cada_modelo_de_averbacao_tem_o_rotulo_e_o_protocolo(codigo):
    """LRP art. 232 (o «AV-») e CN-MA art. 458 (número e data do protocolo
    no início do ato); o fato averbado é o próprio corpo do modelo."""
    corpo = MODELOS_DE_ATO.por_codigo(codigo)["corpo"]
    assert "{{ rotulo }}" in corpo and "{{ protocolo_frase }}" in corpo, codigo


def test_o_fecho_do_ato_tem_a_mesma_forma_com_e_sem_a_funcao():
    """A escolha entre os dois fechos é do código (sem a função cadastrada sai
    o segundo); os dois dizem o lugar, a data, a fé e o nome."""
    for chave in ("RI_FECHO_DO_ATO", "RI_FECHO_DO_ATO_SEM_TITULO"):
        texto = _jinja(_padrao(chave), FECHO_DO_ATO)
        for pedaco in ("Cidade Exemplo/MA", "20 de outubro de 2026", "Dou fé",
                       "CARLA EXEMPLO"):
            assert pedaco in texto, (chave, pedaco)


# --------------------------------- o ouro do LF06A que este lote mudou

# O texto de fábrica de ANTES do LT03 (commit 9a21e71), pelo sha256 — o ouro
# do LF06A (`fixtures/modelos_ouro/LF06A_catalogo.json`) foi regravado SÓ
# nestas três chaves, e só com o que a tabela abaixo diz.
ANTES_DO_LT03 = {
    "RI_FICHA": "39fd8c9927f6d828fc4cb8163b1c7b9b5505e3a622aa4d9c7c5439c0c399b7ac",
    "RI_CERTIDAO_INTEIRO_TEOR":
        "160c594fed10927add069d711870b5ab4639ec2ed26353391ad905ef4ca76477",
    "RI_CERTIDAO_NEGATIVA_IMOVEL":
        "e96c8776c9ec8b62b548b86320976e6678233f00dcf14b35221f62e8331990ed",
}

#: O que o LT03 acrescentou, e por quê — desfeito na ordem, o texto volta a
#: ser o de antes, byte a byte. (padrão, substituição, motivo)
O_QUE_O_LT03_MUDOU = {
    "RI_FICHA": [
        (re.escape("{% if m.inscricao_municipal %} <b>INSCRIÇÃO MUNICIPAL: </b>"
                   "{{ m.inscricao_municipal }}.{% endif %}"), "",
         "a designação cadastral — LRP art. 176, § 1º, II, 3, b"),
        (re.escape("{% if m.cib or m.car"), "{% if m.car", "o CIB entra no bloco do rural"),
        (re.escape("{% if m.cib %}<b>CIB: </b>{{ m.cib }}. {% endif %}"), "",
         "o código do imóvel rural — LRP art. 176, § 1º, II, 3, a"),
    ],
    "RI_CERTIDAO_INTEIRO_TEOR": [
        (r"^\{#.*?#\}\{% set abertura_estruturada = .*?%\}", "",
         "o comentário e a pergunta «a ficha é estruturada sem teor?»"),
        (r"\{% if abertura_estruturada %\}.*?\{% endif %\}(?=\{\{ selo_abertura_odf \}\})", "",
         "a abertura da ficha estruturada — LRP art. 19, § 11"),
        (re.escape("{% if teor_odf or abertura_estruturada or not loop.first %}"),
         "{% if teor_odf or not loop.first %}", "a risca antes do 1º ato, depois da abertura"),
        (re.escape("{% if a.fecho %}<p>{{ a.fecho }}</p>{% endif %}"), "",
         "o fecho de cada ato — LRP art. 19, § 11; CN-MA art. 458"),
    ],
    "RI_CERTIDAO_NEGATIVA_IMOVEL": [
        (r"\{% if imovel_busca %\}<p>Fica ressalvada .*?</p>\n\{% endif %\}", "",
         "a ressalva da descrição diversa — CN-MA art. 554"),
    ],
}


#: Depois do LT03 o ouro NÃO se regravou: o LH13 («14 a», 21/10/2026) trocou a
#: validade do art. 53 pela do 553 na negativa, e a troca está declarada aqui e
#: no `MUDOU_DEPOIS_DO_OURO` do `test_modelos_da_casa` — achada uma vez só.
O_QUE_O_LH13_TROCOU = {
    "RI_CERTIDAO_NEGATIVA_IMOVEL": (("na forma do art. 53 do Código de Normas",
                                     "na forma do art. 553 do Código de Normas"),),
}


@pytest.mark.parametrize("chave", sorted(O_QUE_O_LT03_MUDOU))
def test_o_ouro_do_lf06a_mudou_so_no_que_o_lt03_acrescentou(chave):
    """O LF06A gravou o ouro «para não se regerar»; o LT03 o regravou nestas
    três chaves para pôr no padrão o elemento que a lei exige. Desfazendo
    exatamente o que se acrescentou, sobra o texto de antes — e o ouro, com
    a troca do LH13, é o texto da pasta."""
    import hashlib
    agora = _padrao(chave)
    ouro = json.loads((RAIZ / "tests" / "fixtures" / "modelos_ouro" / "LF06A_catalogo.json")
                      .read_text(encoding="utf-8"))["textos"][chave]
    for velho, novo in O_QUE_O_LH13_TROCOU.get(chave, ()):
        assert ouro.count(velho) == 1, f"{chave}: a troca do LH13 não se acha uma vez"
        ouro = ouro.replace(velho, novo)
    assert ouro == agora, f"o ouro de {chave} não é o texto da pasta"
    desfeito = agora
    for velho, novo in O_QUE_O_LH13_TROCOU.get(chave, ()):
        desfeito = desfeito.replace(novo, velho)      # o LT03 escreveu o art. 53
    for padrao, troca, motivo in O_QUE_O_LT03_MUDOU[chave]:
        desfeito, n = re.subn(padrao, troca, desfeito, count=1, flags=re.S)
        assert n == 1, f"{chave}: não achei o que o LT03 acrescentou ({motivo})"
    assert hashlib.sha256(desfeito.encode("utf-8")).hexdigest() == ANTES_DO_LT03[chave], (
        f"{chave} mudou além do que o LT03 declara")
