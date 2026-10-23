"""O ouro do grupo «certidoes» do LF06C — as certidões do Registro Civil.

O que se grava aqui, ANTES de o texto sair do código (árvore do commit
2c41e90), e se confere depois, saída por saída:

    rc_certidao.montar_teor       o teor da certidão em resumo (modelo do CNJ),
                                  que CONGELA em `rc_certidoes.teor` — o bloco
                                  «OBSERVAÇÕES/AVERBAÇÕES A ACRESCER» e o fecho
                                  viram o papel RC_CERTIDAO_RESUMO, com as peças
                                  «NADA CONSTA.» e a do assento cancelado.
                                  Nascimento, casamento (civil, religioso, do
                                  acervo), óbito, natimorto, proclamas, outro,
                                  espécie vazia, atos com e sem «Lavrado por»/
                                  «Selo», cancelado e não, serventia vazia, e
                                  chaves `{}` dentro dos dados (o `str.format`
                                  do papel não pode lê-las);
    rc_certidao.emitir            o teor e o hash que congelam, nas três
                                  modalidades e nas recusas — o banco é um
                                  dublê que anota o INSERT;
    rc_certidao_quadro.quadro_da_certidao   o quadro impresso, com a frase do
                                  assento cancelado (a mesma peça);
    rc_certidao_inteiro_teor      a introdução (papel RC_CERTIDAO_INTEIRO_TEOR,
                                  com o fim de cada modalidade como peça) em
                                  todas as espécies e com os claros cheios,
                                  parciais e vazios; o teor congelado de texto e
                                  de cópia reprográfica; o HTML e o `.odt`
                                  (`content.xml`) da impressão, com «Era o que
                                  cabia certificar.» e «CERTIDÃO CANCELADA —»
                                  (motivo com `&`, `<`, `>` e chaves).

E os que FICAM NO CÓDIGO, gravados só para provar que o lote não mexeu
neles: os títulos e marcas de `rc_certidao` (MODELOS, SEM_DADO,
SEM_INFORMACAO, data_por_extenso, regime_da_certidao), `rc_certidao_odt`
(`valores` e o `content.xml` do molde), `rc_cabecalho` (PAIS, TITULO_DO_ATO,
montar) e `rc_folha` (COLUNAS, ASSINAM_ALEM_DE_QUEM_LAVROU).

O banco não entra: cada chamada troca a leitura (`banco`, `pessoas`) por um
dublê, dentro dela mesma, e `modelos_da_casa.texto_do_papel` pelo padrão da
pasta — inofensivo na árvore de antes, que não o chamava. Sem dado real de
pessoa: os nomes são «DE EXEMPLO», o CPF é o de teste (000.000.001-91), a
matrícula e os selos são inventados.
"""
from __future__ import annotations

import base64
import io
import json
import re
import zipfile


def _sem_os_estilos(xml: str) -> str:
    """O `content.xml` do `gerar_odt` sem o bloco dos estilos automáticos.

    **OS ESTILOS EXTRAS SÃO DO PROCESSO, E NÃO DO PAPEL** (`ri_odt.
    ESTILOS_EXTRA`): o `notas_web` acrescenta a quebra de página quando a casa
    registra as rotas, e o `ri_odt` o carimbo na primeira certidão com selo.
    O mesmo papel sai com mais ou menos estilos conforme o que rodou antes no
    processo — na suíte, a tela já subiu; no gerador do ouro, não. O texto
    mora no corpo (`office:body`), que é o que o LF06C mexe e o que se compara.
    """
    return re.sub(r"<office:automatic-styles>.*?</office:automatic-styles>",
                  "", xml, flags=re.S)
from unittest import mock

HOJE = "2026-10-19"
AGORA = "2026-10-19 10:00:00"
EXT = "19 de outubro de 2026"
CPF = "000.000.001-91"
CPF_NU = "00000000191"
MAT = "000000" "01" "55" "2026" "1" "00024" "012" "0019555" "00"

# Um PNG de 1×1 — a imagem da via reprográfica. O `content.xml` só a cita.
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGA"
    "hKmMIQAAAABJRU5ErkJggg==")


def _p(papel, nome, **kw):
    return {"papel": papel, "nome": nome, **kw}


def _pela_pasta():
    """`texto_do_papel(con, chave)` → o padrão da pasta, sem banco."""
    import modelos_da_casa as CASA
    return mock.patch.object(CASA, "texto_do_papel",
                             lambda con, chave: CASA.padrao_de(chave))


# =============================================== rc_certidao.montar_teor

SV_R = {"unit_name": "OFÍCIO ÚNICO DE EXEMPLO", "ri_cidade": "Cidade Exemplo",
        "ri_uf": "MA", "ri_cns": "000000",
        "serventia_titular": "MARIA DE EXEMPLO",
        "serventia_titulo": "Oficial Registradora"}
LUGAR = {"livro": "A-24", "folha": "12", "termo": "19555"}

NASC_PESSOAS = [
    _p("REGISTRADO", "MARIA DE EXEMPLO", sexo="F", documento_tipo="CPF",
       documento_numero=CPF, naturalidade_cidade="Cidade Exemplo",
       naturalidade_uf="MA"),
    _p("PAI", "JOÃO DE EXEMPLO"), _p("MAE", "ANA DE EXEMPLO"),
    _p("AVO_PATERNO", "PEDRO DE EXEMPLO"), _p("AVO_PATERNA", "RITA DE EXEMPLO"),
    _p("AVO_MATERNO", "PAULO DE EXEMPLO"), _p("AVO_MATERNA", "LUZIA DE EXEMPLO"),
]
NASC = {"especie": "NASCIMENTO", "nome": "MARIA DE EXEMPLO",
        "matricula": "0000000155" + "0" * 22, "data_fato": "2026-10-01",
        "data_ato": "2026-10-03", "hora_fato": "08:15",
        "local_fato_nome": "HOSPITAL DE EXEMPLO",
        "local_fato_endereco": "Rua de Exemplo, 1", "ibge_gemeo": 1,
        "dnv": "00000000000", "numero": 19555, "situacao": "ATIVO"}
ATOS = [
    {"tipo": "REGISTRO", "teor": "não entra"},
    {"tipo": "AVERBACAO", "teor": "Averbo o CPF.", "lavrou": "MARIA DE EXEMPLO",
     "selo": "AVERBA000000XXXXXXXXXXXXXX"},
    {"tipo": "ANOTACAO",
     "teor": "Anoto o casamento.\nLavrado por: JOÃO DE EXEMPLO.\nSelo: X.",
     "lavrou": "OUTRO", "selo": "Y"},
    {"tipo": "RETIFICACAO", "teor": "", "criado_por": "ESCREVENTE DE EXEMPLO"},
    {"tipo": "AVERBACAO", "teor": "Teor que já cita MARIA DE EXEMPLO e SELO1.",
     "lavrou": "MARIA DE EXEMPLO", "selo": "SELO1"},
    {"tipo": "ANOTACAO", "teor": "  Sem lavrou nem selo.  "},
]
CAS_PESSOAS = [
    _p("NUBENTE1", "JOÃO DE EXEMPLO", nome_pos="JOÃO DE EXEMPLO",
       data_nascimento="1990-01-01", naturalidade_cidade="Cidade Exemplo",
       naturalidade_uf="MA", estado_civil="solteiro", profissao="lavrador",
       documento_tipo="CPF", documento_numero=CPF),
    _p("NUBENTE2", "MARIA DE EXEMPLO", nome_pos="MARIA DE EXEMPLO SOUZA",
       data_nascimento="1992-03-03", naturalidade_cidade="CIDADE EXEMPLO/MA.",
       naturalidade_uf="MA", estado_civil="solteira", profissao="professora"),
    _p("PAI_NUBENTE1", "PEDRO DE EXEMPLO"), _p("MAE_NUBENTE1", "ANA DE EXEMPLO"),
    _p("MAE_NUBENTE2", "RITA DE EXEMPLO"),
]
CAS = {"especie": "CASAMENTO", "nome": "JOÃO DE EXEMPLO E MARIA DE EXEMPLO",
       "matricula": "", "data_fato": "2026-09-21", "data_ato": "2026-09-21",
       "regime_bens": "COMUNHAO_PARCIAL", "numero": 8366}
OBITO_PESSOAS = [
    _p("FALECIDO", "MARIA DE EXEMPLO", sexo="Feminino",
       data_nascimento="1957-10-20", estado_civil="viúva",
       profissao="aposentada", naturalidade_cidade="Cidade Exemplo",
       naturalidade_uf="MA", cidade="Cidade Exemplo", uf="MA",
       documento_numero=CPF_NU),
    _p("PAI", "JOÃO DE EXEMPLO"), _p("MAE", "ANA DE EXEMPLO"),
]
OBITO = {"especie": "OBITO", "nome": "MARIA DE EXEMPLO", "matricula": "M",
         "data_fato": "2026-10-19", "data_ato": "2026-10-19",
         "hora_fato": "23:59", "local_fato_nome": "HOSPITAL DE EXEMPLO",
         "cor_raca": "PARDA", "numero_do": "0000",
         "causa_morte": "causa de exemplo", "atestante": "DR. EXEMPLO",
         "atestante_documento": "CRM/MA 0000",
         "local_sepultamento": "Cemitério de Exemplo", "testamento": "NÃO",
         "situacao": "cancelado"}


def _mt(**kw):
    def chamar():
        import rc_certidao as CE
        base = dict(atos=[], sv=SV_R, hoje=HOJE, lugar=LUGAR, data_extenso=EXT)
        base.update(kw)
        return CE.montar_teor(**base)
    return chamar


def _rc_certidao(f: dict) -> None:
    def CE():
        import rc_certidao
        return rc_certidao

    f["rc_certidao.MODELOS"] = lambda: {
        k: v["titulo"] for k, v in CE().MODELOS.items()}
    f["rc_certidao.SEM_DADO"] = lambda: CE().SEM_DADO
    f["rc_certidao.SEM_INFORMACAO"] = lambda: CE().SEM_INFORMACAO
    f["rc_certidao.titulo_do_modelo"] = lambda: {
        str(e): CE().titulo_do_modelo(e) for e in
        ("NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO",
         "NATIMORTO", "PROCLAMAS", "OUTRO", "XYZ", None, "")}
    for iso in ("2026-10-01", "2026-10-03", "1987-05-28", "2000-12-21",
                "1957-01-31", "2026-10-19T10:00:00", "2026-13-01", "2026-10",
                "", None, "abc-de-fg"):
        f[f"rc_certidao.data_por_extenso({iso!r})"] = (
            lambda i=iso: CE().data_por_extenso(i))
    for r in ("COMUNHAO_PARCIAL", "comunhao_universal", "SEPARACAO_TOTAL",
              "SEPARACAO_OBRIGATORIA", "PARTICIPACAO_FINAL",
              "COMUNHÃO PARCIAL DE BENS", "", None):
        f[f"rc_certidao.regime_da_certidao({r!r})"] = (
            lambda x=r: CE().regime_da_certidao(x))
    f["rc_certidao._lugar"] = lambda: [
        CE()._lugar(c, u) for c, u in (
            ("Cidade Exemplo", "MA"), ("CIDADE EXEMPLO/MA.", "MA"),
            ("CIDADE EXEMPLO MA", "MA"), ("", "MA"), ("Cidade Exemplo", ""),
            (None, None))]
    f["rc_certidao._sexo_por_extenso"] = lambda: [
        CE()._sexo_por_extenso(x) for x in ("M", "f", "Feminino", "X", "", None)]
    f["rc_certidao._idade_no_obito"] = lambda: [
        CE()._idade_no_obito(n, q) for n, q in (
            ("1957-10-20", "2026-10-19"), ("2025-10-19", "2026-10-19"),
            ("2026-10-19", "2026-10-19"), ("2027-01-01", "2026-10-19"),
            ("", "2026-10-19"))]
    f["rc_certidao._documento"] = lambda: [
        CE()._documento(d) for d in ({"strCPF": CPF}, {"strCPFNascido": "1"},
                                     {"strDocumento": "RG 1"}, {})]
    f["rc_certidao._e_junta"] = lambda: [
        CE()._e_junta(x) for x in ([], ["A"], ["A", ""], ["A", "B"],
                                   ["A", "B", "C"])]
    f["rc_certidao.teor_sem_titulo"] = lambda: [
        CE().teor_sem_titulo("CERTIDÃO DE NASCIMENTO\n\nNOME:\nX",
                             "CERTIDÃO DE NASCIMENTO"),
        CE().teor_sem_titulo("OUTRA\nNOME:", "CERTIDÃO DE NASCIMENTO"),
        CE().teor_sem_titulo("", "X")]
    f["rc_certidao.hash_certidao"] = lambda: CE().hash_certidao(
        1, 2026, "MARIA DE EXEMPLO", "T", AGORA)

    # montar_teor — nascimento
    f["montar_teor(NASC completo, atos)"] = _mt(
        assento=NASC, pessoas_do_assento=NASC_PESSOAS, atos=ATOS)
    f["montar_teor(NASC, data_fato_extenso, sem lugar, sem data_extenso)"] = _mt(
        assento={**NASC, "ibge_gemeo": 2}, pessoas_do_assento=NASC_PESSOAS[:2],
        lugar=None, data_extenso=None,
        data_fato_extenso="PRIMEIRO DE OUTUBRO DE DOIS MIL E VINTE E SEIS")
    f["montar_teor(NASC acervo: blob)"] = _mt(
        assento={"especie": "nascimento", "nome": "MARIA DE EXEMPLO",
                 "data_fato": "1987-05-28", "data_ato": "1987-06-01",
                 "ibge_gemeo": None, "numero": "77",
                 "dados_json": json.dumps({
                     "strHoraNascimento": "10:00",
                     "strCidade": "CIDADE EXEMPLO/MA.", "strUF": "MA",
                     "strSexo": "Masculino", "strNomeLocal": "DOMICÍLIO",
                     "strLN_endereco": "Rua de Exemplo",
                     "strLN_bairro": "Centro", "bitGemeos": 1,
                     "strDeclaracaoNascidoVivo": "123",
                     "strCPFNascido": CPF_NU})},
        pessoas_do_assento=[_p("MAE", "ANA DE EXEMPLO")], lugar={})
    f["montar_teor(NASC vazio)"] = _mt(
        assento={"especie": "NASCIMENTO"}, pessoas_do_assento=[], sv={},
        lugar=None)
    f["montar_teor(NASC vazio, sem data_extenso)"] = _mt(
        assento={"especie": "NASCIMENTO"}, pessoas_do_assento=[], sv={},
        lugar=None, data_extenso="")
    f["montar_teor(NASC dados dict, RG sem tipo)"] = _mt(
        assento={**NASC, "dados": {"strCPF": CPF}, "ibge_gemeo": ""},
        pessoas_do_assento=[_p("REGISTRADO", "MARIA DE EXEMPLO",
                               documento_numero="1234567")])
    # chaves dentro dos dados e da serventia: o papel é `str.format`, e o que
    # entra nos claros não pode ser lido como claro
    f["montar_teor(chaves nos dados, cancelado, so REGISTRO)"] = _mt(
        assento={**NASC, "nome": "MARIA {DE} EXEMPLO", "situacao": "Cancelado"},
        pessoas_do_assento=NASC_PESSOAS,
        sv={**SV_R, "unit_name": "OFÍCIO {ÚNICO} DE EXEMPLO {0}",
            "ri_cidade": "Cidade {x} Exemplo"},
        atos=[{"tipo": "REGISTRO", "teor": "x"}], data_extenso="{data}")
    f["montar_teor(chaves no teor do ato)"] = _mt(
        assento=NASC, pessoas_do_assento=NASC_PESSOAS,
        atos=[{"tipo": "AVERBACAO", "teor": "Averbo {nome} e {}.",
               "lavrou": "{lavrou}", "selo": "{selo}"},
              {"tipo": "anotacao", "teor": "minúsculo não entra"}])
    # casamento
    f["montar_teor(CASAMENTO, filiacao por conjuge)"] = _mt(
        assento=CAS, pessoas_do_assento=CAS_PESSOAS)
    f["montar_teor(CASAMENTO_RELIGIOSO, filiacao solta)"] = _mt(
        assento={**CAS, "especie": "CASAMENTO_RELIGIOSO",
                 "regime_bens": "SEPARACAO_OBRIGATORIA"},
        pessoas_do_assento=[CAS_PESSOAS[0], _p("PAI", "PEDRO DE EXEMPLO"),
                            _p("MAE", "ANA DE EXEMPLO")])
    f["montar_teor(CASAMENTO acervo blob)"] = _mt(
        assento={"especie": "CASAMENTO", "nome": "JOÃO DE EXEMPLO",
                 "data_fato": "2000-02-02", "data_ato": "2000-02-02",
                 "dados_json": json.dumps({
                     "strNomeConjuge1": "JOÃO DE EXEMPLO",
                     "strNomeConjuge2": "MARIA DE EXEMPLO",
                     "strRegimeCasamento": "COMUNHÃO PARCIAL DE BENS",
                     "strNomePosCasamentoConjuge2": "MARIA DE EXEMPLO SOUZA"})},
        pessoas_do_assento=[])
    f["montar_teor(CASAMENTO so a.nome)"] = _mt(
        assento={"especie": "CASAMENTO", "nome": "JOÃO DE EXEMPLO"},
        pessoas_do_assento=[])
    # óbito / natimorto
    f["montar_teor(OBITO completo, cancelado)"] = _mt(
        assento=OBITO, pessoas_do_assento=OBITO_PESSOAS, atos=ATOS[:2])
    f["montar_teor(OBITO acervo blob)"] = _mt(
        assento={"especie": "OBITO", "nome": "MARIA DE EXEMPLO",
                 "data_fato": "2026-10-19", "data_ato": "2026-10-20",
                 "dados_json": json.dumps({
                     "strHoraObito": "01:00", "strSexo": "M", "intIdade": "99",
                     "strEstadoCivil": "SOLTEIRO", "strProfissao": "LAVRADOR",
                     "strRacaCor": "PARDA",
                     "strMunicipioNaturalidade": "Cidade Exemplo",
                     "strUFNaturalidade": "MA",
                     "strMunicipioFalecido": "Cidade Exemplo",
                     "strUFFalecido": "MA", "strNomeLocalObito": "DOMICÍLIO",
                     "strNumeroDeclaracaoObito": "1", "strCausaMorte": "X",
                     "strNomeMedico": "DR. EXEMPLO",
                     "strDocumentoMedico": "CRM 1",
                     "strLocalSepultamento": "Cemitério",
                     "strTestamento": "NÃO"})},
        pessoas_do_assento=[_p("FALECIDO", "MARIA DE EXEMPLO",
                               data_nascimento="2025-10-19")])
    f["montar_teor(OBITO acervo intIdade)"] = _mt(
        assento={"especie": "OBITO", "nome": "X",
                 "dados": {"intIdade": 70, "strCRM": "CRM 2"}},
        pessoas_do_assento=[])
    f["montar_teor(NATIMORTO)"] = _mt(
        assento={"especie": "NATIMORTO", "nome": "NATIMORTO DE EXEMPLO",
                 "data_fato": "2026-10-01", "data_ato": "2026-10-02"},
        pessoas_do_assento=[_p("REGISTRADO", "NATIMORTO DE EXEMPLO",
                               documento_tipo="CPF", documento_numero=CPF),
                            _p("MAE", "ANA DE EXEMPLO")])
    # sem bloco de espécie
    for esp in ("PROCLAMAS", "OUTRO", "XYZ", ""):
        f[f"montar_teor({esp or 'vazio'}, cancelado)"] = _mt(
            assento={"especie": esp, "nome": "MARIA DE EXEMPLO",
                     "situacao": "CANCELADO"},
            pessoas_do_assento=[], atos=[{"tipo": "AVERBACAO",
                                          "teor": "Averbo X."}])
    f["montar_teor(OUTRO, nada consta, ativo)"] = _mt(
        assento={"especie": "OUTRO", "nome": "MARIA DE EXEMPLO",
                 "situacao": "ATIVO"}, pessoas_do_assento=[], atos=[])

    def _congelado():
        import rc_certidao as CE
        from certidao_texto import sem_linha_de_assinatura_a_mao
        return sem_linha_de_assinatura_a_mao(CE.montar_teor(
            assento=NASC, pessoas_do_assento=NASC_PESSOAS, atos=ATOS, sv=SV_R,
            hoje=HOJE, lugar=LUGAR, data_extenso=EXT))
    f["sem_linha_de_assinatura_a_mao(montar_teor(NASC))"] = _congelado


# ================================================ rc_certidao.emitir

class _BancoDaEmissao:
    """O dublê de `bd_nativo.banco(con)` na emissão: devolve o assento, as
    pessoas, os atos e o lugar, e anota o INSERT da certidão."""

    def __init__(self, assento, pessoas, atos, lugar):
        self.assento, self.pessoas = assento, pessoas
        self.atos, self.lugar = atos, lugar
        self.gravado: list = []

    def um(self, sql, args=()):
        if "a.folha" in sql:
            return dict(self.lugar) if self.lugar else None
        if "FROM rc_assentos" in sql:
            return dict(self.assento) if self.assento else None
        return None

    def ler(self, sql, args=()):
        if "FROM rc_pessoas" in sql:
            return [dict(p) for p in self.pessoas]
        if "FROM rc_atos" in sql:
            return [dict(a) for a in self.atos]
        return []

    def valor(self, sql, args=()):
        return None

    def travar(self, chave):
        return None

    def escrever(self, sql, args=()):
        self.gravado.append(list(args))
        return [{"id": 41}]


def _emitir(assento, pessoas, atos, lugar=None, **kw):
    def chamar():
        import rc_certidao as CE
        bd = _BancoDaEmissao(assento, pessoas, atos, lugar)
        with _pela_pasta(), mock.patch.object(CE, "banco", lambda con: bd):
            r = CE.emitir(object(), 7, sv=SV_R, hoje=HOJE, agora=AGORA, **kw)
        return {"resultado": r, "gravado": bd.gravado}
    return chamar


def _emissao(f: dict) -> None:
    lugar = {"folha": "12", "rotulo": "12V", "numero_ordem": "19555",
             "numero": "A", "complemento": "-24", "livro_volume": "A-9"}
    nasc = {**NASC, "livro_volume": "A-24"}
    f["emitir(NASC, resumo, com atos)"] = _emitir(
        nasc, NASC_PESSOAS, ATOS, lugar, data_extenso=EXT,
        requerente="  JOÃO DE EXEMPLO ", finalidade="")
    f["emitir(NASC, resumo, sem data_extenso)"] = _emitir(
        nasc, NASC_PESSOAS, [], lugar)
    f["emitir(OBITO cancelado, resumo)"] = _emitir(
        {**OBITO, "livro_volume": "C-1", "numero": 3}, OBITO_PESSOAS,
        ATOS[:2], None,
        data_extenso=EXT, modalidade="cnj")
    f["emitir(CASAMENTO, resumo)"] = _emitir(
        {**CAS, "livro_volume": ""}, CAS_PESSOAS, [], lugar, data_extenso=EXT)
    f["emitir(NASC sem filiacao: recusa)"] = _emitir(
        nasc, NASC_PESSOAS[:1], [], lugar)
    f["emitir(NASC, inteiro texto, atos faltando)"] = _emitir(
        nasc, NASC_PESSOAS, ATOS, lugar, modalidade="inteiro_teor",
        teor_colado="  Aos oito dias lavrou-se o assento de MARIA DE EXEMPLO  ")
    f["emitir(OBITO, inteiro texto, sem lugar)"] = _emitir(
        {**OBITO, "livro_volume": "C-1", "matricula": None, "numero": 3},
        OBITO_PESSOAS, [], None, modalidade="texto",
        teor_colado="«Teor do óbito»")
    f["emitir(NASC, inteiro texto, colado vazio: recusa)"] = _emitir(
        nasc, NASC_PESSOAS, [], lugar, modalidade="INTEIRO_TEXTO",
        teor_colado="   ")
    f["emitir(NASC, reprografica)"] = _emitir(
        nasc, NASC_PESSOAS, ATOS, lugar, modalidade="reprográfica",
        imagem_caminho=" /tmp/assento.png ", imagem_largura_cm=15.0)
    f["emitir(CASAMENTO_RELIGIOSO, reprografica, sem serventia)"] = _emitir(
        {**CAS, "especie": "CASAMENTO_RELIGIOSO", "livro_volume": "B-2"},
        CAS_PESSOAS, [], None, modalidade="imagem",
        imagem_caminho="/tmp/assento.jpg")
    f["emitir(NASC, reprografica sem imagem: recusa)"] = _emitir(
        nasc, NASC_PESSOAS, [], lugar, modalidade="repro", imagem_caminho=" ")
    f["emitir(assento ausente: recusa)"] = _emitir(None, [], [], None)


# ============================== rc_certidao_quadro + rc_certidao_odt

SV_Q = {**SV_R, "serventia_endereco": "Rua de Exemplo, 100",
        "serventia_cep": "65000-000",
        "serventia_email": "exemplo@exemplo.invalid",
        "serventia_telefone": "(99) 0000-0000"}


class _BancoDoQuadro:
    """O dublê de `bd_nativo.banco(con)` no quadro: a linha de `rc_assentos`
    e os atos que a consulta dele filtra."""

    def __init__(self, assento, atos):
        self.assento, self.atos = assento, atos

    def um(self, sql, p=None):
        return dict(self.assento) if self.assento is not None else None

    def ler(self, sql, p=None):
        return [dict(a) for a in self.atos
                if a.get("tipo") in ("AVERBACAO", "ANOTACAO", "RETIFICACAO")]


def _quadro(assento, pessoas, atos=(), certidao=None, sv=SV_Q):
    import rc_certidao as RCE
    import rc_certidao_quadro as RCQ
    certidao = {"assento_id": 1, "emitida_em": AGORA, **(certidao or {})}
    with _pela_pasta(), \
            mock.patch.object(RCQ, "banco",
                              lambda con: _BancoDoQuadro(assento, list(atos))), \
            mock.patch.object(RCE, "pessoas", lambda con, aid: list(pessoas)):
        return RCQ.quadro_da_certidao(None, certidao, sv)


NASC_P = [_p("REGISTRADO", "MARIA DE EXEMPLO", sexo="F", documento_tipo="CPF",
             documento_numero=CPF_NU, naturalidade_cidade="Cidade Exemplo",
             naturalidade_uf="MA"),
          _p("MAE", "ANA DE EXEMPLO", naturalidade_cidade="Cidade Exemplo",
             naturalidade_uf="MA"),
          _p("PAI", "JOÃO DE EXEMPLO"),
          _p("AVO_MATERNO", "PAULO DE EXEMPLO"),
          _p("AVO_MATERNA", "LUZIA DE EXEMPLO"),
          _p("AVO_PATERNO", "PEDRO DE EXEMPLO")]
NASC_Q = {"especie": "NASCIMENTO", "nome": "maria de exemplo", "matricula": MAT,
          "data_fato": "2026-10-01", "data_ato": "2026-10-03",
          "hora_fato": "08:15", "local_fato_nome": "HOSPITAL DE EXEMPLO",
          "local_fato_endereco": "Cidade Exemplo", "ibge_gemeo": 2,
          "dnv": "00000000000",
          "dados_json": json.dumps({"strNomeGemeo": "JOÃO DE EXEMPLO"}),
          "situacao": "CANCELADO"}
ATOS_Q = [{"tipo": "REGISTRO", "teor": "x"},
          {"tipo": "AVERBACAO", "teor": " Averbo o CPF. "},
          {"tipo": "ANOTACAO", "teor": None}]
CAS_P = [_p("NUBENTE1", "JOÃO DE EXEMPLO", documento_tipo="",
            documento_numero=CPF_NU, data_nascimento="1990-01-01",
            naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA",
            estado_civil="solteiro"),
         _p("NUBENTE2", "MARIA DE EXEMPLO", nome_pos="MARIA DE EXEMPLO SOUZA",
            nacionalidade="Portuguesa", documento_tipo="RG",
            documento_numero="123"),
         _p("MAE", "ANA DE EXEMPLO"), _p("PAI", "PEDRO DE EXEMPLO")]
CAS_Q = {"especie": "CASAMENTO_RELIGIOSO", "nome": "JOÃO DE EXEMPLO",
         "data_fato": "2026-09-21", "data_ato": "2026-09-22",
         "regime_bens": "COMUNHAO_PARCIAL", "matricula": ""}
OBI_P = [_p("FALECIDO", "MARIA DE EXEMPLO", sexo="F",
            data_nascimento="1957-10-20", estado_civil="viúva",
            nome_pos="JOÃO DE EXEMPLO", naturalidade_cidade="Cidade Exemplo",
            naturalidade_uf="MA"),
         _p("MAE", "ANA DE EXEMPLO"), _p("PAI", "JOÃO DE EXEMPLO"),
         _p("DECLARANTE", "PEDRO DE EXEMPLO")]
OBI_Q = {"especie": "OBITO", "nome": "Maria de Exemplo",
         "data_fato": "2026-10-19", "data_ato": "2026-10-19",
         "hora_fato": "23 horas", "local_fato_nome": "HOSPITAL DE EXEMPLO",
         "causa_morte": "causa de exemplo", "atestante": "DR. EXEMPLO",
         "atestante_documento": "CRM/MA 0000",
         "local_sepultamento": "Cemitério de Exemplo",
         "situacao": "cancelado",
         "dados_json": json.dumps({
             "strMunicipioObito": "Cidade Exemplo", "strUFObito": "MA",
             "strMunicipioSepultamento": "Cidade Exemplo",
             "strUFSepultamento": "MA", "strBens": "Não",
             "strFilhos": "Sim, dois"})}
SELOS = [{"numero": "CERTID000000AAAAAAAAAAAAAA", "texto": ""},
         {"numero": "CERTID000000BBBBBBBBBBBBBB", "texto": ""}]


def _xml_da_certidao(q, cert, sv):
    import rc_certidao_odt as ODT
    with zipfile.ZipFile(io.BytesIO(ODT.arquivo_da_certidao(q(), cert, sv))) as z:
        return z.read("content.xml").decode("utf-8")


def _quadro_e_molde(f: dict) -> None:
    def RCQ():
        import rc_certidao_quadro
        return rc_certidao_quadro

    def RCE():
        import rc_certidao
        return rc_certidao

    def ODT():
        import rc_certidao_odt
        return rc_certidao_odt

    f["quadro.formatar_cpf"] = lambda: [
        RCQ().formatar_cpf(x) for x in (CPF_NU, CPF, "123", "", None)]
    f["quadro.formatar_matricula"] = lambda: [
        RCQ().formatar_matricula(x) for x in (MAT, "123", None)]
    f["quadro.partes_data"] = lambda: [
        RCQ().partes_data(x) for x in ("2026-10-19", "19102026", "19/10/2026",
                                       "", None)]
    f["quadro._hora"] = lambda: [
        RCQ()._hora(x) for x in ("08:15", "8 horas", "", None)]
    f["quadro._cidade_uf"] = lambda: [
        RCQ()._cidade_uf(x) for x in ("Cidade Exemplo/MA", "A/B/MA",
                                      "Cidade Exemplo", "")]
    f["quadro._genitores_nascimento(mae+pai)"] = lambda: (
        RCQ()._genitores_nascimento(RCE()._por_papel(NASC_P), {}))
    f["quadro._genitores_nascimento(vazio)"] = lambda: (
        RCQ()._genitores_nascimento({}, {}))
    f["quadro._quadro_casamento(pessoas)"] = lambda: RCQ()._quadro_casamento(
        CAS_Q, RCE()._por_papel(CAS_P), {}, "", {})
    f["quadro._quadro_casamento(blob)"] = lambda: RCQ()._quadro_casamento(
        {"nome": "JOÃO DE EXEMPLO"}, {}, {
            "strNomeConjuge2": "MARIA DE EXEMPLO",
            "strNomePosCasamentoConjuge2": "MARIA DE EXEMPLO SOUZA",
            "strRegimeCasamento": "SEPARACAO_TOTAL"}, "", {})
    f["quadro._quadro_casamento(vazio)"] = lambda: RCQ()._quadro_casamento(
        {}, {}, {}, "", {})
    f["quadro._quadro_obito(pessoas)"] = lambda: RCQ()._quadro_obito(
        OBI_Q, RCE()._por_papel(OBI_P), json.loads(OBI_Q["dados_json"]), "", {})
    f["quadro._quadro_obito(blob)"] = lambda: RCQ()._quadro_obito(
        {}, {}, {"strNomeConjuge": "JOÃO DE EXEMPLO", "intIdade": 70,
                 "strCRM": "CRM 1", "strHoraObito": "01:00"}, "", {})

    f["quadro(NASC cancelado, atos)"] = lambda: _quadro(NASC_Q, NASC_P, ATOS_Q)
    f["quadro(NASC cancelado, sem atos)"] = lambda: _quadro(NASC_Q, NASC_P)
    f["quadro(NASC ativo)"] = lambda: _quadro(
        {**NASC_Q, "situacao": "ATIVO"}, NASC_P, ATOS_Q)
    f["quadro(NASC acervo, cpf legado, sem gemeo)"] = lambda: _quadro(
        {"especie": "NASCIMENTO", "nome": "X", "ibge_gemeo": None,
         "dados_json": json.dumps({
             "strCPF": CPF, "bitGemeos": "NAO",
             "strCidade": "CIDADE EXEMPLO/MA.", "strNomeLocal": "DOMICÍLIO",
             "strMunicipioNascimento": "Cidade Exemplo"})}, [])
    f["quadro(NASC cpf da certidao)"] = lambda: _quadro(
        {"especie": "NASCIMENTO", "nome": "X"}, [],
        certidao={"cpf": CPF_NU, "emitida_funcao": "Escrevente"})
    f["quadro(CASAMENTO_RELIGIOSO)"] = lambda: _quadro(CAS_Q, CAS_P)
    f["quadro(OBITO cancelado)"] = lambda: _quadro(
        OBI_Q, OBI_P, [{"tipo": "RETIFICACAO", "teor": "Retifico."}])
    f["quadro(sem assento, NATIMORTO)"] = lambda: _quadro(
        None, [], certidao={"especie": "NATIMORTO"})

    f["odt.valores({},{},{})"] = lambda: ODT().valores({}, {}, {})
    f["odt.valores(quadro NASC, 2 selos)"] = lambda: ODT().valores(
        _quadro(NASC_Q, NASC_P, ATOS_Q),
        {"emitida_por": "ESCREVENTE DE EXEMPLO",
         "emitida_funcao": "Escrevente Autorizada", "selos": SELOS}, SV_Q)
    f["odt.valores(so filiacao texto, 1 selo antigo)"] = lambda: ODT().valores(
        {"especie": "NASCIMENTO",
         "filiacao": "ANA DE EXEMPLO e JOÃO DE EXEMPLO", "gemeo": "SIM"},
        {"selo": "CERTID000000AAAAAAAAAAAAAA", "selo_texto": ""}, {})
    f["odt.valores(filiacao uma so)"] = lambda: ODT().valores(
        {"filiacao": "ANA DE EXEMPLO"}, {}, {})
    f["odt.valores(quadro CAS)"] = lambda: ODT().valores(
        _quadro(CAS_Q, CAS_P), {}, SV_Q)
    f["odt.valores(quadro OBITO, sv vazio)"] = lambda: ODT().valores(
        _quadro(OBI_Q, OBI_P), {}, {})
    for nome, q, cert in (
            ("NASC", lambda: _quadro(NASC_Q, NASC_P, ATOS_Q),
             {"selos": SELOS[:1]}),
            ("CAS", lambda: _quadro(CAS_Q, CAS_P), {}),
            ("OBITO", lambda: _quadro(OBI_Q, OBI_P), {"selos": SELOS})):
        f[f"odt.arquivo_da_certidao({nome}).content.xml"] = (
            lambda q=q, c=cert: _xml_da_certidao(q, c, SV_Q))
    f["odt.arquivo_da_certidao(NATIMORTO): recusa"] = lambda: (
        ODT().arquivo_da_certidao({"especie": "NATIMORTO"}, {}, SV_Q))
    f["odt.html_odt_da_certidao"] = lambda: ODT().html_odt_da_certidao(
        {}, {}, {})


# ============================================ rc_certidao_inteiro_teor

ESP = ("NASCIMENTO", "CASAMENTO", "CASAMENTO_RELIGIOSO", "OBITO", "NATIMORTO",
       "PROCLAMAS", "AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO",
       "UNIAO_ESTAVEL", "OPCAO_NACIONALIDADE", "OUTRO", "", None, " obito ")
CHEIO = dict(nome="MARIA DE EXEMPLO",
             matricula="000000 01 55 2026 1 00001 001 0000001 00",
             livro="A-1", folha="1", termo="1", cns="000000",
             cidade="Cidade Exemplo", uf="MA")
PARC = {
    "cheio": CHEIO,
    "cidade_folha": dict(nome="  MARIA   DE EXEMPLO ", folha="12",
                         cidade="Cidade Exemplo"),
    "uf_livro_termo": dict(nome="MARIA DE EXEMPLO", livro="A-1", termo="7",
                           uf="MA", cns="000000"),
    "vazio": dict(nome=None),
    "chaves": dict(nome="MARIA {nome} EXEMPLO", livro="{livro}", folha="{}",
                   termo="{0}", cns="{cns}", cidade="Cidade {x}",
                   uf="{uf}", matricula="{matricula}"),
}
MODOS = ("INTEIRO_TEXTO", "INTEIRO_REPRO", "RESUMO", "imagem")
SV_IT = {"unit_name": "OFÍCIO ÚNICO DE CIDADE EXEMPLO & <ANEXO>",
         "serventia_titular": "MARIA DE EXEMPLO", "serventia_titulo": "Oficial",
         "serventia_cnpj": "00.000.042/0001-22", "ri_cns": "000000",
         "serventia_telefone": "(00) 0000-0000",
         "endereco_completo": "Rua de Exemplo, 1 — Centro",
         "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
ASPAS = ("Aos oito dias lavrou-se o assento de MARIA DE EXEMPLO", "termina.",
         "termina!", "termina?", "termina…", "«entre angulares»",
         '"entre aspas"', "'simples'", "«»", "  \n  ", "", None)
ATOS_IT = {
    "sem_atos": ("Teor colado de exemplo.", None),
    "lista_vazia": ("Teor colado de exemplo.", []),
    "tres_faltando": ("Teor colado de exemplo.", [
        {"tipo": "AVERBACAO", "teor": "Averbo o CPF 000.000.001-91 de MARIA "
                                      "DE EXEMPLO neste assento."},
        {"tipo": "ANOTACAO", "teor": "Anoto o casamento de MARIA DE EXEMPLO "
                                     "com JOÃO DE EXEMPLO."},
        {"tipo": "RETIFICACAO", "teor": "Retifico o nome da mãe para ANA DE "
                                        "EXEMPLO, por erro material."}]),
    "registro_e_vazio_ignorados": ("Teor.", [
        {"tipo": "REGISTRO", "teor": "o registro"},
        {"tipo": "AVERBACAO", "teor": "   "},
        {"tipo": "AVERBACAO", "teor": None}]),
    "ja_tem_pelo_selo": ("Teor com o selo AVERBA000000XXXXXXXXXXXXXX dentro.", [
        {"tipo": "AVERBACAO", "teor": "Outro texto qualquer.",
         "selo": "averba000000xxxxxxxxxxxxxx"}]),
    "ja_tem_pelo_nucleo": (
        "Teor. Averbo o CPF de MARIA DE EXEMPLO neste assento. Fim.", [
            {"tipo": "AVERBACAO",
             "teor": "Averbo o CPF de MARIA DE EXEMPLO neste assento. "
                     "Lavrado por: JOÃO DE EXEMPLO. Selo: X."}]),
    "colado_vazio": ("", [{"tipo": "ANOTACAO", "teor": "Anoto algo."},
                          {"tipo": "AVERBACAO", "teor": "Averbo outra."}]),
    "colado_none": (None, [{"tipo": "AVERBACAO", "teor": "Averbo X."}]),
    "tipo_minusculo": ("Teor.", [{"tipo": "averbacao", "teor": "Averbo Y."}]),
}


def _inteiro_teor(f: dict) -> None:
    def IT():
        import rc_certidao_inteiro_teor
        return rc_certidao_inteiro_teor

    def SEM_TRACO(texto):
        from certidao_texto import sem_linha_de_assinatura_a_mao
        return sem_linha_de_assinatura_a_mao(texto)

    f["IT.TITULOS"] = lambda: dict(IT().TITULOS)
    f["IT.NOME_DA_ESPECIE"] = lambda: dict(IT().NOME_DA_ESPECIE)
    f["IT.SEPARADOR_ATOS_INTEIRO"] = lambda: IT().SEPARADOR_ATOS_INTEIRO
    for e in ESP:
        f[f"IT.titulo({e!r})"] = lambda e=e: IT().titulo(e)
        f[f"IT._especie_por_extenso({e!r})"] = (
            lambda e=e: IT()._especie_por_extenso(e))
        for pn, kw in PARC.items():
            for modo in MODOS:
                f[f"IT.introducao({e!r},{pn},{modo})"] = (
                    lambda e=e, kw=kw, m=modo: IT().introducao(
                        especie=e, modo=m, **kw))
    f["IT.introducao(sem modo)"] = lambda: IT().introducao(
        especie="NASCIMENTO", **CHEIO)
    for i, t in enumerate(ASPAS):
        f[f"IT.entre_aspas[{i}]({t!r})"] = lambda t=t: IT().entre_aspas(t)
    f["IT._ponto_no_teor_aspas"] = lambda: [
        IT()._ponto_no_teor_aspas(x) for x in (
            "INTRO\n«teor sem ponto»", "«a.» e «b»", "«  »", "sem aspas",
            "«x\ny»", "", None)]
    for nome, (colado, atos) in ATOS_IT.items():
        f[f"IT.completar_teor_colado_com_atos({nome})"] = (
            lambda c=colado, a=atos: IT().completar_teor_colado_com_atos(c, a))

    # A SEQUÊNCIA DA EMISSÃO (`rc_certidao.emitir`), sem o banco: é isto que
    # congela em `rc_certidoes.teor`, e o hash é deste texto.
    def cong_texto(e, colado, atos):
        def chamar():
            it = IT()
            intro = it.introducao(especie=e, modo=it.INTEIRO_TEXTO, **CHEIO)
            limpo = it.completar_teor_colado_com_atos(
                (colado or "").strip() or None, atos) or None
            return SEM_TRACO(it.montar_teor_texto(introducao_txt=intro,
                                                  teor_colado=limpo))
        return chamar

    for e in ("NASCIMENTO", "OBITO", "INTERDICAO"):
        for nome, (colado, atos) in ATOS_IT.items():
            f[f"congelado_texto({e},{nome})"] = cong_texto(e, colado, atos)
        for pn, kw in PARC.items():
            f[f"congelado_repro({e},{pn})"] = (
                lambda e=e, kw=kw: SEM_TRACO(IT().montar_teor_repro(
                    introducao_txt=IT().introducao(
                        especie=e, modo="INTEIRO_REPRO", **kw))))
    f["IT.montar_teor_texto(com atos)"] = lambda: IT().montar_teor_texto(
        introducao_txt="INTRO  \n", teor_colado="Teor colado.",
        atos=ATOS_IT["tres_faltando"][1])

    for nome, sv in (("SV", SV_IT), ("vazio", {}), ("None", None)):
        f[f"IT._cabecalho_notas_html({nome})"] = (
            lambda sv=sv: IT()._cabecalho_notas_html(sv, {}))
    emitentes = {
        "emitente_e_funcao": {"emitida_por": "JOÃO DE EXEMPLO",
                              "emitida_funcao": "Escrevente Autorizado"},
        "so_titulo": {"emitida_por": " JOÃO  DE EXEMPLO ",
                      "emitida_titulo": "Substituto"},
        "ninguem": {},
        "escapar": {"emitida_por": "JOÃO <DE> & EXEMPLO",
                    "emitida_funcao": "Escrevente & Cia"},
    }
    for en, cert in emitentes.items():
        for sn, sv in (("SV", SV_IT), ("vazio", {})):
            f[f"IT._rodape_html({en},{sn})"] = (
                lambda c=cert, sv=sv: IT()._rodape_html(
                    c, sv, "dezenove de outubro de 2026"))
    for x in ("", "<p>a</p><p>b</p>", "sem p", "<p></p>", None):
        f[f"IT._com_fecho_certificar({x!r})"] = (
            lambda x=x: IT()._com_fecho_certificar(x))
    f["IT._paragrafos_html"] = lambda: [
        IT()._paragrafos_html(x) for x in (
            "CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO\n\nCERTIFICO…\n«teor\n\n"
            "colado»", "CERTIDAO DE INTEIRO TEOR\ncorpo & <b>", "outro\n\n\nx",
            "", None, "CERTIDÃO DE INTEIRO TEOR\n\n")]

    teor_txt = ("CERTIDÃO DE INTEIRO TEOR DE NASCIMENTO\n\nCERTIFICO E DOU FÉ "
                "que…, COM O SEGUINTE TEOR:\n«Teor colado de exemplo»")
    teor_rep = ("CERTIDÃO DE INTEIRO TEOR DE ÓBITO\n\nCERTIFICO E DOU FÉ "
                "que…, na imagem abaixo.\n\n[Cópia reprográfica do assento "
                "anexa a esta certidão.]")
    canceladas = {"ativa": {}, "motivo_none": {"cancelada_em": AGORA},
                  "motivo_vazio": {"cancelada_em": AGORA,
                                   "cancelada_motivo": ""},
                  "motivo": {"cancelada_em": AGORA,
                             "cancelada_motivo": "motivo de exemplo"},
                  "motivo_escapar": {"cancelada_em": AGORA,
                                     "cancelada_motivo":
                                         "erro <de> & digitação {motivo}"}}
    for cn, extra in canceladas.items():
        cert = {"teor": teor_txt, "emitida_por": "JOÃO DE EXEMPLO", **extra}
        f[f"IT.html_da_certidao_texto({cn})"] = (
            lambda c=cert: IT().html_da_certidao_texto(
                c, SV_IT, hoje_extenso="19 de outubro de 2026"))
        for tn, teor in (("com_linha", teor_rep),
                         ("sem_linha", teor_rep.split("\n\n[")[0])):
            certr = {"teor": teor, **extra}
            f[f"IT.html_da_certidao_repro({cn},{tn})"] = (
                lambda c=certr: IT().html_da_certidao_repro(
                    c, SV_IT, hoje_extenso="19 de outubro de 2026",
                    marca_imagem="##IMG##"))

    def odt(cert, imagem=None):
        def chamar():
            dados = IT().arquivo_odt(cert, SV_IT,
                                     hoje_extenso="19 de outubro de 2026",
                                     imagem_bytes=imagem)
            with zipfile.ZipFile(io.BytesIO(dados)) as z:
                return _sem_os_estilos(z.read("content.xml").decode("utf-8"))
        return chamar

    base = {"numero": 3, "ano": 2026, "emitida_por": "JOÃO DE EXEMPLO",
            "emitida_funcao": "Escrevente"}
    f["IT.arquivo_odt(texto).content.xml"] = odt(
        {**base, "modalidade": "INTEIRO_TEXTO", "teor": teor_txt})
    f["IT.arquivo_odt(texto cancelada, selo).content.xml"] = odt(
        {**base, "modalidade": "INTEIRO_TEXTO", "teor": teor_txt,
         "cancelada_em": AGORA, "cancelada_motivo": "erro <de> & digitação",
         "selo": "CERTID000000AAAAAAAAAAAAAA"})
    f["IT.arquivo_odt(repro).content.xml"] = odt(
        {**base, "modalidade": "INTEIRO_REPRO", "teor": teor_rep,
         "imagem_caminho": "/tmp/assento.png", "imagem_largura_cm": 15,
         "imagem_altura_cm": "", "imagem_margem_esq_cm": 0,
         "imagem_margem_sup_cm": None}, PNG)
    f["IT.arquivo_odt(repro sem imagem): recusa"] = odt(
        {**base, "modalidade": "INTEIRO_REPRO", "teor": teor_rep})

    for modo in ("RESUMO", "INTEIRO_TEXTO", "INTEIRO_REPRO"):
        for colado in ("Teor de exemplo", ""):
            f[f"IT.previa_html({modo},{colado!r})"] = (
                lambda m=modo, c=colado: IT().previa_html(
                    modalidade=m,
                    introducao_txt=IT().introducao(especie="NASCIMENTO",
                                                   modo=m, **CHEIO),
                    teor_colado=c, tem_imagem=bool(c),
                    atos=ATOS_IT["tres_faltando"][1]))


# ============================== os que ficam no código: cabeçalho e folha

SV_CAB = {"unit_name": "OFÍCIO ÚNICO DE EXEMPLO",
          "serventia_titular": "MARIA DE EXEMPLO",
          "serventia_titulo": "Oficial Registradora",
          "serventia_endereco": "Rua de Exemplo, 100",
          "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
          "serventia_cep": "65000-000",
          "serventia_telefone": "(99) 0000-0000",
          "serventia_email": "exemplo@exemplo.invalid"}


def _cabecalho_e_folha(f: dict) -> None:
    def CAB():
        import rc_cabecalho
        return rc_cabecalho

    def FOLHA():
        import rc_folha
        return rc_folha

    f["rc_cabecalho.PAIS"] = lambda: CAB().PAIS
    f["rc_cabecalho.TITULO_DO_ATO"] = lambda: dict(CAB().TITULO_DO_ATO)
    f["rc_cabecalho.LINHAS"] = lambda: list(CAB().LINHAS)
    for e in ("NASCIMENTO", "CASAMENTO_RELIGIOSO", "OBITO", "INTERDICAO",
              "outro", None, "XYZ"):
        f[f"rc_cabecalho.montar({e!r})"] = (
            lambda e=e: CAB().montar(SV_CAB, especie=e, termo=19555,
                                     livro=" A-24 ", folha="12"))
    f["rc_cabecalho.montar(sv parcial)"] = lambda: CAB().montar(
        {"unit_name": "OFÍCIO ÚNICO DE EXEMPLO", "ri_cidade": "Cidade Exemplo",
         "serventia_email": "exemplo@exemplo.invalid"}, especie="OBITO")
    f["rc_cabecalho.montar(sv None)"] = lambda: CAB().montar(None)
    f["rc_cabecalho.o_que_falta"] = lambda: [
        CAB().o_que_falta(CAB().montar(sv, especie=e)) for sv, e in (
            (SV_CAB, "NASCIMENTO"), ({}, None))]
    f["rc_folha.COLUNAS"] = lambda: [
        {k: c[k] for k in ("chave", "titulo", "largura")}
        for c in FOLHA().COLUNAS]
    f["rc_folha.ASSINAM_ALEM_DE_QUEM_LAVROU"] = lambda: {
        k: [list(x) for x in v]
        for k, v in FOLHA().ASSINAM_ALEM_DE_QUEM_LAVROU.items()}


def chamadas() -> dict:
    f: dict = {}
    _rc_certidao(f)
    _emissao(f)
    _quadro_e_molde(f)
    _inteiro_teor(f)
    _cabecalho_e_folha(f)
    return f
