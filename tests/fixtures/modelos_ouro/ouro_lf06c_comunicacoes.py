"""O ouro do grupo «comunicacoes» do LF06C — as comunicações que saem da casa.

O que se grava aqui, ANTES de o texto sair do código (árvore do commit
2c41e90), e se confere depois, saída por saída:

    rc_comunicacoes.montar        a comunicação mensal de óbitos (art. 226) —
                                  vira o papel RC_COMUNICACAO_OBITOS. Os cinco
                                  destinos, o filtro de cada um, a linha cheia,
                                  a vazia, a sem idade, o «Nada consta» e a
                                  serventia em branco;
    rc_comunicacoes.registrar_envio   o teor e o hash que CONGELAM no envio;
    rc_funai.montar               o ofício à FUNAI (art. 253, § 2º) — vira o
                                  papel RC_OFICIO_FUNAI. Cheio, vazio (todos os
                                  «[COMPLETAR…]»), as quedas do livro e do
                                  termo, e as três recusas.

E os que FICAM NO CÓDIGO — o texto deles é lido de volta, ou é formato de
fio, ou é o catálogo próprio da casa —, gravados só para provar que o lote
não mexeu neles: `rc_cpf.texto_averbacao`/`reescrever_teor_cpf`,
`rc_etiqueta_averbacao.teor_com_lavratura`/`teor_com_selo`/`arquivo_odt` (o
`content.xml`, nunca os bytes do zip), `rc_anotacao.resumo_do_assento`,
`rc_pedidos._averbacoes`, `rc_termo.qualificacao` e `rc_modelos_livres`
(`valores`, `conferir_corpo`, `montar`).

O banco não entra: cada chamada troca a leitura (`banco`, `_exigir`,
`obitos_do_mes`, `lugar_do_assento`) por um dublê, dentro dela mesma, e
`modelos_da_casa.texto_do_papel` pelo padrão da pasta — inofensivo na árvore
de antes, que não o chamava. Sem dado real de pessoa: os nomes são «DE
EXEMPLO», o CPF é o de teste (000.000.001-91) e a matrícula é inventada.
"""
from __future__ import annotations

from unittest import mock

SV = {"nome": "SERVENTIA DE EXEMPLO", "cidade": "Cidade Exemplo", "uf": "MA",
      "registrador": "FULANA DE EXEMPLO", "titulo": "Oficiala Registradora"}

# Os quatro óbitos do mês. A idade sai de `data_nascimento` e `data_fato`.
OBITOS = {
    # cheio: mulher de 75 anos
    901: {"id": 901, "numero": 1201, "nome": "MARIA DE EXEMPLO",
          "data_ato": "2026-09-08T10:00:00", "data_fato": "2026-09-05",
          "matricula": "000000 01 55 2026 4 00012 201 0001201 11",
          "numero_do": "3000000001", "livro_volume": "C-4", "sexo": "F",
          "documento_numero": "000.000.001-91",
          "data_nascimento": "1951-03-10"},
    # tudo vazio: sem nome e sem idade (entra em todos os destinos)
    902: {"id": 902, "numero": None, "nome": None, "data_ato": None,
          "data_fato": None, "matricula": None, "numero_do": None,
          "livro_volume": None, "sexo": None, "documento_numero": None,
          "data_nascimento": None},
    # homem de 26, o resto em branco
    903: {"id": 903, "numero": "", "nome": "JOÃO DE EXEMPLO", "data_ato": "",
          "data_fato": "2026-09-12", "matricula": "", "numero_do": "",
          "livro_volume": "", "sexo": "M", "documento_numero": "",
          "data_nascimento": "2000-01-20"},
    # menina de 7
    904: {"id": 904, "numero": 1204, "nome": "ANA DE EXEMPLO",
          "data_ato": "2026-09-20", "data_fato": "2026-09-18",
          "matricula": "", "numero_do": "3000000004", "livro_volume": "C-4",
          "sexo": "F", "documento_numero": "",
          "data_nascimento": "2019-02-01"},
    # idade ZERO (nasceu e morreu no mesmo ano, antes do aniversário): o zero
    # é idade, e não «não informada»
    905: {"id": 905, "numero": 0, "nome": "JOÃO DE EXEMPLO FILHO",
          "data_ato": "2026-09-25", "data_fato": "2026-09-24",
          "matricula": None, "numero_do": None, "livro_volume": None,
          "sexo": "M", "documento_numero": None,
          "data_nascimento": "2026-01-15"},
}


class _Banco:
    """O dublê de `bd_nativo.banco(con)`: devolve o que lhe deram e anota o
    que lhe pediram para gravar."""

    def __init__(self, um=None, ler=()):
        self._um, self._ler, self.gravado = um, list(ler), []

    def um(self, sql, args=()):
        return dict(self._um) if self._um is not None else None

    def ler(self, sql, args=()):
        return [dict(x) for x in self._ler]

    def escrever(self, sql, args=()):
        self.gravado.append(list(args))
        return []

    def _escrita(self):
        return None


def _pela_pasta():
    """`texto_do_papel(con, chave)` → o padrão da pasta, sem banco."""
    import modelos_da_casa as CASA
    return mock.patch.object(CASA, "texto_do_papel",
                             lambda con, chave: CASA.padrao_de(chave))


def _comunicacao(destino, ids, serventia=SV, competencia="2026-09"):
    def chamar():
        import rc_comunicacoes as COM
        lista = [dict(OBITOS[i]) for i in ids]
        with _pela_pasta(), \
                mock.patch.object(COM, "_exigir", lambda con, cid: {
                    "id": cid, "competencia": competencia,
                    "destino": destino}), \
                mock.patch.object(COM, "obitos_do_mes",
                                  lambda con, comp: [dict(o) for o in lista]):
            r = COM.montar(object(), 1, serventia=serventia)
        return {"texto": r["texto"], "quantos": r["quantos"],
                "quantos_no_mes": r["quantos_no_mes"],
                "entram": [o["id"] for o in r["entram"]],
                "ficam_de_fora": [o["id"] for o in r["ficam_de_fora"]]}
    return chamar


def _envio(destino, ids):
    def chamar():
        import rc_comunicacoes as COM
        lista = [dict(OBITOS[i]) for i in ids]
        bd = _Banco()
        linha = {"id": 7, "competencia": "2026-09", "destino": destino,
                 "situacao": "PENDENTE"}
        with _pela_pasta(), \
                mock.patch.object(COM, "_exigir", lambda con, cid: dict(linha)), \
                mock.patch.object(COM, "_exigir_para_gravar",
                                  lambda con, cid: dict(linha)), \
                mock.patch.object(COM, "obitos_do_mes",
                                  lambda con, comp: [dict(o) for o in lista]), \
                mock.patch.object(COM, "banco", lambda con: bd):
            volta = COM.registrar_envio(
                object(), 7, canal="OFÍCIO", protocolo="PROT-EXEMPLO-1",
                quando="2026-10-03", agora="2026-10-03T09:00:00",
                serventia=SV, usuario="FULANA DE EXEMPLO")
        return {"volta": volta, "gravado": bd.gravado}
    return chamar


def _funai(assento, onde, serventia, etnia="", aldeia=""):
    def chamar():
        import rc_certidao
        import rc_funai as F
        with _pela_pasta(), \
                mock.patch.object(F, "banco", lambda con: _Banco(um=assento)), \
                mock.patch.object(rc_certidao, "lugar_do_assento",
                                  lambda con, aid: dict(onde)):
            return F.montar(object(), 55, serventia=serventia, etnia=etnia,
                            aldeia=aldeia)
    return chamar


NASC_CHEIO = {"id": 55, "especie": "NASCIMENTO", "cor_raca": "Indígena",
              "nome": "MARIA DE EXEMPLO", "data_fato": "2026-09-01",
              "data_ato": "2026-09-03T10:00:00", "livro_volume": "A-3",
              "numero": 123,
              "matricula": "000000 01 55 2026 1 00003 123 0000123 45"}
NASC_VAZIO = {"id": 55, "especie": "NASCIMENTO", "cor_raca": " INDIGENA ",
              "nome": None, "data_fato": "", "data_ato": None,
              "livro_volume": None, "numero": None, "matricula": ""}


def _comunicacoes() -> dict:
    f: dict = {}
    todos = [901, 902, 903, 904]
    for destino in ("ELEITORAL", "ECONOMIA", "RECEITA", "IDENTIFICACAO",
                    "JUNTA_MILITAR"):
        f[f"rc_comunicacoes.montar({destino})"] = _comunicacao(destino, todos)
    f["rc_comunicacoes.montar(JUNTA_MILITAR,so_mulheres)"] = _comunicacao(
        "JUNTA_MILITAR", [901, 904])
    f["rc_comunicacoes.montar(RECEITA,mes_vazio,serventia_vazia)"] = (
        _comunicacao("RECEITA", [], serventia={}))
    f["rc_comunicacoes.montar(ELEITORAL,serventia_com_None)"] = _comunicacao(
        "ELEITORAL", [901], serventia={k: None for k in SV})
    f["rc_comunicacoes.montar(ECONOMIA,idade_zero)"] = _comunicacao(
        "ECONOMIA", [905, 902])
    f["rc_comunicacoes.montar(eleitoral_minusculo)"] = _comunicacao(
        "eleitoral", [903])
    f["rc_comunicacoes.montar(destino_que_nao_existe)"] = _comunicacao(
        "CORREIO", [901])
    f["rc_comunicacoes.registrar_envio(ELEITORAL)"] = _envio(
        "ELEITORAL", todos)
    f["rc_comunicacoes.registrar_envio(JUNTA_MILITAR,nada_consta)"] = _envio(
        "JUNTA_MILITAR", [901, 904])
    return f


def _funais() -> dict:
    f: dict = {}
    cheio_onde = {"livro": "A-3", "folha": "12", "termo": "123"}
    serv = {"nome": "SERVENTIA DE EXEMPLO", "cns": "000000"}
    f["rc_funai.montar(cheio)"] = _funai(
        NASC_CHEIO, cheio_onde, serv, etnia="POVO DE EXEMPLO",
        aldeia="ALDEIA DE EXEMPLO")
    f["rc_funai.montar(cheio,sem_etnia_nem_aldeia)"] = _funai(
        NASC_CHEIO, cheio_onde, serv)
    f["rc_funai.montar(vazio)"] = _funai(NASC_VAZIO, {}, {})
    f["rc_funai.montar(queda_do_livro_e_do_termo)"] = _funai(
        {**NASC_CHEIO, "livro_volume": "B-2", "numero": 77},
        {"livro": "", "folha": None, "termo": ""},
        {"nome": "   ", "cns": None}, etnia="   ", aldeia="ALDEIA DE EXEMPLO")
    f["rc_funai.montar(numero_zero)"] = _funai(
        {**NASC_VAZIO, "numero": 0, "livro_volume": " "},
        {"livro": None, "folha": 0, "termo": None}, serv,
        etnia="POVO DE EXEMPLO")
    f["rc_funai.montar(sem_assento)"] = _funai(None, cheio_onde, serv)
    f["rc_funai.montar(obito)"] = _funai(
        {**NASC_CHEIO, "especie": "OBITO"}, cheio_onde, serv)
    f["rc_funai.montar(parda)"] = _funai(
        {**NASC_CHEIO, "cor_raca": "Parda"}, cheio_onde, serv)
    return f


def _cpf() -> dict:
    import rc_cpf as CPF
    f: dict = {}
    cpf = "00000000191"
    variantes = {
        "simples": {},
        "formatado": {"cpf": "000.000.001-91"},
        "nome_e_rotulo": {"nome": "MARIA DE EXEMPLO",
                          "papel_rotulo": "Primeiro nubente"},
        "so_rotulo": {"papel_rotulo": "  Segundo nubente "},
        "so_nome": {"nome": " JOÃO DE EXEMPLO "},
        "completo": {"selo": "SELO-EXEMPLO-1", "data": "2026-09-08T10:00:00",
                     "usuario": "FULANA DE EXEMPLO", "funcao": "Escrevente"},
        "completo_sem_funcao": {"selo": " SELO-EXEMPLO-2 ",
                                "data": "08/09/2026",
                                "usuario": "FULANA DE EXEMPLO"},
        "usuario_operador": {"selo": "S1", "data": "bobagem",
                             "usuario": "operador", "funcao": "Escrevente"},
        "usuario_robo": {"usuario": "Robô Selador", "funcao": "Robô"},
        "tudo": {"nome": "MARIA DE EXEMPLO", "papel_rotulo": "Primeiro nubente",
                 "selo": "S1", "data": "2026-09-08", "usuario": "FULANA DE EXEMPLO",
                 "funcao": "Oficiala"},
        "invalido": {"cpf": "00000000192"},
    }
    for nome, kw in variantes.items():
        kw = dict(kw)
        numero = kw.pop("cpf", cpf)
        f[f"rc_cpf.texto_averbacao({nome})"] = (
            lambda n=numero, k=kw: CPF.texto_averbacao(n, **k))

    selar = {"selo": "S1", "data": "2026-09-08", "usuario": "FULANA DE EXEMPLO",
             "funcao": "Escrevente"}
    teores = {
        "simples": "Averbo neste assento o CPF n. 000.000.001-91.",
        "nome_e_rotulo": ("Averbo neste assento o CPF n. 000.000.001-91, "
                          "referente ao primeiro nubente, MARIA DE EXEMPLO."),
        "so_rotulo": ("Averbo neste assento o CPF n. 000.000.001-91, "
                      "referente ao segundo nubente."),
        "so_nome": ("Averbo neste assento o CPF n. 000.000.001-91, "
                    "referente a JOÃO DE EXEMPLO."),
        "nome_com_ponto": ("Averbo neste assento o CPF n. 000.000.001-91, "
                           "referente ao primeiro nubente, MARIA S. DE EXEMPLO."),
        "antigo_com_espacos": "averbo  neste assento o CPF nº 00000000191 OLD",
        "digito_errado": "Averbo neste assento o CPF n. 000.000.001-92.",
        "nao_e_cpf": "Averbo neste assento o divórcio do casal.",
        "vazio": "",
        "none": None,
    }
    for nome, teor in teores.items():
        f[f"rc_cpf.reescrever_teor_cpf({nome})"] = (
            lambda t=teor: CPF.reescrever_teor_cpf(t, **selar))
    f["rc_cpf.reescrever_teor_cpf(antigo_so_selo)"] = (
        lambda: CPF.reescrever_teor_cpf(
            "averbo  neste assento o CPF nº 00000000191 OLD", selo="S1"))
    f["rc_cpf.reescrever_teor_cpf(sem_nada)"] = (
        lambda: CPF.reescrever_teor_cpf(teores["nome_e_rotulo"]))
    return f


def _odt(dados, medidas):
    def chamar():
        import io
        import zipfile

        import rc_etiqueta_averbacao as EA
        with zipfile.ZipFile(io.BytesIO(EA.arquivo_odt(dados, medidas))) as z:
            return {"nomes": z.namelist(),
                    **{n: z.read(n).decode("utf-8") for n in z.namelist()}}
    return chamar


def _etiqueta() -> dict:
    import etiqueta as ETQ
    import rc_etiqueta_averbacao as EA
    f: dict = {}
    lavra = {
        "espacos": ("  Averbo o divórcio do casal.  ", "  FULANA DE EXEMPLO "),
        "sem_nome": ("Averbo o divórcio do casal.", None),
        "teor_vazio": ("", "FULANA DE EXEMPLO"),
        "ja_tem_linha": ("Averbo o divórcio.\n  lavrado POR: OUTRA DE EXEMPLO",
                         "FULANA DE EXEMPLO"),
        "cpf": ("Averbo neste assento o CPF n. 000.000.001-91. S1.",
                "FULANA DE EXEMPLO"),
        "no_meio_da_linha": ("Averbo, e foi Lavrado por: alguém, o divórcio.",
                             "FULANA DE EXEMPLO"),
        "none": (None, "FULANA DE EXEMPLO"),
    }
    for nome, (teor, quem) in lavra.items():
        f[f"rc_etiqueta_averbacao.teor_com_lavratura({nome})"] = (
            lambda t=teor, q=quem: EA.teor_com_lavratura(t, q))
    selo = {
        "acrescenta": ("Averbo o divórcio.\nLavrado por: FULANA DE EXEMPLO.",
                       " SELO-EXEMPLO-1 "),
        "em_branco": ("Averbo o divórcio.", "  "),
        "none": ("Averbo o divórcio.", None),
        "ja_esta_no_texto": ("Averbo o divórcio. SELO-EXEMPLO-1.",
                             "SELO-EXEMPLO-1"),
        "outra_linha_de_selo": ("Averbo o divórcio.\nselo: OUTRO-SELO",
                                "SELO-EXEMPLO-1"),
        "teor_vazio": ("", "SELO-EXEMPLO-1"),
    }
    for nome, (teor, numero) in selo.items():
        f[f"rc_etiqueta_averbacao.teor_com_selo({nome})"] = (
            lambda t=teor, n=numero: EA.teor_com_selo(t, n))

    cheio = {"tipo": "averbacao", "livro": "A-3", "folha": "12",
             "termo": "123", "assento_id": 55, "ato_id": 9,
             "nome": "MARIA DE EXEMPLO",
             "teor": "Averbo o divórcio <do casal> & mais.\n\nfim",
             "lavrou": "FULANA DE EXEMPLO", "selo": "SELO-EXEMPLO-1",
             "cartorio": "SERVENTIA DE EXEMPLO"}
    cpf = {"tipo": "AVERBACAO", "livro": "A-3", "folha": 0, "termo": "",
           "assento_id": 55, "ato_id": 10, "nome": "",
           "teor": ("Averbo neste assento o CPF n. 000.000.001-91. "
                    "SELO-EXEMPLO-2. 08/09/2026. FULANA DE EXEMPLO, Escrevente."),
           "lavrou": "FULANA DE EXEMPLO", "selo": "SELO-EXEMPLO-2",
           "cartorio": "SERVENTIA DE EXEMPLO"}
    medidas = dict(ETQ.PADRAO_DA_AVERBACAO)
    torta = {**medidas, "etiqueta_deslocamento_x_mm": "-3",
             "etiqueta_deslocamento_y_mm": "2.5", "etiqueta_corpo_pt": "5"}
    f["rc_etiqueta_averbacao.arquivo_odt(cheio)"] = _odt(cheio, medidas)
    f["rc_etiqueta_averbacao.arquivo_odt(nu)"] = _odt({}, medidas)
    f["rc_etiqueta_averbacao.arquivo_odt(cpf)"] = _odt(cpf, medidas)
    f["rc_etiqueta_averbacao.arquivo_odt(anotacao,deslocada)"] = _odt(
        {**cheio, "tipo": "anotacao", "lavrou": "", "selo": ""}, torta)
    f["rc_etiqueta_averbacao.arquivo_odt(retificacao,deslocada)"] = _odt(
        {**cheio, "tipo": "Retificacao"}, torta)
    return f


def _resumo(linha):
    def chamar():
        import rc_anotacao as ANOT
        with mock.patch.object(ANOT, "banco", lambda con: _Banco(um=linha)):
            return ANOT.resumo_do_assento(object(), 55)
    return chamar


def _margem(linhas):
    def chamar():
        import rc_pedidos as RP
        with mock.patch.object(RP, "banco", lambda con: _Banco(ler=linhas)):
            return RP._averbacoes(object(), 55)
    return chamar


def _outros() -> dict:
    f: dict = {}
    f["rc_anotacao.resumo_do_assento(cheio)"] = _resumo(
        {"especie": "NASCIMENTO", "numero": 123, "livro_volume": "A-3",
         "data_ato": "2026-09-03T10:00:00", "data_fato": "2026-09-01",
         "nome": "MARIA DE EXEMPLO",
         "matricula": "000000 01 55 2026 1 00003 123 0000123 45"})
    f["rc_anotacao.resumo_do_assento(obito_vazio)"] = _resumo(
        {"especie": "OBITO", "numero": 9, "livro_volume": None,
         "data_ato": None, "data_fato": None, "nome": None, "matricula": None})
    f["rc_anotacao.resumo_do_assento(casamento_sem_numero)"] = _resumo(
        {"especie": "CASAMENTO", "numero": None, "livro_volume": "B-1",
         "data_ato": "2026-08-01", "data_fato": "", "nome": "JOÃO DE EXEMPLO",
         "matricula": ""})
    f["rc_anotacao.resumo_do_assento(sem_assento)"] = _resumo(None)

    f["rc_pedidos._averbacoes(tres)"] = _margem([
        {"rotulo": "AV-1", "teor": "Averbo o divórcio do casal."},
        {"rotulo": None, "teor": " Anoto o casamento. "},
        {"rotulo": "AV-3", "teor": "   "},
        {"rotulo": " ", "teor": "Retifico o nome."}])
    f["rc_pedidos._averbacoes(vazio)"] = _margem([])

    pessoas = {
        "cpf_cheio": {"nacionalidade": " Brasileira ", "estado_civil": "Solteira",
                      "profissao": "Lavradora", "documento_tipo": "cpf",
                      "documento_numero": " 000.000.001-91 ",
                      "documento_orgao": "SSP/MA",
                      "naturalidade_cidade": "Cidade Exemplo",
                      "naturalidade_uf": "MA", "data_nascimento": "1990-05-04",
                      "endereco": "Rua de Exemplo, 1", "bairro": "Centro",
                      "cidade": "Cidade Exemplo", "uf": "MA"},
        "rg": {"documento_tipo": "RG", "documento_numero": "123456"},
        "cnh": {"documento_tipo": "cnh", "documento_numero": "999",
                "documento_orgao": "DETRAN/MA"},
        "sem_tipo": {"documento_numero": "777", "naturalidade_uf": "MA"},
        "so_uf": {"naturalidade_uf": "MA", "uf": "MA"},
        "none": None,
        "vazio": {},
    }
    for nome, p in pessoas.items():
        def _q(p=p):
            import rc_termo
            return rc_termo.qualificacao(p)
        f[f"rc_termo.qualificacao({nome})"] = _q
    f.update(_livres())
    return f


def _contexto(especie):
    pessoa = {"nome": "MARIA DE EXEMPLO", "documento_tipo": "",
              "documento_numero": "00000000191", "sexo": "F",
              "profissao": "Lavradora", "nacionalidade": "brasileira",
              "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA",
              "data_nascimento": "1990-05-04", "estado_civil": "casada",
              "endereco": "Rua de Exemplo, 1", "bairro": "Centro",
              "cidade": "Cidade Exemplo", "uf": "MA", "cep": "65000-000",
              "idade_no_fato": None}
    homem = {**pessoa, "nome": "JOÃO DE EXEMPLO", "sexo": "Masculino",
             "documento_tipo": "RG", "documento_numero": "123456",
             "documento_orgao": "SSP/MA"}
    papeis = {"NASCIMENTO": ("REGISTRADO", "MAE", "PAI", "AVO_MATERNA"),
              "CASAMENTO": ("NUBENTE1", "NUBENTE2", "TESTEMUNHA"),
              "OBITO": ("FALECIDO", "DECLARANTE")}[especie]
    todas = []
    for i, papel in enumerate(papeis):
        base = homem if i % 2 else pessoa
        todas.append({**base, "papel": papel, "ordem": i})
    todas.append({**homem, "nome": "ANA DE EXEMPLO", "papel": "TESTEMUNHA",
                  "ordem": 9})
    quem: dict = {}
    for p in todas:
        quem.setdefault(p["papel"], p)
    a = {"id": 55, "especie": especie, "nome": "MARIA DE EXEMPLO",
         "numero": 123, "livro_volume": "", "data_ato": "2026-09-03T10:00:00",
         "data_fato": "2026-09-01", "hora_fato": "",
         "matricula": "00000001552026100003123000012345",
         "regime_bens": "COMUNHAO_PARCIAL", "cor_raca": "Parda",
         "numero_do": "3000000001"}
    d = {"strLivro": "A-3", "strHoraNascimento": "10:30",
         "strCausaMorte": "causa de exemplo", "intIdade": "75",
         "strMunicipioFalecimento": "Cidade Exemplo", "strUFFalecimento": "MA"}
    return {"a": a, "d": d, "quem": quem, "todas": todas,
            "ato": {"folha": "12", "selo": "SELO-EXEMPLO-1"},
            "sv": {"serventia_titular": "SERVENTIA DE EXEMPLO",
                   "cidade": "Cidade Exemplo", "ri_uf": "MA",
                   "registrador": "FULANA DE EXEMPLO",
                   "titulo": "Oficiala Registradora"},
            "hoje": "2026-10-19"}


def _livres() -> dict:
    f: dict = {}
    for esp in ("NASCIMENTO", "CASAMENTO", "OBITO"):
        def _v(e=esp):
            import rc_modelos_livres as ML
            return ML.valores(_contexto(e), e)
        f[f"rc_modelos_livres.valores({esp})"] = _v

    corpos = {
        "chaves": "Certifico que {nome}, termo {termo}, livro {livro}, "
                  "folha {folha}. {cidade}/{uf}, {data_de_hoje_extenso}.",
        "claro_com_espaco": "Certifico que { nome }, termo {termo}.",
        "claro_desconhecido": "Certifico que {nome_do_pai}.",
    }
    for nome, corpo in corpos.items():
        def _c(c=corpo):
            import rc_modelos_livres as ML
            return ML.conferir_corpo("NASCIMENTO", c)
        f[f"rc_modelos_livres.conferir_corpo({nome})"] = _c

        def _m(c=corpo):
            import rc_modelos_livres as ML
            modelo = {"id": 1, "especie": "NASCIMENTO",
                      "nome": "Papel de exemplo", "corpo": c}
            with mock.patch.object(ML, "ler", lambda con, mid: dict(modelo)), \
                    mock.patch.object(ML, "contexto",
                                      lambda con, aid, **kw: _contexto(
                                          "NASCIMENTO")):
                r = ML.montar(object(), 1, 55, serventia={}, hoje="2026-10-19")
            return {"texto": r["texto"], "vazios": r["vazios"]}
        f[f"rc_modelos_livres.montar({nome})"] = _m
    return f


def chamadas() -> dict:
    f: dict = {}
    f.update(_comunicacoes())
    f.update(_funais())
    f.update(_cpf())
    f.update(_etiqueta())
    f.update(_outros())
    return f
