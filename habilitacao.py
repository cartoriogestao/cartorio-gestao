"""A habilitação de casamento — as regras. Domínio, sem tela e sem rede.

A ORDEM NÃO SE PULA, e cada etapa protege alguém:

    abrir            os nubentes se apresentam e dizem o que pretendem
    documentos       o que a lei exige, item por item (CC art. 1.525)
    edital           publica-se, e corre o prazo legal (L6015 art. 67 §1º)
    oposição         qualquer pessoa pode opor impedimento, nesse prazo
    habilitar        o oficial atesta que nada obsta (art. 1.531)
    celebrar         dentro dos noventa dias da certidão (art. 1.532)

    Habilitar sem edital é tirar de terceiro o direito de opor impedimento —
    e é o impedimento que anula o casamento depois. Celebrar com habilitação
    vencida é celebrar sem habilitação.

QUEM RECUSA É ESTE MÓDULO, E NÃO A TELA. A tela esconde o botão por educação;
    o domínio recusa por dever. Há teste que manda o ato fora de ordem direto
    para a função, sem passar pela tela.

O QUE NÃO ESTÁ AQUI, E POR QUÊ
    Nenhuma função calcula se um impedimento PROCEDE. Impedimento é matéria de
    direito e a decisão é do oficial — o módulo registra o que ele decidiu, com
    o fundamento escrito, e nunca decide por ele. É a mesma regra do usucapião
    e da lista de fraudes.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import date, timedelta
from typing import Any

import hc_schema as HC


class HabilitacaoError(ValueError):
    """Impedimento de regra, com mensagem pronta para o balcão."""


# --------------------------------------------------------------- ajudas


def _txt(v: Any) -> str | None:
    v = str(v or "").strip()
    return v or None


def _dia(v: Any) -> date | None:
    try:
        return date.fromisoformat(str(v)[:10])
    except (TypeError, ValueError):
        return None


def _norm(nome: Any) -> str | None:
    from pt_schema import normalizar_nome
    n = _txt(nome)
    return normalizar_nome(n) if n else None


def _andamento(con: sqlite3.Connection, habilitacao_id: int, o_que: str, *,
               quando: str, detalhe: str | None = None,
               antes: str | None = None, depois: str | None = None,
               quem: str | None = None) -> None:
    """Uma linha do histórico. ESCREVE, dentro da transação de quem chama.

    O ANDAMENTO É PARTE DO ATO, e não um registro paralelo: num processo de
    semanas, «o que aconteceu e quando» é a pergunta que mais se repete, e a
    resposta não pode depender de alguém ter lembrado de anotar.
    """
    con.execute(
        """INSERT INTO hc_andamento(habilitacao_id, quando, o_que, detalhe,
               situacao_antes, situacao_depois, quem)
           VALUES (?,?,?,?,?,?,?)""",
        (int(habilitacao_id), quando, o_que, detalhe, antes, depois, quem))


def _hab(con: sqlite3.Connection, habilitacao_id: int) -> sqlite3.Row:
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT * FROM hc_habilitacoes WHERE id=?",
                    (int(habilitacao_id),)).fetchone()
    if not r:
        raise HabilitacaoError(
            f"Habilitação {habilitacao_id} não encontrada.")
    return r


def _mudar(con: sqlite3.Connection, habilitacao_id: int, campos: dict) -> None:
    partes = ", ".join(f"{k}=?" for k in campos)
    con.execute(f"UPDATE hc_habilitacoes SET {partes} WHERE id=?",
                (*campos.values(), int(habilitacao_id)))


# ------------------------------------------------------------- abrir


def proximo_numero(con: sqlite3.Connection, ano: int) -> int:
    """O próximo número do exercício. Só LÊ.

    Por EXERCÍCIO, como o recibo do caixa e a certidão: a habilitação é peça
    que se arquiva por ano, e «habilitação 12/2026» é como o balcão a chama.
    """
    con.row_factory = sqlite3.Row
    r = con.execute("SELECT MAX(numero) n FROM hc_habilitacoes WHERE ano=?",
                    (int(ano),)).fetchone()
    return int((r["n"] or 0)) + 1


def abrir(con: sqlite3.Connection, dados: dict, *, agora: str,
          usuario: str | None = None) -> int:
    """Abre o processo e monta o checklist da lei. ESCREVE.

    O CHECKLIST NASCE COM O PROCESSO, e não se monta depois: item que alguém
    tem de lembrar de acrescentar é item que fica de fora. São os cinco incisos
    do art. 1.525, e cada um vale **para cada nubente** — a certidão de
    nascimento de um não supre a do outro.

    A PROVA DE DISSOLUÇÃO SÓ ENTRA PARA QUEM PRECISA DELA (inciso V, «quando
    for o caso»): pedi-la a quem é solteiro é pedir papel que não existe, e
    checklist com item impossível é checklist que se ignora inteiro.
    """
    for campo, rotulo in (("nubente1_nome", "o nome do primeiro nubente"),
                          ("nubente2_nome", "o nome do segundo nubente")):
        if not _txt(dados.get(campo)):
            raise HabilitacaoError(f"A habilitação não abre sem {rotulo}.")

    tipo = (_txt(dados.get("tipo")) or "CIVIL").upper()
    if tipo not in HC.TIPOS:
        raise HabilitacaoError(
            f"Tipo de casamento desconhecido: {tipo!r}. Os que existem são "
            f"{', '.join(HC.TIPOS)}.")
    regime = _txt(dados.get("regime"))
    if regime and regime.upper() not in HC.REGIMES:
        raise HabilitacaoError(
            f"Regime de bens desconhecido: {regime!r}. Os que existem são "
            f"{', '.join(HC.REGIMES)}.")

    ano = int(str(agora)[:4])
    numero = proximo_numero(con, ano)
    colunas = {
        "numero": numero, "ano": ano,
        "data_entrada": _txt(dados.get("data_entrada")) or str(agora)[:10],
        "tipo": tipo, "regime": (regime or "").upper() or None,
        "situacao": "EM_ANALISE",
        "observacao": _txt(dados.get("observacao")),
        "origem": "MANUAL", "criado_em": agora, "criado_por": usuario,
        # NA CONVERSÃO, QUE UNIÃO SE CONVERTE. Ele entra aqui se já vier no
        # balcão, e pode ser anotado depois — o casal às vezes traz a escritura
        # numa segunda ida. Sem ele o selo da conversão não sai, e é o próprio
        # contrato do selador que o exige.
        "uniao_estavel_processo": _txt(dados.get("uniao_estavel_processo")),
    }
    for lado in ("nubente1", "nubente2"):
        for campo in ("nome", "nome_pos", "sexo", "nascimento", "documento",
                      "estado_civil", "profissao", "nacionalidade",
                      "naturalidade", "endereco", "pai", "mae"):
            colunas[f"{lado}_{campo}"] = _txt(dados.get(f"{lado}_{campo}"))
        colunas[f"{lado}_nome_norm"] = _norm(dados.get(f"{lado}_nome"))

    marcas = ",".join("?" * len(colunas))
    cur = con.execute(
        f"INSERT INTO hc_habilitacoes ({','.join(colunas)}) VALUES ({marcas})",
        tuple(colunas.values()))
    novo = int(cur.lastrowid)

    for codigo, descricao, fundamento in HC.DOCUMENTOS_DA_HABILITACAO:
        for lado in ("NUBENTE1", "NUBENTE2"):
            if codigo == "PROVA_DISSOLUCAO":
                estado = (colunas[f"{lado.lower()}_estado_civil"] or "").upper()
                if estado.startswith("SOLTEIR") or not estado:
                    continue
            con.execute(
                """INSERT INTO hc_documentos(habilitacao_id, codigo, descricao,
                       fundamento, de_quem, criado_em)
                   VALUES (?,?,?,?,?,?)""",
                (novo, codigo, descricao, fundamento, lado, agora))

    _andamento(con, novo, "Processo aberto", quando=agora,
               detalhe=f"{colunas['nubente1_nome']} e {colunas['nubente2_nome']}",
               depois="EM_ANALISE", quem=usuario)
    return novo


# --------------------------------------------------------- documentos


def marcar_documento(con: sqlite3.Connection, documento_id: int, *,
                     apresentado: bool, agora: str,
                     usuario: str | None = None) -> None:
    """Marca um item do checklist como apresentado, ou desmarca. ESCREVE."""
    con.row_factory = sqlite3.Row
    d = con.execute("SELECT * FROM hc_documentos WHERE id=?",
                    (int(documento_id),)).fetchone()
    if not d:
        raise HabilitacaoError("Item de documento não encontrado.")
    con.execute(
        """UPDATE hc_documentos SET apresentado=?, apresentado_em=?,
               apresentado_por=? WHERE id=?""",
        (1 if apresentado else 0, agora if apresentado else None,
         usuario if apresentado else None, int(documento_id)))
    _andamento(con, d["habilitacao_id"],
               "Documento apresentado" if apresentado
               else "Documento desmarcado",
               quando=agora, detalhe=f"{d['descricao']} ({d['de_quem']})",
               quem=usuario)


def dispensar_documento(con: sqlite3.Connection, documento_id: int, *,
                        motivo: str, agora: str,
                        usuario: str | None = None) -> None:
    """Dispensa um item, com motivo escrito. ESCREVE.

    DISPENSAR EXIGE MOTIVO, como no usucapião: dispensar é decisão do oficial,
    e ignorar não é. O motivo fica no processo e é o que a inspeção lê quando
    perguntar por que a habilitação correu sem aquele papel.
    """
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise HabilitacaoError(
            "Escreva o motivo da dispensa com pelo menos dez letras — é ele "
            "que responde, depois, por que a habilitação correu sem este "
            "documento.")
    con.row_factory = sqlite3.Row
    d = con.execute("SELECT * FROM hc_documentos WHERE id=?",
                    (int(documento_id),)).fetchone()
    if not d:
        raise HabilitacaoError("Item de documento não encontrado.")
    con.execute(
        """UPDATE hc_documentos SET dispensado=1, dispensado_motivo=?,
               dispensado_em=?, dispensado_por=? WHERE id=?""",
        (motivo, agora, usuario, int(documento_id)))
    _andamento(con, d["habilitacao_id"], "Documento dispensado", quando=agora,
               detalhe=f"{d['descricao']} ({d['de_quem']}) — {motivo}",
               quem=usuario)


def o_que_falta(con: sqlite3.Connection, habilitacao_id: int) -> list[dict]:
    """Os itens ainda não apresentados nem dispensados. Só LÊ."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        """SELECT * FROM hc_documentos
            WHERE habilitacao_id=? AND apresentado=0 AND dispensado=0
            ORDER BY id""", (int(habilitacao_id),))]


# -------------------------------------------------------------- edital


def publicar_edital(con: sqlite3.Connection, habilitacao_id: int, *,
                    teor: str, agora: str, hoje: str | None = None,
                    usuario: str | None = None) -> dict:
    """Publica o edital de proclamas e abre o prazo de HC.PRAZO_DO_EDITAL dias. ESCREVE.

    NÃO SE PUBLICA COM DOCUMENTO FALTANDO. O edital chama terceiros a opor
    impedimento; chamá-los antes de a casa ter conferido o que a lei exige é
    pedir que o público faça a conferência que é do oficial.

    O TEOR CONGELA, com hash — é papel que fica afixado e que alguém pode vir
    contestar meses depois. A mesma forma da certidão e do edital do Protesto.
    """
    h = _hab(con, habilitacao_id)
    if h["situacao"] not in ("EM_ANALISE",):
        raise HabilitacaoError(
            f"Esta habilitação está {HC.SITUACOES.get(h['situacao'], h['situacao']).lower()} "
            f"— o edital só se publica com o processo em análise.")
    faltam = o_que_falta(con, habilitacao_id)
    if faltam:
        quais = "; ".join(f"{d['descricao']} ({d['de_quem']})" for d in faltam[:3])
        raise HabilitacaoError(
            f"Faltam {len(faltam)} documento(s) para publicar o edital: {quais}"
            f"{'…' if len(faltam) > 3 else ''}. Apresente ou dispense com "
            f"motivo escrito.")
    teor = (teor or "").strip()
    if len(teor) < 40:
        raise HabilitacaoError(
            "O teor do edital não pode sair em branco — é ele que fica "
            "afixado, e é sobre ele que alguém pode opor impedimento.")

    dia = _dia(hoje or agora) or date.today()
    ate = dia + timedelta(days=HC.PRAZO_DO_EDITAL)
    assinatura = hashlib.sha256(
        json.dumps({"habilitacao": int(habilitacao_id), "teor": teor,
                    "publicado": dia.isoformat()},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    _mudar(con, habilitacao_id, {
        "situacao": "EDITAL_PUBLICADO", "edital_em": dia.isoformat(),
        "edital_prazo_ate": ate.isoformat(), "edital_teor": teor,
        "edital_hash": assinatura})
    _andamento(con, habilitacao_id, "Edital de proclamas publicado",
               quando=agora,
               detalhe=f"prazo de {HC.PRAZO_DO_EDITAL} dias, até {ate.isoformat()}",
               antes=h["situacao"], depois="EDITAL_PUBLICADO", quem=usuario)
    return {"publicado_em": dia.isoformat(), "prazo_ate": ate.isoformat(),
            "hash": assinatura}


def prazo_vencido(h: sqlite3.Row | dict, hoje: Any = None) -> bool:
    """O prazo do edital já se esgotou? Só calcula."""
    ate = _dia(h["edital_prazo_ate"] if "edital_prazo_ate" in
               (h.keys() if hasattr(h, "keys") else h) else None)
    if not ate:
        return False
    return (_dia(hoje) or date.today()) > ate


# ------------------------------------------------------------ oposição


def registrar_publicacao(con: sqlite3.Connection, habilitacao_id: int, *,
                         protocolo: str, agora: str,
                         usuario: str | None = None) -> None:
    """Guarda o protocolo que o e-Proclamas devolveu. ESCREVE.

    O EDITAL DESTA CASA VAI PARA A CRC — informação do oficial em 28/08/2026:
    ele não é afixado no lugar de costume nem publicado na imprensa; é
    **publicado digitalmente no e-Proclamas**.

    Edital afixado se prova com o papel na parede. Edital publicado na Central
    se prova com o número que ela devolve — e sem ele, meses depois, ninguém
    mostra que a publicação aconteceu.

    O ENVIO À CENTRAL AINDA NÃO É DAQUI. Enquanto a integração não existir, o
    escrevente publica no e-Proclamas e anota o protocolo aqui. Guardar o
    número é o que se pode fazer com verdade hoje — e é mais do que guardar
    nada.
    """
    protocolo = (protocolo or "").strip()
    if not protocolo:
        raise HabilitacaoError(
            "Informe o protocolo que o e-Proclamas devolveu — é ele que prova "
            "que a publicação aconteceu.")
    h = _hab(con, habilitacao_id)
    if not h["edital_em"]:
        raise HabilitacaoError(
            "Publique o edital aqui primeiro: é dele que sai o teor que vai "
            "para a Central, e é dele que corre o prazo.")
    _mudar(con, habilitacao_id, {"eproclamas_protocolo": protocolo,
                                 "eproclamas_em": str(agora)[:10]})
    _andamento(con, habilitacao_id, "Publicado no e-Proclamas", quando=agora,
               detalhe=f"protocolo {protocolo}", quem=usuario)


def registrar_oposicao(con: sqlite3.Connection, habilitacao_id: int, *,
                       quem: str, teor: str, agora: str,
                       usuario: str | None = None) -> None:
    """Registra impedimento oposto por terceiro. ESCREVE.

    QUEM OPÕE TEM NOME, e o teor fica inteiro: o oficial vai decidir sobre
    aquilo, e a decisão dele se lê contra o que foi oposto — não contra um
    resumo.

    O MÓDULO NÃO JULGA. Se o impedimento procede é matéria de direito, e a
    decisão é do delegatário.
    """
    h = _hab(con, habilitacao_id)
    if h["situacao"] not in ("EDITAL_PUBLICADO", "EM_ANALISE"):
        raise HabilitacaoError(
            "Só se opõe impedimento a processo em análise ou com edital "
            "publicado.")
    quem = (quem or "").strip()
    teor = (teor or "").strip()
    if not quem:
        raise HabilitacaoError("Diga quem está opondo o impedimento.")
    if len(teor) < 10:
        raise HabilitacaoError(
            "Escreva o que foi oposto — é sobre este texto que a decisão vai "
            "ser fundamentada.")
    _mudar(con, habilitacao_id, {
        "situacao": "COM_OPOSICAO", "oposicao_em": str(agora)[:10],
        "oposicao_quem": quem, "oposicao_teor": teor})
    _andamento(con, habilitacao_id, "Impedimento oposto", quando=agora,
               detalhe=f"por {quem}", antes=h["situacao"],
               depois="COM_OPOSICAO", quem=usuario)


def decidir_oposicao(con: sqlite3.Connection, habilitacao_id: int, *,
                     decisao: str, fundamento: str, agora: str,
                     usuario: str | None = None) -> None:
    """O oficial decide sobre o impedimento oposto. ESCREVE.

    ACOLHIDA arquiva o processo; REJEITADA o devolve ao ponto em que estava.
    Nos dois casos o FUNDAMENTO é obrigatório: é ele que responde ao que foi
    oposto, e é ele que o juiz lê se a decisão for questionada.
    """
    decisao = (decisao or "").strip().upper()
    if decisao not in ("ACOLHIDA", "REJEITADA"):
        raise HabilitacaoError(
            "A decisão sobre o impedimento é ACOLHIDA ou REJEITADA.")
    fundamento = (fundamento or "").strip()
    if len(fundamento) < 20:
        raise HabilitacaoError(
            "Escreva o fundamento da decisão com pelo menos vinte letras — é "
            "ele que responde ao impedimento oposto.")
    h = _hab(con, habilitacao_id)
    if h["situacao"] != "COM_OPOSICAO":
        raise HabilitacaoError("Esta habilitação não tem impedimento oposto.")

    volta = "ARQUIVADO" if decisao == "ACOLHIDA" else (
        "EDITAL_PUBLICADO" if h["edital_em"] else "EM_ANALISE")
    campos = {"situacao": volta, "oposicao_decidida_em": str(agora)[:10],
              "oposicao_decisao": decisao, "oposicao_fundamento": fundamento}
    if decisao == "ACOLHIDA":
        campos["arquivado_em"] = str(agora)[:10]
        campos["arquivado_motivo"] = f"impedimento acolhido: {fundamento}"
    _mudar(con, habilitacao_id, campos)
    _andamento(con, habilitacao_id, f"Impedimento {decisao.lower()}",
               quando=agora, detalhe=fundamento, antes="COM_OPOSICAO",
               depois=volta, quem=usuario)


# ---------------------------------------------------------- habilitar


def habilitar(con: sqlite3.Connection, habilitacao_id: int, *, agora: str,
              hoje: str | None = None, usuario: str | None = None,
              teor: str | None = None) -> dict:
    """O oficial atesta que nada obsta ao casamento. ESCREVE.

    CC art. 1.531: cumpridas as formalidades e verificada a inexistência de
    fato obstativo, o oficial extrairá o certificado de habilitação.

    DUAS COISAS RECUSAM, e cada uma protege alguém:

      documento faltando   a lei exige, e o oficial atesta que foi cumprida
      edital não publicado habilitar sem edital tira de terceiro o direito de
                           opor impedimento — e é o impedimento que anula o
                           casamento depois

    O PRAZO DE OPOSIÇÃO continua em edital_prazo_ate / tela (informativo),
    mas **não impede** habilitar depois que o edital foi publicado
    (HOTFIX-2026-10-07-04). Oposição não decidida (COM_OPOSICAO) continua
    bloqueando.

    A CERTIDÃO VALE NOVENTA DIAS (CC art. 1.532), e a data-limite se grava
    agora: calcular na hora de celebrar faria a conta depender de quem
    pergunta.
    """
    h = _hab(con, habilitacao_id)
    if h["situacao"] == "HABILITADO":
        raise HabilitacaoError("Esta habilitação já foi expedida.")
    if h["situacao"] in ("ARQUIVADO", "CELEBRADO"):
        raise HabilitacaoError(
            f"Esta habilitação está {HC.SITUACOES.get(h['situacao'], '').lower()}.")
    if h["situacao"] == "COM_OPOSICAO":
        raise HabilitacaoError(
            "Há impedimento oposto e ainda não decidido. Decida antes de "
            "habilitar — habilitar por cima do impedimento é decidir sem dizer "
            "que decidiu.")
    faltam = o_que_falta(con, habilitacao_id)
    if faltam:
        raise HabilitacaoError(
            f"Faltam {len(faltam)} documento(s) do art. 1.525 do Código Civil. "
            f"Apresente ou dispense com motivo escrito.")
    if not h["edital_em"]:
        raise HabilitacaoError(
            "O edital de proclamas não foi publicado. Habilitar sem edital "
            "tira de terceiro o direito de opor impedimento.")
    # HOTFIX-2026-10-07-04: edital publicado basta para habilitar; o prazo
    # de oposição segue em edital_prazo_ate / tela, sem bloquear a certidão.

    dia = _dia(hoje or agora) or date.today()
    vale_ate = dia + timedelta(days=HC.VALIDADE_DA_HABILITACAO)
    ano = dia.year
    con.row_factory = sqlite3.Row
    ultimo = con.execute(
        "SELECT MAX(certidao_numero) n FROM hc_habilitacoes WHERE certidao_ano=?",
        (ano,)).fetchone()
    numero = int((ultimo["n"] or 0)) + 1
    corpo = (teor or "").strip() or None
    assinatura = hashlib.sha256(
        json.dumps({"habilitacao": int(habilitacao_id), "numero": numero,
                    "ano": ano, "em": dia.isoformat(), "teor": corpo},
                   ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    _mudar(con, habilitacao_id, {
        "situacao": "HABILITADO", "habilitado_em": dia.isoformat(),
        "habilitado_por": usuario,
        "habilitacao_vale_ate": vale_ate.isoformat(),
        "certidao_numero": numero, "certidao_ano": ano,
        "certidao_teor": corpo, "certidao_hash": assinatura})
    _andamento(con, habilitacao_id, "Habilitação expedida", quando=agora,
               detalhe=f"certidão {numero}/{ano}, vale até {vale_ate.isoformat()}",
               antes=h["situacao"], depois="HABILITADO", quem=usuario)
    return {"numero": numero, "ano": ano, "vale_ate": vale_ate.isoformat(),
            "hash": assinatura}


def cancelar_expedicao_sem_selo(
        con: sqlite3.Connection, habilitacao_id: int, *, agora: str,
        usuario: str | None, motivo: str) -> None:
    """Cancela só a EXPEDIÇÃO cujo selo não saiu. ESCREVE.

    Os documentos recebidos, o edital e o prazo continuam válidos. O que não
    pode ficar de pé é a certidão: ela só é expedida quando o selo também é
    emitido. Depois de corrigir o motivo, o mesmo processo volta ao botão
    ``Habilitar`` e recebe número, hash e validade numa nova tentativa.

    O andamento compensatório não apaga a tentativa anterior. Assim o
    histórico conta com verdade que a expedição começou e foi interrompida
    porque o selo falhou.
    """
    h = _hab(con, habilitacao_id)
    if h["situacao"] != "HABILITADO" or str(h["selo"] or "").strip():
        return
    volta = "EDITAL_PUBLICADO" if h["edital_em"] else "EM_ANALISE"
    _mudar(con, habilitacao_id, {
        "situacao": volta,
        "habilitado_em": None,
        "habilitado_por": None,
        "habilitacao_vale_ate": None,
        "certidao_numero": None,
        "certidao_ano": None,
        "certidao_teor": None,
        "certidao_hash": None,
    })
    _andamento(
        con, habilitacao_id, "Expedição não concluída — selo falhou",
        quando=agora, detalhe=(motivo or "falha sem detalhe").strip(),
        antes="HABILITADO", depois=volta, quem=usuario)


def habilitacao_vencida(h: sqlite3.Row | dict, hoje: Any = None) -> bool:
    """A certidão de habilitação já venceu? Só calcula."""
    chaves = h.keys() if hasattr(h, "keys") else h
    ate = _dia(h["habilitacao_vale_ate"] if "habilitacao_vale_ate" in chaves
               else None)
    if not ate:
        return False
    return (_dia(hoje) or date.today()) > ate


def valores_para_lavrar_casamento(h: sqlite3.Row | dict) -> dict:
    """Campos do formulário de casamento a partir da HC. Só LÊ."""
    chaves = h.keys() if hasattr(h, "keys") else h

    def _col(prefixo: str, campo: str) -> str:
        chave = f"{prefixo}_{campo}"
        return str(h[chave] or "").strip() if chave in chaves else ""

    def _pessoa(prefixo: str, lado: str) -> dict[str, str]:
        out = {
            f"{prefixo}_nome": _col(lado, "nome"),
            f"{prefixo}_nome_pos": _col(lado, "nome_pos"),
            f"{prefixo}_documento": _col(lado, "documento"),
            f"{prefixo}_estado_civil": _col(lado, "estado_civil"),
            f"{prefixo}_profissao": _col(lado, "profissao"),
            f"{prefixo}_nacionalidade": _col(lado, "nacionalidade"),
            f"{prefixo}_naturalidade": _col(lado, "naturalidade"),
            f"{prefixo}_endereco": _col(lado, "endereco"),
            f"{prefixo}_nascimento": _col(lado, "nascimento"),
            f"{prefixo}_sexo": _col(lado, "sexo"),
        }
        mae = _col(lado, "mae")
        pai = _col(lado, "pai")
        num = "1" if lado == "nubente1" else "2"
        if mae:
            out[f"filiacao1n{num}_nome"] = mae
        if pai:
            out[f"filiacao2n{num}_nome"] = pai
        return out

    regime = str(h["regime"] or "").strip() if "regime" in chaves else ""
    valores: dict[str, str] = {
        "regime_bens": regime,
        "habilitacao_id": str(int(h["id"])),
    }
    valores.update(_pessoa("nubente1", "nubente1"))
    valores.update(_pessoa("nubente2", "nubente2"))
    return {k: v for k, v in valores.items() if v}


def habilitacao_relacionada_ao_assento(con: sqlite3.Connection,
                                       assento_id: int) -> dict | None:
    """HC celebrada ou pendente ligada a este assento de casamento. Só LÊ."""
    con.row_factory = sqlite3.Row
    celebrada = con.execute(
        """SELECT * FROM hc_habilitacoes
            WHERE casamento_assento_id=?
            ORDER BY id DESC LIMIT 1""",
        (int(assento_id),)).fetchone()
    if celebrada:
        return dict(celebrada)
    ass = con.execute(
        "SELECT especie, dados_json FROM rc_assentos WHERE id=?",
        (int(assento_id),)).fetchone()
    if not ass:
        return None
    if str(ass["especie"] or "").upper() not in (
            "CASAMENTO", "CASAMENTO_RELIGIOSO"):
        return None
    try:
        dados = json.loads(ass["dados_json"] or "{}")
    except json.JSONDecodeError:
        dados = {}
    hid = dados.get("habilitacao_id")
    if not hid:
        return None
    pendente = con.execute(
        "SELECT * FROM hc_habilitacoes WHERE id=?", (int(hid),)).fetchone()
    if not pendente:
        return None
    if pendente["situacao"] != "HABILITADO":
        return dict(pendente)
    if habilitacao_vencida(pendente):
        return dict(pendente)
    return dict(pendente)


def casamentos_da_habilitacao(con: sqlite3.Connection,
                              habilitacao_id: int) -> list[dict]:
    """Os assentos de casamento lavrados A PARTIR desta habilitação. Só LÊ.

    A tela de lavrar grava `habilitacao_id` no `dados_json` do assento; é por
    ele que a ficha oferece o casamento para escolher, em vez de pedir um
    número que se confunde com o do termo (o defeito de 07/10/2026).
    """
    con.row_factory = sqlite3.Row
    achados = []
    for a in con.execute(
            """SELECT id, nome, numero, livro_volume, data_ato, dados_json
                 FROM rc_assentos
                WHERE especie IN ('CASAMENTO','CASAMENTO_RELIGIOSO')
                  AND dados_json LIKE '%habilitacao_id%'
             ORDER BY id DESC"""):
        try:
            hid = json.loads(a["dados_json"] or "{}").get("habilitacao_id")
        except json.JSONDecodeError:
            continue
        if hid and int(hid) == int(habilitacao_id):
            d = dict(a)
            d.pop("dados_json", None)
            achados.append(d)
    return achados


def registrar_celebracao(con: sqlite3.Connection, habilitacao_id: int, *,
                         assento_id: int, agora: str, hoje: str | None = None,
                         usuario: str | None = None) -> None:
    """Amarra o assento de casamento à habilitação que o autorizou. ESCREVE.

    NÃO SE CELEBRA SEM HABILITAÇÃO, E NÃO SE CELEBRA COM ELA VENCIDA — CC art.
    1.532. Passados os noventa dias, o processo se refaz: é o que a lei manda,
    e é o que protege o casamento de ser anulado depois.

    O ASSENTO TEM DE EXISTIR, e isso se confere. Foi a lição do usucapião: sem
    conferir, batia na chave estrangeira e virava HTTP 500 no fim de um
    processo de meses.
    """
    h = _hab(con, habilitacao_id)
    if h["situacao"] != "HABILITADO":
        raise HabilitacaoError(
            "Só se registra a celebração de habilitação expedida. Esta está "
            f"{HC.SITUACOES.get(h['situacao'], h['situacao']).lower()}.")
    if habilitacao_vencida(h, hoje or agora):
        raise HabilitacaoError(
            f"A habilitação venceu em {h['habilitacao_vale_ate']} (noventa "
            f"dias, CC art. 1.532). O processo precisa ser refeito.")
    existe = con.execute(
        "SELECT especie, nome, numero, livro_volume, dados_json "
        "FROM rc_assentos WHERE id=?", (int(assento_id),)).fetchone()
    if not existe:
        raise HabilitacaoError(
            f"O assento {assento_id} não existe — lavre o casamento antes de "
            f"amarrá-lo à habilitação.")
    # **SÓ SE CELEBRA EM ASSENTO DE CASAMENTO** — achado em 07/10/2026 na
    #   produção: a habilitação 1/2026 foi amarrada ao assento id 113, um
    #   NASCIMENTO de 1999, porque o balcão digitou o nº de ordem do casamento
    #   (113) onde o campo grava o código interno; e o selo da habilitação foi
    #   espelhado no registro daquele nascimento. Corrigido à mão em 08/10.
    especie = str(existe["especie"] or "").upper()
    if especie not in ("CASAMENTO", "CASAMENTO_RELIGIOSO"):
        raise HabilitacaoError(
            f"O assento {assento_id} é de {especie.lower() or 'espécie sem nome'} "
            f"({existe['nome'] or 'sem nome'}, Livro {existe['livro_volume'] or '?'}"
            f", nº {existe['numero'] or '?'}), e não de casamento. Escolha o "
            f"casamento na lista — o número pedido é o código do assento, e não "
            f"o número do termo.")
    try:
        ligada = json.loads(existe["dados_json"] or "{}").get("habilitacao_id")
    except (json.JSONDecodeError, AttributeError):
        ligada = None
    if ligada and int(ligada) != int(habilitacao_id):
        raise HabilitacaoError(
            f"O casamento {assento_id} foi lavrado a partir de outra "
            f"habilitação (#{ligada}) — um casamento não pode responder a duas.")
    outro = con.execute(
        """SELECT id, numero, ano FROM hc_habilitacoes
            WHERE casamento_assento_id=? AND id<>?""",
        (int(assento_id), int(habilitacao_id))).fetchone()
    if outro:
        raise HabilitacaoError(
            f"O assento {assento_id} já está ligado à habilitação "
            f"{outro['numero']}/{outro['ano']} — um casamento não pode "
            f"responder a duas habilitações.")
    _mudar(con, habilitacao_id, {
        "situacao": "CELEBRADO", "casamento_assento_id": int(assento_id),
        "celebrado_em": str(hoje or agora)[:10]})
    # O SELO DA HABILITACAO PASSA A SER O DO ASSENTO — um selo só, e ele já
    # foi comprado. Sem isto o assento apareceria em `atos_sem_selo` para
    # sempre, e alguém acabaria comprando um segundo selo para tirá-lo de lá.
    espelhado = espelhar_o_selo_no_assento(con, habilitacao_id)
    _andamento(con, habilitacao_id, "Casamento celebrado", quando=agora,
               detalhe=(f"assento {assento_id}"
                        + (f", selo {espelhado} anotado nele" if espelhado
                           else "")),
               antes="HABILITADO", depois="CELEBRADO", quem=usuario)


def espelhar_o_selo_no_assento(con: sqlite3.Connection,
                              habilitacao_id: int) -> str | None:
    """Põe no assento de casamento o selo que a habilitação já comprou. ESCREVE.

    UM SELO SO, E ELE E O DA HABILITACAO — decisão do oficial em 28/08/2026:
    *«o selo é emitido uma vez apenas; ele é reaproveitado apenas no assento,
    mas já foi emitido na habilitação»*. E a tabela de custas concorda: o item
    `14.1.1` é um só, e cobre «habilitação **e registro**».

    NÃO COMPRA NADA, E NÃO FALA COM A REDE. Só copia um número que já existe —
    é por isso que ela pode rodar dentro da transação de quem chama, ao
    contrário de tudo o mais que envolve selo neste sistema.

    NÃO SOBRESCREVE SELO QUE JÁ ESTÁ LÁ. Se o assento já tem selo — porque
    alguém o digitou à mão quando o aparelho estava fora do ar —, é esse que
    vale: o que está no papel assinado manda sobre o que o sistema deduz.

    RODA NAS DUAS ORDENS, e é por isso que ela é uma função e não duas linhas
    dentro de `registrar_celebracao`: o selo pode chegar depois da celebração
    (aparelho fora do ar na hora de expedir), e a celebração pode chegar depois
    do selo (o caso comum). Chamada nos dois momentos, ela acerta os dois.

    Devolve o número do selo que espelhou, ou None quando não havia o que
    espelhar — e não havia é situação normal, não defeito.
    """
    h = _hab(con, habilitacao_id)
    selo = (h["selo"] or "").strip()
    assento_id = h["casamento_assento_id"]
    if not selo or not assento_id:
        return None
    ato = con.execute(
        """SELECT id, COALESCE(selo,'') selo FROM rc_atos
            WHERE assento_id = ? AND tipo = 'REGISTRO'
            ORDER BY id LIMIT 1""", (int(assento_id),)).fetchone()
    if not ato or ato["selo"].strip():
        return None
    con.execute("UPDATE rc_atos SET selo = ? WHERE id = ?",
                (selo, int(ato["id"])))
    return selo


def registrar_uniao_estavel(con: sqlite3.Connection, habilitacao_id: int, *,
                            processo: str, agora: str,
                            usuario: str | None = None) -> None:
    """Anota qual união estável esta conversão converte. ESCREVE.

    POR QUE ISTO É CAMPO, E NÃO DETALHE DA OBSERVAÇÃO
        O contrato do selador exige `numeroProcesso` na conversão, e a
        descrição dele diz «número do processo da união estável» — não é o
        número desta habilitação. Guardado dentro de um texto livre, ninguém o
        acharia na hora de selar.

    SÓ FAZ SENTIDO NA CONVERSÃO, e por isso as outras são recusadas: anotar
    união estável num casamento civil comum é dado que confunde quem ler
    depois.
    """
    processo = (processo or "").strip()
    if not processo:
        raise HabilitacaoError(
            "Escreva o número do processo, da escritura ou do registro da "
            "união estável que está sendo convertida.")
    h = _hab(con, habilitacao_id)
    if str(h["tipo"] or "").upper() != "CONVERSAO":
        raise HabilitacaoError(
            "Só a conversão de união estável em casamento tem união estável a "
            "citar. Este processo é de casamento "
            f"{HC.TIPOS.get(h['tipo'], h['tipo']).lower()}.")
    _mudar(con, habilitacao_id, {"uniao_estavel_processo": processo})
    _andamento(con, habilitacao_id, "União estável anotada", quando=agora,
               detalhe=processo, quem=usuario)


def arquivar(con: sqlite3.Connection, habilitacao_id: int, *, motivo: str,
             agora: str, usuario: str | None = None) -> None:
    """Arquiva o processo, com motivo escrito. ESCREVE."""
    motivo = (motivo or "").strip()
    if len(motivo) < 10:
        raise HabilitacaoError(
            "Escreva o motivo do arquivamento com pelo menos dez letras.")
    h = _hab(con, habilitacao_id)
    if h["situacao"] == "CELEBRADO":
        raise HabilitacaoError(
            "Este casamento já foi celebrado — não se arquiva o processo que "
            "terminou em ato.")
    _mudar(con, habilitacao_id, {
        "situacao": "ARQUIVADO", "arquivado_em": str(agora)[:10],
        "arquivado_motivo": motivo})
    _andamento(con, habilitacao_id, "Processo arquivado", quando=agora,
               detalhe=motivo, antes=h["situacao"], depois="ARQUIVADO",
               quem=usuario)


# ------------------------------------------------------ o que fazer agora


def proximos_passos(con: sqlite3.Connection, habilitacao_id: int,
                    hoje: Any = None) -> list[str]:
    """O que falta fazer, calculado do estado. Só LÊ.

    Num rito de semanas, «e agora?» é a pergunta que mais se repete, e ela
    merece resposta na tela e não na cabeça de quem lembra. É a mesma peça do
    usucapião, e pelo mesmo motivo.
    """
    h = _hab(con, habilitacao_id)
    situacao = h["situacao"]
    if situacao == "ARQUIVADO":
        return [f"Processo arquivado em {h['arquivado_em']}: "
                f"{h['arquivado_motivo']}"]
    if situacao == "CELEBRADO":
        return [f"Casamento celebrado em {h['celebrado_em']}, assento "
                f"{h['casamento_assento_id']}. Nada a fazer."]
    if situacao == "COM_OPOSICAO":
        return [f"Decidir sobre o impedimento oposto por {h['oposicao_quem']} "
                f"em {h['oposicao_em']} — com fundamento escrito."]

    passos = []
    faltam = o_que_falta(con, habilitacao_id)
    if faltam:
        passos.append(
            f"Receber {len(faltam)} documento(s): "
            + "; ".join(f"{d['descricao']} ({d['de_quem'].lower()})"
                        for d in faltam[:3])
            + ("…" if len(faltam) > 3 else ""))
    if situacao == "EM_ANALISE":
        passos.append("Publicar o edital de proclamas" if not faltam
                      else "Publicar o edital, depois dos documentos")
    elif situacao == "EDITAL_PUBLICADO":
        if not h["eproclamas_protocolo"]:
            # A PUBLICAÇÃO NA CENTRAL É O QUE FAZ O EDITAL EXISTIR PARA FORA.
            # Lembrar disso é o trabalho desta linha: o prazo já está correndo,
            # e quem esquecer de publicar só descobre quando alguém perguntar.
            passos.append(
                f"Publicar o edital no {HC.ONDE_SE_PUBLICA} e anotar aqui o "
                f"protocolo que a Central devolver")
        # HOTFIX-2026-10-07-04: pode expedir assim que o edital está publicado.
        passos.append("Expedir a certidão de habilitação (botão «Habilitar»)")
        if not prazo_vencido(h, hoje):
            passos.append(
                f"Prazo de oposição em curso até {h['edital_prazo_ate']} "
                f"(informativo — não impede habilitar)")
        else:
            passos.append(
                f"Prazo de oposição encerrado em {h['edital_prazo_ate']}")
    elif situacao == "HABILITADO":
        if habilitacao_vencida(h, hoje):
            passos.append(
                f"A habilitação venceu em {h['habilitacao_vale_ate']} — o "
                f"processo precisa ser refeito (CC art. 1.532)")
        else:
            passos.append(
                f"Lavrar o assento de casamento (botão «Registrar casamento») "
                f"até {h['habilitacao_vale_ate']}")
            passos.append(
                "Depois da lavratura, registrar a celebração nesta ficha "
                "informando o número do assento")
    return passos


def listar(con: sqlite3.Connection, *, situacao: str | None = None,
           busca: str | None = None, limite: int = 200) -> list[dict]:
    """As habilitações, filtradas. Só LÊ."""
    con.row_factory = sqlite3.Row
    onde, params = ["1=1"], []
    if situacao:
        onde.append("situacao=?")
        params.append(situacao)
    if busca:
        alvo = f"%{_norm(busca) or ''}%"
        onde.append("(nubente1_nome_norm LIKE ? OR nubente2_nome_norm LIKE ? "
                    "OR CAST(numero AS TEXT) LIKE ?)")
        params += [alvo, alvo, f"%{busca.strip()}%"]
    return [dict(r) for r in con.execute(
        f"""SELECT * FROM hc_habilitacoes WHERE {' AND '.join(onde)}
             ORDER BY ano DESC, numero DESC LIMIT ?""",
        (*params, int(limite)))]


def andamento_de(con: sqlite3.Connection, habilitacao_id: int) -> list[dict]:
    """O histórico do processo, do mais antigo ao mais novo. Só LÊ."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM hc_andamento WHERE habilitacao_id=? ORDER BY id",
        (int(habilitacao_id),))]


def documentos_de(con: sqlite3.Connection, habilitacao_id: int) -> list[dict]:
    """O checklist inteiro, apresentados e não. Só LÊ."""
    con.row_factory = sqlite3.Row
    return [dict(r) for r in con.execute(
        "SELECT * FROM hc_documentos WHERE habilitacao_id=? ORDER BY id",
        (int(habilitacao_id),))]
