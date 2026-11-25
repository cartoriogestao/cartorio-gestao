"""O painel de conformidade do ONR (RI010) — o declarado, o que existe, o entregue com prova e o que falta.

O QUE ESTES TESTES GUARDAM
    * **Declarado sem lastro é divergência, nunca cumprido**: soma acima do total,
      Livro 4 declarado sem entrega, Livro 2 «disponível» sem a prova do CSL2.
    * **Só conta como entregue o que tem prova**: indicador ACEITO em PRODUCAO,
      carga que o IPS levou, CSL2 comprovado e importação informada como IMPORTADO.
      Enviado, em fila, em homologação e anulado não contam.
    * **Sem alarme falso**: sem número lançado nada acusa; o que o sistema não mede
      (polígono, ITN 003) não vira zero nem divergência; o ajuste só aparece na tela.
    * **O semáforo continua o do PR 466**: o painel entrega achados do gestor, e a
      cor sai deles — amarelo para obrigação sem prazo, verde com pendência de
      prazo longe, vermelho com pendência vencida.
    * **Não envia nada**: o painel não chama a API do ONR.

Dados inventados; datas fixas em novembro de 2026 (terça 10/11 é «hoje»).
"""
from __future__ import annotations

import sys
from datetime import date, datetime
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import conformidade as CF                     # noqa: E402
import gestor_checklist as CK                 # noqa: E402
import onr_conformidade as OC                 # noqa: E402
from bd_nativo import banco                   # noqa: E402
from conftest import cg_login                 # noqa: E402

HOJE = date(2026, 11, 10)
AGORA = datetime(2026, 11, 10, 9, 0, 0)
SENHA = "Senha#12345"


# --------------------------------------------------------------- auxiliares

def _ficha(db, numero, *, encerrada=0, teor="Teor de exemplo.", pdf=None, pendente=1,
           tipo_ficha="ESTRUTURADA", criado="2026-10-01T08:00:00", rural="U", sigef="") -> int:
    with db.transaction() as con:
        r = banco(con).escrever(
            """INSERT INTO ri_matriculas(numero, livro, livro_norm, tipo_ficha, encerrada, teor,
                                         digi_sha256, digi_onr_pendente, criado_em, rural_urbano, sigef)
               VALUES (%s,'2','2',%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id""",
            (str(numero), tipo_ficha, encerrada, teor, pdf, pendente, criado, rural, sigef))
        return int(r[0]["id"])


def _parte(db, matricula_id, nome="Parte Exemplo") -> None:
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO ri_partes(matricula_id, nome) VALUES (%s,%s)", (matricula_id, nome))


def _envio(db, matricula_id, situacao, ambiente="PRODUCAO", ident=None) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO ri_onr_envios(especie, ambiente, matricula_id, identificador, corpo_enviado,
                                         corpo_hash, situacao, enviado_em)
               VALUES ('INDICADOR',%s,%s,%s,'{}','h',%s,'2026-11-05T10:00:00')""",
            (ambiente, matricula_id, ident or f"ID{matricula_id}{ambiente}{situacao}", situacao))


def _carga(db, canal, tipo, situacao, quantos=10, gerado="2026-10-10T10:00:00",
           processado="2026-10-11T10:00:00") -> None:
    with db.transaction() as con:
        banco(con).escrever(
            """INSERT INTO ge_onr_cargas(canal, tipo, situacao, quantos, gerado_em, processado_em)
               VALUES (%s,%s,%s,%s,%s,%s)""", (canal, tipo, situacao, quantos, gerado, processado))


def _declarar(db, coluna, valor, lido="2026-11-09", origem="Tela de exemplo", por="Beatriz Exemplo"):
    with db.transaction() as con:
        return OC.lancar_declaracao(con, coluna=coluna, valor=valor, lido_em=lido, origem=origem,
                                    por=por, hoje=HOJE, agora=AGORA)


def _prova(db, coluna, quantos, situacao="IMPORTADO", visto="2026-11-09", protocolo="", por="Beatriz Exemplo"):
    with db.transaction() as con:
        return OC.lancar_prova(con, coluna=coluna, quantos=quantos, situacao=situacao, visto_em=visto,
                               protocolo_onr=protocolo, por=por, hoje=HOJE, agora=AGORA)


def _medir(db, hoje=HOJE) -> dict:
    with db.connect() as con:
        return OC.medir(con, hoje, AGORA)


def _obrigacao(painel, codigo) -> dict:
    return next(o for o in painel["obrigacoes"] if o["codigo"] == codigo)


def _celula(painel, coluna) -> dict:
    for o in painel["obrigacoes"]:
        for c in o["colunas"]:
            if c["codigo"] == coluna:
                return c
    raise KeyError(coluna)


def _codigos(painel, gravidade=None) -> set[str]:
    return {(d["codigo"], d["coluna"]) for d in painel["divergencias"]
            if gravidade is None or d["gravidade"] == gravidade}


def _o_caso_da_circular(db) -> None:
    """O desenho da Circular, com números inventados na mesma proporção."""
    for coluna, valor in (("TOTAL", 3770), ("L2_DIGITADAS", 7695), ("L2_DIGITALIZADAS", 6994),
                          ("L4", 1087), ("L5", 1087), ("DISP_L2", "Não"), ("DISP_L4", "Não"),
                          ("DISP_L5", "Não"), ("ITN_MATRICULAS", 0), ("ITN_ACERVO", 0), ("ITN_ATOS", 0),
                          ("POLIGONOS", 9)):
        _declarar(db, coluna, valor)


def _rodada_valida(db) -> None:
    with db.transaction() as con:
        banco(con).escrever(
            "INSERT INTO ge_execucoes(iniciada_em, terminada_em, hoje, erro) VALUES (%s,%s,%s,NULL)",
            ("2026-11-10T07:30:00", "2026-11-10T07:35:00", "2026-11-10"))


def _grava_achados(db, achados, visto="2026-11-10T07:30:00") -> None:
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever("DELETE FROM ge_achados")
        for a in achados:
            bd.escrever(
                "INSERT INTO ge_achados(chave, regra, gravidade, setor, titulo, prazo, primeiro_visto_em, "
                "ultimo_visto_em) VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                (a["chave"], a["regra"], a["gravidade"], a["setor"], a["titulo"], a["prazo"], visto, visto))


def _achados(db):
    with db.connect() as con:
        return OC.achados_para_o_gestor(con, HOJE)


def _cor_do_ri(db) -> str:
    with db.connect() as con:
        return CF.medir(con, HOJE)["areas"]["RI"]["cor"]


def _pendencia(db, **kw) -> int:
    base = dict(obrigacao="PROV143", titulo="Corrigir o Cronograma", responsavel="Carla Exemplo",
                prazo="2026-12-03", protocolo_onr="ONR-0001", por="Beatriz Exemplo", hoje=HOJE, agora=AGORA)
    base.update(kw)
    with db.transaction() as con:
        return OC.abrir_pendencia(con, **base)


# ------------------------------------------------- o catálogo é coerente

def test_o_catalogo_tem_uma_obrigacao_para_cada_coluna_e_origem_para_o_formulario():
    obrigacoes = {c for c, _ in OC.OBRIGACOES}
    for codigo, d in OC.COLUNAS.items():
        assert d["obrigacao"] in obrigacoes, codigo
        assert d["origem"] and d["rotulo"], codigo
    assert OC.CANAL_PROPRIO <= set(OC.COLUNAS)
    assert set(OC.DISPONIBILIDADE) | set(OC.DISPONIBILIDADE.values()) <= set(OC.COLUNAS)
    assert "TOTAL" not in OC.COM_PROVA_INFORMADA and "DISP_L2" not in OC.COM_PROVA_INFORMADA


# ----------------------------------------------- sem número, nada acusa

def test_sem_numero_lancado_nada_acusa_e_o_semaforo_nao_muda(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1)
    painel = _medir(db)
    assert {o["veredito"] for o in painel["obrigacoes"]} == {OC.SEM_DECLARACAO}
    assert painel["divergencias"] == [] and painel["resumo"]["sem_declaracao"] == 3
    assert _achados(db) == []
    with db.connect() as con:
        c = OC.contagem_para_a_checklist(con, HOJE)
    assert c["n"] == 0 and "nenhum número lançado" in c["texto"]
    _rodada_valida(db)
    assert _cor_do_ri(db) == CF.VERDE


# ----------------------------------------- o caso da Circular, em miniatura

def test_declarado_sem_lastro_vira_divergencia_e_nunca_cumprido(cg_casa):
    db = cg_casa["db"]
    for n in range(1, 6):
        _ficha(db, n)
    _o_caso_da_circular(db)
    painel = _medir(db)
    pares = _codigos(painel, "DIVERGENCIA")
    # soma acima do total (digitadas e digitalizadas)
    assert ("SOMA_ACIMA_DO_TOTAL", "L2_DIGITADAS") in pares
    assert ("SOMA_ACIMA_DO_TOTAL", "L2_DIGITALIZADAS") in pares
    # Livro 4 declarado, nada entregue; e o Livro 2 digitalizado também não tem entrega provada
    assert ("SEM_ENTREGA", "L4") in pares
    assert ("SEM_ENTREGA", "L2_DIGITALIZADAS") in pares
    p143 = _obrigacao(painel, "PROV143")
    assert p143["veredito"] == OC.DIVERGENTE and p143["veredito"] != OC.EM_DIA
    assert p143["painel"]["situacao"] == "INADIMPLENTE"
    l4 = _celula(painel, "L4")
    assert (l4["declarado"]["valor"], l4["entregue"]["valor"], l4["situacao"]) == (1087, 0, "SEM_LASTRO")
    assert l4["falta"] == 3770            # a referência é o total declarado, não o do sistema
    assert _celula(painel, "L2_DIGITALIZADAS")["situacao"] == "ACIMA_DO_TOTAL"


def test_o_que_o_sistema_nao_mede_nao_vira_zero_nem_divergencia(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1)
    _o_caso_da_circular(db)
    painel = _medir(db)
    # Prov. 195: o painel dá adimplente com 9; o sistema não guarda polígono -> sem acusação
    p195 = _obrigacao(painel, "PROV195")
    assert p195["veredito"] == OC.EM_DIA_NO_PAINEL and p195["divergencias"] == []
    pol = _celula(painel, "POLIGONOS")
    assert pol["sistema"]["valor"] is None and pol["entregue"]["valor"] is None and pol["falta"] is None
    # ITN 003: zero no painel é a falta de verdade, e não uma divergência
    itn = _obrigacao(painel, "ITN003")
    assert itn["veredito"] == OC.FALTA and itn["painel"]["situacao"] == "INADIMPLENTE"
    assert not [d for d in itn["divergencias"] if d["gravidade"] == "DIVERGENCIA"]
    assert _celula(painel, "ITN_MATRICULAS")["falta"] == 1       # 1 ficha vigente, 0 recebida


def test_livro2_disponivel_sem_a_prova_do_csl2_e_divergencia_e_a_prova_a_desfaz(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1, pdf="a" * 64, pendente=0)             # a marca baixou, mas o CSL2 não foi provado
    _declarar(db, "TOTAL", 1)
    _declarar(db, "DISP_L2", "Sim")
    painel = _medir(db)
    assert ("LIVRO2_DISPONIVEL_SEM_CSL2", "DISP_L2") in _codigos(painel, "DIVERGENCIA")
    assert _celula(painel, "L2_DIGITALIZADAS")["entregue"]["valor"] == 0
    with db.transaction() as con:
        banco(con).escrever("INSERT INTO settings(key, value) VALUES ('onr_csl2_desde', '2026-10-20') "
                            "ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value")
    painel = _medir(db)
    assert ("LIVRO2_DISPONIVEL_SEM_CSL2", "DISP_L2") not in _codigos(painel)
    assert _celula(painel, "L2_DIGITALIZADAS")["entregue"]["valor"] == 1


def test_livro2_no_papel_sem_csl2_nao_conta_a_pasta_de_conversao(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1, pdf="a" * 64, pendente=1)
    painel = _medir(db)
    cel = _celula(painel, "L2_DIGITALIZADAS")
    assert cel["entregue"]["valor"] == 0 and "CSL2" in cel["entregue"]["nota"]
    assert cel["sistema"]["valor"] == 1                  # existe aqui; existir aqui não é estar no ONR


# --------------------------------------------- o que conta como entregue

def test_so_o_indicador_aceito_em_producao_conta_como_entregue(cg_casa):
    db = cg_casa["db"]
    ids = [_ficha(db, n) for n in range(1, 7)]
    _envio(db, ids[0], "ACEITO")
    _envio(db, ids[1], "ACEITO")
    _envio(db, ids[2], "ENVIADO")                        # em fila: não conta
    _envio(db, ids[3], "RECUSADO")
    _envio(db, ids[4], "ACEITO", ambiente="HOMOLOGACAO")  # teste: não conta
    _declarar(db, "TOTAL", 6)
    _declarar(db, "L4", 6)
    cel = _celula(_medir(db), "L4")
    assert cel["entregue"]["valor"] == 2 and cel["entregue"]["em_andamento"] == 1
    assert (cel["declarado"]["valor"], cel["falta"], cel["situacao"]) == (6, 4, "SEM_LASTRO")


def test_a_importacao_informada_so_conta_quando_o_portal_diz_importado(cg_casa):
    db = cg_casa["db"]
    for n in range(1, 4):
        _ficha(db, n)
    _declarar(db, "TOTAL", 3)
    _prova(db, "L4", 2, "PROCESSANDO")
    _prova(db, "L4", 1, "NAO_IMPORTADO")
    cel = _celula(_medir(db), "L4")
    assert cel["entregue"]["valor"] == 0 and cel["entregue"]["em_andamento"] == 2
    assert cel["entregue"]["nao_importado"] == 1
    pid = _prova(db, "L4", 3, "IMPORTADO", protocolo="ONR-77")
    cel = _celula(_medir(db), "L4")
    assert cel["entregue"]["valor"] == 3 and cel["falta"] == 0
    assert "ONR-77" in cel["entregue"]["fontes"][-1]["rotulo"]
    with db.transaction() as con:
        OC.anular_prova(con, pid, motivo="lancada por engano", por="Beatriz Exemplo", agora=AGORA)
    assert _celula(_medir(db), "L4")["entregue"]["valor"] == 0
    with db.transaction() as con, pytest.raises(OC.PainelOnrError):
        OC.anular_prova(con, pid, motivo="de novo", por="Beatriz Exemplo")


def test_as_fontes_nao_se_somam_vale_a_maior(cg_casa):
    db = cg_casa["db"]
    ids = [_ficha(db, n) for n in range(1, 4)]
    _envio(db, ids[0], "ACEITO")
    _prova(db, "L4", 2, "IMPORTADO")
    cel = _celula(_medir(db), "L4")
    assert cel["entregue"]["valor"] == 2                 # e não 3: podem ser as mesmas matrículas
    assert len(cel["entregue"]["fontes"]) == 2


def test_o_livro5_levado_pelo_ips_conta_as_fichas_ja_existentes_na_carga(cg_casa):
    db = cg_casa["db"]
    antigas = [_ficha(db, n, criado="2026-10-01T08:00:00") for n in (1, 2)]
    nova = _ficha(db, 3, criado="2026-11-01T08:00:00")
    sem_parte = _ficha(db, 4, criado="2026-10-01T08:00:00")
    for fid in antigas + [nova]:
        _parte(db, fid)
    _carga(db, "PESSOAL", "COMPLETA", "PROCESSADO", quantos=3, processado="2026-10-11T10:00:00")
    _carga(db, "PESSOAL", "INCREMENTAL", "NA_PASTA", quantos=1)
    _declarar(db, "TOTAL", 4)
    _declarar(db, "L5", 1)
    cel = _celula(_medir(db), "L5")
    assert cel["entregue"]["valor"] == 2 and cel["sistema"]["valor"] == 3
    assert cel["entregue"]["em_andamento"] == 1           # o arquivo parado na pasta não conta
    assert "aceito" in cel["entregue"]["nota"]
    assert sem_parte                                       # ficha sem parte não entra
    # declarado (1) abaixo do levado (2): ajuste na tela, não divergência
    painel = _medir(db)
    assert ("DECLARADO_ABAIXO_DA_ENTREGA", "L5") in _codigos(painel, "AJUSTE")
    assert ("DECLARADO_ABAIXO_DA_ENTREGA", "L5") not in _codigos(painel, "DIVERGENCIA")
    assert cel["situacao"] == "ABAIXO_DA_ENTREGA"


def test_a_pergunta_nao_com_entrega_provada_pede_ajuste_sem_alarme(cg_casa):
    db = cg_casa["db"]
    ids = [_ficha(db, n) for n in (1, 2)]
    for fid in ids:
        _parte(db, fid)
    _carga(db, "PESSOAL", "COMPLETA", "PROCESSADO")
    _declarar(db, "DISP_L5", "Não")
    painel = _medir(db)
    assert ("PERGUNTA_ABAIXO_DA_ENTREGA", "DISP_L5") in _codigos(painel, "AJUSTE")
    assert _achados(db) == []                              # ajuste não vira achado


def test_acervo_declarado_diferente_do_sistema_e_ajuste_e_declaracao_antiga_tambem(cg_casa):
    db = cg_casa["db"]
    for n in range(1, 4):
        _ficha(db, n)
    _ficha(db, 4, encerrada=1)
    _declarar(db, "TOTAL", 10, lido="2026-10-01")
    painel = _medir(db)
    cel = _celula(painel, "TOTAL")
    assert cel["situacao"] == "DIFERE_DO_SISTEMA" and cel["sistema"]["valor"] == 4
    assert "3 vigentes" in cel["sistema"]["nota"]
    assert {("TOTAL_DIFERENTE_DO_SISTEMA", "TOTAL"), ("DECLARACAO_ANTIGA", "TOTAL")} <= _codigos(painel, "AJUSTE")
    assert _achados(db) == []


def test_ficha_arquivada_nao_entra_na_conta(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1)
    _ficha(db, 904020, encerrada=1)
    assert _medir(db)["obrigacoes"][0]["colunas"][0]["sistema"]["valor"] == 1


# ------------------------------------------------------ a ligação ao semáforo

def test_obrigacao_sem_responsavel_e_prazo_deixa_o_ri_amarelo_e_a_pendencia_decide_a_cor(cg_casa):
    db = cg_casa["db"]
    for n in range(1, 4):
        _ficha(db, n)
    _o_caso_da_circular(db)
    _rodada_valida(db)
    achados = _achados(db)
    por_regra = {}
    for a in achados:
        por_regra.setdefault(a["regra"], []).append(a)
    assert {a["gravidade"] for a in por_regra[OC.REGRA_DIVERGENCIA]} == {"ATENCAO"}
    assert {a["chave"] for a in por_regra[OC.REGRA_OBRIGACAO]} == {"ONR_PAINEL_OBR:PROV143", "ONR_PAINEL_OBR:ITN003"}
    assert all(a["gravidade"] == "PRAZO" and a["prazo"] is None for a in por_regra[OC.REGRA_OBRIGACAO])
    assert all(a["setor"] == "RI" for a in achados)
    _grava_achados(db, achados)
    assert _cor_do_ri(db) == CF.AMARELO                    # ninguém com prazo: a área acende

    # alguém assume as duas obrigações, com o prazo da Circular longe: o RI deixa de acender,
    # e a divergência continua à vista (ATENCAO é contado, não pinta)
    _pendencia(db, obrigacao="PROV143", prazo="2026-12-03")
    _pendencia(db, obrigacao="ITN003", titulo="Pedir o schema ao ONR", prazo="2026-12-03")
    achados = _achados(db)
    assert not [a for a in achados if a["regra"] == OC.REGRA_OBRIGACAO]
    _grava_achados(db, achados)
    assert _cor_do_ri(db) == CF.VERDE
    assert CF.medir(db.connect().__enter__(), HOJE)["areas"]["RI"]["atencao"] >= 4


def test_pendencia_vencida_deixa_o_ri_vermelho_e_sem_prazo_so_atencao(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1)
    _declarar(db, "ITN_MATRICULAS", 0)
    _rodada_valida(db)
    _pendencia(db, obrigacao="ITN003", titulo="Vencida", prazo="2026-11-09")
    _pendencia(db, obrigacao="ITN003", titulo="Sem prazo", prazo="", protocolo_onr="", responsavel="")
    achados = {a["chave"]: a for a in _achados(db)}
    gravidades = sorted(a["gravidade"] for a in achados.values() if a["regra"] == OC.REGRA_PENDENCIA)
    assert gravidades == ["ATENCAO", "VENCIDO"]
    _grava_achados(db, list(achados.values()))
    assert _cor_do_ri(db) == CF.VERMELHO
    sem_prazo = next(a for a in achados.values() if "(sem prazo)" in a["titulo"])
    assert "responsável" in sem_prazo["detalhe"] and "protocolo" in sem_prazo["detalhe"] \
        and "comprovante" in sem_prazo["detalhe"]


def test_as_regras_do_painel_sao_do_oficial_e_nao_viram_tarefa_de_escrevente():
    import gestor_rotina as GR
    for regra in OC.ROTULOS:
        assert regra in GR.ROTULOS and regra in GR.REGRAS_SEM_TAREFA and regra in GR.REGRAS_DAS_CENTRAIS
    import gestor_didatica as GD
    for regra in OC.ROTULOS:
        assert GD.onde_da_regra(regra)[1] == "/ri/onr/conformidade"


def test_a_conferencia_do_gestor_entrega_os_achados_do_painel(cg_casa, monkeypatch):
    """`gestor_cargas_ri.conferir` chama o painel; aqui só se prova que a ligação existe e não derruba."""
    import gestor_cargas_ri as GCR
    import onr_api as API
    monkeypatch.setattr(API, "tem_credencial", lambda *a, **k: True)
    db = cg_casa["db"]
    _ficha(db, 1)
    _declarar(db, "L4", 5)
    _declarar(db, "TOTAL", 5)
    with db.transaction() as con:
        achados = GCR.conferir(con, HOJE)
    ours = [a for a in achados if a["regra"] in OC.ROTULOS]
    assert {"ONR_PAINEL_DIV:SEM_ENTREGA:L4"} <= {a["chave"] for a in ours}
    assert GCR.ROTULOS[OC.REGRA_DIVERGENCIA]


def test_a_checklist_mostra_a_linha_do_painel_com_a_contagem(cg_casa):
    db = cg_casa["db"]
    _ficha(db, 1)
    _declarar(db, "TOTAL", 1)
    _declarar(db, "L4", 1)
    linhas = [c for c in CK.CONFERENCIAS if c[0] == "PAINEL_ONR"]
    assert linhas and linhas[0][2] == "ri_onr_conformidade"
    with db.connect() as con:
        c = CK._conta_painel_onr(con, HOJE)
    assert c["n"] == 1 and "sem lastro" in c["texto"]
    c2 = cg_casa["c"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    cg_login(c2, "mario", SENHA)
    html = c2.get("/administrativo/gestor/checklist").get_data(as_text=True)
    assert "Painel de conformidade do ONR" in html and "/ri/onr/conformidade" in html


# --------------------------------------------------------- lançamentos

def test_o_lancamento_recusa_o_que_nao_se_le(cg_casa):
    db = cg_casa["db"]
    ruins = [
        dict(coluna="NAO_EXISTE", valor="1"),
        dict(coluna="L4", valor="-5"),
        dict(coluna="L4", valor="muitos"),
        dict(coluna="L4", valor="10", lido="2026-11-11"),       # futuro
        dict(coluna="L4", valor="10", lido="10/11/2026"),       # formato
        dict(coluna="L4", valor="10", origem=""),
        dict(coluna="DISP_L4", valor="talvez"),
    ]
    for r in ruins:
        with db.transaction() as con, pytest.raises(OC.PainelOnrError):
            OC.lancar_declaracao(con, coluna=r["coluna"], valor=r["valor"], lido_em=r.get("lido", "2026-11-09"),
                                 origem=r.get("origem", "Tela"), por="Beatriz", hoje=HOJE)
    with db.transaction() as con, pytest.raises(OC.PainelOnrError):
        OC.lancar_prova(con, coluna="TOTAL", quantos=1, situacao="IMPORTADO", visto_em="2026-11-09", por="B", hoje=HOJE)
    with db.transaction() as con, pytest.raises(OC.PainelOnrError):
        OC.lancar_prova(con, coluna="L4", quantos=1, situacao="PRONTO", visto_em="2026-11-09", por="B", hoje=HOJE)
    assert _medir(db)["resumo"]["sem_declaracao"] == 3


def test_lancar_de_novo_vale_o_ultimo_e_anular_volta_ao_anterior(cg_casa):
    db = cg_casa["db"]
    _declarar(db, "L4", 10)
    segundo = _declarar(db, "L4", 20)
    assert _celula(_medir(db), "L4")["declarado"]["valor"] == 20
    with db.transaction() as con:
        OC.anular_declaracao(con, segundo, motivo="digitei errado", por="Beatriz", agora=AGORA)
    cel = _celula(_medir(db), "L4")
    assert cel["declarado"]["valor"] == 10
    with db.connect() as con:
        assert len(OC.historico_de_declaracoes(con)) == 2     # nada se apaga


def test_o_declarado_traz_data_origem_e_quem_lancou(cg_casa):
    db = cg_casa["db"]
    _declarar(db, "L4", 7, lido="2026-11-08", origem="Cronograma de Dados – CNJ", por="Carla Exemplo")
    d = _celula(_medir(db), "L4")["declarado"]
    assert (d["lido_em"], d["origem"], d["lancado_por"]) == ("2026-11-08", "Cronograma de Dados – CNJ", "Carla Exemplo")
    assert d["lancado_em"].startswith("2026-11-10")


def test_pendencia_diz_o_que_falta_nela(cg_casa):
    db = cg_casa["db"]
    completa = _pendencia(db)
    vazia = _pendencia(db, titulo="Sem nada", responsavel="", prazo="", protocolo_onr="")
    with db.connect() as con:
        por_id = {p["id"]: p for p in OC.pendencias(con, HOJE)}
    assert por_id[completa]["sem_comprovante"] and not por_id[completa]["sem_protocolo"]
    f = por_id[vazia]
    assert f["sem_responsavel"] and f["sem_prazo"] and f["sem_protocolo"] and f["sem_comprovante"]
    with db.transaction() as con, pytest.raises(OC.PainelOnrError):
        OC.abrir_pendencia(con, obrigacao="PROV195", coluna="L4", titulo="x", por="B", hoje=HOJE)  # coluna de outra obrigação
    with db.transaction() as con:
        OC.atualizar_pendencia(con, vazia, responsavel="Carla Exemplo", prazo="2026-12-01",
                               protocolo_onr="ONR-9", hoje=HOJE)
        OC.encerrar_pendencia(con, completa, situacao="CONCLUIDA", motivo="feito", por="Beatriz", agora=AGORA)
    with db.connect() as con:
        abertas = OC.pendencias(con, HOJE)
    assert [p["id"] for p in abertas] == [vazia] and not abertas[0]["sem_protocolo"]
    with db.transaction() as con, pytest.raises(OC.PainelOnrError):
        OC.encerrar_pendencia(con, completa, situacao="CANCELADA", motivo="de novo", por="B")


# ------------------------------------------------------------------- as telas

def _entrar(cg_casa, usuario, papel):
    db = cg_casa["db"]
    db.create_user(usuario, f"{usuario.upper()} EXEMPLO", SENHA, papel)
    c = cg_casa["app"].test_client()
    cg_login(c, usuario, SENHA)
    return c


def _csrf(c) -> str:
    c.get("/ri/onr/conformidade")
    with c.session_transaction() as s:
        return s["csrf_token"]


def test_a_tela_mostra_as_quatro_colunas_e_a_divergencia(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _ficha(db, 1)
    _o_caso_da_circular(db)
    r = c.get("/ri/onr/conformidade")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for trecho in ("Declarado ao ONR", "Existe no sistema", "Entregue com prova", "Falta",
                   "declarado sem lastro", "soma acima do total", "Declarado sem lastro",
                   "não envia nada ao ONR", "lastro fora do sistema", "7.695", "1.087"):
        assert trecho in html, trecho
    assert "cumprido" not in html.split("Declarado sem lastro")[0].lower().replace("nunca como cumprido", "")


def test_lancar_pela_tela_grava_com_auditoria_e_recusa_o_invalido(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    token = _csrf(c)
    r = c.post("/ri/onr/conformidade/declaracao", data={
        "csrf_token": token, "coluna": "L4", "valor": "1.087", "lido_em": "2026-11-09",
        "origem": "Cronograma de Dados – CNJ", "observacao": ""})
    assert r.status_code == 302
    assert _celula(_medir(db, date.today()), "L4")["declarado"]["valor"] == 1087
    with db.connect() as con:
        assert banco(con).valor("SELECT count(*) FROM audit_logs WHERE action = 'ONR_CONFORMIDADE_DECLARACAO'") == 1
    r = c.post("/ri/onr/conformidade/declaracao", data={
        "csrf_token": token, "coluna": "L4", "valor": "abc", "lido_em": "2026-11-09", "origem": "x"},
        follow_redirects=True)
    assert "digite um número inteiro" in r.get_data(as_text=True)
    with db.connect() as con:
        assert banco(con).valor("SELECT count(*) FROM onr_declaracoes") == 1


def test_o_auditor_ve_e_imprime_mas_nao_lanca_e_o_balcao_nao_entra(cg_casa):
    auditor = _entrar(cg_casa, "carla", "AUDITOR")
    assert auditor.get("/ri/onr/conformidade").status_code == 200
    assert auditor.get("/ri/onr/conformidade/quadro").status_code == 200
    html = auditor.get("/ri/onr/conformidade").get_data(as_text=True)
    assert "Lançar o que foi declarado" not in html
    assert auditor.post("/ri/onr/conformidade/declaracao", data={"coluna": "L4", "valor": "1"}).status_code in (400, 403)
    balcao = _entrar(cg_casa, "joao", "USER")
    assert balcao.get("/ri/onr/conformidade").status_code == 403
    assert balcao.get("/ri/onr/conformidade/quadro").status_code == 403


def test_pendencia_com_comprovante_pela_tela_e_download(cg_casa_logada):
    import io
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    token = _csrf(c)
    c.post("/ri/onr/conformidade/pendencia", data={
        "csrf_token": token, "obrigacao": "ITN003", "titulo": "Pedir o schema ao ONR",
        "responsavel": "Carla Exemplo", "prazo": "2099-12-03", "protocolo_onr": "ONR-123"})
    with db.connect() as con:
        pid = int(banco(con).valor("SELECT id FROM onr_pendencias"))
    ruim = c.post(f"/ri/onr/conformidade/pendencia/{pid}/comprovante", data={
        "csrf_token": token, "arquivo": (io.BytesIO(b"x"), "virus.exe")},
        content_type="multipart/form-data", follow_redirects=True)
    assert "PDF ou imagem" in ruim.get_data(as_text=True)
    bom = c.post(f"/ri/onr/conformidade/pendencia/{pid}/comprovante", data={
        "csrf_token": token, "arquivo": (io.BytesIO(b"%PDF-1.4 exemplo"), "protocolo.pdf")},
        content_type="multipart/form-data")
    assert bom.status_code == 302
    with db.connect() as con:
        anexo = banco(con).um("SELECT id, stored_path, sha256 FROM attachments WHERE entity_type = 'ONR_PENDENCIA'")
        assert anexo and Path(anexo["stored_path"]).read_bytes() == b"%PDF-1.4 exemplo"
        p = OC.pendencias(con, HOJE)[0]
    assert not p["sem_comprovante"]
    assert c.get(f"/arquivo/{anexo['id']}").status_code == 200
    html = c.get("/ri/onr/conformidade").get_data(as_text=True)
    assert "protocolo.pdf" in html and anexo["sha256"][:12] in html


def test_o_quadro_para_imprimir_traz_data_e_origem_de_cada_numero(cg_casa_logada):
    db, c = cg_casa_logada["db"], cg_casa_logada["c"]
    _ficha(db, 1)
    _declarar(db, "L4", 1087, lido="2026-11-08", origem="Cronograma de Dados – CNJ (Ofício Eletrônico)",
              por="Carla Exemplo")
    _pendencia(db, titulo="Importar o Livro 4 no portal", protocolo_onr="ONR-555")
    r = c.get("/ri/onr/conformidade/quadro")
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    for trecho in ("Quadro de conformidade perante o ONR", "lido em 08/11/2026", "Cronograma de Dados – CNJ",
                   "lançado por Carla Exemplo", "Divergência", "sem lastro", "ONR-555", "Importar o Livro 4",
                   "Não foi enviado ao ONR"):
        assert trecho in html, trecho
    assert "<nav" not in html and "csrf_token" not in html       # página de papel: sem menu nem formulário


def test_o_quadro_em_pdf_usa_o_caminho_de_impressao_da_casa(cg_casa_logada, monkeypatch):
    import impressao_pdf as PDFIMP
    recebido = {}

    def falso(html, **k):
        recebido["html"], recebido["nome"] = html, k.get("nome")
        return b"%PDF-1.4 falso", "application/pdf", "quadro.pdf", "inline"

    monkeypatch.setattr(PDFIMP, "arquivo_de_html", falso)
    r = cg_casa_logada["c"].get("/ri/onr/conformidade/quadro/papel")
    assert r.status_code == 200 and r.data.startswith(b"%PDF")
    assert "Imprimir" not in recebido["html"] and recebido["nome"].startswith("quadro-onr-")


def test_o_painel_nao_chama_a_api_do_onr(cg_casa_logada, monkeypatch):
    import onr_api as API

    def proibido(*a, **k):
        raise AssertionError("o painel não pode chamar a API do ONR")

    for nome in dir(API):
        if nome in ("enviar_indicador", "atualizar_indicador", "fila", "esta_no_ar", "token", "obter_token"):
            monkeypatch.setattr(API, nome, proibido)
    c = cg_casa_logada["c"]
    for rota in ("/ri/onr/conformidade", "/ri/onr/conformidade/quadro"):
        assert c.get(rota).status_code == 200


def test_o_menu_oferece_o_painel_a_quem_pode_abrir():
    import navegacao as NAV
    achados = [i for m in NAV.MODULOS_DA_BARRA for _, itens in m["secoes"] for i in itens
               if i["endpoint"] == "ri_onr_conformidade"]
    assert achados and set(achados[0]["papeis"]) == {"ADMIN", "MANAGER", "AUDITOR"}


def test_o_codigo_nao_carrega_dado_de_serventia():
    """O repositório é público: nada de nome, cidade, CPF ou matrícula real nos arquivos do painel."""
    import re
    for nome in ("onr_conformidade.py", "onr_conformidade_web.py", "onr_conformidade_schema.py",
                 "templates/onr_conformidade.html", "templates/onr_conformidade_quadro.html"):
        texto = (RAIZ / nome).read_text(encoding="utf-8")
        assert not re.search(r"\b\d{3}\.\d{3}\.\d{3}-\d{2}\b", texto), nome
        assert not re.search(r"\bCNS\s*\d{6}\b", texto), nome
