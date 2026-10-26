# -*- coding: utf-8 -*-
"""O andamento dos títulos do RI no Acompanhamento de Títulos do ONR.

O QUE ESTES TESTES GUARDAM
    **A ordem dos campos é a do manual** — o WSDL do `acompanhamentotitulos
    .asmx` não está na casa; o teste relê o manual (cap. 3.2) e compara, e
    compara com o WSDL no dia em que ele for salvo.
    **Só entra na fila fato gravado, e uma vez só** (chave por evento).
    **O gancho nunca derruba o fato.**
    **Na hora de subir, o fato se confere de novo**: ato desfeito é anulado,
    ato sem selo espera — e segura os andamentos seguintes do mesmo título.
    **Nada vai à rede de verdade**: o ONR aqui é de mentira.
"""
from __future__ import annotations

import re
import sys
import xml.etree.ElementTree as ET
from contextlib import contextmanager
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import onr_acompanhamento as A                                     # noqa: E402
import onr_wsoficio as W                                           # noqa: E402
from bd_nativo import banco                                        # noqa: E402
from banco_de_teste import conexao_de_teste                        # noqa: E402

FONTES = RAIZ.parent.parent / "FONTES_EXTERNAS" / "onr_wsoficio"
MANUAL = FONTES / "especificacao_wsoficio_dev_4.43.txt"
WSDL = FONTES / "producao" / "acompanhamentotitulos.wsdl"
CHAVE = "0F1E2D3C-4B5A-6978-8796-A5B4C3D2E1F0"
CERT = {"SUBJECTCN": "FULANO DE TAL:00000004421", "ISSUERO": "ICP-Brasil",
        "PUBLICKEY": "3082010A0282010100AB", "SERIALNUMBER": "763222E368FD67A9",
        "VALIDUNTIL": "08/01/2028 16:10:00"}
METODOS_AT = ("ListTitulosAT", "GetTituloAT", "ListStatusAT", "GetStatusAT", "InsertTituloAT",
              "UpdateTituloAT", "DeleteTituloAT", "InsertStatusAT", "UpdateStatusAT")


# ------------------------------------------------------------------ o contrato

def _campos_do_manual() -> dict[str, tuple[str, ...]]:
    """Os campos de entrada de cada método, na ordem em que o manual os lista
    (cap. 3.2, do corpo e não do sumário: a segunda ocorrência do título)."""
    linhas = MANUAL.read_text(encoding="utf-8").splitlines()
    saida: dict[str, list[str]] = {}
    atual = None
    for linha in linhas:
        m = re.search(r"Envelope de Entrada - (\w+AT)\s*$", linha)
        if m and "...." not in linha:
            atual = m.group(1)
            saida[atual] = []
            continue
        if re.search(r"Envelope de Saída", linha) or re.match(r"^3\.3 ", linha):
            atual = None
            continue
        if atual:
            b = re.match(r"^●\s*(\w+)\s*[–-]", linha)
            if b:
                saida[atual].append(b.group(1))
    return {k: tuple(v) for k, v in saida.items()}


@pytest.mark.skipif(not MANUAL.is_file(), reason="o manual não está nesta árvore")
def test_a_ordem_dos_campos_e_a_do_manual():
    manual = _campos_do_manual()
    for metodo in METODOS_AT:
        assert manual[metodo] == W.CAMPOS[metodo], metodo


@pytest.mark.skipif(not WSDL.is_file(), reason="o WSDL do acompanhamento não foi salvo na casa")
def test_a_ordem_dos_campos_e_a_do_wsdl_quando_ele_existir():
    X = "{http://www.w3.org/2001/XMLSchema}"
    raiz = ET.parse(WSDL).getroot()
    tipos = {ct.get("name"): tuple(e.get("name") for e in ct.iter(X + "element"))
             for ct in raiz.iter(X + "complexType") if ct.get("name")}
    for metodo in METODOS_AT:
        assert tipos[f"{metodo}_WSReq"] == W.CAMPOS[metodo], metodo


def test_o_servico_e_os_metodos():
    assert W.SERVICOS["acompanhamento"] == "acompanhamentotitulos.asmx"
    assert W.SEM_WSDL_NA_CASA == {"acompanhamento"}
    assert all(W.SERVICO_DO_METODO[m] == "acompanhamento" for m in METODOS_AT)
    assert W.ESCREVEM_NO_ACOMPANHAMENTO == {m for m in METODOS_AT
                                            if re.match(r"^(Insert|Update|Delete)", m)}
    # os eventos da casa apontam para status que o manual tem, com o nome dele
    assert {W.TIPO_STATUS_AT[s] for s in A.EVENTOS.values()} == {
        "Título prenotado", "Nota de exigência", "Título com reingresso",
        "Prorrogado o prazo da prenotação", "Suscitação de dúvida", "Título registrado"}


def test_a_data_vai_com_os_dezenove_caracteres():
    assert A.data_do_onr("2026-10-26", "09:05:01") == "2026-10-26 09:05:01"
    assert A.data_do_onr("2026-10-26T14:30:00") == "2026-10-26 14:30:00"
    assert A.data_do_onr("2026-10-26", "14:30") == "2026-10-26 14:30:00"
    assert A.data_do_onr("2026-10-26") == "2026-10-26 00:00:00"
    assert len(A.data_do_onr("2026-10-26")) == 19
    with pytest.raises(A.AcompanhamentoError):
        A.data_do_onr("26/10/2026")


def test_telefone_so_quando_se_separa_sem_adivinhar():
    assert A.telefone_do_onr("(99) 98888-7777") == ("99", "988887777")
    assert A.telefone_do_onr("+55 99 3333-4444") == ("99", "33334444")
    assert A.telefone_do_onr("98888-7777") is None


# -------------------------------------------------------------- o banco de teste

TABELAS = """
CREATE TABLE ri_matriculas (id bigint PRIMARY KEY, numero TEXT);
CREATE TABLE ri_protocolos (id bigint PRIMARY KEY, numero INTEGER NOT NULL,
    livro TEXT, data_prenotacao TEXT NOT NULL, hora TEXT, apresentante TEXT,
    apresentante_documento TEXT, natureza_titulo TEXT, data_limite TEXT,
    situacao TEXT NOT NULL DEFAULT 'ABERTO', telefone TEXT, email TEXT,
    prazo_suspenso_desde TEXT, prazo_suspenso_motivo TEXT, ato_id INTEGER);
CREATE TABLE ri_notas_devolutivas (id bigint PRIMARY KEY, protocolo_id INTEGER,
    numero INTEGER, data_nota TEXT, exigencias TEXT, fundamentacao TEXT,
    prazo_ate TEXT, situacao TEXT, data_reingresso TEXT, emitida_em TEXT);
CREATE TABLE ri_atos (id bigint PRIMARY KEY, matricula_id INTEGER, tipo TEXT,
    numero INTEGER, data_ato TEXT, cancelado INTEGER NOT NULL DEFAULT 0, selo_texto TEXT);
"""
AGORA = "2026-10-26T10:00:00"


class _Db:
    """O `db` da casa para o domínio: connect e transaction na mesma conexão."""

    def __init__(self, con):
        self.con = con

    @contextmanager
    def connect(self):
        yield self.con

    @contextmanager
    def transaction(self):
        try:
            yield self.con
            self.con.commit()
        except BaseException:
            self.con.rollback()
            raise


@pytest.fixture()
def con():
    c = conexao_de_teste()
    bd = banco(c)
    bd.escrever(TABELAS)
    bd.escrever("INSERT INTO ri_matriculas VALUES (1, '4017')")
    bd.escrever("""INSERT INTO ri_protocolos (id, numero, livro, data_prenotacao, hora,
        apresentante, apresentante_documento, natureza_titulo, data_limite, email, telefone)
        VALUES (10, 11600, '1A', '2026-10-20', '09:15:00', 'MARIO DE TESTE',
                '00000004421', 'Escritura de compra e venda', '2026-11-17',
                'mario@exemplo.org', NULL)""")
    A.init_schema(c)
    c.commit()
    yield c
    c.close()


def _eventos(c):
    return banco(c).ler("SELECT * FROM onr_at_eventos ORDER BY id")


# ------------------------------------------------------------------ os ganchos

def test_a_prenotacao_se_anota_uma_vez_so(con):
    assert A.anotar_prenotacao(con, 10, agora=AGORA) is True
    assert A.anotar_prenotacao(con, 10, agora=AGORA) is False
    (ev,) = _eventos(con)
    assert (ev["evento"], ev["id_tipo_status"], ev["situacao"]) == ("PRENOTADO", 4, "PENDENTE")
    assert ev["data_status"] == "2026-10-20 09:15:00"
    assert "11600" in ev["descricao"] and "17/11/2026" in ev["descricao"]


def test_a_nota_de_exigencia_leva_o_texto_da_nota(con):
    banco(con).escrever("""INSERT INTO ri_notas_devolutivas VALUES (5, 10, 1, '2026-10-22',
        '["Apresentar a certidão de casamento.", "Recolher o ITBI."]', 'Lei 6.015, art. 198',
        '2026-11-17', 'ABERTA', NULL, '2026-10-22T16:00:00')""")
    assert A.anotar_nota_de_exigencia(con, 5, agora=AGORA)
    (ev,) = _eventos(con)
    assert ev["id_tipo_status"] == 7 and ev["data_status"] == "2026-10-22 16:00:00"
    assert "1. Apresentar a certidão de casamento." in ev["descricao"]
    assert "2. Recolher o ITBI." in ev["descricao"] and "art. 198" in ev["descricao"]


def test_reingresso_so_dentro_do_prazo(con):
    banco(con).escrever("""INSERT INTO ri_notas_devolutivas VALUES
        (5, 10, 1, '2026-10-22', '[]', NULL, NULL, 'FORA_DO_PRAZO', '2026-12-01', 't'),
        (6, 10, 2, '2026-10-23', '[]', NULL, NULL, 'CUMPRIDA', '2026-10-25', 't')""")
    assert A.anotar_reingresso(con, 5, agora=AGORA) is False
    assert A.anotar_reingresso(con, 6, agora=AGORA) is True
    (ev,) = _eventos(con)
    assert ev["id_tipo_status"] == 1 and ev["data_status"] == "2026-10-25 00:00:00"


def test_prorrogacao_so_com_dia_a_mais_e_duvida_so_com_o_motivo(con):
    assert A.anotar_prorrogacao(con, 10, de="2026-11-17", para="2026-11-17", dias=0,
                                agora=AGORA) is False
    assert A.anotar_prorrogacao(con, 10, de="2026-11-17", para="2026-11-24", dias=5,
                                agora=AGORA) is True
    assert A.anotar_duvida(con, 10, agora=AGORA) is False          # sem suspensão
    banco(con).escrever("""UPDATE ri_protocolos SET prazo_suspenso_desde='2026-10-26',
                           prazo_suspenso_motivo='RETIFICACAO' WHERE id=10""")
    assert A.anotar_duvida(con, 10, agora=AGORA) is False          # outro motivo
    banco(con).escrever("UPDATE ri_protocolos SET prazo_suspenso_motivo='DUVIDA' WHERE id=10")
    assert A.anotar_duvida(con, 10, agora=AGORA) is True
    assert [e["id_tipo_status"] for e in _eventos(con)] == [15, 9]


def test_registro_so_de_prenotacao_aberta(con):
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 0, NULL)")
    banco(con).escrever("UPDATE ri_protocolos SET situacao='ENCERRADO' WHERE id=10")
    assert A.anotar_registro(con, 10, ato_id=77, agora=AGORA) is False
    banco(con).escrever("UPDATE ri_protocolos SET situacao='ABERTO' WHERE id=10")
    assert A.anotar_registro(con, 10, ato_id=77, agora=AGORA) is True
    (ev,) = _eventos(con)
    assert "R-1 na matrícula 4017" in ev["descricao"]
    assert ev["data_status"] == "2026-10-26 10:00:00"


def test_o_gancho_nunca_derruba_o_fato(con, monkeypatch):
    def quebra(*a, **k):
        banco(a[0]).escrever("SELECT * FROM tabela_que_nao_existe")
    monkeypatch.setattr(A, "anotar_na_fila", quebra)
    assert A.anotar_prenotacao(con, 10, agora=AGORA) is False
    # a transação de fora continua viva: o fato segue gravável
    banco(con).escrever("UPDATE ri_protocolos SET hora='09:16:00' WHERE id=10")
    con.commit()
    assert banco(con).valor("SELECT hora FROM ri_protocolos WHERE id=10") == "09:16:00"


# ------------------------------------------------------------------ o envio

def _soap(metodo: str, corpo: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap='
            '"http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<{metodo}Response xmlns="{W.NS}"><{metodo}Result>{corpo}</{metodo}Result>'
            f'</{metodo}Response></soap:Body></soap:Envelope>')


class ONRDeMentira:
    def __init__(self, *, titulo_ja_existe=False, cair=False):
        self.chamadas, self.titulo_ja_existe, self.cair = [], titulo_ja_existe, cair
        self.status = 500

    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        xml = corpo.decode("utf-8")
        self.chamadas.append((url, metodo, xml))
        if metodo == "LoginUsuarioCertificado":
            toks = "".join(f"<string>TK{i}</string>" for i in range(5))
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><Tokens>" + toks + "</Tokens>")
        if self.cair:
            return 503, "Service Unavailable"
        self.status += 1
        if metodo == "InsertTituloAT":
            if self.titulo_ja_existe:
                return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>501</CODIGOERRO>"
                                          "<ERRODESCRICAO>O protocolo informado já está cadastrado"
                                          "</ERRODESCRICAO><IDTitulo>4242</IDTitulo>")
            return 200, _soap(metodo, "<RETORNO>true</RETORNO><IDTitulo>900</IDTitulo>"
                                      f"<IDStatus>{self.status}</IDStatus>")
        if metodo == "InsertStatusAT":
            return 200, _soap(metodo, f"<RETORNO>true</RETORNO><IDStatus>{self.status}</IDStatus>")
        return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>10</CODIGOERRO>")

    def de(self, metodo):
        return [x for _, m, x in self.chamadas if m == metodo]


@pytest.fixture()
def pasta(tmp_path):
    W.configurar(pasta=tmp_path, ambiente=W.HOMOLOGACAO, id_parceiro="2869", chave=CHAVE,
                 cpf="000.000.044-21", email="oficial@exemplo.org")
    return tmp_path


def _enviar(con, pasta, onr):
    return A.enviar_pendentes(
        _Db(con), lambda: W.Sessao(ambiente=W.HOMOLOGACAO, pasta=pasta, transporte=onr,
                                   certificado=CERT),
        amb=W.HOMOLOGACAO, quem="beatriz", agora=lambda: AGORA)


def test_o_primeiro_cadastra_o_titulo_e_o_seguinte_vai_como_status(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("""INSERT INTO ri_notas_devolutivas VALUES (5, 10, 1, '2026-10-22',
        '["Recolher o ITBI."]', NULL, NULL, 'ABERTA', NULL, '2026-10-22T16:00:00')""")
    A.anotar_nota_de_exigencia(con, 5, agora=AGORA)
    con.commit()
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert (feito["enviados"], feito["titulos_novos"], feito["parou"]) == (2, 1, "")
    (titulo,) = onr.de("InsertTituloAT")
    assert onr.chamadas[1][0] == "https://hml3-wsoficio.onr.org.br/acompanhamentotitulos.asmx"
    assert "<Protocolo>11600</Protocolo>" in titulo
    assert "<ModoNotificacaoStatus>E</ModoNotificacaoStatus>" in titulo
    assert "<ApresentanteEmail>mario@exemplo.org</ApresentanteEmail>" in titulo
    assert "<DataProtocolo>2026-10-20 09:15:00</DataProtocolo>" in titulo
    assert "<DataPrevisaoEntrega>2026-11-17 23:59:59</DataPrevisaoEntrega>" in titulo
    assert "<IDTipoStatus>4</IDTipoStatus>" in titulo and "<TipoSolicitacao>1<" in titulo
    assert "ApresentanteDDDTelefone" not in titulo
    # a ordem que vai é a do contrato
    nomes = re.findall(r"<(\w+)>", titulo.split("<oRequest>")[1].split("</oRequest>")[0])
    assert nomes == [c for c in W.CAMPOS["InsertTituloAT"] if c in nomes]
    (status,) = onr.de("InsertStatusAT")
    assert "<IDTitulo>900</IDTitulo>" in status and "<IDTipoStatus>7</IDTipoStatus>" in status
    assert all(CHAVE not in x for _, _, x in onr.chamadas)
    linhas = _eventos(con)
    assert [e["situacao"] for e in linhas] == ["ENVIADO", "ENVIADO"]
    assert all(e["ambiente"] == W.HOMOLOGACAO and e["id_status_onr"] for e in linhas)
    assert banco(con).valor("SELECT id_titulo_onr FROM onr_at_titulos") == 900
    # e o que subiu não sobe de novo
    assert _enviar(con, pasta, ONRDeMentira())["enviados"] == 0


def test_titulo_ja_cadastrado_no_onr_e_aproveitado(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    onr = ONRDeMentira(titulo_ja_existe=True)
    feito = _enviar(con, pasta, onr)
    assert feito["enviados"] == 1
    assert banco(con).um("SELECT id_titulo_onr, como FROM onr_at_titulos") == {
        "id_titulo_onr": 4242, "como": "JA_EXISTIA"}
    (status,) = onr.de("InsertStatusAT")
    assert "<IDTitulo>4242</IDTitulo>" in status and "<IDTipoStatus>4</IDTipoStatus>" in status


def test_registro_sem_selo_espera_e_segura_o_titulo(con, pasta):
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 0, NULL)")
    A.anotar_registro(con, 10, ato_id=77, agora=AGORA)
    A.anotar_prorrogacao(con, 10, de="2026-11-17", para="2026-11-24", dias=5,
                         agora="2026-10-27T08:00:00")
    con.commit()
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert (feito["enviados"], feito["esperando"]) == (0, 1)
    assert onr.chamadas == []                         # nem o login: nada a mandar
    ev = _eventos(con)
    assert [e["situacao"] for e in ev] == ["PENDENTE", "PENDENTE"]
    assert "selo" in ev[0]["ultimo_erro"]
    banco(con).escrever("UPDATE ri_atos SET selo_texto='SELO-TESTE' WHERE id=77")
    con.commit()
    assert _enviar(con, pasta, ONRDeMentira())["enviados"] == 2


def test_ato_desfeito_nao_sobe(con, pasta):
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 0, 'S')")
    A.anotar_registro(con, 10, ato_id=77, agora=AGORA)
    banco(con).escrever("DELETE FROM ri_atos WHERE id=77")
    con.commit()
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert (feito["anulados"], feito["enviados"]) == (1, 0) and onr.chamadas == []
    (ev,) = _eventos(con)
    assert ev["situacao"] == "ANULADO" and "desfeito" in ev["motivo_fim"]


def test_sem_meio_de_avisar_o_apresentante_espera_com_a_frase(con, pasta):
    banco(con).escrever("UPDATE ri_protocolos SET email=NULL, telefone='3333-4444' WHERE id=10")
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["esperando"] == 1 and onr.chamadas == []
    assert "e-mail nem telefone" in _eventos(con)[0]["ultimo_erro"]
    banco(con).escrever("UPDATE ri_protocolos SET telefone='(99) 98888-7777' WHERE id=10")
    con.commit()
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["enviados"] == 1
    (titulo,) = onr.de("InsertTituloAT")
    assert "<ModoNotificacaoStatus>S</ModoNotificacaoStatus>" in titulo
    assert "<ApresentanteDDDTelefone>99</ApresentanteDDDTelefone>" in titulo


def test_falha_de_transporte_para_a_rodada(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    feito = _enviar(con, pasta, ONRDeMentira(cair=True))
    assert feito["parou"] and feito["enviados"] == 0
    (ev,) = _eventos(con)
    assert ev["situacao"] == "PENDENTE" and ev["tentativas"] == 1


def test_descartar_exige_motivo_e_so_o_pendente(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    (ev,) = _eventos(con)
    with pytest.raises(A.AcompanhamentoError, match="dez letras"):
        A.descartar(con, ev["id"], motivo="não", quem="beatriz", agora=AGORA)
    A.descartar(con, ev["id"], motivo="prenotação lançada por engano", quem="beatriz",
                agora=AGORA)
    assert _eventos(con)[0]["situacao"] == "DESCARTADO"
    with pytest.raises(A.AcompanhamentoError, match="só se descarta"):
        A.descartar(con, ev["id"], motivo="de novo, por engano", quem="beatriz", agora=AGORA)


def test_a_ficha_mostra_o_enviado_cujo_fato_sumiu(con, pasta):
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 0, 'S')")
    A.anotar_registro(con, 10, ato_id=77, agora=AGORA)
    con.commit()
    _enviar(con, pasta, ONRDeMentira())
    banco(con).escrever("DELETE FROM ri_atos WHERE id=77")
    (ev,) = A.da_prenotacao(con, 10)["eventos"]
    assert ev["situacao"] == "ENVIADO" and "desfeito" in ev["fato_sumiu"]
    assert ev["rotulo"] == "Título registrado"


def test_o_envio_nasce_desligado_e_o_ambiente_e_o_das_certidoes():
    vazio = {}
    assert A.ligado(lambda k, d=None: vazio.get(k, d)) is False
    assert A.ligado(lambda k, d=None: {"onr_acompanhamento_ligado": "1"}.get(k, d)) is True
    assert A.ambiente(lambda k, d=None: {"onr_certidoes_ambiente": "HOMOLOGACAO"}.get(k, d)) \
        == W.HOMOLOGACAO
    assert A.CHAVE_AMBIENTE == "onr_certidoes_ambiente"


# ------------------------------------------------------------------ as telas

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def test_telas_do_balcao_ao_onr(cg_casa_logada, monkeypatch):
    """De ponta a ponta pelas rotas: a prenotação e a nota anotam a fila, o envio
    nasce desligado, ligado manda (ao ONR de mentira) e a ficha mostra."""
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    html = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    c.post("/registro-imoveis/protocolo", data={
        "apresentante": "MARIO DE TESTE", "natureza_titulo": "COMPRA E VENDA",
        "objeto": "escritura", "livro_destino": "2", "telefone": "(99) 90000-0000",
        "csrf_token": _token(html)}, follow_redirects=True)
    with db.connect() as cx:
        pid = banco(cx).valor("SELECT MAX(id) FROM ri_protocolos")
    html = c.get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
    c.post(f"/registro-imoveis/protocolo/{pid}/nota", data={
        "exigencias": "Recolher o ITBI.", "csrf_token": _token(html)})
    with db.connect() as cx:
        evs = banco(cx).ler("SELECT evento, situacao FROM onr_at_eventos ORDER BY id")
    assert [(e["evento"], e["situacao"]) for e in evs] == [
        ("PRENOTADO", "PENDENTE"), ("EXIGENCIA", "PENDENTE")]

    tela = c.get("/ri/onr/acompanhamento").get_data(as_text=True)
    assert "Título prenotado" in tela and "Ligar o envio" in tela and "Recolher o ITBI." in tela
    tok = _token(tela)
    r = c.post("/ri/onr/acompanhamento/enviar", data={"csrf_token": tok},
               follow_redirects=True).get_data(as_text=True)
    assert "está desligado" in r

    class SessaoFalsa:
        def __init__(self, **_):
            self.n = 0

        def cadastrar_titulo_no_acompanhamento(self, campos):
            assert campos["ModoNotificacaoStatus"] == "S" and campos["IDTipoStatus"] == 4
            return {"RETORNO": True, "IDTitulo": "900", "IDStatus": "1"}

        def cadastrar_status_no_acompanhamento(self, id_titulo, **k):
            assert id_titulo == 900 and k["tipo_status"] == 7
            return {"RETORNO": True, "IDStatus": "2"}

    import onr_acompanhamento_web as AW
    monkeypatch.setattr(AW.WS, "Sessao", SessaoFalsa)
    c.post("/ri/onr/acompanhamento/ligar", data={"csrf_token": tok, "ligar": "1"})
    r = c.post("/ri/onr/acompanhamento/enviar", data={"csrf_token": tok},
               follow_redirects=True).get_data(as_text=True)
    assert "2 andamento(s) enviado(s)" in r
    ficha = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert "Acompanhamento no ONR" in ficha and "Título nº 900 no ONR" in ficha


def test_o_robo_nao_envia_nao_liga_e_nao_descarta(cg_casa, monkeypatch):
    """Revisão de segurança de 26/10/2026 (PR #21): as quatro rotas do
    acompanhamento estão vedadas ao robô pelo nome. A conta de robô (que só
    pode ser USER ou AUDITOR) recebe 403 até na tela de leitura — que o papel
    USER abriria —, e nenhum POST chega ao ONR nem muda o interruptor."""
    import selo_robo as SR
    for rota in ("onr_acompanhamento", "onr_acompanhamento_enviar",
                 "onr_acompanhamento_ligar", "onr_acompanhamento_descartar"):
        assert SR.rota_vedada_ao_robo(rota), rota
    from conftest import cg_login
    db = cg_casa["db"]
    db.create_user("robo_onr", "Robo de Exemplo ONR", "Senha#12345", "USER", eh_robo=1)
    c = cg_casa["c"]
    cg_login(c, "robo_onr", "Senha#12345")

    class SessaoQueNaoPodeSerUsada:
        def __init__(self, **_):
            raise AssertionError("o robô chegou ao ONR")

    import onr_acompanhamento_web as AW
    monkeypatch.setattr(AW.WS, "Sessao", SessaoQueNaoPodeSerUsada)
    assert c.get("/ri/onr/acompanhamento").status_code == 403
    tok = _token(c.get("/").get_data(as_text=True))
    assert c.post("/ri/onr/acompanhamento/ligar",
                  data={"csrf_token": tok, "ligar": "1"}).status_code == 403
    assert c.post("/ri/onr/acompanhamento/enviar",
                  data={"csrf_token": tok}).status_code == 403
    assert c.post("/ri/onr/acompanhamento/1/descartar",
                  data={"csrf_token": tok, "motivo": "teste do robô"}).status_code == 403
    assert not A.ligado(db.get_setting)
