from __future__ import annotations

import argparse
import ast
import hashlib
import json
import os
import re
import sys
import zipfile
from datetime import datetime, timezone
from pathlib import Path

# O MODULO DO SISTEMA E IMPORTADO DE PROPOSITO, e nao copiado — ver a lista das
# pastas ignoradas, mais abaixo. Ele e stdlib puro no topo, entao isto nao
# arrasta o sistema: arrasta a regua.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import update_manager  # noqa: E402  (o caminho vem de cima, nesta ordem)

# **O CACHE DAS FERRAMENTAS IA JUNTO PARA O SERVIDOR.** Medido no pacote da
# 3.6.49, em 31/08/2026: **15 arquivos e 347 KB** de `.pytest_cache` e
# `.ruff_cache`. `__pycache__` ja estava excluido desde sempre; estes dois
# nasceram depois e ninguem os acrescentou.
#
#   Nao quebravam nada — sao inertes —, mas `.pytest_cache/v/cache/lastfailed`
#   copiado para a maquina do balcao diz que **testes falharam ali**, com nomes
#   de teste e tudo. Quem o abrisse tiraria a conclusao errada sobre a
#   instalacao, e o arquivo tem cara de resposta.
#
#   A lista e por NOME DE PASTA, e continua sendo: casar por padrao («tudo que
#   termina em _cache») apanharia pasta de dados que alguem chame assim.
EXCLUDE_DIRS = update_manager.PASTAS_IGNORADAS_NA_COPIA

# A LISTA NAO SE ESCREVE AQUI — ELA VEM DO MODULO DO SISTEMA. 15/09/2026.
#
#   Eram DUAS listas respondendo a mesma pergunta — esta e
#   `update_manager.PASTAS_IGNORADAS_NA_COPIA` —, e a do sistema estava sem
#   `output`, `tmp`, `dist`, `build` e `dist_unico`. **Lista escrita a mao
#   noutro arquivo envelhece na tarde em que se escreve**, e aqui a divergencia
#   tinha consequencia medida e nao teorica:
#
#   a preparacao da atualizacao copia a pasta da instalacao com
#   `shutil.copytree`, que PERCORRE tudo o que copia. Uma pasta de rascunho
#   ilegivel derruba a montagem INTEIRA — aconteceu nesta arvore em 15/09/2026,
#   com uma pasta de teste que ficou com permissao negada. O pacote nunca levou
#   `tmp/`; a preparacao levava.
#
#   `update_manager` e stdlib puro no topo, entao importar dele aqui nao arrasta
#   o sistema para dentro: arrasta a lista.
EXCLUDE_SUFFIXES = {'.pyc', '.pyo', '.zip', '.cgu', '.new'}
# O `=ro` e o `ERRO_POWERSHELL.txt` sao strays de ZERO BYTE: o primeiro nasceu de
# um comando digitado errado em 08/09 e o segundo de um `>` que apontou para o
# arquivo errado. Medido em 15/09/2026: nenhum dos dois e aberto por linha
# nenhuma do programa, e o `ERRO_POWERSHELL.txt` nunca chegou ao servidor.
#   Nome de arquivo de erro dentro da pasta do programa e pior que sobra: quem
#   abre a pasta do balcao o le como se fosse aviso da instalacao.
EXCLUDE_NAMES = {'geracao_exe.log', '=ro', 'ERRO_POWERSHELL.txt'}
EXCLUDE_NAMES.update({
    # Rascunhos antigos em UTF-16, sem uso pelo sistema. Não são módulos
    # instaláveis; a conferência do pacote os recusava em 12/10/2026.
    '_norm_snippet.py', '_patch265_worker.py', '_patch_avisos_v257.py',
    '_patch_faixas_modal_262.py', '_patch_nu_avisos_v2.py',
    '_patch_task_checkbox_262.py', '_proc_snippet.py', 'patch264_modal.py',
    'patch264_tests.py', 'patch_test_modal_js.py', 'shot_politica_senhas.py',
})

# AS COPIAS DE SEGURANCA DE QUEM EDITA NAO VIAJAM.
#
# Medido em 15/09/2026, antes de empacotar: o pacote levaria **854** arquivos, e
# **36** deles eram copia de arquivo de programa com outro nome — 5,1 MB. Sao as
# copias que quem edita faz antes de mexer (`atribuicoes_web.py.bak_pre_folha_*
# `, `ri_odt.py.bak_...`, `atribuicoes_web.py.new`), e mais um arquivo de zero
# byte chamado `=ro`, que nasceu de um comando digitado errado em 08/09.
#
#   Nada disso tem papel no servidor — nao e importado, nao e lido, nao e
#   aberto —, e e a mesma familia do `.pytest_cache`: **arquivo inerte com cara
#   de resposta** dentro da pasta do programa. Quem abrir a pasta do balcao
#   encontraria trinta e seis copias do sistema com nomes que quase sao os
#   verdadeiros, e "qual destes e o que esta rodando?" nao se responde olhando.
#
#   A lista e por PEDACO DO NOME (`.bak`), porque as copias nao tem sufixo
#   constante: o sufixo de cada uma e uma frase de quem a fez. E o `.new` e o
#   `=ro` vao por nome inteiro, que e como eles sao.
EXCLUDE_MARCAS_NO_NOME = ('.bak', '.original')

# E ARQUIVO QUE NAO E DO PROGRAMA NA RAIZ DA PASTA.
#
# Medido em 15/09/2026: a raiz da pasta que viaja tinha `previa_inteiro_teor_daiane.pdf`
# (71 KB) — a previa de uma certidao de cliente, salva ali para conferencia e esquecida.
# Nao e importada nem aberta, e o nome dela carrega o nome de uma pessoa da casa.
#
#   **A REGRA E SO PARA A RAIZ, E ISSO NAO E DETALHE.** Um filtro por `.pdf` no pacote
#   inteiro tiraria `DOCUMENTACAO/modelos_teor_rtdpj/*.pdf`, que sao 3,9 MB de modelos
#   do RTDPJ que a ajuda le — **filtro que tira o que devia ficar e pior que filtro
#   nenhum**. A raiz nao guarda documento: guarda programa.
EXCLUDE_PDF_NA_RAIZ = True

# E MATERIAL DE TRABALHO DE QUEM EDITA, NA RAIZ DA PASTA.
#
# Medido em 17/09/2026, antes de empacotar: **38 entradas de nivel 1 comecando
# com `_`** — tres pastas (`__pycache__`, que ja estava excluida;
# `_crops_matricula/`, 240 arquivos; `_preview_fichas/`, 6) e 35 arquivos soltos
# (`_map_cert_texto*.py`, `_ocr_erros.json`, `_mismatch_imagens.json`,
# `_publish_*_log.txt`, `_restart_cg.ps1`...). O pacote levaria **280 arquivos,
# 0,55 MB** disso.
#
#   E A CONTA FECHA: 246 sao das duas pastas de rascunho (`_crops_matricula/`
#   240, `_preview_fichas/` 6) e 34 sao soltos. **Um dos 35 ja saia sozinho**,
#   pelo sufixo `.zip` (`_crops_matricula.zip`) — sem essa linha, quem somasse
#   35 + 246 acharia 281 e concluiria que a medicao esta errada por um.
#
#   NENHUM E DO PROGRAMA, e isso foi medido dos dois lados: procurei o nome de
#   cada um em todo `import` da arvore, e os quatro `.py` de underscore — os
#   unicos modulos do conjunto — nao aparecem em nenhum. Quem os chama e
#   material de trabalho da MESMA familia (`check_pub.py` chama
#   `_pub_sem_numero.ps1`, `export_crops.py` escreve em `_crops_matricula/`,
#   `varrer_ocr_lote.py` em `_ocr_erros.json`), e nada disso e aberto pelo
#   sistema.
#
#   A FAMILIA E A MESMA DO `.pytest_cache` E DOS `.bak`: **arquivo inerte com
#   cara de resposta** dentro da pasta do programa — e com uma cara pior, porque
#   `_preview_fichas/` guarda **seis recortes do topo de fichas reais**
#   (matriculas 1009, 1354, 3528 e 3542) e `_mismatch_imagens.json` guarda
#   numero de matricula. Nao e dado de cliente, e nao tem papel nenhum na
#   maquina do balcao.
#
# A REGRA E SO PARA A RAIZ, pela mesma razao de `EXCLUDE_PDF_NA_RAIZ`: la mora
# programa, e nao rascunho. **Um filtro por `_` no NOME do arquivo, em qualquer
# nivel, tiraria `templates/_cobrar.html`, `_fraude.html` e `_rascunho.html`** —
# que sao as macros de tres telas do sistema, e a mesma familia de
# `_pessoa_do_assento.html`. Por isso o filtro e pelo PRIMEIRO pedaco do
# CAMINHO, e nao pelo nome: assim ele alcanca a pasta de rascunho inteira e nao
# toca em nada que esteja dentro de pasta de verdade.
#
# E o filtro NAO poda, de proposito: ele e aplicado depois da varredura, como os
# demais, e assim a equivalencia com a regra antiga (`_pela_regra_antiga`, no
# teste) e exata por construcao. Podar pastas exigiria o argumento de que so o
# primeiro nivel e alcancado — verdade, e a regra que deixaria a porta aberta
# para a proxima poda nao equivaler.
EXCLUDE_UNDERSCORE_NA_RAIZ = True

# Bancos e rascunhos não são código de atualização. A exclusão dos rascunhos é
# limitada à raiz: ferramentas legítimas dentro de tools/ continuam no pacote.
# O banco da árvore do instalador pode até estar vazio hoje, mas jamais deve
# substituir ou acompanhar dados de uma serventia num CGU.
EXCLUDE_BANCO_SUFFIXES = ('.sqlite3', '.sqlite3-wal', '.sqlite3-shm')
EXCLUDE_RASCUNHO_RAIZ = ('tmp_', 'fix_', 'patch_')

# OS ARQUIVOS QUE MORAM FORA DA PASTA EMPACOTADA, E VIAJAM ASSIM MESMO.
#
# O `CLAUDE.md` e o arquivo das regras da casa, e ele fica na RAIZ DO PROJETO —
# um nivel acima de `SERVIDOR\INSTALAR_CARTORIO_GESTAO`, que e a pasta que este
# script empacota. Ele mora la porque e de la que o Cursor o le; mover seria
# quebrar quem o le hoje.
#
#   Enquanto ele nao viajava, a ajuda do servidor nao tinha como saber **como se
#   decide nesta casa**: respondia pela regra geral do assunto, que e a pior
#   forma de resposta errada — a que parece certa. Medido em 15/09/2026: 385 mil
#   caracteres, e o unico lugar onde as decisoes estao escritas com o porque.
#
#   **Nao se faz copia dele para dentro da pasta.** Copia com outro nome
#   resolveria hoje e divergiria no primeiro conserto — duas versoes do arquivo
#   das regras, e quem le a velha nao sabe que e a velha. Aqui ha um segundo
#   caminho de entrada, com o destino declarado: o arquivo entra no pacote como
#   `CLAUDE.md` na raiz do programa, que e onde a ajuda o procura.
DE_FORA = {'CLAUDE.md': 'CLAUDE.md'}


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def iter_files(root: Path):
    # A PODA VEM ANTES DA VARREDURA — 16/09/2026.
    #
    #   Aqui havia `sorted(root.rglob('*'))`, que percorre TUDO e so depois
    #   descarta. Recontado nesta arvore em 17/09/2026, com o runtime do
    #   servidor: o `rglob` devolvia **8.386 entradas** — 6.481 arquivos de
    #   pasta excluida (`.venv` 3.953, `tmp` 1.053, `tests` 967,
    #   `__pycache__` 465, `.ruff_cache` 18, `build` 12, `.pytest_cache` 9,
    #   `output` 4) e o resto, pastas —, para os filtros aproveitarem **882**.
    #   Custa **5,4 s por chamada**; podado, **0,4 s**.
    #   O conferidor paga duas (a arvore e a instalacao) em cada atualizacao que
    #   o oficial aplica, e a montagem do pacote paga outra.
    #
    #   **As contagens sao de 17/09/2026, e os tempos, de 16/09.** Foram
    #   recontadas porque o filtro do material de trabalho da raiz mudou o
    #   conjunto (eram 7.936, 6.312 e 875); os dois tempos NAO foram remedidos,
    #   e medi-los aqui de outro jeito seria trocar uma medicao por outra que
    #   mede coisa parecida.
    #
    #   **Podar e EQUIVALENTE, e nao parecido**: o filtro e por PARTE do caminho
    #   (`part in EXCLUDE_DIRS`), logo pasta excluida exclui todos os
    #   descendentes dela — que e exatamente o que deixar de percorrer faz. Quem
    #   guarda a igualdade e
    #   `tests/test_pacote_nao_leva_lixo.py::test_a_poda_nao_muda_a_lista`,
    #   que remonta a regra antiga e exige a mesma lista, arquivo por arquivo.
    #   Medido: 882 de um lado, 882 do outro, zero de diferenca nos dois sentidos.
    for base, pastas, arquivos in os.walk(root):
        pastas[:] = sorted(p for p in pastas if p not in EXCLUDE_DIRS)
        for nome in sorted(arquivos):
            p = Path(base) / nome
            if not p.is_file():
                continue
            rel = p.relative_to(root)
            if any(part in EXCLUDE_DIRS for part in rel.parts):
                continue
            if p.name in EXCLUDE_NAMES or p.suffix.lower() in EXCLUDE_SUFFIXES:
                continue
            if any(marca in p.name for marca in EXCLUDE_MARCAS_NO_NOME):
                continue
            # Ver `EXCLUDE_PDF_NA_RAIZ`: documento solto na raiz da pasta do programa.
            if EXCLUDE_PDF_NA_RAIZ and len(rel.parts) == 1 and p.suffix.lower() == '.pdf':
                continue
            # Ver `EXCLUDE_UNDERSCORE_NA_RAIZ`: material de trabalho na raiz da
            # pasta do programa. O filtro e pelo PRIMEIRO pedaco do caminho, e
            # nao pelo nome do arquivo: pega a pasta de rascunho inteira e nao
            # alcanca as macros `templates/_*.html`.
            if EXCLUDE_UNDERSCORE_NA_RAIZ and rel.parts[0].startswith('_'):
                continue
            if p.name.lower().endswith(EXCLUDE_BANCO_SUFFIXES):
                continue
            if (len(rel.parts) == 1
                    and p.name.lower().startswith(EXCLUDE_RASCUNHO_RAIZ)):
                continue
            yield p, rel.as_posix()


def arquivos_de_fora(root: Path):
    """O que viaja sem estar dentro da pasta — ver `DE_FORA`.

    Procura na raiz do projeto primeiro, porque e la que o arquivo e editado; e
    avisa se achar mais de um, porque duas copias do arquivo das regras e
    exatamente o que a ausencia de copia existia para evitar.
    """
    for nome, destino in DE_FORA.items():
        achados = [pasta / nome for pasta in (root.parent.parent, root.parent, root)
                   if (pasta / nome).is_file()]
        if len(achados) > 1:
            print(f'AVISO: ha mais de um {nome}: '
                  + ', '.join(str(p) for p in achados)
                  + f' — vai o primeiro ({achados[0]}), que e o editado.')
        if achados:
            yield achados[0], destino


def todos_os_arquivos(root: Path):
    """O que entra no pacote, sem repetir caminho de destino.

    **O `DE_FORA` GANHA DA PASTA.** Se alguem copiar o `CLAUDE.md` para dentro
    da pasta empacotada, ele entraria duas vezes no manifesto — a segunda
    sobrescrevendo a primeira dentro do zip —, e o pacote sairia com um arquivo
    que ninguem sabe qual e. A declaracao explicita vence o achado por varredura.

    **E O PAR SAI NA MESMA ORDEM DO `iter_files` — `(arquivo, destino)`.**

    Isto aqui ja esteve invertido, e o estrago tem data: eu escrevi esta funcao
    devolvendo `(destino, arquivo)` por causa do dicionario de dentro (a chave e
    o destino, e `items()` sai com ela na frente). O `main` desempacotava na
    ordem do `iter_files`, recebeu um `str` onde esperava um `Path` e morreu em
    `digest()` com `'str' object has no attribute 'open'` — **no meio do
    empacotamento de 15/09/2026, sem que nada no erro dissesse qual das duas
    funcoes estava torta.** Duas funcoes com o mesmo par e ordens opostas sao
    duas reguas para a mesma medida; a que vale e a de `iter_files`.

    A conferencia custou uma linha e nao prova nada sozinha: quem guarda isso e
    `tests/test_pacote_nao_leva_lixo.py::test_as_duas_funcoes_devolvem_o_par_na_mesma_ordem`.
    """
    achados: dict[str, Path] = {}
    for p, rel in iter_files(root):
        achados[rel] = p
    for p, rel in arquivos_de_fora(root):
        achados[rel] = p
    return sorted((p, rel) for rel, p in achados.items())


# O PACOTE NASCE DE UM COMMIT, E LEVA O NOME DELE — 12/10/2026.
#   Ordem do oficial: «o empacotador grava o commit sozinho» e «mais seguranca
#   nas atualizacoes». Ate aqui o git privado (VERSIONAMENTO\casa.git, ramo
#   `main`) so recebia commit quando alguem lembrava — e ninguem lembrava.
#   Agora, quando a origem e o INSTALAR e o versionamento existe, o empacotador:
#     1. grava o estado da arvore no `main` ANTES de montar o pacote;
#     2. escreve o commit no manifesto (`source_commit`) — o pacote diz de que
#        estado veio, e a producao pode dizer que codigo esta rodando;
#     3. depois do pacote, poe a etiqueta `vX.Y.Z` com o nome e o SHA-256 dele.
#   Versao que ja tem etiqueta e RECUSADA: dois pacotes diferentes com o mesmo
#   numero foi exatamente o que gerou o `_broken.cgu` de 29/09.
#   Sem o versionamento (outra instalacao, outro cartorio), segue como antes.
NOME_DA_ORIGEM_VERSIONADA = 'INSTALAR_CARTORIO_GESTAO'


def versionamento_da_arvore(root: Path):
    """(git_dir, index) do git privado, se esta origem e o INSTALAR da casa."""
    if root.name != NOME_DA_ORIGEM_VERSIONADA:
        return None
    for pai in root.parents:
        git_dir = pai / 'VERSIONAMENTO' / 'casa.git'
        if git_dir.is_dir():
            return git_dir, git_dir / 'index_instalar'
    return None


def _git(versionamento, root: Path, *args: str, ok: bool = False) -> str:
    import subprocess
    git_dir, index = versionamento
    # BYTES, e nao `text=True`: no Windows o texto vai ao git com `\r` e nada
    # casa (o defeito do check-ignore, 09/10/2026).
    r = subprocess.run(
        ['git', f'--git-dir={git_dir}', f'--work-tree={root}',
         '-c', 'core.autocrlf=false', '-c', 'core.safecrlf=false',
         '-c', 'user.name=Cartorio Gestao (empacotador)',
         '-c', 'user.email=versionamento@cartorio-gestao.invalid', *args],
        cwd=root, capture_output=True,
        env=dict(os.environ, GIT_INDEX_FILE=str(index)))
    if r.returncode and not ok:
        raise SystemExit('o versionamento falhou (git ' + ' '.join(args[:2]) + '): '
                         + r.stderr.decode('utf-8', 'replace').strip()
                         + '\nNenhum pacote foi gerado. Para gerar sem gravar no '
                           'git, use --sem-versionar.')
    return r.stdout.decode('utf-8', 'replace').strip()


def versionar_antes(versionamento, root: Path, versao: str, notas: str) -> str:
    """Grava a arvore no `main` e devolve o commit de onde o pacote vai sair."""
    etiqueta = f'v{versao}'
    if _git(versionamento, root, 'tag', '--list', etiqueta):
        raise SystemExit(
            f'A versao {versao} ja foi empacotada (etiqueta {etiqueta} no git). '
            'Suba a versao em app.py e VERSAO.txt: dois pacotes com o mesmo numero '
            'e o mesmo erro do _broken.cgu de 29/09/2026.')
    _git(versionamento, root, 'symbolic-ref', 'HEAD', 'refs/heads/main')
    _git(versionamento, root, 'add', '-A')
    tem_historico = _git(versionamento, root, 'rev-parse', '--verify', '-q', 'HEAD', ok=True)
    if (not tem_historico
            or _git(versionamento, root, 'diff', '--cached', '--name-only', 'HEAD', ok=True)):
        resumo = (notas or '').strip().splitlines()[0][:200] if (notas or '').strip() else ''
        _git(versionamento, root, 'commit', '-q', '-m',
             f'{versao} — pacote' + (f': {resumo}' if resumo else '')
             + '\n\nGravado pelo empacotador (tools/criar_atualizacao.py).')
    return _git(versionamento, root, 'rev-parse', 'HEAD')


def etiquetar_depois(versionamento, root: Path, versao: str, commit: str,
                     pacote: Path, sha256: str) -> None:
    _git(versionamento, root, 'tag', '-a', f'v{versao}', commit, '-m',
         f'{versao}\n\npacote {pacote.name}\nsha256 {sha256}')


def main() -> int:
    ap = argparse.ArgumentParser(description='Gera pacote .cgu do Cartorio Gestao')
    ap.add_argument('source', type=Path)
    ap.add_argument('--version', required=True)
    ap.add_argument('--min-version', required=True)
    ap.add_argument('--output', type=Path, required=True)
    ap.add_argument('--notes', default='')
    ap.add_argument(
        '--validation-summary', default='',
        help='Resumo dos testes executados no ambiente confiavel de desenvolvimento',
    )
    ap.add_argument(
        '--validation-command', default='',
        help='Comando de teste executado no ambiente de desenvolvimento',
    )
    ap.add_argument(
        '--validation-count', type=int, default=0,
        help='Quantidade de testes aprovados informada pelo desenvolvedor',
    )
    ap.add_argument('--run-pip', action='store_true', help='Executa pip install -r requirements.txt durante a atualizacao')
    ap.add_argument('--sem-versionar', action='store_true',
                    help='Nao grava no git privado (so quando ele nao estiver disponivel)')
    ap.add_argument('--assinar', type=Path, default=None, metavar='CHAVE',
                    help='Assina o pacote com a chave do oficial (a senha e pedida na hora)')
    args = ap.parse_args()

    root = args.source.resolve()
    if not re.fullmatch(r'\d+(?:\.\d+){1,3}', args.version):
        ap.error('--version deve conter apenas numeros separados por pontos')
    versao_arquivo = root / 'VERSAO.txt'
    if not versao_arquivo.is_file():
        ap.error('a origem precisa conter VERSAO.txt')
    declarada = versao_arquivo.read_text(encoding='utf-8').strip()
    if declarada != args.version:
        ap.error(
            f'VERSAO.txt declara {declarada!r}, diferente de --version {args.version!r}'
        )
    app_arquivo = root / 'app.py'
    if not app_arquivo.is_file():
        ap.error('a origem precisa conter app.py')
    try:
        arvore_app = ast.parse(app_arquivo.read_text(encoding='utf-8'), filename='app.py')
    except (OSError, UnicodeDecodeError, SyntaxError) as exc:
        ap.error(f'app.py nao pode ser conferido: {exc}')
    versao_app = ''
    for no in arvore_app.body:
        if not isinstance(no, (ast.Assign, ast.AnnAssign)):
            continue
        alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
        valor = no.value
        if (any(isinstance(alvo, ast.Name) and alvo.id == 'VERSION'
                for alvo in alvos)
                and isinstance(valor, ast.Constant)
                and isinstance(valor.value, str)):
            versao_app = valor.value.strip()
            break
    if versao_app != args.version:
        ap.error(
            f'app.py declara VERSION={versao_app!r}, diferente de '
            f'--version {args.version!r}'
        )
    # A chave se abre ANTES de qualquer coisa ser gravada: senha errada nao
    # pode deixar um commit e uma etiqueta para um pacote que nao saiu.
    privada = None
    if args.assinar is not None:
        import getpass
        import assinatura_da_atualizacao as ASS
        if not args.assinar.is_file():
            ap.error(f'chave de assinatura nao encontrada: {args.assinar}')
        senha = getpass.getpass('Senha da chave de assinatura: ')
        try:
            privada = ASS.carregar_privada(args.assinar.read_bytes(), senha.encode('utf-8'))
        except ASS.AssinaturaRecusada as exc:
            ap.error(str(exc))
    versionamento = None if args.sem_versionar else versionamento_da_arvore(root)
    commit = versionar_antes(versionamento, root, args.version, args.notes) if versionamento else ''
    files = []
    for p, rel in todos_os_arquivos(root):
        files.append({'path': rel, 'sha256': digest(p)})
    manifest = {
        'product': 'CartorioGestao',
        'format': 1,
        'version': args.version,
        'min_version': args.min_version,
        'notes': args.notes,
        'run_pip': bool(args.run_pip),
        'files': files,
        'delete': [],
    }
    if commit:
        manifest['source_commit'] = commit
        manifest['source_branch'] = 'main'
    if args.validation_summary.strip():
        manifest['validation'] = {
            'source': 'developer_build',
            'summary': args.validation_summary.strip(),
            'command': args.validation_command.strip(),
            'passed_count': max(0, args.validation_count),
            'recorded_at': datetime.now(timezone.utc).isoformat(timespec='seconds'),
            'notice': 'Declaracao do ambiente de desenvolvimento; nao executada pelo servidor.',
        }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    # O manifesto vira bytes UMA vez: e sobre estes bytes que a assinatura e
    # feita, e sao estes que vao no pacote.
    manifesto_bytes = json.dumps(manifest, ensure_ascii=False, indent=2).encode('utf-8')
    with zipfile.ZipFile(args.output, 'w', zipfile.ZIP_DEFLATED) as zf:
        zf.writestr('update_manifest.json', manifesto_bytes)
        if privada is not None:
            zf.writestr(ASS.NOME_NO_PACOTE, json.dumps(
                ASS.assinar(manifesto_bytes, privada), ensure_ascii=False, indent=2))
        for p, rel in todos_os_arquivos(root):
            zf.write(p, f'payload/{rel}')
    sha_do_pacote = digest(args.output)
    if versionamento:
        etiquetar_depois(versionamento, root, args.version, commit, args.output, sha_do_pacote)
    print(args.output)
    print(sha_do_pacote)
    if commit:
        print(f'git: commit {commit[:12]} no main, etiqueta v{args.version}')
    print('assinado' if privada is not None else 'NAO ASSINADO')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
