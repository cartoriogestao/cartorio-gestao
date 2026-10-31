"""O CARIMBO DAS CERTIDÕES, aprovado pelo oficial em 17/09/2026.

    «preciso que o carimbo das certidoes (todas) saia com data e hora da
     emissao, emolumentos, qr code, link de acesso ao tj, requerente.
     precisamos de um carimbo com todas informacoes que usamos para emitir o
     selo. bole um modelo e me mostra aqui pra eu aprovar»

O modelo foi apresentado e ele respondeu **«tudo conforme pontuado»** — o que
respondeu também as três perguntas que foram junto: alinhar o molde do RCPN,
rotular a parte como **Requerente**, e imprimir as **marcas** do selo.

O que estes testes guardam:

| | |
|---|---|
| as cinco linhas | número · ato e data por extenso · requerente · valores · link |
| as marcas | `Selo Isento` e `Diferido`, coladas na linha que elas qualificam |
| o link | `#/resumo/<código>` — a consulta daquele selo, e não o portal seco |
| a largura | a certidão ocupa a folha inteira; **o ato da ficha não mudou** |
| as quatro | RI, RCPN de inteiro teor, Protesto e RCPJ/RTD |
"""
import re
import sqlite3
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

import ato_selado as AS
import ri_odt
import selo_no_papel as SNP

SENHA = "Senha#12345"

# A etiqueta como o aparelho a devolveu na certidão do oficial, em 17/09/2026.
ETIQUETA = (
    "Poder Judiciário – TJMA. Selo: CERINT0000009ZYQS3MCYZOV5U97, "
    "17/09/2026 16:30:36, Ato: 16.24.4, "
    "Parte(s): OTAVIO CUNHA BARROS DE CASTELO, "
    "Total R$ 101,88 Emol R$ 90,96 FERC R$ 2,73 FADEP R$ 3,64 FEMP R$ 3,64 "
    "FERRFIS R$ 0,91 Consulte em https://selo.tjma.jus.br")
NUMERO = "CERINT0000009ZYQS3MCYZOV5U97"


def _linhas(odf: str) -> list[str]:
    return [" ".join(x.split()) for x in
            re.findall(r'P-selo-compacto">([^<]*)<', odf) if x.strip()]


# ------------------------------------------------- o que o carimbo diz


def test_as_cinco_linhas_do_modelo_aprovado():
    """Número, ato e data, requerente, valores, link — nesta ordem."""
    frag, _ = ri_odt.carimbo_da_certidao_odf(ETIQUETA)
    linhas = _linhas(frag)
    assert linhas[0] == NUMERO
    assert linhas[1] == "Ato 16.24.4 · emitida em 17/09/2026 às 16:30:36"
    assert linhas[2] == "Requerente: OTAVIO CUNHA BARROS DE CASTELO"
    assert "Total R$ 101,88" in linhas[3] and "Emol R$ 90,96" in linhas[3]
    assert "FERRFIS R$ 0,91" in linhas[3], "os quatro fundos, e não só os três"
    assert linhas[4] == (
        f"Confira em https://selo.tjma.jus.br/#/resumo/{NUMERO}")


def test_o_link_abre_este_selo_e_nao_so_o_portal():
    """O aparelho escreve o portal seco — em 25.839 de 25.839.

    Quem recebe o papel teria de digitar 28 caracteres à mão; o nosso leva o
    código, que é o mesmo endereço de dentro do QR.
    """
    assert SNP.ler(ETIQUETA)["consulta"] == "https://selo.tjma.jus.br"
    assert SNP.link_de_consulta(NUMERO).endswith(f"#/resumo/{NUMERO}"), (
        "o link tem de abrir a consulta daquele selo — medido no portal em "
        "24/09/2026: a query `?selo=` abre a tela de digitar, vazia")


def test_a_marca_do_selo_sai_colada_no_valor_que_ela_desmente():
    """«Selo Isento» com R$ 115,44 escrito ao lado — medido: 172 selos.

    A marca numa linha própria deixaria de qualificar coisa nenhuma, e sem
    ela o papel afirma que se cobrou.
    """
    isento = ETIQUETA.replace("Consulte em", "Diferido, Selo Isento, Consulte em")
    linhas = _linhas(ri_odt.carimbo_da_certidao_odf(isento)[0])
    valores = [x for x in linhas if "Total R$" in x]
    assert valores and "Selo Isento" in valores[0] and "Diferido" in valores[0]


def test_o_link_de_2020_tambem_e_lido():
    """Onze selos escrevem «Consulte A VALIDADE DESTE SELO em https://…».

    São de março a maio de 2020 — 8 reconhecimentos de firma e **3 certidões
    do Registro de Imóveis**. Com o padrão literal antigo, nesses onze o papel
    saía sem endereço de consulta nenhum.
    """
    velha = ETIQUETA.replace("Consulte em",
                             "Consulte a validade deste selo em")
    assert SNP.ler(velha)["consulta"] == "https://selo.tjma.jus.br"


def test_sem_etiqueta_no_razao_sai_o_numero_e_nao_uma_conta():
    """Selo digitado à mão pode não ter etiqueta guardada.

    Remontar a conta aqui imprimiria num papel assinado um valor que o selo
    não declara.
    """
    linhas = _linhas(ri_odt.carimbo_da_certidao_odf(NUMERO)[0])
    assert NUMERO in " ".join(linhas)
    assert not any("Total R$" in x for x in linhas)


# ------------------------------------------------- o que NÃO mudou


def test_o_carimbo_do_ato_da_ficha_nao_ganhou_requerente():
    """O livro não mudou, e isso é deliberado.

    No ato, o carimbo está ao lado do próprio ato, que já nomeia as partes
    duas linhas acima — repetir ali gasta a linha que o livro não tem.
    """
    linhas = _linhas(ri_odt.carimbo_do_selo_odf(ETIQUETA, "qr.png"))
    assert not any(x.startswith("Requerente:") for x in linhas)
    assert any(x.startswith("Ato: 16.24.4 · 17/09/2026") for x in linhas)


def test_a_certidao_ocupa_a_folha_e_o_ato_continua_em_meia_largura():
    """Medido a 5,5 pt: a linha de valores mede 9,61 cm e a coluna, 6,25."""
    certidao, _ = ri_odt.carimbo_da_certidao_odf(ETIQUETA)
    assert "Col-selo-inteiro" in certidao and "Col-selo-texto-larga" in certidao
    ato = ri_odt.carimbo_do_selo_odf(ETIQUETA, "qr.png")
    assert "Col-selo-compacto" in ato and 'Col-selo-texto"' in ato


def test_o_qr_vai_um_por_selo_e_dentro_do_pacote():
    frag, imagens = ri_odt.carimbo_da_certidao_odf(ETIQUETA + "\n" + ETIQUETA)
    assert len(imagens) == 2, "um QR por selo — dois selos, dois QR"
    for png, tipo in imagens.values():
        assert png[:4] == b"\x89PNG" and tipo == "image/png"
    assert frag.count("draw:image") == 2


# ------------------------------------------------- o molde do RCPN


@pytest.mark.parametrize("molde", ["certidao_nascimento_modelo.odt",
                                   "certidao_casamento_modelo.odt",
                                   "certidao_obito_modelo.odt"])
def test_o_molde_do_rcpn_pede_as_mesmas_linhas(molde):
    """O molde é desenhado à mão pelo oficial, e fala por marcadores `@`.

    **DUAS MONTAGENS DO MESMO CARIMBO DIVERGEM NO PRIMEIRO CONSERTO** — e aqui
    a divergência seria entre duas certidões assinadas que falam do mesmo selo.
    """
    caminho = Path(__file__).resolve().parents[1] / "modelos" / molde
    xml = zipfile.ZipFile(caminho).read("content.xml").decode("utf-8")
    for marcador in ("@selo1", "@selo1_ato", "@selo1_requerente",
                     "@selo1_valores", "@selo1_consulta",
                     "@selo2_ato", "@selo2_requerente", "@selo2_consulta"):
        assert marcador in xml, f"o molde perdeu {marcador}"
    assert "@selo1_detalhe" not in xml, (
        "o detalhe trazia a parte emendada com o ato e a data; quem a nomeia "
        "agora é a linha do requerente")


# O VARREDOR DE «@ QUE O CODIGO NAO PREENCHE» JA EXISTE, e e de quem desenhou
# o molde: `tests/test_rc_certidao_molde.py`. Escrever o segundo aqui daria
# duas reguas para a mesma pergunta — e foi ele que conferiu os marcadores
# novos desta passada.


# ------------------------------------------------- as quatro certidões


def _sessao(tmp_path):
    import glob
    from app import create_app
    from database import Database
    dados = tmp_path / "dados"
    dados.mkdir()
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS",
                               SENHA, "ADMIN")
    Database(banco).set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    tela = c.get("/login").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    c.post("/login", data={"username": "tabeliao", "password": SENHA,
                           "csrf_token": token}, follow_redirects=True)
    return {"app": app, "c": c, "banco": banco}


@pytest.fixture()
def s(tmp_path):
    return _sessao(tmp_path)


def _selar(banco, tabela, ato_id):
    """O selo como a PRODUÇÃO o guarda: número na coluna, etiqueta no razão.

    Bancada que monta o dado de um jeito que a produção não usa prova contra
    si mesma — foi assim que o carimbo sem emolumentos passou num teste verde.
    """
    con = sqlite3.connect(banco)
    with con:
        con.execute(f"UPDATE {tabela} SET selo=? WHERE id=?", (NUMERO, ato_id))
        con.execute(
            """INSERT INTO sd_selos (numero, texto, caminho, atribuicao,
                                     referencia, tabela, ato_id, obtido_em,
                                     usado_em)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            (NUMERO, ETIQUETA, "/selo/protesto/certidao", "PROTESTO",
             f"{tabela}:{ato_id}", tabela, ato_id,
             "2026-09-17T16:30:36", "2026-09-17T16:30:36"))
    con.close()


def _texto_do_odt(dados: bytes) -> str:
    xml = zipfile.ZipFile(BytesIO(dados)).read("content.xml").decode("utf-8")
    return " ".join(re.sub(r"<[^>]+>", " ", xml).split())


def _emitir_certidao_do_protesto(s, monkeypatch) -> int:
    """A certidão emitida pela tela, com o item 17.5.1 pago no protocolo.

    O aparelho é substituído e não grava nada: a certidão fica SEM selo até o
    teste chamar `_selar`. A conferência de antes de lavrar continua valendo.
    """
    monkeypatch.setattr(AS, "selar_o_ato_lavrado", lambda *a, **k: {
        "selado": True, "numero": NUMERO, "numeros": [NUMERO], "motivo": None})
    con = sqlite3.connect(s["banco"])
    with con:
        cur = con.execute(
            "INSERT INTO cx_protocolos (numero, data_abertura, criado_em)"
            " VALUES ('2026.10.1', '2026-10-15', '2026-10-15T10:00:00')")
        pid = int(cur.lastrowid)
        con.execute("INSERT INTO cx_protocolo_atos (protocolo_id, codigo_ato,"
                    " quitado) VALUES (?, '17.5.1', 1)", (pid,))
    con.close()
    c = s["c"]
    tela = c.get("/protesto/certidoes").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    r = c.post("/protesto/certidoes/emitir",
               data={"csrf_token": token, "nome": "MARIA", "documento": "000.000.001-91", "anos": "5",  # CPF exigido desde 14/10 (CN art. 906)
                     "protocolo_id": str(pid)},
               follow_redirects=True)
    # a recusa da rota aparece aqui, com a mensagem, e não como tabela vazia
    recusa = re.findall(r"Certidão NÃO emitida[^<]*", r.get_data(as_text=True))
    assert not recusa, recusa
    con = sqlite3.connect(s["banco"])
    cid = con.execute("SELECT id FROM pt_certidoes").fetchone()[0]
    con.close()
    return cid


def test_a_certidao_do_protesto_saia_sem_carimbo_e_agora_sai_com(s, monkeypatch):
    """Medido: 57 selos em `/selo/protesto/certidao`, e nenhum no papel.

    Selo comprado que não aparece na certidão é o inverso do carimbo sem
    valores: os dois fazem o papel afirmar menos do que o selo diz.
    """
    c = s["c"]
    cid = _emitir_certidao_do_protesto(s, monkeypatch)
    _selar(s["banco"], "pt_certidoes", cid)

    papel = _texto_do_odt(
        c.get(f"/protesto/certidoes/{cid}/odt?formato=odt").data)
    assert "SELO DA CERTIDÃO" in papel
    assert NUMERO in papel
    assert "Requerente: OTAVIO CUNHA BARROS DE CASTELO" in papel
    assert "Total R$ 101,88" in papel and "FERRFIS R$ 0,91" in papel
    assert f"#/resumo/{NUMERO}" in papel


def test_a_certidao_do_protesto_sem_selo_nao_inventa_carimbo(s, monkeypatch):
    """Certidão sem selo sai sem quadro — caixa vazia afirma que falta colar."""
    c = s["c"]
    cid = _emitir_certidao_do_protesto(s, monkeypatch)
    con = sqlite3.connect(s["banco"])
    assert not con.execute("SELECT selo FROM pt_certidoes WHERE id=?",
                           (cid,)).fetchone()[0]
    con.close()
    papel = _texto_do_odt(
        c.get(f"/protesto/certidoes/{cid}/odt?formato=odt").data)
    assert "SELO DA CERTIDÃO" not in papel


# ------------------------------------------------- o QR, conferido de verdade


def _png_esperado(numero: str) -> bytes:
    """O QR que o carimbo deve levar, montado do mesmo endereço.

    **CONFERIR QUE «HÁ UMA IMAGEM» NÃO BASTA** — imagem errada abre o selo de
    outro ato, com cara de conferido. Aqui o PNG do papel é comparado com o
    PNG do endereço deste selo: mesma entrada, mesmo desenho.
    """
    import segno
    from io import BytesIO
    buf = BytesIO()
    segno.make(SNP.link_de_consulta(numero), error="m").save(
        buf, kind="png", scale=6, border=0)
    return buf.getvalue()


def test_o_qr_do_carimbo_e_o_deste_selo_e_nao_outro():
    frag, imagens = ri_odt.carimbo_da_certidao_odf(ETIQUETA)
    assert len(imagens) == 1
    (png, tipo), = imagens.values()
    assert png == _png_esperado(NUMERO), (
        "o QR do papel não é o do endereço deste selo")
    nome, = imagens
    assert f'xlink:href="Pictures/{nome}"' in frag, (
        "o carimbo tem de citar a imagem que vai no pacote")


def test_a_certidao_do_protesto_leva_o_qr_dentro_do_pacote(s, monkeypatch):
    """Conferir o XML diria que o papel REFERENCIA a imagem; o zip prova que ela foi."""
    c = s["c"]
    cid = _emitir_certidao_do_protesto(s, monkeypatch)
    _selar(s["banco"], "pt_certidoes", cid)

    dados = c.get(f"/protesto/certidoes/{cid}/odt?formato=odt").data
    pacote = zipfile.ZipFile(BytesIO(dados))
    # 14/10/2026: a certidão ganhou o cabeçalho da casa, e o brasão vai no
    # pacote referenciado pelo cabeçalho da página (styles.xml), não pelo
    # corpo. O QR é a imagem que NÃO é o brasão.
    imagens = [n for n in pacote.namelist()
               if n.startswith("Pictures/") and "brasao" not in n]
    assert imagens, "a certidão do protesto saiu sem o QR dentro do pacote"
    xml = pacote.read("content.xml").decode("utf-8")
    for nome in imagens:
        assert f'xlink:href="{nome}"' in xml
    assert pacote.read(imagens[0]) == _png_esperado(NUMERO), (
        "o QR da certidão do protesto não é o do selo dela")


def test_a_certidao_do_rcpj_rtd_leva_o_qr_dentro_do_pacote(s):
    """A outra que não tinha carimbo nenhum — 38 selos comprados no razão."""
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    with con:
        con.execute(
            """INSERT INTO rg_registros(atribuicao, serie, numero,
                   requerente_nome, situacao, origem, criado_em)
               VALUES (4,'TD_B',1508,'EMPRESA X','ATIVO','MANUAL',
                       '2026-09-17T09:00:00')""")
        rid = int(con.execute("SELECT id FROM rg_registros").fetchone()["id"])
        con.execute(
            """INSERT INTO rg_atos(registro_id, tipo, data_ato, teor,
                   folha, origem, criado_em)
               VALUES (?, 'REGISTRO', '2026-09-17',
                       'Teor do registro, reproduzido do livro.', '10',
                       'MANUAL', '2026-09-17T09:00:00')""", (rid,))
    con.close()
    # A CERTIDAO SE EMITE PELO DOMINIO, e o que este teste mede e a ROTA do
    # `.odt`: e nela que o carimbo entrou hoje.
    import atrib_certidao as CE
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    with con:
        feito = CE.emitir(con, "RCPJ_RTD", rid, hoje="2026-09-17",
                          agora="2026-09-17T09:10:00", requerente="EMPRESA X",
                          finalidade="prova", usuario="MARIO")
    con.close()
    cid = int(feito["certidao_id"])
    c = s["c"]
    _selar(s["banco"], "at_certidoes", cid)
    dados = c.get(f"/atribuicoes/certidoes/{cid}/odt?formato=odt").data
    pacote = zipfile.ZipFile(BytesIO(dados))
    imagens = [n for n in pacote.namelist() if n.startswith("Pictures/")]
    assert imagens, "a certidão do RCPJ/RTD saiu sem o QR dentro do pacote"
    assert pacote.read(imagens[0]) == _png_esperado(NUMERO)


def test_o_molde_do_rcpn_troca_o_qr_pelo_deste_selo():
    """O molde nasce com o QR de outro selo desenhado dentro dele.

    Se a troca falhar, o papel sai com **um QR que abre o selo de outra
    certidão** — conferir o selo errado com cara de conferido é pior que não
    conferir.
    """
    import rc_certidao_odt as RCODT
    dados = RCODT.arquivo_da_certidao(
        {"especie": "NASCIMENTO"},
        {"selos": [{"numero": NUMERO, "texto": ETIQUETA}]},
        {"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    pacote = zipfile.ZipFile(BytesIO(dados))
    imagens = [n for n in pacote.namelist() if n.startswith("Pictures/")]
    assert any(pacote.read(n) == _png_esperado(NUMERO) for n in imagens), (
        "o molde do RCPN saiu com o QR que veio desenhado nele")
    xml = pacote.read("content.xml").decode("utf-8")
    assert f"#/resumo/{NUMERO}" in xml, "e o link escrito é o deste selo"
    assert "@selo1" not in xml, "não pode sobrar marcador impresso"
