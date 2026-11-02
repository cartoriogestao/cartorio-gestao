"""O ensaio de atos do Registro Civil: cada ato pelas rotas de verdade, e o documento conferido com a lei.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída. […] Sempre que tem um ato novo, que ainda não fizemos no
sistema, encontramos muitos problemas de adequação do sistema e legal. Queria antecipar esses
problemas e processar antes de encontrar na prática.»

O QUE ESTE TESTE FAZ
    Pratica os casos de `ensaio_de_atos_rcpn.casos` (o ato e a variante que a lei distingue) sobre a
    casa de ensaio, com a trava ligada, pela tela de lavrar, de lançar à margem e de emitir certidão.
    Depois confere cada documento que saiu — o termo, a folha do livro, o breve relato, o papel e o
    inteiro teor — contra o requisito da norma, que vai citado em cada teste.

    A leitura crítica que não cabe numa conferência determinística (redação, padrão da casa,
    conflito entre fontes) está em `docs/ensaio_de_atos/relatorio_rcpn.md`, e o inventário dos atos em
    `docs/ensaio_de_atos/inventario_rcpn.md`.

OS DEFEITOS FICAM À VISTA
    A asserção é a da lei, e não a do que o sistema faz hoje. O defeito aberto e a decisão que é do
    oficial ficam em `xfail(strict=True)`, com o motivo; o que já tem conserto num PR aberto fica em
    `xfail(strict=False)`, que passa antes e depois de ele entrar — e sai daqui quando entrar.

PARA LER OS DOCUMENTOS: `CG_ENSAIO_SAIDA=1` grava cada caso, com tudo o que saiu, em
`<pasta temporária>/ensaio_de_atos_rcpn/`.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

import ensaio_de_atos_rcpn as EA
import layout_casa as LC
import layout_ensaio as E

pytestmark = pytest.mark.lento

#: Conserto em PR aberto: o xfail sai quando ele entrar. Os do ensaio que já entraram — #225 (o
#: casamento que o Código Civil não admite), #226 (quem nasceu depois do fato) e #227 (o estrangeiro) —
#: são conferência comum abaixo.
PR_ABERTO: dict[str, str] = {}


def _pr(chave: str):
    return pytest.mark.xfail(strict=False, reason=f"DEFEITO com conserto em {PR_ABERTO[chave]}")


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _decisao(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DECISÃO DO OFICIAL: {motivo}")


# ------------------------------------------------------------------ a casa e a prática

@pytest.fixture(scope="module")
def casa_rcpn(cg_app, _cg_boot, tmp_path_factory):
    """A casa de ensaio só com a base (o sandbox): os atos do ensaio são lavrados aqui mesmo."""
    import caixa_aviso as CA
    fim = CA.FIM_PADRAO
    CA.FIM_PADRAO = "23:59"
    casa = LC.montar_casa(cg_app, _cg_boot, tmp_path_factory.getbasetemp(), areas=[])
    EA.preparar(casa)
    yield casa
    E.desligar_trava()
    CA.FIM_PADRAO = fim


@pytest.fixture(scope="module")
def saidas(casa_rcpn) -> dict[str, EA.Saida]:
    feitas = {c.chave: EA.praticar(casa_rcpn, c) for c in EA.casos(casa_rcpn)}
    if os.environ.get("CG_ENSAIO_SAIDA"):
        pasta = Path(tempfile.gettempdir()) / "ensaio_de_atos_rcpn"
        pasta.mkdir(exist_ok=True)
        for chave, s in feitas.items():
            (pasta / f"{chave}.txt").write_text(
                f"# {s.caso.titulo}\nassento {s.assento_id}\navisos: {s.avisos}\n\n## TERMO\n{s.termo}\n\n"
                f"## FOLHA DO LIVRO\n{s.folha}\n\n## BREVE RELATO\n{s.certidao}\n\n## PAPEL\n{s.papel}\n\n"
                f"## INTEIRO TEOR\n{s.inteiro_teor}\n", encoding="utf-8")
        print(f"\nos documentos do ensaio estão em {pasta}")
    return feitas


def _s(saidas, chave: str) -> EA.Saida:
    s = saidas[chave]
    assert s.assento_id, f"{chave} não foi lavrado: {s.avisos}"
    return s


#: Os casos que a tela tem de RECUSAR, com o recado que o balcão lê, e por quê.
RECUSADOS = {
    "cas_universal_sem_pacto": ("pacto antenupcial", "CC art. 1.640, parágrafo único, e art. 1.653"),
    "cas_menor_15": ("1.520", "CC art. 1.520"),
    # A GRAFIA QUE O IBGE NÃO CONFIRMA já trava na conferência das centrais (a CRC exige o código do
    # município). O «ND» calado do relatório (item 9) era só sem o cadastro carregado: ali, desde
    # 02/11/2026, a lavratura avisa (`rc_assento.aviso_da_naturalidade`).
    "nasc_naturalidade_fora_do_ibge": ("a CRC exige o código do município", "LRP art. 54, § 4º; CNN art. 474"),
}
#: Os que a lei permite e a tela ainda recusa.
RECUSA_INDEVIDA = {
    "obito_desconhecido_ignora": _decisao(
        "o balcão não consegue declarar que ignora se o falecido deixou bens: a trava da CRC exige S ou N "
        "(«sem opção de ignorado»), e o CN-MA art. 255, § 1º, manda escrever que o declarante ignorava"),
}


def _casos_que_lavram():
    return [pytest.param(c, marks=RECUSA_INDEVIDA[c]) if c in RECUSA_INDEVIDA else c
            for c in EA.CHAVES if c not in RECUSADOS]


@pytest.mark.parametrize("chave", _casos_que_lavram())
def test_o_ato_se_pratica_pela_tela_do_registro_a_certidao(saidas, chave):
    """Do formulário de lavrar ao breve relato e ao inteiro teor, sem recusa. O aviso (o maior de 70, o
    nubente de 16 anos) não é recusa: fica em `avisos`, e o ato sai."""
    s = saidas[chave]
    assert s.assento_id and not [a for a in s.avisos if "recusad" in a], s.avisos
    assert s.termo and s.certidao and s.inteiro_teor and "não saiu" not in s.papel


@pytest.mark.parametrize("chave", list(RECUSADOS))
def test_o_que_a_lei_nao_admite_a_tela_recusa(saidas, chave):
    s = saidas[chave]
    recado, _norma = RECUSADOS[chave]
    assert s.assento_id is None and any(recado in a for a in s.avisos), s.avisos


# ------------------------------------------------------------------ o que vale para todo documento

def _documentos(s: EA.Saida) -> dict[str, str]:
    return {"termo": s.termo, "breve relato": s.certidao, "papel": s.papel, "inteiro teor": s.inteiro_teor}


@pytest.mark.parametrize("chave", [c for c in EA.CHAVES if c not in RECUSADOS and c not in RECUSA_INDEVIDA])
def test_nenhum_documento_sai_com_claro_marcador_ou_none(saidas, chave):
    """O livro não aceita rasura (LRP art. 39): «None», marcador de modelo ou vírgula sem nada entre elas
    num papel assinado não se conserta depois."""
    for nome, texto in _documentos(_s(saidas, chave)).items():
        assert not re.search(r"\bNone\b|\bnull\b|\{\{|\}\}|\{[a-z_]+\}", texto), f"{nome}: {texto[:400]}"
        assert not re.search(r",\s*,|\(\s*\)", texto), f"{nome} tem claro: {texto[:400]}"


@pytest.mark.parametrize("chave", [c for c in EA.CHAVES if c not in RECUSADOS and c not in RECUSA_INDEVIDA])
def test_o_termo_traz_a_data_do_ato_por_extenso_com_o_algarismo(saidas, chave):
    """LRP art. 35 e CN-MA art. 212, II (por extenso, com o algarismo entre parênteses — a forma da
    casa, `ESTILO_DATA_TERMO`)."""
    assert re.search(r"\b(?:Aos|Em) [a-zç ]+ \(\d{2}\) de [a-zç]+ de [a-z ]+ \(\d{4}\)", _s(saidas, chave).termo)


@pytest.mark.parametrize("chave", [c for c in EA.CHAVES if c not in RECUSADOS and c not in RECUSA_INDEVIDA])
def test_o_papel_da_certidao_tem_serventia_selo_consulta_e_fe(saidas, chave):
    """CNN arts. 472 e 473 (os modelos de certidão) e CN-MA arts. 130 a 132 (o selo no corpo do ato, com a
    consulta): o CNS, o selo com o endereço de consulta e o fecho de fé."""
    papel = _s(saidas, chave).papel
    for pedaco in ("CNS nº 000000", "Selo:", "https://selo.tjma.jus.br/#/resumo/", "Dou fé"):
        assert pedaco in papel, f"o papel não traz «{pedaco}»: {papel[-600:]}"


@pytest.mark.parametrize("chave", [c for c in EA.CHAVES if c not in RECUSADOS and c not in RECUSA_INDEVIDA])
def test_a_matricula_tem_32_digitos_e_o_digito_fecha(saidas, chave):
    """CNN art. 473: a matrícula de 32 dígitos, com o dígito verificador, em toda certidão."""
    import rc_matricula
    s = _s(saidas, chave)
    achada = re.search(r"MATRÍCULA N[º°] (\d{32})", s.certidao)
    assert achada, s.certidao[:300]
    assert rc_matricula.confere(achada.group(1))["ok"], achada.group(1)


@pytest.mark.parametrize("chave", [c for c in EA.CHAVES if c not in RECUSADOS and c not in RECUSA_INDEVIDA])
def test_o_inteiro_teor_reproduz_o_termo_entre_aspas(saidas, chave):
    """LRP art. 19, § 1º: o inteiro teor reproduz o assento; aqui, o termo que a casa lavrou."""
    s = _s(saidas, chave)
    entre_aspas = re.search(r"«(.*)»", s.inteiro_teor, re.S)
    assert entre_aspas and s.termo[:200] in entre_aspas.group(1), s.inteiro_teor[:400]


# ------------------------------------------------------------------ nascimento

NASCIMENTOS = [c for c in EA.CHAVES if c.startswith("nasc_") and c not in RECUSA_INDEVIDA
               and c != "nasc_naturalidade_fora_do_ibge"] + [
    "av_nome", "an_obito_no_nascimento", "ret_erro_grafia"]


@pytest.mark.parametrize("chave", NASCIMENTOS)
def test_a_certidao_de_nascimento_traz_a_naturalidade_que_o_balcao_declarou(saidas, chave):
    """LRP art. 54, 11, e § 4º; CNN art. 474: a naturalidade é campo da certidão."""
    s = _s(saidas, chave)
    assert "NATURALIDADE Cidade Exemplo/MA" in s.certidao, s.certidao[:600]


@pytest.mark.parametrize("chave, trecho", [
    ("nasc_padrao", "Lido e achado conforme, a declarante assina."),
    ("nasc_tardio", "a identidade da registrada"),
    ("cas_divorciado", "tendo sido casada com JOSE EXEMPLO ANTERIOR"),
])
def test_o_termo_nao_escreve_o_a_de_quem_tem_sexo_conhecido(saidas, chave, trecho):
    """Ensaio de atos, item 11 (02/11/2026): o «(a)» da peça concorda com a pessoa de quem ela fala."""
    t = _s(saidas, chave).termo
    assert trecho in t and "(a)" not in t, t


def test_o_breve_relato_escreve_o_cpf_com_os_pontos(saidas):
    """Ensaio de atos, item 11: «CPF 00000000191» no teor, «000.000.001-91» no papel."""
    assert "CPF 000.000.001-91" in _s(saidas, "nasc_padrao").certidao


CASADOS = ["nasc_padrao", "nasc_gemeo", "nasc_domicilio", "nasc_tardio", "nasc_pais_estrangeiros",
           "nasc_declarante_avo"]


@pytest.mark.parametrize("chave", CASADOS)
def test_o_registro_de_nascimento_nao_fala_do_casamento_dos_pais(saidas, chave):
    """Lei 8.560/1992, art. 5º (no registro) e art. 6º, § 1º (na certidão, que o inteiro teor reproduz) —
    decisão do oficial de 02/11/2026."""
    s = _s(saidas, chave)
    for nome in ("termo", "inteiro teor"):
        assert "casados entre si" not in _documentos(s)[nome], nome


@pytest.mark.parametrize("chave", ["nasc_padrao", "nasc_gemeo", "nasc_tardio", "nasc_declarante_avo"])
def test_o_termo_da_registrada_diz_sendo_filha_de(saidas, chave):
    """Decisão do oficial, 02/11/2026 (ensaio de atos, item 10): o termo concorda com o sexo, como a prévia,
    no livro e no inteiro teor que o reproduz."""
    s = _s(saidas, chave)
    for nome in ("termo", "inteiro teor"):
        assert "sendo filha de" in _documentos(s)[nome] and "sendo filho de" not in _documentos(s)[nome], nome


def test_o_termo_do_registrado_continua_sendo_filho_de(saidas):
    assert "sendo filho de" in _s(saidas, "natimorto_com_nome").termo


def test_o_termo_do_gemeo_declara_a_ordem_de_nascimento(saidas):
    """LRP art. 54, 3º, e art. 63; CN-MA art. 234. Consertado no ensaio de atos (02/11/2026, item 6): a
    tela de lavrar pergunta a ordem, e o termo de cada gêmeo a declara."""
    assert "gêmea, a 1ª na ordem de nascimento" in _s(saidas, "nasc_gemeo").termo


def test_o_termo_do_parto_em_domicilio_qualifica_as_duas_testemunhas(saidas):
    """LRP art. 54, 9º; CN-MA art. 233, IX."""
    t = _s(saidas, "nasc_domicilio").termo
    assert "CARLA EXEMPLO TESTEMUNHA" in t and "JOAO EXEMPLO TESTEMUNHA" in t and "que também o assinam" in t


def test_o_termo_tardio_diz_o_fundamento_e_as_testemunhas(saidas):
    """LRP art. 46; CN-MA art. 249, I e II."""
    t = _s(saidas, "nasc_tardio").termo
    assert "fora do prazo legal" in t and "art. 46 da Lei nº 6.015/1973" in t
    assert "atestaram, sob as penas da lei, a identidade" in t


def test_a_alegacao_de_paternidade_nao_entra_no_termo(saidas):
    """Lei 8.560/1992, art. 2º: o suposto pai vai ao juiz, e não ao assento."""
    assert "JOSE EXEMPLO SUPOSTO" not in _s(saidas, "nasc_alegacao_paternidade").termo


def test_o_pai_estrangeiro_sai_com_o_pais_e_o_passaporte(saidas):
    t = _s(saidas, "nasc_pais_estrangeiros").termo
    assert "Lisboa, Portugal" in t and "passaporte n.º CB000000" in t


# ------------------------------------------------------------------ à margem do nascimento

@_defeito("a averbação de reconhecimento de paternidade não atualiza a certidão: o breve relato sai com "
          "«FILIAÇÃO: IGNORADO», os avós paternos «ND» e o nome antigo")
def test_depois_do_reconhecimento_a_certidao_traz_o_pai_e_o_nome_novo(saidas):
    c = _s(saidas, "av_paternidade").certidao
    assert "MARIO EXEMPLO DOS SANTOS" in c.split("OBSERVAÇÕES")[0] and "IGNORADO" not in c
    assert "NOME: ANA EXEMPLO DOS SANTOS" in c


@_defeito("o breve relato transcreve a averbação de reconhecimento («reconhece como sua filha»): a Lei "
          "8.560/1992, art. 6º, veda na certidão de nascimento indício da natureza da filiação, e o § 2º "
          "reserva o inteiro teor à autorização judicial — que a tela não pede")
def test_a_certidao_breve_nao_revela_o_reconhecimento(saidas):
    s = _s(saidas, "av_paternidade")
    assert "reconhece" not in s.certidao.lower() and "reconhece" not in s.papel.lower()


@pytest.mark.parametrize("chave", ["av_nome", "av_paternidade", "ret_erro_grafia", "an_obito_no_nascimento",
                                   "av_divorcio"])
def test_a_certidao_menciona_o_que_foi_lancado_a_margem(saidas, chave):
    """LRP art. 21 (a alteração posterior se menciona obrigatoriamente); CN-MA art. 386."""
    s = _s(saidas, chave)
    marca = {"av_nome": "ANNA", "av_paternidade": "MARIO EXEMPLO DOS SANTOS", "ret_erro_grafia": "BEATRIS",
             "an_obito_no_nascimento": "faleceu", "av_divorcio": "divórcio"}[chave]
    assert marca in s.certidao.split("OBSERVAÇÕES")[-1] and marca in s.papel


# ------------------------------------------------------------------ natimorto

def test_a_certidao_de_natimorto_traz_o_sexo_do_termo(saidas):
    """LRP art. 53, § 1º, e art. 54, 2º."""
    s = _s(saidas, "natimorto_com_nome")
    assert "do sexo Masculino" in s.termo
    assert "SEXO MASCULINO" in s.certidao and "MASCULINO" in s.papel


@pytest.mark.parametrize("chave", ["natimorto", "natimorto_com_nome"])
def test_o_breve_relato_do_natimorto_e_dele(saidas, chave):
    """Decisão do oficial, 02/11/2026 (ensaio de atos, item 7): o breve relato do natimorto não pergunta
    estado civil, profissão nem testamento de quem nasceu morto, e diz o parto, a causa e o sepultamento."""
    c = _s(saidas, chave).certidao
    assert "TESTAMENTO" not in c and "ESTADO CIVIL" not in c and "PROFISSÃO" not in c, c
    assert "DATA DO PARTO POR EXTENSO" in c and "anóxia intrauterina" in c
    assert "SEPULTAMENTO OU CREMAÇÃO Cemitério Municipal de Cidade Exemplo" in c


def test_o_natimorto_sem_nome_se_lavra_sem_dizer_que_recebeu_nome(saidas):
    """LRP art. 53, § 3º (o nome é facultativo) — decisão do oficial, 02/11/2026. O assento se acha como a
    casa o indexa, «NATIMORTO DE <a mãe>», e o termo não diz que ele «recebeu o nome de» nada."""
    s = _s(saidas, "natimorto")
    assert "recebeu o nome" not in s.termo and "nasceu morta uma criança do sexo Masculino" in s.termo
    assert "NOME: NATIMORTO DE BEATRIZ EXEMPLO DE SOUZA" in s.certidao


# ------------------------------------------------------------------ óbito

OBITOS = [c for c in EA.CHAVES if c.startswith("obito_") and c not in RECUSA_INDEVIDA] + ["cert_gratuita"]


@pytest.mark.parametrize("chave", OBITOS)
def test_o_termo_de_obito_diz_eleitor_bens_e_filhos(saidas, chave):
    """LRP art. 80, 7º, 10º e 11º; CN-MA art. 255, V, VIII e XI."""
    t = _s(saidas, chave).termo
    assert re.search(r"\b(Era|Não era) eleitor", t) and re.search(r"(Deixou|Não deixou) bens", t)
    assert re.search(r"Deixou os filhos|Não deixou filhos", t)


@pytest.mark.parametrize("chave, frase", [
    ("obito_padrao", "Deixou testamento conhecido: lavrado no Tabelionato de Cidade Exemplo."),
    ("obito_sem_bens", "Não deixou testamento conhecido."),
    ("obito_bebe", "Não deixou testamento conhecido."),
    ("obito_crianca", "o declarante ignorava: deixou testamento conhecido"),
])
def test_o_termo_de_obito_diz_se_havia_testamento(saidas, chave, frase):
    """LRP art. 80, 6º; CN-MA art. 255, VII e § 1º. O testamento é pergunta (decisão do oficial,
    02/11/2026; item 4): sim, não, ou o declarante ignorava."""
    t = _s(saidas, chave).termo
    assert frase in t, t
    assert not re.search(r"testamento conhecido: (NAO|N[ÃA]O)\b", t, re.I)


@pytest.mark.parametrize("chave, valor", [("obito_padrao", "lavrado no Tabelionato"), ("obito_sem_bens", "NÃO")])
def test_a_certidao_de_obito_diz_o_testamento_que_o_termo_declara(saidas, chave, valor):
    assert re.search(rf"TESTAMENTO CONHECIDO {valor}", _s(saidas, chave).certidao)


def test_a_idade_do_bebe_nao_sai_em_zero_anos(saidas):
    """LRP art. 80, 3º (a idade)."""
    t = _s(saidas, "obito_bebe").termo
    assert "com menos de um ano de idade" in t and "0 anos" not in t


def test_a_morte_violenta_se_declara_violenta(saidas):
    """LRP art. 80, 8º; CN-MA art. 255, IX."""
    assert "A morte foi violenta" in _s(saidas, "obito_violento").termo


@_decisao("o óbito de pessoa não identificada afirma «Não deixou filhos. Não deixou bens. Não era eleitor» "
          "de quem ninguém conhece: o CN-MA art. 255, § 1º, manda declarar que o declarante ignorava, mas a "
          "CRC exige S ou N nesses campos (a trava da CRC recusa o branco). E a tela não tem os sinais do LRP "
          "art. 81 (estatura, sinais, idade presumida, vestuário)")
def test_o_obito_do_desconhecido_nao_afirma_o_que_ninguem_sabe(saidas):
    t = _s(saidas, "obito_desconhecido").termo
    assert "Não deixou bens" not in t and re.search(r"estatura|idade presumida|vestuário", t)


# ------------------------------------------------------------------ casamento

CASAMENTOS = [c for c in EA.CHAVES if c.startswith("cas_") and c not in RECUSADOS] + ["av_divorcio"]


@pytest.mark.parametrize("chave", ["cas_universal_pacto", "cas_separacao_pacto", "cas_participacao_pacto"])
def test_o_termo_do_regime_convencional_traz_o_pacto(saidas, chave):
    """LRP art. 70, 7º; CC art. 1.536, VII: a data e a serventia do pacto antenupcial."""
    t = _s(saidas, chave).termo
    assert "pacto antenupcial lavrada em 01/08/2026" in t and "Tabelionato de Notas de Cidade Exemplo" in t


@pytest.mark.parametrize("chave", [c for c in CASAMENTOS if c != "cas_estrangeiro"])
def test_o_breve_relato_do_casamento_traz_o_cpf_dos_conjuges(saidas, chave):
    """CNN art. 477 (o CPF na certidão). Consertado no ensaio de atos (02/11/2026): o casamento lavrado aqui
    saía «CPF SEM INFORMAÇÃO» — a certidão lia só o blob do acervo."""
    cabeca = _s(saidas, chave).certidao.split("MATRÍCULA")[0]
    assert re.search(r"CPF \d{3}\.\d{3}\.\d{3}-\d{2} e \d{3}\.\d{3}\.\d{3}-\d{2}", cabeca), cabeca


def test_o_nubente_de_passaporte_fica_sem_informacao_do_lado_dele(saidas):
    """Sem o CPF de um, o lado dele diz «SEM INFORMAÇÃO»: o CPF que sobra não pode parecer o do primeiro nome."""
    cabeca = _s(saidas, "cas_estrangeiro").certidao.split("MATRÍCULA")[0]
    assert "CPF SEM INFORMAÇÃO e 000.000.050-70" in cabeca, cabeca


@pytest.mark.parametrize("chave", CASAMENTOS)
def test_o_termo_de_casamento_nomeia_o_presidente_do_ato(saidas, chave):
    """CC art. 1.536, caput; LRP art. 70, caput — decisão do oficial de 02/11/2026 (item 5): o termo diz
    quem presidiu o ato, e que ele assina."""
    t = _s(saidas, chave).termo
    assert "foram declarados casados" in t and "por PAULO EXEMPLO JUIZ DE PAZ, Juiz de Paz," in t, t
    assert "assinam comigo, que escrevi, o presidente do ato, os nubentes e as testemunhas" in t, t


def test_o_nubente_estrangeiro_sai_com_o_pais_e_o_passaporte(saidas):
    t = _s(saidas, "cas_estrangeiro").termo
    assert "Roma, Itália" in t and "passaporte n.º YA0000000" in t


def test_o_nubente_divorciado_traz_o_conjuge_anterior_e_a_dissolucao(saidas):
    """LRP art. 70, 3º; CC art. 1.536, III."""
    t = _s(saidas, "cas_divorciado").termo
    assert "JOSE EXEMPLO ANTERIOR" in t and "dissolvido em 10/05/2022" in t


# ------------------------------------------------------------------ Livro E

@pytest.mark.parametrize("chave, pedacos", [
    ("e_emancipacao_escritura", ("escritura pública", "livro 10, folha 20", "Tabelionato de Notas")),
    ("e_emancipacao_sentenca", ("sentença", "0000001-00.2026.8.10.0000")),
    ("e_interdicao", ("curadora CARLA EXEMPLO CURADORA", "limites da curatela", "transitada em julgado")),
    ("e_ausencia", ("CARLA EXEMPLO CURADORA",)),
    ("e_tutela", ("JOAO EXEMPLO TUTOR",)),
    ("e_uniao_estavel", ("MARIO EXEMPLO DOS SANTOS", "BEATRIZ EXEMPLO DE SOUZA", "comunhão parcial",
                         "dez (10) de janeiro de dois mil e dezoito")),
    ("e_opcao_nacionalidade", ("Vara Federal",)),
])
def test_o_termo_do_livro_e_traz_o_titulo_e_quem_ele_nomeia(saidas, chave, pedacos):
    """LRP arts. 90 (emancipação), 92 (interdição), 94 (ausência), 94-A (união estável) e 32, § 4º (opção)."""
    t = _s(saidas, chave).termo
    faltam = [p for p in pedacos if p not in t]
    assert not faltam, f"faltam {faltam}: {t}"


def test_a_opcao_de_nacionalidade_diz_o_pais_onde_nasceu(saidas):
    """CF art. 12, I, c; LRP art. 32, § 4º: quem opta nasceu no estrangeiro."""
    assert "Portugal" in _s(saidas, "e_opcao_nacionalidade").termo
