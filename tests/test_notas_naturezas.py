"""
Testes da sugestão de natureza da escritura.

O QUE ELES DEFENDEM
    Que a sugestão saia do que o ato diz de si mesmo, com a evidência à vista;
    que ato de outra espécie não receba natureza de escritura; e que o padrão
    continue sendo escrito sem acento — foi a normalização do PADRÃO que
    transformou `\\b` em `\\B` e derrubou tudo em silêncio.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import notas_naturezas as NN          # noqa: E402


TEOR = ("REPÚBLICA FEDERATIVA DO BRASIL ESTADO DO MARANHÃO LIVRO n°027 (Notas) "
        "FLS.182 ESCRITURA PÚBLICA DE {}, tendo como OUTORGANTE VENDEDOR "
        "FULANO DE TAL, brasileiro...")


def sugerir(titulo: str) -> dict:
    return NN.sugerir(TEOR.format(titulo))


# ------------------------------------------------------ o defeito do \b

def test_o_padrao_nao_e_transformado_antes_de_usar():
    # A normalização do padrão virava `\b` em `\B`, a asserção OPOSTA, e todo
    # padrão com limite de palavra parava de casar sem dar sinal.
    assert sugerir("DOAÇÃO")["natureza_censec"] == 22
    assert NN.sugerir(None, titulo="doação")["natureza_censec"] == 22
    assert NN.sugerir(None, titulo="Doação")["natureza_censec"] == 22


def test_nenhum_padrao_guarda_acento():
    # O alvo chega normalizado; padrão com acento nunca casaria. Este teste
    # impede que alguém acrescente uma pista com acento e ela morra calada.
    for grupo in (NN.PISTAS_CEP, NN.PISTAS_CESDI, NN.PISTAS_OUTRO_ATO):
        for padrao, _, _ in grupo:
            assert padrao == NN._sem_acento(padrao), padrao
            assert padrao == padrao.upper() or "\\b" in padrao, padrao


def test_toda_pista_e_uma_expressao_valida():
    for grupo in (NN.PISTAS_CEP, NN.PISTAS_CESDI, NN.PISTAS_OUTRO_ATO):
        for padrao, _, _ in grupo:
            re.compile(padrao)


# ------------------------------------------------------------- o título

def test_le_o_titulo_do_teor():
    assert NN.titulo_do_teor(TEOR.format("COMPRA E VENDA")) == "COMPRA E VENDA"


def test_le_tambem_sem_a_palavra_publica():
    # O acervo antigo escreve "ESCRITURA DE VENDA E COMPRA".
    t = "fls. 12-vº, ESCRITURA DE VENDA E COMPRA, no valor de CZ$ 2.000.000,00"
    assert "VENDA E COMPRA" in (NN.titulo_do_teor(t) or "")


def test_teor_vazio_nao_inventa_titulo():
    assert NN.titulo_do_teor(None) is None
    assert NN.sugerir(None)["certeza"] == "nenhuma"


# --------------------------------------------------------- a sugestão

def test_compra_e_venda_nas_duas_ordens():
    assert sugerir("COMPRA E VENDA")["natureza_censec"] == 6
    assert sugerir("VENDA E COMPRA")["natureza_censec"] == 6
    assert sugerir("COMPRA E VENDA DE IMÓVEL RURAL")["natureza_censec"] == 6


def test_a_promessa_vem_antes_da_compra():
    # A ordem das pistas importa: "PROMESSA DE COMPRA E VENDA" tem natureza
    # própria, 80, e casaria como 6 se viesse depois.
    assert sugerir("PROMESSA DE COMPRA E VENDA")["natureza_censec"] == 80


def test_desmembramento_vira_divisao():
    s = sugerir("DESMEMBRAMENTO FEITO PELO OUTORGANTE")
    assert s["natureza_censec"] == 53
    assert "desdobro" in s["descricao"]


def test_reconhecimento_de_paternidade():
    assert sugerir("RECONHECIMENTO DE PATERNIDADE")["natureza_censec"] == 36


def test_a_evidencia_acompanha_a_sugestao():
    # Sugestão sem evidência é palpite com cara de autoridade.
    s = sugerir("COMPRA E VENDA")
    assert s["evidencia"] and "COMPRA E VENDA" in s["evidencia"]
    assert s["certeza"] == "alta"


# ------------------------------------------ o que NÃO é escritura da CEP

def test_divorcio_vai_para_a_cesdi_e_nao_para_a_cep():
    s = sugerir("DIVÓRCIO DIRETO CONSENSUAL")
    assert s["tipo_cesdi"] == 4
    assert s["natureza_censec"] is None


def test_separacao_e_conversao_sao_tipos_diferentes():
    assert sugerir("SEPARAÇÃO CONSENSUAL")["tipo_cesdi"] == 1
    assert sugerir("CONVERSÃO DE SEPARAÇÃO EM DIVÓRCIO")["tipo_cesdi"] == 3


def test_revogacao_de_mandato_nao_recebe_natureza_de_escritura():
    # Uma das 45 "escrituras" do acervo é isto. Dar-lhe natureza seria
    # classificar errado com ar de acerto.
    s = sugerir("REVOGAÇÃO DE MANDATO")
    assert s["outro_tipo"] == "REVOGACAO_PROCURACAO"
    assert s["natureza_censec"] is None and s["tipo_cesdi"] is None
    assert "tipo 6 da CEP" in s["descricao"]


def test_testamento_nao_vai_a_cep():
    s = sugerir("TESTAMENTO PÚBLICO")
    assert s["outro_tipo"] == "TESTAMENTO"
    assert "RCTO" in s["descricao"]


def test_titulo_ambiguo_nao_recebe_sugestao():
    # "RENÚNCIA QUE FAZ FULANA" pode ser de usufruto, de direitos hereditários
    # ou de mandato. Quem decide é o tabelião.
    s = sugerir("RENÚNCIA QUE FAZ FABIO LOPES SALES MARTINS")
    assert s["certeza"] == "nenhuma"
    assert s["natureza_censec"] is None
    assert s["evidencia"]          # mas mostra o que leu


# ---------------------------------------------------------------- resumo

def test_o_resumo_agrupa_para_confirmar_em_lote():
    sugestoes = [sugerir("COMPRA E VENDA") for _ in range(24)]
    sugestoes += [sugerir("DIVÓRCIO DIRETO CONSENSUAL") for _ in range(5)]
    r = NN.resumo(sugestoes)
    assert r[0]["atos"] == 24 and r[0]["natureza_censec"] == 6
    assert r[1]["atos"] == 5 and r[1]["tipo_cesdi"] == 4
