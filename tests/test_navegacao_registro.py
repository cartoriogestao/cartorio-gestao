"""**NENHUM DESTINO DO MENU ANTIGO SE PERDE NO LAYOUT NOVO.**

POR QUE ESTE TESTE EXISTE
    O oficial pediu a revisão antes da troca: «confirmar que nenhuma tela antiga se
    perdeu». Comparar à mão 220 links, papel por papel, envelheceria na tarde em que se
    fizesse. Aqui a comparação é com o próprio `base.html`: o menu antigo é lido com as
    condições dele, para cada papel, e o que o registro oferece tem de ser igual.

SÓ LÊ O CÓDIGO: não importa o app e não abre banco.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import navegacao as NAV  # noqa: E402

BASE = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
BASE_NOVO = (RAIZ / "templates" / "base_novo.html").read_text(encoding="utf-8")
PAPEIS = ("ADMIN", "MANAGER", "USER", "AUDITOR")

_TOKEN = re.compile(r"\{%-?\s*(if|elif|else|endif)\b(.*?)-?%\}|<a\b[^>]*href=\"\{\{\s*url_for\('([\w.]+)'([^)]*)\)\s*\}\}\"[^>]*>", re.S)


class _Usuario:
    def __init__(self, papel):
        self.role = papel


class _Falso:
    """O que o menu pergunta e não decide o destino: `global_stats.overdue`, `mod_notas`."""
    def __getattr__(self, _nome):
        return False

    def __bool__(self):
        return False


class _Ambiente(dict):
    def __missing__(self, _nome):
        return _Falso()


def _vale(condicao: str, papel: str, flags: dict) -> bool:
    """Avalia a condição do Jinja como Python, com o que o menu usa."""
    ambiente = _Ambiente({"user": _Usuario(papel), "MODULOS_ESCONDIDOS": flags.get("escondidos", []),
                          "ajuda_liberada": flags.get("ajuda_liberada", True),
                          "agente_no_menu": flags.get("agente_no_menu", True)})
    return bool(eval(condicao, {"__builtins__": {}}, ambiente))  # noqa: S307


def _args(texto: str) -> tuple:
    achados = re.findall(r"(\w+)\s*=\s*(?:'([^']*)'|(\d+))", texto)
    return tuple(sorted((k, a or b) for k, a, b in achados))


def menu_antigo(papel: str, **flags) -> set[tuple[str, tuple]]:
    """O que o `base.html` oferece àquele papel: (endpoint, argumentos)."""
    sem_comentario = re.sub(r"\{#.*?#\}", "", BASE, flags=re.S)
    trecho = sem_comentario[sem_comentario.index("<nav>"):sem_comentario.index("</nav>")]
    pilha: list[dict] = []
    fora: set[tuple[str, tuple]] = set()
    for m in _TOKEN.finditer(trecho):
        marca, condicao, endpoint, args = m.groups()
        if marca == "if":
            ok = _vale(condicao.strip(), papel, flags)
            pilha.append({"ativo": ok, "ja": ok})
        elif marca == "elif":
            ok = not pilha[-1]["ja"] and _vale(condicao.strip(), papel, flags)
            pilha[-1].update(ativo=ok, ja=pilha[-1]["ja"] or ok)
        elif marca == "else":
            pilha[-1]["ativo"] = not pilha[-1]["ja"]
        elif marca == "endif":
            pilha.pop()
        elif all(p["ativo"] for p in pilha):
            fora.add((endpoint, _args(args)))
    return fora


def menu_novo(papel: str, escondidos=(), ajuda_liberada=True, agente_no_menu=True) -> set[tuple[str, tuple]]:
    flags = NAV._flags(ajuda_liberada, agente_no_menu, escondidos)
    return {(e["endpoint"], tuple(sorted((k, str(v)) for k, v in e["args"].items())))
            for e in NAV.entradas(papel, flags)} | {("dashboard", ())}


@pytest.mark.parametrize("papel", PAPEIS)
def test_o_registro_oferece_o_mesmo_que_o_menu_antigo(papel):
    antigo = menu_antigo(papel)
    novo = menu_novo(papel)
    perdidos = sorted(antigo - novo)
    assert not perdidos, f"{papel}: destinos do menu antigo que o layout novo perdeu:\n  " + "\n  ".join(map(str, perdidos))
    sobrando = sorted(novo - antigo - NAV.ENTRADAS_NOVAS)
    assert not sobrando, f"{papel}: o layout novo oferece o que o antigo não oferecia:\n  " + "\n  ".join(map(str, sobrando))


@pytest.mark.parametrize("papel", PAPEIS)
@pytest.mark.parametrize("flags", [
    {"ajuda_liberada": False},
    {"agente_no_menu": False},
    {"escondidos": ["PROTESTO"]},
    {"escondidos": ["APOSTILA"]},
])
def test_as_condicoes_do_menu_valem_nos_dois(papel, flags):
    """A ajuda fechada, o agente desligado, o Protesto e a Apostila escondidos."""
    antigo = menu_antigo(papel, **flags)
    novo = menu_novo(papel, **{k: v for k, v in flags.items()})
    perdidos = sorted(antigo - novo)
    sobrando = sorted(novo - antigo - NAV.ENTRADAS_NOVAS)
    assert not perdidos and not sobrando, (papel, flags, perdidos, sobrando)


def _rotas() -> dict[str, list[str]]:
    """Endpoint -> regras, lidos do código sem importar o app."""
    rotas: dict[str, list[str]] = {}
    for arquivo in RAIZ.glob("*.py"):
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                for d in no.decorator_list:
                    if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                            and d.func.attr == "route" and d.args
                            and isinstance(d.args[0], ast.Constant)):
                        rotas.setdefault(no.name, []).append(d.args[0].value)
    # Os seis submódulos de modelos: `add_url_rule` com o nome numa tabela.
    fonte = (RAIZ / "modelos_elementos_web.py").read_text(encoding="utf-8")
    for nome in re.findall(r'"(\w+_modelos_papeis)"', fonte):
        rotas.setdefault(nome, [])
    return rotas


def _todas_as_entradas():
    yield NAV.ENTRADA_DO_INICIO
    for m in NAV.MODULOS_DA_BARRA:
        for _, itens in m["secoes"]:
            yield from itens
    for grupo in NAV.NOVO:
        yield from grupo["itens"]


def test_todo_endereco_do_registro_existe():
    rotas = _rotas()
    faltam = sorted({e["endpoint"] for e in _todas_as_entradas()
                     if e.get("endpoint") and e["endpoint"] not in rotas}
                    | {e for e in NAV.PAI if e not in rotas and e not in NAV_ROTAS_DINAMICAS})
    assert not faltam, f"o registro cita rotas que não existem: {faltam}"


NAV_ROTAS_DINAMICAS: frozenset[str] = frozenset()


def test_toda_entrada_traz_os_argumentos_que_a_rota_exige():
    """Sem o argumento, o `url_for` falha e a entrada some em silêncio do menu."""
    rotas = _rotas()
    erradas = []
    for e in _todas_as_entradas():
        if not e.get("endpoint") or not rotas.get(e["endpoint"]):
            continue
        for regra in rotas[e["endpoint"]][:1]:
            exigidos = set(re.findall(r"<(?:\w+:)?(\w+)>", regra))
            if not exigidos <= set(e.get("args", {})):
                erradas.append((e["endpoint"], sorted(exigidos)))
    assert not erradas, erradas


def test_toda_secao_citada_em_pai_existe():
    secoes = {(m["chave"], nome) for m in NAV.MODULOS_DA_BARRA for nome, _ in m["secoes"]}
    erradas = sorted(v for v in NAV.PAI.values() if v not in secoes)
    assert not erradas, f"PAI aponta para seção que não existe: {erradas}"


def _paginas_com_moldura() -> dict[str, str]:
    """As rotas que desenham uma página com `base.html`, com a tela de cada uma."""
    telas = {}
    for p in (RAIZ / "templates").glob("*.html"):
        if re.search(r"\{%-?\s*extends\s+['\"]base\.html['\"]", p.read_text(encoding="utf-8", errors="replace")):
            telas[p.name] = True
    paginas: dict[str, str] = {}
    for arquivo in RAIZ.glob("*.py"):
        try:
            arvore = ast.parse(arquivo.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for no in ast.walk(arvore):
            if not isinstance(no, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if not any(isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                       and d.func.attr == "route" for d in no.decorator_list):
                continue
            for c in ast.walk(no):
                if (isinstance(c, ast.Call) and isinstance(c.func, ast.Name)
                        and c.func.id == "render_template" and c.args
                        and isinstance(c.args[0], ast.Constant)
                        and c.args[0].value in telas):
                    paginas[no.name] = c.args[0].value
    return paginas


# A TELA DE ENTRAR NÃO TEM MODULO: quem a vê ainda não está na casca.
SEM_LUGAR_NA_BARRA = frozenset({"login", "login_dois_fatores", "login_dois_fatores_cadastrar", "setup",
                                "minha_senha", "dois_fatores", "dois_fatores_codigos", "dois_fatores_confirmar"})


def test_a_busca_so_procura_onde_a_pessoa_entra():
    """Opção que leva à recusa é clique perdido: Protesto fechado tira os títulos da busca."""
    def endereco(rota, **args):
        return f"/{rota}"
    aberto = NAV.montar("dashboard", {}, "ADMIN", endereco)
    fechado = NAV.montar("dashboard", {}, "USER", endereco, escondidos=("PROTESTO",))
    assert "protesto_titulos" in {p["u"].strip("/") for p in aberto["procurar"]}
    assert "protesto_titulos" not in {p["u"].strip("/") for p in fechado["procurar"]}
    assert "ri_matriculas" in {p["u"].strip("/") for p in fechado["procurar"]}


def test_toda_pagina_tem_lugar_na_barra():
    """Tela sem lugar abre com a barra fechada: quem chega nela não sabe onde está."""
    conhecidas = {e["endpoint"] for e in _todas_as_entradas() if e.get("endpoint")} | set(NAV.PAI)
    conhecidas |= {"dashboard", "notas_ato"} | SEM_LUGAR_NA_BARRA
    sem_lugar = sorted(set(_paginas_com_moldura()) - conhecidas)
    assert not sem_lugar, "ponha em `navegacao.PAI` (módulo, seção):\n  " + "\n  ".join(sem_lugar)


def test_a_busca_acha_pelo_nome_antigo():
    """Quem decorou o menu antigo continua achando: o nome de lá vale na busca."""
    sem_comentario = re.sub(r"\{#.*?#\}", "", BASE, flags=re.S)
    trecho = sem_comentario[sem_comentario.index("<nav>"):sem_comentario.index("</nav>")]
    rotulos = re.findall(r"<a\b[^>]*href=\"\{\{\s*url_for\('[\w.]+'[^)]*\)\s*\}\}\"[^>]*>(.*?)</a>", trecho, re.S)
    limpos = {re.sub(r"\s+", " ", re.sub(r"<[^>]+>|\{%.*?%\}|\{\{.*?\}\}", "", r, flags=re.S)).replace("&mdash;", "—").strip() for r in rotulos}
    conhecidos = set()
    for e in _todas_as_entradas():
        conhecidos.update((e.get("rotulo", ""), e.get("antigo", "")))
    # O mesmo nome genérico em vários módulos fica no rótulo e na seção de cada um.
    faltam = sorted(r for r in limpos if r and r not in conhecidos)
    assert not faltam, f"nomes do menu antigo que a busca não acha: {faltam}"


def test_a_lista_de_scripts_e_a_mesma_nas_duas_molduras():
    """Tela que depende da lupa ou da ajuda não pode funcionar só numa das molduras."""
    pega = re.compile(r"filename='([\w\-]+\.js)'")
    antigo = set(pega.findall(re.sub(r"\{#.*?#\}", "", BASE, flags=re.S)))
    novo = set(pega.findall(BASE_NOVO)) - {"casca.js"}
    assert antigo == novo, (sorted(antigo - novo), sorted(novo - antigo))


def test_a_moldura_nova_preenche_os_mesmos_blocos():
    pega = re.compile(r"\{%-?\s*block\s+(\w+)")
    assert set(pega.findall(BASE)) == set(pega.findall(BASE_NOVO))


def test_os_avisos_que_nao_fecham_continuam_a_vista_na_moldura_nova():
    """Ordens do oficial: estes não vão para o sino, e não se fecham."""
    area = BASE_NOVO[BASE_NOVO.index('class="cg-area"'):BASE_NOVO.index('class="cg-topo"')]
    for parcial in ("_caixa_aviso.html", "_digi_aviso.html", "_rc_digi_aviso.html",
                    "_selo_trava_aviso.html", "_gratuidade_aviso.html",
                    "_selo_cancelamento_aviso.html"):
        assert parcial in area, parcial


def test_a_coluna_de_apoio_leva_as_tres_ferramentas_de_sempre():
    apoio = BASE_NOVO[BASE_NOVO.index('class="cg-apoio"'):BASE_NOVO.index("</aside>")]
    for parcial in ("_whatsapp_atalho.html", "_produtividade_rapida.html", "_ajuda.html", "_agente.html"):
        assert parcial in apoio, parcial


def test_a_casca_nao_escreve_cor_de_modulo_a_mao():
    css = (RAIZ / "static" / "casca.css").read_text(encoding="utf-8")
    for m in NAV.POR_CHAVE.values():
        assert m["cor"].lower() not in css.lower(), m["chave"]
