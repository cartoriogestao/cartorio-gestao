"""Os papéis do Protesto têm o que a LEI e as NORMAS mandam ter (LT04).

Pedido do oficial, 20/10/2026: os modelos têm de abarcar o que a lei e as
normas exigem. As fontes, nesta ordem de prevalência: a Lei 9.492/1997, o
Código Nacional de Normas (Prov. CNJ 149/2023, compilado até o Prov. CN 253,
de 18/08/2026) e o Código de Normas Extrajudicial do MA (Prov. COGEX
28/2026). Os textos estão em `referencia/normas/` e
`referencia/codigo_de_normas_extrajudicial_ma.txt`.

A MATRIZ É `MATRIZ`, ABAIXO — a mesma de `docs/REQUISITOS_LEGAIS.md`, seção do
Protesto: para cada papel (o termo lavrado, a linha do livro, o aviso, o
edital, o instrumento, as certidões), cada elemento obrigatório com o artigo,
o que o papel tem de trazer (o rótulo e o valor) e o campo do modelo padrão
(`modelos_padrao/protesto/`) que o traz.

DOIS TESTES POR ELEMENTO
    - o papel, montado com um contexto de teste COMPLETO (título da CRA com
      apresentante, credor e devedor com documento e endereço, valor
      protestado diferente do de face, aceite e endosso), traz o elemento.
      O CPF/CNPJ e o endereço do apresentante a CRA não manda: eles moram no
      cadastro dos apresentantes, pelo código (LD08), e o contexto o tem;
    - o modelo padrão tem o campo — o marcador `{claro}` do texto ou o nome
      da peça-vocabulário.
    Elemento que falta é DEFEITO, e fica `xfail(strict=True)` com o artigo: a
    lista dos defeitos está no relatório do LT04 e em
    `docs/COBERTURA_FLUXOS.md`.

O CONTEXTO SE MONTA UMA VEZ POR MÓDULO, pelo domínio (as telas são o
`test_fluxo_protesto`): aqui o que se mede é o TEXTO, e montar dez títulos por
elemento só repetiria o mesmo papel cem vezes. As datas são fixas — o
protocolo da casa sai da data (AAMMDD + sequencial), e o prazo-limite dela.

DADOS FICTÍCIOS (LGPD): as pessoas, os documentos e o lugar são os da casa.
"""
from __future__ import annotations

import html as _html
import re
import sys
from pathlib import Path
from typing import NamedTuple

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco as nativo            # noqa: E402
from prova_de_intimacao import (entregar_com_comprovante,  # noqa: E402
                               juntar_prova)

PASTA_DOS_MODELOS = RAIZ / "modelos_padrao" / "protesto"

SERVENTIA = {
    "unit_name": "TABELIONATO DE PROTESTO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião de Protesto",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
    "serventia_endereco": "Rua Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "serventia_telefone": "(98) 3000-0000",
    "serventia_horario": "de segunda a sexta, das 8h às 17h",
    "modulo_protesto_ligado": "1",
}
EXTENSO = "vinte de outubro de dois mil e vinte e seis"
APONTADO_EM = "2026-10-20T09:00:00"
INTIMADO_EM = "2026-10-21T10:00:00"
PROTESTADO_EM = "2026-10-23T10:00:00"
CANCELADO_EM = "2026-10-26T10:00:00"

APRESENTANTE = "BANCO EXEMPLO S.A."
# O QUE O CADASTRO DOS APRESENTANTES DIZ DO CÓDIGO 999 (LD08): o arquivo da
# CRA traz só o código e o nome, e a casa cadastra o CNPJ e o endereço do banco
# uma vez (Protesto → XML da CENPROT). CNPJ fictício da lista anti-vazamento.
CNPJ_APRESENTANTE = "00000010000127"
ENDERECO_APRESENTANTE = "Avenida Exemplo, 500, Centro, Cidade Exemplo/MA"
DEVEDOR, CPF_DEVEDOR = "PEDRO EXEMPLO DOS SANTOS", "00000000191"
CREDOR, CPF_CREDOR = "CARLA EXEMPLO", "00000000272"
REQUERENTE = "BEATRIZ EXEMPLO DE SOUZA"
# O DA SUSTAÇÃO JUDICIAL PRECÁRIA (LH13): CPF fictício da lista anti-vazamento.
SUSPENSO, CPF_SUSPENSO = "JOANA EXEMPLO DA SILVA", "00000001325"
JUIZO_DA_ORDEM = "1ª Vara Cível de Cidade Exemplo"
PROCESSO_DA_ORDEM = "0800003-00.2026.8.10.0001"


def _titulo(numero: str, *, devedor: str, cpf: str, chave: str) -> dict:
    """Um título COMPLETO, no vocabulário de `protesto_arquivo.para_apontamento`."""
    return {
        "apresentante_codigo": "999", "apresentante_nome": APRESENTANTE,
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": "NN" + numero,
        "data_emissao": "2026-08-01", "data_vencimento": "2026-09-01",
        "valor": "1500.00", "saldo": "1234.56",
        "praca_protesto": "CIDADE EXEMPLO", "tipo_protesto": "C",
        "motivo_protesto": "1", "tipo_endosso": "T", "aceite": "A",
        "tipo_moeda": "1",
        "cedente": {"nome": CREDOR, "documento": CPF_CREDOR,
                    "endereco": "Rua das Flores, 10", "cidade": "Cidade Exemplo",
                    "uf": "MA"},
        "devedores": [{"nome": devedor, "CPF": cpf,
                       "enderecos": [{"endereco": "Rua Exemplo, 200",
                                      "bairro": "Centro", "cep": "65000000",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
        "_chave": chave,
    }


def _livro_na_tela(cliente, qual: str) -> list[str]:
    """As linhas do livro como a tela as mostra: «Coluna: valor | …»."""
    html = cliente.get(f"/protesto/livros/{qual}?de=2026-10-01&ate=2026-10-31"
                       ).get_data(as_text=True)
    cabeca = [_html.unescape(c).strip()
              for c in re.findall(r"<th>(.*?)</th>", html.split("<tbody>")[0])]
    corpo = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0]
    linhas = []
    for tr in re.findall(r"<tr>(.*?)</tr>", corpo, re.S):
        celulas = [_html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
                   for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
        linhas.append(" | ".join(f"{c}: {v}" for c, v in zip(cabeca, celulas)))
    return linhas


@pytest.fixture(scope="module")
def papeis(cg_app) -> dict[str, str]:
    """Todos os papéis do protesto, montados de títulos completos. ESCREVE
    (uma vez, no banco do módulo)."""
    import protesto as PT
    import protesto_aviso as AV
    import protesto_cenprot_xml as PCXML
    import protesto_certidao as PCE
    import protesto_instrumento as PI
    import protesto_relacao as REL
    from conftest import cg_login
    from serventia import dados as dados_serventia

    db = cg_app.extensions["db"]
    db.set_settings(SERVENTIA)
    sv = dados_serventia(db.get_settings)
    saida: dict[str, str] = {}

    def novo(con, dados: dict) -> int:
        chave = dados.pop("_chave")
        tid = PT.cadastrar_titulo(con, dados, origem="CRA", origem_chave=chave,
                                  agora=APONTADO_EM)
        PT.lancar_apontamento(con, tid, sv=sv, agora=APONTADO_EM,
                              data_extenso=EXTENSO)
        return tid

    with db.transaction() as con:
        # 0. O APRESENTANTE DA CRA NO CADASTRO DA CASA, com o CNPJ e o
        # endereço que o arquivo não traz (CN-MA art. 923; Lei 9.492, art.
        # 22, II) — o mesmo cadastro do XML da CENPROT.
        PCXML.gravar_apresentante(con, codigo="999", nome=APRESENTANTE,
                                  documento=CNPJ_APRESENTANTE,
                                  tipo_apresentante="0",
                                  endereco=ENDERECO_APRESENTANTE,
                                  agora=APONTADO_EM)

        # 1. O PROTESTADO: aviso entregue, protesto, instrumento.
        um = novo(con, _titulo("DMI-1/2026", devedor=DEVEDOR, cpf=CPF_DEVEDOR,
                               chave="req:1"))
        aviso = AV.emitir(con, um, hoje=APONTADO_EM[:10], agora=APONTADO_EM)
        saida["aviso"] = AV.montar_teor_do_aviso(
            con, AV.ler(con, aviso["aviso_id"]), sv=sv)
        # A ENTREGA COM O COMPROVANTE E QUEM RECEBEU (29/10/2026).
        entregar_com_comprovante(con, aviso["aviso_id"],
                                 agora=INTIMADO_EM, quando=INTIMADO_EM,
                                 recebido_por=DEVEDOR)
        PT.lancar_protesto(con, um, sv=sv, agora=PROTESTADO_EM,
                           data_extenso=EXTENSO)
        saida["termo"] = nativo(con).valor(
            "SELECT teor FROM pt_atos WHERE titulo_id=%s AND tipo='PROTESTO'",
            (um,))
        saida["instrumento"] = PI.emitir(con, um, serventia=sv["unit_name"],
                                         agora=PROTESTADO_EM)["teor"]

        # 2. O DO EDITAL: aviso não entregue, edital publicado.
        dois = novo(con, _titulo("DMI-2/2026", devedor=REQUERENTE,
                                 cpf="00000000353", chave="req:2"))
        aviso = AV.emitir(con, dois, hoje=APONTADO_EM[:10], agora=APONTADO_EM)
        AV.registrar_entrega(con, aviso["aviso_id"], entregue=False, motivo=1,
                             agora=INTIMADO_EM, quando=INTIMADO_EM)
        saida["edital"] = AV.publicar_edital(
            con, aviso["aviso_id"], sv=sv, hoje=INTIMADO_EM[:10],
            agora=INTIMADO_EM, data_extenso=EXTENSO,
            justificativa="Devedor mudou-se, sem outro endereço conhecido.")["teor"]

        # 3. O PAGO antes do protesto, com forma e emolumentos.
        tres = novo(con, _titulo("DMI-3/2026", devedor="MARIO EXEMPLO DOS SANTOS",
                                 cpf="00000001082", chave="req:3"))
        PT.lancar_pagamento(con, tres, sv=sv, agora=INTIMADO_EM,
                            data_extenso=EXTENSO, valor_pago="1234.56",
                            emolumentos="82,64", forma_pagamento="CHEQUE",
                            forma_identificacao="Banco 001, cheque 000123")

        # 4. O CANCELADO, para a certidão de cancelamento.
        quatro = novo(con, _titulo("DMI-4/2026", devedor=CREDOR, cpf="00000001163",
                                   chave="req:4"))
        PT.lancar_intimacao(con, quatro, modo="PESSOAL", agora=INTIMADO_EM)
        juntar_prova(con, quatro)   # a prova da intimação (29/10/2026)
        PT.lancar_protesto(con, quatro, sv=sv, agora=PROTESTADO_EM,
                           data_extenso=EXTENSO)
        PT.lancar_cancelamento(con, quatro, hipotese="ANUENCIA_CREDOR",
                               fundamento="Carta de anuência do credor.",
                               agora=CANCELADO_EM)

        # 5. O INTIMADO POR MEIO ELETRÔNICO (CN-MA art. 919, § 1º): a marca
        # `digital` que a Resolve confirmada deixa (`lavrar_intimacao_digital`).
        cinco = novo(con, _titulo("DMI-5/2026", devedor="MARIO EXEMPLO DOS SANTOS",
                                  cpf="00000001244", chave="req:5"))
        PT.lancar_intimacao(con, cinco, modo="PESSOAL", digital=True,
                            agora=INTIMADO_EM)
        juntar_prova(con, cinco)    # a Resolve confirmada, com o histórico
        PT.lancar_protesto(con, cinco, sv=sv, agora=PROTESTADO_EM,
                           data_extenso=EXTENSO)
        saida["termo_eletronico"] = nativo(con).valor(
            "SELECT teor FROM pt_atos WHERE titulo_id=%s AND tipo='PROTESTO'",
            (cinco,))
        saida["instrumento_eletronico"] = PI.emitir(
            con, cinco, serventia=sv["unit_name"], agora=PROTESTADO_EM)["teor"]

        # 6. O PROTESTO COM OS EFEITOS SUSPENSOS POR DECISÃO PROVISÓRIA (LH13,
        # 21/10/2026 — CNN art. 263-K, III): a sustação judicial precária.
        seis = novo(con, _titulo("DMI-6/2026", devedor=SUSPENSO, cpf=CPF_SUSPENSO,
                                 chave="req:6"))
        PT.lancar_intimacao(con, seis, modo="PESSOAL", agora=INTIMADO_EM)
        juntar_prova(con, seis)
        PT.lancar_protesto(con, seis, sv=sv, agora=PROTESTADO_EM,
                           data_extenso=EXTENSO)
        PT.lancar_efeito_suspensivo(con, seis, juizo=JUIZO_DA_ORDEM,
                                    processo=PROCESSO_DA_ORDEM,
                                    carater="PROVISORIA", agora=CANCELADO_EM)

        # AS CERTIDÕES, como `protesto_certidao.emitir` as monta.
        desde = PCE.data_limite("2026-10-27", 5)

        def certidao(tipo, nome, documento, **kw):
            achados = PCE.buscar(con, nome=nome, documento=documento,
                                 desde=desde, autorizacao=kw.get("autorizacao"))
            return PCE.montar_teor(tipo=tipo, nome=nome, documento=documento,
                                   achados=achados, desde=desde, hoje="2026-10-27",
                                   con=con, **kw)

        saida["certidao_positiva"] = certidao("POSITIVA", DEVEDOR, CPF_DEVEDOR,
                                              requerente=REQUERENTE)
        saida["certidao_negativa"] = certidao("NEGATIVA", REQUERENTE,
                                              "00000000353")
        saida["certidao_cancelamento"] = certidao(
            "CANCELAMENTO", CREDOR, "00000001163", autorizacao="DEVEDOR_ESCRITO",
            requerente=CREDOR)
        saida["certidao_precaria"] = certidao("POSITIVA", SUSPENSO, CPF_SUSPENSO)

        # A RELAÇÃO DIÁRIA do dia dos protestos (CN-MA art. 949).
        entidade = REL.habilitar_entidade(
            con, nome="ENTIDADE FICTÍCIA DE PROTEÇÃO AO CRÉDITO",
            documento="00000001000055", canal="DIRETO",
            habilitacao="Requerimento 1/2026", habilitada_em="2026-01-01",
            agora=APONTADO_EM)
        relacao = REL.gerar_relacao(con, dia=PROTESTADO_EM[:10],
                                    entidade_id=entidade, hoje="2026-10-27",
                                    agora="2026-10-27T09:00:00", sv=sv)
        saida["relacao"] = REL.relacao(con, relacao["relacao_id"])["teor"]

    # OS LIVROS, como a tela os mostra — o rótulo da coluna é do papel.
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", "Senha#12345", "ADMIN")
    cliente = cg_app.test_client()
    cg_login(cliente, "tabeliao", "Senha#12345")
    protocolo = _livro_na_tela(cliente, "protocolo")
    saida["livro_protocolo"] = next(x for x in protocolo if "DMI-1" in x or DEVEDOR in x)
    [saida["livro_pagamentos"]] = _livro_na_tela(cliente, "pagamentos")
    with db.connect() as con:
        um_titulo = nativo(con).um("SELECT * FROM pt_titulos WHERE id=%s", (um,))
    saida["_protocolo"] = um_titulo["protocolo"]
    return saida


# ------------------------------------------------------------- a matriz


class Requisito(NamedTuple):
    papel: str             # chave em `papeis`
    elemento: str          # o que a norma pede
    artigo: str            # de onde vem
    esperado: tuple        # o que tem de estar no papel (rótulo e valor)
    modelo: tuple | None   # (peça em modelos_padrao/protesto, campo) — None: dado do sistema
    defeito: str | None = None


P = "{protocolo}"   # o protocolo do título 1, que só se sabe depois de apontado

MATRIZ: tuple[Requisito, ...] = (
    # ---------------------------------------- o aviso de intimação
    Requisito("aviso", "número do protocolo", "CN-MA art. 920; Lei 9.492 art. 14, § 2º",
              (f"Protocolo n. {P}",), ("PT_AVISO_INTIMACAO", "{protocolo}")),
    Requisito("aviso", "nome do devedor", "CN-MA art. 920",
              (f"Devedor: {DEVEDOR}",), ("PT_AVISO_INTIMACAO", "{devedor}")),
    Requisito("aviso", "documento do devedor", "CN-MA arts. 906 e 920",
              ("CPF/CNPJ 000.000.001-91",), ("PT_AVISO_INTIMACAO", "{documento_do_devedor}")),
    Requisito("aviso", "endereço do devedor", "CN-MA art. 920; Lei 9.492 art. 14, § 2º",
              ("Endereço: Rua Exemplo, 200, Centro, Cidade Exemplo/MA, CEP 65000000",),
              ("PT_AVISO_INTIMACAO", "{endereco}")),
    Requisito("aviso", "espécie do título por extenso", "CN-MA art. 920",
              ("Título: Duplicata de Venda Mercantil por Indicação",),
              ("PT_AVISO_INTIMACAO", "{especie}")),
    Requisito("aviso", "número do título", "CN-MA art. 920",
              ("n. DMI-1/2026",), ("PT_AVISO_INTIMACAO", "{numero_titulo}")),
    Requisito("aviso", "valor a pagar", "CN-MA art. 920; Lei 9.492 art. 14, § 2º",
              ("Valor: R$ 1.234,56",), ("PT_AVISO_INTIMACAO", "{valor}")),
    Requisito("aviso", "data de vencimento", "CN-MA art. 920",
              ("vencimento em 01/09/2026",), ("PT_AVISO_INTIMACAO", "{vencimento}")),
    Requisito("aviso", "existência ou não de aceite", "CN-MA art. 920",
              ("Aceite: com aceite",), ("PT_AVISO_INTIMACAO", "{aceite}")),
    Requisito("aviso", "sacador ou favorecido (credor), com CPF/CNPJ", "CN-MA arts. 920 e 923",
              (f"Credor (sacador/favorecido): {CREDOR}, CPF/CNPJ 000.000.002-72",),
              ("PT_AVISO_INTIMACAO", "{credor}")),
    Requisito("aviso", "nome do apresentante", "CN-MA arts. 920 e 923",
              (f"Apresentante: {APRESENTANTE}",), ("PT_AVISO_INTIMACAO", "{apresentante}")),
    # LD08: o documento vem do cadastro dos apresentantes, pelo código da CRA
    # (`protesto.apresentante_do_titulo`), e o aviso o escreve ao lado do nome.
    Requisito("aviso", "CPF/CNPJ do apresentante", "CN-MA art. 923; CNN art. 356, § 4º",
              (f"Apresentante: {APRESENTANTE}, CPF/CNPJ 00.000.010/0001-27",),
              ("PT_AVISO_INTIMACAO", "{documento_do_apresentante}")),
    Requisito("aviso", "prazo-limite para pagamento", "CN-MA arts. 920 e 925, § 4º",
              ("Prazo-limite para pagamento: 23/10/2026",),
              ("PT_AVISO_INTIMACAO", "{prazo_limite}")),
    Requisito("aviso", "endereço do tabelionato", "CN-MA art. 920",
              ("Rua Exemplo, 100, Centro, CEP 65000-000, Cidade Exemplo-MA",),
              ("PT_AVISO_INTIMACAO", "{endereco_da_serventia}")),
    Requisito("aviso", "horário de funcionamento", "CN-MA art. 920",
              ("Horário de funcionamento: de segunda a sexta, das 8h às 17h",),
              ("PT_AVISO_INTIMACAO", "{horario}")),
    Requisito("aviso", "telefone do tabelionato", "CN-MA art. 923",
              ("Telefone (98) 3000-0000",), ("PT_AVISO_INTIMACAO", "{telefone}")),

    # ---------------------------------------- o edital
    Requisito("edital", "nome do devedor", "CN-MA art. 922, § 3º; Lei 9.492 art. 15",
              (REQUERENTE,), ("PT_EDITAL_INTIMACAO", "{devedor}")),
    Requisito("edital", "identificação do devedor", "CN-MA arts. 906 e 922, § 3º",
              ("inscrito(a) no CPF/CNPJ sob o nº 000.000.003-53",),
              ("PT_EDITAL_INTIMACAO", "{documento_do_devedor}")),
    Requisito("edital", "identificação do título", "CN-MA art. 922, § 3º",
              ("Título: DMI-2/2026 — espécie DMI",), ("PT_EDITAL_INTIMACAO", "{numero_titulo}")),
    Requisito("edital", "protocolo", "CN-MA art. 922, § 3º (elementos do título)",
              ("Protocolo: 2610200002",), ("PT_EDITAL_INTIMACAO", "{protocolo}")),
    Requisito("edital", "valor a pagar", "CN-MA art. 922, § 3º",
              ("Valor: R$ 1.234,56",), ("PT_EDITAL_INTIMACAO", "{valor}")),
    Requisito("edital", "prazo-limite", "CN-MA art. 922, § 3º",
              ("Prazo-limite para pagamento: 23/10/2026",),
              ("PT_EDITAL_INTIMACAO", "{prazo_limite}")),
    Requisito("edital", "tabelionato, endereço e telefone", "CN-MA art. 922, § 3º",
              (SERVENTIA["unit_name"], "Rua Exemplo, 100, Centro", "Telefone (98) 3000-0000"),
              ("PT_EDITAL_INTIMACAO", "{endereco_da_serventia}")),

    # ---------------------------------------- o registro do protesto (o termo)
    # A QUALIFICAÇÃO DO REGISTRO entrou no LD04 (21/10/2026), com a MESMA
    # redação do instrumento (`protesto_instrumento.pedacos_da_descricao`): o
    # registro e a certidão dele têm de bater. O campo mora na PEÇA
    # `PT_TERMO_QUALIFICACAO`, que a regra põe no alto do termo — e não no
    # texto da casa (`PT_TERMO_PROTESTO`), para o termo personalizado também a
    # receber (art. 21, § 4º: os devedores «não poderão deixar de figurar»). O
    # número de ordem, que o item nomeia e não conferia, entrou junto com a data.
    Requisito("termo", "número de ordem e data do registro", "CN-MA art. 914, I",
              ("Registro do protesto: Livro 1, folha 1, sob o n.º 1, em 23/10/2026.",),
              ("PT_TERMO_QUALIFICACAO", "{data}")),
    Requisito("termo", "data e número da protocolização", "Lei 9.492 art. 22, I; CN-MA art. 914",
              (f"Protocolo n.º {P}, de 20/10/2026.",), ("PT_TERMO_QUALIFICACAO", "{protocolo}")),
    # O nome sem o ponto do fim: ver o mesmo item do instrumento, abaixo.
    Requisito("termo", "nome do apresentante", "Lei 9.492 art. 22, II; CN-MA art. 914",
              (f"Apresentante: {APRESENTANTE}",), ("PT_TERMO_QUALIFICACAO", "{apresentante}")),
    # LD08: «nome do apresentante e endereço» é do REGISTRO e do instrumento
    # (art. 22, caput) — o pedaço é o mesmo dos dois.
    Requisito("termo", "endereço do apresentante", "Lei 9.492 art. 22, II; CN-MA art. 914, III",
              (f"Apresentante: {APRESENTANTE}, endereço {ENDERECO_APRESENTANTE}.",),
              ("PT_TERMO_QUALIFICACAO", "{apresentante}")),
    Requisito("termo", "indicações do título", "Lei 9.492 art. 22, III; CN-MA art. 914",
              ("DMI-1/2026", "1.234,56"), ("PT_TERMO_QUALIFICACAO", "{titulo}")),
    Requisito("termo", "certidão das intimações", "Lei 9.492 art. 22, IV; CN-MA art. 914",
              ("O devedor foi intimado pessoalmente em 21/10/2026.",),
              ("PT_TERMO_PROTESTO", "{edital}")),
    Requisito("termo", "devedor, documento e endereço", "Lei 9.492 arts. 21, § 4º, e 22, VII",
              (f"Devedor: {DEVEDOR}, CPF {CPF_DEVEDOR}, endereço Rua Exemplo, 200, "
               "Centro, Cidade Exemplo/MA.",), ("PT_TERMO_QUALIFICACAO", "{devedor}")),
    Requisito("termo", "tipo do protesto", "Lei 9.492 art. 23; CN-MA art. 914, IX",
              ("PROTESTO COMUM",), ("PT_TERMO_PROTESTO", "{tipo}")),
    Requisito("termo", "motivo do protesto", "Lei 9.492 arts. 21 e 23; CN-MA arts. 914 e 916",
              ("LAVRADO POR FALTA DE PAGAMENTO",), ("PT_TERMO_PROTESTO", "{motivo}")),

    # ---------------------------------------- o instrumento
    Requisito("instrumento", "número de ordem e data do registro", "CN-MA art. 914, I",
              ("Registro do protesto: Livro 1, folha 1, sob o n.º 1, em 23/10/2026.",),
              ("PT_INSTRUMENTO_DESCRICAO", "registro")),
    Requisito("instrumento", "data e número da protocolização", "Lei 9.492 art. 22, I",
              (f"Protocolo n.º {P}, de 20/10/2026.",),
              ("PT_INSTRUMENTO_DESCRICAO", "protocolo_com_data")),
    # O NOME SEM O PONTO DO FIM (LD08): com o endereço o pedaço continua
    # («Apresentante: X, endereço Y.»), e o pedaço inteiro a linha seguinte
    # confere. O ponto era o fecho do pedaço sem endereço — e, com o «S.A.» do
    # nome, a conferência pedia «S.A..».
    Requisito("instrumento", "nome do apresentante", "Lei 9.492 art. 22, II",
              (f"Apresentante: {APRESENTANTE}",), ("PT_INSTRUMENTO_DESCRICAO", "apresentante")),
    # LD08: o endereço vem do cadastro dos apresentantes, pelo código da CRA.
    Requisito("instrumento", "endereço do apresentante", "Lei 9.492 art. 22, II",
              (f"Apresentante: {APRESENTANTE}, endereço {ENDERECO_APRESENTANTE}.",),
              ("PT_INSTRUMENTO_DESCRICAO", "apresentante_endereco")),
    Requisito("instrumento", "indicações do título", "Lei 9.492 art. 22, III",
              ("Título: Duplicata de Venda Mercantil por Indicação, n.º DMI-1/2026, "
               "emitido em 01/08/2026, vencido em 01/09/2026, valor R$ 1.500,00, "
               "valor protestado R$ 1.234,56.",),
              ("PT_INSTRUMENTO_DESCRICAO", "titulo")),
    Requisito("instrumento", "cópia arquivada ou a falta dela",
              "Lei 9.492 art. 22, parágrafo único",
              ("não se aplica a dispensa do parágrafo único do art. 22",),
              ("PT_INSTRUMENTO_PROTESTO", "{copia}")),
    Requisito("instrumento", "certidão das intimações", "Lei 9.492 art. 22, IV",
              ("CERTIFICO que a intimação foi entregue no endereço do devedor em 21/10/2026.",),
              ("PT_INSTRUMENTO_PROTESTO", "{intimacao}")),
    Requisito("instrumento", "credor", "CN-MA art. 914",
              (f"Credor (sacador/favorecido): {CREDOR}, CPF/CNPJ {CPF_CREDOR}.",),
              ("PT_INSTRUMENTO_DESCRICAO", "credor_com_documento")),
    Requisito("instrumento", "devedor, documento e endereço", "Lei 9.492 art. 22, VII",
              (f"Devedor: {DEVEDOR}, CPF {CPF_DEVEDOR}, endereço Rua Exemplo, 200, "
               "Centro, Cidade Exemplo/MA.",),
              ("PT_INSTRUMENTO_DESCRICAO", "devedor_endereco")),
    Requisito("instrumento", "tipo e motivo do protesto", "Lei 9.492 art. 23; CN-MA art. 914, IX",
              ("Tipo: protesto comum. Motivo: falta de pagamento.",),
              ("PT_INSTRUMENTO_DESCRICAO", "tipo_e_motivo")),
    Requisito("instrumento", "a serventia que declara o protesto", "Lei 9.492 art. 20",
              (f"O {SERVENTIA['unit_name']}, Tabelionato de Protesto de Títulos, "
               "DECLARA PROTESTADO",), ("PT_INSTRUMENTO_PROTESTO", "{serventia}")),
    Requisito("instrumento", "data e assinatura do tabelião", "Lei 9.492 art. 22, VIII",
              (), ("PT_MOLDURAS", "local_e_data")),

    # ---------------------------------------- a intimação eletrônica
    Requisito("termo_eletronico", "certidão da intimação eletrônica",
              "Lei 9.492 arts. 14, § 3º, e 22, IV; CN-MA arts. 919, § 1º, e 921, § 6º, II",
              ("O devedor foi intimado por meio eletrônico, com o recebimento "
               "confirmado em 21/10/2026.",),
              ("PT_TERMO_INTIMACAO_DIGITAL", "{data}")),
    # LD04: `protesto_instrumento.dados` lê a marca `digital`, e a peça própria
    # certifica a mesma data que o termo do mesmo protesto.
    Requisito("instrumento_eletronico", "certidão da intimação eletrônica",
              "Lei 9.492 arts. 14, § 3º, e 22, IV; CN-MA arts. 919, § 1º, e 921, § 6º, II",
              ("CERTIFICO que a intimação foi feita por meio eletrônico, com o "
               "recebimento confirmado em 21/10/2026.",),
              ("PT_INSTRUMENTO_INTIMACAO_DIGITAL", "{data}")),

    # ---------------------------------------- o Livro de Protocolo
    Requisito("livro_protocolo", "número de ordem", "Lei 9.492 art. 32; CN-MA art. 908",
              ("Nº de ordem: 1",), ("PT_MOLDURAS", "protocolo_ordem")),
    Requisito("livro_protocolo", "protocolo e data", "CN-MA art. 907",
              (f"Protocolo: {P}", "Data: 20/10/2026"), ("PT_MOLDURAS", "protocolo_data")),
    Requisito("livro_protocolo", "natureza do título", "Lei 9.492 art. 32; CN-MA art. 908",
              ("Natureza: Duplicata de Venda Mercantil por Indicação",),
              ("PT_MOLDURAS", "protocolo_natureza")),
    Requisito("livro_protocolo", "valor", "Lei 9.492 art. 32; CN-MA art. 908",
              ("Valor: 1.500,00",), ("PT_MOLDURAS", "protocolo_valor")),
    Requisito("livro_protocolo", "apresentante", "Lei 9.492 art. 32; CN-MA art. 908",
              (f"Apresentante: {APRESENTANTE}",), ("PT_MOLDURAS", "protocolo_apresentante")),
    Requisito("livro_protocolo", "devedor", "Lei 9.492 art. 32; CN-MA art. 908",
              (f"Devedor: {DEVEDOR}",), ("PT_MOLDURAS", "protocolo_devedor")),
    Requisito("livro_protocolo", "CPF/CNPJ do devedor", "CN-MA art. 906",
              ("CPF/CNPJ do devedor: 000.000.001-91",),
              ("PT_MOLDURAS", "protocolo_documento")),
    Requisito("livro_protocolo", "ocorrências com data", "CN-MA art. 908, §§ 1º e 5º",
              ("intimado pessoalmente em 21/10/2026", "protestado em 23/10/2026"),
              ("PT_LIVRO_PROTOCOLO", "com_data")),

    # ---------------------------------------- o Livro de Registro de Pagamentos
    Requisito("livro_pagamentos", "número de ordem", "CN-MA art. 930, a",
              ("Nº de ordem: 1",), ("PT_MOLDURAS", "pagamentos_ordem")),
    Requisito("livro_pagamentos", "data do assentamento", "CN-MA art. 930, b",
              ("Data: 21/10/2026",), ("PT_MOLDURAS", "pagamentos_data")),
    Requisito("livro_pagamentos", "protocolo do documento pago", "CN-MA art. 930, c",
              ("Protocolo: 2610200003",), ("PT_MOLDURAS", "pagamentos_protocolo")),
    Requisito("livro_pagamentos", "natureza do documento", "CN-MA art. 930, d",
              ("Natureza: Duplicata de Venda Mercantil por Indicação",),
              ("PT_MOLDURAS", "pagamentos_natureza")),
    Requisito("livro_pagamentos", "valor do pagamento", "CN-MA art. 930, e",
              ("Valor pago: 1.234,56",), ("PT_MOLDURAS", "pagamentos_valor")),
    Requisito("livro_pagamentos", "valor dos emolumentos", "CN-MA art. 930, f",
              ("Emolumentos: 82,64",), ("PT_MOLDURAS", "pagamentos_emolumentos")),
    Requisito("livro_pagamentos", "devedor e favorecido", "CN-MA art. 930, g",
              ("Devedor: MARIO EXEMPLO DOS SANTOS", f"Favorecido: {CREDOR}"),
              ("PT_MOLDURAS", "pagamentos_favorecido")),
    Requisito("livro_pagamentos", "forma de pagamento e identificação", "CN-MA art. 930, h",
              ("Ocorrências: pago por cheque — Banco 001, cheque 000123",),
              ("PT_LIVRO_PAGAMENTOS", "pago_com_identificacao")),

    # ---------------------------------------- a certidão negativa
    Requisito("certidao_negativa", "a quem pede", "Lei 9.492 art. 31; CN-MA art. 950",
              ("a requerimento verbal de parte interessada",),
              ("PT_CERTIDAO_NEGATIVA", "{pedido}")),
    Requisito("certidao_negativa", "nome", "Lei 9.492 art. 27, § 1º",
              (REQUERENTE,), ("PT_CERTIDAO_NEGATIVA", "{identificacao}")),
    Requisito("certidao_negativa", "CPF/CNPJ", "Lei 9.492 art. 27, § 1º; CN-MA art. 906",
              ("CPF: 000.000.003-53",), ("PT_CERTIDAO_IDENTIFICACAO", "{documento}")),
    Requisito("certidao_negativa", "período de cinco anos", "Lei 9.492 art. 27; CNN art. 365",
              ("a partir do mês de Outubro de 2021", "Período de Busca: 5 Anos"),
              ("PT_CERTIDAO_NEGATIVA", "{periodo_anos}")),
    Requisito("certidao_negativa", "o resultado", "CNN art. 263-K, I",
              ("NÃO ENCONTREI protesto",), ("PT_CERTIDAO_NEGATIVA", "NÃO ENCONTREI")),

    # ---------------------------------------- a certidão positiva
    Requisito("certidao_positiva", "a quem pede", "Lei 9.492 art. 31; CN-MA art. 950",
              (f"a requerimento de {REQUERENTE}",), ("PT_CERTIDAO_CABECA", "{pedido}")),
    Requisito("certidao_positiva", "nome do devedor", "CNN art. 259, parágrafo único, I",
              (f"encontrei protesto contra {DEVEDOR}",), ("PT_CERTIDAO_CABECA", "{nome}")),
    Requisito("certidao_positiva", "CPF/CNPJ do devedor", "CNN art. 259, p. ú., II; CN-MA art. 906",
              ("inscrito no CPF: 000.000.001-91",), ("PT_CERTIDAO_INSCRITO", "{documento}")),
    Requisito("certidao_positiva", "livro, folha e número do registro", "CNN art. 259, p. ú., III",
              ("Livro 1, fl. 1, n. 1",), ("PT_CERTIDAO_LINHA", "numero_de_ordem")),
    Requisito("certidao_positiva", "ocorrência e data", "CNN art. 259, p. ú., IV",
              ("protestado em 23/10/2026",), ("PT_CERTIDAO_LINHA", "protestado")),
    Requisito("certidao_positiva", "apresentante", "CNN art. 259, p. ú., V",
              (f"apresentante {APRESENTANTE}",), ("PT_CERTIDAO_LINHA", "apresentante")),
    # LD08: o endosso T do título, logo depois do apresentante (o inciso V).
    Requisito("certidao_positiva", "tipo do endosso", "CNN art. 259, p. ú., V",
              ("endosso translativo", f"apresentante {APRESENTANTE}; endosso translativo;"),
              ("PT_CERTIDAO_LINHA", "endosso")),
    Requisito("certidao_positiva", "credor e CPF/CNPJ", "CNN art. 259, p. ú., VI",
              (f"credor {CREDOR} (000.000.002-72)",),
              ("PT_CERTIDAO_LINHA", "credor_com_documento")),
    Requisito("certidao_positiva", "número do protocolo", "CNN art. 259, p. ú., VII",
              (f"protocolo {P}",), ("PT_CERTIDAO_LINHA", "protocolo")),
    # LD08: a data da protocolização é a do apontamento.
    Requisito("certidao_positiva", "data do protocolo", "CNN art. 259, p. ú., VII",
              (f"protocolo {P} de 20/10/2026",), ("PT_CERTIDAO_LINHA", "protocolo_com_data")),
    Requisito("certidao_positiva", "espécie e número do título", "CNN art. 259, p. ú., VII",
              ("Título n. DMI-1/2026", "espécie DMI"), ("PT_CERTIDAO_LINHA", "especie")),
    Requisito("certidao_positiva", "emissão e vencimento", "CNN art. 259, p. ú., VII",
              ("emitido em 01/08/2026", "vencido em 01/09/2026"),
              ("PT_CERTIDAO_LINHA", "vencimento")),
    Requisito("certidao_positiva", "valor original e valor protestado", "CNN art. 259, p. ú., VII",
              ("valor R$ 1.500,00", "valor protestado R$ 1.234,56"),
              ("PT_CERTIDAO_LINHA", "valor_protestado")),
    Requisito("certidao_positiva", "tipo e motivo do protesto",
              "CNN art. 259, p. ú., VII; Lei 9.492 art. 30",
              ("protesto comum por falta de pagamento",), ("PT_CERTIDAO_LINHA", "protesto")),

    # ---------------------------------------- a certidão de cancelamento
    Requisito("certidao_cancelamento", "o pedido escrito do devedor (ou a ordem)",
              "Lei 9.492 art. 27, § 2º; CN-MA arts. 944 e 948",
              ("a requerimento escrito do próprio devedor",),
              ("PT_CERTIDAO_PEDIDO_DEVEDOR", "requerimento escrito")),
    Requisito("certidao_cancelamento", "o registro cancelado", "CN-MA art. 945",
              ("1) Título n. DMI-4/2026", "protestado em 23/10/2026"),
              ("PT_CERTIDAO_CANCELAMENTO", "{corpo}")),
    Requisito("certidao_cancelamento", "a data do cancelamento", "Lei 9.492 art. 26",
              ("CANCELADO em 26/10/2026",), ("PT_CERTIDAO_LINHA", "cancelado")),
    Requisito("certidao_cancelamento", "a baixa pelo art. 26", "Lei 9.492 art. 26",
              ("consta a BAIXA e o CANCELAMENTO do mesmo de acordo com o art. 26",),
              ("PT_CERTIDAO_CANCELAMENTO", "{fecho}")),

    # ---------------------------------------- a sustação judicial precária
    # LH13 (21/10/2026): o oficial passou a seguir o CNN art. 263-K (Prov. CN
    # 253/2026). A decisão PROVISÓRIA sai na certidão a terceiro — positiva,
    # cobrada e selada como ela — com a frase do inciso III, os dados do
    # registro, o número da ação, o caráter provisório e o fecho.
    Requisito("certidao_precaria", "o resultado da sustação provisória", "CNN art. 263-K, III",
              ("CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA",),
              ("PT_CERTIDAO_LINHA", "sustacao_precaria")),
    Requisito("certidao_precaria", "os dados do registro", "CNN art. 263-K, III",
              ("1) Título n. DMI-6/2026", "protestado em 23/10/2026", "Livro 1, fl. "),
              ("PT_CERTIDAO_LINHA", "numero_de_ordem")),
    Requisito("certidao_precaria", "o número da ação e o caráter provisório",
              "CNN art. 263-K, III",
              (f"decisão judicial de caráter provisório ({JUIZO_DA_ORDEM}), na ação "
               f"n. {PROCESSO_DA_ORDEM}",), ("PT_CERTIDAO_LINHA", "sustacao_precaria")),
    Requisito("certidao_precaria", "o fecho do cumprimento da decisão", "CNN art. 263-K, III",
              ("Resultado emitido em cumprimento à decisão judicial — Processo nº "
               f"{PROCESSO_DA_ORDEM}.",), ("PT_CERTIDAO_LINHA", "fecho_precaria")),

    # ---------------------------------------- a certidão em forma de relação
    Requisito("relacao", "nota de informação reservada", "Lei 9.492 art. 29; CN-MA art. 949",
              ("INFORMAÇÃO RESERVADA",), None),
    Requisito("relacao", "nome do devedor", "CNN art. 130",
              (DEVEDOR,), None),
    Requisito("relacao", "CPF do devedor", "CNN art. 130",
              (CPF_DEVEDOR,), None),
    Requisito("relacao", "espécie do título", "CNN art. 130",
              (";DMI;",), None),
    Requisito("relacao", "data do protesto", "CNN art. 130",
              ("P;23/10/2026;",), None),
    Requisito("relacao", "valor protestado", "CNN art. 130",
              (";1.234,56;",), None),
    # O vencimento é a ÚLTIMA coluna (LD11): as oito de antes do LD04 ficam
    # onde estavam, para a entidade que lê a relação por posição.
    Requisito("relacao", "data do vencimento", "CNN art. 130",
              ("TIPO;DIA;PROTOCOLO;ESPECIE;TITULO;VALOR;DEVEDOR;DOCUMENTO;VENCIMENTO\n",
               f";DMI-1/2026;1.234,56;{DEVEDOR};{CPF_DEVEDOR};01/09/2026\n"), None),
)


def _id(r: Requisito) -> str:
    return f"{r.papel}-{re.sub(r'[^a-z0-9]+', '_', r.elemento.lower()).strip('_')}"


def _param(r: Requisito, *, do_modelo: bool = False):
    marcas = []
    if r.defeito:
        marcas.append(pytest.mark.xfail(strict=True, reason=(
            f"DEFEITO ({r.artigo}): {r.elemento} — {r.defeito}.")))
    return pytest.param(r, id=_id(r), marks=marcas)


def _modelo_padrao(chave: str) -> str:
    return (PASTA_DOS_MODELOS / f"{chave}.txt").read_bytes().decode("utf-8")


def _campos_do_modelo(chave: str) -> set[str]:
    """Os claros `{x}` do texto e os nomes `nome = texto` da peça-vocabulário."""
    texto = _modelo_padrao(chave)
    claros = {f"{{{c}}}" for c in re.findall(r"\{(\w+)\}", texto)}
    nomes = {linha.split("=", 1)[0].strip() for linha in texto.splitlines()
             if "=" in linha and re.match(r"^\s*\w+\s*=", linha)}
    return claros | nomes


@pytest.mark.parametrize("req", [_param(r) for r in MATRIZ])
def test_o_papel_traz_o_elemento_que_a_norma_exige(papeis, req):
    texto = papeis[req.papel]
    for esperado in req.esperado:
        esperado = esperado.replace(P, papeis["_protocolo"])
        assert esperado in texto, (req.artigo, esperado, texto)


@pytest.mark.parametrize("req", [_param(r) for r in MATRIZ if r.modelo])
def test_o_modelo_da_casa_tem_o_campo_do_elemento(req):
    chave, campo = req.modelo
    texto = _modelo_padrao(chave)
    assert campo in _campos_do_modelo(chave) or (
        not campo.startswith("{") and not re.fullmatch(r"\w+", campo)
        and campo in texto), (req.artigo, chave, campo)


def test_nenhum_papel_sai_com_marcador_sobrando_ou_none(papeis):
    """O claro que não se preencheu não chega ao papel: nem `{x}`, nem o
    «None» do Python, nem o «;  ;» de um pedaço vazio."""
    for nome, texto in papeis.items():
        if nome.startswith("_"):
            continue
        for sobra in ("{", "}", "None", " ; ;", ", ,"):
            assert sobra not in texto, (nome, sobra, texto)


def test_a_matriz_cobre_todos_os_papeis_do_protesto(papeis):
    """Papel montado sem nenhuma linha na matriz é papel que ninguém confere."""
    conferidos = {r.papel for r in MATRIZ}
    assert conferidos == {k for k in papeis if not k.startswith("_")}


def test_os_modelos_citados_na_matriz_existem_na_pasta_dos_padroes():
    """A matriz só aponta para peça que existe — senão o teste do modelo
    falharia por nome errado, e não pelo campo que falta."""
    for r in MATRIZ:
        if r.modelo:
            assert (PASTA_DOS_MODELOS / f"{r.modelo[0]}.txt").is_file(), r.modelo
