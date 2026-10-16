"""O padrao de importacao — relato #31 do oficial.

O QUE ESTES TESTES GUARDAM

    **Que campo desconhecido NAO passa calado.** Errar o nome de um campo e o
    erro mais facil de cometer ao preparar o arquivo, e o mais dificil de
    perceber: quem o preparou acha que mandou o dado, e ele nao entrou em lugar
    nenhum. O registro e recusado com o nome do campo errado.

    **Que a lista de campos e MEDIDA do esquema**, e nao escrita. Lista de campo
    escrita a mao noutro arquivo envelhece na tarde em que se escreve — foi o
    menu, foram as cargas, e foi o teste que devia guardar as duas.

    **Que conferir nao grava.** Sao dois passos, como na remessa da CRA: aqui
    nao ha como desfazer, porque acervo importado vira o livro.

    **Que o recusado nao derruba o que passou** — e a regra da carga e da
    remessa: registro ruim nao impede os bons de entrar.

    **Que a palavra `chave` nao e coluna de nenhuma tabela importavel.** No dia
    em que fosse, o campo do arquivo teria dois donos.

    **Que as colunas que a BUSCA consulta sao derivadas na entrada** — relato
    #55. `livro_norm` e `imovel_norm` da matricula importada ficavam vazios, e
    a ficha existia e nao era achada por nenhum filtro de livro. A lista de
    derivacoes e curta, medida e guardada contra o esquema: coluna `_norm` nova
    sem derivador fica vermelha aqui, em vez de sumir da busca calada.
"""
from __future__ import annotations

import glob
import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import importar_padrao as IMP                                    # noqa: E402

AGORA = "2026-08-30T10:00"


@pytest.fixture()
def con(cg_db, cg_db_path):
    c = sqlite3.connect(str(cg_db_path))
    c.row_factory = sqlite3.Row
    yield c
    c.close()


def _arquivo(registros, *, especie="RCPN_ASSENTO", formato=IMP.FORMATO,
             versao=IMP.VERSAO) -> str:
    return json.dumps({"formato": formato, "versao": versao,
                       "especie": especie,
                       "de_onde_veio": "Sistema da serventia vizinha",
                       "registros": registros}, ensure_ascii=False)


def _bom(chave="1955-A-12", **extra) -> dict:
    r = {"chave": chave, "serie": "RC_A", "especie": "NASCIMENTO",
         "nome": "MARIA DAS DORES SOUSA", "numero": "12",
         "data_ato": "1955-10-12"}
    r.update(extra)
    return r


# ------------------------------------------------------- os campos, medidos


def test_os_campos_saem_do_esquema_e_nao_de_uma_lista(con):
    """Coluna nova aparece sozinha; coluna que a maquina controla nunca."""
    nomes = {c["nome"] for c in IMP.campos(con, "RCPN_ASSENTO")}
    assert "cor_raca" in nomes and "naturalidade_declarada" in nomes
    assert not (nomes & IMP.DA_MAQUINA), \
        "campo que a máquina controla entrou na lista do arquivo"
    assert not [n for n in nomes if n.endswith("_norm")]


def test_o_obrigatorio_vem_marcado(con):
    # Acervo RCPN antigo: só identidade mínima é obrigatória no arquivo.
    # serie deriva da espécie ao gravar, se faltar.
    obrig = {c["nome"] for c in IMP.campos(con, "RCPN_ASSENTO")
             if c["obrigatorio"]}
    assert "nome" in obrig and "especie" in obrig
    assert "serie" not in obrig
    assert "criado_em" not in obrig, "essa é da máquina"


def test_o_modelo_em_branco_e_um_arquivo_que_este_sistema_le(con):
    """**O manual que nao envelhece**: o exemplo se monta do esquema de hoje."""
    modelo = json.loads(IMP.modelo_em_branco(con, "RI_MATRICULA"))
    assert modelo["formato"] == IMP.FORMATO
    assert modelo["especie"] == "RI_MATRICULA"
    assert IMP.CAMPO_DA_CHAVE in modelo["registros"][0]
    assert "numero" in modelo["registros"][0]


def test_especie_que_nao_existe_diz_as_que_existem(con):
    with pytest.raises(IMP.ImportacaoError) as e:
        IMP.campos(con, "CARTORIO_DO_VIZINHO")
    assert "RCPN_ASSENTO" in str(e.value)


# ------------------------------------------------------- o que se recusa


def test_campo_desconhecido_e_recusado_com_o_nome_dele(con):
    """**O erro mais facil de cometer e o mais dificil de perceber.**"""
    q = IMP.conferir(con, _arquivo([_bom(nome_da_mae="ANA")]))
    assert q["entram"] == []
    assert "nome_da_mae" in q["recusados"][0]["porque"]


def test_campo_que_a_maquina_controla_nao_entra_pelo_arquivo(con):
    """`id` escolheria o numero da linha; `criado_em` diria que entrou ontem."""
    q = IMP.conferir(con, _arquivo([_bom(id=99, criado_em="1900-01-01")]))
    assert q["entram"] == []


def test_falta_de_obrigatorio_diz_o_que_falta(con):
    r = _bom()
    del r["nome"]
    q = IMP.conferir(con, _arquivo([r]))
    assert "nome" in q["recusados"][0]["porque"]


def test_data_impossivel_nao_entra(con):
    """As 21 pessoas que «nasciam» depois do proprio ato, por outro caminho."""
    q = IMP.conferir(con, _arquivo([_bom(data_ato="12/10/1955")]))
    assert "data_ato" in q["recusados"][0]["porque"]


def test_registro_sem_chave_e_recusado(con):
    """Sem ela nao ha como impedir o mesmo registro entrar duas vezes."""
    r = _bom()
    del r["chave"]
    q = IMP.conferir(con, _arquivo([r]))
    assert IMP.CAMPO_DA_CHAVE in q["recusados"][0]["porque"]


def test_chave_repetida_dentro_do_arquivo_e_recusada(con):
    q = IMP.conferir(con, _arquivo([_bom(), _bom()]))
    assert len(q["entram"]) == 1 and len(q["recusados"]) == 1


def test_arquivo_que_nao_diz_o_formato_e_recusado(con):
    with pytest.raises(IMP.ImportacaoError) as e:
        IMP.conferir(con, _arquivo([_bom()], formato="QUALQUER_COISA"))
    assert IMP.FORMATO in str(e.value)


def test_json_quebrado_manda_abrir_no_bloco_de_notas(con):
    with pytest.raises(IMP.ImportacaoError) as e:
        IMP.conferir(con, "{isto nao e json")
    assert "Bloco de Notas" in str(e.value)


# ------------------------------------------------------- conferir e importar


def test_conferir_nao_grava_nada(con):
    antes = con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0]
    IMP.conferir(con, _arquivo([_bom()]))
    assert con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == antes


def test_importar_grava_e_marca_a_origem(con):
    q = IMP.importar(con, _arquivo([_bom()]), agora=AGORA, por="mario")
    assert q["entraram"] == 1
    linha = con.execute(
        "SELECT * FROM rc_assentos WHERE origem = ?",
        (IMP.MARCA_DA_ORIGEM,)).fetchone()
    assert linha["nome"] == "MARIA DAS DORES SOUSA"
    assert linha["origem_chave"] == "1955-A-12"
    assert linha["criado_em"] == AGORA


def test_o_mesmo_arquivo_duas_vezes_nao_duplica(con):
    IMP.importar(con, _arquivo([_bom()]), agora=AGORA)
    q = IMP.importar(con, _arquivo([_bom()]), agora=AGORA)
    assert q["entraram"] == 0 and len(q["repetidos"]) == 1
    assert con.execute("SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 1


def test_o_recusado_nao_derruba_o_que_passou(con):
    """A regra da carga e da remessa: registro ruim nao impede os bons."""
    q = IMP.importar(
        con, _arquivo([_bom("A"), _bom("B", campo_inventado="x"), _bom("C")]),
        agora=AGORA)
    assert q["entraram"] == 2 and len(q["recusados"]) == 1
    assert q["recusados"][0]["linha"] == 2


def test_a_matricula_do_ri_nao_quebra_com_criado_por_de_verdade(con):
    """`criado_por` de `ri_matriculas` é FK para `users(id)`, e `por` é NOME.

    Achado ao importar a matrícula 3110 pela primeira vez: `usuario_nome()` é
    a única coisa que a tela manda como `por`, e gravá-la ali estoura
    `IntegrityError` — a mesma rota que grava as outras cinco espécies sem
    problema. `criado_por` fica `NULL`, como toda outra rota que grava em
    `ri_matriculas` já faz de propósito.
    """
    con.execute("PRAGMA foreign_keys=ON")
    q = IMP.importar(con, _arquivo(
        [{"chave": "2-C/999", "numero": "999", "livro": "2-C"}],
        especie="RI_MATRICULA"), agora=AGORA, por="Fulana de Tal")
    assert q["entraram"] == 1
    assert con.execute(
        "SELECT criado_por FROM ri_matriculas WHERE numero='999'"
    ).fetchone()[0] is None


def test_a_matricula_do_ri_tambem_importa(con):
    """As duas espécies que o oficial citou, e não uma."""
    q = IMP.importar(con, _arquivo(
        [{"chave": "2-C/315", "numero": "315", "livro": "2-C",
          "cidade": "CIDADE EXEMPLO", "uf": "MA"}],
        especie="RI_MATRICULA"), agora=AGORA)
    assert q["entraram"] == 1
    assert con.execute(
        "SELECT numero FROM ri_matriculas WHERE origem=?",
        (IMP.MARCA_DA_ORIGEM,)).fetchone()[0] == "315"


# ------------------------------------------- as colunas que a busca consulta


def test_a_matricula_do_ri_entra_com_o_livro_normalizado(con):
    """**O defeito do relato #55, e ele era deste arquivo.**

    `ri_matriculas.livro_norm` é a coluna que **todo filtro de livro** compara.
    A ficha importada entrava com ela vazia: existia, abria pelo número, e
    **nenhum filtro a achava** — sem erro em lugar nenhum. Medido na produção
    em 15/09/2026: 1 de 1.982 matrículas sem `livro_norm`, e era a que este
    módulo havia importado.

    A igualdade é **construída**, e não suposta: a coluna tem de trazer
    exatamente o que a função da casa devolve — a mesma que o RI usa para
    gravar, contar e filtrar.
    """
    from ri_schema import norm_livro

    IMP.importar(con, _arquivo(
        [{"chave": "2-C/999", "numero": "999", "livro": "2-C"}],
        especie="RI_MATRICULA"), agora=AGORA)
    linha = con.execute(
        "SELECT livro, livro_norm FROM ri_matriculas WHERE numero='999'"
    ).fetchone()
    assert linha["livro_norm"] == norm_livro(linha["livro"])
    assert linha["livro_norm"] == "2C", "«2-C» e «2C» são o mesmo livro"


def test_o_filtro_de_livro_acha_a_ficha_importada(con):
    """E o defeito era do lado da BUSCA: o filtro é que perdia a ficha."""
    IMP.importar(con, _arquivo(
        [{"chave": "2-C/998", "numero": "998", "livro": "2-C"}],
        especie="RI_MATRICULA"), agora=AGORA)
    achou = con.execute(
        "SELECT COUNT(*) FROM ri_matriculas WHERE livro_norm='2C'"
    ).fetchone()[0]
    assert achou == 1, "a ficha importada não é achada pelo filtro de livro"


def test_o_imovel_importado_e_achado_sem_acento(con):
    """`imovel_norm` é o campo da busca do imóvel, e ele também não vem do
    arquivo: quem o escreve é a mesma função do cadastro — a busca do balcão
    digita sem acento, e o acervo guarda com acento."""
    from ri_schema import normalizar_busca

    campos = {"logradouro": "FAZENDA ÁGUA BOA", "bairro": "ZONA RURAL",
              "cidade": "CIDADE EXEMPLO", "descricao_perimetro": "LOTE 7"}
    IMP.importar(con, _arquivo(
        [dict({"chave": "2-C/997", "numero": "997", "livro": "2-C"}, **campos)],
        especie="RI_MATRICULA"), agora=AGORA)
    linha = con.execute(
        "SELECT * FROM ri_matriculas WHERE numero='997'").fetchone()
    assert linha["imovel_norm"] == normalizar_busca(" ".join(campos.values()))
    achou = con.execute(
        "SELECT COUNT(*) FROM ri_matriculas WHERE imovel_norm LIKE ?",
        (f"%{normalizar_busca('fazenda agua boa')}%",)).fetchone()[0]
    assert achou == 1, "o imóvel não é achado por busca sem acento"


def test_a_coluna_norm_nao_entra_pelo_arquivo(con):
    """Ela é derivada: aceitá-la do arquivo faria a busca achar outra coisa."""
    q = IMP.conferir(con, _arquivo(
        [{"chave": "2-C/996", "numero": "996", "livro": "2-C",
          "livro_norm": "9Z"}], especie="RI_MATRICULA"))
    assert q["entram"] == []
    assert "livro_norm" in q["recusados"][0]["porque"]


def test_toda_coluna_norm_importavel_tem_derivacao_declarada(con):
    """**O guarda da família inteira** — é ele que impede a próxima.

    A lista de derivações poderia ser escrita à mão e envelhecer na tarde em que
    a coluna nascesse: foi assim que o `livro_norm` ficou vazio, porque
    `nome_norm` era um caso à parte dentro do laço. Aqui ela se **mede** do
    esquema: toda coluna de sufixo `_norm` de toda tabela que este módulo grava
    tem de ter derivador declarado — ou o teste fica vermelho **antes** de a
    ficha entrar e sumir da busca.
    """
    sem = []
    for especie, modelo in IMP.MODELOS.items():
        tabelas = [modelo["tabela"]]
        if modelo.get("pessoas"):
            tabelas.append(modelo["pessoas"]["tabela"])
        for tabela in tabelas:
            for r in con.execute(f'PRAGMA table_info("{tabela}")'):
                coluna = r[1]
                if not coluna.endswith("_norm"):
                    continue
                if (tabela, coluna) not in IMP.DERIVACOES:
                    sem.append(f"{tabela}.{coluna} ({especie})")
    assert not sem, (
        "coluna `_norm` sem derivador em `importar_padrao.DERIVACOES`: "
        + ", ".join(sem)
        + " — sem ela o registro importado existe e a busca não o acha")


def test_as_derivacoes_usam_as_funcoes_da_casa(con):
    """**Importadas, e não cópias parecidas** — a lição da `normalizar_nome`,
    que neste projeto já divergiu (uma devolvia MAIÚSCULAS onde a outra devolvia
    minúsculas) e custou a busca inteira, calada."""
    from pt_schema import normalizar_nome
    from ri_schema import norm_livro, normalizar_busca

    assert IMP._normalizar_nome_da_casa("José") == normalizar_nome("José")
    assert IMP._normalizar_livro_da_casa("2-F") == norm_livro("2-F")
    assert IMP._normalizar_busca_da_casa("Fazenda Água Boa") == \
        normalizar_busca("Fazenda Água Boa")
    assert IMP._normalizar_livro_da_casa("2-F") != normalizar_nome("2-F"), \
        "as duas normalizações da casa são diferentes de propósito"


def test_a_parte_do_ri_usa_a_normalizacao_MAIUSCULA(con):
    """**As duas normalizações de nome convivem de propósito** — e trocá-las
    deixaria a parte existindo e não achada pela busca por nome do balcão."""
    from ri_schema import normalizar_busca

    assert ("ri_partes", "nome_norm") in IMP.DERIVACOES
    assert IMP._normalizar_busca_da_casa("José da Silva") == \
        normalizar_busca("José da Silva") == "JOSE DA SILVA"


def test_sem_fonte_nao_se_escreve_nada(con):
    """Coluna derivada de campo vazio seria vazio disfarçado de cálculo."""
    linha: dict = {"livro": None, "logradouro": "", "nome": "  "}
    escritas = IMP._derivar("ri_matriculas", IMP._colunas(con, "ri_matriculas"),
                            linha)
    assert escritas == []
    assert "livro_norm" not in linha and "imovel_norm" not in linha


def test_com_fonte_se_escreve_e_a_lista_diz_o_que_foi_escrito(con):
    """**O outro lado do teste de cima** — e ele faltava.

    Sem esta metade, o teste anterior passaria com a régua errada: uma lista de
    colunas em que o nome não está na posição zero faz `_derivar` não achar
    coluna nenhuma, não escrever nada, e o `assert` de vazio fica verde por
    motivo nenhum. Foi assim que a primeira versão do script de conserto
    relatou «nada a preencher» sobre seis linhas que tinham o que preencher.
    """
    linha = {"livro": "2-Q", "logradouro": "FAZENDA ÁGUA BOA", "bairro": "",
             "cidade": "CIDADE EXEMPLO", "descricao_perimetro": ""}
    escritas = IMP._derivar("ri_matriculas", IMP._colunas(con, "ri_matriculas"),
                            linha)
    assert sorted(escritas) == ["imovel_norm", "livro_norm"]
    assert linha["livro_norm"] == "2Q"


# ------------------------------------------- o conserto do que já está gravado
#
# Consertar quem grava impede a PRÓXIMA ficha de nascer cega; não devolve a vista
# às que já nasceram. A passada abaixo é essa segunda metade — e ela roda na
# abertura do banco (`database.py`), ao lado das folhas presas e das sessões
# interrompidas.


def _ficha(con, numero: str, *, livro: str, livro_norm=None,
           logradouro: str = "", perimetro: str = "") -> int:
    cur = con.execute(
        """INSERT INTO ri_matriculas (numero, livro, livro_norm, logradouro,
                                      descricao_perimetro, criado_em)
           VALUES (?,?,?,?,?,?)""",
        (numero, livro, livro_norm, logradouro, perimetro, AGORA))
    con.commit()
    return int(cur.lastrowid)


def test_a_ficha_que_JA_ESTAVA_gravada_tambem_se_completa(con):
    """**O relato #55, do lado do dado** — e é o que o balcão enxerga hoje.

    A ficha 3.110 foi importada com `livro_norm` vazio: existia, abria pelo
    número, e **todo filtro de livro devolvia lista vazia**. Sem esta passada,
    as fichas já gravadas continuariam invisíveis para sempre — e é o balcão que
    paga, procurando uma ficha que o sistema jura que não existe.
    """
    mid = _ficha(con, "3110", livro="2-Q")
    assert con.execute("SELECT livro_norm FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] in (None, "")

    IMP.preencher_colunas_derivadas(con)

    assert con.execute("SELECT livro_norm FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] == "2Q"
    achou = con.execute("SELECT 1 FROM ri_matriculas WHERE id=? AND livro_norm=?",
                        (mid, IMP._normalizar_livro_da_casa("2-Q"))).fetchone()
    assert achou, "o filtro de livro continua sem achar a ficha"


def test_a_passada_NAO_sobrescreve_coluna_que_ja_tem_valor(con):
    """Divergir da função da casa pode ser ajuste a mão ou a função que mudou:
    nos dois casos é assunto do oficial, e sobrescrever calado apagaria o que
    alguém decidiu."""
    mid = _ficha(con, "777", livro="2-Q", livro_norm="AJUSTADO A MAO")

    IMP.preencher_colunas_derivadas(con)

    assert con.execute("SELECT livro_norm FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] == "AJUSTADO A MAO"


def test_sem_fonte_a_passada_nao_inventa_valor(con):
    """Coluna derivada de nada seria um vazio disfarçado de cálculo — e o vazio
    é o que a linha já tinha."""
    mid = _ficha(con, "888", livro="")

    IMP.preencher_colunas_derivadas(con)

    assert con.execute("SELECT livro_norm FROM ri_matriculas WHERE id=?",
                       (mid,)).fetchone()[0] in (None, "")


def test_a_passada_e_IDEMPOTENTE(con):
    """Como as outras da abertura do banco: coluna preenchida não se move de
    novo. É isso que permite ela rodar a cada subida sem marcador de «já
    rodei» — e alcançar também a linha que alguém inserir à mão amanhã, que era
    como este defeito aparecia."""
    _ficha(con, "999", livro="2-Q")
    IMP.preencher_colunas_derivadas(con)

    segunda = IMP.preencher_colunas_derivadas(con)

    assert set(segunda) == {f"{t}.{c}" for t, c in IMP.DERIVACOES}, \
        "a passada tem de dizer o que conferiu, e não só o que mudou"
    assert sum(segunda.values()) == 0


def test_a_subida_do_banco_chama_a_passada(cg_db):
    """**A passada não adianta se ninguém a chama** — e função pronta que
    nenhuma tela chama é o defeito mais repetido deste projeto. Aqui quem chama
    é a abertura do banco, e é ela que roda na máquina do balcão."""
    assert hasattr(cg_db, "colunas_norm_preenchidas")
    assert not isinstance(cg_db.colunas_norm_preenchidas, dict) or \
        "erro" not in cg_db.colunas_norm_preenchidas
    codigo = (RAIZ / "database.py").read_text(encoding="utf-8")
    assert "preencher_colunas_derivadas" in codigo


# ------------------------------------------------------- os guardas


def test_a_palavra_chave_nao_e_coluna_de_tabela_importavel(con):
    """No dia em que fosse, o campo do arquivo teria dois donos."""
    colidem = []
    for especie, modelo in IMP.MODELOS.items():
        colunas = {r[1] for r in con.execute(
            f'PRAGMA table_info("{modelo["tabela"]}")')}
        if IMP.CAMPO_DA_CHAVE in colunas:
            colidem.append(f"{especie} ({modelo['tabela']})")
    assert not colidem, (
        f"a coluna «{IMP.CAMPO_DA_CHAVE}» apareceu em: " + ", ".join(colidem)
        + " — escolha outra palavra para a chave de origem do arquivo")


def test_toda_especie_declarada_tem_tabela_que_existe(con):
    """Espécie que aponta para tabela inexistente só falha no dia do uso."""
    for especie, modelo in IMP.MODELOS.items():
        achou = con.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",
            (modelo["tabela"],)).fetchone()
        assert achou, f"{especie} aponta para «{modelo['tabela']}», que não existe"


def test_o_modulo_nao_lavra_nem_numera_nem_sela():
    """Ele traz ACERVO: o registro que chega já tem número, livro e folha."""
    codigo = (RAIZ / "importar_padrao.py").read_text(encoding="utf-8")
    for proibido in ("obter_selo", "reservar(", "proximo_numero",
                     "selar_o_ato", "cobrar("):
        assert proibido not in codigo, f"o módulo faz «{proibido}»"
