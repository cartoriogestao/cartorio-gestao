"""O ensaio de atos das Notas: cada situação de parte pelas telas de verdade, e o papel conferido com a lei.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída. […] Queria antecipar esses problemas e processar antes de
encontrar na prática.»

O QUE ESTE TESTE FAZ
    `test_fluxo_notas` já leva cada minuta de fábrica do protocolo pago à certidão, com duas pessoas
    solteiras e maiores. Este pratica os casos de `ensaio_de_atos_notas.casos` — o casado e o cônjuge
    que consente, o procurador, o menor e quem o representa, a pessoa jurídica, quem não sabe assinar,
    o testador cego — pelas mesmas telas, e confere o termo que vai ao livro contra o requisito da norma
    citada em cada teste. A leitura que não cabe numa conferência está em
    `docs/ensaio_de_atos/relatorio_notas.md`; o inventário em `docs/ensaio_de_atos/inventario_notas.md`.

A TRAVA ESTÁ LIGADA: barra rede, programa e gravação fora da pasta temporária. A ÚNICA porta que ela
    deixa é a do selador de mentira desta máquina (`selador_falso`, TLS em 127.0.0.1): a lavratura das
    Notas sela pelo aparelho, e não pelo selo digitado como a do Registro Civil.

OS DEFEITOS FICAM À VISTA
    A asserção é a da lei, e não a do que o sistema faz hoje. O defeito aberto fica em
    `xfail(strict=True)`, com o motivo; consertado, o teste avisa (XPASS) e a marca sai.

PARA LER OS DOCUMENTOS: `CG_ENSAIO_SAIDA=1` grava cada caso em `<pasta temporária>/ensaio_de_atos_notas/`.
"""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path

import pytest

import ensaio_de_atos_notas as EN
import layout_ensaio as E
import test_fluxo_notas as F

pytestmark = pytest.mark.lento

CASOS = {c.chave: c for c in EN.casos()}


def _defeito(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DEFEITO: {motivo}")


def _decisao(motivo: str):
    return pytest.mark.xfail(strict=True, reason=f"DECISÃO DO OFICIAL: {motivo}")




# ------------------------------------------------------------------ a bancada e a prática

@pytest.fixture()
def bancada(cg_casa, monkeypatch):
    """A bancada de `test_fluxo_notas`, com a trava ligada e só a porta do selador aberta."""
    from conftest import cg_login
    from selador_de_bancada import ligar_o_selador

    db = cg_casa["db"]
    db.create_user("oficial", F.OFICIAL, F.SENHA, "ADMIN")
    db.create_user("escrevente", F.ESCREVENTE, F.SENHA, "USER")
    db.set_settings(F.SERVENTIA)
    F._semear_a_tabela(db)
    monkeypatch.setitem(cg_casa["app"].extensions, "notas_medir_paginas", lambda odt: 2)
    c = cg_casa["app"].test_client()
    cg_login(c, "escrevente", F.SENHA)
    # a DOI é tela do oficial (a do escrevente responde 403): o ensaio a abre como ele abriria
    oficial = cg_casa["app"].test_client()
    cg_login(oficial, "oficial", F.SENHA)
    b = {"app": cg_casa["app"], "cliente": c, "banco": cg_casa["banco"], "db": db, "dados": cg_casa["dados"],
         "oficial": oficial}
    with ligar_o_selador(b, protocolo_pago=False) as aparelho:
        F._aparelho_com_valores(aparelho)
        b["aparelho"] = aparelho
        E.ligar_trava(cg_casa["dados"], portas_locais=(aparelho.porta,))
        try:
            yield b
        finally:
            E.desligar_trava()


#: O que já saiu, por caso, neste processo: o papel é texto, e não depende mais da bancada.
_FEITOS: dict[str, EN.Saida] = {}


@pytest.fixture()
def praticado(bancada):
    """`praticado("chave")` — o caso, praticado uma vez por processo. A bancada sobe sempre (pedi-la no
    meio do teste, com `getfixturevalue`, desmontava o banco do teste seguinte)."""
    def _praticar(chave: str) -> EN.Saida:
        if chave not in _FEITOS:
            s = EN.praticar(bancada, CASOS[chave])
            _FEITOS[chave] = s
            if os.environ.get("CG_ENSAIO_SAIDA"):
                pasta = Path(tempfile.gettempdir()) / "ensaio_de_atos_notas"
                pasta.mkdir(exist_ok=True)
                (pasta / f"{chave}.txt").write_text(EN.em_texto(s), encoding="utf-8")
        return _FEITOS[chave]
    return _praticar


def _lavrado(praticado, chave: str) -> EN.Saida:
    s = praticado(chave)
    assert s.situacao == "LAVRADO", f"{chave} não foi ao livro: {s.avisos}"
    return s


def _teor(praticado, chave: str) -> str:
    """O teor montado pela minuta — o que vai ao livro, lavrado ou não."""
    s = praticado(chave)
    assert s.teor, f"{chave} não montou o teor: {s.avisos}"
    return s.teor



def _abertura(termo: str) -> str:
    """O comparecimento: de «compareceu/compareceram» até o reconhecimento da identidade."""
    m = re.search(r"comparece(?:u|ram)(.*?)(?:todos )?reconhecid", termo, re.S | re.I)
    assert m, "o termo não tem o comparecimento"
    return m.group(1)



# ------------------------------------------------------------------ todo caso vai ao livro

#: Os casos que o balcão tem de recusar — e o teste que confere a recusa.
RECUSADOS = {"emancipacao_menor_de_16": "test_a_emancipacao_confere_os_dezesseis_anos",
             # a revogação precisa da procuração que revoga: praticada no seu teste
             "revogacao_da_procuracao": "test_a_revogacao_desta_serventia_anota_a_procuracao"}


#: Os casos que um defeito aberto impede de ir ao livro.
NAO_VAO_AO_LIVRO: dict[str, str] = {}


@pytest.mark.parametrize("chave", [pytest.param(c, marks=_defeito(NAO_VAO_AO_LIVRO[c])) if c in NAO_VAO_AO_LIVRO
                                   else c for c in CASOS if c not in RECUSADOS])
def test_o_caso_vai_ao_livro_com_selo_e_o_traslado_reproduz_o_termo(praticado, chave):
    """Do protocolo pago ao termo, pelo balcão; o selo no termo (CN-MA arts. 130 e 131) e o traslado
    com o teor do livro (CN-MA art. 850, § 2º)."""
    s = _lavrado(praticado, chave)
    assert "SELO" in s.termo.upper(), "o termo saiu sem o selo"
    assert s.traslado and "Traslado" in s.traslado
    assert EN.tem(s.traslado, _abertura(s.termo)[:200])


# ------------------------------------------------------------------ o que já está certo

def test_o_local_do_ato_e_o_estado_por_extenso(praticado):
    """CC art. 215, § 1º, I (o local do ato). Decisão do oficial, 03/11/2026 (observação 10): «Estado do
    Maranhão» por extenso, do cadastro da serventia, e não «Estado do MA»."""
    t = _lavrado(praticado, "cv_casado_com_outorga").termo
    assert EN.tem(t, "Estado do Maranhão") and not EN.tem(t, "Estado do MA,")


def test_o_testador_cego_ouve_o_testamento_duas_vezes(praticado):
    """CC art. 1.867: ao cego, o testamento é lido em voz alta duas vezes, uma pelo tabelião e outra
    por testemunha que ele designar, com menção circunstanciada."""
    t = _lavrado(praticado, "testamento_cego").termo
    assert EN.tem(t, "cego", "duas vezes", "LUCIA EXEMPLO TESTEMUNHA", "designada")


def test_quem_nao_sabe_assinar_o_testamento_assina_a_rogo_uma_testemunha(praticado):
    """CC art. 1.865: o tabelião declara e assina a rogo uma das testemunhas instrumentárias."""
    t = _lavrado(praticado, "testamento_nao_assina").termo
    assert EN.tem(t, "a seu rogo", "PAULO EXEMPLO TESTEMUNHA", "1.865", "impressão digital")
    # «sabe | pode» é escolha desde 03/11/2026 (observação 11): o «não» é da minuta.
    assert EN.tem(t, "o TESTADOR não sabe assinar") and not EN.tem(t, "não não")


def test_a_procuracao_para_alienar_imovel_arquiva_a_certidao_do_registro(praticado):
    """CC art. 661, § 1º (poderes especiais e expressos) e CN-MA art. 833 (certidão atualizada do RI,
    exigida e arquivada)."""
    t = _lavrado(praticado, "proc_alienar_imovel").termo
    assert EN.tem(t, "661, § 1º", "certidão atualizada do registro de imóveis", "833")


def test_a_divorcianda_que_volta_ao_nome_de_solteira_fica_no_termo(praticado):
    """CN-MA art. 822 (como o LT02 cita): a declaração do nome que cada um passa a usar."""
    t = _lavrado(praticado, "divorcio_com_nome").termo
    assert EN.tem(t, "JOANA EXEMPLO DOS SANTOS voltará a usar o nome de solteiro(a)")


# ------------------------------------------------------------------ quem comparece, e em que qualidade

def _qualificacao_de(abertura: str, nome: str) -> str:
    """A qualificação de `nome` na abertura: do nome ao próximo «;» que não está dentro dela."""
    m = re.search(re.escape(nome) + r", [^;]*", abertura)
    assert m, f"{nome} não está qualificado na abertura: {abertura[:300]}"
    return m.group(0)


def test_o_procurador_comparece_na_qualificacao_do_vendedor_com_a_procuracao(praticado):
    """CN-MA art. 798, VI: a parte representada, com o livro, a folha e a serventia da procuração.
    Decisão do oficial, 03/11/2026 (item 2): «…, neste ato representado por FULANO, conforme procuração
    lavrada no livro X, folha Y, do …», na qualificação do representado. E o procurador não é comprador
    (item 1)."""
    abertura = _abertura(_lavrado(praticado, "cv_por_procurador").termo)
    vendedor = _qualificacao_de(abertura, "MARIO EXEMPLO DOS SANTOS")
    assert EN.tem(vendedor, "neste ato representado(a) por CARLOS EXEMPLO PROCURADOR",
                  "conforme " + EN.PROCURACAO_DO_VENDEDOR)
    assert "CARLOS" not in abertura.split("como OUTORGADO")[1]


def test_quem_representa_a_compradora_vem_na_qualificacao_dela(praticado):
    """CN-MA art. 798, V e VI (a pessoa jurídica, com quem a representa e o ato que lhe dá poderes)."""
    abertura = _abertura(_lavrado(praticado, "cv_pj_compradora").termo)
    assert EN.tem(abertura.split("como OUTORGADO")[1], "neste ato representado(a) por ANA EXEMPLO SOCIA",
                  "conforme contrato social")
    assert "ANA EXEMPLO SOCIA" not in abertura.split("como OUTORGADO")[0]


def test_o_donatario_menor_vem_representado_pela_mae_com_o_assento(praticado):
    """CN-MA art. 798, VII: havendo interesse de menor, o assento e por quem está representado."""
    abertura = _abertura(_lavrado(praticado, "doacao_a_menor").termo)
    donatario = _qualificacao_de(abertura, "PEDRO EXEMPLO MENOR")
    assert EN.tem(donatario, "neste ato representado(a) por JOANA EXEMPLO DOS SANTOS",
                  "conforme " + EN.ASSENTO_DO_MENOR)
    assert "JOANA" not in abertura.split("como OUTORGADO")[0]


def test_o_donatario_menor_nao_assina_e_a_mae_assina_por_ele(praticado):
    """Observação 9, consertada em 03/11/2026: a linha das assinaturas diz quem assina por quem."""
    t = _lavrado(praticado, "doacao_a_menor").termo
    assinam = t.split("Assinam o ato")[1].split("Dou fé")[0]
    assert EN.tem(assinam, "JOANA EXEMPLO DOS SANTOS, REPRESENTANTE, por PEDRO EXEMPLO MENOR")
    assert "PEDRO EXEMPLO MENOR, DONATARIO" not in assinam


def test_a_nubente_menor_vem_assistida_pela_mae(praticado):
    """CC art. 1.654: o pacto do menor depende da aprovação do representante legal — que assiste, e
    não pactua (CN-MA art. 798, VII)."""
    abertura = _abertura(_lavrado(praticado, "pacto_nubente_menor").termo)
    assert EN.tem(_qualificacao_de(abertura, "ANA EXEMPLO NUBENTE"),
                  "neste ato assistido(a) por JOANA EXEMPLO DOS SANTOS")


def test_o_casal_em_comunhao_vende_junto(praticado):
    """Decisão do oficial, 03/11/2026 (item 3): no imóvel do casal em comunhão, os dois cônjuges são
    outorgantes vendedores, cada um qualificado com o outro e o regime (CC art. 215, § 1º, III)."""
    abertura = _abertura(_lavrado(praticado, "cv_casado_com_outorga").termo)
    vendedores = abertura.split("como OUTORGADO")[0]
    # a qualificação de cada um, e não só o nome: o do marido traz «casado com JOANA …»
    assert "MARIO EXEMPLO DOS SANTOS, brasileiro" in vendedores
    assert "JOANA EXEMPLO DOS SANTOS, brasileira" in vendedores
    assert "ANUENTE" not in abertura


def test_o_conjuge_anuente_consente_e_nao_vende(praticado):
    """CC art. 1.647, I: nenhum dos cônjuges pode, sem autorização do outro (exceto na separação
    absoluta), alienar ou gravar de ônus real os bens imóveis. Decisão do oficial, 03/11/2026 (item 3):
    o anuente sai com a frase do consentimento, e nunca como vendedor."""
    abertura = _abertura(_lavrado(praticado, "cv_bem_particular_com_anuente").termo)
    assert EN.tem(abertura, "e, como ANUENTE, JOANA EXEMPLO DOS SANTOS", "que consente no presente ato",
                  "1.647, I")
    antes_do_anuente = abertura.split("como ANUENTE")[0]
    assert "JOANA EXEMPLO DOS SANTOS, brasileira" not in antes_do_anuente


def test_a_outorgada_mulher_e_outorgada(praticado):
    """CC art. 215, § 1º, III: o nome e a qualificação de cada parte. «OUTORGADA» é qualidade da CEP
    (`notas_censec.QUALIFICACAO_PARA_CEP`) — e quem assina a rogo não é outorgante."""
    abertura = _abertura(_lavrado(praticado, "proc_a_rogo").termo)
    assert "QUALIFIQUE A PARTE" not in abertura
    # quem assina a rogo vem na qualificação do outorgante (CC art. 215, § 2º; item 2, 03/11/2026)
    assert EN.tem(_qualificacao_de(abertura, "MARIO EXEMPLO DOS SANTOS"),
                  "assinando a seu rogo PAULO EXEMPLO TESTEMUNHA", "215, § 2º")


def test_o_estado_civil_do_testamento_e_o_da_parte(praticado):
    """CC art. 215, § 1º, III, e art. 1.864, I: o testamento é escrito pelo tabelião conforme as
    declarações do testador — e o estado civil declarado é o da qualificação. Consertado em 03/11/2026
    (item 4): a escolha vem da parte, com o cônjuge e o regime, e o balcão é avisado da diferença."""
    s = _lavrado(praticado, "testamento_casado_marcado_solteiro")
    assert not EN.tem(s.termo, "ser solteiro")
    assert EN.tem(s.termo, "ser casado, sendo seu cônjuge JOANA EXEMPLO DOS SANTOS")
    assert any("vale o da parte" in a for a in s.avisos), s.avisos


def test_o_testamento_nao_deixa_virgula_antes_do_ponto(praticado):
    """O testador solteiro: a cláusula do cônjuge sai, e a vírgula dela junto (item 4)."""
    t = _lavrado(praticado, "testamento_cego").termo
    assert EN.tem(t, "ser solteiro.")
    assert not re.search(r",\s*\.", t)


@pytest.mark.parametrize("chave", ["inventario_viuva_e_dois_herdeiros", "divorcio_com_nome"])
def test_o_advogado_assiste_e_nao_e_parte(praticado, chave):
    """CN-MA arts. 808, § 1º, 819 e 822, § 5º (como o LT02 cita): o advogado assiste as partes.
    Decisão do oficial, 03/11/2026 (item 5): fora da lista das partes, e o «DOS ADVOGADOS» montado dele,
    com a OAB do quadro «Partes»."""
    termo = _lavrado(praticado, chave).termo
    assert "CARLOS EXEMPLO ADVOGADO" not in _abertura(termo)
    assert EN.tem(termo.split("DOS ADVOGADOS")[1], "CARLOS EXEMPLO ADVOGADO, brasileiro",
                  "inscrito(a) na OAB/MA sob o nº 00000")


def test_a_emancipacao_concedida_so_pela_mae_fala_no_singular(praticado):
    """Consertado em 03/11/2026 (item 6): com um só genitor, o singular em cada lugar da minuta."""
    t = _lavrado(praticado, "emancipacao_so_mae").termo
    assert EN.tem(t, "compareceu como OUTORGANTE JOANA", "Declara o(a) OUTORGANTE que é a mãe",
                  "pelo(a) OUTORGANTE", "CONCEDE AO EMANCIPANDO")
    for plural in ("compareceram como OUTORGANTES", "Declaram os OUTORGANTES", "pelos OUTORGANTES",
                   "CONCEDEM"):
        assert not EN.tem(t, plural), plural


def test_a_emancipacao_confere_os_dezesseis_anos(praticado):
    """CC art. 5º, par. ún., I: a emancipação por concessão dos pais exige dezesseis anos completos.
    Consertado em 03/11/2026 (item 7): o teor não se monta, e o balcão diz por quê."""
    s = praticado("emancipacao_menor_de_16")
    assert s.situacao != "LAVRADO"
    assert any("dezesseis anos completos" in a for a in s.avisos), s.avisos


def test_a_data_por_extenso_tem_acento():
    """O dia 3 e o 23: a data por extenso é a do ato (CC art. 215, § 1º, I) e vai ao livro. Consertado
    em 03/11/2026 (item 8), em `livro_nucleo._UNIDADES`."""
    from datetime import datetime

    import notas_teor as NT
    assert NT.valores_campos_data_lavratura(datetime(2026, 11, 3))["dia_por_extenso"] == "três"


# ------------------------------------------------------------------ a segunda leva (03/11/2026)

def test_a_revogacao_desta_serventia_anota_a_procuracao(bancada):
    """CN-MA art. 831 (como o LT02 cita): a revogação lavrada aqui se anota à margem da procuração, e a
    procuração passa a sair revogada no traslado e na certidão — cópia fiel do livro (Lei 8.935/1994,
    art. 6º, II)."""
    procuracao = EN.praticar(bancada, CASOS["proc_alienar_imovel"])
    assert procuracao.situacao == "LAVRADO", procuracao.avisos
    revogacao = EN.praticar(bancada, CASOS["revogacao_da_procuracao"], anterior_id=procuracao.ato_id)
    assert revogacao.situacao == "LAVRADO", revogacao.avisos
    assert F.ato(bancada, procuracao.ato_id)["situacao"] == "REVOGADO"
    traslado = F._texto_do_odt(F.o_traslado(bancada, procuracao.ato_id))
    assert re.search(r"revoga", traslado, re.I), "o traslado da procuração não diz que ela foi revogada"
    pedido = F.abrir_protocolo_pago(bancada, [("13.12.1", 1)], interessado="MARIO EXEMPLO DOS SANTOS")
    cid = F.emitir_certidao(bancada, protocolo=pedido, ato_id=procuracao.ato_id,
                            requerente="MARIO EXEMPLO DOS SANTOS")
    assert re.search(r"revoga", F._texto_do_odt(F.o_papel_da_certidao(bancada, cid)), re.I)


def test_a_certidao_do_testamento_a_terceiro_com_o_testador_vivo_e_recusada(bancada):
    """CN-MA art. 851, § 4º: enquanto vivo o testador, só a ele, por requerimento escrito, se dá
    certidão do testamento; § 5º: a terceiro, só com a certidão de óbito."""
    s = EN.praticar(bancada, CASOS["testamento_cego"])
    assert s.situacao == "LAVRADO", s.avisos
    antes = F._um(bancada, "SELECT count(*) AS n FROM nt_certidoes")["n"]
    html = F._postar(bancada, "/notas/certidoes/emitir",
                     {"ato_id": str(s.ato_id), "requerente": "BEATRIZ EXEMPLO DE SOUZA"},
                     de=f"/notas/certidoes?ato_id={s.ato_id}").get_data(as_text=True)
    assert F._um(bancada, "SELECT count(*) AS n FROM nt_certidoes")["n"] == antes, \
        "a certidão do testamento saiu para terceiro com o testador vivo"
    assert "851" in " ".join(F._flashes(html))


@pytest.mark.parametrize("chave,central", [
    ("cv_casado_com_outorga", "CEP"), ("cv_por_procurador", "CEP"), ("cv_pj_compradora", "CEP"),
    ("doacao_a_menor", "CEP"), ("proc_alienar_imovel", "CEP"), ("emancipacao_so_mae", "CEP"),
    ("divorcio_com_nome", "CESDI"), ("inventario_viuva_e_dois_herdeiros", "CESDI"),
    ("testamento_cego", "RCTO"),
])
def test_cada_ato_vai_a_central_certa_da_censec(praticado, chave, central):
    """CN-MA art. 785 (como o LT02 cita): a escritura e a procuração à CEP, a separação, o divórcio e
    o inventário à CESDI, o testamento ao RCTO — e nunca o testamento à CEP."""
    assert _lavrado(praticado, chave).censec[:1] == (central,)


@pytest.mark.parametrize("chave", ["cv_casado_com_outorga", "cv_por_procurador", "cv_pj_compradora",
                                   "doacao_a_menor", "proc_alienar_imovel", "emancipacao_so_mae"])
def test_a_escritura_e_a_procuracao_ficam_prontas_para_a_cep(praticado, chave):
    """A CEP trava a lavratura (09/10/2026): o que foi ao livro está pronto para a remessa."""
    assert _lavrado(praticado, chave).censec[1] == "PRONTO", _lavrado(praticado, chave).censec


@pytest.mark.parametrize("chave,alienantes,adquirentes", [
    ("cv_casado_com_outorga", ["MARIO EXEMPLO DOS SANTOS", "JOANA EXEMPLO DOS SANTOS"],
     ["BEATRIZ EXEMPLO DE SOUZA"]),
    ("cv_bem_particular_com_anuente", ["MARIO EXEMPLO DOS SANTOS"], ["BEATRIZ EXEMPLO DE SOUZA"]),
    ("cv_por_procurador", ["MARIO EXEMPLO DOS SANTOS"], ["BEATRIZ EXEMPLO DE SOUZA"]),
    ("cv_pj_compradora", ["MARIO EXEMPLO DOS SANTOS"], ["EXEMPLO COMERCIO DE MATERIAIS LTDA"]),
    ("doacao_a_menor", ["MARIO EXEMPLO DOS SANTOS"], ["PEDRO EXEMPLO MENOR"]),
])
def test_a_doi_tem_quem_aliena_e_quem_adquire_e_mais_ninguem(praticado, chave, alienantes, adquirentes):
    """CN-MA arts. 797 e 800, VII (Lei 10.426/2002, art. 8º): na DOI, os titulares da operação — e não
    o procurador, o representante, o cônjuge anuente nem o advogado."""
    doi = _lavrado(praticado, chave).doi
    assert (doi.get("alienantes"), doi.get("adquirentes"), doi.get("duvidas")) == (alienantes, adquirentes, []), doi


def test_a_doadora_e_a_donataria_vao_ao_livro_e_a_doi(praticado):
    """CC art. 215, § 1º, III: a qualificação de cada parte, no feminino como no masculino. Consertado em
    03/11/2026 (item 13)."""
    s = _lavrado(praticado, "doacao_doadora_a_donataria")
    assert (s.doi.get("alienantes"), s.doi.get("adquirentes")) == (["JOANA EXEMPLO DOS SANTOS"],
                                                                   ["BEATRIZ EXEMPLO DE SOUZA"]), s.doi


@_defeito("a CESDI pede a qualidade de cada parte (Advogado, Divorciando, Herdeiro, Falecido…), a data do "
          "casamento, o regime e o responsável pelos menores, e a tela do ato não tem onde dizê-los: todo "
          "divórcio e todo inventário ficam parados na remessa (item 14)")
@pytest.mark.parametrize("chave", ["divorcio_com_nome", "inventario_viuva_e_dois_herdeiros"])
def test_o_divorcio_e_o_inventario_ficam_prontos_para_a_cesdi(praticado, chave):
    """CN-MA art. 785 (a remessa à CESDI) e o layout dela (`notas_censec.MINIMO_PARTES_CESDI`)."""
    assert _lavrado(praticado, chave).censec[1] == "PRONTO", _lavrado(praticado, chave).censec


@_defeito("o RCTO pede a data de nascimento e o nome da mãe do testador, e o quadro «Partes» não tem a "
          "data, e tem a filiação só como texto livre: todo testamento fica parado na remessa (item 15)")
def test_o_testamento_fica_pronto_para_o_rcto(praticado):
    """CN-MA art. 785, I (a remessa ao RCTO)."""
    assert _lavrado(praticado, "testamento_cego").censec[1] == "PRONTO", _lavrado(praticado, "testamento_cego").censec
