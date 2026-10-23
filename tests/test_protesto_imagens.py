"""
As IMAGENS DOS TITULOS que a CRA entrega.

POR QUE ELAS SAO UM MODULO, e nao um anexo qualquer
    A CRA entrega o titulo em duas partes: o registro de 600 posicoes, que o
    sistema ja lia, e a IMAGEM do papel, que vem num `.zip` a parte. A tela da
    Central lista as duas pendencias lado a lado — «Download remessa» e
    «Download imagens» —, e o sistema fazia so a primeira.

    A imagem nao e enfeite: **e o titulo**. O que se protesta e o documento.

O QUE ESTES TESTES GUARDAM
      - o NOME decodifica em tres partes, e ele foi medido num pacote real;
      - A DUPLA CHAVE: so entra quando o nosso numero E o documento do devedor
        apontam para o MESMO titulo. Nosso numero se repete entre
        apresentantes — 53 grupos e 111 titulos no acervo —, e anexar a imagem
        ao titulo de outra pessoa faria o balcao mostrar ao devedor a divida de
        um terceiro;
      - a RECUSA DIZ QUAL DAS DUAS PARTES FALHOU, porque o conserto e
        diferente;
      - `conferir` NAO GRAVA NADA;
      - o mesmo arquivo nao entra duas vezes, e a trava e o CONTEUDO;
      - o que nao casa NAO DERRUBA o pacote;
      - os titulos do ACERVO nao entram na lista de «sem imagem»: a imagem
        deles esta em papel, e a CRA nao os reenvia.
"""
from __future__ import annotations

import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402

import protesto_imagens as PI
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-08-31T15:00:00"

# O nome medido no pacote real de 15/07/2026, conferido contra a producao:
# as duas primeiras partes apontam para o titulo #1331.
NOME_REAL = "49000005243_00000002135_01.pdf"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    # `pt_atos.livro_id` aponta para `nu_livros`, e o PostgreSQL nativo
    # cobra a chave estrangeira ja na criacao: o nucleo vem antes.
    init_nucleo_schema(con)
    init_pt_schema(con)
    # `attachments` e a tabela geral da casa; aqui monta-se so o que o modulo
    # usa, porque ela nasce em `database.py` e nao num esquema de atribuicao.
    con.executescript("""
        CREATE TABLE IF NOT EXISTS attachments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_type TEXT, entity_id INTEGER, original_name TEXT,
            stored_name TEXT, stored_path TEXT, sha256 TEXT,
            size_bytes INTEGER, description TEXT, uploaded_by INTEGER,
            uploaded_at TEXT);
    """)
    return con


def titulo(con, *, nosso="49000005243", documento="00000002135",
           numero="49000005243", origem="CRA"):
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem, criado_em)
           VALUES ('DMI',?,?,10000,10000,'APONTADO',?,?)""",
        (numero, nosso, origem, AGORA))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,'JOSE RIBAMAR','CPF',?)""",
        (tid, documento))
    return tid


def pacote(*arquivos: tuple[str, bytes]) -> bytes:
    saida = BytesIO()
    with zipfile.ZipFile(saida, "w") as z:
        for nome, conteudo in arquivos:
            z.writestr(nome, conteudo)
    return saida.getvalue()


# ----------------------------------------------------------- o nome


def test_o_nome_decodifica_nas_tres_partes():
    """`<nosso numero>_<documento do devedor>_<sequencial>.pdf` — medido."""
    itens = PI.ler_pacote(pacote((f"1LV/{NOME_REAL}", b"%PDF-1.4 x")))
    assert len(itens) == 1
    p = itens[0]["partes"]
    assert p["nosso_numero"] == "49000005243"
    assert p["documento"] == "00000002135"
    assert p["sequencia"] == "01"
    # A PASTA E O APRESENTANTE, e fica registrada para o dia em que o pacote
    # trouxer dois.
    assert itens[0]["apresentante_pasta"] == "1LV"


def test_o_nome_sem_sequencial_tambem_entra():
    """O pacote real de 07/10/2026 trouxe os cinco arquivos SEM o `_01`
    (`<nosso>_<documento>.pdf`) — com o sequencial obrigatório, nenhum casava."""
    con = banco()
    titulo(con)
    itens = PI.ler_pacote(pacote(("1LV/49000005243_00000002135.pdf",
                                  b"%PDF-1.4 x")))
    p = itens[0]["partes"]
    assert p["nosso_numero"] == "49000005243"
    assert p["documento"] == "00000002135"
    assert p["sequencia"] == ""
    r = PI.conferir(con, pacote(("1LV/49000005243_00000002135.pdf",
                                 b"%PDF-1.4 x")))
    assert len(r["entram"]) == 1 and not r["fora"]


def test_nome_fora_da_forma_nao_derruba_a_leitura():
    """Ele entra sem partes; quem diz por que ele nao serve e `conferir`, que
    tem o banco na mao."""
    itens = PI.ler_pacote(pacote(("leiame.txt", b"x")))
    assert itens[0]["partes"] is None


def test_arquivo_que_nao_e_zip_e_erro_de_regra():
    with pytest.raises(PI.ImagemError, match="não é um pacote"):
        PI.ler_pacote(b"isto nao e um zip")


def test_pacote_vazio_e_recusado():
    with pytest.raises(PI.ImagemError):
        PI.ler_pacote(b"")


# ------------------------------------------------------- a dupla chave


def test_a_imagem_entra_quando_as_duas_partes_apontam_para_o_mesmo_titulo():
    con = banco()
    tid = titulo(con)
    r = PI.conferir(con, pacote((f"1LV/{NOME_REAL}", b"%PDF x")))
    assert len(r["entram"]) == 1
    assert r["entram"][0]["titulo_id"] == tid


def test_documento_que_nao_bate_NAO_entra():
    """NOSSO NUMERO SE REPETE ENTRE APRESENTANTES — 53 grupos e 111 titulos no
    acervo. Anexar a imagem ao titulo de outra pessoa faria o balcao mostrar ao
    devedor a divida de um terceiro."""
    con = banco()
    titulo(con, documento="11122233344")     # outro devedor
    r = PI.conferir(con, pacote((NOME_REAL, b"%PDF x")))
    assert r["entram"] == []
    assert len(r["fora"]) == 1


def test_a_recusa_diz_QUAL_das_duas_partes_falhou():
    """O conserto e diferente: titulo que nao existe e remessa nao recebida;
    documento que nao bate e imagem de outro titulo."""
    con = banco()
    r = PI.conferir(con, pacote((NOME_REAL, b"%PDF x")))
    assert "remessa dele ainda não foi recebida" in r["fora"][0]["motivo"]

    con2 = banco()
    titulo(con2, documento="11122233344")
    r2 = PI.conferir(con2, pacote((NOME_REAL, b"%PDF x")))
    assert "outro título com o mesmo nosso número" in r2["fora"][0]["motivo"]


def test_o_nosso_numero_casa_por_DIGITOS():
    """O nosso numero real tem barra — `17375280/041` aparece em 46 registros
    de 2026 —, e no nome do arquivo ele vem so com digitos."""
    con = banco()
    tid = titulo(con, nosso="17375280/041")
    r = PI.conferir(con, pacote(("17375280041_00000002135_01.pdf", b"%PDF x")))
    assert r["entram"] and r["entram"][0]["titulo_id"] == tid


def test_dois_devedores_com_o_documento_a_tela_mostra_o_primeiro_cadastrado():
    """RESSALVA DO L012R: `ORDER BY t.id LIMIT 1` sobre o JOIN dos devedores
    deixava ao PostgreSQL escolher QUAL devedor a conferência mostra. O SQLite
    dava o primeiro cadastrado (o `rowid`); agora o desempate é `d.id`."""
    con = banco()
    tid = titulo(con)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,'SEGUNDO DEVEDOR DE EXEMPLO','CPF',
               '00000002135')""", (tid,))
    # O UPDATE do documento (coluna com índice) faz o PostgreSQL gravar a linha do primeiro
    # devedor de novo, depois da do segundo: a ordem em que as linhas estão
    # gravadas deixa de ser a do id.
    primeiro = con.execute(
        "SELECT id, nome FROM pt_devedores WHERE titulo_id=? ORDER BY id",
        (tid,)).fetchone()
    # Os mesmos dígitos, com a máscara: o título continua casando.
    con.execute("UPDATE pt_devedores SET documento_numero='0000000213-5' "
                "WHERE id=?", (primeiro["id"],))
    r = PI.conferir(con, pacote((NOME_REAL, b"%PDF x")))
    assert r["entram"][0]["devedor"] == primeiro["nome"]


# --------------------------------------------------- conferir nao grava


def test_conferir_nao_grava_nada():
    con = banco()
    titulo(con)
    PI.conferir(con, pacote((NOME_REAL, b"%PDF x")))
    PI.conferir(con, pacote((NOME_REAL, b"%PDF x")))
    assert con.execute("SELECT COUNT(*) c FROM attachments").fetchone()["c"] == 0


# --------------------------------------------------------- guardar


def test_guardar_anexa_e_grava_o_arquivo(tmp_path):
    con = banco()
    tid = titulo(con)
    r = PI.guardar(con, pacote((f"1LV/{NOME_REAL}", b"%PDF conteudo")),
                   pasta_de_arquivos=tmp_path, agora=AGORA, usuario_id=1)
    assert len(r["guardadas"]) == 1
    linha = con.execute("SELECT * FROM attachments").fetchone()
    assert linha["entity_type"] == "PT_TITULO"
    assert linha["entity_id"] == tid
    assert Path(linha["stored_path"]).read_bytes() == b"%PDF conteudo"


def test_o_mesmo_arquivo_nao_entra_duas_vezes(tmp_path):
    """A trava e o CONTEUDO, e nao o nome: a CRA reenvia o pacote quando
    alguem pede de novo, e o mesmo PDF chega com o mesmo nome."""
    con = banco()
    titulo(con)
    z = pacote((NOME_REAL, b"%PDF igual"))
    PI.guardar(con, z, pasta_de_arquivos=tmp_path, agora=AGORA)
    r = PI.conferir(con, z)
    assert r["entram"] == []
    assert len(r["repetidas"]) == 1
    with pytest.raises(PI.ImagemError, match="Nenhuma"):
        PI.guardar(con, z, pasta_de_arquivos=tmp_path, agora=AGORA)


def test_a_imagem_corrigida_nao_apaga_a_anterior(tmp_path):
    """A CRA pode reenviar a imagem trocada. Apagar a primeira apagaria o que a
    serventia recebeu antes — e o que ela recebeu antes e o que ela usou."""
    con = banco()
    titulo(con)
    PI.guardar(con, pacote((NOME_REAL, b"%PDF primeira")),
               pasta_de_arquivos=tmp_path, agora=AGORA)
    PI.guardar(con, pacote((NOME_REAL, b"%PDF segunda")),
               pasta_de_arquivos=tmp_path, agora=AGORA)
    arquivos = sorted(x.name for x in (tmp_path / "Protesto" / "Titulos" / "1").iterdir())
    assert len(arquivos) == 2
    assert con.execute("SELECT COUNT(*) c FROM attachments").fetchone()["c"] == 2


def test_o_que_nao_casa_nao_derruba_o_pacote(tmp_path):
    """Uma imagem sem titulo e uma; as outras continuam sendo o trabalho do
    dia — a mesma regra do lote da remessa."""
    con = banco()
    titulo(con)
    r = PI.guardar(con, pacote((NOME_REAL, b"%PDF bom"),
                               ("00000000000_00000000000_01.pdf", b"%PDF orfa")),
                   pasta_de_arquivos=tmp_path, agora=AGORA)
    assert len(r["guardadas"]) == 1
    assert len(r["fora"]) == 1


def test_pacote_em_que_nada_entra_e_erro_de_regra(tmp_path):
    con = banco()
    with pytest.raises(PI.ImagemError, match="Nenhuma"):
        PI.guardar(con, pacote((NOME_REAL, b"%PDF x")),
                   pasta_de_arquivos=tmp_path, agora=AGORA)


# ------------------------------------------------------- as consultas


def test_as_imagens_do_titulo_saem_da_mais_nova(tmp_path):
    con = banco()
    tid = titulo(con)
    PI.guardar(con, pacote((NOME_REAL, b"%PDF a")),
               pasta_de_arquivos=tmp_path, agora=AGORA)
    PI.guardar(con, pacote(("49000005243_00000002135_02.pdf", b"%PDF b")),
               pasta_de_arquivos=tmp_path, agora=AGORA)
    assert len(PI.imagens_do_titulo(con, tid)) == 2
    assert PI.quantas(con, tid) == 2


def test_o_acervo_nao_entra_na_lista_de_sem_imagem():
    """OS 1.366 DO E-OFICIO TEM IMAGEM EM PAPEL, na pasta, e a CRA nao os
    reenvia. Lista-los seria acusar o acervo de um atraso que nao existe — e
    alarme que soa sempre e alarme que ninguem ouve."""
    con = banco()
    titulo(con, origem="EOFICIO", nosso="111", numero="do acervo")
    novo = titulo(con, origem="CRA", nosso="222", numero="novo")
    faltam = PI.titulos_sem_imagem(con)
    assert [t["id"] for t in faltam] == [novo]


def test_o_titulo_com_imagem_sai_da_lista(tmp_path):
    con = banco()
    titulo(con)
    assert len(PI.titulos_sem_imagem(con)) == 1
    PI.guardar(con, pacote((NOME_REAL, b"%PDF x")),
               pasta_de_arquivos=tmp_path, agora=AGORA)
    assert PI.titulos_sem_imagem(con) == []


# ------------------------------------------- a IA nao decide, o modulo nao lavra


def test_o_modulo_nao_lavra_nem_aponta_nada():
    """Anexar imagem nao e ato. Se alguem acrescentar aqui uma funcao que
    aponte, proteste ou cancele, isto fica vermelho — a imagem entra por um
    caminho que nao passa pela conferencia do titulo."""
    proibidas = [n for n in dir(PI) if not n.startswith("_")
                 and any(p in n.lower() for p in
                         ("apontar", "protestar", "cancelar", "lavrar",
                          "selar", "cobrar"))]
    assert proibidas == []
