"""O OURO DO LF06G — os papéis da retificação e da usucapião ANTES de o texto
sair do código.

`LF06G_papeis.json`, ao lado, foi gravado em 19/10/2026 na árvore do commit
2c41e90, ANTES de qualquer linha do LF06G, pelo `gerar()` abaixo: as constantes
`rt_notificacao.MODELO`, `us_notificacao.CABECA/CORPO/EDITAL/OFICIO_AO_ENTE` e
as f-strings de `usucapiao.modelos_de_decisao` e do pedido do dossiê ainda
existiam, e cada papel saiu delas. Sem dado real de pessoa — os nomes são «DE
EXEMPLO», o CPF e o CNPJ são os de teste.

    constantes[nome]  o texto das constantes que saíram do código
    funcoes[nome]     o papel montado, contexto por contexto — inclusive os
                      casos em que o montador RECUSA (o erro também é saída)

**NÃO SE REGERA.** Depois do LF06G as constantes não existem mais, e `gerar()`
leria a base: o teste passaria a comparar a base com ela mesma. Para conferir o
gerador, rode-o numa cópia do commit 2c41e90 (`git worktree add`).

`chamadas()` é a mesma lista que o gerador usou; o teste a refaz depois da
mudança — sem `busca` (o padrão da base) e com `busca` (a busca única pela
conexão da casa, sem ajuste) — e compara saída por saída.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "LF06G_papeis.json"

AGORA = "2026-10-19T09:00:00"
HOJE = "2026-10-19"
HOJE_EXTENSO = "Cidade Exemplo-MA, 19 de outubro de 2026"

SERVENTIA = {"nome": "OFÍCIO ÚNICO DE EXEMPLO", "oficial": "FULANO DE EXEMPLO",
             "cargo": "Tabelião e Oficial de Registro"}

SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "serventia_titular": "FULANO DE EXEMPLO",
      "serventia_titulo": "Tabelião e Oficial de Registro"}


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def constantes() -> dict:
    """O texto que morava no código, lido das constantes — só na árvore de antes."""
    import rt_notificacao as RTN
    import rt_tjma as NORMA
    import us_notificacao as UN
    return {"rt_notificacao.MODELO": RTN.MODELO,
            "us_notificacao.CABECA": UN.CABECA,
            "us_notificacao.CORPO": UN.CORPO,
            "us_notificacao.EDITAL": UN.EDITAL,
            "us_notificacao.OFICIO_AO_ENTE": UN.OFICIO_AO_ENTE,
            "rt_tjma.SILENCIO_VALE_ANUENCIA": dict(NORMA.SILENCIO_VALE_ANUENCIA),
            "rt_tjma.COMO_NOTIFICAR": [dict(x) for x in NORMA.COMO_NOTIFICAR]}


def processo_de_exemplo(con) -> int:
    """Um processo de usucapião hipotético, para o dossiê. ESCREVE no banco de teste."""
    import usucapiao as US
    pid = US.autuar(con, numero="US-2026-901", modalidade="EXTRAORDINARIA",
                    agora=AGORA, requerente_nome="MARIA DE EXEMPLO",
                    requerente_documento="00000000191",
                    imovel_descricao="Lote 4 da Quadra B, de exemplo",
                    imovel_municipio="Cidade Exemplo", usuario="TESTE")
    US.juntar_peca(con, pid, tipo="ATA_NOTARIAL", agora=AGORA,
                   teor="Compareceu a requerente e declarou posse de exemplo.")
    return pid


def chamadas(busca=None, con=None, processo_id: int | None = None) -> dict:
    """Cada montador, contexto por contexto.

    `busca` é a conexão que o montador recebe para ler o modelo pela busca
    única (ajuste da casa → padrão da base); sem ela, ele lê o padrão. Na
    árvore de antes os montadores não a aceitavam — o gerador a deixa vazia.
    `con` e `processo_id` são o banco e o processo do dossiê, que lê o banco
    nas duas árvores.

    A data por extenso vem PRONTA (`hoje_extenso`): quem a monta é a tela, e o
    relógio dela não é o do papel.
    """
    import rt_notificacao as RTN
    import us_notificacao as UN
    import usucapiao as US

    com = {"con": busca} if busca is not None else {}
    f: dict = {}

    # ------------------------------------------------ retificação
    p_rt = {"numero": "9/2026", "ano": 2026,
            "requerente_nome": "ANTONIO DE EXEMPLO",
            "matricula_numero": "3.247", "area_na_matricula": "30,7770 ha",
            "area_pretendida": "31,1000 ha", "perimetro": "2.345,67 m",
            "profissional_nome": "ENG. BELTRANO DE EXEMPLO",
            "profissional_conselho": "CREA-MA",
            "profissional_registro": "123456", "art_numero": "MA2026/1"}
    c_rt = {"nome": "SICRANO DE EXEMPLO", "endereco": "Fazenda Vizinha, zona rural",
            "papel": "Confrontante", "divisa_afetada": 1,
            "documento": "00000000191", "matricula_contigua": "1.234",
            "serventia_contigua": "Registro de Imóveis de Cidade Exemplo"}
    casos_rt = {
        "completo": (p_rt, c_rt, SERVENTIA, HOJE_EXTENSO),
        "minimo": ({"numero": "12", "requerente_nome": "ANTONIO DE EXEMPLO"},
                   {"nome": "SICRANO DE EXEMPLO", "endereco": "Rua Exemplo, 10"},
                   {}, ""),
        "contigua_sem_divisa": (
            {"numero": "12", "ano": 2025, "requerente_nome": "ANTONIO DE EXEMPLO",
             "area_pretendida": "1.000 m²"},
            {"nome": "SICRANO DE EXEMPLO", "endereco": "Rua Exemplo, 10",
             "divisa_afetada": 0, "matricula_contigua": "1.234"},
            SERVENTIA, HOJE_EXTENSO),
        "divisa_cnpj_so_art": (
            {**p_rt, "profissional_conselho": "", "profissional_registro": "",
             "matricula_numero": ""},
            {"nome": "EMPRESA DE EXEMPLO", "endereco": "Rua Exemplo, 10",
             "papel": "Titular de direito real", "divisa_afetada": 1,
             "documento": "00000042000122"},
            SERVENTIA, HOJE_EXTENSO),
        "divisa_rg_matricula_sem_serventia": (
            {**p_rt, "art_numero": ""},
            {"nome": "SICRANO DE EXEMPLO", "endereco": "Rua Exemplo, 10",
             "divisa_afetada": True, "documento": "RG 1234567",
             "matricula_contigua": "1.234"},
            SERVENTIA, HOJE_EXTENSO),
        "profissional_so_nome": (
            {**p_rt, "profissional_conselho": "", "profissional_registro": "",
             "art_numero": "", "perimetro": ""},
            {"nome": "SICRANO DE EXEMPLO", "endereco": "Rua Exemplo, 10",
             "divisa_afetada": 1, "serventia_contigua": "Registro de Exemplo"},
            {"nome": "OFÍCIO ÚNICO DE EXEMPLO"}, HOJE_EXTENSO),
        "sem_endereco": (p_rt, {"nome": "SICRANO DE EXEMPLO"}, SERVENTIA,
                         HOJE_EXTENSO),
    }
    for nome, (p, c, s, h) in casos_rt.items():
        f[f"rt_notificacao.montar({nome})"] = (
            lambda p=p, c=c, s=s, h=h: RTN.montar(
                processo=p, confrontante=c, serventia=s, hoje_extenso=h, **com))

    # O PRAZO EM DIAS CORRIDOS. A norma de hoje dá «úteis» ao art. 599, e o
    # ramo dos corridos só se alcança trocando o prazo — que é o que o
    # montador lê (`prazo_para_impugnar`), e não um número escrito nele.
    def _com_prazo(dias, uteis):
        original = RTN.prazo_para_impugnar
        RTN.prazo_para_impugnar = lambda: {"dias": dias, "uteis": uteis}
        try:
            return RTN.montar(processo=p_rt, confrontante=c_rt,
                              serventia=SERVENTIA, hoje_extenso=HOJE_EXTENSO,
                              **com)
        finally:
            RTN.prazo_para_impugnar = original
    f["rt_notificacao.montar(prazo_corrido_30)"] = lambda: _com_prazo(30, False)
    f["rt_notificacao.montar(prazo_util_7)"] = lambda: _com_prazo(7, True)

    # ------------------------------------------------ usucapião: notificação
    p_us = {"numero": "2026.001", "ano": 2026, "modalidade": "EXTRAORDINARIA",
            "modalidade_rotulo": "Extraordinária",
            "requerente_nome": "MARIA DE EXEMPLO",
            "imovel_descricao": "Lote 4 da Quadra B, de exemplo",
            "imovel_endereco": "Rua Exemplo, 100", "imovel_municipio":
            "Cidade Exemplo", "imovel_uf": "MA", "imovel_area": "360 m²",
            "posse_tempo_alegado": "há mais de quinze anos",
            "posse_inicio": "2005"}
    n_us = {"destinatario": "SICRANO DE EXEMPLO",
            "destinatario_papel": "Confrontante",
            "endereco": "Rua Vizinha, 200", "forma": "PESSOAL",
            "prazo_chave": "CONFRONTANTE", "prazo_dias": 15}
    casos_us = {
        "pessoal_completo": (p_us, n_us, SERVENTIA, HOJE_EXTENSO),
        "rtd_titular_posse_desde": (
            {**p_us, "posse_tempo_alegado": "", "imovel_uf": "",
             "imovel_area": "", "ano": None},
            {**n_us, "forma": "RTD", "prazo_chave": "TITULAR_TABULAR"},
            SERVENTIA, HOJE_EXTENSO),
        "correio_sem_chave_minimo": (
            {"modalidade": "ORDINARIA", "imovel_descricao": "Gleba de exemplo"},
            {**n_us, "forma": "correio", "prazo_chave": "", "prazo_dias": 10},
            {}, ""),
        "edital_ente": (
            {**p_us, "posse_tempo_alegado": "", "posse_inicio": "",
             "imovel_endereco": "", "imovel_municipio": ""},
            {**n_us, "forma": "EDITAL", "prazo_chave": "ENTE_PUBLICO",
             "destinatario_papel": "Ente público"},
            SERVENTIA, HOJE_EXTENSO),
        "sem_descricao_do_imovel": (
            {**p_us, "imovel_descricao": ""}, n_us, SERVENTIA, HOJE_EXTENSO),
        "sem_endereco": (p_us, {**n_us, "endereco": ""}, SERVENTIA,
                         HOJE_EXTENSO),
        "forma_que_nao_existe": (p_us, {**n_us, "forma": "FAX"}, SERVENTIA,
                                 HOJE_EXTENSO),
    }
    for nome, (p, n, s, h) in casos_us.items():
        f[f"us_notificacao.montar({nome})"] = (
            lambda p=p, n=n, s=s, h=h: UN.montar(
                processo=p, notificacao=n, serventia=s, hoje_extenso=h, **com))

    # ------------------------------------------------ usucapião: edital
    casos_edital = {
        "sem_origem_com_posse": (p_us, True, SERVENTIA, HOJE_EXTENSO),
        "com_origem_sem_posse": (
            {**p_us, "posse_tempo_alegado": "", "ano": None, "imovel_area": ""},
            False, SERVENTIA, HOJE_EXTENSO),
        "minimo": ({"numero": "7", "requerente_nome": "MARIA DE EXEMPLO",
                    "imovel_descricao": "Gleba de exemplo"}, False, {}, ""),
        "sem_requerente": ({**p_us, "requerente_nome": ""}, False, SERVENTIA,
                           HOJE_EXTENSO),
    }
    for nome, (p, sem_origem, s, h) in casos_edital.items():
        f[f"us_notificacao.montar_edital({nome})"] = (
            lambda p=p, o=sem_origem, s=s, h=h: UN.montar_edital(
                processo=p, serventia=s, hoje_extenso=h, imovel_sem_origem=o,
                **com))

    # ------------------------------------------------ usucapião: ofício ao ente
    for ente in ("União", "Estado", "Município"):
        f[f"us_notificacao.montar_oficio_ao_ente({ente})"] = (
            lambda e=ente: UN.montar_oficio_ao_ente(
                ente=e, processo=p_us, serventia=SERVENTIA,
                hoje_extenso=HOJE_EXTENSO, **com))
    f["us_notificacao.montar_oficio_ao_ente(minimo)"] = (
        lambda: UN.montar_oficio_ao_ente(
            ente="Município", processo={
                "numero": "7", "requerente_nome": "MARIA DE EXEMPLO",
                "imovel_descricao": "Gleba de exemplo",
                "imovel_area": "2 ha"},
            serventia={}, hoje_extenso="", **com))
    f["us_notificacao.montar_oficio_ao_ente(ente_errado)"] = (
        lambda: UN.montar_oficio_ao_ente(
            ente="Distrito", processo=p_us, serventia=SERVENTIA,
            hoje_extenso=HOJE_EXTENSO, **com))
    f["us_notificacao.montar_oficio_ao_ente(sem_numero)"] = (
        lambda: UN.montar_oficio_ao_ente(
            ente="União", processo={**p_us, "numero": ""}, serventia=SERVENTIA,
            hoje_extenso=HOJE_EXTENSO, **com))

    # ------------------------------------------------ usucapião: decisões
    p_dec = {"numero": "US-2026-901", "modalidade": "EXTRAORDINARIA",
             "requerente_nome": "MARIA DE EXEMPLO",
             "imovel_descricao": "Lote 4 da Quadra B, de exemplo"}
    f["usucapiao.modelos_de_decisao(completo)"] = (
        lambda: US.modelos_de_decisao(p_dec, SV, **com))
    f["usucapiao.modelos_de_decisao(vazio)"] = (
        lambda: US.modelos_de_decisao(
            {"numero": "7", "modalidade": "OUTRA", "requerente_nome": "",
             "imovel_descricao": None}, {}, **com))

    # ------------------------------------------------ usucapião: dossiê
    if con is not None and processo_id is not None:
        for mascarar in (True, False):
            f[f"usucapiao.montar_dossie(mascarar={mascarar})"] = (
                lambda m=mascarar: {
                    k: v for k, v in US.montar_dossie(
                        con, processo_id, hoje=HOJE, mascarar=m).items()
                    if k in ("texto", "sha256", "pecas", "mascarado")})
    return f


def gerar(raiz: Path, con) -> None:
    """Grava o ouro. SÓ NA ÁRVORE DE ANTES (commit 2c41e90) — ver o cabeçalho."""
    pid = processo_de_exemplo(con)
    funcoes = {nome: tenta(f) for nome, f in chamadas(None, con, pid).items()}
    commit = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    ARQUIVO.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06G, das constantes e f-strings do commit "
                   f"{commit}, pelo gerador ouro_lf06g.py (relatório "
                   "relatorios/LF06G.md). Não regerar: depois da mudança as "
                   "constantes não existem mais, e regerar a partir da base "
                   "faria o teste comparar a base com ela mesma."),
         "commit": commit, "constantes": normal(constantes()),
         "funcoes": normal(funcoes)},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ouro() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))
