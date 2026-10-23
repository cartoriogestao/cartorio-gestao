"""A autenticação de livros contábeis no RCPJ — `rg_livro_contabil.py` (LG04).

O QUE ESTES TESTES PROTEGEM:

    o controle numera na autenticação    o pedido não toma número; a
                                         autenticação toma o seguinte do
                                         exercício, e o exercício novo
                                         recomeça do 1

    o mesmo livro, uma vez               mesmo CNPJ + tipo + número de ordem
                                         recusa, pela trava e pelo índice;
                                         o cancelado libera

    os termos congelados                 abertura e encerramento saem com os
                                         dados do livro e não se remontam

    o item não se adivinha               sem item configurado não numera nem
                                         sela; com item, o preço é o da tabela

    o selo                               o que sai autentica e amarra; o que
                                         não sai suspende, e «selar de novo»
                                         completa sem trocar o número

    a porta                              anônimo vai ao login, o balcão pede
                                         mas não autentica, POST sem CSRF é
                                         recusado, toda escrita deixa rastro

Dados fictícios (EXEMPLO LTDA, CNPJ de teste). Nenhum teste fala com o
selador de verdade: o selo que sai é um dublê de `selador_cliente.selar`.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rg_livro_contabil as LC
from bd_nativo import banco
from conftest import cg_login

SENHA = "Senha#12345"
CNPJ = "00000043000177"          # o CNPJ de teste de sempre, com dígito válido
ITEM = "15.7.1"
LISTA = "/rcpj-rtd/livros-contabeis"


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.set_settings({"ri_cns": "000000", "selo_tabela_custas_em": "20260101"})
    db.create_user("oficial", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.create_user("balcao", "BALCAO EXEMPLO", SENHA, "USER")
    db.create_user("auditor", "AUDITOR EXEMPLO", SENHA, "AUDITOR")
    with db.transaction() as con:
        bd = banco(con)
        bd.escrever(
            """INSERT INTO cx_vigencias (codigo, descricao, vigente, inicio, fim,
                                         importado_em)
               VALUES (10022, 'PERIODO DE TESTE 2026', 1, '2026-01-01',
                       '2026-12-31', '2026-08-21')
               ON CONFLICT DO NOTHING""")
        bd.escrever(
            """INSERT INTO cx_servicos (codigo, codigo_tj, descricao, ativo)
               VALUES (493, %s, 'Até cinco folhas', 1) ON CONFLICT DO NOTHING""",
            (ITEM,))
        bd.escrever(
            """INSERT INTO cx_servico_valores (servico, vigencia, emolumentos,
                   ferc, femp, fadep, ferrfis, total)
               VALUES (493, 10022, '89,52', '2,69', '3,58', '3,58', '0,90',
                       '100,27')
               ON CONFLICT DO NOTHING""")
    return cg_casa


def _entrar(casa, usuario="oficial"):
    c = casa["app"].test_client()
    cg_login(c, usuario, SENHA)
    return c


def _token(c, url=LISTA + "/novo") -> str:
    html = c.get(url).get_data(as_text=True)
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


def _pedido(**extra) -> dict:
    base = {"pj_nome": "EXEMPLO LTDA", "pj_cnpj": CNPJ, "tipo_livro": "DIARIO",
            "numero_livro": "1", "folhas": "100", "folha_de": "1",
            "folha_ate": "100", "forma": "PAPEL",
            "apresentante_nome": "FULANO DE EXEMPLO"}
    base.update(extra)
    return base


def _pedir(casa, **extra) -> int:
    with casa["db"].transaction() as con:
        return LC.pedir(con, _pedido(**extra), agora=casa["db"].now(),
                        usuario="BALCAO EXEMPLO")["id"]


def _linha(casa, livro_id) -> dict:
    with casa["db"].connect() as con:
        return LC.um(con, livro_id)


def _configurar_item(casa):
    casa["db"].set_settings({LC.CHAVE_DO_ITEM: ITEM})


@pytest.fixture()
def protocolo_pago(casa):
    """O balcão já recebeu: protocolo pago com o 15.7.1, atendido pelo oficial.

    Desde o LX16 o selo PAGO só sai com protocolo e pagamento
    (`ato_selado.cobrir_o_selo`). Estes testes falam da autenticação do
    livro, e não do caixa: montam o que o balcão monta, pelo helper único
    `protocolo_de_teste`, em vez de desligar a trava. Os que medem o selo
    que NÃO sai também o pedem: sem ele, quem suspendia era a trava, e não
    o aparelho ausente.
    """
    from protocolo_de_teste import atender_protocolo_pago
    with casa["db"].transaction() as con:
        return atender_protocolo_pago(con, usuario="MARIO EXEMPLO DOS SANTOS",
                                      codigos=(ITEM,))


def _selador_que_responde(monkeypatch) -> list[dict]:
    """O dublê do aparelho: confere o pedido pelo contrato e grava no razão,
    como o real (`selador_cliente.selar`)."""
    import selador
    import selador_cliente as CL
    chamadas: list[dict] = []

    def falso(con, pasta, caminho, dados, *, referencia, atribuicao, agora,
              cns, tentativa=1, usuario=None, **_):
        selador.montar_pedido(caminho, dados)
        numero = f"RCPJTESTE{len(chamadas) + 1:06d}"
        chamadas.append({"caminho": caminho, "dados": dados,
                         "referencia": referencia})
        banco(con).escrever(
            """INSERT INTO sd_selos (numero, texto, sid, caminho, atribuicao,
                   referencia, obtido_em, obtido_por, ambiente)
               VALUES (%s, 'SELO DE TESTE', %s, %s, %s, %s, %s, %s,
                       'HOMOLOGACAO')""",
            (numero, f"sid:{referencia}", caminho, atribuicao, str(referencia),
             agora, usuario))
        return [selador.SeloGerado(numero=numero, texto="SELO DE TESTE")]

    monkeypatch.setattr(CL, "selar", falso)
    return chamadas


def _autenticar_pela_tela(casa, livro_id, c=None, **extra):
    c = c or _entrar(casa)
    dados = {"csrf_token": _token(c, f"{LISTA}/{livro_id}")}
    dados.update(extra)
    return c.post(f"{LISTA}/{livro_id}/autenticar", data=dados,
                  follow_redirects=True)


def _acoes(casa, acao: str) -> list[dict]:
    with casa["db"].connect() as con:
        return banco(con).ler(
            "SELECT * FROM audit_logs WHERE action = %s ORDER BY id", (acao,))


# ------------------------------------------------------------ o controle


def test_o_pedido_nao_toma_numero_e_a_autenticacao_toma_o_seguinte(casa, protocolo_pago,
                                                                   monkeypatch):
    _configurar_item(casa)
    _selador_que_responde(monkeypatch)
    a = _pedir(casa)
    b = _pedir(casa, numero_livro="2")
    assert _linha(casa, a)["numero"] is None
    _autenticar_pela_tela(casa, a)
    _autenticar_pela_tela(casa, b)
    ano = int(casa["db"].now()[:4])
    assert (_linha(casa, a)["numero"], _linha(casa, a)["ano"]) == (1, ano)
    assert (_linha(casa, b)["numero"], _linha(casa, b)["ano"]) == (2, ano)


def test_o_exercicio_novo_recomeca_o_controle_do_um(casa):
    a = _pedir(casa)
    with casa["db"].transaction() as con:
        # um do ano passado com número alto não puxa a conta deste ano
        banco(con).escrever(
            """INSERT INTO rg_livros_contabeis (numero, ano, pj_nome, pj_cnpj,
                   tipo_livro, numero_livro, folhas, folha_de, folha_ate,
                   situacao, pedido_em)
               VALUES (7, 2025, 'OUTRA EXEMPLO', %s, 'RAZAO', 9, 10, 1, 10,
                       'AUTENTICADO', '2025-12-30T10:00:00')""", (CNPJ,))
        r = LC.autenticar(con, a, codigo_tj=ITEM, serventia={},
                          hoje="2026-10-19", agora="2026-10-19T10:00:00",
                          usuario="MARIO EXEMPLO DOS SANTOS", funcao="Oficial")
    assert r == {"numero": 1, "ano": 2026}


def test_o_mesmo_livro_nao_se_autentica_duas_vezes(casa):
    _pedir(casa)
    with pytest.raises(LC.LivroContabilError, match="não se autentica duas vezes"):
        _pedir(casa)
    # outro número de ordem, ou outro tipo, é outro livro
    _pedir(casa, numero_livro="2")
    _pedir(casa, tipo_livro="RAZAO")


def test_o_outro_livro_se_distingue_pela_descricao(casa):
    _pedir(casa, tipo_livro="OUTRO", tipo_descricao="Livro de Registro de Ações")
    _pedir(casa, tipo_livro="OUTRO", tipo_descricao="Livro de Atas do Conselho")
    with pytest.raises(LC.LivroContabilError):
        _pedir(casa, tipo_livro="OUTRO", tipo_descricao="livro de registro de ações")


def test_o_indice_unico_e_a_segunda_tranca_do_mesmo_livro(casa):
    """Quem escrever por fora da trava ainda esbarra no banco."""
    _pedir(casa)
    with pytest.raises(sqlite3.IntegrityError):
        with casa["db"].transaction() as con:
            banco(con).escrever(
                """INSERT INTO rg_livros_contabeis (pj_nome, pj_cnpj, tipo_livro,
                       numero_livro, folhas, folha_de, folha_ate, pedido_em)
                   VALUES ('EXEMPLO LTDA', %s, 'DIARIO', 1, 5, 1, 5,
                           '2026-10-19T10:00:00')""", (CNPJ,))


def test_o_cancelado_libera_o_livro_e_nao_devolve_o_numero(casa, protocolo_pago,
                                                           monkeypatch):
    _configurar_item(casa)
    _selador_que_responde(monkeypatch)
    a = _pedir(casa)
    _autenticar_pela_tela(casa, a)
    with pytest.raises(LC.LivroContabilError, match="dez letras"):
        with casa["db"].transaction() as con:
            LC.cancelar(con, a, motivo="errado", agora="x", usuario="X")
    c = _entrar(casa)
    c.post(f"{LISTA}/{a}/cancelar", follow_redirects=True,
           data={"csrf_token": _token(c, f"{LISTA}/{a}"),
                 "motivo": "folhas contadas errado pelo apresentante"})
    assert _linha(casa, a)["situacao"] == "CANCELADO"
    b = _pedir(casa)
    _autenticar_pela_tela(casa, b)
    assert _linha(casa, b)["numero"] == 2
    assert _acoes(casa, "RCPJ_LIVRO_CONTABIL_CANCELADO")


def test_folhas_que_nao_batem_com_a_numeracao_sao_recusadas(casa):
    with pytest.raises(LC.LivroContabilError, match="As folhas não batem"):
        _pedir(casa, folhas="100", folha_de="1", folha_ate="99")
    with pytest.raises(LC.LivroContabilError, match="precisa ter folhas"):
        _pedir(casa, folhas="0")


def test_cnpj_com_digito_errado_e_recusado(casa):
    with pytest.raises(LC.LivroContabilError, match="CNPJ"):
        _pedir(casa, pj_cnpj="11222333000180")


def test_o_livro_anterior_ausente_vira_aviso_e_nao_recusa(casa):
    with casa["db"].transaction() as con:
        r = LC.pedir(con, _pedido(numero_livro="5"), agora=casa["db"].now())
    assert r["id"]
    assert any("nº 4" in a for a in r["avisos"])
    with casa["db"].transaction() as con:
        r1 = LC.pedir(con, _pedido(tipo_livro="RAZAO"), agora=casa["db"].now())
    assert r1["avisos"] == []


# ------------------------------------------------------------ os termos


def test_os_termos_saem_com_os_dados_do_livro_e_ficam_congelados(casa, protocolo_pago,
                                                                 monkeypatch):
    _configurar_item(casa)
    _selador_que_responde(monkeypatch)
    a = _pedir(casa)
    _autenticar_pela_tela(casa, a)
    linha = _linha(casa, a)
    ano = linha["ano"]
    for termo in (linha["termo_abertura"], linha["termo_encerramento"]):
        assert "EXEMPLO LTDA" in termo
        assert "00.000.043/0001-77" in termo
        assert "100 folhas" in termo and "de 1 a 100" in termo
        assert f"nº 1/{ano}" in termo
        assert "Livro Diário nº 1" in termo
    assert linha["termo_abertura"].startswith("TERMO DE ABERTURA")
    assert linha["termo_encerramento"].startswith("TERMO DE ENCERRAMENTO")
    # o papel sai do que foi gravado, e não se remonta com o dado de hoje
    with casa["db"].transaction() as con:
        banco(con).escrever(
            "UPDATE rg_livros_contabeis SET pj_nome = 'NOME TROCADO' WHERE id = %s",
            (a,))
    html = _entrar(casa, "auditor").get(f"{LISTA}/{a}/papel/abertura").get_data(as_text=True)
    assert "EXEMPLO LTDA" in html and "NOME TROCADO" not in html


def test_a_certidao_so_sai_da_autenticacao_concluida(casa, protocolo_pago,
                                                     monkeypatch):
    _configurar_item(casa)
    a = _pedir(casa)
    _autenticar_pela_tela(casa, a)          # sem selador: fica suspensa
    with casa["db"].connect() as con:
        with pytest.raises(LC.LivroContabilError, match="concluída"):
            LC.certidao(con, a, {}, hoje="2026-10-19", full_name="X", funcao="Y")
    _selador_que_responde(monkeypatch)
    _autenticar_pela_tela(casa, a)
    with casa["db"].connect() as con:
        texto = LC.certidao(con, a, {}, hoje="2026-10-19",
                            full_name="MARIO EXEMPLO DOS SANTOS", funcao="Oficial")
    assert texto.startswith("CERTIDÃO DE AUTENTICAÇÃO DE LIVRO")
    assert "RCPJTESTE000001" in texto and "MARIO EXEMPLO DOS SANTOS" in texto


# ------------------------------------------------------ o item e o selo


def test_sem_item_configurado_a_autenticacao_nao_numera_e_diz_o_que_falta(casa):
    a = _pedir(casa)
    html = _autenticar_pela_tela(casa, a).get_data(as_text=True)
    assert "Falta configurar o item" in html
    linha = _linha(casa, a)
    assert linha["situacao"] == "PEDIDO" and linha["numero"] is None


def test_com_item_configurado_a_ficha_mostra_o_preco_da_tabela(casa):
    c = _entrar(casa)
    c.post(f"{LISTA}/configuracao", follow_redirects=True,
           data={"csrf_token": _token(c, f"{LISTA}/configuracao"), "item": ITEM})
    assert casa["db"].get_setting(LC.CHAVE_DO_ITEM) == ITEM
    assert _acoes(casa, "RCPJ_LIVRO_CONTABIL_ITEM_CONFIGURADO")
    a = _pedir(casa)
    html = c.get(f"{LISTA}/{a}").get_data(as_text=True)
    assert "R$ 100,27" in html


def test_item_que_nao_esta_na_tabela_nao_se_configura(casa):
    c = _entrar(casa)
    html = c.post(f"{LISTA}/configuracao", follow_redirects=True,
                  data={"csrf_token": _token(c, f"{LISTA}/configuracao"),
                        "item": "99.99"}).get_data(as_text=True)
    assert "não está na tabela" in html
    assert casa["db"].get_setting(LC.CHAVE_DO_ITEM) == ""


def test_o_selo_que_sai_autentica_e_amarra_o_numero_ao_livro(casa, protocolo_pago,
                                                             monkeypatch):
    _configurar_item(casa)
    chamadas = _selador_que_responde(monkeypatch)
    a = _pedir(casa)
    html = _autenticar_pela_tela(casa, a).get_data(as_text=True)
    assert "Selo RCPJTESTE000001" in html
    linha = _linha(casa, a)
    assert linha["situacao"] == "AUTENTICADO" and linha["selo"] == "RCPJTESTE000001"
    pedido = chamadas[0]
    assert pedido["caminho"] == "/selo/rtdpj/autenticacao-contabil"
    assert pedido["referencia"] == f"rg_livros_contabeis:{a}"
    assert pedido["dados"]["ato"] == {"codigo": ITEM,
                                      "codigoTabelaCusta": "0420260101"}
    assert pedido["dados"]["escrevente"] == "MARIO EXEMPLO DOS SANTOS"
    assert pedido["dados"]["partes"]["parteAto"] == [
        {"nome": "EXEMPLO LTDA", "documento": CNPJ}]
    with casa["db"].connect() as con:
        razao = banco(con).um("SELECT tabela, ato_id FROM sd_selos WHERE numero = %s",
                              ("RCPJTESTE000001",))
    assert (razao["tabela"], razao["ato_id"]) == ("rg_livros_contabeis", a)
    assert _acoes(casa, "RCPJ_LIVRO_CONTABIL_SELADO")


def test_o_selo_que_nao_sai_suspende_e_selar_de_novo_completa(casa, protocolo_pago,
                                                              monkeypatch):
    _configurar_item(casa)
    a = _pedir(casa)
    html = _autenticar_pela_tela(casa, a).get_data(as_text=True)
    assert "SUSPENSA" in html
    linha = _linha(casa, a)
    assert linha["situacao"] == "SUSPENSO_SELO" and linha["selo"] is None
    assert linha["numero"] == 1 and linha["motivo_suspensao"]
    assert "aguardando cobertura" not in linha["motivo_suspensao"]
    assert _acoes(casa, "RCPJ_LIVRO_CONTABIL_SELO_FALHOU")
    _selador_que_responde(monkeypatch)
    _autenticar_pela_tela(casa, a)
    linha = _linha(casa, a)
    assert linha["situacao"] == "AUTENTICADO" and linha["numero"] == 1
    assert linha["motivo_suspensao"] is None


def test_o_caixa_so_lanca_com_caixa_aberto_e_diz_quando_nao_ha(casa, protocolo_pago,
                                                               monkeypatch):
    _configurar_item(casa)
    _selador_que_responde(monkeypatch)
    a = _pedir(casa)
    html = _autenticar_pela_tela(casa, a, cobrar="1").get_data(as_text=True)
    assert "não tem caixa aberto" in html
    assert _linha(casa, a)["lancamento_id"] is None


# ------------------------------------------------------------- a porta


def test_anonimo_vai_para_o_login(casa):
    anonimo = casa["app"].test_client()
    for url in (LISTA, LISTA + "/novo", LISTA + "/configuracao"):
        assert anonimo.get(url).status_code == 302, url


def test_o_balcao_pede_mas_nao_autentica_nem_configura(casa):
    c = _entrar(casa, "balcao")
    r = c.post(LISTA + "/novo", data={"csrf_token": _token(c), **_pedido()})
    assert r.status_code == 302
    with casa["db"].connect() as con:
        a = banco(con).valor("SELECT max(id) AS n FROM rg_livros_contabeis")
    token = _token(c, f"{LISTA}/{a}")
    assert c.post(f"{LISTA}/{a}/autenticar",
                  data={"csrf_token": token}).status_code == 403
    assert c.post(f"{LISTA}/{a}/cancelar",
                  data={"csrf_token": token, "motivo": "x" * 20}).status_code == 403
    assert c.get(LISTA + "/configuracao").status_code == 403
    assert _acoes(casa, "RCPJ_LIVRO_CONTABIL_PEDIDO")


def test_o_auditor_le_mas_nao_pede(casa):
    c = _entrar(casa, "auditor")
    assert c.get(LISTA).status_code == 200
    assert c.get(LISTA + "/novo").status_code == 403


def test_post_sem_csrf_e_recusado(casa):
    c = _entrar(casa)
    assert c.post(LISTA + "/novo", data=_pedido()).status_code == 400
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM rg_livros_contabeis") == 0


def test_a_lista_busca_por_cnpj_e_nao_escreve(casa):
    _pedir(casa)
    _pedir(casa, pj_cnpj="11444777000161", pj_nome="OUTRA EXEMPLO")
    c = _entrar(casa, "auditor")
    with casa["db"].connect() as con:
        antes = banco(con).valor("SELECT count(*) AS n FROM audit_logs")
    html = c.get(LISTA, query_string={"cnpj": "00.000.043/0001-77"}).get_data(as_text=True)
    assert "EXEMPLO LTDA" in html and "OUTRA EXEMPLO" not in html
    with casa["db"].connect() as con:
        assert banco(con).valor("SELECT count(*) AS n FROM audit_logs") == antes
