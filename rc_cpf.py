"""O CPF no registro de nascimento — o que dá para fazer, e o que falta.

O QUE O OFICIAL PEDIU
    «Tentemos agora criar um módulo de integração para gerar CPF pelo sistema
     (acho que usa comunicação com CRC ou SIRC). O DeMaria tem esse módulo.»
    E, logo depois: «e-ofício tem módulo, mas não faz».

O QUE SE MEDIU, ANTES DE CONSTRUIR
    **Nem a CRC nem o SIRC geram CPF.** Os dois o *transportam*: o manual de
    carga da CRC registra, no histórico da versão 1.1 (08/12/2014), «inclusão
    do CPF para adequação do convênio com a Receita Federal» — o campo entrou
    para *levar* o número, e o XSD do SIRC lista `CPF` apenas como um tipo de
    documento entre doze.

    **O E-Ofício tem o botão e não funciona** — dito pelo oficial. No binário
    há `MontaXmlCPF` e um campo de hash, mas nenhuma URL de serviço da Receita,
    da ARPEN ou da CRC: as únicas URLs dele são dos Correios, do relatório da
    Microsoft e do selo do TJ-PI.

    **DEPOIS O OFICIAL MANDOU O MANUAL CERTO** — «Manual para emissão do CPF
    na CRC Nacional», versão 1.2, da ARPEN-Brasil —, e ele fecha o quadro:

      - a inscrição é **obrigatória**, e não opcional (IN RFB 1.548/2015);
      - há **três caminhos**, e o primeiro passo é o mesmo para os três: o
        **Termo de Adesão da RFB**, assinado pelo oficial com certificado
        digital na CRC Nacional. **Sem ele, nem a tela deles aparece**;
      - o caminho por webservice existe, e o manual aponta os padrões para a
        versão **2.3** do manual de cargas. A casa tem a 2.6 e a 2.7 — e o XML
        de retorno delas traz código, mensagem e erros, **sem o número
        gerado**. Falta, portanto, a parte do manual que descreve o retorno
        com o CPF.

O QUE ESTE MÓDULO FAZ, ENTÃO
    O que não depende do serviço, que é mais do que parece:

      - **confere** o CPF que vier, pelo dígito verificador — regra pública,
        e é o que impede um número digitado errado de entrar na certidão;
      - diz **o que falta no assento** para que o pedido possa ser feito, que
        é a mesma lista de dados que a Receita exige em qualquer canal;
      - lista **quem ainda não tem CPF**, separando o que é do balcão do que
        é do acervo;
      - guarda o número quando ele chegar, por qualquer caminho.

    Quando o canal existir, ele entra num lugar só — `solicitar`, que hoje
    recusa dizendo exatamente o que falta e de quem é cada coisa.

    **E enquanto isso há um caminho que funciona**: o formulário da CRC
    Nacional, na tela deles, assim que o termo de adesão for assinado. O
    módulo o declara em `CAMINHOS`, para que a falta da integração não seja
    lida como falta do serviço.
"""
from __future__ import annotations

import nome_humano as NOMEHUM

import sqlite3
from typing import Any

import cpf_cnpj as CPFDOC

# ------------------------------------------------- A NORMA, E ELA OBRIGA
#
#   Instrucao Normativa RFB nº 1.548/2015, art. 3º, V: estao **obrigadas** a
#   inscrever-se no CPF as pessoas fisicas «registradas em oficio de registro
#   civil de pessoas naturais no Brasil, **no momento da lavratura do assento
#   de nascimento**».
#
#   O manual da ARPEN e explicito: «A inscricao no CPF nao e um ato
#   discricionario dos usuarios e sim obrigatorio nos termos da referida
#   instrucao normativa.» **Nao e conveniencia que se oferece: e dever.**
NORMA = ("Instrução Normativa RFB nº 1.548/2015, art. 3º, V — a inscrição é "
         "**obrigatória** no momento da lavratura do assento de nascimento, e "
         "não é ato discricionário")

# ONDE A CRC NACIONAL FICA — e por que o sistema só LINKA, e não embute.
#
#   O oficial pediu, em 30/08/2026, «um link para acesso interno no sistema ao
#   campo da CRC que gera o CPF», e contou como o DeMaria fazia: «um link na
#   internet e **uma tela menor** em que usava o certificado digital e as
#   informacoes do registro».
#
#   **A JANELA SEPARADA ENTRA; A MOLDURA EMBUTIDA (iframe), NAO.** A diferenca
#   nao e de tamanho, e de quem parece dono da tela: numa janela do navegador o
#   dominio aparece, e quem vai usar o certificado ve que esta no site da
#   Central. Dentro de um iframe, a tela pareceria nossa — e **tela de terceiro
#   que pede credencial dentro de outro sistema e a forma de um golpe de
#   phishing**. Nao se acostuma o balcao com ela.
#
#   **E OS DADOS DO REGISTRO NAO VAO PELA URL.** Nome, filiacao e data de
#   nascimento numa querystring ficam no historico do navegador e nos registros
#   do servidor do outro lado. O sistema os mostra **ao lado**, prontos para
#   copiar — a conveniencia e a mesma, e o dado nao viaja onde nao devia.
# O ENDERECO DIRETO DA TELA DE INSCRICAO — informado pelo oficial em
# 30/08/2026. Vai direto ao formulario, e nao a pagina inicial: um clique a
# menos, e nenhum menu a procurar no meio do atendimento.
CRC_GERAR_CPF = ("https://sistema.registrocivil.org.br/receitaFederal/"
                 "gerarInscricao.cfm")
CRC_NACIONAL = "https://sistema.registrocivil.org.br/indexFrame.cfm"
CRC_ABRE_FORA = True
PORQUE_NAO_EMBUTE = (
    "A CRC é acessada com o **seu certificado digital**. Ela abre em outra "
    "aba, e não dentro desta tela, para que você veja no navegador que está "
    "no site da Central — tela que pede certificado dentro de outro sistema é "
    "a forma de um golpe, e não se acostuma o balcão com ela."
)

# OS TRES CAMINHOS que a CRC Nacional oferece, medidos no «Manual para emissão
# do CPF na CRC Nacional», versão 1.2, da ARPEN-Brasil.
CAMINHOS: tuple[dict, ...] = (
    {"chave": "FORMULARIO",
     "nome": "Formulário na CRC Nacional",
     "onde": "sistema.registrocivil.org.br → Convênios → Inscrição",
     "link": CRC_GERAR_CPF,
     "como": "o escrevente preenche a mão, na tela da CRC, e o CPF aparece",
     "serve_para_nos": True,
     "porque": "**funciona hoje**, assim que o termo de adesão for assinado — "
               "não depende de nenhuma integração nossa"},
    {"chave": "UNIDADE_INTERLIGADA",
     "nome": "Unidade Interligada",
     "onde": "a maternidade",
     "como": "automático: ao confirmar os dados, a CRC pede o CPF e o insere "
             "na certidão",
     "serve_para_nos": False,
     "porque": "é o fluxo da maternidade, e esta casa registra no balcão"},
    {"chave": "WEBSERVICE",
     "nome": "Integração pelo sistema do cartório",
     "onde": "a carga da CRC",
     "como": "o sistema interno pede, e recebe o CPF de volta",
     "serve_para_nos": True,
     "porque": "**é o que o oficial pediu** — gerar o CPF pelo nosso sistema"},
)

# O QUE FALTA PARA A INTEGRAÇÃO, agora com nome e endereço.
#
#   **O PRIMEIRO ITEM É PRÉ-REQUISITO DE TODOS OS TRÊS CAMINHOS**, inclusive
#   do formulário manual: sem a adesão assinada, nem a tela da CRC aparece.
FALTA_PARA_INTEGRAR = (
    {"o_que": "o **Termo de Adesão da Receita Federal**, assinado com "
              "certificado digital",
     "de_quem": "**o oficial**, em sistema.registrocivil.org.br → Convênios → "
                "Termo de Adesão RFB",
     "link": CRC_NACIONAL,
     "trava_tudo": True},
    {"o_que": "o **manual de cargas da CRC com a parte do CPF** — a ARPEN "
              "aponta a versão 2.3, e a casa tem a 2.6 e a 2.7, cujo XML de "
              "retorno traz só código, mensagem e erros, **sem o CPF gerado**",
     "de_quem": "ARPEN/CRC Nacional. O próprio manual recomenda: «enviar o "
                "manual de cargas atualizado para os desenvolvedores do "
                "sistema interno do cartório»",
     "trava_tudo": False},
    {"o_que": "o **certificado digital** que autentica a chamada",
     "de_quem": "já existe — é o A3 do oficial",
     "trava_tudo": False},
)

# OS ERROS QUE A RECEITA DEVOLVE, e que o manual da ARPEN nomeia.
#
#   **ELES NÃO IMPEDEM O REGISTRO**, e isso é o mais importante: «nos casos em
#   que houver algum erro e o CPF não for gerado, o cartório deverá proceder a
#   emissão da certidão de nascimento **normalmente sem o CPF**, e os pais
#   deverão ser encaminhados a um posto da Receita Federal».
ERROS_CONHECIDOS: tuple[dict, ...] = (
    {"o_que": "divergência no nome da mãe do registrado",
     "como_evitar": "conferir o nome da filiação com o documento dela"},
    {"o_que": "nome do registrado com mais de **60 caracteres**",
     "como_evitar": "não há como contornar — é limite do sistema da RFB"},
)

O_QUE_FAZER_SE_ERRAR = (
    "Emitir a certidão de nascimento **normalmente, sem o CPF**, e encaminhar "
    "os pais a um posto da Receita Federal. O erro do CPF não segura o "
    "registro — que é obrigatório e tem prazo próprio."
)

# O PRAZO PARA CORRIGIR o que saiu errado, na CRC Nacional.
PRAZO_CORRECAO_DIAS = 90
ONDE_CORRIGIR = ("CRC Nacional → CPF-RFB → Pesquisa de inscrição de CPF, "
                 "com certificado digital")

# OS DADOS QUE A RECEITA EXIGE para inscrever alguém no CPF, em qualquer canal.
#
#   **NÃO SÃO INVENTADOS**: são os que constam do assento de nascimento e que a
#   Receita usa para identificar a pessoa. Ter esta lista antes do serviço vale
#   por si — ela diz, hoje, quais assentos estariam prontos para pedir.
DADOS_DO_PEDIDO: tuple[dict, ...] = (
    {"chave": "nome", "o_que": "o nome completo do registrado",
     "de_onde": "`rc_assentos.nome`"},
    {"chave": "data_nascimento", "o_que": "a data de nascimento",
     "de_onde": "`rc_assentos.data_fato`"},
    {"chave": "sexo", "o_que": "o sexo",
     "de_onde": "a pessoa de papel REGISTRADO"},
    {"chave": "filiacao", "o_que": "o nome de ao menos uma filiação",
     "de_onde": "as pessoas de papel MAE ou PAI"},
    {"chave": "municipio_nascimento", "o_que": "o município de nascimento",
     "de_onde": "`naturalidade_declarada` ou o município do registro"},
    {"chave": "matricula", "o_que": "a matrícula de 32 dígitos do assento",
     "de_onde": "`rc_assentos.matricula`"},
)

ORIGEM_DO_ACERVO = "EOFICIO"

# ------------------------- O QUE A PROPRIA TELA DA CRC AVISA, e obriga
#
#   Lido no print da tela `receitaFederal/gerarInscricao.cfm`, em 30/08/2026.
#   O aviso e assinado por «Arpen-Brasil e Receita Federal do Brasil», e as
#   tres frases mudam o que o sistema pode oferecer:
PRAZO_DIAS_UTEIS = 1
QUANDO_SE_PODE = (
    "**No momento do registro de nascimento**, no Livro A — ou, na "
    "impossibilidade, **no máximo no primeiro dia útil posterior**."
)
QUANDO_NAO_SE_PODE = (
    "É **expressamente proibido** inscrever CPF para **transcrições** de "
    "registro de nascimento e para **registros lavrados anteriormente** que "
    "não tenham CPF."
)
PENALIDADE = (
    "«Qualquer prática fora destes padrões ficará o usuário e/ou Oficial às "
    "penalidades legais» — o aviso é da Arpen-Brasil e da Receita Federal."
)

# **ISTO CONFIRMA, DE FORA, A DECISAO DE DEIXAR O ACERVO DE FORA.** A lista de
# `assentos_sem_cpf` ja nascia so com os do balcao porque o CPF dos antigos e o
# mutirao do art. 347; agora se sabe que pedir por eles nao e apenas inutil —
# **e proibido**, com penalidade nomeada.
ACERVO_E_PROIBIDO = True


class CpfError(ValueError):
    """Erro de regra, em português de balcão."""


def _digitos(valor: Any) -> str:
    return "".join(c for c in ("" if valor is None else str(valor))
                   if c.isdigit())


def valido(cpf: Any) -> bool:
    """Digito verificador do CPF — helper central."""
    return CPFDOC.cpf_valido(cpf)


def formatar(cpf: Any) -> str:
    """`00000004502` -> `000.000.045-02`. Devolve como veio se não der."""
    n = _digitos(cpf)
    if len(n) != 11:
        return ("" if cpf is None else str(cpf)).strip()
    return f"{n[:3]}.{n[3:6]}.{n[6:9]}-{n[9:]}"


def o_que_falta_para_pedir(assento: dict, pessoas: list[dict]) -> list[dict]:
    """Os dados que o assento ainda não tem para o pedido. Só lê.

    Existe **antes** do serviço de propósito: quando o canal chegar, a casa já
    saberá quais assentos estão prontos — em vez de descobrir um a um, no
    erro.
    """
    por_papel = {(p.get("papel") or "").upper(): p for p in (pessoas or [])}
    tem = {
        "nome": (assento.get("nome") or "").strip(),
        "data_nascimento": (assento.get("data_fato") or "").strip(),
        "sexo": (por_papel.get("REGISTRADO", {}).get("sexo") or "").strip(),
        "filiacao": ((por_papel.get("MAE", {}).get("nome") or "")
                     or (por_papel.get("PAI", {}).get("nome") or "")).strip(),
        "municipio_nascimento": (
            (assento.get("naturalidade_declarada") or "").strip()),
        "matricula": (assento.get("matricula") or "").strip(),
    }
    return [d for d in DADOS_DO_PEDIDO if not tem.get(d["chave"])]


def dados_para_copiar(assento: dict, pessoas: list[dict], *,
                      lugar: dict | None = None) -> list[dict]:
    """Os dados do assento, **na ordem exata da tela da CRC**. Só lê.

    A ordem e os rótulos foram medidos no print de `gerarInscricao.cfm`, em
    30/08/2026. **A ordem importa**: quem preenche desce a tela de cima para
    baixo, e uma lista fora de ordem obriga a procurar cada campo.

    **EXISTE PARA QUE O DADO NÃO PRECISE VIAJAR PELA URL.** O formulário da
    CRC é preenchido à mão, e o escrevente hoje volta ao assento para ler cada
    campo. Isto põe os seis lado a lado, na ordem em que ele vai digitar.

    Devolve rótulo e valor; o que faltar vem com valor vazio, para a tela
    poder mostrá-lo como falta em vez de escondê-lo.
    """
    por_papel = {(p.get("papel") or "").upper(): p for p in (pessoas or [])}
    mae = por_papel.get("MAE", {})
    pai = por_papel.get("PAI", {})
    nasc = (assento.get("data_fato") or "")[:10]
    if len(nasc) == 10:
        nasc = f"{nasc[8:10]}/{nasc[5:7]}/{nasc[:4]}"
    reg = (assento.get("data_ato") or "")[:10]
    if len(reg) == 10:
        reg = f"{reg[8:10]}/{reg[5:7]}/{reg[:4]}"
    lugar = lugar or {}
    return [
        {"rotulo": "Nome da Criança", "valor": (assento.get("nome") or "").strip()},
        {"rotulo": "Sexo",
         "valor": {"M": "Masculino", "F": "Feminino"}.get(
             ((por_papel.get("REGISTRADO", {}).get("sexo")) or "")[:1].upper(), "")},
        {"rotulo": "Data de Nascimento", "valor": nasc},
        {"rotulo": "DNV", "valor": (assento.get("dnv") or "").strip()},
        {"rotulo": "Estado Naturalidade",
         "valor": (assento.get("naturalidade_uf") or "MA").strip()},
        {"rotulo": "Cidade Naturalidade",
         "valor": (assento.get("naturalidade_declarada") or "").strip()},
        {"rotulo": "Livro", "valor": str(lugar.get("livro_numero") or "").strip()},
        {"rotulo": "Folha", "valor": str(lugar.get("folha") or "").strip()},
        {"rotulo": "Número", "valor": str(assento.get("numero") or "").strip()},
        {"rotulo": "Data do Registro", "valor": reg},
        {"rotulo": "Matrícula",
         "valor": "".join(c for c in (assento.get("matricula") or "")
                          if c.isdigit())},
        # A filiacao nao esta na PRIMEIRA tela — o botao diz «Avançar
        # Formulario», e ela vem depois. Fica no fim da lista, para quem
        # avancar ja ter o dado a mao.
        {"rotulo": "Nome da mãe (etapa seguinte)",
         "valor": (mae.get("nome") or "").strip()},
        {"rotulo": "Nome do pai (etapa seguinte)",
         "valor": (pai.get("nome") or "").strip()},
    ]


# ------------------------------------------------- O PREENCHEDOR
#
#   **O QUE ELE E, E POR QUE E ASSIM.** O oficial pediu «uma forma mais rapida
#   de preencher que copiar uma por uma das informacoes». A tela da CRC e uma
#   tabela com o rotulo numa celula e o campo na seguinte — foi o que o print
#   de 30/08/2026 mostrou —, e isso permite achar cada campo **pelo rotulo**,
#   sem saber o `name` dele.
#
#   O caminho e um **favorito do navegador** (bookmarklet), arrastado uma vez
#   para a barra:
#
#       1. aqui, o escrevente clica «Copiar todos»;
#       2. la, na tela da CRC, clica no favorito;
#       3. o favorito le o que esta na area de transferencia e preenche.
#
#   POR QUE PELO CLIPBOARD, E NAO PELA URL. Dado de crianca — nome, filiacao,
#   data de nascimento — numa querystring fica no historico do navegador e nos
#   registros do servidor do outro lado. Pela area de transferencia ele nao
#   viaja: sai daqui e entra la, na mesma maquina.
#
#   **E ELE NAO ENVIA NADA.** Preenche e para. Quem confere e clica «Avançar
#   Formulario» e a pessoa — que e quem responde pelo ato.
PREENCHEDOR = r"""javascript:(function(){
 function achaCampo(rotulo){
  var tds=document.getElementsByTagName('td');
  for(var i=0;i<tds.length;i++){
   var t=(tds[i].textContent||'').replace(/\s+/g,' ').trim().replace(/:$/,'');
   if(t.toLowerCase()===rotulo.toLowerCase()){
    var l=tds[i].parentNode;
    var c=l.querySelectorAll('input[type=text],input:not([type]),select');
    if(c.length)return c[0];
   }
  }
  return null;
 }
 function marcaSexo(v){
  var r=document.querySelectorAll('input[type=radio]');
  for(var i=0;i<r.length;i++){
   var p=r[i].parentNode,txt=(p.textContent||'').trim().toLowerCase();
   if(txt.indexOf(v.toLowerCase())===0||txt===v.toLowerCase()){r[i].click();return 1;}
  }
  return 0;
 }
 function aplica(texto){
  var n=0,faltou=[];
  texto.split(/
?
/).forEach(function(linha){
   var i=linha.indexOf(':'); if(i<0)return;
   var rot=linha.slice(0,i).trim(), val=linha.slice(i+1).trim();
   if(!val)return;
   if(rot.toLowerCase()==='sexo'){ if(marcaSexo(val))n++; else faltou.push(rot); return; }
   if(rot.indexOf('etapa seguinte')>=0)return;
   var campo=achaCampo(rot);
   if(campo){campo.value=val;
    campo.dispatchEvent(new Event('input',{bubbles:true}));
    campo.dispatchEvent(new Event('change',{bubbles:true}));n++;}
   else faltou.push(rot);
  });
  alert('Preenchidos: '+n+(faltou.length?'\nNao achei: '+faltou.join(', '):'')
        +'\n\nConfira antes de avancar. Nada foi enviado.');
 }
 if(navigator.clipboard&&navigator.clipboard.readText){
  navigator.clipboard.readText().then(aplica,function(){
   var t=prompt('Cole aqui os dados copiados do Cartorio Gestao:');if(t)aplica(t);});
 }else{
  var t=prompt('Cole aqui os dados copiados do Cartorio Gestao:');if(t)aplica(t);
 }
})();"""

COMO_USAR_O_PREENCHEDOR = (
    "Arraste **uma vez** o botão «Preencher CPF na CRC» para a barra de "
    "favoritos do navegador. Depois, para cada registro: clique **Copiar "
    "todos** aqui, abra a inscrição na CRC, e clique no favorito. Ele "
    "preenche os campos e **para** — quem confere e envia é você."
)


def solicitar(*_args, **_kw):
    """**RECUSA, E DIZ POR QUÊ.** Não há canal para pedir CPF.

    Esta função existe para que o dia em que o canal chegar tenha um lugar só
    onde entrar — e para que ninguém procure a integração e conclua que ela
    está escondida em algum lugar. **Ela não está: ela não existe.**
    """
    raise CpfError(
        "O sistema ainda não pede CPF à Receita. Falta, **antes de tudo**, o "
        "Termo de Adesão da RFB assinado pelo oficial na CRC Nacional "
        "(sistema.registrocivil.org.br → Convênios → Termo de Adesão RFB) — "
        "sem ele nenhum dos três caminhos funciona, nem o formulário manual. "
        "E falta o manual de cargas da CRC com a parte do CPF: o que a casa "
        "tem (2.6 e 2.7) traz um XML de retorno com código, mensagem e erros, "
        "**sem o número gerado**. "
        "Enquanto isso, o caminho que já funciona é o **formulário da CRC "
        "Nacional**, na tela deles.")


def assentos_sem_cpf(con: sqlite3.Connection, *, so_do_balcao: bool = True,
                     limite: int = 500) -> list[dict]:
    """Os nascimentos sem CPF gravado. Só lê.

    `so_do_balcao` deixa o acervo de fora, e é o padrão: **o CPF dos assentos
    antigos é o mutirão do art. 347**, que tem tela própria e caminho próprio
    (averbação). Misturá-lo com o do recém-nascido faria uma lista de 244
    linhas onde a de hoje tem poucas — e lista assim ninguém abre.
    """
    con.row_factory = sqlite3.Row
    onde = ["UPPER(COALESCE(a.especie,'')) = 'NASCIMENTO'",
            "COALESCE(a.situacao,'ATIVO') <> 'CANCELADO'",
            "TRIM(COALESCE(a.cpf_registrado,'')) = ''"]
    params: list[Any] = []
    if so_do_balcao:
        onde.append("COALESCE(a.origem,'') <> ?")
        params.append(ORIGEM_DO_ACERVO)
    return [dict(r) for r in con.execute(
        f"""SELECT a.id, a.numero, a.nome, a.data_ato, a.data_fato,
                   a.matricula, a.origem
              FROM rc_assentos a
             WHERE {' AND '.join(onde)}
          ORDER BY a.data_ato IS NULL, a.data_ato DESC, a.id DESC
             LIMIT ?""", (*params, limite))]


# Nomes que NÃO assinam teor — máquina / placeholders.
_NOMES_ROBO = frozenset({
    "operador", "none", "null", "sistema", "robot", "robo", "bot",
    "cartoriogestao", "servidor",
})


def data_br(data: Any) -> str:
    """ISO/`data_ato` → `dd/mm/aaaa` (America/Sao_Paulo calendar day). Só calcula."""
    s = ("" if data is None else str(data)).strip()
    if not s:
        return ""
    if len(s) >= 10 and s[4:5] == "-" and s[7:8] == "-":
        y, m, d = s[:10].split("-")
        return f"{d}/{m}/{y}"
    if len(s) >= 10 and s[2:3] == "/" and s[5:6] == "/":
        return s[:10]
    return ""


def nome_usuario_teor(usuario: Any) -> str:
    """Nome do escrevente no teor — nunca rotulo de robo. So calcula."""
    return NOMEHUM.nome_humano_para_ato(usuario)

def eh_teor_cpf(teor: Any) -> bool:
    """Se o texto é (ou era) averbação de CPF. Só calcula."""
    t = " ".join(str(teor or "").split()).lower()
    return t.startswith("averbo neste assento o cpf")


def extrair_cpf_do_teor(teor: Any) -> str | None:
    """CPF formatado a partir do teor de averbação, se fechar. Só calcula."""
    import re as _re
    m = _re.search(r"CPF\s+n\.?\s*º?\s*([\d.\-]+)", str(teor or ""), _re.I)
    if not m:
        return None
    n = _digitos(m.group(1))
    return formatar(n) if valido(n) else None


def extrair_referente_do_teor(teor: Any) -> tuple[str, str] | None:
    """(rótulo, nome) de quem o CPF é, se o teor disser. Só calcula.

    NASCEU DO CASAMENTO — achado em 09/09/2026: com dois nubentes, o teor
    passou a dizer **de quem** é o CPF (`texto_averbacao` com `nome` e
    `papel_rotulo`), e a sincronização do selo (`reescrever_teor_cpf`)
    reconstrói o texto do zero a cada chamada — sem isto, ela apagaria a
    parte que diz de qual cônjuge é o número assim que o selo saísse.
    """
    import re as _re
    m = _re.search(r"referente\s+a[oa]?\s+([^,]+),\s*([^.]+)\.",
                  str(teor or ""), _re.I)
    if not m:
        return None
    return (m.group(1).strip(), m.group(2).strip())


def texto_averbacao(cpf: Any, *, nome: Any = None, papel_rotulo: Any = None,
                    selo: Any = None, data: Any = None,
                    usuario: Any = None, funcao: Any = None) -> str:
    """Teor curto da averbação de CPF — forma pedida pelo oficial.

    Parcial (antes do selo): ``Averbo neste assento o CPF n. {cpf}.``
    Completo (após selar): ``Averbo neste assento o CPF n. {cpf}. {selo}.
    {data}. {usuario}, {função}.`` — a função (cargo) só entra se conhecida
    em ``users.funcao``; sem cadastro, fica só o nome (não inventar).

    O fundamento art. 347 fica no campo separado ``fundamento`` do ato —
    não se repete no teor. Confere o dígito antes de montar o texto.

    `nome` E `papel_rotulo` DIZEM DE QUEM É O CPF — pedido do oficial em
    09/09/2026, sobre o casamento: com dois nubentes, «Averbo o CPF» sozinho
    não diz de qual dos dois. No nascimento e no óbito, com um só principal,
    ficam de fora (nenhum dos dois é passado) — o teor continua exatamente
    como sempre foi, sem novidade nenhuma para quem já o lia.
    """
    n = _digitos(cpf)
    if not valido(n):
        raise CpfError(
            f"O CPF «{cpf}» não fecha o dígito verificador. Confira com quem "
            f"está no balcão — número errado na certidão não se desfaz "
            f"depois.")
    nome_txt = ("" if nome is None else str(nome)).strip()
    rotulo_txt = ("" if papel_rotulo is None else str(papel_rotulo)).strip()
    if nome_txt and rotulo_txt:
        primeira = (f"Averbo neste assento o CPF n. {formatar(n)}, referente "
                   f"ao {rotulo_txt[:1].lower()}{rotulo_txt[1:]}, "
                   f"{nome_txt}.")
    elif rotulo_txt:
        # SEM NOME MAS COM PAPEL: o assento tem o papel (o casamento sempre
        # tem NUBENTE1/NUBENTE2) e não tem a pessoa — não inventa nome, mas
        # ainda diz de qual dos dois é o número.
        primeira = (f"Averbo neste assento o CPF n. {formatar(n)}, referente "
                   f"ao {rotulo_txt[:1].lower()}{rotulo_txt[1:]}.")
    elif nome_txt:
        primeira = (f"Averbo neste assento o CPF n. {formatar(n)}, referente "
                   f"a {nome_txt}.")
    else:
        primeira = f"Averbo neste assento o CPF n. {formatar(n)}."
    partes = [primeira]
    s = ("" if selo is None else str(selo)).strip()
    if s:
        partes.append(f"{s}.")
    d = data_br(data)
    if d:
        partes.append(f"{d}.")
    u = nome_usuario_teor(usuario)
    if u:
        f = ("" if funcao is None else str(funcao)).strip()
        if f:
            partes.append(f"{u}, {f}.")
        else:
            partes.append(f"{u}.")
    return " ".join(partes)


def reescrever_teor_cpf(teor: Any, *, selo: Any = None, data: Any = None,
                       usuario: Any = None, funcao: Any = None) -> str | None:
    """Reescreve teor de CPF no formato curto; None se não for averbação de CPF."""
    if not eh_teor_cpf(teor):
        return None
    cpf = extrair_cpf_do_teor(teor)
    if not cpf:
        return None
    referente = extrair_referente_do_teor(teor)
    rotulo, nome = referente if referente else (None, None)
    return texto_averbacao(
        cpf, nome=nome, papel_rotulo=rotulo, selo=selo, data=data,
        usuario=usuario, funcao=funcao)


# QUEM RECEBE A AVERBAÇÃO DE CPF, POR ESPÉCIE — pode ser mais de um: o
# casamento tem OS DOIS nubentes, cada um com o seu próprio CPF. Achado em
# 09/09/2026, pedido do oficial: «o sistema só tem a opção de averbar 1
# CPF» — porque `gravar_no_registrado` só sabia gravar em quem tem o papel
# REGISTRADO, que não existe no casamento (lá são NUBENTE1 e NUBENTE2) nem,
# por sinal, no óbito (lá é FALECIDO — o mesmo defeito, menor).
PRINCIPAIS_DA_ESPECIE: dict[str, tuple[tuple[str, str], ...]] = {
    "NASCIMENTO": (("REGISTRADO", ""),),
    "OBITO": (("FALECIDO", ""),),
    "CASAMENTO": (("NUBENTE1", "Primeiro nubente"),
                  ("NUBENTE2", "Segundo nubente")),
    "CASAMENTO_RELIGIOSO": (("NUBENTE1", "Primeiro nubente"),
                           ("NUBENTE2", "Segundo nubente")),
}


def quem_falta_cpf(pessoas: list[dict], especie: Any, *,
                   cpf_registrado: Any = None) -> list[dict]:
    """Quem ainda precisa da averbação do CPF, com papel/rótulo/nome. Só calcula.

    PARA O FORMULÁRIO DA FICHA, e não para a lista do mutirão — aquela
    (`rc_dados_cadastrais.o_que_falta`) responde a mesma pergunta em texto,
    para uma tabela; esta devolve dado estruturado, um item por pessoa que
    falta, para desenhar um botão de cada vez. No nascimento e no óbito, com
    um principal só, o item vem com `papel=None` — o formulário continua
    exatamente como sempre foi, sem pedir para escolher ninguém.
    """
    principais = PRINCIPAIS_DA_ESPECIE.get(str(especie or "").strip().upper())
    if not principais:
        return []
    if len(principais) == 1:
        if "".join(c for c in str(cpf_registrado or "") if c.isdigit()):
            return []
        papel, _rotulo = principais[0]
        pessoa = next((p for p in pessoas
                      if str(p.get("papel") or "").upper() == papel), None)
        return [{"papel": None, "rotulo": "",
                "nome": (pessoa or {}).get("nome") or ""}]
    faltando = []
    for papel, rotulo in principais:
        tem_cpf = any(
            str(p.get("papel") or "").upper() == papel
            and str(p.get("documento_tipo") or "").upper() == "CPF"
            and str(p.get("documento_numero") or "").strip()
            for p in pessoas)
        if tem_cpf:
            continue
        pessoa = next((p for p in pessoas
                      if str(p.get("papel") or "").upper() == papel), None)
        faltando.append({"papel": papel, "rotulo": rotulo,
                        "nome": (pessoa or {}).get("nome") or ""})
    return faltando


def gravar_na_pessoa(con: sqlite3.Connection, assento_id: int, cpf: Any, *,
                     papel: str) -> str:
    """Atualiza o documento CPF da pessoa daquele papel, se ela existir. ESCREVE.

    **Não inventa pessoa.** Assento sem linha daquele papel não grava nada
    aqui — no nascimento e no óbito ela ainda tem `cpf_registrado` no
    assento, que é o que a certidão e o mutirão leem; no casamento, esta
    chamada é a ÚNICA gravação (não há coluna de assento para um segundo
    CPF), e por isso `papel` é obrigatório e não tem valor padrão.
    """
    n = _digitos(cpf)
    if not valido(n):
        raise CpfError(
            f"O CPF «{cpf}» não fecha o dígito verificador. Confira com quem "
            f"está no balcão — número errado na certidão não se desfaz "
            f"depois.")
    con.execute(
        """UPDATE rc_pessoas
              SET documento_tipo='CPF', documento_numero=?
            WHERE assento_id=? AND UPPER(COALESCE(papel,''))=?""",
        (n, int(assento_id), str(papel).strip().upper()))
    return formatar(n)


def gravar_no_registrado(con: sqlite3.Connection, assento_id: int,
                         cpf: Any) -> str:
    """Atalho de `gravar_na_pessoa(..., papel="REGISTRADO")` — o nascimento.

    FICA PARA NÃO QUEBRAR QUEM JÁ CHAMA: era o único papel que este módulo
    conhecia antes de 09/09/2026. Chamadas novas devem usar
    `gravar_na_pessoa` com o papel certo da espécie — `PRINCIPAIS_DA_ESPECIE`
    diz qual é.
    """
    return gravar_na_pessoa(con, assento_id, cpf, papel="REGISTRADO")


def gravar(con: sqlite3.Connection, assento_id: int, cpf: Any) -> str:
    """Grava o CPF no assento, venha ele de onde vier. ESCREVE.

    **CONFERE ANTES DE GRAVAR.** O número vai para a certidão, e certidão com
    CPF errado é papel que o cliente leva e volta.
    """
    n = _digitos(cpf)
    if not valido(n):
        raise CpfError(
            f"O CPF «{cpf}» não fecha o dígito verificador. Confira com quem "
            f"está no balcão — número errado na certidão não se desfaz "
            f"depois.")
    con.execute("UPDATE rc_assentos SET cpf_registrado=? WHERE id=?",
                (n, int(assento_id)))
    return formatar(n)
