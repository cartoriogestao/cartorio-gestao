"""A ficha do cartão de autógrafo, para o cliente assinar.

«Não oferece um cartão de firma gerado para imprimir e dar para o usuário
assinar» — o oficial, em 27/08/2026.

NÃO HÁ PRECEDENTE A IMITAR, e isso foi medido: no E-Ofício a configuração de
etiqueta do cartão de autógrafo está em `0`, e o termo de presença e o livro de
presença estão os dois **desligados** (`tbPropRFirma`). A ficha era preenchida à
mão num formulário pré-impresso comprado pronto.

Sem precedente, o critério foi: **a ficha existe para ser assinada e guardada**,
e tudo o que ela mostra tem de servir a quem depois vai CONFERIR uma assinatura
contra ela.

    três autógrafos      por extenso, abreviado e rubrica — é com a rubrica que
                         se assina folha de escritura, e ela não se parece com a
                         assinatura cheia
    foto e digital       com espaço marcado mesmo sem existirem no sistema: a
                         ficha é assinada NO BALCÃO, com a pessoa presente, e é
                         ali que a digital se colhe
    documento inteiro    esta ficha NÃO deixa a serventia — é contra ela que a
                         firma se confere, e mascarar o CPF do próprio cartão
                         tornaria a conferência impossível
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    c = cg_casa["cliente"]
    cg_casa["db"].create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _cartao(casa, **campos) -> int:
    dados = {"numero": "4063", "nome": "MARIA DAS DORES DA SILVA",
             "nome_norm": "MARIA DAS DORES DA SILVA", "tipo_pessoa": "F",
             "documento": "00000001082", "rg": "0001234", "rg_orgao": "SSP",
             "rg_uf": "MA", "nascimento": "1980-05-12",
             "nacionalidade": "brasileira", "naturalidade": "Cidade Exemplo/MA",
             "estado_civil": "solteira", "profissao": "professora",
             "pai": "JOÃO DA SILVA", "mae": "ANA DA SILVA",
             "endereco": "RUA DAS FLORES", "endereco_numero": "10",
             "bairro": "CENTRO", "cidade": "CIDADE EXEMPLO", "uf": "MA",
             "criado_em": "2026-08-27T10:00:00"}
    dados.update(campos)
    con = sqlite3.connect(casa["banco"])
    with con:
        cur = con.execute(
            f"INSERT INTO nt_cartoes ({','.join(dados)}) "
            f"VALUES ({','.join('?' * len(dados))})", tuple(dados.values()))
    return int(cur.lastrowid)


def _ficha(casa, cartao_id: int) -> str:
    """O texto de dentro do `.odt` — é papel, e não tela."""
    r = casa["cliente"].get(f"/notas/cartoes/{cartao_id}/ficha")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        xml = z.read("content.xml").decode("utf-8")
    return re.sub(r"<[^>]+>", " ", xml)


# ------------------------------------------------------ o que a ficha traz


def test_a_ficha_traz_quem_a_pessoa_e(casa):
    """Quem confere a firma daqui a dez anos lê esta ficha, e mais nada."""
    texto = _ficha(casa, _cartao(casa))
    for esperado in ("MARIA DAS DORES DA SILVA", "00000001082", "0001234",
                     "JOÃO DA SILVA", "ANA DA SILVA", "professora",
                     "RUA DAS FLORES", "CIDADE EXEMPLO"):
        assert esperado in texto, f"a ficha não traz {esperado!r}"


def test_a_ficha_tem_os_tres_autografos(casa):
    """Rubrica não se parece com assinatura cheia, e é ela que assina folha."""
    texto = _ficha(casa, _cartao(casa))
    assert "Assinatura por extenso" in texto
    assert "Assinatura abreviada" in texto
    assert "Rubrica" in texto


def test_a_ficha_tem_espaco_para_foto_e_digital(casa):
    """A ficha é assinada no balcão, com a pessoa presente — é ali que se colhe."""
    texto = _ficha(casa, _cartao(casa))
    assert "Fotografia" in texto
    assert "Impressão digital" in texto


def test_a_ficha_nao_mascara_o_documento(casa):
    """Ela não deixa a serventia: é contra ela que a firma se confere.

    A regra da máscara vale para papel que SAI. Mascarar o CPF do próprio
    cartão de autógrafo tornaria a conferência impossível.
    """
    texto = _ficha(casa, _cartao(casa))
    assert "00000001082" in texto
    assert "***" not in texto


def test_so_o_cliente_assina_a_ficha(casa):
    """MUDOU EM 31/08/2026, POR ORDEM DO OFICIAL: «o oficial nao assina a
    ficha de assinatura, so o cliente».

    ESTE TESTE AFIRMAVA O CONTRARIO, e chamava-se «a ficha leva a assinatura
    de quem atendeu». A assinatura do escrevente estava no papel desde antes,
    e nao veio do meu engano do relato #27 — mas «so o cliente» alcanca as
    duas, a dele e a do delegatario.

    O cartao de autografo e o padrao de assinatura DA PESSOA: quem assina um
    padrao de comparacao e quem esta sendo padronizado. A serventia colhe; a
    fe dela aparece no reconhecimento, que e outro papel.
    """
    texto = _ficha(casa, _cartao(casa))
    assert "MARIO EXEMPLO DOS SANTOS" not in texto
    assert "o titular do cartão" in texto


# --------------------------------------- o que só aparece quando é o caso


def test_solteiro_nao_ganha_linha_de_conjuge(casa):
    """Linha vazia é ruído, e é ruído em papel que se lê por anos."""
    assert "Cônjuge" not in _ficha(casa, _cartao(casa))


def test_casado_ganha(casa):
    texto = _ficha(casa, _cartao(casa, estado_civil="casada",
                                 conjuge="PEDRO DA SILVA"))
    assert "Cônjuge" in texto and "PEDRO DA SILVA" in texto


def test_a_restricao_do_cartao_vem_em_destaque(casa):
    """Quem imprime a ficha tem de ver a restrição antes de reconhecer."""
    texto = _ficha(casa, _cartao(casa, somente_autenticidade=1))
    assert "SÓ ADMITE RECONHECIMENTO POR AUTENTICIDADE" in texto


def test_cartao_bloqueado_diz_o_motivo(casa):
    texto = _ficha(casa, _cartao(casa, bloqueado=1,
                                 motivo_bloqueio="Ordem judicial de 12/08"))
    assert "CARTÃO BLOQUEADO" in texto
    assert "Ordem judicial de 12/08" in texto


# ------------------------------------------------------------- os caminhos


def test_a_ficha_do_cartao_e_oferecida_na_tela_dele(casa):
    cid = _cartao(casa)
    html = casa["cliente"].get(f"/notas/cartoes/{cid}").get_data(as_text=True)
    assert f"/notas/cartoes/{cid}/ficha" in html


def test_cartao_que_nao_existe_da_404(casa):
    assert casa["cliente"].get("/notas/cartoes/99999/ficha").status_code == 404


def test_a_ficha_sai_como_documento_e_nao_como_pagina(casa):
    """É papel que fica guardado e volta a ser consultado por anos."""
    r = casa["cliente"].get(f"/notas/cartoes/{_cartao(casa)}/ficha")
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    assert "cartao-autografo-4063.odt" in r.headers["Content-Disposition"]


# ------------------------------------------------------------- selo na ficha


def test_ficha_com_selo_de_abertura_imprime_o_numero(casa):
    """Pedido 07/09/2026: a ficha sai com o selo emitido no anverso."""
    import sqlite3
    cid = _cartao(casa, selo_abertura="RECFIR000000TESTESELO000001")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO sd_selos
               (numero, texto, caminho, atribuicao, referencia, tabela, ato_id,
                obtido_em, usado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("RECFIR000000TESTESELO000001",
             "Poder Judiciário — TJMA. Selo: RECFIR000000TESTESELO000001, "
             "07/09/2026 15:00:00, Ato: 13.17.1, Parte(s): MARIA DAS DORES DA SILVA, "
             "Total R$ 13,37 Emol R$ 11,93 FERC R$ 0,36 FADEP R$ 0,48 FEMP R$ 0,48 "
             "FERRFIS R$ 0,12 Consulte em https://selo.tjma.jus.br",
             "/selo/notas/cartao-assinatura", "NOTAS",
             f"nt_cartoes:{cid}:13.17.1:1", "nt_cartoes", cid,
             "2026-09-07T15:00:00", "2026-09-07T15:00:00"))
    texto = _ficha(casa, cid)
    # O RÓTULO VEM DENTRO DO CARIMBO, EM CAIXA ALTA, desde 15/09/2026 — ordem
    # dele, para o carimbo ser o mesmo em todos os papéis da casa. Antes havia
    # um parágrafo «Selo de abertura» em cima do quadro, e ele saiu: dois
    # rótulos para o mesmo carimbo é ruído num papel assinado.
    assert "SELO DE ABERTURA" in texto
    assert "RECFIR000000TESTESELO000001" in texto
    assert "13.17.1" in texto or "Total R$" in texto


def test_ficha_sem_selo_avisa(casa):
    texto = _ficha(casa, _cartao(casa))
    assert "SEM SELO DE ABERTURA" in texto


def _odt_zip(casa, cartao_id: int):
    r = casa["cliente"].get(f"/notas/cartoes/{cartao_id}/ficha")
    assert r.status_code == 200
    return zipfile.ZipFile(io.BytesIO(r.get_data()))


def test_ficha_com_selo_traz_qr_no_odt(casa):
    """Mesmo padrao da etiqueta: QR PNG embutido no .odt (07/09/2026)."""
    cid = _cartao(casa, selo_abertura="RECFIR000000TESTESELO000002")
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute(
            """INSERT INTO sd_selos
               (numero, texto, caminho, atribuicao, referencia, tabela, ato_id,
                obtido_em, usado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            ("RECFIR000000TESTESELO000002",
             "Poder Judiciário — TJMA. Selo: RECFIR000000TESTESELO000002, "
             "07/09/2026 15:00:00, Ato: 13.17.1, Parte(s): MARIA DAS DORES DA SILVA, "
             "Total R$ 13,37 Emol R$ 11,93 FERC R$ 0,36 FADEP R$ 0,48 FEMP R$ 0,48 "
             "FERRFIS R$ 0,12 Consulte em https://selo.tjma.jus.br",
             "/selo/notas/cartao-assinatura", "NOTAS",
             f"nt_cartoes:{cid}:13.17.1:1", "nt_cartoes", cid,
             "2026-09-07T15:00:00", "2026-09-07T15:00:00"))
    with _odt_zip(casa, cid) as z:
        nomes = z.namelist()
        assert "Pictures/qr_abertura.png" in nomes, nomes
        png = z.read("Pictures/qr_abertura.png")
        assert png[:8] == b"\x89PNG\r\n\x1a\n"
        xml = z.read("content.xml").decode("utf-8")
    assert "qr_abertura.png" in xml
    # Em caixa alta, e dentro do carimbo — ver o teste do número, acima.
    assert "SELO DE ABERTURA" in re.sub(r"<[^>]+>", " ", xml)


# --------------------------------------------- hibrido com Modelos da casa


def test_o_papel_esta_no_catalogo_de_notas():
    """O piso do texto editavel e o MODELO_CARTAO_FICHA — nao o HTML montado."""
    import modelos_da_casa as MOD
    import notas_web as NW

    assert "NOTAS_CARTAO_FICHA" in MOD.POR_CHAVE
    c = MOD.POR_CHAVE["NOTAS_CARTAO_FICHA"]
    assert c["atribuicao"] == "Tabelionato de Notas"
    assert c["nome"] == "Cartão de autógrafo"
    assert MOD.padrao_de("NOTAS_CARTAO_FICHA") == NW.MODELO_CARTAO_FICHA
    assert "CARTÃO DE AUTÓGRAFO" in NW.MODELO_CARTAO_FICHA
    assert "Autógrafos" in NW.MODELO_CARTAO_FICHA
    assert "o titular do cartão" in NW.MODELO_CARTAO_FICHA
    # Estrutura/media nao vai no modelo como HTML ja preenchido
    assert "@@SELO@@" in NW.MODELO_CARTAO_FICHA
    assert "{{ espaco }}" in NW.MODELO_CARTAO_FICHA
    assert "{{ linha }}" in NW.MODELO_CARTAO_FICHA
    assert "{{ caixa_foto_digital_celulas }}" in NW.MODELO_CARTAO_FICHA
    assert "Fotografia" in NW.MODELO_CARTAO_FICHA


def test_ajuste_do_modelo_aparece_na_ficha(casa):
    """Sem isso o oficial edita na tela e a ficha ignora — o defeito classico."""
    import modelos_da_casa as MOD

    cid = _cartao(casa)
    con = sqlite3.connect(casa["banco"])
    with con:
        MOD.salvar(con, "NOTAS_CARTAO_FICHA",
                   corpo=MOD.padrao_de("NOTAS_CARTAO_FICHA").replace(
                       "o titular do cartão",
                       "o titular do cartão — TEXTO DA CASA"),
                   quem="mario", agora="2026-09-07T16:00")
    texto = _ficha(casa, cid)
    assert "TEXTO DA CASA" in texto
