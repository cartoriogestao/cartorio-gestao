"""O selo do casamento, e a folha de segurança que não se gasta à toa.

O QUE ESTES TESTES GUARDAM, E POR QUE ELES EXISTEM
    Em 28/08/2026 o oficial decidiu que o casamento leva **UM SELO SÓ**:
    *«o selo é emitido uma vez apenas; ele é reaproveitado apenas no assento,
    mas já foi emitido na habilitação»*.

    Eu tinha entendido a resposta anterior dele como duas COMPRAS e cheguei a
    construir um segundo envelope. Não eram duas: é um selo que APARECE nos
    dois papéis — e a tabela de custas dizia isso o tempo todo, com o item
    `14.1.1` cobrindo «habilitação **e registro**».

    Mas a conferência do contrato, feita para montar aquele segundo selo, achou
    três coisas que ninguém tinha medido — e as três valem por si:

      1. A **conversão de união estável** tem caminho e schema próprios
         (`DadosSeloHabilitacaoCasamentoConversao`), com `numeroProcesso`
         **obrigatório** — e o processo que ele pede é o da união estável, e
         não o da habilitação. As três iam pelo mesmo endpoint.

      2. O registro de **proclamas** sela pelo caminho da habilitação, que pede
         `tipoCasamento` — campo que o envelope comum do civil não tem. Mandado
         por ali, o aparelho recusaria.

      3. `papelMoeda` está em **19 dos 100** caminhos do civil, e o sistema
         gastava folha de segurança em **todos**. Averbação, anotação,
         retificação e certidão negativa consumiam papel que ninguém imprime —
         e, com o estoque vazio, eram lavradas SEM SELO por falta de uma folha
         que elas não usam.

    Nenhuma das três apareceria em teste sobre banco vazio nem em releitura de
    código: as três só se veem comparando o que o sistema monta com o que o
    contrato pede.

O CONTRATO SE LÊ, E NÃO SE TRANSCREVE
    `_campos_do_contrato` abre o `selador-doc` e extrai os campos de verdade.
    Um teste que repetisse aqui a lista provaria que eu copiei certo, e não que
    o envelope obedece ao contrato — é a lição do comentário que afirma
    medição sem ter medido.
"""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS            # noqa: E402
import selador as S                # noqa: E402

DOC = Path(r"C:\ProgramData\CartorioGestao\arquivos\eoficio\Selo Eletrônico\selador-doc\civil\index.html")

pytestmark = pytest.mark.skipif(
    not DOC.exists(), reason="o contrato do selador não está nesta máquina")


def _plano() -> str:
    texto = DOC.read_text(encoding="utf-8", errors="replace")
    return html.unescape(re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", texto)))


def _blocos() -> dict[str, str]:
    """Cada schema do contrato e o seu corpo."""
    plano = _plano()
    achados = {}
    for m in re.finditer(r"([A-Za-z0-9]+) Name Description Schema ", plano):
        achados[m.group(1)] = m.start()
    ordem = sorted(achados.items(), key=lambda par: par[1])
    corpo = {}
    for i, (nome, inicio) in enumerate(ordem):
        fim = ordem[i + 1][1] if i + 1 < len(ordem) else len(plano)
        corpo[nome] = plano[inicio:fim]
    return corpo


def _campos_do_contrato(schema: str) -> dict[str, str]:
    """Os campos de um schema, com o «required/optional» de cada."""
    corpo = _blocos().get(schema)
    assert corpo, f"não achei {schema} no contrato"
    return {m.group(1): m.group(2)
            for m in re.finditer(r"(\w+) (required|optional) ", corpo)}


def _conferir(schema: str, envelope: dict) -> None:
    campos = _campos_do_contrato(schema)
    sobrando = set(envelope) - set(campos)
    assert not sobrando, f"{schema}: campos que o contrato não tem: {sobrando}"
    obrigatorios = {n for n, q in campos.items() if q == "required"}
    faltando = obrigatorios - set(envelope)
    assert not faltando, f"{schema}: faltam obrigatórios: {faltando}"


# ------------------------------------------ o envelope contra o contrato


def test_o_envelope_da_habilitacao_cabe_no_schema_do_contrato():
    _conferir("DadosSeloHabilitacaoCasamento", AS.envelope_da_habilitacao(
        escrevente="MARIO", versao_tabela="0120260101", tipo="CIVIL",
        numero_processo="12/2026",
        nubente1={"nome": "FULANO", "documento": "000.000.010-82"},
        nubente2={"nome": "BELTRANA"}))


def test_o_envelope_da_conversao_cabe_no_schema_dela():
    _conferir("DadosSeloHabilitacaoCasamentoConversao",
              AS.envelope_da_habilitacao(
                  escrevente="MARIO", versao_tabela="0120260101",
                  tipo="CONVERSAO", numero_processo="ESCRITURA 123",
                  nubente1={"nome": "FULANO"}, nubente2={"nome": "BELTRANA"}))


def test_o_assento_so_compra_selo_quando_a_habilitacao_e_de_fora():
    """A regra de dinheiro, e ela é exclusiva por construção.

    O oficial decidiu em 28/08/2026 que o casamento leva UM selo, comprado na
    habilitação — e que, quando a habilitação é de OUTRA serventia (item 14.1.6
    da tabela), o assento **compra selo próprio, citando o de lá**.

    O que separa os dois caminhos é uma coisa que o escrevente RESPONDE na
    tela — `habilitacao_serventia` —, e nunca uma dedução do sistema. Deduzir
    aqui seria arriscar cobrar do casal duas vezes.
    """
    codigo = (RAIZ / "atribuicoes_web.py").read_text(encoding="utf-8")
    # a compra só acontece dentro da guarda do «de fora»
    i = codigo.find("AS.envelope_do_casamento(")
    assert i > 0, "o envelope do assento sumiu"
    antes = codigo[max(0, i - 900):i]
    assert "de_fora" in antes, (
        "a compra do selo do assento não está guardada pela habilitação de "
        "fora — e sem essa guarda o casal paga duas vezes")
    # e o caminho do reaproveitamento diz que NÃO compra
    assert "O casamento não compra selo" in codigo


def test_o_envelope_de_fora_cita_o_selo_e_o_cartorio_de_la():
    """Os dois campos existem no contrato exatamente para este caso."""
    e = AS.envelope_do_casamento(
        escrevente="MARIO", versao_tabela="0120260101", tipo="CIVIL",
        livro="B-4", folha="39", termo="40", papel="725061",
        selo_da_habilitacao="DELA0000000000000000000AAAA",
        local_da_habilitacao="CARTÓRIO DE IMPERATRIZ/MA",
        nubente1={"nome": "FULANO"})
    assert e["seloReferencia"] == "DELA0000000000000000000AAAA"
    assert e["localRealizacaoHabilitacao"] == "CARTÓRIO DE IMPERATRIZ/MA"
    _conferir("DadosSeloCasamento", e)


def test_o_assento_de_fora_nao_sela_sem_folha_de_seguranca():
    """`papelMoeda` é **required** em `DadosSeloCasamento` — ele imprime a
    primeira certidão, e por isso este é um dos 19 caminhos que gastam folha."""
    with pytest.raises(AS.AtoError, match="folha de segurança"):
        AS.envelope_do_casamento(
            escrevente="MARIO", versao_tabela="0120260101", tipo="CIVIL",
            livro="B-4", folha="39", termo="40", papel=None)
    assert AS.gasta_folha_de_seguranca("/selo/civil/casamento")

def test_os_tres_tipos_de_casamento_sao_os_do_contrato():
    """0 civil, 1 religioso com efeito civil, 2 conversão."""
    for tipo, esperado in (("CIVIL", 0), ("RELIGIOSO", 1), ("CONVERSAO", 2)):
        e = AS.envelope_da_habilitacao(
            escrevente="MARIO", versao_tabela="0120260101", tipo=tipo,
            numero_processo="12/2026", nubente1={"nome": "FULANO"})
        assert e["tipoCasamento"] == esperado


# -------------------------------------------------- a conversão de união


def test_a_conversao_sela_por_caminho_proprio():
    assert AS.caminho_do_ato("hc_habilitacoes", "HABILITACAO",
                             especie="CONVERSAO") == (
        "/selo/civil/casamento/conversao")
    for tipo in ("CIVIL", "RELIGIOSO"):
        assert AS.caminho_do_ato("hc_habilitacoes", "HABILITACAO",
                                 especie=tipo) == (
            "/selo/civil/casamento/habilitacao")


def test_os_caminhos_da_habilitacao_existem_no_contrato():
    for caminho in AS.CAMINHO_DA_HABILITACAO.values():
        assert caminho in S.ENDPOINTS


def test_a_conversao_exige_o_processo_da_uniao_estavel():
    """O contrato o pede com todas as letras, e ele não é o desta habilitação."""
    with pytest.raises(AS.AtoError, match="união estável"):
        AS.envelope_da_habilitacao(
            escrevente="MARIO", versao_tabela="0120260101", tipo="CONVERSAO",
            nubente1={"nome": "FULANO"}, nubente2={"nome": "BELTRANA"})
    e = AS.envelope_da_habilitacao(
        escrevente="MARIO", versao_tabela="0120260101", tipo="CONVERSAO",
        numero_processo="ESCRITURA 123, LIVRO 40, FL. 12",
        nubente1={"nome": "FULANO"})
    assert e["numeroProcesso"] == "ESCRITURA 123, LIVRO 40, FL. 12"


def test_a_habilitacao_comum_nao_exige_processo():
    """Só a conversão o tem como obrigatório — nas outras ele é `optional`."""
    e = AS.envelope_da_habilitacao(
        escrevente="MARIO", versao_tabela="0120260101", tipo="CIVIL",
        nubente1={"nome": "FULANO"})
    assert "numeroProcesso" not in e


# ------------------------------------------- a folha que não se gasta à toa


def test_a_folha_se_gasta_exatamente_onde_o_contrato_pede():
    """Lido do contrato, e não transcrito: são 19 dos 100 caminhos do civil."""
    corpo = _blocos()
    do_contrato = {
        caminho for caminho, e in S.ENDPOINTS.items()
        if e.get("atribuicao") == "civil"
        and "papelMoeda" in corpo.get(e.get("schema", ""), "")}
    assert do_contrato == set(AS.CAMINHOS_QUE_GASTAM_FOLHA)
    assert len(do_contrato) == 19


def test_averbacao_e_anotacao_nao_gastam_folha():
    """Era o defeito: elas gastavam, e com o estoque vazio saíam sem selo."""
    for tipo in ("AVERBACAO", "ANOTACAO", "RETIFICACAO"):
        caminho = AS.caminho_do_civil("NASCIMENTO", tipo)
        assert caminho, tipo
        assert not AS.gasta_folha_de_seguranca(caminho), caminho


def test_o_registro_e_a_segunda_via_gastam_folha():
    """Estes imprimem certidão — e é por isso que o contrato pede o papel."""
    assert AS.gasta_folha_de_seguranca(
        AS.caminho_do_civil("NASCIMENTO", "REGISTRO"))
    assert AS.gasta_folha_de_seguranca(
        AS.caminho_do_civil("CASAMENTO", "REGISTRO"))
    assert AS.gasta_folha_de_seguranca("/selo/civil/obito/segunda-via")


def test_a_habilitacao_e_os_proclamas_nao_gastam_folha():
    """Nenhum dos dois imprime certidão, e o contrato não tem o campo."""
    for caminho in AS.CAMINHO_DA_HABILITACAO.values():
        assert not AS.gasta_folha_de_seguranca(caminho)
    assert not AS.gasta_folha_de_seguranca(
        AS.caminho_do_civil("PROCLAMAS", "REGISTRO"))
