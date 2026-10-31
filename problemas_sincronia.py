"""OS PROBLEMAS DA SERVENTIA, MASCARADOS, UM ARQUIVO POR PROBLEMA — fase 1.

Nasceu em 27/10/2026 (roteiro «sincronia dos problemas»). Os problemas
registrados na produção e no SANDBOX têm de chegar ao computador de
desenvolvimento **sem dado pessoal**, num repositório Git privado que as duas
máquinas sincronizam:

    produção/SANDBOX ──exportar (mascarado)──▶ repositório privado ──▶ desenvolvimento

**AS FERRAMENTAS ANTIGAS NÃO SERVEM** (`tools/export_problemas_fila.py` e
`tools/import_problemas_fila.py`): leem o SQLite de antes da 3.7.0 e levam a
linha crua, com `detalhe` e `diagnostico` sem máscara — o que não pode ir a
repositório nenhum, nem privado.

O QUE ESTE MÓDULO NUNCA FAZ:
  - exporta texto sem passar por `ajuda_privacidade.sanitizar_texto` — a mesma
    máscara do relatório para conserto (`ajuda_problemas.montar_relatorio`) —,
    seguida de `_mascarar_referencias`, que vale só aqui;
  - exporta login ou nome de quem usou (`criado_por`, `ultimo_usuario`,
    `fechado_por`, `reaberto_por`, `nota_dev_por`);
  - escreve fora da pasta informada, ou apaga arquivo dela;
  - faz `git` ou abre conexão de rede. Commit e envio do repositório privado
    são da operação (fase 3), fora deste código;
  - fecha problema. A exportação só lê o banco; quem grava é `importar` (a
    nota do desenvolvimento, pela `anotar_desenvolvimento` da tela) e
    `classificar`, e nenhum dos dois mexe na `situacao`.

A VOLTA (fase 2) está na seção «o retorno», mais abaixo, e A OPERAÇÃO (fase 3:
o lançador e a tarefa agendada que fazem o `git`) na seção «a operação».

A LINHA DE COMANDO MORA AQUI, EM `main`, E NÃO EM `tools/`. O varredor de
função sem tela (`tests/test_funcao_sem_tela.py`) só lê os módulos da raiz, e
`main` é raiz para ele: com a linha de comando em `tools/`, `exportar` e
`classificar_reproducao` pareceriam órfãs. `tools/problemas_sincronia.py` só
chama `main`.
"""
from __future__ import annotations

import argparse
import os
import re
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import ajuda_privacidade as PRIV
import ajuda_problemas as AP
from bd_nativo import banco

ASSINATURA = "tools/problemas_sincronia.py"

# O RESOLVIDO RECENTE VAI JUNTO: quem conserta precisa ver o que fechou, e não
# só o que falta. Trinta dias é o bastante para a próxima sincronia pegar.
DIAS_DOS_RESOLVIDOS = 30

PREFIXOS = {"OFICIAL": "of", "SANDBOX": "sb"}

PASTA_DOS_PROBLEMAS = "problemas"
ARQUIVO_DO_INDICE = "INDICE.md"


def nome_do_arquivo(problema: dict, ambiente: str) -> str:
    """`of-0035.md` ou `sb-0012.md`. Só calcula.

    O PREFIXO EXISTE PORQUE OS NÚMEROS SE REPETEM: o #12 do oficial e o #12 do
    SANDBOX são problemas diferentes, e no mesmo repositório se confundiriam.
    """
    amb = str(ambiente or "").strip().upper()
    if amb not in PREFIXOS:
        raise AP.ProblemaError(
            f"Ambiente desconhecido: «{ambiente}». Os que existem são "
            + ", ".join(PREFIXOS) + ".")
    return f"{PREFIXOS[amb]}-{int(problema['id']):04d}.md"


def _vazio(valor: Any) -> str:
    texto = str(valor or "").strip()
    return texto or "(vazio)"


# ------------------------------------------- as referências, só na exportação
#
# 31/10/2026: a primeira exportação real mostrou referências que a máscara comum
# não conhece. **ELA NÃO MUDA**: também protege o que vai à IA, e o vocabulário
# dela foi medido contra os nomes da serventia. O que é mais rígido fica aqui e
# vale só para o que sai neste repositório; o relatório para conserto da tela
# (`ajuda_problemas.montar_relatorio`) não ganha esta passagem.

_TIPO_DA_REFERENCIA = "REFERENCIA_REGISTRAL"
_REFERENCIA_JA_MARCADA = re.compile(rf"\[{_TIPO_DA_REFERENCIA}_(\d+)\]")
_ANTES_DO_NUMERO = r"\s*(?:n[ºo°]\.?\s*)?(?:[:=#-]\s*)?"
# O INTEIRO NÃO É CÓDIGO COM PONTOS NEM DATA NEM HORA: «Ato: 16.24.4» e «ato de
# 01/01/2026» ficam. O ano de um número («321/2026») sai junto com ele.
_INTEIRO = r"\d+(?:/\d{4})?(?!\d|\.\d|:\d|/\d|-\d)"
_REFERENCIAS_ROTULADAS = (
    ("folha", re.compile(
        rf"(?P<inicio>\b(?:fls?\b\.?|folhas?\b){_ANTES_DO_NUMERO})"
        r"(?P<valor>\d+[vf]?(?:\s*(?:/|-|a|e)\s*\d+[vf]?)*)\b", re.I)),
    # O ASSENTO PODE TER PONTO DE MILHAR, e por isso não é o `_INTEIRO`.
    ("assento", re.compile(
        rf"(?P<inicio>\bassentos?\b{_ANTES_DO_NUMERO})"
        r"(?P<valor>\d+(?:\.\d+)*(?:/\d{4})?)(?!\d|:\d|/\d|-\d)", re.I)),
    ("ato", re.compile(
        rf"(?P<inicio>\batos?\b{_ANTES_DO_NUMERO})(?P<valor>{_INTEIRO})", re.I)),
    ("interno", re.compile(
        r"(?P<inicio>\b(?P<ato>habilita[cç][aã]o|prenota[cç][aã]o|averba[cç][aã]o|"
        rf"certid[aã]o)\b{_ANTES_DO_NUMERO})(?P<valor>{_INTEIRO})", re.I)),
)
# A LETRA ANTES DA PASTA É O QUE PROTEGE A DATA: em «01/01/2026», o que vem antes
# da barra é dígito. A barra dobrada é a do `repr` num erro do Python.
_PASTA_NUMERICA = re.compile(
    r"(?P<inicio>(?:[^\W\d]|\])[\\/]+)(?P<valor>\d+(?:[\\/]+\d+)*)(?=[\\/])")
# SÓ O QUE TEM CARA DE TABELA. Qualquer `nome:número` levaria `width:1` e
# `localhost:8780`; o ponto antes de `py` deixa `app.py:205` em paz.
_TABELA_COM_NUMERO = re.compile(
    r"(?<![\w./\\-])(?P<inicio>(?:[a-z][a-z0-9]*(?:_[a-z0-9]+)+|tb[a-z0-9]+|"
    r"pessoas|users|recibos|livroauxiliar[a-z]*):)(?P<valor>\d+)\b(?![:.]\d)")
# NUMA CASA PEQUENA, FUNÇÃO E HORA DIZEM QUEM PEDIU. A data fica. Entre a função
# e o «em» só passa marcador: «Pedido do sistema falhou em…» não é tocado.
_PEDIDO_DE_QUEM = re.compile(
    r"\b(?P<pedido>pedido)\s+(?:feito\s+)?(?:d[ao]s?|pel[ao]s?)\s+"
    r"(?:(?:escrevente|oficial|substitut[oa]|auxiliar|atendente|tabeli[ãa]o?|"
    r"registrador[a]?|prepost[oa]|escritur[aá]ri[oa]|interin[oa]|operador[a]?|"
    r"funcion[aá]ri[oa]|colaborador[a]?)\b|\[PESSOA_\d+\])"
    r"(?:\s*,?\s*\[PESSOA_\d+\])*"
    r"(?:\s+em\s+(?P<data>\d{1,2}/\d{1,2}/\d{2,4}|\d{4}-\d{2}-\d{2}))?"
    r"(?:\s*\(?\s*~?\s*(?:[àa]s\s+)?\d{1,2}[:h]\d{2}(?:\s*UTC\s*[-+]\d{1,2})?\s*\)?)?",
    re.I)


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", texto)
                   if not unicodedata.combining(c))


def _mascarar_referencias(texto: str) -> str:
    """Troca as referências que a máscara comum não conhece. Só calcula, e NUNCA
    RECUSA: quem recusa é `PRIV.sanitizar_texto`, que roda antes.

    **A NUMERAÇÃO CONTINUA A DA MÁSCARA COMUM**: ela já numerou a matrícula, e
    recomeçar em 01 faria duas referências diferentes parecerem a mesma.
    """
    usados = [int(n) for n in _REFERENCIA_JA_MARCADA.findall(texto)]
    proximo = [max(usados, default=0)]
    marcadores: dict[tuple[str, str], str] = {}

    def marcador(familia: str, valor: str) -> str:
        chave = (familia, re.sub(r"\s+", " ", valor).casefold())
        if chave not in marcadores:
            proximo[0] += 1
            marcadores[chave] = f"[{_TIPO_DA_REFERENCIA}_{proximo[0]:02d}]"
        return marcadores[chave]

    def trocar_rotulada(familia: str):
        def trocar(m: re.Match) -> str:
            ato = m.groupdict().get("ato")
            qual = f"{familia}:{_sem_acento(ato).casefold()}" if ato else familia
            return f"{m.group('inicio')}{marcador(qual, m.group('valor'))}"
        return trocar

    def trocar_pedido(m: re.Match) -> str:
        data = f" em {m.group('data')}" if m.group("data") else ""
        return f"{m.group('pedido')}{data}"

    def trocar_pasta(m: re.Match) -> str:
        pastas = re.sub(r"\d+", lambda n: marcador("pasta", n.group(0)),
                        m.group("valor"))
        return f"{m.group('inicio')}{pastas}"

    def trocar_tabela(m: re.Match) -> str:
        return f"{m.group('inicio')}{marcador(m.group('inicio'), m.group('valor'))}"

    saida = _PEDIDO_DE_QUEM.sub(trocar_pedido, str(texto or ""))
    for familia, padrao in _REFERENCIAS_ROTULADAS:
        saida = padrao.sub(trocar_rotulada(familia), saida)
    saida = _PASTA_NUMERICA.sub(trocar_pasta, saida)
    return _TABELA_COM_NUMERO.sub(trocar_tabela, saida)


def _com_fim_de_linha_unico(texto: Any) -> str:
    """`read_text` troca `\\r\\n` e `\\r` por `\\n`: sem isto, um relato do Windows
    pareceria mudado a cada ciclo."""
    return str(texto or "").replace("\r\n", "\n").replace("\r", "\n")


# ------------------------------------------------- o aviso de texto mascarado
#
# O BALCÃO ESCREVE EM MAIÚSCULAS, e palavra fora do vocabulário vira
# `[PESSOA_nn]`. Ampliar o vocabulário depende de medir contra os nomes da
# serventia; o que dá para fazer aqui é dizer a quem lê que o texto não presta.
#
# A REGRA COMPARA O ANTES E O DEPOIS, e não a proporção de marcadores no fim: um
# marcador só engole várias palavras. Palavra de uma ou duas letras não conta,
# para «DE» e «A» não fazerem um texto vazio parecer legível. O corte é
# julgamento: o repositório só tem o texto já mascarado, sem o original para medir.

AVISO_DE_TEXTO_MASCARADO = (
    "**Texto muito mascarado: leia na tela do sistema antes de concluir.**")
_PALAVRA_QUE_CONTA = re.compile(r"[^\W\d_]{3,}")
_PERDA_MINIMA_DO_AVISO = 3


def _escrito_por_gente(p: dict) -> str:
    """Título e detalhe de um RELATADO, sem o stack trace colado. As outras
    origens são da máquina, e o `diagnostico` é da IA."""
    if p.get("origem") != "RELATADO":
        return ""
    texto = _com_fim_de_linha_unico(f"{p.get('titulo') or ''}\n{p.get('detalhe') or ''}")
    return texto.split("Traceback (most recent call last)")[0]


def _muito_mascarado(p: dict) -> bool:
    original = _escrito_por_gente(p)
    seguro = _mascarar_referencias(PRIV.sanitizar_texto(original))
    antes = len(_PALAVRA_QUE_CONTA.findall(original))
    depois = len(_PALAVRA_QUE_CONTA.findall(_MARCADOR.sub(" ", seguro)))
    return antes - depois >= _PERDA_MINIMA_DO_AVISO and depois * 2 < antes


def texto_do_arquivo(problema: dict, ambiente: str, mapa: dict | None) -> str:
    """O arquivo de um problema, já mascarado. Só calcula.

    O CABEÇALHO É UMA INFORMAÇÃO POR LINHA, para programa e gente lerem sem
    traduzir; depois vem o mesmo bloco do relatório para conserto
    (`_bloco_do_problema`), que é o mesmo texto da tela.

    **O TEXTO INTEIRO PASSA PELA MÁSCARA**, e não só o `detalhe`: o título de
    um RELATADO é escrito por gente, e gente escreve nome. Se sobrar dado
    depois de mascarar, `PRIV.PrivacidadeError` sobe — e quem chama recusa
    este problema, em vez de deixá-lo sair.

    **AS REFERÊNCIAS SÓ VALEM NO CORPO**: os campos do cabeçalho são lidos por
    programa, e a `impressao` tem de voltar igual no retorno.
    """
    p = dict(problema)
    cabecalho = [
        "---",
        f"ambiente: {str(ambiente).upper()}",
        f"id: {int(p['id'])}",
        f"impressao: {_vazio(p.get('impressao'))}",
        f"origem: {_vazio(p.get('origem'))}",
        f"situacao: {_vazio(p.get('situacao'))}",
        f"reproducao: {AP.reproducao_de(p)}",
        f"versao: {_vazio(p.get('versao'))}",
        f"vezes: {int(p.get('vezes') or 0)}",
        f"ultima_em: {_vazio(p.get('ultima_em'))}",
        f"nota_dev_estado: {_vazio(p.get('nota_dev_estado'))}",
        "---",
        "",
    ]
    seguro = PRIV.sanitizar_texto(_com_fim_de_linha_unico(
        "\n".join(cabecalho + AP._bloco_do_problema(p, mapa))))
    topo, fecho, corpo = seguro.partition("\n---\n")
    texto = f"{topo}{fecho}{_mascarar_referencias(corpo)}"
    if _muito_mascarado(p):
        texto += f"\n{AVISO_DE_TEXTO_MASCARADO}\n"
    return texto


def _titulo_do_indice(p: dict) -> str:
    """O título, mascarado sozinho e antes de entrar na tabela: `_NOME_ROTULADO`
    aceita o `|` e iria até o fim da linha montada. Sobe `PrivacidadeError`
    como `texto_do_arquivo`."""
    titulo = (_com_fim_de_linha_unico(p.get("titulo"))
              .replace("\n", " ").replace("|", "/"))
    return _mascarar_referencias(PRIV.sanitizar_texto(titulo))


def _dia(texto: Any) -> str:
    """`2026-10-27T10:15:00` e `2026-10-27 10:15` comparam pelo mesmo dia."""
    return str(texto or "")[:10]


def _problemas_da_sincronia(con, *, agora: str) -> list[dict]:
    """Os não resolvidos, mais os resolvidos dos últimos trinta dias. Só LÊ."""
    limite = (datetime.fromisoformat(str(agora)[:19].replace(" ", "T"))
              - timedelta(days=DIAS_DOS_RESOLVIDOS)).date().isoformat()
    linhas = banco(con).ler(
        """SELECT * FROM aj_problemas
            WHERE situacao IN ('ABERTO', 'RELATADO', 'RESOLVIDO')
            ORDER BY id""")
    return [dict(p) for p in linhas
            if p["situacao"] != "RESOLVIDO" or _dia(p.get("fechado_em")) >= limite]


def _voltou(p: dict) -> bool:
    return bool(p.get("relatado_em")) and p.get("situacao") == "ABERTO"


def _texto_do_indice(linhas: list[dict], *, ambiente: str) -> str:
    """A tabela do repositório. Primeiro o que voltou depois de relatado — a
    linha mais importante da lista —, depois o que mais se repete.

    O título chega mascarado (`_titulo_do_indice`), e as outras colunas vêm de
    valores controlados: mascarar a tabela montada a quebraria."""
    ordem = sorted(linhas, key=lambda x: (not _voltou(x["p"]),
                                          -int(x["p"].get("vezes") or 0),
                                          int(x["p"]["id"])))
    partes = [
        f"# Problemas — {ambiente}",
        "",
        "> Dados pessoais, sensíveis e segredos foram substituídos.",
        "",
        "| Arquivo | Título | Situação | Reprodução | Retorno |",
        "|---|---|---|---|---|",
    ]
    for x in ordem:
        p = x["p"]
        situacao = str(p.get("situacao") or "")
        if _voltou(p):
            situacao += " (voltou depois de relatado)"
        retorno = AP.ROTULO_CURTO_DEV.get(p.get("nota_dev_estado") or "", "—")
        partes.append(
            f"| [{x['arquivo']}]({PASTA_DOS_PROBLEMAS}/{x['arquivo']}) "
            f"| {x['titulo']} | {situacao} "
            f"| {AP.REPRODUCOES[AP.reproducao_de(p)]} | {retorno} |")
    if not ordem:
        partes.append("| — | Nenhum problema nesta exportação | — | — | — |")
    return "\n".join(partes) + "\n"


def _dentro(pasta: Path, alvo: Path) -> Path:
    """O caminho, conferido: nada se escreve fora da pasta informada."""
    resolvido = alvo.resolve()
    if resolvido != pasta and pasta not in resolvido.parents:
        raise AP.ProblemaError(f"Recusei escrever fora da pasta: {alvo}")
    return resolvido


def _gravar_se_mudou(caminho: Path, texto: str, *, dry_run: bool) -> bool:
    """True quando escreveu (ou escreveria). O MESMO TEXTO NÃO SE REGRAVA:
    o Git registraria mudança à toa a cada sincronia."""
    if caminho.is_file() and caminho.read_text(encoding="utf-8") == texto:
        return False
    if not dry_run:
        caminho.parent.mkdir(parents=True, exist_ok=True)
        caminho.write_text(texto, encoding="utf-8", newline="\n")
    return True


def exportar(db, pasta: Any, *, agora: str, ambiente: str | None = None,
             mapa: dict | None = None, dry_run: bool = False) -> dict:
    """Escreve um arquivo por problema em `<pasta>/problemas/` e o índice em
    `<pasta>/INDICE.md`. ESCREVE EM DISCO; SÓ LÊ O BANCO.

    **NUNCA APAGA.** Um problema que sumiu do banco fica com o arquivo como
    estava: apagar é decisão de quem cuida do repositório, e não de uma
    exportação que só enxerga um dos dois ambientes.

    Problema que a máscara recusa não sai, e os outros seguem: devolve
    `{"escritos": [...], "iguais": n, "recusados": [{"id", "porque"}]}`.
    """
    raiz = Path(pasta).resolve()
    with db.connect() as con:
        amb = (ambiente or AP.ambiente_abertura_padrao(con)).strip().upper()
        problemas = _problemas_da_sincronia(con, agora=agora)

    escritos: list[str] = []
    iguais = 0
    recusados: list[dict] = []
    no_indice: list[dict] = []
    for p in problemas:
        arquivo = nome_do_arquivo(p, amb)
        try:
            texto = texto_do_arquivo(p, amb, mapa)
            titulo = _titulo_do_indice(p)
        except PRIV.PrivacidadeError as erro:
            recusados.append({"id": int(p["id"]), "porque": str(erro)})
            continue
        destino = _dentro(raiz, raiz / PASTA_DOS_PROBLEMAS / arquivo)
        if _gravar_se_mudou(destino, texto, dry_run=dry_run):
            escritos.append(f"{PASTA_DOS_PROBLEMAS}/{arquivo}")
        else:
            iguais += 1
        no_indice.append({"arquivo": arquivo, "p": p, "titulo": titulo})

    indice = _dentro(raiz, raiz / ARQUIVO_DO_INDICE)
    if _gravar_se_mudou(indice, _texto_do_indice(no_indice, ambiente=amb),
                        dry_run=dry_run):
        escritos.append(ARQUIVO_DO_INDICE)
    return {"escritos": escritos, "iguais": iguais, "recusados": recusados,
            "ambiente": amb}


# ------------------------------------------------------------- o retorno
#
# FASE 2, 27/10/2026: a volta. O desenvolvimento escreve `retorno/of-0035.md`
# (o mesmo nome do arquivo do problema), o repositório leva, e a produção
# importa como nota do desenvolvimento:
#
#     desenvolvimento ──responder──▶ retorno/of-0035.md ──▶ repositório privado
#     produção ◀──importar (grava a nota do desenvolvimento)── repositório privado
#
# **NADA AQUI FECHA PROBLEMA.** A importação grava pela mesma
# `anotar_desenvolvimento` da tela, que não mexe na `situacao`.

PASTA_DO_RETORNO = "retorno"

# O RETORNO É UMA NOTA, E NÃO UM DESPEJO. Dezesseis quilobytes cabem qualquer
# nota de gente; o que passa disso é arquivo errado posto na pasta.
LIMITE_DO_RETORNO = 16 * 1024

# O QUANTO O `em` PODE ESTAR À FRENTE DA HORA DA IMPORTAÇÃO (fuso, relógio).
DIAS_DE_FOLGA_DO_EM = 1

_NOME_DO_ARQUIVO = re.compile(r"^(of|sb)-(\d{4})\.md$")
_MARCADOR = re.compile(r"\[([A-Z_]+)_\d+\]")

CHAVES_OBRIGATORIAS_DO_RETORNO = ("ambiente", "id", "impressao", "estado", "em")
CHAVES_DO_RETORNO = CHAVES_OBRIGATORIAS_DO_RETORNO + ("prova", "reproducao")

# QUEM GRAVA A NOTA IMPORTADA. Vai no `nota_dev_por` e como mandante da
# auditoria: a nota é do desenvolvimento, e a ferramenta só a trouxe.
POR_DA_SINCRONIA = "desenvolvimento (sincronia)"


def _cabecalho(texto: str, nome: str) -> tuple[dict[str, str], str]:
    """Separa o cabeçalho `--- … ---` do corpo. Só calcula.

    Recusa o que um programa não saberia ler sem adivinhar: sem os `---`,
    linha sem `:`, chave repetida.
    """
    linhas = str(texto or "").replace("\r\n", "\n").split("\n")
    if not linhas or linhas[0].strip() != "---":
        raise AP.ProblemaError(f"{nome}: o arquivo não começa com «---».")
    try:
        fim = next(i for i, x in enumerate(linhas[1:], 1) if x.strip() == "---")
    except StopIteration:
        raise AP.ProblemaError(
            f"{nome}: o cabeçalho não fecha com «---».") from None
    campos: dict[str, str] = {}
    for linha in linhas[1:fim]:
        if not linha.strip():
            continue
        chave, dois_pontos, valor = linha.partition(":")
        chave = chave.strip()
        if not dois_pontos or not chave:
            raise AP.ProblemaError(
                f"{nome}: linha do cabeçalho sem «chave: valor»: «{linha}».")
        if chave in campos:
            raise AP.ProblemaError(f"{nome}: a chave «{chave}» aparece duas vezes.")
        campos[chave] = valor.strip()
    return campos, "\n".join(linhas[fim + 1:]).strip()


def _instante(texto: Any, nome: str) -> datetime:
    """`2026-10-28T14:00:00` e `2026-10-28 14:00` são o mesmo instante."""
    try:
        return datetime.fromisoformat(str(texto or "").strip().replace(" ", "T"))
    except ValueError:
        raise AP.ProblemaError(
            f"{nome}: «{texto}» não é uma data e hora (use 2026-10-28T14:00:00)."
        ) from None


def _sem_dado_de_pessoa(campo: str, texto: str, nome: str) -> None:
    """Recusa a nota ou a prova que traz dado de pessoa. Só confere.

    **O RETORNO NÃO PASSA PELA MÁSCARA**: ela trocaria pedaços da nota por
    marcadores, e quem lê na produção receberia texto ilegível. Em vez de
    mascarar, recusa — e diz o que achou, para quem responde reescrever.

    `ajuda_privacidade` não tem detector que só aponte; a régua é a da
    leitura de código (`nomes_livres=False`): se a passagem muda o texto,
    havia ali o que ela remove. Decisão de 27/10/2026: a referência registral
    com número (matrícula, folha, protocolo) também é recusada — a exportação
    a mascara, e o desenvolvimento não tem por que escrever o número real.
    """
    seguro = PRIV.sanitizar_para_modelo(texto, nomes_livres=False)
    if seguro != texto:
        tipos = sorted(set(_MARCADOR.findall(seguro))) or ["dado de pessoa"]
        raise AP.ProblemaError(
            f"{nome}: a {campo} tem o que não pode ir ao repositório "
            f"({', '.join(tipos)}). Reescreva sem o dado — por exemplo, "
            "«a matrícula do teste» em vez do número.")


def ler_retorno(texto: str, nome: str) -> dict:
    """Lê e confere um arquivo de retorno, sem banco. Só calcula.

    Devolve `{ambiente, id, impressao, estado, em, prova, reproducao, nota}`
    ou levanta `ProblemaError` com a frase pronta.
    """
    achado = _NOME_DO_ARQUIVO.match(str(nome or ""))
    if not achado:
        raise AP.ProblemaError(
            f"{nome}: o nome do arquivo não segue o padrão «of-0035.md» / "
            "«sb-0012.md».")
    campos, nota = _cabecalho(texto, nome)
    desconhecidas = sorted(set(campos) - set(CHAVES_DO_RETORNO))
    if desconhecidas:
        raise AP.ProblemaError(
            f"{nome}: chave desconhecida no cabeçalho: {', '.join(desconhecidas)}. "
            f"As que existem: {', '.join(CHAVES_DO_RETORNO)}.")
    faltam = [c for c in CHAVES_OBRIGATORIAS_DO_RETORNO if not campos.get(c)]
    if faltam:
        raise AP.ProblemaError(f"{nome}: falta no cabeçalho: {', '.join(faltam)}.")

    ambiente = campos["ambiente"].upper()
    prefixo, numero = achado.group(1), int(achado.group(2))
    if PREFIXOS.get(ambiente) != prefixo:
        raise AP.ProblemaError(
            f"{nome}: o ambiente «{campos['ambiente']}» não é o do nome do arquivo.")
    if not campos["id"].isdigit() or int(campos["id"]) != numero:
        raise AP.ProblemaError(
            f"{nome}: o id «{campos['id']}» não é o do nome do arquivo.")
    _instante(campos["em"], nome)
    try:
        nota, estado, prova = AP.conferir_nota_dev(
            nota, campos["estado"], campos.get("prova", ""))
    except AP.ProblemaError as erro:
        raise AP.ProblemaError(f"{nome}: {erro}") from None
    reproducao = campos.get("reproducao", "").strip().upper()
    if reproducao and reproducao not in AP.REPRODUCOES:
        raise AP.ProblemaError(
            f"{nome}: não conheço a reprodução «{reproducao}». As que conheço: "
            + ", ".join(AP.REPRODUCOES) + ".")
    _sem_dado_de_pessoa("nota", nota, nome)
    _sem_dado_de_pessoa("prova", prova, nome)
    return {"ambiente": ambiente, "id": numero, "impressao": campos["impressao"],
            "estado": estado, "em": campos["em"], "prova": prova,
            "reproducao": reproducao, "nota": nota}


def texto_do_retorno(dados: dict) -> str:
    """O arquivo de retorno, no estilo do cabeçalho da exportação."""
    linhas = ["---",
              f"ambiente: {dados['ambiente']}",
              f"id: {int(dados['id'])}",
              f"impressao: {dados['impressao']}",
              f"estado: {dados['estado']}"]
    if dados.get("reproducao"):
        linhas.append(f"reproducao: {dados['reproducao']}")
    linhas.append(f"em: {dados['em']}")
    if dados.get("prova"):
        linhas.append(f"prova: {dados['prova']}")
    linhas += ["---", str(dados["nota"]).strip(), ""]
    return "\n".join(linhas)


def _arquivo_md(arquivo: str) -> str:
    nome = str(arquivo or "").strip()
    return nome if nome.endswith(".md") else f"{nome}.md"


def _impressao_exportada(raiz: Path, nome: str) -> str:
    """A `impressao` que a exportação escreveu em `problemas/<nome>`."""
    caminho = _dentro(raiz, raiz / PASTA_DOS_PROBLEMAS / nome)
    if not caminho.is_file():
        raise AP.ProblemaError(
            f"{nome}: não há «{PASTA_DOS_PROBLEMAS}/{nome}» — responda só a "
            "problema que a exportação trouxe.")
    campos, _ = _cabecalho(caminho.read_text(encoding="utf-8"), nome)
    return campos.get("impressao", "")


def responder(pasta: Any, arquivo: str, *, estado: str, nota: str,
              prova: str = "", reproducao: str = "", agora: str) -> Path:
    """Escreve `retorno/<arquivo>.md`. ESCREVE EM DISCO; NÃO ABRE BANCO.

    `ambiente`, `id` e `impressao` vêm do arquivo do problema: quem responde
    não copia hash à mão. O texto passa por `ler_retorno` antes de sair — o
    que se escreve aqui é exatamente o que a importação aceita.
    """
    raiz = Path(pasta).resolve()
    nome = _arquivo_md(arquivo)
    achado = _NOME_DO_ARQUIVO.match(nome)
    if not achado:
        raise AP.ProblemaError(
            f"{nome}: o nome do arquivo não segue o padrão «of-0035.md» / "
            "«sb-0012.md».")
    ambiente = next(a for a, p in PREFIXOS.items() if p == achado.group(1))
    texto = texto_do_retorno({
        "ambiente": ambiente, "id": int(achado.group(2)),
        "impressao": _impressao_exportada(raiz, nome),
        "estado": str(estado or "").strip().upper(),
        "reproducao": str(reproducao or "").strip().upper(),
        "em": agora, "prova": str(prova or "").strip(), "nota": nota})
    ler_retorno(texto, nome)
    destino = _dentro(raiz, raiz / PASTA_DO_RETORNO / nome)
    _gravar_se_mudou(destino, texto, dry_run=False)
    return destino


def _arquivos_do_retorno(raiz: Path) -> list[Path]:
    pasta = raiz / PASTA_DO_RETORNO
    return sorted(pasta.glob("*.md")) if pasta.is_dir() else []


def _ler_arquivo_do_retorno(raiz: Path, caminho: Path) -> dict:
    """Recusa o que não é arquivo comum da pasta antes de lê-lo."""
    if caminho.is_symlink():
        raise AP.ProblemaError(f"{caminho.name}: link simbólico não se importa.")
    _dentro(raiz, caminho)
    if caminho.stat().st_size > LIMITE_DO_RETORNO:
        raise AP.ProblemaError(
            f"{caminho.name}: o arquivo passa de {LIMITE_DO_RETORNO // 1024} KB — "
            "retorno é nota, e não despejo.")
    try:
        texto = caminho.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        # UM ARQUIVO SALVO NOUTRA CODIFICAÇÃO NÃO DERRUBA A CONFERÊNCIA: ele
        # volta como recusado, e os outros seguem (revisão do #61).
        raise AP.ProblemaError(
            f"{caminho.name}: o arquivo não está em UTF-8 — salve-o de novo em "
            "UTF-8.") from None
    return ler_retorno(texto, caminho.name)


def conferir_retorno(pasta: Any) -> dict:
    """Confere todos os arquivos de `retorno/`. Só LÊ; NÃO ABRE BANCO.

    Cada um tem de passar por `ler_retorno` e ter o arquivo do problema com a
    mesma `impressao`.
    """
    raiz = Path(pasta).resolve()
    bons: list[str] = []
    recusados: list[dict] = []
    for caminho in _arquivos_do_retorno(raiz):
        try:
            r = _ler_arquivo_do_retorno(raiz, caminho)
            if _impressao_exportada(raiz, caminho.name) != r["impressao"]:
                raise AP.ProblemaError(
                    f"{caminho.name}: a impressão não é a do problema exportado.")
            bons.append(caminho.name)
        except AP.ProblemaError as erro:
            recusados.append({"arquivo": caminho.name, "porque": str(erro)})
    return {"bons": bons, "recusados": recusados}


def _decidir(r: dict, linha: dict, nome: str) -> str:
    """«Quem é mais novo vence»: `gravar`, `iguais` ou `mais_antigos`."""
    if not linha.get("nota_dev_em"):
        return "gravar"
    no_arquivo = _instante(r["em"], nome)
    no_banco = _instante(linha["nota_dev_em"], nome)
    if no_arquivo > no_banco:
        return "gravar"
    if no_arquivo < no_banco:
        return "mais_antigos"
    mesmo = ((linha.get("nota_dev") or "").strip() == r["nota"]
             and (linha.get("nota_dev_estado") or "") == r["estado"]
             and (linha.get("nota_dev_prova") or "").strip() == r["prova"])
    if not mesmo:
        raise AP.ProblemaError(
            f"{nome}: o arquivo mudou sem mudar o «em» — mude o «em» para dizer "
            "que esta é a resposta nova.")
    return "iguais"


def _importar_um(db, raiz: Path, caminho: Path, *, agora: str,
                 dry_run: bool) -> dict:
    """Um arquivo, uma transação. Devolve o que aconteceu com ele."""
    r = _ler_arquivo_do_retorno(raiz, caminho)
    nome = caminho.name
    # O `em` DO FUTURO VENCERIA TODA NOTA DA TELA, e para sempre: «quem é mais
    # novo vence» compara o `em`, e um relógio errado (ou um ano digitado
    # errado) passaria na frente de tudo o que o oficial escrever depois. Um dia
    # de folga cobre fuso e relógio torto (revisão do #61).
    if _instante(r["em"], nome) > _instante(agora, nome) + timedelta(
            days=DIAS_DE_FOLGA_DO_EM):
        raise AP.ProblemaError(
            f"{nome}: o «em» {r['em']} está mais de {DIAS_DE_FOLGA_DO_EM} dia à "
            f"frente de agora ({agora}). Confira o relógio de quem respondeu e "
            "corrija o «em».")
    contexto = db.connect() if dry_run else db.transaction()
    with contexto as con:
        linha = AP.ler(con, r["id"])
        if not linha:
            raise AP.ProblemaError(f"{nome}: não achei o problema #{r['id']}.")
        if (linha.get("impressao") or "") != r["impressao"]:
            raise AP.ProblemaError(
                f"{nome}: a impressão não é a do problema #{r['id']} deste banco "
                "— o número pode ser de outro banco.")
        decisao = _decidir(r, dict(linha), nome)
        if decisao != "gravar":
            return {"decisao": decisao}
        reproducao = None
        muda_reproducao = (r["reproducao"]
                           and r["reproducao"] != AP.reproducao_de(linha))
        if not dry_run:
            AP.anotar_desenvolvimento(con, r["id"], nota=r["nota"],
                                      estado=r["estado"], prova=r["prova"],
                                      agora=r["em"], por=POR_DA_SINCRONIA)
            if muda_reproducao:
                reproducao = AP.classificar_reproducao(
                    con, r["id"], r["reproducao"], agora=r["em"],
                    por=POR_DA_SINCRONIA)
    return {"decisao": "gravar", "id": r["id"], "estado": r["estado"],
            "em": r["em"], "reproducao": reproducao}


def importar(db, pasta: Any, *, agora: str, ambiente: str | None = None,
             dry_run: bool = False) -> dict:
    """Grava as notas de `retorno/` deste ambiente. ESCREVE NO BANCO.

    **CADA ARQUIVO É TRATADO SOZINHO** (a regra de `importar_notas`): o que
    der certo entra, o recusado volta com o motivo. **QUEM É MAIS NOVO
    VENCE**: a nota grava com o `em` do arquivo, e por isso a segunda
    importação dá «iguais»; a nota que a tela escreveu depois fica.

    Não mexe na `situacao` e não apaga nem move nada da pasta. `agora` é a
    hora da importação, para o resumo; quem data a nota é o `em`.
    """
    raiz = Path(pasta).resolve()
    if ambiente is None:
        with db.connect() as con:
            ambiente = AP.ambiente_abertura_padrao(con)
    prefixo = PREFIXOS[str(ambiente).strip().upper()]
    feito: dict[str, Any] = {"gravados": [], "iguais": 0, "mais_antigos": [],
                             "outro_ambiente": 0, "recusados": [],
                             "importado_em": agora}
    for caminho in _arquivos_do_retorno(raiz):
        if not caminho.name.startswith(f"{prefixo}-"):
            feito["outro_ambiente"] += 1
            continue
        try:
            r = _importar_um(db, raiz, caminho, agora=agora, dry_run=dry_run)
        except AP.ProblemaError as erro:
            feito["recusados"].append({"arquivo": caminho.name, "porque": str(erro)})
            continue
        except Exception as erro:                              # noqa: BLE001
            feito["recusados"].append({"arquivo": caminho.name,
                                       "porque": f"não consegui gravar: {erro}"})
            continue
        if r["decisao"] == "iguais":
            feito["iguais"] += 1
        elif r["decisao"] == "mais_antigos":
            feito["mais_antigos"].append(caminho.name)
        else:
            feito["gravados"].append(caminho.name)
            if not dry_run:
                _auditar_importado(db, caminho.name, r)
    return feito


def _auditar_importado(db, nome: str, r: dict) -> None:
    """A auditoria, FORA da transação (como o `audit` das rotas). O texto da
    nota não vai: ele está no problema, e a auditoria aponta para ele."""
    db.log(None, ASSINATURA, "AJUDA_PROBLEMA_NOTA_DEV_SINCRONIA", "aj_problemas",
           r["id"], {"estado": r["estado"], "em": r["em"], "arquivo": nome},
           agente=ASSINATURA, a_mando_de=POR_DA_SINCRONIA)
    if r.get("reproducao"):
        db.log(None, ASSINATURA, "AJUDA_PROBLEMA_REPRODUCAO", "aj_problemas",
               r["id"], {"reproducao": r["reproducao"]["reproducao"],
                         "antes": r["reproducao"]["antes"], "arquivo": nome},
               agente=ASSINATURA, a_mando_de=POR_DA_SINCRONIA)


# ------------------------------------------------------------ a operação
#
# FASE 3, 27/10/2026: o ciclo roda sozinho na serventia, a cada 2 horas, como
# SYSTEM:
#
#     git pull → importar (o retorno) → exportar (os problemas) → commit/push
#                                                    (só problemas/ e INDICE.md)
#
# **IMPORTAR ANTES DE EXPORTAR**: o estado que acabou de voltar já sai na
# exportação do mesmo ciclo. Cada lado só escreve na sua pasta (a serventia em
# `problemas/` e `INDICE.md`, o desenvolvimento em `retorno/`), e por isso o
# `pull --rebase` não tem conflito.
#
# No molde de `automacao_agendador`: **este código GERA o lançador e o registro
# da tarefa e não executa nenhum** — quem registra é o oficial, como
# administrador. Nenhum caminho desta máquina entra aqui: tudo vem do ambiente
# de quem gera ou da linha de comando.

TAREFA_DA_SINCRONIA = "CartorioGestao-Sincronia-Problemas"
AUTOR_DA_SINCRONIA = ("Serventia (sincronia)", "sincronia@cartorio-gestao.invalid")
LANCADOR_DA_SINCRONIA = "sincronia_problemas.cmd"
REGISTRO_DA_SINCRONIA = "registrar_sincronia.ps1"
#: O ciclo só fala SSH com o GitHub, e com a chave da sincronia.
ORIGEM_DA_SINCRONIA = "git@github.com:"


def _variaveis_da_sincronia() -> tuple[str, ...]:
    """As do servidor que importam aqui — tiradas da lista da automação, e não
    copiadas — mais o `PGPASSFILE`, onde mora a senha do banco."""
    import automacao_agendador as AG
    usadas = ("CARTORIO_GESTAO_DATA", "CG_PG_DSN", "CG_PG_SCHEMA")
    return tuple(v for v in AG.VARIAVEIS if v in usadas) + ("PGPASSFILE",)


_SENHA_NO_DSN = re.compile(r"(?i)\bpassword\s*=|://[^/@:\s]+:[^/@\s]*@")


def ambiente_da_sincronia(environ: dict | None = None) -> dict[str, str]:
    """O ambiente que o lançador repete, lido de quem gera. Recusa sem o banco
    dito e com senha no DSN: a senha vai no `pgpass`
    (`docs/SEGURANCA_REDE.md`, item 3), nunca num arquivo `.cmd`."""
    environ = os.environ if environ is None else environ
    ambiente = {v: str(environ.get(v) or "").strip() for v in _variaveis_da_sincronia()}
    faltam = [v for v in ("CG_PG_DSN", "CG_PG_SCHEMA") if not ambiente.get(v)]
    if faltam:
        raise _Recusa(
            "Falta no ambiente: " + " e ".join(faltam) + ". Gere no console com "
            "o ambiente do servidor: o lançador repete o banco dele.")
    if _SENHA_NO_DSN.search(ambiente["CG_PG_DSN"]):
        raise _Recusa(
            "O CG_PG_DSN tem senha. A senha vai no pgpass (PGPASSFILE), e não "
            "no DSN — veja docs/SEGURANCA_REDE.md, item 3. Nada foi gravado.")
    if not ambiente["CARTORIO_GESTAO_DATA"]:
        import automacao_cofre as COFRE
        ambiente["CARTORIO_GESTAO_DATA"] = str(COFRE.pasta_de_dados())
    return {k: v for k, v in ambiente.items() if v}


def _no_cmd(valor: Any) -> str:
    """O valor dentro de `set "X=..."`: o `%` dobrado, para o cmd não expandir."""
    return str(valor).replace("%", "%%")


def _barra(caminho: Any) -> str:
    """Caminho com `/`: o `ssh` e o `safe.directory` do Git entendem, e o shell
    do Git não come a barra invertida."""
    return str(caminho).replace("\\", "/")


def _passo(nome: str, comando: str, *, segue_com: tuple[str, ...] = ("0",)) -> list[str]:
    """Um passo do lançador: roda, anota o código no log e PARA se o código não
    for um dos aceitos."""
    linhas = [f'set "PASSO={nome}"', f'call :registrar "{nome}: inicio"',
              f'{comando} >>"%LOG%" 2>&1', 'set "CODIGO=%errorlevel%"',
              f'call :registrar "{nome}: codigo %CODIGO%"']
    teste = " ".join(f'if not "%CODIGO%"=="{c}"' for c in segue_com)
    return linhas + [f"{teste} goto :parar"]


def arquivos_do_agendamento(repositorio: Any, destino: Any, *, raiz: Any, python: Any,
                            ambiente: dict[str, str]) -> dict[str, str]:
    """O texto do lançador e do registro da tarefa. Não grava nem executa.

    A tarefa aponta para o lançador **onde ele vai ser gravado** (`destino`),
    com o caminho inteiro: a lição do #66, em que as tarefas da automação
    apontavam para uma pasta onde o lançador não estava."""
    repo = Path(repositorio)
    dados = Path(ambiente["CARTORIO_GESTAO_DATA"])
    sincronia = dados / "sincronia"
    logs = dados / "logs"
    ferramenta = Path(raiz) / "tools" / "problemas_sincronia.py"
    nome, email = AUTOR_DA_SINCRONIA
    ssh = (f'ssh -i "{_barra(sincronia / "chave_da_sincronia")}" -o IdentitiesOnly=yes '
           f'-o StrictHostKeyChecking=yes '
           f'-o UserKnownHostsFile="{_barra(sincronia / "known_hosts")}"')
    git = (f'git -C "{repo}" -c safe.directory="{_barra(repo)}" '
           f'-c user.name="{nome}" -c user.email={email}')
    py = f'"{python}" "{ferramenta}"'
    linhas = [
        "@echo off",
        "rem A sincronia dos problemas, a cada 2 horas, como SYSTEM (gerado por",
        "rem tools/problemas_sincronia.py gerar-agendamento; nao executado por ele).",
        "rem pull -> importar -> exportar -> commit/push, so de problemas/ e INDICE.md.",
        "setlocal",
        *[f'set "{k}={_no_cmd(v)}"' for k, v in ambiente.items()],
        f'set "GIT_SSH_COMMAND={_no_cmd(ssh)}"',
        f'set "LOG={_no_cmd(logs / "sincronia_problemas.log")}"',
        f'set "ORIGEM_LIDA={_no_cmd(logs / "sincronia_problemas.origem")}"',
        f'if not exist "{logs}" mkdir "{logs}"',
        f'cd /d "{raiz}"',
        'set "PASSO=inicio"',
        'set "CODIGO=0"',
        'call :registrar "ciclo: inicio"',
        "where git >nul 2>&1",
        "if errorlevel 1 (",
        '  call :registrar "ERRO: o git nao esta instalado (Git for Windows); veja docs/SINCRONIA_DOS_PROBLEMAS.md"',
        "  exit /b 9",
        ")",
        # A ORIGEM TEM DE SER O ENDEREÇO SSH: com HTTPS, o git pediria senha ou
        # usaria credencial de pessoa, e a chave da sincronia não valeria.
        'set "PASSO=origem"',
        'set "ORIGEM="',
        f'{git} remote get-url origin >"%ORIGEM_LIDA%" 2>>"%LOG%"',
        'set /p ORIGEM=<"%ORIGEM_LIDA%"',
        'del "%ORIGEM_LIDA%" >nul 2>&1',
        f'if not "%ORIGEM:~0,{len(ORIGEM_DA_SINCRONIA)}%"=="{ORIGEM_DA_SINCRONIA}" (',
        f'  call :registrar "ERRO: a origem do repositorio nao comeca por {ORIGEM_DA_SINCRONIA} (lida: %ORIGEM%)"',
        "  exit /b 8",
        ")",
        # `--autostash`: um ciclo que caiu no meio não trava os seguintes.
        *_passo("pull", f"{git} pull --rebase --autostash --quiet"),
        # Recusados no retorno (código 1) ficam no log e o ciclo segue.
        *_passo("importar", f'{py} importar --pasta "{repo}"', segue_com=("0", "1")),
        'if "%CODIGO%"=="1" call :registrar "importar: houve RECUSADO, veja acima; o ciclo segue"',
        *_passo("exportar", f'{py} exportar --pasta "{repo}"'),
        f'if not exist "{repo / PASTA_DOS_PROBLEMAS}" mkdir "{repo / PASTA_DOS_PROBLEMAS}"',
        # SÓ ESSES DOIS: `retorno/` é do desenvolvimento.
        *_passo("add", f"{git} add -- {PASTA_DOS_PROBLEMAS} {ARQUIVO_DO_INDICE}"),
        f"{git} diff --cached --quiet",
        'set "CODIGO=%errorlevel%"',
        'if "%CODIGO%"=="0" (',
        '  call :registrar "ciclo: nada a enviar; codigo 0"',
        "  exit /b 0",
        ")",
        'set "PASSO=diff"',
        'if not "%CODIGO%"=="1" goto :parar',
        *_passo("commit", f'{git} commit --quiet -m "Sincronia: problemas da serventia"'),
        *_passo("push", f"{git} push --quiet"),
        'call :registrar "ciclo: fim; codigo 0"',
        "exit /b 0",
        "",
        ":parar",
        'call :registrar "CICLO PARADO no passo %PASSO% (codigo %CODIGO%)"',
        "exit /b %CODIGO%",
        "",
        ":registrar",
        '>>"%LOG%" echo [%date% %time%] %~1',
        "exit /b 0",
        "",
    ]
    import permissao_local as PL
    ps1 = f"""<#
  Registra a tarefa da sincronia dos problemas no Agendador do Windows (gerado
  por tools/problemas_sincronia.py gerar-agendamento; nao executado por ele).
  Rode como administrador.
    - cria {sincronia} com a ACL dos segredos (SYSTEM e Administradores);
    - {TAREFA_DA_SINCRONIA}: como SYSTEM, a cada 2 horas das 7h as 20h.
  NAO gera a chave da sincronia e NAO fala com o GitHub: isso e a parte B do
  docs/SINCRONIA_DOS_PROBLEMAS.md.
#>
$ErrorActionPreference = 'Stop'
$pasta = "{sincronia}"
$lancador = "{Path(destino) / LANCADOR_DA_SINCRONIA}"
if (-not (Test-Path -LiteralPath $lancador)) {{ throw "o lancador nao esta em $lancador; gere de novo" }}
New-Item -ItemType Directory -Force -Path $pasta | Out-Null
# A ACL dos segredos: SYSTEM e Administradores; ninguem mais.
& icacls.exe $pasta /inheritance:r /grant:r "{PL.SID_DO_SERVICO}:(OI)(CI)F" "{PL.SID_DOS_ADMINISTRADORES}:(OI)(CI)F" | Out-Null
if ($LASTEXITCODE -ne 0) {{ throw "o icacls recusou a pasta $pasta" }}
$quem = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
# Todo dia as 7h, repetindo a cada 2 horas por 13 horas: 7h, 9h, ..., 19h.
$quando = New-ScheduledTaskTrigger -Daily -At '07:00'
$quando.Repetition = (New-ScheduledTaskTrigger -Once -At '07:00' -RepetitionInterval (New-TimeSpan -Hours 2) -RepetitionDuration (New-TimeSpan -Hours 13)).Repetition
# PRIORIDADE 7 (abaixo do normal) de proposito: o servidor do balcao nasce com 3.
$t = New-ScheduledTask -Principal $quem `
  -Action (New-ScheduledTaskAction -Execute "$env:SystemRoot\\System32\\cmd.exe" -Argument "/d /c `"$lancador`"") `
  -Trigger $quando `
  -Settings (New-ScheduledTaskSettingsSet -Priority 7 -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 15) -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries)
Register-ScheduledTask -TaskName '{TAREFA_DA_SINCRONIA}' -InputObject $t -Force | Out-Null
Write-Host 'Tarefa registrada: {TAREFA_DA_SINCRONIA} (SYSTEM, a cada 2 horas das 7h as 20h).'
Write-Host "O log fica em {logs / "sincronia_problemas.log"}."
"""
    return {LANCADOR_DA_SINCRONIA: "\r\n".join(linhas),
            REGISTRO_DA_SINCRONIA: ps1.replace("\n", "\r\n")}


def gerar_agendamento(repositorio: Any, destino: Any, *, raiz: Any, python: Any,
                      environ: dict | None = None) -> list[Path]:
    """Confere o ambiente e SÓ DEPOIS grava em `destino`: uma recusa não deixa
    pasta nem arquivo. Não abre banco e não executa nada do que grava."""
    ambiente = ambiente_da_sincronia(environ)
    arquivos = arquivos_do_agendamento(repositorio, destino, raiz=raiz,
                                       python=python, ambiente=ambiente)
    pasta = Path(destino)
    pasta.mkdir(parents=True, exist_ok=True)
    escritos = []
    for nome, texto in arquivos.items():
        alvo = pasta / nome
        alvo.write_text(texto, encoding="utf-8", newline="")
        escritos.append(alvo)
    return escritos


# ----------------------------------------------------------- linha de comando


class _Recusa(Exception):
    """A linha de comando recusou antes de tocar no banco."""


def _banco_conferido():
    """O `Database` da produção, só depois de conferir que ele existe.

    **A CONFERÊNCIA VEM ANTES DO `Database(...)`**, porque o construtor cria o
    schema quando ele não existe. Um `CG_PG_SCHEMA` digitado errado viraria um
    schema vazio na produção — e a exportação diria «nenhum problema» calada,
    que é a pior resposta que ela pode dar (pedido do oficial, 27/10/2026).
    `banco_pg.schema_existe` só procura; não cria nada.
    """
    import banco_pg
    faltam = [v for v in ("CG_PG_DSN", "CG_PG_SCHEMA")
              if not (os.environ.get(v) or "").strip()]
    if faltam:
        raise _Recusa(
            "Falta no ambiente: " + " e ".join(faltam) + ". Esta ferramenta só "
            "abre o banco da casa no PostgreSQL, e com o schema dito: sem ele, "
            "ela criaria um schema vazio e exportaria «nenhum problema».")
    from app import get_data_dir  # tarde, para não importar o Flask à toa
    from database import Database
    db_path = Path(get_data_dir()) / "cartorio_gestao.sqlite3"
    try:
        existe = banco_pg.schema_existe(db_path)
    except Exception as erro:  # noqa: BLE001 — a recusa diz o porquê
        raise _Recusa(f"Não consegui falar com o PostgreSQL: {erro}") from erro
    if not existe:
        raise _Recusa(
            f"O schema «{banco_pg.schema_do_caminho(db_path)}» não existe neste "
            "PostgreSQL. Confira o CG_PG_SCHEMA: esta ferramenta não cria banco.")
    return Database(db_path)


def _agora() -> str:
    return datetime.now().isoformat(timespec="seconds")  # noqa: DTZ005


def _cmd_exportar(db, args) -> int:
    r = exportar(db, args.pasta, agora=_agora(), dry_run=args.dry_run)
    verbo = "escreveria" if args.dry_run else "escritos"
    print(f"ambiente: {r['ambiente']}")
    print(f"{verbo}: {len(r['escritos'])}")
    for nome in r["escritos"]:
        print(f"   {nome}")
    print(f"iguais (não regravados): {r['iguais']}")
    for rec in r["recusados"]:
        print(f"RECUSADO #{rec['id']}: {rec['porque']}", file=sys.stderr)
    if args.dry_run:
        print("SÓ MOSTREI — nada foi escrito.")
    return 0


def _cmd_classificar(db, args) -> int:
    agora = _agora()
    try:
        with db.transaction() as con:
            r = AP.classificar_reproducao(con, args.id, args.valor,
                                          agora=agora, por=args.por)
    except AP.ProblemaError as erro:
        print(f"RECUSA: {erro}", file=sys.stderr)
        return 1
    # A AUDITORIA É ASSINADA PELO NOME DA FERRAMENTA, e o `--por` vai como
    # mandante: assinar com o login de quem não clicou em nada seria o carimbo
    # que mente (a mesma regra de `tools/marcar_problema_atendido.py`).
    db.log(None, ASSINATURA, "AJUDA_PROBLEMA_REPRODUCAO", "aj_problemas",
           r["id"], {"reproducao": r["reproducao"], "antes": r["antes"],
                     "por": args.por},
           agente=ASSINATURA, a_mando_de=args.por)
    print(f"#{r['id']}: {r['antes']} -> {r['reproducao']} "
          f"({r['nome_da_reproducao']})")
    return 0


def _cmd_responder(args) -> int:
    nota = args.nota
    if args.nota_arquivo:
        nota = Path(args.nota_arquivo).read_text(encoding="utf-8")
    try:
        destino = responder(args.pasta, args.arquivo, estado=args.estado,
                            nota=nota, prova=args.prova,
                            reproducao=args.reproducao, agora=_agora())
    except AP.ProblemaError as erro:
        print(f"RECUSA: {erro}", file=sys.stderr)
        return 1
    print(f"retorno escrito: {destino}")
    return 0


def _cmd_conferir_retorno(args) -> int:
    r = conferir_retorno(args.pasta)
    print(f"bons: {len(r['bons'])}")
    for rec in r["recusados"]:
        print(f"RECUSADO {rec['arquivo']}: {rec['porque']}", file=sys.stderr)
    return 1 if r["recusados"] else 0


def _cmd_importar(db, args) -> int:
    r = importar(db, args.pasta, agora=_agora(), dry_run=args.dry_run)
    verbo = "gravaria" if args.dry_run else "gravados"
    print(f"{verbo}: {len(r['gravados'])}")
    for nome in r["gravados"]:
        print(f"   {nome}")
    print(f"iguais: {r['iguais']}")
    print(f"mais antigos que a nota do banco (não gravados): "
          f"{len(r['mais_antigos'])}")
    print(f"de outro ambiente (ignorados): {r['outro_ambiente']}")
    for rec in r["recusados"]:
        print(f"RECUSADO {rec['arquivo']}: {rec['porque']}", file=sys.stderr)
    if args.dry_run:
        print("SÓ MOSTREI — nada foi gravado.")
    return 1 if r["recusados"] else 0


def _cmd_gerar_agendamento(args) -> int:
    raiz = Path(__file__).resolve().parent
    try:
        escritos = gerar_agendamento(args.repositorio, args.destino, raiz=raiz,
                                     python=sys.executable)
    except _Recusa as erro:
        print(f"RECUSA: {erro}", file=sys.stderr)
        return 2
    for alvo in escritos:
        print(f"gerado: {alvo}")
    if not (os.environ.get("PGPASSFILE") or "").strip():
        print("AVISO: falta o PGPASSFILE no ambiente; a tarefa roda como SYSTEM "
              "e não acharia a senha do banco. Repita o set do "
              "iniciar_servidor_servico.cmd e gere de novo.")
    print("Nada foi registrado nem executado. Próximos passos (parte B, em "
          "docs/SINCRONIA_DOS_PROBLEMAS.md):\n"
          "  1. a chave da sincronia e o known_hosts conferido, na pasta sincronia;\n"
          "  2. a chave pública como chave de implantação, com escrita, só no "
          "repositório privado;\n"
          f"  3. como administrador: {REGISTRO_DA_SINCRONIA};\n"
          "  4. a primeira exportação conferida a olho e o primeiro push à mão.")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools/problemas_sincronia.py",
        description="Exporta os problemas, mascarados, para o repositório "
                    "privado; classifica onde cada um se reproduz; gera o "
                    "agendamento da sincronia.")
    sub = ap.add_subparsers(dest="comando", required=True)
    exp = sub.add_parser("exportar", help="um arquivo por problema, mascarado")
    exp.add_argument("--pasta", required=True,
                     help="a pasta do repositório privado")
    exp.add_argument("--dry-run", action="store_true",
                     help="mostra o que escreveria e não escreve")
    cla = sub.add_parser("classificar", help="onde o problema se reproduz")
    cla.add_argument("--id", type=int, required=True)
    # SEM `choices`: quem recusa valor fora do vocabulário é o domínio
    # (`classificar_reproducao`), com a frase pronta — a regra mora lá.
    cla.add_argument("--valor", required=True,
                     help="um de: " + ", ".join(AP.REPRODUCOES))
    cla.add_argument("--por", required=True,
                     help="o login de quem mandou classificar")
    res = sub.add_parser("responder",
                         help="escreve retorno/<arquivo>.md (sem banco)")
    res.add_argument("--pasta", required=True)
    res.add_argument("--arquivo", required=True, help="por exemplo, of-0035")
    res.add_argument("--estado", required=True,
                     help="um de: " + ", ".join(AP.ESTADOS_DO_DEV))
    texto_da_nota = res.add_mutually_exclusive_group(required=True)
    texto_da_nota.add_argument("--nota")
    texto_da_nota.add_argument("--nota-arquivo",
                               help="arquivo com a nota, para várias linhas")
    res.add_argument("--prova", default="")
    res.add_argument("--reproducao", default="",
                     help="um de: " + ", ".join(AP.REPRODUCOES))
    con_r = sub.add_parser("conferir-retorno",
                           help="confere os arquivos de retorno/ (sem banco)")
    con_r.add_argument("--pasta", required=True)
    imp = sub.add_parser("importar",
                         help="grava as notas de retorno/ neste banco")
    imp.add_argument("--pasta", required=True)
    imp.add_argument("--dry-run", action="store_true",
                     help="mostra o que gravaria e não grava")
    ger = sub.add_parser("gerar-agendamento",
                         help="gera o lançador e o registro da tarefa (sem banco)")
    ger.add_argument("--repositorio", required=True,
                     help="a pasta do clone do repositório privado")
    ger.add_argument("--destino", required=True,
                     help="onde gravar os dois arquivos")
    args = ap.parse_args(argv)

    # O QUE É DO DESENVOLVIMENTO NÃO ABRE BANCO: responder e conferir rodam na
    # máquina de quem conserta, que não tem — nem deve ter — o da casa. O
    # gerar-agendamento também não: só escreve arquivos.
    if args.comando == "responder":
        return _cmd_responder(args)
    if args.comando == "conferir-retorno":
        return _cmd_conferir_retorno(args)
    if args.comando == "gerar-agendamento":
        return _cmd_gerar_agendamento(args)

    try:
        db = _banco_conferido()
    except _Recusa as erro:
        print(f"RECUSA: {erro}", file=sys.stderr)
        return 2
    if args.comando == "exportar":
        return _cmd_exportar(db, args)
    if args.comando == "importar":
        return _cmd_importar(db, args)
    return _cmd_classificar(db, args)
