"""Do protocolo à certidão, no Tabelionato de Protesto — PELAS TELAS (LT04).

O oficial, 20/10/2026: «quero que seja possível do protocolo à certidão. Minha
maior preocupação é que TODOS os atos precisam ter uma certidão adequada» — e
depois: «TERMO E CERTIDÃO». Cada ato tem de sair com o que se lavrou (o termo,
a linha do livro) e com o papel que o certifica (a certidão, o instrumento, o
edital), e os dois têm de BATER.

COMO O BALCÃO FAZ, E É O QUE ESTES TESTES FAZEM
    1. abre o caixa e o protocolo geral, acrescenta os itens da tabela e quita
       (o cliente pagou) — `/caixa`, `/caixa/protocolos`;
    2. marca o protocolo que está atendendo (`/selo/cobertura/atender`): é lá
       que o selo pago procura o item;
    3. cadastra o título pelo balcão (`/protesto/novo`) e lança cada ato pela
       ficha (`/protesto/<id>/lancar`), com o item do protocolo marcado;
    4. o selo sai do selador de mentira (`selador_de_bancada`), que é um
       servidor de verdade numa porta local, e não um `mock`;
    5. confere livro, folha e número; o TERMO; e emite a CERTIDÃO (ou o
       instrumento, ou o edital), lida no `.odt` que o cliente leva.

O QUE QUEBRA AQUI E AINDA NÃO SE CONSERTOU fica `xfail(strict=True)`, com o
artigo e o defeito no motivo — a asserção NÃO foi afrouxada para passar. A
lista inteira está em `docs/COBERTURA_FLUXOS.md`, seção do Protesto.

BASE NORMATIVA (os textos estão em `referencia/normas/` e no Código de Normas
do MA, Prov. COGEX 28/2026): Lei 9.492/1997; Código Nacional de Normas (Prov.
CNJ 149/2023), arts. 129, 130, 259 e 263-K; CN-MA arts. 881 a 952 e 130 a 132.

DADOS FICTÍCIOS (LGPD): as pessoas e os documentos são os da casa
(`docs/AGENTES.md`, `tests/fixtures/anti_vazamento/documentos_ficticios.txt`).
"""
from __future__ import annotations

import html as _html
import io
import json
import re
import sys
import zipfile
from datetime import date, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

from bd_nativo import banco as nativo            # noqa: E402
from navegador_de_teste import postar_e_seguir   # noqa: E402
from prova_de_intimacao import juntar_prova      # noqa: E402

# A SERVENTIA DE TESTE. O horário entra porque o aviso RECUSA sem ele (CN-MA
# art. 920 manda o horário de funcionamento no papel).
SERVENTIA = {
    "unit_name": "TABELIONATO DE PROTESTO DE CIDADE EXEMPLO",
    "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
    "serventia_titulo": "Tabelião de Protesto",
    "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
    "serventia_endereco": "Rua Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "serventia_telefone": "(98) 3000-0000",
    "serventia_horario": "de segunda a sexta, das 8h às 17h",
    "modulo_protesto_ligado": "1",
}

# A TABELA DE EMOLUMENTOS DE TESTE: os códigos do TJ que esta casa usa no
# protesto (`atribuicoes.ITENS_DE_CUSTA_POR_CAMINHO`), com preço inventado. A
# instalação nova não traz tabela nenhuma — ela vem da carga do E-Ofício.
ITENS = {   # código interno -> (código do TJ, descrição, preço)
    9701: ("17.1", "Item 17.1 da tabela de teste", "50,00"),
    9703: ("17.3", "Item 17.3 da tabela de teste", "40,00"),
    9704: ("17.4", "Item 17.4 da tabela de teste", "30,00"),
    9705: ("17.5.1", "Item 17.5.1 da tabela de teste", "20,00"),
    9709: ("17.9", "Item 17.9 da tabela de teste", "6,69"),
}
PROTESTO, CANCELAMENTO, RETIRADA, CERTIDAO, EDITAL = 9701, 9703, 9704, 9705, 9709

DEVEDOR = "PEDRO EXEMPLO DOS SANTOS"
CPF_DEVEDOR = "000.000.001-91"
CREDOR = "CARLA EXEMPLO"
CPF_CREDOR = "000.000.002-72"
INTERESSADO = "BEATRIZ EXEMPLO DE SOUZA"

TITULO = {
    "especie": "NP", "numero_titulo": "NP-0001",
    "data_emissao": "2025-01-10", "data_vencimento": "2025-02-10",
    "valor": "1.234,56", "saldo": "1.234,56",
    "praca_protesto": "CIDADE EXEMPLO", "tipo_protesto": "C",
    "motivo_protesto": "1", "tipo_moeda": "1", "aceite": "N",
    "cedente_nome": CREDOR, "cedente_documento": "00000000272",
    "cedente_endereco": "Rua das Flores, 10",
    "cedente_cidade": "Cidade Exemplo", "cedente_uf": "MA",
    "devedor_nome": DEVEDOR, "devedor_documento_tipo": "CPF",
    "devedor_documento": "00000000191",
    "devedor_endereco": "Rua Exemplo, 200", "devedor_bairro": "Centro",
    "devedor_cep": "65000000", "devedor_cidade": "Cidade Exemplo",
    "devedor_uf": "MA",
}

# O que nunca pode sobrar num papel assinado: o marcador do modelo, o «None»
# do Python e o claro de campo que não se preencheu.
SOBRAS = ("{", "}", "None", "%s", "()", " , ", " ;")

REMESSA_DA_CRA = (RAIZ / "tests" / "cra_remessa_exemplo.txt").read_bytes()

# O COMEÇO DE UM PDF, para o canhoto assinado e o comprovante do envio à
# CENPROT: desde 29/10/2026 a entrega e o protesto por edital só saem com o
# papel anexado, e o anexo confere os primeiros bytes.
PDF_DO_CANHOTO = b"%PDF-1.4\n%"


# ------------------------------------------------------------ a bancada


@pytest.fixture()
def s(cg_casa_logada, monkeypatch):
    """A casa logada como ADMIN, com a tabela de teste e o selador ligado.

    `protocolo_pago=False`: o protocolo pago É o que estes testes montam pela
    tela do caixa — a bancada não pode montar o dela por cima, ou o selo
    sairia pago pelo protocolo da bancada e não pelo do cliente.
    """
    from selador_de_bancada import ligar_o_selador
    cg_casa_logada["db"].set_settings(SERVENTIA)
    with cg_casa_logada["db"].transaction() as con:
        bd = nativo(con)
        bd.escrever("""INSERT INTO cx_vigencias(codigo, descricao, vigente, inicio)
                       VALUES (9001, 'tabela de teste', 1, '2026-01-01')""")
        for codigo, (tj, descricao, preco) in ITENS.items():
            bd.escrever("""INSERT INTO cx_servicos(codigo, codigo_tj, descricao,
                               ativo, emolumento)
                           VALUES (%s,%s,%s,1,1)""", (codigo, tj, descricao))
            bd.escrever(
                """INSERT INTO cx_servico_valores(servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s,9001,%s,'0,00','0,00','0,00','0,00',%s)""",
                (codigo, preco, preco))
    # O TRÍDUO (tarefa 56, PR #9): a rota de lançar confere o termo inicial, e
    # este fluxo aponta, intima e protesta no mesmo dia. Aqui o relógio da
    # conferência anda até o termo inicial quando o protesto vem cedo — o resto
    # da conta (atraso, motivo, o que fica gravado no ato) é o de verdade. A
    # recusa antes do prazo é de `test_protesto_triduo`.
    import protesto_triduo as TRIDUO
    conferir = TRIDUO.conferir_lavratura

    def no_termo_inicial(con, titulo_id, *, hoje, **outros):
        inicio = TRIDUO.contar(con, titulo_id).get("termo_inicial")
        if inicio and str(hoje or "")[:10] < inicio:
            hoje = inicio
        return conferir(con, titulo_id, hoje=hoje, **outros)

    monkeypatch.setattr(TRIDUO, "conferir_lavratura", no_termo_inicial)
    with ligar_o_selador(cg_casa_logada, protocolo_pago=False) as aparelho:
        cg_casa_logada["aparelho"] = aparelho
        yield cg_casa_logada


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _post(s, rota: str, origem: str, **campos):
    """O formulário mandado como o navegador manda: token da tela de origem."""
    token = _token(s["c"].get(origem).get_data(as_text=True))
    return postar_e_seguir(s["c"], rota, {"csrf_token": token, **campos})


def _avisos(resposta) -> list[str]:
    """Os recados (flash) que a tela mostrou, em texto."""
    return [_html.unescape(m).strip() for m in re.findall(
        r'<div class="flash \w+" data-aviso>([^<]*)',
        resposta.get_data(as_text=True))]


def _lancado(resposta, ato: str = "") -> bool:
    """O recado de que o ato entrou — e não o «Ato NÃO lançado» do selo que
    falhou, que também diz «lançado»."""
    return any("lançado" in a and not a.startswith("Ato NÃO")
               and a.startswith(ato) for a in _avisos(resposta))


def _ler(s, sql: str, args=()) -> list[dict]:
    with s["db"].connect() as con:
        return nativo(con).ler(sql, args)


def _um(s, sql: str, args=()) -> dict | None:
    linhas = _ler(s, sql, args)
    return linhas[0] if linhas else None


def _hoje(s) -> str:
    return s["db"].now()[:10]


def _br(iso: str) -> str:
    return f"{iso[8:10]}/{iso[5:7]}/{iso[:4]}"


def _extenso(iso: str) -> str:
    from ri_web import data_por_extenso
    return data_por_extenso(date.fromisoformat(iso[:10]))


def _papel(s, rota: str) -> dict:
    """O `.odt` que a tela entrega, aberto: o texto do corpo, o do cabeçalho
    e os nomes do pacote (as imagens dos QR moram em `Pictures/`)."""
    junta = "&" if "?" in rota else "?"
    r = s["c"].get(f"{rota}{junta}formato=odt")
    assert r.status_code == 200, (rota, r.status_code)
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        nomes = z.namelist()
        conteudo = z.read("content.xml").decode("utf-8")
        estilos = z.read("styles.xml").decode("utf-8") if "styles.xml" in nomes else ""

    def _texto(xml: str) -> str:
        xml = re.sub(r"</text:p>|<text:line-break/>", "\n", xml)
        return _html.unescape(re.sub(r"<[^>]+>", "", xml))

    return {"texto": _texto(conteudo), "cabecalho": _texto(estilos),
            "nomes": nomes}


# AS COLUNAS DO LIVRO DE PROTOCOLO PELA POSIÇÃO (LD11): as oito de antes do
# LD04 no mesmo lugar — quem lê o livro por posição não quebra — e o CPF/CNPJ
# do devedor, que o LD04 acrescentou, no fim.
OCORRENCIAS, DOCUMENTO = 7, 8


def _linhas_do_livro(s, qual: str) -> list[list[str]]:
    """As linhas do livro na tela, célula a célula (sem o cabeçalho)."""
    html = s["c"].get(f"/protesto/livros/{qual}?de=2000-01-01").get_data(
        as_text=True)
    corpo = html.split("<tbody>", 1)[1].split("</tbody>", 1)[0] if "<tbody>" in html else ""
    return [[_html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
             for c in re.findall(r"<td>(.*?)</td>", tr, re.S)]
            for tr in re.findall(r"<tr>(.*?)</tr>", corpo, re.S)]


def _pedidos_de_selo(s) -> list[dict]:
    """O que chegou ao selador: o caminho e o envelope."""
    return [{"caminho": p["caminho"], "envelope": json.loads(p["corpo"])}
            for p in s["aparelho"].pedidos if p["caminho"].startswith("/selo/")]


def _sem_sobra(texto: str) -> None:
    for sobra in SOBRAS:
        assert sobra not in texto, f"sobrou {sobra!r} no papel: {texto!r}"
    frases = [f.strip() for f in re.split(r"(?<=\.)\s", texto) if len(f.strip()) > 30]
    repetidas = {f for f in frases if frases.count(f) > 1}
    assert not repetidas, f"frase repetida no papel: {repetidas}"


def _confere_o_selo_no_papel(papel: dict, numero: str) -> None:
    """CN-MA art. 131: o selo consta do corpo do papel; art. 132: a consulta
    se faz pelo código ou pelo QR."""
    assert numero in papel["texto"]
    assert f"https://selo.tjma.jus.br/#/resumo/{numero}" in papel["texto"]
    assert any(n.startswith("Pictures/qr-selo") for n in papel["nomes"]), \
        "o papel saiu sem o QR do selo"


def _confere_a_serventia_no_papel(papel: dict) -> None:
    """O papel identifica a serventia e quem o assina."""
    assert SERVENTIA["unit_name"] in papel["cabecalho"] + papel["texto"]
    assert SERVENTIA["serventia_titular"] in papel["texto"]
    assert SERVENTIA["serventia_titulo"] in papel["texto"]


def _selo_de(s, tabela: str, ato_id: int) -> str:
    return _um(s, "SELECT numero FROM sd_selos WHERE tabela=%s AND ato_id=%s "
                  "ORDER BY id DESC LIMIT 1", (tabela, ato_id))["numero"]


# ------------------------------------------------------------ o balcão


def _protocolo(s, *servicos: int, quitar: bool = True) -> dict:
    """Abre o protocolo, acrescenta os itens, quita e passa a atendê-lo."""
    if not _um(s, "SELECT id FROM cx_caixas WHERE situacao='ABERTO' ORDER BY id"):
        _post(s, "/caixa", "/caixa", acao="abrir", saldo_inicial="0")
    r = _post(s, "/caixa/protocolos", "/caixa/protocolos", acao="novo",
              interessado=INTERESSADO, telefone="(98) 99999-0000",
              atribuicao="PROTESTO")
    assert any("aberto" in a for a in _avisos(r)), _avisos(r)
    p = _um(s, "SELECT * FROM cx_protocolos ORDER BY id DESC LIMIT 1")
    ficha = f"/caixa/protocolos/{p['id']}"
    for servico in servicos:
        _post(s, f"{ficha}/itens", ficha, acao="acrescentar", servico=str(servico))
    if quitar:
        r = _post(s, f"{ficha}/itens", ficha, acao="quitar_todos",
                  forma_pagamento="DINHEIRO")
        assert any("quitad" in a for a in _avisos(r)), _avisos(r)
        assert _um(s, "SELECT situacao FROM cx_protocolos WHERE id=%s",
                   (p["id"],))["situacao"] == "PAGO"
    r = _post(s, "/selo/cobertura/atender", "/selo/cobertura",
              protocolo=p["numero"])
    assert any("atendendo" in a for a in _avisos(r)), _avisos(r)
    itens = [i["id"] for i in _ler(
        s, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
        (p["id"],))]
    return {"id": p["id"], "numero": p["numero"], "itens": itens}


def _titulo_pelo_balcao(s, **mudar) -> int:
    r = _post(s, "/protesto/novo", "/protesto/novo", **{**TITULO, **mudar})
    assert any("cadastrado" in a for a in _avisos(r)), _avisos(r)
    return _um(s, "SELECT id FROM pt_titulos ORDER BY id DESC LIMIT 1")["id"]


def _lancar(s, titulo_id: int, ato: str, protocolo: dict | None = None,
            item: int | None = None, **campos):
    """Lança o ato pela ficha, com o item do protocolo marcado para ele."""
    if protocolo is not None:
        campos["protocolo_id"] = str(protocolo["id"])
        if item is not None:
            campos["protocolo_item_id"] = str(item)
    return _post(s, f"/protesto/{titulo_id}/lancar", f"/protesto/{titulo_id}",
                 ato=ato, **campos)


def _ato(s, titulo_id: int, tipo: str) -> dict:
    """O ato válido (não anulado) mais recente daquele tipo, com o livro."""
    ato = _um(s, """SELECT a.*, v.serie AS livro_serie, v.numero AS livro_numero
                      FROM pt_atos a LEFT JOIN nu_livros v ON v.id = a.livro_id
                     WHERE a.titulo_id=%s AND a.tipo=%s AND a.cancelado=0
                     ORDER BY a.id DESC LIMIT 1""", (titulo_id, tipo))
    assert ato, f"não há {tipo} válido no título {titulo_id}"
    return ato


def _situacao(s, titulo_id: int) -> str:
    return _um(s, "SELECT situacao FROM pt_titulos WHERE id=%s",
               (titulo_id,))["situacao"]


def _apontado(s, protocolo: dict, item: int, **mudar) -> int:
    tid = _titulo_pelo_balcao(s, **mudar)
    r = _lancar(s, tid, "APONTAMENTO", protocolo, item)
    assert _lancado(r, "Apontamento"), _avisos(r)
    return tid


def _aviso(s, titulo_id: int) -> dict:
    r = _post(s, f"/protesto/{titulo_id}/aviso", f"/protesto/{titulo_id}")
    assert any("emitido" in a for a in _avisos(r)), _avisos(r)
    return _um(s, "SELECT * FROM pt_avisos WHERE titulo_id=%s ORDER BY id DESC LIMIT 1",
               (titulo_id,))


def _canhoto(aviso: dict) -> tuple:
    """O canhoto assinado do aviso, como o balcão o anexa: desde 29/10/2026
    a entrega só se registra com ele e com quem recebeu, no mesmo ato. Um
    arquivo por aviso — o mesmo arquivo em dois avisos é suspeito."""
    conteudo = (PDF_DO_CANHOTO + b" canhoto do aviso "
                + str(aviso["id"]).encode())
    return (io.BytesIO(conteudo), f"canhoto-aviso-{aviso['id']}.pdf")


def _intimado_em_maos(s, titulo_id: int) -> dict:
    aviso = _aviso(s, titulo_id)
    r = _post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos",
              entregue="1", recebido_por=DEVEDOR, quando=_hoje(s),
              comprovante=_canhoto(aviso))
    assert any("intimação pessoal foi lavrada" in a for a in _avisos(r)), _avisos(r)
    return aviso


def _protestado(s, protocolo: dict, item_apontamento: int,
                item_protesto: int, **mudar) -> int:
    tid = _apontado(s, protocolo, item_apontamento, **mudar)
    _intimado_em_maos(s, tid)
    r = _lancar(s, tid, "PROTESTO", protocolo, item_protesto)
    assert _lancado(r, "Protesto"), _avisos(r)
    return tid


def _certidao(s, protocolo: dict, item: int, **campos) -> dict:
    """Emite a certidão pela tela e devolve a linha gravada."""
    antes = _um(s, "SELECT max(id) AS m FROM pt_certidoes")["m"] or 0
    r = _post(s, "/protesto/certidoes/emitir", "/protesto/certidoes",
              nome=DEVEDOR, documento=CPF_DEVEDOR, anos="5",
              protocolo_id=str(protocolo["id"]), protocolo_item_id=str(item),
              **campos)
    assert any("emitida" in a for a in _avisos(r)), _avisos(r)
    certidao = _um(s, "SELECT * FROM pt_certidoes WHERE id > %s ORDER BY id",
                   (antes,))
    assert certidao and not certidao["cancelada"], certidao
    return certidao


def _prazo_limite(s, titulo: dict) -> str:
    from protesto_aviso import prazo_limite
    with s["db"].connect() as con:
        return _br(prazo_limite(con, titulo))


def _prazo_do_edital(s, titulo: dict) -> str:
    """O prazo-limite do EDITAL é o MAIOR entre os três dias úteis da
    protocolização e o primeiro dia útil depois da publicação (CN-MA art.
    922, §§ 1º e 3º; art. 925, § 4º) — ordem do oficial em 27/10/2026."""
    from protesto_aviso import prazo_de_pagamento
    with s["db"].connect() as con:
        return _br(prazo_de_pagamento(con, titulo, _hoje(s)))


# ===================================================== o apontamento


def test_o_apontamento_ocupa_o_livro_de_apontamento_e_nao_pede_selo(s):
    """Lei 9.492, arts. 5º e 32; CN-MA arts. 907 e 908 — e a certidão a
    terceiro, de título só apontado, é NEGATIVA (Lei 9.492, art. 27: a
    certidão é de PROTESTO, e apontamento não é protesto).

    CONTRATO MUDADO POR ORDEM DO OFICIAL, 21/10/2026 (P-B, lote LH06): até
    aqui este teste se chamava `..._sela_com_o_item_pago_...` e cobrava o selo
    do apontamento pelo item quitado (LT04). O apontamento NÃO pede selo:
    dos 1.409 apontamentos do E-Ofício, 1.161 não têm selo, e os 248 que têm
    trazem o do ato POSTERIOR. Pedir selo fazia o ato sair cancelado."""
    p = _protocolo(s, PROTESTO, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    titulo = _um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    ato = _ato(s, tid, "APONTAMENTO")

    # O LUGAR NO LIVRO — série própria, folha, número de ordem.
    assert ato["livro_serie"] == "PT_APONTAMENTO"
    assert (ato["livro_numero"], ato["folha"], ato["numero_ordem"]) == ("1", 1, 1)
    assert titulo["situacao"] == "APONTADO"
    assert re.fullmatch(r"\d{10}", titulo["protocolo"])

    # SEM SELO, E DE PÉ: nenhum pedido ao selador, nenhum selo gravado, e o
    # ato não se anula por isso (era o 900001/1: lavrado e cancelado).
    assert ato["selo"] is None and not ato["cancelado"]
    assert _um(s, "SELECT COUNT(*) AS n FROM sd_selos "
                  "WHERE tabela='pt_atos' AND ato_id=%s", (ato["id"],))["n"] == 0
    assert _pedidos_de_selo(s) == []

    # O TERMO É A LINHA DO LIVRO DE PROTOCOLO (CN-MA art. 908, Lei 9.492 art.
    # 32): ordem, natureza, valor, apresentante, devedor, ocorrências — e,
    # desde o LD04, o CPF/CNPJ do devedor (CN-MA art. 906), na última coluna
    # desde o LD11.
    [linha] = _linhas_do_livro(s, "protocolo")
    assert linha[:5] == ["1", titulo["protocolo"], _br(_hoje(s)),
                         "Nota Promissória", "1.234,56"]
    assert linha[6] == DEVEDOR and linha[OCORRENCIAS] == "sem ocorrência"
    assert linha[DOCUMENTO] == linha[-1] == CPF_DEVEDOR

    # A CERTIDÃO A TERCEIRO: negativa, com o nome, o CPF e o período.
    cert = _certidao(s, p, p["itens"][1])
    assert cert["tipo"] == "NEGATIVA"
    assert f"NÃO ENCONTREI protesto contra {DEVEDOR} CPF: {CPF_DEVEDOR}" in cert["teor"]
    assert "Período de Busca: 5 Anos" in cert["teor"]
    _sem_sobra(cert["teor"])
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert "CERTIDÃO NEGATIVA DE PROTESTO" in papel["texto"]
    assert f"n. {cert['numero']}/{cert['ano']}" in papel["texto"]
    assert cert["teor"] in papel["texto"]
    _confere_a_serventia_no_papel(papel)
    _confere_o_selo_no_papel(papel, _selo_de(s, "pt_certidoes", cert["id"]))


def test_o_livro_de_protocolo_traz_o_cpf_do_devedor(s):
    """CN-MA art. 906: o CPF/CNPJ do devedor consta «no Livro de Protocolo e
    em todos os registros e certidões». Até o LD04 a coluna «Devedor» era só o
    nome; o documento é coluna própria — a última, desde o LD11, para quem lê
    o livro por posição achar as ocorrências onde sempre estiveram."""
    p = _protocolo(s, PROTESTO)
    _apontado(s, p, p["itens"][0])
    [linha] = _linhas_do_livro(s, "protocolo")
    assert any(CPF_DEVEDOR in c or "00000000191" in c for c in linha), linha
    html = s["c"].get("/protesto/livros/protocolo?de=2000-01-01").get_data(
        as_text=True)
    cabeca = [_html.unescape(c) for c in re.findall(r"<th>(.*?)</th>", html)]
    assert cabeca[OCORRENCIAS] == "Ocorrências", cabeca
    assert cabeca[DOCUMENTO] == cabeca[-1] == "CPF/CNPJ do devedor", cabeca


def test_o_devedor_tira_certidao_do_apontamento_a_pedido_escrito(s):
    """CN-MA art. 906, § 2º, e art. 905, parágrafo único: informações e
    certidões do Livro de Protocolo saem a requerimento escrito do próprio
    devedor ou por ordem judicial. Até o LD04 o título só apontado saía
    NEGATIVA mesmo a pedido dele; agora a negativa (protesto não há) traz o
    que consta do Livro de Protocolo. E o outro lado da regra: SEM o pedido
    escrito o apontamento não aparece — as anotações do livro são sigilosas
    (CN-MA art. 908, § 4º)."""
    p = _protocolo(s, PROTESTO, CERTIDAO, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    titulo = _um(s, "SELECT protocolo FROM pt_titulos WHERE id=%s", (tid,))
    a_terceiro = _certidao(s, p, p["itens"][1], requerente=INTERESSADO)
    assert a_terceiro["tipo"] == "NEGATIVA"
    assert titulo["protocolo"] not in a_terceiro["teor"], a_terceiro["teor"]
    assert "Livro de Protocolo" not in a_terceiro["teor"]
    cert = _certidao(s, p, p["itens"][2], autorizacao="DEVEDOR_ESCRITO",
                     requerente=DEVEDOR)
    assert cert["tipo"] == "NEGATIVA"          # protesto não há
    for esperado in (
            "a requerimento escrito do próprio devedor",
            "consta do Livro de Protocolo desta serventia",
            f"1) Protocolo n. {titulo['protocolo']}, de {_br(_hoje(s))}",
            "título n. NP-0001", "valor R$ 1.234,56",
            "ocorrências no Livro de Protocolo: sem ocorrência."):
        assert esperado in cert["teor"], (esperado, cert["teor"])
    _sem_sobra(cert["teor"])
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert cert["teor"] in papel["texto"]


def test_a_certidao_pedida_com_o_cpf_nao_traz_o_homonimo(s):
    """CN-MA art. 906, § 2º: o Livro de Protocolo só se certifica ao PRÓPRIO
    devedor, ou por ordem judicial. Até o LD11 a busca casava o documento OU
    o nome: quem pedia com o CPF dele e o nome como está no título levava, a
    terceiro, a POSITIVA com o protesto do homônimo de outro CPF — a certidão
    que mente contra a pessoa — e, a pedido escrito, o protocolo do homônimo.
    Com o CPF, a busca é por ele, e o nome não amplia."""
    p = _protocolo(s, PROTESTO, PROTESTO, PROTESTO, CERTIDAO, CERTIDAO)
    dele = _apontado(s, p, p["itens"][0])
    homonimo = _protestado(s, p, p["itens"][1], p["itens"][2],
                           numero_titulo="NP-0002",
                           devedor_documento="00000000353")
    protocolo = {tid: _um(s, "SELECT protocolo FROM pt_titulos WHERE id=%s",
                          (tid,))["protocolo"] for tid in (dele, homonimo)}
    a_terceiro = _certidao(s, p, p["itens"][3])
    assert a_terceiro["tipo"] == "NEGATIVA", a_terceiro["teor"]
    cert = _certidao(s, p, p["itens"][4], autorizacao="DEVEDOR_ESCRITO",
                     requerente=DEVEDOR)
    assert cert["tipo"] == "NEGATIVA", cert["teor"]
    assert f"Protocolo n. {protocolo[dele]}" in cert["teor"], cert["teor"]
    assert protocolo[homonimo] not in cert["teor"], cert["teor"]
    assert "NP-0002" not in cert["teor"]


def test_a_certidao_pedida_com_o_cpf_acha_o_protesto_do_devedor_gravado_sem_documento(s):
    """A ressalva da revisão do LD11 (LD12). Só pelo documento, o protesto do
    devedor gravado SEM CPF/CNPJ sumia da certidão pedida com o CPF dele, e
    ela saía NEGATIVA para quem tem protesto. Com o mesmo nome, ele entra — e
    a tela de busca (com o apontamento que o pedido escrito traz do Livro de
    Protocolo), o recado da emissão, a página da certidão e a auditoria
    avisam que ali só o nome liga a pessoa, para o escrevente conferir a
    identidade. O teor é o de sempre."""
    p = _protocolo(s, PROTESTO, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    apontado = _apontado(s, p, p["itens"][2], numero_titulo="NP-0002")
    # O DEVEDOR GRAVADO SEM DOCUMENTO, como o do acervo: o balcão de hoje não
    # cadastra assim (a conferência da CRA exige o CPF/CNPJ), e por isso o
    # documento sai depois dos atos lavrados.
    with s["db"].transaction() as con:
        nativo(con).escrever(
            "UPDATE pt_devedores SET documento_tipo=NULL, documento_numero=NULL "
            "WHERE titulo_id IN (%s, %s)", (tid, apontado))

    def _tela(**pedido) -> str:
        return _html.unescape(s["c"].get(
            "/protesto/certidoes", query_string={
                "nome": DEVEDOR, "documento": CPF_DEVEDOR, **pedido}).get_data(
            as_text=True))

    tela = _tela()
    assert "<strong>POSITIVA</strong>" in tela, tela
    assert "data-so-pelo-nome" in tela
    assert "1 título entrou só pelo NOME" in tela
    assert "sem CPF/CNPJ no título" in tela
    # A PEDIDO ESCRITO, O APONTAMENTO DO LIVRO DE PROTOCOLO TAMBÉM ENTRA — e a
    # tela, que não o lista, diz qual é antes de emitir.
    protocolo = _um(s, "SELECT protocolo FROM pt_titulos WHERE id=%s",
                    (apontado,))["protocolo"]
    escrito = _tela(autorizacao="DEVEDOR_ESCRITO")
    assert "2 títulos entraram só pelo NOME" in escrito
    no_aviso = rf"protocolo\s+{protocolo}, de {re.escape(_br(_hoje(s)))}"
    assert re.search(no_aviso, escrito), escrito
    assert not re.search(no_aviso, tela)

    r = _post(s, "/protesto/certidoes/emitir", "/protesto/certidoes",
              nome=DEVEDOR, documento=CPF_DEVEDOR, anos="5",
              protocolo_id=str(p["id"]), protocolo_item_id=str(p["itens"][3]))
    avisos = _avisos(r)
    assert any("emitida" in a for a in avisos), avisos
    assert any(a.startswith("Confira a identidade: 1 título entrou") for a in avisos), avisos
    cert = _um(s, "SELECT * FROM pt_certidoes ORDER BY id DESC LIMIT 1")
    assert cert["tipo"] == "POSITIVA" and not cert["cancelada"], cert["teor"]
    assert f"protesto contra {DEVEDOR}" in cert["teor"], cert["teor"]
    assert "NP-0001" in cert["teor"]
    # O AVISO É AO ESCREVENTE, E NÃO AO PAPEL.
    assert "só pelo" not in cert["teor"] and "identidade" not in cert["teor"]
    _sem_sobra(cert["teor"])
    pagina = _html.unescape(s["c"].get(
        f"/protesto/certidoes/{cert['id']}").get_data(as_text=True))
    assert "entrou só pelo nome" in pagina
    trilha = _um(s, """SELECT details FROM audit_logs
                        WHERE action = 'PROTESTO_CERTIDAO' AND entity_id = %s
                        ORDER BY id DESC LIMIT 1""", (cert["id"],))
    assert json.loads(trilha["details"])["so_pelo_nome"] == 1


# ===================================================== a intimação


def _confere_o_aviso(s, aviso: dict, titulo: dict) -> None:
    """CN-MA arts. 920 e 923; Lei 9.492, art. 14, § 2º — salvo o apresentante,
    que o título do balcão só tem quando o balcão o informa (ver o teste
    próprio, `test_o_titulo_do_balcao_leva_o_apresentante_ao_aviso_e_ao_instrumento`)."""
    papel = _papel(s, f"/protesto/avisos/{aviso['id']}.odt")
    texto = papel["texto"]
    limite = _prazo_limite(s, titulo)
    for esperado in (
            f"Aviso n. {aviso['numero']}/{aviso['ano']} — Protocolo n. {titulo['protocolo']}",
            f"Devedor: {DEVEDOR}, CPF/CNPJ {CPF_DEVEDOR}",
            "Endereço: Rua Exemplo, 200, Centro, Cidade Exemplo/MA",
            "Título: Nota Promissória, n. NP-0001",            # por extenso
            "Valor: R$ 1.234,56 — vencimento em 10/02/2025",
            "Aceite: sem aceite",
            f"Credor (sacador/favorecido): {CREDOR}, CPF/CNPJ {CPF_CREDOR}",
            f"Prazo-limite para pagamento: {limite}",
            "Rua Exemplo, 100, Centro", "Telefone (98) 3000-0000",
            "Horário de funcionamento: de segunda a sexta, das 8h às 17h"):
        assert esperado in texto, (esperado, texto)
    _confere_a_serventia_no_papel(papel)


@pytest.mark.parametrize("modo", ["PESSOAL", "EDITAL"])
def test_a_intimacao_chega_igual_ao_livro_ao_termo_e_ao_instrumento(s, modo):
    """A intimação não ocupa livro próprio: ela se averba no Livro de
    Protocolo (CN-MA art. 908, § 5º), vai ao termo do protesto como a
    certidão da intimação (Lei 9.492, art. 22, IV; CN-MA art. 914) e ao
    instrumento — e a DATA tem de ser a mesma nos três. O edital é o papel da
    intimação que não se fez em mãos (Lei 9.492, art. 15; CN-MA art. 922)."""
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _apontado(s, p, p["itens"][0])
    titulo = _um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    aviso = _aviso(s, tid)
    _confere_o_aviso(s, aviso, titulo)
    hoje = _br(_hoje(s))

    if modo == "PESSOAL":
        r = _post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos",
                  entregue="1", recebido_por=DEVEDOR, quando=_hoje(s),
                  comprovante=_canhoto(aviso))
        assert any("intimação pessoal foi lavrada" in a for a in _avisos(r))
        no_livro = f"intimado pessoalmente em {hoje}"
        no_termo = f"O devedor foi intimado pessoalmente em {hoje}."
        no_instrumento = ("CERTIFICO que a intimação foi entregue no endereço "
                          f"do devedor em {hoje}.")
    else:
        r = _post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos",
                  entregue="0", motivo="1", quando=_hoje(s))
        assert any("Não-entrega registrada" in a for a in _avisos(r))
        r = _post(s, f"/protesto/avisos/{aviso['id']}/edital", "/protesto/avisos",
                  justificativa="Devedor mudou-se e não há outro endereço conhecido.")
        assert any("intimação por edital foi lavrada" in a for a in _avisos(r)), _avisos(r)
        edital = _um(s, "SELECT * FROM pt_editais WHERE titulo_id=%s", (tid,))
        papel = _papel(s, f"/protesto/editais/{edital['id']}.odt")
        # CN-MA art. 922, § 3º: devedor e identificação, título, valor,
        # prazo-limite e o tabelionato com endereço e telefone.
        for esperado in (f"{DEVEDOR}, inscrito(a) no CPF/CNPJ sob o nº {CPF_DEVEDOR}",
                         f"Protocolo: {titulo['protocolo']}", "Título: NP-0001",
                         "Valor: R$ 1.234,56",
                         f"Prazo-limite para pagamento: {_prazo_do_edital(s, titulo)}",
                         "Rua Exemplo, 100, Centro", "Telefone (98) 3000-0000",
                         f"Cidade Exemplo/MA, {_extenso(_hoje(s))}"):
            assert esperado in papel["texto"], (esperado, papel["texto"])
        _confere_a_serventia_no_papel(papel)
        _sem_sobra(edital["teor"])
        # A PROVA DO EDITAL (29/10/2026): o comprovante do envio do arquivo
        # dos editais do dia à CENPROT (CN-MA art. 922, § 1º). Sem ele o
        # protesto por edital não se lavra.
        r = _post(s, "/protesto/editais/comprovante-cenprot", "/protesto/avisos",
                  dia=_hoje(s),
                  comprovante=(io.BytesIO(PDF_DO_CANHOTO + b" envio a CENPROT"),
                               "envio-cenprot.pdf"))
        assert any("Comprovante do envio à CENPROT anexado" in a
                   for a in _avisos(r)), _avisos(r)
        no_livro = f"intimado por edital em {hoje}"
        no_termo = f"O devedor foi intimado por Edital em {hoje}."
        no_instrumento = ("CERTIFICO que a intimação foi feita por EDITAL, "
                          f"publicado em {hoje}")

    intimacao = _ato(s, tid, "INTIMACAO")
    assert json.loads(intimacao["detalhe_json"])["modo"] == modo
    assert _situacao(s, tid) == "INTIMADO"

    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert _lancado(r, "Protesto"), _avisos(r)
    assert no_termo in _ato(s, tid, "PROTESTO")["teor"]
    [linha] = _linhas_do_livro(s, "protocolo")
    assert no_livro in linha[OCORRENCIAS]
    assert f"protestado em {hoje}" in linha[OCORRENCIAS]

    _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    assert no_instrumento in instrumento["teor"]


def test_a_intimacao_por_edital_lancada_pela_ficha_sela_como_edital(s):
    """A intimação lançada pela ficha, com o código do edital, sela pelo modo
    em que aconteceu: por edital é a natureza 2 do contrato do selo, e não a 0
    da carta entregue em mãos (`ato_selado.NATUREZA_DA_INTIMACAO`). Até o LT04
    o modo não chegava ao envelope, e toda intimação selava como pessoal."""
    p = _protocolo(s, PROTESTO, EDITAL)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "INTIMACAO", p, p["itens"][1], modo="EDITAL",
                codigo_edital="ED-2026-0099")
    assert _lancado(r, "Intimacao"), _avisos(r)
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/atos-em-geral"
    assert pedido["envelope"]["natureza"]["tipo"] == 2
    assert pedido["envelope"]["ato"]["codigo"] == "17.9"
    assert _ato(s, tid, "INTIMACAO")["selo"]


def test_a_intimacao_eletronica_sai_igual_no_termo_e_no_instrumento(s):
    """CN-MA arts. 919, § 1º, e 921, § 6º, II; Lei 9.492, art. 22, IV: a
    intimação por meio eletrônico se certifica igual no termo e no
    instrumento. Até o LD04 o instrumento lia só o modo (PESSOAL) e
    certificava «entregue no endereço do devedor»."""
    p = _protocolo(s, PROTESTO, EDITAL, PROTESTO)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "INTIMACAO", p, p["itens"][1], modo="PESSOAL",
                digital="on")
    assert _lancado(r, "Intimacao"), _avisos(r)
    # A PROVA DA INTIMAÇÃO DIGITAL (29/10/2026): a confirmação da Resolve e o
    # histórico guardado — o que este teste confere é o texto do termo.
    with s["db"].transaction() as con:
        juntar_prova(con, tid)
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][2])
    assert _lancado(r, "Protesto"), _avisos(r)
    hoje = _br(_hoje(s))
    assert (f"O devedor foi intimado por meio eletrônico, com o recebimento "
            f"confirmado em {hoje}.") in _ato(s, tid, "PROTESTO")["teor"]
    _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    assert "meio eletrônico" in instrumento["teor"], instrumento["teor"]
    assert "entregue no endereço do devedor" not in instrumento["teor"]


# ===================================================== o protesto


def test_o_protesto_lavrado_e_o_instrumento_e_a_certidao_dizem_o_mesmo(s):
    """O registro (Lei 9.492, arts. 20 a 23; CN-MA arts. 914 e 915), o
    instrumento que vai ao apresentante (art. 20; CN-MA art. 914, «certidão do
    instrumento») e a certidão positiva (Lei 9.492, art. 27; CN-MA art. 906;
    CNN arts. 129 e 259, parágrafo único) — os três com o mesmo livro, folha,
    número, data, título, tipo e motivo. E cada papel com o seu selo (CN-MA
    arts. 130 a 132)."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    titulo = _um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    ato = _ato(s, tid, "PROTESTO")
    data_registro = _br(ato["data_ato"][:10])

    # O LIVRO DE REGISTRO DE PROTESTOS (CN-MA art. 915): série, folha, nº.
    assert ato["livro_serie"] == "PT_PROTESTO"
    assert (ato["livro_numero"], ato["folha"], ato["numero_ordem"]) == ("1", 1, 1)
    assert _situacao(s, tid) == "PROTESTADO"
    selo_do_ato = _selo_de(s, "pt_atos", ato["id"])
    assert ato["selo"] == selo_do_ato
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/titulo"
    assert pedido["envelope"]["natureza"]["tipo"] == 7          # PROTESTO
    # O LIVRO QUE O SELO DECLARA É O DO REGISTRO — o número, e não o id
    # interno da tabela de livros (que aqui é 2: o de apontamento é o 1).
    assert pedido["envelope"]["selo"]["livro"] == ato["livro_numero"] == "1"
    assert pedido["envelope"]["selo"]["folha"] == "1"
    assert pedido["envelope"]["partes"]["parteAto"] == [
        {"nome": DEVEDOR, "documento": "00000000191"}]

    # O TERMO: tipo e motivo do título, a certidão da intimação, sem claro.
    termo = ato["teor"]
    assert "PROTESTO COMUM LAVRADO POR FALTA DE PAGAMENTO." in termo
    assert f"O devedor foi intimado pessoalmente em {data_registro}." in termo
    _sem_sobra(termo)

    # O INSTRUMENTO (Lei 9.492, art. 22; CN-MA art. 914, I a X).
    r = _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    assert r.status_code == 200
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    papel = _papel(s, f"/protesto/instrumentos/{instrumento['id']}/odt")
    for esperado in (
            "INSTRUMENTO DE PROTESTO",
            f"n. {instrumento['numero']}/{instrumento['ano']}",
            "DECLARA PROTESTADO",
            # I — número de ordem e data do registro; data e nº do protocolo
            f"Registro do protesto: Livro 1, folha 1, sob o n.º 1, em {data_registro}.",
            f"Protocolo n.º {titulo['protocolo']}, de {data_registro}.",
            # III — as indicações do título
            "Título: Nota Promissória, n.º NP-0001, emitido em 10/01/2025, "
            "vencido em 10/02/2025, valor R$ 1.234,56.",
            f"Credor (sacador/favorecido): {CREDOR}",
            # VII — devedor, documento e endereço
            f"Devedor: {DEVEDOR}, CPF 00000000191, endereço Rua Exemplo, 200, "
            "Centro, Cidade Exemplo/MA.",
            # IX e X — tipo e motivo, os MESMOS do termo
            "Tipo: protesto comum. Motivo: falta de pagamento.",
            # IV — a certidão da intimação, com a data do termo
            "CERTIFICO que a intimação foi entregue no endereço do devedor em "
            f"{data_registro}.",
            # VIII — local e data, e quem assina
            f"Cidade Exemplo-MA, {_extenso(ato['data_ato'])}."):
        assert esperado in papel["texto"], (esperado, papel["texto"])
    _confere_a_serventia_no_papel(papel)
    _confere_o_selo_no_papel(papel, selo_do_ato)
    _sem_sobra(instrumento["teor"])

    # A CERTIDÃO POSITIVA — FIEL AO REGISTRO, item a item.
    cert = _certidao(s, p, p["itens"][2], requerente=INTERESSADO)
    assert cert["tipo"] == "POSITIVA"
    teor = cert["teor"]
    for esperado in (
            f"CERTIFICO a requerimento de {INTERESSADO}",
            f"encontrei protesto contra {DEVEDOR} e inscrito no CPF: {CPF_DEVEDOR}.",
            "1) Título n. NP-0001", "espécie NP",
            f"protocolo {titulo['protocolo']}", "valor R$ 1.234,56",
            "emitido em 10/01/2025", "vencido em 10/02/2025",
            f"credor {CREDOR} ({CPF_CREDOR})",
            "protesto comum por falta de pagamento",          # = termo
            f"protestado em {data_registro}",                  # = data do ato
            f"Livro {ato['livro_numero']}, fl. {ato['rotulo']}, n. {ato['numero_ordem']}."):
        assert esperado in teor, (esperado, teor)
    _sem_sobra(teor)
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert "CERTIDÃO POSITIVA DE PROTESTO" in papel["texto"]
    assert teor in papel["texto"]
    _confere_a_serventia_no_papel(papel)
    selo_da_certidao = _selo_de(s, "pt_certidoes", cert["id"])
    assert selo_da_certidao != selo_do_ato
    _confere_o_selo_no_papel(papel, selo_da_certidao)
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/certidao"
    assert pedido["envelope"]["partes"]["parteAto"] == [
        {"nome": DEVEDOR, "documento": "00000000191"}]


def test_os_emolumentos_que_o_selo_declara_saem_no_papel_da_certidao(s):
    """CN-MA art. 87, XVI, e art. 952: o valor dos emolumentos consta do
    próprio documento. QUEM ESCREVE O VALOR É O SELO (`selo_no_papel`): o
    aparelho do TJMA devolve o texto com o total e os fundos, e o papel o
    imprime. O selador de mentira devolve só o número — aqui o texto é o que
    o aparelho de verdade devolveria, gravado no razão do selo."""
    p = _protocolo(s, PROTESTO, CERTIDAO)
    _apontado(s, p, p["itens"][0])
    cert = _certidao(s, p, p["itens"][1])
    selo = _selo_de(s, "pt_certidoes", cert["id"])
    with s["db"].transaction() as con:
        nativo(con).escrever(
            "UPDATE sd_selos SET texto=%s WHERE numero=%s",
            (f"Poder Judiciário – TJMA. Selo: {selo}, {_br(_hoje(s))} 10:00:00, "
             f"Ato: 17.5.1, Parte(s): {DEVEDOR}, Total R$ 20,00 Emol R$ 18,00 "
             "FERC R$ 0,50 FADEP R$ 0,75 FEMP R$ 0,75 "
             "Consulte em https://selo.tjma.jus.br", selo))
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert "Total R$ 20,00" in papel["texto"], papel["texto"]
    assert "Emol R$ 18,00" in papel["texto"]


def test_o_registro_do_protesto_traz_os_elementos_do_art_22(s):
    """Lei 9.492, art. 22, I, II, III e VII, e art. 21, § 4º («os devedores
    não poderão deixar de figurar no termo»); CN-MA art. 914. O termo dizia
    «o responsável acima mencionado e qualificado» sem nada acima; desde o
    LD04 a qualificação vai no próprio registro, com a redação do instrumento."""
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    titulo = _um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    termo = _ato(s, tid, "PROTESTO")["teor"]
    for elemento in (titulo["protocolo"], "NP-0001", "1.234,56", DEVEDOR,
                     "00000000191", "Rua Exemplo, 200"):
        assert elemento in termo, (elemento, termo)


def test_o_titulo_do_balcao_leva_o_apresentante_ao_aviso_e_ao_instrumento(s):
    """Lei 9.492, art. 22, II; CN-MA arts. 884, I, 914, III, e 920: o
    cadastro pelo balcão pede o apresentante (LD04), e ele chega ao aviso, ao
    registro do protesto e ao instrumento. Sem o endereço, o pedaço fecha no
    nome; com ele, ver o teste seguinte (LD08)."""
    assert 'name="apresentante_nome"' in s["c"].get("/protesto/novo").get_data(
        as_text=True)
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _apontado(s, p, p["itens"][0], apresentante_nome=CREDOR)
    aviso = _aviso(s, tid)
    papel = _papel(s, f"/protesto/avisos/{aviso['id']}.odt")
    assert f"Apresentante: {CREDOR}" in papel["texto"], papel["texto"]
    r = _post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos",
              entregue="1", recebido_por=DEVEDOR, quando=_hoje(s),
              comprovante=_canhoto(aviso))
    assert any("intimação pessoal foi lavrada" in a for a in _avisos(r)), _avisos(r)
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert _lancado(r, "Protesto"), _avisos(r)
    assert f"Apresentante: {CREDOR}." in _ato(s, tid, "PROTESTO")["teor"]
    _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    assert f"Apresentante: {CREDOR}." in instrumento["teor"], instrumento["teor"]


def test_o_balcao_pede_o_documento_e_o_endereco_do_apresentante_e_eles_vao_aos_papeis(s):
    """CN-MA art. 884, I: quem apresenta informa o nome, o endereço completo
    e o CPF/CNPJ. O documento vai ao aviso (CN-MA art. 923; CNN art. 356, §
    4º), e o endereço ao registro e ao instrumento (Lei 9.492, art. 22, II).
    Até o LD08 a tela não os pedia, e nenhum papel os tinha."""
    tela = s["c"].get("/protesto/novo").get_data(as_text=True)
    assert 'name="apresentante_documento"' in tela
    assert 'name="apresentante_endereco"' in tela
    endereco = "Rua das Flores, 10, Centro, Cidade Exemplo/MA"
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _apontado(s, p, p["itens"][0], apresentante_nome=CREDOR,
                    apresentante_documento=CPF_CREDOR,
                    apresentante_endereco=endereco)
    ficha = _html.unescape(s["c"].get(f"/protesto/{tid}").get_data(as_text=True))
    assert CPF_CREDOR in ficha and endereco in ficha
    aviso = _aviso(s, tid)
    papel = _papel(s, f"/protesto/avisos/{aviso['id']}.odt")
    assert f"Apresentante: {CREDOR}, CPF/CNPJ {CPF_CREDOR}" in papel["texto"], papel["texto"]
    r = _post(s, f"/protesto/avisos/{aviso['id']}/entrega", "/protesto/avisos",
              entregue="1", recebido_por=DEVEDOR, quando=_hoje(s),
              comprovante=_canhoto(aviso))
    assert any("intimação pessoal foi lavrada" in a for a in _avisos(r)), _avisos(r)
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert _lancado(r, "Protesto"), _avisos(r)
    com_endereco = f"Apresentante: {CREDOR}, endereço {endereco}."
    assert com_endereco in _ato(s, tid, "PROTESTO")["teor"]
    _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    assert com_endereco in instrumento["teor"], instrumento["teor"]
    _sem_sobra(instrumento["teor"])


def test_o_balcao_recusa_o_cpf_do_apresentante_que_nao_fecha_o_digito(s):
    """Documento de ninguém num aviso que a casa assina: a tela recusa, diz por
    quê, e o título não entra."""
    antes = _um(s, "SELECT count(*) AS n FROM pt_titulos")["n"]
    r = _post(s, "/protesto/novo", "/protesto/novo",
              **{**TITULO, "apresentante_nome": CREDOR,
                 "apresentante_documento": "000.000.002-73"})
    assert any("CPF/CNPJ do apresentante" in a and "digito verificador" in a
               for a in _avisos(r)), _avisos(r)
    assert _um(s, "SELECT count(*) AS n FROM pt_titulos")["n"] == antes


# ===================================================== o pagamento


def test_o_pagamento_antes_do_protesto_vai_ao_livro_de_pagamentos_e_nao_a_certidao(s):
    """Lei 9.492, art. 19; CN-MA arts. 925, 927 e 930 (o Livro de Registro
    de Pagamentos e as suas colunas) — e art. 934: título pago antes do
    protesto não sai em certidão a terceiro."""
    p = _protocolo(s, PROTESTO, RETIRADA, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    titulo = _um(s, "SELECT * FROM pt_titulos WHERE id=%s", (tid,))
    r = _lancar(s, tid, "PAGAMENTO", p, p["itens"][1], valor_pago="1.234,56",
                emolumentos="30,00", forma_pagamento="PIX",
                forma_identificacao="PIX E2E 0001")
    assert _lancado(r, "Pagamento"), _avisos(r)
    ato = _ato(s, tid, "PAGAMENTO")
    assert ato["livro_serie"] == "PT_PAGAMENTO"
    assert (ato["folha"], ato["numero_ordem"]) == (1, 1)
    assert _situacao(s, tid) == "PAGO"
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/pagamento"
    assert pedido["envelope"]["natureza"]["tipo"] == 8
    assert ato["selo"] == _selo_de(s, "pt_atos", ato["id"])

    # O TERMO É A LINHA DO LIVRO DE PAGAMENTOS (CN-MA art. 930, a a h).
    [linha] = _linhas_do_livro(s, "pagamentos")
    assert linha == ["1", _br(_hoje(s)), titulo["protocolo"], "Nota Promissória",
                     "1.234,56", "30,00", DEVEDOR, CREDOR,
                     "pago por PIX — PIX E2E 0001"]
    [protocolo] = _linhas_do_livro(s, "protocolo")
    assert f"pago em {_br(_hoje(s))}" in protocolo[OCORRENCIAS]

    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "NEGATIVA"
    assert f"{DEVEDOR} CPF: {CPF_DEVEDOR}" in cert["teor"]


def test_o_pagamento_da_ao_devedor_a_quitacao_do_titulo(s):
    """Lei 9.492, art. 19, § 2º («dará a respectiva quitação»); CN-MA art.
    927 e art. 930, § 1º. O recibo do caixa é o dos emolumentos; a quitação do
    valor do título é papel próprio (LD04), e sai do pagamento lançado."""
    p = _protocolo(s, PROTESTO, RETIRADA)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "PAGAMENTO", p, p["itens"][1], valor_pago="1.234,56",
                emolumentos="30,00", forma_pagamento="PIX")
    assert _lancado(r, "Pagamento"), _avisos(r)
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    achado = re.search(r'href="([^"]*quita[^"]*)"', ficha)
    assert achado, "a ficha do título pago não oferece a quitação"
    papel = _papel(s, _html.unescape(achado.group(1)))
    assert DEVEDOR in papel["texto"] and "1.234,56" in papel["texto"]
    # O pagamento já está no livro antes da quitação (CN-MA art. 930, § 1º),
    # e o papel leva o selo do próprio pagamento (CN-MA art. 131).
    ato = _ato(s, tid, "PAGAMENTO")
    assert ("Pagamento lançado no Livro de Registro de Pagamentos, Livro "
            f"{ato['livro_numero']}, folha {ato['rotulo']}, sob o n.º "
            f"{ato['numero_ordem']}") in papel["texto"], papel["texto"]
    _confere_o_selo_no_papel(papel, _selo_de(s, "pt_atos", ato["id"]))
    _confere_a_serventia_no_papel(papel)


def test_a_quitacao_so_sai_do_pagamento_que_ficou_lancado(s):
    """O CAMINHO DE ERRO DA QUITAÇÃO. O pagamento cujo selo não saiu foi
    anulado (`cancelado = 1`) e o título voltou à situação de antes: não há
    pagamento no livro, e quitar seria dar ao devedor papel de um pagamento
    que não existiu (Lei 9.492, art. 19, § 2º; CN-MA art. 930, § 1º). A ficha
    não oferece a quitação, e o endereço dela recusa — o do ato anulado e o de
    ato que não é pagamento."""
    p = _protocolo(s, PROTESTO, RETIRADA)
    tid = _apontado(s, p, p["itens"][0])
    s["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    r = _lancar(s, tid, "PAGAMENTO", p, p["itens"][1], valor_pago="1.234,56",
                forma_pagamento="PIX")
    assert any("Ato NÃO lançado" in a for a in _avisos(r)), _avisos(r)
    s["aparelho"].recusar_com = None
    anulado = _um(s, "SELECT * FROM pt_atos WHERE titulo_id=%s AND tipo='PAGAMENTO' "
                     "ORDER BY id", (tid,))
    assert anulado["cancelado"] == 1 and _situacao(s, tid) == "APONTADO"
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "quitacao" not in ficha
    apontamento = _ato(s, tid, "APONTAMENTO")
    for ato_id in (anulado["id"], apontamento["id"]):
        r = s["c"].get(f"/protesto/pagamentos/{ato_id}/quitacao.odt?formato=odt",
                       follow_redirects=True)
        assert r.mimetype == "text/html", ato_id
        assert any("a quitação só sai do pagamento lançado" in a
                   for a in _avisos(r)), _avisos(r)


def test_a_quitacao_pede_o_papel_de_quem_lanca_o_pagamento(s):
    """Quem tira a quitação é quem lança o pagamento: ADMIN, MANAGER e USER,
    os papéis de `/protesto/<id>/lancar`. Até o LD11 a rota só pedia o login,
    e o AUDITOR — que confere e não pratica ato — emitia a quitação de
    qualquer pagamento, o papel que o devedor mostra para provar que pagou
    (Lei 9.492, art. 19, § 2º). A ficha dele não oferece o botão, a rota
    recusa, e a recusa não deixa rastro de papel emitido; a emissão deixa
    (auditoria `PROTESTO_QUITACAO_ODT`)."""
    from conftest import cg_login
    p = _protocolo(s, PROTESTO, RETIRADA)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "PAGAMENTO", p, p["itens"][1], valor_pago="1.234,56",
                forma_pagamento="PIX")
    assert _lancado(r, "Pagamento"), _avisos(r)
    ato = _ato(s, tid, "PAGAMENTO")
    rota = f"/protesto/pagamentos/{ato['id']}/quitacao.odt?formato=odt"

    def _emitidas() -> list[str]:
        return [l["username_snapshot"] for l in _ler(
            s, """SELECT username_snapshot FROM audit_logs
                   WHERE action = 'PROTESTO_QUITACAO_ODT' AND entity_id = %s
                   ORDER BY id""", (ato["id"],))]

    for login, papel in (("conferente", "AUDITOR"), ("escrevente", "USER")):
        s["db"].create_user(login, f"{papel} DE EXEMPLO", "Senha#12345", papel)
    auditor = s["app"].test_client()
    cg_login(auditor, "conferente", "Senha#12345")
    ficha = auditor.get(f"/protesto/{tid}")
    assert ficha.status_code == 200
    assert "quitacao" not in ficha.get_data(as_text=True)
    assert auditor.get(rota).status_code == 403
    assert _emitidas() == []

    escrevente = s["app"].test_client()
    cg_login(escrevente, "escrevente", "Senha#12345")
    assert "quitacao" in escrevente.get(f"/protesto/{tid}").get_data(as_text=True)
    r = escrevente.get(rota)
    assert r.status_code == 200 and r.get_data()[:2] == b"PK"
    assert _emitidas() == ["escrevente"]


# ===================================================== a desistência


def test_a_desistencia_sela_a_retirada_e_o_titulo_retirado_nao_sai_na_certidao(s):
    """Lei 9.492, art. 16; CN-MA arts. 936 (retirada antes do protesto),
    908, § 1º (a ocorrência no Livro de Protocolo) e 934 (não sai certidão a
    terceiro de título retirado antes do protesto)."""
    p = _protocolo(s, PROTESTO, RETIRADA, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "DESISTENCIA", p, p["itens"][1],
                motivo="O credor desistiu antes do protesto, por escrito.")
    assert _lancado(r), _avisos(r)
    ato = _ato(s, tid, "DESISTENCIA")
    assert _situacao(s, tid) == "DESISTIDO"
    assert ato["selo"] == _selo_de(s, "pt_atos", ato["id"])
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/retirada"
    assert pedido["envelope"]["natureza"]["tipo"] == 9
    [linha] = _linhas_do_livro(s, "protocolo")
    assert f"retirado pelo apresentante em {_br(_hoje(s))}" in linha[OCORRENCIAS]
    assert _certidao(s, p, p["itens"][2])["tipo"] == "NEGATIVA"


# ===================================================== a sustação


def test_a_sustacao_impede_o_protesto_e_a_revogacao_o_devolve_sem_nova_intimacao(s):
    """Lei 9.492, art. 17, §§ 1º e 2º; CN-MA arts. 937 e 938 — e as duas
    ordens averbadas no Livro de Protocolo (CN-MA art. 908, §§ 1º e 5º). A
    ordem judicial não é ato da serventia: não sela e não cobra."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    _intimado_em_maos(s, tid)
    selos_antes = len(_pedidos_de_selo(s))
    r = _lancar(s, tid, "SUSTACAO", juizo="1ª Vara Cível de Cidade Exemplo",
                processo="0800001-00.2026.8.10.0001", recebido_em=_hoje(s))
    assert _lancado(r), _avisos(r)
    assert len(_pedidos_de_selo(s)) == selos_antes           # não sela
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "PROTESTO SUSTADO POR ORDEM JUDICIAL" in ficha
    assert 'value="PROTESTO"' not in ficha
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert any("art. 17, § 1º" in a for a in _avisos(r)), _avisos(r)
    assert _situacao(s, tid) == "INTIMADO"

    r = _lancar(s, tid, "REVOGACAO_SUSTACAO", recebido_em=_hoje(s))
    assert _lancado(r), _avisos(r)
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert _lancado(r, "Protesto"), _avisos(r)
    # SEM NOVA INTIMAÇÃO: a única intimação é a de antes da ordem.
    assert len(_ler(s, "SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo='INTIMACAO'",
                    (tid,))) == 1
    hoje = _br(_hoje(s))
    [linha] = _linhas_do_livro(s, "protocolo")
    for ocorrencia in (f"sustação judicial em {hoje}", f"sustação revogada em {hoje}",
                       f"protestado em {hoje}"):
        assert ocorrencia in linha[OCORRENCIAS], (ocorrencia, linha)
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "POSITIVA" and f"protestado em {hoje}" in cert["teor"]


# ===================================================== o cancelamento


def test_o_cancelamento_sela_a_baixa_e_a_certidao_dele_so_sai_a_pedido_escrito(s):
    """Lei 9.492, arts. 26 e 27, § 2º; CN-MA arts. 942, § 2º (anuência), 944
    e 948 (o cancelado não sai em certidão, salvo a pedido escrito do devedor
    ou por ordem judicial) — e o fecho do art. 26 na certidão de
    cancelamento."""
    p = _protocolo(s, PROTESTO, PROTESTO, CANCELAMENTO, CERTIDAO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    ato_protesto = _ato(s, tid, "PROTESTO")
    r = _lancar(s, tid, "CANCELAMENTO", p, p["itens"][2], hipotese="ANUENCIA_CREDOR",
                fundamento="Carta de anuência do credor, com firma reconhecida.")
    assert _lancado(r), _avisos(r)
    baixa = _ato(s, tid, "CANCELAMENTO")
    assert _situacao(s, tid) == "CANCELADO"
    assert baixa["selo"] == _selo_de(s, "pt_atos", baixa["id"])
    pedido = _pedidos_de_selo(s)[-1]
    assert pedido["caminho"] == "/selo/protesto/baixa-cancelamento"
    assert pedido["envelope"]["natureza"]["tipo"] == 9
    hoje = _br(_hoje(s))
    [linha] = _linhas_do_livro(s, "protocolo")
    assert f"protesto cancelado em {hoje}" in linha[OCORRENCIAS]

    # A TERCEIRO, o cancelado não aparece: negativa.
    assert _certidao(s, p, p["itens"][3])["tipo"] == "NEGATIVA"
    # A PEDIDO ESCRITO DO DEVEDOR, a certidão de cancelamento — fiel ao
    # registro e à baixa.
    cert = _certidao(s, p, p["itens"][4], autorizacao="DEVEDOR_ESCRITO",
                     requerente=DEVEDOR)
    assert cert["tipo"] == "CANCELAMENTO"
    for esperado in (
            "a requerimento escrito do próprio devedor",
            f"Livro {ato_protesto['livro_numero']}, fl. {ato_protesto['rotulo']}, "
            f"n. {ato_protesto['numero_ordem']}",
            f"protestado em {hoje}", f"CANCELADO em {hoje}",
            "consta a BAIXA e o CANCELAMENTO do mesmo de acordo com o art. 26",
            "dou fé"):
        assert esperado in cert["teor"], (esperado, cert["teor"])
    _sem_sobra(cert["teor"])
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert "CANCELAMENTO DE PROTESTO" in papel["texto"]
    assert cert["teor"] in papel["texto"]
    _confere_a_serventia_no_papel(papel)
    _confere_o_selo_no_papel(papel, _selo_de(s, "pt_certidoes", cert["id"]))


def test_o_cancelamento_lavra_o_termo_da_baixa(s):
    """Lei 9.492, art. 26, §§ 5º e 6º: no registro eletrônico, «o termo do
    cancelamento será lançado em documento apartado»; CN-MA art. 896. Até o
    LD04 o ato gravava a hipótese e o fundamento, e `pt_atos.teor` ficava
    vazio."""
    p = _protocolo(s, PROTESTO, PROTESTO, CANCELAMENTO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    r = _lancar(s, tid, "CANCELAMENTO", p, p["itens"][2], hipotese="ANUENCIA_CREDOR",
                fundamento="Carta de anuência do credor, com firma reconhecida.")
    assert _lancado(r), _avisos(r)
    termo = _ato(s, tid, "CANCELAMENTO")["teor"] or ""
    assert "CANCELAMENTO" in termo.upper() and "NP-0001" in termo, termo
    # O protesto cancelado se identifica como o registro dele, e o termo diz a
    # hipótese do catálogo e o fundamento que quem cancelou escreveu.
    protesto = _ato(s, tid, "PROTESTO")
    hoje = _br(_hoje(s))
    for esperado in (
            f"Certifico que, em {hoje}, foi cancelado o registro do protesto",
            f"Registro do protesto: Livro {protesto['livro_numero']}, folha "
            f"{protesto['rotulo']}, sob o n.º {protesto['numero_ordem']}, em {hoje}.",
            f"Devedor: {DEVEDOR}, CPF 00000000191",
            "Hipótese do cancelamento: Anuência do credor ou do apresentante.",
            "Fundamento do caso: Carta de anuência do credor, com firma reconhecida."):
        assert esperado in termo, (esperado, termo)
    _sem_sobra(termo)


def test_o_protesto_pago_depois_de_lavrado_ainda_se_cancela(s):
    """O REGISTRO DA DECISÃO DO OFICIAL DE 21/10/2026 (LH13, pergunta 17,
    letra c): «protesto nao pode ser pago na serventia depois de lavrar». Ele
    voltou atrás na decisão de 24/08/2026, que admitia o pagamento depois do
    protesto — e deixava o título PAGO com o protesto em pé, para sempre na
    certidão positiva, porque o cancelamento só aceitava PROTESTADO. Era o
    `xfail` do LD04 (relatórios/LD04.perguntas.md, pergunta 1).

    Daqui em diante, pelas telas:
      1. a ficha do PROTESTADO não oferece o pagamento, e diz por quê; o
         lançamento mandado assim mesmo recusa com a frase da casa — o caminho
         é o credor, a carta de anuência e o cancelamento (Lei 9.492, art. 26,
         § 1º; CN-MA art. 942, § 2º) —, e nada se lança nem se sela;
      2. o LEGADO — o título pago aqui depois de protestado pela regra antiga
         — AINDA SE CANCELA: pela anuência do credor (ou ordem judicial), e
         não pelo pagamento lançado aqui (a letra «a», que o oficial não
         escolheu); cancelado, sai da certidão a terceiro."""
    p = _protocolo(s, PROTESTO, PROTESTO, RETIRADA, CANCELAMENTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'name="ato" value="PAGAMENTO"' not in ficha
    assert 'name="ato" value="CANCELAMENTO"' in ficha
    assert "não se paga mais nesta serventia" in ficha
    selos_antes = len(_pedidos_de_selo(s))
    r = _lancar(s, tid, "PAGAMENTO", p, p["itens"][2], valor_pago="1.234,56",
                forma_pagamento="PIX")
    assert not _lancado(r), _avisos(r)
    assert any("não se paga mais" in a and "carta de anuência" in a
               and "art. 26, § 1º" in a for a in _avisos(r)), _avisos(r)
    assert _situacao(s, tid) == "PROTESTADO"
    assert not _ler(s, "SELECT id FROM pt_atos WHERE titulo_id=%s AND tipo='PAGAMENTO'",
                    (tid,))
    assert len(_pedidos_de_selo(s)) == selos_antes

    # O LEGADO, como a regra de 24/08/2026 o deixou no banco: o pagamento
    # lançado depois do protesto, e o título PAGO.
    with s["db"].transaction() as con:
        nativo(con).escrever(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, detalhe_json,
                   origem, criado_em)
               VALUES (%s, 'PAGAMENTO', %s, '{"forma_pagamento": "PIX"}',
                       'MANUAL', %s)""", (tid, _hoje(s), _hoje(s)))
        nativo(con).escrever("UPDATE pt_titulos SET situacao='PAGO' WHERE id=%s",
                             (tid,))
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "PAGO DEPOIS DE PROTESTADO" in ficha
    assert 'name="ato" value="CANCELAMENTO"' in ficha
    assert 'value="ANUENCIA_CREDOR"' in ficha and 'value="ORDEM_JUDICIAL"' in ficha
    r = _lancar(s, tid, "CANCELAMENTO", p, p["itens"][3], hipotese="PAGAMENTO",
                fundamento="Título quitado nesta serventia, com recibo.")
    assert not _lancado(r) and any("carta de anuência" in a for a in _avisos(r)), \
        _avisos(r)
    assert _situacao(s, tid) == "PAGO"
    r = _lancar(s, tid, "CANCELAMENTO", p, p["itens"][3], hipotese="ANUENCIA_CREDOR",
                fundamento="Carta de anuência do credor, com firma reconhecida.")
    assert _lancado(r), _avisos(r)
    assert _situacao(s, tid) == "CANCELADO"
    baixa = _ato(s, tid, "CANCELAMENTO")
    assert baixa["selo"] == _selo_de(s, "pt_atos", baixa["id"])
    assert _pedidos_de_selo(s)[-1]["caminho"] == "/selo/protesto/baixa-cancelamento"
    assert _certidao(s, p, p["itens"][4])["tipo"] == "NEGATIVA"


# ===================================================== a ordem judicial depois


PROCESSO_DA_ORDEM = "0800002-00.2026.8.10.0001"
JUIZO_DA_ORDEM = "2ª Vara Cível de Cidade Exemplo"
FECHO_DA_PRECARIA = ("Resultado emitido em cumprimento à decisão judicial — "
                     f"Processo nº {PROCESSO_DA_ORDEM}.")


def _suspenso(s, tid: int, **marca) -> dict:
    """A ordem que suspende os efeitos, lançada pela ficha com a marca que o
    formulário oferece (LH13): o caráter e as duas caixas."""
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    for campo in ('name="carater"', 'name="manda_negativa"', 'name="segredo_de_justica"'):
        assert campo in ficha, f"o formulário da ordem não oferece {campo}"
    r = _lancar(s, tid, "EFEITO_SUSPENSIVO", juizo=JUIZO_DA_ORDEM,
                processo=PROCESSO_DA_ORDEM, observacao="tutela provisória", **marca)
    assert _lancado(r), _avisos(r)
    return _ato(s, tid, "EFEITO_SUSPENSIVO")


def test_protesto_com_efeitos_suspensos_sai_como_consta_com_sustacao_precaria(s):
    """O REGISTRO DA DECISÃO DO OFICIAL DE 21/10/2026 (LH13, pergunta 18,
    letra a): seguir o CNN art. 263-K (Prov. CN 253, de 18/08/2026), que
    prevalece sobre o CN-MA arts. 944 e 948 da decisão dele de 14/10/2026. O
    protesto com os efeitos suspensos por decisão PROVISÓRIA sai na certidão
    a terceiro como «CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA», com os dados do
    registro, o número da ação e o caráter provisório, e fecha com
    «Resultado emitido em cumprimento à decisão judicial — Processo nº …»
    (III). Era o `xfail` do LD04 (pergunta 2).

    A COBRANÇA E O SELO são os da certidão positiva de protesto — a tabela
    não tem item próprio para ela (17.5.1, `/selo/protesto/certidao`)."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    selos_antes = len(_pedidos_de_selo(s))
    ordem = _suspenso(s, tid, carater="PROVISORIA")
    assert ordem["ordem_carater"] == "PROVISORIA"
    assert len(_pedidos_de_selo(s)) == selos_antes          # a ordem não sela
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "«CONSTA COM SUSTAÇÃO" in ficha and "data-ordem-sem-marca" not in ficha
    protesto = _ato(s, tid, "PROTESTO")
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "POSITIVA"
    teor = cert["teor"]
    for esperado in (
            "CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA",
            f"decisão judicial de caráter provisório ({JUIZO_DA_ORDEM}), na ação "
            f"n. {PROCESSO_DA_ORDEM}",
            "1) Título n. NP-0001", f"protestado em {_br(_hoje(s))}",
            f"Livro {protesto['livro_numero']}, fl. {protesto['rotulo']}, "
            f"n. {protesto['numero_ordem']}", FECHO_DA_PRECARIA):
        assert esperado in teor, (esperado, teor)
    assert teor.rstrip().endswith(FECHO_DA_PRECARIA), teor
    _sem_sobra(teor)
    papel = _papel(s, f"/protesto/certidoes/{cert['id']}/odt")
    assert teor in papel["texto"]
    _confere_o_selo_no_papel(papel, _selo_de(s, "pt_certidoes", cert["id"]))
    assert _pedidos_de_selo(s)[-1]["caminho"] == "/selo/protesto/certidao"


def test_a_decisao_definitiva_tira_o_protesto_da_certidao(s):
    """CNN art. 263-K, I: «NADA CONSTA», inclusive quando a sustação veio de
    decisão judicial DEFINITIVA."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    _suspenso(s, tid, carater="DEFINITIVA")
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "NEGATIVA", cert["teor"]
    assert PROCESSO_DA_ORDEM not in cert["teor"]


def test_a_ordem_que_manda_emitir_negativa_se_cumpre_nos_limites(s):
    """CNN art. 263-K, § 1º: ressalvada a determinação judicial específica — a
    decisão provisória que manda EXPRESSAMENTE emitir negativa se cumpre nos
    exatos limites, e o protesto dela não sai."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    _suspenso(s, tid, carater="PROVISORIA", manda_negativa="1")
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "NEGATIVA", cert["teor"]
    assert "PRECÁRIA" not in cert["teor"]


def test_no_segredo_de_justica_a_certidao_diz_so_a_sustacao_e_o_processo(s):
    """CNN art. 263-K, § 1º: no segredo de justiça, a certidão informa só a
    sustação e o número do processo — nada do título, do credor, do valor,
    do registro nem do juízo."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    _suspenso(s, tid, carater="PROVISORIA", segredo_de_justica="1")
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "POSITIVA"
    teor = cert["teor"]
    assert (f"1) CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA, na ação n. "
            f"{PROCESSO_DA_ORDEM}." in teor), teor
    assert teor.rstrip().endswith(FECHO_DA_PRECARIA), teor
    for fora in ("NP-0001", "1.234,56", CREDOR, "protestado em", JUIZO_DA_ORDEM,
                 "Livro "):
        assert fora not in teor, (fora, teor)
    _sem_sobra(teor)


def test_a_ordem_sem_marca_fica_fora_e_a_tela_avisa_ate_alguem_marcar(s):
    """As ordens lançadas antes de 21/10/2026 não têm a marca do art. 263-K:
    continuam como sempre — o protesto fora da certidão — até alguém marcar.
    A tela de certidões e a ficha AVISAM que há ordem a marcar; a ficha marca
    (sem selo, sem cobrança, com a auditoria), e a certidão seguinte já segue
    a marca."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    ordem = _suspenso(s, tid, carater="PROVISORIA")
    with s["db"].transaction() as con:      # como ficou a ordem de antes do LH13
        nativo(con).escrever(
            """UPDATE pt_atos SET ordem_carater = NULL, ordem_manda_negativa = NULL,
                      ordem_segredo_de_justica = NULL, ordem_marcada_em = NULL,
                      ordem_marcada_por = NULL WHERE id = %s""", (ordem["id"],))
    tela = s["c"].get("/protesto/certidoes").get_data(as_text=True)
    assert "data-ordens-sem-marca" in tela and "NP-0001" in tela
    assert f'/protesto/{tid}"' in tela
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert "data-ordem-sem-marca" in ficha and "fica fora da certidão" in ficha
    assert _certidao(s, p, p["itens"][2])["tipo"] == "NEGATIVA"

    selos_antes = len(_pedidos_de_selo(s))
    r = _post(s, f"/protesto/{tid}/ordem/{ordem['id']}/marcar", f"/protesto/{tid}",
              carater="PROVISORIA")
    assert any("Ordem judicial marcada" in a for a in _avisos(r)), _avisos(r)
    assert len(_pedidos_de_selo(s)) == selos_antes
    marcada = _ato(s, tid, "EFEITO_SUSPENSIVO")
    assert marcada["ordem_carater"] == "PROVISORIA" and marcada["ordem_marcada_por"]
    assert _um(s, """SELECT id FROM audit_logs WHERE action='PROTESTO_ORDEM_MARCADA'
                      AND entity_id=%s ORDER BY id DESC LIMIT 1""", (ordem["id"],))
    assert "data-ordens-sem-marca" not in s["c"].get("/protesto/certidoes").get_data(
        as_text=True)
    cert = _certidao(s, p, p["itens"][3])
    assert cert["tipo"] == "POSITIVA" and FECHO_DA_PRECARIA in cert["teor"]


def test_a_marca_da_ordem_e_obrigatoria_ao_lancar(s):
    """A ordem nova sem o caráter recusa, com a frase que diz por quê: é ele
    que decide o que a certidão diz (art. 263-K)."""
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    r = _lancar(s, tid, "EFEITO_SUSPENSIVO", juizo=JUIZO_DA_ORDEM,
                processo=PROCESSO_DA_ORDEM)
    assert any("caráter da decisão" in a and "263-K" in a for a in _avisos(r)), \
        _avisos(r)
    assert not _ler(s, "SELECT id FROM pt_atos WHERE titulo_id=%s "
                       "AND tipo='EFEITO_SUSPENSIVO'", (tid,))


# ===================================================== o selo que não sai


ANTES_DO_ATO = {
    "PROTESTO": {},
    "PAGAMENTO": {"forma_pagamento": "PIX"},
    "DESISTENCIA": {"motivo": "O credor desistiu antes do protesto."},
}


@pytest.mark.parametrize("ato", sorted(ANTES_DO_ATO))
def test_selo_recusado_devolve_o_titulo_a_situacao_de_antes(s, ato):
    """O SELO QUE NÃO SAI DERRUBA O ATO (ordem do oficial de 16/09/2026, item
    1 do relato #77: «suspender o ato para corrigir o problema»), e a tela
    diz «tente de novo». Para que o «de novo» exista, o título tem de voltar
    à situação de antes: ficando PROTESTADO (ou PAGO, ou DESISTIDO) com o ato
    anulado, a ficha não oferecia mais o ato, o domínio recusava o segundo, e
    o título ficava no meio do caminho com um ato que não existiu."""
    campos = ANTES_DO_ATO[ato]
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _apontado(s, p, p["itens"][0])
    _intimado_em_maos(s, tid)
    s["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    r = _lancar(s, tid, ato, p, p["itens"][1], **campos)
    assert any("Ato NÃO lançado" in a for a in _avisos(r)), _avisos(r)
    anulado = _um(s, "SELECT * FROM pt_atos WHERE titulo_id=%s AND tipo=%s",
                  (tid, ato))
    assert anulado["cancelado"] == 1
    assert _situacao(s, tid) == "INTIMADO"

    s["aparelho"].recusar_com = None
    r = _lancar(s, tid, ato, p, p["itens"][1], **campos)
    assert _lancado(r), _avisos(r)
    novo = _ato(s, tid, ato)
    assert novo["id"] != anulado["id"]
    assert novo["selo"] == _selo_de(s, "pt_atos", novo["id"])


def test_intimacao_sem_selo_nao_deixa_o_titulo_intimado(s):
    """A intimação lançada pela ficha sem item para o selo é anulada — e o
    título continuava INTIMADO, de modo que o PROTESTO cabia sem intimação
    válida nenhuma (Lei 9.492, art. 14; o termo saía sem a certidão da
    intimação). Ele volta a APONTADO."""
    p = _protocolo(s, PROTESTO)
    tid = _apontado(s, p, p["itens"][0])
    r = _lancar(s, tid, "INTIMACAO", modo="PESSOAL")
    assert any("Ato NÃO lançado" in a for a in _avisos(r)), _avisos(r)
    assert _situacao(s, tid) == "APONTADO"
    ficha = s["c"].get(f"/protesto/{tid}").get_data(as_text=True)
    assert 'value="PROTESTO"' not in ficha


def test_protesto_que_nao_se_lavrou_nao_sai_na_certidao(s):
    """O protesto anulado porque o selo não saiu NÃO EXISTIU — e a certidão
    não pode mostrá-lo (Lei 9.492, art. 27; o mesmo filtro de `cancelado =
    0` que a relação diária, o XML da CENPROT e o repasse já usam). Sem o
    filtro, a busca da certidão lia o ato anulado como protesto em pé."""
    p = _protocolo(s, PROTESTO, PROTESTO, CERTIDAO)
    tid = _apontado(s, p, p["itens"][0])
    _intimado_em_maos(s, tid)
    s["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][1])
    assert any("Ato NÃO lançado" in a for a in _avisos(r)), _avisos(r)
    s["aparelho"].recusar_com = None
    cert = _certidao(s, p, p["itens"][2])
    assert cert["tipo"] == "NEGATIVA", cert["teor"]


def test_a_baixa_que_nao_se_lavrou_nao_tira_o_protesto_da_certidao(s):
    """O inverso, e o mais grave: o CANCELAMENTO anulado por falta de selo
    contava como baixa, e o protesto em pé SUMIA da certidão — a negativa
    sobre quem tem protesto, que é o papel que faz o banco emprestar para
    quem não devia (`protesto_certidao.emitir`)."""
    p = _protocolo(s, PROTESTO, PROTESTO, CANCELAMENTO, CERTIDAO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    s["aparelho"].recusar_com = (400, {"message": "recusado pelo teste"})
    r = _lancar(s, tid, "CANCELAMENTO", p, p["itens"][2], hipotese="ANUENCIA_CREDOR",
                fundamento="Carta de anuência do credor, com firma reconhecida.")
    assert any("Ato NÃO lançado" in a for a in _avisos(r)), _avisos(r)
    s["aparelho"].recusar_com = None
    assert _situacao(s, tid) == "PROTESTADO"
    cert = _certidao(s, p, p["itens"][3])
    assert cert["tipo"] == "POSITIVA", cert["teor"]
    assert "CANCELADO" not in cert["teor"]


# ===================================================== a central (CRA)


def test_o_titulo_da_cra_entra_apontado_e_o_protesto_diferido_sela_sem_entrar_no_caixa(s):
    """O título que chega pela CRA (93% dos desta casa) entra pela remessa,
    já apontado e com o apresentante do arquivo; o protesto dele é a
    posteriori (CN-MA art. 925, § 11): o item do protocolo, DIFERIDO na tela
    da cobertura, sela o ato, fica devido e NÃO entra no caixa. O instrumento
    traz o apresentante (Lei 9.492, art. 22, II) e o retorno à Central leva o
    protocolo."""
    tela = s["c"].get("/protesto/remessas").get_data(as_text=True)
    r = s["c"].post("/protesto/remessas/conferir",
                    data={"csrf_token": _token(tela),
                          "arquivo": (io.BytesIO(REMESSA_DA_CRA), "B0001307.221")},
                    content_type="multipart/form-data", follow_redirects=True)
    html = r.get_data(as_text=True)
    conteudo = _html.unescape(re.search(r'name="conteudo" value="([^"]*)"', html).group(1))
    r = s["c"].post("/protesto/remessas/receber",
                    data={"csrf_token": _token(html), "conteudo": conteudo,
                          "nome_arquivo": "B0001307.221", "apontar": "1"},
                    follow_redirects=True)
    assert any("Remessa recebida" in a for a in _avisos(r)), _avisos(r)
    titulo = _um(s, "SELECT * FROM pt_titulos ORDER BY id DESC LIMIT 1")
    assert titulo["origem"] == "CRA" and titulo["situacao"] == "APONTADO"
    assert titulo["apresentante_nome"]
    tid = titulo["id"]
    apontamento = _ato(s, tid, "APONTAMENTO")
    assert apontamento["livro_serie"] == "PT_APONTAMENTO"
    assert apontamento["numero_ordem"] == 1

    # O PROTOCOLO DO A POSTERIORI: o item fica a pagar, com quem paga e quando.
    p = _protocolo(s, PROTESTO, quitar=False)
    r = _post(s, "/selo/cobertura/diferir", "/selo/cobertura",
              item_id=str(p["itens"][0]), quem_paga="o devedor, no desfecho",
              quando=(date.fromisoformat(_hoje(s)) + timedelta(days=60)).isoformat(),
              motivo="Título da CRA, a posteriori (CN-MA art. 925, § 11).")
    assert any("Diferimento registrado" in a for a in _avisos(r)), _avisos(r)
    _intimado_em_maos(s, tid)
    caixa_antes = len(_ler(s, "SELECT id FROM cx_lancamentos ORDER BY id"))
    r = _lancar(s, tid, "PROTESTO", p, p["itens"][0],
                cobrar_protocolo_item=str(p["itens"][0]))
    assert _lancado(r, "Protesto"), _avisos(r)
    assert any("NÃO entrou no caixa" in a for a in _avisos(r)), _avisos(r)
    ato = _ato(s, tid, "PROTESTO")
    assert ato["selo"] == _selo_de(s, "pt_atos", ato["id"])
    assert ato["livro_serie"] == "PT_PROTESTO"
    assert len(_ler(s, "SELECT id FROM cx_lancamentos ORDER BY id")) == caixa_antes
    assert _ler(s, "SELECT ato_id FROM pt_emolumentos_diferidos WHERE titulo_id=%s",
                (tid,)) == [{"ato_id": ato["id"]}]

    _post(s, f"/protesto/{tid}/instrumento", f"/protesto/{tid}")
    instrumento = _um(s, "SELECT * FROM pt_instrumentos WHERE titulo_id=%s", (tid,))
    assert f"Apresentante: {titulo['apresentante_nome']}." in instrumento["teor"]

    r = _post(s, "/protesto/retornos/gerar", "/protesto/retornos",
              apresentante_codigo=titulo["apresentante_codigo"], dia=_hoje(s))
    assert any("Retorno e andamento gerados" in a for a in _avisos(r)), _avisos(r)
    retorno = _um(s, "SELECT id FROM pt_retornos WHERE tipo <> 'SDTBFOCRT' "
                     "ORDER BY id LIMIT 1")
    arquivo = s["c"].get(f"/protesto/retornos/{retorno['id']}/arquivo")
    assert titulo["protocolo"].encode() in arquivo.get_data()


# ===================================================== a relação diária


def test_a_relacao_diaria_traz_os_dados_do_art_130_do_cnn(s):
    """CNN art. 130: a certidão em forma de relação traz a espécie, a data do
    vencimento, a data do protesto e o valor protestado. O vencimento é
    coluna desde o LD04."""
    p = _protocolo(s, PROTESTO, PROTESTO)
    tid = _protestado(s, p, p["itens"][0], p["itens"][1])
    ontem = (date.fromisoformat(_hoje(s)) - timedelta(days=1)).isoformat()
    # O protesto de ONTEM: a relação é do dia que já fechou (CN-MA art. 949).
    with s["db"].transaction() as con:
        nativo(con).escrever("UPDATE pt_atos SET data_ato=%s WHERE titulo_id=%s",
                             (ontem + "T10:00:00", tid))
    _post(s, "/protesto/relacao-diaria/entidades", "/protesto/relacao-diaria",
          nome="ENTIDADE FICTÍCIA DE PROTEÇÃO AO CRÉDITO",
          documento="00000001000055", canal="DIRETO",
          habilitacao="Requerimento 1/2026", habilitada_em="2026-01-01")
    entidade = _um(s, "SELECT id FROM pt_relacao_entidades ORDER BY id")
    _post(s, "/protesto/relacao-diaria/gerar", "/protesto/relacao-diaria",
          dia=ontem, entidade_id=str(entidade["id"]))
    relacao = _um(s, "SELECT * FROM pt_relacoes_diarias ORDER BY id")
    teor = relacao["teor"]
    assert "informação reservada" in teor.lower()
    for esperado in (DEVEDOR, "00000000191", "NP", _br(ontem), "1.234,56"):
        assert esperado in teor, (esperado, teor)
    assert "10/02/2025" in teor, teor
