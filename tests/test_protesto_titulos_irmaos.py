"""
Testes dos TÍTULOS IRMÃOS — os que dividem o mesmo protocolo (29/10/2026).

O CASO QUE ELES GUARDAM
    Duas parcelas do mesmo devedor, mesmo credor, MESMO protocolo e mesmo
    valor. O pagamento de uma foi lançado na outra; a paga foi protestada e a
    não paga ficou «paga». A ordem do oficial: não deixar a escrevente errar,
    e, se ela insistir, que afirme expressamente e fique o registro.

O QUE ELES CONFEREM
      - irmão é título com o mesmo protocolo; sem protocolo não há irmão;
      - com irmão EM ABERTO que se distingue (número ou vencimento), o
        pagamento, a desistência e o cancelamento exigem o número e o
        vencimento DO PAPEL: o do irmão é recusado dizendo de quem é, o que
        não bate com nenhum é recusado listando os títulos, e o deste passa e
        fica gravado no ato;
      - o irmão IDÊNTICO (o corresponsável da CDA: mesmo número, vencimento e
        valor) e o irmão já pago não travam — nenhum papel os distinguiria;
      - a afirmação expressa vence a trava só com a caixa E trinta letras
        além da fórmula; o robô não afirma; o texto vai ao ato;
      - a conferência acha o caso real (pago e protestado com o mesmo valor;
        pago o de vencimento posterior) e o cedente que diverge do registro
        de origem — e não corrige nada;
      - pela TELA: a ficha mostra os irmãos e o quadro «Qual título está no
        papel?»; a rota recusa o papel do irmão sem lançar nada; a afirmação
        fica no registro de auditoria `AFIRMACAO_EXPRESSA`.
"""
from __future__ import annotations

import glob
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import banco_pg                                  # noqa: E402
import protesto as PT                            # noqa: E402
import protesto_titulos_irmaos as IRM            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-10-29T10:00:00"
PROTOCOLO = "2601150001"
AFIRMACAO_BOA = ("Afirmo, sob minha responsabilidade, que o devedor declarou no "
                 "balcão que pagava a parcela de junho e não trouxe papel nenhum")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def _dados(numero: str, vencimento: str, valor: str, cpf: str) -> dict:
    return {
        "especie": "DMI", "numero_titulo": numero,
        "data_emissao": "2026-01-10", "data_vencimento": vencimento,
        "valor": valor, "saldo": valor, "praca_protesto": "CIDADE EXEMPLO",
        "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
        "cedente": {"nome": "EMPRESA EXEMPLO LTDA",
                    "documento": "00000001000055",
                    "cidade": "Cidade Exemplo", "uf": "MA"},
        "devedores": [{"nome": "DEVEDOR DE EXEMPLO", "CPF": cpf,
                       "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }


def _titulo(con, numero: str, vencimento: str, *, situacao: str = "APONTADO",
            protocolo: str | None = PROTOCOLO, valor: str = "230.00",
            cpf: str = "00000000191") -> int:
    """Um título já no banco, com o protocolo e a situação postos à mão: o que
    se testa aqui é o irmão, e não o apontamento."""
    tid = PT.cadastrar_titulo(con, _dados(numero, vencimento, valor, cpf),
                              origem="MANUAL", agora=AGORA)
    con.execute("UPDATE pt_titulos SET protocolo=?, situacao=? WHERE id=?",
                (protocolo, situacao, tid))
    return tid


def _ato(con, titulo_id: int, tipo: str = "PAGAMENTO") -> int:
    cur = con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json, origem,
               criado_em) VALUES (?,?,?,?,?,?)""",
        (titulo_id, tipo, AGORA, '{"forma_pagamento": "ESPECIE"}', "MANUAL",
         AGORA))
    return int(cur.lastrowid)


def _detalhe(con, ato_id: int) -> dict:
    return json.loads(con.execute("SELECT detalhe_json FROM pt_atos WHERE id=?",
                                  (ato_id,)).fetchone()["detalhe_json"])


def _parcelas(con, *, situacao_1="APONTADO", situacao_2="APONTADO"):
    """As duas parcelas do caso real: a /1 vence antes, a /2 depois."""
    p1 = _titulo(con, "4321/1", "2026-05-27", situacao=situacao_1)
    p2 = _titulo(con, "4321/2", "2026-06-27", situacao=situacao_2)
    return p1, p2


def _conferir(con, titulo_id, ato_id, ato="PAGAMENTO", **k):
    return IRM.conferir_e_anotar(con, titulo_id, ato, ato_id, quem="MARIO",
                                 agora=AGORA, **k)


# ------------------------------------------------------------ quem é irmão


def test_irmao_e_titulo_do_mesmo_protocolo():
    con = banco()
    p1, p2 = _parcelas(con)
    outro = _titulo(con, "9999/1", "2026-05-27", protocolo="2601150002")
    sem = _titulo(con, "8888/1", "2026-05-27", protocolo=None)
    irmaos = IRM.irmaos_de_varios(con, [p1, p2, outro, sem])
    assert [i["id"] for i in irmaos[p1]] == [p2]
    assert [i["id"] for i in irmaos[p2]] == [p1]
    assert outro not in irmaos and sem not in irmaos
    assert irmaos[p1][0]["distinguivel"] and irmaos[p1][0]["mesmo_devedor"]


def test_a_ficha_traz_este_e_os_irmaos_e_diz_se_trava():
    con = banco()
    _, p2 = _parcelas(con)
    q = IRM.quadro_da_ficha(con, p2)
    assert q["protocolo"] == PROTOCOLO
    assert q["este"]["numero_titulo"] == "4321/2"
    assert [i["numero_titulo"] for i in q["irmaos"]] == ["4321/1"]
    assert q["trava"] is True
    assert IRM.quadro_da_ficha(con, _titulo(con, "1/1", "2026-01-01",
                                            protocolo="2601150009")) is None


# ------------------------------------------------------------ a trava


def test_O_CASO_REAL_o_papel_do_irmao_e_recusado():
    """Na ficha da /2, com o papel da /1 na mão: quem digita o que está no
    papel digita a /1 — e o sistema não deixa lançar na /2."""
    con = banco()
    _, p2 = _parcelas(con)
    ato = _ato(con, p2)
    with pytest.raises(IRM.TituloIrmaoError) as erro:
        _conferir(con, p2, ato, numero="4321/1", vencimento="2026-05-27",
                  situacao_antes="APONTADO")
    frase = str(erro.value)
    assert "IRMÃO" in frase and "4321/1" in frase and "Nada foi lançado" in frase
    assert "afirmacao_expressa" not in _detalhe(con, ato)


def test_o_papel_deste_passa_e_a_conferencia_fica_no_ato():
    con = banco()
    _, p2 = _parcelas(con)
    ato = _ato(con, p2)
    feito = _conferir(con, p2, ato, numero="4321-2", vencimento="27/06/2026")
    assert "titulo_conferido" in feito
    detalhe = _detalhe(con, ato)
    assert detalhe["forma_pagamento"] == "ESPECIE"          # o que havia fica
    assert detalhe["titulo_conferido"]["numero"] == "4321-2"
    assert detalhe["titulo_conferido"]["vencimento"] == "2026-06-27"
    assert detalhe["titulo_conferido"]["por"] == "MARIO"


def test_sem_a_conferencia_recusa_com_a_frase_pronta():
    con = banco()
    _, p2 = _parcelas(con)
    with pytest.raises(IRM.TituloIrmaoError) as erro:
        _conferir(con, p2, _ato(con, p2))
    frase = str(erro.value)
    assert "Qual título está no papel?" in frase
    assert "NO PAPEL" in frase and "4321/1" in frase


def test_numero_sem_a_parcela_nao_bate_e_a_recusa_lista_os_titulos():
    con = banco()
    _, p2 = _parcelas(con)
    with pytest.raises(IRM.TituloIrmaoError) as erro:
        _conferir(con, p2, _ato(con, p2), numero="4321", vencimento="2026-06-27")
    frase = str(erro.value)
    assert "não conferem com nenhum" in frase
    assert "4321/1" in frase and "4321/2" in frase


def test_o_vencimento_do_irmao_tambem_e_recusado():
    """Número deste com o vencimento do irmão: o papel não é deste."""
    con = banco()
    _, p2 = _parcelas(con)
    with pytest.raises(IRM.TituloIrmaoError):
        _conferir(con, p2, _ato(con, p2), numero="4321/2",
                  vencimento="2026-05-27")


@pytest.mark.parametrize("ato", ["DESISTENCIA", "CANCELAMENTO"])
def test_a_desistencia_e_o_cancelamento_tambem_travam(ato):
    con = banco()
    _, p2 = _parcelas(con, situacao_1="PROTESTADO", situacao_2="PROTESTADO")
    with pytest.raises(IRM.TituloIrmaoError):
        _conferir(con, p2, _ato(con, p2, ato), ato=ato)


@pytest.mark.parametrize("ato", ["PROTESTO", "INTIMACAO", "APONTAMENTO"])
def test_os_outros_atos_nao_tem_trava(ato):
    con = banco()
    _, p2 = _parcelas(con)
    assert _conferir(con, p2, _ato(con, p2, ato), ato=ato) is None


def test_o_irmao_identico_o_corresponsavel_nao_trava():
    """A CDA com dois devedores: mesmo número, vencimento e valor. Nenhum
    papel distingue os dois — pedir a conferência seria o alarme que soa
    sempre."""
    con = banco()
    a = _titulo(con, "31420000001", "2026-03-01", cpf="00000000191")
    b = _titulo(con, "31420000001", "2026-03-01", cpf="00000000272")
    assert IRM.quadro_da_ficha(con, a)["trava"] is False
    assert _conferir(con, a, _ato(con, a)) is None
    assert IRM.irmaos_de_varios(con, [a])[a][0]["distinguivel"] is False
    assert b in [i["id"] for i in IRM.irmaos_de_varios(con, [a])[a]]


def test_o_irmao_ja_pago_nao_trava_mas_aparece_com_o_sinal():
    con = banco()
    p1, _ = _parcelas(con, situacao_2="PAGO")
    assert _conferir(con, p1, _ato(con, p1)) is None
    [irmao] = IRM.quadro_da_ficha(con, p1)["irmaos"]
    assert any("PAGO" in s for s in irmao["sinais"])
    # e o sinal do caso real: pago o de vencimento POSTERIOR
    assert any("POSTERIOR" in s for s in irmao["sinais"])


# ------------------------------------------------------- a afirmação expressa


def test_a_afirmacao_vence_a_trava_e_vai_ao_ato():
    con = banco()
    _, p2 = _parcelas(con)
    ato = _ato(con, p2)
    feito = _conferir(con, p2, ato, afirmo=True, afirmacao=AFIRMACAO_BOA)
    af = feito["afirmacao_expressa"]
    assert af["regra"] == IRM.REGRA
    assert af["afirmacao"] == AFIRMACAO_BOA
    assert "4321/1" in af["o_que_faltava"]
    assert _detalhe(con, ato)["afirmacao_expressa"]["afirmacao"] == AFIRMACAO_BOA


def test_a_afirmacao_vence_ate_o_papel_do_irmao_se_a_pessoa_insiste():
    """«Se insistir em algo que é erro, precisa afirmar expressamente e deixar
    log» — e o que faltava diz que o papel era do irmão."""
    con = banco()
    _, p2 = _parcelas(con)
    feito = _conferir(con, p2, _ato(con, p2), numero="4321/1",
                      vencimento="2026-05-27", afirmo=True,
                      afirmacao=AFIRMACAO_BOA)
    assert "IRMÃO" in feito["afirmacao_expressa"]["o_que_faltava"]


@pytest.mark.parametrize("afirmo,texto", [
    (True, "Afirmo, sob minha responsabilidade, que"),       # só a fórmula
    (True, "Afirmo, sob minha responsabilidade, que sim"),   # curta
    (False, AFIRMACAO_BOA),                                  # sem a caixa
])
def test_afirmacao_pela_metade_e_recusada(afirmo, texto):
    con = banco()
    _, p2 = _parcelas(con)
    with pytest.raises(IRM.TituloIrmaoError) as erro:
        _conferir(con, p2, _ato(con, p2), afirmo=afirmo, afirmacao=texto)
    assert "30" in str(erro.value)


def test_a_formula_sozinha_nao_conta_letra():
    assert IRM._letras(IRM.FORMULA) == 0
    assert IRM._letras(AFIRMACAO_BOA) >= IRM.MINIMO_DE_LETRAS


def test_robo_nao_afirma():
    con = banco()
    _, p2 = _parcelas(con)
    with pytest.raises(IRM.TituloIrmaoError) as erro:
        _conferir(con, p2, _ato(con, p2), afirmo=True, afirmacao=AFIRMACAO_BOA,
                  por_robo=True)
    assert "Robô não faz afirmação expressa" in str(erro.value)


def test_a_recusa_e_erro_de_regra_do_protesto():
    """A rota apanha `ProtestoError`: a recusa vira aviso, e não HTTP 500."""
    assert issubclass(IRM.TituloIrmaoError, PT.ProtestoError)
    assert issubclass(IRM.TituloIrmaoError, ValueError)


# ------------------------------------------------------------ a conferência


def test_a_conferencia_acha_o_caso_real_e_nao_corrige_nada():
    """Antes da correção do oficial: a /2 «paga», a /1 protestada."""
    con = banco()
    p1, p2 = _parcelas(con, situacao_1="PROTESTADO", situacao_2="PAGO")
    r = IRM.irmaos_incoerentes(con)
    assert r["protocolos"] == 1
    [g] = r["incoerentes"]
    texto = " ".join(g["frases"])
    assert "PAGO" in texto and "PROTESTADO" in texto and "mesmo valor" in texto
    assert "ANTERIOR" in texto
    sit = {row["id"]: row["situacao"] for row in con.execute(
        "SELECT id, situacao FROM pt_titulos")}
    assert sit[p1] == "PROTESTADO" and sit[p2] == "PAGO"


def test_a_conferencia_acha_a_mesma_divida_com_dois_desfechos():
    con = banco()
    _titulo(con, "31420000001", "2026-03-01", situacao="PAGO")
    _titulo(con, "31420000001", "2026-03-01", situacao="PROTESTADO",
            cpf="00000000272")
    [g] = IRM.irmaos_incoerentes(con)["incoerentes"]
    assert any("dois desfechos" in f for f in g["frases"])


def test_irmaos_coerentes_nao_aparecem():
    con = banco()
    _parcelas(con, situacao_1="PAGO", situacao_2="INTIMADO")
    r = IRM.irmaos_incoerentes(con)
    assert r["protocolos"] == 1 and r["incoerentes"] == []


def _acervo(tmp_path, linhas) -> Path:
    """Um acervo do E-Ofício com a tabela `tbSDT`, nas colunas que o layout da
    remessa dá ao cedente e ao sacador — calculadas, e não escritas."""
    caminho = tmp_path / "acervo_de_teste.sqlite3"
    ced = IRM._COLUNA_NO_ACERVO["cedente_nome"]
    sac = IRM._COLUNA_NO_ACERVO["cedente_nome_2"]
    a = banco_pg.conectar_sqlite(caminho, so_leitura=False)
    a.execute(f"CREATE TABLE tbSDT (intChave REAL, intProtocolo REAL, "
              f"{ced} TEXT, {sac} TEXT)")
    for i, (protocolo, cedente, sacador) in enumerate(linhas, start=1):
        a.execute("INSERT INTO tbSDT VALUES (?,?,?,?)",
                  (float(i), float(protocolo), cedente, sacador))
    a.commit()
    a.close()
    return caminho


def test_o_cedente_que_diverge_do_registro_de_origem(tmp_path):
    con = banco()
    certo = _titulo(con, "1/1", "2026-01-01", protocolo="2601150003")
    errado = _titulo(con, "2/1", "2026-01-01", protocolo="2601150004")
    vazio = _titulo(con, "3/1", "2026-01-01", protocolo="2601150005")
    sem = _titulo(con, "4/1", "2026-01-01", protocolo="2601150006")
    con.execute("UPDATE pt_titulos SET cedente_nome='OUTRA EMPRESA S A' WHERE id=?",
                (errado,))
    con.execute("UPDATE pt_titulos SET cedente_nome=NULL WHERE id=?", (vazio,))
    caminho = _acervo(tmp_path, [
        # o campo da CRA tem 45 posições: o nome cortado ainda é o mesmo
        ("2601150003", "EMPRESA EXEMPLO LTD", "EMPRESA EXEMPLO LTD"),
        ("2601150004", "EMPRESA EXEMPLO LTDA", ""),
        ("2601150005", "EMPRESA EXEMPLO LTDA", ""),
    ])
    acervo = banco_pg.conectar_sqlite(caminho)
    try:
        r = IRM.cedentes_divergentes(con, acervo)
        ficha = IRM.cedente_da_origem(con, dict(PT.titulo(con, errado)), acervo)
    finally:
        acervo.close()
    ids = {d["id"] for d in r["divergentes"]}
    assert ids == {errado, vazio}
    assert certo not in ids and sem not in ids
    assert r["vazios"] == 1 and r["conferidos"] == 3 and r["sem_registro"] >= 1
    assert ficha["confere"] is False
    assert ficha["nomes"] == ["EMPRESA EXEMPLO LTDA"]


def test_o_contrato_com_o_roteiro_do_protesto():
    """O roteiro do protesto chama `protesto_titulos_irmaos.pendencias_dos_
    irmaos(con)` PELO NOME, só com a conexão, e lê de cada linha `titulo_id`,
    `numero_titulo`, `protocolo`, `explicacao` e `origem` (a «ACERVO» ele
    ignora). Renomear quebra o roteiro sem erro: ele mostra «ainda não
    instalada»."""
    con = banco()
    p1, p2 = _parcelas(con, situacao_1="PROTESTADO", situacao_2="PAGO")
    linhas = IRM.pendencias_dos_irmaos(con)
    assert {ln["titulo_id"] for ln in linhas} == {p1, p2}
    for ln in linhas:
        assert {"titulo_id", "numero_titulo", "protocolo", "explicacao",
                "origem"} <= set(ln)
        assert ln["origem"] == IRM.ORIGEM_IRMAOS != "ACERVO"
        assert ln["protocolo"] == PROTOCOLO and "PAGO" in ln["explicacao"]


def test_sem_pendencia_o_roteiro_recebe_lista_vazia():
    con = banco()
    _parcelas(con, situacao_1="PAGO", situacao_2="INTIMADO")
    assert IRM.pendencias_dos_irmaos(con) == []


def test_sem_acervo_a_conferencia_nao_quebra():
    con = banco()
    _titulo(con, "1/1", "2026-01-01")
    r = IRM.resumo_para_o_painel(con, None)
    assert r["cedentes_divergentes"] == 0 and r["cedentes_sem_registro"] == 1


# ------------------------------------------------------------ pela tela


SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(tmp_path):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    caminho = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(caminho)
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"modulo_protesto_ligado": "1",
                     "selo_trava_caixa": "DESLIGADA"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": caminho}


def _con_tela(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _parcelas_na_tela(s) -> tuple[int, int]:
    con = _con_tela(s)
    ids = []
    with con:
        for numero, venc in (("4321/1", "2026-05-27"), ("4321/2", "2026-06-27")):
            cur = con.execute(
                """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                       data_vencimento, valor_centavos, saldo_centavos,
                       situacao, protocolo, origem, criado_em, motivo_protesto)
                   VALUES ('DMI',?,?,?,23000,23000,'APONTADO',?,'MANUAL',?,'1')""",
                (numero, numero, venc, PROTOCOLO, AGORA))
            tid = int(cur.lastrowid)
            con.execute(
                """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                       documento_numero) VALUES (?,'DEVEDOR DE EXEMPLO','CPF',
                       '00000000191')""", (tid,))
            ids.append(tid)
    con.close()
    return ids[0], ids[1]


def _lancar(s, titulo_id, **campos):
    from navegador_de_teste import postar_e_seguir
    tela = s["c"].get(f"/protesto/{titulo_id}").get_data(as_text=True)
    return postar_e_seguir(s["c"], f"/protesto/{titulo_id}/lancar",
                           {"csrf_token": _token(tela), **campos}
                           ).get_data(as_text=True)


def test_a_ficha_mostra_os_irmaos_e_o_quadro_do_papel(s):
    p1, p2 = _parcelas_na_tela(s)
    html = s["c"].get(f"/protesto/{p2}").get_data(as_text=True)
    assert "data-titulos-irmaos" in html
    assert f'href="/protesto/{p1}"' in html
    assert "data-qual-titulo" in html and 'name="irmao_numero"' in html
    assert 'name="afirmo"' in html and 'name="afirmacao"' in html


def test_a_rota_recusa_o_papel_do_irmao_e_nada_e_lancado(s):
    _, p2 = _parcelas_na_tela(s)
    html = _lancar(s, p2, ato="PAGAMENTO", forma_pagamento="ESPECIE",
                   irmao_numero="4321/1", irmao_vencimento="2026-05-27")
    assert "IRMÃO" in html
    con = _con_tela(s)
    assert con.execute("SELECT COUNT(*) FROM pt_atos WHERE tipo='PAGAMENTO'"
                       ).fetchone()[0] == 0
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (p2,)).fetchone()[0] == "APONTADO"
    con.close()


def test_a_afirmacao_pela_tela_vai_ao_ato_e_a_auditoria(s):
    _, p2 = _parcelas_na_tela(s)
    _lancar(s, p2, ato="PAGAMENTO", forma_pagamento="ESPECIE",
            afirmo="1", afirmacao=AFIRMACAO_BOA)
    con = _con_tela(s)
    ato = con.execute("SELECT * FROM pt_atos WHERE tipo='PAGAMENTO'").fetchone()
    assert ato is not None
    detalhe = json.loads(ato["detalhe_json"])
    assert detalhe["afirmacao_expressa"]["afirmacao"] == AFIRMACAO_BOA
    linha = con.execute(
        "SELECT entity_type, entity_id, details FROM audit_logs "
        "WHERE action='AFIRMACAO_EXPRESSA' ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha is not None
    assert linha["entity_type"] == "pt_titulos" and int(linha["entity_id"]) == p2
    det = json.loads(linha["details"])
    assert det["regra"] == IRM.REGRA and det["afirmacao"] == AFIRMACAO_BOA
    assert "o_que_faltava" in det


def test_o_lote_a_protestar_mostra_o_irmao(s):
    p1, p2 = _parcelas_na_tela(s)
    con = _con_tela(s)
    with con:
        con.execute("UPDATE pt_titulos SET situacao='INTIMADO' WHERE id=?", (p1,))
        con.execute("UPDATE pt_titulos SET situacao='PAGO' WHERE id=?", (p2,))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (?,'INTIMACAO','2026-10-20','{"modo": "EDITAL"}',
                       'MANUAL',?)""", (p1, AGORA))
    con.close()
    html = s["c"].get("/protesto/a-protestar").get_data(as_text=True)
    assert f'data-irmaos-do-titulo="{p1}"' in html
    assert "mesmo valor" in html


def test_a_conferencia_e_o_painel_abrem(s):
    _parcelas_na_tela(s)
    html = s["c"].get("/protesto/titulos-irmaos").get_data(as_text=True)
    assert "Títulos irmãos em situações que não se explicam juntas" in html
    assert "Cedente diferente do registro de origem" in html
    painel = s["c"].get("/protesto/roteiro").get_data(as_text=True)
    assert "Conferência dos títulos" in painel
    assert "/protesto/titulos-irmaos" in painel
