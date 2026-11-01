"""O Serviço de Pendências do e-Protocolo: transporte, arquivo estruturado, fila e cumprimento.

Os dados são fictícios. Os dois arquivos estruturados têm a forma dos exemplos públicos
do serviço, inclusive as irregularidades deles (`e-mail`, `causa_morte_d`, UF por extenso).
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import centrais_cred as CC
import eprotocolo as EP
import eprotocolo_api as API

CPF_FICTICIO = "12345678909"

NASCIMENTO = {
    "solicitacao": {"plataformaId": "unidade_interligada", "tipo_registro": "nascimento",
                    "cartorio_destino_cns": "999999"},
    "registro": {
        "dados_nascimento": {"numero_dnv": "123456789", "local_nascimento": {
            "tipo_local_nascimento": "Hospital", "nome_local_nascimento": "Maternidade Exemplo",
            "endereco": {"logradouro": "Rua das Flores, 100", "bairro": "Centro",
                         "cidade": "Cidade Exemplo", "uf": "MA"}}},
        "registrado": {"nome": "Criança de Tal", "data_nascimento": "13-01-2026",
                       "hora_nascimento": "14:25", "sexo": "M",
                       "naturalidade": {"municipio": "Cidade Exemplo", "uf": "MA"},
                       "gemelar": False, "ordem_nascimento": "1"},
        "filiacao": [
            {"tipo": "Mae", "nome": "Maria de Tal", "cpf": CPF_FICTICIO, "estado_civil": "Solteira",
             "naturalidade": "Cidade Exemplo", "naturalidade_uf": "Maranhão",
             "ascendentes": [{"nome": "Avô Materno"}, {"nome": "Avó Materna"}]},
            {"tipo": "Pai", "nome": "João de Tal", "e-mail": "x@exemplo.test",
             "documento_identificacao": {"tipo": "RG", "numero": "MA-1", "orgao_emissor": "SSP"}},
        ],
        "declarante": {"tipo_declarante": "pai", "nome": "João de Tal", "cpf": CPF_FICTICIO},
    },
}

OBITO = {
    "solicitacao": {"plataformaId": "e-obito", "tipo_registro": "obito",
                    "cartorio_destino_cns": "999999"},
    "registro": {
        "falecido": {"nome": "Fulano de Tal", "CPF": CPF_FICTICIO, "sexo": "Masculino",
                     "data_nascimento": "15-03-1950", "idade": "75", "tipo_idade": "anos",
                     "cor": "branca", "estado_civil": "casado",
                     "conjuge": {"nome": "Cônjuge de Tal"},
                     "filiacao": [{"nome": "Pai de Tal", "sexo": "masculino"},
                                  {"nome": "Mãe de Tal", "sexo": "Feminino"}]},
        "declarante": {"nome": "Declarante de Tal", "cpf": CPF_FICTICIO},
        "dados_falecimento": {
            "do": "123456789", "data_falecimento": "17-07-2025", "hora_falecimento": "10:30",
            "local_falecimento": {"tipo_local_falecimento": "Hospital",
                                  "Nome_local_falecimento": "Hospital Exemplo"},
            "medicos": [{"nome": "Médica Um", "crm": "1", "crm_uf": "MA"}, {"nome": "Médico Dois"}],
            "causa_morte": [{"causa_morte_B": "Segunda"}, {"causa_morte_A": "Primeira"},
                            {"causa_morte_d": "Quarta"}],
            "local_sepultamento": {"nome_local_sepultamento": "Cemitério Exemplo"}},
        "deixou_filhos": True, "filhos": [{"nome": "Filho de Tal"}],
    },
}


# ---------------------------------------------------------- arquivo estruturado

def test_o_par_do_manual_escolhe_a_especie():
    assert EP.especie_do_estruturado(NASCIMENTO) == "NASCIMENTO"
    assert EP.especie_do_estruturado(OBITO) == "OBITO"
    assert EP.especie_do_estruturado({"solicitacao": {"plataformaId": "outra"}}) == ""


def test_nascimento_vira_o_vocabulario_da_leitura():
    junto, avisos = EP.montar_registro(NASCIMENTO, cns_da_casa="999999")
    v = junto["valores"]
    assert (v["especie"], v["data_fato"], v["dnv"]) == ("NASCIMENTO", "2026-01-13", "123456789")
    papeis = {p["papel"]: p for p in junto["pessoas"]}
    assert set(papeis) >= {"REGISTRADO", "MAE", "PAI", "DECLARANTE", "AVO_MATERNO", "AVO_MATERNA"}
    assert papeis["MAE"]["documento_tipo"] == "CPF"
    # O RG de quem não tem CPF, e a UF por extenso que o exemplo traz não passa.
    assert papeis["PAI"]["documento_numero"] == "MA-1"
    assert "naturalidade_uf" not in papeis["MAE"]
    assert any("não diz quem é avô" in t for _, t in avisos)


def test_obito_ordena_as_causas_e_decide_a_filiacao_pelo_sexo():
    junto, avisos = EP.montar_registro(OBITO, cns_da_casa="999999")
    v = junto["valores"]
    assert v["causa_morte"] == "Primeira; Segunda; Quarta"
    assert v["atestante"] == "Médica Um" and v["atestante_documento"] == "CRM 1 MA"
    assert v["data_fato"] == "2025-07-17"
    papeis = {p["papel"] for p in junto["pessoas"]}
    assert {"FALECIDO", "PAI", "MAE", "DECLARANTE"} <= papeis
    assert any("2 médicos" in t for _, t in avisos)
    assert any("natureza da morte" in t for _, t in avisos)


def test_arquivo_de_outra_serventia_recusa():
    with pytest.raises(EP.EProtocoloRegra, match="CNS 999999"):
        EP.montar_registro(OBITO, cns_da_casa="111111")


def test_data_ignorada_nao_vira_data():
    e = json.loads(json.dumps(OBITO))
    e["registro"]["dados_falecimento"]["data_falecimento_ignorada"] = True
    assert EP.montar_registro(e)[0]["valores"]["data_fato"] == ""


# -------------------------------------------------------------- o transporte

def _sessao(respostas):
    """Sessão com credencial falsa e transporte que devolve em ordem."""
    feitas = []

    def transporte(metodo, base, caminho, **k):
        feitas.append((metodo, base, caminho, k))
        return respostas.pop(0)

    s = API.Sessao(API.HOMOLOGACAO, transporte=transporte)
    s._token = "T1"
    return s, feitas


def _r(status, corpo=None):
    return {"status": status, "json": corpo, "bytes": b"", "cabecas": {}}


def test_o_token_vale_para_os_dois_servicos(monkeypatch):
    s, feitas = _sessao([_r(200, {"notifications": [], "remainingUnread": 0}),
                         _r(201, {"data": {"status": "request_received"}})])
    s.notificacoes_novas()
    assert s.protocolo("abc-1")["status"] == "request_received"
    assert feitas[0][1] == API.EVENTOS[API.HOMOLOGACAO]
    assert feitas[1][1] == API.PROTOCOLO[API.HOMOLOGACAO]
    assert feitas[1][2] == "/api/v1.0/notifications-system/requirements/abc-1"
    assert feitas[0][3]["token"] == feitas[1][3]["token"] == "T1"


def test_401_autentica_de_novo_e_repete_uma_vez(monkeypatch):
    s, feitas = _sessao([_r(401), _r(200, {"accessToken": "T2"}),
                         _r(200, {"notifications": [{"hash": "h"}], "remainingUnread": 1})])
    monkeypatch.setattr(CC, "credencial", lambda *a, **k: ("u", "s"))
    lote, restam = s.notificacoes_novas()
    assert (len(lote), restam) == (1, 1)
    assert feitas[1][2] == "/auth/signin"
    assert feitas[2][3]["token"] == "T2"


def test_429_para_a_rodada():
    s, _ = _sessao([_r(429)])
    with pytest.raises(API.EProtocoloCheio):
        s.notificacoes_novas()


def test_404_do_arquivo_estruturado_e_resposta():
    s, _ = _sessao([_r(404)])
    assert s.arquivo_estruturado("abc") is None


def test_hash_estranho_nao_vai_para_a_url():
    s, feitas = _sessao([])
    with pytest.raises(API.EProtocoloError):
        s.protocolo("../../admin")
    assert not feitas


RESPONSAVEL = {"cpf": CPF_FICTICIO, "cns": "999999", "name": "Mario", "email": "m@exemplo.test"}


def test_cumprimento_leva_os_dois_tokens_e_o_formulario():
    s, feitas = _sessao([_r(200, {"status": 200, "message": "Ok"})])
    s.cumprir("abc", certidao={"type": "physical"}, responsavel=RESPONSAVEL, token_idrc="IDRC",
              titulares=[{"name": "T", "registerType": "Óbito"}])
    metodo, base, caminho, k = feitas[0]
    assert metodo == "POST" and caminho.endswith("/requirements/abc/fulfillment")
    assert k["token"] == "T1" and k["cabecas"]["access-token"] == "IDRC"
    assert k["tipo"].startswith("multipart/form-data; boundary=")
    corpo = k["corpo"].decode("utf-8")
    for nome in ("certificate[type]", "responsibleUser[cpf]", "subjects[0][registerType]"):
        assert f'name="{nome}"' in corpo
    assert "IDRC" not in corpo


@pytest.mark.parametrize("certidao,resp,frase", [
    ({"type": "electronic"}, RESPONSAVEL, "exige o link"),
    ({"type": "physical", "url": "https://x.test/a"}, RESPONSAVEL, "não leva link"),
    ({"type": "outro"}, RESPONSAVEL, "eletrônica ou física"),
    ({"type": "physical"}, {**RESPONSAVEL, "cpf": "1"}, "11 dígitos"),
    ({"type": "physical"}, {**RESPONSAVEL, "email": "x"}, "e-mail"),
])
def test_o_cumprimento_recusa_antes_da_rede(certidao, resp, frase):
    with pytest.raises(API.EProtocoloError, match=frase):
        API.campos_do_cumprimento(certidao, resp)


def test_recibo_so_das_extensoes_da_referencia():
    with pytest.raises(API.EProtocoloError):
        API.multipart([], {"nome": "a.exe", "bytes": b"x"})
    corpo, _ = API.multipart([], {"nome": 'a"b.pdf', "bytes": b"x"})
    assert b'filename="a_b.pdf"' in corpo


def test_a_credencial_e_par_e_tem_os_dois_ambientes():
    assert CC.FORMA_DA_CENTRAL[CC.EPROTOCOLO] == CC.PAR
    assert CC.ambiente_de_uso(CC.EPROTOCOLO, CC.HOMOLOGACAO) == CC.HOMOLOGACAO
    assert CC.EPROTOCOLO not in CC.CENTRAIS_SO_EM_PRODUCAO


def test_o_ambiente_sem_escolha_e_a_homologacao():
    assert EP.ambiente_em_uso(lambda k, p: p) == API.HOMOLOGACAO
    assert EP.ambiente_em_uso(lambda k, p: "producao".upper()) == API.PRODUCAO
    assert EP.ambiente_em_uso(lambda k, p: "qualquer") == API.HOMOLOGACAO


def test_evento_desconhecido_nao_some():
    assert EP.rotulo_do_evento("novidade_do_servico") == "novidade_do_servico"
    assert "não conhece" in EP.acao_do_evento("novidade_do_servico")


def test_todo_evento_do_manual_e_da_referencia_tem_rotulo():
    manual = {"request_received", "signature_completed", "waiting_for_response_requirement_note",
              "requirement_note_answered", "requirement_note_finished", "send_for_budget",
              "budget_response", "waiting_approval_for_additional_services", "waiting_for_payment",
              "payment_made", "devolved", "accepted_devolution", "rejected_devolution",
              "transferred_to_another_notary", "canceled", "completed"}
    assert manual <= set(EP.EVENTOS)
    assert EP.ESPERAM_A_CASA <= set(EP.EVENTOS) and EP.ENCERRADOS <= set(EP.EVENTOS)


def test_o_robo_nao_chama_o_cumprimento():
    """O cumprimento é clique de gente: a rodada não pode alcançá-lo."""
    import ast
    arvore = ast.parse((RAIZ / "eprotocolo.py").read_text(encoding="utf-8"))
    rodada = next(n for n in arvore.body if getattr(n, "name", "") == "rodada")
    chamadas = {getattr(c.func, "attr", getattr(c.func, "id", "")) for c in ast.walk(rodada)
                if isinstance(c, ast.Call)}
    assert "cumprir" not in chamadas and "para_rascunho" not in chamadas


# ---------------------------------------------------- a fila gravada, no banco

@pytest.fixture()
def con():
    from banco_de_teste import conexao_de_teste
    from eprotocolo_schema import init_eprotocolo_schema
    from rc_schema import init_rc_schema
    from nucleo_schema import init_nucleo_schema
    c = conexao_de_teste()
    init_nucleo_schema(c)
    init_rc_schema(c)
    init_eprotocolo_schema(c)
    return c


def _nota(**extra):
    return {"cns": "999999", "status": "request_received", "requirement_id": 7, "hash": "h-1",
            "content": {}, "createdAt": "2026-10-31T10:00:00", **extra}


def test_gravar_duas_vezes_e_uma_so(con):
    assert EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(), agora="2026-10-31T10:01:00") is True
    assert EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(), agora="2026-10-31T10:02:00") is False
    assert len(EP.a_consultar(con, "HOMOLOGACAO")) == 1


def test_o_mesmo_status_em_outra_hora_e_outro_evento(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(), agora="x")
    assert EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(createdAt="2026-10-31T11:00:00"), agora="x")


def test_o_ambiente_faz_parte_da_chave(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(), agora="x")
    assert EP.guardar_notificacao(con, "PRODUCAO", _nota(), agora="x") is True
    assert len(EP.lista(con, "PRODUCAO")) == 1


def test_a_reconciliacao_antiga_nao_recua_o_status(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(status="payment_made",
                           createdAt="2026-10-31T12:00:00"), agora="x")
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(status="request_received"), agora="x",
                           origem="RECONCILIACAO")
    assert EP.lista(con, "HOMOLOGACAO")[0]["status"] == "payment_made"


def test_notificacao_sem_hash_recusa(con):
    with pytest.raises(EP.EProtocoloRegra):
        EP.guardar_notificacao(con, "HOMOLOGACAO", {"status": "x"}, agora="x")


def test_o_que_espera_a_casa_vem_primeiro(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(hash="h-a", status="waiting_for_payment",
                           createdAt="2026-10-31T12:00:00"), agora="x")
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(hash="h-b"), agora="x")
    primeira = EP.lista(con, "HOMOLOGACAO")[0]
    assert primeira["hash"] == "h-b" and primeira["espera_a_casa"]
    assert EP.contar(con, "HOMOLOGACAO")["esperam"] == 1


def test_a_transferencia_guarda_o_destino(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(
        status="transferred_to_another_notary", content={"new_notary_cns": "888888"}), agora="x")
    p = EP.lista(con, "HOMOLOGACAO")[0]
    assert p["novo_destino_cns"] == "888888" and p["encerrado"]


def test_dispensar_exige_motivo(con):
    EP.guardar_notificacao(con, "HOMOLOGACAO", _nota(), agora="x")
    pid = EP.lista(con, "HOMOLOGACAO")[0]["id"]
    with pytest.raises(EP.EProtocoloRegra):
        EP.dispensar(con, pid, motivo="curto", agora="x", por="mario")
    EP.dispensar(con, pid, motivo="Não é desta serventia.", agora="x", por="mario")
    assert EP.um(con, pid)["espera_a_casa"] is False
