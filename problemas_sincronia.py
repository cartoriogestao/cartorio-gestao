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
  - grava na tabela, faz `git` ou abre conexão de rede. Commit e envio do
    repositório privado são da operação (fase 3), fora deste código.

A LINHA DE COMANDO MORA AQUI, EM `main`, E NÃO EM `tools/`. O varredor de
função sem tela (`tests/test_funcao_sem_tela.py`) só lê os módulos da raiz, e
`main` é raiz para ele: com a linha de comando em `tools/`, `exportar` e
`classificar_reproducao` pareceriam órfãs. `tools/problemas_sincronia.py` só
chama `main`.
"""
from __future__ import annotations

import argparse
import os
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
    args = ap.parse_args(argv)

    try:
        db = _banco_conferido()
    except _Recusa as erro:
        print(f"RECUSA: {erro}", file=sys.stderr)
        return 2
    if args.comando == "exportar":
        return _cmd_exportar(db, args)
    return _cmd_classificar(db, args)
