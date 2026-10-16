"""OS MODELOS DO ESCREVENTE — o módulo «Modelos» do E-Ofício, copiado.

O QUE ESTES TESTES GUARDAM, e cada um custou uma decisão:

      - **o claro que sai vazio é DEVOLVIDO**, e não vira espaço em branco no
        papel — é a metade que o E-Ofício não tinha;
      - **o valor sai do blob do acervo quando a coluna está vazia**, e da
        coluna quando ela tem dado: os 244 assentos desta casa são todos do
        acervo, e um vocabulário que lesse só as colunas devolveria documento
        em branco para o acervo inteiro;
      - **modelo de uma espécie não monta em assento de outra** — claro que
        não existe na outra sairia em branco;
      - **a conferência vem antes de gravar**, e recusa claro desconhecido,
        chave sem fechar, Jinja e `@claro` do E-Ofício;
      - **o de-para não adivinha**: o que ele não conhece volta na lista e
        continua escrito no texto;
      - e **os oito papéis do nascimento leem cada um o seu** — a fábrica de
        claros fecha sobre o valor, e não sobre a variável do laço.
"""
from __future__ import annotations

import json
import sqlite3
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_modelos_livres as MOD
import rc_modelos_livres_schema as ESQ
import rc_schema

AGORA = "2026-09-07T10:00:00"
SV = {"serventia_titular": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
      "serventia_titulo": "Oficial de Registro", "ri_cidade": "Cidade Exemplo",
      "ri_uf": "MA", "ri_estado": "Maranhão",
      "serventia_email": "cidadeexemplo@cartorio.ch",
      "registrador": "MARIO EXEMPLO DOS SANTOS", "titulo": "Oficial"}


@pytest.fixture()
def con(tmp_path):
    c = sqlite3.connect(tmp_path / "t.sqlite3")
    c.row_factory = sqlite3.Row
    rc_schema.init_rc_schema(c)
    ESQ.init_rc_modelos_livres_schema(c)
    yield c
    c.close()


def _assento(con, *, especie="NASCIMENTO", dados=None, **colunas) -> int:
    campos = {"serie": "RC_A", "especie": especie, "numero": 1234,
              "matricula": "0" * 32, "nome": "FULANO DE TAL",
              "data_ato": "2020-01-16", "data_fato": "2020-01-15",
              "dados_json": json.dumps(dados or {}), "criado_em": AGORA}
    campos.update(colunas)
    cols = ", ".join(campos)
    cur = con.execute(
        f"INSERT INTO rc_assentos({cols}) VALUES ({','.join('?' * len(campos))})",
        tuple(campos.values()))
    return int(cur.lastrowid)


def _pessoa(con, assento_id, papel, nome, **campos):
    campos.update({"assento_id": assento_id, "papel": papel, "nome": nome,
                   "criado_em": AGORA})
    cols = ", ".join(campos)
    con.execute(
        f"INSERT INTO rc_pessoas({cols}) VALUES ({','.join('?' * len(campos))})",
        tuple(campos.values()))


def _modelo(con, *, especie="NASCIMENTO", nome="Termo", corpo="oi") -> int:
    return MOD.criar(con, especie=especie, nome=nome, corpo=corpo,
                     quem="MARIO", agora=AGORA)


# ==================================================== o vocabulário existe mesmo

def test_as_tres_especies_tem_vocabulario():
    for especie in ESQ.ESPECIES:
        assert MOD.vocabulario(especie), especie


def test_especie_que_nao_existe_recusa():
    with pytest.raises(MOD.ModeloLivreError):
        MOD.vocabulario("PROCLAMAS")


def test_nenhum_claro_repetido_na_mesma_especie():
    """Claro repetido faria a tela oferecer o mesmo nome com dois sentidos."""
    for especie in ESQ.ESPECIES:
        nomes = [c["nome"] for c in MOD.vocabulario(especie)]
        assert len(nomes) == len(set(nomes)), especie


def test_todo_claro_diz_de_onde_sai():
    """«De onde sai» é o que impede o claro adivinhado de entrar na lista."""
    for especie in ESQ.ESPECIES:
        for c in MOD.vocabulario(especie):
            assert c["de_onde"].strip(), f"{especie}/{c['nome']}"
            assert c["rotulo"].strip(), f"{especie}/{c['nome']}"


def test_o_de_para_so_aponta_para_claro_que_existe():
    """De-para com destino inexistente estouraria só na hora de montar."""
    todos: set[str] = set()
    for especie in ESQ.ESPECIES:
        todos |= MOD.nomes_dos_claros(especie)
    ruins = sorted(d for d in set(MOD.DE_PARA_DO_EOFICIO.values())
                   if d not in todos)
    assert ruins == []


def test_o_de_para_tem_a_chave_em_minuscula():
    """A busca é feita em minúscula — chave com maiúscula nunca casaria.

    Medido nos 13 modelos: o mesmo claro aparece como `@dataatual` e
    `@dataAtual`.
    """
    assert all(k == k.lower() for k in MOD.DE_PARA_DO_EOFICIO)


# ===================================================== os oito papéis do nascimento

def test_cada_papel_le_o_seu(con):
    """A fábrica fecha sobre o VALOR, e não sobre a variável do laço.

    Se ela fechasse sobre a variável, os oito papéis leriam o último — e o
    documento sairia com o nome da avó materna sob o rótulo do pai, sem erro
    em lugar nenhum.
    """
    aid = _assento(con)
    _pessoa(con, aid, "PAI", "JOSE DE TAL")
    _pessoa(con, aid, "MAE", "MARIA DE TAL")
    _pessoa(con, aid, "AVO_MATERNA", "JOANA DE TAL")
    _pessoa(con, aid, "DECLARANTE", "PEDRO DE TAL")
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    v = MOD.valores(ctx, "NASCIMENTO")
    assert v["pai_nome"] == "JOSE DE TAL"
    assert v["mae_nome"] == "MARIA DE TAL"
    assert v["avo_materna_nome"] == "JOANA DE TAL"
    assert v["declarante_nome"] == "PEDRO DE TAL"
    assert v["avo_paterno_nome"] == ""


def test_os_avos_so_tem_nome(con):
    """Oferecer «profissão do avô» seria oferecer claro vazio em 100% dos casos."""
    nomes = MOD.nomes_dos_claros("NASCIMENTO")
    assert "avo_paterno_nome" in nomes
    assert "avo_paterno_profissao" not in nomes


def test_a_primeira_pessoa_de_cada_papel_e_a_que_vale(con):
    aid = _assento(con)
    _pessoa(con, aid, "PAI", "PRIMEIRO", ordem=1)
    _pessoa(con, aid, "PAI", "SEGUNDO", ordem=2)
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    assert MOD.valores(ctx, "NASCIMENTO")["pai_nome"] == "PRIMEIRO"


# ============================================= a coluna vem antes do blob do acervo

def test_a_hora_sai_do_blob_quando_a_coluna_esta_vazia(con):
    """Os 244 assentos desta casa são do acervo, e a coluna deles está vazia."""
    aid = _assento(con, dados={"strHoraNascimento": "16:12"})
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    assert MOD.valores(ctx, "NASCIMENTO")["hora_do_nascimento"] == "16:12"


def test_a_coluna_ganha_do_blob(con):
    """Corrigir o dado na tela tem de aparecer no papel.

    Se o blob ganhasse, o escrevente corrigiria a hora e continuaria
    imprimindo a antiga.
    """
    aid = _assento(con, hora_fato="09:30",
                   dados={"strHoraNascimento": "16:12"})
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    assert MOD.valores(ctx, "NASCIMENTO")["hora_do_nascimento"] == "09:30"


def test_a_causa_da_morte_sai_do_blob(con):
    aid = _assento(con, especie="OBITO",
                   dados={"strCausaMorte": "NEOPLASIA MALIGNA DE PROSTATA"})
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    v = MOD.valores(ctx, "OBITO")
    assert v["causa_da_morte"] == "NEOPLASIA MALIGNA DE PROSTATA"


def test_o_rg_nao_vira_cpf(con):
    """Sem o teste dos onze dígitos, um RG sairia sob o rótulo CPF."""
    aid = _assento(con)
    _pessoa(con, aid, "PAI", "JOSE", documento_numero="049996362013-5")
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    v = MOD.valores(ctx, "NASCIMENTO")
    assert v["pai_cpf"] == ""
    assert v["pai_rg"] == "049996362013-5"


def test_o_sexo_desconhecido_sai_como_veio(con):
    """Devolver «ignorado» inventaria uma declaração que ninguém fez."""
    aid = _assento(con)
    _pessoa(con, aid, "REGISTRADO", "FULANO", sexo="Indefinido")
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    assert MOD.valores(ctx, "NASCIMENTO")["registrado_sexo"] == "Indefinido"


def test_o_sexo_do_acervo_e_da_casa_dao_o_mesmo(con):
    """O acervo grava «Masculino»; o ato novo grava `M`."""
    for gravado in ("M", "Masculino"):
        aid = _assento(con)
        _pessoa(con, aid, "REGISTRADO", "FULANO", sexo=gravado)
        ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
        assert MOD.valores(ctx, "NASCIMENTO")["registrado_sexo"] == "masculino"


def test_a_serventia_entra_pelas_duas_grafias(con):
    aid = _assento(con)
    ctx = MOD.contexto(con, aid, serventia={"nome": "OUTRA CASA",
                                            "cidade": "Imperatriz"},
                       hoje=AGORA)
    v = MOD.valores(ctx, "NASCIMENTO")
    assert v["cartorio"] == "OUTRA CASA"
    assert v["cidade"] == "Imperatriz"


# ================================================= conferir antes de gravar

def test_claro_desconhecido_e_recusado():
    ruim = MOD.conferir_corpo("NASCIMENTO", "Certifico que {inventado}.")
    assert "inventado" in ruim


def test_chave_sem_fechar_e_recusada():
    assert MOD.conferir_corpo("NASCIMENTO", "Certifico que {nome.")


def test_jinja_e_recusado_com_o_recado_certo():
    """Passar Jinja aqui aprovaria texto que o `str.format` não monta."""
    ruim = MOD.conferir_corpo("NASCIMENTO", "{{ a.nome }}")
    assert "chaves simples" in ruim


def test_claro_do_eoficio_e_recusado_e_manda_converter():
    ruim = MOD.conferir_corpo("NASCIMENTO", "NOME: @nomenascido")
    assert "E-Ofício" in ruim


def test_modelo_vazio_e_recusado():
    assert MOD.conferir_corpo("NASCIMENTO", "   ")


def test_modelo_bom_passa():
    assert MOD.conferir_corpo(
        "NASCIMENTO", "Certifico que {nome}, matrícula {matricula}.") == ""


def test_criar_confere_antes_de_gravar(con):
    with pytest.raises(MOD.ModeloLivreError):
        _modelo(con, corpo="Certifico que {inventado}.")
    assert MOD.listar(con) == []


def test_salvar_confere_antes_de_gravar(con):
    ident = _modelo(con, corpo="Certifico que {nome}.")
    with pytest.raises(MOD.ModeloLivreError):
        MOD.salvar(con, ident, nome="Termo", corpo="{inventado}",
                   quem="MARIO", agora=AGORA)
    assert MOD.ler(con, ident)["corpo"] == "Certifico que {nome}."


# ============================================================== o cadastro

def test_dois_modelos_com_o_mesmo_nome_na_mesma_especie_recusam(con):
    _modelo(con, nome="Termo de gêmeos", corpo="{nome}")
    with pytest.raises(MOD.ModeloLivreError):
        _modelo(con, nome="Termo de gêmeos", corpo="{nome}")


def test_o_mesmo_nome_em_especies_diferentes_pode(con):
    """Medido: as linhas 11 e 14 do E-Ofício se chamam as duas «Termo»."""
    _modelo(con, especie="NASCIMENTO", nome="Termo", corpo="{nome}")
    _modelo(con, especie="OBITO", nome="Termo", corpo="{nome}")
    assert len(MOD.listar(con)) == 2


def test_modelo_sem_nome_recusa(con):
    with pytest.raises(MOD.ModeloLivreError):
        _modelo(con, nome="   ", corpo="{nome}")


def test_desativar_nao_apaga(con):
    ident = _modelo(con, corpo="{nome}")
    MOD.ativar(con, ident, ativo=False, quem="MARIO", agora=AGORA)
    assert MOD.ler(con, ident)["ativo"] == 0
    assert len(MOD.listar(con)) == 1
    assert MOD.listar(con, incluir_inativos=False) == []


def test_a_lista_do_assento_so_traz_a_especie_dele_e_ativos(con):
    aid = _assento(con, especie="OBITO")
    _modelo(con, especie="OBITO", nome="Comunicação", corpo="{nome}")
    _modelo(con, especie="NASCIMENTO", nome="Outro", corpo="{nome}")
    inativo = _modelo(con, especie="OBITO", nome="Velho", corpo="{nome}")
    MOD.ativar(con, inativo, ativo=False, quem="MARIO", agora=AGORA)
    nomes = [m["nome"] for m in MOD.para_o_assento(con, aid)]
    assert nomes == ["Comunicação"]


def test_assento_de_especie_sem_vocabulario_devolve_lista_vazia(con):
    """PROCLAMAS não tem vocabulário — a lista vazia é a resposta honesta."""
    aid = _assento(con, especie="PROCLAMAS")
    assert MOD.para_o_assento(con, aid) == []


def test_quantos_por_especie_conta_so_os_ativos(con):
    _modelo(con, especie="NASCIMENTO", nome="Um", corpo="{nome}")
    ident = _modelo(con, especie="NASCIMENTO", nome="Dois", corpo="{nome}")
    MOD.ativar(con, ident, ativo=False, quem="MARIO", agora=AGORA)
    assert MOD.quantos_por_especie(con)["NASCIMENTO"] == 1


# ================================================================== montar

def test_montar_troca_os_claros(con):
    aid = _assento(con, nome="FULANO DE TAL")
    ident = _modelo(con, corpo="Certifico que {nome} nasceu em {data_do_nascimento}.")
    r = MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert r["texto"] == "Certifico que FULANO DE TAL nasceu em 15/01/2020."


def test_montar_devolve_os_claros_vazios(con):
    """**É a metade que o E-Ofício não tinha.**

    Lá o claro sem dado virava espaço em branco no papel, e quem descobria era
    quem lia o documento depois de assinado.
    """
    aid = _assento(con)
    ident = _modelo(con, corpo="{nome}, filho de {pai_nome} e {mae_nome}.")
    r = MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert set(r["vazios"]) == {"pai_nome", "mae_nome"}


def test_montar_nao_repete_claro_vazio(con):
    aid = _assento(con)
    ident = _modelo(con, corpo="{pai_nome} e outra vez {pai_nome}.")
    r = MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert r["vazios"] == ["pai_nome"]


def test_modelo_de_outra_especie_recusa(con):
    """Claro que não existe na outra espécie sairia em branco no papel."""
    aid = _assento(con, especie="OBITO")
    ident = _modelo(con, especie="NASCIMENTO", corpo="{nome}")
    with pytest.raises(MOD.ModeloLivreError) as erro:
        MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert "Óbito" in str(erro.value)


def test_assento_que_nao_existe_recusa(con):
    ident = _modelo(con, corpo="{nome}")
    with pytest.raises(MOD.ModeloLivreError):
        MOD.montar(con, ident, 9999, serventia=SV, hoje=AGORA)


def test_montar_nao_grava_nada(con):
    aid = _assento(con)
    ident = _modelo(con, corpo="{nome}")
    antes = MOD.ler(con, ident)
    MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert dict(MOD.ler(con, ident)) == dict(antes)


def test_a_matricula_sai_na_forma_da_certidao(con):
    aid = _assento(con, matricula="00000001552026100001001000012345")
    ident = _modelo(con, corpo="{matricula}")
    r = MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert r["texto"].startswith("000000 01 55 2026 1 ")


def test_a_folha_sai_do_ato_de_registro(con):
    aid = _assento(con)
    con.execute(
        """INSERT INTO rc_atos(assento_id, tipo, folha, data_ato, criado_em)
           VALUES (?,?,?,?,?)""", (aid, "REGISTRO", 291, "2020-01-16", AGORA))
    ident = _modelo(con, corpo="folha {folha}")
    r = MOD.montar(con, ident, aid, serventia=SV, hoje=AGORA)
    assert r["texto"] == "folha 291"


# ================================================ a conversão do E-Ofício

def test_converte_os_claros_conhecidos():
    r = MOD.traduzir_do_eoficio("NOME: @nomenascido — CPF: @cpfnascido")
    assert r["texto"] == "NOME: {registrado_nome} — CPF: {cpf_do_registrado}"
    assert r["nao_convertidos"] == []


def test_converte_sem_olhar_maiuscula():
    """Medido: o mesmo claro aparece como `@dataatual` e `@dataAtual`."""
    r = MOD.traduzir_do_eoficio("@dataAtual e @dataatual")
    assert r["texto"] == "{data_de_hoje} e {data_de_hoje}"


def test_o_que_nao_sabe_converter_CONTINUA_no_texto():
    """Apagar faria o oficial descobrir o buraco no papel impresso."""
    r = MOD.traduzir_do_eoficio("A: @nomenascido B: @naoexisteisso")
    assert "@naoexisteisso" in r["texto"]
    assert r["nao_convertidos"] == ["naoexisteisso"]


def test_o_texto_convertido_passa_na_conferencia():
    r = MOD.traduzir_do_eoficio("NOME: @nomenascido, CPF @cpfnascido")
    assert MOD.conferir_corpo("NASCIMENTO", r["texto"]) == ""


def test_a_conversao_nao_inventa_o_que_nao_tem_coluna():
    """`@numerofiliacao1` é o número da casa, e não há coluna para ele.

    Convertê-lo para o logradouro poria o endereço sem o número sob o rótulo
    do número — dado errado debaixo do rótulo certo.
    """
    assert "numerofiliacao1" not in MOD.DE_PARA_DO_EOFICIO
    assert "enderecocomplementofiliacao1" not in MOD.DE_PARA_DO_EOFICIO
    assert "datargdeclarante1" not in MOD.DE_PARA_DO_EOFICIO


def test_a_filiacao_do_nubente_vai_para_o_papel_PROPRIO():
    """**Este teste guarda uma correção, e a correção é do desenho.**

    Eu havia escrito que a filiação dos nubentes não convertia porque «esta
    casa não sabe de quem é cada um» — conclusão tirada do ACERVO, onde há 12
    `PAI` e 12 `MAE` avulsos nos 20 casamentos. Mas esta casa tem os quatro
    papéis próprios desde 31/08/2026, e quem me desmentiu foi a recusa de
    `lavrar_assento` num teste das telas.
    """
    assert MOD.DE_PARA_DO_EOFICIO["nomefiliacao3"] == "pai_nubente2_nome"
    assert MOD.DE_PARA_DO_EOFICIO["filiacaoconjuge1"] == "filiacao_nubente1"


def test_a_filiacao_do_nubente_NAO_cai_no_pai_avulso(con):
    """Cair no avulso daria os pais de um sob o rótulo do outro.

    E o parentesco é aquilo que a certidão de casamento existe para provar.
    """
    aid = _assento(con, especie="CASAMENTO")
    _pessoa(con, aid, "NUBENTE1", "NELSON FALCAO BARROS")
    _pessoa(con, aid, "NUBENTE2", "EDNA SERRA MONTEIRO")
    _pessoa(con, aid, "PAI", "PAI AVULSO DO ACERVO")
    _pessoa(con, aid, "MAE", "MAE AVULSA DO ACERVO")
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    v = MOD.valores(ctx, "CASAMENTO")
    assert v["pai_nubente1_nome"] == ""
    assert v["pai_nubente2_nome"] == ""
    assert v["filiacao_nubente1"] == ""


def test_a_filiacao_do_nubente_sai_quando_o_papel_proprio_existe(con):
    aid = _assento(con, especie="CASAMENTO")
    _pessoa(con, aid, "MAE_NUBENTE1", "MARIA")
    _pessoa(con, aid, "PAI_NUBENTE1", "JOSE")
    ctx = MOD.contexto(con, aid, serventia=SV, hoje=AGORA)
    v = MOD.valores(ctx, "CASAMENTO")
    assert v["filiacao_nubente1"] == "MARIA e JOSE"


def test_o_email_da_serventia_atravessa_a_conversao_inteiro():
    """**Este teste guarda a segunda correção da medição.**

    `cidadeexemplo@cartorio.ch` está no rodapé de vários dos 13 modelos reais, e
    a minha primeira versão o convertia para `cidadeexemplo{cartorio}.ch` — o
    varredor contava `@cartorio` como claro. **O `@` de um claro não vem
    depois de letra ou dígito.**
    """
    r = MOD.traduzir_do_eoficio(
        "E-mail: cidadeexemplo@cartorio.ch — NOME: @nomenascido")
    assert "cidadeexemplo@cartorio.ch" in r["texto"]
    assert "{registrado_nome}" in r["texto"]
    assert r["nao_convertidos"] == []


def test_modelo_com_email_no_rodape_passa_na_conferencia():
    """Sem a guarda, o rodapé da casa seria recusado como «texto do E-Ofício»."""
    assert MOD.conferir_corpo(
        "NASCIMENTO",
        "{nome} — E-mail: cidadeexemplo.cartorio@gmail.com") == ""


def test_o_claro_depois_de_hifen_continua_sendo_claro():
    """Nos modelos reais há `@municipiofalecimento-@uffalecimento`.

    Hífen e ponto **não** desqualificam: local de e-mail não termina neles.
    """
    r = MOD.traduzir_do_eoficio("@municipiofalecimento-@uffalecimento")
    assert r["texto"] == "{municipio_do_obito}-{uf_do_obito}"


def test_cartorio_e_gmail_sairam_do_de_para():
    """Eram cauda de e-mail, e não claro — entrada com um lado só medido."""
    assert "cartorio" not in MOD.DE_PARA_DO_EOFICIO
    assert "gmail" not in MOD.DE_PARA_DO_EOFICIO


def test_o_mesmo_claro_muda_de_destino_conforme_a_especie():
    """**`@nomefiliacao1` não quer dizer a mesma coisa nas três espécies.**

    No nascimento é o pai do registrado; no casamento é o pai do PRIMEIRO
    nubente — e o E-Ofício numera de 1 a 4 ali, dois para cada um.

    Quem achou isto foi a conversão dos 13 modelos reais de ponta a ponta: doze
    passavam e o nono não, porque saía `{pai_nome}`, que **não existe no
    vocabulário do casamento**.
    """
    assert (MOD.traduzir_do_eoficio("@nomefiliacao1")["texto"]
            == "{pai_nome}")
    assert (MOD.traduzir_do_eoficio("@nomefiliacao1", "CASAMENTO")["texto"]
            == "{pai_nubente1_nome}")


def test_o_de_para_por_especie_so_aponta_para_claro_daquela_especie():
    """Destino que não existe naquela espécie é recusa na conferência."""
    for especie, tabela in MOD.DE_PARA_POR_ESPECIE.items():
        nomes = MOD.nomes_dos_claros(especie)
        ruins = sorted(d for d in tabela.values() if d not in nomes)
        assert ruins == [], f"{especie}: {ruins}"


def test_todo_claro_convertido_passa_na_conferencia_da_sua_especie():
    """**O que a conversão produz tem de ser aceito por quem grava.**

    Sem este teste, o de-para podia apontar para um claro de outra espécie e o
    oficial receberia «converti 13 claros» seguido de «não sei preencher».
    """
    for especie in ESQ.ESPECIES:
        nomes = MOD.nomes_dos_claros(especie)
        proprio = MOD.DE_PARA_POR_ESPECIE.get(especie, {})
        for origem, destino in MOD.DE_PARA_DO_EOFICIO.items():
            alvo = proprio.get(origem, destino)
            if alvo in nomes:
                continue
            # O claro de outra espécie não converte para esta — e é assim que
            # tem de ser; o que não pode é converter para nome inexistente.
            todos: set[str] = set()
            for e in ESQ.ESPECIES:
                todos |= MOD.nomes_dos_claros(e)
            assert alvo in todos, f"{origem} -> {alvo} não existe em espécie nenhuma"


def test_texto_sem_claro_nenhum_atravessa_inteiro():
    r = MOD.traduzir_do_eoficio("Certifico que sim.")
    assert r["texto"] == "Certifico que sim."
    assert r["convertidos"] == [] and r["nao_convertidos"] == []
