"""A CREDENCIAL DAS CENTRAIS — fora do banco, e fora da conversa.

Construída em 02/09/2026, quando o oficial cadastrou o usuário da API da
CENPROT e perguntou *«mando onde?»*.

O QUE ESTES TESTES GUARDAM
      - **a senha nunca entra no banco** — e isto se varre, como se varreu a
        chave da API do Claude;
      - **gravar um ambiente não apaga o outro** — quem informa a produção
        continua com a homologação para testar;
      - **a tela sabe se está informada sem receber o segredo**;
      - **as quatro exigências da CENPROT são conferidas aqui**, com a frase
        que diz o que falta — a Central devolve 401 e não explica;
      - **a recusa diz onde informar**, e não só que falta.
"""
from __future__ import annotations

import contextlib
import json
import sqlite3
import sys
from pathlib import Path

import pytest


pytestmark = pytest.mark.lento  # gate rapido: pytest -m "not lento" — tempfile persistente / config centrais
RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import centrais_cred as CC

BOA = "Senha#12345"          # 11 chars, maiúscula, minúscula, número, especial


def test_a_senha_da_cenprot_passa_pelas_quatro_exigencias(tmp_path):
    """A Central devolve 401 e não diz o que está errado; esta recusa diz."""
    for ruim, pedaco in (("curta1A#", "caracteres"),      # 8 chars mas ok? não: tem tudo
                         ("senha#12345", "maiúscula"),
                         ("SENHA#12345", "minúscula"),
                         ("SenhaSenha#", "número"),
                         ("Senha123456", "caractere especial")):
        if ruim == "curta1A#":
            continue
        with pytest.raises(CC.CredencialError) as e:
            CC.gravar(CC.CENPROT, usuario="u", senha=ruim, pasta=tmp_path)
        assert pedaco in str(e.value)
        assert "Cadastro do Cartório" in str(e.value), (
            "a frase tem de dizer ONDE a senha foi cadastrada")


def test_arquivo_credencial_com_bom_utf8_continua_lendo(tmp_path):
    """Espelho do oficial pode trazer BOM — sem `utf-8-sig`, `tem()` mente."""
    destino = tmp_path / "cenprot.cred"
    corpo = json.dumps(
        {"HOMOLOGACAO": {"usuario": "u", "senha": BOA}}, ensure_ascii=False)
    destino.write_bytes(b"\xef\xbb\xbf" + corpo.encode("utf-8"))
    assert CC.tem(CC.CENPROT, CC.HOMOLOGACAO, tmp_path)
    assert CC.credencial(CC.CENPROT, CC.HOMOLOGACAO, tmp_path)[0] == "u"


def test_a_cra_nao_herda_a_exigencia_da_cenprot(tmp_path):
    """**A CRA não publica exigência nenhuma**, e inventar uma faria o sistema
    recusar uma senha que a Central aceita."""
    CC.gravar(CC.CRA, usuario="cartorio", senha="abc", pasta=tmp_path)
    assert CC.tem(CC.CRA, pasta=tmp_path)


def test_gravar_um_ambiente_nao_apaga_o_outro(tmp_path):
    """No dia da virada, perder a homologação é perder onde testar."""
    CC.gravar(CC.CRA, usuario="teste", senha="a", ambiente=CC.HOMOLOGACAO, pasta=tmp_path)
    CC.gravar(CC.CRA, usuario="valendo", senha="b", ambiente=CC.PRODUCAO, pasta=tmp_path)
    assert CC.credencial(CC.CRA, CC.HOMOLOGACAO, tmp_path) == ("teste", "a")
    assert CC.credencial(CC.CRA, CC.PRODUCAO, tmp_path) == ("valendo", "b")


def test_o_padrao_das_centrais_do_protesto_e_a_producao(tmp_path):
    """**CONTRATO MUDADO EM 14/10/2026** — ordem do oficial: «tire a opção de
    funcionar na homologação, agora é tudo produção». Este teste se chamava
    `test_o_padrao_e_a_homologacao` e cobrava que a CENPROT gravasse na
    gaveta de homologação quando ninguém dissesse o ambiente; agora cobra a
    produção. Sem central, a régua continua a de antes (é a da `onr_api`)."""
    assert CC._ambiente(None) == CC.HOMOLOGACAO
    assert CC._ambiente("sei la") == CC.HOMOLOGACAO
    for central in (CC.CRA, CC.CENPROT, CC.RESOLVE):
        assert CC._ambiente(None, central) == CC.PRODUCAO
        assert CC._ambiente("sei la", central) == CC.PRODUCAO
    CC.gravar(CC.CENPROT, usuario="u", senha=BOA, pasta=tmp_path)
    assert CC.tem(CC.CENPROT, CC.PRODUCAO, tmp_path)
    assert CC.tem(CC.CENPROT, pasta=tmp_path)
    assert not CC.tem(CC.CENPROT, CC.HOMOLOGACAO, tmp_path)


def test_as_tres_do_protesto_tem_so_a_producao_na_tela(tmp_path):
    """14/10/2026: a tabela de credenciais mostra uma linha só para a CRA, a
    CENPROT e a Resolve — a de produção. A de homologação gravada antes NÃO
    se apaga: continua no arquivo, e a linha diz que ela está fora de uso."""
    # 15/10/2026: a CENSEC e o ONR entraram na mesma regra.
    assert CC.CENTRAIS_SO_EM_PRODUCAO == {CC.CRA, CC.CENPROT, CC.RESOLVE,
                                          CC.CENSEC, CC.ONR}
    for central in CC.CENTRAIS_SO_EM_PRODUCAO:
        assert CC.ambientes_de(central) == (CC.PRODUCAO,)
    CC.gravar(CC.CRA, usuario="teste", senha="a", ambiente=CC.HOMOLOGACAO,
              pasta=tmp_path)
    linhas = [x for x in CC.situacao(tmp_path)
              if x["central"] in CC.CENTRAIS_SO_EM_PRODUCAO]
    assert {x["ambiente"] for x in linhas} == {CC.PRODUCAO}
    cra = next(x for x in linhas if x["central"] == CC.CRA)
    assert cra["informada"] is False
    assert cra["fora_de_uso"] == [CC.HOMOLOGACAO]
    # a gaveta antiga continua lá, intocada
    assert CC.credencial(CC.CRA, CC.HOMOLOGACAO, tmp_path) == ("teste", "a")


def test_o_uso_recusa_homologacao_e_testes_com_a_frase(tmp_path):
    """Pendência, intimação ou lote gravados em outro ambiente não se mandam
    à produção em silêncio: os códigos dos dois ambientes se repetem."""
    for central in CC.CENTRAIS_SO_EM_PRODUCAO:
        assert CC.ambiente_de_uso(central) == CC.PRODUCAO
        assert CC.ambiente_de_uso(central, "producao") == CC.PRODUCAO
        for outro in (CC.HOMOLOGACAO, CC.TESTES):
            with pytest.raises(CC.CredencialError) as e:
                CC.ambiente_de_uso(central, outro)
            assert "só em produção" in str(e.value)
            assert CC.VIROU_PRODUCAO_EM[central] in str(e.value)
    assert CC.VIROU_PRODUCAO_EM[CC.CRA] == "14/10/2026"
    assert CC.VIROU_PRODUCAO_EM[CC.CENSEC] == "15/10/2026"
    # as outras Centrais seguem a régua de sempre (o ON-RCPN só tem homologação)
    assert CC.ambiente_de_uso(CC.ONRCPN, CC.HOMOLOGACAO) == CC.HOMOLOGACAO


def test_falta_a_de_producao_e_a_frase_diz_isso(tmp_path):
    """Pedido do oficial em 14/10/2026: «se a credencial de produção não
    existir, a tela deve dizer isso claramente»."""
    with pytest.raises(CC.CredencialError) as e:
        CC.credencial(CC.CRA, pasta=tmp_path)
    assert "PRODUÇÃO" in str(e.value)
    CC.gravar(CC.CRA, usuario="teste", senha="a", ambiente=CC.HOMOLOGACAO,
              pasta=tmp_path)
    with pytest.raises(CC.CredencialError) as e:
        CC.credencial(CC.CRA, pasta=tmp_path)
    assert "PRODUÇÃO" in str(e.value)
    assert "homologação continua guardada" in str(e.value)
    CC.gravar_token(CC.RESOLVE, ambiente=CC.HOMOLOGACAO, token="h",
                    pasta=tmp_path)
    with pytest.raises(CC.CredencialError) as e:
        CC.token_guardado(CC.RESOLVE, pasta=tmp_path)
    assert "PRODUÇÃO" in str(e.value) and "x-api-key" in str(e.value)


def test_a_tela_sabe_sem_receber_o_segredo(tmp_path):
    """Senha mascarada no HTML continua dizendo o tamanho dela."""
    CC.gravar(CC.CENPROT, usuario="cidadeexemplo", senha=BOA, pasta=tmp_path)
    linhas = CC.situacao(tmp_path)
    assert any(x["central"] == "CENPROT" and x["informada"] for x in linhas)
    for x in linhas:
        assert "senha" not in x
        assert BOA not in json.dumps(x, ensure_ascii=False)
    assert CC.usuario(CC.CENPROT, pasta=tmp_path) == "cidadeexemplo"


def test_a_recusa_diz_onde_informar(tmp_path):
    with pytest.raises(CC.CredencialError) as e:
        CC.credencial(CC.CRA, pasta=tmp_path)
    frase = str(e.value)
    assert "Configurações" in frase
    assert "fora do banco" in frase


def test_faltando_um_ambiente_a_recusa_aponta_o_outro(tmp_path):
    """O engano mais provável é escolher o ambiente errado, e não esquecer a
    senha — a frase tem de dizer isso."""
    CC.gravar(CC.CRA, usuario="teste", senha="a", ambiente=CC.HOMOLOGACAO, pasta=tmp_path)
    with pytest.raises(CC.CredencialError) as e:
        CC.credencial(CC.CRA, CC.PRODUCAO, tmp_path)
    assert "homologacao" in str(e.value).lower() or "homologação" in str(e.value).lower()


def test_apagar_tira_so_o_ambiente_pedido(tmp_path):
    """Credencial trocada pela Central tem de sair: senha velha guardada é
    senha que alguém tenta e toma 401 sem entender."""
    CC.gravar(CC.CRA, usuario="a", senha="1", ambiente=CC.HOMOLOGACAO, pasta=tmp_path)
    CC.gravar(CC.CRA, usuario="b", senha="2", ambiente=CC.PRODUCAO, pasta=tmp_path)
    assert CC.apagar(CC.CRA, CC.HOMOLOGACAO, tmp_path) is True
    assert not CC.tem(CC.CRA, CC.HOMOLOGACAO, tmp_path)
    assert CC.tem(CC.CRA, CC.PRODUCAO, tmp_path)
    assert CC.apagar(CC.CRA, CC.HOMOLOGACAO, tmp_path) is False


def test_arquivo_ilegivel_nao_derruba_a_tela(tmp_path):
    """Arquivo corrompido não pode fazer a tela de configurações estourar —
    ela é justamente onde se conserta."""
    CC.caminho(CC.CRA, tmp_path).write_text("isto nao e json", encoding="utf-8")
    assert CC.tem(CC.CRA, pasta=tmp_path) is False
    assert CC.usuario(CC.CRA, pasta=tmp_path) == ""
    with pytest.raises(CC.CredencialError) as e:
        CC.credencial(CC.CRA, pasta=tmp_path)
    assert "de novo" in str(e.value)


def test_central_desconhecida_recusa_dizendo_quais_existem(tmp_path):
    with pytest.raises(CC.CredencialError) as e:
        CC.gravar("SERASA", usuario="u", senha="s", pasta=tmp_path)
    assert "CENPROT" in str(e.value) and "CRA" in str(e.value)


def test_a_senha_nunca_entra_no_banco(tmp_path):
    """**O BANCO VIAJA NO BACKUP, e o backup já saiu da serventia.** É a mesma
    varredura que guarda a chave da API do Claude."""
    CC.gravar(CC.CENPROT, usuario="cidadeexemplo", senha=BOA, pasta=tmp_path)
    banco = tmp_path / "cartorio_gestao.sqlite3"
    con = sqlite3.connect(banco)
    con.execute("CREATE TABLE settings(key TEXT, value TEXT)")
    con.commit()
    con.close()
    bruto = banco.read_bytes()
    assert BOA.encode() not in bruto
    # E o arquivo da credencial NÃO mora dentro do banco.
    assert CC.caminho(CC.CENPROT, tmp_path).is_file()


def test_a_pasta_de_dados_e_a_do_selador():
    """Ao lado de `selador.cred`, `claude.cred` e `secret.key` — os lugares
    que o backup não alcança."""
    p = CC.pasta_de_dados()
    assert p.name == "CartorioGestao"
    assert "ProgramData" in str(p) or "PROGRAMDATA" in str(p).upper()


# ------------------------------------- o ambiente da Central, e não o de sempre
#
# **DOIS DEFEITOS MEDIDOS EM 18/09/2026, e os dois moravam nesta mesma régua.**
# O primeiro: a régua validava contra `AMBIENTES` (dois) e dobrava o `TESTES`
# da Resolve — que declara **três** — para `HOMOLOGACAO`, **em silêncio**. O
# segundo vinha dele: as duas Centrais de token liam a chave pela porta do par,
# e `credencial` recusa quem guarda token — de propósito. Nenhuma intimação
# subiria nunca, com a chave gravada e a frase da tela apontando para o lugar
# errado.


def test_o_ambiente_se_valida_pelos_da_central_e_nao_pelos_dois_de_sempre(tmp_path):
    """**A mesma palavra, dois destinos** — a Resolve declara três ambientes, e
    o `TESTES` dela ia parar no lugar da homologação."""
    # 14/10/2026: na TELA a Resolve tem só a produção (era homologação e
    # produção) — mas a gaveta de testes pedida pelo nome continua sendo a
    # dela, que é o que este teste guarda.
    assert CC.ambientes_de(CC.RESOLVE) == (CC.PRODUCAO,)
    # A régua, agora ciente da Central: o terceiro ambiente é respeitado.
    assert CC._ambiente(CC.TESTES, CC.RESOLVE) == CC.TESTES
    # E `_ambiente` sem central continua sendo o de antes — é o que a `onr_api`
    # usa, e mudar isso mexeria em quem não tem três ambientes.
    assert CC._ambiente(CC.TESTES) == CC.HOMOLOGACAO
    assert CC._ambiente(None) == CC.HOMOLOGACAO


def test_os_tres_ambientes_da_resolve_nao_se_misturam(tmp_path):
    """Gravava-se escolhendo «TESTES» e o arquivo dizia `{"HOMOLOGACAO": …}` —
    de modo que `tem()` respondia **True nos dois**. Dois ambientes num slot só
    é a chave de um indo para o host do outro."""
    CC.gravar_token(CC.RESOLVE, ambiente=CC.TESTES, token="chave-de-testes",
                    pasta=tmp_path)
    guardado = json.loads(CC.caminho(CC.RESOLVE, tmp_path).read_text("utf-8"))
    assert list(guardado) == [CC.TESTES], (
        "o ambiente escolhido na tela tem de ser o que vai para o arquivo")
    assert CC.tem(CC.RESOLVE, CC.TESTES, tmp_path) is True
    assert CC.tem(CC.RESOLVE, CC.HOMOLOGACAO, tmp_path) is False
    assert CC.tem(CC.RESOLVE, CC.PRODUCAO, tmp_path) is False
    assert CC.token_guardado(CC.RESOLVE, CC.TESTES, tmp_path) == "chave-de-testes"


def test_gravar_sem_ambiente_usa_o_primeiro_da_central(tmp_path):
    """O padrão sai da tabela da Central. **Mudado em 14/10/2026**: a Resolve
    tinha homologação como primeiro ambiente; desde a ordem «agora é tudo
    produção», o único é a produção."""
    CC.gravar_token(CC.RESOLVE, token="t", pasta=tmp_path)
    assert CC.token_guardado(CC.RESOLVE, CC.PRODUCAO, tmp_path) == "t"
    assert not CC.tem(CC.RESOLVE, CC.HOMOLOGACAO, tmp_path)
    CC.gravar_token(CC.ONRTDPJ, token="o", pasta=tmp_path)
    assert CC.token_guardado(CC.ONRTDPJ, CC.PRODUCAO, tmp_path) == "o"


def test_a_recusa_do_token_diz_o_endereco_daquela_central(tmp_path):
    """**A frase era uma só para três Centrais diferentes**, e mandava todas ao
    SINTER — onde só uma fica. Quem seguisse a instrução com o ON-RCPN entraria
    no rtdbrasil, não acharia nada, e concluiria que o sistema está errado.

    É a credencial do selador outra vez: rótulo que não é o nome que a Central
    usa manda o oficial procurar o que não existe.
    """
    do_token = {c for c, forma in CC.FORMA_DA_CENTRAL.items() if forma == CC.TOKEN}
    assert set(CC.ONDE_SE_OBTEM_O_TOKEN) == do_token, (
        "Central de token nova nasce sem entrada, e a recusa dela apontaria "
        "para o endereço de outra")

    frases = {}
    for central in sorted(do_token):
        with pytest.raises(CC.CredencialError) as e:
            CC.token_guardado(central, pasta=tmp_path)
        frases[central] = str(e.value)

    # O SINTER é de uma só, e a frase dela diz que o nome do menu confunde.
    assert "SINTER" in frases[CC.ONRTDPJ]
    for outra in (CC.ONRCPN, CC.RESOLVE):
        assert "SINTER" not in frases[outra], (
            f"a recusa do {outra} não pode mandar ao SINTER")

    # E cada uma leva ao lugar certo.
    assert "IdRC" in frases[CC.ONRCPN]
    assert "integracao.idrc.registrocivil.org.br" in frases[CC.ONRCPN]
    assert "x-api-key" in frases[CC.RESOLVE]

    # E nenhuma delas deixa de dizer onde se cadastra nem que é fora do banco.
    for frase in frases.values():
        assert "Configurações" in frase
        assert "fora do banco" in frase


def test_as_tres_centrais_de_token_lem_pela_porta_do_token():
    """**A peça certa lida pela porta errada.** `resolve_api.chave` chamava
    `CRED.credencial` — a porta do par —, e este depósito guarda token: a
    recusa vinha em **toda** chamada, com a chave já gravada, e o módulo da
    Intimação Digital inteiro ficava sem subir nada.

    O teste lê o FONTE de quem devolve o segredo de cada Central de token: as
    três têm de passar por `token_guardado`, e nenhuma por `credencial`.
    """
    import inspect

    import onrcpn_api
    import onrtdpj_api
    import resolve_api

    for modulo, funcao in ((onrcpn_api, "token"),
                           (onrtdpj_api, "token"),
                           (resolve_api, "chave")):
        fonte = inspect.getsource(getattr(modulo, funcao))
        assert "CRED.token_guardado(" in fonte, (
            f"{modulo.__name__}.{funcao} tem de ler pela porta do token")
        assert "CRED.credencial(" not in fonte, (
            f"{modulo.__name__}.{funcao} está lendo pela porta do par, e "
            "`credencial` recusa quem guarda token")



# ------------------------------------------------- e na tela


def test_o_sirc_e_a_setima_central_e_tem_ambiente_unico():
    """PAR (usuário e senha), dentro do corpo SOAP — não HTTP Basic como a
    CRA — e um ambiente só, porque o WSDL público só declara um endereço."""
    assert CC.SIRC in CC.ARQUIVO_DA_CENTRAL
    assert CC.ARQUIVO_DA_CENTRAL[CC.SIRC] == "sirc.cred"
    assert CC.FORMA_DA_CENTRAL[CC.SIRC] == CC.PAR
    assert CC.ambientes_de(CC.SIRC) == (CC.PRODUCAO,)


def test_a_tela_de_configuracoes_oferece_as_cinco_linhas(tmp_path, monkeypatch):
    """Duas Centrais × dois ambientes, e cada uma com o seu formulário."""
    import glob
    import re
    import tempfile
    dados = str(Path(tempfile.gettempdir()) / "test_cred_tela")
    Path(dados).mkdir(parents=True, exist_ok=True)
    from app import create_app
    from database import Database
    app = create_app({"DATA_DIR": dados})
    banco = Database(Path(glob.glob(f"{dados}/*.sqlite3")[0]))
    # Ja existir de outra rodada e o normal, e nao ha o que registrar.
    with contextlib.suppress(Exception):
        banco.create_user("credadm", "Oficial", "Senha#12345", "ADMIN")
    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": "credadm", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    html = c.get("/configuracoes").get_data(as_text=True)
    # **O TÍTULO DIZIA «Centrais de Protesto», E DEIXOU DE SER VERDADE** em
    # 03/09/2026, quando a ONRTDPJ entrou nesta tabela: ela é do RCPJ e do RTD.
    # Quem procurasse o token dela sob um título de Protesto não olharia aqui.
    assert "Centrais — credenciais das APIs" in html
    for valor in ("CRA", "CENPROT", "ONRTDPJ", "HOMOLOGACAO", "PRODUCAO"):
        assert f'value="{valor}"' in html, f"falta a linha de {valor}"
    assert 'action="/configuracoes/central"' in html
    # **A ROTA DA CREDENCIAL NÃO É A DAS CONFIGURAÇÕES**, e é isso que impede
    # a senha de cair em `settings` e viajar no backup.
    assert 'name="senha" type="password"' in html
    # E A TERCEIRA GUARDA UM TOKEN, e não um par: campo de usuário para ela
    # faria alguém preenchê-lo com o CNS só para a tela deixar salvar.
    assert 'name="token" type="password"' in html
    # 14/10/2026: a CRA, a CENPROT e a Resolve não têm mais linha de
    # homologação (o `HOMOLOGACAO` acima é das outras Centrais).
    for central in ("CRA", "CENPROT", "RESOLVE"):
        assert not re.search(
            rf'name="central" value="{central}">\s*<input type="hidden" '
            rf'name="ambiente" value="(HOMOLOGACAO|TESTES)"', html), central
        assert re.search(
            rf'name="central" value="{central}">\s*<input type="hidden" '
            rf'name="ambiente" value="PRODUCAO"', html), central
    # e a caixa do envio automático em homologação saiu
    assert 'name="cra_auto_enviar_homolog"' not in html
    assert "comece pela de homologação" not in html


def test_a_tela_de_configuracoes_explica_de_onde_vem_a_credencial_do_sirc(
        tmp_path, monkeypatch):
    """**RELATADO PELO OFICIAL EM 14/09/2026**: "não achei onde colocar a
    credencial de acesso ao sirc. eh a mesma que eu uso pra acessar?" — a
    linha do SIRC aparecia na tabela sem UMA FRASE dizendo de onde vem a
    credencial, ao contrário das outras quatro Centrais desta lista, que
    já tinham parágrafo próprio."""
    import glob
    import re
    dados = str(tmp_path / "dados_sirc_tela")
    Path(dados).mkdir(parents=True, exist_ok=True)
    from app import create_app
    from database import Database
    app = create_app({"DATA_DIR": dados})
    banco = Database(Path(glob.glob(f"{dados}/*.sqlite3")[0]))
    banco.create_user("credadm2", "Oficial", "Senha#12345", "ADMIN")
    c = app.test_client()
    pega = lambda h: re.search(r'name="csrf_token"[^>]*value="([^"]+)"', h).group(1)
    c.post("/login", data={"username": "credadm2", "password": "Senha#12345",
                           "csrf_token": pega(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    html = c.get("/configuracoes").get_data(as_text=True)
    assert 'value="SIRC"' in html
    assert "sirc.dataprev.gov.br" in html
    assert "mesma senha" in html.lower()


def test_a_senha_digitada_nao_volta_para_a_tela(tmp_path):
    """Nem mascarada: senha mascarada no HTML continua dizendo o tamanho."""
    CC.gravar(CC.CENPROT, usuario="cidadeexemplo", senha=BOA, pasta=tmp_path)
    for linha in CC.situacao(tmp_path):
        assert BOA not in str(linha)
        assert "*" * 4 not in str(linha)
