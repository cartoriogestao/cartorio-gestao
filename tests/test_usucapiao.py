"""
Testes do usucapiao extrajudicial — o rito, o que falta e o dossie da IA.

O QUE ELES CONFEREM
    A regra, e nao "a funcao devolveu alguma coisa":

      - nao se pula etapa do rito: cada fase protege alguem, e registro com
        fase pulada nasce nulo;
      - juntar peca move o checklist sozinho — pedir para juntar e depois
        marcar a mesma coisa e o jeito de as duas divergirem;
      - dispensar item do rito exige motivo escrito; ignorar nao e dispensar;
      - nao se reconhece usucapiao com item pendente;
      - o dossie MASCARA documento por padrao — dossie que sai da casa e papel
        que sai da casa;
      - a IA nao decide: decisao apoiada em analise nao conferida e recusada;
      - decidir nao e registrar: decisao procedente deixa o processo andando
        ate o registro sair.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import usucapiao as US                            # noqa: E402
from ri_schema import init_ri_schema               # noqa: E402
from us_schema import init_us_schema               # noqa: E402

AGORA = "2026-08-24T09:00:00"
HOJE = "2026-08-24"
SV = {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro"}


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    con.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY)")
    con.execute("""CREATE TABLE IF NOT EXISTS ri_importacoes
                   (id INTEGER PRIMARY KEY)""")
    init_ri_schema(con)
    init_us_schema(con)
    # COM A TRAVA DE CHAVE ESTRANGEIRA LIGADA, como na produção.
    #
    # Ela estava desligada, e por isso este arquivo deixou passar um defeito
    # que só o teste de TELA pegou: registrar em ato inexistente subia
    # `IntegrityError` — HTTP 500 no fim de um processo de meses. Teste que
    # roda com trava diferente da produção testa outro sistema.
    con.execute("PRAGMA foreign_keys = ON")
    return con


def _um_ato_de_ri(con) -> int:
    """Um ato de verdade no RI, para o registro ter a que se amarrar."""
    con.execute("""INSERT INTO ri_matriculas(numero, criado_em)
                   VALUES ('4014', ?)""", (AGORA,))
    mid = con.execute("SELECT id FROM ri_matriculas").fetchone()[0]
    con.execute(
        """INSERT INTO ri_atos(matricula_id, tipo, numero, hash_ato, lavrado_em)
           VALUES (?, 'R', 1, 'abc', ?)""", (mid, AGORA))
    return con.execute("SELECT id FROM ri_atos").fetchone()[0]


def _autuar(con, modalidade="EXTRAORDINARIA", numero="US-2026-001"):
    return US.autuar(con, numero=numero, modalidade=modalidade, agora=AGORA,
                     requerente_nome="MARIA DA SILVA",
                     requerente_documento="12345678901",
                     imovel_descricao="Lote 4 da Quadra B",
                     imovel_municipio="Cidade Exemplo", usuario="TESTE")


def _cumprir_tudo(con, processo_id):
    for item in US.conferir(con, processo_id)["pendentes"]:
        US.marcar_item(con, processo_id, item["item"], estado="CUMPRIDO",
                       agora=AGORA, usuario="TESTE")


# ------------------------------------------------------------- autuação


def test_autua_com_o_checklist_da_modalidade_ja_montado():
    # A tela tem de mostrar o que falta desde o primeiro dia, e não vazio até
    # alguém clicar.
    con = banco()
    pid = _autuar(con)
    p = US.processo(con, pid)
    assert p["etapa"] == "AUTUACAO"
    assert p["situacao"] == "EM_ANDAMENTO"
    conf = US.conferir(con, pid)
    assert conf["itens"]
    assert all(i["estado"] == "PENDENTE" for i in conf["itens"])
    assert not conf["pronto_para_decidir"]


def test_a_modalidade_muda_o_checklist():
    # Especial urbana tem limite de área e exige não ter outro imóvel; a
    # extraordinária não.
    con = banco()
    extra = US.checklist_da_modalidade("EXTRAORDINARIA")
    urbana = US.checklist_da_modalidade("ESPECIAL_URBANA")
    assert len(urbana) > len(extra)
    itens = {c["item"] for c in urbana} - {c["item"] for c in extra}
    assert itens == {"AREA_LIMITE", "NAO_PROPRIETARIO"}


def test_modalidade_inventada_e_recusada():
    con = banco()
    with pytest.raises(US.UsucapiaoError, match="não existe"):
        US.autuar(con, numero="X", modalidade="POR_MERECIMENTO", agora=AGORA)


def test_numero_repetido_e_recusado():
    con = banco()
    _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="Já existe processo"):
        _autuar(con)


# ---------------------------------------------------------- as peças


def test_juntar_peca_move_o_checklist_sozinho():
    con = banco()
    pid = _autuar(con)
    US.juntar_peca(con, pid, tipo="ATA_NOTARIAL", agora=AGORA,
                   descricao="Ata do 1º Tabelionato", usuario="TESTE")
    conf = US.conferir(con, pid)
    ata = next(i for i in conf["itens"] if i["item"] == "ATA_NOTARIAL")
    assert ata["estado"] == "CUMPRIDO"
    # e o movimento ficou nos autos
    assert any(m["tipo"] == "JUNTADA" for m in US.movimentos(con, pid))


def test_tipo_de_peca_desconhecido_e_recusado():
    con = banco()
    pid = _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="Tipo de peça desconhecido"):
        US.juntar_peca(con, pid, tipo="FOTO_DO_QUINTAL", agora=AGORA)


# -------------------------------------------------------- a conferência


def test_dispensar_item_exige_motivo_escrito():
    # Dispensar item do rito é decisão do oficial; decisão sem motivo é o que a
    # inspeção aponta.
    con = banco()
    pid = _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="motivo escrito"):
        US.marcar_item(con, pid, "JUSTO_TITULO", estado="DISPENSADO",
                       agora=AGORA, motivo="não tem")


def test_dispensar_com_motivo_conta_como_resolvido():
    con = banco()
    pid = _autuar(con)
    US.marcar_item(con, pid, "JUSTO_TITULO", estado="DISPENSADO", agora=AGORA,
                   motivo="Posse extraordinária: o art. 216-A, IV dispensa o "
                          "justo título nesta modalidade.")
    conf = US.conferir(con, pid)
    assert len(conf["dispensados"]) == 1
    assert not any(i["item"] == "JUSTO_TITULO" for i in conf["pendentes"])


# ---------------------------------------------------------- as etapas


def test_nao_se_pula_etapa_do_rito():
    # Cada fase protege alguém — o confrontante, o ente público, o terceiro do
    # edital. Registro com fase pulada nasce nulo.
    con = banco()
    pid = _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="pular a etapa"):
        US.avancar(con, pid, etapa="EDITAL", agora=AGORA)


def test_avanca_uma_etapa_de_cada_vez_e_registra_o_movimento():
    con = banco()
    pid = _autuar(con)
    US.avancar(con, pid, etapa="CONFERENCIA", agora=AGORA, usuario="TESTE")
    assert US.processo(con, pid)["etapa"] == "CONFERENCIA"
    US.avancar(con, pid, etapa="NOTIFICACAO", agora=AGORA)
    assert US.processo(con, pid)["etapa"] == "NOTIFICACAO"


def test_voltar_etapa_e_permitido():
    # Diligência nova pode devolver o processo a uma fase anterior.
    con = banco()
    pid = _autuar(con)
    US.avancar(con, pid, etapa="CONFERENCIA", agora=AGORA)
    US.avancar(con, pid, etapa="AUTUACAO", agora=AGORA)
    assert US.processo(con, pid)["etapa"] == "AUTUACAO"


def test_etapas_faltantes_lista_o_que_vem_pela_frente():
    con = banco()
    pid = _autuar(con)
    faltam = US.etapas_faltantes(con, pid)
    assert [f["etapa"] for f in faltam][:3] == ["CONFERENCIA", "NOTIFICACAO",
                                                "CIENCIA_ENTES"]
    assert faltam[-1]["etapa"] == "REGISTRO"


# ----------------------------------------------------- próximos passos


def test_proximos_passos_manda_obter_o_que_falta():
    con = banco()
    pid = _autuar(con)
    passos = US.proximos_passos(con, pid, HOJE)
    assert any("Ata notarial" in p["passo"] for p in passos)
    # e diz POR QUE, com o dispositivo
    assert any("216-A" in p["porque"] for p in passos)


def test_prazo_vencido_vira_passo_urgente():
    con = banco()
    pid = _autuar(con)
    US.movimentar(con, pid, tipo="NOTIFICACAO",
                  descricao="Notificado o confrontante do lado leste.",
                  destinatario="JOÃO DO LADO", destinatario_papel="CONFRONTANTE",
                  prazo_dias=15, prazo_inicio="2026-08-01",
                  prazo_fim="2026-08-16", agora=AGORA)
    passos = US.proximos_passos(con, pid, HOJE)
    certificar = [p for p in passos if "decurso do prazo" in p["passo"]]
    assert certificar
    assert certificar[0]["urgencia"] == 3
    assert "silêncio tem efeito" in certificar[0]["porque"]


def test_impugnacao_manda_remeter_ao_juizo():
    # O oficial não julga impugnação — art. 216-A, § 10.
    con = banco()
    pid = _autuar(con)
    US.movimentar(con, pid, tipo="NOTIFICACAO", descricao="Notificado.",
                  destinatario="VIZINHO", resposta="IMPUGNOU", agora=AGORA)
    passos = US.proximos_passos(con, pid, HOJE)
    assert any("Remeter os autos ao juízo" in p["passo"] for p in passos)


def test_processo_finalizado_nao_tem_proximo_passo():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="IMPROCEDENTE",
               fundamento="A posse alegada não alcança o prazo da modalidade.",
               teor="INDEFIRO o pedido.", agora=AGORA)
    passos = US.proximos_passos(con, pid, HOJE)
    assert len(passos) == 1
    assert "Nada a fazer" in passos[0]["passo"]


# ------------------------------------------------------------ o dossiê


def test_o_dossie_mascara_documento_por_padrao():
    # Dossiê que sai da casa é papel que sai da casa — mesmo que o destino
    # seja uma ferramenta.
    con = banco()
    pid = _autuar(con)
    d = US.montar_dossie(con, pid, hoje=HOJE)
    assert "12345678901" not in d["texto"]
    assert d["mascarado"] is True
    assert "Documentos mascarados" in d["texto"]


def test_o_dossie_sem_mascara_avisa_no_proprio_texto():
    # Quem receber tem de saber o que tem em mãos.
    con = banco()
    pid = _autuar(con)
    d = US.montar_dossie(con, pid, hoje=HOJE, mascarar=False)
    assert "12345678901" in d["texto"]
    assert "NÃO mascarados" in d["texto"]


def test_o_dossie_leva_pecas_checklist_andamento_e_o_que_falta():
    con = banco()
    pid = _autuar(con)
    US.juntar_peca(con, pid, tipo="ATA_NOTARIAL", agora=AGORA,
                   teor="Compareceu a requerente e declarou posse mansa desde 2005.")
    d = US.montar_dossie(con, pid, hoje=HOJE)
    t = d["texto"]
    assert "Peças juntadas (1)" in t
    assert "posse mansa desde 2005" in t          # o teor vai junto
    assert "Conferência do rito" in t
    assert "O que falta" in t
    assert "Andamento" in t
    assert d["pecas"] == 1


def test_o_dossie_pede_analise_e_proibe_a_decisao():
    # A IA auxilia; quem decide é o oficial. O pedido diz isso.
    con = banco()
    pid = _autuar(con)
    t = US.montar_dossie(con, pid, hoje=HOJE)["texto"]
    assert "Não redija a decisão" in t
    assert "a decisão é do oficial registrador" in t


def test_o_sha256_muda_quando_o_processo_muda():
    # É ele que amarra a análise ao que foi mandado.
    con = banco()
    pid = _autuar(con)
    antes = US.montar_dossie(con, pid, hoje=HOJE)["sha256"]
    US.juntar_peca(con, pid, tipo="PLANTA", agora=AGORA)
    assert US.montar_dossie(con, pid, hoje=HOJE)["sha256"] != antes


# ------------------------------------------------------ a análise da IA


def test_a_analise_entra_por_conferir():
    con = banco()
    pid = _autuar(con)
    aid = US.registrar_analise(con, pid, parecer="Falta a ART do profissional.",
                               ferramenta="IA de teste", agora=AGORA)
    a = US.analises(con, pid)[0]
    assert a["id"] == aid
    assert a["conferida_por_humano"] == 0
    assert any(m["tipo"] == "ANALISE_IA" for m in US.movimentos(con, pid))


def test_parecer_vazio_nao_entra():
    con = banco()
    pid = _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="veio vazio"):
        US.registrar_analise(con, pid, parecer="   ", agora=AGORA)


def test_decidir_apoiado_em_analise_nao_conferida_e_recusado():
    # A decisão é ato do delegatário, e ato de delegatário não se delega a uma
    # ferramenta.
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    aid = US.registrar_analise(con, pid, parecer="Está tudo certo.", agora=AGORA)
    with pytest.raises(US.UsucapiaoError, match="ainda não foi conferida"):
        US.decidir(con, pid, sentido="PROCEDENTE", analise_id=aid,
                   fundamento="A posse está comprovada pelos documentos.",
                   teor="RECONHEÇO a usucapião.", agora=AGORA)


def test_depois_de_conferida_a_analise_a_decisao_passa():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    aid = US.registrar_analise(con, pid, parecer="Está tudo certo.", agora=AGORA)
    US.conferir_analise(con, aid, agora=AGORA, usuario="TESTE")
    did = US.decidir(con, pid, sentido="PROCEDENTE", analise_id=aid,
                     fundamento="A posse está comprovada pelos documentos.",
                     teor="RECONHEÇO a usucapião.", agora=AGORA)
    assert did


# ------------------------------------------------------------ a decisão


def test_nao_se_reconhece_usucapiao_com_item_pendente():
    con = banco()
    pid = _autuar(con)
    with pytest.raises(US.UsucapiaoError, match="item\\(ns\\) do rito pendente"):
        US.decidir(con, pid, sentido="PROCEDENTE",
                   fundamento="A posse está comprovada pelos documentos.",
                   teor="RECONHEÇO.", agora=AGORA)


def test_decisao_sem_fundamento_e_recusada():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    with pytest.raises(US.UsucapiaoError, match="fundamento"):
        US.decidir(con, pid, sentido="PROCEDENTE", fundamento="ok",
                   teor="RECONHEÇO.", agora=AGORA)


def test_os_modelos_vem_preenchidos_e_marcam_o_que_falta_completar():
    con = banco()
    pid = _autuar(con)
    modelos = US.modelos_de_decisao(US.processo(con, pid), SV)
    assert set(modelos) == set(US.SENTIDOS)
    assert "US-2026-001" in modelos["PROCEDENTE"]
    assert "MARIA DA SILVA" in modelos["PROCEDENTE"]
    assert "MARIO EXEMPLO DOS SANTOS" in modelos["PROCEDENTE"]
    # e o modelo NÃO finge que o fundamento está pronto
    for texto in modelos.values():
        assert "[COMPLETAR" in texto


def test_decidir_nao_e_registrar():
    # Decisão procedente deixa o processo ANDANDO até o registro sair.
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="PROCEDENTE",
               fundamento="A posse está comprovada pelos documentos juntados.",
               teor="RECONHEÇO a usucapião.", agora=AGORA)
    p = US.processo(con, pid)
    assert p["situacao"] == "EM_ANDAMENTO"
    assert p["etapa"] == "DECISAO"
    assert any("Registrar o reconhecimento" in x["passo"]
               for x in US.proximos_passos(con, pid, HOJE))


def test_registrar_fecha_o_processo_e_amarra_o_ato():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="PROCEDENTE",
               fundamento="A posse está comprovada pelos documentos juntados.",
               teor="RECONHEÇO a usucapião.", agora=AGORA)
    ato_id = _um_ato_de_ri(con)
    US.registrar_reconhecimento(con, pid, ato_id=ato_id, agora=AGORA,
                                selo="REGAVD000000OD1Q8BV5TOOZE492")
    p = US.processo(con, pid)
    assert p["situacao"] == "REGISTRADO"
    assert p["etapa"] == "REGISTRO"
    assert US.decisoes(con, pid)[0]["ato_id"] == ato_id


def test_registrar_em_ato_que_nao_existe_da_frase_de_balcao():
    # Sem esta conferência, o INSERT batia na chave estrangeira e subia
    # `IntegrityError`. Quem achou foi o teste de TELA, porque aqui a trava de
    # FK estava desligada — e teste com trava diferente da produção testa
    # outro sistema.
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="PROCEDENTE",
               fundamento="A posse está comprovada pelos documentos juntados.",
               teor="RECONHEÇO a usucapião.", agora=AGORA)
    with pytest.raises(US.UsucapiaoError, match="Não existe ato 99999"):
        US.registrar_reconhecimento(con, pid, ato_id=99999, agora=AGORA)


def test_nao_se_registra_sem_decisao_procedente():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="EXIGENCIA",
               fundamento="Falta a ART do profissional que assinou a planta.",
               teor="NOTA DE EXIGÊNCIA.", agora=AGORA)
    with pytest.raises(US.UsucapiaoError, match="decisão procedente"):
        US.registrar_reconhecimento(con, pid, ato_id=77, agora=AGORA)


def test_processo_decidido_nao_se_movimenta_mais():
    con = banco()
    pid = _autuar(con)
    _cumprir_tudo(con, pid)
    US.decidir(con, pid, sentido="REMESSA_JUIZO",
               fundamento="Houve impugnação do confrontante do lado leste.",
               teor="REMETAM-SE os autos.", agora=AGORA)
    assert US.processo(con, pid)["situacao"] == "REMETIDO_AO_JUIZO"
    with pytest.raises(US.UsucapiaoError, match="não há mais o que movimentar"):
        US.movimentar(con, pid, tipo="JUNTADA", descricao="Mais um papel.",
                      agora=AGORA)