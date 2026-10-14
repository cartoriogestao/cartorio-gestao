"""A tela da remessa do SIRC.

POR QUE SEPARADO
    `test_sirc_remessa.py` prova que o **módulo** lista e parte em lotes. Este
    prova que a **tela chama o módulo** — décimo caso, neste projeto, em que essa
    diferença importa.

E O QUE ELA TEM DE DIZER
    **O prazo.** Um dia útil é o mais curto da casa, e quem abre a tela sem saber
    disso a trata como as outras. A sanção também: o § 4º pune o descumprimento
    **e a informação inexata**, com ação regressiva do INSS.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_matricula as RCM                                       # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-20T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    """O HTML sem as quebras de linha do Jinja.

    JÁ ERRAMOS ISSO TRÊS VEZES: o modelo quebra a frase no meio e o `in` falha
    numa comparação que está certa.
    """
    return " ".join((t or "").split())


def _assento(casa, *, especie="NASCIMENTO", nome="MARIA", numero=1,
             data_ato="2026-08-20"):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A',?,?,?,?,?,'ATIVO','SISTEMA',?)""",
            (especie, numero, nome, data_ato, data_ato, AGORA))
        return int(cur.lastrowid)


def _assento_pronto(casa, *, nome="MARIA ÍSIS DA CONCEIÇÃO", numero=1):
    """Um NASCIMENTO com matrícula — o que `o_que_falta` exige para sair da
    remessa. `_assento()` não a grava, e por isso serve aos testes de
    "sem lote pronto"; este serve aos que precisam de um lote de verdade."""
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1",
                           livro=24, folha=166, termo=19565 + numero)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula,
                   ibge_local_nascimento)
               VALUES ('RC_A','NASCIMENTO',?,?,?,?,'ATIVO','SISTEMA',?,?,1)""",
            (numero, nome, "2026-08-20", "2026-08-18", AGORA, matricula))


def _abrir(casa, url="/rcpn/sirc"):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


# ------------------------------------------------ a tela diz a norma


def test_a_tela_diz_o_prazo_de_um_dia_util(casa):
    """É o prazo mais curto da casa, e quem abre a tela sem saber disso a trata
    como as outras."""
    html = _abrir(casa)
    assert "art. 225" in html
    assert "1 dia útil" in html


def test_a_tela_diz_a_sancao(casa):
    """Mandar errado é pior que não mandar: o § 4º pune a informação inexata com
    a penalidade do art. 92 **e ação regressiva do INSS**."""
    html = _abrir(casa)
    assert "art. 92 da Lei nº 8.212/1991" in html
    assert "ação regressiva" in html


def test_a_tela_diz_que_sao_sete_coisas(casa):
    """A CRC recebe três; aqui entram também averbação, anotação e retificação —
    e é isso que liga esta remessa ao módulo de anotações."""
    html = _abrir(casa)
    for palavra in ("Nascimento", "Natimorto", "Casamento", "Óbito",
                    "Averbação", "Anotação", "Retificação"):
        assert palavra in html, f"a tela não diz que «{palavra}» vai na remessa"


def test_a_tela_diz_do_mes_sem_movimento(casa):
    """Mês sem registro nenhum **também se comunica** (§ 3º) — é a declaração de
    inexistência, e quem não souber dela vai achar que mês vazio dispensa."""
    html = _abrir(casa)
    assert "mês sem registro nenhum também se comunica" in html.lower()
    assert "5º dia útil do mês seguinte" in html


def test_a_tela_diz_que_envia_sem_a3(casa):
    """**CORRIGIDO EM 14/09/2026** — a tela dizia «este sistema não
    envia», e deixou de ser verdade: o caminho por usuário e senha
    (`sirc_cliente.py`) manda de verdade. Só o OUTRO web service do SIRC
    (`MovimentoCertificadoDigital`) exige A3."""
    html = _abrir(casa)
    assert "este sistema envia" in html.lower()
    assert "A3" in html
    assert "não fala com ele" in html


def test_a_tela_linka_direto_para_configuracoes(casa):
    """**RELATADO PELO OFICIAL EM 14/09/2026**: "não achei onde colocar a
    credencial". A frase «informe em Administrativo → Configurações» era
    só texto, sem link — ao contrário de toda outra tela deste sistema
    que pede credencial de Central. E ela também precisa dizer que é a
    MESMA senha do SIRC-Web, não uma nova."""
    r = casa["cliente"].get("/rcpn/sirc")
    html = r.get_data(as_text=True)
    assert f'href="/configuracoes"' in html
    assert "mesma senha" in html.lower()
    assert "sirc.dataprev.gov.br" in html


# ------------------------------------------------ a tela chama o módulo


def test_a_tela_lista_o_que_espera(casa):
    _assento(casa, nome="MARIA ÍSIS")
    html = _abrir(casa)
    assert "MARIA ÍSIS" in html
    assert "Esperando remessa (1)" in html


def test_a_tela_lista_os_tres_atos_junto(casa):
    """Se ela listasse só `rc_assentos`, a averbação sairia da remessa sem
    ninguém ver — e o art. 225 a exige.

    **DESDE 14/09/2026 A LINHA NÃO DIZ MAIS «AVERBACAO»** — o `tipo` virou
    a espécie (NASCIMENTO), porque o manual manda reenviar o registro
    inteiro como Alteração. A coluna «O quê» é quem diz que aquela linha é
    a alteração, e com qual ato."""
    aid = _assento(casa, nome="MARIA")
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, criado_em)
               VALUES (?,'AVERBACAO',?,?)""", (aid, "2026-08-21", AGORA))
    html = _abrir(casa)
    assert "Alteração" in html
    assert "Averbacao" in html
    assert "Esperando remessa (2)" in html


def test_sem_matricula_nao_oferece_arquivo(casa):
    """`_assento` (o ajudante deste teste) não grava matrícula — e desde
    13/09/2026 ela é obrigatória (os nove campos de `registroCivil` vêm
    dela). Sem matrícula, mesmo nascimento fica retido, e a tela não
    oferece nenhum arquivo para baixar."""
    for i in range(1, 6):
        _assento(casa, nome=f"PESSOA {i}", numero=i)
    html = _abrir(casa)
    assert "Nenhum arquivo pronto para baixar" in html
    assert "arquivo(s)" not in html


def test_a_tela_vazia_nao_assusta(casa):
    """Lista vazia que só mostra nada faz o operador achar que quebrou."""
    html = _abrir(casa)
    assert "Nada esperando remessa" in html


def test_a_tela_nao_grava_nada(casa):
    """Abrir a remessa não muda nada no banco — o que muda é o envio, e este
    sistema não envia."""
    aid = _assento(casa, nome="MARIA")
    antes = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    _abrir(casa)
    depois = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


def test_a_remessa_esta_no_menu(casa):
    assert "Remessa do SIRC" in _abrir(casa)


# ------------------------------------------------ o arquivo


def test_a_tela_baixa_o_lote_em_utf8(casa):
    """O acento conta no limite de tamanho, que é em bytes.

    **NASCIMENTO JÁ SAI** (o envelope `movimentoNascimentoTO` foi
    reconstruído e validado contra o XSD do manual em 13/09/2026), desde
    que o assento tenha matrícula — sem ela, `o_que_falta` retém."""
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1",
                           livro=24, folha=166, termo=19565)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula,
                   ibge_local_nascimento)
               VALUES ('RC_A','NASCIMENTO',1,'MARIA ÍSIS DA CONCEIÇÃO',
                       '2026-08-20','2026-08-18','ATIVO','SISTEMA',?,?,1)""",
            (AGORA, matricula))
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/1",
                            data={"csrf_token": _token(html),
                                  "competencia": "2026-08"})
    assert r.status_code == 200
    assert r.mimetype == "application/xml"
    assert "sirc-remessa-001.xml" in r.headers["Content-Disposition"]
    texto = r.data.decode("utf-8")
    assert "MARIA ÍSIS DA CONCEIÇÃO" in texto
    assert "<movimentoNascimentoTO>" in texto


def test_a_tela_baixa_o_mrc_pronto_para_upload_manual(casa):
    """**ENTROU EM 14/09/2026** — quando a API recusou a credencial e o
    oficial foi tentar a importação manual: o `.xml` cru não serve para
    o SIRC-Web, que só aceita `.mrc` (comprimido e cifrado, seção 3 do
    manual)."""
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1",
                           livro=24, folha=166, termo=19566)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em, matricula,
                   ibge_local_nascimento)
               VALUES ('RC_A','NASCIMENTO',1,'MARIA ÍSIS DA CONCEIÇÃO',
                       '2026-08-20','2026-08-18','ATIVO','SISTEMA',?,?,1)""",
            (AGORA, matricula))
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/1/mrc",
                            data={"csrf_token": _token(html)})
    assert r.status_code == 200
    assert r.mimetype == "application/octet-stream"
    assert "sirc-remessa-001.mrc" in r.headers["Content-Disposition"]
    # O corpo não é XML — é comprimido e cifrado.
    assert b"<movimentoNascimentoTO>" not in r.data


def test_o_mrc_de_lote_que_nao_existe_avisa(casa):
    _assento(casa, nome="MARIA")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/9/mrc",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "nao existe" in _liso(r.get_data(as_text=True)).lower() or \
        "não existe" in _liso(r.get_data(as_text=True))


def test_pedir_lote_que_nao_existe_avisa_em_vez_de_estourar(casa):
    _assento(casa, nome="MARIA")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/9",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "Esse lote nao existe" in _liso(r.get_data(as_text=True))


def test_a_tela_mostra_o_retido_com_o_motivo(casa):
    """Mandar só o que deu certo produziria arquivo bem formado e incompleto — e
    o § 4º pune a informação inexata com ação regressiva do INSS."""
    con = _con(casa)
    with con:
        con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome,
                   situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',9,'SEM DATA','ATIVO','SISTEMA',?)""",
            (AGORA,))
    html = _abrir(casa)
    assert "1 ficaram de fora" in html
    assert "SEM DATA" in html
    assert "a data do ato" in html


def test_a_tela_gera_a_declaracao_de_mes_vazio(casa):
    """§ 3º — mês sem registro nenhum também se comunica."""
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/inexistencia",
                            data={"csrf_token": _token(html),
                                  "competencia": "2026-07"})
    assert r.status_code == 200
    texto = r.data.decode("utf-8")
    assert "<declaracaoInexistenciaMovimentoServicoTO>" in texto
    assert "<competencia>7/2026</competencia>" in texto
    assert "<declaracaoInexistenciaMovimentoNascimento>true</declaracaoInexistenciaMovimentoNascimento>" in texto


def test_a_declaracao_sem_mes_volta_avisando(casa):
    """Erro de regra não é HTTP 500: volta com a frase pronta para o balcão."""
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/inexistencia",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "Diga de qual mês é a declaração" in _liso(r.get_data(as_text=True))


def test_baixar_o_arquivo_nao_grava_nada(casa):
    """Montar não muda nada no banco — o que muda é o envio, e este sistema não
    envia."""
    aid = _assento(casa, nome="MARIA")
    antes = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    casa["cliente"].post("/rcpn/sirc/arquivo/1",
                         data={"csrf_token": _token(html)})
    depois = dict(_con(casa).execute(
        "SELECT * FROM rc_assentos WHERE id=?", (aid,)).fetchone())
    assert antes == depois


# ------------------------------------------------ o envio pela API, sem A3


def test_enviar_sem_credencial_avisa_onde_informar(casa, tmp_path, monkeypatch):
    """Sem `sirc.cred`, o botão não estoura — devolve a frase de
    `centrais_cred.credencial()`, dizendo onde configurar.

    **A PASTA É ISOLADA COM `monkeypatch`** — a mesma correção que
    `test_cra21_web.py` já registrou: sem isolar, o teste lê (e um dia
    poderia escrever em) `%PROGRAMDATA%\\CartorioGestao\\`, onde mora a
    credencial de verdade da casa.
    """
    import centrais_cred as CRED
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    _assento(casa, nome="MARIA")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/1/enviar",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    texto = _liso(r.get_data(as_text=True))
    assert "SIRC" in texto
    assert "Administrativo" in texto or "Configurações" in texto


def test_validar_sem_credencial_avisa_onde_informar(casa, tmp_path, monkeypatch):
    import centrais_cred as CRED
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    _assento(casa, nome="MARIA")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/1/validar",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "SIRC" in _liso(r.get_data(as_text=True))


def test_enviar_com_credencial_chama_o_cliente_e_mostra_o_resultado(
        casa, monkeypatch):
    """A tela não monta o envelope duas vezes — chama `sirc_cliente.enviar`
    com o mesmo XML que `sirc_remessa.montar()` já produziu.

    `sirc_cliente.enviar` é quem checaria a credencial; como este teste o
    troca por um fake, não há disco nenhum para isolar aqui — o teste que
    isso importaria é o de "sem credencial", acima."""
    _assento_pronto(casa)

    import sirc_cliente as SC
    recebido = {}

    def _fake_enviar(especie, conteudo, *, cns, prazo=120, pasta=None):
        recebido["especie"] = especie
        recebido["conteudo"] = conteudo
        return "Recebido com sucesso"

    monkeypatch.setattr(SC, "enviar", _fake_enviar)
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/1/enviar",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    texto = _liso(r.get_data(as_text=True))
    assert "Recebido com sucesso" in texto
    assert recebido["especie"] == "NASCIMENTO"
    assert "<registroNascimentoInclusao>" in recebido["conteudo"]


def test_declarar_inexistencia_pela_api(casa, monkeypatch):
    import sirc_cliente as SC
    recebido = {}

    def _fake(conteudo, *, cns, prazo=120, pasta=None):
        recebido["conteudo"] = conteudo
        return "Recebido"

    monkeypatch.setattr(SC, "declarar_inexistencia", _fake)
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/inexistencia/enviar",
                            data={"csrf_token": _token(html),
                                  "competencia": "2026-07"},
                            follow_redirects=True)
    assert "Recebido" in _liso(r.get_data(as_text=True))
    assert "<competencia>7/2026</competencia>" in recebido["conteudo"]


def test_enviar_lote_que_nao_existe_avisa(casa):
    _assento(casa, nome="MARIA")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/arquivo/9/enviar",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "nao existe" in _liso(r.get_data(as_text=True)).lower() or \
        "não existe" in _liso(r.get_data(as_text=True))


# ------------------------------------------------ o cancelamento de termo


def test_a_tela_lista_o_cancelamento_pendente(casa):
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1", livro=24,
                           folha=166, termo=20000)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome,
                   data_ato, data_fato, situacao, origem, criado_em,
                   matricula)
               VALUES ('RC_A','NASCIMENTO',1,'CANCELADO AQUI','2026-08-20',
                       '2026-08-20','CANCELADO','SISTEMA',?,?)""",
            (AGORA, matricula))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
                   criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
            (aid, "2026-08-21", "art. 347 do Código de Normas", AGORA))
    html = _abrir(casa)
    assert "Cancelamento de termo (1)" in html


def test_a_tela_baixa_o_lote_de_cancelamento(casa):
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1", livro=24,
                           folha=166, termo=20001)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome,
                   data_ato, data_fato, situacao, origem, criado_em,
                   matricula)
               VALUES ('RC_A','NASCIMENTO',1,'CANCELADO AQUI','2026-08-20',
                       '2026-08-20','CANCELADO','SISTEMA',?,?)""",
            (AGORA, matricula))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
                   criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
            (aid, "2026-08-21", "art. 347 do Código de Normas", AGORA))
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/cancelamento/arquivo/1",
                            data={"csrf_token": _token(html)})
    assert r.status_code == 200
    texto = r.data.decode("utf-8")
    assert "<movimentoCancelamentoTO>" in texto
    assert "<registroTermoCancelado>" in texto


def test_cancelamento_sem_credencial_avisa_onde_informar(
        casa, tmp_path, monkeypatch):
    import centrais_cred as CRED
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)
    con = _con(casa)
    matricula = RCM.compor(cns="000000", ano=2026, livro_tipo="1", livro=24,
                           folha=166, termo=20002)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome,
                   data_ato, data_fato, situacao, origem, criado_em,
                   matricula)
               VALUES ('RC_A','NASCIMENTO',1,'CANCELADO AQUI','2026-08-20',
                       '2026-08-20','CANCELADO','SISTEMA',?,?)""",
            (AGORA, matricula))
        aid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO rc_atos (assento_id, tipo, data_ato, fundamento,
                   criado_em) VALUES (?,'AVERBACAO',?,?,?)""",
            (aid, "2026-08-21", "art. 347 do Código de Normas", AGORA))
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    r = casa["cliente"].post("/rcpn/sirc/cancelamento/arquivo/1/enviar",
                            data={"csrf_token": _token(html)},
                            follow_redirects=True)
    assert "SIRC" in _liso(r.get_data(as_text=True))


def test_o_envio_pela_api_fica_anotado_e_sai_da_lista(casa, monkeypatch):
    """06/10/2026: o botão «Enviar» falava com a Central e não anotava nada —
    o registro voltava amanhã como devido, podia ser mandado de novo, e o
    gestor o cobrava como atrasado para sempre. Agora o envio grava em
    `ge_envios` (canal API, a resposta do SIRC como protocolo) e o registro
    sai da lista."""
    _assento_pronto(casa, nome="ENVIADO PELA API", numero=7)
    import sirc_cliente as SC
    monkeypatch.setattr(
        SC, "enviar",
        lambda especie, conteudo, *, cns, prazo=120, pasta=None: "PROTOCOLO 123")
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    assert "ENVIADO PELA API" in _liso(html)
    casa["cliente"].post("/rcpn/sirc/arquivo/1/enviar",
                         data={"csrf_token": _token(html)},
                         follow_redirects=True)
    linhas = _con(casa).execute(
        "SELECT referencia, protocolo, canal FROM ge_envios "
        "WHERE central = 'SIRC'").fetchall()
    assert any(l["protocolo"] == "PROTOCOLO 123" and l["canal"] == "API"
               for l in linhas)
    assert "ENVIADO PELA API" not in _abrir(casa)


def test_envio_recusado_nao_anota_nada(casa, monkeypatch):
    """O que o SIRC recusou não foi enviado: anotar seria esconder o atraso."""
    _assento_pronto(casa, nome="RECUSADO PELO SIRC", numero=8)
    import sirc_cliente as SC

    def _recusa(especie, conteudo, *, cns, prazo=120, pasta=None):
        raise SC.SircRecusou("O SIRC recusou ao enviar: teste")

    monkeypatch.setattr(SC, "enviar", _recusa)
    antes = _con(casa).execute(
        "SELECT COUNT(*) FROM sqlite_master WHERE name = 'ge_envios'").fetchone()[0]
    n_antes = (_con(casa).execute("SELECT COUNT(*) FROM ge_envios").fetchone()[0]
               if antes else 0)
    html = casa["cliente"].get("/rcpn/sirc").get_data(as_text=True)
    casa["cliente"].post("/rcpn/sirc/arquivo/1/enviar",
                         data={"csrf_token": _token(html)},
                         follow_redirects=True)
    n_depois = _con(casa).execute("SELECT COUNT(*) FROM ge_envios").fetchone()[0]         if _con(casa).execute("SELECT COUNT(*) FROM sqlite_master "
                              "WHERE name = 'ge_envios'").fetchone()[0] else 0
    assert n_depois == n_antes
    assert "RECUSADO PELO SIRC" in _abrir(casa)
