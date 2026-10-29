"""OS PEDIDOS DA CRA NO CLIQUE DO DIA — desistência (DP), cancelamento (CP) e
autorização (AC/AD), trazidos no mesmo clique em que a escrevente já traz a
remessa.

O QUE MOTIVOU (29/10/2026, medido só com leitura na produção)
    Desde a virada de 14/10/2026, o registro das Centrais (`centrais_log`,
    central CRA) tem Confirmacao (2), RemessaPendente (9), Retorno (31) e
    TituloComplemento (2) — e NENHUMA chamada a `Desistencia`, `Cancelamento`
    ou `Autorizacao`. `pt_desistencias` está vazia, e nenhum ato DESISTENCIA
    foi lançado pelo sistema desde a virada. Se algum credor desistiu ou
    autorizou cancelamento pela CRA nesse tempo, o sistema não soube — e um
    título desistido pode ter sido protestado. A ordem do oficial é simplificar
    sem nunca deixar título para trás: o clique diário da remessa passa a
    trazer tudo.

NUNCA BAIXAR SEM RECEBER
    As três operações estão em `cra21_api.OPERACOES_QUE_ESCREVEM`: baixar pode
    marcar o arquivo como baixado do lado da CRA. Por isso a resposta INTEIRA
    se grava em `pt_cra_consultas`, numa transação própria, LOGO DEPOIS da
    rede e ANTES de qualquer leitura. Se o banco recusar, ela vai para um
    arquivo na pasta dos arquivos; se o disco também recusar, ela volta à tela
    (`bruto_sem_lugar`) para não sumir das duas pontas. Só depois se lê.

    E NUNCA SE REPETE DEPOIS DE FALHA INCERTA. Cada operação vai UMA vez por
    clique, como a remessa: a falha de rede numa operação que escreve não se
    sabe se a CRA marcou — `cra21_api` já não repete sozinha, e este módulo
    também não. A falha incerta vira PENDÊNCIA («confira no portal da CRA»),
    porque o arquivo pode ter sido marcado como baixado e não ter chegado.

«NADA VEIO» TAMBÉM É REGISTRO
    A consulta que volta com o relatório de «não existe ... na data
    informada» (0006 na desistência, 0007 no cancelamento — página
    «Mensagens» do manual da P21) é uma linha `NADA`, e vai à auditoria como
    `cra_baixar` — a mesma ação que o roteiro do protesto já lê para saber se
    a consulta foi feita. O código de «nada» da AUTORIZAÇÃO não está no
    manual: até ele aparecer, a resposta de relatório na autorização é `AVISO`
    (amarelo), com o código e a frase da CRA, e não «nada» por palpite.

O NOME DO ARQUIVO PEDIDO
    `userArq` é o nome FEBRABAN (manual da P21, «Nomenclatura de arquivos»):
    prefixo + apresentante + dia + mês + `.AA` + sequência. Para trazer de
    TODOS os apresentantes, o apresentante vai `000` — é o precedente do
    E-Ofício nesta casa (as 47 remessas de 2026 da pasta «8. CRA» se chamam
    `B000ddmm.26s`, e a desistência de 26/08/2022 do apresentante 1LV veio
    como `DP0002608.221`) e é como `cra21_api.remessas_pendentes` já pede. O
    manual diz que a CRA confere o prefixo e a data.

O QUE SE FAZ COM O QUE VEIO
    DP — pelo caminho que já existe (`protesto_desistencia.aplicar`), só nos
        títulos que casam pelo protocolo E pelo número (os irmãos inclusive) e
        estão numa situação que aceita desistir. O resto vira pendência. A
        desistência de título já PROTESTADO é o caso grave — o protesto pode
        ter sido lavrado depois de o credor desistir — e vem destacada; a de
        título INTIMADO se aplica, e também vem destacada.
    CP, AC e AD — NÃO se lavram sozinhos: o cancelamento (e a desistência
        autorizada) exige o pagamento das custas pelo devedor. Cada título vira
        uma pendência, visível na ficha e na lista, com o arquivo guardado, até
        a escrevente lavrar o ato ou registrar por que não lavra.

UMA PENDÊNCIA SE FECHA DE DOIS JEITOS
    Pelo ato: o título chega à situação que o pedido pede (DESISTIDO para DP
    e AD, CANCELADO para CP e AC) — isso se mede na leitura, sem gravar nada.
    Ou pela escrevente, que registra o motivo de não lavrar (`tratar_pedido`).
    A desistência de título já protestado só o oficial ou o substituto
    encerram: manter um protesto de que o credor desistiu é decisão de quem
    responde pela serventia.
"""
from __future__ import annotations

from contextlib import AbstractContextManager
from datetime import date
import hashlib
from pathlib import Path
import re
from typing import Any, Callable

from bd_nativo import banco
import centrais_cred as CRED
import centrais_http as HTTP
import cra21_api as CRA
import protesto_desistencia as DS


class PedidoCraError(ValueError):
    """Erro de regra dos pedidos da CRA, com a frase pronta para o balcão."""


# AS TRÊS CONSULTAS, NA ORDEM DO CLIQUE. `o_que` é a opção de
# `cra21_web._trazer` — a MESMA porta da remessa, de propósito: quem simula a
# CRA num teste simula as quatro de uma vez, e nenhuma chamada escapa para a
# Central de verdade. `com_imagem` pede o anexo (a carta de anuência vem em
# `t10`, segundo o manual): sem ele, a pendência ficaria sem o papel que a
# fundamenta.
CONSULTAS: tuple[dict, ...] = (
    {"tipo": "DP", "operacao": "Desistencia", "o_que": "desistencias",
     "com_imagem": False, "rotulo": "Desistências (DP)"},
    {"tipo": "CP", "operacao": "Cancelamento", "o_que": "cancelamentos",
     "com_imagem": True, "rotulo": "Cancelamentos (CP)"},
    {"tipo": "AC", "operacao": "Autorizacao", "o_que": "autorizacoes",
     "com_imagem": True, "rotulo": "Autorizações de cancelamento (AC)"},
)
OPERACAO_DO_TIPO = {c["tipo"]: c["operacao"] for c in CONSULTAS}

# O «NADA VEIO» DE CADA OPERAÇÃO, do manual da P21 (página «Mensagens»). A
# autorização não tem código lá: fica vazia de propósito.
NADA_VEIO: dict[str, frozenset[str]] = {
    "DP": frozenset({"0006"}),
    "CP": frozenset({"0007"}),
    "AC": frozenset(),
}
# OS CÓDIGOS QUE DIZEM QUE O PEDIDO ESTAVA ERRADO — medidos na homologação em
# 12/09/2026 (`cra21_api.CODIGOS_MEDIDOS`): nome inválido e XML corrompido.
PEDIDO_RECUSADO = frozenset({"0002", "10000"})

# O resultado de cada consulta.
GUARDADO = "GUARDADO"      # o bruto entrou e a leitura não terminou
RECEBIDO = "RECEBIDO"      # veio arquivo, e ele foi lido
NADA = "NADA"              # a CRA disse que não há nada
AVISO = "AVISO"            # a CRA respondeu algo cujo sentido não está medido
FALHA = "FALHA"            # não houve resposta utilizável
NAO_LIDO = "NAO_LIDO"      # veio arquivo, ficou guardado, e não se leu
RESULTADOS_QUE_PEDEM_ACAO = (GUARDADO, NAO_LIDO)

# O estado de cada pedido (um por título).
PENDENTE = "PENDENTE"
APLICADO = "APLICADO"      # o sistema lavrou (só a desistência)
RESOLVIDO = "RESOLVIDO"    # o título já estava como o pedido pede
TRATADO = "TRATADO"        # a escrevente registrou por que não lavra

# A SITUAÇÃO QUE FECHA CADA PEDIDO.
SITUACAO_QUE_FECHA = {"DP": "DESISTIDO", "AD": "DESISTIDO",
                      "CP": "CANCELADO", "AC": "CANCELADO"}

# O DESTAQUE. PROTESTADO é o caso grave; INTIMADO é a desistência que chegou
# a tempo, por pouco.
GRAVE = "PROTESTADO"
POR_POUCO = "INTIMADO"

# Quantas letras o motivo de não lavrar precisa ter. Não é a afirmação
# expressa da casa (30 letras e a fórmula): aqui não se insiste num erro, se
# registra uma decisão — mas «ok» não é motivo.
MINIMO_DE_LETRAS = 15

# Quem encerra a desistência de título já protestado sem lavrar nada.
QUEM_ENCERRA_O_GRAVE = ("ADMIN", "MANAGER")

# DESDE QUANDO SE CONTA: a virada do protesto para o sistema.
VIRADA = "2026-10-14"

# O nome na tela de cada tipo.
NOME_DO_TIPO = {"DP": "desistência", "CP": "pedido de cancelamento",
                "AC": "autorização de cancelamento",
                "AD": "autorização de desistência"}


# ------------------------------------------------------------ o nome


def _dia(dia: Any) -> date:
    if isinstance(dia, date):
        return dia
    return date.fromisoformat(str(dia or "")[:10])


def nome_do_pedido(tipo: str, dia: Any) -> str:
    """`DP0002910.261` — prefixo + `000` + dia + mês + `.AA` + `1`."""
    d = _dia(dia)
    return f"{tipo}000{d:%d%m}.{d:%y}1"


# -------------------------------------------------------- classificar

_RAIZ = re.compile(r"^\s*(?:<\?xml[^>]{0,500}\?>\s*)?<([A-Za-z_][\w.-]{0,60})")
_CODIGO = re.compile(r"<codigo[^>]{0,100}>(.{0,40}?)</codigo>",
                     re.DOTALL | re.IGNORECASE)
_OCORRENCIA = re.compile(
    r"<(?:ocorrencia|mensagem)[^>]{0,100}>(.{0,500}?)</(?:ocorrencia|mensagem)>",
    re.DOTALL | re.IGNORECASE)


def classificar(tipo: str, bruto: str) -> tuple[str, str | None, str]:
    """O que a CRA respondeu, sem ler título nenhum: (resultado, código, frase).

    `resultado` é NADA, AVISO, FALHA, ou `None` quando veio conteúdo a ler.
    Só olha a RAIZ: um relatório ou um erro da Central é a resposta inteira, e
    não uma palavra solta no meio de um arquivo.
    """
    texto = str(bruto or "").lstrip("\ufeff").strip()
    if not texto:
        return (AVISO, None,
                "a CRA respondeu vazio — o que isso quer dizer nesta "
                "operação não está medido; a consulta ficou registrada")
    achado = _RAIZ.match(texto)
    raiz = (achado.group(1).lower() if achado else "")
    if raiz not in ("relatorio", "erro"):
        return None, None, ""
    codigo_achado = _CODIGO.search(texto)
    codigo = codigo_achado.group(1).strip() if codigo_achado else None
    frase_achada = _OCORRENCIA.search(texto)
    frase = (frase_achada.group(1).strip() if frase_achada else "") or \
        "sem a frase da Central"
    com_codigo = f"{frase} (código {codigo})" if codigo else frase
    if raiz == "erro":
        return FALHA, codigo, f"a CRA recusou: {com_codigo}"
    if codigo and codigo in NADA_VEIO.get(tipo, frozenset()):
        return NADA, codigo, f"nada veio — {com_codigo}"
    if codigo and codigo in PEDIDO_RECUSADO:
        return FALHA, codigo, f"a CRA recusou o pedido: {com_codigo}"
    return (AVISO, codigo,
            f"a CRA respondeu com um relatório: {com_codigo} — este código "
            f"não está medido para esta operação; confira na CRA")


def _falha_incerta(erro: BaseException) -> bool:
    """A falha em que NÃO se sabe se a CRA marcou o arquivo como baixado.

    É CERTA só a que não chegou a pedir nada: sem credencial, endereço que não
    é https, nome recusado aqui — e a credencial que a CRA recusou (401), que
    não passa da porta. É INCERTA a de transporte (`cra21_api._bater` a
    encadeia a `CentralHttpError`), a resposta fora do combinado
    (`CraRecusou`: falha SOAP, resposta sem `<return>` — a Central pode ter
    feito o trabalho e devolvido outra coisa) e qualquer outra que este
    módulo não conheça. Na dúvida, pendência: quem confere no portal encerra.
    """
    if isinstance(erro, CRED.CredencialError):
        return False
    if isinstance(erro, CRA.CraRecusou):
        return True
    if isinstance(erro, CRA.CraError):
        return isinstance(erro.__cause__, HTTP.CentralHttpError)
    return True


# ----------------------------------------------------------- guardar


def _hash(bruto: str) -> str:
    return hashlib.sha256(bruto.encode("utf-8", errors="surrogatepass")
                          ).hexdigest()


def _gravar_em_disco(pasta: Any, consulta: dict, nome: str, bruto: str,
                     agora: str) -> Path:
    """A reserva do bruto quando o banco recusou. O nome é todo nosso."""
    marca = re.sub(r"[^0-9]", "", str(agora))[:14] or "0"
    seguro = re.sub(r"[^A-Za-z0-9._-]", "_", nome)[:40]
    destino = Path(pasta) / "cra_pedidos"
    destino.mkdir(parents=True, exist_ok=True)
    arquivo = destino / f"{marca}_{consulta['tipo']}_{seguro}.txt"
    arquivo.write_text(bruto, encoding="utf-8", errors="surrogatepass")
    return arquivo


def _guardar_bruto(transacao: Callable[[], AbstractContextManager], consulta: dict,
                   nome: str, bruto: str, *, agora: str, usuario: str | None,
                   pasta_reserva: Any) -> tuple[int | None, str | None, str]:
    """Grava a resposta INTEIRA antes de qualquer leitura. Nunca estoura.

    Devolve (consulta_id, onde ficou, erro). `onde` é «banco», o caminho do
    arquivo de reserva, ou None quando nem o banco nem o disco aceitaram.
    """
    try:
        with transacao() as con:
            novo = banco(con).escrever(
                """INSERT INTO pt_cra_consultas(tipo, operacao, nome_pedido,
                       pedida_em, pedida_por, resultado, bruto, hash_bruto,
                       tamanho)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
                (consulta["tipo"], consulta["operacao"], nome, agora, usuario,
                 GUARDADO, bruto, _hash(bruto), len(bruto)))
        return int(novo[0]["id"]), "banco", ""
    except Exception as erro:  # noqa: BLE001 — o bruto não pode sumir
        falha = f"{type(erro).__name__}: {erro}"
    if pasta_reserva:
        try:
            caminho = _gravar_em_disco(pasta_reserva, consulta, nome, bruto,
                                       agora)
            return None, str(caminho), falha
        except OSError as erro:
            falha += f"; e o disco também recusou: {erro}"
    return None, None, falha


def _anotar(con, consulta_id: int | None, **campos: Any) -> None:
    """O resultado da consulta, na linha dela."""
    if consulta_id is None or not campos:
        return
    nomes = sorted(campos)
    banco(con).escrever(
        f"UPDATE pt_cra_consultas SET {', '.join(f'{n} = %s' for n in nomes)} "
        f"WHERE id = %s",
        (*[campos[n] for n in nomes], int(consulta_id)))


def _registrar_falha(transacao, consulta: dict, nome: str, *, agora: str,
                     usuario: str | None, mensagem: str,
                     incerta: bool) -> int | None:
    """A consulta que não trouxe nada, registrada. Nunca estoura."""
    try:
        with transacao() as con:
            novo = banco(con).escrever(
                """INSERT INTO pt_cra_consultas(tipo, operacao, nome_pedido,
                       pedida_em, pedida_por, resultado, mensagem, incerta,
                       tamanho)
                   VALUES (%s,%s,%s,%s,%s,%s,%s,%s,0) RETURNING id""",
                (consulta["tipo"], consulta["operacao"], nome, agora, usuario,
                 FALHA, mensagem[:2000], 1 if incerta else 0))
        return int(novo[0]["id"])
    except Exception:  # noqa: BLE001 — a frase já vai à tela
        return None


# ----------------------------------------------------------- receber


def _chave(tipo: str, protocolo: Any, numero: Any, titulo_id: Any) -> str:
    return (f"{tipo}|{str(protocolo or '').strip()}|"
            f"{DS.numero_comparavel(numero)}|{titulo_id or '-'}")


def _gravar_pedido(con, *, consulta_id: int, tipo: str, pedido: dict,
                   titulo: dict | None, estado: str, explicacao: str,
                   agora: str, destaque: str | None = None,
                   ato_id: int | None = None) -> int | None:
    """Uma linha por título (ou por pedido sem título). O MESMO pedido que
    volta noutro arquivo não entra de novo — a chave é tipo, protocolo, número
    e título."""
    linha = banco(con).escrever(
        """INSERT INTO pt_cra_pedidos(consulta_id, tipo, chave, protocolo,
               data_protocolo, numero_titulo, devedor_nome, valor_centavos,
               titulo_id, situacao_ao_chegar, destaque, estado, explicacao,
               ato_id, tem_anexo, recebido_em)
           VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
           ON CONFLICT (chave) DO NOTHING RETURNING id""",
        (int(consulta_id), tipo,
         _chave(tipo, pedido.get("protocolo"), pedido.get("numero_do_titulo"),
                (titulo or {}).get("id")),
         pedido.get("protocolo") or None, pedido.get("data"),
         pedido.get("numero_do_titulo") or None,
         pedido.get("devedor_nome") or None, pedido.get("valor_centavos"),
         (titulo or {}).get("id"), (titulo or {}).get("situacao"), destaque,
         estado, explicacao[:2000], ato_id,
         1 if pedido.get("tem_anexo") else 0, agora))
    return int(linha[0]["id"]) if linha else None


def _br(iso: Any) -> str:
    s = str(iso or "")[:10]
    return f"{s[8:10]}/{s[5:7]}/{s[:4]}" if len(s) == 10 else "data não lida"


def _protesto_lavrado_em(con, titulo_id: int) -> str | None:
    linha = banco(con).um(
        """SELECT data_ato FROM pt_atos
            WHERE titulo_id = %s AND tipo = 'PROTESTO' AND cancelado = 0
            ORDER BY id DESC LIMIT 1""", (int(titulo_id),))
    return (linha or {}).get("data_ato")


def receber_desistencias(con, bruto: str, *, consulta_id: int,
                         nome_arquivo: str, agora: str,
                         usuario: str | None) -> dict:
    """O arquivo DP que veio no clique. ESCREVE.

    APLICA PELO CAMINHO QUE JÁ EXISTE — `protesto_desistencia.aplicar` —, e só
    nos protocolos em que a conferência diz que cabe: casou pelo protocolo e
    pelo número, e o título está recebido, apontado ou intimado. `aplicar`
    lavra o ato na hora, nos irmãos inclusive, e devolve o sustado como
    recusado. O arquivo se guarda em `pt_desistencias` mesmo quando nada cabe.
    """
    visto = DS.conferir(con, bruto)
    nome = visto.get("nome_arquivo") or nome_arquivo
    cabem = [l["protocolo"] for l in visto["titulos"] if l["cabe"]]
    aplicados: dict[int, dict] = {}
    recusados: dict[int, str] = {}
    if cabem:
        r = DS.aplicar(con, bruto, protocolos=cabem, agora=agora,
                       nome_arquivo=nome, usuario=usuario)
        desistencia_id = int(r["desistencia_id"])
        aplicados = {int(a["titulo"]["id"]): a for a in r["aplicados"]}
        recusados = {int(x["titulo_id"]): x["porque"] for x in r["recusados"]
                     if x.get("titulo_id")}
    else:
        desistencia_id = DS.guardar_arquivo(con, visto, nome_arquivo=nome,
                                            agora=agora, usuario=usuario)
    dia = visto.get("dia")
    resumo = {"titulos": len(visto["titulos"]), "aplicados": 0,
              "pendentes": 0, "graves": 0, "por_pouco": 0,
              "desistencia_id": desistencia_id,
              "apresentante": visto.get("apresentante_codigo"),
              "recusados": len(recusados)}
    for linha in visto["titulos"]:
        if not linha["titulos"]:
            _gravar_pedido(con, consulta_id=consulta_id, tipo="DP",
                           pedido=linha, titulo=None, estado=PENDENTE,
                           explicacao=linha["porque"], agora=agora)
            resumo["pendentes"] += 1
            continue
        for x in linha["titulos"]:
            tid = int(x["id"])
            if tid in aplicados:
                por_pouco = x["situacao"] == "INTIMADO"
                _gravar_pedido(
                    con, consulta_id=consulta_id, tipo="DP", pedido=linha,
                    titulo=x, estado=APLICADO,
                    destaque=POR_POUCO if por_pouco else None,
                    ato_id=int(aplicados[tid]["ato_id"]), agora=agora,
                    explicacao=(
                        "Desistência aplicada no clique do dia"
                        + (" — o título estava INTIMADO: confira que nenhum "
                           "protesto dele ficou preparado." if por_pouco
                           else ".")))
                resumo["aplicados"] += 1
                resumo["por_pouco"] += int(por_pouco)
            elif x["situacao"] == "DESISTIDO":
                _gravar_pedido(con, consulta_id=consulta_id, tipo="DP",
                               pedido=linha, titulo=x, estado=RESOLVIDO,
                               agora=agora,
                               explicacao="O título já estava DESISTIDO.")
            elif x["situacao"] == "PROTESTADO":
                lavrado = _protesto_lavrado_em(con, tid)
                _gravar_pedido(
                    con, consulta_id=consulta_id, tipo="DP", pedido=linha,
                    titulo=x, estado=PENDENTE, destaque=GRAVE, agora=agora,
                    explicacao=(
                        f"GRAVE: o credor desistiu (arquivo de {_br(dia)}) e o "
                        f"título está PROTESTADO (protesto de "
                        f"{_br(lavrado)}). Se o protesto foi lavrado depois da "
                        f"desistência, ele não devia existir — o caminho é o "
                        f"cancelamento. Decide o oficial."))
                resumo["pendentes"] += 1
                resumo["graves"] += 1
            else:
                _gravar_pedido(
                    con, consulta_id=consulta_id, tipo="DP", pedido=linha,
                    titulo=x, estado=PENDENTE, agora=agora,
                    explicacao=(recusados.get(tid) or x.get("porque")
                                or f"O título está {x['situacao']}."))
                resumo["pendentes"] += 1
    return resumo


def _tipo_da_autorizacao(arquivo: dict, titulo: dict) -> str:
    """AC ou AD. A letra `t07` diz (C cancelamento, S desistência — manual da
    P21); sem ela, a raiz ou o nome do arquivo; sem nada, AC, que é o que se
    pediu."""
    letra = str(titulo.get("reservado_90") or "").strip().upper()
    if letra == "S":
        return "AD"
    if letra == "C":
        return "AC"
    raiz = str(arquivo.get("raiz") or "")
    nome = str(arquivo.get("nome_arquivo") or "").upper()
    if raiz == "autoriza_desistencia" or nome.startswith("AD"):
        return "AD"
    return "AC"


def _explicacao_do_pedido(tipo: str, situacao: str) -> str:
    if tipo == "CP":
        base = ("A CRA mandou o pedido de cancelamento. Lavre o cancelamento "
                "quando o devedor pagar as custas, ou registre por que não.")
    elif tipo == "AD":
        base = ("O credor autorizou a desistência. Ela se lavra quando o "
                "devedor pagar as custas, ou registre por que não.")
    else:
        base = ("O credor autorizou o cancelamento (a carta de anuência vem no "
                "arquivo). Lavre o cancelamento quando o devedor pagar as "
                "custas, ou registre por que não.")
    alvo = "PROTESTADO" if tipo in ("CP", "AC") else None
    if alvo and situacao != alvo:
        base += (f" Atenção: o título está {situacao}, e cancelamento é de "
                 f"protesto lavrado.")
    return base


def receber_pedidos(con, tipo: str, bruto: str, *, consulta_id: int,
                    agora: str) -> dict:
    """O arquivo CP ou AC que veio no clique. ESCREVE só pendências.

    NADA SE LAVRA AQUI: cancelamento e desistência autorizada exigem o
    pagamento das custas pelo devedor. Cada título vira uma pendência.
    """
    arquivo = DS.ler(bruto)
    resumo = {"titulos": len(arquivo["titulos"]), "pendentes": 0,
              "resolvidos": 0, "por_tipo": {}}
    for t in arquivo["titulos"]:
        sub = _tipo_da_autorizacao(arquivo, t) if tipo == "AC" else tipo
        resumo["por_tipo"][sub] = resumo["por_tipo"].get(sub, 0) + 1
        casados, como, todos = DS.casar(con, t)
        if not casados:
            _gravar_pedido(con, consulta_id=consulta_id, tipo=sub, pedido=t,
                           titulo=None, estado=PENDENTE, agora=agora,
                           explicacao=DS.porque_nao_casou(t, como, todos))
            resumo["pendentes"] += 1
            continue
        for x in casados:
            if x["situacao"] == SITUACAO_QUE_FECHA[sub]:
                _gravar_pedido(con, consulta_id=consulta_id, tipo=sub,
                               pedido=t, titulo=x, estado=RESOLVIDO,
                               agora=agora,
                               explicacao=f"O título já estava {x['situacao']}.")
                resumo["resolvidos"] += 1
            else:
                _gravar_pedido(con, consulta_id=consulta_id, tipo=sub,
                               pedido=t, titulo=x, estado=PENDENTE,
                               agora=agora,
                               explicacao=_explicacao_do_pedido(
                                   sub, x["situacao"]))
                resumo["pendentes"] += 1
    return resumo


# ----------------------------------------------------- o clique do dia


def _frase(c: dict, linha: dict) -> tuple[str, str]:
    """A frase e a cor do aviso de cada consulta, para a tela.

    A MENSAGEM SE CORTA: o aviso mora no cookie da sessão, e a frase da CRA
    (uma falha SOAP, por exemplo) pode ter quilobytes. A inteira fica na linha
    da consulta.
    """
    r = linha["resultado"]
    rotulo = c["rotulo"]
    mensagem = str(linha.get("mensagem") or "")[:300]
    if r == FALHA:
        extra = (" Não se sabe se a CRA marcou o arquivo como baixado: confira "
                 "no portal antes de repetir." if linha.get("incerta") else "")
        return f"{rotulo} — falhou: {mensagem}{extra}", "danger"
    if r in (NAO_LIDO, GUARDADO):
        return (f"{rotulo}: o arquivo veio e ficou guardado, mas não foi lido "
                f"({mensagem}). Abra «Pedidos da CRA».", "danger")
    if r == NADA:
        return f"{rotulo}: {mensagem}.", "info"
    if r == AVISO:
        return f"{rotulo}: {mensagem}.", "warning"
    if c["tipo"] == "DP":
        partes = [f"{linha['titulos']} título(s)",
                  f"{linha['aplicados']} aplicada(s)"]
        if linha["pendentes"]:
            partes.append(f"{linha['pendentes']} pendente(s)")
        frase = f"{rotulo}: " + ", ".join(partes) + "."
        if linha["graves"]:
            return (frase + f" {linha['graves']} de título JÁ PROTESTADO — "
                    f"veja «Pedidos da CRA».", "danger")
        if linha["pendentes"]:
            return frase + " Veja «Pedidos da CRA».", "warning"
        return frase, "success"
    frase = (f"{rotulo}: {linha['titulos']} título(s); {linha['pendentes']} "
             f"pendente(s) até o ato ser lavrado")
    return frase + ". Veja «Pedidos da CRA».", ("warning" if linha["pendentes"]
                                               else "success")


def _uma(transacao, trazer, c: dict, *, dia: Any, agora: str,
         usuario: str | None, pasta_reserva: Any) -> dict:
    nome = nome_do_pedido(c["tipo"], dia)
    linha: dict = {"tipo": c["tipo"], "operacao": c["operacao"],
                   "o_que": c["o_que"], "rotulo": c["rotulo"], "nome": nome,
                   "resultado": None, "mensagem": "", "consulta_id": None,
                   "codigo": None, "incerta": False, "tamanho": 0,
                   "titulos": 0, "aplicados": 0, "pendentes": 0, "graves": 0,
                   "desistencia_id": None, "apresentante": None,
                   "recusados": 0, "onde": None, "bruto_sem_lugar": None}
    # 1) A REDE, UMA VEZ SÓ.
    try:
        bruto = trazer(c["o_que"], nome, c["com_imagem"])
    except Exception as erro:  # noqa: BLE001 — a falha de um não derruba os outros
        linha["resultado"] = FALHA
        linha["mensagem"] = str(erro) or type(erro).__name__
        linha["incerta"] = _falha_incerta(erro)
        linha["consulta_id"] = _registrar_falha(
            transacao, c, nome, agora=agora, usuario=usuario,
            mensagem=linha["mensagem"], incerta=linha["incerta"])
        linha["frase"], linha["cor"] = _frase(c, linha)
        return linha
    bruto = "" if bruto is None else str(bruto)
    linha["tamanho"] = len(bruto)

    # 2) GUARDAR ANTES DE LER.
    cid, onde, falha = _guardar_bruto(transacao, c, nome, bruto, agora=agora,
                                      usuario=usuario,
                                      pasta_reserva=pasta_reserva)
    linha["consulta_id"], linha["onde"] = cid, onde
    if cid is None:
        linha["resultado"] = NAO_LIDO
        if onde:
            linha["mensagem"] = (f"o banco não aceitou ({falha}); a resposta "
                                 f"ficou em {onde}")
        else:
            linha["mensagem"] = (f"nem o banco nem o disco aceitaram ({falha}); "
                                 f"a resposta está nesta tela — copie-a")
            linha["bruto_sem_lugar"] = bruto
        linha["frase"], linha["cor"] = _frase(c, linha)
        return linha

    # 3) LER.
    resultado, codigo, frase = classificar(c["tipo"], bruto)
    linha["codigo"] = codigo
    try:
        with transacao() as con:
            if resultado is not None:
                _anotar(con, cid, resultado=resultado, codigo=codigo,
                        mensagem=frase, lida_em=agora)
                linha["resultado"], linha["mensagem"] = resultado, frase
            elif c["tipo"] == "DP":
                r = receber_desistencias(con, bruto, consulta_id=cid,
                                         nome_arquivo=nome, agora=agora,
                                         usuario=usuario)
                linha.update({k: r[k] for k in (
                    "titulos", "aplicados", "pendentes", "graves",
                    "desistencia_id", "apresentante", "recusados")})
                _anotar(con, cid, resultado=RECEBIDO, titulos=r["titulos"],
                        desistencia_id=r["desistencia_id"], lida_em=agora,
                        mensagem=f"{r['titulos']} título(s), {r['aplicados']} "
                                 f"aplicada(s), {r['pendentes']} pendente(s)")
                linha["resultado"] = RECEBIDO
            else:
                r = receber_pedidos(con, c["tipo"], bruto, consulta_id=cid,
                                    agora=agora)
                linha["titulos"], linha["pendentes"] = (r["titulos"],
                                                        r["pendentes"])
                _anotar(con, cid, resultado=RECEBIDO, titulos=r["titulos"],
                        lida_em=agora,
                        mensagem=f"{r['titulos']} título(s), "
                                 f"{r['pendentes']} pendente(s)")
                linha["resultado"] = RECEBIDO
    except Exception as erro:  # noqa: BLE001 — o bruto já está guardado
        linha["resultado"] = NAO_LIDO
        linha["mensagem"] = f"{type(erro).__name__}: {erro}"[:500]
        try:
            with transacao() as con:
                _anotar(con, cid, resultado=NAO_LIDO,
                        mensagem=linha["mensagem"], lida_em=agora)
        except Exception:  # noqa: BLE001 — fica GUARDADO, que também cobra
            pass
    linha["frase"], linha["cor"] = _frase(c, linha)
    return linha


def trazer_do_dia(transacao: Callable[[], AbstractContextManager],
                  trazer: Callable[[str, str, bool], str], *, dia: Any,
                  agora: str, usuario: str | None = None,
                  pasta_reserva: Any = None) -> list[dict]:
    """DP, CP e AC, nesta ordem, uma chamada cada. NUNCA estoura.

    `transacao` abre uma transação curta (a rede fica FORA dela, como no
    envio pós-remessa); `trazer(o_que, nome, com_imagem)` é a porta da CRA —
    na tela, `cra21_web._trazer` em produção. Devolve uma linha por consulta,
    com `frase` e `cor` para o aviso da tela e o que a auditoria precisa.
    """
    return [_uma(transacao, trazer, c, dia=dia, agora=agora, usuario=usuario,
                 pasta_reserva=pasta_reserva) for c in CONSULTAS]


# ------------------------------------------------------------- ler


_SEM_BRUTO = ("id, tipo, operacao, nome_pedido, pedida_em, pedida_por, "
              "resultado, hash_bruto, tamanho, codigo, mensagem, incerta, "
              "titulos, desistencia_id, lida_em, tratada_em, tratada_por, "
              "motivo")


def consulta(con, consulta_id: int) -> dict | None:
    """A consulta guardada, COM o bruto. Só LÊ."""
    return banco(con).um("SELECT * FROM pt_cra_consultas WHERE id = %s",
                         (int(consulta_id),))


def nome_para_baixar(linha: dict) -> str:
    """O nome do arquivo que a tela entrega — só letras, números e `._-`."""
    base = re.sub(r"[^A-Za-z0-9._-]", "_",
                  str(linha.get("nome_pedido") or "cra"))[:40]
    return f"cra-{int(linha['id'])}-{base}.txt"


def consultas_do_dia(con, dia: Any) -> list[dict]:
    d = _dia(dia).isoformat()
    return banco(con).ler(
        f"""SELECT {_SEM_BRUTO} FROM pt_cra_consultas
             WHERE pedida_em >= %s AND pedida_em < %s ORDER BY id""",
        (d, d + "~"))


def contagem_desde_a_virada(con) -> dict:
    """Quantas vezes a CRA foi consultada para DP, CP e AC desde 14/10/2026.

    A FONTE É O REGISTRO DAS CENTRAIS (`centrais_log`), e não esta tela: toda
    chamada SOAP se anota lá, venha do clique do dia ou da tela técnica da
    API. Foi por ele que se mediu o zero de 29/10/2026. Sem a tabela, a
    contagem é `None` — e a tela diz «sem medida», e não zero.
    """
    bd = banco(con)
    saida: dict = {"desde": VIRADA, "desde_br": _br(VIRADA),
                   "DP": None, "CP": None, "AC": None, "pelo_clique": {}}
    if bd.tem_tabela("centrais_log"):
        contas = {r["operacao"]: int(r["n"]) for r in bd.ler(
            """SELECT operacao, COUNT(*) AS n FROM centrais_log
                WHERE central = %s AND operacao IN (%s, %s, %s)
                  AND quando >= %s
                GROUP BY operacao""",
            (CRA.CENTRAL_NO_LOG, "Desistencia", "Cancelamento", "Autorizacao",
             VIRADA))}
        for tipo, operacao in OPERACAO_DO_TIPO.items():
            saida[tipo] = contas.get(operacao, 0)
    saida["pelo_clique"] = {r["tipo"]: int(r["n"]) for r in bd.ler(
        """SELECT tipo, COUNT(*) AS n FROM pt_cra_consultas
            WHERE pedida_em >= %s GROUP BY tipo""", (VIRADA,))}
    return saida


def _pedidos_abertos(con, titulo_id: int | None = None) -> list[dict]:
    """Os pedidos PENDENTES, com a situação de AGORA do título."""
    filtro, args = "", []
    if titulo_id is not None:
        filtro, args = "AND p.titulo_id = %s", [int(titulo_id)]
    linhas = banco(con).ler(
        f"""SELECT p.*, t.situacao AS situacao_agora,
                   t.numero_titulo AS numero_na_casa,
                   c.nome_pedido AS arquivo, c.pedida_em
              FROM pt_cra_pedidos p
              JOIN pt_cra_consultas c ON c.id = p.consulta_id
              LEFT JOIN pt_titulos t ON t.id = p.titulo_id
             WHERE p.estado = %s {filtro}
             ORDER BY CASE WHEN p.destaque = %s THEN 0 ELSE 1 END, p.id""",
        (PENDENTE, *args, GRAVE))
    saida = []
    for p in linhas:
        p = dict(p)
        # FECHA PELO ATO: o título chegou à situação que o pedido pede.
        if p.get("titulo_id") and p.get("situacao_agora") == \
                SITUACAO_QUE_FECHA.get(p["tipo"]):
            continue
        saida.append(p)
    return saida


def _consultas_abertas(con) -> list[dict]:
    """As consultas que pedem ação: arquivo que veio e não se leu, e falha em
    que não se sabe se a CRA marcou como baixado."""
    return banco(con).ler(
        f"""SELECT {_SEM_BRUTO} FROM pt_cra_consultas
             WHERE tratada_em IS NULL
               AND (resultado IN (%s, %s) OR (resultado = %s AND incerta = 1))
             ORDER BY id""", (GUARDADO, NAO_LIDO, FALHA))


def pendencias(con) -> list[dict]:
    """O que veio da CRA e ainda não foi tratado — a forma do roteiro. Só LÊ.

    Uma linha por título pendente (a desistência de título já protestado
    primeiro) e uma por consulta que pede ação. Ver
    `protesto_desistencia.pendencias_da_cra`, que é o nome que o roteiro chama.
    """
    saida: list[dict] = []
    for p in _pedidos_abertos(con):
        numero = p.get("numero_na_casa") or p.get("numero_titulo")
        saida.append({
            "titulo_id": p.get("titulo_id"), "numero_titulo": numero,
            "protocolo": p.get("protocolo"),
            "explicacao": (f"{NOME_DO_TIPO.get(p['tipo'], p['tipo'])} da CRA "
                           f"({p.get('arquivo') or 'arquivo'}): "
                           f"{p.get('explicacao') or ''}").strip(),
            "origem": f"CRA_{p['tipo']}", "tipo": p["tipo"],
            "destaque": p.get("destaque"), "pedido_id": int(p["id"]),
            "consulta_id": int(p["consulta_id"]),
            "situacao_agora": p.get("situacao_agora"),
            "recebido_em": p.get("recebido_em")})
    for c in _consultas_abertas(con):
        quando = str(c.get("pedida_em") or "")
        if c["resultado"] == FALHA:
            texto = (f"a consulta de {c['tipo']} de {_br(quando)} "
                     f"{quando[11:16]} falhou sem saber se a CRA marcou o "
                     f"arquivo como baixado — confira no portal da CRA "
                     f"({c.get('mensagem') or 'sem detalhe'})")
        else:
            texto = (f"o arquivo de {c['tipo']} trazido em {_br(quando)} "
                     f"{quando[11:16]} ficou guardado e não foi lido — "
                     f"{c.get('mensagem') or 'sem detalhe'}")
        saida.append({"titulo_id": None, "numero_titulo": None,
                      "protocolo": None, "explicacao": texto,
                      "origem": f"CRA_{c['tipo']}", "tipo": c["tipo"],
                      "destaque": None, "pedido_id": None,
                      "consulta_id": int(c["id"]), "situacao_agora": None,
                      "recebido_em": quando})
    return saida


def do_titulo(con, titulo_id: int) -> dict:
    """Para a ficha: os pedidos abertos e o histórico deste título. Só LÊ."""
    historico = banco(con).ler(
        """SELECT p.id, p.tipo, p.estado, p.destaque, p.explicacao,
                  p.recebido_em, p.tratado_em, p.tratado_por, p.motivo,
                  p.consulta_id, c.nome_pedido AS arquivo
             FROM pt_cra_pedidos p
             JOIN pt_cra_consultas c ON c.id = p.consulta_id
            WHERE p.titulo_id = %s ORDER BY p.id DESC""", (int(titulo_id),))
    return {"abertos": _pedidos_abertos(con, titulo_id),
            "historico": historico}


def recentes(con, limite: int = 60) -> list[dict]:
    """Os pedidos que chegaram, do mais novo para o mais velho. Só LÊ."""
    return banco(con).ler(
        """SELECT p.id, p.tipo, p.estado, p.destaque, p.protocolo,
                  p.numero_titulo, p.devedor_nome, p.titulo_id,
                  p.situacao_ao_chegar, p.explicacao, p.recebido_em,
                  p.tratado_em, p.tratado_por, p.motivo, p.consulta_id,
                  t.situacao AS situacao_agora
             FROM pt_cra_pedidos p
             LEFT JOIN pt_titulos t ON t.id = p.titulo_id
            ORDER BY p.id DESC LIMIT %s""", (max(1, min(int(limite), 500)),))


def quadro_do_dia(con, *, dia: Any) -> dict:
    """O quadro da tela da remessa e da lista: a contagem desde a virada, as
    consultas de hoje e quantas pendências. Só LÊ."""
    abertas = pendencias(con)
    return {"dia": _dia(dia).isoformat(),
            "contagem": contagem_desde_a_virada(con),
            "consultas": consultas_do_dia(con, dia),
            "pendentes": len(abertas),
            "graves": sum(1 for p in abertas if p.get("destaque") == GRAVE)}


# ------------------------------------------------------------ tratar


def _letras(texto: Any) -> int:
    return sum(1 for ch in str(texto or "") if ch.isalpha())


def _conferir_motivo(motivo: Any) -> str:
    texto = str(motivo or "").strip()
    if _letras(texto) < MINIMO_DE_LETRAS:
        raise PedidoCraError(
            f"Escreva o motivo — pelo menos {MINIMO_DE_LETRAS} letras. Ele "
            f"fica com o pedido e na auditoria, com o seu nome.")
    return texto[:2000]


def tratar_pedido(con, pedido_id: int, *, motivo: Any, agora: str,
                  usuario: str | None, papel: str) -> dict:
    """Registra por que o pedido da CRA não vira ato. ESCREVE.

    A desistência de título já protestado só o oficial ou o substituto
    encerram: manter o protesto de que o credor desistiu é decisão de quem
    responde pela serventia.
    """
    texto = _conferir_motivo(motivo)
    bd = banco(con)
    bd._escrita()      # a linha fica presa até o fim da transação
    p = bd.um("SELECT * FROM pt_cra_pedidos WHERE id = %s FOR UPDATE",
              (int(pedido_id),))
    if not p:
        raise PedidoCraError(f"Pedido {pedido_id} não encontrado.")
    if p["estado"] != PENDENTE:
        raise PedidoCraError(
            f"Este pedido já está {p['estado']} — não há o que registrar.")
    if p.get("destaque") == GRAVE and str(papel or "") not in \
            QUEM_ENCERRA_O_GRAVE:
        raise PedidoCraError(
            "A desistência de título já protestado só o oficial ou o "
            "substituto encerram. Avise-os.")
    bd.escrever(
        """UPDATE pt_cra_pedidos SET estado = %s, tratado_em = %s,
               tratado_por = %s, motivo = %s WHERE id = %s""",
        (TRATADO, agora, usuario, texto, int(pedido_id)))
    return {**dict(p), "estado": TRATADO, "motivo": texto}


def tratar_consulta(con, consulta_id: int, *, motivo: Any, agora: str,
                    usuario: str | None) -> dict:
    """Registra o que se fez com a consulta que pedia ação (arquivo não lido,
    falha incerta) — por exemplo, «conferido no portal da CRA». ESCREVE."""
    texto = _conferir_motivo(motivo)
    bd = banco(con)
    bd._escrita()
    c = bd.um(f"SELECT {_SEM_BRUTO} FROM pt_cra_consultas WHERE id = %s "
              f"FOR UPDATE", (int(consulta_id),))
    if not c:
        raise PedidoCraError(f"Consulta {consulta_id} não encontrada.")
    if c.get("tratada_em"):
        raise PedidoCraError("Esta consulta já foi tratada.")
    bd.escrever(
        """UPDATE pt_cra_consultas SET tratada_em = %s, tratada_por = %s,
               motivo = %s WHERE id = %s""",
        (agora, usuario, texto, int(consulta_id)))
    return {**dict(c), "tratada_em": agora, "motivo": texto}
