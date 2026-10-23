"""Os livros que o Código de Normas do MA manda ter — e onde cada um está aqui.

POR QUE EXISTE (LG08, 19/10/2026)
    A pergunta da correição é sempre a mesma: «quais livros a serventia tem,
    e onde estão?». Até aqui a resposta estava espalhada em seis módulos, e
    ninguém sabia dizer o que FALTAVA. Medido no código em 19/10/2026: dos
    três livros administrativos que o art. 188 exige de TODA serventia, o
    sistema não tinha nenhum como livro — o Livro de Visitas e Correições não
    existia (a tela «Inspeções» é o plano de ação de um relatório, e não o
    registro das visitas), o Diário Auxiliar não existia (não havia sequer
    tabela de despesas: `gestor_financeiro` diz isso na própria docstring) e o
    depósito prévio era um cadastro de saldo, sem a data da conversão nem a da
    devolução que o art. 198 pede.

    Este módulo é a régua: cada livro, o artigo que o manda ter, e o lugar do
    sistema que o atende — ou a frase dizendo que NÃO atende. Não toca no
    banco. O teste confere cada série citada contra `livro_nucleo.SERIES` e
    cada tela contra as rotas do app: catálogo que aponta para o que não
    existe é pior do que catálogo nenhum.

A FONTE
    Código de Normas da Corregedoria Geral do Foro Extrajudicial do Maranhão,
    Provimento COGEX nº 28, de 23/04/2026, na versão recebida por malote em
    27/05/2026 (`referencia/codigo_de_normas_extrajudicial_ma.txt`, texto do
    PDF ao lado). Cada artigo abaixo foi LIDO nesse texto. Alteração posterior
    a 27/05/2026 pode faltar — por isso cada linha cita o artigo, e não um
    resumo.

O QUE A SITUAÇÃO QUER DIZER
    TEM          o livro existe no sistema, na tela indicada;
    PARCIAL      existe, mas falta coluna ou controle que o artigo pede — a
                 nota diz qual;
    FALTA        não existe; a nota diz o que seria preciso;
    FACULTATIVO  o artigo permite, não manda;
    A_CONFERIR   depende de fato da serventia que o código não sabe (a nota
                 diz qual).
"""
from __future__ import annotations

TEM, PARCIAL, FALTA, FACULTATIVO, A_CONFERIR = (
    "TEM", "PARCIAL", "FALTA", "FACULTATIVO", "A_CONFERIR")

SITUACOES: dict[str, str] = {
    TEM: "Tem",
    PARCIAL: "Tem, com falta",
    FALTA: "Falta",
    FACULTATIVO: "Facultativo",
    A_CONFERIR: "A conferir",
}

FONTE = ("Código de Normas do Foro Extrajudicial do MA — Provimento COGEX nº 28, "
         "de 23/04/2026 (versão do malote de 27/05/2026)")

# A ordem dos grupos é a do Código: a Parte Geral (livros de toda serventia)
# e depois a Parte Especial, capítulo a capítulo.
GRUPOS: tuple[tuple[str, str], ...] = (
    ("TODAS", "Toda serventia — livros administrativos (arts. 188 a 208)"),
    ("NOTAS", "Tabelionato de Notas (arts. 788 a 797)"),
    ("PROTESTO", "Tabelionato de Protesto (arts. 893 a 898)"),
    ("RCPN", "Registro Civil das Pessoas Naturais (arts. 210 a 216)"),
    ("RCPJ", "Registro Civil das Pessoas Jurídicas (arts. 403 a 406)"),
    ("RTD", "Registro de Títulos e Documentos (arts. 963 a 965)"),
    ("RI", "Registro de Imóveis (art. 424)"),
)


def _livro(grupo: str, chave: str, nome: str, artigo: str, situacao: str, *,
           series: tuple[str, ...] = (), rotas: tuple[str, ...] = (),
           nota: str = "") -> dict:
    return {"grupo": grupo, "chave": chave, "nome": nome, "artigo": artigo,
            "situacao": situacao, "series": series, "rotas": rotas, "nota": nota}


LIVROS: tuple[dict, ...] = (
    # ------------------------------------------------ toda serventia
    _livro("TODAS", "ADM_VISITAS", "Livro de Visitas e Correições",
           "art. 188, I; art. 189", TEM, rotas=("livro_visitas",),
           nota="Escriturado eletronicamente, sob a guarda do delegatário "
                "(art. 189). Nasceu no LG08. O § 1º o dispensa se as visitas "
                "estiverem registradas em sistema próprio da Corregedoria."),
    _livro("TODAS", "ADM_DIARIO", "Livro Diário Auxiliar da Receita e da Despesa",
           "art. 188, II; arts. 190 a 207", PARCIAL, rotas=("livro_diario",),
           nota="Nasceu no LG08: receita por ato a partir do SELO (data de uso, "
                "código do ato, selo, tipo normal/isento, emolumentos e fundos), "
                "despesas lançadas aqui, totais diários e acumulados, "
                "demonstrativo mensal e geração mensal travada (arts. 205 e "
                "206). FALTA no sistema: ISSQN por ato (não há coluna; art. 190, "
                "I, l), livro e folha do ato no lançamento (I, g), base legal "
                "(I, h), ressarcimento de gratuitos, renda mínima e serviços "
                "autorizados (III, b a d; art. 192), e os espaços de intervenção, "
                "interinidade e imposto de renda (V a VII)."),
    _livro("TODAS", "ADM_DEPOSITO", "Livro de Controle de Depósito Prévio",
           "art. 188, III; arts. 195 a 202", PARCIAL,
           rotas=("livro_deposito_previo", "caixa_depositos"),
           nota="O depósito é cadastrado em Caixa → Depósito prévio; o livro "
                "(LG08) o lê na forma do art. 198. O cadastro NÃO grava, como "
                "coluna, a conversão em emolumentos com a identificação do ato "
                "(IV), a devolução com a justificativa (V) nem o orçamento "
                "completo (VI): o livro os tira do rastro (`audit_logs`) e diz, "
                "depósito a depósito, o que falta."),
    # ------------------------------------------------ notas
    _livro("NOTAS", "NT_NOTAS", "Livro de Notas (escrituras)", "art. 788, I", TEM,
           series=("NT_ESCRITURA",), rotas=("notas_livros",),
           nota="Numeração contínua por espécie, de um livro para o outro "
                "(art. 792): `nt_termos`, por série."),
    _livro("NOTAS", "NT_TESTAMENTOS", "Livro de Testamentos", "art. 788, II", TEM,
           series=("NT_TESTAMENTO", "NT_TESTAMENTO_CERRADO"), rotas=("notas_livros",),
           nota="O sistema tem DUAS séries: testamento público e auto de "
                "aprovação de testamento cerrado. O art. 788 fala de um livro "
                "só — conferir com o oficial se o cerrado vai no mesmo."),
    _livro("NOTAS", "NT_PROCURACOES", "Livro de Procurações", "art. 788, III", TEM,
           series=("NT_PROCURACAO",), rotas=("notas_livros",),
           nota="Revogação e renúncia de mandato são lavradas neste livro "
                "(`notas_livro.LIVRO_DO_ATO`)."),
    _livro("NOTAS", "NT_SUBSTABELECIMENTOS", "Livro de Substabelecimentos de Procuração",
           "art. 788, IV", TEM, series=("NT_SUBSTABELECIMENTO",), rotas=("notas_livros",)),
    _livro("NOTAS", "NT_ATAS", "Livro de Atas Notariais", "art. 788, V", TEM,
           series=("NT_ATA",), rotas=("notas_livros",)),
    _livro("NOTAS", "NT_CONCILIACAO", "Livros de Conciliações e Mediações e de "
           "Protocolo de Conciliações e Mediações", "art. 788, § 5º", FACULTATIVO,
           nota="Facultativos (Prov. 42/2023). O sistema não os tem. Não há "
                "livro de protocolo nem índice OBRIGATÓRIO no Tabelionato de "
                "Notas do MA."),
    # ------------------------------------------------ protesto
    _livro("PROTESTO", "PT_PROTOCOLO", "Livro de Protocolo", "art. 893, I; art. 894", TEM,
           series=("PT_PROTOCOLO", "PT_APONTAMENTO"), rotas=("protesto_livro",),
           nota="Escrituração diária com termo de encerramento do dia "
                "(art. 894, parágrafo único). O sistema tem também o Livro de "
                "Apontamento, que é o nome do E-Ofício — conferir se é o "
                "mesmo livro do art. 893, I."),
    _livro("PROTESTO", "PT_REGISTRO", "Livro de Registro de Protestos", "art. 893, II; art. 895",
           TEM, series=("PT_PROTESTO",)),
    _livro("PROTESTO", "PT_INDICES", "Livro de Índices", "art. 893, III; art. 896", FALTA,
           nota="Os dados existem (`pt_devedores`, `pt_titulos.apresentante_nome`, "
                "`pt_atos.livro_id/folha`), mas nenhuma tela os reúne na forma "
                "do art. 896: devedor com identificação, protestante, livro e "
                "folha do protesto, do cancelamento, da anulação ou do pagamento."),
    _livro("PROTESTO", "PT_PAGAMENTOS", "Livro de Registro de Pagamentos", "art. 893, IV", TEM,
           series=("PT_PAGAMENTO",), rotas=("protesto_livro",)),
    _livro("PROTESTO", "PT_DISTRIBUICAO", "Livro de Distribuição", "art. 893, V; art. 899",
           A_CONFERIR,
           nota="A distribuição só existe na comarca com MAIS DE UM tabelionato "
                "de protesto (art. 899). Conferir se é o caso desta comarca; "
                "o sistema não tem o livro."),
    _livro("PROTESTO", "PT_ADMINISTRATIVOS", "Visitas e Correições, Diário Auxiliar e "
           "Controle de Depósito Prévio", "art. 893, VI a VIII", TEM,
           rotas=("livro_visitas", "livro_diario", "livro_deposito_previo"),
           nota="Os três administrativos de toda serventia, repetidos no "
                "capítulo do Protesto: são os mesmos livros do art. 188."),
    # ------------------------------------------------ registro civil
    _livro("RCPN", "RC_LIVROS", "Livros A, B, B Auxiliar, C, C Auxiliar, D e E",
           "art. 210, I a VII", TEM,
           series=("RC_A", "RC_B", "RC_B_AUXILIAR", "RC_C", "RC_C_AUXILIAR",
                   "RC_D", "RC_E"),
           rotas=("nucleo_livros",),
           nota="O § 1º do art. 210 fala em Livro E «com duzentas (200) "
                "folhas»; a série RC_E declara 150, tiradas do livro físico do "
                "acervo — conferir com o oficial antes de abrir o próximo."),
    _livro("RCPN", "RC_INDICE", "Índice alfabético dos assentos, pelo prenome, em cada livro",
           "art. 214", FALTA, rotas=("rcpn_assentos",),
           nota="Pode ser em banco de dados (§ 1º). O sistema tem a busca por "
                "nome, mas não o índice por PRENOME por livro, nem o do "
                "C Auxiliar pelo nome do pai ou da mãe (§ 2º)."),
    # ------------------------------------------------ pessoas jurídicas
    _livro("RCPJ", "PJ_LIVROS", "Livros A e B", "art. 403 (Lei 6.015/1973)", TEM,
           series=("PJ_A", "PJ_B"), rotas=("nucleo_livros",)),
    _livro("RCPJ", "PJ_PROTOCOLO", "Livro de Protocolo, com 300 folhas", "art. 403", TEM,
           series=("PJ_PROTOCOLO",), rotas=("nucleo_encerramento_diario",)),
    _livro("RCPJ", "PJ_INDICES", "Índices cronológico e alfabético, com partes, "
           "intervenientes e cônjuges", "art. 404", FALTA, rotas=("rcpj_rtd_registros",),
           nota="O registro guarda só o requerente (`rg_registros`); não há "
                "tabela de partes, intervenientes nem cônjuges para o índice."),
    # ------------------------------------------------ títulos e documentos
    _livro("RTD", "TD_PROTOCOLO", "Livro A — Protocolo", "art. 963, I", TEM,
           series=("TD_PROTOCOLO",), rotas=("nucleo_encerramento_diario",)),
    _livro("RTD", "TD_REGISTRO", "Livro B — Registro", "art. 963, II", TEM,
           series=("TD_B",), rotas=("nucleo_livros",)),
    _livro("RTD", "TD_INSCRICAO", "Livro C — Inscrição", "art. 963, III e § 4º", TEM,
           series=("TD_C",),
           nota="Dispensado para quem adota sistema informatizado (§ 4º)."),
    _livro("RTD", "TD_INDICADOR", "Livro D — Indicador Pessoal", "art. 963, IV e § 5º", FALTA,
           nota="Recomenda-se sistema informatizado (§ 5º), mas o sistema não "
                "tem o indicador: só a busca pelo requerente."),
    # ------------------------------------------------ imóveis
    _livro("RI", "RI_PROTOCOLO", "Livro nº 1 — Protocolo", "art. 424, I", TEM,
           rotas=("ri_protocolo",)),
    _livro("RI", "RI_MATRICULA", "Livro nº 2 — Registro Geral", "art. 424, II", TEM,
           rotas=("ri_matriculas",)),
    _livro("RI", "RI_AUXILIAR", "Livro nº 3 — Registro Auxiliar", "art. 424, III", TEM,
           rotas=("livro3_registros",)),
    _livro("RI", "RI_INDICADOR_REAL", "Livro nº 4 — Indicador Real", "art. 424, IV", TEM,
           rotas=("ri_indicador_real",)),
    _livro("RI", "RI_INDICADOR_PESSOAL", "Livro nº 5 — Indicador Pessoal", "art. 424, V", TEM,
           rotas=("ri_indicador_pessoal",)),
    _livro("RI", "RI_ESTRANGEIROS", "Livro de Cadastro de Aquisições de Imóveis Rurais "
           "por Estrangeiros", "art. 424, VI (Lei 5.709/1971, art. 10)", FALTA,
           nota="Não há nada no sistema sobre aquisição por estrangeiro."),
)


def grupos() -> list[dict]:
    """Os livros por grupo, na ordem do Código. Só monta."""
    return [{"chave": chave, "titulo": titulo,
             "livros": [x for x in LIVROS if x["grupo"] == chave]}
            for chave, titulo in GRUPOS]


def contagem() -> dict[str, int]:
    """Quantos livros em cada situação — o resumo do alto da tela."""
    saida = {s: 0 for s in SITUACOES}
    for x in LIVROS:
        saida[x["situacao"]] += 1
    return saida
