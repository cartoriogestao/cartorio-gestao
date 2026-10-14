"""
A etiqueta do reconhecimento de firma, na impressora térmica.

O QUE A ETIQUETA É
    A tira que se cola no documento. É ela que faz o reconhecimento existir no
    mundo — o registro no livro prova o ato, mas quem recebe o documento só vê
    a etiqueta. Saindo errada, sai errado no documento de terceiro.

O TEOR VEIO DO ACERVO, e não de uma suposição minha:

    "RECONHECO POR SEMELHANCA A FIRMA DE CARLA EXEMPLO LIMA. DOU FE.
     EM TEST.________ DA VERDADE. CIDADE EXEMPLO-MA,19/03/2020."

    São 13.209 etiquetas assim no E-Ofício. O sistema novo montava só até o
    "DOU FÉ." — o que basta na tela e não basta na tira, porque o fecho é o
    lugar do sinal público e da data do ato.

O QUE ESTES TESTES PROTEGEM
    Que o fecho não seja duplicado nos atos importados, que a página saia com o
    tamanho de papel certo (sem `@page` o navegador assume A4 e encolhe tudo
    num canto), que ato cancelado não imprima, e que a reimpressão seja contada
    — porque etiqueta térmica enrosca e reimprimir é rotina.
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

from notas_schema import texto_da_etiqueta            # noqa: E402

AGORA = "2026-08-17 09:00:00"


# ============================================================ o teor, sozinho

def test_o_fecho_e_acrescentado():
    """SEM O TRAÇO, desde 27/08/2026.

    «Tire o espaço do "em test da verdade", não gosto de espaço» — o oficial.
    Estava `EM TEST.________ DA VERDADE.`, com o traço onde iria o sinal
    público.

    E ESTE TESTE GUARDAVA UMA AFIRMAÇÃO QUE NUNCA FOI MEDIDA. O comentário do
    código dizia que eram «13.209 etiquetas assim no acervo»; fui conferir para
    atender o pedido e **não há uma sequer**: `strTextoSelo` do acervo não tem
    etiqueta com «VERDADE». A forma nunca teve precedente a imitar — e sem
    precedente, quem decide é quem assina o papel.
    """
    saida = texto_da_etiqueta(
        "RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DA SILVA. DOU FÉ.",
        "Cidade Exemplo", "MA", "2026-08-17")
    assert saida == ("RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DA SILVA. DOU FÉ. "
                     "EM TEST. DA VERDADE. CIDADE EXEMPLO-MA,17/08/2026.")
    assert "_" not in saida


def test_ato_importado_nao_ganha_o_fecho_duas_vezes():
    """Os 13.209 reconhecimentos do E-Ofício já vêm com o texto completo.

    Reimprimir a segunda via de um ato de 2020 tem de sair igual à primeira, e
    não com "DA VERDADE" repetido.
    """
    original = ("RECONHECO POR SEMELHANCA A FIRMA DE CARLA EXEMPLO LIMA. DOU FÉ. "
                "EM TEST.________ DA VERDADE. CIDADE EXEMPLO-MA,19/03/2020.")
    assert texto_da_etiqueta(original, "Cidade Exemplo", "MA", "2020-03-19") == original


def test_data_invalida_nao_quebra_a_etiqueta():
    """Data ruim no banco não pode impedir a tira de sair: o ato existe."""
    saida = texto_da_etiqueta("RECONHEÇO A FIRMA DE X. DOU FÉ.",
                              "Cidade Exemplo", "MA", "")
    assert "DA VERDADE" in saida
    assert "CIDADE EXEMPLO-MA" in saida


# ================================================================ no sistema

def _tem_cryptography() -> bool:
    """O selador de mentira precisa dela para o TLS — ver `selador_falso.py`."""
    try:
        import cryptography              # noqa: F401
    except ImportError:
        return False
    return True


@pytest.fixture()
def serventia(cg_casa):
    """O balcão com um selador de mentira ligado — e o ato nasce SELADO.

    **ELA PASSOU A SELAR EM 16/09/2026**, pelo relato #77: «se falhar o selo,
    sempre suspender o ato para corrigir o problema». Antes desse dia o
    reconhecimento ficava de pé sem selo, e esta bancada se apoiava nisso;
    hoje a rota o desfaz, e sem um selador não haveria ato nenhum para
    imprimir.

    O selador de mentira é o `tests/selador_falso.py`, que esta casa já usa em
    `test_selador_cliente` e em `test_ato_selado`: servidor de verdade, TLS de
    verdade, certificado próprio numa porta local — que é o que o selador
    desta serventia é, uma máquina da rede local.
    """
    if not _tem_cryptography():
        pytest.skip("o selador de mentira precisa de `cryptography`")
    import selador_cliente as CL
    import selador_config as SC
    from selador_falso import SeladorFalso, impressao_digital

    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    d = cg_casa['db']
    d.create_user("balcao", "LAURA MARIA DA COSTA", "Senha#12345", "ADMIN")
    d.set_settings({"ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
                    "ri_cns": "000000",
                    # A VERSÃO É A DATA DE VIGÊNCIA, e não a data do ato — o
                    # segundo defeito que o balcão achou em 27/08/2026. Sem
                    # ela o selador recusa, e o ato é desfeito.
                    "selo_tabela_custas_em": "2026-01-01"})
    con = sqlite3.connect(banco)
    con.execute("UPDATE users SET funcao='Escrevente Autorizado' WHERE username='balcao'")
    # O SERVIÇO 413 COM O ITEM DA TABELA — medido na produção em 16/09/2026:
    # `codigo_tj = '13.17.2'`, o item que esta casa usou 518 vezes só em 2026.
    # Sem ele a rota recusa lavrar (e está certa: selo sem item é selo que o
    # aparelho devolve recusado), e o teste morre no fixture sem chegar ao que
    # queria provar.
    con.execute("""INSERT OR IGNORE INTO cx_servicos
                       (codigo, codigo_tj, descricao, descricao_norm, ativo)
                   VALUES (413, '13.17.2',
                           'Reconhecimento de firma, por assinatura',
                           'RECONHECIMENTO DE FIRMA, POR ASSINATURA', 1)""")
    con.execute(
        """INSERT INTO nt_cartoes (nome, nome_norm, documento, origem, ativo,
                                   abertura, criado_em)
           VALUES ('MARIA DA SILVA','MARIA DA SILVA','52998224725','MANUAL',1,
                   '2026-01-10',?)""", (AGORA,))
    con.commit()
    cartao = con.execute("SELECT id FROM nt_cartoes").fetchone()[0]
    con.close()

    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": "balcao", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    token = pega(c.get("/notas/reconhecimento").get_data(as_text=True))
    with SeladorFalso() as aparelho:
        SC.gravar_credencial(dados, "fulano.detal123", "abcde123", agora=AGORA)
        CL.esquecer_tokens()
        con = sqlite3.connect(banco)
        with con:
            SC.gravar(con, base_url=aparelho.base, usuario="fulano.detal123",
                      agora=AGORA)
            CL.fixar_certificado(con, aparelho.base,
                                 sha256=impressao_digital(), agora=AGORA,
                                 usuario="TESTE")
        con.close()
        c.post("/notas/reconhecimento",
               data={"csrf_token": token, "acao": "reconhecer",
                     "cartao_id": str(cartao), "especie": "SEMELHANCA"},
               follow_redirects=True)
    con = sqlite3.connect(banco)
    linha = con.execute("SELECT id, selo FROM nt_reconhecimentos "
                        "ORDER BY id DESC LIMIT 1").fetchone()
    con.close()
    assert linha is not None, (
        "o reconhecimento não foi lavrado — desde o relato #77 (16/09/2026) "
        "o ato é desfeito quando o selo não sai, e sem selador não há "
        "etiqueta que imprimir")
    rid = linha[0]
    return {"app": app, "cliente": c, "banco": banco, "rec": rid,
            "token": token, "selo": linha[1]}


def sem_o_selo(s):
    """Deixa o ato como o do ACERVO: lavrado, e sem selo nenhum.

    Desde o relato #77 (16/09/2026) o sistema não lavra sem selo — mas os
    **13.209 reconhecimentos que vieram do E-Ofício** estão assim, e o selo
    cancelado também deixa o ato assim. É neles que a etiqueta precisa avisar.
    """
    con = sqlite3.connect(s["banco"])
    with con:
        con.execute("UPDATE nt_reconhecimentos SET selo=NULL WHERE id=?",
                    (s["rec"],))
        con.execute("""UPDATE nt_reconhecimento_partes SET selo=NULL
                        WHERE reconhecimento_id=?""", (s["rec"],))
    con.close()
    return s


def etiqueta(s):
    return s["cliente"].get(f"/notas/reconhecimento/{s['rec']}/etiqueta")


def test_a_etiqueta_abre_com_o_teor_completo(serventia):
    html = etiqueta(serventia).get_data(as_text=True)
    assert "RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DA SILVA. DOU FÉ." in html
    assert "DA VERDADE" in html
    assert "CIDADE EXEMPLO-MA" in html


def test_o_papel_tem_o_tamanho_da_tira(serventia):
    """Sem `@page`, o navegador assume A4 e encolhe a etiqueta num canto — o
    defeito mais comum de impressão térmica por navegador."""
    html = etiqueta(serventia).get_data(as_text=True)
    assert "@page" in html
    assert re.search(r"size:\s*100(\.0)?mm\s+30(\.0)?mm", html), \
        "o tamanho de papel não saiu 100×30 mm"
    assert re.search(r"margin:\s*0", html)


def test_a_etiqueta_nao_herda_o_menu_do_sistema(serventia):
    """O que o navegador manda para a impressora é a página inteira. Herdando o
    layout, a térmica receberia a barra lateral antes do teor."""
    html = etiqueta(serventia).get_data(as_text=True)
    assert "sidebar" not in html
    assert "Tabelionato de Notas</summary>" not in html


def test_quem_reconheceu_sai_na_tira_com_a_funcao(serventia):
    html = etiqueta(serventia).get_data(as_text=True)
    assert "LAURA MARIA DA COSTA" in html
    assert "Escrevente Autorizado" in html


def test_sem_selo_a_etiqueta_avisa_em_vez_de_sair_calada(serventia):
    """Etiqueta sem selo colada num documento é um reconhecimento que ninguém
    consegue conferir depois.

    O ato aqui é o do acervo — ver `sem_o_selo`.
    """
    html = etiqueta(sem_o_selo(serventia)).get_data(as_text=True)
    assert "ainda está sem selo" in html


def test_o_selo_anotado_aparece_na_etiqueta(serventia):
    s = serventia
    pagina = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post(f"/notas/reconhecimento/{s['rec']}",
                      data={"csrf_token": token, "acao": "selo",
                            "selo": "RECFIR000000D0XB4FK298AWP401"},
                      follow_redirects=True)
    html = etiqueta(s).get_data(as_text=True)
    assert "RECFIR000000D0XB4FK298AWP401" in html
    assert "ainda está sem selo" not in html


# ------------------------------------------------------------- reimpressão

def test_a_reimpressao_e_contada(serventia):
    """Etiqueta térmica enrosca, sai torta e sai em branco quando o rolo acaba.
    O que a tela precisa dizer é se aquele ato já teve etiqueta — para o balcão
    não colar duas no mesmo documento nem deixar um sem nenhuma."""
    etiqueta(serventia)
    etiqueta(serventia)
    con = sqlite3.connect(serventia["banco"])
    linha = con.execute("SELECT etiqueta_impressoes, etiqueta_impressa_em "
                        "FROM nt_reconhecimentos WHERE id=?",
                        (serventia["rec"],)).fetchone()
    con.close()
    assert linha[0] == 2
    assert linha[1]


def test_a_tela_do_ato_mostra_que_ja_foi_impressa(serventia):
    etiqueta(serventia)
    html = serventia["cliente"].get(
        f"/notas/reconhecimento/{serventia['rec']}").get_data(as_text=True)
    assert "Reimprimir etiqueta" in html
    assert "já impressa 1" in html


def test_a_impressao_fica_na_auditoria(serventia):
    etiqueta(serventia)
    con = sqlite3.connect(serventia["banco"])
    n = con.execute("SELECT COUNT(*) FROM audit_logs WHERE action='NT_ETIQUETA_IMPRESSA'"
                    ).fetchone()[0]
    con.close()
    assert n == 1


# ---------------------------------------------------------- o que não imprime

def test_ato_cancelado_nao_imprime_etiqueta(serventia):
    """Etiqueta de ato cancelado colada num documento é o ato valendo no mundo
    depois de ter sido desfeito no livro."""
    s = serventia
    pagina = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post(f"/notas/reconhecimento/{s['rec']}",
                      data={"csrf_token": token, "acao": "cancelar",
                            "motivo": "erro de digitação"}, follow_redirects=True)
    r = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}/etiqueta",
                         follow_redirects=True)
    texto = r.get_data(as_text=True)
    assert "não se imprime etiqueta" in texto
    assert "@page" not in texto              # nem chegou a montar a tira

    con = sqlite3.connect(s["banco"])
    n = con.execute("SELECT etiqueta_impressoes FROM nt_reconhecimentos WHERE id=?",
                    (s["rec"],)).fetchone()[0]
    con.close()
    assert n == 0, "ato cancelado não pode contar impressão"


def test_ato_inexistente_da_404(serventia):
    assert serventia["cliente"].get(
        "/notas/reconhecimento/99999/etiqueta").status_code == 404


# ------------------------------------------------------------------- ajuste

def test_a_tela_de_ajuste_abre_com_as_medidas(serventia):
    html = serventia["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    assert "100" in html and "30" in html
    assert "página de teste" in html


def test_medida_alterada_vale_na_etiqueta(serventia):
    s = serventia
    pagina = s["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post("/notas/etiqueta/ajuste",
                      data={"csrf_token": token, "etiqueta_largura_mm": "80",
                            "etiqueta_altura_mm": "40", "etiqueta_margem_mm": "3",
                            "etiqueta_deslocamento_x_mm": "-1",
                            "etiqueta_deslocamento_y_mm": "0.5",
                            "etiqueta_corpo_pt": "8", "etiqueta_entrelinha": "1.1"},
                      follow_redirects=True)
    html = etiqueta(s).get_data(as_text=True)
    assert re.search(r"size:\s*80(\.0)?mm\s+40(\.0)?mm", html)
    assert "translate(-1" in html


def test_medida_com_virgula_e_aceita(serventia):
    """Teclado brasileiro escreve 0,5. Recusar isso seria recusar o teclado."""
    s = serventia
    pagina = s["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = s["cliente"].post("/notas/etiqueta/ajuste",
                          data={"csrf_token": token, "etiqueta_largura_mm": "100",
                                "etiqueta_altura_mm": "30", "etiqueta_margem_mm": "1,5",
                                "etiqueta_deslocamento_x_mm": "0",
                                "etiqueta_deslocamento_y_mm": "0",
                                "etiqueta_corpo_pt": "7,5", "etiqueta_entrelinha": "1,15"},
                          follow_redirects=True)
    assert "Medidas guardadas" in r.get_data(as_text=True)
    assert "padding: 1.5mm" in etiqueta(s).get_data(as_text=True)


def test_medida_absurda_nao_apaga_a_etiqueta(serventia):
    """Alguém digita "10 mm" com a unidade junto. A impressão do balcão não pode
    parar por causa disso."""
    con = sqlite3.connect(serventia["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES "
                "('etiqueta_largura_mm', '10 mm')")
    con.commit()
    con.close()
    html = etiqueta(serventia).get_data(as_text=True)
    assert re.search(r"size:\s*100(\.0)?mm", html), "devia ter caído no padrão"


# ============================================================ o QR do selo
#
# POR QUE O QR IMPORTA
#     O selo tem 28 caracteres — `RECFIR000000D0XB4FK298AWP401`. Quem recebe o
#     documento e quer conferir precisa digitar os 28 no portal do tribunal sem
#     errar um. Na prática ninguém confere. Com o QR, aponta a câmera.
#
# ONDE SE CONFERE
#     https://selo.tjma.jus.br/ — confirmado no site do TJMA e no rodapé das
#     certidões que esta serventia já emitiu.

def com_selo(s, selo="RECFIR000000D0XB4FK298AWP401"):
    pagina = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post(f"/notas/reconhecimento/{s['rec']}",
                      data={"csrf_token": token, "acao": "selo", "selo": selo},
                      follow_redirects=True)
    return etiqueta(s).get_data(as_text=True)


def test_o_qr_sai_na_etiqueta(serventia):
    pytest.importorskip("segno", reason="o QR é opcional")
    html = com_selo(serventia)
    assert "<svg" in html
    assert 'class="qr"' in html


def test_o_numero_continua_impresso_ao_lado_do_qr(serventia):
    """QR borrado na térmica, etiqueta amassada, câmera de celular velho — o
    número legível é o que sobra quando o QR falha. Num documento que vale por
    décadas, redundância não é desperdício."""
    pytest.importorskip("segno")
    html = com_selo(serventia)
    assert "RECFIR000000D0XB4FK298AWP401" in html
    assert "<svg" in html


def test_sem_selo_nao_ha_qr(serventia):
    """QR que aponta para uma consulta vazia é pior que nenhum: parece
    conferível e não é."""
    pytest.importorskip("segno")
    html = etiqueta(sem_o_selo(serventia)).get_data(as_text=True)
    assert 'class="qr"' not in html


def test_o_qr_tem_o_tamanho_pedido(serventia):
    pytest.importorskip("segno")
    html = com_selo(serventia)
    assert re.search(r'width="12(\.0)?mm"', html), "o QR não saiu com 12 mm"


def test_o_qr_le_de_volta_o_endereco_certo(serventia):
    """Gerar um QR bonito que nenhuma câmera decodifica seria pior que não ter.

    Este teste desenha o QR no tamanho FÍSICO em que vai ser impresso, nas duas
    resoluções de térmica que existem no balcão (203 e 300 DPI), e lê de volta.
    """
    pytest.importorskip("segno")
    cv2 = pytest.importorskip("cv2", reason="leitura do QR precisa do OpenCV")
    import io as _io

    import numpy as np
    import segno
    from PIL import Image

    import notas_selo as NS
    esperado = NS.conteudo(NS.MODELO_PADRAO, "RECFIR000000D0XB4FK298AWP401")
    assert esperado.startswith("https://selo.tjma.jus.br/")

    qr = segno.make(esperado, error="m")
    modulos = qr.symbol_size(border=0)[0]
    detector = cv2.QRCodeDetector()
    for dpi in (203, 300):
        px = int(round(16 * dpi / 25.4))
        buf = _io.BytesIO()
        qr.save(buf, kind="png", border=2, scale=max(1, px // (modulos + 4)))
        imagem = np.array(Image.open(_io.BytesIO(buf.getvalue())).convert("L"))
        lido, *_ = detector.detectAndDecode(imagem)
        assert lido == esperado, f"a {dpi} DPI o QR não leu de volta (leu {lido!r})"


def test_o_conteudo_do_qr_e_configuravel(serventia):
    """O tribunal não publica o formato do link que abre a consulta preenchida.
    No dia em que publicar, tem de ser um campo — não uma atualização."""
    pytest.importorskip("segno")
    s = serventia
    pagina = s["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    dados = {"csrf_token": token, "etiqueta_largura_mm": "100",
             "etiqueta_altura_mm": "30", "etiqueta_margem_mm": "2",
             "etiqueta_deslocamento_x_mm": "0", "etiqueta_deslocamento_y_mm": "0",
             "etiqueta_corpo_pt": "8", "etiqueta_entrelinha": "1.15",
             "etiqueta_qr_mm": "16",
             "etiqueta_qr_url": "https://outro.exemplo/{selo}/{codigo}"}
    s["cliente"].post("/notas/etiqueta/ajuste", data=dados, follow_redirects=True)

    import notas_selo as NS
    assert NS.conteudo("https://outro.exemplo/{selo}/{codigo}", "ABC", "XYZ") \
        == "https://outro.exemplo/ABC/XYZ"
    html = s["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    assert "outro.exemplo" in html


def test_modelo_vazio_poe_o_numero_cru_no_qr():
    """Sem internet no celular, um leitor qualquer mostra os 28 caracteres na
    tela — já poupa a digitação."""
    import notas_selo as NS
    assert NS.conteudo("", "RECFIR000000D0XB4FK298AWP401") \
        == "RECFIR000000D0XB4FK298AWP401"
    assert NS.conteudo(NS.MODELO_PADRAO, "") == ""


def test_sem_a_biblioteca_a_etiqueta_sai_do_mesmo_jeito(serventia, monkeypatch):
    """Biblioteca que falta não pode impedir o balcão de imprimir: o selo
    impresso já vale por si, o QR é conveniência."""
    import builtins

    import notas_selo as NS
    real = builtins.__import__

    def sem_segno(nome, *a, **kw):
        if nome == "segno":
            raise ImportError("simulando servidor sem segno")
        return real(nome, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", sem_segno)
    assert NS.svg("qualquer coisa", 16) == ""
    assert NS.disponivel() is False
    monkeypatch.undo()

    html = com_selo(serventia)          # com a biblioteca de volta
    assert "RECFIR000000D0XB4FK298AWP401" in html


def test_campo_ausente_nao_derruba_a_gravacao(serventia):
    """Formulário já aberto no navegador não conhece medida acrescentada depois.

    Aconteceu ao pôr o tamanho do QR: as telas abertas no balcão passaram a não
    salvar nada, com a mensagem de que "" não é número. Ausente é "não mexi
    nisso"; presente e inválido é que é erro.
    """
    s = serventia
    pagina = s["cliente"].get("/notas/etiqueta/ajuste").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    r = s["cliente"].post("/notas/etiqueta/ajuste",
                          data={"csrf_token": token, "etiqueta_corpo_pt": "9"},
                          follow_redirects=True)
    assert "Medidas guardadas" in r.get_data(as_text=True)
    html = etiqueta(s).get_data(as_text=True)
    assert "font-size: 9.0pt" in html          # o que veio, mudou
    assert re.search(r"size:\s*100(\.0)?mm", html)   # o que não veio, ficou


def test_o_qr_QUE_A_ROTA_DEVOLVE_le_de_volta(serventia):
    """A prova que importa: não a biblioteca, mas o QR que sai pela rota.

    Os outros testes conferem que o `segno` funciona e que o `<svg>` aparece no
    HTML. Nenhum deles pega uma escala errada no template, um `viewBox` trocado
    ou um transform que achata o desenho — e qualquer um dos três produziria um
    QR que existe na tela e não lê no papel.

    Aqui o SVG é arrancado da resposta HTTP, redesenhado módulo a módulo e lido
    de volta pelo decodificador, no tamanho físico das duas resoluções de
    térmica que existem no balcão.
    """
    pytest.importorskip("segno")
    cv2 = pytest.importorskip("cv2", reason="a leitura do QR precisa do OpenCV")
    np = pytest.importorskip("numpy")

    selo = "RECFIR000000D0XB4FK298AWP401"
    html = com_selo(serventia, selo)
    svg = re.search(r"<svg.*?</svg>", html, re.S)
    assert svg, "a etiqueta saiu sem o QR"
    svg = svg.group(0)

    escala = float(re.search(r"scale\(([\d.]+)\)", svg).group(1))
    lado_mm = float(re.search(r'width="([\d.]+)mm"', svg).group(1))
    modulos = int(round(lado_mm / escala))
    caminho = re.search(r' d="([^"]+)"', svg).group(1)

    grade = np.zeros((modulos, modulos), dtype=np.uint8)
    x = y = 0.0
    for comando, args in re.findall(r"([MmhH])([-\d. ]*)", caminho):
        n = [float(v) for v in args.replace("-", " -").split()] if args.strip() else []
        if comando == "M":
            x, y = n[0], n[1]
        elif comando == "m":
            x, y = x + n[0], y + n[1]
        else:
            largura = n[0] if comando == "h" else n[0] - x
            for i in range(int(round(largura))):
                grade[int(y), int(round(x)) + i] = 1
            x += largura

    # O ENDERECO DA CONSULTA, medido no portal em 24/09/2026: a rota de
    # hash abre o selo validado; a query abre a tela de digitar.
    esperado = f"https://selo.tjma.jus.br/#/resumo/{selo}"
    for dpi in (203, 300):
        px = max(1, int(round(lado_mm * dpi / 25.4)) // modulos)
        desenho = np.kron(1 - grade, np.ones((px, px), dtype=np.uint8)) * 255
        borda = 4 * px          # a zona silenciosa que o decodificador exige
        tela = np.full((desenho.shape[0] + 2 * borda,
                        desenho.shape[1] + 2 * borda), 255, dtype=np.uint8)
        tela[borda:borda + desenho.shape[0], borda:borda + desenho.shape[1]] = desenho
        lido, *_ = cv2.QRCodeDetector().detectAndDecode(tela)
        assert lido == esperado, f"a {dpi} DPI o QR da rota não leu (leu {lido!r})"


# ------------------------------------------- os emolumentos na etiqueta


def _linha_de_valores(html: str):
    """O conteúdo da tira de valores, ou `None` se ela não saiu."""
    m = re.search(r'<div class="valores">(.*?)</div>', html, re.DOTALL)
    return m.group(1).strip() if m else None


def test_a_etiqueta_imprime_os_valores_que_o_selo_declara(serventia):
    """**PEDIDO DO OFICIAL EM 01/09/2026**: *«aplique a correção do selo (com
    emolumentos e demais informações) também para todos demais atos do
    cartório, inclusive etiqueta de reconhecimento de firma e autenticação de
    cópia»*.

    E o precedente é medido: nos **25.634** selos que esta casa imprimiu, o
    texto do selo traz `Total R$ … Emol R$ …` em **25.634**. Quem os escreve é
    o aparelho; o que faltava era o papel imprimir o que o selo declara.
    """
    s = serventia
    selo = "RECFIR000000D0XB4FK298AWP401"
    texto = ("Poder Judiciario - TJMA. Selo: " + selo + ", "
             "06/12/2021 14:38:30, Ato: 13.17.4, Parte(s): MARIA DA SILVA, "
             "Rec Firma: Semelhanca, Total R$ 18,11 Emol R$ 16,31 "
             "FERC R$ 0,50 FADEP R$ 0,65 FEMP R$ 0,65 "
             "Consulte em https://selo.tjma.jus.br")
    pagina = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post(f"/notas/reconhecimento/{s['rec']}",
                      data={"csrf_token": token, "acao": "selo", "selo": selo},
                      follow_redirects=True)
    # O TEXTO MORA NO RAZÃO DOS SELOS, e é de lá que o papel o lê — não se
    # remonta aqui o que o selador escreveu.
    #
    # **E ESCREVER A LINHA AQUI FOI O QUE MOSTROU UM BURACO**: o selo DIGITADO
    # À MÃO nesta tela grava só `nt_reconhecimentos.selo`; ele **não entra em
    # `sd_selos`**, e por isso a etiqueta dele sai sem valores — o que está
    # certo, porque o sistema não tem o texto. O caminho AUTOMÁTICO
    # (`ato_selado`) grava as duas coisas, e é o que este `INSERT` imita.
    # Achado em 01/09/2026, e é anterior a esta passada.
    con = sqlite3.connect(s["banco"])
    con.execute("""INSERT OR REPLACE INTO sd_selos(numero, texto, atribuicao,
                       tabela, ato_id, obtido_em)
                   VALUES (?,?,?,?,?,?)""",
                (selo, texto, "NOTAS", "nt_reconhecimentos", s["rec"],
                 "2026-09-01T10:00:00"))
    con.commit()
    con.close()

    # **O TESTE OLHA A LINHA, E NÃO O HTML INTEIRO.** A primeira versão
    # procurava «Total R$» na página toda e achou — num comentário meu dentro
    # do `<style>`, que o navegador recebe. Varredor que procura palavra solta
    # bate na própria prosa; é a sétima vez neste projeto.
    linha = _linha_de_valores(etiqueta(s).get_data(as_text=True))
    assert linha, "a linha de valores não saiu na tira"
    assert "Total R$ 18,11" in linha
    assert "Emol R$ 16,31" in linha
    assert "FADEP R$ 0,65" in linha, "o rótulo do papel é FADEP; a sigla é FADP"
    assert "FERRFIS" not in linha, (
        "rótulo sem valor é ruído: este selo não declara FERRFIS")


def test_selo_sem_texto_nao_poe_rotulos_secos_na_etiqueta(serventia):
    """Selo digitado à mão pode não ter texto no razão. A etiqueta sai com o
    número e **sem a linha** — e não com «Total R$» e nada depois."""
    s = serventia
    pagina = s["cliente"].get(f"/notas/reconhecimento/{s['rec']}").get_data(as_text=True)
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', pagina).group(1)
    s["cliente"].post(f"/notas/reconhecimento/{s['rec']}",
                      data={"csrf_token": token, "acao": "selo",
                            "selo": "RECFIR000000D0XB4FK298AWP401"},
                      follow_redirects=True)
    html = etiqueta(s).get_data(as_text=True)
    assert "RECFIR000000D0XB4FK298AWP401" in html
    assert _linha_de_valores(html) is None, (
        "sem texto no razão não há linha — e não uma linha de rótulos secos")
