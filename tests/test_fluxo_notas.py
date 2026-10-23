"""Tabelionato de Notas, do protocolo à certidão — LT02, 20/10/2026.

    «quero que seja possível do protocolo à certidão. Minha maior preocupação
     é que TODOS os atos precisam ter uma certidão adequada» — e depois:
    «TERMO E CERTIDÃO».                                  — o oficial, 20/10/2026

O QUE ESTES TESTES FAZEM
    O caminho do balcão, PELAS TELAS, como o escrevente (USER) o faz: abre o
    protocolo no caixa, acrescenta os itens pelo serviço da tabela, abre o
    caixa, quita, marca o protocolo que está atendendo; pratica o ato; sela
    pelo aparelho (o selador falso de `tests/selador_falso.py`, com TLS de
    verdade e a trava do selo pago LIGADA — `protocolo_pago=False`); confere
    livro, folha e termo; confere o TERMO que vai ao livro; emite a CERTIDÃO e
    confere que ela bate com o termo.

    Um teste por tipo de ato; os que têm o mesmo caminho são parametrizados
    (as minutas de fábrica de `notas_modelos` são o cardápio: cada uma é um
    tipo de ato que a casa lavra).

O QUE «ADEQUADO» QUER DIZER AQUI (a régua está em `_conferir_termo` e
`_conferir_certidao`, e cada exigência cita o artigo):
    - TERMO: partes e qualificação, objeto, data por extenso, local, quem
      lavrou, leitura, encerramento, assinaturas, selo e emolumentos no ato
      (CN-MA arts. 87, XVI; 131; 798; 847; CC art. 215, § 1º); sem campo
      vazio, sem «None», sem marcador de modelo sobrando, sem texto repetido
      (CN-MA art. 795, § 2º: «sem claros ou espaços em branco»);
    - CERTIDÃO: identifica a serventia e quem a expede, o ato (livro, folha,
      termo, data), reproduz o teor (inteiro teor, CN-MA art. 851), traz o
      selo com o código e a consulta (arts. 131 e 132) e os emolumentos
      (art. 87, XVI), e diz a forma.

O APARELHO DIZ OS VALORES
    O selador de verdade devolve no `textoSelo` o «Total R$ … Emol R$ …» que o
    papel imprime (medido: 25.634 selos de 25.634 — ver
    `test_etiqueta_reconhecimento`). O falso devolve só o número; aqui ele
    passa a devolver o texto inteiro, com os valores da tabela de 2026
    (`tests/custas_reais.json`, tabela pública), para o papel ter o que
    imprimir. Sem isso, a conferência dos emolumentos mediria o falso, e não
    a casa.

DEFEITO ACHADO vira `xfail(strict=True, reason="DEFEITO: …")`: a asserção fica
inteira, e o dia em que o defeito for consertado o teste avisa.

Dados fictícios (docs/AGENTES.md): nomes «EXEMPLO», Cidade Exemplo, CNS
000000, CPFs da lista `tests/fixtures/anti_vazamento/documentos_ficticios.txt`.
"""
from __future__ import annotations

import json
import re
import sys
import unicodedata
import zipfile
from datetime import date
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import banco_pg                                              # noqa: E402
from bd_nativo import banco                                  # noqa: E402

SENHA = "Senha#12345"
OFICIAL = "BEATRIZ EXEMPLO DE SOUZA"
SUBSTITUTA = "CARLA EXEMPLO"
ESCREVENTE = "PEDRO EXEMPLO DOS SANTOS"
CIDADE = "Cidade Exemplo"

SERVENTIA = {
    "unit_name": "TABELIONATO DE NOTAS DE CIDADE EXEMPLO",
    "serventia_titular": OFICIAL,
    "serventia_titulo": "Tabeliã e Oficiala de Registro",
    "ri_substituta": SUBSTITUTA,
    "serventia_cnpj": "00.000.001/0000-55",
    "serventia_endereco": "Rua Exemplo, 100, Centro",
    "serventia_cep": "65000-000",
    "serventia_telefone": "(99) 3000-0000",
    "ri_cidade": CIDADE,
    "ri_uf": "MA",
    "ri_cns": "000000",
    "selo_tabela_custas_em": "2026-01-01",
}

# A TABELA DE 2026 DO TJMA, pública, exportada do acervo (`custas_reais.json`).
CUSTAS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
VALORES = {v["tj"]: v for v in CUSTAS["valores_2026"]}
VIGENCIA = int(CUSTAS["valores_2026"][0]["v"])

# AS PESSOAS DO ATO — fictícias, com os CPFs da lista da casa.
PESSOAS = {
    "MARIO EXEMPLO DOS SANTOS": "000.000.001-91",
    "JOANA EXEMPLO DA SILVA": "000.000.002-72",
    "PAULO EXEMPLO TESTEMUNHA": "000.000.003-53",
    "LUCIA EXEMPLO TESTEMUNHA": "000.000.010-82",
    "ANA EXEMPLO HERDEIRA": "000.000.011-63",
}


# ================================================================ a bancada


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _flashes(html: str) -> list[str]:
    return [" ".join(re.sub(r"<[^>]+>", " ", m).split()) for m in
            re.findall(r'<div class="flash [^"]*" data-aviso>(.*?)</div>', html,
                       re.DOTALL)]


def _sem_acento(texto: str) -> str:
    s = unicodedata.normalize("NFKD", str(texto or ""))
    return "".join(c for c in s if not unicodedata.combining(c))


def _reais(valor: float) -> str:
    return f"{valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _texto_do_selo(numero: str, envelope: dict) -> str:
    """O `textoSelo` como o aparelho de verdade o escreve — com os valores.

    A forma é a medida no acervo (`test_etiqueta_reconhecimento`): «Poder
    Judiciario - TJMA. Selo: …, data, Ato: …, Parte(s): …, Total R$ … Emol R$
    … FERC R$ … FADEP R$ … FEMP R$ … Consulte em https://selo.tjma.jus.br».
    O isento declara «Selo Isento» e zero (CN-MA art. 133) — é por essa
    marca que `gratuidade_comprovante` cobra o PDF do comprovante.
    """
    ato = (envelope.get("ato") or {}).get("codigo") or ""
    quantos = int(envelope.get("quantidade") or 1)
    partes = ", ".join(p.get("nome", "") for p in
                       ((envelope.get("partes") or {}).get("parteAto") or []))
    linha = VALORES.get(ato)
    isento = envelope.get("isento")
    if isento is True or (isinstance(isento, dict) and isento.get("value")):
        valores = ("Selo Isento, Total R$ 0,00 Emol R$ 0,00 FERC R$ 0,00 "
                   "FADEP R$ 0,00 FEMP R$ 0,00")
    elif linha:
        emol = linha["emol"] * quantos
        ferc, femp, fadp = (linha["ferc"] * quantos, linha["femp"] * quantos,
                            linha["fadp"] * quantos)
        total = emol + ferc + femp + fadp + linha["ferrfis"] * quantos
        valores = (f"Total R$ {_reais(total)} Emol R$ {_reais(emol)} "
                   f"FERC R$ {_reais(ferc)} FADEP R$ {_reais(fadp)} "
                   f"FEMP R$ {_reais(femp)}")
    else:
        faixa = next((f for f in CUSTAS["faixas_2026"]
                      if f["strCodigoTJ"] == ato), None)
        valores = (f"Total R$ {_reais(faixa['curValor'] * 1.1)} Emol R$ "
                   f"{_reais(faixa['curValor'])}") if faixa else ""
    return (f"Poder Judiciário – TJMA. Selo: {numero}, 20/10/2026 10:00:00, "
            f"Ato: {ato}, Parte(s): {partes}, {valores} "
            "Consulte em https://selo.tjma.jus.br")


def _aparelho_com_valores(aparelho) -> None:
    """Troca a resposta do selador falso pela do aparelho de verdade."""
    Mao = aparelho.http.RequestHandlerClass

    class MaoComValores(Mao):
        def _responder(self, status, corpo):
            if isinstance(corpo, dict) and corpo.get("resumos"):
                try:
                    envelope = json.loads(aparelho.pedidos[-1]["corpo"] or "{}")
                except ValueError:
                    envelope = {}
                for r in corpo["resumos"]:
                    r["textoSelo"] = _texto_do_selo(r["numeroSelo"], envelope)
            return super()._responder(status, corpo)

    aparelho.http.RequestHandlerClass = MaoComValores


def _semear_a_tabela(db) -> None:
    """Os serviços das Notas, com o preço de 2026, e as faixas da escritura.

    O caixa lê o preço do item da tabela vigente — o valor do protocolo não se
    digita. A casa nova chega sem a tabela; a de verdade a importa do
    E-Ofício (`caixa_import`).
    """
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("UPDATE cx_vigencias SET vigente = 0")
        bd.escrever(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente)
               VALUES (%s, '2026', 1)
               ON CONFLICT (codigo) DO UPDATE SET vigente = 1""", (VIGENCIA,))
        for v in CUSTAS["valores_2026"]:
            if not str(v["tj"]).startswith("13."):
                continue
            codigo = int(v["s"])
            total = round(v["emol"] + v["ferc"] + v["femp"] + v["fadp"]
                          + v["ferrfis"], 2)
            bd.escrever(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao,
                       descricao_norm, ativo)
                   VALUES (%s, %s, %s, %s, 1) ON CONFLICT DO NOTHING""",
                (codigo, v["tj"], v["descricao"],
                 _sem_acento(v["descricao"]).upper()))
            bd.escrever(
                """INSERT INTO cx_servico_valores (servico, vigencia,
                       emolumentos, ferc, femp, fadep, ferrfis, total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT DO NOTHING""",
                (codigo, VIGENCIA, _reais(v["emol"]), _reais(v["ferc"]),
                 _reais(v["femp"]), _reais(v["fadp"]), _reais(v["ferrfis"]),
                 _reais(total)))
        for f in CUSTAS["faixas_2026"]:
            if int(f["intCodigoTabela"]) != 3:
                continue
            total = round(f["curValor"] + f["curFERMOJUPI"] + f["curValor_MP"]
                          + f["curValor_DP"] + (f["curvalor_ferrfis"] or 0), 2)
            bd.escrever(
                """INSERT INTO cx_faixas (vigencia, tabela, de, ate, codigo_tj,
                       emolumentos, ferc, femp, fadep, ferrfis, total)
                   VALUES (%s, 3, %s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (VIGENCIA, _reais(f["curDe"]), _reais(f["curAte"]),
                 f["strCodigoTJ"], _reais(f["curValor"]),
                 _reais(f["curFERMOJUPI"]), _reais(f["curValor_MP"]),
                 _reais(f["curValor_DP"]), _reais(f["curvalor_ferrfis"] or 0),
                 _reais(total)))


@pytest.fixture()
def balcao(cg_casa, monkeypatch):
    """A serventia de exemplo, com o selador ligado e o escrevente no balcão."""
    from conftest import cg_login
    from selador_de_bancada import ligar_o_selador

    db = cg_casa["db"]
    db.create_user("oficial", OFICIAL, SENHA, "ADMIN")
    db.create_user("escrevente", ESCREVENTE, SENHA, "USER")
    db.set_settings(SERVENTIA)
    _semear_a_tabela(db)
    # AS PÁGINAS DO TERMO se medem no LibreOffice (`_paginas_medidas_para_lancar`);
    # a casa deixou a medição num ponto só, para o teste a trocar sem ele.
    # Duas páginas: uma folha, frente e verso.
    monkeypatch.setitem(cg_casa["app"].extensions, "notas_medir_paginas",
                        lambda odt: 2)
    c = cg_casa["app"].test_client()
    cg_login(c, "escrevente", SENHA)
    bancada = {"app": cg_casa["app"], "cliente": c, "banco": cg_casa["banco"],
               "db": db, "dados": cg_casa["dados"]}
    with ligar_o_selador(bancada, protocolo_pago=False) as aparelho:
        _aparelho_com_valores(aparelho)
        bancada["aparelho"] = aparelho
        yield bancada


def _ler(b, sql: str, parametros=()) -> list[dict]:
    con = banco_pg.conectar(b["banco"])
    try:
        return banco(con).ler(sql, parametros)
    finally:
        con.close()


def _um(b, sql: str, parametros=()) -> dict | None:
    linhas = _ler(b, sql, parametros)
    return linhas[0] if linhas else None


def _tela(b, url: str) -> str:
    r = b["cliente"].get(url)
    assert r.status_code == 200, f"{url} respondeu {r.status_code}"
    return r.get_data(as_text=True)


def _postar(b, url: str, dados: dict, *, de: str | None = None,
            seguir: bool = True, arquivos=None):
    dados = dict(dados)
    dados.setdefault("csrf_token", _token(_tela(b, de or url)))
    if arquivos:
        dados.update(arquivos)
    return b["cliente"].post(url, data=dados, follow_redirects=seguir,
                             content_type=("multipart/form-data" if arquivos
                                           else None))


# ======================================================= o caixa, pela tela


def _servico(codigo_tj: str) -> int:
    return int(VALORES[codigo_tj]["s"])


def abrir_protocolo_pago(b, itens, *, interessado="MARIO EXEMPLO DOS SANTOS",
                         base_da_faixa: int | None = None) -> dict:
    """Protocolo → itens pela tabela → caixa aberto → quitado → em atendimento.

    `itens`: [(codigo_tj, quantidade)]. A faixa da escritura com valor vai
    pela tabela 3 e pelo valor do negócio (`base_da_faixa`, em centavos).
    """
    r = _postar(b, "/caixa/protocolos",
                {"acao": "novo", "interessado": interessado,
                 "telefone": "(99) 90000-0000", "atribuicao": "NOTAS"},
                seguir=False)
    assert r.status_code == 302, "o protocolo não abriu"
    pid = int(re.search(r"/caixa/protocolos/(\d+)", r.headers["Location"]).group(1))
    ficha = f"/caixa/protocolos/{pid}"
    for codigo, quantidade in itens:
        dados = {"acao": "acrescentar", "quantidade": str(quantidade)}
        if codigo == "FAIXA":
            dados.update(tabela="3", base_calculo=_reais(base_da_faixa / 100))
        else:
            dados["servico"] = str(_servico(codigo))
        _postar(b, f"{ficha}/itens", dados, de=ficha)
    _postar(b, "/caixa", {"acao": "abrir", "saldo_inicial": "0,00"})
    for item in _ler(b, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id = %s "
                        "AND coalesce(quitado, 0) = 0 ORDER BY id", (pid,)):
        _postar(b, f"{ficha}/itens", {"acao": "quitar", "item_id": str(item["id"]),
                                      "forma_pagamento": "DINHEIRO"}, de=ficha)
    p = _um(b, "SELECT numero FROM cx_protocolos WHERE id = %s", (pid,))
    r = _postar(b, "/selo/cobertura/atender", {"protocolo": p["numero"]},
                de="/selo/cobertura")
    assert f"Você está atendendo o protocolo {p['numero']}" in r.get_data(as_text=True)
    itens_gravados = _ler(b, "SELECT codigo_ato, quitado FROM cx_protocolo_atos "
                             "WHERE protocolo_id = %s ORDER BY id", (pid,))
    assert itens_gravados and all(i["quitado"] == 1 for i in itens_gravados), (
        f"o caixa não quitou os itens: {itens_gravados}")
    return {"id": pid, "numero": p["numero"], "itens": itens_gravados}


def quitar_o_que_falta(b, protocolo: dict) -> None:
    """O item que nasceu depois (o 13.30 do arquivamento) se quita no caixa."""
    ficha = f"/caixa/protocolos/{protocolo['id']}"
    for item in _ler(b, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id = %s "
                        "AND coalesce(quitado, 0) = 0 ORDER BY id",
                     (protocolo["id"],)):
        _postar(b, f"{ficha}/itens", {"acao": "quitar", "item_id": str(item["id"]),
                                      "forma_pagamento": "DINHEIRO"}, de=ficha)


# ===================================================== os papéis, em texto


def _xml_em_texto(xml: str) -> str:
    # Fim de parágrafo e de célula viram espaço; as marcas de dentro da frase
    # (negrito, por exemplo) somem sem espaço, como no papel.
    xml = re.sub(r"</text:(p|h)>|<text:line-break/>|</table:table-cell>", " ", xml)
    xml = re.sub(r"<text:s(?: text:c=\"(\d+)\")?/>", " ", xml)
    texto = re.sub(r"<[^>]+>", "", xml)
    texto = (texto.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&apos;", "'")
             .replace("&amp;", "&"))
    return " ".join(texto.split())


def _texto_do_odt(dados: bytes, *, cabecalho: bool = False) -> str:
    """O texto de um .odt, em uma linha: o corpo, ou o cabeçalho das páginas."""
    pacote = zipfile.ZipFile(BytesIO(dados))
    if cabecalho:
        estilos = pacote.read("styles.xml").decode("utf-8")
        primeiro = re.search(r"<style:header>(.*?)</style:header>", estilos, re.S)
        return _xml_em_texto(primeiro.group(1) if primeiro else "")
    return _xml_em_texto(pacote.read("content.xml").decode("utf-8"))


def _imagens_do_odt(dados: bytes) -> list[str]:
    return [n for n in zipfile.ZipFile(BytesIO(dados)).namelist()
            if n.startswith("Pictures/")]


def _so_texto(html: str) -> str:
    texto = re.sub(r"<[^>]+>", " ", html or "")
    texto = (texto.replace("&lt;", "<").replace("&gt;", ">")
             .replace("&quot;", '"').replace("&#39;", "'").replace("&amp;", "&"))
    return " ".join(texto.split())


_MARCAS_DE_MODELO = (
    (re.compile(r"\{\{|\}\}|\{%|%\}"), "marcador Jinja sobrando"),
    (re.compile(r"\[[A-ZÁÉÍÓÚÂÊÔÃÕÇ][^\[\]]{2,120}\]"), "campo [ ] do modelo sobrando"),
    (re.compile(r"\{[A-ZÁÉÍÓÚÂÊÔÃÕÇ ]{3,}:"), "escolha { : } do modelo sobrando"),
    (re.compile(r"«SE "), "cláusula «SE» do modelo sobrando"),
    (re.compile(r"\bNone\b"), "«None» no papel"),
    (re.compile(r"@@[A-Z_]+@@"), "marca interna @@ sobrando"),
)


def _defeitos_de_texto(texto: str) -> list[str]:
    """O que o art. 795, § 2º, proíbe e o modelo pode deixar: claro, marcador,
    «None», e o mesmo período escrito duas vezes."""
    achados = [f"{rotulo}: {m.group(0)!r}" for padrao, rotulo in _MARCAS_DE_MODELO
               for m in [padrao.search(texto)] if m]
    periodos = [p.strip() for p in re.split(r"(?<=[.;:])\s+", texto)
                if len(p.strip()) >= 60]
    vistos = set()
    for p in periodos:
        if p in vistos:
            achados.append(f"texto repetido: {p[:80]!r}")
        vistos.add(p)
    return achados


# ================================================== o ato de livro, pela tela

# O documento de identidade e a união estável entram na qualificação desde o
# LD07 (CNN art. 111): sem eles o teor sai com o colchete do que falta, e a
# trava da lavratura não deixa o ato ir ao livro — o balcão os informa.
QUALIFICACAO_DA_PESSOA = {
    "nacionalidade": "brasileira", "estado_civil": "solteira",
    "profissao": "comerciante", "tipo_pessoa": "F",
    "endereco": "Rua Exemplo, 10, Centro, Cidade Exemplo-MA",
    "identidade": "1234567 SSP/MA", "uniao_estavel": "NAO",
}


def abrir_o_ato(b, modelo: str, *, interessado: str) -> int:
    r = _postar(b, "/notas/atos/novo",
                {"modelo_codigo": modelo, "tipo": "", "interessado": interessado},
                seguir=False)
    assert r.status_code == 302, f"o ato não abriu ({r.status_code})"
    achado = re.search(r"/notas/atos/(\d+)$", r.headers["Location"])
    assert achado, f"abrir o ato levou a {r.headers['Location']}"
    return int(achado.group(1))


def ligar_ao_protocolo(b, ato_id: int, protocolo: dict) -> None:
    html = _postar(b, f"/notas/atos/{ato_id}/protocolo-geral",
                   {"acao": "vincular", "numero": protocolo["numero"]},
                   de=f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert not [f for f in _flashes(html) if "não" in f.lower()
                and "protocolo" in f.lower()], _flashes(html)


def incluir_parte(b, ato_id: int, nome: str, qualificacao: str, *,
                  testemunha: bool = False) -> None:
    dados = {"acao": "parte_nova", "nome": nome, "documento": PESSOAS[nome],
             "qualificacao": qualificacao, **QUALIFICACAO_DA_PESSOA}
    if testemunha:
        dados["testemunha"] = "1"
    html = _postar(b, f"/notas/atos/{ato_id}", dados).get_data(as_text=True)
    assert "Parte incluída" in " ".join(_flashes(html)), _flashes(html)


def _valor_de_exemplo(campo: dict, hoje: dict) -> str:
    """O que o escrevente digitaria: a data do dia nos campos da data do ato,
    e um valor fictício que se reconhece no papel nos outros."""
    if campo["chave"] in hoje:
        return hoje[campo["chave"]]
    if campo["tipo"] == "data":
        return "dez de outubro de dois mil e vinte e seis (10/10/2026)"
    if campo["tipo"] == "moeda":
        return "R$ 2.000,00 (dois mil reais)"
    rotulo = _sem_acento(campo["rotulo"]).upper()
    return f"{rotulo} DE EXEMPLO"


def preencher_pelo_modelo(b, ato_id: int, modelo: str, *,
                          aceita_pendencia: bool = False) -> dict:
    """«Preencher a partir do modelo», com todos os campos e a 1ª opção."""
    from datetime import datetime

    import notas_teor as NT
    from ri_modelos_atos import campos_do_modelo
    corpo = _um(b, "SELECT corpo FROM nt_modelos WHERE codigo = %s",
                (modelo,))["corpo"]
    hoje = NT.valores_campos_data_lavratura(datetime.now())
    valores = {}
    for campo in campos_do_modelo({"corpo": corpo}):
        if campo["tipo"] == "condicao":
            continue                                  # cláusula opcional: fora
        if campo["tipo"] == "escolha":
            valores[campo["chave"]] = campo["opcoes"][0]
        elif campo["chave"] != NT.CHAVE_ASSINANTES:   # este, a tela completa
            valores[campo["chave"]] = _valor_de_exemplo(campo, hoje)
    html = _postar(b, f"/notas/atos/{ato_id}/preencher", valores,
                   de=f"/notas/atos/{ato_id}").get_data(as_text=True)
    recado = " ".join(_flashes(html))
    assert ("Teor montado a partir do modelo" in recado
            or (aceita_pendencia and "continuam em branco" in recado)), recado
    return valores


def lancar_no_livro(b, ato_id: int, *, item: str, especie: str | None = None,
                    isento: bool = False, motivo: str = "") -> str:
    dados = {"acao": "lancar", "codigo_tj": item}
    if especie:
        dados["especie_procuracao"] = especie
    if isento:
        dados.update(selo_isento="1", motivo_isencao=motivo)
    html = _postar(b, f"/notas/atos/{ato_id}", dados).get_data(as_text=True)
    return " · ".join(_flashes(html))


def o_termo_do_livro(b, ato_id: int) -> bytes:
    r = b["cliente"].get(f"/notas/atos/{ato_id}/termo-livro")
    assert r.status_code == 200, (
        f"o termo do livro não saiu ({r.status_code}): "
        f"{b['cliente'].get(r.headers.get('Location', '/')).status_code}")
    return r.data


def o_traslado(b, ato_id: int) -> bytes:
    r = b["cliente"].get(f"/notas/atos/{ato_id}/traslado")
    assert r.status_code == 200, f"o traslado não saiu ({r.status_code})"
    return r.data


def emitir_certidao(b, *, protocolo: dict | None = None, **campos) -> int:
    """«Emitir a certidão», pela tela das certidões das Notas."""
    consulta = "&".join(f"{k}={v}" for k, v in campos.items()
                        if k in ("ato_id", "nome", "documento"))
    dados = {k: str(v) for k, v in campos.items()}
    if protocolo:
        dados["protocolo_id"] = str(protocolo["id"])
    antes = _um(b, "SELECT coalesce(max(id), 0) AS n FROM nt_certidoes")["n"]
    html = _postar(b, "/notas/certidoes/emitir", dados,
                   de=f"/notas/certidoes?{consulta}").get_data(as_text=True)
    nova = _um(b, "SELECT id, cancelada, selo FROM nt_certidoes WHERE id > %s "
                  "ORDER BY id LIMIT 1", (antes,))
    assert nova, f"a certidão não foi emitida: {_flashes(html)}"
    assert not nova["cancelada"], f"a certidão saiu cancelada: {_flashes(html)}"
    return int(nova["id"])


def o_papel_da_certidao(b, certidao_id: int) -> bytes:
    r = b["cliente"].get(f"/notas/certidoes/{certidao_id}/odt?formato=odt")
    assert r.status_code == 200, f"o papel da certidão não saiu ({r.status_code})"
    return r.data


def ato(b, ato_id: int) -> dict:
    return _um(b, "SELECT * FROM nt_atos WHERE id = %s", (ato_id,))


def itens_oferecidos(b, ato_id: int) -> list[str]:
    """Os itens que a tela do ato oferece no quadro do selo — o balcão só
    escolhe o que está na lista."""
    html = _tela(b, f"/notas/atos/{ato_id}")
    bloco = re.search(r'<select name="codigo_tj">(.*?)</select>', html, re.S)
    return re.findall(r'<option value="([^"]+)"', bloco.group(1)) if bloco else []


def _pdf_de_uma_folha() -> bytes:
    from pypdf import PdfWriter
    escrita = PdfWriter()
    escrita.add_blank_page(width=595, height=842)
    saida = BytesIO()
    escrita.write(saida)
    return saida.getvalue()


def arquivar_o_documento(b, ato_id: int, protocolo: dict) -> None:
    """O arquivamento obrigatório (13.30) da procuração e afins, pela tela:
    anexa o documento, confirma as folhas, e o caixa quita o 13.30 que a
    confirmação lançou no protocolo (CN-MA art. 789)."""
    html = _postar(b, f"/notas/atos/{ato_id}/anexos",
                   {"descricao": "Documento de identificação do outorgante"},
                   de=f"/notas/atos/{ato_id}",
                   arquivos={"arquivo": (BytesIO(_pdf_de_uma_folha()),
                                         "identidade.pdf")}).get_data(as_text=True)
    assert "Arquivo guardado" in " ".join(_flashes(html)), _flashes(html)
    html = _postar(b, f"/notas/atos/{ato_id}",
                   {"acao": "confirmar_arquivamento",
                    "folhas_arquivamento": "1"}).get_data(as_text=True)
    assert "Folhas do arquivamento confirmadas" in " ".join(_flashes(html)), (
        _flashes(html))
    quitar_o_que_falta(b, protocolo)


# ===================================================== a régua do papel


def _conferir_termo(b, a: dict, caso, texto: str, odt: bytes) -> None:
    """O TERMO que vai ao livro é adequado — cada falta diz o artigo."""
    from datetime import date

    import notas_teor as NT
    from ri_web import MESES
    faltas = []

    def exige(condicao: bool, o_que: str) -> None:
        if not condicao:
            faltas.append(o_que)

    exige(SERVENTIA["unit_name"] in texto, "o nome da serventia")
    exige(f"LIVRO {a['livro']}" in texto and f"FOLHA {a['folha']}" in texto
          and f"TERMO {a['termo']}" in texto,
          "livro, folha e termo no cabeçalho do termo (CN-MA art. 792)")
    exige(_titulo(b, a).upper() in texto.upper(), "o título do instrumento")
    hoje = date.today()
    exige(NT.valores_campos_data_lavratura(
        __import__("datetime").datetime.now())["ano_por_extenso"] in texto
          and MESES[hoje.month - 1] in texto,
          "a data por extenso (CN-MA art. 795, § 4º; art. 798, I)")
    exige(CIDADE in texto, "o local do ato (CN-MA art. 798, I)")
    exige(ESCREVENTE in texto, "quem lavrou (CN-MA art. 798, XIII)")
    for nome, _qualificacao, testemunha in caso.partes:
        exige(nome in texto, f"a parte {nome} (CN-MA art. 798, V)")
        if not testemunha:
            exige(_sem_acento(PESSOAS[nome]).replace(".", "").replace("-", "")
                  in texto, f"o CPF de {nome} (CN-MA art. 798, V)")
    for dado in ("brasileira", "solteira", "comerciante", "Rua Exemplo, 10"):
        exige(dado in texto, f"a qualificação ({dado}) (CC art. 215, § 1º, III)")
    exige(re.search(r"\blid[ao]\b|\bleu\b|\bleram\b|\bleitura\b|\bli\b", texto,
                    re.I) is not None,
          "a declaração de leitura (CN-MA art. 798, XI; art. 847, IV)")
    exige(re.search(r"encerr|dou fé", texto, re.I) is not None,
          "o encerramento (CN-MA art. 798, XII)")
    linhas = texto.count("_________________________________")
    exige(linhas >= len(caso.partes) + 1,
          f"uma linha de assinatura por comparecente e a de quem lavrou "
          f"(CN-MA art. 798, XIII): {linhas}")
    exige(a["selo"] in texto, "o número do selo no corpo do ato (CN-MA art. 131)")
    exige("selo.tjma.jus.br" in texto and any(
        n.startswith("Pictures/qr-") for n in _imagens_do_odt(odt)),
          "a consulta do selo e o QR (CN-MA art. 132)")
    exige(("Total R$" in texto and "Emol R$" in texto),
          "os emolumentos no ato (CN-MA art. 87, XVI)")
    if caso.arquivamento:
        exige(bool(a["selo_arquivamento"]) and a["selo_arquivamento"] in texto,
              "o selo do arquivamento obrigatório (13.30) no termo")
    defeitos = _defeitos_de_texto(texto)
    assert not faltas and not defeitos, (
        f"o termo de {caso.minuta} não está adequado: faltas={faltas} "
        f"defeitos={defeitos}")


def _sem_espaco_antes_da_pontuacao(texto: str) -> str:
    """A certidão tira o espaço antes da vírgula que sobra quando a cláusula
    opcional sai (`certidao_texto.sem_linha_de_assinatura_a_mao`); o termo o
    guarda. A comparação do teor é de palavra, não de espaço."""
    return re.sub(r"\s+([,;.:])", r"\1", texto)


def _titulo(b, a: dict) -> str:
    """O título que o termo e o traslado imprimem (`titulo_do_instrumento`)."""
    from notas_web import titulo_do_instrumento
    nome = None
    if a["modelo_codigo"]:
        nome = _um(b, "SELECT nome FROM nt_modelos WHERE codigo = %s",
                   (a["modelo_codigo"],))["nome"]
    return titulo_do_instrumento(a, nome_modelo=nome)


def _teor_do_termo(texto: str, a: dict, titulo: str) -> str:
    """O teor como o termo o imprime: do título ao quadro do selo do ato."""
    from notas_web import rotulo_do_selo
    inicio = texto.index(f"TERMO {a['termo']}")
    depois = texto.upper().index(titulo.upper(), inicio) + len(titulo)
    fim = texto.index(rotulo_do_selo(a["tipo"]), depois)
    return texto[depois:fim].strip()


def _conferir_certidao(b, a: dict, caso, termo: str, papel: bytes,
                       certidao_id: int) -> None:
    """A CERTIDÃO de inteiro teor é adequada e FIEL AO TERMO."""
    corpo = _texto_do_odt(papel)
    cabecalho = _texto_do_odt(papel, cabecalho=True)
    linha = _um(b, "SELECT * FROM nt_certidoes WHERE id = %s", (certidao_id,))
    faltas = []

    def exige(condicao: bool, o_que: str) -> None:
        if not condicao:
            faltas.append(o_que)

    exige(SERVENTIA["unit_name"].upper() in cabecalho.upper()
          and OFICIAL in cabecalho and "CNS 000000" in cabecalho,
          "a serventia, o oficial e o CNS no cabeçalho (Lei 8.935, art. 6º, II)")
    exige("CERTIDÃO DE INTEIRO TEOR" in corpo, "a forma: inteiro teor (CN-MA art. 851)")
    exige(f"n. {linha['numero']}/{linha['ano']}" in corpo, "o número da certidão")
    data = a["data"]
    exige(f"Livro {a['livro']}, folha {a['folha']}" in corpo
          and f"{data[8:10]}/{data[5:7]}/{data[:4]}" in corpo,
          "o livro, a folha e a data do ato (CN-MA art. 851, § 1º)")
    exige(f"termo n. {a['termo']}" in corpo,
          "o número do termo (CN-MA art. 792 — numeração das escrituras)")
    teor = _teor_do_termo(termo, a, _titulo(b, a))
    exige(_sem_espaco_antes_da_pontuacao(teor)
          in _sem_espaco_antes_da_pontuacao(corpo),
          "o teor do termo, na íntegra (CN-MA art. 851)")
    exige(a["selo"] in corpo, "o selo do ato certificado, como está no termo")
    depois_do_selo = corpo[corpo.find(a["selo"]):][:600]
    exige("Total R$" in depois_do_selo,
          "os emolumentos do ato certificado, como estão no termo (art. 87, XVI)")
    if caso.arquivamento:
        exige(a["selo_arquivamento"] in corpo, "o selo do arquivamento do ato")
    exige(bool(linha["selo"]) and linha["selo"] in corpo,
          "o selo da certidão (CN-MA art. 131)")
    exige("SELO DA CERTIDÃO" in corpo and "Ato 13.12.1" in corpo
          and "selo.tjma.jus.br" in corpo
          and any(n.startswith("Pictures/qr-") for n in _imagens_do_odt(papel)),
          "o código, a consulta e o QR do selo da certidão (CN-MA art. 132)")
    carimbo = corpo[corpo.find("SELO DA CERTIDÃO"):]
    exige("Total R$" in carimbo and "Emol R$" in carimbo,
          "os emolumentos da certidão (CN-MA art. 87, XVI)")
    exige(ESCREVENTE in corpo, "quem expede a certidão")
    exige(f"{CIDADE}-MA" in corpo, "o lugar da expedição")
    defeitos = _defeitos_de_texto(corpo)
    assert not faltas and not defeitos, (
        f"a certidão de {caso.minuta} não está adequada: faltas={faltas} "
        f"defeitos={defeitos}")


# ============================================== os atos de livro, um a um


def preparar_o_ato(b, caso, protocolo: dict, *,
                   aceita_pendencia: bool = False) -> int:
    """Abre o ato pela minuta, liga ao protocolo, partes, valor, arquivamento
    e teor — tudo o que vem antes de «Lançar no livro»."""
    ato_id = abrir_o_ato(b, caso.minuta, interessado=caso.partes[0][0])
    assert ato(b, ato_id)["tipo"] == caso.tipo
    ligar_ao_protocolo(b, ato_id, protocolo)
    for nome, qualificacao, testemunha in caso.partes:
        incluir_parte(b, ato_id, nome, qualificacao, testemunha=testemunha)
    if caso.valor is not None:
        _postar(b, f"/notas/escrituras/{ato_id}/valor",
                {"valor": str(caso.valor)}, de=f"/notas/atos/{ato_id}")
    if caso.arquivamento:
        arquivar_o_documento(b, ato_id, protocolo)
    preencher_pelo_modelo(b, ato_id, caso.minuta,
                          aceita_pendencia=aceita_pendencia)
    return ato_id


def lavrar_pela_tela(b, caso, protocolo: dict, **lancamento) -> tuple:
    """`preparar_o_ato` e o lançamento, com o item que o protocolo pagou e
    que a tela oferece. Devolve (ato_id, item, recado)."""
    ato_id = preparar_o_ato(b, caso, protocolo)
    item = protocolo["itens"][0]["codigo_ato"] if caso.item == "FAIXA" else caso.item
    assert item in itens_oferecidos(b, ato_id), (
        f"a tela não oferece o item {item}: {itens_oferecidos(b, ato_id)}")
    return ato_id, item, lancar_no_livro(b, ato_id, item=item,
                                         especie=caso.especie, **lancamento)


class Caso:
    """Um tipo de ato de livro: a minuta de fábrica e o que o balcão informa."""

    def __init__(self, minuta, tipo, partes, *, valor=None, item="13.2",
                 especie=None, marcas=()):
        self.minuta, self.tipo, self.partes = minuta, tipo, partes
        self.valor, self.item, self.especie = valor, item, especie
        self.marcas = marcas
        import notas_arquivamento as NARQ
        self.arquivamento = NARQ.arquivamento_obrigatorio(tipo)

    def __repr__(self):
        return self.minuta


VENDE = ("MARIO EXEMPLO DOS SANTOS", "OUTORGANTE", False)
COMPRA = ("JOANA EXEMPLO DA SILVA", "OUTORGADO", False)
SEGUNDA = ("JOANA EXEMPLO DA SILVA", "OUTORGANTE", False)
TESTEMUNHAS = [("PAULO EXEMPLO TESTEMUNHA", "TESTEMUNHA", True),
               ("LUCIA EXEMPLO TESTEMUNHA", "TESTEMUNHA", True)]
CEM_MIL = 10_000_000          # R$ 100.000,00, em centavos


# AS TRÊS MINUTAS QUE A TELA NÃO PREENCHIA — o usufruto (uma escolha dentro de
# outra), as diretivas (uma cláusula «SE» dentro de outra) e a partilha (duas
# escolhas «ATO» com opções diferentes) — foram consertadas no LD02 (21/10/2026)
# e andam do protocolo à certidão como as outras. A trava continua valendo para
# o modelo que a casa personalizou com a marcação antiga: ver
# `test_a_marca_aninhada_trava_a_lavratura_e_nao_vai_crua_ao_livro`.
CASOS_DE_LIVRO = [
    # Escrituras com valor declarado: a faixa da tabela 3 (13.1.x) pelo valor.
    *[Caso(m, "ESCRITURA", [VENDE, COMPRA], valor=CEM_MIL, item="FAIXA")
      for m in ("NT-ESC-COMPRA-VENDA", "NT-ESC-COMPRA-VENDA-RURAL",
                "NT-ESC-DOACAO", "NT-ESC-CESSAO-HEREDITARIA", "NT-ESC-HIPOTECA",
                "NT-ESC-ALIENACAO-FIDUCIARIA", "NT-ESC-CONFISSAO-DACAO",
                "NT-ESC-USUFRUTO")],
    Caso("NT-ESC-PERMUTA", "ESCRITURA", [VENDE, SEGUNDA], valor=CEM_MIL,
         item="FAIXA"),
    *[Caso(m, "ESCRITURA", [VENDE, SEGUNDA], valor=CEM_MIL, item="FAIXA")
      for m in ("NT-ESC-INVENTARIO-PARTILHA", "NT-ESC-SOBREPARTILHA",
                "NT-ESC-PARTILHA-ADJUDICACAO")],
    # Escrituras sem valor econômico: 13.2.
    *[Caso(m, "ESCRITURA", [VENDE, SEGUNDA], valor=0)
      for m in ("NT-ESC-NOMEACAO-INVENTARIANTE", "NT-ESC-DIVORCIO",
                "NT-ESC-SEPARACAO", "NT-ESC-CONVERSAO-DIVORCIO",
                "NT-ESC-RESTABELECIMENTO", "NT-ESC-UNIAO-ESTAVEL",
                "NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL", "NT-ESC-QUITACAO",
                "NT-ESC-DISTRATO", "NT-ESC-PACTO-ANTENUPCIAL")],
    Caso("NT-ESC-EMANCIPACAO", "ESCRITURA", [VENDE, COMPRA], valor=0),
    Caso("NT-ESC-DIRETIVAS-VONTADE", "ESCRITURA", [VENDE], valor=0),
    # Procurações e afins: caminho da procuração, arquivamento obrigatório.
    Caso("NT-PROC-PUBLICA", "PROCURACAO", [VENDE, COMPRA], item="13.9.3",
         especie="PODERES_ESPECIFICOS"),
    Caso("NT-PROC-CAUSA-PROPRIA", "PROCURACAO", [VENDE, COMPRA], item="13.9.3",
         especie="VENDA"),
    Caso("NT-PROC-PREVIDENCIARIA", "PROCURACAO_PREVIDENCIARIA", [VENDE, COMPRA],
         item="13.9.3", especie="INSS"),
    Caso("NT-SUBSTABELECIMENTO", "SUBSTABELECIMENTO", [VENDE, COMPRA],
         item="13.9.3", especie="PODERES_ESPECIFICOS"),
    Caso("NT-REVOGACAO-MANDATO", "REVOGACAO", [VENDE, COMPRA], item="13.9.3",
         especie="PODERES_ESPECIFICOS"),
    Caso("NT-RENUNCIA-MANDATO", "RENUNCIA", [VENDE], item="13.9.3",
         especie="PODERES_ESPECIFICOS"),
    # Testamentos: caminho próprio, duas testemunhas instrumentárias.
    Caso("NT-TESTAMENTO-PUBLICO", "TESTAMENTO",
         [("MARIO EXEMPLO DOS SANTOS", "TESTADOR", False), *TESTEMUNHAS],
         item="13.10.1"),
    Caso("NT-TESTAMENTO-CERRADO", "TESTAMENTO_CERRADO",
         [("MARIO EXEMPLO DOS SANTOS", "TESTADOR", False), *TESTEMUNHAS],
         item="13.10.3"),
    # Atas notariais.
    Caso("NT-ATA-NOTARIAL", "ATA",
         [("MARIO EXEMPLO DOS SANTOS", "SOLICITANTE", False)], item="13.14.1"),
    Caso("NT-ATA-ADJUDICACAO", "ATA",
         [("MARIO EXEMPLO DOS SANTOS", "REQUERENTE", False)], item="13.14.1"),
    # A ata para usucapião é ato de conteúdo econômico: cobra-se pela faixa do
    # 13.1 conforme o valor venal do imóvel (CNN art. 423, I; o item 13.14.3
    # remete ao 13.1), e não pelo 13.14.1 da ata comum. Até o LD02 (21/10/2026)
    # este caso pagava o 13.14.1, e a tela não tinha onde pôr o valor.
    Caso("NT-ATA-USUCAPIAO", "ATA_USUCAPIAO",
         [("MARIO EXEMPLO DOS SANTOS", "REQUERENTE", False)], valor=CEM_MIL,
         item="FAIXA"),
]


def test_cada_minuta_de_fabrica_tem_o_seu_caso_ponta_a_ponta():
    """O cardápio é a lista de minutas: minuta nova sem caso aqui é tipo de
    ato que ninguém levou do protocolo à certidão."""
    import notas_modelos as NM
    assert sorted(c.minuta for c in CASOS_DE_LIVRO) == sorted(
        m["codigo"] for m in NM.MINUTAS)


@pytest.mark.parametrize("caso", [pytest.param(c, id=c.minuta, marks=c.marcas)
                                  for c in CASOS_DE_LIVRO])
def test_o_ato_de_livro_vai_do_protocolo_a_certidao_fiel_ao_termo(balcao, caso):
    """Protocolo pago → ato → livro/folha/termo → selo → termo adequado →
    traslado → certidão de inteiro teor adequada e igual ao termo.

    A trava do selo pago está LIGADA: o selo só sai porque o item da tabela
    está no protocolo que o escrevente atende, quitado no caixa (LX16). O
    item escolhido no lançamento tem de ser um dos que a tela oferece.
    """
    b = balcao
    protocolo = abrir_protocolo_pago(b, [(caso.item, 1), ("13.12.1", 1)],
                                     base_da_faixa=caso.valor)
    ato_id, item, recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO", f"{caso.minuta} não ficou lavrado: {recado}"
    assert a["livro"] and a["folha"] and a["termo"], recado
    assert f"Lançado no livro {a['livro']}, folha {a['folha']}" in recado
    assert a["selo"], recado
    if caso.arquivamento:
        assert a["selo_arquivamento"], f"faltou o selo do arquivamento: {recado}"
    usados = _ler(b, "SELECT codigo_ato, quantidade_usada FROM cx_protocolo_atos "
                     "WHERE protocolo_id = %s ORDER BY id", (protocolo["id"],))
    assert {"codigo_ato": item, "quantidade_usada": 1} in usados, (
        f"o selo não gastou o item pago: {usados}")

    termo_odt = o_termo_do_livro(b, ato_id)
    termo = _texto_do_odt(termo_odt)
    _conferir_termo(b, a, caso, termo, termo_odt)

    traslado = _texto_do_odt(o_traslado(b, ato_id))
    assert _teor_do_termo(termo, a, _titulo(b, a)) in traslado, (
        "o traslado não reproduz o termo (CN-MA art. 850, § 2º)")
    assert a["selo"] in traslado and "Traslado" in traslado

    pedido = {"ato_id": ato_id, "requerente": caso.partes[0][0]}
    if caso.tipo in ("TESTAMENTO", "TESTAMENTO_CERRADO"):
        # Enquanto vive o testador, só ele, por requerimento escrito
        # (CN-MA art. 851, § 4º).
        pedido.update(requerente_documento=PESSOAS[caso.partes[0][0]],
                      requerimento_escrito="1")
    certidao_id = emitir_certidao(b, protocolo=protocolo, **pedido)
    _conferir_certidao(b, ato(b, ato_id), caso, termo,
                       o_papel_da_certidao(b, certidao_id), certidao_id)


def _caso(minuta: str) -> Caso:
    return next(c for c in CASOS_DE_LIVRO if c.minuta == minuta)


# ======================================================= a gratuidade, com o PDF


def test_a_procuracao_do_inss_isenta_sela_sem_pagar_e_cobra_o_pdf_da_gratuidade(balcao):
    """A procuração para fins previdenciários sai com selo ISENTO (art. 68-A da
    Lei 8.212/1991 — o motivo dos 8 selos isentos desta casa), sem item pago
    no protocolo, e o selo isento vira a pendência do comprovante, que se
    junta em PDF depois do ato («geralmente temos o comprovante da gratuidade
    só depois que o ato é praticado» — o oficial, 19/10/2026; CN-MA art. 133).

    ATÉ O LT02 ESTE CAMINHO NÃO EXISTIA: a trava do selo pago só lia
    `isento: true`, e as Notas mandam `isento: {value: true, motivo}` — o ato
    ficava suspenso, esperando um pagamento que a lei dispensa.
    """
    b = balcao
    caso = _caso("NT-PROC-PREVIDENCIARIA")
    # Só a certidão se paga; o ato e o arquivamento são isentos.
    protocolo = abrir_protocolo_pago(b, [("13.12.1", 1)])
    ato_id, item, recado = lavrar_pela_tela(
        b, Caso(caso.minuta, caso.tipo, caso.partes, item="13.9.3",
                especie="INSS"),
        protocolo, isento=True, motivo="art. 68-A da Lei 8.212/1991")
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO", recado
    assert a["selo"] and a["selo_arquivamento"], recado
    selos = _ler(b, "SELECT id, numero, texto FROM sd_selos WHERE tabela = 'nt_atos' "
                    "AND ato_id = %s ORDER BY id", (ato_id,))
    assert {s["numero"] for s in selos} == {a["selo"], a["selo_arquivamento"]}
    assert all("Selo Isento" in s["texto"] for s in selos)
    assert not _ler(b, "SELECT id FROM cx_protocolo_atos WHERE protocolo_id = %s "
                       "AND coalesce(quantidade_usada, 0) > 0 ORDER BY id",
                    (protocolo["id"],)), "o ato isento gastou item pago"

    termo = _texto_do_odt(o_termo_do_livro(b, ato_id))
    assert a["selo"] in termo and "Total R$ 0,00" in termo, (
        "o termo não declara o selo isento (CN-MA arts. 87, XVI, e 133)")

    # O COMPROVANTE: a pendência aparece, recebe o PDF, e some.
    pendentes = _tela(b, "/gratuidades/comprovantes")
    for s in selos:
        assert s["numero"] in pendentes, f"o selo isento {s['numero']} não pede o PDF"
        r = _postar(b, f"/gratuidades/comprovantes/{s['id']}",
                    {"fundamento": "ISENCAO_LEGAL"}, de="/gratuidades/comprovantes",
                    arquivos={"arquivo": (BytesIO(_pdf_de_uma_folha()),
                                          "comprovante-inss.pdf")})
        assert "comprovante(s) guardado(s)" in " ".join(
            _flashes(r.get_data(as_text=True)))
    import gratuidade_comprovante as GC
    con = banco_pg.conectar(b["banco"])
    try:
        ainda = {p["numero"] for p in GC.pendentes(con, nome=ESCREVENTE)}
    finally:
        con.close()
    assert not ainda & {s["numero"] for s in selos}, (
        "o PDF juntado não baixou a pendência da gratuidade")

    certidao_id = emitir_certidao(b, protocolo=protocolo, ato_id=ato_id,
                                  requerente=caso.partes[0][0])
    _conferir_certidao(b, ato(b, ato_id), caso, termo,
                       o_papel_da_certidao(b, certidao_id), certidao_id)


def test_a_isencao_no_formato_das_notas_e_gratuidade_para_a_trava():
    """`isento: {value: true, motivo}` é a forma que as Notas mandam
    (procuração, arquivamento e certidão) — e a trava a lê como a do RCPN."""
    import ato_selado as AS
    import notas_certidao as NCE
    envelope, _ = AS.envelope_do_ato_de_livro_das_notas(
        tipo="PROCURACAO_PREVIDENCIARIA", codigo_tj="13.9.3",
        escrevente=ESCREVENTE, versao_tabela="0520260101", livro="1", folha="1",
        partes=[{"nome": "MARIO EXEMPLO DOS SANTOS"}], especie_procuracao="INSS",
        isento=True, motivo_isencao="art. 68-A da Lei 8.212/1991")
    assert AS.selo_e_gratuito(envelope)
    assert AS.selo_e_gratuito(NCE.envelope(
        codigo="13.12.1", quantidade=1, escrevente=ESCREVENTE,
        versao_tabela="0520260101", parte={"nome": "MARIO EXEMPLO DOS SANTOS"},
        isento=True, motivo_isencao="hipossuficiência"))
    assert not AS.selo_e_gratuito({"isento": {"value": False, "motivo": "x"}})
    sem, _ = AS.envelope_do_ato_de_livro_das_notas(
        tipo="PROCURACAO", codigo_tj="13.9.3", escrevente=ESCREVENTE,
        versao_tabela="0520260101", livro="1", folha="1",
        especie_procuracao="SIMPLES")
    assert not AS.selo_e_gratuito(sem), "o ato pago não pode virar gratuito"


# ============================================== a certidão pela busca da parte


def test_a_certidao_pela_busca_e_positiva_com_o_ato_e_negativa_sem_ele(balcao):
    """«inclusive busca quando não disser o ato» — o oficial, 15/10/2026.

    A positiva relaciona o ato que a busca achou, com os elementos do termo
    (espécie, livro, folha, data, a qualidade da parte); a negativa diz que
    nada consta. As duas identificam a serventia, levam o selo da certidão e
    os emolumentos (CN-MA arts. 87, XVI, 131 e 851).
    """
    b = balcao
    caso = _caso("NT-ESC-COMPRA-VENDA")
    protocolo = abrir_protocolo_pago(
        b, [("FAIXA", 1), ("13.12.1", 2)], base_da_faixa=caso.valor)
    ato_id, _item, recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO", recado

    positiva = emitir_certidao(b, protocolo=protocolo,
                               nome="MARIO EXEMPLO DOS SANTOS",
                               requerente="MARIO EXEMPLO DOS SANTOS")
    papel = o_papel_da_certidao(b, positiva)
    corpo = _texto_do_odt(papel)
    linha = _um(b, "SELECT * FROM nt_certidoes WHERE id = %s", (positiva,))
    assert linha["tipo"] == "POSITIVA" and "CERTIDÃO POSITIVA" in corpo.upper()
    assert f"Livro {a['livro']}, folha {a['folha']}" in corpo
    assert "MARIO EXEMPLO DOS SANTOS" in corpo and "OUTORGANTE" in corpo
    assert linha["selo"] in corpo and "Total R$" in corpo
    assert SERVENTIA["unit_name"].upper() in _texto_do_odt(papel, cabecalho=True).upper()
    assert not _defeitos_de_texto(corpo), _defeitos_de_texto(corpo)

    negativa = emitir_certidao(b, protocolo=protocolo, nome="ANA EXEMPLO HERDEIRA",
                               requerente="ANA EXEMPLO HERDEIRA")
    corpo = _texto_do_odt(o_papel_da_certidao(b, negativa))
    linha = _um(b, "SELECT * FROM nt_certidoes WHERE id = %s", (negativa,))
    assert linha["tipo"] == "NEGATIVA" and "NADA CONSTA" in corpo
    assert linha["selo"] in corpo and "Total R$" in corpo
    assert not _defeitos_de_texto(corpo), _defeitos_de_texto(corpo)


def test_a_certidao_positiva_escreve_a_data_do_ato_como_data_de_papel(balcao):
    """A data do ato achado sai como data de papel (dd/mm/aaaa), e não como o
    banco a guarda (CN-MA art. 795, § 4º) — a inteiro teor já convertia; a
    positiva escrevia `{{ x.data }}` cru até o LD02 (21/10/2026)."""
    b = balcao
    caso = _caso("NT-ESC-COMPRA-VENDA")
    protocolo = abrir_protocolo_pago(
        b, [("FAIXA", 1), ("13.12.1", 1)], base_da_faixa=caso.valor)
    ato_id, _item, _recado = lavrar_pela_tela(b, caso, protocolo)
    data = ato(b, ato_id)["data"]
    positiva = emitir_certidao(b, protocolo=protocolo,
                               nome="MARIO EXEMPLO DOS SANTOS")
    corpo = _texto_do_odt(o_papel_da_certidao(b, positiva))
    assert f"{data[8:10]}/{data[5:7]}/{data[:4]}" in corpo
    assert data not in corpo


def test_a_certidao_em_breve_relato_traz_os_elementos_do_termo(balcao):
    """A cópia RESUMIDA do art. 851 do CN-MA («cópia integral ou resumida»),
    que a casa não emitia até o LD02 (21/10/2026): o livro, a folha, o termo,
    as partes e o selo do ato, como o termo os tem."""
    import notas_certidao as NCE
    assert "BREVE_RELATO" in NCE.TIPOS
    b = balcao
    caso = _caso("NT-ESC-COMPRA-VENDA")
    protocolo = abrir_protocolo_pago(
        b, [("FAIXA", 1), ("13.12.1", 1)], base_da_faixa=caso.valor)
    ato_id, _item, _recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    breve = emitir_certidao(b, protocolo=protocolo, ato_id=ato_id,
                            tipo="BREVE_RELATO")
    corpo = _texto_do_odt(o_papel_da_certidao(b, breve))
    for elemento in (f"Livro {a['livro']}", f"folha {a['folha']}",
                     f"termo n. {a['termo']}", "MARIO EXEMPLO DOS SANTOS",
                     "JOANA EXEMPLO DA SILVA", a["selo"]):
        assert elemento in corpo, elemento


# ============================================ o item da tabela, na tela do ato


@pytest.mark.parametrize("minuta,item", [
    ("NT-SUBSTABELECIMENTO", "13.9.5"),
    ("NT-REVOGACAO-MANDATO", "13.9.6"),
    ("NT-RENUNCIA-MANDATO", "13.9.6"),
    ("NT-ESC-DIVORCIO", "13.7"),
    ("NT-ESC-SEPARACAO", "13.7"),
    ("NT-ESC-CONVERSAO-DIVORCIO", "13.7"),
    ("NT-ESC-DISSOLUCAO-UNIAO-ESTAVEL", "13.7"),
])
def test_a_tela_oferece_o_item_proprio_da_tabela_para_a_especie(balcao, minuta, item):
    """O item próprio da tabela de 2026 (`tests/custas_reais.json`) para a
    espécie: 13.9.5 no substabelecimento, 13.9.6 na revogação e na renúncia,
    13.7 na separação, no divórcio e na extinção da união estável sem bens. Até
    o LD02 (21/10/2026) a tela só oferecia os itens medidos no caminho do selo,
    e o caixa cobra pelo próprio: o selo pedido pelo item da tela não achava o
    item pago no protocolo."""
    b = balcao
    caso = _caso(minuta)
    protocolo = abrir_protocolo_pago(b, [(item, 1)])
    ato_id = preparar_o_ato(b, Caso(caso.minuta, caso.tipo, caso.partes,
                                    valor=0 if caso.tipo == "ESCRITURA" else None,
                                    item=item, especie=caso.especie), protocolo)
    assert item in itens_oferecidos(b, ato_id)


# ================================================ os consertos, um por um


def test_a_escolha_longa_da_minuta_vira_campo_da_tela_e_pendencia():
    """11 das 35 minutas têm escolha com mais de 300 letras (o ITR da rural,
    o regime da união estável…). Até o LT02 ela não virava campo, não era
    pendência, e ia crua ao livro."""
    from ri_modelos_atos import campos_do_modelo, pendencias
    import modelos_da_casa as MOD
    corpo = MOD.minuta_de_fabrica("NT-ESC-COMPRA-VENDA-RURAL")["corpo"]
    assert "op_itr" in {c["chave"] for c in campos_do_modelo({"corpo": corpo})}
    assert "{ITR}" in pendencias(corpo)


def _a_minuta_de_antes_ajustada_pela_casa(b, minuta: str) -> None:
    """A minuta com a marcação de ANTES do LD02, como a casa que a personalizou
    a guarda: o ajuste da casa não se toca na subida (`notas_modelos.instalar`
    deixa a linha com `atualizado_em`), e é ele que o balcão usa. O corpo de
    antes é o do ouro do LF06D."""
    ouro = json.loads((RAIZ / "tests" / "fixtures" / "modelos_ouro"
                       / "LF06D_notas.json").read_text("utf-8"))
    corpo = next(m["corpo"] for m in ouro["minutas"] if m["codigo"] == minuta)
    with b["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE nt_modelos SET corpo = %s, atualizado_em = %s WHERE codigo = %s",
            (corpo, "2026-10-20T10:00:00", minuta))


@pytest.mark.parametrize("minuta,marca", [("NT-ESC-USUFRUTO", "{ATO"),
                                          ("NT-ESC-DIRETIVAS-VONTADE", "«SE NOMEAR"),
                                          ("NT-ESC-PARTILHA-ADJUDICACAO", "{ATO")])
def test_a_marca_aninhada_trava_a_lavratura_e_nao_vai_crua_ao_livro(balcao, minuta,
                                                                  marca):
    """O usufruto tinha uma escolha dentro de outra; as diretivas antecipadas,
    uma cláusula «SE» dentro de outra; a partilha, duas escolhas «ATO» com
    opções diferentes. O leitor dos modelos não as alcança: a tela não as
    oferece e o teor guarda o marcador. As minutas de fábrica foram consertadas
    no LD02, mas a casa que as personalizou antes guarda a marcação antiga — e
    para ela a trava da lavratura continua valendo
    (`notas_teor.marcas_de_modelo_sobrando`): o ato não ocupa folha (CN-MA
    art. 795, § 2º)."""
    b = balcao
    caso = _caso(minuta)
    _a_minuta_de_antes_ajustada_pela_casa(b, minuta)
    item = "FAIXA" if caso.item == "FAIXA" else caso.item
    protocolo = abrir_protocolo_pago(b, [(item, 1)], base_da_faixa=caso.valor)
    ato_id = preparar_o_ato(b, caso, protocolo, aceita_pendencia=True)
    recado = lancar_no_livro(b, ato_id, item=protocolo["itens"][0]["codigo_ato"])
    assert "Ato NÃO lançado" in recado and marca in recado, recado
    a = ato(b, ato_id)
    assert a["situacao"] == "EM_LAVRATURA" and not a["livro"] and not a["selo"]


def test_o_tipo_da_cesdi_nasce_com_a_escritura_aberta_pela_minuta(balcao):
    """Como o tipo do RCTO nasce com o testamento (LG04): o divórcio aberto
    pela minuta já vai à CESDI, e a trava da CEP não pede a natureza de um
    ato que não vai à CEP."""
    import notas_modelos as NM
    b = balcao
    for minuta in ("NT-ESC-DIVORCIO", "NT-ESC-INVENTARIO-PARTILHA"):
        ato_id = abrir_o_ato(b, minuta, interessado="MARIO EXEMPLO DOS SANTOS")
        assert ato(b, ato_id)["tipo_cesdi"] == NM.por_codigo(minuta)["tipo_cesdi"]
    ato_id = abrir_o_ato(b, "NT-ESC-COMPRA-VENDA", interessado="MARIO EXEMPLO DOS SANTOS")
    assert ato(b, ato_id)["tipo_cesdi"] is None


# ================================================================ os atos de balcão
#
# Os atos de BALCÃO das Notas, do protocolo ao papel — LT02, 20/10/2026.
#
#     «quero que seja possível do protocolo à certidão. Minha maior preocupação
#      é que TODOS os atos precisam ter uma certidão adequada» — o oficial.
#
# O ato de balcão não vai a livro: o papel que sai dele (a etiqueta colada no
# documento, a ficha do cartão, o termo de comparecimento) É o ato no mundo.
# Por isso aqui a régua é o PAPEL: espécie, nome, quem praticou, data e lugar,
# selo com número e consulta, emolumentos — e nada de «None», marcador de
# modelo ou texto repetido. Certidão destes atos o sistema não emite, e o
# art. 851 do Código de Normas do MA (certidão é cópia de escrito em LIVRO ou
# ARQUIVO) não a exige: o inventário diz isso, e não se inventa xfail.
#
# O caminho é o do escrevente (USER), pelas telas, com a trava do selo pago
# LIGADA: protocolo, item pela tabela, caixa aberto, quitado, protocolo em
# atendimento; o ato; o selo, que gasta a unidade do item.
#
# Os ajudantes e a bancada (`balcao`) são os de cima.
HOJE = date.today()
HOJE_BR = HOJE.strftime("%d/%m/%Y")

# A qualificação de quem abre o cartão — fictícia, como as pessoas da bancada.
QUALIFICACAO_DO_CARTAO = {
    "tipo_pessoa": "F", "rg": "1234567", "rg_orgao": "SSP",
    "nascimento": "1980-05-04", "nacionalidade": "brasileira",
    "estado_civil": "solteiro", "profissao": "comerciante",
    "pai": "PAI DE EXEMPLO", "mae": "MAE DE EXEMPLO",
    "endereco": "Rua Exemplo", "endereco_numero": "10", "bairro": "Centro",
    "cidade": CIDADE, "uf": "MA", "cep": "65000-000",
}


# ================================================================ ajudantes


def _usado(b, protocolo: dict, codigo_tj: str) -> int:
    """Quantas unidades do item `codigo_tj` do protocolo o selo gastou."""
    linha = _um(b, """SELECT coalesce(sum(quantidade_usada), 0)::int AS n
                        FROM cx_protocolo_atos
                       WHERE protocolo_id = %s AND codigo_ato = %s""",
                (protocolo["id"], codigo_tj))
    return int(linha["n"])


def _selos_do_razao(b, tabela: str, ato_id: int) -> list[str]:
    return [r["numero"] for r in _ler(
        b, "SELECT numero FROM sd_selos WHERE tabela = %s AND ato_id = %s "
           "ORDER BY id", (tabela, int(ato_id)))]


def _etiqueta(html: str) -> str:
    """Só a tira: o que vai à térmica, sem a barra, o aviso e o script."""
    inicio = html.index('<div class="etiqueta">')
    fim = html.index('<div class="aviso">', inicio)
    return _so_texto(html[inicio:fim])


def _valores_da_tira(html: str) -> str:
    achado = re.search(r'<div class="valores">(.*?)</div>', html, re.S)
    return _so_texto(achado.group(1)) if achado else ""


def abrir_cartao(b, nome: str) -> int:
    """«Abrir cartão», pela tela, com a qualificação inteira."""
    r = _postar(b, "/notas/cartoes",
                {"acao": "novo", "nome": nome, "documento": PESSOAS[nome],
                 **QUALIFICACAO_DO_CARTAO},
                seguir=False)
    assert r.status_code == 302, f"o cartão não abriu ({r.status_code})"
    achado = re.search(r"/notas/cartoes/(\d+)$", r.headers["Location"])
    assert achado, ("o cartão não abriu: "
                    + " ".join(_flashes(b["cliente"].get(
                        r.headers["Location"]).get_data(as_text=True))))
    return int(achado.group(1))


def reconhecer(b, cartoes: list[int], especie: str, **extra) -> int:
    dados = {"acao": "reconhecer", "cartao_id": [str(c) for c in cartoes],
             "especie": especie, **extra}
    r = _postar(b, "/notas/reconhecimento", dados, seguir=False)
    destino = r.headers.get("Location", "")
    achado = re.search(r"/notas/reconhecimento/(\d+)$", destino)
    assert achado, ("o reconhecimento não foi lavrado: "
                    + " ".join(_flashes(b["cliente"].get(destino or "/").get_data(
                        as_text=True))))
    return int(achado.group(1))


def etiqueta_do_reconhecimento(b, rid: int) -> str:
    r = _postar(b, f"/notas/reconhecimento/{rid}/etiqueta", {},
                de=f"/notas/reconhecimento/{rid}")
    assert r.status_code == 200, f"a etiqueta não saiu ({r.status_code})"
    return r.get_data(as_text=True)


def _o_papel_de_balcao_e_adequado(tira: str, html: str, *, selo: str,
                                  quem: list[str]) -> None:
    """A régua comum da etiqueta (CN-MA arts. 87, XVI; 131; 132; 861 §10)."""
    for nome in quem:
        assert nome.upper() in tira.upper(), f"«{nome}» não está na etiqueta"
    assert ESCREVENTE in tira, "quem praticou o ato não está na etiqueta (art. 861 §10)"
    assert HOJE_BR in tira, "a etiqueta não traz a data do ato"
    assert CIDADE.upper() in tira.upper(), "a etiqueta não traz o lugar do ato"
    assert selo in tira, "o número do selo não está na etiqueta (art. 131)"
    assert "selo.tjma.jus.br" in tira, "a etiqueta não diz onde se consulta o selo"
    assert "<svg" in html.split('<div class="etiqueta">', 1)[1], (
        "a etiqueta saiu sem o QR da consulta (art. 132)")
    valores = _valores_da_tira(html)
    assert "Total R$" in valores and "Emol R$" in valores, (
        f"a etiqueta não traz os emolumentos que o selo declara (art. 87, XVI): "
        f"{valores!r}")
    assert _defeitos_de_texto(tira) == []


# ====================================================== 1. o cartão de firma


def test_o_cartao_de_firma_abre_pago_selado_e_a_ficha_traz_o_que_o_art_864_pede(balcao):
    """Abrir o cartão é ato com selo próprio (13.17.1, «selo de abertura de
    firma-cadastro» — CN-MA art. 864, caput) e a ficha é o papel contra o qual
    toda firma se confere depois: numeração crescente, nome da serventia,
    nome, endereço, profissão, estado civil, nascimento, CPF e identidade
    (art. 864 §1º, I a IV), e o selo com o que ele declara."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.17.1", 1)])
    nome = "MARIO EXEMPLO DOS SANTOS"
    cid = abrir_cartao(b, nome)

    cartao = _um(b, "SELECT * FROM nt_cartoes WHERE id = %s", (cid,))
    assert cartao["selo_abertura"], "o cartão abriu sem o selo de abertura"
    assert _selos_do_razao(b, "nt_cartoes", cid) == [cartao["selo_abertura"]]
    assert _usado(b, protocolo, "13.17.1") == 1, "o selo não gastou o item pago"

    odt = b["cliente"].get(f"/notas/cartoes/{cid}/ficha")
    assert odt.status_code == 200, f"a ficha não saiu ({odt.status_code})"
    ficha = _texto_do_odt(odt.data)
    assert f"Ficha nº {cid}" in ficha, "a ficha sai sem a numeração (art. 864 §1º, I)"
    assert SERVENTIA["unit_name"] in ficha, "a ficha não traz a serventia (§1º, II)"
    for valor in (nome, "Rua Exemplo, 10", "comerciante", "solteiro",
                  "04/05/1980", "00000000191", "1234567 SSP",
                  "PAI DE EXEMPLO e MAE DE EXEMPLO"):
        assert valor in ficha, f"a ficha não traz «{valor}» (art. 864 §1º, III e IV)"
    assert "SELO DE ABERTURA" in ficha and cartao["selo_abertura"] in ficha
    assert "Total R$" in ficha and "Emol R$" in ficha, (
        "a ficha não traz os emolumentos do selo de abertura (art. 87, XVI)")
    assert any("qr" in n for n in _imagens_do_odt(odt.data)), "a ficha saiu sem o QR"
    assert _defeitos_de_texto(ficha) == []


def test_a_ficha_do_cartao_traz_a_data_de_emissao_da_identidade(balcao):
    """O RG «junto com a data de emissão» (CN-MA art. 864 §1º, IV): o
    formulário de abrir cartão pergunta, `notas_partes.criar_cartao` grava em
    `rg_emissao` e a ficha a imprime como data de papel — até o LD02
    (21/10/2026) nenhum dos três o fazia."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 1)])
    r = _postar(b, "/notas/cartoes",
                {"acao": "novo", "nome": "MARIO EXEMPLO DOS SANTOS",
                 "documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 "rg_emissao": "2001-02-03", **QUALIFICACAO_DO_CARTAO},
                seguir=False)
    cid = int(re.search(r"/notas/cartoes/(\d+)$", r.headers["Location"]).group(1))
    ficha = _texto_do_odt(b["cliente"].get(f"/notas/cartoes/{cid}/ficha").data)
    assert "03/02/2001" in ficha


def test_a_ficha_do_cartao_traz_quem_verificou_o_preenchimento(balcao):
    """«nome, assinatura e carimbo do tabelião ou do seu substituto ou outro
    preposto designado que verificou a regularidade do preenchimento» (CN-MA
    art. 864, § 1º, VI).

    Era `xfail` do LT02: a ficha não dizia quem conferiu, pela decisão de
    31/08/2026 («o oficial não assina a ficha, só o cliente»). Perguntado
    (LD02/LD07), o oficial respondeu em 21/10/2026: «9 b» — ao pé da ficha,
    «Preenchimento conferido por: NOME — função», com a linha da assinatura e
    o espaço do carimbo, DO ESCREVENTE QUE ABRIU O CARTÃO (LH13). O cartão
    aberto pela tela grava quem estava logado, e a ficha o imprime."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 1)])
    cid = abrir_cartao(b, "MARIO EXEMPLO DOS SANTOS")
    cartao = _um(b, "SELECT conferente_nome, conferente_funcao FROM nt_cartoes "
                    "WHERE id = %s", (cid,))
    # o escrevente não tem função cadastrada: vale a da serventia (`usuario_funcao`)
    assert cartao == {"conferente_nome": ESCREVENTE, "conferente_funcao": "Escrevente"}
    ficha = _texto_do_odt(b["cliente"].get(f"/notas/cartoes/{cid}/ficha").data)
    assert f"Preenchimento conferido por: {ESCREVENTE} — Escrevente" in ficha, (
        "a ficha não diz quem verificou (art. 864 §1º, VI)")
    assert "assinatura e carimbo de quem conferiu o preenchimento" in ficha
    # e o cliente continua assinando só os autógrafos e o fecho dele
    assert "o titular do cartão" in ficha


# ======================================== 2 e 3. o reconhecimento de firma


@pytest.mark.parametrize("especie,frase", [
    ("SEMELHANCA", "POR SEMELHANÇA"),
    ("AUTENTICIDADE", "POR AUTENTICIDADE"),
])
def test_o_reconhecimento_de_firma_sela_pago_e_a_etiqueta_diz_a_especie(
        balcao, especie, frase):
    """A etiqueta é o ato colado no documento: diz a ESPÉCIE e o NOME, sem
    «supra» nem «retro» (CN-MA art. 861 §5º), quem reconheceu (§10), a data,
    o selo com a consulta (arts. 131 e 132) e os emolumentos (art. 87, XVI).
    Um selo por firma, 13.17.2 — o item que o protocolo pago cobre."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.17.1", 1), ("13.17.2", 1)])
    nome = "JOANA EXEMPLO DA SILVA"
    cid = abrir_cartao(b, nome)
    rid = reconhecer(b, [cid], especie)

    ato = _um(b, "SELECT * FROM nt_reconhecimentos WHERE id = %s", (rid,))
    assert ato["especie"] == especie and ato["selo"]
    assert ato["oficial"] == ESCREVENTE
    assert _selos_do_razao(b, "nt_reconhecimentos", rid) == [ato["selo"]]
    assert _usado(b, protocolo, "13.17.2") == 1, "o selo não gastou o item pago"

    html = etiqueta_do_reconhecimento(b, rid)
    tira = _etiqueta(html)
    assert frase in tira.upper(), f"a etiqueta não diz a espécie «{frase}» (art. 861 §5º)"
    _o_papel_de_balcao_e_adequado(tira, html, selo=ato["selo"], quem=[nome])


def test_o_termo_de_comparecimento_da_autenticidade_traz_nome_documento_selo_e_data(balcao):
    """Na autenticidade a pessoa assina na frente do tabelião, e o termo de
    presença registra isso: nome, documento de identificação, o número do
    selo do reconhecimento, a data do comparecimento e a assinatura do
    interessado (CN-MA art. 866)."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 1), ("13.17.2", 1)])
    nome = "JOANA EXEMPLO DA SILVA"
    rid = reconhecer(b, [abrir_cartao(b, nome)], "AUTENTICIDADE",
                     documento_descricao="contrato particular de exemplo")
    ato = _um(b, "SELECT selo FROM nt_reconhecimentos WHERE id = %s", (rid,))
    parte = _um(b, "SELECT id FROM nt_reconhecimento_partes "
                   "WHERE reconhecimento_id = %s ORDER BY id", (rid,))
    r = _postar(b, f"/notas/reconhecimento/{rid}/termo-comparecimento/{parte['id']}",
                {}, de=f"/notas/reconhecimento/{rid}")
    assert r.status_code == 200, f"o termo não saiu ({r.status_code})"
    termo = _texto_do_odt(r.data)
    assert "TERMO DE COMPARECIMENTO" in termo
    assert SERVENTIA["unit_name"] in termo, "o termo não identifica a serventia"
    assert termo.count(nome) >= 2, "o termo não traz o nome e a linha de quem assina"
    assert "00000000272" in termo, "o termo não traz o documento (art. 866)"
    assert ato["selo"] in termo, "o termo não traz o número do selo (art. 866)"
    assert "autenticidade" in termo.lower()
    assert "contrato particular de exemplo" in termo
    assert str(HOJE.year) in termo, "o termo não traz a data do comparecimento"
    assert ESCREVENTE in termo, "o termo não traz quem o lavrou"
    assert _defeitos_de_texto(termo) == []
    presenca = _um(b, "SELECT * FROM nt_presencas WHERE reconhecimento_id = %s",
                   (rid,))
    assert presenca and presenca["selo"] == ato["selo"]


def test_o_termo_de_presenca_tem_numero_de_ordem(balcao):
    """O termo de presença «conterá a ordem, o nome, o documento…» (CN-MA art.
    866). Até o LD02 (21/10/2026) `nt_presencas.ordem` nascia nula e o modelo
    não tinha o claro."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 1), ("13.17.2", 1)])
    rid = reconhecer(b, [abrir_cartao(b, "JOANA EXEMPLO DA SILVA")], "AUTENTICIDADE")
    parte = _um(b, "SELECT id FROM nt_reconhecimento_partes "
                   "WHERE reconhecimento_id = %s ORDER BY id", (rid,))
    _postar(b, f"/notas/reconhecimento/{rid}/termo-comparecimento/{parte['id']}",
            {}, de=f"/notas/reconhecimento/{rid}")
    presenca = _um(b, "SELECT ordem FROM nt_presencas WHERE reconhecimento_id = %s",
                   (rid,))
    assert presenca["ordem"] is not None, "a presença não tem número de ordem"


def test_o_termo_de_presenca_de_cada_firma_traz_o_selo_dela(balcao):
    """Com duas firmas no mesmo reconhecimento, o termo de cada pessoa traz «a
    numeração do selo de reconhecimento de firma utilizado» (CN-MA art. 866) —
    o dela, de `nt_reconhecimento_partes.selo`. Até o LD02 (21/10/2026) o da
    segunda saía com o selo da primeira."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 2), ("13.17.2", 2)])
    cartoes = [abrir_cartao(b, n) for n in ("JOANA EXEMPLO DA SILVA",
                                            "MARIO EXEMPLO DOS SANTOS")]
    rid = reconhecer(b, cartoes, "AUTENTICIDADE")
    partes = _ler(b, "SELECT id, selo FROM nt_reconhecimento_partes "
                     "WHERE reconhecimento_id = %s ORDER BY id", (rid,))
    assert len(partes) == 2 and partes[0]["selo"] != partes[1]["selo"]
    segunda = partes[1]
    r = _postar(b, f"/notas/reconhecimento/{rid}/termo-comparecimento/{segunda['id']}",
                {}, de=f"/notas/reconhecimento/{rid}")
    assert segunda["selo"] in _texto_do_odt(r.data)


def test_o_reconhecimento_no_documento_de_veiculo_e_por_autenticidade_e_cobra_o_13_17_3(balcao):
    """Firma em CRV/ATPV de transferência de veículo se reconhece por
    AUTENTICIDADE (CN-MA art. 865, II), e o item é o próprio da tabela de
    2026: 13.17.3 («em documento de transferência…»)."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.17.1", 1), ("13.17.3", 1)])
    nome = "MARIO EXEMPLO DOS SANTOS"
    rid = reconhecer(b, [abrir_cartao(b, nome)], "AUTENTICIDADE", veiculo="1",
                     veiculo_documento="CRV", veiculo_placa="ABC1D23")
    ato = _um(b, "SELECT * FROM nt_reconhecimentos WHERE id = %s", (rid,))
    assert ato["selo"] and ato["veiculo_placa"] == "ABC1D23"
    assert _usado(b, protocolo, "13.17.3") == 1, "o selo não gastou o 13.17.3 pago"
    html = etiqueta_do_reconhecimento(b, rid)
    tira = _etiqueta(html)
    assert "POR AUTENTICIDADE" in tira.upper()
    _o_papel_de_balcao_e_adequado(tira, html, selo=ato["selo"], quem=[nome])


# ===================================================== 4. o sinal público


def _reconhecer_sinal(b) -> tuple[int, dict]:
    protocolo = abrir_protocolo_pago(b, [("13.17.2", 1)])
    titular = "ANA EXEMPLO HERDEIRA"
    r = _postar(b, "/notas/sinais",
                {"acao": "novo", "titular": titular,
                 "documento": PESSOAS[titular], "origem": "CNSIP"},
                de="/notas/sinais", seguir=False,
                arquivos={"pdf": (__import__("io").BytesIO(
                    b"%PDF-1.4\n% sinal de exemplo\n%%EOF\n"), "sinal.pdf")})
    sid = int(re.search(r"/notas/sinais/(\d+)$", r.headers["Location"]).group(1))
    r = _postar(b, "/notas/sinais/reconhecimento",
                {"acao": "reconhecer", "sinal_id": str(sid),
                 "documento_descricao": "certidão de exemplo"}, seguir=False)
    destino = r.headers.get("Location", "")
    achado = re.search(r"/notas/sinais/reconhecimento/(\d+)$", destino)
    assert achado, ("o sinal não foi reconhecido: " + " ".join(_flashes(
        b["cliente"].get(destino or "/").get_data(as_text=True))))
    return int(achado.group(1)), protocolo


def test_o_reconhecimento_de_sinal_publico_sela_pago_pelo_item_da_firma(balcao):
    """O sinal público se reconhece como firma, com o selo do reconhecimento
    de firma (CN-MA art. 874 e §1º): 13.17.2, pago no protocolo."""
    b = balcao
    rid, protocolo = _reconhecer_sinal(b)
    ato = _um(b, "SELECT * FROM nt_sinais_reconhecimentos WHERE id = %s", (rid,))
    assert ato["selo"], "o reconhecimento do sinal ficou sem selo"
    assert ato["oficial"] == ESCREVENTE
    assert "ANA EXEMPLO HERDEIRA" in ato["texto"]
    assert _usado(b, protocolo, "13.17.2") == 1, "o selo não gastou o item pago"
    tela = _tela(b, f"/notas/sinais/reconhecimento/{rid}")
    assert ato["selo"] in tela


def test_o_reconhecimento_de_sinal_publico_imprime_a_etiqueta_com_o_selo(balcao):
    """O sinal público reconhecido sai com papel: a etiqueta, com o selo (CN-MA
    art. 131: o selo «deverá constar expressamente no corpo do ato físico»;
    art. 874). Até o LD02 (21/10/2026) a ficha só mostrava o ato na tela."""
    b = balcao
    rid, _ = _reconhecer_sinal(b)
    ato = _um(b, "SELECT selo FROM nt_sinais_reconhecimentos WHERE id = %s", (rid,))
    tela = _tela(b, f"/notas/sinais/reconhecimento/{rid}")
    achado = re.search(r'action="([^"]*etiqueta[^"]*)"', tela)
    assert achado, "a ficha do reconhecimento do sinal não oferece etiqueta"
    r = _postar(b, achado.group(1), {}, de=f"/notas/sinais/reconhecimento/{rid}")
    assert r.status_code == 200 and ato["selo"] in r.get_data(as_text=True)


# ============================================ 5 e 6. a autenticação de cópia


ENDERECO_CONFERIDO = "https://servicos.exemplo.gov.br/certidao/000001"


def _autenticar(b, *, folhas: int, tipo: str = "PADRAO") -> tuple[int, dict]:
    protocolo = abrir_protocolo_pago(b, [("13.18", folhas)])
    antes = _um(b, "SELECT coalesce(max(id), 0) AS n FROM nt_autenticacoes")["n"]
    dados = {"acao": "autenticar", "folhas": str(folhas), "tipo": tipo,
             "documento_tipo": "Certidão",
             "documento_descricao": "certidão de exemplo",
             "apresentante": "MARIO EXEMPLO DOS SANTOS",
             "apresentante_documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"]}
    if tipo == "INTERNET":
        # O documento da internet só se autentica conferido no endereço dele,
        # que o balcão informa (CN-MA art. 839 e § 1º) — a tela o pede desde o
        # LD02, e até lá este caminho não o mandava porque não havia onde.
        dados["endereco_eletronico"] = ENDERECO_CONFERIDO
    html = _postar(b, "/notas/autenticacao", dados).get_data(as_text=True)
    nova = _um(b, "SELECT id FROM nt_autenticacoes WHERE id > %s ORDER BY id",
               (antes,))
    assert nova, "a autenticação não foi lavrada: " + " ".join(_flashes(html))
    return int(nova["id"]), protocolo


def etiqueta_da_autenticacao(b, aid: int) -> str:
    r = _postar(b, f"/notas/autenticacao/{aid}/etiqueta", {},
                de="/notas/autenticacao")
    assert r.status_code == 200, f"a etiqueta não saiu ({r.status_code})"
    return r.get_data(as_text=True)


@pytest.mark.parametrize("tipo,frase", [
    ("PADRAO", "AUTENTICO E DOU FÉ QUE A CÓPIA É A REPRODUÇÃO FIEL"),
    ("INTERNET", "DOCUMENTOS EXPEDIDOS ATRAVÉS DA INTERNET"),
])
def test_a_autenticacao_de_uma_folha_sela_pago_e_a_etiqueta_e_adequada(
        balcao, tipo, frase):
    """Uma folha, um selo do 13.18 («por página»), pago no protocolo; a
    etiqueta declara a conferência com o original (CN-MA art. 836), quem
    autenticou, a data, o selo e os emolumentos."""
    b = balcao
    aid, protocolo = _autenticar(b, folhas=1, tipo=tipo)
    ato = _um(b, "SELECT * FROM nt_autenticacoes WHERE id = %s", (aid,))
    assert ato["selo"] and ato["oficial"] == ESCREVENTE
    assert _selos_do_razao(b, "nt_autenticacoes", aid) == [ato["selo"]]
    assert _usado(b, protocolo, "13.18") == 1, "o selo não gastou o item pago"
    html = etiqueta_da_autenticacao(b, aid)
    tira = _etiqueta(html)
    assert frase in tira, f"a etiqueta não traz a fórmula da autenticação ({tipo})"
    _o_papel_de_balcao_e_adequado(tira, html, selo=ato["selo"], quem=[])


def test_a_autenticacao_de_duas_folhas_sela_e_cobra_uma_vez_por_folha(balcao):
    """O 13.18 é por página: duas folhas, dois selos, duas unidades do item
    pago (CN-MA art. 842 — cada documento, a sua autenticação)."""
    b = balcao
    aid, protocolo = _autenticar(b, folhas=2)
    selos = _selos_do_razao(b, "nt_autenticacoes", aid)
    assert len(selos) == 2 and len(set(selos)) == 2, selos
    assert _usado(b, protocolo, "13.18") == 2


def test_cada_folha_autenticada_leva_o_seu_selo_no_papel(balcao):
    """Duas folhas, dois selos, duas tiras — cada folha com o seu selo no
    papel (CN-MA art. 131: o selo «deverá constar expressamente no corpo do ato
    físico»; art. 842). Até o LD02 (21/10/2026) a etiqueta imprimia só o
    primeiro."""
    b = balcao
    aid, _ = _autenticar(b, folhas=2)
    selos = _selos_do_razao(b, "nt_autenticacoes", aid)
    tira = _etiqueta(etiqueta_da_autenticacao(b, aid))
    assert all(s in tira for s in selos), f"a etiqueta não traz todos os selos {selos}"


def test_cada_firma_reconhecida_leva_o_seu_selo_na_etiqueta(balcao):
    """Duas firmas, dois selos, duas tiras — cada firma com o seu selo, de
    `nt_reconhecimento_partes.selo` (CN-MA art. 131). Até o LD02 (21/10/2026)
    a etiqueta imprimia só o do ato, que é o da primeira."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 2), ("13.17.2", 2)])
    cartoes = [abrir_cartao(b, n) for n in ("JOANA EXEMPLO DA SILVA",
                                            "MARIO EXEMPLO DOS SANTOS")]
    rid = reconhecer(b, cartoes, "SEMELHANCA")
    selos = _selos_do_razao(b, "nt_reconhecimentos", rid)
    assert len(selos) == 2
    tira = _etiqueta(etiqueta_do_reconhecimento(b, rid))
    assert all(s in tira for s in selos), f"a etiqueta não traz todos os selos {selos}"


def test_a_autenticacao_da_internet_diz_o_endereco_a_data_e_a_hora_da_conferencia(balcao):
    """«A autenticação mencionará o endereço eletrônico de acesso, a data e o
    horário da conferência» (CN-MA art. 839 §1º). Até o LD02 (21/10/2026) a
    tela não perguntava o endereço e o papel não tinha os claros."""
    b = balcao
    aid, _ = _autenticar(b, folhas=1, tipo="INTERNET")
    ato = _um(b, "SELECT hora FROM nt_autenticacoes WHERE id = %s", (aid,))
    tira = _etiqueta(etiqueta_da_autenticacao(b, aid))
    assert "http" in tira.lower(), "a autenticação não diz o endereço eletrônico"
    assert ato["hora"][:5] in tira, "a autenticação não diz o horário da conferência"


# ======================================================== 7. a pública forma


def _emitir_publica_forma(b) -> tuple[int, dict]:
    from conftest import cg_login
    oficial = b["app"].test_client()
    cg_login(oficial, "oficial", SENHA)
    tela = oficial.get("/notas/publica-forma/configuracao").get_data(as_text=True)
    oficial.post("/notas/publica-forma/configuracao",
                 data={"codigo_tj": "13.18", "csrf_token": _token(tela)})
    protocolo = abrir_protocolo_pago(b, [("13.18", 1)])
    r = _postar(b, "/notas/publica-forma/emitir",
                {"documento_especie": "Certidão de nascimento",
                 "documento_descricao": "segunda via de exemplo",
                 "documento_expedidor": "Ofício de exemplo",
                 "apresentante": "MARIO EXEMPLO DOS SANTOS",
                 "apresentante_documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 "transcricao": "TEXTO DO DOCUMENTO DE EXEMPLO, TRANSCRITO NA ÍNTEGRA.",
                 "folhas": "1"},
                de="/notas/publica-forma", seguir=False)
    destino = r.headers.get("Location", "")
    achado = re.search(r"/notas/publica-forma/(\d+)$", destino)
    assert achado, ("a pública forma não foi emitida: " + " ".join(_flashes(
        b["cliente"].get(destino or "/").get_data(as_text=True))))
    return int(achado.group(1)), protocolo


def test_a_publica_forma_numera_sela_pago_e_congela_o_teor(balcao):
    """A pública forma é a cópia transcrita do original, com fé pública
    (CN-MA art. 849): número do exercício, teor congelado com o hash, o selo
    pelo item que a casa configurou, pago no protocolo."""
    b = balcao
    pf_id, protocolo = _emitir_publica_forma(b)
    pf = _um(b, "SELECT * FROM nt_publicas_formas WHERE id = %s", (pf_id,))
    assert pf["situacao"] == "EMITIDA" and pf["selo"], (pf["situacao"],
                                                       pf["motivo_suspensao"])
    assert pf["numero"] == 1 and pf["ano"] == HOJE.year
    assert _usado(b, protocolo, "13.18") == 1, "o selo não gastou o item pago"
    teor = _so_texto(pf["teor"])
    for valor in (f"PÚBLICA FORMA n. 1/{HOJE.year}", "CERTIFICO",
                  "MARIO EXEMPLO DOS SANTOS", "certidão de nascimento",
                  "TEXTO DO DOCUMENTO DE EXEMPLO", "dou fé"):
        assert valor in teor, f"o teor da pública forma não traz «{valor}»"
    assert _defeitos_de_texto(teor) == []
    assert pf["selo"] in _tela(b, f"/notas/publica-forma/{pf_id}")


def test_a_publica_forma_imprime_o_papel_com_serventia_data_selo_e_assinatura(balcao):
    """A pública forma tem papel: a serventia, o selo com os emolumentos e quem
    a expede, juntos num .odt/PDF (CN-MA art. 131: selo no corpo do ato físico;
    arts. 849 a 851). Até o LD02 (21/10/2026) só havia a tela do sistema."""
    b = balcao
    pf_id, _ = _emitir_publica_forma(b)
    pf = _um(b, "SELECT selo FROM nt_publicas_formas WHERE id = %s", (pf_id,))
    r = b["cliente"].get(f"/notas/publica-forma/{pf_id}/odt?formato=odt")
    assert r.status_code == 200, "a pública forma não tem papel para imprimir"
    papel = _texto_do_odt(r.data) + " " + _texto_do_odt(r.data, cabecalho=True)
    for valor in (SERVENTIA["unit_name"], pf["selo"], ESCREVENTE, "Total R$"):
        assert valor in papel


# ================================== 8. a comunicação de venda de veículo


def test_a_comunicacao_de_venda_de_veiculo_sela_pago_antes_de_comunicar(balcao):
    """Sem selo nada se comunica: o 13.22 («comunicação eletrônica de
    transferência de veículo») sai primeiro, pago no protocolo; com a
    integração desligada, a comunicação fica registrada com o protocolo do
    portal do DETRAN."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.22", 1)])
    r = _postar(b, "/notas/veiculos/nova",
                {"documento": "ATPV_E", "placa": "ABC1D23",
                 "renavam": "00639884962",
                 "vendedor_nome": "MARIO EXEMPLO DOS SANTOS",
                 "vendedor_documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 "comprador_nome": "JOANA EXEMPLO DA SILVA",
                 "comprador_documento": PESSOAS["JOANA EXEMPLO DA SILVA"],
                 "data_venda": HOJE.isoformat(), "valor": "25.000,00",
                 "municipio": CIDADE, "uf": "MA"},
                de="/notas/veiculos", seguir=False)
    destino = r.headers.get("Location", "")
    achado = re.search(r"/notas/veiculos/(\d+)$", destino)
    assert achado, ("a comunicação não foi registrada: " + " ".join(_flashes(
        b["cliente"].get(destino or "/").get_data(as_text=True))))
    com_id = int(achado.group(1))
    html = _postar(b, f"/notas/veiculos/{com_id}/comunicar",
                   {"protocolo": "PORTAL-EXEMPLO-0001"},
                   de=f"/notas/veiculos/{com_id}").get_data(as_text=True)
    com = _um(b, "SELECT * FROM nt_comunicacoes_veiculo WHERE id = %s", (com_id,))
    assert com["selo"], "a comunicação ficou sem selo: " + " ".join(_flashes(html))
    assert com["situacao"] == "COMUNICADA_A_MAO"
    assert _selos_do_razao(b, "nt_comunicacoes_veiculo", com_id) == [com["selo"]]
    assert _usado(b, protocolo, "13.22") == 1, "o selo não gastou o item pago"
    assert com["selo"] in _tela(b, f"/notas/veiculos/{com_id}")


# ========================================== a anotação à margem, na certidão


def test_a_revogacao_anota_a_procuracao_e_a_certidao_dela_traz_a_margem(balcao):
    """A revogação lavrada aqui anota a procuração revogada, na mesma
    transação do lançamento, sem selo e sem ônus (CN-MA art. 831) — e a
    certidão e o traslado da procuração passam a dizê-lo: cópia FIDEDIGNA é a
    que traz a margem (Lei 8.935/1994, art. 6º, II; CN-MA art. 851).

    É o elo que faz a certidão dizer a verdade depois do ato seguinte; os
    testes de anotação de `test_notas_anotacoes.py` estão quase todos em
    `falhas_conhecidas.txt`, e este anda pelas telas inteiras.
    """
    b = balcao
    procuracao = _caso("NT-PROC-PUBLICA")
    protocolo = abrir_protocolo_pago(b, [("13.9.3", 2), ("13.12.1", 1)])
    proc_id, _item, recado = lavrar_pela_tela(b, procuracao, protocolo)
    assert ato(b, proc_id)["situacao"] == "LAVRADO", recado

    revogacao = _caso("NT-REVOGACAO-MANDATO")
    rev_id = preparar_o_ato(b, revogacao, protocolo)
    r = _postar(b, f"/notas/atos/{rev_id}",
                {"acao": "vincular_anterior", "anterior_id": str(proc_id)})
    assert "Vinculado ao ato do livro" in " ".join(_flashes(r.get_data(as_text=True)))
    recado = lancar_no_livro(b, rev_id, item="13.9.3", especie=revogacao.especie)
    assert ato(b, rev_id)["situacao"] == "LAVRADO", recado
    assert "Anotado à margem do ato anterior" in recado, recado

    p = ato(b, proc_id)
    assert p["situacao"] == "REVOGADO", "a procuração revogada continua «lavrada»"
    margem = _ler(b, "SELECT texto, selo FROM nt_ato_anotacoes WHERE ato_id = %s "
                     "ORDER BY id", (proc_id,))
    assert len(margem) == 1 and not margem[0]["selo"], (
        f"a anotação do art. 831 é sem selo: {margem}")
    rev = ato(b, rev_id)
    assert f"livro {rev['livro']}" in margem[0]["texto"].lower(), margem

    certidao_id = emitir_certidao(b, protocolo=protocolo, ato_id=proc_id,
                                  requerente="JOANA EXEMPLO DA SILVA")
    corpo = _texto_do_odt(o_papel_da_certidao(b, certidao_id))
    assert "ANOTAÇÕES À MARGEM" in corpo and "Nada mais consta à margem" not in corpo
    assert _sem_espaco_antes_da_pontuacao(" ".join(margem[0]["texto"].split())) in (
        _sem_espaco_antes_da_pontuacao(corpo)), "a certidão não traz a margem"
    traslado = _texto_do_odt(o_traslado(b, proc_id))
    assert "ANOTAÇÕES À MARGEM" in traslado, "o traslado não transcreve a margem"
