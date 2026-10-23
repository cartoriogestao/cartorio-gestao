"""O ENSAIO DE CAMPOS DA CARGA DA CRC — vai além do XSD.

    «crie um teste do sistema que consiga verificar além do xsd, mas olhe se
     efetivamente o arquivo importado está com os campos perfeitamente
     preenchidos» — o oficial, 13/09/2026, depois de simular a importação
     do acervo em `.docx` numa cópia do banco.

O QUE O XSD PROVA, E O QUE ELE NÃO PROVA
    `tests/test_crc_carga.py` já confere o XML contra
    `schemas/cargaRegistrosCompleto.xsd`, com exemplos escritos à mão — e
    isso prova a FORMA: que a tag existe, que o tipo bate, que o valor está
    num enum aceito. **O XSD não prova o CONTEÚDO.** Uma tag `<NOME></NOME>`
    vazia, uma tag `<NOME>None</NOME>` (o `str(None)` do Python vazando para
    dentro do XML), um `<CNS>1234567</CNS>` com sete dígitos, ou uma tag com
    o caractere de substituição Unicode (`\\ufffd`, a marca de um texto lido
    com o encoding errado — o mesmo defeito que corrompeu o caminho da pasta
    «CERTIDÕES E TERMOS REUNIDOS» ao passar pela linha de comando em
    13/09/2026) são todas **sintaticamente válidas** para o schema, e são
    exatamente o tipo de defeito que só aparece depois, na recusa da Central.

ESTE ARQUIVO RODA CONTRA O QUE REALMENTE ESTÁ GRAVADO NESTA MÁQUINA
    E não contra exemplos fabricados à mão — é a mesma régua de
    `test_acervo_carga.py::test_contra_o_acervo_real`: teste de mesa prova a
    regra, ensaio contra o dado real prova o dado. Ele audita TODO assento
    que `rc_assentos` tiver — do E-Ofício, de lavratura nova, ou da
    importação em `.docx` —, porque a régua vale para qualquer origem: o
    manual da CRC não sabe de onde o dado veio.

    Só lê (`crc_carga.montar()` não grava nada) e pula quando o banco de
    produção não existe nesta máquina, como os outros ensaios já pulam.
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path
from typing import Any

import pytest
from lxml import etree


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — referencia acervo_eoficio ou sqlite de producao
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import crc_carga as CRC                                          # noqa: E402

PRODUCAO = Path(r"C:\ProgramData\CartorioGestao\cartorio_gestao.sqlite3")
CNS = "000000"

# Lixo de programação que uma tag NUNCA deveria carregar — é `str(None)`,
# `str(float('nan'))` ou o `undefined`/`[object Object]` do JavaScript
# vazando para dentro de um campo que deveria estar vazio, e não com a
# PALAVRA que descreve a ausência.
LIXO_DE_PROGRAMACAO = re.compile(
    r"^(none|null|undefined|nan|\[object object\])$", re.I)

DATA_DD_MM_AAAA = re.compile(r"^\d{2}/\d{2}/\d{4}$")

pytestmark = pytest.mark.skipif(
    not PRODUCAO.exists(),
    reason="o banco de produção não está nesta máquina")


def _con() -> sqlite3.Connection:
    return sqlite3.connect(f"file:{PRODUCAO}?mode=ro", uri=True)


def _todos_os_ids(con: sqlite3.Connection) -> list[int]:
    return [r[0] for r in
           con.execute("SELECT id FROM rc_assentos ORDER BY id").fetchall()]


def _montar_tudo() -> dict[str, Any]:
    """`crc_carga.montar()` sobre TODOS os assentos de produção. Só lê."""
    con = _con()
    try:
        ids = _todos_os_ids(con)
        if not ids:
            pytest.skip("não há assento nenhum no banco desta máquina")
        return CRC.montar(con, ids, cns=CNS)
    finally:
        con.close()


@pytest.fixture(scope="module")
def xsd():
    return etree.XMLSchema(etree.parse(
        str(RAIZ / "schemas" / "cargaRegistrosCompleto.xsd")))


@pytest.fixture(scope="module")
def montado() -> dict[str, Any]:
    return _montar_tudo()


@pytest.fixture(scope="module")
def doc(montado):
    return etree.fromstring(montado["xml"].encode("utf-8"))


def test_o_xml_da_producao_bate_com_o_xsd(montado, xsd, doc):
    ok = xsd.validate(doc)
    assert ok, [str(e) for e in xsd.error_log]


def test_nenhuma_tag_carrega_lixo_de_programacao(doc):
    """`None`/`null`/`undefined`/`nan` dentro de uma tag é bug de
    formatação — o campo deveria ter saído vazio, e saiu com o texto que o
    programa usa para dizer "não tenho valor", que não é a mesma coisa."""
    achados = [f"<{el.tag}>{(el.text or '').strip()}</{el.tag}>"
              for el in doc.iter()
              if (el.text or "").strip()
              and LIXO_DE_PROGRAMACAO.match((el.text or "").strip())]
    assert achados == []


def test_nenhuma_tag_tem_caractere_de_encoding_quebrado(montado):
    """O caractere de substituição Unicode (`\\ufffd`) é a marca de um texto
    lido com o encoding errado — o mesmo defeito medido ao passar um
    caminho de pasta acentuado pela linha de comando em 13/09/2026, agora
    conferido dentro do próprio XML antes de ele sair da casa."""
    achados = re.findall(r"<(\w+)>([^<]*\ufffd[^<]*)</\1>", montado["xml"])
    assert achados == []


def test_os_campos_obrigatorios_do_manual_nao_vao_vazios(doc):
    """`crc_carga.OBRIGATORIOS` são os `*` do manual — sem eles a Central
    recusa o registro inteiro. Isto audita, tag por tag, todo registro que
    efetivamente foi para o XML (quem falta um obrigatório nem chega a
    entrar — `o_que_falta` retém antes — então aqui só se espera achar
    vazio se houver um bug na montagem, não uma falta real de dado)."""
    vazios = []
    for especie, (_, inclusao, _) in CRC.MOVIMENTO_DA_ESPECIE.items():
        obrigatorios = CRC.OBRIGATORIOS.get(especie)
        if not obrigatorios:
            continue
        for registro in doc.iter(inclusao):
            for nome_tag in obrigatorios:
                el = registro.find(nome_tag)
                if el is None or not (el.text or "").strip():
                    vazios.append(f"{inclusao}.{nome_tag}")
    assert vazios == [], sorted(set(vazios))[:20]


def test_as_datas_do_xml_batem_com_dd_mm_aaaa(doc):
    ruins = []
    for tag in ("DATAREGISTRO", "DATANASCIMENTO", "DATACASAMENTO",
               "DATAOBITO", "DATANASCIMENTOFALECIDO"):
        for el in doc.iter(tag):
            texto = (el.text or "").strip()
            if texto and not DATA_DD_MM_AAAA.match(texto):
                ruins.append(f"{tag}={texto!r}")
    assert ruins == [], ruins[:20]


def test_o_cns_tem_exatamente_seis_digitos(doc):
    achados = [(el.text or "").strip() for el in doc.iter("CNS")]
    assert achados, "não achei tag CNS nenhuma no XML"
    ruins = [v for v in achados if not re.match(r"^\d{6}$", v)]
    assert ruins == []


def test_a_matricula_tem_32_digitos_quando_presente(doc):
    ruins = [(el.text or "").strip() for el in doc.iter("MATRICULA")
            if (el.text or "").strip()
            and not re.match(r"^\d{32}$", (el.text or "").strip())]
    assert ruins == [], ruins[:20]


def test_regime_de_casamento_nunca_sai_vazio(doc):
    """Ao contrário de SEXO e de outros campos fechados, o XSD não lista
    `''` entre os valores de `REGIMECASAMENTO` — vazio aqui é sempre defeito
    de montagem, nunca falta de dado (que vira `IGNORADO`)."""
    vazios = [1 for el in doc.iter("REGIMECASAMENTO")
             if not (el.text or "").strip()]
    assert not vazios


def test_retidos_e_a_arrumar_sao_o_espelho_do_que_falta(montado):
    """`retidos` (bloqueiam) e `a_arrumar` (avisam, mas sobem) não podem se
    confundir: um assento retido não pode aparecer nos dois ao mesmo tempo
    dizendo coisas contraditórias, e as duas listas têm de ter `assento_id`
    e `nome` em toda linha — sem isso, quem for corrigir não sabe qual
    assento é."""
    retidos_ids = {r["assento_id"] for r in montado["retidos"]}
    arrumar_ids = {r["assento_id"] for r in montado["a_arrumar"]}
    assert not (retidos_ids & arrumar_ids), (
        "assento retido e com aviso ao mesmo tempo — "
        + str(retidos_ids & arrumar_ids))
    for r in montado["retidos"] + montado["a_arrumar"]:
        assert r.get("assento_id"), r
        assert r.get("faltas") or r.get("arrumar"), r
