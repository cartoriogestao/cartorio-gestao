"""OS LIVROS OBRIGATÓRIOS DO CÓDIGO DE NORMAS DO MA (LG08, 19/10/2026).

O QUE SE PROVA AQUI
    - o catálogo (`livros_obrigatorios`) não aponta para série que não existe,
      e os cinco livros do Tabelionato de Notas (art. 788) são séries próprias,
      com numeração contínua por espécie de um livro para o outro (art. 792);
    - o Livro de Visitas e Correições (art. 189) numera em sequência, não
      registra visita no futuro e só se corrige por retificação, que não apaga
      o lançamento antigo;
    - o Livro Diário Auxiliar (arts. 190 a 207) tira a receita do SELO usado
      no dia — emolumento é receita, fundo não; isento, diferido, cancelado e
      homologação não somam —, lança e anula despesa sem apagar, e gerar o mês
      grava uma fotografia que só se refaz com retificação circunstanciada;
    - o Livro de Controle de Depósito Prévio (art. 198) lê o cadastro e o
      rastro, e diz o que falta em cada depósito;
    - os prazos dos arts. 205 e 207 entram na agenda do oficial em dia útil.

Sem o `create_app`: o banco é um `Database` solto, com o esquema da casa.
Equipe, depositantes e partes fictícios. Nada de dado real de pessoa.
"""
from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import atribuicoes as ATR                    # noqa: E402
import custas                                # noqa: E402
import livro_deposito_previo as LDP          # noqa: E402
import livro_diario as LD                    # noqa: E402
import livro_nucleo as LN                    # noqa: E402
import livro_visitas as LV                   # noqa: E402
import livros_obrigatorios as LO             # noqa: E402
import notas_livro as NL                     # noqa: E402
import oficial_obrigacoes as OO              # noqa: E402
from bd_nativo import banco                  # noqa: E402
from database import Database                # noqa: E402

HOJE = "2026-10-19"
AGORA = "2026-10-19T10:00:00"
POR = "OFICIAL DE TESTE"


@pytest.fixture()
def db(tmp_path):
    return Database(tmp_path / "b.sqlite3")


def _visita(db, **campos) -> dict:
    dados = {"data": "2026-10-01", "natureza": "CORREICAO_ORDINARIA",
             "autoridade": "Juiz corregedor permanente da comarca",
             "termo": "Livros e arquivos examinados; nada a anotar."}
    dados.update(campos)
    with db.transaction() as con:
        return LV.lancar(con, hoje=HOJE, agora=AGORA, por=POR, **dados)


def _linha(db, visita_id: int) -> dict:
    with db.connect() as con:
        return next(x for x in LV.lancamentos(con) if x["id"] == visita_id)


def _selo(db, numero: str, *, usado_em: str, texto: str, atribuicao: str = "NOTAS",
          ambiente: str = "PRODUCAO", cancelado: bool = False) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, atribuicao, referencia, ambiente,
                   obtido_em, usado_em, cancelado_em)
               VALUES (%s, %s, %s, %s, %s, %s, %s, %s)""",
            (numero, texto, atribuicao, "protocolo 2026.09.1", ambiente, usado_em,
             usado_em, usado_em if cancelado else None))


def _texto(ato: str, total: str, emol: str, fundos: str = "", marca: str = "") -> str:
    return (f"Selo: TESTE{ato.replace('.', '')}000000000000000000 01/09/2026 10:00:00, "
            f"Ato: {ato}, Parte(s): FULANA DE TESTE, Total R$ {total} Emol R$ {emol} "
            f"{fundos} {marca} Consulte em https://selo.exemplo.invalid")


# ------------------------------------------------------------- o catálogo


def test_toda_serie_que_o_catalogo_cita_existe_no_nucleo_do_livro():
    citadas = {s for x in LO.LIVROS for s in x["series"]}
    assert citadas, "o catálogo tem de citar as séries que atendem"
    assert citadas <= set(LN.SERIES), citadas - set(LN.SERIES)


def test_os_cinco_livros_do_tabelionato_de_notas_sao_series_proprias():
    """Art. 788: Notas, Testamentos, Procurações, Substabelecimentos e Atas,
    em livros separados — cada um com série própria no núcleo e no lançamento."""
    notas = {x["chave"]: x for x in LO.LIVROS if x["grupo"] == "NOTAS"}
    for chave, serie in (("NT_NOTAS", "ESCRITURA"), ("NT_TESTAMENTOS", "TESTAMENTO"),
                         ("NT_PROCURACOES", "PROCURACAO"),
                         ("NT_SUBSTABELECIMENTOS", "SUBSTABELECIMENTO"),
                         ("NT_ATAS", "ATA")):
        assert notas[chave]["situacao"] == LO.TEM
        assert f"NT_{serie}" in notas[chave]["series"]
        assert serie in NL.LIVRO_DO_ATO.values()
    assert len({NL.LIVRO_DO_ATO[t] for t in ("ESCRITURA", "TESTAMENTO", "PROCURACAO",
                                             "SUBSTABELECIMENTO", "ATA")}) == 5


def test_a_numeracao_das_notas_continua_de_um_livro_para_o_outro():
    """Art. 792: a numeração da mesma espécie não se interrompe ao fim do livro."""
    for codigo, serie in LN.SERIES.items():
        if serie.atribuicao == 1:
            assert serie.termo_continuo and not serie.numeracao_diaria, codigo


def test_no_tabelionato_de_notas_nao_ha_protocolo_nem_indice_obrigatorio():
    notas = [x for x in LO.LIVROS if x["grupo"] == "NOTAS"]
    obrigatorios = [x for x in notas if x["situacao"] != LO.FACULTATIVO]
    assert not [x for x in obrigatorios if "protocolo" in x["nome"].lower()
                or "índice" in x["nome"].lower()]
    assert any("§ 5º" in x["artigo"] for x in notas if x["situacao"] == LO.FACULTATIVO)


def test_os_tres_livros_administrativos_de_toda_serventia_estao_no_catalogo():
    todas = {x["chave"]: x for x in LO.LIVROS if x["grupo"] == "TODAS"}
    assert set(todas) == {"ADM_VISITAS", "ADM_DIARIO", "ADM_DEPOSITO"}
    assert all("art. 188" in x["artigo"] for x in todas.values())
    assert sum(LO.contagem().values()) == len(LO.LIVROS)


def test_livro_que_falta_diz_o_que_falta():
    for x in LO.LIVROS:
        if x["situacao"] in (LO.FALTA, LO.PARCIAL, LO.A_CONFERIR):
            assert len(x["nota"]) > 30, x["chave"]


# ------------------------------------------------------ visitas e correições


def test_o_livro_de_visitas_numera_em_sequencia(db):
    a = _visita(db)
    b = _visita(db, natureza="INSPECAO", data="2026-10-02")
    assert (a["numero"], b["numero"]) == (1, 2)
    with db.connect() as con:
        linhas = LV.lancamentos(con)
    assert [x["numero"] for x in linhas] == [1, 2]
    assert linhas[0]["natureza_nome"] == "Correição ordinária"


def test_visita_no_futuro_nao_entra_no_livro(db):
    with pytest.raises(LV.VisitaError, match="futuro"):
        _visita(db, data="2026-10-20")


def test_visita_sem_termo_ou_sem_autoridade_nao_entra(db):
    with pytest.raises(LV.VisitaError, match="termo"):
        _visita(db, termo="ok")
    with pytest.raises(LV.VisitaError, match="autoridade"):
        _visita(db, autoridade="  ")
    with pytest.raises(LV.VisitaError, match="natureza"):
        _visita(db, natureza="PASSEIO")


def test_a_retificacao_e_lancamento_novo_e_o_antigo_fica_marcado(db):
    a = _visita(db)
    with pytest.raises(LV.VisitaError, match="por que"):
        _visita(db, retifica_id=a["id"], motivo_retificacao="erro")
    r = _visita(db, retifica_id=a["id"], data="2026-10-01",
                motivo_retificacao="A data do termo estava trocada com a da inspeção.")
    assert r["numero"] == 2
    antigo, novo = _linha(db, a["id"]), _linha(db, r["id"])
    assert antigo["termo"] and antigo["retificado_por_numero"] == 2
    assert novo["retifica_numero"] == 1
    with pytest.raises(LV.VisitaError, match="já foi retificado"):
        _visita(db, retifica_id=a["id"], motivo_retificacao="Segunda tentativa de corrigir.")


def test_o_livro_de_visitas_nao_tem_funcao_que_edite_ou_apague():
    """Eletrônico, sob a guarda do delegatário (art. 189): nada de UPDATE nem
    DELETE no módulo — a correção é a retificação."""
    fonte = (RAIZ / "livro_visitas.py").read_text(encoding="utf-8")
    assert "UPDATE lv_visitas" not in fonte and "DELETE FROM lv_visitas" not in fonte


def test_a_visita_pode_apontar_para_a_inspecao_do_plano_de_acao(db):
    with pytest.raises(LV.VisitaError, match="não existe"):
        _visita(db, inspecao_id=99999)
    with db.transaction() as con:
        iid = banco(con).escrever(
            """INSERT INTO inspections (title, report_date, active, created_at)
               VALUES ('Inspeção de teste', '2026-08-12', 1, %s) RETURNING id""",
            (AGORA,))[0]["id"]
    v = _visita(db, natureza="INSPECAO", inspecao_id=iid)
    assert _linha(db, v["id"])["inspecao_id"] == iid


def test_id_do_formulario_que_nao_e_digito_ascii_e_ignorado_e_nao_derruba_a_visita(db):
    """`'²'.isdigit()` é verdadeiro e `int('²')` estoura: era um 500 no POST
    (ressalva da revisão do LG08). Agora o campo é ignorado, como o vazio."""
    v = _visita(db, inspecao_id="²", retifica_id="²")
    linha = _linha(db, v["id"])
    assert linha["inspecao_id"] is None and linha["retifica_id"] is None
    assert v["numero"] == 1


# --------------------------------------------------------------- diário


def test_a_receita_do_diario_e_o_emolumento_do_selo_usado_no_dia(db):
    _selo(db, "S1", usado_em="2026-09-03T10:00:00",
          texto=_texto("13.23", "140,01", "125,01",
                       "FERC R$ 3,75 FADEP R$ 5,00 FEMP R$ 5,00 FERRFIS R$ 1,25"))
    _selo(db, "S2", usado_em="2026-09-03T11:00:00", atribuicao="CIVIL",
          texto=_texto("16.1", "27,50", "26,70", "FERC R$ 0,80"))
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    dia = livro["dias"][0]
    assert dia["dia"] == "2026-09-03"
    assert livro["receita_bruta"] == 12501 + 2670           # só emolumento
    assert livro["fundos"]["FERC"] == 375 + 80              # fundo não é receita
    assert livro["fundos"]["ISS"] == 0                      # o selo não declarou
    assert livro["por_especialidade"] == {"Notas": 12501, "RCPN": 2670}
    linha = next(r for r in dia["receitas"] if r["selo"] == "S1")
    assert (linha["ato"], linha["tipo"], linha["emolumentos"]) == ("13.23", "Normal", 12501)


def test_isento_diferido_cancelado_e_homologacao_nao_somam_receita(db):
    base = dict(usado_em="2026-09-04T09:00:00")
    _selo(db, "ISENTO", texto=_texto("16.3", "115,44", "100,00", marca="Selo Isento"), **base)
    _selo(db, "DIFERIDO", texto=_texto("16.3", "50,00", "40,00", marca="Diferido"), **base)
    _selo(db, "CANCELADO", texto=_texto("13.23", "140,01", "125,01"), cancelado=True, **base)
    _selo(db, "HOMOLOG", texto=_texto("13.23", "140,01", "125,01"),
          ambiente="HOMOLOGACAO", **base)
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    assert livro["receita_bruta"] == 0
    assert (livro["atos"], livro["isentos"], livro["diferidos"]) == (2, 1, 1)
    tipos = {r["selo"]: r["tipo"] for r in livro["dias"][0]["receitas"]}
    assert tipos == {"ISENTO": "Isento", "DIFERIDO": "Diferido"}


def test_selo_sem_texto_aparece_sem_valor_e_nao_como_zero(db):
    _selo(db, "MUDO", usado_em="2026-09-05T09:00:00", texto="")
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    linha = livro["dias"][0]["receitas"][0]
    assert linha["emolumentos"] is None and livro["sem_valor"] == 1
    assert LD.em_reais(linha["emolumentos"]) == "—"


def test_a_despesa_se_lanca_no_dia_do_pagamento_e_entra_no_demonstrativo(db):
    _selo(db, "S1", usado_em="2026-09-03T10:00:00", texto=_texto("13.23", "140,01", "125,01"))
    with db.transaction() as con:
        LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por=POR, data="2026-09-10",
                          descricao="Energia elétrica da sede, conta de agosto",
                          documento_especie="Fatura", documento_numero="0001",
                          valor="45,00")
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    assert (livro["receita_bruta"], livro["despesas"], livro["receita_liquida"]) == \
        (12501, 4500, 8001)
    ultimo = livro["dias"][-1]
    assert ultimo["dia"] == "2026-09-10" and ultimo["transporte"] == 8001


def test_despesa_sem_documento_sem_descricao_ou_no_futuro_nao_entra(db):
    def lancar(**campos):
        dados = {"data": "2026-09-10", "descricao": "Material de escritório",
                 "documento_especie": "Nota fiscal", "valor": "10,00"}
        dados.update(campos)
        with db.transaction() as con:
            LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por=POR, **dados)
    with pytest.raises(LD.DiarioError, match="espécie"):
        lancar(documento_especie="")
    with pytest.raises(LD.DiarioError, match="detalhe"):
        lancar(descricao="papel")
    with pytest.raises(LD.DiarioError, match="futuro"):
        lancar(data="2026-10-20")
    with pytest.raises(LD.DiarioError, match="maior que zero"):
        lancar(valor="0,00")


def test_despesa_anulada_sai_da_conta_e_fica_no_historico(db):
    with db.transaction() as con:
        did = LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por=POR, data="2026-09-10",
                                descricao="Aluguel da sede, setembro",
                                documento_especie="Recibo", valor="1.000,00")
    with db.transaction() as con:
        with pytest.raises(LD.DiarioError, match="por que"):
            LD.anular_despesa(con, did, agora=AGORA, por=POR, motivo="erro")
    with db.transaction() as con:
        LD.anular_despesa(con, did, agora=AGORA, por=POR,
                          motivo="Lançada em duplicidade com a de 09/09.")
    with db.connect() as con:
        assert LD.apurar(con, "2026-09")["despesas"] == 0
        historico = LD.despesas_do_mes(con, "2026-09", com_anuladas=True)
    assert len(historico) == 1 and historico[0]["anulada_em"]


def test_a_competencia_so_aceita_digito_ascii_e_ano_que_existe():
    """`\\d` aceitava «٢٠٢٦-٠٩», que o texto ISO do selo nunca iguala (o mês
    sairia vazio), e «0000-05» chegava a `date(0, ...)`."""
    assert LD.competencia("2026-09") == "2026-09"
    for errada in ("٢٠٢٦-٠٩", "0000-05", "2026-13", "2026-9"):
        with pytest.raises(LD.DiarioError, match="AAAA-MM"):
            LD.competencia(errada)


def test_o_mes_em_curso_nao_se_gera(db):
    with db.transaction() as con:
        with pytest.raises(LD.DiarioError, match="ainda não acabou"):
            LD.gerar(con, "2026-10", hoje=HOJE, agora=AGORA, por=POR)


def test_gerar_de_novo_so_com_retificacao_circunstanciada_e_a_versao_antiga_fica(db):
    _selo(db, "S1", usado_em="2026-09-03T10:00:00", texto=_texto("13.23", "140,01", "125,01"))
    with db.transaction() as con:
        v1 = LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    assert v1["versao"] == 1 and v1["receita_bruta"] == 12501
    with db.transaction() as con:
        with pytest.raises(LD.DiarioError, match="art. 206"):
            LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    with db.transaction() as con:
        LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por=POR, data="2026-09-15",
                          descricao="Manutenção da impressora do balcão",
                          documento_especie="Nota fiscal", valor="200,00")
    with db.connect() as con:
        assert LD.situacao_do_mes(con, "2026-09", hoje=HOJE)["movimento_mudou"]
    with db.transaction() as con:
        v2 = LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR,
                      motivo="Despesa de 15/09 lançada depois da geração.")
    with db.connect() as con:
        versoes = LD.geracoes(con, "2026-09")
        antiga = LD.geracao(con, v1["id"])
        situacao = LD.situacao_do_mes(con, "2026-09", hoje=HOJE)
    assert [v["versao"] for v in versoes] == [2, 1]
    assert antiga["livro"]["despesas"] == 0 and antiga["integra"]
    assert v2["despesas"] == 20000 and versoes[0]["motivo"].startswith("Despesa")
    assert not situacao["movimento_mudou"]


def test_a_fotografia_gerada_acusa_alteracao_posterior(db):
    with db.transaction() as con:
        g = LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    with db.transaction() as con:
        conteudo = json.loads(banco(con).valor(
            "SELECT conteudo AS c FROM ld_geracoes WHERE id = %s", (g["id"],)))
        conteudo["receita_bruta"] = 999
        banco(con).escrever("UPDATE ld_geracoes SET conteudo = %s WHERE id = %s",
                            (json.dumps(conteudo), g["id"]))
    with db.connect() as con:
        assert not LD.geracao(con, g["id"])["integra"]


# ------------------------------------------- o FERJ não é o FERC (25/10/2026)


def _percentual_ferj(db, valor: str) -> None:
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO settings (key, value) VALUES (%s, %s)",
                            (custas.CHAVE_PERCENTUAL_FERJ, valor))


def test_o_ferj_e_12_por_cento_do_emolumento_e_o_ferc_fica_na_coluna_dele(db):
    """Art. 190, I, k. O oficial: «ferj e ferc são diferentes. ferj é uns 12%,
    ferc é 3%, mas não abate dos emolumentos». O FERC é o que o selo declara;
    o FERJ sai de dentro do emolumento, e não mexe na receita."""
    _selo(db, "S1", usado_em="2026-09-03T10:00:00",
          texto=_texto("13.23", "140,01", "125,01",
                       "FERC R$ 3,75 FADEP R$ 5,00 FEMP R$ 5,00 FERRFIS R$ 1,25"))
    _selo(db, "S2", usado_em="2026-09-03T11:00:00", atribuicao="CIVIL",
          texto=_texto("16.1", "13,12", "12,38", "FERC R$ 0,37"))
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    linhas = {r["selo"]: r for r in livro["dias"][0]["receitas"]}
    assert linhas["S1"]["fundos"]["FERJ"] == 1500          # 12% de 125,01
    assert linhas["S1"]["fundos"]["FERC"] == 375           # o do selo, intocado
    assert linhas["S2"]["fundos"]["FERJ"] == 149           # 148,56 centavos sobe
    assert livro["fundos"]["FERJ"] == 1500 + 149
    assert livro["fundos"]["FERC"] == 375 + 37
    assert livro["receita_bruta"] == 12501 + 1238          # o FERJ não abate
    assert livro["ferj_percentual"] == 1200


def test_nenhuma_coluna_do_livro_chama_o_ferc_de_ferj():
    rotulos = dict(LD.FUNDOS)
    assert rotulos["FERC"] == "FERC" and rotulos["FERJ"] == "FERJ"
    # O FERJ vem logo depois do emolumento (art. 190, I, j e k), e o ISSQN
    # fecha a linha (I, l).
    assert LD.FUNDOS[0][0] == "FERJ" and LD.FUNDOS[-1][0] == "ISS"
    fonte = (RAIZ / "livro_diario.py").read_text(encoding="utf-8")
    assert '("FERC", "FERJ' not in fonte


def test_o_percentual_do_ferj_e_configuracao_e_vai_gravado_no_livro(db):
    _percentual_ferj(db, "10,00")
    _selo(db, "S1", usado_em="2026-09-03T10:00:00", texto=_texto("13.23", "140,01", "125,01"))
    with db.transaction() as con:
        g = LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    with db.connect() as con:
        livro = LD.geracao(con, g["id"])["livro"]
    assert livro["ferj_percentual"] == 1000
    assert livro["fundos"]["FERJ"] == 1250                 # 10% de 125,01


def test_isento_e_diferido_mostram_o_ferj_que_teriam_e_nao_somam(db):
    base = dict(usado_em="2026-09-04T09:00:00")
    _selo(db, "ISENTO", texto=_texto("16.3", "115,44", "100,00", marca="Selo Isento"), **base)
    _selo(db, "DIFERIDO", texto=_texto("16.3", "50,00", "40,00", marca="Diferido"), **base)
    _selo(db, "MUDO", texto="", **base)
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    linhas = {r["selo"]: r for r in livro["dias"][0]["receitas"]}
    assert linhas["ISENTO"]["fundos"]["FERJ"] == 1200
    assert linhas["DIFERIDO"]["fundos"]["FERJ"] == 480
    assert linhas["MUDO"]["fundos"]["FERJ"] is None        # sem valor: «—», não zero
    assert livro["fundos"]["FERJ"] == 0


def _como_se_gerado_antes_do_ferj(db, geracao_id: int) -> None:
    """Regrava a fotografia na forma de antes de 25/10/2026, com o hash dela —
    o que a produção tem para os meses gerados antes da correção."""
    with db.transaction() as con:
        bd = banco(con)
        velho = LD._sem_ferj(json.loads(bd.valor(
            "SELECT conteudo AS c FROM ld_geracoes WHERE id = %s", (geracao_id,))))
        bd.escrever("UPDATE ld_geracoes SET conteudo = %s, hash = %s WHERE id = %s",
                    (json.dumps(velho, ensure_ascii=False, sort_keys=True),
                     LD._hash(velho), geracao_id))


def test_o_livro_gerado_antes_do_ferj_e_reconhecido_e_nao_acusa_movimento(db):
    _selo(db, "S1", usado_em="2026-09-03T10:00:00",
          texto=_texto("13.23", "140,01", "125,01", "FERC R$ 3,75"))
    with db.transaction() as con:
        g = LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    _como_se_gerado_antes_do_ferj(db, g["id"])
    with db.connect() as con:
        situacao = LD.situacao_do_mes(con, "2026-09", hoje=HOJE)
        antiga = LD.geracao(con, g["id"])
    assert situacao["gerado_antes_do_ferj"] and not situacao["movimento_mudou"]
    assert antiga["integra"] and "ferj_percentual" not in antiga["livro"]
    # Se o movimento também mudou, é isso que a tela diz.
    with db.transaction() as con:
        LD.lancar_despesa(con, hoje=HOJE, agora=AGORA, por=POR, data="2026-09-15",
                          descricao="Manutenção da impressora do balcão",
                          documento_especie="Nota fiscal", valor="200,00")
    with db.connect() as con:
        situacao = LD.situacao_do_mes(con, "2026-09", hoje=HOJE)
    assert situacao["movimento_mudou"] and not situacao["gerado_antes_do_ferj"]


def test_o_livro_gerado_ja_com_o_ferj_nao_se_diz_de_antes(db):
    _selo(db, "S1", usado_em="2026-09-03T10:00:00", texto=_texto("13.23", "140,01", "125,01"))
    with db.transaction() as con:
        LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)
    with db.connect() as con:
        situacao = LD.situacao_do_mes(con, "2026-09", hoje=HOJE)
    assert not situacao["gerado_antes_do_ferj"] and not situacao["movimento_mudou"]


def test_a_regua_do_ferj_le_virgula_recusa_o_ilegivel_e_arredonda_ao_centavo(db):
    assert custas.percentual_ferj({}) == 1200
    assert custas.percentual_ferj({custas.CHAVE_PERCENTUAL_FERJ: ""}) == 1200
    assert custas.percentual_ferj({custas.CHAVE_PERCENTUAL_FERJ: "12,5%"}) == 1250
    for ruim in ("doze", "100", "-1"):
        with pytest.raises(custas.CustasError, match="FERJ"):
            custas.percentual_ferj({custas.CHAVE_PERCENTUAL_FERJ: ruim})
    assert custas.ferj_do_emolumento(12501, 1200) == 1500   # 15,0012
    assert custas.ferj_do_emolumento(1238, 1200) == 149     # 1,4856
    assert custas.ferj_do_emolumento(0, 1200) == 0
    with db.connect() as con:
        assert custas.percentual_ferj_da_casa(con) == 1200  # nada gravado
    _percentual_ferj(db, "11,75")
    with db.connect() as con:
        assert custas.percentual_ferj_da_casa(con) == 1175


def test_ferj_vazio_vale_12_e_o_ilegivel_e_recusa_do_livro_com_onde_corrigir(db):
    """Decisão do oficial em 27/10/2026: «12% para os dois». Vazio vale 12,00
    no livro (e na NFS-e, que passou a ler pela mesma função). O ilegível
    gravado fora da tela é `DiarioError` com a frase de onde corrigir — até
    essa data era `CustasError`, que a tela não apanhava (HTTP 500)."""
    _selo(db, "S1", usado_em="2026-09-03T10:00:00", texto=_texto("13.23", "140,01", "125,01"))
    _percentual_ferj(db, "")
    with db.connect() as con:
        livro = LD.apurar(con, "2026-09")
    assert livro["ferj_percentual"] == 1200 and livro["fundos"]["FERJ"] == 1500
    with db.transaction() as con:
        banco(con).escrever("UPDATE settings SET value = %s WHERE key = %s",
                            ("doze", custas.CHAVE_PERCENTUAL_FERJ))
    with db.connect() as con:
        with pytest.raises(LD.DiarioError, match="Gestor → NFS-e") as erro:
            LD.apurar(con, "2026-09")
        assert "doze" in str(erro.value)
        with pytest.raises(LD.DiarioError, match="FERJ"):
            LD.receitas_do_mes(con, "2026-09")
    with db.transaction() as con:
        with pytest.raises(LD.DiarioError, match="FERJ"):
            LD.gerar(con, "2026-09", hoje=HOJE, agora=AGORA, por=POR)


def test_o_ferc_nao_tem_o_nome_do_ferj_no_cadastro_de_fundos():
    """O `tbFundo` do E-Ofício dá ao FERC o nome do FERJ; os dois cadastros
    daqui o copiaram. O nome do FERC é o do Código de Normas, art. 217."""
    nome_do_ferj = "Modernização e Reaparelhamento"
    for cadastro in (ATR.FUNDOS, custas.FUNDOS):
        ferc = next(f for f in cadastro if f["sigla"] == "FERC")
        assert nome_do_ferj not in ferc["nome"]
        assert "Registro Civil de Pessoas Naturais" in ferc["nome"]
        assert ferc["percentual"] == 3


def test_o_prazo_do_diario_e_o_quinto_dia_util_do_mes_seguinte():
    """Art. 205. Outubro/2026: 1º (qui), 2 (sex), 5 (seg), 6 (ter), 7 (qua)."""
    assert LD.prazo_de_geracao("2026-09") == date(2026, 10, 7)
    # Janeiro/2027: o dia 1º é feriado.
    assert LD.prazo_de_geracao("2026-12") == date(2027, 1, 8)
    with pytest.raises(LD.DiarioError):
        LD.competencia("2026-13")


def test_o_dinheiro_do_diario_e_bigint_em_centavos(db):
    with db.connect() as con:
        tipos = {x["column_name"]: x["data_type"] for x in banco(con).ler(
            """SELECT column_name, data_type FROM information_schema.columns
                WHERE table_schema = current_schema()
                  AND table_name IN ('ld_despesas', 'ld_geracoes')
                ORDER BY column_name""")}
    for coluna in ("valor", "receita_bruta", "despesas", "receita_liquida"):
        assert tipos[coluna] == "bigint", coluna


def test_o_esquema_ganha_o_indice_que_falta_na_tabela_que_ja_existe(db):
    with db.transaction() as con:
        banco(con).escrever("DROP INDEX ux_lv_visitas_numero")
    try:
        with db.transaction() as con:
            LV.init_livro_visitas_schema(con)
        with db.connect() as con:
            assert banco(con).tem_tabela("ux_lv_visitas_numero")
    finally:
        with db.transaction() as con:
            LV.init_livro_visitas_schema(con)


# -------------------------------------------------------- depósito prévio


def test_o_livro_de_deposito_previo_le_conversao_e_devolucao_do_rastro(db):
    with db.transaction() as con:
        bd = banco(con)
        pid = bd.escrever(
            """INSERT INTO cx_protocolos (numero, data_abertura, atribuicao, criado_em)
               VALUES ('2026.09.7', '2026-09-01', 'NOTAS', %s) RETURNING id""",
            (AGORA,))[0]["id"]
        com = bd.escrever(
            """INSERT INTO cx_depositos (numero, data, depositante, valor, saldo,
                   protocolo_id, criado_em)
               VALUES ('DP2026.09.1', '2026-09-01', 'DEPOSITANTE DE TESTE',
                       '500,00', '0,00', %s, %s) RETURNING id""", (pid, AGORA))[0]["id"]
        solto = bd.escrever(
            """INSERT INTO cx_depositos (numero, data, depositante, valor, saldo, criado_em)
               VALUES ('DP2026.09.2', '2026-09-02', 'OUTRO DEPOSITANTE DE TESTE',
                       '300,00', '100,00', %s) RETURNING id""", (AGORA,))[0]["id"]
    db.log(None, "teste", LDP.USADO, "DEPOSITO", com,
           {"usado": "400,00", "saldo": "100,00", "protocolo": "2026.09.7"}, None)
    db.log(None, "teste", LDP.DEVOLVIDO, "DEPOSITO", com,
           {"valor": "100,00", "motivo": "Ato desistido pela parte."}, None)
    with db.connect() as con:
        livro = LDP.livro(con)
    por_id = {x["id"]: x for x in livro["linhas"]}
    a, b = por_id[com], por_id[solto]
    assert a["protocolo"] == "2026.09.7" and a["valor"] == 50000 and a["diferenca"] == 0
    assert [m["valor"] for m in a["conversoes"]] == [40000]
    assert a["devolucoes"][0]["motivo"] == "Ato desistido pela parte."
    assert not [f for f in a["faltas"] if f.startswith(("I —", "IV", "V —"))]
    assert any(f.startswith("I —") for f in b["faltas"])
    assert b["diferenca"] == 20000                  # saiu do saldo sem rastro
    assert (livro["total_depositado"], livro["total_convertido"],
            livro["total_devolvido"]) == (80000, 40000, 10000)


def test_o_ano_do_deposito_previo_filtra_e_o_ano_estranho_e_ignorado(db):
    """O filtro só vale com quatro dígitos ASCII: «²» passava no `isdigit()` e
    derrubava a tela no `int()` (ressalva da revisão do LG08)."""
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO cx_depositos (numero, data, depositante, valor, saldo, criado_em)
               VALUES ('DP2025.12.1', '2025-12-30', 'DEPOSITANTE DE TESTE',
                       '10,00', '10,00', %s), ('DP2026.01.1', '2026-01-02',
                       'OUTRO DEPOSITANTE DE TESTE', '20,00', '20,00', %s)""",
            (AGORA, AGORA))
    with db.connect() as con:
        de_2026 = [x["data"] for x in LDP.livro(con, ano="2026")["linhas"]]
        estranho = [x["data"] for x in LDP.livro(con, ano="²")["linhas"]]
    assert de_2026 == ["2026-01-02"]
    assert estranho == ["2025-12-30", "2026-01-02"]


# ------------------------------------------------------- agenda do oficial


def test_o_diario_do_mes_entra_na_agenda_ate_o_quinto_dia_util():
    mensal = next(o for o in OO.OBRIGACOES if o["codigo"] == "LIVRO_DIARIO_MENSAL")
    assert OO.proximo_vencimento(mensal, date(2026, 10, 1)) == \
        (date(2026, 10, 7), "referência 09/2026")
    # Passado o prazo de outubro, o próximo é o de novembro, de outubro.
    assert OO.proximo_vencimento(mensal, date(2026, 10, 8)) == \
        (date(2026, 11, 9), "referência 10/2026")


def test_o_diario_do_ano_vai_ate_o_primeiro_dia_util_de_maio():
    anual = next(o for o in OO.OBRIGACOES if o["codigo"] == "LIVRO_DIARIO_ANUAL")
    # 1º/05/2027 é feriado e sábado; 03/05 é segunda.
    assert OO.proximo_vencimento(anual, date(2026, 10, 19)) == (date(2027, 5, 3), "ano de 2026")


def test_o_livro_diario_saiu_da_pergunta_e_o_carne_leao_continua_nela():
    a_confirmar = {o["codigo"] for o in OO.A_CONFIRMAR}
    assert "LIVRO_CAIXA_IR" not in a_confirmar and "CARNE_LEAO" in a_confirmar
    assert {"LIVRO_DIARIO_MENSAL", "LIVRO_DIARIO_ANUAL"} <= {o["codigo"] for o in OO.OBRIGACOES}
