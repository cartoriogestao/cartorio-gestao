"""O TERMO do Registro Civil — o texto que vai escrito no livro.

    «vamos seguir no desenvolvimento do nosso módulo maduro e completo de RCPN»
    — o oficial, 29/08/2026

O QUE ESTES TESTES GUARDAM
    **Que o termo congela.** Ele é o papel que o declarante leu e assinou; um
    sistema que o remontasse depois faria o livro de hoje discordar do papel
    assinado ontem.

    **Que a qualificação pula o que falta.** O termo do E-Ofício escrevia a
    frase inteira com os campos vazios no meio — «portador do RG n.º , inscrito
    no CPF n.º ,» —, e papel assinado com buraco no meio é pior que papel sem a
    informação: ele **afirma** que há um RG e não diz qual.

    **Que o cabeçalho não veio junto.** Dois dos treze modelos do E-Ofício
    trazem a oficial anterior, com endereço, telefone e CEP antigos.
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

import rc_termo as TERMO                                         # noqa: E402

SENHA = "Senha#12345"
AGORA = "2026-08-29T09:00"

SERVENTIA = {
    "nome": "SERVENTIA EXTRAJUDICIAL DE CIDADE EXEMPLO",
    "cidade": "Cidade Exemplo", "uf": "MA", "estado": "Maranhão",
    "registrador": "MARIO EXEMPLO DOS SANTOS",
    "titulo": "Tabelião e Oficial de Registro",
}


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela não trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def casa(cg_casa):
    """App/DB compartilhados do modulo (conftest); setup de dominio por teste."""
    db = cg_casa["db"]
    c = cg_casa["cliente"]
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return cg_casa

def _con(casa):
    con = sqlite3.connect(casa["banco"])
    con.row_factory = sqlite3.Row
    return con


def _liso(texto: str) -> str:
    """O texto com o espaco normalizado.

    O MODELO QUEBRA LINHA, e a frase que no papel sai «na ocasiao do parto» vem
    do Jinja com uma quebra no meio, porque a linha do modelo terminou ali. Em
    HTML isso e um espaco; numa comparacao de teste e uma falha.

    **Esta licao ja estava registrada neste projeto**, do teste do cartao de
    autografo, e eu a esqueci ao escrever estes tres testes. Fica aqui a funcao,
    para nao a esquecer de novo.
    """
    return " ".join((texto or "").split())


def _assento(con, *, especie="NASCIMENTO", **extras):
    campos = {
        "serie": "RC_A", "especie": especie, "numero": "8687",
        "matricula": "0000000155202611000226910086871",
        "nome": "MARIA NUNES SANTOS ARAÚJO",
        "data_ato": "2026-08-20", "data_fato": "2026-08-18",
        "hora_fato": "14:30", "cor_raca": "Parda",
        "dnv": "30868091423",
        "local_fato_nome": "Hospital Municipal de Imperatriz",
        "local_fato_endereco": "Rua das Flores, 100, Centro",
        "naturalidade_declarada": "Cidade Exemplo/MA",
        "situacao": "ATIVO", "origem": "SISTEMA", "criado_em": AGORA,
    }
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    cur = con.execute(f"INSERT INTO rc_assentos ({colunas}) VALUES ({marcas})",
                      tuple(campos.values()))
    return int(cur.lastrowid)


def _pessoa(con, assento_id, papel, nome, **extras):
    campos = {"assento_id": assento_id, "papel": papel, "nome": nome,
              "nome_norm": nome.lower(), "criado_em": AGORA}
    campos.update(extras)
    colunas = ", ".join(campos)
    marcas = ", ".join("?" for _ in campos)
    con.execute(f"INSERT INTO rc_pessoas ({colunas}) VALUES ({marcas})",
                tuple(campos.values()))


def _nascimento_completo(con):
    aid = _assento(con)
    _pessoa(con, aid, "DECLARANTE", "JOSÉ SANTOS ARAÚJO",
            nacionalidade="brasileiro", profissao="lavrador",
            documento_tipo="CPF", documento_numero="00000000191",
            naturalidade_cidade="Cidade Exemplo", naturalidade_uf="MA",
            endereco="Rua A, 10", bairro="Centro", cidade="Cidade Exemplo",
            uf="MA")
    _pessoa(con, aid, "PAI", "JOSÉ SANTOS ARAÚJO", nacionalidade="brasileiro",
            profissao="lavrador")
    _pessoa(con, aid, "MAE", "ANA SANTOS", nacionalidade="brasileira",
            profissao="do lar", idade_no_fato="27")
    _pessoa(con, aid, "AVO_PATERNO", "MANOEL ARAÚJO")
    _pessoa(con, aid, "AVO_PATERNA", "JOSEFA ARAÚJO")
    _pessoa(con, aid, "AVO_MATERNO", "PEDRO SANTOS")
    _pessoa(con, aid, "AVO_MATERNA", "MARIA SANTOS")
    return aid


# ------------------------------------------------ o termo se monta


def test_a_frase_ocasional_nao_gruda_no_ponto_da_anterior(casa):
    """Relato #63 — «TEM ESPAÇOS», medido no termo do assento 8266.

    **As frases ocasionais do Registro Civil nascem com o espaço que as separa
    do que vem antes**, e ele é parte da frase, não sobra de digitação:
    `frase_cpf` é « Inscrito no CPF n.º …», `frase_naturalidade` é
    «. A naturalidade declarada é de …», `frase_hora` é «, às 14:30».

    O modelo é montado por `str.format`, e cada valor passava por um
    `str.strip()` antes de entrar — de modo que o termo saía
    «…Lei Federal n.º 6.015/1973.Inscrito no CPF n.º …»: **a frase colada no
    ponto da anterior**, indo assim para `rc_assentos.teor`, que é o próprio
    Livro do Registro Civil e o papel que o declarante assina.

    Medido nos 7.047 assentos em 15/09/2026: 40 termos tinham a colagem, e os
    40 eram NASCIMENTO — exatamente os que trazem CPF. Depois do conserto,
    nenhum; os 22 que sobram estão DENTRO do que o declarante escreveu (o CID,
    o `D.O`, o «MARIA C.DO ARAGAO» do acervo) e ficam como estão: limpar ali
    seria reescrever a declaração.
    """
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        con.execute("UPDATE rc_assentos SET cpf_registrado=? WHERE id=?",
                    ("00000001759", aid))
    liso = _liso(TERMO.montar(con, aid, serventia=SERVENTIA))

    # 09/10/2026: entre a 6.015 e o CPF agora vem «Trata-se de primeiro
    # registro.» e o CPF sai formatado (pedido do oficial).
    assert ("1973. Trata-se de primeiro registro. "
            "Inscrito no CPF n.º 000.000.017-59.") in liso, liso[-260:]
    assert "1973.Inscrito" not in liso
    # E O CONSERTO NÃO PODE TER FEITO O DEFEITO DO OUTRO LADO: guardar o
    # espaço de uma frase não é deixar dois espaços nem espaço antes do ponto.
    assert "  " not in liso
    assert " ." not in liso
    # A frase da hora carrega a vírgula dela, e não a do modelo.
    assert ", às 14:30" in liso


def test_o_termo_de_nascimento_sai_com_o_que_o_livro_precisa(casa):
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA, livro="A-25",
                         folha="102")
    # **O CABEÇALHO SAIU DA LISTA, E NÃO PORQUE O TERMO PIOROU.**
    #
    #   Até 31/08/2026 este teste exigia «REGISTRO DE NASCIMENTO» no texto — era
    #   o cabeçalho dos modelos do E-Ofício. O oficial recusou aqueles modelos em
    #   30/08 («não utilizaremos os modelos ruins do e-ofício, nem em papel»), e
    #   no termo da casa **o cabeçalho é peça à parte**: dois dos treze modelos
    #   do E-Ofício traziam a oficial ANTERIOR impressa dentro do corpo, com
    #   endereço e CEP de outra época — o «carimbo que mente» colado no papel que
    #   vai escrito no livro.
    #
    #   O que este teste guarda continua o mesmo: **o termo traz o que o livro
    #   precisa.** São os dados, e não o timbre.
    for esperado in ("MARIA NUNES SANTOS ARAÚJO", "JOSÉ SANTOS ARAÚJO",
                     "ANA SANTOS", "30868091423", "14:30", "Parda",
                     "Hospital Municipal de Imperatriz"):
        assert esperado in texto, f"faltou «{esperado}» no termo"



def test_o_nome_do_registrado_sai_em_negrito(casa):
    """Ordem do oficial 07/09/2026: nome do registrado sempre em negrito."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "<strong>MARIA NUNES SANTOS ARAÚJO</strong>" in texto


def test_a_idade_da_mae_no_parto_entra_no_termo(casa):
    """Está no termo do E-Ofício — «tendo a mãe, na ocasião do parto, X anos» —
    E na remessa do IBGE, que a cobra como campo próprio."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "na ocasião do parto, 27 anos de idade" in _liso(texto)


def test_a_naturalidade_declarada_cita_o_artigo(casa):
    """O art. 54, § 4º da LRP é a faculdade de declarar como naturalidade o
    município de residência da mãe. **Exigência sem endereço é exigência que
    ninguém confere.**"""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "art. 54, § 4º" in _liso(texto)
    assert "Cidade Exemplo/MA" in _liso(texto)


def test_os_avos_saem_pelo_lado_certo(casa):
    """Os paternos são os do pai. Este projeto mediu a numeração de filiação no
    acervo em 28/08, e o texto do termo a confirma pelo outro lado — o tipo de
    conferência que vale, porque as fontes são independentes."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    # **A REDAÇÃO É «FILIAÇÃO 1 E 2», E ISSO É DELIBERADO.**
    #
    #   Este projeto mediu em 28/08 que quem era pai e quem era mãe **estava
    #   errado em 42 assentos** do acervo, e que nem o código nem o sexo
    #   resolvem sozinhos. Escrever «paternos» e «maternos» no papel assinado
    #   afirma o lado; a filiação numerada afirma só o que o assento garante.
    #
    #   O que o teste prova é o mesmo de antes, e mais forte: os avós de cada
    #   lado seguem a filiação daquele lado, **sem se cruzarem**. Aqui a
    #   filiação 1 é ANA, e por isso os avós dela são PEDRO e MARIA.
    liso = _liso(texto)
    assert "sendo filho de ANA SANTOS" in liso
    assert "avós (da filiação 1): PEDRO SANTOS e MARIA SANTOS" in liso
    assert "(da filiação 2): MANOEL ARAÚJO e JOSEFA ARAÚJO" in liso


# ------------------------------------------------ a qualificação pula o vazio


def test_a_qualificacao_pula_o_que_falta():
    """Papel assinado com buraco no meio é pior que papel sem a informação: ele
    AFIRMA que há um RG e não diz qual."""
    magra = TERMO.qualificacao({"nome": "FULANO",
                                "nacionalidade": "brasileiro"})
    assert magra == "brasileiro"
    assert "RG" not in magra
    assert "CPF" not in magra
    assert "natural de" not in magra


def test_a_qualificacao_monta_o_que_existe():
    cheia = TERMO.qualificacao({
        "nacionalidade": "Brasileiro", "profissao": "Lavrador",
        "documento_tipo": "RG", "documento_numero": "123456",
        "documento_orgao": "SSP/MA",
        "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA",
        "data_nascimento": "1990-01-01",
        "endereco": "Rua A, 10", "cidade": "Cidade Exemplo", "uf": "MA"})
    assert "brasileiro" in cheia
    assert "portador(a) do RG n.º 123456, expedido por SSP/MA" in cheia
    assert "natural de Cidade Exemplo, MA" in cheia
    assert "residente e domiciliado(a) em" in cheia


def test_pessoa_que_nao_existe_nao_vira_frase():
    assert TERMO.qualificacao(None) == ""
    assert TERMO.qualificacao({}) == ""


# ------------------------------------------------ o termo congela


def test_o_termo_nao_se_reescreve(casa):
    """É o papel que o declarante leu e assinou. Corrigir é averbar ao lado."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        TERMO.congelar(con, aid, serventia=SERVENTIA, agora=AGORA)
    with con, pytest.raises(TERMO.TermoError) as erro:
        TERMO.congelar(con, aid, serventia=SERVENTIA, agora=AGORA)
    assert "não se reescreve" in str(erro.value)
    assert "averbe ao lado" in str(erro.value)


def test_congelar_guarda_no_assento(casa):
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        texto = TERMO.congelar(con, aid, serventia=SERVENTIA, agora=AGORA)
    linha = con.execute(
        "SELECT teor, teor_formato FROM rc_assentos WHERE id = ?",
        (aid,)).fetchone()
    assert linha["teor"] == texto
    assert linha["teor_formato"] == "html"


def test_montar_nao_grava(casa):
    """Montar é barato e se pode fazer quantas vezes quiser para ver como fica;
    gravar acontece uma vez, na lavratura."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    TERMO.montar(con, aid, serventia=SERVENTIA)
    TERMO.montar(con, aid, serventia=SERVENTIA)
    teor = con.execute("SELECT teor FROM rc_assentos WHERE id = ?",
                       (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


# ------------------------------------------------ a espécie manda no modelo


def test_a_especie_escolhe_o_modelo_e_nao_o_chamador(casa):
    """Deixar o balcão escolher seria deixar lavrar um óbito com o texto de
    nascimento — e o defeito só apareceria na certidão, meses depois."""
    con = _con(casa)
    with con:
        obito = _assento(con, especie="OBITO", nome="ANTONIO DA SILVA",
                         numero_do="12345678")
        _pessoa(con, obito, "FALECIDO", "ANTONIO DA SILVA",
                idade_no_fato="72 anos", estado_civil="casado")
        _pessoa(con, obito, "DECLARANTE", "MARIA DA SILVA")
    texto = TERMO.montar(con, obito, serventia=SERVENTIA)
    # O que separa os dois modelos não é mais um cabeçalho: é o corpo. O termo
    # de óbito fala de quem faleceu; o de nascimento, de quem compareceu a
    # declarar.
    #
    # **E ESTE TESTE PEGOU UM DEFEITO DE VERDADE**: as marcas do óbito chegavam
    # como lista onde a ponte espera dicionário, e a lavratura estourava com
    # HTTP 500 em vez de sair o termo.
    assert "ANTONIO DA SILVA" in texto
    assert "faleceu" in texto.lower()
    assert "nasceu uma criança" not in texto


def test_o_casamento_traz_o_nome_que_cada_um_passou_a_usar(casa):
    """É o motivo pelo qual a certidão de casamento existe — e medido no
    acervo, o segundo cônjuge muda de nome em 17 dos 20 casamentos."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="CASAMENTO", nome="JOÃO e MARIA",
                       regime_bens="Comunhão parcial de bens")
        _pessoa(con, aid, "NUBENTE1", "JOÃO DA SILVA")
        _pessoa(con, aid, "NUBENTE2", "MARIA SOUZA",
                nome_pos="MARIA SOUZA DA SILVA")
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "Comunhão parcial de bens" in texto
    # A frase da casa nomeia **quem** mudou, e não só o nome novo: num termo com
    # dois nubentes, «passou a assinar X» não diz qual dos dois.
    assert ("Passou o cônjuge MARIA SOUZA a assinar-se MARIA SOUZA DA SILVA"
            in _liso(texto))


def test_livro_e_monta_com_o_modelo_compartilhado(casa):
    """Ordem do oficial: «livro e usa o mesmo modelo». Interdição (e as demais
    do Livro E) montam com `RC_TERMO_LIVRO_E` — não se recusam por falta de
    modelo."""
    con = _con(casa)
    with con:
        aid = _assento(con, especie="INTERDICAO", serie="RC_E",
                       nome="JOÃO DA SILVA INTERDITO")
        _pessoa(con, aid, "REGISTRADO", "JOÃO DA SILVA INTERDITO")
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "JOÃO DA SILVA INTERDITO" in texto
    assert "<strong>JOÃO DA SILVA INTERDITO</strong>" in texto
    assert "REGISTRO DE INTERDIÇÃO" in texto
    assert "MARIO EXEMPLO DOS SANTOS" in texto


def test_as_especies_com_termo_sao_as_do_e_oficio():
    assert set(TERMO.especies_com_termo()) == {
        "NASCIMENTO", "NATIMORTO", "OBITO", "CASAMENTO", "CASAMENTO_RELIGIOSO",
        "AUSENCIA", "INTERDICAO", "TUTELA", "EMANCIPACAO", "UNIAO_ESTAVEL",
        "OPCAO_NACIONALIDADE", "OUTRO"}


# ------------------------------------------------ o cabeçalho não veio junto


def test_o_cabecalho_do_e_oficio_nao_entrou_nos_modelos():
    """Dois dos treze modelos trazem a oficial ANTERIOR, com endereço, telefone
    e CEP antigos. Copiar o cabeçalho traria o oficial de ontem para dentro do
    sistema de hoje — o «carimbo que mente» outra vez."""
    codigo = (RAIZ / "rc_termo.py").read_text(encoding="utf-8")
    for velho in ("ANA CRISTINA", "REPÚBLICA FEDERATIVA DO BRASIL",
                  "Fabricio Ferraz", "65.936-000", "98472-0370"):
        assert velho not in codigo, f"o cabeçalho do E-Ofício vazou: {velho}"


def test_quem_assina_vem_de_fora_do_modelo(casa):
    """Sai da regra viva de quem responde pela serventia, que mora num lugar
    só — a mesma do cartão de autógrafo e da certidão do RI."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    outra = {**SERVENTIA, "registrador": "BEATRIZ EXEMPLO DE SOUZA",
             "titulo": "Tabeliã Registradora Substituta"}
    texto = TERMO.montar(con, aid, serventia=outra)
    assert "BEATRIZ EXEMPLO DE SOUZA" in texto
    assert "Tabeliã Registradora Substituta" in texto
    assert "MARIO" not in texto


# ------------------------------------------------ o catálogo e o acervo


def test_os_tres_termos_estao_no_catalogo_de_modelos():
    """O código é o piso e a tabela é o ajuste — o oficial pode mexer no texto
    sem programador, como no relato #28."""
    import modelos_da_casa as MOD
    for chave in ("RC_TERMO_NASCIMENTO", "RC_TERMO_CASAMENTO",
                  "RC_TERMO_OBITO"):
        assert chave in MOD.POR_CHAVE
        assert len(MOD.padrao_de(chave)) > 500


def test_o_ajuste_da_casa_vence_o_padrao_tambem_no_termo(casa):
    import modelos_da_casa as MOD
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        # **O CLARO É `{nome}`, E NÃO `{{ a.nome }}`** — os três termos do
        # civil passaram ao formato da casa em 31/08/2026. O que este teste
        # guarda não mudou: **o que o oficial escreve é o que vai ao livro**,
        # que é o relato #28. Se um dia o padrão vencer o ajuste dele, é aqui
        # que fica vermelho.
        MOD.salvar(con, "RC_TERMO_NASCIMENTO",
                   corpo="TERMO AJUSTADO — {nome}",
                   quem="mario", agora=AGORA)
    texto = TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "TERMO AJUSTADO —" in texto
    assert "MARIA NUNES SANTOS ARAÚJO" in texto
    assert "<strong>MARIA NUNES SANTOS ARAÚJO</strong>" in texto


def test_os_assentos_do_acervo_aparecem_sem_termo_e_isso_e_certo(casa):
    """Eles NÃO têm o teor, porque o E-Ofício não o guardava. Montá-lo agora
    seria escrever hoje um termo que foi lido e assinado há anos, com os dados
    que sobreviveram à carga — e o que sairia não é o que está no livro."""
    con = _con(casa)
    with con:
        aid = _assento(con, origem="ACERVO")
    faltando = TERMO.assentos_sem_termo(con)
    assert [x["id"] for x in faltando] == [aid]
    with con:
        TERMO.congelar(con, aid, serventia=SERVENTIA, agora=AGORA)
    assert TERMO.assentos_sem_termo(con) == []


# ------------------------------------------------ o modelo quebrado


def test_modelo_quebrado_vira_erro_de_regra_e_nao_HTTP_500(casa):
    import modelos_da_casa as MOD
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        MOD.salvar(con, "RC_TERMO_NASCIMENTO", corpo="Aos {nao_existe} dias.",
                   quem="mario", agora=AGORA)
    with pytest.raises(TERMO.TermoError) as erro:
        TERMO.montar(con, aid, serventia=SERVENTIA)
    # A intenção é a mesma: **modelo torto é erro de regra, com frase de balcão,
    # e não HTTP 500 na cara de quem está lavrando.** O que mudou foi o formato
    # do modelo, e por isso o jeito de torcê-lo.
    assert "claros que este termo não tem" in str(erro.value)
    assert "nao_existe" in str(erro.value)


def test_modelo_do_formato_antigo_e_RECUSADO_e_nao_sai_torto(casa):
    """**Um ajuste do formato antigo sairia literal no papel assinado.**

    Os três termos eram Jinja (`{{ a.nome }}`) até 31/08/2026 e passaram a ser
    `{nome}`. O `str.format` **não estoura** com o texto antigo: ele devolve
    `{ a.nome }`, com uma chave só — e isso iria escrito no livro.

    Medido no servidor em 31/08: `mo_modelos` tem zero linhas, de modo que hoje
    ninguém é alcançado. Quem editar amanhã, sem esta guarda, seria.
    """
    import modelos_da_casa as MOD
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        MOD.salvar(con, "RC_TERMO_NASCIMENTO",
                   corpo="<p>TERMO — {{ a.nome }}</p>", quem="mario",
                   agora=AGORA)
    with pytest.raises(TERMO.TermoError) as erro:
        TERMO.montar(con, aid, serventia=SERVENTIA)
    assert "formato antigo" in str(erro.value)
    assert "Apague o corpo para voltar ao padrão" in str(erro.value)



# ------------------------------------------------ mostrar nao e gravar (relato #38)


def test_texto_para_mostrar_monta_o_vazio_e_nao_grava(casa):
    """Página em branco é defeito; montar a prévia não congela o teor."""
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
    visto = TERMO.texto_para_mostrar(con, aid, serventia=SERVENTIA)
    assert visto["congelado"] is False
    assert "MARIA NUNES SANTOS ARAÚJO" in visto["texto"]
    assert not visto["erro"]
    teor = con.execute("SELECT teor FROM rc_assentos WHERE id=?",
                       (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


def test_texto_para_mostrar_do_importado_tambem_nao_grava(casa):
    con = _con(casa)
    with con:
        aid = _assento(con, especie="OBITO", nome="ANTONIO DA SILVA",
                       origem="EOFICIO", numero_do="12345678")
        _pessoa(con, aid, "FALECIDO", "ANTONIO DA SILVA")
        _pessoa(con, aid, "DECLARANTE", "MARIA DA SILVA")
    visto = TERMO.texto_para_mostrar(con, aid, serventia=SERVENTIA)
    assert visto["do_acervo"] is True
    assert visto["congelado"] is False
    assert "faleceu" in visto["texto"].lower()
    teor = con.execute("SELECT teor FROM rc_assentos WHERE id=?",
                       (aid,)).fetchone()["teor"]
    assert not (teor or "").strip()


def test_texto_para_mostrar_respeita_o_teor_congelado(casa):
    con = _con(casa)
    with con:
        aid = _nascimento_completo(con)
        TERMO.congelar(con, aid, serventia=SERVENTIA, agora=AGORA)
        con.execute("UPDATE rc_assentos SET teor=? WHERE id=?",
                    ("GRAVADO E NAO REMONTAR", aid))
    visto = TERMO.texto_para_mostrar(con, aid, serventia=SERVENTIA)
    assert visto["congelado"] is True
    assert visto["texto"] == "GRAVADO E NAO REMONTAR"


# ------------------------------------------------ o módulo não decide


def test_o_modulo_nao_lavra_nem_numera():
    """Quem lavra é `rc_assento`, com a série, o lugar no livro e o selo. Este
    módulo só escreve o texto do que já foi lavrado."""
    codigo = (RAIZ / "rc_termo.py").read_text(encoding="utf-8")
    assert "INSERT INTO rc_assentos" not in codigo
    assert "nu_numeracao" not in codigo
    publicos = [n for n in dir(TERMO)
                if not n.startswith("_") and callable(getattr(TERMO, n))]
    for nome in publicos:
        for proibido in ("lavrar", "numerar", "selar", "averbar"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"
