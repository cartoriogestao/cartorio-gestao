"""
Leitura da pasta das matriculas digitadas em Word.

POR QUE ESTE MODULO EXISTE
    Ate 14/08/2026 os arquivos estavam numa pasta sincronizada em modo "sob demanda":
    de fora da maquina da serventia so o nome e o tamanho apareciam, e a
    extracao tinha de rodar la, por PowerShell. A pasta baixou por inteiro, e
    a leitura passou a ser um processo comum do sistema — um botao, sem script
    solto e sem depender de quem lembra de executa-lo.

O QUE ELE FAZ
    1. varre a pasta e tira de cada nome de arquivo o numero da matricula;
    2. quando ha varias versoes do mesmo numero, escolhe uma e diz por que;
    3. le o texto de cada arquivo e grava `matriculas_doc.jsonl`.

    A conferencia contra o acervo NAO acontece aqui — e do `ri_doc`.

O QUE ELE NAO FAZ
    Nao decide nada de registral. So le arquivo e organiza o que achou. O que
    entra no livro depende do registrador.

SOBRE O .doc ANTIGO
    O formato binario do Word 97 nao se le sem conversor. Havendo LibreOffice
    na maquina, o modulo converte para .docx numa pasta temporaria e le dali.
    Nao havendo, os .doc ficam marcados como pendentes e o resto segue — meia
    leitura e melhor do que nenhuma, desde que o relatorio diga quais faltaram.
"""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import unicodedata
import zipfile
from pathlib import Path

# Maior matricula do acervo e 4013. O teto evita ler "Lei 8.935" como
# matricula 8935 e a data "2023" como matricula 2023.
LIMITE_NUMERO = 4100

EXTENSOES = (".docx", ".doc", ".rtf")

# O numero pode vir de varios jeitos no nome do arquivo. A ordem importa: o
# primeiro padrao que casar decide.
PADROES = (
    # "MATRICULA 218", "MATRÍCULA Nº 3", "MATRICULA NOVA 3980", "Mat. 1.771"
    r"^\s*(?:nova\s+)?mat(?:r[ií]cula)?\.?\s*(?:nova\s*)?(?:n[ºo°]\.?\s*)?[-–]?\s*"
    r"(\d{1,3}(?:\.\d{3})+|\d{1,5})\b",
    # "Mt 851", "mt 1342"
    r"^\s*mt\.?\s*(\d{1,3}(?:\.\d{3})+|\d{1,5})\b",
    # "1085 - PREFEITURA", "099- SEM EFEITO", "1.771 - Gumercindo"
    r"^\s*(\d{1,3}(?:\.\d{3})+|\d{1,5})\b",
    # "1418ANASTACIO" — numero colado no nome
    r"^\s*(\d{2,5})(?=[A-Za-zÁ-Úá-ú])",
)

# Nomes que denunciam que o arquivo NAO e matricula, ainda que tragam numero.
# "Artigo 26 da Lei nº 8" foi lido como matricula 26 na primeira passada.
NAO_E_MATRICULA = ("artigo", "lei n", "modelo de", "termo de abertura",
                   "termo de encerramento", "anexo", "minuta", "oficio")

SOFFICE = ("soffice", r"C:\Program Files\LibreOffice\program\soffice.exe",
           r"C:\Program Files (x86)\LibreOffice\program\soffice.exe")


def _sem_acento(t: str) -> str:
    t = unicodedata.normalize("NFD", t.lower())
    return "".join(c for c in t if unicodedata.category(c) != "Mn")


def numero_do_nome(nome: str) -> tuple[int | None, str]:
    """Devolve (numero, como_achou) ou (None, motivo).

    O nome vem da nuvem e chega com o acento ora composto ora decomposto
    (NFC x NFD). Sem normalizar, "MATRÍCULA NOVA 3980" escapa do padrao — foi
    exatamente o que aconteceu na primeira leitura.
    """
    base = unicodedata.normalize("NFC", re.sub(r"\.[^.]*$", "", nome))
    seco = _sem_acento(base)
    for p in PADROES:
        m = re.match(p, base, re.I)
        if m:
            n = int(m.group(1).replace(".", ""))
            if 1 <= n <= LIMITE_NUMERO:
                return n, "padrao"
    if any(t in seco for t in NAO_E_MATRICULA):
        return None, "nao_e_matricula"
    # Ultimo recurso: um unico numero plausivel no meio do nome. Havendo dois,
    # nao adivinha — "Artigo 26 da Lei no 8" nao e matricula 26 nem 8.
    achados = {int(x.replace(".", ""))
               for x in re.findall(r"\b(\d{1,3}(?:\.\d{3})+|\d{1,4})\b", base)}
    achados = {n for n in achados if 1 <= n <= LIMITE_NUMERO}
    if len(achados) == 1:
        return achados.pop(), "unico_no_nome"
    return None, ("ambiguo" if achados else "sem_numero")


def pontos(nome: str, tamanho: int) -> int:
    """Qual versao vale quando ha varias do mesmo numero.

    "ATUALIZADA" e a versao que o registrador refez: ganha do original.
    "Copia em conflito" e ramo morto do sincronismo da nuvem, nao versao do
    registrador. "SEM EFEITO" e matricula cancelada — so entra se for a unica.
    O .docx ganha do .doc porque sai sem passar por conversor.
    """
    b = _sem_acento(nome)
    p = 0
    if b.endswith(".docx"):
        p += 100
    if re.match(r"^\s*\d+\s*\.docx?$", b):
        p += 10
    if "atualiz" in b:
        p += 120
    if re.search(r"edit[aá]vel|editavel", b):
        p += 20
    if "copia em conflito" in b:
        p -= 150
    if "sem efeito" in b:
        p -= 200
    p += min(tamanho // 1000, 60)
    return p


def texto_docx(caminho: Path) -> str:
    """Paragrafo a paragrafo, do word/document.xml. Sem biblioteca externa."""
    with zipfile.ZipFile(caminho) as z:
        try:
            xml = z.read("word/document.xml").decode("utf-8", "replace")
        except KeyError:
            return ""
    partes = []
    for par in re.findall(r"<w:p[ >].*?</w:p>", xml, re.S):
        # tabulacao e quebra viram espaco, senao as palavras colam
        par = re.sub(r"<w:(?:tab|br)\s*/>", " ", par)
        t = "".join(re.findall(r"<w:t[^>]*>(.*?)</w:t>", par, re.S))
        t = (t.replace("&amp;", "&").replace("&lt;", "<").replace("&gt;", ">")
              .replace("&quot;", '"').replace("&apos;", "'"))
        if t.strip():
            partes.append(t.strip())
    return "\n".join(partes)


def texto_rtf(caminho: Path) -> str:
    """RTF sem biblioteca: desfaz os escapes e joga fora o comando."""
    bruto = caminho.read_bytes().decode("latin-1", "replace")
    bruto = re.sub(r"\\'([0-9a-fA-F]{2})",
                   lambda m: bytes([int(m.group(1), 16)]).decode("latin-1"), bruto)
    bruto = re.sub(r"\\par[d]?\b", "\n", bruto)
    bruto = re.sub(r"\{\\\*.*?\}", "", bruto, flags=re.S)
    bruto = re.sub(r"\\[a-zA-Z]+-?\d*\s?", "", bruto)
    bruto = bruto.replace("{", "").replace("}", "")
    return "\n".join(l.strip() for l in bruto.split("\n") if l.strip())


def achar_soffice() -> str | None:
    for c in SOFFICE:
        achado = shutil.which(c) if os.sep not in c else (c if Path(c).exists() else None)
        if achado:
            return achado
    return None


def escolher(pasta: Path):
    """Percorre a pasta e devolve (escolhidos, todos_os_candidatos, descartes).

    `escolhidos` e {numero: (caminho, como, bytes)}; `candidatos` guarda TODAS
    as versoes de cada numero, para que a tela possa dizer que havia outra e
    qual foi preterida — decisao de acervo nao pode acontecer em silencio.
    """
    candidatos: dict[int, list[tuple[Path, str, int]]] = {}
    descartes: list[dict] = []
    for f in sorted(pasta.iterdir()):
        if not f.is_file() or f.suffix.lower() not in EXTENSOES:
            continue
        n, como = numero_do_nome(f.name)
        if not n:
            descartes.append({"arquivo": f.name, "motivo": como})
            continue
        try:
            tam = f.stat().st_size
        except OSError:
            tam = 0
        candidatos.setdefault(n, []).append((f, como, tam))

    escolhidos: dict[int, tuple[Path, str, int]] = {}
    for n, versoes in candidatos.items():
        # Desempate explicito: pontuacao, depois tamanho, depois nome. Sem a
        # segunda e a terceira chave, dois arquivos com a mesma pontuacao eram
        # decididos pela ordem em que o sistema de arquivos os devolvesse — a
        # matricula 3769 mudou de versao entre duas leituras da mesma pasta.
        escolhidos[n] = max(versoes,
                            key=lambda v: (pontos(v[0].name, v[2]), v[2], v[0].name))
    return escolhidos, candidatos, descartes


def extrair(pasta: str | Path, destino: str | Path,
            progresso=None, converter_doc: bool = True) -> dict:
    """Le a pasta inteira e grava o JSONL. Devolve o resumo do que aconteceu.

    `progresso` e uma funcao opcional chamada com (feitos, total) — serve para
    a tela nao ficar muda durante uma leitura de tres mil arquivos.
    """
    pasta, destino = Path(pasta), Path(destino)
    if not pasta.is_dir():
        raise FileNotFoundError(f"pasta nao encontrada: {pasta}")

    escolhidos, candidatos, descartes = escolher(pasta)
    total = len(escolhidos)
    soffice = achar_soffice() if converter_doc else None
    convertidos: dict[int, Path] = {}
    temporaria = None

    docs = {n: v for n, v in escolhidos.items() if v[0].suffix.lower() == ".doc"}
    if docs and soffice:
        temporaria = Path(tempfile.mkdtemp(prefix="matdoc_"))
        entrada, saida = temporaria / "in", temporaria / "out"
        entrada.mkdir(); saida.mkdir()
        for n, (caminho, _, _) in docs.items():
            # renomeia para o numero: o LibreOffice devolve pelo nome do
            # arquivo, e nome com acento ou parentese se perde no caminho
            shutil.copyfile(caminho, entrada / f"{n}.doc")
        # em lotes: a fila inteira de uma vez estoura o tempo do conversor
        arquivos = sorted(entrada.glob("*.doc"))
        for i in range(0, len(arquivos), 200):
            lote = [str(a) for a in arquivos[i:i + 200]]
            try:
                subprocess.run([soffice, "--headless", "--convert-to", "docx",
                                "--outdir", str(saida), *lote],
                               capture_output=True, timeout=1800, check=False)
            except (subprocess.TimeoutExpired, OSError):
                pass
        for n in docs:
            p = saida / f"{n}.docx"
            if p.exists():
                convertidos[n] = p

    resumo = {"pasta": str(pasta), "arquivos_lidos": 0, "sem_texto": 0,
              "doc_convertidos": len(convertidos),
              "doc_pendentes": len(docs) - len(convertidos),
              "descartados": len(descartes), "numeros": total,
              "libreoffice": bool(soffice)}

    with open(destino, "w", encoding="utf-8") as fh:
        for i, n in enumerate(sorted(escolhidos), 1):
            caminho, como, tam = escolhidos[n]
            ext = caminho.suffix.lower()
            texto, erro = "", None
            try:
                if ext == ".docx":
                    texto = texto_docx(caminho)
                elif ext == ".rtf":
                    texto = texto_rtf(caminho)
                elif n in convertidos:
                    texto = texto_docx(convertidos[n])
                else:
                    erro = "LibreOffice indisponivel para ler .doc"
            except Exception as e:                      # noqa: BLE001
                erro = f"{type(e).__name__}: {e}"
            if len(texto.strip()) < 40:
                resumo["sem_texto"] += 1
            resumo["arquivos_lidos"] += 1
            fh.write(json.dumps({
                "numero": n, "arquivo": caminho.name, "como": como,
                "ext": ext.lstrip("."), "bytes": tam,
                "alterado": _quando(caminho),
                "versoes": len(candidatos[n]),
                "outras": [v[0].name for v in candidatos[n] if v[0] != caminho],
                "texto": texto, "erro": erro,
            }, ensure_ascii=False) + "\n")
            if progresso and i % 100 == 0:
                progresso(i, total)

    if temporaria:
        shutil.rmtree(temporaria, ignore_errors=True)
    destino.with_suffix(".descartados.json").write_text(
        json.dumps(descartes, ensure_ascii=False, indent=1), encoding="utf-8")
    resumo["destino"] = str(destino)
    return resumo


def _quando(caminho: Path) -> str | None:
    try:
        from datetime import datetime
        return datetime.fromtimestamp(caminho.stat().st_mtime).strftime("%Y-%m-%d")
    except OSError:
        return None
