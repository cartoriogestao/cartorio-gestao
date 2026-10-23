"""O ouro do LF06B, grupo A — as frases de `ri_web` e `ri_certidao_negativa`.

Gerado ANTES da mudança, na árvore do commit 2c41e90 (ver `ouro_lf06b.py`):

    python tests/fixtures/modelos_ouro/ouro_lf06b.py /tmp/lf06b_antes a

Cada ramo da regra que escolhe a frase tem a sua chamada: há / não há
prenotação, uma / várias, campo do protocolo presente / ausente; cada um dos
cinco motivos do encerramento, com título / sem título / sem nome de quem
assina; documento / nome / descrição do imóvel na negativa. Nomes «DE
EXEMPLO», CPF de teste (LGPD) e datas fixas — nada de `date.today()`.
"""
from __future__ import annotations


def chamadas() -> dict:
    """{nome: chamada} — o mesmo contexto antes e depois da mudança."""
    import ri_certidao_negativa as RINEG
    import ri_web as W

    def _data(v):
        # O `fmt_date` da casa, fixo: dd/mm/aaaa.
        s = str(v)[:10]
        return f"{s[8:10]}/{s[5:7]}/{s[0:4]}"

    f: dict = {}

    # -- clausula_html_prenotacoes_abertas: não há / há uma / há várias
    um = {"numero": "4.321", "data_prenotacao": "2026-09-08",
          "natureza_titulo": "Escritura pública de compra e venda",
          "objeto": "Lote 10 da Quadra 2"}
    so_numero = {"numero": " 77 "}
    com_escape = {"numero": "12<b>", "data_prenotacao": "2026-09-01",
                  "natureza_titulo": "Cédula & aditivo", "objeto": "\"casa\" <1>"}
    sem_numero = {"numero": None, "objeto": "Gleba de exemplo"}
    f["clausula_html_prenotacoes_abertas([])"] = (
        lambda: W.clausula_html_prenotacoes_abertas([], fmt_date=_data))
    f["clausula_html_prenotacoes_abertas([]) sem fmt_date"] = (
        lambda: W.clausula_html_prenotacoes_abertas([]))
    f["clausula_html_prenotacoes_abertas(uma completa)"] = (
        lambda: W.clausula_html_prenotacoes_abertas([um], fmt_date=_data))
    f["clausula_html_prenotacoes_abertas(uma so numero)"] = (
        lambda: W.clausula_html_prenotacoes_abertas([so_numero], fmt_date=_data))
    f["clausula_html_prenotacoes_abertas(uma sem fmt_date)"] = (
        lambda: W.clausula_html_prenotacoes_abertas([um]))
    f["clausula_html_prenotacoes_abertas(duas)"] = (
        lambda: W.clausula_html_prenotacoes_abertas([um, so_numero], fmt_date=_data))
    f["clausula_html_prenotacoes_abertas(tres com escape)"] = (
        lambda: W.clausula_html_prenotacoes_abertas(
            [com_escape, sem_numero, um], fmt_date=_data))

    # -- modelos_de_encerramento: os cinco motivos × quem assina
    m2 = {"numero": "1234", "livro": "2", "livro_norm": "2"}
    m3 = {"numero": "56A", "livro": "3-A", "livro_norm": "3"}
    quem = {
        "titulo e artigo": ("FULANO DE EXEMPLO", "Oficial Registrador", "O"),
        "titulo sem artigo": ("FULANA DE EXEMPLO", "Escrevente Autorizada", None),
        "artigo A": ("FULANA DE EXEMPLO", "Oficiala Substituta", "A"),
        "sem titulo": ("FULANO DE EXEMPLO",),
        "sem nome": None,
        "nome vazio": ("", "Oficial Registrador", "O"),
    }
    for rot, q in quem.items():
        f[f"modelos_de_encerramento(m2, {rot})"] = (lambda q=q: W.modelos_de_encerramento(
            m2, 3, "2026-09-08", q, cidade="Cidade Exemplo", uf="MA"))
    f["modelos_de_encerramento(m3, sem cidade, uf padrao)"] = (
        lambda: W.modelos_de_encerramento(
            m3, 12, "2026-01-31T10:00:00", quem["titulo e artigo"]))
    f["modelos_de_encerramento(numero vazio, uf PI)"] = (
        lambda: W.modelos_de_encerramento(
            {"numero": None, "livro": ""}, 1, "2026-12-01",
            quem["sem titulo"], cidade="Cidade Exemplo", uf="PI"))

    # -- montar_identificacao: documento / nome / descrição do imóvel
    buscas = {
        "PESSOA cpf": ("00000000191", "PESSOA"),
        "PESSOA cpf com mascara": ("000.000.001-91", "PESSOA"),
        "PESSOA cnpj": ("00000042000122", "PESSOA"),
        "PESSOA nome": ("  FULANO DE EXEMPLO  ", "PESSOA"),
        "PESSOA numero curto": ("12345", "PESSOA"),
        "PESSOA vazio": ("", "PESSOA"),
        "PESSOA None": (None, "PESSOA"),
        "IMOVEL descricao": ("Rua de Exemplo, 10 — Cidade Exemplo", "IMOVEL"),
        "IMOVEL cpf": ("00000000191", "IMOVEL"),
        "IMOVEL vazio": ("", "IMOVEL"),
    }
    for rot, (b, modo) in buscas.items():
        f[f"montar_identificacao({rot})"] = (
            lambda b=b, modo=modo: RINEG.montar_identificacao(b, modo=modo))

    # -- selos_do_ato_rotulados: ficou no código (ver o relatório do lote);
    #    o ouro confere que continua igual.
    pre = "PRENOT000000AAAAAAAAAAAAAAAA"
    reg = "REGAVD000000BBBBBBBBBBBBBBBB"
    arq = "ARQUIV000000CCCCCCCCCCCCCCCC"
    mat = "MATRIC000000DDDDDDDDDDDDDDDD"
    av2 = "AVESVD000000EEEEEEEEEEEEEEEE"
    f["selos_do_ato_rotulados(R, reg+pre)"] = (
        lambda: W.selos_do_ato_rotulados("R", [reg, pre]))
    f["selos_do_ato_rotulados(AV, dois comuns + arq + mat)"] = (
        lambda: W.selos_do_ato_rotulados("AV", [reg, arq, av2, mat, pre]))
    f["selos_do_ato_rotulados(R, vazio)"] = (
        lambda: W.selos_do_ato_rotulados("R", None))
    return f
