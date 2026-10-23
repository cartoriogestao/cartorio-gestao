"""Do protocolo à certidão, no Registro Civil das Pessoas Naturais — LT01.

O PEDIDO, do oficial em 20/10/2026: «quero que seja possível do protocolo à
certidão. Minha maior preocupação é que TODOS os atos precisam ter uma
certidão adequada» — e depois: «TERMO E CERTIDÃO». Cada ato do RCPN tem de
sair com o TERMO adequado (o texto lavrado no livro) E a CERTIDÃO adequada, e
os dois têm de bater entre si.

POR QUE PELAS TELAS, e não pelos módulos: as regras têm teste próprio em
`test_rc_*`. O que estes guardam é o caminho que o balcão percorre — abrir o
caixa, abrir o protocolo, acrescentar o item da tabela, quitar, atender o
protocolo, lavrar, selar, conferir o livro, emitir a certidão — com login e
CSRF, como o navegador faz. Uma peça que funciona sozinha e não se liga à
seguinte é exatamente o que um teste de módulo não vê (o Livro D da
habilitação, abaixo, é o exemplo).

O SELADOR É O DE MENTIRA DA CASA (`selador_falso`, TLS de verdade numa porta
local), ligado SEM o protocolo pago da bancada (`protocolo_pago=False`): o
protocolo, o item e o pagamento são os que o próprio teste monta pelas telas,
e a trava do selo pago (LX16) roda sobre eles.

A BASE NORMATIVA vai citada em cada teste: Lei 6.015/1973 (LRP), o Código
Nacional de Normas (Prov. CNJ 149/2023, «CNN») e o Código de Normas
Extrajudicial do Maranhão (Prov. COGEX 28/2026, «CN-MA»). A matriz completa
dos elementos está em `docs/REQUISITOS_LEGAIS.md` e é conferida, modelo por
modelo, em `tests/test_requisitos_rcpn.py`. O que quebra e não é conserto
pequeno fica em `xfail(strict=True, reason="DEFEITO: …")` — a asserção é a
da lei, e não a do que o sistema faz hoje.

SÓ OS FICTÍCIOS DA CASA (docs/AGENTES.md): pessoas «Exemplo», Cidade Exemplo,
CNS 000000, CPF da lista `documentos_ficticios.txt`.
"""
from __future__ import annotations

import io
import json
import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from bd_nativo import banco                                      # noqa: E402

SENHA = "Senha#12345"
OFICIAL = "MARIO EXEMPLO DOS SANTOS"
FUNCAO = "Oficial Registrador"
FOLHAS = tuple(str(9300001 + i) for i in range(12))

# A TABELA DE EMOLUMENTOS DE TESTE: o código do TJ é o que a casa usa para o
# ato (`ato_selado.CODIGO_DO_REGISTRO_DO_CIVIL`, `CODIGO_DO_ATO_DO_CIVIL`,
# `CODIGO_DA_CERTIDAO`); o PREÇO é de exemplo, e não o da tabela do TJMA. O
# caixa lê o valor daqui — no balcão o valor do protocolo não se digita.
ITENS_DA_TABELA = {
    # codigo (cx_servicos) : (codigo_tj, descricao, emolumento, total)
    9141: ("14.1.1", "Habilitação e registro de casamento", "180,00", "200,00"),
    9116: ("14.1.6", "Registro de casamento com habilitação de outra serventia",
           "120,00", "130,00"),
    9120: ("14.2", "Registro no Livro E", "90,00", "100,00"),
    9132: ("14.3.2", "Registro de opção de nacionalidade", "90,00", "100,00"),
    9180: ("14.8", "Registro de união estável", "90,00", "100,00"),
    9144: ("14.4.1", "Averbação à margem do registro", "40,00", "45,00"),
    9147: ("14.7", "Anotação", "20,00", "22,00"),
    9110: ("14.10", "Retificação", "40,00", "45,00"),
    9151: ("14.5.1", "Certidão (segunda via)", "30,00", "33,50"),
    9156: ("14.5.6", "Certidão de inteiro teor", "50,00", "55,00"),
}
POR_TJ = {tj: cod for cod, (tj, *_r) in ITENS_DA_TABELA.items()}


# ------------------------------------------------------------------ a casa


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _semear(bd) -> None:
    """O que a casa de verdade já tem carregado antes do primeiro balcão: a
    tabela de emolumentos e o cadastro de municípios do IBGE (é ele que deixa
    a naturalidade declarada chegar à pessoa — `rc_assento._naturalidade_do_titular`)."""
    import ibge_schema as IB
    vig = bd.valor("SELECT codigo FROM cx_vigencias WHERE vigente = 1 "
                   "ORDER BY codigo LIMIT 1")
    if vig is None:
        vig = 1
        bd.escrever("INSERT INTO cx_vigencias (codigo, descricao, vigente) "
                    "VALUES (%s, '2026', 1)", (vig,))
    for codigo, (tj, descricao, emol, total) in ITENS_DA_TABELA.items():
        bd.escrever(
            """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                   descricao_norm, ativo)
               VALUES (%s, %s, %s, upper(%s), 1) ON CONFLICT DO NOTHING""",
            (codigo, tj, descricao, descricao))
        bd.escrever(
            """INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (%s, %s, %s, '1,00', '1,00', '1,00', '0,00', %s)
               ON CONFLICT DO NOTHING""", (codigo, vig, emol, total))
    # Cidade Exemplo: código fictício (o IBGE não numera acima de 53xxxxx).
    bd.escrever(
        """INSERT INTO ib_municipios (codigo_ibge, codigo_uf, codigo_mun, uf,
               nome, nome_norm, origem)
           VALUES (2199999, 21, '99999', 'MA', 'Cidade Exemplo', %s, 'TESTE')
           ON CONFLICT DO NOTHING""", (IB.normalizar_nome("Cidade Exemplo"),))


@pytest.fixture()
def balcao(cg_casa):
    """A serventia de teste, com o oficial logado, o papel e o selador.

    O OFICIAL TEM FUNÇÃO: é ela que o termo escreve depois do nome («Eu,
    MARIO …, Oficial Registrador, dou fé e assino»). Sem função o termo cai no
    piso «Oficial», e o teste não saberia distinguir regra de acaso.
    """
    from selador_de_bancada import ligar_o_selador

    db = cg_casa["db"]
    db.create_user("mario", OFICIAL, SENHA, "ADMIN")
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("UPDATE users SET funcao = %s WHERE username = 'mario'",
                    (FUNCAO,))
        _semear(bd)
    db.set_settings({"serventia_titular": OFICIAL,
                     "serventia_titulo": FUNCAO})
    c = cg_casa["cliente"]
    c.post("/login", data={"username": "mario", "password": SENHA,
                           "csrf_token": _token(c.get("/login").get_data(
                               as_text=True))}, follow_redirects=True)
    casa = dict(cg_casa)
    # A CAIXA DE PAPEL DE SEGURANÇA CHEGOU — pela tela do papel.
    _post(casa, "/rcpn/papel", "/rcpn/papel/receber",
          fornecedor="ARPENBRASIL", serie="IA", codigo_de=FOLHAS[0],
          codigo_ate=FOLHAS[-1], nota_fiscal="NF DE TESTE")
    assert _um(casa, "SELECT count(*) AS n FROM pp_folhas")["n"] == len(FOLHAS)
    with ligar_o_selador(cg_casa, protocolo_pago=False) as aparelho:
        casa["aparelho"] = aparelho
        yield casa


def _post(casa, tela: str, rota: str, **dados):
    """POST como o navegador: o token sai da tela de onde o botão é clicado.
    Lista vira campo repetido (as caixinhas marcadas de `protocolo_item_id`)."""
    c = casa["cliente"]
    dados["csrf_token"] = _token(c.get(tela).get_data(as_text=True))
    return c.post(rota, data=dados, follow_redirects=True)


def _ler(casa, sql: str, parametros=()):
    with casa["db"].connect() as con:
        return banco(con).ler(sql, parametros)


def _um(casa, sql: str, parametros=()):
    linhas = _ler(casa, sql, parametros)
    return linhas[0] if linhas else None


def _avisos(html: str) -> str:
    """O texto dos avisos (flash) da página, para a mensagem do assert."""
    return " | ".join(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", m)).strip()
                      for m in re.findall(
                          r'<div class="flash[^"]*"[^>]*>(.*?)</div>', html, re.S))


def _pedidos_de_selo(casa) -> list[dict]:
    """O que chegou ao aparelho: caminho e envelope de cada selo pedido."""
    return [{"caminho": p["caminho"], **json.loads(p["corpo"] or "{}")}
            for p in casa["aparelho"].pedidos if "/selo/" in p["caminho"]]


# ------------------------------------------------------- o caixa e o protocolo


def _abrir_protocolo(casa, *, interessado: str, codigos=()) -> dict:
    """Caixa aberto, protocolo aberto, itens acrescentados e quitados, e o
    protocolo em atendimento — o que o balcão faz antes de lavrar.

    Devolve o protocolo e, por código do TJ, o `id` do item (é ele que a tela
    do ato marca em «Selar», para o item valer para AQUELE ato e não para o
    seguinte do mesmo protocolo)."""
    _post(casa, "/caixa", "/caixa", acao="abrir", saldo_inicial="0,00")
    _post(casa, "/caixa/protocolos", "/caixa/protocolos", acao="novo",
          interessado=interessado, telefone="(99) 99999-0000",
          atribuicao="RCPN", assunto="Registro civil")
    p = _um(casa, "SELECT id, numero FROM cx_protocolos WHERE interessado = %s "
                  "ORDER BY id DESC LIMIT 1", (interessado,))
    assert p, "o protocolo não abriu"
    pid = int(p["id"])
    tela = f"/caixa/protocolos/{pid}"
    for tj in codigos:
        _post(casa, tela, f"{tela}/itens", acao="acrescentar",
              servico=str(POR_TJ[tj]), quantidade="1")
    itens = {}
    if codigos:
        r = _post(casa, tela, f"{tela}/itens", acao="quitar_todos",
                  forma_pagamento="DINHEIRO")
        linhas = _ler(casa, "SELECT id, codigo_ato, quitado, lancamento_id "
                            "FROM cx_protocolo_atos WHERE protocolo_id = %s "
                            "ORDER BY id", (pid,))
        assert [i["codigo_ato"] for i in linhas] == list(codigos)
        assert all(int(i["quitado"]) == 1 for i in linhas), _avisos(
            r.get_data(as_text=True))
        # QUITAR É LANÇAR NO CAIXA (decisão de 27/08/2026): o dinheiro entrou.
        assert all(i["lancamento_id"] for i in linhas)
        itens = {i["codigo_ato"]: int(i["id"]) for i in linhas}
    _post(casa, "/selo/cobertura", "/selo/cobertura/atender",
          protocolo=p["numero"])
    return {"id": pid, "numero": p["numero"], "itens": itens}


def _do_protocolo(protocolo: dict | None, *codigos: str) -> dict:
    """Os campos da tela do ato que amarram o protocolo e marcam os itens."""
    if not protocolo:
        return {}
    return {"protocolo_id": str(protocolo["id"]),
            "protocolo_item_id": [str(protocolo["itens"][c]) for c in codigos]}


def _item_gasto_pelo_ato(casa, protocolo: dict, codigo: str, *, tabela: str,
                         ato_id: int) -> None:
    """A unidade paga do item foi gasta por ESTE ato (a cobertura do LX16)."""
    import caixa_protocolo as CXP
    item = _um(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s",
               (protocolo["itens"][codigo],))
    assert CXP.saldo_do_item(item) == 0, item
    assert (item["usado_por_tabela"], int(item["usado_por_ato_id"] or 0)) == (
        tabela, int(ato_id)), item


# ------------------------------------------------------------- o assento

SLUG = {"NASCIMENTO": "nascimento", "OBITO": "obito",
        "NATIMORTO": "natimorto", "CASAMENTO": "casamento",
        "EMANCIPACAO": "emancipacao", "INTERDICAO": "interdicao",
        "AUSENCIA": "ausencia", "TUTELA": "tutela",
        "UNIAO_ESTAVEL": "uniao-estavel",
        "OPCAO_NACIONALIDADE": "opcao-nacionalidade"}


def _qualificacao(prefixo: str, nome: str, sexo: str = "F", **extra) -> dict:
    """A pessoa com a qualificação inteira, como o balcão a digita."""
    o_a = "a" if sexo == "F" else "o"
    d = {f"{prefixo}_nome": nome, f"{prefixo}_sexo": sexo,
         f"{prefixo}_nacionalidade": f"brasileir{o_a}",
         f"{prefixo}_profissao": f"lavrador{'a' if sexo == 'F' else ''}",
         f"{prefixo}_estado_civil": f"casad{o_a}",
         f"{prefixo}_documento_tipo": "CPF",
         f"{prefixo}_documento_numero": "000.000.010-82",
         f"{prefixo}_naturalidade_cidade": "Cidade Exemplo",
         f"{prefixo}_naturalidade_uf": "MA",
         f"{prefixo}_data_nascimento": "1996-03-10",
         f"{prefixo}_endereco": "Rua Exemplo, 10",
         f"{prefixo}_bairro": "Centro",
         f"{prefixo}_cidade": "Cidade Exemplo",
         f"{prefixo}_uf": "MA"}
    d.update({f"{prefixo}_{k}": v for k, v in extra.items()})
    return d


def _form_nascimento() -> dict:
    """O nascimento com tudo o que o art. 54 da LRP pede, e nada real."""
    f = {"pessoa_nome": "PEDRO EXEMPLO DOS SANTOS", "pessoa_sexo": "M",
         "data_fato": "2026-10-01", "hora_fato": "08:30",
         "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
         "local_fato_endereco": "Avenida Exemplo, 100, Centro",
         "naturalidade_declarada": "Cidade Exemplo/MA",
         "cor_raca": "PARDA", "ibge_local": "1", "ibge_gemeo": "1",
         "dnv": "12345678901",
         "pais_casamento_lugar": "Cidade Exemplo/MA",
         "pais_casamento_cartorio": "Ofício Único de Cidade Exemplo"}
    f |= _qualificacao("filiacao1", "BEATRIZ EXEMPLO DE SOUZA")
    f |= _qualificacao("filiacao2", "MARIO EXEMPLO DOS SANTOS", sexo="M",
                       documento_numero="000.000.011-63",
                       data_nascimento="1990-05-20")
    f |= {"prog1f1_nome": "JOSE EXEMPLO DE SOUZA",
          "prog2f1_nome": "ANA EXEMPLO DE SOUZA",
          "prog1f2_nome": "JOAO EXEMPLO DOS SANTOS",
          "prog2f2_nome": "MARIA EXEMPLO DOS SANTOS"}
    f |= _qualificacao("declarante", "BEATRIZ EXEMPLO DE SOUZA")
    return f


def _form_obito(**trocar) -> dict:
    """O óbito com tudo o que o art. 80 da LRP e o art. 255 do CN-MA pedem."""
    f = {"pessoa_data_nascimento": "1950-01-02",
         "data_fato": "2026-10-18", "hora_fato": "14:00",
         "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
         "local_fato_endereco": "Avenida Exemplo, 100, Centro",
         "naturalidade_declarada": "Cidade Exemplo/MA",
         "cor_raca": "PARDA", "numero_do": "98765432",
         "natureza_obito": "1", "local_obito": "1",
         "causa_morte": "natural, por insuficiência cardíaca",
         "atestante": "BEATRIZ EXEMPLO DE SOUZA",
         "atestante_documento": "CRM-MA 0000",
         "local_sepultamento": "Cemitério Municipal de Cidade Exemplo",
         "testamento": "SIM, lavrado no Tabelionato de Cidade Exemplo",
         "obito_eleitor": "SIM", "obito_possui_bens": "SIM",
         "obito_possui_filho": "SIM", "obito_desconhecido": "NAO",
         "obito_conjuge_nome": "PEDRO EXEMPLO DOS SANTOS",
         "obito_conjuge_situacao": "PRE_MORTO",
         "obito_conjuge_cartorio": "Ofício Único de Cidade Exemplo",
         "obito_filhos": "MARIO EXEMPLO DOS SANTOS, com 50 anos",
         "obito_herdeiros_menores": "NAO"}
    f |= _qualificacao("pessoa", "CARLA EXEMPLO", estado_civil="viúva",
                       profissao="aposentada",
                       documento_numero="000.000.012-44",
                       data_nascimento="1950-01-02", endereco="Rua Exemplo, 20")
    f |= {"filiacao1_nome": "ANA EXEMPLO DE SOUZA",
          "filiacao2_nome": "JOSE EXEMPLO DE SOUZA"}
    f |= _qualificacao("declarante", "MARIO EXEMPLO DOS SANTOS", sexo="M",
                       documento_numero="000.000.011-63")
    f.update(trocar)
    return f


def _lavrar(casa, especie: str, campos: dict, *, folha: str | None = None,
            protocolo: dict | None = None, itens=()):
    """A lavratura pela tela de conferência, com a folha escolhida."""
    rota = f"/rcpn/novo/{SLUG[especie]}"
    dados = {"acao": "lavrar", "especie": especie, **campos,
             **_do_protocolo(protocolo, *itens)}
    if folha:
        dados["folha_seguranca"] = folha
    antes = _um(casa, "SELECT coalesce(max(id), 0) AS n FROM rc_assentos")["n"]
    r = _post(casa, rota, rota, **dados)
    html = r.get_data(as_text=True)
    novo = _um(casa, "SELECT * FROM rc_assentos WHERE id > %s AND "
                     "situacao = 'ATIVO' ORDER BY id DESC LIMIT 1", (antes,))
    assert novo, f"o assento não foi lavrado: {_avisos(html)}"
    ato = _um(casa, "SELECT * FROM rc_atos WHERE assento_id = %s "
                    "AND tipo = 'REGISTRO' ORDER BY id LIMIT 1", (novo["id"],))
    return novo, ato, html


def _livro(casa, ato: dict) -> dict:
    return _um(casa, "SELECT * FROM nu_livros WHERE id = %s", (ato["livro_id"],))


def _termo(casa, assento_id: int) -> str:
    """O termo congelado no assento — o texto do livro, sem as marcas HTML."""
    a = _um(casa, "SELECT teor FROM rc_assentos WHERE id = %s", (assento_id,))
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", a["teor"] or "")).strip()


def _folha_do_livro(casa, assento_id: int) -> str:
    """A página do livro como sai para imprimir: termo, cabeçalho e carimbo."""
    r = casa["cliente"].get(f"/rcpn/{assento_id}/folha")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    html = re.sub(r"<style.*?</style>", " ", html, flags=re.S)
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))


def _sem_defeito_de_texto(texto: str, onde: str) -> None:
    """O que nenhum papel assinado pode ter: «None», marcador de modelo
    sobrando, vírgula sem nada entre elas, frase repetida."""
    assert texto.strip(), f"{onde} saiu vazio"
    assert not re.search(r"\bNone\b|\bnull\b", texto), \
        f"{onde} escreveu «None»: {texto}"
    assert not re.search(r"\{\{|\}\}|\{%|\{[a-z_]+\}", texto), \
        f"{onde} ficou com marcador de modelo: {texto}"
    assert not re.search(r",\s*,|\(\s*\)|_{4,}", texto), \
        f"{onde} tem claro: {texto}"
    frases = [f.strip() for f in re.split(r"(?<=[.;])\s+", texto)
              if len(f.strip()) > 25]
    repetidas = {f for f in frases if frases.count(f) > 1}
    assert not repetidas, f"{onde} repete: {repetidas}"


def _contem(texto: str, onde: str, *pedacos: str) -> None:
    faltam = [p for p in pedacos if p not in texto]
    assert not faltam, f"{onde} não traz {faltam}: {texto}"


def _papel(casa, certidao_id: int) -> zipfile.ZipFile:
    """O papel da certidão (o ODT da casa). Recusa = redirect com o recado."""
    r = casa["cliente"].get(f"/rcpn/certidoes/{certidao_id}/odt?formato=odt")
    if r.status_code != 200:
        volta = casa["cliente"].get(r.headers.get("Location") or "/",
                                    follow_redirects=True)
        pytest.fail(f"o papel não saiu ({r.status_code}): "
                    f"{_avisos(volta.get_data(as_text=True))}")
    return zipfile.ZipFile(io.BytesIO(r.get_data()))


def _odt(casa, certidao_id: int) -> str:
    """O texto do papel da certidão, sem as marcas do XML."""
    with _papel(casa, certidao_id) as z:
        xml = z.read("content.xml").decode("utf-8")
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", xml))


def _qr_do_papel(casa, certidao_id: int) -> bytes:
    """A imagem do QR do (primeiro) selo no papel da certidão."""
    import rc_certidao_odt as RCODT
    with _papel(casa, certidao_id) as z:
        return z.read(RCODT._QR_SELO1)


def _emitir(casa, assento_id: int, *, protocolo: dict | None = None,
            itens=(), **dados):
    tela = f"/rcpn/{assento_id}"
    dados.setdefault("tipo_certidao", "resumo")
    dados.setdefault("requerente", "BEATRIZ EXEMPLO DE SOUZA")
    dados.setdefault("finalidade", "documentação")
    dados.update(_do_protocolo(protocolo, *itens))
    antes = _um(casa, "SELECT coalesce(max(id), 0) AS n FROM rc_certidoes")["n"]
    r = _post(casa, tela, f"/rcpn/{assento_id}/certidao", **dados)
    html = r.get_data(as_text=True)
    cert = _um(casa, "SELECT * FROM rc_certidoes WHERE id > %s AND assento_id = %s "
                     "AND cancelada_em IS NULL ORDER BY id DESC LIMIT 1",
               (antes, assento_id))
    assert cert, f"a certidão não saiu: {_avisos(html)}"
    return cert, html


def _confere_o_papel_da_certidao(casa, certidao_id: int, *, selo: str) -> str:
    """O que todo papel de certidão do RCPN tem de dizer (CNN arts. 472 e 473,
    modelos de certidão; CN-MA arts. 131 e 132, o selo «no corpo do ato» e a
    consulta pelo código ou pelo QR): a serventia (CNS e município), o oficial
    que assina e a função, o selo com a consulta, o QR DESTE selo e a fé."""
    import rc_certidao_odt as RCODT
    papel = _odt(casa, certidao_id)
    _contem(papel, "o papel da certidão", "CNS nº 000000", "Cidade Exemplo",
            OFICIAL, FUNCAO, f"Selo: {selo}",
            f"https://selo.tjma.jus.br/#/resumo/{selo}",
            "O conteúdo da certidão é verdadeiro. Dou fé.")
    qr = RCODT._png_do_qr(selo)
    if qr is None:
        pytest.skip("sem `segno` não se gera o QR do selo")
    assert _qr_do_papel(casa, certidao_id) == qr, "o QR do papel não é o do selo"
    return papel


# ============================================================ nascimento


def test_nascimento_do_balcao_a_certidao_com_termo_e_certidao_que_batem(balcao):
    """LRP art. 54 (o assento), art. 30 (registro e 1ª certidão gratuitos:
    sem protocolo pago, o selo sai ISENTO pelo item da lei 14.a), art. 19 e
    CNN (a certidão no modelo nacional, com a matrícula); CN-MA arts. 227 e ss.
    A 1ª via sai com o selo e a folha do registro (FOLHA_DA_1A_VIA_20261009)."""
    assento, ato, html = _lavrar(balcao, "NASCIMENTO", _form_nascimento(),
                                 folha=FOLHAS[0])

    # O SELO: isento pelo item da lei, com a folha que foi ao TJMA.
    assert (ato["selo"] or "").strip(), _avisos(html)
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith("/selo/civil/nascimento")
    assert pedido["codigoTipoAtoRegistro"] == "14.a"
    assert pedido["dadosSelo"]["isentoGratuito"] == "ISENTO"
    assert pedido["papelMoeda"]["codigo"] == FOLHAS[0]
    # Sem dinheiro: a gratuidade é da lei, e não pede comprovante (LX16).
    assert _um(balcao, "SELECT count(*) AS n FROM cx_lancamentos")["n"] == 0

    # LIVRO, FOLHA E NÚMERO — o Livro A, aberto pela série da espécie.
    livro = _livro(balcao, ato)
    assert (livro["serie"], int(livro["numero"])) == ("RC_A", 1)
    assert (int(ato["folha"]), int(ato["numero_ordem"])) == (1, 1)
    assert pedido["dadosSelo"]["livro"] == "1"
    assert pedido["dadosSelo"]["folha"] == "1"
    assert pedido["dadosSelo"]["termo"] == "1"
    # A matrícula de 32 dígitos (CNN): CNS, acervo 01, RCPN 55, ano do
    # registro, livro A (tipo 1), livro, folha e termo.
    ano = str(assento["data_ato"])[:4]
    assert re.fullmatch(rf"0000000155{ano}1000010010000001\d\d",
                        assento["matricula"]), assento["matricula"]

    # O TERMO — art. 54, itens 1º a 11, e o encerramento com quem assina.
    termo = _termo(balcao, assento["id"])
    _sem_defeito_de_texto(termo, "o termo de nascimento")
    _contem(termo, "o termo de nascimento",
            "neste Município de Cidade Exemplo",          # lugar do ato
            "compareceu BEATRIZ EXEMPLO DE SOUZA",        # declarante
            "apresentou a DNV n.º 12345678901",           # item 10
            "um (01) de outubro de dois mil e vinte e seis",  # item 1º: dia
            "às 08:30",                                   # item 1º: hora
            "em Hospital Municipal de Cidade Exemplo",    # item 1º: lugar
            "do sexo Masculino",                          # item 2º
            "cor Parda",
            '"PEDRO EXEMPLO DOS SANTOS"',                 # item 4º
            "sendo filho de BEATRIZ EXEMPLO DE SOUZA",    # item 7º
            "e de MARIO EXEMPLO DOS SANTOS",
            "lavradora", "natural de Cidade Exemplo/MA",  # item 7º: profissão
            "casados entre si em Cidade Exemplo/MA",      # item 7º: casamento
            "30 anos de idade",                           # item 7º: idade
            "JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA",   # item 8º
            "JOAO EXEMPLO DOS SANTOS e MARIA EXEMPLO DOS SANTOS",
            "A naturalidade declarada é de Cidade Exemplo/MA",  # item 11
            "Lido e achado conforme, o(a) declarante assina.",
            f"Eu, {OFICIAL}, {FUNCAO}, dou fé e assino.",
            f"Matrícula {assento['matricula']}.")

    # A FOLHA DO LIVRO leva o termo, o cabeçalho com livro/folha/termo e o
    # carimbo do selo — é o «selo no ato» do papel que o declarante assina.
    folha = _folha_do_livro(balcao, assento["id"])
    _contem(folha, "a folha do livro", "REGISTRO DE NASCIMENTO",
            "Termo: 1", "Livro: 1", "Folha: 1", ato["selo"],
            "PEDRO EXEMPLO DOS SANTOS")

    # A 1ª VIA: gratuita, com o selo do registro e a folha dele.
    antes = len(_pedidos_de_selo(balcao))
    cert, html_c = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[0])
    assert cert["selo"] == ato["selo"], _avisos(html_c)
    assert len(_pedidos_de_selo(balcao)) == antes, "a 1ª via não compra selo"
    assert cert["modalidade"] == "RESUMO"

    # A CERTIDÃO FIEL AO TERMO — cada elemento do breve relato é o do termo.
    teor = cert["teor"]
    _sem_defeito_de_texto(teor.replace("\n", " "), "a certidão de nascimento")
    _contem(teor, "a certidão de nascimento", "CERTIDÃO DE NASCIMENTO",
            "PEDRO EXEMPLO DOS SANTOS", assento["matricula"],
            "PRIMEIRO DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "08:30",
            "MASCULINO", "Hospital Municipal de Cidade Exemplo",
            "MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA",
            "JOAO EXEMPLO DOS SANTOS e MARIA EXEMPLO DOS SANTOS",
            "JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA",
            "12345678901", "LIVRO\n1", "FOLHA\n1", "TERMO\n1",
            "NADA CONSTA.", "O referido é verdade e dou fé.")
    # A DATA DO REGISTRO é a do assento, lavrado hoje — por isso sai do
    # assento, e não escrita à mão: o teste não fica vermelho amanhã.
    import rc_certidao as RCE
    _contem(teor, "a certidão de nascimento", "DATA DO REGISTRO POR EXTENSO\n"
            + RCE.data_por_extenso(assento["data_ato"]))
    # A naturalidade do termo, e não «ND» (art. 54, item 11).
    assert re.search(r"NATURALIDADE\nCidade Exemplo/MA", teor), teor

    # O PAPEL — o molde do CNJ com a serventia, o oficial e o selo com QR.
    papel = _confere_o_papel_da_certidao(balcao, cert["id"],
                                         selo=ato["selo"])
    _contem(papel, "o papel da certidão de nascimento",
            "CERTIDÃO DE NASCIMENTO", "PEDRO EXEMPLO DOS SANTOS",
            "PRIMEIRO DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "08:30",
            "MASCULINO", "BEATRIZ EXEMPLO DE SOUZA", "MARIO EXEMPLO DOS SANTOS",
            "12345678901")


def test_o_papel_da_certidao_de_nascimento_diz_o_municipio_e_nao_a_rua(balcao):
    """LRP art. 54, item 1º (o lugar do nascimento); CNN, modelo da certidão
    de nascimento. Consertado no LD01: a célula MUNICÍPIO DE NASCIMENTO lia o
    «Endereço do local» (rua, número e bairro), e o município de fato não
    saía. A tela pergunta o município do local, e traz o da serventia escrito
    — que é o que vale quando o balcão não diz outro."""
    assento, _ato, _ = _lavrar(balcao, "NASCIMENTO", _form_nascimento(),
                               folha=FOLHAS[0])
    assert assento["local_fato_municipio"] == "Cidade Exemplo/MA"
    cert, _ = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[0])
    papel = _odt(balcao, cert["id"])
    trecho = papel[papel.index("LOCAL DE NASCIMENTO"):papel.index("NOME DO(A) GENITOR")]
    # A linha de valores: o local (com ou sem o endereço), o MUNICÍPIO, a UF
    # e o sexo — e a rua não fica no lugar do município.
    assert re.search(r"(?:Exemplo|Centro)\s+Cidade Exemplo\s+MA\s+MASCULINO",
                     trecho), trecho
    assert "Avenida Exemplo" not in trecho


def test_o_municipio_que_o_balcao_escreve_e_o_que_o_papel_imprime(balcao):
    """O padrão da tela é o município da serventia, e é só padrão: nascido em
    outro município e registrado aqui pela residência dos pais (LRP art. 50),
    o que o escrevente escreve é o que vai ao papel — e não o da casa."""
    f = _form_nascimento() | {"local_fato_municipio": "Outra Cidade/PI"}
    assento, _ato, _ = _lavrar(balcao, "NASCIMENTO", f, folha=FOLHAS[0])
    assert assento["local_fato_municipio"] == "Outra Cidade/PI"
    cert, _ = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[0])
    papel = _odt(balcao, cert["id"])
    trecho = papel[papel.index("LOCAL DE NASCIMENTO"):papel.index("NOME DO(A) GENITOR")]
    assert re.search(r"Exemplo\s+Outra Cidade\s+PI\s+MASCULINO", trecho), trecho
    # A tela traz o campo, com o município da serventia já escrito.
    html = balcao["cliente"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert re.search(r'name="local_fato_municipio"\s+value="Cidade Exemplo/MA"',
                     html), "a tela não traz o município do local"


# ================================================================= óbito


def test_obito_do_balcao_a_certidao_com_termo_e_certidao_que_batem(balcao):
    """LRP art. 80 e CN-MA art. 255 (os doze itens do assento, e o § 1º: o que
    não se perguntou se declara); LRP art. 30 (registro e 1ª certidão
    gratuitos, item 14.c)."""
    assento, ato, html = _lavrar(balcao, "OBITO", _form_obito(),
                                 folha=FOLHAS[1])
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith("/selo/civil/obito"), _avisos(html)
    assert pedido["codigoTipoAtoRegistro"] == "14.c"
    assert pedido["dadosSelo"]["isentoGratuito"] == "ISENTO"
    assert pedido["papelMoeda"]["codigo"] == FOLHAS[1]
    assert _um(balcao, "SELECT count(*) AS n FROM cx_lancamentos")["n"] == 0
    livro = _livro(balcao, ato)
    assert (livro["serie"], int(ato["folha"]), int(ato["numero_ordem"])) == (
        "RC_C", 1, 1)

    termo = _termo(balcao, assento["id"])
    _sem_defeito_de_texto(termo, "o termo de óbito")
    _contem(termo, "o termo de óbito",
            "compareceu MARIO EXEMPLO DOS SANTOS",            # declarante
            "dezoito (18) de outubro de dois mil e vinte e seis",  # I
            "às 14:00", "em Hospital Municipal de Cidade Exemplo",  # I, II
            "faleceu CARLA EXEMPLO",                          # III
            "aposentada", "natural de Cidade Exemplo/MA",
            "residente e domiciliada em Rua Exemplo, 20",
            "ANA EXEMPLO DE SOUZA e JOSE EXEMPLO DE SOUZA",   # VI
            "cônjuge pré-morto PEDRO EXEMPLO DOS SANTOS",     # IV
            "Ofício Único de Cidade Exemplo",
            "insuficiência cardíaca", "BEATRIZ EXEMPLO DE SOUZA",  # IX
            "CRM-MA 0000",
            "Cemitério Municipal de Cidade Exemplo",          # X
            "eleitor",                                        # V
            "Tabelionato de Cidade Exemplo",                  # VII
            "MARIO EXEMPLO DOS SANTOS, com 50 anos",          # VIII
            "Deixou bens",                                    # XI
            "Não deixou herdeiros menores",
            "000.000.012-44",                                 # XII: CPF
            "Declaração de Óbito n.º 98765432",
            "Lido e achado conforme",
            f"Eu, {OFICIAL}, {FUNCAO}, escrevi e assino.")
    # TUDO FOI PERGUNTADO E RESPONDIDO: o termo não declara ignorância
    # nenhuma, e muito menos que a falecida, com nome e CPF, não foi
    # identificada (CN-MA art. 255, § 1º; art. 257 é outro caso).
    assert "ignorava" not in termo
    assert "não identificad" not in termo

    folha = _folha_do_livro(balcao, assento["id"])
    _contem(folha, "a folha do livro", "Termo: 1", "Livro: 1", "Folha: 1",
            ato["selo"], "CARLA EXEMPLO")

    cert, html_c = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[1])
    assert cert["selo"] == ato["selo"], _avisos(html_c)
    teor = cert["teor"]
    _sem_defeito_de_texto(teor.replace("\n", " "), "a certidão de óbito")
    _contem(teor, "a certidão de óbito", "CERTIDÃO DE ÓBITO", "CARLA EXEMPLO",
            assento["matricula"],
            "DEZOITO DE OUTUBRO DE DOIS MIL E VINTE E SEIS", "14:00",
            "FEMININO", "DOIS DE JANEIRO DE MIL NOVECENTOS E CINQUENTA",
            "viúva", "aposentada", "Cidade Exemplo/MA",
            "Hospital Municipal de Cidade Exemplo", "98765432",
            "insuficiência cardíaca", "BEATRIZ EXEMPLO DE SOUZA — CRM-MA 0000",
            "Cemitério Municipal de Cidade Exemplo",
            "Tabelionato de Cidade Exemplo",
            "JOSE EXEMPLO DE SOUZA e ANA EXEMPLO DE SOUZA",
            "LIVRO\n1", "FOLHA\n1", "TERMO\n1", "O referido é verdade e dou fé.")

    papel = _confere_o_papel_da_certidao(balcao, cert["id"],
                                         selo=ato["selo"])
    _contem(papel, "o papel da certidão de óbito", "CERTIDÃO DE ÓBITO",
            "CARLA EXEMPLO", "insuficiência cardíaca",
            "Cemitério Municipal de Cidade Exemplo", "MARIO EXEMPLO DOS SANTOS")


def test_o_obito_sem_a_pergunta_do_desconhecido_nao_diz_que_a_pessoa_nao_foi_identificada(balcao):
    """CN-MA art. 255, § 1º: o que não se perguntou dos itens DO ARTIGO se
    declara ignorado. «Pessoa não identificada» não é item dele (é o assento
    de desconhecido, LRP art. 81; CN-MA art. 257): a falecida tem nome e CPF.
    Consertado no LT01 (`rc_modelos_do_livro.frase_dos_ignorados`)."""
    campos = _form_obito()
    for marca in ("obito_desconhecido", "obito_eleitor"):
        campos.pop(marca)
    assento, _ato, _ = _lavrar(balcao, "OBITO", campos, folha=FOLHAS[1])
    termo = _termo(balcao, assento["id"])
    assert "não identificad" not in termo, termo
    # E o que de fato ficou sem resposta continua declarado (§ 1º).
    _contem(termo, "o termo de óbito", "O oficial indagou a respeito de todos "
            "os itens do art. 255, e o declarante ignorava: era eleitor, na "
            "forma do § 1º do referido artigo.")


def test_o_termo_de_obito_de_uma_falecida_concorda_no_feminino(balcao):
    """LRP art. 80, item 3º (o sexo); CN-MA art. 255, III. Consertado no LD01:
    as peças «Filho de», «Sepultado em» e «Era eleitor» eram uma só, no
    masculino. E o termo diz agora o sexo, a idade e a cor (art. 80, 3º) e a
    natureza da morte (8º), que a certidão já imprimia e o termo calava."""
    assento, _ato, _ = _lavrar(balcao, "OBITO", _form_obito(), folha=FOLHAS[1])
    termo = _termo(balcao, assento["id"])
    _contem(termo, "o termo de óbito de uma falecida",
            "Filha de", "Sepultada em", "Era eleitora",
            "do sexo feminino", "com 76 anos de idade", "de cor parda",
            "A morte foi natural")
    for masculino in ("Filho de", "Sepultado em", "Era eleitor."):
        assert masculino not in termo, masculino


def test_o_papel_da_certidao_de_obito_traz_conjuge_bens_e_filhos_do_termo(balcao):
    """LRP art. 80, 4º, 7º e 10º; CN-MA art. 255, IV, VIII e XI — o que o termo
    declara, o papel diz. Consertado no LT01: `rc_certidao_quadro._quadro_obito`
    só lia o blob do acervo, e o óbito lavrado aqui saía com as três células
    em branco."""
    assento, _ato, _ = _lavrar(balcao, "OBITO", _form_obito(), folha=FOLHAS[1])
    cert, _ = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[1])
    papel = _odt(balcao, cert["id"])
    conjuge = papel[papel.index("NOME DO ÚLTIMO CÔNJUGE"):papel.index("IDADE")]
    assert "PEDRO EXEMPLO DOS SANTOS" in conjuge, conjuge
    fim = papel[papel.index("EXISTÊNCIA DE FILHOS"):papel.index("ANOTAÇÕES/AVERBAÇÕES")]
    assert "MARIO EXEMPLO DOS SANTOS, com 50 anos" in fim, fim
    assert re.search(r"\bSIM\b", fim), fim


@pytest.mark.parametrize("gravado, no_papel, no_termo", [
    ("SIM", "SIM", "Deixou"), ("S", "SIM", "Deixou"), ("1", "SIM", "Deixou"),
    ("NAO", "NÃO", "Não deixou"), ("não", "NÃO", "Não deixou"),
    ("N", "NÃO", "Não deixou"),
    ("", "", ""), (None, "", ""), ("TALVEZ", "", "")])
def test_o_papel_e_o_termo_leem_a_marca_de_bens_e_filhos_do_mesmo_jeito(
        gravado, no_papel, no_termo):
    """O conserto do papel do óbito (LT01) não pode dizer «SIM» onde o termo
    calou, nem calar onde o termo disse «Não deixou» (LRP art. 80, 7º e 10º;
    CN-MA art. 255, VIII e XI). A tela grava SIM/NAO, mas a carga antiga trouxe
    «S», «1», «não» — por isso este vai sem as telas: é a régua das duas
    pontas (`rc_marcas_do_obito.normalizar`), e não o caminho do balcão.
    «Não perguntado» não vira palavra em nenhuma das duas (art. 255, § 1º)."""
    import rc_certidao_quadro as RCQ
    import rc_marcas_do_obito as MO
    import rc_modelos_do_livro as ML
    assento = {"obito_possui_bens": gravado, "obito_possui_filho": gravado}
    quadro = RCQ._quadro_obito(assento, {}, {}, "", {})
    assert (quadro["bens"], quadro["filhos"]) == (no_papel, no_papel)
    # O termo, pela mesma porta da lavratura (`rc_termo`: marcas do assento).
    marcas = {m["chave"]: m["estado"] for m in MO.do_assento(assento)}
    termo = ML.valores_do_obito(assento, [], marcas=marcas)
    esperado = (f"{no_termo} bens.", f"{no_termo} filhos.") if no_termo \
        else ("", "")
    assert (termo["frase_deixou_bens"], termo["frase_filhos"]) == esperado


def test_o_papel_da_certidao_de_obito_traz_o_municipio_do_falecimento(balcao):
    """LRP art. 80, 2º («com indicação precisa»); CN-MA art. 255, II.
    Consertado no LD01: o quadro do óbito só lia o município do blob do
    acervo, e a tela não perguntava o município do local — o papel do óbito
    lavrado aqui saía com a célula MUNICÍPIO DE FALECIMENTO em branco."""
    assento, _ato, _ = _lavrar(balcao, "OBITO", _form_obito(), folha=FOLHAS[1])
    cert, _ = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[1])
    papel = _odt(balcao, cert["id"])
    bloco = papel[papel.index("LOCAL DE FALECIMENTO"):papel.index("SEXO")]
    # A linha de valores: o local, o MUNICÍPIO e a UF, nesta ordem.
    assert re.search(r"Hospital Municipal de Cidade Exemplo\s+Cidade Exemplo"
                     r"\s+MA\b", bloco), bloco


# ============================================================= natimorto


def _form_natimorto() -> dict:
    return {"pessoa_nome": "NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA",
            "pessoa_sexo": "M", "data_fato": "2026-10-15", "hora_fato": "10:00",
            "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
            "naturalidade_declarada": "Cidade Exemplo/MA",
            "numero_do": "11112222",
            "filiacao1_nome": "BEATRIZ EXEMPLO DE SOUZA",
            "filiacao2_nome": "MARIO EXEMPLO DOS SANTOS",
            **_qualificacao("declarante", "MARIO EXEMPLO DOS SANTOS", sexo="M")}


def test_natimorto_do_balcao_ao_livro_c_auxiliar_e_ao_breve_relato(balcao):
    """LRP art. 53, § 1º (o natimorto no Livro C-Auxiliar, «com os elementos
    que couberem»), art. 30 (isento, item 14.d)."""
    assento, ato, html = _lavrar(balcao, "NATIMORTO", _form_natimorto(),
                                 folha=FOLHAS[2])
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith("/selo/civil/natimorto"), _avisos(html)
    assert pedido["codigoTipoAtoRegistro"] == "14.d"
    assert pedido["dadosSelo"]["isentoGratuito"] == "ISENTO"
    assert _um(balcao, "SELECT count(*) AS n FROM cx_lancamentos")["n"] == 0
    assert _livro(balcao, ato)["serie"] == "RC_C_AUXILIAR"
    termo = _termo(balcao, assento["id"])
    _sem_defeito_de_texto(termo, "o termo de natimorto")
    _contem(termo, "o termo de natimorto", "compareceu MARIO EXEMPLO DOS SANTOS",
            "quinze (15) de outubro de dois mil e vinte e seis",
            "Hospital Municipal de Cidade Exemplo", "BEATRIZ EXEMPLO DE SOUZA",
            "Lido e achado conforme", f"Eu, {OFICIAL}, {FUNCAO}")
    cert, html_c = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[2])
    assert cert["selo"] == ato["selo"], _avisos(html_c)
    _contem(cert["teor"], "o breve relato do natimorto",
            "NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA", "11112222",
            "LIVRO\n1", "TERMO\n1", "O referido é verdade e dou fé.")


def test_o_termo_de_natimorto_declara_que_a_crianca_nasceu_morta(balcao):
    """LRP art. 53, § 1º, e art. 54, item 5º («a declaração de que nasceu
    morta»). Consertado no LD01: o natimorto sai pelo modelo do nascimento, e
    o modelo afirmava «nasceu uma criança … que recebeu o nome de» sem dizer
    que ela nasceu morta — o próprio fato do Livro C-Auxiliar. O documento que
    o balcão apresenta é a Declaração de Óbito, e o termo diz qual; o
    natimorto não tem CPF nem é «primeiro registro» (CNN art. 479-A)."""
    assento, _ato, _ = _lavrar(balcao, "NATIMORTO", _form_natimorto(),
                               folha=FOLHAS[2])
    termo = _termo(balcao, assento["id"])
    assert re.search(r"nasc\w* mort", termo), termo
    _contem(termo, "o termo de natimorto", "nasceu morta uma criança",
            "apresentou a Declaração de Óbito n.º 11112222")
    assert "DNV" not in termo and "primeiro registro" not in termo


def test_a_certidao_de_natimorto_sai_em_papel(balcao):
    """LRP art. 30 (a 1ª certidão, gratuita) e art. 19. Consertado no LD01: não
    havia papel para a certidão de natimorto — a guarda do molde só servia
    nascimento, casamento e óbito, e a 1ª via ficava sem o que imprimir. O
    molde é próprio (`tools/moldes_do_civil.py`): diz natimorto, e não
    nascimento com vida, nem traz caixa de DNV."""
    assento, ato, _ = _lavrar(balcao, "NATIMORTO", _form_natimorto(),
                              folha=FOLHAS[2])
    cert, _ = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[2])
    papel = _confere_o_papel_da_certidao(balcao, cert["id"], selo=ato["selo"])
    _contem(papel, "o papel da certidão de natimorto", "CERTIDÃO DE NATIMORTO",
            "NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA", "11112222",
            "Hospital Municipal de Cidade Exemplo", "BEATRIZ EXEMPLO DE SOUZA")
    assert "CERTIDÃO DE NASCIMENTO" not in papel
    assert "NASCIDO VIVO" not in papel


# ================================================== casamento e habilitação


def _form_casamento() -> dict:
    """O casamento com o que o art. 70 da LRP pede."""
    f = {"data_fato": "2026-10-17", "hora_fato": "10:00",
         "local_fato_nome": "Sede do Ofício Único de Cidade Exemplo",
         "regime_bens": "COMUNHAO_PARCIAL",
         "habilitacao_serventia": "Ofício de Outra Cidade/MA",
         "habilitacao_selo": "HABCAS000000ABCDEFGHIJ123456",
         "proclamas_data": "2026-09-01",
         "documentos_apresentados": "certidões de nascimento dos nubentes",
         "juiz_de_paz": "PEDRO EXEMPLO DOS SANTOS"}
    f |= _qualificacao("nubente1", "MARIO EXEMPLO DOS SANTOS", sexo="M",
                       estado_civil="solteiro",
                       nome_pos="MARIO EXEMPLO DOS SANTOS")
    f |= _qualificacao("nubente2", "BEATRIZ EXEMPLO DE SOUZA",
                       estado_civil="solteira",
                       documento_numero="000.000.011-63",
                       nome_pos="BEATRIZ EXEMPLO DE SOUZA DOS SANTOS")
    f |= {"filiacao1n1_nome": "ANA EXEMPLO DOS SANTOS",
          "filiacao2n1_nome": "JOAO EXEMPLO DOS SANTOS",
          "filiacao1n2_nome": "MARIA EXEMPLO DE SOUZA",
          "filiacao2n2_nome": "JOSE EXEMPLO DE SOUZA"}
    f |= _qualificacao("testemunha", "CARLA EXEMPLO",
                       documento_numero="000.000.013-25")
    return f


def _habilitacao_ate_o_edital(casa) -> tuple[int, str]:
    """A habilitação desta casa pelas telas, até o edital publicado: abrir,
    receber os documentos, publicar. Devolve o id e a ficha."""
    _post(casa, "/rcpn/habilitacoes/nova", "/rcpn/habilitacoes/nova",
          nubente1_nome="MARIO EXEMPLO DOS SANTOS",
          nubente1_estado_civil="SOLTEIRO", nubente1_sexo="M",
          nubente1_mae="ANA EXEMPLO DOS SANTOS",
          nubente1_pai="JOAO EXEMPLO DOS SANTOS",
          nubente1_endereco="Rua Exemplo, 10, Centro, Cidade Exemplo/MA",
          nubente2_nome="BEATRIZ EXEMPLO DE SOUZA",
          nubente2_estado_civil="SOLTEIRO", nubente2_sexo="F",
          nubente2_mae="MARIA EXEMPLO DE SOUZA",
          nubente2_pai="JOSE EXEMPLO DE SOUZA",
          nubente2_endereco="Rua Exemplo, 50, Centro, Cidade Exemplo/MA",
          tipo="CIVIL", regime="COMUNHAO_PARCIAL")
    hid = int(_um(casa, "SELECT max(id) AS n FROM hc_habilitacoes")["n"])
    ficha = f"/rcpn/habilitacoes/{hid}"
    for d in _ler(casa, "SELECT id FROM hc_documentos WHERE habilitacao_id = %s "
                        "ORDER BY id", (hid,)):
        _post(casa, ficha, ficha, acao="documento", documento_id=str(d["id"]),
              apresentado="1")
    # O TEOR QUE A FICHA OFERECE é o do modelo da casa, com o estado civil, a
    # filiação e a cidade do domicílio dos noivos (CNN art. 122 — LD01).
    html = casa["cliente"].get(ficha).get_data(as_text=True)
    sugerido = re.search(r'<textarea[^>]*name="teor"[^>]*>(.*?)</textarea>',
                         html, re.S)
    assert sugerido, "a ficha não oferece o teor do edital"
    import html as HTML
    teor = HTML.unescape(sugerido.group(1)).strip()
    _contem(teor, "o teor sugerido do edital", "MARIO EXEMPLO DOS SANTOS",
            "de estado civil SOLTEIRO e SOLTEIRA, respectivamente",
            "filhos, respectivamente, de ANA EXEMPLO DOS SANTOS e JOAO EXEMPLO "
            "DOS SANTOS e de MARIA EXEMPLO DE SOUZA e JOSE EXEMPLO DE SOUZA",
            "ambos domiciliados em Cidade Exemplo/MA, nesta circunscrição")
    assert "Rua Exemplo" not in teor, "o edital publica só a cidade (CNN art. 122)"
    _post(casa, ficha, ficha, acao="edital", teor=teor)
    return hid, ficha


def test_casamento_pela_habilitacao_desta_casa_vai_do_protocolo_a_certidao(balcao):
    """LRP arts. 67 e 33 (o Livro D); CC arts. 1.531 e 1.532; CN-MA arts. 265 a
    267 (o edital «será registrado no Livro D», com a época da publicação e os
    documentos). Consertado no LD01: a habilitação desta casa não chegava ao
    HABILITADO pelas telas — o selo dela exige livro, folha e termo do registro
    do edital no Livro D (HOTFIX-2026-10-07-05), e nenhum código gravava o
    vínculo. O edital agora se registra ao ser publicado, o selo da
    habilitação (14.1.1, pago pelo protocolo) leva o lugar desse registro, e o
    registro recebe o MESMO selo — um selo só."""
    p = _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ",
                         codigos=("14.1.1",))
    c = balcao["cliente"]
    hid, ficha = _habilitacao_ate_o_edital(balcao)
    hab = _um(balcao, "SELECT * FROM hc_habilitacoes WHERE id = %s", (hid,))
    registro = _um(balcao, "SELECT * FROM rc_assentos WHERE id = %s",
                   (hab["proclamas_assento_id"],))
    assert registro and (registro["especie"], registro["serie"]) == (
        "PROCLAMAS", "RC_D"), registro
    ato_d = _um(balcao, "SELECT * FROM rc_atos WHERE assento_id = %s AND "
                        "tipo = 'REGISTRO' ORDER BY id LIMIT 1", (registro["id"],))
    assert ato_d["folha"] and ato_d["numero_ordem"], ato_d
    _contem(registro["teor"], "o registro do edital no Livro D",
            f"habilitação n.º {hab['numero']}/{hab['ano']}",
            "Os nubentes apresentaram os seguintes documentos",
            "Faço saber que pretendem casar-se MARIO EXEMPLO DOS SANTOS")
    antes = len(_pedidos_de_selo(balcao))

    r = _post(balcao, ficha, ficha, acao="habilitar")
    h = _um(balcao, "SELECT situacao, selo FROM hc_habilitacoes WHERE id = %s",
            (hid,))
    assert h["situacao"] == "HABILITADO" and h["selo"], _avisos(
        r.get_data(as_text=True))
    certidao_hab = c.get(f"{ficha}/certidao")
    assert certidao_hab.status_code == 200
    _item_gasto_pelo_ato(balcao, p, "14.1.1", tabela="hc_habilitacoes",
                         ato_id=hid)
    # UM SELO SÓ, pedido pelo caminho da habilitação, com o lugar do Livro D.
    pedidos = _pedidos_de_selo(balcao)[antes:]
    assert len(pedidos) == 1, pedidos
    assert pedidos[0]["caminho"].endswith("/selo/civil/casamento/habilitacao")
    assert (pedidos[0]["dadosSelo"]["folha"], pedidos[0]["dadosSelo"]["termo"]) == (
        str(ato_d["rotulo"] or ato_d["folha"]), str(ato_d["numero_ordem"]))
    ato_d = _um(balcao, "SELECT selo FROM rc_atos WHERE id = %s", (ato_d["id"],))
    assert ato_d["selo"] == h["selo"], "o registro do Livro D ficou sem o selo"


def test_o_registro_do_edital_no_livro_d_nao_compra_selo_a_parte(balcao):
    """O CAMINHO DE ERRO DO LD01 — nada de selo vendido duas vezes (CN-MA art.
    130, § 2º, ao avesso: o ato tem o seu selo, e um só). Entre o edital e a
    habilitação o registro do Livro D ainda está sem selo, e a ficha dele
    oferece «Selar». Selar ali compraria o 14.1.2 para o mesmo edital que o
    14.1.1 da habilitação já cobre: a casa recusa, e não pede selo nenhum."""
    _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ", codigos=("14.1.1",))
    hid, _ficha = _habilitacao_ate_o_edital(balcao)
    aid = _um(balcao, "SELECT proclamas_assento_id AS a FROM hc_habilitacoes "
                      "WHERE id = %s", (hid,))["a"]
    ato = _um(balcao, "SELECT id FROM rc_atos WHERE assento_id = %s AND "
                      "tipo = 'REGISTRO' ORDER BY id LIMIT 1", (aid,))
    antes = len(_pedidos_de_selo(balcao))
    r = _post(balcao, f"/rcpn/{aid}", f"/rcpn/ato/{ato['id']}/selar")
    assert len(_pedidos_de_selo(balcao)) == antes, "comprou selo para o edital"
    assert not (_um(balcao, "SELECT selo FROM rc_atos WHERE id = %s",
                    (ato["id"],))["selo"] or "").strip()
    assert "o selo é o da habilitação" in _avisos(r.get_data(as_text=True))
    # E o edital se registra UMA vez: habilitar não lavra um segundo registro.
    _post(balcao, f"/rcpn/habilitacoes/{hid}", f"/rcpn/habilitacoes/{hid}",
          acao="habilitar")
    assert _um(balcao, "SELECT count(*) AS n FROM rc_assentos WHERE "
                       "especie = 'PROCLAMAS'")["n"] == 1


def test_o_edital_publicado_antes_do_ld01_se_registra_ao_habilitar(balcao):
    """A habilitação cujo edital foi publicado antes do LD01 não tem o registro
    no Livro D (nenhum código o fazia), e sem ele o selo não sai. «Habilitar»
    o lavra antes de pedir o selo — uma vez só, com a data do edital como data
    do fato — e a habilitação chega ao HABILITADO (CN-MA arts. 265 a 267)."""
    import habilitacao as HAB
    _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ", codigos=("14.1.1",))
    _post(balcao, "/rcpn/habilitacoes/nova", "/rcpn/habilitacoes/nova",
          nubente1_nome="MARIO EXEMPLO DOS SANTOS", nubente1_estado_civil="SOLTEIRO",
          nubente2_nome="BEATRIZ EXEMPLO DE SOUZA", nubente2_estado_civil="SOLTEIRO",
          tipo="CIVIL", regime="COMUNHAO_PARCIAL")
    hid = int(_um(balcao, "SELECT max(id) AS n FROM hc_habilitacoes")["n"])
    # O EDITAL DE ANTES: publicado pelo domínio, sem o registro no Livro D.
    with balcao["db"].transaction() as con:
        for d in HAB.o_que_falta(con, hid):
            HAB.marcar_documento(con, d["id"], apresentado=True,
                                 agora="2026-10-01T10:00:00", usuario=OFICIAL)
        HAB.publicar_edital(con, hid, teor=(
            "Faço saber que pretendem casar-se MARIO EXEMPLO DOS SANTOS e "
            "BEATRIZ EXEMPLO DE SOUZA. Quem souber de impedimento o diga."),
            agora="2026-10-01T10:00:00", hoje="2026-10-01", usuario=OFICIAL)
    assert _um(balcao, "SELECT proclamas_assento_id AS a FROM hc_habilitacoes "
                       "WHERE id = %s", (hid,))["a"] is None
    ficha = f"/rcpn/habilitacoes/{hid}"
    r = _post(balcao, ficha, ficha, acao="habilitar")
    h = _um(balcao, "SELECT * FROM hc_habilitacoes WHERE id = %s", (hid,))
    assert h["situacao"] == "HABILITADO" and h["selo"], _avisos(
        r.get_data(as_text=True))
    registro = _um(balcao, "SELECT * FROM rc_assentos WHERE id = %s",
                   (h["proclamas_assento_id"],))
    assert (registro["especie"], str(registro["data_fato"])[:10]) == (
        "PROCLAMAS", "2026-10-01")


def test_o_casamento_lavrado_pela_habilitacao_desta_casa_traz_os_proclamas(balcao):
    """LRP art. 70, itens 4º e 5º; CN-MA art. 284, IV e V. Consertado no LD01:
    com a habilitação DESTA casa o termo não escrevia a data dos proclamas (só
    a de fora a tinha, digitada), e a ligação com a habilitação só entrava no
    assento depois de o termo estar escrito — a relação dos documentos ficava
    de fora. O casamento não compra selo: é o da habilitação."""
    _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ", codigos=("14.1.1",))
    hid, ficha = _habilitacao_ate_o_edital(balcao)
    _post(balcao, ficha, ficha, acao="habilitar")
    hab = _um(balcao, "SELECT * FROM hc_habilitacoes WHERE id = %s", (hid,))
    assert hab["situacao"] == "HABILITADO" and hab["selo"]
    f = _form_casamento()
    for de_fora in ("habilitacao_serventia", "habilitacao_selo", "proclamas_data",
                    "documentos_apresentados"):
        f.pop(de_fora)
    f |= {"habilitacao_id": str(hid)}
    antes = len(_pedidos_de_selo(balcao))
    assento, _ato, html = _lavrar(balcao, "CASAMENTO", f, folha=FOLHAS[6])
    assert len(_pedidos_de_selo(balcao)) == antes, "o casamento comprou selo"
    termo = _termo(balcao, assento["id"])
    edital = str(hab["edital_em"])
    _contem(termo, "o termo do casamento pela habilitação desta casa",
            "Os proclamas foram publicados nesta serventia em "
            f"{edital[8:10]}/{edital[5:7]}/{edital[:4]}",
            "os seguintes documentos:")
    _sem_defeito_de_texto(termo, "o termo de casamento")


def test_casamento_com_habilitacao_de_outra_serventia_do_protocolo_a_certidao(balcao):
    """LRP art. 70 (os elementos do assento), CC arts. 1.535 e 1.536; o selo é
    comprado no registro porque a habilitação é de outra serventia (item
    14.1.6), pago pelo protocolo; a certidão (14.5.1) também."""
    p = _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ",
                         codigos=("14.1.6", "14.5.1"))
    assento, ato, html = _lavrar(balcao, "CASAMENTO", _form_casamento(),
                                 folha=FOLHAS[6], protocolo=p, itens=("14.1.6",))
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith("/selo/civil/casamento"), _avisos(html)
    assert pedido["codigoTipoAtoRegistro"] == "14.1.6"
    assert (ato["selo"] or "").strip()
    # O PAGAMENTO COBRIU O SELO: a unidade do item foi gasta neste ato.
    cobertura = _um(balcao, "SELECT * FROM cx_selo_coberturas WHERE tabela = "
                            "'rc_atos' AND ato_id = %s ORDER BY id LIMIT 1",
                    (ato["id"],))
    assert cobertura and cobertura["situacao"] == "CONFIRMADA", cobertura
    _item_gasto_pelo_ato(balcao, p, "14.1.6", tabela="rc_atos", ato_id=ato["id"])
    livro = _livro(balcao, ato)
    assert (livro["serie"], int(ato["folha"]), int(ato["numero_ordem"])) == (
        "RC_B", 1, 1)

    termo = _termo(balcao, assento["id"])
    _sem_defeito_de_texto(termo, "o termo de casamento")
    _contem(termo, "o termo de casamento",
            "nesta cidade de Cidade Exemplo",
            "compareceram os nubentes MARIO EXEMPLO DOS SANTOS",   # item 1º
            "inscrita no CPF n.º 000.000.011-63",
            "natural de Cidade Exemplo/MA",
            "certidões de nascimento dos nubentes",                 # item 5º
            "Ofício de Outra Cidade/MA",
            "proclamas publicados em 01/09/2026",                   # item 4º
            "comunhão parcial de bens",                             # item 7º
            "BEATRIZ EXEMPLO DE SOUZA DOS SANTOS",                  # item 8º
            "ANA EXEMPLO DOS SANTOS e JOAO EXEMPLO DOS SANTOS",     # item 2º
            "MARIA EXEMPLO DE SOUZA e JOSE EXEMPLO DE SOUZA",
            "CARLA EXEMPLO",                                        # item 6º
            "Lido e achado conforme",
            f"Eu, {OFICIAL}, {FUNCAO}, escrevi e assino.")
    folha = _folha_do_livro(balcao, assento["id"])
    _contem(folha, "a folha do livro", "Termo: 1", "Livro: 1", ato["selo"],
            "PEDRO EXEMPLO DOS SANTOS")              # o juiz de paz assina

    cert, html_c = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[7],
                           protocolo=p, itens=("14.5.1",))
    assert (cert["selo"] or "").strip(), _avisos(html_c)
    assert _pedidos_de_selo(balcao)[-1]["codigoTipoAtoCertidao"] == "14.5.1"
    _item_gasto_pelo_ato(balcao, p, "14.5.1", tabela="rc_certidoes",
                         ato_id=cert["id"])
    teor = cert["teor"]
    _sem_defeito_de_texto(teor.replace("\n", " "), "a certidão de casamento")
    _contem(teor, "a certidão de casamento", "CERTIDÃO DE CASAMENTO",
            "MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA",
            assento["matricula"],
            # a data da celebração é a do fato, e não a do registro (art. 70, 4º)
            "DATA DA CELEBRAÇÃO POR EXTENSO\nDEZESSETE DE OUTUBRO DE DOIS MIL "
            "E VINTE E SEIS",
            "COMUNHÃO PARCIAL", "BEATRIZ EXEMPLO DE SOUZA DOS SANTOS",
            "ANA EXEMPLO DOS SANTOS", "MARIA EXEMPLO DE SOUZA",
            "LIVRO\n1", "FOLHA\n1", "TERMO\n1", "O referido é verdade e dou fé.")
    papel = _confere_o_papel_da_certidao(balcao, cert["id"],
                                         selo=cert["selo"])
    _contem(papel, "o papel da certidão de casamento", "CERTIDÃO DE CASAMENTO",
            "MARIO EXEMPLO DOS SANTOS", "BEATRIZ EXEMPLO DE SOUZA DOS SANTOS")


def test_o_casamento_registra_as_duas_testemunhas(balcao):
    """CC art. 1.534 (pelo menos duas testemunhas); LRP art. 70, item 6º; CN-MA
    art. 284, VI (cada uma qualificada). Consertado no LD01: a tela do
    casamento tinha UM bloco de testemunha, e o termo saía «assinam … as
    testemunhas CARLA EXEMPLO» com um nome só — e só o nome."""
    p = _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ",
                         codigos=("14.1.6",))
    html = balcao["cliente"].get("/rcpn/novo/casamento").get_data(as_text=True)
    assert 'name="testemunha2_nome"' in html, "a tela não tem a 2ª testemunha"
    f = _form_casamento()
    f |= _qualificacao("testemunha2", "PEDRO EXEMPLO DOS SANTOS", sexo="M",
                       profissao="agricultor", documento_numero="000.000.015-97")
    assento, _ato, _ = _lavrar(balcao, "CASAMENTO", f, folha=FOLHAS[6],
                               protocolo=p, itens=("14.1.6",))
    testemunhas = _ler(balcao, "SELECT nome FROM rc_pessoas WHERE assento_id = %s "
                               "AND papel = 'TESTEMUNHA' ORDER BY id",
                       (assento["id"],))
    assert len(testemunhas) >= 2, testemunhas
    termo = _termo(balcao, assento["id"])
    _contem(termo, "o termo de casamento com duas testemunhas",
            "as testemunhas CARLA EXEMPLO, brasileira, lavradora",
            "; e PEDRO EXEMPLO DOS SANTOS, brasileiro, agricultor")


def test_o_termo_de_casamento_traz_a_data_da_celebracao(balcao):
    """LRP art. 70, item 4º; CN-MA art. 284, IV. Consertado no LD01: o termo
    começava «Em <data do ato>» e ignorava a data do fato, que a certidão
    imprime como DATA DA CELEBRAÇÃO — celebrado num dia e lavrado no outro,
    termo e certidão discordavam."""
    p = _abrir_protocolo(balcao, interessado="MARIO E BEATRIZ",
                         codigos=("14.1.6",))
    f = _form_casamento() | {"data_fato": "2026-10-19"}
    assento, _ato, _ = _lavrar(balcao, "CASAMENTO", f, folha=FOLHAS[6],
                               protocolo=p, itens=("14.1.6",))
    assert "dezenove (19) de outubro" in _termo(balcao, assento["id"])


# ========================================== 2ª via, inteiro teor e as notas


def test_segunda_via_e_inteiro_teor_saem_pagos_pelo_protocolo(balcao):
    """LRP art. 19 (certidão em breve relato ou inteiro teor) e art. 14,
    parágrafo único (o valor no documento); a 2ª via compra o selo 14.5.1 e o
    inteiro teor o 14.5.6, cada um com a sua unidade do protocolo pago e a sua
    folha de segurança. O inteiro teor reproduz o termo palavra por palavra."""
    assento, ato, _ = _lavrar(balcao, "NASCIMENTO", _form_nascimento(),
                              folha=FOLHAS[0])
    _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[0])
    p = _abrir_protocolo(balcao, interessado="BEATRIZ EXEMPLO DE SOUZA",
                         codigos=("14.5.1", "14.5.6"))

    segunda, html = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[3],
                            protocolo=p, itens=("14.5.1",))
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith("/selo/civil/nascimento/segunda-via")
    assert pedido["codigoTipoAtoCertidao"] == "14.5.1", _avisos(html)
    assert pedido["papelMoeda"]["codigo"] == FOLHAS[3]
    assert segunda["selo"] and segunda["selo"] != ato["selo"]
    assert _um(balcao, "SELECT situacao FROM pp_folhas WHERE codigo = %s",
               (FOLHAS[3],))["situacao"] == "USADA"
    _item_gasto_pelo_ato(balcao, p, "14.5.1", tabela="rc_certidoes",
                         ato_id=segunda["id"])
    papel = _confere_o_papel_da_certidao(balcao, segunda["id"],
                                         selo=segunda["selo"])
    # O VALOR DO ATO VAI NO PAPEL PELO TEXTO DO SELO (LRP art. 14, parágrafo
    # único): o TJMA devolve a etiqueta com «Total R$ … Emol R$ …», e o papel
    # a decompõe (`selo_no_papel`). O selador de mentira não traz valores; a
    # etiqueta abaixo é a forma que o TJMA devolve, com valores de exemplo.
    with balcao["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE sd_selos SET texto = %s WHERE numero = %s",
            (f"Poder Judiciário – TJMA. Selo: {segunda['selo']}, "
             "20/10/2026 10:00:00, Ato: 14.5.1, Parte(s): PEDRO EXEMPLO DOS "
             "SANTOS, Total R$ 33,50 Emol R$ 30,00 FERC R$ 1,00 FADEP R$ 1,00 "
             "FEMP R$ 1,00 FERRFIS R$ 0,00 Consulte em https://selo.tjma.jus.br",
             segunda["selo"]))
    papel = _odt(balcao, segunda["id"])
    _contem(papel, "o papel da 2ª via", "33,50", "30,00")

    termo = _termo(balcao, assento["id"])
    inteiro, html_it = _emitir(
        balcao, assento["id"], folha_seguranca=FOLHAS[4], protocolo=p,
        itens=("14.5.6",), tipo_certidao="inteiro_teor", modo_inteiro="texto",
        teor_colado=termo)
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["codigoTipoAtoCertidao"] == "14.5.6", _avisos(html_it)
    assert inteiro["modalidade"] == "INTEIRO_TEXTO"
    _contem(inteiro["teor"], "o inteiro teor", "CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO",
            "PEDRO EXEMPLO DOS SANTOS", assento["matricula"],
            "livro 1, folha 1, termo 1", "CNS 000000")
    papel_it = _odt(balcao, inteiro["id"])
    assert termo in papel_it, "o inteiro teor não reproduz o termo inteiro"
    _contem(papel_it, "o papel do inteiro teor", "Era o que cabia certificar.",
            OFICIAL, FUNCAO, inteiro["selo"])


@pytest.mark.parametrize("tipo, codigo, rota, caminho, extra", [
    ("AVERBACAO", "14.4.1", "averbar", "averbacao",
     {"natureza_averbacao": "reconhecimento_filiacao",
      "fundamento": "LRP art. 29, § 1º, alínea d"}),
    ("ANOTACAO", "14.7", "anotar", "anotacao", {}),
    ("RETIFICACAO", "14.10", "retificar", "retificacao",
     {"fundamento": "LRP art. 110, erro de grafia"}),
], ids=["averbacao", "anotacao", "retificacao"])
def test_o_lancamento_a_margem_sai_selado_e_entra_na_certidao(
        balcao, tipo, codigo, rota, caminho, extra):
    """LRP art. 97 e ss. (averbação), 106 a 108 (anotação), 109 e 110
    (retificação); art. 21 (a certidão menciona TODA alteração posterior, sob
    pena de responsabilidade); CN-MA arts. 337, 348 e 367. O lançamento não
    ocupa folha nova e é pago pelo protocolo; a 2ª via que vem depois o traz."""
    assento, _ato, _ = _lavrar(balcao, "NASCIMENTO", _form_nascimento(),
                               folha=FOLHAS[0])
    _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[0])
    p = _abrir_protocolo(balcao, interessado="BEATRIZ EXEMPLO DE SOUZA",
                         codigos=(codigo, "14.5.1"))
    teor = (f"{tipo.capitalize()} de teste: consta que o registrado PEDRO "
            f"EXEMPLO DOS SANTOS teve o assento alterado por mandado.")
    livro_antes = _livro(balcao, _ato)
    numero_antes = _um(balcao, "SELECT proximo FROM nu_numeracao WHERE serie = "
                               "'RC_A'")
    r = _post(balcao, f"/rcpn/{assento['id']}/{rota}",
              f"/rcpn/{assento['id']}/lancar", tipo=tipo, teor=teor,
              **extra, **_do_protocolo(p, codigo))
    lanc = _um(balcao, "SELECT * FROM rc_atos WHERE assento_id = %s AND tipo = %s "
                       "ORDER BY id DESC LIMIT 1", (assento["id"], tipo))
    assert lanc and (lanc["selo"] or "").strip(), _avisos(r.get_data(as_text=True))
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["caminho"].endswith(f"/selo/civil/nascimento/{caminho}")
    # O ITEM DO TJ QUE O PROTOCOLO PAGOU é o que vai no envelope.
    assert f'"{codigo}"' in json.dumps(pedido), pedido
    # NÃO OCUPA FOLHA NEM NÚMERO NOVO: lança-se no espaço do próprio assento.
    assert _livro(balcao, _ato)["folha_atual"] == livro_antes["folha_atual"]
    assert _um(balcao, "SELECT proximo FROM nu_numeracao WHERE serie = "
                       "'RC_A'") == numero_antes
    # O TEOR DO LANÇAMENTO leva quem lavrou e o selo (rc_etiqueta_averbacao).
    _contem(lanc["teor"], "o lançamento", "teve o assento alterado",
            lanc["selo"])
    _item_gasto_pelo_ato(balcao, p, codigo, tabela="rc_atos", ato_id=lanc["id"])

    cert, html_c = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[3],
                           protocolo=p, itens=("14.5.1",))
    assert cert["selo"], _avisos(html_c)
    _contem(cert["teor"], "a 2ª via depois do lançamento",
            "OBSERVAÇÕES/AVERBAÇÕES A ACRESCER:", "teve o assento alterado",
            lanc["selo"])
    assert "NADA CONSTA" not in cert["teor"]
    papel = _odt(balcao, cert["id"])
    _contem(papel, "o papel da 2ª via", "teve o assento alterado")
    assert "Não há." not in papel.split("ANOTAÇÕES/AVERBAÇÕES", 1)[1][:60]


def test_averbacao_gratuita_sela_isenta_e_guarda_o_comprovante(balcao):
    """A gratuidade por pessoa (custas.GRATUIDADES_POR_PESSOA, LRP art. 30, §
    1º): sem protocolo pago, o selo sai GRATUITO com o motivo escrito, e o
    comprovante (o PDF) se guarda pela tela das gratuidades (LX16)."""
    assento, _ato, _ = _lavrar(balcao, "NASCIMENTO", _form_nascimento(),
                               folha=FOLHAS[0])
    r = _post(balcao, f"/rcpn/{assento['id']}/averbar",
              f"/rcpn/{assento['id']}/lancar", tipo="AVERBACAO",
              teor="Averbação gratuita de teste: inclusão de sobrenome por "
                   "declaração de hipossuficiência.",
              natureza_averbacao="alteracao_nome", ato_gratuito="1",
              gratuidade_codigo="HIPOSSUFICIENCIA",
              motivo_gratuidade="declaração de hipossuficiência assinada")
    lanc = _um(balcao, "SELECT * FROM rc_atos WHERE assento_id = %s AND "
                       "tipo = 'AVERBACAO' ORDER BY id DESC LIMIT 1",
               (assento["id"],))
    assert lanc and lanc["selo"], _avisos(r.get_data(as_text=True))
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["dadosSelo"].get("isentoGratuito") == "GRATUITO", pedido
    assert "HIPOSSUFICIÊNCIA" in pedido["dadosSelo"].get(
        "motivoIsentoGratuito", "").upper()
    assert _um(balcao, "SELECT count(*) AS n FROM cx_lancamentos")["n"] == 0

    # O TJMA DEVOLVE O SELO GRATUITO COM A MARCA «Selo Isento» no texto, e é
    # por ela que a casa sabe que falta o comprovante (`gratuidade_comprovante`).
    # O selador de mentira não a escreve: a etiqueta é a forma da do TJMA.
    import gratuidade_comprovante as GC
    selo_id = _um(balcao, "SELECT id FROM sd_selos WHERE numero = %s",
                  (lanc["selo"],))["id"]
    with balcao["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE sd_selos SET texto = %s WHERE id = %s",
            (f"Poder Judiciário – TJMA. Selo: {lanc['selo']}, Ato: 14.4.1, "
             "Selo Isento, Consulte em https://selo.tjma.jus.br", selo_id))
    with balcao["db"].connect() as con:
        assert [x["id"] for x in GC.pendentes(con, nome=OFICIAL)] == [selo_id]
    c = balcao["cliente"]
    token = _token(c.get("/gratuidades/comprovantes").get_data(as_text=True))
    r = c.post(f"/gratuidades/comprovantes/{selo_id}", data={
        "csrf_token": token, "fundamento": "ISENCAO_LEGAL",
        "arquivo": (io.BytesIO(b"%PDF-1.4\n% comprovante de teste\n%%EOF\n"),
                    "comprovante.pdf")},
        content_type="multipart/form-data", follow_redirects=True)
    guardado = _um(balcao, "SELECT count(*) AS n FROM attachments WHERE "
                           "entity_type = 'SELO_GRATUIDADE' AND entity_id = %s",
                   (selo_id,))
    assert guardado["n"] == 1, _avisos(r.get_data(as_text=True))
    # E A PENDÊNCIA SOME com o PDF guardado.
    with balcao["db"].connect() as con:
        assert GC.pendentes(con, nome=OFICIAL) == []


# ================================================================ Livro E


LIVRO_E = {
    "EMANCIPACAO": ("14.2", {
        "nome": "PEDRO EXEMPLO DOS SANTOS",
        "livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-10-05",
        "livro_e_escritura_livro": "40", "livro_e_escritura_folha": "12",
        "livro_e_tabelionato": "Tabelionato de Notas de Cidade Exemplo",
        **_qualificacao("pessoa", "PEDRO EXEMPLO DOS SANTOS", sexo="M",
                        estado_civil="solteiro", data_nascimento="2009-05-01"),
        "filiacao1_nome": "BEATRIZ EXEMPLO DE SOUZA",
        "filiacao2_nome": "MARIO EXEMPLO DOS SANTOS"},
     ("Emancipação", "Tabelionato de Notas de Cidade Exemplo",
      "BEATRIZ EXEMPLO DE SOUZA")),
    "INTERDICAO": ("14.2", {
        "nome": "PEDRO EXEMPLO DOS SANTOS", "livro_e_titulo": "SENTENCA",
        "livro_e_titulo_data": "2026-09-01",
        "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo",
        "livro_e_juiz": "CARLA EXEMPLO", "livro_e_processo": "0000001-00.2026.8.10.0000",
        "livro_e_causa": "causa de exemplo", "livro_e_limites": "atos patrimoniais",
        **_qualificacao("pessoa", "PEDRO EXEMPLO DOS SANTOS", sexo="M"),
        "curador_nome": "BEATRIZ EXEMPLO DE SOUZA", "curador_sexo": "F",
        "requerente_nome": "MARIO EXEMPLO DOS SANTOS"},
     ("Interdição", "Vara Única da Comarca de Cidade Exemplo",
      "BEATRIZ EXEMPLO DE SOUZA", "atos patrimoniais")),
    "AUSENCIA": ("14.2", {
        "nome": "PEDRO EXEMPLO DOS SANTOS", "livro_e_titulo": "SENTENCA",
        "livro_e_titulo_data": "2026-09-01",
        "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo",
        "livro_e_ausencia_tempo": "dois anos",
        **_qualificacao("pessoa", "PEDRO EXEMPLO DOS SANTOS", sexo="M"),
        "curador_nome": "BEATRIZ EXEMPLO DE SOUZA", "curador_sexo": "F",
        "requerente_nome": "MARIO EXEMPLO DOS SANTOS"},
     ("Ausência", "Vara Única da Comarca de Cidade Exemplo",
      "BEATRIZ EXEMPLO DE SOUZA")),
    "TUTELA": ("14.2", {
        "nome": "PEDRO EXEMPLO DOS SANTOS", "livro_e_titulo": "SENTENCA",
        "livro_e_titulo_data": "2026-09-01",
        "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo",
        **_qualificacao("pessoa", "PEDRO EXEMPLO DOS SANTOS", sexo="M",
                        data_nascimento="2015-01-01"),
        "tutor_nome": "BEATRIZ EXEMPLO DE SOUZA", "tutor_sexo": "F"},
     ("Tutela", "BEATRIZ EXEMPLO DE SOUZA")),
    "UNIAO_ESTAVEL": ("14.8", {
        "nome": "MARIO EXEMPLO DOS SANTOS e BEATRIZ EXEMPLO DE SOUZA",
        "livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-10-05",
        "livro_e_tabelionato": "Tabelionato de Notas de Cidade Exemplo",
        "livro_e_uniao_inicio": "2020-01-01", "regime_bens": "COMUNHAO_PARCIAL",
        **_qualificacao("companheiro1", "MARIO EXEMPLO DOS SANTOS", sexo="M",
                        estado_civil="solteiro"),
        **_qualificacao("companheiro2", "BEATRIZ EXEMPLO DE SOUZA",
                        estado_civil="solteira",
                        documento_numero="000.000.011-63")},
     ("MARIO EXEMPLO DOS SANTOS", "BEATRIZ EXEMPLO DE SOUZA",
      "Tabelionato de Notas de Cidade Exemplo")),
    "OPCAO_NACIONALIDADE": ("14.3.2", {
        "nome": "PEDRO EXEMPLO DOS SANTOS", "livro_e_titulo": "SENTENCA",
        "livro_e_titulo_data": "2026-09-01",
        "livro_e_juizo": "Vara Federal de Exemplo",
        **_qualificacao("pessoa", "PEDRO EXEMPLO DOS SANTOS", sexo="M",
                        naturalidade_cidade="Lisboa", naturalidade_uf=""),
        "filiacao1_nome": "BEATRIZ EXEMPLO DE SOUZA"},
     ("Vara Federal de Exemplo",)),
}


@pytest.mark.parametrize("especie", sorted(LIVRO_E))
def test_o_registro_do_livro_e_vai_do_protocolo_ao_termo_selado(balcao, especie):
    """LRP arts. 89 a 94-A (emancipação, interdição, ausência, união estável),
    art. 32, § 4º (opção de nacionalidade), tutela por analogia ao art. 92;
    CN-MA arts. 327 a 329. Pago pelo protocolo (14.2, 14.8, 14.3.2), sem folha
    de segurança (o envelope do Livro E não leva `papelMoeda`)."""
    codigo, campos, no_termo = LIVRO_E[especie]
    p = _abrir_protocolo(balcao, interessado="MARIO EXEMPLO DOS SANTOS",
                         codigos=(codigo,))
    assento, ato, html = _lavrar(balcao, especie, campos, protocolo=p,
                                 itens=(codigo,))
    assert (ato["selo"] or "").strip(), _avisos(html)
    pedido = _pedidos_de_selo(balcao)[-1]
    assert pedido["codigoTipoAtoRegistro"] == codigo, pedido
    _item_gasto_pelo_ato(balcao, p, codigo, tabela="rc_atos", ato_id=ato["id"])
    livro = _livro(balcao, ato)
    assert (livro["serie"], int(ato["numero_ordem"])) == ("RC_E", 1)
    termo = _termo(balcao, assento["id"])
    _sem_defeito_de_texto(termo, f"o termo do Livro E ({especie})")
    _contem(termo, f"o termo do Livro E ({especie})", *no_termo,
            "Lido e achado conforme", f"Eu, {OFICIAL}, {FUNCAO}, dou fé e assino.")


@pytest.mark.parametrize("especie", sorted(LIVRO_E))
def test_a_certidao_do_livro_e_traz_o_que_o_termo_registra(balcao, especie):
    """LRP arts. 19, 21 e 89 a 94-A. Consertado no LD01: o Livro E não tinha
    certidão adequada — o breve relato só tinha corpo para nascimento,
    casamento e óbito, e saía com o título «CERTIDÃO» e o nome, sem a
    espécie, o título registrado (sentença ou escritura, juízo, data), o
    curador ou tutor; e não havia papel, porque a guarda do molde recusava o
    Livro E. O breve relato e o papel leem a mesma lista
    (`rc_certidao.linhas_do_livro_e`), e o título diz a espécie."""
    import rc_certidao as RCE
    codigo, campos, no_termo = LIVRO_E[especie]
    p = _abrir_protocolo(balcao, interessado="MARIO EXEMPLO DOS SANTOS",
                         codigos=(codigo, "14.5.1"))
    assento, _ato, _ = _lavrar(balcao, especie, campos, protocolo=p,
                               itens=(codigo,))
    cert, html = _emitir(balcao, assento["id"], folha_seguranca=FOLHAS[5],
                         protocolo=p, itens=("14.5.1",))
    titulo = RCE.titulo_do_modelo(especie)
    assert titulo != "CERTIDÃO", especie
    _contem(cert["teor"], "o breve relato do Livro E", titulo, *no_termo)
    _sem_defeito_de_texto(cert["teor"].replace("\n", " "),
                          f"a certidão do Livro E ({especie})")
    assert (cert["selo"] or "").strip(), _avisos(html)
    papel = _confere_o_papel_da_certidao(balcao, cert["id"], selo=cert["selo"])
    _contem(papel, f"o papel da certidão do Livro E ({especie})", titulo,
            *no_termo)
