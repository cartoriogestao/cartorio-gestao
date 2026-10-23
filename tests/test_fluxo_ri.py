"""DO PROTOCOLO À CERTIDÃO, NO REGISTRO DE IMÓVEIS — LT03, 20/10/2026.

O PEDIDO DO OFICIAL, nas palavras dele:

    «quero que seja possível do protocolo à certidão. Minha maior preocupação
     é que TODOS os atos precisam ter uma certidão adequada» — e depois:
    «TERMO E CERTIDÃO».

COMO ESTE ARQUIVO ANDA
    PELAS TELAS, como o balcão anda: cliente de teste do Flask, login, CSRF de
    cada tela, e os mesmos POSTs que os formulários mandam. Nada de linha
    gravada à mão no meio do caminho — o que o teste monta direto no banco é
    só o que a CASA já tem antes de abrir a porta (a tabela de custas do
    TJMA, quem trabalha aqui e a numeração do Livro 2 a partir do 4.100, que
    é o intervalo que este sistema lavra: abaixo de 4.015 é acervo).

    Cada ato passa pelas mesmas etapas:
        protocolo geral no caixa → itens da tabela → pagamento (ou gratuidade
        com o PDF) → «estou atendendo este protocolo» → prenotação no Livro 1
        → prática do ato → selo → TERMO no livro (a ficha .odt) → CERTIDÃO.

O SELADOR É O FALSO DA CASA (`selador_falso.py`, TLS de verdade), com UMA
    diferença, e ela é a razão deste arquivo ter o seu: a etiqueta. O falso
    de sempre devolve «Poder Judiciário – TJMA. Selo: X» e mais nada; o de
    verdade devolve o ato, a data e a hora, as partes, o total, os
    emolumentos e cada fundo, e «Selo Isento» quando é gratuito (medido em
    25.839 selos, `selo.py`). Sem isso não há como conferir o que a Lei
    6.015/1973, art. 14, parágrafo único, exige — «o valor correspondente às
    custas (...) constará, obrigatoriamente, do próprio documento» —, porque
    é da etiqueta que o carimbo tira os valores. Aqui o aparelho devolve a
    etiqueta naquele formato, com os valores da tabela de 2026
    (`custas_reais.json`) do item que o envelope pediu.

O QUE CADA TESTE CONFERE NO TERMO E NA CERTIDÃO
    Os elementos que a lei e as normas exigem, cada um com o artigo ao lado:
    Lei 6.015/1973 (LRP), Código Nacional de Normas (Prov. CNJ 149/2023) e o
    Código de Normas Extrajudicial do MA (Prov. COGEX 28/2026, «CN-MA»). E o
    que não pode sobrar: campo vazio, «None», marcador de modelo e texto
    repetido. O que o código não cumpre está marcado `xfail(strict=True)` com
    o defeito escrito — a asserção não se afrouxa para passar.

DADOS
    Só os fictícios da casa (`docs/AGENTES.md`): «Mario Exemplo dos Santos» é
    o oficial, «Carla Exemplo» a escrevente, «Pedro Exemplo dos Santos» e
    «Beatriz Exemplo de Souza» as partes, «Cidade Exemplo» o lugar, CNS
    000000 e os CPF/CNPJ de `fixtures/anti_vazamento/documentos_ficticios.txt`.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from datetime import date, datetime
from html import unescape
from pathlib import Path
from urllib.parse import urlsplit

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco  # noqa: E402
from caixa_schema import reais  # noqa: E402

SENHA = "Senha#12345"
OFICIAL = {"login": "oficial", "nome": "MARIO EXEMPLO DOS SANTOS",
           "funcao": "Oficial Registrador", "papel": "ADMIN"}
ESCREVENTE = {"login": "carla", "nome": "CARLA EXEMPLO",
              "funcao": "Escrevente Autorizada", "papel": "USER"}

# A serventia de teste completa — o que a tela Configurações → Serventia
# guarda. O que `conftest.SERVENTIA_DE_TESTE` já traz (nome, CNS, cidade,
# registrador, substituta) não se repete aqui.
SERVENTIA = {
    "serventia_cnpj": "00.000.001/0000-55",
    "serventia_telefone": "(99) 3000-0000",
    "serventia_endereco": "Rua Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "serventia_email": "contato@serventia.exemplo",
    "serventia_titular": "Mario Exemplo dos Santos",
    "selo_tabela_custas_em": "2026-01-01",
}

PRIMEIRA_MATRICULA = 4100      # o sistema lavra de 4.015 em diante

# As partes: duas pessoas, documentos da lista dos fictícios.
VENDEDOR = {"nome": "PEDRO EXEMPLO DOS SANTOS", "cpf": "00000000191",
            "cpf_fmt": "000.000.001-91",
            "qualificacao": ("brasileiro, solteiro, maior, lavrador, residente e "
                             "domiciliado na Rua Exemplo, 10, Centro, Cidade "
                             "Exemplo/MA")}
COMPRADORA = {"nome": "BEATRIZ EXEMPLO DE SOUZA", "cpf": "00000000272",
              "cpf_fmt": "000.000.002-72",
              "qualificacao": ("brasileira, solteira, maior, professora, "
                               "residente e domiciliada na Rua Exemplo, 20, "
                               "Centro, Cidade Exemplo/MA")}

REAIS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
_TABELA = {e["tj"]: e for e in REAIS["valores_2026"]}
# O item da tabela → o número do serviço no E-Ofício (`cx_servicos.codigo`),
# que é o que a busca da ficha do protocolo devolve no `name="servico"`.
SERVICO = {tj: int(e["s"]) for tj, e in _TABELA.items()}
ITENS_DA_CASA = ("16.1", "16.2", "16.3.14", "16.4", "16.8", "16.22.2",
                 "16.24.1", "16.24.2", "16.24.4", "16.24.4.1", "16.25.7", "16.39")


# =============================================== o aparelho com a etiqueta


def _centavos_do_item(codigo: str, quantidade: int) -> dict | None:
    e = _TABELA.get(codigo)
    if not e:
        return None
    fundos = {k: int(round(e[k] * 100)) * quantidade
              for k in ("emol", "ferc", "fadp", "femp", "ferrfis")}
    fundos["total"] = sum(fundos.values())
    return fundos


def _percorrer(valor):
    if isinstance(valor, dict):
        for k, v in valor.items():
            yield k, v
            yield from _percorrer(v)
    elif isinstance(valor, list):
        for v in valor:
            yield from _percorrer(v)


def _prefixo(caminho: str, codigo: str) -> str:
    """O tipo do selo, como o TJMA o escreve (`selo.PREFIXOS`)."""
    if codigo == "16.39":
        return "ARQUIV"
    if codigo.startswith("16.25"):
        return "BUSCAS"
    if codigo.startswith("16.24.4"):
        return "CERINT"
    if codigo.startswith("16.24"):
        return "CERIMV"
    for pedaco, prefixo in (("prenotacao", "PRENOT"), ("subdivisao", "MATRIC"),
                            ("com-valor", "REGAVD"), ("sem-valor", "AVESVD")):
        if pedaco in caminho:
            return prefixo
    return "REGTOR"


def _etiqueta(numero: str, envelope: dict) -> str:
    """O texto que o aparelho de verdade devolve, no formato medido."""
    import ato_selado as AS
    codigo = AS.codigo_do_envelope(envelope) or ""
    achados = dict(_percorrer(envelope))
    try:
        quantidade = max(1, int(achados.get("quantidade") or 1))
    except (TypeError, ValueError):
        quantidade = 1
    partes = [str(p.get("nome") or "").strip()
              for k, v in _percorrer(envelope) if k == "parteAto"
              for p in (v or []) if isinstance(p, dict)]
    pedacos = [f"Poder Judiciário – TJMA. Selo: {numero}",
               datetime.now().strftime("%d/%m/%Y %H:%M:%S"),
               f"Ato: {codigo}"]
    if any(partes):
        pedacos.append("Parte(s): " + ", ".join(p for p in partes if p))
    texto = ", ".join(pedacos)
    valores = _centavos_do_item(codigo, quantidade)
    if valores:
        texto += (f", Total R$ {reais(valores['total'])} "
                  f"Emol R$ {reais(valores['emol'])} "
                  f"FERC R$ {reais(valores['ferc'])} "
                  f"FADEP R$ {reais(valores['fadp'])} "
                  f"FEMP R$ {reais(valores['femp'])} "
                  f"FERRFIS R$ {reais(valores['ferrfis'])}")
    if achados.get("isento") is True:
        texto += " Selo Isento"
    return texto + " Consulte em https://selo.tjma.jus.br"


def _selador_com_etiqueta():
    """O `SeladorFalso` da casa, devolvendo a etiqueta inteira.

    É o MESMO servidor (TLS, token, SID → mesmo selo): só a resposta do selo
    ganha o tipo no prefixo e o texto completo. O número continua saindo do
    contador dele, e por isso o mesmo SID continua dando o mesmo selo.
    """
    from selador_falso import SeladorFalso

    class SeladorComEtiqueta(SeladorFalso):
        def __init__(self, **kw):
            super().__init__(**kw)
            base = self.http.RequestHandlerClass

            class Mao(base):
                def do_POST(self):                         # noqa: N802
                    tamanho = int(self.headers.get("Content-Length") or 0)
                    bruto = self.rfile.read(tamanho) if tamanho else b""
                    self._lido = (self.path.partition("?")[0], bruto)
                    self.rfile = io.BytesIO(bruto)
                    super().do_POST()

                def _responder(self, status, corpo):
                    caminho, bruto = getattr(self, "_lido", ("", b""))
                    resumos = (corpo.get("resumos")
                               if isinstance(corpo, dict) else None)
                    if status == 200 and resumos:
                        try:
                            envelope = json.loads(bruto.decode("utf-8") or "{}")
                        except ValueError:
                            envelope = {}
                        import ato_selado as AS
                        codigo = AS.codigo_do_envelope(envelope) or ""
                        for r in resumos:
                            sequencia = re.sub(r"\D", "", r["numeroSelo"])[-11:]
                            r["numeroSelo"] = (f"{_prefixo(caminho, codigo)}"
                                               f"000000TESTE{sequencia:0>11}")
                            r["textoSelo"] = _etiqueta(r["numeroSelo"], envelope)
                    super()._responder(status, corpo)

            self.http.RequestHandlerClass = Mao

    return SeladorComEtiqueta


# =============================================== a bancada


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _entrar(app, quem: dict):
    c = app.test_client()
    tela = c.get("/login").get_data(as_text=True)
    c.post("/login", data={"username": quem["login"], "password": SENHA,
                           "csrf_token": _token(tela)}, follow_redirects=True)
    return c


def _clicar(c, tela: str, alvo: str, **campos):
    """O botão da tela: POST com o token dela, seguindo para onde ele leva."""
    token = _token(c.get(tela).get_data(as_text=True))
    return c.post(alvo, data={"csrf_token": token, **campos},
                  follow_redirects=True).get_data(as_text=True)


def _clicar_sem_seguir(c, tela: str, alvo: str, **campos):
    """O botão que leva a um PAPEL: a resposta do POST, sem seguir. O papel
    sai em PDF onde há LibreOffice, e PDF não se lê como texto."""
    token = _token(c.get(tela).get_data(as_text=True))
    return c.post(alvo, data={"csrf_token": token, **campos})


def _destino_em_texto(c, r) -> str:
    """Para a mensagem de falha: aonde o botão levou e, se foi a uma TELA, o
    recado dela. O papel não é aberto como texto."""
    if r.status_code not in (301, 302, 303):
        return f"{r.status_code}: {r.get_data(as_text=True)[:900]}"
    seguinte = c.get(r.location)
    if seguinte.mimetype != "text/html":
        return f"{r.status_code} → {r.location} ({seguinte.mimetype})"
    return f"{r.status_code} → {r.location}: {seguinte.get_data(as_text=True)[:900]}"


def _ler(casa, sql: str, params=()) -> list[dict]:
    with casa["db"].connect() as con:
        return [dict(r) for r in banco(con).ler(sql, params)]


def _um(casa, sql: str, params=()) -> dict | None:
    linhas = _ler(casa, sql, params)
    return linhas[0] if linhas else None


def _semear_a_tabela_de_custas(db) -> None:
    """A vigência de 2026 e os itens do RI, tirados da tabela real do TJMA."""
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias(codigo, descricao, vigente, importado_em)
               VALUES (10022, 'Período de 2026', 1, '2026-08-21')
               ON CONFLICT DO NOTHING""")
        for codigo in ITENS_DA_CASA:
            e = _TABELA[codigo]
            bd.escrever(
                """INSERT INTO cx_servicos(codigo, codigo_tj, descricao, ativo)
                   VALUES (%s,%s,%s,1) ON CONFLICT DO NOTHING""",
                (int(e["s"]), codigo, e["descricao"]))
            v = _centavos_do_item(codigo, 1)
            bd.escrever(
                """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s,10022,%s,%s,%s,%s,%s,%s) ON CONFLICT DO NOTHING""",
                (int(e["s"]), reais(v["emol"]), reais(v["ferc"]), reais(v["femp"]),
                 reais(v["fadp"]), reais(v["ferrfis"]), reais(v["total"])))


@pytest.fixture()
def casa(cg_casa, monkeypatch):
    """A serventia aberta para o balcão: gente, tabela, numeração e o selador.

    O APARELHO SOBE COM `protocolo_pago=False` — a bancada de sempre
    (`selador_de_bancada`) monta sozinha um protocolo pago e em atendimento
    por todos, e isso esconderia exatamente o que este arquivo mede: o caixa
    de verdade cobrindo o selo de verdade.
    """
    import selador_falso
    from selador_de_bancada import ligar_o_selador

    db = cg_casa["db"]
    for quem in (OFICIAL, ESCREVENTE):
        db.create_user(quem["login"], quem["nome"], SENHA, quem["papel"])
    with db.transaction() as con:
        bd = banco(con)
        for quem in (OFICIAL, ESCREVENTE):
            bd.escrever("UPDATE users SET funcao=%s WHERE username=%s",
                        (quem["funcao"], quem["login"]))
    db.set_settings(SERVENTIA)
    _semear_a_tabela_de_custas(db)
    monkeypatch.setattr(selador_falso, "SeladorFalso", _selador_com_etiqueta())
    with ligar_o_selador(cg_casa, protocolo_pago=False) as aparelho:
        oficial = _entrar(cg_casa["app"], OFICIAL)
        # A NUMERAÇÃO DO LIVRO 2 É DA CASA, e quem a fixa é o oficial, na tela
        # dele: o próximo número é o 4.100, dentro do intervalo do sistema.
        _clicar(oficial, "/registro-imoveis/numeracao",
                "/registro-imoveis/numeracao", livro="2",
                proximo_numero=str(PRIMEIRA_MATRICULA),
                observacao="Intervalo dos atos lavrados no sistema")
        yield {**cg_casa, "aparelho": aparelho, "oficial": oficial,
               "balcao": _entrar(cg_casa["app"], ESCREVENTE)}


# =============================================== o papel


def _xml_em_texto(xml: str) -> str:
    xml = re.sub(r"<text:(?:line-break|tab)\s*/>", " ", xml)
    xml = re.sub(r"</text:(?:p|h)>", " ", xml)
    return " ".join(unescape(re.sub(r"<[^>]+>", "", xml)).split())


def _texto_do_odt(conteudo: bytes) -> str:
    """O texto do papel, em uma linha: o cabeçalho da página (o timbre mora no
    `styles.xml`, que é onde o ODF guarda o que se repete em toda folha) e o
    corpo (`content.xml`)."""
    with zipfile.ZipFile(io.BytesIO(conteudo)) as z:
        estilos = z.read("styles.xml").decode("utf-8")
        corpo = z.read("content.xml").decode("utf-8")
    cabecalhos = re.findall(r"<style:header>(.*?)</style:header>", estilos, re.S)
    return " ".join(filter(None, [_xml_em_texto(" ".join(cabecalhos)),
                                  _xml_em_texto(corpo)]))


def _papel(c, url: str) -> str:
    """O .odt de uma rota de papel — pedido em .odt, que é o que se arquiva."""
    junta = "&" if "?" in url else "?"
    r = c.get(f"{url}{junta}formato=odt")
    assert r.status_code == 200, f"{url} não devolveu o papel ({r.status_code})"
    assert r.data[:2] == b"PK", f"{url} não devolveu um .odt"
    return _texto_do_odt(r.data)


def _confere(papel: str, elementos, onde: str) -> None:
    """Cada elemento exigido, com o artigo — e a falta diz TODOS de uma vez."""
    def achou(trecho) -> bool:
        if isinstance(trecho, re.Pattern):
            return bool(trecho.search(papel))
        return str(trecho) in papel
    faltam = [f"{porque}: «{getattr(trecho, 'pattern', trecho)}»"
              for trecho, porque in elementos if not achou(trecho)]
    assert not faltam, (f"{onde} sem:\n  - " + "\n  - ".join(faltam)
                        + f"\n--- o papel ---\n{papel}")


def _sem_sobra(texto: str, onde: str) -> None:
    """O que não pode estar em papel assinado: claro, «None», modelo cru."""
    for sobra in ("None", "{{", "}}", "{%", "%}", "[QUALIFICAR", "[INFORMAR",
                  "[DESCREVER", "PREENCHER", "@@ODF", "nan,", "Traceback"):
        assert sobra not in texto, f"{onde}: sobrou «{sobra}» no papel"
    assert not re.search(r"\[[A-ZÇÃÕÉÍÓÚ ]{3,}\]", texto), (
        f"{onde}: sobrou um [CAMPO] do modelo por preencher")


def _uma_vez(texto: str, trecho: str, onde: str) -> None:
    n = texto.count(trecho)
    assert n == 1, f"{onde}: «{trecho[:60]}» aparece {n} vez(es), e não 1"


def _data_por_extenso(d: date) -> str:
    from ri_web import data_por_extenso
    return data_por_extenso(d)


# =============================================== o balcão


def _abrir_o_caixa_do_dia(c) -> None:
    _clicar(c, "/caixa", "/caixa", acao="abrir", saldo_inicial="0,00")


def _protocolo_geral(casa, *, interessado: dict, itens: list[tuple[str, int]],
                     pagar: bool = True) -> dict:
    """O balcão abre o protocolo geral do RI, lança os itens, recebe e o atende.

    É o caminho das telas: «Abrir protocolo» (`/caixa/protocolos`), o item
    achado na tabela pelo número do serviço, «Quitar todos» com o caixa do dia
    aberto, e «Estou atendendo este protocolo» no quadro do selo — é este
    último que diz ao selo pago onde procurar o item (`ato_selado.
    cobrir_o_selo`, LX16).
    """
    c = casa["balcao"]
    html = _clicar(c, "/caixa/protocolos", "/caixa/protocolos", acao="novo",
                   atribuicao="RI", interessado=interessado["nome"],
                   interessado_documento=interessado["cpf"],
                   telefone="(99) 90000-0000")
    assert "aberto" in html, html[:400]
    p = _um(casa, """SELECT id, numero FROM cx_protocolos WHERE interessado=%s
                      ORDER BY id DESC LIMIT 1""", (interessado["nome"],))
    ficha = f"/caixa/protocolos/{p['id']}"
    for codigo, quantidade in itens:
        html = _clicar(c, ficha, f"{ficha}/itens", acao="acrescentar",
                       servico=str(SERVICO[codigo]), quantidade=str(quantidade))
        assert f"Item {codigo} acrescentado" in html, html[:600]
    if pagar:
        if not _um(casa, "SELECT id FROM cx_caixas WHERE operador_nome=%s "
                         "AND situacao='ABERTO' ORDER BY id LIMIT 1",
                   (ESCREVENTE["nome"],)):
            _abrir_o_caixa_do_dia(c)
        html = _clicar(c, ficha, f"{ficha}/itens", acao="quitar_todos",
                       forma_pagamento="DINHEIRO")
        assert "quitado" in html, html[:600]
    html = _clicar(c, "/selo/cobertura", "/selo/cobertura/atender",
                   protocolo=p["numero"])
    assert f"atendendo o protocolo {p['numero']}" in html
    return p


def _prenotar(casa, cx: dict, *, apresentante: dict, natureza: str,
              objeto: str, matricula: str = "", destino: str = "2",
              **extra) -> dict:
    """«Prenotar este título» a partir do protocolo geral (Livro 1-A)."""
    c = casa["balcao"]
    html = _clicar(
        c, f"/registro-imoveis/protocolo?cx={cx['id']}",
        "/registro-imoveis/protocolo", livro_destino=destino,
        cx_protocolo_id=str(cx["id"]), apresentante=apresentante["nome"],
        apresentante_documento=apresentante["cpf"], telefone="(99) 90000-0000",
        natureza_titulo=natureza, documento_descricao=f"Título: {natureza}",
        objeto=objeto, matricula_numero=matricula, codigo_tj="16.1", **extra)
    assert "prenotado em" in html, html[:800]
    p = _um(casa, "SELECT * FROM ri_protocolos ORDER BY id DESC LIMIT 1")
    return p | {"recado": html}


# =============================================== Livro 1 — a prenotação


def test_a_prenotacao_paga_sai_com_selo_e_o_comprovante_traz_o_que_o_livro_1_exige(casa):
    """LRP arts. 175 (número de ordem, data, apresentante, natureza formal do
    título), 182/183 (o número e a data voltam no título), 186 (prioridade) e
    205 (prazo); CN-MA arts. 443, § 2º (documento comprobatório no ato), 444 e
    452 (20 dias úteis); selo no corpo do papel — CN-MA arts. 130, § 2º, e 131;
    emolumentos no próprio documento — LRP art. 14, parágrafo único."""
    cx = _protocolo_geral(casa, interessado=VENDEDOR, itens=[("16.1", 1)])
    p = _prenotar(casa, cx, apresentante=VENDEDOR,
                  natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    assert p["livro"] == "1A" and p["numero"] == 1 and p["situacao"] == "ABERTO"
    assert p["data_prenotacao"] == date.today().isoformat()
    assert p["data_limite"], "a prenotação nasceu sem prazo"
    assert p["selo_prenotacao"], f"a prenotação paga saiu sem selo: {p['recado'][:600]}"
    geral = _um(casa, "SELECT * FROM cx_protocolos WHERE id=%s", (cx["id"],))
    assert geral["ri_protocolo_id"] == p["id"], "o protocolo geral não se ligou à prenotação"
    cobertura = _um(casa, """SELECT forma, item_id FROM cx_selo_coberturas
                              WHERE tabela='ri_protocolos' AND ato_id=%s""", (p["id"],))
    assert cobertura and cobertura["item_id"], "o selo não saiu do item pago"

    papel = _papel(casa["balcao"], f"/registro-imoveis/protocolo/{p['id']}/comprovante")
    _confere(papel, (
            ("COMPROVANTE DE PRENOTAÇÃO", "o papel diz o que é"),
            ("Protocolo nº 1 — Livro 1-A", "número de ordem e livro — LRP art. 175, I"),
            (date.today().strftime("%d/%m/%Y"), "data da apresentação — LRP art. 175, II"),
            (VENDEDOR["nome"], "apresentante — LRP art. 175, III"),
            ("Compra e venda", "natureza formal do título — LRP art. 175, IV"),
            ("Imóvel urbano na Rua Exemplo, 30", "objeto — LRP art. 175, V"),
            ("20 dias úteis", "prazo — LRP art. 205; CN-MA art. 452"),
            ("Ofício Único de Cidade Exemplo/MA", "a serventia"),
            ("CNS 000000", "o CNS da serventia"),
            (p["selo_prenotacao"], "o selo — CN-MA arts. 130 e 131"),
            ("selo.tjma.jus.br", "a consulta do selo — CN-MA art. 132"),
            ("Emol R$ 38,72", "os emolumentos — LRP art. 14, parágrafo único"),
            (ESCREVENTE["nome"], "quem emitiu"),
            (ESCREVENTE["funcao"], "a função de quem emitiu")),
        "comprovante de prenotação")
    _sem_sobra(papel, "comprovante de prenotação")


# =============================================== Livro 2 — abertura e atos

IMOVEL = {"rural_urbano": "U", "logradouro": "Rua Exemplo", "numero_predial": "30",
          "bairro": "Centro", "cidade": "Cidade Exemplo", "uf": "MA",
          "cep": "65000-000", "area_valor": "360,00", "area_unidade": "m2",
          "registro_anterior": "Matrícula 3.900 deste Ofício, de 10/01/2000"}
CONFRONTACOES = ("frente para a Rua Exemplo, 12,00 m; fundos com o lote 31, "
                 "12,00 m; lado direito com o lote 28, 30,00 m; lado esquerdo "
                 "com o lote 32, 30,00 m")


def _abrir_matricula(casa, prenotacao: dict, *, dono: dict = VENDEDOR) -> dict:
    """«Nova matrícula» (Livro 2) e «Selar a abertura», pelas telas."""
    c = casa["balcao"]
    campos = dict(IMOVEL, data_abertura=date.today().isoformat(),
                  proprietario_nome=dono["nome"],
                  proprietario_documento=dono["cpf_fmt"],
                  proprietario_qualificacao=dono["qualificacao"],
                  confrontacoes=CONFRONTACOES)
    html = _clicar(c, "/registro-imoveis/nova", "/registro-imoveis/nova", **campos)
    assert f"Matrícula {PRIMEIRA_MATRICULA} aberta" in html, html[:800]
    m = _um(casa, "SELECT * FROM ri_matriculas WHERE numero=%s",
            (str(PRIMEIRA_MATRICULA),))
    ficha = f"/registro-imoveis/{m['id']}"
    html = _clicar(c, ficha, f"{ficha}/selar-abertura", codigo_tj="16.2",
                   prenotacao=str(prenotacao["numero"]))
    assert "selada" in html, f"a abertura não selou: {html[:900]}"
    return _um(casa, "SELECT * FROM ri_matriculas WHERE id=%s", (m["id"],))


def _teor_do_modelo(casa, matricula_id: int, codigo: str, valores: dict) -> str:
    """O texto que o botão do modelo põe na caixa de teor, com cada [CAMPO]
    trocado pelo que o escrevente digita — como no balcão, campo a campo."""
    r = casa["balcao"].get(f"/registro-imoveis/{matricula_id}/modelo/{codigo}")
    assert r.status_code == 200, r.get_data(as_text=True)[:300]
    teor = json.loads(r.get_data(as_text=True))["teor"]
    for marcador, valor in valores.items():
        # «PREFIXO*» casa o marcador que começa assim (o da qualificação das
        # partes traz a lista inteira do que se qualifica dentro dele).
        if marcador.endswith("*"):
            teor = re.sub(re.escape("[" + marcador[:-1]) + r"[^\]]*\]",
                          lambda _m: valor, teor)
        else:
            teor = teor.replace(f"[{marcador}]", valor)
    for marcador in re.findall(r"\[[^\[\]]{2,120}\]", teor):
        raise AssertionError(f"o teste não preencheu {marcador} do {codigo}")
    return teor


def _item(casa, cx: dict, codigo: str) -> dict:
    return _um(casa, """SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s
                         AND codigo_ato=%s ORDER BY id LIMIT 1""", (cx["id"], codigo))


def _lavrar(casa, matricula: dict, *, tipo: str, teor: str, natureza: str,
            prenotacao: dict | None, cx: dict | None, itens: list[str],
            partes: list[tuple[dict, str]] = (), base_calculo: str = "",
            modelo: str = "", cliente=None, **extra) -> str:
    """«Lavrar novo ato nesta matrícula» — os campos que a ficha manda."""
    c = cliente or casa["balcao"]
    ficha = f"/registro-imoveis/{matricula['id']}"
    campos = {
        "tipo": tipo, "data_ato": date.today().isoformat(),
        "natureza_titulo": natureza, "teor": teor, "modelo_codigo": modelo,
        "protocolo": str(prenotacao["numero"]) if prenotacao else "",
        "prenotacao": "", "protocolo_id": str(cx["id"]) if cx else "",
        "protocolo_item_id": [str(_item(casa, cx, i)["id"]) for i in itens] if cx else [],
        "base_calculo": base_calculo, "emolumentos": "", "cnib_protocolo": "",
        "parte_nome": [p["nome"] for p, _ in partes],
        "parte_documento": [p["cpf_fmt"] for p, _ in partes],
        "parte_papel": [papel for _, papel in partes],
        "parte_qualificacao": [p["qualificacao"] for p, _ in partes],
        "parte_documento_tipo": ["CPF" for _ in partes],
        **extra}
    tela = ficha + (f"?lavrar=1&prenotacao_id={prenotacao['id']}"
                    if prenotacao else "?lavrar=1")
    return _clicar(c, tela, f"{ficha}/atos", **campos)


# As palavras do título da compra e venda — o que o escrevente lê na escritura.
COMPRA_E_VENDA = {
    "DATA DA ESCRITURA": "02 de outubro de 2026",
    "LIVRO": "12-N", "FOLHAS": "45 a 47",
    "TABELIONATO": "Tabelionato de Notas de Cidade Exemplo/MA",
    "PRECO POR EXTENSO E EM ALGARISMOS": "R$ 100.000,00 (cem mil reais)",
    "NUMERO DA GUIA DE ITBI": "2026/000123",
    "DATA DO ITBI": "01 de outubro de 2026",
    "VALOR DO ITBI": "R$ 2.000,00 (dois mil reais)",
    "VALOR PARA EMOLUMENTOS": "R$ 100.000,00",
}


def _compra_e_venda(casa) -> dict:
    """O caminho inteiro de um título: protocolo, pagamento, prenotação,
    abertura selada e o R-1 de compra e venda selado."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    valores = dict(COMPRA_E_VENDA)
    # A prenotação que abriu a matrícula ainda não está ligada a ela (o
    # vínculo nasce no primeiro ato, `amarrar_prenotacao`), e o modelo deixa
    # o marcador: o escrevente escreve a frase, na forma do RI_MINUTA_PROTOCOLO.
    valores["INFORMAR O PROTOCOLO"] = (
        f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}")
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = (
        f"{COMPRADORA['nome']}, {COMPRADORA['qualificacao']}, inscrita no CPF "
        f"sob o nº {COMPRADORA['cpf_fmt']}")
    teor = _teor_do_modelo(casa, m["id"], "R-COMPRA-VENDA", valores)
    html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda",
                   prenotacao=p, cx=cx, itens=["16.3.14"],
                   partes=[(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")],
                   base_calculo="100.000,00", modelo="R-COMPRA-VENDA")
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
              (m["id"],))
    assert ato, f"o R-1 não foi lavrado: {html[:1200]}"
    return {"cx": cx, "prenotacao": p, "matricula": m, "ato": ato, "recado": html,
            "teor": teor}


def test_a_abertura_da_matricula_sela_e_o_termo_traz_os_requisitos_do_art_176(casa):
    """A abertura da matrícula é o primeiro termo do Livro 2. LRP art. 176,
    § 1º, II: 1) número de ordem; 2) data; 3) identificação do imóvel urbano —
    características e confrontações, localização, área, logradouro, número;
    4) proprietário — nome, domicílio, nacionalidade, estado civil,
    profissão e CPF (e CN-MA art. 479, I); 5) registro anterior (CN-MA art.
    479, III: número e data). O CNM (CNN art. 330), o fecho datado e
    subscrito (CN-MA art. 458) e o selo da abertura (CN-MA arts. 130 e 131),
    com os emolumentos do 16.2 (LRP art. 14, parágrafo único)."""
    cx = _protocolo_geral(casa, interessado=VENDEDOR, itens=[("16.1", 1), ("16.2", 1)])
    p = _prenotar(casa, cx, apresentante=VENDEDOR, natureza="Abertura de matrícula",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    assert m["selo_abertura_texto"], "a abertura ficou sem selo"
    assert m["tipo_ficha"] == "ESTRUTURADA" and m["cnm"]

    termo = _papel(casa["balcao"], f"/registro-imoveis/{m['id']}/ficha.odt")
    hoje = date.today()
    _confere(termo, (
            (f"MATRÍCULA Nº {PRIMEIRA_MATRICULA}", "número de ordem — art. 176, § 1º, II, 1"),
            (f"CNM Nº {m['cnm']}", "CNM — CNN art. 330"),
            ("LIVRO Nº 2 - REGISTRO GERAL", "o livro"),
            (hoje.strftime("%d/%m/%Y"), "data — art. 176, § 1º, II, 2"),
            ("Rua Exemplo, nº 30", "logradouro e número — art. 176, § 1º, II, 3, b"),
            ("Centro", "localização (bairro)"),
            ("Cidade Exemplo/MA", "localização (município)"),
            ("360,00 m2", "área — art. 176, § 1º, II, 3, b"),
            (CONFRONTACOES, "confrontações — art. 176, § 1º, II, 3, b"),
            (VENDEDOR["nome"], "proprietário — art. 176, § 1º, II, 4"),
            (VENDEDOR["qualificacao"], "qualificação do proprietário — art. 176, "
                                       "§ 1º, II, 4; CN-MA art. 479, I"),
            (VENDEDOR["cpf"], "CPF do proprietário — art. 176, § 1º, II, 4, a"),
            ("Matrícula 3.900 deste Ofício, de 10/01/2000",
             "registro anterior — art. 176, § 1º, II, 5; CN-MA art. 479, III"),
            ("O referido é verdade e dou fé", "fecho — CN-MA art. 458"),
            (ESCREVENTE["nome"], "quem subscreve — CN-MA art. 458"),
            (m["selo_abertura_texto"], "selo da abertura — CN-MA arts. 130 e 131"),
            ("Emol R$ 91,20", "emolumentos do 16.2 — LRP art. 14, p. ú."),
            ("Ofício Único de Cidade Exemplo".upper(), "a serventia"),
            ("MARIO EXEMPLO DOS SANTOS", "o oficial no timbre")),
        "termo de abertura da matrícula")
    _sem_sobra(termo, "abertura da matrícula")
    _uma_vez(termo, VENDEDOR["qualificacao"], "abertura da matrícula")


def _trecho_do_ato(termo: str, rotulo: str) -> str:
    """O pedaço do termo que é o ato: do rótulo até o fim do carimbo dele."""
    inicio = termo.find(rotulo)
    assert inicio >= 0, f"o termo não traz o ato {rotulo}"
    return termo[inicio:]


def test_o_registro_de_compra_e_venda_sela_e_o_termo_traz_o_art_176_III(casa):
    """O R-1 na matrícula. LRP art. 176, § 1º, III: 1) a data; 2) transmitente
    e adquirente com nome, domicílio, nacionalidade, estado civil, profissão
    e CPF; 3) o título da transmissão; 4) a forma do título, procedência e
    caracterização; 5) o valor. LRP art. 232 (o «R-» com o número de ordem e
    o da matrícula); CN-MA arts. 443, § 1º, e 458 (número e data do
    protocolo no início; datado e subscrito); selo no corpo (CN-MA arts. 130
    e 131) e emolumentos no documento (LRP art. 14, parágrafo único)."""
    f = _compra_e_venda(casa)
    ato, m, p = f["ato"], f["matricula"], f["prenotacao"]
    assert (ato["tipo"], ato["numero"], ato["cancelado"]) == ("R", 1, 0)
    assert ato["selo_texto"], f"o R-1 não selou: {f['recado'][:900]}"
    assert ato["lavrado_nome"] == ESCREVENTE["nome"]
    assert ato["lavrado_titulo"] == ESCREVENTE["funcao"]
    # o selo saiu do item pago e ligado a este ato; a prenotação amarrou-se a ele
    cobertura = _um(casa, """SELECT forma, item_id FROM cx_selo_coberturas
                              WHERE tabela='ri_atos' AND ato_id=%s""", (ato["id"],))
    assert cobertura and cobertura["item_id"] == _item(casa, f["cx"], "16.3.14")["id"]
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s",
               (p["id"],))["ato_id"] == ato["id"]

    termo = _papel(casa["balcao"], f"/registro-imoveis/{m['id']}/ficha.odt")
    rotulo = f"R-01/{PRIMEIRA_MATRICULA}"
    r1 = _trecho_do_ato(termo, rotulo + " –")
    hoje = date.today()
    _confere(r1, (
        (rotulo, "R-, número de ordem e matrícula — LRP art. 232"),
        ("COMPRA E VENDA", "título da transmissão — art. 176, § 1º, III, 3"),
        (f"PROTOCOLO Nº {p['numero']}", "número do protocolo — CN-MA arts. 443, § 1º, e 458"),
        (f"DE {hoje.day:02d} DE", "data do protocolo — CN-MA art. 458"),
        (VENDEDOR["nome"], "transmitente — art. 176, § 1º, III, 2"),
        (COMPRADORA["nome"], "adquirente — art. 176, § 1º, III, 2"),
        (COMPRADORA["qualificacao"], "qualificação do adquirente — art. 176, § 1º, III, 2, a"),
        (COMPRADORA["cpf_fmt"], "CPF do adquirente — art. 176, § 1º, III, 2, a"),
        ("escritura publica lavrada em 02 de outubro de 2026",
         "forma do título e data — art. 176, § 1º, III, 4"),
        ("Livro 12-N", "procedência: livro — art. 176, § 1º, III, 4"),
        ("folhas 45 a 47", "procedência: folhas — art. 176, § 1º, III, 4"),
        ("Tabelionato de Notas de Cidade Exemplo/MA", "procedência — art. 176, § 1º, III, 4"),
        ("R$ 100.000,00 (cem mil reais)", "valor do contrato — art. 176, § 1º, III, 5"),
        ("ITBI", "o tributo da transmissão — CN-MA art. 475"),
        (f"Cidade Exemplo/MA, {_data_por_extenso(hoje)}", "data do ato — art. 176, § 1º, III, 1"),
        ("Dou fé", "o fecho"),
        (f"A {ESCREVENTE['funcao']} ({ESCREVENTE['nome']})",
         "quem subscreve, com a função — CN-MA art. 458"),
        (ato["selo_texto"], "o selo do registro — CN-MA arts. 130 e 131"),
        ("SELO DE REGISTRO", "o carimbo do selo do ato"),
        # o carimbo escreve o valor sem o ponto do milhar («1636,01»)
        (re.compile(r"Emol R\$ 1\.?636,01"), "emolumentos do 16.3.14 — LRP art. 14, p. ú."),
        (p["selo_prenotacao"], "o selo da prenotação que deu origem ao ato")),
        "termo do R-1 (compra e venda)")
    _sem_sobra(r1, "termo do R-1")
    _uma_vez(termo, "escritura publica lavrada em 02 de outubro de 2026", "termo do R-1")


def _certidao(casa, matricula: dict, tipo: str, *, cx: dict, **extra) -> dict:
    """«Emitir certidão» na ficha. Devolve a linha gravada e o papel (.odt)."""
    c = casa["balcao"]
    ficha = f"/registro-imoveis/{matricula['id']}"
    campos = {"tipo": tipo, "fonte_corpo": "TEXTO", "folhas": "",
              "requerente": COMPRADORA["nome"],
              "requerente_documento": COMPRADORA["cpf_fmt"],
              "finalidade": "Para fins de financiamento", "emolumentos": "",
              "protocolo": cx["numero"], "busca_formulario": "1",
              "busca_item": "16.25.9", **extra}
    token = _token(c.get(ficha).get_data(as_text=True))
    r = c.post(f"{ficha}/certidao", data={"csrf_token": token, **campos})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    linha = _um(casa, "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1")
    assert linha and linha["tipo"] == tipo
    recado = c.get(r.headers["Location"].split("?")[0].replace(
        f"/registro-imoveis/certidoes/{linha['id']}.odt", ficha)).get_data(as_text=True)
    assert not linha["cancelada"], (f"a certidão {tipo} saiu cancelada: "
                                    f"{linha['motivo_cancelamento']}")
    papel = _papel(c, f"/registro-imoveis/certidoes/{linha['id']}.odt")
    return {"linha": linha, "papel": papel, "recado": recado}


def _identifica_a_serventia_e_o_selo(cert: dict, *, emol: str) -> list:
    """O que TODA certidão do RI diz: quem certifica, o selo, o valor, a validade."""
    c = cert["linha"]
    return [
        ("Ofício Único de Cidade Exemplo/MA".upper(), "a serventia"),
        ("000000", "o CNS da serventia"),
        ("Mario Exemplo dos Santos", "o oficial"),
        (c["selo_texto"], "o selo da certidão — CN-MA arts. 130 e 131"),
        ("selo.tjma.jus.br", "a consulta do selo — CN-MA art. 132"),
        (emol, "os emolumentos da certidão — LRP art. 14, p. ú."),
        ("30 (trinta) dias", "a validade — CN-MA art. 553"),
        ("na forma do art. 553 do Código de Normas",
         "o artigo vigente da validade — LH13, «14 a»"),
        (COMPRADORA["nome"], "o requerente — CN-MA art. 551"),
        ("Para fins de financiamento", "a finalidade"),
        (ESCREVENTE["nome"], "quem expediu — LRP art. 19 (autenticada)"),
        (ESCREVENTE["funcao"], "a função de quem expediu"),
        (_data_por_extenso(date.today()), "a data da emissão"),
    ]


def test_a_certidao_emitida_antes_do_lh13_reimprime_o_artigo_que_ela_disse(casa):
    """LH13 — o oficial, 21/10/2026, «14 a»: a validade das certidões do RI
    passou a citar o art. 553 do Código de Normas. AS JÁ EMITIDAS NÃO MUDAM:
    o corpo da certidão do Livro 2 é congelado na emissão (com o hash), e a
    segunda via reimprime o corpo gravado — não remonta pelo molde de hoje.

    A certidão «de antes» é a de hoje com o corpo gravado como a casa o
    gravava até o LH13 (art. 53): a segunda via tem de dizer o que ela disse."""
    f = _compra_e_venda(casa)
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.24.4", 1), ("16.24.4.1", 9)])
    cert = _certidao(casa, f["matricula"], "INTEIRO_TEOR", cx=cx)
    assert "na forma do art. 553 do Código de Normas" in cert["papel"]
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE ri_certidoes SET corpo = replace(corpo, %s, %s) WHERE id = %s",
            ("art. 553 do Código", "art. 53 do Código", cert["linha"]["id"]))
    segunda_via = _papel(casa["balcao"],
                         f"/registro-imoveis/certidoes/{cert['linha']['id']}.odt")
    assert "na forma do art. 53 do Código de Normas" in segunda_via, segunda_via
    assert "art. 553" not in segunda_via


def test_a_certidao_de_inteiro_teor_reproduz_o_termo_da_matricula(casa):
    """Inteiro teor é a reprodução de TODO o conteúdo da matrícula — LRP art.
    19, caput e §§ 1º e 11 —, e por isso cada pedaço do termo tem de estar no
    papel: a abertura (art. 176, § 1º, II) e o ato com o seu fecho e o seu
    selo. Com os títulos em aberto mencionados (LRP art. 21; CN-MA art. 553,
    § 4º) e o que identifica a certidão (CN-MA art. 553)."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    termo = _papel(casa["balcao"], f"/registro-imoveis/{m['id']}/ficha.odt")
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.24.4", 1), ("16.24.4.1", 9)])
    cert = _certidao(casa, m, "INTEIRO_TEOR", cx=cx)
    papel = cert["papel"]
    assert cert["linha"]["selo_texto"], cert["recado"][:900]

    rotulo = f"R-01/{PRIMEIRA_MATRICULA}"
    r1_no_termo = _trecho_do_ato(termo, rotulo + " –")
    fecho = re.search(r"Cidade Exemplo/MA, [^.]+\. Dou fé\. [^.]+?\)\.?", r1_no_termo)
    assert fecho, "o termo do R-1 não tem fecho para comparar"
    _confere(papel, [
        ("CERTIDÃO DE INTEIRO TEOR", "a forma — LRP art. 19"),
        (f"MATRÍCULA Nº {PRIMEIRA_MATRICULA}", "a matrícula certificada"),
        ("Livro 2", "o livro"),
        (m["cnm"], "o CNM — CNN art. 330"),
        # a abertura, como o termo a traz
        ("Rua Exemplo, nº 30", "a abertura: o imóvel — art. 176, § 1º, II, 3"),
        (CONFRONTACOES, "a abertura: as confrontações"),
        (VENDEDOR["qualificacao"], "a abertura: o proprietário qualificado"),
        ("Matrícula 3.900 deste Ofício, de 10/01/2000", "a abertura: o registro anterior"),
        (m["selo_abertura_texto"], "a abertura: o selo"),
        # o ato, como o termo o traz
        (rotulo, "o R-1"),
        (f["teor"][-120:], "o teor do R-1, igual ao lavrado"),
        (fecho.group(0), "o fecho do R-1 (data, «dou fé», quem subscreveu)"),
        (f["ato"]["selo_texto"], "o selo do R-1"),
        ("Era o que nela continha", "o encerramento do inteiro teor"),
        ("prenotado", "os títulos prenotados em aberto — CN-MA art. 553, § 4º"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 90,96"),
        "certidão de inteiro teor")
    _sem_sobra(papel, "certidão de inteiro teor")
    _uma_vez(papel, f["teor"][-120:], "certidão de inteiro teor")


# =============================================== os 25 modelos de ato da casa

import ri_modelos_atos as MODELOS_DE_ATO  # noqa: E402

_OPCIONAL = re.compile(r"«[^«»]{2,1500}»", re.S)
_ESCOLHA = re.compile(r"\{([^{}]{2,300})\}")


def _valor_de_exemplo(marcador: str) -> str:
    """O que o escrevente digita no [CAMPO], pela natureza do campo."""
    m = marcador.upper()
    if "QUALIFICAR" in m or "QUALIFICACAO COMPLETA" in m:
        return (f"{COMPRADORA['nome']}, {COMPRADORA['qualificacao']}, inscrita "
                f"no CPF sob o nº {COMPRADORA['cpf_fmt']}")
    if "INFORMAR O PROTOCOLO" in m:
        return f"PROTOCOLO N. 1, DE {date.today().strftime('%d/%m/%Y')}"
    if "DATA" in m:
        return "01 de outubro de 2026"
    if "VALOR" in m or "PRECO" in m:
        return "R$ 100.000,00 (cem mil reais)"
    if "CPF" in m:
        return COMPRADORA["cpf_fmt"]
    if m.startswith("SE ENCERRAMENTO"):
        return ""
    return f"{marcador.split(':')[0].strip().lower()} de exemplo"


def _como_o_balcao_preenche(teor: str) -> tuple[str, list[str]]:
    """O que o escrevente faz no texto que o modelo pôs na caixa de teor:
    tira a cláusula opcional que não se aplica, fica com a primeira opção de
    cada escolha e preenche cada [CAMPO]. Devolve o texto e o que digitou."""
    teor = _OPCIONAL.sub("", teor)

    def escolhe(m):
        lido = MODELOS_DE_ATO._le_escolha(m.group(1))
        return lido[1][0] if lido else m.group(0)
    teor = _ESCOLHA.sub(escolhe, teor)
    digitados = []

    def preenche(m):
        valor = _valor_de_exemplo(" ".join(m.group(1).split()))
        if valor:
            digitados.append(valor)
        return valor
    teor = re.sub(r"\[([^\[\]]{2,160})\]", preenche, teor)
    return " ".join(teor.split()), digitados


@pytest.mark.parametrize("codigo", [m["codigo"] for m in MODELOS_DE_ATO.MODELOS])
def test_cada_modelo_de_ato_da_casa_lavra_sela_e_sai_igual_no_termo_e_na_certidao(
        casa, codigo):
    """Os 25 modelos de `ri_modelos_atos`, pelo mesmo caminho do balcão:
    protocolo pago, prenotação, matrícula aberta, o texto do modelo na caixa
    de teor, lavratura com o item, selo, TERMO (ficha .odt) e CERTIDÃO de
    inteiro teor. No termo: o R-/AV- com o número e a matrícula (LRP art. 232),
    a natureza, o protocolo (CN-MA art. 458), tudo o que se digitou, o fecho
    com quem praticou, o selo e os emolumentos (CN-MA arts. 130/131; LRP art.
    14, p. ú.). Na certidão: o MESMO texto, o fecho e o selo do ato (LRP art.
    19, § 11)."""
    modelo = MODELOS_DE_ATO.por_codigo(codigo)
    tipo = modelo["tipo"]
    item = "16.3.14" if tipo == "R" else "16.22.2"
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), (item, 1),
                                 ("16.24.4", 1), ("16.24.4.1", 9)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza=modelo["natureza"],
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    r = casa["balcao"].get(f"/registro-imoveis/{m['id']}/modelo/{codigo}")
    teor, digitados = _como_o_balcao_preenche(json.loads(r.get_data(as_text=True))["teor"])
    partes = ([(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")]
              if tipo == "R" else [])
    html = _lavrar(casa, m, tipo=tipo, teor=teor, natureza=modelo["natureza"],
                   prenotacao=p, cx=cx, itens=[item], partes=partes,
                   base_calculo="100.000,00" if tipo == "R" else "",
                   modelo=codigo)
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
              (m["id"],))
    assert ato and ato["selo_texto"], f"{codigo} não lavrou com selo: {html[:1500]}"
    rotulo = f"{tipo}-01/{PRIMEIRA_MATRICULA}"
    selo_do_tipo = "SELO DE REGISTRO" if tipo == "R" else "SELO DE AVERBAÇÃO"
    emol = (re.compile(r"Emol R\$ 1\.?636,01") if tipo == "R"
            else "Emol R$ 120,03")

    termo = _trecho_do_ato(_papel(casa["balcao"], f"/registro-imoveis/{m['id']}/ficha.odt"),
                           rotulo + " –")
    # A FICHA TROCA A PRIMEIRA FRASE DO TEOR PELO CABEÇALHO DELA (natureza,
    # protocolo e data — `ri_odt.teor_sem_cabecalho_do_ato`); o que se digitou
    # ali sai no cabeçalho, e o resto do teor sai inteiro.
    import ri_odt
    corpo_no_termo = ri_odt.teor_sem_cabecalho_do_ato(teor, tipo, 1, str(PRIMEIRA_MATRICULA))
    digitados_no_corpo = [d for d in digitados if d in corpo_no_termo]
    fecho = f"Cidade Exemplo/MA, {_data_por_extenso(date.today())}. Dou fé."
    _confere(termo, [
        (rotulo, "o rótulo — LRP art. 232"),
        (modelo["natureza"].upper(), "a natureza do título"),
        (f"PROTOCOLO Nº {p['numero']}", "o protocolo — CN-MA art. 458"),
        (fecho, "a data e o «Dou fé» — CN-MA art. 458"),
        (f"({ESCREVENTE['nome']})", "quem praticou — CN-MA art. 458"),
        (ato["selo_texto"], "o selo — CN-MA arts. 130 e 131"),
        (selo_do_tipo, "o carimbo do selo do ato"),
        (emol, "os emolumentos — LRP art. 14, p. ú."),
    ] + [(d, "o que o escrevente digitou") for d in digitados_no_corpo],
        f"termo do {codigo}")
    _sem_sobra(termo, f"termo do {codigo}")

    cert = _certidao(casa, m, "INTEIRO_TEOR", cx=cx)
    papel = cert["papel"]
    _confere(papel, [
        (rotulo, "o ato certificado"),
        (" ".join(teor.split())[-100:], "o teor do ato, igual ao lavrado"),
        (fecho, "o fecho do ato"),
        (f"({ESCREVENTE['nome']})", "quem praticou o ato"),
        (ato["selo_texto"], "o selo do ato"),
        (cert["linha"]["selo_texto"], "o selo da certidão"),
    ] + [(d, "o que o termo diz") for d in digitados],
        f"certidão de inteiro teor com o {codigo}")
    _sem_sobra(papel, f"certidão com o {codigo}")


# =============================================== as certidões da situação do imóvel

BANCO = {"nome": "BANCO EXEMPLO S.A.", "cpf": "00000010000127",
         "cpf_fmt": "00.000.010/0001-27",
         "qualificacao": ("instituição financeira com sede na Rua Exemplo, 500, "
                          "Centro, Cidade Exemplo/MA")}

HIPOTECA = {"DATA DO TITULO": "05 de outubro de 2026",
            "VALOR POR EXTENSO E EM ALGARISMOS": "R$ 80.000,00 (oitenta mil reais)",
            "PRAZO": "120 meses", "TAXA": "1% ao mês",
            "DATA DE VENCIMENTO": "05 de outubro de 2036",
            "INFORMAR O PROTOCOLO": "", "QUALIFICAR O(S) ADQUIRENTE(S)*": ""}


def _com_hipoteca(casa) -> dict:
    """O R-1 de compra e venda e, por outro título, o R-2 de hipoteca."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cx = _protocolo_geral(casa, interessado=BANCO, itens=[("16.1", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=BANCO, natureza="Hipoteca",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}",
                  matricula=str(PRIMEIRA_MATRICULA))
    r = casa["balcao"].get(f"/registro-imoveis/{m['id']}/modelo/R-HIPOTECA")
    teor = json.loads(r.get_data(as_text=True))["teor"]
    teor = MODELOS_DE_ATO._ESCOLHA.sub(
        lambda x: (MODELOS_DE_ATO._le_escolha(x.group(1)) or ("", [x.group(0)]))[1][0], teor)
    valores = dict(HIPOTECA)
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = (
        f"{BANCO['nome']}, {BANCO['qualificacao']}, inscrito no CNPJ sob o nº "
        f"{BANCO['cpf_fmt']}")
    for marcador, valor in valores.items():
        if marcador.endswith("*"):
            teor = re.sub(re.escape("[" + marcador[:-1]) + r"[^\]]*\]", lambda _m: valor, teor)
        elif valor:
            teor = teor.replace(f"[{marcador}]", valor)
    assert not re.search(r"\[[A-Z][^\]]+\]", teor), teor
    html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Hipoteca", prenotacao=p,
                   cx=cx, itens=["16.3.14"], base_calculo="80.000,00",
                   partes=[(COMPRADORA, "devedor"), (BANCO, "credor")],
                   modelo="R-HIPOTECA")
    r2 = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s AND numero=2", (m["id"],))
    assert r2 and r2["selo_texto"], f"o R-2 (hipoteca) não lavrou: {html[:1200]}"
    return f | {"r2": r2, "teor_r2": teor}


def _pede_certidao(casa, quem: dict = COMPRADORA, itens=(("16.24.4", 1), ("16.24.4.1", 9))):
    return _protocolo_geral(casa, interessado=quem, itens=list(itens))


def test_a_certidao_de_onus_negativa_diz_livre_e_desembaracado(casa):
    """Ônus e ações reais e reipersecutórias (LRP art. 19, § 9º; CN-MA arts.
    553, § 4º, e 558): sem ônus lavrado, «NADA CONSTA» dos dois — e o que
    identifica a certidão (CN-MA art. 553)."""
    f = _compra_e_venda(casa)
    cert = _certidao(casa, f["matricula"], "ONUS", cx=_pede_certidao(casa),
                     onus_formulario="1", resultado_onus="negativa",
                     resultado_acoes="negativa", proprietario_conferido="1")
    _confere(cert["papel"], [
        ("NEGATIVA", "a forma: negativa"),
        ("NADA CONSTA", "a afirmação sobre os ônus"),
        ("LIVRE E DESEMBARAÇADO", "o imóvel livre"),
        ("NÃO CONSTA", "a afirmação sobre as ações reipersecutórias — CN-MA art. 558"),
        (f"MATRÍCULA Nº {PRIMEIRA_MATRICULA}", "a matrícula"),
        ("Rua Exemplo", "o imóvel — LRP art. 19, § 9º"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 90,96"),
        "certidão negativa de ônus")
    _sem_sobra(cert["papel"], "certidão negativa de ônus")


def test_a_certidao_de_onus_positiva_transcreve_a_hipoteca_igual_ao_termo(casa):
    """Com a hipoteca R-2 lavrada, a certidão é POSITIVA e transcreve o ato
    com o rótulo, a natureza, a data e o texto — iguais aos do termo (LRP
    art. 19, § 9º; CN-MA art. 553, § 4º)."""
    f = _com_hipoteca(casa)
    r2 = f["r2"]
    cert = _certidao(casa, f["matricula"], "ONUS", cx=_pede_certidao(casa),
                     onus_formulario="1", resultado_onus="positiva",
                     resultado_acoes="negativa", onus_item=f"ATO:{r2['id']}",
                     proprietario_conferido="1")
    assert cert["linha"]["resultado_onus"] == "POSITIVA"
    _confere(cert["papel"], [
        ("POSITIVA", "a forma: positiva"),
        ("HÁ ÔNUS REAIS", "a afirmação"),
        (f"R-02/{PRIMEIRA_MATRICULA}", "o ato do ônus, pelo rótulo do termo"),
        ("Hipoteca", "a natureza do ônus"),
        (_data_por_extenso(date.today()), "a data do ato"),
        ("R$ 80.000,00 (oitenta mil reais)", "o valor da dívida, como no termo"),
        (BANCO["nome"], "o credor, como no termo"),
        ("NÃO CONSTA", "a afirmação sobre as ações — CN-MA art. 558"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 90,96"),
        "certidão positiva de ônus")
    _sem_sobra(cert["papel"], "certidão positiva de ônus")


def test_a_certidao_de_propriedade_depois_da_venda_afirma_o_comprador(casa):
    """Depois do R-1 de compra e venda, quem é dono é a compradora — e só ela.

    Era `xfail` do LT03 (o transmitente continuava titular e o adquirente não
    entrava: a lavratura tinha a sua própria régua, `startswith('propriet')`);
    consertado no LD03 — a régua é a de `ri_correcoes`, e quem transmite sai
    do quadro. LRP art. 19, § 9º (proprietário vigente); CN-MA art. 553."""
    f = _compra_e_venda(casa)
    cert = _certidao(casa, f["matricula"], "PROPRIEDADE",
                     cx=_pede_certidao(casa, itens=(("16.24.1", 1), ("16.24.2", 9))))
    papel = cert["papel"]
    atual = papel.split("PROPRIETÁRIO(S) ATUAL(IS):", 1)
    assert len(atual) == 2, f"a certidão não diz quem é o proprietário: {papel}"
    dono = atual[1].split(".", 1)[0]
    assert COMPRADORA["nome"] in dono, f"a compradora não é a dona na certidão: {dono}"
    assert VENDEDOR["nome"] not in dono, f"o vendedor continua dono na certidão: {dono}"


def test_a_certidao_de_propriedade_identifica_a_matricula_e_o_imovel(casa):
    """O que a certidão de propriedade traz (LRP art. 19, § 9º; CN-MA art.
    553), medido sem a questão do titular acima: a matrícula, o imóvel, o
    quadro de proprietários, a afirmação e o selo do 16.24.1."""
    f = _compra_e_venda(casa)
    cert = _certidao(casa, f["matricula"], "PROPRIEDADE",
                     cx=_pede_certidao(casa, itens=(("16.24.1", 1), ("16.24.2", 9))))
    _confere(cert["papel"], [
        ("CERTIDÃO DE PROPRIEDADE", "a forma"),
        (f"MATRÍCULA Nº {PRIMEIRA_MATRICULA}", "a matrícula"),
        ("Rua Exemplo", "o imóvel"),
        ("PROPRIETÁRIO(S) ATUAL(IS)", "o quadro dos titulares"),
        ("encontra-se registrada em nome do(s) titular(es)", "a afirmação da propriedade"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 47,84"),
        "certidão de propriedade")
    _sem_sobra(cert["papel"], "certidão de propriedade")


@pytest.mark.parametrize("tipo, titulo", [("DOMINIAL", "CADEIA DOMINIAL"),
                                          ("VINTENARIA", "CERTIDÃO VINTENÁRIA")])
def test_a_cadeia_dominial_e_a_vintenaria_trazem_a_compra_e_venda_do_termo(casa, tipo, titulo):
    """As transmissões de domínio, em ordem, com o ato como o termo o traz."""
    f = _compra_e_venda(casa)
    cert = _certidao(casa, f["matricula"], tipo, cx=_pede_certidao(casa))
    _confere(cert["papel"], [
        (titulo, "a forma"),
        (f"R-01/{PRIMEIRA_MATRICULA}", "a compra e venda, pelo rótulo do termo"),
        ("Compra e venda", "a natureza da transmissão"),
        ("R$ 100.000,00 (cem mil reais)", "o teor do ato, como no termo"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 90,96"),
        f"certidão {tipo.lower()}")
    _sem_sobra(cert["papel"], f"certidão {tipo.lower()}")


@pytest.mark.parametrize("modo", ["PESSOA", "IMOVEL"])
def test_a_certidao_negativa_diz_o_que_se_buscou_e_que_nada_consta(casa, modo):
    """A negativa pelos indicadores (Livros 4 e 5): o parâmetro da busca no
    texto (CN-MA arts. 554, p. ú., e 557), o resultado total (art. 555), a
    finalidade e o requerente (arts. 549, III, e 551), o selo da certidão
    (16.24.1) e o da busca (16.25.7)."""
    _compra_e_venda(casa)
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.24.1", 1), ("16.24.2", 9), ("16.25.7", 1)])
    c = casa["balcao"]
    if modo == "PESSOA":
        busca, tela = "JOAO INEXISTENTE DE EXEMPLO", "/registro-imoveis/indicador-pessoal"
        criterio = busca
    else:
        busca, tela = "Avenida Inexistente, 999", "/registro-imoveis/indicador-real"
        criterio = busca
    # O BOTÃO SEM SEGUIR O REDIRECT (LD14, 21/10/2026). A negativa emitida
    # leva ao papel `.odt`, e onde há LibreOffice o papel sai em PDF: seguir e
    # ler como texto estourava no primeiro byte do PDF (UnicodeDecodeError no
    # servidor). Confere-se o DESTINO, e o teor sai do `.odt` pedido como tal.
    r = _clicar_sem_seguir(c, f"{tela}?busca={busca}", "/registro-imoveis/certidao-negativa",
                           modo=modo, busca=busca, requerente=COMPRADORA["nome"],
                           requerente_documento=COMPRADORA["cpf_fmt"],
                           finalidade="Para fins de financiamento", protocolo=cx["numero"],
                           busca_formulario="1", busca_item="16.25.7")
    linha = _um(casa, "SELECT * FROM ri_certidoes WHERE tipo='NEGATIVA_IMOVEL' ORDER BY id DESC LIMIT 1")
    assert linha and not linha["cancelada"], f"a negativa não saiu: {_destino_em_texto(c, r)}"
    destino = f"/registro-imoveis/certidoes/{linha['id']}.odt"
    assert r.status_code == 302 and urlsplit(r.location).path == destino, (
        f"a negativa não levou ao papel dela: {_destino_em_texto(c, r)}")
    papel = _papel(c, destino)
    cert = {"linha": linha, "papel": papel}
    _confere(papel, [
        ("CERTIDÃO NEGATIVA DE IMÓVEL", "a forma"),
        ("NADA CONSTA", "o resultado — CN-MA art. 555"),
        (criterio, "o parâmetro da busca no texto — CN-MA arts. 554, p. ú., e 557"),
    ] + _identifica_a_serventia_e_o_selo(cert, emol="Emol R$ 47,84"),
        f"certidão negativa ({modo})")
    _sem_sobra(papel, f"certidão negativa ({modo})")
    busca_selada = _um(casa, """SELECT numero FROM sd_selos WHERE tabela='ri_certidoes'
                                 AND ato_id=%s AND numero LIKE 'BUSCAS%%' ORDER BY id""",
                       (linha["id"],))
    assert busca_selada, "a busca paga não saiu com o selo próprio (16.25.7)"


# =============================================== a gratuidade, com o PDF

MOTIVO_REURB = ("O REGISTRO DISPENSA O PAGAMENTO DE EMOLUMENTOS PREVISTO NA "
                "LEI Nº 13.465, DE 2017.")
PDF_DE_EXEMPLO = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
                  b"2 0 obj<</Type/Pages/Kids[]/Count 0>>endobj\ntrailer<</Root 1 0 R>>\n%%EOF\n")


def test_a_averbacao_gratuita_sela_isenta_e_o_pdf_da_gratuidade_fica_no_selo(casa):
    """REURB-S: a prenotação ganha 40 dias e sai isenta, a averbação sai com o
    selo ISENTO e o motivo dentro (CN-MA art. 133; Lei 13.465/2017, art. 13,
    § 1º), sem passar pelo caixa — e o comprovante da gratuidade, em PDF,
    fica amarrado ao selo (LX16), com o fundamento escolhido na lista."""
    cx = _protocolo_geral(casa, interessado=VENDEDOR, itens=[("16.2", 1)])
    p = _prenotar(casa, cx, apresentante=VENDEDOR, natureza="Construção",
                  objeto="Regularização fundiária — Rua Exemplo, 30",
                  reurb_tipo="S")
    assert p["reurb_tipo"] == "S" and p["selo_prenotacao"], p["recado"][:800]
    m = _abrir_matricula(casa, p)
    teor, digitados = _como_o_balcao_preenche(json.loads(casa["balcao"].get(
        f"/registro-imoveis/{m['id']}/modelo/AV-CONSTRUCAO").get_data(as_text=True))["teor"])
    html = _lavrar(casa, m, tipo="AV", teor=teor, natureza="Construção",
                   prenotacao=p, cx=None, itens=[], codigo_tj="16.22.2",
                   isento="1", motivo_isencao=MOTIVO_REURB, modelo="AV-CONSTRUCAO")
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
              (m["id"],))
    assert ato and ato["selo_texto"] and ato["isento"] == 1, html[:1200]
    assert ato["motivo_isencao"] == MOTIVO_REURB
    selo = _um(casa, "SELECT * FROM sd_selos WHERE tabela='ri_atos' AND ato_id=%s",
               (ato["id"],))
    assert "Selo Isento" in selo["texto"]
    # o selo gratuito não passa pelo caixa: nada se cobriu nem se gastou
    assert _um(casa, """SELECT id FROM cx_selo_coberturas WHERE tabela='ri_atos'
                         AND ato_id=%s""", (ato["id"],)) is None

    # o comprovante: a lista do escrevente mostra o selo, e o PDF fica nele
    c = casa["balcao"]
    lista = c.get("/gratuidades/comprovantes").get_data(as_text=True)
    assert selo["numero"] in lista, "o selo isento não apareceu para comprovar"
    token = _token(lista)
    r = c.post(f"/gratuidades/comprovantes/{selo['id']}",
               data={"csrf_token": token, "fundamento": "REURB_S",
                     "arquivo": (io.BytesIO(PDF_DE_EXEMPLO), "declaracao_reurb.pdf")},
               content_type="multipart/form-data", follow_redirects=True)
    assert "comprovante(s) guardado(s)" in r.get_data(as_text=True)
    anexo = _um(casa, """SELECT * FROM attachments WHERE entity_type='SELO_GRATUIDADE'
                          AND entity_id=%s""", (selo["id"],))
    assert anexo and "REURB-S" in anexo["description"]
    # e a pendência some (a tela passa a listá-lo entre os já comprovados)
    import gratuidade_comprovante as GC
    with casa["db"].connect() as con:
        pendentes = GC.pendentes(con, nome=ESCREVENTE["nome"], username=ESCREVENTE["login"])
    assert selo["id"] not in [x["id"] for x in pendentes]

    termo = _trecho_do_ato(_papel(c, f"/registro-imoveis/{m['id']}/ficha.odt"),
                           f"AV-01/{PRIMEIRA_MATRICULA} –")
    _confere(termo, [
        (ato["selo_texto"], "o selo — CN-MA arts. 130 e 131"),
        (re.compile(r"(?i)isento"), "a marca do selo isento — CN-MA art. 133"),
        (f"({ESCREVENTE['nome']})", "quem praticou"),
    ], "termo da averbação gratuita")
    _sem_sobra(termo, "termo da averbação gratuita")


# =============================================== a nota devolutiva

EXIGENCIAS = ("Apresentar a certidão negativa de débitos municipais do imóvel "
              "(Lei 6.015/1973, art. 221; CN-MA art. 475).\n"
              "Reconhecer a firma do vendedor no instrumento particular "
              "(Código Civil, art. 221).")


def test_a_nota_devolutiva_formula_as_exigencias_de_uma_so_vez_e_o_titulo_reingressa(casa):
    """LRP art. 198: por escrito, de uma só vez, articuladamente, com data,
    identificação e assinatura do oficial ou preposto, e a ressalva da dúvida
    (VI). CN-MA art. 41: fundamentos fático e legal e o procedimento a
    adotar; art. 44: o reingresso no prazo aproveita o mesmo número de ordem."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA, itens=[("16.1", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    c = casa["balcao"]
    tela = f"/registro-imoveis/protocolo/{p['id']}/nota"
    token = _token(c.get(tela).get_data(as_text=True))
    r = c.post(tela, data={"csrf_token": token, "exigencias": EXIGENCIAS,
                           "fundamentacao": "Lei 6.015/1973, arts. 198 e 221; "
                                            "Código de Normas do MA, art. 41."})
    assert r.status_code == 302, r.get_data(as_text=True)[:600]
    nota = _um(casa, "SELECT * FROM ri_notas_devolutivas WHERE protocolo_id=%s", (p["id"],))
    assert nota and nota["numero"] == 1
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=%s",
               (p["id"],))["situacao"] == "DEVOLVIDO"
    papel = _papel(c, f"/registro-imoveis/notas/{nota['id']}.odt")
    _confere(papel, [
        ("NOTA DEVOLUTIVA Nº 1", "a nota e o número dela"),
        ("Ofício Único de Cidade Exemplo/MA".upper(), "a serventia — papel timbrado (CN-MA art. 41)"),
        ("CNS 000000", "o CNS"),
        (f"PROTOCOLO Nº {p['numero']}", "o título devolvido, pelo protocolo"),
        (date.today().strftime("%d/%m/%Y"), "a data da prenotação"),
        (COMPRADORA["nome"], "o apresentante"),
        ("1. Apresentar a certidão negativa", "a primeira exigência, numerada — LRP art. 198"),
        ("2. Reconhecer a firma", "a segunda exigência, numerada — LRP art. 198"),
        ("CN-MA art. 475", "o fundamento legal de cada exigência — CN-MA art. 41, § 1º"),
        ("FUNDAMENTAÇÃO", "a fundamentação — CN-MA art. 41"),
        ("reapresentar o título dentro do prazo", "o procedimento — CN-MA art. 41, § 1º"),
        ("art. 44", "o reingresso com o mesmo número — CN-MA art. 44"),
        ("suscitação de dúvida", "a ressalva da dúvida — LRP art. 198, VI"),
        (f"Cidade Exemplo/MA, {_data_por_extenso(date.today())}", "a data da nota — LRP art. 198"),
        ("Beatriz Exemplo de Souza", "a identificação de quem assina — LRP art. 198"),
        ("Substituta", "a função de quem assina"),
    ], "nota devolutiva")
    _sem_sobra(papel, "nota devolutiva")

    # o reingresso dentro do prazo: o MESMO protocolo volta a correr
    html = _clicar(c, tela, f"/registro-imoveis/notas/{nota['id']}/reingresso",
                   data_reingresso=date.today().isoformat(),
                   observacao="Exigências cumpridas")
    assert "aproveita o mesmo número de ordem" in html
    depois = _um(casa, "SELECT * FROM ri_protocolos WHERE id=%s", (p["id"],))
    assert (depois["situacao"], depois["numero"]) == ("ABERTO", p["numero"])


# =============================================== Livro 3 — registro auxiliar

PACTO = {"natureza": "PACTO_ANTENUPCIAL", "titulo_tipo": "Escritura pública de pacto antenupcial",
         "titulo_numero": "Livro 12-N, folhas 50 a 52",
         "data_titulo": "2026-10-01",
         "teor": ("Pela escritura pública de pacto antenupcial lavrada em 01 de outubro "
                  "de 2026 no Tabelionato de Notas de Cidade Exemplo/MA, os nubentes "
                  "adotaram o regime da SEPARAÇÃO TOTAL DE BENS para o casamento que "
                  "pretendem contrair."),
         "natureza_titulo": "Convenções Antenupciais", "codigo_tj": "16.8"}


def test_o_registro_do_livro_3_sela_e_a_certidao_reproduz_o_registro(casa):
    """Livro 3 — Registro Auxiliar (LRP arts. 177 e 178, V: as convenções
    antenupciais; CN-MA art. 513). O registro numerado na ordem do livro, as
    partes, o título, o teor, a prenotação (CN-MA art. 443, § 1º), o selo
    (CN-MA arts. 130 e 131). A certidão de inteiro teor do registro reproduz
    o que o livro diz (LRP art. 19) e se identifica como as do Livro 2."""
    cx = _protocolo_geral(casa, interessado=VENDEDOR,
                          itens=[("16.1", 1), ("16.8", 1), ("16.24.4", 1),
                                 ("16.24.4.1", 9)])
    p = _prenotar(casa, cx, apresentante=VENDEDOR, natureza="Pacto antenupcial",
                  objeto="Registro do pacto antenupcial no Livro 3", destino="3")
    c = casa["balcao"]
    html = _clicar(c, "/livro3/novo", "/livro3/novo", **PACTO,
                   prenotacao=str(p["numero"]), base_calculo="", valor="",
                   parte_nome=[VENDEDOR["nome"], COMPRADORA["nome"]],
                   parte_documento_tipo=["CPF", "CPF"],
                   parte_documento=[VENDEDOR["cpf_fmt"], COMPRADORA["cpf_fmt"]],
                   parte_papel=["OUTORGANTE", "OUTORGANTE"])
    reg = _um(casa, "SELECT * FROM ra_registros ORDER BY id DESC LIMIT 1")
    assert reg, f"o registro do Livro 3 não nasceu: {html[:900]}"
    r1 = _um(casa, "SELECT * FROM ra_atos WHERE registro_id=%s AND numero=1", (reg["id"],))
    assert r1["selo"], f"o R-1 do Livro 3 não selou: {html[:1200]}"
    # quem praticou o ato, congelado nele (LH13, «15 a»: como no Livro 2)
    assert (r1["lavrado_nome"], r1["lavrado_titulo"], r1["lavrado_tratamento"]) == (
        ESCREVENTE["nome"], ESCREVENTE["funcao"], "A")

    termo = _papel(c, f"/livro3/{reg['id']}/ficha.odt")
    _confere(termo, [
        (f"Cidade Exemplo/MA, {_data_por_extenso(date.today())}. Dou fé. "
         f"A {ESCREVENTE['funcao']} ({ESCREVENTE['nome']}).",
         "o ato datado e subscrito, com a função — CN-MA art. 458 (LH13)"),
        (f"REGISTRO Nº {reg['numero']}", "o número de ordem no Livro 3"),
        ("NATUREZA: PACTO ANTENUPCIAL", "a natureza, pelo nome — LRP art. 178, V"),
        ("DATA DO TÍTULO: 01/10/2026", "a data do título, na forma do papel"),
        (PACTO["titulo_tipo"], "o título"),
        (PACTO["titulo_numero"], "a procedência do título"),
        ("SEPARAÇÃO TOTAL DE BENS", "o teor"),
        (VENDEDOR["nome"], "a primeira parte"),
        (COMPRADORA["nome"], "a segunda parte"),
        (str(p["numero"]), "a prenotação — CN-MA art. 443, § 1º"),
        (r1["selo"], "o selo do registro — CN-MA arts. 130 e 131"),
        (re.compile(r"Emol R\$ 100,89"), "os emolumentos do 16.8 — LRP art. 14, p. ú."),
    ], "termo do Livro 3")
    _sem_sobra(termo, "termo do Livro 3")

    ficha = f"/livro3/{reg['id']}"
    token = _token(c.get(ficha).get_data(as_text=True))
    r = c.post(f"/atribuicoes/certidoes/LIVRO3/{reg['id']}",
               data={"csrf_token": token, "requerente": COMPRADORA["nome"],
                     "requerente_documento": COMPRADORA["cpf_fmt"],
                     "finalidade": "Para fins de financiamento", "fonte_corpo": "TEXTO",
                     "folhas": "", "protocolo": cx["numero"],
                     "busca_formulario": "1", "busca_item": "16.25.9"},
               follow_redirects=True)
    cert = _um(casa, "SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert cert and not cert["cancelada"], r.get_data(as_text=True)[:900]
    papel = _papel(c, f"/atribuicoes/certidoes/{cert['id']}/odt")
    _confere(papel, [
        ("CERTIDÃO DE INTEIRO TEOR", "a forma"),
        ("Livro 3", "o livro"),
        (f"registro n.{reg['numero']}", "o registro certificado"),
        ("SEPARAÇÃO TOTAL DE BENS", "o teor, igual ao do livro"),
        (VENDEDOR["nome"], "as partes, iguais às do livro"),
        (COMPRADORA["nome"], "as partes, iguais às do livro"),
        (PACTO["titulo_tipo"], "o título, igual ao do livro"),
        ("Era o que nela continha", "o encerramento"),
        (cert["selo"] or "sem selo gravado", "o selo da certidão — CN-MA arts. 130 e 131"),
        ("selo.tjma.jus.br", "a consulta do selo — CN-MA art. 132"),
        ("Emol R$ 90,96", "os emolumentos da certidão — LRP art. 14, p. ú."),
        ("30 (trinta) dias", "a validade — CN-MA art. 553"),
        ("na forma do art. 553 do Código de Normas", "o artigo vigente da validade (LH13)"),
        ("Para fins de financiamento", "a finalidade"),
        (ESCREVENTE["nome"], "quem expediu"),
        ("Ofício Único de Cidade Exemplo/MA".upper(), "a serventia"),
        ("000000", "o CNS"),
    ], "certidão do Livro 3")
    _sem_sobra(papel, "certidão do Livro 3")


def test_cada_ato_do_livro_3_fecha_com_quem_o_lavrou_e_o_cadastro_mudado_nao_o_troca(casa):
    """LH13 — o oficial, 21/10/2026, «15 a»: o Livro 3 como o Livro 2. Todo
    registro e averbação é «datado e subscrito pelo oficial, seu substituto ou
    escrevente autorizado» (CN-MA art. 458): cada lavratura grava o nome e a
    função de quem está logado, e a ficha fecha o ato com eles — «Cidade/UF,
    data. Dou fé. A Escrevente Autorizada (NOME).».

    O ato que não os tem (o da carga do acervo, e todo o lavrado antes do
    LH13) sai SEM fecho: não se deduz quem foi. E o fecho é o CONGELADO na
    lavratura — trocar o nome ou a função no cadastro depois não muda a ficha.
    """
    import ra_registro as RA
    c = casa["balcao"]
    _clicar(c, "/livro3/novo", "/livro3/novo", **PACTO, prenotacao="",
            base_calculo="", valor="", parte_nome=[VENDEDOR["nome"]],
            parte_documento_tipo=["CPF"], parte_documento=[VENDEDOR["cpf_fmt"]],
            parte_papel=["OUTORGANTE"])
    reg = _um(casa, "SELECT * FROM ra_registros ORDER BY id DESC LIMIT 1")
    ficha = f"/livro3/{reg['id']}"
    # a averbação, pelo oficial — outra pessoa, outra função, outro artigo
    _clicar(casa["oficial"], ficha, f"{ficha}/lancar", tipo="AVERBACAO",
            teor="Averbação do aditivo ao pacto antenupcial, de exemplo.")
    # o ato que chega sem quem o praticou: o caminho da carga do acervo
    with casa["db"].transaction() as con:
        RA.averbar(con, reg["id"], teor="Averbação trazida do acervo antigo.",
                   agora=f"{date.today().isoformat()}T09:00:00", origem="EOFICIO")
    atos = _ler(casa, """SELECT numero, lavrado_nome, lavrado_titulo, lavrado_tratamento
                           FROM ra_atos WHERE registro_id=%s ORDER BY numero""",
                (reg["id"],))
    assert [(a["numero"], a["lavrado_nome"], a["lavrado_titulo"], a["lavrado_tratamento"])
            for a in atos] == [
        (1, ESCREVENTE["nome"], ESCREVENTE["funcao"], "A"),
        (2, OFICIAL["nome"], OFICIAL["funcao"], "O"),
        (3, None, None, None)]

    dia = f"Cidade Exemplo/MA, {_data_por_extenso(date.today())}. Dou fé."
    da_escrevente = f"{dia} A {ESCREVENTE['funcao']} ({ESCREVENTE['nome']})."
    do_oficial = f"{dia} O {OFICIAL['funcao']} ({OFICIAL['nome']})."

    def os_tres_atos() -> tuple[str, str, str]:
        termo = _papel(c, f"{ficha}/ficha.odt")
        _sem_sobra(termo, "ficha do Livro 3")
        i_r1, i_av2, i_av3 = (termo.index(f"{rotulo} – ")
                              for rotulo in ("R-1", "AV-2", "AV-3"))
        return termo[i_r1:i_av2], termo[i_av2:i_av3], termo[i_av3:]

    r1, av2, av3 = os_tres_atos()
    assert da_escrevente in r1, r1
    assert do_oficial in av2, av2
    assert "Dou fé" not in av3, f"o ato sem quem o praticou ganhou fecho: {av3}"

    # O CADASTRO MUDA; O ATO NÃO.
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE users SET full_name=%s, funcao=%s WHERE username=%s",
            ("CARLA EXEMPLO DE OUTRO NOME", "Oficial Substituta", ESCREVENTE["login"]))
    r1, _av2, _av3 = os_tres_atos()
    assert da_escrevente in r1, r1
    assert "OUTRO NOME" not in r1 and "Substituta" not in r1


# =============================================== encerramento e cancelamento

def _teor_da_caixa(html: str) -> str:
    """O texto que a tela pôs na caixa «O texto do ato» (`name="teor"`) do
    formulário que lavra (o que posta em `/atos`)."""
    form = re.search(r'<form[^>]*action="[^"]*/atos"[^>]*>(.*?)</form>', html, re.S)
    assert form, "a tela não trouxe o formulário de lavrar"
    achado = re.search(r'<textarea name="teor"[^>]*>(.*?)</textarea>', form.group(1), re.S)
    assert achado, "a tela não trouxe a caixa de teor"
    return unescape(achado.group(1)).strip()


def _atender(casa, cliente, cx: dict) -> None:
    html = _clicar(cliente, "/selo/cobertura", "/selo/cobertura/atender",
                   protocolo=cx["numero"])
    assert f"atendendo o protocolo {cx['numero']}" in html


def test_o_encerramento_da_matricula_e_do_oficial_sela_e_a_certidao_o_informa(casa):
    """O encerramento é averbação (LRP art. 233; CN-MA art. 495), lavrado pelo
    oficial a partir do modelo que o botão «Encerrar» põe na caixa, com o
    selo; a ficha fica encerrada e a certidão, que continua possível, diz o
    encerramento (CN-MA art. 553, §§ 2º e 3º)."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Encerramento de matrícula",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}", matricula=str(PRIMEIRA_MATRICULA))
    oficial = casa["oficial"]
    tela = oficial.get(f"/registro-imoveis/{m['id']}?encerrar=1&lavrar=1").get_data(as_text=True)
    teor = _teor_da_caixa(tela)
    assert "«PREENCHER" in teor, "o botão «Encerrar» não pôs o modelo na caixa"
    teor = re.sub(r"«PREENCHER: motivo e fundamento do encerramento»",
                  "Em virtude do desmembramento total do imóvel requerido pela "
                  "proprietária em 15 de outubro de 2026", teor)
    teor = re.sub(r"«PREENCHER: matrícula de destino»", "4.101", teor)
    html = _lavrar(casa, m, tipo="AV", teor=teor, natureza="Encerramento de matrícula",
                   prenotacao=p, cx=cx, itens=["16.22.2"], cliente=oficial,
                   encerra="1", encerra_motivo="Desmembramento total do imóvel",
                   encerra_destino="Matrícula 4.101")
    m2 = _um(casa, "SELECT * FROM ri_matriculas WHERE id=%s", (m["id"],))
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert m2["encerrada"] == 1, f"a matrícula não encerrou: {html[:1200]}"
    assert av["selo_texto"], f"o encerramento não selou: {html[:1200]}"
    assert av["lavrado_nome"] == OFICIAL["nome"]

    termo = _trecho_do_ato(_papel(oficial, f"/registro-imoveis/{m['id']}/ficha.odt"),
                           f"AV-02/{PRIMEIRA_MATRICULA}")
    _confere(termo, [
        ("ENCERRAMENTO DE MATRÍCULA", "a natureza, no cabeçalho do ato"),
        ("procede-se ao encerramento da Matrícula nº 4.100", "o que o ato faz — LRP art. 233"),
        ("desmembramento total", "o motivo"),
        ("4.101", "a matrícula de destino — remissão recíproca"),
        (OFICIAL["nome"], "quem praticou — CN-MA art. 458"),
        (av["selo_texto"], "o selo — CN-MA arts. 130 e 131"),
    ], "termo do encerramento")
    _sem_sobra(termo, "termo do encerramento")

    cert = _certidao(casa, m2, "INTEIRO_TEOR", cx=_pede_certidao(casa))
    _confere(cert["papel"], [
        ("ENCERRAMENTO DA MATRÍCULA", "o encerramento informado — CN-MA art. 553, § 3º"),
        ("4.101", "a matrícula para onde o imóvel foi — CN-MA art. 553, § 2º"),
        (av["selo_texto"], "o selo do encerramento"),
    ], "certidão de matrícula encerrada")


def test_o_cancelamento_da_hipoteca_e_averbado_selado_e_a_certidao_volta_a_ser_negativa(casa):
    """O cancelamento é averbação (LRP arts. 248 e 250; CN-MA art. 538): o
    ato cancelado fica na ficha, marcado; o selo sai com a própria averbação
    (LD03 — o item vem do protocolo geral da prenotação informada; «Selar
    este ato» fica para o ato que nasceu sem selo); e a certidão de ônus
    passa a dizer que nada consta."""
    f = _com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    oficial = casa["oficial"]
    cx = _protocolo_geral(casa, interessado=BANCO, itens=[("16.1", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=BANCO, natureza="Cancelamento de Hipoteca",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}", matricula=str(PRIMEIRA_MATRICULA))
    ficha = f"/registro-imoveis/{m['id']}"
    html = _clicar(oficial, ficha, f"/registro-imoveis/atos/{r2['id']}/cancelar",
                   motivo="Termo de quitação do credor de 18 de outubro de 2026",
                   data_ato=date.today().isoformat(), protocolo=str(p["numero"]))
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert av["numero"] == 3 and "CANCELAMENTO DO ATO R-02" in av["teor"], html[:900]
    assert _um(casa, "SELECT cancelado FROM ri_atos WHERE id=%s", (r2["id"],))["cancelado"] == 1
    if not av["selo_texto"]:
        _atender(casa, oficial, cx)
        html = _clicar(oficial, ficha, f"/registro-imoveis/ato/{av['id']}/selar",
                       natureza_titulo="Cancelamento de Hipoteca", codigo_tj="16.22.2")
        av = _um(casa, "SELECT * FROM ri_atos WHERE id=%s", (av["id"],))
    assert av["selo_texto"], f"a averbação de cancelamento não selou: {html[:1200]}"

    termo = _trecho_do_ato(_papel(oficial, f"{ficha}/ficha.odt"), f"AV-03/{PRIMEIRA_MATRICULA}")
    _confere(termo, [
        (f"CANCELAMENTO DO ATO R-02/{PRIMEIRA_MATRICULA}", "o ato cancelado, pelo rótulo"),
        ("Termo de quitação do credor", "o fundamento do cancelamento"),
        (OFICIAL["nome"], "quem praticou"),
        (av["selo_texto"], "o selo"),
    ], "termo do cancelamento")
    _sem_sobra(termo, "termo do cancelamento")

    cert = _certidao(casa, m, "ONUS", cx=_pede_certidao(casa),
                     onus_formulario="1", resultado_onus="negativa",
                     resultado_acoes="negativa", proprietario_conferido="1")
    _confere(cert["papel"], [("NADA CONSTA", "a hipoteca cancelada não é mais ônus")],
             "certidão de ônus depois do cancelamento")


def test_a_averbacao_de_cancelamento_ja_nasce_selada(casa):
    """«Cancelar este ato» lavra a averbação JÁ com o selo — CN-MA art. 130,
    § 2º (nenhum ato se conclui sem o selo) e o relato #77. Era `xfail` do
    LT03 (a AV ficava de pé sem selo até «Selar este ato»); consertado no LD03."""
    f = _com_hipoteca(casa)
    m, r2 = f["matricula"], f["r2"]
    cx = _protocolo_geral(casa, interessado=BANCO, itens=[("16.1", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=BANCO, natureza="Cancelamento de Hipoteca",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}", matricula=str(PRIMEIRA_MATRICULA))
    _atender(casa, casa["oficial"], cx)
    _clicar(casa["oficial"], f"/registro-imoveis/{m['id']}",
            f"/registro-imoveis/atos/{r2['id']}/cancelar",
            motivo="Termo de quitação do credor de 18 de outubro de 2026",
            data_ato=date.today().isoformat(), protocolo=str(p["numero"]))
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert av["selo_texto"], "a averbação de cancelamento ficou de pé sem selo"


# O CAMINHO DO ERRO DO CANCELAMENTO SELADO — LD03, 21/10/2026. O selo que não
# sai, o clique duplo e o protocolo com mais de um item: nada de ato de pé sem
# selo (CN-MA art. 130, § 2º), nada de selo pedido duas vezes, nada de item
# gasto duas vezes.

FUNDAMENTO_DO_CANCELAMENTO = "Termo de quitação do credor de 18 de outubro de 2026"


def _recados(html: str) -> str:
    """Os recados («flash») da tela, em texto corrido."""
    return " ".join(unescape(re.sub(r"<[^>]+>", " ", t))
                    for t in re.findall(r'class="flash[^"]*"[^>]*>(.*?)</', html, re.S))


def _para_cancelar(casa, itens=(("16.1", 1), ("16.22.2", 1))) -> dict:
    """A hipoteca R-2 lavrada e o título do cancelamento pago e prenotado."""
    f = _com_hipoteca(casa)
    cx = _protocolo_geral(casa, interessado=BANCO, itens=list(itens))
    p = _prenotar(casa, cx, apresentante=BANCO, natureza="Cancelamento de Hipoteca",
                  objeto=f"Matrícula {PRIMEIRA_MATRICULA}", matricula=str(PRIMEIRA_MATRICULA))
    return f | {"cx": cx, "p": p, "ficha": f"/registro-imoveis/{f['matricula']['id']}"}


def _cancelar(casa, t: dict, cliente=None, **extra) -> str:
    return _clicar(cliente or casa["oficial"], t["ficha"],
                   f"/registro-imoveis/atos/{t['r2']['id']}/cancelar",
                   motivo=FUNDAMENTO_DO_CANCELAMENTO, data_ato=date.today().isoformat(),
                   protocolo=str(t["p"]["numero"]), **extra)


def _atos_da_ficha(casa, matricula_id: int) -> list[dict]:
    return _ler(casa, """SELECT id, tipo, numero, cancelado, cancelado_por_ato_id,
                                selo_texto, teor FROM ri_atos
                          WHERE matricula_id=%s ORDER BY id""", (matricula_id,))


def test_o_cancelamento_cujo_selo_nao_sai_nao_fica_de_pe_e_o_ato_continua_valendo(casa):
    """O aparelho recusa: nada do cancelamento fica — nem a averbação no livro,
    nem a marca no R-2, nem o lançamento dos Livros 4 e 5, nem a prenotação
    amarrada, nem a unidade gasta do protocolo; e o fundamento digitado volta
    no recado (CN-MA art. 130, § 2º; relato #77). Com o aparelho de volta, o
    mesmo cancelamento sai selado — com UM selo e UMA unidade do item."""
    t = _para_cancelar(casa)
    m, r2, p = t["matricula"], t["r2"], t["p"]
    item = _item(casa, t["cx"], "16.22.2")
    antes = _atos_da_ficha(casa, m["id"])

    casa["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    try:
        html = _cancelar(casa, t)
    finally:
        casa["aparelho"].recusar_com = None
    recado = _recados(html)
    assert "O cancelamento NÃO foi lavrado" in recado, recado
    assert FUNDAMENTO_DO_CANCELAMENTO in recado, "o fundamento digitado se perdeu"
    assert _atos_da_ficha(casa, m["id"]) == antes, (
        "a averbação de cancelamento ficou no livro sem selo, ou o R-2 ficou marcado")
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s", (p["id"],))["ato_id"] is None
    assert not _ler(casa, """SELECT id FROM ri_indicador_lancamentos
                              WHERE ato_cancelado_id=%s ORDER BY id""", (r2["id"],))
    devolvido = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id=%s", (item["id"],))
    assert not devolvido["quantidade_usada"] and devolvido["usado_em"] is None, (
        "a unidade do protocolo não voltou")

    html = _cancelar(casa, t)
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert av["numero"] == 3 and av["selo_texto"], _recados(html)
    assert "CANCELAMENTO DO ATO R-02" in av["teor"]
    assert _um(casa, "SELECT cancelado_por_ato_id FROM ri_atos WHERE id=%s",
               (r2["id"],))["cancelado_por_ato_id"] == av["id"]
    selos = _ler(casa, """SELECT numero FROM sd_selos WHERE tabela='ri_atos' AND ato_id=%s
                           AND cancelado_em IS NULL ORDER BY id""", (av["id"],))
    assert len(selos) == 1, f"o cancelamento saiu com {len(selos)} selos"
    gasto = _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s", (item["id"],))
    assert gasto["quantidade_usada"] == 1, "o item foi gasto mais de uma vez"
    cobertura = _ler(casa, """SELECT item_id FROM cx_selo_coberturas
                               WHERE tabela='ri_atos' AND ato_id=%s ORDER BY id""", (av["id"],))
    assert [c["item_id"] for c in cobertura] == [item["id"]], cobertura
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s",
               (p["id"],))["ato_id"] == av["id"]


def test_dois_cliques_em_cancelar_lavram_uma_averbacao_so(casa, monkeypatch):
    """Dois «Cancelar o ato por averbação» ao mesmo tempo (duas abas, clique
    duplo) passam juntos pela conferência que a rota faz antes da transação.
    O segundo tem de parar na conferência PRESA, dentro da trava da numeração:
    UMA averbação, UM selo, UMA unidade do item.

    O ITEM TEM DUAS UNIDADES DE PROPÓSITO: com uma só, o segundo clique pararia
    na outra guarda (a unidade acabou no meio) e este teste não mediria a
    conferência presa — foi o que o mutante sem ela mostrou."""
    import threading

    import ri_frases
    t = _para_cancelar(casa, itens=(("16.1", 1), ("16.22.2", 2)))
    m, r2 = t["matricula"], t["r2"]
    item = _item(casa, t["cx"], "16.22.2")
    abas = [_entrar(casa["app"], OFICIAL) for _ in range(2)]
    tokens = [_token(c.get(t["ficha"]).get_data(as_text=True)) for c in abas]
    # As duas abas passam da conferência de fora antes de qualquer uma lavrar:
    # o teor do cancelamento se monta logo depois dela, e é ali que esperam.
    juntas = threading.Barrier(2, timeout=60)
    frase_de_verdade = ri_frases.frase

    def frase(chave, *a, **k):
        if chave == "RI_CANCELAMENTO_DO_ATO":
            juntas.wait()
        return frase_de_verdade(chave, *a, **k)
    monkeypatch.setattr(ri_frases, "frase", frase)

    respostas = []

    def clicar(c, token):
        r = c.post(f"/registro-imoveis/atos/{r2['id']}/cancelar",
                   data={"csrf_token": token, "motivo": FUNDAMENTO_DO_CANCELAMENTO,
                         "data_ato": date.today().isoformat(),
                         "protocolo": str(t["p"]["numero"])})
        respostas.append(r.status_code)
    fios = [threading.Thread(target=clicar, args=par) for par in zip(abas, tokens)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(120)
    assert respostas == [302, 302], respostas

    cancelamentos = [a for a in _atos_da_ficha(casa, m["id"])
                     if "CANCELAMENTO DO ATO R-02" in (a["teor"] or "")]
    assert len(cancelamentos) == 1, (
        f"{len(cancelamentos)} averbações de cancelamento para o mesmo ato")
    assert cancelamentos[0]["selo_texto"]
    assert len(_ler(casa, """SELECT id FROM sd_selos WHERE tabela='ri_atos'
                              AND ato_id=%s ORDER BY id""",
                    (cancelamentos[0]["id"],))) == 1
    assert _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
               (item["id"],))["quantidade_usada"] == 1


def test_o_cancelamento_pergunta_o_item_quando_o_protocolo_tem_mais_de_um(casa):
    """Com dois itens com saldo no protocolo do título, escolher um seria
    adivinhar qual serviço o cliente pagou (`caixa_protocolo.
    itens_para_o_selo`): a rota recusa ANTES de lavrar e diz quais são. Com o
    item marcado, sai selado e gasta só ele."""
    t = _para_cancelar(casa, itens=(("16.1", 1), ("16.22.2", 1), ("16.39", 2)))
    m, r2 = t["matricula"], t["r2"]
    antes = _atos_da_ficha(casa, m["id"])
    recado = _recados(_cancelar(casa, t))
    assert "16.22.2" in recado and "16.39" in recado and "NÃO foi lavrado" in recado, recado
    assert _atos_da_ficha(casa, m["id"]) == antes

    averbacao = _item(casa, t["cx"], "16.22.2")
    arquivamento = _item(casa, t["cx"], "16.39")
    _cancelar(casa, t, protocolo_id=str(t["cx"]["id"]),
              protocolo_item_id=[str(averbacao["id"])])
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert av["numero"] == 3 and av["selo_texto"] and av["codigo_tj"] == "16.22.2"
    assert _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
               (averbacao["id"],))["quantidade_usada"] == 1
    assert not _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
                   (arquivamento["id"],))["quantidade_usada"], "gastou o item que não era"


def test_o_abort_dentro_da_transacao_desfaz_a_averbacao_ja_gravada(casa, monkeypatch):
    """`abort(redirect(...))` dentro de `db.transaction()` é a saída de três
    recusas da lavratura e do cancelamento, e a do item que acabou no meio vem
    DEPOIS do INSERT da averbação. Ela só não deixa a AV no livro porque o
    `transaction` desfaz também na exceção HTTP — a revisão do LD03 pediu a
    prova (LD10). O item «acaba» aqui, já com a AV gravada na transação: nada
    fica (nem a AV, nem a marca no R-2, nem o lançamento dos Livros 4 e 5, nem
    a unidade), e o número não se queima — o cancelamento de verdade sai
    AV-03."""
    import caixa_protocolo
    t = _para_cancelar(casa)
    m, r2, p = t["matricula"], t["r2"], t["p"]
    item = _item(casa, t["cx"], "16.22.2")
    antes = _atos_da_ficha(casa, m["id"])
    gravada = []

    def acabou(con, item_id, **campos):
        # a AV já está gravada na transação quando o item «acaba»
        gravada.append(banco(con).valor(
            "SELECT count(*) AS n FROM ri_atos WHERE id=%s", (campos["ato_id"],)))
        return False

    with monkeypatch.context() as mp:
        mp.setattr(caixa_protocolo, "consumir_item", acabou)
        recado = _recados(_cancelar(casa, t))
    assert gravada == [1], "o cancelamento não chegou ao abort com a AV gravada"
    assert "O item do protocolo acabou" in recado and "NÃO foi lavrado" in recado, recado
    assert _atos_da_ficha(casa, m["id"]) == antes, (
        "o abort dentro da transação deixou a averbação no livro")
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s", (p["id"],))["ato_id"] is None
    assert not _ler(casa, """SELECT id FROM ri_indicador_lancamentos
                              WHERE ato_cancelado_id=%s ORDER BY id""", (r2["id"],))
    assert not _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
                   (item["id"],))["quantidade_usada"]

    _cancelar(casa, t)
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert (av["numero"], bool(av["selo_texto"])) == (3, True)


def test_a_venda_que_o_selo_recusou_nao_fica_no_livro_e_o_vendedor_continua_dono(casa):
    """O selo recusado suspende o R-1 (ordem do oficial, 16/09/2026): o ato
    volta a ser minuta com as partes, a prenotação se solta, o item volta — e
    o quadro de titulares continua o de antes (LRP art. 19, § 9º): quem
    transmite só sai dele com o ato de pé.

    Antes do LD03 a suspensão nem chegava a acontecer no PostgreSQL: a
    prenotação amarrada ao ato estourava a chave estrangeira no `DELETE`, e o
    R-1 FICAVA lavrado sem selo («FOREIGN KEY constraint failed»)."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    valores = dict(COMPRA_E_VENDA)
    valores["INFORMAR O PROTOCOLO"] = (
        f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}")
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = (
        f"{COMPRADORA['nome']}, {COMPRADORA['qualificacao']}, inscrita no CPF "
        f"sob o nº {COMPRADORA['cpf_fmt']}")
    teor = _teor_do_modelo(casa, m["id"], "R-COMPRA-VENDA", valores)
    casa["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    try:
        html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda",
                       prenotacao=p, cx=cx, itens=["16.3.14"], base_calculo="100.000,00",
                       partes=[(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")],
                       modelo="R-COMPRA-VENDA")
    finally:
        casa["aparelho"].recusar_com = None
    assert "NÃO foi lavrado" in _recados(html), _recados(html)
    assert not _atos_da_ficha(casa, m["id"]), "o R-1 com o selo recusado ficou no livro"
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s", (p["id"],))["ato_id"] is None
    minuta = _um(casa, "SELECT * FROM ri_minutas WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
                 (m["id"],))
    assert minuta and minuta["situacao"] == "A_REVISAR"
    assert len(_ler(casa, "SELECT id FROM ri_minuta_partes WHERE minuta_id=%s ORDER BY id",
                    (minuta["id"],))) == 2
    titulares = [x["nome"] for x in _ler(
        casa, """SELECT nome FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1
                  ORDER BY id""", (m["id"],))]
    assert titulares == [VENDEDOR["nome"]], titulares
    assert not _item(casa, cx, "16.3.14")["quantidade_usada"], "o item não voltou"


def test_a_venda_lavrada_troca_o_titular_no_quadro_e_avisa_quem_saiu(casa):
    """Com o R-1 de pé, a compradora é a titular atual e o vendedor deixa de
    ser — a linha dele fica (`proprietario`), só deixa de ser atual; e a tela
    diz quem saiu e por onde se corrige a venda de parte ideal."""
    f = _compra_e_venda(casa)
    m = f["matricula"]
    linhas = _ler(casa, """SELECT nome, papel, ato_id, proprietario, proprietario_ativo
                            FROM ri_partes WHERE matricula_id=%s ORDER BY id""", (m["id"],))
    ativos = [x["nome"] for x in linhas if x["proprietario_ativo"]]
    assert ativos == [COMPRADORA["nome"]], linhas
    abertura = [x for x in linhas if x["ato_id"] is None]
    assert abertura and abertura[0]["nome"] == VENDEDOR["nome"] and abertura[0]["proprietario"]
    recado = _recados(f["recado"])
    assert "deixou(aram) de figurar como titular" in recado, recado
    assert "parte ideal" in recado


def _titulares(casa, matricula_id: int) -> list[str]:
    return [x["nome"] for x in _ler(
        casa, """SELECT nome FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1
                  ORDER BY id""", (matricula_id,))]


def _auditoria(casa, acao: str) -> list[dict]:
    linhas = _ler(casa, "SELECT entity_id, details FROM audit_logs WHERE action=%s ORDER BY id",
                  (acao,))
    return [{"ato_id": x["entity_id"], **json.loads(x["details"] or "{}")} for x in linhas]


def test_o_vendedor_sem_cpf_no_ato_fica_no_quadro_e_a_tela_e_a_auditoria_avisam(casa):
    """LD10 (ressalva da revisão do LD03): o nome do transmitente bate com o
    titular da abertura, mas só a abertura tem o CPF. Pelo nome ninguém sai —
    no LD03 saía, e o homônimo sem CPF saía junto —, e a pendência vai para o
    recado e para a auditoria, com o caminho do conserto. A compradora entra
    no quadro do mesmo jeito (LRP art. 19, § 9º)."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    valores = dict(COMPRA_E_VENDA)
    valores["INFORMAR O PROTOCOLO"] = (
        f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}")
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = f"{COMPRADORA['nome']}, qualificada no título"
    teor = _teor_do_modelo(casa, m["id"], "R-COMPRA-VENDA", valores)
    html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda", prenotacao=p,
                   cx=cx, itens=["16.3.14"], base_calculo="100.000,00",
                   partes=[({**VENDEDOR, "cpf_fmt": ""}, "transmitente"),
                           (COMPRADORA, "adquirente")],
                   modelo="R-COMPRA-VENDA")
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s", (m["id"],))
    assert ato and ato["selo_texto"], _recados(html)
    assert _titulares(casa, m["id"]) == [VENDEDOR["nome"], COMPRADORA["nome"]]
    recado = _recados(html)
    assert "Quadro de titulares a conferir" in recado, recado
    assert "só um dos dois tem CPF/CNPJ" in recado and "Partes → Corrigir" in recado
    auditoria = _auditoria(casa, "RI_TITULARES_A_CONFERIR")
    assert [a["ato_id"] for a in auditoria] == [ato["id"]], auditoria
    assert "só um dos dois tem CPF/CNPJ" in auditoria[0]["a_conferir"][0]


def test_a_falha_ao_tirar_o_transmitente_nao_derruba_o_ato_ja_lavrado(casa, monkeypatch):
    """A saída do transmitente roda na SEGUNDA transação, com o R-1 já no livro
    e selado. A falha ali (aqui, a trava da ficha que não veio depois de a
    saída já ter sido gravada) virava a tela de erro, e quem lavrou não sabia
    que o ato tinha saído (LD10, ressalva da revisão do LD03). Agora: o ato de
    pé, o quadro como estava — a transação volta inteira —, e a pendência no
    recado e na auditoria."""
    import sqlite3

    import ri_correcoes as RC
    de_verdade = RC.titulares_que_transmitiram

    def cai_no_meio(con, *a, **k):
        de_verdade(con, *a, **k)
        raise sqlite3.OperationalError("database is locked")
    monkeypatch.setattr(RC, "titulares_que_transmitiram", cai_no_meio)

    f = _compra_e_venda(casa)
    m, ato = f["matricula"], f["ato"]
    assert ato["selo_texto"], "o R-1 tinha de ficar lavrado e selado"
    assert _titulares(casa, m["id"]) == [VENDEDOR["nome"], COMPRADORA["nome"]], (
        "a saída do vendedor ficou gravada pela metade")
    recado = _recados(f["recado"])
    assert "R-1 lavrado" in recado, recado
    assert "o quadro de titulares NÃO foi atualizado (database is locked)" in recado
    assert "Partes → Corrigir" in recado
    falhas = _auditoria(casa, "RI_TITULARES_NAO_ATUALIZADOS")
    assert [(a["ato_id"], a["erro"]) for a in falhas] == [(ato["id"], "database is locked")]
    assert falhas[0]["transmitentes"] == [VENDEDOR["nome"]]
    assert [a["ato_id"] for a in _auditoria(casa, "RI_ATO_LAVRADO")] == [ato["id"]]


# A SEGUNDA TRANSAÇÃO APANHA SÓ O QUE É DO BANCO — LD13, 21/10/2026 (ressalva
# da revisão do LD10). O `except Exception` largo fazia do erro de programação
# um recado e uma linha de auditoria, sem rastro no log de erro; e a auditoria
# de dentro do `except`, se falhasse, trazia de volta o 500 que se queria evitar.

def _o_quadro_cai_no_meio(monkeypatch, erro: BaseException) -> None:
    """A saída do transmitente gravada na 2ª transação, e depois `erro`."""
    import ri_correcoes as RC
    de_verdade = RC.titulares_que_transmitiram

    def cai_no_meio(con, *a, **k):
        de_verdade(con, *a, **k)
        raise erro
    monkeypatch.setattr(RC, "titulares_que_transmitiram", cai_no_meio)


def _no_log(caplog, trecho: str) -> list:
    """Os registros de erro do log que citam `trecho` e trazem o traceback."""
    return [r for r in caplog.records
            if r.levelname == "ERROR" and r.exc_info and trecho in r.getMessage()]


def test_a_falha_de_banco_ao_tirar_o_transmitente_vai_ao_log_com_o_traceback(
        casa, monkeypatch, caplog):
    """O recado e a auditoria do LD10 continuam; e quem conserta acha a falha
    no log do servidor, com o traceback — a auditoria guarda só a frase."""
    import sqlite3
    _o_quadro_cai_no_meio(monkeypatch, sqlite3.OperationalError("database is locked"))
    with caplog.at_level("ERROR"):
        f = _compra_e_venda(casa)
    assert "o quadro de titulares NÃO foi atualizado" in _recados(f["recado"])
    assert len(_auditoria(casa, "RI_TITULARES_NAO_ATUALIZADOS")) == 1
    registrados = _no_log(caplog, "quadro de titulares")
    assert registrados, [r.getMessage() for r in caplog.records]
    assert registrados[0].exc_info[0] is sqlite3.OperationalError


def test_o_erro_de_programacao_ao_tirar_o_transmitente_sobe_e_nao_vira_recado(
        casa, monkeypatch, caplog):
    """Um `TypeError` (o defeito de amanhã em `titulares_que_transmitiram`)
    não é «o banco não deixou»: sobe para a tela de erro, que o anota para
    quem cuida do sistema, e o traceback fica no log. Nem recado de
    pendência, nem auditoria dela — o quadro fica como estava, porque a
    transação volta inteira."""
    _o_quadro_cai_no_meio(monkeypatch, TypeError("defeito de programação"))
    with caplog.at_level("ERROR"):
        f = _compra_e_venda(casa)
    assert f["ato"]["selo_texto"], "o R-1 tinha de ficar lavrado e selado"
    assert "O sistema não conseguiu terminar o que você pediu" in f["recado"], (
        _recados(f["recado"]))
    assert not _auditoria(casa, "RI_TITULARES_NAO_ATUALIZADOS")
    assert _titulares(casa, f["matricula"]["id"]) == [VENDEDOR["nome"], COMPRADORA["nome"]]
    assert any(r.exc_info and r.exc_info[0] is TypeError for r in caplog.records), (
        "o erro de programação não deixou traceback no log")


def test_a_auditoria_que_falha_no_recado_do_quadro_nao_derruba_a_tela(
        casa, monkeypatch, caplog):
    """O banco que recusou o quadro pode recusar também a linha de auditoria
    da pendência. Ela não pode trazer o 500 de volta: o ato está lavrado, e a
    tela tem de dizer isso e o que falta. A falha da auditoria vai ao log.

    O `db.log` já engole o `OperationalError` (a trava e o número que não
    cabe: LX14); o que escapa dele é o resto do banco — aqui, a conexão que
    caiu (`DatabaseError`)."""
    import sqlite3
    _o_quadro_cai_no_meio(monkeypatch, sqlite3.OperationalError("database is locked"))
    db = casa["db"]
    log_de_verdade = db.log

    def log(usuario_id, usuario, acao, *a, **k):
        if acao == "RI_TITULARES_NAO_ATUALIZADOS":
            raise sqlite3.DatabaseError("server closed the connection unexpectedly")
        return log_de_verdade(usuario_id, usuario, acao, *a, **k)
    monkeypatch.setattr(db, "log", log)
    with caplog.at_level("ERROR"):
        f = _compra_e_venda(casa)
    recado = _recados(f["recado"])
    assert "R-1 lavrado" in recado, recado
    assert "o quadro de titulares NÃO foi atualizado (database is locked)" in recado
    assert _no_log(caplog, "RI_TITULARES_NAO_ATUALIZADOS"), (
        [r.getMessage() for r in caplog.records])
    assert [a["ato_id"] for a in _auditoria(casa, "RI_ATO_LAVRADO")] == [f["ato"]["id"]]


# =============================================== o arquivamento por folha

def test_o_arquivamento_por_folha_sai_com_selo_proprio_e_encerra_a_prenotacao(casa):
    """O 16.39 (arquivamento do título, por folha) sai junto com a averbação,
    com selo próprio e a quantidade de folhas (LRP art. 194: o título
    digitalizado e arquivado); com ele o título se esgota e a prenotação se
    encerra (a regra da casa, 23/09/2026)."""
    cx = _protocolo_geral(casa, interessado=VENDEDOR,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 1), ("16.39", 3)])
    p = _prenotar(casa, cx, apresentante=VENDEDOR, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    teor, _ = _como_o_balcao_preenche(json.loads(casa["balcao"].get(
        f"/registro-imoveis/{m['id']}/modelo/AV-CONSTRUCAO").get_data(as_text=True))["teor"])
    html = _lavrar(casa, m, tipo="AV", teor=teor, natureza="Construção", prenotacao=p,
                   cx=cx, itens=["16.22.2"], modelo="AV-CONSTRUCAO",
                   gerar_arquivamento="1", folhas_arquivamento="3")
    av = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
             (m["id"],))
    assert av["selo_texto"] and av["selo_arquivamento"], html[:1500]
    assert av["folhas_arquivamento"] == 3
    assert _um(casa, "SELECT situacao FROM ri_protocolos WHERE id=%s",
               (p["id"],))["situacao"] == "ENCERRADO"
    termo = _trecho_do_ato(_papel(casa["balcao"], f"/registro-imoveis/{m['id']}/ficha.odt"),
                           f"AV-01/{PRIMEIRA_MATRICULA} –")
    _confere(termo, [
        (av["selo_texto"], "o selo da averbação"),
        ("SELO DE ARQUIVAMENTO (3 fl.)", "o carimbo do arquivamento, com as folhas"),
        (av["selo_arquivamento"], "o selo do arquivamento — CN-MA arts. 130 e 131"),
        ("Ato: 16.39", "o item do arquivamento"),
    ], "termo com arquivamento")


# =============================================== os caminhos que não chegam ao livro

def test_o_modelo_preenchido_na_tela_do_modelo_chega_ao_livro(casa):
    """«Enviar para a lavratura» da tela do modelo leva o ato inteiro — a
    prenotação, o protocolo geral e o item (CN-MA art. 130, § 2º). Era
    `xfail` do LT03 (ia só o texto, e a lavratura recusava pelo item de custa);
    consertado no LD03."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    c = casa["balcao"]
    tela = f"/registro-imoveis/{m['id']}/preencher/AV-CONSTRUCAO"
    campos = {"c_" + x["chave"]: _valor_de_exemplo(x["marcador"]) or "x"
              for x in MODELOS_DE_ATO.campos_do_modelo(
                  MODELOS_DE_ATO.por_codigo("AV-CONSTRUCAO"))}
    pronto = _clicar(c, tela, tela, acao="lavrar", confirmar_pendencias="1", **campos)
    form = re.search(r'<form[^>]*id="form-lavrar"[^>]*>(.*?)</form>', pronto, re.S)
    assert form, "a tela do modelo não ofereceu «Lavrar»"
    enviados = dict(re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"',
                               form.group(1)))
    enviados["teor"] = unescape(re.search(r'<textarea name="teor"[^>]*>(.*?)</textarea>',
                                          form.group(1), re.S).group(1))
    enviados.pop("csrf_token", None)
    html = _clicar(c, tela, f"/registro-imoveis/{m['id']}/atos", **enviados)
    recusa = re.search(r"Escolha o item da tabela de custas[^<]*", html)
    assert _um(casa, "SELECT id FROM ri_atos WHERE matricula_id=%s", (m["id"],)), (
        "o texto preenchido na tela do modelo não virou ato: "
        + (recusa.group(0) if recusa else html[:600]))


def test_a_lavratura_recusa_o_campo_do_modelo_que_ficou_por_preencher(casa):
    """O [CAMPO] do modelo informado em `modelo_codigo` que ninguém preencheu
    não vai ao livro (LRP art. 176, § 1º, III; CN-MA art. 458). Era `xfail` do
    LT03 (só o `{{ }}` cru era recusado); consertado no LD03."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    teor = json.loads(casa["balcao"].get(
        f"/registro-imoveis/{m['id']}/modelo/R-COMPRA-VENDA").get_data(as_text=True))["teor"]
    assert "[DATA DA ESCRITURA]" in teor
    _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda", prenotacao=p,
            cx=cx, itens=["16.3.14"], base_calculo="100.000,00",
            partes=[(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")],
            modelo="R-COMPRA-VENDA")
    assert _um(casa, "SELECT id FROM ri_atos WHERE matricula_id=%s", (m["id"],)) is None, (
        "o R-1 foi lavrado com «[DATA DA ESCRITURA]» e os outros campos em branco")


# A TELA DO MODELO E OS COLCHETES — LD03, 21/10/2026. O que a tela «Preencher
# o modelo» manda à lavratura e o que a lavratura recusa saem da mesma régua
# (`ri_modelos_atos.por_preencher`).

def _preencher(casa, m: dict, codigo: str, **campos) -> str:
    tela = f"/registro-imoveis/{m['id']}/preencher/{codigo}"
    return _clicar(casa["balcao"], tela, tela, **campos)


def _o_que_a_tela_manda(pronto: str) -> dict:
    """O formulário «Lavrar» da tela do modelo, como o navegador o posta:
    os campos escondidos (repetidos viram lista) e o teor."""
    form = re.search(r'<form[^>]*id="form-lavrar"[^>]*>(.*?)</form>', pronto, re.S)
    assert form, f"a tela do modelo não ofereceu «Lavrar»: {_recados(pronto)}"
    enviados: dict = {}
    for nome, valor in re.findall(r'<input type="hidden" name="([a-z_]+)" value="([^"]*)"',
                                  form.group(1)):
        if nome != "csrf_token":
            enviados.setdefault(nome, []).append(unescape(valor))
    enviados["teor"] = [unescape(re.search(r'<textarea name="teor"[^>]*>(.*?)</textarea>',
                                           form.group(1), re.S).group(1))]
    return enviados


def test_a_tela_do_modelo_lavra_o_registro_com_as_partes_e_a_compradora_vira_titular(casa):
    """O R-1 de compra e venda inteiro pela tela do modelo: os campos do
    título, a qualificação da adquirente (que só o título diz, e a parte fixa
    deixava como marcador), as duas partes, o valor declarado e o item 16.3.14
    do protocolo geral — selado, com a frase do protocolo da prenotação do
    título (CN-MA arts. 443, § 1º, e 458), a minuta de onde saiu marcada como
    lavrada e a compradora no quadro de titulares (LRP art. 19, § 9º)."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    modelo = MODELOS_DE_ATO.por_codigo("R-COMPRA-VENDA")
    valores = {"c_" + x["chave"]: COMPRA_E_VENDA[x["marcador"]]
               for x in MODELOS_DE_ATO.campos_do_modelo(modelo) if x["natureza"] == "texto"}
    adquirente = (f"{COMPRADORA['nome']}, {COMPRADORA['qualificacao']}, inscrita no "
                  f"CPF sob o nº {COMPRADORA['cpf_fmt']}")
    pronto = _preencher(
        casa, m, "R-COMPRA-VENDA", acao="lavrar", adquirentes=adquirente,
        base_calculo="100.000,00",
        parte_nome=[VENDEDOR["nome"], COMPRADORA["nome"]],
        parte_documento=[VENDEDOR["cpf_fmt"], COMPRADORA["cpf_fmt"]],
        parte_papel=["transmitente", "adquirente"],
        parte_qualificacao=[VENDEDOR["qualificacao"], COMPRADORA["qualificacao"]],
        parte_documento_tipo=["CPF", "CPF"], **valores)
    enviados = _o_que_a_tela_manda(pronto)
    assert enviados["protocolo"] == [str(p["numero"])]
    assert enviados["protocolo_item_id"] == [str(_item(casa, cx, "16.3.14")["id"])]
    ficha = f"/registro-imoveis/{m['id']}"
    html = _clicar(casa["balcao"], ficha, f"{ficha}/atos", **enviados)

    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
              (m["id"],))
    assert ato and ato["selo_texto"], _recados(html)
    assert (ato["tipo"], ato["numero"], ato["modelo_codigo"]) == ("R", 1, "R-COMPRA-VENDA")
    assert adquirente in ato["teor"]
    assert f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}" in ato["teor"]
    assert not re.search(r"\[[^\]]+\]", ato["teor"]), ato["teor"]
    assert _um(casa, "SELECT item_id FROM cx_selo_coberturas WHERE tabela='ri_atos' AND ato_id=%s",
               (ato["id"],))["item_id"] == _item(casa, cx, "16.3.14")["id"]
    minuta = _um(casa, "SELECT situacao, ato_id FROM ri_minutas WHERE matricula_id=%s "
                       "ORDER BY id DESC LIMIT 1", (m["id"],))
    assert minuta == {"situacao": "LAVRADA", "ato_id": ato["id"]}
    titulares = [x["nome"] for x in _ler(
        casa, """SELECT nome FROM ri_partes WHERE matricula_id=%s AND proprietario_ativo=1
                  ORDER BY id""", (m["id"],))]
    assert titulares == [COMPRADORA["nome"]], titulares


def test_a_recusa_da_lavratura_pela_tela_do_modelo_volta_para_a_minuta_com_o_texto(casa):
    """«O texto preenchido se perde» era a outra metade do defeito: a recusa
    voltava para a ficha crua. Com o item desmarcado na tela, a lavratura
    recusa (falta o item de custa) — e a ficha abre na minuta que a tela
    guardou, com o texto dentro, sem nada lavrado."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    campos = {"c_" + x["chave"]: _valor_de_exemplo(x["marcador"]) or "x"
              for x in MODELOS_DE_ATO.campos_do_modelo(
                  MODELOS_DE_ATO.por_codigo("AV-CONSTRUCAO"))}
    enviados = _o_que_a_tela_manda(_preencher(casa, m, "AV-CONSTRUCAO", acao="lavrar",
                                              itens_da_tela="1", **campos))
    assert "protocolo_item_id" not in enviados, "o item desmarcado foi junto"
    ficha = f"/registro-imoveis/{m['id']}"
    html = _clicar(casa["balcao"], ficha, f"{ficha}/atos", **enviados)
    assert "Escolha o item da tabela de custas" in _recados(html), _recados(html)
    assert not _atos_da_ficha(casa, m["id"])
    minuta = _um(casa, "SELECT * FROM ri_minutas WHERE matricula_id=%s ORDER BY id DESC LIMIT 1",
                 (m["id"],))
    assert minuta and minuta["situacao"] == "A_REVISAR"
    assert minuta["modelo_codigo"] == "AV-CONSTRUCAO"
    assert minuta["teor"] == enviados["teor"][0]
    assert _teor_da_caixa(html) == enviados["teor"][0], "a ficha não abriu na minuta"


def test_a_tela_do_modelo_nao_manda_ao_livro_campo_do_modelo_em_branco(casa):
    """O campo do modelo em branco não vai, nem com «Lavrar mesmo assim»: a
    lavratura o recusaria (LRP art. 176, § 1º, III), e a marca que confirmava
    ficaria prometendo o que não acontece. Nada se guarda nem se lavra."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    campos = {"c_" + x["chave"]: _valor_de_exemplo(x["marcador"]) or "x"
              for x in MODELOS_DE_ATO.campos_do_modelo(
                  MODELOS_DE_ATO.por_codigo("AV-CONSTRUCAO"))}
    campos["c_numero_do_habite_se"] = ""
    pronto = _preencher(casa, m, "AV-CONSTRUCAO", acao="lavrar",
                        confirmar_pendencias="1", **campos)
    assert 'id="form-lavrar"' not in pronto
    assert "[NUMERO DO HABITE-SE]" in _recados(pronto), _recados(pronto)
    assert not _ler(casa, "SELECT id FROM ri_minutas WHERE matricula_id=%s ORDER BY id",
                    (m["id"],))


def test_o_colchete_que_nao_e_do_modelo_continua_indo_ao_livro(casa):
    """A recusa é dos campos DO MODELO informado: o colchete que o escrevente
    escreveu de propósito (o acervo transcrito tem «[rubrica]») não é campo de
    modelo nenhum, e o R-1 se lavra com ele."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    m = _abrir_matricula(casa, p)
    valores = dict(COMPRA_E_VENDA)
    valores["INFORMAR O PROTOCOLO"] = (
        f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}")
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = f"{COMPRADORA['nome']}, qualificada no título"
    teor = _teor_do_modelo(casa, m["id"], "R-COMPRA-VENDA", valores)
    teor += " Consta no título a assinatura do vendedor [rubrica]."
    html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda", prenotacao=p,
                   cx=cx, itens=["16.3.14"], base_calculo="100.000,00",
                   partes=[(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")],
                   modelo="R-COMPRA-VENDA")
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s", (m["id"],))
    assert ato and ato["selo_texto"] and "[rubrica]" in ato["teor"], _recados(html)


def test_todo_colchete_que_a_parte_fixa_escreve_a_lavratura_reconhece(casa):
    """Numa ficha sem prenotação, sem titular e sem logradouro, a parte fixa
    dos modelos escreve o marcador do que não sabe (o protocolo, as partes, o
    imóvel, o adquirente). Cada colchete que sobra no texto de cada um dos 25
    modelos tem de estar entre os que a lavratura recusa
    (`ri_modelos_atos.por_preencher`) — senão o marcador novo de amanhã
    passaria calado para o livro."""
    with casa["db"].transaction() as con:
        mid = banco(con).escrever(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                   tipo_ficha, criado_em)
               VALUES ('4999', '2', '2', 'ATIVO', 'ESTRUTURADA', '2026-10-21T08:00')
               RETURNING id""")[0]["id"]
    vistos = set()
    for modelo in MODELOS_DE_ATO.MODELOS:
        r = casa["balcao"].get(f"/registro-imoveis/{mid}/modelo/{modelo['codigo']}")
        teor = json.loads(r.get_data(as_text=True))["teor"]
        sobram = {"[" + " ".join(x.split()) + "]" for x in re.findall(r"\[([^\[\]]+)\]", teor)}
        recusados = set(MODELOS_DE_ATO.por_preencher(teor, modelo["codigo"]))
        assert sobram <= recusados, (modelo["codigo"], sorted(sobram - recusados))
        vistos |= sobram
    # e a ficha vazia de fato fez a parte fixa escrever os marcadores dela
    assert {"[INFORMAR O PROTOCOLO]", "[QUALIFICAR AS PARTES]", "[DESCREVER]"} <= vistos
    assert any(x.startswith("[QUALIFICAR O(S) ADQUIRENTE(S)") for x in vistos)


# O DUPLO «ENVIAR» E A MINUTA PRESA — LD10, 21/10/2026 (ressalvas da revisão do
# LD03). O número da minuta só volta na tela depois do primeiro envio; o clique
# duplo manda os dois sem ele. A tela leva a marca do envio (`envio`), e a
# minuta se guarda sob a trava da ficha, presa antes de se conferir a situação.

def _construcao_pela_tela(casa) -> dict:
    """O título da averbação de construção pago e prenotado, a ficha aberta, a
    tela do modelo e os campos que o escrevente preenche."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 1)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    campos = {"c_" + x["chave"]: _valor_de_exemplo(x["marcador"]) or "x"
              for x in MODELOS_DE_ATO.campos_do_modelo(
                  MODELOS_DE_ATO.por_codigo("AV-CONSTRUCAO"))}
    return {"cx": cx, "p": p, "m": m, "campos": campos,
            "tela": f"/registro-imoveis/{m['id']}/preencher/AV-CONSTRUCAO"}


def _abrir_a_tela(c, tela: str) -> dict:
    """O que o navegador guarda da tela aberta: o token e a marca do envio."""
    html = c.get(tela).get_data(as_text=True)
    envio = re.search(r'name="envio" value="([0-9a-f]+)"', html)
    assert envio, "a tela do modelo não trouxe a marca do envio"
    return {"csrf_token": _token(html), "envio": envio.group(1)}


def _minutas(casa, matricula_id: int) -> list[dict]:
    return _ler(casa, """SELECT id, situacao, teor, ato_id FROM ri_minutas
                          WHERE matricula_id=%s ORDER BY id""", (matricula_id,))


def test_o_clique_duplo_em_enviar_da_tela_do_modelo_guarda_uma_minuta_so(casa, monkeypatch):
    """Os dois envios da MESMA tela (a mesma marca) chegam juntos, os dois sem
    o número da minuta, e passam juntos pela leitura que a rota faz fora da
    transação: uma minuta só, e as duas respostas mandam lavrar a mesma."""
    import threading

    import caixa_protocolo
    t = _construcao_pela_tela(casa)
    abas = [_entrar(casa["app"], ESCREVENTE) for _ in range(2)]
    abertas = [_abrir_a_tela(c, t["tela"]) for c in abas]
    envio = abertas[0]["envio"]
    juntas = threading.Barrier(2, timeout=60)
    de_verdade = caixa_protocolo.prenotacoes_abertas

    def prenotacoes_abertas(*a, **k):
        juntas.wait()
        return de_verdade(*a, **k)
    monkeypatch.setattr(caixa_protocolo, "prenotacoes_abertas", prenotacoes_abertas)

    respostas = []

    def enviar(c, aberta):
        r = c.post(t["tela"], data={**t["campos"], "csrf_token": aberta["csrf_token"],
                                    "envio": envio, "acao": "lavrar",
                                    "confirmar_pendencias": "1"})
        respostas.append(r.get_data(as_text=True))
    fios = [threading.Thread(target=enviar, args=par) for par in zip(abas, abertas)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(120)
    monkeypatch.setattr(caixa_protocolo, "prenotacoes_abertas", de_verdade)

    minutas = _minutas(casa, t["m"]["id"])
    assert len(minutas) == 1, f"{len(minutas)} minutas para o mesmo envio"
    mandadas = [_o_que_a_tela_manda(html)["minuta_id"] for html in respostas]
    assert mandadas == [[str(minutas[0]["id"])]] * 2, mandadas


def test_a_minuta_da_tela_do_modelo_se_guarda_presa_e_dentro_da_trava_da_ficha(
        casa, monkeypatch):
    """Quando a minuta se cria, a trava da ficha (`ri_minutas.modelo:<id>`) já é
    desta transação; quando se atualiza pelo número que a tela devolveu, a
    linha já está presa — a lavratura em outra aba espera, e o texto desta tela
    não cai por cima do que foi ao livro. Visto de dentro (a trava, no
    `pg_locks` do próprio processo) e de fora (a linha, por `NOWAIT`)."""
    import psycopg

    import banco_pg
    import ri_minuta as RIMIN
    t = _construcao_pela_tela(casa)
    chave = f"ri_minutas.modelo:{int(t['m']['id'])}"
    vistos = []

    def olhar(con, minuta_id=None):
        bd = banco(con)
        trava = bool(bd.valor(
            """SELECT count(*) AS n FROM pg_locks
                WHERE locktype = 'advisory' AND pid = pg_backend_pid() AND granted
                  AND objsubid = 1
                  AND classid::bigint = ((hashtext(%s)::bigint >> 32) & 4294967295)
                  AND objid::bigint = (hashtext(%s)::bigint & 4294967295)""",
            (chave, chave)))
        presa = None
        if minuta_id is not None:
            esquema = bd.valor("SELECT current_schema() AS s")
            with psycopg.connect(banco_pg.dsn(), autocommit=True) as vigia:
                vigia.execute(f'SET search_path TO "{esquema}", public')
                try:
                    vigia.execute("SELECT id FROM ri_minutas WHERE id=%s FOR UPDATE NOWAIT",
                                  (int(minuta_id),))
                    presa = False
                except psycopg.errors.LockNotAvailable:
                    presa = True
        vistos.append({"trava": trava, "linha_presa": presa})

    criar, atualizar = RIMIN.criar, RIMIN.atualizar

    def criar_vigiado(con, **campos):
        olhar(con)
        return criar(con, **campos)

    def atualizar_vigiado(con, minuta_id, **campos):
        olhar(con, minuta_id)
        return atualizar(con, minuta_id, **campos)
    monkeypatch.setattr(RIMIN, "criar", criar_vigiado)
    monkeypatch.setattr(RIMIN, "atualizar", atualizar_vigiado)

    c = casa["balcao"]
    aberta = _abrir_a_tela(c, t["tela"])
    envio = {**t["campos"], "envio": aberta["envio"], "acao": "lavrar",
             "confirmar_pendencias": "1"}
    primeira = _clicar(c, t["tela"], t["tela"], **envio)
    guardada = _o_que_a_tela_manda(primeira)["minuta_id"][0]
    _clicar(c, t["tela"], t["tela"], **envio, minuta_guardada=guardada)
    assert vistos == [{"trava": True, "linha_presa": None},
                      {"trava": True, "linha_presa": True}], vistos


def test_a_tela_que_volta_depois_da_lavratura_nao_escreve_na_minuta_lavrada(casa):
    """A minuta da tela foi ao livro; a mesma tela (a mesma marca, o mesmo
    número) é enviada de novo. A lavrada continua dizendo o que o ato diz — a
    procedência —, e o envio novo vira outra minuta, a revisar."""
    t = _construcao_pela_tela(casa)
    c = casa["balcao"]
    aberta = _abrir_a_tela(c, t["tela"])
    envio = {**t["campos"], "envio": aberta["envio"], "acao": "lavrar",
             "confirmar_pendencias": "1"}
    enviados = _o_que_a_tela_manda(_clicar(c, t["tela"], t["tela"], **envio))
    ficha = f"/registro-imoveis/{t['m']['id']}"
    _clicar(c, ficha, f"{ficha}/atos", **enviados)
    ato = _um(casa, "SELECT id, teor FROM ri_atos WHERE matricula_id=%s", (t["m"]["id"],))
    assert ato, "a averbação da tela do modelo não foi lavrada"
    lavrada = _minutas(casa, t["m"]["id"])

    campos = dict(envio, c_numero_do_habite_se="2026/000777")
    _clicar(c, t["tela"], t["tela"], **campos, minuta_guardada=enviados["minuta_id"][0])
    minutas = _minutas(casa, t["m"]["id"])
    assert [(x["situacao"], x["ato_id"]) for x in minutas] == [
        ("LAVRADA", ato["id"]), ("A_REVISAR", None)], minutas
    assert minutas[0] == lavrada[0], "o envio novo escreveu na minuta lavrada"
    assert "2026/000777" in minutas[1]["teor"] and "2026/000777" not in ato["teor"]


def test_duas_abas_lavrando_a_mesma_minuta_lavram_um_ato_so(casa, monkeypatch):
    """A minuta da tela do modelo aberta em duas abas, «Lavrar» nas duas ao
    mesmo tempo: as duas passam pela conferência que a rota faz antes da
    transação («a minuta ainda está a revisar»). Achado do LD10 ao prender a
    minuta da tela do modelo: a lavratura não a conferia de novo, e saíam DOIS
    atos do mesmo texto, com dois selos — e a minuta apontando só para o
    segundo. A segunda aba tem de parar na conferência PRESA, dentro da trava
    da numeração.

    O ITEM TEM DUAS UNIDADES DE PROPÓSITO, como no clique duplo do
    cancelamento: com uma, a segunda aba pararia no selo sem item, e o teste
    não mediria a conferência presa."""
    import threading

    import ri_minuta as RIMIN
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1), ("16.22.2", 2)])
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Construção",
                  objeto="Averbação de construção — Rua Exemplo, 30")
    m = _abrir_matricula(casa, p)
    campos = {"c_" + x["chave"]: _valor_de_exemplo(x["marcador"]) or "x"
              for x in MODELOS_DE_ATO.campos_do_modelo(
                  MODELOS_DE_ATO.por_codigo("AV-CONSTRUCAO"))}
    enviados = _o_que_a_tela_manda(_preencher(casa, m, "AV-CONSTRUCAO", acao="lavrar",
                                              confirmar_pendencias="1", **campos))
    ficha = f"/registro-imoveis/{m['id']}"
    abas = [_entrar(casa["app"], ESCREVENTE) for _ in range(2)]
    tokens = [_token(c.get(ficha).get_data(as_text=True)) for c in abas]
    juntas = threading.Barrier(2, timeout=60)
    de_verdade = RIMIN.uma

    def uma(con, minuta_id):
        achada = de_verdade(con, minuta_id)
        juntas.wait()
        return achada
    monkeypatch.setattr(RIMIN, "uma", uma)

    respostas = []

    def lavrar(c, token):
        r = c.post(f"{ficha}/atos", data={**enviados, "csrf_token": token})
        respostas.append(r.status_code)
    fios = [threading.Thread(target=lavrar, args=par) for par in zip(abas, tokens)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(120)
    monkeypatch.setattr(RIMIN, "uma", de_verdade)
    assert respostas == [302, 302], respostas

    atos = _atos_da_ficha(casa, m["id"])
    assert len(atos) == 1, f"{len(atos)} atos lavrados da mesma minuta"
    minuta = _um(casa, "SELECT situacao, ato_id FROM ri_minutas WHERE id=%s",
                 (int(enviados["minuta_id"][0]),))
    assert minuta == {"situacao": "LAVRADA", "ato_id": atos[0]["id"]}
    assert _um(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id=%s",
               (_item(casa, cx, "16.22.2")["id"],))["quantidade_usada"] == 1


# UMA MINUTA A REVISAR POR MARCA — LD13, 21/10/2026 (ressalva 5 da revisão do
# LD10). A marca do envio (`origem_chave`) pode ficar em mais de uma minuta da
# ficha: a lavrada ou descartada e a que a mesma tela mandou depois. Só uma
# pode estar a revisar; senão a fila mostra duas com o mesmo texto e ninguém
# sabe qual lavrar. Quem garante é a trava da ficha (`ri_minutas.modelo:<id>`)
# e a busca pela que está A REVISAR, e não pela mais nova.

def _a_revisar_da_marca(casa, matricula_id: int, envio: str) -> list[dict]:
    return _ler(casa, """SELECT id, teor FROM ri_minutas
                          WHERE matricula_id=%s AND origem_chave=%s AND situacao='A_REVISAR'
                          ORDER BY id""",
                (matricula_id, f"modelo:AV-CONSTRUCAO:{envio}"))


def test_a_tela_reenviada_acha_a_minuta_a_revisar_da_marca_mesmo_com_uma_descartada_mais_nova(
        casa):
    """A corrida que deixa isto: a aba A lavra a minuta e o selo ainda não
    voltou; a aba B reenvia a mesma tela, acha a minuta lavrada e cria a sua;
    o selo da A falha e a suspensão (`voltar_do_ato`) devolve a primeira à
    fila. Descartada a da B, ficam a primeira A REVISAR e uma descartada MAIS
    NOVA com a mesma marca. A tela reenviada atualiza a primeira; buscando só
    a mais nova, ela criava uma segunda a revisar."""
    import ri_minuta as RIMIN
    t = _construcao_pela_tela(casa)
    c, m = casa["balcao"], t["m"]
    aberta = _abrir_a_tela(c, t["tela"])
    envio = {**t["campos"], "envio": aberta["envio"], "acao": "lavrar",
             "confirmar_pendencias": "1"}
    _clicar(c, t["tela"], t["tela"], **envio)
    (primeira,) = _a_revisar_da_marca(casa, m["id"], aberta["envio"])
    with casa["db"].transaction() as con:
        da_outra_aba = RIMIN.criar(
            con, matricula_id=m["id"], tipo="AV", teor="O texto da outra aba.",
            agora=f"{date.today().isoformat()} 10:00:00",
            modelo_codigo="AV-CONSTRUCAO", origem=RIMIN.MANUAL,
            origem_chave=f"modelo:AV-CONSTRUCAO:{aberta['envio']}")
        RIMIN.descartar(con, da_outra_aba, motivo="Repetida pela outra aba do balcão",
                        agora=f"{date.today().isoformat()} 10:01:00")

    _clicar(c, t["tela"], t["tela"], **dict(envio, c_numero_do_habite_se="2026/000888"))
    ativas = _a_revisar_da_marca(casa, m["id"], aberta["envio"])
    assert [x["id"] for x in ativas] == [primeira["id"]], ativas
    assert "2026/000888" in ativas[0]["teor"], "a tela não escreveu na minuta a revisar"


def test_o_clique_duplo_depois_da_minuta_descartada_deixa_uma_a_revisar_so(casa, monkeypatch):
    """A minuta da tela foi descartada pelo oficial, e o balcão manda a MESMA
    tela de novo com o clique duplo: os dois envios acham a descartada e
    passam juntos pela leitura de fora da transação. A trava da ficha põe um
    atrás do outro — o segundo acha a que o primeiro criou e a atualiza."""
    import threading

    import caixa_protocolo
    t = _construcao_pela_tela(casa)
    m = t["m"]
    abas = [_entrar(casa["app"], ESCREVENTE) for _ in range(2)]
    abertas = [_abrir_a_tela(c, t["tela"]) for c in abas]
    envio = abertas[0]["envio"]
    campos = {**t["campos"], "envio": envio, "acao": "lavrar", "confirmar_pendencias": "1"}
    _clicar(abas[0], t["tela"], t["tela"], **campos)
    (descartada,) = _a_revisar_da_marca(casa, m["id"], envio)
    ficha = f"/registro-imoveis/{m['id']}"
    _clicar(casa["oficial"], ficha, f"/registro-imoveis/minuta/{descartada['id']}/descartar",
            motivo="O título foi devolvido: refazer o texto")
    assert not _a_revisar_da_marca(casa, m["id"], envio)

    juntas = threading.Barrier(2, timeout=60)
    de_verdade = caixa_protocolo.prenotacoes_abertas

    def prenotacoes_abertas(*a, **k):
        juntas.wait()
        return de_verdade(*a, **k)
    monkeypatch.setattr(caixa_protocolo, "prenotacoes_abertas", prenotacoes_abertas)

    def enviar(c, aberta):
        c.post(t["tela"], data={**campos, "csrf_token": aberta["csrf_token"]})
    fios = [threading.Thread(target=enviar, args=par) for par in zip(abas, abertas)]
    for fio in fios:
        fio.start()
    for fio in fios:
        fio.join(120)
    monkeypatch.setattr(caixa_protocolo, "prenotacoes_abertas", de_verdade)

    assert len(_a_revisar_da_marca(casa, m["id"], envio)) == 1, (
        _minutas(casa, m["id"]))


# O NÚMERO DIGITADO TEM TAMANHO — LD10, 21/10/2026 (ressalva da revisão do
# LD03). Com mais de 4.300 dígitos o Python recusa `int(...)` e a rota caía na
# tela de erro (medido: cancelamento, lavratura, tela do modelo, ficha e
# prenotação); acima de 18, o número não cabe no banco.

@pytest.mark.parametrize("digitado,numero", [
    ("42", 42), (" 0042 ", 42),
    pytest.param("9" * 18, int("9" * 18), id="18-digitos"),
    pytest.param("9" * 19, None, id="19-noves"),
    pytest.param("1" * 19, None, id="19-uns"),
    pytest.param("9" * 5000, None, id="5000-digitos"),
    pytest.param("0" * 30 + "7", 7, id="zeros-na-frente"),
    # LD13: os zeros saem antes do `int()` — com eles, 5.001 dígitos caíam.
    pytest.param("0" * 5000 + "5", 5, id="5000-zeros-na-frente"),
    pytest.param("000", 0, id="so-zeros"), (0, 0),
    ("11.534", None), ("²", None), ("", None), (None, None),
])
def test_o_numero_digitado_so_vale_se_cabe_no_banco(digitado, numero):
    from ri_web import numero_digitado
    assert numero_digitado(digitado) == numero


def test_o_protocolo_gigante_digitado_nao_derruba_tela_nenhuma_do_ri(casa):
    """Um número de 5.000 dígitos no protocolo do cancelamento e da lavratura,
    na prenotação da tela do modelo e nos endereços da ficha e da prenotação:
    nenhuma tela cai, e o número que não existe não acha nem amarra prenotação
    nenhuma — é o «não achei» do texto que não é número."""
    gigante = "9" * 5000
    t = _para_cancelar(casa)
    m, p, c = t["matricula"], t["p"], casa["oficial"]
    antes = _atos_da_ficha(casa, m["id"])

    token = _token(c.get(t["ficha"]).get_data(as_text=True))
    r = c.post(f"/registro-imoveis/atos/{t['r2']['id']}/cancelar",
               data={"csrf_token": token, "motivo": FUNDAMENTO_DO_CANCELAMENTO,
                     "data_ato": date.today().isoformat(), "protocolo": gigante})
    assert r.status_code == 302, f"o cancelamento caiu: {r.status_code}"
    assert _atos_da_ficha(casa, m["id"]) == antes

    token = _token(c.get(t["ficha"]).get_data(as_text=True))
    r = c.post(f"{t['ficha']}/atos", data={
        "csrf_token": token, "tipo": "AV", "data_ato": date.today().isoformat(),
        "natureza_titulo": "Construção", "protocolo": gigante,
        "teor": "AVERBAÇÃO DE CONSTRUÇÃO de prédio residencial com 80,00 m² na Rua Exemplo, 30.",
        "protocolo_id": str(t["cx"]["id"]),
        "protocolo_item_id": [str(_item(casa, t["cx"], "16.22.2")["id"])]})
    assert r.status_code == 302, f"a lavratura caiu: {r.status_code}"
    assert _um(casa, "SELECT ato_id FROM ri_protocolos WHERE id=%s", (p["id"],))["ato_id"] is None

    tela = f"{t['ficha']}/preencher/AV-CONSTRUCAO"
    token = _token(c.get(tela).get_data(as_text=True))
    r = c.post(tela, data={"csrf_token": token, "prenotacao_id": gigante, "acao": "previa"})
    assert r.status_code == 200, f"a tela do modelo caiu: {r.status_code}"
    for endereco in (f"{t['ficha']}?lavrar=1&prenotacao_id={gigante}",
                     f"{t['ficha']}?lavrar=1&protocolo_id={gigante}",
                     f"{t['ficha']}?minuta={gigante}",
                     f"/registro-imoveis/protocolo?cx={gigante}"):
        assert c.get(endereco).status_code == 200, endereco[:80]


# O MESMO 500 NO RESTO DO RI — LD13, 21/10/2026 (ressalva 3 da revisão do
# LD10, «nenhuma pendência»). `int(...)` direto sobre o que a tela mandou:
# «abc» vira `ValueError`; o «²» passa pelo `isdigit()` e o `int()` o recusa;
# 30 dígitos passam pelos dois e estouram no banco (o OFFSET da página, a
# numeração do livro, a decisão do CNIB, o número do ato de acervo); 5.000
# dígitos o próprio Python recusa. Todos passam por `numero_digitado`.

_NAO_E_NUMERO = [pytest.param("abc", id="abc"), pytest.param("9" * 30, id="30-digitos"),
                 pytest.param("9" * 5000, id="5000-digitos"), pytest.param("²", id="expoente")]


def _ficha_do_acervo(casa) -> dict:
    """Uma ficha de ACERVO, como a carga do E-Ofício a deixa: a casa já a tem
    antes de abrir a porta (o número do ato dela vem do livro físico)."""
    with casa["db"].transaction() as con:
        novo = banco(con).escrever(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, tipo_ficha,
                                          data_abertura, criado_em)
               VALUES ('100', '2', '2', 'ACERVO', '1990-01-02', '1990-01-02 08:00:00')
               RETURNING id""")[0]["id"]
    return _um(casa, "SELECT * FROM ri_matriculas WHERE id=%s", (novo,))


def _pagina_digitalizada(casa, matricula_id: int, pasta: Path) -> dict:
    """Uma página digitalizada da ficha (TIFF de verdade, mínimo), como a
    carga das imagens do E-Ofício a deixa."""
    from PIL import Image
    arquivo = pasta / "ficha-0001.tif"
    Image.new("1", (8, 8)).save(arquivo, "TIFF")
    with casa["db"].transaction() as con:
        novo = banco(con).escrever(
            """INSERT INTO ri_imagens (matricula_id, nome_arquivo, caminho, ordem)
               VALUES (%s, %s, %s, 1) RETURNING id""",
            (matricula_id, arquivo.name, str(arquivo)))[0]["id"]
    return _um(casa, "SELECT * FROM ri_imagens WHERE id=%s", (novo,))


@pytest.mark.parametrize("digitado", _NAO_E_NUMERO)
def test_o_numero_que_nao_e_numero_nao_derruba_rota_nenhuma_do_ri(casa, digitado, tmp_path):
    """Cada rota do RI que convertia o número digitado com `int(...)`, com o
    texto ruim no lugar: nenhuma cai, e nenhuma grava — o texto que não é
    número de até 18 dígitos é o mesmo «não achei» de sempre."""
    t = _para_cancelar(casa)
    m, p, r2, c = t["matricula"], t["p"], t["r2"], casa["oficial"]
    ficha, hoje = t["ficha"], date.today().isoformat()
    acervo = _ficha_do_acervo(casa)
    pagina = _pagina_digitalizada(casa, m["id"], tmp_path)
    numeracao = _ler(casa, "SELECT * FROM ri_numeracao ORDER BY livro")
    prenotacoes = _ler(casa, "SELECT id, situacao FROM ri_protocolos ORDER BY id")
    atos = _ler(casa, "SELECT id, numero, cancelado FROM ri_atos ORDER BY id")
    caidas = []

    def pedir(rota: str, **campos) -> str:
        """POST com o token da sessão (ou GET sem campos), seguindo o recado."""
        if campos:
            token = _token(c.get(ficha).get_data(as_text=True))
            r = c.post(rota, data={"csrf_token": token, **campos}, follow_redirects=True)
        else:
            r = c.get(rota, follow_redirects=True)
        if r.status_code != 200:
            caidas.append(f"{rota.split('?')[0]} → {r.status_code}")
        return _recados(r.get_data(as_text=True)) if r.mimetype == "text/html" else ""

    encerrar = pedir("/registro-imoveis/protocolo", acao="encerrar", protocolo_id=digitado,
                     motivo="Título devolvido ao apresentante", situacao="ENCERRADO")
    prenotar = pedir("/registro-imoveis/protocolo", livro_destino="2", cx_protocolo_id=digitado,
                     apresentante=COMPRADORA["nome"], apresentante_documento=COMPRADORA["cpf"],
                     telefone="(99) 90000-0000", natureza_titulo="Compra e venda",
                     objeto="Imóvel urbano na Rua Exemplo, 30")
    pedir(f"/registro-imoveis/atos/{r2['id']}/cancelar", motivo=FUNDAMENTO_DO_CANCELAMENTO,
          data_ato=hoje, protocolo=digitado, protocolo_id=digitado,
          protocolo_item_id=[digitado])
    pedir(f"{ficha}/atos", tipo="AV", data_ato=hoje, natureza_titulo="Construção",
          protocolo=digitado, protocolo_id=digitado, protocolo_item_id=[digitado],
          teor="AVERBAÇÃO DE CONSTRUÇÃO de prédio residencial com 80,00 m².")
    pedir(f"{ficha}/preencher/AV-CONSTRUCAO", acao="previa", itens_da_tela="1",
          protocolo_item_id=[digitado], prenotacao_id=digitado)
    pedir("/registro-imoveis/cnib/pendentes", matricula_id=digitado,
          protocolo_cnib="CNIB-EXEMPLO-1", pessoa_nome="FULANO EXEMPLO", criterio="nome",
          motivo="Conferido pelo CPF: é outra pessoa, de outro município.")
    pedir("/registro-imoveis/numeracao", livro="2", proximo_numero=digitado,
          observacao="Teste do número digitado")
    pedir(f"/registro-imoveis/{acervo['id']}/atos", tipo="AV", numero=digitado,
          data_ato=hoje, natureza_titulo="Construção",
          teor="AVERBAÇÃO DE CONSTRUÇÃO de prédio residencial com 80,00 m².")
    pedir(f"/registro-imoveis/{m['id']}/imagens", acao="excluir", imagem_id=digitado)
    pedir(f"/registro-imoveis/{m['id']}/imagens", acao="ordem",
          imagem_id=str(pagina["id"]), ordem=digitado)
    for endereco in (f"/registro-imoveis?pagina={digitado}",
                     f"/registro-imoveis/indicador-real?pagina={digitado}",
                     f"/registro-imoveis/imagem/{pagina['id']}?p={digitado}"):
        pedir(endereco)

    assert not caidas, "; ".join(caidas)
    assert "marcado como" not in encerrar, encerrar
    assert "protocolo geral indicado não existe" in prenotar, prenotar
    assert _ler(casa, "SELECT * FROM ri_numeracao ORDER BY livro") == numeracao
    assert _ler(casa, "SELECT id, situacao FROM ri_protocolos ORDER BY id") == prenotacoes
    assert _ler(casa, "SELECT id, numero, cancelado FROM ri_atos ORDER BY id") == atos
    assert not _ler(casa, "SELECT id FROM ri_cnib_decisoes ORDER BY id")
    assert _ler(casa, "SELECT id, ordem FROM ri_imagens ORDER BY id") == [
        {"id": pagina["id"], "ordem": 1}]


@pytest.mark.parametrize("digitado", _NAO_E_NUMERO)
def test_a_pagina_das_matriculas_digitadas_em_word_nao_cai_com_o_numero_que_nao_e_numero(
        casa, digitado):
    """A lista das matrículas digitadas em Word (`?pagina=`) só se monta com o
    arquivo da conferência no lugar; vazio basta para chegar à página."""
    db = casa["db"]
    raiz = Path((db.get_setting("archive_root", "") or "").strip()
                or (Path(db.db_path).parent / "arquivos")) / "ri"
    raiz.mkdir(parents=True, exist_ok=True)
    (raiz / "matriculas_doc.jsonl").write_text("", encoding="utf-8")
    r = casa["oficial"].get(f"/registro-imoveis/matriculas-doc?pagina={digitado}")
    assert r.status_code == 200, r.status_code


# =============================================== o depósito prévio

def test_o_deposito_previo_do_titulo_paga_a_abertura_e_o_registro_no_selo(casa):
    """O RI cobra por depósito prévio (CNN art. 329, § 2º; CN-MA arts. 454 e
    456): a prenotação se paga no caixa, o depósito entra na tela do título
    e, na hora de cada selo, o item do protocolo se paga com ele — a abertura
    pelo protocolo em atendimento, o R-1 pelo item ligado ao ato. O saldo
    que sobra é o que a casa devolve."""
    cx = _protocolo_geral(casa, interessado=COMPRADORA, pagar=False,
                          itens=[("16.1", 1), ("16.2", 1), ("16.3.14", 1)])
    c = casa["balcao"]
    ficha_cx = f"/caixa/protocolos/{cx['id']}"
    _abrir_o_caixa_do_dia(c)
    html = _clicar(c, ficha_cx, f"{ficha_cx}/itens", acao="quitar",
                   item_id=str(_item(casa, cx, "16.1")["id"]))
    assert "Item quitado" in html
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    assert p["selo_prenotacao"], p["recado"][:800]
    html = _clicar(c, f"/registro-imoveis/protocolo/{p['id']}",
                   f"/registro-imoveis/protocolo/{p['id']}", acao="deposito",
                   valor="2.000,00", depositante=COMPRADORA["nome"],
                   depositante_documento=COMPRADORA["cpf"], forma_pagamento="PIX")
    assert "registrado no título" in html, html[:900]
    dep = _um(casa, "SELECT * FROM cx_depositos WHERE ri_protocolo_id=%s", (p["id"],))
    assert dep and dep["valor"] == "2.000,00"

    m = _abrir_matricula(casa, p)
    valores = dict(COMPRA_E_VENDA)
    valores["INFORMAR O PROTOCOLO"] = (
        f"PROTOCOLO N. {p['numero']}, DE {date.today().strftime('%d/%m/%Y')}")
    valores["QUALIFICAR O(S) ADQUIRENTE(S)*"] = (
        f"{COMPRADORA['nome']}, {COMPRADORA['qualificacao']}, inscrita no CPF "
        f"sob o nº {COMPRADORA['cpf_fmt']}")
    teor = _teor_do_modelo(casa, m["id"], "R-COMPRA-VENDA", valores)
    html = _lavrar(casa, m, tipo="R", teor=teor, natureza="Compra e venda",
                   prenotacao=p, cx=cx, itens=["16.3.14"], base_calculo="100.000,00",
                   partes=[(VENDEDOR, "transmitente"), (COMPRADORA, "adquirente")],
                   modelo="R-COMPRA-VENDA")
    ato = _um(casa, "SELECT * FROM ri_atos WHERE matricula_id=%s", (m["id"],))
    assert ato and ato["selo_texto"], html[:1200]

    # os dois itens pagos pelo depósito, e o saldo que sobra
    for codigo in ("16.2", "16.3.14"):
        it = _item(casa, cx, codigo)
        assert it["quitado"] == 1 and "DEPÓSITO" in (it["quitado_por"] or ""), it
    gasto = sum(_centavos_do_item(cod, 1)["total"] for cod in ("16.2", "16.3.14"))
    depois = _um(casa, "SELECT saldo FROM cx_depositos WHERE id=%s", (dep["id"],))
    assert depois["saldo"] == reais(200000 - gasto), (depois, reais(200000 - gasto))
    formas = {r["forma"] for r in _ler(
        casa, "SELECT forma FROM cx_selo_coberturas WHERE tabela IN "
              "('ri_matriculas','ri_atos') ORDER BY id")}
    assert formas == {"DEPOSITO"}, formas


# =============================================== a certidão que espera o selo


def test_a_certidao_sem_protocolo_atendido_espera_o_selo_e_sela_depois(casa):
    """22/10/2026, dia da 3.7.0 na produção: a escrevente quitou o protocolo
    2026.10.61 e as certidões 83 e 84 da matrícula 3252 foram CANCELADAS
    sozinhas — o protocolo pago não estava marcado como «em atendimento», e a
    trava do selo pago nem pediu o selo. A 83 ainda foi impressa duas vezes,
    sem selo.

    Agora: a certidão fica de pé e SEM poder ser impressa, e o «Selar» da
    ficha pede o selo depois, com as mesmas referências da emissão."""
    f = _compra_e_venda(casa)
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.24.4", 1), ("16.24.4.1", 9)])
    c = casa["balcao"]
    html = _clicar(c, "/selo/cobertura", "/selo/cobertura/atender", encerrar="1")
    assert "Atendimento encerrado" in html, html[:400]

    m = f["matricula"]
    ficha = f"/registro-imoveis/{m['id']}"
    token = _token(c.get(ficha).get_data(as_text=True))
    r = c.post(f"{ficha}/certidao", data={
        "csrf_token": token, "tipo": "INTEIRO_TEOR", "fonte_corpo": "TEXTO",
        "folhas": "", "requerente": COMPRADORA["nome"],
        "requerente_documento": COMPRADORA["cpf_fmt"],
        "finalidade": "Para fins de financiamento", "emolumentos": "",
        "protocolo": cx["numero"]})
    assert r.status_code == 302 and ".odt" not in r.headers["Location"], (
        _destino_em_texto(c, r))
    linha = _um(casa, "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1")
    assert not linha["cancelada"], linha["motivo_cancelamento"]
    assert not linha["selo_texto"]
    assert _um(casa, "SELECT 1 AS um FROM cx_selo_aguardando WHERE "
                     "tabela='ri_certidoes' AND ato_id=%s", (linha["id"],))

    # Sem selo, o papel não sai — nem pelo número na ficha.
    papel = c.get(f"/registro-imoveis/certidoes/{linha['id']}.odt?formato=odt")
    assert papel.status_code == 302 and papel.data[:2] != b"PK"
    tela = c.get(ficha).get_data(as_text=True)
    assert f"/registro-imoveis/certidoes/{linha['id']}/selar" in tela
    assert "aguardando pagamento" in tela

    # A ficha oferece o protocolo pago para escolher (escrevente confirma).
    assert f'name="protocolo_selo" value="{cx["id"]}"' in tela

    # O balcão marca o protocolo pago no «Selar» e pede o selo de novo.
    r = _clicar_sem_seguir(c, ficha,
                           f"/registro-imoveis/certidoes/{linha['id']}/selar",
                           protocolo_selo=str(cx["id"]))
    assert r.status_code == 302 and r.headers["Location"].endswith(
        f"/registro-imoveis/certidoes/{linha['id']}.odt"), _destino_em_texto(c, r)
    depois = _um(casa, "SELECT * FROM ri_certidoes WHERE id=%s", (linha["id"],))
    assert depois["selo_texto"] and not depois["cancelada"]
    assert not _um(casa, "SELECT 1 AS um FROM cx_selo_aguardando WHERE "
                         "tabela='ri_certidoes' AND ato_id=%s", (linha["id"],))
    assert depois["selo_texto"] in _papel(
        c, f"/registro-imoveis/certidoes/{linha['id']}.odt")

    # Pedir de novo não vende outro selo: a certidão já está selada.
    _clicar(c, ficha, f"/registro-imoveis/certidoes/{linha['id']}/selar")
    selos = _ler(casa, "SELECT numero FROM sd_selos WHERE tabela='ri_certidoes' "
                       "AND ato_id=%s", (linha["id"],))
    assert len({s["numero"] for s in selos}) == len(selos)


def test_sem_atendimento_a_prenotacao_e_a_abertura_selam_pelo_protocolo_escolhido(casa):
    """22/10/2026: a trava do selo pago só acha o pagamento no protocolo «em
    atendimento», e esse passo morava escondido em «Selo e caixa». A
    prenotação usa o protocolo geral escolhido no próprio formulário; a
    abertura e o «selar depois» da prenotação usam o protocolo marcado na tela
    (`protocolo_selo`) — a escrevente confirma, o sistema não escolhe."""
    c = casa["balcao"]
    cx = _protocolo_geral(casa, interessado=COMPRADORA,
                          itens=[("16.1", 1), ("16.2", 1)])
    _clicar(c, "/selo/cobertura", "/selo/cobertura/atender", encerrar="1")
    p = _prenotar(casa, cx, apresentante=COMPRADORA, natureza="Compra e venda",
                  objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    assert p["selo_prenotacao"], f"a prenotação saiu sem selo: {p['recado'][:600]}"

    _clicar(c, "/selo/cobertura", "/selo/cobertura/atender", encerrar="1")
    campos = dict(IMOVEL, data_abertura=date.today().isoformat(),
                  proprietario_nome=VENDEDOR["nome"],
                  proprietario_documento=VENDEDOR["cpf_fmt"],
                  proprietario_qualificacao=VENDEDOR["qualificacao"],
                  confrontacoes=CONFRONTACOES)
    _clicar(c, "/registro-imoveis/nova", "/registro-imoveis/nova", **campos)
    m = _um(casa, "SELECT * FROM ri_matriculas WHERE numero=%s",
            (str(PRIMEIRA_MATRICULA),))
    ficha = f"/registro-imoveis/{m['id']}"
    tela = c.get(ficha).get_data(as_text=True)
    assert f'name="protocolo_selo" value="{cx["id"]}"' in tela
    html = _clicar(c, ficha, f"{ficha}/selar-abertura", codigo_tj="16.2",
                   prenotacao=str(p["numero"]), protocolo_selo=str(cx["id"]))
    assert "selada" in html, f"a abertura não selou: {html[:900]}"

    # A prenotação de um protocolo AINDA NÃO PAGO fica sem selo; paga depois,
    # o «Selar» dela usa o protocolo marcado.
    cx2 = _protocolo_geral(casa, interessado=VENDEDOR, itens=[("16.1", 1)],
                           pagar=False)
    p2 = _prenotar(casa, cx2, apresentante=VENDEDOR, natureza="Hipoteca",
                   objeto="Imóvel urbano na Rua Exemplo, 30, Cidade Exemplo")
    assert not p2["selo_prenotacao"]
    ficha_cx = f"/caixa/protocolos/{cx2['id']}"
    _clicar(c, ficha_cx, f"{ficha_cx}/itens", acao="quitar_todos",
            forma_pagamento="DINHEIRO")
    _clicar(c, "/selo/cobertura", "/selo/cobertura/atender", encerrar="1")
    ver = f"/registro-imoveis/protocolo/{p2['id']}"
    assert f'name="protocolo_selo" value="{cx2["id"]}"' in c.get(ver).get_data(as_text=True)
    _clicar(c, ver, f"{ver}/selar", natureza_titulo="Hipoteca", codigo_tj="16.1",
            protocolo_selo=str(cx2["id"]))
    depois = _um(casa, "SELECT selo_prenotacao FROM ri_protocolos WHERE id=%s",
                 (p2["id"],))
    assert depois["selo_prenotacao"], "a prenotação paga depois não selou"
