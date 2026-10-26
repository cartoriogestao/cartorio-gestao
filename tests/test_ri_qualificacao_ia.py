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
    html = casa["c"].get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
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


def test_o_quadro_aparece_na_nota_e_o_pedido_entra_em_segundo_plano(casa, monkeypatch):
    monkeypatch.setattr(AP, "tem_chave", lambda *a, **k: True)
    comecados = []
    monkeypatch.setattr(QIA, "preparar_em_segundo_plano",
                        lambda banco, pasta, pid: comecados.append(pid))
    _, pid = _prenotacao(casa)
    escritura, itbi = _titulo_e_itbi(casa, pid)
    html = casa["c"].get(f"/registro-imoveis/protocolo/{pid}/nota").get_data(as_text=True)
    assert 'id="qualificacao-ia"' in html and "escritura.pdf" in html
    assert "sem máscara" in html
    # o quadro vem antes do formulário de emitir
    assert html.index('id="qualificacao-ia"') < html.index('id="emitir-nota"')
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
