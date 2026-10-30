"""O RTD E O RCPJ, DO PROTOCOLO À CERTIDÃO — PELAS TELAS (LT05, 20/10/2026).

    «quero que seja possível do protocolo à certidão. Minha maior preocupação
     é que TODOS os atos precisam ter uma certidão adequada» — e depois:
     «TERMO E CERTIDÃO».                               — o oficial, 20/10/2026

CADA TESTE FAZ O QUE O BALCÃO FAZ, NA ORDEM EM QUE FAZ, E SÓ PELA TELA: o
cliente de teste do Flask entra com login e CSRF, abre o caixa, recebe o título
no Livro de Protocolo, lança e quita no protocolo o item da tabela, qualifica,
lavra e sela, imprime a etiqueta, gera o termo em PDF e, por fim, pede, paga,
emite e sela a certidão. O banco só se LÊ, para conferir o que a tela gravou; e
só se escreve no preparo — a tabela de emolumentos de 2026, que vem do acervo
(`tests/custas_reais.json`), como em `test_apostila`.

O SELADOR É O DA BANCADA (`selador_de_bancada`): servidor de verdade, com TLS,
numa porta local. E A TRAVA DO SELO PAGO ESTÁ LIGADA (`protocolo_pago=False`):
o selo só sai porque o protocolo foi quitado na tela do caixa e o escrevente o
marcou em atendimento (`/selo/cobertura/atender`). Sem o pagamento, o ato
ficaria sem selo e o teste cairia — que é o que se quer provar. O texto do selo
é o que o aparelho de verdade devolve (item, valores e consulta, na forma
medida em `tests/test_selo_no_papel.py`): sem ele a certidão não teria
emolumentos a declarar, e o teste mediria o boneco, e não o papel.

O QUE É «TERMO» AQUI. O RTD e o RCPJ lavram por trasladação (Lei 6.015/1973,
art. 142; CN-MA, art. 980): o termo é o PDF do ato (`rg_teor_rtdpj`) — o
cabeçalho da serventia, «CERTIFICO que me foi apresentado para ser
REGISTRADO/AVERBADO…», o documento digitalizado, o encerramento com quem
subscreve, a data e o selo no rodapé — e o texto que o livro guarda
(`rg_atos.teor`) é o que a certidão de inteiro teor reproduz. O PDF é imagem: o
texto dele se captura na montagem (`textos_prontos`, `montar_pagina`), que é o
que a rota de fato desenha.

A BASE: Lei 6.015/1973 (LRP); Código Nacional de Normas (Prov. CNJ 149/2023);
Código de Normas Extrajudicial do MA (Prov. COGEX 28/2026, «CN-MA»). O artigo
vai em cada teste. O que não coube consertar neste lote está
`xfail(strict=True, reason="DEFEITO: …")` e em `docs/COBERTURA_FLUXOS.md` — a
asserção diz o que a norma pede, e não o que o sistema faz hoje.

Dados fictícios (LGPD): nomes «DE EXEMPLO», CPF 000.000.001-91, CNPJ
00.000.043/0001-77, a serventia de exemplo dos testes (CNS 000000).
"""
from __future__ import annotations

import dataclasses
import html as HTML
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

from bd_nativo import banco  # noqa: E402
from conftest import cg_login  # noqa: E402
from navegador_de_teste import postar_e_seguir  # noqa: E402
import rg_registro as RG  # noqa: E402

SENHA = "Senha#12345"
OFICIAL = "FULANO DE EXEMPLO"            # o ADMIN que qualifica, lavra e assina
CONFERENTE = "BELTRANA DE EXEMPLO"       # quem só reimprime, noutro dia
FUNCAO = "Escrevente"                    # a função padrão da casa (usuário sem função)
SERVENTIA = "Ofício Único de Cidade Exemplo/MA"
CNS = "000000"
CPF = "00000000191"
CNPJ = "00000043000177"
CNPJ_FORMATADO = "00.000.043/0001-77"

REAIS = json.loads((RAIZ / "tests" / "custas_reais.json").read_text("utf-8"))
VIGENCIA_2026 = 10022
TABELA_15 = {e["tj"]: e for e in REAIS["valores_2026"]
             if str(e["tj"]).startswith("15.")}

MESES = ("janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro")


# ------------------------------------------------------------ o preparo


def _servico(tj: str) -> int:
    return int(TABELA_15[tj]["s"])


def _reais(v: float) -> str:
    c = int(round(v * 100))
    return f"{c // 100},{c % 100:02d}"


def _total(tj: str) -> str:
    e = TABELA_15[tj]
    return _reais(e["emol"] + e["ferc"] + e["femp"] + e["fadp"] + e["ferrfis"])


def _tabela_do_rtd_e_do_rcpj(db) -> None:
    """Os itens 15.x da tabela de 2026, como o caixa os importa."""
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio, fim,
                   importado_em)
               VALUES (%s, '2026', 1, '2026-01-01', NULL, '2026-08-21')
               ON CONFLICT (codigo) DO NOTHING""", (VIGENCIA_2026,))
        for tj, e in TABELA_15.items():
            bd.escrever(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                   VALUES (%s, %s, %s, 1) ON CONFLICT (codigo) DO NOTHING""",
                (int(e["s"]), tj, e["descricao"]))
            bd.escrever(
                """INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (servico, vigencia) DO NOTHING""",
                (int(e["s"]), VIGENCIA_2026, _reais(e["emol"]), _reais(e["ferc"]),
                 _reais(e["femp"]), _reais(e["fadp"]), _reais(e["ferrfis"]),
                 _total(tj)))


def _texto_do_aparelho(numero: str, dados: dict, agora: str) -> str:
    """O texto que o selador de verdade escreve: item, valores e consulta."""
    import ato_selado as AS
    codigo = AS.codigo_do_envelope(dados) or ""
    quando = f"{agora[8:10]}/{agora[5:7]}/{agora[:4]} {agora[11:19]}"
    texto = f"Poder Judiciario - TJMA. Selo: {numero}, {quando}, Ato: {codigo}"
    e = TABELA_15.get(codigo)
    if e:
        texto += (f", Total R$ {_total(codigo)} Emol R$ {_reais(e['emol'])} "
                  f"FERC R$ {_reais(e['ferc'])} FADEP R$ {_reais(e['fadp'])} "
                  f"FEMP R$ {_reais(e['femp'])}")
    return texto + " Consulte em https://selo.tjma.jus.br"


@pytest.fixture()
def casa(cg_casa, monkeypatch):
    db = cg_casa["db"]
    db.create_user("oficial", OFICIAL, SENHA, "ADMIN")
    db.create_user("conferente", CONFERENTE, SENHA, "MANAGER")
    db.set_settings({"serventia_titular": OFICIAL,
                     "serventia_endereco": "Rua de Exemplo, 1"})
    _tabela_do_rtd_e_do_rcpj(db)
    import selador_cliente as CL
    pedir_ao_aparelho = CL.selar

    def selar_com_o_texto_do_aparelho(con, pasta, caminho, dados, **kw):
        saida = []
        for selo in pedir_ao_aparelho(con, pasta, caminho, dados, **kw):
            texto = _texto_do_aparelho(selo.numero, dados, kw["agora"])
            banco(con).escrever("UPDATE sd_selos SET texto=%s WHERE numero=%s",
                                (texto, selo.numero))
            saida.append(dataclasses.replace(selo, texto=texto))
        return saida

    monkeypatch.setattr(CL, "selar", selar_com_o_texto_do_aparelho)
    from selador_de_bancada import ligar_o_selador
    with ligar_o_selador(cg_casa, protocolo_pago=False) as aparelho:
        cg_casa["selador"] = aparelho
        yield cg_casa


# ------------------------------------------------------ o que se lê da tela


def _token(c, url: str) -> str:
    html = c.get(url).get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, f"{url} não trouxe csrf_token"
    return achado.group(1)


def _sem_tags(html: str) -> str:
    return HTML.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", html))).strip()


def _avisos(resposta) -> str:
    return " | ".join(_sem_tags(x) for x in re.findall(
        r'class="flash[^"]*"[^>]*>(.*?)</', resposta.get_data(as_text=True), re.S))


def _odt(dados: bytes) -> tuple[str, list[str]]:
    """O texto do `.odt` (corpo e cabeçalho da página) e os nomes das imagens."""
    with zipfile.ZipFile(io.BytesIO(dados)) as z:
        texto = " ".join(_sem_tags(z.read(n).decode("utf-8"))
                         for n in ("styles.xml", "content.xml"))
        return texto, [n for n in z.namelist() if n.startswith("Pictures/")]


def _png() -> bytes:
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (600, 800), "white").save(buf, "PNG")
    return buf.getvalue()


def _extenso(iso: str) -> str:
    d = date.fromisoformat(str(iso)[:10])
    return f"{d.day} de {MESES[d.month - 1]} de {d.year}"


def _br(iso: str) -> str:
    s = str(iso)[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}"


class _Amanha(date):
    """O relógio do dia seguinte: a segunda via impressa amanhã."""

    @classmethod
    def today(cls):
        return date.today() + timedelta(days=1)


def _sem_sobra_de_modelo(texto: str, onde: str) -> None:
    """Termo e certidão sem campo vazio, «None» nem marcador sobrando."""
    assert "None" not in texto, f"{onde}: «None» no papel"
    assert "{" not in texto and "}" not in texto, f"{onde}: marcador de modelo sobrando"
    assert not re.search(r"(?<!\S)(?:nº|n\.|fls\.)\s*(?:,|\.|$)", texto), (
        f"{onde}: rótulo sem valor")


class Balcao:
    """O escrevente no balcão — só pela tela, com login e CSRF."""

    def __init__(self, casa, usuario: str = "oficial"):
        self.casa, self.db = casa, casa["db"]
        self.c = casa["app"].test_client()
        cg_login(self.c, usuario, SENHA)

    def post(self, url: str, de: str, **dados):
        return self.c.post(url, data={"csrf_token": _token(self.c, de), **dados},
                           follow_redirects=True)

    def um(self, sql: str, args=()):
        with self.db.connect() as con:
            return banco(con).um(sql, args)

    def ler(self, sql: str, args=()):
        with self.db.connect() as con:
            return banco(con).ler(sql, args)

    def abrir_caixa(self) -> None:
        r = self.post("/caixa", "/caixa", acao="abrir", saldo_inicial="0,00")
        assert "Caixa aberto" in _avisos(r)

    def pagar(self, protocolo_id: int, *codigos: str) -> str:
        """Lança os itens da tabela no protocolo, quita e passa a atendê-lo."""
        url = f"/caixa/protocolos/{protocolo_id}"
        for tj in codigos:
            r = self.post(f"{url}/itens", url, acao="acrescentar",
                          servico=str(_servico(tj)))
            assert f"Item {tj} acrescentado" in _avisos(r), _avisos(r)
        r = self.post(f"{url}/itens", url, acao="quitar_todos",
                      forma_pagamento="DINHEIRO")
        assert "lançado" in _avisos(r), _avisos(r)
        numero = self.um("SELECT numero FROM cx_protocolos WHERE id=%s",
                         (protocolo_id,))["numero"]
        r = self.post("/selo/cobertura/atender", "/caixa", protocolo=numero)
        assert "atendendo o protocolo" in _avisos(r), _avisos(r)
        return numero

    def protocolo(self, atribuicao: str, interessado: str, *codigos: str) -> int:
        """Um protocolo do balcão para o serviço seguinte, pago e em atendimento."""
        r = self.c.post("/caixa/protocolos", data={
            "csrf_token": _token(self.c, "/caixa/protocolos"), "acao": "novo",
            "interessado": interessado, "telefone": "(99) 0000-0000",
            "atribuicao": atribuicao, "assunto": "Pedido de exemplo"})
        assert r.status_code == 302, r.status_code
        pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
        self.pagar(pid, *codigos)
        return pid

    def receber_titulo(self, atribuicao: int, *, serie: str, natureza: str,
                       apresentante: str, documento: str, **extra) -> dict:
        url = f"/rcpj-rtd/titulos/novo?atribuicao={atribuicao}"
        r = self.post(url, url, atribuicao=str(atribuicao), apresentante=apresentante,
                      apresentante_documento=documento, natureza=natureza,
                      serie=serie, forma="PAPEL", **extra)
        assert "título recebido sob o protocolo" in _avisos(r), _avisos(r)
        return self.um("SELECT * FROM rg_titulos ORDER BY id DESC LIMIT 1")

    def qualificar(self, titulo_id: int, **dados):
        url = f"/rcpj-rtd/titulo/{titulo_id}"
        return self.post(f"{url}/qualificar", url, **dados)

    def termo_do_ato(self, ato_id: int, monkeypatch) -> dict:
        """O PDF do termo, e o texto que a rota desenhou nele."""
        import rg_teor_rtdpj as RGTEOR
        textos, faixas = [], []
        montar_textos, montar_pagina = RGTEOR.textos_prontos, RGTEOR.montar_pagina

        def textos_capturados(**kw):
            textos.append(montar_textos(**kw))
            return textos[-1]

        def pagina_capturada(src, **kw):
            faixas.append(kw)
            return montar_pagina(src, **kw)

        monkeypatch.setattr(RGTEOR, "textos_prontos", textos_capturados)
        monkeypatch.setattr(RGTEOR, "montar_pagina", pagina_capturada)
        r = self.c.get(f"/rcpj-rtd/ato/{ato_id}/teor")
        monkeypatch.setattr(RGTEOR, "textos_prontos", montar_textos)
        monkeypatch.setattr(RGTEOR, "montar_pagina", montar_pagina)
        return {"resposta": r, "textos": textos[-1] if textos else None,
                "ultima_pagina": faixas[-1] if faixas else None}

    def emitir_certidao(self, registro_id: int, atribuicao: str, *,
                        ato_ids=None) -> dict:
        """O cliente pede a certidão: protocolo pago do 15.10.1 e a emissão."""
        pid = self.protocolo(atribuicao, "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
        ficha = f"/rcpj-rtd/{registro_id}"
        dados = {"csrf_token": _token(self.c, ficha),
                 "requerente": "FULANA REQUERENTE DE EXEMPLO",
                 "requerente_documento": CPF, "finalidade": "prova",
                 "protocolo_id": str(pid)}
        if ato_ids is not None:
            dados["ato_id"] = [str(x) for x in ato_ids]
        r = self.c.post(f"/atribuicoes/certidoes/RCPJ_RTD/{registro_id}",
                        data=dados, follow_redirects=True)
        assert "emitida" in _avisos(r), _avisos(r)
        return self.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")

    def certidao_em_pdf(self, certidao_id: int, monkeypatch) -> dict:
        """O PDF da certidão (capa e folhas), e o que a rota mandou desenhar."""
        import rg_certidao_pdf as RGCERT
        chamadas = []
        gerar = RGCERT.gerar_pdf

        def gerar_capturado(**kw):
            chamadas.append(kw)
            return gerar(**kw)

        monkeypatch.setattr(RGCERT, "gerar_pdf", gerar_capturado)
        r = self.c.get(f"/atribuicoes/certidoes/{certidao_id}/imprimir")
        monkeypatch.setattr(RGCERT, "gerar_pdf", gerar)
        return {"resposta": r, "pedido": chamadas[-1] if chamadas else None}


def _campos_da_lista(serie: str, natureza: str) -> dict:
    """O que a tela do RCPJ passou a exigir (CN-MA 410/412/413, III).

    O RTD não declara. No RCPJ, a natureza que cai nos três artigos leva a
    lista apresentada, com referência de exemplo; o resto, «não se aplica»."""
    if serie not in RG.SERIES_RCPJ:
        return {}
    sugestao = RG.sugerir_enquadramento(natureza)
    if sugestao in ("ART410", "ART412", "ART413"):
        return {"enquadramento_cnma": sugestao, "lista_presenca": "APRESENTADA",
                "lista_presenca_ref": "Lista de presença de exemplo, folha 1"}
    return {"enquadramento_cnma": "NAO_SE_APLICA",
            "justificativa_cnma": "Ato fora dos arts. 410, 412 e 413 do CN-MA."}


def _lavrar_pelo_titulo(b: Balcao, *, atribuicao: int, serie: str, item: str,
                        natureza: str, apresentante: str, documento: str,
                        teor: str, declaracoes: dict | None = None) -> dict:
    """Do protocolo ao registro selado: o caminho comum aos cinco livros.

    `declaracoes` são as do termo do livro (LD09), digitadas nos campos que a
    ficha do título oferece — o teste confere que a tela os tem antes de
    mandar."""
    titulo = b.receber_titulo(atribuicao, serie=serie, natureza=natureza,
                              apresentante=apresentante, documento=documento)
    b.pagar(titulo["protocolo_geral_id"], item)
    r = b.qualificar(titulo["id"], resultado="POSITIVA",
                     fundamentacao="Título em ordem para registro.")
    assert "Qualificação positiva" in _avisos(r), _avisos(r)
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    campos = {f"declaracao_{claro}": valor
              for claro, valor in (declaracoes or {}).items()}
    if campos:
        ficha = b.c.get(url).get_data(as_text=True)
        for nome in campos:
            assert f'name="{nome}"' in ficha, f"a ficha do título não pergunta {nome}"
    etiqueta = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": serie, "teor": teor,
        "protocolo_id": str(titulo["protocolo_geral_id"]), **campos,
        **_campos_da_lista(serie, natureza)})
    ato = b.um("SELECT * FROM rg_atos ORDER BY id DESC LIMIT 1")
    registro = b.um("SELECT * FROM rg_registros WHERE id=%s", (ato["registro_id"],))
    # o documento trasladado, como o balcão o anexa na ficha do registro
    ficha = f"/rcpj-rtd/{registro['id']}"
    r = b.c.post(f"{ficha}/arquivo", data={
        "csrf_token": _token(b.c, ficha), "descricao": "Documento apresentado",
        "arquivo": (io.BytesIO(_png()), "documento.png")},
        content_type="multipart/form-data", follow_redirects=True)
    assert "Arquivo anexado" in _avisos(r), _avisos(r)
    return {"titulo": b.um("SELECT * FROM rg_titulos WHERE id=%s", (titulo["id"],)),
            "registro": registro, "ato": ato,
            "etiqueta": _sem_tags(etiqueta.get_data(as_text=True))}


# ------------------------------------------- o registro, nos cinco livros

LIVROS = [
    # (atribuição, série, item da tabela, natureza, nome do registro na certidão,
    #  apresentante, documento, base legal do livro)
    pytest.param(4, "TD_B", "15.3.1", "Contrato de locação de imóvel residencial",
                 "Registro de Títulos e Documentos", "EMPRESA DE EXEMPLO LTDA",
                 CNPJ, id="rtd-livro-B-registro-integral"),   # LRP 127, I; 132, II; 142
    pytest.param(4, "TD_C", "15.3.1", "Contrato de penhor de bem móvel",
                 "Registro de Títulos e Documentos", "EMPRESA DE EXEMPLO LTDA",
                 CNPJ, id="rtd-livro-C-registro-por-extrato"),  # LRP 132, III; 143
    pytest.param(4, "TD_F", "15.18", "Conjunto de documentos para conservação",
                 "Registro de Títulos e Documentos", "FULANA DE EXEMPLO",
                 CPF, id="rtd-livro-F-registro-facultativo"),   # LRP 127, VII; 127-A
    pytest.param(3, "PJ_A", "15.5.1", "Estatuto de associação civil sem fins econômicos",
                 "Registro de Pessoas Jurídicas", "ASSOCIAÇÃO DE EXEMPLO",
                 CNPJ, id="rcpj-livro-A-constituicao-de-pj"),   # LRP 114, I; 120
    pytest.param(3, "PJ_B", "15.6", "Matrícula de jornal periódico",
                 "Registro de Pessoas Jurídicas", "EDITORA DE EXEMPLO LTDA",
                 CNPJ, id="rcpj-livro-B-matricula-de-periodico"),  # LRP 122, I; 123
]


@pytest.mark.parametrize(
    "atribuicao,serie,item,natureza,nome_do_registro,apresentante,documento", LIVROS)
def test_o_registro_vai_do_protocolo_a_certidao_e_termo_e_certidao_batem(
        casa, monkeypatch, atribuicao, serie, item, natureza, nome_do_registro,
        apresentante, documento):
    """Protocolo → pagamento → qualificação → registro → selo → etiqueta →
    termo → certidão, em cada livro do RTD e do RCPJ.

    LRP arts. 135, 146 e 147 (protocolo e declaração no título); 142, § 1º, e
    152 (encerramento, data e assinatura); 18 e 19 (certidão que menciona o
    livro, autenticada); 161 (a certidão do RTD vale o original). CN-MA arts.
    403 e 966 (protocolo); 972 (datado e assinado); 130 a 132 (selo em cada
    ato, no corpo do papel, conferível pelo código ou pelo QR); 420, IV
    (inteiro teor do RCPJ).
    """
    b = Balcao(casa)
    b.abrir_caixa()
    teor = (f"{natureza.upper()} DE EXEMPLO, firmado por {apresentante}, "
            f"documento nº 1, trasladado na íntegra.")
    feito = _lavrar_pelo_titulo(b, atribuicao=atribuicao, serie=serie, item=item,
                                natureza=natureza, apresentante=apresentante,
                                documento=documento, teor=teor)
    titulo, registro, ato = feito["titulo"], feito["registro"], feito["ato"]
    protocolo_do_livro = "TD_PROTOCOLO" if atribuicao == 4 else "PJ_PROTOCOLO"

    # 1. O PROTOCOLO: número de ordem, data, natureza e apresentante (LRP 135,
    #    146; CN-MA 966, 403), no Livro de Protocolo da atribuição.
    livro_do_protocolo = b.um("SELECT * FROM nu_livros WHERE id=%s", (titulo["livro_id"],))
    assert livro_do_protocolo["serie"] == protocolo_do_livro
    assert titulo["numero"] == 1 and titulo["rotulo"] == "1"
    assert titulo["data_apresentacao"] == date.today().isoformat()
    assert titulo["apresentante"] == apresentante
    assert titulo["natureza"] == natureza

    # 2. O PAGAMENTO: o item da tabela quitado no protocolo e lançado no caixa,
    #    e gasto por ESTE ato (a ponte que a trava do selo pago confere).
    pago = b.um("""SELECT i.*, l.valor FROM cx_protocolo_atos i
                     JOIN cx_lancamentos l ON l.id = i.lancamento_id
                    WHERE i.protocolo_id=%s""", (titulo["protocolo_geral_id"],))
    assert pago["codigo_ato"] == item and pago["quitado"] == 1
    assert pago["valor"] == _total(item)
    assert (pago["usado_por_tabela"], pago["usado_por_ato_id"]) == ("rg_atos", ato["id"])

    # 3. O REGISTRO: livro, folha e número de ordem; o título fecha registrado.
    livro = b.um("SELECT * FROM nu_livros WHERE id=%s", (ato["livro_id"],))
    assert livro["serie"] == serie and str(livro["numero"]) == "1"
    assert (ato["tipo"], ato["folha"], ato["numero_ordem"]) == ("REGISTRO", 1, 1)
    assert registro["numero"] == 1 and registro["serie"] == serie
    assert titulo["situacao"] == "REGISTRADO" and titulo["registro_id"] == registro["id"]

    # 4. O SELO do ato, do aparelho, no razão e no ato (CN-MA 130).
    selo = b.um("SELECT * FROM sd_selos WHERE tabela='rg_atos' AND ato_id=%s",
                (ato["id"],))
    assert selo and ato["selo"] == selo["numero"]
    assert f"Ato: {item}" in selo["texto"]

    # 5. A ETIQUETA colada no título: livro, folha, número, data, protocolo e
    #    selo com QR (LRP 147; CN-MA 967, § 1º).
    e = feito["etiqueta"]
    assert f"fl. 1, sob o n. 1" in e and _br(ato["data_ato"]) in e
    assert "protocolo n. 1" in e and ato["selo"] in e and "confira o selo" in e
    assert SERVENTIA in e

    # 6. O TERMO NO LIVRO — o texto que o livro guarda, e o PDF do ato. O PDF
    #    é impresso «amanhã» (o relógio do módulo um dia à frente): a data do
    #    fecho tem de continuar sendo a do ato, e não a da impressão.
    assert ato["teor"] == teor
    import rg_teor_rtdpj as RGTEOR
    monkeypatch.setattr(RGTEOR, "date", _Amanha)
    termo = b.termo_do_ato(ato["id"], monkeypatch)
    monkeypatch.setattr(RGTEOR, "date", date)
    assert termo["resposta"].status_code == 200, _avisos(termo["resposta"])
    assert termo["resposta"].mimetype == "application/pdf"
    t = termo["textos"]
    cabecalho = " ".join(t["linhas_cabecalho"])
    assert SERVENTIA in cabecalho and f"CNS {CNS}" in cabecalho
    assert (("Registro Civil das Pessoas Jurídicas" if atribuicao == 3
             else "Registro de Títulos e Documentos") in cabecalho)
    assert "para ser REGISTRADO no Registro nº 1" in t["intro"]
    assert f"Tipo do ato: {natureza}." in t["intro"]        # a do protocolo
    # antes do registro, o protocolo do título e quem o apresentou (LD09;
    # LRP art. 136; art. 120, caput e VI) — lidos do Livro de Protocolo
    assert (f"Protocolizado em {_br(titulo['data_apresentacao'])}, sob o nº "
            f"{titulo['numero']}.") in t["intro"]
    assert f"Apresentante: {apresentante}." in t["intro"]
    # o total de páginas, só no registro para conservação (LRP art. 127-A, § 3º)
    assert ("Total de páginas registradas: 1 página." in t["intro"]) == (serie == "TD_F")
    assert f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino." in t["encerramento"]
    assert t["data"] == f"Cidade Exemplo/MA, {_extenso(ato['data_ato'])}."
    for parte in (cabecalho, t["intro"], t["encerramento"], t["data"]):
        _sem_sobra_de_modelo(parte, "termo")
    # o selo do ato no rodapé da última folha (CN-MA 131)
    faixa = termo["ultima_pagina"]["selo_averbacao"]
    assert faixa and faixa["numero"] == ato["selo"]
    assert faixa["qr_texto"].endswith(ato["selo"])

    # 7. A CERTIDÃO: paga, emitida, numerada no exercício e selada.
    cert = b.emitir_certidao(registro["id"], "RTD" if atribuicao == 4 else "RCPJ")
    hoje = date.today().isoformat()
    assert (cert["numero"], cert["ano"]) == (1, date.today().year)
    assert cert["validade_ate"] == (date.today() + timedelta(days=30)).isoformat()
    selo_da_certidao = b.um(
        "SELECT * FROM sd_selos WHERE tabela='at_certidoes' AND ato_id=%s", (cert["id"],))
    assert selo_da_certidao and cert["selo"] == selo_da_certidao["numero"]
    letra = serie.split("_")[-1]
    # ... que menciona o livro (com o número do volume), a folha, o número e a
    # data do ato (LRP 18) ...
    assert f'no Livro "{letra}-1" de {nome_do_registro}' in cert["teor"]
    assert "fls. 1" in cert["teor"] and "ATO n. 1" in cert["teor"]
    assert f"datada de {_br(ato['data_ato'])}" in cert["teor"]
    assert natureza in cert["teor"]
    # ... e é FIEL AO TERMO: reproduz o texto do livro, letra por letra.
    assert teor in cert["teor"]
    _sem_sobra_de_modelo(cert["teor"], "certidão")

    # 8. O PAPEL DA CERTIDÃO (.odt): a serventia e o oficial, o número, o teor,
    #    o local e a data, quem assina, a autenticidade e o selo com os
    #    emolumentos, a consulta e o QR (CN-MA 130 a 132).
    r = b.c.get(f"/atribuicoes/certidoes/{cert['id']}/odt?formato=odt")
    assert r.status_code == 200 and r.mimetype.endswith("opendocument.text")
    papel, imagens = _odt(r.data)
    for pedaco in (SERVENTIA, f"CNS {CNS}", OFICIAL,
                   f"CERTIDÃO n. 1/{date.today().year}", teor,
                   f"Cidade Exemplo-MA, {_extenso(hoje)}",
                   f"Autenticidade: {cert['hash_certidao']}", cert["selo"],
                   f"Emol R$ {_reais(TABELA_15['15.10.1']['emol'])}",
                   f"https://selo.tjma.jus.br/#/resumo/{cert['selo']}"):
        assert pedaco in papel, pedaco
    assert any("qr" in nome for nome in imagens), imagens

    # 9. A CERTIDÃO POR REPRODUÇÃO (PDF com o documento digitalizado): a capa
    #    diz o protocolo e a apresentação do título, o volume do livro, a data
    #    da emissão e quem expediu — e leva o selo da certidão. Quem reimprime
    #    é outra pessoa: a segunda via continua dizendo quem a expediu.
    pdf = Balcao(casa, "conferente").certidao_em_pdf(cert["id"], monkeypatch)
    assert pdf["resposta"].mimetype == "application/pdf", _avisos(pdf["resposta"])
    p = pdf["pedido"]
    assert p["unit_short"] == SERVENTIA and p["cns"] == CNS and p["oficial"] == OFICIAL
    assert p["protocolo"] == str(titulo["numero"])
    assert p["data_apresentacao"] == titulo["data_apresentacao"]
    assert str(p["volume"]) == "1" and p["numero"] == 1
    assert p["dia"] == date.fromisoformat(cert["emitida_em"][:10])
    assert p["lavrante_nome"] == cert["emitida_por_nome"] == OFICIAL
    assert p["lavrante_funcao"] == cert["emitida_por_funcao"] == FUNCAO
    assert p["selo"]["numero"] == cert["selo"]


# ------------------------------------------------------------ a averbação


AVERBACOES = [
    pytest.param(4, "TD_B", "Contrato de locação de imóvel residencial",
                 "Aditivo de prorrogação do prazo", "EMPRESA DE EXEMPLO LTDA",
                 id="rtd-averbacao-de-aditivo"),       # LRP 128; CN-MA 983
    pytest.param(3, "PJ_A", "Estatuto de associação civil sem fins econômicos",
                 "Ata de eleição da diretoria", "ASSOCIAÇÃO DE EXEMPLO",
                 id="rcpj-averbacao-de-eleicao-de-diretoria"),  # CN-MA 412, 414
]


@pytest.mark.parametrize("atribuicao,serie,natureza,natureza_ato,apresentante",
                         AVERBACOES)
def test_a_averbacao_entra_pelo_protocolo_e_sai_no_termo_e_na_certidao(
        casa, monkeypatch, atribuicao, serie, natureza, natureza_ato, apresentante):
    """O título de averbação é protocolado, pago e qualificado; a averbação se
    lavra na ficha do registro, em folha nova, gastando o item daquele
    protocolo; o título se conclui pelo ato; o termo traz o tipo do ato, a data
    da assinatura e o selo; e a certidão — inteira, ou só das averbações — o
    reproduz.

    LRP arts. 128 (averbação à margem do registro) e 19, § 1º; CN-MA arts. 983,
    412 a 414 (averbação no RCPJ, cada documento em ato próprio), 972 e 131.
    """
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=atribuicao, serie=serie,
        item="15.3.1" if atribuicao == 4 else "15.5.1", natureza=natureza,
        apresentante=apresentante, documento=CNPJ,
        teor=f"{natureza.upper()} DE EXEMPLO, trasladado na íntegra.")
    registro = base["registro"]
    # o título da averbação: protocolo, pagamento do 15.9.1 e qualificação
    titulo = b.receber_titulo(atribuicao, serie=serie, natureza=natureza_ato,
                              apresentante=apresentante, documento=CNPJ)
    numero_do_protocolo = b.pagar(titulo["protocolo_geral_id"], "15.9.1")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    ficha = f"/rcpj-rtd/{registro['id']}"
    etiqueta = postar_e_seguir(b.c, f"{ficha}/lancar", {
        "csrf_token": _token(b.c, ficha), "tipo": "AVERBACAO",
        "natureza_ato": natureza_ato, "data_assinatura": "01/10/2026",
        "protocolo_id": str(titulo["protocolo_geral_id"]),
        "novo_arquivo": (io.BytesIO(_png()), "averbacao.png"),
        **_campos_da_lista(serie, natureza_ato)})
    av = b.um("SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'",
              (registro["id"],))
    # folha nova, número seguinte, o selo dela, o item do protocolo dela
    assert (av["folha"], av["numero_ordem"]) == (2, 2)
    assert av["livro_id"] == base["ato"]["livro_id"]
    assert av["selo"] and av["selo"] != base["ato"]["selo"]
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s",
                (titulo["protocolo_geral_id"],))
    assert (item["usado_por_tabela"], item["usado_por_ato_id"]) == ("rg_atos", av["id"])
    # a etiqueta da averbação traz o protocolo DELA (LRP 147)
    e = _sem_tags(etiqueta.get_data(as_text=True))
    assert "fl. 2, sob o n. 2" in e and f"protocolo n. {titulo['numero']}" in e
    assert av["selo"] in e
    # o título se conclui pelo ato lavrado
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    r = b.post(f"{url}/concluir", url, ato_id=str(av["id"]))
    assert "Título concluído" in _avisos(r), _avisos(r)
    assert b.um("SELECT situacao FROM rg_titulos WHERE id=%s",
                (titulo["id"],))["situacao"] == "REGISTRADO"

    # O TERMO: o texto do livro e o PDF do ato
    assert "para ser AVERBADO no Registro nº 1" in av["teor"]
    assert f"Tipo do ato: {natureza_ato}." in av["teor"]
    assert "Data da assinatura: 01/10/2026." in av["teor"]
    termo = b.termo_do_ato(av["id"], monkeypatch)
    assert termo["resposta"].mimetype == "application/pdf", _avisos(termo["resposta"])
    t = termo["textos"]
    assert SERVENTIA in " ".join(t["linhas_cabecalho"])
    # o número de ordem da própria averbação, no alto da folha (LD09; LRP
    # arts. 149 e 153) — e a intro continua a do livro
    assert f"Averbação nº {av['numero_ordem']}" in t["linhas_cabecalho"]
    assert t["intro"] == av["teor"]
    assert "apresentado para averbação" in t["encerramento"]
    assert f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino." in t["encerramento"]
    assert t["data"] == f"Cidade Exemplo/MA, {_extenso(av['data_ato'])}."
    assert termo["ultima_pagina"]["selo_averbacao"]["numero"] == av["selo"]

    # A CERTIDÃO INTEIRA reproduz o registro E a averbação
    cert = b.emitir_certidao(registro["id"], "RTD" if atribuicao == 4 else "RCPJ")
    assert base["ato"]["teor"] in cert["teor"]
    assert f"--- AVERBAÇÃO n. 2 ---\n{av['teor']}" in cert["teor"]
    # A CERTIDÃO SÓ DAS AVERBAÇÕES: o objeto é a averbação, e não o registro
    so_av = b.emitir_certidao(registro["id"], "RTD" if atribuicao == 4 else "RCPJ",
                              ato_ids=[av["id"]])
    assert "ao qual constam as seguintes averbações" in so_av["teor"]
    assert av["teor"] in so_av["teor"]
    assert base["ato"]["teor"] not in so_av["teor"]
    pdf = b.certidao_em_pdf(so_av["id"], monkeypatch)["pedido"]
    assert f"nº 2 ({natureza_ato})" in pdf["objeto_certificado"]
    assert pdf["identificacao_curta"] == "Averbação nº 2"
    # o protocolo da capa é o da própria averbação
    assert pdf["protocolo"] == numero_do_protocolo


# ---------------------------------------------------------- o cancelamento


def test_o_cancelamento_entra_na_certidao_com_o_ato_que_cancelou(casa):
    """O cancelamento é ato próprio, em folha nova, com selo; a etiqueta do
    registro cancelado não sai; e a certidão diz que está cancelado E
    reproduz o ato de cancelamento com a razão dele.

    LRP arts. 164 e 165 (o oficial certifica, na coluna das averbações, o
    cancelamento e a razão dele); CN-MA art. 994, § 1º.
    """
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=4, serie="TD_B", item="15.3.1",
        natureza="Contrato de penhor de bem móvel",
        apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ,
        teor="CONTRATO DE PENHOR DE EXEMPLO, trasladado na íntegra.")
    registro = base["registro"]
    pid = b.protocolo("RTD", "EMPRESA DE EXEMPLO LTDA", "15.9.1")
    motivo = "Quitação do credor apresentada com firma reconhecida, de 01/10/2026."
    ficha = f"/rcpj-rtd/{registro['id']}"
    r = b.post(f"{ficha}/lancar", ficha, tipo="CANCELAMENTO", motivo=motivo,
               protocolo_id=str(pid))
    assert "Cancelamento lançada" in _avisos(r), _avisos(r)
    canc = b.um("SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='CANCELAMENTO'",
                (registro["id"],))
    assert (canc["folha"], canc["numero_ordem"]) == (2, 2) and canc["selo"]
    assert b.um("SELECT situacao FROM rg_registros WHERE id=%s",
                (registro["id"],))["situacao"] == "CANCELADO"
    # etiqueta de registro cancelado não sai
    r = b.post(f"/rcpj-rtd/ato/{base['ato']['id']}/etiqueta", ficha)
    assert "está cancelado" in _avisos(r)
    cert = b.emitir_certidao(registro["id"], "RTD")
    assert "encontra-se CANCELADO nesta Serventia" in cert["teor"]
    assert f"--- AVERBAÇÃO n. 2 ---\n{motivo}" in cert["teor"]


def test_o_cancelamento_tem_termo_datado_e_assinado(casa, monkeypatch):
    """O cancelamento tem termo: a certidão do oficial com a causa e o
    documento que o autorizou, datada (do dia do ato, e não do da impressão) e
    assinada por quem lavrou — com o selo do ato no rodapé, e a ficha oferece
    o PDF. LRP art. 165 e CN-MA art. 994, § 1º («datando e assinando»). Era
    defeito até o LD05: a rota recusava, e o ato guardava só o motivo."""
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=4, serie="TD_B", item="15.3.1",
        natureza="Contrato de penhor de bem móvel",
        apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ,
        teor="CONTRATO DE PENHOR DE EXEMPLO, trasladado na íntegra.")
    pid = b.protocolo("RTD", "EMPRESA DE EXEMPLO LTDA", "15.9.1")
    ficha = f"/rcpj-rtd/{base['registro']['id']}"
    b.post(f"{ficha}/lancar", ficha, tipo="CANCELAMENTO", protocolo_id=str(pid),
           motivo="Quitação do credor apresentada com firma reconhecida.")
    canc = b.um("SELECT * FROM rg_atos WHERE tipo='CANCELAMENTO' ORDER BY id DESC LIMIT 1")
    assert f"rcpj-rtd/ato/{canc['id']}/teor" in b.c.get(ficha).get_data(as_text=True)
    import rg_teor_rtdpj as RGTEOR
    monkeypatch.setattr(RGTEOR, "date", _Amanha)      # a 2ª via, amanhã
    # quem reimprime é outra pessoa: o termo continua assinado por quem lavrou
    termo = Balcao(casa, "conferente").termo_do_ato(canc["id"], monkeypatch)
    monkeypatch.setattr(RGTEOR, "date", date)
    assert termo["resposta"].mimetype == "application/pdf"
    t = termo["textos"]
    assert f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino." in t["encerramento"]
    assert "termo de cancelamento" in t["encerramento"]
    assert "fica CANCELADO o Registro nº 1" in t["intro"]
    assert ("documento que o autorizou: Quitação do credor apresentada com "
            "firma reconhecida.") in t["intro"]
    assert t["data"] == f"Cidade Exemplo/MA, {_extenso(canc['data_ato'])}."
    for parte in (" ".join(t["linhas_cabecalho"]), t["intro"], t["encerramento"]):
        _sem_sobra_de_modelo(parte, "termo de cancelamento")
    assert SERVENTIA in " ".join(t["linhas_cabecalho"])
    assert termo["ultima_pagina"]["selo_averbacao"]["numero"] == canc["selo"]


def test_a_certidao_do_rcpj_sai_pelo_modelo_do_rcpj_e_a_do_rtd_pelo_do_rtd(casa):
    """O ajuste que a casa faz na certidão do RCPJ vale para o RCPJ, e só nele.

    A emissão escolhia o modelo perguntando se o painel era «RCPJ» — e o painel
    das duas atribuições se chama «RCPJ_RTD»: toda certidão do RCPJ saía pelo
    RTD_CERTIDAO. O papel que a serventia assina é o que o oficial ajustou para
    ele (Lei 8.935/1994, art. 30, XIV; CN-MA art. 420).
    """
    import modelos_da_casa as MODELOS
    b = Balcao(casa)
    b.abrir_caixa()
    with b.db.transaction() as con:
        MODELOS.salvar(con, "RCPJ_CERTIDAO", quem="oficial",
                       agora="2026-10-20T09:00:00",
                       corpo=("CERTIFICO, NA FORMA DA CASA PARA O RCPJ, {onde}{natureza}"
                              ":\n\n{teor}"))
    rcpj = _lavrar_pelo_titulo(
        b, atribuicao=3, serie="PJ_A", item="15.5.1",
        natureza="Estatuto de associação civil", apresentante="ASSOCIAÇÃO DE EXEMPLO",
        documento=CNPJ, teor="ESTATUTO DA ASSOCIAÇÃO DE EXEMPLO.")
    rtd = _lavrar_pelo_titulo(
        b, atribuicao=4, serie="TD_B", item="15.3.1",
        natureza="Contrato de exemplo", apresentante="EMPRESA DE EXEMPLO LTDA",
        documento=CNPJ, teor="CONTRATO DE EXEMPLO.")
    teor_rcpj = b.emitir_certidao(rcpj["registro"]["id"], "RCPJ")["teor"]
    teor_rtd = b.emitir_certidao(rtd["registro"]["id"], "RTD")["teor"]
    assert teor_rcpj.startswith("CERTIFICO, NA FORMA DA CASA PARA O RCPJ, no Livro")
    assert teor_rtd.startswith("CERTIFICO E DOU FÉ, que revendo os livros")


def test_o_registro_pelo_titulo_so_sela_o_item_do_registro(casa):
    """No protocolo único do atendimento (a ordem do oficial de 11/09/2026),
    o registro sela o item dele, e a diligência e a certidão ficam para os
    atos delas. CN-MA art. 130 (um selo por ato). Era defeito até o LD05: o
    registro selava todos os itens do protocolo do título."""
    b = Balcao(casa)
    b.abrir_caixa()
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Notificação extrajudicial",
                              apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.8", "15.8.1", "15.8.2")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B",
        "teor": "NOTIFICAÇÃO EXTRAJUDICIAL DE EXEMPLO.",
        "protocolo_id": str(titulo["protocolo_geral_id"])})
    ato = b.um("SELECT * FROM rg_atos ORDER BY id DESC LIMIT 1")
    selos = b.ler("SELECT * FROM sd_selos WHERE tabela='rg_atos' AND ato_id=%s "
                  "ORDER BY id", (ato["id"],))
    assert [s["referencia"].split(":")[-1] for s in selos] == ["15.8"]
    livres = b.ler("""SELECT codigo_ato FROM cx_protocolo_atos
                       WHERE protocolo_id=%s AND usado_em IS NULL ORDER BY id""",
                   (titulo["protocolo_geral_id"],))
    assert [x["codigo_ato"] for x in livres] == ["15.8.1", "15.8.2"]


def test_a_ficha_do_titulo_marca_so_os_itens_do_registro(casa):
    """A tela do título mostra os itens do protocolo para marcar, como a ficha
    do registro: os do registro vêm marcados, os da diligência e da certidão
    não. E não oferece cobrar de novo o que o caixa já recebeu."""
    b = Balcao(casa)
    b.abrir_caixa()
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Notificação extrajudicial",
                              apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.8", "15.8.1", "15.8.2")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    html = b.c.get(f"/rcpj-rtd/titulo/{titulo['id']}").get_data(as_text=True)
    itens = {i["codigo_ato"]: i["id"] for i in b.ler(
        "SELECT id, codigo_ato FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
        (titulo["protocolo_geral_id"],))}
    caixas = dict(re.findall(
        r'name="protocolo_item_id" value="(\d+)"\s*class="protocolo-item-check"( checked)?',
        html))
    assert caixas == {str(itens["15.8"]): " checked", str(itens["15.8.1"]): "",
                      str(itens["15.8.2"]): ""}
    assert 'name="cobrar_protocolo_item"' not in html


def test_o_item_que_outro_ato_gastou_nao_sela_de_novo_e_o_marcado_vale(casa):
    """O caminho de erro do selo (CN-MA art. 130, § 2º): o item que um registro
    já gastou não paga o selo do seguinte — não se vende o mesmo selo duas
    vezes —, e o item que a tela marcou é o único que sela. O arquivamento
    (15.22) que o escrevente desmarcou fica no protocolo."""
    b = Balcao(casa)
    b.abrir_caixa()
    primeiro = b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                                apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
    b.pagar(primeiro["protocolo_geral_id"], "15.3.1", "15.22")
    itens = {i["codigo_ato"]: i["id"] for i in b.ler(
        "SELECT id, codigo_ato FROM cx_protocolo_atos WHERE protocolo_id=%s ORDER BY id",
        (primeiro["protocolo_geral_id"],))}
    b.qualificar(primeiro["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{primeiro['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B", "teor": "CONTRATO DE EXEMPLO.",
        "protocolo_id": str(primeiro["protocolo_geral_id"]),
        "protocolo_item_id": [str(itens["15.3.1"])]})
    ato = b.um("SELECT * FROM rg_atos ORDER BY id DESC LIMIT 1")
    selos = b.ler("SELECT referencia FROM sd_selos WHERE tabela='rg_atos' AND ato_id=%s",
                  (ato["id"],))
    assert [s["referencia"].split(":")[-1] for s in selos] == ["15.3.1"]
    assert b.um("SELECT usado_em FROM cx_protocolo_atos WHERE id=%s",
                (itens["15.22"],))["usado_em"] is None
    # o segundo título aponta o MESMO protocolo: o 15.3.1 já foi gasto
    segundo = b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                               apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
    b.qualificar(segundo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{segundo['id']}"
    r = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B", "teor": "OUTRO CONTRATO.",
        "protocolo_id": str(primeiro["protocolo_geral_id"]),
        "protocolo_item_id": [str(itens["15.3.1"])]})
    assert "SEM SELO" in _avisos(r), _avisos(r)
    assert b.um("SELECT count(*) AS n FROM sd_selos WHERE referencia LIKE %s",
                ("%:15.3.1",))["n"] == 1


# ------------------------------------------------- a notificação extrajudicial


def _dias_de_diligencia(db, quantos: int) -> list[str]:
    """Dias passados em que a norma deixa diligenciar (CN-MA 986, § 4º): sem
    domingo, sem feriado nacional nem local da casa, do mais antigo ao mais novo."""
    from ri_schema import feriados_nacionais, ler_feriados_locais
    locais = ler_feriados_locais(db.get_setting("ri_feriados_locais", ""))
    dias, d = [], date.today() - timedelta(days=1)
    while len(dias) < quantos:
        if d.weekday() != 6 and d not in feriados_nacionais(d.year) | locais:
            dias.append(d.isoformat())
        d -= timedelta(days=1)
    return sorted(dias)


def _notificacao_registrada(b: Balcao, apresentado_em: str) -> dict:
    """O documento entra para registro com notificação (item 15.8), é
    registrado no Livro B, e a notificação de um destinatário se abre."""
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Notificação extrajudicial",
                              apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ,
                              data_apresentacao=apresentado_em, hora="09:00")
    b.pagar(titulo["protocolo_geral_id"], "15.8")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B",
        "teor": "NOTIFICAÇÃO EXTRAJUDICIAL DE EXEMPLO, para pagamento de aluguel.",
        "protocolo_id": str(titulo["protocolo_geral_id"])})
    registro = b.um("SELECT * FROM rg_registros ORDER BY id DESC LIMIT 1")
    # a diligência e a certidão num protocolo seu (no protocolo único, o
    # registro pelo título já não gasta os itens delas — LD05, ver
    # `test_o_registro_pelo_titulo_so_sela_o_item_do_registro`)
    b.protocolo("RTD", "EMPRESA DE EXEMPLO LTDA", "15.8.1", "15.8.2")
    nova = f"/rcpj-rtd/notificacoes/nova?titulo_id={titulo['id']}"
    r = b.post(nova, nova, destinatario_nome="CICLANO DE EXEMPLO",
               destinatario_documento=CPF,
               endereco="Rua de Exemplo, 100, Centro, Cidade Exemplo/MA",
               zona="URBANA")
    assert "Notificação aberta" in _avisos(r), _avisos(r)
    n = b.um("SELECT * FROM rg_notificacoes ORDER BY id DESC LIMIT 1")
    return {"titulo": titulo, "registro": registro, "notificacao": n}


def _certidao_da_notificacao(b: Balcao, nid: int) -> tuple[dict, str]:
    url = f"/rcpj-rtd/notificacao/{nid}"
    r = b.post(f"{url}/certidao", url)
    assert "emitida" in _avisos(r), _avisos(r)
    c = b.um("SELECT * FROM rg_notificacao_certidoes WHERE notificacao_id=%s", (nid,))
    return c, _sem_tags(r.get_data(as_text=True))


def test_a_notificacao_positiva_sai_certificada_averbada_e_na_certidao_do_registro(casa):
    """Registro, diligência, certidão positiva com selo, averbação à margem e a
    certidão do registro que a reproduz.

    LRP art. 160 e § 1º; CN-MA arts. 986, §§ 2º e 4º (diligência das 6h às 20h,
    certidão averbada à margem), 987, § 1º e § 4º, e 988, § 2º (não há certidão
    antes do registro); 130 a 132 (selo e consulta).
    """
    b = Balcao(casa)
    b.abrir_caixa()
    dia = _dias_de_diligencia(b.db, 1)[0]
    feito = _notificacao_registrada(b, dia)
    nid = feito["notificacao"]["id"]
    url = f"/rcpj-rtd/notificacao/{nid}"
    r = b.post(f"{url}/diligencia", url, data=dia, hora="10:00", resultado="ENTREGUE")
    assert "1ª diligência registrada. Selo" in _avisos(r), _avisos(r)
    cert, pagina = _certidao_da_notificacao(b, nid)
    assert cert["tipo"] == "POSITIVA" and cert["selo_situacao"] == "SELADO"
    # o teor: quem, onde, quando, como, e em que registro
    for pedaco in ("procedi à NOTIFICAÇÃO de CICLANO DE EXEMPLO",
                   f"CPF/CNPJ {CPF}", "Rua de Exemplo, 100",
                   f"no dia {_br(dia)}, às 10:00", "entregando-lhe uma via",
                   "sob o nº 1 do Livro B do Registro de Títulos e Documentos"):
        assert pedaco in cert["teor"], pedaco
    _sem_sobra_de_modelo(cert["teor"], "certidão de notificação")
    # o papel: a serventia, quem expediu e o selo conferível com os valores
    for pedaco in (SERVENTIA, f"CNS {CNS}", OFICIAL, cert["selo"],
                   f"Emol R$ {_reais(TABELA_15['15.8.2']['emol'])}",
                   f"https://selo.tjma.jus.br/#/resumo/{cert['selo']}"):
        assert pedaco in pagina, pedaco
    assert re.search(r'class="qr">\s*<svg', b.c.get(
        f"/rcpj-rtd/notificacao/certidao/{cert['id']}").get_data(as_text=True))
    # averbada à margem do registro, e na certidão do registro
    r = b.post(f"{url}/averbar", url)
    assert "averbado à margem" in _avisos(r), _avisos(r)
    av = b.um("SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'",
              (feito["registro"]["id"],))
    assert av["teor"].startswith("AVERBAÇÃO DE NOTIFICAÇÃO.")
    assert f"certidão de notificação nº {cert['numero']}/{cert['ano']}" in av["teor"]
    certidao_do_registro = b.emitir_certidao(feito["registro"]["id"], "RTD")
    assert av["teor"] in certidao_do_registro["teor"]


def test_a_notificacao_negativa_so_se_certifica_depois_de_tres_diligencias_alternadas(casa):
    """Três idas frustradas, em dias e turnos alternados, e só então o
    resultado negativo, a certidão que lista as diligências e a averbação.

    CN-MA art. 987, § 2º (no mínimo três diligências em dias e horários
    alternados) e § 4º; art. 986, § 2º.
    """
    b = Balcao(casa)
    b.abrir_caixa()
    dias = _dias_de_diligencia(b.db, 3)
    feito = _notificacao_registrada(b, dias[0])
    nid = feito["notificacao"]["id"]
    url = f"/rcpj-rtd/notificacao/{nid}"
    for dia, hora in zip(dias[:2], ("09:00", "14:00")):
        b.post(f"{url}/diligencia", url, data=dia, hora=hora, resultado="AUSENTE")
    r = b.post(f"{url}/negativa", url)
    assert "no mínimo 3" in _avisos(r)                 # ainda não
    b.post(f"{url}/diligencia", url, data=dias[2], hora="19:00", resultado="MUDOU_SE")
    r = b.post(f"{url}/negativa", url)
    assert "Resultado negativo registrado" in _avisos(r), _avisos(r)
    cert, pagina = _certidao_da_notificacao(b, nid)
    assert cert["tipo"] == "NEGATIVA" and cert["selo"]
    for pedaco in ("não o(a) localizei nas 3 diligências",
                   f"1ª em {_br(dias[0])}, às 09:00", f"2ª em {_br(dias[1])}, às 14:00",
                   f"3ª em {_br(dias[2])}, às 19:00", "Deixo, por isso, de efetivar"):
        assert pedaco in cert["teor"], pedaco
    assert cert["selo"] in pagina and SERVENTIA in pagina
    b.post(f"{url}/averbar", url)
    av = b.um("SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'",
              (feito["registro"]["id"],))
    assert av["teor"].startswith("AVERBAÇÃO DE NOTIFICAÇÃO NEGATIVA.")
    assert "realizadas 3 diligências" in av["teor"]


# ------------------------------------------ a autenticação de livro contábil


def test_a_autenticacao_de_livro_contabil_sai_com_termos_e_certidao_que_batem(casa):
    """Pedido, autenticação numerada e selada, termos de abertura e de
    encerramento congelados, e a certidão da autenticação — com a serventia,
    o número do controle, o livro, a pessoa jurídica, as folhas e o selo.

    Código Civil art. 1.181; CN-MA art. 402, V (o RCPJ autentica os livros das
    pessoas jurídicas nele registradas); arts. 130 a 132 (selo e consulta).
    """
    b = Balcao(casa)
    b.abrir_caixa()
    conf = "/rcpj-rtd/livros-contabeis/configuracao"
    assert "Item gravado" in _avisos(b.post(conf, conf, item="15.7.1"))
    novo = "/rcpj-rtd/livros-contabeis/novo"
    r = b.post(novo, novo, pj_nome="ASSOCIAÇÃO DE EXEMPLO", pj_cnpj=CNPJ_FORMATADO,
               tipo_livro="DIARIO", numero_livro="1", folhas="50", forma="PAPEL",
               apresentante_nome="FULANA DE EXEMPLO")
    assert "Pedido registrado" in _avisos(r), _avisos(r)
    lc = b.um("SELECT * FROM rg_livros_contabeis ORDER BY id DESC LIMIT 1")
    b.protocolo("RCPJ", "ASSOCIAÇÃO DE EXEMPLO", "15.7.1")
    ficha = f"/rcpj-rtd/livros-contabeis/{lc['id']}"
    r = b.post(f"{ficha}/autenticar", ficha)
    assert "Selo " in _avisos(r), _avisos(r)
    lc = b.um("SELECT * FROM rg_livros_contabeis WHERE id=%s", (lc["id"],))
    assert lc["situacao"] == "AUTENTICADO" and (lc["numero"], lc["ano"]) == (1, date.today().year)
    controle = f"nº 1/{date.today().year}"
    comuns = ("Livro Diário nº 1", "ASSOCIAÇÃO DE EXEMPLO", CNPJ_FORMATADO,
              "50 folhas", "numeradas de 1 a 50", controle,
              f"Cidade Exemplo/MA, {_extenso(lc['autenticado_em'])}", OFICIAL)
    for qual, proprios in (("abertura", ("TERMO DE ABERTURA", SERVENTIA, f"CNS {CNS}")),
                           ("encerramento", ("TERMO DE ENCERRAMENTO",)),
                           ("certidao", ("CERTIDÃO DE AUTENTICAÇÃO DE LIVRO", SERVENTIA,
                                         f"CNS {CNS}", f"Selo de fiscalização: {lc['selo']}"))):
        html = b.c.get(f"{ficha}/papel/{qual}").get_data(as_text=True)
        texto = _sem_tags(html)
        for pedaco in comuns + proprios:
            assert pedaco in texto, (qual, pedaco)
        papel = re.search(r'<pre class="papel"[^>]*>(.*?)</pre>', html, re.S)
        _sem_sobra_de_modelo(_sem_tags(papel.group(1)), qual)
        # o selo da autenticação, conferível no papel
        assert lc["selo"] in texto and re.search(r'class="qr">\s*<svg', html), qual
        assert f"https://selo.tjma.jus.br/#/resumo/{lc['selo']}" in texto, qual


# ------------------------------------------------- a qualificação negativa


def test_a_qualificacao_negativa_sai_em_nota_devolutiva_fundamentada(casa):
    """A nota devolutiva identifica a serventia, o protocolo e o apresentante,
    e traz as exigências, o fundamento, o prazo, o local, a data e quem assina.

    CN-MA arts. 41 e § 1º (nota escrita, fundamentada, com data, identificação
    e assinatura) e 975; LRP art. 156.
    """
    b = Balcao(casa)
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                              apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ)
    r = b.qualificar(titulo["id"], resultado="NEGATIVA",
                     exigencias="Apresentar o original com firma reconhecida do credor.",
                     fundamentacao="Lei 6.015/1973, art. 130, § 3º.",
                     prazo_ate="2026-11-20")
    assert "Qualificação negativa" in _avisos(r), _avisos(r)
    nota = _sem_tags(b.c.get(f"/rcpj-rtd/titulo/{titulo['id']}/nota").get_data(as_text=True))
    for pedaco in (SERVENTIA, f"CNS {CNS}", "Nota devolutiva",
                   "RTD — Registro de Títulos e Documentos", "n. 1",
                   f"Apresentado em {_br(titulo['data_apresentacao'])}",
                   "EMPRESA DE EXEMPLO LTDA", "Contrato de exemplo",
                   "Apresentar o original com firma reconhecida do credor.",
                   "Lei 6.015/1973, art. 130, § 3º.", "até 20/11/2026",
                   f"Cidade Exemplo/MA, {_extenso(date.today().isoformat())}",
                   OFICIAL, FUNCAO):
        assert pedaco in nota, pedaco


# ------------------------------------- o que a norma pede e a casa não tem


def test_a_certidao_por_texto_traz_o_selo_de_cada_ato_que_reproduz(casa):
    """O selo de cada ato reproduzido sai logo abaixo dele — o do registro e o
    da averbação —, além do selo da certidão. CN-MA art. 131 (o selo consta no
    corpo do ato) e LRP art. 19, § 1º (o inteiro teor reproduz o ato). Era
    defeito até o LD05: só o selo da certidão saía."""
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=3, serie="PJ_A", item="15.5.1",
        natureza="Estatuto de associação civil", apresentante="ASSOCIAÇÃO DE EXEMPLO",
        documento=CNPJ, teor="ESTATUTO DA ASSOCIAÇÃO DE EXEMPLO.")
    # e uma averbação, com o selo dela
    titulo = b.receber_titulo(3, serie="PJ_A", natureza="Ata de eleição da diretoria",
                              apresentante="ASSOCIAÇÃO DE EXEMPLO", documento=CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.9.1")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    ficha = f"/rcpj-rtd/{base['registro']['id']}"
    postar_e_seguir(b.c, f"{ficha}/lancar", {
        "csrf_token": _token(b.c, ficha), "tipo": "AVERBACAO",
        "natureza_ato": "Ata de eleição da diretoria", "data_assinatura": "01/10/2026",
        "protocolo_id": str(titulo["protocolo_geral_id"]),
        "novo_arquivo": (io.BytesIO(_png()), "averbacao.png"),
        **_campos_da_lista("PJ_A", "Ata de eleição da diretoria")})
    av = b.um("SELECT * FROM rg_atos WHERE registro_id=%s AND tipo='AVERBACAO'",
              (base["registro"]["id"],))
    assert av["selo"]
    cert = b.emitir_certidao(base["registro"]["id"], "RCPJ")
    papel, _ = _odt(b.c.get(f"/atribuicoes/certidoes/{cert['id']}/odt?formato=odt").data)
    assert base["ato"]["selo"] in papel and av["selo"] in papel and cert["selo"] in papel
    # cada selo logo abaixo do ato dele, na ordem do livro
    assert (cert["teor"].index(base["ato"]["teor"])
            < cert["teor"].index(base["ato"]["selo"])
            < cert["teor"].index(av["teor"]) < cert["teor"].index(av["selo"]))


def test_a_certidao_por_texto_reproduz_o_encerramento_e_quem_subscreveu(casa, monkeypatch):
    """A certidão de inteiro teor reproduz o termo: o encerramento com quem
    subscreveu o ato, o local e a data — os mesmos do PDF do termo, ainda que
    quem emite a certidão seja outra pessoa. LRP arts. 19, § 1º, e 161; CN-MA
    art. 420, IV. Era defeito até o LD05: saía só o texto que o livro guarda."""
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=4, serie="TD_B", item="15.3.1",
        natureza="Contrato de exemplo", apresentante="EMPRESA DE EXEMPLO LTDA",
        documento=CNPJ, teor="CONTRATO DE EXEMPLO, trasladado na íntegra.")
    termo = b.termo_do_ato(base["ato"]["id"], monkeypatch)["textos"]
    # quem pede a certidão é atendido por outro escrevente
    conferente = Balcao(casa, "conferente")
    conferente.abrir_caixa()
    cert = conferente.emitir_certidao(base["registro"]["id"], "RTD")
    assert termo["encerramento"] in cert["teor"]
    assert termo["data"] in cert["teor"]
    assert f"Eu, {OFICIAL}, {FUNCAO}, o subscrevo e assino." in cert["teor"]
    assert CONFERENTE not in cert["teor"]
    # o fecho vem logo depois do texto do ato que ele encerra
    assert f"{base['ato']['teor']}\n{termo['encerramento']}\n{termo['data']}" in cert["teor"]
    _sem_sobra_de_modelo(cert["teor"], "certidão")


def test_a_certidao_negativa_do_rtd_sai_pela_tela(casa):
    """A certidão negativa — serviços 314 e 315 — sai pela tela: pesquisa pelo
    nome e pelo CPF/CNPJ, numerada, selada pelo item de certidão do protocolo
    (gasto por ELA), e o papel diz quem se pesquisou, em que livros, e que nada
    consta. LRP arts. 16, 17 e 19; CN-MA art. 963, § 3º. Era defeito até o
    LD05: a casa só emitia certidão de um registro que existe."""
    b = Balcao(casa)
    b.abrir_caixa()
    pid = b.protocolo("RTD", "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
    r = b.post("/atribuicoes/certidoes/RCPJ_RTD/negativa", "/atribuicoes/certidoes",
               nome_pesquisado="BELTRANO DE EXEMPLO", documento_pesquisado=CPF,
               requerente="FULANA REQUERENTE DE EXEMPLO", protocolo_id=str(pid))
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert r.status_code == 200 and cert, _avisos(r)
    assert "BELTRANO DE EXEMPLO" in cert["teor"] and cert["selo"]
    assert "emitida" in _avisos(r), _avisos(r)
    assert not cert["cancelada"] and (cert["numero"], cert["ano"]) == (1, date.today().year)
    for pedaco in ("NÃO CONSTA registro nem averbação", "000.000.001-91",
                   "Registro de Títulos e Documentos"):
        assert pedaco in cert["teor"], pedaco
    _sem_sobra_de_modelo(cert["teor"], "certidão negativa")
    selo = b.um("SELECT * FROM sd_selos WHERE tabela='at_certidoes' AND ato_id=%s",
                (cert["id"],))
    assert selo and selo["numero"] == cert["selo"] and "Ato: 15.10.1" in selo["texto"]
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
    assert (item["usado_por_tabela"], item["usado_por_ato_id"]) == ("at_certidoes",
                                                                    cert["id"])
    # o papel: a serventia, o número, a data, o selo com os valores e o QR
    r = b.c.get(f"/atribuicoes/certidoes/{cert['id']}/odt?formato=odt")
    papel, imagens = _odt(r.data)
    for pedaco in (SERVENTIA, f"CERTIDÃO n. 1/{date.today().year}",
                   "BELTRANO DE EXEMPLO", cert["selo"],
                   f"Emol R$ {_reais(TABELA_15['15.10.1']['emol'])}"):
        assert pedaco in papel, pedaco
    assert any("qr" in nome for nome in imagens), imagens


def test_a_negativa_nao_sai_para_quem_consta_dos_livros(casa):
    """Quem figura num registro não tem certidão negativa: a pesquisa acha o
    nome (sem ligar para acento nem caixa) e o documento, e a certidão é
    recusada ANTES de numerar — e o item de certidão do protocolo continua lá,
    para a certidão do registro. CN-MA art. 963, § 3º; LRP art. 19."""
    b = Balcao(casa)
    b.abrir_caixa()
    _lavrar_pelo_titulo(b, atribuicao=4, serie="TD_B", item="15.3.1",
                        natureza="Contrato de exemplo",
                        apresentante="EMPRESA DE EXEMPLO LTDA", documento=CNPJ,
                        teor="CONTRATO DE EXEMPLO, firmado por SICRANO DE EXEMPLO.")
    pid = b.protocolo("RTD", "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
    for nome, documento in (("Empresa de Exemplo Ltda", ""),
                            ("OUTRO NOME QUALQUER", CNPJ_FORMATADO),
                            ("Sicrano de Exêmplo", "")):
        r = b.post("/atribuicoes/certidoes/RCPJ_RTD/negativa", "/atribuicoes/certidoes",
                   nome_pesquisado=nome, documento_pesquisado=documento,
                   requerente="FULANA REQUERENTE DE EXEMPLO", protocolo_id=str(pid))
        assert "Consta registro" in _avisos(r), (nome, _avisos(r))
    assert not b.ler("SELECT id FROM at_certidoes")
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
    assert item["usado_em"] is None and not item["quantidade_usada"]


def test_a_negativa_sem_pagamento_nao_sai_sem_selo_e_o_item_volta(casa):
    """O caminho de erro do selo (CN-MA art. 130, § 2º): o item de certidão do
    protocolo não foi pago, a trava do selo pago recusa — e a certidão NÃO
    sai sem selo: fica cancelada com o motivo, nenhum selo é vendido, e o item
    volta ao protocolo (nem gasto, nem ligado a certidão nenhuma)."""
    b = Balcao(casa)
    b.abrir_caixa()
    r = b.c.post("/caixa/protocolos", data={
        "csrf_token": _token(b.c, "/caixa/protocolos"), "acao": "novo",
        "interessado": "FULANA REQUERENTE DE EXEMPLO", "telefone": "(99) 0000-0000",
        "atribuicao": "RTD", "assunto": "Pedido de exemplo"})
    pid = int(r.headers["Location"].rstrip("/").split("/")[-1])
    url = f"/caixa/protocolos/{pid}"
    r = b.post(f"{url}/itens", url, acao="acrescentar", servico=str(_servico("15.10.1")))
    assert "Item 15.10.1 acrescentado" in _avisos(r), _avisos(r)
    r = b.post("/atribuicoes/certidoes/RCPJ_RTD/negativa", "/atribuicoes/certidoes",
               nome_pesquisado="BELTRANO DE EXEMPLO", documento_pesquisado=CPF,
               requerente="FULANA REQUERENTE DE EXEMPLO", protocolo_id=str(pid))
    assert "NÃO emitida" in _avisos(r), _avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    assert cert["cancelada"] == 1 and not cert["selo"]
    assert cert["motivo_cancelamento"].startswith("Selo não emitido")
    assert not b.ler("SELECT id FROM sd_selos WHERE tabela='at_certidoes'")
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
    assert item["usado_em"] is None and not item["quantidade_usada"]
    assert item["usado_por_ato_id"] is None
    assert not b.ler("SELECT id FROM cx_item_do_ato WHERE tabela='at_certidoes'")


SEDE_DE_EXEMPLO = "Rua de Exemplo, 100, Centro, Cidade Exemplo/MA"
OBJETO_DE_EXEMPLO = "Promover atividades culturais de exemplo."
DIRETORIA_DE_EXEMPLO = ("FULANA DE EXEMPLO (presidente); BELTRANO DE EXEMPLO "
                        "(tesoureiro)")


def test_a_certidao_do_rcpj_em_breve_relato_traz_os_elementos_do_art_420(casa):
    """O breve relato da situação atual da pessoa jurídica: denominação, sede,
    CNPJ, objeto, diretoria e a data do último ato — com os VALORES, e não só
    os rótulos — e selado. CN-MA art. 420, II. Era defeito até o LD05: o RCPJ
    só emitia o inteiro teor, e a casa não guardava esses dados.

    O TESTE DO LT05 PEDIA A CERTIDÃO SEM QUE NINGUÉM TIVESSE DITO A SEDE, O
    OBJETO OU A DIRETORIA — e conferia só os rótulos. Os dados estão no
    estatuto, e a casa não os guardava (o próprio defeito o dizia): a única
    certidão que passaria assim teria rótulos vazios, que o art. 420, II não
    aceita. Agora quem leu o estatuto grava os dados na ficha do registro,
    pela tela, antes do pedido; o resto do teste é o de antes, mais os valores.
    """
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=3, serie="PJ_A", item="15.5.1",
        natureza="Estatuto de associação civil", apresentante="ASSOCIAÇÃO DE EXEMPLO",
        documento=CNPJ, teor="ESTATUTO DA ASSOCIAÇÃO DE EXEMPLO.")
    ficha = f"/rcpj-rtd/{base['registro']['id']}"
    r = b.post(f"{ficha}/dados-pj", ficha, pj_sede=SEDE_DE_EXEMPLO,
               pj_objeto=OBJETO_DE_EXEMPLO, pj_diretoria=DIRETORIA_DE_EXEMPLO)
    assert "Dados da pessoa jurídica gravados" in _avisos(r), _avisos(r)
    pid = b.protocolo("RCPJ", "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
    r = b.post(f"/atribuicoes/certidoes/RCPJ_RTD/{base['registro']['id']}", ficha,
               forma="BREVE_RELATO", requerente="FULANA REQUERENTE DE EXEMPLO",
               protocolo_id=str(pid))
    assert "emitida" in _avisos(r), _avisos(r)
    cert = b.um("SELECT * FROM at_certidoes ORDER BY id DESC LIMIT 1")
    for rotulo in ("Denominação", "Sede", "CNPJ", "Diretoria", "último ato"):
        assert rotulo.lower() in cert["teor"].lower(), rotulo
    for valor in ("Denominação: ASSOCIAÇÃO DE EXEMPLO",
                  f"Endereço da sede: {SEDE_DE_EXEMPLO}", f"CNPJ: {CNPJ_FORMATADO}",
                  f"Objeto social: {OBJETO_DE_EXEMPLO}",
                  f"Membros da diretoria: {DIRETORIA_DE_EXEMPLO}",
                  f"nesta Serventia: {_br(base['ato']['data_ato'])} (registro n. 1)",
                  'no Livro "A-1" de Registro de Pessoas Jurídicas'):
        assert valor in cert["teor"], valor
    assert "ESTATUTO DA ASSOCIAÇÃO DE EXEMPLO." not in cert["teor"]   # não é o inteiro teor
    _sem_sobra_de_modelo(cert["teor"], "breve relato")
    assert cert["selo"] and not cert["cancelada"]
    assert cert["fonte_corpo"] == "BREVE_RELATO"


def test_o_breve_relato_sem_os_dados_da_ficha_ou_com_dados_velhos_nao_sai(casa):
    """O caminho de erro: sem a leitura do estatuto gravada na ficha, o breve
    relato é recusado ANTES de numerar — a certidão não se redige no balcão —,
    e o item da certidão continua no protocolo. E a leitura mais velha que o
    último ato não é a situação ATUAL (CN-MA art. 420, II)."""
    import atrib_certidao as CE
    b = Balcao(casa)
    b.abrir_caixa()
    base = _lavrar_pelo_titulo(
        b, atribuicao=3, serie="PJ_A", item="15.5.1",
        natureza="Estatuto de associação civil", apresentante="ASSOCIAÇÃO DE EXEMPLO",
        documento=CNPJ, teor="ESTATUTO DA ASSOCIAÇÃO DE EXEMPLO.")
    pid = b.protocolo("RCPJ", "FULANA REQUERENTE DE EXEMPLO", "15.10.1")
    ficha = f"/rcpj-rtd/{base['registro']['id']}"
    r = b.post(f"/atribuicoes/certidoes/RCPJ_RTD/{base['registro']['id']}", ficha,
               forma="BREVE_RELATO", requerente="FULANA REQUERENTE DE EXEMPLO",
               protocolo_id=str(pid))
    assert "Para o breve relato falta, na ficha do registro" in _avisos(r), _avisos(r)
    assert not b.ler("SELECT id FROM at_certidoes")
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s", (pid,))
    assert item["usado_em"] is None
    # a ficha também recusa a leitura incompleta
    r = b.post(f"{ficha}/dados-pj", ficha, pj_sede=SEDE_DE_EXEMPLO, pj_objeto="")
    assert "Falta o objeto social, os sócios" in _avisos(r), _avisos(r)
    # a leitura de ANTES do último ato
    dados = {"registro": {"serie": "PJ_A", "numero": 1, "requerente_nome": "X DE EXEMPLO",
                          "pj_sede": "Sede", "pj_objeto": "Objeto", "pj_diretoria": "D",
                          "pj_dados_em": "2026-10-01T10:00:00"},
             "atos": [{"id": 1, "tipo": "REGISTRO", "data_ato": "2026-09-01",
                       "criado_em": "2026-09-01T09:00:00"},
                      {"id": 2, "tipo": "AVERBACAO", "numero_ordem": 2,
                       "data_ato": "2026-10-02", "criado_em": "2026-10-02T09:00:00"}]}
    with pytest.raises(CE.CertidaoError, match="situação ATUAL"):
        CE.teor_do_breve_relato(dados)


def test_o_registro_gratuito_sela_como_isento_com_o_comprovante(casa):
    """O ato gratuito tem selo, de categoria própria («isento»), com o
    fundamento escrito, e sai sem pagamento — a trava do selo pago não o
    segura (o oficial, 19/10/2026: «a gratuidade NÃO trava»). CN-MA art. 133;
    CPC art. 98, § 1º, IX. Era defeito até o LD05: o envelope do RTD/RCPJ não
    levava `isento`, e sem pagamento o selo não saía.

    O PEDIDO SE CONFERE PELO CONTRATO, e não por uma grafia: o AtosEmGeral do
    selador leva a isenção como `DadosIsento` (`selador.CAMPOS_ISENTO`: value +
    motivo), a forma medida nas Notas e no arquivamento do RI. O teste do LT05
    procurava o texto `"isento": true` no corpo, que é a forma do RCPN — a
    régua da casa é `ato_selado.selo_e_gratuito`, a mesma que a trava lê.
    """
    import ato_selado as AS
    b = Balcao(casa)
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                              apresentante="FULANA DE EXEMPLO", documento=CPF)
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B",
        "teor": "CONTRATO DE EXEMPLO, trasladado na íntegra.",
        "gratuito": "1", "fundamento_gratuidade": "Gratuidade da justiça — CPC art. 98",
        "protocolo_id": str(titulo["protocolo_geral_id"])})
    ato = b.um("SELECT * FROM rg_atos ORDER BY id DESC LIMIT 1")
    assert ato["selo"], "o ato gratuito sela como isento"
    pedidos = [json.loads(p["corpo"]) for p in casa["selador"].pedidos
               if p["corpo"].strip().startswith("{")]
    isentos = [p for p in pedidos if AS.selo_e_gratuito(p)]
    assert len(isentos) == 1
    assert isentos[0]["isento"] == {"value": True,
                                    "motivo": "Gratuidade da justiça — CPC art. 98"}
    assert isentos[0]["ato"]["codigo"] == "15.3.1"      # o item do Livro B
    # sem dinheiro nenhum: o caixa não recebeu nada, e o selo saiu
    assert not b.ler("SELECT id FROM cx_protocolo_atos WHERE protocolo_id=%s",
                     (titulo["protocolo_geral_id"],))


def test_o_ato_gratuito_sem_fundamento_nao_se_lavra(casa):
    """O caminho de erro: gratuito sem o fundamento escrito é recusado ANTES
    de gastar número de livro — senão o registro ficava no livro sem selo
    (CN-MA arts. 130, § 2º, e 133)."""
    b = Balcao(casa)
    titulo = b.receber_titulo(4, serie="TD_B", natureza="Contrato de exemplo",
                              apresentante="FULANA DE EXEMPLO", documento=CPF)
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    r = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "TD_B", "teor": "CONTRATO.",
        "gratuito": "1", "fundamento_gratuidade": "  ",
        "protocolo_id": str(titulo["protocolo_geral_id"])})
    assert "precisa do fundamento" in _avisos(r), _avisos(r)
    assert b.um("SELECT count(*) AS n FROM rg_atos")["n"] == 0
    assert not casa["selador"].pedidos


# ------------------------------- o que o termo declara (LD09, 21/10/2026)
#
# O termo do registro declara, antes da trasladação, o protocolo do título e
# quem o apresentou (LRP art. 136; art. 120); o do Livro C, o extrato (art.
# 143; CN-MA art. 981); o da inscrição da pessoa jurídica, as indicações do
# art. 120; o da matrícula do periódico, as do art. 123, I. As declarações do
# livro, quem lavra as escreve na ficha do título, e elas ficam NO ATO.

DECLARACOES_DO_LIVRO = [
    pytest.param(4, "TD_C", "15.3.1", "Contrato de penhor de bem móvel",
                 "EMPRESA DE EXEMPLO LTDA", {
                     "valor": "R$ 12.345,67", "prazo": "doze meses",
                     "lugar": "Cidade Exemplo",
                     "partes": ("CREDORA: EMPRESA DE EXEMPLO LTDA; DEVEDOR: "
                                "FULANO DE EXEMPLO, brasileiro, comerciante"),
                     "testemunhas": "CICLANO DE EXEMPLO e BELTRANA DE EXEMPLO",
                     "reconhecimento": "01/10/2026, no Tabelionato de Exemplo",
                     "imposto": "nenhum devido"},
                 ("Valor: R$ 12.345,67.", "Instrumento celebrado em Cidade Exemplo.",
                  "Importância e qualidade do imposto pago: nenhum devido."),
                 id="rtd-livro-C-o-extrato"),                       # LRP 143
    pytest.param(3, "PJ_A", "15.5.1", "Estatuto de associação civil sem fins econômicos",
                 "ASSOCIAÇÃO DE EXEMPLO", {
                     "denominacao": "ASSOCIAÇÃO DE EXEMPLO",
                     "fins": "promover a cultura de exemplo",
                     "sede": "Rua de Exemplo, 100, Centro, Cidade Exemplo/MA",
                     "duracao": "por tempo indeterminado",
                     "administracao": "pela diretoria; representa-a o presidente",
                     "reforma": "sim, pela assembleia, por dois terços",
                     "responsabilidade": "não",
                     "extincao": "por deliberação da assembleia; o patrimônio vai "
                                 "a entidade de fins iguais",
                     "fundadores": "FULANO DE EXEMPLO, brasileiro, casado, comerciante",
                     "diretoria": "FULANA DE EXEMPLO (presidente), brasileira, professora",
                     "residencia_apresentante": "Rua do Apresentante, 1, Cidade Exemplo/MA"},
                 ("Denominação: ASSOCIAÇÃO DE EXEMPLO.",
                  "Se os membros respondem subsidiariamente pelas obrigações sociais: não.",
                  "Diretoria: FULANA DE EXEMPLO (presidente), brasileira, professora."),
                 id="rcpj-livro-A-o-art-120"),                      # LRP 120
    pytest.param(3, "PJ_B", "15.6", "Matrícula de jornal periódico",
                 "EDITORA DE EXEMPLO LTDA", {
                     "titulo_periodico": "GAZETA DE EXEMPLO",
                     "sede_redacao": "Rua da Redação, 10, Cidade Exemplo/MA",
                     "oficinas": "oficina própria, na sede da redação",
                     "diretor": "FULANO DE EXEMPLO, 40 anos, brasileiro",
                     "proprietario": "EDITORA DE EXEMPLO LTDA"},
                 ("Título do periódico: GAZETA DE EXEMPLO.",
                  "Diretor: FULANO DE EXEMPLO, 40 anos, brasileiro.",
                  "Proprietário: EDITORA DE EXEMPLO LTDA."),
                 id="rcpj-livro-B-o-art-123"),                      # LRP 123, I
]


@pytest.mark.parametrize("atribuicao,serie,item,natureza,apresentante,declaracoes,linhas",
                         DECLARACOES_DO_LIVRO)
def test_o_termo_declara_o_protocolo_e_o_que_o_livro_pede_e_a_segunda_via_tambem(
        casa, monkeypatch, atribuicao, serie, item, natureza, apresentante,
        declaracoes, linhas):
    """Pela tela: as declarações do livro digitadas na ficha do título vão
    para o ato na lavratura, e o termo — o da ficha do registro e a prévia do
    título — as declara, com o protocolo e o apresentante do título. A
    segunda via, impressa amanhã por outra pessoa, diz o mesmo: e, no RCPJ, a
    leitura do estatuto gravada DEPOIS (`dados-pj`, a do breve relato) não
    troca a diretoria que a inscrição declarou."""
    import rg_teor_rtdpj as RGTEOR
    b = Balcao(casa)
    b.abrir_caixa()
    feito = _lavrar_pelo_titulo(
        b, atribuicao=atribuicao, serie=serie, item=item, natureza=natureza,
        apresentante=apresentante, documento=CNPJ,
        teor=f"{natureza.upper()} DE EXEMPLO, trasladado na íntegra.",
        declaracoes=declaracoes)
    titulo, ato = feito["titulo"], feito["ato"]
    assert ato["selo"], "o registro com as declarações sela como qualquer outro"
    gravadas = json.loads(ato["declaracoes"])
    # a lista de presença fica no mesmo JSON, à parte dos claros do termo
    lista = gravadas.pop("cnma_lista_presenca", None)
    assert gravadas == declaracoes
    if serie in RG.SERIES_RCPJ:
        assert lista and lista.get("enquadramento")

    protocolo = (f"Protocolizado em {_br(titulo['data_apresentacao'])}, sob o nº "
                 f"{titulo['numero']}.")
    t = b.termo_do_ato(ato["id"], monkeypatch)["textos"]
    assert protocolo in t["intro"] and f"Apresentante: {apresentante}." in t["intro"]
    for valor in declaracoes.values():
        assert valor in t["intro"], valor
    for linha in linhas:
        assert linha in t["intro"], linha
    _sem_sobra_de_modelo(t["intro"], "termo")

    # a prévia do termo, na ficha do título, diz o mesmo
    capturados = []
    montar = RGTEOR.textos_prontos
    monkeypatch.setattr(RGTEOR, "textos_prontos",
                        lambda **kw: capturados.append(montar(**kw)) or capturados[-1])
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    r = b.c.post(f"{url}/teor/previa", data={"csrf_token": _token(b.c, url),
                                              "tipo": "REGISTRO"})
    monkeypatch.setattr(RGTEOR, "textos_prontos", montar)
    assert r.mimetype == "application/pdf", _avisos(r)
    assert capturados[-1]["intro"] == t["intro"]

    if serie == "PJ_A":
        ficha = f"/rcpj-rtd/{feito['registro']['id']}"
        r = b.post(f"{ficha}/dados-pj", ficha, pj_sede="Rua Nova de Exemplo, 2",
                   pj_objeto="Objeto de exemplo.",
                   pj_diretoria="CICLANA DE EXEMPLO (presidente)")
        assert "Dados da pessoa jurídica gravados" in _avisos(r), _avisos(r)
    monkeypatch.setattr(RGTEOR, "date", _Amanha)
    outra = Balcao(casa, "conferente").termo_do_ato(ato["id"], monkeypatch)
    monkeypatch.setattr(RGTEOR, "date", date)
    assert outra["textos"]["intro"] == t["intro"]
    assert "CICLANA DE EXEMPLO" not in outra["textos"]["intro"]


def test_a_declaracao_de_outro_livro_e_recusada_e_nada_se_lavra(casa):
    """O caminho de erro: quem preencheu o quadro do Livro A e escolheu o
    Livro B perderia, calado, o que escreveu, e lavraria um termo sem as
    declarações que achou que fez. A recusa vem antes do número do livro: nenhum
    ato, nenhum selo pedido, o item do protocolo intacto e o título ainda
    qualificado, para lavrar de novo."""
    b = Balcao(casa)
    b.abrir_caixa()
    titulo = b.receber_titulo(3, serie="PJ_B", natureza="Matrícula de jornal periódico",
                              apresentante="EDITORA DE EXEMPLO LTDA", documento=CNPJ)
    b.pagar(titulo["protocolo_geral_id"], "15.6")
    b.qualificar(titulo["id"], resultado="POSITIVA")
    url = f"/rcpj-rtd/titulo/{titulo['id']}"
    r = postar_e_seguir(b.c, f"{url}/registrar", {
        "csrf_token": _token(b.c, url), "serie": "PJ_B", "teor": "MATRÍCULA DE EXEMPLO.",
        "protocolo_id": str(titulo["protocolo_geral_id"]),
        "declaracao_titulo_periodico": "GAZETA DE EXEMPLO",
        "declaracao_denominacao": "ASSOCIAÇÃO DE EXEMPLO"})
    assert "não declara Denominação" in _avisos(r), _avisos(r)
    assert "nada foi lavrado" in _avisos(r)
    assert b.um("SELECT count(*) AS n FROM rg_atos")["n"] == 0
    assert b.um("SELECT situacao FROM rg_titulos WHERE id=%s",
                (titulo["id"],))["situacao"] == "QUALIFICADO"
    assert not casa["selador"].pedidos
    item = b.um("SELECT * FROM cx_protocolo_atos WHERE protocolo_id=%s",
                (titulo["protocolo_geral_id"],))
    assert item["usado_em"] is None and item["usado_por_ato_id"] is None


def test_o_registro_novo_tambem_pergunta_as_declaracoes_e_recusa_a_de_outro_livro(casa):
    """A tela do registro aberto sem título (`/rcpj-rtd/novo`) oferece os
    quadros dos três livros; a declaração do Livro C num registro do Livro B
    volta com o recado e com o que se digitou, e nada se lavra."""
    b = Balcao(casa)
    tela = b.c.get("/rcpj-rtd/novo").get_data(as_text=True)
    for nome in ("declaracao_valor", "declaracao_denominacao",
                 "declaracao_titulo_periodico"):
        assert f'name="{nome}"' in tela, nome
    r = b.post("/rcpj-rtd/novo", "/rcpj-rtd/novo", serie="TD_B",
               natureza="Contrato de exemplo", declaracao_valor="R$ 1,00")
    assert "não declara Valor" in _avisos(r), _avisos(r)
    assert 'value="R$ 1,00"' in r.get_data(as_text=True)
    assert b.um("SELECT count(*) AS n FROM rg_atos")["n"] == 0
