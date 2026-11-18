"""Quem comparece por outra parte vem na qualificação dela, com o instrumento.

Decisão do oficial, 03/11/2026 (ensaio de atos das Notas, item 2; CN-MA art. 798, VI e VII): «…, neste
ato representado por FULANO, conforme procuração lavrada no livro X, folha Y, do …», na qualificação
do representado. A prática pela tela está em `test_ensaio_de_atos_notas`. Os nomes são fictícios.
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import notas_teor as NT  # noqa: E402

BASE = {"tipo_pessoa": "F", "nacionalidade": "brasileiro", "estado_civil": "solteiro",
        "profissao": "comerciante", "documento": "00000000191", "identidade": "1234567 SSP/MA",
        "uniao_estavel": "NAO", "endereco": "Rua Exemplo, 10"}
VENDEDOR = {**BASE, "id": 1, "nome": "MARIO EXEMPLO DOS SANTOS", "qualificacao": "VENDEDOR"}
COMPRADORA = {**BASE, "id": 2, "nome": "BEATRIZ EXEMPLO DE SOUZA", "qualificacao": "COMPRADORA"}
PROCURACAO = "procuração lavrada no livro 10, folha 20, do Tabelionato de Notas de Cidade Exemplo"


def _procurador(**mais) -> dict:
    return {**BASE, "id": 3, "nome": "CARLOS EXEMPLO PROCURADOR", "qualificacao": "PROCURADOR",
            "representa_parte_id": 1, "representa_instrumento": PROCURACAO, **mais}


def test_o_procurador_vem_na_qualificacao_do_vendedor_com_a_procuracao():
    outorgantes, outorgados = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador()],
                                                 tipo_ato="ESCRITURA")
    assert ", neste ato representado(a) por <b>CARLOS EXEMPLO PROCURADOR</b>" in outorgantes
    assert outorgantes.endswith("conforme " + PROCURACAO)
    assert outorgantes.count("CARLOS") == 1 and "CARLOS" not in outorgados
    assert "[" not in outorgantes.split("CARLOS")[1]


def test_sem_o_instrumento_ele_fica_marcado():
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador(representa_instrumento="")],
                                        tipo_ato="ESCRITURA")
    assert "[INSTRUMENTO DA REPRESENTAÇÃO" in outorgantes


def test_sem_dizer_quem_representa_ele_continua_marcado_fora_dos_lados():
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador(representa_parte_id=None)],
                                        tipo_ato="ESCRITURA")
    assert "DIGA JUNTO DE QUEM REPRESENTA" in outorgantes and "neste ato" not in outorgantes


def test_a_assistente_assiste():
    mae = {**BASE, "id": 3, "nome": "JOANA EXEMPLO DOS SANTOS", "qualificacao": "ASSISTENTE",
           "representa_parte_id": 2, "representa_instrumento": "certidão de nascimento lavrada no livro A-1"}
    _, outorgados = NT.partes_por_lado([VENDEDOR, COMPRADORA, mae], tipo_ato="ESCRITURA")
    assert ", neste ato assistido(a) por <b>JOANA EXEMPLO DOS SANTOS</b>" in outorgados


def test_quem_assina_a_rogo_nao_representa_e_nao_pede_instrumento():
    rogo = {**BASE, "id": 3, "nome": "PAULO EXEMPLO TESTEMUNHA", "qualificacao": "ASSINA A ROGO",
            "representa_parte_id": 1}
    outorgantes, _ = NT.partes_por_lado([VENDEDOR, COMPRADORA, rogo], tipo_ato="ESCRITURA")
    assert "assinando a seu rogo <b>PAULO EXEMPLO TESTEMUNHA</b>" in outorgantes
    assert "representado" not in outorgantes and "[INSTRUMENTO" not in outorgantes


def test_parte_de_outro_ato_ou_ela_mesma_nao_conta():
    assert NT.representantes_por_parte([VENDEDOR, _procurador(representa_parte_id=99)]) == {}
    assert NT.representantes_por_parte([_procurador(id=1, representa_parte_id=1)]) == {}


# ------------------------------------------- quem assina por quem (observação 9, 03/11/2026)

def test_o_representado_nao_assina_e_o_procurador_assina_por_ele():
    linha = NT.texto_dos_assinantes([VENDEDOR, COMPRADORA, _procurador()])
    assert "MARIO EXEMPLO DOS SANTOS, VENDEDOR" not in linha
    assert "CARLOS EXEMPLO PROCURADOR, PROCURADOR, por MARIO EXEMPLO DOS SANTOS" in linha
    assert "BEATRIZ EXEMPLO DE SOUZA, COMPRADORA" in linha


def test_quem_assina_a_rogo_assina_a_rogo_de():
    rogo = {**BASE, "id": 3, "nome": "PAULO EXEMPLO TESTEMUNHA", "qualificacao": "ASSINA A ROGO",
            "representa_parte_id": 1}
    linha = NT.texto_dos_assinantes([VENDEDOR, COMPRADORA, rogo])
    assert "PAULO EXEMPLO TESTEMUNHA, a rogo de MARIO EXEMPLO DOS SANTOS" in linha
    assert "MARIO EXEMPLO DOS SANTOS, VENDEDOR" not in linha


def test_o_assistido_assina_com_o_assistente():
    mae = {**BASE, "id": 3, "nome": "JOANA EXEMPLO DOS SANTOS", "qualificacao": "ASSISTENTE",
           "representa_parte_id": 2}
    linha = NT.texto_dos_assinantes([VENDEDOR, COMPRADORA, mae])
    assert "BEATRIZ EXEMPLO DE SOUZA, COMPRADORA" in linha
    assert "JOANA EXEMPLO DOS SANTOS, ASSISTENTE, assistindo BEATRIZ EXEMPLO DE SOUZA" in linha


def test_as_linhas_de_assinatura_seguem_a_mesma_regra():
    bloco = NT.bloco_de_assinaturas([VENDEDOR, COMPRADORA, _procurador()], "PEDRO EXEMPLO", "Escrevente")
    # nenhuma linha em nome do vendedor; o nome dele só na condição de quem assina por ele
    assert ">MARIO EXEMPLO DOS SANTOS<" not in bloco
    assert "PROCURADOR, por MARIO EXEMPLO DOS SANTOS" in bloco


# ------------------------------------------- várias partes, 18/11/2026

PROC_A = "procuração A, livro 1, folhas 2, termo 3"
PROC_B = "procuração B, livro 4, folhas 5, termo 6"


def _parte(pid: int, nome: str, qualificacao: str, **mais) -> dict:
    return {**BASE, "id": pid, "nome": nome, "qualificacao": qualificacao, **mais}


def _procuradora_de(vinculos: list[tuple[int, str]], **mais) -> dict:
    """Procuradora X com N vínculos (representado_id, instrumento)."""
    reps = [{"representado_parte_id": a, "instrumento": i} for a, i in vinculos]
    primeiro = reps[0] if reps else {}
    return _parte(90, "PROCURADORA X", "PROCURADORA",
                  representacoes=reps,
                  representa_parte_id=primeiro.get("representado_parte_id"),
                  representa_instrumento=primeiro.get("instrumento"),
                  **mais)


def test_uma_procuradora_representa_varias_partes_com_instrumentos_distintos():
    # 6 partes com a procuração A e 1 com a B — nomes fictícios (Parte A… / Parte G)
    seis = [_parte(10 + i, f"PARTE {chr(65 + i)}", "VENDEDOR") for i in range(6)]
    uma = _parte(20, "PARTE G", "VENDEDOR")
    compradora = _parte(2, "PARTE B COMPRADORA", "COMPRADORA")
    proc = _procuradora_de([(p["id"], PROC_A) for p in seis] + [(uma["id"], PROC_B)])
    reps = NT.representantes_por_parte(seis + [uma, compradora, proc])
    assert len(reps) == 7
    assert all(reps[p["id"]][0]["representa_instrumento"] == PROC_A for p in seis)
    assert reps[uma["id"]][0]["representa_instrumento"] == PROC_B

    outorgantes, _ = NT.partes_por_lado(seis + [uma, compradora, proc], tipo_ato="ESCRITURA")
    assert outorgantes.count("PROCURADORA X") == 1
    assert PROC_A in outorgantes and PROC_B in outorgantes
    assert "quanto a" in outorgantes  # instrumentos distintos na mesma frase
    assert "PARTE A" in outorgantes and "PARTE G" in outorgantes


def test_representados_com_o_mesmo_instrumento_ficam_agrupados():
    a = _parte(1, "PARTE A", "VENDEDOR")
    b = _parte(2, "PARTE B", "VENDEDOR")
    c = _parte(3, "PARTE C", "COMPRADORA")
    proc = _procuradora_de([(1, PROC_A), (2, PROC_A)])
    outorgantes, _ = NT.partes_por_lado([a, b, c, proc], tipo_ato="ESCRITURA")
    assert outorgantes.count("PROCURADORA X") == 1
    assert "representados por" in outorgantes
    assert outorgantes.count(PROC_A) == 1
    assert "[INSTRUMENTO" not in outorgantes


def test_falta_de_instrumento_continua_marcada_com_varios_vinculos():
    a = _parte(1, "PARTE A", "VENDEDOR")
    b = _parte(2, "PARTE B", "VENDEDOR")
    proc = _procuradora_de([(1, PROC_A), (2, "")])
    outorgantes, _ = NT.partes_por_lado([a, b, _parte(3, "PARTE C", "COMPRADORA"), proc],
                                        tipo_ato="ESCRITURA")
    assert "[INSTRUMENTO DA REPRESENTAÇÃO" in outorgantes
    assert PROC_A in outorgantes


def test_ato_antigo_com_vinculo_unico_continua_igual():
    # Colunas antigas, sem `representacoes`: mesmo teor de antes.
    outorgantes, outorgados = NT.partes_por_lado([VENDEDOR, COMPRADORA, _procurador()],
                                                 tipo_ato="ESCRITURA")
    assert ", neste ato representado(a) por <b>CARLOS EXEMPLO PROCURADOR</b>" in outorgantes
    assert outorgantes.endswith("conforme " + PROCURACAO)
    assert outorgantes.count("CARLOS") == 1 and "CARLOS" not in outorgados


def test_o_procurador_assina_uma_vez_por_todas_as_partes():
    a = _parte(1, "PARTE A", "VENDEDOR")
    b = _parte(2, "PARTE B", "VENDEDOR")
    c = _parte(3, "PARTE C", "COMPRADORA")
    proc = _procuradora_de([(1, PROC_A), (2, PROC_B)])
    linha = NT.texto_dos_assinantes([a, b, c, proc])
    assert linha.count("PROCURADORA X") == 1
    assert "por PARTE A e PARTE B" in linha or ("por PARTE A" in linha and "PARTE B" in linha)
    assert "PARTE A, VENDEDOR" not in linha and "PARTE B, VENDEDOR" not in linha


def test_oab_da_procuradora_entra_na_qualificacao_e_nao_nos_advogados():
    proc = _procuradora_de([(1, PROC_A)], oab_numero="12345", oab_uf="MA",
                           profissao="advogada")
    texto = NT.qualificar(proc)
    assert "inscrito(a) na OAB/MA sob o nº 12345" in texto
    ctx = NT.contexto_jinja_partes([VENDEDOR, COMPRADORA, proc], tipo_ato="ESCRITURA")
    assert "OAB/MA" in ctx["outorgantes"]
    assert "PROCURADORA X" not in ctx["advogados"] or ctx["advogados"].startswith("[ADVOGADO")


def test_anexar_representacoes_espelha_o_primeiro_no_legado():
    partes = NT.anexar_representacoes(
        [_parte(90, "PROCURADORA X", "PROCURADORA")],
        [{"representante_parte_id": 90, "representado_parte_id": 1, "instrumento": PROC_A},
         {"representante_parte_id": 90, "representado_parte_id": 2, "instrumento": PROC_B}])
    assert len(partes[0]["representacoes"]) == 2
    assert partes[0]["representa_parte_id"] == 1
    assert partes[0]["representa_instrumento"] == PROC_A


def test_a_tela_mostra_oab_para_procuradora_e_varios_vinculos():
    html = (Path(__file__).resolve().parent.parent / "templates" / "notas_ato.html"
            ).read_text(encoding="utf-8")
    assert "por_outro" in html and "oab_numero" in html
    assert "startswith('ADVOGAD') or por_outro" in html
    assert 'name="representa_parte_id"' in html
    assert "+ outra parte" in html
    assert "reps-" in html


def test_doi_mantem_procuradora_fora_e_representados_no_papel():
    import notas_doi as NDOI
    assert NDOI.lado_da_parte("PROCURADORA") == "FORA"
    assert NDOI.lado_da_parte("ASSISTENTE") == "FORA"
    alienantes, adquirentes, _ = NDOI.lados_das_partes([
        _parte(1, "PARTE A", "VENDEDOR"),
        _parte(2, "PARTE B", "COMPRADORA"),
        _procuradora_de([(1, PROC_A), (2, PROC_B)]),
    ])
    assert [p["nome"] for p in alienantes] == ["PARTE A"]
    assert [p["nome"] for p in adquirentes] == ["PARTE B"]


def test_migracao_de_representacao_esta_no_upgrade_e_e_idempotente():
    import inspect
    import notas_schema as NS

    assert "nt_ato_representacoes" in NS.SCHEMA
    assert "ux_nt_ato_representacoes_par" in NS.SCHEMA
    corpo = inspect.getsource(NS.init_notas_schema)
    assert "migrar_representacoes_legado" in corpo
    sql = inspect.getsource(NS.migrar_representacoes_legado)
    assert "NOT EXISTS" in sql and "representa_parte_id" in sql
    # Sem banco: o espelhamento legado→lista é o que a tela/teor leem após a migração.
    partes = NT.anexar_representacoes(
        [_parte(1, "PARTE A", "VENDEDOR"),
         _parte(90, "PROCURADORA X", "PROCURADORA",
                representa_parte_id=1, representa_instrumento=PROC_A)])
    assert partes[1]["representacoes"] == [
        {"representado_parte_id": 1, "instrumento": PROC_A}]
    outorgantes, _ = NT.partes_por_lado(
        [_parte(1, "PARTE A", "VENDEDOR"),
         _parte(2, "PARTE B", "COMPRADORA"),
         partes[1]],
        tipo_ato="ESCRITURA")
    assert outorgantes.count("PROCURADORA X") == 1
    assert PROC_A in outorgantes
