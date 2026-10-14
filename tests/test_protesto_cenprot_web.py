"""
Testes da TELA da chave do CENPROT.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMINIO
    «Funcao de dominio pronta que nenhuma tela chama» e o defeito que mais se
    repetiu neste projeto — seis vezes —, e o modulo do CENPROT nasceu assim:
    leitor pronto, testado, e sem por onde o balcao mandar o arquivo.

O QUE ESTES TESTES GUARDAM, E QUE O TESTE DE DOMINIO NAO ALCANCA
      - a tela EXISTE e esta NO MENU (o defeito das seis vezes);
      - ela manda o `csrf_token` — dez formularios da casa nao mandavam, e o
        balcao levou «bad request error» em 27/08/2026;
      - o arquivo de OUTRA SERVENTIA e recusado NA TELA, com a mensagem em
        portugues, e nao com um HTTP 500;
      - a tela mostra os TRES numeros do quadro, e nao um: «faltam 1.366»
        esconderia que a maioria falta por um motivo que esta tela nao
        resolve;
      - ela nao promete conserto que nao pode fazer: o link da carga so
        aparece para quem pode abri-la.

E ELES ACHARAM UM DEFEITO NA PRIMEIRA RODADA, que e a razao de existirem:
a rota chamava `guardar` direto, e quando NADA entra ele **recusa** — certo do
lado do dominio. So que a rota respondia com `flash` e `redirect`, e o
redirecionamento **jogava fora a lista do que nao casou e por que**: a
informacao mais util, descartada justamente no caso em que ela e a unica coisa
que ha para ver. Os dois testes que a exigem sao
`test_titulo_que_nao_casa_aparece_com_o_motivo` e
`test_divergencia_nao_grava_e_a_tela_explica_que_parou_de_proposito`.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — acervo_eoficio / integração pesada
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"
AGORA = "2026-09-01T10:00:00"

CHAVE = "21987650141243301260417"
PROTOCOLO = "2604170001"
NOSSO = "YK0000000000072"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    # A IDENTIDADE DA CASA — sem ela a tela nem confere o arquivo, e esta certo:
    # é o que separa «este arquivo é nosso» de «este é da serventia vizinha».
    bd.set_settings({"ibge_uf": "21", "ibge_municipio": "98765",
                     "ibge_cartorio": "01", "ibge_distrito": "05"})
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def titulo(s, *, protocolo=PROTOCOLO, nosso=NOSSO, numero="EDILENA0003") -> int:
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, situacao, protocolo,
                   origem, criado_em)
               VALUES ('DMI',?,?,200785,200785,'APONTADO',?,'CRA',?)""",
            (numero, nosso, protocolo, AGORA))
        tid = int(cur.lastrowid)
    con.close()
    return tid


def xml(*, comarca="2198765", cartorio="01", chave=CHAVE,
        protocolo=PROTOCOLO, nosso=NOSSO) -> bytes:
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        '<estados total="1" versao="1.23-geral"><estado uf="MA">'
        f'<cartorios total="1"><cartorio codigo="{cartorio}" '
        f'comarca="{comarca}">'
        '<apresentantes total="1"><apresentante codigo="033">'
        '<nome>BANCO SANTANDER</nome><titulos total="1">'
        f'<titulo id="{chave}"><nosso_numero>{nosso}</nosso_numero>'
        '<numero_titulo>EDILENA0003</numero_titulo><valor>2007.8500</valor>'
        f'<protocolo>{protocolo}</protocolo>'
        '<data_protocolo>2026-04-17</data_protocolo>'
        '</titulo></titulos></apresentante></apresentantes>'
        '</cartorio></cartorios></estado></estados>').encode()


def mandar(s, conteudo: bytes, nome="MA-2198765-01-P-20260831-01.xml"):
    import io
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    return s["c"].post(
        "/protesto/cenprot",
        data={"csrf_token": _token(tela),
              "arquivo": (io.BytesIO(conteudo), nome)},
        content_type="multipart/form-data", follow_redirects=True)


# --------------------------------------------------------- a tela existe


def test_a_tela_abre(s):
    r = s["c"].get("/protesto/cenprot")
    assert r.status_code == 200
    assert "Chave do CENPROT" in r.get_data(as_text=True)


def test_a_tela_esta_no_menu(s):
    """O DEFEITO DAS SEIS VEZES: funcao pronta que nenhuma tela chama."""
    html = s["c"].get("/protesto/titulos").get_data(as_text=True)
    assert 'href="/protesto/cenprot"' in html


def test_a_tela_manda_o_csrf_token(s):
    """Dez formularios da casa nao mandavam, e o balcao levou «bad request»."""
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert 'name="csrf_token"' in html


# --------------------------------------------------------- o quadro


def test_o_quadro_mostra_os_tres_numeros(s):
    """«Faltam 1.366» esconderia que a maioria falta por outro motivo."""
    titulo(s)
    titulo(s, protocolo="", nosso="A", numero="SEM PROTOCOLO")
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Já têm a chave do CENPROT" in html
    assert "Esperando a chave" in html
    assert "Sem protocolo" in html


def test_o_quadro_explica_o_que_esta_tela_nao_resolve(s):
    """Sem protocolo nao ha por onde casar — e o conserto e outra tela."""
    titulo(s, protocolo="", nosso="A", numero="SEM PROTOCOLO")
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Trazer o\n    acervo do E-Ofício" in html or \
           "acervo do E-Ofício" in html


def test_o_escrevente_nao_ve_link_para_tela_que_nao_pode_abrir(cg_casa):
    """Link que devolve 403 faz o escrevente achar que o sistema quebrou."""
    s = _sessao(cg_casa, papel="USER")
    titulo(s, protocolo="", nosso="A", numero="SEM PROTOCOLO")
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "só o administrador abre" in html
    assert 'href="/atribuicoes/importar"' not in html


# --------------------------------------------------------- guardar pela tela


def test_manda_o_arquivo_e_a_chave_fica_guardada(s):
    tid = titulo(s)
    r = mandar(s, xml())
    assert r.status_code == 200
    con = _con(s)
    guardada = con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                           (tid,)).fetchone()[0]
    con.close()
    assert guardada == CHAVE


def test_a_tela_mostra_a_chave_guardada(s):
    titulo(s)
    html = mandar(s, xml()).get_data(as_text=True)
    assert CHAVE in html
    assert "Chaves guardadas" in html


def test_arquivo_de_outra_serventia_e_recusado_na_tela(s):
    """E COM A MENSAGEM EM PORTUGUES, e nao com um HTTP 500.

    Erro de regra e subclasse de `ValueError` e a rota o trata com `flash` —
    a regra da casa, e aqui ela protege contra escrever nos nossos titulos as
    chaves dos titulos da serventia vizinha.
    """
    tid = titulo(s)
    r = mandar(s, xml(comarca="2801405"))
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    assert "não é desta serventia" in html or "NAO e desta serventia" in html
    con = _con(s)
    ficou = con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                        (tid,)).fetchone()[0]
    con.close()
    assert ficou is None, "nada foi gravado"


def test_arquivo_que_nao_e_xml_recusa_sem_estourar(s):
    titulo(s)
    r = mandar(s, b"isto nao e um xml", nome="qualquer.xml")
    assert r.status_code == 200
    assert "letra «P»" in r.get_data(as_text=True)


def test_sem_escolher_arquivo_a_tela_avisa(s):
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot", data={"csrf_token": _token(tela)},
                    content_type="multipart/form-data", follow_redirects=True)
    assert "Escolha o arquivo" in r.get_data(as_text=True)


def test_titulo_que_nao_casa_aparece_com_o_motivo(s):
    """O que nao casa nao derruba o arquivo, e a tela diz por que."""
    titulo(s, protocolo="9999999999")
    html = mandar(s, xml()).get_data(as_text=True)
    assert "Não casaram com título nenhum desta casa" in html
    assert "nenhum titulo desta casa tem o protocolo" in html


def test_divergencia_nao_grava_e_a_tela_explica_que_parou_de_proposito(s):
    tid = titulo(s, nosso="YK0000000000999")
    html = mandar(s, xml()).get_data(as_text=True)
    assert "Divergem" in html
    assert "parou de propósito" in html
    con = _con(s)
    ficou = con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                        (tid,)).fetchone()[0]
    con.close()
    assert ficou is None


def test_mandar_o_mesmo_arquivo_duas_vezes_nao_estraga_nada(s):
    tid = titulo(s)
    mandar(s, xml())
    r = mandar(s, xml())
    assert r.status_code == 200
    con = _con(s)
    ficou = con.execute("SELECT chave_cenprot FROM pt_titulos WHERE id=?",
                        (tid,)).fetchone()[0]
    con.close()
    assert ficou == CHAVE


def test_a_tela_diz_que_nada_e_lavrado(s):
    """O escrevente precisa saber que este botao nao gasta selo nem folha."""
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Nada aqui é lavrado" in html


# ------------------------------------------- o arquivo de emolumentos, na tela


def protestado(s, *, valor=10160, chave=CHAVE):
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, valor_centavos,
                   saldo_centavos, situacao, chave_cenprot, origem, criado_em)
               VALUES ('DMI','T',?,?,'PROTESTADO',?,'CRA',?)""",
            (valor, valor, chave, AGORA))
    con.close()


def com_tabela(s):
    """Traz a tabela de emolumentos da producao para o banco do teste.

    Conexao PROPRIA com `uri=True`: o `_con` daqui abre pelo caminho simples,
    e o `ATTACH` de um banco em modo `ro` precisa da forma URI.
    """
    con = sqlite3.connect(str(s["banco"]), uri=True)
    con.row_factory = sqlite3.Row
    # `ATTACH` e `DETACH` NAO RODAM DENTRO DE TRANSACAO — ficam de fora do
    # `with`, que e quem abre uma.
    con.execute("ATTACH DATABASE 'file:C:/ProgramData/CartorioGestao"
                "/cartorio_gestao.sqlite3?mode=ro' AS prod")
    with con:
        for t in ("cx_faixas", "cx_vigencias", "cx_servicos", "cx_servico_valores"):
            con.execute(f"DELETE FROM {t}")
            con.execute(f"INSERT INTO {t} SELECT * FROM prod.{t}")
    con.execute("DETACH DATABASE prod")
    con.close()


tem_producao = pytest.mark.skipif(
    not Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3").exists(),
    reason="a tabela de emolumentos so existe na maquina da serventia")


@tem_producao
def test_a_tela_oferece_gerar_o_arquivo_de_emolumentos(s):
    com_tabela(s)
    protestado(s)
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Arquivo de emolumentos" in html
    assert 'action="/protesto/cenprot/emolumentos"' in html


@tem_producao
def test_sem_titulo_com_chave_a_tela_nao_oferece_o_botao(s):
    """Botao que gera arquivo vazio e pior que botao nenhum."""
    com_tabela(s)
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Nenhum título entra hoje" in html
    assert 'action="/protesto/cenprot/emolumentos"' not in html


@tem_producao
def test_gera_e_baixa_o_arquivo(s):
    com_tabela(s)
    protestado(s)
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/emolumentos",
                    data={"csrf_token": _token(tela)})
    assert r.status_code == 200
    assert "MA-2198765-01-E-" in r.headers["Content-Disposition"]
    corpo = r.get_data()
    assert corpo.startswith(b"nm_chave|"), "sem BOM, com o cabecalho medido"
    assert b"\r\n" in corpo
    linha = corpo.split(b"\r\n")[1].decode()
    assert linha.split("|") == [CHAVE, "96.54", "248.26", "2198765", "01",
                               linha.split("|")[5]]


@tem_producao
def test_arquivo_vazio_nao_desce_e_a_tela_diz_por_que(s):
    """Cabecalho sozinho subiria na Central dizendo «nenhum protesto tem
    preco», que e diferente de «nao ha protesto vivo»."""
    com_tabela(s)
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/emolumentos",
                    data={"csrf_token": _token(tela)}, follow_redirects=True)
    assert r.status_code == 200
    assert "Nenhum título entra no arquivo" in r.get_data(as_text=True)


@tem_producao
def test_o_preco_segue_a_TABELA_DO_DIA_e_nao_um_numero_fixo(s):
    """A TELA TEM DE ACOMPANHAR A VIRADA DA TABELA, sozinha.

    Ate o arquivo de edital chegar, a constante era um numero escrito e o
    modulo **recusava** gerar fora da vigencia em que ele fora medido. Agora
    ela se soma dos itens, e o arquivo sai com o preco daquela tabela.

    Numero fixo nao avisa que envelheceu: no dia da tabela nova, a Central
    receberia o preco do ano passado e o devedor viria ao balcao com ele.
    """
    com_tabela(s)
    protestado(s)
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    corrente = s["c"].post("/protesto/cenprot/emolumentos",
                           data={"csrf_token": _token(tela)}).get_data(as_text=True)
    assert "|96.54|248.26|" in corrente, "a tabela corrente"

    con = _con(s)
    with con:
        con.execute("UPDATE cx_vigencias SET vigente=0, inicio=NULL, fim=NULL")
        con.execute("UPDATE cx_vigencias SET vigente=1 WHERE codigo=10021")
    con.close()
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    anterior = s["c"].post("/protesto/cenprot/emolumentos",
                           data={"csrf_token": _token(tela)}).get_data(as_text=True)
    assert "|96.54|248.26|" not in anterior, "a tabela anterior e outra"
    assert "|91.75|236.03|" in anterior, "e e a dela, somada dos itens"


# ------------------------------------------------- o edital eletronico, na tela


def edital_publicado(s, *, dia, nome="DENIS PACHECO DOS TELES"):
    con = _con(s)
    with con:
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
                   valor_centavos, saldo_centavos, situacao, protocolo,
                   data_emissao, data_vencimento, cedente_nome, origem,
                   criado_em)
               VALUES ('DMI','31000005739','31000005739',24344,24344,
                       'INTIMADO','2608120002','2026-06-02','2026-06-10',
                       'EQUATORIAL',?,?)""", ("CRA", AGORA))
        tid = int(cur.lastrowid)
        con.execute(
            """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
                   documento_numero, bairro, cep, cidade, uf)
               VALUES (?,?,'CPF','00000002054','VAQUEJADA','65936000',
                       'CIDADE EXEMPLO','MA')""", (tid, nome))
        av = con.execute(
            """INSERT INTO pt_avisos(titulo_id, numero, ano, devedor_nome,
                   situacao, emitido_em, entregue, criado_em)
               VALUES (?,1,2026,?,'EDITAL',?,0,?)""", (tid, nome, dia, AGORA))
        con.execute(
            """INSERT INTO pt_editais(numero, ano, aviso_id, titulo_id,
                   publicado_em, teor, criado_em)
               VALUES (1,2026,?,?,?,'teor',?)""",
            (int(av.lastrowid), tid, dia, AGORA))
    con.close()
    return tid


def test_a_tela_oferece_gerar_o_edital_eletronico(s):
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "Edital eletrônico" in html
    assert 'action="/protesto/cenprot/edital"' in html


def test_a_tela_diz_que_o_ATO_vem_antes_do_arquivo(s):
    """Gerar o arquivo NAO publica edital — e quem le precisa saber disso."""
    html = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert "O ato vem antes do arquivo" in html
    assert "Lei 9.492/1997" in html


def test_gera_e_baixa_o_edital_do_dia(s):
    edital_publicado(s, dia="2026-08-14")
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/edital",
                    data={"csrf_token": _token(tela), "dia": "2026-08-14"})
    assert r.status_code == 200
    assert "Edital_Eletronico_2198765_14082026_001.xml" in \
        r.headers["Content-Disposition"]
    corpo = r.get_data(as_text=True)
    assert "<editais>" in corpo
    assert "000.000.020-54" in corpo, "o documento vai com mascara"
    assert "243,4400" in corpo and "243.4400" in corpo


def test_dia_sem_edital_publicado_nao_desce_arquivo(s):
    """Arquivo sem um edital diria a Central que a casa publicou NADA naquele
    dia, que e diferente de nao ter gerado o arquivo."""
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    r = s["c"].post("/protesto/cenprot/edital",
                    data={"csrf_token": _token(tela), "dia": "2026-08-14"},
                    follow_redirects=True)
    html = r.get_data(as_text=True)
    assert "Nenhum edital foi publicado em 2026-08-14" in html
    assert "Avisos e editais" in html


def test_o_dia_e_escolhido_e_nao_fixo_em_hoje(s):
    """Quem esqueceu ontem precisa poder mandar hoje."""
    edital_publicado(s, dia="2026-08-14")
    tela = s["c"].get("/protesto/cenprot").get_data(as_text=True)
    assert 'name="dia"' in tela
    r = s["c"].post("/protesto/cenprot/edital",
                    data={"csrf_token": _token(tela), "dia": "2026-08-13"},
                    follow_redirects=True)
    assert "Nenhum edital foi publicado em 2026-08-13" in r.get_data(as_text=True)
