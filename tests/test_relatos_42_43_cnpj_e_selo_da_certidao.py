"""Os relatos #42 e #43 do oficial, de 07/09/2026.

    #42  «precisa atualizar o cnpj da serventia no sistema e em todos os atos.
          cnpj certo é 00.000.020/0001-62»
    #43  «certidão não está emitindo selo automático — ainda aparece campo
          para inclusão manual do selo»

O QUE A MEDIÇÃO ACHOU, e nos dois casos era maior que o relato
    **#42 — o CNPJ estava ESCRITO NO CÓDIGO.** `serventia.PADRAO` trazia
    `00.000.042/0001-22`, e a produção **não tem linha em `settings`** — logo
    era esse padrão que valia. Ele sai no recibo, no orçamento e na recepção do
    caixa, no traslado das notas, na nota devolutiva do RCPJ/RTD, no teor da
    escritura, na certidão do RCPN e no cabeçalho de toda tela.

    **E os dois passam no verificador**: conferi os catorze dígitos de cada um
    com `ri_schema.valida_cpf_cnpj`. A conta não desempata — quem desempata é
    quem responde pela serventia.

    **#43 — faltavam TRÊS peças, e a primeira é a que assusta.**
    `ri_certidoes` **não estava em `ato_selado.TABELAS_DE_ATO`**, que é o mesmo
    defeito que fez uma certidão do RCPN **sumir depois de emitida**: o
    escrevente digitava o selo, via o aviso vermelho, e a certidão deixava de
    existir — porque a rota faz o que a casa manda (selo recusado derruba o
    lançamento) sobre uma premissa errada.

    As outras duas: não havia caminho mapeado — **e existe**,
    `/selo/imovel/certidao`, que esta casa usou **667 vezes** —, e a rota lia
    `selo_texto` do formulário sem nunca chamar o selador.
"""
from __future__ import annotations

import glob
import re
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import ato_selado as AS                                          # noqa: E402
import ri_schema as RIS                                          # noqa: E402
import serventia as SV                                           # noqa: E402
from ri_schema import so_digitos, valida_cpf_cnpj                # noqa: E402

SENHA = "Senha#12345"
CNPJ_CERTO = "00.000.020/0001-62"
CNPJ_ERRADO = "00.000.042/0001-22"


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    bd = cg_casa['db']
    bd.create_user("tabeliao", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "tabeliao", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "c": c, "banco": banco, "db": bd}


# ================================================================ #42


def test_o_cnpj_da_serventia_e_o_que_o_oficial_informou():
    # SANITIZACAO B0 (05/10/2026): o CNPJ real saiu de `serventia.PADRAO` e
    # mora em `settings` (migrado por tools/migrar_settings_serventia_b0.py).
    # A regua agora e: o codigo nao traz CNPJ nenhum, e o que estiver em
    # settings e o que vai para o papel.
    assert SV.PADRAO["serventia_cnpj"] == SV.PADRAO_GENERICO["serventia_cnpj"] == ""
    assert SV.PADRAO["serventia_cnpj"] != CNPJ_ERRADO
    assert SV.dados({"serventia_cnpj": CNPJ_CERTO})["serventia_cnpj"] == CNPJ_CERTO


def test_OS_DOIS_PASSAM_NO_VERIFICADOR_e_por_isso_a_conta_nao_decide():
    """**A conta não desempata, e é por isso que o relato importa.**

    Se o errado fosse inválido, um teste teria pego. Os dois são CNPJ bem
    formados — quem sabe qual é o desta serventia é quem responde por ela.
    """
    assert valida_cpf_cnpj(so_digitos(CNPJ_CERTO))
    assert valida_cpf_cnpj(so_digitos(CNPJ_ERRADO)), (
        "o antigo também era válido — a conta nunca acusaria a troca")


def test_o_cnpj_errado_NAO_sobrou_em_lugar_nenhum():
    """Ele saía em sete arquivos. Um esquecido continuaria imprimindo.

    **E ESTE VARREDOR BATEU NA MINHA PRÓPRIA PROSA na primeira versão** — pela
    décima vez neste projeto. O comentário de `serventia.py` **cita o CNPJ
    antigo** para explicar a correção, que é justamente o que este projeto
    manda fazer: «correção fica visível». Procurar a string no arquivo inteiro
    acusava a explicação.

    **A régua lê o CÓDIGO**: os `.py` pelos literais da árvore, sem comentário
    e sem docstring; os `.html` pelo texto, que ali não tem comentário Python.
    """
    # **DUAS REGRAS DA CASA SE ENCONTRAM AQUI, e a exceção se declara.**
    # «Correção fica visível» manda o comentário dizer o que estava escrito
    # antes; «o valor errado não sobra» manda varrer. Os dois arquivos abaixo
    # existem para NARRAR o que foi consertado — a nota do desenvolvimento é
    # prosa em string por construção, e o cadastro cita o antigo no comentário
    # da correção. Excluí-los é reconhecer que ali o número é *citação*, e não
    # valor; é a forma de `FORA_DA_VARREDURA` e de `DONOS_DO_PRAGMA`.
    NARRAM_A_CORRECAO = {"notas_do_desenvolvimento.py"}

    import ast
    sobrou = []
    for p in RAIZ.glob("*.py"):
        if p.name.startswith("test_") or p.name in NARRAM_A_CORRECAO:
            continue
        try:
            arvore = ast.parse(p.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        docs = set()
        for n in ast.walk(arvore):
            if isinstance(n, (ast.Module, ast.ClassDef, ast.FunctionDef,
                              ast.AsyncFunctionDef)) and n.body:
                pr = n.body[0]
                if (isinstance(pr, ast.Expr) and isinstance(pr.value, ast.Constant)
                        and isinstance(pr.value.value, str)):
                    docs.add(id(pr.value))
        for n in ast.walk(arvore):
            if (isinstance(n, ast.Constant) and isinstance(n.value, str)
                    and id(n) not in docs
                    and (CNPJ_ERRADO in n.value
                         or so_digitos(CNPJ_ERRADO) in n.value)):
                sobrou.append(p.name)
                break
    for p in (RAIZ / "templates").glob("*.html"):
        texto = p.read_text(encoding="utf-8", errors="replace")
        if CNPJ_ERRADO in texto or so_digitos(CNPJ_ERRADO) in texto:
            sobrou.append(p.name)
    assert not sobrou, f"o CNPJ antigo ficou em {sorted(set(sobrou))}"


def test_o_cnpj_chega_ao_papel_pela_MACRO_da_serventia(s):
    """Ele é lido de `serventia`, e não escrito em cada tela — por isso um
    lugar só decide os sete papéis.

    **E a régua é a MACRO, e não a página inicial** — defeito meu na primeira
    versão: eu pedia `/`, que não a inclui, e o teste ficava vermelho por
    olhar o lugar errado.
    """
    macro = (RAIZ / "templates" / "_serventia.html").read_text(encoding="utf-8")
    assert "sv.serventia_cnpj" in macro, (
        "a macro tem de LER a configuração, e não trazer o número escrito")
    from serventia import PADRAO
    # B0: nenhum CNPJ no codigo; o valor vem de settings pela macro.
    assert PADRAO["serventia_cnpj"] not in (CNPJ_CERTO, CNPJ_ERRADO)


# ================================================================ #43


def test_ri_certidoes_ESTA_REGISTRADA_como_tabela_de_ato():
    """**Tabela não registrada não dá erro de programação: dá ATO PERDIDO.**

    É o defeito que `rc_certidoes` teve: selo digitado à mão sobre tabela não
    registrada faz a rota desfazer o lançamento inteiro, e a certidão emitida
    deixa de existir.
    """
    assert "ri_certidoes" in AS.TABELAS_DE_ATO
    assert AS.COLUNA_DO_SELO.get("ri_certidoes") == "selo_texto", (
        "`ri_certidoes` guarda em `selo_texto`, como `ri_atos` — e não em `selo`")


def test_o_caminho_do_selo_e_o_que_a_casa_USOU():
    """667 selos por `/selo/imovel/certidao` no acervo. Não há escolha por
    semelhança a fazer."""
    # AS TRÊS ESPÉCIES QUE A TELA EMITE — problema #75, 18/09/2026. A
    # «negativa de matrícula» saiu do mapa junto com o tipo: mapa de selo que
    # aceita um tipo que a tela não emite é porta aberta para o próximo código
    # digitar `NEGATIVA` e o selador responder por uma busca que não foi feita.
    for tipo in ("INTEIRO_TEOR", "ONUS", "PROPRIEDADE"):
        assert AS.caminho_do_ato("ri_certidoes", tipo) == "/selo/imovel/certidao"


def test_o_envelope_sai_como_a_casa_mandou_nos_667():
    """Campo por campo, medido: `descontoProvimento279`, `isento` e `reterIss`
    em `False`; `percentualDesconto` em 0.0; `nomePartes` VAZIO e não ausente."""
    e = AS.envelope_da_certidao_do_ri(
        tipo="INTEIRO_TEOR", escrevente="FULANO",
        versao_tabela="0220220101", quantidade=2, matricula="1116")
    assert e["descontoProvimento279"] is False
    assert e["isento"] is False
    assert e["reterIss"] is False
    assert e["percentualDesconto"] == 0.0
    assert e["quantidade"] == 2
    assert e["partes"]["nomePartes"] == []
    assert e["versaoTabelaDeCustas"] == "0220220101"


def test_SEM_REQUERENTE_vai_o_numero_da_matricula():
    """Foi o que a casa fez: `{'documento': '00000000000',
    'nome': 'MATRICULA 1116'}`. Inventar um nome seria pior."""
    e = AS.envelope_da_certidao_do_ri(
        tipo="ONUS", escrevente="F", versao_tabela="02", matricula="1116")
    assert e["partes"]["parteAto"] == [
        {"documento": "00000000000", "nome": "MATRICULA 1116"}]


def test_o_codigo_do_ato_vem_da_TABELA_e_a_procedencia_fica_marcada():
    """**Os 667 usaram três códigos, e o acervo não guarda com qual tipo de
    certidão cada um foi.** A leitura é da tabela de emolumentos do TJMA, pela
    descrição do item — e por isso a procedência é `TABELA`, e não `MEDIDO`.
    """
    assert AS.PROCEDENCIA_DO_CODIGO_DA_CERTIDAO_DO_RI == "TABELA"
    # 16.24.4 nomeia «inteiro teor, ônus e ações reais»; 16.24.1 é a comum
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["INTEIRO_TEOR"] == "16.24.4"
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["ONUS"] == "16.24.4"
    assert AS.CODIGO_DA_CERTIDAO_DO_RI["PROPRIEDADE"] == "16.24.1"
    # **E O MAPA TEM EXATAMENTE OS TIPOS DA TELA** — problema #75, 18/09/2026.
    # A chave `NEGATIVA` saiu daqui junto com o tipo, e não por arrumação:
    # mapa de selo que aceita um tipo que a tela não emite é porta aberta para
    # o próximo código digitar `NEGATIVA` e o selador responder por uma busca
    # que não foi feita.
    assert set(AS.CODIGO_DA_CERTIDAO_DO_RI) == set(RIS.TIPOS_CERTIDAO)


def test_tipo_sem_codigo_medido_RECUSA_em_vez_de_escolher_parecido():
    """Não se sela por caminho que a casa nunca usou — e não se escolhe código
    por semelhança. A certidão sai sem selo, e a tela diz por quê."""
    with pytest.raises(AS.AtoError) as erro:
        AS.envelope_da_certidao_do_ri(
            tipo="INVENTADA", escrevente="F", versao_tabela="02")
    assert "SEM SELO" in str(erro.value)


def test_sem_a_versao_da_tabela_de_custas_RECUSA_no_balcao():
    """A recusa é aqui, e não na rede: a viagem até o selador custa mais."""
    with pytest.raises(AS.AtoError) as erro:
        AS.envelope_da_certidao_do_ri(
            tipo="ONUS", escrevente="F", versao_tabela="")
    assert "tabela de custas" in str(erro.value)


def test_a_rota_da_certidao_do_RI_CHAMA_o_selo_automatico():
    """**O relato era este**: «ainda aparece campo para inclusão manual».

    A rota lia `selo_texto` do formulário e nunca chamava o selador. O campo
    manual FICA — o selador é máquina da rede local e cai —, mas agora é a
    exceção, e não o caminho.
    """
    fonte = (RAIZ / "ri_web.py").read_text(encoding="utf-8")
    trecho = fonte[fonte.index("def ri_emitir_certidao"):]
    trecho = trecho[:trecho.index("def ri_certidao_odt")]
    assert "envelope_da_certidao_do_ri" in trecho
    assert 'tabela="ri_certidoes"' in trecho
    assert "selar_o_ato_lavrado" in trecho


def test_SELAR_NAO_DERRUBA_a_certidao_que_ja_existe(s):
    """A chamada vem DEPOIS do `with`: a certidão já está gravada, com número
    e hash. Sem selador configurado ela sai SEM SELO — e existe."""
    con = sqlite3.connect(s["banco"])
    con.execute("INSERT INTO ri_matriculas (numero, livro, criado_em) "
                "VALUES ('1','2','2026-09-07')")
    con.commit()
    mid = int(con.execute("SELECT id FROM ri_matriculas").fetchone()[0])
    con.close()

    tela = s["c"].get(f"/registro-imoveis/{mid}").get_data(as_text=True)
    r = s["c"].post(f"/registro-imoveis/{mid}/certidao",
                    data={"csrf_token": _token(tela), "tipo": "INTEIRO_TEOR"},
                    follow_redirects=True)
    assert r.status_code == 200
    con = sqlite3.connect(s["banco"])
    quantas = con.execute("SELECT COUNT(*) FROM ri_certidoes").fetchone()[0]
    con.close()
    assert quantas == 1, "a certidão tem de existir mesmo sem selo"
