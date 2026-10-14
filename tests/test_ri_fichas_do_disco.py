"""As páginas digitalizadas que o banco não conhece.

    «precisamos criar uma ferramenta para subir matrículas antigas, com
     digitalização, indicadores e etc»        — o oficial, 04/09/2026

O QUE A MEDIÇÃO ACHOU, antes de escrever qualquer linha
    A digitalização **já estava dentro do sistema** — `ri_imagens`, 3.667
    páginas copiadas em 13/08/2026. O buraco era outro, e maior:

    | | |
    |---|---|
    | páginas no disco | **10.227** |
    | páginas no banco | 3.667 |
    | **faltando** | **6.508** |
    | **matrículas com ficha incompleta** | **1.203** |

    A matrícula 5 tem **60 páginas no disco e 6 no sistema**. Quem a abre lê um
    décimo dela, e nada avisa.

O TESTE QUE MAIS VALE AQUI É O DA MATRÍCULA REPETIDA
    O número do arquivo é o número da matrícula — conferido em 3.667 de 3.667.
    Mas **duas matrículas desta casa têm o mesmo número** (`067` e `8`), e ali
    casar pelo número escolheria no escuro. **Medido na produção: 48 páginas
    caem nesse caso.**

    Ligar a ficha ao imóvel errado é o engano que ninguém desconfia — porque a
    ficha abre.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ri_fichas_do_disco as FD                                  # noqa: E402

SENHA = "Senha#12345"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd, "tmp": dados}


def _matricula(s, numero: str, livro: str = "2") -> int:
    con = sqlite3.connect(s["banco"])
    cur = con.execute(
        "INSERT INTO ri_matriculas (numero, livro, criado_em) VALUES (?,?,?)",
        (numero, livro, "2026-09-04"))
    con.commit()
    tid = int(cur.lastrowid)
    con.close()
    return tid


def _disco(s, *nomes: str) -> Path:
    """Uma pasta com arquivos do jeito que o E-Ofício os deixa."""
    pasta = s["tmp"] / "IMAGENS" / "00000000"
    pasta.mkdir(parents=True, exist_ok=True)
    for n in nomes:
        (pasta / n).write_bytes(b"II*\x00" + b"\x00" * 40)   # cabeçalho TIFF
    return s["tmp"] / "IMAGENS"


def _con(s):
    con = sqlite3.connect(s["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------ o nome do arquivo


def test_o_nome_se_parte_em_matricula_e_pagina():
    """`.0069` é o NÚMERO DA PÁGINA, e não extensão — foi supor o contrário que
    derrubou 3.689 imagens de uma vez, em silêncio."""
    assert FD.partir("00003744.0069") == ("3744", 69)
    assert FD.partir("00003744.0069.TIF") == ("3744", 69)
    assert FD.partir("00000005.0001.tif") == ("5", 1)


def test_nome_fora_do_padrao_NAO_se_adivinha():
    """Arquivo com outro nome não é página de ficha desta casa — e chutar
    poria coisa de fora dentro do livro."""
    for n in ("foto.jpg", "123", "matricula 5.pdf", "", "00000005.0001.0002"):
        assert FD.partir(n) is None


# ------------------------------------------------ o casamento


def test_a_pagina_casa_pelo_numero_da_matricula(s):
    mid = _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF", "00003744.0002.TIF")
    with _con(s) as con:
        r = FD.conferir(con, raiz)
    assert r["quantas_novas"] == 2
    assert {x["matricula_id"] for x in r["novas"]} == {mid}
    assert [x["pagina"] for x in r["novas"]] == [1, 2]


def test_NUMERO_REPETIDO_nao_casa_e_aparece_com_o_motivo(s):
    """**O teste que mais vale deste arquivo.**

    Medido na produção: `067` e `8` estão em duas matrículas cada, e 48 páginas
    caem nesse caso. Escolher uma poria a ficha de um imóvel na de outro — e
    ninguém desconfia de uma ficha que abre.
    """
    _matricula(s, "8", livro="2")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")
    with _con(s) as con:
        r = FD.conferir(con, raiz)
    assert r["quantas_novas"] == 0
    assert len(r["ambiguas"]) == 1
    assert "2 matrículas" in r["ambiguas"][0]


def test_pagina_de_matricula_que_nao_existe_fica_a_vista(s):
    _matricula(s, "3744")
    raiz = _disco(s, "00009999.0001.TIF")
    with _con(s) as con:
        r = FD.conferir(con, raiz)
    assert r["quantas_novas"] == 0
    assert r["sem_matricula"] == ["00009999.0001.TIF"]


def test_o_que_ja_esta_no_banco_nao_entra_de_novo(s):
    """Trazer duas vezes é rotina — e a segunda não pode duplicar a ficha."""
    mid = _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT INTO ri_imagens (matricula_id, nome_arquivo, ordem) "
                "VALUES (?,?,?)", (mid, "00003744.0001", 1))
    con.commit()
    con.close()
    with _con(s) as con:
        r = FD.conferir(con, raiz)
    assert r["quantas_novas"] == 0
    assert r["ja_no_banco"] == 1


def test_conferir_NAO_grava_nada(s):
    """É o passo que se repete à vontade — a forma de conferir/receber da
    remessa da CRA."""
    _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    with _con(s) as con:
        antes = con.execute("SELECT COUNT(*) FROM ri_imagens").fetchone()[0]
        FD.conferir(con, raiz)
        FD.conferir(con, raiz)
        assert con.execute(
            "SELECT COUNT(*) FROM ri_imagens").fetchone()[0] == antes == 0


def test_pasta_que_nao_existe_e_erro_de_regra_com_a_dica_do_SYSTEM(s):
    """O servidor roda como SYSTEM: unidade mapeada não funciona, e a frase
    tem de dizer isso — senão o oficial troca o caminho às cegas."""
    with _con(s) as con:
        with pytest.raises(FD.FichaDoDiscoError) as erro:
            FD.conferir(con, s["tmp"] / "nao-existe")
    assert "SYSTEM" in str(erro.value)


# ------------------------------------------------ trazer para dentro


def test_trazer_COPIA_o_arquivo_e_grava_a_linha(s):
    mid = _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF", "00003744.0002.TIF")
    r = FD.trazer(s["db"], raiz)
    assert r["trazidas"] == 2
    assert not r["falhas"]

    with _con(s) as con:
        linhas = [dict(x) for x in con.execute(
            "SELECT * FROM ri_imagens ORDER BY ordem")]
    assert len(linhas) == 2
    assert linhas[0]["matricula_id"] == mid
    assert linhas[0]["nome_arquivo"] == "00003744.0001"
    assert linhas[0]["ordem"] == 1
    assert linhas[0]["sha256"]
    assert linhas[0]["bytes"] > 0
    # **A CÓPIA EXISTE MESMO** — não basta a linha dizer que existe.
    interno = FD.pasta_interna(s["db"]) / str(mid) / "00003744.0001.TIF"
    assert interno.exists()
    assert str(mid) in linhas[0]["caminho_interno"]


def test_trazer_duas_vezes_nao_duplica(s):
    _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    assert FD.trazer(s["db"], raiz)["trazidas"] == 1
    segunda = FD.trazer(s["db"], raiz)
    assert segunda["trazidas"] == 0
    assert "não há página nova" in segunda["porque"]


def test_o_limite_traz_so_uma_parte(s):
    """São milhares e 453 MB — quem quiser começar devagar, pode."""
    _matricula(s, "3744")
    raiz = _disco(s, *[f"00003744.{i:04d}.TIF" for i in range(1, 8)])
    r = FD.trazer(s["db"], raiz, limite=3)
    assert r["trazidas"] == 3
    assert FD.trazer(s["db"], raiz)["trazidas"] == 4


def test_a_copia_vai_para_a_pasta_QUE_O_BACKUP_VARRE(s):
    """Duas pastas para a mesma coisa fariam metade das fichas sumir do backup
    sem ninguém ver."""
    interna = FD.pasta_interna(s["db"])
    assert interna.name == "fichas"
    assert interna.parent.name == "ri"


def test_a_ficha_incompleta_aparece_na_lista(s):
    mid = _matricula(s, "5")
    raiz = _disco(s, *[f"00000005.{i:04d}.TIF" for i in range(1, 11)])
    FD.trazer(s["db"], raiz, limite=2)
    with _con(s) as con:
        faltando = FD.incompletas(con, raiz)
    assert len(faltando) == 1
    assert faltando[0]["id"] == mid
    assert faltando[0]["tem"] == 2
    assert faltando[0]["faltam"] == 8


# ------------------------------------------------ a tela


def test_a_tela_abre_e_mostra_o_que_falta(s):
    _matricula(s, "5")
    raiz = _disco(s, *[f"00000005.{i:04d}.TIF" for i in range(1, 6)])
    con = sqlite3.connect(s["banco"])
    con.execute("UPDATE settings SET value=? WHERE key='ri_imagens_raiz'",
                (str(raiz),))
    if con.total_changes == 0:
        con.execute("INSERT INTO settings (key, value) VALUES (?,?)",
                    ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()

    html = " ".join(s["c"].get("/registro-imoveis/imagens/do-disco")
                    .get_data(as_text=True).split())
    assert "Páginas que faltam" in html
    assert "fichas estão incompletas" in html


def test_a_tela_das_fichas_leva_a_nova(s):
    """Tela sem porta é o defeito que mais se repetiu neste projeto."""
    html = s["c"].get("/registro-imoveis/imagens/resolver").get_data(
        as_text=True)
    assert "do-disco" in html


def test_as_duas_rotas_existem(s):
    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    assert "/registro-imoveis/imagens/do-disco" in regras
    assert "/registro-imoveis/imagens/do-disco/trazer" in regras


def test_trazer_pela_tela_grava_e_avisa(s):
    mid = _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()

    html = s["c"].get("/registro-imoveis/imagens/do-disco").get_data(
        as_text=True)
    r = s["c"].post("/registro-imoveis/imagens/do-disco/trazer",
                    data={"csrf_token": _token(html), "limite": "0"},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "1 página(s) trazida(s)" in " ".join(
        r.get_data(as_text=True).split())
    with _con(s) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM ri_imagens WHERE matricula_id=?",
            (mid,)).fetchone()[0] == 1


# ------------------------------------------------ escolher a matrícula
#
# **AVISO SEM SAÍDA É AVISO QUE FICA PARA SEMPRE** — a lição do livro a
# confirmar. As 48 páginas ambíguas medidas na produção apareceriam na
# conferência todo dia, e na terceira vez ninguém mais lê.
#
# O que muda não é a régua: continua sendo verdade que **um programa não pode
# escolher**. O que muda é haver quem escolha.


def test_candidatas_traz_as_matriculas_possiveis_da_pagina_ambigua(s):
    a = _matricula(s, "8", livro="2S")
    b = _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")
    with _con(s) as con:
        fora = FD.candidatas(con, raiz)
    assert len(fora) == 1
    assert fora[0]["nome"] == "00000008.0001"
    assert fora[0]["pagina"] == 1
    assert {o["id"] for o in fora[0]["opcoes"]} == {a, b}
    # **O LIVRO É O QUE DECIDE, e por isso ele tem de estar na tela.** Nº 8 são
    # dois imóveis de verdade — Livro 2S de 1977 e Livro 2-A de 2022 —, e o
    # nome do arquivo não diz qual.
    assert {o["livro"] for o in fora[0]["opcoes"]} == {"2S", "2-A"}


def test_candidatas_NAO_traz_a_pagina_que_casa_sozinha(s):
    """Quem casa sozinho já entra pela trazida em massa — repeti-lo aqui faria
    o oficial escolher onde não há escolha."""
    _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    with _con(s) as con:
        assert FD.candidatas(con, raiz) == []


def test_candidatas_NAO_GRAVA_nada(s):
    _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")
    with _con(s) as con:
        FD.candidatas(con, raiz)
        FD.candidatas(con, raiz)
        assert con.execute(
            "SELECT COUNT(*) FROM ri_imagens").fetchone()[0] == 0


def test_resolver_liga_a_pagina_a_matricula_escolhida_e_copia(s):
    a = _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")

    r = FD.resolver(s["db"], "00000008.0001", a, raiz=raiz)
    assert r["matricula_id"] == a and r["pagina"] == 1

    with _con(s) as con:
        linha = con.execute(
            "SELECT matricula_id, ficha_digitalizada, caminho_interno "
            "FROM ri_imagens WHERE nome_arquivo=?", ("00000008.0001",)
        ).fetchone()
    assert linha["matricula_id"] == a
    assert linha["ficha_digitalizada"] == 1
    # **A CÓPIA VAI PARA A PASTA QUE O BACKUP VARRE** — decisão do oficial:
    # «dentro do sistema». Duas pastas fariam metade das fichas sumir do
    # backup sem ninguém ver.
    assert (FD.pasta_interna(s["db"]) / str(a) / "00000008.0001.TIF").exists()


def test_resolver_RECUSA_matricula_que_nao_e_candidata(s):
    """**O guarda que mais importa deste quadro.**

    Um número trocado na barra do navegador poria a ficha de um imóvel na de
    outro — que é exatamente o engano que esta tela existe para evitar. E a
    recusa DIZ quais são as possíveis, porque quem está na tela precisa saber
    o que marcar.
    """
    _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    alheia = _matricula(s, "3744")
    raiz = _disco(s, "00000008.0001.TIF")

    with pytest.raises(FD.FichaDoDiscoError) as erro:
        FD.resolver(s["db"], "00000008.0001", alheia, raiz=raiz)
    assert "não é uma das candidatas" in str(erro.value)
    assert "Livro 2S" in str(erro.value)

    with _con(s) as con:
        assert con.execute(
            "SELECT COUNT(*) FROM ri_imagens").fetchone()[0] == 0


def test_resolver_RECUSA_pagina_que_nao_espera_escolha(s):
    """Página que casa sozinha, ou já resolvida, não passa por aqui — senão
    haveria dois caminhos gravando a mesma coisa, e eles divergem."""
    mid = _matricula(s, "3744")
    raiz = _disco(s, "00003744.0001.TIF")
    with pytest.raises(FD.FichaDoDiscoError) as erro:
        FD.resolver(s["db"], "00003744.0001", mid, raiz=raiz)
    assert "não está esperando escolha" in str(erro.value)


def test_resolvida_a_pagina_SAI_da_lista(s):
    """Marca que volta é pior que marca que nunca existiu — a lição do livro a
    confirmar. Resolvida, ela não pode reaparecer amanhã pedindo escolha."""
    a = _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")

    FD.resolver(s["db"], "00000008.0001", a, raiz=raiz)
    with _con(s) as con:
        assert FD.candidatas(con, raiz) == []
        assert FD.conferir(con, raiz)["ambiguas"] == []


def test_a_rota_de_escolher_existe_E_A_TELA_A_CHAMA(s):
    """**FUNÇÃO PRONTA QUE NENHUMA TELA CHAMA é o defeito mais repetido deste
    projeto**, e ele quase aconteceu aqui: numa primeira passada `escolher`
    era passado ao modelo e o modelo não o desenhava — o oficial ficaria com
    a lista sem um botão para resolvê-la.
    """
    _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()

    regras = {r.rule for r in s["app"].url_map.iter_rules()}
    assert "/registro-imoveis/imagens/do-disco/escolher" in regras

    html = " ".join(s["c"].get("/registro-imoveis/imagens/do-disco")
                    .get_data(as_text=True).split())
    assert "Escolher a matrícula" in html
    assert "/registro-imoveis/imagens/do-disco/escolher" in html
    assert 'name="matricula_id"' in html
    assert "Ligar a esta" in html


def test_escolher_pela_tela_grava_e_avisa(s):
    a = _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    raiz = _disco(s, "00000008.0001.TIF")
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()

    html = s["c"].get("/registro-imoveis/imagens/do-disco").get_data(
        as_text=True)
    r = s["c"].post("/registro-imoveis/imagens/do-disco/escolher",
                    data={"csrf_token": _token(html),
                          "nome": "00000008.0001", "matricula_id": str(a)},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "ligada à matrícula escolhida" in " ".join(
        r.get_data(as_text=True).split())
    with _con(s) as con:
        assert con.execute(
            "SELECT matricula_id FROM ri_imagens WHERE nome_arquivo=?",
            ("00000008.0001",)).fetchone()[0] == a


def test_escolher_errado_pela_tela_NAO_da_erro_500(s):
    """Erro de regra é mensagem de balcão, e não HTTP 500 — regra da casa."""
    _matricula(s, "8", livro="2S")
    _matricula(s, "8", livro="2-A")
    alheia = _matricula(s, "3744")
    raiz = _disco(s, "00000008.0001.TIF")
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)",
                ("ri_imagens_raiz", str(raiz)))
    con.commit()
    con.close()

    html = s["c"].get("/registro-imoveis/imagens/do-disco").get_data(
        as_text=True)
    r = s["c"].post("/registro-imoveis/imagens/do-disco/escolher",
                    data={"csrf_token": _token(html),
                          "nome": "00000008.0001",
                          "matricula_id": str(alheia)},
                    follow_redirects=True)
    assert r.status_code == 200
    assert "não é uma das candidatas" in " ".join(
        r.get_data(as_text=True).split())
