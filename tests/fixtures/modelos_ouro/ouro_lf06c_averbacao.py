"""O ouro do grupo «averbacao» do LF06C — a averbação de retificação (art. 110).

Cobre `rc_averbacao_modelos` (os dois modelos: erro na data do registro e erro
material genérico) e a rota de `rc_averbacao_modelos_web`:

    · o teor montado: de ofício e a requerimento (com e sem data, data
      inválida), com e sem função de quem subscreve, com e sem cidade, uma
      correção com artigo no feminino/masculino, singular/plural e sem artigo,
      várias correções (lista, «; e », título com «, » e « E »), com e sem
      documentos/provas, o fundamento cortado no limite, e as recusas;
    · as frases soltas: `_abertura`, `_do_elemento`, `data_por_extenso`, a
      prova sugerida (termos vizinhos e data de nascimento) e as sugestões do
      formulário (o fundamento padrão), com a data de hoje fixada;
    · a rota: GET (sugestões), POST «gerar» (prévia) e POST «levar» (sessão),
      com um Flask mínimo, banco de mentira e `render_template` trocado — nada
      de banco de verdade.

Sem dado real de pessoa: os nomes são «DE EXEMPLO» e a cidade, «Cidade
Exemplo». O que depende de conexão é trocado por função de mentira dentro de
cada chamada, e a troca se desfaz no fim dela.
"""
from __future__ import annotations

import json
from contextlib import ExitStack, contextmanager
from datetime import date
from unittest import mock

ASSENTO = {"id": 1, "especie": "NASCIMENTO", "numero": 1234}
VIZINHOS = [{"termo": 1233, "data": "01/01/2001"},
            {"termo": 1235, "data": "02/01/2001"}]
HOJE = date(2026, 10, 19)
CON = object()          # a conexão de mentira: só passa de mão em mão


class _Hoje(date):
    """`date` com o dia fixo: as sugestões preenchem a data da averbação."""

    @classmethod
    def today(cls):
        return HOJE


def _base(RAM):
    dr = dict(numero_av="01/1.234", data_como_consta="primeiro de janeiro de dois mil",
              data_correta="2001-01-01",
              elementos_prova="a sequência dos termos vizinhos (termo 1.233, de 01/01/2001).",
              requerente_tipo="oficio", requerente_nome="",
              fundamento=RAM.FUNDAMENTO_PADRAO, data_averbacao="2026-10-19",
              cidade="Cidade Exemplo/MA", subscritor_nome="FULANA DE EXEMPLO",
              subscritor_funcao="Escrevente Autorizada")
    em = dict(numero_av="02/1.234", requerente_tipo="oficio", requerente_nome="",
              data_requerimento="", documentos="", fundamento=RAM.FUNDAMENTO_PADRAO,
              data_averbacao="2026-10-19", cidade="Cidade Exemplo/MA",
              subscritor_nome="FULANA DE EXEMPLO",
              subscritor_funcao="Escrevente Autorizada")
    return dr, em


C_A = {"campo": "a data de nascimento", "errado": "01/01/2000", "correto": "02/01/2000"}
C_AS = {"campo": "AS DATAS", "errado": "x", "correto": "y"}
C_O = {"campo": "o nome da genitora", "errado": "MARIA DE EXEMPLO",
       "correto": "MARIA DE EXEMPLO SILVA"}
C_OS = {"campo": "OS NOMES DOS AVÓS PATERNOS", "errado": "«JOSE DE EXEMPLO»",
        "correto": "\"JOSÉ DE EXEMPLO\""}
C_SEM = {"campo": "naturalidade", "errado": "CIDADE A", "correto": "CIDADE B"}


@contextmanager
def _sem_banco(RAM, *, vizinhos=VIZINHOS):
    """O que pede conexão vira função de mentira; a busca única, o padrão."""
    import modelos_da_casa as CASA
    with ExitStack() as pilha:
        pilha.enter_context(mock.patch.object(
            CASA, "texto_do_papel", lambda con, k: CASA.padrao_de(k)))
        pilha.enter_context(mock.patch.object(
            RAM, "termos_vizinhos", lambda con, a, **_: list(vizinhos)))
        pilha.enter_context(mock.patch.object(
            RAM, "proximo_numero_av", lambda con, a: "03/1.234"))
        pilha.enter_context(mock.patch.object(
            RAM, "cidade_da_casa", lambda con: "Cidade Exemplo/MA"))
        pilha.enter_context(mock.patch.object(RAM, "date", _Hoje))
        yield


def _rota(passos):
    """A rota inteira num Flask mínimo: sem banco, sem template de verdade."""
    import flask
    import rc_averbacao_modelos as RAM
    import rc_averbacao_modelos_web as WEB

    assento = {"id": 5, "especie": "NASCIMENTO", "numero": 1234, "situacao": "ATIVO",
               "nome": "JOÃO DE EXEMPLO", "data_ato": "2001-01-01",
               "data_fato": "2000-12-31",
               "dados_json": json.dumps({"data_registro_teor": "um de janeiro de dois mil"})}

    class _Banco:
        def __init__(self, con):
            pass

        def um(self, sql, params=()):
            if "rc_assentos" in sql:
                return dict(assento) if params and params[0] == 5 else None
            return {"full_name": "FULANA DE EXEMPLO", "username": "fulana",
                    "funcao": "Escrevente Autorizada"}

        def tem_coluna(self, tabela, coluna):
            return True

    class _Db:
        @contextmanager
        def connect(self):
            yield CON

    def _tela(nome, **kw):
        return json.dumps({"tela": nome, "valores": kw["valores"],
                           "previa": kw["previa"], "modelo": kw["modelo"]["slug"],
                           "assento": kw["assento"]["id"]},
                          ensure_ascii=False, sort_keys=True)

    app = flask.Flask("ouro_lf06c_averbacao")
    app.secret_key = "ouro"
    for rota, nome in (("/a/<int:assento_id>", "rcpn_averbar"), ("/b", "rcpn_assentos"),
                       ("/c/<int:assento_id>", "rcpn_assento")):
        app.add_url_rule(rota, nome, lambda **_: "")
    with _sem_banco(RAM), ExitStack() as pilha:
        pilha.enter_context(mock.patch.object(WEB, "banco", _Banco))
        pilha.enter_context(mock.patch.object(WEB, "render_template", _tela))
        WEB.registrar_rotas(app, _Db(), lambda f: f, lambda *papeis: (lambda f: f), None)
        cliente = app.test_client()
        with cliente.session_transaction() as s:
            s["user_id"] = 7
        saida = []
        for metodo, url, dados in passos:
            r = cliente.open(url, method=metodo, data=dados)
            with cliente.session_transaction() as s:
                sessao = {k: v for k, v in s.items() if k != "user_id"}
                s.pop("_flashes", None)
                s.pop(RAM.CHAVE_DA_SESSAO, None)
            saida.append({"status": r.status_code, "local": r.headers.get("Location"),
                          "corpo": r.get_data(as_text=True), "sessao": sessao})
        return saida


def chamadas() -> dict:
    import rc_averbacao_modelos as RAM

    DR, EM = _base(RAM)
    A = ASSENTO
    dr, em = "retificacao-data-registro", "retificacao-erro-material"
    longo = "Y" * 600

    def montar(slug, v, a=A):
        return lambda: RAM.montar(slug, v, a)

    def com_banco(f):
        def chamada():
            with _sem_banco(RAM):
                return f()
        return chamada

    def prova(assento, vizinhos=VIZINHOS):
        def chamada():
            with _sem_banco(RAM, vizinhos=vizinhos):
                return RAM._prova_sugerida(CON, assento)
        return chamada

    form_dr = {"numero_av": "01/1.234", "data_como_consta": "um de janeiro de dois mil",
               "data_correta": "2001-01-01",
               "elementos_prova": "a sequência dos termos vizinhos",
               "requerente_tipo": "oficio", "requerente_nome": "",
               "fundamento": "Artigo 110, §§1º e 3º, da Lei 6.015/1973",
               "data_averbacao": "2026-10-19", "cidade": "Cidade Exemplo/MA",
               "subscritor_nome": "FULANA DE EXEMPLO",
               "subscritor_funcao": "Escrevente Autorizada"}
    form_em = {"numero_av": "02/1.234", "correcao_campo_1": "O NOME DA GENITORA",
               "correcao_errado_1": "MARIA DE EXEMPLO",
               "correcao_correto_1": "MARIA DE EXEMPLO SILVA",
               "correcao_campo_2": "A DATA DE NASCIMENTO",
               "correcao_errado_2": "01/01/2000", "correcao_correto_2": "02/01/2000",
               "requerente_tipo": "parte", "requerente_nome": "JOÃO DE EXEMPLO",
               "data_requerimento": "2026-10-10", "documentos": "certidão",
               "fundamento": "Artigo 110, §§1º e 3º, da Lei 6.015/1973",
               "data_averbacao": "2026-10-19", "cidade": "Cidade Exemplo/MA",
               "subscritor_nome": "FULANA DE EXEMPLO", "subscritor_funcao": ""}

    return {
        # ------------------------------------------------ data do registro
        "dr_oficio": montar(dr, DR),
        "dr_parte": montar(dr, dict(DR, requerente_tipo="parte",
                                    requerente_nome="JOÃO DE EXEMPLO")),
        "dr_sem_funcao": montar(dr, dict(DR, subscritor_funcao="")),
        "dr_sem_cidade": montar(dr, dict(DR, cidade="")),
        "dr_datas_dd_mm_e_aspas": montar(dr, dict(
            DR, data_correta="01/01/2001", data_averbacao="19/10/2026",
            data_como_consta="“primeiro de janeiro de dois mil”")),
        "dr_sem_prova_recusa": montar(dr, dict(DR, elementos_prova="")),
        "dr_ausencia_recusa": montar(dr, DR, {"especie": "AUSENCIA"}),
        "dr_data_correta_invalida": montar(dr, dict(DR, data_correta="2001-13-01")),
        "dr_data_averbacao_invalida": montar(dr, dict(DR, data_averbacao="xx")),
        "dr_parte_sem_nome": montar(dr, dict(DR, requerente_tipo="parte")),
        # ------------------------------------------------ erro material
        "em_a": montar(em, dict(EM, correcoes=[C_A])),
        "em_as": montar(em, dict(EM, correcoes=[C_AS])),
        "em_o": montar(em, dict(EM, correcoes=[C_O])),
        "em_os": montar(em, dict(EM, correcoes=[C_OS])),
        "em_sem_artigo": montar(em, dict(EM, correcoes=[C_SEM])),
        "em_duas_parte_data_documentos_obito": montar(em, dict(
            EM, correcoes=[C_O, C_SEM], requerente_tipo="parte",
            requerente_nome="JOÃO DE EXEMPLO", data_requerimento="2026-10-10",
            documentos="certidão de nascimento da genitora."), {"especie": "OBITO"}),
        "em_cinco_parte_sem_data_funcao_cidade_casamento": montar(em, dict(
            EM, correcoes=[C_A, C_AS, C_O, C_OS, C_SEM], requerente_tipo="parte",
            requerente_nome="MARIA DE EXEMPLO", subscritor_funcao="", cidade=""),
            {"especie": "CASAMENTO"}),
        "em_fundamento_cortado": montar(em, dict(EM, correcoes=[
            {"campo": "O ELEMENTO 1", "errado": longo, "correto": longo},
            {"campo": "O ELEMENTO 2", "errado": longo, "correto": longo}])),
        "em_sem_correcao": montar(em, dict(EM, correcoes=[])),
        "em_linha_pela_metade": montar(em, dict(EM, correcoes=[
            {"campo": "O SEXO", "errado": "M", "correto": ""}])),
        "em_data_requerimento_invalida": montar(em, dict(
            EM, correcoes=[C_A], requerente_tipo="parte",
            requerente_nome="JOÃO DE EXEMPLO", data_requerimento="xx")),
        "slug_desconhecido": montar("x", EM),
        # ------------------------------------------------ frases soltas
        "abertura_oficio": lambda: RAM._abertura({"requerente_tipo": "oficio"}),
        "abertura_vazia": lambda: RAM._abertura({}),
        "abertura_parte_com_data": lambda: RAM._abertura({
            "requerente_tipo": "parte", "requerente_nome": " JOÃO DE EXEMPLO ",
            "data_requerimento": "2026-10-10"}),
        "abertura_parte_data_invalida": lambda: RAM._abertura({
            "requerente_tipo": "parte", "requerente_nome": "JOÃO DE EXEMPLO",
            "data_requerimento": "xx"}),
        "abertura_parte_sem_nome": lambda: RAM._abertura({"requerente_tipo": "parte"}),
        "do_elemento": lambda: [RAM._do_elemento(c) for c in (
            "o nome", "OS NOMES", "a data", "AS DATAS", "naturalidade", "DA MÃE")],
        "data_por_extenso": lambda: [RAM.data_por_extenso(d) for d in (
            "2026-01-05", "19/10/2026", "", "xx")],
        "constantes_antigas": lambda: {"FUNDAMENTO_PADRAO": RAM.FUNDAMENTO_PADRAO,
                                       "ABERTURA_DE_OFICIO": RAM.ABERTURA_DE_OFICIO},
        # ------------------------------------------------ prova sugerida
        "prova_nascimento": prova({"id": 1, "especie": "NASCIMENTO",
                                   "data_fato": "2000-12-31"}),
        "prova_obito": prova({"id": 1, "especie": "OBITO", "data_fato": "2000-12-31"}),
        "prova_sem_vizinhos": prova({"id": 1, "especie": "NASCIMENTO",
                                     "data_fato": "2000-12-31"}, vizinhos=[]),
        "prova_sem_data_fato": prova({"id": 1, "especie": "NASCIMENTO"}),
        "prova_nada": prova({"id": 1, "especie": "OBITO"}, vizinhos=[]),
        # ------------------------------------------------ sugestões
        "sugestoes_dr": com_banco(lambda: RAM.sugestoes(
            CON, dr, dict(A, data_ato="2001-01-01", data_fato="2000-12-31",
                          dados_json=json.dumps({"data_registro_teor": "um de janeiro"})),
            {"nome": "FULANA DE EXEMPLO", "funcao": "Escrevente Autorizada"})),
        "sugestoes_em": com_banco(lambda: RAM.sugestoes(CON, em, A)),
        "sugestoes_dr_montadas": com_banco(lambda: RAM.montar(dr, RAM.sugestoes(
            CON, dr, dict(A, data_ato="2001-01-01", data_fato="2000-12-31",
                          dados_json=json.dumps({"data_registro_teor": "um de janeiro"})),
            {"nome": "FULANA DE EXEMPLO", "funcao": "Escrevente Autorizada"}), A)),
        "sugestoes_em_montadas": com_banco(lambda: RAM.montar(em, dict(RAM.sugestoes(
            CON, em, A, {"nome": "FULANA DE EXEMPLO"}), correcoes=[C_O]), A)),
        # ------------------------------------------------ a rota
        "rota_data_registro": lambda: _rota([
            ("GET", f"/rcpn/5/averbar/modelo/{dr}", None),
            ("POST", f"/rcpn/5/averbar/modelo/{dr}", dict(form_dr, acao="gerar")),
            ("POST", f"/rcpn/5/averbar/modelo/{dr}", dict(form_dr, acao="levar")),
            ("POST", f"/rcpn/5/averbar/modelo/{dr}", dict(
                form_dr, acao="levar", teor="TEXTO EDITADO", fundamento_ato="F")),
            ("POST", f"/rcpn/5/averbar/modelo/{dr}", dict(
                form_dr, acao="levar", subscritor_nome="", teor="TEXTO EDITADO")),
            ("GET", f"/rcpn/6/averbar/modelo/{dr}", None),
            ("GET", "/rcpn/5/averbar/modelo/x", None),
        ]),
        "rota_erro_material": lambda: _rota([
            ("GET", f"/rcpn/5/averbar/modelo/{em}", None),
            ("POST", f"/rcpn/5/averbar/modelo/{em}", dict(form_em, acao="gerar")),
            ("POST", f"/rcpn/5/averbar/modelo/{em}", dict(form_em, acao="levar")),
            ("POST", f"/rcpn/5/averbar/modelo/{em}", dict(
                form_em, acao="gerar", correcao_correto_2="")),
        ]),
    }


def textos() -> dict:
    import rc_averbacao_modelos as RAM
    return {"rc_averbacao_modelos.FUNDAMENTO_PADRAO": RAM.FUNDAMENTO_PADRAO,
            "rc_averbacao_modelos.ABERTURA_DE_OFICIO": RAM.ABERTURA_DE_OFICIO}
