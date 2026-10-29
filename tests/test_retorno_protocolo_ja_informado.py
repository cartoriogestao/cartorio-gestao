"""
O protocolo que a CRA já tem não volta no retorno — nem pelo outro título.

POR QUE ESTES TESTES EXISTEM (29/10/2026)
    Protocolo 2610070011, apresentante 901: uma CDA com DOIS devedores, que
    entra nesta casa como dois títulos (#9602 e #9603) com o MESMO protocolo
    e o mesmo número. Os dois protestos de 23/10 saíram numa linha só no
    R9012310.261, e a CRA aceitou. O protesto do #9603 foi tornado sem efeito
    e refeito em 28/10; o R9012810.261 levou o protocolo de novo como
    protestado, e a Central recusou o arquivo inteiro com 2161. A CRA conhece
    o PROTOCOLO, e não o título.

    Ordem do oficial no mesmo dia: o sistema tem de impedir o erro; se a
    escrevente insistir, só com afirmação expressa e log.

O QUE ELES CONFEREM
    - o ato do título irmão, com a ocorrência que a CRA já aceitou para o
      protocolo, não entra em `pendentes`; aparece em lista própria, dizendo
      qual título informou, em que arquivo e quando;
    - ocorrência DIFERENTE no irmão (o cancelamento depois do protesto) segue
      para a fila — não é repetição;
    - a afirmação expressa (caixa `afirmo` + texto com 30 letras) devolve o
      ato à fila e grava `AFIRMACAO_EXPRESSA` com as três chaves do contrato;
      sem ela, ou curta, a recusa diz o que já foi informado e como afirmar;
    - o arquivo recusado apaga a afirmação ao devolver os atos;
    - a conferência dos protocolos com mais de um título mostra a repetição.
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
from prova_de_intimacao import juntar_prova  # noqa: E402

AGORA = "2026-10-23T13:25:00"
DIA_1 = "2026-10-23"
DIA_2 = "2026-10-28"
DIA_3 = "2026-10-29"
APRESENTANTE = "901"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
AFIRMACAO = ("Afirmo, sob minha responsabilidade, que conferi no portal da "
             "CRA e a Central não tem o protesto deste devedor")


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, chave: str, numero: str = "CDA-0001",
           apresentante: str = APRESENTANTE, cpf: str = "00000000191") -> int:
    dados = {
        "apresentante_codigo": apresentante,
        "apresentante_nome": "PROCURADORIA EXEMPLO",
        "especie": "CDA", "numero_titulo": numero,
        "nosso_numero": numero,
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1.200,00", "saldo": "1.310,45",
        "praca_protesto": "CIDADE EXEMPLO", "motivo_protesto": "1",
        "cedente": {"nome": "FAZENDA EXEMPLO",
                    "documento": "00000001000055"},
        "devedores": [{"nome": "FULANO DE TAL EXEMPLO", "CPF": cpf,
                       "enderecos": [{"endereco": "RUA EXEMPLO, 10",
                                      "bairro": "CENTRO",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    return PT.cadastrar_titulo(con, dados, origem="CRA",
                               origem_chave=f"lote:{apresentante}:{chave}",
                               agora=AGORA)


def apontar_e_intimar(con, titulo_id: int) -> None:
    PT.lancar_apontamento(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, titulo_id, modo="PESSOAL", agora=AGORA)
    # A PROVA DA INTIMAÇÃO (trava do #106): o que se confere aqui é o retorno.
    juntar_prova(con, titulo_id)


def protestar(con, titulo_id: int) -> None:
    PT.lancar_protesto(con, titulo_id, sv=SV, agora=AGORA, data_extenso="x")


def protocolo(con, titulo_id: int) -> str:
    return con.execute(
        "SELECT protocolo FROM pt_titulos WHERE id=?", (titulo_id,)).fetchone()[0]


def mesmo_protocolo(con, de: int, para: int) -> str:
    """O título com DOIS devedores: o segundo título leva o protocolo do
    primeiro, como a remessa da CRA traz."""
    prot = protocolo(con, de)
    con.execute("UPDATE pt_titulos SET protocolo=? WHERE id=?", (prot, para))
    return prot


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
        ("Tornado sem efeito: teste", ato))


def aceitar(con, retorno_id: int) -> None:
    con.execute(
        """UPDATE pt_retornos
              SET cra_enviado_em=?, cra_enviado_ambiente='PRODUCAO',
                  cra_recusado_em=NULL
            WHERE id=?""",
        ("2026-10-26T10:51:00", retorno_id))


def recusar(con, retorno_id: int) -> None:
    con.execute(
        """UPDATE pt_retornos
              SET cra_enviado_em=NULL, cra_recusado_em=?,
                  cra_recusa_codigo='2161',
                  cra_recusa_motivo='NENHUM REGISTRO FOI GRAVADO',
                  cra_enviado_ambiente='PRODUCAO'
            WHERE id=?""",
        ("2026-10-28T14:40:00", retorno_id))


def gerar(con, dia: str = DIA_1) -> dict:
    return PR.gerar(con, apresentante_codigo=APRESENTANTE, dia=dia,
                    agora=AGORA, marca="A", usuario="OFICIAL")


def aceitar_os_dois(con, r: dict) -> None:
    for chave in ("retorno_id", "andamento_id"):
        if r.get(chave):
            aceitar(con, r[chave])


def nome_do(con, retorno_id: int) -> str:
    return con.execute(
        "SELECT nome_arquivo FROM pt_retornos WHERE id=?",
        (retorno_id,)).fetchone()[0]


def ids_pendentes(con) -> list[int]:
    return [int(p["ato_id"]) for p in PR.pendentes(con)]


def o_caso_do_protocolo_2610070011(con) -> dict:
    """Dois títulos, um protocolo; os dois protestos aceitos numa linha só; o
    protesto do segundo tornado sem efeito e refeito."""
    a = titulo(con, chave="1")
    b = titulo(con, chave="2", cpf="00000000272")
    apontar_e_intimar(con, a)
    apontar_e_intimar(con, b)
    prot = mesmo_protocolo(con, a, b)
    protestar(con, a)
    protestar(con, b)
    r = gerar(con)
    linhas = [ln for ln in r["conteudo"].splitlines() if ln[:1] == "1"]
    assert [ln[447:457] for ln in linhas] == [prot], "uma linha por protocolo"
    aceitar_os_dois(con, r)
    protesto_a = ato_id(con, a, "PROTESTO")
    antigo_b = ato_id(con, b, "PROTESTO")
    desfazer(con, antigo_b)
    refeito_b = novo_ato(con, b, "PROTESTO", "2026-10-28T14:31:00")
    return {"a": a, "b": b, "protocolo": prot, "retorno": r,
            "arquivo": nome_do(con, r["retorno_id"]),
            "protesto_a": protesto_a, "antigo_b": antigo_b,
            "refeito_b": refeito_b}


# --------------------------------------- o irmão não volta, e diz quem foi


def test_o_titulo_irmao_refeito_nao_volta_e_diz_quem_informou():
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    refeito = caso["refeito_b"]
    assert refeito not in ids_pendentes(con)

    fora = {int(p["ato_id"]): p for p in PR.ja_aceitas_fora_da_fila(con)}
    assert refeito in fora
    linha = fora[refeito]
    assert linha["por_outro_titulo"] is True
    assert linha["pode_insistir"] is True
    quem = {int(i["ato_id"]): i for i in linha["informantes"]}
    # O protesto VÁLIDO do outro título, e o desfeito do próprio título —
    # os dois foram na mesma linha do arquivo aceito.
    assert set(quem) == {caso["protesto_a"], caso["antigo_b"]}
    assert int(quem[caso["protesto_a"]]["titulo_id"]) == caso["a"]
    assert not int(quem[caso["protesto_a"]]["desfeito"])
    assert int(quem[caso["antigo_b"]]["desfeito"])
    assert quem[caso["protesto_a"]]["arquivo"] == caso["arquivo"]
    assert "26/10/2026" in quem[caso["protesto_a"]]["frase"]
    assert f"#{caso['a']}" in quem[caso["protesto_a"]]["frase"]

    frase = PR.frase_dos_pulados([linha])
    assert "outro título do mesmo protocolo" in frase
    assert f"#{caso['a']}" in frase and caso["arquivo"] in frase

    # Gerar não manda: só havia ele, e a recusa diz quem já informou.
    with pytest.raises(PR.RetornoError) as erro:
        gerar(con, dia=DIA_3)
    assert "outro título do mesmo protocolo" in str(erro.value)
    assert caso["arquivo"] in str(erro.value)


def test_o_irmao_protestado_depois_tambem_fica_de_fora():
    """Sem ato desfeito nenhum: o outro título protesta primeiro, a CRA
    aceita, e o protesto do irmão — que é o mesmo protocolo — fica fora."""
    con = banco()
    a = titulo(con, chave="1")
    b = titulo(con, chave="2", cpf="00000000272")
    apontar_e_intimar(con, a)
    apontar_e_intimar(con, b)
    mesmo_protocolo(con, a, b)
    protestar(con, a)
    r = gerar(con)
    aceitar_os_dois(con, r)
    protestar(con, b)
    do_irmao = ato_id(con, b, "PROTESTO")
    assert do_irmao not in ids_pendentes(con)
    fora = {int(p["ato_id"]): p for p in PR.ja_aceitas_fora_da_fila(con)}
    assert fora[do_irmao]["por_outro_titulo"] is True
    assert [int(i["ato_id"]) for i in fora[do_irmao]["informantes"]] == [
        ato_id(con, a, "PROTESTO")]


def test_o_apontamento_do_irmao_tambem_nao_repete_o_andamento():
    """O andamento é por protocolo também: o «0» já aceito não sai de novo."""
    con = banco()
    a = titulo(con, chave="1")
    apontar_e_intimar(con, a)
    r = PR.gerar_andamento(con, apresentante_codigo=APRESENTANTE, dia=DIA_1,
                           agora=AGORA, marca="A", usuario="OFICIAL")
    aceitar(con, r["andamento_id"])
    b = titulo(con, chave="2", cpf="00000000272")
    apontar_e_intimar(con, b)
    mesmo_protocolo(con, a, b)
    apontamento_b = ato_id(con, b, "APONTAMENTO")
    andamento = [int(p["ato_id"])
                 for p in PR.pendentes(con, tipo="SDTBFOAND")]
    assert apontamento_b not in andamento
    fora = {int(p["ato_id"]): p for p in PR.ja_aceitas_fora_da_fila(con)}
    assert fora[apontamento_b]["por_outro_titulo"] is True
    assert fora[apontamento_b]["ocorrencia"] == "0"


# ------------------------------------------- ocorrência diferente não repete


def test_ocorrencia_diferente_no_irmao_segue_para_a_fila():
    """Protestado e depois cancelado é a vida do título na CRA, e não
    repetição: o «A» do protocolo sai, ainda que o «C» tenha ido pelo outro
    título."""
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    cancelamento = novo_ato(con, caso["b"], "CANCELAMENTO",
                            "2026-10-29T09:00:00")
    assert cancelamento in ids_pendentes(con)
    r = gerar(con, dia=DIA_3)
    assert cancelamento in [int(a["ato_id"]) for a in r["atos"]]
    assert caso["refeito_b"] not in [int(a["ato_id"]) for a in r["atos"]]
    linhas = [ln for ln in r["conteudo"].splitlines() if ln[:1] == "1"]
    assert [(ln[447:457], ln[457]) for ln in linhas] == [
        (caso["protocolo"], "A")]


# ---------------------------------------------------- a afirmação expressa


def test_insistir_sem_afirmacao_recusa_e_diz_o_que_ja_foi_informado():
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    with pytest.raises(PR.RetornoError) as erro:
        PR.forcar_envio_de_protocolo_ja_informado(
            con, caso["refeito_b"], afirmacao=None, agora=AGORA,
            usuario="ESCREVENTE")
    texto = str(erro.value)
    assert caso["protocolo"] in texto and caso["arquivo"] in texto
    assert PR.FRASE_DA_AFIRMACAO in texto
    assert "2161" in texto
    with pytest.raises(PR.RetornoError, match="curta demais"):
        PR.forcar_envio_de_protocolo_ja_informado(
            con, caso["refeito_b"],
            afirmacao=f"{PR.FRASE_DA_AFIRMACAO} está certo",
            agora=AGORA, usuario="ESCREVENTE")
    # A frase sozinha tem mais de trinta letras, e não vale.
    assert PR.afirmacao_valida(PR.FRASE_DA_AFIRMACAO) is None
    assert caso["refeito_b"] not in ids_pendentes(con)


def test_a_afirmacao_devolve_a_fila_e_o_recusado_a_apaga():
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    refeito = caso["refeito_b"]
    registro = PR.forcar_envio_de_protocolo_ja_informado(
        con, refeito, afirmacao=AFIRMACAO, agora="2026-10-29T10:00:00",
        usuario="ESCREVENTE")
    assert registro["regra"] == "RETORNO_PROTOCOLO_JA_INFORMADO"
    assert registro["afirmacao"].startswith(PR.FRASE_DA_AFIRMACAO)
    assert caso["arquivo"] in registro["o_que_faltava"]
    assert f"#{caso['a']}" in registro["o_que_faltava"]
    assert set(PR.para_a_auditoria(registro)) == {
        "regra", "afirmacao", "o_que_faltava"}
    gravado = con.execute(
        """SELECT cra_reenvio_afirmado_em, cra_reenvio_afirmado_por,
                  cra_reenvio_afirmacao FROM pt_atos WHERE id=?""",
        (refeito,)).fetchone()
    assert gravado["cra_reenvio_afirmado_por"] == "ESCREVENTE"
    assert gravado["cra_reenvio_afirmacao"] == registro["afirmacao"]

    assert refeito in ids_pendentes(con)
    assert refeito not in {int(p["ato_id"])
                           for p in PR.ja_aceitas_fora_da_fila(con)}
    with pytest.raises(PR.RetornoError, match="já voltou à fila"):
        PR.forcar_envio_de_protocolo_ja_informado(
            con, refeito, afirmacao=AFIRMACAO, agora=AGORA,
            usuario="ESCREVENTE")

    r = gerar(con, dia=DIA_3)
    assert refeito in [int(a["ato_id"]) for a in r["atos"]]
    recusar(con, r["retorno_id"])
    devolvido = PR.devolver_atos_do_recusado(
        con, r["retorno_id"], agora=AGORA, usuario="OFICIAL")
    assert refeito in [int(p["ato_id"])
                       for p in devolvido["continuam_de_fora"]]
    assert refeito not in ids_pendentes(con)
    apagado = con.execute(
        "SELECT cra_reenvio_afirmado_em FROM pt_atos WHERE id=?",
        (refeito,)).fetchone()[0]
    assert apagado is None


def test_insistir_recusa_o_que_nao_esta_travado_o_marcado_e_o_desfeito():
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    # Um título sem irmão, com o protesto na fila: não há o que forçar.
    livre = titulo(con, chave="3", numero="CDA-0002", cpf="00000000353")
    apontar_e_intimar(con, livre)
    protestar(con, livre)
    na_fila = ato_id(con, livre, "PROTESTO")
    with pytest.raises(PR.RetornoError, match="já está em «Esperando retorno»"):
        PR.forcar_envio_de_protocolo_ja_informado(
            con, na_fila, afirmacao=AFIRMACAO, agora=AGORA, usuario="X")
    # O desfeito não vai à CRA.
    with pytest.raises(PR.RetornoError, match="desfeito"):
        PR.forcar_envio_de_protocolo_ja_informado(
            con, caso["antigo_b"], afirmacao=AFIRMACAO, agora=AGORA,
            usuario="X")
    # A marca manual do próprio ato não se desmancha por afirmação.
    PR.marcar_ja_informado_a_cra(
        con, caso["refeito_b"], retorno_id=caso["retorno"]["retorno_id"],
        motivo="A CRA já aceitou este protocolo pelo outro título.",
        agora=AGORA, usuario="OFICIAL")
    fora = {int(p["ato_id"]): p for p in PR.ja_aceitas_fora_da_fila(con)}
    assert fora[caso["refeito_b"]]["pode_insistir"] is False
    with pytest.raises(PR.RetornoError, match="marcado à mão"):
        PR.forcar_envio_de_protocolo_ja_informado(
            con, caso["refeito_b"], afirmacao=AFIRMACAO, agora=AGORA,
            usuario="X")


# ------------------------------------------------------- a conferência


def test_a_conferencia_mostra_o_protocolo_com_dois_titulos_e_a_repeticao():
    con = banco()
    caso = o_caso_do_protocolo_2610070011(con)
    livre = titulo(con, chave="3", numero="CDA-0002", cpf="00000000353")
    apontar_e_intimar(con, livre)
    # O R9012810.261: o protesto refeito foi num arquivo que a CRA recusou.
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
               numero_da_remessa, nome_arquivo, conteudo, gerado_em,
               cra_recusado_em, cra_recusa_codigo, cra_recusa_motivo,
               cra_enviado_ambiente)
           VALUES ('SDTBFORTP', ?, ?, 1, 'R9012810.261', 'x', ?,
                   ?, '2161', 'NENHUM REGISTRO FOI GRAVADO', 'PRODUCAO')""",
        (APRESENTANTE, DIA_2, AGORA, AGORA))
    recusado = int(con.execute("SELECT MAX(id) FROM pt_retornos").fetchone()[0])
    con.execute("UPDATE pt_atos SET retorno_id=? WHERE id=?",
                (recusado, caso["refeito_b"]))

    conf = PR.protocolos_com_mais_de_um_titulo(con)
    assert conf["total"] == 1 and conf["titulos"] == 2
    assert conf["com_repeticao"] == 1 and conf["com_recusado"] == 1
    p = conf["protocolos"][0]
    assert p["protocolo"] == caso["protocolo"]
    assert p["precisa_olhar"] is True
    assert [r["ocorrencia"] for r in p["repeticoes"]] == ["C"]
    assert [a["situacao"] for a in p["repeticoes"][0]["arquivos"]] == [
        "ACEITO", "RECUSADO"]
    estados = {a["ato_id"]: a["estado"] for t in p["titulos"]
               for a in t["atos"]}
    assert estados[caso["protesto_a"]] == "INFORMADO"
    assert estados[caso["refeito_b"]] == "RECUSADO"
    assert p["situacoes_divergentes"] is False

    # Títulos do mesmo protocolo em situações diferentes: a Central guarda
    # uma ocorrência só, e a conferência avisa.
    con.execute("UPDATE pt_titulos SET situacao='CANCELADO' WHERE id=?",
                (caso["b"],))
    conf = PR.protocolos_com_mais_de_um_titulo(con)
    assert conf["divergentes"] == 1
    # O filtro por apresentante.
    assert PR.protocolos_com_mais_de_um_titulo(
        con, apresentante_codigo="341")["total"] == 0


# ------------------------------------- o contrato do roteiro do protesto


def test_o_roteiro_le_os_repetidos_na_fila_pelo_nome_combinado():
    """O roteiro (PR #104, `protesto_roteiro.GANCHOS`) chama
    `protocolos_repetidos_na_fila(con)` e lê `titulo_id`, `numero_titulo`,
    `protocolo` e `explicacao` de cada linha."""
    con = banco()
    assert PR.protocolos_repetidos_na_fila(con) == []
    caso = o_caso_do_protocolo_2610070011(con)
    linhas = {int(l["ato_id"]): l for l in PR.protocolos_repetidos_na_fila(con)}
    retido = linhas[caso["refeito_b"]]
    assert {"titulo_id", "numero_titulo", "protocolo",
            "explicacao"} <= set(retido)
    assert retido["situacao"] == "RETIDO"
    assert retido["titulo_id"] == caso["b"]
    assert retido["protocolo"] == caso["protocolo"]
    # O informante que explica é o protesto VÁLIDO do outro título.
    assert retido["explicacao"].startswith(
        f"já informado como protestado pelo título CDA-0001 #{caso['a']} "
        f"em 26/10/2026")
    assert caso["arquivo"] in retido["explicacao"]

    PR.forcar_envio_de_protocolo_ja_informado(
        con, caso["refeito_b"], afirmacao=AFIRMACAO,
        agora="2026-10-29T10:00:00", usuario="ESCREVENTE")
    linhas = {int(l["ato_id"]): l for l in PR.protocolos_repetidos_na_fila(con)}
    liberado = linhas[caso["refeito_b"]]
    assert liberado["situacao"] == "LIBERADO"
    assert "afirmação expressa de ESCREVENTE em 29/10/2026" in liberado[
        "explicacao"]


# ------------------------------------------------------------- a tela


SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(tmp_path, papel: str = "USER"):
    from app import create_app
    from database import Database

    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    caminho = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    db = Database(caminho)
    db.create_user("escrevente", "CARLA EXEMPLO", SENHA, papel)
    db.set_settings({"modulo_protesto_ligado": "1",
                     "selo_trava_caixa": "DESLIGADA"})
    c = app.test_client()
    c.post("/login",
           data={"username": "escrevente", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": caminho}


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def _afirmacoes(s) -> list:
    con = _con(s)
    linhas = con.execute(
        """SELECT entity_type, entity_id, details FROM audit_logs
            WHERE action='AFIRMACAO_EXPRESSA'""").fetchall()
    con.close()
    return linhas


def test_a_escrevente_so_insiste_com_afirmacao_e_fica_o_log(tmp_path):
    s = _sessao(tmp_path, "USER")
    con = _con(s)
    caso = o_caso_do_protocolo_2610070011(con)
    con.commit()
    con.close()
    refeito = caso["refeito_b"]

    c = s["c"]
    pagina = c.get("/protesto/retornos").get_data(as_text=True)
    assert "Já informado por outro título do mesmo protocolo" in pagina
    assert f"/protesto/retornos/ato/{refeito}/forcar-envio" in pagina
    assert caso["arquivo"] in pagina
    token = _token(pagina)

    # Sem a caixa «Afirmo», o texto não vale: recusa, e nada na auditoria.
    html = c.post(f"/protesto/retornos/ato/{refeito}/forcar-envio",
                  data={"csrf_token": token, "afirmacao": AFIRMACAO},
                  follow_redirects=True).get_data(as_text=True)
    assert "Afirmo" in html
    assert not _afirmacoes(s)
    con = _con(s)
    assert refeito not in ids_pendentes(con)
    con.close()

    html = c.post(f"/protesto/retornos/ato/{refeito}/forcar-envio",
                  data={"csrf_token": token, "afirmo": "1",
                        "afirmacao": AFIRMACAO},
                  follow_redirects=True).get_data(as_text=True)
    assert "voltou a «Esperando retorno»" in html
    linhas = _afirmacoes(s)
    assert len(linhas) == 1
    assert linhas[0]["entity_type"] == "pt_atos"
    assert int(linhas[0]["entity_id"]) == refeito
    detalhe = json.loads(linhas[0]["details"])
    assert set(detalhe) == {"regra", "afirmacao", "o_que_faltava"}
    assert detalhe["regra"] == "RETORNO_PROTOCOLO_JA_INFORMADO"
    assert detalhe["afirmacao"].startswith(PR.FRASE_DA_AFIRMACAO)
    assert caso["arquivo"] in detalhe["o_que_faltava"]
    con = _con(s)
    assert refeito in ids_pendentes(con)
    con.close()
    assert "liberado por afirmação expressa" in c.get(
        "/protesto/retornos").get_data(as_text=True)


def test_a_conferencia_abre_e_mostra_o_protocolo(tmp_path):
    s = _sessao(tmp_path, "USER")
    vazia = s["c"].get("/protesto/retornos/protocolos")
    assert vazia.status_code == 200
    assert "Nenhum protocolo com mais de um título" in vazia.get_data(
        as_text=True)
    con = _con(s)
    caso = o_caso_do_protocolo_2610070011(con)
    con.commit()
    con.close()
    html = s["c"].get("/protesto/retornos/protocolos").get_data(as_text=True)
    assert caso["protocolo"] in html
    assert f"#{caso['a']}" in html and f"#{caso['b']}" in html
    filtrada = s["c"].get(
        "/protesto/retornos/protocolos?apresentante=341").get_data(
            as_text=True)
    assert caso["protocolo"] not in filtrada
