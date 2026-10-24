"""O comprovante da gratuidade — aviso ao USUÁRIO, e não trava no ato.

    «vamos construir no sistema essa trava nos atos gratuitos, mas que seja um
     aviso de usuário, não de ato. pratica o ato e o usuário fica com aviso
     insistente até terminar de subir a comprovação da gratuidade»
                                                    — o oficial, 11/10/2026

POR QUÊ: o Portal do Selo analisa cada gratuidade e pede o comprovante; em
outubro de 2026 a casa teve de ir atrás de todos de uma vez (duas escreventes,
~5 h numa semana), porque não foram guardados na hora.

COMO SE SABE QUE O ATO É GRATUITO: pelo selo. O aparelho escreve «Selo Isento»
no texto do selo (medido em 11/10/2026: 179 selos isentos desde 08/09, 157 deles
averbações do RCPN). É a mesma régua do carimbo (`selo_no_papel`).

DE QUEM É O AVISO: de quem obteve o selo (`sd_selos.obtido_por`, que o sistema
grava com o nome da pessoa). O aviso some quando o comprovante está guardado
(`attachments`, entidade `SELO_GRATUIDADE`, amarrado ao selo).

DESDE QUANDO: `settings.gratuidade_comprovante_desde`; sem ela, 13/10/2026 —
o primeiro dia útil depois da ordem. O passado (o que já foi recolhido na
pasta da serventia) não vira aviso sozinho: retroagir é decisão do oficial, na configuração.

A COBRANÇA FICOU MAIS INCISIVA (LX16, 19/10/2026), e continua sem travar:
«geralmente temos o comprovante da gratuidade só depois que o ato é
praticado; é necessário juntar o comprovante + cópia da certidão do ato
praticado» (o oficial). A barra no topo diz quantos e qual o selo mais
antigo; passados N dias (`settings.gratuidade_comprovante_dias_alerta`,
padrão 3) ela fica vermelha e o selo entra na lista do gestor, por
escrevente. A pendência some com UM arquivo por selo — um PDF com o
comprovante e a certidão do ato —, e o fundamento legal se escolhe numa
lista (`FUNDAMENTOS`).

GRATUIDADE PRESUMIDA NÃO SE COBRA: registro de nascimento e de óbito (e de
natimorto), e a primeira certidão deles. A própria tabela do TJ diz
«Isento» nesses itens (`ato_selado.MOTIVO_DA_ISENCAO`), e não há
comprovante a pedir a quem registrou um filho.

A PASTA DA SERVENTIA AJUDA: arquivo da pasta dos comprovantes cujo NOME traz o código do selo
(a equipe já salva assim: «AVERBA000000XA66PB40MVB00E35.pdf») é oferecido para
trazer com um clique — e só com o clique: quem confere é a pessoa.
"""
from __future__ import annotations

import hashlib
import re
import sqlite3
import unicodedata
from datetime import date
from pathlib import Path
from typing import Any

from bd_nativo import banco

ENTIDADE = "SELO_GRATUIDADE"
DESDE_PADRAO = "2026-10-13"
MARCA_DO_SELO_ISENTO = "%Selo Isento%"
#: A pasta dos comprovantes é configuração da serventia (`settings.gratuidade_pasta`,
#: na tela de Configurações): o código não sabe onde ela fica nem como se chama.
EXTENSOES = (".pdf", ".jpg", ".jpeg", ".png")
#: Código do selo: 6 letras, o CNS (6 dígitos) e 10 a 16 caracteres (`selo.py`).
_CODIGO_DO_SELO = re.compile(r"[A-Z]{6}\d{6}[A-Z0-9]{10,16}")

#: A barra fica vermelha a partir de tantos dias sem o comprovante.
CHAVE_DOS_DIAS = "gratuidade_comprovante_dias_alerta"
DIAS_PARA_FICAR_VERMELHO = 3
#: O que vai no arquivo e por quê — a frase da tela, escrita uma vez.
O_QUE_VAI_NO_PDF = "um PDF com: comprovante + certidão do ato"
POR_QUE = "o Portal do Selo pede o comprovante de cada selo gratuito"
#: Gratuidade presumida: o item da tabela (`14.a` nascimento, `14.c` óbito,
#: `14.d` natimorto — «bem como pela primeira certidão respectiva») e o
#: caminho do registro, que é por onde sai também a primeira certidão.
CODIGOS_DE_GRATUIDADE_PRESUMIDA = frozenset({"14.a", "14.c", "14.d"})
CAMINHOS_DE_GRATUIDADE_PRESUMIDA = frozenset({
    "/selo/civil/nascimento", "/selo/civil/obito", "/selo/civil/natimorto"})
_ATO_NO_TEXTO = re.compile(r"Ato:\s*([0-9]+(?:\.[0-9A-Za-z]+)*)")
#: O fundamento legal da gratuidade, escolhido numa lista. A lista é do
#: fundamento; o TIPO do documento (declaração, decisão...) é do LG07
#: (`selo_portal.TIPOS_DE_COMPROVANTE`).
FUNDAMENTOS: dict[str, str] = {
    "JUSTICA_GRATUITA": "Justiça gratuita deferida nos autos (CPC, art. 98, § 1º, IX)",
    "POBREZA_RCPN": "Reconhecidamente pobre — certidões do registro civil "
                    "(Lei 6.015/1973, art. 30, § 1º)",
    "CASAMENTO_POBRE": "Habilitação, registro e 1ª certidão de casamento de quem se "
                       "declara pobre (Código Civil, art. 1.512, parágrafo único)",
    "REURB_S": "REURB-S (Lei 13.465/2017, art. 13, § 1º)",
    "REQUISICAO": "Requisição do juiz, do Ministério Público ou da Defensoria",
    "ISENCAO_LEGAL": "Isenção prevista em lei para o ato (citada no comprovante)",
}


class ComprovanteError(ValueError):
    """Recusa com frase de balcão."""


def _norm(s: Any) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(s or ""))
                   if unicodedata.category(c) != "Mn").strip().lower()


def desde(con: sqlite3.Connection) -> str:
    try:
        row = banco(con).um("SELECT value FROM settings WHERE key='gratuidade_comprovante_desde'")
    except sqlite3.OperationalError:
        row = None
    valor = (row["value"] if row else "") or ""
    return valor[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", valor) else DESDE_PADRAO


def incluidos(con: sqlite3.Connection) -> list[int]:
    """HOTFIX-2026-10-13-04 (escrevente, 13/10/2026, mat. 4019 -> FERJ): selos de
    antes do «desde» que o oficial manda pôr na lista, um a um, por
    `settings.gratuidade_comprovante_incluir` («26461,26463»). Retroagir só o
    que foi pedido, sem ligar o passado inteiro."""
    try:
        row = banco(con).um("SELECT value FROM settings WHERE key='gratuidade_comprovante_incluir'")
    except sqlite3.OperationalError:
        row = None
    return [int(x) for x in re.findall(r"\d+", (row["value"] if row else "") or "")]


def gratuidade_presumida(texto: Any, caminho: Any = None) -> bool:
    """Nascimento, óbito, natimorto e a 1ª certidão deles: não se cobra. Só calcula.

    Pelo item da tabela escrito no texto do selo («Ato: 14.a») ou pelo
    caminho do registro — os dois são do próprio selo, e nenhum é palpite.
    """
    if str(caminho or "").strip().rstrip("/") in CAMINHOS_DE_GRATUIDADE_PRESUMIDA:
        return True
    achado = _ATO_NO_TEXTO.search(str(texto or ""))
    return bool(achado and achado.group(1) in CODIGOS_DE_GRATUIDADE_PRESUMIDA)


def _todos_pendentes(con: sqlite3.Connection) -> list[dict]:
    """Os selos isentos sem comprovante, de todo mundo, mais antigo primeiro."""
    bd = banco(con)
    caminho = ("s.caminho" if bd.tem_coluna("sd_selos", "caminho")
               else "NULL::text")
    extras = incluidos(con)
    rows = bd.ler(
        f"SELECT s.id, s.numero, s.tabela, s.ato_id, s.atribuicao, s.obtido_em, s.obtido_por, "
        f"s.texto, {caminho} AS caminho "
        "FROM sd_selos s WHERE s.texto ILIKE %s AND (s.obtido_em >= %s OR s.id IN ("
        + (",".join(["%s"] * len(extras)) or "NULL") + ")) AND s.cancelado_em IS NULL "
        "AND NOT EXISTS (SELECT 1 FROM attachments a WHERE a.entity_type=%s AND a.entity_id=s.id) "
        "ORDER BY s.obtido_em, s.id",
        (MARCA_DO_SELO_ISENTO, desde(con), *extras, ENTIDADE))
    return [r for r in rows if not gratuidade_presumida(r["texto"], r["caminho"])]


def pendentes(con: sqlite3.Connection, *, nome: str, username: str = "",
              com_rotulo: bool = True) -> list[dict]:
    """Os selos isentos desta pessoa ainda sem comprovante guardado. Só LÊ.

    A LISTA MUDOU NO LX16 (3520f55), E É A DECISÃO DO OFICIAL — conferida no
    LX21b contra `funcionalidades/LX16.md` (pedido e «correção do oficial»
    de 19/10/2026), achado 7 da revisão do LX16:
      - a gratuidade NÃO trava: o selo isento sai, e só depois entra aqui;
      - a pendência é por selo e some com UM anexo (o PDF com comprovante +
        certidão do ato; mais de um também vale);
      - nascimento, óbito e natimorto (e a 1ª certidão deles) têm gratuidade
        presumida e NÃO entram (`gratuidade_presumida`) — nem aqui, nem na
        lista do gestor, que lê o mesmo `_todos_pendentes`.

    `com_rotulo=False` é para a barra do topo, que roda em toda tela: o
    rótulo custa uma consulta por selo do RI, e a barra só mostra o número e
    o mais antigo.
    """
    alvos = {_norm(nome), _norm(username)} - {""}
    if not alvos:
        return []
    saida = []
    for r in _todos_pendentes(con):
        if _norm(r["obtido_por"]) in alvos:
            saida.append({"id": r["id"], "numero": r["numero"], "tabela": r["tabela"],
                          "ato_id": r["ato_id"], "atribuicao": r["atribuicao"],
                          "obtido_em": r["obtido_em"], "obtido_por": r["obtido_por"],
                          "rotulo": (rotulo(con, r["tabela"], r["ato_id"])
                                     if com_rotulo else "")})
    return saida


def dias_para_ficar_vermelho(con: sqlite3.Connection) -> int:
    """N da configuração; sem ela (ou com lixo), 3."""
    try:
        row = banco(con).um("SELECT value FROM settings WHERE key=%s", (CHAVE_DOS_DIAS,))
    except sqlite3.OperationalError:
        row = None
    bruto = str((row["value"] if row else "") or "").strip()
    return int(bruto) if bruto.isdigit() and int(bruto) > 0 else DIAS_PARA_FICAR_VERMELHO


def _dias_desde(obtido_em: Any, hoje: Any) -> int:
    try:
        inicio = date.fromisoformat(str(obtido_em or "")[:10])
        fim = date.fromisoformat(str(hoje)[:10])
    except ValueError:
        return 0
    return max(0, (fim - inicio).days)


def aviso(con: sqlite3.Connection, *, nome: str, username: str = "",
          hoje: Any) -> dict:
    """O que a barra do topo diz a esta pessoa. Só LÊ.

    Barra, e não janela: a janela se fecha sem ler (LX17). Diz quantos, qual o
    selo mais antigo e há quantos dias; a partir de N dias fica vermelha.
    """
    lista = pendentes(con, nome=nome, username=username, com_rotulo=False)
    if not lista:
        return {"quantos": 0, "vermelho": False}
    antigo = lista[0] | {"rotulo": rotulo(con, lista[0]["tabela"], lista[0]["ato_id"])}
    dias = _dias_desde(antigo["obtido_em"], hoje)
    prazo = dias_para_ficar_vermelho(con)
    return {"quantos": len(lista), "mais_antigo": antigo, "dias": dias,
            "prazo": prazo, "vermelho": dias >= prazo,
            "o_que_vai": O_QUE_VAI_NO_PDF, "por_que": POR_QUE}


def sem_comprovante_por_escrevente(con: sqlite3.Connection, *, hoje: Any,
                                   so_vencidos: bool = True) -> list[dict]:
    """A lista do gestor/oficial: gratuidades sem comprovante, por escrevente.

    Por padrão só o que passou de N dias — o que ainda está no prazo é
    assunto da própria pessoa, e a barra dela já cobra.
    """
    prazo = dias_para_ficar_vermelho(con)
    grupos: dict[str, dict] = {}
    for r in _todos_pendentes(con):
        dias = _dias_desde(r["obtido_em"], hoje)
        if so_vencidos and dias < prazo:
            continue
        quem = str(r["obtido_por"] or "").strip() or "(sem nome)"
        g = grupos.setdefault(_norm(quem), {"escrevente": quem, "quantos": 0,
                                            "mais_antigo": r, "dias": dias, "selos": []})
        g["quantos"] += 1
        g["selos"].append({"id": r["id"], "numero": r["numero"], "obtido_em": r["obtido_em"],
                           "dias": dias, "rotulo": rotulo(con, r["tabela"], r["ato_id"])})
    return sorted(grupos.values(), key=lambda g: (-g["dias"], g["escrevente"]))


def comprovados(con: sqlite3.Connection, *, nome: str, username: str = "",
                limite: int = 300) -> list[dict]:
    """HOTFIX-2026-10-13-07: os selos isentos desta pessoa que JA tem
    comprovante, com a lista de anexos - para ver e acrescentar mais."""
    alvos = {_norm(nome), _norm(username)} - {""}
    if not alvos:
        return []
    rows = banco(con).ler(
        "SELECT s.id, s.numero, s.tabela, s.ato_id, s.atribuicao, s.obtido_em, s.obtido_por "
        "FROM sd_selos s WHERE s.texto ILIKE %s AND s.cancelado_em IS NULL "
        "AND EXISTS (SELECT 1 FROM attachments a WHERE a.entity_type=%s AND a.entity_id=s.id) "
        "ORDER BY s.obtido_em DESC, s.id DESC LIMIT %s",
        (MARCA_DO_SELO_ISENTO, ENTIDADE, int(limite)))
    saida = []
    for r in rows:
        if _norm(r["obtido_por"]) in alvos:
            saida.append({"id": r["id"], "numero": r["numero"], "tabela": r["tabela"],
                          "ato_id": r["ato_id"], "atribuicao": r["atribuicao"],
                          "obtido_em": r["obtido_em"], "obtido_por": r["obtido_por"],
                          "rotulo": rotulo(con, r["tabela"], r["ato_id"]),
                          "anexos": anexos(con, r["id"])})
    return saida


def anexos(con: sqlite3.Connection, selo_id: int) -> list[dict]:
    """HOTFIX-2026-10-13-07: todos os comprovantes de um selo (nunca apaga)."""
    return [{"id": a["id"], "nome": a["original_name"], "em": a["uploaded_at"]}
            for a in banco(con).ler(
                "SELECT id, original_name, uploaded_at FROM attachments WHERE entity_type=%s "
                "AND entity_id=%s ORDER BY id", (ENTIDADE, int(selo_id)))]


def rotulo(con: sqlite3.Connection, tabela: Any, ato_id: Any) -> str:
    """HOTFIX-2026-10-13-08: «Mat. 4019 – R-01» em vez de «ri atos 3751». So le."""
    try:
        if tabela == "ri_atos" and ato_id:
            r = banco(con).um("SELECT m.numero AS mat, a.tipo, a.numero FROM ri_atos a "
                              "JOIN ri_matriculas m ON m.id=a.matricula_id WHERE a.id=%s",
                              (int(ato_id),))
            if r:
                n = str(r["numero"] or "")
                return f"Mat. {r['mat']} – {r['tipo'] or ''}-{n.zfill(2) if n.isdigit() else n}"
        if tabela == "ri_matriculas" and ato_id:
            r = banco(con).um("SELECT numero FROM ri_matriculas WHERE id=%s", (int(ato_id),))
            if r:
                return f"Mat. {r['numero']} – abertura"
    except (sqlite3.Error, ValueError, TypeError):
        pass
    return ""


def quantos_pendentes(con: sqlite3.Connection, *, nome: str, username: str = "") -> int:
    return len(pendentes(con, nome=nome, username=username))


def _selo(con, selo_id: int) -> dict:
    r = banco(con).um("SELECT id, numero, texto, obtido_por FROM sd_selos WHERE id=%s",
                      (int(selo_id),))
    if not r:
        raise ComprovanteError("Selo não encontrado.")
    if "selo isento" not in (r["texto"] or "").lower():
        raise ComprovanteError("Este selo não é de ato gratuito.")
    return {"id": r["id"], "numero": r["numero"], "obtido_por": r["obtido_por"]}


def guardar(con: sqlite3.Connection, selo_id: int, *, nome_arquivo: str, conteudo: bytes,
            pasta: Path, usuario_id: int | None, agora: str, origem: str = "upload",
            fundamento: str | None = None) -> int:
    """Guarda o comprovante amarrado ao selo. O aviso daquele ato some.

    `fundamento` é uma chave de `FUNDAMENTOS` (a tela oferece a lista); vai
    na descrição do anexo, que é o que a conferência lê.
    """
    selo = _selo(con, selo_id)
    chave = str(fundamento or "").strip().upper()
    if chave and chave not in FUNDAMENTOS:
        raise ComprovanteError("Escolha o fundamento da gratuidade na lista.")
    nome_arquivo = Path(nome_arquivo or "").name
    if not nome_arquivo.lower().endswith(EXTENSOES):
        raise ComprovanteError("Comprovante em PDF ou imagem (JPG, PNG).")
    if not conteudo:
        raise ComprovanteError("O arquivo veio vazio.")
    sha = hashlib.sha256(conteudo).hexdigest()
    pasta.mkdir(parents=True, exist_ok=True)
    destino = pasta / f"{selo['numero']}_{sha[:10]}{Path(nome_arquivo).suffix.lower()}"
    destino.write_bytes(conteudo)
    novo = banco(con).escrever(
        "INSERT INTO attachments(entity_type, entity_id, original_name, stored_name, stored_path, "
        "sha256, size_bytes, description, uploaded_by, uploaded_at) "
        "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id",
        (ENTIDADE, int(selo_id), nome_arquivo, destino.name, str(destino), sha, len(conteudo),
         f"Comprovante da gratuidade do selo {selo['numero']} ({origem})"
         + (f" — fundamento: {FUNDAMENTOS[chave]}" if chave else ""), usuario_id, agora))
    return int(novo[0]["id"])


def guardar_junto(con: sqlite3.Connection, selo_id: int, *,
                  arquivos: list[tuple[str, bytes]], pasta: Path,
                  usuario_id: int | None, agora: str,
                  fundamento: str | None = None) -> int:
    """Junta comprovante + certidão do ato num PDF só e guarda. ESCREVE.

    É o «um clique» da tela: o comprovante que a pessoa mandou e a certidão
    do ato, na ordem do pacote do Portal (comprovante primeiro). A junção é a
    do LG07 (`selo_portal.juntar_em_pdf`), para o pacote e o anexo não
    divergirem na forma.
    """
    import selo_portal as SP
    selo = _selo(con, selo_id)
    validos = [(Path(n or "").name, c) for n, c in (arquivos or []) if c]
    if not validos:
        raise ComprovanteError("Mande o comprovante (e a certidão do ato, se não estiver nele).")
    for nome, _ in validos:
        if not nome.lower().endswith(EXTENSOES):
            raise ComprovanteError("Comprovante em PDF ou imagem (JPG, PNG).")
    try:
        pdf = SP.juntar_em_pdf(validos)
    except Exception as erro:                                  # noqa: BLE001
        raise ComprovanteError(
            "Não consegui juntar os arquivos num PDF só — guarde-os um a um "
            "(a pendência some com o primeiro).") from erro
    aid = guardar(con, selo_id, nome_arquivo=f"{selo['numero']}_comprovante_e_certidao.pdf",
                  conteudo=pdf, pasta=pasta, usuario_id=usuario_id, agora=agora,
                  origem="comprovante + certidão do ato", fundamento=fundamento)
    # O pacote do Portal (LG07) lê o que cada arquivo é: este traz os dois.
    bd = banco(con)
    if bd.tem_tabela("sd_gratuidade_pecas"):
        SP._marcar(bd, aid, int(selo_id), peca=SP.AMBOS, tipo_comprovante="",
                   agora=agora, usuario="")
    return aid


def na_pasta(codigos: list[str], pasta: Path | None = None) -> dict[str, Path]:
    """Arquivos da pasta dos comprovantes (`settings.gratuidade_pasta`) cujo nome
    traz o código do selo. Sem pasta configurada, nada — não se procura."""
    if not codigos or not pasta or not Path(pasta).is_dir():
        return {}
    procurados = {c.upper() for c in codigos if c}
    achados: dict[str, Path] = {}
    for arq in Path(pasta).rglob("*"):
        if not arq.is_file() or arq.suffix.lower() not in EXTENSOES:
            continue
        for codigo in _CODIGO_DO_SELO.findall(arq.name.upper()):
            if codigo in procurados and codigo not in achados:
                achados[codigo] = arq
    return achados
