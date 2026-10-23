"""O oficial diz de quem é o nome que não casou — lote LH10, 21/10/2026.

`tools/ajuste_criado_por_matriculas.sql` (LX09) devolve a
`ri_matriculas.criado_por` o id do usuário cujo nome de exibição é o valor que o
ajuste guardou. No ensaio com o banco real de 21/10 o seco disse: «com
aplicar=1 este script RECUSARIA: 2 valor(es) não casam com nenhum usuário e 0
casam com mais de um». Só o oficial sabe de quem são. O LH10 deu a ele a
`cg_ajuste_de_para` (valor_original, user_id) e o modo `mostrar_valores=1`, que
mostra os valores só na tela de quem roda no servidor.

O QUE ESTES TESTES GUARDAM (pela carga, pelo ajuste no modo guardar e pelo psql
de verdade, num SQLite de fixture sem dado real — `virada_de_teste.py`, onde um
nome casa com um usuário, um com nenhum e um com dois):
    - o seco conta, NÃO mostra nome nenhum e não grava nada (nem a tabela);
    - gravar sem a palavra do oficial continua recusando;
    - `mostrar_valores=1` mostra os nomes, não grava matrícula, recusa junto
      com aplicar=1 e deixa a tabela do de-para pronta;
    - a linha que ele imprime para anotar funciona como está (só troca o id);
    - anotado o dono, grava; anotado «sem dono» (NULL), a matrícula fica NULL
      com o original guardado; rodar de novo não muda nada;
    - o de-para vale mais que o nome.
"""
from __future__ import annotations

import hashlib
import re
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent))
import virada_de_teste as V  # noqa: E402
from virada_de_teste import virada  # noqa: E402,F401  (a fixture)

import banco_pg  # noqa: E402

pytestmark = pytest.mark.skipif(not banco_pg.ativo(), reason="a virada é para o PostgreSQL")

NOMES = (V.CASA_COM_UM, V.NAO_CASA, V.CASA_COM_DOIS)


def _depois_do_ajuste(v) -> None:
    _, feito = V.ate_o_ajuste(v, nao_numericos="guardar")
    assert feito.returncode == 0, feito.saida


def _criado_por(schema: str) -> dict:
    return {r["id"]: r["criado_por"] for r in V.sql(
        schema, "SELECT id, criado_por FROM ri_matriculas ORDER BY id")}


def _chave(valor: str) -> str:
    return hashlib.md5(valor.encode("utf-8")).hexdigest()[:12]


def _anotar(schema: str, saida: str, valor: str, user_id: str) -> None:
    """Roda a linha «para_anotar» que o modo mostrar_valores imprimiu para o
    valor, trocando só o <id> — como o oficial faria no psql."""
    linhas = [m.group(0) for m in re.finditer(r"INSERT INTO \S+\.cg_ajuste_de_para .*?;", saida)
              if f"'{_chave(valor)}'" in m.group(0)]
    assert len(linhas) == 1, saida
    V.sql(schema, linhas[0].replace("<id>", user_id))


def test_o_seco_conta_sem_mostrar_nome_e_nao_grava_nada(virada):
    _depois_do_ajuste(virada)
    antes = _criado_por(virada.schema)
    feito = V.rodar_sql(V.LX09, virada.schema)
    assert feito.returncode == 0, feito.saida
    assert ("SECO: com aplicar=1 este script RECUSARIA: 1 valor(es) não casam com nenhum "
            "usuário e 1 casam com mais de um") in feito.saida
    assert "SECO, nada foi gravado" in feito.saida
    for nome in NOMES:
        assert nome not in feito.saida
    assert _criado_por(virada.schema) == antes == {1: 1, 2: None, 3: None, 4: None, 5: None,
                                                   6: None, 7: None, 8: None}
    assert not V.tem_tabela(virada.schema, "cg_ajuste_de_para")


def test_gravar_sem_a_palavra_do_oficial_continua_recusando(virada):
    _depois_do_ajuste(virada)
    antes = _criado_por(virada.schema)
    feito = V.rodar_sql(V.LX09, virada.schema, aplicar="1")
    assert feito.returncode != 0, feito.saida
    assert "RECUSADO, NADA FOI ALTERADO: 1 valor(es) guardado(s) não casam" in feito.saida
    assert "mostrar_valores=1" in feito.saida
    for nome in NOMES:
        assert nome not in feito.saida
    assert _criado_por(virada.schema) == antes


def test_mostrar_valores_mostra_os_nomes_so_no_seco_e_deixa_o_de_para_pronto(virada):
    _depois_do_ajuste(virada)
    antes = _criado_por(virada.schema)
    feito = V.rodar_sql(V.LX09, virada.schema, mostrar_valores="1")
    assert feito.returncode == 0, feito.saida
    assert "NOME DE PESSOA" in feito.saida
    assert V.NAO_CASA in feito.saida and V.CASA_COM_DOIS in feito.saida
    assert _chave(V.NAO_CASA) in feito.saida and _chave(V.CASA_COM_DOIS) in feito.saida
    # o que casa com um usuário só não pede decisão e não ganha linha de anotar
    assert _chave(V.CASA_COM_UM) not in feito.saida
    assert "nenhuma matrícula foi gravada" in feito.saida
    assert _criado_por(virada.schema) == antes
    assert V.sql(virada.schema, "SELECT count(*) AS n FROM cg_ajuste_de_para") == [{"n": 0}]

    junto = V.rodar_sql(V.LX09, virada.schema, mostrar_valores="1", aplicar="1")
    assert junto.returncode != 0, junto.saida
    assert "mostrar_valores=1 só roda no seco" in junto.saida
    for nome in NOMES:
        assert nome not in junto.saida
    assert _criado_por(virada.schema) == antes


def test_anotado_o_dono_grava_e_o_sem_dono_fica_nulo_com_o_original_guardado(virada):
    _depois_do_ajuste(virada)
    mostrado = V.rodar_sql(V.LX09, virada.schema, mostrar_valores="1")
    assert mostrado.returncode == 0, mostrado.saida
    _anotar(virada.schema, mostrado.saida, V.NAO_CASA, "3")
    _anotar(virada.schema, mostrado.saida, V.CASA_COM_DOIS, "NULL")
    assert V.sql(virada.schema, "SELECT valor_original, user_id FROM cg_ajuste_de_para "
                                "ORDER BY valor_original") == [
        {"valor_original": V.CASA_COM_DOIS, "user_id": None},
        {"valor_original": V.NAO_CASA, "user_id": 3}]

    seco = V.rodar_sql(V.LX09, virada.schema)
    assert seco.returncode == 0, seco.saida
    assert "todo valor a preencher tem dono certo" in seco.saida
    assert "RECUSARIA" not in seco.saida

    feito = V.rodar_sql(V.LX09, virada.schema, aplicar="1")
    assert feito.returncode == 0, feito.saida
    assert "ajuste_criado_por_matriculas.sql: GRAVADO" in feito.saida
    for nome in NOMES:
        assert nome not in feito.saida
    esperado = {1: 1, 2: 2, 3: 2, 4: 2, 5: 3, 6: 3, 7: None, 8: None}
    assert _criado_por(virada.schema) == esperado
    # o original continua guardado, inclusive o do que ficou sem dono
    assert V.guardados(virada.schema)[("ri_matriculas", "criado_por")] == \
        V.GUARDAVEIS[("ri_matriculas", "criado_por")]

    de_novo = V.rodar_sql(V.LX09, virada.schema, aplicar="1")
    assert de_novo.returncode == 0, de_novo.saida
    assert _criado_por(virada.schema) == esperado


def test_o_de_para_vale_mais_que_o_nome(virada):
    _depois_do_ajuste(virada)
    mostrado = V.rodar_sql(V.LX09, virada.schema, mostrar_valores="1")
    _anotar(virada.schema, mostrado.saida, V.NAO_CASA, "NULL")
    _anotar(virada.schema, mostrado.saida, V.CASA_COM_DOIS, "4")
    # o nome que casa com o usuário 2: o oficial sabe que foi o 1 quem carregou
    V.sql(virada.schema, "INSERT INTO cg_ajuste_de_para (valor_original, user_id) "
                         "VALUES (%s, 1)", (V.CASA_COM_UM,))

    feito = V.rodar_sql(V.LX09, virada.schema, aplicar="1")
    assert feito.returncode == 0, feito.saida
    assert _criado_por(virada.schema) == {1: 1, 2: 1, 3: 1, 4: 1, 5: None, 6: None, 7: 4, 8: None}


def test_o_de_para_recusa_usuario_que_nao_existe(virada):
    _depois_do_ajuste(virada)
    V.rodar_sql(V.LX09, virada.schema, mostrar_valores="1")
    with pytest.raises(Exception, match="cg_ajuste_de_para_user_id_fkey"):
        V.sql(virada.schema, "INSERT INTO cg_ajuste_de_para (valor_original, user_id) "
                             "VALUES (%s, 99)", (V.NAO_CASA,))
