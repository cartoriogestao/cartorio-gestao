"""As pontes do casamento e do obito — do assento para o termo da casa.

    «Termo de nascimento, casamento e obito vamos construir os nossos com os
     requisitos legais e regulamentares, nao utilizaremos os modelos ruins do
     e-oficio, nem em papel.»            — decisao do oficial, 30/08/2026

O QUE FALTAVA
    O termo da casa existia para as **tres** especies; a ponte do assento
    existia so para o **nascimento**. Sem ela, o termo que se lavra continuava
    saindo do modelo do E-Oficio — que e exatamente o que ele recusou.

OS QUATRO DEFEITOS QUE O ENSAIO ACHOU, e nenhum aparecia em teste de mesa

    1. **Tres nomes de coluna inventados.** Eu li `causa_morte`,
       `local_sepultamento` e `testamento` do assento, e **as tres nao
       existiam**. `get` nao estoura: o termo sairia sem a causa da morte e
       ninguem perceberia, porque campo ocasional vazio some de proposito.

    2. **Pontuacao dobrada**: «lavrador., filho de» — o modelo fecha a
       qualificacao com ponto e minha frase comecava com virgula.

    3. **A identificacao saia duas vezes**: «portador do RG n.º 123456» na
       qualificacao e «Identificado por RG n.º 123456.» tres linhas abaixo.

    4. **Linha vazia no meio do termo**, onde a frase ausente estava. No papel
       isso se le como falha de impressao — e a ordem do oficial foi «nao
       contera qualquer mencao ou espaco».
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_marcas_do_obito as MO                                  # noqa: E402
import rc_modelos_do_livro as ML                                 # noqa: E402

SV = {"ri_cidade": "Cidade Exemplo"}
QUEM = {"escrevente": "MARIO EXEMPLO", "funcao_do_escrevente": "Oficial"}


# ------------------------------------------------------- o casamento


CASAMENTO = {"data_ato": "2026-08-30", "regime_bens": "comunhão parcial"}
NUBENTES = [
    {"papel": "NUBENTE1", "nome": "JOAO BATISTA", "sexo": "M",
     "profissao": "lavrador", "nome_pos": "JOAO BATISTA"},
    {"papel": "NUBENTE2", "nome": "MARIA DAS DORES", "sexo": "F",
     "profissao": "professora", "nome_pos": "MARIA DAS DORES SOUSA"},
    {"papel": "MAE_NUBENTE1", "nome": "ANA"},
    {"papel": "PAI_NUBENTE1", "nome": "PEDRO"},
    {"papel": "MAE_NUBENTE2", "nome": "RITA"},
    {"papel": "PAI_NUBENTE2", "nome": "JOSE"},
    {"papel": "TESTEMUNHA", "nome": "CARLOS"},
    {"papel": "TESTEMUNHA", "nome": "LUCIA"},
]
DOCS = [
    {"descricao": "Certidão de nascimento", "apresentado": 1},
    {"descricao": "Documento de identidade", "apresentado": 1},
    {"descricao": "Certidão de óbito do cônjuge anterior", "dispensado": 1,
     "dispensado_motivo": "solteiros"},
]


def _casar(**troca):
    dados = dict(documentos=DOCS, sv=SV, **QUEM)
    pessoas = troca.pop("pessoas", NUBENTES)
    assento = dict(CASAMENTO, **troca.pop("assento", {}))
    dados.update(troca)
    return ML.montar_casamento_do_assento(assento, pessoas, **dados)


def test_o_termo_relaciona_os_documentos_um_a_um():
    """**Quem confere um casamento anos depois precisa saber QUAIS.**"""
    texto = _casar()["texto"]
    assert "Certidão de nascimento" in texto
    assert "Documento de identidade" in texto
    assert "os documentos exigidos em lei" not in texto


def test_o_dispensado_nao_entra_como_apresentado():
    """**A dispensa é ato do oficial**, e a correição pergunta por ela.

    Misturar os dois faria o termo afirmar que se apresentou o que a serventia
    dispensou.
    """
    texto = _casar()["texto"]
    assert "dispensada a apresentação de" in texto
    assert "Certidão de óbito do cônjuge anterior (solteiros)" in texto


def test_quando_um_muda_de_nome_o_termo_diz_qual():
    texto = _casar()["texto"]
    assert "Passou o cônjuge MARIA DAS DORES a assinar-se " \
           "MARIA DAS DORES SOUSA." in texto


def test_quando_NINGUEM_muda_o_termo_diz_isso():
    """**Pedido do oficial**: «se ninguém mudou o nome, fala que ambos mantêm
    os mesmos nomes». O silêncio é pior que qualquer das duas frases."""
    iguais = [dict(p, nome_pos=p["nome"]) if p["papel"].startswith("NUBENTE")
              else p for p in NUBENTES]
    texto = _casar(pessoas=iguais)["texto"]
    assert "Nenhum dos cônjuges alterou o nome" in texto
    assert "Passou o cônjuge" not in texto


def test_quando_os_DOIS_mudam_o_termo_diz_os_dois():
    dois = [dict(p, nome_pos=p["nome"] + " REIS")
            if p["papel"].startswith("NUBENTE") else p for p in NUBENTES]
    texto = _casar(pessoas=dois)["texto"]
    assert "Passaram os cônjuges a assinar-se" in texto


def test_as_QUATRO_filiacoes_saem_separadas_por_nubente():
    """São quatro pessoas, e o art. 70 exige a filiação dos dois."""
    texto = _casar()["texto"]
    assert "São pais do primeiro nubente ANA e PEDRO" in texto
    assert "do segundo, RITA e JOSE" in texto


def test_um_casamento_comum_sai_COMPLETO():
    """**Alarme que soa sempre é alarme que ninguém ouve.**

    Não ser conversão de união estável não é uma falta.
    """
    r = _casar()
    assert r["completo"], f"faltou: {r['em_branco']}"
    assert "Conversão de união estável" in r["nao_e_o_caso"]


# ------------------------------------------------------- o óbito


OBITO = {"data_ato": "2026-08-30", "data_fato": "2026-08-29",
         "hora_fato": "14:30", "local_fato_nome": "Hospital Municipal",
         "numero_do": "12345678", "causa_morte": "natural",
         "local_sepultamento": "Cemitério Municipal"}
DO_OBITO = [
    {"papel": "FALECIDO", "nome": "ANTONIO PEREIRA", "sexo": "M",
     "profissao": "lavrador", "estado_civil": "casado",
     "documento_tipo": "RG", "documento_numero": "123456"},
    {"papel": "DECLARANTE", "nome": "MARIA PEREIRA", "sexo": "F",
     "profissao": "do lar"},
    {"papel": "MAE", "nome": "ANA PEREIRA"},
    {"papel": "PAI", "nome": "JOSE PEREIRA"},
]
TUDO_PERGUNTADO = {"obito_eleitor": MO.SIM, "obito_possui_bens": MO.NAO,
                   "obito_possui_filho": MO.SIM,
                   "obito_desconhecido": MO.NAO}


def _obitar(**troca):
    pessoas = troca.pop("pessoas", DO_OBITO)
    assento = dict(OBITO, **troca.pop("assento", {}))
    marcas = troca.pop("marcas", TUDO_PERGUNTADO)
    return ML.montar_obito_do_assento(assento, pessoas, marcas=marcas,
                                      sv=SV, **QUEM)


def test_as_tres_colunas_do_art_255_existem_no_esquema():
    """**Eu inventei as três ao escrever a ponte**, e `get` não estoura: o
    termo sairia sem a causa da morte e ninguém perceberia."""
    import rc_schema as RS

    colunas = {c for _, c, _ in RS.MIGRACOES}
    for quem in ("causa_morte", "local_sepultamento", "testamento"):
        assert quem in colunas, f"{quem} não está nas migrações"


def test_o_termo_traz_a_causa_o_sepultamento_e_as_marcas():
    texto = _obitar()["texto"]
    assert "A morte foi natural." in texto
    assert "Sepultado em Cemitério Municipal." in texto
    assert "Era eleitor." in texto and "Deixou filhos." in texto
    assert "Não deixou bens." in texto


def test_a_pontuacao_nao_dobra():
    """«lavrador., filho de» — o modelo fecha com ponto e a frase começava com
    vírgula. Medido no primeiro ensaio."""
    texto = _obitar()["texto"]
    assert "., " not in texto.replace("n.º", "")
    assert "Filho de ANA PEREIRA e JOSE PEREIRA." in texto


def test_a_identificacao_nao_sai_duas_vezes():
    """A qualificação já traz o documento — repetir é dizer a mesma coisa duas
    vezes no papel que a serventia assina."""
    texto = _obitar()["texto"]
    # **O PADRAO INCLUI O «RG», e nao so o numero.** A primeira versao contava
    # a substring `123456`, que casa tambem dentro de `12345678` — o numero da
    # Declaracao de Obito — e acusava repeticao onde nao havia. Procurar por
    # pedaco de numero acha o numero vizinho.
    assert texto.count("RG n.º 123456") == 1
    assert "Identificado por" not in texto


def test_quando_nao_ha_identificacao_o_termo_declara():
    sem_doc = [{k: v for k, v in p.items() if "documento" not in k}
               for p in DO_OBITO]
    texto = _obitar(pessoas=sem_doc,
                    marcas=dict(TUDO_PERGUNTADO,
                                obito_desconhecido=MO.SIM))["texto"]
    assert "Não foi possível identificar a pessoa falecida." in texto


def test_o_que_o_declarante_ignorava_vira_declaracao_do_paragrafo_1():
    """**A norma manda escrever que se perguntou** — art. 255, § 1º.

    É a diferença entre «não» e «não perguntei», e é por isso que as marcas
    têm três estados.
    """
    marcas = dict(TUDO_PERGUNTADO, obito_possui_bens=MO.NAO_PERGUNTADO,
                  obito_possui_filho=MO.NAO_PERGUNTADO)
    texto = _obitar(marcas=marcas)["texto"]
    assert "O oficial indagou" in texto
    assert "§ 1º" in texto
    # e o que foi respondido NAO entra na declaracao
    assert "Era eleitor." in texto


def test_nao_sobra_linha_vazia_no_meio_do_termo():
    """**«Não conterá qualquer menção ou espaço»** — e linha vazia é espaço.

    No papel ela se lê como falha de impressão.
    """
    for r in (_obitar(), _casar()):
        vazias = [i for i, l in enumerate(r["texto"].splitlines())
                  if not l.strip()]
        assert not vazias, f"linhas vazias em {vazias}"


def test_um_obito_comum_sai_COMPLETO():
    """Metade dos campos do óbito é frase ocasional — sem testamento, sem bens
    declarados. Marcá-lo incompleto faria o aviso soar em todo óbito."""
    r = _obitar()
    assert r["completo"], f"faltou: {r['em_branco']}"
