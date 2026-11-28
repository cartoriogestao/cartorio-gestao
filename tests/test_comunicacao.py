"""A COMUNICAÇÃO DA CASA (T028, 28/11/2026) — conversas de todos e avisos que insistem.

O PEDIDO (R1–R12 em `ti/relatorios/2026-11-28-T028-pedido.md`) e a decisão do titular
na rodada 2: admin, gerente e TI mandam aviso; todo usuário conversa com qualquer outro;
destino do aviso é toda a equipe, um grupo ou uma pessoa.

O QUE SE PROVA AQUI
    - a regra dos graus (sinal → faixa → cartão) nas bordas de cada urgência;
    - quem manda aviso (ADMIN, MANAGER, TI) e quem não manda (USER, AUDITOR: 403);
    - a tela de quem recebe em cada grau, nos dois layouts;
    - que no grau máximo o trabalho continua (sem modal, sem `inert`, a tela grava);
    - «estou fazendo» acaba com a insistência e fica na trilha e no `audit_logs`;
    - «recolher», «feito», «encerrar» e o «vi» (que só o POST grava);
    - o mensageiro: conversa direta entre quaisquer dois, grupo, «vista», resposta,
      edição de 15 min, anexo só para quem participa, busca sem acento, texto escapado.

NOMES: todos fictícios, «de teste», como manda a regra da casa.
"""
from __future__ import annotations

import io
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import comunicacao as CM            # noqa: E402
import comunicacao_avisos as CA     # noqa: E402
from bd_nativo import banco         # noqa: E402

SENHA = "Senha#12345"
ISO = "%Y-%m-%dT%H:%M:%S"
T0 = datetime(2026, 11, 28, 9, 0, 0)


def _t(minutos: float = 0, base: datetime = T0) -> str:
    return (base + timedelta(minutes=minutos)).strftime(ISO)


# =============================================================== a regra (só calcula)

@pytest.mark.parametrize("minutos, esperado", [
    (0, CA.SINAL), (14.98, CA.SINAL), (15, CA.FAIXA), (59.98, CA.FAIXA), (60, CA.CARTAO), (600, CA.CARTAO),
])
def test_normal_sinal_faixa_aos_15_cartao_aos_60(minutos, esperado):
    assert CA.grau(CA.NORMAL, _t(), _t(minutos)) == esperado


@pytest.mark.parametrize("minutos, esperado", [(0, CA.FAIXA), (9.98, CA.FAIXA), (10, CA.CARTAO)])
def test_urgente_faixa_na_hora_cartao_aos_10(minutos, esperado):
    assert CA.grau(CA.URGENTE, _t(), _t(minutos)) == esperado


def test_imediata_e_cartao_desde_o_envio():
    assert CA.grau(CA.IMEDIATA, _t(), _t()) == CA.CARTAO


def test_o_grau_nunca_desce_com_o_tempo():
    graus = [CA.grau(CA.NORMAL, _t(), _t(m)) for m in range(0, 180, 3)]
    assert graus == sorted(graus)


def test_o_cartao_recolhido_fica_faixa_e_volta_sozinho():
    ate = _t(65)
    assert CA.grau(CA.NORMAL, _t(), _t(61), recolhido_ate=ate) == CA.FAIXA
    assert CA.grau(CA.NORMAL, _t(), _t(65), recolhido_ate=ate) == CA.CARTAO
    # recolher não rebaixa a faixa a sinal
    assert CA.grau(CA.NORMAL, _t(), _t(20), recolhido_ate=_t(25)) == CA.FAIXA


def test_quando_sobe_de_grau():
    assert CA.proximo_grau_em(CA.NORMAL, _t(), _t(3)) == _t(15)
    assert CA.proximo_grau_em(CA.NORMAL, _t(), _t(20)) == _t(60)
    assert CA.proximo_grau_em(CA.NORMAL, _t(), _t(61)) is None


def test_o_texto_da_mensagem_e_escapado_e_os_links_ligados():
    import comunicacao_web as W
    html = str(W._texto_html('<script>alert(1)</script>\nveja http://casa:5000/ri/1, e https://fora.example/x.',
                             "casa:5000"))
    assert "<script>" not in html and "&lt;script&gt;" in html
    assert '<a href="http://casa:5000/ri/1" target="_top">' in html
    assert 'href="https://fora.example/x" target="_blank" rel="noopener noreferrer"' in html
    assert "<br>" in html and html.endswith(".")


# =============================================================== a casa de teste

PAPEIS = {"mario": "ADMIN", "gina": "MANAGER", "tiago": "TI", "ester": "USER",
          "ana": "USER", "carla": "AUDITOR"}


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    ids = {}
    for login, papel in PAPEIS.items():
        db.create_user(login, f"{login.upper()} DE TESTE", SENHA, papel)
    with db.connect() as con:
        for linha in banco(con).ler("SELECT id, username FROM users"):
            ids[linha["username"]] = int(linha["id"])
    cg_casa["ids"] = ids
    return cg_casa


def _entrar(casa, login: str, layout: str | None = None):
    from conftest import cg_login
    c = casa["app"].test_client()
    cg_login(c, login, SENHA)
    if layout:
        r = _post(c, "/preferencias/layout", layout=layout, next="/minha-rotina")
        assert r.status_code == 302
    return c


def _token(c) -> str:
    with c.session_transaction() as s:
        token = s.get("csrf_token")
    if token:
        return token
    html = c.get("/minha-rotina").get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _post(c, url: str, *, fetch: bool = False, **dados):
    cabecalhos = {"X-Requested-With": "fetch"} if fetch else {}
    dados.setdefault("csrf_token", _token(c))
    return c.post(url, data=dados, headers=cabecalhos)


def _aviso(casa, de: str = "gina", **campos) -> int:
    c = _entrar(casa, de)
    dados = {"titulo": "Conferir os selos do lote de ontem",
             "texto": "Antes de fechar o caixa, conferir se os 40 selos do lote 3 saíram.",
             "urgencia": CA.NORMAL, "destino_tipo": CA.TODOS}
    dados.update(campos)
    r = _post(c, "/comunicacao/avisos/novo", **dados)
    assert r.status_code == 302, r.get_data(as_text=True)[:400]
    return int(re.search(r"/comunicacao/avisos/(\d+)", r.headers["Location"]).group(1))


def _envelhecer(casa, aviso_id: int, minutos: float) -> None:
    """Faz de conta que o aviso saiu há `minutos` (o grau é calculado pelo envio)."""
    quando = (datetime.now() - timedelta(minutes=minutos)).replace(microsecond=0).strftime(ISO)
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE cm_avisos SET criado_em=%s WHERE id=%s", (quando, aviso_id))


def _destino(casa, aviso_id: int, login: str) -> dict:
    with casa["db"].connect() as con:
        return banco(con).um("SELECT * FROM cm_aviso_destinos WHERE aviso_id=%s AND user_id=%s",
                             (aviso_id, casa["ids"][login]))


def _eventos(casa, aviso_id: int, login: str | None = None) -> list[str]:
    with casa["db"].connect() as con:
        if login:
            linhas = banco(con).ler("SELECT evento FROM cm_aviso_eventos WHERE aviso_id=%s AND user_id=%s "
                                    "ORDER BY id", (aviso_id, casa["ids"][login]))
        else:
            linhas = banco(con).ler("SELECT evento FROM cm_aviso_eventos WHERE aviso_id=%s ORDER BY id",
                                    (aviso_id,))
    return [x["evento"] for x in linhas]


def _tela(c, url: str = "/minha-rotina") -> str:
    r = c.get(url)
    assert r.status_code == 200, (url, r.status_code)
    return r.get_data(as_text=True)


def _tem_cartao(html: str) -> bool:
    return 'class="cm-cartao' in html


def _tem_faixa(html: str) -> bool:
    return 'class="cm-faixa"' in html


# =============================================================== R3: quem manda aviso

@pytest.mark.parametrize("login", ["mario", "gina", "tiago"])
def test_admin_gerente_e_ti_mandam_aviso(casa, login):
    aid = _aviso(casa, de=login)
    assert _destino(casa, aid, "ester")["situacao"] == CA.ESPERANDO


@pytest.mark.parametrize("login", ["ester", "carla"])
def test_escrevente_e_auditor_nao_mandam_aviso(casa, login):
    c = _entrar(casa, login)
    assert c.get("/comunicacao/avisos/novo").status_code == 403
    r = _post(c, "/comunicacao/avisos/novo", titulo="X", urgencia="NORMAL", destino_tipo="TODOS")
    assert r.status_code == 403
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM cm_avisos") == 0


def test_a_regra_recusa_quem_nao_manda_mesmo_sem_a_rota(casa):
    with casa["db"].transaction() as con, pytest.raises(PermissionError):
        CA.criar(con, titulo="X", texto="", urgencia=CA.NORMAL, destino_tipo=CA.TODOS, destino_ref=None,
                 por=casa["ids"]["ester"], papel="USER", agora=_t())


def test_o_auditor_confere_os_avisos_e_o_escrevente_nao(casa):
    aid = _aviso(casa)
    assert _entrar(casa, "carla").get(f"/comunicacao/avisos/{aid}").status_code == 200
    assert _entrar(casa, "ester").get("/comunicacao/avisos").status_code == 403


def test_destino_toda_equipe_tira_quem_mandou_inativo_e_robo(casa):
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE users SET active=0 WHERE username='ana'")
        banco(con).escrever("UPDATE users SET eh_robo=1 WHERE username='tiago'")
    aid = _aviso(casa)
    with casa["db"].connect() as con:
        quem = {x["user_id"] for x in banco(con).ler("SELECT user_id FROM cm_aviso_destinos WHERE aviso_id=%s", (aid,))}
    ids = casa["ids"]
    assert ids["ester"] in quem and ids["mario"] in quem and ids["carla"] in quem
    assert ids["gina"] not in quem and ids["ana"] not in quem and ids["tiago"] not in quem


def test_destino_uma_pessoa_e_um_grupo_por_atribuicao(casa):
    ids = casa["ids"]
    aid = _aviso(casa, destino_tipo=CA.DESTINO_PESSOA, pessoa_id=str(ids["ana"]))
    assert _destino(casa, aid, "ana") and not _destino(casa, aid, "ester")
    # o grupo «Registro de Imóveis», criado por um escrevente, serve de destino
    with casa["db"].transaction() as con:
        gid = CM.criar_grupo(con, nome="Registro de Imóveis", membros_ids=[ids["ana"]],
                             criado_por=ids["ester"], agora=_t())
    aid2 = _aviso(casa, destino_tipo=CA.DESTINO_GRUPO, grupo_id=str(gid))
    assert _destino(casa, aid2, "ana") and _destino(casa, aid2, "ester") and not _destino(casa, aid2, "mario")
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT destino_rotulo FROM cm_avisos WHERE id=%s", (aid2,)) == "Grupo Registro de Imóveis"


# =============================================================== R4–R8: a tela de quem recebe

@pytest.mark.parametrize("layout", ["novo", "antigo"])
def test_grau_1_so_o_sinal_na_coluna_da_direita(casa, layout):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 5)
    html = _tela(_entrar(casa, "ester", layout))
    assert re.search(r'class="cm-atalho cm-com-aviso"', html)
    assert re.search(r"data-cm-conta[^>]*>1<", html)
    assert not _tem_faixa(html) and not _tem_cartao(html)


@pytest.mark.parametrize("layout", ["novo", "antigo"])
def test_grau_2_a_faixa_sem_botao_de_fechar(casa, layout):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 20)
    html = _tela(_entrar(casa, "ester", layout))
    assert _tem_faixa(html) and not _tem_cartao(html)
    faixa = html[html.index('class="cm-faixa"'):]
    faixa = faixa[:faixa.index("</section>")]
    assert "Conferir os selos do lote de ontem" in faixa and "Estou fazendo" in faixa
    assert "Fechar" not in faixa and "×" not in faixa and "data-aviso" not in faixa
    assert "vira cartão às" in faixa


@pytest.mark.parametrize("layout", ["novo", "antigo"])
def test_grau_3_o_cartao_completo_no_canto_superior_direito(casa, layout):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 70)
    html = _tela(_entrar(casa, "ester", layout))
    assert _tem_cartao(html) and not _tem_faixa(html)
    cartao = html[html.index('class="cm-cartao'):]
    cartao = cartao[:cartao.index("</section>")]
    assert "Antes de fechar o caixa, conferir se os 40 selos do lote 3 saíram." in cartao
    assert "GINA DE TESTE" in cartao and "Estou fazendo" in cartao and "Recolher por 5 min" in cartao
    css = (RAIZ / "static" / "comunicacao.css").read_text(encoding="utf-8")
    regra = re.search(r"\.cm-cartao\{([^}]*)\}", css).group(1)
    assert "position:fixed" in regra and "top:" in regra and "right:" in regra


def test_no_grau_maximo_o_trabalho_continua(casa):
    """R7: o cartão não é modal — a tela segue inteira, clicável, e grava."""
    aid = _aviso(casa, urgencia=CA.IMEDIATA)
    c = _entrar(casa, "ester")
    html = _tela(c, "/caixa/protocolos")
    assert _tem_cartao(html)
    cartao = html[html.index('class="cm-cartao'):]
    cartao = cartao[:cartao.index("</section>")]
    assert 'role="region"' in cartao
    assert "aria-modal" not in cartao and "alertdialog" not in cartao and "<dialog" not in cartao
    assert " inert" not in html
    # a tela de trabalho continua lá, com os formulários dela
    assert html.count("<form") > 4
    # e grava: com o cartão na tela, outra ação do sistema passa normalmente
    r = _post(c, "/comunicacao/grupos/novo", nome="Balcão", membros=str(casa["ids"]["ana"]))
    assert r.status_code == 302
    assert _destino(casa, aid, "ester")["situacao"] == CA.ESPERANDO
    # nem o estilo nem o script travam a página
    css = (RAIZ / "static" / "comunicacao.css").read_text(encoding="utf-8")
    js = (RAIZ / "static" / "comunicacao.js").read_text(encoding="utf-8")
    assert "pointer-events:none" not in css.replace(" ", "")
    for proibido in ("showModal", ".inert", "aria-modal", "overflow = \"hidden\"", "preventDefault();\n      return false"):
        assert proibido not in js


def test_harmonicamente_sem_som_sem_piscar_e_com_menos_movimento(casa):
    css = (RAIZ / "static" / "comunicacao.css").read_text(encoding="utf-8")
    js = (RAIZ / "static" / "comunicacao.js").read_text(encoding="utf-8")
    tpl = "".join(p.read_text(encoding="utf-8") for p in (RAIZ / "templates").glob("*comunicacao*.html"))
    reduzido = css[css.index("@media (prefers-reduced-motion:reduce)"):]
    assert ".cm-cartao{animation:none" in reduzido.replace(" ", "")
    assert "45s" in re.search(r"\.cm-cartao\{[^}]*\}", css).group(0)
    assert "<audio" not in tpl and "Audio(" not in js and "AudioContext" not in js
    assert "blink" not in css
    assert 'aria-live="polite"' in tpl


def test_estou_fazendo_acaba_a_insistencia_e_fica_na_trilha(casa):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 70)
    c = _entrar(casa, "ester")
    assert _tem_cartao(_tela(c))
    r = _post(c, f"/comunicacao/avisos/{aid}/fazendo", next="/minha-rotina")
    assert r.status_code == 302 and r.headers["Location"].endswith("/minha-rotina")
    html = _tela(c)
    assert not _tem_cartao(html) and not _tem_faixa(html)
    assert 'class="cm-atalho cm-com-aviso"' not in html
    d = _destino(casa, aid, "ester")
    assert d["situacao"] == CA.FAZENDO and d["fazendo_em"] and d["visto_em"]
    assert "FAZENDO" in _eventos(casa, aid, "ester")
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT COUNT(*) FROM audit_logs WHERE action='COMUNICACAO_AVISO_FAZENDO' "
                                "AND entity_id=%s AND user_id=%s", (aid, casa["ids"]["ester"])) == 1
    # repetir não grava de novo; o outro escrevente continua sendo cobrado
    _post(c, f"/comunicacao/avisos/{aid}/fazendo", fetch=True)
    assert _eventos(casa, aid, "ester").count("FAZENDO") == 1
    assert _tem_cartao(_tela(_entrar(casa, "ana")))


def test_feito_depois_de_fazendo_e_feito_direto(casa):
    aid = _aviso(casa)
    c = _entrar(casa, "ester")
    _post(c, f"/comunicacao/avisos/{aid}/fazendo", fetch=True)
    r = _post(c, f"/comunicacao/avisos/{aid}/feito", fetch=True)
    assert r.get_json() == {"ok": True}
    assert _destino(casa, aid, "ester")["situacao"] == CA.FEITO
    ana = _entrar(casa, "ana")
    _post(ana, f"/comunicacao/avisos/{aid}/feito", fetch=True)
    d = _destino(casa, aid, "ana")
    assert d["situacao"] == CA.FEITO and d["fazendo_em"] and d["feito_em"]
    assert _eventos(casa, aid, "ana") == ["FAZENDO", "FEITO"]


def test_recolher_desce_o_cartao_a_faixa_e_ele_volta(casa):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 70)
    c = _entrar(casa, "ester")
    r = _post(c, f"/comunicacao/avisos/{aid}/recolher", fetch=True)
    assert r.get_json()["ok"]
    html = _tela(c)
    assert _tem_faixa(html) and not _tem_cartao(html) and "recolhido até" in html
    assert _destino(casa, aid, "ester")["recolhidas"] == 1
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE cm_aviso_destinos SET recolhido_ate=%s WHERE aviso_id=%s",
                            ((datetime.now() - timedelta(seconds=1)).strftime(ISO), aid))
    assert _tem_cartao(_tela(c))
    assert "RECOLHIDA" in _eventos(casa, aid, "ester")


def test_so_o_cartao_se_recolhe(casa):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 20)
    r = _post(_entrar(casa, "ester"), f"/comunicacao/avisos/{aid}/recolher", fetch=True)
    assert r.status_code == 400 and "cartão" in r.get_json()["erro"]


def test_o_vi_e_as_subidas_de_grau_ficam_gravados_so_pelo_post(casa):
    aid = _aviso(casa)
    _envelhecer(casa, aid, 20)
    c = _entrar(casa, "ester")
    _tela(c)
    c.get("/comunicacao/estado.json")
    assert _eventos(casa, aid, "ester") == []          # GET não grava
    _post(c, "/comunicacao/avisos/visto", fetch=True, ids=str(aid))
    assert _eventos(casa, aid, "ester") == ["VISTA", "SUBIU_GRAU"]
    _post(c, "/comunicacao/avisos/visto", fetch=True, ids=str(aid))
    assert _eventos(casa, aid, "ester") == ["VISTA", "SUBIU_GRAU"]   # o mesmo grau não grava de novo
    _envelhecer(casa, aid, 70)
    _post(c, "/comunicacao/avisos/visto", fetch=True, ids=str(aid))
    assert _eventos(casa, aid, "ester") == ["VISTA", "SUBIU_GRAU", "SUBIU_GRAU"]
    assert _destino(casa, aid, "ester")["grau_max"] == CA.CARTAO
    # quem não recebeu o aviso não grava nada nele
    _post(_entrar(casa, "gina"), "/comunicacao/avisos/visto", fetch=True, ids=str(aid))
    assert not _eventos(casa, aid, "gina")[1:]


def test_o_estado_redesenha_a_insistencia_sem_recarregar(casa):
    aid = _aviso(casa)
    c = _entrar(casa, "ester")
    j = c.get("/comunicacao/estado.json").get_json()
    assert j["esperando"] == 1 and j["grau"] == CA.SINAL and "cm-cartao" not in j["html"]
    _envelhecer(casa, aid, 70)
    j2 = c.get("/comunicacao/estado.json").get_json()
    assert j2["grau"] == CA.CARTAO and 'class="cm-cartao' in j2["html"] and j2["versao"] != j["versao"]


def test_encerrar_tira_da_tela_de_todos(casa):
    aid = _aviso(casa, de="mario")
    gerente = _entrar(casa, "gina")
    assert _post(gerente, f"/comunicacao/avisos/{aid}/encerrar").status_code == 403
    aid2 = _aviso(casa, de="gina", urgencia=CA.IMEDIATA)
    assert _post(gerente, f"/comunicacao/avisos/{aid2}/encerrar").status_code == 302
    assert _post(_entrar(casa, "mario"), f"/comunicacao/avisos/{aid}/encerrar").status_code == 302
    html = _tela(_entrar(casa, "ester"))
    assert not _tem_cartao(html) and not _tem_faixa(html)
    assert "ENCERRADA" in _eventos(casa, aid2)


def test_o_acompanhamento_mostra_quem_viu_fazendo_e_feito(casa):
    aid = _aviso(casa)
    _post(_entrar(casa, "ester"), f"/comunicacao/avisos/{aid}/fazendo", fetch=True)
    html = _tela(_entrar(casa, "gina"), f"/comunicacao/avisos/{aid}")
    assert "ESTER DE TESTE" in html and "Fazendo" in html and "Esperando" in html
    lista = _tela(_entrar(casa, "gina"), "/comunicacao/avisos")
    assert "Conferir os selos do lote de ontem" in lista


# =============================================================== R2: a coluna da direita

def test_o_botao_esta_na_coluna_da_direita_acima_do_whatsapp():
    base = (RAIZ / "templates" / "base_novo.html").read_text(encoding="utf-8")
    apoio = base[base.index('class="cg-apoio"'):base.index("</aside>", base.index('class="cg-apoio"'))]
    assert apoio.index("_comunicacao_atalho.html") < apoio.index("_whatsapp_atalho.html")


def test_a_tela_mostra_o_botao_e_a_gaveta_nos_dois_layouts(casa):
    novo = _tela(_entrar(casa, "ester", "novo"))
    apoio = novo[novo.index('class="cg-apoio"'):]
    assert "data-cm-abrir" in apoio[:apoio.index("</aside>")]
    assert 'data-src="/comunicacao/painel"' in novo
    antigo = _tela(_entrar(casa, "ana", "antigo"))
    assert "data-cm-atalho-caixa" in antigo and 'data-layout="novo"' not in antigo


def test_a_gaveta_abre_sem_moldura_e_sem_insistencia_em_dobro(casa):
    _aviso(casa, urgencia=CA.IMEDIATA)
    html = _tela(_entrar(casa, "ester"), "/comunicacao/painel")
    assert "data-cm-app" in html and "cm-corpo-embutido" in html
    assert "data-cm-insistencia" not in html and 'class="cg-apoio"' not in html


# =============================================================== o mensageiro

def test_todo_usuario_conversa_com_qualquer_outro(casa):
    ids = casa["ids"]
    ester, carla = _entrar(casa, "ester"), _entrar(casa, "carla")
    r = _post(ester, f"/comunicacao/para/{ids['carla']}/enviar", fetch=True, texto="Oi, Carla! <b>teste</b>")
    j = r.get_json()
    assert j["ok"] and "/comunicacao/painel" not in j["url"]
    cid = j["conversa_id"]
    assert carla.get("/comunicacao/estado.json").get_json()["nao_lidas"] == 1
    html = _tela(carla, f"/comunicacao?c={cid}")
    assert "Oi, Carla! &lt;b&gt;teste&lt;/b&gt;" in html and "Novas mensagens" in html
    # a resposta, pela mesma conversa (a direta é sempre a mesma)
    r2 = _post(carla, f"/comunicacao/para/{ids['ester']}/enviar", fetch=True, texto="Oi!")
    assert r2.get_json()["conversa_id"] == cid
    # o «li até aqui» só pelo POST
    assert carla.get("/comunicacao/estado.json").get_json()["nao_lidas"] == 0   # respondeu: leu
    novas = ester.get(f"/comunicacao/c/{cid}/novas?depois={j['mensagem_id']}").get_json()
    assert "Oi!" in novas["html"] and "Vista" in novas["recibo"]


def test_quem_nao_participa_nao_le_nem_escreve(casa):
    ids = casa["ids"]
    r = _post(_entrar(casa, "ester"), f"/comunicacao/para/{ids['ana']}/enviar", fetch=True, texto="segredo")
    cid = r.get_json()["conversa_id"]
    intruso = _entrar(casa, "mario")
    assert intruso.get(f"/comunicacao?c={cid}").status_code == 404
    assert intruso.get(f"/comunicacao/c/{cid}/novas?depois=0").status_code == 404
    assert _post(intruso, f"/comunicacao/c/{cid}/enviar", texto="oi").status_code == 404
    busca = _tela(intruso, "/comunicacao/buscar?q=segredo")
    assert "Nada encontrado" in busca and 'class="cm-achados"' not in busca


def test_a_lista_de_conversas_tem_previa_e_nao_lidas(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    _post(ester, f"/comunicacao/para/{ids['ana']}/enviar", fetch=True, texto="Primeira")
    _post(ester, f"/comunicacao/para/{ids['ana']}/enviar", fetch=True, texto="Segunda mensagem")
    html = _tela(_entrar(casa, "ana"), "/comunicacao/painel")
    item = html[html.index('class="cm-item'):]
    assert "ESTER DE TESTE" in item[:600] and "Segunda mensagem" in item[:900]
    assert re.search(r'aria-label="2 não lida\(s\)">2<', html)


def test_o_mesmo_envio_repetido_nao_sai_em_dobro(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    a = _post(ester, f"/comunicacao/para/{ids['ana']}/enviar", fetch=True, texto="uma vez", token="tok-1").get_json()
    b = _post(ester, f"/comunicacao/c/{a['conversa_id']}/enviar", fetch=True, texto="uma vez", token="tok-1").get_json()
    assert a["mensagem_id"] == b["mensagem_id"]


def test_grupo_vista_por_n_de_m_e_resposta(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    r = _post(ester, "/comunicacao/grupos/novo", nome="Protesto", membros=[str(ids["ana"]), str(ids["carla"])])
    cid = int(re.search(r"c=(\d+)", r.headers["Location"]).group(1))
    m1 = _post(ester, f"/comunicacao/c/{cid}/enviar", fetch=True, texto="Bom dia, grupo").get_json()["mensagem_id"]
    ana = _entrar(casa, "ana")
    _post(ana, f"/comunicacao/c/{cid}/lida", fetch=True, ate=str(m1))
    recibo = ester.get(f"/comunicacao/c/{cid}/novas?depois={m1}").get_json()["recibo"]
    assert "Vista por 1 de 2" in recibo and "ANA DE TESTE" in recibo
    _post(ana, f"/comunicacao/c/{cid}/enviar", fetch=True, texto="Bom dia!", resposta_a=str(m1))
    novas = ester.get(f"/comunicacao/c/{cid}/novas?depois={m1}").get_json()["html"]
    assert 'class="cm-citacao"' in novas and "Bom dia, grupo" in novas and "ANA DE TESTE" in novas


def test_quem_gere_o_grupo_e_quem_sai(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    r = _post(ester, "/comunicacao/grupos/novo", nome="Notas", membros=str(ids["ana"]))
    cid = int(re.search(r"c=(\d+)", r.headers["Location"]).group(1))
    ana = _entrar(casa, "ana")
    assert _post(ana, f"/comunicacao/grupos/{cid}", acao="renomear", nome="Outro").status_code == 403
    assert _post(_entrar(casa, "gina"), f"/comunicacao/grupos/{cid}", acao="renomear",
                 nome="Tabelionato de Notas").status_code == 302
    assert _post(ana, f"/comunicacao/grupos/{cid}", acao="sair").status_code == 302
    assert ana.get(f"/comunicacao?c={cid}").status_code == 404
    # nome de grupo não se repete
    r2 = _post(ester, "/comunicacao/grupos/novo", nome="tabelionato de notas", membros=str(ids["carla"]))
    assert r2.status_code == 200 and "Já existe um grupo" in r2.get_data(as_text=True)


def test_editar_e_apagar_so_a_propria_e_so_por_15_minutos(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    j = _post(ester, f"/comunicacao/para/{ids['ana']}/enviar", fetch=True, texto="texto com erro").get_json()
    mid = j["mensagem_id"]
    assert _post(_entrar(casa, "ana"), f"/comunicacao/m/{mid}/editar", fetch=True, texto="x").status_code == 400
    assert _post(ester, f"/comunicacao/m/{mid}/editar", fetch=True, texto="texto certo").get_json()["ok"]
    with casa["db"].connect() as con:
        hist = banco(con).ler("SELECT evento, texto_antes FROM cm_mensagens_historico WHERE mensagem_id=%s", (mid,))
    assert hist == [{"evento": "EDITADA", "texto_antes": "texto com erro"}]
    with casa["db"].transaction() as con:
        banco(con).escrever("UPDATE cm_mensagens SET criada_em=%s WHERE id=%s",
                            ((datetime.now() - timedelta(minutes=16)).strftime(ISO), mid))
    r = _post(ester, f"/comunicacao/m/{mid}/apagar", fetch=True)
    assert r.status_code == 400 and "15 minutos" in r.get_json()["erro"]
    j2 = _post(ester, f"/comunicacao/c/{j['conversa_id']}/enviar", fetch=True, texto="esta sai").get_json()
    assert _post(ester, f"/comunicacao/m/{j2['mensagem_id']}/apagar", fetch=True).get_json()["ok"]
    html = _tela(_entrar(casa, "ana"), f"/comunicacao?c={j['conversa_id']}")
    assert "Mensagem apagada" in html and "esta sai" not in html and "texto certo" in html


def test_anexo_so_para_quem_participa_e_so_tipos_seguros(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    png = b"\x89PNG\r\n\x1a\n" + b"0" * 64
    r = ester.post(f"/comunicacao/para/{ids['ana']}/enviar",
                   data={"csrf_token": _token(ester), "texto": "o print",
                         "anexo": (io.BytesIO(png), "tela.png")},
                   headers={"X-Requested-With": "fetch"}, content_type="multipart/form-data")
    assert r.get_json()["ok"], r.get_data(as_text=True)
    with casa["db"].connect() as con:
        aid = banco(con).valor("SELECT id FROM cm_anexos")
    baixado = _entrar(casa, "ana").get(f"/comunicacao/anexo/{aid}")
    assert baixado.status_code == 200 and baixado.data == png and baixado.mimetype == "image/png"
    assert _entrar(casa, "mario").get(f"/comunicacao/anexo/{aid}").status_code == 404
    ruim = ester.post(f"/comunicacao/para/{ids['ana']}/enviar",
                      data={"csrf_token": _token(ester), "texto": "x",
                            "anexo": (io.BytesIO(b"<script>"), "pagina.html")},
                      headers={"X-Requested-With": "fetch"}, content_type="multipart/form-data")
    assert ruim.status_code == 400 and "tipo de arquivo" in ruim.get_json()["erro"]


def test_a_busca_acha_sem_acento_so_nas_proprias_conversas(casa):
    ids = casa["ids"]
    _post(_entrar(casa, "ester"), f"/comunicacao/para/{ids['ana']}/enviar", fetch=True,
          texto="Certidão de ônus pronta no balcão")
    html = _tela(_entrar(casa, "ana"), "/comunicacao/buscar?q=certidao onus")
    assert "Certidão de ônus pronta no balcão" in html


def test_o_esquema_roda_de_novo_sem_erro(casa):
    with casa["db"].transaction() as con:
        CM.init_comunicacao_schema(con)
        CM.init_comunicacao_schema(con)


# =============================================================== toda tela abre

def test_toda_tela_da_comunicacao_abre_nas_duas_molduras(casa):
    ids = casa["ids"]
    ester = _entrar(casa, "ester")
    r = _post(ester, "/comunicacao/grupos/novo", nome="Caixa", membros=str(ids["ana"]))
    cid = int(re.search(r"c=(\d+)", r.headers["Location"]).group(1))
    _post(ester, f"/comunicacao/c/{cid}/enviar", fetch=True, texto="oi, grupo")
    aid = _aviso(casa, destino_tipo=CA.DESTINO_GRUPO, grupo_id=str(cid))
    for url in ("/comunicacao", f"/comunicacao?c={cid}", f"/comunicacao?para={ids['carla']}",
                "/comunicacao?aba=avisos", f"/comunicacao?aba=avisos&aviso={aid}",
                "/comunicacao/painel", f"/comunicacao/painel?c={cid}", "/comunicacao/painel?aba=avisos",
                "/comunicacao/grupos/novo", "/comunicacao/grupos/novo?embutido=1",
                f"/comunicacao/grupos/{cid}", f"/comunicacao/grupos/{cid}?embutido=1",
                "/comunicacao/buscar?q=grupo", "/comunicacao/buscar?q=grupo&embutido=1"):
        html = _tela(ester, url)
        assert "Traceback" not in html, url
    assert "Registro de Imóveis" in _tela(ester, "/comunicacao/grupos/novo")   # sugestão por atribuição
    gina = _entrar(casa, "gina")
    for url in ("/comunicacao/avisos", "/comunicacao/avisos/novo", f"/comunicacao/avisos/{aid}"):
        _tela(gina, url)
    # a gestão abre o grupo de que não participa, para gerir
    assert "Mudar o grupo" in _tela(gina, f"/comunicacao/grupos/{cid}")
    assert _entrar(casa, "carla").get(f"/comunicacao/grupos/{cid}").status_code == 404


def test_o_voltar_nao_leva_para_fora_da_casa(casa):
    aid = _aviso(casa)
    c = _entrar(casa, "ester")
    for fora in ("//fora.example/x", "/\\fora.example", "https://fora.example/"):
        r = _post(c, f"/comunicacao/avisos/{aid}/abri", next=fora)
        assert "fora.example" not in r.headers["Location"], fora
