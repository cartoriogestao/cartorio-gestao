"""O manual para baixar nas telas de importacao — pedido do oficial, 30/08/2026.

    «coloque o manual disponível para baixar nas páginas de importação»

O QUE ESTES TESTES GUARDAM

    **Que o arquivo baixado leva a lista de campos junto.** O documento em disco
    diz, de proposito, que a lista «esta na tela, sempre atual» — e isso vale
    para quem esta AQUI. **Quem recebe o arquivo esta fora da serventia e nao
    tem tela nenhuma**: receberia um manual mandando consultar o que ele nao
    alcanca. O que se baixa e o documento MAIS o que so o banco de hoje sabe.

    **Que sao CINCO telas e UMA macro.** A regra de `_fraude.html` e
    `_cobrar.html`: cinco copias divergiriam no primeiro conserto, e a
    consistencia aqui nao e estetica — e o operador achar a mesma coisa, com as
    mesmas palavras, em qualquer tela de importacao.

    **Que tela de importacao nova nasce com o manual.** O piso e medido: se
    alguem criar a sexta e esquecer, este teste fica vermelho — em vez de o
    buraco aparecer meses depois, quando alguem precisar do manual e nao achar.

    **Que meio manual nao se entrega.** Sem o documento em disco a funcao diz
    que ele falta, em vez de devolver so os campos: quem recebesse metade
    prepararia o arquivo sem as regras de recusa, e descobriria no dia da
    importacao.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent


def _documento(nome: str) -> Path:
    """O documento da casa (DOCUMENTACAO) ou, no clone público, a cópia
    sanitizada em docs/tecnico (23/10/2026)."""
    casa = RAIZ / "DOCUMENTACAO" / nome
    return casa if casa.is_file() else RAIZ / "docs" / "tecnico" / nome

sys.path.insert(0, str(RAIZ))

import importar_padrao as IMP                                    # noqa: E402

SENHA = "Senha#12345"
TELAS = RAIZ / "templates"

# AS TELAS DE IMPORTACAO desta casa. **O piso**: se nascer a sexta e ela nao
# oferecer o manual, este teste fica vermelho.
TELAS_DE_IMPORTACAO: tuple[str, ...] = (
    "importar_padrao.html", "atrib_importar.html", "caixa_importar.html",
    "notas_importar.html", "ri_importar.html",
    "atrib_livro3_importar.html", "protesto_importar_eoficio.html",
    "rcpn_importar_acervo.html",
    # Os pré-cadastros do Registro Civil (11/10/2026) — entrou em 14/10/2026,
    # quando o varredor abaixo acusou a tela sem o manual da casa.
    "rcpn_importar.html",
)


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token" value="([^"]+)"', html)
    return achado.group(1) if achado else ""


@pytest.fixture(scope="module")
def casa(tmp_path_factory):
    from app import create_app
    from database import Database

    dados = tmp_path_factory.mktemp("dados")
    app = create_app({"DATA_DIR": str(dados)})
    banco = Path(glob.glob(f"{dados}/*.sqlite3")[0])
    Database(banco).create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA,
                                "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"c": c, "banco": banco}


def _con(casa) -> sqlite3.Connection:
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


# ------------------------------------------------------- o que se baixa


def test_o_manual_baixa_e_e_texto(casa):
    r = casa["c"].get("/importar-padrao/manual")
    assert r.status_code == 200
    assert "attachment" in r.headers.get("Content-Disposition", "")
    assert "padrao-de-importacao" in r.headers["Content-Disposition"]


def test_o_manual_baixado_leva_a_lista_de_campos(casa):
    """**O documento em disco NAO a tem, e de proposito.**

    Quem recebe o arquivo esta fora da serventia e nao tem a tela onde a lista
    mora — sem ela, o manual manda consultar o que o destinatario nao alcanca.
    """
    texto = casa["c"].get("/importar-padrao/manual").get_data(as_text=True)
    assert "cor_raca" in texto, "a lista de campos do RCPN não veio junto"
    assert "descricao_perimetro" in texto, "a do RI não veio"
    assert "Os campos de cada especie" in texto

    # E O DOCUMENTO EM DISCO NAO TEM A LISTA — o que se procura aqui e a
    # LINHA DE TABELA, e nao a palavra: o documento cita `cor_raca` no meio de
    # uma frase, como exemplo de coluna que ja e portugues. **Setima vez neste
    # projeto que um varredor bate na prosa** — desta vez foi um teste meu, no
    # dia em que consertei o mesmo defeito no teto de portabilidade.
    em_disco = _documento(IMP.NOME_DO_MANUAL).read_text(
        encoding="utf-8")
    assert "| `cor_raca` |" not in em_disco, (
        "a lista de campos foi transcrita dentro do documento — ela envelhece "
        "lá; o lugar dela é o arquivo montado do banco")


def test_o_manual_baixado_leva_um_exemplo_de_cada_especie(casa):
    texto = casa["c"].get("/importar-padrao/manual").get_data(as_text=True)
    for especie in IMP.MODELOS:
        assert especie in texto, f"faltou o exemplo de {especie}"


def test_o_exemplo_que_o_manual_traz_e_lido_pelo_sistema(casa):
    """Se o exemplo e o leitor divergirem um dia, é aqui que se vê."""
    import json

    texto = casa["c"].get("/importar-padrao/manual").get_data(as_text=True)
    blocos = re.findall(r"```json\n(.*?)\n```", texto, re.DOTALL)
    assert len(blocos) >= len(IMP.MODELOS)
    con = _con(casa)
    for bruto in blocos:
        quadro = IMP.conferir(con, bruto)
        assert quadro["lidos"] == 1
        assert json.loads(bruto)["formato"] == IMP.FORMATO
    con.close()


def test_sem_o_documento_nao_se_entrega_meio_manual(casa, tmp_path):
    """**Meio manual e pior que nenhum**: quem o recebesse prepararia o arquivo
    sem as regras de recusa, e descobriria no dia da importacao."""
    con = _con(casa)
    with pytest.raises(IMP.ImportacaoError) as e:
        IMP.manual(con, pasta=tmp_path)
    con.close()
    assert "DOCUMENTACAO" in str(e.value)


# ------------------------------------------------------- onde ele aparece


@pytest.mark.parametrize("tela", TELAS_DE_IMPORTACAO)
def test_toda_tela_de_importacao_oferece_o_manual(tela):
    """O piso: a sexta tela que nascer sem ele fica vermelha aqui."""
    caminho = TELAS / tela
    assert caminho.is_file(), f"{tela} sumiu — atualize a lista deste teste"
    html = caminho.read_text(encoding="utf-8")
    assert "manual_para_baixar" in html, (
        f"{tela} não oferece o manual do padrão de importação")


def test_e_uma_macro_e_nao_cinco_copias():
    """A regra de `_fraude.html`: cinco cópias divergem no primeiro conserto."""
    macro = TELAS / "_manual_de_importacao.html"
    assert macro.is_file()
    for tela in TELAS_DE_IMPORTACAO:
        html = (TELAS / tela).read_text(encoding="utf-8")
        assert "_manual_de_importacao.html" in html, \
            f"{tela} não importa a macro — escreveu cópia própria?"
        assert "importar_padrao_manual" not in html, (
            f"{tela} chama a rota do manual direto, por fora da macro — "
            f"é assim que as cinco divergem")


def test_a_lista_deste_teste_cobre_as_telas_que_existem():
    """**PISO QUE NAO VIRA DEPOSITO.** Se aparecer tela de importacao fora
    desta lista, e ela que esta velha — e nao a casa."""
    achadas = {p.name for p in TELAS.glob("*importar*.html")}
    achadas -= {"ri_importacoes.html"}      # é o histórico, não uma importação
    faltando = achadas - set(TELAS_DE_IMPORTACAO)
    assert not faltando, (
        "estas telas de importação não estão na lista deste teste: "
        + ", ".join(sorted(faltando))
        + " — acrescente-as, e ponha o manual nelas")
