"""A certidão do RI: carimbo completo e a linha de quem assina.

    «emiti uma certidao agora, mas saiu com o carimbo incompleto. preciso que
     o carimbo da certidao saia completo com qr code, link, emolumentos, etc.
     e precisa dar uma linha de espaco para quem emitiu a certidao assinar.
     (revisar o nome que aparece no final para assinatura por emitir a
     certidao, precisa constar o nome e funcao do usuario logado»
      — o oficial, 16/09/2026

O QUE ESTAVA ERRADO, medido na certidão que ele emitiu — a **nº 9/2026** da
matrícula 3.110, às 23h43 daquele dia:

  * a rota chamava `carimbo_do_selo_odf(selo, **None**, ...)`, e o segundo
    parâmetro é o nome da imagem do QR. **Das quatro chamadas desse carimbo na
    casa, era a única que passava `None`;**
  * o **endereço da consulta** era calculado por `partes_do_carimbo` e não era
    impresso em papel nenhum — quem não tem câmera à mão ficava sem conferir;
  * a certidão terminava no carimbo: **não havia onde assinar**, e
    `ri_certidoes.emitida_por` estava **NULL nas 372**, embora o `INSERT` já a
    nomeasse e passasse `None`.

O QUE ESTE ARQUIVO PROVA, e por que cada coisa:

  1. **O QR chega ao pacote.** Um `.odt` é um zip; o teste abre e procura a
     imagem em `Pictures/`. Conferir só o XML diria que o papel *referencia* a
     figura — e figura referenciada e ausente é um quadrado vazio no papel
     assinado.
  2. **O link sai escrito**, com o número do selo dentro.
  3. **Os emolumentos saem**, que é a linha de valores do próprio selo.
  4. **Há espaço antes da linha de assinatura.** O branco tem dono: é onde a
     caneta passa. Por isso o teste lê o XML **sem colapsar espaço** — teste
     que mede branco não pode colapsar branco, lição que este projeto pagou
     duas vezes.
  5. **O nome e a função são os de quem emitiu**, gravados na emissão. A
     segunda via tirada por outra pessoa continua trazendo o nome de quem
     expediu — e é isso que separa uma certidão de um papel que qualquer um
     reimprime em nome alheio.
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

SENHA = "Senha#12345"
SELO = "CERINT000000B5L9KK4F2QJ5ZQ95"
# O TEXTO DO SELO É O QUE O APARELHO IMPRIME — a linha de valores sai dele.
TEXTO_DO_SELO = (
    "Poder Judiciário — TJMA. Selo: " + SELO + ", 16/09/2026 23:43:15, "
    "Ato: 16.24.4, Total R$ 121,63 Emol R$ 108,60 FERC R$ 3,26 "
    "FADP R$ 4,34 FEMP R$ 4,34 FERRFIS R$ 1,09"
)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    db = cg_casa["db"]
    db.create_user("balcao", "LAURA MARIA DA COSTA", SENHA, "ADMIN")
    db.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
                     "ri_cns": "000000"})
    con = sqlite3.connect(cg_casa["banco"])
    with con:
        con.execute("UPDATE users SET funcao=? WHERE username=?",
                    ("Escrevente Autorizada", "balcao"))
        con.execute(
            """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
                                          tipo_ficha, cidade, uf, teor,
                                          origem, criado_em)
               VALUES ('3110','2-S','2S','ATIVA','ESTRUTURADA','Cidade Exemplo',
                       'MA','Teor da ficha para a certidão.','MANUAL',
                       '2026-09-16T10:00:00')""")
    mid = con.execute(
        "SELECT id FROM ri_matriculas WHERE numero='3110'").fetchone()[0]
    con.close()
    c = cg_casa["app"].test_client()
    c.post("/login",
           data={"username": "balcao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {**cg_casa, "cliente": c, "mid": mid}


def _emitir(casa) -> int:
    """Emite a certidão e guarda o selo **como a produção guarda**.

    O NÚMERO NA COLUNA, A ETIQUETA NO RAZÃO. Medido nas duas certidões reais
    desta casa: `ri_certidoes.selo_texto` tem os **28 caracteres** do código, e
    `sd_selos.texto` tem os **264** com `Total R$ … Emol R$ … FERC R$ …`.

    **A PRIMEIRA VERSÃO DESTE AJUDANTE MANDAVA A ETIQUETA INTEIRA NO
    FORMULÁRIO**, e a rota guarda o que recebe — de modo que o teste dos
    emolumentos passava com o defeito de pé, e quem o viu foi o oficial, no
    papel. Bancada que monta o dado de um jeito que a produção não usa prova
    contra si mesma.
    """
    ficha = casa["cliente"].get(
        f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    casa["cliente"].post(
        f'/registro-imoveis/{casa["mid"]}/certidao',
        data={"csrf_token": _token(ficha), "tipo": "INTEIRO_TEOR",
              "fonte_corpo": "TEXTO", "requerente": "OTAVIO PEREIRA DE CASTELO",
              "selo_texto": SELO},
        follow_redirects=True)
    con = sqlite3.connect(casa["banco"])
    linha = con.execute(
        "SELECT id FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    assert linha is not None, "a certidão não foi emitida"
    cid = int(linha[0])
    with con:
        con.execute(
            """INSERT INTO sd_selos (numero, texto, caminho, atribuicao,
                                     referencia, tabela, ato_id, obtido_em,
                                     usado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (SELO, TEXTO_DO_SELO, "/selo/imovel/certidao", "IMOVEL",
             f"ri_certidoes:{cid}", "ri_certidoes", cid,
             "2026-09-17T11:08:55", "2026-09-17T11:08:55"))
    con.close()
    return cid


def _odt(casa, certidao_id: int) -> tuple[str, list[str]]:
    """Devolve o `content.xml` CRU e a lista de arquivos do pacote.

    **CRU de propósito**: o que se mede aqui inclui o espaço da assinatura, e
    um extrator que colapse branco mede a coisa errada.
    """
    r = casa["cliente"].get(
        f"/registro-imoveis/certidoes/{certidao_id}.odt?formato=odt")
    assert r.status_code == 200, r.status_code
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        return z.read("content.xml").decode("utf-8"), z.namelist()


# ------------------------------------------------------------- o carimbo


def test_o_qr_do_selo_vai_dentro_do_pacote(casa):
    """Figura referenciada e ausente é um quadrado vazio no papel assinado."""
    pytest.importorskip("segno")
    xml, nomes = _odt(casa, _emitir(casa))
    imagens = [n for n in nomes if n.startswith("Pictures/")]
    assert imagens, f"a certidão saiu sem imagem nenhuma: {nomes}"
    assert any("qr" in n.lower() for n in imagens), (
        f"nenhuma das imagens é o QR do selo: {imagens}")
    citada = re.findall(r'xlink:href="(Pictures/[^"]+)"', xml)
    for nome in citada:
        assert nome in nomes, f"o papel cita {nome} e ele não está no pacote"


def test_o_link_da_consulta_sai_escrito(casa):
    """Quem não tem câmera à mão também tem de poder conferir o selo."""
    xml, _ = _odt(casa, _emitir(casa))
    assert "selo.tjma.jus.br" in xml, "o endereço da consulta não saiu"
    assert SELO in xml, "o número do selo não saiu no carimbo"


def test_os_emolumentos_saem_no_carimbo(casa):
    """«o carimbo de certidão sempre precisa ir completo, com os emolumentos
    do ato» — o oficial, 17/09/2026.

    **A COLUNA GUARDA O NÚMERO; A ETIQUETA MORA NO RAZÃO**, e é ela que traz
    os valores. O carimbo monta o que diz a partir do texto que recebe: com o
    número, ele imprime rótulo, número, QR e link, e **não tem de onde tirar os
    valores**. É a mesma armadilha de 15/09, noutra tela.
    """
    xml, _ = _odt(casa, _emitir(casa))
    sem_marcas = re.sub(r"<[^>]+>", " ", xml)
    for pedaco in ("Total R$ 121,63", "Emol R$ 108,60", "FERC R$ 3,26"):
        assert pedaco in sem_marcas, (
            f"faltou «{pedaco}» no carimbo — ele leu o número da coluna em vez "
            f"da etiqueta do razão")


def test_sem_etiqueta_no_razao_sai_o_numero_e_nao_uma_conta(casa):
    """Selo digitado à mão pode não ter etiqueta guardada — e ali não se inventa.

    Remontar a conta aqui imprimiria num papel assinado um valor que o selo
    não declara. O carimbo sai com o número, e sem a linha de valores.
    """
    cid = _emitir(casa)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("DELETE FROM sd_selos WHERE ato_id=? AND tabela=?",
                    (cid, "ri_certidoes"))
    con.close()
    xml, _ = _odt(casa, cid)
    sem_marcas = re.sub(r"<[^>]+>", " ", xml)
    assert SELO in sem_marcas, "o número do selo tem de sair assim mesmo"
    assert "Total R$" not in sem_marcas, (
        "saiu uma linha de valores que o selo não declara")


# ---------------------------------------------------------- a assinatura


def test_nao_ha_traco_para_assinar_a_mao(casa):
    """O CONTRATO MUDOU EM 22/09/2026, e este teste cobrava o antigo.

    Até ali ele exigia a linha de sublinhados e dois parágrafos vazios antes
    dela — o branco da caneta, ordem de 16/09. Em 22/09 o espaço de
    assinatura à mão saiu da certidão («só na ficha», `certidao_texto.
    sem_linha_de_assinatura_a_mao`), e o oficial confirmou em 23/09 ao mandar
    atualizar os testes. Fica o nome e o título de quem expediu — o teste
    seguinte —, e o traço não volta.
    """
    xml, _ = _odt(casa, _emitir(casa))
    assert not re.search(r"_{8,}", xml), (
        "a certidão voltou a sair com traço de assinatura à mão")


def test_com_selo_digitado_a_mao_a_tela_nao_estoura(casa):
    """`folhas_contadas_msg` só nascia no ramo do selo AUTOMÁTICO — 23/09/2026.

    Com o selo digitado à mão (o caminho de quando o selador não responde) a
    tela estourava `UnboundLocalError` DEPOIS de gravar a certidão: o desenho
    do problema #84, a tela dizendo «erro» sobre um ato já praticado. Este
    arquivo emite sempre com selo digitado, e por isso os testes daqui foram
    os primeiros a ver.
    """
    ficha = casa["cliente"].get(
        f'/registro-imoveis/{casa["mid"]}').get_data(as_text=True)
    r = casa["cliente"].post(
        f'/registro-imoveis/{casa["mid"]}/certidao',
        data={"csrf_token": _token(ficha), "tipo": "INTEIRO_TEOR",
              "fonte_corpo": "TEXTO", "requerente": "OTAVIO PEREIRA DE CASTELO",
              "selo_texto": SELO},
        follow_redirects=False)
    assert r.status_code == 302, (
        f"a emissão com selo à mão respondeu {r.status_code} em vez de voltar "
        "para a ficha")
    con = sqlite3.connect(casa["banco"])
    quantas = con.execute("SELECT COUNT(*) FROM ri_certidoes").fetchone()[0]
    con.close()
    assert quantas == 1, "um clique tem de dar uma certidão, e só uma"


def test_o_nome_e_a_funcao_sao_os_de_quem_emitiu(casa):
    """Quem assina é a pessoa que expediu, com a função do cadastro dela."""
    cid = _emitir(casa)
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    linha = con.execute("SELECT * FROM ri_certidoes WHERE id=?",
                        (cid,)).fetchone()
    con.close()
    assert linha["emitida_por_nome"] == "LAURA MARIA DA COSTA", (
        "a certidão não gravou quem a emitiu — a coluna existia e recebia None")
    assert linha["emitida_por_funcao"] == "Escrevente Autorizada"

    xml, _ = _odt(casa, cid)
    sem_marcas = re.sub(r"<[^>]+>", " ", xml)
    assert "LAURA MARIA DA COSTA" in sem_marcas
    assert "Escrevente Autorizada" in sem_marcas
    assert "quem expediu esta certidão" not in sem_marcas


def test_certidao_antiga_sai_sem_nome_inventado(casa):
    """As 372 anteriores não ganham nome inventado — ninguém sabe quem as fez.

    Escrever ali quem está imprimindo faria a segunda via afirmar que ela foi
    expedida por quem só a reimprimiu.

    Até 23/09/2026 este teste também exigia a linha de assinatura; ela saiu
    da certidão em 22/09 (ver `test_nao_ha_traco_para_assinar_a_mao`), e o
    que continua valendo é o nome não ser inventado.
    """
    cid = _emitir(casa)
    con = sqlite3.connect(casa["banco"])
    with con:
        con.execute("""UPDATE ri_certidoes
                          SET emitida_por_nome=NULL, emitida_por_funcao=NULL
                        WHERE id=?""", (cid,))
    con.close()
    xml, _ = _odt(casa, cid)
    sem_marcas = re.sub(r"<[^>]+>", " ", xml)
    assert not re.search(r"_{8,}", xml)
    assert "LAURA MARIA DA COSTA" not in sem_marcas


def test_o_cabecalho_da_certidao_e_o_completo(casa):
    """«o cabeçalho não está completo» — o oficial, 23/09/2026.

    Aprovado em imagem («pode aplicar»): República, Estado, Comarca, Serventia,
    endereço, contato, titular, substituta e CNS — no cabeçalho da página, o
    mesmo da certidão do Livro 3. E os valores são os de hoje (`serventia`),
    e não os do E-Ofício, que trazem o oficial anterior.
    """
    cid = _emitir(casa)
    r = casa["cliente"].get(
        f"/registro-imoveis/certidoes/{cid}.odt?formato=odt")
    assert r.status_code == 200
    with zipfile.ZipFile(io.BytesIO(r.data)) as z:
        estilos = z.read("styles.xml").decode("utf-8")
    cabecalho = estilos[estilos.index("<style:header"):]
    for trecho in ("REPÚBLICA FEDERATIVA DO BRASIL", "ESTADO DO MARANHÃO",
                   "COMARCA DE CIDADE EXEMPLO/MA", "SERVENTIA EXTRAJUDICIAL DO",
                   "CNPJ", "Substituta", "CNS 000000"):
        assert trecho in cabecalho, trecho
    assert "Oficial: " not in cabecalho
    assert "Rogério" not in cabecalho and "ROGÉRIO" not in cabecalho
