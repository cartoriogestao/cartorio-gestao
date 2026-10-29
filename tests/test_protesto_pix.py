"""PIX NO PROTESTO SÓ É PAGAMENTO COM O COMPROVANTE E O CRÉDITO CONFERIDO.

POR QUE ESTES TESTES EXISTEM (29/10/2026)
    Um PIX de pagamento de título entrou na conta em 16/10/2026; a escrevente
    só o lançou em 21/10, «por PIX», sem comprovante e sem protocolo com o
    item marcado. O selo falhou e o ato se desfez, mas o título ficou PAGO, e
    a CRA foi informada com a data do lançamento. O oficial levou 8 dias para
    conseguir confirmar se o dinheiro tinha entrado. A ordem dele: «a
    escrevente não pode conseguir errar; se insistir, tem de afirmar
    expressamente e deixar log».

O QUE ELES CONFEREM
    - PIX não se lavra sem crédito conferido, por tela nenhuma (o domínio);
    - registrar o PIX exige o comprovante, no mesmo ato, e não cria ato: o
      título não vira PAGO, nada vai ao retorno da CRA, nada se sela;
    - o mesmo comprovante, ou o mesmo E2E, não paga dois títulos;
    - enquanto o PIX espera, o título não se protesta, não se desiste e não
      recebe outro pagamento;
    - o extrato confirma pelo E2E ou pelo valor e pelo dia, e só quando o
      crédito é um só; o crédito usado não confirma outro PIX;
    - a confirmação à mão é do oficial ou do gerente, nunca de quem lançou,
      nunca de robô, e só com a afirmação expressa que diz o valor;
    - confirmado, o pagamento se lavra pelo caminho de sempre, com a DATA DO
      CRÉDITO no ato, no Livro de Pagamentos e no D da CENPROT;
    - a pendência de mais de um dia útil, no contrato dos ganchos do roteiro;
    - e o furo do item 4: o retorno gerado que leva ato desfeito depois não
      vai à CRA.

Os documentos são os fictícios de `fixtures/anti_vazamento`; a rede do banco e
a da CRA são simuladas.
"""
from __future__ import annotations

import glob
import io
import json
import re
import sqlite3
import sys
from contextlib import contextmanager
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from navegador_de_teste import postar_e_seguir  # noqa: E402
from prova_de_intimacao import garantir_anexos, juntar_prova  # noqa: E402

import pix_credito as PC  # noqa: E402
import protesto as PT  # noqa: E402
import protesto_pix as PIX  # noqa: E402
import protesto_retorno as PR  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-10-21T08:19:00"
DIA_DO_CREDITO = "2026-10-16"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
QUEM_LANCA = "CARLA EXEMPLO"
QUEM_CONFERE = "BEATRIZ EXEMPLO"
E2E = "E00000000202610161130ABCDEFGHIJK"
AFIRMACAO = ("Afirmo, sob minha responsabilidade, que o crédito de R$ 1.765,14 "
             "entrou em 16/10/2026 na conta corrente da serventia, conferida "
             "no extrato do banco de ensaio")


def _pdf(marca: str = "a") -> bytes:
    return f"%PDF-1.4\n% comprovante de ensaio {marca}\n".encode()


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    garantir_anexos(con)
    return con


def titulo(con, numero="1/1", *, valor="1.765,14", cpf="00000000191") -> int:
    dados = {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO DE ENSAIO",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-08-05", "data_vencimento": "2026-09-05",
        "valor": valor, "saldo": valor,
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA DE ENSAIO LTDA", "documento": "00000001000055"},
        "devedores": [{"nome": "PESSOA DE ENSAIO", "CPF": cpf,
                       "enderecos": [{"endereco": "RUA DE ENSAIO, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    tid = PT.cadastrar_titulo(con, dados, origem="CRA",
                              origem_chave=f"lote:{numero}", agora=AGORA)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    return tid


def registrar(con, tid, tmp_path, *, conteudo=None, e2eid=None, valor="1.765,14",
              data_pix=DIA_DO_CREDITO) -> dict:
    return PIX.registrar(con, tid, valor=valor, data_pix=data_pix, e2eid=e2eid,
                         nome="comprovante.pdf",
                         conteudo=_pdf(str(tid)) if conteudo is None else conteudo,
                         pasta_de_arquivos=tmp_path, agora=AGORA,
                         usuario=QUEM_LANCA)


def _pix(con, pix_id) -> dict:
    return dict(con.execute("SELECT * FROM pt_pix WHERE id=?", (pix_id,)).fetchone())


def _pagamentos(con, tid) -> list:
    return con.execute("SELECT * FROM pt_atos WHERE titulo_id=? AND tipo='PAGAMENTO'",
                       (tid,)).fetchall()


def confirmar(con, pix_id, **mudar):
    campos = dict(papel="MANAGER", usuario=QUEM_CONFERE, usuario_id=None,
                  por_robo=False, afirmo=True, afirmacao=AFIRMACAO,
                  credito_data=DIA_DO_CREDITO, conta="Banco de ensaio, ag. 0001, cc 1",
                  agora="2026-10-23T10:00:00")
    campos.update(mudar)
    return PIX.confirmar_a_mao(con, pix_id, **campos)


# ------------------------------------------- PIX não é pagamento sem crédito


def test_pix_sem_credito_conferido_nao_se_lavra_por_tela_nenhuma():
    con = banco()
    tid = titulo(con)
    with pytest.raises(PT.ProtestoError, match="PIX NÃO É PAGAMENTO"):
        PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x",
                            valor_pago="1.765,14", forma_pagamento="PIX")
    assert _pagamentos(con, tid) == []
    assert PT.titulo(con, tid)["situacao"] == "APONTADO"


def test_registrar_o_pix_exige_o_comprovante_no_mesmo_ato(tmp_path):
    con = banco()
    tid = titulo(con)
    with pytest.raises(PIX.PixError, match="COMPROVANTE"):
        registrar(con, tid, tmp_path, conteudo=b"")
    with pytest.raises(PIX.PixError, match="não é"):
        registrar(con, tid, tmp_path, conteudo=b"isto nao e um pdf")
    assert con.execute("SELECT COUNT(*) FROM pt_pix").fetchone()[0] == 0


def test_o_pix_registrado_nao_e_pagamento_nao_vai_a_cra_e_nao_sela(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)
    p = _pix(con, r["pix_id"])
    assert p["situacao"] == PIX.AGUARDANDO
    assert p["valor_centavos"] == 176514 and p["data_pix"] == DIA_DO_CREDITO
    assert p["lancado_por"] == QUEM_LANCA
    # nenhum ato, a situação de antes, nada para a CRA
    assert _pagamentos(con, tid) == []
    assert PT.titulo(con, tid)["situacao"] == "APONTADO"
    assert [a for a in PR.pendentes(con) if a["tipo"] == "PAGAMENTO"] == []
    # o comprovante: anexado ao PIX, e o nome em disco não vem de fora
    [anexo] = con.execute("SELECT * FROM attachments WHERE entity_type='PT_PIX' "
                          "AND entity_id=?", (r["pix_id"],)).fetchall()
    assert anexo["original_name"] == "comprovante.pdf"
    assert anexo["stored_name"] == f"pix-{r['pix_id']}.pdf"
    assert Path(anexo["stored_path"]).read_bytes() == _pdf(str(tid))


def test_o_mesmo_comprovante_e_o_mesmo_e2e_nao_pagam_dois_titulos(tmp_path):
    con = banco()
    a, b, c = titulo(con, "1/1"), titulo(con, "2/1"), titulo(con, "3/1")
    registrar(con, a, tmp_path, conteudo=_pdf("mesmo"), e2eid=E2E)
    with pytest.raises(PIX.PixError, match="já foi apresentado"):
        registrar(con, b, tmp_path, conteudo=_pdf("mesmo"))
    with pytest.raises(PIX.PixError, match="já foi apresentado"):
        registrar(con, c, tmp_path, conteudo=_pdf("outro"), e2eid=E2E.lower()
                  .replace("e", "E", 1))
    with pytest.raises(PIX.PixError, match="32 caracteres"):
        registrar(con, c, tmp_path, conteudo=_pdf("outro"), e2eid="E123")


def test_um_titulo_um_pix_esperando(tmp_path):
    con = banco()
    tid = titulo(con)
    registrar(con, tid, tmp_path, conteudo=_pdf("1"))
    with pytest.raises(PIX.PixError, match="já tem o PIX"):
        registrar(con, tid, tmp_path, conteudo=_pdf("2"))


def test_o_pix_do_protestado_e_recusado_como_o_pagamento(tmp_path):
    con = banco()
    tid = titulo(con)
    con.execute("UPDATE pt_titulos SET situacao='PROTESTADO' WHERE id=?", (tid,))
    with pytest.raises(PT.ProtestoError, match="não se paga mais"):
        registrar(con, tid, tmp_path)


def test_enquanto_o_pix_espera_o_titulo_nao_anda(tmp_path):
    con = banco()
    tid = titulo(con)
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA)
    juntar_prova(con, tid)
    registrar(con, tid, tmp_path)
    with pytest.raises(PIX.PixError, match="AGUARDANDO O CRÉDITO"):
        PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    with pytest.raises(PIX.PixError, match="AGUARDANDO O CRÉDITO"):
        PT.lancar_desistencia(con, tid, motivo="Credor desistiu", agora=AGORA)
    with pytest.raises(PIX.PixError, match="AGUARDANDO O CRÉDITO"):
        PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x",
                            forma_pagamento="ESPECIE")
    assert PT.titulo(con, tid)["situacao"] == "INTIMADO"


# ------------------------------------------------------ o extrato do banco


def _credito(valor="1765.14", dia=DIA_DO_CREDITO, e2e=E2E, ident="T1",
             tipo="PIX", operacao="C", documento="00000000191",
             pagador="PESSOA DE ENSAIO") -> dict:
    return {"idTransacao": ident, "dataTransacao": dia, "tipoTransacao": tipo,
            "tipoOperacao": operacao, "valor": valor,
            "detalhes": {"tipoDetalhe": tipo, "endToEndId": e2e,
                         "nomePagador": pagador,
                         "cpfCnpjPagador": documento}}


def test_procurar_pelo_e2e_do_comprovante():
    r = PC.procurar([_credito()], valor_centavos=176514, dia="2026-10-20", e2eid=E2E)
    assert r["resultado"] == PC.ACHADO
    assert r["credito"]["id"] == "T1" and r["credito"]["dia"] == DIA_DO_CREDITO
    # o documento do pagador não se guarda
    assert "00000000191" not in json.dumps(r["credito"])


def test_procurar_pelo_e2e_que_o_extrato_nao_tem_nao_cai_para_o_valor():
    r = PC.procurar([_credito(e2e="")], valor_centavos=176514,
                    dia=DIA_DO_CREDITO, e2eid=E2E)
    assert r["resultado"] == PC.NAO_ACHADO


def test_procurar_pelo_e2e_com_outro_valor_diverge():
    r = PC.procurar([_credito(valor="1765.00")], valor_centavos=176514,
                    dia=DIA_DO_CREDITO, e2eid=E2E)
    assert r["resultado"] == PC.DIVERGE


def test_procurar_pelo_valor_e_pelo_dia_so_quando_e_um_so():
    um = PC.procurar([_credito(e2e="")], valor_centavos=176514, dia=DIA_DO_CREDITO)
    assert um["resultado"] == PC.ACHADO
    dois = PC.procurar([_credito(e2e="", ident="T1"), _credito(e2e="", ident="T2")],
                       valor_centavos=176514, dia=DIA_DO_CREDITO)
    assert dois["resultado"] == PC.AMBIGUO and dois["credito"] is None
    outro_dia = PC.procurar([_credito(e2e="", dia="2026-10-17")],
                            valor_centavos=176514, dia=DIA_DO_CREDITO)
    assert outro_dia["resultado"] == PC.NAO_ACHADO
    debito = PC.procurar([_credito(e2e="", operacao="D")], valor_centavos=176514,
                         dia=DIA_DO_CREDITO)
    assert debito["resultado"] == PC.NAO_ACHADO


def test_o_credito_usado_nao_confirma_outro_pix():
    r = PC.procurar([_credito()], valor_centavos=176514, dia=DIA_DO_CREDITO,
                    e2eid=E2E, ja_usados={"T1"})
    assert r["resultado"] == PC.JA_USADO
    r = PC.procurar([_credito(e2e="")], valor_centavos=176514, dia=DIA_DO_CREDITO,
                    ja_usados={"T1"})
    assert r["resultado"] == PC.NAO_ACHADO


def test_o_e2e_digitado_e_o_lido_do_comprovante():
    assert PC.e2e_valido(f"  {E2E} ") == E2E
    assert PC.e2e_valido("E123") is None
    pdf = b"%PDF-1.4\n(Identificador: " + E2E.encode() + b")\n"
    assert PC.e2e_do_comprovante(pdf, ".pdf") == E2E
    assert PC.e2e_do_comprovante(b"\x89PNG....", ".png") is None


def test_o_token_da_conferencia_so_le():
    assert PC.ClienteExtrato.escopos == "extrato.read"


class _Db:
    """O `db` da casa sobre uma conexão só — o que `conferir_no_banco` usa."""

    def __init__(self, con):
        self.con = con

    @contextmanager
    def connect(self):
        yield self.con

    @contextmanager
    def transaction(self):
        yield self.con
        self.con.commit()


class _Extrato:
    def __init__(self, creditos):
        self.creditos_dados, self.pedidos = creditos, []

    def creditos(self, inicio, fim):
        self.pedidos.append((inicio, fim))
        return list(self.creditos_dados)


def test_o_extrato_confirma_e_o_pagamento_se_lavra_com_a_data_do_credito(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path, e2eid=E2E)
    con.commit()
    extrato = _Extrato([_credito()])
    feito = PIX.conferir_no_banco(_Db(con), cliente=extrato,
                                  agora=datetime(2026, 10, 22, 9, 0))
    assert [c["pix_id"] for c in feito["confirmados"]] == [r["pix_id"]]
    assert extrato.pedidos == [("2026-10-15", "2026-10-22")]
    p = _pix(con, r["pix_id"])
    assert (p["situacao"], p["confirmacao_modo"]) == (PIX.CONFIRMADO, PIX.PELO_BANCO)
    assert p["credito_id"] == "T1" and p["credito_data"] == DIA_DO_CREDITO
    # confirmado não é lavrado: o título continua de pé, e não anda por cima
    assert PT.titulo(con, tid)["situacao"] == "APONTADO"
    with pytest.raises(PIX.PixError, match="conferido"):
        PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x",
                            forma_pagamento="ESPECIE")
    # o pagamento se lavra pelo caminho de sempre, com o PIX
    with pytest.raises(PT.ProtestoError, match="valor pago"):
        PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-22T10:00:00",
                            data_extenso="x", forma_pagamento="PIX",
                            pix_id=r["pix_id"], valor_pago="10,00")
    lavrado = PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-22T10:00:00",
                                  data_extenso="x", forma_pagamento="PIX",
                                  pix_id=r["pix_id"])
    assert PT.titulo(con, tid)["situacao"] == "PAGO"
    [ato] = _pagamentos(con, tid)
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe["valor_pago_centavos"] == 176514
    assert detalhe["data_do_pagamento"] == DIA_DO_CREDITO   # a do crédito
    assert str(ato["data_ato"]).startswith("2026-10-22")    # a do assentamento
    assert detalhe["forma_identificacao"] == f"E2E {E2E}"
    assert detalhe["pix"]["pix_id"] == r["pix_id"]
    assert _pix(con, r["pix_id"])["ato_id"] == lavrado["ato_id"]
    # e agora sim vai ao retorno
    assert [a["tipo"] for a in PR.pendentes(con)] == ["PAGAMENTO"]
    # o D da CENPROT leva a data do crédito
    import protesto_cenprot_xml as PXML
    assert PXML._data_da_ocorrencia(dict(ato)) == DIA_DO_CREDITO
    # o mesmo crédito não confirma um segundo PIX
    outro = titulo(con, "2/1")
    r2 = registrar(con, outro, tmp_path, conteudo=_pdf("segundo"))
    con.commit()
    segunda = PIX.conferir_no_banco(_Db(con), cliente=_Extrato([_credito()]),
                                    agora=datetime(2026, 10, 22, 11, 0))
    assert segunda["confirmados"] == []
    assert _pix(con, r2["pix_id"])["situacao"] == PIX.AGUARDANDO
    assert "não localizado" in _pix(con, r2["pix_id"])["ultima_consulta"]


def test_o_pagamento_por_pix_desfeito_pelo_selo_volta_a_esperar_o_lancamento(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)
    confirmar(con, r["pix_id"])
    lavrado = PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-23T11:00:00",
                                  data_extenso="x", forma_pagamento="PIX",
                                  pix_id=r["pix_id"])
    # como a rota desfaz quando o selo não sai
    con.execute("UPDATE pt_atos SET cancelado=1, motivo_cancelamento='Selo não "
                "emitido: ensaio' WHERE id=?", (lavrado["ato_id"],))
    con.execute("UPDATE pt_titulos SET situacao='APONTADO' WHERE id=?", (tid,))
    assert PIX.ativo_do_titulo(con, tid)["id"] == r["pix_id"]
    de_novo = PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-23T11:05:00",
                                  data_extenso="x", forma_pagamento="PIX",
                                  pix_id=r["pix_id"])
    assert _pix(con, r["pix_id"])["ato_id"] == de_novo["ato_id"]
    assert PIX.ativo_do_titulo(con, tid) is None


# ------------------------------------- a conciliação ao contrário (29/10/2026)


def test_dinheiro_que_entrou_sem_pagamento_e_pendencia_no_mesmo_dia(tmp_path):
    """O caso: o PIX entrou em 16/10 e ninguém lançou o pagamento até 21/10."""
    con = banco()
    tid = titulo(con)
    titulo(con, "2/1", valor="500,00", cpf="00000000272")
    pix = _credito(ident="C1", e2e="")
    alheio = _credito(ident="C2", e2e="", valor="80.00", tipo="TRANSFERENCIA",
                      documento="00000000353", pagador="OUTRA PESSOA")
    novos = PIX.conciliar_creditos(con, [pix, alheio], hoje=date(2026, 10, 16),
                                   agora="2026-10-16T18:00:00")
    assert [n["titulo_id"] for n in novos] == [tid]
    [c] = PIX.creditos_sem_pagamento(con)
    assert c["titulo_id"] == tid and c["tipo"] == "PIX" and c["documento_bate"] == 1
    assert "o valor bate" in c["candidatos"][0]["motivo"]
    # o documento de quem pagou não se guarda
    gravado = dict(con.execute("SELECT * FROM pt_creditos_banco").fetchone())
    assert "00000000191" not in json.dumps(gravado, default=str)
    # rodar de novo não duplica
    assert PIX.conciliar_creditos(con, [pix], hoje=date(2026, 10, 16),
                                  agora="2026-10-16T19:00:00") == []
    # pendência no mesmo dia (sexta, 16/10), atrasada no dia útil seguinte (19/10)
    def do_credito(hoje):
        return [p for p in PIX.pendencias_do_pix(con, hoje=hoje, feriados=set())
                if p["especie"] == PIX.ESPECIE_CREDITO]
    [p] = do_credito("2026-10-16")
    assert {"titulo_id", "numero_titulo", "protocolo", "explicacao"} <= set(p)
    assert p["titulo_id"] == tid and not p["atrasado"]
    assert "SEM PAGAMENTO LANÇADO" in p["explicacao"]
    [p] = do_credito("2026-10-19")
    assert p["atrasado"] and "ATRASADO" in p["explicacao"]
    assert PIX.para_a_ficha(con, tid)["creditos_sem_pagamento"]
    # lançado o PIX do título, o dinheiro sai da lista sozinho
    registrar(con, tid, tmp_path)
    assert PIX.creditos_sem_pagamento(con) == []
    assert do_credito("2026-10-21") == []


def test_o_credito_casa_pelo_documento_mesmo_com_outro_valor():
    con = banco()
    tid = titulo(con)
    [n] = PIX.conciliar_creditos(con, [_credito(ident="C3", e2e="", valor="1900.00")],
                                 hoje=date(2026, 10, 16), agora="2026-10-16T18:00:00")
    assert n["titulo_id"] == tid
    [c] = PIX.creditos_sem_pagamento(con)
    assert "documento de quem pagou" in c["candidatos"][0]["motivo"]
    assert "valor" not in c["candidatos"][0]["motivo"]


def test_o_descarte_e_do_oficial_ou_do_gerente_e_tem_motivo():
    con = banco()
    titulo(con)
    PIX.conciliar_creditos(con, [_credito(ident="C4", e2e="")],
                           hoje=date(2026, 10, 16), agora="2026-10-16T18:00:00")
    [c] = PIX.creditos_sem_pagamento(con)
    with pytest.raises(PIX.PixError, match="oficial ou do gerente"):
        PIX.descartar_credito(con, c["id"], papel="USER", usuario=QUEM_LANCA,
                              motivo="não é de título", agora=AGORA)
    with pytest.raises(PIX.PixError, match="pelo menos"):
        PIX.descartar_credito(con, c["id"], papel="MANAGER", usuario=QUEM_CONFERE,
                              motivo="não", agora=AGORA)
    PIX.descartar_credito(con, c["id"], papel="MANAGER", usuario=QUEM_CONFERE,
                          motivo="é o aluguel do imóvel da serventia", agora=AGORA)
    assert PIX.creditos_sem_pagamento(con) == []


def test_a_conferencia_le_o_extrato_mesmo_sem_pix_esperando():
    con = banco()
    tid = titulo(con)
    con.commit()
    extrato = _Extrato([_credito(ident="C9", e2e="")])
    r = PIX.conferir_no_banco(_Db(con), cliente=extrato,
                              agora=datetime(2026, 10, 16, 18, 0))
    assert extrato.pedidos == [("2026-10-12", "2026-10-16")]
    assert [n["titulo_id"] for n in r["sem_pagamento"]] == [tid]


# ------------------------------------------------- a confirmação à mão


def test_a_confirmacao_a_mao_e_do_oficial_ou_do_gerente_e_nunca_de_quem_lancou(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)
    with pytest.raises(PIX.PixError, match="oficial ou do gerente"):
        confirmar(con, r["pix_id"], papel="USER")
    with pytest.raises(PIX.PixError, match="Quem lançou o PIX"):
        confirmar(con, r["pix_id"], usuario=QUEM_LANCA.lower())
    with pytest.raises(PIX.PixError, match="robô"):
        confirmar(con, r["pix_id"], por_robo=True)
    assert _pix(con, r["pix_id"])["situacao"] == PIX.AGUARDANDO


def test_a_confirmacao_a_mao_exige_a_afirmacao_expressa_com_o_valor(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)
    with pytest.raises(PIX.PixError, match="AFIRMAÇÃO EXPRESSA"):
        confirmar(con, r["pix_id"], afirmo=False)
    with pytest.raises(PIX.PixError, match="AFIRMAÇÃO EXPRESSA"):
        confirmar(con, r["pix_id"], afirmacao="Afirmo, sob minha responsabilidade, que sim")
    with pytest.raises(PIX.PixError, match="dizer o valor"):
        confirmar(con, r["pix_id"], afirmacao=AFIRMACAO.replace("1.765,14", "mil reais"))
    with pytest.raises(PIX.PixError, match="conta"):
        confirmar(con, r["pix_id"], conta="")
    with pytest.raises(PIX.PixError, match="antes do PIX"):
        confirmar(con, r["pix_id"], credito_data="2026-10-15")
    feito = confirmar(con, r["pix_id"])
    assert feito["regra"] == "PIX_SEM_CREDITO_CONFERIDO"
    assert set(feito) >= {"regra", "afirmacao", "o_que_faltava"}
    assert "não foi localizado" in feito["o_que_faltava"]
    p = _pix(con, r["pix_id"])
    assert (p["situacao"], p["confirmacao_modo"]) == (PIX.CONFIRMADO, PIX.A_MAO)
    assert p["confirmado_por"] == QUEM_CONFERE and p["afirmacao"] == feito["afirmacao"]


def test_o_pix_dado_por_nao_confirmado_solta_o_titulo(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)
    with pytest.raises(PIX.PixError, match="oficial ou do gerente"):
        PIX.dar_por_nao_confirmado(con, r["pix_id"], papel="USER", usuario=QUEM_LANCA,
                                   motivo="nenhum crédito no extrato", agora=AGORA)
    with pytest.raises(PIX.PixError, match="Escreva por que"):
        PIX.dar_por_nao_confirmado(con, r["pix_id"], papel="ADMIN", usuario=QUEM_CONFERE,
                                   motivo="não", agora=AGORA)
    PIX.dar_por_nao_confirmado(con, r["pix_id"], papel="ADMIN", usuario=QUEM_CONFERE,
                               motivo="conferido o extrato do período, nenhum PIX",
                               agora=AGORA)
    assert _pix(con, r["pix_id"])["situacao"] == PIX.NAO_CONFIRMADO
    PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x",
                        valor_pago="1.765,14", forma_pagamento="ESPECIE")
    assert PT.titulo(con, tid)["situacao"] == "PAGO"


# ---------------------------------------------------------- a pendência


def test_a_pendencia_do_pix_passa_de_um_dia_util(tmp_path):
    con = banco()
    tid = titulo(con)
    r = registrar(con, tid, tmp_path)            # lançado numa quarta, 21/10
    assert PIX.pendencias_do_pix(con, hoje="2026-10-22", feriados=set()) == []
    [p] = PIX.pendencias_do_pix(con, hoje="2026-10-26", feriados=set())
    assert {"titulo_id", "numero_titulo", "protocolo", "explicacao"} <= set(p)
    assert p["titulo_id"] == tid and p["pix_id"] == r["pix_id"]
    assert p["especie"] == PIX.AGUARDANDO and "NÃO está pago" in p["explicacao"]
    # o gancho do roteiro chama só com a conexão
    assert isinstance(PIX.pendencias_do_pix(con), list)
    # confirmado e não lavrado continua pendente, com a outra frase
    confirmar(con, r["pix_id"])
    [p] = PIX.pendencias_do_pix(con, hoje="2026-10-28", feriados=set())
    assert p["especie"] == "LAVRAR" and "não foi lavrado" in p["explicacao"]


# --------------------------- o furo do item 4: o retorno com ato desfeito


@pytest.fixture()
def cra(monkeypatch):
    import centrais_cred as CRED
    import cra21_api as API
    import protesto_cra_envio as ENV
    monkeypatch.setattr(CRED, "tem", lambda *a, **k: True)
    monkeypatch.setattr(ENV, "user_dados_do_arquivo",
                        lambda conteudo, tipo="SDTBFOCRT": "<x/>")
    chamadas = []

    def nao_deveria(*a, **k):
        chamadas.append(a)
        raise AssertionError("o arquivo com ato desfeito foi à CRA")
    monkeypatch.setattr(API, "enviar_retorno", nao_deveria)
    return ENV, chamadas


def test_o_retorno_gerado_que_leva_ato_desfeito_nao_vai_a_cra(tmp_path, cra):
    ENV, chamadas = cra
    con = banco()
    valido, desfeito = titulo(con, "1/1"), titulo(con, "2/1")
    for tid in (valido, desfeito):
        PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x",
                            valor_pago="1.765,14", forma_pagamento="ESPECIE")
    r = PR.gerar(con, apresentante_codigo="001", dia="2026-10-21", agora=AGORA,
                 marca="A", usuario="MARIO EXEMPLO DOS SANTOS")
    rid = int(r["retorno_id"])
    # o selo falhou DEPOIS de o retorno ser gerado: o ato se desfaz
    [ato] = _pagamentos(con, desfeito)
    con.execute("UPDATE pt_atos SET cancelado=1, motivo_cancelamento='Selo não "
                "emitido: ensaio' WHERE id=?", (ato["id"],))
    con.commit()
    [gerado] = [g for g in PR.listar(con) if g["id"] == rid]
    assert gerado["atos_desfeitos"] == 1

    @contextmanager
    def transacao():
        yield con
        con.commit()
    with pytest.raises(ENV.CraEnvioError, match="DESFEITOS"):
        ENV.enviar_arquivo(transacao, rid, usuario="MARIO EXEMPLO DOS SANTOS")
    with pytest.raises(ENV.CraEnvioError, match="DESFEITOS"):
        ENV.enviar_arquivo(transacao, rid, forcar=True)
    assert chamadas == []
    # a saída: devolver os atos — o válido volta à fila, o desfeito não
    devolvidos = PR.devolver_atos_do_recusado(con, rid, agora=AGORA)
    assert len(devolvidos["atos"]) == 2
    assert [a["titulo_id"] for a in PR.pendentes(con)] == [valido]
    with pytest.raises(ENV.CraEnvioError, match="voltaram à fila"):
        ENV.enviar_arquivo(transacao, rid)
    assert chamadas == []


# -------------------------------------------------------------- as telas


SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _cliente(app, login):
    c = app.test_client()
    c.post("/login", data={"username": login, "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(tmp_path):
    from app import create_app
    from database import Database
    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    arquivo = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(arquivo)
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("beatriz", "BEATRIZ EXEMPLO", SENHA, "MANAGER")
    db.create_user("carla", "CARLA EXEMPLO", SENHA, "USER")
    db.set_settings({"modulo_protesto_ligado": "1",
                     "selo_trava_caixa": "DESLIGADA"})
    con = sqlite3.connect(arquivo)
    con.row_factory = sqlite3.Row
    tid = titulo(con)
    con.commit()
    con.close()
    from selador_de_bancada import ligar_o_selador
    sessao = {"app": app, "db": db, "banco": arquivo, "dados": dados,
              "titulo": tid}
    with ligar_o_selador(sessao):
        yield sessao


def _ler(casa) -> sqlite3.Connection:
    """Uma conexão nova a cada leitura: o que a tela gravou, já gravado."""
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def test_a_ficha_registra_o_pix_e_ele_so_vira_pagamento_conferido(casa):
    app, tid = casa["app"], casa["titulo"]
    carla, beatriz = _cliente(app, "carla"), _cliente(app, "beatriz")
    ficha = carla.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-pix-registrar" in ficha
    assert '<option value="PIX" disabled>' in ficha        # PIX não se escolhe sem crédito
    dia = (date.today() - timedelta(days=3)).isoformat()
    sem = postar_e_seguir(carla, f"/protesto/{tid}/pix",
                          {"csrf_token": _token(ficha), "valor_pix": "1.765,14",
                           "data_pix": dia}).get_data(as_text=True)
    assert "COMPROVANTE" in sem
    feito = postar_e_seguir(
        carla, f"/protesto/{tid}/pix",
        {"csrf_token": _token(ficha), "valor_pix": "1.765,14", "data_pix": dia,
         "comprovante": (io.BytesIO(_pdf("tela")), "comprovante do devedor.pdf")},
        content_type="multipart/form-data").get_data(as_text=True)
    assert "AGUARDANDO O" in feito and "data-pix-aguardando" in feito
    con = _ler(casa)
    [p] = con.execute("SELECT * FROM pt_pix").fetchall()
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "APONTADO"
    assert con.execute("SELECT COUNT(*) FROM audit_logs WHERE action="
                       "'PROTESTO_PIX_REGISTRADO'").fetchone()[0] == 1
    # o balcão não confirma à mão; quem lançou também não
    lista = carla.get("/protesto/pix").get_data(as_text=True)
    assert "data-pix-confirmar-a-mao" not in lista
    r = carla.post(f"/protesto/pix/{p['id']}/confirmar",
                   data={"csrf_token": _token(lista)})
    assert r.status_code == 403
    # o gerente confirma, com a afirmação
    tela = beatriz.get("/protesto/pix").get_data(as_text=True)
    assert "data-pix-confirmar-a-mao" in tela
    postar_e_seguir(beatriz, f"/protesto/pix/{p['id']}/confirmar",
                    {"csrf_token": _token(tela), "afirmo": "1",
                     "afirmacao": AFIRMACAO, "credito_data": dia,
                     "conta": "Banco de ensaio, ag. 0001, cc 1",
                     "titulo_id": str(tid), "volta": "lista"})
    con = _ler(casa)
    assert con.execute("SELECT situacao FROM pt_pix WHERE id=?",
                       (p["id"],)).fetchone()[0] == PIX.CONFIRMADO
    auditada = con.execute(
        "SELECT entity_type, details FROM audit_logs WHERE action='AFIRMACAO_EXPRESSA' "
        "ORDER BY id DESC LIMIT 1").fetchone()
    assert auditada["entity_type"] == "pt_pix"
    assert json.loads(auditada["details"])["regra"] == "PIX_SEM_CREDITO_CONFERIDO"
    # a ficha leva o PIX no formulário do pagamento, e ele se lavra
    ficha = carla.get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-pix-para-lavrar" in ficha
    assert f'name="pix_id" value="{p["id"]}"' in ficha
    lancado = postar_e_seguir(carla, f"/protesto/{tid}/lancar",
                              {"csrf_token": _token(ficha), "ato": "PAGAMENTO",
                               "forma_pagamento": "PIX", "pix_id": str(p["id"]),
                               "selo": "AVESVD000000NARRKWVNJCRSVO21"}
                              ).get_data(as_text=True)
    assert "Pagamento lançado" in lancado
    con = _ler(casa)
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "PAGO"
    # o Livro de Pagamentos diz a data do crédito
    import protesto_livros as PLIV
    [linha] = PLIV.livro_de_pagamentos(con)
    assert f"crédito em {dia[8:10]}/{dia[5:7]}/{dia[:4]}" in linha["ocorrencias"]
