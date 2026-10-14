"""
Medir UMA pasta e responder sobre TODAS.

O QUE ACONTECEU
    As 3.644 assinaturas foram trazidas do `\\\\servidor\\C11\\Firmas` para
    `arquivos\\eoficio\\Firmas`, dentro do acervo, num caminho local que o
    serviço enxerga. A tela continuou dizendo "nenhuma assinatura localizada".

    Não era a cópia: era a medição. A tela indexava a pasta gravada na
    configuração — que seguia sendo o UNC morto — e informava o resultado como
    se fosse sobre o sistema inteiro. Uma resposta que parece medição é pior
    que nenhuma, porque encerra a investigação.

O QUE ESTES TESTES PROTEGEM
    Quem procura em várias pastas tem de medir as várias.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_imagens as RIMG          # noqa: E402


def montar(tmp_path):
    """Um acervo com as firmas, e um UNC morto ao lado."""
    acervo = tmp_path / "arquivos" / "eoficio" / "Firmas"
    acervo.mkdir(parents=True)
    for nome in ("RF210703-1.JPG", "RF210705-1.JPG", "RF180633-1.JPG"):
        (acervo / nome).write_bytes(b"jpeg")
    morta = tmp_path / "servidor" / "C11" / "Firmas"      # nunca criada
    return acervo, morta


def test_a_pasta_morta_sozinha_nao_acha_nada(tmp_path):
    # O estado que o usuário via, e que estava correto para o que se mediu.
    _acervo, morta = montar(tmp_path)
    r = RIMG.diagnostico(["RF210703-1.JPG"], morta)
    assert r["raiz_existe"] is False
    assert r["achadas"] == 0


def test_com_as_duas_pastas_o_acervo_responde(tmp_path):
    acervo, morta = montar(tmp_path)
    r = RIMG.diagnostico(["RF210703-1.JPG", "RF210705-1.JPG"], [acervo, morta])
    assert r["raiz_existe"] is True
    assert r["achadas"] == 2
    assert r["perdidas"] == 0
    # E o rótulo mostra a pasta que de fato respondeu, não a que foi pedida.
    assert "eoficio" in r["raiz"]
    assert str(morta) not in r["raiz"]


def test_a_ordem_das_raizes_decide_o_desempate(tmp_path):
    acervo, _morta = montar(tmp_path)
    outra = tmp_path / "outra"
    outra.mkdir()
    (outra / "RF210703-1.JPG").write_bytes("a cópia velha".encode("utf-8"))
    indice, _n, _ex, _abertas = RIMG.indexar_varias([acervo, outra])
    assert RIMG.achar("RF210703-1.JPG", indice).startswith(str(acervo))
    indice, _n, _ex, _abertas = RIMG.indexar_varias([outra, acervo])
    assert RIMG.achar("RF210703-1.JPG", indice).startswith(str(outra))


def test_pasta_que_nao_abre_e_simplesmente_pulada(tmp_path):
    acervo, morta = montar(tmp_path)
    _i, arquivos, _ex, abertas = RIMG.indexar_varias([morta, acervo, morta])
    assert abertas == [acervo]
    assert arquivos == 3


def test_nenhuma_pasta_abrindo_o_diagnostico_ainda_responde(tmp_path):
    r = RIMG.diagnostico(["RF210703-1.JPG"],
                         [tmp_path / "a", tmp_path / "b"])
    assert r["raiz_existe"] is False
    assert r["perdidas"] == 1
    # Os dois lados continuam visíveis: é o que permite comparar.
    assert r["exemplos_perdidos"] == ["RF210703-1.JPG"]
    assert r["exemplos_disco"] == []


def test_uma_pasta_so_continua_funcionando_como_antes(tmp_path):
    # A assinatura antiga da função não pode ter mudado: o Registro de Imóveis
    # chama `diagnostico(nomes, raiz)` com uma pasta só.
    acervo, _morta = montar(tmp_path)
    r = RIMG.diagnostico(["RF180633-1.JPG"], acervo)
    assert r["achadas"] == 1
    assert r["arquivos"] == 3
