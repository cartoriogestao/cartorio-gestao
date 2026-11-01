"""A PARTE DO BACKUP QUE SÓ O TITULAR ABRE.

Ordem do oficial (31/10/2026): o balanço «deve ficar criptografado no backup da serventia», e
na troca de delegatário «o livro-caixa não ficaria aberto para o novo».
"""
from __future__ import annotations

import sys
import zipfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import backup as BKP
import cofre_do_titular as COT
import despesas as DP

AGORA = datetime(2026, 10, 31, 9, 0, tzinfo=timezone(timedelta(hours=-3)))
SENHA = "senha-ficticia-do-teste"
MARCA = "FAVORECIDO_PRIVADO_XYZ"


def _chave():
    return COT.gerar_chave(SENHA, de_quem="MARIO EXEMPLO", agora=AGORA)


def test_a_senha_curta_e_recusada():
    with pytest.raises(COT.CofreDoTitularError, match="ao menos 12"):
        COT.gerar_chave("curta", de_quem="MARIO", agora=AGORA)


def test_a_senha_nao_aparece_e_a_publica_nao_abre(tmp_path):
    chave = _chave()
    assert SENHA not in "".join(chave.values())
    assert "ENCRYPTED PRIVATE KEY" in chave[COT.CHAVE_PRIVADA]
    origem = tmp_path / "dado"
    origem.write_bytes(MARCA.encode() * 100)
    fechado = COT.fechar(origem, tmp_path / "fechado", chave)
    assert MARCA.encode() not in fechado.read_bytes()
    assert COT.abrir(fechado, tmp_path / "volta", SENHA)["de"] == "MARIO EXEMPLO"
    assert (tmp_path / "volta").read_bytes() == origem.read_bytes()


def test_a_senha_errada_nao_abre(tmp_path):
    origem = tmp_path / "dado"
    origem.write_bytes(b"x")
    fechado = COT.fechar(origem, tmp_path / "fechado", _chave())
    with pytest.raises(COT.CofreDoTitularError, match="não abre"):
        COT.abrir(fechado, tmp_path / "volta", "outra-senha-qualquer")
    assert not (tmp_path / "volta").exists()


def test_o_arquivo_estranho_e_recusado(tmp_path):
    estranho = tmp_path / "estranho"
    estranho.write_bytes(b"nao e a parte do titular")
    with pytest.raises(COT.CofreDoTitularError, match="não é a parte do titular"):
        COT.abrir(estranho, tmp_path / "volta", SENHA)


def test_o_livro_diario_fecha_junto_e_a_ordem_de_apagar_tem_todas():
    assert {"ld_despesas", "ld_geracoes"} <= set(COT.TABELAS)
    assert set(COT.NA_ORDEM_DE_APAGAR) == set(COT.TABELAS)
    ordem = COT.NA_ORDEM_DE_APAGAR
    assert ordem.index("dp_eventos") < ordem.index("dp_despesas")
    assert ordem.index("cl_marcacoes") < ordem.index("ld_despesas")


def test_o_anexo_privado_e_o_da_pasta_das_despesas():
    assert COT.e_anexo_privado(Path("despesas/recibo.pdf"))
    assert not COT.e_anexo_privado(Path("ri/despesas.pdf"))


def _com_despesa(casa):
    with casa["db"].transaction() as con:
        i = DP.cadastrar(con, agora=AGORA, por="mario", origem="MANUAL", chave_origem=None, beneficiario_nome=MARCA,
                         beneficiario_documento="00000000191", valor_centavos=1000, vencimento="2026-11-05",
                         forma=DP.PIX_CHAVE, codigo="exemplo@example.com", descricao="Despesa privada do teste",
                         categoria="PESSOAL", documento_especie="Recibo")
        DP.guardar_anexo(con, i, nome_arquivo="recibo.pdf", conteudo=b"%PDF ANEXO_PRIVADO", pasta=casa["acervo"] / "despesas",
                         usuario_id=None, agora="2026-10-31T09:00:00")
    return i


def test_sem_a_chave_o_pacote_sai_como_sempre(cg_casa_logada, tmp_path):
    casa = cg_casa_logada
    _com_despesa(casa)
    pacote = BKP.gerar_pacote(casa["db"], tmp_path / "p.zip", casa["acervo"], com_arquivos=True)
    with zipfile.ZipFile(pacote) as zf:
        nomes = [n.replace("\\", "/") for n in zf.namelist()]
    assert not [n for n in nomes if n.startswith("privado")]
    assert [n for n in nomes if n.startswith("arquivos/despesas/")], "sem chave, nada se perde"


def test_com_a_chave_o_dado_sai_do_banco_e_volta_com_a_senha(cg_casa_logada, tmp_path):
    casa = cg_casa_logada
    _com_despesa(casa)
    COT.criar_chave(casa["db"], SENHA, SENHA, de_quem="MARIO", agora=AGORA)
    pacote = BKP.gerar_pacote(casa["db"], tmp_path / "p.zip", casa["acervo"], com_arquivos=True)
    assert BKP.conferir(pacote) is None
    with zipfile.ZipFile(pacote) as zf:
        nomes = [n.replace("\\", "/") for n in zf.namelist()]
        tudo = b"".join(zf.read(n) for n in zf.namelist())
        manifesto = zf.read(BKP.NOME_MANIFESTO).decode("utf-8")
    assert COT.NOME_DAS_TABELAS in nomes and COT.NOME_DOS_ANEXOS in nomes
    assert not [n for n in nomes if n.startswith("arquivos/despesas/")]
    assert MARCA.encode() not in tudo and b"ANEXO_PRIVADO" not in tudo
    assert '"dp_despesas": 0' in manifesto, "é o que o teste de restauração acha"
    saidas = COT.abrir_do_pacote(pacote, tmp_path / "aberto", SENHA)
    assert [p.name for p in saidas] == ["tabelas_do_titular.dump", "anexos_do_titular.zip"]


def test_trocar_a_chave_pede_a_senha_atual(cg_casa_logada):
    db = cg_casa_logada["db"]
    COT.criar_chave(db, SENHA, SENHA, de_quem="MARIO", agora=AGORA)
    antes = COT.dados_da_chave(db)
    with pytest.raises(COT.CofreDoTitularError, match="não abre"):
        COT.criar_chave(db, "nova-senha-qualquer", "nova-senha-qualquer", de_quem="OUTRO", agora=AGORA,
                        senha_atual="errada-errada-errada")
    assert COT.dados_da_chave(db) == antes
    COT.criar_chave(db, "nova-senha-qualquer", "nova-senha-qualquer", de_quem="MARIO", agora=AGORA, senha_atual=SENHA)
    assert COT.dados_da_chave(db) != antes


def test_a_tela_cria_a_chave_e_nao_guarda_a_senha(cg_casa_logada):
    import re
    casa = cg_casa_logada
    c, url = casa["c"], "/administrativo/despesas/configuracao"
    tela = c.get(url).get_data(as_text=True)
    assert "saem abertos no backup" in tela
    token = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', tela).group(1)
    r = c.post(url, data={"csrf_token": token, "acao": "chave_do_titular", "senha": SENHA, "confirmacao": SENHA},
               follow_redirects=True).get_data(as_text=True)
    assert "Chave do titular criada" in r and SENHA not in r
    assert SENHA not in "".join(COT.dados_da_chave(casa["db"]).values())
    assert "saem fechados no backup" in r
