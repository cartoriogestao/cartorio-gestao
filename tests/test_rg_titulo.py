"""O TÍTULO APRESENTADO no RCPJ e no RTD — do protocolo ao registro.

    «Preciso que o sistema receba o título em protocolo (…) se positiva a
     qualificação possa imprimir a etiqueta de registro para o título
     apresentado em papel, ou encaminhamento pela ONRTDPJ para os
     eletrônicos.» — o oficial, 03/09/2026

O QUE ESTES TESTES GUARDAM
      - **o número do protocolo sai do Livro de Protocolo do núcleo**, e não de
        um contador deste módulo — `PJ_PROTOCOLO` e `TD_PROTOCOLO` estavam
        declarados desde 21/08/2026 e nenhuma tela escrevia neles;
      - **o título entra antes de qualquer exigência** (Lei 6.015/1973, art.
        12): só a data é obrigatória;
      - **as duas atribuições contam SEPARADO**, como no E-Ofício
        (`intProtocolo_RTD` = 1.275 e `intProtocolo_RPJ` = 1.273);
      - **negativa sem exigência escrita não passa** — devolver dizendo «não
        pode» é devolver sem dizer o que fazer;
      - **só se registra com qualificação positiva**, e um título tem um
        registro e não dois;
      - **cada situação terminal tem quem a produza** — a lição medida do
        E-Ofício, onde `bitFinalizado` é 0 em 21.360 de 21.360;
      - e **o módulo não transmite nada para a Central**: ele guarda a
        passagem, porque não há contrato medido a imitar.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))
from banco_de_teste import conexao_de_teste  # noqa: E402

import escrituracao as ESC
import livro_nucleo as LN
import rg_registro as RG
import rg_schema as RGS
import rg_titulo as TIT
from nucleo_schema import init_nucleo_schema

AGORA = "2026-09-03T09:30:00"
HOJE = "2026-09-03"
EXTENSO = "três de setembro de dois mil e vinte e seis"
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO/MA",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "MA", "ri_cns": "000000",
      "serventia_titular": "MARIO EXEMPLO DOS SANTOS",
      "serventia_titulo": "Tabelião e Oficial de Registro"}


@pytest.fixture()
def con(tmp_path):
    c = conexao_de_teste()
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys=ON")
    # As tabelas de que este módulo depende, e só elas: o núcleo (livro, lugar,
    # numeração) e as do RCPJ/RTD.
    init_nucleo_schema(c)
    # `cx_protocolos` antes do RCPJ/RTD: `rg_titulos` aponta para ela (FK), e
    # o PostgreSQL cobra a FK na criacao.
    c.executescript("""
        CREATE TABLE IF NOT EXISTS cx_protocolos (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numero TEXT);
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT, full_name TEXT);
    """)
    RGS.init_rg_schema(c)
    return c


def receber(con, **kw) -> dict:
    padrao = {"atribuicao": TIT.RTD, "sv": SV, "agora": AGORA,
              "data_extenso": EXTENSO, "data_apresentacao": HOJE,
              "apresentante": "ASSOCIAÇÃO X",
              "apresentante_documento": "00000010000127",
              "natureza": "Estatuto de associação", "usuario": "teste"}
    padrao.update(kw)
    return TIT.receber(con, **padrao)


# ------------------------------------------------- receber e protocolar


def test_o_numero_sai_do_livro_de_protocolo_do_nucleo(con):
    """**O contador é o do núcleo, e não um deste módulo.**

    `livro_nucleo` declara `TD_PROTOCOLO` desde 21/08/2026 — diário, com termo
    contínuo, citando o contador medido do E-Ofício — e **nenhuma tela jamais
    escreveu nele**. Um segundo contador aqui seria a segunda fonte para o
    mesmo número: o defeito que abriu a matrícula 4011 depois de a 4013 já
    existir, em 18/08/2026.
    """
    feito = receber(con)
    assert feito["numero_ordem"] == 1
    lugar = ESC.lugar_de(con, "rg_titulos", feito["titulo_id"])
    assert lugar, "o título não ocupou lugar no Livro de Protocolo"
    livro = con.execute("SELECT serie FROM nu_livros WHERE id=?",
                        (lugar["livro_id"],)).fetchone()
    assert livro["serie"] == "TD_PROTOCOLO"


def test_o_titulo_guarda_onde_ficou_no_livro(con):
    """Livro, folha e número ficam na própria linha — é o que a etiqueta e a
    nota devolutiva imprimem, e ir buscá-los em `nu_lugares` a cada papel faria
    o mesmo dado sair de dois lugares."""
    feito = receber(con)
    t = TIT.um(con, feito["titulo_id"])
    assert t["numero"] == feito["numero_ordem"]
    assert t["livro_id"] == feito["livro_id"]
    assert t["rotulo"] == feito["rotulo"]


def test_as_duas_atribuicoes_contam_separado(con):
    """**Medido no E-Ofício:** `tbTD_Propriedade` guarda `intProtocolo_RTD` =
    1.275 e `intProtocolo_RPJ` = 1.273 — dois contadores, e não um. Um
    contador só faria o protocolo do RCPJ pular por causa do movimento do RTD.
    """
    a = receber(con, atribuicao=TIT.RTD)
    b = receber(con, atribuicao=TIT.RCPJ)
    c = receber(con, atribuicao=TIT.RTD)
    assert a["numero_ordem"] == 1
    assert b["numero_ordem"] == 1, "o RCPJ herdou o número do RTD"
    assert c["numero_ordem"] == 2


def test_o_titulo_entra_sem_natureza_sem_serie_e_sem_apresentante(con):
    """**Lei 6.015/1973, art. 12**: nenhuma exigência obsta a apresentação do
    título e o seu lançamento no protocolo com o número de ordem. Campo
    obrigatório a mais aqui é título esperando na bancada — e perdendo a ordem
    de chegada, que é a única coisa que o protocolo garante."""
    feito = TIT.receber(con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA,
                        data_extenso=EXTENSO, data_apresentacao=HOJE)
    t = TIT.um(con, feito["titulo_id"])
    assert t["numero"] == 1
    assert t["natureza"] is None and t["serie"] is None
    assert t["situacao"] == TIT.APRESENTADO


def test_sem_data_nao_ha_ordem_no_livro(con):
    with pytest.raises(TIT.TituloError, match="data"):
        TIT.receber(con, atribuicao=TIT.RTD, sv=SV, agora=AGORA,
                    data_extenso=EXTENSO, data_apresentacao="")


def test_atribuicao_que_nao_e_rcpj_nem_rtd_e_recusada(con):
    with pytest.raises(TIT.TituloError, match="RCPJ"):
        receber(con, atribuicao=5)


def test_livro_de_outra_atribuicao_e_recusado(con):
    """**A atribuição não se pergunta duas vezes.** Quem sabe de qual
    atribuição é a série é `livro_nucleo.SERIES` — o mesmo lugar de onde
    `rg_registro` a lê. Sem isto, um título do RCPJ entraria pedindo o Livro B
    do RTD, e o erro só apareceria ao registrar."""
    with pytest.raises(TIT.TituloError, match="não é do"):
        receber(con, atribuicao=TIT.RCPJ, serie="TD_B")


def test_forma_desconhecida_e_recusada(con):
    with pytest.raises(TIT.TituloError, match="forma"):
        receber(con, forma="FAX")


def test_a_carga_e_repetivel_por_construcao(con):
    """Reapresentar a mesma (origem, origem_chave) devolve o id já existente —
    a mesma regra de `rg_registro.abrir_registro`."""
    a = receber(con, origem="EOFICIO", origem_chave="tbRegistroTD:10078")
    b = receber(con, origem="EOFICIO", origem_chave="tbRegistroTD:10078")
    assert b["reaproveitado"] is True
    assert b["titulo_id"] == a["titulo_id"]
    assert con.execute("SELECT COUNT(*) n FROM rg_titulos").fetchone()["n"] == 1


def test_origem_eoficio_sem_chave_e_recusada(con):
    with pytest.raises(TIT.TituloError, match="chave de origem"):
        receber(con, origem="EOFICIO", origem_chave="")


def test_dados_que_faltaram_na_apresentacao_podem_ser_completados(con):
    feito = TIT.receber(con, atribuicao=TIT.RCPJ, sv=SV, agora=AGORA,
                        data_extenso=EXTENSO, data_apresentacao=HOJE)
    TIT.atualizar(con, feito["titulo_id"], apresentante="ASSOCIAÇÃO NOVA",
                  natureza="Ata e estatuto", serie="PJ_A", vias=2,
                  forma=TIT.PAPEL)
    titulo = TIT.um(con, feito["titulo_id"])
    assert titulo["apresentante"] == "ASSOCIAÇÃO NOVA"
    assert titulo["natureza"] == "Ata e estatuto"
    assert titulo["serie"] == "PJ_A" and titulo["vias"] == 2


def test_edicao_nao_aceita_livro_de_outra_atribuicao(con):
    feito = receber(con, atribuicao=TIT.RCPJ)
    with pytest.raises(TIT.TituloError, match="não é do"):
        TIT.atualizar(con, feito["titulo_id"], serie="TD_B")


def test_titulo_que_ja_saiu_nao_e_editado_em_silencio(con):
    feito = receber(con)
    TIT.encerrar(con, feito["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="O interessado desistiu do pedido.", agora=AGORA)
    with pytest.raises(TIT.TituloError, match="já saiu"):
        TIT.atualizar(con, feito["titulo_id"], natureza="outra")


# --------------------------------------------------------- qualificar


def test_a_positiva_libera_o_registro(con):
    feito = receber(con)
    r = TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA,
                       agora=AGORA, usuario="teste")
    assert r["situacao"] == TIT.QUALIFICADO
    assert TIT.um(con, feito["titulo_id"])["situacao"] == TIT.QUALIFICADO


def test_a_negativa_sem_exigencia_escrita_nao_passa(con):
    """**Devolver um título dizendo apenas «não pode» é devolver sem dizer o
    que fazer** — e o apresentante volta ao balcão para perguntar, que é o
    mesmo trabalho feito duas vezes. A régua são as mesmas dez letras do resto
    da casa."""
    feito = receber(con)
    with pytest.raises(TIT.TituloError, match="exigência"):
        TIT.qualificar(con, feito["titulo_id"], resultado=TIT.NEGATIVA,
                       agora=AGORA, exigencias="falta doc")


def test_a_negativa_com_exigencia_devolve_o_titulo(con):
    feito = receber(con)
    r = TIT.qualificar(
        con, feito["titulo_id"], resultado=TIT.NEGATIVA, agora=AGORA,
        exigencias="Falta a ata de eleição da diretoria, com as assinaturas.",
        prazo_ate="2026-09-20")
    assert r["situacao"] == TIT.EXIGENCIA
    t = TIT.um(con, feito["titulo_id"])
    assert t["prazo_ate"] == "2026-09-20"


def test_a_positiva_nao_carrega_exigencia_sobrando(con):
    """Exigência guardada numa decisão positiva faria a tela mostrar pendência
    em título liberado, e alguém a leria como aberta."""
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA,
                   agora=AGORA, exigencias="sobra de um rascunho anterior")
    assert TIT.ultima_qualificacao(con, feito["titulo_id"])["exigencias"] is None


def test_requalificar_e_linha_nova_e_nao_correcao(con):
    """**A decisão velha fica**: é ela que explica por que o título voltou, e é
    ela que a correição lê."""
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.NEGATIVA,
                   agora=AGORA,
                   exigencias="Falta a ata de eleição da diretoria.")
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA,
                   agora=AGORA)
    decisoes = TIT.qualificacoes_de(con, feito["titulo_id"])
    assert [d["ordem"] for d in decisoes] == [1, 2]
    assert decisoes[0]["resultado"] == TIT.NEGATIVA
    assert TIT.ultima_qualificacao(con, feito["titulo_id"])["ordem"] == 2


def test_resultado_desconhecido_e_recusado(con):
    feito = receber(con)
    with pytest.raises(TIT.TituloError, match="resultado"):
        TIT.qualificar(con, feito["titulo_id"], resultado="TALVEZ", agora=AGORA)


# ---------------------------------------------------------- registrar


def test_so_se_registra_com_qualificacao_positiva(con):
    """**O registro é o efeito da qualificação, e não o contrário.** Registrar
    antes seria gastar número de livro num título que ainda pode voltar."""
    feito = receber(con)
    with pytest.raises(TIT.TituloError, match="qualificação positiva"):
        TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO)


def test_o_registro_amarra_os_dois_lados(con):
    """A ponte existe nos dois sentidos de propósito: da ficha do registro se
    chega ao título apresentado (e ao PDF dele), e do título se chega ao
    registro que ele virou."""
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    r = TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO,
                      teor="Registro integral do documento apresentado.")
    t = TIT.um(con, feito["titulo_id"])
    assert t["situacao"] == TIT.REGISTRADO
    assert t["registro_id"] == r["registro_id"]
    reg = RG.registro(con, r["registro_id"])
    assert reg["titulo_id"] == feito["titulo_id"]
    assert TIT.titulo_do_registro(con, r["registro_id"])["id"] == feito["titulo_id"]


def test_o_registro_nasce_com_os_dados_do_titulo(con):
    """Redigitar o requerente na hora de registrar é a segunda fonte para o
    mesmo dado — e a segunda diverge da primeira no primeiro engano de
    digitação."""
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    r = TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO)
    reg = RG.registro(con, r["registro_id"])
    assert reg["requerente_nome"] == "ASSOCIAÇÃO X"
    assert reg["requerente_documento"] == "00000010000127"
    assert reg["natureza"] == "Estatuto de associação"


def test_um_titulo_tem_um_registro_e_nao_dois(con):
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV, agora=AGORA,
                  data_extenso=EXTENSO)
    with pytest.raises(TIT.TituloError, match="já foi registrado"):
        TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO)


def test_registrar_em_livro_de_outra_atribuicao_e_recusado(con):
    feito = receber(con, atribuicao=TIT.RCPJ)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    with pytest.raises(TIT.TituloError, match="não é do"):
        TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO)


def test_o_ato_do_registro_ocupa_lugar_no_livro_da_serie(con):
    """O registro é o do `rg_registro` — mesmo livro, mesma numeração, mesma
    regra de folha nova. Uma segunda versão dele aqui divergiria no primeiro
    conserto."""
    feito = receber(con)
    TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    r = TIT.registrar(con, feito["titulo_id"], serie="TD_B", sv=SV,
                      agora=AGORA, data_extenso=EXTENSO)
    lugar = ESC.lugar_de(con, "rg_atos", r["ato_id"])
    livro = con.execute("SELECT serie FROM nu_livros WHERE id=?",
                        (lugar["livro_id"],)).fetchone()
    assert livro["serie"] == "TD_B"
    assert LN.serie("TD_B").folha_nova is True


# ------------------------------------------------------------ encerrar


def test_as_duas_palavras_do_encerramento_existem_e_sao_diferentes(con):
    """**`DEVOLVIDO` é o título que voltou ao apresentante; `CANCELADO` é o que
    não virou serviço.** Juntar as duas faria a correição não distinguir o
    trabalho feito do trabalho que não houve — a lição de
    `caixa_protocolo`."""
    a = receber(con)
    b = receber(con)
    TIT.encerrar(con, a["titulo_id"], situacao=TIT.DEVOLVIDO,
                 motivo="O apresentante retirou o título no balcão.",
                 agora=AGORA)
    TIT.encerrar(con, b["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="Pedido de orçamento; não voltou.", agora=AGORA)
    assert TIT.um(con, a["titulo_id"])["situacao"] == TIT.DEVOLVIDO
    assert TIT.um(con, b["titulo_id"])["situacao"] == TIT.CANCELADO


def test_o_motivo_do_encerramento_e_obrigatorio(con):
    feito = receber(con)
    with pytest.raises(TIT.TituloError, match="dez letras"):
        TIT.encerrar(con, feito["titulo_id"], situacao=TIT.DEVOLVIDO,
                     motivo="ok", agora=AGORA)


def test_o_motivo_fica_escrito_e_nao_apaga_o_que_havia(con):
    feito = receber(con, observacao="Veio pelo malote da associação.")
    TIT.encerrar(con, feito["titulo_id"], situacao=TIT.DEVOLVIDO,
                 motivo="O apresentante retirou o título no balcão.",
                 agora=AGORA)
    anotacao = TIT.um(con, feito["titulo_id"])["observacao"]
    assert "malote" in anotacao and "DEVOLVIDO:" in anotacao


def test_titulo_encerrado_nao_recebe_mais_decisao(con):
    feito = receber(con)
    TIT.encerrar(con, feito["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="Pedido de orçamento; não voltou.", agora=AGORA)
    with pytest.raises(TIT.TituloError):
        TIT.qualificar(con, feito["titulo_id"], resultado=TIT.POSITIVA,
                       agora=AGORA)
    with pytest.raises(TIT.TituloError):
        TIT.encerrar(con, feito["titulo_id"], situacao=TIT.DEVOLVIDO,
                     motivo="tentando encerrar duas vezes", agora=AGORA)


def test_toda_situacao_declarada_tem_quem_a_produza(con):
    """**A LIÇÃO MEDIDA DO E-OFÍCIO, em 03/09/2026.** Lá havia cinco situações
    declaradas em `tbProtocoloGeral_Situacao` e **21.360 de 21.360**
    protocolos na primeira, `bitFinalizado = 0` em todos, `dtmFinalizado` vazia
    em todos, e as 9.987 ocorrências **todas** com o código 1 «Aberto
    protocolo geral». A máquina de situação existia inteira e nunca foi
    exercitada.

    **Situação que nenhum caminho alcança é trava esperando um estado que nada
    cria** — o defeito que `caixa_protocolo` consertou em 28/08/2026. Este
    teste percorre as seis e produz cada uma.
    """
    produzidas = set()

    a = receber(con)
    produzidas.add(TIT.um(con, a["titulo_id"])["situacao"])

    TIT.qualificar(con, a["titulo_id"], resultado=TIT.NEGATIVA, agora=AGORA,
                   exigencias="Falta a ata de eleição da diretoria.")
    produzidas.add(TIT.um(con, a["titulo_id"])["situacao"])

    TIT.qualificar(con, a["titulo_id"], resultado=TIT.POSITIVA, agora=AGORA)
    produzidas.add(TIT.um(con, a["titulo_id"])["situacao"])

    TIT.registrar(con, a["titulo_id"], serie="TD_B", sv=SV, agora=AGORA,
                  data_extenso=EXTENSO)
    produzidas.add(TIT.um(con, a["titulo_id"])["situacao"])

    b = receber(con)
    TIT.encerrar(con, b["titulo_id"], situacao=TIT.DEVOLVIDO,
                 motivo="O apresentante retirou o título no balcão.",
                 agora=AGORA)
    produzidas.add(TIT.um(con, b["titulo_id"])["situacao"])

    c = receber(con)
    TIT.encerrar(con, c["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="Pedido de orçamento; não voltou.", agora=AGORA)
    produzidas.add(TIT.um(con, c["titulo_id"])["situacao"])

    assert produzidas == set(TIT.SITUACOES), (
        f"situação declarada que nenhum caminho produz: "
        f"{set(TIT.SITUACOES) - produzidas}")


# ------------------------------------------ a passagem pela Central


def test_o_encaminhamento_guarda_e_nao_transmite(con):
    """**ESTE MÓDULO GUARDA; QUEM FALA COM A CENTRAL É `onrtdpj_api`.** É a
    mesma separação de `cenprot_pendencias` e `cenprot_api`, e ela vale para os
    dois lados: o que a API faz também vira linha aqui, e o que se fez pelo
    portal entra pela mesma porta.

    (O comentário desta função dizia que não havia contrato a medir, porque o
    acervo do E-Ofício não tem uma coluna de RTDPJ. A medição estava certa e a
    conclusão errada: **o contrato da Central está público**. Ver
    `onrtdpj_api`.)
    """
    feito = receber(con, forma=TIT.ELETRONICO)
    TIT.registrar_encaminhamento(
        con, feito["titulo_id"], sentido=TIT.RECEBIDO, agora=AGORA,
        protocolo_central="2026.0001234", observacao="Baixado do portal.")
    linhas = TIT.encaminhamentos_de(con, feito["titulo_id"])
    assert len(linhas) == 1
    assert linhas[0]["central"] == "ONRTDPJ"
    assert linhas[0]["protocolo_central"] == "2026.0001234"


def test_o_modulo_nao_tem_funcao_que_ENVIE(con):
    """**Varredor**, e não confiança na leitura. Este módulo guarda o registro
    da passagem; no dia em que alguém escrever `enviar`, `transmitir` ou
    `postar` aqui sem contrato medido, o teste fica vermelho — e é assim que se
    impede a função pronta que alguém religa depois, já cinco vezes neste
    projeto.
    """
    proibidas = ("enviar", "transmitir", "postar", "upload", "sincronizar")
    achados = [nome for nome in dir(TIT)
               if not nome.startswith("_")
               and callable(getattr(TIT, nome))
               and any(p in nome.lower() for p in proibidas)]
    assert not achados, (
        f"função com nome de quem transmite: {achados}. A ONRTDPJ não tem "
        f"contrato medido nesta casa — ver o cabeçalho de `rg_titulo`.")


def test_sentido_desconhecido_e_recusado(con):
    feito = receber(con)
    with pytest.raises(TIT.TituloError, match="sentido"):
        TIT.registrar_encaminhamento(con, feito["titulo_id"], sentido="TALVEZ",
                                     agora=AGORA)


def test_o_titulo_de_papel_tambem_pode_ter_passagem_registrada(con):
    """Recusar por causa da forma esconderia um fato que aconteceu: um título
    de papel pode ter sido enviado à Central depois de registrado."""
    feito = receber(con, forma=TIT.PAPEL)
    TIT.registrar_encaminhamento(con, feito["titulo_id"], sentido=TIT.ENVIADO,
                                 agora=AGORA)
    assert TIT.encaminhamentos_de(con, feito["titulo_id"])


# ---------------------------------------------------------- consultas


def test_o_painel_traz_as_seis_situacoes_mesmo_em_zero(con):
    """Coluna que só aparece quando tem número faz o painel mudar de forma
    conforme o dia — e quem o lê todo dia perde a referência de onde olhar."""
    quadro = TIT.painel(con)
    assert set(quadro) == set(TIT.SITUACOES)
    assert all(v == 0 for v in quadro.values())
    receber(con)
    assert TIT.painel(con)[TIT.APRESENTADO] == 1


def test_a_fila_filtra_por_atribuicao_e_por_situacao(con):
    receber(con, atribuicao=TIT.RTD)
    b = receber(con, atribuicao=TIT.RCPJ)
    TIT.encerrar(con, b["titulo_id"], situacao=TIT.CANCELADO,
                 motivo="Pedido de orçamento; não voltou.", agora=AGORA)
    assert len(TIT.fila(con, atribuicao=TIT.RTD)) == 1
    assert len(TIT.fila(con, atribuicao=TIT.RCPJ)) == 1
    assert len(TIT.fila(con, situacao=TIT.CANCELADO)) == 1
    assert len(TIT.fila(con)) == 2


def test_titulo_do_registro_sem_ponte_devolve_None(con):
    """Os 72 registros do acervo nasceram sem título nenhum — inventar uma
    ponte por aproximação acharia título errado."""
    r = RG.abrir_registro(con, serie="TD_B", sv=SV, agora=AGORA,
                          data_extenso=EXTENSO, natureza="do acervo")
    assert TIT.titulo_do_registro(con, r["registro_id"]) is None
