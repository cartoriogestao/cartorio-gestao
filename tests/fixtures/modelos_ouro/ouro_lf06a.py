"""O OURO DO LF06A — o que os 41 papéis eram ANTES de o texto sair do código.

`LF06A_catalogo.json`, ao lado, foi gravado em 19/10/2026 na árvore do commit
90704fc, ANTES de qualquer linha do LF06A, pelo `gerar()` abaixo: as constantes
`MODELO_*`/`TERMO_*` ainda existiam, e cada texto saiu delas. Sem dado real de
pessoa — os nomes são de exemplo, e o CPF é o de teste.

    textos[chave]   o texto de fábrica (`padrao_de`, que lia a constante)
    previa[chave]   o papel montado pela prévia da casa (`modelos_previa`)
    funcoes[nome]   o que os montadores puros devolvem SEM modelo — é o
                    caminho em que eles caem no padrão

**NÃO SE REGERA.** Depois do LF06A as constantes não existem mais, e `gerar()`
leria a base: o teste passaria a comparar a base com ela mesma. Para conferir o
gerador, rode-o numa cópia do commit 90704fc (`git worktree add`).

`chamadas()` é a mesma lista que o gerador usou; o teste a refaz depois da
mudança e compara saída por saída.
"""
from __future__ import annotations

import datetime
import json
import subprocess
import sys
from pathlib import Path
from unittest import mock

ARQUIVO = Path(__file__).resolve().parent / "LF06A_catalogo.json"

# O dia em que o ouro foi gravado. `rg_certidao_pdf.textos_prontos` sem `dia`
# põe a data de HOJE no título, no corpo, na faixa e no fecho — o ouro saiu com
# «19/10/2026» e o teste ficou vermelho no dia seguinte sem nenhum texto ter
# mudado (LX25). O relógio fica preso neste dia, no gerador e no teste.
DIA_DO_OURO = datetime.date(2026, 10, 19)


class _DiaDoOuro(datetime.date):
    """`date` cujo `today()` é o dia da gravação (o padrão do LF06C)."""

    @classmethod
    def today(cls):
        return cls(DIA_DO_OURO.year, DIA_DO_OURO.month, DIA_DO_OURO.day)


def normal(valor):
    """A forma com que o valor foi gravado (tupla vira lista, chave ordenada)."""
    return json.loads(json.dumps(valor, ensure_ascii=False, sort_keys=True))


def tenta(f):
    try:
        return {"ok": f()}
    except Exception as erro:  # noqa: BLE001 — o erro também é saída
        return {"erro": f"{type(erro).__name__}: {erro}"}


def chamadas() -> dict:
    """Cada montador puro, chamado SEM modelo — o caminho do padrão."""
    import atrib_certidao as AC
    import notas_certidao as NC
    import protesto_certidao as PTC
    import protesto_instrumento as PTI
    import protesto_termo as PTT
    import rc_modelos_do_livro as LIVRO
    import rg_certidao_pdf as CERT
    import rg_teor_rtdpj as TEOR

    f: dict = {}
    for esp in LIVRO.CHAVES:
        f[f"rc_modelos_do_livro.modelo({esp})[texto]"] = (
            lambda e=esp: LIVRO.modelo(e)["texto"])

        def _form(e=esp):
            claros = LIVRO.claros_do_texto(LIVRO.modelo(e)["texto"])
            valores = {c: f"[{c}]" for c in claros}
            r = LIVRO.montar_do_formulario(e, valores)
            return {k: r[k] for k in sorted(r)
                    if isinstance(r[k], (str, list, tuple, int, bool, type(None)))}
        f[f"rc_modelos_do_livro.montar_do_formulario({esp})"] = _form

    for atr in ("RCPJ", "RTD"):
        for tipo in ("AVERBACAO", "REGISTRO"):
            f[f"rg_teor_rtdpj.textos_prontos({atr},{tipo})"] = (lambda a=atr, t=tipo: {
                k: v for k, v in TEOR.textos_prontos(
                    numero_registro=123, lavrante_nome="FULANO DE EXEMPLO",
                    lavrante_funcao="Escrevente", cns="000000",
                    unit_short="OFÍCIO ÚNICO DE EXEMPLO / UF", cidade="Cidade Exemplo",
                    uf="MA", dia=datetime.date(2026, 9, 8), atribuicao=a, tipo_ato=t,
                    natureza_ato="ATA DE ASSEMBLEIA", data_assinatura="2026-09-01").items()
                if isinstance(v, (str, list, tuple, int))})
            f[f"rg_teor_rtdpj.corpo_do_modelo({atr}_TEOR_{tipo})"] = (
                lambda a=atr, t=tipo: TEOR.corpo_do_modelo(f"{a}_TEOR_{t}"))

    def _certidao(a):
        with mock.patch.object(CERT, "date", _DiaDoOuro):
            prontos = CERT.textos_prontos(
                numero=123, lavrante_nome="FULANO DE EXEMPLO",
                lavrante_funcao="Escrevente", atribuicao=a)
        return {k: v for k, v in prontos.items()
                if isinstance(v, (str, list, tuple, int))}

    for atr in ("RCPJ", "RTD"):
        f[f"rg_certidao_pdf.textos_prontos({atr})"] = (lambda a=atr: _certidao(a))
        for chave in (f"{atr}_CERTIDAO_CAPA", f"{atr}_CERTIDAO_FAIXA"):
            f[f"rg_certidao_pdf.corpo_do_modelo({chave})"] = (
                lambda c=chave: CERT.corpo_do_modelo(c))

    f["protesto_termo.montar(edital)"] = lambda: PTT.montar(
        edital_data="2026-09-08", edital_motivo="endereço incerto",
        motivo_protesto="1", tipo_protesto="")
    f["protesto_termo.montar(pessoal)"] = lambda: PTT.montar(
        pessoal_data="2026-09-08", motivo_protesto="1", tipo_protesto="")
    f["protesto_termo.montar(nada)"] = lambda: PTT.montar(
        motivo_protesto="1", tipo_protesto="")

    for copia in (True, False):
        f[f"protesto_instrumento.montar_teor(copia={copia})"] = (lambda c=copia: PTI.montar_teor(
            serventia="SERVENTIA DE EXEMPLO", praca="Cidade Exemplo - UF",
            motivo="falta de pagamento", copia_arquivada=c, intimacao=None,
            descricao="Duplicata mercantil n. 123, de exemplo."))

    achados = [{"numero_protocolo": 10, "livro": "10", "folha": "42",
                "data_protesto": "2026-09-08", "valor": "100,00",
                "apresentante": "EMPRESA DE EXEMPLO", "especie": "DMI",
                "numero_titulo": "123", "data_cancelamento": "2026-09-20"}]
    for tipo, ach in (("NEGATIVA", []), ("POSITIVA", achados), ("CANCELAMENTO", achados)):
        f[f"protesto_certidao.montar_teor({tipo})"] = (lambda t=tipo, a=ach: PTC.montar_teor(
            tipo=t, nome="MARIA DE EXEMPLO", documento="00000000191", achados=a,
            desde="2021-09-08", hoje="2026-09-08"))

    ctx = {"a": {"livro": "15", "folha": "42", "folha_final": "43"},
           "rotulo_tipo": "Procuração",
           "data_do_ato": "8 de setembro de 2026", "requerente": "JOÃO DE EXEMPLO",
           "achados": [{"rotulo_tipo": "Procuração", "natureza": "PÚBLICA",
                        "livro": "15", "folha": "42", "data": "08/09/2026",
                        "qualificacao": "outorgante"}],
           "finalidade": "instruir processo hipotético",
           "livro": "15", "folha": "42", "nome": "MARIA DE EXEMPLO",
           "documento": "000.000.000-00", "teor": "Teor hipotético do ato.",
           "atos": [{"livro": "15", "folha": "42", "data": "08/09/2026",
                     "natureza": "PROCURAÇÃO", "qualificacao": "outorgante"}],
           "anotacoes": [{"tipo": "RETIFICAÇÃO", "data": "09/09/2026",
                          "texto": "anotação hipotética"}],
           "periodo": "em todo o acervo do sistema",
           "hoje": "8 de setembro de 2026"}
    for tipo in ("INTEIRO_TEOR", "POSITIVA", "NEGATIVA"):
        f[f"notas_certidao.montar_teor({tipo})"] = (
            lambda t=tipo: NC.montar_teor(tipo=t, **ctx))

    dados = {"registro": {"numero": 77, "serie": None, "atribuicao": 6, "volume": "5",
                          "natureza": "ATA DE CONSTITUIÇÃO",
                          "teor": "Teor hipotético do registro."},
             "atos": [{"id": 1, "tipo": "REGISTRO", "folha": "42",
                       "data_ato": "2026-09-08", "teor": "Teor hipotético do registro."},
                      {"id": 2, "tipo": "AVERBACAO", "numero_ordem": "1",
                       "teor": "Averbação hipotética."}]}
    for atr in ("RCPJ_RTD", "LIVRO3"):
        f[f"atrib_certidao.montar_teor({atr})"] = (
            lambda a=atr: AC.montar_teor(a, dados))
    dados_td = {**dados, "registro": {**dados["registro"], "serie": "TD_B",
                                      "atribuicao": 4}}
    f["atrib_certidao.montar_teor(RCPJ_RTD,TD)"] = (
        lambda: AC.montar_teor("RCPJ_RTD", dados_td))
    return f


def gerar(raiz: Path) -> None:
    """Grava o ouro. SÓ NA ÁRVORE DE ANTES (commit 90704fc) — ver o cabeçalho."""
    sys.path.insert(0, str(raiz))
    import modelos_da_casa as MOD
    import modelos_previa as PREVIA

    textos = {c["chave"]: MOD.padrao_de(c["chave"]) for c in MOD.CATALOGO}
    previa = {}
    for chave, texto in textos.items():
        doc, erro = PREVIA.renderizar(chave, [texto, "", ""])
        previa[chave] = {"documento": doc, "erro": erro}
    funcoes = {nome: tenta(f) for nome, f in chamadas().items()}
    commit = subprocess.run(["git", "-C", str(raiz), "rev-parse", "--short", "HEAD"],
                            capture_output=True, text=True).stdout.strip()
    ARQUIVO.write_text(json.dumps(
        {"_como": ("Gerado ANTES do LF06A, das constantes MODELO_*/TERMO_* do commit "
                   f"{commit}, pelo script do relatório relatorios/LF06A.md. Não regerar: "
                   "depois da mudança as constantes não existem mais, e regerar a partir "
                   "da base faria o teste comparar a base com ela mesma."),
         "commit": commit, "textos": textos, "previa": previa, "funcoes": funcoes},
        ensure_ascii=False, indent=1, sort_keys=True) + "\n", encoding="utf-8")


def ouro() -> dict:
    return json.loads(ARQUIVO.read_text(encoding="utf-8"))
