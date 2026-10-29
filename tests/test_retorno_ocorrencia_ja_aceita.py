"""
Ocorrência já aceita pela CRA não volta no retorno seguinte.

POR QUE ESTES TESTES EXISTEM (29/10/2026)
    Título 1353, apresentante 341. O cancelamento 4104 saiu no R3412810.261,
    a CRA aceitou (0000), o ato foi desfeito por falta de selo e o 4128, novo
    cancelamento do mesmo título, voltou à fila. A lista só olhava se o ato
    atual tinha `retorno_id`. O segundo «A» faz a Central recusar o arquivo
    com 2161 «NENHUM REGISTRO FOI GRAVADO».

O QUE ELES CONFEREM
    - o ato substituto, da mesma ocorrência no mesmo título ou protocolo, não
      entra em `pendentes` nem no arquivo;
    - a frase da geração diz qual ato ficou de fora e em que arquivo a CRA
      aceitou;
    - ocorrência diferente, e ocorrência cujo retorno anterior foi recusado,
      continuam elegíveis;
    - a marca manual (motivo e retorno anterior) tira o ato da fila, não
      amarra `retorno_id`, e a rota grava a auditoria. USER não marca.
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

import protesto as PT  # noqa: E402
import protesto_retorno as PR  # noqa: E402
from nucleo_schema import init_nucleo_schema  # noqa: E402
from pt_schema import init_pt_schema  # noqa: E402

AGORA = "2026-10-28T14:32:00"
HOJE = "2026-10-28"
DIA_SEGUINTE = "2026-10-29"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
MOTIVO = "A CRA já aceitou esta ocorrência no retorno anterior."


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="1353", apresentante="341") -> int:
    dados = {
        "apresentante_codigo": apresentante,
        "apresentante_nome": "BANCO EXEMPLO",
        "especie": "DMI", "numero_titulo": numero,
        "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA EXEMPLO LTDA",
                    "documento": "00000001000055"},
        "devedores": [{"nome": "FULANO DE TAL EXEMPLO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA EXEMPLO, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    return PT.cadastrar_titulo(con, dados, origem="CRA",
                               origem_chave=f"lote:{apresentante}:{numero}",
                               agora=AGORA)


def ate_o_protesto(con, titulo_id: int) -> None:
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")


def ato_id(con, titulo_id: int, tipo: str) -> int:
    return int(con.execute(
        "SELECT id FROM pt_atos WHERE titulo_id=? AND tipo=? ORDER BY id DESC",
        (titulo_id, tipo)).fetchone()[0])


def novo_ato(con, titulo_id: int, tipo: str, quando: str) -> int:
    con.execute(
        """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
               origem, criado_em)
           VALUES (?, ?, ?, '{}', 'MANUAL', ?)""",
        (titulo_id, tipo, quando, quando))
    return int(con.execute("SELECT MAX(id) FROM pt_atos").fetchone()[0])


def desfazer(con, ato: int) -> None:
    con.execute(
        "UPDATE pt_atos SET cancelado=1, motivo_cancelamento=? WHERE id=?",
        ("Selo não emitido: teste", ato))


def aceitar(con, retorno_id: int) -> None:
    con.execute(
        """UPDATE pt_retornos
              SET cra_enviado_em=?, cra_enviado_ambiente='PRODUCAO',
                  cra_recusado_em=NULL
            WHERE id=?""",
        (AGORA, retorno_id))


def recusar(con, retorno_id: int) -> None:
    con.execute(
        """UPDATE pt_retornos
              SET cra_enviado_em=NULL, cra_recusado_em=?,
                  cra_recusa_codigo='2161',
                  cra_recusa_motivo='NENHUM REGISTRO FOI GRAVADO',
                  cra_enviado_ambiente='PRODUCAO'
            WHERE id=?""",
        (AGORA, retorno_id))


def ids_pendentes(con) -> list[int]:
    return [int(p["ato_id"]) for p in PR.pendentes(con)]


def gerar(con, apresentante="341", dia=HOJE) -> dict:
    return PR.gerar(con, apresentante_codigo=apresentante, dia=dia,
                    agora=AGORA, marca="A", usuario="OFICIAL")


def protocolo(con, titulo_id: int) -> str:
    return con.execute(
        "SELECT protocolo FROM pt_titulos WHERE id=?", (titulo_id,)).fetchone()[0]


def nome_do(con, retorno_id: int) -> str:
    return con.execute(
        "SELECT nome_arquivo FROM pt_retornos WHERE id=?",
        (retorno_id,)).fetchone()[0]


# ------------------------------------------------- a letra é o tipo do ato


def test_cada_ato_final_tem_uma_ocorrencia_so():
    """`pendentes` casa o tipo do ato porque cada um tem uma letra só.
    Duas letras iguais exigiriam casar a letra, não o tipo."""
    letras = list(PR.OCORRENCIA_DO_ATO.values())
    assert len(letras) == len(set(letras))
    assert PR.OCORRENCIA_DO_ATO["CANCELAMENTO"] == "A"
    assert PR.OCORRENCIA_DO_ATO["PROTESTO"] == "C"


# ------------------------------------------ o substituto não volta à fila


def test_ato_substituto_de_ocorrencia_aceita_nao_reenfileira():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    prot = protocolo(con, tid)
    r_protesto = gerar(con)
    aceitar(con, r_protesto["retorno_id"])

    cancelado = novo_ato(con, tid, "CANCELAMENTO", "2026-10-28T13:00:00")
    r_canc = gerar(con)
    assert cancelado in [int(a["ato_id"]) for a in r_canc["atos"]]
    aceitar(con, r_canc["retorno_id"])
    arquivo = nome_do(con, r_canc["retorno_id"])
    desfazer(con, cancelado)

    substituto = novo_ato(con, tid, "CANCELAMENTO", "2026-10-29T09:00:00")
    assert substituto not in ids_pendentes(con)
    # Sem o aceite, a fila voltaria a ver o ato — era só o `retorno_id` dele.
    con.execute("UPDATE pt_retornos SET cra_enviado_em=NULL WHERE id=?",
                (r_canc["retorno_id"],))
    assert substituto in ids_pendentes(con)
    aceitar(con, r_canc["retorno_id"])
    assert substituto not in ids_pendentes(con)

    # O mesmo protocolo noutro título é a mesma ocorrência para a CRA.
    irmao = titulo(con, numero="1353-irmao")
    con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?", (prot, irmao))
    do_irmao = novo_ato(con, irmao, "CANCELAMENTO", "2026-10-29T10:00:00")
    assert do_irmao not in ids_pendentes(con)

    # Outro título, outro protocolo: o protesto dele continua na fila e sai
    # no arquivo. O «A» do 1353 não sai, e a frase cita o arquivo aceito.
    livre = titulo(con, numero="2000")
    ate_o_protesto(con, livre)
    prot_livre = protocolo(con, livre)
    r = gerar(con, dia=DIA_SEGUINTE)
    assert substituto not in [int(a["ato_id"]) for a in r["atos"]]
    assert do_irmao not in [int(a["ato_id"]) for a in r["atos"]]
    pulados = {int(p["ato_id"]): p for p in r["pulados"]}
    assert substituto in pulados and do_irmao in pulados
    assert pulados[substituto]["arquivo_anterior"] == arquivo
    assert arquivo in PR.frase_dos_pulados(r["pulados"])
    assert str(substituto) in PR.frase_dos_pulados(r["pulados"])
    linhas = [ln for ln in r["conteudo"].splitlines() if ln[:1] == "1"]
    ocorrencias = {ln[447:457]: ln[457] for ln in linhas}
    assert ocorrencias[prot_livre] == "C"
    assert prot not in ocorrencias
    assert "A" not in ocorrencias.values()

    # Devolver o substituto de um arquivo recusado não o põe na fila: a
    # ocorrência já foi aceita antes.
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em,
               cra_recusado_em, cra_recusa_codigo, cra_recusa_motivo,
               cra_enviado_ambiente)
           VALUES ('SDTBFORTP','341',?,1,'R3412910.269','x',?,
                   ?,'2161','NENHUM REGISTRO FOI GRAVADO','PRODUCAO')""",
        (DIA_SEGUINTE, AGORA, AGORA))
    recusado = int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])
    con.execute("UPDATE pt_atos SET retorno_id=? WHERE id=?",
                (recusado, substituto))
    devolvido = PR.devolver_atos_do_recusado(
        con, recusado, agora=AGORA, usuario="OFICIAL")
    assert substituto in [int(p["ato_id"])
                          for p in devolvido["continuam_de_fora"]]
    assert substituto not in ids_pendentes(con)


def test_so_o_substituto_diz_o_motivo_em_vez_de_nao_ha_ato():
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    r1 = gerar(con)
    aceitar(con, r1["retorno_id"])
    primeiro = novo_ato(con, tid, "CANCELAMENTO", "2026-10-28T13:00:00")
    # O protesto já foi; o cancelamento é a ocorrência nova e sai.
    r2 = gerar(con, dia=DIA_SEGUINTE)
    aceitar(con, r2["retorno_id"])
    desfazer(con, primeiro)
    substituto = novo_ato(con, tid, "CANCELAMENTO", "2026-10-29T11:00:00")
    with pytest.raises(PR.RetornoError) as erro:
        gerar(con, dia="2026-10-30")
    assert str(substituto) in str(erro.value)
    assert nome_do(con, r2["retorno_id"]) in str(erro.value)
    assert "já aceitou" in str(erro.value)


# ---------------------- ocorrência que a CRA ainda não aceitou continua


def test_ocorrencia_diferente_continua_elegivel():
    """Protesto aceito não segura o cancelamento: a letra é outra."""
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    prot = protocolo(con, tid)
    r = gerar(con)
    aceitar(con, r["retorno_id"])
    canc = novo_ato(con, tid, "CANCELAMENTO", "2026-10-29T09:00:00")
    assert canc in ids_pendentes(con)
    seguinte = gerar(con, dia=DIA_SEGUINTE)
    assert canc in [int(a["ato_id"]) for a in seguinte["atos"]]
    linhas = [ln for ln in seguinte["conteudo"].splitlines() if ln[:1] == "1"]
    assert linhas[0][447:457] == prot
    assert linhas[0][457] == "A"


def test_retorno_recusado_nao_conta_como_aceite_e_o_substituto_segue():
    """2161 não gravou nada. O ato novo da mesma letra continua na fila."""
    con = banco()
    tid = titulo(con)
    ate_o_protesto(con, tid)
    r = gerar(con)
    recusar(con, r["retorno_id"])
    desfazer(con, ato_id(con, tid, "PROTESTO"))
    novo = novo_ato(con, tid, "PROTESTO", "2026-10-29T09:00:00")
    assert novo in ids_pendentes(con)
    seguinte = gerar(con, dia=DIA_SEGUINTE)
    assert novo in [int(a["ato_id"]) for a in seguinte["atos"]]
    assert all(ln[457] == "C"
               for ln in seguinte["conteudo"].splitlines() if ln[:1] == "1")


# ------------------------------------------------------- a marca manual


def _alvo_pendente(con):
    """Um protesto na fila e um retorno já aceito do mesmo apresentante,
    de outro título, para citar."""
    base = titulo(con, numero="1/1")
    ate_o_protesto(con, base)
    r = gerar(con)
    aceitar(con, r["retorno_id"])
    alvo = titulo(con, numero="2/1")
    ate_o_protesto(con, alvo)
    return alvo, ato_id(con, alvo, "PROTESTO"), r


def test_marcar_ja_informado_tira_da_fila_sem_amarrar_o_arquivo():
    con = banco()
    _alvo, ato, r = _alvo_pendente(con)
    assert ato in ids_pendentes(con)
    marcado = PR.marcar_ja_informado_a_cra(
        con, ato, retorno_id=r["retorno_id"], motivo=MOTIVO,
        agora=AGORA, usuario="OFICIAL")
    assert marcado["nome_arquivo"] == nome_do(con, r["retorno_id"])
    assert ato not in ids_pendentes(con)
    linha = con.execute(
        """SELECT retorno_id, cra_ja_informado_em, cra_ja_informado_por,
                  cra_ja_informado_motivo, cra_ja_informado_retorno_id
             FROM pt_atos WHERE id=?""", (ato,)).fetchone()
    assert linha["retorno_id"] is None
    assert linha["cra_ja_informado_por"] == "OFICIAL"
    assert linha["cra_ja_informado_motivo"] == MOTIVO
    assert int(linha["cra_ja_informado_retorno_id"]) == int(r["retorno_id"])
    assert str(linha["cra_ja_informado_em"]).startswith("2026-10-28")
    # O substituto do ato marcado também fica de fora.
    desfazer(con, ato)
    novo = novo_ato(con, _alvo, "PROTESTO", "2026-10-29T09:00:00")
    assert novo not in ids_pendentes(con)
    fora = {int(p["ato_id"]): p for p in PR.ja_aceitas_fora_da_fila(con)}
    assert novo in fora
    assert fora[novo]["arquivo_anterior"] == nome_do(con, r["retorno_id"])


def test_a_marca_recusa_motivo_curto_retorno_recusado_e_outro_apresentante():
    con = banco()
    alvo, ato, r = _alvo_pendente(con)
    with pytest.raises(PR.RetornoError, match="dez letras"):
        PR.marcar_ja_informado_a_cra(
            con, ato, retorno_id=r["retorno_id"], motivo="curto",
            agora=AGORA, usuario="OFICIAL")
    recusar(con, r["retorno_id"])
    with pytest.raises(PR.RetornoError, match="recusado"):
        PR.marcar_ja_informado_a_cra(
            con, ato, retorno_id=r["retorno_id"], motivo=MOTIVO,
            agora=AGORA, usuario="OFICIAL")
    aceitar(con, r["retorno_id"])
    andamento = int(con.execute(
        "SELECT id FROM pt_retornos WHERE tipo='SDTBFOAND'").fetchone()[0])
    aceitar(con, andamento)
    with pytest.raises(PR.RetornoError, match="andamento"):
        PR.marcar_ja_informado_a_cra(
            con, ato, retorno_id=andamento, motivo=MOTIVO,
            agora=AGORA, usuario="OFICIAL")
    outro = titulo(con, numero="9/1", apresentante="237")
    ate_o_protesto(con, outro)
    do_outro = gerar(con, apresentante="237", dia=DIA_SEGUINTE)
    aceitar(con, do_outro["retorno_id"])
    with pytest.raises(PR.RetornoError, match="apresentante"):
        PR.marcar_ja_informado_a_cra(
            con, ato, retorno_id=do_outro["retorno_id"], motivo=MOTIVO,
            agora=AGORA, usuario="OFICIAL")
    assert ato in ids_pendentes(con)


# ------------------------------------------------------------- a tela


SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "MANAGER"):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    caminho = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(caminho)
    db.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    db.set_settings({"modulo_protesto_ligado": "1", "selo_trava_caixa": "DESLIGADA"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": caminho}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def test_a_marcacao_manual_grava_auditoria_e_o_usuario_nao_marca(tmp_path):
    s = _sessao(tmp_path, "MANAGER")
    con = _con(s)
    base = titulo(con, numero="1/1")
    ate_o_protesto(con, base)
    r = gerar(con)
    aceitar(con, r["retorno_id"])
    alvo = titulo(con, numero="2/1")
    ate_o_protesto(con, alvo)
    ato = ato_id(con, alvo, "PROTESTO")
    con.commit()
    con.close()

    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    html = c.post(
        f"/protesto/retornos/ato/{ato}/ja-informado",
        data={"csrf_token": token, "retorno_id": str(r["retorno_id"]),
              "motivo": MOTIVO},
        follow_redirects=True).get_data(as_text=True)
    assert "marcado como já informado à CRA" in html
    assert "Não entram de novo" in html
    con = _con(s)
    assert ato not in ids_pendentes(con)
    con.close()
    con = _con(s)
    linha = con.execute(
        """SELECT action, entity_type, entity_id, details
             FROM audit_logs
            WHERE action='PROTESTO_ATO_JA_INFORMADO_CRA'""").fetchone()
    con.close()
    assert linha["entity_type"] == "pt_atos"
    assert int(linha["entity_id"]) == ato
    detalhe = json.loads(linha["details"])
    assert detalhe["motivo"] == MOTIVO
    assert int(detalhe["retorno_id"]) == int(r["retorno_id"])
    assert detalhe["tipo"] == "PROTESTO"
    assert detalhe["ocorrencia"] == "C"

    pasta_do_usuario = tmp_path / "usuario"
    pasta_do_usuario.mkdir()
    comum = _sessao(pasta_do_usuario, "USER")
    token = _token(comum["c"].get("/protesto/retornos").get_data(as_text=True))
    recusa = comum["c"].post(
        "/protesto/retornos/ato/1/ja-informado",
        data={"csrf_token": token, "retorno_id": "1", "motivo": MOTIVO})
    assert recusa.status_code == 403
    pagina = comum["c"].get("/protesto/retornos").get_data(as_text=True)
    assert "Marcar como já informado à CRA" not in pagina


def test_gerar_pela_tela_avisa_o_ato_pulado(tmp_path):
    s = _sessao(tmp_path, "MANAGER")
    con = _con(s)
    tid = titulo(con)
    ate_o_protesto(con, tid)
    r1 = gerar(con)
    aceitar(con, r1["retorno_id"])
    primeiro = novo_ato(con, tid, "CANCELAMENTO", "2026-10-28T13:00:00")
    r2 = gerar(con, dia=DIA_SEGUINTE)
    aceitar(con, r2["retorno_id"])
    arquivo = nome_do(con, r2["retorno_id"])
    desfazer(con, primeiro)
    substituto = novo_ato(con, tid, "CANCELAMENTO", "2026-10-29T09:00:00")
    livre = titulo(con, numero="2000")
    ate_o_protesto(con, livre)
    con.commit()
    con.close()

    c = s["c"]
    token = _token(c.get("/protesto/retornos").get_data(as_text=True))
    html = c.post(
        "/protesto/retornos/gerar",
        data={"csrf_token": token, "apresentante_codigo": "341",
              "dia": "2026-10-30", "numero_da_remessa": "1", "marca": "A"},
        follow_redirects=True).get_data(as_text=True)
    assert "já aceitou" in html
    assert str(substituto) in html
    assert arquivo in html
    assert "gerado" in html
    con = _con(s)
    protesto_livre = ato_id(con, livre, "PROTESTO")
    assert con.execute(
        "SELECT retorno_id FROM pt_atos WHERE id=?",
        (protesto_livre,)).fetchone()[0] is not None
    assert con.execute(
        "SELECT retorno_id FROM pt_atos WHERE id=?",
        (substituto,)).fetchone()[0] is None
    con.close()
