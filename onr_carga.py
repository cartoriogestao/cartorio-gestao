# -*- coding: utf-8 -*-
"""A CARGA COMPLETA para o Next Cloud SAS do ONR — modalidade (b).

    «vamos seguir a modalidade b. processse, escreva, me ensine a usar.
     e como fica o indicador real?»               — o oficial, 04/09/2026

SÃO TRÊS COISAS, E O NEXT CLOUD SAS LEVA DUAS — a resposta à pergunta dele
    Medido em 04/09/2026 nos **seis** documentos do ONR que estão na casa
    (o manual de integração 3.7 e os cinco que ele cita): a expressão
    «indicador real» aparece **zero vezes em todos**.

    | o quê | por onde vai | quem monta |
    |---|---|---|
    | **Indicador Pessoal** (Livro 5) | Firestore, pelo programa **IPS** | este módulo |
    | **Imagens do Livro 2** | Bucket, pelo programa **CSL2** | o disco, já pronto |
    | **Indicador Real** (Livro 2) | **a API — `POST /v1/indicador/real`** | `ri_onr_central` |

    **O indicador real NÃO passa pelo Next Cloud SAS, e não é esquecimento
    do ONR: é outra coisa.** O Next Cloud SAS é *armazenamento* — um balde de
    arquivos e um banco de pesquisa, que o ONR lê. O indicador real é *envio*,
    ato por ato, para o índice nacional, e tem caminho, situação e fila
    próprios, construídos em 03/09/2026.

    Aderir à modalidade (b) **não desliga o indicador real**, e é por isso que
    a tela diz isso com todas as letras: quem lesse «Next Cloud SAS ligado»
    concluiria que o Registro de Imóveis inteiro está integrado, e o índice
    real pararia sem ninguém ver.

A DIFERENÇA ENTRE ESTE MÓDULO E `ri_onr`, que já existia
    `ri_onr` gera o arquivo **de um período** — o mês, para envio manual. O
    Next Cloud SAS pede o contrário: **a carga COMPLETA**, «desde o dia 1º de
    janeiro de 1976 (...) até a data atual», e depois o próprio programa IPS
    faz a incremental diária sozinho.

    **O FORMATO É O MESMO, E POR ISSO NÃO SE ESCREVE DUAS VEZES.** Este módulo
    monta a lista e chama `ri_onr.gerar_indicador_pessoal`. Uma segunda
    montagem «parecida» divergiria no primeiro conserto — e aqui as duas
    escreveriam o mesmo arquivo com conteúdo diferente. Há teste que exige a
    chamada.

O QUE O ONR RECUSA, E ESTÁ MEDIDO CONTRA A PRODUÇÃO
    O manual é explícito, e em maiúsculas: **«Não serão aceitas base de dados
    ou de imagens parciais ou incompletas.»**

    | | medido em 04/09/2026 |
    |---|---|
    | matrículas sem imagem nenhuma no disco | **74 de 1.701** |
    | pessoas sem CPF/CNPJ no Indicador Pessoal | **2.819 de 3.992** |
    | a base alcança 1976? | **alcança** — matrícula de 1951, ato de 1948 |
    | imagens no padrão do ONR | **10.227 de 10.227** |

    **A conferência vem antes de gerar, e não recusa.** Quem decide se manda a
    base como está — com a declaração de base incompleta assinada — ou se
    digitaliza antes é o oficial. O que o sistema não pode é deixá-lo mandar
    sem saber o tamanho do que falta.

O DOCUMENTO ZERADO É PRECEDENTE DESTA CASA, E ELE CONTRARIA O MODELO
    O modelo do ONR diz, em comentário dentro do próprio XML:

        <CNPJCPF>00000000000</CNPJCPF>
        <!-- CAMPO OBRIGATORIO - DOCUMENTO (CPF ou CNPJ)
             - A INFORMACAO DEVE SER MAIOR QUE ZERO -->

    E os arquivos que **esta casa mandou** dizem o contrário. Medido nos 19
    XML de `arquivos\\eoficio\\ONR`, 10.781 `<INDIVIDUO>`:

        7.812  com onze zeros
        2.259  CPF
          604  CNPJ
          106  com catorze zeros

    **Setenta e três por cento do que esta casa mandou tem o documento
    zerado.** A regra do oficial de 24/08/2026 decide o empate — «na dúvida,
    faça como o E-Ofício fazia» —, e por isso `ri_onr.DOC_DESCONHECIDO` fica.
    **Mas a divergência não passa calada**: ela aparece na conferência com os
    dois números, porque quem assina precisa saber que está mandando o que o
    comentário do modelo desaconselha.

    > **E O COMENTÁRIO DE `ri_onr` DIZIA 7.772 DE 10.685.** Medido agora:
    > **7.812 de 10.781**. A conclusão não muda e o número, sim — e número
    > escrito em comentário é número que ninguém confere. Corrigido lá.

ESTE MÓDULO NÃO TRANSMITE NADA
    Quem sobe são os programas **IPS** e **CSL2**, que o ONR instala no
    servidor da serventia. Escrever direto no Bucket e no Firestore daria dois
    caminhos gravando o mesmo fato — e o segundo divergiria do primeiro no dia
    em que o ONR mudasse o formato. **Aqui se produz o arquivo e se confere a
    pasta; a subida é dos programas deles.**
"""
from __future__ import annotations

import re
import sqlite3
import struct
from datetime import date, timedelta
from pathlib import Path
from typing import Any

from bd_nativo import banco
import ri_fichas_do_disco as FD
import ri_onr as ONR


class CargaOnrError(ValueError):
    """Erro de regra da carga do ONR — mensagem pronta para o balcão."""


# ------------------------------------------------------------ o que o ONR quer
#
# Do `instrucoes_imagens_livro2.pdf`, versao 2.2, item 1. Transcrito, e nao
# suposto: o manual mora em FONTES_EXTERNAS, que nao viaja no `.cgu` — a mesma
# decisao dos vocabularios do ONR em `onr_api`.

RESOLUCAO_EXIGIDA = 200          # dpi, nos dois eixos
UNIDADE_POLEGADA = 2             # TIFF tag 296: 1 nenhuma, 2 polegada, 3 cm

# TIFF tag 259. O manual aceita «sem compressao ou com compressao utilizando um
# dos seguintes algoritmos de compressao SEM PERDAS, baseado na especificacao
# TIFF 6.0».
COMPRESSAO_SEM_PERDAS = {
    1: "sem compressão", 2: "CCITT Group 3 1D", 3: "CCITT Group 3 2D",
    4: "CCITT T.6 (Group 4)", 5: "LZW",
}
COMPRESSAO_COM_PERDAS = {6: "JPEG (antigo)", 7: "JPEG"}

# A data a partir da qual o ONR exige a base — art. 39 da Lei 11.977/2009 lido
# pelo manual: «desde 1º/01/1976, ou desde o inicio das atividades».
DESDE = "1976-01-01"

# Pasta de 8 digitos agrupando de mil em mil: 00000000 guarda 1 a 999.
POR_PASTA = 1000
LARGURA_DA_PASTA = 8


def _so_digitos(valor: Any) -> str:
    return "".join(c for c in str(valor or "") if c.isdigit())


def _numero(valor: Any) -> str:
    """'067' e '67' são a mesma matrícula para o disco. Sem dígitos, vazio."""
    d = _so_digitos(valor)
    return str(int(d)) if d else ""


# =========================================================== o Indicador Pessoal


def vinculos_da_carga(con: sqlite3.Connection) -> list[dict]:
    """Todo vínculo pessoa-matrícula da casa. **SÓ LÊ.**

    **É a carga COMPLETA, e por isso não há filtro de período** — o recorte
    mensal de `ri_onr` serve ao envio avulso; aqui o ONR pede tudo, e mandar
    um mês faria a base «parcial» que ele recusa.

    Uma pessoa com três matrículas dá três linhas: é assim que o histórico
    desta casa está montado, e é assim que os 19 arquivos que ela já mandou
    estão escritos.
    """
    return banco(con).ler(
        """SELECT p.nome,
                  p.documento_numero          AS documento,
                  m.numero                    AS matricula,
                  COALESCE(a.natureza_titulo,
                           CASE WHEN a.tipo='R' THEN 'MATRICULA' ELSE NULL END,
                           'MATRICULA')       AS tipo_ato,
                  COALESCE(a.data_ato, m.data_abertura) AS data_ato,
                  -- **`DTVENDA` LEVA A MESMA DATA, e isso e' medido, nao
                  -- suposto**: nos 19 arquivos que esta casa mandou,
                  -- `DTVENDA` e' igual a `DTREGAVERB` em **10.781 de
                  -- 10.781** — sem uma excecao. Vale a regra do oficial de
                  -- 24/08/2026: na duvida, como o E-Oficio fazia.
                  --
                  -- **E o ensaio contra a producao foi quem achou.** Os
                  -- testes de mesa passavam com o campo vazio, porque no
                  -- teste eu escrevia o que esperava ver; a producao mostrou
                  -- <DTVENDA></DTVENDA> em 3.992 de 3.992. A tela da
                  -- exportacao mensal tem o mesmo buraco, e agora ela chama
                  -- esta consulta.
                  COALESCE(a.data_ato, m.data_abertura) AS data_venda
             FROM ri_partes p
             JOIN ri_matriculas m ON m.id = p.matricula_id
             LEFT JOIN ri_atos  a ON a.id = p.ato_id
            WHERE TRIM(COALESCE(p.nome,'')) <> ''
            ORDER BY coalesce(substring(m.numero FROM '^[0-9]+')::bigint, 0), p.nome, p.id""")


def gerar_indicador_pessoal(con: sqlite3.Connection, cns: str = "") -> str:
    """O XML `<BANCOLIGHT>` da casa inteira, para a primeira carga do IPS.

    **Chama `ri_onr.gerar_indicador_pessoal`, e não uma cópia.** O formato foi
    levantado dos arquivos reais desta serventia; escrevê-lo de novo aqui daria
    duas versões do mesmo arquivo, divergindo no primeiro conserto — e o que a
    tela mostrasse deixaria de ser o que o programa IPS lê.
    """
    return ONR.gerar_indicador_pessoal(vinculos_da_carga(con), cns)


def conferir_indicador_pessoal(con: sqlite3.Connection) -> dict:
    """O que sairia na carga do Indicador Pessoal, antes de gerar. **SÓ LÊ.**"""
    vinculos = vinculos_da_carga(con)
    com_doc = sum(1 for v in vinculos
                  if len(_so_digitos(v.get("documento"))) in (11, 14))
    sem_data = sum(1 for v in vinculos if not (v.get("data_ato") or "").strip())
    pessoas = len({(v.get("nome") or "").strip().upper() for v in vinculos})
    # **NOME COM LIXO NA FRENTE SE DECLARA, E NAO SE LIMPA.** O ensaio contra a
    # producao achou `: WILSON ROCHEDO DE OLIVEIRA` — 11 nomes em 3.992. E os
    # arquivos que o E-Oficio mandou tem **19** iguais: e' sujeira do acervo,
    # e nao defeito nosso.
    #
    # **E limpar seria pior que declarar.** Tirar `: ` parece seguro; tirar o
    # comeco de `1a SUEZ ENERGIA RENOVAVEL S/A` estragaria a razao social. O
    # nome e' o que identifica a pessoa na pesquisa nacional de bens — quem
    # corrige e' quem tem o livro na frente.
    estranhos = [(v.get("nome") or "").strip() for v in vinculos
                 if (v.get("nome") or "").strip()
                 and not (v.get("nome") or "").strip()[0].isalpha()]
    matriculas = len({_numero(v.get("matricula")) for v in vinculos} - {""})
    return {
        "vinculos": len(vinculos),
        "pessoas": pessoas,
        "matriculas": matriculas,
        "com_documento": com_doc,
        "sem_documento": len(vinculos) - com_doc,
        "sem_data": sem_data,
        "nomes_estranhos": sorted(set(estranhos))[:20],
        "quantos_nomes_estranhos": len(set(estranhos)),
        # **O ZERADO É PRECEDENTE DA CASA, E CONTRARIA O MODELO** — os dois
        # números ficam à vista, porque quem assina precisa saber o que manda.
        "zerado_vai_assim": ONR.DOC_DESCONHECIDO,
        "precedente_da_casa": (
            "esta serventia já mandou 7.812 dos 10.781 vínculos com o "
            "documento zerado, e o modelo do ONR pede documento maior que "
            "zero. Vale a regra da casa — fazer como o sistema antigo fazia —, e a "
            "divergência fica declarada aqui."),
    }


# ================================================================ as imagens


def _tags_do_tiff(caminho: Path) -> dict[int, Any] | None:
    """Lê o cabeçalho TIFF sem carregar a imagem. Devolve None se não for TIFF.

    **Ler o cabeçalho é o suficiente e é barato**: são dez mil arquivos, e
    abrir cada um numa biblioteca de imagem levaria minutos numa tela que o
    balcão abre para conferir.
    """
    try:
        with open(caminho, "rb") as f:
            cab = f.read(8)
            if len(cab) < 8:
                return None
            ordem = "<" if cab[:2] == b"II" else ">" if cab[:2] == b"MM" else None
            if ordem is None or struct.unpack(ordem + "H", cab[2:4])[0] != 42:
                return None
            inicio = struct.unpack(ordem + "I", cab[4:8])[0]
            f.seek(inicio)
            (quantas,) = struct.unpack(ordem + "H", f.read(2))
            bruto = f.read(12 * quantas)
            tags: dict[int, Any] = {}
            for i in range(quantas):
                b = bruto[i * 12:(i + 1) * 12]
                if len(b) < 12:
                    break
                etiqueta, tipo, _ = struct.unpack(ordem + "HHI", b[:8])
                (valor,) = struct.unpack(ordem + "I", b[8:12])
                if tipo == 3:                       # SHORT: mora nos 2 primeiros
                    (valor,) = struct.unpack(ordem + "H", b[8:10])
                elif tipo == 5:                     # RATIONAL: mora fora
                    f.seek(valor)
                    num, den = struct.unpack(ordem + "II", f.read(8))
                    valor = num / den if den else num
                tags[etiqueta] = valor
            return tags
    except (OSError, struct.error):
        return None


def conferir_imagens(raiz: Any, *, amostra: int = 300) -> dict:
    """A pasta do disco contra o padrão do ONR. **SÓ LÊ.**

    Confere as quatro coisas que o `instrucoes_imagens_livro2.pdf` exige: o
    nome do arquivo, a pasta de oito dígitos agrupando de mil em mil, a
    resolução de 200 × 200 dpi e a compressão sem perdas.

    **A resolução se mede por amostra, e o número da amostra aparece.** Abrir
    dez mil cabeçalhos leva segundos, mas a tela é do balcão; dizer «120 de
    120» sem dizer que foram 120 seria o carimbo que mente pelo tamanho.
    """
    pasta = Path(raiz)
    if not pasta.exists():
        raise CargaOnrError(
            f"A pasta das imagens não existe: {pasta}. O serviço roda como "
            f"SYSTEM, e unidade mapeada (Z:\\) não funciona para ele — use o "
            f"caminho completo da rede ou uma pasta local.")

    arquivos = [f for f in pasta.rglob("*") if f.is_file()]
    fora_do_nome: list[str] = []
    fora_da_pasta: list[str] = []
    matriculas: set[str] = set()
    certos: list[Path] = []

    for f in arquivos:
        partido = FD.partir(f.name)
        if partido is None:
            fora_do_nome.append(str(f.relative_to(pasta)))
            continue
        numero, _pagina = partido
        matriculas.add(numero)
        mae = f.parent
        # **A pasta é a do ONR? 00000000 guarda 1 a 999.** Arquivo na raiz da
        # varredura não tem pasta nenhuma, e por isso também cai aqui.
        if (mae == pasta or not mae.name.isdigit()
                or len(mae.name) != LARGURA_DA_PASTA
                or int(mae.name) != int(numero) // POR_PASTA):
            fora_da_pasta.append(str(f.relative_to(pasta)))
        else:
            certos.append(f)

    passo = max(1, len(certos) // amostra) if certos else 1
    olhados = certos[::passo][:amostra]
    resolucao_ok = compressao_ok = lidos = 0
    achados: list[str] = []
    for f in olhados:
        tags = _tags_do_tiff(f)
        if tags is None:
            achados.append(f"{f.name}: não é TIFF, ou o cabeçalho não abriu")
            continue
        lidos += 1
        x, y, unid = tags.get(282), tags.get(283), tags.get(296)
        if (x, y) == (RESOLUCAO_EXIGIDA, RESOLUCAO_EXIGIDA) and unid == UNIDADE_POLEGADA:
            resolucao_ok += 1
        elif len(achados) < 12:
            achados.append(f"{f.name}: {x}×{y} dpi (o ONR quer 200×200)")
        comp = tags.get(259)
        if comp in COMPRESSAO_SEM_PERDAS:
            compressao_ok += 1
        elif len(achados) < 12:
            achados.append(
                f"{f.name}: compressão {COMPRESSAO_COM_PERDAS.get(comp, comp)}"
                f" — o ONR exige sem perdas")

    return {
        "raiz": str(pasta),
        "arquivos": len(arquivos),
        "no_padrao": len(certos),
        "matriculas": len(matriculas),
        "fora_do_nome": fora_do_nome[:20],
        "quantos_fora_do_nome": len(fora_do_nome),
        "fora_da_pasta": fora_da_pasta[:20],
        "quantos_fora_da_pasta": len(fora_da_pasta),
        "amostra": lidos,
        "resolucao_ok": resolucao_ok,
        "compressao_ok": compressao_ok,
        "achados": achados,
    }


def matriculas_sem_imagem(con: sqlite3.Connection, raiz: Any,
                          *, limite: int = 0) -> list[dict]:
    """As matrículas que não têm UMA página no disco. **SÓ LÊ.**

    **São elas que fazem a base ser «incompleta» para o ONR**, e não as fichas
    pela metade: para o Bucket, matrícula com uma página é matrícula que
    existe. A ficha incompleta é problema nosso, e mora na outra tela.
    """
    pasta = Path(raiz)
    if not pasta.exists():
        raise CargaOnrError(f"A pasta das imagens não existe: {pasta}.")
    no_disco = {FD.partir(f.name)[0] for f in pasta.rglob("*")
                if f.is_file() and FD.partir(f.name)}
    linhas = banco(con).ler(
        """SELECT id, numero, livro, folha, tipo_ficha, data_abertura
             FROM ri_matriculas
            ORDER BY coalesce(substring(numero FROM '^[0-9]+')::bigint, 0), id""")
    faltando = [x for x in linhas if _numero(x["numero"]) not in no_disco]
    return faltando[:limite] if limite else faltando


# ================================================================ o quadro


# =========================================== o que se copia no formulario
#
# **O FORMULARIO DE ADESAO E' UMA DECLARACAO ASSINADA, e nao um cadastro** —
# achado em 07/09/2026, quando o oficial perguntou «qual a necessidade do
# formulario de adesao?» e eu fui abrir o arquivo pela primeira vez. Ele pede
# numeros que o sistema sabe e o oficial teria de contar a mao.
#
# **E ELE PEDE UMA CONTA DO GMAIL**, que nao e' detalhe de cadastro: e' a conta
# que **controla os dados desta serventia** no Console do Google Cloud — por
# ela se concede, altera e revoga acesso, inclusive o do ONR.

# **A CONTA DO GOOGLE, E NAO O E-MAIL DA SERVENTIA — o oficial me corrigiu em
# 07/09/2026**, no mesmo minuto em que eu escrevia isto: *«esse e' email do
# google, nao oficial da serventia para contato geral»*.
#
# **E A CORRECAO E' DO MEU RACIOCINIO, e nao do rotulo.** Eu havia achado o
# mesmo endereco em `Empresa.Email` e `tbEmpresa.strEmail` do acervo e escrito
# que «as tres fontes batem» — como se a coincidencia provasse que aquele e' o
# e-mail de contato da casa. **Nao prova nada disso**: prova que aquelas duas
# colunas guardam esta string. Duas colunas com o mesmo valor sao uma medicao;
# o que elas SIGNIFICAM nao se deduz de elas concordarem.
#
# É a lição «nome de coluna é afirmação de quem a criou» pela quarta vez — e
# aqui quem desempatou nao foi o dado: foi quem conhece a casa.
#
# O que ela e': a conta que o formulario pede para o **Console do Google Cloud
# Platform**, e por isso a que **controla os dados desta serventia** — por ela
# se concede, altera e revoga acesso, inclusive o do ONR.
#
# **A SENHA DELA NAO ENTRA AQUI, nem em lugar nenhum deste sistema.** Isto e'
# um endereco, e nao uma credencial — a regra do `selador.cred` vale inteira: o
# banco viaja no backup, e o backup ja saiu da serventia.
#
# **E O E-MAIL DE CONTATO DA SERVENTIA CONTINUA NAO EXISTINDO NO SISTEMA.**
# Medido: `settings` nao tem uma unica linha com `@`. E' outro campo, para
# outra coisa — entre elas o e-mail diario de ocorrencias que o ONR manda —, e
# fica declarado em vez de ser preenchido com este por parecenca.
#
# SEM PADRÃO NO CÓDIGO desde 09/10/2026 (sanitização para o código aberto): a
# conta é desta instalação e mora em `settings.onr_conta_google`, gravada pelo
# perfil local (`tools/migrar_settings_serventia_b0.py`).
CHAVE_CONTA_GOOGLE = "onr_conta_google"
CONTA_GOOGLE_PADRAO = ""

# A lista que o proprio formulario oferece em «Qual sistema utiliza?».
# Transcrita, e o nosso e' o «Outros».
SISTEMAS_DO_FORMULARIO = ("Siplam – ControlM", "Siscart", "Cartoon",
                          "Ocian Bit", "Outros")
NOSSO_SISTEMA = "Outros — Cartório Gestão"


def espaco_do_livro_2(raiz: Any) -> dict:
    """Quantos bytes as imagens ocupam. O formulário pede em GB. **SÓ LÊ.**"""
    pasta = Path(raiz)
    if not pasta.exists():
        raise CargaOnrError(f"A pasta das imagens não existe: {pasta}.")
    bytes_ = sum(f.stat().st_size for f in pasta.rglob("*") if f.is_file())
    return {"bytes": bytes_, "gb": round(bytes_ / 1024 ** 3, 2)}


def ultima_matricula(con: sqlite3.Connection) -> dict | None:
    """A de maior número — o formulário pede «Última Matrícula». **SÓ LÊ.**

    **Ordenada por NÚMERO, e não por texto.** Os números desta casa têm
    larguras diferentes, e em ordem alfabética `999` viria depois de `4013`.
    """
    return banco(con).um(
        """SELECT numero, livro, folha, data_abertura FROM ri_matriculas
            ORDER BY coalesce(substring(numero FROM '^[0-9]+')::bigint, 0) DESC, id DESC
            LIMIT 1""")


def para_o_formulario(con: sqlite3.Connection, raiz: Any, *,
                      conta_google: str = "", cns: str = "") -> dict:
    """Os campos do formulário de adesão que o sistema sabe responder. **SÓ LÊ.**

    **O que ele NÃO devolve é tão importante quanto o que devolve.** Nome e IP
    do servidor, IP externo, velocidade do link e o técnico de informática
    responsável **só o oficial tem** — e o formulário avisa que o suporte do
    ONR liga para esse técnico na carga inicial e no erro de atualização.
    Inventar qualquer um deles poria o ONR a ligar para um número que não
    existe.
    """
    try:
        espaco = espaco_do_livro_2(raiz)
        erro = None
    except CargaOnrError as e:
        espaco, erro = None, str(e)
    return {
        "cns": cns,
        # O rotulo do formulario e' «Gmail* do Cartorio ou Oficial/Designado»,
        # com a nota de que serve ao Console do Google Cloud. Nao e' o e-mail
        # de contato da serventia, que o sistema **nao tem**.
        "conta_google": conta_google or CONTA_GOOGLE_PADRAO,
        "conta_google_e_para": (
            "o Console do Google Cloud Platform — é por ela que se concede, "
            "altera e revoga acesso aos dados desta serventia. NÃO é o e-mail "
            "de contato geral do cartório."),
        "total_de_matriculas": int(banco(con).valor(
            "SELECT COUNT(*) FROM ri_matriculas")),
        "ultima_matricula": ultima_matricula(con),
        "espaco": espaco,
        "erro_do_espaco": erro,
        "diretorio": str(Path(raiz)),
        "sistema": NOSSO_SISTEMA,
        # **O QUE SÓ O OFICIAL TEM, dito e não adivinhado.**
        "so_o_oficial_sabe": (
            "nome e IP do servidor, IP da rede e IP externo, a velocidade do "
            "link de internet, e o nome, telefone e e-mail do técnico de "
            "informática responsável — é para ele que o suporte do ONR liga"),
    }


# =========================== a ficha NOVA que ninguem digitalizou
#
# **AS 74 SEM IMAGEM SAO DUAS COISAS, E SO UMA E' ACERVO** — medido em
# 07/09/2026: 55 sao de 1977-1978 (o comeco do Livro 2-A, nunca digitalizado) e
# **sete sao de 2026**, das quais cinco sao as matriculas 4009 a 4013,
# ESTRUTURADAS, abertas entre junho e agosto.
#
# **Aquelas nao sao acervo por digitalizar: sao ficha nova que ninguem
# escaneou** — e esse lado CRESCE a cada matricula que a casa abre. O mutirao
# do acervo espera decisao; este nao deveria esperar nada.
#
# **E O PRAZO E CONFIGURACAO, e nao constante escrita.** Quanto tempo uma ficha
# nova pode ficar sem digitalizacao e' decisao de quem trabalha no balcao; se
# for numero no codigo, mudar de ideia exige empacotar versao.
DIAS_PARA_DIGITALIZAR_PADRAO = 30

# Ate onde a lista olha para tras. Alem disto e' acervo, e acervo nao vira
# atraso — ver a docstring abaixo.
JANELA_DE_MESES_PADRAO = 12


def sem_digitalizacao(con: sqlite3.Connection, raiz: Any, *, hoje: str,
                      dias: int = DIAS_PARA_DIGITALIZAR_PADRAO,
                      meses: int = JANELA_DE_MESES_PADRAO,
                      limite: int = 0) -> list[dict]:
    """As matrículas ABERTAS POR ESTA CASA que passaram do prazo sem imagem.

    **SÓ LÊ**, e é uma lente: mede na hora, e a ficha sai da lista sozinha no
    dia em que a página aparecer no disco. Nada aqui grava marca nenhuma —
    marca que volta é pior que marca que nunca existiu.

    **O ACERVO NÃO ENTRA, e é a regra da casa pela oitava vez.** As 55 fichas
    de 1977 não são atraso de ninguém: são digitalização que nunca foi feita, e
    pô-las aqui faria a lista nascer com cinquenta e cinco linhas que o balcão
    não tem como zerar — e alarme que soa sempre é alarme que ninguém ouve.
    Quem decide o mutirão do acervo é o oficial, noutra tela.

    **E O QUE SEPARA UM DO OUTRO É A DATA, E NÃO A ORIGEM — defeito meu, na
    primeira versão desta função.** Eu havia escrito
    `COALESCE(origem,'') <> 'EOFICIO'`, achando que «veio do acervo» quisesse
    dizer «é antiga». **Não quer**: das cinco matrículas de 2026 que estão sem
    imagem, **três têm `origem = 'EOFICIO'`** — a 4009, a 4012 e a 4013 —,
    porque o E-Ofício foi o sistema desta casa **até agosto de 2026**. O filtro
    esconderia três dos cinco casos reais.

    **`origem` diz DE ONDE A LINHA VEIO; `data_abertura` diz QUANDO O ATO
    ACONTECEU** — e a pergunta aqui é a segunda. É a lição «a mesma palavra em
    dois lugares não quer dizer a mesma coisa», agora entre duas colunas da
    mesma tabela.

    Então são duas janelas, e as duas se configuram: `meses` diz até onde olhar
    para trás (o que é mais velho é acervo), e `dias` diz a partir de quando a
    ficha nova está atrasada.
    """
    try:
        corte = (date.fromisoformat(str(hoje)[:10])
                 - timedelta(days=max(0, int(dias)))).isoformat()
    except ValueError as erro:
        raise CargaOnrError(f"Data inválida: {hoje}") from erro

    pasta = Path(raiz)
    if not pasta.exists():
        raise CargaOnrError(
            f"A pasta das imagens não existe: {pasta}. O serviço roda como "
            f"SYSTEM, e unidade mapeada (Z:\\\\) não funciona para ele.")
    no_disco = {FD.partir(f.name)[0] for f in pasta.rglob("*")
                if f.is_file() and FD.partir(f.name)}

    # A janela em DIAS, e não em meses de calendário: o que se quer é «até onde
    # olhar para trás», e trinta dias por mês responde isso sem trazer a
    # aritmética de fevereiro para dentro de uma lista de trabalho.
    try:
        piso = (date.fromisoformat(str(hoje)[:10])
                - timedelta(days=max(1, int(meses)) * 30)).isoformat()
    except (ValueError, TypeError) as erro:
        raise CargaOnrError(f"Janela inválida: {meses}") from erro

    fora: list[dict] = []
    for linha in banco(con).ler(
            """SELECT id, numero, livro, folha, tipo_ficha, data_abertura,
                      origem
                 FROM ri_matriculas
                WHERE data_abertura IS NOT NULL AND TRIM(data_abertura) <> ''
                  AND data_abertura <= %s
                  AND data_abertura >= %s
                ORDER BY data_abertura DESC, id DESC""", (corte, piso)):
        x = dict(linha)
        if _numero(x["numero"]) in no_disco:
            continue
        try:
            x["dias"] = (date.fromisoformat(str(hoje)[:10])
                         - date.fromisoformat(x["data_abertura"][:10])).days
        except ValueError:
            x["dias"] = None
        fora.append(x)
    return fora[:limite] if limite else fora


def _minima(con: sqlite3.Connection, tabela: str, coluna: str) -> str | None:
    return banco(con).valor(
        f"SELECT MIN({coluna}) FROM {tabela} "
        f"WHERE {coluna} IS NOT NULL AND TRIM({coluna}) <> ''")


def prontidao(con: sqlite3.Connection, raiz: Any) -> dict:
    """A conferência inteira: a casa está pronta para a carga do ONR?

    **NÃO devolve «pronto» nem «não pronto», e isso é deliberado.** Devolve os
    números, e cada um com o que o ONR exige ao lado. Quem decide se manda a
    base como está — com a declaração de base incompleta assinada — é quem
    assina; um verde ou vermelho aqui seria o sistema decidindo pelo oficial,
    que é a regra do CNIB pela sétima vez.
    """
    ip = conferir_indicador_pessoal(con)
    try:
        img = conferir_imagens(raiz)
        sem_imagem = matriculas_sem_imagem(con, raiz)
        erro_do_disco = None
    except CargaOnrError as erro:
        # **ZERO MEDIDO E ZERO POR ENGANO SÃO COISAS DIFERENTES.** Pasta que
        # não abre não pode virar «nenhuma imagem»: o erro sobe no lugar dos
        # números, e a tela o mostra.
        img, sem_imagem, erro_do_disco = None, None, str(erro)

    total = int(banco(con).valor("SELECT COUNT(*) FROM ri_matriculas"))
    mais_antiga = _minima(con, "ri_matriculas", "data_abertura")
    ato_mais_antigo = _minima(con, "ri_atos", "data_ato")

    return {
        "matriculas": total,
        "indicador_pessoal": ip,
        "imagens": img,
        "erro_do_disco": erro_do_disco,
        "sem_imagem": len(sem_imagem) if sem_imagem is not None else None,
        "mais_antiga": mais_antiga,
        "ato_mais_antigo": ato_mais_antigo,
        "desde": DESDE,
        "alcanca_1976": bool(mais_antiga and mais_antiga <= DESDE),
    }
