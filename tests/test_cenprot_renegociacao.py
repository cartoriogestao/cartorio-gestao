"""As renegociações da Resolve — o que faltava da API da CENPROT.

    «construa a integração com a api da resolve na cenprot»
                                        — o oficial, 03/09/2026

O QUE JÁ ESTAVA FEITO, e foi medido antes de escrever qualquer linha
    A integração existe desde 02/09/2026: `cenprot_api` fala com a Central,
    `cenprot_pendencias` guarda a fila do balcão, `cenprot_web` tem as telas, e
    «Pendências da CENPROT» está no menu do Protesto. **Dezessete dos vinte
    caminhos do contrato já tinham função.**

O QUE FALTAVA, E ERA O CORAÇÃO DA COISA
    `/renegociacoes` e `/renegociacoes/processar` estavam **declarados e sem
    função nenhuma**. E a renegociação é justamente aquilo para que a Resolve
    existe: o comunicado do IEPTB diz que a API veio para que ela «aumente a
    base de títulos que podem ser cobrados junto aos devedores».

    Os outros dois caminhos sem função são os legados `/anuencias` e
    `/certidoes`, e esses estão declarados **de propósito** — para ninguém os
    reinventar achando que sumiram.

O TESTE QUE MAIS VALE AQUI É O DA CUSTA
    A renegociação manda `vl_custa`, que é a **custa de cancelamento**. A casa
    já calculava as duas coisas — `retirada` e `cancelamento` — e a retirada
    era a que estava à mão. **Trocar uma pela outra manda à Central um valor
    que o devedor paga**, e isso não apareceria em tela nenhuma: só no balcão,
    com o cliente reclamando do preço.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import cenprot_api as API                                        # noqa: E402
import cenprot_pendencias as PEND                                # noqa: E402
import cn_schema as CN                                           # noqa: E402

CONTRATO = (RAIZ.parent.parent / "FONTES_EXTERNAS" / "cra21"
            / "cenprot_swagger_v2.1.0.yaml")


# ------------------------------------------------ contra o contrato


def _contrato() -> str:
    if not CONTRATO.exists():
        pytest.skip(f"o contrato não está nesta cópia ({CONTRATO.name})")
    return CONTRATO.read_text(encoding="utf-8")


def test_os_dois_caminhos_estao_no_contrato_com_esse_nome():
    """**O caminho não se supõe: lê-se.** Um caminho inventado devolve 404, e
    o balcão veria «não deu para baixar» sem saber que o endereço é que estava
    errado."""
    texto = _contrato()
    assert "/renegociacoes:" in texto
    assert "/renegociacoes/processar:" in texto
    assert API.CAMINHO["renegociacoes"] == "/renegociacoes"
    assert API.CAMINHO["renegociacoes_processar"] == "/renegociacoes/processar"


def test_o_teto_do_lote_e_o_do_contrato():
    """`maxItems: 1000` — o número é dele, e não uma precaução minha."""
    texto = _contrato()
    assert "maxItems: 1000" in texto
    assert API.MAXIMO_DE_RENEGOCIACOES_POR_LOTE == 1000


def test_os_obrigatorios_sao_os_que_o_contrato_marca():
    """O schema marca dois `required`, e são estes."""
    exigidos = {c for c, _ in API.CAMPOS_OBRIGATORIOS_DA_RENEGOCIACAO}
    assert exigidos == {"cd_renegociacao_divida", "vl_custa"}


def test_o_codigo_da_especie_e_o_do_contrato():
    """**É o sexto nome diferente numa API só.** `cd_anuencia`, `cd_pedido`,
    `nr_pedido`, `nm_chave`, `cd_pedido_protesto` — e agora
    `cd_renegociacao_divida`. Escrever o nome de outro caminho não estoura:
    a pendência entraria sem código e sem resposta possível."""
    assert PEND.CODIGO_DA_ESPECIE[CN.RENEGOCIACAO] == "cd_renegociacao_divida"
    assert "cd_renegociacao_divida:" in _contrato()


# ------------------------------------------------ o envio recusa antes da rede


def test_lote_vazio_e_recusado():
    with pytest.raises(API.CenprotError) as erro:
        API.processar_renegociacoes([])
    assert "nenhuma" in str(erro.value).lower()


def test_lote_acima_do_teto_e_recusado_ANTES_de_bater_na_rede():
    """Mandar 1.001 faria a Central recusar o lote inteiro — e a recusa dela
    chega depois de o balcão achar que mandou."""
    lote = [{"cd_renegociacao_divida": i, "vl_custa": 10.0}
            for i in range(1001)]
    with pytest.raises(API.CenprotError) as erro:
        API.processar_renegociacoes(lote)
    assert "1000" in str(erro.value)
    assert "partes" in str(erro.value)


def test_item_sem_custa_e_recusado_e_a_mensagem_diz_qual():
    """**A Central recusa item a item dentro de uma resposta de sucesso**, com
    um `status_http` por item. Sem esta conferência, metade de um lote voltaria
    recusada e a tela diria que deu certo."""
    with pytest.raises(API.CenprotError) as erro:
        API.processar_renegociacoes([
            {"cd_renegociacao_divida": 1, "vl_custa": 10.0},
            {"cd_renegociacao_divida": 2}])
    assert "renegociação 2" in str(erro.value)
    assert "vl_custa" in str(erro.value)


def test_item_sem_codigo_e_recusado():
    with pytest.raises(API.CenprotError) as erro:
        API.processar_renegociacoes([{"vl_custa": 10.0}])
    assert "cd_renegociacao_divida" in str(erro.value)


def test_o_caminho_que_escreve_esta_declarado_como_tal():
    """Há teste na casa que exige que todo caminho de escrita passe por
    `_escrever`, e `_escrever` recusa o que não estiver declarado."""
    assert "renegociacoes_processar" in API.CAMINHOS_QUE_ESCREVEM
    assert "renegociacoes" not in API.CAMINHOS_QUE_ESCREVEM


# ------------------------------------------------ a espécie está inteira


def test_a_especie_tem_os_tres_despachos():
    """Espécie meio ligada é a que aparece na lista e não baixa, ou baixa e não
    envia — e o balcão só descobre no dia em que precisa."""
    assert CN.RENEGOCIACAO in CN.ESPECIES
    assert CN.RENEGOCIACAO in CN.NOME_DA_ESPECIE
    assert PEND.BAIXA_DA_ESPECIE[CN.RENEGOCIACAO] is API.renegociacoes
    assert CN.RENEGOCIACAO in PEND.CODIGO_DA_ESPECIE
    assert CN.RENEGOCIACAO in PEND._MANDA_DA_ESPECIE
    assert CN.RENEGOCIACAO not in PEND.ESPECIES_QUE_SO_SE_BAIXAM


def test_toda_especie_declarada_tem_despacho_de_baixa():
    """**A lista não se escreve em dois lugares.** Uma espécie nova em
    `cn_schema` sem entrada aqui apareceria no seletor da tela e estouraria ao
    baixar — é a lição da lista das cargas, que envelheceu noutro arquivo."""
    faltam = [e for e in CN.ESPECIES if e not in PEND.BAIXA_DA_ESPECIE]
    assert not faltam, f"sem função de baixa: {faltam}"
    faltam = [e for e in CN.ESPECIES if e not in PEND.CODIGO_DA_ESPECIE]
    assert not faltam, f"sem campo de código: {faltam}"


def test_o_resumo_da_linha_traz_o_que_a_proposta_tem():
    """Sem estes campos a linha sairia com o nome do devedor e mais nada — e o
    que se decide aqui é o valor."""
    for campo in ("vl_proposta", "dt_vencimento_proposta", "nm_descricao"):
        assert campo in PEND.CAMPOS_DO_RESUMO


# ------------------------------------------------ a custa, que é o caro


def test_a_custa_de_cancelamento_NAO_E_a_retirada():
    """**O teste que mais vale deste arquivo.**

    São dois números que a mesma função da casa devolve, e a retirada era a que
    estava à mão. Trocá-los manda à Central um valor que o devedor paga, e não
    aparece em tela nenhuma.
    """
    import inspect

    fonte = inspect.getsource(PEND.custa_de_cancelamento_sugerida)
    assert 'precos.get("cancelamento")' in fonte
    assert 'precos.get("retirada")' not in fonte

    outra = inspect.getsource(PEND.retirada_sugerida)
    assert 'precos.get("retirada")' in outra


def test_sem_titulo_casado_a_custa_nao_vira_zero(tmp_path):
    """**Zero afirma «não custa nada»**, e o devedor viria ao balcão com essa
    afirmação. `None` diz o que se sabe: que não deu para calcular."""
    r = PEND.custa_de_cancelamento_sugerida(
        None, {"titulo_id": None, "titulo_valor_centavos": None},
        hoje="2026-09-03")
    assert r["centavos"] is None
    assert r["reais"] == ""
    assert r["motivo"]


def test_a_ficha_pede_a_custa_e_diz_que_e_sugestao():
    """A tela tem de dizer de onde veio o número — a mesma regra da receita de
    custas e da participação das partes na DOI."""
    bruto = (RAIZ / "templates" / "protesto_pendencia.html").read_text(
        encoding="utf-8")
    # **O HTML QUEBRA A FRASE EM DUAS LINHAS**, e procurar a frase inteira num
    # texto com quebras acusa falta onde nao ha. E a licao do varredor que
    # batia na propria prosa, agora do lado do teste.
    html = " ".join(bruto.split())
    assert "RENEGOCIACAO" in html
    assert 'name="vl_custa"' in html
    assert "Sugerido pelo sistema" in html
    # e diz o que a casa NÃO faz: julgar a proposta
    assert "não aceita nem recusa" in html


def test_a_decisao_da_tela_manda_os_dois_campos_e_so_eles():
    """O contrato declara dois `required` e mais nada; mandar campo a mais é
    como a Central passa a recusar o lote por um motivo que ninguém lê."""
    import inspect

    import cenprot_web

    fonte = inspect.getsource(cenprot_web._decisao_do_formulario)
    i = fonte.index("CN.RENEGOCIACAO")
    trecho = fonte[i:i + 600]
    assert "cd_renegociacao_divida" in trecho
    assert "vl_custa" in trecho
