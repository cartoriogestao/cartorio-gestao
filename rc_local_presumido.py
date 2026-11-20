"""O LOCAL DE NASCIMENTO DOS LIVROS A-1 A A-5, E A MATRÍCULA QUE FALTAVA.

A AUDITORIA DE 18/11/2026
    Dos 994 nascimentos dos livros A-1 a A-5, **918 não têm local de
    nascimento** em campo nenhum: a importação do acervo trouxe nome, datas,
    filiação e naturalidade, e não o local. A certidão sai «LOCAL DE
    NASCIMENTO: NÃO CONSTA» e o município de nascimento fica vazio. Dois
    assentos do acervo transcrito também estavam **sem matrícula** — a CRC os
    retinha e a certidão saía sem ela.

A DECISÃO DO OFICIAL, 19/11/2026
    «local de nascimento coloque, na dúvida, [o município da serventia] e
    código IBGE [dele]».

    **«Na dúvida» quer dizer quando o assento não diz outra coisa.** Nos
    livros antigos a naturalidade é o lugar do nascimento, e ela está na
    pessoa do registrado em quase todos: medido em 19/11/2026, 755 da sede e
    ~160 de outras cidades (75 de uma só). Escrever a sede para quem a
    naturalidade diz ter nascido noutra cidade poria na certidão o contrário
    do que o assento diz. Por isso:

      1. o local é a **naturalidade do registrado**, quando o cadastro do
         IBGE a confirma;
      2. só quando ela falta (ou não se confirma), vale a **sede da
         serventia** (`ri_cidade`/`ri_uf`) — e, se a pessoa não tinha
         naturalidade nenhuma, ela também recebe a da sede, que é de onde a
         CRC tira o `CODIGOIBGEMUNNASCIMENTO`.

    Fica escrito no próprio assento (`dados_json.local_nascimento_presumido` e
    `historico`) que o local **não foi transcrito do livro** — é o mesmo
    combinado da data de registro derivada (12/09/2026).

A MATRÍCULA
    Assento destes livros sem matrícula, com livro, folha, termo e data do
    registro, ganha a matrícula calculada por `rc_matricula.compor` (Anexo IV
    da CRC), a mesma conta do botão da ficha.

O QUE NÃO SE TOCA
    Assento com qualquer local (coluna ou pacote do acervo), pessoa que já tem
    naturalidade, assento cancelado, lavratura desta casa (`MANUAL`) e assento
    cujo `livro_volume` é de outra letra ou de outro número que não 1 a 5 —
    esses são divergências de livro, assunto de conferência, e não de
    presunção. Idempotente: a segunda rodada não acha ninguém.
"""
from __future__ import annotations

import json
import re
from datetime import datetime
from typing import Any

from bd_nativo import banco

LIVROS = range(1, 6)
DECISAO = ("decisão do oficial em 19/11/2026: na dúvida, o local de "
           "nascimento é o município da serventia, com o código IBGE dele")
CHAVES_DE_LOCAL = ("strNomeLocal", "strLN_endereco", "strMunicipioNascimento",
                   "local_nascimento", "local_fato")


def _texto(v: Any) -> str:
    return "" if v is None else str(v).strip()


def _dados(assento: dict) -> dict | None:
    try:
        dados = json.loads(assento.get("dados_json") or "{}")
    except (TypeError, ValueError):
        return None
    return dados if isinstance(dados, dict) else None


def livro_antigo(assento: dict) -> int | None:
    """O número do livro A (1 a 5) deste assento, ou None. Só calcula.

    O `livro_volume` manda; vazio, vale o livro dentro da matrícula (tipo 1 =
    livro A). Volume de outra letra ou de outro número não entra.
    """
    import rc_matricula as MAT
    volume = _texto(assento.get("livro_volume"))
    if volume:
        # «A-02, FLS 180» é o livro 2 com a folha escrita junto.
        m = re.match(r"^A\s*-?\s*0*(\d+)(?!\d)(?:\s*[,;/].*)?$", volume, re.I)
        n = int(m.group(1)) if m else None
        return n if n in LIVROS else None
    try:
        p = MAT.partes(assento.get("matricula"))
    except Exception:                                   # noqa: BLE001
        return None
    if p.get("livro_tipo") != "1":
        return None
    n = int(p["livro"])
    return n if n in LIVROS else None


def _tem_local(assento: dict, dados: dict) -> bool:
    if any(_texto(assento.get(c)) for c in
           ("local_fato_nome", "local_fato_endereco", "local_fato_municipio")):
        return True
    transcrito = dados.get("acervo_transcrito") or {}
    if not isinstance(transcrito, dict):
        transcrito = {}
    return any(_texto(dados.get(k)) or _texto(transcrito.get(k))
               for k in CHAVES_DE_LOCAL)


def _municipio_confirmado(con, cidade: Any, uf: Any) -> tuple[str, str]:
    """(município, UF) quando o IBGE confirma; senão ("", "")."""
    from crc_carga import _codigo_ibge_municipio
    from rc_assento import municipio_da_naturalidade
    if not _texto(cidade) or not _codigo_ibge_municipio(con, cidade, uf):
        return "", ""
    nome, uf_lida = municipio_da_naturalidade(cidade)
    uf_final = _texto(uf).upper() if len(_texto(uf)) == 2 else uf_lida
    return nome, uf_final


def _setting(bd, chave: str) -> str:
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
    return _texto(linha["value"]) if linha else ""


def _registrado(bd, assento_id: int) -> dict | None:
    return bd.um(
        """SELECT * FROM rc_pessoas WHERE assento_id=%s AND papel='REGISTRADO'
            ORDER BY ordem, id LIMIT 1""", (int(assento_id),))


def _historico(dados: dict, entrada: dict) -> dict:
    dados = dict(dados)
    dados["historico"] = list(dados.get("historico") or []) + [entrada]
    return dados


def _candidatos(bd) -> list[dict]:
    return [dict(r) for r in bd.ler(
        """SELECT * FROM rc_assentos
            WHERE especie = 'NASCIMENTO'
              AND COALESCE(situacao, 'ATIVO') = 'ATIVO'
              AND COALESCE(origem, '') <> 'MANUAL'
            ORDER BY id""")]


def gravar(con, *, agora: str | None = None) -> dict:
    """Grava o local presumido e a matrícula que faltava. ESCREVE.

    Devolve quantos assentos ganharam local (pela naturalidade e pela sede),
    quantas pessoas ganharam a naturalidade da sede e quantas matrículas.
    """
    import rc_matricula as MAT
    bd = banco(con)
    quando = agora or datetime.now().replace(microsecond=0).isoformat(
        timespec="seconds")
    saida = {"pela_naturalidade": 0, "pela_sede": 0,
             "naturalidade_da_sede": 0, "matriculas": 0}
    if not bd.tem_tabela("rc_assentos") or not bd.tem_tabela("settings"):
        return saida
    sede = _municipio_confirmado(con, _setting(bd, "ri_cidade"),
                                 _setting(bd, "ri_uf"))
    cns = re.sub(r"\D", "", _setting(bd, "serventia_cns")
                 or _setting(bd, "ri_cns"))

    for a in _candidatos(bd):
        livro = livro_antigo(a)
        if livro is None:
            continue
        dados = _dados(a)
        if dados is None:
            continue
        sets: dict[str, Any] = {}

        # ------------------------------------------------- o local
        if not _tem_local(a, dados):
            pessoa = _registrado(bd, a["id"]) or {}
            cidade, uf = _municipio_confirmado(
                con, _texto(pessoa.get("naturalidade_cidade"))
                or _texto(a.get("naturalidade_declarada")),
                pessoa.get("naturalidade_uf"))
            fonte = "naturalidade do registrado"
            if not cidade and sede[0]:
                cidade, uf = sede
                fonte = "município da serventia"
            if cidade:
                lugar = f"{cidade}/{uf}" if uf else cidade
                sets["local_fato_nome"] = lugar
                sets["local_fato_municipio"] = cidade
                alteracoes = [
                    {"campo": "rc_assentos.local_fato_nome", "antes": None,
                     "depois": lugar},
                    {"campo": "rc_assentos.local_fato_municipio",
                     "antes": None, "depois": cidade}]
                sem_naturalidade = (
                    pessoa.get("id")
                    and not _texto(pessoa.get("naturalidade_cidade"))
                    and not _texto(a.get("naturalidade_declarada")))
                if fonte == "município da serventia" and sem_naturalidade:
                    bd.escrever(
                        """UPDATE rc_pessoas
                              SET naturalidade_cidade=%s, naturalidade_uf=%s
                            WHERE id=%s
                              AND COALESCE(TRIM(naturalidade_cidade), '')=''""",
                        (cidade, uf or None, int(pessoa["id"])))
                    saida["naturalidade_da_sede"] += 1
                    alteracoes.append(
                        {"campo": "rc_pessoas.naturalidade (REGISTRADO)",
                         "antes": None, "depois": lugar})
                dados["local_nascimento_presumido"] = (
                    f"o local de nascimento é a {fonte} ({lugar}), por "
                    f"{DECISAO}. O livro/transcrição não trazia o local. NÃO "
                    "foi transcrito do livro: confira no livro antes de "
                    "certificar outro lugar.")
                dados = _historico(dados, {
                    "quando": quando, "registro": "AUTO-LOCAL-PRESUMIDO",
                    "pedido_por": DECISAO, "fonte": fonte,
                    "alteracoes": alteracoes})
                saida["pela_naturalidade" if fonte.startswith("natural")
                      else "pela_sede"] += 1

        # ---------------------------------------------- a matrícula
        if not re.sub(r"\D", "", _texto(a.get("matricula"))) and cns:
            transcrito = dados.get("acervo_transcrito") or {}
            folha = _texto(dados.get("folha")) or _texto(
                transcrito.get("folha") if isinstance(transcrito, dict) else "")
            termo = a.get("numero") or dados.get("termo")
            try:
                matricula = MAT.compor_do_assento(
                    {"especie": a["especie"], "data_ato": a.get("data_ato"),
                     "livro": livro, "folha": folha, "numero": termo},
                    cns=cns)
            except MAT.MatriculaError:
                matricula = ""
            if matricula and MAT.confere(matricula)["ok"] and folha and termo:
                sets["matricula"] = matricula
                dados["matricula"] = matricula
                dados = _historico(dados, {
                    "quando": quando, "registro": "AUTO-MATRICULA",
                    "pedido_por": "decisão do oficial em 19/11/2026: resolver "
                                  "as matrículas vazias",
                    "composicao": {"fonte": "rc_matricula.compor (Anexo IV CRC)",
                                   "livro": livro, "folha": folha,
                                   "termo": termo,
                                   "ano_registro": _texto(a.get("data_ato"))[:4]},
                    "alteracoes": [{"campo": "rc_assentos.matricula",
                                    "antes": None, "depois": matricula}]})
                saida["matriculas"] += 1

        if sets:
            sets["dados_json"] = json.dumps(dados, ensure_ascii=False)
            colunas = ", ".join(f"{c}=%s" for c in sets)
            bd.escrever(f"UPDATE rc_assentos SET {colunas} WHERE id=%s",
                        tuple(sets.values()) + (int(a["id"]),))
    return saida
