"""Minuta / traslado: titulo do ato nao pode repetir no inicio do teor."""
import notas_teor as NT


def test_tira_paragrafo_so_com_titulo():
    teor = (
        '<p style="text-align:center;font-weight:bold">'
        "ESCRITURA PUBLICA DE DIVORCIO CONSENSUAL DIRETO</p>"
        "<p>Saibam quantos este publico instrumento virem</p>"
    )
    limpo = NT.teor_sem_titulo_duplicado(
        teor, "Escritura publica de divorcio consensual direto")
    assert "DIVORCIO CONSENSUAL" not in limpo.split("Saibam")[0]
    assert "Saibam quantos" in limpo


def test_tira_titulo_colado_no_comparecimento():
    teor = (
        "<p><b>ESCRITURA PUBLICA DE DISSOLUCAO DE UNIAO ESTAVEL.</b> "
        "Saibam quantos este publico instrumento virem</p>"
    )
    limpo = NT.teor_sem_titulo_duplicado(
        teor, "Escritura publica de dissolucao de uniao estavel")
    assert limpo.startswith("<p>Saibam quantos")
    assert "DISSOLUCAO" not in limpo


def test_nao_mexe_se_titulo_nao_casa():
    teor = "<p>Saibam quantos este publico instrumento virem</p>"
    assert NT.teor_sem_titulo_duplicado(teor, "Compra e venda") == teor
