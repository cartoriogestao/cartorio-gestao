"""
Livro, folha e termo — a numeracao dos atos do Tabelionato de Notas.

O QUE ESTE MODULO RESOLVE
    Ate aqui o balcao digitava a folha a mao, o `folha_atual` do livro nascia
    em 1 e morria em 1, e o numero de ordem era um MAX()+1 filtrado pelo ano de
    hoje. Tres consequencias praticas, todas de correicao:

      1. nada impedia dois atos na mesma folha do mesmo livro;
      2. nada impedia lavrar na folha 350 de um livro de 200;
      3. guardar o teor com o campo Folha em branco APAGAVA a folha do ato.

    Aqui a folha deixa de ser digitada e passa a ser ATRIBUIDA, uma so vez, no
    momento em que o ato e lancado no livro.

A REGRA DESTA SERVENTIA
    Definida pelo delegatario em 17/08/2026:

      - cada ato comeca em FOLHA NOVA. Nenhum ato divide folha com outro;
      - conta-se FRENTE e VERSO: a folha 12 tem duas paginas, "12" e "12v";
      - o ato ocupa folhas inteiras, logo o numero de paginas reservadas e
        SEMPRE PAR. Sobrando o verso da ultima folha, ele nao serve ao ato
        seguinte — e inutilizado;
      - o TERMO e continuo por serie de livro e NAO REINICIA a cada livro novo;
      - livro cheio ENCERRA e o seguinte ABRE sozinho, sem parar o balcao.

    O verso que sobra nao fica em branco: o art. 795, § 2º, do Codigo de Normas
    manda que a escrituracao seja seguida, SEM CLAROS OU ESPACOS EM BRANCO.
    Espaco em branco em livro de notas e o lugar por onde se acrescenta o que
    ninguem declarou. Por isso `lancar_ato` devolve `inutilizar`, dizendo qual
    pagina o escrevente tem de inutilizar antes de encadernar.

POR QUE O LANCAMENTO E NO FIM, E NAO NA ABERTURA DO ATO
    Folha reservada para ato que nao se lavrou vira BURACO no livro, e buraco
    em livro de notas nao se explica em correicao. O ato nasce EM_LAVRATURA,
    sem livro, sem folha e sem termo; recebe os tres quando o teor esta pronto
    e se sabe quantas paginas ele tem. A partir dali e LAVRADO, e a folha nao
    volta atras — nem se o ato for depois cancelado, porque o papel foi gasto.

FUNDAMENTO
    Lei 8.935/1994, art. 30, I (manter em ordem os livros) e art. 46 (guarda e
        responsabilidade sobre os livros).
    Codigo de Normas do Foro Extrajudicial do Maranhao — Provimento TJMA n. 28,
        de 23/04/2026, Capitulo IV, Secao III "Dos Livros e da sua
        Escrituracao", arts. 788 a 797; em especial o art. 795, caput e §§ 2º
        e 4º (escrituracao seguida, sem claros; numeros por extenso com
        repeticao em algarismos).
    Provimento CNJ 149/2023 — Codigo Nacional de Normas do Foro Extrajudicial.

    A remissao a Secao III e ao intervalo 788-797 esta conferida contra o
    sumario oficial do Provimento 28/2026. O teor do art. 795, § 2º esta
    conferido e ja era citado em `notas_modelos.py`. Os demais artigos DENTRO
    do intervalo nao foram lidos um a um: por isso este modulo cita a SECAO, e
    nao um numero de artigo que ninguem verificou.

COMO SE USA
    Sempre de dentro de uma transacao do chamador, no molde da casa
    (`database.next_protocol`, `caixa_depositos.criar`):

        with db.transaction() as con:
            feito = NL.lancar_ato(con, ato_id, paginas=4, sv=sv,
                                  agora=db.now(), usuario=usuario_nome())
        audit("NT_ATO_LANCADO", "NT_ATO", ato_id, feito)   # FORA do with

    `audit()` abre transacao propria: chamado de dentro do `with`, trava a si
    mesmo por 10 segundos no busy_timeout. Isso ja e o padrao do modulo de
    notas e continua valendo aqui.
"""
from __future__ import annotations

import math
import re
import sqlite3
from typing import Any

# --------------------------------------------------------------- constantes

# Folhas que um livro comporta. E o que a serventia usa; a tela deixa mudar.
CAPACIDADE_PADRAO = 200

# Frente e verso. Nao e configuracao: e o que e uma folha.
PAGINAS_POR_FOLHA = 2

# Estimativa de quanto texto cabe numa pagina do livro. Serve para PRE-PREENCHER
# o campo de paginas, nunca para decidir sozinho — quem sabe quantas paginas o
# ato tem e quem imprimiu. Numero conservador: 32 linhas de 75 caracteres.
CARACTERES_POR_PAGINA = 2400

# Em que livro cada tipo de ato se lavra.
#
# Revogacao e renuncia de mandato acompanham a procuracao — a Secao X do
# Codigo de Normas trata as quatro na mesma secao ("Da Procuracao, do
# Substabelecimento, da Revogacao e da Renuncia de Mandato", arts. 831 a 833),
# e o ato de revogacao so faz sentido ao lado do que ele revoga.
#
# Substabelecimento tem livro proprio em TIPOS_LIVRO e fica com ele. Serventia
# que prefira lavrar substabelecimento no livro de procuracoes muda AQUI, num
# lugar so, e a numeracao inteira acompanha.
LIVRO_DO_ATO = {
    "ESCRITURA": "ESCRITURA",
    "PROCURACAO": "PROCURACAO",
    "PROCURACAO_PREVIDENCIARIA": "PROCURACAO",
    "REVOGACAO": "PROCURACAO",
    "RENUNCIA": "PROCURACAO",
    "SUBSTABELECIMENTO": "SUBSTABELECIMENTO",
    "TESTAMENTO": "TESTAMENTO",
    "TESTAMENTO_CERRADO": "TESTAMENTO_CERRADO",
    "ATA": "ATA",
    "ATA_USUCAPIAO": "ATA",
}

# Nome da serie no termo de abertura, no plural e por extenso.
NOME_DA_SERIE = {
    "ESCRITURA": "Escrituras Publicas",
    "PROCURACAO": "Procuracoes",
    "SUBSTABELECIMENTO": "Substabelecimentos",
    "TESTAMENTO": "Testamentos Publicos",
    "TESTAMENTO_CERRADO": "Registro de Testamentos Cerrados",
    "ATA": "Atas Notariais",
}


class LivroError(ValueError):
    """Regra de escrituracao violada.

    E `ValueError` de proposito: a rota trata com `flash(..., 'danger')`, no
    mesmo padrao de `caixa_depositos.criar`. Erro de regra nao e HTTP 500.
    """


# ------------------------------------------------------------- por extenso
#
# Isto MUDOU DE LUGAR na versao 3.4.2: o texto por extenso passou a viver no
# nucleo, em `livro_nucleo`, porque o termo de abertura do Livro A do RCPN
# precisa dele igual ao termo do Livro de Escrituras. Fica reexportado aqui
# para nao quebrar `notas_livro.por_extenso`, que a tela de conferencia e os
# testes chamam por este nome.

from livro_nucleo import (  # noqa: E402,F401  (reexportado de proposito)
    LIMITE_POR_EXTENSO,
    com_algarismos,
    por_extenso,
)

# ------------------------------------------------------------- folha e pagina



def rotulo_folha_da_pagina(folha_inicial: Any, pagina_pdf: int) -> str:
    """A face do livro que corresponde à página N do PDF/ODT.

    Página 1 = frente da folha inicial; página 2 = verso (`Nv`); página 3 =
    frente da seguinte. É a conta do art. 795 do Código de Normas (frente e
    verso), e não o número sequencial da página do arquivo.
    """
    inicio = inteiro(folha_inicial)
    if inicio is None or int(pagina_pdf) < 1:
        return ""
    pagina = int(pagina_pdf)
    numero = inicio + (pagina - 1) // 2
    verso = (pagina % 2) == 0
    return rotulo_folha(numero, verso=verso)

def rotulo_folha(numero: Any, verso: bool = False) -> str:
    """`12` para a frente, `12v` para o verso. Vazio se o numero nao presta."""
    n = inteiro(numero)
    if n is None:
        return ""
    return f"{n}v" if verso else str(n)


def inteiro(valor: Any) -> int | None:
    """O numero que houver dentro do valor, ou None. Nao levanta.

    Aceita `12`, `"12"`, `"12v"`, `"fl. 12"`. Devolve None para `""`, `None`,
    `"XII"` — e devolver None e melhor do que devolver um numero inventado.

    LE FOLHA, NAO LE QUANTIDADE. Como acha o primeiro grupo de digitos, `"-4"`
    devolve 4: o sinal some. Para campo de quantidade use `quantidade()`, que
    recusa em vez de adivinhar.
    """
    if valor is None:
        return None
    if isinstance(valor, bool):
        return None
    if isinstance(valor, int):
        return valor
    achado = re.search(r"\d+", str(valor))
    return int(achado.group(0)) if achado else None


def quantidade(valor: Any, rotulo: str) -> int | None:
    """Um inteiro POSITIVO vindo de formulario, ou None se o campo veio vazio.

    Recusa 0, negativo e lixo, em vez de cair num padrao silencioso — foi
    assim que `paginas=0` virava a estimativa e `paginas=-4` virava 4, os dois
    sem uma palavra na tela. Numero de pagina errado desloca todo o resto do
    livro; e o tipo de erro que so aparece na correicao.
    """
    if valor is None:
        return None
    texto = str(valor).strip()
    if not texto:
        return None
    try:
        n = int(texto)
    except ValueError:
        raise LivroError(f"{rotulo}: informe um número inteiro.") from None
    if n < 1:
        raise LivroError(f"{rotulo}: precisa ser pelo menos 1.")
    if n > LIMITE_POR_EXTENSO:
        raise LivroError(f"{rotulo}: {n} não é um número plausível.")
    return n


def folhas_de(paginas: Any) -> int:
    """Quantas folhas o ato ocupa. Sempre pelo menos uma."""
    p = inteiro(paginas) or 0
    return max(1, math.ceil(p / PAGINAS_POR_FOLHA))


def paginas_reservadas(folhas: int) -> int:
    """As paginas que o livro perde para o ato — sempre PAR.

    O pedido da serventia: ato em numero par de paginas, para que o proximo
    nunca comece no verso do anterior. Como o ato comeca em folha nova e ocupa
    folhas inteiras, isso sai por construcao.
    """
    return int(folhas) * PAGINAS_POR_FOLHA


def estimar_paginas(teor: Any,
                    caracteres_por_pagina: int = CARACTERES_POR_PAGINA) -> int:
    """Um palpite de quantas paginas o teor ocupa. Minimo de uma.

    NAO E MEDIDA. Tira as marcacoes de HTML, conta o que sobrou e divide. Serve
    para o campo chegar preenchido na tela; quem confirma e quem imprimiu. Se
    errar, erra para MAIS — pagina reservada a mais se inutiliza, pagina a
    menos nao existe.
    """
    texto = re.sub(r"<[^>]+>", " ", str(teor or ""))
    texto = re.sub(r"\s+", " ", texto).strip()
    if not texto:
        return 1
    return max(1, math.ceil(len(texto) / max(1, int(caracteres_por_pagina))))


# ------------------------------------------------------------- contador do termo

def _semente(con: sqlite3.Connection, serie: str) -> int:
    """O maior numero de termo ja em uso na serie, LENDO e nada mais.

    Semear importa: o acervo do E-Oficio trouxe 213 procuracoes e 45 escrituras
    com `numero_ordem` proprio. Comecar do 1 daria termo repetido com ato de
    1985 — e o livro nao aceita dois termos com o mesmo numero.
    """
    tipos = [t for t, s in LIVRO_DO_ATO.items() if s == serie] or [serie]
    marcas = ",".join("?" for _ in tipos)
    maior = con.execute(
        f"""SELECT MAX(x) m FROM (
                SELECT MAX(COALESCE(termo, 0)) x FROM nt_atos WHERE tipo IN ({marcas})
                UNION ALL
                SELECT MAX(COALESCE(numero_ordem, 0)) x FROM nt_atos WHERE tipo IN ({marcas})
            )""", tipos + tipos).fetchone()
    return int((maior["m"] if maior and maior["m"] is not None else 0) or 0)


def _garantir_contador(con: sqlite3.Connection, serie: str) -> sqlite3.Row:
    """A linha do contador da serie, criada na primeira vez. ESCREVE."""
    linha = con.execute("SELECT * FROM nt_termos WHERE serie=?", (serie,)).fetchone()
    if linha:
        return linha
    base = _semente(con, serie)
    con.execute(
        """INSERT INTO nt_termos(serie, proximo, maior_em_uso, observacao)
           VALUES (?,?,?,?)""",
        (serie, base + 1, base,
         "semeado a partir do maior numero de ordem do acervo"))
    return con.execute("SELECT * FROM nt_termos WHERE serie=?", (serie,)).fetchone()


def proximo_termo(con: sqlite3.Connection, serie: str,
                  consumir: bool = True) -> int:
    """O proximo numero de termo da serie. Continuo, nunca reinicia.

    Com `consumir=False` NAO ESCREVE NADA — nem o UPDATE do contador, nem a
    criacao da linha. Isso importa mais do que parece: a tela de conferencia
    chama isto num GET, e um GET que abre transacao de escrita fica dez
    segundos preso no `busy_timeout` quando outro balcao esta lavrando, e
    depois devolve 500. Tela de leitura le.
    """
    linha = con.execute("SELECT * FROM nt_termos WHERE serie=?", (serie,)).fetchone()
    if not consumir:
        return int(linha["proximo"]) if linha else _semente(con, serie) + 1
    linha = _garantir_contador(con, serie)
    numero = int(linha["proximo"])
    con.execute(
        """UPDATE nt_termos SET proximo=?, maior_em_uso=MAX(COALESCE(maior_em_uso,0),?)
           WHERE serie=?""", (numero + 1, numero, serie))
    return numero


def fixar_termo(con: sqlite3.Connection, serie: str, proximo: int,
                usuario: str | None, motivo: str | None, agora: str) -> None:
    """Corrige o contador a mao, como a tela de numeracao do RI faz.

    Recusa numero igual ou menor que o maior ja usado: isso criaria termo
    duplicado, e o `ux_nt_atos_termo` recusaria depois, no meio do atendimento.
    Melhor recusar aqui, com o motivo na tela.
    """
    linha = _garantir_contador(con, serie)
    maior = int(linha["maior_em_uso"] or 0)
    if int(proximo) <= maior:
        raise LivroError(
            f"O termo {proximo} é igual ou menor que o maior já usado nesta "
            f"série ({maior}). Isso criaria termo repetido no livro.")
    con.execute(
        """UPDATE nt_termos SET proximo=?, fixado_em=?, fixado_por=?, observacao=?
           WHERE serie=?""",
        (int(proximo), agora, usuario, (motivo or "").strip() or None, serie))


# ------------------------------------------------------------- os termos do livro

def texto_termo_abertura(serie: str, numero: Any, folhas: int, sv: dict,
                         data_extenso: str, folha_inicial: int = 1) -> str:
    """O termo de abertura, na forma do art. 30, I, da Lei 8.935/1994.

    Diz o que o livro e, quantas folhas tem, como estao numeradas e quem
    responde pela serventia. Sem isso o livro e um maco de papel.
    """
    ultima = int(folha_inicial) + int(folhas) - 1
    return (
        f"TERMO DE ABERTURA. Este Livro n. {numero}, de "
        f"{NOME_DA_SERIE.get(serie, serie.title())}, contem "
        f"{com_algarismos(folhas, feminino=True)} folhas, numeradas de "
        f"{com_algarismos(folha_inicial, feminino=True)} a "
        f"{com_algarismos(ultima, feminino=True)}, todas por mim rubricadas, e "
        f"servira para a lavratura dos atos de sua especie nesta "
        f"{sv.get('unit_name', '')}, CNS {sv.get('ri_cns', '')}, "
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}. "
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, {data_extenso}. "
        f"{sv.get('serventia_titular', '')} — {sv.get('serventia_titulo', '')}."
    )


def texto_termo_encerramento(serie: str, numero: Any, folhas: int,
                             ultima_usada: int | None,
                             primeiro_termo: int | None,
                             ultimo_termo: int | None,
                             sv: dict, data_extenso: str,
                             folha_inicial: int = 1,
                             motivo: str | None = None) -> str:
    """O termo de encerramento, com o que foi usado e o que foi inutilizado.

    A parte que costuma faltar e a ultima: dizer o que sobrou em branco e que
    ficou inutilizado. Folha em branco dentro de livro encerrado e a porta
    aberta do art. 795, § 2º.
    """
    ultima_capacidade = int(folha_inicial) + int(folhas) - 1
    usada = int(ultima_usada) if ultima_usada else None
    partes = [
        f"TERMO DE ENCERRAMENTO. Fica encerrado o presente Livro n. {numero}, "
        f"de {NOME_DA_SERIE.get(serie, serie.title())}, com "
        f"{com_algarismos(folhas, feminino=True)} folhas."
    ]
    if usada:
        partes.append(
            f"Foram utilizadas as folhas de "
            f"{com_algarismos(folha_inicial, feminino=True)} a "
            f"{com_algarismos(usada, feminino=True)}.")
    else:
        partes.append("Nenhuma folha foi utilizada.")
    if primeiro_termo and ultimo_termo:
        partes.append(
            f"Nelas foram lavrados os termos de n. {com_algarismos(primeiro_termo)} "
            f"a n. {com_algarismos(ultimo_termo)}.")
    if usada is not None and usada < ultima_capacidade:
        partes.append(
            f"As folhas de {com_algarismos(usada + 1, feminino=True)} a "
            f"{com_algarismos(ultima_capacidade, feminino=True)} ficam "
            f"INUTILIZADAS por este termo, nada mais podendo nelas ser lancado.")
    if motivo:
        partes.append(f"Motivo do encerramento: {motivo.strip()}.")
    partes.append(
        f"{sv.get('ri_cidade', '')}-{sv.get('ri_uf', '')}, {data_extenso}. "
        f"{sv.get('serventia_titular', '')} — {sv.get('serventia_titulo', '')}.")
    return " ".join(partes)


# ------------------------------------------------------------- livros

def capacidade(livro: Any) -> int:
    """Quantas folhas o livro comporta, com um piso que nao mente.

    `nt_livros.folhas` e NULLABLE e a importacao copia o `intNFL` do E-Oficio
    sem conferir. Com `folhas` NULO a conta da ultima folha dava ZERO, e o
    primeiro ato lancado no livro 27 — em uso, com 139 folhas escritas —
    "nao cabia": o sistema encerrava o livro de verdade, com um termo de
    encerramento dizendo que ele tinha "0 (zero) folhas", e abria o 28.

    Livro sem capacidade declarada vale o padrao da serventia. Errar para 200
    e recuperavel; encerrar livro em uso nao e.
    """
    n = inteiro(livro["folhas"] if not isinstance(livro, (int, float)) else livro)
    return n if n and n > 0 else CAPACIDADE_PADRAO


def ultima_folha(livro: Any) -> int:
    """O numero da ultima folha do livro."""
    return int(livro["folha_inicial"] or 1) + capacidade(livro) - 1


def folha_livre(con: sqlite3.Connection, livro: Any) -> int:
    """A primeira folha livre do livro. So LE — nao grava nada.

    POR QUE ISTO EXISTE
        Os livros abertos antes desta versao nasceram com `folha_atual = 1` e
        ficaram em 1 para sempre, ainda que tivessem atos lavrados. Confiar no
        campo mandaria o proximo ato para a folha 1 de um livro que ja vai na
        139.

        Olha tres fontes: o proprio `folha_atual`, a folha final numerica dos
        atos ja lancados por este modulo, e o numero que houver dentro do campo
        `folha` de TEXTO do acervo importado. A maior manda.
    """
    inicio = int(livro["folha_inicial"] or 1)
    maior = inicio - 1
    for linha in con.execute(
            """SELECT folha, folha_final, folha_inicial_num, folha_final_num
               FROM nt_atos WHERE livro_id=?""", (livro["id"],)):
        for valor in (linha["folha_final_num"], linha["folha_inicial_num"],
                      linha["folha_final"], linha["folha"]):
            n = inteiro(valor)
            if n is not None and n > maior:
                maior = n
    return max(int(livro["folha_atual"] or inicio), maior + 1, inicio)


def sincronizar_folha_atual(con: sqlite3.Connection, livro_id: int) -> int:
    """Grava em `folha_atual` a primeira folha livre. ESCREVE.

    So se chama de dentro de transacao de escrita — nunca de uma tela de
    leitura. Para a tela, use `folha_livre`, que faz a mesma conta sem gravar.
    """
    livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (livro_id,)).fetchone()
    if not livro:
        raise LivroError("Livro não encontrado.")
    proxima = folha_livre(con, livro)
    if proxima != int(livro["folha_atual"] or 0):
        con.execute("UPDATE nt_livros SET folha_atual=? WHERE id=?",
                    (proxima, livro_id))
    return proxima


def numero_do_proximo_livro(con: sqlite3.Connection, serie: str) -> str:
    """O numero seguinte da serie, lido do maior numero ja existente.

    Numero de livro e texto na tabela porque o acervo tem `2-F` e coisas assim.
    So o que tem digito conta para o maximo: um livro chamado `UNICO` nao
    atrapalha a sequencia, e o primeiro livro de uma serie vazia e o 1.
    """
    maior = 0
    for linha in con.execute("SELECT numero FROM nt_livros WHERE tipo=?", (serie,)):
        n = inteiro(linha["numero"])
        if n is not None:
            maior = max(maior, n)
    return str(maior + 1)


def livro_da_vez(con: sqlite3.Connection, serie: str) -> sqlite3.Row | None:
    """O livro aberto da serie. None se nao houver. So LE.

    Havendo mais de um aberto — o que nao deveria acontecer, e acontece quando
    alguem abre dois pela tela — vale o de MENOR numero: escritura-se o livro
    velho ate ele encher, nao se pula para o novo.
    """
    linhas = list(con.execute(
        """SELECT * FROM nt_livros WHERE tipo=? AND ativo=1 AND encerrado=0""",
        (serie,)))
    if not linhas:
        return None
    linhas.sort(key=lambda r: (inteiro(r["numero"]) if inteiro(r["numero"]) is not None
                               else 10 ** 9, r["id"]))
    return linhas[0]


def abrir_livro(con: sqlite3.Connection, serie: str, sv: dict, agora: str,
                data_extenso: str, usuario: str | None = None,
                numero: Any = None, folhas: int | None = None,
                abertura: str | None = None, complemento: str = "",
                termo: str | None = None, automatico: bool = False,
                folha_inicial: int = 1) -> int:
    """Abre o livro e escreve o termo de abertura. Devolve o id.

    O termo NAO e opcional. Antes desta versao o campo aceitava branco e o
    livro nascia sem termo — que e o mesmo que nascer sem identidade. Quando o
    texto nao vem, este modulo escreve o padrao.
    """
    if serie not in NOME_DA_SERIE:
        raise LivroError(f"Série de livro desconhecida: {serie!r}.")
    folhas = int(folhas or CAPACIDADE_PADRAO)
    if folhas < 1:
        raise LivroError("O livro precisa de pelo menos uma folha.")
    if folhas > LIMITE_POR_EXTENSO:
        raise LivroError(f"{folhas} folhas não é um livro plausível.")
    folha_inicial = max(1, int(folha_inicial or 1))
    numero = str(numero or numero_do_proximo_livro(con, serie)).strip()
    if not numero:
        raise LivroError("Informe o número do livro.")
    complemento = (complemento or "").strip()
    ja = con.execute(
        """SELECT id FROM nt_livros WHERE tipo=? AND numero=? AND complemento=?""",
        (serie, numero, complemento)).fetchone()
    if ja:
        raise LivroError(f"Já existe {NOME_DA_SERIE[serie]} n. {numero}.")
    texto = (termo or "").strip() or texto_termo_abertura(
        serie, numero, folhas, sv, data_extenso, folha_inicial)
    cur = con.execute(
        """INSERT INTO nt_livros
           (tipo, numero, complemento, descricao, folhas, folha_inicial,
            folha_atual, abertura, termo_abertura, aberto_por, automatico,
            encerrado, ativo, criado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,0,1,?)""",
        (serie, numero, complemento, NOME_DA_SERIE[serie], folhas,
         folha_inicial, folha_inicial,
         abertura or agora[:10], texto, usuario, 1 if automatico else 0, agora))
    return int(cur.lastrowid)


def encerrar_livro(con: sqlite3.Connection, livro_id: int, sv: dict, agora: str,
                   data_extenso: str, usuario: str | None = None,
                   motivo: str | None = None, termo: str | None = None) -> dict:
    """Encerra o livro, escrevendo o que foi usado e o que ficou inutilizado."""
    livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (livro_id,)).fetchone()
    if not livro:
        raise LivroError("Livro não encontrado.")
    if int(livro["encerrado"] or 0):
        raise LivroError("Este livro já está encerrado.")
    pendente = con.execute(
        """SELECT COUNT(*) n FROM nt_atos
           WHERE livro_id=? AND situacao='EM_LAVRATURA'""", (livro_id,)).fetchone()
    if pendente and int(pendente["n"] or 0):
        raise LivroError(
            f"Há {pendente['n']} ato(s) em lavratura neste livro. Encerre ou "
            f"cancele cada um antes de encerrar o livro.")
    uso = con.execute(
        """SELECT MIN(termo) pri, MAX(termo) ult, MAX(COALESCE(folha_final_num,
                  folha_inicial_num)) ultima
           FROM nt_atos WHERE livro_id=?""", (livro_id,)).fetchone()
    ultima = inteiro(uso["ultima"] if uso else None)
    if ultima is None:
        ultima = max(int(livro["folha_inicial"] or 1) - 1,
                     int(livro["folha_atual"] or 1) - 1)
    texto = (termo or "").strip() or texto_termo_encerramento(
        livro["tipo"], livro["numero"], capacidade(livro), ultima,
        inteiro(uso["pri"] if uso else None), inteiro(uso["ult"] if uso else None),
        sv, data_extenso, int(livro["folha_inicial"] or 1), motivo)
    inutilizadas = None
    fim = ultima_folha(livro)
    if ultima is not None and ultima < fim:
        inutilizadas = f"{ultima + 1}-{fim}"
    con.execute(
        """UPDATE nt_livros SET encerrado=1, ativo=0, encerramento=?,
           termo_encerramento=?, encerrado_por=?, folhas_inutilizadas=?
           WHERE id=?""",
        (agora[:10], texto, usuario, inutilizadas, livro_id))
    return {"livro_id": livro_id, "numero": livro["numero"],
            "ultima_folha_usada": ultima, "folhas_inutilizadas": inutilizadas,
            "termo_encerramento": texto}


# ------------------------------------------------------------- o lancamento

def previsao(con: sqlite3.Connection, tipo: str, paginas: Any = None) -> dict:
    """O que a tela mostra ANTES de lancar: que livro, que folha, que termo.

    Nao consome numero nenhum. Serve para o escrevente conferir antes de
    apertar o botao — e para o aviso de que o livro esta acabando.
    """
    serie = LIVRO_DO_ATO.get((tipo or "").upper())
    if not serie:
        return {"serie": None, "erro": f"Tipo de ato sem livro definido: {tipo!r}."}
    folhas = folhas_de(paginas) if paginas else 1
    livro = livro_da_vez(con, serie)
    dados: dict[str, Any] = {
        "serie": serie, "serie_nome": NOME_DA_SERIE.get(serie, serie),
        "termo": proximo_termo(con, serie, consumir=False),
        "folhas": folhas, "paginas_reservadas": paginas_reservadas(folhas),
        "restam": None,
    }
    if not livro:
        dados.update({"livro": None, "livro_id": None, "capacidade": None,
                      "proximo_livro": numero_do_proximo_livro(con, serie),
                      "abrira_livro": True, "folha_inicial": 1,
                      "folha_final": folhas})
        return dados
    inicio = folha_livre(con, livro)
    ultima = ultima_folha(livro)
    cabe = inicio + folhas - 1 <= ultima
    dados.update({
        "livro_id": livro["id"], "livro": livro["numero"],
        "capacidade": capacidade(livro),
        "folha_inicial": inicio if cabe else 1,
        "folha_final": (inicio + folhas - 1) if cabe else folhas,
        "restam": max(0, ultima - inicio + 1),
        "abrira_livro": not cabe,
        "proximo_livro": numero_do_proximo_livro(con, serie) if not cabe else None,
    })
    return dados


def lancar_ato(con: sqlite3.Connection, ato_id: int, sv: dict, agora: str,
               data_extenso: str, paginas: Any = None,
               usuario: str | None = None,
               capacidade_novo_livro: int | None = None) -> dict:
    """Lanca o ato no livro: atribui livro, folha inicial, folha final e termo.

    E O UNICO LUGAR QUE ESCREVE ESSES CAMPOS. Uma vez lancado, o ato nao volta
    a passar por aqui — a folha do livro foi gasta e nao se devolve.

    Roda inteiro dentro da transacao do chamador, que ja e `BEGIN IMMEDIATE`.
    Dois balcoes lancando ao mesmo tempo serializam: o segundo espera, le o
    `folha_atual` ja incrementado pelo primeiro e recebe a folha seguinte. A
    rede de baixo e o indice unico `ux_nt_atos_folha`, que transforma qualquer
    falha de logica futura em IntegrityError em vez de duas escrituras na
    mesma folha.

    UNIDADE DO ATO
        Ato nao se divide entre dois livros. Nao cabendo inteiro no que resta,
        o livro e encerrado — dizendo no termo quais folhas ficaram
        inutilizadas — e o ato inteiro comeca no livro seguinte.
    """
    ato = con.execute("SELECT * FROM nt_atos WHERE id=?", (ato_id,)).fetchone()
    if not ato:
        raise LivroError("Ato não encontrado.")

    # A TRAVA E A SITUACAO, E NAO A COLUNA VAZIA.
    #
    # A primeira versao desta guarda perguntava "ja tem termo ou folha
    # numerica?". Os 258 atos do acervo NAO TEM nem uma coisa nem outra — as
    # colunas sao novas e o acervo entrou antes delas. A guarda deixava passar
    # o acervo inteiro: um clique em "Lançar no livro" numa escritura de 2011
    # mudava a folha 139 para 141, trocava o numero de ordem, e — se o ato
    # fosse uma procuracao REVOGADA — devolvia a situacao para LAVRADO,
    # ressuscitando o mandato e reabilitando o ato para a remessa a CENSEC,
    # que filtra por LAVRADO.
    #
    # So se lanca o que esta EM LAVRATURA. Ato que ja tem livro ou folha de
    # texto, tambem nao — mesmo sem termo, ele ja esta no papel.
    ja_no_papel = (ato["termo"] is not None
                   or ato["folha_inicial_num"] is not None
                   or str(ato["livro"] or "").strip()
                   or str(ato["folha"] or "").strip())
    if ja_no_papel:
        onde = f"livro {ato['livro'] or '?'}, folha {ato['folha'] or '?'}"
        if ato["termo"] is not None:
            onde += f", termo {ato['termo']}"
        raise LivroError(f"Este ato já está lançado no {onde}. "
                         f"A folha não se relança.")
    if (ato["situacao"] or "") != "EM_LAVRATURA":
        raise LivroError(
            f"Só se lança no livro o ato em lavratura. A situação deste é "
            f"{(ato['situacao'] or '—').replace('_', ' ').lower()}.")

    tipo = (ato["tipo"] or "").upper()
    serie = LIVRO_DO_ATO.get(tipo)
    if not serie:
        raise LivroError(f"Tipo de ato sem livro definido: {tipo!r}.")

    paginas_texto = quantidade(paginas, "Páginas escritas") \
        or estimar_paginas(ato["teor"])
    folhas = folhas_de(paginas_texto)

    livro = livro_da_vez(con, serie)
    aberto_agora = False
    encerrado = None

    if livro is None:
        novo = abrir_livro(con, serie, sv, agora, data_extenso, usuario,
                           folhas=capacidade_novo_livro, automatico=True)
        livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (novo,)).fetchone()
        aberto_agora = True

    inicio = sincronizar_folha_atual(con, livro["id"])
    ultima_do_livro = ultima_folha(livro)

    if inicio + folhas - 1 > ultima_do_livro:
        # Nao cabe inteiro: encerra este e abre — ou aproveita — o seguinte.
        encerrado = encerrar_livro(
            con, livro["id"], sv, agora, data_extenso, usuario,
            motivo=(f"livro completo — o ato seguinte ocupa "
                    f"{com_algarismos(folhas, feminino=True)} folhas e não cabe "
                    f"no que restava"))
        anterior = capacidade(livro)
        # Pode haver OUTRO livro da serie ja aberto — alguem abriu dois pela
        # tela. Abrir um terceiro deixaria um livro fantasma, com termo de
        # abertura escrito e nenhum ato dentro, que a correicao pergunta de
        # onde saiu. Aproveita o que existe.
        livro = livro_da_vez(con, serie)
        if livro is None:
            novo = abrir_livro(con, serie, sv, agora, data_extenso, usuario,
                               folhas=capacidade_novo_livro or anterior,
                               automatico=True)
            livro = con.execute("SELECT * FROM nt_livros WHERE id=?",
                                (novo,)).fetchone()
            aberto_agora = True
        inicio = sincronizar_folha_atual(con, livro["id"])
        ultima_do_livro = ultima_folha(livro)
        if inicio + folhas - 1 > ultima_do_livro:
            raise LivroError(
                f"O ato ocupa {folhas} folhas e não cabe no livro "
                f"{livro['numero']}, que comporta {capacidade(livro)} e está na "
                f"folha {inicio}. Abra um livro com mais folhas antes de "
                f"lançar este ato.")

    fim = inicio + folhas - 1
    # O texto termina no verso quando o numero de paginas escritas e par.
    verso_final = (paginas_texto % PAGINAS_POR_FOLHA) == 0
    termo = proximo_termo(con, serie, consumir=True)

    con.execute(
        """UPDATE nt_atos SET
               livro_id=?, livro=?, livro_complemento=?, serie=?,
               folha=?, folha_final=?, folha_inicial_num=?, folha_final_num=?,
               folhas=?, paginas=?, verso_final=?,
               termo=?, situacao=?,
               lancado_em=?, lancado_por=?
           WHERE id=?""",
        (livro["id"], livro["numero"],
         (livro["complemento"] or "").strip() or None, serie,
         rotulo_folha(inicio), rotulo_folha(fim, verso=verso_final),
         inicio, fim, folhas, paginas_reservadas(folhas),
         1 if verso_final else 0, termo, "LAVRADO",
         agora, usuario, ato_id))

    con.execute("UPDATE nt_livros SET folha_atual=? WHERE id=?",
                (fim + 1, livro["id"]))

    fechou_agora = None
    if fim >= ultima_do_livro:
        # Encheu com este ato. Encerra e JA ABRE O SEGUINTE — deixar a serie
        # sem livro aberto adiaria o problema para o proximo atendimento, que
        # e sempre a hora pior.
        anterior = capacidade(livro)
        fechou_agora = encerrar_livro(
            con, livro["id"], sv, agora, data_extenso, usuario,
            motivo="livro completo")
        if livro_da_vez(con, serie) is None:
            abrir_livro(con, serie, sv, agora, data_extenso, usuario,
                        folhas=capacidade_novo_livro or anterior,
                        automatico=True)

    inutilizar = None if verso_final else rotulo_folha(fim, verso=True)

    return {
        "ato_id": ato_id, "serie": serie, "termo": termo,
        "livro_id": livro["id"], "livro": livro["numero"],
        "folha": rotulo_folha(inicio),
        "folha_final": rotulo_folha(fim, verso=verso_final),
        "folhas": folhas, "paginas_texto": paginas_texto,
        "paginas_reservadas": paginas_reservadas(folhas),
        "inutilizar": inutilizar,
        "livro_aberto_automaticamente": aberto_agora,
        "livro_encerrado": (encerrado or fechou_agora or {}).get("numero"),
        "folhas_inutilizadas": (encerrado or fechou_agora or {}).get(
            "folhas_inutilizadas"),
    }


# ------------------------------------------------------------- acervo

def desambiguar_folhas_do_acervo(con: sqlite3.Connection) -> int:
    """Da complemento de folha aos atos do acervo que dividem a mesma folha.

    POR QUE ISTO IMPORTA
        A CENSEC identifica o ato pela chave (livro, livroComplemento, folha,
        folhaComplemento). Dois atos na mesma folha do mesmo livro, ambos sem
        complemento, sao recusados por DUPLICIDADE. No acervo importado isso ja
        acontece — e a coluna `folha_complemento` existia, era lida por
        `notas_censec.py`, e nada jamais a escrevia.

        O complemento nao muda o livro de papel: e um desempate de remessa. Por
        isso o primeiro ato de cada folha fica SEM complemento (e o que a
        central ja conhece) e os seguintes recebem A, B, C — na ordem do
        numero de ordem e do id, que e estavel entre execucoes.

    Idempotente: rodar duas vezes nao muda nada, e nao toca em ato que ja tenha
    complemento posto a mao.
    """
    grupos: dict[tuple, list] = {}
    for linha in con.execute(
            """SELECT id, tipo, livro_id, livro, folha, numero_ordem,
                      folha_complemento
               FROM nt_atos
               WHERE livro IS NOT NULL AND folha IS NOT NULL
               ORDER BY COALESCE(numero_ordem, 0), id"""):
        # A SERIE ENTRA NA CHAVE.
        #
        # Livro 27 de escrituras e livro 27 de procuracoes sao dois livros de
        # papel diferentes, e cada serie tem a sua numeracao. Agrupar so por
        # (numero, folha) juntava os dois e dava complemento a uma procuracao
        # que nao tinha duplicidade nenhuma — mudando, sem motivo, a chave com
        # que a CENSEC ja conhece aquele ato.
        serie = LIVRO_DO_ATO.get((linha["tipo"] or "").upper(), linha["tipo"])
        chave = (linha["livro_id"] if linha["livro_id"] is not None
                 else (serie, str(linha["livro"]).strip().upper().replace("-", "")),
                 str(linha["folha"]).strip().upper())
        grupos.setdefault(chave, []).append(linha)
    letras = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    mudou = 0
    for atos in grupos.values():
        if len(atos) < 2:
            continue
        for posicao, ato in enumerate(atos[1:]):
            if (ato["folha_complemento"] or "").strip():
                continue
            sufixo = letras[posicao] if posicao < len(letras) else str(posicao + 1)
            con.execute("UPDATE nt_atos SET folha_complemento=? WHERE id=?",
                        (sufixo, ato["id"]))
            mudou += 1
    return mudou


def conferir_livro(con: sqlite3.Connection, livro_id: int) -> dict:
    """Confere o livro contra si mesmo. E o que a correicao pergunta.

    Devolve as tres perguntas que o livro tem de responder sozinho: ha folha
    pulada, ha folha repetida, e a numeracao dos termos corre sem furo.
    """
    livro = con.execute("SELECT * FROM nt_livros WHERE id=?", (livro_id,)).fetchone()
    if not livro:
        raise LivroError("Livro não encontrado.")
    atos = [r for r in con.execute(
        """SELECT id, termo, folha, folha_inicial_num, folha_final_num, situacao
           FROM nt_atos WHERE livro_id=?
           ORDER BY COALESCE(folha_inicial_num, 0), id""", (livro_id,))]
    inicio = int(livro["folha_inicial"] or 1)
    ocupadas: dict[int, list[int]] = {}
    buracos, repetidas = [], []
    esperada = inicio
    for a in atos:
        i = inteiro(a["folha_inicial_num"]) or inteiro(a["folha"])
        f = inteiro(a["folha_final_num"]) or i
        if i is None:
            continue
        if i > esperada:
            buracos.append(f"{esperada}-{i - 1}" if i - 1 > esperada else str(esperada))
        for n in range(i, (f or i) + 1):
            ocupadas.setdefault(n, []).append(a["id"])
        esperada = max(esperada, (f or i) + 1)
    repetidas = [n for n, ids in sorted(ocupadas.items()) if len(ids) > 1]
    termos = [inteiro(a["termo"]) for a in atos if a["termo"] is not None]
    furos_termo = []
    if termos:
        termos.sort()
        for anterior, seguinte in zip(termos, termos[1:]):
            if seguinte - anterior > 1:
                furos_termo.append(f"{anterior + 1}-{seguinte - 1}")
    return {
        "livro": livro["numero"], "serie": livro["tipo"],
        "atos": len(atos), "folha_atual": int(livro["folha_atual"] or inicio),
        "capacidade": int(livro["folhas"] or 0),
        "folhas_puladas": buracos, "folhas_repetidas": repetidas,
        "termos_faltando": furos_termo,
        "sem_termo_de_abertura": not (livro["termo_abertura"] or "").strip(),
        "em_lavratura": sum(1 for a in atos if a["situacao"] == "EM_LAVRATURA"),
    }


# ------------------------------------------------ termo de comparecimento (#91)

ORIGEM_PRESENCA_RECONHECIMENTO = "RECONHECIMENTO"


def chave_presenca_reconhecimento(reconhecimento_id: int, parte_id: int) -> str:
    return f"{int(reconhecimento_id)}:{int(parte_id)}"


def parse_livro_folha_busca(busca: str) -> tuple[str | None, str | None]:
    import re
    m = re.match(r"^\s*(\S+)\s*[/\-]\s*(\d+)\s*$", busca or "")
    if not m:
        return None, None
    return m.group(1).strip(), m.group(2).strip()


def texto_termo_comparecimento(
    *,
    sv: dict,
    reconhecimento: dict,
    parte: dict,
    data_extenso: str,
) -> str:
    nome = (parte.get("nome") or parte.get("nome_cartao") or "").strip()
    doc = (parte.get("documento") or parte.get("documento_cartao") or "").strip()
    doc_linha = f", portador(a) do CPF/CNPJ n {doc}" if doc else ""
    doc_desc = (
        reconhecimento.get("documento_descricao")
        or reconhecimento.get("documento_tipo")
        or "documento apresentado"
    )
    doc_desc = str(doc_desc).strip()
    selo = (reconhecimento.get("selo") or "").strip()
    selo_linha = f" Selo n {selo}." if selo else ""
    oficial = (reconhecimento.get("oficial") or "").strip()
    funcao = (reconhecimento.get("oficial_funcao") or "").strip()
    assina = " - ".join(x for x in (oficial, funcao) if x)
    return (
        f'<p align="center"><b>{sv.get("unit_name") or ""}</b><br/>'
        f'{sv.get("serventia_titulo") or ""}: {sv.get("serventia_titular") or ""}<br/>'
        f'CNS {sv.get("ri_cns") or ""} - {sv.get("endereco_completo") or ""}</p>'
        f"<p><b>TERMO DE COMPARECIMENTO</b></p>"
        f"<p>Saibam quantos este publico instrumento virem que, aos "
        f"{data_extenso}, nesta serventia, compareceu "
        f"<b>{nome}</b>{doc_linha}, reconhecendo por <b>autenticidade</b> "
        f"a assinatura constante de {doc_desc}.{selo_linha}</p>"
        f"<p>E, por ser verdade, firmou o presente termo.</p>"
        f"<p>________________________________<br/>{nome}</p>"
        f"<p>________________________________<br/>{assina or 'Oficial / escrevente'}</p>"
    )


def registrar_presenca_reconhecimento(
    con,
    *,
    reconhecimento_id: int,
    parte_id: int,
    data: str,
    nome: str,
    documento: str | None,
    cartao_id: int | None,
    selo: str | None,
    conteudo: str,
    oficial: str | None,
    agora: str,
) -> int:
    chave = chave_presenca_reconhecimento(reconhecimento_id, parte_id)
    linha = con.execute(
        "SELECT id FROM nt_presencas WHERE origem=? AND origem_chave=?",
        (ORIGEM_PRESENCA_RECONHECIMENTO, chave),
    ).fetchone()
    if linha:
        con.execute(
            """UPDATE nt_presencas SET data=?, nome=?, documento=?,
               cartao_id=?, reconhecimento_id=?, selo=?, quantidade=1,
               conteudo=?, oficial=? WHERE id=?""",
            (
                data,
                nome,
                documento,
                cartao_id,
                int(reconhecimento_id),
                selo,
                conteudo,
                oficial,
                linha[0],
            ),
        )
        return int(linha[0])
    cur = con.execute(
        """INSERT INTO nt_presencas
           (data, ordem, nome, documento, cartao_id, reconhecimento_id, selo,
            quantidade, conteudo, oficial, origem, origem_chave, criado_em)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            data,
            None,
            nome,
            documento,
            cartao_id,
            int(reconhecimento_id),
            selo,
            1,
            conteudo,
            oficial,
            ORIGEM_PRESENCA_RECONHECIMENTO,
            chave,
            agora,
        ),
    )
    return int(cur.lastrowid)
