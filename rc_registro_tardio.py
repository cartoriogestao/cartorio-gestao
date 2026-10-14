"""O registro de nascimento tardio — art. 249 e art. 46 da Lei 6.015/1973.

O MODELO DO E-OFÍCIO AFIRMA UMA DISPENSA QUE A NORMA CONDICIONA
    O modelo `m04_Registro_Tardio` desta casa traz impresso, em toda folha:

        «Dispensada a presença de testemunhas nos termos do Artigo 3º do
         Provimento 28/2018 – CGJ-MA.»

    **O art. 249, II diz outra coisa.** A regra é que o requerimento «**será
    assinado por duas testemunhas**, sob as penas da lei»; a dispensa existe
    **num caso só**: registrando **menor de 12 anos** *e* com **DNV** (ou
    documento equivalente de estabelecimento de saúde) apresentada. Nesse caso
    dispensa-se a presença das testemunhas **e a entrevista do registrando**.

    Um papel que afirma a dispensa em toda folha faz o balcão deixar de colher
    testemunha no caso em que ela é obrigatória — e é o declarante que assina
    esse papel «sob as penas da lei». **Por isso este módulo calcula a dispensa
    em vez de imprimi-la**, e diz por quê.

    > Não estou dizendo que o Provimento 28/2018 não exista: não o li. Estou
    > dizendo que **o Código de Normas vigente condiciona**, e que afirmar sem
    > condição num papel assinado é o que não se pode fazer. Se o oficial souber
    > de norma posterior que amplie a dispensa, a régua muda aqui, num lugar só.

E O LUGAR DO REGISTRO NÃO É O DO NASCIMENTO
    «serão registradas **no lugar de residência do interessado**» (art. 249,
    caput). É competência, e não preferência — e o balcão que registrasse pelo
    local do parto lavraria em serventia incompetente.
"""
from __future__ import annotations

from typing import Any


class RegistroTardioError(ValueError):
    """Erro de regra, com mensagem pronta para o balcao."""


ARTIGO = "art. 249 do Código de Normas do TJMA"
LEI = "art. 46 da Lei nº 6.015/1973"

ONDE_SE_REGISTRA = (
    "no lugar de **residência do interessado** (art. 249, caput) — e não no do "
    "nascimento. É competência, e não preferência")

# A DNV E OBRIGATORIA NO REGISTRO COMUM (art. 236), **ressalvado o tardio** — e
# e por isso que o tardio existe: quem nunca foi registrado costuma nao ter DNV.
DNV_NO_TARDIO = (
    "o art. 236 torna a DNV obrigatória no registro de nascimento, **ressalvada "
    "a hipótese de registro tardio** — que é justamente o caso de quem não a "
    "tem")

# ---------------------------------------------------------- as testemunhas
#
# **A REGRA E COLHER DUAS; A DISPENSA E O CASO EXCEPCIONAL.** Ver o cabecalho.
TESTEMUNHAS_EXIGIDAS = 2
IDADE_LIMITE_DA_DISPENSA = 12

REGRA_DAS_TESTEMUNHAS = (
    "o requerimento será assinado por **duas testemunhas, sob as penas da lei** "
    "(art. 249, II)")

QUANDO_SE_DISPENSA = (
    "só quando o registrando for **menor de 12 anos** *e* for apresentada a DNV "
    "ou documento equivalente expedido por estabelecimento de saúde — e aí "
    "dispensa-se também a **entrevista do registrando**")


def dispensa_testemunhas(*, idade: Any, tem_dnv: bool) -> dict:
    """Se as testemunhas são dispensadas naquele caso. Só calcula.

    **AS DUAS CONDIÇÕES SÃO CUMULATIVAS**, e o «e» é do artigo: menor de 12
    anos *e* DNV apresentada. Tratá-las como alternativas dispensaria testemunha
    de um adulto que trouxe DNV, ou de uma criança que não trouxe — e nos dois
    casos o art. 249, II manda colher.

    **IDADE DESCONHECIDA NÃO DISPENSA.** Não saber não é o mesmo que saber que é
    menor, e o erro para o lado da dispensa produz requerimento sem as
    testemunhas que a lei exige — que é o defeito que só aparece se alguém
    contestar o registro.
    """
    try:
        anos = int(idade)
    except (TypeError, ValueError):
        anos = None
    menor = anos is not None and anos < IDADE_LIMITE_DA_DISPENSA
    dispensada = bool(menor and tem_dnv)
    if dispensada:
        porque = ("registrando menor de 12 anos e com DNV apresentada — "
                  "art. 249, II. Dispensa-se também a entrevista do "
                  "registrando")
    elif anos is None:
        porque = ("não se sabe a idade do registrando, e não saber não é o "
                  "mesmo que saber que é menor: colha as duas testemunhas")
    elif not menor and not tem_dnv:
        porque = ("registrando com 12 anos ou mais e sem DNV — as duas "
                  "condições faltam")
    elif not menor:
        porque = "registrando com 12 anos ou mais — a dispensa é só para menores"
    else:
        porque = ("registrando menor de 12 anos, mas **sem DNV** — as duas "
                  "condições são cumulativas")
    return {"dispensada": dispensada, "porque": porque,
            "quantas": 0 if dispensada else TESTEMUNHAS_EXIGIDAS,
            "dispensa_entrevista": dispensada}


# ------------------------------------------------ o que instrui o requerimento
#
# § 2o: «**Sempre que possivel**, o requerimento sera acompanhado por» — e o
# «sempre que possivel» e do artigo: sao documentos desejaveis, e nao condicao.
# Trata-los como obrigatorios travaria o registro de quem nao os tem, que e
# exatamente quem precisa do tardio.
DOCUMENTOS_DESEJAVEIS: tuple[dict, ...] = (
    {"chave": "DNV", "inciso": "I",
     "nome": "DNV — ou, na ausência dela, declaração com as informações do "
             "nascimento, com **firma reconhecida**, em caso de extravio"},
    {"chave": "CERTIDAO_NEGATIVA", "inciso": "II",
     "nome": "certidão negativa expedida pelo oficial do **local de nascimento** "
             "do registrando"},
    {"chave": "CERTIDOES_IRMAOS", "inciso": "III",
     "nome": "cópias das certidões de nascimento dos irmãos, se houver"},
)

SAO_DESEJAVEIS_E_NAO_CONDICAO = (
    "o § 2º diz «**sempre que possível**» — tratá-los como obrigatórios travaria "
    "o registro de quem não os tem, que é exatamente quem precisa do tardio")

# ------------------------------------------------------------ o que o oficial faz
O_RITO: tuple[dict, ...] = (
    {"inciso": "I", "o_que": "o requerimento é **autuado e numerado** pelo "
                             "oficial, substituto ou preposto designado"},
    {"inciso": "II", "o_que": "assinado por duas testemunhas, salvo a dispensa "
                              "do caso único"},
    {"inciso": "III", "o_que": "**se suspeitar da falsidade** da declaração, o "
                               "oficial pode exigir prova suficiente"},
    {"inciso": "IV", "o_que": "**persistindo a suspeita**, encaminha os autos "
                              "ao juízo competente"},
)

# O ARQUIVO E DE VINTE ANOS (§ 1o), e so depois disso o JUIZ pode autorizar a
# incineracao — nao e a serventia que decide descartar.
ARQUIVO_ANOS = 20
COMO_SE_DESCARTA = (
    "findo o prazo, **o juiz da vara de registros públicos** é quem autoriza a "
    "incineração — e não a serventia (art. 249, § 1º)")

# E ELE FICA EM ARQUIVO OBRIGATORIO, com os documentos que o instruem — art.
# 211, II, que remete ao Provimento no 149/2023 do CNJ.
ARQUIVO_OBRIGATORIO = (
    "art. 211, II — o requerimento de registro de nascimento tardio fica em "
    "arquivo, físico ou eletrônico, **contendo obrigatoriamente os documentos "
    "que o instruem**, na forma do Provimento nº 149/2023 do CNJ")


def artigos_citados() -> tuple[str, ...]:
    """Todo artigo que este módulo cita. Só lê — para o oficial conferir."""
    return ("art. 46 da Lei nº 6.015/1973", "art. 211, II", "art. 236",
            "art. 249", "art. 249, I", "art. 249, II", "art. 249, III",
            "art. 249, IV", "art. 249, § 1º", "art. 249, § 2º",
            "art. 249, § 4º", "Provimento nº 149/2023 do CNJ")


def o_que_conferir(*, idade: Any, tem_dnv: bool,
                   testemunhas: int = 0) -> list[str]:
    """O que falta no requerimento. Só calcula — a tela mostra antes de imprimir.

    **NÃO RECUSA NADA**: o registro de nascimento é imperativo legal (art. 250),
    e travar o requerimento por documento faltante seria negar registro a quem
    mais precisa dele. Ele diz o que falta; decidir é do oficial.
    """
    faltas: list[str] = []
    regra = dispensa_testemunhas(idade=idade, tem_dnv=tem_dnv)
    if not regra["dispensada"] and int(testemunhas or 0) < TESTEMUNHAS_EXIGIDAS:
        faltas.append(
            f"as {TESTEMUNHAS_EXIGIDAS} testemunhas do art. 249, II — "
            f"{regra['porque']}")
    if not tem_dnv:
        faltas.append(
            "a DNV, ou a declaração com as informações do nascimento e firma "
            "reconhecida, em caso de extravio (§ 2º, I)")
    return faltas


def _texto(v: Any) -> str:
    if v is None:
        return ""
    return str(v).strip()
