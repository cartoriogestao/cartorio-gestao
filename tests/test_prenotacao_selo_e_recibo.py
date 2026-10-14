"""A prenotação do RI: livro de destino, selo e comprovante.

Pedidos do oficial em 27/08/2026, pela janela da ajuda:

  «Na prenotação do RI poderia colocar o livro apenas com duas opções: Livro 2
   ou 3 … em vez de campo livre.»

  «Quando um título é prenotado no RI, devemos emitir um recibo de protocolo ao
   cliente, com prazo da prenotação e outras informações importantes… A
   prenotação do RI é cobrada e deve emitir selo.»

O QUE A MEDIÇÃO MUDOU NO PRIMEIRO PEDIDO
    `ri_protocolos.livro` **não é** o livro de destino: é o Livro 1-A de
    Protocolo, e está `1A` em **783 dos 784** registros. A única linha com `2`
    é alguém tendo digitado no campo livre — o defeito que ele apontou. O selo
    confirma: `livro: "1A"` em **829 de 829**.

    São duas coisas diferentes, e agora têm dois campos: o de protocolo, que
    não se escolhe, e o de destino, que se escolhe entre dois.

E NO SEGUNDO, A MEDIÇÃO EVITOU UM SEGUNDO DOCUMENTO
    O comprovante de prenotação já existia, com máscara de CPF e prazo. Criar
    um «recibo» ao lado dele daria dois papéis para a mesma coisa. O que
    faltava era o conteúdo — e um defeito: o prazo era constante.
"""
from __future__ import annotations

import glob
import io
import re
import sqlite3
import sys
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
    cg_casa["db"].create_user("jean", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "jean", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _prenotar(casa, **extra):
    html = casa["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    dados = {"apresentante": "MARIA DA SILVA",
             "apresentante_documento": "00000001082",
             "natureza_titulo": "COMPRA E VENDA",
             "livro_destino": "2", "csrf_token": _token(html),
             # 10/10/2026: telefone OU e-mail obrigatório ao prenotar
             # (ordem do oficial; contato_do_cliente.py).
             "telefone": "(99) 98888-7777"}
    dados.update(extra)
    return casa["cliente"].post("/registro-imoveis/protocolo", data=dados,
                                follow_redirects=True)


def _ultimo(casa):
    return _con(casa).execute(
        "SELECT * FROM ri_protocolos ORDER BY id DESC LIMIT 1").fetchone()


# --------------------------------------------------- o livro, agora com dois


def test_a_tela_oferece_apenas_livro_2_ou_3(casa):
    html = casa["cliente"].get("/registro-imoveis/protocolo").get_data(as_text=True)
    assert 'name="livro_destino"' in html
    assert "Livro 2" in html and "Livro 3" in html
    # E o campo livre do livro de protocolo saiu da tela.
    assert 'name="livro"' not in html


def test_o_livro_de_protocolo_e_sempre_1a(casa):
    """Ele não se escolhe: 783 dos 784 registros do acervo dizem 1A."""
    _prenotar(casa, livro_destino="3")
    p = _ultimo(casa)
    assert p["livro"] == "1A"
    assert p["livro_destino"] == "3"


def test_prenotar_sem_dizer_o_destino_e_recusado(casa):
    html = _prenotar(casa, livro_destino="").get_data(as_text=True)
    assert "Livro 2" in html and "Livro 3" in html
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM ri_protocolos").fetchone()["n"] == 0


def test_destino_inventado_nao_entra(casa):
    """Caixa de seleção não impede POST forjado; quem recusa é a rota."""
    _prenotar(casa, livro_destino="7")
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM ri_protocolos").fetchone()["n"] == 0


# ------------------------------------------------------------------- o selo


def test_a_prenotacao_continua_de_pe_sem_o_selador(casa):
    """Prenotação desfeita por causa de selo é pior que prenotação sem selo.

    Ela é o que garante a prioridade do título, e a prioridade se conta da
    hora em que ele entrou.
    """
    r = _prenotar(casa)
    assert r.status_code == 200
    assert _con(casa).execute(
        "SELECT COUNT(*) n FROM ri_protocolos").fetchone()["n"] == 1
    assert "SEM SELO" in r.get_data(as_text=True)


def test_o_envelope_da_prenotacao_tem_os_valores_medidos():
    """Cada valor tem a sua contagem nos 829 envelopes do acervo."""
    import ato_selado as AS
    e = AS.envelope_da_prenotacao(
        protocolo="11150", escrevente="JEAN", versao_tabela="0220260101",
        descricao_natureza="compra e venda",
        partes=[{"nome": "MARIA", "documento": "000.000.010-82"}])
    assert list(e) == ["protocolo", "dadosSelo"]
    d = e["dadosSelo"]
    assert d["livro"] == "1A"                    # 829/829
    assert d["naturezaTitulo"] == 126.0          # 829/829
    assert d["folha"] == 0                       # 773/829
    assert d["percentualDesconto"] == 0.0        # 829/829
    assert d["descontoProvimento279"] is False   # 829/829
    assert d["reterIss"] is False                # 829/829
    assert d["codigoTipoAto"] == "16.1"          # 797/829
    assert d["descricaoNatureza"] == "COMPRA E VENDA"
    assert d["partes"]["parteAto"][0]["documento"] == "00000001082"
    assert "motivoIsentoGratuito" not in d


def test_isencao_sem_motivo_escrito_e_recusada():
    """48 dos 829 saíram isentos, e todos com o motivo dentro."""
    import ato_selado as AS
    with pytest.raises(AS.AtoError, match="motivo"):
        AS.envelope_da_prenotacao(
            protocolo="1", escrevente="JEAN", versao_tabela="0220260101",
            descricao_natureza="REURB", isento=True)
    e = AS.envelope_da_prenotacao(
        protocolo="1", escrevente="JEAN", versao_tabela="0220260101",
        descricao_natureza="REURB", isento=True,
        motivo_isencao="Lei 13.465 de 2017")
    assert e["dadosSelo"]["motivoIsentoGratuito"] == "LEI 13.465 DE 2017"


def test_o_selo_da_prenotacao_grava_na_coluna_certa():
    import ato_selado as AS
    assert AS.COLUNA_DO_SELO["ri_protocolos"] == "selo_prenotacao"
    assert AS.caminho_do_ato("ri_protocolos",
                             "PRENOTACAO") == "/selo/imovel/prenotacao"


# ------------------------------------------------------------- o comprovante


def _comprovante(casa) -> str:
    """O texto de dentro do `.odt`.

    O comprovante sai em documento, e nao em tela: e papel que o cliente leva.
    Ler o `content.xml` de dentro do zip e a unica forma honesta de conferir o
    que foi impresso — conferir o HTML de uma tela que nao existe seria testar
    outra coisa.
    """
    import re as _re
    import zipfile
    pid = _ultimo(casa)["id"]
    bruto = casa["cliente"].get(
        f"/registro-imoveis/protocolo/{pid}/comprovante").get_data()
    with zipfile.ZipFile(io.BytesIO(bruto)) as z:
        xml = z.read("content.xml").decode("utf-8")
    return _re.sub(r"<[^>]+>", " ", xml)


def test_o_comprovante_diz_o_prazo_que_a_prenotacao_TEM(casa):
    """O REURB-S tem 40 dias úteis, e o comprovante dizia 20.

    Era `PRAZO_PRENOTACAO` fixo no lugar do prazo gravado — o papel que o
    cliente leva para casa afirmando um prazo menor do que o que ele tem.
    Estava no backlog do balcão desde a revisão do RI.
    """
    _prenotar(casa, reurb="1")
    html = _comprovante(casa)
    assert "40 dias úteis" in html
    assert "20 dias úteis" not in html


def test_o_comprovante_comum_continua_dizendo_20(casa):
    _prenotar(casa)
    assert "20 dias úteis" in _comprovante(casa)


def test_o_comprovante_traz_o_que_o_cliente_veio_saber(casa):
    """Serviço requerido, documentos, livro de destino e dias que faltam."""
    _prenotar(casa, documento_descricao="Escritura publica, 2 vias",
              livro_destino="3")
    html = _comprovante(casa)
    assert "COMPRA E VENDA" in html.upper()
    assert "Escritura publica, 2 vias" in html
    assert "Livro 3" in html
    assert "faltam" in html
    # E o livro do protocolo aparece como o que é, sem depender da coluna.
    assert "Livro 1-A de Protocolo" in html


# ---------------------------------------- o carimbo do selo no comprovante
#
# ORDEM DO OFICIAL EM 22/09/2026: «comprovante da prenotacao tem que sair
# carimbo do selo completo».
#
# Ate aqui o papel trazia uma linha «Selo» com o NUMERO e mais nada — o mesmo
# que as certidoes traziam antes de 17/09. Medido no razao da producao: esta
# casa comprou **835 selos** em `/selo/imovel/prenotacao`, e nenhum aparecia
# inteiro no papel que o apresentante leva.

# A etiqueta como o aparelho a escreve — copiada de uma prenotacao REAL desta
# casa (protocolo 11573, 22/09/2026), e nao inventada.
ETIQUETA_REAL = (
    "Poder Judiciário – TJMA. Selo: PRENOT000000STZ9R7DD8BZ6AG49, "
    "22/09/2026 10:56:07, Ato: 16.1, Parte(s): LUANNA CARREIRO SOUSA, "
    "Total R$ 43,37 Emol R$ 38,72 FERC R$ 1,16 FADEP R$ 1,55 FEMP R$ 1,55 "
    "FERRFIS R$ 0,39 Consulte em https://selo.tjma.jus.br")
NUMERO_REAL = "PRENOT000000STZ9R7DD8BZ6AG49"


def _selar_a_mao(casa, *, texto: str | None) -> None:
    """Poe o selo na prenotacao e, quando houver, a etiqueta no razao.

    **O NUMERO E A ETIQUETA MORAM EM LUGARES DIFERENTES**, e e isso que o
    conserto enfrenta: `ri_protocolos.selo_prenotacao` guarda os 28
    caracteres, e quem tem o texto do aparelho e `sd_selos`.
    """
    con = _con(casa)
    with con:
        con.execute("UPDATE ri_protocolos SET selo_prenotacao=? WHERE id=?",
                    (NUMERO_REAL, _ultimo(casa)["id"]))
        if texto is not None:
            con.execute(
                "INSERT INTO sd_selos(numero, texto, caminho, atribuicao,"
                "                     obtido_em, obtido_por) "
                "VALUES (?,?,?,?,?,?)",
                (NUMERO_REAL, texto, "/selo/imovel/prenotacao", "IMOVEL",
                 "2026-09-22T10:56:07", "MARIO EXEMPLO DOS SANTOS"))


def test_o_comprovante_sai_com_o_carimbo_INTEIRO_do_selo(casa):
    """Numero, ato, data, partes, os quatro fundos e o endereco de consulta.

    **NUMERO DE SELO SOZINHO NAO SE CONFERE.** Quem recebe o comprovante
    precisa saber qual ato foi selado, quando, sobre quem e quanto se cobrou —
    e e a linha de valores que desmente, ou confirma, o que foi pago no
    balcao.
    """
    _prenotar(casa)
    _selar_a_mao(casa, texto=ETIQUETA_REAL)
    papel = _comprovante(casa)
    assert NUMERO_REAL in papel
    assert "16.1" in papel                       # o ato da tabela do TJMA
    assert "22/09/2026" in papel                 # a data em que o selo saiu
    assert "43,37" in papel and "38,72" in papel  # total e emolumentos
    for fundo in ("FERC", "FADEP", "FEMP", "FERRFIS"):
        assert fundo in papel, f"o carimbo perdeu o {fundo}"
    assert "selo.tjma.jus.br" in papel           # o atalho de conferencia


def test_o_numero_do_selo_so_aparece_DENTRO_do_carimbo(casa):
    """A linha «Selo» da tabela saiu: quem diz o numero agora e o carimbo.

    Deixar as duas faria o numero aparecer como dado solto numa tabela E
    dentro do carimbo, num papel de uma pagina — e quem le concluiria que sao
    dois selos.

    **DUAS VEZES E O CERTO, E NAO UMA**: o carimbo escreve o numero na
    primeira linha e outra vez dentro do endereco de conferencia
    (`.../#/resumo/<codigo>`), que e o atalho de quem vai conferir. E o mesmo das
    quatro certidoes. O que este teste guarda e o LUGAR: as duas ocorrencias
    ficam DEPOIS do rotulo do carimbo — a linha da tabela vinha antes.
    """
    _prenotar(casa)
    _selar_a_mao(casa, texto=ETIQUETA_REAL)
    papel = _comprovante(casa)
    assert papel.count(NUMERO_REAL) == 2
    assert papel.index(NUMERO_REAL) > papel.index("SELO DA PRENOTAÇÃO")


def test_sem_a_etiqueta_no_razao_o_carimbo_sai_com_o_NUMERO(casa):
    """Os 14 casos medidos: ha numero e o razao nao guardou o texto.

    **Carimbo com o numero cru e melhor que carimbo nenhum** — e o numero e
    justamente o que se digita no site do Tribunal. Sumir com ele faria o
    papel calar sobre um selo que foi comprado e pago.
    """
    _prenotar(casa)
    _selar_a_mao(casa, texto=None)
    assert NUMERO_REAL in _comprovante(casa)


def test_prenotacao_sem_selo_nao_inventa_carimbo(casa):
    """Sem selo o papel nao afirma nada — campo vazio nao mente."""
    _prenotar(casa)
    papel = _comprovante(casa)
    assert "SELO DA PRENOTAÇÃO" not in papel
    assert "selo.tjma.jus.br" not in papel
