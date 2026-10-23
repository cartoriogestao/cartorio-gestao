"""O OURO DO LF06D — o que os papéis das Notas eram ANTES de o texto sair do código.

`LF06D_notas.json`, ao lado, foi gravado em 19/10/2026 na árvore do commit
2c41e90, ANTES de qualquer linha do LF06D, pelo `gerar()` abaixo: as constantes
e as f-strings ainda estavam nos módulos, e cada saída veio delas. Sem dado
real de pessoa — os nomes são «DE EXEMPLO», e o CPF é o de teste.

    funcoes[nome]     o que cada montador devolve com um contexto de teste,
                      SEM `con` — o caminho em que ele cai no padrão. Cada
                      regra (singular × plural, uma face × várias, com e sem
                      selo…) tem pelo menos uma chamada; e os textos que
                      moravam em constante (o fecho da etiqueta, as aberturas
                      e os fechos do teor, o nome das séries…) entram aqui
                      lidos pelo nome antigo
    minutas           as 33 minutas de fábrica de `notas_modelos.MODELOS`,
                      inteiras (o corpo e o que vai com ele)
    rotas[nome]       os dois textos escritos DENTRO de rotas de `notas_web`
                      (o rótulo do selo, nas duas cópias, e o aviso do cartão
                      sem selo), lidos do código-fonte de antes pela árvore
                      sintática — não há como chamá-los sem a rota inteira

**NÃO SE REGERA.** Depois do LF06D as constantes não existem mais, e `gerar()`
leria a base: o teste passaria a comparar a base com ela mesma. Para conferir o
gerador, rode-o numa cópia do commit 2c41e90 (`git worktree add`).

`chamadas()` é a mesma lista que o gerador usou; o teste a refaz depois da
mudança e compara saída por saída.
"""
from __future__ import annotations

import ast
import json
import subprocess
import sys
from pathlib import Path

ARQUIVO = Path(__file__).resolve().parent / "LF06D_notas.json"

# O contexto de teste. Nenhum dado de gente: nomes de exemplo, CPF de teste.
SV = {"unit_name": "SERVENTIA EXTRAJUDICIAL DE EXEMPLO", "ri_cns": "000000",
      "ri_cidade": "Cidade Exemplo", "ri_uf": "UF",
      "serventia_titular": "FULANO DE EXEMPLO", "serventia_titulo": "Tabelião",
      "endereco_completo": "Rua de Exemplo, 1, Centro, Cidade Exemplo-UF"}
DATA = "oito (8) dias do mês de setembro de 2026"

PF = {"nome": "maria de exemplo", "nacionalidade": "Brasileira",
      "estado_civil": "Solteira", "profissao": "Professora",
      "documento": "000.000.000-00", "endereco": "Rua de Exemplo, 1",
      "tipo_pessoa": "F"}
PF_VAZIA = {"nome": "", "tipo_pessoa": "F"}
PJ = {"nome": "Empresa de Exemplo Ltda", "tipo_pessoa": "J",
      "documento": "00.000.000/0001-00", "endereco": "Avenida de Exemplo, 2"}
PJ_VAZIA = {"nome": "EMPRESA SEM DADOS", "tipo_pessoa": "j"}


def _p(base: dict, **mais) -> dict:
    return {**base, **mais}


PARTES = {
    "um_e_um": [_p(PF, qualificacao="Outorgante"),
                _p(PF, nome="JOÃO DE EXEMPLO", qualificacao="OUTORGADO")],
    "varios_e_testemunha": [
        _p(PF, qualificacao="OUTORGANTE"),
        _p(PF, nome="ANA DE EXEMPLO", qualificacao="Outorgante"),
        _p(PF, nome="JOÃO DE EXEMPLO", qualificacao="PROCURADOR"),
        _p(PJ, qualificacao="OUTORGADA"),
        _p(PF, nome="PEDRO DE EXEMPLO", qualificacao="ANUENTE"),
        _p(PF, nome="TESTEMUNHA DE EXEMPLO", testemunha=1),
        _p(PF_VAZIA, testemunha=1)],
    "nenhuma": [],
    "escritura": [_p(PF, qualificacao="VENDEDOR"),
                  _p(PJ, qualificacao="COMPRADOR"),
                  _p(PJ_VAZIA, qualificacao="")],
    "sem_qualificacao": [_p(PF_VAZIA), _p(PF, qualificacao=None)],
}

PODERES = ("com amplos poderes para assinar contrato de compra de imóvel de exemplo",
           "<p>1 - PODERES: vender o veículo de exemplo.</p>",
           "<p>A quem confere os poderes de exemplo;</p>", "", None)


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def chamadas() -> dict:
    """Cada montador das Notas, com o contexto de teste, sem `con`."""
    import modelos_motor_etiqueta as ETQ
    import notas_anotacoes as NA
    import notas_certidao as NC
    import notas_inutilizacao as NI
    import notas_livro as NL
    import notas_schema as NS
    import notas_teor as NT
    import notas_web as NW
    from jinja2.sandbox import SandboxedEnvironment

    f: dict = {}

    # ------------------------------------------------ reconhecimento e autenticação
    nomes = {"nenhum": [], "um": ["maria de exemplo"],
             "dois": ["MARIA DE EXEMPLO", " joão de exemplo "],
             "brancos": ["", "  "], "um_e_branco": ["MARIA DE EXEMPLO", ""]}
    for especie in ("SEMELHANCA", "AUTENTICIDADE", "OUTRA"):
        for rotulo, lista in nomes.items():
            for sinal in (False, True):
                f[f"notas_schema.texto_reconhecimento({especie},{rotulo},{sinal})"] = (
                    lambda e=especie, n=lista, s=sinal: NS.texto_reconhecimento(e, n, s))
    for rotulo, titular in (("nome", "maria de exemplo"), ("vazio", ""),
                            ("nada", None), ("brancos", "   ")):
        f[f"notas_schema.texto_reconhecimento_sinal({rotulo})"] = (
            lambda t=titular: NS.texto_reconhecimento_sinal(t))
    for tipo in ("PADRAO", "INTERNET", "DESCONHECIDO"):
        f[f"notas_schema.texto_autenticacao({tipo})"] = (
            lambda t=tipo: NS.texto_autenticacao(t))
    f["notas_schema.texto_autenticacao()"] = lambda: NS.texto_autenticacao()
    f["notas_schema.TIPOS_AUTENTICACAO"] = lambda: NS.TIPOS_AUTENTICACAO
    f["notas_schema.FECHO_ETIQUETA"] = lambda: NS.FECHO_ETIQUETA

    teor = "RECONHEÇO POR SEMELHANÇA A FIRMA DE MARIA DE EXEMPLO. DOU FÉ."
    etiquetas = {
        "completa": (teor, "Cidade Exemplo", "uf", "2026-09-08"),
        "sem_local": (teor, "", "", "2026-09-08"),
        "sem_data": (teor, "Cidade Exemplo", "UF", ""),
        "sem_nada": (teor, "", "", ""),
        "data_torta": (teor, "Cidade Exemplo", "UF", "2026-13-45"),
        "so_cidade": (teor, "Cidade Exemplo", "", "2026-09-08T10:00:00"),
        "importada": (teor + " EM TEST. DA VERDADE. CIDADE-UF,08/09/2026.",
                      "Cidade Exemplo", "UF", "2026-09-08"),
        "teor_vazio": (None, "Cidade Exemplo", "UF", "2026-09-08"),
        "teor_com_espaco": ("  " + teor + "  ", "Cidade Exemplo", "UF", "2026-09-08"),
    }
    for rotulo, args in etiquetas.items():
        f[f"notas_schema.texto_da_etiqueta({rotulo})"] = (
            lambda a=args: NS.texto_da_etiqueta(*a))
        f[f"modelos_motor_etiqueta.texto_da_etiqueta_motor({rotulo})"] = (
            lambda a=args: ETQ.texto_da_etiqueta_motor(*a))

    # ------------------------------------------------ termos do livro
    reconhecimento = {"documento_descricao": "contrato de exemplo",
                      "selo": "ABC12345", "oficial": "FULANO DE EXEMPLO",
                      "oficial_funcao": "Escrevente"}
    comparecimentos = {
        "completo": (SV, reconhecimento,
                     {"nome": "MARIA DE EXEMPLO", "documento": "00000000191"}),
        "do_cartao": (SV, {**reconhecimento, "documento_descricao": None,
                           "documento_tipo": "procuração particular"},
                      {"nome": "", "nome_cartao": "ANA DE EXEMPLO",
                       "documento_cartao": "00000000191"}),
        "sem_nada": ({}, {}, {}),
        "so_oficial": (SV, {"oficial": "FULANO DE EXEMPLO", "selo": "  "},
                       {"nome": "MARIA DE EXEMPLO"}),
        "so_funcao": (SV, {"oficial_funcao": "Tabelião"},
                      {"nome": "MARIA DE EXEMPLO", "documento": "  "}),
    }
    for rotulo, (sv, rec, parte) in comparecimentos.items():
        f[f"notas_livro.texto_termo_comparecimento({rotulo})"] = (
            lambda s=sv, r=rec, p=parte: NL.texto_termo_comparecimento(
                sv=s, reconhecimento=r, parte=p, data_extenso=DATA))
    for serie in ("ESCRITURA", "PROCURACAO", "TESTAMENTO_CERRADO", "NOVA_SERIE"):
        f[f"notas_livro.texto_termo_abertura({serie})"] = (
            lambda s=serie: NL.texto_termo_abertura(s, "15", 200, SV, DATA))
    f["notas_livro.texto_termo_abertura(folha_inicial)"] = (
        lambda: NL.texto_termo_abertura("ATA", 3, 100, SV, DATA, folha_inicial=201))
    f["notas_livro.texto_termo_abertura(sem_serventia)"] = (
        lambda: NL.texto_termo_abertura("ESCRITURA", "1", 1, {}, DATA))
    encerramentos = {
        "nada_usado": ("ESCRITURA", None, None, None, 1, None),
        "zero": ("PROCURACAO", 0, 1, 1, 1, None),
        "metade": ("ESCRITURA", 150, 1, 40, 1, None),
        "cheio": ("SUBSTABELECIMENTO", 200, 3, 77, 1, None),
        "com_motivo": ("ATA", 120, None, 9, 1, "  encerrado por ordem de exemplo  "),
        "folha_inicial": ("TESTAMENTO", 230, 5, 9, 201, None),
        "serie_nova": ("NOVA_SERIE", 10, 1, 2, 1, None),
    }
    for rotulo, (serie, usada, t1, t2, inicio, motivo) in encerramentos.items():
        f[f"notas_livro.texto_termo_encerramento({rotulo})"] = (
            lambda s=serie, u=usada, a=t1, b=t2, i=inicio, m=motivo:
            NL.texto_termo_encerramento(s, "15", 200, u, a, b, SV, DATA,
                                        folha_inicial=i, motivo=m))
    f["notas_livro.NOME_DA_SERIE"] = lambda: NL.NOME_DA_SERIE

    # ------------------------------------------------ inutilização
    faces = {"uma": ["10v"], "duas": ["181", "181v"],
             "quatro": ["181", "181v", "182", "182v"], "nenhuma": []}
    for rotulo, lista in faces.items():
        for serie in ("ESCRITURA", "NOVA_SERIE"):
            f[f"notas_inutilizacao.dizer({rotulo},{serie})"] = (
                lambda l=lista, s=serie: NI.dizer(l, s, "15", SV, DATA))
        f[f"notas_inutilizacao.dizer({rotulo},motivo)"] = (
            lambda l=lista: NI.dizer(l, "PROCURACAO", 7, {}, DATA,
                                     motivo="  por erro de impressão de exemplo "))
    for serie in ("ESCRITURA", "NOVA_SERIE"):
        f[f"notas_inutilizacao.html_da_face({serie})"] = (
            lambda s=serie: NI.html_da_face("10v", s, "15", SV, DATA, "texto de exemplo"))
    f["notas_inutilizacao.html_da_face(sem_serventia)"] = (
        lambda: NI.html_da_face("2", "ATA", 3, {}, DATA, ""))

    # ------------------------------------------------ anotação à margem
    ato_novo = {"tipo": "REVOGACAO", "data": "2026-09-08", "livro": "15",
                "folha": "42", "folha_final": "43", "termo": "120",
                "selo": "ABC12345"}
    novos = {
        "completo": ato_novo,
        "mesma_folha": {**ato_novo, "folha_final": "42"},
        "sem_folha": {**ato_novo, "folha": None, "folha_final": None},
        "ordem": {**ato_novo, "termo": None, "numero_ordem": "33", "selo": None},
        "sem_livro": {"tipo": "ESCRITURA", "data": "2026-09-08"},
        "tipo_estranho": {"tipo": "XYZ", "data": "ontem"},
        "sem_tipo": {"tipo": None, "data": None},
    }
    for tipo in ("REVOGACAO", "RENUNCIA", "SUBSTABELECIMENTO", "RETIFICACAO",
                 "ADITAMENTO", "CANCELAMENTO", "ORDEM_JUDICIAL", "OUTRA", "XYZ"):
        f[f"notas_anotacoes.texto_padrao({tipo})"] = (
            lambda t=tipo: NA.texto_padrao(t, None, SV))
    for rotulo, novo in novos.items():
        f[f"notas_anotacoes.texto_padrao(ato,{rotulo})"] = (
            lambda n=novo: NA.texto_padrao("REVOGACAO", n, SV))
    externas = {"com_cns": ("1º Tabelionato de Exemplo", " 999999 "),
                "sem_cns": ("1º Tabelionato de Exemplo", ""),
                "so_cns": ("  ", "999999"), "nada": (None, None)}
    for rotulo, (onde, cns) in externas.items():
        f[f"notas_anotacoes.texto_padrao(externa,{rotulo})"] = (
            lambda o=onde, c=cns: NA.texto_padrao(
                "SUBSTABELECIMENTO", None, SV, "2026-09-08", True, o, c))
    f["notas_anotacoes.texto_padrao(externa,ato)"] = (
        lambda: NA.texto_padrao("REVOGACAO", ato_novo, SV, None, True,
                                "1º Tabelionato de Exemplo", "999999"))
    f["notas_anotacoes.texto_padrao(so_data)"] = (
        lambda: NA.texto_padrao("RETIFICACAO", None, SV, "2026-09-08"))
    f["notas_anotacoes.texto_padrao(data_torta)"] = (
        lambda: NA.texto_padrao("RETIFICACAO", None, SV, "ontem."))
    f["notas_anotacoes.texto_padrao(sem_serventia)"] = (
        lambda: NA.texto_padrao("CANCELAMENTO", None, None))
    f["notas_anotacoes.texto_padrao(serventia_sem_nome)"] = (
        lambda: NA.texto_padrao("CANCELAMENTO", ato_novo, {}))

    # ------------------------------------------------ o teor do ato
    for rotulo, parte in (("pf", PF), ("pf_vazia", PF_VAZIA), ("pj", PJ),
                          ("pj_vazia", PJ_VAZIA),
                          ("pf_espacos", _p(PF, nacionalidade="  ", endereco="  ",
                                            documento=" 1 ", tipo_pessoa=None))):
        f[f"notas_teor.qualificar({rotulo})"] = lambda p=parte: NT.qualificar(p)
    tipos = ("PROCURACAO", "ESCRITURA", "SUBSTABELECIMENTO", "REVOGACAO", "ATA",
             "TESTAMENTO", "RENUNCIA", "PROCURACAO_PREVIDENCIARIA")
    for i, tipo in enumerate(tipos):
        for j, (rotulo, partes) in enumerate(PARTES.items()):
            poderes = PODERES[(i + j) % len(PODERES)]
            f[f"notas_teor.montar({tipo},{rotulo})"] = (
                lambda t=tipo, p=partes, d=poderes: NT.montar(
                    t, p, d, DATA, "Cidade Exemplo", "MA",
                    lavrado_nome="FULANO DE EXEMPLO", lavrado_titulo="Tabelião"))
    for k, poderes in enumerate(PODERES):
        f[f"notas_teor.montar(PROCURACAO,poderes{k})"] = (
            lambda d=poderes: NT.montar("PROCURACAO", PARTES["um_e_um"], d, DATA,
                                        "Cidade Exemplo", "ma"))
    f["notas_teor.montar(ESCRITURA,objeto)"] = (
        lambda: NT.montar("ESCRITURA", PARTES["escritura"], None, DATA, "Cidade Exemplo",
                          "XX", objeto="o imóvel de exemplo"))
    f["notas_teor.montar(ESCRITURA,sem_uf)"] = (
        lambda: NT.montar("ESCRITURA", PARTES["escritura"], "", DATA))
    f["notas_teor.montar(PROCURACAO,so_procurador)"] = (
        lambda: NT.montar("PROCURACAO", [_p(PF, qualificacao="PROCURADOR")],
                          PODERES[0], DATA, "Cidade Exemplo", "PI"))
    for rotulo, partes in PARTES.items():
        f[f"notas_teor.texto_dos_assinantes({rotulo})"] = (
            lambda p=partes: NT.texto_dos_assinantes(p))
        f[f"notas_teor.bloco_de_assinaturas({rotulo})"] = (
            lambda p=partes: NT.bloco_de_assinaturas(p))
        f[f"notas_teor.bloco_de_assinaturas({rotulo},lavrado)"] = (
            lambda p=partes: NT.bloco_de_assinaturas(
                p, lavrado_nome=" FULANO DE EXEMPLO ", lavrado_titulo="Tabelião"))
        f[f"notas_teor.bloco_de_assinaturas({rotulo},lavrado_sem_titulo)"] = (
            lambda p=partes: NT.bloco_de_assinaturas(p, lavrado_nome="FULANO DE EXEMPLO"))
        f[f"notas_teor.contexto_jinja_partes({rotulo})"] = (
            lambda p=partes: NT.contexto_jinja_partes(p))
    f["notas_teor.ABERTURAS"] = lambda: NT.ABERTURAS
    f["notas_teor.FECHOS"] = lambda: NT.FECHOS
    f["notas_teor.UF_EXTENSO"] = lambda: NT.UF_EXTENSO

    # ------------------------------------------------ traslado e certidão
    instrumentos = {
        "escritura_com_modelo": ({"tipo": "ESCRITURA", "natureza": "Doação"},
                                 "Escritura pública de doação de exemplo"),
        "escritura_natureza": ({"tipo": "escritura", "natureza": " Compra e Venda "}, None),
        "escritura_nada": ({"tipo": "ESCRITURA"}, "  "),
        "ata_com_modelo": ({"tipo": "ATA_USUCAPIAO"}, "Ata notarial de exemplo"),
        "ata": ({"tipo": "ATA"}, None),
        "procuracao": ({"tipo": "PROCURACAO", "natureza": "Venda"}, "Ignorado"),
        "estranho": ({"tipo": "XYZ"}, None),
        "vazio": ({}, None),
    }
    for rotulo, (ato, nome) in instrumentos.items():
        f[f"notas_web.titulo_do_instrumento({rotulo})"] = (
            lambda a=ato, n=nome: NW.titulo_do_instrumento(a, nome_modelo=n))
    f["notas_web.MODELO_TRASLADO_CABECALHO"] = lambda: NW.MODELO_TRASLADO_CABECALHO
    cabecalhos = {"termo": {"livro": "15", "termo": "120", "numero_ordem": "3"},
                  "ordem": {"livro": "15", "termo": None, "numero_ordem": "3"},
                  "nada": {"livro": None}}
    for rotulo, a in cabecalhos.items():
        f[f"notas_web.MODELO_TRASLADO_CABECALHO(render,{rotulo})"] = (
            lambda a=a: SandboxedEnvironment(autoescape=False).from_string(
                NW.MODELO_TRASLADO_CABECALHO).render(a=a))
    f["notas_certidao.NOME_DO_TIPO"] = lambda: NC.NOME_DO_TIPO
    for rotulo, (de, ate) in {"periodo": ("2010-01-01", "2026-10-15"),
                              "desde": ("2010-01-01", ""), "ate": ("", "2026-10-15T09:00"),
                              "tudo": ("", ""), "nada": (None, None),
                              "torto": ("2026-01", " x ")}.items():
        f[f"notas_certidao.frase_do_periodo({rotulo})"] = (
            lambda d=de, a=ate: NC.frase_do_periodo(d, a))
    return f


def minutas() -> list:
    """As minutas de fábrica, inteiras, na ordem do código."""
    import notas_modelos as NM
    return NM.MODELOS


def _rotas_do_codigo(raiz: Path) -> dict:
    """Os textos que moram DENTRO de rotas de `notas_web`, lidos da árvore sintática."""
    arvore = ast.parse((raiz / "notas_web.py").read_text(encoding="utf-8"))
    rotulos, sem_selo = [], []
    for no in ast.walk(arvore):
        if isinstance(no, ast.Dict) and any(
                isinstance(k, ast.Constant) and k.value == "ESCRITURA" for k in no.keys) \
                and any(isinstance(v, ast.Constant) and str(v.value).startswith("SELO D")
                        for v in no.values):
            rotulos.append({k.value: v.value for k, v in zip(no.keys, no.values)})
        if isinstance(no, ast.Constant) and isinstance(no.value, str) \
                and "SEM SELO DE ABERTURA" in no.value:
            sem_selo.append(no.value)
    # o padrão do `.get(tipo, «SELO DO ATO»)` que vem depois de cada dicionário
    padroes = sorted({n.args[1].value for n in ast.walk(arvore)
                      if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
                      and n.func.attr == "get" and isinstance(n.func.value, ast.Dict)
                      and len(n.args) == 2 and isinstance(n.args[1], ast.Constant)})
    return {"rotulo_do_selo": rotulos, "rotulo_do_selo_sem_tipo": padroes,
            "cartao_sem_selo_de_abertura": sem_selo}


def gerar(raiz: Path) -> None:
    """Grava o ouro. SÓ NA ÁRVORE DE ANTES (commit 2c41e90) — ver o cabeçalho."""
    mudou = subprocess.run(
        ["git", "-C", str(raiz), "status", "--porcelain", "--untracked-files=no"],
        capture_output=True, text=True).stdout.strip()
    if mudou:
        raise SystemExit(f"A árvore não está limpa — o ouro tem de ser o de antes:\n{mudou}")
    sys.path.insert(0, str(raiz))
    funcoes = {nome: normal(tenta(f)) for nome, f in chamadas().items()}
    commit = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    ARQUIVO.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06D, dos montadores e constantes do commit "
                   f"{commit}, pelo gerador ouro_lf06d.py (relatório "
                   "relatorios/LF06D.md). Não regerar: depois da mudança os textos "
                   "moram na base, e regerar faria o teste comparar a base com ela "
                   "mesma."),
         "commit": commit, "funcoes": funcoes, "minutas": normal(minutas()),
         "rotas": _rotas_do_codigo(raiz)},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ouro() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))


if __name__ == "__main__":
    gerar(Path(sys.argv[1]).resolve())
