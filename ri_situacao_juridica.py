"""A SITUACAO JURIDICA DO IMOVEL, num clique — consulta interna, e NAO certidao.

O PEDIDO (o oficial, 26/10/2026)
    Juntar numa tela so o que a ficha da matricula espalha: quem e dono hoje,
    o que grava o imovel, de onde veio o dominio, se ha ordem da CNIB sobre as
    partes, se ha titulo prenotado esperando e nota devolutiva sem resposta, e
    quais atos o TEXTO da ficha escreve. **Sem IA nesta primeira versao**: so
    a agregacao do que o sistema ja calcula, cada pedaco pela funcao que ja o
    calcula para a certidao e para a ficha — `ri_onus.onus_vigentes`,
    `ri_dominial.cadeia_dominial`, `ri_schema.consultar_cnib`,
    `ri_cnib.filtrar_pendentes`, `ri_pedidos.etapa`,
    `ri_numeros_do_teor.citados_no_teor`. Uma regra escrita duas vezes
    diverge no primeiro conserto, e aqui a divergencia faria o resumo dizer
    uma coisa e a certidao outra.

NAO E CERTIDAO, E A TELA DIZ ISSO NO ALTO
    A publicidade registral se faz por certidao (Lei 6.015/1973, art. 19), com
    selo, conferencia e assinatura. Este resumo e para o balcao saber onde
    olhar, e nao para sair da casa: a marca `MARCA_NAO_E_CERTIDAO` mora aqui,
    numa frase so, e o teste a procura na tela e na impressao.

O ERRO CARO E O FALSO NEGATIVO DE ONUS
    «Livre» dito sobre imovel gravado e o papel que faz o banco emprestar e o
    comprador pagar. Por isso:

      · sem onus lavrado no sistema, a frase e `FRASE_SEM_ONUS` — «nenhum onus
        lavrado no sistema — confira o teor» —, e nunca «livre» nem «nada
        consta» (ha teste que procura as duas palavras);
      · na ficha do ACERVO o ato mora no TEXTO, e nao em `ri_atos`: cada
        paragrafo do teor que abre com rotulo desta matricula passa pela MESMA
        `ri_onus.classificar`, e o que ela marca aparece como «possivel onus
        escrito no teor — conferir», com a frase. O sistema nao sabe se ele
        esta vigente ou cancelado, e diz isso; se outro paragrafo fala em
        cancelamento e cita aquele rotulo, a tela mostra o paragrafo que cita;
      · ficha sem teor e ficha nao conferida contra o livro dizem isso em cima.

O QUE ESTE MODULO NAO FAZ
    Nao grava, nao numera, nao sela, nao cobra e nao decide. Nao «resolve» a
    cadeia dominial nem a vigencia de nada: mostra o que cada regra da casa
    devolve, de onde veio, e o que ela nao sabe.
"""
from __future__ import annotations

import unicodedata
from datetime import date

import ri_cnib as CNIB
import ri_dominial as RIDOM
import ri_numeros_do_teor as NUMT
import ri_onus as RIONUS
import ri_pedidos as PED
from bd_nativo import banco
from ri_odt import rotulo_ato
from ri_schema import consultar_cnib, matricula_de_acervo

#: A marca que a tela PRECISA mostrar, e que a impressao leva junto.
MARCA_NAO_E_CERTIDAO = ("Não é certidão — consulta interna; a publicidade "
                        "registral se faz por certidão (Lei 6.015/1973, art. 19)")

#: O que se diz quando o sistema nao tem onus lavrado. NUNCA «livre».
FRASE_SEM_ONUS = "Nenhum ônus lavrado no sistema — confira o teor."

#: Quantos caracteres de cada paragrafo do teor a tela mostra.
TRECHO_DO_PARAGRAFO = 600

_PRENOTACAO_ABERTA = ("ABERTO", "DEVOLVIDO")


def _sem_acento(texto: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", str(texto or ""))
                   if unicodedata.category(c) != "Mn").upper()


def _numero(valor) -> str:
    return RIDOM.normalizar_numero_matricula(valor)


def _rotulos_citados(texto: str, meu: str, meu_cnm: str) -> set[tuple[str, int]]:
    """Os rotulos `(tipo, numero)` que o texto cita E que sao desta matricula."""
    achados = set()
    for padrao in (NUMT.ROTULO, NUMT.ROTULO_CNM):
        for m in padrao.finditer(texto or ""):
            alvo = _numero(m.group(3))
            if alvo and alvo in (meu, meu_cnm):
                achados.add((m.group(1).upper(), int(m.group(2))))
    return achados


def _do_teor(m: dict, atos: list[dict]) -> dict:
    """O que o TEXTO da ficha escreve: atos citados, e os possiveis onus e
    transmissoes, cada um com a frase. SO LE."""
    numero, cnm = m["numero"], m.get("cnm")
    paragrafos = NUMT.paragrafos_dos_atos_no_teor(numero, m.get("teor"), cnm)
    meu = _numero(numero)
    meu_cnm = _numero(cnm) or meu
    ja_em_atos = {(str(a["tipo"]).upper(), int(a["numero"])) for a in atos}

    # Quem fala em cancelamento, e de quem.
    citado_em_cancelamento: dict[tuple, list[str]] = {}
    for p in paragrafos:
        if "CANCEL" not in _sem_acento(p["texto"]):
            continue
        for chave in _rotulos_citados(p["texto"], meu, meu_cnm):
            if chave != (p["tipo"], p["numero"]):
                citado_em_cancelamento.setdefault(chave, []).append(p["rotulo"])

    onus, dominio = [], []
    for p in paragrafos:
        chave = (p["tipo"], p["numero"])
        if chave in ja_em_atos:
            continue          # o ato lavrado ja responde por ele, la em cima
        falso_ato = {"tipo": p["tipo"], "numero": p["numero"],
                     "natureza_titulo": "", "teor": p["texto"], "cancelado": 0}
        linha = {"rotulo": rotulo_ato(p["tipo"], p["numero"], numero),
                 "trecho": p["texto"][:TRECHO_DO_PARAGRAFO],
                 "cortado": len(p["texto"]) > TRECHO_DO_PARAGRAFO,
                 "fala_em_cancelamento": "CANCEL" in _sem_acento(p["texto"]),
                 "cancelado_por": citado_em_cancelamento.get(chave, [])}
        if RIONUS.classificar(falso_ato):
            onus.append(linha)
        if RIDOM.classificar_dominio(falso_ato):
            dominio.append(linha)
    return {
        "paragrafos": len(paragrafos),
        "citados": NUMT.citados_no_teor(numero, m.get("teor"), cnm),
        "onus": onus,
        "dominio": dominio,
    }


def _prenotacoes(bd, m: dict) -> list[dict]:
    """As prenotacoes abertas DESTA matricula — pela amarracao e pelo numero
    digitado. Ate 28/08/2026 o campo era texto livre, e prenotacao que so cita
    o numero tambem disputa prioridade sobre o imovel (Lei 6.015, art. 186)."""
    meu = _numero(m["numero"])
    marcas = ",".join(["%s"] * len(_PRENOTACAO_ABERTA))
    linhas = bd.ler(
        f"""SELECT * FROM ri_protocolos
             WHERE situacao IN ({marcas})
               AND (matricula_id = %s
                    OR (matricula_id IS NULL AND matricula_numero IS NOT NULL))
             ORDER BY numero, id""",
        list(_PRENOTACAO_ABERTA) + [int(m["id"])])
    return [dict(p) for p in linhas
            if p["matricula_id"] == m["id"] or _numero(p["matricula_numero"]) == meu]


def montar(con, matricula_id: int, *, hoje: date,
           cnib_base=None, cnib_ordens: int | None = None) -> dict | None:
    """O resumo inteiro, ou None se a matricula nao existe. SO LE."""
    bd = banco(con)
    m = bd.um("SELECT * FROM ri_matriculas WHERE id=%s", (int(matricula_id),))
    if not m:
        return None
    m = dict(m)
    acervo = matricula_de_acervo(m["numero"]) or m.get("tipo_ficha") == "ACERVO"
    numero = m["numero"]

    atos = [dict(a) for a in bd.ler(
        "SELECT * FROM ri_atos WHERE matricula_id=%s ORDER BY numero, tipo, id",
        (int(matricula_id),))]

    def rotulo(a):
        return rotulo_ato(a["tipo"], a["numero"], numero)

    partes = [dict(p) for p in bd.ler(
        "SELECT * FROM ri_partes WHERE matricula_id=%s ORDER BY nome, id",
        (int(matricula_id),))]
    proprietarios = [p for p in partes if p.get("proprietario_ativo")]

    onus = RIONUS.onus_vigentes(atos, rotulo=rotulo)
    dominio = RIDOM.cadeia_dominial(atos, rotulo=rotulo)
    teor = _do_teor(m, atos)

    # A ORIGEM: so as matriculas citadas que EXISTEM no banco viram link.
    origens = []
    for n in RIDOM.sugerir_numeros_origem(m.get("registro_anterior"),
                                          numero_atual=numero):
        achada = bd.um(
            "SELECT id, numero FROM ri_matriculas WHERE numero=%s ORDER BY id LIMIT 1",
            (n,))
        origens.append({"numero": n, "id": achada["id"] if achada else None})

    # A CNIB, pelas mesmas partes e pela mesma funcao da ficha.
    ordens = consultar_cnib(
        con, [p["documento_numero"] for p in partes if p.get("documento_numero")],
        [p["nome"] for p in partes])
    cnib = {
        "ordens": ordens,
        "pendentes": CNIB.filtrar_pendentes(con, matricula_id, ordens),
        "decisoes": CNIB.decisoes_da_matricula(con, matricula_id),
        "base": cnib_base,
        "base_n": cnib_ordens,
    }

    hoje_iso = hoje.isoformat()
    prenotacoes = []
    for p in _prenotacoes(bd, m):
        quals = PED.qualificacoes_de(con, p["id"])
        ultima = quals[-1] if quals else None
        chave = PED.etapa(p, ultima, hoje_iso)
        prenotacoes.append(p | {"etapa": chave,
                                "etapa_rotulo": PED.ROTULO_DA_ETAPA.get(chave, chave)})
    # A NOTA PENDENTE pode estar numa prenotacao que ja nao conta como
    # aberta; quem decide e a NOTA (situacao ABERTA), amarrada a esta
    # matricula pela mesma regra da prenotacao.
    notas = []
    meu = _numero(numero)
    for n in bd.ler(
            """SELECT n.*, p.numero AS protocolo_numero, p.matricula_id,
                      p.matricula_numero, p.situacao AS protocolo_situacao
                 FROM ri_notas_devolutivas n
                 JOIN ri_protocolos p ON p.id = n.protocolo_id
                WHERE n.situacao = 'ABERTA'
                ORDER BY n.data_nota, n.id"""):
        if n["matricula_id"] == m["id"] or (
                n["matricula_id"] is None and _numero(n["matricula_numero"]) == meu):
            notas.append(dict(n))

    avisos = []
    if m.get("encerrada"):
        avisos.append(f"Matrícula ENCERRADA"
                      f"{' em ' + str(m['data_encerramento']) if m.get('data_encerramento') else ''}"
                      f"{' — ' + str(m['motivo_encerramento']) if m.get('motivo_encerramento') else ''}.")
    if acervo:
        avisos.append("Ficha do ACERVO: os atos anteriores ao sistema estão escritos no "
                      "TEOR, e não lavrados um a um. O que esta tela lê do teor é "
                      "leitura de texto — confira na ficha.")
    if not (m.get("teor") or "").strip():
        avisos.append("A ficha não tem teor transcrito: nada do que o livro escreve "
                      "pôde ser lido. Confira a digitalização ou o livro físico.")
    if not m.get("conferido"):
        avisos.append("Ficha ainda não conferida contra o livro físico.")
    if not proprietarios:
        avisos.append("Nenhum proprietário atual cadastrado nas partes desta ficha — "
                      "o domínio pode estar só no teor.")

    return {
        "m": m,
        "acervo": acervo,
        "avisos": avisos,
        "proprietarios": proprietarios,
        "partes_total": len(partes),
        "atos_total": len(atos),
        "atos_cancelados": sum(1 for a in atos if a.get("cancelado")),
        "onus": onus,
        "dominio": dominio,
        "teor": teor,
        "origens": origens,
        "cnib": cnib,
        "prenotacoes": prenotacoes,
        "notas": notas,
        "piso": NUMT.piso_do_proximo(con, matricula_id),
        "marca": MARCA_NAO_E_CERTIDAO,
        "frase_sem_onus": FRASE_SEM_ONUS,
    }
