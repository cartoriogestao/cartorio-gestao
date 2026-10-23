"""O OURO DO LF06C, GRUPO «termos» — o termo do Registro Civil antes de as frases saírem do código.

O que se cobre:

    · `rc_modelos_do_livro` — a qualificação das partes (`qualificacao_inteira`),
      as frases ocasionais dos quatro termos (nascimento, casamento, óbito e
      Livro E), o CPF e o «primeiro registro» do nascimento, o motor do
      formulário (`montar_do_formulario`, o traço da casa, quem assina), a
      limpeza do texto corrido e a data por extenso;
    · `rc_termo.qualificacao` — a qualificação dos papéis avulsos, que fica no
      código e entra aqui só para provar que não mudou.

Cada REGRA que decide se uma frase entra tem a sua chamada: sexo M, F e vazio;
um, dois ou nenhum; campo vazio; origem do acervo; natimorto; cada espécie do
Livro E; cada estado das marcas do óbito. Os termos montados de ponta a ponta
(`montar_*_do_assento`) são o texto que a lavratura congela no livro, e cada um
grava os `valores` E o `texto` — `limpar` esconde diferença de espaço, os
valores não.

As VARREDURAS (`varre.*`) combinam os campos de cada regra e guardam só a
contagem e o sha256 das saídas, para o ouro não virar um livro: a
`qualificacao_inteira` sozinha passa de vinte mil combinações.

Sem dado real de pessoa: os nomes são «DE EXEMPLO», o CPF é o de teste
(000.000.001-91) e as cidades são «Cidade Exemplo». Nada aqui depende do
relógio nem da conexão com o banco.
"""
from __future__ import annotations

import hashlib
import itertools
import json

# ------------------------------------------------------------------ os dados
SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "EX", "estado": "Estado Exemplo"}
KW = dict(sv=SV, escrevente="FULANA DE EXEMPLO",
          funcao_do_escrevente="Escrevente Autorizada")

A = {"data_ato": "2026-08-19", "data_fato": "2026-08-08", "hora_fato": "14:30",
     "cor_raca": "PARDA", "dnv": "12345678901",
     "naturalidade_declarada": "Cidade Exemplo/EX",
     "cpf_registrado": "000.000.001-91",
     "matricula": "000000 01 55 2026 1 00024 169 0019555 53",
     "local_fato_nome": "Hospital Exemplo", "local_fato_endereco": "Rua Exemplo, 1",
     "nome": "ANA DE EXEMPLO", "origem": "MANUAL", "especie": "NASCIMENTO",
     "pais_casamento_lugar": "Cidade Exemplo",
     "pais_casamento_cartorio": "Ofício Exemplo"}
REG = {"papel": "REGISTRADO", "nome": "ANA DE EXEMPLO", "sexo": "F"}
MAE = {"papel": "MAE", "nome": "MARIA DE EXEMPLO", "sexo": "F",
       "nacionalidade": "brasileira", "profissao": "lavradora",
       "idade_no_fato": "29", "cpf": "00000000191"}
PAI = {"papel": "PAI", "nome": "JOÃO DE EXEMPLO", "sexo": "M",
       "nacionalidade": "brasileiro"}
DEC = {"papel": "DECLARANTE", "nome": "JOÃO DE EXEMPLO", "sexo": "M"}
AV = [{"papel": "AVO_MATERNO", "nome": "PEDRO DE EXEMPLO"},
      {"papel": "AVO_MATERNA", "nome": "ROSA DE EXEMPLO"},
      {"papel": "AVO_PATERNO", "nome": "PAULO DE EXEMPLO"},
      {"papel": "AVO_PATERNA", "nome": "LUZIA DE EXEMPLO"}]
P = [REG, MAE, PAI, DEC, *AV]

CHEIA = {"nome": "MARIA DE EXEMPLO", "sexo": "F", "nacionalidade": "brasileira",
         "estado_civil": "solteira", "profissao": "lavradora",
         "documento_tipo": "RG", "documento_numero": "123456",
         "documento_orgao": "SSP/EX", "cpf": "000.000.001-91",
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "EX",
         "data_nascimento": "1990-02-01", "endereco": "Rua Exemplo, 1",
         "bairro": "Centro", "cidade": "Cidade Exemplo", "uf": "EX"}

TN = ("Aos dezenove (19) de agosto, compareceu JOÃO DE EXEMPLO. Lido e achado "
      "conforme, o(a) declarante assina.")

# --- casamento
N1 = {"papel": "NUBENTE1", "nome": "JOÃO DE EXEMPLO", "sexo": "M",
      "nacionalidade": "brasileiro", "profissao": "lavrador",
      "cpf": "00000000191", "nome_pos": "JOÃO DE EXEMPLO"}
N2 = {"papel": "NUBENTE2", "nome": "MARIA DE EXEMPLO", "sexo": "F",
      "nacionalidade": "brasileira", "profissao": "professora",
      "nome_pos": "MARIA DE EXEMPLO SOUSA"}
CAS_PESSOAS = [
    N1, N2,
    {"papel": "MAE_NUBENTE1", "nome": "ANA DE EXEMPLO"},
    {"papel": "PAI_NUBENTE1", "nome": "PEDRO DE EXEMPLO"},
    {"papel": "MAE_NUBENTE2", "nome": "RITA DE EXEMPLO"},
    {"papel": "TESTEMUNHA", "nome": "CARLOS DE EXEMPLO"},
    {"papel": "TESTEMUNHA", "nome": "LUCIA DE EXEMPLO"},
    {"papel": "TESTEMUNHA", "nome": "PAULO DE EXEMPLO"}]
CAS_CHEIO = {"data_ato": "2026-08-30", "regime_bens": "COMUNHAO_PARCIAL",
             "habilitacao_serventia": "Cartório de Exemplo de Outra Cidade/MA",
             "proclamas_data": "2026-08-01",
             "uniao_estavel_processo": "0000000-00.2026.8.10.0000",
             "nubente1_conjuge_anterior": "BEATRIZ DE EXEMPLO",
             "nubente1_dissolucao_data": "2020-05-03",
             "nubente2_conjuge_anterior": "ROBERTO DE EXEMPLO",
             "pacto_data": "2026-07-15", "pacto_serventia": "Tabelionato de Exemplo"}
DOCS = [{"descricao": "Certidão de nascimento", "apresentado": 1, "de_quem": "NUBENTE1"},
        {"descricao": "Certidão de nascimento", "apresentado": 1, "de_quem": "NUBENTE2"},
        {"codigo": "RG", "apresentado": 1},
        {"descricao": "Comprovante de residência", "apresentado": 1},
        {"descricao": "Certidão de óbito do cônjuge anterior", "dispensado": 1,
         "dispensado_motivo": "nubentes solteiros"},
        {"descricao": "Declaração de testemunhas", "dispensado": 1},
        {"descricao": "Documento não entregue"}]
SV2 = {"ri_cidade": "Cidade Exemplo", "estado": "Estado de Exemplo", "ri_uf": "EX"}
QUEM = {"escrevente": "ESCREVENTE DE EXEMPLO",
        "funcao_do_escrevente": "Escrevente Autorizado"}

# --- óbito
OB_ASSENTO = {"data_ato": "2026-08-30", "data_fato": "2026-08-29", "hora_fato": "14:30",
              "local_fato_nome": "Hospital de Exemplo",
              "local_fato_endereco": "Rua de Exemplo, 100",
              "numero_do": "00000000", "causa_morte": "natural",
              "atestante": "Dr. MÉDICO DE EXEMPLO",
              "atestante_documento": "CRM 0000/EX",
              "local_sepultamento": "Cemitério de Exemplo",
              "testamento": "lavrado no Tabelionato de Exemplo",
              "obito_filhos": "ANA DE EXEMPLO, 10 anos;\n\n PEDRO DE EXEMPLO, 8 anos.\n",
              "obito_herdeiros_menores": "SIM", "obito_conjuge_nome": "JOSÉ DE EXEMPLO",
              "obito_conjuge_cartorio": "Cartório de Exemplo"}
OB_PESSOAS = [{"papel": "FALECIDO", "nome": "MARIA DE EXEMPLO", "sexo": "F",
               "estado_civil": "casada", "profissao": "professora",
               "cpf": "00000000191"},
              {"papel": "DECLARANTE", "nome": "JOÃO DE EXEMPLO", "sexo": "M",
               "profissao": "lavrador"},
              {"papel": "MAE", "nome": "ANA MÃE DE EXEMPLO"},
              {"papel": "PAI", "nome": "PEDRO PAI DE EXEMPLO"}]

# --- Livro E
REG_F = {"papel": "REGISTRADO", "nome": "MARIA DE EXEMPLO", "sexo": "F",
         "nacionalidade": "brasileira", "profissao": "estudante",
         "cpf": "00000000191", "data_nascimento": "2008-03-04",
         "endereco": "Rua de Exemplo, 1", "cidade": "Cidade Exemplo", "uf": "EX"}
REG_M = dict(REG_F, nome="JOÃO DE EXEMPLO", sexo="M", nacionalidade="brasileiro")
MAE_E = {"papel": "MAE", "nome": "ANA DE EXEMPLO"}
PAI_E = {"papel": "PAI", "nome": "PEDRO DE EXEMPLO"}
TUTOR_M = {"papel": "TUTOR", "nome": "TUTOR DE EXEMPLO", "sexo": "M",
           "profissao": "comerciante"}
TUTOR_F = {"papel": "TUTOR", "nome": "TUTORA DE EXEMPLO", "sexo": "F"}
CUR_F = {"papel": "CURADOR", "nome": "CURADORA DE EXEMPLO", "sexo": "F",
         "cpf": "00000000191"}
CUR_M = {"papel": "CURADOR", "nome": "CURADOR DE EXEMPLO", "sexo": "M"}
REQ = {"papel": "REQUERENTE", "nome": "REQUERENTE DE EXEMPLO", "sexo": "M"}
REQ_SEM_NOME = {"papel": "REQUERENTE", "nome": ""}
C1 = {"papel": "COMPANHEIRO1", "nome": "JOÃO DE EXEMPLO", "sexo": "M",
      "profissao": "lavrador", "nome_pos": "JOÃO DE EXEMPLO"}
C2 = {"papel": "COMPANHEIRO2", "nome": "MARIA DE EXEMPLO", "sexo": "F",
      "profissao": "professora", "nome_pos": "MARIA DE EXEMPLO SOUSA"}
SENT = {"livro_e_titulo": "SENTENCA", "livro_e_titulo_data": "2026-09-01",
        "livro_e_juizo": "1ª Vara de Exemplo", "livro_e_juiz": "JUIZ DE EXEMPLO",
        "livro_e_processo": "0000000-00.2026.8.10.0000",
        "livro_e_transito": "2026-09-20"}
ESCR = {"livro_e_titulo": "ESCRITURA", "livro_e_titulo_data": "2026-09-01",
        "livro_e_escritura_livro": "10", "livro_e_escritura_folha": "42",
        "livro_e_tabelionato": "Tabelionato de Exemplo"}
NASC = {"livro_e_registro_nascimento": "Livro A-1, folha 2, termo 3, Cartório de Exemplo"}
CASR = {"livro_e_registro_casamento": "Livro B-1, folha 4, termo 5",
        "livro_e_conjuge": "CÔNJUGE DE EXEMPLO"}


def _pp(*ps):
    return {p["papel"]: p for p in ps}


def _tenta(f):
    try:
        return ["ok", f()]
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return ["erro", f"{type(erro).__name__}: {erro}"]


def _varre(casos):
    """Roda cada caso e guarda só a contagem e o sha256 das saídas."""
    def _f():
        saidas = [_tenta(c) for c in casos()]
        dump = json.dumps(saidas, ensure_ascii=False, sort_keys=True, default=repr)
        return {"n": len(saidas),
                "erros": sum(1 for s in saidas if s[0] == "erro"),
                "sha256": hashlib.sha256(dump.encode("utf-8")).hexdigest()}
    return _f


def _sem_vazios(d: dict) -> dict:
    return {k: v for k, v in d.items() if v is not None}


def chamadas() -> dict:
    import rc_marcas_do_obito as MO
    import rc_modelos_do_livro as L
    import rc_termo as T

    f: dict = {}

    # ============================================ rc_termo.qualificacao (fica)
    for nome, p in {
        "none": None, "vazio": {}, "so_nome": {"nome": "MARIA DE EXEMPLO"},
        "cheia": CHEIA,
        "rg_minusculo_sem_orgao": {**CHEIA, "documento_tipo": "rg", "documento_orgao": ""},
        "cpf_como_documento": {"documento_tipo": "CPF", "documento_numero": "00000000191"},
        "cnh": {"documento_tipo": "CNH", "documento_numero": "999"},
        "documento_sem_tipo": {"documento_numero": "777"},
        "so_uf_natural": {"naturalidade_uf": "EX"},
        "so_cidade_natural": {"naturalidade_cidade": "Cidade Exemplo"},
        "so_nascimento": {"data_nascimento": "1990-02-01"},
        "so_cidade": {"cidade": "Cidade Exemplo"},
        "endereco_numero": {"endereco": 12, "uf": "EX"},
        "maiusculas_com_espaco": {"nacionalidade": " BRASILEIRA ", "profissao": "LAVRADORA"},
    }.items():
        f[f"rc_termo.qualificacao.{nome}"] = lambda p=p: T.qualificacao(p)

    # ============================================ montar_do_formulario
    for esp in ("NASCIMENTO", "LIVRO_E", "OBITO", "CASAMENTO"):
        f[f"form.{esp}.vazio"] = lambda e=esp: L.montar_do_formulario(e, {})
        f[f"form.{esp}.claros_preenchidos"] = lambda e=esp: L.montar_do_formulario(
            e, {c["nome"]: f"  [{c['nome']}]\n x " for c in L.campos_do(e)})
        f[f"form.{esp}.quem_assina"] = lambda e=esp: L.montar_do_formulario(
            e, {"escrevente": "DIGITADO"}, quem_assina={
                "escrevente": "FULANA DE EXEMPLO",
                "funcao_do_escrevente": "Escrevente Autorizada"})
    corpo_curto = "{nome}|{frase_observacoes}|{escrevente}|{funcao_do_escrevente}"
    vals = {"nome": "<strong>MARIA DE EXEMPLO</strong>",
            "frase_observacoes": " Nota  de\nexemplo .", "escrevente": "",
            "funcao_do_escrevente": "Escrevente"}
    f["form.LIVRO_E.texto_proprio"] = lambda: L.montar_do_formulario(
        "LIVRO_E", vals, texto=corpo_curto)
    f["form.LIVRO_E.quem_assina_vence"] = lambda: L.montar_do_formulario(
        "LIVRO_E", vals, texto=corpo_curto, quem_assina={
            "escrevente": "FULANA DE EXEMPLO",
            "funcao_do_escrevente": "Escrevente Autorizada"})
    f["form.LIVRO_E.quem_assina_vazio_vira_traco"] = lambda: L.montar_do_formulario(
        "LIVRO_E", vals, texto=corpo_curto, quem_assina={})
    f["form.LIVRO_E.texto_vazio"] = lambda: L.montar_do_formulario(
        "LIVRO_E", vals, texto="")
    f["form.erro.chave"] = lambda: L.montar_do_formulario("XYZ", {})
    f["form.erro.claro"] = lambda: L.montar_do_formulario(
        "NASCIMENTO", {}, texto="{nome} {inexistente}")
    f["form.valores_none"] = lambda: L.montar_do_formulario("OBITO", None)

    # ============================================ limpar / datas
    for i, t in enumerate((
            "", "  a  b  ", "a ,b .c ;d :e", "linha\n\nnova\n  linha", "a\tb\t\tc",
            "Fim .  Começo , meio", " , x", "x\r\ny", "Aos {x}  ,  ")):
        f[f"limpar.{i}"] = lambda t=t: L.limpar(t)
    for v in (None, "", "2026-08-19", "19/08/2026", "2026-13-01", "2026-00-10",
              "2026-08-19T10:00:00", "2026-1-5", "abc", "2000-01-01",
              "1994-07-21", "2026-12-31 23:59"):
        f[f"data_do_termo.{v!r}"] = lambda v=v: L.data_do_termo(v)
        f[f"data_do_termo.com_numeros.{v!r}"] = lambda v=v: L.data_do_termo(
            v, com_numeros=True)
    for n, fem in ((19, False), (1, True), (2, True), (2026, False), ("8", False),
                   (0, False), (100, False), (1994, False)):
        f[f"por_extenso_com_algarismo.{n!r}.{fem}"] = (
            lambda n=n, fem=fem: L.por_extenso_com_algarismo(n, fem))
    f["por_extenso_com_algarismo.erro"] = lambda: L.por_extenso_com_algarismo("x")
    f["nome_em_negrito"] = lambda: [L.nome_em_negrito(x) for x in
                                    (None, "", "  ", " MARIA DE EXEMPLO ")]

    # ============================================ qualificacao_inteira
    QI = {
        "vazio": ({}, {}), "none": (None, {}), "cheia": (CHEIA, {}),
        "cheia_m": ({**CHEIA, "sexo": "M", "nome": "JOÃO DE EXEMPLO"}, {}),
        "cheia_sem_sexo": ({**CHEIA, "sexo": ""}, {}),
        "cheia_forca_fem": ({**CHEIA, "sexo": "M"}, {"feminino": True}),
        "cheia_forca_masc": (CHEIA, {"feminino": False}),
        "cheia_negrito": (CHEIA, {"nome_negrito": True}),
        "negrito_sem_nome": ({**CHEIA, "nome": ""}, {"nome_negrito": True}),
        "cpf_como_documento": ({"nome": "JOÃO DE EXEMPLO", "documento_tipo": "CPF",
                                "documento_numero": "00000000191"}, {}),
        "documento_sem_tipo": ({"nome": "JOÃO DE EXEMPLO",
                                "documento_numero": "123456"}, {}),
        "cnh": ({"nome": "JOÃO DE EXEMPLO", "documento_tipo": "CNH",
                 "documento_numero": "999"}, {}),
        "rg_minusculo": ({"nome": "MARIA DE EXEMPLO", "sexo": "f",
                          "documento_tipo": "rg", "documento_numero": "1"}, {}),
        "so_cidade_natal": ({"naturalidade_cidade": "Cidade Exemplo"}, {}),
        "so_uf_natal": ({"naturalidade_uf": "EX"}, {}),
        "data_br": ({"nome": "JOÃO DE EXEMPLO", "data_nascimento": "01/02/1990"}, {}),
        "data_curta": ({"nome": "JOÃO DE EXEMPLO", "data_nascimento": "1990-2-1"}, {}),
        "data_com_hora": ({"sexo": "F", "data_nascimento": "1990-02-01 10:00"}, {}),
        "endereco_cidade": ({"endereco": "Rua Exemplo, 1", "cidade": "Cidade Exemplo"}, {}),
        "bairro_cidade_uf_sem_endereco": ({"bairro": "Centro", "cidade": "Cidade Exemplo",
                                           "uf": "EX"}, {}),
        "fem_profissao_endereco_uf": ({"sexo": "F", "profissao": "lavradora",
                                       "endereco": "Rua Exemplo, 1", "uf": "EX"}, {}),
        "nome_com_espacos": ({"nome": "  MARIA  DE EXEMPLO  ", "sexo": "F"}, {}),
        "valores_numericos": ({"nome": "MARIA DE EXEMPLO", "cpf": 191,
                               "documento_numero": 123, "endereco": 12}, {}),
        "so_sexo": ({"sexo": "F"}, {}),
    }
    for nome, (p, kw) in QI.items():
        f[f"qualificacao_inteira.{nome}"] = lambda p=p, kw=kw: L.qualificacao_inteira(p, **kw)

    def _casos_qi():
        sexos = ((None, None), ("M", None), ("F", None), ("", None), ("M", True),
                 ("F", False))
        oficios = (("brasileira", "lavradora"), ("brasileira", ""), ("", ""))
        documentos = (("RG", "123456"), ("CPF", "00000000191"), ("CNH", "999"),
                      ("", "777"), ("RG", ""))
        naturais = (("Cidade Exemplo", "EX"), ("Cidade Exemplo", ""), ("", "EX"))
        moradas = (("Rua Exemplo, 1", "Centro", "Cidade Exemplo", "EX"),
                   ("Rua Exemplo, 1", "", "", ""), ("Rua Exemplo, 1", "", "", "EX"),
                   ("Rua Exemplo, 1", "Centro", "", ""), ("", "Centro", "Cidade Exemplo", "EX"),
                   ("", "", "", ""))
        for ((sexo, feminino), negrito, nome, (nac, prof), (dtipo, dnum), cpf,
             (nat, uf_nat), nasc, (end, bairro, cidade, uf)) in itertools.product(
                sexos, (False, True), ("MARIA DE EXEMPLO", ""), oficios, documentos,
                ("000.000.001-91", ""), naturais, ("1990-02-01", "01/02/1990", ""),
                moradas):
            p = _sem_vazios({"sexo": sexo, "nome": nome, "nacionalidade": nac,
                             "profissao": prof, "documento_tipo": dtipo,
                             "documento_numero": dnum, "cpf": cpf,
                             "naturalidade_cidade": nat, "naturalidade_uf": uf_nat,
                             "data_nascimento": nasc, "endereco": end,
                             "bairro": bairro, "cidade": cidade, "uf": uf})
            yield (lambda p=p, fe=feminino, ng=negrito:
                   L.qualificacao_inteira(p, feminino=fe, nome_negrito=ng))
    f["varre.qualificacao_inteira"] = _varre(_casos_qi)

    # ============================================ nascimento
    NV = {
        "cheio": (A, P, KW),
        "sv_vazio": (A, P, {}),
        "hora_14": ({**A, "hora_fato": "14"}, P, KW),
        "hora_14_dois_pontos": ({**A, "hora_fato": "14:"}, P, KW),
        "hora_espacada": ({**A, "hora_fato": " 9 : 05 "}, P, KW),
        "hora_so_minuto": ({**A, "hora_fato": ":30"}, P, KW),
        "sem_hora_cor_dnv_nat_matricula": (
            {**A, "hora_fato": "", "cor_raca": "", "dnv": "",
             "naturalidade_declarada": "", "matricula": ""}, P, KW),
        "so_endereco": ({**A, "local_fato_nome": ""}, P, KW),
        "so_local": ({**A, "local_fato_endereco": ""}, P, KW),
        "cpf_do_documento_m": (
            {**A, "cpf_registrado": ""},
            [{**REG, "sexo": "M", "documento_tipo": "cpf",
              "documento_numero": "00000000191"}, MAE, PAI, DEC], KW),
        "cpf_curto": ({**A, "cpf_registrado": "123"}, P, KW),
        "sem_cpf": ({**A, "cpf_registrado": ""}, P, KW),
        "eoficio": ({**A, "origem": "EOFICIO"}, P, KW),
        "acervo_minusculo": ({**A, "origem": "acervo"}, P, KW),
        "natimorto": ({**A, "especie": "natimorto"}, P, KW),
        "avos_so_maternos": (A, [REG, MAE, PAI, DEC, AV[0], AV[1]], KW),
        "avos_so_paternos": (A, [REG, MAE, PAI, DEC, AV[2], AV[3]], KW),
        "avos_um_de_cada": (A, [REG, MAE, PAI, DEC, AV[1], AV[2]], KW),
        "avos_so_avo_materna": (A, [REG, MAE, PAI, DEC, AV[1]], KW),
        "sem_avos": (A, [REG, MAE, PAI, DEC], KW),
        "sem_pai": (A, [REG, MAE, DEC, *AV], KW),
        "pai_sem_nome": (A, [REG, MAE, {"papel": "PAI", "nome": ""}, DEC], KW),
        "pais_so_lugar": ({**A, "pais_casamento_cartorio": ""}, P, KW),
        "pais_so_cartorio": ({**A, "pais_casamento_lugar": ""}, P, KW),
        "pais_nao_casados": ({**A, "pais_casamento_lugar": "",
                              "pais_casamento_cartorio": ""}, P, KW),
        "sem_idade": (A, [REG, {**MAE, "idade_no_fato": ""}, PAI, DEC], KW),
        "sexo_m": (A, [{**REG, "sexo": "M"}, MAE, PAI, DEC], KW),
        "sexo_vazio": (A, [{**REG, "sexo": ""}, MAE, PAI, DEC], KW),
        "papel_repetido": (A, [REG, MAE, {**MAE, "nome": "OUTRA DE EXEMPLO"},
                               {"papel": "mae", "nome": "MINUSCULA DE EXEMPLO"},
                               PAI, DEC], KW),
        "gemeos": (A, P, {**KW, "frase_gemeos": ", não é gêmeo único"}),
        "minimo": ({}, [], {}),
        "cor_minuscula": ({**A, "cor_raca": "branca"}, P, KW),
    }
    for nome, (a, p, kw) in NV.items():
        f[f"nasc.valores.{nome}"] = lambda a=a, p=p, kw=kw: L.valores_do_assento(a, p, **kw)
        f[f"nasc.montado.{nome}"] = lambda a=a, p=p, kw=kw: L.montar_do_assento(a, p, **kw)
    f["nasc.montado.corpo_da_casa"] = lambda: L.montar_do_assento(
        A, P, "{nome}{frase_cpf}{frase_primeiro_registro}{frase_naturalidade} "
              "{frase_matricula}", **KW)

    def _casos_nasc():
        # As frases do próprio assento, com as pessoas do caso cheio…
        for (hora, cor, dnv, nat, cpf, sexo, mat, origem, especie) in itertools.product(
                ("14:30", "14", "", " 9 : 05 "), ("PARDA", ""), ("123", ""),
                ("Cidade Exemplo/EX", ""), ("00000000191", "123", ""),
                ("M", "F", ""), ("000000 01 55", ""), ("MANUAL", "EOFICIO", "ACERVO"),
                ("NASCIMENTO", "NATIMORTO")):
            a = {**A, "hora_fato": hora, "cor_raca": cor, "dnv": dnv,
                 "naturalidade_declarada": nat, "cpf_registrado": cpf,
                 "matricula": mat, "origem": origem, "especie": especie}
            ps = [{**REG, "sexo": sexo}, MAE, PAI, DEC, *AV]
            yield lambda a=a, ps=ps: (L.valores_do_assento(a, ps, **KW),
                                      L.montar_do_assento(a, ps, **KW)["texto"])
        # …e as pessoas (avós, pai, casamento dos pais, idade, declarante).
        for avos, pai, (lugar, cart), idade, decl in itertools.product(
                range(16), (True, False),
                (("Cidade Exemplo", "Ofício Exemplo"), ("Cidade Exemplo", ""),
                 ("", "Ofício Exemplo"), ("", "")),
                ("29", ""), (True, False)):
            a = {**A, "pais_casamento_lugar": lugar, "pais_casamento_cartorio": cart}
            ps = [REG, {**MAE, "idade_no_fato": idade}]
            if pai:
                ps.append(PAI)
            if decl:
                ps.append(DEC)
            ps += [AV[i] for i in range(4) if avos & (1 << i)]
            yield lambda a=a, ps=ps: (L.valores_do_assento(a, ps, **KW),
                                      L.montar_do_assento(a, ps, **KW)["texto"])
    f["varre.nascimento"] = _varre(_casos_nasc)

    # ============================================ CPF e primeiro registro
    for cpf, sexo in (("00000000191", "F"), ("000.000.001-91", "M"), ("", "F"),
                      (None, "feminino"), ("123", "F"), ("00000000191", ""),
                      ("00000000191", None), (191, "m"), ("000 000 001 91", "f")):
        f[f"frase_do_cpf.{cpf!r}.{sexo!r}"] = lambda c=cpf, s=sexo: L.frase_do_cpf(c, s)
    f["frase_do_cpf.sem_sexo"] = lambda: L.frase_do_cpf("00000000191")
    for nome, (teor, kw) in {
        "none": (None, {}), "vazio": ("", {}), "espacos": ("   ", {"cpf": "00000000191"}),
        "sem_ancora": ("Texto próprio sem o fecho.", {"cpf": "00000000191"}),
        "tn": (TN, {}),
        "tn_cpf_f": (TN, {"cpf": "00000000191", "sexo": "F"}),
        "tn_cpf_m": (TN, {"cpf": "000.000.001-91", "sexo": "M"}),
        "sem_ponto_final": (TN.replace("EXEMPLO. Lido", "EXEMPLO Lido"),
                            {"cpf": "00000000191", "sexo": "F"}),
        "exclamacao": (TN.replace("EXEMPLO. Lido", "EXEMPLO! Lido"), {}),
        "ja_tem_primeiro": (TN.replace("EXEMPLO.", "EXEMPLO. Trata-se de PRIMEIRO "
                                       "REGISTRO."), {"cpf": "00000000191"}),
        "cpf_em_digitos_no_texto": (TN.replace("EXEMPLO.", "EXEMPLO, CPF 00000000191."),
                                    {"cpf": "000.000.001-91", "sexo": "F"}),
        "cpf_formatado_no_texto": (TN.replace("EXEMPLO.", "EXEMPLO, CPF 000.000.001-91."),
                                   {"cpf": "00000000191"}),
        "os_dois_no_texto": (TN.replace("EXEMPLO.", "EXEMPLO. Trata-se de primeiro "
                                        "registro. Inscrita no CPF n.º "
                                        "000.000.001-91."),
                             {"cpf": "00000000191", "sexo": "F"}),
        "ancora_no_inicio": ("Lido e achado conforme, assina.", {"cpf": "00000000191"}),
        "bordas_cpf_curto": ("  " + TN + "  ", {"cpf": "123"}),
        "cpf_curto_no_texto": (TN.replace("EXEMPLO.", "EXEMPLO 123."), {"cpf": "123"}),
        "numero": (12345, {}),
    }.items():
        f[f"completar_teor_nascimento.{nome}"] = (
            lambda t=teor, kw=kw: L.completar_teor_nascimento(t, **kw))

    # ============================================ casamento
    f.update({
        "nomes.ninguem_vazio": lambda: L.frase_dos_nomes({}, {}),
        "nomes.ninguem_none": lambda: L.frase_dos_nomes(None, None),
        "nomes.ninguem_igual": lambda: L.frase_dos_nomes(
            dict(N1), dict(N2, nome_pos=" MARIA DE EXEMPLO ")),
        "nomes.so_o_2": lambda: L.frase_dos_nomes(N1, N2),
        "nomes.so_o_1": lambda: L.frase_dos_nomes(
            dict(N1, nome_pos="JOÃO DE EXEMPLO SOUSA"), dict(N2, nome_pos="")),
        "nomes.os_dois": lambda: L.frase_dos_nomes(
            dict(N1, nome_pos="JOÃO DE EXEMPLO SOUSA"), N2),
        "nomes.sem_nome_antes": lambda: L.frase_dos_nomes({"nome_pos": "MARIA DE EXEMPLO"}, {}),
        "docs.none": lambda: L.relacao_de_documentos(None),
        "docs.so_sem_nome_e_nao_entregue": lambda: L.relacao_de_documentos(
            [{"apresentado": 1}, {"descricao": "X DE EXEMPLO"}]),
        "docs.um_apresentado": lambda: L.relacao_de_documentos(DOCS[:1]),
        "docs.dois_apresentados_dedup": lambda: L.relacao_de_documentos(DOCS[:3]),
        "docs.tres_apresentados": lambda: L.relacao_de_documentos(DOCS[:4]),
        "docs.so_dispensado_com_motivo": lambda: L.relacao_de_documentos(DOCS[4:5]),
        "docs.so_dispensado_sem_motivo": lambda: L.relacao_de_documentos(DOCS[5:6]),
        "docs.dispensados_dedup": lambda: L.relacao_de_documentos(DOCS[4:6] + DOCS[4:5]),
        "docs.dispensado_vence_apresentado": lambda: L.relacao_de_documentos(
            [dict(DOCS[4], apresentado=1)]),
        "docs.todos": lambda: L.relacao_de_documentos(DOCS),
    })
    for v in ("COMUNHAO_PARCIAL", "comunhao_universal", " SEPARACAO_TOTAL ",
              "SEPARACAO_OBRIGATORIA", "PARTICIPACAO_FINAL", "COMUNHÃO PARCIAL DE BENS",
              "", None):
        f[f"regime.{v!r}"] = lambda v=v: L.regime_por_extenso(v)
    f.update({
        "cas.valores.cheio": lambda: L.valores_do_casamento(
            CAS_CHEIO, CAS_PESSOAS, documentos=DOCS, sv=SV2, **QUEM),
        "cas.valores.fora_sem_proclamas": lambda: L.valores_do_casamento(
            dict(CAS_CHEIO, proclamas_data=""), CAS_PESSOAS, documentos=DOCS, sv=SV2,
            **QUEM),
        "cas.valores.proclamas_nao_iso": lambda: L.valores_do_casamento(
            dict(CAS_CHEIO, proclamas_data="01/08/2026"), CAS_PESSOAS, sv=SV2),
        "cas.valores.desta_casa": lambda: L.valores_do_casamento(
            {"data_ato": "2026-08-30", "regime_bens": "comunhão parcial"}, CAS_PESSOAS,
            documentos=DOCS, sv=SV2, **QUEM),
        "cas.valores.docs_digitados": lambda: L.valores_do_casamento(
            dict(CAS_CHEIO, documentos_apresentados="Certidões de nascimento e RG"),
            CAS_PESSOAS),
        "cas.valores.docs_lista_vence_digitado": lambda: L.valores_do_casamento(
            dict(CAS_CHEIO, documentos_apresentados="IGNORADO"), CAS_PESSOAS,
            documentos=DOCS[:1]),
        "cas.valores.docs_lista_vazia_usa_digitado": lambda: L.valores_do_casamento(
            dict(CAS_CHEIO, documentos_apresentados="RG"), CAS_PESSOAS,
            documentos=[{"descricao": "X"}]),
        "cas.valores.sem_nada": lambda: L.valores_do_casamento({}, []),
        "cas.valores.uma_testemunha_um_genitor": lambda: L.valores_do_casamento(
            {}, [N1, {"papel": "PAI_NUBENTE1", "nome": "PEDRO DE EXEMPLO"},
                 {"papel": "TESTEMUNHA", "nome": "CARLOS DE EXEMPLO"}]),
        "cas.montado.cheio": lambda: L.montar_casamento_do_assento(
            CAS_CHEIO, CAS_PESSOAS, documentos=DOCS, sv=SV2, **QUEM),
        "cas.montado.desta_casa_ninguem_muda": lambda: L.montar_casamento_do_assento(
            {"data_ato": "2026-08-30", "regime_bens": "SEPARACAO_TOTAL"},
            [N1, dict(N2, nome_pos="")], documentos=[], sv=SV2, **QUEM),
        "cas.montado.sem_nada": lambda: L.montar_casamento_do_assento({}, []),
        "cas.montado.corpo_da_casa": lambda: L.montar_casamento_do_assento(
            CAS_CHEIO, CAS_PESSOAS, "{nubente1_qualificacao}|{frase_habilitacao}|"
            "{regime_bens}|{frase_conversao}", documentos=DOCS, sv=SV2, **QUEM),
        "cas_ant.vazio": lambda: L.frase_do_casamento_anterior({}, "nubente1"),
        "cas_ant.so_nome": lambda: L.frase_do_casamento_anterior(CAS_CHEIO, "nubente2"),
        "cas_ant.nome_data_iso": lambda: L.frase_do_casamento_anterior(CAS_CHEIO, "nubente1"),
        "cas_ant.nome_data_livre": lambda: L.frase_do_casamento_anterior(
            dict(CAS_CHEIO, nubente1_dissolucao_data="maio de 2020"), "nubente1"),
        "cas_ant.so_data": lambda: L.frase_do_casamento_anterior(
            {"nubente1_dissolucao_data": "2020-05-03"}, "nubente1"),
        "pacto.vazio": lambda: L.frase_do_pacto({}),
        "pacto.so_data": lambda: L.frase_do_pacto({"pacto_data": "2026-07-15"}),
        "pacto.so_data_livre": lambda: L.frase_do_pacto({"pacto_data": "15 de julho"}),
        "pacto.so_serventia": lambda: L.frase_do_pacto({"pacto_serventia": "Tabelionato de Exemplo"}),
        "pacto.os_dois": lambda: L.frase_do_pacto(CAS_CHEIO),
        "pais.vazio": lambda: L.frase_do_casamento_dos_pais({}),
        "pais.so_lugar": lambda: L.frase_do_casamento_dos_pais(
            {"pais_casamento_lugar": "Cidade Exemplo/EX"}),
        "pais.so_cartorio": lambda: L.frase_do_casamento_dos_pais(
            {"pais_casamento_cartorio": "Cartório de Exemplo"}),
        "pais.os_dois": lambda: L.frase_do_casamento_dos_pais(
            {"pais_casamento_lugar": "Cidade Exemplo/EX",
             "pais_casamento_cartorio": "Cartório de Exemplo"}),
        "pais.no_nascimento_com_pai": lambda: L.valores_do_assento(
            {"pais_casamento_lugar": "Cidade Exemplo/EX",
             "pais_casamento_cartorio": "Cartório de Exemplo"},
            [{"papel": "PAI", "nome": "PEDRO DE EXEMPLO", "sexo": "M"}])["frase_filiacao2"],
        "pais.no_nascimento_sem_pai": lambda: L.valores_do_assento(
            {"pais_casamento_lugar": "Cidade Exemplo/EX"}, [])["frase_filiacao2"],
    })

    def _casos_cas():
        def _par(a, ps, d):
            return lambda: (
                L.valores_do_casamento(a, ps, documentos=d, sv=SV2, **QUEM),
                L.montar_casamento_do_assento(a, ps, documentos=d, sv=SV2,
                                              **QUEM)["texto"])
        # A habilitação, os documentos e a conversão…
        for fora, procl, docs, digit, proc in itertools.product(
                ("Cartório de Outra Cidade", ""), ("2026-08-01", "01/08", ""),
                (None, [], DOCS[:1], DOCS[4:6], DOCS), ("Certidões e RG", ""),
                ("0000000-00.2026", "")):
            a = {**CAS_CHEIO, "habilitacao_serventia": fora, "proclamas_data": procl,
                 "uniao_estavel_processo": proc, "documentos_apresentados": digit}
            yield _par(a, CAS_PESSOAS, docs)
        # …e os nubentes: casamento anterior, pacto, nomes e regime.
        for (ant1, diss1, ant2, (pdata, pserv), pos1, pos2, regime) in itertools.product(
                ("BEATRIZ DE EXEMPLO", ""), ("2020-05-03", "maio de 2020", ""),
                ("ROBERTO DE EXEMPLO", ""),
                (("2026-07-15", "Tabelionato"), ("2026-07-15", ""), ("", "Tabelionato"),
                 ("", "")),
                ("", "JOÃO DE EXEMPLO", "JOÃO DE EXEMPLO SOUSA"),
                ("", "MARIA DE EXEMPLO SOUSA"), ("COMUNHAO_PARCIAL", "livre", "")):
            a = {**CAS_CHEIO, "regime_bens": regime,
                 "nubente1_conjuge_anterior": ant1, "nubente1_dissolucao_data": diss1,
                 "nubente2_conjuge_anterior": ant2, "pacto_data": pdata,
                 "pacto_serventia": pserv}
            ps = [dict(N1, nome_pos=pos1), dict(N2, nome_pos=pos2), *CAS_PESSOAS[2:]]
            yield _par(a, ps, DOCS)
    f["varre.casamento"] = _varre(_casos_cas)

    # ============================================ óbito
    SIM4 = {m["chave"]: MO.SIM for m in MO.MARCAS}
    NAO4 = {m["chave"]: MO.NAO for m in MO.MARCAS}
    f.update({
        "ign.none": lambda: L.frase_dos_ignorados(None),
        "ign.tudo_sim": lambda: L.frase_dos_ignorados(SIM4),
        "ign.tudo_nao": lambda: L.frase_dos_ignorados(NAO4),
        "ign.um": lambda: L.frase_dos_ignorados(dict(SIM4, obito_eleitor=MO.NAO_PERGUNTADO)),
        "ign.dois": lambda: L.frase_dos_ignorados(
            dict(NAO4, obito_possui_bens="", obito_possui_filho=None)),
        "ign.tres": lambda: L.frase_dos_ignorados({"obito_desconhecido": MO.NAO}),
        "conj.nada": lambda: L.frase_do_conjuge_do_falecido({}, ""),
        "conj.so_estado": lambda: L.frase_do_conjuge_do_falecido({}, "solteira"),
        "conj.estado_sobrevivente": lambda: L.frase_do_conjuge_do_falecido(
            {"obito_conjuge_nome": "JOSÉ DE EXEMPLO"}, "casada"),
        "conj.estado_sobrevivente_cartorio": lambda: L.frase_do_conjuge_do_falecido(
            OB_ASSENTO, "casada"),
        "conj.estado_premorto_cartorio": lambda: L.frase_do_conjuge_do_falecido(
            dict(OB_ASSENTO, obito_conjuge_situacao="pre_morto"), "viúva"),
        "conj.sem_estado_sobrevivente": lambda: L.frase_do_conjuge_do_falecido(
            {"obito_conjuge_nome": "JOSÉ DE EXEMPLO",
             "obito_conjuge_situacao": "SOBREVIVENTE"}, ""),
        "conj.sem_estado_premorto_cartorio": lambda: L.frase_do_conjuge_do_falecido(
            dict(OB_ASSENTO, obito_conjuge_situacao="PRE_MORTO"), ""),
        "conj.sem_estado_sobrevivente_cartorio": lambda: L.frase_do_conjuge_do_falecido(
            OB_ASSENTO, ""),
        "conj.cartorio_sem_nome": lambda: L.frase_do_conjuge_do_falecido(
            {"obito_conjuge_cartorio": "Cartório de Exemplo"}, "divorciada"),
        "filhos.sem_lista": lambda: L.frase_dos_filhos_do_falecido({}, "Deixou filhos."),
        "filhos.sem_lista_vazio": lambda: L.frase_dos_filhos_do_falecido(
            {"obito_filhos": " \n ; \n"}, ""),
        "filhos.um": lambda: L.frase_dos_filhos_do_falecido(
            {"obito_filhos": "ANA DE EXEMPLO, 10 anos"}, "Deixou filhos."),
        "filhos.dois": lambda: L.frase_dos_filhos_do_falecido(OB_ASSENTO, "Deixou filhos."),
        "herd.sim": lambda: L.frase_dos_herdeiros({"obito_herdeiros_menores": "sim"}),
        "herd.nao": lambda: L.frase_dos_herdeiros({"obito_herdeiros_menores": "NAO"}),
        "herd.outro": lambda: L.frase_dos_herdeiros({"obito_herdeiros_menores": "TALVEZ"}),
        "herd.vazio": lambda: L.frase_dos_herdeiros({}),
        "ob.valores.cheio_sim": lambda: L.valores_do_obito(
            OB_ASSENTO, OB_PESSOAS, marcas=SIM4, sv=SV2, **QUEM),
        "ob.valores.cheio_nao": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, obito_herdeiros_menores="NAO"), OB_PESSOAS, marcas=NAO4,
            sv=SV2, **QUEM),
        "ob.valores.nada_perguntado": lambda: L.valores_do_obito({}, [], marcas=None),
        "ob.valores.so_hora": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, hora_fato="14"), OB_PESSOAS)["frase_hora"],
        "ob.valores.hora_sem_h": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, hora_fato=":30"), OB_PESSOAS)["frase_hora"],
        "ob.valores.so_local_nome": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, local_fato_endereco=""), OB_PESSOAS)["local_do_fato"],
        "ob.valores.causa_sem_atestante": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, atestante="", atestante_documento=""),
            OB_PESSOAS)["frase_causa"],
        "ob.valores.causa_so_doc": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, atestante=""), OB_PESSOAS)["frase_causa"],
        "ob.valores.causa_atestante_sem_doc": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, atestante_documento=""), OB_PESSOAS)["frase_causa"],
        "ob.valores.so_mae": lambda: L.valores_do_obito(
            OB_ASSENTO, OB_PESSOAS[:3])["frase_filiacao"],
        "ob.valores.filhos_sim_sem_lista": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, obito_filhos=""), OB_PESSOAS, marcas=SIM4)["frase_filhos"],
        "ob.valores.bens_vazio_herd_sim": lambda: L.valores_do_obito(
            OB_ASSENTO, OB_PESSOAS, marcas={})["frase_deixou_bens"],
        "ob.valores.bens_sim_herd_nao": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, obito_herdeiros_menores="NAO"), OB_PESSOAS,
            marcas=SIM4)["frase_deixou_bens"],
        "ob.valores.bens_nao_herd_vazio": lambda: L.valores_do_obito(
            dict(OB_ASSENTO, obito_herdeiros_menores=""), OB_PESSOAS,
            marcas=NAO4)["frase_deixou_bens"],
        "ob.valores.desconhecido_com_documento": lambda: L.valores_do_obito(
            OB_ASSENTO, [dict(OB_PESSOAS[0], documento_numero="123")],
            marcas=dict(NAO4, obito_desconhecido=MO.SIM)),
        "ob.valores.com_documento": lambda: L.valores_do_obito(
            OB_ASSENTO, [dict(OB_PESSOAS[0], documento_numero="123")], marcas=NAO4),
        "ob.montado.cheio_sim": lambda: L.montar_obito_do_assento(
            OB_ASSENTO, OB_PESSOAS, marcas=SIM4, sv=SV2, **QUEM),
        "ob.montado.cheio_nao": lambda: L.montar_obito_do_assento(
            dict(OB_ASSENTO, obito_herdeiros_menores="NAO"), OB_PESSOAS, marcas=NAO4,
            sv=SV2, **QUEM),
        "ob.montado.nada_perguntado": lambda: L.montar_obito_do_assento(
            {"data_ato": "2026-08-30"}, OB_PESSOAS[:2], marcas={}, sv=SV2, **QUEM),
        "ob.montado.corpo_da_casa": lambda: L.montar_obito_do_assento(
            OB_ASSENTO, OB_PESSOAS, "{frase_filiacao}|{frase_causa}|"
            "{frase_sepultamento}|{frase_ignorados}", marcas={}, sv=SV2, **QUEM),
    })

    def _casos_obito():
        def _par(a, ps, m):
            return lambda: (
                L.valores_do_obito(a, ps, marcas=m, sv=SV2, **QUEM),
                L.montar_obito_do_assento(a, ps, marcas=m, sv=SV2, **QUEM)["texto"])
        estados = (MO.SIM, MO.NAO, MO.NAO_PERGUNTADO)
        chaves = tuple(x["chave"] for x in MO.MARCAS)
        # As quatro marcas nos três estados, com herdeiros e filhos…
        for marcas, herd, filhos in itertools.product(
                itertools.product(estados, repeat=len(chaves)),
                ("SIM", "NAO", ""), (OB_ASSENTO["obito_filhos"], "")):
            a = {**OB_ASSENTO, "obito_herdeiros_menores": herd, "obito_filhos": filhos}
            yield _par(a, OB_PESSOAS, dict(zip(chaves, marcas)))
        # …as frases simples e a filiação…
        for (hora, causa, atest, atdoc, sep, test, numdo, pais) in itertools.product(
                ("14:30", "14", ""), ("natural", ""), ("Dr. MÉDICO DE EXEMPLO", ""),
                ("CRM 0000/EX", ""), ("Cemitério de Exemplo", ""),
                ("lavrado no Tabelionato", ""), ("00000000", ""), range(4)):
            a = {**OB_ASSENTO, "hora_fato": hora, "causa_morte": causa,
                 "atestante": atest, "atestante_documento": atdoc,
                 "local_sepultamento": sep, "testamento": test, "numero_do": numdo}
            ps = [OB_PESSOAS[0], OB_PESSOAS[1],
                  *([OB_PESSOAS[2]] if pais & 1 else []),
                  *([OB_PESSOAS[3]] if pais & 2 else [])]
            yield _par(a, ps, {})
        # …e o cônjuge, com e sem estado civil.
        for (cnome, ccart, csit), estado in itertools.product(
                (("JOSÉ DE EXEMPLO", "Cartório de Exemplo", ""),
                 ("JOSÉ DE EXEMPLO", "", "PRE_MORTO"),
                 ("JOSÉ DE EXEMPLO", "Cartório de Exemplo", "pre_morto"),
                 ("JOSÉ DE EXEMPLO", "", "SOBREVIVENTE"),
                 ("", "Cartório de Exemplo", ""), ("", "", "")),
                ("casada", "viúva", "")):
            a = {**OB_ASSENTO, "obito_conjuge_nome": cnome,
                 "obito_conjuge_cartorio": ccart, "obito_conjuge_situacao": csit}
            ps = [dict(OB_PESSOAS[0], estado_civil=estado), *OB_PESSOAS[1:]]
            yield _par(a, ps, {})
    f["varre.obito"] = _varre(_casos_obito)

    # ============================================ Livro E
    f.update({
        "tit.sentenca_tudo": lambda: L._do_titulo(SENT),
        "tit.sentenca_juiz_sem_juizo": lambda: L._do_titulo(dict(SENT, livro_e_juizo="")),
        "tit.sentenca_juizo_sem_juiz": lambda: L._do_titulo(
            dict(SENT, livro_e_juiz="", livro_e_processo="", livro_e_transito="")),
        "tit.sentenca_nada": lambda: L._do_titulo({"livro_e_titulo": "sentenca"}),
        "tit.escritura_tudo": lambda: L._do_titulo(ESCR),
        "tit.escritura_nada": lambda: L._do_titulo({"livro_e_titulo": "ESCRITURA"}),
        "tit.escritura_so_folha": lambda: L._do_titulo(
            {"livro_e_titulo": "ESCRITURA", "livro_e_escritura_folha": "42"}),
        "tit.termo_data": lambda: L._do_titulo(
            {"livro_e_titulo": "TERMO", "livro_e_titulo_data": "2026-09-01"}),
        "tit.termo_data_livre": lambda: L._do_titulo(
            {"livro_e_titulo": "TERMO", "livro_e_titulo_data": "01/09/2026 às 10h"}),
        "tit.termo": lambda: L._do_titulo({"livro_e_titulo": "TERMO"}),
        "tit.nenhum": lambda: L._do_titulo({}),
        "fil.nada": lambda: L._filiacao_curta(None, None, None),
        "fil.filha_dois": lambda: L._filiacao_curta(REG_F, MAE_E, PAI_E),
        "fil.filho_so_pai": lambda: L._filiacao_curta(REG_M, None, PAI_E),
        "fil.sem_sexo_so_mae": lambda: L._filiacao_curta({}, MAE_E, {"nome": ""}),
        "le.emancipacao_cheia": lambda: L.frase_do_livro_e(
            "EMANCIPACAO", {**ESCR, **NASC}, _pp(REG_F, MAE_E, PAI_E, TUTOR_M)),
        "le.emancipacao_min": lambda: L.frase_do_livro_e("EMANCIPACAO", {}, {}),
        "le.emancipacao_tutor_sem_nome": lambda: L.frase_do_livro_e(
            "EMANCIPACAO", {}, _pp(dict(TUTOR_M, nome=""))),
        "le.interdicao_cheia": lambda: L.frase_do_livro_e(
            "INTERDICAO", {**SENT, **NASC, **CASR, "livro_e_causa": "causa de exemplo",
                           "livro_e_limites": "atos patrimoniais",
                           "livro_e_internacao": "Clínica de Exemplo"},
            _pp(REG_M, REQ, CUR_F)),
        "le.interdicao_min": lambda: L.frase_do_livro_e("INTERDICAO", None, {}),
        "le.interdicao_req_sem_nome_so_conj": lambda: L.frase_do_livro_e(
            "INTERDICAO", {"livro_e_conjuge": "CÔNJUGE DE EXEMPLO"},
            _pp(REQ_SEM_NOME, CUR_M)),
        "le.interdicao_so_cas": lambda: L.frase_do_livro_e(
            "INTERDICAO", {"livro_e_registro_casamento": "Livro B-1, folha 4, termo 5"}, {}),
        "le.ausencia_cheia": lambda: L.frase_do_livro_e(
            "AUSENCIA", {**SENT, **NASC, **CASR, "livro_e_ausencia_tempo": "dois anos",
                         "livro_e_limites": "administração dos bens"},
            _pp(REG_M, REQ, CUR_M)),
        "le.ausencia_min": lambda: L.frase_do_livro_e("AUSENCIA", {}, {}),
        "le.tutela_cheia_tutora": lambda: L.frase_do_livro_e(
            "TUTELA", {**SENT, **NASC}, _pp(REG_M, MAE_E, PAI_E, TUTOR_F)),
        "le.tutela_tutor": lambda: L.frase_do_livro_e("TUTELA", {}, _pp(REG_F, TUTOR_M)),
        "le.tutela_min": lambda: L.frase_do_livro_e("TUTELA", {}, {}),
        "le.ue_cheia": lambda: L.frase_do_livro_e(
            "UNIAO_ESTAVEL", {"livro_e_titulo": "TERMO", "livro_e_titulo_data": "2026-09-01",
                              "livro_e_uniao_inicio": "2020-01-10",
                              "regime_bens": "COMUNHAO_PARCIAL", **NASC, **CASR},
            _pp(C1, C2, {"papel": "MAE_COMPANHEIRO1", "nome": "ANA DE EXEMPLO"},
                {"papel": "PAI_COMPANHEIRO2", "nome": "PEDRO DE EXEMPLO"})),
        "le.ue_um_lado_regime_livre": lambda: L.frase_do_livro_e(
            "UNIAO_ESTAVEL", {"regime_bens": "comunhão parcial"}, _pp(C2)),
        "le.ue_min": lambda: L.frase_do_livro_e("UNIAO_ESTAVEL", {}, {}),
        "le.opcao_cheia": lambda: L.frase_do_livro_e(
            "OPCAO_NACIONALIDADE", {**SENT, **NASC}, _pp(REG_F, MAE_E, PAI_E)),
        "le.opcao_min": lambda: L.frase_do_livro_e("OPCAO_NACIONALIDADE", {}, {}),
        "le.outro": lambda: L.frase_do_livro_e("OUTRO", {**SENT, **NASC}, _pp(REG_F)),
        "le.minuscula_nao_casa": lambda: L.frase_do_livro_e("tutela", {}, {}),
        "lev.interdicao": lambda: L.valores_livro_e_do_assento(
            {"especie": "INTERDICAO", "data_ato": "2026-09-30", "nome": "JOÃO DE EXEMPLO",
             **SENT, "observacoes": "Observação de exemplo."}, [REG_M, REQ, CUR_F],
            sv=SV2, **QUEM),
        "lev.sem_sv_defaults": lambda: L.valores_livro_e_do_assento(
            {"especie": "TUTELA"}, [REG_F, TUTOR_M]),
        "lev.especie_vazia": lambda: L.valores_livro_e_do_assento({}, []),
        "lev.especie_desconhecida": lambda: L.valores_livro_e_do_assento(
            {"especie": "xyz"}, [])["titulo_do_ato"],
        "lev.ue_sem_qualif": lambda: L.valores_livro_e_do_assento(
            {"especie": "uniao_estavel"}, [dict(REG_F), C1, C2],
            sv=SV2)["qualificacao_do_titular"],
        "lev.registrado_so_nome": lambda: L.valores_livro_e_do_assento(
            {"especie": "OUTRO"}, [{"papel": "REGISTRADO", "nome": "MARIA DE EXEMPLO"}])[
            "qualificacao_do_titular"],
        "lev.obs_teor_livre": lambda: L.valores_livro_e_do_assento(
            {"especie": "OUTRO", "teor_livre": "Teor livre de exemplo."}, [])[
            "frase_observacoes"],
        "lev.obs_dados_obs": lambda: L.valores_livro_e_do_assento(
            {"especie": "OUTRO", "dados": {"observacoes": "Nota de exemplo."}}, [])[
            "frase_observacoes"],
        "lev.obs_dados_teor": lambda: L.valores_livro_e_do_assento(
            {"especie": "OUTRO", "dados": {"teor": "Teor de exemplo."}}, [])[
            "frase_observacoes"],
        "lev.obs_dados_nao_dict": lambda: L.valores_livro_e_do_assento(
            {"especie": "OUTRO", "dados": "texto"}, [])["frase_observacoes"],
        "lev.montado.interdicao": lambda: L.montar_livro_e_do_assento(
            {"especie": "INTERDICAO", "data_ato": "2026-09-30", "nome": "JOÃO DE EXEMPLO",
             **SENT, "observacoes": "Observação de exemplo."}, [REG_M, REQ, CUR_F],
            sv=SV2, **QUEM),
        "lev.montado.ue_sem_sv": lambda: L.montar_livro_e_do_assento(
            {"especie": "UNIAO_ESTAVEL", "data_ato": "2026-09-30",
             "regime_bens": "SEPARACAO_TOTAL"}, [C1, C2], **QUEM),
        "lev.montado.corpo_da_casa": lambda: L.montar_livro_e_do_assento(
            {"especie": "TUTELA", "data_ato": "2026-09-30", **SENT},
            [REG_F, TUTOR_M, MAE_E], "{nome}{qualificacao_do_titular}|{frase_da_especie}",
            sv=SV2, **QUEM),
    })
    for esp, a, ps in (
            ("EMANCIPACAO", {**ESCR, **NASC}, [REG_F, MAE_E, PAI_E, TUTOR_M]),
            ("INTERDICAO", {**SENT, **NASC, **CASR, "livro_e_causa": "causa de exemplo",
                            "livro_e_limites": "atos patrimoniais",
                            "livro_e_internacao": "Clínica de Exemplo"},
             [REG_M, REQ, CUR_F]),
            ("AUSENCIA", {**SENT, **CASR, "livro_e_ausencia_tempo": "dois anos"},
             [REG_F, REQ, CUR_M]),
            ("TUTELA", {**SENT, **NASC}, [REG_M, MAE_E, PAI_E, TUTOR_F]),
            ("UNIAO_ESTAVEL", {"livro_e_titulo": "TERMO", "livro_e_uniao_inicio": "2020-01-10",
                               "regime_bens": "COMUNHAO_PARCIAL", **NASC, **CASR},
             [C1, C2]),
            ("OPCAO_NACIONALIDADE", {**SENT, **NASC}, [REG_F, MAE_E, PAI_E]),
            ("OUTRO", {"observacoes": "Observação de exemplo."}, [REG_M])):
        f[f"lev.montado.{esp}"] = lambda e=esp, a=a, ps=ps: L.montar_livro_e_do_assento(
            {"especie": e, "data_ato": "2026-09-30", "nome": ps[0]["nome"], **a}, ps,
            sv=SV2, **QUEM)

    def _casos_titulo():
        campos_s = ("livro_e_titulo_data", "livro_e_juizo", "livro_e_juiz",
                    "livro_e_processo", "livro_e_transito")
        campos_e = ("livro_e_titulo_data", "livro_e_escritura_livro",
                    "livro_e_escritura_folha", "livro_e_tabelionato")
        for tipo, base, campos in (("SENTENCA", SENT, campos_s),
                                   ("ESCRITURA", ESCR, campos_e),
                                   ("TERMO", {"livro_e_titulo_data": "2026-09-01"},
                                    ("livro_e_titulo_data",)),
                                   ("", SENT, campos_s)):
            for mascara in range(1 << len(campos)):
                a = {"livro_e_titulo": tipo,
                     **{c: base[c] for i, c in enumerate(campos) if mascara & (1 << i)}}
                yield lambda a=a: L._do_titulo(a)
    f["varre.titulo"] = _varre(_casos_titulo)

    def _casos_livro_e():
        titulos = ({}, SENT, ESCR, {"livro_e_titulo": "TERMO",
                                    "livro_e_titulo_data": "2026-09-01"})
        opcionais = {"livro_e_registro_nascimento": NASC["livro_e_registro_nascimento"],
                     "livro_e_registro_casamento": CASR["livro_e_registro_casamento"],
                     "livro_e_conjuge": CASR["livro_e_conjuge"],
                     "livro_e_causa": "causa de exemplo",
                     "livro_e_limites": "atos patrimoniais",
                     "livro_e_internacao": "Clínica de Exemplo",
                     "livro_e_ausencia_tempo": "dois anos",
                     "livro_e_uniao_inicio": "2020-01-10",
                     "regime_bens": "COMUNHAO_PARCIAL"}
        chaves = tuple(opcionais)
        pessoas = (
            (), (REG_F, MAE_E, PAI_E, TUTOR_M, REQ, CUR_F, C1, C2),
            (REG_M, PAI_E, TUTOR_F, REQ_SEM_NOME, CUR_M, dict(C2, nome_pos="")),
            (dict(REG_F, sexo=""), MAE_E, dict(TUTOR_M, nome=""), REQ, C1,
             dict(C2, nome="")),
            (REG_M, MAE_E, CUR_F, dict(C1, nome_pos="JOÃO DE EXEMPLO SOUSA"), C2,
             {"papel": "MAE_COMPANHEIRO1", "nome": "ANA DE EXEMPLO"},
             {"papel": "PAI_COMPANHEIRO2", "nome": "PEDRO DE EXEMPLO"}))
        for esp in ("EMANCIPACAO", "INTERDICAO", "AUSENCIA", "TUTELA", "UNIAO_ESTAVEL",
                    "OPCAO_NACIONALIDADE", "OUTRO", ""):
            for ti, titulo in enumerate(titulos):
                for mascara in range(1 << len(chaves)):
                    # Sem título, todas as combinações; com título, nenhuma,
                    # todas e cada uma sozinha.
                    if ti and mascara not in (0, (1 << len(chaves)) - 1) \
                            and bin(mascara).count("1") != 1:
                        continue
                    a = {**titulo, **{c: opcionais[c] for i, c in enumerate(chaves)
                                      if mascara & (1 << i)}}
                    for ps in pessoas:
                        yield lambda e=esp, a=a, ps=ps: L.frase_do_livro_e(
                            e, a, _pp(*ps))
    f["varre.frase_do_livro_e"] = _varre(_casos_livro_e)

    def _casos_lev():
        for esp in ("EMANCIPACAO", "INTERDICAO", "AUSENCIA", "TUTELA", "UNIAO_ESTAVEL",
                    "OPCAO_NACIONALIDADE", "OUTRO", "", "xyz"):
            for obs in ("", "Observação de exemplo."):
                for ps in ([], [REG_F, MAE_E, PAI_E, TUTOR_M, REQ, CUR_F, C1, C2],
                           [REG_M, CUR_M, C1], [{"papel": "REGISTRADO", "nome": ""}]):
                    for sv in (SV2, None):
                        a = {"especie": esp, "data_ato": "2026-09-30",
                             "observacoes": obs, **SENT, **NASC}
                        yield lambda a=a, ps=ps, sv=sv: (
                            L.valores_livro_e_do_assento(a, ps, sv=sv, **QUEM),
                            L.montar_livro_e_do_assento(a, ps, sv=sv, **QUEM)["texto"])
    f["varre.livro_e_do_assento"] = _varre(_casos_lev)

    return f


def textos() -> dict:
    """A constante de texto que virou peça — o valor de antes."""
    import rc_modelos_do_livro as L
    return {"rc_modelos_do_livro.FRASE_PRIMEIRO_REGISTRO": L.FRASE_PRIMEIRO_REGISTRO}
