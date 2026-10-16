"""
O ROTEIRO DAS CENTRAIS — o que o oficial trouxe, e o que o sistema faz dele.

Dois papeis, de 01/09/2026: o **Roteiro das Centrais de Protesto** do TJMA e o
**Oficio Circular IEPTB-MA/CRA-MA n. 015/2025**. **Isto nao esta no acervo, e
nao se descobre medindo** — o acervo guarda o que foi lavrado, e nao a ordem
nem a hora.

O QUE ESTES TESTES GUARDAM
      - os QUATRO HORARIOS da CRA, com a hora exata do papel — errar um deles
        e o apresentante sem resposta;
      - **o passo que o sistema NAO faz diz que nao faz, e diz onde se faz**.
        Um roteiro que leva a tela em oito de dez e cala os dois faz o
        escrevente procurar o que nao existe;
      - **nenhum passo aponta para tela que nao existe** — a promessa com cara
        de prova, que ja pegou quinze provas minhas inventadas;
      - a coluna «hoje» CONTA e nao julga: zero pode ser «nao fiz» ou «nada
        chegou», e o sistema nao sabe qual;
      - a tela e de LEITURA e esta aberta ao balcao — «amplo acesso dos
        escreventes» foi o pedido, e trancar a instrucao nao protege ato
        nenhum.
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

import protesto_roteiro as PR
from pt_schema import init_pt_schema

SENHA = "Senha#12345"
HOJE = "2026-09-01"


def banco() -> sqlite3.Connection:
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    init_pt_schema(con)
    return con


# ------------------------------------------------------------- os horarios


def test_os_quatro_horarios_sao_os_do_papel():
    """A HORA E O QUE MAIS PESA, e o sistema nao a tinha em lugar nenhum."""
    horas = {h["o_que"]: h["hora"] for h in PR.HORARIOS_DA_CRA}
    assert horas == {"Envio de remessa": "12:30",
                     "Envio de confirmacao": "14:10",
                     "Envio de retorno": "11:30",
                     "Andamento": "11:30"}


def test_tres_dos_quatro_horarios_sao_de_arquivo_que_SAI_daqui():
    """A remessa e a CRA que manda; os outros tres a casa manda — e sao esses
    que alguem tem de lembrar de fazer antes da hora."""
    nossos = [h["o_que"] for h in PR.HORARIOS_DA_CRA if h["nosso"]]
    assert nossos == ["Envio de confirmacao", "Envio de retorno", "Andamento"]


# ------------------------------------------------------------- os passos


def test_os_dois_roteiros_tem_o_numero_de_passos_do_papel():
    assert len(PR.ROTEIRO_DA_CRA) == 8
    assert len(PR.ROTEIRO_DA_CENPROT) == 8


def test_todo_passo_sem_tela_DIZ_onde_se_faz():
    """Calar aqui faria o escrevente procurar no sistema o que nao existe."""
    for lista in (PR.ROTEIRO_DA_CRA, PR.ROTEIRO_DA_CENPROT):
        for p in lista:
            if not p.get("tela"):
                assert p.get("onde"), f"«{p['passo']}» nao diz onde se faz"


def test_nenhum_passo_aponta_para_tela_que_nao_existe():
    """A PROMESSA COM CARA DE PROVA — ela ja pegou quinze provas minhas.

    Apontar para uma tela parecida faria o escrevente marcar o passo como
    feito sem te-lo feito.
    """
    telas = {p["tela"] for lista in (PR.ROTEIRO_DA_CRA, PR.ROTEIRO_DA_CENPROT)
             for p in lista if p.get("tela")}

    # **ESTE VARREDOR OLHAVA UM ARQUIVO SO, E ELE ENVELHECEU NA PRIMEIRA
    # MUDANCA.** Ele lia `atribuicoes_web.py`, porque em 01/09/2026 todas as
    # telas do Protesto moravam la; em 02/09 as da CENPROT nasceram em
    # `cenprot_web.py`, e o teste acusou «a rota nao existe» sobre rotas que
    # existem. **Lista escrita a mao noutro arquivo envelhece na tarde em que
    # se escreve** — e aqui o arquivo era o do teste que deveria guardar a
    # regra, pela segunda vez neste projeto (a primeira foi o
    # `MODULOS_COM_SECAO` do menu do Registro Civil).
    #
    # Agora ele procura em TODO modulo que pendura rota, e o nome do arquivo
    # nao decide nada.
    fontes = "".join(
        arq.read_text(encoding="utf-8", errors="replace")
        for arq in RAIZ.glob("*.py")
        if "registrar_rotas" in arq.read_text(encoding="utf-8",
                                              errors="replace"))
    for tela in sorted(telas):
        assert f"def {tela}(" in fontes, f"a rota «{tela}» nao existe"


def test_o_oficio_da_a_norma_de_quatro_passos_da_cenprot():
    """Quatro dos oito passos da CENPROT tem norma citada no oficio 015/2025;
    os outros quatro nao, e o campo fica VAZIO — nao se preenche por
    semelhanca."""
    com_norma = [p["passo"] for p in PR.ROTEIRO_DA_CENPROT if p.get("norma")]
    assert len(com_norma) == 4
    juntas = " ".join(p.get("norma", "") for p in PR.ROTEIRO_DA_CENPROT)
    assert "Resolucao n. 1 do IEPTB-BR" in juntas
    assert "Lei 9.492/1997" in juntas
    assert "Resolucao n. 8" in juntas and "Resolucao n. 9" in juntas


def test_o_cadastro_de_usuario_e_do_tabeliao():
    assert any("Tabeliao ou Substituto" in x for x in PR.SO_O_TABELIAO)


# ------------------------------------------------------------- o que se mede


def test_conta_o_que_aconteceu_hoje_e_nao_o_de_ontem():
    con = banco()
    for dia, quando in (("2026-09-01", "2026-09-01T11:00:00"),
                        ("2026-08-31", "2026-08-31T11:00:00")):
        con.execute(
            """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia,
                   nome_arquivo, conteudo, titulos, gerado_em)
               VALUES ('SDTBFORTP','033',?,'r.txt','x',1,?)""", (dia, quando))
    feito = PR.o_que_ja_aconteceu_hoje(con, hoje=HOJE)
    assert feito["retorno_gerado"] == 1


def test_coluna_errada_ESTOURA_em_vez_de_virar_zero():
    """O GUARDA SO PERDOA A TABELA QUE FALTA, e nada mais.

    A primeira versao tinha `except sqlite3.Error: return 0`, e me escondeu um
    defeito no mesmo minuto: eu escrevera `recebido_em` onde a coluna e
    `recebida_em`. A tela diria «nenhuma remessa hoje» para sempre.
    """
    con = banco()
    with pytest.raises(sqlite3.Error):
        PR._um(con, "pt_remessas",
               "SELECT COUNT(*) FROM pt_remessas WHERE nao_existe = ?", "x")


def test_tabela_que_nao_existe_devolve_NONE_e_nao_zero():
    """Instalacao sem o Protesto e caso real — e ali «nao ha o que contar» e
    diferente de «contei, e deu zero»."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    assert PR._um(con, "pt_remessas", "SELECT COUNT(*) FROM pt_remessas") is None


def test_o_zero_e_zero_e_nao_um_julgamento():
    """Um zero pode ser «ainda nao fiz» ou «nada chegou hoje» — o modulo NAO
    tem funcao que diga «atrasado», e e de proposito."""
    publicos = [n for n in dir(PR) if not n.startswith("_")]
    for palavra in ("atrasado", "atraso", "pendente", "vencido", "alerta"):
        assert not any(palavra in n.lower() for n in publicos), (
            f"«{palavra}» nos nomes publicos: este modulo conta, nao julga")


def test_a_cobertura_fica_a_vista():
    """Um roteiro que nao diz quanto dele o sistema cobre deixa supor que
    cobre tudo."""
    c = PR.quantos_o_sistema_faz()
    assert c["cra_total"] == 8 and c["cenprot_total"] == 8
    assert 0 < c["cra_com_tela"] < c["cra_total"]
    assert 0 < c["cenprot_com_tela"] < c["cenprot_total"]


def test_o_roteiro_junta_tudo_para_a_tela():
    con = banco()
    r = PR.roteiro(con, hoje=HOJE)
    assert r["hoje"] == HOJE
    assert len(r["cra"]) == 8 and len(r["cenprot"]) == 8
    assert len(r["horarios"]) == 4
    assert r["fontes"] and r["so_o_tabeliao"]
    com_tela = [p for p in r["cra"] if p["o_sistema_faz"]]
    assert com_tela and all(p["tela"] for p in com_tela)


# ------------------------------------------------------------- a tela


def _token(html: str) -> str:
    achado = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', html)
    assert achado
    return achado.group(1)


@pytest.fixture()
def s(cg_casa):
    app = cg_casa['app']
    banco_ = cg_casa['banco']
    dados = cg_casa['dados']
    # USER, e nao ADMIN: o pedido foi «amplo acesso dos escreventes».
    cg_casa['db'].create_user("escrevente", "MARIA", SENHA, "USER")
    # O PROTESTO ESTA DESLIGADO DE FABRICA desde 01/09/2026 — ordem do
    # oficial. Estes testes exercitam as TELAS dele, e por isso o LIGAM
    # aqui, de proposito e a vista: eles provam que o modulo funciona
    # quando ele voltar, que e o que «fica para um futuro» quer dizer.
    cg_casa['db'].set_settings({"modulo_protesto_ligado": "1"})
    c = app.test_client()
    c.post("/login", data={"username": "escrevente", "password": SENHA,
                           "csrf_token": _token(
                               c.get("/login").get_data(as_text=True))},
           follow_redirects=True)
    return c


def test_o_escrevente_abre_a_tela(s):
    """«Para amplo acesso dos escreventes» — trancar a instrucao por perfil
    seria trancar o que ensina, e nao o ato."""
    r = s.get("/protesto/roteiro")
    assert r.status_code == 200
    assert "roteiro das Centrais" in r.get_data(as_text=True)


def test_a_tela_esta_no_menu(s):
    """E vem PRIMEIRO no menu do Protesto — e a unica que diz o que fazer e
    ate que hora; as outras fazem."""
    html = s.get("/protesto").get_data(as_text=True)
    assert 'href="/protesto/roteiro"' in html


def test_os_horarios_aparecem_na_TELA_ONDE_O_BALCAO_CHEGA(s):
    """«NA PAGINA PRINCIPAL DO PROTESTO», que foi o pedido.

    Ali vai so a parte com HORA MARCADA — o roteiro inteiro empurraria a lista
    de titulos para baixo toda vez que alguem a abrisse.
    """
    html = s.get("/protesto").get_data(as_text=True)
    assert "Horários da CRA" in html
    assert "11:30" in html and "14:10" in html and "12:30" in html
    assert 'href="/protesto/roteiro"' in html


def test_a_faixa_dos_horarios_e_SO_do_protesto(s):
    """As outras tres atribuicoes usam a mesma tela de lista, e a CRA nao tem
    nada a ver com elas."""
    for outra in ("/rcpn", "/rcpj-rtd", "/livro3"):
        assert "Horários da CRA" not in s.get(outra).get_data(as_text=True)


def test_a_tela_mostra_os_quatro_horarios(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    for hora in ("12:30", "14:10", "11:30"):
        assert hora in html


def test_a_tela_diz_o_que_o_sistema_nao_faz(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "o sistema não faz este passo" in html
    assert "no site da CENPROT" in html


def test_a_tela_traz_a_norma_de_cada_passo_que_a_tem(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "Lei 9.492/1997" in html
    assert "Resolucao n. 9 de 2024" in html


def test_a_tela_explica_a_coluna_de_hoje(s):
    """Numero sem explicacao vira julgamento na cabeca de quem le."""
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "conta, e não julga" in html


def test_a_tela_diz_de_onde_saiu_o_roteiro(s):
    """Exigencia sem endereco e exigencia que ninguem confere."""
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "IEPTB-MA/CRA-MA" in html
    assert "não está no acervo" in html


# ================================================================ o PAINEL DO DIA
#
# Pedido do oficial em 14/10/2026: «botao claro e bem posicionado para cada
# parte da rotina do protesto» e «um fluxo natural». O que estes testes
# guardam:
#   - as dez etapas, na ordem em que o titulo anda, cada uma com o botao que
#     leva a tela que FAZ aquilo — e toda tela existe no url_map;
#   - o que nao existe nao ganha botao que finge: o XML diario assinado a
#     CENPROT fica SEM botao, dizendo onde se faz;
#   - os links das Centrais pedem PRODUCAO (desde 14/10 tudo e producao);
#   - a contagem conta, e nao julga: None quando nao da para medir, nunca um
#     zero inventado; e a marca da virada nao conta como arquivo de hoje.

import json as _json


def _retorno(con, *, tipo, gerado_em, ambiente=None, enviado=None, erro=None):
    con.execute(
        """INSERT INTO pt_retornos(tipo, apresentante_codigo, dia, nome_arquivo,
               conteudo, titulos, gerado_em, cra_enviado_em,
               cra_enviado_ambiente, cra_envio_erro)
           VALUES (?, '033', ?, 'x.txt', 'x', 1, ?, ?, ?, ?)""",
        (tipo, gerado_em[:10], gerado_em, enviado, ambiente, erro))


def test_as_etapas_sao_dez_na_ordem_da_rotina():
    numeros = [e["n"] for e in PR.ETAPAS_DO_DIA]
    assert numeros == list(range(1, 11))
    ancoras = [e["ancora"] for e in PR.ETAPAS_DO_DIA]
    assert len(set(ancoras)) == len(ancoras)
    titulos = " | ".join(e["titulo"] for e in PR.ETAPAS_DO_DIA)
    for palavra in ("remessa", "imagens", "Confirmar", "Intimar",
                    "desistências", "Pagamentos", "protestos", "Retorno",
                    "CENPROT", "Certidões"):
        assert palavra in titulos, palavra


def test_toda_etapa_tem_botao_e_diz_o_que_faz():
    for e in PR.ETAPAS_DO_DIA:
        assert e["botoes"], f"etapa {e['n']} sem botao"
        assert e["faz"].strip()
        for b in e["botoes"]:
            assert b["rotulo"].strip() and b["tela"].strip()


def test_toda_medida_tem_frase_e_toda_frase_e_medida():
    """Lista escrita em dois lugares diverge na tarde em que se escreve."""
    medido = PR.medir_o_dia(banco(), hoje=HOJE)
    assert set(medido) == set(PR.MEDIDAS_DO_DIA)
    for e in PR.ETAPAS_DO_DIA:
        for k in e["medidas"]:
            assert k in PR.MEDIDAS_DO_DIA, k


def test_os_links_das_centrais_pedem_producao():
    """Desde 14/10/2026 tudo e producao; as telas ainda abrem na homologacao
    quando nao se diz qual — por isso o painel DIZ."""
    import centrais_cred as CRED
    assert PR.AMBIENTE_DE_PRODUCAO == CRED.PRODUCAO
    centrais = {"protesto_cra_api", "protesto_resolve", "protesto_pendencias"}
    vistos = set()
    for e in PR.ETAPAS_DO_DIA:
        for b in e["botoes"]:
            if b["tela"] in centrais:
                vistos.add(b["tela"])
                assert b["args"].get("ambiente") == CRED.PRODUCAO
    assert vistos == centrais
    assert "HOMOLOG" not in _json.dumps(PR.ETAPAS_DO_DIA,
                                        ensure_ascii=False).upper()


def test_o_xml_diario_se_gera_e_nenhum_botao_promete_o_envio():
    """Desde 15/10/2026 o sistema GERA o XML diário (P e D, com o instrumento
    assinado dentro) — e o ENVIO continua pelo portal, porque a API da
    CENPROT não tem caminho para ele. A etapa diz as duas coisas, e nenhum
    botão promete enviar o que só se gera. (Até 14/10 este teste exigia que
    nenhum botão falasse do XML diário: ele não existia.)"""
    cenprot = next(e for e in PR.ETAPAS_DO_DIA if e["ancora"] == "etapa-cenprot")
    assert "XML diário" in cenprot["sem_botao"]
    assert "portal da CENPROT" in cenprot["falta"]
    assert any(b["tela"] == "protesto_cenprot_xml" for b in cenprot["botoes"])
    for e in PR.ETAPAS_DO_DIA:
        for b in e["botoes"]:
            if "XML diário" in b["rotulo"]:
                assert "envi" not in b["rotulo"].lower()


def test_o_retorno_sobe_pelo_botao_e_o_andamento_do_par_diz_que_nao():
    # Até 14/10/2026 o retorno não subia pela API; ganhou o botão «Enviar à
    # CRA» (`protesto_cra_envio.enviar_arquivo`). O andamento em par com o
    # retorno continua pelo portal, e a etapa diz isso.
    retorno = next(e for e in PR.ETAPAS_DO_DIA if e["ancora"] == "etapa-retorno")
    assert "Enviar à CRA" in retorno["falta"]
    assert "portal da CRA" in retorno["falta"]
    assert "11:30" in retorno["falta"]


def test_as_horas_das_etapas_sao_as_do_papel():
    p = PR.painel_do_dia(banco(), hoje=HOJE)
    horas = {e["ancora"]: e["hora_limite"] for e in p["etapas"]}
    assert horas["etapa-remessa"] == "12:30"
    assert horas["etapa-confirmacao"] == "14:10"
    assert horas["etapa-retorno"] == "11:30"
    assert horas["etapa-intimar"] is None
    # O relogio junta retorno e andamento, que sao a mesma hora e etapa.
    assert [r["hora"] for r in p["relogio"]] == ["11:30", "12:30", "14:10"]
    assert p["relogio"][0]["ancora"] == "etapa-retorno"
    assert "Andamento" in p["relogio"][0]["o_que"]


def test_sem_tabela_a_contagem_e_none_e_nao_zero():
    """Instalacao sem o Protesto: «nao ha o que contar» nao e «contei zero»."""
    con = sqlite3.connect(":memory:")
    con.row_factory = sqlite3.Row
    medido = PR.medir_o_dia(con, hoje=HOJE)
    assert medido and all(v is None for v in medido.values())
    assert PR.estado_do_envio(con)["cra_envio_automatico_producao"] is None


def test_com_tabela_vazia_a_contagem_e_zero_medido():
    medido = PR.medir_o_dia(banco(), hoje=HOJE)
    assert medido["remessas_recebidas_hoje"] == 0
    assert medido["a_protestar"] == 0
    assert medido["atos_esperando_retorno"] == 0


def test_a_marca_da_virada_nao_conta_como_arquivo_de_hoje():
    """A virada gravou em `pt_retornos` linhas que nao sao arquivo (o que o
    E-Oficio ja informou). Contadas, o primeiro dia diria «1 retorno gerado»
    sem ninguem ter gerado."""
    con = banco()
    _retorno(con, tipo="SDTBFORTP", gerado_em=HOJE + "T08:13:17",
             ambiente="EOFICIO", enviado=HOJE + "T08:13:17")
    assert PR.o_que_ja_aconteceu_hoje(con, hoje=HOJE)["retorno_gerado"] == 0
    assert PR.medir_o_dia(con, hoje=HOJE)["retornos_e_andamentos_hoje"] == 0
    _retorno(con, tipo="SDTBFORTP", gerado_em=HOJE + "T10:00:00")
    assert PR.o_que_ja_aconteceu_hoje(con, hoje=HOJE)["retorno_gerado"] == 1
    assert PR.medir_o_dia(con, hoje=HOJE)["retornos_e_andamentos_hoje"] == 1


def test_a_confirmacao_conta_gerada_aceita_e_com_erro():
    con = banco()
    _retorno(con, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:40:00",
             ambiente="PRODUCAO", enviado=HOJE + " 15:41:00")
    _retorno(con, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:41:00",
             ambiente="PRODUCAO", erro="A CRA recusou")
    _retorno(con, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:42:00")
    # Um de homologacao aceito nao e aceito em producao.
    _retorno(con, tipo="SDTBFOCRT", gerado_em=HOJE + "T12:43:00",
             ambiente="HOMOLOGACAO", enviado=HOJE + " 15:44:00")
    m = PR.medir_o_dia(con, hoje=HOJE)
    assert m["confirmacoes_hoje"] == 4
    assert m["confirmacoes_aceitas_hoje"] == 1
    assert m["confirmacoes_com_erro_hoje"] == 1


def test_o_instrumento_nao_conta_o_protesto_do_acervo():
    """«Protesto sem instrumento» do acervo nao e trabalho de hoje: o E-Oficio
    nao guardava instrumento, e contar os mil protestos dele faria o numero
    nunca zerar."""
    con = banco()
    for origem in ("EOFICIO", "MANUAL"):
        cur = con.execute(
            """INSERT INTO pt_titulos(especie, numero_titulo, situacao,
                   origem, origem_chave, criado_em)
               VALUES ('DMI', ?, 'PROTESTADO', 'CRA', ?, ?)""",
            (origem, origem, HOJE))
        con.execute(
            """INSERT INTO pt_atos(titulo_id, tipo, data_ato, origem,
                   criado_em)
               VALUES (?, 'PROTESTO', ?, ?, ?)""",
            (cur.lastrowid, HOJE, origem, HOJE))
    assert PR.medir_o_dia(con, hoje=HOJE)["protestos_sem_instrumento"] == 1


def test_o_painel_nao_tem_nome_que_julga():
    for palavra in ("atrasado", "atraso", "pendente", "vencido", "alerta"):
        for k in list(PR.MEDIDAS_DO_DIA) + list(PR.MEDIDAS_DO_DIA.values()):
            assert palavra not in k.lower(), (palavra, k)


def test_toda_tela_do_painel_existe_e_aceita_os_argumentos(cg_casa):
    """Mais forte que procurar `def nome(`: monta o endereco de verdade."""
    from flask import url_for
    app = cg_casa["app"]
    with app.test_request_context():
        for e in PR.ETAPAS_DO_DIA:
            for b in e["botoes"]:
                assert b["tela"] in app.view_functions, b["tela"]
                url_for(b["tela"], **b["args"])
        url_for("settings")


def test_a_tela_mostra_o_painel_com_os_botoes(s):
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    assert "o painel do dia" in html
    for e in PR.ETAPAS_DO_DIA:
        assert e["titulo"] in html
        assert f'id="{e["ancora"]}"' in html
    assert 'href="/protesto/remessas"' in html
    assert 'href="/protesto/a-protestar"' in html
    assert "ambiente=PRODUCAO" in html
    assert "ambiente=HOMOLOG" not in html
    assert "Sem botão:" in html and "XML diário" in html
    assert "enviar até" in html and "a CRA disponibiliza" in html
    assert "Envio automático à CRA (produção)" in html


def test_o_painel_nao_tem_formulario(s):
    """Os botoes LEVAM a tela que faz — nenhum faz por aqui, e o GET so le."""
    html = s.get("/protesto/roteiro").get_data(as_text=True)
    painel = html.split('id="relogio"', 1)[1].split(
        'id="roteiro-das-centrais"', 1)[0]
    assert "<form" not in painel
