"""
Identificacao da serventia e protecao de dado pessoal nos documentos.

POR QUE UM MODULO SO
    O cabecalho aparece no recibo, no orcamento, no protocolo de recepcao e na
    prenotacao do Registro de Imoveis. Escrito em quatro lugares, mudaria em
    tres quando alguem corrigisse um telefone. Aqui e um so.

DE ONDE VEM OS DADOS (sanitizacao B0, 05/10/2026)
    Os dados REAIS da serventia moram SO no banco, na tabela `settings`, nas
    chaves de `CAMPOS`. Este arquivo vai para o repositorio publico e por isso
    `PADRAO` e uma SEMENTE GENERICA, com placeholders: nenhum nome, CNS, CNPJ,
    endereco ou cidade de serventia real.

    Instalacao nova: preencha Configuracoes -> Serventia na primeira execucao.
    Instalacao que ja existia (dados antes escritos aqui no codigo): rode UMA
    vez `tools/migrar_settings_serventia_b0.py`, que faz backup do banco e
    grava em `settings` os valores antigos onde estiver em branco. A ordem e
    essa — migrar ANTES de subir este arquivo —, senao o papel sai com
    «NOME DA SERVENTIA» no cabecalho.

    `dados(get_settings)` nunca completa com dado de serventia real: o que
    faltar em `settings` cai no placeholder generico, visivel no papel, para
    ser corrigido na tela e nao escondido no codigo.
"""
from __future__ import annotations

import re
from types import MappingProxyType
from typing import Any, Mapping

# Semente generica (open source). NAO coloque aqui dado de serventia real —
# a CI anti-vazamento (`ci/anti_vazamento.py`) existe para barrar isso.
PADRAO = {
    "unit_name": "NOME DA SERVENTIA",
    "serventia_titular": "",
    "serventia_titulo": "Tabelião e Oficial de Registro",
    "ri_substituta": "",
    "serventia_cnpj": "",
    "ri_cns": "000000",
    "serventia_telefone": "",
    "serventia_endereco": "",
    "serventia_cep": "",
    "ri_cidade": "",
    "ri_uf": "",
    "serventia_email": "",
    # Caminho (relativo a pasta do sistema) ou URL da imagem do brasao. O
    # arquivo padrao e o Brasao da Republica, simbolo publico, que vai no repo.
    "serventia_brasao": "static/brasao.jpg",
    # IP/host do aparelho selador da rede local. O endereco completo, usuario
    # e senha continuam em `selador_config` (tabela `sd_config` + selador.cred).
    "selador_host": "127.0.0.1",
}

# Copia imutavel da semente: e contra ela que os testes de sanitizacao
# conferem, mesmo que algum teste legado ajuste `PADRAO` em tempo de execucao.
PADRAO_GENERICO: Mapping[str, str] = MappingProxyType(dict(PADRAO))

# Chaves que a tela de configuracoes deve oferecer.
CAMPOS = tuple(PADRAO.keys())

# CHAVES DUPLICADAS QUE JA EXISTEM NOS BANCOS (inventario SERVIDOR 05/10/2026).
#     O CNS e gravado como `ri_cns` pela instalacao, mas alguns leitores
#     procuram `serventia_cns`; o titular e `ri_registrador` na tela de
#     Configuracoes e `serventia_titular` no codigo. A leitura unifica aqui:
#     vale a chave canonica (de `CAMPOS`); em branco, vale a legada.
ALIASES_LEGADOS: Mapping[str, tuple[str, ...]] = MappingProxyType({
    "ri_cns": ("serventia_cns",),
    "serventia_titular": ("ri_registrador",),
})


def _texto(valor: Any) -> str:
    return str(valor or "").strip()


def _ler_settings(get_settings) -> dict:
    if callable(get_settings):
        return dict(get_settings() or {})
    return dict(get_settings or {})


def dados(get_settings) -> dict:
    """Monta o bloco de identificacao a partir das configuracoes.

    `get_settings` e o metodo do banco (ou um dict ja lido). O que estiver em
    branco tenta a chave legada (`ALIASES_LEGADOS`) e, por fim, a semente
    GENERICA de `PADRAO` — nunca um dado real escrito no codigo.
    """
    s = _ler_settings(get_settings)
    d: dict[str, str] = {}
    for chave, padrao in PADRAO.items():
        valor = _texto(s.get(chave))
        if not valor:
            for legada in ALIASES_LEGADOS.get(chave, ()):
                valor = _texto(s.get(legada))
                if valor:
                    break
        d[chave] = valor or padrao
    d["cidade_uf"] = cidade_uf(d)
    d["endereco_completo"] = endereco_completo(d)
    return d


def cidade_uf(d: Mapping[str, Any]) -> str:
    """`Cidade/UF`; com um dos dois em branco, so o que houver."""
    return "/".join(p for p in (_texto(d.get("ri_cidade")),
                                _texto(d.get("ri_uf"))) if p)


def endereco_completo(d: Mapping[str, Any]) -> str:
    """`Endereco, CEP 00.000-000, Cidade-UF` — mesma forma de antes quando
    tudo esta preenchido; sem virgulas soltas quando falta algum pedaco."""
    partes = []
    if _texto(d.get("serventia_endereco")):
        partes.append(_texto(d.get("serventia_endereco")))
    if _texto(d.get("serventia_cep")):
        partes.append(f"CEP {_texto(d.get('serventia_cep'))}")
    local = "-".join(p for p in (_texto(d.get("ri_cidade")),
                                 _texto(d.get("ri_uf"))) if p)
    if local:
        partes.append(local)
    return ", ".join(partes)


# Aliases `{{serventia.*}}` dos modelos (contrato com Modelos Fidelidade/Editor
# — BASE_COMUM_PROPOSTA §1.2). Alias -> chave de `dados()`.
ALIASES_MODELOS: Mapping[str, str] = MappingProxyType({
    "nome": "unit_name",
    "unit_name": "unit_name",
    "cns": "ri_cns",
    "cnpj": "serventia_cnpj",
    "cidade": "ri_cidade",
    "uf": "ri_uf",
    "cidade_uf": "cidade_uf",
    "endereco": "serventia_endereco",
    "endereco_completo": "endereco_completo",
    "cep": "serventia_cep",
    "telefone": "serventia_telefone",
    "email": "serventia_email",
    "titular": "serventia_titular",
    "titulo": "serventia_titulo",
    "substituta": "ri_substituta",
    "brasao": "serventia_brasao",
})


def namespace_modelos(dados_dict: Mapping[str, Any]) -> dict:
    """O dict que os modelos enxergam como `serventia.*`. SO LE.

    Recebe o resultado de `dados()` e devolve `{alias: valor}` com os aliases
    de `ALIASES_MODELOS`. Chave ausente vira texto vazio (nunca KeyError no
    meio de uma previa).
    """
    dados_dict = dados_dict or {}
    return {alias: _texto(dados_dict.get(chave))
            for alias, chave in ALIASES_MODELOS.items()}


# --------------------------------------------------------------- LGPD

def quem_assina_o_papel(dados_da_serventia: dict) -> dict:
    """Quem assina o papel que sai da casa: `{oficial, cargo, nome}`. SO LE.

    **DA REGRA VIVA, E NUNCA ESCRITO NO MODELO** — o cabecalho que o E-Oficio
    guardava traz a oficial ANTERIOR, com endereco e CEP diferentes; copia-lo
    para dentro de um modelo traria o oficial de ontem para o papel de hoje.

    **E NUM LUGAR SO**: a notificacao da usucapiao e a da retificacao montam o
    mesmo bloco de assinatura, e duas montagens divergiriam no primeiro
    conserto — o papel de um modulo passaria a dizer quem o do outro nao diz.
    """
    dados_da_serventia = dados_da_serventia or {}
    return {
        "oficial": str(dados_da_serventia.get("serventia_titular") or ""),
        "cargo": str(dados_da_serventia.get("serventia_titulo") or "Oficial"),
        "nome": str(dados_da_serventia.get("unit_name") or ""),
    }


def _digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def mascarar_documento(valor: Any) -> str:
    """CPF e CNPJ com o miolo escondido, para documento que sai do cartorio.

    O CPF fica ***.456.789-**, mantendo o que a Receita e o proprio titular
    usam para conferir, e escondendo o bastante para o papel nao servir de
    fonte de dado pessoal se for extraviado. E a forma que o CNJ e o STJ ja
    adotam nas publicacoes.

    CNPJ e de pessoa juridica e nao e dado pessoal: sai inteiro.
    """
    n = _digitos(valor)
    if len(n) == 11:
        return f"***.{n[3:6]}.{n[6:9]}-**"
    if len(n) == 14:
        return f"{n[:2]}.{n[2:5]}.{n[5:8]}/{n[8:12]}-{n[12:]}"
    if not n:
        return ""
    # Documento de outro tipo: esconde o miolo do mesmo jeito.
    if len(n) > 4:
        return n[:2] + "*" * (len(n) - 4) + n[-2:]
    return "*" * len(n)


def mascarar_telefone(valor: Any) -> str:
    """Telefone com o miolo escondido: (99) *****-1234."""
    n = _digitos(valor)
    if len(n) < 8:
        return "*" * len(n) if n else ""
    ddd = n[:2] if len(n) >= 10 else ""
    resto = n[2:] if ddd else n
    visivel = resto[-4:]
    escondido = "*" * (len(resto) - 4)
    corpo = f"{escondido}-{visivel}" if escondido else visivel
    return f"({ddd}) {corpo}" if ddd else corpo


def mascarar_email(valor: Any) -> str:
    """joao.silva@exemplo.com -> jo***@exemplo.com."""
    texto = str(valor or "").strip()
    if "@" not in texto:
        return texto
    usuario, dominio = texto.split("@", 1)
    if len(usuario) <= 2:
        return f"{usuario[:1]}***@{dominio}"
    return f"{usuario[:2]}***@{dominio}"


def mascarar_texto(texto: Any) -> str:
    """Esconde CPF e telefone soltos dentro de um texto livre.

    Serve para campo de observacao e descricao, onde o dado pessoal entra
    digitado no meio da frase e nao num campo proprio.
    """
    t = str(texto or "")
    t = re.sub(r"\b\d{3}\.?\d{3}\.?\d{3}-?\d{2}\b",
               lambda m: mascarar_documento(m.group(0)), t)
    t = re.sub(r"\(?\d{2}\)?\s?9?\d{4}-?\d{4}\b",
               lambda m: mascarar_telefone(m.group(0)), t)
    return t
