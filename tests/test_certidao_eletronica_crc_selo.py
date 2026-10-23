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


def test_o_selo_sai_pelo_caminho_geral_com_o_14_5_7_e_sem_folha(bancada):
    """ESTE TESTE ESPERAVA A SEGUNDA VIA até 23/10/2026 — e o aparelho real a
    recusou na certidão 171 («É obrigatório informar os dados utilizados no
    papel moeda»). Por ordem do oficial o selo da certidão eletrônica vai pelo
    caminho geral do civil, no envelope dos 60 selos 14.5.7 de 2022–2024."""
    s, aparelho = bancada["s"], bancada["aparelho"]
    aid = _semear(s)
    r = _emitir_selo_crc(s, aid, requerente="BEATRIZ EXEMPLO")
    html = r.get_data(as_text=True)
    assert any("Selo da certidão eletrônica:" in a for a in _avisos(html)), _avisos(html)
    selos = [p for p in aparelho.pedidos if p["caminho"].startswith("/selo/")]
    assert len(selos) == 1, [p["caminho"] for p in aparelho.pedidos]
    assert selos[0]["caminho"].endswith("/selo/civil/atos-em-geral")
    corpo = json.loads(selos[0]["corpo"])
    # O `escrevente` no alto do envelope é da SEGUNDA TRANCA de `obter_selo`
    # (máquina não assina), e vai em todo envelope do civil que não o traz em
    # cima — as certidões da segunda via saem assim e o aparelho as aceita.
    topo = corpo.pop("escrevente", None)
    assert topo in (None, corpo["dadosSelo"]["escrevente"])
    assert sorted(corpo) == ["codigoAto", "dadosSelo", "nomesPartes", "quantidade"]
    assert corpo["codigoAto"] == "14.5.7"
    assert corpo["quantidade"] == 1
    assert sorted(corpo["dadosSelo"]) == ["escrevente", "versaoTabelaDeCustas"]
    parte = corpo["nomesPartes"]["parteAto"][0]
    assert corpo["nomesPartes"]["nomePartes"] == [parte["nome"]] and parte["nome"]
    assert len(parte["documento"]) == 11
    assert "papelMoeda" not in json.dumps(corpo)
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


def test_so_a_certidao_eletronica_vai_pelo_caminho_geral():
    """«Aplicar essa regra só pro selo da certidão eletrônica» — o oficial,
    23/10/2026. A certidão comum continua pela segunda via da espécie."""
    assert AS.CAMINHO_CERTIDAO_ELETRONICA_CRC == "/selo/civil/atos-em-geral"
    assert AS.caminho_do_civil("NASCIMENTO", "CERTIDAO") == \
        "/selo/civil/nascimento/segunda-via"


def test_o_isento_do_caminho_geral_vai_como_a_casa_mandava():
    env = AS.envelope_da_certidao_eletronica_crc(
        nome_parte="JOAO ENSAIO", documento="", escrevente="CARLA ENSAIO",
        versao_tabela="0120260101", isento=True, motivo_isencao="art. 30 da lei")
    assert env["dadosSelo"]["isentoGratuito"] == "ISENTO"
    assert env["dadosSelo"]["motivoIsentoGratuito"] == "ART. 30 DA LEI"
    assert env["nomesPartes"]["parteAto"][0]["documento"] == "00000000000"
    with pytest.raises(AS.AtoError, match="motivo"):
        AS.envelope_da_certidao_eletronica_crc(
            nome_parte="JOAO ENSAIO", documento="", escrevente="CARLA ENSAIO",
            versao_tabela="0120260101", isento=True)


def test_o_codigo_de_validacao_que_o_selador_devolve_aparece_na_tela(bancada):
    """«O código de validação vem quando gera o selo pelo selador» — o oficial,
    23/10/2026. O leitor guardava só número, texto, data e saldo; o resto da
    resposta se perdia. Agora o que vier a mais aparece no aviso, como veio,
    e a resposta inteira fica anotada em `selador_respostas.jsonl`."""
    s, aparelho = bancada["s"], bancada["aparelho"]
    aparelho.campos_a_mais = {"codigoValidacao": "ABCD1234ENSAIO"}
    aid = _semear(s)
    html = _emitir_selo_crc(s, aid).get_data(as_text=True)
    aviso = next(a for a in _avisos(html) if "Selo da certidão eletrônica:" in a)
    assert "codigoValidacao: ABCD1234ENSAIO" in aviso
    anotado = Path(s["app"].config["DATA_DIR"]) / "selador_respostas.jsonl"
    assert "ABCD1234ENSAIO" in anotado.read_text(encoding="utf-8")


def test_sem_campo_a_mais_o_aviso_diz_que_nao_veio_codigo(bancada):
    s = bancada["s"]
    aid = _semear(s)
    html = _emitir_selo_crc(s, aid).get_data(as_text=True)
    aviso = next(a for a in _avisos(html) if "Selo da certidão eletrônica:" in a)
    assert "não devolveu código de validação" in aviso


def test_o_leitor_guarda_o_que_veio_alem_do_contrato():
    import selador
    selos = selador.ler_resposta({"resumos": [{
        "numeroSelo": "CERELE000000ENSAIO0000000001", "textoSelo": "x",
        "dataGeracao": "2026-10-23", "saldoRemanescente": 1.0,
        "codigoValidacao": "ZZZ999"}]})
    assert dict(selos[0].extras) == {"codigoValidacao": "ZZZ999"}
