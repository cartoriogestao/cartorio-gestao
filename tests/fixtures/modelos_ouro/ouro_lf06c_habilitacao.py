"""O ouro do grupo «habilitacao» do LF06C — o edital de proclamas e a certidão de habilitação.

Cobre os três papéis de `habilitacao_web`, chamados PELAS ROTAS, como o
escrevente os chama — um Flask mínimo, banco de mentira, nada de banco de
verdade. Pela rota, e não pelo montador, porque antes do LF06C os montadores
eram funções de dentro de `registrar_rotas`, sem nome que se alcance de fora;
a rota existe igual nas duas árvores.

    · a ficha (GET /rcpn/habilitacoes/<id>): o teor que a tela OFERECE no campo
      do edital (o `modelo_edital` entregue ao `render_template`, que aqui é
      trocado) — nomes comuns, com apóstrofo, «&», marcação e chaves, nome
      vazio; o dia fixado em 19/10/2026;
    · o edital (.odt): o HTML entregue a `html_para_odf`, o que chega a
      `gerar_odt` e o `content.xml` do pacote — teor com marcação e chaves,
      teor nulo, prazo vazio, datas com hora, e a recusa quando o edital ainda
      não foi publicado;
    · a certidão (.odt): as quatro linhas do prazo (encerrado ou em curso, com
      ou sem oposição), a expedição no próprio dia do prazo (com e sem hora),
      a oposição em texto vazio, prazo e data da expedição vazios, os cinco
      regimes, o regime nulo, vazio e desconhecido, quem assinou vazio (vale o
      titular), nomes com sinais, validade vazia, o selo com e sem etiqueta, a
      celebrada e a recusa da que não foi expedida.

Cada caso roda com a configuração de teste da serventia e com a configuração
vazia (a semente genérica de `serventia.PADRAO`).

Sem dado real de pessoa: os nomes são «DE EXEMPLO», o CPF é o de teste e a
cidade, «Cidade Exemplo». O que depende de conexão, de hoje e do selo é trocado
por coisa de mentira dentro de cada chamada (`mock.patch.object`), e a troca se
desfaz no fim dela. Depois do LF06C a rota lê o texto pela busca única com a
conexão de mentira — por isso `modelos_da_casa.texto_do_papel` é trocado pelo
padrão da base (a troca não faz nada na árvore de antes).
"""
from __future__ import annotations

import hashlib
import io
import re
import zipfile
from contextlib import ExitStack
from datetime import date
from types import SimpleNamespace
from unittest import mock

HOJE = date(2026, 10, 19)

SV_TESTE = {
    "unit_name": "OFÍCIO ÚNICO DE CIDADE EXEMPLO",
    "ri_cns": "000000",
    "ri_cidade": "Cidade Exemplo",
    "ri_uf": "MA",
    "ri_registrador": "MARIA DE EXEMPLO",
    "serventia_titulo": "Oficiala de Registro Civil",
    "serventia_endereco": "Rua de Exemplo, 1",
    "serventia_cep": "00000-000",
}
CONFIGURACOES = {"sv": SV_TESTE, "sv_vazia": {}}

BASE = dict(
    id=1, numero=7, ano=2026, tipo="CIVIL", regime="COMUNHAO_PARCIAL",
    situacao="HABILITADO",
    nubente1_nome="JOÃO DE EXEMPLO", nubente2_nome="MARIA DE EXEMPLO",
    nubente1_documento="00000000191", nubente2_documento="00000000191",
    edital_em="2026-10-01", edital_prazo_ate="2026-10-06",
    edital_teor=("Faço saber que pretendem casar-se JOÃO DE EXEMPLO e MARIA DE "
                 "EXEMPLO. Cidade Exemplo/MA, 01/10/2026."),
    edital_hash="a" * 64,
    oposicao_em=None, habilitado_em="2026-10-07",
    habilitado_por="JOÃO DE EXEMPLO", habilitacao_vale_ate="2027-01-05",
    certidao_numero=3, certidao_ano=2026, certidao_hash="b" * 64, selo=None)

SINAIS = {"nubente1_nome": "JOÃO D'EXEMPLO {nubente2_nome} {0}",
          "nubente2_nome": "MARIA DE EXEMPLO & <i>CIA</i> {"}

CASOS_DO_MODELO = {
    "base": {},
    "sinais": SINAIS,
    "nome_nulo": {"nubente2_nome": None},
    "nome_vazio": {"nubente1_nome": ""},
}

CASOS_DO_EDITAL = {
    "base": {},
    "teor_com_sinais": {"edital_teor": "TEOR COM {teor} {CHAVES} {0} E <i>MARCA</i> "
                                       "& ASPAS' — {"},
    "teor_nulo": {"edital_teor": None},
    "prazo_vazio": {"edital_prazo_ate": None},
    "datas_com_hora": {"edital_em": "2026-10-01T09:30:00",
                       "edital_prazo_ate": "2026-10-06T00:00:00"},
    "numero_grande": {"numero": 1234, "ano": 2027},
    "nao_publicado": {"edital_em": None},
}

SELO = "HABCAS000000TESTE0000000001"
CASOS_DA_CERTIDAO = {
    "encerrado_sem_oposicao": {},
    "encerrado_com_oposicao": {"oposicao_em": "2026-10-03"},
    "no_dia_do_prazo": {"habilitado_em": "2026-10-06"},
    "no_dia_do_prazo_com_hora": {"habilitado_em": "2026-10-06T16:00:00"},
    "no_dia_do_prazo_com_oposicao": {"habilitado_em": "2026-10-06",
                                     "oposicao_em": "2026-10-02"},
    "em_curso_sem_oposicao": {"habilitado_em": "2026-10-05"},
    "em_curso_com_oposicao": {"habilitado_em": "2026-10-05",
                              "oposicao_em": "2026-10-03"},
    "oposicao_em_texto_vazio": {"oposicao_em": ""},
    "prazo_vazio": {"edital_prazo_ate": None},
    "prazo_vazio_com_oposicao": {"edital_prazo_ate": None,
                                 "oposicao_em": "2026-10-03"},
    "expedicao_vazia": {"habilitado_em": None},
    "expedicao_vazia_com_oposicao": {"habilitado_em": None,
                                     "oposicao_em": "2026-10-03"},
    "prazo_e_expedicao_vazios": {"habilitado_em": None, "edital_prazo_ate": None},
    "regime_comunhao_parcial": {"regime": "COMUNHAO_PARCIAL"},
    "regime_comunhao_universal": {"regime": "COMUNHAO_UNIVERSAL"},
    "regime_separacao_total": {"regime": "SEPARACAO_TOTAL"},
    "regime_separacao_obrigatoria": {"regime": "SEPARACAO_OBRIGATORIA"},
    "regime_participacao_final": {"regime": "PARTICIPACAO_FINAL"},
    "regime_nulo": {"regime": None},
    "regime_vazio": {"regime": ""},
    "regime_desconhecido": {"regime": "XYZ"},
    "sem_quem_assinou": {"habilitado_por": None},
    "quem_assinou_vazio": {"habilitado_por": ""},
    "sinais": SINAIS,
    "validade_vazia": {"habilitacao_vale_ate": None},
    "com_selo": {"selo": SELO},
    "com_selo_sem_etiqueta": {"selo": SELO, "_sem_etiqueta": True},
    "celebrada": {"situacao": "CELEBRADO"},
    "nao_expedida": {"situacao": "EDITAL_PUBLICADO"},
}


class _Hoje(date):
    """`date` com o dia fixo: o modelo do edital leva a data de hoje."""

    @classmethod
    def today(cls):
        return HOJE


class _Conexao:
    """A conexão de mentira: só abre e fecha o `with`."""

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False


class _Banco:
    """O `db` de mentira que `registrar_rotas` recebe."""

    def __init__(self, sv: dict):
        self.sv = dict(sv)

    def get_settings(self):
        return dict(self.sv)

    def get_setting(self, chave, padrao=""):
        return self.sv.get(chave, padrao)

    def connect(self):
        return _Conexao()

    def get_attachments(self, *_):
        return []

    def now(self):
        return "2026-10-19T10:00:00"


class _Linha:
    """O `banco(con)` de mentira: a habilitação do caso, e mais nada."""

    def __init__(self, h: dict):
        self.h = h

    def um(self, *_):
        return dict(self.h)


# O DOMÍNIO DA FICHA, de mentira: o ouro é o teor oferecido, e o resto da ficha
# (documentos, andamento, passos) lê o banco.
_HAB_DA_FICHA = SimpleNamespace(
    documentos_de=lambda con, i: [], andamento_de=lambda con, i: [],
    proximos_passos=lambda con, i, hoje: [], o_que_falta=lambda con, i: [],
    prazo_vencido=lambda h, hoje: False, habilitacao_vencida=lambda h, hoje: False,
    casamentos_da_habilitacao=lambda con, i: [])


def _impressao(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def _content_xml(odt: bytes) -> str:
    """A impressão (sha256) do `content.xml` do pacote.

    O texto por extenso já está no ouro — é o HTML entregue ao conversor, que
    é o que o LF06C mexe. O `content.xml` tem 17 kB de estilos iguais em toda
    folha; gravá-lo por extenso em oitenta saídas só engordaria o ouro, e a
    impressão pega do mesmo jeito qualquer diferença no papel (o carimbo do
    selo inclusive).
    """
    with zipfile.ZipFile(io.BytesIO(odt)) as z:
        return _impressao(_sem_os_estilos(z.read("content.xml").decode("utf-8")))


def _sem_os_estilos(xml: str) -> str:
    """O `content.xml` sem o bloco dos estilos automáticos.

    **OS ESTILOS EXTRAS SÃO DO PROCESSO, E NÃO DO PAPEL** (`ri_odt.
    ESTILOS_EXTRA`): o `notas_web` acrescenta a quebra de página quando a casa
    registra as rotas, e o `ri_odt` o carimbo na primeira certidão com selo.
    O mesmo edital sai com mais ou menos estilos conforme o que rodou antes no
    processo — na suíte, a tela já subiu; no gerador do ouro, não. O texto
    mora no corpo (`office:body`), que é o que se compara.
    """
    return re.sub(r"<office:automatic-styles>.*?</office:automatic-styles>",
                  "", xml, flags=re.S)


def _rodar(rota: str, sv: dict, kw: dict):
    """Chama a rota com a habilitação do caso. Devolve o que o papel recebeu."""
    import flask
    import modelos_da_casa as CASA
    import habilitacao_web as W
    from app import fmt_date

    kw = dict(kw)
    sem_etiqueta = kw.pop("_sem_etiqueta", False)
    h = {**BASE, **kw}
    htmls: list[str] = []
    odts: list[dict] = []
    telas: list[dict] = []
    html_para_odf = W.html_para_odf
    gerar_odt = W.gerar_odt

    def espiao_html(html, *a, **k):
        htmls.append(html)
        return html_para_odf(html, *a, **k)

    def espiao_odt(corpo, *a, **k):
        imagens = k.get("imagens") or {}
        odts.append({
            "corpo_sha256": _impressao(corpo), "titulo": k.get("titulo"),
            "imagens": {n: [hashlib.sha256(b).hexdigest(), m]
                        for n, (b, m) in sorted(imagens.items())}})
        return gerar_odt(corpo, *a, **k)

    def tela(nome, **contexto):
        telas.append({"tela": nome, "modelo_edital": contexto.get("modelo_edital")})
        return "TELA"

    with ExitStack() as pilha:
        troca = pilha.enter_context
        troca(mock.patch.object(W, "date", _Hoje))
        troca(mock.patch.object(W, "banco", lambda con: _Linha(h)))
        troca(mock.patch.object(W, "html_para_odf", espiao_html))
        troca(mock.patch.object(W, "gerar_odt", espiao_odt))
        troca(mock.patch.object(W, "render_template", tela))
        troca(mock.patch.object(W, "HAB", _HAB_DA_FICHA))
        troca(mock.patch.object(
            W.AS, "etiqueta_do_ato",
            lambda con, tabela, ato_id, numero: (
                None if sem_etiqueta else
                f"Selo {numero} — ETIQUETA DE EXEMPLO DA HABILITAÇÃO")))
        troca(mock.patch.object(CASA, "texto_do_papel",
                                lambda con, chave: CASA.padrao_de(chave)))
        app = flask.Flask("ouro_lf06c_habilitacao")
        app.secret_key = "ouro-lf06c"
        app.extensions["usuario_nome"] = lambda: "JOÃO DE EXEMPLO"
        app.extensions["usuario_funcao"] = lambda: "Escrevente"
        app.extensions["usuario_id"] = lambda: 1
        ident = lambda f: f  # noqa: E731
        W.registrar_rotas(app, _Banco(sv), ident, lambda *r, **k: ident,
                          lambda *a, **k: None, fmt_date)
        with app.test_request_context():
            r = app.view_functions[rota](1)
            recados = flask.get_flashed_messages(with_categories=True)
            if isinstance(r, str):
                return {"telas": telas}
            saida = {"status": r.status_code, "recados": recados,
                     "htmls": htmls, "odts": odts,
                     "destino": r.headers.get("Location"),
                     "disposicao": r.headers.get("Content-Disposition"),
                     "mimetype": r.mimetype}
            if r.status_code == 200:
                saida["content_xml_sha256"] = _content_xml(r.get_data())
            return saida


def chamadas() -> dict:
    """Nome -> chamada sem argumento. As mesmas antes e depois do LF06C."""
    saida: dict = {}
    for nome_sv, sv in CONFIGURACOES.items():
        for caso, kw in CASOS_DO_MODELO.items():
            saida[f"ficha.modelo_do_edital.{caso}.{nome_sv}"] = (
                lambda sv=sv, kw=kw: _rodar("rcpn_habilitacao", sv, kw))
        for caso, kw in CASOS_DO_EDITAL.items():
            saida[f"edital.{caso}.{nome_sv}"] = (
                lambda sv=sv, kw=kw: _rodar("rcpn_habilitacao_edital", sv, kw))
        for caso, kw in CASOS_DA_CERTIDAO.items():
            saida[f"certidao.{caso}.{nome_sv}"] = (
                lambda sv=sv, kw=kw: _rodar("rcpn_habilitacao_certidao", sv, kw))
    return saida
