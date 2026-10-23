"""
Testes da carga do acervo de notas (`notas_import`) no PostgreSQL.

O QUE ELES CONFEREM
    A carga e repetivel: rodar duas vezes nao duplica nada, e a segunda vez
    conta tudo como `*_ja_existentes`. E o que nao da para aproveitar vai para
    `nt_rejeitados`, em vez de derrubar a carga inteira.

POR QUE EXISTEM — revisao do L057, 18/10/2026
    O INSERT antigo, que ignorava conflito, no SQLite tambem descartava calado a
    linha com NULL em coluna NOT NULL. O `ON CONFLICT DO NOTHING` do PostgreSQL
    so cobre unicidade, e um NULL ali derrubaria a carga. A linha minima de cada
    arquivo (so a chave, a data e o nome) passa por todos os NOT NULL das
    tabelas que a carga grava sem nenhuma excecao.

Os dados sao ficticios.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

from bd_nativo import banco                    # noqa: E402
from notas_import import ARQUIVOS, importar    # noqa: E402

# Cada arquivo traz uma linha completa e, quando cabe, uma linha MINIMA: so a
# chave, a data e o nome, sem os campos que viram coluna NOT NULL com padrao
# (quantidade, tipo de pessoa, ativo, complemento do livro...).
ACERVO = {
    "censec_tipos": [{"tipo": "CEP", "codigo": 1, "descricao": "ESCRITURA"}],
    "censec_naturezas": [{"intCodigoNaturezaEscritura": 1, "intCodigoTipoAto": 1,
                          "strDescricao": "COMPRA E VENDA"}],
    "censec_qualificacoes": [{"intCodigo": 1, "strCENSEC": "CEP",
                              "strDescricao": "OUTORGANTE"}],
    "doi_transacoes": [{"intCodigoDOI": 11, "strDescricao": "COMPRA E VENDA",
                        "bitativo": True}],
    "doi_tipos_imovel": [{"Id": 1, "descricao": "Casa"}],
    "cartoes": [
        {"intCodigoFirma": 101, "strNome": "FULANO DE TAL EXEMPLO",
         "strTipoPessoa": "F", "strCPF": "000.000.000-00", "bitAtivo": 1,
         "bitPPE": 0, "dtmAbertura": "2020-01-02 00:00:00"},
        {"intCodigoFirma": 102, "strNome": "BELTRANA EXEMPLO"},
        {"intCodigoFirma": 103},
    ],
    "imagens": [
        {"intCodigoFirma": 101, "strNomeDigital": "RF000101-2.JPG",
         "strPath": "C:\\Firmas", "bitFavorito": 1},
        {"intCodigoFirma": 999, "strNomeDigital": "RF000999-1.JPG"},
    ],
    "reconhecimentos": [
        {"intID": 1, "dtmData": "2026-01-05 10:00:00", "strselo": "SELO-TESTE-1",
         "strTextoMontado": "RECONHECO POR SEMELHANCA A FIRMA DE FULANO."},
        {"intID": 2, "dtmData": "2026-01-05 11:00:00"},
    ],
    "reconhecimento_partes": [{"strSelo": "SELO-TESTE-1", "intCodigoFirma": 101,
                               "intCodigoServico": 415}],
    "presencas": [{"intChave": 1, "strNome": "FULANO DE TAL EXEMPLO",
                   "dtmData": "2026-01-05 10:00:00", "strSelo": "SELO-TESTE-1"}],
    "autenticacoes": [{"intID": 1, "dtmData": "2026-01-06 09:00:00"}],
    "livros": [
        {"intLivro": 28, "strDescricaoLivro": "LIVRO DE ESCRITURA", "intNFL": 200,
         "intFolha": 63, "bitAtivo": 1},
        {"intLivro": 5},
    ],
    "modelos_procuracao": [{"intChave": 1, "strProcuracao": "PROCURACAO AD JUDICIA",
                            "memTexto": "{\\rtf1{\\fonttbl{\\f0 Arial;}}Outorga poderes.\\par}"}],
    "modelos_escritura": [{"intChave": 2, "strEscritura": "COMPRA E VENDA",
                           "memTexto": "Texto do modelo.", "strCENSEC": "CEP",
                           "intNaturezaOperacao_CENSEC": 1, "bitComImovel": 1}],
    "procuracoes": [
        {"intProtocolo": 500, "dtmData": "2026-02-01 00:00:00", "intLivro": 5,
         "intFolha": 10, "intCodigoTipoProcuracao": 1, "memProcuracao": "Teor."},
        {"intProtocolo": 501, "dtmData": "2026-02-02 00:00:00"},
    ],
    "outorgantes": [{"intProtocolo": 500, "intCodigoOutorgante": 101}],
    "outorgados": [{"intProtocolo": 500, "intCodigoOutorgado": 102}],
    "escrituras": [
        {"id": 900, "strProtocolo": "2026.01.001", "dtmData": "2026-03-01 00:00:00",
         "intLivroRegistro": 28, "strLivro_Registro": "28", "strFolha_Registro": "48",
         "intCodigoTipoEscritura": 2, "memEscritura": "Teor.",
         "curValorTransacao": 1500.5},
        {"id": 901, "dtmData": "2026-03-02 00:00:00"},
    ],
    "escritura_partes": [{"strProtocolo": "2026.01.001", "intCodigoParte": 101,
                          "strQualificacao": "VENDEDOR"}],
}

TABELAS = ("nt_cartoes", "nt_cartao_imagens", "nt_reconhecimentos",
           "nt_reconhecimento_partes", "nt_presencas", "nt_autenticacoes",
           "nt_livros", "nt_modelos", "nt_atos", "nt_ato_partes",
           "nt_censec_tipos", "nt_censec_naturezas", "nt_censec_qualificacoes",
           "nt_doi_transacoes", "nt_doi_tipos_imovel")


@pytest.fixture
def pasta(tmp_path) -> Path:
    for chave, linhas in ACERVO.items():
        (tmp_path / ARQUIVOS[chave]).write_text(
            "".join(json.dumps(l, ensure_ascii=False) + "\n" for l in linhas),
            encoding="utf-8")
    return tmp_path


def _contagens(con) -> dict[str, int]:
    bd = banco(con)
    return {t: int(bd.valor(f"SELECT count(*) AS n FROM {t}")) for t in TABELAS}


def test_linha_minima_entra_e_a_carga_nao_cai(pasta):
    con = conexao_de_teste()
    contas = importar(con, pasta)
    con.commit()

    assert contas["cartoes"] == 2
    assert contas["rejeitados_nt_cartoes"] == 1          # sem nome
    assert contas["imagens"] == 1
    assert contas["rejeitados_nt_cartao_imagens"] == 1   # cartao que nao veio
    assert contas["reconhecimentos"] == 2
    assert contas["reconhecimento_partes"] == 1
    assert contas["presencas"] == 1
    assert contas["autenticacoes"] == 1
    assert contas["livros"] == 2
    assert contas["modelos_procuracao"] == 1
    assert contas["modelos_escritura"] == 1
    assert contas["procuracoes"] == 2
    assert contas["escrituras"] == 2
    assert contas["ato_partes"] == 3
    assert not any(k.endswith("_ja_existentes") for k in contas)

    bd = banco(con)
    minimo = bd.um("SELECT tipo_pessoa, ativo, pessoa_exposta FROM nt_cartoes"
                   " WHERE origem_chave = %s", ("102",))
    assert (minimo["tipo_pessoa"], minimo["ativo"], minimo["pessoa_exposta"]) == ("F", 1, 0)
    assert bd.valor("SELECT quantidade FROM nt_reconhecimentos"
                    " WHERE origem_chave = %s", ("2",)) == 1
    assert bd.valor("SELECT folhas FROM nt_autenticacoes") == 1
    assert bd.valor("SELECT complemento FROM nt_livros WHERE numero = %s", ("5",)) == ""
    assert bd.valor("SELECT situacao FROM nt_atos WHERE origem_chave = %s",
                    ("PROC:501",)) == "LAVRADO"
    escritura = bd.um("SELECT a.livro_id, l.numero, a.valor_transacao FROM nt_atos a"
                      " JOIN nt_livros l ON l.id = a.livro_id"
                      " WHERE a.origem_chave = %s", ("ESC:900",))
    assert (escritura["numero"], escritura["valor_transacao"]) == ("28", 150050)
    presenca = bd.um("SELECT p.reconhecimento_id, r.origem_chave FROM nt_presencas p"
                     " JOIN nt_reconhecimentos r ON r.id = p.reconhecimento_id")
    assert presenca["origem_chave"] == "1"
    situacao = bd.valor("SELECT situacao FROM nt_importacoes ORDER BY id DESC LIMIT 1")
    assert situacao == "CONCLUIDA"


def test_segunda_carga_nao_duplica_e_conta_ja_existentes(pasta):
    con = conexao_de_teste()
    importar(con, pasta)
    con.commit()
    antes = _contagens(con)

    contas = importar(con, pasta)
    con.commit()

    assert _contagens(con) == antes
    for chave in ("cartoes", "imagens", "reconhecimentos", "presencas",
                  "autenticacoes", "livros", "modelos_procuracao",
                  "modelos_escritura", "procuracoes", "escrituras"):
        assert chave not in contas, chave
        assert contas[f"{chave}_ja_existentes"] >= 1, chave
    assert contas["cartoes_ja_existentes"] == 2
    assert contas["escrituras_ja_existentes"] == 2
    # Partes so se gravam junto do ato novo: na segunda carga, nenhuma.
    assert "ato_partes" not in contas
    assert "reconhecimento_partes" not in contas
    # Os dominios se atualizam (UPSERT), e por isso contam de novo.
    assert contas["censec_tipos"] == 1
