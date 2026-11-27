"""A008 (26/11/2026) — o envio automático do Acompanhamento Registral do ONR.

    O processo `RI_ONR_ACOMPANHAMENTO` da central de automação e as travas do
    envio (`onr_acompanhamento.avaliar`): carência, atrasados travados até a
    liberação, exigência só revisada (e bloqueada quando é rascunho ou não tem
    exigência), um «registrado» por (protocolo, ato, matrícula), validação do
    cadastro, título sem «prenotado», a chamada de prova de 1 título e os
    avisos. Dados inventados; o ONR é o de mentira de `test_onr_acompanhamento`.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import automacao_avisos as AV                                      # noqa: E402
import automacao_processos as PROC                                 # noqa: E402
import onr_acompanhamento as A                                     # noqa: E402
import onr_wsoficio as W                                           # noqa: E402
from bd_nativo import banco                                        # noqa: E402
from test_onr_acompanhamento import (AGORA, CERT, ONRDeMentira, _Db,  # noqa: E402,F401
                                     _cofre, _eventos, _revisar_as_exigencias, _soap, _token,
                                     con, pasta)

#: A sessão de verdade, antes de qualquer `monkeypatch` (o ONR é o de mentira).
_SessaoReal = W.Sessao


def _enviar(con, pasta, onr, **k):
    return A.enviar_pendentes(
        _Db(con), lambda: W.Sessao(ambiente=W.HOMOLOGACAO, pasta=pasta, transporte=onr,
                                   certificado=CERT),
        amb=W.HOMOLOGACAO, quem="beatriz", agora=lambda: AGORA, **k)


def _nota(con, nid=5, numero=1, data="2026-10-22", exigencias='["Recolher o ITBI."]',
          prazo="2026-11-17"):
    banco(con).escrever(
        "INSERT INTO ri_notas_devolutivas VALUES (%s, 10, %s, %s, %s, NULL, %s, 'ABERTA', "
        "NULL, %s)", (nid, numero, data, exigencias, prazo, f"{data}T16:00:00"))
    A.anotar_nota_de_exigencia(con, nid, agora=AGORA)
    con.commit()
    return banco(con).um("SELECT * FROM onr_at_eventos WHERE origem_id=%s AND evento='EXIGENCIA'",
                         (nid,))


class Recusa(ONRDeMentira):
    """O ONR que recusa o cadastro do título com um código do manual."""

    def __call__(self, url, corpo, acao):
        metodo = acao.rsplit("/", 1)[-1]
        if metodo == "InsertTituloAT":
            self.chamadas.append((url, metodo, corpo.decode("utf-8")))
            return 200, _soap(metodo, "<RETORNO>false</RETORNO><CODIGOERRO>15</CODIGOERRO>"
                                      "<ERRODESCRICAO>O CPF/CNPJ do apresentante é inválido."
                                      "</ERRODESCRICAO>")
        return super().__call__(url, corpo, acao)


# ------------------------------------------------------------------ a carência

def test_carencia_segura_o_que_acabou_de_entrar(con, pasta):
    A.anotar_prenotacao(con, 10, agora="2026-10-27T09:30:00")
    con.commit()
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr, criado_ate="2026-10-27T08:00:00")   # 2 h antes das 10:00
    assert (feito["enviados"], feito["em_carencia"]) == (0, 1) and onr.chamadas == []
    assert _eventos(con)[0]["espera"] is None          # a carência não se grava na linha
    assert _enviar(con, pasta, ONRDeMentira(), criado_ate="2026-10-27T09:30:00")["enviados"] == 1


# --------------------------------------------------------- os atrasados travados

def test_os_atrasados_so_saem_com_a_liberacao(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("""INSERT INTO ri_protocolos (id, numero, data_prenotacao, hora,
        apresentante, natureza_titulo, data_limite, email)
        VALUES (11, 99001, '2026-10-27', '10:00:00', 'JOANA DE TESTE', 'Hipoteca',
                '2026-11-20', 'joana@exemplo.org')""")
    con.commit()
    assert A.travar_atrasados(_Db(con), agora="2026-10-27T08:30:00") == 1
    assert A.travar_atrasados(_Db(con), agora="2026-10-27T12:30:00") == 0     # uma vez só
    assert banco(con).valor("SELECT value FROM settings WHERE key=%s",
                            (A.CHAVE_AUTO_DESDE,)) == "2026-10-27T08:30:00"
    A.anotar_prenotacao(con, 11, agora="2026-10-27T10:00:00")                # o novo anda
    con.commit()
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert (feito["enviados"], feito["atrasados"]) == (1, 1)
    (titulo,) = onr.de("InsertTituloAT")
    assert "<Protocolo>99001</Protocolo>" in titulo
    # o atrasado espera, e a tela diz por quê
    (ev,) = [e for e in A.painel(con, amb=W.HOMOLOGACAO)["eventos"] if e["protocolo_id"] == 10]
    assert ev["avaliacao"]["espera"] == "ATRASADO"
    assert A.painel(con, amb=W.HOMOLOGACAO)["atrasados"] == 1
    # liberado por título, sai
    assert A.liberar_atrasados(con, quem="oficial", agora=AGORA, protocolo_id=10) == 1
    con.commit()
    assert _enviar(con, pasta, ONRDeMentira())["enviados"] == 1
    ev = banco(con).um("SELECT * FROM onr_at_eventos WHERE protocolo_id=10")
    assert ev["situacao"] == "ENVIADO" and ev["liberado_por"] == "oficial"


def test_liberar_todos_e_o_retroativo_nasce_atrasado(con, pasta):
    _nota(con)
    A.travar_atrasados(_Db(con), agora="2026-10-27T08:30:00")
    A.opcao(con, A.CHAVE_RETROATIVO, True)
    A.anotar_prenotacao_retroativa(con, 10, agora="2026-10-27T09:00:00")
    con.commit()
    assert all(e["atrasado"] == 1 for e in _eventos(con))
    assert A.liberar_atrasados(con, quem="oficial", agora=AGORA) == 2
    with pytest.raises(A.AcompanhamentoError, match="já tem"):
        A.anotar_prenotacao_retroativa(con, 10, agora=AGORA)


# ------------------------------------------------------------------ a exigência

@pytest.mark.parametrize("exigencias, motivo", [
    ("[]", "nenhuma exigência"),
    ('["Apresentar a CND. A conferencia fica a cargo do Oficial."]', "rascunho"),
    ('["Recolher o ITBI (valores que não constam das fontes)."]', "rascunho"),
    ('["Retificar a área, a conferir pelo oficial."]', "rascunho"),
    # as variantes que a fila real mostrou (texto inventado)
    ('["Apresentar o aditivo. A redação do art. 1 não consta das fontes recebidas e deve '
     'ser conferida pelo oficial."]', "rascunho"),
    ('["Apresentar o extrato. O texto do dispositivo não consta do acervo recebido."]',
     "rascunho"),
    ('["Retificar a cédula (dispositivos a conferir, por não constarem das fontes)."]',
     "rascunho"),
])
def test_exigencia_bloqueada_nao_sobe_nem_se_revisa(con, pasta, exigencias, motivo):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    ev = _nota(con, exigencias=exigencias)
    with pytest.raises(A.AcompanhamentoError, match="Não dá para marcar"):
        A.marcar_revisada(con, ev["id"], quem="beatriz", agora=AGORA)
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert feito["enviados"] == 1 and feito["por_espera"] == {"BLOQUEIO": 1}
    linha = banco(con).um("SELECT * FROM onr_at_eventos WHERE id=%s", (ev["id"],))
    assert linha["espera"] == "BLOQUEIO" and motivo in linha["ultimo_erro"]
    assert onr.de("InsertStatusAT") == []


def test_exigencia_de_verdade_nao_e_rascunho():
    texto = ("Nota de exigência nº 1, de 25/11/2026.\n1. Apresentar o título hábil (Lei "
             "6.015/1973, art. 221).\nFundamentação: o oficial qualificou o título.")
    assert A.bloqueio_da_exigencia(texto) == ""


def test_exigencia_so_sobe_revisada_e_a_marca_fica(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    ev = _nota(con)
    assert _enviar(con, pasta, ONRDeMentira())["por_espera"] == {"REVISAO": 1}
    A.marcar_revisada(con, ev["id"], quem="beatriz", agora="2026-10-26T11:00:00")
    con.commit()
    with pytest.raises(A.AcompanhamentoError, match="já foi revisada por beatriz"):
        A.marcar_revisada(con, ev["id"], quem="outra", agora=AGORA)
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["enviados"] == 1
    (status,) = onr.de("InsertStatusAT")
    assert "1. Recolher o ITBI." in status and "Prazo da prenotação: 17/11/2026." in status
    linha = banco(con).um("SELECT * FROM onr_at_eventos WHERE id=%s", (ev["id"],))
    assert (linha["revisado_por"], linha["revisado_em"]) == ("beatriz", "2026-10-26T11:00:00")


def test_texto_curto_desligado_de_fabrica_e_pronto(con, pasta):
    assert A.texto_curto_ligado(banco(con)) is False
    A.anotar_prenotacao(con, 10, agora=AGORA)
    _nota(con, numero=3, exigencias='["Apresentar a certidão de casamento atualizada."]')
    A.opcao(con, A.CHAVE_TEXTO_CURTO, True)
    con.commit()
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["enviados"] == 2          # sem revisão
    (status,) = onr.de("InsertStatusAT")
    descricao = re.search(r"<DescricaoStatus>(.*)</DescricaoStatus>", status, re.S).group(1)
    assert descricao == "Nota de exigência nº 3, de 22/10/2026. Prazo: 17/11/2026."
    # a fila guarda o texto inteiro: desligar a opção volta a ele
    assert "certidão de casamento" in _eventos(con)[1]["descricao"]
    with pytest.raises(A.AcompanhamentoError):
        A.opcao(con, "outra_chave_qualquer", True)


# -------------------------------------------------------- registrado sem repetição

def test_um_registrado_por_protocolo_ato_e_matricula(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("""INSERT INTO ri_atos VALUES
        (77, 1, 'R', 1, '2026-10-26', 0, 'S1'), (78, 1, 'R', 1, '2026-10-26', 0, 'S2'),
        (79, 1, 'AV', 2, '2026-10-26', 0, 'S3'), (80, 1, 'R', 1, '2026-10-26', 0, 'S4')""")
    for ato in (77, 78, 79, 80):
        A.anotar_registro(con, 10, ato_id=ato, agora=AGORA)
    banco(con).escrever("DELETE FROM ri_atos WHERE id=77")          # desfeito e refeito
    con.commit()
    medida = A.registros_repetidos(con)
    assert medida == {"registrados": 4, "repetidos": 1, "anulariam": 1, "unicos": 2}
    onr = ONRDeMentira()
    feito = _enviar(con, pasta, onr)
    assert (feito["enviados"], feito["anulados"]) == (3, 2)        # prenotado + R-1 + AV-2
    linhas = {e["origem_id"]: e for e in _eventos(con) if e["evento"] == "REGISTRADO"}
    assert linhas[77]["situacao"] == "ANULADO" and "desfeito" in linhas[77]["motivo_fim"]
    assert linhas[78]["situacao"] == "ENVIADO" and linhas[79]["situacao"] == "ENVIADO"
    assert linhas[80]["situacao"] == "ANULADO" and "repete" in linhas[80]["motivo_fim"]
    assert len(onr.de("InsertStatusAT")) == 2
    # a medida está na tela da fila
    assert A.painel(con, amb=W.HOMOLOGACAO)["repetidos"]["repetidos"] == 0   # já anulados


def test_ato_cancelado_continua_anulado(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 1, 'S')")
    A.anotar_registro(con, 10, ato_id=77, agora=AGORA)
    con.commit()
    assert _enviar(con, pasta, ONRDeMentira())["anulados"] == 1
    assert "cancelado" in _eventos(con)[1]["motivo_fim"]


# ------------------------------------------------------- a validação do cadastro

def test_nome_com_email_dentro_espera_dado_com_a_frase(con, pasta):
    banco(con).escrever("""UPDATE ri_protocolos SET apresentante='BANCO EXEMPLO S.A
        contato@exemplo.org' WHERE id=10""")
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    onr = ONRDeMentira()
    assert _enviar(con, pasta, onr)["por_espera"] == {"DADO": 1} and onr.chamadas == []
    (ev,) = A.da_prenotacao(con, 10)["eventos"]
    assert ev["espera"] == "DADO" and "e-mail dentro" in ev["avaliacao"]["frase"]
    assert "contato@" not in ev["avaliacao"]["frase"]            # a frase não repete o dado


def test_prazo_anterior_a_data_da_nota_espera_dado(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    ev = _nota(con, data="2026-11-03", prazo="2026-10-30")
    A.marcar_revisada(con, ev["id"], quem="beatriz", agora=AGORA)
    con.commit()
    feito = _enviar(con, pasta, ONRDeMentira())
    assert feito["enviados"] == 1 and feito["por_espera"] == {"DADO": 1}
    linha = banco(con).um("SELECT * FROM onr_at_eventos WHERE id=%s", (ev["id"],))
    assert "30/10/2026" in linha["ultimo_erro"] and "03/11/2026" in linha["ultimo_erro"]


def test_sem_email_e_sem_telefone_espera_dado(con, pasta):
    banco(con).escrever("UPDATE ri_protocolos SET email=NULL, telefone=NULL WHERE id=10")
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    assert _enviar(con, pasta, ONRDeMentira())["por_espera"] == {"DADO": 1}
    assert "e-mail nem telefone" in _eventos(con)[0]["ultimo_erro"]


def test_a_ficha_do_protocolo_mostra_a_frase(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    html = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    c.post("/registro-imoveis/protocolo", data={
        "apresentante": "BANCO EXEMPLO S.A contato@exemplo.org",
        "natureza_titulo": "COMPRA E VENDA", "objeto": "escritura", "livro_destino": "2",
        "telefone": "(99) 90000-0000", "csrf_token": _token(html)}, follow_redirects=True)
    with db.connect() as cx:
        pid = banco(cx).valor("SELECT MAX(id) FROM ri_protocolos")
    ficha = c.get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert 'data-trava="DADO"' in ficha and "e-mail dentro" in ficha


# ------------------------------------------------------- a chamada de prova

def test_a_previa_mostra_o_que_sobe_e_a_prova_manda_um_so(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    banco(con).escrever("INSERT INTO ri_atos VALUES (77, 1, 'R', 1, '2026-10-26', 0, 'S')")
    A.anotar_registro(con, 10, ato_id=77, agora=AGORA)
    con.commit()
    A.travar_atrasados(_Db(con), agora="2026-10-27T08:30:00")      # os dois atrasados
    previa = A.previa_da_prova(con, 10, amb=W.HOMOLOGACAO)
    assert previa["segura"] is None and previa["vai"]["metodo"] == "InsertTituloAT"
    campos = dict(previa["vai"]["campos"])
    assert campos["Protocolo"] == "11600" and campos["IDTipoStatus"] == 4
    assert [c for c, _ in previa["vai"]["campos"]] == [
        c for c in W.CAMPOS["InsertTituloAT"] if c in campos]
    assert "<oRequest>" in previa["vai"]["envelope"] and CHAVE_NAO_VAZA(previa)
    ev_id = previa["vai"]["evento"]["id"]
    sessao = lambda: W.Sessao(ambiente=W.HOMOLOGACAO, pasta=pasta,  # noqa: E731
                              transporte=onr, certificado=CERT)
    onr = ONRDeMentira()
    with pytest.raises(A.AcompanhamentoError, match="mudou"):
        A.enviar_prova(_Db(con), sessao, amb=W.HOMOLOGACAO, quem="oficial",
                       agora=lambda: AGORA, protocolo_id=10, evento_id=ev_id + 1)
    assert onr.chamadas == []
    feito = A.enviar_prova(_Db(con), sessao, amb=W.HOMOLOGACAO, quem="oficial",
                           agora=lambda: AGORA, protocolo_id=10, evento_id=ev_id)
    assert feito["enviados"] == 1 and len(onr.de("InsertTituloAT")) == 1
    assert onr.de("InsertStatusAT") == []                          # UM evento, e não o título
    assert [e["situacao"] for e in _eventos(con)] == ["ENVIADO", "PENDENTE"]


def CHAVE_NAO_VAZA(previa) -> bool:
    return "0F1E2D3C" not in previa["vai"]["envelope"]


def test_a_prova_nao_sai_com_trava(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    ev = _nota(con)
    banco(con).escrever("UPDATE onr_at_eventos SET situacao='ENVIADO' WHERE evento='PRENOTADO'")
    banco(con).escrever("""INSERT INTO onr_at_titulos (ambiente, protocolo_id, protocolo_numero,
        id_titulo_onr, como, cadastrado_em) VALUES (%s, 10, '11600', 900, 'CADASTRADO', %s)""",
                        (W.HOMOLOGACAO, AGORA))
    con.commit()
    previa = A.previa_da_prova(con, 10, amb=W.HOMOLOGACAO)
    assert previa["vai"] is None and previa["segura"]["espera"] == "REVISAO"
    with pytest.raises(A.AcompanhamentoError, match="revisão"):
        A.enviar_prova(_Db(con), lambda: None, amb=W.HOMOLOGACAO, quem="oficial",
                       agora=lambda: AGORA, protocolo_id=10, evento_id=ev["id"])
    A.marcar_revisada(con, ev["id"], quem="beatriz", agora=AGORA)
    previa = A.previa_da_prova(con, 10, amb=W.HOMOLOGACAO)
    assert previa["vai"]["metodo"] == "InsertStatusAT"
    assert dict(previa["vai"]["campos"])["IDTitulo"] == 900


# ------------------------------------------------------- o processo na central

def _ctx(con, pasta, *, agora=datetime(2026, 10, 27, 8, 30), pode_agir=True, estado=None,
         parametros=None):
    semente = next(s for s in PROC.SEMENTES if s["codigo"] == "RI_ONR_ACOMPANHAMENTO")
    processo = {"codigo": semente["codigo"], "pode_agir": pode_agir,
                "parametros": dict(semente["parametros"], **(parametros or {})),
                "timeout_s": semente["timeout_s"], "estado": estado or {}}
    return PROC.Contexto(db=_Db(con), agora=agora, pasta_dados=pasta, raiz=Path("."),
                         processo=processo)


@pytest.fixture()
def casa(con, pasta, monkeypatch):
    """O acompanhamento em homologação, com o ONR de mentira no lugar da rede."""
    banco(con).escrever("INSERT INTO settings VALUES ('onr_acompanhamento_ambiente', 'HOMOLOGACAO')")
    con.commit()
    onr = ONRDeMentira()
    monkeypatch.setattr(W, "Sessao",
                        lambda **k: _SessaoReal(**dict(k, transporte=onr, certificado=CERT)))
    return {"con": con, "pasta": pasta, "onr": onr}


def _ligar(con):
    banco(con).escrever("INSERT INTO settings VALUES ('onr_acompanhamento_ligado', '1') "
                        "ON CONFLICT (key) DO UPDATE SET value='1'")
    con.commit()


def test_a_semente_nasce_desligada_com_a_agenda_proposta():
    s = next(s for s in PROC.SEMENTES if s["codigo"] == "RI_ONR_ACOMPANHAMENTO")
    assert s["agenda"] == {"dias": [0, 1, 2, 3, 4], "horarios": ["08:30", "12:30", "17:30"]}
    assert s["parametros"]["carencia_horas"] == 2 and s["timeout_s"] == 600
    assert "pode_agir" not in s and "ativo" not in s           # `semear` grava 0 e 0
    assert PROC.CATALOGO[s["alvo"]] is PROC.verificar_onr_acompanhamento
    import automacao as AU
    assert s["alvo"] in AU.funcoes_permitidas()


def test_envio_desligado_so_mede_e_avisa(casa):
    con = casa["con"]
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"]))
    assert r["situacao"] == "AVISO" and "DESLIGADO" in r["relato"] and r["acoes"] == []
    assert casa["onr"].chamadas == []
    assert not banco(con).valor("SELECT value FROM settings WHERE key=%s", (A.CHAVE_AUTO_DESDE,))


def test_sem_pode_agir_so_mede(casa):
    con = casa["con"]
    _ligar(con)
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"], pode_agir=False))
    assert "só medi; 1 andamento(s) iriam agora" in r["relato"] and r["situacao"] == "OK"
    assert casa["onr"].chamadas == [] and _eventos(con)[0]["atrasado"] == 0


def test_com_pode_agir_trava_os_atrasados_e_manda_os_novos(casa):
    con = casa["con"]
    _ligar(con)
    A.anotar_prenotacao(con, 10, agora=AGORA)                     # já estava na fila
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"]))
    assert r["situacao"] == "AVISO" and casa["onr"].de("InsertTituloAT") == []
    assert "1 atrasado(s) aguardando a liberação do titular" in r["relato"]
    assert r["acoes"][0]["eventos"] == 1 and r["estado"]["auto_desde"]
    # o novo, passada a carência, sai sozinho na rodada seguinte
    banco(con).escrever("""INSERT INTO ri_protocolos (id, numero, data_prenotacao, hora,
        apresentante, natureza_titulo, data_limite, email)
        VALUES (11, 99001, '2026-10-27', '09:00:00', 'JOANA DE TESTE', 'Hipoteca',
                '2026-11-20', 'joana@exemplo.org')""")
    A.anotar_prenotacao(con, 11, agora="2026-10-27T09:00:00")
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"],
                                               agora=datetime(2026, 10, 27, 11, 30),
                                               estado=r["estado"]))
    assert "1 andamento(s) enviado(s) agora" in r["relato"]
    assert len(casa["onr"].de("InsertTituloAT")) == 1


def test_a_rodada_respeita_o_limite(casa):
    con = casa["con"]
    _ligar(con)
    banco(con).escrever("""INSERT INTO ri_protocolos (id, numero, data_prenotacao, hora,
        apresentante, natureza_titulo, data_limite, email)
        VALUES (11, 99001, '2026-10-27', '09:00:00', 'JOANA DE TESTE', 'Hipoteca',
                '2026-11-20', 'joana@exemplo.org')""")
    A.travar_atrasados(_Db(con), agora="2026-10-26T07:00:00")     # marco antes de tudo
    A.anotar_prenotacao(con, 10, agora=AGORA)
    A.anotar_prenotacao(con, 11, agora=AGORA)
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"],
                                               parametros={"limite_por_rodada": 1}))
    assert "1 andamento(s) enviado(s)" in r["relato"] and "limite de chamadas" in r["relato"]
    assert [e["situacao"] for e in _eventos(con)] == ["ENVIADO", "PENDENTE"]


def test_o_prazo_da_rodada_para_antes_do_timeout(con, pasta):
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    tempos = iter([0.0, 1000.0])
    feito = _enviar(con, pasta, ONRDeMentira(), prazo_s=10, relogio=lambda: next(tempos))
    assert feito["tempo_esgotado"] and feito["enviados"] == 0


def test_recusa_do_onr_avisa_com_codigo_e_texto(casa, monkeypatch):
    con = casa["con"]
    _ligar(con)
    A.travar_atrasados(_Db(con), agora="2026-10-26T07:00:00")
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    onr = Recusa()
    monkeypatch.setattr(W, "Sessao", lambda **k: _SessaoReal(**dict(k, transporte=onr,
                                                                     certificado=CERT)))
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"]))
    assert r["situacao"] == "AVISO"
    assert "1 recusa(s) do ONR: 1× código 15 «O CPF/CNPJ do apresentante é inválido.»" in r["relato"]
    assert r["achados"][1]["recusas_desta_rodada"][0]["protocolo_numero"] == "11600"
    assert _eventos(con)[0]["espera"] == "RECUSA"


def test_rodada_parada_e_erro(casa, monkeypatch):
    con = casa["con"]
    _ligar(con)
    A.travar_atrasados(_Db(con), agora="2026-10-26T07:00:00")
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    onr = ONRDeMentira(cair=True)
    monkeypatch.setattr(W, "Sessao", lambda **k: _SessaoReal(**dict(k, transporte=onr,
                                                                     certificado=CERT)))
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"]))
    assert r["situacao"] == "ERRO" and "parou (login ou rede)" in r["relato"] and r["erro"]


def test_sem_credencial_e_aviso(casa, tmp_path):
    con = casa["con"]
    _ligar(con)
    r = PROC.verificar_onr_acompanhamento(_ctx(con, tmp_path / "vazia"))
    assert r["situacao"] == "AVISO" and "credencial" in r["relato"]


def test_esperando_dado_e_fila_acumulando_e_resumo(casa):
    con = casa["con"]
    _ligar(con)
    A.travar_atrasados(_Db(con), agora="2026-10-20T07:00:00")
    banco(con).escrever("UPDATE ri_protocolos SET email=NULL WHERE id=10")
    A.anotar_prenotacao(con, 10, agora="2026-10-22T10:00:00")      # quinta
    con.commit()
    # segunda 26/10, 17:45: o pendente é de antes de sexta 17:45 → mais de 1 dia útil
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"],
                                               agora=datetime(2026, 10, 26, 17, 45)))
    assert r["situacao"] == "AVISO"
    assert "1 pendente(s) há mais de 1 dia útil" in r["relato"]
    assert "1 esperando dado do cadastro" in r["relato"]
    assert r["relato"].startswith("Resumo do dia: 0 enviado(s)")
    assert r["achados"][0]["medida"]["esperando_dado"][0]["protocolo_numero"] == "11600"
    # o resumo sai uma vez por dia
    r2 = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"],
                                                agora=datetime(2026, 10, 26, 18, 0),
                                                estado=r["estado"]))
    assert not r2["relato"].startswith("Resumo do dia")


def test_precisa_de_decisao_e_exigencia_por_revisar_viram_aviso(casa):
    con = casa["con"]
    _ligar(con)
    _nota(con)                                                     # sem o «prenotado»
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"], pode_agir=False))
    assert r["situacao"] == "AVISO" and "precisam de decisão do titular" in r["relato"]
    assert r["achados"][0]["precisam_de_decisao"] == ["11600"]
    A.anotar_prenotacao(con, 10, agora=AGORA)
    con.commit()
    r = PROC.verificar_onr_acompanhamento(_ctx(con, casa["pasta"], pode_agir=False))
    assert "1 exigência(s) aguardando revisão" in r["relato"]


# ------------------------------------------------------- quem recebe o aviso

def test_o_aviso_vai_ao_responsavel_do_onr_ou_do_ri(con):
    bd = banco(con)
    bd.escrever("""CREATE TABLE users (id bigint PRIMARY KEY, role TEXT, active INTEGER,
                       eh_robo INTEGER DEFAULT 0);
                   CREATE TABLE ge_responsaveis (setor TEXT PRIMARY KEY, user_id INTEGER);
                   INSERT INTO users VALUES (1, 'ADMIN', 1, 0), (2, 'USER', 1, 0),
                                            (3, 'USER', 1, 0), (4, 'USER', 0, 0);
                   INSERT INTO ge_responsaveis VALUES ('GESTAO', 1), ('RI', 3);""")
    semente = next(s for s in PROC.SEMENTES if s["codigo"] == "RI_ONR_ACOMPANHAMENTO")
    processo = {"parametros": semente["parametros"]}
    assert AV.responsavel(con, processo) == 3                     # sem a chave: o do RI
    bd.escrever("INSERT INTO settings VALUES ('onr_pedidos_responsavel_id', '2')")
    assert AV.responsavel(con, processo) == 2                     # a escolha da A005
    bd.escrever("UPDATE settings SET value='4' WHERE key='onr_pedidos_responsavel_id'")
    assert AV.responsavel(con, processo) == 3                     # inativo não recebe
    assert AV.responsavel(con, {"parametros": {}}) == 1           # os outros, como antes
    assert AV.responsavel(con, {"responsavel_user_id": 2, "parametros": semente["parametros"]}) == 2


# ------------------------------------------------------- as telas (ADMIN)

def _protocolo_pela_tela(c, db):
    html = c.get("/registro-imoveis/protocolo").get_data(as_text=True)
    c.post("/registro-imoveis/protocolo", data={
        "apresentante": "MARIO DE TESTE", "natureza_titulo": "COMPRA E VENDA",
        "objeto": "escritura", "livro_destino": "2", "telefone": "(99) 90000-0000",
        "csrf_token": _token(html)}, follow_redirects=True)
    with db.connect() as cx:
        return banco(cx).valor("SELECT MAX(id) FROM ri_protocolos")


def test_telas_liberar_prova_e_opcoes(cg_casa_logada, monkeypatch):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo_pela_tela(c, db)
    with db.connect() as cx:
        numero = banco(cx).valor("SELECT numero FROM ri_protocolos WHERE id=%s", (pid,))
    A.travar_atrasados(db, agora=db.now())
    tela = c.get("/ri/onr/acompanhamento").get_data(as_text=True)
    assert "Atrasados aguardando liberação: <strong>1</strong>" in tela
    assert 'data-trava="ATRASADO"' in tela and "Liberar todos os atrasados" in tela
    assert "Texto curto da exigência (sem revisão): <strong>desligado</strong>" in tela
    tok = _token(tela)

    chamadas = []

    class SessaoFalsa:
        def __init__(self, **_):
            pass

        def cadastrar_titulo_no_acompanhamento(self, campos):
            chamadas.append(campos)
            return {"RETORNO": True, "IDTitulo": "900", "IDStatus": "1"}

    import onr_acompanhamento_web as AW
    monkeypatch.setattr(AW.WS, "Sessao", SessaoFalsa)
    previa = c.get(f"/ri/onr/acompanhamento/prova?protocolo_id={pid}").get_data(as_text=True)
    assert "InsertTituloAT" in previa and "<code>Protocolo</code>" in previa
    assert "Mandar este andamento ao ONR" in previa
    with db.connect() as cx:
        ev_id = banco(cx).valor("SELECT id FROM onr_at_eventos WHERE protocolo_id=%s", (pid,))
    dados = {"csrf_token": tok, "protocolo_id": pid, "evento_id": ev_id}
    # o envio desligado segura a prova
    r = c.post("/ri/onr/acompanhamento/prova", data=dict(dados, confirmacao=str(numero)),
               follow_redirects=True).get_data(as_text=True)
    assert "a prova não sai" in r and chamadas == []
    c.post("/ri/onr/acompanhamento/ligar", data={"csrf_token": tok, "ligar": "1"})
    r = c.post("/ri/onr/acompanhamento/prova", data=dict(dados, confirmacao="000"),
               follow_redirects=True).get_data(as_text=True)
    assert "digite o número do protocolo" in r and chamadas == []
    r = c.post("/ri/onr/acompanhamento/prova", data=dict(dados, confirmacao=str(numero)),
               follow_redirects=True).get_data(as_text=True)
    assert "Prova enviada ao ONR" in r and len(chamadas) == 1
    with db.connect() as cx:
        acoes = [x["action"] for x in banco(cx).ler("SELECT action FROM audit_logs")]
    assert "ONR_ACOMPANHAMENTO_PROVA" in acoes

    # liberar todos e as opções, auditados
    c.post("/ri/onr/acompanhamento/liberar", data={"csrf_token": tok, "todos": "1"})
    c.post("/ri/onr/acompanhamento/opcao", data={
        "csrf_token": tok, "chave": A.CHAVE_TEXTO_CURTO, "ligar": "1"})
    assert db.get_setting(A.CHAVE_TEXTO_CURTO) == "1"
    with db.connect() as cx:
        acoes = [x["action"] for x in banco(cx).ler("SELECT action FROM audit_logs")]
    assert {"ONR_ACOMPANHAMENTO_ATRASADOS_LIBERADOS", "ONR_ACOMPANHAMENTO_OPCAO"} <= set(acoes)
    r = c.post("/ri/onr/acompanhamento/opcao", data={
        "csrf_token": tok, "chave": "onr_acompanhamento_ligado", "ligar": "1"},
        follow_redirects=True).get_data(as_text=True)
    assert "não é do acompanhamento" in r


def test_tela_revisar_exigencia_e_bloqueada_sem_botao(cg_casa_logada):
    c, db = cg_casa_logada["c"], cg_casa_logada["db"]
    pid = _protocolo_pela_tela(c, db)
    html = c.get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
    c.post(f"/registro-imoveis/protocolo/{pid}/nota", data={
        "exigencias": "Apresentar a CND, a conferir pelo oficial.", "csrf_token": _token(html)})
    tela = c.get("/ri/onr/acompanhamento").get_data(as_text=True)
    assert 'data-trava="BLOQUEIO"' in tela and "frase de rascunho" in tela
    assert "marcar como revisada" not in tela
    with db.connect() as cx:
        exig = banco(cx).valor("SELECT id FROM onr_at_eventos WHERE evento='EXIGENCIA'")
    r = c.post(f"/ri/onr/acompanhamento/{exig}/revisar", data={"csrf_token": _token(tela)},
               follow_redirects=True).get_data(as_text=True)
    assert "Não dá para marcar como revisada" in r
