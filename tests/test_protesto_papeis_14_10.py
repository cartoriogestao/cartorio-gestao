"""
Os papéis do Protesto conferidos contra o Código de Normas — 14/10/2026.

Pergunta do oficial: «os modelos dos atos estão acompanhando o cabeçalho padrão
da serventia e os requisitos legais no corpo?». A conferência disse que não:
o aviso não tinha papel, o edital dizia «no prazo legal», o instrumento dizia
«o documento abaixo descrito» e não descrevia nada, o termo só certificava a
intimação por edital, e o Livro de Registro de Pagamentos — inexistente desde
a inspeção de 2021 — não existia. Cada teste aqui guarda um desses buracos,
com o artigo ao lado (Código de Normas do TJMA, Prov. 28/2026).
"""
from __future__ import annotations

import sqlite3

import pytest

from test_protesto_aviso_web import (_con, _token, aviso_id, emitir, registrar,
                                     s, titulo_apontado)  # noqa: F401

import protesto as PT
import protesto_aviso as AV
import protesto_instrumento as PI
import protesto_livros as PLIV
import protesto_termo as TERMO
import sys as _sys
_sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "endereco_completo": "Rua Grande, 1, Centro",
      "serventia_telefone": "(99) 0000-0000",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}


def _horario(s, valor="segunda a sexta, das 8h às 17h"):
    con = _con(s)
    with con:
        con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES (?,?)",
                    (AV.CHAVE_DO_HORARIO, valor))
    con.close()


# ------------------------------------------------ o aviso (arts. 920 e 923)


def test_o_aviso_sem_horario_de_funcionamento_nao_sai(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    con = _con(s)
    aviso = AV.ler(con, aviso_id(s))
    with pytest.raises(AV.AvisoError, match="horário de funcionamento"):
        AV.montar_teor_do_aviso(con, aviso, sv=SV)


def test_o_aviso_traz_os_itens_do_art_920(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    _horario(s)
    con = _con(s)
    teor = AV.montar_teor_do_aviso(con, AV.ler(con, aviso_id(s)), sv=SV)
    tit = PT.titulo(con, tid)
    assert f"Protocolo n. {tit['protocolo']}" in teor
    assert "JOSÉ DA SILVA, CPF/CNPJ 047.855.123-88" in teor
    assert "RUA GRANDE, 10" in teor
    assert "Duplicata de Venda Mercantil por Indicação" in teor   # por extenso
    assert "Aceite:" in teor
    assert "LOJA CENTRAL LTDA, CPF/CNPJ" in teor                    # art. 923
    assert "Apresentante: BANCO DO BRASIL" in teor
    assert "Prazo-limite para pagamento:" in teor
    assert "segunda a sexta, das 8h às 17h" in teor
    assert "(99) 0000-0000" in teor


def test_o_prazo_limite_e_o_terceiro_dia_util_do_protocolo():
    """Lei 9.492, art. 12; CN-MA arts. 913, I e 925, § 4º. Protocolo de uma
    quinta (15/10/2026): sexta, segunda e terça — 20/10/2026."""
    con = conexao_de_teste()
    con.execute("CREATE TABLE settings(key TEXT PRIMARY KEY, value TEXT)")
    assert AV.prazo_limite(con, {"protocolo": "2610150001"}) == "2026-10-20"
    assert AV.prazo_limite(con, {"protocolo": "0"}) is None


def test_o_aviso_imprime_com_o_cabecalho_da_casa(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    _horario(s)
    r = s["c"].get(f"/protesto/avisos/{aviso_id(s)}.odt?formato=odt")
    assert r.status_code == 200
    assert r.data[:2] == b"PK"


def test_a_ficha_oferece_imprimir_o_aviso(s):
    tid = titulo_apontado(s)
    emitir(s, tid)
    html = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert f"/protesto/avisos/{aviso_id(s)}.odt" in html


# ------------------------------------------------- o edital (art. 922, § 3º)


def test_o_edital_traz_o_prazo_limite_e_nao_traz_apresentante_nem_credor(s):
    tid = titulo_apontado(s)
    con = _con(s)
    tit = PT.titulo(con, tid)
    teor = AV.montar_teor_do_edital(
        aviso={"devedor_nome": "JOSÉ DA SILVA", "devedor_documento": "04785512388"},
        titulo=tit, sv=SV, hoje="2026-10-14", limite="2026-10-20")
    assert "até 20/10/2026" in teor
    assert "Prazo-limite para pagamento: 20/10/2026" in teor
    assert "Apresentante:" not in teor and "Credor:" not in teor
    assert "(99) 0000-0000" in teor


# ---------------------------------------- o termo (art. 22, IV; CN-MA 914)


def test_o_termo_certifica_a_intimacao_pessoal_com_a_data():
    texto = TERMO.montar(motivo_protesto="1", pessoal_data="2026-10-10")
    assert "O devedor foi intimado pessoalmente em 10/10/2026." in texto


def test_o_termo_certifica_a_intimacao_digital():
    texto = TERMO.montar(motivo_protesto="1", pessoal_data="2026-10-10",
                         pessoal_digital=True)
    assert "por meio eletrônico" in texto


def test_o_termo_nao_diz_mais_sacado():
    """Na nota promissória e no cheque o devedor é o emitente (CN-MA 919, § 4º)."""
    texto = TERMO.montar(motivo_protesto="1", edital_data="2026-10-10")
    assert "Sacado" not in texto and "O devedor foi intimado por Edital" in texto


# ------------------------------------- o pagamento e o livro (art. 930)


def _intimado(s) -> int:
    tid = titulo_apontado(s)
    con = _con(s)
    with con:
        PT.lancar_intimacao(con, tid, modo="PESSOAL", agora="2026-10-10T10:00:00")
    con.close()
    return tid


def test_pagamento_em_cheque_exige_a_identificacao(s):
    tid = _intimado(s)
    con = _con(s)
    with pytest.raises(PT.ProtestoError, match="número do cheque"):
        PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                            data_extenso="x", forma_pagamento="CHEQUE")


def test_forma_de_pagamento_desconhecida_recusa(s):
    tid = _intimado(s)
    con = _con(s)
    with pytest.raises(PT.ProtestoError, match="Forma de pagamento"):
        PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                            data_extenso="x", forma_pagamento="FIADO")


def test_o_livro_de_pagamentos_traz_as_colunas_do_art_930(s):
    tid = _intimado(s)
    con = _con(s)
    with con:
        PT.lancar_pagamento(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                            data_extenso="x", valor_pago="1.310,45",
                            emolumentos="82,64", forma_pagamento="CHEQUE",
                            forma_identificacao="BB, cheque 000123")
    linhas = PLIV.livro_de_pagamentos(con, de="2026-10-01", ate="2026-10-31")
    assert len(linhas) == 1
    l = linhas[0]
    assert l["ordem"] is not None and l["protocolo"]
    assert l["natureza"] == "Duplicata de Venda Mercantil por Indicação"
    assert l["valor"] == "1.310,45" and l["emolumentos"] == "82,64"
    assert l["devedor"] == "JOSÉ DA SILVA" and l["favorecido"] == "LOJA CENTRAL LTDA"
    assert "pago por cheque — BB, cheque 000123" in l["ocorrencias"]


def test_o_livro_de_protocolo_traz_as_ocorrencias_com_data(s):
    tid = _intimado(s)
    con = _con(s)
    linhas = PLIV.livro_de_protocolo(con)
    l = next(x for x in linhas if x["titulo_id"] == tid)
    assert "intimado pessoalmente em 10/10/2026" in l["ocorrencias"]
    assert l["apresentante"] == "BANCO DO BRASIL"


def test_as_telas_dos_livros_abrem_e_imprimem(s):
    _intimado(s)
    for qual in ("pagamentos", "protocolo"):
        r = s["c"].get(f"/protesto/livros/{qual}?de=2000-01-01")
        assert r.status_code == 200, qual
        odt = s["c"].get(f"/protesto/livros/{qual}?de=2000-01-01&formato=odt")
        assert odt.status_code == 200 and odt.data[:2] == b"PK", qual
    assert s["c"].get("/protesto/livros/outro").status_code == 404


# ------------------------------------------- o instrumento (CN-MA art. 914)


def _protestado(s, motivo="1") -> int:
    tid = _intimado(s)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET motivo_protesto=? WHERE id=?",
                    (motivo, tid))
        PT.lancar_protesto(con, tid, sv=SV, agora="2026-10-14T10:00:00",
                           data_extenso="x")
    con.close()
    return tid


def test_o_instrumento_descreve_o_documento(s):
    tid = _protestado(s)
    con = _con(s)
    with con:
        r = PI.emitir(con, tid, serventia=SV["unit_name"],
                      agora="2026-10-14T11:00:00")
    teor = r["teor"]
    assert "Registro do protesto:" in teor
    assert "Protocolo n.º" in teor
    assert "Duplicata de Venda Mercantil por Indicação, n.º 9911/1" in teor
    assert "Devedor: JOSÉ DA SILVA" in teor
    assert "Apresentante: BANCO DO BRASIL" in teor
    assert "Motivo: falta de pagamento" in teor


def test_o_instrumento_sem_motivo_recusa_e_nao_inventa(s):
    tid = _protestado(s)
    con = _con(s)
    with con:
        con.execute("UPDATE pt_titulos SET motivo_protesto=NULL WHERE id=?", (tid,))
    with pytest.raises(PI.InstrumentoError, match="motivo do protesto"):
        PI.emitir(con, tid, serventia=SV["unit_name"],
                  agora="2026-10-14T11:00:00")


def test_o_instrumento_imprime(s):
    tid = _protestado(s)
    con = _con(s)
    with con:
        r = PI.emitir(con, tid, serventia=SV["unit_name"],
                      agora="2026-10-14T11:00:00")
    odt = s["c"].get(f"/protesto/instrumentos/{r['id']}/odt?formato=odt")
    assert odt.status_code == 200 and odt.data[:2] == b"PK"
    tela = s["c"].get("/protesto/instrumentos").get_data(as_text=True)
    assert f"/protesto/instrumentos/{r['id']}/odt" in tela
