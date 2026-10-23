"""Monta a árvore PÚBLICA do Cartório Gestão — por lista do que ENTRA.

POR QUE LISTA DO QUE ENTRA, E NÃO SÓ O .gitignore
    Medido em 09/10/2026 no SANDBOX: o `.gitignore` sozinho deixaria entrar
    2.203 arquivos (36 MB), entre eles 240 recortes de matrículas digitalizadas
    (`_crops_matricula/`), 138 módulos da raiz que nada importa (rascunhos de
    conserto, sondas e scripts com nome de pessoa real) e testes com CPF de
    gente de verdade. Um `.gitignore` é uma lista do que SAI: todo rascunho
    novo entra por padrão. Aqui é o contrário — entra o que o sistema usa, e o
    resto fica de fora sem precisar ser lembrado.

O QUE ENTRA
    - módulos `.py` da raiz ALCANÇADOS a partir de `app.py` pelos imports
      (lidos com `ast`), mais os que `tools/`, `tests/`, `installer/` e `ci/`
      importam;
    - as pastas de código em `PASTAS`, menos os rascunhos de `RASCUNHO_EM_TOOLS`;
    - os arquivos de projeto em `ARQUIVOS_DE_PROJETO`;
    - e, sobre tudo isso, o `.gitignore` continua valendo (via `git
      check-ignore`, com um índice temporário FORA da árvore — nada de `.git`
      dentro do SANDBOX).

O QUE NÃO ENTRA, DE PROPÓSITO
    `DOCUMENTACAO/`, `CLAUDE.md` e `AGENTS.md`: são o diário desta serventia,
    com nomes, CPFs, selos e matrículas reais (medido: 1.959 menções da casa só
    na documentação). Publicá-los é decisão do oficial, depois de sanitizados.

OS MOLDES SAEM SEM QUEM OS SALVOU — B4, 11/10/2026
    Um `.odt` guarda em `meta.xml` o nome de quem o criou e salvou, e em
    `settings.xml` a impressora daquela máquina (medido nos três moldes da
    certidão do RCPN: as duas coisas, e nada mais da casa). Na CÓPIA exportada
    elas saem; os moldes desta árvore não são tocados — o molde é do oficial,
    e ele o edita no LibreOffice. E o portão abre os `.odt`/`.docx` e varre o
    XML de dentro: um zip passava por ele sem ser lido.

O QUE ESTE PROGRAMA NÃO FAZ
    Não reescreve código (trocar «Cidade Exemplo» por outra coisa num `.py` muda
    comportamento — isso se faz na fonte, com teste), não cria repositório,
    não faz commit nem push. Publicar no GitHub é ato do oficial.

USO
    python tools/exportar_publico.py                 # só MEDE e lista
    python tools/exportar_publico.py --gerar DESTINO # copia e varre o destino
Sai com código 1 se o varredor `ci/anti_vazamento` achar vazamento no que
entraria — é o portão: enquanto não for zero, não se publica.
"""
from __future__ import annotations

import argparse
import ast
import collections
import fnmatch
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent

SEMENTES_DO_APP = ("app",)
PASTAS = ("templates", "static", "tests", "tools", "installer", "modelos",
          "modelos_papeis", "schemas", "ci", ".github", "docs",
          # O TEXTO DE FÁBRICA DOS PAPÉIS (LF06A, 19/10/2026): saiu do código
          # para esta pasta, e sem ela a instalação nova não tem padrão nenhum.
          "modelos_padrao",
          # A EXTENSÃO DO NAVEGADOR DO CCN (15/10/2026): sem ela o envio ao
          # CCN e a consulta não funcionam em outra serventia. Entra só a
          # extensão; o README e o contrato ficam (ver FORA_POR_DECISAO).
          "ccn_assistente")
ARQUIVOS_DE_PROJETO = ("README.md", "requirements.txt", "requirements-build.txt",
                       "requirements-test.txt",
                       "VERSAO.txt", ".gitignore", ".gitleaks.toml",
                       # a pasta dos padrões vai byte a byte (LF06A)
                       ".gitattributes",
                       ".env.example", "LICENSE", "LICENSE.md", "pyproject.toml",
                       # OS PONTOS DE ENTRADA DA INSTALAÇÃO (B5, 11/10/2026): o
                       # `installer/INSTALAR_SERVIDOR.cmd` chama o da raiz, e a
                       # raiz ficava de fora como «arquivo solto» — o público
                       # sairia com um instalador que não instala.
                       "INSTALAR_SERVIDOR.cmd", "INSTALAR_CLIENTE.cmd",
                       "REPARAR_REDE.cmd", "DIAGNOSTICAR_INSTALACAO.cmd",
                       "RODAR_SUITE_RAPIDA.cmd", "RODAR_SUITE_COMPLETA.cmd",
                       # O SANDBOX DE DEMONSTRAÇÃO (15/10/2026): um clique liga
                       # uma instalação fictícia e isolada para quem baixou.
                       "INICIAR_SANDBOX.cmd",
                       # OS ARQUIVOS DE DADOS QUE O CÓDIGO LÊ (23/10/2026): a
                       # v3.7.1 saiu sem eles e o sistema público não subia —
                       # `ri_doi` lê o layout da DOI ao ser importado, e as
                       # funções do PostgreSQL moram num `.sql`. Ficavam de fora
                       # como «arquivo solto». `dados_que_o_codigo_le` agora
                       # recusa a publicação quando faltar outro.
                       "pytest.ini", "banco_pg_funcoes.sql", "ri_doi_layout.json",
                       "censec_ctp_esquema.json", "patches_natureza_averbacao.json")
# A FICAR DE FORA ATÉ O OFICIAL DECIDIR (ver docstring).
FORA_POR_DECISAO = ("DOCUMENTACAO/*", "CLAUDE.md", "AGENTS.md",
                    "modelos/_preview/*",
                    # o README da extensão é da casa (caminhos e contatos), e o
                    # contrato é trecho de documentação de terceiro; a
                    # instalação da extensão está em docs/REQUISITOS.md.
                    "ccn_assistente/README.md", "ccn_assistente/contrato/*",
                    # o diário da casa guardado como dado (11/10/2026): as notas
                    # do desenvolvimento sobre os relatos do oficial e o
                    # relatório da inspeção de 12/08/2026. O sistema roda sem
                    # os dois (`database.py` os importa como opcionais).
                    "notas_do_desenvolvimento.py", "inspection_seed.py",
                    "tools/marcar_problema_atendido.py",
                    # B4 (11/10/2026): uma certidão de nascimento PREENCHIDA,
                    # de 01/09, com selos e dados reais dentro — e nenhum
                    # código a lê (os moldes do sistema são os três `.odt`).
                    "modelos/*.docx")
# RASCUNHO EM tools/: conserto pontual, publicação na produção, sonda, saída
#   de execução. Medido em 09/10/2026 — são os nomes desta árvore; quem criar
#   ferramenta de uso geral não use estes prefixos.
RASCUNHO_EM_TOOLS = ("tools/_*", "tools/patch*", "tools/apply_*", "tools/fix_*",
                     "tools/bump*", "tools/run_patch*", "tools/publicar_*",
                     "tools/write_partial*", "tools/restart_*", "tools/shot_*",
                     "tools/repair_*", "tools/update_doc*", "tools/seed_*",
                     "tools/*_agora.py", "tools/*_hoje.py", "tools/*.log",
                     "tools/*.json", "tools/*.txt", "tools/*elevado*")
# FERRAMENTAS DESTA CASA: corrigem ou importam dados desta serventia (minutas
#   da pasta dela, nomes dela, o acervo dela). Não são rascunho — rodaram de
#   verdade —, mas não servem a outro cartório. Medido em 09/10/2026.
FERRAMENTAS_DA_CASA = (
    "tools/importar_minutas_da_pasta_ri.py", "tools/gerar_caso_hipotetico_ri.py",
    "tools/extrair_rcpn_docx.py", "tools/esteira_rcpn_docx.py",
    "tools/uniformizar_nome_da_casa.py", "tools/conferir_para_a_crc.py",
    "tools/onr_lote_extrair_endereco_teor.py", "tools/import_problemas_fila.py",
    "tools/export_problemas_fila.py", "tools/listar_drift_prod_instalar.py",
    "tools/aplicar_regra_acervo_4015.py", "tools/descancelar_ato_do_ri.py",
    "tools/desfazer_ato_e_reintegrar_protocolo.py", "tools/atos_para_minutas_do_ri.py",
    "tools/preencher_marcadores_das_minutas_cnib.py", "tools/marcar_encerramento_pelo_ato.py",
    "tools/repor_partes_do_ato.py", "tools/anotar_rascunho_de_notas.py",
    "tools/atualizar_endereco_do_qr.py", "tools/marcar_problema_atendido.py",
)


def _imports(caminho: Path, nomes: set[str]) -> set[str]:
    """Módulos da raiz que este arquivo importa (ou cita como texto exato)."""
    try:
        arvore = ast.parse(caminho.read_text(encoding="utf-8", errors="replace"))
    except SyntaxError:
        return set()
    achou: set[str] = set()
    for n in ast.walk(arvore):
        if isinstance(n, ast.Import):
            achou.update(a.name.split(".")[0] for a in n.names)
        elif isinstance(n, ast.ImportFrom) and n.module and n.level == 0:
            achou.add(n.module.split(".")[0])
        elif isinstance(n, ast.Constant) and isinstance(n.value, str):
            # registro dinâmico (`import_module("x")`, listas de módulos)
            if n.value in nomes:
                achou.add(n.value)
    return achou & nomes


def modulos_alcancados(raiz: Path) -> set[str]:
    nomes = {p.stem for p in raiz.glob("*.py")}
    sementes = {s for s in SEMENTES_DO_APP if s in nomes}
    for pasta in ("tools", "tests", "installer", "ci"):
        for p in (raiz / pasta).rglob("*.py"):
            if not _rascunho(p.relative_to(raiz).as_posix()):
                sementes |= _imports(p, nomes)
    vistos: set[str] = set()
    fila = list(sementes)
    while fila:
        m = fila.pop()
        if m in vistos:
            continue
        vistos.add(m)
        fila.extend(_imports(raiz / f"{m}.py", nomes) - vistos)
    return vistos


def _rascunho(rel: str) -> bool:
    return (any(fnmatch.fnmatch(rel, p) for p in RASCUNHO_EM_TOOLS)
            or rel in FERRAMENTAS_DA_CASA)


def _teste_depende_do_que_ficou_fora(raiz: Path, rel: str, fora: set[str]) -> str:
    """O nome do arquivo de fora de que este teste depende, ou vazio.

    Teste público que importa um módulo que não foi publicado quebra na
    primeira rodada de quem clonar — então ele fica de fora junto. Procura o
    nome como import (`import x`, `tools.x`) ou como caminho (`tools/x.py`).
    """
    try:
        texto = (raiz / rel).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""
    for f in fora:
        stem = Path(f).stem
        if f in texto or f"tools.{stem}" in texto or (
                "/" not in f and (f"import {stem}" in texto or f"from {stem} " in texto)):
            return f
    return ""


def _ignorados_pelo_git(raiz: Path, rels: list[str]) -> set[str]:
    """O que o `.gitignore` da árvore exclui — sem criar `.git` dentro dela."""
    if not rels:
        return set()
    with tempfile.TemporaryDirectory() as tmp:
        idx = Path(tmp) / "idx.git"
        subprocess.run(["git", "init", "-q", "--bare", str(idx)], check=True)
        # EM BYTES, E NÃO EM TEXTO: no Windows o modo texto troca `\n` por
        #   `\r\n`, e o git procura «arquivo\r» — que não casa com regra
        #   nenhuma. A primeira versão deixou passar assim a lista local de
        #   nomes da casa, a chave de teste e os selos reais (medido 09/10).
        r = subprocess.run(
            ["git", f"--git-dir={idx}", f"--work-tree={raiz}", "check-ignore",
             "--no-index", "--stdin"],
            input=("\n".join(rels) + "\n").encode("utf-8"), capture_output=True)
        if r.returncode not in (0, 1):
            raise RuntimeError(
                f"git check-ignore falhou: {r.stderr.decode('utf-8', 'replace').strip()}")
        return {l.strip() for l in r.stdout.decode("utf-8").splitlines() if l.strip()}


def selecionar(raiz: Path = RAIZ) -> dict:
    """O que entra e o que fica de fora, com o motivo. Só lê."""
    alcancados = modulos_alcancados(raiz)
    entra: list[str] = []
    fora: dict[str, list[str]] = collections.defaultdict(list)
    for p in sorted(raiz.rglob("*")):
        if not p.is_file():
            continue
        rel = p.relative_to(raiz).as_posix()
        if "__pycache__" in rel or rel.startswith((".git/", "backups_patch/")):
            continue
        topo = rel.split("/")[0]
        if any(fnmatch.fnmatch(rel, f) for f in FORA_POR_DECISAO):
            fora["decisão do oficial (documentação/diário da casa)"].append(rel)
        elif "/" not in rel:
            if rel.endswith(".py"):
                if rel[:-3] in alcancados:
                    entra.append(rel)
                else:
                    fora["módulo da raiz que nada importa (rascunho)"].append(rel)
            elif rel in ARQUIVOS_DE_PROJETO:
                entra.append(rel)
            else:
                fora["arquivo solto na raiz"].append(rel)
        elif topo in PASTAS:
            if _rascunho(rel):
                fora["rascunho em tools/"].append(rel)
            else:
                entra.append(rel)
        else:
            fora["pasta fora da lista"].append(rel)
    ignorados = _ignorados_pelo_git(raiz, entra)
    if ignorados:
        fora[".gitignore"].extend(sorted(ignorados))
        entra = [r for r in entra if r not in ignorados]
    # Os testes que dependem de módulo ou ferramenta que ficou de fora.
    de_fora = {r for r in fora.get("rascunho em tools/", []) if r.endswith(".py")} | \
              {r for r in fora.get("módulo da raiz que nada importa (rascunho)", [])}
    sem_par = [r for r in entra if r.startswith("tests/") and r.endswith(".py")
               and _teste_depende_do_que_ficou_fora(raiz, r, de_fora)]
    if sem_par:
        fora["teste de algo que ficou de fora"].extend(sem_par)
        entra = [r for r in entra if r not in set(sem_par)]
    return {"entra": entra, "fora": dict(fora), "alcancados": alcancados}


_LITERAL_DE_DADO = re.compile(
    r"""["']([A-Za-z0-9_\-]+\.(?:json|sql|xsd|csv|ini|toml|xml|txt))["']""")


def dados_que_o_codigo_le(raiz: Path, entra: list[str]) -> list[tuple[str, str]]:
    """Arquivo de dados da RAIZ citado pelo código publicado e que não vai junto.

    Devolve (quem cita, o arquivo). Só olha o nome solto num literal do código
    (`Path(__file__).with_name("x.json")`, `RAIZ / "x.sql"`) que existe na raiz
    desta árvore — e que não entrou nem foi tirado pelo `.gitignore`. O que o
    `.gitignore` tira é decisão (selos reais, a deny-list local); o resto é
    esquecimento, e foi assim que a v3.7.1 saiu sem subir.
    """
    publicados = set(entra)
    candidatos = {}
    for rel in entra:
        if not rel.endswith(".py"):
            continue
        try:
            texto = (raiz / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for nome in _LITERAL_DE_DADO.findall(texto):
            if nome not in publicados and (raiz / nome).is_file():
                candidatos.setdefault(nome, rel)
    ignorados = _ignorados_pelo_git(raiz, sorted(candidatos))
    return sorted((quem, nome) for nome, quem in candidatos.items()
                  if nome not in ignorados)


MOLDES = (".odt", ".ott", ".ods", ".docx")
# O que identifica a pessoa que salvou o arquivo, dentro de `meta.xml` (ODF) e
# de `docProps/core.xml` (OOXML). Só o elemento sai; o resto do arquivo fica.
_QUEM_SALVOU = re.compile(
    r"<(meta:initial-creator|dc:creator|meta:printed-by|cp:lastModifiedBy)\b[^>]*>"
    r".*?</\1>|<(meta:initial-creator|dc:creator|meta:printed-by|cp:lastModifiedBy)\b[^>]*/>",
    re.S)


def impessoal(dados: bytes) -> bytes:
    """O mesmo molde, sem quem o salvou e sem a impressora dele. Só calcula.

    A impressora sai pela função que a impressão já usa
    (`impressao_pdf.sem_a_impressora_de_quem_salvou`) — duas réguas para a
    mesma coisa divergiriam. Arquivo que não abre como zip volta inalterado.
    """
    # da árvore onde este programa mora, e não de `RAIZ` (que os testes trocam)
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    import impressao_pdf   # noqa: E402  (a régua da casa)
    dados = impressao_pdf.sem_a_impressora_de_quem_salvou(dados)
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            fora = io.BytesIO()
            mudou = False
            with zipfile.ZipFile(fora, "w", zipfile.ZIP_DEFLATED) as saida:
                for item in z.infolist():
                    conteudo = z.read(item.filename)
                    if item.filename in ("meta.xml", "docProps/core.xml"):
                        texto = conteudo.decode("utf-8")
                        limpo = _QUEM_SALVOU.sub("", texto)
                        if limpo != texto:
                            conteudo, mudou = limpo.encode("utf-8"), True
                    # `writestr(item, …)` preserva o modo de cada membro — o
                    # `mimetype` do ODF tem de continuar o primeiro e sem
                    # compressão, senão o LibreOffice não o reconhece.
                    saida.writestr(item, conteudo)
            return fora.getvalue() if mudou else dados
    except (zipfile.BadZipFile, UnicodeDecodeError):
        return dados


def textos_do_molde(dados: bytes) -> list[tuple[str, str]]:
    """O XML de dentro de um molde (`membro`, `texto`), para o varredor ler."""
    try:
        with zipfile.ZipFile(io.BytesIO(dados)) as z:
            return [(nome, re.sub(r">\s*<", ">\n<",
                                  z.read(nome).decode("utf-8", "replace")))
                    for nome in z.namelist() if nome.endswith((".xml", ".rels"))]
    except zipfile.BadZipFile:
        return []


def varrer(raiz: Path, rels: list[str], denylist_local: Path | None = None) -> list:
    sys.path.insert(0, str(RAIZ))
    import ci.anti_vazamento as AV   # noqa: E402  (o varredor da casa)
    deny = AV.denylist_ativa(RAIZ, denylist_local)
    fict_arq = RAIZ / AV.FICTICIOS
    fict = AV.carregar_ficticios(fict_arq) if fict_arq.exists() else set()
    achados = []
    for rel in rels:
        p = raiz / rel
        if AV.arquivo_proibido(rel):
            achados.append(AV.Achado(rel, 0, "ARQUIVO_PROIBIDO", "nome proibido"))
            continue
        if any(fnmatch.fnmatch(rel, c) for c in AV.CAMINHOS_IGNORADOS):
            continue
        if p.suffix.lower() in MOLDES:
            # Um zip passava pelo portão sem ser lido (B4, 11/10/2026). E ele
            # é lido COMO SAIRIA — depois de `impessoal` —, senão a medição
            # acusaria na árvore o nome de quem salvou, que a exportação tira:
            # foi o que a primeira versão fez (6 achados que nunca iriam ao
            # público, apontados pela sessão do agente de produtividade).
            for membro, texto in textos_do_molde(impessoal(p.read_bytes())):
                achados.extend(AV.varrer_texto(texto, arquivo=f"{rel}!{membro}",
                                               denylist=deny, ficticios=fict))
                if _QUEM_SALVOU.search(texto):
                    achados.append(AV.Achado(f"{rel}!{membro}", 0, "QUEM_SALVOU",
                                             "o molde guarda o nome de quem o salvou"))
            continue
        if p.suffix.lower() not in AV.EXTENSOES_VARRIDAS or p.stat().st_size > AV.TAMANHO_MAXIMO:
            continue
        achados.extend(AV.varrer_texto(p.read_text(encoding="utf-8", errors="replace"),
                                       arquivo=rel, denylist=deny, ficticios=fict))
    return achados


def main(argv: list[str] | None = None) -> int:
    for s in (sys.stdout, sys.stderr):
        try:
            s.reconfigure(encoding="utf-8")
        except AttributeError:
            pass
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--gerar", metavar="DESTINO",
                    help="copia a árvore pública para DESTINO (fora do SANDBOX)")
    ap.add_argument("--denylist-local")
    ap.add_argument("--max", type=int, default=40, help="arquivos listados")
    a = ap.parse_args(argv)

    sel = selecionar(RAIZ)
    print(f"ENTRA: {len(sel['entra'])} arquivos "
          f"({len(sel['alcancados'])} módulos da raiz alcançados)")
    for motivo, rels in sorted(sel["fora"].items(), key=lambda x: -len(x[1])):
        print(f"FORA — {motivo}: {len(rels)}")

    base = RAIZ
    if a.gerar:
        destino = Path(a.gerar).resolve()
        if RAIZ in (destino, *destino.parents):
            print("Recusado: o destino não pode ficar dentro da árvore de origem.")
            return 2
        if destino.exists() and any(destino.iterdir()) and not (destino / ".exportado_publico").exists():
            print(f"Recusado: {destino} existe, não está vazio e não é uma "
                  f"exportação anterior. Nada foi copiado.")
            return 2
        if destino.exists():
            for filho in destino.iterdir():
                if filho.name == ".git":
                    continue        # o histórico do repositório, se houver, fica
                shutil.rmtree(filho) if filho.is_dir() else filho.unlink()
        destino.mkdir(parents=True, exist_ok=True)
        for rel in sel["entra"]:
            alvo = destino / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            if Path(rel).suffix.lower() in MOLDES:
                alvo.write_bytes(impessoal((RAIZ / rel).read_bytes()))
                continue
            shutil.copy2(RAIZ / rel, alvo)
        (destino / ".exportado_publico").write_text(
            "árvore gerada por tools/exportar_publico.py — não editar aqui\n",
            encoding="utf-8")
        print(f"copiado para {destino}")
        base = destino

    faltam_dados = dados_que_o_codigo_le(RAIZ, sel["entra"])
    if faltam_dados:
        print("\nFALTA NO PACOTE — arquivo de dados que o código publicado lê:")
        for quem, nome in faltam_dados:
            print(f"  {nome}  (citado em {quem})")
        print("Ponha em ARQUIVOS_DE_PROJETO, ou no .gitignore se ficar de fora de propósito.")
        return 1

    achados = varrer(base, sel["entra"],
                     Path(a.denylist_local) if a.denylist_local else None)
    por_tipo = collections.Counter(x.tipo for x in achados)
    por_arq = collections.Counter(x.arquivo for x in achados)
    print(f"\nVARREDOR: {len(achados)} achados em {len(por_arq)} arquivos"
          + (" — " + ", ".join(f"{t} {n}" for t, n in por_tipo.most_common()) if achados else ""))
    for arq, n in por_arq.most_common(a.max):
        print(f"  {n:5}  {arq}")
    if achados:
        print("\nNÃO PUBLICAR: o portão só abre com zero achados.")
        return 1
    print("\nZero achados no que entraria.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
