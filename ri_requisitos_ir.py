"""O QUE A MATRÍCULA NOVA PRECISA TER PARA SUBIR AO INDICADOR REAL (RI018, 25/11/2026).

O DEFEITO
    A tela «Abrir matrícula» não pedia o tipo do imóvel, deixava o município e a UF em texto
    livre e aceitava qualquer frase no logradouro. Medido na réplica em 25/11/2026: das
    matrículas abertas pelo sistema, **só uma** passa pelos próprios dados no gerador do arquivo do
    Indicador Real (`onr_ir_json`): as outras têm tipo do imóvel vazio ou «RURAL», logradouro que começa
    por «situada na zona rural…» e afins. A Circular COGEX 243/2026 cobra esse envio.

A RÉGUA NÃO É NOVA
    É a do arquivo: `onr_ir_json.montar_registro_por_campo`, a mesma que o PR 501 usa para gerar
    o JSON e que a fila de conferência (`ri_fila_fichas`, PR 499) usa para classificar. Uma régua
    paralela aqui poderia abrir ficha que o arquivo recusa, e era exatamente esse o buraco.

O QUE TRAVA E O QUE SÓ AVISA (a escolha, documentada)
    * TRAVA a abertura de matrícula NOVA (número fora do acervo) pela tela e o selo automático da
      abertura: é o momento em que a ficha nasce, quem abre tem o título na mão, e corrigir
      depois custa uma retificação cadastral por ficha.
    * TRAVA a retificação cadastral de ficha nova que CRIA um impedimento que ela não tinha.
      O que já faltava antes não impede gravar outra correção: as fichas abertas desde setembro
      precisam ser corrigidas por esta mesma tela, e travar tudo de uma vez impediria isso.
    * SÓ AVISA na ficha de ACERVO (número abaixo de 4.015, importação do E-Ofício e do Word): a
      ficha conta o que o papel diz, e recusar a importação esconderia a ficha em vez de corrigi-la.
      O que falta vai para a fila de conferência do PR 499.
    * SÓ AVISA no selo digitado à mão: o selo já existe fora do sistema; recusar o registro dele
      esconderia um selo emitido, que é pior que a ficha incompleta.
    * SÓ AVISA quando a configuração da serventia (CNS, UF, código IBGE) está incompleta: aí o
      defeito é da casa, não da ficha, e travar pararia o balcão inteiro. O aviso diz onde configurar.
    * SÓ AVISA o imóvel rural sem CCIR: o manual não o exige, e tornar o CCIR obrigatório na
      abertura é decisão registral (LRP, art. 176, § 1º, II, 3, a), que fica com o oficial.

SÓ CALCULA. Não grava e não transmite nada.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Mapping

import onr_ir_json as J

#: Os 13 tipos do manual (seção 11), com a grafia que a casa já grava. `codigo_do_imovel` casa
#: cada rótulo com o código, e `tests/test_ri_requisitos_ir.py` confere os 13.
TIPOS_DO_IMOVEL: tuple[str, ...] = (
    "Casa", "Apartamento", "Loja", "Sala/Conjunto", "Terreno/fração", "Galpão", "Prédio comercial",
    "Prédio residencial", "Fazenda/Sítio/Chácara", "Vaga", "Depósito", "Públicos", "Outros",
)

#: Os tipos de via do manual (seção 9), na ordem da tabela, menos os que não nomeiam a via.
TIPOS_DE_VIA: tuple[str, ...] = tuple(
    nome for codigo, nome in J.TIPOS_DE_LOGRADOURO.items() if codigo not in J._TIPOS_QUE_NAO_NOMEIAM)

ROTULO_DO_CAMPO: dict[str, str] = {
    "numero": "Número da matrícula",
    "livro_norm": "Livro",
    "rural_urbano": "Localização (urbano ou rural)",
    "tipo_imovel": "Tipo do imóvel",
    "logradouro": "Logradouro / denominação",
    "uf": "UF",
    "cidade": "Município",
    "cep": "CEP",
    "car": "CAR",
    "ccir": "CCIR",
    "sigef": "SIGEF",
    "nirf": "NIRF / CIB",
}

#: O que a configuração precisa ter, para a mensagem dizer onde se conserta.
ONDE_CONFIGURAR = ("Administrativo → Configurações: «ri_cns», «ri_uf», «ri_cidade», o código IBGE "
                   "do município e, se a circunscrição tiver outro município, «ri_municipios_ibge»")


@dataclass
class Conferencia:
    """O resultado de conferir uma ficha (ou o que a tela vai gravar) contra o manual."""
    pendencias: list[dict] = field(default_factory=list)   # [{campo, rotulo, mensagem}]
    avisos: list[str] = field(default_factory=list)
    sem_configuracao: list[str] = field(default_factory=list)

    @property
    def sobe(self) -> bool:
        return not self.pendencias and not self.sem_configuracao

    def campos(self) -> set[str]:
        return {p["campo"] for p in self.pendencias}

    def resumo(self, limite: int = 6) -> str:
        partes = [f"{p['rotulo']}: {p['mensagem']}" for p in self.pendencias[:limite]]
        if len(self.pendencias) > limite:
            partes.append(f"e mais {len(self.pendencias) - limite}")
        return " · ".join(partes)


def settings_de(con: Any) -> dict:
    """A configuração inteira, como `onr_ir_lotes_web` a lê para o gerador."""
    from bd_nativo import banco
    return {x["key"]: x["value"] for x in banco(con).ler("SELECT key, value FROM settings")}


def municipios_da_casa(settings: Mapping[str, Any]) -> list[str]:
    """Os municípios da circunscrição com código IBGE, com a grafia da configuração. A sede primeiro.

    Vazio quando a configuração não fecha: a tela volta ao campo de texto e avisa.
    """
    casa, faltam = J.serventia_de(settings)
    if casa is None or faltam:
        return []
    nomes = [J._texto(settings.get("ri_cidade") or settings.get("serventia_cidade"))]
    bruto = settings.get("ri_municipios_ibge")
    try:
        outros = json.loads(bruto) if isinstance(bruto, str) and bruto.strip() else (bruto or {})
    except ValueError:
        outros = {}
    if isinstance(outros, Mapping):
        nomes += [J._texto(n) for n in outros if J.chave(n) != J.chave(nomes[0])]
    return [n for n in nomes if n]


def uf_da_casa(settings: Mapping[str, Any]) -> str:
    casa, _ = J.serventia_de(settings)
    return casa.uf if casa else ""


def completar_pela_casa(valores: dict, settings: Mapping[str, Any], *, tipo_via: str = "") -> dict:
    """O que a tela deduz sem inventar. Devolve uma cópia; não grava.

    * A UF SAI DO MUNICÍPIO: se o município é da circunscrição, a UF é a da serventia (o código
      IBGE do município começa pelo da UF). Município de fora não ganha UF nenhuma.
    * O MUNICÍPIO ESCRITO SE TROCA PELA GRAFIA DO CADASTRO («montes altos» → como a casa o grava).
    * O TIPO DE VIA escolhido na lista entra na frente do nome, se o nome ainda não começa por um.
    """
    saida = dict(valores)
    casa, faltam = J.serventia_de(settings)
    if casa is not None and not faltam:
        cadastro = {J.chave(n): n for n in municipios_da_casa(settings)}
        escrita = J.chave(saida.get("cidade"))
        if escrita in cadastro:
            saida["cidade"] = cadastro[escrita]
            saida["uf"] = casa.uf
    tipo_via = J._texto(tipo_via)
    if tipo_via and J.chave(tipo_via) in {J.chave(t) for t in TIPOS_DE_VIA}:
        logradouro = J._texto(saida.get("logradouro"))
        if J.partir_logradouro(logradouro)[0] is None:
            saida["logradouro"] = f"{tipo_via} {logradouro}".strip()
    return saida


def conferir(m: Mapping[str, Any], settings: Mapping[str, Any]) -> Conferencia:
    """A ficha `m` (colunas de `ri_matriculas`) passaria no arquivo do Indicador Real?"""
    res = Conferencia()
    casa, faltam = J.serventia_de(settings)
    if casa is None or faltam:
        res.sem_configuracao = list(faltam)
        return res
    ficha = dict(m)
    ficha.setdefault("livro_norm", "2")
    _registro, por_campo = J.montar_registro_por_campo(ficha, casa)
    vistos: set[tuple[str, str]] = set()
    for campo, mensagem in por_campo:
        if (campo, mensagem) in vistos:
            continue
        vistos.add((campo, mensagem))
        res.pendencias.append({"campo": campo, "rotulo": ROTULO_DO_CAMPO.get(campo, campo),
                               "mensagem": mensagem})
    if J.chave(ficha.get("rural_urbano")) in ("r", "rural") and not J._digitos(ficha.get("ccir")):
        res.avisos.append("Imóvel rural sem CCIR. O manual não o exige, e o arquivo sobe sem ele; "
                          "confira se o título traz o CCIR (LRP, art. 176, § 1º, II, 3, a).")
    return res


def novos_impedimentos(antes: Conferencia, depois: Conferencia) -> list[dict]:
    """Os impedimentos que a mudança cria e que a ficha não tinha. É o que a retificação recusa."""
    ja = antes.campos()
    return [p for p in depois.pendencias if p["campo"] not in ja]


def recado_sem_configuracao(conf: Conferencia) -> str:
    return ("Não deu para conferir os requisitos do Indicador Real: falta na configuração "
            + "; ".join(conf.sem_configuracao) + f". Configure em {ONDE_CONFIGURAR}.")
