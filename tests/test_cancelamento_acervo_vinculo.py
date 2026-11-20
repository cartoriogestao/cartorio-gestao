"""Cancelamento/baixa em atos de acervo: vínculo cancelado_por_ato_id e teor inteiro na IA.

Pedido 20/11/2026 (matrícula 1.197): AV de baixa no acervo citava R-4 e R-5 no teor,
mas ri_atos ficava cancelado=0; a revisão por IA truncava o teor e perdia o R-04 no fim.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_cancelamentos_sem_marca as LISTA  # noqa: E402
import ri_onus as ONUS  # noqa: E402
import ri_onus_ia as RONIA  # noqa: E402
from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


def _a(tipo, natureza, teor="", cancelado=0):
    return {"tipo": tipo, "natureza_titulo": natureza, "teor": teor,
            "cancelado": cancelado}


def _entrar(app, usuario: str):
    c = app.test_client()
    c.post("/login",
           data={"username": usuario, "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


@pytest.fixture()
def casa(cg_casa):
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    return {**cg_casa, "oficial": _entrar(cg_casa["app"], "mario")}


def _mid(casa, numero="1197", tipo_ficha="ACERVO") -> int:
    with casa["db"].transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO ri_matriculas
               (numero, livro, livro_norm, situacao, tipo_ficha, origem,
                criado_em, data_abertura, cidade, uf)
               VALUES (%s, '2-F', '2F', 'ATIVA', %s, 'MANUAL',
                       '2026-10-27', '2026-10-01', 'Cidade Exemplo', 'MA')""",
            (numero, tipo_ficha))
        return int(bd.valor("SELECT id FROM ri_matriculas WHERE numero=%s", (numero,)))


def _ato(casa, mid, tipo, numero, natureza, teor="teor", *, aid=None):
    with casa["db"].transaction() as con:
        bd = banco(con)
        if aid is None:
            bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    cancelado, hash_ato, lavrado_em)
                   VALUES (%s,%s,%s,'2026-10-27',%s,%s,0,%s,'2026-10-27')""",
                (mid, tipo, numero, natureza, teor, f"h-{tipo}-{numero}-{mid}"))
        else:
            bd.escrever(
                """INSERT INTO ri_atos
                   (id, matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    cancelado, hash_ato, lavrado_em)
                   VALUES (%s,%s,%s,%s,'2026-10-27',%s,%s,0,%s,'2026-10-27')""",
                (aid, mid, tipo, numero, natureza, teor, f"h{aid}"))
        return int(bd.valor(
            "SELECT id FROM ri_atos WHERE matricula_id=%s AND tipo=%s AND numero=%s",
            (mid, tipo, numero)))


# ------------------------------------------------------------------ lista / teor

def test_baixa_na_natureza_entra_na_lista_de_cancelamento_sem_marca():
    assert LISTA.e_de_cancelamento(natureza="Baixa de hipoteca cedular")
    assert LISTA.e_de_cancelamento(
        teor="AV-06/1.197 — fica BAIXADO os Registros R-05/1197 e R-04/1197.")
    assert not LISTA.e_de_cancelamento(natureza="Penhora", teor="Penhora no rosto da matrícula.")


def test_ids_do_formulario_aceitam_varios():
    class F(dict):
        def getlist(self, k):
            v = self.get(k)
            if v is None:
                return []
            return v if isinstance(v, list) else [v]
    assert LISTA.ids_do_formulario(F(cancela_ato_id=["10", "20", "10"])) == [10, 20]
    assert LISTA.ids_do_formulario(F(cancela_ato_id="7")) == [7]


def test_citados_do_teor_acham_r04_no_fim_da_frase(casa):
    mid = _mid(casa)
    _ato(casa, mid, "R", 4, "Hipoteca 1º grau")
    _ato(casa, mid, "R", 5, "Hipoteca 2º grau")
    _ato(casa, mid, "AV", 6, "Baixa de hipoteca")
    teor = ("AV-06/1.197 — " + ("x" * 200)
            + " fica BAIXADO os Registros R-05/1197 e R-04/1197.")
    with casa["db"].connect() as con:
        citados = LISTA.citados_do_teor(banco(con), mid, teor, av_numero=6)
    assert [(c["tipo"], c["numero"]) for c in citados] == [("R", 5), ("R", 4)]


def test_lista_so_acervo_ignora_ficha_estruturada(casa):
    mid_e = _mid(casa, "5000", "ESTRUTURADA")
    mid_a = _mid(casa, "1197", "ACERVO")
    for mid in (mid_e, mid_a):
        _ato(casa, mid, "R", 2, "Hipoteca")
        with casa["db"].transaction() as con:
            banco(con).escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    modelo_codigo, cancelado, hash_ato, lavrado_em)
                   VALUES (%s,'AV',3,'2026-10-27','Cancelamento de Hipoteca',
                           'cancelado o R-2/x', 'AV-CANCELAMENTO', 0, %s, '2026-10-27')""",
                (mid, f"hav-{mid}"))
    with casa["db"].connect() as con:
        todas = LISTA.listar(con)
        so = LISTA.listar(con, so_acervo=True)
    assert {x["matricula"] for x in todas} >= {"5000", "1197"}
    assert [x["matricula"] for x in so] == ["1197"]


# ------------------------------------------------------------------ ônus / IA

def test_averbacao_de_baixa_nao_e_onus():
    assert ONUS.classificar(
        _a("AV", "Baixa de hipoteca", "BAIXADO R-4 e R-5")) is None
    assert ONUS.classificar(
        _a("AV", "Quitação de cédula", "quitado o R-2")) is None


def test_classificar_le_natureza_de_baixa_mesmo_com_teor_longo():
    teor = ("AV-06 — " + ("texto. " * 900)
            + "fica BAIXADO o Registro R-04/1197 da hipoteca cedular.")
    assert len(teor) > 4000
    assert ONUS.classificar(_a("AV", "Baixa", teor)) is None


def test_dossie_da_ia_preserva_a_cauda_quando_passa_do_limite(casa, monkeypatch):
    mid = _mid(casa, "4017", "ESTRUTURADA")
    with casa["db"].transaction() as con:
        bd = banco(con)
        bd.escrever("UPDATE ri_matriculas SET teor=%s WHERE id=%s",
                    ("ficha " * 50, mid))
        for n in range(1, 6):
            corpo = ("ATO " + str(n) + " " + ("bloco. " * 8000)
                     + (f" fica BAIXADO R-04/1197." if n == 5 else ""))
            bd.escrever(
                """INSERT INTO ri_atos
                   (matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    cancelado, hash_ato, lavrado_em)
                   VALUES (%s,'AV',%s,'2026-10-27','Baixa',%s,0,%s,'2026-10-27')""",
                (mid, n, corpo, f"h{n}"))
    monkeypatch.setattr(RONIA, "LIMITE_DO_DOSSIE", 20_000)
    with casa["db"].connect() as con:
        dossie = RONIA.dossie(con, mid)
    assert "R-04/1197" in dossie
    assert len(dossie) <= 20_000


def test_categoria_da_ia_le_teor_inteiro():
    teor = ("x" * 400) + " CITAÇÃO DE AÇÃO REAL contra o proprietário."
    assert RONIA.categoria(_a("AV", None, teor)) == RONIA.ACAO


# ------------------------------------------------------------------ lavratura acervo

def test_lavrar_av_de_baixa_no_acervo_marca_os_dois_r_citados(casa):
    """Sem modelo e sem cancela_ato_id: o teor da baixa aponta R-5 e R-4."""
    mid = _mid(casa)
    r4 = _ato(casa, mid, "R", 4, "Hipoteca 1º grau")
    r5 = _ato(casa, mid, "R", 5, "Hipoteca 2º grau")
    teor = ("AV-06/1.197 — fica BAIXADO os Registros R-05/1197 e R-04/1197 "
            "das cédulas, restando o imóvel liberado.")
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/atos", data={
        "csrf_token": _token(tela),
        "tipo": "AV", "numero": "6", "data_ato": "2026-10-27",
        "natureza_titulo": "Baixa de hipoteca",
        "teor": teor, "modelo_codigo": "",
        "protocolo": "", "prenotacao": "", "cnib_protocolo": "",
        "emolumentos": "", "base_calculo": "",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        bd = banco(con)
        av = bd.um("SELECT id FROM ri_atos WHERE matricula_id=%s AND tipo='AV' AND numero=6",
                   (mid,))
        assert av, "a AV-06 de acervo não foi lavrada"
        for rid in (r4, r5):
            row = bd.um("SELECT cancelado, cancelado_por_ato_id FROM ri_atos WHERE id=%s",
                        (rid,))
            assert int(row["cancelado"]) == 1 and int(row["cancelado_por_ato_id"]) == int(av["id"]), row


def test_lavrar_com_dois_cancela_ato_id_marca_ambos(casa):
    mid = _mid(casa)
    r4 = _ato(casa, mid, "R", 4, "Hipoteca 1º grau")
    r5 = _ato(casa, mid, "R", 5, "Hipoteca 2º grau")
    c = casa["oficial"]
    tela = c.get(f"/registro-imoveis/{mid}?lavrar=1").get_data(as_text=True)
    c.post(f"/registro-imoveis/{mid}/atos", data={
        "csrf_token": _token(tela),
        "tipo": "AV", "numero": "6", "data_ato": "2026-10-27",
        "natureza_titulo": "Baixa de hipoteca",
        "teor": "AV-06 — baixa das hipotecas.",
        "cancela_ato_id": [str(r4), str(r5)],
        "modelo_codigo": "", "protocolo": "", "prenotacao": "",
        "cnib_protocolo": "", "emolumentos": "", "base_calculo": "",
    }, follow_redirects=True)
    with casa["db"].connect() as con:
        bd = banco(con)
        av = bd.um("SELECT id FROM ri_atos WHERE matricula_id=%s AND tipo='AV' AND numero=6",
                   (mid,))
        assert av
        for rid in (r4, r5):
            row = bd.um("SELECT cancelado, cancelado_por_ato_id FROM ri_atos WHERE id=%s",
                        (rid,))
            assert int(row["cancelado"]) == 1 and int(row["cancelado_por_ato_id"]) == int(av["id"])


# ------------------------------------------------------------------ script 1.197

def test_script_marcar_1197_mede_e_aplica(casa):
    import tools.marcar_cancelamentos_matricula_1197 as SCR

    with casa["db"].transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO ri_matriculas
               (id, numero, livro, livro_norm, situacao, tipo_ficha, origem, criado_em)
               VALUES (4967, '1197', '2-F', '2F', 'ENCERRADA', 'ACERVO', 'MANUAL',
                       '2026-10-27')""")
        for aid, tipo, numero, nat in (
                (4725, "AV", 3, "Cancelamento"),
                (4726, "R", 4, "Hipoteca 1º"),
                (4727, "R", 5, "Hipoteca 2º"),
                (4728, "AV", 6, "Baixa"),
                (4800, "R", 2, "Registro")):
            bd.escrever(
                """INSERT INTO ri_atos
                   (id, matricula_id, tipo, numero, data_ato, natureza_titulo, teor,
                    cancelado, hash_ato, lavrado_em)
                   VALUES (%s, 4967, %s, %s, '2026-10-27', %s, 'teor', 0, %s, '2026-10-27')""",
                (aid, tipo, numero, nat, f"h{aid}"))
    with casa["db"].connect() as con:
        bd = banco(con)
        medicao = SCR.medir(bd)
        assert len(medicao["plano"]) == 3
        n = SCR.aplicar(bd, medicao["plano"])
        assert n == 3
        for alvo, por in ((4726, 4728), (4727, 4728), (4800, 4725)):
            row = bd.um("SELECT cancelado, cancelado_por_ato_id FROM ri_atos WHERE id=%s",
                        (alvo,))
            assert int(row["cancelado"]) == 1 and int(row["cancelado_por_ato_id"]) == por
