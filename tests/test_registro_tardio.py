"""O registro de nascimento tardio, do requerimento ao termo — 21/10/2026.

    «precisamos fazer um registro tardio, o cartorio gestao comporta?» e
    «preciso fazer hoje, verificar o que tem e faz o que nao tem pra conseguir
     fazer tudo»; «tem que gerar modelo de requerimento para fornecer para os
     comparecentes assinarem (de preferencia preenchido) e possivel para
     importar por documentos digitalizados como o normal» — o oficial

O QUE ESTES TESTES GUARDAM
    **A marca e o número do requerimento entram pelo formulário**, a segunda
    testemunha também, e nada disso é exigido pela tela.
    **A lavratura recusa o tardio sem as duas testemunhas** (art. 249, II) — e
    as dispensa só quando o registrando tem menos de 12 anos E DNV.
    **O termo diz que é tardio**, com o requerimento e as testemunhas; o
    registro dentro do prazo sai como era.
    **A conferência traz o requerimento preenchido para imprimir.**
    **A leitura de documentos monta o nascimento do requerimento, sem DNV.**

Nomes fictícios, como em todo teste desta casa.

Veio do sandbox (versão das 14h25 de 21/10, a mais nova — `pendentes_sandbox`):
os testes de lá estão aqui sem asserção mudada; o SQL de conferir o banco é o
do PostgreSQL. No fim, os da junção com a branch (LH05): no NASCIMENTO a
segunda gaveta grava `TESTEMUNHA2` também fora do tardio (o LD01 a gravava
como outra `TESTEMUNHA`), e o termo do tardio não escreve a mesma testemunha
duas vezes.
"""
from __future__ import annotations

import re
import sys
from datetime import date
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import rc_assento as RC                                          # noqa: E402
import rc_leitura_documentos as LEIT                             # noqa: E402
import rc_modelos_do_livro as ML                                 # noqa: E402
from bd_nativo import banco                                      # noqa: E402
from test_testemunha_fantasma_20261009 import (                  # noqa: E402,F401
    FOLHAS, _como_o_navegador, _con, _rascunho_nascimento, casa)

ADULTO = {"nome": "JOAO EXEMPLO", "data_fato": "1990-05-03",
          "local_fato_nome": "Domicílio", "sexo": "M", "registro_tardio": "1"}
PESSOAS = [{"papel": "REGISTRADO", "nome": "JOAO EXEMPLO",
            "data_nascimento": "1990-05-03"},
           {"papel": "MAE", "nome": "MARIA EXEMPLO"},
           {"papel": "PAI", "nome": "IGNORADO"},
           {"papel": "DECLARANTE", "nome": "JOAO EXEMPLO"}]
DUAS = [{"papel": "TESTEMUNHA", "nome": "BEATRIZ EXEMPLO"},
        {"papel": "TESTEMUNHA2", "nome": "CARLA EXEMPLO"}]


# ------------------------------------------------------------- a regra

def test_tardio_de_adulto_sem_as_duas_testemunhas_e_recusado():
    with pytest.raises(RC.RcError) as erro:
        RC.conferir_requisitos_legais("NASCIMENTO", ADULTO, PESSOAS + DUAS[:1])
    assert "art. 249" in str(erro.value)
    assert "segunda testemunha" in str(erro.value)
    RC.conferir_requisitos_legais("NASCIMENTO", ADULTO, PESSOAS + DUAS)


def test_menor_de_12_com_dnv_dispensa_as_testemunhas_e_sem_dnv_nao():
    hoje = date.today()
    crianca = dict(ADULTO, data_fato=f"{hoje.year - 5}-01-01")
    pessoas = [dict(PESSOAS[0], data_nascimento=crianca["data_fato"])] + PESSOAS[1:]
    with pytest.raises(RC.RcError, match="testemunha"):
        RC.conferir_requisitos_legais("NASCIMENTO", crianca, pessoas)
    RC.conferir_requisitos_legais(
        "NASCIMENTO", dict(crianca, dnv="30-00000000-1"), pessoas)


def test_registro_no_prazo_nao_pede_a_segunda_testemunha():
    RC.conferir_requisitos_legais(
        "NASCIMENTO", dict(ADULTO, registro_tardio=""), PESSOAS)


def test_a_segunda_testemunha_tem_rotulo_prefixo_e_ordem():
    assert "TESTEMUNHA2" in RC.PAPEIS_DA_ESPECIE["NASCIMENTO"]
    assert RC.PREFIXO_DO_PAPEL["TESTEMUNHA2"] == "testemunha2"
    assert RC.ROTULO_DO_PAPEL["TESTEMUNHA2"]
    assert RC.ORDEM_DO_PAPEL["TESTEMUNHA2"] > RC.ORDEM_DO_PAPEL["TESTEMUNHA"]


# --------------------------------------------------------------- o termo

def test_o_termo_do_tardio_diz_o_requerimento_e_as_testemunhas():
    a = dict(ADULTO, especie="NASCIMENTO", tardio_requerimento="1/2026",
             data_ato="2026-10-21")
    frase = ML.frase_do_tardio(a, PESSOAS + DUAS)
    assert "fora do prazo legal" in frase and "art. 46 da Lei" in frase
    assert "requerimento nº 1/2026" in frase
    assert "BEATRIZ EXEMPLO" in frase and "CARLA EXEMPLO" in frase
    assert "dispensada" not in frase


def test_a_dispensa_sai_so_quando_vale():
    a = {"especie": "NASCIMENTO", "registro_tardio": "1",
         "data_fato": "2020-01-01", "data_ato": "2026-10-21",
         "dnv": "30-00000000-1"}
    pessoas = [{"papel": "REGISTRADO", "nome": "X", "data_nascimento": "2020-01-01"}]
    assert "dispensada a presença de testemunhas" in ML.frase_do_tardio(a, pessoas)
    assert "dispensada" not in ML.frase_do_tardio(dict(a, dnv=""), pessoas)


def test_no_prazo_o_termo_sai_como_era():
    assert ML.frase_do_tardio({"registro_tardio": None}, PESSOAS) == ""
    assert "{frase_tardio}" in ML.TERMO_NASCIMENTO
    assert ML.conferir("NASCIMENTO") == []


# ----------------------------------------------------- a leitura sem DNV

def test_a_leitura_monta_o_nascimento_do_requerimento_sem_dnv():
    req = {"tipo": "TARDIO", "arquivo": "requerimento.pdf", "n": 1, "dados": {
        "numero_requerimento": "3/2026",
        "requerente": {"nome": "JOAO EXEMPLO", "cpf": "000.000.001-91"},
        "registrando": {"nome": "JOAO EXEMPLO", "sexo": "Masculino",
                        "data_nascimento": "03/05/1990",
                        "municipio_nascimento": "Cidade Exemplo",
                        "uf_nascimento": "MA"},
        "mae": {"nome": "MARIA EXEMPLO"},
        "avos_maternos": ["AVO EXEMPLO", "AVA EXEMPLO"],
        "testemunhas": [{"nome": "BEATRIZ EXEMPLO", "cpf": "000.000.002-72"},
                        {"nome": "CARLA EXEMPLO"}]}}
    junto = LEIT.juntar_nascimento([req])
    v = junto["valores"]
    assert v["registro_tardio"] == "1" and v["tardio_requerimento"] == "3/2026"
    assert v["data_fato"] == "1990-05-03" and not v["dnv"]
    papeis = {p["papel"]: p["nome"] for p in junto["pessoas"]}
    assert papeis["TESTEMUNHA"] == "Beatriz Exemplo"
    assert papeis["TESTEMUNHA2"] == "Carla Exemplo"
    assert papeis["AVO_MATERNA"] == "Ava Exemplo"
    assert papeis["DECLARANTE"] == "Joao Exemplo"


def test_sem_dnv_e_sem_requerimento_a_recusa_aponta_o_requerimento():
    with pytest.raises(LEIT.LeituraError, match="requerimento"):
        LEIT.juntar_nascimento([])


# --------------------------------------------------------------- a tela

def test_a_tela_pergunta_o_tardio_sem_exigir(casa):
    html = casa["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert 'name="registro_tardio"' in html
    assert re.search(r'name="tardio_requerimento"\s+value="1/\d{4}"', html)
    assert 'name="testemunha2_nome"' in html
    for campo in ("registro_tardio", "tardio_requerimento", "testemunha2_nome"):
        assert not re.search(rf'name="{campo}"[^>]*required', html), campo


def _tardio_pela_tela(casa, **trocar):
    dados = _rascunho_nascimento()
    dados.update(dnv="", data_fato="1990-05-03",
                 pessoa_data_nascimento="1990-05-03",
                 filiacao1_data_nascimento="1960-01-10",
                 filiacao2_data_nascimento="1958-02-11",
                 declarante_data_nascimento="1958-02-11",
                 registro_tardio="1", tardio_requerimento="7/2026",
                 testemunha_nome="BEATRIZ EXEMPLO",
                 testemunha2_nome="CARLA EXEMPLO", testemunha2_sexo="F",
                 testemunha2_profissao="lavradora")
    dados.update(trocar)          # o que o teste troca vence o de cima
    c = casa["c"]
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    envio = _como_o_navegador(html, ("acao", "conferir"),
                              **{k: v for k, v in dados.items() if k != "especie"})
    conf = c.post("/rcpn/novo/nascimento", data=envio,
                  follow_redirects=True).get_data(as_text=True)
    return c, conf


def test_a_conferencia_traz_o_requerimento_preenchido(casa):
    _, conf = _tardio_pela_tela(casa)
    assert "REQUERIMENTO DE REGISTRO DE NASCIMENTO TARDIO" in conf
    assert "Imprimir requerimento do registro tardio" in conf
    assert "<strong>7/2026</strong>" in conf
    assert "CARLA EXEMPLO" in conf and "BEATRIZ EXEMPLO" in conf
    assert "Dispensada a presença" not in conf     # adulto sem DNV: colhem-se
    assert "(X) pai" in conf                       # o declarante é o pai


def test_o_tardio_lavrado_pela_tela_leva_a_marca_as_testemunhas_e_a_frase(casa):
    c, conf = _tardio_pela_tela(casa)
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[0])
    r = c.post("/rcpn/novo/nascimento", data=envio2, follow_redirects=True)
    con = _con(casa)
    bd = banco(con)
    a = bd.um("SELECT * FROM rc_assentos ORDER BY id DESC LIMIT 1")
    papeis = {p["papel"]: p["nome"] for p in bd.ler(
        "SELECT papel, nome FROM rc_pessoas WHERE assento_id = %s ORDER BY id",
        (a["id"],))}
    con.close()
    assert a and int(a["registro_tardio"] or 0) == 1, \
        re.sub(r"\s+", " ", r.get_data(as_text=True))[:800]
    assert a["tardio_requerimento"] == "7/2026"
    assert papeis.get("TESTEMUNHA2") == "CARLA EXEMPLO"
    teor = a["teor"] or ""
    assert "Registro lavrado fora do prazo legal" in teor
    assert "requerimento nº 7/2026" in teor and "CARLA EXEMPLO" in teor


def test_a_tela_de_corrigir_mostra_o_tardio(casa):
    c, conf = _tardio_pela_tela(casa)
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[0])
    c.post("/rcpn/novo/nascimento", data=envio2, follow_redirects=True)
    con = _con(casa)
    aid = banco(con).valor("SELECT max(id) AS id FROM rc_assentos")
    con.close()
    html = c.get(f"/rcpn/{aid}/editar").get_data(as_text=True)
    assert 'name="registro_tardio"' in html and 'value="7/2026"' in html
    assert 'name="testemunha2_nome"' in html and 'value="CARLA EXEMPLO"' in html


# ------------------------------------- a segunda passada — 21/10/2026, tarde
#
# «uma solucao que tinha sido resolvida, segue rejeitando se nao acha dnv
#  [...] e nao tem opcao de colocar que eh registro tardio para receber a
#  documentacao e preencher o requerimento para imprimirmos»; «requerimento,
#  de preferencia sai preenchido depois do processamento dos demais
#  documentos»; «bata com os requisitos do codigo de normas do tjma» — o
#  oficial. A leitura nº 10 da produção juntou PAI e DECLARANTE, TESTEMUNHA 1
#  e TESTEMUNHA 2, sem DNV e sem requerimento.

def _rg(arquivo, nome, cpf, nasc="10/01/1960", mae="MAE EXEMPLO"):
    return {"arquivo": arquivo, "n": 1, "tipo": "IDENTIDADE",
            "dados": {"pessoas": [{"nome": nome, "cpf": cpf, "data_nascimento": nasc,
                                   "naturalidade": "CIDADE EXEMPLO - MA",
                                   "filiacao_mae": mae}]}}


DOCS_DO_TARDIO = [
    _rg("PAI e DECLARANTE.pdf", "MARIO EXEMPLO", "000.000.001-91", "12/12/1953",
        "AVA PATERNA EXEMPLO"),
    _rg("TESTEMUNHA 1.pdf", "BEATRIZ EXEMPLO", "000.000.002-72", "06/09/1985"),
    _rg("TESTEMUNHA 2.pdf", "CARLA EXEMPLO", "000.000.003-53", "21/05/1983"),
    {"arquivo": "ENDEREÇO TESTEMUNHA 2.pdf", "n": 1, "tipo": "OUTRO",
     "dados": {"tipo_do_documento": "Fatura de energia elétrica"}},
]


def test_o_papel_sai_do_nome_do_arquivo():
    assert LEIT.papeis_pelo_nome_do_arquivo("PAI e DECLARANTE.pdf") == ["PAI", "DECLARANTE"]
    assert LEIT.papeis_pelo_nome_do_arquivo("TESTEMUNHA 1.pdf") == ["TESTEMUNHA"]
    assert LEIT.papeis_pelo_nome_do_arquivo("TESTEMUNHA 2.pdf") == ["TESTEMUNHA2"]
    assert LEIT.papeis_pelo_nome_do_arquivo("MÃE.jpg") == ["MAE"]
    assert LEIT.papeis_pelo_nome_do_arquivo("DOCS.pdf") == []


def test_com_a_marca_o_tardio_se_monta_sem_dnv_e_sem_requerimento():
    junto = LEIT.juntar_nascimento(DOCS_DO_TARDIO, tardio=True)
    assert junto["valores"]["registro_tardio"] == "1"
    papeis = {p["papel"]: p for p in junto["pessoas"]}
    assert papeis["PAI"]["nome"] == "Mario Exemplo" and papeis["PAI"]["sexo"] == "M"
    assert papeis["DECLARANTE"]["nome"] == "Mario Exemplo"
    assert papeis["TESTEMUNHA"]["nome"] == "Beatriz Exemplo"
    assert papeis["TESTEMUNHA2"]["nome"] == "Carla Exemplo"
    assert papeis["AVO_PATERNA"]["nome"] == "Ava Paterna Exemplo"
    textos = " ".join(a["texto"] for a in junto["conferencia"])
    assert "registrando" in textos and "art. 249" in textos


def test_sem_a_marca_a_recusa_ensina_a_marcar():
    with pytest.raises(LEIT.LeituraError, match="É registro tardio"):
        LEIT.juntar_nascimento(DOCS_DO_TARDIO)


def test_arquivo_com_duas_pessoas_nao_decide_quem_e_quem():
    duas = {"arquivo": "TESTEMUNHAS.pdf", "n": 1, "tipo": "IDENTIDADE",
            "dados": {"pessoas": [{"nome": "BEATRIZ EXEMPLO"}, {"nome": "CARLA EXEMPLO"}]}}
    junto = LEIT.juntar_nascimento([DOCS_DO_TARDIO[0], duas], tardio=True)
    assert not [p for p in junto["pessoas"] if p["papel"].startswith("TESTEMUNHA")]
    assert any("escolha na tela" in a["texto"] for a in junto["conferencia"])


def test_a_caixa_de_juntar_tem_a_marca_do_tardio(casa):
    html = casa["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    caixa = html[html.index('id="juntar-anexos"'):]
    caixa = caixa[:caixa.index("</form>")]
    assert 'name="registro_tardio"' in caixa and "É registro tardio" in caixa


def test_o_requerimento_se_imprime_da_tela_de_preencher(casa):
    c = casa["c"]
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert "rcpn/requerimento-tardio/imprimir" in html
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    r = c.post("/rcpn/requerimento-tardio/imprimir",
               data={"csrf_token": token, "registro_tardio": "1",
                     "tardio_requerimento": "9/2026",
                     "declarante_nome": "MARIO EXEMPLO", "filiacao2_nome": "MARIO EXEMPLO",
                     "testemunha_nome": "BEATRIZ EXEMPLO",
                     "testemunha2_nome": "CARLA EXEMPLO"})
    papel = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "REQUERIMENTO DE REGISTRO DE NASCIMENTO TARDIO" in papel
    assert "<strong>9/2026</strong>" in papel and "(X) pai" in papel
    assert "window.print" in papel
    # o que o Código de Normas (art. 249) e o Provimento CNJ 149/2023 pedem
    for exigencia in ("art. 249", "arts. 480 a 494", "art. 482, § 2º", "art. 482, § 5º",
                      "ENTREVISTAS", "art. 494", "art. 481", "CPF nº",
                      "certidão negativa", "20 anos"):
        assert exigencia in papel, exigencia
    assert "Dispensada a presença" not in papel       # sem idade: colhem-se


def test_depois_do_processamento_o_requerimento_sai_preenchido(casa):
    con = _con(casa)
    with con:
        lid = LEIT.abrir(con, especie="NASCIMENTO", agora="2026-10-21T14:00:00", por="t")
        LEIT.concluir(con, lid, arquivos=[{"nome": d["arquivo"]} for d in DOCS_DO_TARDIO],
                      lido={"documentos": DOCS_DO_TARDIO}, tardio=True)
        situacao = banco(con).um(
            "SELECT situacao, erro FROM rc_leituras WHERE id = %s", (lid,))
        assert situacao["situacao"] == "LIDA", situacao["erro"]
        rid = LEIT.para_rascunho(con, lid, agora="2026-10-21T14:00:01", por="t")
    con.close()
    html = casa["c"].get(f"/rcpn/novo/nascimento?rascunho_id={rid}").get_data(as_text=True)
    assert "Imprimir o requerimento do registro tardio, preenchido" in html
    assert 'form="form-do-ato"' in html
    assert "Beatriz Exemplo" in html and "Carla Exemplo" in html


def test_com_dnv_as_testemunhas_saem_com_espaco_de_assinar(casa):
    """«Esse registro, em específico, possui apenas cópia da DNV, nisso vou
    pedir testemunhas [...] contar espaço para elas assinarem, mesmo que
    tenhamos o número da DNV» — o oficial, 21/10/2026. Menor de 12 anos com
    DNV: a dispensa vira opção a marcar, e as linhas ficam."""
    c = casa["c"]
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)
    nasc = date.today().replace(year=date.today().year - 5).isoformat()
    base = {"csrf_token": token, "registro_tardio": "1", "dnv": "30-12345678-9",
            "data_fato": nasc, "pessoa_data_nascimento": nasc}
    com = c.post("/rcpn/requerimento-tardio/imprimir",
                 data={**base, "testemunha_nome": "BEATRIZ EXEMPLO",
                       "testemunha2_nome": "CARLA EXEMPLO"}).get_data(as_text=True)
    assert "BEATRIZ EXEMPLO" in com and "CARLA EXEMPLO" in com
    assert "(X) Colhidas por decisão do oficial" in com.replace("( X )", "(X)")
    assert com.count("______________________________________________<br>") >= 3
    sem = c.post("/rcpn/requerimento-tardio/imprimir", data=base).get_data(as_text=True)
    assert "Primeira testemunha" in sem and "Segunda testemunha" in sem
    assert "(X) Dispensadas as testemunhas" in sem.replace("( X )", "(X)")


# ------------------------------------ a junção com a branch — LH05, 21/10/2026
#
# O LD01 (21/10/2026) deu à tela uma SEGUNDA GAVETA de testemunha, prefixo
# `testemunha2`, que gravava outra `TESTEMUNHA` (o casamento pede duas; o parto
# sem assistência médica também). O tardio do servidor deu ao NASCIMENTO o
# papel próprio `TESTEMUNHA2`, com o MESMO prefixo. A junção: no nascimento a
# gaveta grava `TESTEMUNHA2`; nas outras espécies continua a 2ª `TESTEMUNHA`.

def test_no_nascimento_a_segunda_gaveta_e_testemunha2_e_no_casamento_continua_testemunha():
    assert RC.prefixos_do_papel("TESTEMUNHA", "NASCIMENTO") == ("testemunha",)
    assert RC.prefixos_do_papel("TESTEMUNHA2", "NASCIMENTO") == ("testemunha2",)
    assert RC.prefixos_do_papel("TESTEMUNHA", "CASAMENTO") == ("testemunha", "testemunha2")
    assert RC.prefixos_do_papel("TESTEMUNHA", "OBITO") == ("testemunha", "testemunha2")
    assert RC.prefixos_do_papel("TESTEMUNHA") == ("testemunha", "testemunha2")


def test_a_conferencia_le_cada_gaveta_uma_vez_so():
    import rc_conferencia_dados as CONF
    valores = {"testemunha_nome": "BEATRIZ EXEMPLO", "testemunha2_nome": "CARLA EXEMPLO"}
    nasc = CONF.dados_do_formulario(valores, especie="NASCIMENTO")["pessoas"]
    assert [(p["papel"], p["nome"]) for p in nasc] == [
        ("TESTEMUNHA", "BEATRIZ EXEMPLO"), ("TESTEMUNHA2", "CARLA EXEMPLO")]
    cas = CONF.dados_do_formulario(valores, especie="CASAMENTO")["pessoas"]
    assert [(p["papel"], p["nome"]) for p in cas] == [
        ("TESTEMUNHA", "BEATRIZ EXEMPLO"), ("TESTEMUNHA", "CARLA EXEMPLO")]


def test_a_testemunha2_com_o_nome_do_registrado_e_a_fantasma():
    import rc_conferencia_dados as CONF
    probs = CONF.conferir({"especie": "NASCIMENTO", "nome": "JOAO EXEMPLO",
                           "pessoas": [{"papel": "REGISTRADO", "nome": "JOAO EXEMPLO"},
                                       {"papel": "TESTEMUNHA2", "nome": "JOAO EXEMPLO"}]})
    fantasmas = [p for p in probs if p["codigo"] == "TESTEMUNHA_FANTASMA"]
    assert fantasmas and fantasmas[0]["campo"] == "TESTEMUNHA2"
    assert CONF.campos_para_corrigir(fantasmas)[0]["campo"].startswith("testemunha2_")


def test_a_tela_do_nascimento_tem_uma_gaveta_so_da_segunda_testemunha(casa):
    html = casa["c"].get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert html.count('name="testemunha2_nome"') == 1
    casamento = casa["c"].get("/rcpn/novo/casamento").get_data(as_text=True)
    assert casamento.count('name="testemunha2_nome"') == 1


def test_o_termo_do_tardio_nao_escreve_a_testemunha_duas_vezes():
    a = dict(ADULTO, especie="NASCIMENTO", tardio_requerimento="1/2026",
             data_ato="2026-10-21")
    valores = ML.valores_do_assento(a, PESSOAS + DUAS)
    assert "CARLA EXEMPLO" in valores["frase_tardio"]
    assert valores["testemunhas"] == ""
    texto = ML.montar_do_assento(a, PESSOAS + DUAS)["texto"]
    assert texto.count("CARLA EXEMPLO") == 1 and texto.count("BEATRIZ EXEMPLO") == 1


def test_no_prazo_as_duas_testemunhas_do_parto_saem_no_termo():
    """O parto sem assistência médica (LRP art. 54, 9º — LD01): a segunda do
    nascimento agora é TESTEMUNHA2, e continua no claro `{testemunhas}`."""
    a = dict(ADULTO, especie="NASCIMENTO", registro_tardio="", data_ato="2026-10-21")
    valores = ML.valores_do_assento(a, PESSOAS + DUAS)
    assert valores["frase_tardio"] == ""
    assert "BEATRIZ EXEMPLO" in valores["testemunhas"]
    assert "CARLA EXEMPLO" in valores["testemunhas"]


def test_a_frase_do_tardio_tem_os_bytes_da_producao():
    """As peças `RC_TERMO_NASCIMENTO__tardio*` (o texto saiu do código, LF06C)
    montam a MESMA frase que a f-string do servidor (rc_modelos_do_livro da
    produção 3.6.293.4 + tardio 2), nos três casos."""
    a = dict(ADULTO, especie="NASCIMENTO", tardio_requerimento="1/2026",
             data_ato="2026-10-21")
    inicio = (" Registro lavrado fora do prazo legal, nos termos do art. 46 da "
              "Lei nº 6.015/1973 e do art. 249 do Código de Normas do TJMA, à "
              "vista do requerimento")
    assert ML.frase_do_tardio(a, PESSOAS + DUAS) == (
        inicio + " nº 1/2026 autuado nesta serventia, assinado pelas testemunhas "
        "BEATRIZ EXEMPLO e CARLA EXEMPLO, que atestaram, sob as penas da lei, a "
        "identidade do(a) registrado(a).")
    crianca = {"especie": "NASCIMENTO", "registro_tardio": "1",
               "data_fato": "2020-01-01", "data_ato": "2026-10-21",
               "dnv": "30-00000000-1"}
    pessoas = [{"papel": "REGISTRADO", "nome": "X", "data_nascimento": "2020-01-01"}]
    assert ML.frase_do_tardio(crianca, pessoas) == (
        inicio + " autuado nesta serventia, dispensada a presença de testemunhas "
        "por se tratar de registrando menor de 12 (doze) anos com DNV "
        "apresentada (art. 249, II).")
    assert ML.frase_do_tardio(dict(crianca, dnv=""), pessoas) == (
        inicio + " autuado nesta serventia.")


def test_o_numero_sugerido_e_o_seguinte_ao_maior_do_ano(casa):
    ano = date.today().year
    c, conf = _tardio_pela_tela(casa, tardio_requerimento=f"7/{ano}")
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[0])
    c.post("/rcpn/novo/nascimento", data=envio2, follow_redirects=True)
    con = _con(casa)
    assert banco(con).valor(
        "SELECT count(*) AS n FROM rc_assentos WHERE tardio_requerimento = %s",
        (f"7/{ano}",)) == 1
    con.close()
    html = c.get("/rcpn/novo/nascimento").get_data(as_text=True)
    assert re.search(rf'name="tardio_requerimento"\s+value="8/{ano}"', html)


def test_pela_tela_a_segunda_testemunha_entra_uma_vez_so(casa):
    """A gaveta `testemunha2` grava UMA pessoa no nascimento: a TESTEMUNHA2.
    Lida também como segunda TESTEMUNHA (a régua do LD01 sem a espécie), a
    mesma pessoa entraria duas vezes no assento."""
    c, conf = _tardio_pela_tela(casa)
    envio2 = _como_o_navegador(conf, ("acao", "lavrar"), folha_seguranca=FOLHAS[0])
    c.post("/rcpn/novo/nascimento", data=envio2, follow_redirects=True)
    con = _con(casa)
    bd = banco(con)
    aid = bd.valor("SELECT max(id) AS id FROM rc_assentos")
    papeis = [r["papel"] for r in bd.ler(
        "SELECT papel FROM rc_pessoas WHERE assento_id = %s AND nome = %s ORDER BY id",
        (aid, "CARLA EXEMPLO"))]
    con.close()
    assert papeis == ["TESTEMUNHA2"]
