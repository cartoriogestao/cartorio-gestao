"""Do protocolo ao recibo — o CAIXA E O PROTOCOLO GERAL, pelas telas (LT06).

O PEDIDO DO OFICIAL (20/10/2026)
    «quero que seja possível do protocolo à certidão. Minha maior preocupação
    é que TODOS os atos precisam ter uma certidão adequada» — e depois:
    «TERMO E CERTIDÃO».

    No caixa, o «termo» é o que fica escrito na casa — o LANÇAMENTO de cada
    serviço (`cx_lancamentos`, um por item, com os fundos separados) e a linha
    do Livro de Controle de Depósito Prévio — e a «certidão» é o papel que sai
    com o cliente: o RECIBO, o COMPROVANTE DE RECEPÇÃO e o ORÇAMENTO. Os dois
    têm de BATER: o recibo que diz um valor que o caixa não recebeu, ou que
    discrimina um serviço que não foi pago, é o papel que volta na correição.

COMO ESTES TESTES ANDAM
    Como o balcão anda: cliente de teste do Flask, login pelo POST /login com
    o token da tela, e cada passo pelo formulário que a tela oferece — abrir o
    protocolo, pôr o item da tabela, abrir o caixa, quitar, emitir o recibo.
    O papel é lido do .odt que a rota devolve (o `content.xml`), e não de uma
    montagem à parte: é o que o cliente leva.

    A tabela do tribunal é de ENSAIO (valores inventados, vigência 99001), e a
    serventia e as pessoas são fictícias (LGPD).

A BASE NORMATIVA está citada em cada teste e reunida em
`docs/REQUISITOS_LEGAIS.md`, seção «Caixa e protocolo geral (LT06)».
"""
from __future__ import annotations

import html as _html
import io
import re
import sys
import zipfile
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402

SENHA = "Senha#12345"
#: CPF de ensaio (dígitos válidos, de gerador) — nunca de pessoa da casa.
CPF_DE_ENSAIO = "52998224725"
INTERESSADO = "CLIENTE DE EXEMPLO DA SILVA"
ESCREVENTE = "ELISA EXEMPLO ESCREVENTE"
OFICIAL = "MARIO EXEMPLO DOS SANTOS"

#: A serventia COMPLETA: com ela, campo vazio no papel é defeito do papel, e
#: não falta de configuração.
SERVENTIA_COMPLETA = {
    "unit_name": "Ofício Único de Cidade Exemplo/MA",
    "serventia_titulo": "Oficial e Tabelião",
    "serventia_titular": "Mario Exemplo dos Santos",
    "serventia_cnpj": "00.000.042/0001-22",
    "ri_cns": "000000",
    "serventia_telefone": "(99) 3000-0000",
    "serventia_endereco": "Rua de Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
}

VIGENCIA = 99001
#: (código interno, código TJ, descrição, emolumentos, FERC, FADEP, FEMP, FERRFIS)
SERVICOS = (
    (990101, "13.18", "Autenticação de cópia de documento, por página",
     "5,50", "0,22", "0,17", "0,16", "0,16"),
    (990102, "14.5.1", "Certidão do registro civil em breve relato",
     "40,00", "1,60", "1,20", "1,28", "1,28"),
    (990103, "16.24.1", "Certidão negativa de propriedade de imóvel",
     "35,00", "1,40", "1,05", "1,12", "1,12"),
    # os itens que o envelope de cada atribuição pede ao selo (o código que a
    # trava procura no protocolo — `ato_selado.codigo_do_envelope`)
    # 413 é o serviço que a tela do reconhecimento procura (`notas_web`)
    (413, "13.17.2", "Reconhecimento de firma, por assinatura",
     "6,00", "0,24", "0,18", "0,19", "0,19"),
    (990105, "16.24.4", "Certidão de inteiro teor da matrícula",
     "45,00", "1,80", "1,35", "1,44", "1,44"),
    (990106, "17.5.1", "Certidão de protesto, por nome, até cinco anos",
     "30,00", "1,20", "0,90", "0,96", "0,96"),
    (990107, "15.10.1", "Certidão de registro de títulos e documentos",
     "32,00", "1,28", "0,96", "1,02", "1,02"),
)
FUNDOS = ("emolumentos", "ferc", "fadep", "femp", "ferrfis")


def _c(valor: str) -> int:
    return int(valor.replace(".", "").replace(",", ""))


def _r(centavos: int) -> str:
    inteiro, resto = divmod(int(centavos), 100)
    return f"{inteiro:,}".replace(",", ".") + f",{resto:02d}"


def _total(servico) -> str:
    return _r(sum(_c(v) for v in servico[3:]))


# ----------------------------------------------------------------- o balcão


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe o csrf_token"
    return achado.group(1)


class Balcao:
    """Um navegador logado: lê o token da tela e manda o formulário."""

    def __init__(self, app, usuario: str, casa: dict | None = None):
        self.casa = casa
        self.c = app.test_client()
        html = self.c.get("/login").get_data(as_text=True)
        r = self.c.post("/login", data={"username": usuario, "password": SENHA,
                                        "csrf_token": _token(html)})
        assert r.status_code == 302 and "/login" not in r.headers["Location"], \
            "o login do balcão não entrou"
        self.tok = _token(self.c.get("/caixa/protocolos").get_data(as_text=True))

    def get(self, url, **kw):
        return self.c.get(url, **kw)

    def post(self, url, dados=None, seguir=True, **kw):
        return self.c.post(url, data={"csrf_token": self.tok, **(dados or {})},
                           follow_redirects=seguir, **kw)

    def texto(self, url) -> str:
        return self.c.get(url).get_data(as_text=True)


def _texto_da_tela(html: str) -> str:
    """A página como o balcão a lê — avisos do topo incluídos —, sem o HTML."""
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", " ", html)).split())


def texto_do_odt(dados: bytes) -> str:
    """O texto corrido do `content.xml` — o que o cliente lê no papel."""
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        xml = z.read("content.xml").decode("utf-8")
    xml = re.sub(r"<text:(s|tab|line-break)[^>]*/>", " ", xml)
    xml = re.sub(r"</(text:p|text:h|table:table-cell)>", " ", xml)
    return " ".join(_html.unescape(re.sub(r"<[^>]+>", "", xml)).split())


def papel_sem_sobra(texto: str) -> None:
    """Papel pronto não tem marcador de modelo, «None» nem rótulo vazio."""
    for sobra in ("{{", "}}", "{%", "%}", "None"):
        assert sobra not in texto, f"sobrou «{sobra}» no papel: {texto[:400]}"
    for rotulo in ("CNPJ —", "R$ ,", "R$ (", "nº .", "Nº /"):
        assert rotulo not in texto, f"rótulo vazio «{rotulo}» no papel: {texto[:400]}"


@pytest.fixture
def casa(cg_casa):
    """A casa do ensaio: serventia completa, tabela do TJ, oficial e escrevente."""
    db = cg_casa["db"]
    db.set_settings(SERVENTIA_COMPLETA)
    db.create_user("mario", OFICIAL, SENHA, "ADMIN")
    db.create_user("elisa", ESCREVENTE, SENHA, "USER")
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("""INSERT INTO cx_vigencias (codigo, descricao, vigente, servicos,
                                                 faixas, importado_em)
                       VALUES (%s, 'Vigência de ensaio do LT06', 1, %s, 0, '2026-10-20')
                       ON CONFLICT (codigo) DO NOTHING""", (VIGENCIA, len(SERVICOS)))
        bd.escrever("UPDATE cx_vigencias SET vigente = 0 WHERE codigo <> %s", (VIGENCIA,))
        for codigo, tj, descricao, *fundos in SERVICOS:
            bd.escrever("""INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                                                    descricao_norm, ativo)
                           VALUES (%s,%s,%s,%s,1) ON CONFLICT (codigo) DO NOTHING""",
                        (codigo, tj, descricao, descricao.lower()))
            bd.escrever("""INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                                                          ferc, fadep, femp, ferrfis, total)
                           VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                           ON CONFLICT (servico, vigencia) DO NOTHING""",
                        (codigo, VIGENCIA, *fundos, _r(sum(_c(v) for v in fundos))))
    return cg_casa


def _ler(casa, sql, params=()):
    with casa["db"].connect() as con:
        return banco(con).ler(sql, params)


def _um(casa, sql, params=()):
    linhas = _ler(casa, sql, params)
    return linhas[0] if linhas else None


def abrir_protocolo(b: Balcao, *, atribuicao="RCPN", tipo="SERVICO", **extra) -> int:
    dados = {"acao": "novo", "interessado": INTERESSADO,
             "interessado_documento": CPF_DE_ENSAIO, "telefone": "(99) 98888-7777",
             "email": "cliente@exemplo.invalid", "atribuicao": atribuicao,
             "assunto": "Pedido de ensaio do LT06", "tipo": tipo,
             "documento_tipo": "", "documento_descricao": "Requerimento assinado",
             "previsao_entrega": "2026-10-27"} | extra
    r = b.post("/caixa/protocolos", dados, seguir=False)
    assert r.status_code == 302, r.get_data(as_text=True)[:300]
    achado = re.search(r"/caixa/protocolos/(\d+)$", r.headers["Location"])
    assert achado, f"o protocolo não abriu: {r.headers['Location']}"
    return int(achado.group(1))


def acrescentar(b: Balcao, pid: int, servico: int, quantidade: int = 1) -> dict:
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/itens",
                        {"acao": "acrescentar", "servico": str(servico),
                         "quantidade": str(quantidade)}).get_data(as_text=True))
    assert "acrescentado" in t, t[:400]
    return t


def abrir_caixa(b: Balcao) -> None:
    b.post("/caixa", {"acao": "abrir", "saldo_inicial": "0,00"})


def quitar_tudo(b: Balcao, pid: int, forma="PIX") -> str:
    return _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/itens",
                           {"acao": "quitar_todos", "forma_pagamento": forma})
                    .get_data(as_text=True))


def papel(b: Balcao, url: str, dados=None, metodo="post") -> str:
    """O .odt que a rota devolve (seguindo o redirecionamento), em texto."""
    r = b.post(url, dados) if metodo == "post" else b.get(url)
    assert r.mimetype == "application/vnd.oasis.opendocument.text", \
        _texto_da_tela(r.get_data(as_text=True))[:400]
    return texto_do_odt(r.data)


# ====================================================== 1. abertura do protocolo


def test_o_balcao_abre_o_protocolo_com_o_numero_do_mes_e_o_contato(casa):
    """O número do protocolo geral é `AAAA.MM.N`, o mesmo do E-Ofício, e o
    contato é obrigatório ao abrir (ordem do oficial, 10/10/2026). CN-MA art.
    33: o pedido recebido tem a posição na ordem de atendimento, com data e
    hora — sem elas não há como dizer depois o que entrou primeiro."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    hoje = date.today()
    assert re.fullmatch(rf"{hoje.year}\.{hoje.month:02d}\.\d+", p["numero"])
    assert p["situacao"] == "ABERTO" and p["data_abertura"] == hoje.isoformat()
    assert p["interessado"] == INTERESSADO and p["atribuicao"] == "RCPN"
    # Sem telefone nem e-mail, a tela recusa e não abre nada.
    antes = _um(casa, "SELECT count(*) AS n FROM cx_protocolos")["n"]
    t = _texto_da_tela(b.post("/caixa/protocolos",
                        {"acao": "novo", "interessado": INTERESSADO}).get_data(as_text=True))
    assert "telefone" in t.lower() or "e-mail" in t.lower()
    assert _um(casa, "SELECT count(*) AS n FROM cx_protocolos")["n"] == antes


def test_o_segundo_protocolo_do_mes_ganha_o_numero_seguinte(casa):
    b = Balcao(casa["app"], "elisa")
    um = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (abrir_protocolo(b),))
    dois = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (abrir_protocolo(b),))
    assert int(dois["numero"].rsplit(".", 1)[1]) == int(um["numero"].rsplit(".", 1)[1]) + 1


def test_o_comprovante_de_recepcao_diz_o_que_entrou_no_balcao(casa):
    """O comprovante que fica com o cliente: quem trouxe, o quê, para quê,
    quando, e o que vai custar. CN-MA art. 33 (recibo de protocolo com a
    ordem, a data e a hora), art. 447, § 4º, e art. 974, § 1º (data, número de
    ordem e previsão de entrega); LRP art. 14, parágrafo único (os valores no
    documento); dados pessoais mascarados (LGPD art. 6º, III)."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990102)
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    t = papel(b, f"/caixa/protocolos/{pid}/recepcao")
    papel_sem_sobra(t)
    for esperado in (SERVENTIA_COMPLETA["unit_name"], "CNS 000000",
                     f"PROTOCOLO DE RECEPÇÃO Nº {p['numero']}", INTERESSADO,
                     "RCPN", "Pedido de ensaio do LT06", "Requerimento assinado",
                     "14.5.1", _total(SERVICOS[1]), "a quitar", ESCREVENTE):
        assert esperado in t, (esperado, t)
    # O CPF sai mascarado: o papel viaja com o cliente.
    assert CPF_DE_ENSAIO not in t
    assert _um(casa, "SELECT recepcao_em FROM cx_protocolos WHERE id = %s",
               (pid,))["recepcao_em"]


# ============================================== 2. item da tabela e pagamento


def test_o_item_vem_da_tabela_do_tribunal_com_os_fundos_separados(casa):
    """O valor NÃO se digita: sai da tabela vigente (CN-MA art. 87, VIII —
    observar os emolumentos fixados; art. 88, II — nada além da tabela e dos
    fundos). A quantidade multiplica emolumento e cada fundo."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990101, quantidade=3)
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    assert item["codigo_ato"] == "13.18" and int(item["quantidade"]) == 3
    servico = SERVICOS[0]
    for i, fundo in enumerate(FUNDOS):
        assert _c(item[fundo]) == 3 * _c(servico[3 + i]), fundo
    assert _c(item["valor_total"]) == 3 * _c(_total(servico))
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "A_PAGAR"


def test_sem_caixa_aberto_o_item_nao_se_quita(casa):
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990102)
    t = quitar_tudo(b, pid)
    assert "caixa aberto" in t
    assert not _ler(casa, "SELECT id FROM cx_lancamentos WHERE protocolo_id = %s", (pid,))


def test_quitar_lanca_cada_item_no_caixa_e_o_protocolo_fica_pago(casa):
    """Um lançamento POR ITEM, com os fundos do item — é o que deixa a
    conferência dos fundos fechar (CN-MA art. 12, IV — recolhimento ao FERJ e
    aos outros fundos; art. 881, § 1º — FERJ, FERC, FEMP, FADEP e FERRFIS)."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990101, quantidade=2)
    acrescentar(b, pid, 990102)
    abrir_caixa(b)
    t = quitar_tudo(b, pid)
    assert "2 itens quitados" in t
    itens = _ler(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s ORDER BY id",
                 (pid,))
    lancs = _ler(casa, """SELECT * FROM cx_lancamentos WHERE protocolo_id = %s
                           ORDER BY id""", (pid,))
    assert len(lancs) == 2
    for item, lanc in zip(itens, lancs):
        assert item["quitado"] == 1 and item["lancamento_id"] == lanc["id"]
        assert lanc["valor"] == item["valor_total"]
        assert lanc["forma_pagamento"] == "PIX" and lanc["sentido"] == "ENTRADA"
        assert lanc["pagador"] == INTERESSADO
        for fundo in FUNDOS:
            assert lanc[fundo] == item[fundo], fundo
        assert lanc["numero"] and lanc["hash_lancamento"]
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "PAGO"


# ============================================================== 3. o recibo


def _protocolo_pago(b: Balcao, *servicos, forma="PIX") -> int:
    pid = abrir_protocolo(b)
    for s in servicos:
        acrescentar(b, pid, s)
    abrir_caixa(b)
    quitar_tudo(b, pid, forma=forma)
    return pid


def test_o_recibo_do_atendimento_e_fiel_ao_que_entrou_no_caixa(casa):
    """O RECIBO É A CERTIDÃO DO CAIXA: tem de dizer o que o caixa recebeu, nem
    mais nem menos. CN-MA art. 87, IX (Lei 8.935/1994, art. 30, IX: «dar
    recibo dos emolumentos percebidos») e XVI (o valor no próprio documento,
    também LRP art. 14, parágrafo único); art. 952 e Lei 9.492/1997, art. 37,
    § 2º (parcelas discriminadas); art. 115, II (recibo numerado e datado)."""
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990101, 990102)
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    t = papel(b, f"/caixa/protocolos/{pid}/recibo")
    papel_sem_sobra(t)
    r = _um(casa, "SELECT * FROM cx_recibos WHERE protocolo_id = %s", (pid,))
    lancs = _ler(casa, "SELECT * FROM cx_lancamentos WHERE protocolo_id = %s ORDER BY id",
                 (pid,))
    total = sum(_c(l["valor"]) for l in lancs)
    assert _c(r["valor_total"]) == total
    # identificação da serventia e de quem responde por ela
    for esperado in (SERVENTIA_COMPLETA["unit_name"], SERVENTIA_COMPLETA["serventia_titular"],
                     f"CNPJ {SERVENTIA_COMPLETA['serventia_cnpj']}", "CNS 000000",
                     SERVENTIA_COMPLETA["serventia_endereco"]):
        assert esperado in t, esperado
    # o recibo: número por exercício, quem pagou, quanto (e por extenso), de quê
    assert f"RECIBO Nº {r['numero']}/{r['ano']}" in t
    assert f"Recebemos de: {INTERESSADO}" in t
    assert f"R$ {_r(total)} ({r['valor_extenso']})" in t
    assert f"protocolo nº {p['numero']}" in t
    for servico in SERVICOS[:2]:
        assert servico[1] in t and servico[2] in t and _total(servico) in t
    for fundo, rotulo in zip(FUNDOS, ("emolumentos R$", "FERC R$", "FADEP R$", "FEMP R$",
                                      "FERRFIS R$")):
        assert f"{rotulo} {_r(sum(_c(l[fundo]) for l in lancs))}" in t, fundo
    assert "Forma de pagamento: PIX" in t
    assert f"Conferência: {r['hash_recibo'][:16]}" in t
    assert ESCREVENTE in t and "Cidade Exemplo/MA" in t
    # o CPF do pagador vai mascarado
    assert CPF_DE_ENSAIO not in t
    # e todo o dinheiro do recibo fica marcado: não sai num segundo recibo
    assert all(l["recibo_id"] == r["id"] for l in lancs)


def test_o_recibo_de_um_lancamento_discrimina_so_o_que_ele_pagou(casa):
    """O recibo de UM lançamento (o botão da ficha do ato e da tela do caixa)
    listava TODOS os itens do protocolo, pagos ou não, e somava os fundos de
    todos: «A importância de R$ 6,21», e logo abaixo a discriminação de R$
    51,57 (medido em 20/10/2026; consertado no LT06, em `caixa_web.caixa_recibo`).
    Recibo é prova de pagamento — é a frase da própria rota do recibo do
    atendimento — e dizer que se recebeu o que não se recebeu é o papel que
    volta (CN-MA art. 87, IX; Lei 8.935/1994, art. 30, IX)."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990101)
    acrescentar(b, pid, 990102)
    abrir_caixa(b)
    primeiro = _ler(casa, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id = %s "
                          "ORDER BY id", (pid,))[0]["id"]
    b.post(f"/caixa/protocolos/{pid}/itens", {"acao": "quitar", "item_id": str(primeiro),
                                              "forma_pagamento": "DINHEIRO"})
    lanc = _um(casa, "SELECT * FROM cx_lancamentos WHERE protocolo_id = %s", (pid,))
    t = papel(b, f"/caixa/recibo/{lanc['id']}")
    papel_sem_sobra(t)
    assert f"R$ {_total(SERVICOS[0])}" in t
    assert SERVICOS[0][2] in t
    assert SERVICOS[1][2] not in t, "o recibo discrimina serviço que não foi pago"
    assert f"emolumentos R$ {SERVICOS[0][3]};" in t


def test_sem_servico_pago_nao_ha_recibo(casa):
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    acrescentar(b, pid, 990102)
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/recibo").get_data(as_text=True))
    assert "Recibo é prova de pagamento" in t
    assert not _ler(casa, "SELECT id FROM cx_recibos WHERE protocolo_id = %s", (pid,))


def test_o_mesmo_dinheiro_nao_sai_em_dois_recibos(casa):
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990102)
    papel(b, f"/caixa/protocolos/{pid}/recibo")
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/recibo").get_data(as_text=True))
    assert "já estão num recibo" in t
    assert len(_ler(casa, "SELECT id FROM cx_recibos WHERE protocolo_id = %s", (pid,))) == 1


def test_a_reimpressao_do_recibo_sai_com_o_mesmo_teor(casa):
    """O teor do recibo fica congelado (`discriminacao` + hash): a segunda via
    é a mesma, ainda que o item mude depois."""
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990102)
    primeira = papel(b, f"/caixa/protocolos/{pid}/recibo")
    r = _um(casa, "SELECT id FROM cx_recibos WHERE protocolo_id = %s", (pid,))
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE cx_protocolo_atos SET descricao = 'MUDOU' "
                            "WHERE protocolo_id = %s", (pid,))
    segunda = papel(b, f"/caixa/recibo/{r['id']}/odt", metodo="get")
    tirar_hora = re.compile(r"emitido pelo sistema em [0-9/: ]+")
    assert tirar_hora.sub("", primeira) == tirar_hora.sub("", segunda)


# ============================================================ 4. o orçamento


def test_o_orcamento_de_mero_calculo_diz_que_nao_e_ato(casa):
    """«Mero cálculo» não é recibo nem prenotação: o papel diz isso com todas
    as letras (peça CAIXA_ORCAMENTO__aviso), e traz os valores da tabela
    vigente por ato, com os fundos. LRP art. 12, parágrafo único (exame e
    cálculo independem de protocolo); CN-MA art. 450, § 5º (estimativa, sem
    vínculo com o valor definitivo); art. 87, VII (a tabela à vista)."""
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b, tipo="ORCAMENTO")
    acrescentar(b, pid, 990103)
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    t = papel(b, f"/caixa/protocolos/{pid}/orcamento", metodo="get")
    papel_sem_sobra(t)
    assert f"CÁLCULO DE EMOLUMENTOS Nº {p['numero']}" in t
    assert "MERO CÁLCULO DE EMOLUMENTOS" in t and "NÃO representa a prática de ato" in t
    assert "16.24.1" in t and f"TOTAL: R$ {_total(SERVICOS[2])}" in t
    assert f"vigência {VIGENCIA}" in t


# ======================================================== 5. estorno e devolução


def test_o_estorno_exige_motivo_desfaz_a_quitacao_e_deixa_o_rastro(casa):
    """Dinheiro que entrou sai por ESTORNO, que deixa rastro: o lançamento
    original fica, marcado, e o item volta a «a pagar» (F13). Sem motivo, não
    se estorna — é a pergunta da correição (CN-MA art. 204: a restituição se
    lança; art. 206: retificação circunstanciada, com histórico)."""
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990102)
    lanc = _um(casa, "SELECT * FROM cx_lancamentos WHERE protocolo_id = %s", (pid,))
    t = _texto_da_tela(b.post("/caixa", {"acao": "estornar", "lancamento_id": str(lanc["id"]),
                                   "motivo": ""}).get_data(as_text=True))
    assert "precisa de motivo" in t
    t = _texto_da_tela(b.post("/caixa", {"acao": "estornar", "lancamento_id": str(lanc["id"]),
                                   "motivo": "Cliente desistiu antes do ato"})
                 .get_data(as_text=True))
    assert "Estornado" in t
    original = _um(casa, "SELECT * FROM cx_lancamentos WHERE id = %s", (lanc["id"],))
    estorno = _um(casa, "SELECT * FROM cx_lancamentos WHERE estorna_id = %s", (lanc["id"],))
    assert original["estornado"] == 1 and original["estornado_por_id"] == estorno["id"]
    assert estorno["valor"] == lanc["valor"] and estorno["sentido"] == "ESTORNO"
    assert "Cliente desistiu" in estorno["motivo_estorno"]
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    assert item["quitado"] == 0 and item["lancamento_id"] is None
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "A_PAGAR"
    # O caixa do dia não conta o estornado nem o estorno.
    from caixa_schema import resumo_caixa
    resumo = resumo_caixa(_ler(casa, "SELECT * FROM cx_lancamentos WHERE caixa_id = %s "
                                     "ORDER BY id", (lanc["caixa_id"],)))
    assert resumo["entradas"] == 0 and resumo["saidas"] == 0


def test_protocolo_com_dinheiro_dentro_nao_se_encerra(casa):
    """Encerrar faria o serviço sumir da lista e o valor ficar: o caminho é o
    estorno (`caixa_protocolo.encerrar`)."""
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990102)
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}",
                        {"acao": "encerrar", "encerramento": "CANCELADO",
                         "motivo": "O cliente não voltou ao balcão"}).get_data(as_text=True))
    assert "Estorne o lançamento primeiro" in t
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "PAGO"


def test_o_protocolo_sem_servico_se_encerra_com_motivo_e_reabre(casa):
    b = Balcao(casa["app"], "elisa")
    pid = abrir_protocolo(b)
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}",
                        {"acao": "encerrar", "encerramento": "CANCELADO",
                         "motivo": "Era só uma consulta de preço"}).get_data(as_text=True))
    assert "encerrado como cancelado" in t
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    assert p["situacao"] == "CANCELADO" and p["encerrado_por"] == "elisa"
    b.post(f"/caixa/protocolos/{pid}", {"acao": "reabrir",
                                        "motivo": "O cliente voltou com o papel"})
    p = _um(casa, "SELECT * FROM cx_protocolos WHERE id = %s", (pid,))
    assert p["situacao"] == "ABERTO" and "Era só uma consulta" in p["encerramento_motivo"]


# ============================================================ 6. depósito prévio


def _deposito(b: Balcao, valor="100,00", **extra) -> dict:
    t = _texto_da_tela(b.post("/caixa/depositos",
                        {"acao": "novo", "valor": valor, "depositante": INTERESSADO,
                         "depositante_documento": CPF_DE_ENSAIO,
                         "forma_pagamento": "DINHEIRO", "atribuicao": "RI",
                         "observacao": "Adiantamento do título de ensaio"} | extra)
                 .get_data(as_text=True))
    assert "registrado" in t, t[:300]
    return t


def test_o_deposito_previo_entra_no_caixa_e_e_consumido_no_protocolo(casa):
    """O depósito prévio tem número próprio (DPAAAA.MM.N), entra no caixa do
    dia e baixa o saldo quando é usado — com o protocolo (CN-MA, arts. 195 a
    202: Livro de Controle de Depósito Prévio)."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    t = _deposito(b)
    assert "lançado no caixa" in t
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    assert re.fullmatch(r"DP\d{4}\.\d{2}\.\d+", d["numero"]) and d["saldo"] == "100,00"
    entrada = _um(casa, "SELECT * FROM cx_lancamentos WHERE natureza = 'DEPOSITO_PREVIO'")
    assert entrada["valor"] == "100,00" and d["numero"] in entrada["descricao"]
    t = _texto_da_tela(b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                             "valor_usar": "30,00",
                                             "protocolo": p["numero"]}).get_data(as_text=True))
    assert "Saldo do depósito: R$ 70,00" in t
    d = _um(casa, "SELECT * FROM cx_depositos WHERE id = %s", (d["id"],))
    assert d["saldo"] == "70,00" and d["protocolo_id"] == pid
    # Usar mais do que há é recusado.
    t = _texto_da_tela(b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                             "valor_usar": "70,01"}).get_data(as_text=True))
    assert "Não dá para usar" in t


def test_a_devolucao_do_deposito_sai_da_gaveta_com_o_motivo(casa):
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    _deposito(b, "50,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    t = _texto_da_tela(b.post("/caixa/depositos", {"acao": "devolver", "deposito_id": str(d["id"]),
                                             "motivo": "Título devolvido com exigência"})
                 .get_data(as_text=True))
    assert "R$ 50,00 devolvidos" in t
    d = _um(casa, "SELECT * FROM cx_depositos WHERE id = %s", (d["id"],))
    assert d["encerrado"] == 1 and d["saldo"] == "0,00"
    saida = _um(casa, "SELECT * FROM cx_lancamentos WHERE natureza = 'DEVOLUCAO'")
    assert saida["sentido"] == "SAIDA" and saida["valor"] == "50,00"
    assert "Título devolvido com exigência" in saida["descricao"]


def test_o_livro_de_deposito_previo_traz_as_seis_indicacoes_do_art_198(casa):
    """CN-MA art. 198: I protocolo; II data do depósito; III valor; IV data da
    conversão em emolumentos com o ato; V data da devolução com a
    justificativa; VI o orçamento. O livro lê o rastro das telas."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                "valor_usar": "30,00", "protocolo": p["numero"]})
    b.post("/caixa/depositos", {"acao": "devolver", "deposito_id": str(d["id"]),
                                "motivo": "Sobra devolvida ao apresentante"})
    oficial = Balcao(casa["app"], "mario")
    t = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    hoje = date.today().isoformat()
    assert d["numero"] in t and INTERESSADO in t
    assert p["numero"] in t                                   # I
    assert hoje in t                                          # II
    assert "R$ 100,00" in t                                   # III
    assert f"{hoje}: R$ 30,00 — protocolo {p['numero']}" in t  # IV
    assert f"{hoje}: R$ 70,00 — Sobra devolvida ao apresentante" in t  # V
    assert "saíram do saldo sem uso" not in t


# ================================================== 7. NFS-e desligada de fábrica


def test_a_nfse_nasce_desligada_e_o_recibo_nao_vira_nota_sozinho(casa):
    """A NFS-e (LG01) nasce DESLIGADA: o recibo sai, e o botão «Emitir» diz
    onde se liga, sem mandar nada ao emissor nem gravar nota."""
    b = Balcao(casa["app"], "elisa")
    pid = _protocolo_pago(b, 990102)
    papel(b, f"/caixa/protocolos/{pid}/recibo")
    r = _um(casa, "SELECT * FROM cx_recibos WHERE protocolo_id = %s", (pid,))
    assert casa["db"].get_setting("nfse_ligada", "0") in ("", "0")
    t = _texto_da_tela(b.post(f"/caixa/nfse/recibo/{r['id']}/emitir").get_data(as_text=True))
    assert "desligada" in t
    assert not _ler(casa, "SELECT id FROM nfse_notas WHERE recibo_id = %s", (r["id"],))
    r = _um(casa, "SELECT * FROM cx_recibos WHERE id = %s", (r["id"],))
    assert not r["nfse_numero"] and not r["nfse_chave"]


# ======================================================= 8. fechar e conferir


def test_o_caixa_se_fecha_por_quem_atendeu_e_se_confere_por_outro(casa):
    """Fechar não é conferir, e são duas pessoas: quem atendeu fecha e conta;
    o oficial confere depois — e fica gravado quem e quando (CN-MA art. 12, II
    e IV: o corregedor fiscaliza os recibos e os recolhimentos)."""
    b = Balcao(casa["app"], "elisa")
    _protocolo_pago(b, 990102, forma="DINHEIRO")
    t = _texto_da_tela(b.post("/caixa", {"acao": "fechar", "valor_contado": _total(SERVICOS[1])})
                 .get_data(as_text=True))
    assert "Caixa fechado" in t and "diferença R$ 0,00" in t
    caixa = _um(casa, "SELECT * FROM cx_caixas WHERE operador_nome = %s", (ESCREVENTE,))
    assert caixa["situacao"] == "FECHADO" and caixa["valor_esperado"] == _total(SERVICOS[1])
    t = _texto_da_tela(b.post("/caixa", {"acao": "conferir", "caixa_id": str(caixa["id"])})
                 .get_data(as_text=True))
    assert "Quem atendeu não confere o próprio caixa" in t
    oficial = Balcao(casa["app"], "mario")
    oficial.post("/caixa", {"acao": "conferir", "caixa_id": str(caixa["id"])})
    caixa = _um(casa, "SELECT * FROM cx_caixas WHERE id = %s", (caixa["id"],))
    mario = _um(casa, "SELECT id FROM users WHERE username = 'mario'")
    assert caixa["conferido_por"] == mario["id"] and caixa["conferido_em"]


def test_o_deposito_que_pagou_o_item_pelo_quadro_do_selo_aparece_no_livro(casa):
    """O quadro «Para selar este ato falta» paga o item com o depósito do
    protocolo (`caixa_depositos.pagar_item`), e o débito fica em
    `cx_deposito_usos` — mas o Livro de Controle de Depósito Prévio só lia o
    rastro da tela do caixa (`audit_logs`), e mostrava o débito como «saiu do
    saldo sem uso nem devolução» (medido em 20/10/2026). O art. 198, IV, pede a
    data da conversão em emolumentos COM o ato: o rastro do débito tem os
    dois, e o livro passou a lê-lo (LT06)."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    acrescentar(b, pid, 990103)
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                "valor_usar": "10,00", "protocolo": p["numero"]})
    b.post("/selo/cobertura/atender", {"protocolo": p["numero"]})
    t = _texto_da_tela(b.post("/selo/cobertura/deposito", {"item_id": str(item["id"])})
                 .get_data(as_text=True))
    assert f"Item pago com o depósito {d['numero']}" in t, t[-600:]
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s", (item["id"],))
    assert item["quitado"] == 1 and item["quitado_por"].startswith("DEPÓSITO PRÉVIO")
    oficial = Balcao(casa["app"], "mario")
    t = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    hoje = date.today().isoformat()
    assert f"{hoje}: R$ 10,00 — protocolo {p['numero']}" in t
    assert f"{hoje}: R$ {_total(SERVICOS[2])} — protocolo {p['numero']}" in t
    assert "16.24.1" in t
    assert "saíram do saldo sem uso" not in t


def test_o_recibo_do_deposito_previo_traz_o_orcamento_discriminado(casa):
    """O recibo do depósito «deverá incluir a discriminação orçamentária de
    todos os valores previstos para o serviço requerido» (CN-MA art. 197), e
    o livro, «a descrição completa do orçamento, inclusive seus acréscimos»
    (art. 198, VI). Consertado no LD06: o depósito guarda o orçamento
    congelado (`cx_depositos.orcamento`).

    O DEPÓSITO DIZ O SERVIÇO (LD06). Até o LT06 este teste registrava o
    depósito sem serviço nem protocolo, e esperava o 16.24.1 no recibo — que
    não tinha de onde sair: o orçamento é do serviço requerido (art. 197), e
    quem o requer é o cliente, no balcão. O depósito agora informa o serviço
    pelo campo que a tela já tinha; a asserção é a mesma."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    _deposito(b, "100,00", servico_codigo="990103")
    lanc = _um(casa, "SELECT id FROM cx_lancamentos WHERE natureza = 'DEPOSITO_PREVIO'")
    t = papel(b, f"/caixa/recibo/{lanc['id']}")
    assert "DISCRIMINAÇÃO" in t and "16.24.1" in t
    oficial = Balcao(casa["app"], "mario")
    livro = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    assert "VI — sem orçamento" not in livro and "VI — orçamento só pelo serviço" not in livro


def test_usar_o_deposito_no_protocolo_quita_o_item(casa):
    """«Usar» o depósito com o número do protocolo baixava o saldo e deixava o
    item a pagar: a trava do selo pedia o pagamento de novo e o caixa o
    cobrava em dinheiro — o cliente pagava duas vezes. Consertado no LD06:
    o «usar» quita o item pelo mesmo débito do quadro «Selo e caixa»
    (`caixa_depositos.pagar_item`). CN-MA art. 202."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    acrescentar(b, pid, 990103)
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                "valor_usar": _total(SERVICOS[2]), "protocolo": p["numero"]})
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    assert item["quitado"] == 1


def test_o_deposito_com_o_protocolo_do_orcamento_guarda_cada_item_com_os_fundos(casa):
    """O orçamento de mais de um ato se monta no protocolo — o «mero cálculo»
    é um protocolo —, e o depósito que aponta para ele guarda TODOS os itens a
    pagar, com os emolumentos e cada fundo: os acréscimos do art. 198, VI.
    Congelados no dia, como o teor do recibo: o item mexido depois não muda o
    que foi dito ao cliente. E o recibo diz que a discriminação é ORÇAMENTO,
    e não pagamento de ato (CN-MA arts. 197 e 202) — LD06."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI", tipo="ORCAMENTO")
    acrescentar(b, pid, 990101, quantidade=2)
    acrescentar(b, pid, 990103)
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    orcado = 2 * _c(_total(SERVICOS[0])) + _c(_total(SERVICOS[2]))
    t = _deposito(b, "100,00", protocolo=p["numero"])
    assert f"Orçamento de R$ {_r(orcado)} guardado" in t, t[:500]
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    assert d["protocolo_id"] == pid
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE cx_protocolo_atos SET valor_total = '1,00', "
                            "emolumentos = '1,00' WHERE protocolo_id = %s", (pid,))
    lanc = _um(casa, "SELECT id FROM cx_lancamentos WHERE natureza = 'DEPOSITO_PREVIO'")
    t = papel(b, f"/caixa/recibo/{lanc['id']}")
    papel_sem_sobra(t)
    assert "DISCRIMINAÇÃO ORÇAMENTÁRIA" in t
    assert "R$ 100,00 (cem reais)" in t
    for servico in (SERVICOS[0], SERVICOS[2]):
        assert servico[1] in t and servico[2] in t, servico[1]
    assert _r(2 * _c(_total(SERVICOS[0]))) in t and _total(SERVICOS[2]) in t
    for i, (fundo, rotulo) in enumerate(zip(FUNDOS, ("emolumentos R$", "FERC R$",
                                                     "FADEP R$", "FEMP R$",
                                                     "FERRFIS R$"))):
        soma = 2 * _c(SERVICOS[0][3 + i]) + _c(SERVICOS[2][3 + i])
        assert f"{rotulo} {_r(soma)}" in t, fundo
    assert f"Depósito prévio nº {d['numero']}" in t
    assert "ORÇAMENTO de todos os valores previstos" in t
    assert f"no total de R$ {_r(orcado)}" in t and "não recibo de emolumentos" in t
    oficial = Balcao(casa["app"], "mario")
    livro = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    assert f"Total do orçamento: R$ {_r(orcado)}" in livro
    assert "VI — sem orçamento" not in livro and "VI — orçamento só" not in livro


def test_o_deposito_sem_orcamento_entra_avisado_e_o_livro_aponta_a_falta(casa):
    """O tipo do depósito é opcional (o oficial, 17/09/2026), e o depósito sem
    serviço nem protocolo entra — mas a tela diz que o recibo vai sem a
    discriminação do art. 197, o recibo não inventa uma, e o livro aponta a
    falta do art. 198, VI, em vez de imprimir a coluna vazia (LD06)."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    t = _deposito(b, "50,00")
    assert "ficou sem orçamento" in t
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    assert d["orcamento"] is None
    lanc = _um(casa, "SELECT id FROM cx_lancamentos WHERE natureza = 'DEPOSITO_PREVIO'")
    recibo = papel(b, f"/caixa/recibo/{lanc['id']}")
    papel_sem_sobra(recibo)
    assert "DISCRIMINAÇÃO" not in recibo
    assert f"Depósito prévio nº {d['numero']}" in recibo
    oficial = Balcao(casa["app"], "mario")
    livro = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    assert "VI — sem orçamento" in livro


def test_o_protocolo_do_orcamento_que_nao_existe_e_recusado_sem_gravar(casa):
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    t = _texto_da_tela(b.post("/caixa/depositos",
                        {"acao": "novo", "valor": "100,00", "depositante": INTERESSADO,
                         "forma_pagamento": "DINHEIRO", "protocolo": "2026.99.999"})
                 .get_data(as_text=True))
    assert "O protocolo 2026.99.999 não existe" in t
    assert not _ler(casa, "SELECT id FROM cx_depositos ORDER BY id")
    assert not _ler(casa, "SELECT id FROM cx_lancamentos ORDER BY id")


def _usar(b: Balcao, deposito_id, valor: str, protocolo: str = "") -> str:
    return _texto_da_tela(b.post("/caixa/depositos",
                                 {"acao": "usar", "deposito_id": str(deposito_id),
                                  "valor_usar": valor, "protocolo": protocolo})
                          .get_data(as_text=True))


def test_usar_quita_so_os_itens_inteiros_que_o_valor_cobre_e_avisa_o_resto(casa):
    """Meio item pago não existe no caixa: o valor usado quita, na ordem do
    protocolo, cada item que ele cobre INTEIRO; o que não cabe fica a pagar,
    com aviso — é o item que o balcão cobraria sem saber que parte do
    dinheiro do cliente já foi usada ali. O resto do valor é o uso de sempre,
    e o livro lê cada parte de um lugar só: fecha com o saldo (LD06)."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    acrescentar(b, pid, 990103)            # 39,69 — não cabe em 20,00
    acrescentar(b, pid, 990101)            # 6,21 — cabe
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    t = _usar(b, d["id"], "20,00", p["numero"])
    assert "Saldo do depósito: R$ 80,00" in t
    assert f"Quitado(s) com o depósito no protocolo {p['numero']}: 13.18" in t
    assert "1 item(ns) do protocolo" in t and "continua(m) a pagar" in t
    itens = _ler(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s "
                       "ORDER BY id", (pid,))
    assert [i["quitado"] for i in itens] == [0, 1]
    assert itens[1]["quitado_por"] == f"DEPÓSITO PRÉVIO {d['numero']}"
    usos = _ler(casa, "SELECT * FROM cx_deposito_usos WHERE deposito_id = %s "
                      "ORDER BY id", (d["id"],))
    assert [(u["item_id"], int(u["valor_centavos"])) for u in usos] == [
        (itens[1]["id"], _c(_total(SERVICOS[0])))]
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "A_PAGAR"
    oficial = Balcao(casa["app"], "mario")
    livro = _texto_da_tela(oficial.texto("/livros-obrigatorios/deposito-previo"))
    hoje = date.today().isoformat()
    assert f"{hoje}: R$ {_total(SERVICOS[0])} — protocolo {p['numero']} (item 13.18)" in livro
    assert f"{hoje}: R$ {_r(2000 - _c(_total(SERVICOS[0])))} — protocolo {p['numero']}" in livro
    assert "saíram do saldo sem uso" not in livro


def test_o_item_pago_pelo_deposito_nao_se_cobra_de_novo_nem_se_reabre(casa):
    """NADA DE ITEM PAGO DUAS VEZES. O item que o «usar» quitou não entra no
    caixa em dinheiro — nem pelo botão de um item, que a tela velha ou outra
    aba ainda mostra, nem pelo «quitar todos» —, não se reabre deixando o
    valor gasto no depósito, e o segundo «usar» no mesmo protocolo não o
    paga outra vez (LD06; CN-MA art. 202)."""
    b = Balcao(casa["app"], "elisa")
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    acrescentar(b, pid, 990103)
    p = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    _usar(b, d["id"], _total(SERVICOS[2]), p["numero"])
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    assert item["quitado"] == 1
    assert _um(casa, "SELECT situacao FROM cx_protocolos WHERE id = %s",
               (pid,))["situacao"] == "PAGO"
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/itens",
                              {"acao": "quitar", "item_id": str(item["id"]),
                               "forma_pagamento": "DINHEIRO"}).get_data(as_text=True))
    assert "já está quitado" in t
    t = quitar_tudo(b, pid, forma="DINHEIRO")
    assert "Não há item a quitar" in t
    assert not _ler(casa, "SELECT id FROM cx_lancamentos WHERE origem = 'PROTOCOLO' "
                          "AND protocolo_id = %s ORDER BY id", (pid,))
    t = _texto_da_tela(b.post(f"/caixa/protocolos/{pid}/itens",
                              {"acao": "desquitar", "item_id": str(item["id"])})
                       .get_data(as_text=True))
    assert f"foi pago com o depósito prévio {d['numero']}" in t
    assert _um(casa, "SELECT quitado FROM cx_protocolo_atos WHERE id = %s",
               (item["id"],))["quitado"] == 1
    _usar(b, d["id"], _total(SERVICOS[2]), p["numero"])
    assert len(_ler(casa, "SELECT id FROM cx_deposito_usos WHERE item_id = %s "
                          "ORDER BY id", (item["id"],))) == 1


# ============================== 9. selo pago × caixa, em cada atribuição
#
# A REGRA DO OFICIAL (LX16, 19/10/2026): «os selos pagos precisam estar sempre
# vinculados a um protocolo geral e à confirmação da entrada de um dinheiro».
# A trava mora em `ato_selado.obter_selo` — o ponto por onde todo selo passa —,
# e aqui ela é medida PELA TELA de cada atribuição, com o aparelho de mentira
# (`selador_de_bancada.ligar_o_selador`) e SEM o protocolo pronto da bancada
# (`protocolo_pago=False`): o protocolo é o que o balcão abre e paga.
# CN-MA art. 130, § 2º: nenhum ato sujeito a selo se conclui sem o selo.


@pytest.fixture
def aparelho(casa):
    from selador_de_bancada import ligar_o_selador
    casa["db"].set_settings({"selo_tabela_custas_em": "2026-01-01",
                             "modulo_protesto_ligado": "1"})
    with ligar_o_selador(casa, protocolo_pago=False) as falso:
        yield falso


def pagar_e_atender(b: Balcao, *, atribuicao: str, servico: int,
                    atender: bool = True) -> dict:
    """O que o balcão faz antes do ato pago: protocolo, item, caixa, quitação
    e — para os selos que procuram o item pelo código — o atendimento."""
    pid = abrir_protocolo(b, atribuicao=atribuicao)
    acrescentar(b, pid, servico)
    abrir_caixa(b)
    quitar_tudo(b, pid, forma="DINHEIRO")
    numero = _um(b.casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))["numero"]
    if atender:
        t = _texto_da_tela(b.post("/selo/cobertura/atender", {"protocolo": numero})
                     .get_data(as_text=True))
        assert f"Você está atendendo o protocolo {numero}" in t
    item = _um(b.casa, "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s", (pid,))
    assert item["quitado"] == 1
    return {"pid": pid, "numero": numero, "item": item}


def _selos(casa, tabela: str) -> list[dict]:
    return _ler(casa, "SELECT * FROM sd_selos WHERE tabela = %s AND cancelado_em IS NULL "
                      "ORDER BY id", (tabela,))


def _coberturas(casa, tabela: str) -> list[dict]:
    return _ler(casa, "SELECT * FROM cx_selo_coberturas WHERE tabela = %s ORDER BY id",
                (tabela,))


def _balcao_com_casa(casa) -> Balcao:
    return Balcao(casa["app"], "elisa", casa)


def test_notas_o_reconhecimento_de_firma_so_sela_com_o_protocolo_pago(casa, aparelho):
    """Notas — reconhecimento de firma (item 13.17.2). Sem protocolo, o ato
    não fica de pé e a tela leva ao quadro «Selo e caixa»; pago e atendido, o
    selo sai e gasta UMA unidade do item."""
    with casa["db"].transaction() as con:
        cartao = banco(con).escrever(
            """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                       abertura, criado_em)
               VALUES (%s, %s, %s, 'MANUAL', 1, '2026-01-10', '2026-10-20T09:00:00')
               RETURNING id""", (INTERESSADO, INTERESSADO, CPF_DE_ENSAIO))[0]["id"]
    b = _balcao_com_casa(casa)

    def reconhecer():
        return b.post("/notas/reconhecimento", {"acao": "reconhecer",
                                                "cartao_id": str(cartao),
                                                "especie": "SEMELHANCA"})

    # SEM PROTOCOLO O ATO FICA SUSPENSO (22/10/2026, decisão do oficial: «pode
    # ser suspenso, com botão para selar depois do pagamento»). Até essa data
    # este teste cobrava o ato apagado; foi virado, e não apagado.
    r = reconhecer()
    t = _texto_da_tela(r.get_data(as_text=True))
    assert "SUSPENSO" in t and "Para selar este ato falta" in t
    assert r.request.path == "/selo/cobertura"
    suspenso = _um(casa, "SELECT * FROM nt_reconhecimentos ORDER BY id DESC LIMIT 1")
    assert suspenso and not (suspenso["selo"] or "").strip()
    assert not _ler(casa, "SELECT id FROM sd_selos ORDER BY id")
    # O balcão paga, e o escrevente ESCOLHE o protocolo ao selar o suspenso —
    # sem passar pelo «Atender» de «Selo e caixa».
    pago = pagar_e_atender(b, atribuicao="NOTAS", servico=413, atender=False)
    b.post(f"/notas/reconhecimento/{suspenso['id']}/selar",
           {"protocolo_selo": str(pago["pid"])})
    assert _um(casa, "SELECT count(*) AS n FROM nt_reconhecimentos")["n"] == 1
    ato = _um(casa, "SELECT * FROM nt_reconhecimentos ORDER BY id DESC LIMIT 1")
    assert ato and ato["selo"], "o reconhecimento pago não saiu selado"
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s", (pago["item"]["id"],))
    assert int(item["quantidade_usada"]) == 1
    cob = _ler(casa, "SELECT * FROM cx_selo_coberturas ORDER BY id")
    assert [(c["forma"], c["situacao"], c["protocolo_id"]) for c in cob] == [
        ("ITEM_PAGO", "CONFIRMADA", pago["pid"])]


def _matricula(casa) -> int:
    with casa["db"].transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO ri_matriculas (numero, livro, data_abertura, criado_em)
               VALUES ('4099', '2', '2016-01-10', '2026-10-20T09:00:00') RETURNING id"""
        )[0]["id"])


def test_ri_a_certidao_de_inteiro_teor_so_sela_com_o_protocolo_pago(casa, aparelho,
                                                                   monkeypatch):
    """Registro de Imóveis — certidão de inteiro teor (item 16.24.4). Sem
    protocolo pago, a certidão fica SUSPENSA — gravada, sem selo e sem poder
    ser impressa — e a tela diz por quê; paga, o «Selar» a sela, sem tomar
    número novo (CN-MA art. 155: certidão leva selo).

    Até 22/10/2026 ela era CANCELADA. Decisão do oficial naquele dia, depois
    de as certidões 83 e 84 da produção se cancelarem com o protocolo quitado:
    «pode ser suspenso, com botão para selar depois do pagamento»."""
    import ri_web
    monkeypatch.setattr(ri_web.CFOLHAS, "decidir_folhas_antes_de_emitir", lambda **k: 1)
    mid = _matricula(casa)
    b = _balcao_com_casa(casa)

    t = _texto_da_tela(b.post(f"/registro-imoveis/{mid}/certidao",
                              {"tipo": "INTEIRO_TEOR", "fonte_corpo": "TEXTO",
                               "requerente": INTERESSADO}).get_data(as_text=True))
    assert "SEM SELO" in t and "Para selar este ato falta" in t, t[-600:]
    certidoes = _ler(casa, "SELECT * FROM ri_certidoes ORDER BY id")
    assert len(certidoes) == 1
    suspensa = certidoes[0]
    assert not suspensa["cancelada"] and not suspensa["selo_texto"]
    pagar_e_atender(b, atribuicao="RI", servico=990105)
    b.post(f"/registro-imoveis/certidoes/{suspensa['id']}/selar", {})
    depois = _um(casa, "SELECT * FROM ri_certidoes WHERE id = %s", (suspensa["id"],))
    assert not depois["cancelada"] and depois["selo_texto"], "a certidão paga não selou"
    assert len(_ler(casa, "SELECT id FROM ri_certidoes")) == 1, "tomou número novo"
    selos = _ler(casa, "SELECT * FROM sd_selos WHERE cancelado_em IS NULL ORDER BY id")
    assert len(selos) == 1 and selos[0]["ato_id"] == suspensa["id"]


def _certidao_do_protesto(b: Balcao, pid: int):
    return b.post("/protesto/certidoes/emitir",
                  {"nome": INTERESSADO, "documento": "000.000.001-91", "anos": "5",
                   "protocolo_id": str(pid)})


def test_protesto_a_certidao_so_sela_com_o_item_pago(casa, aparelho):
    """Protesto — certidão por nome (item 17.5.1). O item do protocolo NÃO
    PAGO não cobre o selo: a certidão é cancelada; quitado no caixa e com o
    protocolo em atendimento, ela sai selada (CN-MA art. 881, § 1º, e a ordem
    do oficial de 19/10/2026)."""
    b = _balcao_com_casa(casa)
    pid = abrir_protocolo(b, atribuicao="PROTESTO")
    acrescentar(b, pid, 990106)
    t = _texto_da_tela(_certidao_do_protesto(b, pid).get_data(as_text=True))
    assert "Certidão NÃO emitida" in t, t[-500:]
    assert all(c["cancelada"] for c in _ler(casa, "SELECT * FROM pt_certidoes ORDER BY id"))
    assert not _selos(casa, "pt_certidoes")
    abrir_caixa(b)
    quitar_tudo(b, pid)
    numero = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))["numero"]
    b.post("/selo/cobertura/atender", {"protocolo": numero})
    _certidao_do_protesto(b, pid)
    ultima = _um(casa, "SELECT * FROM pt_certidoes ORDER BY id DESC LIMIT 1")
    assert not ultima["cancelada"], "a certidão paga foi cancelada"
    selos = _selos(casa, "pt_certidoes")
    assert len(selos) == 1 and selos[0]["ato_id"] == ultima["id"]
    assert [c["forma"] for c in _coberturas(casa, "pt_certidoes")] == ["ITEM_PAGO"]


def _registro_rtd(casa) -> int:
    with casa["db"].transaction() as con:
        bd = banco(con)
        rid = int(bd.escrever(
            """INSERT INTO rg_registros (atribuicao, serie, numero, requerente_nome,
                   situacao, origem, criado_em, teor)
               VALUES (4, 'TD_B', 1508, 'EMPRESA DE EXEMPLO LTDA', 'ATIVO', 'MANUAL',
                       '2026-10-20T09:00:00', 'Teor do registro, reproduzido do livro.')
               RETURNING id""")[0]["id"])
        bd.escrever(
            """INSERT INTO rg_atos (registro_id, tipo, data_ato, teor, folha, origem,
                                    criado_em)
               VALUES (%s, 'REGISTRO', '2026-09-17', 'Teor do registro, reproduzido do
               livro.', '10', 'MANUAL', '2026-10-20T09:00:00')""", (rid,))
    return rid


def _certidao_do_rtd(b: Balcao, rid: int, pid: int | None):
    dados = {"requerente": "EMPRESA DE EXEMPLO LTDA"}
    if pid:
        dados["protocolo_id"] = str(pid)
    return b.post(f"/atribuicoes/certidoes/RCPJ_RTD/{rid}", dados)


def test_rtd_a_certidao_com_o_item_pago_sai_selada(casa, aparelho):
    """RTD/RCPJ — certidão (item 15.10.1), com o protocolo PAGO desde o começo."""
    b = _balcao_com_casa(casa)
    rid = _registro_rtd(casa)
    pago = pagar_e_atender(b, atribuicao="RTD", servico=990107, atender=False)
    _certidao_do_rtd(b, rid, pago["pid"])
    certidoes = _ler(casa, "SELECT * FROM at_certidoes ORDER BY id")
    assert len(certidoes) == 1 and not certidoes[0]["cancelada"]
    selos = _selos(casa, "at_certidoes")
    assert len(selos) == 1 and selos[0]["ato_id"] == certidoes[0]["id"]


def test_rtd_a_certidao_paga_depois_da_recusa_sai_selada(casa, aparelho):
    """A certidão pedida com o item AINDA NÃO PAGO é cancelada (certo), e
    levava o item consigo: quitado e pedida de novo, a certidão não achava
    item nenhum e saía EMITIDA, SEM SELO e sem aviso (CN-MA art. 130, § 2º, e
    art. 155). Consertado no LD06: a certidão cancelada devolve o item ao
    protocolo (`caixa_protocolo.soltar_itens_do_ato`)."""
    b = _balcao_com_casa(casa)
    rid = _registro_rtd(casa)
    pid = abrir_protocolo(b, atribuicao="RTD")
    acrescentar(b, pid, 990107)
    _certidao_do_rtd(b, rid, pid)
    assert all(c["cancelada"] for c in _ler(casa, "SELECT * FROM at_certidoes ORDER BY id"))
    abrir_caixa(b)
    quitar_tudo(b, pid)
    _certidao_do_rtd(b, rid, pid)
    ultima = _um(casa, "SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert not ultima["cancelada"]
    selos = _selos(casa, "at_certidoes")
    assert len(selos) == 1 and selos[0]["ato_id"] == ultima["id"]


def test_protesto_o_protocolo_escolhido_na_certidao_basta_quando_o_item_esta_pago(
        casa, aparelho):
    """O protocolo escolhido no formulário da certidão dava o código ao
    envelope, mas não ligava o item à certidão: com o item PAGO, a trava
    respondia «Ligar o ato a um protocolo do balcão» a quem acabou de
    escolher o protocolo, e a certidão era cancelada. Consertado no LD06: a
    certidão do Protesto liga o item antes do selo, como a do RTD."""
    b = _balcao_com_casa(casa)
    pago = pagar_e_atender(b, atribuicao="PROTESTO", servico=990106, atender=False)
    _certidao_do_protesto(b, pago["pid"])
    ultima = _um(casa, "SELECT * FROM pt_certidoes ORDER BY id DESC LIMIT 1")
    assert ultima and not ultima["cancelada"]


def test_rtd_o_protocolo_sem_item_disponivel_nao_deixa_a_certidao_sair_sem_selo(
        casa, aparelho):
    """A segunda certidão pedida com o MESMO protocolo, cujo item a primeira já
    usou, saía EMITIDA e SEM SELO, calada: `_selar_a_certidao_rtdpj` não
    achava item e devolvia vazio. Agora ela é cancelada e a tela diz que o
    protocolo não tem item disponível — nenhum ato sujeito a selo se expede
    sem ele (LD06; CN-MA art. 130, § 2º)."""
    b = _balcao_com_casa(casa)
    rid = _registro_rtd(casa)
    pago = pagar_e_atender(b, atribuicao="RTD", servico=990107, atender=False)
    _certidao_do_rtd(b, rid, pago["pid"])
    t = _texto_da_tela(_certidao_do_rtd(b, rid, pago["pid"]).get_data(as_text=True))
    assert "Certidão NÃO emitida" in t and "não tem item disponível" in t, t[-600:]
    certidoes = _ler(casa, "SELECT * FROM at_certidoes ORDER BY id")
    assert [bool(c["cancelada"]) for c in certidoes] == [False, True]
    assert len(_selos(casa, "at_certidoes")) == 1
    # a primeira continua dona do item: a segunda, cancelada, não o soltou
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s", (pago["item"]["id"],))
    assert (item["usado_por_tabela"], item["usado_por_ato_id"]) == (
        "at_certidoes", certidoes[0]["id"])


def test_notas_a_certidao_cancelada_devolve_o_item_ao_protocolo(casa, monkeypatch):
    """O mesmo defeito do RTD, na certidão das Notas: ela também liga os itens
    13.12/13.13 do protocolo antes do selo, e a certidão cancelada levava o
    item consigo — o pedido seguinte não o achava. Cancelada, ela o devolve
    (LD06; CN-MA art. 130, § 2º)."""
    import ato_selado as AS
    import certidao_folhas as CF
    monkeypatch.setattr(CF, "decidir_folhas_antes_de_emitir", lambda **k: 1)
    monkeypatch.setattr(AS, "selar_o_ato_lavrado",
                        lambda *a, **k: {"selado": False, "motivo": "aparelho fora do ar"})
    casa["db"].set_settings({"selo_tabela_custas_em": "20260101"})
    b = _balcao_com_casa(casa)
    pid = abrir_protocolo(b, atribuicao="NOTAS")
    with casa["db"].transaction() as con:
        item_id = banco(con).escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                                              quantidade, valor_total)
               VALUES (%s, 'Certidão das Notas, de ensaio', '13.12.1', 1, '20,00')
               RETURNING id""", (pid,))[0]["id"]
    t = _texto_da_tela(b.post("/notas/certidoes/emitir",
                              {"nome": "NINGUÉM DE TAL", "protocolo_id": str(pid)})
                       .get_data(as_text=True))
    assert "NÃO emitida" in t, t[-500:]
    assert all(c["cancelada"] for c in _ler(casa, "SELECT * FROM nt_certidoes ORDER BY id"))
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s", (item_id,))
    assert item["usado_em"] is None and item["usado_por_ato_id"] is None


def test_o_selo_do_item_pago_pelo_usar_nao_debita_o_deposito_outra_vez(casa, aparelho,
                                                                       monkeypatch):
    """O item que o «usar» quitou é item PAGO para a trava do selo: a certidão
    sai selada pela cobertura do item, e o depósito não é debitado de novo
    pelo quadro «Selo e caixa» — um pagamento, um débito (LD06; CN-MA art.
    202 e art. 130, § 2º)."""
    import ri_web
    monkeypatch.setattr(ri_web.CFOLHAS, "decidir_folhas_antes_de_emitir", lambda **k: 1)
    mid = _matricula(casa)
    b = _balcao_com_casa(casa)
    abrir_caixa(b)
    pid = abrir_protocolo(b, atribuicao="RI")
    acrescentar(b, pid, 990105)
    numero = _um(casa, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))["numero"]
    _deposito(b, "100,00")
    d = _um(casa, "SELECT * FROM cx_depositos ORDER BY id DESC LIMIT 1")
    b.post("/caixa/depositos", {"acao": "usar", "deposito_id": str(d["id"]),
                                "valor_usar": _total(SERVICOS[4]), "protocolo": numero})
    b.post("/selo/cobertura/atender", {"protocolo": numero})
    b.post(f"/registro-imoveis/{mid}/certidao",
           {"tipo": "INTEIRO_TEOR", "fonte_corpo": "TEXTO", "requerente": INTERESSADO})
    ultima = _um(casa, "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1")
    assert ultima and not ultima["cancelada"], "a certidão paga pelo depósito foi cancelada"
    selos = _ler(casa, "SELECT * FROM sd_selos WHERE cancelado_em IS NULL ORDER BY id")
    assert len(selos) == 1 and selos[0]["ato_id"] == ultima["id"]
    assert [c["forma"] for c in _coberturas(casa, "ri_certidoes")] == ["ITEM_PAGO"]
    d = _um(casa, "SELECT * FROM cx_depositos WHERE id = %s", (d["id"],))
    assert d["saldo"] == _r(10000 - _c(_total(SERVICOS[4])))
    assert len(_ler(casa, "SELECT id FROM cx_deposito_usos WHERE deposito_id = %s "
                          "ORDER BY id", (d["id"],))) == 1


# ================================== 10. gratuidade: sela sem caixa, e a barra


def _casamento(casa) -> int:
    with casa["db"].transaction() as con:
        bd = banco(con)
        aid = int(bd.escrever(
            """INSERT INTO rc_assentos (serie, especie, numero, matricula, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_B', 'CASAMENTO', 111, '000000015519971000111270020385 79',
                       'NUBENTE UM / NUBENTE DOIS', '2010-05-03', '2010-05-03',
                       'ATIVO', 'EOFICIO', '2026-10-20T09:00:00') RETURNING id""")[0]["id"])
        bd.escrever(
            """INSERT INTO rc_atos (assento_id, tipo, folha, numero_ordem, rotulo,
                                    data_ato, origem, criado_em)
               VALUES (%s, 'REGISTRO', 13, 111, '13', '2010-05-03', 'EOFICIO',
                       '2026-10-20T09:00:00')""", (aid,))
        for papel, nome in (("NUBENTE1", "NUBENTE UM DE EXEMPLO"),
                            ("NUBENTE2", "NUBENTE DOIS DE EXEMPLO")):
            bd.escrever("""INSERT INTO rc_pessoas (assento_id, papel, nome, origem, criado_em)
                           VALUES (%s, %s, %s, 'EOFICIO', '2026-10-20T09:00:00')""",
                        (aid, papel, nome))
    return aid


BARRA = "ato(s) gratuito(s) sem o comprovante"


def test_rcpn_o_selo_gratuito_sai_sem_caixa_e_a_barra_cobra_o_comprovante(casa, aparelho):
    """RCPN — averbação do CPF, gratuita por lei. O selo ISENTO sai sem
    protocolo nem pagamento («geralmente temos o comprovante só depois que o
    ato é praticado» — o oficial, 19/10/2026), e quem obteve o selo fica com a
    barra no topo de toda tela até guardar UM PDF com o comprovante e a
    certidão (CN-MA art. 133: selo de categoria «isento»; LRP art. 30, § 2º e
    CNN art. 239, § 5º: a declaração do interessado)."""
    aid = _casamento(casa)
    b = _balcao_com_casa(casa)
    t = _texto_da_tela(b.post(f"/rcpn/{aid}/averbar-cpf",
                        {"cpf": "000.000.045-02", "papel": "NUBENTE1"}).get_data(as_text=True))
    assert "averbado gratuitamente" in t, t[-400:]
    assert not _ler(casa, "SELECT id FROM cx_protocolos ORDER BY id"), \
        "o selo gratuito pediu protocolo"
    selos = _ler(casa, "SELECT * FROM sd_selos WHERE cancelado_em IS NULL ORDER BY id")
    assert len(selos) == 1 and selos[0]["obtido_por"] in (ESCREVENTE, "elisa")
    # O aparelho de verdade escreve «Selo Isento» no texto do selo isento — é
    # por ele que a casa sabe que o ato é gratuito (`gratuidade_comprovante`).
    # O de mentira devolve sempre o mesmo texto: aqui ele ganha a marca.
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE sd_selos SET texto = texto || ' — Selo Isento' "
                            "WHERE id = %s", (selos[0]["id"],))
    assert BARRA in _texto_da_tela(b.texto("/caixa/protocolos"))
    r = b.c.post(f"/gratuidades/comprovantes/{selos[0]['id']}",
                 data={"csrf_token": b.tok, "fundamento": "ISENCAO_LEGAL",
                       "arquivo": (io.BytesIO(b"%PDF-1.4\n% comprovante de ensaio\n"),
                                   "comprovante_e_certidao.pdf")},
                 content_type="multipart/form-data", follow_redirects=True)
    assert "1 comprovante(s) guardado(s)" in _texto_da_tela(r.get_data(as_text=True))
    assert BARRA not in _texto_da_tela(b.texto("/caixa/protocolos"))


def test_marcar_isento_sem_o_motivo_nao_escapa_da_trava_do_selo_pago(casa, aparelho,
                                                                    monkeypatch):
    """A certidão do RI marcada isenta SEM o motivo não vira selo gratuito —
    senão o caminho da gratuidade seria a porta de saída da trava. A isenção
    se declara com o fundamento (CN-MA art. 133; art. 463, § 1º)."""
    import ri_web
    monkeypatch.setattr(ri_web.CFOLHAS, "decidir_folhas_antes_de_emitir", lambda **k: 1)
    mid = _matricula(casa)
    b = _balcao_com_casa(casa)
    b.post(f"/registro-imoveis/{mid}/certidao",
           {"tipo": "INTEIRO_TEOR", "fonte_corpo": "TEXTO", "requerente": INTERESSADO,
            "isento": "1", "motivo_isencao": ""})
    assert not _ler(casa, "SELECT id FROM sd_selos WHERE cancelado_em IS NULL ORDER BY id")


def _atendido(casa):
    linha = _um(casa, "SELECT protocolo_id FROM cx_atendimento ORDER BY desde DESC LIMIT 1")
    return linha["protocolo_id"] if linha else None


def test_o_protocolo_escolhido_em_qualquer_tela_vira_o_atendimento(casa):
    """22/10/2026, ordem do oficial: o protocolo pago escolhido vale em TODAS
    as atribuições. O campo `protocolo_selo` (a macro `_protocolo_do_selo`),
    mandado por QUALQUER tela, vira o «em atendimento» antes de a rota rodar
    — o `before_request` do selo e caixa —, e a cobertura acha o item ali sem
    a rota da atribuição ter mudado. A rota usada aqui recusa o pedido (400),
    e mesmo assim o atendimento já foi gravado: é a prova de que vem antes."""
    b = _balcao_com_casa(casa)
    pid = abrir_protocolo(b, atribuicao="RCPN")
    b.post("/selo/cobertura/vincular", {"protocolo_selo": str(pid)})
    assert _atendido(casa) == pid
    rastro = _um(casa, "SELECT details FROM audit_logs WHERE action = "
                       "'SELO_PROTOCOLO_EM_ATENDIMENTO' ORDER BY id DESC LIMIT 1")
    assert rastro and "selo_cobertura_vincular" in rastro["details"]


def test_o_protocolo_do_quadro_de_cobranca_tambem_vira_o_atendimento(casa):
    """O quadro de cobrança (`_cobrar.html`) já pede o protocolo: com a marca
    `protocolo_do_quadro`, ele vale para a cobertura do selo. Sem a marca, um
    `protocolo_id` qualquer NÃO mexe no atendimento — noutras telas ele é a
    prenotação do RI, e não um protocolo do caixa."""
    b = _balcao_com_casa(casa)
    pid = abrir_protocolo(b, atribuicao="RTD")
    b.post("/selo/cobertura/vincular", {"protocolo_id": str(pid)})
    assert _atendido(casa) is None, "protocolo_id sem a marca mexeu no atendimento"
    b.post("/selo/cobertura/vincular", {"protocolo_id": str(pid),
                                        "protocolo_do_quadro": "1"})
    assert _atendido(casa) == pid


def test_guardar_o_rascunho_nao_muda_o_protocolo_em_atendimento(casa):
    """O rascunho leva o protocolo marcado na tela, para ela voltar com ele. Mas rascunho não é ato: quem passa a
    atender o protocolo é o envio do ato, e não o papel de anotação (31/10/2026)."""
    b = _balcao_com_casa(casa)
    pid = abrir_protocolo(b, atribuicao="RTD")
    b.post("/rascunhos/salvar", {"_tela": "rcpj_rtd_registro_novo", "_titulo": "Registro", "requerente_nome": "ANA EXEMPLO",
                                 "protocolo_id": str(pid), "protocolo_do_quadro": "1"})
    assert _atendido(casa) is None, "guardar o rascunho mexeu no atendimento"
    guardado = _um(casa, "SELECT dados_json FROM rascunhos_de_tela ORDER BY id DESC LIMIT 1")
    assert str(pid) in guardado["dados_json"], "o protocolo marcado tem de voltar com a tela"


def test_o_quadro_de_cobranca_leva_a_marca_do_protocolo():
    fonte = (Path(__file__).resolve().parent.parent / "templates" / "_cobrar.html"
             ).read_text(encoding="utf-8")
    assert 'name="protocolo_do_quadro"' in fonte and 'name="protocolo_id"' in fonte
