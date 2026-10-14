"""Os anexos do ato na revisão — triagem, transcrição barata, leitura guardada, teto.

Pedido do oficial em 07/10/2026: «gostei do ler cada anexo uma vez, usar o modelo
mais barato para transcrever e aviso quando passar de 40 páginas. pode também
implementar no revisor um filtro do que é e o que não é importante antes de
transcrever tudo».

A IA aqui é de mentira: ela conta as chamadas e responde conforme a instrução
— é isso que prova que o arquivo lido não se paga de novo e que o descartado
na triagem não se transcreve.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import revisao_anexos as RA          # noqa: E402
import revisao_previa as RV          # noqa: E402


# ------------------------------------------------------------- o material

def pdf_com_texto(paginas: list[str]) -> bytes:
    """Um PDF mínimo, com camada de texto (Helvetica), uma página por item."""
    objetos = ["<< /Type /Catalog /Pages 2 0 R >>", None,
               "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>"]
    kids = []
    for texto in paginas:
        linhas = [texto[i:i + 70] for i in range(0, len(texto), 70)] or [""]
        corpo = "BT /F1 10 Tf 40 800 Td 12 TL " + " ".join(
            f"({l.replace('(', '').replace(')', '')}) '" for l in linhas) + " ET"
        objetos.append(f"<< /Length {len(corpo)} >>\nstream\n{corpo}\nendstream")
        conteudo = len(objetos)
        objetos.append(f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 595 842] "
                       f"/Resources << /Font << /F1 3 0 R >> >> /Contents {conteudo} 0 R >>")
        kids.append(f"{len(objetos)} 0 R")
    objetos[1] = f"<< /Type /Pages /Kids [{' '.join(kids)}] /Count {len(kids)} >>"
    saida = b"%PDF-1.4\n"
    posicoes = []
    for n, obj in enumerate(objetos, start=1):
        posicoes.append(len(saida))
        saida += f"{n} 0 obj\n{obj}\nendobj\n".encode("latin-1")
    xref = len(saida)
    saida += f"xref\n0 {len(objetos) + 1}\n0000000000 65535 f \n".encode()
    for p in posicoes:
        saida += f"{p:010d} 00000 n \n".encode()
    saida += (f"trailer\n<< /Size {len(objetos) + 1} /Root 1 0 R >>\n"
              f"startxref\n{xref}\n%%EOF\n").encode()
    return saida


def pdf_digitalizado(n: int) -> bytes:
    """Um PDF só de imagens — como o scanner entrega."""
    import io
    from PIL import Image
    paginas = [Image.new("L", (300, 420), 255) for _ in range(n)]
    saida = io.BytesIO()
    paginas[0].save(saida, format="PDF", save_all=True, append_images=paginas[1:])
    return saida.getvalue()


TEXTO_LONGO = ("ESCRITURA PUBLICA DE COMPRA E VENDA. Outorgante vendedor JOSE DA SILVA, "
               "CPF 123.456.789-00, casado. Imovel: lote 12 da quadra 3, area de 300 m2. ") * 3


class IA:
    def __init__(self, importante=True):
        self.importante = importante
        self.triagens = 0
        self.transcricoes = 0
        self.imagens = 0
        self.revisoes: list[str] = []

    def __call__(self, pasta, *, provedor, sistema, conversa, ferramentas, modelo,
                 maximo_de_saida):
        pedido = conversa[0]
        self.imagens += len(pedido.get("imagens") or [])
        if sistema == RA.INSTRUCAO_TRIAGEM:
            self.triagens += 1
            assert modelo == RA.MODELO_BARATO
            texto = json.dumps({"tipo": "escritura", "importante": self.importante,
                                "motivo": "fundamenta o ato" if self.importante
                                else "comprovante de pagamento"})
        elif sistema == RA.INSTRUCAO_TRANSCRICAO:
            self.transcricoes += 1
            assert modelo == RA.MODELO_BARATO
            texto = "[página] JOSE DA SILVA, lote 12, area 300 m2"
        else:
            self.revisoes.append(pedido["texto"])
            texto = json.dumps({"achados": [], "parecer": "ok"})
        return {"texto": texto, "entrada": 100, "saida": 10, "modelo": modelo}


@pytest.fixture()
def casa(tmp_path):
    banco = tmp_path / "casa.sqlite3"
    con = sqlite3.connect(banco)
    con.executescript("""
        CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT);
        CREATE TABLE attachments (id INTEGER PRIMARY KEY, entity_type TEXT,
            entity_id INTEGER, original_name TEXT, stored_name TEXT, stored_path TEXT,
            sha256 TEXT, size_bytes INTEGER, description TEXT, uploaded_by INTEGER,
            uploaded_at TEXT);
    """)
    con.commit()
    return {"banco": banco, "con": con, "pasta": tmp_path}


def anexar(casa, nome: str, dados: bytes, entidade="NT_ATO", entidade_id=7) -> None:
    caminho = casa["pasta"] / nome
    caminho.write_bytes(dados)
    casa["con"].execute(
        """INSERT INTO attachments (entity_type, entity_id, original_name, stored_path,
               sha256, size_bytes) VALUES (?,?,?,?,?,?)""",
        (entidade, entidade_id, nome, str(caminho), hashlib.sha256(dados).hexdigest(),
         len(dados)))
    casa["con"].commit()


ORIGEM = {"entidade": "NT_ATO", "id": 7}


# ------------------------------------------------------------- a leitura

def test_pagina_com_texto_se_le_aqui_e_nao_vai_a_transcricao(casa):
    anexar(casa, "escritura.pdf", pdf_com_texto([TEXTO_LONGO, TEXTO_LONGO]))
    ia = IA()
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.triagens == 1 and ia.transcricoes == 0 and ia.imagens == 0
    assert "JOSE DA SILVA" in r["bloco"]
    assert r["resumo"][0]["lidas"] == 2 and r["aviso"] == ""


def test_o_mesmo_arquivo_nao_se_le_duas_vezes(casa):
    anexar(casa, "rg.pdf", pdf_digitalizado(2))
    primeira = IA()
    RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=primeira)
    assert primeira.triagens == 1 and primeira.transcricoes == 1
    segunda = IA()
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=segunda)
    assert segunda.triagens == 0 and segunda.transcricoes == 0
    assert r["resumo"][0]["reaproveitado"] is True
    assert "JOSE DA SILVA" in r["bloco"]


def test_o_que_a_triagem_descarta_nao_se_transcreve(casa):
    anexar(casa, "boleto.pdf", pdf_digitalizado(3))
    ia = IA(importante=False)
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.triagens == 1 and ia.transcricoes == 0
    assert ia.imagens == 1                         # só a primeira página subiu
    assert r["bloco"] == ""
    assert r["resumo"][0]["importante"] is False
    assert "comprovante" in r["resumo"][0]["motivo"]


def test_digitalizado_vai_em_grupos_de_tres_paginas(casa):
    anexar(casa, "titulo.pdf", pdf_digitalizado(4))
    ia = IA()
    RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.transcricoes == 2                    # 3 + 1
    assert ia.imagens == 1 + 4                     # triagem + as quatro


def test_passou_de_40_paginas_avisa_e_nao_transcreve_o_excesso(casa):
    anexar(casa, "processo.pdf", pdf_digitalizado(45))
    ia = IA()
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert r["resumo"][0]["lidas"] == 40
    assert "45 páginas" in r["aviso"] and "Ficaram sem leitura" in r["aviso"]
    assert ia.imagens == 1 + 40


def test_com_mascara_ligada_nenhum_anexo_sobe(casa):
    anexar(casa, "rg.pdf", pdf_digitalizado(1))
    ia = IA()
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia, mascarada=True)
    assert ia.triagens == 0 and r["bloco"] == "" and "máscara" in r["aviso"]


def test_formato_nao_lido_aparece_com_o_motivo(casa):
    anexar(casa, "script.bat", b"echo nada")
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=IA())
    assert "não é lido" in r["resumo"][0]["motivo"]


def test_peticao_em_word_se_le_sem_imagem(casa):
    # Medido em 07/10/2026: seis anexos da produção são .docx — a petição de
    # inventário e a minuta entre eles.
    import io
    import zipfile
    corpo = io.BytesIO()
    with zipfile.ZipFile(corpo, "w") as z:
        z.writestr("word/document.xml",
                   "<w:document><w:body><w:p><w:r><w:t>PETICAO DE INVENTARIO</w:t>"
                   "<w:br/><w:t>herdeiro JOSE DA SILVA</w:t></w:r></w:p></w:body></w:document>")
    anexar(casa, "peticao.docx", corpo.getvalue())
    ia = IA()
    r = RA.ler(casa["con"], casa["pasta"], ORIGEM, conversar=ia)
    assert ia.imagens == 0 and ia.transcricoes == 0
    assert "PETICAO DE INVENTARIO\nherdeiro JOSE DA SILVA" in r["bloco"]


# ------------------------------------------------------------- na revisão

def test_anexar_depois_da_revisao_pede_revisao_nova(casa):
    con = casa["con"]
    RV.init_schema(con)
    a, nova_a = RV.pedir(con, "NOTAS", 7, "h", "dossie", anexos_origem=ORIGEM)
    b, nova_b = RV.pedir(con, "NOTAS", 7, "h", "dossie", anexos_origem=ORIGEM)
    assert nova_a and not nova_b and a == b
    anexar(casa, "titulo.pdf", pdf_com_texto([TEXTO_LONGO]))
    c, nova_c = RV.pedir(con, "NOTAS", 7, "h", "dossie", anexos_origem=ORIGEM)
    assert nova_c and c != a


def test_a_revisao_le_os_anexos_antes_do_ato(casa):
    con = casa["con"]
    anexar(casa, "titulo.pdf", pdf_com_texto([TEXTO_LONGO]))
    RV.init_schema(con)
    rid, _ = RV.pedir(con, "NOTAS", 7, "h",
                      "PARTES...\n=== ATO A LAVRAR ===\nteor do ato", anexos_origem=ORIGEM)
    con.commit()
    ia = IA()
    RV.executar(casa["banco"], casa["pasta"], rid, conversar=ia)
    enviado = ia.revisoes[0]
    assert enviado.index("DOCUMENTOS ANEXADOS") < enviado.index("=== ATO A LAVRAR ===")
    con2 = sqlite3.connect(casa["banco"])
    vista = RV.mostrar(con2, rid)
    con2.close()
    assert vista["situacao"] == "PRONTA"
    assert vista["anexos"][0]["nome"] == "titulo.pdf"


def test_falha_dos_anexos_nao_derruba_a_revisao(casa, monkeypatch):
    con = casa["con"]
    anexar(casa, "titulo.pdf", pdf_com_texto([TEXTO_LONGO]))
    RV.init_schema(con)
    rid, _ = RV.pedir(con, "NOTAS", 7, "h", "=== ATO A LAVRAR ===\nteor",
                      anexos_origem=ORIGEM)
    con.commit()

    def quebra(*a, **k):
        raise RuntimeError("rede caiu")
    monkeypatch.setattr(RA, "ler", quebra)
    RV.executar(casa["banco"], casa["pasta"], rid, conversar=IA())
    con2 = sqlite3.connect(casa["banco"])
    vista = RV.mostrar(con2, rid)
    con2.close()
    assert vista["situacao"] == "PRONTA"
    assert "não foram lidos" in vista["aviso_anexos"]


# ------------------------------------------------------------- o transporte

def test_a_imagem_vai_antes_do_texto_no_pedido_da_anthropic():
    import agente_provedores as AP
    pedido = AP.montar_pedido("claude", sistema="s", conversa=[
        {"tipo": "user", "texto": "leia", "imagens": [{"mime": "image/jpeg",
                                                       "base64": "QUJD"}]}],
        ferramentas=[], modelo="claude-haiku-4-5-20251001")
    conteudo = pedido["corpo"]["messages"][0]["content"]
    assert conteudo[0]["type"] == "image" and conteudo[1]["type"] == "text"


def test_provedor_sem_imagem_recusa_em_vez_de_calar():
    import agente_provedores as AP
    with pytest.raises(AP.AgenteError):
        AP.montar_pedido("gpt", sistema="s", conversa=[
            {"tipo": "user", "texto": "leia",
             "imagens": [{"mime": "image/jpeg", "base64": "QUJD"}]}], ferramentas=[])
