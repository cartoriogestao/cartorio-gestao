"""O MOLDE DA CERTIDÃO DE ÓBITO — igual ao Anexo VI do Provimento CNJ
182/2024, e não mais o derivado do de nascimento.

    «pode seguir como recomendado» · «seguir»    — o oficial, 10/09/2026

COMO ELE FOI ACHADO
    **Ao CONFERIR o trabalho do dia, e não ao construí-lo.** O oficial pediu
    para eu verificar se estava tudo certo; renderizei o molde de óbito só
    para ver se eu não o tinha quebrado ao mexer no rodapé, e ele **nunca
    recebeu nada do que foi consertado nos outros dois em 09/09** — o rodapé
    velho com os seis campos que ele mandou tirar, e **20 pares aninhados** do
    defeito da fonte, que no PDF saíam em Calibri ao lado dos rótulos em
    Times.

    **Por que sobreviveu:** o varredor da fonte lia o molde de nascimento e o
    de casamento, e não havia guarda para o de óbito. Agora ele varre **pela
    espécie** (`test_rc_certidao_molde.py`), e molde novo entra sozinho.

    **E era a hora:** a casa emitiu 18 certidões de nascimento e 4 de
    casamento, e **nenhuma de óbito** — com 31 assentos de óbito no sistema
    esperando a primeira.

O QUE MUDOU NO CORPO, MEDIDO CONTRA O ANEXO VI (página 7)
    Onze diferenças, e **duas são falta de campo obrigatório**:

    1. **a data do registro não existia em campo nenhum** — o Anexo tem «Data
       de registro» com Dia/Mês/Ano, e é item do art. 80 da Lei 6.015/1973.
       Os marcadores já existiam: nasceram no casamento;
    2. **o CPF estava na linha do cônjuge** — no Anexo ele tem caixa própria
       sob o nome do falecido; ali saía ao lado de «NOME DO CÔNJUGE», e quem
       lê pareia linha com linha. É o descasamento dos avós outra vez;
    3. local, município e UF do falecimento juntos num campo — e o local
       dividindo a linha com o **declarante**;
    4. município da naturalidade e UF juntos;
    5. data de nascimento sem as caixas de Dia/Mês/Ano;
    6. CRM colado no nome do médico;
    7. município e UF do sepultamento juntos;
    8. **«NATUREZA E CAUSA DA MORTE»** — o Anexo diz só «Causa da morte». A
       natureza é campo do **IBGE** (1 natural, 2 violenta, 9 ignorado), e não
       da certidão: rótulo que promete natureza faz quem lê esperar a palavra,
       e ela não vem;
    9. sexo/estado civil/cônjuge são UMA linha no Anexo, e idade + nascimento
       + naturalidade a seguinte; o molde misturava as duas;
   10. «POR EXTENSO» nos rótulos — o placeholder de dentro da caixa;
   11. «OBSERVAÇÕES/AVERBAÇÕES A ACRESCER» e «ANOTAÇÕES DE CADASTRO», onde o
       Anexo diz «Anotações/Averbações» e «Anotações voluntárias de cadastro».

    **O dado já estava todo no quadro** (`rc_certidao_quadro._quadro_obito`):
    local, município e UF do falecimento, médico e CRM separados, município e
    UF do sepultamento, e a data de nascimento em dia/mês/ano. O molde jogava
    fora — a mesma coisa que acontecia com o município de nascimento de cada
    genitor no de nascimento.

DOIS RÓTULOS FORAM ENCURTADOS, E FICA DITO POR QUÊ
    O Anexo escreve com uma fonte de rótulo muito menor que a nossa (8pt
    negrito), e dois não caberiam antes da caixa seguinte:

      · «Nome do médico que atestou o óbito ou, se for o caso, das
        testemunhas» — 70 caracteres, ~13 cm numa folha de 15,19 — vai «NOME
        DO MÉDICO OU DAS TESTEMUNHAS». O «se for o caso» é a regra de QUANDO a
        testemunha substitui o médico, e não conteúdo do campo;
      · «Horário do falecimento» quebrou em duas linhas no primeiro ensaio —
        vai «HORA DO ÓBITO». Alargar a caixa exigiria encurtar a da data por
        extenso, e a quebra sairia de cima do rótulo para dentro do **dado**,
        que é pior.
"""
from __future__ import annotations

import re
import sys
import zipfile
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_certidao_odt as ODT

MOLDE = RAIZ / "modelos" / "certidao_obito_modelo.odt"
tem_o_molde = pytest.mark.skipif(
    not MOLDE.is_file(), reason="o molde .odt não está nesta instalação")


def conteudo() -> str:
    return zipfile.ZipFile(MOLDE).read("content.xml").decode("utf-8")


def texto_do_molde() -> str:
    x = conteudo()
    x = x[x.find("<office:body"):]
    x = re.sub(r"<text:tab/>", " | ", x)
    x = re.sub(r"<text:line-break/>", "\n", x)
    x = re.sub(r'<text:s text:c="(\d+)"/>', lambda m: " " * int(m.group(1)), x)
    x = re.sub(r"<text:s[^/]*/>", " ", x)
    x = re.sub(r"</text:p>|</table:table-cell>", "\n", x)
    return re.sub(r"<[^>]+>", "", x)


def linhas() -> list[str]:
    return [l.strip() for l in texto_do_molde().split("\n") if l.strip()]


ROTULOS_DO_ANEXO_VI = [
    "NÚMERO DO CPF",
    "DATA DO FALECIMENTO | DIA | MÊS | ANO | HORA DO ÓBITO",
    "LOCAL DE FALECIMENTO | MUNICÍPIO DE FALECIMENTO | UF",
    "SEXO | ESTADO CIVIL | NOME DO ÚLTIMO CÔNJUGE OU CONVIVENTE",
    "IDADE | DIA | MÊS | ANO | MUNICÍPIO DA NATURALIDADE | UF",
    "NOME DO(A) GENITOR(ES)",
    "CAUSA DA MORTE",
    "NOME DO MÉDICO OU DAS TESTEMUNHAS | NÚMERO DO DOCUMENTO",
    "LOCAL DE SEPULTAMENTO / CREMAÇÃO | MUNICÍPIO | UF",
    "DATA DE REGISTRO | DIA | MÊS | ANO",
    "NOME DO DECLARANTE | EXISTÊNCIA DE BENS | EXISTÊNCIA DE FILHOS",
    "ANOTAÇÕES/AVERBAÇÕES",
    "ANOTAÇÕES VOLUNTÁRIAS DE CADASTRO",
]


@tem_o_molde
def test_todo_marcador_do_molde_o_codigo_sabe_preencher():
    """O guarda principal, o mesmo dos outros dois: `@` que o código não
    conhece **sai impresso** numa certidão assinada."""
    no_papel = set(re.findall(r"@[A-Za-z_0-9]+", texto_do_molde()))
    faltando = sorted(no_papel - set(ODT.valores({}, {}, {})))
    assert not faltando, (
        "estes marcadores estão no molde e o código não preenche — sairiam "
        f"escritos no papel: {faltando}")


@tem_o_molde
def test_o_corpo_e_o_do_anexo_vi_na_ordem_do_anexo_vi():
    """Cada linha do Anexo VI, na ordem dele."""
    fora = linhas()
    onde = []
    for rotulo in ROTULOS_DO_ANEXO_VI:
        assert rotulo in fora, f"o Anexo VI pede o rótulo «{rotulo}»"
        de = (onde[-1] + 1) if onde else 0
        onde.append(fora.index(rotulo, de))
    assert onde == sorted(onde), f"rótulos fora de ordem: {onde}"


@tem_o_molde
def test_a_data_do_registro_ENTROU():
    """**FALTAVA CAMPO OBRIGATÓRIO** — art. 80 da Lei 6.015/1973. O molde não
    tinha a data do registro em lugar nenhum, e os marcadores já existiam
    desde o casamento."""
    t = texto_do_molde()
    for marcador in ("@DATAREGISTROEXTENSOSN", "@diaregistro",
                     "@mesregistro", "@anoregistro"):
        assert marcador in t, f"{marcador} não está no molde"


@tem_o_molde
def test_o_cpf_e_do_FALECIDO_e_sai_debaixo_do_nome_dele():
    """**ERA DESCASAMENTO, e sai mais caro que repetição.** O CPF ficava ao
    lado de «NOME DO CÔNJUGE»: quem lê pareia os dois e conclui que é o CPF do
    cônjuge — e é o do falecido."""
    fora = linhas()
    onde_cpf = fora.index("NÚMERO DO CPF")
    onde_conjuge = next(i for i, l in enumerate(fora) if "CÔNJUGE" in l)
    assert onde_cpf < onde_conjuge, (
        "o CPF tem de vir sob o nome do falecido, e não na linha do cônjuge")
    assert "NOME DO CÔNJUGE | CPF" not in fora, "a linha antiga voltou"


@tem_o_molde
def test_o_que_o_anexo_vi_separa_nao_volta_junto():
    """Local, município e UF; médico e documento; sepultamento e município.
    O quadro já os traz separados — o molde é que os juntava."""
    t = texto_do_molde()
    for separado in ("@localfalecimento", "@municipio_falecimento",
                     "@uf_falecimento", "@municipio_naturalidade",
                     "@uf_naturalidade", "@medicoobito", "@crmobito",
                     "@localsepultamento", "@municipio_sepultamento",
                     "@uf_sepultamento", "@dianascfalecido",
                     "@mesnascfalecido", "@anonascfalecido",
                     "@diaobito", "@mesobito", "@anoobito"):
        assert separado in t, f"{separado} não está no molde"
    for juntou in ("@localobito", "@atestouobito", "@naturalidadefalecido",
                   "@datanascimentofalecido"):
        assert juntou not in t, f"{juntou} junta o que o Anexo VI separa"
    # e os que juntam continuam no VOCABULÁRIO: o oficial edita o molde, e
    # quem repuser a caixa única continua com o marcador que a monta.
    vocabulario = ODT.valores({}, {}, {})
    for juntou in ("@localobito", "@atestouobito", "@naturalidadefalecido",
                   "@datanascimentofalecido", "@sepultamento"):
        assert juntou in vocabulario, f"{juntou} saiu do vocabulário"


@tem_o_molde
def test_a_natureza_da_morte_nao_esta_no_rotulo():
    """**ELA É CAMPO DO IBGE, E NÃO DA CERTIDÃO** — 1 natural, 2 violenta, 9
    ignorado. O Anexo VI diz só «Causa da morte»; rótulo que promete natureza
    faz quem lê esperar a palavra, e ela não vem."""
    t = texto_do_molde()
    assert "NATUREZA" not in t
    assert "CAUSA DA MORTE" in t


@tem_o_molde
def test_o_rotulo_nao_e_o_placeholder_de_dentro_da_caixa():
    """Terceira vez, e as três foram do oficial: «(assinatura)», «DIA MÊS
    ANO» do Anexo V, e o «POR EXTENSO»."""
    assert "POR EXTENSO" not in texto_do_molde()


@tem_o_molde
def test_as_anotacoes_tem_os_nomes_do_anexo():
    """«OBSERVAÇÕES/AVERBAÇÕES A ACRESCER» era o texto de dentro da caixa;
    «ANOTAÇÕES DE CADASTRO» estava sem o «voluntárias», que é o que separa a
    anotação do art. 347 da que o interessado pede."""
    fora = linhas()
    assert "ANOTAÇÕES/AVERBAÇÕES" in fora
    assert "ANOTAÇÕES VOLUNTÁRIAS DE CADASTRO" in fora
    assert not [l for l in fora if "A ACRESCER" in l]


@tem_o_molde
def test_nenhum_valor_fica_aninhado_dentro_de_tvalor():
    """Os **20 pares** que o molde de óbito carregava — ver o cabeçalho. O
    varredor por espécie de `test_rc_certidao_molde.py` também os pega; este
    fica porque é aqui que a medição está escrita."""
    aninhados = re.findall(
        r'<text:span text:style-name="T\d+"><text:span '
        r'text:style-name="TValor(?:Negrito)?">', conteudo())
    assert not aninhados, f"o defeito da fonte voltou: {len(aninhados)} pares"


def test_o_quadro_do_obito_traz_separado_o_que_o_molde_agora_pede():
    """**A MEDIÇÃO QUE PERMITIU NÃO INVENTAR CAMPO.** Se algum destes sair do
    quadro, o molde passa a prometer o que o código não tem — e a certidão sai
    com a caixa vazia sem ninguém saber por quê."""
    v = ODT.valores(
        {"local_falecimento": "HOSPITAL SANTA RITA",
         "municipio_falecimento": "IMPERATRIZ",
         "municipio_falecimento_uf": "MA",
         "naturalidade": "BURITICUPU", "naturalidade_uf": "MA",
         "medico": "DR. PAULO MENDES", "crm": "CRM/MA 12345",
         "sepultamento": "CEMITÉRIO MUNICIPAL",
         "sepultamento_mun": "CIDADE EXEMPLO", "sepultamento_uf": "MA",
         "dma_nascimento": {"dia": "14", "mes": "03", "ano": "1948"},
         "dma_fato": {"dia": "02", "mes": "09", "ano": "2026"}},
        {}, {})
    assert v["@localfalecimento"] == "HOSPITAL SANTA RITA"
    assert v["@municipio_falecimento"] == "IMPERATRIZ"
    assert v["@uf_falecimento"] == "MA"
    assert v["@municipio_naturalidade"] == "BURITICUPU"
    assert v["@uf_naturalidade"] == "MA"
    assert v["@medicoobito"] == "DR. PAULO MENDES"
    assert v["@crmobito"] == "CRM/MA 12345"
    assert v["@localsepultamento"] == "CEMITÉRIO MUNICIPAL"
    assert v["@municipio_sepultamento"] == "CIDADE EXEMPLO"
    assert v["@uf_sepultamento"] == "MA"
    assert (v["@dianascfalecido"], v["@mesnascfalecido"],
            v["@anonascfalecido"]) == ("14", "03", "1948")
    assert (v["@diaobito"], v["@mesobito"], v["@anoobito"]) == ("02", "09",
                                                                "2026")


def test_campo_vazio_nao_afirma_nada():
    """Quadro sem o dado devolve um espaço — nunca zero, nunca um traço que
    pareça informação."""
    v = ODT.valores({}, {}, {})
    for marcador in ("@localfalecimento", "@municipio_falecimento",
                     "@uf_falecimento", "@medicoobito", "@crmobito",
                     "@uf_sepultamento", "@diaobito", "@dianascfalecido"):
        assert v[marcador] == " ", marcador
