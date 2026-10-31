"""As telas longas do Protesto e das consultas no layout novo: o que espera em cima, nenhum campo perdido.

O QUE ELES DEFENDEM
    Doze telas eram de rolar milhares de pixels: a CRA pela API, os avisos, os repasses, a certidão, a
    certidão eletrônica, o SIRC, a tarefa, o CPF, os modelos de atos, os livros obrigatórios, os selos e o
    Next Cloud SAS. No layout novo, o que espera a pessoa abre a tela e o resto fica em quadro recolhido,
    com o estado no título. Nada disso pode mudar regra nem perder campo, e quem continua no layout
    antigo tem de ver a tela de sempre.

    A armadilha é o quadro recolhido: o título precisa dizer como ele está, e quem traz perigo (a rotina
    com erro, a evidência que falta, o que ficou retido) não pode ficar fechado. E a âncora que outra tela
    usa tem de continuar existindo no quadro certo.

    Tudo aqui monta o molde de verdade sobre uma moldura vazia, sem banco e sem o sistema de pé.
"""
from __future__ import annotations

import re
from collections import Counter
from html.parser import HTMLParser
from pathlib import Path
from types import SimpleNamespace

import jinja2


def test_o_titulo_da_aba_do_cpf_nao_leva_script():
    fonte = (Path(__file__).resolve().parents[1] / "templates" / "rcpn_cpf.html").read_text(encoding="utf-8")
    titulo = re.search(r"{% block title %}(.*?){% endblock %}", fonte, re.S).group(1)
    assert titulo == "CPF no registro de nascimento"
    assert fonte.count("<script>") == 1
import pytest

RAIZ = Path(__file__).resolve().parent.parent
SERVENTIA = {"unit_name": "Ofício de Exemplo", "serventia_titulo": "Tabelião", "serventia_titular": "Mario",
             "serventia_cnpj": "00.000.000/0000-00", "ri_cns": "000000", "serventia_telefone": "(00) 0000-0000",
             "endereco_completo": "Rua da Demonstração, 100", "serventia_email": ""}


def _url(rota, **args):
    return "/" + rota + "".join(f"/{k}={v}" for k, v in sorted(args.items()))


def _montar(molde: str, **contexto) -> str:
    """O molde de verdade sobre uma moldura vazia: o que se confere aqui é o conteúdo da tela."""
    env = jinja2.Environment(autoescape=True, loader=jinja2.ChoiceLoader([
        jinja2.DictLoader({"base.html": "{% block content %}{% endblock %}"}),
        jinja2.FileSystemLoader(str(RAIZ / "templates"))]))
    for filtro in ("forte", "sem_script", "so_http", "com_links"):
        env.filters[filtro] = lambda texto: texto
    env.filters["filesize"] = str
    return env.get_template(molde).render(url_for=_url, csrf_token="t", sv=SERVENTIA, **contexto)


class _Leitor(HTMLParser):
    """Anota os formulários, os quadros, e se as caixas fecham na ordem."""

    CAIXAS = {"details", "summary", "section", "div", "form", "table"}
    CAMPOS = {"input", "select", "textarea", "button"}

    def __init__(self):
        super().__init__()
        self.pilha, self.tortas, self.quadros = [], [], {}
        self.campos, self.form = Counter(), None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form":
            self.form = a.get("action", "")
            self.campos[("form", self.form, a.get("method", ""), a.get("enctype", ""))] += 1
        if tag in self.CAMPOS and a.get("name"):
            self.campos[(self.form, tag, a["name"], a.get("type", ""), a.get("value", ""), "required" in a)] += 1
        if tag == "details" and "cg-quadro" in (a.get("class") or ""):
            self.quadros[a.get("id")] = "open" in a
        if tag in self.CAIXAS:
            self.pilha.append(tag)

    def handle_endtag(self, tag):
        if tag == "form":
            self.form = None
        if tag in self.CAIXAS and (not self.pilha or self.pilha.pop() != tag):
            self.tortas.append(tag)


def _ler(html: str) -> _Leitor:
    leitor = _Leitor()
    leitor.feed(html)
    return leitor


def _antes(html: str, *trechos):
    """Os trechos aparecem nesta ordem."""
    posicoes = [html.index(t) for t in trechos]
    assert posicoes == sorted(posicoes), trechos


# ---------------------------------------------------------------- /protesto/cra/api

def _cra(novo=True, credencial=True):
    return _montar(
        "protesto_cra_api.html", layout_novo=novo, ambiente="PRODUCAO", fora_de_uso=False,
        tem_credencial=credencial, usuario="mario", endereco="https://exemplo.invalid/cra",
        o_que_se_traz=[("pendentes", "Todas as remessas", "não precisa de nome"), ("ac", "Autorizações", "AC ou AD")],
        operacoes=["BuscarApresentante", "Imagem"], sem_sentido_medido=["Imagem"], VERSION="1")


def test_cra_os_downloads_abrem_a_tela_e_a_consulta_fica_recolhida():
    html = _cra()
    _antes(html, "Baixar todas as remessas", "Trazer da CRA", "Consultar na CRA", "Ligação e teste", "Referência — WSDL")
    assert _ler(html).quadros == {"cra-opcoes": False, "cra-consultar": False, "cra-ligacao": False, "cra-referencia": False}


@pytest.mark.parametrize("credencial, frase", [(True, "credencial informada — usuário <code>mario</code>"),
                                               (False, "credencial não informada")])
def test_cra_o_titulo_da_ligacao_diz_como_ela_esta(credencial, frase):
    html = _cra(credencial=credencial)
    assert frase in html[html.index('id="cra-ligacao"'):html.index('id="cra-referencia"')].split("</summary>")[0]


def test_cra_nenhum_dado_da_ligacao_se_perde():
    html = _cra()
    assert "https://exemplo.invalid/cra" in html and "HTTP Basic" in html and "Testar a ligação com a produção" in html


def test_cra_no_antigo_a_ordem_e_a_de_sempre():
    html = _cra(novo=False)
    _antes(html, "Ligação e teste", "Todas as remessas disponíveis", "Outros downloads", "Consultar na CRA", "Referência")
    assert "<td><strong>Endereço</strong>" not in html


# ---------------------------------------------------------------- /protesto/avisos

def _aviso(n, **extra):
    return dict({"id": n, "titulo_id": 100 + n, "numero": n, "ano": 2026, "emitido_em": "2026-10-21T10:00:00",
                 "numero_titulo": f"T-{n}", "protocolo": f"P{n}", "tentativas": [], "devedor_nome": "Ana Exemplo",
                 "endereco": "Rua da Demonstração, 100", "bairro": "Centro"}, **extra)


def _avisos(novo=True, **ao):
    base = dict(
        para_edital=[], esperando=[], entregues=[], sem_aviso=[], antigos=[], antigo_dias=180,
        contas={"EMITIDO": 1, "ENTREGUE": 2, "NAO_ENTREGUE": 3, "EDITAL": 4}, do_dia=[], envios=[], sem_prova=[],
        motivos=[{"codigo": 1, "motivo": "Ausente"}], motivos_destaque=[{"codigo": 1, "motivo": "Ausente"}],
        motivos_outros=[{"codigo": 2, "motivo": "Mudou-se"}], cenprot_pago={}, entregadores=["Mario"], hoje="2026-10-30")
    base.update(ao)
    return _montar("protesto_avisos.html", layout_novo=novo, **base)


SEM_PROVA = [{"titulo_id": 1, "numero_titulo": "T-1", "modo": "PESSOAL", "protocolo": "P1", "explicacao": "falta o canhoto",
              "onde": "na lista dos entregues", "aviso_id": 7, "falta_quem_recebeu": False}]
SEM_AVISO = [{"apontado_em": "2026-10-20", "titulo_id": 2, "protocolo": "P2", "numero_titulo": "T-2", "devedor_nome": "João Modelo"}]
CAMINHO = {"frase": "A Intimação Digital não serve.", "passo": "RESOLVE", "edital": "JUSTIFICAR"}
NAO_ENTREGUE = _aviso(5, caminho=CAMINHO, comprovantes=[], base=None, motivo=1)
ENTREGUE = _aviso(7, entrega_em="2026-10-23", recebido_por="", comprovantes=[], base_cadastro=None)
TUDO = dict(sem_prova=SEM_PROVA, sem_aviso=SEM_AVISO, esperando=[_aviso(3)], para_edital=[NAO_ENTREGUE], entregues=[ENTREGUE],
            do_dia=[{"id": 1, "ano": 2026, "numero": 1, "publicado_por": "Mario", "numero_titulo": "T-9", "protocolo": "P9"}],
            envios=[{"dia": "2026-10-20", "editais": 1, "com_comprovante": 0, "do_eoficio": 0, "completo": False, "anexos": []}],
            antigos=[{"apontado_em": "2021-05-05", "titulo_id": 9, "protocolo": "P9", "devedor_nome": "Carla", "avisos": 0}])


@pytest.mark.parametrize("presentes, abre", [
    (TUDO, "sem-prova"),
    ({k: v for k, v in TUDO.items() if k != "sem_prova"}, "apontados-sem-aviso"),
    ({"esperando": [_aviso(3)], "para_edital": [NAO_ENTREGUE]}, "esperando"),
    ({"para_edital": [NAO_ENTREGUE]}, "nao-entregues"),
])
def test_avisos_abre_so_o_primeiro_que_espera(presentes, abre):
    quadros = _ler(_avisos(**presentes)).quadros
    esperam = {"sem-prova", "apontados-sem-aviso", "esperando", "nao-entregues"} & set(quadros)
    assert [q for q in esperam if quadros[q]] == [abre]


def test_avisos_sem_nada_esperando_nenhuma_lista_abre_sozinha():
    assert not any(_ler(_avisos()).quadros.values())


def test_avisos_o_edital_de_hoje_abre_porque_o_dia_ainda_tem_passos():
    assert _ler(_avisos(do_dia=TUDO["do_dia"])).quadros["editais-de-hoje"]
    assert not _ler(_avisos()).quadros["editais-de-hoje"]


def test_avisos_o_que_espera_vem_antes_do_que_ja_foi():
    _antes(_avisos(**TUDO), "Intimados sem a prova", "Apontados sem aviso", "Saíram e esperam desfecho", "Não entregues —",
           "Entregues —", "Editais publicados hoje", "Envio do edital", "Apontados antigos", "Como esta tela funciona")


def test_avisos_as_ancoras_dos_outros_continuam_no_quadro_certo():
    html = _avisos(**TUDO)
    for ancora in ("sem-prova", "apontados-sem-aviso", "entregues", "envio-do-edital", "apontados-antigos"):
        assert html.count(f'id="{ancora}"') == 1
    assert 'href="#aviso-7"' in html
    assert html.index('id="entregues"') < html.index('id="aviso-7"') < html.index('id="editais-de-hoje"')
    assert html.index('id="nao-entregues"') < html.index('id="aviso-5"') < html.index('id="entregues"')


def test_avisos_o_titulo_diz_o_que_falta_sem_abrir():
    html = _avisos(**TUDO)
    entregues = html[html.index('id="entregues"'):].split("</summary>")[0]
    assert "1 sem comprovante" in entregues and "1 sem o nome de quem recebeu" in entregues
    assert "1 dia(s) sem comprovante" in html[html.index('id="envio-do-edital"'):].split("</summary>")[0]


def test_avisos_o_que_se_explica_nao_se_perde():
    html = _avisos(**TUDO)
    assert "a <strong>intimação é o ato</strong>" in html and "O aviso desta casa era também o boleto" in html
    assert "3 não entregues" in html and "4 em edital" in html


def test_avisos_no_antigo_a_ordem_e_a_de_sempre():
    html = _avisos(novo=False, **TUDO)
    _antes(html, "<span>Como está</span>", "<span>Apontados sem aviso", "<span>Saíram e esperam desfecho", "<span>Não entregues —",
           "<span>Intimados sem a prova", "<span>Entregues —", "<span>Editais publicados hoje", "<span>Envio do edital",
           "O aviso desta casa era também o boleto", "<span>Apontados antigos")


# ---------------------------------------------------------------- /protesto/repasses

def _pagamento(n, canal):
    return {"ato_id": n, "titulo_id": 100 + n, "numero_titulo": f"T-{n}", "protocolo": f"P{n}", "canal": canal, "favorecido": "Banco Exemplo",
            "apresentante_codigo": "237", "recebido_em": "2026-10-20", "observacao": "", "prazo": "2026-10-21", "vencido": True,
            "dias_de_atraso": 9, "valor_centavos": 1000, "valor_de": "PAGO"}


def _rotina(ativo=True, situacao="OK"):
    return {"existe": True, "ativo": ativo, "pode_agir": True, "agenda": "seg a sex",
            "ultima": {"iniciada_em": "2026-10-29", "situacao": situacao, "relato": "ensaio"} if situacao else None}


def _repasses(novo=True, pendentes=(), faltam=(), rotina=None, robo=None, guias=(), a_conciliar=()):
    return _montar(
        "protesto_repasses.html", layout_novo=novo, user={"role": "ADMIN"}, pode_mexer=["ADMIN"], hoje="2026-10-30",
        rel={"pendentes": list(pendentes), "vencidos": 1, "a_conciliar": list(a_conciliar),
             "por_canal": {"IEPTB": {"titulos": 1, "total_centavos": 1000, "vencidos": 1}}},
        guias=list(guias), faltam=list(faltam), rotina=rotina or _rotina(), robo=robo or _rotina(),
        portais={"CRA": {"onde": "no portal", "passo": "entre", "precedente": "lido", "a_conferir": "a palavra"}},
        formas={"ESPECIE": "Espécie", "PIX": "Depósito"}, reais=str, fundamento="art. 19, § 2º")


PENDENTES = [_pagamento(1, "IEPTB"), _pagamento(2, "DIRETO")]
FALTAM = [{"titulo_id": 101, "numero_titulo": "T-1", "protocolo": "P1", "central": "CRA", "guia_id": None, "guia": None, "etapa": "SEM_GUIA",
           "prazo": "2026-10-21", "vencido": True, "dias_de_atraso": 9, "explicacao": "gere a relação"}]


def test_repasses_o_que_falta_vem_primeiro_e_as_listas_com_item_abrem():
    html = _repasses(pendentes=PENDENTES, faltam=FALTAM)
    _antes(html, "O que falta para o repasse sair", "Da Central —", "Do balcão —", "Guias ao IEPTB", "Rotina automática",
           "Robô do boleto", "Onde a guia se emite", "Resumo", "Como funciona o repasse")
    q = _ler(html).quadros
    assert q["o-que-falta"] and q["da-central"] and q["do-balcao"]
    assert not (q["rotina"] or q["robo"] or q["onde-se-emite"] or q["resumo"] or q["como-funciona"])


def test_repasses_sem_nada_a_repassar_nada_abre():
    assert not any(_ler(_repasses()).quadros.values())


def test_repasses_a_rotina_com_erro_abre_sozinha_e_o_titulo_diz():
    html = _repasses(rotina=_rotina(situacao="ERRO"))
    assert _ler(html).quadros["rotina"]
    assert '<strong class="danger">ERRO</strong>' in html[html.index('id="rotina"'):].split("</summary>")[0]
    assert not _ler(html).quadros["robo"]


def test_repasses_o_robo_com_erro_tambem_abre():
    assert _ler(_repasses(robo=_rotina(situacao="ERRO"))).quadros["robo"]


@pytest.mark.parametrize("ativo, palavra", [(True, "Ligada"), (False, "Desligada")])
def test_repasses_o_titulo_diz_ligada_ou_desligada(ativo, palavra):
    html = _repasses(rotina=_rotina(ativo=ativo, situacao=None))
    titulo = html[html.index('id="rotina"'):].split("</summary>")[0]
    assert palavra in titulo and "ainda não rodou" in titulo


def test_repasses_a_rotina_que_nao_existe_nao_derruba_o_titulo():
    html = _repasses(rotina={"existe": False, "motivo": "a central não está instalada"})
    assert "não disponível" in html[html.index('id="rotina"'):].split("</summary>")[0]
    assert "a central não está instalada" in html


def test_repasses_guia_paga_abre_o_quadro_das_guias():
    assert _ler(_repasses(a_conciliar=[{"id": 1}])).quadros["guias"]


def test_repasses_no_antigo_a_ordem_e_a_de_sempre():
    html = _repasses(novo=False, pendentes=PENDENTES, faltam=FALTAM)
    _antes(html, "à disposição do apresentante", "O que falta para o repasse sair", "Onde a guia se emite", "Rotina automática",
           "Robô do boleto", "Resumo", "Da Central —", "Do balcão —", "Guias ao IEPTB")


# ---------------------------------------------------------------- a certidão do RCPN

def _certidao(novo=True, cancelada=False, papel="ADMIN"):
    return _montar(
        "rc_certidao.html", layout_novo=novo, user={"role": papel},
        certidao={"id": 1, "numero": 1, "ano": 2026, "assento_id": 1, "especie": "NASCIMENTO", "nome": "Ana Exemplo",
                  "emitida_em": "2026-10-30", "matricula": "0001", "selo": "SELO", "requerente": "Mario", "finalidade": "",
                  "modalidade": "RESUMO", "atos_no_assento": 1, "hash_teor": "abc", "teor": "CERTIDÃO DE NASCIMENTO",
                  "cancelada_em": "2026-10-30" if cancelada else None, "cancelada_por": "Mario", "cancelada_motivo": "erro",
                  "declaracao_selo_tjma_em": None})


def test_certidao_o_teor_fica_a_vista_e_so_o_cancelamento_recolhe():
    html = _certidao()
    assert _ler(html).quadros == {"cancelar": False}
    assert html.index("CERTIDÃO DE NASCIMENTO") > html.index("</details>")


def test_certidao_cancelada_nao_oferece_cancelar_e_mostra_o_teor():
    html = _certidao(cancelada=True)
    assert 'id="cancelar"' not in html and "CERTIDÃO DE NASCIMENTO" in html and "Certidão cancelada" in html


def test_certidao_quem_nao_pode_cancelar_nao_ve_o_quadro():
    assert 'id="cancelar"' not in _certidao(papel="AUDITOR")


def test_certidao_no_antigo_o_teor_vem_antes_do_cancelamento():
    html = _certidao(novo=False)
    _antes(html, "Matrícula", "O teor", "Cancelar esta certidão")


# ---------------------------------------------------------------- a certidão eletrônica

def _eletronica(novo=True, credencial=True, pronto=True, ja_saiu=(), avisos=("o CPF vai em branco",)):
    return _montar(
        "rcpn_certidao_eletronica_nova.html", layout_novo=novo, tem_credencial=credencial, arquivo_da_credencial="onrcpn.cred",
        assento={"id": 1, "especie": "NASCIMENTO", "numero": 1, "nome": "Ana Exemplo"},
        c={"impedem": [] if pronto else ["falta o CPF"], "avisos": list(avisos), "pronto": pronto, "tipo_registro": "nascimento",
           "registro": {"NOME_COMPLETO": "Ana Exemplo", "FILIACAO": [{"nome": "Beatriz"}]}},
        campos={"selo": "SELO", "cod_selo": "", "cota_emolumentos": "", "cota_isento": False},
        tipos=["nascimento", "casamento"], base="https://exemplo.invalid", ambiente="PRODUCAO", ja_saiu=list(ja_saiu))


JA_SAIU = [{"id": 9, "certidao_id": "ID-1", "situacao": "CRIADA", "assinatura_link": "", "pedido_id": None, "criada_em": "2026-10-25"}]


def test_eletronica_conferir_e_criar_ficam_a_vista_e_o_resto_recolhe():
    html = _eletronica()
    _antes(html, "Como a certidão vai", "Criar na Central", "O registro, como ele vai", "Emitir JSON (CRC)")
    q = _ler(html).quadros
    assert q["ce-como"] and q["ce-em-branco"] and not q["ce-registro"] and not q["ce-json"]


def test_eletronica_o_que_ja_saiu_vem_antes_de_criar_outra():
    html = _eletronica(ja_saiu=JA_SAIU)
    _antes(html, "Já saíram deste registro", "ID-1", "Criar na Central")
    assert _ler(html).quadros["ce-ja-saiu"]


def test_eletronica_sem_token_nao_ha_botao_de_criar():
    html = _eletronica(credencial=False)
    assert "Criar na Central" not in html and "O token do IdRC não foi informado" in html


def test_eletronica_nada_em_branco_nao_abre_quadro_vazio():
    assert "ce-em-branco" not in _ler(_eletronica(avisos=())).quadros


def test_eletronica_no_antigo_a_ordem_e_a_de_sempre():
    _antes(_eletronica(novo=False, ja_saiu=JA_SAIU), "Como a certidão vai", "O que vai em branco", "O registro, como ele vai",
           "Emitir JSON (CRC)", "Criar a certidão eletrônica", "Já saíram deste registro")


# ---------------------------------------------------------------- /rcpn/sirc

NORMA_SIRC = SimpleNamespace(
    PRAZO_DIAS_UTEIS=1, ARTIGO="art. 225", SANCAO="penalidade", O_QUE_VAI=[{"nome": "Nascimento"}, {"nome": "Óbito"}],
    PRAZO_SEM_INTERNET_DIAS_UTEIS=5, PRAZO_DA_INEXISTENCIA_DIAS_UTEIS=5, MAXIMO_DE_REGISTROS=250,
    MAXIMO_DE_BYTES=1024 * 1024, INTERVALO_MINIMO_SEGUNDOS=60)
LOTE = {"numero": 1, "especie": "NASCIMENTO", "quantos": 1, "bytes": 100, "avisos": [], "cabe": True}
RETIDO = {"nome": "Ana Exemplo", "tipo": "NASCIMENTO", "faltas": ["a matrícula"], "assento_id": 1, "especie": "NASCIMENTO"}
ESPERA = {"data_ato": "2026-10-01", "tipo": "NASCIMENTO", "nome": "João Modelo", "numero": 1, "atos": []}


def _sirc(novo=True, devendo=(ESPERA,), retidos=(), carga=(), cancelamentos=(), do_acervo=0, lotes=(LOTE,)):
    montado = {"quantos": len(lotes), "lotes": list(lotes), "retidos": list(retidos)}
    return _montar(
        "rcpn_sirc.html", layout_novo=novo, norma=NORMA_SIRC, devendo=list(devendo), montado=montado, do_acervo=do_acervo,
        carga=list(carga), montado_carga={"quantos": 1, "lotes": [LOTE], "retidos": list(retidos)},
        cancelamentos=list(cancelamentos), montado_cancelamento={"quantos": 1, "lotes": [LOTE], "retidos": []})


def test_sirc_os_botoes_do_lote_vem_primeiro_e_a_lista_fica_depois():
    html = _sirc(retidos=[RETIDO], carga=[ESPERA])
    _antes(html, "Esperando remessa", "Enviar o lote 1 pela API", "Ficaram de fora", "A lista dos que esperam", "Cancelamento de termo",
           "Mês sem movimento", "Carga do acervo", "O que o SIRC recebe")
    q = _ler(html).quadros
    assert q["sirc-retidos"] and not (q["sirc-lista"] or q["sirc-mes"] or q["sirc-carga"] or q["sirc-como"] or q["sirc-cancelamento"])


def test_sirc_o_numero_pequeno_continua_dizendo_por_que_e_pequeno():
    html = _sirc(do_acervo=3)
    _antes(html, "Enviar o lote 1 pela API", "3 assento(s) do acervo ficam de fora", "A lista dos que esperam")
    assert "3 assento(s) do acervo ficam de fora" in _sirc(do_acervo=3, devendo=(), lotes=())


def test_sirc_termo_cancelado_pendente_abre_o_quadro():
    assert _ler(_sirc(cancelamentos=[{"nome": "Ana"}])).quadros["sirc-cancelamento"]


def test_sirc_sem_nada_esperando_diz_e_nao_quebra():
    html = _sirc(devendo=(), lotes=())
    assert "Nada esperando remessa." in html and "sirc-lista" not in _ler(html).quadros


def test_sirc_no_antigo_a_ordem_e_a_de_sempre():
    _antes(_sirc(novo=False, retidos=[RETIDO], carga=[ESPERA], do_acervo=3), "sete coisas", "ficam de fora desta", "Carga do acervo",
           "Esperando remessa", "ficaram de fora", "Registro novo", "Mês sem movimento", "Cancelamento de termo", "Este sistema envia")


# ---------------------------------------------------------------- /tarefas/<id>

def _linha_do_historico(n):
    return {"ts": f"2026-10-{n + 10}T10:00:00", "full_name": "Beatriz", "action": "NOTA", "new_value": "OBSERVACAO", "old_value": None, "note": f"nota {n}"}


def _tarefa(novo=True, historico=2, vinculos=(), docs=(), evidencia=False, anexos=(), origem="MANUAL", especie="", sugerida="ADM", **linha):
    row = dict({"id": 7, "created_at": "2026-10-20", "status": "ABERTA", "evidence_required": evidencia, "backup_user_id": None, "created_by": None,
                "source_type": origem, "description": "Faça isto.", "title": "Protocolo de exemplo", "sector": "", "system_name": "", "priority": "ALTA",
                "start_date": "", "due_days": None, "due_date": "2026-11-05", "assigned_user_id": 1, "assigned_name": "Mario", "legal_ref": "",
                "source_page": None, "linked_expediente_id": None, "backup_name": "", "creator_name": ""}, **linha)
    return _montar(
        "task_detail.html", layout_novo=novo, row=row, attachments=list(anexos), history=[_linha_do_historico(n) for n in range(historico)],
        users=[{"id": 1, "full_name": "Mario"}], sectors=[], PRIORITIES=["ALTA"], TASK_STATUSES=["ABERTA"], pasta_vinculos=list(vinculos), pasta_docs=list(docs),
        pasta_retirados=[], pasta_tipos={"ASSENTO": {"nome": "Assento"}}, suspensao=None, MODOS_DE_SUSPENDER={"PRAZO": "Por prazo"}, amanha="2026-10-31",
        tipo={"especie": especie, "sugerida": sugerida, "catalogo": {"ADM": {"nome": "Tarefa administrativa", "exemplos": "LGPD"}}},
        user={"role": "ADMIN"}, TIPOS_ANDAMENTO=[("OBSERVACAO", "Observação")], fmt_date=str, fmt_dt=str, rotulo_da_acao=str, rotulo_do_tipo_andamento=str)


VINCULO = {"id": 1, "nome": "Protocolo", "origem": True, "url": "/p/1", "rotulo": "2026.10.1", "etapa": "", "tabela": "cx_protocolos"}


def test_tarefa_registrar_o_andamento_vem_primeiro():
    html = _tarefa()
    _antes(html, "Registrar andamento", 'name="note"', 'id="historico"', 'id="pasta"', 'id="evidencias"', 'id="tipo"', 'id="dados"')


def test_tarefa_as_ancoras_de_volta_continuam():
    html = _tarefa()
    assert html.count('id="pasta"') == 1 and html.count('id="tipo"') == 1


@pytest.mark.parametrize("vinculos, abre", [((), False), ((VINCULO,), True)])
def test_tarefa_a_pasta_abre_quando_tem_peca(vinculos, abre):
    assert _ler(_tarefa(vinculos=vinculos)).quadros["pasta"] is abre


def test_tarefa_o_documento_da_pasta_tambem_abre():
    doc = {"id": 1, "nome": "mandado.pdf", "tamanho": 10, "de_onde": "expediente"}
    assert _ler(_tarefa(docs=[doc])).quadros["pasta"]


def test_tarefa_a_evidencia_exigida_abre_e_o_alto_leva_ate_ela():
    html = _tarefa(evidencia=True)
    assert _ler(html).quadros["evidencias"]
    assert 'href="#evidencias"' in html and "aqui ao lado" not in html.split("</details>")[0]
    assert "esta tarefa exige evidência" in html[html.index('id="evidencias"'):].split("</summary>")[0]


def test_tarefa_com_evidencia_anexada_o_quadro_fica_fechado():
    anexo = {"id": 1, "original_name": "a.pdf", "size_bytes": 1, "sha256": "a" * 64, "uploaded_at": "2026-10-20"}
    assert not _ler(_tarefa(evidencia=True, anexos=[anexo])).quadros["evidencias"]


@pytest.mark.parametrize("n, abre", [(0, False), (6, True), (7, False)])
def test_tarefa_o_historico_curto_abre_e_o_longo_recolhe(n, abre):
    assert bool(_ler(_tarefa(historico=n)).quadros["historico"]) is abre


def test_tarefa_o_titulo_diz_o_ultimo_registro_e_os_dados():
    html = _tarefa(historico=7)
    assert "7 registro(s), o último em 2026-10-10T10:00:00 por Beatriz" in html
    assert "ABERTA · prioridade ALTA · vence em 2026-11-05 · com Mario" in html


def test_tarefa_o_titulo_do_tipo_diz_o_gravado_ou_o_sugerido():
    assert "ainda sem tipo · sugerido: Tarefa administrativa" in _tarefa()
    html = _tarefa(especie="ADM", sugerida="")
    assert "ainda sem tipo" not in html[html.index('id="tipo"'):].split("</summary>")[0]


def test_tarefa_o_que_fazer_do_gestor_vem_antes_de_tudo():
    html = _tarefa(origem="GESTOR")
    _antes(html, "O que fazer", "Registrar andamento")


def test_tarefa_no_antigo_a_ordem_e_a_de_sempre():
    html = _tarefa(novo=False, evidencia=True)
    _antes(html, "aqui ao lado", "<h2>Pasta do processo", "<h2>Tipo do processo", 'name="title"', "<h2>Evidências", "<h2>Histórico e andamento", 'name="note"')


# ---------------------------------------------------------------- /rcpn/cpf

NORMA_CPF = SimpleNamespace(
    NORMA="a norma", QUANDO_SE_PODE="no registro", QUANDO_NAO_SE_PODE="proibido", PENALIDADE="penalidade",
    FALTA_PARA_INTEGRAR=[{"o_que": "o termo", "de_quem": "o oficial", "trava_tudo": True}],
    CAMINHOS=[{"nome": "Formulário", "onde": "na CRC", "como": "à mão", "porque": "funciona"}],
    O_QUE_FAZER_SE_ERRAR="emita sem CPF", ERROS_CONHECIDOS=[{"o_que": "nome", "como_evitar": "confira"}], ONDE_CORRIGIR="na CRC",
    PRAZO_CORRECAO_DIAS=90, COMO_USAR_O_PREENCHEDOR="arraste", PREENCHEDOR="javascript:void(0)", CRC_GERAR_CPF="https://exemplo.invalid",
    PORQUE_NAO_EMBUTE="certificado")


def _assento_sem_cpf(n, falta=()):
    return {"id": n, "numero": 9000 + n, "nome": f"Ana Exemplo {n}", "data_ato": "2026-10-20", "falta": list(falta),
            "copiar": [{"rotulo": "Nome da Criança", "valor": f"Ana Exemplo {n}"}, {"rotulo": "DNV", "valor": ""}]}


def _cpf(novo=True, linhas=()):
    return _montar("rcpn_cpf.html", layout_novo=novo, norma=NORMA_CPF, linhas=list(linhas))


def test_cpf_a_lista_vem_primeiro_e_a_norma_depois():
    html = _cpf(linhas=[_assento_sem_cpf(1)])
    _antes(html, "A inscrição no CPF é obrigatória", "1\n    nascimento sem CPF", "Nascimento nº 9001", 'name="cpf"', "Quando se pode pedir",
           "O que falta para o sistema", "Os três caminhos", "Quando a Receita recusar", "Preencher a CRC", "Por que a CRC abre")


def test_cpf_so_o_primeiro_assento_abre_e_todos_continuam_na_tela():
    q = _ler(_cpf(linhas=[_assento_sem_cpf(1), _assento_sem_cpf(2), _assento_sem_cpf(3)])).quadros
    assert (q["cpf-assento-1"], q["cpf-assento-2"], q["cpf-assento-3"]) == (True, False, False)


def test_cpf_o_titulo_diz_o_que_falta_sem_abrir():
    html = _cpf(linhas=[_assento_sem_cpf(1, falta=[{"o_que": "o sexo"}]), _assento_sem_cpf(2)])
    assert "falta 1 dado(s)" in html[html.index('id="cpf-assento-1"'):].split("</summary>")[0]
    assert "tem tudo o que a Receita exige" in html[html.index('id="cpf-assento-2"'):].split("</summary>")[0]


@pytest.mark.parametrize("n, tem", [(1, False), (2, True)])
def test_cpf_abrir_todos_so_com_mais_de_um(n, tem):
    html = _cpf(linhas=[_assento_sem_cpf(i) for i in range(1, n + 1)])
    assert ("Abrir todos" in html) is tem


def test_cpf_lista_vazia_diz_que_nao_ha_ninguem():
    assert "Nenhum nascimento do balcão está sem CPF." in _cpf()


def test_cpf_no_antigo_a_ordem_e_a_de_sempre():
    html = _cpf(novo=False, linhas=[_assento_sem_cpf(1)])
    _antes(html, "Quando se pode pedir", "O que falta para o sistema", "Os três caminhos", "Quando a Receita recusar", "Preencher a CRC",
           "1\n    nascimento sem CPF", "Nascimento nº 9001", "Por que a CRC abre")
    assert "Abrir todos" not in html and 'class="tabela cg-cpf-dados"' not in html


# ---------------------------------------------------------------- modelos de atos

def _modelo(n, tipo):
    return {"codigo": f"M{n}", "tipo": tipo, "nome": f"Modelo {n}", "fundamentacao": "Lei 6.015/73", "requisitos": ["confira"], "corpo": "Teor"}


def _modelos(novo=True, modelos=(), matricula_id=None):
    return _montar("ri_modelos_atos.html", layout_novo=novo, modelos=list(modelos), total=len(modelos), busca="", tipo="",
                   matricula_id=matricula_id, matricula_numero=70001)


TODOS_OS_MODELOS = [_modelo(1, "R"), _modelo(2, "AV"), _modelo(3, "R")]


def test_modelos_registros_e_averbacoes_lado_a_lado_e_nenhum_se_perde():
    html = _modelos(modelos=TODOS_OS_MODELOS)
    assert "Registros (2)" in html and "Averbações (1)" in html and 'class="cg-modelos cg-modelos-uma"' not in html
    assert all(f"Modelo {n}" in html for n in (1, 2, 3))
    _antes(html, "Registros (2)", "Modelo 1", "Modelo 3", "Averbações (1)", "Modelo 2")


def test_modelos_filtrar_um_tipo_vira_uma_coluna():
    assert 'class="cg-modelos cg-modelos-uma"' in _modelos(modelos=[_modelo(1, "R")])


def test_modelos_vindo_da_ficha_oferece_usar_na_matricula():
    html = _modelos(modelos=TODOS_OS_MODELOS, matricula_id=5)
    assert html.count("Usar este modelo na matrícula 70001") == 3


@pytest.mark.parametrize("novo", [True, False])
def test_modelos_busca_vazia_diz_que_nao_achou(novo):
    assert "Nenhum modelo encontrado." in _modelos(novo=novo)


def test_modelos_no_antigo_a_lista_e_uma_so_na_ordem_do_catalogo():
    html = _modelos(novo=False, modelos=TODOS_OS_MODELOS)
    assert "Registros (2)" not in html
    _antes(html, "Modelo 1", "Modelo 2", "Modelo 3")


# ---------------------------------------------------------------- livros obrigatórios

def _livro(nome, situacao, nota=""):
    return {"nome": nome, "artigo": "art. 1", "situacao": situacao, "rotas": ["livro_visitas"], "series": [], "nota": nota}


GRUPOS_DE_LIVROS = [
    {"chave": "TODAS", "titulo": "Toda serventia", "livros": [_livro("Visitas", "TEM"), _livro("Diário", "PARCIAL", "falta coluna")]},
    {"chave": "PROTESTO", "titulo": "Protesto", "livros": [_livro("Índices", "FALTA", "não há tela"), _livro("Distribuição", "A_CONFERIR")]},
]


def _livros(novo=True, grupos=None):
    grupos = GRUPOS_DE_LIVROS if grupos is None else grupos
    conta = Counter(x["situacao"] for g in grupos for x in g["livros"])
    return _montar("livros_obrigatorios.html", layout_novo=novo, grupos=grupos, contagem=dict(conta), fonte="o Código",
                   situacoes={"TEM": "Tem", "PARCIAL": "Tem, com falta", "FALTA": "Falta", "FACULTATIVO": "Facultativo", "A_CONFERIR": "A conferir"})


def test_livros_o_que_falta_vem_antes_e_cada_atribuicao_recolhe():
    html = _livros()
    q = _ler(html).quadros
    assert q == {"livros-a-olhar": True, "livros-TODAS": False, "livros-PROTESTO": False}
    primeiro = html[html.index('id="livros-a-olhar"'):html.index('id="livros-TODAS"')]
    assert "Diário" in primeiro and "Índices" in primeiro and "Distribuição" in primeiro and "Visitas" not in primeiro


def test_livros_a_lista_inteira_continua_em_cada_atribuicao():
    html = _livros()
    assert "Visitas" in html[html.index('id="livros-TODAS"'):html.index('id="livros-PROTESTO"')]


def test_livros_o_titulo_diz_a_contagem():
    html = _livros()
    assert "2 livro(s) · 1 falta(m) · 1 a conferir" in html[html.index('id="livros-PROTESTO"'):].split("</summary>")[0]
    assert "2 livro(s) · 1 com falta" in html[html.index('id="livros-TODAS"'):].split("</summary>")[0]


def test_livros_nada_faltando_nao_abre_lista_vazia():
    grupos = [{"chave": "TODAS", "titulo": "Toda serventia", "livros": [_livro("Visitas", "TEM")]}]
    assert "livros-a-olhar" not in _ler(_livros(grupos=grupos)).quadros


def test_livros_no_antigo_e_a_tabela_de_sempre():
    html = _livros(novo=False)
    assert html.count("<h2>") == 2 and "<td>Visitas</td>" in html


# ---------------------------------------------------------------- /selos

def _selos(novo=True, orfaos=0, grupos=()):
    linha = {"numero": "SELO1", "tipo_do_ato": "REG", "obtido_em": "2026-10-30T10:00:00", "obtido_por": "Mario", "atribuicao_legivel": "Registro Civil",
             "caminho": "", "ato_id": 1, "tabela": "rc_atos", "situacao": "USADO"}
    return _montar(
        "selos_emitidos.html", layout_novo=novo, f={"inicio": "", "fim": "", "atribuicao": "", "quem": "", "tipo": "", "caminho": "", "situacao": "", "numero": ""},
        lista={"linhas": [linha], "pagina": 1, "paginas": 1, "total": 1, "por_pagina": 50},
        escolhas={"atribuicoes": ["RC"], "usuarios": ["Mario"], "tipos": [{"codigo": "REG", "rotulo": "Registro", "quantos": 1}], "caminhos": [],
                  "situacoes": {"": "todas"}, "agrupamentos": {"usuario": "Por usuário"}},
        conta={"total": 9, "usados": 7, "orfaos": orfaos, "cancelados": 2, "primeiro": "2026-10-01", "ultimo": "2026-10-30"},
        grupos=list(grupos), agrupar="usuario", norma=SimpleNamespace(ATRIBUICOES={"RC": "Registro Civil"}))


def test_selos_a_lista_sobe_e_os_numeros_ficam_no_titulo():
    html = _selos()
    _antes(html, "Procurar", "O que este filtro alcança", "Os selos", "SELO1")
    assert "9 selo(s) · 7 usado(s) · 0 não usado(s) · 2 cancelado(s)" in html
    assert _ler(html).quadros == {"selos-alcance": False}


def test_selos_o_nao_usado_se_destaca_no_titulo():
    assert '<strong class="danger">3 não usado(s)</strong>' in _selos(orfaos=3)


def test_selos_a_contagem_por_grupo_continua_no_quadro():
    html = _selos(grupos=[{"chave": "Mario", "quantos": 4, "cancelados": 0}, {"chave": "Carla", "quantos": 5, "cancelados": 1}])
    assert html.index('id="selos-alcance"') < html.index("Carla") < html.index("</details>")


def test_selos_no_antigo_e_a_forma_de_sempre():
    html = _selos(novo=False)
    assert "<h2>O que este filtro alcança</h2>" in html and "<h2>Os selos</h2>" in html


# ---------------------------------------------------------------- Next Cloud SAS

def _next_cloud(novo=True, imagens=None, faltando=(), sem_imagem=None, erro=""):
    pessoal = {"com_documento": 1, "vinculos": 2, "sem_documento": 1, "pessoas": 2, "matriculas": 2, "sem_data": 0, "zerado_vai_assim": "00000000000",
               "precedente_da_casa": "já mandou zerado.", "quantos_nomes_estranhos": 0, "nomes_estranhos": []}
    return _montar(
        "ri_onr_next_cloud.html", layout_novo=novo, raiz="pasta-de-exemplo", faltando=list(faltando), cns="000000",
        q={"alcanca_1976": True, "mais_antiga": "1951", "ato_mais_antigo": "1948", "sem_imagem": sem_imagem, "matriculas": 10, "indicador_pessoal": pessoal,
           "erro_do_disco": erro, "imagens": imagens},
        formulario={"cns": "000000", "conta_google": "exemplo", "total_de_matriculas": 10, "ultima_matricula": {"numero": 10, "livro": "2"}, "espaco": {"gb": 1},
                    "erro_do_espaco": "", "diretorio": "pasta", "sistema": "Outros", "conta_google_e_para": "o console.", "so_o_oficial_sabe": "o IP"})


IMAGENS = {"arquivos": 5, "no_padrao": 5, "matriculas": 3, "resolucao_ok": 1, "amostra": 1, "compressao_ok": 1, "quantos_fora_do_nome": 0, "quantos_fora_da_pasta": 0,
           "fora_do_nome": [], "fora_da_pasta": [], "achados": []}
SEM_IMAGEM = [{"id": 1, "numero": 7, "livro": "2", "folha": "1", "tipo_ficha": "ACERVO", "data_abertura": "1990"}]


def test_next_cloud_a_conferencia_e_o_xml_ficam_a_vista_e_o_resto_recolhe():
    html = _next_cloud(imagens=IMAGENS, faltando=SEM_IMAGEM, sem_imagem=1)
    q = _ler(html).quadros
    assert q == {"nc-tres-coisas": False, "nc-formulario": False, "nc-base": True, "nc-pessoal": True, "nc-imagens": False, "nc-sem-imagem": False, "nc-caminho": False}
    _antes(html, "São três coisas", "O formulário de adesão", "A base está completa?", "1. Indicador Pessoal", "Gerar o XML", "2. Imagens do Livro 2",
           "As matrículas sem imagem", "O caminho, na ordem")


def test_next_cloud_o_titulo_ja_responde_a_pergunta_do_oficial():
    html = _next_cloud()
    assert "aderir não desliga o Indicador Real: ele continua pela API" in html[html.index('id="nc-tres-coisas"'):].split("</summary>")[0]
    assert "é uma declaração assinada com o seu e-CPF" in html[html.index('id="nc-formulario"'):].split("</summary>")[0]


@pytest.mark.parametrize("sem_imagem, frase", [(None, "imagens não medidas"), (0, "toda matrícula com imagem"), (3, "3 de 10 matrículas sem imagem")])
def test_next_cloud_o_titulo_da_base_diz_como_ela_esta(sem_imagem, frase):
    assert frase in _next_cloud(sem_imagem=sem_imagem).split('id="nc-base"')[1].split("</summary>")[0]


def test_next_cloud_o_que_a_amostra_achou_abre_o_quadro():
    assert _ler(_next_cloud(imagens=dict(IMAGENS, achados=["um arquivo errado"]))).quadros["nc-imagens"]


def test_next_cloud_no_antigo_e_a_forma_de_sempre():
    html = _next_cloud(novo=False, imagens=IMAGENS, faltando=SEM_IMAGEM, sem_imagem=1)
    assert html.count('<section class="cartao">') == 7


# ---------------------------------------------------------------- o que vale para as doze

TELAS = {
    "cra": lambda novo: _cra(novo=novo),
    "cra_sem_credencial": lambda novo: _cra(novo=novo, credencial=False),
    "avisos": lambda novo: _avisos(novo=novo, **TUDO),
    "avisos_vazia": lambda novo: _avisos(novo=novo),
    "repasses": lambda novo: _repasses(novo=novo, pendentes=PENDENTES, faltam=FALTAM, rotina=_rotina(situacao="ERRO"), a_conciliar=[{"id": 1}]),
    "repasses_vazia": lambda novo: _repasses(novo=novo),
    "certidao": lambda novo: _certidao(novo=novo),
    "certidao_cancelada": lambda novo: _certidao(novo=novo, cancelada=True),
    "eletronica": lambda novo: _eletronica(novo=novo, ja_saiu=JA_SAIU),
    "eletronica_sem_token": lambda novo: _eletronica(novo=novo, credencial=False, pronto=False),
    "sirc": lambda novo: _sirc(novo=novo, retidos=[RETIDO], carga=[ESPERA], cancelamentos=[{"nome": "Ana"}], do_acervo=2),
    "sirc_vazia": lambda novo: _sirc(novo=novo, devendo=(), lotes=()),
    "tarefa": lambda novo: _tarefa(novo=novo, historico=7, vinculos=[VINCULO], evidencia=True, origem="GESTOR"),
    "tarefa_concluida": lambda novo: _tarefa(novo=novo, status="CONCLUIDA"),
    "cpf": lambda novo: _cpf(novo=novo, linhas=[_assento_sem_cpf(1), _assento_sem_cpf(2)]),
    "cpf_vazia": lambda novo: _cpf(novo=novo),
    "modelos": lambda novo: _modelos(novo=novo, modelos=TODOS_OS_MODELOS, matricula_id=5),
    "livros": lambda novo: _livros(novo=novo),
    "selos": lambda novo: _selos(novo=novo, orfaos=3, grupos=[{"chave": "Mario", "quantos": 4, "cancelados": 0}, {"chave": "Carla", "quantos": 5, "cancelados": 1}]),
    "next_cloud": lambda novo: _next_cloud(novo=novo, imagens=IMAGENS, faltando=SEM_IMAGEM, sem_imagem=1),
}
SEM_QUADRO_NENHUM = {"modelos"}  # o catálogo é coluna, e os modelos continuam `<details>` como sempre


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_as_duas_molduras_mandam_os_mesmos_campos(tela):
    assert _ler(TELAS[tela](True)).campos == _ler(TELAS[tela](False)).campos


@pytest.mark.parametrize("novo", [True, False])
@pytest.mark.parametrize("tela", sorted(TELAS))
def test_as_caixas_fecham_na_ordem(tela, novo):
    leitor = _ler(TELAS[tela](novo))
    assert leitor.tortas == [] and leitor.pilha == []


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_no_antigo_nao_ha_quadro_nem_estilo_nem_o_script_do_novo(tela):
    html = TELAS[tela](False)
    assert "cg-quadro" not in html and "<style" not in html and "sessionStorage" not in html


@pytest.mark.parametrize("tela", sorted(set(TELAS) - SEM_QUADRO_NENHUM))
def test_no_novo_o_script_dos_quadros_vem_depois_de_todos_eles(tela):
    html = TELAS[tela](True)
    if not _ler(html).quadros:
        return
    assert html.count('var guarda = "cg-quadros:"') == 1
    assert html.rindex('<details class="panel cg-quadro"') < html.index('var guarda = "cg-quadros:"')


@pytest.mark.parametrize("tela", sorted(TELAS))
def test_cada_quadro_tem_id_unico(tela):
    html = TELAS[tela](True)
    ids = re.findall(r'<details class="panel cg-quadro" id="([^"]+)"', html)
    assert len(ids) == len(set(ids)) and all(ids)


@pytest.mark.parametrize("molde", ["protesto_cra_api", "protesto_avisos", "protesto_repasses", "rc_certidao", "rcpn_certidao_eletronica_nova", "rcpn_sirc",
                                   "task_detail", "rcpn_cpf", "ri_modelos_atos", "livros_obrigatorios", "selos_emitidos", "ri_onr_next_cloud"])
def test_o_estilo_novo_so_entra_no_layout_novo(molde):
    """O estilo mora no molde, dentro do `if layout_novo`: as outras telas e o layout antigo não o recebem."""
    fonte = (RAIZ / "templates" / f"{molde}.html").read_text(encoding="utf-8")
    for achado in re.finditer(r"<style", fonte):
        antes = fonte[:achado.start()]
        assert antes.rfind("{% if layout_novo %}") > antes.rfind("{% else %}") or antes.rstrip().endswith("{% if layout_novo %}")
