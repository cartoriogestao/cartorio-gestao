"""A ponte do título para a Intimação Digital, e a tela dela.

**O DEFEITO MAIS CARO QUE ESTE ARQUIVO GUARDA É A CONVERSÃO DE CENTAVOS.** A
casa guarda `valor_centavos` como inteiro; a Central quer reais com duas casas
(`2255.39`). Mandar o inteiro faria a intimação cobrar **cem vezes o valor** —
e o devedor receberia isso escrito, com o nome desta serventia em cima.

**E O SEGUNDO É O TÍTULO SUSTADO.** O § 1º do art. 17 da Lei 9.492/1997 diz que
o título sustado só se paga, protesta ou retira com autorização judicial;
`protesto` já recusa os três. Deixar a mensageria correndo sobre ele seria
cobrar justamente quem o juiz mandou parar — pelo caminho que não passa pelas
guardas do módulo de protesto.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CRED                                     # noqa: E402
import resolve_api as API                                        # noqa: E402
import resolve_intimacao as RI                                   # noqa: E402

SENHA = "Senha#12345"
CHAVE = "21987650141243301260417"           # 23 dígitos, do CENPROT


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    bd.set_settings({"modulo_protesto_alcance": "TODOS"})
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


@pytest.fixture()
def sem_chave(monkeypatch, tmp_path):
    """A pasta das credenciais das Centrais apontada para uma pasta VAZIA.

    **AQUI O PINO TEM DE SER A PASTA, E NÃO UMA FUNÇÃO** — medido em
    18/09/2026. A tela pergunta a `CENTCRED.tem(RESOLVE, ambiente)`; o envio
    vai por `resolve_api.chave`. São **dois** caminhos de leitura, e prender um
    só deixaria o outro lendo `%PROGRAMDATA%`. A pasta vazia prende os dois.

    Sem isto os dois testes ficavam verdes enquanto `resolve.cred` não existia
    — e ficariam vermelhos no dia em que o oficial informar a `x-api-key`, sem
    uma linha de código mudar. É o que aconteceu com o ONRTDPJ em 12/09/2026.
    """
    monkeypatch.setattr(CRED, "pasta_de_dados", lambda: tmp_path)


def _titulo(s, **troca) -> int:
    """Um título com devedor, do jeito que a carga o deixa."""
    dados = {"especie": "DM", "numero_titulo": "36410/2024",
             "chave_cenprot": CHAVE, "data_vencimento": "2026-10-09",
             "valor_centavos": 225539, "saldo_centavos": 225539,
             "situacao": "APONTADO", "protocolo": "2604170001",
             "cedente_nome": "BANCO EXEMPLO S/A",
             "cedente_documento": "45315321000113",
             "apresentante_nome": "BANCO EXEMPLO S/A",
             "origem": "CRA", "criado_em": "2026-09-03"}
    dados.update(troca)
    con = sqlite3.connect(s["banco"])
    colunas = ", ".join(dados)
    marcas = ", ".join("?" for _ in dados)
    cur = con.execute(f"INSERT INTO pt_titulos ({colunas}) VALUES ({marcas})",
                      list(dados.values()))
    tid = cur.lastrowid
    con.execute(
        """INSERT INTO pt_devedores
               (titulo_id, nome, documento_tipo, documento_numero,
                endereco, bairro, cep, cidade, uf)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (tid, "MARCOS COSTA DA SILVA", "CPF", "04243752101",
         "Rua das Flores, 123", "Centro", "65920000", "Cidade Exemplo", "MA"))
    con.commit()
    con.close()
    return int(tid)


# ------------------------------------------------ o dinheiro


def test_centavos_viram_REAIS_e_nao_o_inteiro_cru():
    """**Cem vezes o valor**, se isto quebrar — e escrito num papel com o nome
    da serventia."""
    assert RI._reais(225539) == 2255.39
    assert RI._reais(100) == 1.0
    assert RI._reais(0) == 0.0
    assert RI._reais(None) == 0.0


def test_o_valor_do_titulo_sai_em_reais_no_corpo():
    titulo = {"valor_centavos": 225539, "saldo_centavos": 225539,
              "numero_titulo": "1", "especie": "DM",
              "data_vencimento": "2026-10-09", "chave_cenprot": CHAVE}
    devedor = {"nome": "D", "documento_numero": "04243752101",
               "endereco": "R", "cep": "65920000", "cidade": "c", "uf": "MA"}
    corpo = RI.montar(titulo, devedor, identificador="X-1")
    assert corpo["titulo"]["valorTitulo"] == 2255.39
    assert corpo["titulo"]["valorDivida"] == 2255.39


def test_o_valor_a_pagar_e_de_quem_chama_e_nunca_zero():
    """**O contrato não diz a fórmula** de `valorAPagar` — é «o valor total a
    ser pago pelo devedor». Sem ninguém informar, vai o valor do título, que é
    o que se sabe; zero afirmaria que não se deve nada."""
    titulo = {"valor_centavos": 225539, "numero_titulo": "1", "especie": "DM",
              "data_vencimento": "2026-10-09", "chave_cenprot": CHAVE}
    devedor = {"nome": "D", "documento_numero": "1", "endereco": "R",
               "cep": "1", "cidade": "c", "uf": "MA"}
    assert RI.montar(titulo, devedor, identificador="X")[
        "titulo"]["valorAPagar"] == 2255.39
    assert RI.montar(titulo, devedor, identificador="X",
                     valor_a_pagar_centavos=308203)[
        "titulo"]["valorAPagar"] == 3082.03


# ------------------------------------------------ o endereço


def test_endereco_pela_metade_NAO_vai():
    """**Os quatro campos são obrigatórios juntos**, e a Central recusa o lote
    inteiro por causa de um. Meio endereço não se manda."""
    assert RI._endereco({"endereco": "R", "cep": "", "cidade": "c",
                         "uf": "MA"}) == []
    assert RI._endereco({"endereco": "", "cep": "1", "cidade": "c",
                         "uf": "MA"}) == []


def test_endereco_completo_vai_com_bairro_junto():
    fora = RI._endereco({"endereco": "Rua A, 10", "bairro": "Centro",
                         "cep": "65.920-000", "cidade": "Cidade Exemplo",
                         "uf": "ma"})
    assert fora == [{"endereco": "Rua A, 10, Centro", "cep": "65920000",
                     "cidade": "Cidade Exemplo", "uf": "MA",
                     "origem": RI.ORIGEM_DO_ENDERECO}]


# ------------------------------------------------ quem não vai, e por quê


def test_o_titulo_SUSTADO_nao_vai():
    """**É o caso mais grave.** Mensageria correndo sobre título sustado cobra
    quem o juiz mandou parar — pelo caminho que não passa pelas guardas do
    módulo de protesto."""
    assert "SUSTADO" in RI.SITUACOES_QUE_NAO_VAO


def test_pago_retirado_e_protestado_tambem_nao_vao():
    for situacao in ("PAGO", "RETIRADO", "PROTESTADO"):
        assert situacao in RI.SITUACOES_QUE_NAO_VAO


def test_sem_a_chave_do_cenprot_o_titulo_NAO_vai_e_a_lista_DIZ_por_que(s):
    """Título em situação de ir e sem a chave não vai, e a lista diz por quê.

    (O docstring dizia «medido na produção em 03/09/2026: vazia em 1.366 de
    1.366 — hoje nenhum título pode ser intimado». Envelheceu: medido em
    14/10/2026, 1.261 de 1.409 têm a chave.)"""
    _titulo(s, chave_cenprot="")
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    lista = RI.candidatos(con)
    assert len(lista) == 1
    assert lista[0]["pode_ir"] is False
    assert "chave do CENPROT" in lista[0]["porque_nao"]


def test_com_chave_e_apontado_o_titulo_PODE_ir(s):
    _titulo(s)
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    lista = RI.candidatos(con)
    assert lista[0]["pode_ir"] is True
    assert lista[0]["porque_nao"] == ""


def test_o_quadro_conta_quantos_faltam_por_falta_de_chave(s):
    _titulo(s)
    _titulo(s, chave_cenprot="")
    _titulo(s, chave_cenprot="")
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    q = RI.quantos_podem_ir(con)
    assert q["titulos"] == 3
    assert q["elegiveis"] == 3
    assert q["podem_ir"] == 1
    assert q["sem_chave"] == 2
    assert len(q["sem_chave_lista"]) == 2


# ------------------------------------------------ a chave, medida de verdade
#
# RELATO DO OFICIAL EM 14/10/2026: «diz erroneamente na intimação digital que
# não tem chave da CENPROT». Medido no banco da produção (só leitura): 1.261
# de 1.409 títulos têm a chave; o quadro contava 148 «sem a chave» porque
# somava pagos, desistidos e cancelados — que não vão de jeito nenhum —, e
# entre os que poderiam ir faltavam 11. Os testes abaixo guardam a régua nova.


def test_titulo_que_nao_vai_pela_situacao_nao_conta_como_sem_chave(s):
    _titulo(s)                                            # pode ir
    _titulo(s, situacao="PAGO", chave_cenprot="")
    _titulo(s, situacao="DESISTIDO", chave_cenprot="")
    _titulo(s, situacao="PROTESTADO", chave_cenprot="")
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    q = RI.quantos_podem_ir(con)
    assert q["titulos"] == 4
    assert q["elegiveis"] == 1
    assert q["podem_ir"] == 1
    assert q["sem_chave"] == 0 and q["sem_chave_lista"] == []
    assert q["fora_pela_situacao"] == 3
    for item in RI.candidatos(con):
        if item["situacao"] != "APONTADO":
            assert "chave" not in item["porque_nao"], item["porque_nao"]


def test_a_tela_so_diz_que_falta_chave_quando_falta_e_diz_quais(s):
    _titulo(s)
    _titulo(s, situacao="PAGO", chave_cenprot="")
    html = " ".join(s["c"].get("/protesto/resolve")
                    .get_data(as_text=True).split())
    assert "nenhum — os 1 em situação de ir têm a chave" in html
    assert "Nenhum título pode ir" not in html
    assert "Quais estão sem a chave" not in html
    _titulo(s, numero_titulo="SEMCHAVE/1", protocolo="2604170099",
            chave_cenprot="")
    html = " ".join(s["c"].get("/protesto/resolve")
                    .get_data(as_text=True).split())
    assert "Quais estão sem a chave do CENPROT" in html
    assert "SEMCHAVE/1" in html and "2604170099" in html
    assert "<strong>1</strong> dos 2 em situação de ir" in html


def test_nenhum_pode_ir_por_falta_de_chave_so_quando_e_esse_o_motivo(s):
    _titulo(s, chave_cenprot="")
    html = " ".join(s["c"].get("/protesto/resolve")
                    .get_data(as_text=True).split())
    assert "Nenhum título pode ir, e o motivo é um só" in html


def test_chave_com_tamanho_errado_tem_frase_propria(s):
    _titulo(s, chave_cenprot="123")
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    item = RI.candidatos(con)[0]
    assert item["pode_ir"] is False
    assert "tem 3 dígitos" in item["porque_nao"]


def test_os_que_podem_ir_vem_primeiro_na_lista(s):
    """A lista trazia os 200 mais novos em qualquer situação — na produção,
    150 protestados para 20 que podiam ir."""
    apontado = _titulo(s)
    for _ in range(3):
        _titulo(s, situacao="PROTESTADO")
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    assert RI.candidatos(con, limite=1)[0]["id"] == apontado


# ------------------------------------------------ o identificador


def test_o_identificador_muda_a_cada_tentativa():
    """O mesmo título pode ser intimado de novo, e a Central guarda as duas
    com o mesmo identificador se ele não mudar — a busca por ele devolveria as
    duas sem dizer qual é qual."""
    titulo = {"id": 7, "protocolo": "2604170001"}
    assert RI.identificador_do_titulo(titulo) == "2604170001-1"
    assert RI.identificador_do_titulo(titulo, quantas_ja=2) == "2604170001-3"


def test_sem_protocolo_o_identificador_usa_o_id_e_nao_fica_vazio():
    assert RI.identificador_do_titulo({"id": 9, "protocolo": ""}) == "T9-1"


# ------------------------------------------------ o envio recusa cedo


def test_enviar_sem_marcar_nada_e_erro_de_regra(s):
    with pytest.raises(RI.IntimacaoDigitalError) as erro:
        RI.enviar(s["db"], [])
    assert "marcado" in str(erro.value).lower()


def test_o_corpo_montado_passa_na_conferencia_da_api(s):
    """A ponte e o transporte têm de concordar: o que ela monta, ele aceita."""
    tid = _titulo(s)
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    linha = dict(con.execute(
        """SELECT t.*, d.nome AS devedor_nome,
                  d.documento_numero AS devedor_documento,
                  d.endereco AS d_endereco, d.bairro AS d_bairro,
                  d.cep AS d_cep, d.cidade AS d_cidade, d.uf AS d_uf
             FROM pt_titulos t JOIN pt_devedores d ON d.titulo_id = t.id
            WHERE t.id = ?""", (tid,)).fetchone())
    devedor = {"nome": linha["devedor_nome"],
               "documento_numero": linha["devedor_documento"],
               "endereco": linha["d_endereco"], "bairro": linha["d_bairro"],
               "cep": linha["d_cep"], "cidade": linha["d_cidade"],
               "uf": linha["d_uf"]}
    corpo = RI.montar(linha, devedor, identificador="2604170001-1")
    assert API.conferir_lote([corpo]) == [corpo]


# ------------------------------------------------ a tela


def test_a_tela_abre_e_diz_que_falta_a_credencial(s, sem_chave):
    html = s["c"].get("/protesto/resolve").get_data(as_text=True)
    assert "Intimação Digital" in html
    assert "chave da Resolve ainda não foi informada" in " ".join(html.split())


def test_a_tela_diz_que_isto_NAO_lavra_a_intimacao(s):
    """**A distinção que mais importa nesta tela.** O que a plataforma chama de
    «intimado» é ciência do devedor; a intimação que faz o protesto sair é o
    ato lavrado na ficha."""
    html = " ".join(s["c"].get("/protesto/resolve")
                    .get_data(as_text=True).split())
    assert "não lavra a intimação no livro" in html


def test_a_tela_mostra_o_motivo_de_cada_um_que_nao_pode_ir(s):
    _titulo(s, chave_cenprot="")
    html = " ".join(s["c"].get("/protesto/resolve")
                    .get_data(as_text=True).split())
    assert "falta a chave do CENPROT" in html
    assert "carregue o XML diário" in html


def test_a_tela_avisa_quando_o_ambiente_e_o_de_producao(s):
    html = " ".join(s["c"].get("/protesto/resolve?ambiente=PRODUCAO")
                    .get_data(as_text=True).split())
    assert "ambiente de PRODUÇÃO" in html
    assert "chega ao devedor de verdade" in html


def test_a_tela_so_tem_producao(s):
    """**CONTRATO MUDADO EM 14/10/2026** — ordem do oficial: «tire a opção de
    funcionar na homologação, agora é tudo produção». Este teste se chamava
    `test_o_ambiente_padrao_da_tela_e_homologacao` e cobrava a homologação
    selecionada no seletor. O seletor saiu, e um endereço antigo com
    `?ambiente=TESTES` ou `HOMOLOGACAO` abre a produção."""
    for endereco in ("/protesto/resolve", "/protesto/resolve?ambiente=TESTES",
                     "/protesto/resolve?ambiente=HOMOLOGACAO"):
        html = s["c"].get(endereco).get_data(as_text=True)
        assert '<select name="ambiente"' not in html
        assert 'value="HOMOLOGACAO"' not in html
        assert 'value="TESTES"' not in html
        assert "ambiente de PRODUÇÃO" in " ".join(html.split())


def test_a_tela_esta_no_menu_do_protesto():
    """Tela sem porta no menu é o defeito que mais se repetiu neste projeto."""
    base = (RAIZ / "templates" / "base.html").read_text(encoding="utf-8")
    assert "url_for('protesto_resolve')" in base


def test_enviar_sem_credencial_volta_como_FRASE_e_nao_HTTP_500(s, sem_chave):
    """Erro de regra não é 500 — e foi assim que o teste de tela me pegou na
    CENPROT, em cinco rotas de uma vez."""
    tid = _titulo(s)
    html = s["c"].get("/protesto/resolve").get_data(as_text=True)
    r = s["c"].post("/protesto/resolve/enviar",
                    data={"titulo_id": str(tid), "ambiente": "TESTES",
                          "csrf_token": _token(html)},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "chave da Resolve ainda não foi informada" in " ".join(
        r.get_data(as_text=True).split())


def test_as_quatro_rotas_existem(s):
    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    for rota in ("/protesto/resolve", "/protesto/resolve/enviar",
                 "/protesto/resolve/atualizar", "/protesto/resolve/testar"):
        assert rota in regras


# ------------------------------------------------ a Central é a sexta


def test_a_resolve_e_a_sexta_central_e_tem_so_a_producao_na_tela():
    """Até 13/10/2026: homologação e produção. Desde 14/10, só a produção —
    «agora é tudo produção»."""
    assert CRED.RESOLVE in CRED.ARQUIVO_DA_CENTRAL
    assert CRED.ARQUIVO_DA_CENTRAL[CRED.RESOLVE] == "resolve.cred"
    assert CRED.ambientes_de(CRED.RESOLVE) == (CRED.PRODUCAO,)


def test_toda_central_declarada_tem_arquivo_forma_e_nome():
    """A lista não se escreve em três lugares sem alguém conferir."""
    for central in CRED.ARQUIVO_DA_CENTRAL:
        assert central in CRED.FORMA_DA_CENTRAL
        assert central in CRED.NOME_DA_CENTRAL


# ------------------------------------------------ a ficha


def _intimacao_gravada(s, **troca) -> int:
    """Uma intimação já mandada, como o envio a deixa."""
    tid = _titulo(s)
    # PRODUCAO desde 14/10/2026 (era «TESTES»): a lista mostra só as dela.
    dados = {"titulo_id": tid, "ambiente": "PRODUCAO",
             "lote_id": "68532a2a6e5df1d32d14a971",
             "intimacao_id": "68532a2a6e5df1d32d14a97e",
             "identificador": "2604170001-1",
             "teor": '{"titulo": {"nrChave": "%s"}}' % CHAVE,
             "resumo": "MARCOS COSTA DA SILVA · título 36410/2024",
             "enviada_em": "2026-09-03 10:00:00", "enviada_por": "tabeliao"}
    dados.update(troca)
    con = sqlite3.connect(s["banco"])
    cur = con.execute(
        f"INSERT INTO rs_intimacoes ({', '.join(dados)}) "
        f"VALUES ({', '.join('?' for _ in dados)})", list(dados.values()))
    con.commit()
    con.close()
    return int(cur.lastrowid)


def test_a_ficha_abre_e_mostra_o_que_subiu(s):
    iid = _intimacao_gravada(s)
    html = " ".join(s["c"].get(f"/protesto/resolve/{iid}")
                    .get_data(as_text=True).split())
    assert "2604170001-1" in html
    assert "68532a2a6e5df1d32d14a971" in html          # o lote
    assert CHAVE in html                                # o teor congelado


def test_a_ficha_diz_que_avisar_NAO_lavra_ato(s):
    """A distinção que separa o aviso à Central do ato no livro."""
    iid = _intimacao_gravada(s)
    html = " ".join(s["c"].get(f"/protesto/resolve/{iid}")
                    .get_data(as_text=True).split())
    assert "não lavra ato nenhum" in html
    assert "com selo, custas e lugar no livro" in html


def test_a_lista_leva_a_ficha(s):
    _intimacao_gravada(s)
    # Desde 14/10/2026 a tela é só de produção, e a intimação de exemplo
    # também (era de TESTES, pedida pela URL).
    html = s["c"].get("/protesto/resolve").get_data(as_text=True)
    assert "/protesto/resolve/1" in html


def test_intimacao_de_testes_fica_como_historico_e_nao_se_avisa(s):
    """A que ficou no banco de antes da virada: some da lista, a ficha diz o
    que ela é, e avisar a Central sobre ela é recusado com a frase."""
    iid = _intimacao_gravada(s, ambiente="TESTES")
    lista = s["c"].get("/protesto/resolve").get_data(as_text=True)
    assert f"/protesto/resolve/{iid}" not in lista
    ficha = " ".join(s["c"].get(f"/protesto/resolve/{iid}")
                     .get_data(as_text=True).split())
    assert "guardada só como histórico" in ficha
    with pytest.raises(CRED.CredencialError) as erro:
        RI.avisar(s["db"], iid, "paga")
    assert "só em produção" in str(erro.value)


def test_os_tres_avisos_a_central_estao_declarados():
    """**Cada um existe porque o fato aconteceu AQUI** e a Central não tem como
    saber: o pagamento no balcão, a intimação em mãos, e a baixa do título."""
    assert set(RI.AVISOS_A_CENTRAL) == {"paga", "intimada", "cancelada"}
    for _, (funcao, estado, _) in RI.AVISOS_A_CENTRAL.items():
        assert callable(funcao)
        assert estado in API.ESTADOS


def test_avisar_o_que_nao_existe_e_erro_de_regra(s):
    iid = _intimacao_gravada(s)
    with pytest.raises(RI.IntimacaoDigitalError) as erro:
        RI.avisar(s["db"], iid, "inventado")
    assert "inventado" in str(erro.value)


def test_avisar_sem_numero_na_central_e_recusado(s):
    """Intimação que a Central não aceitou não tem o que avisar — e a frase
    diz isso, em vez de mandar um `null` e receber 404."""
    iid = _intimacao_gravada(s, intimacao_id="")
    with pytest.raises(RI.IntimacaoDigitalError) as erro:
        RI.avisar(s["db"], iid, "paga")
    assert "não chegou a ser aceita" in str(erro.value)


def test_as_rotas_da_ficha_existem(s):
    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    for rota in ("/protesto/resolve/<int:intimacao_id>",
                 "/protesto/resolve/<int:intimacao_id>/historico",
                 "/protesto/resolve/<int:intimacao_id>/pdf",
                 "/protesto/resolve/<int:intimacao_id>/avisar",
                 "/protesto/resolve/lote/<lote_id>/pdfs"):
        assert rota in regras


def test_as_duas_funcoes_sem_uso_no_balcao_foram_APAGADAS():
    """**Função pronta sem tela é a arma que alguém religa** — já aconteceu
    cinco vezes neste projeto. `cancelar_lote` desfaz duas mil de uma vez, e
    `link_de_pagamento` depende de configuração que esta casa não tem.

    Os caminhos ficam declarados, para ninguém os reinventar achando que
    sumiram — é o que se fez com os legados da CENPROT.
    """
    assert not hasattr(API, "cancelar_lote")
    assert not hasattr(API, "link_de_pagamento")
    assert "lote_cancelar" in API.CAMINHO
    assert "link_de_pagamento" in API.CAMINHO


# ------------------------- o que a homologação recusou em 13/10/2026

def _montado(**troca_titulo):
    titulo = {"especie": "DM", "numero_titulo": "1", "chave_cenprot": CHAVE,
              "data_vencimento": "2026-10-09", "valor_centavos": 10000,
              "protocolo": "2604170001", "cedente_nome": "BANCO EXEMPLO S/A",
              "cedente_documento": "45315321000113",
              "apresentante_nome": "BANCO EXEMPLO S/A"}
    titulo.update(troca_titulo)
    devedor = {"nome": "FULANO", "documento_numero": "04243752101",
               "endereco": "Rua A", "cep": "65920000", "cidade": "X", "uf": "MA"}
    return RI.montar(titulo, devedor, identificador="T-1")


def test_tipo_do_documento_so_vai_no_devedor():
    """A Central recusou o lote inteiro: «credor.tipoDocumento — A propriedade
    tipoDocumento não é permitida» (whitelistValidation)."""
    corpo = _montado()
    assert "tipoDocumento" not in corpo["credor"]
    assert corpo["devedor"]["tipoDocumento"] == "CPF"


def test_apresentante_sem_documento_nao_vai_pela_metade():
    """O contrato exige nome E documento no apresentante, e a casa não tem o
    documento dele — ele é opcional no lote: vai inteiro, ou não vai."""
    assert "apresentante" not in _montado()
    com_doc = _montado(apresentante_documento="45315321000113")
    assert com_doc["apresentante"] == {"nome": "BANCO EXEMPLO S/A",
                                       "documento": "45315321000113"}
    API.conferir_lote([_montado()])          # o lote montado passa na conferência


def test_a_conferencia_recusa_pessoa_sem_documento_antes_da_rede():
    corpo = _montado()
    corpo["apresentante"] = {"nome": "SO O NOME"}
    with pytest.raises(API.ResolveError, match="apresentante sem «documento»"):
        API.conferir_lote([corpo])


def test_a_recusa_diz_qual_campo_a_central_apontou():
    """O 400 traz `errors` com o campo; a frase mostrava só «Body inválido»."""
    r = {"status": 400, "texto": "", "json": {
        "message": "Body inválido",
        "errors": [{"target": {"itemIndex": 0}, "property": "credor.tipoDocumento",
                    "constraints": {"whitelistValidation":
                                    "A propriedade tipoDocumento não é permitida."}}]}}
    with pytest.raises(API.ResolveError) as erro:
        API._resposta_ou_erro(r, "criar o lote")
    assert "intimação 1, credor.tipoDocumento" in str(erro.value)
    assert "não é permitida" in str(erro.value)
