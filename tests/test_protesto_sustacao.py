"""
A SUSTACAO JUDICIAL DO PROTESTO — Lei 9.492/1997, art. 17.

COMO ELA APARECEU
    Nos dezessete prints que o oficial fez do menu do E-Oficio, em 31/08/2026.
    «Efeito Suspensivo» esta la, em «Registrar Ocorrencia», e neste sistema
    nao existia em lugar nenhum.

POR QUE ELA E A MAIS GRAVE DA LISTA
    E ordem judicial que IMPEDE O PROTESTO. A tela «A protestar», construida
    na vespera, oferece em lote os titulos intimados sem movimentacao — e sem
    a sustacao registrada ela ofereceria, no meio dos outros, um titulo que o
    juiz mandou parar. Um clique, e o ato esta lavrado.

O QUE O ARTIGO MANDA — lido no Gentil, cap. 7, [p. 2568]

    Art. 17. Permanecerao no Tabelionato, a disposicao do Juizo respectivo, os
    titulos ... cujo protesto for judicialmente sustado.

    § 1o O titulo ... cujo protesto tiver sido sustado judicialmente so podera
    ser PAGO, PROTESTADO ou RETIRADO com autorizacao judicial.

    § 2o Revogada a ordem de sustacao, NAO HA NECESSIDADE de nova intimacao do
    devedor, sendo a lavratura e o registro do protesto efetivados ate o
    PRIMEIRO DIA UTIL SUBSEQUENTE ao do recebimento da revogacao ...

O QUE ESTES TESTES GUARDAM
      - SAO TRES ATOS BLOQUEADOS, e nao um: eu ia bloquear so o protesto;
      - a recusa DIZ QUAL E A ORDEM — juizo e processo —, porque quem esta no
        balcao precisa deles para explicar e para pedir a autorizacao;
      - o juizo e o processo sao OBRIGATORIOS ao registrar;
      - o sustado sai da fila do «A protestar» mesmo quando a ordem chegou
        ANTES da intimacao;
      - o REVOGADO volta a aparecer, e essa e a parte que quase se perdeu: com
        dois atos posteriores a intimacao ele sumiria para sempre, justamente
        com um dia util de prazo;
      - e o sistema NAO PROTESTA SOZINHO nem julga a ordem.

E A CASA NUNCA SUSTOU: medido, `tbAvisoProtesto.snSustado` e **0 em 1.370 de
1.370**. Nao e argumento contra construir — e a razao de construir antes do
primeiro, porque quando o mandado chegar ele chega com prazo exiguo.
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(__import__("pathlib").Path(__file__).resolve().parent))
from banco_de_teste import conexao_de_teste  # noqa: E402
from prova_de_intimacao import juntar_prova  # noqa: E402

import protesto as PT
from nucleo_schema import init_nucleo_schema
from pt_schema import init_pt_schema

AGORA = "2026-09-01T10:00:00"
HOJE = "2026-09-01"
SV = {"unit_name": "SERVENTIA", "cidade": "Cidade Exemplo", "uf": "MA"}
JUIZO = "1ª Vara Cível da Comarca de Cidade Exemplo/MA"
PROCESSO = "0800123-45.2026.8.10.0100"


def banco() -> sqlite3.Connection:
    con = conexao_de_teste()
    con.row_factory = sqlite3.Row
    init_nucleo_schema(con)
    init_pt_schema(con)
    return con


def titulo(con, *, numero="84713/1") -> int:
    cur = con.execute(
        """INSERT INTO pt_titulos(especie, numero_titulo, nosso_numero,
               valor_centavos, saldo_centavos, situacao, origem, criado_em,
               motivo_protesto)
           VALUES ('DMI',?,'00200000991',148278,148278,'RECEBIDO','CRA',?,'1')""",
        (numero, AGORA))
    tid = int(cur.lastrowid)
    con.execute(
        """INSERT INTO pt_devedores(titulo_id, nome, documento_tipo,
               documento_numero) VALUES (?,'MARIA SANTOS','CPF','04785512388')""",
        (tid,))
    return tid


def ate_a_intimacao(con, tid) -> None:
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA)
    # A PROVA DA INTIMAÇÃO (29/10/2026): o que se testa aqui é a ordem
    # judicial, e o protesto, quando cabe, sai com a prova junta.
    juntar_prova(con, tid)


def sustar(con, tid, **k):
    return PT.lancar_sustacao(con, tid, juizo=JUIZO, processo=PROCESSO,
                              agora=AGORA, **k)


# ------------------------------------------------ registrar a ordem


def test_a_ordem_se_registra_com_o_juizo_e_o_processo():
    con = banco()
    tid = titulo(con)
    r = sustar(con, tid)
    assert r["ato_id"]
    ordem = PT.sustacao_em_vigor(con, tid)
    assert ordem["juizo"] == JUIZO
    assert ordem["processo"] == PROCESSO


def test_sem_juizo_ou_processo_a_ordem_NAO_se_registra():
    """Campo em branco aqui vira, meses depois, um título parado que ninguém
    sabe por quê — e sem o processo não há como pedir a autorização judicial
    que o § 1º exige."""
    con = banco()
    tid = titulo(con)
    for juizo, processo in ((JUIZO, ""), ("", PROCESSO), ("", "")):
        with pytest.raises(PT.ProtestoError, match="juízo e o número do processo"):
            PT.lancar_sustacao(con, tid, juizo=juizo, processo=processo,
                               agora=AGORA)


def test_nao_se_susta_duas_vezes():
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    with pytest.raises(PT.ProtestoError, match="já está sustado"):
        sustar(con, tid)


def test_a_data_do_RECEBIMENTO_e_campo_proprio():
    """O mandado pode levar dias para chegar, e o prazo do § 2º corre do
    recebimento — não da decisão."""
    con = banco()
    tid = titulo(con)
    sustar(con, tid, recebido_em="2026-08-25")
    assert PT.sustacao_em_vigor(con, tid)["data_ato"] == "2026-08-25"


# ------------------------------- os TRÊS atos que o § 1º bloqueia


def test_o_PROTESTO_e_recusado_enquanto_a_ordem_vale():
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    with pytest.raises(PT.ProtestoError, match="SUSTADO por ordem judicial"):
        PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")


def test_o_PAGAMENTO_e_recusado_enquanto_a_ordem_vale():
    """Receber o dinheiro de um título que o juiz mandou parar é tão grave
    quanto lavrar o ato. Eu ia bloquear só o protesto; o § 1º bloqueia os
    três."""
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    with pytest.raises(PT.ProtestoError, match="SUSTADO por ordem judicial"):
        PT.lancar_pagamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")


def test_a_DESISTENCIA_e_recusada_enquanto_a_ordem_vale():
    """A desistência é a «retirada» do art. 17, § 1º — o pedido do credor de
    tirar o título antes do protesto."""
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    with pytest.raises(PT.ProtestoError, match="SUSTADO por ordem judicial"):
        PT.lancar_desistencia(con, tid, motivo="o credor desistiu",
                              agora=AGORA)


def test_a_recusa_DIZ_qual_e_a_ordem():
    """Quem está no balcão com o cliente na frente precisa do juízo e do
    processo para explicar — e para pedir a autorização judicial."""
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    with pytest.raises(PT.ProtestoError) as erro:
        PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    texto = str(erro.value)
    assert JUIZO in texto
    assert PROCESSO in texto
    assert "art. 17" in texto
    assert "AUTORIZAÇÃO JUDICIAL" in texto


def test_os_tres_atos_bloqueados_estao_declarados():
    assert set(PT.ATOS_QUE_A_SUSTACAO_BLOQUEIA) >= {
        "PROTESTO", "PAGAMENTO", "DESISTENCIA"}


# ------------------------------------------------------ a revogação


def test_revogada_a_ordem_o_protesto_volta_a_ser_possivel():
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)
    assert PT.sustacao_em_vigor(con, tid) is None
    r = PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    assert r["ato_id"]


def test_nao_se_revoga_o_que_nao_esta_sustado():
    con = banco()
    tid = titulo(con)
    with pytest.raises(PT.ProtestoError, match="não está sustado"):
        PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)


def test_sustar_revogar_e_sustar_de_novo_vale_a_ULTIMA_palavra():
    """A mesma ordem pode ser sustada, revogada e sustada de novo. Contar
    quantas há de cada daria a resposta errada na segunda vez — vale o ato
    mais recente."""
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)
    sustar(con, tid)
    assert PT.sustacao_em_vigor(con, tid) is not None


# -------------------------------------------------- e as duas listas


def test_o_sustado_SAI_da_fila_do_a_protestar():
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    assert len(PT.esperando_protesto(con, hoje=HOJE)) == 1
    sustar(con, tid)
    assert PT.esperando_protesto(con, hoje=HOJE) == []


def test_o_sustado_sai_da_fila_MESMO_com_a_ordem_ANTES_da_intimacao():
    """O `NOT EXISTS` da fila já tiraria o título quando a ordem chega DEPOIS
    da intimação — mas ela pode chegar antes, e aí ele continuaria ali. É a
    guarda explícita que fecha os dois casos."""
    con = banco()
    tid = titulo(con)
    PT.lancar_apontamento(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    sustar(con, tid)                       # a ordem chega ANTES
    PT.lancar_intimacao(con, tid, modo="PESSOAL", agora=AGORA)
    assert PT.esperando_protesto(con, hoje=HOJE) == []


def test_o_REVOGADO_volta_a_aparecer_e_essa_e_a_parte_que_quase_se_perdeu():
    """Depois de sustar e revogar há DOIS atos posteriores à intimação, e a
    fila do «A protestar» o excluiria para sempre — justamente o título que o
    art. 17, § 2º manda protestar até o primeiro dia útil seguinte.

    **Lista que esconde o que tem um dia de prazo é pior que não ter lista.**
    """
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA,
                                 recebido_em="2026-08-31")
    lista = PT.sustacao_revogada(con, hoje=HOJE)
    assert [x["id"] for x in lista] == [tid]
    assert lista[0]["dias_desde_a_revogacao"] == 1
    assert lista[0]["juizo"] == JUIZO
    assert lista[0]["devedores"][0]["nome"] == "MARIA SANTOS"


def test_o_revogado_JA_PROTESTADO_sai_da_lista():
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)
    PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")
    assert PT.sustacao_revogada(con, hoje=HOJE) == []


def test_ha_lista_dos_sustados_porque_eles_nao_aparecem_em_nenhuma_outra():
    """Eles ficam à disposição do Juízo (art. 17, caput), e saíram da fila do
    «A protestar» de propósito. Sem tela própria, ninguém sabe que existem."""
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    sustar(con, tid)
    lista = PT.sustados(con)
    assert [x["id"] for x in lista] == [tid]
    assert lista[0]["processo"] == PROCESSO


def test_o_revogado_nao_aparece_como_sustado():
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)
    assert PT.sustados(con) == []


# --------------------------------------- o que o sistema não faz


def test_o_modulo_nao_ganhou_funcao_que_JULGUE_a_ordem():
    """Ela vem do juiz; ao tabelião cabe cumprir. E o sistema não protesta
    sozinho quando a sustação cai — a mesma regra do tríduo, do oficial, de
    24/08/2026."""
    proibidas = [n for n in dir(PT) if not n.startswith("_")
                 and any(x in n.lower() for x in
                         ("julgar_sustacao", "sustacao_procede",
                          "protestar_apos_revogacao", "decidir_sustacao"))]
    assert proibidas == []


def test_sem_data_informada_o_recebimento_e_HOJE_e_isso_e_o_certo():
    """ESTE TESTE NASCEU AFIRMANDO O CONTRÁRIO, e a execução me corrigiu.

    Eu havia escrito que a data em branco devia dar `None`, pela mesma regra
    do tríduo — «zero diria que foi revogada hoje, que é afirmação». Não vale
    aqui: **o mandado se registra quando chega**, e quem não informa outra
    data está registrando o recebimento de agora. Afirmar «hoje» é o que
    aconteceu de fato.

    E `data_ato` é NOT NULL: um ato sem data não existe nesta tabela.
    """
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    PT.lancar_revogacao_sustacao(con, tid, agora=AGORA, recebido_em="")
    assert PT.sustacao_revogada(con, hoje=HOJE)[0][
        "dias_desde_a_revogacao"] == 0


def test_data_ILEGIVEL_da_None_e_nao_zero():
    """O caso de verdade do `None`: data que veio torta do acervo. Aí zero
    diria «revogada hoje» sobre um ato de que não se sabe a data — e num
    prazo de um dia útil essa diferença é o prazo inteiro."""
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    r = PT.lancar_revogacao_sustacao(con, tid, agora=AGORA)
    con.execute("UPDATE pt_atos SET data_ato='30/08/2026' WHERE id=?",
                (r["ato_id"],))
    assert PT.sustacao_revogada(con, hoje=HOJE)[0][
        "dias_desde_a_revogacao"] is None


# =====================================================================
# O EFEITO SUSPENSIVO — o outro instituto, e o único que esta casa usou
# =====================================================================
#
# SAO DOIS, e o E-Oficio guarda os dois na mesma tabela:
# `tbProtesto_TipoEfeitoTitulo` tem `1 = Suspensivo` e `2 = Sustado`.
#
#   SUSTAR ...... a ordem chega ANTES: o protesto nao se lavra.
#   SUSPENDER ... a ordem chega DEPOIS: o registro fica, e a publicidade para.
#
# MEDI A COLUNA ERRADA, E DEPOIS LI O CASO ERRADO — duas vezes no mesmo dia.
#
# Primeiro medi `tbAvisoProtesto.snSustado` (0 em 1.370) e conclui que a casa
# nunca usara nada disso. O oficial mandou procurar no banco, e a tabela
# propria apareceu: `tbProtesto_EfeitoSuspensivo`, 1 linha real — protocolo
# 7792040002, 18/08/2025, por GISELE, «PROTESTADO POR ENGANO».
#
#   **Coluna vazia nao prova que a coisa nao acontece; prova que aquela coluna
#   nao e onde ela fica.** Setima vez neste projeto.
#
# Ai eu li aquele caso como EFEITO SUSPENSIVO, pelo texto e pelo nome da
# tabela. O dado do titulo desmente: `snProtestado = 0`, sem livro nem folha,
# ocorrencia `3` (Retirado) na mesma data, e hoje PAGO. **O protesto nunca foi
# lavrado** — ordem que impede o ato e SUSTACAO. Bate com `intTipoEfeito = 2`
# (Sustado); o `id_tipoEfeito = 1` e que esta errado na linha.
#
#   **Nome de tabela e afirmacao de quem a criou; o estado do titulo e o
#   fato.** Bastava abrir o titulo.
#
# O placar, entao: sustacao **1**, efeito suspensivo **0**. Os dois continuam
# construidos — o dano que cada um evita nao depende de frequencia.


def protestar(con, tid):
    ate_a_intimacao(con, tid)
    return PT.lancar_protesto(con, tid, sv=SV, agora=AGORA, data_extenso="x")


def suspender(con, tid, **k):
    """A ordem DEFINITIVA, se o teste não disser outra: desde o LH13
    (21/10/2026) o caráter é obrigatório, e a definitiva é a que mantém a
    regra de antes na certidão (o protesto fica fora — CNN art. 263-K, I)."""
    k.setdefault("carater", "DEFINITIVA")
    return PT.lancar_efeito_suspensivo(con, tid, juizo=JUIZO,
                                       processo=PROCESSO, agora=AGORA, **k)


def test_suspende_os_efeitos_de_um_protesto_ja_lavrado():
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    r = suspender(con, tid)
    assert r["ato_id"]
    assert PT.efeito_suspensivo_em_vigor(con, tid)["processo"] == PROCESSO


def test_NAO_cabe_sobre_titulo_sem_protesto_lavrado():
    """Antes do protesto o instituto é outro — a sustação, que impede o ato.
    Usar um pelo outro faria a certidão dizer que há efeito suspenso sobre um
    protesto que não existe."""
    con = banco()
    tid = titulo(con)
    ate_a_intimacao(con, tid)
    with pytest.raises(PT.ProtestoError, match="não tem protesto lavrado"):
        suspender(con, tid)


def test_o_protesto_NAO_SOME_do_livro():
    """Apagar o protesto seria fazer sumir um ato lavrado. O que a ordem faz é
    parar a publicidade dele — o registro fica."""
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid)
    quantos = con.execute(
        "SELECT COUNT(*) FROM pt_atos WHERE titulo_id=? AND tipo='PROTESTO' "
        "AND cancelado=0", (tid,)).fetchone()[0]
    assert quantos == 1
    assert con.execute("SELECT situacao FROM pt_titulos WHERE id=?",
                       (tid,)).fetchone()[0] == "PROTESTADO"


def test_a_CERTIDAO_diz_que_os_efeitos_estao_suspensos():
    """**É aqui que este instituto pesa.** A certidão é o papel que faz o banco
    negar crédito, e um protesto cujos efeitos o juiz suspendeu sairia nela
    como protesto vivo.

    E ele **não some da certidão**: sumir seria mentir do outro lado — o
    protesto existe e está no livro, e certidão negativa sobre quem tem
    protesto é o erro que não se desfaz.
    """
    import protesto_certidao as PC
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    achados = PC.buscar(con, documento="04785512388")
    assert len(achados) == 1
    assert achados[0]["efeitos_suspensos"] is False

    suspender(con, tid)
    # MUDOU EM 14/10/2026, por decisão do oficial que é a letra da lei (Lei
    # 9.492, art. 27, § 2º; CN-MA arts. 944 e 948; Gentil, cap. 7, [p. 2693]):
    # suspensos os efeitos, a publicidade para — o protesto NÃO entra na
    # certidão comum. Até aqui este teste exigia o contrário («o protesto não
    # pode sumir»). Com ordem judicial expressa, ele entra, com a nota.
    # E DESDE 21/10/2026 (LH13, CNN art. 263-K) isso vale para a decisão
    # DEFINITIVA, que é a de `suspender`; a provisória sai como sustação
    # precária — ver os testes do art. 263-K, abaixo.
    assert PC.buscar(con, documento="04785512388") == []
    achados = PC.buscar(con, documento="04785512388",
                        autorizacao="ORDEM_JUDICIAL")
    assert len(achados) == 1
    assert achados[0]["efeitos_suspensos"] is True
    assert achados[0]["suspensao_juizo"] == JUIZO
    assert achados[0]["suspensao_processo"] == PROCESSO


def test_revogada_a_suspensao_o_protesto_volta_a_publicar():
    import protesto_certidao as PC
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid)
    PT.lancar_revogacao_efeito_suspensivo(con, tid, agora=AGORA)
    assert PT.efeito_suspensivo_em_vigor(con, tid) is None
    assert PC.buscar(con, documento="04785512388")[0][
        "efeitos_suspensos"] is False


def test_os_dois_institutos_nao_se_confundem():
    """Sustar e suspender são coisas diferentes, e a leitura de um não pode
    responder pelo outro."""
    con = banco()
    tid = titulo(con)
    sustar(con, tid)
    assert PT.sustacao_em_vigor(con, tid) is not None
    assert PT.efeito_suspensivo_em_vigor(con, tid) is None


def test_nao_se_suspende_duas_vezes():
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid)
    with pytest.raises(PT.ProtestoError, match="já estão suspensos"):
        suspender(con, tid)


def test_os_dois_pares_de_ordem_e_revogacao_estao_declarados():
    assert PT.ORDEM_JUDICIAL_E_A_REVOGACAO == {
        "SUSTACAO": "REVOGACAO_SUSTACAO",
        "EFEITO_SUSPENSIVO": "REVOGACAO_EFEITO_SUSPENSIVO"}


# ------------------------------------------------ CNN art. 263-K (LH13)
#
# O oficial, 21/10/2026 (pergunta 18, letra a): seguir o Código Nacional de
# Normas, art. 263-K (Prov. CN 253/2026), no lugar da sua decisão de 14/10 pelo
# CN-MA. A decisão PROVISÓRIA sai na certidão a terceiro como «CONSTA COM
# SUSTAÇÃO JUDICIAL PRECÁRIA»; a DEFINITIVA fica fora; a que manda emitir
# negativa cumpre-se nos limites; no segredo de justiça, só a sustação e o
# número do processo. A ordem lançada antes, sem a marca, fica como estava.

FECHO = ("Resultado emitido em cumprimento à decisão judicial — Processo nº "
         + PROCESSO + ".")


def _a_terceiro(con, **k):
    """O que a certidão pedida por terceiro (sem autorização) diz da MARIA."""
    import protesto_certidao as PC
    achados = PC.buscar(con, documento="04785512388", **k)
    teor = PC.montar_teor(tipo=PC.tipo_para(achados), nome="MARIA SANTOS",
                          documento="04785512388", achados=achados,
                          desde="2021-09-01", hoje=HOJE, con=con)
    return achados, teor


def test_a_ordem_nova_exige_o_carater_da_decisao():
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    for carater in (None, "", "LIMINAR"):
        with pytest.raises(PT.ProtestoError, match="caráter da decisão"):
            suspender(con, tid, carater=carater)
    assert PT.efeito_suspensivo_em_vigor(con, tid) is None


def test_a_decisao_provisoria_sai_na_certidao_como_sustacao_judicial_precaria():
    """CNN art. 263-K, III: os dados do registro, o número da ação, o caráter
    provisório e o fecho. A certidão é a POSITIVA — cobrada e selada como ela
    (não há item próprio na tabela)."""
    import protesto_certidao as PC
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid, carater="PROVISORIA")
    achados, teor = _a_terceiro(con)
    assert len(achados) == 1 and achados[0]["sustacao_precaria"] is True
    assert PC.tipo_para(achados) == "POSITIVA"
    for esperado in ("Título n. 84713/1", "protestado em 01/09/2026",
                     "CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA",
                     f"decisão judicial de caráter provisório ({JUIZO}), na ação "
                     f"n. {PROCESSO}", FECHO):
        assert esperado in teor, (esperado, teor)
    assert teor.rstrip().endswith(FECHO), teor
    assert "EFEITOS SUSPENSOS" not in teor


def test_a_decisao_definitiva_fica_fora_da_certidao():
    """CNN art. 263-K, I: «NADA CONSTA», inclusive quando a sustação veio de
    decisão judicial definitiva."""
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid, carater="DEFINITIVA")
    achados, teor = _a_terceiro(con)
    assert achados == [] and "NÃO ENCONTREI" in teor
    assert PROCESSO not in teor


def test_a_ordem_que_manda_emitir_negativa_se_cumpre_nos_exatos_limites():
    """CNN art. 263-K, § 1º: a decisão provisória que manda expressamente
    emitir negativa tira da certidão o protesto DELA — e só ele: o outro
    protesto da mesma pessoa continua na positiva."""
    con = banco()
    suspenso = titulo(con)
    protestar(con, suspenso)
    suspender(con, suspenso, carater="PROVISORIA", manda_negativa=True)
    _, teor = _a_terceiro(con)
    assert "NÃO ENCONTREI" in teor
    outro = titulo(con, numero="99999/2")
    protestar(con, outro)
    achados, teor = _a_terceiro(con)
    assert [a["numero_titulo"] for a in achados] == ["99999/2"]
    assert "84713/1" not in teor and "PRECÁRIA" not in teor and PROCESSO not in teor


def test_no_segredo_de_justica_a_certidao_diz_so_a_sustacao_e_o_processo():
    """CNN art. 263-K, § 1º: nada do título, do valor, do credor, do registro
    nem do juízo — a sustação, o número do processo e o fecho."""
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    suspender(con, tid, carater="PROVISORIA", segredo_de_justica=True)
    achados, teor = _a_terceiro(con)
    assert len(achados) == 1
    assert (f"1) CONSTA COM SUSTAÇÃO JUDICIAL PRECÁRIA, na ação n. {PROCESSO}."
            in teor), teor
    assert teor.rstrip().endswith(FECHO), teor
    for fora in ("84713/1", "1.482,78", "protestado em", "Livro", JUIZO):
        assert fora not in teor, (fora, teor)


def test_a_ordem_sem_marca_fica_fora_ate_alguem_marcar():
    """A ordem lançada antes de 21/10/2026 não tem a marca: o protesto fica
    fora da certidão, como ficava, e ela aparece em `ordens_sem_marca` para a
    tela avisar. Marcada provisória, a certidão seguinte já diz a sustação
    precária — e quem marcou e quando ficam no ato."""
    con = banco()
    tid = titulo(con)
    protestar(con, tid)
    ato = suspender(con, tid)["ato_id"]
    con.execute("UPDATE pt_atos SET ordem_carater = NULL, ordem_marcada_em = NULL,"
                " ordem_marcada_por = NULL WHERE id = ?", (ato,))
    assert _a_terceiro(con)[0] == []
    assert [o["ato_id"] for o in PT.ordens_sem_marca(con)] == [ato]

    PT.marcar_ordem_judicial(con, ato, carater="PROVISORIA",
                             agora="2026-10-21T10:00:00", usuario="escrevente")
    achados, teor = _a_terceiro(con)
    assert achados[0]["sustacao_precaria"] and FECHO in teor
    assert PT.ordens_sem_marca(con) == []
    ordem = PT.efeito_suspensivo_em_vigor(con, tid)
    assert (ordem["ordem_marcada_por"], ordem["ordem_marcada_em"]) == (
        "escrevente", "2026-10-21T10:00:00")
    # o juízo e o processo do ato não se reescrevem
    assert (ordem["juizo"], ordem["processo"]) == (JUIZO, PROCESSO)


def test_a_ordem_revogada_ou_de_protesto_cancelado_nao_pede_marca():
    """A lista das ordens a marcar é só das que VALEM sobre protesto em pé: a
    revogada e a do protesto cancelado não mudam certidão nenhuma."""
    con = banco()
    revogada = titulo(con)
    protestar(con, revogada)
    a = suspender(con, revogada)["ato_id"]
    PT.lancar_revogacao_efeito_suspensivo(con, revogada, agora=AGORA)
    cancelado = titulo(con, numero="77777/3")
    protestar(con, cancelado)
    b = suspender(con, cancelado)["ato_id"]
    PT.lancar_cancelamento(con, cancelado, hipotese="ORDEM_JUDICIAL",
                           fundamento="Sentença que mandou cancelar.", agora=AGORA)
    con.execute("UPDATE pt_atos SET ordem_carater = NULL WHERE id IN (?, ?)", (a, b))
    assert PT.ordens_sem_marca(con) == []


def test_so_a_ordem_de_efeito_suspensivo_leva_a_marca():
    """A sustação chega antes do protesto, e título sem protesto lavrado não
    entra em certidão nenhuma: marcá-la não mudaria nada."""
    con = banco()
    tid = titulo(con)
    ato = sustar(con, tid)["ato_id"]
    with pytest.raises(PT.ProtestoError, match="art. 263-K"):
        PT.marcar_ordem_judicial(con, ato, carater="PROVISORIA", agora=AGORA)
