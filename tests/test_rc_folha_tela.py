"""A folha do livro — o texto do termo, nas três espécies.

O QUE ESTES TESTES GUARDAM
    **Relato #38, 31/08/2026.** `/rcpn/244` (óbito) saía com a página em
    branco: o E-Ofício não guardava o teor, a carga deixou a coluna vazia, e
    `/rcpn/<id>/folha` só lia o gravado. Página em branco é defeito.

    **A prévia monta dos campos e não grava.** O importado não congela só
    porque a folha abriu. Ato novo continua `congelar` uma vez.

    **A geometria das três colunas fica no papel** (retrato 215×279 mm,
    1ª coluna estreita só com o número, pauta só nas averbações, verso).
    A aula sobre elas saiu da tela de uso.
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

import rc_folha as FOLHA                                         # noqa: E402
import rc_modelos_do_livro as LIVRO                              # noqa: E402
import rc_termo as TERMO                                         # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-31T10:00"


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
                     "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
                     "ri_cidade": "Cidade Exemplo", "ri_uf": "MA",
                     "ri_estado": "Maranhão"})
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


def _abrir(casa, url):
    r = casa["cliente"].get(url)
    assert r.status_code == 200, f"{url} não abriu ({r.status_code})"
    return r.get_data(as_text=True)


def _pessoa(con, aid, papel, nome, **extras):
    campos = {"assento_id": aid, "papel": papel, "nome": nome,
              "nome_norm": nome.lower(), "criado_em": AGORA}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    con.execute(f"INSERT INTO rc_pessoas ({colunas}) VALUES ({marcas})",
                tuple(campos.values()))


def _assento(casa, *, especie, numero, nome, origem="SISTEMA", **extras):
    serie = {"NASCIMENTO": "RC_A", "NATIMORTO": "RC_A",
             "CASAMENTO": "RC_B", "CASAMENTO_RELIGIOSO": "RC_B",
             "OBITO": "RC_C"}.get(especie, "RC_A")
    campos = {
        "serie": serie, "especie": especie, "numero": numero,
        "nome": nome, "data_ato": "2026-08-20", "data_fato": "2026-08-18",
        "situacao": "ATIVO", "origem": origem, "criado_em": AGORA,
        "livro_volume": "A-1",
    }
    campos.update(extras)
    con = _con(casa)
    with con:
        colunas = ", ".join(campos)
        marcas = ", ".join("?" for _ in campos)
        cur = con.execute(
            f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
            tuple(campos.values()))
        return int(cur.lastrowid)


def _nascimento(casa, **extras):
    origem = extras.pop("origem", "SISTEMA")
    aid = _assento(casa, especie="NASCIMENTO", numero="8687",
                   nome="MARIA ENSAIO NASCIMENTO", origem=origem,
                   hora_fato="14:30", cor_raca="Parda",
                   dnv="30868091423",
                   local_fato_nome="Hospital Municipal de Ensaio",
                   local_fato_endereco="Rua das Flores, 100",
                   **extras)
    con = _con(casa)
    with con:
        _pessoa(con, aid, "DECLARANTE", "JOSE ENSAIO NASCIMENTO")
        _pessoa(con, aid, "PAI", "JOSE ENSAIO NASCIMENTO")
        _pessoa(con, aid, "MAE", "ANA ENSAIO NASCIMENTO")
    return aid


def _casamento(casa, **extras):
    origem = extras.pop("origem", "SISTEMA")
    aid = _assento(casa, especie="CASAMENTO", numero="40",
                   nome="JOAO ENSAIO e MARIA ENSAIO", origem=origem,
                   regime_bens="Comunhão parcial de bens", **extras)
    con = _con(casa)
    with con:
        _pessoa(con, aid, "NUBENTE1", "JOAO ENSAIO CASAMENTO")
        _pessoa(con, aid, "NUBENTE2", "MARIA ENSAIO CASAMENTO")
    return aid


def _obito(casa, **extras):
    origem = extras.pop("origem", "SISTEMA")
    aid = _assento(casa, especie="OBITO", numero="244",
                   nome="ANTONIO ENSAIO OBITO", origem=origem,
                   hora_fato="03:15", numero_do="12345678",
                   local_fato_nome="Residência",
                   local_fato_endereco="Rua do Ensaio, 10",
                   **extras)
    con = _con(casa)
    with con:
        _pessoa(con, aid, "FALECIDO", "ANTONIO ENSAIO OBITO",
                idade_no_fato="72 anos", estado_civil="casado")
        _pessoa(con, aid, "DECLARANTE", "MARIA ENSAIO OBITO")
    return aid


def _larguras(html: str) -> list[str]:
    return re.findall(r'width:\s*([0-9.]+)%', html)


# ------------------------------------------------ as três espécies na folha


def test_as_tres_especies_mostram_o_texto_com_teor_vazio(casa):
    """Página em branco é defeito. Nascimento, casamento e óbito usam a
    mesma tela; o texto sai dos campos via `rc_termo.montar`."""
    casos = (
        (_nascimento(casa), "MARIA ENSAIO NASCIMENTO", "compareceu"),
        (_casamento(casa), "JOAO ENSAIO CASAMENTO", "matrimônio"),
        (_obito(casa), "ANTONIO ENSAIO OBITO", "faleceu"),
    )
    for aid, nome, marca in casos:
        html = _liso(_abrir(casa, f"/rcpn/{aid}/folha"))
        assert nome in html, f"faltou {nome} na folha {aid}"
        assert marca in html, f"faltou «{marca}» na folha {aid}"
        assert "Frente" in html and "Verso" in html
        assert "table class=\"colunas\"" in html or "class=\"colunas\"" in html


def test_o_obito_traz_os_doze_incisos_do_art_255():
    """A tela de óbito é a mesma; o texto é o dos doze incisos."""
    achados = set()
    for c in LIVRO.CAMPOS_OBITO:
        m = re.search(r"art\. 255, ([IVX]+)", c.get("artigo") or "")
        if m:
            achados.add(m.group(1))
    assert achados >= {"I", "II", "III", "IV", "V", "VI", "VII", "VIII",
                       "IX", "X", "XI", "XII"}


def test_campo_exigido_vazio_vira_claro_nao_pagina_em_branco(casa):
    """O importado magro — só o nome — ainda mostra o termo, com claros."""
    aid = _assento(casa, especie="OBITO", numero="244",
                   nome="FALECIDO DE ENSAIO", origem="EOFICIO")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "FALECIDO DE ENSAIO" in html or "faleceu" in html.lower()
    assert "____________" in html
    assert "Prévia dos campos do assento" in html


# ------------------------------------------------ vazio vs congelado


def test_abrir_a_folha_com_teor_vazio_nao_congela(casa):
    aid = _obito(casa, origem="EOFICIO")
    _abrir(casa, f"/rcpn/{aid}/folha")
    _abrir(casa, f"/rcpn/{aid}/folha")
    teor = _con(casa).execute("SELECT teor FROM rc_assentos WHERE id=?",
                              (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


def test_a_folha_do_congelado_mostra_o_gravado_nao_o_remontado(casa):
    aid = _nascimento(casa)
    con = _con(casa)
    with con:
        TERMO.congelar(con, aid, serventia={
            "cidade": "Cidade Exemplo", "uf": "MA", "estado": "Maranhão",
            "registrador": "MARIO EXEMPLO DOS SANTOS",
            "titulo": "Tabelião e Oficial de Registro",
        }, agora=AGORA)
        con.execute("UPDATE rc_assentos SET teor=? WHERE id=?",
                    ("TEXTO CONGELADO DE ENSAIO — não remontar.", aid))
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "TEXTO CONGELADO DE ENSAIO" in html
    assert "Prévia dos campos do assento" not in html


def test_a_tela_do_termo_do_importado_tambem_nao_congela(casa):
    aid = _obito(casa, origem="EOFICIO")
    html = _liso(_abrir(casa, f"/rcpn/assentos/{aid}/termo"))
    assert "Como o termo vai ficar" in html
    assert "doze incisos do art. 255" in html
    teor = _con(casa).execute("SELECT teor FROM rc_assentos WHERE id=?",
                              (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


# ------------------------------------------------ o papel continua em 3 colunas


def test_a_folha_impressa_continua_com_tres_colunas_medidas(casa):
    """Oficial 01/09/2026: retrato, 1ª coluna estreita só com o número,
    3ª coluna um só recanto pautado, verso também. Livro no topo."""
    aid = _nascimento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert FOLHA.ORIENTACAO == "retrato"
    assert FOLHA.LARGURA_MM < FOLHA.ALTURA_MM
    assert FOLHA.COLUNAS[0]["largura"] < 0.10
    assert FOLHA.COLUNAS[0]["largura"] == pytest.approx(0.06)
    assert FOLHA.COLUNAS[1]["largura"] == pytest.approx(0.64)
    assert FOLHA.COLUNAS[2]["largura"] == pytest.approx(0.30)
    assert FOLHA.somam_um()
    larguras = _larguras(html)
    assert "6.0" in larguras or "6" in larguras
    assert "64.0" in larguras or "64" in larguras
    assert "30.0" in larguras or "30" in larguras
    assert html.count("Notas, Averbações e Retificações") >= 1
    assert html.count('class="campo-notas pautado"') == 2
    assert "<strong>Livro:</strong>" in html
    assert "A-1" in html
    assert "<strong>Termo:</strong>" in html
    assert "<strong>Folha:</strong>" in html
    assert "Verso" in html
    assert "pautado" in html
    assert 'class="pauta-linhas"' in html
    assert "class=\"prenome\"" not in html
    assert "paisagem" not in html.lower()
    assert "retrato" in html.lower()
    assert f"{FOLHA.LARGURA_MM}mm" in html
    assert f"{FOLHA.ALTURA_MM}mm" in html


def test_so_a_terceira_coluna_leva_um_bloco_pautado(casa):
    """Oficial 01/09/2026, 10:25: um só recanto pautado na 3ª coluna;
    1ª e 2ª lisas. Sem três caixas rotuladas."""
    aid = _nascimento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert FOLHA.A_TERCEIRA_COLUNA_E_PAUTADA
    assert FOLHA.SO_AVERBACOES_SAO_PAUTADAS is False
    assert FOLHA.PAUTA_ATRAVESSA_AS_COLUNAS is False
    assert FOLHA.PAUTA_PASSO_MM == 5.0
    assert 'class="col-numero"' in html
    assert "col-numero pautado" not in html
    assert "col-termo pautado" not in html
    assert 'class="campo-notas pautado"' in html
    assert "campo-averbacao" not in html
    assert "campo-retificacao" not in html
    assert "rotulo-campo" not in html
    assert html.count('class="pauta-linhas"') == 2
    assert html.count("campo-notas pautado") == 2  # frente e verso
    # Relato #124, 15/10/2026: a pauta desce até a margem de baixo — a altura
    # sai da conta de `rc_folha` (eram 155 mm fixos; hoje 180).
    assert f"min-height: {FOLHA.PAUTA_ALTURA_MM}mm" in html


def test_o_topo_da_folha_nao_desperdica_papel(casa):
    """Oficial 01/09/2026, manhã: tirar o espaço de cima não usado.
    A folha começa mais perto do topo; margem de casa pequena permanece."""
    aid = _nascimento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert FOLHA.MARGEM_TOPO_MM < 12
    assert FOLHA.MARGEM_TOPO_MM >= 4
    topo = re.search(r"margin-top:\s*([0-9.]+)mm", html)
    assert topo, "a folha não declara margin-top"
    assert float(topo.group(1)) == pytest.approx(FOLHA.MARGEM_TOPO_MM)
    assert float(topo.group(1)) < 12
    # padding-top da prévia no ecrã acompanha o topo curto
    pads = re.findall(r"padding:\s*([0-9.]+)mm\s+[0-9.]+mm", html)
    assert pads, "a prévia não declara padding com topo distinto"
    assert all(float(x) < 12 for x in pads)
    assert "height: 18mm" not in html
    assert "height: 16mm" not in html
    assert "margin-bottom:6mm" not in html
    assert "padding: 2mm 1mm" not in html
    assert "<strong>Livro:</strong>" in html
    assert "<strong>Termo:</strong>" in html
    assert "<strong>Folha:</strong>" in html
    assert "height: 9mm" not in html
    assert "height: 7mm" not in html


def test_a_aula_das_tres_colunas_saiu_da_tela_de_uso(casa):
    """A geometria fica no papel; a tela de uso não dá aula sobre ela."""
    aid = _obito(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "Três colunas, frente e verso" not in html
    assert "Inspeção Ordinária" not in html
    assert "COGEX" not in html
    assert "A-24" not in html
    assert "prazo de 30 dias" not in html

def test_pauta_da_terceira_coluna_linhas_uniformes(casa):
    """Um só título; um só bloco pautado; passo uniforme 5,0 mm."""
    aid = _nascimento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    passo = FOLHA.PAUTA_PASSO_MM
    assert passo == 5.0
    sizes = re.findall(r'<pattern[^>]*height="([0-9.]+)mm"', html)
    assert len(sizes) == 2, "frente e verso precisam de pauta"
    assert all(float(x) == pytest.approx(passo) for x in sizes)
    assert f"{passo}mm" in html
    bloco = re.search(r"\.campo-notas\.pautado\s*\{([^}]+)\}", html, re.S)
    assert bloco, "faltou a regra CSS da pauta da 3ª coluna"
    css = bloco.group(1)
    pad = re.search(r"padding-top:\s*([0-9.]+)mm", css)
    if pad:
        v = float(pad.group(1))
        assert v == 0 or abs(v % passo) < 1e-9, "padding-top da caixa pautada deve ser 0 ou múltiplo do passo"
    pad_sh = re.search(r"(?<!-)padding:\s*([0-9.]+)mm", css)
    if pad_sh:
        v = float(pad_sh.group(1))
        assert v == 0 or abs(v % passo) < 1e-9
    assert 'id="pauta-1"' in html and 'id="pauta-2"' in html
    assert 'y="4.88mm"' in html and 'height="0.12mm"' in html
    assert html.count("Notas, Averbações e Retificações") >= 1
    assert html.count('class="campo-notas pautado"') == 2
    assert "rotulo-campo" not in html
    assert "campo-averbacao" not in html
    assert "campo-retificacao" not in html

