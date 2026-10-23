"""O BOTAO ENTREGA PDF — pedido do oficial em 01/09/2026.

*«a ferramenta de impressão está baixando um arquivo, preciso que gere o pdf
para impressão nesse botão»*.

O QUE ESTES TESTES GUARDAM
      - **codigo de saida nao e prova; o arquivo existir e** — a medicao que
        deu origem a este modulo foi um `soffice` que saiu com codigo 0 e nao
        escreveu PDF nenhum;
      - **o PDF sai de verdade**, com o cabecalho `%PDF-` — e nao bytes vazios
        com cara de sucesso;
      - **o `.odt` continua alcancavel**, porque ha papel que o oficial abre
        para ajustar, e porque o balcao nao pode parar se o LibreOffice cair;
      - **o PDF abre na tela e o `.odt` baixa** — `inline` poe o visualizador
        do navegador, com o botao de imprimir do lado, que foi o pedido;
      - **o nome do arquivo e ASCII** — cabecalho HTTP com acento quebra a
        resposta inteira, e os papeis desta casa se chamam «Certidão 1/2026»;
      - **toda rota de papel volta para uma tela que existe**. Este varredor
        achou uma que nao existia (`ri_nota`), e ela so seria chamada no
        caminho de falha — o erro apareceria meses depois, justamente quando o
        balcao ja estivesse com um problema.
"""
from __future__ import annotations

import re
import sys
import tempfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import impressao_pdf as PDF

MOLDE = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
TEM_LIBREOFFICE = PDF.onde_esta_o_conversor() is not None


# ------------------------------------------------- a regra, sem converter


def test_o_formato_desconhecido_cai_no_pdf():
    """O balcao clicou num botao; nao escreveu o endereco a mao."""
    assert PDF.formato_pedido("docx") == "pdf"
    assert PDF.formato_pedido(None) == "pdf"
    assert PDF.formato_pedido("") == "pdf"
    assert PDF.formato_pedido("ODT") == "odt"


def test_o_pdf_abre_na_tela_e_o_odt_baixa():
    """`inline` poe o papel no visualizador, que ja tem o botao de imprimir."""
    assert PDF.ENTREGA_DO_FORMATO["pdf"] == "inline"
    assert PDF.ENTREGA_DO_FORMATO["odt"] == "attachment"


def test_o_nome_do_arquivo_e_ascii_e_sem_barra():
    """CABECALHO HTTP COM ACENTO QUEBRA A RESPOSTA INTEIRA, e os papeis desta
    casa se chamam «Certidão 1/2026» — com acento e com barra, que nem em nome
    de arquivo do Windows entra."""
    _, _, arquivo, _ = PDF.papel_para_baixar(
        b"nao-e-odt-de-verdade", nome="Certidão 1/2026", formato="odt")
    assert arquivo.isascii(), arquivo
    assert "/" not in arquivo and "\\" not in arquivo
    assert arquivo.endswith(".odt")


def test_nome_vazio_nao_produz_arquivo_sem_nome():
    _, _, arquivo, _ = PDF.papel_para_baixar(b"x", nome="///", formato="odt")
    assert arquivo == "documento.odt"


def test_o_odt_sai_inteiro_e_nao_passa_pelo_conversor():
    """Pedir `.odt` devolve o que entrou, byte a byte."""
    dentro = b"PK\x03\x04 isto e um zip de mentira"
    conteudo, tipo, _, entrega = PDF.papel_para_baixar(
        dentro, nome="papel", formato="odt")
    assert conteudo == dentro
    assert tipo == "application/vnd.oasis.opendocument.text"
    assert entrega == "attachment"


def test_documento_vazio_recusa_em_vez_de_devolver_nada():
    """Papel vazio com cara de sucesso e o carimbo que mente."""
    with pytest.raises(PDF.PdfError):
        PDF.pdf_de_odt(b"", nome="papel")


def test_sem_conversor_a_recusa_diz_o_que_fazer():
    """«Nao encontrado» faria o balcao achar que o sistema quebrou.

    O caminho configurado fica DENTRO da pasta de programas (revisão de
    segurança de 22/10/2026, M3: fora dela o caminho é ignorado e vale a
    detecção) — e não existe: a recusa diz onde consertar."""
    sem_nada = lambda chave, padrao=None: "C:/Program Files/nao/existe/soffice.exe"
    with pytest.raises(PDF.PdfError) as e:
        PDF.pdf_de_odt(b"conteudo", nome="p", get_setting=sem_nada)
    frase = str(e.value)
    assert "LibreOffice" in frase
    assert "Configurações" in frase


def test_a_configuracao_manda_sobre_os_caminhos_conhecidos(tmp_path, monkeypatch):
    """No dia em que ele mudar de lugar, ninguem quer mexer no codigo para o
    balcao voltar a imprimir — a mesma decisao da versao da tabela de custas.

    DESDE 22/10/2026 (revisão de segurança, M3) a configuração só manda se o
    programa estiver numa pasta de programas e tiver o nome do programa: um
    caminho em Downloads — ou um `.odt`, que era o que este teste usava —
    seria executado como conversor por quem conseguisse gravar a configuração."""
    monkeypatch.setenv("ProgramFiles", str(tmp_path / "Program Files"))
    monkeypatch.setenv("ProgramFiles(x86)", str(tmp_path / "Program Files (x86)"))
    monkeypatch.setenv("ProgramW6432", str(tmp_path / "Program Files"))
    de_fora = tmp_path / "Program Files" / "LibreOffice 25" / "program" / "soffice.exe"
    de_fora.parent.mkdir(parents=True)
    de_fora.write_bytes(b"x")
    escrito = lambda chave, padrao=None: str(de_fora)
    assert PDF.onde_esta_o_conversor(escrito) == de_fora
    # fora da pasta de programas (o molde .odt) a configuração é ignorada
    monkeypatch.setattr(PDF, "CAMINHOS_CONHECIDOS", ())
    monkeypatch.setattr(PDF.shutil, "which", lambda *_: None)
    escrito = lambda chave, padrao=None: str(MOLDE)
    assert PDF.onde_esta_o_conversor(escrito) is None


# ------------------------------------------------- e convertendo de verdade


@pytest.mark.skipif(not TEM_LIBREOFFICE, reason="sem LibreOffice nesta maquina")
def test_o_pdf_sai_de_verdade():
    """**A PROVA E O ARQUIVO, E NAO O CODIGO DE SAIDA.** Foi um `soffice` que
    saiu com codigo 0 e pasta vazia que decidiu o desenho deste modulo."""
    pdf = PDF.pdf_de_odt(MOLDE.read_bytes(), nome="certidao")
    assert pdf[:5] == b"%PDF-", "nao veio PDF"
    assert len(pdf) > 10_000, "PDF pequeno demais para uma certidao"


def test_o_padrao_da_casa_decide_quando_a_tela_nao_pede():
    """**O PADRAO E DO OFICIAL, E NAO MEU.** A conversao mediu de 1 s a 51 s
    nesta maquina e nao se achou o que separa os dois; se ficar lenta no
    balcao, quem volta para o `.odt` e ele, numa tarde."""
    so_odt = lambda c, p=None: "odt" if c == "impressao_formato_padrao" else p
    assert PDF.formato_pedido(None, so_odt) == "odt"
    assert PDF.formato_pedido("", so_odt) == "odt"
    # E o que a TELA pede manda sobre o padrao: o botao «.odt» funciona mesmo
    # com o padrao em PDF, e o «Imprimir» mesmo com o padrao em .odt.
    assert PDF.formato_pedido("pdf", so_odt) == "pdf"
    # Valor estranho na configuracao nao troca o formato por acidente.
    estranho = lambda c, p=None: "docx"
    assert PDF.formato_pedido(None, estranho) == "pdf"


def test_o_odt_sai_sem_acender_o_libreoffice():
    """O caminho do `.odt` nao converte nada — e por isso e o que serve de
    saida quando o conversor nao responde."""
    _, tipo, _, _ = PDF.papel_para_baixar(
        b"x", nome="p", formato="odt",
        get_setting=lambda c, p=None: "C:/nao/existe.exe")
    assert tipo == "application/vnd.oasis.opendocument.text"


# ------------------------------------------------- o varredor das rotas


def test_toda_rota_de_papel_volta_para_uma_tela_que_existe():
    """**ELE ACHOU UMA QUE NAO EXISTIA.** `ri_nota_odt` voltava para `ri_nota`,
    que nao e rota nenhuma — a tela e `ri_nota_devolutiva`, do protocolo. E o
    `url_for` so seria chamado no caminho de FALHA: quem topasse com ele ja
    estaria com um problema, e levaria um segundo.

    Varredor, e nao teste de um caso: rota de papel nova nasce guardada.
    """
    from app import create_app
    dados = Path(tempfile.gettempdir()) / "test_impressao_rotas"
    dados.mkdir(parents=True, exist_ok=True)
    app = create_app({"DATA_DIR": str(dados)})
    existentes = {r.endpoint for r in app.url_map.iter_rules()}

    procurados = 0
    faltando = []
    for arq in sorted(RAIZ.glob("*_web.py")):
        texto = arq.read_text(encoding="utf-8")
        for m in re.finditer(r'voltar_para=url_for\(\s*"([a-z_]+)"', texto):
            procurados += 1
            if m.group(1) not in existentes:
                faltando.append(f"{arq.name}: {m.group(1)}")
    assert procurados >= 6, (
        f"o varredor achou so {procurados} rotas de papel — ele parou de "
        f"enxergar, e varredor que deixa de achar passa calado")
    assert not faltando, f"voltam para tela que nao existe: {faltando}"
