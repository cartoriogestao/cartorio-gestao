"""Os papéis editáveis saem sem o que executa — revisão de segurança de
22/10/2026 (achados A7, A8 e M16).

O QUE A REVISÃO MEDIU: cinco sítios montavam papel a partir de um modelo que
o papel USER edita na tela de Modelos (a pública forma, a certidão por texto
do RCPJ/RTD/Livro 3, os modelos do RI, a lavratura das Notas e o recibo do
caixa) e mandavam o resultado ao navegador com `|safe` — um `<script>` ou um
`onerror=` gravado no modelo rodaria na sessão do oficial. E o corpo das
certidões ia ao Chrome do servidor, que conta as folhas, como o balcão o
escreveu: `file:` e `//maquina` no HTML iriam ao disco e à rede com a
credencial da máquina.

O CONSERTO É UMA RÉGUA SÓ (`modelos_da_casa.sem_o_que_executa`): o texto de
fábrica sai byte a byte como saía — é o que o teste-ouro dos padrões
confere —, e o ajuste da casa passa por `html_sem_script.limpar`. O corpo
das folhas passa sempre, antes do Chrome. Estes testes provam as duas
metades em cada ponto que não exige banco.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_da_casa as MODELOS  # noqa: E402

# O que um modelo ajustado poderia carregar: script, atributo de evento e
# endereço que executa. Nenhum dos três é teor de papel nenhum.
CARGA = ('<p>texto</p><script>alert(1)</script>'
         '<img src="x" onerror="alert(2)"><a href="javascript:alert(3)">x</a>')


def _chave_qualquer() -> str:
    return next(iter(MODELOS.POR_CHAVE))


def test_o_texto_de_fabrica_e_reconhecido_byte_a_byte():
    padrao = MODELOS.padrao_de(_chave_qualquer())
    assert MODELOS.e_texto_de_fabrica(padrao)
    assert not MODELOS.e_texto_de_fabrica(padrao + " ")
    assert not MODELOS.e_texto_de_fabrica("")


def test_o_padrao_sai_como_saia_e_o_ajuste_sai_filtrado():
    padrao = MODELOS.padrao_de(_chave_qualquer())
    # Modelo de fábrica: o filtro NÃO entra — nem num HTML que ele mudaria.
    assert MODELOS.sem_o_que_executa(padrao, CARGA) == CARGA
    limpo = MODELOS.sem_o_que_executa(padrao + " ", CARGA)
    assert "<script" not in limpo
    assert "onerror" not in limpo
    assert "javascript:" not in limpo
    assert "<p>texto</p>" in limpo


def test_a_publica_forma_com_modelo_da_casa_sai_sem_script():
    import nt_publica_forma as PF
    modelo = MODELOS.padrao_de(PF.CHAVE_DO_PAPEL) + CARGA
    teor = PF.montar_teor(modelo=modelo, transcricao="linha 1")
    assert "linha 1" in teor
    assert "<script" not in teor
    assert "onerror" not in teor


def test_a_publica_forma_de_fabrica_nao_muda():
    """O padrão rende exatamente como rendia antes do filtro existir."""
    import nt_publica_forma as PF
    from jinja2.sandbox import SandboxedEnvironment
    from markupsafe import Markup
    padrao = MODELOS.padrao_de(PF.CHAVE_DO_PAPEL)
    esperado = SandboxedEnvironment(autoescape=True).from_string(padrao).render(
        transcricao=Markup("a &amp; b"))
    assert PF.montar_teor(transcricao="a & b") == esperado


def test_a_certidao_por_texto_com_modelo_da_casa_sai_sem_script():
    import atrib_certidao as AC
    certidao = {"teor": "<p>TEOR DO LIVRO</p>", "cancelada": 0}
    papel = AC._montar_papel_por_texto(
        "<div>{{ c.teor }}</div>" + CARGA, certidao, sv={}, hoje="2026-10-22")
    assert "TEOR DO LIVRO" in papel
    assert "<script" not in papel
    assert "onerror" not in papel


def test_o_corpo_vai_ao_chrome_sem_o_que_executa(monkeypatch):
    """O que chega ao Chrome que conta as folhas já passou pelo filtro."""
    import certidao_folhas as CF
    import impressao_pdf as IP
    visto = {}

    def falso(html, *, nome="documento", get_setting=None):
        visto["html"] = html
        return b"%PDF-1.4 falso"

    monkeypatch.setattr(IP, "pdf_de_html_chrome", falso)
    corpo = ('<p>certidao</p><script>alert(1)</script>'
             '<img src="//maquina/x.png"><a href="file:///C:/x">x</a>')
    CF._pdf_do_html(corpo, get_setting=None)
    assert "certidao" in visto["html"]
    assert "<script" not in visto["html"]
    assert "//maquina" not in visto["html"]
    assert "file:" not in visto["html"]


def test_o_qr_em_png_sobrevive_ao_filtro():
    """O carimbo do RI leva o QR como `<img src="data:image/png…">`; o
    filtro tem de deixá-lo, senão a folha contada perde o carimbo."""
    import html_sem_script as HSS
    img = '<img class="carimbo-qr" alt="QR" width="56" src="data:image/png;base64,iVBORw0KGgo=" />'
    assert "data:image/png;base64,iVBORw0KGgo=" in HSS.limpar(img)
