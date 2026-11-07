"""Semente da casa de ensaio: o Registro Civil (`/rcpn`). Ver `layout_casa.py`.

O QUE ELA PÕE
    Os três assentos (nascimento, casamento e óbito) em cada estado que muda as abas da ficha
    (`rc_abas`): sem nada, com averbação, com anotação, com certidão, e os que têm o que esperar
    (termo por digitalizar, paternidade por remeter, registro sem selo, casamento por amarrar).
    E a habilitação de casamento em cada estado do rito (`habilitacao_fases`), do balcão ao casamento
    celebrado. Em volta deles, o que as outras rotas pedem: certidão, modelo, comunicação, pedido da
    Central, e-Protocolo, leitura, retificação e o termo digitalizado.

POR QUAL CAMINHO
    Pela tela, que prova o fluxo e deixa tudo como o balcão deixa. O selo não sai, porque não há
    selador: o escrevente o digita, e é isso que `selo=` faz em cada formulário. Só onde a tela não
    chega entra a função de domínio, e por último `casa.inserir`:
      - a expedição da habilitação e o selo dela (pela tela ela pede o selo ao aparelho e, sem
        aparelho, desfaz o ato);
      - o registro e a averbação sem selo (a tela desfaz o ato quando o selo falha);
      - o que chega da Central pela rede (pedido, certidão eletrônica, protocolo do e-Protocolo) e o
        que a IA devolveria (a leitura dos documentos).

O QUE FICA NO `casa.ids`
    `civil_<ficha>_<estado>`: o número de cada registro semeado. O teste das fichas
    (`test_layout_fichas_civil`) lê daqui, e por isso o nome do estado é o da tabela dele.
"""
from __future__ import annotations

import hashlib
import io
import json
import re
import struct
import zlib
from datetime import date, timedelta
from itertools import count

import layout_ensaio as E
from bd_nativo import banco

#: Rota com número que não tem como abrir aqui: endpoint -> o motivo. Nenhuma: as 39 abrem. As duas
#: que buscam o arquivo na Central (`rcpn_certidao_eletronica_pdf`, `rcpn_eprotocolo_anexo`) respondem,
#: sem credencial, com o aviso e o redirecionamento que o balcão veria, e é isso que a semente exercita.
SEM_SEMENTE: dict[str, str] = {}

CNS = "000000"
CPF_REGISTRADO = "00000000191"
CPF_MAE = "000.000.010-82"
CPF_PAI = "000.000.011-63"
CPF_FALECIDO = "000.000.012-44"
CPF_TESTEMUNHA = "000.000.013-25"
CPF_TESTEMUNHA_2 = "000.000.015-97"

_selos = count(1)
_folhas = count(1)
_folhas_de_certidao = count(60)


# ------------------------------------------------------------------ o que serve a tudo

def _dia(casa, atras: int = 0) -> str:
    return (date.fromisoformat(casa.hoje) - timedelta(days=atras)).isoformat()


def _selo(prefixo: str) -> str:
    """Um selo digitado. O miolo não é o de outra área: `sd_selos.numero` é único na casa toda."""
    return f"{prefixo}{CNS}CVLRKWVNJCRSVO{next(_selos):02d}"


def _folha() -> str:
    return str(99900000 + next(_folhas))


def _folha_de_certidao() -> str:
    return str(99900000 + next(_folhas_de_certidao))


def _png() -> bytes:
    """Uma página branca, a menor que o Pillow abre: o termo digitalizado de ensaio."""
    def pedaco(tipo: bytes, dados: bytes) -> bytes:
        return (struct.pack(">I", len(dados)) + tipo + dados
                + struct.pack(">I", zlib.crc32(tipo + dados) & 0xFFFFFFFF))
    linha = b"\x00" + b"\xff\xff\xff" * 8
    return (b"\x89PNG\r\n\x1a\n" + pedaco(b"IHDR", struct.pack(">IIBBBBB", 8, 8, 8, 2, 0, 0, 0))
            + pedaco(b"IDAT", zlib.compress(linha * 8)) + pedaco(b"IEND", b""))


def _enviar(casa, endereco: str, destino: str, **campos) -> str:
    """Manda o formulário como a tela manda e devolve para onde ela leva.

    Recusa de regra volta com aviso e sem redirecionar para `destino`: aqui ela vira falha, com o
    aviso que o balcão leria.
    """
    c = casa.cliente("ADMIN", "novo")
    r = casa.postar(endereco, _cliente=c, **campos)
    local = r.headers.get("Location", "")
    if r.status_code == 302 and re.search(destino, local):
        return local
    html = c.get(local).get_data(as_text=True) if r.status_code == 302 else r.get_data(as_text=True)
    avisos = " | ".join(texto for _classe, texto in E.ler_pagina(html).flashes) or f"HTTP {r.status_code}"
    raise AssertionError(f"POST {endereco} não levou a {destino} ({r.status_code} {local}): {avisos}")


def _numero_no_fim(endereco: str) -> int:
    return int(re.search(r"/(\d+)(?:[?#].*)?$", endereco).group(1))


def _nome_do_oficial(casa) -> str:
    return casa.um("SELECT full_name FROM users WHERE id=%s", (casa.ids["admin"],))["full_name"]


# ------------------------------------------------------------------ os formulários

def _quali(prefixo: str, nome: str, sexo: str = "F", cpf: str = CPF_MAE, **extra) -> dict:
    """A pessoa com a qualificação inteira, como o balcão a digita."""
    a = "a" if sexo == "F" else "o"
    campos = {f"{prefixo}_nome": nome, f"{prefixo}_sexo": sexo,
              f"{prefixo}_nacionalidade": f"brasileir{a}",
              f"{prefixo}_profissao": "lavradora" if sexo == "F" else "lavrador",
              f"{prefixo}_estado_civil": f"casad{a}",
              f"{prefixo}_documento_tipo": "CPF", f"{prefixo}_documento_numero": cpf,
              f"{prefixo}_naturalidade_cidade": "Cidade Exemplo", f"{prefixo}_naturalidade_uf": "MA",
              f"{prefixo}_data_nascimento": "1996-03-10",
              f"{prefixo}_endereco": "Rua Exemplo, 10", f"{prefixo}_bairro": "Centro",
              f"{prefixo}_cidade": "Cidade Exemplo", f"{prefixo}_uf": "MA"}
    campos.update({f"{prefixo}_{k}": v for k, v in extra.items()})
    return campos


def _form_nascimento(casa, n: int, nome: str = "Ana Exemplo", **trocar) -> dict:
    f = {"pessoa_nome": nome, "pessoa_sexo": "F", "data_fato": _dia(casa, 3), "hora_fato": "08:30",
         "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
         "local_fato_endereco": "Avenida Exemplo, 100, Centro",
         "naturalidade_declarada": "Cidade Exemplo/MA", "cor_raca": "PARDA",
         "ibge_local": "1", "ibge_gemeo": "1", "dnv": f"1000000{n:04d}",
         "pais_casamento_lugar": "Cidade Exemplo/MA",
         "pais_casamento_cartorio": "Ofício Único de Cidade Exemplo",
         "cpf_registrado": CPF_REGISTRADO}
    f |= _quali("filiacao1", "Beatriz Exemplo")
    f |= _quali("filiacao2", "Mario Exemplo", sexo="M", cpf=CPF_PAI, data_nascimento="1990-05-20")
    f |= {"prog1f1_nome": "João Modelo", "prog2f1_nome": "Carla Exemplo",
          "prog1f2_nome": "Mario Exemplo", "prog2f2_nome": "Ana Exemplo"}
    f |= _quali("declarante", "Beatriz Exemplo")
    f.update(trocar)
    return f


def _form_obito(casa, n: int, nome: str = "Carla Exemplo", **trocar) -> dict:
    f = {"pessoa_data_nascimento": "1950-01-02", "data_fato": _dia(casa, 2), "hora_fato": "14:00",
         "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
         "local_fato_endereco": "Avenida Exemplo, 100, Centro",
         "naturalidade_declarada": "Cidade Exemplo/MA", "cor_raca": "PARDA",
         "numero_do": f"2000{n:04d}", "natureza_obito": "1", "local_obito": "1",
         "causa_morte": "natural, por insuficiência cardíaca", "atestante": "Beatriz Exemplo",
         "atestante_documento": "CRM-MA 0000",
         "local_sepultamento": "Cemitério Municipal de Cidade Exemplo",
         "testamento": "SIM, lavrado no Tabelionato de Cidade Exemplo",
         "obito_eleitor": "SIM", "obito_possui_bens": "SIM", "obito_possui_filho": "SIM",
         "obito_desconhecido": "NAO", "obito_conjuge_nome": "João Modelo",
         "obito_conjuge_situacao": "PRE_MORTO",
         "obito_conjuge_cartorio": "Ofício Único de Cidade Exemplo",
         "obito_filhos": "Mario Exemplo, com 50 anos", "obito_herdeiros_menores": "NAO",
         "cpf_registrado": re.sub(r"\D", "", CPF_FALECIDO)}
    f |= _quali("pessoa", nome, estado_civil="viúva", profissao="aposentada",
                cpf=CPF_FALECIDO, data_nascimento="1950-01-02", endereco="Rua Exemplo, 20")
    f |= {"filiacao1_nome": "Ana Exemplo", "filiacao2_nome": "João Modelo"}
    f |= _quali("declarante", "Mario Exemplo", sexo="M", cpf=CPF_PAI)
    f.update(trocar)
    return f


def _form_casamento(casa, **trocar) -> dict:
    """O casamento à vista de habilitação de outra serventia: o selo e o lugar vêm no formulário."""
    f = {"data_fato": _dia(casa, 5), "hora_fato": "10:00",
         "local_fato_nome": "Sede do Ofício Único de Cidade Exemplo",
         "regime_bens": "COMUNHAO_PARCIAL", "habilitacao_serventia": "Ofício de Outra Cidade/MA",
         "habilitacao_selo": f"HABCAS{CNS}ABCDEFGHIJ123456", "proclamas_data": _dia(casa, 40),
         "documentos_apresentados": "certidões de nascimento dos nubentes",
         "juiz_de_paz": "Ana Exemplo"}
    f |= _quali("nubente1", "Mario Exemplo", sexo="M", estado_civil="solteiro",
                nome_pos="Mario Exemplo")
    f |= _quali("nubente2", "Beatriz Exemplo", estado_civil="solteira", cpf=CPF_PAI,
                nome_pos="Beatriz Exemplo")
    f |= {"filiacao1n1_nome": "Ana Exemplo", "filiacao2n1_nome": "João Modelo",
          "filiacao1n2_nome": "Carla Exemplo", "filiacao2n2_nome": "Mario Exemplo"}
    f |= _quali("testemunha", "Carla Exemplo", cpf=CPF_TESTEMUNHA)
    f |= _quali("testemunha2", "João Modelo", sexo="M", cpf=CPF_TESTEMUNHA_2)
    f.update(trocar)
    return f


# ------------------------------------------------------------------ o que o balcão faz no assento

_ROTA = {"NASCIMENTO": "nascimento", "CASAMENTO": "casamento", "OBITO": "obito"}
_SELO_DO_REGISTRO = {"NASCIMENTO": "REGNAS", "CASAMENTO": "REGCAS", "OBITO": "REGOBT"}


def _lavrar(casa, especie: str, campos: dict) -> int:
    selo = _selo(_SELO_DO_REGISTRO[especie])
    local = _enviar(casa, f"/rcpn/novo/{_ROTA[especie]}", r"/rcpn/\d+$", acao="lavrar",
                    especie=especie, selo=selo, folha_seguranca=_folha(), **campos)
    assento_id = _numero_no_fim(local)
    assert casa.um("SELECT id FROM rc_atos WHERE assento_id=%s AND tipo='REGISTRO' AND selo=%s",
                   (assento_id, selo)), f"o registro do assento {assento_id} nasceu sem o selo digitado"
    return assento_id


def _lancar(casa, assento_id: int, tipo: str, prefixo: str, teor: str, **extra) -> int:
    selo = _selo(prefixo)
    _enviar(casa, f"/rcpn/{assento_id}/lancar", rf"/rcpn/{assento_id}$", tipo=tipo, teor=teor,
            selo=selo, **extra)
    ato = casa.um("SELECT id FROM rc_atos WHERE assento_id=%s AND tipo=%s AND selo=%s",
                  (assento_id, tipo, selo))
    assert ato, f"{tipo} do assento {assento_id} não nasceu"
    return int(ato["id"])


def _averbar(casa, assento_id: int) -> int:
    return _lancar(casa, assento_id, "AVERBACAO", "AVESVD",
                   "Averbação de ensaio: consta à margem a alteração do sobrenome por mandado.",
                   natureza_averbacao="reconhecimento_filiacao",
                   fundamento="LRP art. 29, § 1º, alínea d")


def _anotar(casa, assento_id: int) -> int:
    return _lancar(casa, assento_id, "ANOTACAO", "ANOTAC",
                   "Anotação de ensaio: remissão ao assento de casamento, livro B, termo 1.")


def _retificar(casa, assento_id: int) -> int:
    return _lancar(casa, assento_id, "RETIFICACAO", "RETIFI",
                   "Retificação de ensaio: onde se lê Anna, leia-se Ana, por erro de grafia.",
                   fundamento="LRP art. 110, erro de grafia")


def _certidao(casa, assento_id: int) -> int:
    """A certidão do casamento pela ficha, com o selo digitado: só a 1ª via do nascimento e a do óbito
    levam o selo do registro, e essas já vêm da base."""
    local = _enviar(casa, f"/rcpn/{assento_id}/certidao", r"/rcpn/certidoes/\d+$",
                    tipo_certidao="resumo", requerente="Beatriz Exemplo", finalidade="documentação",
                    folha_seguranca=_folha_de_certidao(), selo=_selo("CERTID"))
    return _numero_no_fim(local)


def _digitalizar(casa, assento_id: int) -> None:
    """O termo assinado, escaneado: quem o envia baixa a pendência de 7 dias."""
    c = casa.cliente("ADMIN", "novo")
    r = casa.postar(f"/rcpn/{assento_id}/digitalizacao", _cliente=c,
                    arquivo=(io.BytesIO(_png()), "termo-assinado.png"))
    assert r.status_code == 302 and "termo-digitalizado" in r.headers.get("Location", ""), (
        f"o termo não foi guardado: {r.status_code}")
    assert casa.um("SELECT digi_path FROM rc_assentos WHERE id=%s", (assento_id,))["digi_path"]


def _nascimento_sem_selo(casa) -> int:
    """O registro e a averbação que ninguém selou, como o que um robô lavra: pela função de domínio,
    que lavra e não sela. A tela desfaz o ato quando o selo falha, e por isso não deixa este estado."""
    import rc_assento as RC
    from ri_web import data_por_extenso
    from serventia import dados as dados_serventia
    nome, agora = _nome_do_oficial(casa), casa.db.now()
    mae = {"estado_civil": "casada", "profissao": "lavradora", "nacionalidade": "brasileira",
           "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA",
           "documento_tipo": "CPF", "cidade": "Cidade Exemplo", "uf": "MA"}
    pessoas = [
        {"papel": "REGISTRADO", "nome": "Ana Exemplo", "sexo": "F", "data_nascimento": _dia(casa, 3),
         "naturalidade_cidade": "Cidade Exemplo", "naturalidade_uf": "MA"},
        {"papel": "MAE", "nome": "Beatriz Exemplo", "sexo": "F", "documento_numero": CPF_MAE,
         "data_nascimento": "1996-03-10", **mae},
        {"papel": "PAI", "nome": "Mario Exemplo", "sexo": "M", "documento_numero": CPF_PAI,
         "data_nascimento": "1990-05-20", **{**mae, "estado_civil": "casado",
                                              "profissao": "lavrador", "nacionalidade": "brasileiro"}},
        {"papel": "DECLARANTE", "nome": "Beatriz Exemplo", "sexo": "F",
         "documento_tipo": "CPF", "documento_numero": CPF_MAE},
        {"papel": "AVO_MATERNO", "nome": "João Modelo", "sexo": "M"},
        {"papel": "AVO_MATERNA", "nome": "Carla Exemplo", "sexo": "F"},
        {"papel": "AVO_PATERNO", "nome": "Mario Exemplo", "sexo": "M"},
        {"papel": "AVO_PATERNA", "nome": "Ana Exemplo", "sexo": "F"}]
    with casa.transacao() as con:
        r = RC.lavrar_assento(
            con, especie="NASCIMENTO", nome="Ana Exemplo", sv=dados_serventia(casa.db.get_settings),
            agora=agora, data_extenso=data_por_extenso(date.fromisoformat(casa.hoje)),
            data_fato=_dia(casa, 3), usuario=nome, dados={"sexo": "F"},
            ibge={"local_nascimento": "1", "gemeo": "1", "dnv": "10000009999"},
            termo_dados={"cor_raca": "PARDA", "hora_fato": "08:30",
                         "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
                         "local_fato_endereco": "Avenida Exemplo, 100, Centro",
                         "naturalidade_declarada": "Cidade Exemplo/MA"},
            pessoas=pessoas)
        RC.averbar(con, r["assento_id"], teor="Averbação de ensaio, ainda sem selo: consta à margem a "
                   "alteração do sobrenome por mandado.", agora=agora, usuario=nome)
    return int(r["assento_id"])


# ------------------------------------------------------------------ a habilitação

def _abrir_habilitacao(casa, tipo: str = "CIVIL", estado_civil: str = "SOLTEIRO") -> int:
    local = _enviar(
        casa, "/rcpn/habilitacoes/nova", r"/rcpn/habilitacoes/\d+$", tipo=tipo,
        regime="COMUNHAO_PARCIAL",
        nubente1_nome="Mario Exemplo", nubente1_estado_civil=estado_civil, nubente1_sexo="M",
        nubente1_mae="Ana Exemplo", nubente1_pai="João Modelo", nubente1_documento=CPF_MAE,
        nubente1_endereco="Rua Exemplo, 10, Centro, Cidade Exemplo/MA",
        nubente2_nome="Beatriz Exemplo", nubente2_estado_civil=estado_civil, nubente2_sexo="F",
        nubente2_mae="Carla Exemplo", nubente2_pai="Mario Exemplo", nubente2_documento=CPF_PAI,
        nubente2_endereco="Rua Exemplo, 50, Centro, Cidade Exemplo/MA")
    return _numero_no_fim(local)


def _acao(casa, habilitacao_id: int, acao: str, **campos) -> None:
    ficha = f"/rcpn/habilitacoes/{habilitacao_id}"
    _enviar(casa, ficha, rf"{ficha}$", acao=acao, **campos)


def _situacao(casa, habilitacao_id: int) -> str:
    return casa.um("SELECT situacao FROM hc_habilitacoes WHERE id=%s", (habilitacao_id,))["situacao"]


def _documentos_pela_tela(casa, habilitacao_id: int) -> None:
    for d in casa.ler("SELECT id FROM hc_documentos WHERE habilitacao_id=%s ORDER BY id", (habilitacao_id,)):
        _acao(casa, habilitacao_id, "documento", documento_id=str(d["id"]), apresentado="1")


def _documentos(casa, habilitacao_id: int) -> None:
    """Os documentos do art. 1.525, todos apresentados. Pelo domínio, numa transação só: a tela de
    cada um já foi percorrida em `_documentos_pela_tela`, e são oito por habilitação."""
    import habilitacao as HAB
    nome, agora = _nome_do_oficial(casa), casa.db.now()
    with casa.transacao() as con:
        for d in HAB.o_que_falta(con, habilitacao_id):
            HAB.marcar_documento(con, d["id"], apresentado=True, agora=agora, usuario=nome)


def _edital(casa, habilitacao_id: int) -> None:
    _acao(casa, habilitacao_id, "edital",
          teor="Faço saber que pretendem casar-se Mario Exemplo e Beatriz Exemplo. "
               "Quem souber de impedimento o diga, no prazo da lei.")
    assert _situacao(casa, habilitacao_id) == "EDITAL_PUBLICADO", "o edital não saiu"


def _na_central(casa, habilitacao_id: int) -> None:
    _acao(casa, habilitacao_id, "eproclamas", protocolo=f"LOTE-{habilitacao_id:04d}")
    assert casa.um("SELECT eproclamas_protocolo AS p FROM hc_habilitacoes WHERE id=%s",
                   (habilitacao_id,))["p"], "o protocolo da Central não foi anotado"


def _com_edital(casa, *, central: bool = False) -> int:
    habilitacao_id = _abrir_habilitacao(casa)
    _documentos(casa, habilitacao_id)
    _edital(casa, habilitacao_id)
    if central:
        _na_central(casa, habilitacao_id)
    return habilitacao_id


def _opor(casa, habilitacao_id: int) -> None:
    _acao(casa, habilitacao_id, "oposicao", quem="Carla Exemplo",
          teor="Alega que a noiva já é casada, o que não consta dos documentos.")
    assert _situacao(casa, habilitacao_id) == "COM_OPOSICAO"


def _expedir(casa, habilitacao_id: int, *, hoje: str | None = None, com_selo: bool) -> None:
    """A expedição vai pelo domínio, e o selo, quando há, é o que o escrevente digita onde o aparelho
    não responde."""
    import ato_selado as AS
    import habilitacao as HAB
    nome, agora = _nome_do_oficial(casa), casa.db.now()
    with casa.transacao() as con:
        HAB.habilitar(con, habilitacao_id, agora=agora, hoje=hoje or casa.hoje, usuario=nome)
        if com_selo:
            AS.registrar_selo_obtido_a_mao(
                con, _selo("HABCAS"), tabela="hc_habilitacoes", ato_id=habilitacao_id,
                atribuicao="RCPN", agora=agora, cns=CNS, usuario=nome)
            HAB.espelhar_o_selo_no_livro_d(con, habilitacao_id)
    assert _situacao(casa, habilitacao_id) == "HABILITADO"


def _casar_pela_habilitacao(casa, habilitacao_id: int) -> int:
    """Lavra o casamento a partir da habilitação desta casa: o selo é o da habilitação, e não se digita."""
    campos = _form_casamento(casa)
    for de_fora in ("habilitacao_serventia", "habilitacao_selo", "proclamas_data",
                    "documentos_apresentados"):
        campos.pop(de_fora)
    local = _enviar(casa, "/rcpn/novo/casamento", r"/rcpn/\d+$", acao="lavrar",
                    especie="CASAMENTO", folha_seguranca=_folha(), habilitacao_id=str(habilitacao_id),
                    **campos)
    return _numero_no_fim(local)


# ------------------------------------------------------------------ a semente

_falhas: list[str] = []


def _passo(nome: str, funcao) -> None:
    """Um passo da semente. A falha de um não esconde a dos outros: todas saem juntas no fim."""
    try:
        funcao()
    except Exception as erro:                                   # noqa: BLE001
        _falhas.append(f"{nome}: {type(erro).__name__}: {erro}")


def semear(casa) -> None:
    global _selos, _folhas, _folhas_de_certidao
    _selos, _folhas, _folhas_de_certidao = count(1), count(1), count(60)
    _falhas.clear()
    base_nascimento = casa.um("SELECT id FROM rc_assentos WHERE especie='NASCIMENTO' AND origem='ENSAIO' "
                              "ORDER BY id LIMIT 1")
    base_obito = casa.um("SELECT id FROM rc_assentos WHERE especie='OBITO' AND origem='ENSAIO' "
                         "ORDER BY id LIMIT 1")
    assert base_nascimento and base_obito, "a base não trouxe o nascimento e o óbito de demonstração"
    casa.ids["civil_nascimento_certidao"] = int(base_nascimento["id"])
    casa.ids["civil_obito_certidao"] = int(base_obito["id"])

    for nome, passo in (("nascimentos", _nascimentos), ("óbitos", _obitos), ("casamentos", _casamentos),
                        ("habilitações", _habilitacoes), ("modelo", _modelo),
                        ("comunicações", _comunicacoes), ("retificação", _retificacao),
                        ("pedido da Central", _pedido_da_central), ("e-Protocolo", _eprotocolo),
                        ("leituras", _leituras), ("endereços", _enderecos)):
        _passo(nome, lambda passo=passo: passo(casa))
    assert not _falhas, "a semente do civil não nasceu inteira:\n  " + "\n  ".join(_falhas)


def _nascimentos(casa) -> None:
    ids = casa.ids
    ids["civil_nascimento_sem"] = _lavrar(casa, "NASCIMENTO", _form_nascimento(casa, 1))
    _digitalizar(casa, ids["civil_nascimento_sem"])
    ids["civil_nascimento_averbacao"] = _lavrar(casa, "NASCIMENTO", _form_nascimento(casa, 2))
    _averbar(casa, ids["civil_nascimento_averbacao"])
    # A anotação e a retificação no mesmo assento: cada aba depende só do seu bloco.
    ids["civil_nascimento_anotacao"] = _lavrar(casa, "NASCIMENTO", _form_nascimento(casa, 3))
    _anotar(casa, ids["civil_nascimento_anotacao"])
    _retificar(casa, ids["civil_nascimento_anotacao"])
    # O pai ignorado pede o termo de paternidade, e o indígena chega à FUNAI. O CPF fica de fora
    # de propósito: é o que abre a aba das averbações sem averbação nenhuma.
    campos = _form_nascimento(casa, 5, cor_raca="INDIGENA", cpf_registrado="",
                              paternidade_tipo="ALEGACAO", nao_tem_filiacao2="1",
                              suposto_pai_nome="João Modelo", suposto_pai_profissao="lavrador",
                              suposto_pai_documento="0000000 SSP/MA",
                              suposto_pai_residencia="Povoado Exemplo, zona rural",
                              prog1f2_nome="", prog2f2_nome="")
    campos.update({k: "" for k in campos if k.startswith("filiacao2_")})
    ids["civil_nascimento_pai_ignorado"] = _lavrar(casa, "NASCIMENTO", campos)
    ids["civil_nascimento_sem_selo"] = _nascimento_sem_selo(casa)


def _obitos(casa) -> None:
    ids = casa.ids
    ids["civil_obito_sem"] = _lavrar(casa, "OBITO", _form_obito(casa, 1))
    _digitalizar(casa, ids["civil_obito_sem"])
    ids["civil_obito_averbacao"] = _lavrar(casa, "OBITO", _form_obito(casa, 2))
    _averbar(casa, ids["civil_obito_averbacao"])
    ids["civil_obito_anotacao"] = _lavrar(casa, "OBITO", _form_obito(casa, 3))
    _anotar(casa, ids["civil_obito_anotacao"])


def _casamentos(casa) -> None:
    ids = casa.ids
    ids["civil_casamento_sem"] = _lavrar(casa, "CASAMENTO", _form_casamento(casa))
    _digitalizar(casa, ids["civil_casamento_sem"])
    ids["civil_casamento_averbacao"] = _lavrar(casa, "CASAMENTO", _form_casamento(casa))
    _averbar(casa, ids["civil_casamento_averbacao"])
    ids["civil_casamento_anotacao"] = _lavrar(casa, "CASAMENTO", _form_casamento(casa))
    _anotar(casa, ids["civil_casamento_anotacao"])
    ids["civil_casamento_certidao"] = _lavrar(casa, "CASAMENTO", _form_casamento(casa))
    _certidao(casa, ids["civil_casamento_certidao"])


def _habilitacoes(casa) -> None:
    ids = casa.ids
    # O rito, do balcão ao casamento: cada estado que muda as fases da ficha.
    ids["civil_hab_sem_documentos"] = _abrir_habilitacao(casa)
    h = _abrir_habilitacao(casa)
    _documentos_pela_tela(casa, h)
    ids["civil_hab_documentos_ok"] = h
    h = _abrir_habilitacao(casa, tipo="CONVERSAO")
    _documentos(casa, h)
    ids["civil_hab_conversao_sem_uniao"] = h

    ids["civil_hab_edital_sem_central"] = _com_edital(casa)
    ids["civil_hab_edital_na_central"] = _com_edital(casa, central=True)
    h = _com_edital(casa, central=True)
    ultimo = casa.ler("SELECT id FROM hc_documentos WHERE habilitacao_id=%s ORDER BY id DESC LIMIT 1", (h,))[0]
    _acao(casa, h, "documento", documento_id=str(ultimo["id"]), apresentado="0")
    assert casa.um("SELECT apresentado AS a FROM hc_documentos WHERE id=%s", (ultimo["id"],))["a"] == 0
    ids["civil_hab_edital_falta_papel"] = h
    h = _com_edital(casa)
    _opor(casa, h)
    ids["civil_hab_com_oposicao"] = h

    h = _com_edital(casa, central=True)
    _expedir(casa, h, com_selo=False)
    ids["civil_hab_habilitado_sem_selo"] = h
    h = _com_edital(casa, central=True)
    _expedir(casa, h, com_selo=True)
    ids["civil_hab_habilitado_com_selo"] = h
    h = _com_edital(casa, central=True)
    _expedir(casa, h, hoje=_dia(casa, 120), com_selo=True)
    ids["civil_hab_vencida"] = h

    # O casamento lavrado pela habilitação fica esperando ser amarrado a ela; amarrado, a habilitação
    # se encerra. Dois pares, um em cada ponto.
    h = _com_edital(casa, central=True)
    _expedir(casa, h, com_selo=True)
    ids["civil_hab_casamento_lavrado"] = h
    ids["civil_casamento_falta_amarrar"] = _casar_pela_habilitacao(casa, h)
    h = _com_edital(casa, central=True)
    _expedir(casa, h, com_selo=True)
    ids["civil_casamento_celebrado"] = _casar_pela_habilitacao(casa, h)
    _acao(casa, h, "celebrado", assento_id=str(ids["civil_casamento_celebrado"]))
    assert _situacao(casa, h) == "CELEBRADO", "a celebração não amarrou o casamento"
    ids["civil_hab_celebrado"] = h
    # O aparelho fora do ar na expedição: o casamento sai antes do selo, e a ficha continua cobrando.
    h = _com_edital(casa, central=True)
    _expedir(casa, h, com_selo=False)
    casamento = _casar_pela_habilitacao(casa, h)
    _acao(casa, h, "celebrado", assento_id=str(casamento))
    assert _situacao(casa, h) == "CELEBRADO", "a celebração sem selo não amarrou o casamento"
    ids["civil_hab_celebrado_sem_selo"] = h

    h = _abrir_habilitacao(casa)
    _acao(casa, h, "arquivar", motivo="Os nubentes desistiram do casamento.")
    assert _situacao(casa, h) == "ARQUIVADO", "o processo não se arquivou"
    ids["civil_hab_arquivado_sem_edital"] = h
    h = _com_edital(casa)
    _opor(casa, h)
    _acao(casa, h, "decidir", decisao="ACOLHIDA",
          fundamento="O impedimento procede: consta casamento anterior não dissolvido.")
    assert _situacao(casa, h) == "ARQUIVADO", "o impedimento acolhido não arquivou o processo"
    ids["civil_hab_arquivado_com_edital"] = h


# ------------------------------------------------------------------ o que gira em volta

def _modelo(casa) -> None:
    local = _enviar(casa, "/rcpn/modelos", r"/rcpn/modelos/\d+$", especie="NASCIMENTO",
                    nome="Declaração de nascimento (ensaio)",
                    corpo="Certifico que {nome} é filho de {mae_nome}.")
    casa.ids["civil_modelo"] = _numero_no_fim(local)


def _comunicacoes(casa) -> None:
    _enviar(casa, "/rcpn/comunicacoes/abrir", r"/rcpn/comunicacoes$", competencia=_dia(casa)[:7])
    linhas = casa.ler("SELECT id FROM rc_comunicacoes ORDER BY id")
    assert linhas, "as comunicações do mês não abriram"
    for i, linha in enumerate(linhas):
        casa.ids[f"civil_comunicacao_{i}"] = int(linha["id"])


def _retificacao(casa) -> None:
    local = _enviar(casa, "/rcpn/retificacoes/nova", r"/rcpn/retificacoes/\d+$",
                    instituto="RETIFICACAO", forma="ESCRITO", requerente_nome="Beatriz Exemplo",
                    o_que_se_pede="corrigir o nome da genitora", assento_descricao="Livro A, termo 1")
    casa.ids["civil_retificacao"] = _numero_no_fim(local)


def _pedido_da_central(casa) -> None:
    """O pedido e a certidão eletrônica chegam pela rede, que a casa de ensaio não tem: entram
    como a Central os mandaria, pela linha da tabela."""
    import rc_pedidos as PED
    base = casa.ids["civil_nascimento_certidao"]
    a = casa.um("SELECT nome, matricula, data_fato FROM rc_assentos WHERE id=%s", (base,))
    nome, agora = _nome_do_oficial(casa), casa.db.now()
    teor = {"pedido_certidao_id": 9001, "tipo_registro": "N", "nome_requerente": "Beatriz Exemplo",
            "documento_requerente": CPF_MAE, "data_pedido": casa.hoje, "nome_registrado": a["nome"],
            "data_ato_fato": str(a["data_fato"] or ""), "matricula": a["matricula"],
            "obs_pedido": "Certidão para a matrícula escolar.", "deposito_previo": "R$ 43,76"}
    pedido = casa.inserir(
        "rc_pedidos", modulo="CRC", ambiente=PED.ambiente(), numero_pedido="9001", letra_registro="N",
        especie="NASCIMENTO", assento_id=base,
        casamento_motivo=f"Achado pela matrícula {a['matricula']}.",
        teor=json.dumps(teor, ensure_ascii=False),
        resumo=f"{a['nome']} · NASCIMENTO · pedido por Beatriz Exemplo",
        baixado_em=agora, baixado_por=nome, situacao="PENDENTE")
    casa.ids["civil_pedido"] = pedido
    with casa.transacao() as con:
        corpo = PED.corpo_crc(con, base, cns=CNS)
    bruto = json.dumps(corpo, ensure_ascii=False)
    casa.ids["civil_certidao_eletronica"] = casa.inserir(
        "rc_certidoes_eletronicas", assento_id=base, pedido_id=pedido, ambiente=PED.ambiente(),
        tipo_registro="nascimento", modalidade="eletronica", certidao_id="ENSAIO-0001",
        corpo_enviado=bruto, corpo_hash=hashlib.sha256(bruto.encode("utf-8")).hexdigest(),
        situacao="CRIADA", criada_em=agora, criada_por=nome)


def _eprotocolo(casa) -> None:
    """A notificação e o detalhe chegam da Central, e entram pelas mesmas funções que a rodada usa."""
    import eprotocolo as EP
    ambiente, agora = EP.ambiente_em_uso(casa.db.get_setting), casa.db.now()
    hash_ = "ensaio-eprotocolo-0001"
    registro = {
        "solicitacao": {"plataformaId": "unidade_interligada", "tipo_registro": "nascimento",
                        "cartorio_destino_cns": CNS},
        "registro": {
            "dados_nascimento": {"numero_dnv": "123456789", "local_nascimento": {
                "tipo_local_nascimento": "Hospital", "nome_local_nascimento": "Maternidade Exemplo",
                "endereco": {"logradouro": "Rua Exemplo, 100", "bairro": "Centro",
                             "cidade": "Cidade Exemplo", "uf": "MA"}}},
            "registrado": {"nome": "Ana Exemplo", "data_nascimento": "13-01-2026", "hora_nascimento": "14:25",
                           "sexo": "F", "naturalidade": {"municipio": "Cidade Exemplo", "uf": "MA"},
                           "gemelar": False, "ordem_nascimento": "1"},
            "filiacao": [{"tipo": "Mae", "nome": "Beatriz Exemplo", "cpf": CPF_REGISTRADO,
                          "estado_civil": "Solteira", "naturalidade": "Cidade Exemplo",
                          "ascendentes": [{"nome": "Carla Exemplo"}, {"nome": "João Modelo"}]},
                         {"tipo": "Pai", "nome": "Mario Exemplo"}],
            "declarante": {"tipo_declarante": "mae", "nome": "Beatriz Exemplo", "cpf": CPF_REGISTRADO}}}
    detalhe = {"protocol": "2026.000001", "status": "request_received", "paymentStatus": "paid",
               "serviceType": "Registro de nascimento", "department": "Registro Civil",
               "requestingUserName": "Beatriz Exemplo", "certificateType": "electronic",
               "observations": "Pedido de ensaio.", "hasStructuredFile": True,
               "attachments": [{"id": 7, "name": "dnv", "extension": "pdf"}]}
    with casa.transacao() as con:
        EP.guardar_notificacao(con, ambiente, {"hash": hash_, "status": "request_received",
                                               "createdAt": agora, "requirement_id": 1, "cns": CNS,
                                               "content": {}}, agora=agora)
        protocolo = banco(con).um("SELECT id FROM ep_protocolos WHERE ambiente=%s AND hash=%s",
                                  (ambiente, hash_))
        EP.guardar_detalhe(con, int(protocolo["id"]), detalhe, registro, agora=agora)
    casa.ids["civil_eprotocolo"] = int(protocolo["id"])


def _leituras(casa) -> None:
    """A leitura que deu certo e a que falhou: a IA não responde aqui, e o que ela devolveria entra
    como `concluir` o recebe."""
    import rc_leitura_documentos as LEIT
    nome, agora = _nome_do_oficial(casa), LEIT.agora()
    dnv = {"numero_dnv": "30-12345678-9", "nome_rn": "Ana Exemplo",
           "data_nascimento": date.fromisoformat(_dia(casa, 3)).strftime("%d/%m/%Y"),
           "hora_nascimento": "10:15", "sexo": "Feminino", "raca_cor_rn": "Parda", "peso_gramas": "3100",
           "tipo_gravidez": "Única", "local_ocorrencia": "Hospital",
           "estabelecimento": "Hospital Municipal de Cidade Exemplo", "endereco_ocorrencia": "Rua Exemplo",
           "numero_ocorrencia": "10", "bairro_ocorrencia": "Centro", "municipio_ocorrencia": "CIDADE EXEMPLO",
           "uf_ocorrencia": "MA", "nome_mae": "Beatriz Exemplo", "cartao_sus_mae": "123456789012345",
           "ocupacao_mae": "Lavradora", "nascimento_mae": "10/03/1996", "idade_mae": "30",
           "naturalidade_mae": "Cidade Exemplo-MA", "situacao_conjugal_mae": "Solteira",
           "logradouro_residencia": "Rua Exemplo", "numero_residencia": "S/N", "bairro_residencia": "Centro",
           "municipio_residencia": "CIDADE EXEMPLO", "uf_residencia": "MA"}
    identidade = {"pessoas": [{"tipo_documento": "RG", "nome": "Beatriz Exemplo", "numero_documento": "0123",
                               "orgao_emissor": "SSP/MA", "cpf": CPF_REGISTRADO,
                               "data_nascimento": "10/03/1996", "naturalidade": "CIDADE EXEMPLO - MA",
                               "filiacao_pai": "João Modelo", "filiacao_mae": "Carla Exemplo"}]}
    documentos = [{"arquivo": "documentos.pdf", "n": 1, "attachment_id": None, "tipo": "DNV", "dados": dnv},
                  {"arquivo": "documentos.pdf", "n": 2, "attachment_id": None, "tipo": "IDENTIDADE",
                   "dados": identidade}]
    arquivos = [{"nome": "documentos.pdf", "attachment_id": None, "sha256": None}]
    with casa.transacao() as con:
        lida = LEIT.abrir(con, especie="NASCIMENTO", agora=agora, por=nome)
        LEIT.concluir(con, lida, arquivos=arquivos, lido={
            "paginas": [{"arquivo": "documentos.pdf", "n": 1, "tipo": "DNV"},
                        {"arquivo": "documentos.pdf", "n": 2, "tipo": "IDENTIDADE"}],
            "documentos": documentos, "envios": []})
        falhou = LEIT.abrir(con, especie="OBITO", agora=agora, por=nome)
        LEIT.concluir(con, falhou, arquivos=arquivos, lido=None,
                      erro="A IA não respondeu: a casa de ensaio não tem rede.")
    casa.ids["civil_leitura_lida"], casa.ids["civil_leitura_falhou"] = int(lida), int(falhou)
    # A ÚLTIMA REVISÃO DO RASCUNHO (#371): uma terceira leitura vira rascunho, e a rota que a tela
    # chama ao abrir responde por ele.
    with casa.transacao() as con:
        outra = LEIT.abrir(con, especie="NASCIMENTO", agora=agora, por=nome)
        LEIT.concluir(con, outra, arquivos=arquivos, lido={
            "paginas": [{"arquivo": "documentos.pdf", "n": 1, "tipo": "DNV"}],
            "documentos": documentos[:1], "envios": []})
        rascunho = LEIT.para_rascunho(con, outra, agora=agora, por=nome)
    casa.pagina("revisao_previa_rcpn_ultima", rascunho_id=int(rascunho))


# ------------------------------------------------------------------ os endereços

#: A tela de lavrar de cada espécie só se abre pelo endereço com o nome dela.
ESPECIES_DA_TELA_DE_LAVRAR = (
    "nascimento", "casamento", "casamento-religioso", "obito", "natimorto", "proclamas", "ausencia",
    "interdicao", "tutela", "emancipacao", "uniao-estavel", "opcao-nacionalidade", "outro-livro-e")


def _enderecos(casa) -> None:
    ids = casa.ids
    for chave, valor in sorted(ids.items()):
        if chave.startswith(("civil_nascimento_", "civil_obito_", "civil_casamento_")):
            casa.pagina("rcpn_assento", assento_id=valor)

    # O que cada ficha oferece, uma vez por espécie: as telas que dependem do que o assento é.
    for especie, chave in (("nascimento", "civil_nascimento_averbacao"), ("obito", "civil_obito_averbacao"),
                           ("casamento", "civil_casamento_averbacao")):
        a = ids[chave]
        for endpoint in ("rcpn_averbar", "rcpn_anotar", "rcpn_retificar", "rcpn_checklist",
                         "rcpn_assento_editar", "rcpn_folha", "rcpn_termo", "rcpn_termo_odt",
                         "rcpn_modelos_do_assento", "rcpn_certidao_eletronica_nova",
                         "rcpn_certidao_eletronica_json"):
            casa.pagina(endpoint, assento_id=a)
        # O PDF pede o LibreOffice, que a trava barra: o `.odt` é o mesmo papel.
        casa.pagina("rcpn_folha_papel", {"formato": "odt"}, assento_id=a)
        casa.pagina("rcpn_formulario", chave=especie.upper())
        casa.pagina("rcpn_importar_modelo", especie=especie.upper())
    for especie in ESPECIES_DA_TELA_DE_LAVRAR:
        casa.pagina("rcpn_assento_novo", especie_url=especie)
    casa.pagina("rcpn_assento_novo")
    casa.pagina("rcpn_assento_novo", {"habilitacao_id": ids["civil_hab_habilitado_com_selo"]},
                especie_url="casamento")
    casa.pagina("rcpn_formulario", chave="LIVRO_E")
    termo = casa.um("SELECT numero FROM rc_assentos WHERE id=%s", (ids["civil_nascimento_averbacao"],))
    casa.pagina("rcpn_formulario", {"assento": termo["numero"]}, chave="NASCIMENTO")
    casa.pagina("rcpn_averbacao_modelo", assento_id=ids["civil_nascimento_averbacao"],
                slug="retificacao-erro-material")
    casa.pagina("rcpn_averbacao_modelo", assento_id=ids["civil_obito_averbacao"],
                slug="retificacao-data-registro")
    casa.pagina("rcpn_modelo", modelo_id=ids["civil_modelo"])
    casa.pagina("rcpn_modelo_emitir", assento_id=ids["civil_nascimento_averbacao"],
                modelo_id=ids["civil_modelo"])

    # As telas de um estado só: o indígena, o pai ignorado e o termo escaneado.
    casa.pagina("rcpn_funai_oficio", assento_id=ids["civil_nascimento_pai_ignorado"])
    casa.pagina("rcpn_paternidade_termo", assento_id=ids["civil_nascimento_pai_ignorado"])
    casa.pagina("rcpn_digitalizacao_arquivo", assento_id=ids["civil_nascimento_sem"])
    casa.pagina("rcpn_digitalizacao_miniatura", assento_id=ids["civil_nascimento_sem"])

    # As certidões: a do nascimento e a do óbito vêm da base, a do casamento é daqui.
    for assento_id in (ids["civil_nascimento_certidao"], ids["civil_obito_certidao"],
                       ids["civil_casamento_certidao"]):
        for certidao in casa.ler("SELECT id FROM rc_certidoes WHERE assento_id=%s ORDER BY id", (assento_id,)):
            casa.pagina("rcpn_certidao", certidao_id=certidao["id"])
            casa.pagina("rcpn_certidao_imprimir", {"formato": "odt"}, certidao_id=certidao["id"])
            casa.pagina("rcpn_certidao_odt", {"formato": "odt"}, certidao_id=certidao["id"])

    for chave in sorted(ids):
        if chave.startswith("civil_comunicacao_"):
            casa.pagina("rcpn_comunicacao", comunicacao_id=ids[chave])
    pendencias = casa.ler("SELECT id FROM rc_anotacoes ORDER BY id")
    assert pendencias, "o óbito e o casamento lavrados não abriram anotação a fazer"
    for pendencia in (pendencias[0], pendencias[-1]):
        casa.pagina("rcpn_anotacao_oficio", pendencia_id=pendencia["id"])
    casa.pagina("rcpn_pedido", pedido_id=ids["civil_pedido"])
    casa.pagina("rcpn_certidao_eletronica_json_gravado", eletronica_id=ids["civil_certidao_eletronica"])
    casa.pagina("rcpn_certidao_eletronica_pdf", eletronica_id=ids["civil_certidao_eletronica"])
    casa.pagina("rcpn_eprotocolo_ficha", protocolo_id=ids["civil_eprotocolo"])
    casa.pagina("rcpn_eprotocolo_anexo", protocolo_id=ids["civil_eprotocolo"], anexo_id=7)
    casa.pagina("rcpn_leitura_ficha", leitura_id=ids["civil_leitura_lida"])
    casa.pagina("rcpn_leitura_ficha", leitura_id=ids["civil_leitura_falhou"])
    casa.pagina("rcpn_retificacao", processo_id=ids["civil_retificacao"])

    for chave, habilitacao_id in sorted(ids.items()):
        if chave.startswith("civil_hab_"):
            casa.pagina("rcpn_habilitacao", habilitacao_id=habilitacao_id)
    casa.pagina("rcpn_habilitacao_edital", habilitacao_id=ids["civil_hab_edital_sem_central"])
    casa.pagina("rcpn_proclama", habilitacao_id=ids["civil_hab_edital_sem_central"])
    for chave in ("civil_hab_habilitado_com_selo", "civil_hab_vencida", "civil_hab_celebrado"):
        casa.pagina("rcpn_habilitacao_certidao", habilitacao_id=ids[chave])
