from __future__ import annotations

import ast
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath
from typing import Any

PRODUCT = "CartorioGestao"
FORMAT_VERSION = 1
MAX_PACKAGE_BYTES = 100 * 1024 * 1024
MAX_FILES = 2_000
MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_TOTAL_UNCOMPRESSED = 250 * 1024 * 1024
VERSION_RE = re.compile(r"^\d+(?:\.\d+){1,3}$")

# A LISTA E UMA SO, E ELA JA ESTAVA EM DOIS LUGARES DIVERGINDO — 15/09/2026.
#
#   Aqui ficavam `runtime`, `updates` e `tests`, e o empacotador
#   (`tools/criar_atualizacao.py`, `EXCLUDE_DIRS`) ja excluia tambem `output`,
#   `tmp`, `dist`, `build` e `dist_unico`. **Duas listas que respondem a mesma
#   pergunta** — «o que e programa e o que e sobra de quem escreve o programa» —
#   divergem na tarde em que uma delas e editada.
#
#   E a divergencia tinha consequencia medida, nao teorica: `shutil.copytree`
#   PERCORRE o que copia, e **uma sobra ilegivel derruba a montagem inteira**.
#   Aconteceu nesta arvore em 15/09/2026 — uma pasta de teste que ficou com
#   permissao negada (`tmp/pytest-cancelamento-folhas-3677`) fez «validar e
#   preparar» falhar, com a mensagem crua do `shutil.Error` no lugar da frase.
#   O pacote nao levava `tmp/`; a preparacao levava.
#
#   Quem leva o programa nao precisa de pasta de rascunho de ninguem. A lista
#   boa e a do empacotador, que e a que ja tinha sido medida.
PASTAS_IGNORADAS_NA_COPIA = {
    ".git", ".venv", "__pycache__", ".pytest_cache", ".ruff_cache",
    "runtime", "updates", "tests",
    "output", "tmp", "dist", "build", "dist_unico",
    "backups_patch",
}
CAMINHOS_CRITICOS = {
    "app.py", "database.py", "security.py", "update_manager.py",
    "requirements.txt", "installer/aplicar_atualizacao.ps1",
    #   O COMPONENTE QUE PARA E SOBE O SERVICO — 15/09/2026.
    #     Ele decide se o balcao volta ao ar depois da copia, e as duas portas de
    #     atualizacao o chamam. Critico pelo mesmo motivo do aplicar_atualizacao.ps1:
    #     se ele nao chegar, a parada e a subida ficam sem quem as faca.
    "installer/reiniciar_servidor.ps1",
}


class UpdateError(ValueError):
    pass


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def version_key(value: str) -> tuple[int, ...]:
    parts: list[int] = []
    for piece in (value or "0").split("."):
        digits = "".join(ch for ch in piece if ch.isdigit())
        parts.append(int(digits or 0))
    return tuple((parts + [0, 0, 0])[:4])


def _safe_rel(path: str) -> str:
    # Pacotes usam sempre caminhos POSIX relativos. Barras invertidas e dois-pontos
    # sao rejeitados para impedir que um pacote escape da pasta de instalacao no Windows.
    if not path or "\\" in path or ":" in path or "\x00" in path:
        raise UpdateError(f"Caminho invalido no pacote: {path}")
    p = PurePosixPath(path)
    if p.is_absolute() or ".." in p.parts or not p.parts:
        raise UpdateError(f"Caminho invalido no pacote: {path}")
    return p.as_posix()


def _safe_version(value: Any) -> str:
    versao = str(value or "").strip()
    if not VERSION_RE.fullmatch(versao):
        raise UpdateError(
            "Versao de destino invalida. Use somente numeros separados por "
            "pontos, por exemplo 3.7.0."
        )
    return versao


def _digest_valido(value: Any) -> str:
    digest = str(value or "").strip().lower()
    if not re.fullmatch(r"[0-9a-f]{64}", digest):
        raise UpdateError("SHA-256 ausente ou invalido no manifesto.")
    return digest


def _escrever_json(caminho: Path, dados: dict) -> None:
    temporario = caminho.with_suffix(caminho.suffix + ".tmp")
    temporario.write_text(
        json.dumps(dados, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    temporario.replace(caminho)


def validate_and_stage(package: Path, stage_root: Path, current_version: str,
                       expected_sha256: str = "",
                       *, require_expected_hash: bool = False) -> dict[str, Any]:
    package = Path(package)
    if not package.is_file() or package.stat().st_size <= 0:
        raise UpdateError("Pacote de atualizacao vazio ou inexistente.")
    if package.stat().st_size > MAX_PACKAGE_BYTES:
        raise UpdateError(
            f"Pacote acima do limite de {MAX_PACKAGE_BYTES // 1024 // 1024} MB."
        )
    actual_package_hash = sha256_file(package)
    expected = (expected_sha256 or "").strip().lower().replace(" ", "")
    if require_expected_hash and not expected:
        raise UpdateError(
            "Informe o SHA-256 recebido por um canal separado do pacote."
        )
    if expected and not re.fullmatch(r"[0-9a-f]{64}", expected):
        raise UpdateError("O SHA-256 informado deve ter 64 caracteres hexadecimais.")
    if expected and expected != actual_package_hash:
        raise UpdateError("O SHA-256 informado nao corresponde ao arquivo recebido.")

    with zipfile.ZipFile(package, "r") as zf:
        informacoes = zf.infolist()
        if len(informacoes) > MAX_FILES + 1:
            raise UpdateError("Pacote com quantidade excessiva de arquivos.")
        if any(i.flag_bits & 0x1 for i in informacoes):
            raise UpdateError("Pacote criptografado nao e aceito.")
        total = sum(i.file_size for i in informacoes)
        if total > MAX_TOTAL_UNCOMPRESSED:
            raise UpdateError("Conteudo descompactado acima do limite seguro.")
        grande = next((i.filename for i in informacoes
                       if i.file_size > MAX_FILE_BYTES), "")
        if grande:
            raise UpdateError(f"Arquivo interno acima do limite seguro: {grande}")
        nomes_lista = zf.namelist()
        if len(nomes_lista) != len(set(nomes_lista)):
            raise UpdateError("Pacote contem nomes internos duplicados.")
        names = set(nomes_lista)
        if "update_manifest.json" not in names:
            raise UpdateError("Pacote sem update_manifest.json.")
        manifesto_bytes = zf.read("update_manifest.json")
        try:
            manifest = json.loads(manifesto_bytes.decode("utf-8"))
        except Exception as exc:
            raise UpdateError("Manifesto de atualizacao invalido.") from exc
        # QUEM FEZ O PACOTE — 12/10/2026. O SHA-256 prova que ele chegou
        # inteiro; a assinatura prova que foi o oficial quem o montou. Ela e
        # conferida ANTES de qualquer arquivo ser escrito na preparacao. Sem
        # chave cadastrada (`CHAVES_CONFIAVEIS` vazio), aceita-se como antes e
        # a tela diz que o pacote nao e assinado. Ver assinatura_da_atualizacao.
        import assinatura_da_atualizacao as ASS
        try:
            assinatura = ASS.conferir(
                manifesto_bytes,
                zf.read(ASS.NOME_NO_PACOTE) if ASS.NOME_NO_PACOTE in names else None)
        except ASS.AssinaturaRecusada as exc:
            raise UpdateError(str(exc)) from exc
        if manifest.get("product") != PRODUCT or int(manifest.get("format", 0)) != FORMAT_VERSION:
            raise UpdateError("Pacote nao pertence a este produto ou usa formato incompativel.")
        target_version = _safe_version(manifest.get("version"))
        if version_key(target_version) <= version_key(current_version):
            raise UpdateError(f"A versao {target_version} nao e posterior a versao instalada {current_version}.")
        min_version = str(manifest.get("min_version", "0")).strip()
        if min_version != "0":
            _safe_version(min_version)
        if version_key(current_version) < version_key(min_version):
            raise UpdateError(f"Esta atualizacao exige pelo menos a versao {min_version}.")
        files = manifest.get("files")
        if not isinstance(files, list) or not files:
            raise UpdateError("Manifesto sem arquivos de atualizacao.")
        if len(files) > MAX_FILES:
            raise UpdateError("Manifesto com quantidade excessiva de arquivos.")

        stage_root = Path(stage_root).resolve()
        stage_root.mkdir(parents=True, exist_ok=True)
        stage_dir = (stage_root / target_version).resolve()
        if stage_dir.parent != stage_root:
            raise UpdateError("A versao tentou sair da pasta de preparacao.")
        if stage_dir.exists():
            meta_existente = stage_dir / "_update_meta.json"
            estado_existente = "PARTIAL"
            if meta_existente.is_file():
                try:
                    estado_existente = str(json.loads(
                        meta_existente.read_text(encoding="utf-8")
                    ).get("state") or "PARTIAL")
                except (OSError, json.JSONDecodeError):
                    estado_existente = "PARTIAL"
            if estado_existente not in {"PARTIAL", "STAGED", "REJECTED"}:
                raise UpdateError(
                    f"Ja existe uma preparacao {estado_existente} para a versao "
                    f"{target_version}. Use uma nova versao para preservar a auditoria."
                )
            shutil.rmtree(stage_dir)
        payload_dir = stage_dir / "payload"
        payload_dir.mkdir(parents=True, exist_ok=True)

        checked: list[dict[str, Any]] = []
        vistos: set[str] = set()
        for entry in files:
            if not isinstance(entry, dict):
                raise UpdateError("Entrada de arquivo invalida no manifesto.")
            rel = _safe_rel(str(entry.get("path", "")))
            chave_windows = rel.casefold()
            if chave_windows in vistos:
                raise UpdateError(f"Caminho repetido no manifesto: {rel}")
            vistos.add(chave_windows)
            member = f"payload/{rel}"
            if member not in names:
                raise UpdateError(f"Arquivo ausente no pacote: {rel}")
            data = zf.read(member)
            digest = hashlib.sha256(data).hexdigest()
            esperado_do_arquivo = _digest_valido(entry.get("sha256"))
            if digest.lower() != esperado_do_arquivo:
                raise UpdateError(f"Falha de integridade em {rel}.")
            target = payload_dir / Path(rel)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            checked.append({"path": rel, "sha256": digest, "bytes": len(data)})

        declarados = {x["path"] for x in checked}
        permitidos = {"update_manifest.json", ASS.NOME_NO_PACOTE} | {
            f"payload/{rel}" for rel in declarados
        }
        extras = sorted(nome for nome in names if nome not in permitidos)
        if extras:
            raise UpdateError(
                "Pacote contem arquivo oculto fora do manifesto: " + extras[0]
            )

        delete_manifesto = manifest.get("delete", [])
        if not isinstance(delete_manifesto, list):
            raise UpdateError("A lista de exclusao do manifesto e invalida.")
        delete_paths = [_safe_rel(str(x)) for x in delete_manifesto]
        if len({p.casefold() for p in delete_paths}) != len(delete_paths):
            raise UpdateError("Manifesto repete caminho na lista de exclusao.")
        sobrepostos = sorted(
            rel for rel in delete_paths if rel.casefold() in vistos
        )
        if sobrepostos:
            raise UpdateError(
                "O mesmo caminho nao pode ser atualizado e excluido: " +
                sobrepostos[0]
            )
        meta = {
            "manifest": manifest,
            "package_sha256": actual_package_hash,
            "assinatura": assinatura,
            "source_commit": str(manifest.get("source_commit") or ""),
            "package_path": str(package.resolve()),
            "checked_files": checked,
            "delete": delete_paths,
            "staged_at": datetime.now().isoformat(timespec="seconds"),
            "state": "STAGED",
        }
        _escrever_json(stage_dir / "_update_meta.json", meta)
        return {**meta, "stage_dir": str(stage_dir), "version": target_version}


def _validar_texto(rel: str, dados: bytes) -> list[str]:
    problemas: list[str] = []
    sufixo = Path(rel).suffix.lower()
    if sufixo not in {".py", ".html", ".js", ".css", ".json", ".txt", ".md"}:
        return problemas
    try:
        texto = dados.decode("utf-8")
    except UnicodeDecodeError:
        return [f"{rel}: arquivo textual nao esta em UTF-8"]
    if sufixo == ".py":
        try:
            ast.parse(texto, filename=rel)
        except SyntaxError as erro:
            problemas.append(
                f"{rel}: erro de sintaxe na linha {erro.lineno or '?'}: {erro.msg}"
            )
    elif sufixo == ".json":
        try:
            json.loads(texto)
        except json.JSONDecodeError as erro:
            problemas.append(f"{rel}: JSON invalido na linha {erro.lineno}")
    elif sufixo == ".html":
        posicao = 0
        aberturas = {"{{": "}}", "{%": "%}", "{#": "#}"}
        nomes = {"{{": "expressao", "{%": "bloco", "{#": "comentario"}
        while posicao < len(texto):
            proximos = [
                (texto.find(abertura, posicao), abertura)
                for abertura in aberturas
            ]
            proximos = [(indice, abertura) for indice, abertura in proximos
                        if indice >= 0]
            if not proximos:
                break
            inicio, abertura = min(proximos)
            fechamento = aberturas[abertura]
            fim = texto.find(fechamento, inicio + len(abertura))
            if fim < 0:
                problemas.append(
                    f"{rel}: delimitador de {nomes[abertura]} nao foi fechado"
                )
                break
            conteudo = texto[inicio + len(abertura):fim].strip().lower()
            posicao = fim + len(fechamento)
            if abertura == "{%" and conteudo.split(None, 1)[:1] == ["raw"]:
                fim_raw = re.search(r"\{%\s*endraw\s*%\}", texto[posicao:], re.I)
                if not fim_raw:
                    problemas.append(f"{rel}: bloco raw nao foi fechado")
                    break
                posicao += fim_raw.end()
    return problemas


def _versao_de_app_py(dados: bytes) -> str:
    try:
        arvore = ast.parse(dados.decode("utf-8"), filename="app.py")
    except (UnicodeDecodeError, SyntaxError):
        return ""
    for no in arvore.body:
        if not isinstance(no, (ast.Assign, ast.AnnAssign)):
            continue
        alvos = no.targets if isinstance(no, ast.Assign) else [no.target]
        valor = no.value
        if (any(isinstance(alvo, ast.Name) and alvo.id == "VERSION"
                for alvo in alvos)
                and isinstance(valor, ast.Constant)
                and isinstance(valor.value, str)):
            return valor.value.strip()
    return ""


def _explicar_falha_na_copia(erro: Exception) -> str:
    """Uma frase em portugues no lugar da lista de tuplas do `shutil`.

    O `shutil.Error` carrega uma LISTA de tuplas — `[('origem', 'destino',
    '[WinError 5] Acesso negado: ...')]` — e ela ia inteira para o `flash`:
    quem clicasse em «validar e preparar» lia isso na cara. A pergunta que
    aquela mensagem tem de responder nao e tecnica — e «quebrou o sistema, ou
    so nao deu para ler um arquivo?». Aqui, as duas coisas sao diferentes: a
    pasta de preparacao e descartada e **nada muda no sistema**.
    """
    itens = erro.args[0] if erro.args else None
    if (
        isinstance(itens, list)
        and itens
        and isinstance(itens[0], tuple)
        and len(itens[0]) >= 3
    ):
        origem, motivo = itens[0][0], itens[0][2]
        return (
            f"Nao deu para montar a atualizacao: a copia parou em "
            f"{Path(str(origem)).name} ({motivo}). NADA mudou no sistema — a "
            "pasta de preparacao foi descartada e o sistema continua rodando o "
            "que ja estava. Confira se a conta que roda o servidor consegue ler "
            "essa pasta, e prepare de novo."
        )
    return (
        "Nao deu para montar a atualizacao: a copia da instalacao para a pasta "
        "de preparacao falhou. NADA mudou no sistema. Confira o espaco em disco "
        "e as permissoes da pasta da instalacao, e prepare de novo."
    )


def inspect_staged(stage_dir: Path, install_dir: Path) -> dict[str, Any]:
    """Monta uma copia candidata e a confere sem executar o codigo recebido."""
    stage_dir = Path(stage_dir).resolve()
    install_dir = Path(install_dir).resolve()
    if not install_dir.is_dir():
        raise UpdateError("A pasta da instalacao nao foi localizada.")
    if stage_dir == install_dir or stage_dir.is_relative_to(install_dir):
        raise UpdateError(
            "A pasta de preparacao deve ficar fora da pasta da instalacao."
        )
    meta_path = stage_dir / "_update_meta.json"
    if not meta_path.is_file():
        raise UpdateError("Preparacao sem metadados de atualizacao.")
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    if meta.get("state") != "STAGED":
        raise UpdateError("Esta preparacao ja foi inspecionada ou aprovada.")
    payload = stage_dir / "payload"
    candidato = stage_dir / "candidate"
    if candidato.exists():
        shutil.rmtree(candidato)

    def ignorar(_pasta: str, nomes: list[str]) -> set[str]:
        ignoradas = {nome.casefold() for nome in PASTAS_IGNORADAS_NA_COPIA}
        return {nome for nome in nomes if nome.casefold() in ignoradas}

    try:
        shutil.copytree(install_dir, candidato, ignore=ignorar)
    except (shutil.Error, OSError) as erro:
        # Ver `_explicar_falha_na_copia`: o `shutil.Error` traz uma LISTA, e ela
        # ia crua para a tela. Aqui ela vira frase, e a frase diz o que mais
        # importa a quem clicou: o sistema nao mudou.
        shutil.rmtree(candidato, ignore_errors=True)
        raise UpdateError(_explicar_falha_na_copia(erro)) from erro
    impacto: list[dict[str, Any]] = []
    problemas: list[str] = []
    avisos: list[str] = []

    # O QUE A TELA DIZ DA ASSINATURA SAI DE UMA CONFERÊNCIA FEITA AGORA, contra
    # o pacote — e não da palavra gravada no meta na hora do upload (revisão
    # de 22/10/2026, C1). Se não confere, a preparação é RECUSADA.
    try:
        assinatura_agora = reconferir_contra_o_pacote(meta, stage_dir)[
            "assinatura"]
    except UpdateError as erro:
        problemas.append(f"Conferencia do pacote assinado: {erro}")
        assinatura_agora = {"situacao": "NAO_CONFERIDA",
                            "observacao": str(erro)}
    meta["assinatura"] = assinatura_agora

    for item in meta.get("checked_files", []):
        rel = _safe_rel(item.get("path", ""))
        origem = payload / Path(rel)
        destino = candidato / Path(rel)
        if not origem.is_file():
            problemas.append(f"{rel}: sumiu da pasta preparada")
            continue
        dados = origem.read_bytes()
        digest = hashlib.sha256(dados).hexdigest()
        if digest != item.get("sha256"):
            problemas.append(f"{rel}: foi alterado depois da preparacao")
            continue
        anterior = install_dir / Path(rel)
        estado = "NOVO"
        sha_anterior = ""
        if anterior.is_file():
            sha_anterior = sha256_file(anterior)
            estado = "IGUAL" if sha_anterior == digest else "ALTERADO"
        destino.parent.mkdir(parents=True, exist_ok=True)
        destino.write_bytes(dados)
        critico = rel.casefold() in {p.casefold() for p in CAMINHOS_CRITICOS}
        impacto.append({
            "path": rel, "status": estado, "bytes": len(dados),
            "sha256": digest, "previous_sha256": sha_anterior,
            "critical": critico,
        })
        if critico and estado != "IGUAL":
            avisos.append(f"Arquivo critico alterado: {rel}")
        problemas.extend(_validar_texto(rel, dados))

    # O PACOTE NÃO APAGA CALADO O CONSERTO FEITO POR FORA — 14/10/2026.
    # Arquivo instalado que mudou depois da última atualização (cópia direta)
    # e que o pacote substituiria por outra coisa é BLOQUEIO: o conserto da
    # produção não chegou ao INSTALAR, e se perderia. Ver retrato_da_instalacao.
    conflitos: list[dict[str, Any]] = []
    try:
        import retrato_da_instalacao as RET
        versao_instalada = ""
        versao_txt = install_dir / "VERSAO.txt"
        if versao_txt.is_file():
            versao_instalada = versao_txt.read_text(encoding="utf-8").strip()
        if not versao_instalada and (install_dir / "app.py").is_file():
            versao_instalada = _versao_de_app_py((install_dir / "app.py").read_bytes())
        if versao_instalada:
            conflitos = RET.conflitos_do_pacote(
                stage_dir.parent.parent, install_dir, versao_instalada,
                {i["path"]: i["sha256"] for i in meta.get("checked_files", [])})
    except (OSError, ValueError, KeyError) as erro:
        avisos.append(f"A conferência do retrato da instalação não rodou: {erro}")
    if conflitos:
        nomes = ", ".join(c["path"] for c in conflitos[:8])
        problemas.append(
            f"{len(conflitos)} arquivo(s) da produção foram mudados depois da "
            f"última atualização e este pacote os sobrescreveria: {nomes}"
            + ("…" if len(conflitos) > 8 else "")
            + ". Leve a mudança ao INSTALAR e gere o pacote de novo — ou, se "
              "ela deve mesmo ser descartada, aceite o estado instalado nesta "
              "tela, com o motivo, e prepare de novo.")

    for rel in meta.get("delete", []):
        alvo = candidato / Path(_safe_rel(rel))
        if alvo.is_dir():
            shutil.rmtree(alvo)
        elif alvo.exists():
            alvo.unlink()
        impacto.append({"path": rel, "status": "EXCLUIDO", "critical": True})
        avisos.append(f"Exclusao solicitada: {rel}")

    if bool((meta.get("manifest") or {}).get("run_pip")):
        requisitos = candidato / "requirements.txt"
        if not requisitos.is_file():
            problemas.append(
                "O pacote pede sincronizacao de dependencias, mas nao contem "
                "requirements.txt no candidato."
            )
        else:
            avisos.append(
                "O pacote pede sincronizacao de dependencias Python durante a aplicacao."
            )

    versao = str((meta.get("manifest") or {}).get("version") or "")
    versao_arquivo = candidato / "VERSAO.txt"
    if not versao_arquivo.is_file():
        problemas.append("O candidato nao contem VERSAO.txt.")
    else:
        declarada = versao_arquivo.read_text(encoding="utf-8", errors="replace").strip()
        if declarada != versao:
            problemas.append(
                f"VERSAO.txt declara {declarada or 'vazio'}, mas o pacote declara {versao}."
            )
    app_candidato = candidato / "app.py"
    if not app_candidato.is_file():
        problemas.append("O candidato nao contem app.py.")
    else:
        versao_app = _versao_de_app_py(app_candidato.read_bytes())
        if versao_app != versao:
            problemas.append(
                f"app.py declara {versao_app or 'versao ausente'}, mas o pacote "
                f"declara {versao}."
            )

    inspecao = {
        "ok": not problemas,
        "executed_code": False,
        "impact": impacto,
        "problems": problemas,
        "warnings": avisos,
        "candidate_dir": str(candidato),
        "inspected_at": datetime.now().isoformat(timespec="seconds"),
        "validation_claim": (meta.get("manifest") or {}).get("validation") or {},
        # quem fez o pacote e de que estado do git ele saiu (12/10/2026)
        "assinatura": assinatura_agora,
        "source_commit": str((meta.get("manifest") or {}).get("source_commit") or ""),
        "conflitos": conflitos,
    }
    meta["inspection"] = inspecao
    meta["state"] = "READY_FOR_APPROVAL" if inspecao["ok"] else "REJECTED"
    _escrever_json(meta_path, meta)
    return inspecao


def reconferir_contra_o_pacote(meta: dict[str, Any],
                               stage_dir: Path) -> dict[str, Any]:
    """Reabre o `.cgu` e confere, NA HORA, a assinatura e cada hash. Só lê.

    A PREPARAÇÃO NÃO É PROVA (revisão de segurança da 3.7.0, 22/10/2026,
    achado C1). A pasta `updates/staged` e o `_update_meta.json` são arquivos
    do disco: quem puder escrever ali troca um `.py` do payload e reescreve o
    hash — e a palavra «ASSINADO» — no meta. Até aqui a assinatura Ed25519 só
    era conferida no upload (`validate_and_stage`); a tela, a aprovação e o
    `aplicar_atualizacao.ps1` liam o meta e acreditavam nele.

    Agora a inspeção e a aprovação reabrem o PACOTE ORIGINAL: a assinatura do
    manifesto é conferida de novo contra as chaves de hoje, e cada arquivo da
    preparação é comparado ao hash que o MANIFESTO ASSINADO declara — e não ao
    que o meta diz. Arquivo a mais no payload é recusa: o `ps1` copia a pasta
    inteira, e um `.pth` plantado ali iria para a instalação sem conferência.

    Devolve `{"assinatura", "manifest"}` lidos do pacote. Recusa quando o
    pacote sumiu ou mudou, quando a assinatura não confere, quando o manifesto
    da preparação não é o do pacote, e quando a preparação difere dele.
    """
    import assinatura_da_atualizacao as ASS
    pacote = Path(str(meta.get("package_path") or ""))
    if not pacote.is_file():
        raise UpdateError(
            "O pacote original nao foi localizado para a conferencia final.")
    if sha256_file(pacote) != str(meta.get("package_sha256") or ""):
        raise UpdateError("O pacote original mudou depois da preparacao.")
    with zipfile.ZipFile(pacote, "r") as zf:
        nomes = set(zf.namelist())
        if "update_manifest.json" not in nomes:
            raise UpdateError("Pacote sem update_manifest.json.")
        manifesto_bytes = zf.read("update_manifest.json")
        try:
            assinatura = ASS.conferir(
                manifesto_bytes,
                zf.read(ASS.NOME_NO_PACOTE) if ASS.NOME_NO_PACOTE in nomes
                else None)
        except ASS.AssinaturaRecusada as exc:
            raise UpdateError(str(exc)) from exc
    try:
        manifesto = json.loads(manifesto_bytes.decode("utf-8"))
    except Exception as exc:
        raise UpdateError("Manifesto de atualizacao invalido.") from exc
    if manifesto != meta.get("manifest"):
        raise UpdateError(
            "O manifesto da preparacao nao e o do pacote assinado.")
    declarados: dict[str, str] = {}
    for entry in manifesto.get("files") or []:
        if not isinstance(entry, dict):
            raise UpdateError("Entrada de arquivo invalida no manifesto.")
        declarados[_safe_rel(str(entry.get("path", "")))] = _digest_valido(
            entry.get("sha256"))
    payload = Path(stage_dir) / "payload"
    no_disco: dict[str, str] = {}
    if payload.is_dir():
        for caminho in payload.rglob("*"):
            if caminho.is_file():
                no_disco[caminho.relative_to(payload).as_posix()] = (
                    sha256_file(caminho))
    conhecidos = {rel.casefold() for rel in declarados}
    a_mais = sorted(rel for rel in no_disco if rel.casefold() not in conhecidos)
    if a_mais:
        raise UpdateError(
            "A preparacao contem arquivo que o manifesto assinado nao "
            f"declara: {a_mais[0]}")
    for rel, digest in declarados.items():
        if no_disco.get(rel) != digest:
            raise UpdateError(
                f"A preparacao foi alterada depois da conferencia: {rel}")
    # O `ps1` lê `checked_files` do meta: ele tem de ser o que o manifesto
    # assinado declara, nem mais nem menos.
    conferidos = {}
    for item in meta.get("checked_files") or []:
        if isinstance(item, dict):
            conferidos[_safe_rel(str(item.get("path", "")))] = str(
                item.get("sha256") or "").strip().lower()
    if conferidos != declarados:
        raise UpdateError(
            "Os metadados da preparacao nao batem com o manifesto assinado.")
    return {"assinatura": assinatura, "manifest": manifesto}


def load_staged(stage_dir: Path) -> dict[str, Any]:
    stage_dir = Path(stage_dir).resolve()
    meta_path = stage_dir / "_update_meta.json"
    if not meta_path.is_file():
        raise UpdateError("Atualizacao preparada nao encontrada.")
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as erro:
        raise UpdateError("Metadados da atualizacao preparada estao ilegíveis.") from erro
    meta["stage_dir"] = str(stage_dir)
    meta["version"] = str((meta.get("manifest") or {}).get("version") or "")
    return meta


def revalidate_staged(stage_dir: Path) -> dict[str, Any]:
    """Confere novamente cada byte imediatamente antes da aprovacao."""
    meta = load_staged(stage_dir)
    if meta.get("state") != "READY_FOR_APPROVAL":
        raise UpdateError("A atualizacao nao esta pronta para aprovacao.")
    payload = Path(stage_dir) / "payload"
    for item in meta.get("checked_files", []):
        caminho = payload / Path(_safe_rel(item.get("path", "")))
        if not caminho.is_file() or sha256_file(caminho) != item.get("sha256"):
            raise UpdateError(
                f"A preparacao foi alterada depois da conferencia: {item.get('path')}"
            )
    # A ASSINATURA E OS HASHES SÃO RECONFERIDOS AQUI, CONTRA O PACOTE — e não
    # lidos do meta (revisão de 22/10/2026, C1). É esta chamada que a
    # aprovação (`mark_approved`) atravessa.
    meta["assinatura"] = reconferir_contra_o_pacote(
        meta, Path(stage_dir))["assinatura"]
    inspecao = meta.get("inspection") or {}
    if not inspecao.get("ok") or inspecao.get("executed_code") is not False:
        raise UpdateError("A inspecao estatica da atualizacao nao e valida.")
    return meta


def mark_approved(stage_dir: Path, *, approved_by: str, approved_at: str,
                  backup: str) -> dict[str, Any]:
    meta = revalidate_staged(stage_dir)
    if not str(approved_by or "").strip():
        raise UpdateError("A aprovacao precisa identificar o administrador.")
    caminho_backup = Path(str(backup or ""))
    if not caminho_backup.is_file() or caminho_backup.stat().st_size <= 0:
        raise UpdateError("O backup previo obrigatorio nao foi localizado.")
    meta["state"] = "APPROVED"
    meta["approved_by"] = str(approved_by or "")
    meta["approved_at"] = str(approved_at or "")
    meta["backup"] = str(backup or "")
    _escrever_json(Path(stage_dir) / "_update_meta.json", meta)
    return meta


def installed_app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


def _conta_atual() -> str:
    """Quem somos, para a frase de recusa dizer quem procurar.

    Nao se usa `getpass` de proposito: dentro de um servico do Windows ele devolve o
    nome do servico em algumas configuracoes, e a frase que o oficial le tem de nomear
    uma conta que existe.
    """
    for chave in ("USERNAME", "USER"):
        valor = (os.environ.get(chave) or "").strip()
        if valor:
            return valor
    return "a conta que roda o sistema"


def _mesmo_caminho(um: str | Path, outro: str | Path) -> bool:
    """Compara dois caminhos do Windows como o Windows os compara.

    `C:\\Program Files\\CartorioGestao` e `c:/program files/cartoriogestao/` sao a mesma
    pasta, e comparar as duas strings diria que nao sao: **duas reguas para a mesma
    medida**, na forma que este projeto ja pagou caro varias vezes.
    """
    try:
        a = os.path.normcase(os.path.abspath(str(um)))
        b = os.path.normcase(os.path.abspath(str(outro)))
    except (OSError, ValueError):
        return False
    return a.rstrip("\\/") == b.rstrip("\\/")


def instalacao_declarada(data_dir: Path | None) -> str:
    """A pasta que esta instalacao diz ser a dela, lida do `install.json` — ou vazio."""
    if data_dir is None:
        return ""
    caminho = Path(data_dir) / "install.json"
    if not caminho.is_file():
        return ""
    try:
        dados = json.loads(caminho.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    if not isinstance(dados, dict):
        return ""
    return str(dados.get("install_dir") or "").strip()


def pode_escrever_na_instalacao(install_dir: Path | None = None) -> tuple[bool, str]:
    """Mede se ESTE processo consegue gravar na pasta do programa. Devolve (pode, motivo).

    **A PERGUNTA «POSSO APLICAR A ATUALIZACAO?» SE RESPONDE MEDINDO, E NAO SUPONDO** —
    medido em 15/09/2026. A tela respondia «sim» por sinais que nada provam sobre
    permissao (estar no Windows, existir `install.json`, o pacote estar preparado), e uma
    instancia rodando em `C:\\Program Files\\CartorioGestao` sob conta sem permissao
    mandava aplicar: o `robocopy` morria com **«Acesso negado.»** — treze caracteres, sem
    dizer qual pasta nem o que fazer — **depois** de o servico ter sido parado. O balcao
    caia para descobrir que nao dava.

    A prova e a unica que nao mente: **criar um arquivo e apagar**. Nao se pergunta ao
    sistema de arquivos o que ele acha; escreve-se.
    """
    pasta = Path(install_dir) if install_dir is not None else installed_app_dir()
    if not sys.platform.startswith("win"):
        return False, (
            "A aplicacao automatica so existe na instalacao convencional do Windows. "
            "Aqui da para preparar e revisar o pacote; quem aplica e o "
            "ATUALIZAR_SISTEMA.cmd."
        )
    if not pasta.is_dir():
        return False, f"A pasta do programa nao foi encontrada em {pasta}."
    pista = pasta / f".teste_de_escrita_{os.getpid()}.tmp"
    try:
        pista.write_bytes(b"")
    except OSError:
        return False, (
            f"A conta «{_conta_atual()}» nao pode gravar em {pasta}, que e onde esta "
            "instalado o programa. Para aplicar a atualizacao e preciso permissao nessa "
            "pasta: use o ATUALIZAR_SISTEMA.cmd (ele pede a permissao ao Windows) ou "
            "aplique pelo sistema do servidor, que roda como servico."
        )
    finally:
        try:
            pista.unlink()
        except OSError:
            pass
    return True, ""


def pode_aplicar_sozinho(data_dir: Path | None = None,
                         install_dir: Path | None = None) -> tuple[bool, str]:
    """A regua UNICA de «esta instalacao aplica a atualizacao sozinha»: (pode, motivo).

    Sao tres perguntas, nesta ordem, e cada uma tem a sua frase **porque o conserto de
    cada uma e diferente** — e e isso que faz a recusa servir para alguma coisa:

    1. **e uma instalacao de Windows?** Sem isso nao existe tarefa agendada nem servico.
    2. **o programa que roda e o da instalacao?** O `install.json` diz qual pasta e a
       instalacao. **Rodar de outra copia nao e detalhe:** ela aplicaria a atualizacao na
       pasta errada e **relataria sucesso** — carimbo que mente no pior lugar, porque
       quem le a tela conclui que o servidor subiu.
    3. **esta conta pode gravar la?** Medido, com um arquivo de teste.

    **UMA REGUA SO, E POR ISSO ELA MORA AQUI.** A tela pergunta isto para decidir se
    oferece o botao; a rota pergunta de novo, imediatamente antes de aprovar, porque e
    ela que derruba o balcao; e o lancador pergunta uma terceira vez, porque a partir
    dali nao ha mais quem recuse. Escritas tres vezes, divergiriam no primeiro conserto.
    """
    pasta = Path(install_dir) if install_dir is not None else installed_app_dir()
    if not sys.platform.startswith("win"):
        return False, (
            "A aplicacao automatica so existe na instalacao convencional do Windows. "
            "Aqui da para preparar e revisar o pacote; quem aplica e o "
            "ATUALIZAR_SISTEMA.cmd."
        )
    if data_dir is not None:
        declarada = instalacao_declarada(data_dir)
        if not declarada:
            return False, (
                f"Nao encontrei o install.json desta instalacao em "
                f"{Path(data_dir) / 'install.json'} — sem ele nao ha como saber qual "
                "pasta e a instalacao. Para aplicar esta atualizacao use o "
                "ATUALIZAR_SISTEMA.cmd, que pede a permissao ao Windows."
            )
        if not _mesmo_caminho(declarada, pasta):
            return False, (
                f"Esta copia do sistema nao e a instalada: ela roda de {pasta}, e a "
                f"instalacao e {declarada}. Aplicar daqui trocaria os arquivos de "
                f"{pasta} e o servidor continuaria como esta, sem erro nenhum. Aplique "
                "pela tela de atualizacoes do sistema do servidor, ou pelo "
                "ATUALIZAR_SISTEMA.cmd."
            )
    return pode_escrever_na_instalacao(pasta)


def launch_windows_updater(stage_dir: Path, data_dir: Path, parent_pid: int, port: int = 8765, task_name: str = "CartorioGestaoServidor") -> None:
    if not sys.platform.startswith("win"):
        raise UpdateError("Aplicacao automatica de atualizacao so esta disponivel no Windows instalado.")
    install_dir = installed_app_dir()
    script = install_dir / "installer" / "aplicar_atualizacao.ps1"
    if not script.exists():
        raise UpdateError("Componente de atualizacao da instalacao nao foi encontrado.")
    # A ULTIMA PORTA, E A UNICA QUE NAO TEM QUEM RECUSE DEPOIS DELA: daqui para a frente
    # o servico e parado e os arquivos sao trocados. A rota ja perguntou o mesmo e
    # respondeu que sim — perguntar de novo custa um arquivo de teste e evita derrubar o
    # balcao por um caminho que mudou entre a tela e o clique.
    pode, motivo = pode_aplicar_sozinho(data_dir, install_dir)
    if not pode:
        raise UpdateError(motivo)
    creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
    subprocess.Popen(
        [
            "powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script),
            "-InstallDir", str(install_dir), "-StageDir", str(stage_dir), "-DataDir", str(data_dir),
            "-TaskName", task_name, "-ParentPid", str(parent_pid), "-Port", str(int(port)),
        ],
        close_fds=True,
        creationflags=creationflags,
    )
