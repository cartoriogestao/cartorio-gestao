"""As telas do termo do Registro Civil.

POR QUE ESTE ARQUIVO EXISTE SEPARADO
    `test_rc_termo.py` prova que o **módulo** monta e congela. Este prova que a
    **ficha do assento chama o módulo** — e são coisas diferentes.

    **É o defeito que mais se repetiu neste projeto**, sete vezes: função de
    domínio pronta e testada que nenhuma tela chamava, e o buraco só aparecendo
    meses depois no balcão. `obter_selo`, a remessa da CRA, o apontamento do
    protesto, as telas do núcleo, o edital, o aviso, a DOI das notas.
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

import rc_termo as TERMO                                         # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    db.set_settings({"ri_registrador": "MARIO EXEMPLO DOS SANTOS",
                     "serventia_titular": "MARIO EXEMPLO DOS SANTOS"})
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa


def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(t: str) -> str:
    return " ".join((t or "").split())


def _assento(casa, **extras):
    con = _con(casa)
    campos = {
        "serie": "RC_A", "especie": "NASCIMENTO", "numero": "8687",
        "nome": "MARIA NUNES SANTOS ARAÚJO", "data_ato": "2026-08-20",
        "data_fato": "2026-08-18", "hora_fato": "14:30",
        "dnv": "30868091423", "cor_raca": "Parda",
        "naturalidade_declarada": "Cidade Exemplo/MA",
        "situacao": "ATIVO", "origem": "SISTEMA", "criado_em": AGORA,
    }
    campos.update(extras)
    with con:
        colunas = ", ".join(campos)
        marcas = ", ".join("?" for _ in campos)
        cur = con.execute(
            f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
            tuple(campos.values()))
        aid = int(cur.lastrowid)
        for papel, nome in (("DECLARANTE", "JOSÉ SANTOS ARAÚJO"),
                            ("PAI", "JOSÉ SANTOS ARAÚJO"),
                            ("MAE", "ANA SANTOS")):
            con.execute(
                """INSERT INTO rc_pessoas (assento_id, papel, nome, nome_norm,
                       criado_em) VALUES (?,?,?,?,?)""",
                (aid, papel, nome, nome.lower(), AGORA))
    return aid


def _abrir(casa, url):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


# ------------------------------------------------ a ficha oferece o termo


def test_a_ficha_do_assento_leva_ao_termo(casa):
    """Sem o botão na ficha, o módulo seria a oitava função pronta que ninguém
    chama."""
    aid = _assento(casa)
    html = _abrir(casa, f"/rcpn/{aid}")  # a ficha é `/rcpn/<id>`, e não `/rcpn/assentos/<id>`
    assert "O termo do livro" in html
    assert f"/rcpn/assentos/{aid}/termo" in html
    assert "Ainda não escrito" in html


def test_a_tela_do_termo_mostra_como_fica_antes_de_gravar(casa):
    """Ver como fica é de graça, e você pode voltar, completar o assento e
    olhar de novo."""
    aid = _assento(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "Como o termo vai ficar" in html
    assert "Nada foi gravado ainda" in html
    # **O CABEÇALHO NÃO ESTÁ NO CORPO DO TERMO, e é de propósito** — decisão do
    # oficial em 30/08/2026 de não usar os modelos do E-Ofício, dois dos quais
    # traziam a oficial ANTERIOR impressa dentro do texto. O que a tela tem de
    # mostrar é o termo da casa montado com os dados deste assento.
    assert "MARIA NUNES SANTOS ARAÚJO" in html
    assert "compareceu" in html


def test_ver_como_fica_nao_grava(casa):
    aid = _assento(casa)
    _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    teor = _con(casa).execute("SELECT teor FROM rc_assentos WHERE id=?",
                              (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


# ------------------------------------------------ escrever, e uma vez só


def _escrever(casa, aid, **extra):
    html = casa["cliente"].get(
        f"/rcpn/assentos/{aid}/termo").get_data(as_text=True)
    dados = {"csrf_token": _token(html), "livro": "A-25", "folha": "102"}
    dados.update(extra)
    return casa["cliente"].post(f"/rcpn/assentos/{aid}/termo/escrever",
                                data=dados, follow_redirects=True)


def test_a_tela_escreve_o_termo_no_assento(casa):
    aid = _assento(casa)
    r = _escrever(casa, aid)
    assert r.status_code == 200
    teor = _con(casa).execute("SELECT teor FROM rc_assentos WHERE id=?",
                              (aid,)).fetchone()["teor"]
    # **O TERMO NÃO REPETE LIVRO E FOLHA, e isto foi medido em 31/08/2026.**
    #
    #   Os três modelos da casa não têm campo de livro nem de folha: no livro de
    #   papel o termo **está escrito naquela folha**, e a matrícula de 32 dígitos
    #   que ele traz já codifica as duas coisas (tipo de livro, livro, folha e
    #   termo). Repetir no corpo seria afirmar duas vezes o que o próprio lugar
    #   do papel diz — e criar uma segunda fonte para divergir da primeira.
    #
    #   O que este teste guarda continua sendo o que importa: **a tela gravou, e
    #   o que ficou gravado é o termo deste assento.**
    assert "MARIA NUNES SANTOS ARAÚJO" in teor
    assert "dou fé e assino" in teor


def test_a_rota_recusa_reescrever(casa):
    """MANDADO DIRETO PARA A ROTA: quem recusa é o domínio, e a tela só esconde
    o botão por educação."""
    aid = _assento(casa)
    _escrever(casa, aid)
    r = _escrever(casa, aid)
    assert "não se reescreve" in _liso(r.get_data(as_text=True))


def test_escrito_a_tela_diz_que_nao_se_reescreve(casa):
    aid = _assento(casa)
    _escrever(casa, aid)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "já está escrito" in html
    assert "averbar ao lado" in html
    assert "Escrever o termo no assento" not in html


# ------------------------------------------------ o .odt


def test_o_termo_sai_em_odt_para_o_livro(casa):
    """Termo que só existe no banco não serve — é a mesma razão pela qual os
    termos de abertura e encerramento do núcleo saem em arquivo."""
    aid = _assento(casa)
    _escrever(casa, aid)
    r = casa["cliente"].get(f"/rcpn/assentos/{aid}/termo.odt")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.oasis.opendocument.text"
    import zipfile
    from io import BytesIO
    with zipfile.ZipFile(BytesIO(r.data)) as z:
        bruto = z.read("content.xml").decode("utf-8")
    texto = _liso(re.sub(r"<[^>]+>", " ", bruto))
    assert "MARIA NUNES SANTOS ARAÚJO" in texto
    assert "compareceu" in texto


def test_o_odt_sai_mesmo_antes_de_escrever(casa):
    """Para levar ao oficial e conferir antes de gravar."""
    aid = _assento(casa)
    r = casa["cliente"].get(f"/rcpn/assentos/{aid}/termo.odt")
    assert r.status_code == 200
    assert r.mimetype == "application/vnd.oasis.opendocument.text"


# ------------------------------------------------ a lista


def test_a_lista_mostra_quem_falta_e_explica_o_acervo(casa):
    """Os 244 do acervo vão aparecer, e a tela diz por que isso está certo."""
    aid = _assento(casa, origem="ACERVO")
    html = _abrir(casa, "/rcpn/termos-a-escrever")
    assert "MARIA NUNES SANTOS ARAÚJO" in html
    assert "E-Ofício não o guardava" in html
    assert "sem fingir ser a cópia" in html
    _escrever(casa, aid)
    assert "MARIA NUNES SANTOS ARAÚJO" not in _abrir(casa,
                                                    "/rcpn/termos-a-escrever")


def test_a_lista_esta_no_menu(casa):
    html = _abrir(casa, "/rcpn/termos-a-escrever")
    assert "Termos a escrever" in html


# ------------------------------------------------ quem assina


def test_quem_assina_sai_da_regra_viva(casa):
    """**QUEM ASSINA É QUEM ESTÁ NA TELA — E ESTE TESTE COBRAVA O CONTRATO ANTIGO.**

    Até 09/09/2026 o termo saía com a **substituta** do cadastro
    (`ri_substituta`), qualquer que fosse quem estava lavrando: todo ato novo
    saía assinado pela mesma pessoa, e cadastrar a função de cada usuário na
    tela Usuários não mudava nada. Foi o oficial quem mandou mudar (3.6.76), e
    é a mesma correção que o #65 pede no Registro de Imóveis.

    `atribuicoes_web._servent()` passou a entregar `escrevente` e `funcao` de
    quem está logado; `registrador` e `titulo` continuam sendo a regra viva da
    casa para os DEMAIS papéis. A expectativa deste teste era a substituta, e
    por isso ele estava vermelho desde aquele dia — **teste que afirma o
    contrato antigo é pior que teste nenhum**, porque quem o lê conclui que o
    sistema regrediu.

    O que ele guarda agora: o nome de quem assina aparece no termo, e a
    substituta do cadastro **não assina por ele**.
    """
    casa["db"].set_settings({"ri_substituta": "BEATRIZ EXEMPLO DE SOUZA"})
    aid = _assento(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "MARIO EXEMPLO DOS SANTOS" in html, "quem assina é quem está logado"
    assert "BEATRIZ EXEMPLO DE SOUZA" not in html, (
        "a substituta do cadastro não assina o ato de quem está no balcão")


def test_espécie_sem_modelo_avisa_na_tela_em_vez_de_estourar(casa):
    """Erro de regra não é HTTP 500.

    **A ESPÉCIE DESTE TESTE ERA `INTERDICAO`, E ELA DEIXOU DE SERVIR EM
    07/09/2026** — o oficial mandou que o Livro E inteiro usasse **um modelo
    só** («livro e usa o mesmo modelo»), e a interdição ganhou texto. O que
    continua valendo é a guarda: uma espécie que o mapa não conhece — um
    registro velho, um valor que entrou por importação — **avisa**, e não
    derruba a tela. É por isso que a espécie inventada entra aqui direto no
    banco: é assim que ela chegaria.
    """
    aid = _assento(casa, especie="DESCONHECIDA", serie="RC_E")
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "Não dá para montar o termo" in html
    assert "nunca lavrou nenhuma" in html


# ---------------- a ordem do oficial de 30/08/2026: nao imaginar o termo


def _importado(casa, nome="HEITOR DIAS CAMARGO", numero=283):
    """Um assento vindo da carga, como os 244 da produção."""
    con = _con(casa)
    with con:
        cur = con.execute(
            """INSERT INTO rc_assentos (serie, especie, numero, nome, data_ato,
                   data_fato, situacao, origem, criado_em)
               VALUES ('RC_A','NASCIMENTO',?,?,'1955-10-12','1955-10-01',
                       'ATIVO','EOFICIO',?)""", (numero, nome, AGORA))
        return int(cur.lastrowid)


def test_o_importado_mostra_previa_e_nao_grava(casa):
    """Relato #38, 31/08/2026: página em branco é defeito. A prévia sai dos
    campos; **abrir a tela não congela**. O termo original existe em papel.
    """
    aid = _importado(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "veio do E-Ofício, e o termo dele existe em papel" in html
    assert "Como o termo vai ficar" in html
    teor = _con(casa).execute("SELECT teor FROM rc_assentos WHERE id=?",
                              (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


def test_o_importado_oferece_anexar_o_pdf_do_termo(casa):
    """«Permitir, caso conveniente, que se importe o pdf do termo» — e ele é a
    única coisa que ainda pode vir do papel."""
    aid = _importado(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "O termo digitalizado" in html
    assert "Anexar o termo do livro" in html


def test_o_importado_pede_confirmacao_para_gravar(casa):
    """Mostrar não é gravar. O botão existe, e o texto avisa que não é o
    termo de papel."""
    aid = _importado(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "Escrever o termo no assento" in html
    assert "não é o termo de papel" in html
    assert "Gerar mesmo assim" not in html


def test_o_lavrado_aqui_continua_mostrando_a_previa(casa):
    """A ordem vale para o **importado**. Para o ato novo a prévia é o que
    permite conferir antes de congelar — tirá-la de todos seria cumprir a ordem
    para além do que ela diz."""
    aid = _assento(casa)
    html = _abrir(casa, f"/rcpn/assentos/{aid}/termo")
    assert "veio do E-Ofício" not in html


def test_a_lista_de_termos_nao_traz_os_importados(casa):
    """**LISTA É PROMESSA**: o que está numa lista de trabalho é trabalho que
    alguém vai fazer, por mais que a legenda diga o contrário."""
    _importado(casa, "DO ACERVO", 283)
    html = _abrir(casa, "/rcpn/termos-a-escrever")
    assert "DO ACERVO" not in html
    assert "0" in html


def test_a_conta_separa_o_importado_do_trabalho(casa):
    """Número que parece trabalho e não é faz planejar o que não existe."""
    import rc_termo as T
    con = _con(casa)
    _importado(casa, "DO ACERVO", 283)
    r = T.quantos_termos_faltam(con)
    assert r["a_escrever"] == 0
    assert r["importados"] == 1
