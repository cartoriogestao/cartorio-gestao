"""
Dois devedores pela CRA: um título, um protocolo, uma chave e um lugar no livro.

O E-OFÍCIO (`Apontamento_CRA`) lê a posição 297 da linha: «1» é título novo; outro
valor fica com o protocolo da linha anterior. Medido no acervo: 34 pares, todos
com a linha «2» logo depois da «1», com os mesmos dados do título e outro
documento. Este teste usa só dado fictício, montado do exemplo da remessa.

SEM CRITÉRIO SEGURO, OS TÍTULOS FICAM SEPARADOS E A CONFERÊNCIA AVISA: pôr duas
pessoas sem relação no mesmo protocolo é pior que deixar dois protocolos.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import protesto as PT                            # noqa: E402
import protesto_arquivo as PA                    # noqa: E402
import protesto_cenprot as CP                    # noqa: E402
import protesto_remessa as PRM                   # noqa: E402
import protesto_retorno as PR                    # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

AGORA = "2026-10-30T09:00:00"
HOJE = "2026-10-30"
EXTENSO = "trinta dias do mês de outubro do ano de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
PESOS = "73197319731973197319731"
CONFIGURACAO = (("ibge_uf", "12"), ("ibge_municipio", "34567"),
                ("ibge_cartorio", "3"), (CP.CHAVE_DOS_PESOS, PESOS))

EXEMPLO = (Path(__file__).parent / "cra_remessa_exemplo.txt").read_bytes().decode("latin-1")
_LINHAS = [x for x in EXEMPLO.replace("\r\n", "\n").split("\n") if x.strip()]
CABECALHO = _LINHAS[0]
TITULO = next(x for x in _LINHAS if x[:1] == "1")
RODAPE = _LINHAS[-1]


def _trocar(linha: str, nome: str, valor: str) -> str:
    campo = next(c for c in PA.TITULO_NA_REMESSA if c.nome == nome)
    return (linha[:campo.inicio - 1] + valor.ljust(campo.tamanho)[:campo.tamanho]
            + linha[campo.fim:])


def _linha(controle="1", *, documento=None, numero=None, nosso=None) -> str:
    linha = _trocar(TITULO, "motivo_do_protesto", controle)
    if documento:
        linha = _trocar(linha, "devedor_documento", documento)
    if numero:
        linha = _trocar(linha, "numero_do_titulo", numero)
    if nosso:
        linha = _trocar(linha, "nosso_numero", nosso)
    return linha


def _arquivo(*linhas: str) -> bytes:
    numeradas = [x[:596] + f"{i:04d}" for i, x in enumerate(linhas, start=2)]
    return "\r\n".join([CABECALHO, *numeradas, RODAPE]).encode("latin-1")


DOIS_DEVEDORES = _arquivo(_linha("1"), _linha("2", documento="00000000000191"))


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)", CONFIGURACAO)
    yield c
    c.close()


def receber(con, conteudo=DOIS_DEVEDORES, **kw):
    return PRM.receber(con, conteudo, agora=AGORA, data_extenso=EXTENSO, sv=SV, **kw)


def titulos(con) -> list[sqlite3.Row]:
    return con.execute("SELECT * FROM pt_titulos ORDER BY id").fetchall()


def _apontamento(con, tid) -> sqlite3.Row:
    return con.execute("SELECT * FROM pt_atos WHERE titulo_id=? AND tipo='APONTAMENTO'",
                       (tid,)).fetchone()


# ------------------------------------------------------------------ o critério


def test_a_posicao_297_e_o_controle_do_devedor():
    assert PA.controle_do_devedor({"motivo_do_protesto": "2"}) == "2"
    assert PA.controle_do_devedor({"motivo_do_protesto": None}) == ""


def test_conferir_mostra_o_par_e_nao_grava(con):
    lote = PRM.conferir(con, DOIS_DEVEDORES)["lotes"][0]
    primeira, segunda = lote["titulos"]
    assert primeira["principal"] is None and not primeira["aviso_devedor"]
    assert segunda["principal"] == primeira["sequencial"]
    assert not segunda["aviso_devedor"]
    assert con.execute("SELECT COUNT(*) n FROM pt_titulos").fetchone()["n"] == 0


def test_o_controle_nao_vira_motivo_do_protesto(con):
    """O «2» diria falta de aceite, e ele quer dizer segundo devedor."""
    receber(con)
    assert [t["motivo_protesto"] for t in titulos(con)] == ["1", "1"]


# ------------------------------------------------------------------ o que entra


def test_os_dois_devedores_ficam_com_o_mesmo_protocolo_e_a_mesma_chave(con):
    receber(con)
    a, b = titulos(con)
    assert a["protocolo"] == b["protocolo"] == "2610300001"
    assert a["chave_cenprot"] and a["chave_cenprot"] == b["chave_cenprot"]
    assert (a["controle_devedor"], b["controle_devedor"]) == ("1", "2")
    assert a["titulo_principal_id"] is None
    assert b["titulo_principal_id"] == a["id"]


def test_os_dois_ficam_com_devedores_proprios(con):
    receber(con)
    a, b = titulos(con)
    docs = [con.execute("SELECT documento_numero FROM pt_devedores WHERE titulo_id=?",
                        (t["id"],)).fetchone()[0] for t in (a, b)]
    assert docs[0] != docs[1]


def test_o_livro_de_apontamento_tem_um_lugar_so(con):
    r = receber(con)
    assert r["apontados"] == 2
    a, b = titulos(con)
    ato_a, ato_b = _apontamento(con, a["id"]), _apontamento(con, b["id"])
    for coluna in ("livro_id", "folha", "verso", "numero_ordem", "rotulo"):
        assert ato_a[coluna] == ato_b[coluna]
    assert con.execute("SELECT COUNT(*) n FROM nu_lugares WHERE tabela='pt_atos'"
                       ).fetchone()["n"] == 1


def test_o_titulo_seguinte_toma_o_proximo_protocolo_a_chave_e_a_ordem(con):
    receber(con, _arquivo(_linha("1"), _linha("2", documento="00000000000191"),
                          _linha("1", numero="OUTRO", nosso="OUTRO")))
    a, b, c = titulos(con)
    assert c["protocolo"] == "2610300002"
    assert c["chave_cenprot"] != a["chave_cenprot"]
    assert CP.decompor_chave(c["chave_cenprot"])["sequencial"] == "0000002"
    assert _apontamento(con, c["id"])["numero_ordem"] == (
        _apontamento(con, a["id"])["numero_ordem"] + 1)
    assert b["protocolo"] == a["protocolo"]


def test_tres_devedores_ficam_todos_no_primeiro(con):
    receber(con, _arquivo(_linha("1"), _linha("2", documento="00000000000191"),
                          _linha("3", documento="00000000000272")))
    a, b, c = titulos(con)
    assert a["protocolo"] == b["protocolo"] == c["protocolo"]
    assert b["titulo_principal_id"] == c["titulo_principal_id"] == a["id"]


# ------------------------------------------------------------ sem critério seguro


@pytest.mark.parametrize("arquivo", [
    # O número de controle diz que é o mesmo título, e os dados dizem que não.
    _arquivo(_linha("1"), _linha("2", documento="00000000000191", numero="OUTRO")),
    _arquivo(_linha("1"), _linha("2", documento="00000000000191", nosso="OUTRO")),
    # Não há linha do primeiro devedor antes dela.
    _arquivo(_linha("2", documento="00000000000191")),
    # O mesmo número duas vezes no mesmo título.
    _arquivo(_linha("1"), _linha("2", documento="00000000000191"),
             _linha("2", documento="00000000000272")),
])
def test_sem_criterio_seguro_ficam_separados_e_a_conferencia_avisa(con, arquivo):
    lote = PRM.conferir(con, arquivo)["lotes"][0]
    separada = lote["titulos"][-1]
    assert separada["principal"] is None
    assert "título separado" in separada["aviso_devedor"]
    assert lote["avisados"] >= 1
    receber(con, arquivo)
    ultimo = titulos(con)[-1]
    assert ultimo["titulo_principal_id"] is None
    assert ultimo["motivo_protesto"] is None
    outros = [t["protocolo"] for t in titulos(con)[:-1]]
    assert ultimo["protocolo"] not in outros
    assert ultimo["chave_cenprot"] not in [t["chave_cenprot"] for t in titulos(con)[:-1]]


def test_a_linha_anterior_recusada_nao_liga(con):
    recusada = _trocar(_linha("1"), "especie", "XXX")
    lote = PRM.conferir(con, _arquivo(recusada,
                                      _linha("2", documento="00000000000191")))["lotes"][0]
    assert not lote["titulos"][0]["aceito"]
    assert lote["titulos"][1]["principal"] is None
    assert "não entra" in lote["titulos"][1]["aviso_devedor"]


# --------------------------------------------------------- apontar depois, na ficha


def test_o_seguinte_nao_se_aponta_antes_do_primeiro(con):
    receber(con, apontar=False)
    a, b = titulos(con)
    assert not a["protocolo"] and not b["protocolo"]
    with pytest.raises(PT.ProtestoError, match="ainda não foi apontado"):
        PT.lancar_apontamento(con, b["id"], sv=SV, agora=AGORA, data_extenso=EXTENSO)


def test_apontados_pela_ficha_ficam_com_o_mesmo_protocolo_e_chave(con):
    receber(con, apontar=False)
    a, b = titulos(con)
    for t in (a, b):
        PT.lancar_apontamento(con, t["id"], sv=SV, agora=AGORA, data_extenso=EXTENSO)
    a, b = titulos(con)
    assert a["protocolo"] == b["protocolo"]
    assert a["chave_cenprot"] == b["chave_cenprot"]


def test_se_o_primeiro_saiu_sem_apontar_o_seguinte_se_aponta_sozinho(con):
    receber(con, apontar=False)
    a, b = titulos(con)
    con.execute("UPDATE pt_titulos SET situacao='DESISTIDO' WHERE id=?", (a["id"],))
    PT.lancar_apontamento(con, b["id"], sv=SV, agora=AGORA, data_extenso=EXTENSO)
    b = titulos(con)[1]
    assert b["protocolo"] == "2610300001" and b["chave_cenprot"]


# ------------------------------------------------------- o que vai à CRA e à Central


def test_a_confirmacao_leva_as_duas_linhas_com_o_mesmo_protocolo(con):
    """Como o E-Ofício (`FormConfirmacao`): toda linha da remessa, com o protocolo."""
    r = receber(con)
    conteudo = con.execute("SELECT conteudo FROM pt_retornos WHERE id=?",
                           (r["confirmacoes"][0],)).fetchone()["conteudo"]
    lidas = PA.ler(conteudo).titulos
    assert [str(t["protocolo"]) for t in lidas] == ["2610300001", "2610300001"]


def test_o_retorno_leva_uma_linha_so_e_os_dois_atos(con):
    """O retorno tem de sair com um protocolo uma vez: a CRA recusa o repetido."""
    receber(con)
    for t in titulos(con):
        PT.lancar_intimacao(con, t["id"], modo="PESSOAL", agora=AGORA)
        juntar_prova(con, t["id"])
        PT.lancar_protesto(con, t["id"], sv=SV, agora=AGORA, data_extenso=EXTENSO)
    montado = PR.montar(con, apresentante_codigo="001", dia=HOJE, marca="A")
    lido = PA.ler(montado["conteudo"])
    assert [str(t["protocolo"]) for t in lido.titulos] == ["2610300001"]
    assert len(montado["atos"]) == 2


def test_a_tela_de_conferir_conta_o_que_vai_acontecer():
    tela = (RAIZ / "templates" / "protesto_remessa_conferir.html").read_text(encoding="utf-8")
    assert "t.principal" in tela and "t.aviso_devedor" in tela
