"""A APOSTILA DE HAIA (LG03, 19/10/2026) — pronta para quando a serventia for habilitada.

O QUE SE PROVA AQUI
    - o módulo chega DESLIGADO, até para o oficial, e é o oficial quem o liga
      no Gestor (a tela de configuração fica fora da guarda);
    - a guarda é na rota: o favorito não entra; o AUDITOR vê e não pratica; só
      oficial e gerente cancelam; POST sem token de formulário é recusado;
    - o valor sai da tabela do MA do dia (13.23, R$ 140,01 em 2026);
    - o registro da Convenção (art. 7º): quem assinou e em que qualidade, ou a
      autoridade do selo/carimbo — sem isso o documento não entra;
    - o número de ordem só nasce na emissão, em sequência, e o cancelamento
      não o devolve; código do CNJ e selo não se repetem;
    - a cobrança é o item do protocolo geral: a emissão o consome, o
      cancelamento o devolve, e item de outro serviço não paga apostila;
    - as pendências cobram emissão, selo e cobrança;
    - o rastro vai para `audit_logs`, sem o nome de quem pediu;
    - o esquema é PostgreSQL nativo, com dinheiro em `bigint`.

Equipe, requerente e signatários fictícios. Nada de dado real de pessoa.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import apostila as AP                      # noqa: E402
import caixa_protocolo as CXP              # noqa: E402
import modulos_ligados as MODLIG           # noqa: E402
from bd_nativo import banco                # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-10-19T10:00:00"
HOJE = "2026-10-19"
VIGENCIA_2026 = 10022
# A tabela de 2026, tirada de `tests/custas_reais.json` (o acervo real do
# E-Ofício): o 13.23 das Notas e o 15.16 do RTD, ambos a R$ 140,01; e uma
# certidão do Protesto, para provar que item de outro serviço não paga apostila.
REAIS = json.loads((Path(__file__).parent / "custas_reais.json").read_text("utf-8"))
SERVICOS = (422, 639, 105)
REQUERENTE = "FULANA DE TESTE DA SILVA"


def _tabela(casa) -> None:
    linhas = {int(e["s"]): e for e in REAIS["valores_2026"]}
    with casa["db"].transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio, fim, importado_em)
               VALUES (%s, '2026', 1, '2026-01-01', NULL, '2026-08-21')
               ON CONFLICT (codigo) DO NOTHING""", (VIGENCIA_2026,))
        for codigo in SERVICOS:
            e = linhas.get(codigo) or {"tj": "9.99", "descricao": "Certidão de teste",
                                       "emol": 10.0, "ferc": 0.3, "femp": 0.4,
                                       "fadp": 0.4, "ferrfis": 0.1}
            bd.escrever(
                """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
                   VALUES (%s, %s, %s, 1) ON CONFLICT (codigo) DO NOTHING""",
                (codigo, e["tj"], e["descricao"]))
            cent = {k: int(round(e[k] * 100)) for k in ("emol", "ferc", "femp", "fadp", "ferrfis")}
            r = lambda c: f"{c // 100},{c % 100:02d}"  # noqa: E731
            bd.escrever(
                """INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                       ferc, femp, fadep, ferrfis, total)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                   ON CONFLICT (servico, vigencia) DO NOTHING""",
                (codigo, VIGENCIA_2026, r(cent["emol"]), r(cent["ferc"]), r(cent["femp"]),
                 r(cent["fadp"]), r(cent["ferrfis"]), r(sum(cent.values()))))


def _entrar(casa, usuario: str, papel: str):
    casa["db"].create_user(usuario, f"OPERADOR {papel} DE TESTE", SENHA, papel)
    c = casa["app"].test_client()
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                      c.get("/login").get_data(as_text=True)).group(1)
    c.post("/login", data={"username": usuario, "password": SENHA, "csrf_token": token},
           follow_redirects=True)
    return c


def _token(c) -> str:
    html = c.get("/login").get_data(as_text=True)
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    if achado:
        return achado.group(1)
    with c.session_transaction() as s:
        return s["csrf_token"]


def _post(c, url: str, **dados):
    return c.post(url, data={"csrf_token": _token(c), **dados})


def _ligar(casa, alcance: str = "TODOS") -> None:
    casa["db"].set_settings({MODLIG.CHAVE_DA_CONFIGURACAO["APOSTILA"]: alcance})


@pytest.fixture
def casa(cg_casa):
    _tabela(cg_casa)
    return cg_casa


def _pedido(casa, **campos) -> int:
    dados = {"recebido_em": HOJE, "atribuicao": "NOTAS", "requerente_nome": REQUERENTE}
    dados.update(campos)
    with casa["db"].transaction() as con:
        return AP.abrir_pedido(con, agora=AGORA, por="ESCREVENTE DE TESTE", **dados)


def _documento(casa, pedido_id: int, **campos) -> int:
    dados = {"documento_tipo": "REGISTRO_CIVIL", "documento_data": "2026-10-01",
             "signatario_nome": "OFICIAL FICTICIO", "signatario_cargo": "Oficial de Registro Civil"}
    dados.update(campos)
    with casa["db"].transaction() as con:
        return AP.incluir_documento(con, pedido_id, agora=AGORA, por="ESCREVENTE DE TESTE",
                                    get_setting=casa["db"].get_setting, **dados)


def _emitir(casa, apostila_id: int, codigo: str, **campos) -> dict:
    with casa["db"].transaction() as con:
        return AP.emitir(con, apostila_id, agora=AGORA, por="ESCREVENTE DE TESTE",
                         codigo_cnj=codigo, emitida_em=HOJE,
                         get_setting=casa["db"].get_setting, **campos)


def _protocolo_com_item(casa, servico: int = 422, codigo_tj: str = "13.23",
                        quantidade: int = 1) -> tuple[str, int]:
    with casa["db"].transaction() as con:
        p = CXP.abrir(con, data_abertura=HOJE, agora=AGORA, atribuicao="NOTAS",
                      interessado=REQUERENTE)
        item = banco(con).escrever(
            """INSERT INTO cx_protocolo_atos (protocolo_id, descricao, codigo_ato,
                   quantidade, valor_total, emolumentos, servico_codigo)
               VALUES (%s, 'Apostila de Haia', %s, %s, '140,01', '125,01', %s)
               RETURNING id""", (p["protocolo_id"], codigo_tj, quantidade, servico))
    return p["numero"], int(item[0]["id"])


def _ler(casa, sql: str, parametros=None):
    with casa["db"].connect() as con:
        return banco(con).ler(sql, parametros)


# ------------------------------------------------- o alcance e a guarda


def test_de_fabrica_a_apostila_chega_desligada_ate_para_o_oficial(casa):
    sem_config = lambda chave, padrao=None: padrao  # noqa: E731
    assert MODLIG.alcance(sem_config, "APOSTILA") == MODLIG.NINGUEM
    oficial = _entrar(casa, "ap_adm", "ADMIN")
    r = oficial.get("/apostila")
    assert r.status_code == 302
    assert r.headers["Location"].endswith("/administrativo/gestor/apostila")
    escrevente = _entrar(casa, "ap_usr", "USER")
    r = escrevente.get("/apostila", follow_redirects=True)
    assert "está desligada nesta serventia" in r.get_data(as_text=True)
    # O favorito do POST também não entra: a guarda é da rota, e não do menu.
    r = _post(escrevente, "/apostila/pedido", recebido_em=HOJE, atribuicao="NOTAS",
              requerente_nome=REQUERENTE)
    assert r.status_code == 302
    assert not _ler(casa, "SELECT id FROM ap_pedidos ORDER BY id")


def test_o_menu_so_oferece_ao_oficial_o_caminho_para_ligar(casa):
    oficial = _entrar(casa, "ap_adm", "ADMIN")
    html = oficial.get("/administrativo/gestor/apostila").get_data(as_text=True)
    assert "Apostila de Haia (desligada)" in html
    escrevente = _entrar(casa, "ap_usr", "USER")
    html = escrevente.get("/").get_data(as_text=True)
    assert "Apostila de Haia" not in html


def test_o_oficial_liga_no_gestor_e_o_balcao_entra(casa):
    oficial = _entrar(casa, "ap_adm", "ADMIN")
    r = _post(oficial, "/administrativo/gestor/apostila", alcance="TODOS", servico="639")
    assert r.status_code == 302
    assert casa["db"].get_setting("modulo_apostila_alcance", "") == "TODOS"
    assert casa["db"].get_setting(AP.CHAVE_DO_SERVICO, "") == "639"
    escrevente = _entrar(casa, "ap_usr", "USER")
    assert escrevente.get("/apostila").status_code == 200
    rastro = _ler(casa, "SELECT details FROM audit_logs WHERE action = %s ORDER BY id",
                  ("APOSTILA_CONFIGURACAO",))
    assert rastro and "TODOS" in rastro[-1]["details"]


def test_valor_estranho_na_configuracao_nao_liga_o_modulo(casa):
    oficial = _entrar(casa, "ap_adm", "ADMIN")
    _post(oficial, "/administrativo/gestor/apostila", alcance="SEI_LA", servico="999999")
    assert casa["db"].get_setting("modulo_apostila_alcance", "") == "NINGUEM"
    assert casa["db"].get_setting(AP.CHAVE_DO_SERVICO, "x") == ""


def test_so_o_oficial_mexe_na_configuracao(casa):
    _ligar(casa)
    for papel in ("MANAGER", "USER", "AUDITOR"):
        c = _entrar(casa, f"ap_{papel.lower()}", papel)
        assert c.get("/administrativo/gestor/apostila").status_code == 403
        assert _post(c, "/administrativo/gestor/apostila", alcance="TODOS").status_code == 403


def test_post_sem_token_de_formulario_e_recusado(casa):
    _ligar(casa)
    escrevente = _entrar(casa, "ap_usr", "USER")
    r = escrevente.post("/apostila/pedido", data={"recebido_em": HOJE, "atribuicao": "NOTAS",
                                                  "requerente_nome": REQUERENTE})
    assert r.status_code == 400


def test_o_auditor_ve_e_nao_pratica(casa):
    _ligar(casa)
    pedido_id = _pedido(casa)
    apostila_id = _documento(casa, pedido_id)
    auditor = _entrar(casa, "ap_aud", "AUDITOR")
    html = auditor.get(f"/apostila/pedido/{pedido_id}").get_data(as_text=True)
    assert "Documento 1" in html
    assert "Registrar emissão" not in html and "Incluir documento" not in html
    assert _post(auditor, f"/apostila/{apostila_id}/emitir", codigo_cnj="ABC12345",
                 emitida_em=HOJE).status_code == 403
    assert auditor.get("/apostila/controle").status_code == 200


def test_so_oficial_ou_gerente_cancela_apostila_emitida(casa):
    _ligar(casa)
    apostila_id = _documento(casa, _pedido(casa))
    _emitir(casa, apostila_id, "BR-0001-TESTE")
    escrevente = _entrar(casa, "ap_usr", "USER")
    assert _post(escrevente, f"/apostila/{apostila_id}/cancelar",
                 motivo="Erro de digitação no CNJ").status_code == 403
    gerente = _entrar(casa, "ap_ger", "MANAGER")
    assert _post(gerente, f"/apostila/{apostila_id}/cancelar",
                 motivo="Erro de digitação no CNJ").status_code == 302
    assert _ler(casa, "SELECT situacao FROM ap_apostilas WHERE id = %s",
                (apostila_id,))[0]["situacao"] == AP.CANCELADA


# ------------------------------------------------- pedido e documento


def test_o_valor_sai_da_tabela_do_ma_no_dia(casa):
    apostila_id = _documento(casa, _pedido(casa))
    linha = _ler(casa, "SELECT * FROM ap_apostilas WHERE id = %s", (apostila_id,))[0]
    assert linha["servico"] == 422 and linha["codigo_tj"] == "13.23"
    assert linha["vigencia"] == VIGENCIA_2026
    assert (linha["emolumentos"], linha["ferc"], linha["femp"], linha["fadep"],
            linha["ferrfis"], linha["total"]) == (12501, 375, 500, 500, 125, 14001)


def test_o_servico_escolhido_no_gestor_manda_sobre_o_primeiro_da_tabela(casa):
    casa["db"].set_settings({AP.CHAVE_DO_SERVICO: "639"})
    apostila_id = _documento(casa, _pedido(casa, atribuicao="RTD"))
    linha = _ler(casa, "SELECT servico, codigo_tj FROM ap_apostilas WHERE id = %s",
                 (apostila_id,))[0]
    assert (linha["servico"], linha["codigo_tj"]) == (639, "15.16")


def test_sem_a_tabela_da_apostila_o_documento_nao_entra_e_a_frase_diz_o_que_fazer(casa):
    with casa["db"].transaction() as con:
        banco(con).escrever("DELETE FROM cx_servico_valores WHERE servico IN (422, 639)")
        banco(con).escrever("DELETE FROM cx_servicos WHERE codigo IN (422, 639)")
    pedido_id = _pedido(casa)
    with pytest.raises(AP.ApostilaError, match="não tem o serviço da Apostila"):
        _documento(casa, pedido_id)


def test_documento_sem_quem_assinou_nem_autoridade_e_recusado(casa):
    """O registro da Convenção (art. 7º) pede um ou outro."""
    pedido_id = _pedido(casa)
    with pytest.raises(AP.ApostilaError, match="selo ou carimbo"):
        _documento(casa, pedido_id, signatario_nome="", signatario_cargo="")
    # O documento sem assinatura entra pela autoridade do selo ou carimbo.
    assert _documento(casa, pedido_id, signatario_nome="", signatario_cargo="",
                      autoridade="SECRETARIA FICTICIA DE EDUCACAO")


def test_quem_assinou_sem_cargo_e_recusado(casa):
    with pytest.raises(AP.ApostilaError, match="cargo ou a função"):
        _documento(casa, _pedido(casa), signatario_cargo="")


def test_tipo_outro_pede_descricao(casa):
    with pytest.raises(AP.ApostilaError, match="descreva"):
        _documento(casa, _pedido(casa), documento_tipo="OUTRO")


def test_o_protesto_nao_apostila_porque_o_ato_nao_esta_liberado(casa):
    """O acervo do E-Ofício marca o ato 101 (Apostila no Protesto) como não liberado."""
    assert "PROTESTO" not in AP.ATRIBUICOES_LIBERADAS
    assert set(AP.ATRIBUICOES_LIBERADAS) == {"NOTAS", "RTD", "RI"}
    with pytest.raises(AP.ApostilaError, match="atribuição"):
        _pedido(casa, atribuicao="PROTESTO")


def test_cpf_que_nao_fecha_o_digito_e_recusado(casa):
    with pytest.raises(AP.ApostilaError, match="digito verificador"):
        _pedido(casa, requerente_documento="111.444.777-00")
    assert _pedido(casa, requerente_documento="000.000.049-36")


def test_protocolo_geral_que_nao_existe_e_recusado(casa):
    with pytest.raises(AP.ApostilaError, match="não existe"):
        _pedido(casa, protocolo="2026.10.999")
    numero, _ = _protocolo_com_item(casa)
    pedido_id = _pedido(casa, protocolo=numero)
    assert _ler(casa, "SELECT protocolo_numero FROM ap_pedidos WHERE id = %s",
                (pedido_id,))[0]["protocolo_numero"] == numero


def test_data_no_futuro_e_recusada(casa):
    with pytest.raises(AP.ApostilaError, match="futuro"):
        _pedido(casa, recebido_em="2026-10-20")
    apostila_id = _documento(casa, _pedido(casa))
    with casa["db"].transaction() as con, pytest.raises(AP.ApostilaError, match="futuro"):
        AP.emitir(con, apostila_id, agora=AGORA, por="X", codigo_cnj="ABCD1234",
                  emitida_em="2026-10-20")


# ------------------------------------------------- emissão e controle


def test_o_numero_de_ordem_so_nasce_na_emissao_e_e_sequencial(casa):
    pedido_id = _pedido(casa)
    recusada, primeira, segunda = (_documento(casa, pedido_id) for _ in range(3))
    with casa["db"].transaction() as con:
        AP.recusar(con, recusada, agora=AGORA, por="X",
                   motivo="Assinatura não confere com o cadastro")
    assert _emitir(casa, primeira, "BR-0001-TESTE")["ordem"] == 1
    assert _emitir(casa, segunda, "BR-0002-TESTE")["ordem"] == 2
    linhas = _ler(casa, "SELECT id, ordem, situacao FROM ap_apostilas ORDER BY id")
    assert [(x["ordem"], x["situacao"]) for x in linhas] == [
        (None, "RECUSADA"), (1, "EMITIDA"), (2, "EMITIDA")]


def test_emitida_nao_se_emite_de_novo_nem_se_recusa(casa):
    apostila_id = _documento(casa, _pedido(casa))
    _emitir(casa, apostila_id, "BR-0001-TESTE")
    with pytest.raises(AP.ApostilaError, match="não pode ser emitida de novo"):
        _emitir(casa, apostila_id, "BR-0009-TESTE")
    with casa["db"].transaction() as con, pytest.raises(AP.ApostilaError):
        AP.recusar(con, apostila_id, agora=AGORA, por="X", motivo="Motivo qualquer longo")


def test_o_mesmo_codigo_do_cnj_e_o_mesmo_selo_nao_entram_duas_vezes(casa):
    pedido_id = _pedido(casa)
    a, b, c = (_documento(casa, pedido_id) for _ in range(3))
    _emitir(casa, a, "br-0001-teste", selo="SELO-TESTE-1")
    with pytest.raises(AP.ApostilaError, match="já está no controle"):
        _emitir(casa, b, "BR-0001-TESTE")
    with pytest.raises(AP.ApostilaError, match="já está em outra apostila"):
        _emitir(casa, b, "BR-0002-TESTE", selo="selo-teste-1")
    _emitir(casa, c, "BR-0003-TESTE")
    with casa["db"].transaction() as con, pytest.raises(AP.ApostilaError, match="outra apostila"):
        AP.registrar_selo(con, c, agora=AGORA, por="X", selo="SELO-TESTE-1")


def test_cancelar_mantem_o_numero_no_controle_e_pede_motivo(casa):
    apostila_id = _documento(casa, _pedido(casa))
    _emitir(casa, apostila_id, "BR-0001-TESTE")
    with casa["db"].transaction() as con, pytest.raises(AP.ApostilaError, match="motivo"):
        AP.cancelar(con, apostila_id, agora=AGORA, por="X", motivo="erro")
    with casa["db"].transaction() as con:
        AP.cancelar(con, apostila_id, agora=AGORA, por="X",
                    motivo="Cancelada no CNJ por erro de digitação")
    with casa["db"].connect() as con:
        r = AP.controle(con)
    assert [(x["ordem"], x["situacao"]) for x in r["linhas"]] == [(1, "CANCELADA")]
    assert (r["emitidas"], r["canceladas"], r["total"]) == (0, 1, "0,00")
    # A próxima não reaproveita o número da cancelada.
    outra = _documento(casa, _pedido(casa))
    assert _emitir(casa, outra, "BR-0002-TESTE")["ordem"] == 2


def test_emitir_consome_o_item_do_protocolo_geral_e_cancelar_devolve(casa):
    numero, item_id = _protocolo_com_item(casa)
    pedido_id = _pedido(casa, protocolo=numero)
    apostila_id = _documento(casa, pedido_id)
    with casa["db"].connect() as con:
        assert [i["id"] for i in AP.itens_para_cobrar(con, pedido_id)] == [item_id]
    _emitir(casa, apostila_id, "BR-0001-TESTE", protocolo_item_id=str(item_id))
    item = _ler(casa, "SELECT * FROM cx_protocolo_atos WHERE id = %s", (item_id,))[0]
    assert (item["quantidade_usada"], item["usado_por_tabela"],
            item["usado_por_ato_id"]) == (1, "ap_apostilas", apostila_id)
    with casa["db"].connect() as con:
        assert AP.itens_para_cobrar(con, pedido_id) == []
    # Item sem saldo não paga uma segunda apostila.
    outra = _documento(casa, pedido_id)
    with pytest.raises(AP.ApostilaError, match="saldo"):
        _emitir(casa, outra, "BR-0002-TESTE", protocolo_item_id=str(item_id))
    with casa["db"].transaction() as con:
        assert AP.cancelar(con, apostila_id, agora=AGORA, por="X",
                           motivo="Cancelada no CNJ por erro de digitação")["unidade_devolvida"]
    item = _ler(casa, "SELECT quantidade_usada FROM cx_protocolo_atos WHERE id = %s",
                (item_id,))[0]
    assert item["quantidade_usada"] == 0
    # A apostila que vem no lugar usa o mesmo pagamento.
    _emitir(casa, outra, "BR-0002-TESTE", protocolo_item_id=str(item_id))


def test_item_de_outro_servico_nao_paga_a_apostila(casa):
    numero, item_id = _protocolo_com_item(casa, servico=105, codigo_tj="11.1")
    pedido_id = _pedido(casa, protocolo=numero)
    apostila_id = _documento(casa, pedido_id)
    with pytest.raises(AP.ApostilaError, match="não é da apostila"):
        _emitir(casa, apostila_id, "BR-0001-TESTE", protocolo_item_id=str(item_id))
    assert _ler(casa, "SELECT situacao FROM ap_apostilas WHERE id = %s",
                (apostila_id,))[0]["situacao"] == "PENDENTE"


def test_as_pendencias_cobram_emissao_selo_e_cobranca(casa):
    pedido_id = _pedido(casa)
    na_fila, sem_nada = _documento(casa, pedido_id), _documento(casa, pedido_id)
    _emitir(casa, sem_nada, "BR-0001-TESTE")
    with casa["db"].connect() as con:
        faltas = {(x["id"], x["falta"]) for x in AP.pendencias(con)}
    assert faltas == {(na_fila, "emissão no sistema do CNJ"), (sem_nada, "selo"),
                      (sem_nada, "cobrança no protocolo geral")}
    with casa["db"].transaction() as con:
        AP.registrar_selo(con, sem_nada, agora=AGORA, por="X", selo="SELO-TESTE-9")
    with casa["db"].connect() as con:
        assert (sem_nada, "selo") not in {(x["id"], x["falta"]) for x in AP.pendencias(con)}


# ------------------------------------------------- as telas e o rastro


def test_o_balcao_faz_o_caminho_inteiro_pela_tela(casa):
    _ligar(casa)
    escrevente = _entrar(casa, "ap_usr", "USER")
    r = _post(escrevente, "/apostila/pedido", recebido_em=HOJE, atribuicao="NOTAS",
              requerente_nome=REQUERENTE, requerente_documento="000.000.049-36",
              pais_destino="Portugal")
    assert r.status_code == 302
    pedido_id = int(r.headers["Location"].rstrip("/").split("/")[-1])
    r = _post(escrevente, f"/apostila/pedido/{pedido_id}/documento",
              documento_tipo="REGISTRO_CIVIL", signatario_nome="OFICIAL FICTICIO",
              signatario_cargo="Oficial de Registro Civil")
    assert r.status_code == 302
    apostila_id = _ler(casa, "SELECT id FROM ap_apostilas WHERE pedido_id = %s ORDER BY id",
                       (pedido_id,))[0]["id"]
    html = escrevente.get(f"/apostila/pedido/{pedido_id}").get_data(as_text=True)
    assert "total R$ 140,01" in html
    _post(escrevente, f"/apostila/{apostila_id}/emitir", codigo_cnj="BR-0001-TESTE",
          emitida_em=HOJE, selo="SELO-TESTE-1")
    html = escrevente.get("/apostila/controle").get_data(as_text=True)
    assert "BR-0001-TESTE" in html and "OFICIAL FICTICIO, Oficial de Registro Civil" in html
    assert "1 emitida(s), 0 cancelada(s). Total das emitidas: R$ 140,01" in html
    certidao = escrevente.get(f"/apostila/{apostila_id}/certidao").get_data(as_text=True)
    assert "nº de ordem 1" in certidao and "BR-0001-TESTE" in certidao
    assert REQUERENTE not in certidao
    acoes = [x["action"] for x in _ler(
        casa, "SELECT action FROM audit_logs WHERE action LIKE %s ORDER BY id", ("APOSTILA_%",))]
    assert acoes == ["APOSTILA_PEDIDO", "APOSTILA_DOCUMENTO", "APOSTILA_EMITIDA",
                     "APOSTILA_CERTIDAO"]


def test_o_rastro_nao_leva_o_nome_nem_o_documento_de_quem_pediu(casa):
    _ligar(casa)
    escrevente = _entrar(casa, "ap_usr", "USER")
    _post(escrevente, "/apostila/pedido", recebido_em=HOJE, atribuicao="NOTAS",
          requerente_nome=REQUERENTE, requerente_documento="000.000.049-36")
    detalhes = " ".join(x["details"] or "" for x in _ler(
        casa, "SELECT details FROM audit_logs WHERE action LIKE %s ORDER BY id", ("APOSTILA_%",)))
    assert detalhes
    assert "FULANA" not in detalhes and "00000004936" not in detalhes


def test_a_frase_do_impedimento_volta_para_a_ficha(casa):
    _ligar(casa)
    escrevente = _entrar(casa, "ap_usr", "USER")
    pedido_id = _pedido(casa)
    r = _post(escrevente, f"/apostila/pedido/{pedido_id}/documento",
              documento_tipo="REGISTRO_CIVIL")
    assert r.status_code == 302
    html = escrevente.get(r.headers["Location"]).get_data(as_text=True)
    assert "selo ou carimbo" in html
    assert not _ler(casa, "SELECT id FROM ap_apostilas ORDER BY id")


def test_certidao_so_de_apostila_que_esta_no_controle(casa):
    _ligar(casa)
    escrevente = _entrar(casa, "ap_usr", "USER")
    apostila_id = _documento(casa, _pedido(casa))
    r = escrevente.get(f"/apostila/{apostila_id}/certidao")
    assert r.status_code == 302
    assert escrevente.get("/apostila/999999/certidao").status_code == 404


# ------------------------------------------------- o esquema


def test_o_esquema_e_nativo_com_dinheiro_e_numero_em_bigint(casa):
    tipos = {x["column_name"]: x["data_type"] for x in _ler(
        casa, """SELECT column_name, data_type FROM information_schema.columns
                  WHERE table_schema = current_schema() AND table_name = 'ap_apostilas'
                  ORDER BY ordinal_position""")}
    for coluna in ("id", "pedido_id", "ordem", "emolumentos", "total", "protocolo_item_id"):
        assert tipos[coluna] == "bigint", coluna
    indices = {x["indexname"] for x in _ler(
        casa, """SELECT indexname FROM pg_indexes
                  WHERE schemaname = current_schema() AND tablename = 'ap_apostilas'
                  ORDER BY indexname""")}
    assert {"ux_ap_apostilas_codigo", "ux_ap_apostilas_selo",
            "ix_ap_apostilas_pedido"} <= indices


def test_a_subida_cria_o_indice_que_falta_em_tabela_que_ja_existe(casa):
    """Tabela já existente ganha o índice novo — o `if not tem_tabela` por objeto."""
    with casa["db"].transaction() as con:
        banco(con).escrever("DROP INDEX ix_ap_apostilas_emitida")
    try:
        with casa["db"].transaction() as con:
            AP.init_apostila_schema(con)
            assert banco(con).tem_tabela("ix_ap_apostilas_emitida")
    finally:
        with casa["db"].transaction() as con:
            AP.init_apostila_schema(con)
