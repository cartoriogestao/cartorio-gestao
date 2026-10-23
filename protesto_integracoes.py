# -*- coding: utf-8 -*-
"""O INTERRUPTOR das integrações do Protesto com quem está fora da casa: os
Correios (o AR digital da intimação) e o banco (o boleto do devedor).

    «integração externa SEMPRE desligada por padrão (configuração no Gestor,
    credenciais fora do código e fora de log), com modo homologação e teste
    com o serviço FALSO (sem rede)»            — especificação do LG06

TRÊS MODOS, E O PADRÃO É O PRIMEIRO
    DESLIGADO   — nada sai e nada se grava; a tela diz por quê. É o que vale
                  numa instalação nova e o que vale quando a chave some de
                  `settings` ou traz uma palavra que ninguém conhece.
    HOMOLOGACAO — o ensaio. Fala com o SERVIÇO FALSO desta casa (sem rede),
                  grava com a marca `HOMOLOGACAO` e **NADA VALE NO LIVRO**: o AR
                  que «volta» não lavra intimação, e o boleto «pago» não dá
                  baixa no título. Serve para o balcão aprender o caminho com
                  os títulos de verdade sem que nada aconteça a eles.
    PRODUCAO    — fala com o provedor do contrato, e o que volta lavra.

**PRODUÇÃO SÓ COM O TRANSPORTE ESCRITO.** Em 19/10/2026 a serventia não tem
contrato de AR digital com os Correios nem convênio de cobrança registrada com
banco nenhum, e por isso nenhum dos dois transportes de verdade foi escrito: o
endereço da API, os campos e os códigos de retorno se transcrevem do manual que
vem com o contrato — inventá-los seria o pior tipo de número inventado, porque
quem os usasse acharia que está falando com o provedor. A tela do Gestor recusa
gravar PRODUÇÃO enquanto `pronto` for falso, e quem lê a configuração recusa
outra vez (a chave pode ter sido mexida à mão no banco).

**E O SERVIÇO FALSO NUNCA VALE EM PRODUÇÃO.** É a mesma razão ao contrário: um
AR que o simulador inventou lavraria intimação de quem ninguém intimou.

A CHAVE MORA EM `settings`, A SENHA NÃO. O modo e o provedor são configuração
da casa e viajam no backup sem dano; o par do contrato mora em
`centrais_cred` (`correios.cred`, `boleto.cred`), fora do banco, e nenhuma
função daqui o lê — quem o lê é o transporte, na hora de autenticar.
"""
from __future__ import annotations

from typing import Any

import boleto_api as BAPI
import centrais_cred as CRED
import correios_api as CAPI
from bd_nativo import banco
from caixa_schema import centavos


class IntegracaoError(ValueError):
    """Recusa de configuração, com a frase pronta para a tela."""


class IntegracaoDesligada(IntegracaoError):
    """A integração está desligada — o padrão de fábrica."""


DESLIGADO = "DESLIGADO"
HOMOLOGACAO, PRODUCAO = CRED.HOMOLOGACAO, CRED.PRODUCAO
MODOS: tuple[str, ...] = (DESLIGADO, HOMOLOGACAO, PRODUCAO)
ROTULO_DO_MODO: dict[str, str] = {
    DESLIGADO: "Desligada",
    HOMOLOGACAO: "Homologação (serviço falso, nada vale no livro)",
    PRODUCAO: "Produção",
}

AR, BOLETO = "AR", "BOLETO"

# AS DUAS INTEGRAÇÕES, e o que cada uma guarda em `settings`. A credencial vai
# por `central` — o nome da gaveta em `centrais_cred`.
INTEGRACOES: dict[str, dict[str, Any]] = {
    AR: {
        "nome": "AR digital dos Correios (intimação)",
        "chave_modo": "protesto_ar_modo",
        "chave_provedor": "protesto_ar_provedor",
        "central": CRED.CORREIOS,
        "provedores": CAPI.PROVEDORES,
        "erro_do_transporte": CAPI.CorreiosError,
    },
    BOLETO: {
        "nome": "Boleto do devedor (cobrança registrada, com PIX)",
        "chave_modo": "protesto_boleto_modo",
        "chave_provedor": "protesto_boleto_provedor",
        "central": CRED.BANCO_BOLETO,
        "provedores": BAPI.PROVEDORES,
        "erro_do_transporte": BAPI.BoletoError,
    },
}

# CN-MA art. 925, § 5º: quem paga pelo boleto que acompanha a intimação pode
# ter repassado o custo de emissão e registro. **O padrão é zero** — repassar é
# faculdade do tabelião, e cobrar sem ele decidir seria decidir por ele.
CHAVE_TARIFA_DO_BOLETO = "protesto_boleto_tarifa_centavos"


def _qual(qual: Any) -> str:
    nome = str(qual or "").strip().upper()
    if nome not in INTEGRACOES:
        raise IntegracaoError(
            f"Integração desconhecida: «{qual}». As que existem: "
            + ", ".join(INTEGRACOES) + ".")
    return nome


def _setting(bd, chave: str) -> str:
    linha = bd.um("SELECT value FROM settings WHERE key=%s", (chave,))
    return str((linha or {}).get("value") or "").strip()


def provedor_padrao(qual: Any, modo: str) -> str:
    """O provedor quando ninguém escolheu: o falso no ensaio, o do contrato na
    produção. Só calcula."""
    provedores = INTEGRACOES[_qual(qual)]["provedores"]
    for nome, p in provedores.items():
        if bool(p["falso"]) == (modo != PRODUCAO):
            return nome
    return next(iter(provedores))


def configuracao(con: Any, qual: Any) -> dict:
    """O que está ligado, em que modo e com que provedor. SÓ LÊ.

    **Palavra desconhecida vira DESLIGADO**, e não o modo mais parecido: a
    chave mexida à mão no banco não liga integração nenhuma por engano.
    """
    nome = _qual(qual)
    info = INTEGRACOES[nome]
    bd = banco(con)
    modo = _setting(bd, info["chave_modo"]).upper()
    if modo not in MODOS:
        modo = DESLIGADO
    provedor = _setting(bd, info["chave_provedor"]).upper()
    if provedor not in info["provedores"]:
        provedor = provedor_padrao(nome, modo)
    fora = {"integracao": nome, "nome": info["nome"], "modo": modo,
            "rotulo_do_modo": ROTULO_DO_MODO[modo], "provedor": provedor,
            "provedor_nome": info["provedores"][provedor]["nome"],
            "central": info["central"],
            "ambiente": None if modo == DESLIGADO else modo}
    if nome == BOLETO:
        try:
            fora["tarifa_centavos"] = max(0, int(_setting(
                bd, CHAVE_TARIFA_DO_BOLETO) or 0))
        except ValueError:
            fora["tarifa_centavos"] = 0
    return fora


def conferir_escolha(qual: Any, modo: Any, provedor: Any) -> tuple[str, str]:
    """Recusa a combinação que não pode valer. Só calcula.

    Devolve `(modo, provedor)` normalizados. As três recusas, e cada uma
    protege alguém:

      - provedor que não existe — a tela não oferece, mas o formulário pode
        ser mexido;
      - PRODUÇÃO com o serviço falso — intimação lavrada de AR inventado,
        baixa de título por pagamento que não entrou;
      - provedor cujo transporte não foi escrito, em qualquer modo que fale
        com ele — sem o manual do contrato não há o que mandar.
    """
    nome = _qual(qual)
    info = INTEGRACOES[nome]
    m = str(modo or "").strip().upper() or DESLIGADO
    if m not in MODOS:
        raise IntegracaoError(
            f"Modo desconhecido: «{modo}». Os que existem: "
            + ", ".join(MODOS) + ".")
    p = str(provedor or "").strip().upper() or provedor_padrao(nome, m)
    if p not in info["provedores"]:
        raise IntegracaoError(
            f"Provedor desconhecido para {info['nome']}: «{provedor}». Os que "
            f"existem: " + ", ".join(info["provedores"]) + ".")
    if m == DESLIGADO:
        return m, p
    escolhido = info["provedores"][p]
    if m == PRODUCAO and escolhido["falso"]:
        raise IntegracaoError(
            f"{escolhido['nome']} não vale em produção: ele inventa as "
            f"respostas, e em produção o que volta lavra ato. Escolha o "
            f"provedor do contrato.")
    if not escolhido["pronto"]:
        raise IntegracaoError(
            f"{escolhido['nome']}: {escolhido['falta']}")
    return m, p


def gravar_configuracao(con: Any, qual: Any, *, modo: Any, provedor: Any,
                        tarifa: Any = None) -> dict:
    """Grava o modo e o provedor. ESCREVE em `settings` — e só isso.

    **A credencial não passa por aqui**: ela se informa em Administrativo →
    Configurações, na tabela das Centrais, e vai para fora do banco.
    """
    nome = _qual(qual)
    info = INTEGRACOES[nome]
    m, p = conferir_escolha(nome, modo, provedor)
    valores = {info["chave_modo"]: m, info["chave_provedor"]: p}
    if nome == BOLETO and tarifa is not None and str(tarifa).strip():
        c = centavos(str(tarifa))
        if c < 0:
            raise IntegracaoError("A tarifa do boleto não pode ser negativa.")
        valores[CHAVE_TARIFA_DO_BOLETO] = str(c)
    bd = banco(con)
    for chave in sorted(valores):
        bd.escrever(
            """INSERT INTO settings(key, value) VALUES (%s, %s)
               ON CONFLICT (key) DO UPDATE SET value = excluded.value""",
            (chave, valores[chave]))
    return configuracao(bd, nome)


def transporte_em_uso(con: Any, qual: Any, *, pasta: Any = None) -> tuple[dict, Any]:
    """A configuração e o transporte com que se fala agora. SÓ LÊ.

    Recusa com `IntegracaoDesligada` quando está desligada, e com
    `IntegracaoError` quando a combinação gravada não pode valer — a mesma
    régua da tela do Gestor, porque a chave pode ter sido mexida à mão.
    """
    cfg = configuracao(con, qual)
    info = INTEGRACOES[cfg["integracao"]]
    if cfg["modo"] == DESLIGADO:
        raise IntegracaoDesligada(
            f"{info['nome']}: a integração está DESLIGADA, que é como ela "
            f"nasce. Quem liga é o administrador, no Gestor → Integrações do "
            f"Protesto — primeiro em homologação, com o serviço falso.")
    conferir_escolha(cfg["integracao"], cfg["modo"], cfg["provedor"])
    fabrica = info["provedores"][cfg["provedor"]]["fabrica"]
    return cfg, fabrica(cfg["modo"], pasta)


def e_simulador(transporte: Any) -> bool:
    """O transporte é o serviço falso desta casa? Só calcula."""
    return bool(getattr(transporte, "E_SIMULADOR", False))


def recusar_simulador_em_producao(ambiente: str, transporte: Any) -> None:
    """A segunda guarda, no ponto em que se grava: o serviço falso não vale em
    produção nem quando chega por outro caminho que não a configuração."""
    if ambiente == PRODUCAO and e_simulador(transporte):
        raise IntegracaoError(
            "O serviço falso não vale em produção: o que ele responde é "
            "inventado, e em produção o que volta lavra ato.")


def quadro(con: Any, *, pasta: Any = None) -> list[dict]:
    """O que a tela do Gestor mostra, uma linha por integração. SÓ LÊ.

    **Diz se a credencial foi informada, e nunca qual é** — a regra de
    `centrais_cred.situacao`.
    """
    fora = []
    for nome, info in INTEGRACOES.items():
        cfg = configuracao(con, nome)
        cfg["provedores"] = [
            {"codigo": codigo, "nome": p["nome"], "falso": p["falso"],
             "pronto": p["pronto"], "falta": p.get("falta") or ""}
            for codigo, p in info["provedores"].items()]
        cfg["credencial"] = {
            onde: CRED.tem(info["central"], onde, pasta)
            for onde in (HOMOLOGACAO, PRODUCAO)}
        cfg["nome_da_central"] = CRED.NOME_DA_CENTRAL[info["central"]]
        fora.append(cfg)
    return fora
