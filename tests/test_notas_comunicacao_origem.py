"""A comunicação à serventia de origem da procuração substabelecida.

Relato #129 (10/10/2026), vindo da inspeção da Corregedoria: substabelecimento
de procuração lavrada noutra serventia (4º Ofício de Imperatriz/MA) sem
comprovação de comunicação. Código de Normas TJMA, art. 831, § 1º.

O QUE ESTES TESTES PROTEGEM
    - a obrigação NASCE no substabelecimento de procuração de outra serventia,
      e não nasce no da própria serventia, nem em outros atos;
    - o aviso PERSISTE: não some editando a origem, não some sem providência;
    - a baixa EXIGE uma das duas providências (comprovante ou ofício anotado),
      e deixa o rastro — quem, quando, o quê — na linha e na auditoria;
    - a tela mostra o aviso e os formulários, com csrf_token.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import inacabados as IN                          # noqa: E402
import notas_anotacoes as NA                     # noqa: E402
import notas_comunicacao_origem as NCO           # noqa: E402
from notas_schema import init_notas_schema       # noqa: E402

AGORA = "2026-10-14T10:00:00"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
IMPERATRIZ = {"cartorio": "4º Ofício Extrajudicial de Imperatriz/MA",
              "cns": "", "cidade": "Imperatriz", "uf": "MA",
              "livro": "12", "folha": "45", "data": "2025-03-10"}
SENHA = "Senha#12345"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    init_notas_schema(con)
    con.execute("""CREATE TABLE attachments (id INTEGER PRIMARY KEY, entity_type
                   TEXT, entity_id INTEGER, original_name TEXT, stored_name TEXT,
                   stored_path TEXT, sha256 TEXT, size_bytes INTEGER,
                   description TEXT, uploaded_by INTEGER, uploaded_at TEXT)""")
    return con


def ato(con, tipo="SUBSTABELECIMENTO", situacao="LAVRADO", **kw) -> int:
    cols = {"tipo": tipo, "data": "2026-10-01", "situacao": situacao,
            "livro": "02", "folha": "003", "criado_em": AGORA}
    cols.update(kw)
    return int(con.execute(
        f"INSERT INTO nt_atos({','.join(cols)}) VALUES "
        f"({','.join('?' * len(cols))})", tuple(cols.values())).lastrowid)


def anexo(con, ob_id, entity_type=NCO.TIPO_DO_ANEXO) -> int:
    return int(con.execute(
        """INSERT INTO attachments(entity_type, entity_id, original_name,
               stored_name, stored_path, sha256, size_bytes, uploaded_at)
           VALUES (?,?,'ar.pdf','ar.pdf','x','abc123',1,?)""",
        (entity_type, ob_id, AGORA)).lastrowid)


# ------------------------------------------------------------- nasce

def test_nasce_no_substabelecimento_de_procuracao_de_outra_serventia():
    con = banco()
    sub = ato(con)
    feito = NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "OFICIAL")
    assert feito["obrigacao_nasceu"]
    ob = NCO.do_ato(con, sub)
    assert ob["aberta"] and ob["situacao"] == "ABERTA"
    assert "Imperatriz" in ob["destinatario"]
    assert ob["procuracao_livro"] == "12" and ob["procuracao_folha"] == "45"
    assert ob["nascida_por"] == "OFICIAL" and ob["nascida_como"] == "TELA"
    # os dados da origem ficam no ato, onde a CENSEC também os lê
    linha = con.execute("SELECT * FROM nt_atos WHERE id=?", (sub,)).fetchone()
    assert linha["anterior_cartorio"].startswith("4º Ofício")


def test_nasce_no_lancamento_quando_a_origem_ja_esta_no_ato():
    con = banco()
    sub = ato(con, anterior_cartorio="2º OFÍCIO DE IMPERATRIZ",
              anterior_cns="012345")
    ob = NCO.abrir(con, sub, SV, AGORA, "ESCREVENTE", "LAVRATURA")
    assert ob and ob["nascida_como"] == "LAVRATURA"
    assert ob["destinatario_cns"] == "012345"
    # repetir não cria a segunda
    assert NCO.abrir(con, sub, SV, AGORA, "ESCREVENTE", "LAVRATURA") is None
    assert con.execute("SELECT COUNT(*) FROM nt_comunicacoes_origem").fetchone()[0] == 1


def test_em_lavratura_ainda_nao_nasce():
    con = banco()
    sub = ato(con, situacao="EM_LAVRATURA")
    feito = NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "X")
    assert not feito["obrigacao_nasceu"] and NCO.do_ato(con, sub) is None


def test_nao_nasce_no_substabelecimento_da_propria_serventia():
    con = banco()
    pelo_cns = ato(con, anterior_cns="000000", anterior_cartorio="QUALQUER")
    pelo_nome = ato(con, anterior_cartorio=SV["unit_name"])
    procuracao = ato(con, tipo="PROCURACAO", livro="27", folha="139")
    vinculado = ato(con, anterior_ato_id=procuracao, anterior_cartorio="X DE FORA")
    for a in (pelo_cns, pelo_nome, vinculado):
        assert NCO.abrir(con, a, SV, AGORA, "X", "TELA") is None
    # e o vinculado a ato desta casa nem aceita origem de fora
    with pytest.raises(NCO.ComunicacaoError, match="desta serventia"):
        NCO.informar_origem(con, vinculado, IMPERATRIZ, SV, AGORA, "X")


def test_sem_origem_informada_nao_nasce():
    con = banco()
    sub = ato(con)
    assert not NCO.devida(con.execute("SELECT * FROM nt_atos WHERE id=?",
                                      (sub,)).fetchone(), SV)
    assert NCO.abrir(con, sub, SV, AGORA, "X", "TELA") is None


@pytest.mark.parametrize("tipo", ["PROCURACAO", "ESCRITURA", "REVOGACAO",
                                  "RENUNCIA", "ATA"])
def test_nao_nasce_em_outros_atos(tipo):
    con = banco()
    a = ato(con, tipo=tipo, anterior_cartorio="4º OFÍCIO DE IMPERATRIZ",
            anterior_cns="099999")
    assert NCO.abrir(con, a, SV, AGORA, "X", "TELA") is None
    with pytest.raises(NCO.ComunicacaoError, match="Só o substabelecimento"):
        NCO.informar_origem(con, a, IMPERATRIZ, SV, AGORA, "X")


def test_ato_cancelado_ou_sem_efeito_nao_nasce():
    con = banco()
    for situacao in ("CANCELADO", "SEM_EFEITO"):
        a = ato(con, situacao=situacao, anterior_cartorio="4º OFÍCIO DE IMPERATRIZ")
        assert NCO.abrir(con, a, SV, AGORA, "X", "TELA") is None


# ------------------------------------------------------------- persiste

def test_o_aviso_persiste_e_nao_some_trocando_a_origem():
    con = banco()
    sub = ato(con)
    NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "X")
    # tentar dizer que a procuração é «desta casa» não apaga a obrigação
    with pytest.raises(NCO.ComunicacaoError, match="não\\s+some"):
        NCO.informar_origem(con, sub, {**IMPERATRIZ, "cns": "000000"},
                            SV, AGORA, "X")
    assert NCO.do_ato(con, sub)["aberta"]
    # corrigir o destinatário (ainda de fora) é permitido, e o aviso continua
    NCO.informar_origem(con, sub, {**IMPERATRIZ, "cartorio": "2º Ofício de Imperatriz"},
                        SV, AGORA, "X")
    ob = NCO.do_ato(con, sub)
    assert ob["aberta"] and ob["destinatario"].startswith("2º Ofício")
    # a lista e a lente do painel continuam mostrando
    assert [p["ato_id"] for p in NCO.pendentes(con)] == [sub]
    con.execute("CREATE TABLE IF NOT EXISTS ex_fontes (chave TEXT PRIMARY KEY, "
                "ligada INTEGER, dias INTEGER, atualizado_em TEXT, atualizado_por TEXT)")
    con.execute("CREATE TABLE IF NOT EXISTS ex_anotacoes (tabela TEXT, item_id "
                "INTEGER, texto TEXT, responsavel TEXT, ate TEXT, criado_em TEXT, "
                "criado_por TEXT, UNIQUE(tabela, item_id))")
    itens = IN.lista(con, hoje="2026-10-20", chave="NOTAS_COMUNICACAO_ORIGEM")
    assert [i["id"] for i in itens] == [sub] and itens[0]["parado"]


def test_nao_ha_funcao_de_apagar_nem_de_reabrir():
    publicos = {n for n in dir(NCO) if not n.startswith("_")}
    for proibido in ("apagar", "excluir", "remover", "reabrir", "desfazer"):
        assert not any(proibido in n for n in publicos), proibido


# ------------------------------------------------------------- baixa

def test_baixa_pelo_oficio_exige_os_quatro_campos_e_deixa_rastro():
    con = banco()
    sub = ato(con)
    NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "X")
    completo = dict(data="2026-10-13", meio="CARTA_REGISTRADA",
                    numero="OF-12/2026 / BR123456789BR", enviado_por="BEATRIZ")
    for falta in ("meio", "numero", "enviado_por", "data"):
        dados = {**completo, falta: ""}
        with pytest.raises(NCO.ComunicacaoError):
            NCO.baixar_por_oficio(con, sub, agora=AGORA, por="OFICIAL", **dados)
        assert NCO.do_ato(con, sub)["aberta"]
    with pytest.raises(NCO.ComunicacaoError, match="depois de hoje"):
        NCO.baixar_por_oficio(con, sub, agora=AGORA, por="OFICIAL",
                              **{**completo, "data": "2026-12-01"})
    ob = NCO.baixar_por_oficio(con, sub, agora=AGORA, por="OFICIAL", **completo)
    assert ob["situacao"] == "CUMPRIDA" and ob["providencia"] == "OFICIO"
    assert ob["cumprida_por"] == "OFICIAL" and ob["cumprida_em"] == AGORA
    assert ob["envio_numero"] == "OF-12/2026 / BR123456789BR"
    assert ob["envio_por"] == "BEATRIZ" and ob["envio_meio"] == "CARTA_REGISTRADA"
    # a norma pede comprovante de recebimento: a falta continua visível
    assert ob["falta_comprovante"]
    assert NCO.pendentes(con) == []
    with pytest.raises(NCO.ComunicacaoError, match="já foi baixada"):
        NCO.baixar_por_oficio(con, sub, agora=AGORA, por="OUTRO", **completo)


def test_baixa_pelo_comprovante_e_o_comprovante_depois_do_oficio():
    con = banco()
    sub = ato(con)
    NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "X")
    ob = NCO.do_ato(con, sub)
    alheio = anexo(con, ob["id"], entity_type="NT_ATO")
    with pytest.raises(NCO.ComunicacaoError, match="não pertence"):
        NCO.juntar_comprovante(con, sub, attachment_id=alheio,
                               recebido_em="2026-10-13", agora=AGORA, por="X")
    certo = anexo(con, ob["id"])
    ob = NCO.juntar_comprovante(con, sub, attachment_id=certo,
                                recebido_em="2026-10-13", agora=AGORA,
                                por="CARLA")
    assert ob["situacao"] == "CUMPRIDA" and ob["providencia"] == "COMPROVANTE"
    assert ob["comprovante_sha256"] == "abc123" and ob["comprovante_por"] == "CARLA"
    assert not ob["falta_comprovante"]
    with pytest.raises(NCO.ComunicacaoError, match="já foi juntado"):
        NCO.juntar_comprovante(con, sub, attachment_id=certo,
                               recebido_em="2026-10-13", agora=AGORA, por="X")
    # a origem não muda depois de cumprida
    with pytest.raises(NCO.ComunicacaoError, match="já foi cumprida"):
        NCO.informar_origem(con, sub, IMPERATRIZ, SV, AGORA, "X")

    # comprovante que chega DEPOIS do ofício completa sem trocar quem baixou
    outro = ato(con)
    NCO.informar_origem(con, outro, IMPERATRIZ, SV, AGORA, "X")
    NCO.baixar_por_oficio(con, outro, data="2026-10-10", meio="MALOTE_DIGITAL",
                          numero="MD-55", enviado_por="DANIEL", agora=AGORA,
                          por="DANIEL")
    ob2 = NCO.do_ato(con, outro)
    depois = NCO.juntar_comprovante(con, outro, attachment_id=anexo(con, ob2["id"]),
                                    recebido_em="2026-10-12",
                                    agora="2026-10-15T09:00:00", por="CARLA")
    assert depois["providencia"] == "OFICIO" and depois["cumprida_por"] == "DANIEL"
    assert depois["comprovante_por"] == "CARLA" and not depois["falta_comprovante"]


def test_sem_obrigacao_nao_ha_o_que_baixar():
    con = banco()
    sub = ato(con)
    with pytest.raises(NCO.ComunicacaoError, match="não tem obrigação"):
        NCO.baixar_por_oficio(con, sub, data="2026-10-13", meio="EMAIL",
                              numero="1", enviado_por="X", agora=AGORA, por="X")


def test_cumprida_sai_da_lista_das_anotacoes_pendentes():
    con = banco()
    sub = ato(con)
    NCO.informar_origem(con, sub, {**IMPERATRIZ, "cns": "999999"}, SV, AGORA, "X")
    assert sub in [p["id"] for p in NA.pendentes(con)]
    NCO.baixar_por_oficio(con, sub, data="2026-10-13", meio="EMAIL", numero="7",
                          enviado_por="X", agora=AGORA, por="X")
    assert sub not in [p["id"] for p in NA.pendentes(con)]


# ------------------------------------------------------------- pelas telas

def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def serventia(cg_casa):
    app = cg_casa["app"]
    cg_casa["db"].create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": cg_casa["banco"], "db": cg_casa["db"],
            "dados": cg_casa["dados"]}


def sql(s, comando, args=()):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    cur = con.execute(comando, args)
    linhas = [dict(r) for r in cur.fetchall()]
    con.commit()
    ultimo = cur.lastrowid
    con.close()
    return linhas, ultimo


def _sub_lavrado(s) -> int:
    _, novo = sql(s, """INSERT INTO nt_atos(tipo, data, livro, folha, situacao,
                            interessado, criado_em)
                        VALUES ('SUBSTABELECIMENTO','2026-09-30','02','003',
                                'LAVRADO','JOSE OUTORGADO','2026-09-30T10:00:00')""")
    return novo


def _post(s, ato_id, **dados):
    html = s["cliente"].get(f"/notas/atos/{ato_id}").get_data(as_text=True)
    dados.setdefault("csrf_token", _token(html))
    return s["cliente"].post(f"/notas/atos/{ato_id}/comunicacao-origem",
                             data=dados, follow_redirects=True,
                             content_type="multipart/form-data")


def test_a_tela_mostra_o_formulario_da_origem_com_csrf(serventia):
    sub = _sub_lavrado(serventia)
    html = serventia["cliente"].get(f"/notas/atos/{sub}").get_data(as_text=True)
    assert 'id="comunicacao-origem"' in html
    trecho = html[html.index('id="comunicacao-origem"'):]
    assert f'/notas/atos/{sub}/comunicacao-origem' in trecho
    assert 'name="csrf_token"' in trecho and 'value="origem"' in trecho


def test_pela_tela_nasce_avisa_e_baixa_com_rastro(serventia):
    sub = _sub_lavrado(serventia)
    corpo = _post(serventia, sub, acao="origem", **IMPERATRIZ).get_data(as_text=True)
    assert "Nasceu a obrigação" in corpo
    assert "COMUNICAÇÃO À SERVENTIA DE ORIGEM PENDENTE" in corpo
    trecho = corpo[corpo.index('id="comunicacao-origem"'):]
    # os dois formulários de baixa, cada um com o seu token
    assert 'value="oficio"' in trecho and 'value="comprovante"' in trecho
    assert trecho.count('name="csrf_token"') >= 3
    assert 'enctype="multipart/form-data"' in trecho

    # o painel e a lista de pendências mostram
    painel = serventia["cliente"].get("/").get_data(as_text=True)
    assert "Substabelecimento sem comunicação à serventia de origem" in painel
    lista = serventia["cliente"].get("/notas/anotacoes/pendentes").get_data(as_text=True)
    assert "1 obrigação(ões) aberta(s)" in lista

    # baixar sem a providência completa é recusado, e o aviso fica
    corpo = _post(serventia, sub, acao="oficio", envio_data="2026-10-13",
                  envio_meio="CARTA_REGISTRADA", envio_numero="",
                  envio_por="BEATRIZ").get_data(as_text=True)
    assert "número do ofício" in corpo
    assert "COMUNICAÇÃO À SERVENTIA DE ORIGEM PENDENTE" in corpo

    # o comprovante baixa
    corpo = _post(serventia, sub, acao="comprovante", recebido_em="2026-10-13",
                  comprovante=(io.BytesIO(b"%PDF-1.4 AR"), "ar.pdf")
                  ).get_data(as_text=True)
    assert "Comprovante juntado" in corpo
    assert "COMUNICAÇÃO À SERVENTIA DE ORIGEM PENDENTE" not in corpo
    (ob,), _ = sql(serventia, "SELECT * FROM nt_comunicacoes_origem WHERE ato_id=?",
                   (sub,))
    assert ob["situacao"] == "CUMPRIDA" and ob["providencia"] == "COMPROVANTE"
    assert ob["cumprida_por"] == "MARIO EXEMPLO DOS SANTOS"
    (anx,), _ = sql(serventia, "SELECT * FROM attachments WHERE id=?",
                    (ob["comprovante_attachment_id"],))
    assert anx["entity_type"] == NCO.TIPO_DO_ANEXO and anx["sha256"] == ob["comprovante_sha256"]
    acoes = [r["action"] for r in sql(
        serventia, "SELECT action FROM audit_logs WHERE entity_id=? "
                   "AND action LIKE 'NT_COMUNICACAO_ORIGEM%'", (sub,))[0]]
    assert "NT_COMUNICACAO_ORIGEM_INFORMADA" in acoes
    assert "NT_COMUNICACAO_ORIGEM_COMPROVANTE" in acoes
    lista = serventia["cliente"].get("/notas/anotacoes/pendentes").get_data(as_text=True)
    assert "0 obrigação(ões) aberta(s)" in lista


def test_o_ato_do_acervo_ganha_a_obrigacao_por_botao(serventia):
    """O caminho do caso da inspeção: ato já lavrado, com a origem de fora,
    sem a obrigação — ninguém a lança sozinho; a ficha avisa e oferece."""
    _, sub = sql(serventia, """INSERT INTO nt_atos(tipo, data, livro, folha,
                                   situacao, acervo, origem, anterior_cartorio,
                                   anterior_cidade, anterior_uf, criado_em)
                               VALUES ('SUBSTABELECIMENTO','2025-11-03','02','003',
                                       'LAVRADO',1,'EOFICIO',
                                       '4º Ofício Extrajudicial de Imperatriz',
                                       'Imperatriz','MA','2026-08-01T10:00:00')""")
    html = serventia["cliente"].get(f"/notas/atos/{sub}").get_data(as_text=True)
    assert "SEM OBRIGAÇÃO DE COMUNICAÇÃO LANÇADA" in html
    assert 'value="abrir"' in html
    corpo = _post(serventia, sub, acao="abrir").get_data(as_text=True)
    assert "Obrigação de comunicação lançada" in corpo
    corpo = _post(serventia, sub, acao="oficio", envio_data="2026-10-14",
                  envio_meio="MALOTE_DIGITAL", envio_numero="MD-2026-0099",
                  envio_por="CARLA").get_data(as_text=True)
    assert "Envio do ofício anotado" in corpo
    assert "comprovante de recebimento ainda não juntado" in corpo
    (ob,), _ = sql(serventia, "SELECT * FROM nt_comunicacoes_origem WHERE ato_id=?",
                   (sub,))
    assert ob["envio_numero"] == "MD-2026-0099" and ob["envio_por"] == "CARLA"


def test_o_lancamento_pela_tela_faz_nascer_a_obrigacao(serventia):
    """O caminho de todo dia: o substabelecimento nasce em lavratura, a
    origem é informada antes, e a obrigação nasce no lançamento — na mesma
    transação do livro."""
    from selador_de_bancada import ligar_o_selador
    from notas_pronto_para_a_censec import preparar

    html = serventia["cliente"].get("/notas/atos/novo").get_data(as_text=True)
    serventia["cliente"].post("/notas/atos/novo",
                              data={"csrf_token": _token(html),
                                    "tipo": "SUBSTABELECIMENTO"},
                              follow_redirects=True)
    (novo,), _ = sql(serventia, "SELECT MAX(id) id FROM nt_atos")
    novo = novo["id"]
    corpo = _post(serventia, novo, acao="origem", **IMPERATRIZ).get_data(as_text=True)
    assert "Nasceu a obrigação" not in corpo          # ainda em lavratura
    assert "nasce sozinha quando este ato for lançado" in corpo

    def acao(**dados):
        h = serventia["cliente"].get(f"/notas/atos/{novo}").get_data(as_text=True)
        dados.setdefault("csrf_token", _token(h))
        return serventia["cliente"].post(f"/notas/atos/{novo}", data=dados,
                                         follow_redirects=True)

    # O ARQUIVAMENTO É OBRIGATÓRIO NO SUBSTABELECIMENTO desde 15/10/2026
    # (pedido do oficial): sem o documento anexado e as folhas confirmadas o
    # lançamento é recusado — ver test_arquivamento_obrigatorio_procuracao.py.
    import io
    h = serventia["cliente"].get(f"/notas/atos/{novo}").get_data(as_text=True)
    serventia["cliente"].post(
        f"/notas/atos/{novo}/anexos",
        data={"csrf_token": _token(h), "descricao": "Documento arquivado",
              "arquivo": (io.BytesIO(b"\xff\xd8\xff\xe0 imagem"), "doc.jpg")},
        content_type="multipart/form-data", follow_redirects=True)
    acao(acao="confirmar_arquivamento", folhas_arquivamento="1")

    with ligar_o_selador(serventia):
        acao(acao="teor", teor="<p>substabeleço os poderes</p>")
        preparar(serventia["banco"], novo)
        corpo = acao(acao="lancar", paginas=2, codigo_tj="13.9.3").get_data(as_text=True)
    (linha,), _ = sql(serventia, "SELECT * FROM nt_atos WHERE id=?", (novo,))
    assert linha["situacao"] != "EM_LAVRATURA", corpo[:2000]
    (ob,), _ = sql(serventia, "SELECT * FROM nt_comunicacoes_origem WHERE ato_id=?",
                   (novo,))
    assert ob["situacao"] == "ABERTA" and ob["nascida_como"] == "LAVRATURA"
    assert "Nasceu a" in corpo and "obrigação de comunicá-la" in corpo
    assert "COMUNICAÇÃO À SERVENTIA DE ORIGEM PENDENTE" in corpo


def test_escritura_nao_tem_o_quadro(serventia):
    _, esc = sql(serventia, """INSERT INTO nt_atos(tipo, data, situacao, criado_em)
                               VALUES ('ESCRITURA','2026-09-30','LAVRADO',
                                       '2026-09-30T10:00:00')""")
    html = serventia["cliente"].get(f"/notas/atos/{esc}").get_data(as_text=True)
    assert 'id="comunicacao-origem"' not in html
