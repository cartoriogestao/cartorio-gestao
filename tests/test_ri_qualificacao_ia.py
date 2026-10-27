"""A qualificação assistida do RI — 26/10/2026.

    A IA cruza o título apresentado, a guia do ITBI e a matrícula e RASCUNHA a
    nota devolutiva (as exigências, cada uma com fundamento), para o oficial ou
    o escrevente revisar, editar e assinar. A qualificação é ato privativo do
    oficial: a IA não decide, não emite nota e não devolve título.

A IA AQUI É DE MENTIRA: ela guarda o que recebeu e devolve o rascunho no formato
combinado. Nenhum teste fala com o provedor de verdade.

O QUE ESTES TESTES PROTEGEM
    1. O que sobe: o título e o ITBI inteiros, a ficha da matrícula, a lista de
       conferência da espécie, o Opus no esforço alto e o esquema novo.
    2. A régua literal: o trecho que está escrito sai conferido; o inventado sai
       marcado; o do digitalizado manda conferir no papel — a não ser que a
       revisão já tenha guardado a leitura dele; a exigência por ausência não
       tem trecho.
    3. A IA não decide: depois do rascunho não há nota, nem qualificação, e a
       prenotação continua como estava.
    4. Só sobem os documentos daquela prenotação.
    5. SANDBOX, interruptor desligado e falta de chave: o botão diz por quê, e
       nada é pedido.
    6. «Levar para a nota devolutiva» só PREENCHE o formulário; quem emite é a
       rota de sempre — e a nota emitida fica ligada ao rascunho.
    7. Recusa do modelo e o simulador do SANDBOX viram ERRO com a frase.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import agente_provedores as AP        # noqa: E402
import ri_qualificacao_ia as QIA      # noqa: E402

# O ITBI DIGITALIZADO: um PDF sem texto (só a página).
PDF_SEM_TEXTO = (b"%PDF-1.4\n1 0 obj << /Type /Catalog >> endobj\ntrailer << /Root 1 0 R >>\n"
                 b"%%EOF\n")


def _pdf_com_texto(linhas: list[str]) -> bytes:
    """Um PDF de uma página com texto digital — o que `pypdfium2` lê."""
    def esc(s):
        return s.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    conteudo = ("BT /F1 11 Tf 50 780 Td 14 TL "
                + " ".join(f"({esc(l)}) '" for l in linhas) + " ET")
    objs = ["<< /Type /Catalog /Pages 2 0 R >>",
            "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
            "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
            "/Resources << /Font << /F1 5 0 R >> >> /Contents 4 0 R >>",
            f"<< /Length {len(conteudo)} >>\nstream\n{conteudo}\nendstream",
            "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    saida = b"%PDF-1.4\n"
    posicoes = []
    for i, o in enumerate(objs, 1):
        posicoes.append(len(saida))
        saida += f"{i} 0 obj\n{o}\nendobj\n".encode("latin-1")
    xref = len(saida)
    saida += f"xref\n0 {len(objs) + 1}\n0000000000 65535 f \n".encode()
    for p in posicoes:
        saida += f"{p:010d} 00000 n \n".encode()
    saida += (f"trailer << /Size {len(objs) + 1} /Root 1 0 R >>\nstartxref\n{xref}\n"
              "%%EOF\n").encode()
    return saida


ESCRITURA = _pdf_com_texto(["ESCRITURA PUBLICA DE COMPRA E VENDA",
                            "vendedor JOSE EXEMPLO, casado com CARLA EXEMPLO",
                            "comprador MARIO EXEMPLO",
                            "imovel objeto da matricula 777, lote 12 da quadra 3"])

RASCUNHO = {
    "especie_do_titulo": "Escritura pública de compra e venda",
    "exigencias": [
        {"exigencia": "Apresentar a anuência do cônjuge do vendedor",
         "fundamento": "CC, art. 1.647, I", "documento": "escritura.pdf", "pagina": "1",
         "trecho": "vendedor JOSE EXEMPLO, casado com CARLA EXEMPLO"},
        {"exigencia": "Retificar o nome do comprador",
         "fundamento": "Lei 6.015/1973, art. 176", "documento": "escritura.pdf",
         "pagina": "1", "trecho": "comprador JOAO INVENTADO"},
        {"exigencia": "Apresentar a certidão de casamento do vendedor",
         "fundamento": "fundamento a conferir pelo oficial", "documento": "",
         "pagina": "", "trecho": ""},
        {"exigencia": "Esclarecer a divergência de valor na guia do ITBI",
         "fundamento": "Lei 6.015/1973, art. 289", "documento": "itbi.pdf", "pagina": "1",
         "trecho": "guia 2026/123 valor venal 50.000,00"},
    ],
    "conferidos": [
        {"item": "o imóvel do título é o desta matrícula", "documento": "matrícula",
         "trecho": "lote 12 da quadra 3"},
    ],
    "duvidas": ["a consulta à CNIB é do balcão"],
    "nao_lidos": [],
    "observacoes": "",
}


class IA:
    """O provedor de mentira: guarda cada pedido e responde o rascunho."""

    def __init__(self, resposta=None, parou="end_turn", texto=None):
        self.resposta = resposta or RASCUNHO
        self.parou = parou
        self.texto = texto
        self.pedidos: list[dict] = []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida, **resto):
        self.pedidos.append({"sistema": sistema, "conversa": conversa, "modelo": modelo,
                             **resto})
        texto = self.texto if self.texto is not None else json.dumps(self.resposta)
        return {"texto": texto, "parou": self.parou, "entrada": 3000, "saida": 400,
                "modelo": modelo}


# ------------------------------------------------------------- a bancada


@pytest.fixture()
def casa(cg_casa_logada):
    return cg_casa_logada


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _anexar(casa, entidade: str, entidade_id: int, nome: str, dados: bytes) -> int:
    caminho = casa["dados"] / f"{entidade}-{entidade_id}-{nome}"
    caminho.write_bytes(dados)
    con = _con(casa)
    with con:
        aid = int(con.execute(
            """INSERT INTO attachments (entity_type, entity_id, original_name, stored_name,
                   stored_path, sha256, size_bytes, uploaded_at)
               VALUES (?,?,?,?,?,?,?,?)""",
            (entidade, entidade_id, nome, caminho.name, str(caminho),
             hashlib.sha256(dados + nome.encode()).hexdigest(), len(dados),
             "2026-10-26T10:00")).lastrowid)
    con.close()
    return aid


def _prenotacao(casa, numero=11800, com_matricula=True) -> tuple[int | None, int]:
    con = _con(casa)
    with con:
        mid = None
        if com_matricula:
            mid = int(con.execute(
                """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao, tipo_ficha,
                       teor, criado_em)
                   VALUES ('777', '2', '2', 'ATIVO', 'ESTRUTURADA',
                           'IMÓVEL: lote 12 da quadra 3, Cidade Exemplo. PROPRIETÁRIO: JOSE EXEMPLO.',
                           '2026-10-01T10:00')""").lastrowid)
        pid = int(con.execute(
            """INSERT INTO ri_protocolos (numero, livro, data_prenotacao, natureza_titulo,
                   matricula_id, data_limite, situacao, criado_em)
               VALUES (?, '1A', '2026-10-26', 'Escritura de compra e venda', ?,
                       '2026-11-24', 'ABERTO', '2026-10-26T09:00')""",
            (numero, mid)).lastrowid)
    con.close()
    return mid, pid


def _titulo_e_itbi(casa, pid) -> tuple[int, int]:
    return (_anexar(casa, "RI_PROTOCOLO", pid, "escritura.pdf", ESCRITURA),
            _anexar(casa, "RI_PROTOCOLO", pid, "itbi.pdf", PDF_SEM_TEXTO))


def _pedir_e_executar(casa, pid, anexos, ia, **kw) -> int:
    con = _con(casa)
    with con:
        pedido = QIA.pedir(con, pid, anexos_ids=anexos, usuario="MARIO", **kw)
    con.close()
    QIA.executar(casa["banco"], casa["dados"], pedido, conversar=ia)
    return pedido


def _pedido(casa, pedido_id) -> dict:
    con = _con(casa)
    p = QIA.mostrar(con, pedido_id)
    con.close()
    return p


def _token(html: str) -> str:
    return re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html).group(1)


# ------------------------------------------------------------- o que sobe


def test_sobem_o_titulo_o_itbi_a_ficha_e_a_lista_e_volta_o_rascunho(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    ia = IA()
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], ia, especie="R-COMPRA-VENDA",
                               instrucao="confira a outorga conjugal")
    p = _pedido(casa, pedido)
    assert p["situacao"] == QIA.PRONTA, p.get("erro")

    enviado = ia.pedidos[0]
    assert enviado["modelo"] == "claude-opus-5-5"
    assert enviado["extras"]["output_config"]["effort"] == "high"
    esquema = enviado["extras"]["output_config"]["format"]["schema"]
    assert set(esquema["properties"]["exigencias"]["items"]["required"]) == {
        "exigencia", "fundamento", "documento", "pagina", "trecho"}
    assert enviado["finalidade"] == "ri_qualificacao_ia" and enviado["mascarado"] is False
    turno = enviado["conversa"][0]
    assert [d["mime"] for d in turno["documentos"]] == ["application/pdf"] * 2
    assert "MATRÍCULA nº 777" in turno["texto"] and "lote 12 da quadra 3" in turno["texto"]
    assert "Prenotação nº 11800" in turno["texto"]
    assert "LISTA DE CONFERÊNCIA DA CASA" in turno["texto"]
    assert "recolhimento do ITBI" in turno["texto"]
    assert "confira a outorga conjugal" in turno["texto"]
    assert "NÃO decide" in enviado["sistema"] and "ITBI" in enviado["sistema"]


# ------------------------------------------------------------- a régua literal


def test_cada_trecho_sai_com_a_marca_do_que_se_conferiu(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    p = _pedido(casa, _pedir_e_executar(casa, pid, [escritura, itbi], IA()))
    marcas = [x["citacao"] for x in p["resultado"]["exigencias"]]
    assert marcas == [QIA.ESCRITO, QIA.NAO_ACHADO, QIA.FALTA, QIA.SEM_TEXTO]
    assert p["resultado"]["exigencias"][0]["conferido_em"] == "escritura.pdf"
    # o trecho da ficha confere contra a matrícula que subiu ao modelo
    assert p["resultado"]["conferidos"][0]["citacao"] == QIA.ESCRITO
    assert p["resultado"]["conferidos"][0]["conferido_em"] == "matrícula"
    assert p["resultado"]["sem_texto_para_conferir"] == ["itbi.pdf"]


def test_a_leitura_ja_guardada_pela_revisao_confere_o_digitalizado(casa):
    import revisao_anexos as RA
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    con = _con(casa)
    with con:
        RA.init_schema(con)
        sha = con.execute("SELECT sha256 FROM attachments WHERE id = ?", (itbi,)).fetchone()[0]
        con.execute("""INSERT INTO rv_anexos_lidos (sha256, nome, paginas, transcricao,
                           situacao) VALUES (?, 'itbi.pdf', 1, ?, 'LIDO')""",
                    (sha, "[página 1] GUIA DE ITBI guia 2026/123 valor venal 50.000,00"))
    con.close()
    p = _pedido(casa, _pedir_e_executar(casa, pid, [escritura, itbi], IA()))
    ultima = p["resultado"]["exigencias"][3]
    assert ultima["citacao"] == QIA.ESCRITO and ultima["conferido_em"] == "itbi.pdf"
    assert p["resultado"]["sem_texto_para_conferir"] == []


# ------------------------------------------------------------- a IA não decide


def test_o_rascunho_nao_emite_nota_nem_qualifica_nem_devolve(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    _pedir_e_executar(casa, pid, [escritura, itbi], IA())
    con = _con(casa)
    notas = con.execute("SELECT COUNT(*) FROM ri_notas_devolutivas WHERE protocolo_id = ?",
                        (pid,)).fetchone()[0]
    quals = con.execute("SELECT COUNT(*) FROM ri_qualificacoes WHERE protocolo_id = ?",
                        (pid,)).fetchone()[0]
    situacao = con.execute("SELECT situacao FROM ri_protocolos WHERE id = ?",
                           (pid,)).fetchone()[0]
    con.close()
    assert (notas, quals, situacao) == (0, 0, "ABERTO")


def test_so_sobem_os_documentos_daquela_prenotacao(casa):
    _, pid = _prenotacao(casa)
    _titulo_e_itbi(casa, pid)
    _, outra = _prenotacao(casa, numero=11801, com_matricula=False)
    de_outra = _anexar(casa, "RI_PROTOCOLO", outra, "outro.pdf", ESCRITURA)
    con = _con(casa)
    with pytest.raises(QIA.QualificacaoIAError, match="não é desta prenotação"):
        QIA.pedir(con, pid, anexos_ids=[de_outra])
    with pytest.raises(QIA.QualificacaoIAError, match="ao menos um documento"):
        QIA.pedir(con, pid, anexos_ids=[])
    con.close()


# ------------------------------------------------------------- o portão


def test_no_sandbox_desligada_ou_sem_chave_o_botao_diz_por_que(casa, monkeypatch):
    import centrais_trava_sandbox as TRAVA
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)

    monkeypatch.setattr(TRAVA, "e_sandbox", lambda: True)
    html = casa["c"].get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert 'id="qualificacao-ia-bloqueio"' in html and "SANDBOX" in html
    assert "Pedir a qualificação assistida</button>" not in html
    r = casa["c"].post(f"/registro-imoveis/protocolo/{pid}/qualificacao-ia/pedir",
                       data={"csrf_token": _token(html), "anexo": [str(escritura)]})
    assert r.status_code == 302
    monkeypatch.setattr(TRAVA, "e_sandbox", lambda: False)

    casa["db"].set_settings({QIA.CHAVE_LIGADA: "0"})
    con = _con(casa)
    assert "desligada" in QIA.por_que_nao(con, casa["dados"])
    casa["db"].set_settings({QIA.CHAVE_LIGADA: "1"})
    assert QIA.por_que_nao(con, casa["dados"]) is None
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: False)
    assert "chave do Claude" in QIA.por_que_nao(con, casa["dados"])
    assert con.execute("SELECT COUNT(*) FROM ri_qualificacao_ia").fetchone()[0] == 0
    con.close()


def test_o_quadro_aparece_no_protocolo_e_o_pedido_entra_em_segundo_plano(casa, monkeypatch):
    # 27/10/2026, pergunta do oficial: «nao pode ser positiva e negativa? nao eh
    # melhor ficar no protocolo?» — o quadro saiu da tela da nota e foi para a
    # seção «Qualificação» do protocolo, logo depois dos dois botões de sempre.
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(QIA, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    html = casa["c"].get(f"/registro-imoveis/protocolo/{pid}").get_data(as_text=True)
    assert 'id="qualificacao-ia"' in html and "escritura.pdf" in html
    assert "sem máscara" in html and "positiva ou negativa" in html
    assert html.index('id="qualificar-positiva"') < html.index('id="qualificacao-ia"')
    # a tela da nota não monta mais o quadro: aponta para o protocolo
    nota = casa["c"].get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
    assert 'id="qualificacao-ia"' not in nota and "Qualificação do protocolo" in nota
    # a espécie sugerida pela natureza do título
    assert 'value="R-COMPRA-VENDA" selected' in html
    r = casa["c"].post(f"/registro-imoveis/protocolo/{pid}/qualificacao-ia/pedir", data={
        "csrf_token": _token(html), "anexo": [str(escritura), str(itbi)],
        "especie": "R-COMPRA-VENDA"})
    assert r.status_code == 302
    con = _con(casa)
    linha = con.execute("SELECT * FROM ri_qualificacao_ia WHERE protocolo_id = ?",
                        (pid,)).fetchone()
    con.close()
    assert linha and comecados == [linha["id"]] and linha["especie"] == "R-COMPRA-VENDA"


# ------------------------------------------------------------- levar à nota


def test_levar_so_preenche_e_a_rota_de_sempre_emite_e_liga(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], IA())

    pagina = casa["c"].get(f"/registro-imoveis/qualificacao-ia/{pedido}").get_data(as_text=True)
    assert "trecho NÃO está escrito no documento" in pagina
    assert "Levar para a nota devolutiva" in pagina
    r = casa["c"].post(f"/registro-imoveis/qualificacao-ia/{pedido}/levar", data={
        "csrf_token": _token(pagina), "escolhida": ["0", "2"],
        "texto_0": "Apresentar a anuência de CARLA EXEMPLO (EDITADA À MÃO).",
        "texto_2": ""})
    assert r.status_code == 302 and f"qualificacao={pedido}" in r.headers["Location"]

    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM ri_notas_devolutivas").fetchone()[0] == 0
    con.close()
    nota = casa["c"].get(f"/registro-imoveis/protocolo/{pid}/nota?qualificacao={pedido}"
                         ).get_data(as_text=True)
    caixa = re.search(r'<textarea name="exigencias"[^>]*>(.*?)</textarea>', nota, re.S).group(1)
    assert "EDITADA À MÃO" in caixa
    assert "certidão de casamento do vendedor. Fundamento: fundamento a conferir" in caixa
    assert "JOAO INVENTADO" not in caixa
    assert f'name="qualificacao_ia_id" value="{pedido}"' in nota

    # quem emite é a rota de sempre, com o que a pessoa deixou no formulário
    r = casa["c"].post(f"/registro-imoveis/protocolo/{pid}/nota", data={
        "csrf_token": _token(nota), "exigencias": caixa.replace("&#39;", "'"),
        "qualificacao_ia_id": str(pedido), "data_nota": "2026-10-26"})
    assert r.status_code == 302
    con = _con(casa)
    n = con.execute("SELECT * FROM ri_notas_devolutivas WHERE protocolo_id = ?",
                    (pid,)).fetchone()
    ligado = con.execute("SELECT nota_id FROM ri_qualificacao_ia WHERE id = ?",
                         (pedido,)).fetchone()[0]
    con.close()
    assert n and len(json.loads(n["exigencias"])) == 2 and ligado == n["id"]
    # o mesmo rascunho não vai a uma segunda nota, e o formulário volta vazio
    con = _con(casa)
    with pytest.raises(QIA.QualificacaoIAError, match="já foram para uma nota"):
        QIA.levar(con, pedido, [(0, "")], usuario="MARIO")
    assert QIA.preenchimento(con, pedido, pid) is None
    con.close()


def test_sem_exigencia_marcada_nao_se_leva_nada(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], IA())
    con = _con(casa)
    with pytest.raises(QIA.QualificacaoIAError, match="ao menos uma exigência"):
        QIA.levar(con, pedido, [], usuario="MARIO")
    with pytest.raises(QIA.QualificacaoIAError, match="não é deste pedido"):
        QIA.levar(con, pedido, [(99, "x")], usuario="MARIO")
    con.close()


# ------------------------------------------- positiva ou negativa (27/10/2026)
#
# Pergunta do oficial: «qualificacao assistida nao pode ser positiva e
# negativa?». O rascunho aponta um dos dois caminhos e só preenche o formulário
# daquele caminho; quem qualifica continua sendo a rota de sempre.

TITULO_EM_ORDEM = {
    "especie_do_titulo": "Escritura pública de compra e venda",
    "exigencias": [],
    "conferidos": [
        {"item": "o comprador do título é o da qualificação", "documento": "escritura.pdf",
         "trecho": "comprador MARIO EXEMPLO"},
        {"item": "o imóvel do título é o desta matrícula", "documento": "matrícula",
         "trecho": "lote 12 da quadra 3"},
    ],
    "duvidas": [],
    "nao_lidos": [],
    "observacoes": "",
}


@pytest.mark.parametrize("resultado,esperado", [
    ({"exigencias": [{"exigencia": "Apresentar x"}], "conferidos": []}, QIA.SUGERE_NEGATIVA),
    ({"exigencias": [], "conferidos": [{"item": "a", "citacao": "ESCRITO"}]},
     QIA.SUGERE_POSITIVA),
    ({"exigencias": [], "conferidos": [{"item": "a", "citacao": "ESCRITO"}],
      "duvidas": ["CNIB"]}, QIA.SUGERE_DECIDIR),
    ({"exigencias": [], "conferidos": [{"item": "a", "citacao": "ESCRITO"}],
      "nao_lidos": ["itbi.pdf, ilegível"]}, QIA.SUGERE_DECIDIR),
    ({"exigencias": [], "conferidos": [{"item": "a", "citacao": "ESCRITO"}],
      "sem_texto_para_conferir": ["itbi.pdf"]}, QIA.SUGERE_DECIDIR),
    ({"exigencias": [], "conferidos": [{"item": "a", "citacao": "NAO_ACHADO"}]},
     QIA.SUGERE_DECIDIR),
    ({"exigencias": [], "conferidos": []}, QIA.SUGERE_DECIDIR),
])
def test_o_rascunho_aponta_positiva_negativa_ou_a_decidir(resultado, esperado):
    assert QIA.sugestao({"resultado": resultado})["resultado"] == esperado


def test_o_rascunho_com_exigencia_aponta_a_nota_e_nao_preenche_a_positiva(casa):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], IA())
    assert _pedido(casa, pedido)["sugestao"]["resultado"] == QIA.SUGERE_NEGATIVA
    con = _con(casa)
    assert QIA.preenchimento_positiva(con, pedido, pid) is None
    with con:
        assert QIA.ligar_a_positiva(con, pedido, pid, 999) is False
    con.close()
    pagina = casa["c"].get(f"/registro-imoveis/qualificacao-ia/{pedido}").get_data(as_text=True)
    assert "aponta a qualificação negativa" in pagina
    assert "Levar para a qualificação positiva" not in pagina


def test_titulo_em_ordem_leva_a_fundamentacao_a_positiva_e_a_rota_de_sempre_liga(casa):
    _, pid = _prenotacao(casa)
    escritura = _anexar(casa, "RI_PROTOCOLO", pid, "escritura.pdf", ESCRITURA)
    pedido = _pedir_e_executar(casa, pid, [escritura], IA(resposta=TITULO_EM_ORDEM))
    p = _pedido(casa, pedido)
    assert p["sugestao"]["resultado"] == QIA.SUGERE_POSITIVA, p["sugestao"]

    # a tela do rascunho oferece a positiva, e o link só PREENCHE o protocolo
    pagina = casa["c"].get(f"/registro-imoveis/qualificacao-ia/{pedido}").get_data(as_text=True)
    assert "aponta a qualificação positiva" in pagina
    assert "Levar para a qualificação positiva" in pagina
    con = _con(casa)
    assert con.execute("SELECT COUNT(*) FROM ri_qualificacoes WHERE protocolo_id = ?",
                       (pid,)).fetchone()[0] == 0
    con.close()
    tela = casa["c"].get(f"/registro-imoveis/protocolo/{pid}?qualificacao={pedido}"
                         ).get_data(as_text=True)
    caixa = re.search(r'<textarea name="fundamentacao"[^>]*>(.*?)</textarea>', tela, re.S).group(1)
    assert f"qualificação assistida nº {pedido}" in caixa
    assert "o imóvel do título é o desta matrícula" in caixa
    assert f'name="qualificacao_ia_id" value="{pedido}"' in tela

    # quem qualifica é a rota de sempre, com o que a pessoa deixou no campo
    r = casa["c"].post(f"/registro-imoveis/protocolo/{pid}/qualificar", data={
        "csrf_token": _token(tela), "fundamentacao": "Título em ordem (conferido à mão).",
        "qualificacao_ia_id": str(pedido)})
    assert r.status_code == 302
    con = _con(casa)
    q = con.execute("SELECT * FROM ri_qualificacoes WHERE protocolo_id = ?", (pid,)).fetchone()
    ligado = con.execute("SELECT qualificacao_id FROM ri_qualificacao_ia WHERE id = ?",
                         (pedido,)).fetchone()[0]
    assert q["resultado"] == "POSITIVA" and "à mão" in q["fundamentacao"] and ligado == q["id"]
    # o mesmo rascunho não serve a uma segunda positiva nem vira nota
    assert QIA.preenchimento_positiva(con, pedido, pid) is None
    with con:
        assert QIA.ligar_a_positiva(con, pedido, pid, q["id"] + 1) is False
    with pytest.raises(QIA.QualificacaoIAError, match="qualificação positiva registrada"):
        QIA.levar(con, pedido, [(0, "")], usuario="MARIO")
    con.close()


def test_o_preenchimento_da_positiva_nao_atravessa_de_prenotacao(casa):
    _, pid = _prenotacao(casa)
    escritura = _anexar(casa, "RI_PROTOCOLO", pid, "escritura.pdf", ESCRITURA)
    pedido = _pedir_e_executar(casa, pid, [escritura], IA(resposta=TITULO_EM_ORDEM))
    _, outra = _prenotacao(casa, numero=11803, com_matricula=False)
    tela = casa["c"].get(f"/registro-imoveis/protocolo/{outra}?qualificacao={pedido}"
                         ).get_data(as_text=True)
    assert 'name="qualificacao_ia_id"' not in tela
    con = _con(casa)
    assert QIA.preenchimento_positiva(con, pedido, outra) is None
    with con:
        assert QIA.ligar_a_positiva(con, pedido, outra, 1) is False
    con.close()


def test_a_coluna_da_positiva_entra_na_instalacao_que_ja_tem_a_tabela(casa):
    con = _con(casa)
    with con:
        con.execute("ALTER TABLE ri_qualificacao_ia DROP COLUMN qualificacao_id")
    from bd_nativo import banco as _banco
    assert not _banco(con).tem_coluna("ri_qualificacao_ia", "qualificacao_id")
    with con:
        QIA.init_schema(con)
    assert _banco(con).tem_coluna("ri_qualificacao_ia", "qualificacao_id")
    con.close()


# ------------------------------------------------------------- as falhas


@pytest.mark.parametrize("ia,frase", [
    (IA(parou="refusal"), "recusou"),
    (IA(texto="[SIMULADOR DO SANDBOX] resposta simulada"), "simulada"),
    (IA(texto="não é json"), "formato combinado"),
])
def test_recusa_simulador_e_resposta_torta_viram_erro_com_a_frase(casa, ia, frase):
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    p = _pedido(casa, _pedir_e_executar(casa, pid, [escritura, itbi], ia))
    assert p["situacao"] == QIA.ERRO and frase in p["erro"]


def test_dois_pedidos_ao_mesmo_tempo_na_mesma_prenotacao_sao_recusados(casa):
    _, pid = _prenotacao(casa)
    escritura, _ = _titulo_e_itbi(casa, pid)
    con = _con(casa)
    with con:
        QIA.pedir(con, pid, anexos_ids=[escritura])
    with pytest.raises(QIA.QualificacaoIAError, match="ainda está lendo"):
        QIA.pedir(con, pid, anexos_ids=[escritura])
    con.close()


def test_prenotacao_sem_ficha_aceita_a_matricula_digitada(casa):
    _prenotacao(casa)                       # cria a matrícula 777 (e outra prenotação)
    _, pid = _prenotacao(casa, numero=11802, com_matricula=False)
    escritura, _ = _titulo_e_itbi(casa, pid)
    con = _con(casa)
    with con:
        pedido = QIA.pedir(con, pid, anexos_ids=[escritura], matricula_numero="777")
    with pytest.raises(QIA.QualificacaoIAError, match="Não há matrícula"):
        QIA.matricula_da_prenotacao(con, {"matricula_id": None}, "999999")
    assert QIA.mostrar(con, pedido)["matricula_id"]
    con.close()


# ------------------------------------------- revisão de segurança (26/10/2026)
#
# O teto do dia contava só `ia_uso`, que grava DEPOIS da resposta: pedidos ao
# mesmo tempo passavam todos. Agora a vaga se reserva no pedido, e o que está
# em voo conta; e o robô não pede nem leva.


def _teto(monkeypatch, n):
    import ia_catalogo as CAT
    monkeypatch.setitem(CAT.CHAMADAS_POR_DIA, QIA.FINALIDADE, n)


def test_o_teto_conta_os_pedidos_em_voo_e_recusa_antes_de_gravar(casa, monkeypatch):
    _teto(monkeypatch, 2)
    con = _con(casa)
    for numero in (11810, 11811):
        _, pid = _prenotacao(casa, numero=numero)
        escritura, _ = _titulo_e_itbi(casa, pid)
        with con:
            QIA.pedir(con, pid, anexos_ids=[escritura])      # ficam PENDENTE
    _, pid = _prenotacao(casa, numero=11812)
    escritura, _ = _titulo_e_itbi(casa, pid)
    with pytest.raises(QIA.QualificacaoIAError, match="0 leitura.*2 em andamento, de 2"):
        with con:
            QIA.pedir(con, pid, anexos_ids=[escritura])
    n = con.execute("SELECT COUNT(*) FROM ri_qualificacao_ia WHERE protocolo_id = ?",
                    (pid,)).fetchone()[0]
    con.close()
    assert n == 0                            # a recusa não deixou pedido gravado


def test_o_teto_soma_o_que_ia_uso_ja_registrou(casa, monkeypatch):
    import ia_uso as USO
    _teto(monkeypatch, 3)
    monkeypatch.setattr(USO, "usos_do_dia",
                        lambda con, fin, dia: 3 if fin == QIA.FINALIDADE else 0)
    _, pid = _prenotacao(casa)
    escritura, _ = _titulo_e_itbi(casa, pid)
    con = _con(casa)
    with pytest.raises(QIA.QualificacaoIAError, match="3 leitura"):
        with con:
            QIA.pedir(con, pid, anexos_ids=[escritura])
    con.close()


def test_executar_confere_o_teto_antes_da_rede_sem_contar_o_proprio(casa, monkeypatch):
    _teto(monkeypatch, 2)
    con = _con(casa)
    pedidos = []
    for numero in (11820, 11821):
        _, pid = _prenotacao(casa, numero=numero)
        escritura, _ = _titulo_e_itbi(casa, pid)
        with con:
            pedidos.append(QIA.pedir(con, pid, anexos_ids=[escritura]))
    con.close()
    # com teto 2 e um outro em voo, o próprio passa (1 < 2) e a IA é chamada
    ia = IA()
    QIA.executar(casa["banco"], casa["dados"], pedidos[0], conversar=ia)
    assert len(ia.pedidos) == 1 and _pedido(casa, pedidos[0])["situacao"] == QIA.PRONTA
    # o teto baixou (o catálogo mudou, ou outra porta gastou): o segundo para
    # ANTES da rede, com a frase, e a IA não é chamada
    _teto(monkeypatch, 0)
    ia2 = IA()
    QIA.executar(casa["banco"], casa["dados"], pedidos[1], conversar=ia2)
    p = _pedido(casa, pedidos[1])
    assert ia2.pedidos == [] and p["situacao"] == QIA.ERRO and "teto" in p["erro"]


def test_o_robo_nao_pede_nao_le_e_nao_leva(casa, monkeypatch):
    import selo_robo as SR
    from conftest import cg_login
    for rota in ("ri_qualificacao_ia_pedir", "ri_qualificacao_ia_ver",
                 "ri_qualificacao_ia_levar"):
        assert SR.rota_vedada_ao_robo(rota), rota
    assert not SR.rota_vedada_ao_robo("ri_qualificar")
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(QIA, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    casa["db"].create_user("robo_ri", "Robo de Exemplo RI", "Senha#12345", "USER",
                           eh_robo=1)
    c = casa["app"].test_client()
    cg_login(c, "robo_ri", "Senha#12345")
    tok = _token(c.get("/").get_data(as_text=True))
    r = c.post(f"/registro-imoveis/protocolo/{pid}/qualificacao-ia/pedir", data={
        "csrf_token": tok, "anexo": [str(escritura), str(itbi)]})
    assert r.status_code == 403 and comecados == []
    assert c.get("/registro-imoveis/qualificacao-ia/1").status_code == 403
    assert c.post("/registro-imoveis/qualificacao-ia/1/levar",
                  data={"csrf_token": tok}).status_code == 403
    con = _con(casa)
    n = con.execute("SELECT COUNT(*) FROM ri_qualificacao_ia").fetchone()[0]
    con.close()
    assert n == 0


# ------------------------------------------------------------- quem pode pedir


@pytest.mark.parametrize("papel", ["USER", "MANAGER"])
def test_todo_humano_que_pratica_ato_pede_a_qualificacao(casa, monkeypatch, papel):
    """DECISÃO DO OFICIAL EM 26/10/2026, «todos podem»: o escrevente (USER) e
    o gerente (MANAGER) pedem a qualificação assistida e veem o botão, como o
    ADMIN. A régua é a da casa (`seguranca_web.PRATICA`)."""
    import ri_qualificacao_ia_web as QWEB
    import seguranca_web as SEGWEB
    from conftest import cg_login
    assert set(QWEB.PAPEIS_QUE_PEDEM) == {"ADMIN", "MANAGER", "USER"}
    assert tuple(QWEB.PAPEIS_QUE_PEDEM) == tuple(SEGWEB.PRATICA)
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(QIA, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    casa["db"].create_user("beatriz", "BEATRIZ EXEMPLO", "Senha#12345", papel)
    c = casa["app"].test_client()
    cg_login(c, "beatriz", "Senha#12345")
    # leva à nota: o botão aparece no rascunho pronto
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], IA())
    pagina = c.get(f"/registro-imoveis/qualificacao-ia/{pedido}").get_data(as_text=True)
    assert "Levar para a nota devolutiva" in pagina
    # e pede uma qualificação nova pela tela da nota
    html = c.get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
    assert "Pedir a qualificação assistida" in html
    r = c.post(f"/registro-imoveis/protocolo/{pid}/qualificacao-ia/pedir", data={
        "csrf_token": _token(html), "anexo": [str(escritura), str(itbi)],
        "especie": "R-COMPRA-VENDA"})
    assert r.status_code == 302
    con = _con(casa)
    linha = con.execute("SELECT * FROM ri_qualificacao_ia WHERE protocolo_id = ? "
                        "ORDER BY id DESC", (pid,)).fetchone()
    con.close()
    assert linha and linha["id"] != pedido and comecados == [linha["id"]]
    assert "BEATRIZ" in (linha["pedido_por"] or "")


def test_o_auditor_le_o_rascunho_mas_nao_pede_nem_leva(casa, monkeypatch):
    """O AUDITOR só lê (decisão de 26/10/2026): vê o rascunho, sem o botão de
    levar; pedir e levar respondem 403 e nada é gravado."""
    from conftest import cg_login
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(QIA, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    pedido = _pedir_e_executar(casa, pid, [escritura, itbi], IA())
    casa["db"].create_user("carla", "CARLA EXEMPLO", "Senha#12345", "AUDITOR")
    c = casa["app"].test_client()
    cg_login(c, "carla", "Senha#12345")
    pagina = c.get(f"/registro-imoveis/qualificacao-ia/{pedido}")
    assert pagina.status_code == 200
    texto = pagina.get_data(as_text=True)
    assert "Levar para a nota devolutiva" not in texto
    tok = _token(c.get("/").get_data(as_text=True))
    r = c.post(f"/registro-imoveis/protocolo/{pid}/qualificacao-ia/pedir", data={
        "csrf_token": tok, "anexo": [str(escritura), str(itbi)]})
    assert r.status_code == 403 and comecados == []
    r = c.post(f"/registro-imoveis/qualificacao-ia/{pedido}/levar", data={
        "csrf_token": tok, "escolhida": ["0"], "texto_0": "x"})
    assert r.status_code == 403
    con = _con(casa)
    n = con.execute("SELECT COUNT(*) FROM ri_qualificacao_ia").fetchone()[0]
    levado = con.execute("SELECT levado_em, nota_id FROM ri_qualificacao_ia WHERE id = ?",
                         (pedido,)).fetchone()
    con.close()
    assert n == 1 and levado["levado_em"] is None and levado["nota_id"] is None


# ------------------------------------------------- o teto do dia (26/10/2026)


def test_o_teto_padrao_e_20_por_dia(casa):
    """DECISÃO DO OFICIAL EM 26/10/2026: 20 leituras por dia (era 40)."""
    import ia_catalogo as CAT
    assert CAT.CHAMADAS_POR_DIA[QIA.FINALIDADE] == 20
    assert QIA.teto_padrao() == 20
    con = _con(casa)
    assert QIA.teto_do_dia(con) == 20
    con.close()
    # o quadro e a tela de configuração dizem o número
    tela = casa["c"].get("/registro-imoveis/qualificacao-ia/configuracao").get_data(as_text=True)
    assert "20 leitura(s) por dia" in tela


def test_o_admin_muda_o_teto_para_5_e_o_sexto_pedido_e_recusado(casa):
    """O ADMIN grava 5 na tela (com auditoria); cinco pedidos em voo ocupam o
    dia e o sexto é recusado antes de gravar. O gerente não muda o teto."""
    from conftest import cg_login
    pagina = casa["c"].get("/registro-imoveis/qualificacao-ia/configuracao").get_data(as_text=True)
    r = casa["c"].post("/registro-imoveis/qualificacao-ia/configuracao",
                       data={"csrf_token": _token(pagina), "teto": "5"})
    assert r.status_code == 302
    con = _con(casa)
    assert QIA.teto_do_dia(con) == 5
    auditoria = con.execute("SELECT details FROM audit_logs WHERE action = ? "
                            "ORDER BY id DESC", ("RI_QUALIFICACAO_IA_TETO",)).fetchone()
    detalhes = json.loads(auditoria[0])
    assert detalhes["depois"] == 5 and detalhes["antes"] == 20
    for numero in range(11830, 11835):
        _, pid = _prenotacao(casa, numero=numero)
        escritura, _ = _titulo_e_itbi(casa, pid)
        with con:
            QIA.pedir(con, pid, anexos_ids=[escritura])      # ficam PENDENTE
    _, pid = _prenotacao(casa, numero=11835)
    escritura, _ = _titulo_e_itbi(casa, pid)
    with pytest.raises(QIA.QualificacaoIAError, match="5 em andamento, de 5"):
        with con:
            QIA.pedir(con, pid, anexos_ids=[escritura])
    n = con.execute("SELECT COUNT(*) FROM ri_qualificacao_ia WHERE protocolo_id = ?",
                    (pid,)).fetchone()[0]
    con.close()
    assert n == 0
    # fora da faixa é recusado e não muda nada; vazio volta ao padrão
    pagina = casa["c"].get("/registro-imoveis/qualificacao-ia/configuracao").get_data(as_text=True)
    casa["c"].post("/registro-imoveis/qualificacao-ia/configuracao",
                   data={"csrf_token": _token(pagina), "teto": "0"})
    con = _con(casa)
    assert QIA.teto_do_dia(con) == 5
    con.close()
    casa["c"].post("/registro-imoveis/qualificacao-ia/configuracao",
                   data={"csrf_token": _token(pagina), "teto": ""})
    con = _con(casa)
    assert QIA.teto_do_dia(con) == 20
    con.close()
    # o gerente não muda o teto
    casa["db"].create_user("beatriz", "BEATRIZ EXEMPLO", "Senha#12345", "MANAGER")
    c = casa["app"].test_client()
    cg_login(c, "beatriz", "Senha#12345")
    assert c.get("/registro-imoveis/qualificacao-ia/configuracao").status_code == 403
    tok = _token(c.get("/").get_data(as_text=True))
    assert c.post("/registro-imoveis/qualificacao-ia/configuracao",
                  data={"csrf_token": tok, "teto": "50"}).status_code == 403
    con = _con(casa)
    assert QIA.teto_do_dia(con) == 20
    con.close()
