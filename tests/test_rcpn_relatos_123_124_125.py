"""Relatos #123, #124 e #125 do RCPN — 15/10/2026.

#123 (08/10, /rcpn/formulario/CASAMENTO): «página de visualização do teor não
     chega a lugar algum e não puxa quem está assinando o ato, ficando lacuna
     para preencher».
#124 (08/10): «adequar todos os termos do RCPN para constar campo de
     assinatura para quem assina o ato; e expandir a parte de baixo para
     alcançar mais a margem de baixo».
#125 (08/10, /rcpn/novo/casamento): «carimbo do selo, na parte do número do
     selo, está mal posicionado e passando da parte do carimbo, entrando no
     campo das averbações».

O que estes testes guardam está escrito em cada um. Usuários de teste:
mario (ADMIN, da fixture). Nenhum documento real.
"""
from __future__ import annotations

import os
import re
import sqlite3
from pathlib import Path

import pytest

from test_rc_folha_tela import (  # noqa: F401
    casa, _con, _abrir, _assento, _pessoa, _nascimento, _obito, _casamento,
    _token,
)

import rc_folha as FOLHA                                         # noqa: E402
import rc_termo as RCT                                           # noqa: E402

AGORA = "2026-10-15T10:00:00"
NOME_MARIO = "MARIO EXEMPLO DOS SANTOS"
FUNCAO_MARIO = "Escrevente Autorizado de Ensaio"

# Selo de casamento com a etiqueta INTEIRA, como o razão a guarda — os nomes
# das partes e os quatro fundos alongam o carimbo, que é o caso do relato #125.
SELO_CASAMENTO = "HABCAS0000009ZYQS3MCYZOV5U97"
ETIQUETA_CASAMENTO = (
    "Poder Judiciário – TJMA. Selo: HABCAS0000009ZYQS3MCYZOV5U97, "
    "15/10/2026 10:00:00, Ato: 14.1.1, "
    "Parte(s): JOAO ENSAIO CASAMENTO DE OLIVEIRA SOBRENOME LONGO, "
    "MARIA ENSAIO CASAMENTO DE SOUSA SOBRENOME MAIS LONGO AINDA, "
    "Total R$ 340,51 Emol R$ 304,03 FERC R$ 9,12 FADEP R$ 12,16 "
    "FEMP R$ 12,16 FERRFIS R$ 3,04 Consulte em https://selo.tjma.jus.br")


def _mario_com_funcao(casa):
    con = _con(casa)
    with con:
        con.execute("UPDATE users SET funcao=? WHERE username='mario'",
                    (FUNCAO_MARIO,))


def _registro(casa, aid, *, selo="", etiqueta="", criado_por=NOME_MARIO):
    con = _con(casa)
    with con:
        con.execute(
            "INSERT INTO rc_atos (assento_id, tipo, selo, data_ato, criado_em,"
            " criado_por) VALUES (?, 'REGISTRO', ?, ?, ?, ?)",
            (aid, selo, AGORA, AGORA, criado_por))
        if selo and etiqueta:
            con.execute(
                """INSERT INTO sd_selos (numero, texto, caminho, atribuicao,
                                         referencia, tabela, ato_id,
                                         obtido_em, usado_em)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (selo, etiqueta, "/selo/civil/casamento", "CIVIL",
                 f"rc_assentos:{aid}", "rc_assentos", aid, AGORA, AGORA))


def _emancipacao(casa):
    aid = _assento(casa, especie="EMANCIPACAO", numero="77",
                   nome="PEDRO ENSAIO EMANCIPADO")
    con = _con(casa)
    with con:
        _pessoa(con, aid, "REGISTRADO", "PEDRO ENSAIO EMANCIPADO")
    return aid


def _natimorto(casa):
    aid = _assento(casa, especie="NATIMORTO", numero="12",
                   nome="NATIMORTO DE ENSAIO")
    con = _con(casa)
    with con:
        _pessoa(con, aid, "DECLARANTE", "ANA ENSAIO DECLARANTE")
    return aid


# =========================================================== relato #123


def test_o_formulario_ja_abre_com_quem_assina_preenchido(casa):
    """A lacuna do relato: os dois claros de quem assina chegavam vazios.
    Agora vêm de quem está na tela (a regra da lavratura) e só se leem."""
    _mario_com_funcao(casa)
    html = _abrir(casa, "/rcpn/formulario/CASAMENTO")
    campo = re.search(r'<input[^>]*name="escrevente"[^>]*>', html)
    assert campo, "o formulário não tem o claro de quem assina"
    assert "readonly" in campo.group(0)
    assert f'value="{NOME_MARIO}"' in campo.group(0)
    funcao = re.search(r'<input[^>]*name="funcao_do_escrevente"[^>]*>', html)
    assert funcao and "readonly" in funcao.group(0)
    assert f'value="{FUNCAO_MARIO}"' in funcao.group(0)


def test_ver_como_fica_assina_com_o_nome_e_nao_com_o_traco(casa):
    """POST da prévia: «Eu, ____________, Oficial» era o defeito (sv() não
    tem quem assina). E o formulário digitado não vence a regra (#65)."""
    _mario_com_funcao(casa)
    c = casa["cliente"]
    pagina = c.get("/rcpn/formulario/CASAMENTO").get_data(as_text=True)
    r = c.post("/rcpn/formulario/CASAMENTO", data={
        "csrf_token": _token(pagina), "acao": "ver",
        "escrevente": "OUTRA PESSOA QUALQUER",
        "funcao_do_escrevente": "Oficial"})
    assert r.status_code == 200
    html = r.get_data(as_text=True)
    montado = re.search(r"Como o termo fica</h2>\s*<pre[^>]*>(.*?)</pre>",
                        html, re.S)
    assert montado, "a prévia não saiu"
    texto = montado.group(1)
    assert f"Eu, {NOME_MARIO}, {FUNCAO_MARIO}" in texto
    assert "OUTRA PESSOA QUALQUER" not in texto
    assert "Eu, ____________" not in texto


def test_a_tela_tem_saida_para_lavrar_e_para_mudar_o_texto(casa):
    """«Não chega a lugar algum»: a tela só tinha Ver e Voltar."""
    html = _abrir(casa, "/rcpn/formulario/CASAMENTO")
    assert 'href="/rcpn/novo/casamento"' in html
    assert "/modelos?editar=RC_TERMO_CASAMENTO" in html
    assert "Lavrar um registro com este termo" in html
    assert "Mudar o texto deste termo" in html
    # Livro E não tem espécie única: leva ao seletor de espécie.
    html_e = _abrir(casa, "/rcpn/formulario/LIVRO_E")
    assert 'href="/rcpn/novo"' in html_e
    assert "/modelos?editar=RC_TERMO_LIVRO_E" in html_e


def test_o_texto_velho_que_dizia_nao_ser_o_do_livro_saiu(casa):
    """O cartão dizia «Este ainda não é o texto que se congela no assento»
    — falso desde 31/08/2026."""
    for chave in ("NASCIMENTO", "CASAMENTO", "OBITO", "LIVRO_E"):
        html = _abrir(casa, f"/rcpn/formulario/{chave}")
        assert "Este ainda não é o texto que se congela" not in html
        assert "passa hoje pelos modelos do E-Ofício" not in html
        assert "Conferir com um assento real" in html, chave
        assert "É este o texto que vai ao livro" in html, chave


@pytest.mark.parametrize("especie", ["NASCIMENTO", "CASAMENTO", "OBITO",
                                     "LIVRO_E"])
def test_conferir_com_assento_real_nas_quatro_especies(casa, especie):
    """Antes: só o nascimento tinha o botão — e ele dava HTTP 500
    (`data_extenso` não é parâmetro da ponte). Agora as quatro, pela mesma
    montagem da lavratura, com quem assina preenchido."""
    _mario_com_funcao(casa)
    aid, numero, nome = {
        "NASCIMENTO": lambda: (_nascimento(casa), "8687",
                               "MARIA ENSAIO NASCIMENTO"),
        "CASAMENTO": lambda: (_casamento(casa), "40",
                              "JOAO ENSAIO CASAMENTO"),
        "OBITO": lambda: (_obito(casa), "244", "ANTONIO ENSAIO OBITO"),
        "LIVRO_E": lambda: (_emancipacao(casa), "77",
                            "PEDRO ENSAIO EMANCIPADO"),
    }[especie]()
    r = casa["cliente"].get(f"/rcpn/formulario/{especie}?assento={numero}")
    assert r.status_code == 200, r.status_code
    html = r.get_data(as_text=True)
    assert "Não achei" not in html
    bloco = re.search(r"Conferir com um assento real(.*?)</div>", html, re.S)
    assert bloco
    assert nome in bloco.group(1)
    assert f"Eu, {NOME_MARIO}, {FUNCAO_MARIO}" in bloco.group(1)


def test_conferir_numero_que_nao_existe_diz_que_nao_achou(casa):
    html = _abrir(casa, "/rcpn/formulario/OBITO?assento=999999")
    assert "Não achei termo de óbito com o número 999999." in html


def test_a_conferencia_e_a_lavratura_montam_igual(casa):
    """Uma régua só: `montar` devolve o texto de `montar_para_conferir`."""
    aid = _casamento(casa)
    sv = {"cidade": "Cidade Exemplo", "uf": "MA", "estado": "Maranhão",
          "registrador": NOME_MARIO, "titulo": "Oficial"}
    con = _con(casa)
    r = RCT.montar_para_conferir(con, aid, serventia=sv)
    assert r["texto"] == RCT.montar(con, aid, serventia=sv)
    assert {"texto", "em_branco", "completo"} <= set(r)


# =========================================================== relato #124


def test_toda_especie_com_termo_tem_quem_assina_declarado():
    """Espécie com termo e sem linha de assinatura é o defeito do relato.
    A tabela da folha tem de cobrir TODAS as espécies que têm modelo."""
    com_termo = set(RCT.MODELO_DA_ESPECIE)
    assert com_termo <= set(FOLHA.ASSINAM_ALEM_DE_QUEM_LAVROU), (
        com_termo - set(FOLHA.ASSINAM_ALEM_DE_QUEM_LAVROU))


def test_natimorto_tem_declarante_e_quem_lavrou(casa):
    _mario_com_funcao(casa)
    aid = _natimorto(casa)
    _registro(casa, aid)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert html.count('class="assinaturas-do-termo"') == 1
    assert "ANA ENSAIO DECLARANTE, Declarante" in html
    assert f"{NOME_MARIO}, {FUNCAO_MARIO}" in html


def test_livro_e_tem_a_linha_de_quem_lavrou(casa):
    """O termo do Livro E diz só «Eu, …, dou fé e assino»: uma linha."""
    _mario_com_funcao(casa)
    aid = _emancipacao(casa)
    _registro(casa, aid)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert html.count('class="assinaturas-do-termo"') == 1
    assert html.count('class="assinatura"') == 1
    assert f"{NOME_MARIO}, {FUNCAO_MARIO}" in html


def _testemunhas(casa, aid, *nomes):
    con = _con(casa)
    with con:
        for n in nomes:
            _pessoa(con, aid, "TESTEMUNHA", n)


def _linhas_de_assinatura(html: str) -> list[str]:
    return re.findall(r'<div class="nome-ass">(.*?)</div>', html)


def test_casamento_assinam_testemunhas_e_juiz_de_paz(casa):
    """Resposta do oficial (15/10/2026): testemunhas e juiz de paz ganham
    linha com o nome; sem nome, a linha sai com o rótulo da função. Ordem:
    nubentes, testemunhas, juiz de paz, quem lavrou — duas por linha."""
    _mario_com_funcao(casa)
    aid = _casamento(casa)
    _testemunhas(casa, aid, "CARLA ENSAIO TESTEMUNHA",
                 "BEATRIZ ENSAIO TESTEMUNHA")
    _registro(casa, aid)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert 'class="assinaturas-do-termo em-par"' in html
    assert _linhas_de_assinatura(html) == [
        "JOAO ENSAIO CASAMENTO, Primeiro nubente",
        "MARIA ENSAIO CASAMENTO, Segundo nubente",
        "CARLA ENSAIO TESTEMUNHA, Testemunha",
        "BEATRIZ ENSAIO TESTEMUNHA, Testemunha",
        "Juiz(a) de Paz",
        f"{NOME_MARIO}, {FUNCAO_MARIO}",
    ]


def test_casamento_sem_testemunha_ainda_tem_duas_linhas(casa):
    """Código Civil, art. 1.534: duas testemunhas no mínimo. Sem nome no
    assento, as duas linhas saem com o rótulo, para assinar à mão."""
    aid = _casamento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    linhas = _linhas_de_assinatura(html)
    assert linhas.count("Testemunha") == 2
    assert "Juiz(a) de Paz" in linhas


def test_juiz_de_paz_do_acervo_vem_do_celebrante(casa):
    """O assento lavrado aqui não tem campo para quem presidiu; o do acervo
    traz `strNomeCelebrante` — e é ele que sai na linha."""
    import json
    aid = _casamento(casa, dados_json=json.dumps(
        {"strNomeCelebrante": "PAULO ENSAIO JUIZ DE PAZ"}))
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "PAULO ENSAIO JUIZ DE PAZ, Juiz(a) de Paz" in html


# ------------------------------------- o campo do juiz de paz (15/10/2026)


def test_a_coluna_do_juiz_de_paz_nasce_por_migracao_idempotente(casa):
    """Aditiva e idempotente: rodar o esquema de novo não estoura nem
    duplica; a coluna existe no banco do teste."""
    import rc_schema as RCS
    con = _con(casa)
    with con:
        RCS.init_rc_schema(con)
        RCS.init_rc_schema(con)
    colunas = [r[1] for r in con.execute("PRAGMA table_info(rc_assentos)")]
    assert colunas.count("juiz_de_paz") == 1
    assert ("rc_assentos", "juiz_de_paz", "TEXT") in RCS.MIGRACOES


def test_juiz_de_paz_so_no_casamento_civil():
    import rc_assento as RC
    assert "juiz_de_paz" in RC.CAMPOS_DO_TERMO_POR_ESPECIE["CASAMENTO"]
    assert "juiz_de_paz" not in RC.CAMPOS_DO_TERMO_POR_ESPECIE[
        "CASAMENTO_RELIGIOSO"]
    assert "juiz_de_paz" not in RC.CAMPOS_DO_TERMO_POR_ESPECIE["OBITO"]


def test_o_juiz_de_paz_grava_no_assento_e_sai_na_folha(casa):
    """O nome entra pelo caminho do termo (o mesmo da lavratura e da
    edição) e sai embaixo da linha da folha; o religioso recusa."""
    import rc_assento as RC
    aid = _casamento(casa)
    rel = _assento(casa, especie="CASAMENTO_RELIGIOSO", numero="41",
                   nome="CASAL RELIGIOSO DE ENSAIO")
    con = _con(casa)
    with con:
        RC.anotar_do_termo(con, aid, juiz_de_paz="PAULO ENSAIO DA PAZ")
        with pytest.raises(RC.RcError):
            RC.anotar_do_termo(con, rel, juiz_de_paz="NAO PODE ENTRAR")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "PAULO ENSAIO DA PAZ, Juiz(a) de Paz" in html


def test_a_coluna_vence_o_celebrante_do_acervo(casa):
    """Corrigido na ficha, o nome novo é o que sai — não o do blob."""
    import json
    import rc_assento as RC
    aid = _casamento(casa, dados_json=json.dumps(
        {"strNomeCelebrante": "NOME ANTIGO DO ACERVO"}))
    con = _con(casa)
    with con:
        RC.anotar_do_termo(con, aid, juiz_de_paz="NOME CORRIGIDO NA FICHA")
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert "NOME CORRIGIDO NA FICHA, Juiz(a) de Paz" in html
    assert "NOME ANTIGO DO ACERVO" not in html


def test_as_telas_de_lavrar_e_editar_perguntam_o_juiz_de_paz(casa):
    html = _abrir(casa, "/rcpn/novo/casamento")
    assert 'name="juiz_de_paz"' in html
    assert "Juiz(a) de Paz que presidiu o ato" in html
    rel = _abrir(casa, "/rcpn/novo/casamento-religioso")
    assert 'name="juiz_de_paz"' not in rel
    import rc_assento as RC
    aid = _casamento(casa)
    con = _con(casa)
    with con:
        RC.anotar_do_termo(con, aid, juiz_de_paz="PAULO ENSAIO DA PAZ")
    ed = _abrir(casa, f"/rcpn/{aid}/editar")
    campo = re.search(r'<input name="juiz_de_paz"[^>]*>', ed)
    assert campo and 'value="PAULO ENSAIO DA PAZ"' in campo.group(0)


@pytest.mark.parametrize("especie,papeis,esperado", [
    ("UNIAO_ESTAVEL",
     (("COMPANHEIRO1", "ANA ENSAIO COMPANHEIRA"),
      ("COMPANHEIRO2", "JOSE ENSAIO COMPANHEIRO")),
     ["ANA ENSAIO COMPANHEIRA, Primeiro(a) companheiro(a)",
      "JOSE ENSAIO COMPANHEIRO, Segundo(a) companheiro(a)"]),
    ("OPCAO_NACIONALIDADE",
     (("REGISTRADO", "LUIS ENSAIO OPTANTE"),),
     ["LUIS ENSAIO OPTANTE, Optante"]),
    ("INTERDICAO",
     (("REGISTRADO", "RUI ENSAIO INTERDITADO"),
      ("REQUERENTE", "VERA ENSAIO REQUERENTE")),
     ["VERA ENSAIO REQUERENTE, Requerente"]),
    ("AUSENCIA", (("REGISTRADO", "SAULO ENSAIO AUSENTE"),),
     ["Requerente"]),
])
def test_livro_e_as_partes_assinam(casa, especie, papeis, esperado):
    """Resposta do oficial (15/10/2026): no Livro E as partes assinam —
    companheiros, optante, e quem o termo nomeia como requerente."""
    _mario_com_funcao(casa)
    aid = _assento(casa, especie=especie, numero="78",
                   nome=papeis[0][1])
    con = _con(casa)
    with con:
        for papel, nome in papeis:
            _pessoa(con, aid, papel, nome)
    _registro(casa, aid)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert _linhas_de_assinatura(html) == esperado + [
        f"{NOME_MARIO}, {FUNCAO_MARIO}"]


def test_quem_assina_pela_serventia_continua_so_leitura(casa):
    """Regra do relato #65, confirmada pelo oficial: não se escolhe."""
    for chave in ("NASCIMENTO", "CASAMENTO", "OBITO", "LIVRO_E"):
        html = _abrir(casa, f"/rcpn/formulario/{chave}")
        for nome in ("escrevente", "funcao_do_escrevente"):
            campo = re.search(rf'<input[^>]*name="{nome}"[^>]*>', html)
            assert campo and "readonly" in campo.group(0), (chave, nome)


def test_o_odt_da_folha_do_livro_e_traz_a_linha_de_quem_lavrou(casa):
    """O ODT editável da folha usa as mesmas linhas da tela."""
    import io
    import zipfile
    _mario_com_funcao(casa)
    aid = _emancipacao(casa)
    _registro(casa, aid)
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel?formato=odt")
    assert r.status_code == 200
    xml = zipfile.ZipFile(io.BytesIO(r.data)).read(
        "content.xml").decode("utf-8")
    assert f"{NOME_MARIO}, {FUNCAO_MARIO}" in xml
    assert "_" * 45 in xml


def test_a_pauta_desce_ate_a_margem_de_baixo(casa):
    """A pauta tinha 155 mm fixos (31 linhas) e deixava a folha em branco
    embaixo. Agora a altura sai da conta da folha e cabe na página."""
    assert FOLHA.PAUTA_ALTURA_MM > 155.0
    assert FOLHA.PAUTA_LINHAS == int(FOLHA.PAUTA_ALTURA_MM
                                     // FOLHA.PAUTA_PASSO_MM)
    # a pauta é múltiplo do passo: a última linha fecha a caixa
    assert FOLHA.PAUTA_ALTURA_MM % FOLHA.PAUTA_PASSO_MM == pytest.approx(0)
    # e a conta fecha dentro da folha, já com o zoom da impressão
    assert (FOLHA.PAUTA_ALTURA_MM + FOLHA.RESERVA_FORA_DA_PAUTA_MM
            <= FOLHA.altura_util_impressa_mm() + 1e-9)
    aid = _casamento(casa)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    assert f"min-height: {FOLHA.PAUTA_ALTURA_MM}mm" in html


# =========================================================== relato #125


def test_casamento_o_carimbo_fica_na_coluna_do_termo(casa):
    """O número do selo invadia a coluna das averbações. O carimbo mora na
    célula do termo, com quebra dentro da caixa, e nada dele vai à 3ª."""
    _mario_com_funcao(casa)
    aid = _casamento(casa)
    _registro(casa, aid, selo=SELO_CASAMENTO, etiqueta=ETIQUETA_CASAMENTO)
    html = _abrir(casa, f"/rcpn/{aid}/folha")
    termo = re.search(r'<td class="col-termo">(.*?)</td>', html, re.S)
    margem = re.search(r'<td class="col-margem">(.*?)</td>', html, re.S)
    assert termo and margem
    assert 'class="carimbo-do-selo"' in termo.group(1)
    assert SELO_CASAMENTO in termo.group(1)
    assert SELO_CASAMENTO not in margem.group(1)
    assert "carimbo" not in margem.group(1)
    # a caixa não passa da coluna, e o número quebra dentro dela
    css = re.search(r"\.carimbo-do-selo \.carimbo-texto\s*\{([^}]*)\}", html)
    assert css and "overflow-wrap: anywhere" in css.group(1)
    assert re.search(r"\.carimbo-do-selo\s*\{[^}]*max-width:\s*100%", html)
    assert re.search(r"\.carimbo-link\s*\{[^}]*word-break:\s*break-all", html)
    # nubentes e quem lavrou continuam assinando
    assert "JOAO ENSAIO CASAMENTO, Primeiro nubente" in html
    assert f"{NOME_MARIO}, {FUNCAO_MARIO}" in html


# ------------------------------------------- o papel de verdade (Chrome)


def _pdf_da_folha(casa, aid) -> bytes:
    import impressao_pdf as PDFIMP
    if PDFIMP.onde_esta_o_chrome() is None:
        pytest.skip("sem Chrome/Edge nesta máquina para imprimir a folha")
    pytest.importorskip("pypdfium2")
    r = casa["cliente"].get(f"/rcpn/{aid}/folha/papel")
    if r.status_code != 200 or not r.data.startswith(b"%PDF"):
        pytest.skip("o Chrome não devolveu o PDF nesta rodada")
    destino = os.environ.get("RELATO124_PDF")
    if destino:
        Path(destino).write_bytes(r.data)
    return r.data


def _medidas_da_frente(pdf: bytes) -> dict:
    """Páginas, e onde a pauta da 3ª coluna termina na frente (mm)."""
    import pypdfium2 as pdfium
    doc = pdfium.PdfDocument(pdf)
    paginas = len(doc)
    pagina = doc[0]
    largura_pt, altura_pt = pagina.get_size()
    escala = 4
    img = pagina.render(scale=escala).to_pil().convert("L")
    w, h = img.size
    px = img.load()
    # A pauta é cinza-claro e fina: a linha dela é a fileira de pixels em que
    # quase toda a largura da 3ª coluna sai do branco. Texto não faz isso.
    x0, x1 = int(w * 0.72), int(w * 0.95)
    ultima = None
    for y in range(h - 1, 0, -1):
        tinta = sum(1 for x in range(x0, x1, 2) if px[x, y] < 245)
        if tinta > (x1 - x0) / 2 * 0.8:
            ultima = y
            break
    mm_por_px = (altura_pt / 72 * 25.4) / h
    return {"paginas": paginas,
            "altura_mm": altura_pt / 72 * 25.4,
            "fim_da_pauta_mm": (ultima or 0) * mm_por_px,
            "sobra_embaixo_mm": (h - (ultima or 0)) * mm_por_px}


def test_no_papel_a_frente_cabe_numa_pagina_e_a_pauta_desce(casa):
    """Prova no PDF que o Chrome imprime (o mesmo da rota): frente e verso
    são DUAS páginas — nada empurrado para uma terceira — e a pauta da
    frente desce: medido antes, a última linha ficava a 52 mm da borda de
    baixo; agora fica a menos de 26 mm (5 mm são a margem da impressora).

    O cabeçalho da bancada leva endereço e contato, como o da produção — é
    ele que decide quanto sobra para a pauta."""
    casa["db"].set_settings({
        "unit_name": "Ofício Único de Cidade Exemplo",
        "serventia_endereco": "Rua de Ensaio, 100, Centro",
        "serventia_cep": "00000-000",
        "serventia_telefone": "(00) 0000-0000",
        "serventia_email": "contato@exemplo.invalid"})
    _mario_com_funcao(casa)
    aid = _casamento(casa)
    # Seis linhas de assinatura — nubentes, duas testemunhas, juiz de paz e
    # quem lavrou —, que é o caso mais alto da frente (resposta de 15/10).
    _testemunhas(casa, aid, "CARLA ENSAIO TESTEMUNHA",
                 "BEATRIZ ENSAIO TESTEMUNHA")
    _registro(casa, aid, selo=SELO_CASAMENTO, etiqueta=ETIQUETA_CASAMENTO)
    m = _medidas_da_frente(_pdf_da_folha(casa, aid))
    assert m["paginas"] == 2, m
    assert m["sobra_embaixo_mm"] < 26, m
    assert m["sobra_embaixo_mm"] > 5, m
