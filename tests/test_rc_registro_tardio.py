"""O registro de nascimento tardio — art. 249, e o modelo que afirma demais.

O QUE ESTES TESTES GUARDAM
    **Que a dispensa das testemunhas é CONDICIONADA, e as condições são
    cumulativas.** O modelo do E-Ofício desta casa traz impresso, em toda folha,
    «Dispensada a presença de testemunhas» — e o art. 249, II diz que a regra é
    colher **duas**, com dispensa num caso só: menor de 12 anos *e* com DNV.

    Um papel que afirma a dispensa sempre faz o balcão deixar de colher
    testemunha onde ela é obrigatória — e é o declarante que assina «sob as penas
    da lei».

    **Que não saber a idade não dispensa.** Errar para o lado da dispensa produz
    requerimento sem as testemunhas que a lei exige, e o defeito só aparece se
    alguém contestar o registro.
"""
from __future__ import annotations

import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))

import rc_registro_tardio as T                                   # noqa: E402


# ------------------------------------------------ a norma


def test_o_lugar_do_registro_e_o_da_residencia():
    """É competência, e não preferência — registrar pelo local do parto seria
    lavrar em serventia incompetente."""
    assert "residência do interessado" in T.ONDE_SE_REGISTRA
    assert "não no do" in T.ONDE_SE_REGISTRA


def test_a_regra_e_colher_duas_testemunhas():
    assert T.TESTEMUNHAS_EXIGIDAS == 2
    assert "duas testemunhas" in T.REGRA_DAS_TESTEMUNHAS
    assert "art. 249, II" in T.REGRA_DAS_TESTEMUNHAS


def test_a_dispensa_e_de_um_caso_so():
    assert T.IDADE_LIMITE_DA_DISPENSA == 12
    assert "menor de 12 anos" in T.QUANDO_SE_DISPENSA
    assert "DNV" in T.QUANDO_SE_DISPENSA


def test_a_dnv_e_dispensada_justamente_no_tardio():
    """O art. 236 a torna obrigatória, ressalvado o tardio — que é o caso de
    quem não a tem."""
    assert "ressalvada" in T.DNV_NO_TARDIO
    assert "art. 236" in T.DNV_NO_TARDIO


def test_o_arquivo_e_de_vinte_anos_e_quem_descarta_e_o_juiz():
    """Não é a serventia que decide incinerar."""
    assert T.ARQUIVO_ANOS == 20
    assert "juiz" in T.COMO_SE_DESCARTA


def test_os_documentos_do_paragrafo_2_sao_desejaveis():
    """«Sempre que possível» é do artigo. Tratá-los como obrigatórios travaria o
    registro de quem não os tem — que é exatamente quem precisa do tardio."""
    assert "sempre que possível" in T.SAO_DESEJAVEIS_E_NAO_CONDICAO.lower()
    assert len(T.DOCUMENTOS_DESEJAVEIS) == 3
    chaves = {x["chave"] for x in T.DOCUMENTOS_DESEJAVEIS}
    assert chaves == {"DNV", "CERTIDAO_NEGATIVA", "CERTIDOES_IRMAOS"}


def test_o_rito_tem_os_quatro_incisos():
    assert [x["inciso"] for x in T.O_RITO] == ["I", "II", "III", "IV"]
    junto = " ".join(x["o_que"] for x in T.O_RITO)
    assert "autuado e numerado" in junto
    assert "juízo competente" in junto


def test_o_arquivo_obrigatorio_cita_o_provimento_149():
    assert "art. 211, II" in T.ARQUIVO_OBRIGATORIO
    assert "149/2023" in T.ARQUIVO_OBRIGATORIO


# ------------------------------------------------ a dispensa


def test_dispensa_so_com_as_DUAS_condicoes():
    """O «e» é do artigo. Tratá-las como alternativas dispensaria testemunha de
    um adulto que trouxe DNV, ou de uma criança que não trouxe — e nos dois casos
    o art. 249, II manda colher."""
    assert T.dispensa_testemunhas(idade=5, tem_dnv=True)["dispensada"]
    assert not T.dispensa_testemunhas(idade=5, tem_dnv=False)["dispensada"]
    assert not T.dispensa_testemunhas(idade=30, tem_dnv=True)["dispensada"]
    assert not T.dispensa_testemunhas(idade=30, tem_dnv=False)["dispensada"]


def test_doze_anos_ja_nao_dispensa():
    """«menor de 12 anos» — quem tem 12 não é menor de 12."""
    assert not T.dispensa_testemunhas(idade=12, tem_dnv=True)["dispensada"]
    assert T.dispensa_testemunhas(idade=11, tem_dnv=True)["dispensada"]


def test_idade_desconhecida_nao_dispensa():
    """Não saber não é o mesmo que saber que é menor, e o erro para o lado da
    dispensa produz requerimento sem as testemunhas que a lei exige."""
    for ruim in (None, "", "não sei", "abc"):
        r = T.dispensa_testemunhas(idade=ruim, tem_dnv=True)
        assert not r["dispensada"], f"«{ruim}» não devia dispensar"
        assert r["quantas"] == 2


def test_a_dispensa_diz_sempre_por_que():
    """Quem lê a tela precisa saber por que colhe ou por que não colhe — senão a
    régua vira caixa-preta e alguém a contorna."""
    for idade, dnv in ((5, True), (5, False), (30, True), (None, True)):
        r = T.dispensa_testemunhas(idade=idade, tem_dnv=dnv)
        assert len(r["porque"]) > 20, f"({idade}, {dnv}) sem explicação"


def test_a_dispensa_tambem_alcanca_a_entrevista():
    """O art. 249, II dispensa «a presença das testemunhas **e a entrevista do
    registrando**» — as duas juntas, no mesmo caso."""
    assert T.dispensa_testemunhas(idade=5, tem_dnv=True)["dispensa_entrevista"]
    assert not T.dispensa_testemunhas(
        idade=30, tem_dnv=True)["dispensa_entrevista"]


# ------------------------------------------------ a conferência


def test_o_adulto_sem_dnv_precisa_das_duas_testemunhas():
    faltas = T.o_que_conferir(idade=30, tem_dnv=False, testemunhas=0)
    assert any("2 testemunhas" in f for f in faltas)
    assert any("DNV" in f for f in faltas)


def test_com_as_duas_testemunhas_a_falta_some():
    faltas = T.o_que_conferir(idade=30, tem_dnv=False, testemunhas=2)
    assert not any("testemunhas" in f for f in faltas)


def test_a_crianca_com_dnv_nao_falta_nada():
    assert T.o_que_conferir(idade=5, tem_dnv=True) == []


def test_uma_testemunha_so_nao_basta():
    faltas = T.o_que_conferir(idade=30, tem_dnv=True, testemunhas=1)
    assert any("2 testemunhas" in f for f in faltas)


def test_a_conferencia_nao_recusa_nada():
    """O registro de nascimento é imperativo legal (art. 250), e travar o
    requerimento por documento faltante seria negar registro a quem mais precisa
    dele. Ele diz o que falta; decidir é do oficial."""
    publicos = [n for n in dir(T)
                if not n.startswith("_") and callable(getattr(T, n))]
    for nome in publicos:
        for proibido in ("recusar", "impedir", "travar", "bloquear"):
            assert proibido not in nome.lower(), f"`{nome}` faz o que não deve"


# ------------------------------------------------ o modelo que afirma demais


def test_o_modulo_nao_copia_o_cabecalho_do_eoficio():
    """Dois dos treze modelos trazem a oficial ANTERIOR, com endereço e telefone.
    Copiá-la traria o oficial de ontem para dentro do sistema de hoje — o
    «carimbo que mente» outra vez."""
    codigo = (RAIZ / "rc_registro_tardio.py").read_text(encoding="utf-8")
    for vazado in ("ANA CRISTINA", "MURAI", "98472-0370",
                   "cidadeexemplo.cartorio@gmail.com"):
        assert vazado not in codigo, f"o cabeçalho do E-Ofício vazou: {vazado}"


def test_o_modulo_registra_a_divergencia_do_modelo_da_casa():
    """**COMENTÁRIO QUE AFIRMA MEDIÇÃO SEM TER MEDIDO É PIOR QUE COMENTÁRIO
    NENHUM** — e o contrário também vale: uma divergência achada e não anotada é
    uma divergência que alguém vai reintroduzir. O módulo diz o que o modelo da
    casa afirma e o que a norma condiciona."""
    doc = T.__doc__ or ""
    assert "Provimento 28/2018" in doc
    assert "art. 249, II" in doc
    assert "não o li" in doc          # honestidade sobre o que NÃO se mediu


def test_a_lista_de_artigos_serve_para_conferir():
    """Régua que ninguém confere é régua que se acredita."""
    citados = T.artigos_citados()
    assert "art. 249, II" in citados
    assert "art. 46 da Lei nº 6.015/1973" in citados
    assert len(set(citados)) == len(citados)


# ------------------------------------------------ a tela


import glob                                                      # noqa: E402
import re                                                        # noqa: E402
import sqlite3                                                   # noqa: E402

import pytest                                                    # noqa: E402

SENHA = "Senha#12345"


def _token(html):
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado, "a tela nao trouxe csrf_token"
    return achado.group(1)


@pytest.fixture()
def logado(cg_casa):
    app = cg_casa['app']
    banco = cg_casa['banco']
    dados = cg_casa['dados']
    db = cg_casa['db']
    db.create_user("mario", "MARIO EXEMPLO DOS SANTOS", SENHA, "ADMIN")
    c = app.test_client()
    c.post("/login",
           data={"username": "mario", "password": SENHA,
                 "csrf_token": _token(c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return {"app": app, "cliente": c, "banco": banco, "db": db}


def _liso(t):
    return " ".join((t or "").split())


def _abrir(logado, url="/rcpn/registro-tardio"):
    r = logado["cliente"].get(url)
    assert r.status_code == 200, f"{url} nao abriu ({r.status_code})"
    return _liso(r.get_data(as_text=True))


def test_a_tela_avisa_do_modelo_que_afirma_demais(logado):
    """É o achado que fez esta tela existir."""
    html = _abrir(logado)
    assert "afirma o que a norma condiciona" in html
    assert "Provimento 28/2018" in html
    assert "art. 249, II" in html


def test_a_tela_e_honesta_sobre_o_que_nao_leu(logado):
    """Não afirmar que o Provimento não existe é diferente de dizer que a norma
    vigente condiciona — e a tela diz as duas coisas."""
    html = _abrir(logado)
    assert "ele não foi lido" in html


def test_a_tela_diz_que_o_lugar_e_o_da_residencia(logado):
    html = _abrir(logado)
    assert "residência do interessado" in html


def test_a_regua_dispensa_a_crianca_com_dnv(logado):
    html = _abrir(logado, "/rcpn/registro-tardio?conferir=1&idade=5&tem_dnv=on")
    assert "Testemunhas dispensadas" in html
    assert "entrevista do registrando" in html


def test_a_regua_manda_colher_do_adulto(logado):
    html = _abrir(logado, "/rcpn/registro-tardio?conferir=1&idade=30&tem_dnv=on")
    assert "Colha as 2 testemunhas" in html


def test_a_regua_manda_colher_da_crianca_sem_dnv(logado):
    """As duas condições são cumulativas."""
    html = _abrir(logado, "/rcpn/registro-tardio?conferir=1&idade=5")
    assert "Colha as 2 testemunhas" in html
    assert "cumulativas" in html


def test_sem_idade_a_regua_manda_colher(logado):
    """Não saber não é o mesmo que saber que é menor."""
    html = _abrir(logado, "/rcpn/registro-tardio?conferir=1&tem_dnv=on")
    assert "Colha as 2 testemunhas" in html
    assert "não se sabe a idade" in html


def test_a_tela_sem_pergunta_nao_afirma_nada(logado):
    """Abrir a tela não responde uma pergunta que ninguém fez."""
    html = _abrir(logado)
    assert "Testemunhas dispensadas" not in html
    assert "Colha as" not in html


def test_a_tela_mostra_os_artigos_para_conferir(logado):
    """Régua que ninguém confere é régua que se acredita."""
    html = _abrir(logado)
    assert "art. 249, § 2º" in html
    assert "149/2023" in html


def test_a_tela_diz_que_os_documentos_sao_desejaveis(logado):
    """Tratá-los como obrigatórios travaria o registro de quem não os tem."""
    html = _abrir(logado)
    assert "sempre que possível" in html
    assert "certidão negativa" in html


def test_a_tela_nao_grava_nada(logado):
    """Ela é régua, e régua não escreve."""
    _abrir(logado, "/rcpn/registro-tardio?conferir=1&idade=5&tem_dnv=on")
    con = sqlite3.connect(logado["banco"])
    assert con.execute(
        "SELECT COUNT(*) FROM rc_assentos").fetchone()[0] == 0


def test_esta_no_menu(logado):
    assert "Registro tardio" in _abrir(logado)
