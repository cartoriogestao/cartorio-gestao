"""AS REGRAS DESTA CASA — a ajuda passa a ler o arquivo que as guarda.

A FRASE DO OFICIAL, EM 15/09/2026:

    «A ajuda passa a ler o CLAUDE.md, fatiado por seção.»

E O QUE ESTES TESTES GUARDAM, em ordem de importância:

1. **O ARQUIVO CHEGA AO SERVIDOR.** Ele mora na raiz do projeto — fora da pasta
   que o `.cgu` empacota e fora da pasta que o `ATUALIZAR_SISTEMA.cmd` copia —,
   e enquanto não viajava a ajuda respondia pela regra geral do assunto. Há
   teste para os DOIS transportes, e não para um: consertar um só deixaria o
   outro caminho mentindo.

2. **O QUE VAI NO CONTEXTO É O ÍNDICE, E NÃO A PROSA.** São 385 mil caracteres.
   Mandá-los em toda pergunta custaria em toda pergunta — a mesma regra da
   fatia que `ajuda_projeto` já segue com os documentos.

3. **O MÓDULO NÃO GUARDA CÓPIA DE NENHUMA REGRA.** Cópia com o tempo diverge do
   original, e quem lê a velha não sabe que é a velha. É a `normalizar_nome`
   pela enésima vez, e aqui se mede em vez de se prometer.

4. **O CARIMBO É CONFERIDO, E NÃO ACREDITADO.** Foi este projeto que escreveu
   «carimbo que mente é pior que carimbo nenhum» — e o próprio `CLAUDE.md` já
   mentiu duas vezes, dizendo 3.6.79 enquanto o `app.py` estava na 3.6.129.

5. **O QUE NÃO SE PODE CONFERIR VEM DITO, E NÃO COM VEREDITO INVENTADO.**
   A suíte não viaja com a atualização: contar `def test_` acharia outra coisa.
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

import pytest

RAIZ = Path(__file__).resolve().parent.parent

# O ATUALIZADOR MORA AO LADO DA PASTA INSTALÁVEL (INSTALAR_CARTORIO_GESTAO); no
# SANDBOX ele fica em `SERVIDOR/`, e o repositório público não traz nenhum dos
# dois. Sem ele o teste se declara pulado, em vez de estourar por arquivo ausente.
_ATUALIZADOR = next((p for p in (RAIZ.parent / "ATUALIZAR_SISTEMA.cmd",
                                 RAIZ.parent.parent / "SERVIDOR" / "ATUALIZAR_SISTEMA.cmd")
                     if p.exists()), RAIZ.parent / "ATUALIZAR_SISTEMA.cmd")


def _ler_atualizador() -> str:
    if not _ATUALIZADOR.exists():
        import unittest
        raise unittest.SkipTest("o ATUALIZAR_SISTEMA.cmd não está ao lado desta árvore")
    return _ATUALIZADOR.read_text(encoding="utf-8", errors="replace")
sys.path.insert(0, str(RAIZ))

import agente_ferramentas as AF                                   # noqa: E402
import ajuda_regras as REGRAS                                     # noqa: E402


# ------------------------------------------------------------------ o arquivo


def test_as_regras_desta_casa_sao_lidas():
    """O arquivo está onde a ajuda o procura, e tem seções de verdade."""
    assert REGRAS.disponivel(), (
        "o arquivo das regras não foi achado em "
        f"{[str(c) for c in REGRAS._caminhos()]}"
    )
    indice = REGRAS.indice()
    assert len(indice) > 20, "o arquivo das regras perdeu as seções"
    assert REGRAS.onde().endswith("CLAUDE.md")


def test_o_indice_traz_titulo_e_tamanho_e_NAO_traz_o_texto():
    """A medição que decide o custo da ajuda: vai o índice, não a biblioteca."""
    indice = REGRAS.indice()
    secao = max(indice, key=lambda s: s["caracteres"])
    assert secao["caracteres"] > 10_000, "a maior seção deveria ser grande"

    contexto = "\n".join(REGRAS.indice_para_o_contexto())
    # o corpo da maior seção não pode estar no índice
    corpo = REGRAS.ler(str(secao["n"]))
    alguma_linha = [linha for linha in corpo.splitlines() if len(linha.strip()) > 120]
    assert alguma_linha, "a maior seção não tem linha longa para conferir"
    assert alguma_linha[0].strip() not in contexto
    assert secao["titulo"] in contexto


def test_le_a_secao_pelo_numero_e_pelo_titulo():
    por_numero = REGRAS.ler("2")
    por_titulo = REGRAS.ler("Antes de escrever")
    assert "regras, seção 2" in por_numero
    assert por_numero == por_titulo


def test_secao_que_nao_existe_recusa_dizendo_a_faixa():
    with pytest.raises(REGRAS.RegraError) as erro:
        REGRAS.ler("9999")
    assert "9999" in str(erro.value)


def test_titulo_ambiguo_recusa_e_diz_quais_sao():
    """«selo» casa com mais de uma seção, e escolher por conta própria seria a
    ferramenta decidindo o que a pergunta era."""
    with pytest.raises(REGRAS.RegraError) as erro:
        REGRAS.ler("selo")
    mensagem = str(erro.value)
    assert "casa com" in mensagem
    assert mensagem.count("(") >= 2, "a recusa deve nomear as seções que casaram"


def test_procurar_devolve_as_linhas_com_a_secao_de_origem():
    """É o caminho curto e o mais usado: quem pergunta «como se decide sobre
    selo» quer a frase que decide, e não a seção inteira."""
    achado = REGRAS.procurar("carimbo que mente")
    assert "linha(s) com" in achado
    assert "[seção " in achado
    assert "carimbo que mente" in achado


def test_termo_que_a_casa_nunca_escreveu_diz_que_NAO_escreveu():
    """Ausência de achado com cara de medição é o defeito que este projeto mais
    paga. Aqui o vazio VEM DITO: «a casa não escreveu nada sobre isso» — e não
    «a regra é a que parece natural»."""
    vazio = REGRAS.procurar("xilofone azulado tonitroante")
    assert "Nenhuma linha" in vazio
    assert "não que a regra" in vazio


def test_procurar_sem_termo_e_recusa():
    with pytest.raises(REGRAS.RegraError):
        REGRAS.procurar("   ")


# ----------------------------------------------------------------- o carimbo


def test_o_carimbo_do_arquivo_e_lido():
    """A versão e o tamanho da suíte saem do texto do arquivo.

    **A PRIMEIRA VERSÃO DESTA LEITURA NÃO ACHAVA A VERSÃO**, e não avisava: o
    padrão esperava «versão **3.6.130**» e o arquivo escreve «**versão
    3.6.130**». O `re.search` devolvia `None` e o veredito saía
    «nao_conferivel» com a maior tranquilidade — ausência de achado com cara de
    medição. Por isso aqui se exige o número, e não «não veio vazio»."""
    carimbo = REGRAS.carimbo()
    assert re.fullmatch(r"\d+\.\d+\.\d+", carimbo["versao"]), carimbo
    assert re.fullmatch(r"[\d.]+", carimbo["testes"]), carimbo


def test_versao_atras_do_sistema_gera_aviso():
    """O sistema numa versão adiante do material escrito: é o dia em que a
    ajuda diria ao balcão que o sistema está numa versão e o arquivo em outra."""
    atras = REGRAS.conferir("99.0.0")
    versao = [a for a in atras if a["o_que"] == "a versão escrita nas regras"][0]
    assert versao["veredito"] == "atras"
    assert versao["no_ar"] == "99.0.0"

    resumo = REGRAS.resumo_da_conferencia("99.0.0")
    assert resumo.startswith("(Atenção")
    assert "99.0.0" in resumo


def test_versao_igual_nao_gera_aviso_nenhum(tmp_path):
    """**Vazio é o caso normal**, e o silêncio é o que faz o aviso valer: um
    bloco dizendo «tudo certo» em toda pergunta custaria token em toda pergunta
    para não dizer nada.

    **E A PRIMEIRA VERSÃO DESTE TESTE PERGUNTAVA A COISA ERRADA — medido em
    16/09/2026.** Ele passava `carimbo()["versao"]` como «a versão que roda» e
    exigia silêncio. Mas a conferência tem **dois carimbos** — o das regras e o
    do `ROTEIRO_*.md` mais novo —, e naquele dia o roteiro era o 3.6.132 contra
    um carimbo de 3.6.136: **o aviso era devido, e o teste acusava o produto por
    um defeito dele mesmo** — usar um carimbo onde havia dois.

    Aqui o outro carimbo é montado do mesmo tamanho, que é a única situação em
    que o silêncio é devido: **tudo o que está escrito acompanha o que roda.**
    """
    igual = REGRAS.carimbo()["versao"]
    docs = tmp_path / "DOCUMENTACAO"
    docs.mkdir()
    (docs / f"ROTEIRO_{igual}.md").write_text("roteiro do dia", encoding="utf-8")

    assert REGRAS.resumo_da_conferencia(igual, docs) == ""
    versao = [a for a in REGRAS.conferir(igual, docs)
              if a["o_que"] == "a versão escrita nas regras"][0]
    assert versao["veredito"] == "de_acordo"


def test_o_roteiro_atras_e_avisado_SEM_contaminar_o_outro_carimbo(tmp_path):
    """**SÃO DOIS CARIMBOS, E O AVISO DIZ QUAL DOS DOIS ESTÁ ATRÁS.**

    O `ROTEIRO_*.md` é escrito quando há entrega ou interrupção — não a cada
    versão —, e por isso ele vive atrás do `app.py` entre uma coisa e outra. O
    que não pode acontecer é o aviso dele sair com a cara do outro: quem lê «as
    regras estão atrás», vai conferir o `CLAUDE.md`, encontra o carimbo certo e
    conclui que a ajuda mente sobre o que leu.

    O caso é montado, e não medido na pasta real: aqui o que se mede é a
    **régua**, e a pasta de verdade muda a cada versão.
    """
    igual = REGRAS.carimbo()["versao"]
    docs = tmp_path / "DOCUMENTACAO"
    docs.mkdir()
    (docs / "ROTEIRO_1.0.0.md").write_text("roteiro velho", encoding="utf-8")

    resumo = REGRAS.resumo_da_conferencia(igual, docs)
    assert resumo.startswith("(Atenção")
    assert "o roteiro mais novo" in resumo
    assert "a versão escrita nas regras" not in resumo, (
        "o aviso do roteiro saiu com a cara do carimbo das regras — quem lê "
        "vai conferir o CLAUDE.md e encontrá-lo certo")


def test_o_que_nao_se_confere_vem_dito_e_nao_com_veredito_inventado():
    """O número de testes não se mede nesta instalação — a suíte não viaja com
    a atualização. Ele aparece como NÃO CONFERÍVEL, com o motivo."""
    testes = [a for a in REGRAS.conferir("3.6.130")
              if a["o_que"] == "o número de testes coletados"]
    if testes:
        assert testes[0]["veredito"] == "nao_conferivel"
        assert "não viaja" in testes[0]["nota"]


def test_sem_o_arquivo_a_conferencia_DIZ_que_ele_falta(monkeypatch):
    """Instalação em que a atualização foi feita à mão fica sem o arquivo. O
    que não pode acontecer é ela responder como se as regras não existissem."""
    monkeypatch.setattr(REGRAS, "arquivo", lambda: None)
    monkeypatch.setattr(REGRAS, "_secoes", lambda: [])
    achados = REGRAS.conferir("3.6.130")
    assert achados[0]["veredito"] == "ausente"
    assert "não está nesta instalação" in achados[0]["nota"]
    assert REGRAS.disponivel() is False
    with pytest.raises(REGRAS.RegraError):
        REGRAS.ler("1")
    assert REGRAS.carimbo()["versao"] == ""
    # e o contexto diz que falta, em vez de sair calado
    assert REGRAS.resumo_da_conferencia("3.6.130").startswith("(Atenção")


# ------------------------------------------------- o módulo não guarda cópia


def test_o_modulo_nao_guarda_texto_de_regra_dentro_dele():
    """**Nada de cópia.** Se um dia alguém colar um trecho das regras aqui
    dentro «para não ler o arquivo toda vez», o trecho envelhece e a ajuda passa
    a responder pela versão velha — sem nada dizendo que é a velha.

    Medido no que o Python lê de fato: os literais longos do módulo não podem
    aparecer no arquivo das regras.
    """
    fonte = (RAIZ / "ajuda_regras.py").read_text(encoding="utf-8")
    textos = [n.value for n in ast.walk(ast.parse(fonte))
              if isinstance(n, ast.Constant) and isinstance(n.value, str)
              and len(n.value) >= 120]
    regras = REGRAS.arquivo().read_text(encoding="utf-8", errors="replace")
    colados = [t for t in textos if t.strip() and t.strip() in regras]
    assert not colados, (
        "ajuda_regras.py guarda trecho das regras dentro dele: "
        f"{[t[:60] for t in colados]}"
    )


# ------------------------------------------------------------- a ferramenta


def _contexto():
    return AF.Contexto(db=None, raiz=RAIZ, pasta_de_dados=RAIZ, agora="2026-09-15T14:00",
                       usuario="jean", sessao_id=1, versao=REGRAS.carimbo()["versao"])


def test_a_ferramenta_de_regras_e_de_LEITURA_e_vai_para_todo_mundo():
    """Ler as regras da casa não é o que só o ADMIN faz — é o que o balcão
    precisa para não responder ao cliente pela regra geral."""
    assert "ler_regras" in AF.FERRAMENTAS_DA_AJUDA
    assert "ler_regras" not in AF.FERRAMENTAS_DA_AJUDA_SO_ADMIN
    for admin in (True, False):
        nomes = [f.nome for f in AF.catalogo_da_ajuda(admin=admin)]
        assert "ler_regras" in nomes
    ferramenta = AF.POR_NOME["ler_regras"]
    assert ferramenta.e_escrita is False
    assert ferramenta.tipo == AF.LEITURA


def test_a_ferramenta_sem_argumento_devolve_o_indice():
    saida = AF.executar(_contexto(), "ler_regras", {})
    assert not saida.get("erro"), saida
    conteudo = saida["conteudo"]
    assert "As regras do projeto CartorioGestao" in conteudo
    assert re.search(r"\n\d+\. ", conteudo), "o índice não veio"


def test_a_ferramenta_le_a_secao_e_procura_o_assunto():
    por_secao = AF.executar(_contexto(), "ler_regras", {"secao": "2"})
    assert not por_secao.get("erro")
    assert "regras, seção 2" in por_secao["conteudo"]

    por_termo = AF.executar(_contexto(), "ler_regras", {"procura": "carimbo que mente"})
    assert not por_termo.get("erro")
    assert "carimbo que mente" in por_termo["conteudo"]


def test_a_ferramenta_recusa_com_a_frase_do_balcao_e_nao_com_traceback():
    """Erro de regra é subclasse de `ValueError` com mensagem pronta — a regra
    da casa. A falha de ferramenta volta como informação para o modelo, e não
    como turno perdido por HTTP 500."""
    saida = AF.executar(_contexto(), "ler_regras", {"secao": "9999"})
    assert saida["erro"] is True
    assert "9999" in saida["conteudo"]


def test_todo_erro_de_ferramenta_e_ValueError():
    """**O CONTRATO QUE FAZ A LISTA DE `except` SER DESNECESSÁRIA.**

    `executar` apanha `ValueError`, e é isso que faz uma ferramenta escrita
    amanhã se comportar como as de hoje sem que ninguém acrescente o erro dela
    numa linha. Se alguém declarar `class MinhaError(Exception)`, o `except` não
    a pega e a consulta do balcão morre com rastreio de erro — que é o defeito
    que apareceu em 15/09/2026, quando a leitura das regras da casa nasceu e o
    `RegraError` dela não estava na lista escrita à mão.

    A varredura é por `ast`, e não por palavra no arquivo: `class XError(...)` é
    o que o Python lê.
    """
    modulos = ["agente_ferramentas.py", "agente_provedores.py",
               "ajuda_problemas.py", "ajuda_regras.py"]
    declarados: list[tuple[str, str, str]] = []
    for nome in modulos:
        arvore = ast.parse((RAIZ / nome).read_text(encoding="utf-8"))
        for no in ast.walk(arvore):
            if not isinstance(no, ast.ClassDef) or not no.name.endswith("Error"):
                continue
            bases = [ast.unparse(b) for b in no.bases]
            declarados.append((nome, no.name, ", ".join(bases)))
    assert len(declarados) >= 4, declarados
    fora = [(m, c, b) for m, c, b in declarados if "ValueError" not in b]
    assert not fora, (
        "erro de ferramenta que não é ValueError: o `executar` não vai apanhá-lo "
        f"e a consulta do balcão morre com rastreio de erro — {fora}"
    )


def test_o_que_a_barreira_faz_com_o_texto_das_regras_e_medido():
    """**O ARQUIVO DAS REGRAS ATRAVESSA A BARREIRA DE PRIVACIDADE**, e isso
    precisa ser medido e não suposto: ele cita e-mail de Central, IP de
    aparelho e nome de credencial, tudo em prosa.

    A barreira roda sobre tudo o que sai para o provedor, e o que ela não
    mascarar tem de ser lido por alguém. Aqui se exige que a leitura **não
    estoure** — porque um `PrivacidadeError` no meio de uma consulta do balcão
    é a ajuda inteira fora do ar por causa de um trecho de documentação — e que
    o resultado ainda diga o que a seção diz.
    """
    saida = AF.executar(_contexto(), "ler_regras", {"procura": "credencial"})
    assert not saida.get("erro"), saida.get("conteudo")
    assert saida["conteudo"].strip(), "a barreira devolveu vazio"


# ------------------------------------------------------- os dois transportes


def _pacote():
    """O `criar_atualizacao.py` é script de ferramenta, e não módulo instalado."""
    import importlib.util

    caminho = RAIZ / "tools" / "criar_atualizacao.py"
    spec = importlib.util.spec_from_file_location("criar_atualizacao", caminho)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_o_pacote_cgu_leva_o_arquivo_das_regras():
    """O `criar_atualizacao.py` empacota a pasta do programa, e o arquivo das
    regras mora UM NÍVEL ACIMA dela. Sem o `DE_FORA` ele não viaja, e a ajuda
    do servidor fica sem as regras."""
    CA = _pacote()

    # A ORDEM DO PAR SE DESFAZ AQUI, e é legítimo: `todos_os_arquivos` devolve
    # `(arquivo, destino)`, como o `iter_files` — **e já devolveu o contrário**,
    # pelo dicionário de dentro, o que quebrou o empacotamento em 15/09/2026.
    por_destino = {rel: p for p, rel in CA.todos_os_arquivos(RAIZ)}
    assert "CLAUDE.md" in por_destino, sorted(por_destino)[:20]
    # entra UMA vez: destino repetido no manifesto é o pacote se sobrescrevendo
    destinos = [rel for _p, rel in CA.todos_os_arquivos(RAIZ)]
    assert len(destinos) == len(set(destinos))

    # e o que veio de fora é o arquivo das regras de verdade
    texto = por_destino["CLAUDE.md"].read_text(encoding="utf-8",
                                               errors="replace")
    assert texto.startswith("# CartorioGestao")
    assert REGRAS._quebrar(texto), "o arquivo empacotado não tem seções"


def test_a_atualizacao_rapida_copia_os_documentos_e_as_regras():
    """O `ATUALIZAR_SISTEMA.cmd` é O OUTRO caminho, e até 15/09/2026 não copiava
    `.md` nenhum: o servidor ficou com TRÊS documentos contra 169 da árvore de
    desenvolvimento, e a ajuda respondia sobre uma biblioteca vazia sem nada
    dizendo que ela não tinha chegado."""
    cmd = _ler_atualizador()
    assert "CLAUDE.md" in cmd, "a atualização rápida não leva as regras da casa"
    assert "DOCUMENTACAO" in cmd, "a atualização rápida não leva os documentos"
    # e conferir que chegou, em vez de supor que chegou
    assert '%PROG%\\CLAUDE.md' in cmd, (
        "o CLAUDE.md não é carimbado no destino: ele vem por `copy`, de um "
        "caminho próprio, porque mora fora da pasta que o robocopy espelha")

    #   A CONFERÊNCIA É MEDIDA, E NÃO ESCRITA — 16/09/2026.
    #
    #   Aqui havia `assert "A ajuda nao vai saber como se decide aqui" in cmd`:
    #   a frase de AVISO, num comentário do .cmd, dizendo que sem o `CLAUDE.md` a
    #   ajuda ficaria cega. **Aviso escrito em comentário não é conferência** — e
    #   quem reescrevesse o bloco apagava junto a frase que avisava, deixando o
    #   teste exigindo o contrário do que devia. Foi o que aconteceu.
    #
    #   O que se exige agora é o que MEDE, e quem mede é o conferidor: ele
    #   compara a instalação com a pasta que viajou, arquivo por arquivo, e o
    #   `CLAUDE.md` entra nessa conta pelo `DE_FORA` do empacotador (há teste
    #   próprio disso em `test_pacote_nao_leva_lixo.py`).
    assert "conferir_atualizacao.py" in cmd, (
        "a atualização rápida não confere o que chegou: sem o conferidor, o "
        "CLAUDE.md e os documentos que faltarem não aparecem em aviso nenhum")
    assert '--arvore "%FONTE%"' in cmd, (
        "o conferidor precisa medir contra a MESMA pasta que acabou de ser "
        "copiada — apontado para outra, ele daria a pasta errada por conferida")
