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


def _abertura(termo: str) -> str:
    """O comparecimento: de «compareceu/compareceram» até o reconhecimento da identidade."""
    m = re.search(r"comparece(?:u|ram)(.*?)(?:todos )?reconhecid", termo, re.S | re.I)
    assert m, "o termo não tem o comparecimento"
    return m.group(1)


def _lado(abertura: str, rotulo: str, ate: str | None = None) -> str:
    """O trecho da abertura que começa em «como <rótulo>» e vai até o próximo «como …» (ou `ate`)."""
    m = re.search(rf"como {rotulo}\b(.*?)(?=(?:;\s*)?e,? como |$)", abertura, re.S | re.I)
    assert m, f"a abertura não tem «como {rotulo}»: {abertura[:300]}"
    trecho = m.group(1)
    return trecho.split(ate)[0] if ate else trecho


# ------------------------------------------------------------------ todo caso vai ao livro

@pytest.mark.parametrize("chave", [c for c in CASOS if c != "proc_a_rogo"])
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


def test_a_procuracao_para_alienar_imovel_arquiva_a_certidao_do_registro(praticado):
    """CC art. 661, § 1º (poderes especiais e expressos) e CN-MA art. 833 (certidão atualizada do RI,
    exigida e arquivada)."""
    t = _lavrado(praticado, "proc_alienar_imovel").termo
    assert EN.tem(t, "661, § 1º", "certidão atualizada do registro de imóveis", "833")


def test_a_divorcianda_que_volta_ao_nome_de_solteira_fica_no_termo(praticado):
    """CN-MA art. 822 (como o LT02 cita): a declaração do nome que cada um passa a usar."""
    t = _lavrado(praticado, "divorcio_com_nome").termo
    assert EN.tem(t, "JOANA EXEMPLO DOS SANTOS voltará a usar o nome")


# ------------------------------------------------------------------ quem comparece, e em que qualidade

@_defeito("o procurador do vendedor sai na abertura como OUTORGADO COMPRADOR: `notas_teor.partes_por_lado` "
          "manda para o segundo lado toda qualificação com «PROCURADOR» (relatorio_notas.md, item 1)")
def test_o_procurador_do_vendedor_nao_vira_comprador(praticado):
    """CN-MA art. 798, VI: a parte representada, com a menção da procuração. O procurador comparece
    pelo outorgante; não é parte do outro lado do negócio."""
    abertura = _abertura(_lavrado(praticado, "cv_por_procurador").termo)
    assert "CARLOS EXEMPLO PROCURADOR" not in _lado(abertura, "OUTORGADO COMPRADOR")


@_defeito("quem representa a pessoa jurídica compradora sai como OUTORGANTE VENDEDOR (item 1)")
def test_o_representante_da_compradora_nao_vira_vendedor(praticado):
    """CN-MA art. 798, V (qualificação da pessoa jurídica, com quem a representa)."""
    abertura = _abertura(_lavrado(praticado, "cv_pj_compradora").termo)
    assert "ANA EXEMPLO SOCIA" not in _lado(abertura, "OUTORGANTE VENDEDOR", ate="como OUTORGADO")


@_defeito("a mãe que representa o donatário menor sai como OUTORGANTE DOADORA, e o termo não diz que o "
          "donatário é menor nem por quem é representado (item 1 e item 2)")
def test_a_mae_que_representa_o_donatario_menor_nao_vira_doadora(praticado):
    """CN-MA art. 798, VII: havendo interesse de menor, a data de nascimento, o assento e por quem está
    representado."""
    abertura = _abertura(_lavrado(praticado, "doacao_a_menor").termo)
    assert "JOANA EXEMPLO DOS SANTOS" not in _lado(abertura, "OUTORGANTE DOADOR", ate="como OUTORGADO")


@_defeito("a mãe que assiste a nubente menor sai entre os NUBENTES (item 1)")
def test_a_assistente_da_nubente_menor_nao_vira_nubente(praticado):
    """CC art. 1.654: o pacto do menor depende da aprovação do representante legal — que assiste, e
    não pactua."""
    abertura = _abertura(_lavrado(praticado, "pacto_nubente_menor").termo)
    assert "JOANA EXEMPLO DOS SANTOS" not in _lado(abertura, "NUBENTES")


@_defeito("o cônjuge que dá a outorga sai como mais um OUTORGANTE VENDEDOR, sem dizer que consente "
          "(item 3)")
def test_o_conjuge_do_vendedor_consente_e_o_termo_o_diz(praticado):
    """CC art. 1.647, I: nenhum dos cônjuges pode, sem autorização do outro (exceto na separação
    absoluta), alienar ou gravar de ônus real os bens imóveis."""
    # Na abertura, e não na linha das assinaturas — lá a qualificação digitada aparece crua («JOANA …,
    # ANUENTE»), o que não é a declaração do consentimento.
    abertura = _abertura(_lavrado(praticado, "cv_casado_com_outorga").termo)
    assert re.search(r"JOANA EXEMPLO DOS SANTOS[^;]{0,400}(anuente|consent|outorga conjugal|outorga uxória)",
                     abertura, re.I)


@_defeito("a qualificação «OUTORGADA», que a CEP aceita, não conta como outorgado: a procuração fica "
          "com «[OUTORGADO(S) — QUALIFIQUE A PARTE NO ATO]» e não se lavra (item 1)")
def test_a_outorgada_mulher_e_outorgada(praticado):
    """CC art. 215, § 1º, III: o nome e a qualificação de cada parte. «OUTORGADA» é qualidade da CEP
    (`notas_censec.QUALIFICACAO_PARA_CEP`)."""
    s = _lavrado(praticado, "proc_a_rogo")
    assert "QUALIFIQUE A PARTE" not in s.termo


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


@_defeito("o emancipando nascido há menos de dezesseis anos é declarado «com dezesseis anos "
          "completos», e a lavratura não confere a data (item 7)")
def test_a_emancipacao_confere_os_dezesseis_anos(praticado):
    """CC art. 5º, par. ún., I: a emancipação por concessão dos pais exige dezesseis anos completos."""
    s = praticado("emancipacao_so_mae")
    assert s.situacao != "LAVRADO"


@_defeito("a data por extenso diz «tres», sem acento (`livro_nucleo._UNIDADES`) (item 8)")
def test_a_data_por_extenso_tem_acento():
    """O dia 3 e o 23: a data por extenso é a do ato (CC art. 215, § 1º, I) e vai ao livro."""
    from datetime import datetime

    import notas_teor as NT
    assert NT.valores_campos_data_lavratura(datetime(2026, 11, 3))["dia_por_extenso"] == "três"
