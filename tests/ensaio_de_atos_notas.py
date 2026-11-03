"""Os casos do ensaio de atos das Notas e a prática de cada um pelas telas.

O teste e a régua da lei estão em `test_ensaio_de_atos_notas.py`; o inventário e o relatório em
`docs/ensaio_de_atos/`. Os passos de balcão (protocolo pago, abrir o ato, ligar ao protocolo, preencher
pela minuta, lançar no livro, o termo, o traslado e a certidão) são os de `test_fluxo_notas`, que já
leva cada minuta de fábrica do protocolo à certidão com duas pessoas solteiras e maiores. Aqui o que
varia é QUEM COMPARECE e A SITUAÇÃO que a lei distingue: o casado e o cônjuge que consente, o
procurador, o menor e quem o representa, a pessoa jurídica, quem não sabe assinar, o testador cego.

Os nomes e os números são fictícios, como em todo teste desta casa: os CPF e o CNPJ começam com zeros
e só têm os dígitos verificadores certos.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date

import test_fluxo_notas as F


def _dv(base: str, pesos: list[int]) -> str:
    resto = sum(int(d) * p for d, p in zip(base, pesos)) % 11
    return "0" if resto < 2 else str(11 - resto)


def cpf(n: int) -> str:
    base = f"{n:09d}"
    base += _dv(base, list(range(10, 1, -1)))
    base += _dv(base, list(range(11, 1, -1)))
    return f"{base[:3]}.{base[3:6]}.{base[6:9]}-{base[9:]}"


def cnpj(n: int) -> str:
    base = f"{n:08d}0001"
    base += _dv(base, [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    base += _dv(base, [6, 5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2])
    return f"{base[:2]}.{base[2:5]}.{base[5:8]}/{base[8:12]}-{base[12:]}"


@dataclass
class Parte:
    nome: str
    qualificacao: str
    documento: str
    testemunha: bool = False
    civil: dict = field(default_factory=dict)       # troca o que `F.QUALIFICACAO_DA_PESSOA` diz
    representa: str = ""                             # o nome da parte que esta representa ou assiste
    instrumento: str = ""                            # o instrumento da representação (item 2)


@dataclass
class Caso:
    chave: str
    minuta: str
    tipo: str
    titulo: str
    partes: list[Parte]
    item: str = "13.2"
    valor: int | None = None                         # em centavos; a faixa da tabela 3 vem dele
    especie: str | None = None                       # a espécie da procuração
    clausulas: tuple[str, ...] = ()                  # as cláusulas «SE» ligadas, pela chave do campo
    escolhas: dict = field(default_factory=dict)     # escolha -> trecho da opção
    valores: dict = field(default_factory=dict)      # campo -> o que o escrevente digita
    certidao_por: str = ""                           # quem pede a certidão (vazio: a primeira parte)
    doi_operacao: str = ""                           # a operação da DOI (11 compra e venda, 67 doação)


@dataclass
class Saida:
    caso: Caso
    ato_id: int | None = None
    situacao: str = ""
    termo: str = ""
    traslado: str = ""
    certidao: str = ""
    teor: str = ""
    avisos: list[str] = field(default_factory=list)
    censec: tuple = ()                               # (central, PRONTO/PARADO/FORA, o que falta)
    doi: dict = field(default_factory=dict)          # alienantes, adquirentes e o que impede


# ------------------------------------------------------------------ as pessoas do ensaio

_MULHERES = ("JOANA", "BEATRIZ", "ANA", "LUCIA")


def _pessoa(nome: str, qualificacao: str, n: int, representa: str = "", instrumento: str = "",
            **civil) -> Parte:
    """A pessoa como o escrevente a digita: nacionalidade e estado civil concordam com ela."""
    mulher = nome.split()[0] in _MULHERES
    base = {"nacionalidade": "brasileira" if mulher else "brasileiro",
            "estado_civil": "solteira" if mulher else "solteiro",
            "profissao": "comerciante"}
    return Parte(nome, qualificacao, cpf(n), civil=base | civil, representa=representa,
                 instrumento=instrumento)


PROCURACAO_DO_VENDEDOR = ("procuração lavrada no livro 10, folha 20, do Tabelionato de Notas de "
                          "Cidade Exemplo")
ASSENTO_DO_MENOR = ("certidão de nascimento lavrada no livro A-1, folha 1, termo 1, do Registro Civil "
                    "de Cidade Exemplo")


CASADO = {"estado_civil": "casado", "conjuge": "JOANA EXEMPLO DOS SANTOS",
          "regime_bens": "comunhão parcial de bens"}
CASADA = {"estado_civil": "casada", "conjuge": "MARIO EXEMPLO DOS SANTOS",
          "regime_bens": "comunhão parcial de bens"}
VENDEDOR = _pessoa("MARIO EXEMPLO DOS SANTOS", "VENDEDOR", 1, **CASADO)
CONJUGE_QUE_CONSENTE = _pessoa("JOANA EXEMPLO DOS SANTOS", "ANUENTE", 2, **CASADA)
# O padrão da casa no imóvel do casal em comunhão: os dois vendem (decisão do oficial, 03/11/2026).
CONJUGE_QUE_VENDE = _pessoa("JOANA EXEMPLO DOS SANTOS", "VENDEDORA", 2, **CASADA)
COMPRADORA = _pessoa("BEATRIZ EXEMPLO DE SOUZA", "COMPRADORA", 3)
TESTEMUNHAS = [Parte("PAULO EXEMPLO TESTEMUNHA", "TESTEMUNHA", cpf(4), testemunha=True,
                     civil={"nacionalidade": "brasileiro", "estado_civil": "solteiro"}),
               Parte("LUCIA EXEMPLO TESTEMUNHA", "TESTEMUNHA", cpf(5), testemunha=True)]
CEM_MIL = 10_000_000


def _nascido_ha(anos: int) -> str:
    """A data de nascimento de quem completou `anos` há um mês, como o escrevente a escreve."""
    hoje = date.today()
    mes = hoje.month - 1 or 12
    ano = hoje.year - anos - (1 if hoje.month == 1 else 0)
    return f"{1:02d}/{mes:02d}/{ano} (primeiro de um mês de {ano})"


def casos() -> list[Caso]:
    return [
        # ---- compra e venda: o que mais cai no balcão
        Caso("cv_casado_com_outorga", "NT-ESC-COMPRA-VENDA", "ESCRITURA",
             "Compra e venda — o imóvel do casal em comunhão: os dois cônjuges vendem "
             "(CC art. 215, § 1º, III; o padrão da casa)",
             [VENDEDOR, CONJUGE_QUE_VENDE, COMPRADORA], item="FAIXA", valor=CEM_MIL,
             escolhas={"op_forma_de_pagamento": "PIX"}, doi_operacao="11"),
        Caso("cv_bem_particular_com_anuente", "NT-ESC-COMPRA-VENDA", "ESCRITURA",
             "Compra e venda — bem particular do vendedor casado, com o cônjuge anuente (CC art. 1.647, I)",
             [VENDEDOR, CONJUGE_QUE_CONSENTE, COMPRADORA], item="FAIXA", valor=CEM_MIL, doi_operacao="11"),
        Caso("cv_por_procurador", "NT-ESC-COMPRA-VENDA", "ESCRITURA",
             "Compra e venda — vendedor representado por procurador (CN-MA art. 798, VI)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "VENDEDOR", 1),
              _pessoa("CARLOS EXEMPLO PROCURADOR", "PROCURADOR", 6, representa="MARIO EXEMPLO DOS SANTOS",
                      instrumento=PROCURACAO_DO_VENDEDOR),
              COMPRADORA], item="FAIXA", valor=CEM_MIL,
             valores={"assinantes_do_ato_e_a_condicao_em_que_assinam":
                      "CARLOS EXEMPLO PROCURADOR, procurador do outorgante vendedor, nos termos da procuração "
                      "lavrada no Livro 10, folha 20, do Tabelionato de Notas de Cidade Exemplo; e a "
                      "outorgada compradora"}, doi_operacao="11"),
        Caso("cv_pj_compradora", "NT-ESC-COMPRA-VENDA", "ESCRITURA",
             "Compra e venda — a compradora é pessoa jurídica (qualificação da PJ)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "VENDEDOR", 1),
              Parte("EXEMPLO COMERCIO DE MATERIAIS LTDA", "COMPRADORA", cnpj(7),
                    civil={"tipo_pessoa": "J", "nacionalidade": "", "estado_civil": "", "profissao": "",
                           "identidade": "", "uniao_estavel": ""}),
              _pessoa("ANA EXEMPLO SOCIA", "REPRESENTANTE", 8, representa="EXEMPLO COMERCIO DE MATERIAIS LTDA",
                      instrumento="contrato social arquivado na Junta Comercial do Maranhão")],
             item="FAIXA", valor=CEM_MIL, doi_operacao="11"),
        # ---- doação a menor
        Caso("doacao_a_menor", "NT-ESC-DOACAO", "ESCRITURA",
             "Doação a menor, que aceita representado pela mãe (CN-MA art. 798, VII; CC art. 543)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "DOADOR", 1),
              _pessoa("PEDRO EXEMPLO MENOR", "DONATARIO", 9,
                      profissao="estudante"),
              _pessoa("JOANA EXEMPLO DOS SANTOS", "REPRESENTANTE", 2, representa="PEDRO EXEMPLO MENOR",
                      instrumento=ASSENTO_DO_MENOR)],
             item="FAIXA", valor=CEM_MIL, doi_operacao="67"),
        Caso("doacao_doadora_a_donataria", "NT-ESC-DOACAO", "ESCRITURA",
             "Doação — a doadora e a donatária (o feminino da qualificação)",
             [_pessoa("JOANA EXEMPLO DOS SANTOS", "DOADORA", 2),
              _pessoa("BEATRIZ EXEMPLO DE SOUZA", "DONATARIA", 3)],
             item="FAIXA", valor=CEM_MIL, doi_operacao="67"),
        # ---- procurações
        Caso("proc_a_rogo", "NT-PROC-PUBLICA", "PROCURACAO",
             "Procuração — outorgante que não sabe assinar, com assinatura a rogo (CC art. 215, § 2º)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "OUTORGANTE", 1),
              _pessoa("BEATRIZ EXEMPLO DE SOUZA", "OUTORGADA", 3),
              _pessoa("PAULO EXEMPLO TESTEMUNHA", "ASSINA A ROGO", 4, representa="MARIO EXEMPLO DOS SANTOS")],
             item="13.9.3", especie="PODERES_ESPECIFICOS",
             valores={"assinantes_do_ato_e_a_condicao_em_que_assinam":
                      "PAULO EXEMPLO TESTEMUNHA, a rogo do outorgante, que não sabe assinar, e apôs a sua "
                      "impressão digital"}),
        Caso("proc_alienar_imovel", "NT-PROC-PUBLICA", "PROCURACAO",
             "Procuração com poderes para alienar imóvel (CC art. 661, § 1º; CN-MA art. 833)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "OUTORGANTE", 1, **CASADO), CONJUGE_QUE_CONSENTE,
              _pessoa("CARLOS EXEMPLO PROCURADOR", "OUTORGADO", 6)],
             item="13.9.3", especie="VENDA",
             clausulas=("se_se_poderes_especiais", "se_se_poderes_sobre_imovel")),
        Caso("revogacao_da_procuracao", "NT-REVOGACAO-MANDATO", "REVOGACAO",
             "Revogação da procuração lavrada nesta serventia (CN-MA art. 831)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "OUTORGANTE", 1, **CASADO),
              _pessoa("CARLOS EXEMPLO PROCURADOR", "OUTORGADO", 6)],
             item="13.9.3", especie="PODERES_ESPECIFICOS"),
        # ---- testamentos
        Caso("testamento_nao_assina", "NT-TESTAMENTO-PUBLICO", "TESTAMENTO",
             "Testamento público — testador que não sabe assinar (CC art. 1.865)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "TESTADOR", 1, estado_civil="solteiro"), *TESTEMUNHAS],
             item="13.10.1", clausulas=("se_se_testador_nao_assina",),
             escolhas={"op_estado_civil_do_testador": "solteiro", "op_motivo": "sabe"},
             valores={"nome_da_testemunha_que_assina_a_rogo": "PAULO EXEMPLO TESTEMUNHA"}),
        Caso("testamento_cego", "NT-TESTAMENTO-PUBLICO", "TESTAMENTO",
             "Testamento público — testador cego, lido duas vezes (CC art. 1.867)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "TESTADOR", 1, estado_civil="solteiro"), *TESTEMUNHAS],
             item="13.10.1", clausulas=("se_se_testador_cego",),
             escolhas={"op_estado_civil_do_testador": "solteiro"},
             valores={"nome_da_testemunha_designada_pelo_testador": "LUCIA EXEMPLO TESTEMUNHA"}),
        Caso("testamento_casado_marcado_solteiro", "NT-TESTAMENTO-PUBLICO", "TESTAMENTO",
             "Testamento público — a parte é casada e a escolha da minuta diz «solteiro»",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "TESTADOR", 1, **CASADO), *TESTEMUNHAS],
             item="13.10.1", escolhas={"op_estado_civil_do_testador": "solteiro"},
             # o cônjuge e o regime em branco na tela: vêm da parte
             valores={"nome_e_qualificacao_do_conjuge_ou_convivente": "", "regime_de_bens": ""}),
        # ---- família
        Caso("inventario_viuva_e_dois_herdeiros", "NT-ESC-INVENTARIO-PARTILHA", "ESCRITURA",
             "Inventário — viúva meeira e dois filhos, com advogado (CNN art. 441; CN-MA art. 812)",
             [_pessoa("JOANA EXEMPLO DOS SANTOS", "INVENTARIANTE", 2, estado_civil="viúva"),
              _pessoa("ANA EXEMPLO HERDEIRA", "HERDEIRA", 10),
              _pessoa("PEDRO EXEMPLO HERDEIRO", "HERDEIRO", 11, estado_civil="casado",
                      conjuge="BEATRIZ EXEMPLO DE SOUZA", regime_bens="comunhão parcial de bens"),
              _pessoa("CARLOS EXEMPLO ADVOGADO", "ADVOGADO", 6, oab_numero="00000", oab_uf="MA")],
             item="FAIXA", valor=CEM_MIL),
        Caso("divorcio_com_nome", "NT-ESC-DIVORCIO", "ESCRITURA",
             "Divórcio — sem filhos menores, a mulher volta a usar o nome de solteira (CN-MA arts. 821 e 822)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "DIVORCIANDO", 1, **CASADO),
              _pessoa("JOANA EXEMPLO DOS SANTOS", "DIVORCIANDA", 2, **CASADA),
              _pessoa("CARLOS EXEMPLO ADVOGADO", "ADVOGADO", 6, oab_numero="00000", oab_uf="MA")], valor=0,
             escolhas={"op_nome": "voltará"},
             valores={"nome_de_quem_altera": "JOANA EXEMPLO DOS SANTOS"}),
        Caso("uniao_estavel_separacao", "NT-ESC-UNIAO-ESTAVEL", "ESCRITURA",
             "União estável — com o regime da separação de bens (CC art. 1.725)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "DECLARANTE", 1, uniao_estavel="SIM"),
              _pessoa("JOANA EXEMPLO DOS SANTOS", "DECLARANTE", 2, uniao_estavel="SIM")], valor=0),
        Caso("emancipacao_so_mae", "NT-ESC-EMANCIPACAO", "ESCRITURA",
             "Emancipação — só a mãe concede, pai falecido (CC art. 5º, par. ún., I)",
             [_pessoa("JOANA EXEMPLO DOS SANTOS", "OUTORGANTE", 2, estado_civil="viúva"),
              _pessoa("PEDRO EXEMPLO MENOR", "OUTORGADO", 9, profissao="estudante")],
             valor=0, clausulas=("se_se_um_dos_pais",), escolhas={"op_filiacao": "a mãe"},
             valores={"data_de_nascimento_do_emancipando": _nascido_ha(17)}),
        Caso("emancipacao_menor_de_16", "NT-ESC-EMANCIPACAO", "ESCRITURA",
             "Emancipação — o emancipando tem quinze anos (CC art. 5º, par. ún., I)",
             [_pessoa("JOANA EXEMPLO DOS SANTOS", "OUTORGANTE", 2, estado_civil="viúva"),
              _pessoa("PEDRO EXEMPLO MENOR", "OUTORGADO", 9, profissao="estudante")],
             valor=0, clausulas=("se_se_um_dos_pais",), escolhas={"op_filiacao": "a mãe"},
             valores={"data_de_nascimento_do_emancipando": _nascido_ha(15)}),
        Caso("pacto_nubente_menor", "NT-ESC-PACTO-ANTENUPCIAL", "ESCRITURA",
             "Pacto antenupcial — nubente de 17 anos, com o assistente (CC art. 1.654)",
             [_pessoa("MARIO EXEMPLO DOS SANTOS", "OUTORGANTE", 1),
              _pessoa("ANA EXEMPLO NUBENTE", "OUTORGANTE", 10),
              _pessoa("JOANA EXEMPLO DOS SANTOS", "ASSISTENTE", 2, representa="ANA EXEMPLO NUBENTE",
                      instrumento=ASSENTO_DO_MENOR)], valor=0),
    ]


# ------------------------------------------------------------------ a prática

def _incluir(b, ato_id: int, p: Parte) -> str:
    dados = {"acao": "parte_nova", "nome": p.nome, "documento": p.documento, "qualificacao": p.qualificacao,
             **F.QUALIFICACAO_DA_PESSOA, **p.civil}
    if p.testemunha:
        dados["testemunha"] = "1"
    if p.representa:
        alvo = F._um(b, "SELECT id FROM nt_ato_partes WHERE ato_id=%s AND nome=%s", (ato_id, p.representa))
        dados |= {"representa_parte_id": str(alvo["id"]), "representa_instrumento": p.instrumento}
    html = F._postar(b, f"/notas/atos/{ato_id}", dados).get_data(as_text=True)
    recado = " · ".join(F._flashes(html))
    return "" if "Parte incluída" in recado else f"parte {p.nome} recusada: {recado}"


def _preencher(b, ato_id: int, caso: Caso) -> str:
    from datetime import datetime

    import notas_teor as NT
    from ri_modelos_atos import campos_do_modelo
    corpo = F._um(b, "SELECT corpo FROM nt_modelos WHERE codigo = %s", (caso.minuta,))["corpo"]
    hoje = NT.valores_campos_data_lavratura(datetime.now())
    valores = {}
    for campo in campos_do_modelo({"corpo": corpo}):
        chave = campo["chave"]
        if campo["tipo"] == "condicao":
            if chave in caso.clausulas:
                valores[chave] = "1"
        elif campo["tipo"] == "escolha":
            querida = caso.escolhas.get(chave)
            valores[chave] = next((o for o in campo["opcoes"] if querida and querida in o), campo["opcoes"][0])
        elif chave in caso.valores:
            valores[chave] = caso.valores[chave]
        elif chave != NT.CHAVE_ASSINANTES:
            valores[chave] = F._valor_de_exemplo(campo, hoje)
    html = F._postar(b, f"/notas/atos/{ato_id}/preencher", valores,
                     de=f"/notas/atos/{ato_id}").get_data(as_text=True)
    return " · ".join(F._flashes(html))


def praticar(b, caso: Caso, *, anterior_id: int | None = None) -> Saida:
    """O caso do protocolo à certidão. `anterior_id`: o ato desta serventia que este revoga ou
    substabelece, vinculado pela tela («Vincular») antes do lançamento."""
    saida = Saida(caso)
    protocolo = F.abrir_protocolo_pago(b, [(caso.item, 1), ("13.12.1", 1)], interessado=caso.partes[0].nome,
                                       base_da_faixa=caso.valor)
    ato_id = F.abrir_o_ato(b, caso.minuta, interessado=caso.partes[0].nome)
    saida.ato_id = ato_id
    F.ligar_ao_protocolo(b, ato_id, protocolo)
    for p in caso.partes:
        if recusa := _incluir(b, ato_id, p):
            saida.avisos.append(recusa)
    if caso.valor is not None:
        F._postar(b, f"/notas/escrituras/{ato_id}/valor", {"valor": str(caso.valor)}, de=f"/notas/atos/{ato_id}")
    import notas_arquivamento as NARQ
    if NARQ.arquivamento_obrigatorio(caso.tipo):
        F.arquivar_o_documento(b, ato_id, protocolo)
    saida.avisos.append(f"preencher: {_preencher(b, ato_id, caso)}")
    if anterior_id:
        html = F._postar(b, f"/notas/atos/{ato_id}", {"acao": "vincular_anterior",
                                                     "anterior_id": str(anterior_id)}).get_data(as_text=True)
        saida.avisos.append(f"vincular: {' · '.join(F._flashes(html))}")
    item = protocolo["itens"][0]["codigo_ato"] if caso.item == "FAIXA" else caso.item
    saida.avisos.append(f"lançar: {F.lancar_no_livro(b, ato_id, item=item, especie=caso.especie)}")
    a = F.ato(b, ato_id)
    saida.situacao = a["situacao"]
    saida.teor = F._so_texto(a.get("teor") or "")
    if saida.situacao != "LAVRADO":
        return saida
    saida.termo = F._texto_do_odt(F.o_termo_do_livro(b, ato_id))
    saida.traslado = F._texto_do_odt(F.o_traslado(b, ato_id))
    saida.censec = _censec(b, ato_id)
    if caso.doi_operacao:
        saida.doi = _doi(b, ato_id, caso.doi_operacao)
    quem = caso.certidao_por or caso.partes[0].nome
    pedido = {"ato_id": ato_id, "requerente": quem}
    if caso.tipo in ("TESTAMENTO", "TESTAMENTO_CERRADO"):
        pedido |= {"requerente_documento": caso.partes[0].documento, "requerimento_escrito": "1"}
    try:
        cid = F.emitir_certidao(b, protocolo=protocolo, **pedido)
        saida.certidao = F._texto_do_odt(F.o_papel_da_certidao(b, cid))
    except AssertionError as recusa:
        saida.avisos.append(f"certidão: {str(recusa).splitlines()[0]}")
    return saida


# ------------------------------------------------------------------ a segunda leva: CENSEC e DOI
#
# O ato lavrado vai à central da CENSEC pela fila de remessas, e a escritura com imóvel à DOI, pela
# tela única da serventia. O ensaio olha as duas telas como o balcão olha: a da quinzena do ato, e a da
# competência dele.

def _censec(b, ato_id: int) -> tuple:
    """(central, PRONTO ou PARADO, o que falta) — ou (None, FORA, "") se nenhuma o tem."""
    from datetime import date
    hoje = date.today()
    quinzena = 1 if hoje.day <= 15 else 2
    for central in ("CEP", "CESDI", "RCTO"):
        html = F._tela(b, f"/notas/remessas/{central}/pendencias?ano={hoje.year}&mes={hoje.month}"
                          f"&quinzena={quinzena}")
        parados, _, prontos = html.partition("Prontos para ir")
        ligacao = f'/notas/atos/{ato_id}"'
        if ligacao in parados:
            linha = parados.split(ligacao, 1)[1].split("</tr>", 1)[0]
            return central, "PARADO", F._so_texto(linha)
        if ligacao in prontos:
            return central, "PRONTO", ""
    return None, "FORA", ""


def _doi(b, ato_id: int, operacao: str) -> dict:
    """Os dados do imóvel pela ficha do ato e a declaração que a tela da DOI monta dele."""
    from datetime import date

    import notas_doi as NDOI
    html = F._tela(b, f"/notas/atos/{ato_id}")
    dados = {"acao": "imovel", "com_imovel": "1", "doi_transacao": operacao, "doi_tipo_imovel": "67",
             "doi_matricula": "4010", "doi_endereco": "RUA EXEMPLO, 10", "doi_area": "360"}
    for parte_id, valor in re.findall(r'name="participacao_(\d+)"[^>]*value="([^"]*)"', html):
        dados[f"participacao_{parte_id}"] = valor
    F._postar(b, f"/notas/atos/{ato_id}", dados)
    vistos = []
    montar = NDOI.declaracao_da_escritura

    def guardar(ato, partes, *args, **kw):
        reg, problemas = montar(ato, partes, *args, **kw)
        if dict(ato).get("id") == ato_id:
            vistos.append({"partes": [dict(p) for p in partes], "reg": reg, "problemas": problemas})
        return reg, problemas
    NDOI.declaracao_da_escritura = guardar
    try:
        r = b["oficial"].get(f"/registro-imoveis/doi?competencia={date.today():%Y-%m}")
    finally:
        NDOI.declaracao_da_escritura = montar
    if not vistos:
        return {"erro": f"a tela da DOI (HTTP {r.status_code}) não montou a declaração do ato"}
    visto = vistos[-1]
    alienantes, adquirentes, duvidas = NDOI.lados_das_partes(
        [p for p in visto["partes"] if not p.get("testemunha")])
    return {"alienantes": [p["nome"] for p in alienantes], "adquirentes": [p["nome"] for p in adquirentes],
            "duvidas": [p["nome"] for p in duvidas],
            "problemas": [str(getattr(x, "motivo", x)) for x in (visto["problemas"] or [])]}


def em_texto(s: Saida) -> str:
    """O caso inteiro para ler (`CG_ENSAIO_SAIDA=1`)."""
    return "\n\n".join([f"# {s.caso.chave} — {s.caso.titulo}", f"situação: {s.situacao}",
                        "avisos:\n" + "\n".join(s.avisos), "TERMO:\n" + s.termo, "TRASLADO:\n" + s.traslado,
                        "CERTIDÃO:\n" + s.certidao, f"CENSEC: {s.censec}", f"DOI: {s.doi}"])


def tem(texto: str, *trechos: str) -> bool:
    """Todos os trechos, sem olhar caixa nem espaço."""
    plano = re.sub(r"\s+", " ", texto).lower()
    return all(re.sub(r"\s+", " ", t).lower() in plano for t in trechos)
