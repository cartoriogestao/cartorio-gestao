"""O ensaio de atos das Notas: cada situação de parte pelas telas de verdade, e o papel conferido com a lei.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída. […] Queria antecipar esses problemas e processar antes de
encontrar na prática.»

O QUE ESTE TESTE FAZ
    `test_fluxo_notas` já leva cada minuta de fábrica do protocolo pago à certidão, com duas pessoas
    solteiras e maiores. Este pratica os casos de `ensaio_de_atos_notas.casos` — o casado e o cônjuge
    que consente, o procurador, o menor e quem o representa, a pessoa jurídica, quem não sabe assinar,
    o testador cego — pelas mesmas telas, e confere o termo que vai ao livro contra o requisito da norma
    citada em cada teste. A leitura que não cabe numa conferência está em
    `docs/ensaio_de_atos/relatorio_notas.md`; o inventário em `docs/ensaio_de_atos/inventario_notas.md`.

A TRAVA ESTÁ LIGADA: barra rede, programa e gravação fora da pasta temporária. A ÚNICA porta que ela
    deixa é a do selador de mentira desta máquina (`selador_falso`, TLS em 127.0.0.1): a lavratura das
    Notas sela pelo aparelho, e não pelo selo digitado como a do Registro Civil.

OS DEFEITOS FICAM À VISTA
    A asserção é a da lei, e não a do que o sistema faz hoje. O defeito aberto fica em
    `xfail(strict=True)`, com o motivo; consertado, o teste avisa (XPASS) e a marca sai.

PARA LER OS DOCUMENTOS: `CG_ENSAIO_SAIDA=1` grava cada caso em `<pasta temporária>/ensaio_de_atos_notas/`.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

import ensaio_de_atos_notas as EN
import layout_ensaio as E
import test_fluxo_notas as F

pytestmark = pytest.mark.lento

CASOS = {c.chave: c for c in EN.casos()}


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _decisao(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DECISÃO DO OFICIAL: {motivo}")


#: Quem comparece por outra parte sai com a marca «DIGA JUNTO DE QUEM REPRESENTA», que trava a
#: lavratura: o quadro «Partes» ainda não diz quem ele representa (relatorio_notas.md, item 2, à espera
#: do oficial). O resto destes casos se confere no teor montado.
ESPERAM_O_ITEM_2 = ("cv_por_procurador", "cv_pj_compradora", "doacao_a_menor", "pacto_nubente_menor",
                    "proc_a_rogo")
_ITEM_2 = _decisao("quem representa ainda não tem campo; a marca trava a lavratura (item 2)")


# ------------------------------------------------------------------ a bancada e a prática

@pytest.fixture()
def bancada(cg_casa, monkeypatch):
    """A bancada de `test_fluxo_notas`, com a trava ligada e só a porta do selador aberta."""
    from conftest import cg_login
    from selador_de_bancada import ligar_o_selador

    db = cg_casa["db"]
    db.create_user("oficial", F.OFICIAL, F.SENHA, "ADMIN")
    db.create_user("escrevente", F.ESCREVENTE, F.SENHA, "USER")
    db.set_settings(F.SERVENTIA)
    F._semear_a_tabela(db)
    monkeypatch.setitem(cg_casa["app"].extensions, "notas_medir_paginas", lambda odt: 2)
    c = cg_casa["app"].test_client()
    cg_login(c, "escrevente", F.SENHA)
    b = {"app": cg_casa["app"], "cliente": c, "banco": cg_casa["banco"], "db": db, "dados": cg_casa["dados"]}
    with ligar_o_selador(b, protocolo_pago=False) as aparelho:
        F._aparelho_com_valores(aparelho)
        b["aparelho"] = aparelho
        E.ligar_trava(cg_casa["dados"], portas_locais=(aparelho.porta,))
        try:
            yield b
        finally:
            E.desligar_trava()


#: O que já saiu, por caso, neste processo: o papel é texto, e não depende mais da bancada.
_FEITOS: dict[str, EN.Saida] = {}


@pytest.fixture()
def praticado(bancada):
    """`praticado("chave")` — o caso, praticado uma vez por processo. A bancada sobe sempre (pedi-la no
    meio do teste, com `getfixturevalue`, desmontava o banco do teste seguinte)."""
    def _praticar(chave: str) -> EN.Saida:
        if chave not in _FEITOS:
            s = EN.praticar(bancada, CASOS[chave])
            _FEITOS[chave] = s
            if os.environ.get("CG_ENSAIO_SAIDA"):
                pasta = Path(tempfile.gettempdir()) / "ensaio_de_atos_notas"
                pasta.mkdir(exist_ok=True)
                (pasta / f"{chave}.txt").write_text(EN.em_texto(s), encoding="utf-8")
        return _FEITOS[chave]
    return _praticar


def _lavrado(praticado, chave: str) -> EN.Saida:
    s = praticado(chave)
    assert s.situacao == "LAVRADO", f"{chave} não foi ao livro: {s.avisos}"
    return s


def _teor(praticado, chave: str) -> str:
    """O teor montado pela minuta — o que vai ao livro, lavrado ou não."""
    s = praticado(chave)
    assert s.teor, f"{chave} não montou o teor: {s.avisos}"
    return s.teor


def _marcado_fora_dos_lados(teor: str, nome: str) -> bool:
    """`nome` sai qualificado e com a marca de quem comparece por outro, e não como parte."""
    return bool(re.search(re.escape(nome) + r"[^\[;]*\[[^\]]*DIGA JUNTO DE QUEM REPRESENTA", teor))


def _abertura(termo: str) -> str:
    """O comparecimento: de «compareceu/compareceram» até o reconhecimento da identidade."""
    m = re.search(r"comparece(?:u|ram)(.*?)(?:todos )?reconhecid", termo, re.S | re.I)
    assert m, "o termo não tem o comparecimento"
    return m.group(1)



# ------------------------------------------------------------------ todo caso vai ao livro

#: Os casos que o balcão tem de recusar — e o teste que confere a recusa.
RECUSADOS = {"emancipacao_menor_de_16": "test_a_emancipacao_confere_os_dezesseis_anos"}


@pytest.mark.parametrize("chave", [pytest.param(c, marks=_ITEM_2) if c in ESPERAM_O_ITEM_2 else c
                                   for c in CASOS if c not in RECUSADOS])
def test_o_caso_vai_ao_livro_com_selo_e_o_traslado_reproduz_o_termo(praticado, chave):
    """Do protocolo pago ao termo, pelo balcão; o selo no termo (CN-MA arts. 130 e 131) e o traslado
    com o teor do livro (CN-MA art. 850, § 2º)."""
    s = _lavrado(praticado, chave)
    assert "SELO" in s.termo.upper(), "o termo saiu sem o selo"
    assert s.traslado and "Traslado" in s.traslado
    assert EN.tem(s.traslado, _abertura(s.termo)[:200])


# ------------------------------------------------------------------ o que já está certo

def test_o_testador_cego_ouve_o_testamento_duas_vezes(praticado):
    """CC art. 1.867: ao cego, o testamento é lido em voz alta duas vezes, uma pelo tabelião e outra
    por testemunha que ele designar, com menção circunstanciada."""
    t = _lavrado(praticado, "testamento_cego").termo
    assert EN.tem(t, "cego", "duas vezes", "LUCIA EXEMPLO TESTEMUNHA", "designada")


def test_quem_nao_sabe_assinar_o_testamento_assina_a_rogo_uma_testemunha(praticado):
    """CC art. 1.865: o tabelião declara e assina a rogo uma das testemunhas instrumentárias."""
    t = _lavrado(praticado, "testamento_nao_assina").termo
    assert EN.tem(t, "a seu rogo", "PAULO EXEMPLO TESTEMUNHA", "1.865", "impressão digital")
    # «sabe | pode» é escolha desde 03/11/2026 (observação 11): o «não» é da minuta.
    assert EN.tem(t, "o TESTADOR não sabe assinar") and not EN.tem(t, "não não")


def test_a_procuracao_para_alienar_imovel_arquiva_a_certidao_do_registro(praticado):
    """CC art. 661, § 1º (poderes especiais e expressos) e CN-MA art. 833 (certidão atualizada do RI,
    exigida e arquivada)."""
    t = _lavrado(praticado, "proc_alienar_imovel").termo
    assert EN.tem(t, "661, § 1º", "certidão atualizada do registro de imóveis", "833")


def test_a_divorcianda_que_volta_ao_nome_de_solteira_fica_no_termo(praticado):
    """CN-MA art. 822 (como o LT02 cita): a declaração do nome que cada um passa a usar."""
    t = _lavrado(praticado, "divorcio_com_nome").termo
    assert EN.tem(t, "JOANA EXEMPLO DOS SANTOS voltará a usar o nome de solteiro(a)")


# ------------------------------------------------------------------ quem comparece, e em que qualidade

def test_o_procurador_do_vendedor_nao_vira_comprador(praticado):
    """CN-MA art. 798, VI: a parte representada, com a menção da procuração. O procurador comparece
    pelo outorgante; não é parte do outro lado do negócio. Consertado em 03/11/2026 (item 1): até o
    item 2, ele sai marcado para o escrevente o pôr junto do vendedor."""
    assert _marcado_fora_dos_lados(_teor(praticado, "cv_por_procurador"), "CARLOS EXEMPLO PROCURADOR")


def test_o_representante_da_compradora_nao_vira_vendedor(praticado):
    """CN-MA art. 798, V (qualificação da pessoa jurídica, com quem a representa)."""
    assert _marcado_fora_dos_lados(_teor(praticado, "cv_pj_compradora"), "ANA EXEMPLO SOCIA")


def test_a_mae_que_representa_o_donatario_menor_nao_vira_doadora(praticado):
    """CN-MA art. 798, VII: havendo interesse de menor, a data de nascimento, o assento e por quem está
    representado. O que falta — dizer que o donatário é menor e o assento — é o item 2."""
    assert _marcado_fora_dos_lados(_teor(praticado, "doacao_a_menor"), "JOANA EXEMPLO DOS SANTOS")


def test_a_assistente_da_nubente_menor_nao_vira_nubente(praticado):
    """CC art. 1.654: o pacto do menor depende da aprovação do representante legal — que assiste, e
    não pactua."""
    assert _marcado_fora_dos_lados(_teor(praticado, "pacto_nubente_menor"), "JOANA EXEMPLO DOS SANTOS")


def test_o_casal_em_comunhao_vende_junto(praticado):
    """Decisão do oficial, 03/11/2026 (item 3): no imóvel do casal em comunhão, os dois cônjuges são
    outorgantes vendedores, cada um qualificado com o outro e o regime (CC art. 215, § 1º, III)."""
    abertura = _abertura(_lavrado(praticado, "cv_casado_com_outorga").termo)
    vendedores = abertura.split("como OUTORGADO")[0]
    # a qualificação de cada um, e não só o nome: o do marido traz «casado com JOANA …»
    assert "MARIO EXEMPLO DOS SANTOS, brasileiro" in vendedores
    assert "JOANA EXEMPLO DOS SANTOS, brasileira" in vendedores
    assert "ANUENTE" not in abertura


def test_o_conjuge_anuente_consente_e_nao_vende(praticado):
    """CC art. 1.647, I: nenhum dos cônjuges pode, sem autorização do outro (exceto na separação
    absoluta), alienar ou gravar de ônus real os bens imóveis. Decisão do oficial, 03/11/2026 (item 3):
    o anuente sai com a frase do consentimento, e nunca como vendedor."""
    abertura = _abertura(_lavrado(praticado, "cv_bem_particular_com_anuente").termo)
    assert EN.tem(abertura, "e, como ANUENTE, JOANA EXEMPLO DOS SANTOS", "que consente no presente ato",
                  "1.647, I")
    antes_do_anuente = abertura.split("como ANUENTE")[0]
    assert "JOANA EXEMPLO DOS SANTOS, brasileira" not in antes_do_anuente


def test_a_outorgada_mulher_e_outorgada(praticado):
    """CC art. 215, § 1º, III: o nome e a qualificação de cada parte. «OUTORGADA» é qualidade da CEP
    (`notas_censec.QUALIFICACAO_PARA_CEP`) — e quem assina a rogo não é outorgante."""
    teor = _teor(praticado, "proc_a_rogo")
    assert "QUALIFIQUE A PARTE" not in teor
    assert EN.tem(teor, "procuradora BEATRIZ EXEMPLO DE SOUZA") or EN.tem(teor, "procurador BEATRIZ")
    assert _marcado_fora_dos_lados(teor, "PAULO EXEMPLO TESTEMUNHA")


def test_o_estado_civil_do_testamento_e_o_da_parte(praticado):
    """CC art. 215, § 1º, III, e art. 1.864, I: o testamento é escrito pelo tabelião conforme as
    declarações do testador — e o estado civil declarado é o da qualificação. Consertado em 03/11/2026
    (item 4): a escolha vem da parte, com o cônjuge e o regime, e o balcão é avisado da diferença."""
    s = _lavrado(praticado, "testamento_casado_marcado_solteiro")
    assert not EN.tem(s.termo, "ser solteiro")
    assert EN.tem(s.termo, "ser casado, sendo seu cônjuge JOANA EXEMPLO DOS SANTOS")
    assert any("vale o da parte" in a for a in s.avisos), s.avisos


def test_o_testamento_nao_deixa_virgula_antes_do_ponto(praticado):
    """O testador solteiro: a cláusula do cônjuge sai, e a vírgula dela junto (item 4)."""
    t = _lavrado(praticado, "testamento_cego").termo
    assert EN.tem(t, "ser solteiro.")
    assert not re.search(r",\s*\.", t)


@_defeito("o advogado entra na lista das partes «todas maiores, capazes e concordes», e de novo no "
          "parágrafo DOS ADVOGADOS (item 5)")
def test_o_advogado_do_inventario_assiste_e_nao_e_parte(praticado):
    """CN-MA arts. 808, § 1º, 819 e 822, § 5º (como o LT02 cita): o advogado assiste as partes."""
    abertura = _abertura(_lavrado(praticado, "inventario_viuva_e_dois_herdeiros").termo)
    assert "CARLOS EXEMPLO ADVOGADO" not in abertura


@_defeito("com um só genitor, a emancipação diz «compareceram como OUTORGANTES» e «Declaram os "
          "OUTORGANTES que são a mãe» (item 6)")
def test_a_emancipacao_concedida_so_pela_mae_fala_no_singular(praticado):
    t = _lavrado(praticado, "emancipacao_so_mae").termo
    assert not EN.tem(t, "OUTORGANTES que são a mãe")


def test_a_emancipacao_confere_os_dezesseis_anos(praticado):
    """CC art. 5º, par. ún., I: a emancipação por concessão dos pais exige dezesseis anos completos.
    Consertado em 03/11/2026 (item 7): o teor não se monta, e o balcão diz por quê."""
    s = praticado("emancipacao_menor_de_16")
    assert s.situacao != "LAVRADO"
    assert any("dezesseis anos completos" in a for a in s.avisos), s.avisos


def test_a_data_por_extenso_tem_acento():
    """O dia 3 e o 23: a data por extenso é a do ato (CC art. 215, § 1º, I) e vai ao livro. Consertado
    em 03/11/2026 (item 8), em `livro_nucleo._UNIDADES`."""
    from datetime import datetime

    import notas_teor as NT
    assert NT.valores_campos_data_lavratura(datetime(2026, 11, 3))["dia_por_extenso"] == "três"
