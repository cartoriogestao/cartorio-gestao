"""O PAPEL DA CERTIDÃO DO RCPN, EDITÁVEL PELA TELA DE MODELOS.

    «Atualizar esses modelos no modulo de modelos, para poder editar por la»
                                            — o oficial, 10/09/2026

O DEFEITO QUE ISSO CONSERTA, MEDIDO
    O molde morava só em disco, e a linha 55 do `ATUALIZAR_SISTEMA.cmd` é

        robocopy "%FONTE%\\modelos" "%PROG%\\modelos" /E

    **`/E` copia a pasta inteira por cima**: todo ajuste que o oficial fizesse
    no `.odt` instalado era apagado na atualização seguinte, sem aviso e sem
    como recuperar — e ele não teria por que desconfiar, porque a certidão
    continuava saindo, só sem o ajuste dele.

    Agora o ajuste mora no banco, que o `robocopy` não alcança, e o arquivo do
    pacote volta a ser o que sempre devia ter sido: **o piso**.

POR QUE NÃO ENTROU NO CATÁLOGO DE `modelos_da_casa`
    Aquele guarda TEXTO, numa caixa de edição. Estes três são FORMULÁRIOS —
    tabelas, larguras de coluna em centímetros, estilos de fonte, as duas
    caixas de selo —, e formulário não se escreve numa caixa de texto: o
    oficial os desenha no LibreOffice.
"""
from __future__ import annotations

import sqlite3
import sys
import zipfile
from io import BytesIO
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import modelos_moldes as MOLDES
import rc_certidao_odt as ODT

MOLDE_NASC = RAIZ / "modelos" / "certidao_nascimento_modelo.odt"
tem_o_molde = pytest.mark.skipif(
    not MOLDE_NASC.is_file(), reason="o molde .odt não está nesta instalação")


@pytest.fixture()
def con():
    c = sqlite3.connect(":memory:")
    MOLDES.init_modelos_moldes_schema(c)
    yield c
    c.close()


# --------------------------------------------------- o piso e o ajuste


@tem_o_molde
def test_sem_ajuste_vale_o_papel_do_pacote(con):
    """**O CÓDIGO É O PISO.** Sem linha na tabela, sai o `.odt` que veio no
    pacote — e é isso que faz instalação nova nascer funcionando."""
    arquivo = MOLDES.arquivo_que_vale(con, "RC_MOLDE_NASCIMENTO")
    assert arquivo == MOLDE_NASC.read_bytes()
    assert MOLDES.como_esta(con, "RC_MOLDE_NASCIMENTO")["ajustado"] is False


@tem_o_molde
def test_o_ajuste_ganha_do_pacote(con):
    """Com linha na tabela, vale o papel do oficial."""
    ajustado = _molde_com(MOLDE_NASC.read_bytes(),
                          {"CERTIDÃO DE NASCIMENTO": "CERTIDÃO DE NASCIMENTO"})
    MOLDES.salvar(con, "RC_MOLDE_NASCIMENTO", arquivo=ajustado,
                  nome_arquivo="meu_molde.odt", quem="MARIO",
                  agora="2026-09-10T10:00")
    assert MOLDES.arquivo_que_vale(con, "RC_MOLDE_NASCIMENTO") == ajustado
    como = MOLDES.como_esta(con, "RC_MOLDE_NASCIMENTO")
    assert como["ajustado"] is True
    assert como["nome_arquivo"] == "meu_molde.odt"
    assert como["atualizado_por"] == "MARIO"
    assert como["tamanho"] == len(ajustado)


@tem_o_molde
def test_voltar_ao_padrao_e_apagar_a_linha(con):
    """**É POR ISSO QUE O PADRÃO NÃO MORA NO BANCO**: voltar atrás é apagar
    uma linha, e não recadastrar um arquivo que ninguém tem mais."""
    MOLDES.salvar(con, "RC_MOLDE_NASCIMENTO",
                  arquivo=MOLDE_NASC.read_bytes(), nome_arquivo=None,
                  quem=None, agora="2026-09-10T10:00")
    assert MOLDES.restaurar(con, "RC_MOLDE_NASCIMENTO") is True
    assert MOLDES.como_esta(con, "RC_MOLDE_NASCIMENTO")["ajustado"] is False
    # e restaurar de novo não mente dizendo que havia ajuste
    assert MOLDES.restaurar(con, "RC_MOLDE_NASCIMENTO") is False


def test_papel_que_esta_casa_nao_emite_e_recusado_com_a_lista(con):
    """Chave inventada não passa calada — e a recusa diz quais existem."""
    with pytest.raises(MOLDES.PapelError) as erro:
        MOLDES.arquivo_que_vale(con, "RC_MOLDE_NATIMORTO")
    assert "RC_MOLDE_NASCIMENTO" in str(erro.value)


# ------------------------------------------------------- a conferência


def _molde_com(base: bytes, trocas: dict[str, str]) -> bytes:
    """O mesmo `.odt`, com trocas no `content.xml`. Só para o ensaio."""
    fora = BytesIO()
    with zipfile.ZipFile(BytesIO(base)) as zin, \
            zipfile.ZipFile(fora, "w", zipfile.ZIP_DEFLATED) as zout:
        for item in zin.infolist():
            dados = zin.read(item.filename)
            if item.filename == "content.xml":
                texto = dados.decode("utf-8")
                for de, para in trocas.items():
                    texto = texto.replace(de, para)
                dados = texto.encode("utf-8")
            zout.writestr(item, dados)
    return fora.getvalue()


def test_arquivo_que_nao_e_odt_e_recusado(con):
    """Um `.doc`, um PDF ou um arquivo truncado."""
    erro = MOLDES.conferir("RC_MOLDE_NASCIMENTO", b"isto nao e um zip")
    assert erro and ".odt" in erro


def test_arquivo_vazio_e_recusado(con):
    assert MOLDES.conferir("RC_MOLDE_NASCIMENTO", b"")


@tem_o_molde
def test_marcador_que_o_codigo_NAO_preenche_e_recusado(con):
    """**O GUARDA MAIS IMPORTANTE DESTE PAPEL.**

    `@` que `rc_certidao_odt.valores()` não conhece **não é substituído: sai
    impresso** numa certidão assinada. `tests/test_rc_certidao_molde.py` já
    varre isso nos moldes do pacote; aqui a mesma régua passa a valer para o
    que o oficial enviar — e é a hora em que dá para consertar, e não o balcão
    com o cliente na frente.
    """
    torto = _molde_com(MOLDE_NASC.read_bytes(),
                       {"@nomenascido": "@nome_do_registrado"})
    erro = MOLDES.conferir("RC_MOLDE_NASCIMENTO", torto)
    assert erro and "@nome_do_registrado" in erro
    with pytest.raises(MOLDES.PapelError):
        MOLDES.salvar(con, "RC_MOLDE_NASCIMENTO", arquivo=torto,
                      nome_arquivo=None, quem=None, agora="2026-09-10T10:00")
    # e NADA foi gravado: a conferência vem antes
    assert MOLDES.como_esta(con, "RC_MOLDE_NASCIMENTO")["ajustado"] is False


@tem_o_molde
def test_molde_sem_a_matricula_e_recusado(con):
    """A matrícula de 32 dígitos é a identidade nacional da certidão: sem ela
    o papel não serve, e a falta só apareceria quando alguém fosse conferir o
    registro noutra serventia. **Já se perdeu uma vez**, em 01/09/2026, ao
    derivar os moldes de casamento e óbito do de nascimento."""
    sem = _molde_com(MOLDE_NASC.read_bytes(), {"@matriculanascido": " "})
    erro = MOLDES.conferir("RC_MOLDE_NASCIMENTO", sem)
    assert erro and "matrícula" in erro.lower()


@tem_o_molde
def test_a_matricula_cobrada_e_a_da_ESPECIE_daquele_papel(con):
    """`@matriculacasamento` num molde de nascimento não serve: quem preenche
    olha o nome do marcador, e o campo sairia em branco."""
    trocado = _molde_com(MOLDE_NASC.read_bytes(),
                         {"@matriculanascido": "@matriculacasamento"})
    assert MOLDES.conferir("RC_MOLDE_NASCIMENTO", trocado)


@tem_o_molde
def test_o_molde_do_pacote_passa_na_propria_conferencia():
    """A régua não pode reprovar o papel que a casa emite hoje — seria régua
    errada, e não papel errado."""
    for m in MOLDES.MOLDES:
        caminho = MOLDES.caminho_padrao(m["chave"])
        if not caminho.is_file():
            continue
        assert MOLDES.conferir(m["chave"], caminho.read_bytes()) is None, (
            f"a conferência reprovou o molde do pacote: {m['nome']}")


# ------------------------------------------------ a amarração com a certidão


def test_cada_especie_tem_o_seu_papel():
    """E o casamento religioso usa o do casamento: **muda de livro, e não de
    papel** — a mesma decisão de `rc_certidao_odt.MOLDE_DA_ESPECIE`."""
    assert MOLDES.chave_da_especie("NASCIMENTO") == "RC_MOLDE_NASCIMENTO"
    assert MOLDES.chave_da_especie("CASAMENTO") == "RC_MOLDE_CASAMENTO"
    assert MOLDES.chave_da_especie("CASAMENTO_RELIGIOSO") == "RC_MOLDE_CASAMENTO"
    assert MOLDES.chave_da_especie("OBITO") == "RC_MOLDE_OBITO"
    # espécie que o molde não serve não ganha papel inventado
    assert MOLDES.chave_da_especie("INTERDICAO") is None
    assert MOLDES.chave_da_especie(None) is None


def test_o_catalogo_aponta_para_os_moldes_QUE_EXISTEM():
    """**O CATÁLOGO GUARDA ONDE MORA, E NÃO O CAMINHO ESCRITO À MÃO.** Quem
    mapeia espécie para arquivo é `rc_certidao_odt`, que é quem o abre para
    imprimir; um segundo mapa aqui divergiria no dia em que um dos dois
    mudasse de nome — e a tela passaria a oferecer um papel que o programa
    não usa."""
    for m in MOLDES.MOLDES:
        assert m["especie"] in ODT.MOLDE_DA_ESPECIE, m["chave"]
        assert MOLDES.caminho_padrao(m["chave"]) == ODT.molde_da_especie(
            m["especie"])


@tem_o_molde
def test_a_certidao_sai_no_papel_AJUSTADO():
    """A ponta final: `arquivo_da_certidao` monta a certidão sobre o papel que
    a casa gravou, e não sobre o do pacote."""
    marca = "PAPEL AJUSTADO PELA CASA"
    ajustado = _molde_com(MOLDE_NASC.read_bytes(),
                          {"CERTIDÃO DE NASCIMENTO": marca})
    saiu = ODT.arquivo_da_certidao(
        {"especie": "NASCIMENTO", "nome": "MARIA"}, {}, {},
        molde_bytes=ajustado)
    with zipfile.ZipFile(BytesIO(saiu)) as z:
        texto = z.read("content.xml").decode("utf-8")
    assert marca in texto
    assert "CERTIDÃO DE NASCIMENTO" not in texto


@tem_o_molde
def test_sem_papel_ajustado_a_certidao_continua_saindo():
    """**DOCUMENTO QUE NÃO SAI É PIOR QUE DOCUMENTO SEM O AJUSTE NOVO.** Sem
    `molde_bytes`, vale o do pacote — que é o caminho de hoje e o de qualquer
    instalação que nunca tenha ajustado nada."""
    saiu = ODT.arquivo_da_certidao(
        {"especie": "NASCIMENTO", "nome": "MARIA"}, {}, {})
    with zipfile.ZipFile(BytesIO(saiu)) as z:
        texto = z.read("content.xml").decode("utf-8")
    assert "CERTIDÃO DE NASCIMENTO" in texto


def test_instalacao_sem_a_tabela_nao_derruba_a_certidao():
    """**O PISO NÃO PODE DEPENDER DO ANDAR DE CIMA** — a mesma decisão de
    `modelos_da_casa.corpo_de`. Banco a meio de migrar continua imprimindo o
    papel do pacote, em vez de estourar na cara de quem emite."""
    c = sqlite3.connect(":memory:")           # sem `mo_moldes`
    try:
        assert MOLDES.como_esta(c, "RC_MOLDE_NASCIMENTO")["ajustado"] is False
        assert MOLDES.restaurar(c, "RC_MOLDE_NASCIMENTO") is False
    finally:
        c.close()
