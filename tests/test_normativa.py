"""A base normativa por artigo — o índice e a busca com citação (05/11/2026).

O oficial pediu os agentes abastecidos com o código de normas estadual, o
nacional e as leis da atividade, e a resposta citando o artigo. Estes testes
guardam o índice (cada artigo uma vez, com o número certo, nas formas que os
arquivos trazem) e a busca (o artigo pertinente aparece, com a citação e o
link da fonte; o revogado não).
"""
from __future__ import annotations

import collections
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import normativa as N                                            # noqa: E402


# ------------------------------------------------------------------ o índice


def test_toda_norma_da_pasta_entra_com_fonte_e_artigos():
    arquivos = sorted(p.stem for p in N.PASTA.rglob("*.md")
                      if p.name.lower() != "readme.md")
    normas = N.normas()
    assert sorted(n["chave"] for n in normas) == arquivos
    for n in normas:
        # o link da fonte oficial; no CN-MA, o DJe por extenso (não há link)
        assert n["fonte"].startswith("http") or "Diário da Justiça" in n["fonte"], (
            n["chave"], n["fonte"])
        assert n["artigos"], f"{n['chave']} não tem artigo nenhum"


def test_todo_arquivo_tem_nome_curto_e_todo_nome_curto_tem_arquivo():
    """Os nomes curtos são escritos à mão: a lista não pode envelhecer calada."""
    arquivos = {p.stem for p in N.PASTA.rglob("*.md") if p.name.lower() != "readme.md"}
    assert set(N.NOMES) == arquivos


def test_nenhuma_norma_tem_dois_artigos_com_o_mesmo_numero():
    for n in N.normas():
        repetidos = [k for k, v in collections.Counter(
            a["numero"] for a in n["artigos"]).items() if v > 1]
        assert not repetidos, f"{n['nome']}: {repetidos[:5]}"


def test_os_codigos_tem_os_artigos_que_tem():
    """Contados no arquivo em 05/11/2026 (ver base_normativa/README.md)."""
    por_chave = {n["chave"]: n for n in N.normas()}
    assert len(por_chave["codigo_de_normas_tjma"]["artigos"]) == 1036
    assert len(por_chave["codigo_nacional_de_normas_cnj"]["artigos"]) == 906


def test_o_artigo_do_provimento_nao_e_o_artigo_do_codigo():
    """O «Art. 1º» do provimento que institui o código perdeu a marca na
    ingestão: o art. 1º do índice é o do código."""
    texto = N.artigo("CN-MA", "1")["texto"]
    assert "Fica aprovado" not in texto
    assert "atualiza, revisa e consolida" in texto


def test_o_numero_se_le_em_todas_as_formas_dos_arquivos():
    texto = "\n".join([
        "# Lei de teste",
        "**Art. 1º.** Primeiro.",
        "**Art. 2.º** Segundo.",
        "**Art**. 3º Terceiro.",
        "**Art. 12-A.** Com letra.",
        "**Art. 1.020.** Milhar.",
        "**Art. 1.**021. O negrito no lugar errado.",
        "**Art. 1022.** Milhar sem ponto.",
        "**Art. 5.** *(Revogado pela Lei de teste)*",
        "## Seção II",
        "**Art. 6** Na seção dois.",
    ])
    artigos = N.partir(texto)
    assert [a["numero"] for a in artigos] == [
        "1", "2", "3", "12-A", "1020", "1021", "1022", "5", "6"]
    assert [a["numero"] for a in artigos if a["revogado"]] == ["5"]
    assert artigos[-1]["secao"] == "Seção II"


def test_o_artigo_de_mil_que_a_conversao_negritou_errado_e_achado():
    assert "Indicador Pessoal" in N.artigo("CN-MA", "1.000")["texto"]


# --------------------------------------------------------- pedir pelo número


def test_pede_a_norma_pelo_apelido():
    assert N.norma("LRP")["chave"] == "lei-6015-1973-12-31"
    assert N.norma("cn-ma")["chave"] == "codigo_de_normas_tjma"
    assert N.norma("Lei 9.492")["chave"] == "lei-9492-1997-09-10"
    assert N.norma("CNN")["chave"] == "codigo_nacional_de_normas_cnj"


def test_norma_que_nao_ha_recusa_dizendo_as_que_ha():
    with pytest.raises(N.NormaError) as erro:
        N.norma("Lei 99.999")
    assert "Lei 6.015/1973 (LRP)" in str(erro.value)


def test_artigo_com_letra_e_com_citacao():
    a = N.artigo("LRP", "216-A")
    assert "usucapião" in a["texto"].lower()
    assert a["citacao"].startswith("Lei 6.015/1973 (LRP), art. 216-A — fonte: http")


def test_artigo_que_nao_ha_recusa_com_frase():
    with pytest.raises(N.NormaError, match="não tem art. 9999"):
        N.artigo("Lei 9.492", "9999")


def test_artigo_grande_vem_cortado_avisando_e_inteiro_quando_pedido():
    grandes = [(n, a) for n in N.normas() for a in n["artigos"]
               if len(a["texto"]) > N.LIMITE_DO_TRECHO]
    assert grandes
    n, a = grandes[0]
    cortado = N.artigo(n["chave"], a["numero"])["texto"]
    assert "peça o artigo inteiro" in cortado
    assert N.artigo(n["chave"], a["numero"], inteiro=True)["texto"] == a["texto"]


# ------------------------------------------------------------------- a busca


def test_o_cheque_furtado_acha_a_vedacao_nos_dois_codigos():
    achados = N.buscar("protesto de cheque devolvido por furto ou extravio", limite=3)
    citados = {(a["norma"], a["artigo"]) for a in achados}
    assert ("CNN (Prov. CNJ 149/2023)", "390") in citados
    assert ("CN-MA (Prov. COGEX/TJMA 28/2026)", "911") in citados


def test_o_cancelamento_de_hipoteca_acha_a_lrp():
    achados = N.buscar("cancelamento de hipoteca", limite=5)
    assert ("Lei 6.015/1973 (LRP)", "251") in {(a["norma"], a["artigo"]) for a in achados}


def test_a_busca_pode_ficar_numa_norma_so():
    achados = N.buscar("gratuidade nascimento", em="LRP")
    assert achados and {a["norma"] for a in achados} == {"Lei 6.015/1973 (LRP)"}


def test_revogado_nao_entra_na_busca_a_nao_ser_que_se_peca():
    revogados = [(n, a) for n in N.normas() for a in n["artigos"] if a["revogado"]]
    assert revogados
    n, a = revogados[0]
    termo = a["texto"].split("\n")[0][len(a["rotulo"]):].strip(" .*")[:40]
    sem = N.buscar(termo, em=n["chave"], limite=50)
    assert a["numero"] not in {x["artigo"] for x in sem}
    com = N.buscar(termo, em=n["chave"], limite=50, com_revogados=True)
    assert a["numero"] in {x["artigo"] for x in com}


def test_cada_achado_vai_ao_modelo_com_a_citacao_na_frente():
    achados = N.buscar("cancelamento de hipoteca", limite=2)
    texto = N.para_o_modelo(achados)
    assert texto.startswith("[")
    assert texto.count("— fonte: ") == 2


def test_o_vazio_diz_que_e_vazio_e_nao_que_a_norma_nao_trata():
    texto = N.para_o_modelo(N.buscar("xilofone azulado tonitroante"), "xilofone")
    assert "não que a norma" in texto


def test_termo_vazio_e_recusado():
    with pytest.raises(N.NormaError):
        N.buscar("   ")


# ------------------------------------------- a ferramenta dos agentes (etapa 3)

import agente_ferramentas as AF                                  # noqa: E402


def _contexto():
    return AF.Contexto(db=None, raiz=RAIZ, pasta_de_dados=RAIZ, agora="",
                       usuario="", sessao_id=0)


def test_a_norma_e_de_leitura_e_vai_para_o_balcao_e_para_o_agente():
    assert "consultar_norma" in AF.FERRAMENTAS_DA_AJUDA
    assert "consultar_norma" not in AF.FERRAMENTAS_DA_AJUDA_SO_ADMIN
    assert AF.POR_NOME["consultar_norma"].e_escrita is False
    assert "consultar_norma" in {f.nome for f in AF.catalogo(escrita=False)}
    for admin in (True, False):
        assert "consultar_norma" in {f["nome"] for f in AF.esquemas_da_ajuda(admin=admin)}


def test_a_ferramenta_devolve_o_artigo_com_a_citacao():
    r = AF.executar(_contexto(), "consultar_norma", {"norma": "CNN", "artigo": "390"})
    assert r["erro"] is False
    assert r["conteudo"].startswith("[CNN (Prov. CNJ 149/2023), art. 390 — fonte:")
    assert "20, 25, 28, 30 e 35" in r["conteudo"]


def test_a_ferramenta_procura_e_pede_a_norma_para_o_artigo():
    r = AF.executar(_contexto(), "consultar_norma", {"termo": "cancelamento de hipoteca"})
    assert r["erro"] is False and "art. 251" in r["conteudo"]
    sem_norma = AF.executar(_contexto(), "consultar_norma", {"artigo": "390"})
    assert sem_norma["erro"] is True and "diga a norma" in sem_norma["conteudo"]
    lista = AF.executar(_contexto(), "consultar_norma", {})
    assert "Lei 9.492/1997 (Protesto)" in lista["conteudo"]


def test_as_duas_instrucoes_mandam_citar_o_artigo_lido():
    import agente
    import ajuda
    for instrucao in (agente.INSTRUCAO, ajuda.INSTRUCAO):
        assert "consultar_norma" in instrucao
        assert "Não cite artigo que não leu" in instrucao


def test_nenhum_artigo_e_bloqueado_nem_adulterado_pela_barreira():
    """O texto é público e não traz dado da serventia. Decisão do oficial (05/11/2026): a ferramenta o
    declara texto público, e a barreira pula as passagens de nome, endereço e dado sensível — antes, cerca
    de um quarto dos artigos chegava ao modelo com «[PESSOA_01]» no lugar de «em nome do loteador». Só o
    identificador inequívoco continua trocado: o e-mail institucional do art. 446 do CNN."""
    import ajuda_privacidade as PRIV
    alterados = []
    for n in N.normas():
        for a in n["artigos"]:
            texto = f"[{N.citacao(n, a)}]\n{N._cortar(a['texto'])}"
            if PRIV.sanitizar_para_modelo(texto, nomes_livres=False, texto_publico=True) != texto:
                alterados.append((n["chave"], a["numero"]))
    assert alterados == [("codigo_nacional_de_normas_cnj", "446")], alterados[:10]


def test_a_ferramenta_da_norma_e_texto_publico_e_a_lei_chega_inteira():
    assert AF.POR_NOME["consultar_norma"].texto_publico is True
    assert not any(f.texto_publico for f in AF.FERRAMENTAS if f.nome != "consultar_norma")
    r = AF.executar(_contexto(), "consultar_norma", {"norma": "Lei 6.766", "termo": "em nome do loteador"})
    assert "em nome do loteador" in r["conteudo"] and "[PESSOA_" not in r["conteudo"], r["conteudo"][:600]


# ------------------------------------- os agentes de chamada única (05/11/2026, item 5)

def test_o_bloco_do_pedido_traz_os_artigos_da_atribuicao_com_a_citacao():
    bloco = N.trechos_para_o_pedido("compra e venda registro", atribuicao="RI")
    assert bloco.startswith("=== A NORMA PERTINENTE")
    citadas = {linha.split(", art.")[0].lstrip("[") for linha in bloco.splitlines() if linha.startswith("[")}
    nomes_ri = {N.norma(c)["nome"] for c in N.NORMAS_DA_ATRIBUICAO["RI"]}
    assert citadas and citadas <= nomes_ri, citadas
    assert bloco.count("— fonte: ") <= N.LIMITE_PARA_O_PEDIDO


def test_sem_assunto_ou_sem_achado_nao_ha_bloco():
    assert N.trechos_para_o_pedido("", atribuicao="RI") == ""
    assert N.trechos_para_o_pedido("xilofone azulado tonitroante", atribuicao="RI") == ""


def test_a_qualificacao_assistida_recebe_a_base_por_ordem_do_oficial():
    import ri_qualificacao_ia as QIA
    assert QIA.SUSPENSA_POR_BASE_NORMATIVA is False
    fonte = open(QIA.__file__, encoding="utf-8").read()
    assert "CONHEC.contexto" in fonte
