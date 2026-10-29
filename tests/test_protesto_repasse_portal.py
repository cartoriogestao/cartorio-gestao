"""
Testes do robô que emite o boleto de repasse no portal da CRA (29/10/2026).

Ordem do oficial: «as guias, configure para a automação emitir. Posso colocar
as senhas no cofre pra entrar.»

NADA AQUI FALA COM O PORTAL. As páginas são sintéticas, no formato que o
portal tem: o formulário de entrada foi lido numa visita anônima em
29/10/2026 (campos `login`, `senha`, `NTISPOSTBACK`, botão `confirmar`, sem
CAPTCHA); a página dos boletos segue o que o coordenador leu, só lendo (as
três listas e o botão «GERAR BOLETO»). O PDF é gerado aqui, com uma linha
digitável montada pela regra FEBRABAN.

O QUE ELES CONFEREM
      - entrar pelo formulário, sem a senha ir ao rastro nem ao log;
      - CAPTCHA no login PARA o robô, sem enviar nada — e vira «emita à mão»;
      - as três listas se leem pelo título de cada uma;
      - com «pode agir»: gera, confirma, baixa o PDF, confere a linha
        digitável e a soma do retorno, registra a guia com o nosso número e o
        PDF anexado, e lança a despesa AGUARDANDO a autorização do oficial;
      - sem «pode agir»: entra, lê, e não clica nem grava;
      - valor que não bate é ERRO, e a guia não se registra;
      - gerou e não confirmou: a marca fica, e a rodada seguinte NÃO gera de
        novo;
      - o boleto que o portal mostra «PAGO» concilia a guia;
      - cofre trancado e sandbox são AVISO, sem entrar no portal;
      - o robô nunca paga, e está no catálogo da automação.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.parse
from datetime import date, datetime
from pathlib import Path
from types import SimpleNamespace

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cra_portal as CRA                         # noqa: E402
import protesto as PT                            # noqa: E402
import protesto_repasse as REP                   # noqa: E402
import protesto_repasse_portal as PRP            # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402

BASE = CRA.URL_DO_PORTAL
USUARIO = "robo.teste"
SENHA_DE_TESTE = "senha-de-teste-7781"
NOSSO = "000000000123"
CONTA = "Banco de Teste"
CPF = "00000000191"                 # da lista de fictícios
CNPJ = "00000001000055"             # da lista de fictícios
SV = {"unit_name": "SERVENTIA DE TESTE", "serventia_titular": "TABELIÃO DE TESTE",
      "serventia_titulo": "Tabelião", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
EXTENSO = "vinte e um dias do mês de outubro do ano de dois mil e vinte e seis"
VENCIMENTO = date(2026, 11, 3)


# ------------------------------------------------------------ a linha digitável


def _mod10(numero: str) -> int:
    soma, peso = 0, 2
    for d in reversed(numero):
        p = int(d) * peso
        soma += p // 10 + p % 10
        peso = 1 if peso == 2 else 2
    return (10 - soma % 10) % 10


def _mod11(numero: str) -> int:
    soma, peso = 0, 2
    for d in reversed(numero):
        soma += int(d) * peso
        peso = 2 if peso == 9 else peso + 1
    dv = 11 - soma % 11
    return 1 if dv in (0, 10, 11) else dv


def linha_digitavel(valor_centavos: int, vencimento: date = VENCIMENTO) -> str:
    """A linha FORMATADA, como o boleto imprime."""
    fator = (vencimento - date(2025, 2, 22)).days + 1000
    livre = "0000001234567890123456789"
    meio = f"{fator:04d}{valor_centavos:010d}{livre}"
    dv = _mod11("0019" + meio)
    barras = "0019" + str(dv) + meio
    c1 = barras[0:4] + barras[19:24]
    c1 += str(_mod10(c1))
    c2 = barras[24:34]
    c2 += str(_mod10(c2))
    c3 = barras[34:44]
    c3 += str(_mod10(c3))
    return (f"{c1[:5]}.{c1[5:]} {c2[:5]}.{c2[5:]} {c3[:5]}.{c3[5:]} "
            f"{barras[4]} {barras[5:19]}")


def pdf_do_boleto(*, valor: str = "200,00", centavos: int = 20000,
                  linha: str | None = None) -> bytes:
    pymupdf = pytest.importorskip("pymupdf")
    doc = pymupdf.open()
    pagina = doc.new_page()
    y = 72
    for texto in ("Beneficiario: INSTITUTO DE TESTE", f"Nosso Numero {NOSSO}",
                  f"Vencimento {VENCIMENTO.strftime('%d/%m/%Y')}",
                  f"Valor do Documento {valor}", linha or linha_digitavel(centavos)):
        pagina.insert_text((72, y), texto)
        y += 20
    return doc.tobytes()


# ------------------------------------------------------------ o portal falso

LOGIN = """<html><body>
<form method="post" enctype="multipart/form-data" accept-charset="utf-8">
<input type="hidden" name="NTISPOSTBACK" value="1" />
<input type="hidden" name="NTSUPERIORREF" id="NTSUPERIORREF" value="" />
<input id="login" name="login" placeholder="Usuário" type="text">
<input id="senha" name="senha" placeholder="Senha" type="password">
{desafio}
<button type="submit" id="confirmar" name="confirmar">Enviar</button>
</form><a href="https://exemplo.invalid/ajuda">Ajuda</a></body></html>"""

INICIO = """<html><body><ul class="menu">
<li><a href="admin.php?acao=UmV0b3Jubw==">Retorno</a>
<ul><li><a href="admin.php?acao=Qm9sZXRvcw==">Boletos de repasse</a></li></ul></li>
<li><a href="admin.php?acao=U2Fpcg==">Sair</a></li></ul></body></html>"""


def _linha_do_boleto(b: dict) -> str:
    return (f"<tr><td>{CONTA}</td><td>29/10/2026 09:45</td><td>26/10/2026</td>"
            f"<td>{b['nosso']}</td><td>{b['repasse']}</td><td>0,00</td>"
            f"<td>{b['valor']}</td><td>{b['situacao']}</td>"
            f"<td><a href=\"admin.php?acao=cGRm{b['nosso']}\" title=\"Imprimir boleto\">"
            f"<i class=\"fa fa-print\"></i></a></td></tr>")


def pagina_dos_boletos(boletos: list[dict], pendentes: list[dict]) -> str:
    cab = ("<tr><th>Conta</th><th>Geração</th><th>Retorno</th><th>Nosso número</th>"
           "<th>Repasse</th><th>Taxa</th><th>Valor</th><th>Situação</th><th></th></tr>")
    pend = "".join(f"<tr><td>{CONTA}</td><td>26/10/2026</td><td>{p['repasse']}</td>"
                   f"<td>PENDENTE</td></tr>" for p in pendentes)
    return f"""<html><body><form method="post" enctype="multipart/form-data">
<input type="hidden" name="NTISPOSTBACK" value="1">
<label>Conta <select name="conta"><option value="7">{CONTA}</option></select></label>
<div class="portlet"><div class="caption">Boletos</div>
<table><thead>{cab}</thead><tbody>{"".join(_linha_do_boleto(b) for b in boletos)}</tbody></table></div>
<div class="portlet"><div class="caption">Boletos pendentes de geração</div>
<table><thead><tr><th>Conta</th><th>Movimento</th><th>Repasse</th><th>Situação</th></tr></thead>
<tbody>{pend}</tbody></table>
<button type="submit" name="gerar_boleto" value="1">GERAR BOLETO</button></div>
<div class="portlet"><div class="caption">Boletos excluídos</div>
<table><thead>{cab}</thead><tbody></tbody></table></div>
</form></body></html>"""


class _Resposta:
    def __init__(self, url: str, corpo: bytes, tipo: str = "text/html; charset=UTF-8",
                 status: int = 200):
        self.url, self.corpo, self.status = url, corpo, status
        self.headers = {"Content-Type": tipo}

    def read(self, _n: int = -1) -> bytes:
        return self.corpo

    def geturl(self) -> str:
        return self.url

    def getcode(self) -> int:
        return self.status


class PortalFalso:
    """O portal, em memória. Guarda cada pedido; nenhum sai para a rede."""

    def __init__(self, *, captcha: bool = False, gera: bool = True,
                 repasse: str = "200,00", pdf: bytes = b""):
        self.captcha, self.gera, self.pdf = captcha, gera, pdf
        self.logado = False
        self.pedidos: list[tuple[str, str, bytes]] = []
        self.boletos: list[dict] = []
        self.pendentes: list[dict] = [{"repasse": repasse}]

    def html(self, texto: str, url: str = BASE) -> _Resposta:
        return _Resposta(url, texto.encode("utf-8"))

    def __call__(self, pedido, timeout=None):
        url, metodo = pedido.full_url, pedido.get_method()
        corpo = pedido.data or b""
        self.pedidos.append((metodo, url, corpo))
        consulta = urllib.parse.urlsplit(url).query
        if metodo == "POST" and b'name="senha"' in corpo:
            self.logado = SENHA_DE_TESTE.encode() in corpo
            return self.html(INICIO if self.logado else LOGIN.format(desafio=""))
        if not self.logado:
            desafio = '<div class="g-recaptcha" data-sitekey="x"></div>' if self.captcha else ""
            return self.html(LOGIN.format(desafio=desafio))
        if metodo == "POST" and b'name="gerar_boleto"' in corpo:
            if self.gera and self.pendentes:
                p = self.pendentes.pop(0)
                self.boletos.append({"nosso": NOSSO, "repasse": p["repasse"],
                                     "valor": p["repasse"],
                                     "situacao": "AGUARDANDO PAGAMENTO"})
            return self.html(pagina_dos_boletos(self.boletos, self.pendentes), url)
        if "acao=Qm9sZXRvcw" in consulta:
            return self.html(pagina_dos_boletos(self.boletos, self.pendentes), url)
        if "acao=cGRm" in consulta:
            return _Resposta(url, self.pdf, "application/pdf")
        return self.html(INICIO, url)

    def posts_de_geracao(self) -> int:
        return sum(1 for m, _, c in self.pedidos
                   if m == "POST" and b'name="gerar_boleto"' in c)


# ------------------------------------------------------------ o portal, sozinho


def test_entrar_pelo_formulario_sem_a_senha_no_rastro():
    portal = PortalFalso()
    nav = CRA.Navegador(abrir=portal)
    pagina = CRA.entrar(nav, USUARIO, SENHA_DE_TESTE)
    assert CRA.esta_dentro(pagina)
    [(_, _, corpo)] = [p for p in portal.pedidos if p[0] == "POST"]
    for campo in (b'name="NTISPOSTBACK"', b'name="confirmar"', b'name="login"'):
        assert campo in corpo
    assert SENHA_DE_TESTE not in json.dumps(nav.passos)


def test_captcha_no_login_para_sem_enviar_nada():
    portal = PortalFalso(captcha=True)
    with pytest.raises(CRA.DesafioNoLogin, match="não contorna"):
        CRA.entrar(CRA.Navegador(abrir=portal), USUARIO, SENHA_DE_TESTE)
    assert [m for m, _, _ in portal.pedidos] == ["GET"]


def test_senha_errada_e_recusa_sem_tentar_de_novo():
    portal = PortalFalso()
    with pytest.raises(CRA.LoginRecusado):
        CRA.entrar(CRA.Navegador(abrir=portal), USUARIO, "outra-senha")
    assert sum(1 for m, _, _ in portal.pedidos if m == "POST") == 1


def test_o_portal_so_se_abre_por_https():
    with pytest.raises(CRA.PortalError, match="https"):
        CRA.Navegador(abrir=PortalFalso()).abrir("http://crama.crabr.com.br/x")


def test_as_tres_listas_se_leem_pelo_titulo():
    pagina = CRA.Pagina(BASE, 200, "text/html", pagina_dos_boletos(
        [{"nosso": NOSSO, "repasse": "1.632,93", "valor": "1.632,93",
          "situacao": "AGUARDANDO PAGAMENTO"}], [{"repasse": "10,00"}]).encode())
    q = CRA.ler_boletos(pagina)
    [b] = q[CRA.BOLETOS]
    assert (b["nosso_numero"], b["repasse_centavos"], b["retorno_em"]) == (
        NOSSO, 163293, "2026-10-26")
    assert CRA.em_aberto(b) and not CRA.pago(b)
    assert CRA.pago({"situacao_norm": "pago"})
    assert [p["repasse_centavos"] for p in q[CRA.PENDENTES]] == [1000]
    assert q[CRA.EXCLUIDOS] == []
    assert CRA.link_do_pdf(b).endswith("acao=cGRm" + NOSSO)


def test_dois_botoes_sem_a_conta_na_linha_o_robo_nao_escolhe():
    html = pagina_dos_boletos([], [{"repasse": "1,00"}]).replace(
        "</form>", '<button type="submit" name="outro">GERAR BOLETO</button></form>')
    html = html.replace(f"<option value=\"7\">{CONTA}</option>", "")
    pagina = CRA.Pagina(BASE, 200, "text/html", html.encode())
    with pytest.raises(CRA.PaginaDesconhecida, match="não escolhe"):
        CRA.gerar_boleto(CRA.Navegador(abrir=PortalFalso()), pagina, conta="Outra conta")


def test_o_pdf_se_le_pela_linha_digitavel_e_a_errada_e_recusada():
    lido = CRA.ler_boleto_pdf(pdf_do_boleto())
    assert lido["valor_centavos"] == 20000
    assert VENCIMENTO.isoformat() in lido["vencimentos"]
    assert lido["nosso_numero"].endswith("123")
    errada = linha_digitavel(20000)
    errada = errada[:2] + ("1" if errada[2] != "1" else "2") + errada[3:]
    with pytest.raises(CRA.PortalError, match="não confere"):
        CRA.ler_boleto_pdf(pdf_do_boleto(linha=errada))


# ------------------------------------------------------------ o robô, com o banco


def _pago_da_cra(db, *, saldo: str = "200.00", chave: str = "CRAB:1") -> dict:
    d = {"especie": "DMI", "numero_titulo": chave.replace(":", "/"),
         "data_emissao": "2026-07-21", "data_vencimento": "2026-09-05",
         "valor": saldo, "saldo": saldo, "praca_protesto": "CIDADE EXEMPLO",
         "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
         "apresentante_codigo": "999", "apresentante_nome": "BANCO FICTICIO",
         "cedente": {"nome": "CREDOR FICTICIO", "documento": CNPJ,
                     "cidade": "Cidade Exemplo", "uf": "MA"},
         "devedores": [{"nome": "DEVEDOR FICTICIO", "CPF": CPF,
                        "enderecos": [{"endereco": "Rua X", "bairro": "Centro",
                                       "cidade": "Cidade Exemplo", "uf": "MA"}]}]}
    quando = "2026-10-21T10:00:00"
    with db.transaction() as con:
        tid = PT.cadastrar_titulo(con, d, origem="CRA", origem_chave=chave, agora=quando)
        PT.lancar_apontamento(con, tid, sv=SV, agora=quando, data_extenso=EXTENSO)
        # A forma é incidental aqui, e não pode ser PIX: desde o PR #119 o PIX
        # só é pagamento com o crédito conferido (`pix_id`). Trocado na
        # integração de 29/10/2026.
        ato = PT.lancar_pagamento(con, tid, sv=SV, agora=quando, data_extenso=EXTENSO,
                                  forma_pagamento="TRANSFERENCIA")["ato_id"]
        rid = nativo(con).escrever(
            """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia, nome_arquivo,
                   conteudo, gerado_em, cra_enviado_em)
               VALUES ('SDTBFORTP', '999', '2026-10-23', 'RTESTE.TXT',
                       'arquivo de teste', '2026-10-23T13:40:00',
                       '2026-10-23T13:50:00') RETURNING id""")[0]["id"]
        nativo(con).escrever("UPDATE pt_atos SET retorno_id=%s WHERE id=%s", (rid, ato))
    return {"titulo_id": tid, "ato_id": ato}


def _contexto(db, portal, tmp_path, *, pode_agir: bool = True, estado=None):
    return SimpleNamespace(
        db=db, agora=datetime(2026, 10, 29, 14, 30), pasta_dados=tmp_path,
        processo={"codigo": PRP.CODIGO, "pode_agir": pode_agir, "estado": estado or {},
                  "alterado_por": "mario"},
        navegador=CRA.Navegador(abrir=portal), setting=lambda chave, padrao="": "")


@pytest.fixture()
def robo(cg_casa, monkeypatch):
    monkeypatch.setattr(PRP, "_credencial",
                        lambda contexto: {"usuario": USUARIO, "senha": SENHA_DE_TESTE})
    import centrais_trava_sandbox as TRAVA
    monkeypatch.setattr(TRAVA, "e_sandbox", lambda: False)
    return cg_casa["db"]


def _guias(db):
    with db.connect() as con:
        return nativo(con).ler("SELECT * FROM pt_repasse_guias ORDER BY id")


def test_o_robo_gera_registra_a_guia_e_lanca_a_despesa_sem_pagar(robo, tmp_path):
    p = _pago_da_cra(robo)
    portal = PortalFalso(pdf=pdf_do_boleto())
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    assert r["situacao"] == "AVISO", r["relato"]
    assert portal.posts_de_geracao() == 1
    assert [a["acao"] for a in r["acoes"]] == ["gerou o boleto no portal",
                                               "registrou a guia do boleto"]
    [g] = _guias(robo)
    assert (g["situacao"], g["identificador"]) == ("REGISTRADA", NOSSO)
    with robo.connect() as con:
        [anexo] = nativo(con).ler("SELECT * FROM attachments WHERE entity_type=%s "
                                  "AND entity_id=%s", ("pt_repasse_guias", g["id"]))
        [despesa] = nativo(con).ler("SELECT * FROM dp_despesas WHERE origem=%s",
                                    (PRP.ORIGEM_DA_DESPESA,))
        linha = REP.pendencias_do_repasse(con, hoje="2026-10-29")
    assert Path(anexo["stored_path"]).name == anexo["sha256"] + ".pdf"
    assert despesa["situacao"] == "AGUARDANDO_AUTORIZACAO"
    assert despesa["categoria"] == PRP.CATEGORIA_DA_DESPESA
    assert int(despesa["valor"]) == 20000
    assert [x["etapa"] for x in linha if x["ato_id"] == p["ato_id"]] == [
        REP.GUIA_REGISTRADA]
    assert "esperando o pagamento" in r["relato"]


def test_sem_pode_agir_o_robo_entra_le_e_nao_clica_nem_grava(robo, tmp_path):
    _pago_da_cra(robo)
    portal = PortalFalso(pdf=pdf_do_boleto())
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path, pode_agir=False))
    assert r["situacao"] == "AVISO" and r["acoes"] == []
    assert portal.posts_de_geracao() == 0
    assert [a["tipo"] for a in r["achados"]] == ["PENDENTE_DE_GERACAO"]
    assert _guias(robo) == []


def test_valor_que_nao_bate_e_erro_e_a_guia_nao_se_registra(robo, tmp_path):
    _pago_da_cra(robo, saldo="150.00")
    portal = PortalFalso(pdf=pdf_do_boleto())
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    assert r["situacao"] == "ERRO"
    assert "NÃO foi registrado" in r["relato"] and "somam R$ 150,00" in r["relato"]
    assert [g for g in _guias(robo) if g["situacao"] == "REGISTRADA"] == []


def test_gerou_e_nao_confirmou_a_rodada_seguinte_nao_gera_de_novo(robo, tmp_path):
    _pago_da_cra(robo)
    portal = PortalFalso(gera=False, pdf=pdf_do_boleto())
    r1 = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    assert "não apareceu na lista" in r1["relato"]
    assert CRA.normalizar(CONTA) in {CRA.normalizar(c)
                                     for c in r1["estado"][PRP.CHAVE_DO_ESTADO]}
    r2 = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path,
                                             estado=r1["estado"]))
    assert portal.posts_de_geracao() == 1
    assert "não gera de novo sozinho" in r2["relato"]


def test_o_boleto_pago_no_portal_concilia_a_guia(robo, tmp_path):
    p = _pago_da_cra(robo)
    portal = PortalFalso(pdf=pdf_do_boleto())
    PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    portal.boletos[0]["situacao"] = "PAGO"
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    assert [a["acao"] for a in r["acoes"]] == ["conciliou a guia pelo portal"]
    [g] = _guias(robo)
    assert g["situacao"] == "CONCILIADA"
    assert g["comprovante"].startswith("situação no portal: PAGO")
    with robo.connect() as con:
        assert [x for x in REP.pendencias_do_repasse(con, hoje="2026-10-29")
                if x["ato_id"] == p["ato_id"]] == []


def test_captcha_para_o_robo_e_vira_emita_a_mao(robo, tmp_path):
    _pago_da_cra(robo)
    portal = PortalFalso(captcha=True)
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    assert r["situacao"] == "AVISO"
    assert [a["tipo"] for a in r["achados"]] == ["EMITA_A_MAO"]
    assert [m for m, _, _ in portal.pedidos] == ["GET"]


def test_a_senha_nao_vai_ao_log_nem_a_auditoria_nem_ao_relato(robo, tmp_path):
    _pago_da_cra(robo)
    portal = PortalFalso(pdf=pdf_do_boleto())
    r = PRP.emitir_boletos_da_cra(_contexto(robo, portal, tmp_path))
    with robo.connect() as con:
        logs = nativo(con).ler("SELECT * FROM centrais_log WHERE operacao=%s",
                               (PRP.OPERACAO,))
        auditoria = nativo(con).ler("SELECT * FROM audit_logs WHERE agente=%s",
                                    (PRP.AGENTE,))
    assert {x["evento"] for x in logs} >= {"ENTROU", "LEU_BOLETOS", "GERAR_BOLETO",
                                           "GUIA_REGISTRADA"}
    assert auditoria
    tudo = json.dumps([logs, auditoria, r], ensure_ascii=False, default=str)
    assert SENHA_DE_TESTE not in tudo and "DEVEDOR" not in tudo


def test_cofre_trancado_e_aviso_sem_entrar(cg_casa, monkeypatch, tmp_path):
    import automacao_cofre as COFRE
    import centrais_trava_sandbox as TRAVA
    monkeypatch.setattr(TRAVA, "e_sandbox", lambda: False)

    def trancado(_contexto):
        raise COFRE.CofreTrancado("o cofre está trancado")

    monkeypatch.setattr(PRP, "_credencial", trancado)
    portal = PortalFalso()
    r = PRP.emitir_boletos_da_cra(_contexto(cg_casa["db"], portal, tmp_path))
    assert r["situacao"] == "AVISO" and "trancado" in r["relato"]
    assert portal.pedidos == []


def test_no_sandbox_o_robo_nao_entra(cg_casa, monkeypatch, tmp_path):
    import centrais_trava_sandbox as TRAVA
    monkeypatch.setattr(TRAVA, "e_sandbox", lambda: True)
    monkeypatch.setattr(PRP, "_credencial", lambda _c: pytest.fail("leu o cofre"))
    portal = PortalFalso()
    r = PRP.emitir_boletos_da_cra(_contexto(cg_casa["db"], portal, tmp_path))
    assert r["situacao"] == "AVISO" and portal.pedidos == []


# ------------------------------------------------------------ as cercas


def test_o_robo_esta_no_catalogo_e_nasce_desligado():
    import automacao as AU
    import automacao_processos as PROC
    assert "protesto_repasse_portal" in PROC.MODULOS_COM_PROCESSOS
    [semente] = [s for s in PROC.sementes_de_outros_modulos()
                 if s["codigo"] == PRP.CODIGO]
    assert semente["alvo"] == "protesto_repasse_portal:emitir_boletos_da_cra"
    assert semente["alvo"] in AU.funcoes_permitidas()
    assert semente["agenda"]["horarios"] == ["14:30"]


def test_o_robo_nunca_paga():
    for nome in ("protesto_repasse_portal.py", "cra_portal.py"):
        fonte = (RAIZ / nome).read_text(encoding="utf-8")
        assert not re.search(r"^\s*(?:import|from)\s+(despesas_inter|cobranca_banco)\b",
                             fonte, re.MULTILINE), nome
        assert not re.search(r"\b(autorizar|pagar_autorizadas)\s*\(", fonte), nome
