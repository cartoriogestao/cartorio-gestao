"""O agente do malote — agente 13, pedido do oficial em 11/10/2026.

    «Agente malote: esse agente sera responsavel por acessar o malote digital e
     baixar e fazer a triagem dos recebidos no malote para o sistema.»

O QUE SE MEDIU ANTES DE ESCREVER (11/10/2026, produção só lida, antes das 14h36)
    - 31 expedientes no sistema, 30 deles do Malote Digital, TODOS cadastrados à
      mão (28 pela mesma escrevente). O assunto é colado da lista do malote, com a quebra
      de linha dela dentro («AT IVIDA», «CIRCUL AR»).
    - A equipe baixa o PDF do malote e o salva no Proton, em «6. MALOTE DIGITAL».
      Existe ali uma subpasta «PARA CADASTRAR»: o que ainda não entrou no
      sistema. Nela havia DOIS arquivos parados desde 23/09/2026 — um deles uma
      decisão de divórcio para averbar no nascimento (RCPN), dezoito dias fora do
      sistema e sem tarefa.
    - Dos 34 PDFs salvos no Proton desde 10/09, 21 estão no sistema (o sha256 do
      arquivo bate com um anexo de expediente) e 13 não. Dos 13, quatro são papel
      que a própria casa produziu (certidão emitida, etiqueta de selo) e não são
      «recebidos»; os outros são circulares e decisões arquivadas no Proton sem
      expediente.
    - O Malote Digital do TJMA (versão 26.05, https://malote.tjma.jus.br) entra
      por LOGIN E SENHA, e a página de entrada avisa: «Habilitado duplo fator de
      acesso (2FA)». A Corregedoria (Prov. 19/2013 CGJ-MA) dá ao recibo de leitura
      valor de ciência: ABRIR O DOCUMENTO NO MALOTE CONTA PRAZO.

O QUE ISSO DECIDIU
    1. O robô NÃO entra sozinho no Malote Digital. Com o 2FA, entrar sem gente é
       guardar o segundo fator na máquina — decisão de segurança do oficial, e não
       minha. E baixar é dar ciência: o relógio do prazo começa no clique. A parte
       «acessar e baixar» fica ASSISTIDA (o agente Claude, com a sessão aberta
       pelo escrevente, lista e baixa o que ele aprovar — ver
       `.claude/agents/agente-malote.md`), e `sondar_malote_digital` só mede a
       porta, sem credencial nenhuma.
    2. Do arquivo baixado em diante, o agente faz tudo sozinho: acha o que chegou
       (a pasta «PARA CADASTRAR» do Proton e a pasta de entrada do sistema),
       separa o que já está no sistema pelo sha256, separa o que é papel da casa,
       CADASTRA o expediente com os anexos — o mesmo expediente que a tela cria —
       e entrega à triagem que já existe (`gestor_expedientes`, que lê o PDF,
       decide setor e prazo e abre a tarefa).
    3. O que foi arquivado no Proton sem expediente NÃO se cadastra sozinho: a
       equipe já o classificou, e pode ter sido de propósito (circular de
       ciência). Vai para o relatório, com o nome e a pasta.

O QUE ELE NÃO FAZ
    Não responde ao remetente, não arquiva nem muda etapa de expediente, não move
    nem apaga nada no Proton (a pasta é da equipe), não guarda senha e não digita
    senha. `expedientes.created_by` é NOT NULL e o sistema não tem usuário-robô
    (decisão dele de 06/10: não criar conta para agente); o oficial decidiu em
    11/10/2026 que o agente cadastra **em nome dele**, e que **só ele**
    acessa o malote, com a ajuda do agente. A configuração
    O login vai em `settings.malote_cadastra_em_nome_de` (gravada na produção
    em 14/10/2026); o código não traz login nenhum.
"""
from __future__ import annotations

import argparse
import hashlib
import html
import json
import re
import sqlite3
import sys
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import banco_pg
from bd_nativo import banco

QUEM = "AGENTE MALOTE"
ORIGEM = "Malote Digital"

#: O NOME da pasta em que a equipe guarda o malote no Proton. O caminho até ela
#   (a conta e a pasta compartilhada) é desta casa e não se escreve no código
#   (relato #111, anti-vazamento): vem de `settings.malote_pasta_proton`, ou é
#   achado procurando esta pasta dentro do Proton Drive do usuário.
NOME_DA_PASTA_DO_MALOTE = "6. MALOTE DIGITAL"
SUBPASTA_A_CADASTRAR = "PARA CADASTRAR"
#: A pasta de entrada do próprio sistema (ordem do oficial de 10/10/2026: nada
#   novo fora de `arquivos\<atribuição>`). É onde o download assistido grava.
SUBPASTA_ENTRADA = Path("malote") / "entrada"

URL_MALOTE = "https://malote.tjma.jus.br/malotedigital/login.jsf"

#: Papel que a casa PRODUZIU e que a equipe guarda junto do expediente cumprido
#   — não é recebido. Medido na pasta em 11/10/2026: a etiqueta de selo
#   («AVERBA<CNS>…  CERTID<CNS>….pdf») e «certidao-rcpn-N-AAAA.pdf». O código do
#   selo tem 6 letras, o CNS da casa e o resto (`selo.py`); o CNS vem de
#   `settings.serventia_cns` (senão `ri_cns`), e não de literal.
_CERTIDAO_DA_CASA = re.compile(r"^certid[aã]o-(rcpn|ri|rcpj|rtd|protesto)-\d+-\d{4}", re.I)

#: A categoria que a equipe deu, pelo começo do nome do arquivo. Medido nos 42
#   anexos de expediente da produção em 11/10/2026: CIRC-… → Circulares em
#   todos; PORTARIA-… → Portarias; EDT-… → Circulares. DECISAO e DESPACHO caíram
#   ora em Circulares, ora em Outros — não decidem, e ficam em «Outros».
_CATEGORIA_PELO_NOME = (
    (re.compile(r"^CIRC", re.I), "Circulares"),
    (re.compile(r"^PORTARIA", re.I), "Portarias"),
    (re.compile(r"^EDT", re.I), "Circulares"),
)
#: O setor que a equipe anota no expediente: «Gestão» em 11 dos 12 últimos. O
#   setor da TAREFA é outro, e quem o decide é a triagem.
SETOR_PADRAO = "Gestão"

_IGNORAR = {".ds_store", "desktop.ini", "thumbs.db"}

#: EM NOME DE QUEM O AGENTE CADASTRA — decisão do oficial em 11/10/2026: «o
#   agente vai cadastrar no meu nome. agora apenas eu vou acessar o malote
#   com sua ajuda para triagem». A configuração
#   `settings.malote_cadastra_em_nome_de` continua ganhando deste padrão: mudar
#   de ideia não exige versão nova.
# 14/10/2026: o padrão era o login do oficial escrito aqui; saiu porque o
# código vai ao GitHub. Sem a configuração, o agente mede e não cadastra.
EM_NOME_DE_PADRAO = ""

#: A CAPA QUE O MALOTE DIGITAL PÕE NO PDF — medida em 11/10/2026 nos PDFs do
#   Proton: 137 de 153 a têm, e nas 137 vêm os mesmos campos na mesma ordem
#   (Tipo de documento, Código de rastreabilidade, Nome original, Data,
#   Remetente, Documento, Prioridade, Motivo de envio; Assunto em 133). É de lá
#   que saem remetente, assunto e o código — que é o número do documento no
#   malote, e por isso a chave contra cadastrar duas vezes (as cópias «(1).pdf»
#   da pasta têm o mesmo código).
_CAMPOS_DA_CAPA = ("Tipo de documento", "Código de rastreabilidade", "Nome original", "Data",
                   "Remetente", "Documento", "Prioridade", "Motivo de envio", "Assunto")
#: O assunto quebra a cada 64 caracteres, NO MEIO da palavra («…CBS NA AT» /
#   «IVIDADE NOTARIAL…»): 101 dos 133 assuntos têm a primeira linha com 64. É
#   por isso que os cadastrados à mão saem com «AT IVIDA». Junta-se SEM espaço
#   enquanto a linha anterior tiver 64 — o espaço, quando há, já está no texto.
LARGURA_DO_ASSUNTO = 64
_PRIORIDADE_DA_CAPA = {"URGENTE": "ALTA", "ALTA": "ALTA", "NORMAL": "MEDIA", "BAIXA": "BAIXA"}


def ler_capa(texto: str) -> dict | None:
    """A capa do malote no texto da 1ª página, ou None se não houver."""
    if "Código de rastreabilidade" not in (texto or ""):
        return None
    # SEM rstrip: na quebra do assunto o espaço do fim da linha é a separação
    # entre palavras («…constantes » / «no Proc. …»), e tirá-lo as colaria.
    linhas = texto.replace("\r", "").split("\n")
    capa: dict[str, str] = {}
    atual, largura = None, 0
    for linha in linhas:
        rotulo = next((c for c in _CAMPOS_DA_CAPA if linha.startswith(c + ":")), None)
        if rotulo:
            atual = rotulo
            valor = linha[len(rotulo) + 1:].lstrip()
            capa[atual] = valor if rotulo == "Assunto" else valor.strip()
            # a largura medida é a do TEXTO do assunto, sem o rótulo
            largura = len(linha[len(rotulo) + 1:].lstrip())
            continue
        if atual == "Remetente":                 # o remetente vem em várias linhas
            capa[atual] = " — ".join(x for x in (capa[atual], linha.strip()) if x)
        elif atual == "Assunto" and largura >= LARGURA_DO_ASSUNTO and linha:
            if "Código de rastreabilidade" in linha:
                break
            capa[atual] += linha
            largura = len(linha)
        elif atual == "Assunto":
            break
    codigo = re.match(r"\d+", capa.get("Código de rastreabilidade", ""))
    data = re.match(r"(\d{2})/(\d{2})/(\d{4})\s*([\d:]*)", capa.get("Data", ""))
    return {
        "codigo": codigo.group(0) if codigo else None,
        "nome_original": capa.get("Nome original") or None,
        "enviado_em": f"{data.group(3)}-{data.group(2)}-{data.group(1)} {data.group(4)}".strip() if data else None,
        "remetente": capa.get("Remetente") or None,
        "prioridade": (capa.get("Prioridade") or "").rstrip(".").strip() or None,
        "motivo": (capa.get("Motivo de envio") or "").rstrip(".").strip() or None,
        "tipo": capa.get("Tipo de documento") or None,
        "assunto": " ".join((capa.get("Assunto") or "").split()) or None,
    }


def capa_do_pdf(caminho: Path) -> dict | None:
    """Lê a capa da 1ª página. PDF que não abre ou não tem capa: None."""
    if caminho.suffix.lower() != ".pdf":
        return None
    try:
        import logging
        from pypdf import PdfReader
        logging.getLogger("pypdf").setLevel(logging.ERROR)
        return ler_capa(PdfReader(str(caminho)).pages[0].extract_text() or "")
    except Exception:                                    # noqa: BLE001 — sem capa, segue pelo nome
        return None

SCHEMA = """
CREATE TABLE IF NOT EXISTS mt_arquivos (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    caminho TEXT NOT NULL,
    visto_em TEXT NOT NULL,
    situacao TEXT NOT NULL,
    expediente_id bigint,
    nota TEXT
);
CREATE TABLE IF NOT EXISTS mt_execucoes (
    id bigint GENERATED BY DEFAULT AS IDENTITY PRIMARY KEY,
    iniciada_em TEXT NOT NULL,
    terminada_em TEXT,
    confirmou integer NOT NULL DEFAULT 0,
    resumo_json TEXT,
    erro TEXT
);
"""

SITUACOES = ("CADASTRADO", "JA_NO_SISTEMA", "REPETIDO", "DA_CASA", "PARCIAL", "SEM_RESPONSAVEL",
             "NA_LISTA_DE_FRAUDES", "FRAUDE_PENDENTE")


class MaloteError(ValueError):
    """Recusa de regra, com a frase pronta para o balcão."""


@dataclass
class Grupo:
    """Um expediente a nascer: um arquivo solto, ou uma subpasta inteira."""
    nome: str
    pasta_origem: str
    arquivos: list[Path] = field(default_factory=list)
    shas: dict[str, str] = field(default_factory=dict)      # caminho -> sha256
    situacao: str = ""
    nota: str = ""
    expediente_id: int | None = None
    protocolo: str | None = None
    capa: dict | None = None

    @property
    def recebido_em(self) -> str:
        """A data em que o arquivo chegou à pasta — e NÃO a da leitura no
        malote, que o arquivo não guarda. O relatório e a observação dizem isso."""
        mais_antigo = min(p.stat().st_mtime for p in self.arquivos)
        return date.fromtimestamp(mais_antigo).isoformat()


def init_schema(con: sqlite3.Connection) -> None:
    bd = banco(con)
    for comando in SCHEMA.split(";\n"):
        if comando.strip():
            bd.escrever(comando)


def _sha256(caminho: Path) -> str:
    h = hashlib.sha256()
    with caminho.open("rb") as f:
        for bloco in iter(lambda: f.read(1024 * 1024), b""):
            h.update(bloco)
    return h.hexdigest()


def _arquivos_de(pasta: Path) -> list[Path]:
    return sorted(p for p in pasta.rglob("*")
                  if p.is_file() and p.name.lower() not in _IGNORAR and not p.name.startswith("~$"))


def cns_da_casa(con: sqlite3.Connection | None) -> str:
    """Os dígitos do CNS em `settings` (`serventia_cns`, senão `ri_cns`). Só lê."""
    if con is None:
        return ""
    for chave in ("serventia_cns", "ri_cns"):
        try:
            r = banco(con).um("SELECT value FROM settings WHERE key = %s", (chave,))
        except sqlite3.Error:
            return ""
        digitos = "".join(ch for ch in str((r["value"] if r else "") or "") if ch.isdigit())
        if digitos:
            return digitos
    return ""


def e_da_casa(nome: str, cns: str = "") -> bool:
    """Certidão emitida aqui, ou etiqueta com o selo DESTA casa. Sem CNS
    configurado, a etiqueta não se reconhece — e o arquivo segue como recebido,
    o que é o lado seguro: aparece, em vez de sumir."""
    if _CERTIDAO_DA_CASA.search(nome):
        return True
    return bool(cns) and re.search(rf"\b[A-Z]{{6}}{re.escape(cns)}[A-Z0-9]{{10,16}}\b", nome) is not None


def pasta_proton_padrao(con: sqlite3.Connection | None = None) -> Path | None:
    """A pasta do malote no Proton: `settings.malote_pasta_proton`, senão a que
    se achar com o nome `NOME_DA_PASTA_DO_MALOTE` no Proton Drive do usuário
    (conta/«Shared with me»/pasta compartilhada/…). Nenhuma: None."""
    if con is not None:
        try:
            r = banco(con).um("SELECT value FROM settings WHERE key = 'malote_pasta_proton'")
        except sqlite3.Error:
            r = None
        if r and str(r["value"] or "").strip():
            return Path(str(r["value"]).strip())
    proton = Path.home() / "Proton Drive"
    if not proton.is_dir():
        return None
    achadas = sorted(proton.glob(f"*/Shared with me/*/{NOME_DA_PASTA_DO_MALOTE}")) \
        or sorted(proton.glob(f"*/{NOME_DA_PASTA_DO_MALOTE}"))
    return achadas[0] if achadas else None


def categoria_do_nome(nome: str) -> str:
    for regra, categoria in _CATEGORIA_PELO_NOME:
        if regra.search(nome):
            return categoria
    return "Outros"


def assunto_do_nome(nome: str) -> str:
    base = Path(nome).stem if "." in nome[-6:] else nome
    return " ".join(base.replace("_", " ").split())[:200] or "Sem assunto"


def pastas_de_entrada(pasta_dados: Path, pasta_proton: Path | None) -> list[Path]:
    pastas = [archive_root_de(pasta_dados) / SUBPASTA_ENTRADA]
    if pasta_proton is not None:
        pastas.append(pasta_proton / SUBPASTA_A_CADASTRAR)
    return pastas


def archive_root_de(pasta_dados: Path, con: sqlite3.Connection | None = None) -> Path:
    """O MESMO caminho de `app.archive_root`: `settings.archive_root`, senão
    `<dados>/arquivos`. Recalculado aqui porque o agente roda fora do Flask; o
    teste compara as duas regras."""
    if con is not None:
        try:
            r = banco(con).um("SELECT value FROM settings WHERE key = 'archive_root'")
        except sqlite3.Error:
            r = None
        if r and str(r["value"] or "").strip():
            return Path(str(r["value"]).strip()).expanduser()
    return Path(pasta_dados) / "arquivos"


def varrer(pastas: list[Path]) -> list[Grupo]:
    """O que está nas pastas de entrada, agrupado: arquivo solto é um grupo;
    subpasta é um grupo com tudo o que tem dentro (a equipe junta assim o
    «MANDADO DE AVERBAÇÃO RAFAEL/DOCUMENTOS.pdf»). Só lê."""
    grupos: list[Grupo] = []
    for pasta in pastas:
        if not pasta.is_dir():
            continue
        for item in sorted(pasta.iterdir()):
            if item.name.lower() in _IGNORAR or item.name.startswith("~$"):
                continue
            arquivos = _arquivos_de(item) if item.is_dir() else ([item] if item.is_file() else [])
            if not arquivos:
                continue
            g = Grupo(nome=item.name, pasta_origem=str(pasta), arquivos=arquivos)
            g.shas = {str(p): _sha256(p) for p in arquivos}
            # A CAPA É A DO DOCUMENTO PRINCIPAL, e não a do primeiro arquivo da
            # pasta: em 13/10/2026 o EXP-034 nasceu com o código do ANEXO, porque
            # «MALOTE_…430_anexo» vem antes de «MALOTE_…431_CIRC» na ordem do nome.
            capas = [c for c in map(capa_do_pdf, arquivos) if c]
            g.capa = next((c for c in capas if not str(c.get("nome_original") or "").lower()
                           .startswith("anexo")), capas[0] if capas else None)
            grupos.append(g)
    return grupos


def _shas_no_sistema(con: sqlite3.Connection, shas) -> dict[str, int]:
    """sha256 -> expediente que já tem esse arquivo como anexo."""
    bd = banco(con)
    achados: dict[str, int] = {}
    for sha in set(shas):
        r = bd.um("""SELECT entity_id FROM attachments
                      WHERE entity_type = 'EXPEDIENTE' AND sha256 = %s ORDER BY id LIMIT 1""",
                  (sha,))
        if r:
            achados[sha] = int(r["entity_id"])
    return achados


def _shas_na_lista_de_fraudes(con: sqlite3.Connection, shas) -> set[str]:
    """sha256 que já foram aviso de fraude lido pela IA (`mt_arquivos` FRAUDE).
    Banco sem a tabela (a medição em `mode=ro` numa casa que nunca rodou): nenhum."""
    shas = sorted(set(shas))
    if not shas:
        return set()
    try:
        return {r["sha256"] for r in banco(con).ler(
            "SELECT sha256 FROM mt_arquivos WHERE situacao = 'FRAUDE' AND sha256 = ANY(%s) "
            "ORDER BY sha256", (shas,))}
    except sqlite3.OperationalError:
        return set()


def classificar(con: sqlite3.Connection, grupos: list[Grupo]) -> list[Grupo]:
    """Decide o destino de cada grupo SEM gravar nada."""
    vistos: dict[str, str] = {}                    # código do malote -> grupo
    cns = cns_da_casa(con)
    for g in grupos:
        no_sistema = _shas_no_sistema(con, g.shas.values())
        nas_fraudes = _shas_na_lista_de_fraudes(con, g.shas.values())
        proprios = [p for p in g.arquivos if e_da_casa(p.name, cns)]
        codigo = (g.capa or {}).get("codigo")
        pelo_codigo = banco(con).um(
            "SELECT id FROM expedientes WHERE external_reference = %s ORDER BY id LIMIT 1",
            (codigo,)) if codigo else None
        if codigo and codigo in vistos:
            g.situacao = "REPETIDO"
            g.nota = f"mesmo documento do malote (código {codigo}) que «{vistos[codigo]}»"
        elif len(proprios) == len(g.arquivos):
            g.situacao, g.nota = "DA_CASA", "papel produzido pela casa (selo/certidão), não é recebido"
        elif nas_fraudes and len(nas_fraudes) == len(set(g.shas.values())):
            # AVISO DE FRAUDE JÁ LIDO: não vira expediente (ordem de 13/10/2026)
            g.situacao = "NA_LISTA_DE_FRAUDES"
            g.nota = "aviso de fraude já lido pela IA interna; as pessoas estão na lista de fraudes"
        elif no_sistema and len(no_sistema) == len(set(g.shas.values())):
            g.situacao = "JA_NO_SISTEMA"
            g.expediente_id = next(iter(no_sistema.values()))
            g.nota = f"já está no expediente {g.expediente_id}"
        elif no_sistema:
            g.situacao = "PARCIAL"
            g.nota = (f"{len(no_sistema)} de {len(g.arquivos)} arquivo(s) já estão no expediente "
                      f"{next(iter(no_sistema.values()))}; juntar à mão — não abro outro expediente")
        elif pelo_codigo:
            g.situacao, g.expediente_id = "JA_NO_SISTEMA", int(pelo_codigo["id"])
            g.nota = f"o código do malote {codigo} já é o do expediente {g.expediente_id}"
        else:
            g.situacao = "A_CADASTRAR"
        if codigo:
            vistos.setdefault(codigo, g.nome)
    return grupos


def usuario_responsavel(con: sqlite3.Connection, em_nome_de: str | None = None) -> int | None:
    """O id em nome de quem o agente cadastra: o login passado, senão
    `settings.malote_cadastra_em_nome_de`, senão o padrão que o oficial ditou
    (`EM_NOME_DE_PADRAO`). Login que não existe é recusa com frase — não se cai
    para outro usuário, porque autoria não se adivinha."""
    login = (em_nome_de or "").strip()
    if not login:
        try:
            r = banco(con).um("SELECT value FROM settings WHERE key = 'malote_cadastra_em_nome_de'")
        except sqlite3.Error:
            r = None
        login = str(r["value"] or "").strip() if r else ""
    login = login or EM_NOME_DE_PADRAO
    if not login:
        return None
    r = banco(con).um("SELECT id FROM users WHERE username = %s", (login,))
    if not r:
        raise MaloteError(f"O usuário «{login}», em nome de quem o agente do malote cadastra, "
                          "não existe. Confira em Configurações.")
    return int(r["id"])


def _proximo_protocolo(con: sqlite3.Connection) -> str:
    """O protocolo da casa, pela MESMA função da tela (`Database.next_protocol`
    aceita a conexão e só usa `self` quando não a recebe)."""
    from database import Database
    return Database.next_protocol(None, con)            # type: ignore[arg-type]


def _auditar(con, acao: str, entidade_id, detalhes: dict, agora: str) -> None:
    banco(con).escrever(
        """INSERT INTO audit_logs (ts, user_id, username_snapshot, action, entity_type,
               entity_id, details) VALUES (%s, NULL, %s, %s, 'EXPEDIENTE', %s, %s)""",
        (agora, QUEM, acao, entidade_id, json.dumps(detalhes, ensure_ascii=False, default=str)))


def cadastrar(con: sqlite3.Connection, g: Grupo, usuario_id: int, raiz_arquivos: Path,
              agora: str | None = None) -> int:
    """Cria o expediente e copia os anexos — a forma da tela de expedientes.

    A cópia vai para `arquivos/Expedientes/<categoria>/<protocolo>`, como a tela
    grava; o arquivo do Proton fica onde está. Tudo numa transação: anexo sem
    expediente ou expediente sem anexo não sobram.
    """
    from storage import copy_existing, safe_component
    if g.situacao != "A_CADASTRAR":
        raise MaloteError(f"«{g.nome}» não é para cadastrar ({g.situacao}): {g.nota}")
    agora = agora or datetime.now().isoformat(timespec="seconds")
    categoria = categoria_do_nome(g.nome)
    capa = g.capa or {}
    if capa:
        observacao = (f"Cadastrado pelo agente do malote a partir de «{g.pasta_origem}», com os dados "
                      f"da capa do Malote Digital: enviado em {capa.get('enviado_em') or '—'}, "
                      f"motivo «{capa.get('motivo') or '—'}», prioridade «{capa.get('prioridade') or '—'}», "
                      f"tipo «{capa.get('tipo') or '—'}». A data de recebimento é a de chegada do arquivo "
                      f"à pasta ({g.recebido_em}), e não a da leitura no malote.")
    else:
        observacao = (f"Cadastrado pelo agente do malote a partir de «{g.pasta_origem}». O PDF não traz a "
                      f"capa do Malote Digital: remetente e número do malote a conferir. A data de "
                      f"recebimento é a de chegada do arquivo à pasta ({g.recebido_em}).")
    if g.nota:                                   # o que a leitura de fraude disse
        observacao += f" Leitura de fraude pela IA interna: {g.nota}."
    prioridade = _PRIORIDADE_DA_CAPA.get((capa.get("prioridade") or "").upper(), "MEDIA")
    copiados: list[Path] = []
    try:
        bd = banco(con)
        bd.travar("expedientes.internal_protocol")
        protocolo = _proximo_protocolo(con)
        exp_id = int(bd.escrever(
            """INSERT INTO expedientes (internal_protocol, source, external_reference, sender,
                   subject, category, sector, received_at, priority, stage, notes,
                   created_by, created_at, updated_at)
               VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s, 'RECEBIDO', %s, %s, %s, %s)
               RETURNING id""",
            # A REFERÊNCIA É O CÓDIGO DO MALOTE quando há capa — a equipe já o
            # escrevia ali em 4 dos 12 últimos —, e o nome do arquivo quando não há.
            (protocolo, ORIGEM, (capa.get("codigo") or g.nome)[:200], capa.get("remetente"),
             (capa.get("assunto") or assunto_do_nome(g.nome))[:200], categoria,
             SETOR_PADRAO, g.recebido_em, prioridade, observacao, usuario_id, agora, agora))[0]["id"])
        destino = raiz_arquivos / "Expedientes" / safe_component(categoria) / safe_component(protocolo)
        for p in g.arquivos:
            info = copy_existing(p, destino)
            copiados.append(Path(info["stored_path"]))
            if info["sha256"] != g.shas[str(p)]:
                raise MaloteError(f"«{p.name}» mudou durante a cópia; nada foi cadastrado.")
            bd.escrever(
                """INSERT INTO attachments (entity_type, entity_id, original_name, stored_name,
                       stored_path, sha256, size_bytes, description, uploaded_by, uploaded_at)
                   VALUES ('EXPEDIENTE', %s, %s, %s, %s, %s, %s, 'Documento recebido (agente do malote)', %s, %s)""",
                (exp_id, info["original_name"], info["stored_name"], info["stored_path"],
                 info["sha256"], info["size_bytes"], usuario_id, agora))
            bd.escrever("""INSERT INTO mt_arquivos (sha256, caminho, visto_em, situacao,
                               expediente_id) VALUES (%s,%s,%s, 'CADASTRADO', %s)
                            ON CONFLICT (sha256) DO UPDATE SET caminho = EXCLUDED.caminho,
                               visto_em = EXCLUDED.visto_em, situacao = EXCLUDED.situacao,
                               expediente_id = EXCLUDED.expediente_id, nota = NULL""",
                        (info["sha256"], str(p), agora, exp_id))
        _auditar(con, "EXPEDIENTE_CREATED", exp_id,
                 {"origem": g.pasta_origem, "arquivos": [p.name for p in g.arquivos],
                  "em_nome_de": usuario_id, "protocolo": protocolo}, agora)
        con.commit()
    except Exception:
        con.rollback()
        for c in copiados:                     # cópia sem expediente não fica
            try:
                c.unlink()
            except OSError:
                pass
        raise
    g.situacao, g.expediente_id, g.protocolo = "CADASTRADO", exp_id, protocolo
    return exp_id


def arquivados_sem_expediente(con: sqlite3.Connection, pasta_proton: Path,
                              desde: date | None = None) -> list[dict]:
    """O que a equipe arquivou no Proton (fora de «PARA CADASTRAR») e que não
    tem expediente. SÓ RELATÓRIO: pode ser circular de ciência guardada de
    propósito, e quem decide é a pessoa."""
    if not pasta_proton.is_dir():
        return []
    saida = []
    cns = cns_da_casa(con)
    for p in _arquivos_de(pasta_proton):
        if SUBPASTA_A_CADASTRAR in p.parts or e_da_casa(p.name, cns):
            continue
        if desde and date.fromtimestamp(p.stat().st_mtime) < desde:
            continue
        sha = _sha256(p)
        if not _shas_no_sistema(con, [sha]):
            saida.append({"arquivo": p.name, "pasta": str(p.parent.relative_to(pasta_proton)),
                          "chegou_em": date.fromtimestamp(p.stat().st_mtime).isoformat()})
    return saida


def sondar_malote_digital(timeout: int = 20, abrir=None) -> dict:
    """Mede a porta do Malote Digital SEM credencial: se responde, a versão e se
    o aviso do 2FA está lá. Nunca manda login nem senha."""
    import urllib.request
    abrir = abrir or (lambda url: urllib.request.urlopen(url, timeout=timeout).read())
    try:
        corpo = abrir(URL_MALOTE).decode("utf-8", "replace")
    except Exception as erro:                           # noqa: BLE001 — vira medição
        return {"responde": False, "erro": f"{type(erro).__name__}: {str(erro)[:200]}"}
    texto = html.unescape(re.sub(r"<[^>]+>", " ", corpo))
    versao = re.search(r"Malote Digital\s+(\d+\.\d+)", texto)
    return {"responde": True,
            "versao": versao.group(1) if versao else None,
            "pede_login_e_senha": 'name="Login"' in corpo and 'name="Senha"' in corpo,
            "aviso_2fa": bool(re.search(r"2FA|duplo fator", texto, re.I))}


def rodada(con: sqlite3.Connection, pasta_dados: Path, *, pasta_proton: Path | None | str = "PADRAO",
           confirmar: bool = False, em_nome_de: str | None = None, triar: bool = False,
           hoje: date | None = None, sondar: bool = False, fraudes: bool = True,
           conversar=None) -> dict:
    """A volta inteira. Sem `confirmar`, só mede e diz o que faria.

    AVISO DE FRAUDE NÃO VIRA EXPEDIENTE (ordem do oficial de 13/10/2026: «nem
    tarefa, nem expediente»; «pode ser a ia interna»). Antes de cadastrar, o
    grupo que fala em fraude vai à IA interna (`malote_fraudes.tratar_grupo`):
    aviso com pessoas entra direto na lista de fraudes; o resto segue para
    expediente; se a IA não ler, o arquivo FICA na pasta e o verificador acusa.
    `fraudes=False` desliga a leitura (e aí tudo vira expediente, como antes)."""
    hoje = hoje or date.today()
    if pasta_proton == "PADRAO":
        pasta_proton = pasta_proton_padrao(con)
    init_schema(con)
    agora = datetime.now().isoformat(timespec="seconds")
    bd = banco(con)
    exec_id = bd.escrever("INSERT INTO mt_execucoes (iniciada_em, confirmou) VALUES (%s, %s) RETURNING id",
                          (agora, int(confirmar)))[0]["id"]
    con.commit()
    resumo: dict = {"grupos": [], "cadastrados": 0, "erros": [], "fraudes": []}
    try:
        grupos = classificar(con, varrer(pastas_de_entrada(pasta_dados, pasta_proton)))
        usuario, motivo = None, ("não cadastrei: falta dizer em nome de quem o agente cadastra "
                                 "(settings.malote_cadastra_em_nome_de)")
        if confirmar:
            try:
                usuario = usuario_responsavel(con, em_nome_de)
            except MaloteError as erro:          # vira nota em cada grupo, e não queda da rodada
                motivo = f"não cadastrei: {erro}"
        raiz = archive_root_de(pasta_dados, con)
        login = (bd.um("SELECT username FROM users WHERE id = %s", (usuario,))["username"]
                 if usuario is not None else None)
        leituras = 0
        for g in grupos:
            if g.situacao == "A_CADASTRAR" and confirmar:
                if usuario is None:
                    g.situacao = "SEM_RESPONSAVEL"
                    g.nota = motivo
                    continue
                if fraudes:
                    import malote_fraudes as MF
                    try:
                        if leituras >= MF.TETO_POR_RODADA:
                            f = {"caminho": "PENDENTE", "motivo": f"passou do teto de {MF.TETO_POR_RODADA} "
                                 "leituras de fraude nesta rodada; fica para a próxima", "leu": False}
                        else:
                            f = MF.tratar_grupo(con, g, pasta_dados, raiz, login, conversar=conversar)
                    except Exception as erro:          # noqa: BLE001 — o arquivo fica; vai ao resumo
                        resumo["erros"].append(f"{g.nome}: {type(erro).__name__}: {erro}")
                        g.situacao, g.nota = "FRAUDE_PENDENTE", f"erro ao levar à lista de fraudes: {erro}"
                        continue
                    leituras += bool(f.get("leu"))
                    if f["caminho"] == "FRAUDE":
                        g.situacao, g.nota = "NA_LISTA_DE_FRAUDES", f["nota"]
                        resumo["fraudes"].append({"grupo": g.nome, **{k: f[k] for k in (
                            "codigo", "incluidos", "ja_havia", "fora", "resumo", "pasta")}})
                        continue
                    if f["caminho"] == "PENDENTE":
                        g.situacao, g.nota = "FRAUDE_PENDENTE", f["motivo"]
                        continue
                    if f.get("leu"):
                        g.nota = f["motivo"]
                try:
                    cadastrar(con, g, usuario, raiz)
                    resumo["cadastrados"] += 1
                except Exception as erro:              # noqa: BLE001 — vai ao resumo
                    resumo["erros"].append(f"{g.nome}: {type(erro).__name__}: {erro}")
        # O RESUMO SE MONTA DEPOIS DO LAÇO: com os desvios do aviso de fraude o
        # laço tem `continue`, e montado dentro ele perdia justamente esses grupos
        # (o teste pegou, 13/10/2026).
        for g in grupos:
            resumo["grupos"].append({"nome": g.nome, "pasta": g.pasta_origem, "situacao": g.situacao,
                                     "nota": g.nota, "expediente_id": g.expediente_id,
                                     "protocolo": g.protocolo, "recebido_em": g.recebido_em,
                                     "arquivos": [p.name for p in g.arquivos],
                                     "categoria": categoria_do_nome(g.nome), "capa": g.capa})
        if pasta_proton is not None:
            resumo["arquivados_sem_expediente"] = arquivados_sem_expediente(con, pasta_proton)
        if triar and resumo["cadastrados"]:
            import gestor_expedientes
            resumo["triagem"] = gestor_expedientes.triar_pendentes(con, pasta_dados, hoje)
        if sondar:
            resumo["malote_digital"] = sondar_malote_digital()
        bd.escrever("UPDATE mt_execucoes SET terminada_em = %s, resumo_json = %s WHERE id = %s",
                    (datetime.now().isoformat(timespec="seconds"),
                     json.dumps(resumo, ensure_ascii=False, default=str), exec_id))
        con.commit()
    except Exception as erro:
        con.rollback()
        bd.escrever("UPDATE mt_execucoes SET terminada_em = %s, erro = %s WHERE id = %s",
                    (datetime.now().isoformat(timespec="seconds"),
                     f"{type(erro).__name__}: {str(erro)[:400]}", exec_id))
        con.commit()
        raise
    return resumo


_ROTULO = {"A_CADASTRAR": "a cadastrar", "REPETIDO": "cópia repetida (mesmo código)", "CADASTRADO": "cadastrado agora",
           "JA_NO_SISTEMA": "já no sistema", "DA_CASA": "papel da casa (ignorado)",
           "PARCIAL": "parte já no sistema — juntar à mão",
           "SEM_RESPONSAVEL": "não cadastrado: falta o responsável",
           "NA_LISTA_DE_FRAUDES": "aviso de fraude — pessoas na lista de fraudes (sem expediente)",
           "FRAUDE_PENDENTE": "parece aviso de fraude e a IA não leu — fica na pasta"}


def relatorio_html(resumo: dict, hoje: date) -> str:
    e = html.escape
    linhas = "".join(
        f"<tr><td>{e(g['nome'])}{'<br><small>' + e((g.get('capa') or {}).get('remetente') or '') + ' — ' + e((g.get('capa') or {}).get('assunto') or '') + '</small>' if g.get('capa') else ''}</td><td>{e(_ROTULO.get(g['situacao'], g['situacao']))}</td>"
        f"<td>{e(g.get('protocolo') or (str(g['expediente_id']) if g.get('expediente_id') else ''))}</td>"
        f"<td>{e(g['recebido_em'])}</td><td>{e(g['categoria'])}</td><td>{e(g['nota'])}</td></tr>"
        for g in resumo["grupos"]) or "<tr><td colspan=6>Nada nas pastas de entrada.</td></tr>"
    arq = "".join(f"<tr><td>{e(a['arquivo'])}</td><td>{e(a['pasta'])}</td><td>{e(a['chegou_em'])}</td></tr>"
                  for a in resumo.get("arquivados_sem_expediente", []))
    md = resumo.get("malote_digital")
    md_txt = ("" if not md else f"<p>Malote Digital: {'responde' if md.get('responde') else 'não respondeu'}"
              f"{', versão ' + e(md['versao']) if md.get('versao') else ''}"
              f"{', com 2FA' if md.get('aviso_2fa') else ''}.</p>")
    erros = "".join(f"<li>{e(x)}</li>" for x in resumo.get("erros", []))
    _papel = {"VITIMA": "vítima", "ENVOLVIDO": "envolvido(a)", "DOCUMENTO": "nome em documento fraudado"}
    fraudes = "".join(
        f"<h3>{e(f['grupo'])} — malote nº {e(f.get('codigo') or '—')}</h3><p>{e(f.get('resumo') or '')}</p><ul>"
        + "".join(f"<li>{e(x['nome'])} — {e(_papel.get(x['papel'], x['papel']))}</li>" for x in f["incluidos"])
        + "".join(f"<li>{e(x['nome'])} — já estava na lista</li>" for x in f["ja_havia"])
        + "".join(f"<li><i>ficou de fora: {e(x)}</i></li>" for x in f.get("fora") or [])
        + f"</ul><p><small>PDF guardado em {e(f.get('pasta') or '')}</small></p>"
        for f in resumo.get("fraudes", []))
    bloco_fraudes = (f"<h2>Avisos de fraude levados à lista de fraudes (sem expediente)</h2>{fraudes}"
                     if fraudes else "")
    return f"""<!doctype html><html lang="pt-BR"><head><meta charset="utf-8">
<title>Malote {hoje:%d/%m/%Y}</title>
<style>body{{font-family:Arial,sans-serif;margin:24px;color:#222}}table{{border-collapse:collapse;width:100%}}
td,th{{border:1px solid #ccc;padding:6px;font-size:13px;vertical-align:top}}th{{background:#eee}}</style></head><body>
<h1>Agente do malote — {hoje:%d/%m/%Y}</h1>
<p>{resumo['cadastrados']} expediente(s) cadastrado(s) nesta rodada.</p>{md_txt}
{bloco_fraudes}
<h2>O que estava nas pastas de entrada</h2>
<table><tr><th>arquivo ou pasta</th><th>situação</th><th>expediente</th><th>chegou em</th><th>categoria</th><th>nota</th></tr>{linhas}</table>
<h2>Arquivados no Proton sem expediente no sistema</h2>
<p>Só para conferir: pode ser circular de ciência guardada de propósito. O agente não os cadastra.</p>
<table><tr><th>arquivo</th><th>pasta</th><th>chegou em</th></tr>{arq or '<tr><td colspan=3>Nenhum.</td></tr>'}</table>
{f'<h2>Erros</h2><ul>{erros}</ul>' if erros else ''}
</body></html>"""


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="Agente do malote: acha o que chegou, cadastra e entrega à triagem.")
    ap.add_argument("--banco", required=True)
    ap.add_argument("--pasta-dados", help="padrão: a pasta do banco")
    ap.add_argument("--proton", default=None,
                    help="pasta «6. MALOTE DIGITAL»; padrão: settings.malote_pasta_proton ou a achada no "
                         "Proton Drive; '' desliga")
    ap.add_argument("--confirmar", action="store_true", help="sem isto, só mede")
    ap.add_argument("--em-nome-de", help="login em nome de quem cadastrar")
    ap.add_argument("--triar", action="store_true", help="chama a triagem do gestor depois de cadastrar")
    ap.add_argument("--sondar", action="store_true", help="mede a porta do Malote Digital (sem credencial)")
    ap.add_argument("--sem-fraudes", action="store_true",
                    help="não leva os avisos de fraude à IA interna (tudo vira expediente)")
    ap.add_argument("--saida", help="arquivo HTML do relatório")
    ap.add_argument("--sem-copia", action="store_true",
                    help="não tirar a cópia do banco antes de gravar (só em teste)")
    a = ap.parse_args(argv)
    banco = Path(a.banco)
    # PELA PORTA (`banco_pg.conectar`), e não pelo `sqlite3.connect`: fora do
    # sistema ninguém instala o desvio, e o acesso nativo recusa o sqlite3 cru.
    if a.confirmar:
        con = banco_pg.conectar(str(banco), timeout=60)
        if not a.sem_copia:
            # A CÓPIA ANTES DE GRAVAR, regra da casa: `VACUUM INTO`, conferida
            # antes de seguir. E LONGE DO BANCO — ordem do oficial de 11/10/2026
            # («backup e coisas não importantes não devem ficar na mesma pasta do
            # banco de dados»), no dia em que o banco foi apagado no meio das
            # cópias que moravam ao lado dele. Até essa ordem ia para
            # `<dados>/backups`; quem decide a pasta agora é `pasta_das_copias`
            # (produção: C:\CartorioGestao_Copiasntes_de_mexer, 15 mais novas).
            from pasta_das_copias import destino_da_copia
            copia = destino_da_copia(
                Path(f"antes_malote_agente_{datetime.now():%Y%m%d_%H%M%S_%f}.sqlite3"), banco)
            # `?` E NÃO TEXTO: é comando do sqlite3, que a ponte troca pelo pg_dump
            # lendo o parâmetro; o caminho com apóstrofo, escrito no SQL, ela não lia.
            con.execute("VACUUM INTO ?", (str(copia),))
            if not copia.is_file() or copia.stat().st_size == 0:
                raise MaloteError(f"A cópia do banco não saiu ({copia}); nada foi gravado.")
            print(f"cópia do banco: {copia}")
    else:
        # `mode=ro`: o SQLite recusa qualquer escrita, e `medir` não tenta nenhuma.
        con = banco_pg.conectar(f"file:{banco.as_posix()}?mode=ro", uri=True)
    try:
        if a.confirmar:
            resumo = rodada(con, Path(a.pasta_dados or banco.parent), pasta_proton=("PADRAO" if a.proton is None else (Path(a.proton) if a.proton else None)),
                            confirmar=True, em_nome_de=a.em_nome_de, triar=a.triar, sondar=a.sondar,
                            fraudes=not a.sem_fraudes)
        else:
            resumo = medir(con, Path(a.pasta_dados or banco.parent), (pasta_proton_padrao(con) if a.proton is None else (Path(a.proton) if a.proton else None)), a.sondar)
    finally:
        con.close()
    print(json.dumps(resumo, ensure_ascii=False, indent=1, default=str))
    if a.saida:
        Path(a.saida).write_bytes(relatorio_html(resumo, date.today()).encode("utf-8"))
    return 0


def medir(con: sqlite3.Connection, pasta_dados: Path, pasta_proton: Path | None, sondar: bool = False) -> dict:
    """A rodada sem gravar nada — nem a linha de execução. Serve à produção lida em `mode=ro`."""
    grupos = classificar(con, varrer(pastas_de_entrada(pasta_dados, pasta_proton)))
    resumo = {"cadastrados": 0, "erros": [], "so_mediu": True,
              "grupos": [{"nome": g.nome, "pasta": g.pasta_origem, "situacao": g.situacao, "nota": g.nota,
                          "expediente_id": g.expediente_id, "protocolo": None, "recebido_em": g.recebido_em,
                          "arquivos": [p.name for p in g.arquivos], "categoria": categoria_do_nome(g.nome), "capa": g.capa}
                         for g in grupos]}
    if pasta_proton is not None:
        resumo["arquivados_sem_expediente"] = arquivados_sem_expediente(con, pasta_proton)
    if sondar:
        resumo["malote_digital"] = sondar_malote_digital()
    return resumo


if __name__ == "__main__":
    raise SystemExit(main())
