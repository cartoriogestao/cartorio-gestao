"""O layout da certidão de inteiro teor do Registro de Imóveis.

O DÉBITO DO BALCÃO era «layout da certidão de inteiro teor», e a medição deu
nome a ele.

O QUE SE MEDIU EM 28/08/2026
    `ri_certidoes` tem **369** certidões, todas de INTEIRO TEOR, e **uma só**
    guarda o corpo: as outras 368 vieram do E-Ofício sem ele. Essa uma é a
    **6/2026, da matrícula 582**, emitida por este sistema em 18/08 — e ela
    saía assim:

        AV-28/582 — 2026-08-18

    A data do ato em **forma de banco**, dentro do documento que a serventia
    assina.

    E `data_extenso` **já estava pronta** no contexto, ao lado de `data_ato`,
    calculada com `data_por_extenso()` — a mesma função dos termos de livro e
    da certidão do RCPN. **O modelo é que não a usava.** É a sétima vez neste
    projeto que a peça está pronta e quem devia chamá-la não chama.

E OS DOIS RELATOS ERAM O MESMO PAPEL
    A matrícula 582 é a mesma do outro relato do oficial — «AV-28 aparecendo no
    teor de ficha do acervo».

POR QUE O TESTE EMITE A CERTIDÃO DE VERDADE
    `render_modelo` mora dentro de `create_app`, e recriar as duas linhas de
    Jinja aqui seria testar a minha cópia e não a da casa — o erro que este
    projeto já cometeu com os 37 testes do selo, que aplicavam a suposição aos
    dois lados. O teste emite pela tela e lê o corpo **congelado** em
    `ri_certidoes`, que é o papel que sai.
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

SENHA = "Senha#12345"


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
    db.set_settings({"ri_cns": "000000", "ri_cidade": "Cidade Exemplo",
                     "ri_uf": "MA"})
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _matricula_com_ato(con, *, numero="582", tipo="AV", n=28,
                       data="2026-08-18"):
    from ri_schema import hash_ato
    # Forma do RI (mesmo de data_por_extenso em ri_web): dia em algarismo.
    EXTENSO = {
        "2026-08-18": "18 de agosto de 2026",
        "1977-07-29": "29 de julho de 1977",
    }
    data_br = EXTENSO.get(data)
    if not data_br:
        from ri_web import data_por_extenso
        data_br = data_por_extenso(data)
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, situacao,
               tipo_ficha, cidade, uf, descricao_perimetro, criado_em)
           VALUES (?, '2-C', '2C', 'ATIVA', 'ESTRUTURADA', 'Cidade Exemplo',
                   'MA', 'um imovel urbano', '2026-08-28T09:00')""", (numero,))
    mid = int(cur.lastrowid)
    # Data no TEOR do ato (papel real). Certidao texto nao imprime mais
    # a linha de rotulo+data; so o texto. Pedido 16/09/2026.
    teor = "<p>%s-%s/%s — %s. o texto do ato</p>" % (tipo, n, numero, data_br)
    h = hash_ato(numero, tipo, n, data, teor, None)
    con.execute(
        """INSERT INTO ri_atos (matricula_id, tipo, numero, data_ato, teor,
               teor_formato, cancelado, acervo, origem, hash_ato,
               hash_anterior, lavrado_em)
           VALUES (?,?,?,?, ?, 'html', 0, 0, 'MANUAL',
                   ?, NULL, '2026-08-18T09:00')""",
        (mid, tipo, n, data, teor, h))
    return mid






def _emitir(casa, mid, tipo="INTEIRO_TEOR"):
    html = casa["cliente"].get(
        f"/registro-imoveis/{mid}").get_data(as_text=True)
    casa["cliente"].post(f"/registro-imoveis/{mid}/certidao", data={
        "csrf_token": _token(html), "tipo": tipo,
        "fonte_corpo": "TEXTO",
        "requerente": "FULANO DE TAL",
        "_removido_lavrar_sem_selo": "0"}, follow_redirects=True)
    linha = _con(casa).execute(
        "SELECT * FROM ri_certidoes ORDER BY id DESC LIMIT 1").fetchone()
    assert linha, "a certidão não foi emitida"
    return dict(linha)


# ------------------------------------------- a data


def test_a_data_do_ato_sai_por_extenso_e_nao_em_forma_de_banco(casa):
    """Medido na certidão 6/2026, da matrícula 582: saía «AV-28/582 —
    2026-08-18»."""
    con = _con(casa)
    with con:
        mid = _matricula_com_ato(con)
    corpo = _emitir(casa, mid)["corpo"]
    # `18 de agosto de 2026`, e não «dezoito de agosto…»: no Registro de
    # Imóveis o dia sai em algarismo e o mês por extenso — é a forma de
    # `data_por_extenso`, a mesma dos termos de livro. A certidão do RCPN
    # escreve tudo por extenso porque o modelo do CNJ manda assim; são dois
    # papéis diferentes, e eu esperei aqui a forma do outro.
    assert "18 de agosto de 2026" in corpo
    assert "2026-08-18" not in corpo


def test_nenhuma_data_de_banco_sobra_no_corpo(casa):
    """Uma varredura, e não uma conferência de campo por campo: data em forma
    de banco não pode aparecer em lugar nenhum de um papel que a casa assina."""
    con = _con(casa)
    with con:
        mid = _matricula_com_ato(con, tipo="R", n=1, data="1977-07-29")
    corpo = _emitir(casa, mid)["corpo"]
    assert not re.search(r"\b(19|20)\d\d-\d\d-\d\d\b", corpo), (
        "sobrou data em forma de banco no corpo da certidão")


def test_a_data_antiga_tambem_sai_por_extenso(casa):
    """O acervo desta casa tem ato de 1977. Por extenso é como a certidão do
    RCPN já escreve, e como os termos de livro escrevem."""
    con = _con(casa)
    with con:
        mid = _matricula_com_ato(con, tipo="R", n=1, data="1977-07-29")
    corpo = _emitir(casa, mid)["corpo"]
    assert "29 de julho de 1977" in corpo


# ------------------------------------------- a validade, com o artigo


def test_a_validade_cita_o_artigo_do_codigo_de_normas(casa):
    """Dizia «na forma do Código de Normas da CGJ/TJMA», sem artigo — e a casa
    assina esse papel.

    Conferido no PDF que está na casa (`Código de normas TJMA atualizado.pdf`):
    **art. 53** — «(...) estas deverão ser atualizadas, observando-se o prazo
    de validade de 30 (trinta) dias». O prazo estava certo; faltava o endereço.

    Numa certidão, quem confere é o banco, o comprador e o juiz."""
    con = _con(casa)
    with con:
        mid = _matricula_com_ato(con)
    corpo = _emitir(casa, mid)["corpo"]
    assert "art. 53 do Código de Normas" in corpo
    assert "30 (trinta) dias" in corpo
    assert "inteiro teor segue" in corpo.lower()
    assert "era o que nela continha" in corpo.lower()
    i_segue = corpo.lower().find("inteiro teor segue")
    i_era = corpo.lower().find("era o que nela continha")
    assert i_segue >= 0 and i_era > i_segue


# ------------------------------------------- a peça que já existia


def test_a_data_por_extenso_e_a_mesma_funcao_da_casa():
    """`data_extenso` sai de `data_por_extenso()`, a mesma dos termos de livro
    e da certidão do RCPN. Uma segunda forma de escrever data por extenso
    divergiria no primeiro conserto — este projeto já pagou por isso duas
    vezes, com `normalizar_nome`."""
    codigo = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    assert '"data_extenso": (data_por_extenso(' in codigo


def test_o_modelo_usa_a_peca_pronta_e_nao_a_crua():
    """Fica vermelho se alguém voltar a imprimir `a.data_ato` sozinho — que é
    como o defeito nasceu: a peça pronta ao lado, e o modelo chamando a crua."""
    modelo = (RAIZ / "ri_odt.py").read_text(encoding="utf-8")
    assert "{{ a.data_extenso }}" in modelo
    # a forma crua só sobrevive como reserva, depois do `elif`
    assert "{% if a.data_ato %} — {{ a.data_ato }}{% endif %}" not in modelo
