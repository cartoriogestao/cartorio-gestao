"""**TODA ROTA TEM DE SER ALCANÇÁVEL POR UM CLIQUE — OU DIZER POR QUE NÃO É.**

POR QUE ESTE VARREDOR EXISTE
    O `test_funcao_sem_tela` pergunta se uma FUNÇÃO tem caminho até uma rota. O
    `test_debitos_do_balcao` pergunta se uma rota que grava é citada em alguma
    tela. Nenhum dos dois pergunta o que a revisão de telas de 30/10/2026
    perguntou: **saindo do menu e clicando, chego nela?**

    A resposta achou três buracos, e nenhum dava erro:

      - o **Livro de Pagamentos** do Protesto, que a inspeção de 2021 e a de
        2026 marcaram como inexistente, só tinha porta em «Livros obrigatórios»,
        que o escrevente não vê;
      - a **certidão diária em relação** e suas sete ações não tinham porta
        nenhuma; a tela existia desde o LG05, em 19/10/2026;
      - o **edital do usucapião pela Central do ONR** e o **mapa do ONR** idem.

COMO ELE PERGUNTA
    Só lê o código: não importa o sistema e não abre banco. Monta o grafo
    «rota -> telas que ela desenha -> `url_for` dessas telas», parte do que o
    `base.html` oferece em toda tela e anda. Rota citada num `.js` conta como
    alcançada, porque é a tela que a chama.

O QUE ELE NÃO PROVA
    `url_for(variavel)` não aparece no grafo. Por isso a lista de baixo é de
    **conhecidas, com o motivo de cada uma**, e o teste cobra as duas direções:
    rota nova sem porta reprova, e nome que ganhou porta tem de sair da lista.
"""
from __future__ import annotations

import ast
import re
from collections import defaultdict
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
TELAS = RAIZ / "templates"
ESTATICOS = RAIZ / "static"

_MOTIVO_JS = "chamada pelo script da tela, com o endereço montado na própria tela"
_MOTIVO_ATALHO = "endereço antigo que continua respondendo; a tela nova é outra"
_MOTIVO_IMPORTACAO = ("importação do E-Ofício terminada: o oficial mandou tirar o "
                      "botão e a rota fica, sem link")
_MOTIVO_WHATSAPP = ("substituída por `whatsapp_detalhes` na segunda revisão do #73: "
                    "setor, responsável e «Usa IA» se mudam de uma vez só")

# AS CONHECIDAS. **Esta lista só pode encolher**, e cada uma diz por que não tem
# porta — lista sem motivo vira depósito.
SEM_PORTA_DE_PROPOSITO: dict[str, str] = {
    # Quem chama não é uma pessoa.
    "ccn_ponte_consulta": "ponte local do assinador A3, chamada pela extensão",
    "ccn_ponte_lote": "ponte local do assinador A3, chamada pela extensão",
    "ccn_ponte_resultado": "ponte local do assinador A3, chamada pela extensão",
    "health": "sonda do instalador e do monitoramento",
    "whatsapp_webhook": "quem chama é a Meta",
    # Quem chama é o script da tela.
    "nu_avisos_fechar_modal": _MOTIVO_JS,
    "nu_avisos_pendentes_json": _MOTIVO_JS,
    "revisao_previa_notas_ultima": _MOTIVO_JS,
    "revisao_previa_ri_ultima": _MOTIVO_JS,
    # Entrada no sistema: o próprio sistema redireciona para elas.
    "login_dois_fatores": "a entrada redireciona para ela",
    "login_dois_fatores_cadastrar": "a entrada redireciona para ela",
    "setup": "a primeira instalação redireciona para ela",
    # Endereços antigos.
    "caixa_emolumentos_buscar": "atalho de busca para robôs e testes; a tela usa ?busca=",
    "expedientes_prontos": _MOTIVO_ATALHO,
    "nu_avisos_admin_lista": _MOTIVO_ATALHO,
    "protesto_pendencias_atalho": _MOTIVO_ATALHO,
    "protesto_titulos_legacy": _MOTIVO_ATALHO,
    "relatorio_selos": _MOTIVO_ATALHO,
    "ri_aplicar_modelo": "a montagem do ato passou para `ri_preencher`; sobrou o endereço",
    "ri_modelos": _MOTIVO_ATALHO,
    # Tiradas do menu por ordem do oficial.
    "atribuicoes_importar": _MOTIVO_IMPORTACAO,
    "caixa_importar": _MOTIVO_IMPORTACAO,
    "cnib_credencial_do_acervo": _MOTIVO_IMPORTACAO,
    "livro3_importar_acervo": _MOTIVO_IMPORTACAO,
    "notas_assinaturas": _MOTIVO_IMPORTACAO,
    "notas_importar": _MOTIVO_IMPORTACAO,
    "protesto_cenprot_xml_apresentantes_do_acervo": _MOTIVO_IMPORTACAO,
    "protesto_importar_eoficio": _MOTIVO_IMPORTACAO,
    "rcpn_importar_acervo": _MOTIVO_IMPORTACAO,
    "ri_importar": _MOTIVO_IMPORTACAO,
    # As etiquetas saíram da tela por ordem do oficial; os dados ficam.
    "whatsapp_etiqueta": "as etiquetas saíram da tela na segunda revisão do #73",
    "whatsapp_devolver": _MOTIVO_WHATSAPP,
    "whatsapp_passar": _MOTIVO_WHATSAPP,
    "whatsapp_transferir": _MOTIVO_WHATSAPP,
}


def _rotas_e_saidas() -> tuple[dict[str, dict], dict[str, set[str]], dict[str, set[str]]]:
    """Endpoint -> dados da rota; função -> telas; função -> `url_for` dela.

    **O QUE O AJUDANTE DESENHA CONTA COMO DESENHADO PELA ROTA.** `whatsapp_lista`
    chama `_tela_do_chat`, e é este que chama `render_template`: sem seguir a
    chamada, todas as ações da tela do WhatsApp apareciam sem porta.
    """
    rotas: dict[str, dict] = {}
    telas_da_funcao: dict[str, set[str]] = defaultdict(set)
    urls_da_funcao: dict[str, set[str]] = defaultdict(set)
    chamadas: dict[str, set[str]] = defaultdict(set)

    def _texto(no):
        return no.value if isinstance(no, ast.Constant) and isinstance(no.value, str) else None

    for arquivo in sorted(RAIZ.glob("*.py")):
        fonte = arquivo.read_text(encoding="utf-8", errors="replace")
        try:
            arvore = ast.parse(fonte)
        except SyntaxError:
            continue
        pilha: list[str] = []

        class Visita(ast.NodeVisitor):
            def visit_FunctionDef(self, f):
                pilha.append(f.name)
                for d in f.decorator_list:
                    if (isinstance(d, ast.Call) and isinstance(d.func, ast.Attribute)
                            and d.func.attr == "route" and d.args):
                        regra = _texto(d.args[0])
                        metodos = ["GET"]
                        for k in d.keywords:
                            if k.arg == "methods" and isinstance(k.value, (ast.List, ast.Tuple)):
                                metodos = [_texto(x) for x in k.value.elts if _texto(x)]
                        dados = rotas.setdefault(f.name, {"regras": [], "metodos": set()})
                        if regra:
                            dados["regras"].append(regra)
                        dados["metodos"].update(metodos)
                self.generic_visit(f)
                pilha.pop()

            visit_AsyncFunctionDef = visit_FunctionDef

            def visit_Call(self, c):
                nome = (c.func.id if isinstance(c.func, ast.Name)
                        else c.func.attr if isinstance(c.func, ast.Attribute) else "")
                if nome and pilha:
                    chamadas[pilha[-1]].add(nome)
                if c.args and pilha:
                    alvo = _texto(c.args[0])
                    if alvo and nome == "render_template":
                        for f in pilha:
                            telas_da_funcao[f].add(alvo)
                    elif alvo and nome == "url_for":
                        for f in pilha:
                            urls_da_funcao[f].add(alvo)
                self.generic_visit(c)

        Visita().visit(arvore)

    def _ajudantes(funcao: str, vistas: set[str]) -> None:
        for outra in chamadas.get(funcao, ()):
            if outra not in vistas and (outra in telas_da_funcao
                                        or outra in urls_da_funcao
                                        or (outra.startswith("_") and outra in chamadas)):
                vistas.add(outra)
                _ajudantes(outra, vistas)

    for endpoint in rotas:
        ajudantes: set[str] = set()
        _ajudantes(endpoint, ajudantes)
        for ajudante in ajudantes:
            telas_da_funcao[endpoint] |= telas_da_funcao.get(ajudante, set())
            urls_da_funcao[endpoint] |= urls_da_funcao.get(ajudante, set())
    return rotas, telas_da_funcao, urls_da_funcao


_COMENTARIO = re.compile(r"\{#.*?#\}", re.S)
_URL_FOR = re.compile(r"url_for\(\s*['\"]([\w.]+)['\"]")
_INCLUI = re.compile(r"\{%-?\s*(?:include|import|from|extends)\s+['\"]([^'\"]+)['\"]")


def _ler_tela(nome: str) -> str:
    caminho = TELAS / nome
    if not caminho.is_file():
        return ""
    return _COMENTARIO.sub("", caminho.read_text(encoding="utf-8", errors="replace"))


def _urls_da_tela(nome: str, vistas: set[str] | None = None) -> set[str]:
    """Os `url_for` de uma tela e do que ela inclui. `base.html` não entra: é o ponto de partida."""
    vistas = vistas if vistas is not None else set()
    if nome in vistas:
        return set()
    vistas.add(nome)
    texto = _ler_tela(nome)
    fora = set(_URL_FOR.findall(texto))
    for outra in _INCLUI.findall(texto):
        if outra != "base.html":
            fora |= _urls_da_tela(outra, vistas)
    return fora


def _casa(regra: str, caminho: str) -> bool:
    padrao = re.sub(r"<[^>]+>", "[^/]+", regra)
    return re.fullmatch(padrao, caminho.rstrip("/") or "/") is not None


def fora_de_alcance() -> dict[str, dict]:
    """As rotas que nenhum clique alcança, saindo do que o `base.html` oferece."""
    rotas, telas_da_funcao, urls_da_funcao = _rotas_e_saidas()
    saidas: dict[str, set[str]] = defaultdict(set)
    for endpoint in rotas:
        for tela in telas_da_funcao.get(endpoint, ()):
            saidas[endpoint] |= _urls_da_tela(tela)
        saidas[endpoint] |= urls_da_funcao.get(endpoint, set())

    alcance = _urls_da_tela("base.html") | {"dashboard"}
    fila = list(alcance)
    while fila:
        for outra in saidas.get(fila.pop(), ()):
            if outra not in alcance:
                alcance.add(outra)
                fila.append(outra)

    caminhos_de_script = set()
    for js in ESTATICOS.glob("*.js"):
        caminhos_de_script |= set(re.findall(
            r"[\"'`](/[A-Za-z0-9_\-/]+)", js.read_text(encoding="utf-8", errors="replace")))
    return {e: d for e, d in rotas.items()
            if e not in alcance
            and not any(_casa(r, c) for r in d["regras"] for c in caminhos_de_script)}


def test_toda_rota_tem_porta_ou_diz_por_que_nao_tem():
    novas = sorted(set(fora_de_alcance()) - set(SEM_PORTA_DE_PROPOSITO))
    assert not novas, (
        "estas rotas não têm clique que chegue nelas — ponha o link na tela certa "
        "ou declare o motivo em SEM_PORTA_DE_PROPOSITO:\n  " + "\n  ".join(novas))


def test_a_lista_de_conhecidas_nao_vira_deposito():
    sobrando = sorted(set(SEM_PORTA_DE_PROPOSITO) - set(fora_de_alcance()))
    assert not sobrando, (
        "estas ganharam porta ou deixaram de existir; tire-as da lista:\n  "
        + "\n  ".join(sobrando))


def test_o_varredor_continua_enxergando_as_rotas():
    """**Varredor que deixa de achar passa calado.**"""
    rotas, _, _ = _rotas_e_saidas()
    assert len(rotas) >= 1000, f"só {len(rotas)} rotas: o padrão parou de casar"
    assert len(_urls_da_tela("base.html")) >= 190, "o menu encolheu ou o padrão parou de casar"


def test_os_livros_e_os_repasses_do_protesto_estao_no_menu():
    """O Livro de Pagamentos é o que a inspeção marcou como inexistente, duas vezes."""
    menu = _ler_tela("base.html")
    for endpoint in ("protesto_livro", "protesto_repasses", "protesto_relacao_diaria"):
        assert f"url_for('{endpoint}'" in menu, endpoint


def test_o_edital_do_onr_tem_porta_na_ficha_do_usucapiao():
    assert "url_for('ri_onr_edital'" in _ler_tela("usucapiao_ficha.html")


def test_o_mapa_do_onr_tem_porta_e_so_quem_baixa_a_ve():
    tela = _ler_tela("ri_onr.html")
    assert "url_for('ri_mapa_onr_csv')" in tela
    assert "user.role == 'ADMIN'" in tela, "a rota é só do ADMIN (`ri_mapa_onr.QUEM_BAIXA`)"
