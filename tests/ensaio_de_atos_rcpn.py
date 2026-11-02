"""Ensaio de atos do Registro Civil: pratica cada ato pelas rotas de verdade e guarda o que sai.

O PEDIDO, do oficial (01/11/2026): «um teste que usasse todos botões e formulários do sistema para
simular todos atos possíveis previstos em lei ou nos códigos de normas […] e fizesse uma análise
crítica apurada sobre o resultado de saída». Ver `docs/ensaio_de_atos/inventario_rcpn.md` e
`docs/ensaio_de_atos/relatorio_rcpn.md`.

O QUE ESTE MÓDULO FAZ
    `praticar(casa, caso)` leva um CASO (um ato e a variante que a lei distingue) do formulário
    de lavrar à certidão, sobre a casa de ensaio e com a trava ligada: lavra pela tela, lança à
    margem o que o caso pede, emite o breve relato e o inteiro teor, e devolve os documentos —
    o termo congelado, a folha do livro, o teor e o papel de cada certidão. Quem os confere é
    `test_ensaio_de_atos_rcpn`.

O SELO É DIGITADO, como na casa de ensaio (`layout_semente_civil`): a trava barra a rede, e com
ela o selador de bancada, que fala TLS numa porta local. O caminho do selador pelo protocolo pago
está em `test_fluxo_rcpn`.

SÓ OS FICTÍCIOS DA CASA: «Exemplo», Cidade Exemplo, CNS 000000, CPF da lista de fictícios.
"""
from __future__ import annotations

import io
import re
import zipfile
from dataclasses import dataclass, field
from html.parser import HTMLParser

import layout_ensaio as E
import layout_semente_civil as S

# Os CPF fictícios válidos da casa (dígito verificador certo, faixa 000.000.0xx).
CPF = {"mae": "000.000.010-82", "pai": "000.000.011-63", "falecido": "000.000.012-44",
       "test1": "000.000.013-25", "test2": "000.000.015-97", "n1": "000.000.047-74",
       "n2": "000.000.050-70", "registrado": "000.000.001-91"}

SLUG = {"NASCIMENTO": "nascimento", "NATIMORTO": "natimorto", "OBITO": "obito",
        "CASAMENTO": "casamento", "EMANCIPACAO": "emancipacao", "INTERDICAO": "interdicao",
        "AUSENCIA": "ausencia", "TUTELA": "tutela", "UNIAO_ESTAVEL": "uniao-estavel",
        "OPCAO_NACIONALIDADE": "opcao-nacionalidade"}

PREFIXO_DO_SELO = {"NASCIMENTO": "REGNAS", "NATIMORTO": "REGOBT", "OBITO": "REGOBT",
                   "CASAMENTO": "REGCAS"}


@dataclass
class Caso:
    """Um ato com a variante que a lei distingue. `campos` é o que o balcão digita."""
    chave: str
    especie: str
    titulo: str
    campos: dict
    margem: list = field(default_factory=list)      # [(tipo, teor, extra)] lançados depois
    gratuita: bool = False                          # a certidão sai gratuita


@dataclass
class Saida:
    caso: Caso
    assento_id: int | None = None
    termo: str = ""
    folha: str = ""
    certidao: str = ""            # o breve relato (teor gravado)
    papel: str = ""               # o papel (ODT) do breve relato
    inteiro_teor: str = ""
    avisos: list = field(default_factory=list)      # recusas da tela, com o recado do balcão


# ------------------------------------------------------------------ o que serve a tudo

_DE_LINHA = frozenset({"strong", "b", "em", "i", "u", "span", "small", "sup", "sub"})


class _SoTexto(HTMLParser):
    """O texto da página, como o balcão lê: sem script e sem estilo, e com as entidades como estão.

    LEITOR DE HTML, E NÃO EXPRESSÃO REGULAR (alerta #296 do CodeQL): `<script.*?</script>` não pega
    `</script >` nem `</SCRIPT>`. A marca de dentro da linha (o nome em negrito) some sem deixar
    espaço; a de bloco vira espaço."""

    def __init__(self):
        super().__init__(convert_charrefs=False)
        self.pedacos: list[str] = []
        self.escondido = 0

    def handle_starttag(self, tag, attrs):
        if tag in ("script", "style"):
            self.escondido += 1
        elif tag not in _DE_LINHA:
            self.pedacos.append(" ")

    def handle_endtag(self, tag):
        if tag in ("script", "style"):
            self.escondido = max(0, self.escondido - 1)
        elif tag not in _DE_LINHA:
            self.pedacos.append(" ")

    def handle_startendtag(self, tag, attrs):
        if tag not in _DE_LINHA:
            self.pedacos.append(" ")

    def handle_data(self, data):
        if not self.escondido:
            self.pedacos.append(data)

    def handle_entityref(self, name):
        if not self.escondido:
            self.pedacos.append(f"&{name};")

    def handle_charref(self, name):
        if not self.escondido:
            self.pedacos.append(f"&#{name};")

    def handle_comment(self, data):
        self.pedacos.append(" ")

    def handle_decl(self, decl):
        self.pedacos.append(" ")


def _texto(html: str) -> str:
    leitor = _SoTexto()
    leitor.feed(html or "")
    leitor.close()
    return re.sub(r"\s+", " ", "".join(leitor.pedacos)).strip()


def _folha_em_branco(casa) -> str:
    """A primeira folha de segurança em branco: a tela só aceita a da remessa recebida."""
    linha = casa.um("SELECT codigo FROM pp_folhas WHERE situacao='EM BRANCO' ORDER BY codigo LIMIT 1")
    assert linha, "acabou o papel de segurança da casa de ensaio"
    return linha["codigo"]


def _postar(casa, endereco: str, **campos):
    """POST como a tela, e o recado do balcão quando ela recusa."""
    c = casa.cliente("ADMIN", "novo")
    r = casa.postar(endereco, _cliente=c, **campos)
    local = r.headers.get("Location", "")
    html = c.get(local).get_data(as_text=True) if r.status_code == 302 else r.get_data(as_text=True)
    avisos = [t for classe, t in E.ler_pagina(html).flashes if classe in ("error", "danger", "warning")]
    # A TRAVA DA CONFERÊNCIA (`rcpn_conferencia.html`): o que bloqueia vem em lista, e não em aviso.
    trava = re.search(r"(?:campo\(s\) que a CRC|problema\(s\) —|dado\(s\) se contradizem).*?<ul>(.*?)</ul>", html, re.S)
    if trava:
        avisos += [f"trava: {_texto(li)}" for li in re.findall(r"<li>(.*?)</li>", trava.group(1), re.S)]
    return r.status_code, local, avisos


def _quali(prefixo: str, nome: str, sexo: str = "F", cpf: str = CPF["mae"], **extra) -> dict:
    return S._quali(prefixo, nome, sexo=sexo, cpf=cpf, **extra)


# ------------------------------------------------------------------ os formulários-base

def form_nascimento(casa, n: int, **trocar) -> dict:
    f = S._form_nascimento(casa, n, nome="ANA EXEMPLO DE SOUZA")
    f["dnv"] = f"3{n:010d}"
    f.update(trocar)
    return f


def form_obito(casa, n: int, **trocar) -> dict:
    f = S._form_obito(casa, n, nome="CARLA EXEMPLO DE SOUZA")
    f["numero_do"] = f"4{n:07d}"
    # O TESTAMENTO É PERGUNTA desde o item 4 do ensaio (02/11/2026); o texto o identifica.
    f |= {"obito_testamento": "SIM", "testamento": "lavrado no Tabelionato de Cidade Exemplo"}
    f.update(trocar)
    return f


def form_casamento(casa, **trocar) -> dict:
    f = S._form_casamento(casa)
    f.update({"nubente1_nome": "MARIO EXEMPLO DOS SANTOS", "nubente1_nome_pos": "MARIO EXEMPLO DOS SANTOS",
              "nubente2_nome": "BEATRIZ EXEMPLO DE SOUZA",
              "nubente2_nome_pos": "BEATRIZ EXEMPLO DE SOUZA DOS SANTOS",
              "nubente1_documento_numero": CPF["n1"], "nubente2_documento_numero": CPF["n2"],
              "nubente1_data_nascimento": "1994-02-11", "nubente2_data_nascimento": "1997-08-30",
              "juiz_de_paz": "PAULO EXEMPLO JUIZ DE PAZ"})
    f.update(trocar)
    return f


def _titulo(sentenca: bool = True, **extra) -> dict:
    t = {"livro_e_titulo": "SENTENCA", "livro_e_titulo_data": "2026-09-15",
         "livro_e_juizo": "Vara Única da Comarca de Cidade Exemplo", "livro_e_juiz": "JOSE EXEMPLO JUIZ",
         "livro_e_processo": "0000001-00.2026.8.10.0000", "livro_e_transito": "2026-10-05",
         "livro_e_registro_nascimento": "Livro A-1, folha 1, termo 1, do Ofício Único de Cidade Exemplo"}
    if not sentenca:
        t.update({"livro_e_titulo": "ESCRITURA", "livro_e_juizo": "", "livro_e_juiz": "",
                  "livro_e_processo": "", "livro_e_transito": "",
                  "livro_e_tabelionato": "Tabelionato de Notas de Cidade Exemplo",
                  "livro_e_escritura_livro": "10", "livro_e_escritura_folha": "20"})
    t.update(extra)
    return t


def form_livro_e(casa, especie: str, **trocar) -> dict:
    nome = "PEDRO EXEMPLO DE SOUZA"
    f = {"nome": nome, "data_fato": S._dia(casa, 10)}
    f |= _quali("pessoa", nome, sexo="M", cpf=CPF["registrado"], estado_civil="solteiro",
                data_nascimento="2009-04-01", profissao="estudante")
    if especie in ("EMANCIPACAO", "TUTELA", "OPCAO_NACIONALIDADE"):
        f |= {"filiacao1_nome": "BEATRIZ EXEMPLO DE SOUZA", "filiacao2_nome": "MARIO EXEMPLO DOS SANTOS"}
    if especie == "TUTELA":
        f |= _quali("tutor", "JOAO EXEMPLO TUTOR", sexo="M", cpf=CPF["test1"])
    if especie in ("INTERDICAO", "AUSENCIA"):
        f |= _quali("curador", "CARLA EXEMPLO CURADORA", cpf=CPF["test1"])
        f |= _quali("requerente", "CARLA EXEMPLO CURADORA", cpf=CPF["test1"])
        f["pessoa_data_nascimento"] = "1960-04-01"
        f["pessoa_profissao"] = "aposentado"
        f["livro_e_limites"] = "curatela restrita aos atos de natureza patrimonial e negocial (Lei 13.146/2015, art. 85)"
        f["livro_e_registro_casamento"] = ""
    if especie == "INTERDICAO":
        f["livro_e_causa"] = "enfermidade que impede a expressão da vontade"
        f["livro_e_internacao"] = "não há internação"
    if especie == "AUSENCIA":
        f["livro_e_ausencia_tempo"] = "dois anos"
    if especie == "UNIAO_ESTAVEL":
        f["nome"] = "MARIO EXEMPLO DOS SANTOS E BEATRIZ EXEMPLO DE SOUZA"
        for k in list(f):
            if k.startswith("pessoa_"):
                f.pop(k)
        f |= _quali("companheiro1", "MARIO EXEMPLO DOS SANTOS", sexo="M", cpf=CPF["n1"],
                    estado_civil="solteiro", data_nascimento="1990-05-20")
        f |= _quali("companheiro2", "BEATRIZ EXEMPLO DE SOUZA", cpf=CPF["n2"], estado_civil="solteira")
        f |= {"filiacao1c1_nome": "ANA EXEMPLO", "filiacao2c1_nome": "JOAO MODELO",
              "filiacao1c2_nome": "CARLA EXEMPLO", "filiacao2c2_nome": "JOSE EXEMPLO",
              "regime_bens": "COMUNHAO_PARCIAL", "livro_e_uniao_inicio": "2018-01-10"}
        f |= _titulo(sentenca=False)
    elif especie == "EMANCIPACAO":
        f |= _titulo(sentenca=False)
    else:
        f |= _titulo()
    if especie == "OPCAO_NACIONALIDADE":
        f["livro_e_juizo"] = "1ª Vara Federal da Seção Judiciária do Maranhão"
        f["pessoa_naturalidade_pais"] = "Portugal"
        f["pessoa_nacionalidade"] = "brasileiro"
    f.update(trocar)
    return f


# ------------------------------------------------------------------ os casos

def casos(casa) -> list[Caso]:
    """Os atos do RCPN, cada um nas variantes que a lei distingue. A ordem é a do balcão."""
    nas = lambda n, **t: form_nascimento(casa, n, **t)        # noqa: E731
    obi = lambda n, **t: form_obito(casa, n, **t)             # noqa: E731
    cas = lambda **t: form_casamento(casa, **t)               # noqa: E731
    sem_pai = {"nao_tem_filiacao2": "1", "paternidade_tipo": "NEGATIVO", **{k: "" for k in nas(0) if k.startswith(("filiacao2_", "prog1f2", "prog2f2"))},
               "pais_casamento_lugar": "", "pais_casamento_cartorio": ""}
    lista = [
        Caso("nasc_padrao", "NASCIMENTO", "Nascimento — pais casados, hospital, declarante a mãe", nas(1)),
        Caso("nasc_so_mae", "NASCIMENTO", "Nascimento — só a mãe (pai não declarado)", nas(2, **sem_pai)),
        Caso("nasc_alegacao_paternidade", "NASCIMENTO",
             "Nascimento — só a mãe, com indicação do suposto pai (Lei 8.560/1992, art. 2º)",
             nas(3, **{**sem_pai, "paternidade_tipo": "ALEGACAO"}, suposto_pai_nome="JOSE EXEMPLO SUPOSTO",
                 suposto_pai_profissao="lavrador", suposto_pai_documento=CPF["test1"],
                 suposto_pai_residencia="Rua Exemplo, 30, Cidade Exemplo/MA")),
        Caso("nasc_gemeo", "NASCIMENTO", "Nascimento — gêmeo (LRP art. 54, 3º, e art. 63)",
             nas(4, ibge_gemeo="2", gemeo_ordem="1")),
        Caso("nasc_domicilio", "NASCIMENTO",
             "Nascimento — parto em domicílio sem assistência médica, com duas testemunhas (LRP art. 54, 9º)",
             nas(5, ibge_local="3", local_fato_nome="Residência", local_fato_endereco="Rua Exemplo, 10, Centro",
                 dnv="", **_quali("testemunha", "CARLA EXEMPLO TESTEMUNHA", cpf=CPF["test1"]),
                 **_quali("testemunha2", "JOAO EXEMPLO TESTEMUNHA", sexo="M", cpf=CPF["test2"]))),
        Caso("nasc_tardio", "NASCIMENTO", "Nascimento — registro tardio de maior (LRP art. 46)",
             nas(6, data_fato="1990-06-15", registro_tardio="1", dnv="",
                 tardio_requerimento="Requerimento autuado sob nº 1/2026",
                 pessoa_nome="ANA EXEMPLO DE SOUZA", filiacao1_data_nascimento="1962-03-10",
                 filiacao2_data_nascimento="1960-05-20", declarante_data_nascimento="1962-03-10",
                 **_quali("testemunha", "CARLA EXEMPLO TESTEMUNHA", cpf=CPF["test1"], data_nascimento="1970-01-01"),
                 **_quali("testemunha2", "JOAO EXEMPLO TESTEMUNHA", sexo="M", cpf=CPF["test2"],
                          data_nascimento="1972-01-01"))),
        Caso("nasc_tardio_testemunha_jovem", "NASCIMENTO",
             "Nascimento tardio — testemunha mais nova que o registrando (CN-MA art. 249)",
             nas(13, data_fato="1990-06-15", registro_tardio="1", dnv="",
                 tardio_requerimento="Requerimento autuado sob nº 3/2026",
                 filiacao1_data_nascimento="1962-03-10", filiacao2_data_nascimento="1960-05-20",
                 declarante_data_nascimento="1962-03-10",
                 **_quali("testemunha", "CARLA EXEMPLO TESTEMUNHA", cpf=CPF["test1"], data_nascimento="1996-03-10"),
                 **_quali("testemunha2", "JOAO EXEMPLO TESTEMUNHA", sexo="M", cpf=CPF["test2"],
                          data_nascimento="1972-01-01"))),
        Caso("obito_tardio_neto", "OBITO", "Óbito tardio — declarado pelo neto, nascido depois do óbito",
             obi(8, data_fato="1985-03-01", pessoa_data_nascimento="1920-01-02",
                 **_quali("declarante", "PEDRO EXEMPLO NETO", sexo="M", cpf=CPF["test2"],
                          data_nascimento="1990-07-07"))),
        Caso("nasc_pais_estrangeiros", "NASCIMENTO", "Nascimento — pai estrangeiro, com passaporte",
             nas(7, filiacao2_nacionalidade="português", filiacao2_naturalidade_pais="Portugal",
                 filiacao2_naturalidade_cidade="Lisboa", filiacao2_naturalidade_uf="",
                 filiacao2_documento_tipo="PASSAPORTE", filiacao2_documento_numero="CB000000")),
        Caso("nasc_naturalidade_fora_do_ibge", "NASCIMENTO",
             "Nascimento — naturalidade com grafia que o cadastro do IBGE não confirma",
             nas(14, naturalidade_declarada="Cidade Exempo/MA")),
        Caso("nasc_declarante_avo", "NASCIMENTO", "Nascimento — declarado pela avó (LRP art. 52, 4º)",
             nas(8, **_quali("declarante", "JOANA EXEMPLO AVO", cpf=CPF["test1"], data_nascimento="1960-01-01"))),
        Caso("natimorto", "NATIMORTO", "Natimorto — Livro C-Auxiliar (LRP art. 53, § 1º)",
             {"data_fato": S._dia(casa, 1), "hora_fato": "03:10", "numero_do": "50000001",
              "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
              "local_fato_endereco": "Avenida Exemplo, 100, Centro", "local_obito": "1", "natureza_obito": "1",
              **_quali("filiacao1", "BEATRIZ EXEMPLO DE SOUZA"),
              **_quali("filiacao2", "MARIO EXEMPLO DOS SANTOS", sexo="M", cpf=CPF["pai"]),
              **_quali("declarante", "MARIO EXEMPLO DOS SANTOS", sexo="M", cpf=CPF["pai"]),
              "pessoa_nome": "", "pessoa_sexo": "M"}),
        Caso("natimorto_com_nome", "NATIMORTO", "Natimorto — com o nome que os pais deram",
             {"data_fato": S._dia(casa, 1), "hora_fato": "03:10", "numero_do": "50000002",
              "local_fato_nome": "Hospital Municipal de Cidade Exemplo",
              "local_fato_endereco": "Avenida Exemplo, 100, Centro", "local_obito": "1", "natureza_obito": "1",
              **_quali("filiacao1", "BEATRIZ EXEMPLO DE SOUZA"),
              **_quali("filiacao2", "MARIO EXEMPLO DOS SANTOS", sexo="M", cpf=CPF["pai"]),
              **_quali("declarante", "MARIO EXEMPLO DOS SANTOS", sexo="M", cpf=CPF["pai"]),
              "pessoa_nome": "LUCAS EXEMPLO DOS SANTOS", "pessoa_sexo": "M",
              "pessoa_naturalidade_cidade": "Cidade Exemplo", "pessoa_naturalidade_uf": "MA"}),
        Caso("obito_padrao", "OBITO", "Óbito — viúva, com bens, filhos e testamento", obi(1)),
        Caso("obito_sem_bens", "OBITO", "Óbito — solteiro, sem bens, sem filhos, sem testamento",
             obi(2, pessoa_nome="JOAO EXEMPLO SOLTEIRO", pessoa_sexo="M", pessoa_nacionalidade="brasileiro", pessoa_estado_civil="solteiro",
                 pessoa_profissao="lavrador", obito_possui_bens="NAO", obito_possui_filho="NAO",
                 obito_filhos="", obito_testamento="NAO", testamento="", obito_conjuge_nome="", obito_conjuge_situacao="",
                 obito_conjuge_cartorio="", obito_eleitor="NAO")),
        Caso("obito_conjuge_vivo", "OBITO", "Óbito — casado, cônjuge sobrevivente, herdeiro menor",
             obi(3, pessoa_nome="JOSE EXEMPLO CASADO", pessoa_sexo="M", pessoa_nacionalidade="brasileiro", pessoa_estado_civil="casado",
                 obito_conjuge_situacao="SOBREVIVENTE", obito_conjuge_nome="BEATRIZ EXEMPLO VIUVA",
                 obito_herdeiros_menores="SIM", obito_filhos="ANA EXEMPLO, com 12 anos")),
        Caso("obito_violento", "OBITO", "Óbito — morte violenta, atestado do IML (LRP art. 80, 8º)",
             obi(4, natureza_obito="2", causa_morte="politraumatismo; acidente de trânsito",
                 atestante="PERITO EXEMPLO DO IML", atestante_documento="CRM-MA 0001", local_obito="4",
                 local_fato_nome="Via pública", local_fato_endereco="Rodovia Exemplo, km 10")),
        Caso("obito_desconhecido", "OBITO", "Óbito — pessoa não identificada (LRP art. 81)",
             obi(5, obito_desconhecido="SIM", pessoa_nome="PESSOA NÃO IDENTIFICADA", pessoa_sexo="M",
                 pessoa_estado_civil="", pessoa_profissao="", pessoa_naturalidade_cidade="",
                 pessoa_naturalidade_uf="", pessoa_endereco="", pessoa_nacionalidade="",
                 pessoa_documento_numero="", pessoa_data_nascimento="", cpf_registrado="",
                 nao_tem_filiacao1="1", nao_tem_filiacao2="1", filiacao1_nome="", filiacao2_nome="",
                 obito_conjuge_nome="", obito_conjuge_situacao="", obito_filhos="", obito_possui_filho="NAO",
                 obito_possui_bens="NAO", obito_testamento="NAO", testamento="", obito_eleitor="NAO")),
        Caso("obito_desconhecido_ignora", "OBITO",
             "Óbito — não identificado, com as marcas em branco (o declarante ignora)",
             obi(9, obito_desconhecido="SIM", pessoa_nome="PESSOA NÃO IDENTIFICADA", pessoa_sexo="M",
                 pessoa_estado_civil="", pessoa_profissao="", pessoa_naturalidade_cidade="",
                 pessoa_naturalidade_uf="", pessoa_endereco="", pessoa_nacionalidade="", naturalidade_declarada="",
                 pessoa_documento_numero="", pessoa_data_nascimento="", cpf_registrado="",
                 nao_tem_filiacao1="1", nao_tem_filiacao2="1", filiacao1_nome="", filiacao2_nome="",
                 obito_conjuge_nome="", obito_conjuge_situacao="", obito_filhos="", obito_possui_filho="",
                 obito_possui_bens="", obito_testamento="", testamento="", obito_eleitor="", obito_herdeiros_menores="")),
        Caso("obito_bebe", "OBITO", "Óbito — bebê de três meses",
             obi(10, pessoa_nome="PEDRO EXEMPLO BEBE", pessoa_sexo="M", pessoa_estado_civil="",
                 pessoa_nacionalidade="brasileiro", pessoa_profissao="", pessoa_data_nascimento=S._dia(casa, 95),
                 obito_conjuge_nome="", obito_conjuge_situacao="", obito_filhos="", obito_possui_filho="NAO",
                 obito_possui_bens="NAO", obito_testamento="NAO", testamento="", obito_eleitor="NAO",
                 pessoa_documento_numero=CPF["registrado"], cpf_registrado=re.sub(r"\D", "", CPF["registrado"]))),
        Caso("obito_crianca", "OBITO", "Óbito — criança de 2 anos",
             obi(6, pessoa_nome="PEDRO EXEMPLO CRIANCA", pessoa_sexo="M", pessoa_nacionalidade="brasileiro", pessoa_estado_civil="",
                 pessoa_profissao="", pessoa_data_nascimento="2024-05-01", obito_conjuge_nome="",
                 obito_conjuge_situacao="", obito_filhos="", obito_possui_filho="NAO", obito_possui_bens="NAO",
                 obito_testamento="", testamento="", obito_eleitor="NAO", pessoa_documento_numero=CPF["registrado"],
                 cpf_registrado=re.sub(r"\D", "", CPF["registrado"]))),
        Caso("cas_parcial", "CASAMENTO", "Casamento — comunhão parcial, sem pacto", cas()),
        Caso("cas_universal_pacto", "CASAMENTO",
             "Casamento — comunhão universal, com pacto antenupcial (LRP art. 70, 7º; CC art. 1.640, par. ún.)",
             cas(regime_bens="COMUNHAO_UNIVERSAL", pacto_data="2026-08-01",
                 pacto_serventia="Tabelionato de Notas de Cidade Exemplo, livro 10, folha 20")),
        Caso("cas_separacao_pacto", "CASAMENTO", "Casamento — separação convencional, com pacto",
             cas(regime_bens="SEPARACAO_TOTAL", pacto_data="2026-08-01",
                 pacto_serventia="Tabelionato de Notas de Cidade Exemplo, livro 10, folha 21")),
        Caso("cas_participacao_pacto", "CASAMENTO", "Casamento — participação final nos aquestos, com pacto",
             cas(regime_bens="PARTICIPACAO_FINAL", pacto_data="2026-08-01",
                 pacto_serventia="Tabelionato de Notas de Cidade Exemplo, livro 10, folha 22")),
        Caso("cas_universal_sem_pacto", "CASAMENTO",
             "Casamento — comunhão universal SEM pacto (deve ser recusado: CC art. 1.640, par. ún.)",
             cas(regime_bens="COMUNHAO_UNIVERSAL")),
        Caso("cas_obrigatoria_70", "CASAMENTO", "Casamento — separação obrigatória, nubente maior de 70 (CC art. 1.641, II)",
             cas(regime_bens="SEPARACAO_OBRIGATORIA", nubente1_data_nascimento="1950-01-10",
                 nubente1_estado_civil="viúvo", nubente1_conjuge_anterior="ANA EXEMPLO FALECIDA",
                 nubente1_dissolucao_data="2020-03-01")),
        Caso("cas_parcial_70_sem_pacto", "CASAMENTO",
             "Casamento — nubente de 76 anos em comunhão parcial, sem pacto (deve ser recusado: CC art. 1.641, II)",
             cas(nubente1_data_nascimento="1950-01-10")),
        Caso("cas_menor_15", "CASAMENTO", "Casamento — nubente de 15 anos (deve ser recusado: CC art. 1.520)",
             cas(nubente2_data_nascimento="2011-06-01", nubente2_idade_no_fato="15")),
        Caso("cas_divorciado", "CASAMENTO", "Casamento — nubente divorciado (LRP art. 70, 3º)",
             cas(nubente2_estado_civil="divorciada", nubente2_conjuge_anterior="JOSE EXEMPLO ANTERIOR",
                 nubente2_dissolucao_data="2022-05-10")),
        Caso("cas_estrangeiro", "CASAMENTO", "Casamento — nubente estrangeiro, com passaporte",
             cas(nubente1_nacionalidade="italiano", nubente1_naturalidade_pais="Itália",
                 nubente1_naturalidade_cidade="Roma", nubente1_naturalidade_uf="",
                 nubente1_documento_tipo="PASSAPORTE", nubente1_documento_numero="YA0000000")),
        Caso("cas_menor_16", "CASAMENTO", "Casamento — nubente de 16 anos, com autorização dos pais (CC arts. 1.517 e 1.537)",
             cas(nubente2_data_nascimento="2010-03-01", nubente2_idade_no_fato="16")),
        Caso("cas_mesmo_sexo", "CASAMENTO", "Casamento — pessoas do mesmo sexo (Res. CNJ 175/2013)",
             cas(nubente1_sexo="F", nubente1_nome="MARIA EXEMPLO DOS SANTOS",
                 nubente1_nome_pos="MARIA EXEMPLO DOS SANTOS", nubente1_profissao="lavradora",
                 nubente1_nacionalidade="brasileira", nubente1_estado_civil="solteira")),
        Caso("cas_sem_mudanca_nome", "CASAMENTO", "Casamento — nenhum dos dois muda o nome",
             cas(nubente2_nome_pos="BEATRIZ EXEMPLO DE SOUZA")),
        Caso("e_emancipacao_escritura", "EMANCIPACAO", "Livro E — emancipação por escritura (LRP art. 90; CC art. 5º, par. ún., I)",
             form_livro_e(casa, "EMANCIPACAO")),
        Caso("e_emancipacao_sentenca", "EMANCIPACAO", "Livro E — emancipação por sentença (tutelado)",
             form_livro_e(casa, "EMANCIPACAO", **_titulo())),
        Caso("e_interdicao", "INTERDICAO", "Livro E — interdição/curatela (LRP art. 92)", form_livro_e(casa, "INTERDICAO")),
        Caso("e_ausencia", "AUSENCIA", "Livro E — ausência (LRP art. 94)", form_livro_e(casa, "AUSENCIA")),
        Caso("e_tutela", "TUTELA", "Livro E — tutela", form_livro_e(casa, "TUTELA")),
        Caso("e_uniao_estavel", "UNIAO_ESTAVEL", "Livro E — união estável por escritura (LRP art. 94-A)",
             form_livro_e(casa, "UNIAO_ESTAVEL")),
        Caso("e_opcao_nacionalidade", "OPCAO_NACIONALIDADE", "Livro E — opção de nacionalidade (LRP art. 32, § 4º)",
             form_livro_e(casa, "OPCAO_NACIONALIDADE")),
    ]
    # À MARGEM: o que mais cai no balcão depois do registro.
    margem = [
        Caso("av_divorcio", "CASAMENTO", "Averbação — divórcio no assento de casamento (LRP art. 29, § 1º, a; CC art. 10, I)",
             cas(), margem=[("AVERBACAO", "Averbo, por mandado do Juízo da Vara Única da Comarca de Cidade "
                             "Exemplo, extraído do processo nº 0000002-00.2026.8.10.0000, que, por sentença de "
                             "10/09/2026, transitada em julgado em 01/10/2026, proferida pelo MM. Juiz JOSE EXEMPLO "
                             "JUIZ, foi decretado o divórcio do casal; a cônjuge voltou a usar o nome de solteira, "
                             "BEATRIZ EXEMPLO DE SOUZA.",
                             {"natureza_averbacao": "outra", "fundamento": "LRP art. 29, § 1º, a; CC art. 10, I"})]),
        Caso("av_paternidade", "NASCIMENTO", "Averbação — reconhecimento de paternidade (LRP art. 29, § 1º, d)",
             nas(9, **sem_pai), margem=[("AVERBACAO", "Averbo, a requerimento do pai, por termo de reconhecimento "
                                         "lavrado nesta serventia em 20/10/2026, com anuência da mãe, que MARIO EXEMPLO "
                                         "DOS SANTOS reconhece como sua filha a registrada, que passa a chamar-se ANA "
                                         "EXEMPLO DOS SANTOS; avós paternos JOAO EXEMPLO DOS SANTOS e MARIA EXEMPLO DOS SANTOS.",
                                         {"natureza_averbacao": "reconhecimento_filiacao",
                                          "fundamento": "LRP art. 29, § 1º, d; Lei 8.560/1992, art. 1º"})]),
        Caso("av_nome", "NASCIMENTO", "Averbação — alteração de prenome, extrajudicial (LRP art. 56)",
             nas(10), margem=[("AVERBACAO", "Averbo, a requerimento da registrada, maior, que o seu prenome passa "
                                "a ser ANNA, permanecendo inalterados os sobrenomes, conforme procedimento "
                                "extrajudicial autuado sob nº 2/2026.",
                                {"natureza_averbacao": "alteracao_nome", "fundamento": "LRP art. 56"})]),
        Caso("an_obito_no_nascimento", "NASCIMENTO", "Anotação — óbito anotado no nascimento (LRP art. 106)",
             nas(11), margem=[("ANOTACAO", "Anoto que a registrada faleceu em 01/10/2026, conforme assento lavrado "
                               "no Livro C-1, folha 2, termo 3, do Ofício Único de Cidade Exemplo.", {})]),
        Caso("ret_erro_grafia", "NASCIMENTO", "Retificação — erro de grafia (LRP art. 110)",
             nas(12), margem=[("RETIFICACAO", "Retifico, de ofício, o nome da mãe: onde se lê BEATRIS, leia-se "
                                "BEATRIZ, por erro de grafia evidente.",
                                {"fundamento": "LRP art. 110, I"})]),
    ]
    gratuita = [Caso("cert_gratuita", "OBITO", "Certidão de óbito gratuita por hipossuficiência (LRP art. 30)",
                     obi(7), gratuita=True)]
    return lista + margem + gratuita


# ------------------------------------------------------------------ a prática

def preparar(casa) -> None:
    """O que a serventia de verdade já tem antes do primeiro balcão e a casa de ensaio não: o
    município no cadastro do IBGE. Sem ele a naturalidade declarada não chega à pessoa
    (`rc_assento._naturalidade_do_titular`) e a certidão diria «ND». Como em `test_fluxo_rcpn`."""
    import ibge_schema as IB
    casa.sql("""INSERT INTO ib_municipios (codigo_ibge, codigo_uf, codigo_mun, uf, nome, nome_norm, origem)
                VALUES (2199999, 21, '99999', 'MA', 'Cidade Exemplo', %s, 'TESTE') ON CONFLICT DO NOTHING""",
             (IB.normalizar_nome("Cidade Exemplo"),))


def _lavrar(casa, caso: Caso, saida: Saida) -> int | None:
    prefixo = PREFIXO_DO_SELO.get(caso.especie, "REGTOR")
    campos = {"acao": "lavrar", "especie": caso.especie, "selo": S._selo(prefixo),
              "folha_seguranca": _folha_em_branco(casa), **caso.campos}
    antes = casa.um("SELECT coalesce(max(id), 0) AS n FROM rc_assentos")["n"]
    status, local, avisos = _postar(casa, f"/rcpn/novo/{SLUG[caso.especie]}", **campos)
    novo = casa.um("SELECT id FROM rc_assentos WHERE id > %s AND situacao='ATIVO' ORDER BY id DESC LIMIT 1",
                   (antes,))
    if not novo:
        saida.avisos.append(f"lavrar recusado ({status}): {' | '.join(avisos) or local}")
        return None
    saida.avisos += [f"lavrar avisou: {a}" for a in avisos]
    return int(novo["id"])


def _lancar(casa, assento_id: int, tipo: str, teor: str, extra: dict, saida: Saida) -> None:
    prefixo = {"AVERBACAO": "AVESVD", "ANOTACAO": "ANOTAC", "RETIFICACAO": "RETIFI"}[tipo]
    status, local, avisos = _postar(casa, f"/rcpn/{assento_id}/lancar", tipo=tipo, teor=teor,
                                    selo=S._selo(prefixo), **extra)
    if not re.search(rf"/rcpn/{assento_id}$", local):
        saida.avisos.append(f"{tipo} recusado ({status}): {' | '.join(avisos) or local}")


def _como_a_tela_manda(casa, tela: str, acao: str) -> dict:
    """O que o navegador mandaria daquele formulário sem ninguém mexer: o texto que a tela já põe
    na caixa (o teor do assento, no inteiro teor) vai junto, como no balcão."""
    html = casa.cliente("ADMIN", "novo").get(tela).get_data(as_text=True)
    form = next(f for f in E.ler_pagina(html).formularios if f["action"] == acao)
    campos = {}
    for nome, valor in E.como_o_navegador_manda(form):
        if nome != "csrf_token":
            campos.setdefault(nome, valor)
    return campos


def _emitir(casa, assento_id: int, tipo: str, saida: Saida, *, gratuita: bool = False) -> int | None:
    campos = _como_a_tela_manda(casa, f"/rcpn/{assento_id}", f"/rcpn/{assento_id}/certidao")
    campos |= {"tipo_certidao": tipo, "requerente": "BEATRIZ EXEMPLO DE SOUZA", "finalidade": "documentação",
              "folha_seguranca": _folha_em_branco(casa),
              "selo": S._selo("CERINT" if tipo == "inteiro_teor" else "CERTID")}
    if tipo == "inteiro_teor":
        campos["modo_inteiro"] = "texto"
    if gratuita:
        campos |= {"ato_gratuito": "1", "gratuidade_codigo": "HIPOSSUFICIENCIA",
                   "motivo_gratuidade": "declaração de pobreza"}
    status, local, avisos = _postar(casa, f"/rcpn/{assento_id}/certidao", **campos)
    achado = re.search(r"/rcpn/certidoes/(\d+)", local)
    if not achado:
        saida.avisos.append(f"certidão {tipo} recusada ({status}): {' | '.join(avisos) or local}")
        return None
    return int(achado.group(1))


def _papel(casa, certidao_id: int) -> str:
    c = casa.cliente("ADMIN", "novo")
    r = c.get(f"/rcpn/certidoes/{certidao_id}/odt?formato=odt")
    if r.status_code != 200:
        return f"[o papel não saiu: HTTP {r.status_code} {r.headers.get('Location', '')}]"
    with zipfile.ZipFile(io.BytesIO(r.get_data())) as z:
        xml = z.read("content.xml").decode("utf-8")
    xml = re.sub(r"<text:(p|h)\b", r"\n<text:\1", xml)
    return re.sub(r"[ \t]+", " ", re.sub(r"<[^>]+>", " ", xml)).strip()


def praticar(casa, caso: Caso) -> Saida:
    saida = Saida(caso)
    assento_id = _lavrar(casa, caso, saida)
    if assento_id is None:
        return saida
    saida.assento_id = assento_id
    for tipo, teor, extra in caso.margem:
        _lancar(casa, assento_id, tipo, teor, extra, saida)
    a = casa.um("SELECT teor FROM rc_assentos WHERE id=%s", (assento_id,))
    saida.termo = _texto(a["teor"] or "")
    c = casa.cliente("ADMIN", "novo")
    r = c.get(f"/rcpn/{assento_id}/folha")
    saida.folha = _texto(r.get_data(as_text=True)) if r.status_code == 200 else f"[HTTP {r.status_code}]"
    cid = _emitir(casa, assento_id, "resumo", saida, gratuita=caso.gratuita)
    if cid:
        saida.certidao = _texto(casa.um("SELECT teor FROM rc_certidoes WHERE id=%s", (cid,))["teor"] or "")
        saida.papel = _papel(casa, cid)
    cid = _emitir(casa, assento_id, "inteiro_teor", saida)
    if cid:
        saida.inteiro_teor = _texto(casa.um("SELECT teor FROM rc_certidoes WHERE id=%s", (cid,))["teor"] or "")
    return saida


class _SoAData:
    """O que `casos` lê da casa para montar os formulários: só a data de hoje."""
    def __init__(self):
        from datetime import date
        self.hoje = date.today().isoformat()


#: As chaves dos casos, para o pytest parametrizar antes de haver casa.
CHAVES: list[str] = [c.chave for c in casos(_SoAData())]
