"""As abas da ficha do registro do Livro 3: a conta da régua, e o que a ficha não pode perder.

O QUE ELES DEFENDEM
    Projeto do novo layout, 30/10/2026. Quadro sem aba some da tela sem erro nenhum, e alarme sobre o
    acervo soaria em todo registro antigo. A parte de baixo usa o sistema de pé, e roda na outra máquina.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ra_abas as RAA  # noqa: E402

TELA = (RAIZ / "templates" / "atrib_livro3_ficha.html").read_text(encoding="utf-8-sig")
ATO_DO_BALCAO = {"id": 7, "tipo": "AV", "numero": 2, "origem": "MANUAL", "selo": None}
ATO_DO_ACERVO = {"id": 8, "tipo": "AV", "numero": 2, "origem": "EOFICIO", "selo": None}


def _r(situacao="ATIVO", **kw):
    return RAA.abas_do_registro({"situacao": situacao}, **kw)


def _chaves(r):
    return [x["chave"] for x in r["apoio"]]


def _aba(r, chave):
    return next(x for x in r["apoio"] if x["chave"] == chave)


def _textos(r):
    return [x["texto"] for x in r["espera"]]


def test_abre_no_resumo_e_nao_ha_fases():
    r = _r()
    assert r["inicial"] == RAA.RESUMO
    assert r["fases"] == [], "registro vivo não tem ordem a seguir"
    assert r["foco"] == RAA.TEOR


def test_aba_de_lista_vazia_nao_aparece_e_as_de_criar_ficam():
    assert _chaves(_r()) == [RAA.RESUMO, RAA.TEOR, RAA.PARTES, RAA.REVISAR, RAA.CERTIDOES, RAA.LANCAR]


def test_com_tudo_preenchido():
    r = _r(atos=[ATO_DO_BALCAO], minutas=[{}], certidoes=[{}, {}], partes=[{}], pode_corrigir=True)
    assert _chaves(r) == [RAA.RESUMO, RAA.ATOS, RAA.TEOR, RAA.PARTES, RAA.MINUTAS, RAA.REVISAR, RAA.CERTIDOES,
                          RAA.CORRIGIR, RAA.LANCAR]
    assert _aba(r, RAA.CERTIDOES)["contagem"] == 2
    assert _aba(r, RAA.LANCAR)["principal"] is True


def test_registro_cancelado_nao_lanca():
    assert RAA.LANCAR not in _chaves(_r("CANCELADO"))


def test_corrigir_e_so_de_quem_ve_o_quadro():
    assert RAA.CORRIGIR not in _chaves(_r(pode_corrigir=False))
    assert RAA.CORRIGIR in _chaves(_r(pode_corrigir=True))


def test_a_ata_de_ocorrencia_segura_a_aba_atos():
    assert RAA.ATOS in _chaves(_r(expurgos=[{}]))


def test_o_rascunho_antigo_segura_a_aba_minutas_sem_soar():
    """O rascunho de tela já «continuou aparecendo como se esperasse alguém»: fica à mão, sem alarme."""
    r = _r(rascunho={"id": 1})
    assert RAA.MINUTAS in _chaves(r) and _aba(r, RAA.MINUTAS)["alerta"] == 0
    assert r["espera"] == []


def test_ficha_em_dia_nao_tem_o_quadro():
    assert _r(atos=[{**ATO_DO_BALCAO, "selo": "AVESVD000000"}], partes=[{}])["espera"] == []


def test_o_acervo_nao_vira_alarme():
    """Ato antigo sem selo não é trabalho de hoje, e alarme que soa sempre ninguém ouve."""
    r = _r(atos=[ATO_DO_ACERVO])
    assert r["espera"] == []
    assert _aba(r, RAA.ATOS)["alerta"] == 0
    assert _aba(r, RAA.PARTES)["alerta"] == 0


def test_o_ato_do_balcao_sem_selo_leva_ao_botao_dele():
    r = _r(atos=[ATO_DO_BALCAO], partes=[{}])
    assert r["espera"] == [{"texto": "AV-2 lavrado e sem selo", "ir": "selar-ato-7", "botao": "Selar"}]
    assert _aba(r, RAA.ATOS)["alerta"] == 1
    assert 'id="selar-ato-{{ a.id }}"' in TELA, "o botão precisa do endereço que o quadro aponta"


def test_sem_partes_vem_antes_do_selo_porque_sem_elas_o_selo_nao_sai():
    r = _r(atos=[ATO_DO_BALCAO])
    assert "sem elas o selo não sai" in _textos(r)[0]
    assert r["espera"][0]["ir"] == RAA.PARTES
    assert _aba(r, RAA.PARTES)["alerta"] == 1


def test_minuta_a_revisar_cobra_as_partes_e_a_descartada_nao():
    assert "sem elas" in _textos(_r(minutas=[{"situacao": "A_REVISAR"}]))[0]
    r = _r(minutas=[{"situacao": "DESCARTADA"}, {"situacao": "LAVRADA"}], partes=[{}])
    assert r["espera"] == []
    assert _aba(r, RAA.MINUTAS)["contagem"] == 2 and _aba(r, RAA.MINUTAS)["alerta"] == 0


def test_minutas_e_notas_contam_so_as_abertas():
    r = _r(partes=[{}], minutas=[{"situacao": "A_REVISAR"}, {"situacao": "LAVRADA"}],
           revisoes=[{"situacao": "ABERTA"}, {"situacao": "ABERTA"}, {"situacao": "BAIXADA"}])
    assert _textos(r) == ["1 minuta(s) a revisar e lavrar", "2 ponto(s) a revisar antes de selar"]
    assert _aba(r, RAA.REVISAR)["alerta"] == 2


def _fora(id_, selo=None):
    return {"id": id_, "fora_do_lugar": True, "selo": selo}


def test_a_numeracao_so_cobra_o_que_o_balcao_lavrou():
    atos = [{**ATO_DO_BALCAO, "selo": "AVESVD"}, {**ATO_DO_ACERVO, "selo": "AVESVD"}]
    assert RAA.numeracao_a_corrigir([_fora(8)], atos) == []
    assert RAA.numeracao_a_corrigir([_fora(7)], atos) == [_fora(7)]
    assert RAA.numeracao_a_corrigir([{"id": 7, "fora_do_lugar": False}], atos) == []


def test_a_numeracao_nao_cobra_o_que_a_rota_recusaria():
    """Um ato fora do lugar com selo faz `renumerar` recusar o registro inteiro."""
    atos = [ATO_DO_BALCAO, {**ATO_DO_ACERVO, "id": 9}]
    assert RAA.numeracao_a_corrigir([_fora(7), _fora(9, selo="AVESVD")], atos) == []
    fonte = (RAIZ / "ra_correcoes.py").read_text(encoding="utf-8")
    assert 'com_selo = [a for a in fora if _texto(a["selo"])]' in fonte, "a recusa mudou"


def test_a_numeracao_so_avisa_quem_pode_corrigir():
    atos = [{**ATO_DO_BALCAO, "selo": ""}]
    assert any("numeração" in t for t in _textos(_r(atos=atos, partes=[{}], numeracao=[_fora(7)], pode_corrigir=True)))
    assert not any("numeração" in t for t in _textos(_r(atos=atos, partes=[{}], numeracao=[_fora(7)])))
    r = _r(atos=atos, partes=[{}], numeracao=[_fora(7)], pode_corrigir=True)
    assert _aba(r, RAA.CORRIGIR)["alerta"] == 1


# ------------------------------------------------------------ o domínio é o mesmo


def test_as_palavras_sao_as_dos_modulos():
    import ra_minuta as MIN
    import ra_revisao as RREV
    assert RAA.A_REVISAR == MIN.A_REVISAR and RAA.ABERTA == RREV.ABERTA
    assert "selectattr('situacao', 'equalto', 'A_REVISAR')" in TELA
    assert "selectattr('situacao', 'equalto', 'ABERTA')" in TELA
    assert "{% if registro.situacao == 'ATIVO' %}" in TELA, "o Lançar é o quadro desta condição"


def test_corrigir_tem_a_mesma_condicao_do_quadro():
    assert "abas_da_ficha(user.role in ['ADMIN','MANAGER'])" in TELA
    trecho = TELA[:TELA.index('data-fase="corrigir"')]
    assert trecho.rstrip().endswith('<section class="panel"')
    assert trecho.rstrip().rsplit("\n", 1)[0].rstrip().endswith("{% if user.role in ['ADMIN','MANAGER'] %}")


# ------------------------------------------------------------ o molde


def test_todo_quadro_diz_a_aba():
    """Quadro novo sem `data-fase` apareceria em todas as abas, sem ninguém pedir."""
    assert [m for m in re.findall(r"<section\b[^>]*>", TELA) if "data-fase" not in m] == []


def test_cada_chave_do_molde_existe_na_regua():
    r = _r(atos=[ATO_DO_BALCAO], minutas=[{}], pode_corrigir=True)
    no_molde = set(re.findall(r'data-fase="([a-z]+)"', TELA)) | {"resumo"}
    assert no_molde == set(_chaves(r)), no_molde ^ set(_chaves(r))


def test_o_alerta_de_fraude_sai_em_todas_as_abas():
    """O que ameaça o ato não pode ficar escondido numa aba."""
    inicio = TELA.index("{% block content %}")
    assert "alerta_fraude(fraudes" in TELA[inicio:TELA.index('data-fase="resumo"')]
    assert "data-fase" not in next(x for x in TELA.splitlines() if "alerta_fraude(fraudes" in x)


def test_a_certidao_tem_a_aba_dela_e_o_layout_antigo_nao_ve_a_caixa():
    assert '{% if abas %}<div data-fase="certidoes">{% endif %}' in TELA


def test_o_estilo_novo_so_vale_no_layout_novo():
    assert TELA.count("<style>") == 1
    assert re.search(r"\{% if abas %\}\{\{ abre_ficha\(VERSION\) \}\}.*?</style>\{% endif %\}", TELA, re.S)
    assert '{% if abas %}<div class="cg-ato-teor">{% endif %}' in TELA


def test_o_cancelamento_vem_recolhido_e_continua_o_mesmo_formulario():
    """Cancelar é a exceção. O formulário é um só, e no layout antigo a caixa não existe."""
    abre = TELA.index('{% if abas %}<details class="cg-cancelar"><summary>Cancelar o registro</summary>{% endif %}')
    fecha = TELA.index("{% if abas %}</details>{% endif %}", abre)
    assert 'name="tipo" value="CANCELAMENTO"' in TELA[abre:fecha]
    assert TELA.count('name="tipo" value="CANCELAMENTO"') == 1


def test_as_frases_nao_apontam_para_o_que_mudou_de_lugar():
    assert "{% if abas %}na aba Atos{% else %}mais abaixo{% endif %}" in TELA
    assert "{% if abas %}da aba Atos{% else %}abaixo{% endif %}" in TELA
    assert "{% if abas %}na aba Lançar{% else %}no" in TELA
    assert "onde_a_varredura=('na aba Teor e imagem' if abas else 'acima')" in TELA
    assert "onde_a_varredura='acima'" in (RAIZ / "templates" / "_certidao.html").read_text(encoding="utf-8-sig")


def test_o_layout_antigo_nao_chama_as_abas():
    assert "{% set abas = abas_da_ficha(user.role in ['ADMIN','MANAGER']) if layout_novo else none %}" in TELA
    assert "{% if abas %}{{ o_que_espera(abas.espera, 'resumo') }}{% endif %}" in TELA


# ------------------------------------------------------------- com o sistema de pé


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _entrar(app, usuario: str, papel: str = "ADMIN"):
    d = app.extensions["db"]
    try:
        d.create_user(usuario, "Operador Exemplo", "Senha#12345", papel)
    except Exception:                                              # noqa: BLE001
        pass
    c = app.test_client()
    c.post("/login", data={"username": usuario, "password": "Senha#12345",
                           "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def _registro(app, numero: int, origem: str = "MANUAL") -> int:
    from bd_nativo import banco
    d = app.extensions["db"]
    with d.transaction() as con:
        rid = banco(con).um(
            """INSERT INTO ra_registros (numero, natureza, teor, situacao, origem, criado_em)
               VALUES (%s, 'OUTRO', 'Teor de ensaio.', 'ATIVO', %s, %s) RETURNING id""",
            (numero, origem, d.now()))["id"]
        banco(con).escrever(
            """INSERT INTO ra_atos (registro_id, tipo, numero, data_ato, teor, origem, criado_em)
               VALUES (%s, 'R', 1, '2026-10-30', 'Ato de ensaio.', %s, %s)""",
            (rid, origem, d.now()))
    return rid


def _layout(c, qual: str) -> None:
    c.post("/preferencias/layout", data={
        "layout": qual, "next": "/", "csrf_token": _token(c.get("/").get_data(as_text=True))})


def test_a_regua_aparece_so_no_layout_novo(cg_app):
    rid = _registro(cg_app, 8801)
    c = _entrar(cg_app, "abas_l3_a")
    _layout(c, "antigo")
    antigo = c.get(f"/livro3/{rid}").get_data(as_text=True)
    assert "data-cg-regua" not in antigo and "O que espera ação" not in antigo and "selar-ato-" not in antigo
    _layout(c, "novo")
    novo = c.get(f"/livro3/{rid}").get_data(as_text=True)
    assert "data-cg-regua" in novo and 'data-inicial="resumo"' in novo
    assert "O que espera ação" in novo and "sem elas o selo não sai" in novo
    assert novo.count('id="selar-ato-') == 1


def test_o_acervo_abre_sem_o_quadro(cg_app):
    rid = _registro(cg_app, 8802, origem="EOFICIO")
    c = _entrar(cg_app, "abas_l3_b")
    _layout(c, "novo")
    assert "O que espera ação" not in c.get(f"/livro3/{rid}").get_data(as_text=True)


def test_para_o_balcao_nao_ha_aba_de_corrigir(cg_app):
    rid = _registro(cg_app, 8803)
    c = _entrar(cg_app, "abas_l3_c", "USER")
    _layout(c, "novo")
    novo = c.get(f"/livro3/{rid}").get_data(as_text=True)
    assert 'data-cg-fase="corrigir"' not in novo and 'data-cg-fase="lancar"' in novo
