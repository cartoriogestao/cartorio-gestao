"""AS TELAS DO TÍTULO do RCPJ/RTD — o caminho inteiro, do balcão ao papel.

POR QUE ELES EXISTEM SEPARADOS DOS DE DOMÍNIO
    «Função de domínio pronta que nenhuma tela chama» é o defeito que mais se
    repetiu neste projeto. E o oposto também já aconteceu: o relato #25 pedia
    **visualizar** os documentos da prenotação, `ri_documentos.e_imagem` foi
    escrita para decidir isso, a tela do RI põe `target="_blank"` — e a única
    rota que servia arquivo **baixava sempre**. Metade pronta, metade nunca
    ligada, e nenhum teste de domínio veria.

O QUE ESTES TESTES GUARDAM
      - as telas EXISTEM, abrem, e estão NO MENU;
      - elas mandam o `csrf_token` — dez formulários da casa não mandavam, e o
        balcão levou «bad request error» em 27/08/2026;
      - **o PDF abre NA TELA**, com `Content-Disposition: inline`, e o `.docx`
        continua baixando;
      - **o arquivo de OUTRO título não abre nesta ficha** — número trocado na
        barra mostraria o documento de outro protocolo, e ninguém desconfia de
        um documento que abre;
      - a recusa do domínio chega como frase em português, e não como HTTP 500;
      - **qualificar e registrar não são do balcão**;
      - a etiqueta conta as impressões e **recusa registro cancelado**;
      - e a tela diz, com todas as letras, que o sistema **não transmite** nada
        para a ONRTDPJ.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from io import BytesIO
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — notoriamente pesado (~47 testes web)
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
from navegador_de_teste import postar_e_seguir  # noqa: E402

import rg_titulo as TIT

SENHA = "Senha#12345"

# UM PDF DE VERDADE, e não um `.txt` com outro nome. A rota declara o tipo pela
# extensão; um arquivo que não é PDF passaria neste teste do mesmo jeito, mas o
# quadro da tela mostraria página em branco no balcão — e é justamente isso que
# o teste quer poder afirmar que não acontece.
PDF = (b"%PDF-1.4\n1 0 obj<</Type/Catalog/Pages 2 0 R>>endobj\n"
       b"2 0 obj<</Type/Pages/Kids[3 0 R]/Count 1>>endobj\n"
       b"3 0 obj<</Type/Page/Parent 2 0 R/MediaBox[0 0 200 200]>>endobj\n"
       b"trailer<</Root 1 0 R>>\n%%EOF\n")


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


def _imprimir(c, url, **kw):
    """A etiqueta é POST com o token desde o LX11 (M8 do LS01): GET que grava
    a contagem não passava pelo CSRF."""
    with c.session_transaction() as sessao:
        token = sessao["csrf_token"]
    return c.post(url, data={"csrf_token": token}, **kw)


def _sessao(cg_casa, papel: str = "ADMIN"):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, papel)
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


@pytest.fixture()
def s(cg_casa):
    return _sessao(cg_casa)


def _con(s) -> sqlite3.Connection:
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


def receber(s, **campos) -> int:
    """Recebe um título PELA TELA, e devolve o id. É o caminho do balcão."""
    atribuicao = campos.pop("atribuicao", TIT.RTD)
    html = s["c"].get(f"/rcpj-rtd/titulos/novo?atribuicao={atribuicao}"
                      ).get_data(as_text=True)
    dados = {"csrf_token": _token(html), "data_apresentacao": "2026-09-03",
             "apresentante": "ASSOCIAÇÃO X",
             "apresentante_documento": "00000010000127",
             "natureza": "Estatuto de associação", "forma": TIT.PAPEL}
    dados.update(campos)
    s["c"].post(f"/rcpj-rtd/titulos/novo?atribuicao={atribuicao}", data=dados,
                follow_redirects=True)
    con = _con(s)
    linha = con.execute("SELECT id FROM rg_titulos ORDER BY id DESC LIMIT 1"
                        ).fetchone()
    con.close()
    assert linha, "o título não entrou pela tela"
    return int(linha["id"])


def anexar(s, titulo_id: int, nome="titulo.pdf", conteudo=PDF) -> int:
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/arquivo",
                data={"csrf_token": _token(html),
                      "arquivo": (BytesIO(conteudo), nome)},
                content_type="multipart/form-data", follow_redirects=True)
    con = _con(s)
    linha = con.execute("SELECT id FROM attachments ORDER BY id DESC LIMIT 1"
                        ).fetchone()
    con.close()
    assert linha, "o arquivo não foi anexado"
    return int(linha["id"])


def qualificar(s, titulo_id: int, resultado=TIT.POSITIVA, **campos):
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "resultado": resultado}
    dados.update(campos)
    return s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/qualificar", data=dados,
                       follow_redirects=True)


def registrar(s, titulo_id: int, serie="TD_B", teor="Registro integral.",
              **extras):
    """Lavra pela tela. `extras` leva selo/cobrar/pagador/protocolo_id — o
    mesmo espírito do `_post` de `test_atribuicoes_web`: selo e custas são
    opcionais no formulário, e o teste posta o que quer conferir."""
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "serie": serie, "teor": teor}
    dados.update(extras)
    # Com selo, a lavratura leva à etiqueta por 307 (`navegador_de_teste`).
    return postar_e_seguir(s["c"], f"/rcpj-rtd/titulo/{titulo_id}/registrar", dados)


# --------------------------------------- as telas existem, e no menu


def test_a_fila_abre_nas_duas_atribuicoes(s):
    for atribuicao in TIT.ATRIBUICOES:
        r = s["c"].get(f"/rcpj-rtd/titulos?atribuicao={atribuicao}")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert TIT.NOME_DA_ATRIBUICAO[atribuicao] in html
        # As seis situações aparecem, mesmo em zero.
        for rotulo in TIT.SITUACOES.values():
            assert rotulo.split(" —")[0] in html


def test_as_duas_filas_estao_no_menu(s):
    """**O menu é onde o balcão acha o que fazer.** Rota sem item de menu é
    porta escondida — e a lista do menu já envelheceu duas vezes neste
    projeto."""
    html = s["c"].get("/rcpj-rtd/titulos").get_data(as_text=True)
    assert 'href="/rcpj-rtd/titulos?atribuicao=4"' in html
    assert 'href="/rcpj-rtd/titulos?atribuicao=3"' in html


def test_a_tela_de_receber_abre_e_manda_o_token(s):
    html = s["c"].get("/rcpj-rtd/titulos/novo").get_data(as_text=True)
    assert 'name="csrf_token"' in html
    assert 'name="data_apresentacao"' in html


def test_a_lista_vazia_diz_o_que_fazer(s):
    """Lista vazia que só mostra nada faz o operador achar que quebrou — foi o
    que custou três respostas na tela de assinaturas."""
    html = s["c"].get("/rcpj-rtd/titulos").get_data(as_text=True)
    assert "Nenhum título nesta lista" in html


# ------------------------------------------------ receber e protocolar


def test_receber_pela_tela_protocola_o_titulo(s):
    titulo_id = receber(s)
    con = _con(s)
    t = con.execute("SELECT * FROM rg_titulos WHERE id=?", (titulo_id,)).fetchone()
    lugar = con.execute("SELECT * FROM nu_lugares WHERE tabela='rg_titulos' "
                        "AND referencia=?", (titulo_id,)).fetchone()
    con.close()
    assert t["numero"] == 1
    assert t["situacao"] == TIT.APRESENTADO
    assert lugar, "o título não ocupou lugar no Livro de Protocolo"


def test_receber_abre_e_amarra_o_protocolo_geral(s):
    titulo_id = receber(s, telefone="99999-0000")
    con = _con(s)
    titulo = con.execute("SELECT * FROM rg_titulos WHERE id=?",
                         (titulo_id,)).fetchone()
    geral = con.execute("SELECT * FROM cx_protocolos WHERE id=?",
                        (titulo["protocolo_geral_id"],)).fetchone()
    con.close()
    assert geral["numero"].startswith("2026.09.")
    assert geral["atribuicao"] == "RTD"
    assert geral["interessado"] == "ASSOCIAÇÃO X"
    assert geral["telefone"] == "99999-0000"
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert geral["numero"] in html
    assert f"/caixa/protocolos/{geral['id']}" in html


def test_a_ficha_permite_completar_os_dados_e_sincroniza_o_geral(s):
    titulo_id = receber(s, apresentante="")
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    r = s["c"].post(
        f"/rcpj-rtd/titulo/{titulo_id}/editar",
        data={"csrf_token": _token(html), "apresentante": "ASSOCIAÇÃO Y",
              "natureza": "Ata de eleição", "serie": "TD_B",
              "forma": TIT.PAPEL, "vias": "2"},
        follow_redirects=True)
    assert r.status_code == 200
    con = _con(s)
    titulo = con.execute("SELECT * FROM rg_titulos WHERE id=?",
                         (titulo_id,)).fetchone()
    geral = con.execute("SELECT * FROM cx_protocolos WHERE id=?",
                        (titulo["protocolo_geral_id"],)).fetchone()
    con.close()
    assert titulo["apresentante"] == geral["interessado"] == "ASSOCIAÇÃO Y"
    assert titulo["natureza"] == geral["assunto"] == "Ata de eleição"


def test_a_recusa_do_dominio_vira_frase_e_nao_HTTP_500(s):
    """**Erro de regra não é HTTP 500** — a regra da casa, quebrada por mim em
    cinco rotas de uma vez no `cenprot_web`."""
    html = s["c"].get("/rcpj-rtd/titulos/novo?atribuicao=3").get_data(as_text=True)
    r = s["c"].post("/rcpj-rtd/titulos/novo?atribuicao=3",
                    data={"csrf_token": _token(html),
                          "data_apresentacao": "2026-09-03",
                          "serie": "TD_B"},   # livro do RTD numa tela de RCPJ
                    follow_redirects=True)
    assert r.status_code == 200
    assert "não é do" in r.get_data(as_text=True)


def test_a_ficha_do_titulo_abre_com_os_dados(s):
    titulo_id = receber(s)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "ASSOCIAÇÃO X" in html
    assert "Estatuto de associação" in html


# -------------------------------------- o arquivo, na tela e para baixar


def test_o_pdf_ABRE_NA_TELA_e_nao_baixa(s):
    """**É metade do pedido do oficial**: «analisar no visualizador de pdf
    direto no sistema». Até 03/09/2026 a única rota que servia arquivo mandava
    `as_attachment=True` — o navegador baixava, sempre."""
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id)
    r = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/arquivo/{anexo_id}")
    assert r.status_code == 200
    assert r.headers["Content-Type"].startswith("application/pdf")
    assert "inline" in r.headers.get("Content-Disposition", "")
    assert "attachment" not in r.headers.get("Content-Disposition", "")


def test_quem_mostra_manda_o_nosniff_e_a_politica(s):
    """**A lista decide o que se oferece; os cabeçalhos protegem o que se
    serviu.** Sem `nosniff` o navegador pode adivinhar o tipo pelo conteúdo e
    tratar como HTML um arquivo que dissemos ser PDF — e a lista teria sido
    para nada."""
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id)
    r = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/arquivo/{anexo_id}")
    assert r.headers.get("X-Content-Type-Options") == "nosniff"
    assert "sandbox" in r.headers.get("Content-Security-Policy", "")


def test_o_que_o_navegador_nao_desenha_volta_para_o_baixar(s):
    """Não é recusa: é o mesmo arquivo pelo caminho que funciona para ele. Uma
    tela em branco seria pior que o botão de baixar."""
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id, nome="minuta.docx", conteudo=b"PK\x03\x04")
    r = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/arquivo/{anexo_id}")
    assert r.status_code == 302
    assert f"/arquivo/{anexo_id}" in r.headers["Location"]


def test_o_arquivo_de_OUTRO_titulo_nao_abre_nesta_ficha(s):
    """**O quadro do visualizador monta o endereço a partir do título.** Sem a
    conferência, um número trocado na barra mostraria o documento de outro
    protocolo dentro desta ficha — e ninguém desconfia de um documento que
    abre."""
    a = receber(s)
    b = receber(s)
    anexo_de_a = anexar(s, a)
    r = s["c"].get(f"/rcpj-rtd/titulo/{b}/arquivo/{anexo_de_a}")
    assert r.status_code == 404


def test_a_ficha_mostra_o_quadro_do_pdf_e_o_botao_de_baixar(s):
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert f"/rcpj-rtd/titulo/{titulo_id}/arquivo/{anexo_id}" in html
    assert "<iframe" in html, "o PDF não ganhou o quadro do visualizador"
    assert f"/arquivo/{anexo_id}" in html, "sumiu o botão de baixar"


def test_sem_arquivo_a_ficha_pede_o_arquivo(s):
    titulo_id = receber(s)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "Nenhum arquivo anexado ainda" in html


def test_a_rota_geral_de_ver_tambem_serve_em_linha(s):
    """`/arquivo/<id>/ver` conserta o relato #25 na atribuição vizinha: a
    prenotação do RI já oferecia o link e a rota baixava."""
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id)
    r = s["c"].get(f"/arquivo/{anexo_id}/ver")
    assert r.status_code == 200
    assert "inline" in r.headers.get("Content-Disposition", "")


# ------------------------------------------------------- qualificar


def test_a_positiva_libera_o_bloco_de_registrar(s):
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "Lavrar o registro" in html


def test_a_negativa_sem_exigencia_volta_com_frase(s):
    titulo_id = receber(s)
    r = qualificar(s, titulo_id, TIT.NEGATIVA, exigencias="falta")
    assert r.status_code == 200
    assert "exigência" in r.get_data(as_text=True)


def test_a_negativa_oferece_a_nota_devolutiva(s):
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.NEGATIVA,
               exigencias="Falta a ata de eleição da diretoria.",
               prazo_ate="2026-09-20")
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert f"/rcpj-rtd/titulo/{titulo_id}/nota" in html


def test_a_nota_devolutiva_leva_as_exigencias_e_o_prazo(s):
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.NEGATIVA,
               exigencias="Falta a ata de eleição da diretoria.",
               prazo_ate="2026-09-20")
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/nota").get_data(as_text=True)
    assert "Falta a ata de eleição da diretoria." in html
    assert "EXIGÊNCIAS A CUMPRIR" in html
    assert "000000" in html, "a nota saiu sem a identificação da serventia"


def test_a_nota_sem_prazo_DIZ_que_nao_ha_prazo(s):
    """**Prazo em branco não se inventa.** Prazo errado num papel que a
    serventia assina é o apresentante perdendo direito por conta da tela."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.NEGATIVA,
               exigencias="Falta a ata de eleição da diretoria.")
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/nota").get_data(as_text=True)
    assert "não foi fixado prazo" in html


def test_titulo_sem_negativa_nao_tem_nota_devolutiva(s):
    titulo_id = receber(s)
    r = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/nota", follow_redirects=True)
    assert "não tem qualificação negativa" in r.get_data(as_text=True)


# --------------------------------------------------------- registrar


def test_registrar_pela_tela_lavra_o_ato(s):
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    r = registrar(s, titulo_id)
    assert r.status_code == 200
    con = _con(s)
    t = con.execute("SELECT * FROM rg_titulos WHERE id=?", (titulo_id,)).fetchone()
    ato = con.execute("SELECT * FROM rg_atos WHERE registro_id=?",
                      (t["registro_id"],)).fetchone()
    con.close()
    assert t["situacao"] == TIT.REGISTRADO
    assert ato["tipo"] == "REGISTRO" and ato["numero_ordem"] == 1


def test_registrar_sem_qualificar_volta_com_frase(s):
    titulo_id = receber(s)
    r = registrar(s, titulo_id)
    assert r.status_code == 200
    assert "qualificação positiva" in r.get_data(as_text=True)


def test_a_ficha_do_registrado_oferece_a_etiqueta(s):
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "/rcpj-rtd/ato/" in html and "Etiqueta" in html
    assert "em papel" in html, "a ficha não lembrou de colar a etiqueta"


# ---------------------------------------------------------- a etiqueta


def _ato_do(s, titulo_id: int) -> int:
    con = _con(s)
    linha = con.execute(
        """SELECT a.id FROM rg_atos a JOIN rg_titulos t ON t.registro_id = a.registro_id
            WHERE t.id = ? ORDER BY a.id""", (titulo_id,)).fetchone()
    con.close()
    return int(linha["id"])


def test_a_etiqueta_de_registro_usa_a_tira_100_por_30(s):
    """Registro e reconhecimento usam a mesma bobina física."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    html = _imprimir(s["c"], f"/rcpj-rtd/ato/{_ato_do(s, titulo_id)}/etiqueta"
                      ).get_data(as_text=True)
    assert "size: 100.0mm 30.0mm" in html or "size: 100mm 30mm" in html, html[:400]
    assert "Livro" in html and "fl." in html


def test_a_etiqueta_conta_as_impressoes(s):
    """**Segunda via de etiqueta é o mesmo selo colado em dois papéis**, e quem
    confere precisa ver que houve. A contagem sobe ao ABRIR a tela, porque
    abrir é a única forma de imprimir — botão que a pessoa tem de lembrar de
    apertar é botão que não é apertado."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    ato_id = _ato_do(s, titulo_id)
    _imprimir(s["c"], f"/rcpj-rtd/ato/{ato_id}/etiqueta")
    html = _imprimir(s["c"], f"/rcpj-rtd/ato/{ato_id}/etiqueta").get_data(as_text=True)
    assert "2ª impressão desta etiqueta" in html
    con = _con(s)
    ato = con.execute("SELECT * FROM rg_atos WHERE id=?", (ato_id,)).fetchone()
    con.close()
    assert ato["etiqueta_impressoes"] == 2
    assert ato["etiqueta_impressa_em"]


def test_a_etiqueta_de_registro_cancelado_e_recusada(s):
    """Etiqueta de registro cancelado colada num título é o ato valendo no
    mundo depois de ter sido desfeito no livro."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    ato_id = _ato_do(s, titulo_id)
    con = _con(s)
    with con:
        con.execute("UPDATE rg_registros SET situacao='CANCELADO' "
                    "WHERE id=(SELECT registro_id FROM rg_atos WHERE id=?)",
                    (ato_id,))
    con.close()
    r = _imprimir(s["c"], f"/rcpj-rtd/ato/{ato_id}/etiqueta", follow_redirects=True)
    assert "cancelado" in r.get_data(as_text=True)


def test_a_etiqueta_tem_ONDE_SER_AJUSTADA(s):
    """**Impressora térmica nunca encaixa de primeira** — é medição desta casa,
    escrita quando a etiqueta de firma nasceu. Entregar uma etiqueta nova sem
    tela de ajuste faria cada meio milímetro virar uma atualização do sistema,
    que é o defeito que aquela tela existe para impedir."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    html = _imprimir(s["c"], f"/rcpj-rtd/ato/{_ato_do(s, titulo_id)}/etiqueta"
                      ).get_data(as_text=True)
    assert "/rcpj-rtd/etiqueta/ajuste" in html
    r = s["c"].get("/rcpj-rtd/etiqueta/ajuste")
    assert r.status_code == 200
    ajuste = r.get_data(as_text=True)
    assert 'name="etiqueta_largura_mm"' in ajuste
    assert 'name="etiqueta_registro_corpo_pt"' in ajuste


def test_ajuste_fisico_do_registro_calibra_a_mesma_bobina_da_firma(s):
    html = s["c"].get("/rcpj-rtd/etiqueta/ajuste").get_data(as_text=True)
    s["c"].post("/rcpj-rtd/etiqueta/ajuste",
                data={"csrf_token": _token(html),
                      "etiqueta_altura_mm": "31"},
                follow_redirects=True)
    import etiqueta as ETQ
    gravadas = s["db"].get_settings
    assert ETQ.medidas_registro_rtdpj(gravadas)["etiqueta_altura_mm"] == 31.0
    assert ETQ.medidas(gravadas, ETQ.RECONHECIMENTO)["etiqueta_altura_mm"] == 31.0
    assert ETQ.medidas_registro_rtdpj(gravadas)["etiqueta_corpo_pt"] == 6.0


def test_medida_invalida_no_ajuste_volta_com_frase(s):
    """«10 mm» digitado com a unidade junto não pode parar a impressão do
    balcão nem gravar uma tira em branco."""
    html = s["c"].get("/rcpj-rtd/etiqueta/ajuste").get_data(as_text=True)
    r = s["c"].post("/rcpj-rtd/etiqueta/ajuste",
                    data={"csrf_token": _token(html),
                          "etiqueta_altura_mm": "40 mm"},
                    follow_redirects=True)
    assert "não é um número" in r.get_data(as_text=True)


def test_a_etiqueta_sem_selo_avisa_em_vez_de_calar(s):
    """Sem selo não há QR — um QR que aponta para consulta vazia é pior que
    nenhum, porque parece conferível e não é."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    html = _imprimir(s["c"], f"/rcpj-rtd/ato/{_ato_do(s, titulo_id)}/etiqueta"
                      ).get_data(as_text=True)
    assert "ainda está sem selo" in html


def _selo_externo_rtdpj(s, numero: str, *, texto: str,
                        cancelado_em=None, tabela=None, ato_id=None):
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO sd_selos
               (numero, texto, caminho, atribuicao, tabela, ato_id,
                obtido_em, obtido_por, cancelado_em)
               VALUES (?, ?, '/selo/rtdpj/atos-em-geral', 'RTDPJ', ?, ?,
                       '2026-09-10 10:30:00', 'BEATRIZ', ?)""",
            (numero, texto, tabela, ato_id, cancelado_em))
    con.close()


def test_gerador_de_etiquetas_externas_esta_no_menu_e_lista_o_razao(s):
    numero = "REGTER000000EXTERNO00000001"
    _selo_externo_rtdpj(
        s, numero,
        texto=(f"Poder Judiciário - TJMA. Selo: {numero}, 10/09/2026 10:30:00, "
               "Ato: 15.5.1, Parte(s): ASSOCIAÇÃO TESTE, Total R$ 20,00 "
               "Emol R$ 18,00 FERC R$ 0,50 FADEP R$ 0,75 FEMP R$ 0,75"))
    menu = s["c"].get("/rcpj-rtd/titulos?atribuicao=4").get_data(as_text=True)
    assert "/rcpj-rtd/etiquetas/selos-externos" in menu
    html = s["c"].get(
        "/rcpj-rtd/etiquetas/selos-externos?busca=ASSOCIAÇÃO"
    ).get_data(as_text=True)
    assert numero in html and "Ato: 15.5.1" in html
    assert 'name="selo"' in html
    assert 'name="selo_manual"' in html
    assert 'name="texto_registro"' in html


def test_gerador_manual_recebe_selo_e_texto_sem_gravar_ato_ou_selo(s):
    numero = "REGTER000000ABCDEFGHIJKL1234"
    tela = s["c"].get("/rcpj-rtd/etiquetas/selos-externos").get_data(as_text=True)
    con = _con(s)
    atos_antes = con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0]
    selos_antes = con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0]
    con.close()

    r = s["c"].post(
        "/rcpj-rtd/etiquetas/selos-externos",
        data={"csrf_token": _token(tela), "selo_manual": numero,
              "texto_registro": "Averbação n. 2\nAlteração da diretoria."})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert "size: 100.0mm 30.0mm" in html or "size: 100mm 30mm" in html
    assert numero in html
    assert "Averbação n. 2\nAlteração da diretoria." in html
    assert "REGISTRO/AVERBAÇÃO" in html

    con = _con(s)
    assert con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0] == atos_antes
    assert con.execute("SELECT COUNT(*) FROM sd_selos").fetchone()[0] == selos_antes
    con.close()


def test_gerador_manual_exige_o_texto_do_registro(s):
    tela = s["c"].get("/rcpj-rtd/etiquetas/selos-externos").get_data(as_text=True)
    r = s["c"].post(
        "/rcpj-rtd/etiquetas/selos-externos",
        data={"csrf_token": _token(tela),
              "selo_manual": "REGTER000000ABCDEFGHIJKL1234"},
        follow_redirects=True)
    assert "Escreva o texto do registro" in r.get_data(as_text=True)


def test_gerador_imprime_uma_tira_por_selo_sem_criar_ato(s):
    numeros = ["REGTER000000EXTERNO00000001", "REGTER000000EXTERNO00000002"]
    for i, numero in enumerate(numeros, 1):
        _selo_externo_rtdpj(
            s, numero,
            texto=(f"Poder Judiciário - TJMA. Selo: {numero}, "
                   f"10/09/2026 10:3{i}:00, Ato: 15.5.{i}, "
                   f"Parte(s): PARTE {i}, Total R$ 20,00 Emol R$ 18,00 "
                   "FERC R$ 0,50 FADEP R$ 0,75 FEMP R$ 0,75"))
    tela = s["c"].get("/rcpj-rtd/etiquetas/selos-externos").get_data(as_text=True)
    con = _con(s)
    antes = con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0]
    con.close()
    r = s["c"].post(
        "/rcpj-rtd/etiquetas/selos-externos",
        data={"csrf_token": _token(tela), "selo": numeros})
    html = r.get_data(as_text=True)
    assert r.status_code == 200
    assert html.count('class="etiqueta"') == 2
    assert "size: 100.0mm 30.0mm" in html or "size: 100mm 30mm" in html
    assert all(numero in html for numero in numeros)
    assert "Total R$ 20,00" in html and "SELO ELETRÔNICO" in html
    con = _con(s)
    depois = con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0]
    con.close()
    assert depois == antes


# ------------------------------------------------ a passagem pela Central


def test_o_titulo_que_NAO_veio_da_central_diz_isso(s):
    """**Tela que oferece «enviar» a quem não tem protocolo na Central** faria
    o escrevente clicar e não entender a recusa. Ela diz o que falta, e onde a
    fila de lá está.

    (Este teste chamava-se «a tela diz que o sistema não transmite», e a frase
    deixou de ser verdade no mesmo dia: o contrato da Central apareceu, e a
    integração foi construída. O que a tela diz agora é **de que lado o título
    está**.)"""
    titulo_id = receber(s, forma=TIT.ELETRONICO)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert "ONRTDPJ" in html
    assert "não veio da Central" in html
    assert "/rcpj-rtd/onrtdpj" in html, "não apontou para a fila da Central"


def test_registrar_a_passagem_guarda_a_linha(s):
    titulo_id = receber(s, forma=TIT.ELETRONICO)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/encaminhar",
                data={"csrf_token": _token(html), "sentido": TIT.RECEBIDO,
                      "protocolo_central": "2026.0001234"},
                follow_redirects=True)
    con = _con(s)
    linha = con.execute("SELECT * FROM rg_encaminhamentos WHERE titulo_id=?",
                        (titulo_id,)).fetchone()
    con.close()
    assert linha["protocolo_central"] == "2026.0001234"
    assert linha["central"] == "ONRTDPJ"


# ---------------------------------------------------------- encerrar


def test_encerrar_pela_tela_produz_a_situacao_terminal(s):
    """**A lição medida do E-Ofício**: lá `bitFinalizado` é 0 em 21.360 de
    21.360, e as cinco situações declaradas nunca foram exercitadas. Um
    protocolo que só abre é um diário."""
    titulo_id = receber(s)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/encerrar",
                data={"csrf_token": _token(html), "situacao": TIT.DEVOLVIDO,
                      "motivo": "O apresentante retirou o título no balcão."},
                follow_redirects=True)
    con = _con(s)
    t = con.execute("SELECT situacao FROM rg_titulos WHERE id=?",
                    (titulo_id,)).fetchone()
    con.close()
    assert t["situacao"] == TIT.DEVOLVIDO


# --------------------------------------------------------- quem entra


def test_qualificar_e_registrar_nao_sao_do_balcao(cg_casa):
    """**Qualificar é ato registral**, e o registro é efeito dela. É a mesma
    separação do envio às Centrais e da configuração da ajuda: consultar abre,
    decidir não. **A guarda é no servidor, e não no menu** — tirar o botão e
    deixar a rota de pé esconde a porta sem trancá-la."""
    s = _sessao(cg_casa, papel="USER")
    titulo_id = receber(s)
    # O TOKEN VAI JUNTO, E ISSO É O QUE FAZ O TESTE VALER. Sem ele a resposta é
    # **400 do CSRF**, que é uma recusa por outro motivo — e um teste que
    # aceitasse o 400 continuaria verde no dia em que a guarda de papel
    # sumisse. Ele sai de uma tela que o escrevente pode abrir: o token é da
    # sessão, e não do formulário.
    token = _token(s["c"].get("/rcpj-rtd/titulos/novo").get_data(as_text=True))
    for caminho in ("qualificar", "registrar", "encerrar"):
        r = s["c"].post(f"/rcpj-rtd/titulo/{titulo_id}/{caminho}",
                        data={"csrf_token": token})
        assert r.status_code in (302, 403), (
            f"a rota /{caminho} aceitou quem não decide (HTTP "
            f"{r.status_code})")


def test_o_balcao_recebe_titulo_e_anexa_arquivo(cg_casa):
    """O que é do balcão continua sendo: receber o título e anexar o papel."""
    s = _sessao(cg_casa, papel="USER")
    titulo_id = receber(s)
    anexo_id = anexar(s, titulo_id)
    assert anexo_id
    r = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}/arquivo/{anexo_id}")
    assert r.status_code == 200


def test_toda_tela_que_grava_manda_o_csrf_token(s):
    """Dez formulários da casa não mandavam, e o balcão levou «bad request
    error» em 27/08/2026. Os testes montam o POST com o token na mão: eles
    provam que a ROTA funciona, e não que a TELA manda o que a rota exige."""
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id)
    for caminho in ("/rcpj-rtd/titulos/novo", f"/rcpj-rtd/titulo/{titulo_id}"):
        html = s["c"].get(caminho).get_data(as_text=True)
        formularios = re.findall(r"<form[^>]*method=[\"']post[\"'].*?</form>",
                                 html, re.DOTALL | re.IGNORECASE)
        assert formularios, f"{caminho} não tem formulário de gravar"
        for f in formularios:
            assert 'name="csrf_token"' in f, (
                f"formulário sem token em {caminho}: {f[:120]}")


# ---------------------------------------------- selo e custas no título
#
# Espelho do espírito de `test_atribuicoes_web`: o selo é opcional porque o
# selador é máquina da rede local e cai; cobrar sem caixa aberto desfaz o
# registro inteiro — não pode sobrar ato lavrado com cobrança que falhou.


SELO_BOM = "AVESVD000000NARRKWVNJCRSVO21"


def _com_servico(s, codigo=1, codigo_tj="15.10.2", total="53,58"):
    """Um serviço com preço no banco da sessão.

    `15.10.2` é o primeiro item de `itens_de_custa_do_ato('/selo/rtdpj/
    atos-em-geral')` — o caminho do REGISTRO em `rg_atos`. Sem este código
    TJ na receita, o checkbox de cobrar não aparece na ficha.
    """
    con = _con(s)
    with con:
        con.execute("INSERT OR IGNORE INTO cx_vigencias(codigo, vigente) VALUES (1,1)")
        con.execute("""INSERT OR IGNORE INTO cx_servicos(codigo, codigo_tj, descricao)
                       VALUES (?,?, 'Serviço de teste RTDPJ')""",
                    (codigo, codigo_tj))
        con.execute("""INSERT INTO cx_servico_valores(servico, vigencia,
                           emolumentos, ferc, femp, fadep, ferrfis, total)
                       VALUES (?,1,?, '0,00','0,00','0,00','0,00', ?)""",
                    (codigo, total, total))
    con.close()
    return codigo


def _abrir_caixa(s) -> int:
    """O caixa do operador, aberto — sem ele não se cobra.

    O nome TEM de ser o `full_name` do create_user da sessão
    («MARIO EXEMPLO DOS SANTOS», com T). `_caixa_aberto` filtra por
    `usuario_nome()`, e typo no nome = teste que passa fingindo caixa e
    falha no balcão de verdade.
    """
    con = _con(s)
    with con:
        con.execute(
            """INSERT INTO cx_caixas(data, operador_nome, aberto_em, situacao)
               VALUES ('2026-09-03','MARIO EXEMPLO DOS SANTOS',
                       '2026-09-03T08:00:00','ABERTO')""")
        cid = con.execute("SELECT id FROM cx_caixas").fetchone()[0]
    con.close()
    return cid


def test_bloco_registrar_oferece_selo_e_cobrar(s):
    """A ficha QUALIFICADA oferece selo e o quadro de cobrar — o buraco
    que esta fatia fecha: /novo já tinha, o título não."""
    _com_servico(s)  # sem 15.10.2 na receita o checkbox não aparece
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = s["c"].get(f"/rcpj-rtd/titulo/{titulo_id}").get_data(as_text=True)
    assert 'name="selo"' in html
    assert "Cobrar no caixa" in html
    assert 'name="cobrar"' in html


def test_registrar_com_selo_amarra_ao_rg_ato(s):
    # o selo digitado é o objeto aqui; a cobertura do selo pago (A9) tem teste próprio
    s["db"].set_settings({"selo_trava_caixa": "DESLIGADA"})
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = registrar(s, titulo_id, selo=SELO_BOM).get_data(as_text=True)
    assert SELO_BOM in html or "Selo" in html
    con = _con(s)
    linha = con.execute("SELECT * FROM sd_selos WHERE numero=?",
                        (SELO_BOM,)).fetchone()
    assert linha is not None
    assert linha["tabela"] == "rg_atos"
    ato = con.execute("SELECT * FROM rg_atos WHERE id=?",
                      (linha["ato_id"],)).fetchone()
    assert ato["selo"] == SELO_BOM
    con.close()


def test_a_etiqueta_sai_mesmo_sem_o_razao_dos_selos(s):
    """`_texto_do_selo` perdoa a `sd_selos` que falta (`except sqlite3.Error`).
    No PostgreSQL o erro chega pelo `bd_nativo`, já traduzido, numa conexão
    própria e fora de transação — a etiqueta sai, só sem a linha de valores
    (revisão do L043). O banco é do módulo: a tabela volta no fim."""
    from bd_nativo import Banco
    # o selo digitado é o objeto aqui; a cobertura do selo pago (A9) tem teste próprio
    s["db"].set_settings({"selo_trava_caixa": "DESLIGADA"})
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    registrar(s, titulo_id, selo=SELO_BOM)
    ato_id = _ato_do(s, titulo_id)
    con = _con(s)
    bd = Banco(con)
    bd.escrever("ALTER TABLE sd_selos RENAME TO sd_selos_fora_do_teste")
    con.commit()
    try:
        r = _imprimir(s["c"], f"/rcpj-rtd/ato/{ato_id}/etiqueta")
        assert r.status_code == 200
        html = r.get_data(as_text=True)
        assert SELO_BOM in html and 'class="valores"' not in html
    finally:
        bd.escrever("ALTER TABLE sd_selos_fora_do_teste RENAME TO sd_selos")
        con.commit()
        con.close()


def test_selo_de_outra_serventia_desfaz_o_registro_do_titulo(s):
    # A transação volta atrás: não pode sobrar registro lavrado com selo
    # recusado — a mesma regra do /rcpj-rtd/novo.
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = registrar(s, titulo_id,
                     selo="AVESVD999999NARRKWVNJCRSVO21").get_data(as_text=True)
    assert "não é desta serventia" in html
    con = _con(s)
    t = con.execute("SELECT * FROM rg_titulos WHERE id=?",
                    (titulo_id,)).fetchone()
    assert t["situacao"] == TIT.QUALIFICADO
    assert t["registro_id"] is None
    assert con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0] == 0
    con.close()


def test_registrar_marcando_cobrar_lanca_no_caixa(s):
    servico = _com_servico(s)
    caixa_id = _abrir_caixa(s)
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = registrar(s, titulo_id, cobrar=str(servico),
                     pagador="ASSOCIAÇÃO X").get_data(as_text=True)
    assert "Lançado no caixa" in html
    con = _con(s)
    linha = con.execute(
        "SELECT * FROM cx_lancamentos WHERE origem='ATO'").fetchone()
    assert linha is not None
    assert linha["caixa_id"] == caixa_id
    assert linha["pagador"] == "ASSOCIAÇÃO X"
    con.close()


def test_sem_caixa_aberto_nao_cobra_e_titulo_continua_qualificado(s):
    # Sem caixa, marcar cobrar desfaz o registro inteiro — não sobra
    # registro_id no título nem ato no livro.
    servico = _com_servico(s)
    titulo_id = receber(s)
    qualificar(s, titulo_id, TIT.POSITIVA)
    html = registrar(s, titulo_id,
                     cobrar=str(servico)).get_data(as_text=True)
    assert "não tem caixa aberto" in html
    con = _con(s)
    t = con.execute("SELECT * FROM rg_titulos WHERE id=?",
                    (titulo_id,)).fetchone()
    assert t["situacao"] == TIT.QUALIFICADO
    assert t["registro_id"] is None
    assert con.execute("SELECT COUNT(*) FROM rg_atos").fetchone()[0] == 0
    con.close()
