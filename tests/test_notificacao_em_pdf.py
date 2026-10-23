"""AS NOTIFICAÇÕES SAEM EM ARQUIVO — usucapião e georreferenciamento.

    «faça ser possível imprimir as notificações da usucapião e da
     georreferenciamento em pdf»            — o oficial, 21/09/2026

E ELE VEIO DEPOIS DO RELATO #88, do mesmo dia, por Beatriz:

    «NÃO ESTOU CONSEGUINDO GERAR IMPRIMIR AS NOTIFICAÇÕES DA UNIÃO, ESTADO E
     MUNICIPIO. APARECE QUE GEROU PORÉM NÃO CONSIGO ACESSAR»

**O QUE A MEDIÇÃO MOSTROU, na base do balcão:** os três ofícios de ciência
estavam gravados — movimentos 7, 8 e 9 do processo 2026.07.194, criados às
14h05:52, com teor de 682, 683 e 686 caracteres. Nada falhou ao gerar. O que
não existia era **arquivo**: o papel era uma página do navegador com um botão
chamando a caixa de impressão dele — e quem trabalha por acesso remoto clica
ali e a caixa abre na outra máquina.

**E NA RETIFICAÇÃO NÃO HAVIA NEM A PÁGINA.** O módulo registrava *que*
notificou — `notificado_em`, `forma`, `prazo_ate` — e o texto entregue ao
confrontante era escrito fora do sistema. Registro de notificação sem o papel
que a sustenta é uma linha dizendo que a serventia notificou alguém, sem prova
do que foi dito.
"""
from __future__ import annotations

import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import retificacao as RT
import rt_notificacao as NOTIF
import rt_tjma as NORMA

SENHA = "Senha#12345"
AGORA = "2026-09-21T15:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _processo_com_confrontante(casa, *, endereco="Fazenda Vizinha, zona rural",
                               documento=None, matricula_contigua=None,
                               serventia_contigua=None):
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO ri_matriculas (numero, livro, situacao, criado_em)
               VALUES ('3247', '2', 'ATIVA', ?)""", (AGORA,))
        mid = int(cur.lastrowid)
        pid = RT.autuar(
            con, numero="9/2026", especie=NORMA.GEORREFERENCIADA,
            fundamento=NORMA.A_REQUERIMENTO, matricula_id=mid, rural=True,
            agora=AGORA, usuario="mario", ano=2026,
            requerente_nome="ANTONIO JARDINEIRO PEREIRA",
            area_na_matricula="30,7770 ha", area_pretendida="31,1000 ha",
            profissional_nome="ENG. BELTRANO",
            profissional_conselho="CREA-MA", art_numero="MA2026/1")
        #  `divisa_afetada` E A MARCA DO ART. 596, 0 OU 1, e nao a descricao da
        #  divisa (medido em 19/10/2026): `retificacao.anotar_confrontante`
        #  grava `1 if divisa_afetada else 0`, e o banco migrado da producao
        #  tem a coluna como `bigint`. O SQLite guardava o texto 'divisa oeste'
        #  na coluna inteira; o PostgreSQL o recusa, e a producao nunca o grava.
        cur = con.execute(
            """INSERT INTO rt_confrontantes (processo_id, papel, nome,
                   nome_norm, documento, endereco, matricula_contigua,
                   serventia_contigua, divisa_afetada, criado_em)
               VALUES (?, 'CONFRONTANTE', 'SICRANO DA SILVA', 'sicrano da silva',
                       ?, ?, ?, ?, 1, ?)""",
            (pid, documento, endereco, matricula_contigua, serventia_contigua,
             AGORA))
        cid = int(cur.lastrowid)
    return pid, cid


# ==================================================== o papel, como texto


def test_o_papel_anuncia_o_prazo_o_silencio_e_a_impugnacao_atrasada():
    """AS TRÊS COISAS QUE A NORMA MANDA DIZER, e cada uma com o artigo.

    O silêncio é a mais importante: **quem não responde precisa saber, antes,
    o que o seu silêncio vale** (art. 599, § 1º). E a impugnação fora do prazo
    ainda entra até a averbação (§ 3º) — calar isso faria o papel afirmar um
    prazo mais duro que o da norma.
    """
    teor = NOTIF.montar(
        processo={"numero": "9/2026", "ano": 2026,
                  "requerente_nome": "ANTONIO JARDINEIRO PEREIRA",
                  "matricula_numero": "3.247"},
        confrontante={"nome": "SICRANO DA SILVA", "endereco": "Fazenda Vizinha",
                      "papel": "Confrontante"},
        serventia={"nome": "OFÍCIO ÚNICO", "oficial": "MARIO", "cargo": "Oficial"},
        hoje_extenso="Cidade Exemplo-MA, 21 de setembro de 2026")
    assert "15 (quinze) dias úteis" in teor
    assert "art. 599" in teor
    assert "presumida a anuência" in teor
    assert "art. 599, § 1º" in teor
    assert "antes da averbação" in teor
    assert "art. 599, § 3º" in teor
    assert "RECIBO" in teor, (
        "o recibo vai na mesma folha — recibo em folha separada é o recibo "
        "que se perde")
    assert "SICRANO DA SILVA" in teor
    assert "ANTONIO JARDINEIRO PEREIRA" in teor


def test_o_prazo_do_papel_e_lido_da_norma_e_nao_escrito():
    """Duas cópias de um prazo divergem no dia em que a norma mudar."""
    assert NOTIF.prazo_para_impugnar() == NORMA.prazo("IMPUGNAR")
    assert NOTIF.prazo_para_impugnar()["dias"] == 15


# ================================================ a divisa, depois dos dois-pontos

DIVISA = "Divisa que toca o imóvel de V. S.ª: "
EXEMPLO = ("Divisa que toca o imóvel de V. S.ª: FULANO DE TAL, CPF "
           "000.000.000-00, imóvel da matrícula n.º 1.234 do Registro de "
           "Imóveis de Cidade Exemplo")


def _teor(**confrontante) -> str:
    return NOTIF.montar(
        processo={"numero": "9/2026", "ano": 2026,
                  "requerente_nome": "ANTONIO JARDINEIRO PEREIRA",
                  "matricula_numero": "3.247"},
        confrontante={"nome": "FULANO DE TAL", "endereco": "Rua Exemplo, 10",
                      "papel": "Confrontante", **confrontante},
        serventia={"nome": "OFÍCIO ÚNICO", "oficial": "MARIO",
                   "cargo": "Oficial"},
        hoje_extenso="Cidade Exemplo-MA, 19 de outubro de 2026")


def _linha_da_divisa(teor: str) -> str | None:
    linhas = [x for x in teor.splitlines() if x.startswith(DIVISA)]
    assert len(linhas) <= 1, "a divisa sai numa linha só"
    return linhas[0] if linhas else None


@pytest.mark.parametrize("marca", [1, True])
def test_a_divisa_traz_quem_e_o_confrontante_e_nunca_o_numero_um(marca):
    """O PAPEL DIZIA «Divisa que toca o imóvel de V. S.ª: 1».

    `divisa_afetada` é a marca SIM/NÃO do art. 596 (INTEGER 0/1 em
    `rt_schema`), e a linha copiava a marca. A frase fica — é o padrão das
    intimações —, e depois dos dois-pontos vêm os dados do confrontante.
    """
    for extra in ({}, {"documento": "00000000000"},
                  {"matricula_contigua": "1.234"},
                  {"documento": "00000000000", "matricula_contigua": "1.234",
                   "serventia_contigua": "Registro de Imóveis de Cidade Exemplo"}):
        teor = _teor(divisa_afetada=marca, **extra)
        assert "V. S.ª: 1" not in teor, extra
        assert "V. S.ª: True" not in teor, extra
        assert _linha_da_divisa(teor).startswith(DIVISA + "FULANO DE TAL"), extra


def test_com_nome_documento_e_matricula_sai_a_linha_do_exemplo():
    """O exemplo do oficial, letra por letra — o CPF formatado como o resto do
    sistema formata (`cpf_cnpj.formatar_documento`)."""
    teor = _teor(divisa_afetada=1, documento="00000000000",
                 matricula_contigua="1.234",
                 serventia_contigua="Registro de Imóveis de Cidade Exemplo")
    assert _linha_da_divisa(teor) == EXEMPLO


def test_a_matricula_contigua_nao_sai_duas_vezes():
    """Com a divisa, a matrícula já entrou na linha dela; a linha «Imóvel
    contíguo de V. S.ª» a repetiria."""
    teor = _teor(divisa_afetada=1, documento="00000000000",
                 matricula_contigua="1.234",
                 serventia_contigua="Registro de Imóveis de Cidade Exemplo")
    assert teor.count("1.234") == 1
    assert "Imóvel contíguo de V. S.ª" not in teor


def test_sem_divisa_afetada_a_matricula_sai_na_linha_de_sempre():
    """Sem a marca do art. 596 não há linha da divisa — e a matrícula contígua
    continua saindo, uma vez, onde sempre saiu."""
    teor = _teor(divisa_afetada=0, matricula_contigua="1.234")
    assert _linha_da_divisa(teor) is None
    assert "Imóvel contíguo de V. S.ª: matrícula 1.234" in teor
    assert teor.count("1.234") == 1


def test_so_entra_o_que_existe_e_nao_sobra_virgula():
    """Cada dado ausente some com a vírgula dele."""
    assert _linha_da_divisa(_teor(divisa_afetada=1)) == DIVISA + "FULANO DE TAL"
    assert _linha_da_divisa(_teor(
        divisa_afetada=1, matricula_contigua="1.234")) == (
        DIVISA + "FULANO DE TAL, imóvel da matrícula n.º 1.234")
    assert _linha_da_divisa(_teor(
        divisa_afetada=1, documento="00000000000000")) == (
        DIVISA + "FULANO DE TAL, CNPJ 00.000.000/0000-00")
    for teor in (_teor(divisa_afetada=1), _teor(divisa_afetada=1,
                                                 documento="  ")):
        assert ", ," not in teor and not _linha_da_divisa(teor).endswith(",")


def test_o_documento_sem_tamanho_de_cpf_nem_de_cnpj_nao_vira_cpf():
    """O campo da tela é «Documento», livre: o papel não chama de CPF o que
    não tem 11 dígitos."""
    linha = _linha_da_divisa(_teor(divisa_afetada=1, documento="RG 1234567"))
    assert linha == DIVISA + "FULANO DE TAL, documento RG 1234567"


def test_o_endereco_nao_entra_na_divisa():
    """Art. 598, § 1º: o endereço pode ser a residência dele, e não o imóvel
    que faz a divisa."""
    teor = _teor(divisa_afetada=1, endereco="Rua Exemplo, 10",
                 matricula_contigua="1.234")
    assert "Rua Exemplo" not in _linha_da_divisa(teor)


def test_a_serventia_sozinha_nao_entra_na_divisa():
    """«do Registro de Imóveis de …» diz onde a matrícula está; sem a
    matrícula, depois de uma vírgula, não diz qual imóvel é."""
    teor = _teor(divisa_afetada=1,
                 serventia_contigua="Registro de Imóveis de Cidade Exemplo")
    assert _linha_da_divisa(teor) == DIVISA + "FULANO DE TAL"


def test_sem_dado_nenhum_alem_da_marca_a_linha_nao_sai():
    """O `montar` não deixa sair papel sem nome; a linha, sozinha, também não
    sai com os dois-pontos e nada depois."""
    assert NOTIF._quem_faz_a_divisa({"divisa_afetada": 1}) == ""
    assert NOTIF._quem_faz_a_divisa(
        {"divisa_afetada": 1, "endereco": "Rua Exemplo, 10",
         "serventia_contigua": "Registro de Imóveis de Cidade Exemplo"}) == ""


def test_sem_endereco_o_papel_nao_sai_e_a_recusa_diz_o_artigo():
    """A CONFERÊNCIA VEM ANTES DE O MOVIMENTO EXISTIR: notificação registrada
    sem papel consome o prazo de alguém que não foi avisado."""
    faltas = NOTIF.conferir(
        processo={"numero": "9/2026", "requerente_nome": "FULANO"},
        confrontante={"nome": "SICRANO"})
    assert any("endereço" in f for f in faltas)
    assert any("art. 598, § 1º" in f for f in faltas)
    with pytest.raises(NOTIF.NotificacaoError):
        NOTIF.montar(processo={"numero": "9/2026",
                               "requerente_nome": "FULANO"},
                     confrontante={"nome": "SICRANO"},
                     serventia={"nome": "X"})


def test_este_modulo_nao_pratica_ato():
    """Ele monta o texto e mais nada — a mesma régua das fraudes, do CNIB e da
    minuta do RI."""
    proibidos = ("notificar", "lavrar", "registrar", "averbar", "decidir",
                 "gravar", "salvar")
    for nome in dir(NOTIF):
        if nome.startswith("_"):
            continue
        assert not any(nome.lower().startswith(p) for p in proibidos), (
            f"`rt_notificacao.{nome}` tem cara de praticar ato")


# ==================================================== o ciclo, pela tela


def test_notificar_congela_o_teor_e_a_linha_oferece_o_pdf(casa):
    pid, cid = _processo_com_confrontante(casa)
    tela = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    assert "imprimir em PDF" not in tela, (
        "antes de notificar não há papel — oferecer o que a rota recusa é o "
        "defeito do problema #90 pelo outro lado")

    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/notificar",
        data={"csrf_token": _token(tela), "confrontante_id": str(cid),
              "forma": "CORREIO", "quando": "2026-09-21",
              "prazo_ate": "2026-10-13"},
        follow_redirects=True)
    assert r.status_code == 200

    linha = _con(casa).execute(
        "SELECT * FROM rt_confrontantes WHERE id = ?", (cid,)).fetchone()
    assert linha["notificado_em"] == "2026-09-21"
    assert linha["teor_expedido"], "o papel tem de ficar congelado no registro"
    assert "presumida a anuência" in linha["teor_expedido"]
    #  QUEM ASSINA É O TITULAR DA SERVENTIA, e não quem clicou: o papel sai
    #  com o que está no cadastro da casa, e é por isso que ele não se escreve
    #  dentro do modelo — o cabeçalho que o E-Ofício guardava traz a oficial
    #  ANTERIOR. Sem cadastro, sai a linha em branco para assinar à mão.
    assert "____________" in linha["teor_expedido"] or "Oficial" in (
        linha["teor_expedido"])
    assert "9/2026/2026" not in linha["teor_expedido"], (
        "o número desta seção já traz o ano — repeti-lo daria «9/2026/2026»")

    tela = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    assert "imprimir em PDF" in tela

    papel = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}/notificacao/{cid}?formato=odt")
    assert papel.status_code == 200
    assert papel.data[:2] == b"PK", "o .odt é um pacote zip"
    assert "opendocument" in papel.headers.get("Content-Type", "")


def _notificar_pela_tela(casa, pid, cid):
    tela = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/notificar",
        data={"csrf_token": _token(tela), "confrontante_id": str(cid),
              "forma": "CORREIO", "quando": "2026-09-21",
              "prazo_ate": "2026-10-13"},
        follow_redirects=True)
    assert r.status_code == 200
    return _con(casa).execute(
        "SELECT teor_expedido FROM rt_confrontantes WHERE id = ?",
        (cid,)).fetchone()["teor_expedido"]


def test_o_papel_expedido_pela_tela_traz_os_dados_do_confrontante_na_divisa(casa):
    """O CAMINHO DE VERDADE: a linha lida do banco (`divisa_afetada` inteiro,
    como a produção migrada guarda) até o teor congelado."""
    pid, cid = _processo_com_confrontante(
        casa, documento="00000000000", matricula_contigua="1.234",
        serventia_contigua="Registro de Imóveis de Cidade Exemplo")
    teor = _notificar_pela_tela(casa, pid, cid)
    assert teor, "o papel tem de ficar congelado no registro"
    assert "V. S.ª: 1" not in teor
    assert EXEMPLO.replace("FULANO DE TAL", "SICRANO DA SILVA") in (
        teor.splitlines())
    assert teor.count("1.234") == 1


def test_a_notificacao_ja_expedida_sai_como_foi_entregue(casa):
    """O TEXTO EXPEDIDO É CONGELADO — inclusive o «V. S.ª: 1» de antes do
    conserto. Consertar o modelo não reescreve o que o confrontante leu, e o
    papel de quem já foi notificado sai com o teor de então."""
    pid, cid = _processo_com_confrontante(casa, matricula_contigua="1.234")
    antigo = ("NOTIFICAÇÃO — RETIFICAÇÃO DE ÁREA\n"
              "Divisa que toca o imóvel de V. S.ª: 1\n"
              "Imóvel contíguo de V. S.ª: matrícula 1.234\n")
    con = _con(casa)
    with con:
        con.execute(
            """UPDATE rt_confrontantes SET notificado_em = '2026-09-21',
                   forma = 'CORREIO', prazo_ate = '2026-10-13',
                   teor_expedido = ?
                WHERE id = ?""", (antigo, cid))
    papel = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}/notificacao/{cid}?formato=odt")
    assert papel.status_code == 200
    conteudo = zipfile.ZipFile(io.BytesIO(papel.data)).read(
        "content.xml").decode("utf-8")
    assert "Divisa que toca o imóvel de V. S.ª: 1" in conteudo
    assert "SICRANO DA SILVA, imóvel da matrícula" not in conteudo
    linha = _con(casa).execute(
        "SELECT teor_expedido FROM rt_confrontantes WHERE id = ?",
        (cid,)).fetchone()
    assert linha["teor_expedido"] == antigo


def test_sem_teor_o_papel_recusa_em_vez_de_remontar(casa):
    """O que sairia agora não é o que foi entregue — mesma regra do termo do
    Registro Civil e da certidão do Protesto."""
    pid, cid = _processo_com_confrontante(casa)
    con = _con(casa)
    with con:
        con.execute(
            """UPDATE rt_confrontantes SET notificado_em='2026-01-05',
                   forma='CORREIO', prazo_ate='2026-01-30'
                WHERE id=?""", (cid,))
    r = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}/notificacao/{cid}",
        follow_redirects=True)
    assert r.status_code == 200
    assert "não guardou o teor" in r.get_data(as_text=True)


def test_sem_endereco_a_tela_recusa_antes_de_registrar(casa):
    """Nada é gravado: a notificação não fica registrada sem o papel."""
    pid, cid = _processo_com_confrontante(casa, endereco="")
    tela = casa["cliente"].get(
        f"/registro-imoveis/retificacoes/{pid}").get_data(as_text=True)
    r = casa["cliente"].post(
        f"/registro-imoveis/retificacoes/{pid}/notificar",
        data={"csrf_token": _token(tela), "confrontante_id": str(cid),
              "forma": "CORREIO", "quando": "2026-09-21",
              "prazo_ate": "2026-10-13"},
        follow_redirects=True)
    assert "endereço" in r.get_data(as_text=True)
    linha = _con(casa).execute(
        "SELECT notificado_em FROM rt_confrontantes WHERE id=?",
        (cid,)).fetchone()
    assert linha["notificado_em"] is None, (
        "notificação registrada sem papel consome o prazo de quem não foi "
        "avisado")


# ============================================ o papel da usucapião, em arquivo


def test_a_notificacao_da_usucapiao_sai_em_arquivo(casa):
    """RELATO #88: «aparece que gerou porém não consigo acessar».

    Os três ofícios de ciência estavam gravados, com teor. O que não existia
    era **arquivo** — o papel era uma página do navegador, e o botão
    «Imprimir» chama a caixa de impressão DELE: quem trabalha por acesso
    remoto clica ali e a caixa abre na outra máquina.
    """
    import usucapiao as US
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    pid = US.autuar(con, numero="88", modalidade="ORDINARIA",
                    agora=AGORA, requerente_nome="JOÃO BATISTA DE SOUSA",
                    imovel_descricao="Terreno urbano de 12m por 30m",
                    imovel_municipio="Cidade Exemplo", usuario="mario")
    con.commit()
    r = US.dar_ciencia_aos_entes(
        con, pid, agora=AGORA,
        serventia={"nome": "OFÍCIO ÚNICO", "oficial": "MARIO",
                   "cargo": "Oficial"},
        hoje_extenso="Cidade Exemplo-MA, 21 de setembro de 2026",
        usuario="mario")
    con.commit()
    movimentos = [x["movimento_id"] for x in r]
    con.close()
    assert len(movimentos) == 3, "são três entes, e os três se avisam"

    ficha = casa["cliente"].get(f"/usucapiao/{pid}").get_data(as_text=True)
    assert ficha.count("Imprimir em PDF") == 3
    assert "ver na tela" in ficha, (
        "a tela não some — ela é a leitura rápida; o arquivo é o que se leva")

    for mid in movimentos:
        papel = casa["cliente"].get(
            f"/usucapiao/{pid}/notificacao/{mid}/papel?formato=odt")
        assert papel.status_code == 200
        assert papel.data[:2] == b"PK"
        assert "opendocument" in papel.headers.get("Content-Type", "")


def test_movimento_sem_teor_nao_vira_papel(casa):
    """O papel não se remonta: o que sairia agora não é o que foi entregue."""
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    with con:
        cur = con.execute(
            """INSERT INTO us_processos (numero, modalidade, etapa, situacao,
                   requerente_nome, criado_em, criado_por)
               VALUES ('89', 'ORDINARIA', 'AUTUACAO', 'EM_ANDAMENTO',
                       'FULANO', ?, 'mario')""", (AGORA,))
        pid = int(cur.lastrowid)
        cur = con.execute(
            """INSERT INTO us_movimentos (processo_id, tipo, etapa, descricao,
                   data_movimento, criado_em, criado_por)
               VALUES (?, 'CIENCIA', 'CIENCIA_ENTES', 'sem teor', ?, ?, 'mario')""",
            (pid, AGORA, AGORA))
        mid = int(cur.lastrowid)
    con.close()
    r = casa["cliente"].get(f"/usucapiao/{pid}/notificacao/{mid}/papel",
                            follow_redirects=True)
    assert r.status_code == 200
    assert "não guardou o teor" in r.get_data(as_text=True)
