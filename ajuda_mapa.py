"""
O QUE A AJUDA SABE DESTA INSTALAÇÃO — o mapa, e ele é MEDIDO.

POR QUE ELE EXISTE
    A instrução de `ajuda.py` conta ao modelo qual é a serventia e quais são as
    normas. Isso basta para dúvida jurídica e não basta para a pergunta mais
    comum do balcão, que é de USO: «onde é que eu lanço isto?», «esta tela é a
    de qual livro?», «que erro é este?».

    Sem o mapa, a resposta a essas é chute educado — e chute educado num
    cartório é pior que «não sei», porque parece certo.

O MAPA NÃO SE ESCREVE: MEDE-SE
    Escrever à mão a lista das telas é o defeito que o menu deste sistema já
    cometeu e pagou. Está escrito em `base.html`, com todas as letras:

        «A primeira versão listava as rotas de cada módulo à mão. Envelheceu na
        mesma tarde em que foi escrita: nove nomes que eu supus e não existiam,
        e vinte e três rotas reais de fora.»

    Aqui seria pior, porque quem lê a lista velha não é um operador que
    estranha — é uma máquina que responde com convicção. Então tudo o que sai
    daqui vem de medição:

      - as telas e os endereços, de `app.url_map`;
      - o NOME de cada tela, do próprio menu (`templates/base.html`) — é o
        nome que a casa usa, e não um que eu inventasse agora;
      - o dono de cada tela, de `view_functions[...].__module__`, que é o
        arquivo de verdade e não o que eu suporia pelo prefixo;
      - as tabelas e as colunas, do catálogo do banco desta máquina;
      - o que cada módulo é, da primeira linha da docstring dele.

    Nada aqui é adjetivo, e nada é lembrança minha do que o sistema tinha.

O MAPA NÃO CARREGA DADO DE CLIENTE, E ISSO SE PROVA
    Ele leva NOME de tabela e de coluna, e nunca o conteúdo delas. Um mapa que
    levasse valores mandaria dado do balcão para fora em toda pergunta, sem
    ninguém pedir — e a máscara do módulo protege o que o escrevente digita,
    não o que o sistema junta sozinho.

    `tests/test_ajuda_mapa.py` monta um banco com CPF, nome e endereço dentro e
    confere que nenhum deles aparece no mapa.

VAI UMA FATIA, E NÃO O MAPA INTEIRO
    São 219 telas e 106 tabelas nesta instalação. Mandar tudo em toda pergunta
    custaria em toda pergunta — e afogaria a dúvida no meio do inventário.

    Então vai o menu (que é o que responde «onde fica») e a FATIA da tela de
    onde a pergunta nasceu: o arquivo dela, as telas irmãs e as tabelas que
    aquele módulo abre. O resto fica aqui, para o relatório de problema, onde
    espaço não é dinheiro.

MEDIR CUSTA, E POR ISSO SE MEDE UMA VEZ
    Ler noventa arquivos e o catálogo do banco a cada pergunta seria pagar
    disco por uma resposta que não muda: o código não muda debaixo do servidor
    em execução. Mede-se na primeira consulta do processo e guarda-se na
    memória. `esquecer()` existe para o teste, que troca de banco a cada caso.
"""
from __future__ import annotations

import re
import sqlite3
from pathlib import Path
from typing import Any

# A REGRA DE «DE QUE MODULO E ESTA TELA» E A DE `modulos.py`, a mesma do menu.
# Escrever aqui uma segunda — e ela seria parecida, que e como duas regras
# divergem — faria a resposta a «o que mudou» nomear o modulo errado.
import modulos

# O teto do que vai junto da pergunta. Não é estética: é a conta do mês. Acima
# disto a fatia sai cortada, e o corte fica DITO no texto — mapa que some sem
# avisar faz o modelo responder como se aquilo não existisse.
LIMITE_DO_RESUMO = 9_000

# Os arquivos que não são o sistema: teste é sobre o sistema, e ferramenta é
# de quem empacota. Nenhum dos dois responde dúvida de balcão.
PASTAS_QUE_NAO_SAO_O_SISTEMA = {"tests", "tools", "installer", "__pycache__"}

RAIZ_PADRAO = Path(__file__).resolve().parent

_MEDIDO: dict | None = None


def esquecer() -> None:
    """Joga fora o mapa guardado. Só o teste precisa disto."""
    global _MEDIDO
    _MEDIDO = None


# ------------------------------------------------------------- as telas


def _endereco_de(app, endpoint: str) -> str:
    """O endereço mais simples da tela — o que se digita no navegador.

    Uma tela pode ter mais de uma regra (`/ajuda` e `/ajuda/<id>`). Vale a que
    não pede parâmetro: é a que alguém consegue abrir sozinho.
    """
    melhor = ""
    for regra in app.url_map.iter_rules(endpoint):
        texto = str(regra)
        if "<" in texto:
            melhor = melhor or texto
            continue
        if not melhor or "<" in melhor or len(texto) < len(melhor):
            melhor = texto
    return melhor


def _nomes_do_menu(raiz: Path) -> dict[str, str]:
    """O nome de cada tela, tirado do MENU e não da minha cabeça.

    `base.html` já traz o nome que a casa usa — «Reconhecer firma», «Trazer
    notas do E-Ofício». Qualquer outro nome que eu escrevesse aqui seria um
    segundo vocabulário para as mesmas telas, e o operador que perguntasse
    «onde fica X» ouviria de volta uma palavra que não está na tela dele.
    """
    try:
        html = (raiz / "templates" / "base.html").read_text(encoding="utf-8")
    except OSError:
        return {}

    def limpar(bruto: str) -> str:
        # O rótulo vem com Jinja dentro ({% if %}, contadores) e às vezes com
        # marcação. Fica o que uma pessoa leria na tela.
        texto = re.sub(r"\{[%{].*?[%}]\}", " ", bruto, flags=re.DOTALL)
        texto = re.sub(r"<[^>]+>", " ", texto)
        return re.sub(r"\s+", " ", texto).strip()

    # O GRUPO VAI JUNTO DO NOME, e passou a ir em 27/08/2026, quando cada
    # atribuição ganhou o seu próprio grupo no menu. Antes o link dizia
    # «Protesto — títulos» e o nome bastava sozinho; agora ele diz «Títulos»
    # dentro do grupo «Protesto», e há três «Certidões» no menu — uma do RI,
    # uma do Protesto e uma do Registro Civil.
    #
    # Sem o grupo, a ajuda responderia «vá em Certidões» a quem pergunta pela
    # certidão de nascimento, e o operador acharia a do Registro de Imóveis.
    # Com ele, a resposta sai como o caminho que se percorre: **Registro Civil
    # → Certidões**.
    achados: dict[str, str] = {}
    grupo = ""
    # O `[^)]*` NO `url_for` NAO E DETALHE: desde 27/08 há link de menu com
    # argumento — `url_for('rcpj_rtd_registros', atribuicao=3)`, que é como o
    # RCPJ e o RTD ganharam cada um a sua lista dentro da mesma tela. A versão
    # anterior exigia o parêntese logo depois do nome, e esses dois links
    # sumiam do mapa **em silêncio**: a ajuda passaria a não saber que existem.
    padrao = (r"<summary>(.*?)</summary>"
              r"|<a href=\"\{\{ url_for\('([a-z0-9_]+)'[^)]*\)[^\"]*\"[^>]*>(.*?)</a>")
    for titulo, endpoint, rotulo in re.findall(padrao, html, re.DOTALL):
        if titulo:
            grupo = limpar(titulo)
            continue
        texto = limpar(rotulo)
        if not texto:
            continue
        nome = f"{grupo} → {texto}" if grupo else texto
        if endpoint not in achados:
            achados[endpoint] = nome
        elif nome not in achados[endpoint]:
            # A MESMA TELA COM DOIS NOMES é o caso do RCPJ e do RTD: uma tela
            # só, dois lugares no menu, porque são duas atribuições. Guardar só
            # o primeiro faria a ajuda dizer que o RTD não existe.
            achados[endpoint] = f"{achados[endpoint]} · {texto}"
    return achados


# ---------------------------------------------------------- os arquivos


def _primeira_linha_da_docstring(fonte: str) -> str:
    """O que o módulo diz que é, na primeira linha dele.

    Todo módulo desta casa abre com uma docstring que explica por que ele
    existe. A primeira linha é a frase curta; o resto é a história, que não
    cabe numa pergunta de balcão.
    """
    texto = fonte.lstrip()
    for aspas in ('"""', "'''"):
        if not texto.startswith(aspas):
            continue
        fim = texto.find(aspas, len(aspas))
        corpo = texto[len(aspas):fim] if fim > 0 else texto[len(aspas):]
        for linha in corpo.splitlines():
            if linha.strip():
                return linha.strip()
    return ""


def _arquivos_do_sistema(raiz: Path) -> dict[str, dict]:
    achados: dict[str, dict] = {}
    for caminho in sorted(raiz.glob("*.py")):
        if caminho.parent.name in PASTAS_QUE_NAO_SAO_O_SISTEMA:
            continue
        try:
            fonte = caminho.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        achados[caminho.name] = {
            "arquivo": caminho.name,
            "o_que_e": _primeira_linha_da_docstring(fonte),
            "linhas": fonte.count("\n") + 1,
            "_fonte": fonte,
        }
    return achados


# ------------------------------------------------------------- o banco


def _tabelas(con: sqlite3.Connection) -> dict[str, list[str]]:
    """Os nomes das tabelas e das colunas desta instalação. Só LÊ.

    NÃO PERGUNTA O ESQUEMA AO BANCO PELA PORTA QUE SÓ O SQLite TEM — aquela
    que os módulos de esquema usam para decidir migração. Ela tem teto zero
    para módulo novo (`tests/test_portabilidade.py`), e aqui há caminho que
    custa o mesmo: um `SELECT` que não traz linha nenhuma devolve a descrição
    das colunas sem tirar do balcão um dado sequer.

    O catálogo (`sqlite_master`) continua sendo do SQLite; em Postgres o mesmo
    se lê de `information_schema`. Fica numa função só, que é onde a troca
    caberia num lugar só.

    (A porta não está escrita aqui com o nome dela de propósito. O varredor de
    portabilidade lê o arquivo inteiro, comentário incluído, e contaria a
    citação como se fosse uso — foi o que aconteceu na primeira versão deste
    módulo, e já tinha acontecido antes em `ajuda.py`. **Regra que se aplica ao
    arquivo inteiro alcança também o comentário que fala dela**, e desta vez o
    comentário é o segundo a aprender isso.)
    """
    achados: dict[str, list[str]] = {}
    try:
        nomes = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    except sqlite3.Error:
        return achados
    for nome in nomes:
        if nome.startswith("sqlite_"):
            continue
        try:
            cur = con.execute(f'SELECT * FROM "{nome}" LIMIT 0')
            achados[nome] = [d[0] for d in (cur.description or [])]
        except sqlite3.Error:
            achados[nome] = []
    return achados


# ------------------------------------------------------------- a medição


def medir(app, con: sqlite3.Connection, *, versao: str = "",
          raiz: Any = None) -> dict:
    """Mede o sistema como ele está nesta máquina, agora. Só LÊ.

    Não guarda nada: quem guarda é `do_processo`. Separado para o teste poder
    medir um sistema montado na hora sem herdar a medição de outro caso.
    """
    raiz = Path(raiz or RAIZ_PADRAO)
    arquivos = _arquivos_do_sistema(raiz)
    tabelas = _tabelas(con)
    nomes = _nomes_do_menu(raiz)

    telas: dict[str, dict] = {}
    for regra in app.url_map.iter_rules():
        endpoint = regra.endpoint
        if endpoint in telas or endpoint == "static":
            continue
        vista = app.view_functions.get(endpoint)
        # O DONO SAI DO PRÓPRIO PYTHON, e não do prefixo do nome. `usucapiao_*`
        # mora em `usucapiao_web.py`, mas `rcpn_*` e `protesto_*` moram os dois
        # em `atribuicoes_web.py` — supor pelo prefixo poria a ajuda mandando
        # quem conserta para o arquivo errado.
        modulo = getattr(vista, "__module__", "") or ""
        telas[endpoint] = {
            "endpoint": endpoint,
            "endereco": _endereco_de(app, endpoint),
            "arquivo": f"{modulo}.py" if modulo and modulo != "flask.app" else "",
            "nome": nomes.get(endpoint, ""),
            "no_menu": endpoint in nomes,
        }

    # QUE TABELAS CADA ARQUIVO ABRE — medido procurando o nome real da tabela
    # dentro do fonte do módulo. Não é perfeito (o nome pode aparecer num
    # comentário), e erra para MAIS: sobra tabela parente, não falta a certa.
    # Para dizer a quem conserta onde olhar, sobrar é barato e faltar é caro.
    for dados in arquivos.values():
        fonte = dados.pop("_fonte", "")
        # O `in` VEM ANTES DO `re`, e nao e capricho: sao 85 arquivos por 105
        # tabelas, e a busca com fronteira de palavra em todos os 8.925 pares
        # levava seis segundos — na primeira pergunta do dia, seis segundos
        # antes de a pergunta sequer sair. O `in` derruba quase todos os pares
        # a custo de comparacao de texto, e o `re` so decide os que sobram.
        dados["tabelas"] = [
            t for t in tabelas
            if t in fonte and re.search(rf"\b{re.escape(t)}\b", fonte)]

    return {
        "versao": versao,
        "telas": telas,
        "menu": [{"nome": nomes[e], "endereco": telas[e]["endereco"],
                  "endpoint": e} for e in nomes if e in telas],
        "arquivos": arquivos,
        "tabelas": tabelas,
        "quantas_telas": len(telas),
        "quantas_tabelas": len(tabelas),
        "quantos_arquivos": len(arquivos),
    }


def do_processo(app, con: sqlite3.Connection, *, versao: str = "") -> dict:
    """O mapa medido uma vez e guardado enquanto o servidor viver.

    O código não muda debaixo do servidor em execução — atualizar o sistema
    reinicia o serviço. Medir de novo a cada pergunta seria ler noventa
    arquivos para obter a mesma resposta.
    """
    global _MEDIDO
    if _MEDIDO is None or _MEDIDO.get("versao") != versao:
        _MEDIDO = medir(app, con, versao=versao)
    return _MEDIDO


# --------------------------------------------------------- a fatia da tela


def fatia(mapa: dict, onde: Any) -> dict:
    """O que interessa sobre a tela de onde a pergunta saiu. Só calcula.

    `onde` é o endpoint. Tela que não existe devolve fatia vazia — e vazia é
    melhor que inventada: a ajuda responde sem o contexto da tela em vez de
    responder sobre uma tela que não é aquela.
    """
    tela = (mapa.get("telas") or {}).get(str(onde or ""))
    if not tela:
        return {}
    arquivo = (mapa.get("arquivos") or {}).get(tela["arquivo"], {})
    irmas = [t for t in (mapa.get("telas") or {}).values()
             if t["arquivo"] == tela["arquivo"]
             and t["endpoint"] != tela["endpoint"]]
    return {
        "tela": tela,
        "arquivo": arquivo,
        "irmas": sorted(irmas, key=lambda t: t["endereco"]),
        "tabelas": {t: (mapa.get("tabelas") or {}).get(t, [])
                    for t in arquivo.get("tabelas", [])},
    }


def arquivo_da_tela(mapa: dict, onde: Any) -> str:
    """Em que arquivo mora esta tela. Para o relatório dizer onde consertar."""
    tela = (mapa.get("telas") or {}).get(str(onde or ""), {}) or {}
    return tela.get("arquivo", "")


# ----------------------------------------------------------- o texto que vai


def _linhas_do_menu(mapa: dict) -> list[str]:
    return [f"  {m['nome']} — {m['endereco']}" for m in mapa.get("menu", [])]


def _linhas_da_fatia(f: dict) -> list[str]:
    """O essencial de "em que tela estou": nome, endereço, arquivo e vizinhas.

    NÃO TRAZ AS TABELAS — achado em 08/09/2026. As colunas de cada tabela do
    arquivo (`_linhas_das_tabelas_da_fatia`) são o pedaço mais comprido da
    fatia, e o que se perde por último quando o mapa está pequeno é o que se
    ganha por perder primeiro quando ele está grande: a coluna de uma tabela é
    detalhe; saber que "esta tela mora em `caixa_web.py`" é o que a pergunta
    "onde fica" precisa para não vir respondida em tese.
    """
    if not f:
        return []
    tela, arquivo = f["tela"], f["arquivo"]
    linhas = [
        "",
        "A TELA DE ONDE A PERGUNTA SAIU",
        f"  {tela['nome'] or tela['endpoint']} — {tela['endereco']}",
    ]
    if arquivo.get("arquivo"):
        linhas.append(
            f"  Mora em {arquivo['arquivo']}"
            + (f" — {arquivo['o_que_e']}" if arquivo.get("o_que_e") else ""))
    if f["irmas"]:
        # O NOME QUANDO HÁ NOME, E O ENDEREÇO QUANDO NÃO HÁ. Tela que não está
        # no menu — a ficha de um ato, a montagem de uma minuta — não tem nome
        # escrito em lugar nenhum, e o endpoint é palavra de programador. O
        # endereço, ao menos, é o que aparece na barra do navegador de quem
        # está perguntando.
        vizinhas = ", ".join(t["nome"] or t["endereco"] for t in f["irmas"][:14])
        sobram = len(f["irmas"]) - 14
        linhas.append(f"  Telas do mesmo módulo: {vizinhas}"
                      + (f" e mais {sobram}" if sobram > 0 else ""))
    return linhas


def _linhas_das_tabelas_da_fatia(f: dict) -> list[str]:
    """As colunas das tabelas do arquivo da tela atual — o detalhe mais
    comprido da fatia, e por isso o que primeiro se sacrifica no corte."""
    if not f:
        return []
    linhas = []
    for nome, colunas in list(f["tabelas"].items())[:12]:
        corte = " …" if len(colunas) > 24 else ""
        linhas.append(f"  Tabela {nome}: {', '.join(colunas[:24])}{corte}")
    return linhas


def resumo(mapa: dict, onde: Any = None) -> str:
    """O bloco que vai junto da instrução. Só calcula — não fala com a rede.

    É a MESMA função que a tela usa para mostrar o que sairia. Uma segunda
    montagem parecida divergiria no primeiro conserto, e a tela passaria a
    mostrar uma coisa e a mandar outra — a lição que este módulo já aprendeu
    na prévia da pergunta.
    """
    if not mapa:
        return ""
    cabeca = [
        "O MAPA DESTA INSTALAÇÃO",
        (f"Medido nesta máquina, na versão "
         f"{mapa.get('versao') or 'A CONFERIR'}: "
         f"{mapa.get('quantas_telas', 0)} telas, "
         f"{mapa.get('quantas_tabelas', 0)} tabelas, "
         f"{mapa.get('quantos_arquivos', 0)} arquivos de programa."),
    ]
    # A ORDEM DE SACRIFÍCIO DO MIOLO TEM TRÊS DEGRAUS, NÃO DOIS — achado em
    # 08/09/2026. O mapa cresceu (451 telas) até a lista geral sozinha já
    # estourar o teto, e o corte — que sempre foi "a lista encolhe, nunca a
    # instrução" — comia a fatia da tela atual, porque ela vinha DEPOIS da
    # lista inteira no miolo. Quem pergunta já está numa tela: saber em que
    # arquivo ELA mora vale mais que a lista das outras 450.
    #
    # MAS A FATIA TEM UMA PARTE GRANDE E DISPENSÁVEL: as colunas de cada
    # tabela do arquivo. Pôr a fatia INTEIRA na frente da lista geral
    # resolvia o "onde mora esta tela" e estourava o "onde ficam as outras
    # telas" — o mesmo defeito, do lado oposto. As colunas vão por ÚLTIMO, e
    # são as primeiras a sumir quando o mapa não cabe.
    essencial_da_fatia = _linhas_da_fatia(fatia(mapa, onde))
    tabelas_da_fatia = _linhas_das_tabelas_da_fatia(fatia(mapa, onde))
    miolo = (essencial_da_fatia
             + ["", "AS TELAS DO MENU, COM O ENDEREÇO DE CADA UMA"]
             + _linhas_do_menu(mapa)
             + tabelas_da_fatia)
    rodape = [
        "",
        "COMO USAR ISTO",
        # ESTAS DUAS LINHAS SE MASCARAVAM SOZINHAS — achado em 08/09/2026. O
        # sanitizador trata "nome" como rótulo de dado pessoal
        # (`_NOME_ROTULADO`) mesmo dentro da instrução fixa, e capturava tudo
        # até a próxima vírgula como se fosse um nome de pessoa: a frase
        # saía "responda com o nome [PESSOA_03], e com o caminho do menu" —
        # incompreensível para quem lê do outro lado. Reescrito para não
        # começar a frase por "nome".
        ("- Quando a pergunta for «onde fica», diga qual é a tela, como ela "
         "está no menu acima, e o caminho dela."),
        ("- Tela, tabela ou arquivo que NÃO estejam aqui não existem neste "
         "sistema. Não invente: diga que não achou."),
    ]
    return _juntar_cortando_o_miolo(cabeca, miolo, rodape)


AVISO_DO_CORTE = "[o mapa continua, e foi cortado aqui pelo tamanho]"


def _juntar_cortando_o_miolo(cabeca: list[str], miolo: list[str],
                             rodape: list[str]) -> str:
    """Junta as três partes, e **o que encolhe é a lista, nunca a instrução**.

    ESTE É O CONSERTO DE 30/08/2026, E ELE TEM UMA HISTÓRIA CURTA.

    Antes, as três partes eram uma lista só e o corte caía no fim — que é
    onde mora o «Não invente: diga que não achou». Naquele dia entraram as
    telas dos modelos, do checklist e da folha do livro; o mapa passou de 9.000
    caracteres pela primeira vez; e o corte decepou a instrução no meio da
    palavra: «...não existe neste sistema. Não inve».

    O efeito não seria um erro na tela. Seria a ajuda **voltando a inventar
    nome de tela** — mandando o escrevente procurar o que não existe — e
    ninguém ligaria uma coisa à outra, porque nada quebrou.

    Por isso a ordem de sacrifício é esta, e é o contrário da ordem de leitura:
    a instrução é a menor parte e a única que muda o comportamento de quem lê;
    a lista é a maior e a que aguenta perder o rabo, **desde que diga que
    perdeu**. Cabeça e rodapé passam inteiros mesmo que estourem sozinhos: um
    limite que apaga a regra troca um resumo grande por uma resposta errada.
    """
    fixo = "\n".join(cabeca + rodape)
    sobra = LIMITE_DO_RESUMO - len(fixo) - len(AVISO_DO_CORTE) - 2
    texto_do_miolo = "\n".join(miolo)
    if len(texto_do_miolo) > sobra:
        # O CORTE FICA DITO. Mapa que some em silêncio faz o modelo responder
        # como se a parte cortada não existisse — e ele responde com convicção.
        # Corta em linha inteira: meia linha de menu é um caminho de menu pela
        # metade, que é justamente o que a instrução manda não inventar.
        cabem: list[str] = []
        gasto = 0
        for linha in miolo:
            if gasto + len(linha) + 1 > max(sobra, 0):
                break
            cabem.append(linha)
            gasto += len(linha) + 1
        texto_do_miolo = "\n".join(cabem + [AVISO_DO_CORTE])
    return "\n".join(cabeca + [texto_do_miolo] + rodape)
# ----------------------------------------------- a fotografia, para comparar
#
# **A AJUDA PRECISA SABER O QUE MUDOU, E NINGUEM ESCREVE ISSO PARA ELA.**
# O que se mede sozinho e o mapa — telas, arquivos e tabelas saem da arvore e
# do banco. O que nao se atualizava era o TEXTO: o modulo novo, a tela nova, a
# tabela nova. E nao se atualizava por um motivo banal: **ninguem escrevia**.
# Havia um roteiro por versao (`ROTEIRO_3.6.92.md`), e ele parou na 3.6.92 —
# como toda lista escrita a mao, ele morreu no dia em que deu trabalho.
#
# A FOTOGRAFIA TROCA A MEMORIA DE QUEM ESCREVE PELA COMPARACAO DE DUAS
# MEDICOES. Guarda-se o NOME das coisas, e nao as coisas: o mapa inteiro tem as
# colunas de 105 tabelas e passa de duzentos mil caracteres, enquanto a lista
# de nomes tem alguns milhares. E a diferenca entre guardar a fotografia e
# guardar a casa.
#
# QUEM GUARDA E `ajuda.py`, e nao este modulo — aqui so se mede e se compara.
# **Este arquivo nao escreve**, e ha varredor que confere isso lendo o texto,
# comentario incluido.

def impressao(mapa: dict) -> dict:
    """A fotografia comparavel do mapa: so NOMES. So calcula.

    Comparar o mapa inteiro daria a mesma resposta e custaria cem vezes mais —
    e a fotografia e gravada a cada versao, dentro do banco que vai no backup.

    **E ELA LEVA O NOME COM QUE A CASA CHAMA A TELA**, e nao so o
    identificador. `telas` continua sendo a lista dos endpoints — e a
    identidade, e o que se compara —, e `nomes` e o rotulo do menu de cada um.
    Sem ele, a resposta a «o que mudou» saia assim, medido na producao em
    15/09/2026: «1 tela(s) nova(s): ri_minuta_guardar». **O mapa ja sabia o
    nome da tela** (`telas[...]["nome"]`, do menu) e a fotografia o jogava
    fora — a peca pronta outra vez, e desta vez quem lia era o oficial.
    """
    mapa = mapa or {}
    telas = mapa.get("telas") or {}
    return {
        "versao": str(mapa.get("versao") or ""),
        "telas": sorted(str(e) for e in telas),
        "nomes": {str(e): str((telas[e] or {}).get("nome") or "") for e in telas},
        # `menu` FICA, e nao e resto: as fotografias gravadas ate a 3.6.130
        # trazem so ele, e sem ele a comparacao com aquelas perderia «esta no
        # menu?» — que e como se sabe se a tela tem nome humano. Nao se
        # compara: e leitura.
        "menu": sorted(str(m.get("endpoint") or "")
                       for m in (mapa.get("menu") or [])),
        "arquivos": sorted(str(a) for a in (mapa.get("arquivos") or {})),
        "tabelas": sorted(str(t) for t in (mapa.get("tabelas") or {})),
    }


# ------------------------------------------------- como se LE o que mudou
#
# O NOME DA TELA E DO MENU, e o identificador tambem vai: quem conserta precisa
# dos dois — o nome para achar na tela, o `endpoint` para achar no codigo.
#
# E HA TELA QUE NAO TEM NOME HUMANO NENHUM. Medido em 15/09/2026: das 503
# telas, 142 estao no menu, e as **quatro** nascidas depois da 3.6.128 —
# `ri_selar_ato`, `ri_descartar_minuta`, `ri_reabrir_matricula` e
# `ri_minuta_guardar` — sao botoes dentro de telas que ja existem. Para elas
# nao ha rotulo a mostrar, e o certo e DIZER ISSO e dizer de que modulo sao:
# «entao onde isso aparece?» e a pergunta que sobra, e ela tem resposta.

def _estava_no_menu(foto: dict) -> set[str]:
    """Os endpoints que aquela fotografia diz estarem no menu. So calcula.

    DUAS FORMAS, E A SEGUNDA E POR COMPATIBILIDADE. A fotografia desta versao
    responde por `nomes` (que sabe o rotulo); as gravadas ate a 3.6.130
    respondem por `menu`, que e so a lista dos endpoints — sabe QUEM esta no
    menu, e nao COMO se chama. As duas respondem o que a comparacao precisa, e
    por isso a resposta nao pode depender de qual das duas veio.
    """
    nomes = (foto or {}).get("nomes")
    if isinstance(nomes, dict):
        return {str(e) for e, rotulo in nomes.items() if rotulo}
    return {str(e) for e in ((foto or {}).get("menu") or [])}


def _rotulos_da_fotografia(*fotos: dict) -> dict[str, str]:
    """endpoint -> rotulo do menu, juntando o que as fotografias souberem.

    A ORDEM E A DE QUEM CHAMA, e o primeiro que souber responde: a fotografia
    nova manda, porque o nome de hoje e o que esta escrito na tela de hoje.
    """
    rotulos: dict[str, str] = {}
    for foto in fotos:
        nomes = (foto or {}).get("nomes")
        if not isinstance(nomes, dict):
            continue
        for endpoint, rotulo in nomes.items():
            if rotulo and str(endpoint) not in rotulos:
                rotulos[str(endpoint)] = str(rotulo)
    return rotulos


def _onde_fica(endpoint: str) -> str:
    """De que modulo e aquela tela, pela MESMA regra do menu. So calcula.

    `modulos.modulo_da_tela` e a regra da casa — ha teste que a roda contra
    todas as rotas comparando com a do menu. Escrever aqui uma segunda regra,
    parecida com ela, daria a segunda resposta no primeiro conserto.
    """
    chave = modulos.modulo_da_tela(endpoint)
    if not chave:
        return ""
    return str((modulos.POR_CHAVE.get(chave) or {}).get("nome") or "")


def _nome_para_ler(endpoint: str, mudanca: dict, *, sem_menu: bool) -> str:
    """Como aquela tela se escreve para quem le. So calcula.

    COM nome no menu: «o nome» (endpoint). SEM: o endpoint e o motivo — que ela
    nao tem item de menu, e de que modulo e. O que nao se faz e inventar um
    nome: nome inventado faz o oficial procurar no menu uma palavra que nao
    existe la.
    """
    rotulo = str((mudanca.get("rotulos") or {}).get(endpoint) or "")
    if rotulo:
        return f"«{rotulo}» ({endpoint})"
    if not sem_menu:
        # ESTAVA NO MENU E NAO SE SABE O NOME: e a fotografia antiga, que
        # gravou so a lista de endpoints. Dizer «sem item de menu» aqui seria
        # afirmar sobre o menu uma coisa que aquela fotografia nao mediu.
        return f"{endpoint} (no menu)"
    modulo = _onde_fica(endpoint)
    return (f"{endpoint} (sem item no menu"
            + (f" — do {modulo})" if modulo else ")"))


# Os campos que a comparacao percorre, e o nome que cada um recebe no texto.
# A ordem e a de leitura de quem conserta: a tela primeiro (e o que o oficial
# ve), depois o arquivo (onde se mexe) e por ultimo a tabela.
CAMPOS_DA_FOTOGRAFIA: tuple[tuple[str, str], ...] = (
    ("telas", "tela"),
    ("arquivos", "arquivo"),
    ("tabelas", "tabela"),
)


def diferenca(antes: dict | None, agora: dict) -> dict:
    """O que mudou entre duas fotografias. So calcula.

    DEVOLVE O QUE ENTROU E O QUE SAIU, e nao um numero: «mais doze telas» nao
    diz a quem le qual tela procurar. E **devolve vazio quando nao ha com o que
    comparar** — a primeira versao de uma instalacao nao tem anterior, e
    inventar «mudou tudo» ali seria pior que nao dizer nada.
    """
    if not antes:
        return {}
    saida: dict = {
        "da_versao": str(antes.get("versao") or ""),
        "para_versao": str(agora.get("versao") or ""),
        "mudou": False,
    }
    # O QUE AS DUAS FOTOGRAFIAS SABEM SOBRE O MENU, antes de percorrer os
    # campos: o rotulo de cada tela e quem nao tem rotulo nenhum. Fica aqui, e
    # nao dentro do laco, porque a pergunta e das duas fotografias juntas —
    # tela nova esta na de agora, tela que saiu esta na de antes.
    saida["rotulos"] = _rotulos_da_fotografia(agora, antes)
    no_menu = _estava_no_menu(antes) | _estava_no_menu(agora)
    for campo, _rotulo in CAMPOS_DA_FOTOGRAFIA:
        # `.get` e nao indexacao: uma fotografia gravada por uma versao
        # anterior pode nao ter um campo que so passou a existir depois, e o
        # erro aqui derrubaria a tela de quem so queria ver o estado.
        velho = set(antes.get(campo) or [])
        novo = set(agora.get(campo) or [])
        saida[f"{campo}_novos"] = sorted(novo - velho)
        saida[f"{campo}_que_sairam"] = sorted(velho - novo)
        if campo == "telas":
            # A TELA QUE NAO ESTA NO MENU NAO SE ACHA PELO NOME, e por isso o
            # texto diz que ela nao esta — so para ela. Ver `_nome_para_ler`.
            saida["telas_sem_menu"] = sorted(
                t for t in (set(saida["telas_novos"])
                            | set(saida["telas_que_sairam"]))
                if t not in no_menu)
        if saida[f"{campo}_novos"] or saida[f"{campo}_que_sairam"]:
            saida["mudou"] = True
    return saida


def resumo_da_diferenca(mudanca: dict | None, *, limite: int = 12) -> list[str]:
    """As linhas do «o que mudou», medidas — e nao lembradas. So calcula.

    A TELA SAI PELO NOME QUE A CASA USA, com o identificador ao lado: a versao
    anterior deste texto dizia «1 tela(s) nova(s): ri_minuta_guardar», e quem
    le nao tem como saber o que isso e. Ver `_nome_para_ler`.

    O CORTE FICA DITO, como no mapa: lista cortada em silencio faz quem le
    concluir que so aquilo mudou.

    E O SILENCIO E DIFERENTE DE ZERO. Sem versao anterior, a resposta certa e
    nao dizer nada — e nao uma lista vazia, que se le como «nada mudou».
    """
    if not mudanca:
        return []
    if not mudanca.get("mudou"):
        return [(
            f"Da versão {mudanca.get('da_versao') or 'anterior'} para "
            f"{mudanca.get('para_versao') or 'esta'}: nada mudou no que se "
            f"mede por nome — nem tela, nem arquivo, nem tabela.")]
    linhas = [(
        f"Da versão {mudanca.get('da_versao') or 'anterior'} para "
        f"{mudanca.get('para_versao') or 'esta'}, medido:")]
    sem_menu = set(mudanca.get("telas_sem_menu") or [])
    for campo, rotulo in CAMPOS_DA_FOTOGRAFIA:
        novos = mudanca.get(f"{campo}_novos") or []
        saiu = mudanca.get(f"{campo}_que_sairam") or []
        for itens, palavra in ((novos, "nova(s)"), (saiu, "que saíram")):
            if not itens:
                continue
            # SO A TELA TEM NOME DE MENU: arquivo e tabela sao o que o Python
            # e o banco chamam, e escreve-los de outro jeito seria inventar um
            # segundo vocabulario para eles.
            escritos = [
                _nome_para_ler(t, mudanca, sem_menu=t in sem_menu)
                if campo == "telas" else t
                for t in itens[:limite]]
            linhas.append(f"- {len(itens)} {rotulo}(s) {palavra}: "
                          + ", ".join(escritos)
                          + (" ..." if len(itens) > limite else ""))
    return linhas
