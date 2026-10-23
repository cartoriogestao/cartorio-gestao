"""O ouro do grupo «anotacao_crc» do LF06C — a anotação sugerida a partir da CRC.

O que `rc_anotacao_crc` devolvia ANTES de o texto dos três modelos sair do
código (commit 2c41e90): a leitura do HTML da CRC (`ler_arquivo`), os três
modelos de `gerar` (compacto, completo, com fé pública) com e sem assinatura,
cidade e filtro de espécie, e cada montador (`_texto_compacto`,
`_texto_completo`, `_texto_fe_publica`) com comunicações de beira — campo
faltando, nome vazio, sem livro/folha/termo, sem serventia de origem — para
que cada frase opcional apareça presente e ausente.

Os defeitos de antes estão aqui de propósito, e o ouro os guarda byte a byte:
o óbito sem nome sai «anoto o óbito de , na serventia …»; a alteração de
estado civil sai «anoto o alterações de estado civil…» e «referente a
casamento»; o modelo com fé pública diz sempre «recebida da …».

`hoje` vai sempre dado (sem ele, `gerar` cai no `date.today()`). Sem dado real
de pessoa: os nomes são «DE EXEMPLO», as cidades e serventias, de exemplo, e o
arquivo da CRC é o de demonstração que já mora em `tests/fixtures/`.
"""
from __future__ import annotations


def _bloco(tit, org, cod, corpo,
           dest="Ao Cidade Exemplo - Registro Civil de Exemplo - MA"):
    return (f"<center>\n{tit}<br><br>\n{org}<br><br>\n{dest}<br><br>\n"
            f"Código da comunicação:\n{cod}\n<br><br>\n"
            f"<div align=\"JUSTIFY\">\n{corpo}\n\nOBSERVAÇÕES: Em Branco\n"
            f"</div>\n</center>")


ORIGEM = "Serventia de Exemplo - Cidade Modelo - MA"

HTML = "<hr>".join([
    _bloco("Comunicação de Casamento Civil", ORIGEM, "90000101",
           "Aos 01/02/2026 no livro B número 001, folhas 010, termo 0001001\n"
           "foi lavrado o assento de casamento civil de: MARIA DE EXEMPLO,\n"
           "a qual passou a assinar: MARIA DE EXEMPLO SANTOS, e JOÃO DE EXEMPLO,\n"
           "o qual continuou com o mesmo nome."),
    _bloco("Comunicação de Casamento Religioso com Efeito Civil", ORIGEM,
           "90000102",
           "Aos 02/02/2026 no livro B número 002, folhas 011, termo 0001002\n"
           "foi lavrado o assento de casamento de: MARIA DE EXEMPLO,\n"
           "a qual passou a assinar: MARIA DE EXEMPLO, e JOÃO DE EXEMPLO,\n"
           "o qual continuou com o mesmo nome."),
    _bloco("Comunicação de Casamento Civil", ORIGEM, "90000103",
           "Aos 03/02/2026 no livro B número 003 foi lavrado o assento de "
           "casamento civil de: MARIA DE EXEMPLO, nascida em Cidade Modelo."),
    _bloco("Comunicação de Casamento Civil", "", "90000108",
           "Aos 03/02/2026 foi lavrado um assento sem nomes."),
    _bloco("Comunicação de Óbito", ORIGEM, "90000104",
           "Aos 04/02/2026 no livro C número 004, folhas 012, termo 0003001\n"
           "foi registrado o óbito de MARIA DE EXEMPLO ocorrido em 01/01/2026,\n"
           "em Cidade Modelo-MA."),
    _bloco("Comunicação de Óbito", ORIGEM, "90000105",
           "Aos 05/02/2026 foi registrado o óbito de MARIA DE EXEMPLO, sem "
           "data informada."),
    _bloco("Comunicação de Óbito", ORIGEM, "90000109",
           "Aos 07/02/2026 foi lavrado o registro."),
    _bloco("Comunicação de Óbito", ORIGEM, "90000110",
           "Sem a data inicial. Óbito de MARIA DE EXEMPLO ocorrido em "
           "01/01/2026."),
    _bloco("Comunicação de Alterações de Estado Civil por Escritura Pública",
           ORIGEM, "90000106",
           "Aos 06/02/2026 no livro B número 040, folhas 013, termo 0005001\n"
           "foi averbado o divórcio por escritura pública no termo de "
           "casamento, de MARIA DE EXEMPLO e JOÃO DE EXEMPLO,\n"
           "CONFORME ESCRITURA PÚBLICA."),
    _bloco("Comunicação de Óbito", "", "90000107",
           "Registrado o óbito de MARIA DE EXEMPLO em livro próprio.", dest=""),
    "<p>bloco sem comunicação</p>"])

ORG2 = "Serventia de Exemplo - Cidade Exemplo - MA"

# Comunicações já lidas, de beira: cada frase opcional presente e ausente.
OBITOS = {
    "cheio": {"tipo": "OBITO", "titulo": "Comunicação de Óbito",
              "codigo": "90000201", "nome_principal": "MARIA DE EXEMPLO",
              "falecido": "MARIA DE EXEMPLO", "data_fato": "01/01/2026",
              "livro": "C 004", "folhas": "012", "termo": "0003001",
              "data_lavratura": "04/02/2026", "origem_serventia": ORG2,
              "destino": "Cidade Exemplo - Registro Civil de Exemplo - MA",
              "texto_corpo": "Aos 04/02/2026 foi registrado o óbito de MARIA "
                             "DE EXEMPLO ocorrido em 01/01/2026.",
              "rename_frases": ["MARIA DE EXEMPLO passou a assinar MARIA "
                                "DE EXEMPLO SANTOS"]},
    "minimo": {"tipo": "OBITO"},
    "so_falecido_e_termo": {"tipo": "OBITO", "codigo": "90000202",
                            "nome_principal": "", "falecido": "JOÃO DE EXEMPLO",
                            "termo": "0003002"},
    "so_origem": {"tipo": "OBITO", "codigo": "90000203",
                  "origem_serventia": ORG2},
    "so_data_do_fato": {"tipo": "OBITO", "codigo": "90000204",
                        "data_fato": "02/01/2026", "origem_serventia": ""},
    "nome_com_chaves": {"tipo": "OBITO", "codigo": "90000205",
                        "nome_principal": "MARIA {nome} DE EXEMPLO {}",
                        "livro": "C {0}", "origem_serventia": "Serventia {x}",
                        "texto_corpo": "texto com {chaves} e {}"},
}
CASAMENTOS = {
    "cheio": {"tipo": "CASAMENTO",
              "titulo": "Comunicação de Casamento Religioso com Efeito Civil",
              "codigo": "90000301",
              "conjuges": ["MARIA DE EXEMPLO", "JOÃO DE EXEMPLO"],
              "nome_principal": "MARIA DE EXEMPLO", "livro": "B 001",
              "folhas": "010", "termo": "0001001",
              "data_lavratura": "01/02/2026", "data_fato": "31/01/2026",
              "origem_serventia": ORG2,
              "destino": "Ao Cidade Exemplo - Registro Civil - MA",
              "texto_corpo": "Aos 01/02/2026 foi lavrado o assento.",
              "rename_frases": [
                  "MARIA DE EXEMPLO passou a assinar MARIA DE EXEMPLO SANTOS",
                  "JOÃO DE EXEMPLO passou a assinar JOÃO DE EXEMPLO SANTOS"]},
    "minimo": {"tipo": "CASAMENTO"},
    "so_nome_e_folhas": {"tipo": "CASAMENTO",
                         "titulo": "Comunicação de Casamento Civil",
                         "codigo": "90000302", "conjuges": [],
                         "nome_principal": "MARIA DE EXEMPLO",
                         "folhas": "011",
                         "rename_frases": ["MARIA DE EXEMPLO passou a assinar "
                                           "MARIA DE EXEMPLO SANTOS"]},
    "so_falecido": {"tipo": "CASAMENTO", "codigo": "90000303",
                    "nome_principal": "", "falecido": "JOÃO DE EXEMPLO",
                    "livro": "B 003", "termo": "0001003"},
    "um_conjuge_e_data": {"tipo": "CASAMENTO", "codigo": "90000304",
                          "conjuges": ["MARIA DE EXEMPLO"],
                          "data_lavratura": "03/02/2026",
                          "rename_frases": []},
    "so_origem": {"tipo": "CASAMENTO", "codigo": "90000305",
                  "origem_serventia": ORG2},
}
OUTROS = {
    "cheio": {"tipo": "OUTRO",
              "titulo": "Comunicação de Alterações de Estado Civil",
              "codigo": "90000401", "nome_principal": "MARIA DE EXEMPLO",
              "livro": "B 040", "folhas": "013", "termo": "0005001",
              "data_lavratura": "06/02/2026", "data_fato": "05/02/2026",
              "origem_serventia": ORG2, "destino": "Cidade Exemplo",
              "texto_corpo": "Aos 06/02/2026 foi averbado o divórcio.",
              "rename_frases": ["MARIA DE EXEMPLO passou a assinar MARIA"]},
    "minimo": {"tipo": "OUTRO"},
    "so_nome": {"tipo": "OUTRO", "titulo": "Averbação Diversa",
                "codigo": "90000402", "nome_principal": "JOÃO DE EXEMPLO"},
    "so_folhas_e_termo": {"tipo": "OUTRO", "titulo": "Comunicação de",
                          "codigo": "90000403", "folhas": "014",
                          "termo": "0005002"},
    "so_origem": {"tipo": "OUTRO", "codigo": "90000404",
                  "origem_serventia": ORG2, "falecido": "JOÃO DE EXEMPLO"},
}
# Só para o completo: a narrativa e a cidade de cada jeito.
COMPLETOS = {
    "observacoes_no_fim": {"tipo": "OBITO", "codigo": "90000501",
                           "texto_corpo": "Aos 04/02/2026 foi registrado o "
                                          "óbito. OBSERVAÇÕES: Em Branco",
                           "destino": ""},
    "so_observacoes": {"tipo": "CASAMENTO", "codigo": "90000502",
                       "texto_corpo": "  observações: nada  ",
                       "destino": "- Registro Civil de Exemplo"},
    "destino_sem_traco": {"tipo": "OUTRO", "titulo": "Averbação Diversa",
                          "codigo": "90000503", "texto_corpo": "Averbado.",
                          "destino": "Cidade Exemplo",
                          "origem_serventia": ORG2},
}


def chamadas() -> dict:
    """Cada saída do módulo com um contexto de teste, pelo nome."""
    import datetime
    from pathlib import Path

    import rc_anotacao_crc as CRC

    f: dict = {}
    f["CRC.MODELOS"] = lambda: CRC.MODELOS
    f["CRC.ASSINATURA_PADRAO"] = lambda: CRC.ASSINATURA_PADRAO
    for tp, tt in (("OBITO", ""), ("CASAMENTO", "Comunicação de Casamento Religioso"),
                   ("CASAMENTO", "Comunicação de Casamento Civil"),
                   ("OUTRO", "Comunicação de Alterações de Estado Civil"),
                   ("OUTRO", "Averbação Diversa"), ("OUTRO", ""),
                   ("OUTRO", "Comunicação de")):
        f[f"CRC._titulo_humano({tp},{tt!r})"] = (
            lambda tp=tp, tt=tt: CRC._titulo_humano(tp, tt))

    f["CRC.ler_arquivo(HTML)"] = lambda: CRC.ler_arquivo(HTML)
    f["CRC.ler_arquivo('')"] = lambda: CRC.ler_arquivo("")
    f["CRC.ler_arquivo(sem comunicação)"] = lambda: CRC.ler_arquivo("<p>nada</p>")

    for mid in ("compacto", "completo", "fe_publica"):
        for esp in (None, "OBITO", "CASAMENTO"):
            for ass in (None, "", "JOÃO DE EXEMPLO, Escrevente Autorizado"):
                for cid in (None, "Cidade Exemplo"):
                    f[f"CRC.gerar(HTML,{mid},especie={esp},assinatura={ass!r},"
                      f"cidade={cid})"] = (
                        lambda mid=mid, esp=esp, ass=ass, cid=cid: CRC.gerar(
                            CRC.ler_arquivo(HTML), mid, hoje="2026-09-08",
                            assinatura=ass, cidade_destino=cid, especie=esp))
        for hoje in ("08/09/2026", datetime.date(2026, 9, 8)):
            f[f"CRC.gerar(HTML,{mid},hoje={hoje!r})"] = (
                lambda mid=mid, hoje=hoje: CRC.gerar(
                    CRC.ler_arquivo(HTML), mid, hoje=hoje))
        # As comunicações de beira, todas juntas, por gerar.
        for ass in (None, "", "JOÃO DE EXEMPLO, Escrevente Autorizado"):
            f[f"CRC.gerar(beiras,{mid},assinatura={ass!r})"] = (
                lambda mid=mid, ass=ass: CRC.gerar(
                    [*OBITOS.values(), *CASAMENTOS.values(), *OUTROS.values(),
                     *COMPLETOS.values()],
                    mid, hoje="2026-09-08", assinatura=ass))
        # O exemplo da CRC que já mora em tests/fixtures (uma de cada espécie).
        f[f"CRC.gerar(exemplo da CRC,{mid})"] = (
            lambda mid=mid: CRC.gerar(
                [next(c for c in CRC.ler_arquivo(
                    (Path(CRC.__file__).resolve().parent / "tests" / "fixtures"
                     / "crc_comunicacoes_exemplo.html").read_text(
                        encoding="utf-8"))
                      if c["tipo"] == tipo)
                 for tipo in ("CASAMENTO", "OBITO", "OUTRO")],
                mid, hoje="2026-09-08", cidade_destino="Cidade Exemplo"))

    f["CRC.gerar(HTML,' Completo ')"] = lambda: CRC.gerar(
        CRC.ler_arquivo(HTML), " Completo ", hoje="2026-09-08")
    f["CRC.gerar(HTML,'xyz')"] = lambda: CRC.gerar(
        CRC.ler_arquivo(HTML), "xyz", hoje="2026-09-08")
    f["CRC.gerar(HTML,None)"] = lambda: CRC.gerar(
        CRC.ler_arquivo(HTML), None, hoje="2026-09-08")
    f["CRC.gerar(HTML,compacto,especie=OUTRO)"] = lambda: CRC.gerar(
        CRC.ler_arquivo(HTML), "compacto", hoje="2026-09-08", especie="OUTRO")
    f["CRC.gerar(HTML,compacto,especie=' obito ')"] = lambda: CRC.gerar(
        CRC.ler_arquivo(HTML), "compacto", hoje="2026-09-08", especie=" obito ")
    f["CRC.gerar([],compacto)"] = lambda: CRC.gerar([], "compacto",
                                                    hoje="2026-09-08")
    f["CRC.gerar(só óbitos,compacto,especie=CASAMENTO)"] = lambda: CRC.gerar(
        list(OBITOS.values()), "compacto", hoje="2026-09-08",
        especie="CASAMENTO")

    # Cada montador, comunicação por comunicação.
    beiras = {**{f"OBITO.{k}": v for k, v in OBITOS.items()},
              **{f"CASAMENTO.{k}": v for k, v in CASAMENTOS.items()},
              **{f"OUTRO.{k}": v for k, v in OUTROS.items()},
              **{f"COMPLETO.{k}": v for k, v in COMPLETOS.items()},
              "sem_tipo": {"codigo": "90000601"}}
    for nome, c in beiras.items():
        f[f"CRC._texto_compacto({nome})"] = (
            lambda c=c: CRC._texto_compacto(c, hoje_br="08/09/2026"))
        for cid in ("", "Cidade Exemplo"):
            for ass in ("", "JOÃO DE EXEMPLO, Escrevente Autorizado"):
                f[f"CRC._texto_completo({nome},cidade={cid!r},assinatura={ass!r})"] = (
                    lambda c=c, cid=cid, ass=ass: CRC._texto_completo(
                        c, cidade_destino=cid, assinatura=ass))
                f[f"CRC._texto_fe_publica({nome},cidade={cid!r},assinatura={ass!r})"] = (
                    lambda c=c, cid=cid, ass=ass: CRC._texto_fe_publica(
                        c, hoje_br="08/09/2026", cidade_destino=cid,
                        assinatura=ass))

    # As réguas que os montadores usam.
    for livro in ("", "C 004"):
        for folhas in ("", "012"):
            for termo in ("", "0003001"):
                f[f"CRC._indicacao_registro({livro!r},{folhas!r},{termo!r})"] = (
                    lambda livro=livro, folhas=folhas, termo=termo:
                    CRC._indicacao_registro(
                        {"livro": livro, "folhas": folhas, "termo": termo}))
    for destino, reserva in (("", ""), ("", "Cidade Exemplo"),
                             ("Cidade Exemplo - Registro Civil - MA", ""),
                             ("- Registro Civil", "Cidade Exemplo"),
                             ("- Registro Civil", ""), ("Cidade Exemplo", "")):
        f[f"CRC._cidade_do_destino({destino!r},{reserva!r})"] = (
            lambda destino=destino, reserva=reserva:
            CRC._cidade_do_destino(destino, reserva))
    for hoje in ("2026-09-08", "2026-09-08T10:00:00", "8/9/2026",
                 datetime.date(2026, 9, 8)):
        f[f"CRC._hoje_br({hoje!r})"] = lambda hoje=hoje: CRC._hoje_br(hoje)
    return f
