"""O agente das Notas: as regras, a revisão da minuta e o encaixe no gestor.

O QUE ESTES TESTES GUARDAM
    **Que banco sem nada não vira alarme.** Instalação nova não tem ato de
    Notas, e regra que acusa banco vazio é o alarme que soa sempre.

    **Que cada caso medido na produção em 09/10/2026 é pego** — o divórcio sem
    o tipo da CESDI (778), o termo 200 abaixo do contador, o rascunho com as
    mesmas partes de uma procuração já lavrada (787), a minuta com claro e
    destaque amarelo (786).

    **Que o agente não lança, não sela, não cobra, não apaga e não envia.**
    Código de Normas TJMA, arts. 169, IV e 171: a IA assiste na redação e na
    revisão; quem lavra é gente.
"""
from __future__ import annotations

import sqlite3
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_notas as AN                                        # noqa: E402
import gestor_conferencia as GC                                  # noqa: E402
import gestor_rotina as GR                                       # noqa: E402

AGORA = "2026-10-09T08:00:00"
HOJE = date(2026, 10, 9)


@pytest.fixture()
def con(cg_casa):
    c = sqlite3.connect(cg_casa["banco"])
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _livro(con, tipo="ESCRITURA", numero="30", folha_atual=194, ativo=1):
    return int(con.execute(
        """INSERT INTO nt_livros (tipo, numero, folhas, folha_atual, encerrado, ativo,
               criado_em) VALUES (?,?,300,?,0,?,?)""",
        (tipo, numero, folha_atual, ativo, AGORA)).lastrowid)


def _ato(con, **campos):
    base = {"tipo": "ESCRITURA", "data": "2026-09-17", "situacao": "LAVRADO",
            "origem": "MANUAL", "criado_em": AGORA}
    base.update(campos)
    nomes = ",".join(base)
    marcas = ",".join("?" * len(base))
    return int(con.execute(f"INSERT INTO nt_atos ({nomes}) VALUES ({marcas})",
                           tuple(base.values())).lastrowid)


def _parte(con, ato_id, nome, documento, qualificacao=None, **extra):
    campos = {"ato_id": ato_id, "nome": nome, "documento": documento,
              "qualificacao": qualificacao, "criado_em": AGORA}
    campos.update(extra)
    con.execute(f"INSERT INTO nt_ato_partes ({','.join(campos)}) "
                f"VALUES ({','.join('?' * len(campos))})", tuple(campos.values()))


def _regra(achados, nome):
    return [a for a in achados if a["regra"] == nome]


# CPFs que fecham o dígito verificador.
CPF_A = "52998224725"
CPF_B = "11144477735"
CPF_C = "39053344705"


# ------------------------------------------------------------ banco vazio

def test_banco_sem_ato_de_notas_nao_acusa_nada(con):
    assert AN.conferir(con, HOJE) == []


def test_regra_que_quebra_vira_nao_mediu_com_o_nome_dela(con, monkeypatch):
    def quebra(con, hoje):
        raise RuntimeError("coluna sumiu")
    monkeypatch.setattr(AN, "REGRAS", (("NOTAS_LIVRO", quebra),
                                       ("NOTAS_ANOTACAO", AN.regra_anotacao_a_margem)))
    achados = AN.conferir(con, HOJE)
    assert [a["regra"] for a in achados] == ["NOTAS_LIVRO"]
    assert achados[0]["gravidade"] == "NAO_MEDIU"
    assert "coluna sumiu" in achados[0]["detalhe"]


# ------------------------------------------------------------ CENSEC

def test_divorcio_sem_tipo_da_cesdi_vai_a_central_errada(con):
    livro = _livro(con)
    ato = _ato(con, livro_id=livro, livro="30", folha="193", termo=5522,
               natureza="Escritura pública de divórcio consensual direto",
               lancado_em="2026-09-18T09:37:51")
    _parte(con, ato, "SONIA", CPF_A, "Divorcianda")
    _parte(con, ato, "EGNALDO", CPF_B, "Divorciando")
    achados = _regra(AN.regra_censec_por_ato(con, HOJE), "NOTAS_CENSEC")
    assert len(achados) == 1
    a = achados[0]
    assert a["chave"] == f"NOTAS_CENSEC:nt_atos:{ato}:CESDI"
    assert "tipo da CESDI" in a["detalhe"]
    assert a["gravidade"] == "VENCIDO"          # 2ª quinzena de setembro: prazo 05/10
    assert a["setor"] == AN.SETOR_QUALIFICACAO


def test_procuracao_com_parte_sem_qualificacao_conta_uma_vez(con):
    livro = _livro(con, tipo="PROCURACAO", numero="28")
    ato = _ato(con, tipo="PROCURACAO", data="2026-10-08", livro_id=livro, livro="28",
               folha="46", termo=5288, natureza="Procuração pública",
               lancado_em="2026-10-08T09:42:33")
    _parte(con, ato, "A", CPF_A)
    _parte(con, ato, "B", CPF_B)
    _parte(con, ato, "C", CPF_C, "OUTORGANTE")
    a = _regra(AN.regra_censec_por_ato(con, HOJE), "NOTAS_CENSEC")[0]
    assert a["gravidade"] == "PRAZO"            # 1ª quinzena de outubro: prazo 20/10
    assert "(2 partes)" in a["detalhe"]
    assert a["detalhe"].count("parte sem qualificação") == 1


def test_ato_antes_do_corte_nao_vira_cobranca_da_censec(con):
    _ato(con, tipo="PROCURACAO", data="2026-09-01", livro="28", folha="1",
         lancado_em="2026-09-01T10:00:00")
    assert AN.regra_censec_por_ato(con, HOJE) == []


# ------------------------------------------------------------ livro

def test_termo_do_contador_acima_do_ultimo_ato_do_sistema(con):
    livro = _livro(con)
    ato = _ato(con, livro_id=livro, livro="30", folha="193", folha_inicial_num=193,
               folha_final_num=193, termo=5522, serie="ESCRITURA",
               lancado_em="2026-09-18T09:37:51")
    con.execute("""INSERT INTO nt_termos (serie, proximo, maior_em_uso, fixado_em,
                       fixado_por) VALUES ('ESCRITURA', 5723, 5722, ?, 'oficial')""",
                (AGORA,))
    achados = _regra(AN.regra_livros(con, HOJE), "NOTAS_LIVRO")
    assert len(achados) == 1
    assert achados[0]["chave"] == f"NOTAS_LIVRO:nt_atos:{ato}:CONTADOR:ESCRITURA"
    assert "5523 a 5722 (200)" in achados[0]["detalhe"]


def test_dois_atos_na_mesma_folha_e_critico(con):
    livro = _livro(con)
    a1 = _ato(con, livro_id=livro, livro="30", folha="193", folha_inicial_num=193,
              folha_final_num=193, termo=1, serie="ESCRITURA",
              lancado_em="2026-09-18T09:00:00")
    a2 = _ato(con, livro_id=livro, livro="30", folha="192", folha_inicial_num=192,
              folha_final_num=193, termo=2, serie="ESCRITURA",
              lancado_em="2026-09-19T09:00:00")
    achados = [a for a in AN.regra_livros(con, HOJE) if ":FOLHA:" in a["chave"]]
    assert len(achados) == 1
    assert achados[0]["gravidade"] == "CRITICO"
    assert str(a1) in achados[0]["titulo"] and str(a2) in achados[0]["titulo"]


def test_livro_desativado_nao_conta_como_segundo_aberto(con):
    _livro(con, tipo="PROCURACAO", numero="28", folha_atual=48)
    _livro(con, tipo="PROCURACAO", numero="1", folha_atual=4, ativo=0)
    assert [a for a in AN.regra_livros(con, HOJE) if "DOIS_ABERTOS" in a["chave"]] == []
    _livro(con, tipo="PROCURACAO", numero="2", folha_atual=1)
    dois = [a for a in AN.regra_livros(con, HOJE) if "DOIS_ABERTOS" in a["chave"]]
    assert len(dois) == 1 and "788" in dois[0]["fundamento"]


# ------------------------------------------------------------ anotação à margem

def test_revogacao_sem_anotacao_no_ato_desta_casa(con):
    procuracao = _ato(con, tipo="PROCURACAO", data="2026-09-15", livro="28", folha="40")
    revogacao = _ato(con, tipo="REVOGACAO", data="2026-10-01", livro="28", folha="41",
                     anterior_ato_id=procuracao)
    achado = _regra(AN.regra_anotacao_a_margem(con, HOJE), "NOTAS_ANOTACAO")
    assert len(achado) == 1 and achado[0]["gravidade"] == "VENCIDO"
    con.execute("""INSERT INTO nt_ato_anotacoes (ato_id, data, tipo, texto,
                       ato_relacionado_id, criado_em) VALUES (?,?,?,?,?,?)""",
                (procuracao, "2026-10-01", "REVOGACAO", "Revogada.", revogacao, AGORA))
    assert AN.regra_anotacao_a_margem(con, HOJE) == []


# ------------------------------------------------------------ escritura de imóvel

def test_escritura_de_imovel_lavrada_sem_cnib_e_critica(con):
    ato = _ato(con, natureza="Escritura pública de compra e venda de imóvel urbano",
               com_imovel=1, livro="30", folha="195", lancado_em="2026-09-20T10:00:00",
               teor="<p>Certifico o pagamento do imposto de transmissão ITBI. "
                    "Emitida a DOI.</p>")
    a = _regra(AN.regra_escritura_de_imovel(con, HOJE), "NOTAS_IMOVEL")[0]
    assert a["gravidade"] == "CRITICO" and "CNIB" in a["detalhe"]
    con.execute("UPDATE nt_atos SET teor = teor || ? WHERE id = ?",
                ("<p>Consulta à CNIB negativa, hash ABC123.</p>", ato))
    assert AN.regra_escritura_de_imovel(con, HOJE) == []


# ------------------------------------------------------------ minuta e rascunho

def test_minuta_com_claro_destaque_e_cnib_em_branco(con):
    ato = _ato(con, situacao="EM_LAVRATURA", data="2026-09-29", com_imovel=1,
               natureza="Escritura pública de inventário, partilha e cessão",
               valor_transacao=17702479,
               teor=("<p>Herdeiros declaram inexistência de testamento, certidão RCTO. "
                     "CNIB em nome dos cedentes, com resultado a ser consignado: _ </p>"
                     "<p><span style='background-color: yellow'>data efetiva</span> "
                     "ITBI pago. DOI será emitida.</p>" + "x" * 200))
    _parte(con, ato, "RAFAEL", CPF_A, "INVENTARIANTE E CESSIONÁRIO")
    _parte(con, ato, "LEONAN", CPF_B, "ADVOGADO ASSISTENTE")
    itens = [i["item"] for i in AN.revisar_minuta(con, ato)]
    assert any("dois-pontos" in i for i in itens)
    assert any("amarelo" in i for i in itens)
    assert any("CNIB está em branco" in i for i in itens)
    assert any("tipo de ato da CESDI" in i for i in itens)
    assert not any("advogado" in i for i in itens)
    assert _regra(AN.regra_minutas(con, HOJE), "NOTAS_MINUTA")


def test_traco_de_assinatura_nao_e_claro(con):
    assert AN._claros_no_texto("<p>__________________________</p><p>FULANO</p>") == []


def test_rascunho_com_as_partes_de_procuracao_lavrada(con):
    rascunho = _ato(con, tipo="PROCURACAO", situacao="EM_LAVRATURA", data="2026-10-02")
    _parte(con, rascunho, "DEUSDETE", CPF_A)
    _parte(con, rascunho, "ANTONIO", CPF_B)
    lavrada = _ato(con, tipo="PROCURACAO", data="2026-10-08", livro="28", folha="46")
    for nome, doc in (("ANTONIO", CPF_B), ("ALZENIRA", CPF_C), ("DEUSDETE", CPF_A)):
        _parte(con, lavrada, nome, doc)
    a = _regra(AN.regra_rascunhos(con, HOJE), "NOTAS_RASCUNHO")[0]
    assert f"procuração {lavrada}" in a["titulo"]
    assert a["titulo"].startswith("Procuração ")
    assert "NOTAS_RASCUNHO" in AN.REGRAS_SEM_TAREFA


def test_rascunho_vazio_de_ontem_ainda_nao_e_achado(con):
    _ato(con, tipo="PROCURACAO", situacao="EM_LAVRATURA", data="2026-10-08")
    assert AN.regra_rascunhos(con, HOJE) == []
    assert len(AN.regra_rascunhos(con, date(2026, 10, 12))) == 1


# ------------------------------------------------------------ o encaixe

def test_a_conferencia_do_gestor_traz_as_regras_das_notas(con):
    _ato(con, natureza="Escritura pública de divórcio consensual direto",
         livro="30", folha="193", lancado_em="2026-09-18T09:37:51")
    achados = GC.conferir(con, HOJE)
    assert _regra(achados, "NOTAS_CENSEC")
    assert "NOTAS_CENSEC" in GR.ROTULOS
    assert AN.REGRAS_SEM_TAREFA <= GR.REGRAS_SEM_TAREFA


def test_relatorio_sai_com_as_secoes(con, tmp_path):
    _ato(con, situacao="EM_LAVRATURA", data="2026-09-29", teor="<p>" + "x" * 300 + "</p>")
    caminho = AN.escrever_relatorio(con, HOJE, tmp_path)
    texto = caminho.read_text(encoding="utf-8")
    for secao in ("O que a conferência achou", "Minutas em lavratura", "Livros abertos",
                  "CENSEC por quinzena"):
        assert secao in texto


def test_o_agente_nao_lanca_nao_sela_nao_cobra_nao_apaga_nao_envia():
    proibidos = ("lancar", "lavrar", "selar", "cobrar", "apagar", "enviar", "excluir",
                 "cancelar", "gerar_remessa")
    publicos = [n for n in dir(AN) if not n.startswith("_") and callable(getattr(AN, n))]
    assert not [n for n in publicos if any(p in n.lower() for p in proibidos)]
    fonte = (RAIZ / "agente_notas.py").read_text(encoding="utf-8")
    for verbo in ("INSERT", "UPDATE", "DELETE"):
        assert f"{verbo} INTO" not in fonte and f"{verbo} nt_" not in fonte \
            and f"{verbo} FROM" not in fonte
