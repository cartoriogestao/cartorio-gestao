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
    máscara do relatório para conserto (`ajuda_problemas.montar_relatorio`);
  - exporta login ou nome de quem usou (`criado_por`, `ultimo_usuario`,
    `fechado_por`, `reaberto_por`, `nota_dev_por`);
  - escreve fora da pasta informada, ou apaga arquivo dela;
  - faz `git` ou abre conexão de rede. Commit e envio do repositório privado
    são da operação (fase 3), fora deste código;
  - fecha problema. A exportação só lê o banco; quem grava é `importar` (a
    nota do desenvolvimento, pela `anotar_desenvolvimento` da tela) e
    `classificar`, e nenhum dos dois mexe na `situacao`.

A VOLTA (fase 2) está na seção «o retorno», mais abaixo.

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


def texto_do_arquivo(problema: dict, ambiente: str, mapa: dict | None) -> str:
    """O arquivo de um problema, já mascarado. Só calcula.

    O CABEÇALHO É UMA INFORMAÇÃO POR LINHA, para programa e gente lerem sem
    traduzir; depois vem o mesmo bloco do relatório para conserto
    (`_bloco_do_problema`), que é o mesmo texto da tela.

    **O TEXTO INTEIRO PASSA PELA MÁSCARA**, e não só o `detalhe`: o título de
    um RELATADO é escrito por gente, e gente escreve nome. Se sobrar dado
    depois de mascarar, `PRIV.PrivacidadeError` sobe — e quem chama recusa
    este problema, em vez de deixá-lo sair.
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
    return PRIV.sanitizar_texto(
        "\n".join(cabecalho + AP._bloco_do_problema(p, mapa)))


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
    linha mais importante da lista —, depois o que mais se repete."""
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
        titulo = str(p.get("titulo") or "").replace("|", "/").replace("\n", " ")
        situacao = str(p.get("situacao") or "")
        if _voltou(p):
            situacao += " (voltou depois de relatado)"
        retorno = AP.ROTULO_CURTO_DEV.get(p.get("nota_dev_estado") or "", "—")
        partes.append(
            f"| [{x['arquivo']}]({PASTA_DOS_PROBLEMAS}/{x['arquivo']}) "
            f"| {titulo} | {situacao} "
            f"| {AP.REPRODUCOES[AP.reproducao_de(p)]} | {retorno} |")
    if not ordem:
        partes.append("| — | Nenhum problema nesta exportação | — | — | — |")
    return PRIV.sanitizar_texto("\n".join(partes) + "\n")


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
        except PRIV.PrivacidadeError as erro:
            recusados.append({"id": int(p["id"]), "porque": str(erro)})
            continue
        destino = _dentro(raiz, raiz / PASTA_DOS_PROBLEMAS / arquivo)
        if _gravar_se_mudou(destino, texto, dry_run=dry_run):
            escritos.append(f"{PASTA_DOS_PROBLEMAS}/{arquivo}")
        else:
            iguais += 1
        no_indice.append({"arquivo": arquivo, "p": p})

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


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        prog="tools/problemas_sincronia.py",
        description="Exporta os problemas, mascarados, para o repositório "
                    "privado; classifica onde cada um se reproduz.")
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
    args = ap.parse_args(argv)

    # O QUE É DO DESENVOLVIMENTO NÃO ABRE BANCO: responder e conferir rodam na
    # máquina de quem conserta, que não tem — nem deve ter — o da casa.
    if args.comando == "responder":
        return _cmd_responder(args)
    if args.comando == "conferir-retorno":
        return _cmd_conferir_retorno(args)

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
