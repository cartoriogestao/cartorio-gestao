"""Os consertos do LD02 nas Notas — o caminho de erro de cada um, 21/10/2026.

    «corrija tudo» — o oficial, depois de ver a lista dos defeitos que os
    lotes LT01–LT06 acharam e deixaram em `xfail(strict=True)`.

O QUE ESTE ARQUIVO MEDE
    Os testes que eram `xfail` moram em `tests/test_fluxo_notas.py` e em
    `tests/test_requisitos_notas.py`, e agora passam. Aqui fica o que eles não
    medem: o CAMINHO DE ERRO de cada conserto que mexe em selo, dinheiro ou
    número — nada de ato concluído sem selo (CN-MA art. 130, § 2º), nada de
    item pago gasto pelo item errado, nada de número repetido — e a recusa de
    cada tela nova.

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

import pytest

RAIZ = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RAIZ))
sys.path.insert(0, str(RAIZ / "tests"))

import banco_pg                                              # noqa: E402
import notas_certidao as NCE                                 # noqa: E402
import notas_livro as NL                                     # noqa: E402
from bd_nativo import banco                                  # noqa: E402
from test_fluxo_notas import (                               # noqa: E402
    CEM_MIL, COMPRA, ESCREVENTE, PESSOAS, SEGUNDA, VENDE, Caso, _caso, _etiqueta,
    _flashes, _ler, _o_papel_de_balcao_e_adequado, _postar, _reconhecer_sinal,
    _tela, _texto_do_odt, _um, _usado, abrir_cartao, abrir_protocolo_pago, ato,
    balcao, emitir_certidao, etiqueta_do_reconhecimento, itens_oferecidos,
    lancar_no_livro, lavrar_pela_tela, o_papel_da_certidao, preparar_o_ato,
    reconhecer)

assert balcao  # a bancada vem de lá (o pytest a acha pelo nome)


def _selos_do_ato(b, ato_id: int) -> list[dict]:
    return _ler(b, "SELECT numero, caminho FROM sd_selos WHERE tabela = 'nt_atos' "
                   "AND ato_id = %s ORDER BY id", (ato_id,))


# ===================================== o item próprio da espécie, no selo


def test_o_divorcio_sem_bens_sela_pelo_13_7_no_caminho_sem_valor_e_gasta_o_item_pago(balcao):
    """O 13.7 é da escritura «sem bens a partilhar»: valor zero é SEM valor, e
    o selo sai pelo caminho sem valor, como a tela o mostra. Até o LD02 o zero
    ia pelo caminho com valor declarado, e a tela não oferecia o 13.7."""
    b = balcao
    caso = Caso("NT-ESC-DIVORCIO", "ESCRITURA", [VENDE, SEGUNDA], valor=0, item="13.7")
    protocolo = abrir_protocolo_pago(b, [("13.7", 1)])
    ato_id, item, recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    assert item == "13.7" and a["situacao"] == "LAVRADO" and a["selo"], recado
    assert _usado(b, protocolo, "13.7") == 1, "o selo não gastou o 13.7 pago"
    assert [s["caminho"] for s in _selos_do_ato(b, ato_id)] == [
        "/selo/notas/ato-declarado/sem-valor"]


def test_o_substabelecimento_sela_pelo_13_9_5_que_o_protocolo_pagou(balcao):
    """O item próprio do substabelecimento (13.9.5), oferecido pela tela, é o
    que o selo pede e o que gasta — com o arquivamento obrigatório ao lado."""
    b = balcao
    caso = Caso("NT-SUBSTABELECIMENTO", "SUBSTABELECIMENTO", [VENDE, COMPRA],
                item="13.9.5", especie="PODERES_ESPECIFICOS")
    protocolo = abrir_protocolo_pago(b, [("13.9.5", 1)])
    ato_id, _item, recado = lavrar_pela_tela(b, caso, protocolo)
    a = ato(b, ato_id)
    assert a["situacao"] == "LAVRADO" and a["selo"] and a["selo_arquivamento"], recado
    assert _usado(b, protocolo, "13.9.5") == 1


def test_o_item_proprio_que_o_protocolo_nao_pagou_nao_sela_e_o_ato_fica_suspenso(balcao):
    """O CAMINHO DE ERRO: o protocolo pagou o 13.9.3 e o escrevente escolhe o
    13.9.5. O selo não sai (a trava do selo pago não acha o item), o ato fica
    SUSPENSO, sem selo — nada de ato concluído sem selo (CN-MA art. 130, § 2º)
    —, e o 13.9.3 pago não é gasto pelo item errado."""
    b = balcao
    caso = Caso("NT-SUBSTABELECIMENTO", "SUBSTABELECIMENTO", [VENDE, COMPRA],
                item="13.9.5", especie="PODERES_ESPECIFICOS")
    protocolo = abrir_protocolo_pago(b, [("13.9.3", 1)])
    ato_id = preparar_o_ato(b, caso, protocolo)
    assert "13.9.5" in itens_oferecidos(b, ato_id)
    recado = lancar_no_livro(b, ato_id, item="13.9.5", especie=caso.especie)
    a = ato(b, ato_id)
    assert a["situacao"] == "SUSPENSO_SELO" and not a["selo"], recado
    assert "NÃO concluído" in recado, recado
    assert _usado(b, protocolo, "13.9.3") == 0, "o item pago foi gasto pelo item errado"
    assert not _selos_do_ato(b, ato_id)


def test_o_restabelecimento_nao_ganha_o_13_7_que_e_da_separacao_e_do_divorcio(balcao):
    """O 13.7 é de separação, divórcio e extinção da união estável sem bens; o
    restabelecimento da sociedade conjugal não está nele."""
    b = balcao
    caso = _caso("NT-ESC-RESTABELECIMENTO")
    protocolo = abrir_protocolo_pago(b, [("13.2", 1)])
    ato_id = preparar_o_ato(b, caso, protocolo)
    oferecidos = itens_oferecidos(b, ato_id)
    assert "13.2" in oferecidos and "13.7" not in oferecidos, oferecidos


# ===================================== a ata para usucapião, pela faixa


def test_o_valor_do_imovel_da_ata_para_usucapiao_se_informa_na_ficha(balcao):
    """A ficha da ata para usucapião tem o campo do valor (CNN art. 423, I), a
    gravação volta para a ficha, e a tela passa a oferecer a faixa do 13.1 —
    e só ela."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("FAIXA", 1)], base_da_faixa=CEM_MIL)
    caso = Caso("NT-ATA-USUCAPIAO", "ATA_USUCAPIAO",
                [("MARIO EXEMPLO DOS SANTOS", "REQUERENTE", False)])
    ato_id = preparar_o_ato(b, caso, protocolo)
    ficha = _tela(b, f"/notas/atos/{ato_id}")
    assert f"/notas/escrituras/{ato_id}/valor" in ficha and "Valor do imóvel" in ficha
    assert not itens_oferecidos(b, ato_id), "sem o valor o selo não tem item"
    r = _postar(b, f"/notas/escrituras/{ato_id}/valor",
                {"valor": "100.000,00", "voltar": "ato"},
                de=f"/notas/atos/{ato_id}", seguir=False)
    assert r.status_code == 302 and r.headers["Location"].endswith(f"/notas/atos/{ato_id}")
    assert ato(b, ato_id)["valor_transacao"] == CEM_MIL
    assert itens_oferecidos(b, ato_id) == [protocolo["itens"][0]["codigo_ato"]]


def test_a_ata_para_usucapiao_recusa_o_item_que_nao_e_a_faixa_do_valor(balcao):
    """O 13.14.1 é da ata comum. A de usucapião se cobra pela faixa do valor
    venal (CNN art. 423, I): outro item é recusado ANTES de a folha ser gasta."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("FAIXA", 1), ("13.14.1", 1)],
                                     base_da_faixa=CEM_MIL)
    ato_id = preparar_o_ato(b, _caso("NT-ATA-USUCAPIAO"), protocolo)
    recado = lancar_no_livro(b, ato_id, item="13.14.1")
    a = ato(b, ato_id)
    assert "Ato NÃO lançado" in recado and "exige o item 13.1." in recado, recado
    assert not a["livro"] and not a["selo"] and a["situacao"] == "EM_LAVRATURA"
    assert _usado(b, protocolo, "13.14.1") == 0


def test_o_valor_nao_se_lanca_na_ata_comum(balcao):
    """Só a escritura e a ata para usucapião declaram valor."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.14.1", 1)])
    ato_id = preparar_o_ato(b, _caso("NT-ATA-NOTARIAL"), protocolo)
    html = _postar(b, f"/notas/escrituras/{ato_id}/valor",
                   {"valor": "100.000,00", "voltar": "ato"},
                   de=f"/notas/atos/{ato_id}").get_data(as_text=True)
    assert "só se lança em escritura ou em ata para usucapião" in " ".join(
        _flashes(html))
    assert ato(b, ato_id)["valor_transacao"] is None


# ===================================== a certidão em breve relato


def _lavrar_compra_e_venda(b, *, certidoes: int = 1) -> tuple[int, dict]:
    caso = _caso("NT-ESC-COMPRA-VENDA")
    protocolo = abrir_protocolo_pago(b, [("FAIXA", 1), ("13.12.1", certidoes)],
                                     base_da_faixa=caso.valor)
    ato_id, _item, recado = lavrar_pela_tela(b, caso, protocolo)
    assert ato(b, ato_id)["situacao"] == "LAVRADO", recado
    return ato_id, protocolo


def test_o_breve_relato_sai_do_ato_sem_teor_e_o_inteiro_teor_nao(balcao):
    """O breve relato se monta dos campos do livro, e o ato do acervo que veio
    sem o teor continua tendo o que se resumir; o inteiro teor, não — ele
    reproduz o livro, e sem o teor a recusa vem antes de numerar."""
    b = balcao
    ato_id, protocolo = _lavrar_compra_e_venda(b, certidoes=2)
    with b["db"].transaction() as con:
        banco(con).escrever("UPDATE nt_atos SET teor = NULL WHERE id = %s", (ato_id,))
    tela = _tela(b, f"/notas/certidoes?ato_id={ato_id}")
    assert 'value="BREVE_RELATO"' in tela and 'value="INTEIRO_TEOR"' not in tela
    antes = _um(b, "SELECT count(*) AS n FROM nt_certidoes")["n"]
    html = _postar(b, "/notas/certidoes/emitir",
                   {"ato_id": str(ato_id), "tipo": "INTEIRO_TEOR",
                    "protocolo_id": str(protocolo["id"])},
                   de=f"/notas/certidoes?ato_id={ato_id}").get_data(as_text=True)
    assert "sem o teor" in " ".join(_flashes(html))
    assert _um(b, "SELECT count(*) AS n FROM nt_certidoes")["n"] == antes
    breve = emitir_certidao(b, protocolo=protocolo, ato_id=ato_id, tipo="BREVE_RELATO")
    a = ato(b, ato_id)
    corpo = _texto_do_odt(o_papel_da_certidao(b, breve))
    assert "CERTIDÃO EM BREVE RELATO" in corpo
    for elemento in (f"Livro {a['livro']}", f"termo n. {a['termo']}",
                     "figura como OUTORGANTE: MARIO EXEMPLO DOS SANTOS", a["selo"]):
        assert elemento in corpo, elemento


def test_o_ato_identificado_so_tem_inteiro_teor_ou_breve_relato(balcao):
    """A forma que o pedido diz é conferida: positiva e negativa são da busca."""
    b = balcao
    ato_id, _protocolo = _lavrar_compra_e_venda(b)
    con = banco_pg.conectar(b["banco"])
    try:
        with pytest.raises(NCE.CertidaoNotasError, match="breve relato"):
            NCE.emitir(con, hoje="2026-10-21", agora="2026-10-21T10:00:00",
                       ato_id=ato_id, tipo="POSITIVA")
    finally:
        con.close()


def test_a_positiva_guarda_a_data_do_banco_no_registro_e_escreve_a_de_papel():
    """A data de papel é do papel: `achados_json` continua com a do banco, que
    é a que a busca compara."""
    assert NCE.data_de_papel("2026-10-20") == "20/10/2026"
    assert NCE.data_de_papel("2026-10-20T10:30:00") == "20/10/2026"
    assert NCE.data_de_papel("20/10/2026") == "20/10/2026"
    assert NCE.data_de_papel(None) == ""


# ===================================== o termo de presença: a ordem


def test_a_ordem_do_termo_de_presenca_segue_e_a_segunda_via_guarda_a_sua(balcao):
    """Duas firmas, dois termos, duas ordens seguidas; a segunda via do mesmo
    termo não gasta número (CN-MA art. 866). Cada termo diz a ordem e o selo
    da sua firma."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 2), ("13.17.2", 2)])
    rid = reconhecer(b, [abrir_cartao(b, n) for n in ("JOANA EXEMPLO DA SILVA",
                                                      "MARIO EXEMPLO DOS SANTOS")],
                     "AUTENTICIDADE")
    partes = _ler(b, "SELECT id, selo FROM nt_reconhecimento_partes "
                     "WHERE reconhecimento_id = %s ORDER BY id", (rid,))

    def termo(parte) -> tuple[str, int]:
        r = _postar(b, f"/notas/reconhecimento/{rid}/termo-comparecimento/{parte['id']}",
                    {}, de=f"/notas/reconhecimento/{rid}")
        assert r.status_code == 200
        ordem = _um(b, "SELECT ordem FROM nt_presencas WHERE origem_chave = %s",
                    (f"{rid}:{parte['id']}",))["ordem"]
        return _texto_do_odt(r.data), ordem

    texto1, ordem1 = termo(partes[0])
    texto2, ordem2 = termo(partes[1])
    de_novo, ordem1_de_novo = termo(partes[0])
    assert ordem2 == ordem1 + 1 and ordem1_de_novo == ordem1
    assert f"ordem n. {ordem1}" in texto1 and f"ordem n. {ordem2}" in texto2
    assert partes[0]["selo"] in texto1 and partes[1]["selo"] in texto2
    assert partes[0]["selo"] not in texto2
    assert _um(b, "SELECT count(*) AS n FROM nt_presencas WHERE reconhecimento_id = %s",
               (rid,))["n"] == 2


class _BancoQueAnota:
    """Um `bd` de mentira que anota a ordem das chamadas."""

    def __init__(self):
        self.chamadas: list[str] = []

    def travar(self, chave):
        self.chamadas.append(f"travar:{chave}")

    def um(self, sql, parametros=()):
        self.chamadas.append("ler")
        return None

    def valor(self, sql, parametros=()):
        self.chamadas.append("ler")
        return 41


def test_a_trava_da_ordem_vem_antes_de_ler_o_maior(monkeypatch):
    """A trava vem ANTES da leitura: dois balcões juntos leriam o mesmo maior e
    gravariam a mesma ordem. Sem a trava, ou com ela depois, o teste cai."""
    falso = _BancoQueAnota()
    monkeypatch.setattr(NL, "banco", lambda con: falso)
    assert NL.ordem_da_presenca(object(), reconhecimento_id=1, parte_id=2) == 42
    assert falso.chamadas[0] == "travar:nt_presencas.ordem"
    assert falso.chamadas.count("travar:nt_presencas.ordem") == 1


# ===================================== a autenticação da internet


def test_a_autenticacao_da_internet_sem_o_endereco_nao_se_lavra_nem_sela(balcao):
    """Sem o endereço em que se conferiu, não há o que a autenticação mencione
    (CN-MA art. 839, § 1º): a recusa vem antes do ato e do selo, e o item pago
    fica no protocolo."""
    b = balcao
    protocolo = abrir_protocolo_pago(b, [("13.18", 1)])
    antes = _um(b, "SELECT coalesce(max(id), 0) AS n FROM nt_autenticacoes")["n"]
    html = _postar(b, "/notas/autenticacao",
                   {"acao": "autenticar", "folhas": "1", "tipo": "INTERNET",
                    "documento_descricao": "certidão de exemplo"}).get_data(as_text=True)
    assert "839" in " ".join(_flashes(html)), _flashes(html)
    assert _um(b, "SELECT coalesce(max(id), 0) AS n FROM nt_autenticacoes")["n"] == antes
    assert _usado(b, protocolo, "13.18") == 0


# ===================================== a pública forma e o sinal público


def test_a_publica_forma_suspensa_nao_tem_papel(balcao):
    """Sem selo a pública forma não foi emitida, e o papel dela não sai — ele
    poria no mundo o ato sem selo (CN-MA art. 130, § 2º)."""
    from conftest import cg_login
    b = balcao
    oficial = b["app"].test_client()
    cg_login(oficial, "oficial", "Senha#12345")
    tela = oficial.get("/notas/publica-forma/configuracao").get_data(as_text=True)
    oficial.post("/notas/publica-forma/configuracao",
                 data={"codigo_tj": "13.18",
                       "csrf_token": re.search(r'name="csrf_token"[^>]*value="([^"]+)"',
                                               tela).group(1)})
    # nenhum protocolo pago e em atendimento: a trava do selo pago não deixa sair
    r = _postar(b, "/notas/publica-forma/emitir",
                {"documento_especie": "Certidão de nascimento",
                 "apresentante": "MARIO EXEMPLO DOS SANTOS",
                 "apresentante_documento": PESSOAS["MARIO EXEMPLO DOS SANTOS"],
                 "transcricao": "TEXTO DO DOCUMENTO DE EXEMPLO, TRANSCRITO NA ÍNTEGRA.",
                 "folhas": "1"}, de="/notas/publica-forma", seguir=False)
    pf_id = int(re.search(r"/notas/publica-forma/(\d+)$", r.headers["Location"]).group(1))
    pf = _um(b, "SELECT situacao, selo FROM nt_publicas_formas WHERE id = %s", (pf_id,))
    assert pf["situacao"] == "SUSPENSO_SELO" and not pf["selo"]
    assert "publica-forma/%d/odt" % pf_id not in _tela(b, f"/notas/publica-forma/{pf_id}")
    papel = b["cliente"].get(f"/notas/publica-forma/{pf_id}/odt?formato=odt")
    assert papel.status_code == 302 and papel.headers["Location"].endswith(
        f"/notas/publica-forma/{pf_id}")


def test_a_etiqueta_do_sinal_publico_e_adequada_e_conta_a_impressao(balcao):
    """A tira do sinal é a do reconhecimento de firma: o nome, quem
    reconheceu, a data, o lugar, o selo com a consulta e os emolumentos (CN-MA
    arts. 87, XVI, 131, 132 e 874); a segunda via se conta."""
    b = balcao
    rid, _ = _reconhecer_sinal(b)
    selo = _um(b, "SELECT selo FROM nt_sinais_reconhecimentos WHERE id = %s",
               (rid,))["selo"]
    r = _postar(b, f"/notas/sinais/reconhecimento/{rid}/etiqueta", {},
                de=f"/notas/sinais/reconhecimento/{rid}")
    html = r.get_data(as_text=True)
    tira = _etiqueta(html)
    assert "SINAL PÚBLICO" in tira.upper()
    _o_papel_de_balcao_e_adequado(tira, html, selo=selo, quem=["ANA EXEMPLO HERDEIRA"])
    assert _um(b, "SELECT etiqueta_impressoes AS n FROM nt_sinais_reconhecimentos "
                  "WHERE id = %s", (rid,))["n"] == 1


# ===================================== uma tira por firma


def test_cada_tira_das_firmas_diz_o_nome_e_o_selo_daquela_firma(balcao):
    """Cada firma é um ato e um selo: a tira de cada uma traz o nome dela e o
    selo dela — como o selo diz em `parteAto` —, e não o da outra."""
    b = balcao
    abrir_protocolo_pago(b, [("13.17.1", 2), ("13.17.2", 2)])
    nomes = ("JOANA EXEMPLO DA SILVA", "MARIO EXEMPLO DOS SANTOS")
    rid = reconhecer(b, [abrir_cartao(b, n) for n in nomes], "SEMELHANCA")
    partes = _ler(b, "SELECT selo FROM nt_reconhecimento_partes "
                     "WHERE reconhecimento_id = %s ORDER BY id", (rid,))
    html = etiqueta_do_reconhecimento(b, rid)
    tiras = html.split('<div class="etiqueta">')[1:]
    assert len(tiras) == 2
    for tira, nome, parte, outro in zip(tiras, nomes, partes, reversed(nomes)):
        assert nome in tira and parte["selo"] in tira and outro not in tira
        assert ESCREVENTE in tira and "Total R$" in tira
