"""A PROVA DA INTIMAÇÃO E A AFIRMAÇÃO EXPRESSA — ordem do oficial, 29/10/2026.

«nao deixar protestar sem aviso de que foi intimado (com comprovante juntado)
ou comprovacao do envio do edital na cenprot. vincular cada obrigacao a uma
conduta, nao deixando a escrevente cometer erros. se insistir em algo que eh
erro, precisa afirmar expressamente e deixar log».

O QUE ESTES TESTES GUARDAM
      - **sem a prova, o protesto não se lavra** — em nenhum caminho: o
        domínio confere sempre, e as duas rotas que protestam (a ficha e o
        lote «A protestar») passam a afirmação do formulário;
      - **pessoal**: o aviso que lavrou a intimação ENTREGUE, com quem
        recebeu e com o comprovante anexado A ELE; a intimação lançada à mão,
        sem aviso, não tem prova;
      - **digital**: a Resolve confirmou (INTIMADO) e o histórico está
        guardado;
      - **edital**: o edital publicado E o comprovante do envio à CENPROT do
        dia dele — e, juntado depois do dia do edital, o protesto só do
        segundo dia útil depois do comprovante (CN-MA art. 922, § 1º);
      - **a entrega só com o comprovante e quem recebeu**, no mesmo ato; a
        tentativa continua aceitando o comprovante depois;
      - **o comprovante suspeito** — o mesmo arquivo de outro aviso, o
        protocolo de outro título no nome — só entra com afirmação;
      - **a afirmação expressa**: a caixa e o texto com pelo menos 30 letras
        além da frase de abertura; vencida a trava, o texto vai no ato e uma
        linha `AFIRMACAO_EXPRESSA` vai na auditoria, por regra vencida.
"""
from __future__ import annotations

import ast
import json
import sqlite3
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import (PDF_DE_TESTE, entregar_com_comprovante,  # noqa: E402
                                garantir_anexos)

import protesto as PT                            # noqa: E402
import protesto_aviso as AV                      # noqa: E402
import protesto_prova as PROVA                   # noqa: E402
from bd_nativo import banco as nativo            # noqa: E402
from nucleo_schema import init_nucleo_schema     # noqa: E402
from pt_schema import init_pt_schema             # noqa: E402

HOJE = "2026-08-25"
AGORA = "2026-08-25T12:30:00"
EXTENSO = "vinte e cinco de agosto de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DO OFÍCIO ÚNICO DE CIDADE EXEMPLO",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro",
      "ri_cns": "000000", "ri_cidade": "Cidade Exemplo", "ri_uf": "MA"}
AFIRMACAO = ("o canhoto assinado está na pasta do dia e será escaneado amanhã "
             "pela digitalização")


@pytest.fixture()
def con():
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    init_nucleo_schema(c)
    init_pt_schema(c)
    c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
    c.executemany("INSERT OR REPLACE INTO settings VALUES (?, ?)",
                  [("ibge_uf", "21"), ("ibge_municipio", "98765")])
    garantir_anexos(c)
    yield c
    c.close()


def titulo(con, numero="7001/1") -> int:
    dados = {
        "apresentante_codigo": "001", "apresentante_nome": "BANCO EXEMPLO",
        "especie": "DMI", "numero_titulo": numero, "nosso_numero": f"NN{numero}",
        "data_emissao": "2026-01-05", "data_vencimento": "2026-02-05",
        "valor": "1200.00", "saldo": "1310.45",
        "praca_protesto": "CIDADE EXEMPLO",
        "tipo_moeda": "1", "tipo_protesto": "C", "motivo_protesto": "1",
        "cedente": {"nome": "LOJA EXEMPLO LTDA", "documento": "00000001000055"},
        "devedores": [{"nome": "MARIA EXEMPLO", "CPF": "00000000191",
                       "enderecos": [{"endereco": "RUA GRANDE, 10",
                                      "bairro": "CENTRO", "cep": "65000000",
                                      "cidade": "Cidade Exemplo", "uf": "MA"}]}],
    }
    tid = PT.cadastrar_titulo(con, dados, origem="CRA",
                              origem_chave=f"lote:{numero}", agora=AGORA)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso=EXTENSO)
    return tid


def protocolo(con, tid, numero: str = "2608250001") -> str:
    """O protocolo do título, AAMMDD + sequencial — posto à vista no teste,
    para a conta não depender do sequencial do dia."""
    nativo(con).escrever("UPDATE pt_titulos SET protocolo = %s WHERE id = %s",
                         (numero, tid))
    return numero


def protestar(con, tid, *, agora=AGORA, **kw):
    return PT.lancar_protesto(con, tid, sv=SV, agora=agora,
                              data_extenso=EXTENSO, **kw)


def protestos(con, tid) -> list[dict]:
    return nativo(con).ler(
        "SELECT * FROM pt_atos WHERE titulo_id = %s AND tipo = 'PROTESTO'",
        (tid,))


def pasta() -> str:
    return tempfile.mkdtemp(prefix="cg_prova_")


# ------------------------------------------------- o contrato da afirmação


def test_a_frase_de_abertura_nao_conta_no_piso_de_trinta_letras():
    assert PROVA.afirmacao_valida(None) is None
    assert PROVA.afirmacao_valida("") is None
    # a frase sozinha tem mais de trinta letras — e não diz nada
    assert PROVA.afirmacao_valida(PROVA.FRASE_DA_AFIRMACAO) is None
    assert PROVA.afirmacao_valida(PROVA.FRASE_DA_AFIRMACAO + " ok, confere") is None
    # pontuação e números não são letras
    assert PROVA.afirmacao_valida("." * 80 + " 123456789") is None


def test_a_afirmacao_valida_fica_com_a_frase_uma_vez_so():
    texto = PROVA.afirmacao_valida(AFIRMACAO)
    assert texto == f"{PROVA.FRASE_DA_AFIRMACAO} {AFIRMACAO}"
    # quem digitou a frase de novo não a vê repetida
    de_novo = PROVA.afirmacao_valida(f"{PROVA.FRASE_DA_AFIRMACAO}, {AFIRMACAO}")
    assert de_novo == texto


def test_a_recusa_diz_como_afirmar_e_avisa_quando_a_afirmacao_e_curta():
    with pytest.raises(PROVA.ProvaError) as erro:
        PROVA.vencer_ou_recusar("REGRA_DE_TESTE", "Falta tal coisa.", None)
    assert "Falta tal coisa." in str(erro.value)
    assert "marque «Afirmo»" in str(erro.value)
    with pytest.raises(PROVA.ProvaError) as erro:
        PROVA.vencer_ou_recusar("REGRA_DE_TESTE", "Falta tal coisa.", "curta")
    assert "curta demais" in str(erro.value)
    registro = PROVA.vencer_ou_recusar("REGRA_DE_TESTE", "Falta tal coisa.",
                                       AFIRMACAO)
    assert PROVA.para_a_auditoria(registro) == {
        "regra": "REGRA_DE_TESTE",
        "afirmacao": f"{PROVA.FRASE_DA_AFIRMACAO} {AFIRMACAO}",
        "o_que_faltava": "Falta tal coisa."}


# --------------------------------------------- a prova da intimação pessoal


def test_intimacao_pessoal_lancada_a_mao_nao_tem_prova_e_nao_protesta(con):
    tid = titulo(con)
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA,
                        comprovante="AR 123")
    with pytest.raises(PROVA.ProvaError) as erro:
        protestar(con, tid)
    texto = str(erro.value)
    assert "lançada à mão, sem aviso entregue" in texto
    assert "Avisos e editais" in texto            # onde se resolve
    assert protestos(con, tid) == []
    assert PT.titulo(con, tid)["situacao"] == "INTIMADO"


def test_aviso_entregue_com_comprovante_e_quem_recebeu_e_prova_completa(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, aviso["aviso_id"], agora=AGORA,
                             pasta=pasta())
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert prova["completa"] and prova["modo"] == "PESSOAL", prova
    r = protestar(con, tid)
    assert r["afirmacao_expressa"] is None
    detalhe = json.loads(protestos(con, tid)[0]["detalhe_json"])
    assert detalhe["prova"]["completa"] is True
    assert "afirmacao_expressa" not in detalhe


def test_entrega_sem_comprovante_por_afirmacao_e_o_protesto_pede_outra(con):
    """Cada obrigação, uma conduta: a afirmação da entrega não vale pelo
    protesto — ele pede a sua, com o que falta dito de novo."""
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, aviso["aviso_id"], entregue=True, agora=AGORA,
                         recebido_por="MARIA EXEMPLO", afirmacao=AFIRMACAO)
    with pytest.raises(PROVA.ProvaError) as erro:
        protestar(con, tid)
    assert "não tem o comprovante anexado" in str(erro.value)
    assert protestos(con, tid) == []

    r = protestar(con, tid, afirmacao=AFIRMACAO)
    afirmada = r["afirmacao_expressa"]
    assert afirmada["regra"] == "PROTESTO_SEM_PROVA_DA_INTIMACAO"
    assert afirmada["afirmacao"].startswith(PROVA.FRASE_DA_AFIRMACAO)
    assert "não tem o comprovante anexado" in afirmada["o_que_faltava"]
    detalhe = json.loads(protestos(con, tid)[0]["detalhe_json"])
    assert detalhe["afirmacao_expressa"] == afirmada
    assert detalhe["prova"]["completa"] is False


def test_o_comprovante_retirado_nao_prova_nada(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, aviso["aviso_id"], agora=AGORA, pasta=pasta())
    bd = nativo(con)
    bd.escrever("ALTER TABLE attachments ADD COLUMN IF NOT EXISTS retirado_em TEXT")
    bd.escrever("UPDATE attachments SET retirado_em = %s WHERE entity_id = %s",
                (AGORA, aviso["aviso_id"]))
    assert not PROVA.conferir(con, tid, hoje=HOJE)["completa"]


# ------------------------------------------------------ a prova do edital


def _por_edital(con, numero="7001/1") -> tuple[int, dict]:
    tid = titulo(con, numero)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, aviso["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    edital = AV.publicar_edital(con, aviso["aviso_id"], sv=SV, hoje=HOJE,
                                agora=AGORA)
    return tid, edital


def test_edital_sem_o_comprovante_do_envio_a_cenprot_nao_protesta(con):
    """O caso de outubro: o protesto saiu antes de o arquivo do edital subir
    à CENPROT (CN-MA art. 922, § 1º: afixado E publicado)."""
    tid, _ = _por_edital(con)
    with pytest.raises(PROVA.ProvaError) as erro:
        protestar(con, tid, agora="2026-08-27T10:00:00")
    texto = str(erro.value)
    assert "comprovante do envio do arquivo dos editais de 25/08/2026" in texto
    assert "Envio do edital à CENPROT" in texto
    assert protestos(con, tid) == []

    AV.guardar_comprovante_do_envio(con, HOJE, nome="envio.pdf",
                                    conteudo=PDF_DE_TESTE,
                                    pasta_de_arquivos=pasta(), agora=AGORA)
    protestar(con, tid, agora="2026-08-27T10:00:00")
    assert len(protestos(con, tid)) == 1


def test_comprovante_juntado_depois_do_edital_conta_do_dia_dele(con):
    """O arquivo do edital de 22/10 só subiu em 26/10: a publicação na CENPROT
    só está provada desde o comprovante, e o protesto, do segundo dia útil
    depois dele. Edital de 25/08 (terça), comprovante de 27/08 (quinta):
    protesto a partir de 31/08 (segunda)."""
    tid, _ = _por_edital(con)
    AV.guardar_comprovante_do_envio(con, HOJE, nome="envio.pdf",
                                    conteudo=PDF_DE_TESTE,
                                    pasta_de_arquivos=pasta(),
                                    agora="2026-08-27T16:00:00")
    with pytest.raises(PROVA.ProvaError) as erro:
        protestar(con, tid, agora="2026-08-28T10:00:00")
    assert "só foi juntado em 27/08/2026" in str(erro.value)
    assert "a partir de 31/08/2026" in str(erro.value)
    protestar(con, tid, agora="2026-08-31T10:00:00")
    assert len(protestos(con, tid)) == 1


def test_intimacao_por_edital_digitada_a_mao_sem_edital_publicado(con):
    tid = titulo(con)
    PT.lancar_intimacao(con, tid, modo="EDITAL", agora=AGORA,
                        codigo_edital="ED-2026-0099")
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert not prova["completa"]
    assert "«ED-2026-0099» foi digitado à mão" in prova["frase"]


# ----------------------------------------------------- a prova digital


def _digital(con, *, estado="INTIMADO", historico='[{"canal": "EMAIL"}]'):
    from rs_schema import init_rs_schema
    import centrais_cred as CRED
    init_rs_schema(con)
    tid = titulo(con)
    PT.lancar_intimacao(con, tid, modo="PESSOAL", digital=True, agora=AGORA)
    if estado:
        nativo(con).escrever(
            """INSERT INTO rs_intimacoes(titulo_id, ambiente, identificador,
                   teor, enviada_em, estado, estado_em, historico)
               VALUES (%s,%s,%s,'{}',%s,%s,%s,%s)""",
            (tid, CRED.PRODUCAO, f"T-{tid}", AGORA, estado, AGORA, historico))
    return tid


def test_digital_sem_a_resolve_nao_tem_prova(con):
    tid = _digital(con, estado=None)
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert prova["modo"] == "DIGITAL" and not prova["completa"]
    assert "não há Intimação Digital (Resolve)" in prova["frase"]


def test_digital_confirmada_sem_o_historico_guardado_nao_tem_prova(con):
    tid = _digital(con, historico=None)
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert not prova["completa"]
    assert "histórico da Resolve" in prova["frase"]
    assert "Trazer o histórico" in prova["frase"]


def test_digital_confirmada_com_o_historico_protesta(con):
    tid = _digital(con)
    assert PROVA.conferir(con, tid, hoje=HOJE)["completa"]
    protestar(con, tid)
    assert len(protestos(con, tid)) == 1


def test_digital_so_entregue_precisa_da_entrega_aceita_pela_tela(con):
    tid = _digital(con, estado="ENTREGUE")
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert not prova["completa"]
    assert "só ENTREGOU" in prova["frase"]


# ---------------------------------------------- a entrega e o comprovante


def test_entrega_sem_comprovante_e_sem_quem_recebeu_e_recusada(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        AV.registrar_entrega(con, aviso["aviso_id"], entregue=True, agora=AGORA)
    texto = str(erro.value)
    assert "falta o nome de quem recebeu" in texto
    assert "falta o comprovante assinado" in texto
    assert "marque «Afirmo»" in texto
    assert AV.ler(con, aviso["aviso_id"])["situacao"] == "EMITIDO"
    assert PT.titulo(con, tid)["situacao"] == "APONTADO"


def test_entrega_por_afirmacao_devolve_o_registro_para_a_auditoria(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    r = AV.registrar_entrega(con, aviso["aviso_id"], entregue=True,
                             agora=AGORA, afirmacao=AFIRMACAO)
    assert r["situacao"] == "ENTREGUE" and r["anexo_id"] is None
    [afirmada] = r["afirmacoes"]
    assert afirmada["regra"] == "ENTREGA_SEM_COMPROVANTE"
    assert "quem recebeu" in afirmada["o_que_faltava"]


def test_a_tentativa_continua_aceitando_o_comprovante_depois(con):
    """O caminho «comprovante depois» existe de propósito para o aviso NÃO
    entregue: o canhoto com as tentativas anotadas volta depois, e é ele que
    fundamenta o edital."""
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    r = AV.registrar_entrega(con, aviso["aviso_id"], entregue=False, motivo=11,
                             agora=AGORA)
    assert r["afirmacoes"] == []
    anexo = AV.guardar_comprovante(con, aviso["aviso_id"], nome="tentativa.pdf",
                                   conteudo=PDF_DE_TESTE,
                                   pasta_de_arquivos=pasta(), agora=AGORA)
    assert anexo["anexo_id"] and anexo["afirmacoes"] == []


def test_o_mesmo_arquivo_de_outro_titulo_e_recusado(con):
    um = titulo(con, "7001/1")
    dois = titulo(con, "7002/1")
    a1 = AV.emitir(con, um, hoje=HOJE, agora=AGORA)
    a2 = AV.emitir(con, dois, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, a1["aviso_id"], entregue=True, agora=AGORA,
                         recebido_por="MARIA EXEMPLO",
                         comprovante_nome="canhoto.pdf",
                         comprovante_conteudo=PDF_DE_TESTE,
                         pasta_de_arquivos=pasta())
    with pytest.raises(AV.AvisoError) as erro:
        AV.registrar_entrega(con, a2["aviso_id"], entregue=True, agora=AGORA,
                             recebido_por="MARIA EXEMPLO",
                             comprovante_nome="canhoto.pdf",
                             comprovante_conteudo=PDF_DE_TESTE,
                             pasta_de_arquivos=pasta())
    assert "de OUTRO título" in str(erro.value)
    assert AV.ler(con, a2["aviso_id"])["situacao"] == "EMITIDO"

    r = AV.registrar_entrega(con, a2["aviso_id"], entregue=True, agora=AGORA,
                             recebido_por="MARIA EXEMPLO",
                             comprovante_nome="canhoto.pdf",
                             comprovante_conteudo=PDF_DE_TESTE,
                             pasta_de_arquivos=pasta(), afirmacao=AFIRMACAO)
    assert [x["regra"] for x in r["afirmacoes"]] == ["COMPROVANTE_DE_OUTRO_TITULO"]
    assert r["anexo_id"]


def test_o_nome_com_o_protocolo_de_outro_titulo_e_recusado(con):
    """O caso de outubro: «2610070012.pdf» anexado ao aviso do protocolo
    2610070007."""
    tid = titulo(con)
    meu = protocolo(con, tid)
    outro = "2608250006"
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        AV.registrar_entrega(con, aviso["aviso_id"], entregue=True, agora=AGORA,
                             recebido_por="MARIA EXEMPLO",
                             comprovante_nome=f"{outro}.pdf",
                             comprovante_conteudo=PDF_DE_TESTE,
                             pasta_de_arquivos=pasta())
    assert f"cita o protocolo {outro}" in str(erro.value)
    # o nome com o protocolo DESTE título entra sem afirmação
    r = AV.registrar_entrega(con, aviso["aviso_id"], entregue=True, agora=AGORA,
                             recebido_por="MARIA EXEMPLO",
                             comprovante_nome=f"{meu}.pdf",
                             comprovante_conteudo=PDF_DE_TESTE,
                             pasta_de_arquivos=pasta())
    assert r["afirmacoes"] == [] and r["anexo_id"]


def test_numero_de_dez_digitos_que_nao_comeca_com_data_nao_e_protocolo():
    assert PROVA.protocolos_no_nome("2610070012.pdf") == ["2610070012"]
    assert PROVA.protocolos_no_nome("telefone 9899991234.pdf") == []
    assert PROVA.protocolos_no_nome("aviso-412-2026-1.pdf") == []
    assert PROVA.protocolos_no_nome("26100700120.pdf") == []   # onze dígitos


def test_o_comprovante_depois_tambem_recusa_o_arquivo_de_outro_aviso(con):
    tid = titulo(con)
    a1 = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, a1["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    a2 = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, a2["aviso_id"], entregue=False, motivo=11,
                         agora=AGORA)
    AV.guardar_comprovante(con, a1["aviso_id"], nome="t.pdf",
                           conteudo=PDF_DE_TESTE, pasta_de_arquivos=pasta(),
                           agora=AGORA)
    with pytest.raises(AV.AvisoError) as erro:
        AV.guardar_comprovante(con, a2["aviso_id"], nome="t.pdf",
                               conteudo=PDF_DE_TESTE, pasta_de_arquivos=pasta(),
                               agora=AGORA)
    assert "deste mesmo título" in str(erro.value)
    r = AV.guardar_comprovante(con, a2["aviso_id"], nome="t.pdf",
                               conteudo=PDF_DE_TESTE, pasta_de_arquivos=pasta(),
                               agora=AGORA, afirmacao=AFIRMACAO)
    assert [x["regra"] for x in r["afirmacoes"]] == ["COMPROVANTE_DE_OUTRO_AVISO"]


# --------------------------------- a pendência que o roteiro do Protesto lê


def test_intimacoes_sem_prova_lista_so_o_que_a_trava_recusaria(con):
    """A régua é a do protesto (`conferir`): o provado não entra; o pessoal
    sem comprovante, o edital sem o envio à CENPROT e o digital sem a Resolve
    entram, cada um com o que falta."""
    provado = titulo(con, "7001/1")
    aviso = AV.emitir(con, provado, hoje=HOJE, agora=AGORA)
    entregar_com_comprovante(con, aviso["aviso_id"], agora=AGORA, pasta=pasta())

    a_mao = titulo(con, "7002/1")
    PT.lancar_intimacao(con, a_mao, modo="PESSOAL", agora=AGORA)
    edital, _ = _por_edital(con, "7003/1")
    digital = titulo(con, "7004/1")
    PT.lancar_intimacao(con, digital, modo="PESSOAL", digital=True, agora=AGORA)

    linhas = {x["titulo_id"]: x for x in PROVA.intimacoes_sem_prova(con, hoje=HOJE)}
    assert set(linhas) == {a_mao, edital, digital}
    assert "lançada à mão" in linhas[a_mao]["explicacao"]
    assert "envio do arquivo dos editais" in linhas[edital]["explicacao"]
    assert linhas[edital]["numero_titulo"] == "7003/1"
    assert linhas[digital]["modo"] == "DIGITAL"
    for x in linhas.values():
        assert set(x) >= {"titulo_id", "numero_titulo", "protocolo",
                          "explicacao", "onde", "origem"}
        assert x["origem"] == "SISTEMA"

    # sem `hoje`, vale o dia de hoje — e a lista não muda por isso
    assert {x["titulo_id"] for x in PROVA.intimacoes_sem_prova(con)} == set(linhas)


def test_intimacoes_sem_prova_marca_o_acervo_do_eoficio(con):
    """O papel da intimação do E-Ofício é do arquivo do E-Ofício: ela sai com
    `origem = "ACERVO"`, que o roteiro deixa de fora (o acervo não vira
    atraso)."""
    tid = titulo(con)
    r = PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA,
                            origem="EOFICIO")
    assert r["ato_id"]
    [linha] = PROVA.intimacoes_sem_prova(con, hoje=HOJE)
    assert linha["titulo_id"] == tid and linha["origem"] == "ACERVO"


def test_titulo_que_nao_esta_intimado_nao_entra_na_pendencia(con):
    titulo(con)                                   # só apontado
    assert PROVA.intimacoes_sem_prova(con, hoje=HOJE) == []


# --------------------------- quem recebeu, completado depois (29/10/2026)


def test_sem_o_nome_de_quem_recebeu_a_prova_diz_onde_completar(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    AV.registrar_entrega(con, aviso["aviso_id"], entregue=True, agora=AGORA,
                         comprovante_nome="canhoto.pdf",
                         comprovante_conteudo=PDF_DE_TESTE,
                         pasta_de_arquivos=pasta(), afirmacao=AFIRMACAO)
    prova = PROVA.conferir(con, tid, hoje=HOJE)
    assert not prova["completa"] and prova["falta_quem_recebeu"]
    assert prova["aviso_id"] == aviso["aviso_id"]
    assert "falta o nome de quem recebeu" in prova["frase"]
    assert "Completar quem recebeu" in prova["frase"]

    tarefa = AV.tarefa_para_completar(con, aviso["aviso_id"], hoje=HOJE, dono=7)
    assert tarefa["source_type"] == AV.TAREFA_SEM_RECEBEDOR
    assert tarefa["source_ref"] == f"pt_avisos:{aviso['aviso_id']}"
    assert tarefa["assigned_user_id"] == 7 and tarefa["sector"] == "PROTESTO"

    r = AV.completar_quem_recebeu(con, aviso["aviso_id"],
                                  recebido_por="  MARIA   EXEMPLO ", agora=AGORA)
    assert r["recebido_por"] == "MARIA EXEMPLO" and r["antes"] is None
    assert AV.tarefa_para_completar(con, aviso["aviso_id"], hoje=HOJE,
                                    dono=7) is None
    assert PROVA.conferir(con, tid, hoje=HOJE)["completa"]
    protestar(con, tid)                           # sem afirmação
    assert len(protestos(con, tid)) == 1


def test_completar_quem_recebeu_recusa_o_que_nao_cabe(con):
    tid = titulo(con)
    aviso = AV.emitir(con, tid, hoje=HOJE, agora=AGORA)
    with pytest.raises(AV.AvisoError, match="aviso ENTREGUE"):
        AV.completar_quem_recebeu(con, aviso["aviso_id"],
                                  recebido_por="MARIA EXEMPLO", agora=AGORA)
    entregar_com_comprovante(con, aviso["aviso_id"], agora=AGORA, pasta=pasta(),
                             recebido_por="MARIA EXEMPLO")
    with pytest.raises(AV.AvisoError, match="Escreva o nome"):
        AV.completar_quem_recebeu(con, aviso["aviso_id"], recebido_por=" a ",
                                  agora=AGORA)
    with pytest.raises(AV.AvisoError, match="já diz que quem recebeu"):
        AV.completar_quem_recebeu(con, aviso["aviso_id"],
                                  recebido_por="maria exemplo", agora=AGORA)
    with pytest.raises(AV.AvisoError, match="exige afirmação expressa"):
        AV.completar_quem_recebeu(con, aviso["aviso_id"],
                                  recebido_por="JOSÉ EXEMPLO", agora=AGORA)
    r = AV.completar_quem_recebeu(con, aviso["aviso_id"],
                                  recebido_por="JOSÉ EXEMPLO", agora=AGORA,
                                  afirmacao=AFIRMACAO)
    assert r["antes"] == "MARIA EXEMPLO"
    assert [x["regra"] for x in r["afirmacoes"]] == ["CORRECAO_DE_QUEM_RECEBEU"]


# ------------------------------------------------- quem pede a afirmação


def test_as_rotas_que_protestam_passam_a_afirmacao_do_formulario():
    """A trava é do domínio, sem chave para desligar; o que as rotas têm de
    fazer é levar a afirmação do formulário — sem ela, o balcão não teria como
    vencer a trava nem quando tem razão."""
    chamadas = 0
    for arquivo in RAIZ.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        if "lancar_protesto(" not in texto or arquivo.name == "protesto.py":
            continue
        for no in ast.walk(ast.parse(texto)):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "lancar_protesto"):
                chamadas += 1
                kw = {k.arg for k in no.keywords}
                assert "afirmacao" in kw, f"{arquivo.name}:{no.lineno}"
    assert chamadas >= 2


def test_a_entrega_de_producao_leva_o_comprovante_no_mesmo_ato():
    """Todo caminho de produção que registra a entrega manda o arquivo junto
    — a tela, o PDF com várias intimações e o AR dos Correios."""
    vistos = set()
    for arquivo in RAIZ.glob("*.py"):
        texto = arquivo.read_text(encoding="utf-8")
        if "registrar_entrega(" not in texto or arquivo.name == "protesto_aviso.py":
            continue
        for no in ast.walk(ast.parse(texto)):
            if (isinstance(no, ast.Call) and isinstance(no.func, ast.Attribute)
                    and no.func.attr == "registrar_entrega"
                    and isinstance(no.func.value, ast.Name)
                    and no.func.value.id == "AV"):
                kw = {k.arg for k in no.keywords}
                assert {"comprovante_conteudo", "comprovante_nome"} <= kw, \
                    f"{arquivo.name}:{no.lineno}"
                vistos.add(arquivo.name)
    assert {"atribuicoes_web.py", "protesto_intimacoes_lote.py",
            "protesto_ar.py"} <= vistos
