"""O selo da certidão eletrônica da CRC, emitido dentro do sistema — 22/10/2026.

    «no roteiro para emitir certidao da CRC eletronica precisa colocar na
     central o numero do selo, antes de subir o arquivo de importacao. Nesse
     momento as escreventes estao gerando o selo fora. Vamos criar um botao no
     registro para emitir o numero do selo da certidao eletronica dentro do
     sistema para copiar manualmente para a crc»; «o selo da certidao
     eletronica funciona com valores da CRC, nao entram imediatamente no
     caixa» — o oficial

O QUE ESTES TESTES GUARDAM
    **O botão está na ficha do assento**, e o selo sai pela segunda via da
    espécie com o item 14.5.7 e SEM folha de segurança (o precedente desta
    casa, 2023; o contrato a declara opcional).
    **A trava do selo pago não o barra**: o valor vem pela CRC, e a cobertura
    é a forma CENTRAL_CRC — que só vale para a certidão gravada com a
    finalidade da CRC e o item 14.5.7.
    **Selo que não sai cancela a certidão**, como na emissão de sempre.

Nomes fictícios, como em todo teste desta casa.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import re                                                           # noqa: E402

import ato_selado as AS                                              # noqa: E402
from test_rc_certidao_web import _con, _semear, _sessao, _token     # noqa: E402


def _avisos(html: str) -> list[str]:
    """Os avisos da tela (a caixa leva `data-aviso` e o botão de fechar)."""
    return [re.sub(r"<[^>]+>", "", a).strip() for a in re.findall(
        r'<div class="flash[^"]*"[^>]*>(.*?)<button', html, flags=re.DOTALL)]


@pytest.fixture()
def bancada(cg_casa):
    """O aparelho de mentira COM A TRAVA DE VERDADE: sem protocolo pago."""
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa, protocolo_pago=False) as aparelho:
        yield {"s": _sessao(cg_casa), "aparelho": aparelho, "db": cg_casa["db"]}


def _emitir_selo_crc(s, assento_id: int, **campos):
    html = s["c"].get(f"/rcpn/{assento_id}").get_data(as_text=True)
    return s["c"].post(f"/rcpn/{assento_id}/certidao-eletronica/selo",
                       data={"csrf_token": _token(html), **campos},
                       follow_redirects=True)


def test_o_botao_esta_na_ficha_do_assento(bancada):
    s = bancada["s"]
    aid = _semear(s)
    html = s["c"].get(f"/rcpn/{aid}").get_data(as_text=True)
    assert f"/rcpn/{aid}/certidao-eletronica/selo" in html
    assert "Emitir selo da certidão eletrônica (CRC)" in html


def test_o_selo_sai_pela_segunda_via_com_o_14_5_7_e_sem_folha(bancada):
    s, aparelho = bancada["s"], bancada["aparelho"]
    aid = _semear(s)
    r = _emitir_selo_crc(s, aid, requerente="BEATRIZ EXEMPLO")
    html = r.get_data(as_text=True)
    assert any("Selo da certidão eletrônica:" in a for a in _avisos(html)), _avisos(html)
    selos = [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]
    assert len(selos) == 1, [p["caminho"] for p in aparelho.pedidos]
    assert selos[0]["caminho"].endswith("/selo/civil/nascimento/segunda-via")
    corpo = json.loads(selos[0]["corpo"])
    assert corpo["codigoTipoAtoCertidao"] == "14.5.7"
    assert "papelMoeda" not in corpo
    con = _con(s)
    cert = con.execute("SELECT * FROM rc_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    cob = con.execute("SELECT forma FROM cx_selo_coberturas WHERE tabela='rc_certidoes' "
                      "AND ato_id=?", (cert["id"],)).fetchone()
    folhas_usadas = con.execute("SELECT COUNT(*) FROM pp_folhas "
                                "WHERE situacao <> 'EM BRANCO'").fetchone()[0]
    con.close()
    assert cert["selo"] and not cert["cancelada_em"]
    assert cert["finalidade"] == AS.FINALIDADE_CERTIDAO_ELETRONICA_CRC
    assert cert["requerente"] == "BEATRIZ EXEMPLO"
    assert cob["forma"] == AS.FORMA_CENTRAL_CRC
    assert folhas_usadas == 0


def test_a_forma_da_crc_nao_cobre_outra_certidao_nem_outro_item(bancada):
    s = bancada["s"]
    aid = _semear(s)
    _emitir_selo_crc(s, aid)
    con = _con(s)
    cid = con.execute("SELECT id FROM rc_certidoes ORDER BY id DESC LIMIT 1").fetchone()[0]
    con.close()
    from bd_nativo import banco
    with bancada["db"].connect() as con:
        bd = banco(con)
        assert AS.e_certidao_eletronica_da_crc(
            bd, "rc_certidoes", cid, {"codigoTipoAtoCertidao": "14.5.7"})
        # o mesmo ato com outro item, ou outra tabela, não é o da CRC
        assert not AS.e_certidao_eletronica_da_crc(
            bd, "rc_certidoes", cid, {"codigoTipoAtoCertidao": "14.5.1"})
        assert not AS.e_certidao_eletronica_da_crc(
            bd, "rc_atos", cid, {"codigoTipoAtoCertidao": "14.5.7"})
        # e a certidão comum (sem a finalidade da CRC) também não
        outra = _semear_certidao_comum(con, cid)
        assert not AS.e_certidao_eletronica_da_crc(
            bd, "rc_certidoes", outra, {"codigoTipoAtoCertidao": "14.5.7"})


def _semear_certidao_comum(con, modelo_id: int) -> int:
    """Uma cópia da certidão da CRC, sem a finalidade dela."""
    from bd_nativo import banco
    bd = banco(con)
    m = bd.um("SELECT * FROM rc_certidoes WHERE id=%s", (modelo_id,))
    novo = bd.escrever(
        """INSERT INTO rc_certidoes(numero, ano, assento_id, especie, nome,
               teor, hash_teor, emitida_em, emitida_por, finalidade)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
        (int(m["numero"]) + 1, m["ano"], m["assento_id"], m["especie"],
         m["nome"], m["teor"], m["hash_teor"], m["emitida_em"],
         m["emitida_por"], "Para fins de prova"))
    con.commit()
    return int(novo[0]["id"])


def test_selo_recusado_cancela_a_certidao(bancada):
    s, aparelho = bancada["s"], bancada["aparelho"]
    aid = _semear(s)
    aparelho.recusar_com = (400, {"message": "Ato não encontrado"})
    r = _emitir_selo_crc(s, aid)
    assert any("NÃO saiu" in a for a in _avisos(r.get_data(as_text=True)))
    con = _con(s)
    cert = con.execute("SELECT * FROM rc_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert cert["cancelada_em"] and "Selo não emitido" in cert["cancelada_motivo"]


def test_selo_isento_exige_motivo(bancada):
    s = bancada["s"]
    aid = _semear(s)
    r = _emitir_selo_crc(s, aid, selo_gratuito="1")
    assert any("motivo" in a for a in _avisos(r.get_data(as_text=True)))
    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM rc_certidoes").fetchone()[0] == 0
    con.close()
