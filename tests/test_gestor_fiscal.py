"""O agente financeiro e das gratuidades (`gestor_fiscal`) — pedido do oficial em 09/10/2026.

O que se prova aqui: a resposta do Portal do Selo é lida na forma medida em
09/10/2026 (isento deferido, cancelado, indeferido, selo inexistente = HTTP
400); a fila de consulta respeita o corte, o teto e a prioridade, e não pergunta
duas vezes no mesmo dia; a conferência aponta o selo que o TJ não conhece, o
cancelado de um lado só, o valor e a isenção divergentes, a gratuidade
indeferida com prazo e a em análise por mês; o saldo do aparelho mede o preço
do selo no próprio período e acusa o que saiu por fora; e `conferir` não grava.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from datetime import date
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import gestor_conferencia as GC  # noqa: E402
import gestor_fiscal as GF  # noqa: E402
import gestor_rotina as GR  # noqa: E402
from gestor_schema import init_gestor_schema  # noqa: E402
from selador_config import init_selador_schema  # noqa: E402

HOJE = date(2026, 10, 9)


def _banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_selador_schema(con)
    init_gestor_schema(con)
    return con


def _texto(numero, total="43,37", isento=False):
    return (f"Poder Judiciário – TJMA. Selo: {numero}, 10/09/2026 08:48:55, Ato: 14.4.1, "
            f"Total R$ {total} Emol R$ 38,72 FERC R$ 1,16 FADEP R$ 1,55 FEMP R$ 1,55 "
            f"FERRFIS R$ 0,39{' Selo Isento' if isento else ''}, Consulte em https://selo.tjma.jus.br")


def _selo(con, n, *, obtido="2026-09-15T10:00:00", tabela="rc_atos", ato_id=None,
          isento=False, total="43,37", saldo=None, cancelado_em=None, ambiente="PRODUCAO"):
    numero = f"AVERBA000000{n:016d}"
    con.execute(
        """INSERT INTO sd_selos (numero, texto, atribuicao, tabela, ato_id, saldo_remanescente,
                                 ambiente, obtido_em, obtido_por, usado_em, cancelado_em,
                                 motivo_cancelamento)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, _texto(numero, total, isento), "RCPN", tabela, ato_id or n, saldo, ambiente,
         obtido, "Escrevente Teste", obtido if tabela else None, cancelado_em,
         "cancelado no balcão" if cancelado_em else None))
    return numero


def _resposta(numero, *, isento=False, cancelado=False, deferido=None, indeferido=None,
              valor=43.37, motivo="ART. 347 DO CODIGO DE NORMAS DO TJMA", prazo=None,
              indef_motivo=None):
    """A forma medida em 09/10/2026 em `/portal-cidadao/selos/consulta/<selo>`."""
    return json.dumps({"selo": {
        "codSelo": numero, "codigoAto": "14.4.1", "dataSelo": "2026-09-10", "horaSelo": "08:48",
        "codAtoTabelaAto": {"codigoAto": "14.4.1", "emolumento": 38.72, "valorSelo": 0 if isento else 0.45,
                            "valorAto": valor},
        "escrevente": "Escrevente Teste",
        "infoIsento": {"isento": isento, "motivoGratuitoIsento": motivo if isento else None},
        "cancelado": cancelado, "dataCancelado": "2026-10-09" if cancelado else None,
        "deferido": deferido, "indeferido": indeferido, "motivoIndeferimento": indef_motivo,
        "prazoMaximoParaRecorrer": prazo}, "numeroSelo": numero}, ensure_ascii=False)


def _gravar(con, numero, status, corpo, quando="2026-10-08T07:30:00"):
    linha = GF.ler_resposta(numero, status, corpo)
    linha["consultado_em"] = quando
    cols = list(linha)
    con.execute(f"INSERT OR REPLACE INTO ge_portal_selos ({', '.join(cols)}) "
                f"VALUES ({', '.join('?' * len(cols))})", [linha[c] for c in cols])


def _regras(achados) -> dict:
    saida: dict = {}
    for a in achados:
        saida.setdefault(a["regra"], []).append(a)
    return saida


# ------------------------------------------------------- a resposta do portal

def test_isento_deferido_e_gratuidade_comprovada():
    n = "AVERBA000000ROMJEB4E13BWJ271"
    r = GF.ler_resposta(n, 200, _resposta(n, isento=True, deferido=True, indeferido=False))
    assert r["situacao"] == "ACHADO" and r["isento"] == 1 and r["cancelado"] == 0
    assert r["analise"] == "DEFERIDA"
    assert r["motivo_isencao"].startswith("ART. 347")
    assert r["valor_ato"] == 43.37 and r["codigo_ato"] == "14.4.1"


def test_selo_inexistente_e_http_400_invalido():
    corpo = ("<ExceptionMessage><status>400</status><message>Dados de entrada inválidos."
             "</message><details>O selo informado no campo \"txSelo\" é inválido</details>")
    r = GF.ler_resposta("AVERBA000000ZZZZZZZZZZZZZZZZ", 400, corpo)
    assert r["situacao"] == "NAO_ACHADO"


def test_isento_cancelado_nao_fica_em_analise():
    n = "AVERBA000000IL2UFB45KLXKLQ12"
    r = GF.ler_resposta(n, 200, _resposta(n, isento=True, cancelado=True,
                                          deferido=False, indeferido=False))
    assert r["analise"] == "CANCELADA" and r["cancelado"] == 1


def test_indeferido_e_em_analise_e_pago():
    n = "AVERBA0000000000000000000001"
    assert GF.ler_resposta(n, 200, _resposta(n, isento=True, indeferido=True))["analise"] == "INDEFERIDA"
    assert GF.ler_resposta(n, 200, _resposta(n, isento=True, deferido=False,
                                             indeferido=False))["analise"] == "EM_ANALISE"
    assert GF.ler_resposta(n, 200, _resposta(n))["analise"] is None


def test_erro_nao_vira_achado():
    n = "AVERBA0000000000000000000001"
    assert GF.ler_resposta(n, 500, "x")["situacao"] == "ERRO"
    assert GF.ler_resposta(n, 200, "não é json")["situacao"] == "ERRO"
    outro = GF.ler_resposta(n, 200, _resposta("AVERBA0000000000000000000002"))
    assert outro["situacao"] == "ERRO" and "outro selo" in outro["erro"]


# ---------------------------------------------------------- a consulta

def test_consulta_respeita_corte_ambiente_teto_e_espera():
    con = _banco()
    antes = _selo(con, 1, obtido="2026-09-01T10:00:00")
    homolog = _selo(con, 2, ambiente="HOMOLOGACAO")
    novos = [_selo(con, 10 + i, obtido=f"2026-09-2{i}T10:00:00") for i in range(4)]
    pedidos, dormidas = [], []

    def buscar(numero):
        pedidos.append(numero)
        return 200, _resposta(numero)

    feito = GF.consultar_portal(con, HOJE, teto=3, espera=1.5, buscar=buscar,
                                dormir=dormidas.append)
    assert feito["na_fila"] == 4 and feito["consultados"] == 3
    assert antes not in pedidos and homolog not in pedidos
    assert pedidos == novos[:3]                       # o mais antigo primeiro
    assert dormidas == [1.5, 1.5]                     # entre pedidos, não antes do primeiro
    # No mesmo dia, o que já foi consultado não volta à fila.
    pedidos.clear()
    GF.consultar_portal(con, HOJE, buscar=buscar, dormir=lambda s: None)
    assert pedidos == [novos[3]]


def test_reconsulta_o_que_pode_mudar():
    con = _banco()
    analise = _selo(con, 1, isento=True)
    deferido = _selo(con, 2, isento=True)
    _gravar(con, analise, 200, _resposta(analise, isento=True, deferido=False, indeferido=False))
    _gravar(con, deferido, 200, _resposta(deferido, isento=True, deferido=True))
    assert GF._a_consultar(con, HOJE) == [analise]


def test_queda_de_rede_grava_erro_e_segue():
    con = _banco()
    a, b = _selo(con, 1), _selo(con, 2, obtido="2026-09-16T10:00:00")

    def buscar(numero):
        if numero == a:
            raise OSError("sem rede")
        return 200, _resposta(numero)

    feito = GF.consultar_portal(con, HOJE, buscar=buscar, dormir=lambda s: None)
    assert feito["ERRO"] == 1 and feito["ACHADO"] == 1
    assert con.execute("SELECT erro FROM ge_portal_selos WHERE numero=?", (a,)).fetchone()[0] \
        .startswith("OSError")
    assert b


# ---------------------------------------------------------- a conferência

def test_selo_que_o_tj_nao_conhece_vira_critico_so_depois_do_prazo():
    con = _banco()
    velho = _selo(con, 1, obtido="2026-10-01T10:00:00")
    novo = _selo(con, 2, obtido="2026-10-09T09:00:00")
    for n in (velho, novo):
        _gravar(con, n, 400, "O selo informado é inválido")
    r = _regras(GF.conferir(con, HOJE))
    fora = r["FISCAL_SELO_FORA_DO_PORTAL"]
    assert [a["chave"] for a in fora] == [f"FISCAL_FORA:{velho}"]
    assert fora[0]["gravidade"] == "CRITICO" and fora[0]["setor"] == "RCPN"


def test_cancelado_de_um_lado_so():
    con = _banco()
    no_tj = _selo(con, 1)
    aqui = _selo(con, 2, cancelado_em="2026-09-20T10:00:00")
    _gravar(con, no_tj, 200, _resposta(no_tj, cancelado=True))
    _gravar(con, aqui, 200, _resposta(aqui))
    r = _regras(GF.conferir(con, HOJE))
    assert r["FISCAL_CANCELADO_NO_PORTAL"][0]["chave"].endswith(no_tj)
    assert r["FISCAL_CANCELADO_SO_NO_SISTEMA"][0]["chave"].endswith(aqui)
    assert r["FISCAL_CANCELADO_SO_NO_SISTEMA"][0]["gravidade"] == "ATENCAO"


def test_valor_e_isencao_divergentes():
    con = _banco()
    valor = _selo(con, 1, total="53,58")
    isencao = _selo(con, 2, isento=False)
    _gravar(con, valor, 200, _resposta(valor, valor=43.37))
    _gravar(con, isencao, 200, _resposta(isencao, isento=True, deferido=True))
    r = _regras(GF.conferir(con, HOJE))
    assert r["FISCAL_VALOR_DIVERGENTE"][0]["chave"].endswith(valor)
    assert "53,58" in r["FISCAL_VALOR_DIVERGENTE"][0]["titulo"]
    assert r["FISCAL_ISENCAO_DIVERGENTE"][0]["chave"].endswith(isencao)


def test_gratuidade_indeferida_vai_para_o_oficial_com_prazo():
    con = _banco()
    n = _selo(con, 1, isento=True)
    _gravar(con, n, 200, _resposta(n, isento=True, indeferido=True, prazo="2026-10-20",
                                   indef_motivo="Motivo não enquadrado"))
    a = _regras(GF.conferir(con, HOJE))["FISCAL_GRATUIDADE_INDEFERIDA"][0]
    assert a["setor"] == "GESTAO" and a["gravidade"] == "PRAZO" and a["prazo"] == "2026-10-20"
    assert "Motivo não enquadrado" in a["detalhe"]
    # Prazo vencido: a gravidade sobe — já não há recurso, há recolhimento.
    _gravar(con, n, 200, _resposta(n, isento=True, indeferido=True, prazo="01/10/2026"))
    assert _regras(GF.conferir(con, HOJE))["FISCAL_GRATUIDADE_INDEFERIDA"][0]["gravidade"] == "CRITICO"


def test_em_analise_e_um_achado_por_mes_com_o_valor():
    con = _banco()
    for i, dia in enumerate(("2026-09-15", "2026-09-16", "2026-10-02")):
        n = _selo(con, i + 1, isento=True, obtido=f"{dia}T10:00:00")
        _gravar(con, n, 200, _resposta(n, isento=True, deferido=False, indeferido=False))
    r = _regras(GF.conferir(con, HOJE))["FISCAL_GRATUIDADE_EM_ANALISE"]
    assert [a["chave"] for a in r] == ["FISCAL_ANALISE:2026-09", "FISCAL_ANALISE:2026-10"]
    assert r[0]["titulo"].startswith("2 gratuidade(s)") and "86,74" in r[0]["titulo"]


def test_selo_sem_resposta_e_nao_mediu_e_nao_zero():
    con = _banco()
    _selo(con, 1, obtido="2026-10-01T10:00:00")
    _selo(con, 2, obtido="2026-10-09T10:00:00")       # de hoje: ainda não se cobra
    a = _regras(GF.conferir(con, HOJE))["FISCAL_PORTAL_SEM_RESPOSTA"][0]
    assert a["gravidade"] == "NAO_MEDIU" and a["titulo"].startswith("1 selo(s)")


def test_conferir_nao_grava():
    con = _banco()
    n = _selo(con, 1)
    _gravar(con, n, 400, "inválido")
    con.commit()
    antes = con.total_changes
    GF.conferir(con, HOJE)
    assert con.total_changes == antes


# ---------------------------------------------------------- o saldo

def _sequencia(con, saldos_e_isencao, dia="2026-09-20"):
    for i, (saldo, isento) in enumerate(saldos_e_isencao):
        _selo(con, 100 + i, obtido=f"{dia}T10:{i:02d}:00", saldo=saldo, isento=isento)


def test_saldo_mede_o_preco_e_acusa_o_que_saiu_por_fora():
    con = _banco()
    saldos, s = [], 100.0
    for i in range(14):
        isento = i in (3, 7)
        s = round(s - (0 if isento else 0.45), 2)
        if i == 10:
            s = round(s - 0.90, 2)                    # dois selos tirados por fora
        saldos.append((s, isento))
    _sequencia(con, saldos)
    for i in range(12):                              # isentos bastantes para medir a classe
        _selo(con, 300 + i, obtido=f"2026-09-21T10:{i:02d}:00", saldo=s, isento=True)
    r = GF.saldo_do_aparelho(con, GC.IMPLANTACAO)
    assert r["nao_mediu"] is None
    assert r["custo"] == {"pago": 0.45, "isento": 0.0}
    assert r["dias"] == {"2026-09-20": {"selos": 2, "valor": 0.9}}
    a = _regras(GF.conferir(con, HOJE))["FISCAL_SELOS_FORA_DO_SISTEMA"][0]
    assert a["chave"] == "FISCAL_FORA_DO_SISTEMA:2026-09" and a["titulo"].startswith("2 selo(s)")


def test_recarga_nao_conta_e_classe_sem_preco_fica_de_fora():
    con = _banco()
    saldos = [(round(50 - 0.45 * i, 2), False) for i in range(12)]
    saldos.append((200.0, False))                     # recarga
    saldos.append((199.55, True))                    # um isento solto: não se mede
    _sequencia(con, saldos)
    r = GF.saldo_do_aparelho(con, GC.IMPLANTACAO)
    assert len(r["recargas"]) == 1 and r["dias"] == {}
    assert "isento" in r["fora_da_conta"]


def test_saldo_sem_pares_bastantes_e_nao_mediu():
    con = _banco()
    _sequencia(con, [(10.0, False), (9.55, False), (9.10, False)])
    a = _regras(GF.conferir(con, HOJE))["FISCAL_SELOS_FORA_DO_SISTEMA"][0]
    assert a["gravidade"] == "NAO_MEDIU"


# ------------------------------------------------- o gestor e o relatório

def test_o_gestor_conhece_o_agente():
    assert ("FISCAL", GC.regra_fiscal) in GC.REGRAS
    for regra in GF.ROTULOS:
        assert GR.ROTULOS[regra] == GF.ROTULOS[regra]
    com_tarefa = {"FISCAL_SELO_FORA_DO_PORTAL", "FISCAL_CANCELADO_NO_PORTAL",
                  "FISCAL_GRATUIDADE_INDEFERIDA"}
    assert not com_tarefa & GR.REGRAS_SEM_TAREFA
    assert GF.REGRAS_SEM_TAREFA <= GR.REGRAS_SEM_TAREFA
    assert set(GF.ROTULOS) == GF.REGRAS_SEM_TAREFA | com_tarefa


def test_relatorio_do_mes(tmp_path):
    con = _banco()
    n = _selo(con, 1, isento=True)
    _gravar(con, n, 200, _resposta(n, isento=True, indeferido=True, prazo="2026-10-20",
                                   motivo="<script>x</script>"))
    caminhos = GF.escrever_relatorio(con, HOJE, tmp_path)
    assert [c.name for c in caminhos] == ["fiscal_2026-09.html", "fiscal_2026-10.html"]
    texto = caminhos[0].read_text(encoding="utf-8")
    assert "Gratuidades" in texto and "INDEFERIDA" in texto and n in texto
    assert "<script>x</script>" not in texto and "&lt;script&gt;" in texto
