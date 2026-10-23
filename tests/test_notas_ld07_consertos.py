"""Os consertos do LD07 nas Notas — o caminho de cada um, 21/10/2026.

    «corrija tudo» — o oficial, depois de ver a lista dos elementos que a
    norma exige no papel e que os modelos das Notas não tinham (LT02).

O QUE ESTE ARQUIVO MEDE
    Os 38 casos da matriz que eram `xfail` moram em
    `tests/test_requisitos_notas.py` e agora passam: ela mede o papel montado
    com um contexto completo. Aqui fica o que ela não mede — o caminho de cada
    conserto pelas telas e pelo domínio, e o de ERRO:

      - a qualificação (CNN art. 111): a parte sem o documento de identidade e
        sem a união estável sai marcada, e o ato NÃO vai ao livro — sem selo e
        sem gastar o item pago; completada pela tela, lavra;
      - a parte tirada do cartão traz o RG, a filiação e o cônjuge da ficha;
      - a testemunha não ganha marca, e o casado sem cônjuge nem regime também
        não (pergunta ao oficial, `relatorios/LD07.perguntas.md`);
      - a ficha do cartão: a data de abertura, o título eleitoral e a firma
        três vezes (CN-MA art. 864, § 1º, I, III e V; art. 867);
      - a autenticação com a ressalva do original (art. 836);
      - a certidão positiva com o termo do ato achado (arts. 792 e 851, § 1º);
      - a pública forma: o papel é o de `papel_html`, e a marca do selo não
        sobra no `.odt`.

    Os ajudantes e a bancada (`balcao`: o escrevente pelas telas, o selador
    falso com TLS e a trava do selo pago LIGADA) são os de
    `tests/test_fluxo_notas.py`.

Dados fictícios (docs/AGENTES.md): nomes «EXEMPLO», Cidade Exemplo, CNS
000000, CPFs da lista `tests/fixtures/anti_vazamento/documentos_ficticios.txt`.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import notas_certidao as NCE                                 # noqa: E402
import notas_schema as NS                                    # noqa: E402
import notas_teor as NT                                      # noqa: E402
import nt_publica_forma as PF                                # noqa: E402
from bd_nativo import banco                                  # noqa: E402
from test_fluxo_notas import (                               # noqa: E402
    ESCREVENTE, HOJE_BR, PESSOAS, QUALIFICACAO_DA_PESSOA, QUALIFICACAO_DO_CARTAO,
    _caso, _emitir_publica_forma, _etiqueta, _flashes, _postar, _texto_do_odt, _um,
    _usado, abrir_o_ato, abrir_protocolo_pago, ato, balcao, emitir_certidao,
    etiqueta_da_autenticacao, lancar_no_livro, lavrar_pela_tela, ligar_ao_protocolo,
    o_papel_da_certidao, preencher_pelo_modelo)

assert balcao  # a bancada vem de lá (o pytest a acha pelo nome)

MARCA_DA_IDENTIDADE = "[DOCUMENTO DE IDENTIDADE OU FILIAÇÃO]"
MARCA_DA_UNIAO = "[UNIÃO ESTÁVEL — SIM OU NÃO]"

# Uma parte de exemplo, com o que a qualificação pedia ANTES do LD07 — os seis
# do Código Civil — e nada do que o CNN art. 111 acrescentou.
SO_O_DE_ANTES = {k: v for k, v in QUALIFICACAO_DA_PESSOA.items()
                 if k not in ("identidade", "uniao_estavel")}


# ================================================ a qualificação, pelo domínio


def _pf(**mais) -> dict:
    return {"nome": "MARIO EXEMPLO DOS SANTOS", "documento": "00000000191",
            "tipo_pessoa": "F", "nacionalidade": "brasileiro",
            "estado_civil": "solteiro", "profissao": "comerciante",
            "endereco": "Rua Exemplo, 10, Cidade Exemplo-MA", **mais}


def test_a_parte_sem_identidade_nem_uniao_estavel_sai_marcada_e_pendente():
    """O que o CNN art. 111 pôs na qualificação e falta sai entre colchetes,
    como os seis de antes — e a lista de pendências diz quais são."""
    texto = NT.qualificar(_pf())
    assert MARCA_DA_IDENTIDADE in texto and MARCA_DA_UNIAO in texto, texto
    faltas = NT.pendencias_da_qualificacao([_pf()])
    assert faltas and "documento de identidade ou filiação" in faltas[0]
    assert "união estável" in faltas[0]


def test_a_qualificacao_completa_segue_a_ordem_e_nao_tem_marca():
    """Estado civil, união estável, profissão, documento de identidade, CPF e
    domicílio — e a filiação só na falta do documento."""
    texto = NT.qualificar(_pf(identidade="1234567 SSP/MA", uniao_estavel="NAO"))
    assert "[" not in texto, texto
    assert re.search(r"solteiro, que declara não conviver em união estável, "
                     r"comerciante, portador\(a\) do documento de identidade n\. "
                     r"1234567 SSP/MA, inscrito\(a\) no CPF", texto), texto
    sem_doc = NT.qualificar(_pf(filiacao="PAI DE EXEMPLO e MAE DE EXEMPLO",
                                uniao_estavel="NAO"))
    assert "filho(a) de PAI DE EXEMPLO e MAE DE EXEMPLO" in sem_doc, sem_doc
    assert NT.pendencias_da_qualificacao([_pf(identidade="1", uniao_estavel="NAO")]) == []


def test_a_uniao_estavel_declarada_entra_com_o_companheiro():
    texto = NT.qualificar(_pf(identidade="1234567 SSP/MA", uniao_estavel="SIM",
                              conjuge="ANA EXEMPLO DOS SANTOS"))
    assert "que declara conviver em união estável com ANA EXEMPLO DOS SANTOS" in texto


def test_o_casado_com_conjuge_e_regime_os_tem_na_qualificacao():
    """CC art. 215, § 1º, III; CN-MA art. 798, V: o nome do cônjuge e o
    regime de bens de quem é casado."""
    texto = NT.qualificar(_pf(estado_civil="casado", identidade="1", uniao_estavel="NAO",
                              conjuge="ANA EXEMPLO DOS SANTOS",
                              regime_bens="comunhão parcial"))
    assert ("casado com ANA EXEMPLO DOS SANTOS, sob o regime de bens da comunhão "
            "parcial") in texto, texto


def test_o_casado_sem_conjuge_nem_regime_nao_ganha_marca_mas_com_a_metade_ganha():
    """A lei pede o cônjuge e o regime «quando necessário» (CC) ou no ato de
    imóvel (CN-MA): o montador não sabe de que é o ato, e exigir sempre é
    pergunta ao oficial. Dito um dos dois, o outro sai marcado."""
    base = _pf(estado_civil="casado", identidade="1", uniao_estavel="NAO")
    assert "[" not in NT.qualificar(base)
    assert NT.pendencias_da_qualificacao([base]) == []
    metade = dict(base, conjuge="ANA EXEMPLO DOS SANTOS")
    assert "[REGIME DE BENS]" in NT.qualificar(metade)
    assert "regime de bens" in NT.pendencias_da_qualificacao([metade])[0]


def test_a_testemunha_sem_os_dados_novos_sai_como_antes():
    """O art. 111 fala dos sujeitos do ato; a testemunha não é parte — o que
    ela tiver entra, o que não tiver não se cobra."""
    texto = NT.qualificar(_pf(testemunha=1, estado_civil="casado"))
    assert "[" not in texto, texto
    assert NT.pendencias_da_qualificacao([_pf(testemunha=1)]) == []
    com_doc = NT.qualificar(_pf(testemunha=1, identidade="1234567 SSP/MA"))
    assert "portador(a) do documento de identidade n. 1234567 SSP/MA" in com_doc


# ================================================== a qualificação, pela tela


def _abrir_a_quitacao(b, protocolo: dict, dados_da_parte: dict) -> int:
    """A escritura de quitação (13.2), com uma parte digitada do zero."""
    caso = _caso("NT-ESC-QUITACAO")
    ato_id = abrir_o_ato(b, caso.minuta, interessado="MARIO EXEMPLO DOS SANTOS")
    ligar_ao_protocolo(b, ato_id, protocolo)
    html = _postar(b, f"/notas/atos/{ato_id}",
                   {"acao": "parte_nova", "nome": "MARIO EXEMPLO DOS SANTOS",
                    "documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                    "qualificacao": "OUTORGANTE", **dados_da_parte}).get_data(as_text=True)
    assert "Parte incluída" in " ".join(_flashes(html)), _flashes(html)
    _postar(b, f"/notas/escrituras/{ato_id}/valor", {"valor": "0"},
            de=f"/notas/atos/{ato_id}")
    return ato_id


def test_o_ato_com_a_qualificacao_incompleta_nao_vai_ao_livro_nem_gasta_o_item(balcao):
    """O CAMINHO DE ERRO: a parte sem o documento de identidade e sem a união
    estável deixa o teor com as duas marcas, e a trava da lavratura (o campo
    em branco do teor) recusa — o ato fica em lavratura, sem folha e sem
    selo, e o 13.2 pago não é gasto (CN-MA arts. 130, § 2º, e 795, § 2º)."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.2", 1)])
    ato_id = _abrir_a_quitacao(b, protocolo, SO_O_DE_ANTES)
    preencher_pelo_modelo(b, ato_id, "NT-ESC-QUITACAO", aceita_pendencia=True)
    teor = ato(b, ato_id)["teor"]
    assert MARCA_DA_IDENTIDADE in teor and MARCA_DA_UNIAO in teor
    recado = lancar_no_livro(b, ato_id, item="13.2")
    a = ato(b, ato_id)
    assert a["situacao"] == "EM_LAVRATURA", recado
    assert not a["selo"] and not a["folha"] and not a["termo"], recado
    assert "campo em branco" in recado and "UNIÃO ESTÁVEL" in recado, recado
    assert _usado(b, protocolo, "13.2") == 0, "o item pago foi gasto sem o ato lavrar"


def test_completar_a_qualificacao_na_tela_tira_a_marca_e_o_ato_lavra(balcao):
    """A parte incluída sem os dados novos se completa na própria tela do ato
    (`acao=qualificacao_civil`), sem tirá-la; montado de novo, o teor sai
    sem marca, e o ato vai ao livro com o selo pelo item pago."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.2", 1)])
    ato_id = _abrir_a_quitacao(b, protocolo, SO_O_DE_ANTES)
    parte = _um(b, "SELECT id FROM nt_ato_partes WHERE ato_id = %s ORDER BY id",
                (ato_id,))
    html = _postar(b, f"/notas/atos/{ato_id}",
                   {"acao": "qualificacao_civil", "parte_id": str(parte["id"]),
                    "identidade": "1234567 SSP/MA", "uniao_estavel": "NAO"}
                   ).get_data(as_text=True)
    assert "Qualificação da parte completa" in " ".join(_flashes(html)), _flashes(html)
    gravada = _um(b, "SELECT identidade, uniao_estavel FROM nt_ato_partes WHERE id = %s",
                  (parte["id"],))
    assert gravada == {"identidade": "1234567 SSP/MA", "uniao_estavel": "NAO"}
    preencher_pelo_modelo(b, ato_id, "NT-ESC-QUITACAO")
    teor = ato(b, ato_id)["teor"]
    assert "[" not in re.sub(r"<[^>]+>", "", teor), teor
    assert "portador(a) do documento de identidade n. 1234567 SSP/MA" in teor
    assert "que declara não conviver em união estável" in teor
    recado = lancar_no_livro(b, ato_id, item="13.2")
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO" and a["selo"], recado
    assert _usado(b, protocolo, "13.2") == 1


def test_a_parte_tirada_do_cartao_traz_o_rg_a_filiacao_e_o_conjuge_da_ficha(balcao):
    """O cartão de autógrafo já tem o RG, o pai e a mãe e o cônjuge: a parte
    que vem dele os traz para a qualificação. A união estável o cartão não
    tem — é declaração da parte em cada ato, e vem do formulário."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.17.1", 1), ("13.2", 1)])
    r = _postar(b, "/notas/cartoes",
                {"acao": "novo", "nome": "MARIO EXEMPLO DOS SANTOS",
                 "documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 **dict(QUALIFICACAO_DO_CARTAO, estado_civil="casado",
                        conjuge="ANA EXEMPLO DOS SANTOS")}, seguir=False)
    cid = int(re.search(r"/notas/cartoes/(\d+)$", r.headers["Location"]).group(1))
    ato_id = abrir_o_ato(b, "NT-ESC-QUITACAO", interessado="MARIO EXEMPLO DOS SANTOS")
    ligar_ao_protocolo(b, ato_id, protocolo)
    html = _postar(b, f"/notas/atos/{ato_id}",
                   {"acao": "parte_cartao", "cartao_id": str(cid),
                    "qualificacao": "OUTORGANTE", "uniao_estavel": "NAO"}
                   ).get_data(as_text=True)
    assert "Parte incluída" in " ".join(_flashes(html)), _flashes(html)
    parte = _um(b, """SELECT * FROM nt_ato_partes WHERE ato_id = %s
                      ORDER BY id""", (ato_id,))
    assert parte["identidade"] == "1234567 SSP"
    assert parte["filiacao"] == "PAI DE EXEMPLO e MAE DE EXEMPLO"
    assert parte["conjuge"] == "ANA EXEMPLO DOS SANTOS"
    assert parte["uniao_estavel"] == "NAO"
    # o cartão não diz o regime de bens: dito o cônjuge, o regime sai marcado
    assert "com ANA EXEMPLO DOS SANTOS, sob o regime de bens da [REGIME DE BENS]" in (
        NT.qualificar(parte))
    assert "regime de bens" in NT.pendencias_da_qualificacao([parte])[0]


# ======================================================= a ficha do cartão


def test_a_ficha_traz_a_abertura_o_titulo_eleitoral_e_a_firma_tres_vezes(balcao):
    """CN-MA art. 864, § 1º: a data de ABERTURA (I — a do fecho é a do dia em
    que se imprime), o título eleitoral, se houver (III), e a firma «ao menos
    três vezes» (V; art. 867: cada assinatura três vezes). O título se informa
    ao abrir o cartão e se corrige na ficha dele."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 1)])
    r = _postar(b, "/notas/cartoes",
                {"acao": "novo", "nome": "MARIO EXEMPLO DOS SANTOS",
                 "documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 "titulo_eleitor": "000000000000", **QUALIFICACAO_DO_CARTAO},
                seguir=False)
    cid = int(re.search(r"/notas/cartoes/(\d+)$", r.headers["Location"]).group(1))
    cartao = _um(b, "SELECT titulo_eleitor, abertura FROM nt_cartoes WHERE id = %s", (cid,))
    assert cartao["titulo_eleitor"] == "000000000000"
    ficha = _texto_do_odt(b["cliente"].get(f"/notas/cartoes/{cid}/ficha").data)
    abertura = cartao["abertura"]
    assert f"aberta em {abertura[8:10]}/{abertura[5:7]}/{abertura[:4]}" in ficha, ficha
    assert "Título eleitoral" in ficha and "000000000000" in ficha
    assert "três vezes" in ficha
    autografos = ficha.split("Autógrafos", 1)[1].split("Fotografia", 1)[0]
    assert autografos.count("_" * 64) == 9, "cada forma de assinar, três vezes"

    _postar(b, f"/notas/cartoes/{cid}", {"acao": "editar", "titulo_eleitor": "111111111111"})
    assert _um(b, "SELECT titulo_eleitor FROM nt_cartoes WHERE id = %s",
               (cid,))["titulo_eleitor"] == "111111111111"


def test_o_cartao_do_e_oficio_sem_data_de_abertura_nao_ganha_a_data_da_carga(balcao):
    """O cartão importado do E-Ofício traz a abertura de lá (`dtmAbertura`).
    Sem ela, o dia em que nasceu no sistema é o da carga, e não o da abertura:
    a ficha não afirma uma data que não sabe. O aberto aqui sem a coluna usa
    o dia em que nasceu, que é o da abertura."""
    b = balcao
    with b["db"].transaction() as con:
        cid = banco(con).escrever(
            """INSERT INTO nt_cartoes (numero, nome, nome_norm, documento, origem,
                   criado_em)
               VALUES (4071, 'MARIO EXEMPLO DOS SANTOS', 'mario exemplo dos santos',
                       '00000000191', 'EOFICIO', '2026-10-01T09:00:00')
               RETURNING id""")[0]["id"]
    ficha = _texto_do_odt(b["cliente"].get(f"/notas/cartoes/{cid}/ficha").data)
    assert "Ficha nº 4071" in ficha and "aberta em" not in ficha, ficha[:200]
    with b["db"].transaction() as con:
        banco(con).escrever("UPDATE nt_cartoes SET origem = 'MANUAL' WHERE id = %s", (cid,))
    ficha = _texto_do_odt(b["cliente"].get(f"/notas/cartoes/{cid}/ficha").data)
    assert "Ficha nº 4071, aberta em 01/10/2026" in ficha, ficha[:200]


# ======================================================== a autenticação


def _autenticar_com(b, **mais) -> int:
    abrir_protocolo_pago(b, [("13.18", 1)])
    antes = _um(b, "SELECT coalesce(max(id), 0) AS n FROM nt_autenticacoes")["n"]
    html = _postar(b, "/notas/autenticacao",
                   {"acao": "autenticar", "folhas": "1", "tipo": "PADRAO",
                    "documento_tipo": "Contrato", "documento_descricao": "contrato de exemplo",
                    "apresentante": "MARIO EXEMPLO DOS SANTOS",
                    "apresentante_documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                    **mais}).get_data(as_text=True)
    nova = _um(b, "SELECT id FROM nt_autenticacoes WHERE id > %s ORDER BY id", (antes,))
    assert nova, "a autenticação não foi lavrada: " + " ".join(_flashes(html))
    return int(nova["id"])


def test_a_autenticacao_ressalva_a_rasura_do_original(balcao):
    """«verificará, com cautela, se o documento original contém rasuras ou
    quaisquer outros defeitos, os quais serão ressalvados na autenticação»
    (CN-MA art. 836). A ressalva vai ao teor, à etiqueta e à coluna própria."""
    b = balcao
    aid = _autenticar_com(b, ressalva="  a folha 1 do original tem rasura na data.  ")
    a = _um(b, "SELECT texto, ressalva, selo FROM nt_autenticacoes WHERE id = %s", (aid,))
    assert a["ressalva"] == "a folha 1 do original tem rasura na data."
    assert a["texto"].endswith(" RESSALVA: a folha 1 do original tem rasura na data."), a
    tira = _etiqueta(etiqueta_da_autenticacao(b, aid))
    assert "RESSALVA: a folha 1 do original tem rasura na data." in tira
    assert a["selo"] in tira and ESCREVENTE in tira


def test_a_autenticacao_sem_ressalva_sai_como_antes(balcao):
    """Original sem defeito não pede frase: o teor é a fórmula de sempre."""
    b = balcao
    aid = _autenticar_com(b)
    a = _um(b, "SELECT texto, ressalva FROM nt_autenticacoes WHERE id = %s", (aid,))
    assert a["ressalva"] is None
    assert a["texto"] == NS.texto_autenticacao("PADRAO")
    assert "RESSALVA" not in a["texto"]


# ================================================== a certidão positiva


def test_a_certidao_positiva_diz_o_termo_de_cada_ato_achado(balcao):
    """A localização do ato no livro é o livro, a folha E o número — «a
    numeração das escrituras ... não será interrompida» (CN-MA arts. 792 e
    851, § 1º). A positiva dizia o livro e a folha."""
    b = balcao
    caso = _caso("NT-ESC-COMPRA-VENDA")
    protocolo = abrir_protocolo_pago(
        b, [("FAIXA", 1), ("13.12.1", 1)], base_da_faixa=caso.valor)
    ato_id, _item, recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO" and a["termo"], recado
    positiva = emitir_certidao(b, protocolo=protocolo, nome="MARIO EXEMPLO DOS SANTOS")
    corpo = _texto_do_odt(o_papel_da_certidao(b, positiva))
    assert f"folha {a['folha']}, termo n. {a['termo']}" in corpo, corpo


def test_o_ato_do_acervo_sem_termo_sai_com_a_ordem_na_certidao_positiva():
    """O acervo do E-Ofício tem a ordem e não o termo: a positiva o diz como o
    inteiro teor diz. Sem nenhum dos dois, a linha é a de antes."""
    achado = {"rotulo_tipo": "Procuração", "natureza": None, "livro": "15",
              "folha": "42", "data": "08/09/2026", "qualificacao": "OUTORGANTE"}
    comum = {"requerente": "JOANA EXEMPLO DA SILVA", "nome": "MARIO EXEMPLO DOS SANTOS",
             "documento": "", "periodo": "em todo o acervo do sistema", "finalidade": None}
    com_ordem = NCE.montar_teor(tipo="POSITIVA", achados=[dict(achado, numero_ordem=33)],
                                **comum)
    assert "folha 42, ordem n. 33, de 08/09/2026" in com_ordem
    sem_nada = NCE.montar_teor(tipo="POSITIVA", achados=[achado], **comum)
    assert "folha 42, de 08/09/2026" in sem_nada and "termo n." not in sem_nada


# ===================================================== a pública forma


def test_a_moldura_da_publica_forma_tem_lugar_data_quem_expede_e_a_marca_do_selo():
    """`papel_html` é a moldura da rota (LD02), fora dela para a matriz medir o
    papel: o teor congelado, o lugar e a data da emissão, quem a expede, o
    rodapé com a impressão digital e, por último, a marca do selo."""
    pf = {"teor": "<p><b>PÚBLICA FORMA</b> n. 3/2026</p>", "situacao": "EMITIDA",
          "emitida_em": "2026-10-20T10:30:00", "emitida_por": "PEDRO EXEMPLO DOS SANTOS",
          "emitida_por_funcao": "Escrevente autorizado", "numero": 3, "ano": 2026,
          "hash_teor": "0" * 64}
    papel = PF.papel_html(pf, sv={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    assert papel.startswith(pf["teor"])
    assert papel.endswith(f"<p>{PF.MARCA_DO_SELO}</p>")
    assert papel.count(PF.MARCA_DO_SELO) == 1
    for valor in ("Cidade Exemplo-MA, ", "PEDRO EXEMPLO DOS SANTOS", "Escrevente autorizado",
                  "Pública forma n. 3/2026, emitida em 20/10/2026 às 10:30:00", "0" * 64):
        assert valor in papel, valor
    cancelada = PF.papel_html(dict(pf, situacao="CANCELADA",
                                   motivo_cancelamento="erro de exemplo"),
                              sv={"ri_cidade": "Cidade Exemplo", "ri_uf": "MA"})
    assert cancelada.startswith('<p align="center"><b>PÚBLICA FORMA CANCELADA — erro de exemplo')


def test_o_papel_da_publica_forma_tem_o_selo_no_lugar_da_marca(balcao):
    """Pela rota: o quadro do selo entra onde a moldura marca, e a marca não
    sobra no papel; o lugar e a data da emissão estão lá."""
    b = balcao
    pf_id, _ = _emitir_publica_forma(b)
    pf = _um(b, "SELECT selo FROM nt_publicas_formas WHERE id = %s", (pf_id,))
    r = b["cliente"].get(f"/notas/publica-forma/{pf_id}/odt?formato=odt")
    assert r.status_code == 200
    papel = _texto_do_odt(r.data)
    assert PF.MARCA_DO_SELO not in papel and "@@" not in papel
    assert "SELO DA PÚBLICA FORMA" in papel and pf["selo"] in papel
    assert "Cidade Exemplo-MA," in papel and ESCREVENTE in papel
    assert HOJE_BR in papel
