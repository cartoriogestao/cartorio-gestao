"""Os elementos dos modelos — herança por atribuição, com troca por ato.

    «preciso que haja um submodulo de modelos para cada atribuicao e nesse
     submodulo quero poder editar cada parte dos modelos, especialmente
     gerenciando cada elemento do modelo» — o oficial, 07/09/2026.

O QUE ESTE MÓDULO RESOLVE
    Até hoje um papel era **um texto só**, e o ajuste era tudo ou nada: para
    mudar o fecho de todas as certidões do Registro de Imóveis era preciso
    reescrever a certidão inteira, uma por uma. Agora o papel é **corpo +
    encerramento + rodapé**, e cada parte tem dono próprio.

OS TRÊS DEGRAUS
    ```
    1. o elemento do ATO         a certidão do RCPN tem encerramento próprio
    2. o elemento da ATRIBUIÇÃO  o resto do RCPN usa o comum
    3. o padrão do CÓDIGO        instalação nova já nasce funcionando
    ```

    O terceiro é a regra que `modelos_da_casa` já paga: **o código é o piso, a
    tabela é o ajuste** — e por isso «voltar ao padrão» é apagar a linha. Desde
    o LF06A (19/10/2026) o piso não mora mais no código: mora na pasta
    `modelos_padrao/`, carregada na base auxiliar, e a regra é a mesma.

O QUE FOI MEDIDO EM 07/09/2026, e o que cada medição decidiu

    **`mo_modelos` e `ri_modelos` estão com ZERO linhas na produção.** Os 14
    papéis saem todos do código. Por isso a tabela nova pode ser o lar único do
    corpo **sem migração nenhuma** — e as duas velhas ficam como legado, para
    uma instalação que já tivesse ajustado alguma coisa.

    **São 15 papéis, e não 10** — o catálogo cresceu desde 29/08. Contados.

    **O formato do claro é uniforme dentro de cada atribuição.** Registro de
    Imóveis, Notas e Caixa são Jinja (`{{ a.numero }}`); Registro Civil e
    Protesto são chaves (`{numero}`). Isso é o que **permite** um elemento
    compartilhado pela atribuição: um encerramento em Jinja herdado por um
    termo do civil seria texto que passa numa conferência e é recusado pela
    outra. `formato_da_atribuicao` **mede** essa uniformidade em vez de a
    supor, e recusa se um dia ela deixar de valer.

O CABEÇALHO NÃO ESTÁ AQUI, e a decisão é do oficial, no mesmo dia:

    «cabecalho dos atos vamos deixar num ajuste separado para manter a forma e
     diminuir o risco de ir errado».

    Ele continua no `RI_CABECALHO` do catálogo e em `rc_cabecalho.py`, montado
    em código. Ver `CABECALHO_FICOU_DE_FORA` no esquema.

**E O ENCERRAMENTO E O RODAPÉ NASCEM VAZIOS**, de propósito: os 15 papéis já
trazem o fecho dentro do próprio texto, e partir isso automaticamente seria
adivinhar onde o corpo acaba num documento que a serventia assina. Vazio não
acrescenta nada — **o papel sai, no dia da subida, exatamente como saía na
véspera.**
"""
from __future__ import annotations

import re
import sqlite3

from bd_nativo import banco
import string
from typing import Any

import modelos_da_casa as CASA
from modelos_elementos_schema import (
    ATRIBUICOES,
    CHAVE_DO_ROTULO,
    CORPO,
    NOME_DA_ATRIBUICAO,
    NOME_DA_PARTE,
    PARTES,
    TODA_A_ATRIBUICAO,
)


class ElementoError(ValueError):
    """Erro de regra, com mensagem pronta para o balcão."""


# ============================================================ o que existe

def _texto(valor: Any) -> str:
    return str(valor if valor is not None else "").strip()


def atribuicao_valida(atribuicao: Any) -> str:
    chave = _texto(atribuicao).upper()
    if chave not in ATRIBUICOES:
        raise ElementoError(
            f"«{atribuicao}» não é uma atribuição desta casa. As que existem: "
            + ", ".join(NOME_DA_ATRIBUICAO[a] for a in ATRIBUICOES) + ".")
    return chave


def parte_valida(parte: Any) -> str:
    p = _texto(parte).upper()
    if p not in PARTES:
        raise ElementoError(
            f"«{parte}» não é uma parte do modelo. As que existem: "
            + ", ".join(NOME_DA_PARTE[x] for x in PARTES) + ".")
    return p


def atos_da_atribuicao(atribuicao: str) -> tuple[dict, ...]:
    """Os papéis daquela atribuição, lidos do catálogo. Só calcula.

    **LIDOS DO CATÁLOGO, e não copiados para cá.** Uma segunda lista de papéis
    divergiria da primeira no dia em que alguém acrescentasse um — e a tela
    ofereceria para editar um papel que o programa não usa, ou deixaria de
    fora um que ele usa.
    """
    chave = atribuicao_valida(atribuicao)
    return tuple(c for c in CASA.CATALOGO
                 if CHAVE_DO_ROTULO.get(c["atribuicao"]) == chave)


def atribuicao_do_ato(ato: str) -> str:
    """De qual atribuição é aquele papel. Só calcula."""
    c = CASA.POR_CHAVE.get(_texto(ato).upper())
    if not c:
        raise ElementoError(f"«{ato}» não é um papel que esta casa emita.")
    chave = CHAVE_DO_ROTULO.get(c["atribuicao"])
    if not chave:
        raise ElementoError(
            f"O papel «{ato}» está no catálogo sob «{c['atribuicao']}», que "
            "não é uma das seis atribuições desta tela. Isso é defeito do "
            "de-para, e não do papel.")
    return chave


def formato_da_atribuicao(atribuicao: str) -> str:
    """Em que formato os papéis daquela atribuição escrevem os claros.

    **MEDE, E NÃO SUPÕE.** Um elemento compartilhado pela atribuição inteira só
    faz sentido se os papéis dela leem o mesmo marcador: um encerramento em
    Jinja herdado por um termo do Registro Civil — que é `str.format` — seria
    texto aprovado numa conferência e recusado pela outra, e o escrevente
    descobriria com o cliente na frente.

    Medido em 07/09/2026: as cinco atribuições com papel são uniformes. A
    sexta (RCPJ e RTD) não tem papel nenhum, e aí vale o padrão da casa.
    """
    chave = atribuicao_valida(atribuicao)
    formatos = {CASA.formato_de(c["chave"]) for c in atos_da_atribuicao(chave)
                if c.get("elementos_comuns", True)}
    if not formatos:
        # Sem papel no catálogo — RCPJ e RTD é o caso, medido. O Jinja é o
        # formato da casa inteira; declarar isso é melhor que estourar.
        return CASA.JINJA
    if len(formatos) > 1:
        raise ElementoError(
            f"Os papéis de {NOME_DA_ATRIBUICAO[chave]} não usam todos o mesmo "
            "marcador de claro, e por isso não podem partilhar um elemento: "
            + ", ".join(sorted(formatos)) + ". Ajuste um deles antes.")
    return formatos.pop()


def formato_do_ato(ato: str) -> str:
    """O marcador daquele papel — Jinja ou chaves. Só calcula."""
    return CASA.formato_de(_texto(ato).upper())


# ====================================================== ler o que vale hoje

# De onde o texto veio, e a tela mostra isso: «herdado» e «próprio deste ato»
# parecem a mesma coisa quando o texto é o mesmo, e são diferentes no dia em
# que o da atribuição mudar — o próprio **não** acompanha.
DO_ATO = "ato"
DA_ATRIBUICAO = "atribuicao"
DO_PADRAO = "padrao"
DO_LEGADO = "legado"


def _linha(con: sqlite3.Connection, atribuicao: str, ato: str,
           parte: str) -> str | None:
    r = banco(con).um(
        """SELECT corpo FROM mo_elementos
            WHERE atribuicao = %s AND ato = %s AND parte = %s
              AND COALESCE(ativo, 1) = 1 AND COALESCE(corpo, '') <> ''""",
        (atribuicao, ato, parte))
    return str(r["corpo"]) if r else None


def elemento(con: sqlite3.Connection, *, atribuicao: str, ato: str,
             parte: str) -> dict:
    """O que vale para aquela parte, e **de onde veio**. Só lê.

    Devolve `{"texto", "de_onde", "proprio"}`. `proprio` diz se há linha
    daquele ato — é o que a tela usa para oferecer «voltar ao herdado».
    """
    atrib = atribuicao_valida(atribuicao)
    p = parte_valida(parte)
    alvo = _texto(ato).upper()

    proprio = _linha(con, atrib, alvo, p) if alvo else None
    if proprio is not None:
        return {"texto": proprio, "de_onde": DO_ATO, "proprio": True}

    # O DEGRAU DO LEGADO, e ele vem **antes** da atribuição de propósito: quem
    # já tinha ajustado aquele papel ajustou o PAPEL, que é mais específico
    # que a atribuição. Perder esse ajuste ao subir de versão seria apagar
    # trabalho de alguém sem avisar.
    #
    #   **A COMPARAÇÃO É COM O PADRÃO, e não `esta_ajustado`**: aquela função
    #   olha só `mo_modelos`, e o legado do Registro de Imóveis mora numa
    #   segunda tabela (`ri_modelos`). Perguntar «o que sai é diferente do que
    #   o programa traz?» alcança as duas.
    if alvo and p == CORPO:
        gravado = CASA.corpo_gravado_ou_padrao(con, alvo)
        if gravado != CASA.padrao_de(alvo):
            return {"texto": gravado, "de_onde": DO_LEGADO, "proprio": False}

    aceita_comum = (not alvo or
                    CASA.POR_CHAVE.get(alvo, {}).get("elementos_comuns", True))
    comum = (_linha(con, atrib, TODA_A_ATRIBUICAO, p)
             if aceita_comum else None)
    if comum is not None:
        return {"texto": comum, "de_onde": DA_ATRIBUICAO, "proprio": False}

    # O PISO. Só o corpo tem padrão (na base, desde o LF06A); o encerramento e o
    # rodapé nascem vazios, e vazio **não acrescenta nada**.
    if p == CORPO and alvo:
        return {"texto": CASA.padrao_de(alvo), "de_onde": DO_PADRAO,
                "proprio": False}
    return {"texto": "", "de_onde": DO_PADRAO, "proprio": False}


def corpo_do_ato(con: sqlite3.Connection, ato: str) -> str:
    """Só o CORPO daquele papel, sem o fecho. É o que a tela de edição mostra."""
    return elemento(con, atribuicao=atribuicao_do_ato(ato), ato=ato,
                    parte=CORPO)["texto"]


def legenda_do_ato(ato: str, texto: str) -> list[dict[str, str]]:
    """Os claros do modelo, apresentados como ``@campo`` à moda do E-Ofício.

    O código inserido continua sendo o que o emissor realmente entende. Assim
    a legenda é uniforme para a pessoa sem converter silenciosamente modelos
    antigos nem criar uma terceira linguagem de emissão.
    """
    vistos: set[str] = set()
    itens: list[dict[str, str]] = []

    def juntar(codigo: str, nome: str) -> None:
        limpo = re.sub(r"[^A-Za-z0-9_]+", "_", nome).strip("_").lower()
        if not limpo or codigo in vistos:
            return
        vistos.add(codigo)
        itens.append({"rotulo": "@" + limpo, "codigo": codigo,
                      "nome": nome.replace("_", " ").replace(".", " › ")})

    if formato_do_ato(ato) == CASA.CHAVES:
        try:
            for _, campo, _, _ in string.Formatter().parse(texto or ""):
                if campo:
                    juntar("{" + campo + "}", campo)
        except ValueError:
            pass
    else:
        # Expressões simples são os claros clicáveis. Laços e condições
        # continuam visíveis no código, mas não viram um botão enganoso.
        # `{{([^{}]+)}}`, e não `{{\s*([^{}]+?)\s*}}` (CodeQL, 28/10/2026):
        # a forma antiga era cúbica num `{{` sem fecho seguido de brancos.
        # Casa os mesmos trechos, e o `.strip()` de baixo tira os brancos das
        # pontas que o grupo agora traz.
        for expr in re.findall(r"{{([^{}]+)}}", texto or ""):
            base = expr.split("|", 1)[0].strip()
            if re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*", base):
                juntar("{{ " + base + " }}", base)
    return itens


# **AS PARTES SE JUNTAM COM LINHA EM BRANCO ENTRE ELAS**, e não coladas: no
# Jinja e no `str.format` o texto sai como está escrito, e duas frases sem
# separação virariam uma só no papel.
SEPARADOR = "\n\n"


def montar_documento(con: sqlite3.Connection, ato: str) -> str:
    """O papel inteiro — corpo, encerramento e rodapé. Só calcula.

    **NO DIA DA SUBIDA ISTO DEVOLVE EXATAMENTE O QUE `corpo_de` DEVOLVIA**,
    porque o encerramento e o rodapé nascem vazios: sem eles, o que sai é o
    corpo **literal**, sem uma vírgula de diferença.

    > **E A PRIMEIRA VERSÃO DISTO QUEBROU ESSA PROMESSA POR UM CARACTERE.**
    > Ela juntava as três partes com `strip()` em cada uma, e **nove dos
    > catorze papéis** perderam a quebra de linha do fim — 743 caracteres
    > viraram 742, e assim nos nove de Jinja. Um deles é o molde da ficha da
    > matrícula, que é XML de ODT.
    >
    > Quem pegou foi o ensaio que compara papel por papel contra o padrão do
    > código, e **não** a releitura: «um caractere a menos» não se vê lendo.
    > **Promessa de que nada muda se mede, e não se afirma.**

    Quando o oficial escreve um encerramento, aí sim o corpo perde o espaço em
    branco do fim — senão sairiam três linhas vazias entre uma parte e outra. E
    isso já é uma mudança que ele pediu.
    """
    alvo = _texto(ato).upper()
    atrib = atribuicao_do_ato(alvo)
    partes = [elemento(con, atribuicao=atrib, ato=alvo, parte=p)["texto"]
              for p in PARTES]

    corpo, depois = partes[0], [x.strip() for x in partes[1:] if x.strip()]
    if not depois:
        return corpo
    return corpo.rstrip() + SEPARADOR + SEPARADOR.join(depois)


def partes_do_documento(con: sqlite3.Connection, ato: str) -> list[str]:
    """As partes efetivas, na ordem, para editor e prévia sem gravar."""
    alvo = _texto(ato).upper()
    atrib = atribuicao_do_ato(alvo)
    return [elemento(con, atribuicao=atrib, ato=alvo, parte=p)["texto"]
            for p in PARTES]


def quadro(con: sqlite3.Connection, atribuicao: str) -> dict:
    """Tudo o que a tela do submódulo mostra. Só lê."""
    atrib = atribuicao_valida(atribuicao)
    comuns = []
    for p in PARTES:
        if p == CORPO:
            # **NÃO HÁ CORPO COMPARTILHADO PELA ATRIBUIÇÃO**, e a ausência é
            # deliberada: o corpo de uma certidão não é o corpo de uma nota
            # devolutiva. Oferecê-lo daria um campo que, preenchido, apagaria
            # o texto de todos os papéis da atribuição de uma vez.
            continue
        e = elemento(con, atribuicao=atrib, ato="", parte=p)
        comuns.append({"parte": p, "nome": NOME_DA_PARTE[p],
                       "explica": _explica(p), **e})

    atos = []
    for c in atos_da_atribuicao(atrib):
        partes = []
        for p in PARTES:
            e = elemento(con, atribuicao=atrib, ato=c["chave"], parte=p)
            partes.append({"parte": p, "nome": NOME_DA_PARTE[p], **e})
        atos.append({**c, "partes": partes,
                     "legenda": legenda_do_ato(c["chave"],
                                                partes[0]["texto"]),
                     "formato": CASA.formato_de(c["chave"])})

    return {"atribuicao": atrib, "nome": NOME_DA_ATRIBUICAO[atrib],
            "formato": formato_da_atribuicao(atrib),
            "comuns": comuns, "atos": atos,
            "quantos_ajustes": _quantos(con, atrib)}


def _explica(parte: str) -> str:
    from modelos_elementos_schema import EXPLICA_A_PARTE
    return EXPLICA_A_PARTE[parte]


def _quantos(con: sqlite3.Connection, atribuicao: str) -> int:
    r = banco(con).um(
        """SELECT COUNT(*) AS n FROM mo_elementos
            WHERE atribuicao = %s AND COALESCE(corpo, '') <> ''""",
        (atribuicao,))
    return int(r["n"])


# ============================================================ conferir e gravar

# OS PAPÉIS QUE SE CONFEREM PELA PRÓPRIA MONTAGEM — LF06F, 19/10/2026.
#
#   O boneco (`_ENSAIO`) só tem `hoje`, `agora` e `sv`. Um papel em Jinja que
#   use `t`, `e` ou `c` estoura nele com «'t' is undefined» em TODO ajuste — a
#   casa não grava nem o próprio padrão, e o papel fica editável só no nome.
#   O módulo do papel registra aqui a conferência dele (a mesma montagem da
#   emissão, com um caso de exemplo), na subida das rotas; quem não registrou
#   continua no boneco, como sempre foi. A chave é a do papel no catálogo, e a
#   função devolve o erro ou `""`.
CONFERIDORES: dict[str, Any] = {}


def conferir(atribuicao: str, ato: str, parte: str, texto: str) -> str:
    """O que há de errado naquele elemento, ou `""`. Só calcula.

    **A CONFERÊNCIA É NO FORMATO DO ATO**, e não num genérico: passar um
    `{numero}` pelo Jinja aprova texto que o `str.format` não monta, e
    vice-versa. É a armadilha que `modelos_da_casa` documenta desde 29/08.
    """
    atrib = atribuicao_valida(atribuicao)
    p = parte_valida(parte)
    corpo = texto or ""

    if p == CORPO and not corpo.strip():
        # Corpo vazio não se grava — ele volta ao herdado. Guardar vazio faria
        # a casa imprimir folha em branco, e folha em branco assinada é pior
        # que modelo feio.
        return ""
    if not corpo.strip():
        return ""

    proprio = CONFERIDORES.get(_texto(ato).upper()) if p == CORPO else None
    if proprio is not None:
        return proprio(corpo) or ""

    formato = formato_do_ato(ato) if _texto(ato) else formato_da_atribuicao(atrib)
    if formato == CASA.CHAVES:
        # o encerramento e o rodapé PRÓPRIOS do papel entram no mesmo texto
        # que o montador preenche (`montar_documento`): conferem-se igual
        return (_conferir_chaves(corpo)
                or (_conferir_claros_do_padrao(_texto(ato).upper(), corpo)
                    if _texto(ato) else ""))
    erro = CASA.conferir(corpo, contexto_de_ensaio(_texto(ato).upper()))
    return erro or ""


# O CONTEXTO DE ENSAIO — o mesmo boneco de `modelos_web`, e pelo mesmo motivo:
# conferir com dado real exigiria escolher um ato, e a escolha mudaria o
# resultado, de modo que um elemento aprovado numa certidão reprovaria na
# seguinte. O que ele pega é a FORMA.
_ENSAIO = {
    "hoje": "7 de setembro de 2026",
    "agora": "2026-09-07T09:00",
    "sv": {"nome": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO",
           "cns": "000000", "cidade": "Cidade Exemplo", "uf": "UF",
           "endereco": "(endereço de ensaio)", "telefone": "(99) 0000-0000",
           "registrador": "(nome de ensaio)", "titulo": "Tabelião e Oficial"},
}


class _SoAForma:
    """O valor de uma variável que só o módulo do papel conhece: serve para montar o texto.

    `{{ serventia.cidade|upper }}` precisa passar, e `{% for a in m.atos %}` também: a conferência
    daqui olha a FORMA. Qual campo existe é o conferidor do módulo quem diz, ou a hora de emitir.
    """

    def __getattr__(self, _nome):
        return self

    def __getitem__(self, _chave):
        return self

    def __call__(self, *_a, **_k):
        return self

    def __iter__(self):
        return iter(())

    def __len__(self):
        return 0

    def __bool__(self):
        return False

    def __str__(self):
        return ""

    def __int__(self):
        return 0

    def __float__(self):
        return 0.0

    def __round__(self, _casas=None):
        return 0

    def __lt__(self, _outro):
        return False

    __le__ = __gt__ = __ge__ = __lt__

    def _conta(self, _outro):
        return self

    __add__ = __radd__ = __sub__ = __rsub__ = __mul__ = __rmul__ = _conta
    __truediv__ = __rtruediv__ = __floordiv__ = __mod__ = __neg__ = _conta


def contexto_de_ensaio(ato: str) -> dict:
    """O boneco, mais as variáveis que o PADRÃO daquele papel usa. Só calcula.

    21 PAPÉIS NÃO SE GRAVAVAM, E NENHUM ERA QUEBRADO. O boneco só conhece `hoje`, `agora` e `sv`, e
    o cabeçalho do RI usa `serventia`, a ficha usa `m`, o recibo usa `r`: até o texto de fábrica era
    recusado, com «'serventia' is undefined» na tela. O nome que o padrão usa é legítimo, e o que
    ele não usa continua recusado: `{{ serventa.cidade }}` é erro de digitação, e o papel não sairia.
    """
    contexto = dict(_ENSAIO)
    if not ato or ato not in CASA.POR_CHAVE:
        return contexto
    from jinja2 import meta
    from jinja2.sandbox import SandboxedEnvironment
    try:
        nomes = meta.find_undeclared_variables(SandboxedEnvironment().parse(CASA.padrao_de(ato) or ""))
    except Exception:                                  # noqa: BLE001 — padrão ilegível: fica o boneco
        return contexto
    for nome in nomes:
        contexto.setdefault(nome, _SoAForma())
    return contexto


def _conferir_chaves(corpo: str) -> str:
    """Chave aberta sem fechar, e Jinja onde não cabe."""
    for marca in ("{{", "{%"):
        if marca in corpo:
            return (f"Este texto usa «{marca}», que é a marcação das outras "
                    "atribuições. Aqui o claro se escreve entre chaves "
                    "simples, assim: {nome}.")
    if corpo.count("{") != corpo.count("}"):
        return "Há chave aberta sem fechar. Cada claro se escreve {assim}."
    return ""


def _conferir_claros_do_padrao(ato: str, corpo: str) -> str:
    """Claro que o padrão não usa, num papel que só aceita os dele. LF06D.

    **O MONTADOR DAS NOTAS PREENCHE OS CLAROS DO PADRÃO, E SÓ ELES** — a
    fórmula do reconhecimento recebe `{quem}`, a abertura do teor recebe a data
    e a cidade. Um `{cartorio}` escrito na tela passaria pela conferência das
    chaves e estouraria no balcão. O papel declara isso no catálogo
    (`so_claros_do_padrao`); os termos do Registro Civil, que aceitam claros
    além dos do padrão, não declaram, e seguem com a conferência deles.

    **A RÉGUA É A DO `modelos_da_casa.conferir_claros`** — a mesma que o
    montador usa ao preencher (`Textos.preencher` → `preencher`). Duas réguas
    diriam coisas diferentes do mesmo texto na tela e no balcão; o LF06C já
    tinha juntado a do Registro Civil a ela.
    """
    c = CASA.POR_CHAVE.get(ato) or {}
    if not c.get("so_claros_do_padrao"):
        return ""
    return CASA.conferir_claros(corpo, c.get("campos") or ())


def salvar(con: sqlite3.Connection, *, atribuicao: str, ato: str, parte: str,
           corpo: str, quem: str | None, agora: str) -> None:
    """Grava o elemento. Confere ANTES.

    **CORPO VAZIO APAGA A LINHA**, e não grava vazio: apagar é o «voltar ao
    herdado», e é por isso que ele não precisa de botão próprio nem de
    recadastrar um texto que ninguém tem mais guardado.
    """
    atrib = atribuicao_valida(atribuicao)
    p = parte_valida(parte)
    alvo = _texto(ato).upper()
    if alvo:
        # Grava ajuste de ato de OUTRA atribuição seria pôr o texto onde
        # ninguém o procura — e a herança nunca o alcançaria.
        de_quem = atribuicao_do_ato(alvo)
        if de_quem != atrib:
            raise ElementoError(
                f"O papel «{alvo}» é de {NOME_DA_ATRIBUICAO[de_quem]}, e não "
                f"de {NOME_DA_ATRIBUICAO[atrib]}.")

    ruim = conferir(atrib, alvo, p, corpo)
    if ruim:
        raise ElementoError(ruim)

    limpo = (corpo or "").strip()
    if not limpo:
        restaurar(con, atribuicao=atrib, ato=alvo, parte=p)
        return

    # SOBRE QUAL PADRÃO ESTE CORPO FOI ESCRITO (LF06A): é o que deixa a tela
    # dizer «o padrão mudou depois do seu ajuste» numa versão nova. Só o corpo
    # de um ato tem padrão; o resto fica nulo.
    base = CASA.impressao_sob_o_ajuste(alvo) if (alvo and p == CORPO) else None
    banco(con).escrever(
        """INSERT INTO mo_elementos
               (atribuicao, ato, parte, corpo, ativo, atualizado_em,
                atualizado_por, base_impressao)
           VALUES (%s,%s,%s,%s,1,%s,%s,%s)
           ON CONFLICT(atribuicao, ato, parte) DO UPDATE SET
               corpo = excluded.corpo, ativo = 1,
               atualizado_em = excluded.atualizado_em,
               atualizado_por = excluded.atualizado_por,
               base_impressao = excluded.base_impressao""",
        (atrib, alvo, p, limpo, agora, quem, base))


def esta_ajustado(con: sqlite3.Connection, ato: str) -> bool:
    """Se a casa mexeu em alguma parte daquele papel. Só lê.

    A TELA PRECISA DIZER ISSO, porque «igual ao padrão» e «ajustado pela casa»
    parecem a mesma coisa quando o texto é o mesmo — e são diferentes no dia em
    que o padrão mudar numa versão nova: o ajustado **não** acompanha.
    """
    alvo = _texto(ato).upper()
    atrib = atribuicao_do_ato(alvo)
    r = banco(con).um(
        """SELECT 1 AS um FROM mo_elementos
            WHERE atribuicao = %s AND ato = %s AND COALESCE(corpo, '') <> ''
            ORDER BY id LIMIT 1""", (atrib, alvo))
    if r:
        return True
    # O legado das duas tabelas antigas conta como ajuste — é ajuste da casa.
    return CASA.corpo_gravado_ou_padrao(con, alvo) != CASA.padrao_de(alvo)


def restaurar(con: sqlite3.Connection, *, atribuicao: str, ato: str,
              parte: str) -> bool:
    """Apaga o ajuste e volta ao degrau de cima. Devolve se havia ajuste."""
    atrib = atribuicao_valida(atribuicao)
    p = parte_valida(parte)
    apagadas = banco(con).escrever(
        "DELETE FROM mo_elementos WHERE atribuicao=%s AND ato=%s AND parte=%s "
        "RETURNING id", (atrib, _texto(ato).upper(), p))
    return len(apagadas) > 0
