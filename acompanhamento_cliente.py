"""O CÓDIGO DE ACOMPANHAMENTO DO PROTOCOLO — o cliente vê o andamento sem
entrar no servidor da casa.

    «portal do cliente para acompanhar o pedido e baixar o recibo» — e, na
     escolha de como o cliente se identifica: «código no recibo».
     O oficial, 26/10/2026.

O QUE ESTE MÓDULO FAZ
    Cada protocolo geral (`cx_protocolos`) ganha, na primeira vez em que um
    papel dele é impresso, um CÓDIGO ALEATÓRIO de oito caracteres. O código sai
    no recibo e no protocolo de recepção, ao lado do número. Com NÚMERO + CÓDIGO
    o cliente vê a situação do pedido — no portal (a página da VPS, ver
    `portal_cliente.py` e `vps/portal/`) ou perguntando ao atendente do
    WhatsApp, que chama `consultar` daqui.

    Quem não tem o papel não consulta o protocolo de outra pessoa: o número é
    sequencial (`2026.10.57`, o 58 é o do vizinho) e por isso NÃO serve de
    senha; o código não se deduz do número — sai de `secrets`, e não de conta
    nenhuma sobre ele.

O QUE ESTE MÓDULO GUARDA, E POR QUÊ ASSIM
    `acompanhamento_hash` — o HASH do código (PBKDF2-SHA256, sal aleatório por
        protocolo, 200 mil voltas). É o que confere a consulta, aqui e na VPS.
        O código tem 8 caracteres de 32 = 40 bits: um SHA-256 simples se
        quebraria por força bruta em minutos com o hash na mão. Com 200 mil
        voltas por tentativa, a mesma busca leva séculos — e é isso que deixa o
        hash viajar para a VPS sem que a VPS vazada entregue os códigos.
    `acompanhamento_cifra` — o CÓDIGO CIFRADO (AES-GCM), com a chave no cofre da
        casa (`portal.cred`, `cofre_cred`), FORA do banco. É o que permite
        REIMPRIMIR o recibo com o mesmo código, e o balcão dizê-lo ao cliente
        pelo telefone. O código é uma senha do cliente: em texto claro, ele iria
        em todo backup do banco — a regra da casa para segredo (LX14) vale aqui.
        Só o hash, sem a cifra, obrigaria a trocar o código a cada reimpressão,
        e o papel que o cliente já tem deixaria de valer.
    `acompanhamento_em` — quando o código nasceu (ou foi trocado).

    PERDER A CHAVE DO COFRE NÃO TRANCA O BALCÃO: o código que não abre é
    TROCADO por um novo na próxima impressão (`codigo_do_protocolo`), e o papel
    novo sai com ele. O papel antigo deixa de valer — o que é o certo, porque
    ninguém mais sabe dizer qual era o código dele.

O QUE O CLIENTE VÊ (`consultar`)
    Número, situação em linguagem simples, previsão, última movimentação e a
    atribuição. NUNCA nome, CPF, valor, teor, assunto ou o que foi pedido. O
    PROTESTO fica fora de tudo (sigilo do art. 27 da Lei 9.492/97 — o próprio
    pedido de certidão é sigiloso): não ganha código, não sai no portal e a
    consulta responde como se o protocolo não existisse.

A MESMA RESPOSTA PARA «NÃO EXISTE» E PARA «CÓDIGO ERRADO»
    `consultar` devolve `None` nos dois casos, e gasta o mesmo tempo nos dois
    (o hash roda contra um falso quando o número não existe). Uma resposta que
    distinguisse diria a quem tenta adivinhar quais números existem.

QUEM MAIS USA ESTE MÓDULO
    O atendente de IA do WhatsApp (outro agente, em paralelo, 26/10/2026) chama
    `consultar(con, numero, codigo)` e lê `SITUACOES_PUBLICAS`. A ASSINATURA
    DAS QUATRO FUNÇÕES PÚBLICAS É CONTRATO — `gerar_codigo`,
    `codigo_do_protocolo`, `consultar` e `situacao_publica` —, e o guarda é
    `tests/test_acompanhamento_cliente.py::test_o_contrato_do_modulo`.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import logging
import os
import re
import secrets
import threading
import time
from datetime import date, datetime
from typing import Any, Mapping

from bd_nativo import banco

LOG = logging.getLogger("cartorio.acompanhamento")

# ------------------------------------------------------------------ o código

#: Sem 0/O e sem 1/I: ditado ao telefone ou lido num papel amassado, nenhum
#: caractere se confunde com outro. São 32 — 8 dígitos e 24 letras —, e cada
#: caractere vale exatamente 5 bits.
ALFABETO = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"
TAMANHO = 8

#: As voltas do PBKDF2. Ficam gravadas no próprio hash, e por isso podem subir
#: um dia sem invalidar os códigos de antes.
ITERACOES = 200_000
#: O teto que se aceita ao LER um hash: um hash gravado com um número absurdo de
#: voltas faria cada consulta prender o servidor.
ITERACOES_MAXIMAS = 2_000_000
PREFIXO_DO_HASH = "pbkdf2_sha256"

# ------------------------------------------------------------- as situações

#: O que o cliente lê, na língua do balcão. A chave é estável (o atendente do
#: WhatsApp e a VPS podem usá-la); o texto é o que aparece.
SITUACOES_PUBLICAS: dict[str, str] = {
    "EM_ATENDIMENTO": "em atendimento",
    "AGUARDANDO_PAGAMENTO": "aguardando pagamento",
    "EXIGENCIA": "aguardando documento/exigência",
    "PRONTO": "pronto para retirar",
    "ENTREGUE": "entregue",
    "CANCELADO": "cancelado",
    "PROCURE_O_CARTORIO": "procure o cartório",
}

#: A atribuição como o cliente a reconhece. O código interno não sai.
ATRIBUICOES_PUBLICAS: dict[str, str] = {
    "RI": "Registro de Imóveis",
    "NOTAS": "Tabelionato de Notas",
    "RCPN": "Registro Civil das Pessoas Naturais",
    "RTD": "Registro de Títulos e Documentos",
    "RCPJ": "Registro Civil das Pessoas Jurídicas",
    "FIRMAS": "Reconhecimento de firma e autenticação",
}

#: Atribuição que NÃO entra no acompanhamento — nem código, nem portal, nem
#: consulta. O protesto é sigiloso (Lei 9.492/97, art. 27).
FORA_DO_ACOMPANHAMENTO = frozenset({"PROTESTO"})

# ------------------------------------------------- a trava contra adivinhar

#: Quantos erros um MESMO NÚMERO aceita numa janela, nesta máquina. Passou
#: disso, a consulta daquele número responde `None` até a janela acabar —
#: inclusive com o código certo. É a mesma régua da VPS (`vps/portal/`), e é o
#: que impede o atendente do WhatsApp de virar uma porta de força bruta.
ERROS_POR_NUMERO = 10
JANELA_SEGUNDOS = 3600

_TENTATIVAS: dict[str, tuple[float, int]] = {}
_TRAVA_TENTATIVAS = threading.Lock()

# O cofre: um arquivo cifrado na pasta de dados, ao lado dos outros `.cred`.
ARQUIVO_DO_COFRE = "portal.cred"
CHAVE_DA_CIFRA = "chave_dos_codigos"
VERSAO_DA_CIFRA = "v1"


class AcompanhamentoError(ValueError):
    """Erro de regra, com a frase pronta para o balcão."""


# ================================================================ o código


def gerar_codigo() -> str:
    """Um código novo, aleatório: 8 caracteres de `ALFABETO`. Só calcula.

    `secrets`, e não `random`: o código é uma senha, e o gerador comum se
    prevê a partir de algumas saídas.
    """
    return "".join(secrets.choice(ALFABETO) for _ in range(TAMANHO))


def normalizar_codigo(texto: Any) -> str:
    """O código como foi digitado → o código como foi gerado. Só calcula.

    Aceita minúscula, espaço e hífen («abcd-efgh», «ABCD EFGH»). Não «corrige»
    0 para O nem 1 para I: nenhum dos quatro existe no alfabeto, e adivinhar
    o que o cliente quis dizer seria aceitar código errado.
    """
    return re.sub(r"[\s\-\.]", "", str(texto or "")).upper()


def formatar_codigo(codigo: Any) -> str:
    """«ABCDEFGH» → «ABCD-EFGH», para o papel e para ditar. Só calcula."""
    c = normalizar_codigo(codigo)
    return f"{c[:4]}-{c[4:]}" if len(c) == TAMANHO else c


def codigo_valido(codigo: Any) -> bool:
    c = normalizar_codigo(codigo)
    return len(c) == TAMANHO and all(x in ALFABETO for x in c)


def hash_do_codigo(codigo: Any, *, sal: bytes | None = None,
                   iteracoes: int = ITERACOES) -> str:
    """`pbkdf2_sha256$<voltas>$<sal hex>$<hash hex>`. Só calcula.

    O formato é o que a VPS lê (`vps/portal/portal_vps.py::confere`), e as duas
    pontas têm de concordar nele byte a byte.
    """
    sal = sal if sal is not None else os.urandom(16)
    feito = hashlib.pbkdf2_hmac("sha256", normalizar_codigo(codigo).encode("ascii"),
                                sal, int(iteracoes))
    return f"{PREFIXO_DO_HASH}${int(iteracoes)}${sal.hex()}${feito.hex()}"


# Um hash de mentira, para gastar o mesmo tempo quando o número não existe.
_HASH_DE_MENTIRA = None


def _hash_de_mentira() -> str:
    global _HASH_DE_MENTIRA
    if _HASH_DE_MENTIRA is None:
        _HASH_DE_MENTIRA = hash_do_codigo("2" * TAMANHO)
    return _HASH_DE_MENTIRA


def confere(codigo: Any, gravado: Any) -> bool:
    """O código bate com o hash gravado? Só calcula. Tempo constante no fim."""
    try:
        prefixo, voltas, sal, esperado = str(gravado or "").split("$")
        voltas_n = int(voltas)
        if prefixo != PREFIXO_DO_HASH or not 1 <= voltas_n <= ITERACOES_MAXIMAS:
            return False
        calculado = hashlib.pbkdf2_hmac(
            "sha256", normalizar_codigo(codigo).encode("ascii", "replace"),
            bytes.fromhex(sal), voltas_n).hex()
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(calculado, esperado)


# ================================================================ o cofre


def _pasta(con):
    import cofre_cred as COFRE
    return COFRE.pasta_do_banco(con)


def _chave_da_cifra(con, *, criar: bool) -> bytes | None:
    """A chave AES dos códigos, do `portal.cred`. Nasce na primeira vez."""
    import cofre_cred as COFRE
    pasta = _pasta(con)
    guardada = COFRE.ler(pasta, ARQUIVO_DO_COFRE).get(CHAVE_DA_CIFRA, "")
    if not guardada and criar:
        COFRE.gravar(pasta, ARQUIVO_DO_COFRE, {
            CHAVE_DA_CIFRA: base64.b64encode(os.urandom(32)).decode("ascii")})
        # RELIDA DO ARQUIVO, e não a que se acabou de sortear: duas impressões
        # ao mesmo tempo sorteiam duas chaves, e só a que ficou gravada abre.
        guardada = COFRE.ler(pasta, ARQUIVO_DO_COFRE).get(CHAVE_DA_CIFRA, "")
    try:
        chave = base64.b64decode(guardada) if guardada else b""
    except ValueError:
        return None
    return chave if len(chave) == 32 else None


def _associado(protocolo_id: int) -> bytes:
    # O id entra como dado associado: a cifra de um protocolo copiada para a
    # linha de outro não abre, em vez de entregar o código do primeiro.
    return f"cx_protocolos:{int(protocolo_id)}".encode("ascii")


def _cifrar(con, protocolo_id: int, codigo: str) -> str:
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    chave = _chave_da_cifra(con, criar=True)
    if chave is None:
        raise AcompanhamentoError(
            "O cofre da casa não tem uma chave válida para o código de "
            "acompanhamento. Confira a pasta de dados do servidor.")
    nonce = os.urandom(12)
    cifra = AESGCM(chave).encrypt(nonce, codigo.encode("ascii"),
                                  _associado(protocolo_id))
    return f"{VERSAO_DA_CIFRA}:" + base64.b64encode(nonce + cifra).decode("ascii")


def _decifrar(con, protocolo_id: int, texto: Any) -> str | None:
    """O código guardado, ou None quando não abre (chave perdida, linha mexida)."""
    from cryptography.exceptions import InvalidTag
    from cryptography.hazmat.primitives.ciphers.aead import AESGCM
    versao, _, corpo = str(texto or "").partition(":")
    if versao != VERSAO_DA_CIFRA or not corpo:
        return None
    chave = _chave_da_cifra(con, criar=False)
    if chave is None:
        return None
    try:
        bruto = base64.b64decode(corpo)
        claro = AESGCM(chave).decrypt(bruto[:12], bruto[12:],
                                      _associado(protocolo_id)).decode("ascii")
    except (ValueError, InvalidTag, UnicodeDecodeError):
        return None
    return claro if codigo_valido(claro) else None


# ============================================================ o protocolo


def elegivel(protocolo: Mapping) -> bool:
    """Este protocolo pode ter acompanhamento? Só calcula.

    Fora: o protesto (sigilo) e o protocolo de mero cálculo de emolumentos
    (`tipo = ORCAMENTO`), que não tem serviço para acompanhar.
    """
    atribuicao = str(protocolo.get("atribuicao") or "").strip().upper()
    if atribuicao in FORA_DO_ACOMPANHAMENTO:
        return False
    return str(protocolo.get("tipo") or "SERVICO").strip().upper() != "ORCAMENTO"


def _protocolo(con, protocolo_id: int, *, para_escrever: bool = False) -> dict:
    bd = banco(con)
    if para_escrever:
        # A trava da linha só vale dentro da transação: sem ela, duas
        # impressões ao mesmo tempo sorteariam dois códigos, e o primeiro
        # papel sairia com um código que já não vale.
        bd._escrita()
    linha = bd.um(
        "SELECT * FROM cx_protocolos WHERE id = %s"
        + (" FOR UPDATE" if para_escrever else ""), (int(protocolo_id),))
    if not linha:
        raise AcompanhamentoError(f"Não achei o protocolo id {protocolo_id}.")
    return dict(linha)


def _gravar_codigo_novo(con, p: Mapping) -> str:
    codigo = gerar_codigo()
    banco(con).escrever(
        """UPDATE cx_protocolos
              SET acompanhamento_hash = %s, acompanhamento_cifra = %s,
                  acompanhamento_em = %s,
                  -- código novo, retrato novo: a VPS tem de receber o hash
                  -- deste, e não continuar aceitando o de antes
                  portal_marca = NULL
            WHERE id = %s""",
        (hash_do_codigo(codigo), _cifrar(con, int(p["id"]), codigo),
         datetime.now().isoformat(timespec="seconds"), int(p["id"])))
    return codigo


def codigo_do_protocolo(con, protocolo_id: int) -> str:
    """O código de acompanhamento do protocolo; cria e grava na primeira vez.

    ESCREVE na primeira vez (e quando a cifra não abre mais); nas outras, só lê.
    Devolve os 8 caracteres, sem hífen (`formatar_codigo` põe o hífen do papel).

    Levanta `AcompanhamentoError` para protocolo que não tem acompanhamento
    (protesto, orçamento) e quando o cofre da casa não pode ser usado.
    """
    p = _protocolo(con, protocolo_id, para_escrever=True)
    if not elegivel(p):
        raise AcompanhamentoError(
            f"O protocolo {p['numero']} não tem código de acompanhamento: "
            + ("protesto é sigiloso e não entra no portal."
               if str(p.get("atribuicao") or "").upper() in FORA_DO_ACOMPANHAMENTO
               else "é de mero cálculo de emolumentos, sem serviço para acompanhar."))
    if p.get("acompanhamento_hash"):
        guardado = _decifrar(con, int(p["id"]), p.get("acompanhamento_cifra"))
        if guardado and confere(guardado, p["acompanhamento_hash"]):
            return guardado
        # A CIFRA NÃO ABRE (o cofre perdeu a chave, ou a linha foi mexida).
        # Ninguém sabe mais qual era o código: troca-se, e o papel novo sai com
        # o novo. Fica no log, para quem conferir saber por que mudou.
        LOG.warning("protocolo %s: o código de acompanhamento não pôde ser "
                    "relido do cofre e foi trocado", p["numero"])
    return _gravar_codigo_novo(con, p)


def codigo_ja_gravado(con, protocolo_id: int) -> str | None:
    """O código que o protocolo já tem, ou None. SÓ LÊ — é o da ficha (GET).

    Não cria: a tela que só mostra não abre transação de escrita (regra da
    casa). O código nasce quando um papel é impresso, ou no botão da ficha.
    """
    linha = banco(con).um(
        """SELECT id, acompanhamento_hash, acompanhamento_cifra
             FROM cx_protocolos WHERE id = %s""", (int(protocolo_id),))
    if not linha or not linha["acompanhamento_hash"]:
        return None
    try:
        guardado = _decifrar(con, int(linha["id"]), linha["acompanhamento_cifra"])
    except Exception:                                   # noqa: BLE001
        LOG.exception("o cofre não abriu para mostrar o código do protocolo")
        return None
    return guardado if guardado and confere(guardado, linha["acompanhamento_hash"]) else None


def trocar_codigo(con, protocolo_id: int) -> str:
    """Um código NOVO para o protocolo; o de antes deixa de valer. ESCREVE.

    É o botão da ficha do protocolo para quando o cliente perdeu o papel, ou o
    código foi visto por quem não devia.
    """
    p = _protocolo(con, protocolo_id, para_escrever=True)
    if not elegivel(p):
        raise AcompanhamentoError(
            f"O protocolo {p['numero']} não tem código de acompanhamento.")
    return _gravar_codigo_novo(con, p)


def codigo_para_o_papel(con, protocolo_id: Any, *,
                        endereco_do_portal: str | None = None,
                        criar: bool = True) -> dict | None:
    """O bloco do código para o recibo e o protocolo de recepção.

    Com `criar` (o padrão), ESCREVE na primeira vez — é o caminho das rotas
    POST que emitem o papel. Sem `criar`, SÓ LÊ o código que já existe — é o da
    reimpressão por GET, que não abre transação de escrita (regra da casa).

    NUNCA DERRUBA O PAPEL: protocolo sem acompanhamento, cofre fora do ar ou
    qualquer outro problema devolvem None, e o papel sai como saía antes — o
    recibo é prova de pagamento, e não pode deixar de sair por causa do portal.
    """
    if not protocolo_id:
        return None
    try:
        if criar:
            # NUM PONTO DE RETORNO: o papel é impresso dentro da transação do
            # recibo (ou da recepção), e um erro de banco aqui não pode
            # condenar a transação de fora — o recibo tem de sair do mesmo jeito.
            with banco(con).ponto_de_retorno("acompanhamento_cliente") as bd:
                codigo = codigo_do_protocolo(bd, int(protocolo_id))
                numero = bd.valor("SELECT numero FROM cx_protocolos WHERE id = %s",
                                  (int(protocolo_id),))
        else:
            codigo = codigo_ja_gravado(con, int(protocolo_id))
            if not codigo:
                return None
            numero = banco(con).valor("SELECT numero FROM cx_protocolos WHERE id = %s",
                                      (int(protocolo_id),))
    except AcompanhamentoError:
        return None
    except Exception:                                   # noqa: BLE001
        LOG.exception("o código de acompanhamento do protocolo %s não saiu no "
                      "papel", protocolo_id)
        return None
    endereco = str(endereco_do_portal or "").strip()
    if endereco:
        como = (f"Acompanhe o andamento em {endereco}, informando o número do "
                f"protocolo e este código. Guarde este papel: sem o código, a "
                f"consulta não é possível.")
    else:
        como = ("Para saber o andamento, informe o número do protocolo e este "
                "código ao cartório. Guarde este papel: sem o código, a "
                "consulta não é possível.")
    return {"numero": numero, "codigo": formatar_codigo(codigo),
            "como_consultar": como}


# ============================================================ a situação


def _etapa_do_ri(con, ri_protocolo_id: Any, hoje: str) -> str | None:
    """A etapa da prenotação ligada, pela régua do agente do RI. Só lê."""
    if not ri_protocolo_id:
        return None
    try:
        import ri_pedidos as RP
        bd = banco(con)
        prenotacao = bd.um("SELECT * FROM ri_protocolos WHERE id = %s",
                           (int(ri_protocolo_id),))
        if not prenotacao:
            return None
        prenotacao = dict(prenotacao)
        if not prenotacao.get("ato_id") and str(prenotacao.get("situacao") or "") \
                .upper() not in ("ABERTO", "DEVOLVIDO"):
            # Encerrada ou cancelada sem ato lavrado: quem explica é o balcão.
            return "ENCERRADA_SEM_ATO"
        quals = RP.qualificacoes_de(bd, int(ri_protocolo_id))
        return RP.etapa(prenotacao, quals[-1] if quals else None, hoje)
    except Exception:                                   # noqa: BLE001
        # A etapa do RI é um refinamento: sem ela, a situação sai dos itens.
        LOG.exception("etapa do RI do protocolo não pôde ser lida")
        return None


def _itens(con, protocolo_id: int) -> list[dict]:
    return [dict(r) for r in banco(con).ler(
        "SELECT * FROM cx_protocolo_atos WHERE protocolo_id = %s ORDER BY id",
        (int(protocolo_id),))]


def chave_da_situacao(con, protocolo: Mapping, *, hoje: str | None = None) -> str:
    """A chave de `SITUACOES_PUBLICAS` para este protocolo. Só lê.

    A ORDEM DAS PERGUNTAS É A REGRA:
      1. encerrado (ENTREGUE/CANCELADO) é o que está escrito, e acabou;
      2. o RI em exigência vem antes de tudo — é o cliente que tem de agir;
         prenotação vencida, ou encerrada sem ato, manda procurar o cartório;
      3. item sem pagar → aguardando pagamento;
      4. pronto: no RI, o ato lavrado; fora dele, todos os itens já gastos por
         ato (`quantidade_usada`, a régua do selo) — o ato foi praticado;
      5. o resto está em atendimento.
    """
    hoje = (hoje or date.today().isoformat())[:10]
    situacao = str(protocolo.get("situacao") or "").strip().upper()
    if situacao == "CANCELADO":
        return "CANCELADO"
    if situacao == "ENTREGUE":
        return "ENTREGUE"
    etapa = _etapa_do_ri(con, protocolo.get("ri_protocolo_id"), hoje)
    if etapa == "EM_EXIGENCIA":
        return "EXIGENCIA"
    if etapa in ("VENCIDA", "ENCERRADA_SEM_ATO"):
        return "PROCURE_O_CARTORIO"
    itens = _itens(con, int(protocolo["id"])) if protocolo.get("id") else []
    if any(not i.get("quitado") and not i.get("gratuito") for i in itens):
        return "AGUARDANDO_PAGAMENTO"
    if etapa == "REGISTRADO":
        return "PRONTO"
    if etapa is None and itens:
        import caixa_protocolo as CXP
        if all(CXP.saldo_do_item(i) <= 0 for i in itens):
            return "PRONTO"
    return "EM_ATENDIMENTO"


def situacao_publica(con, protocolo: Mapping, *, hoje: str | None = None) -> str:
    """O estado interno traduzido para o cliente, em linguagem simples. Só lê."""
    return SITUACOES_PUBLICAS[chave_da_situacao(con, protocolo, hoje=hoje)]


def _mais_recente(*valores: Any) -> str | None:
    datas = [str(v)[:16] for v in valores if v and re.match(r"\d{4}-\d{2}-\d{2}", str(v))]
    return max(datas) if datas else None


def atualizado_em(con, protocolo: Mapping) -> str | None:
    """A última movimentação do protocolo que se enxerga daqui. Só lê.

    É a mais recente entre a abertura, a recepção, o encerramento, a quitação e
    o uso dos itens, o recibo e a qualificação da prenotação do RI — tudo o que
    muda a situação pública. Calculada, e não uma coluna: uma coluna «mexido
    em» seria um segundo lugar dizendo o que estas datas já dizem.
    """
    bd = banco(con)
    pid = int(protocolo["id"])
    datas = [protocolo.get("criado_em"), protocolo.get("data_abertura"),
             protocolo.get("recepcao_em"), protocolo.get("data_finalizacao")]
    linha = bd.um(
        """SELECT max(quitado_em) AS q, max(usado_em) AS u
             FROM cx_protocolo_atos WHERE protocolo_id = %s""", (pid,))
    if linha:
        datas += [linha["q"], linha["u"]]
    datas.append(bd.valor("SELECT max(criado_em) FROM cx_recibos WHERE protocolo_id = %s",
                          (pid,)))
    if protocolo.get("ri_protocolo_id"):
        try:
            datas.append(bd.valor(
                "SELECT max(criado_em) FROM ri_qualificacoes WHERE protocolo_id = %s",
                (int(protocolo["ri_protocolo_id"]),)))
        except Exception:                               # noqa: BLE001
            pass
    return _mais_recente(*datas)


def retrato(con, protocolo: Mapping, *, hoje: str | None = None) -> dict:
    """O que o cliente pode ver deste protocolo — e NADA além. Só lê.

    É o mesmo dicionário de `consultar` e o miolo do que vai à VPS. Nome, CPF,
    valores, assunto e teor não entram nem por engano: a lista é fechada aqui.
    """
    atribuicao = str(protocolo.get("atribuicao") or "").strip().upper()
    return {
        "numero": str(protocolo["numero"]),
        "situacao_publica": situacao_publica(con, protocolo, hoje=hoje),
        "previsao": (str(protocolo.get("previsao_entrega"))[:10]
                     if protocolo.get("previsao_entrega") else None),
        "atualizado_em": atualizado_em(con, protocolo),
        "atribuicao": ATRIBUICOES_PUBLICAS.get(atribuicao, "Serviços do cartório"),
    }


# ============================================================ a consulta


def _travado(numero: str) -> bool:
    with _TRAVA_TENTATIVAS:
        inicio, erros = _TENTATIVAS.get(numero, (0.0, 0))
        if time.monotonic() - inicio > JANELA_SEGUNDOS:
            _TENTATIVAS.pop(numero, None)
            return False
        return erros >= ERROS_POR_NUMERO


def _anotar_erro(numero: str) -> None:
    with _TRAVA_TENTATIVAS:
        agora = time.monotonic()
        inicio, erros = _TENTATIVAS.get(numero, (agora, 0))
        if agora - inicio > JANELA_SEGUNDOS:
            inicio, erros = agora, 0
        _TENTATIVAS[numero] = (inicio, erros + 1)


def consultar(con, numero: str, codigo: str) -> dict | None:
    """NÚMERO + CÓDIGO → o retrato público do protocolo; None se não confere.

    Só lê. `None` quando o número não existe, quando o código está errado,
    quando o protocolo não tem acompanhamento (protesto, orçamento) e quando
    aquele número errou demais na última hora — sempre o mesmo `None`, para
    que quem tenta adivinhar não aprenda nada com a resposta.

    Devolve `{"numero", "situacao_publica", "previsao", "atualizado_em",
    "atribuicao"}`.
    """
    numero = str(numero or "").strip()[:40]
    if not numero or _travado(numero):
        # O mesmo trabalho do caminho que confere, para o tempo não contar.
        confere(codigo, _hash_de_mentira())
        return None
    linha = banco(con).um("SELECT * FROM cx_protocolos WHERE numero = %s", (numero,))
    p = dict(linha) if linha else None
    gravado = p.get("acompanhamento_hash") if p else None
    if not gravado or not elegivel(p):
        confere(codigo, _hash_de_mentira())
        _anotar_erro(numero)
        return None
    if not codigo_valido(codigo) or not confere(codigo, gravado):
        if not codigo_valido(codigo):
            confere(codigo, _hash_de_mentira())
        _anotar_erro(numero)
        return None
    return retrato(con, p)
