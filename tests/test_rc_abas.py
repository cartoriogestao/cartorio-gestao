"""As abas da ficha do assento: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Que nenhum quadro fica fora de alcance, e que «O que espera ação» não vira alarme que soa
    sempre. Quadro sem aba some da tela sem erro nenhum. A parte de baixo usa o sistema de pé, e
    roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_abas as RA  # noqa: E402

FICHA = (RAIZ / "templates" / "atrib_rcpn_ficha.html").read_text(encoding="utf-8-sig")
DIGITALIZACAO = (RAIZ / "templates" / "_rc_digitalizacao.html").read_text(encoding="utf-8-sig")


def _assento(**campos) -> dict:
    return {"id": 1, "especie": "NASCIMENTO", "situacao": "ATIVO", "origem": "MANUAL", **campos}


def _blocos(**campos) -> dict:
    return {"REGISTRO": [], "AVERBACAO": [], "ANOTACAO": [], "RETIFICACAO": [], **campos}


def _chaves(r: dict) -> list[str]:
    return [x["chave"] for x in r["apoio"]]


def _aba(r: dict, chave: str) -> dict:
    return next(x for x in r["apoio"] if x["chave"] == chave)


def _textos(itens: list[dict]) -> str:
    return " | ".join(i["texto"] for i in itens)


def test_o_minimo_de_todo_assento():
    r = RA.abas_do_assento(_assento(), blocos=_blocos())
    assert _chaves(r) == [RA.ASSENTO, RA.FILIACAO, RA.CERTIDOES, RA.TERMO]
    assert r["inicial"] == RA.ASSENTO


def test_nao_ha_fase_nem_trava():
    """O assento já está lavrado: ninguém «termina» as averbações."""
    assert RA.abas_do_assento(_assento(), blocos=_blocos())["fases"] == []


def test_aba_de_lista_vazia_nao_aparece_e_a_cheia_conta():
    r = RA.abas_do_assento(_assento(), blocos=_blocos(
        AVERBACAO=[{"selo": "A"}], ANOTACAO=[{"selo": "B"}, {"selo": "C"}], RETIFICACAO=[{"selo": "D"}]),
        pessoas=[1, 2, 3], certidoes=[1], anexos=[1])
    assert _chaves(r) == [RA.ASSENTO, RA.FILIACAO, RA.AVERBACOES, RA.ANOTACOES, RA.RETIFICACOES,
                          RA.CERTIDOES, RA.TERMO, RA.DOCUMENTOS]
    contagem = {x["chave"]: x["contagem"] for x in r["apoio"]}
    assert contagem[RA.ANOTACOES] == 2 and contagem[RA.FILIACAO] == 3 and contagem[RA.CERTIDOES] == 1


def test_o_cpf_a_averbar_abre_a_aba_porque_o_formulario_mora_la():
    r = RA.abas_do_assento(_assento(), blocos=_blocos(), cpf_pendentes=[{"papel": None}])
    assert RA.AVERBACOES in _chaves(r)


def test_o_cpf_nao_entra_no_que_espera():
    """Assento antigo sem CPF é a regra daqueles livros, e não atraso."""
    r = RA.abas_do_assento(_assento(), blocos=_blocos(), cpf_pendentes=[{"papel": None}])
    assert r["espera"] == []


def test_o_termo_de_paternidade_abre_documentos_mesmo_sem_anexo():
    r = RA.abas_do_assento(_assento(), blocos=_blocos(), paternidade={"tipo": "NEGATIVO"})
    assert RA.DOCUMENTOS in _chaves(r)
    assert _aba(r, RA.DOCUMENTOS)["alerta"] == 0


def test_o_registro_sem_selo_espera_e_leva_ao_formulario():
    itens = RA.o_que_espera(_assento(), blocos=_blocos(REGISTRO=[{"id": 7, "selo": "", "origem": "MANUAL"}]))
    assert [i["ir"] for i in itens] == ["selar-registro-7"]


def test_o_acervo_nao_vira_alarme():
    blocos = _blocos(REGISTRO=[{"id": 7, "selo": "", "origem": "EOFICIO"}],
                     AVERBACAO=[{"id": 8, "selo": "", "origem": "EOFICIO"}])
    assert RA.o_que_espera(_assento(origem="EOFICIO"), blocos=blocos) == []
    assert _aba(RA.abas_do_assento(_assento(), blocos=blocos), RA.AVERBACOES)["alerta"] == 0


def test_o_casamento_nao_cobra_selo_do_registro():
    """O selo dele é o da habilitação: o assento só o espelha, e o botão de selar não existe."""
    for especie in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        blocos = _blocos(REGISTRO=[{"id": 7, "selo": "", "origem": "MANUAL"}])
        assert RA.o_que_espera(_assento(especie=especie), blocos=blocos) == []


def test_o_cancelado_nao_cobra():
    blocos = _blocos(REGISTRO=[{"id": 7, "selo": ""}], AVERBACAO=[{"id": 8, "selo": ""}])
    assert RA.o_que_espera(_assento(situacao="CANCELADO"), blocos=blocos) == []


def test_a_averbacao_sem_selo_espera_e_marca_a_aba():
    blocos = _blocos(AVERBACAO=[{"id": 8, "selo": ""}, {"id": 9, "selo": "X"}])
    r = RA.abas_do_assento(_assento(), blocos=blocos)
    assert [i["ir"] for i in r["espera"]] == ["selar-averbacao-8"]
    assert _aba(r, RA.AVERBACOES)["alerta"] == 1


def test_a_paternidade_so_espera_na_alegacao_nao_remetida():
    assert "paternidade" in _textos(RA.o_que_espera(_assento(), blocos=_blocos(), paternidade={"tipo": "ALEGACAO"}))
    for paternidade in ({"tipo": "ALEGACAO", "remetido_em": "2026-10-01"}, {"tipo": "NEGATIVO"},
                        {"tipo": "MAE_AUSENTE"}, None):
        assert RA.o_que_espera(_assento(), blocos=_blocos(), paternidade=paternidade) == []


def test_a_digitalizacao_pendente_diz_se_venceu():
    pendente = RA.o_que_espera(_assento(), blocos=_blocos(), digi={"pendente": True, "vencida": False})
    vencida = RA.o_que_espera(_assento(), blocos=_blocos(), digi={"pendente": True, "vencida": True})
    assert "ainda não digitalizado" in _textos(pendente)
    assert "vencido" in _textos(vencida)
    assert RA.o_que_espera(_assento(), blocos=_blocos(), digi={"pendente": False}) == []
    r = RA.abas_do_assento(_assento(), blocos=_blocos(), digi={"pendente": True})
    assert _aba(r, RA.TERMO)["alerta"] == 1


def test_a_habilitacao_so_espera_enquanto_falta_amarrar():
    assert RA.o_que_espera(_assento(especie="CASAMENTO"), blocos=_blocos(), habilitacao={"situacao": "HABILITADO"})
    assert not RA.o_que_espera(_assento(especie="CASAMENTO"), blocos=_blocos(), habilitacao={"situacao": "CELEBRADO"})


def test_o_botao_de_selar_e_a_conta_usam_as_mesmas_especies():
    """Se a ficha passar a oferecer selo a outra espécie, a conta tem de vir junto."""
    achado = re.search(r"\(assento\.especie or ''\)\|upper in \(([^)]+)\)", FICHA)
    assert achado, "o varredor deixou de achar a condição do botão"
    assert set(re.findall(r"'([A-Z_]+)'", achado.group(1))) == set(RA.ESPECIES_QUE_SELAM_O_REGISTRO)


# ------------------------------------------------------------- o molde

def _sem_marcas(html: str) -> str:
    return re.sub(r"\{%.*?%\}", "", re.sub(r"\{#.*?#\}", "", html, flags=re.S), flags=re.S)


def test_todo_quadro_diz_em_que_aba_mora():
    corpo = _sem_marcas(FICHA[FICHA.index("{% block content %}"):])
    abertos = re.findall(r"<section\b[^>]*\bclass=\"panel[^>]*>", corpo)
    assert len(abertos) >= 12, "o varredor deixou de achar os quadros"
    assert [t for t in abertos if "data-fase" not in t] == []
    assert 'data-fase="termo"' in re.search(r"<section[^>]*termo-digitalizado[^>]*>", DIGITALIZACAO).group(0)


def test_toda_aba_tem_endereco_e_quadro():
    for chave in (RA.ASSENTO, RA.FILIACAO, RA.AVERBACOES, RA.CERTIDOES, RA.TERMO, RA.DOCUMENTOS):
        assert f'id="{chave}"' in FICHA, chave
    for chave in (RA.ASSENTO, RA.FILIACAO, RA.AVERBACOES, RA.ANOTACOES, RA.RETIFICACOES, RA.CERTIDOES,
                  RA.TERMO, RA.DOCUMENTOS):
        assert f'data-fase="{chave}"' in FICHA or f"'{chave}')" in FICHA, chave
    assert 'id="{{ aba }}"' in FICHA, "as âncoras de Anotações e Retificações"


def test_todo_endereco_do_que_espera_existe():
    for ancora in ('id="selar-registro-{{ a.id }}"', 'id="selar-averbacao-{{ a.id }}"', 'id="paternidade"',
                   'id="habilitacao-do-assento"'):
        assert ancora in FICHA, ancora
    assert 'id="termo-digitalizado"' in DIGITALIZACAO


def test_quem_continua_no_layout_antigo_nao_recebe_nada():
    assert "{% set abas = abas_da_ficha(rc_digi_ficha) if layout_novo else none %}" in FICHA
    assert "{% if not abas %}{{ bloco_documentos }}{{ bloco_termo }}{% endif %}" in FICHA
    assert "{% if abas %}</div>{% endif %}" in FICHA


def test_os_documentos_e_o_termo_saem_uma_vez_em_cada_moldura():
    assert FICHA.count("{{ bloco_documentos }}") == 2
    assert FICHA.count("{{ bloco_termo }}") == 2
    novo = FICHA[FICHA.index("{% if not abas %}{{ bloco_documentos }}"):]
    assert '<section class="panel" data-fase="termo">{{ bloco_termo }}</section>' in novo


# ------------------------------------------------------------- com o sistema de pé

def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", "ADMIN")
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def _assento_de_ensaio(app) -> int:
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        return int(banco(con).escrever(
            """INSERT INTO rc_assentos (serie, especie, nome, situacao, origem, criado_em)
               VALUES ('A', 'NASCIMENTO', 'Ana Exemplo', 'ATIVO', 'MANUAL', %s) RETURNING id""",
            (d.now(),))[0]["id"])


def test_as_duas_molduras_oferecem_o_mesmo(cg_app):
    c = _entrar(cg_app, "assento_a")
    endereco = f"/rcpn/{_assento_de_ensaio(cg_app)}"
    corpo = lambda html: html[html.index('class="content"'):]        # noqa: E731
    formularios = lambda html: {e for e in re.findall(r'<form[^>]*\baction="([^"]+)"', corpo(html))  # noqa: E731
                                if "/rcpn/" in e}
    _layout(c, "antigo")
    antigo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" not in antigo
    _layout(c, "novo")
    novo = c.get(endereco).get_data(as_text=True)
    assert "data-cg-regua" in novo
    assert formularios(antigo) == formularios(novo)
    assert len(formularios(novo)) >= 2, "o varredor deixou de achar os formulários"
