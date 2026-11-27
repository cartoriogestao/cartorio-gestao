"""O WSOficio do ONR — o web service do Ofício Eletrônico (SAEC), por SOAP.

    «coloquei as chaves de api de producao no sistema, vamos fazer funcionar»
    — o oficial, 09/10/2026, com `especificacao_wsoficio_dev.pdf` (v4.43)

NÃO É A API REST DO ONR (`onr_api.py`), E ISSO FOI MEDIDO NO DIA.
    O par gravado em `onr.cred` (produção) foi recusado pela API REST com HTTP
    422 «Parâmetro inválido: client_id e client_secret». E o formato dele é o
    deste serviço, e não o daquele: um número de 4 dígitos e um GUID de 36
    caracteres — o `IDParceiroWS` (tipo int, no contrato) e a chave do hash, que
    o manual manda pedir em oficioeletronico@onr.org.br. Os dois serviços
    convivem: a REST leva o indicador real e o edital; este leva os pedidos do
    Ofício Eletrônico (ofícios, penhora online, certidões, e-Protocolo,
    intimações) e o BDLight, que é o Indicador Pessoal por web service.

COMO SE AUTENTICA (manual, cap. 2 e 3.1)
    1. `LoginUsuarioCertificado` com os dados PÚBLICOS do certificado do usuário
       cadastrado no Ofício Eletrônico (CN do titular, O do emissor, chave
       pública, número de série, validade), o CPF, o e-mail e o `IDParceiroWS`.
       **A chave privada do A3 não entra** — nada de PKCS#11, que dá segfault
       nesta máquina (ver `assinatura_digital.py`).
    2. Ele devolve 5 tokens de 6 caracteres, de uso único, válidos por 8 horas.
    3. Cada chamada leva `Hash = SHA-1(chave + token)`, em UTF-8.
    E o acesso é **restrito por IP** — o IP de saída da casa tem de estar
    cadastrado no ONR junto do `IDParceiroWS`.

MEDIDO EM PRODUÇÃO EM 09/10/2026 (com autorização do oficial, só leitura)
    Login aceito — usuário 827433, instituição 9087, ativo —; ofícios e penhora
    online responderam (0 pedidos nos 30 dias anteriores). **O hash vale em
    MAIÚSCULAS.** **O login devolveu 1 token, e não os 5 do manual** — a sessão
    entra de novo quando acaba, e cada chamada custa um login. E o
    `ListPedidosPO` estoura `NullReferenceException` do lado deles se os dois
    campos de data de resposta não vierem (presentes e vazios resolvem).

O QUE ERA A CONFERIR ANTES DA MEDIÇÃO
    - **A caixa do hash.** O manual não traz exemplo (o campo vem como «...Hash
      obtido na autenticação...»). Começa em MAIÚSCULAS — a forma do
      `FormsAuthentication` do .NET em que o serviço (`.asmx`) foi feito — e,
      se o ONR responder «Hash inválido» (sem «já utilizado» nem «expirado»),
      tenta UMA vez a outra caixa e passa a usar a que valeu.
    - **A forma de cada campo do certificado.** Sem exemplo no manual; vai como
      o .NET lê o certificado no Windows (`GetPublicKeyString`,
      `GetSerialNumberString`, `GetExpirationDateString`). O que confirma a
      leitura: `ISSUERO` é `string(10)` no manual, e «ICP-Brasil» tem 10.

O QUE ESTE MÓDULO FAZ HOJE
    Lê: login, as listas e fichas dos pedidos de ofício e de penhora online, a
    lista dos arquivos do BDLight e — desde 11/10/2026 — as certidões a emitir.
    **Responde só as certidões** (informar custas, anexar, finalizar, devolver),
    por ordem do oficial («faça a da onr certidões»), e só a partir da tela de
    `onr_certidoes_web`, um clique por pedido. Ofício, penhora e e-Protocolo
    continuam só leitura.

    **E, desde 26/10/2026, o ACOMPANHAMENTO DE TÍTULOS** (`acompanhamentotitulos
    .asmx`, manual 4.43, cap. 3.2): o andamento das prenotações do RI que o
    apresentante consulta na Central. Quem decide o que sobe é
    `onr_acompanhamento`, por uma fila de fatos gravados; este módulo só sabe
    falar com o serviço. **O WSDL dele NÃO está na casa** (as pastas
    `homologacao` e `producao` têm os outros oito, e não este): os campos vão
    na ORDEM DO MANUAL — que bateu com o WSDL nos dois métodos em que se pôde
    conferir (`ListPedidosPO` e `FinalizarRespostaCertidao`) —, há teste que
    compara com o texto do manual, e outro que compara com o WSDL no dia em
    que ele for salvo em `FONTES_EXTERNAS/onr_wsoficio/producao`. **A primeira
    chamada em homologação é a prova que falta.**

    **E, desde 25/11/2026 (RI013 B0), O TRANSPORTE INTEIRO DE TRÊS SERVIÇOS**:
    e-Protocolo (`eprotocolo.asmx`, 30 métodos), e-Intimação (`intimacoes.asmx`,
    14) e matrícula online (`matriculaonline.asmx`, 2) estão todos em `CAMPOS`,
    na ordem do WSDL, com as listas, o base64 e as datas que eles pedem. As
    leituras a sessão chama; as escritas só se MONTAM (`pedido_*`, que devolve
    um `Pedido`), e `Sessao.chamar` as recusa enquanto estiverem em
    `ESPERAM_O_PODE_DO_TITULAR` — cada uma espera o «pode» do titular e a
    primeira chamada em homologação. Nenhuma rodada, processo ou tela as chama.

    **O BDLight recebe um LINK, e não o arquivo** (`ImportarArquivoBDL` leva
    `URLArquivo`; até 5 MB) — o ONR vai buscar o XML num endereço. Esta casa
    não tem endereço público, e por isso a importação não foi construída.

A REDE NUNCA ACONTECE DENTRO DE `db.transaction()` — este módulo nem recebe banco.
"""
from __future__ import annotations

import base64
import hashlib
import json
import re
import subprocess
import time
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from datetime import date, datetime
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

import centrais_cred as CRED
import centrais_http as HTTP

NS = "http://tempuri.org/WSOficio"
SOAP = "http://schemas.xmlsoap.org/soap/envelope/"

PRODUCAO = "PRODUCAO"
HOMOLOGACAO = "HOMOLOGACAO"

#: Os dois hosts. Homologação está no manual; produção foi medida em
#: 09/10/2026: os oito `.asmx?wsdl` respondem 200 nos dois, com o
#: `soap:address` apontando para o próprio host.
BASE = {PRODUCAO: "https://wsoficio.onr.org.br",
        HOMOLOGACAO: "https://hml3-wsoficio.onr.org.br"}

#: Os oito serviços, um `.asmx` cada. A grafia (com o «C» maiúsculo de
#: Certidoes) é a do manual e a do servidor.
SERVICOS = {"login": "login.asmx", "bdlight": "bdlight.asmx",
            "oficios": "oficios.asmx", "penhora": "penhoraonline.asmx",
            "certidoes": "Certidoes.asmx", "eprotocolo": "eprotocolo.asmx",
            "matricula": "matriculaonline.asmx", "intimacoes": "intimacoes.asmx",
            # 26/10/2026 — o nome é o do manual (3.2, «acompanhamentotitulos
            # .asmx?wsdl»), todo em minúsculas. NÃO MEDIDO no servidor: o WSDL
            # dele não foi baixado (ver `SEM_WSDL_NA_CASA`).
            "acompanhamento": "acompanhamentotitulos.asmx"}

#: Os serviços cujo WSDL NÃO está em `FONTES_EXTERNAS/onr_wsoficio`. Os
#: testes que abrem o contrato pulam estes — e recusam qualquer outro que falte.
SEM_WSDL_NA_CASA = frozenset({"acompanhamento"})

#: A ORDEM DOS CAMPOS DE CADA PEDIDO, transcrita do WSDL de produção. Em
#: document/literal a `sequence` é posicional: campo fora de ordem o .NET
#: ignora calado. Há teste que abre o WSDL e compara.
CAMPOS = {
    "LoginUsuarioCertificado": ("SUBJECTCN", "ISSUERO", "PUBLICKEY", "SERIALNUMBER",
                                "VALIDUNTIL", "CPF", "EMAIL", "IDParceiroWS"),
    "ListPedidosOE_V2": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo",
                         "IDInstituicao", "IDTipoPesquisa", "IDStatus",
                         "DataSolicitacaoInicial", "DataSolicitacaoFinal",
                         "DataRespostaInicial", "DataRespostaFinal"),
    "GetPedidoOE": ("Hash", "IDPedido"),
    "ListPedidosPO": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo", "IDVara",
                      "IDTipoPedido", "IDStatus", "DataSolicitacaoInicial",
                      "DataSolicitacaoFinal", "DataRespostaInicial",
                      "DataRespostaFinal"),
    "GetPedidoPO": ("Hash", "IDPedido"),
    "ListArquivosXMLBDL": ("Hash", "MaxRowPerPage", "PageNumber", "DataInicial",
                           "DataFinal"),
    # CERTIDÕES A EMITIR (manual 4.43, cap. 3.6, p. 75-90) — 11/10/2026, por
    # ordem do oficial («faça a da onr certidões»). A ordem é a do WSDL de
    # produção (`FONTES_EXTERNAS/onr_wsoficio/producao/Certidoes.wsdl`).
    "ObterXMLSolicitacoes_v6": ("Hash", "Protocolo", "Solicitante", "TipoCertidao",
                                "PesquisaPor", "Status", "TipoResposta", "DataPedidoDe",
                                "DataPedidoAte", "DataConferenciaDe", "DataConferenciaAte"),
    "InformarCustasCertidao": ("Hash", "Protocolo", "ValorCustas"),
    "EnviarAnexoCertidao": ("Hash", "Protocolo", "NomeArquivo", "ArquivoBase64"),
    "EnviarAnexosListCertidao": ("Hash", "Protocolo", "AnexoList"),
    "FinalizarRespostaCertidao": ("Hash", "Protocolo", "Matriculas", "InteresseSocial"),
    "DevolverCertidao": ("Hash", "Protocolo", "Motivo"),
    # ACOMPANHAMENTO DE TÍTULOS (manual 4.43, cap. 3.2, p. 18-29) — 26/10/2026.
    # A ORDEM É A DO MANUAL, porque o WSDL deste serviço não está na casa
    # (`SEM_WSDL_NA_CASA`); `tests/test_onr_acompanhamento.py` relê o manual e
    # compara, e compara com o WSDL quando ele chegar.
    "ListTitulosAT": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo",
                      "DataProtocoloInicio", "DataProtocoloFinal", "IDTipoStatus",
                      "Exportado", "Apresentante"),
    "GetTituloAT": ("Hash", "IDTitulo"),
    "ListStatusAT": ("Hash", "MaxRowPerPage", "PageNumber", "IDTitulo",
                     "DataStatusInicio", "DataStatusFinal", "IDTipoStatus"),
    "GetStatusAT": ("Hash", "IDStatus"),
    "InsertTituloAT": ("Hash", "Protocolo", "ApresentanteNome", "ApresentanteEmail",
                       "ApresentanteDDDTelefone", "ApresentanteNumeroTelefone",
                       "ApresentanteCPFCNPJ", "ValorDeposito", "ValorEmolumentos",
                       "DataProtocolo", "DataPrevisaoEntrega", "ModoNotificacaoStatus",
                       "InteressadoNome", "InteressadoCPFCNPJ", "NaturezaTitulo",
                       "CodigoVerificador", "TipoSolicitacao",
                       "IDTipoStatus", "DataStatus", "DescricaoStatus"),
    "UpdateTituloAT": ("Hash", "IDTitulo", "Protocolo", "ApresentanteNome",
                       "ApresentanteEmail", "ApresentanteDDDTelefone",
                       "ApresentanteNumeroTelefone", "ApresentanteCPFCNPJ",
                       "ValorDeposito", "ValorEmolumentos", "DataProtocolo",
                       "DataPrevisaoEntrega", "ModoNotificacaoStatus", "InteressadoNome",
                       "InteressadoCPFCNPJ", "NaturezaTitulo", "CodigoVerificador",
                       "TipoSolicitacao"),
    "DeleteTituloAT": ("Hash", "IDTitulo"),
    "InsertStatusAT": ("Hash", "IDTitulo", "IDTipoStatus", "DataStatus", "DescricaoStatus"),
    "UpdateStatusAT": ("Hash", "IDStatus", "IDTipoStatus", "DataStatus", "DescricaoStatus"),
    # E-PROTOCOLO DO RI (manual 4.43, cap. 3.10, p. 94-133) — 24/11/2026, RI013
    # P1: SÓ AS LEITURAS. A ordem é a do WSDL de produção
    # (`FONTES_EXTERNAS/onr_wsoficio/producao/eprotocolo.wsdl`, o mesmo arquivo
    # salvo em 09/10/2026 e baixado de novo em 24/11/2026: SHA-256 igual). Os
    # `Set*` (prenotar, custas, exigência, averbado, devolvido) ficam de fora até
    # a P2/P3, com o «pode» do oficial. NÃO É o e-Protocolo do Registro Civil
    # (`eprotocolo.py`, CRC), que é outro produto.
    "ListPedidosAC": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo", "Instituicao",
                      "IDTipoServico", "IDStatus", "DataSolicitacaoInicial",
                      "DataSolicitacaoFinal", "NumeroBanco"),
    "GetPedidoAC_V8": ("Hash", "IDContrato"),
    "ListAnexosAC": ("Hash", "IDContrato"),
    "ListBoletosAC": ("Hash", "IDContrato"),
    "ListCustasAC": ("Hash", "IDContrato"),
    "GetExtratoXMLAC": ("Hash", "Protocolo"),
    # O RESTO DO E-PROTOCOLO — 25/11/2026, RI013 B0 (o transporte). Os 24
    # métodos que faltavam, na ordem do mesmo WSDL. As leituras (`Get*`,
    # `List*` e `ContratoXMLtoPDF`) a sessão já chama; as escritas estão em
    # `ESPERAM_O_PODE_DO_TITULAR` e a sessão as RECUSA (ver lá). O WSDL tem 30
    # métodos, e não 31. ONDE O MANUAL E O WSDL DIVERGEM, VALE O WSDL: o
    # `SetPrenotacaoExameCalculoAC` leva `Senha`, e não `DataVencimento`; os
    # anexos do `SetContratoExigenciaAC` têm `Nome`, e não `Descricao`; e o
    # método do repositório é `ListRepositorioDocumentosAC`, e não
    # `ListDocumentosRepositorioAC`.
    "ContratoXMLtoPDF": ("Hash", "URLArquivo"),
    "SetBaixaBoletoAC": ("Hash", "IDBoleto", "Convenio"),
    "GetPedidoAC": ("Hash", "IDContrato"),
    "GetPedidoAC_V2": ("Hash", "IDContrato"),
    "GetPedidoAC_V3": ("Hash", "IDContrato"),
    "GetPedidoAC_V4": ("Hash", "IDContrato"),
    "GetPedidoAC_V5": ("Hash", "IDContrato"),
    "GetPedidoAC_V6": ("Hash", "IDContrato"),
    "GetPedidoAC_V7": ("Hash", "IDContrato"),
    "AlterarPedidoAC": ("Hash", "IDContrato", "TipoDocumento", "ApresentanteNome",
                        "ApresentanteEmail", "EnderecoVia", "EnderecoLogradouro",
                        "EnderecoNumero", "EnderecoComplemento", "EnderecoBairro", "EnderecoUF",
                        "EnderecoCidade", "EnderecoCEP", "ContatoDDD", "ContatoTelefone"),
    "SetPrenotacaoAC": ("Hash", "IDContrato", "NumeroPrenotacao", "DataPrenotacao",
                        "DataVencimento", "Senha"),
    "SetProrrogarPrenotacaoAC": ("Hash", "IDContrato", "Motivo"),
    "SetCustasAC": ("Hash", "IDContrato", "ValorCustas"),
    "SetCustasComplementarAC": ("Hash", "IDContrato", "ValorCustas"),
    "SetPrenotacaoExameCalculoAC": ("Hash", "IDContrato", "NumeroPrenotacao", "DataPrenotacao",
                                    "Senha"),
    "SetContratoAverbadoAC": ("Hash", "IDContrato", "Resposta", "CertidaoAverbacao"),
    "SetContratoAverbadoAC_DocID": ("Hash", "IDContrato", "Resposta", "CertidaoAverbacao"),
    "SetContratoExigenciaAC": ("Hash", "IDContrato", "ExigenciaFinal", "Resposta", "Anexos"),
    "SetContratoExigenciaAC_DocID": ("Hash", "IDContrato", "ExigenciaFinal", "Resposta",
                                     "Anexos"),
    "SetContratoCumprimentoExigenciaRI": ("Hash", "IDContrato"),
    "SetContratoDevolvidoAC": ("Hash", "IDContrato", "Resposta"),
    "ListRepositorioDocumentosAC": ("Hash", "IDContrato", "IDDepartamento", "CPFVinculado",
                                    "DataVencimentoInicial", "DataVencimentoFinal"),
    "SetFinalizarProtocoloAC": ("Hash", "IDContrato", "Resposta", "Anexos"),
    "SetBaixaCustasAC": ("Hash", "IDCustas"),
    # A E-INTIMAÇÃO (manual 4.43, cap. 3.11, p. 135-154) — 25/11/2026, RI013 B0.
    # Os 14 métodos de `FONTES_EXTERNAS/onr_wsoficio/producao/intimacoes.wsdl`.
    # O `CancelamentoJudicialIN` está no WSDL e não no manual.
    "ImportarPrenotacaoIN": ("Hash", "XMLs"),
    "ListStatusIN": ("Hash",),
    "ListPedidosIN": ("Hash", "MaxRowPerPage", "PageNumber", "IDStatus", "Protocolo",
                      "TipoDataPesquisa", "DataInicial", "DataFinal"),
    "ListMensagensPedidoIN": ("Hash", "MaxRowPerPage", "PageNumber", "IDPedido", "IDStatus",
                              "Assunto", "IDFiltro"),
    "AdicionarMensagemIN": ("Hash", "IDIntimacao", "IDStatus", "Assunto", "Mensagem",
                            "URLAnexos", "NumeroPrenotacao", "DataPrenotacao",
                            "VencimentoPrenotacao", "ValorPrenotacao", "TipoDestinacaoMutuo",
                            "TipoDeterminacaoJudicial", "ValorServico", "DataPagamento",
                            "ValorPagamento"),
    "GetDetalhesIN": ("Hash", "IDPedido"),
    "GetDetalhesIN_V2": ("Hash", "IDPedido"),
    "GetDetalhesIN_V3": ("Hash", "IDPedido"),
    "GetMensagemIN": ("Hash", "IDMensagem"),
    "GetEmolumentosIN": ("Hash", "IDPedido"),
    "AdicionarEmolumentoIN": ("Hash", "IDPedido", "IDStatus", "Descricao", "Valor"),
    "ExcluirEmolumentoIN": ("Hash", "IDEmolumento"),
    "CancelamentoJudicialIN": ("Hash", "IDPedido", "DataAverbacao"),
    "ListPagamentoIN": ("Hash", "MaxRowPerPage", "PageNumber", "Protocolo", "IDStatusPagamento",
                        "IDStatusEmolumentos", "ProtocoloPagamento", "NossoNumero",
                        "DataCustasInicial", "DataCustasFinal", "DataPagamentoInicial",
                        "DataPagamentoFinal"),
    # A MATRÍCULA ONLINE (manual 4.43, cap. 3.9, p. 91-93) — 25/11/2026, RI013
    # B0. Dois métodos, os dois de leitura, com o MESMO tipo de pedido. O «x»
    # minúsculo de `Xml` é do WSDL (as certidões escrevem `XML`).
    "ObterXmlSolicitacoes": ("Hash", "Protocolo", "DataInicial", "DataFinal", "idPedido"),
    "ObterXmlSolicitacoesV2": ("Hash", "Protocolo", "DataInicial", "DataFinal", "idPedido"),
}

#: O tipo do pedido no WSDL quando ele não é `<Metodo>_WSReq`. Medido no WSDL
#: de produção: o `GetPedidoAC_V8` usa `GetPedidoAC_v8_WSReq`, com «v» minúsculo.
#: E há reaproveitamento: o `GetPedidoAC_V6` usa o tipo da v5, o
#: `GetDetalhesIN_V3` o da v2, e as duas da matrícula online o mesmo tipo.
TIPO_DO_PEDIDO_NO_WSDL = {"LoginUsuarioCertificado": "Login_WSReq",
                          "ObterXMLSolicitacoes_v6": "ObterXMLSolicitacoesv2_WSReq",
                          "GetPedidoAC_V3": "GetPedidoAC_v3_WSReq",
                          "GetPedidoAC_V4": "GetPedidoAC_v4_WSReq",
                          "GetPedidoAC_V5": "GetPedidoAC_v5_WSReq",
                          "GetPedidoAC_V6": "GetPedidoAC_v5_WSReq",
                          "GetPedidoAC_V7": "GetPedidoAC_v7_WSReq",
                          "GetPedidoAC_V8": "GetPedidoAC_v8_WSReq",
                          "GetDetalhesIN_V3": "GetDetalhesIN_V2_WSReq",
                          "ListPagamentoIN": "ListPagamentosIN_WSReq",
                          "ObterXmlSolicitacoes": "MatriculaOnline_WSReq",
                          "ObterXmlSolicitacoesV2": "MatriculaOnline_WSReq"}

#: OS MÉTODOS QUE MUDAM COISA NO ONR E AINDA NÃO TÊM O «PODE» DO TITULAR — RI013
#: B0, 25/11/2026. O transporte deles está pronto (campos, listas, base64,
#: datas; testado contra o WSDL), mas **`Sessao.chamar` os recusa**: prenotar,
#: informar custas, responder exigência, averbar, devolver, finalizar e mandar
#: mensagem de intimação mudam o que o banco e o devedor veem na Central, e cada
#: um espera DUAS coisas — o «pode» do titular e a primeira chamada em
#: homologação. A etapa que ganhar as duas (P2, P3, I2, I3) tira o método daqui,
#: no mesmo PR que o chama, e diz no comentário quando e por quem.
ESPERAM_O_PODE_DO_TITULAR = frozenset({
    # e-Protocolo (manual 3.10)
    "SetBaixaBoletoAC", "AlterarPedidoAC", "SetPrenotacaoAC", "SetProrrogarPrenotacaoAC",
    "SetCustasAC", "SetCustasComplementarAC", "SetPrenotacaoExameCalculoAC",
    "SetContratoAverbadoAC", "SetContratoAverbadoAC_DocID", "SetContratoExigenciaAC",
    "SetContratoExigenciaAC_DocID", "SetContratoCumprimentoExigenciaRI",
    "SetContratoDevolvidoAC", "SetFinalizarProtocoloAC", "SetBaixaCustasAC",
    # e-Intimação (manual 3.11)
    "ImportarPrenotacaoIN", "AdicionarMensagemIN", "AdicionarEmolumentoIN",
    "ExcluirEmolumentoIN", "CancelamentoJudicialIN",
})

#: OS CAMPOS QUE SÃO LISTA, POR MÉTODO: (método, campo) → (o nome de cada item,
#: os campos do item na ordem do WSDL). `None` no lugar dos campos é lista de
#: texto puro (`ArrayOfString`, cada item `<string>`). É por método, e não por
#: campo, porque o mesmo nome muda de forma: os `Anexos` da exigência levam
#: `Nome`+`URLArquivo`, os da exigência por DocID `Nome`+`DocumentID`, e os da
#: finalização `NomeArquivo`+`ArquivoBase64`.
LISTAS_DO_METODO = {
    ("SetContratoAverbadoAC", "CertidaoAverbacao"):
        ("SetContratoAverbadoAC_Certidao_WSReq", ("Descricao", "URLArquivo")),
    ("SetContratoAverbadoAC_DocID", "CertidaoAverbacao"):
        ("SetContratoAverbadoAC_DocID_Certidao_WSReq", ("Descricao", "DocumentID")),
    ("SetContratoExigenciaAC", "Anexos"):
        ("SetContratoExigenciaAC_Anexo_WSReq", ("Nome", "URLArquivo")),
    ("SetContratoExigenciaAC_DocID", "Anexos"):
        ("SetContratoExigenciaAC_DocID_Anexo_WSReq", ("Nome", "DocumentID")),
    ("SetFinalizarProtocoloAC", "Anexos"):
        ("SetFinalizarProtocoloAC_Anexo_WSReq", ("NomeArquivo", "ArquivoBase64")),
    ("ImportarPrenotacaoIN", "XMLs"): ("ImportarPrenotacaoIN_XML_WSReq", ("URLXML",)),
    ("AdicionarMensagemIN", "URLAnexos"): ("string", None),
    ("EnviarAnexosListCertidao", "AnexoList"):
        ("AnexoListCertidao_WSReq", ("NomeArquivo", "ArquivoBase64")),
}

#: Campo que leva o arquivo em base64: `bytes` vira base64 aqui; texto vai como veio.
CAMPOS_BASE64 = frozenset({"ArquivoBase64"})

#: AS DATAS. O WSDL diz `string` em todas; o formato é do manual: aaaa-mm-dd no
#: e-Protocolo (3.10), na e-Intimação (3.11) e na matrícula online (erro 13 do
#: 3.9). `date`/`datetime` viram esse texto aqui; texto vai como veio. Só
#: nestes serviços — nos outros o formato não foi conferido, e objeto de data
#: é recusado. Os três da mensagem de intimação levam hora: o manual escreve
#: «aaaa-mm-ddhh:mm:ss», sem nada entre o dia e a hora, o que parece espaço
#: perdido no PDF — vai com espaço, **A CONFERIR na homologação**.
SERVICOS_COM_DATA_ISO = frozenset({"eprotocolo", "intimacoes", "matricula"})
CAMPOS_DE_DATA_COM_HORA = frozenset({("AdicionarMensagemIN", "DataPrenotacao"),
                                     ("AdicionarMensagemIN", "VencimentoPrenotacao"),
                                     ("AdicionarMensagemIN", "DataPagamento")})

#: Os métodos do Acompanhamento de Títulos que MUDAM COISA NO ONR — e que o
#: apresentante vê. Só `onr_acompanhamento` os chama, a partir de uma fila de
#: fatos gravados; nunca uma tela com campo livre.
ESCREVEM_NO_ACOMPANHAMENTO = frozenset({"InsertTituloAT", "UpdateTituloAT", "DeleteTituloAT",
                                        "InsertStatusAT", "UpdateStatusAT"})

#: Os tipos de status do Acompanhamento de Títulos (manual 3.2.1), por extenso
#: como o manual os escreve. -1 («Todos») só vale como filtro.
TIPO_STATUS_AT = {1: "Título com reingresso", 2: "Exame e cálculo cancelado",
                  3: "Título pronto para retirada", 4: "Título prenotado",
                  5: "Exame e cálculo concluído", 6: "Título registrado",
                  7: "Nota de exigência", 8: "Título entregue",
                  9: "Suscitação de dúvida", 10: "Dúvida julgada procedente",
                  11: "Dúvida julgada improcedente", 12: "Exame e cálculo protocolado",
                  13: "Exame e cálculo pronto para a retirada", 14: "Bloqueio de matrículas",
                  15: "Prorrogado o prazo da prenotação",
                  16: "Prorrogado o prazo de entrega e devolução",
                  17: "Prorrogado o prazo da Penhora Online", 18: "Notificação",
                  19: "Prorrogado o prazo da Notificação", 20: "Processamento",
                  21: "Aguardando Pagamento"}
#: Campo que é LISTA no contrato: o nome de cada item e os campos dele, em ordem.
LISTAS = {"AnexoList": ("AnexoListCertidao_WSReq", ("NomeArquivo", "ArquivoBase64"))}
SERVICO_DO_METODO = {
    "LoginUsuarioCertificado": "login",
    "ListPedidosOE_V2": "oficios", "GetPedidoOE": "oficios",
    "ListPedidosPO": "penhora", "GetPedidoPO": "penhora",
    "ListArquivosXMLBDL": "bdlight",
    "ObterXMLSolicitacoes_v6": "certidoes", "InformarCustasCertidao": "certidoes",
    "EnviarAnexoCertidao": "certidoes", "EnviarAnexosListCertidao": "certidoes",
    "FinalizarRespostaCertidao": "certidoes", "DevolverCertidao": "certidoes",
    "ListTitulosAT": "acompanhamento", "GetTituloAT": "acompanhamento",
    "ListStatusAT": "acompanhamento", "GetStatusAT": "acompanhamento",
    "InsertTituloAT": "acompanhamento", "UpdateTituloAT": "acompanhamento",
    "DeleteTituloAT": "acompanhamento", "InsertStatusAT": "acompanhamento",
    "UpdateStatusAT": "acompanhamento",
    "ListPedidosAC": "eprotocolo", "GetPedidoAC_V8": "eprotocolo",
    "ListAnexosAC": "eprotocolo", "ListBoletosAC": "eprotocolo",
    "ListCustasAC": "eprotocolo", "GetExtratoXMLAC": "eprotocolo",
}
# RI013 B0, 25/11/2026: os métodos novos dos três serviços. Cada nome só existe
# num serviço (há teste que confere contra os WSDLs).
SERVICO_DO_METODO.update({m: "eprotocolo" for m in (
    "ContratoXMLtoPDF", "SetBaixaBoletoAC", "GetPedidoAC", "GetPedidoAC_V2", "GetPedidoAC_V3",
    "GetPedidoAC_V4", "GetPedidoAC_V5", "GetPedidoAC_V6", "GetPedidoAC_V7", "AlterarPedidoAC",
    "SetPrenotacaoAC", "SetProrrogarPrenotacaoAC", "SetCustasAC", "SetCustasComplementarAC",
    "SetPrenotacaoExameCalculoAC", "SetContratoAverbadoAC", "SetContratoAverbadoAC_DocID",
    "SetContratoExigenciaAC", "SetContratoExigenciaAC_DocID",
    "SetContratoCumprimentoExigenciaRI", "SetContratoDevolvidoAC",
    "ListRepositorioDocumentosAC", "SetFinalizarProtocoloAC", "SetBaixaCustasAC")})
SERVICO_DO_METODO.update({m: "intimacoes" for m in (
    "ImportarPrenotacaoIN", "ListStatusIN", "ListPedidosIN", "ListMensagensPedidoIN",
    "AdicionarMensagemIN", "GetDetalhesIN", "GetDetalhesIN_V2", "GetDetalhesIN_V3",
    "GetMensagemIN", "GetEmolumentosIN", "AdicionarEmolumentoIN", "ExcluirEmolumentoIN",
    "CancelamentoJudicialIN", "ListPagamentoIN")})
SERVICO_DO_METODO.update({m: "matricula" for m in ("ObterXmlSolicitacoes",
                                                   "ObterXmlSolicitacoesV2")})

#: OS CÓDIGOS DA E-INTIMAÇÃO — só o manual 4.43 os dá (3.11). Os status do
#: PEDIDO vêm do próprio serviço (`ListStatusIN`); estes são os da MENSAGEM que
#: o cartório pode mandar (3.11.15). O 28 (determinação judicial) o manual cita
#: no `TipoDeterminacaoJudicial` e não lista aqui.
STATUS_DA_MENSAGEM_IN = {2: "Devolvido", 3: "Devolvido com exigência", 4: "Prenotado",
                         6: "Boleto de consolidação", 7: "Intimado", 8: "Não intimado",
                         10: "Negativa de pagamento", 12: "Registro / averbação",
                         14: "Pagamento no cartório", 16: "Expedição de intimação",
                         20: "Informação RI", 22: "Boleto intimação edital",
                         23: "Arquivamento por desinteresse",
                         24: "Devolvido por incompetência", 25: "Desistência concluída",
                         29: "Nova projeção"}
#: `IDFiltro` do `ListMensagensPedidoIN` (3.11.7).
FILTRO_DE_MENSAGEM_IN = {1: "Todas", 2: "Não lidas", 3: "Lidas", 4: "Recebidas",
                         5: "Enviadas"}
#: `IDStatus` do `AdicionarEmolumentoIN` (3.11.17).
TIPO_DE_EMOLUMENTO_IN = {1: "Prenotação", 2: "Outros", 3: "Intimação"}
#: `IDStatusPagamento` e `IDStatusEmolumentos` do `ListPagamentoIN` (3.11.21);
#: 0 é «qualquer um» nos dois.
STATUS_DO_PAGAMENTO_IN = {1: "Em aberto", 2: "Em processamento", 3: "Concluído"}
TIPO_DE_CUSTAS_NO_PAGAMENTO_IN = {1: "Prenotação", 2: "Outros", 3: "Intimação",
                                  5: "Boleto de consolidação", 6: "Boleto edital"}
#: `TipoDeterminacaoJudicial` (3.11.15) — só com o status 28.
TIPO_DETERMINACAO_JUDICIAL_IN = {1: "Paralisação do procedimento", 2: "Outros"}
#: `TipoDestinacaoMutuo` (3.11.15) — obrigatório com o status 4 (prenotado).
DESTINACAO_DO_MUTUO_IN = {
    1: "Comércio", 2: "Exportação", 3: "Habitacional — compra de imóvel dado em garantia",
    4: "Habitacional — compra de outro imóvel", 5: "Habitacional — construção — autoconstrução",
    6: "Habitacional — construção — empreendimento", 7: "Habitacional — reforma e ampliação",
    8: "Importação", 9: "Microcrédito", 10: "Não declarada",
    11: "Não habitacional — compra de outro imóvel",
    12: "Não habitacional — construção — autoconstrução",
    13: "Não habitacional — construção — empreendimento",
    14: "Não habitacional — compra de imóvel dado em garantia", 15: "Operações societárias",
    16: "Produção agrícola", 17: "Produção industrial", 18: "Produção pecuária",
    19: "Serviços", 20: "Outras destinações"}
#: Mínimo de linhas por página nas listagens da e-Intimação (erro 12).
MINIMO_POR_PAGINA_INTIMACAO = 10
#: A matrícula online pesquisa no máximo 30 dias de cada vez (erro 13, 3.9).
DIAS_POR_PESQUISA_MATRICULA_ONLINE = 30

#: OS CÓDIGOS DO E-PROTOCOLO DO RI — só o manual 4.43 os dá (o WSDL diz `int`).
#: `IDStatus` (3.10.4 e 3.10.22, p. 98 e 115-116). O 0 só aparece no filtro
#: da listagem (3.10.3, p. 97); 18, 19 e 100 só na saída.
STATUS_EPROTOCOLO = {0: "Não concluído", 1: "Em aberto", 2: "Processando", 3: "Prenotado",
                     4: "Calculado", 5: "Devolvido", 6: "Nota de exigência",
                     7: "Registrado / averbado", 8: "Reaberto — não concluído",
                     9: "Aguardando pagamento", 10: "Pagamento efetivado",
                     18: "Finalizado sem prática do ato", 19: "Cancelamento de prenotação",
                     100: "Prazo suspenso"}
#: `TipoServico` da ficha (3.10.22, p. 116) e `IDTipoServico` do FILTRO da
#: listagem (3.10.3, p. 97). **A SAÍDA da listagem (3.10.4, p. 98) traz outra
#: tabela** (1 Certidão Digital … 5 EProtocolo, 6 Intimação), que parece copiada
#: de outro serviço: a primeira chamada real diz qual vale.
TIPO_SERVICO_EPROTOCOLO = {1: "Registro / averbação", 2: "Exame e cálculo",
                           3: "Requerimento de cancelamento de hipoteca"}
TIPO_SERVICO_NA_LISTA_SEGUNDO_O_MANUAL = {1: "Certidão digital", 2: "Matrícula online",
                                          3: "Consulta eletrônica", 4: "Monitor registral",
                                          5: "EProtocolo", 6: "Intimação"}
#: `TipoDocumento` (p. 116): o manual só dá o 1.
TIPO_DOCUMENTO_EPROTOCOLO = {1: "Escritura pública"}
#: `TipoCobranca`, `TipoIsencao` e `CertidaoInteiroTeor` (p. 117).
TIPO_COBRANCA_EPROTOCOLO = {1: "Integral", 2: "Prefeitura", 3: "Isenção total"}
TIPO_ISENCAO_EPROTOCOLO = {0: "Nenhuma", 1: "Assistência jurídica gratuita"}
#: As listas de anexos de `ListAnexosAC` (3.10.6, p. 99), na ordem do WSDL.
GRUPOS_DE_ANEXO_EPROTOCOLO = {"AnexosContrato": "CONTRATO", "AnexosAverbacao": "AVERBACAO",
                              "AnexosExigencia": "EXIGENCIA"}
#: Mínimo de linhas por página da listagem (erro 12, p. 98).
MINIMO_POR_PAGINA_EPROTOCOLO = 10

#: Os status do pedido de certidão (manual 3.6.5) e os tipos de certidão.
STATUS_CERTIDAO = {1: "Em aberto", 2: "Processando", 3: "Respondido",
                   10: "Informar valor dos emolumentos", 11: "Aguardando pagamento",
                   12: "Cancelado", 13: "Pendente de resposta",
                   23: "Cancelado pelo solicitante"}
TIPO_CERTIDAO = {1: "Propriedade / negativa de propriedade", 2: "Vintenária",
                 3: "Matrícula do imóvel", 4: "Transcrição", 5: "Pacto antenupcial",
                 6: "Ônus", 7: "Documento arquivado", 8: "Convenção de condomínio",
                 9: "Livro 3 — garantias", 10: "Outros registros Livro 3 — auxiliar",
                 11: "Outras certidões", 12: "Inteiro teor, ônus e ações",
                 13: "Por quesito", 14: "Negativa de penhor",
                 15: "Ônus reais e ações reipersecutórias", 16: "Usucapião",
                 17: "Propriedade, ônus e alienações",
                 18: "Cadeia dominial (filiação até a origem)",
                 19: "Ações reipersecutórias", 20: "Ônus reais",
                 21: "Situação jurídica atualizada do imóvel", 22: "Agronegócio"}
PESQUISA_POR = {4: "Matrícula", 5: "Transcrição", 6: "Pessoa", 7: "Número de registro",
                8: "Nome dos pactuantes", 9: "Endereço", 10: "Protocolo",
                11: "Nº do registro do Livro 3", 12: "Nome do condomínio",
                13: "Matrícula com complemento", 14: "Transcrição com complemento",
                15: "Busca de garantias"}
EXTENSOES_ACEITAS_NA_CERTIDAO = (".pdf", ".p7s")   # erro 25 do manual

#: Os status do pedido de penhora (manual 3.3.1). O dos ofícios está no 3.5.4.
STATUS_PENHORA = {1: "Aberto", 2: "Respondido", 3: "Devolvido",
                  5: "Finalizado sem pagamento", 7: "Nota de exigência",
                  8: "Reaberto não concluído", 9: "Prenotado",
                  10: "Aguardando pagamento", 11: "Aguardando pagamento — vencido",
                  12: "Não prenotado", 13: "Pagamento efetivado",
                  14: "Registro / averbação"}
TIPO_PEDIDO_PENHORA = {1: "Pedido de matrícula", 2: "Pedido de pessoa",
                       3: "Pedido de penhora"}

TOKENS_VALEM_SEGUNDOS = 8 * 3600
ARQUIVO_DA_CREDENCIAL = "wsoficio.cred"


class WSOficioError(ValueError):
    """Recusa com a frase pronta para o balcão."""


class WSOficioRecusou(WSOficioError):
    """O ONR respondeu RETORNO=false. Guarda o código e a descrição dele — e a
    resposta inteira, porque há recusa que traz dado: o erro 501 do
    `InsertTituloAT` devolve o `IDTitulo` já cadastrado, e o do
    `InsertStatusAT`, o `IDStatus` (manual 3.2.9 e 3.2.13)."""

    def __init__(self, metodo: str, codigo: Any, descricao: str,
                 resposta: dict | None = None):
        self.metodo, self.codigo, self.descricao = metodo, codigo, descricao
        self.resposta = dict(resposta or {})
        super().__init__(f"O ONR recusou {metodo} (código {codigo}): {descricao}")


# ------------------------------------------------------------ a credencial

def caminho_da_credencial(pasta=None) -> Path:
    """Ao lado das outras credenciais das Centrais, FORA do banco."""
    return CRED.caminho(CRED.ONR, pasta).parent / ARQUIVO_DA_CREDENCIAL


def _ler_cred(pasta=None) -> dict:
    c = caminho_da_credencial(pasta)
    if not c.is_file():
        return {}
    try:
        return json.loads(c.read_text(encoding="utf-8")) or {}
    except (OSError, ValueError):
        return {}


def situacao(ambiente: str = PRODUCAO, pasta=None) -> dict:
    """O que está configurado. **Não devolve a chave.**"""
    d = _ler_cred(pasta).get(ambiente) or {}
    return {"ambiente": ambiente,
            "id_parceiro": str(d.get("usuario") or ""),
            "tem_chave": bool(str(d.get("senha") or "").strip()),
            "cpf": str(d.get("cpf") or ""), "email": str(d.get("email") or ""),
            "certificado": str(d.get("certificado") or "")}


def configurar(*, ambiente: str = PRODUCAO, pasta=None, id_parceiro=None, chave=None,
               cpf=None, email=None, certificado=None, certificado_publico=None) -> Path:
    """Grava o que vier (`None` = não mexe). A chave nunca volta por função."""
    tudo = _ler_cred(pasta)
    d = dict(tudo.get(ambiente) or {})
    for campo, valor in (("usuario", id_parceiro), ("senha", chave), ("cpf", cpf),
                         ("email", email), ("certificado", certificado),
                         ("certificado_publico", certificado_publico)):
        if valor is not None:
            v = str(valor).strip()
            if campo == "cpf":
                v = re.sub(r"\D", "", v)
            d[campo] = v
    tudo[ambiente] = d
    destino = caminho_da_credencial(pasta)
    destino.write_text(json.dumps(tudo, ensure_ascii=False), encoding="utf-8")
    import centrais_cred as _CRED
    _CRED._so_do_servico(destino)          # a ACL na hora (22/10/2026, M6)
    return destino


_GUID = re.compile(r"^[0-9A-Fa-f]{8}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{4}-[0-9A-Fa-f]{12}$")


def par_do_onr_cred_parece_wsoficio(pasta=None) -> bool:
    """O par de produção gravado como «API REST» tem a forma do WSOficio?
    (número inteiro + GUID). Só olha a forma — não devolve nem imprime nada."""
    try:
        d = json.loads(CRED.caminho(CRED.ONR, pasta).read_text(encoding="utf-8"))[PRODUCAO]
    except (OSError, ValueError, KeyError, TypeError):
        return False
    return str(d.get("usuario", "")).isdigit() and bool(_GUID.match(str(d.get("senha", ""))))


def trazer_do_onr_cred(pasta=None) -> bool:
    """Copia o par de produção de `onr.cred` para `wsoficio.cred`, se tiver a
    forma do WSOficio. **Copia, não move**: tirar de lá é decisão do oficial."""
    if not par_do_onr_cred_parece_wsoficio(pasta):
        return False
    d = json.loads(CRED.caminho(CRED.ONR, pasta).read_text(encoding="utf-8"))[PRODUCAO]
    configurar(ambiente=PRODUCAO, pasta=pasta, id_parceiro=d["usuario"], chave=d["senha"])
    return True


# ------------------------------------------------------------- o certificado

def certificados_do_windows(cpf: str = "") -> list[dict]:
    """Os certificados do usuário do Windows, **só a parte pública**, na forma
    em que o .NET os lê. Nada aqui toca a chave privada."""
    ps = (r"Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.NotAfter -gt (Get-Date) } | "
          r"ForEach-Object { [pscustomobject]@{ "
          r"SUBJECTCN=([regex]::Match($_.Subject,'CN=([^,]+)')).Groups[1].Value; "
          r"ISSUERO=([regex]::Match($_.Issuer,'O=([^,]+)')).Groups[1].Value; "
          r"EMISSOR=([regex]::Match($_.Issuer,'CN=([^,]+)')).Groups[1].Value; "
          r"PUBLICKEY=$_.GetPublicKeyString(); SERIALNUMBER=$_.GetSerialNumberString(); "
          r"VALIDUNTIL=$_.GetExpirationDateString(); ASSUNTO=$_.Subject } } | ConvertTo-Json")
    # A FALHA DE FORA VIRA RECUSA LEGÍVEL — 27/10/2026. O PowerShell que passa
    # do prazo ou devolve texto que não é JSON subia cru, e as telas do ONR,
    # que apanham `WSOficioError`, davam HTTP 500 no balcão.
    try:
        r = subprocess.run(["powershell", "-NoProfile", "-Command", ps],
                           capture_output=True, text=True, timeout=60)
        dados = json.loads(r.stdout or "[]")
    except (subprocess.TimeoutExpired, OSError, ValueError) as erro:
        raise WSOficioError(
            "Não foi possível ler os certificados do Windows para entrar no "
            f"Ofício Eletrônico ({type(erro).__name__}). Tente de novo; se "
            "repetir, confira se o certificado está instalado na conta que roda "
            "o servidor.") from erro
    lista = dados if isinstance(dados, list) else [dados]
    cpf = re.sub(r"\D", "", cpf or "")
    return [c for c in lista if not cpf or cpf in (c.get("ASSUNTO") or "")]


def certificado_publico_do_pem(pem: str, cpf: str) -> dict:
    """Le apenas um X.509 publico; nao aceita PFX nem chave privada.

    O servico do Windows pode nao enxergar o repositorio do usuario. O WSOficio
    usa os dados PUBLICOS do certificado no login, sem operacao de assinatura.
    A validade e o CPF sao conferidos tambem em cada login automatizado.
    """
    from datetime import datetime, timezone
    from cryptography import x509
    from cryptography.hazmat.primitives import serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID
    texto = str(pem or "").strip()
    if len(texto) > 32000 or not texto.startswith("-----BEGIN CERTIFICATE-----") or "PRIVATE KEY" in texto:
        raise WSOficioError("Informe somente o certificado publico em formato PEM, sem chave privada.")
    try:
        cert = x509.load_pem_x509_certificate(texto.encode("ascii"))
    except (ValueError, UnicodeError) as exc:
        raise WSOficioError("O certificado publico PEM nao e valido.") from exc
    agora = datetime.now(timezone.utc)
    inicio = (cert.not_valid_before_utc if hasattr(cert, "not_valid_before_utc")
              else cert.not_valid_before.replace(tzinfo=timezone.utc))
    fim = (cert.not_valid_after_utc if hasattr(cert, "not_valid_after_utc")
           else cert.not_valid_after.replace(tzinfo=timezone.utc))
    if not inicio <= agora <= fim:
        raise WSOficioError("O certificado publico esta fora da validade.")
    def atributo(nome, oid):
        valores = nome.get_attributes_for_oid(oid)
        return valores[0].value if valores else ""
    cn = atributo(cert.subject, NameOID.COMMON_NAME)
    documento = re.sub(r"\D", "", cpf or "")
    identificadores = [cn, atributo(cert.subject, NameOID.SERIAL_NUMBER)]
    if len(documento) != 11 or not any(documento in re.sub(r"\D", "", v) for v in identificadores):
        raise WSOficioError("O certificado publico nao pertence ao CPF cadastrado no WSOficio.")
    chave = cert.public_key()
    if not isinstance(chave, rsa.RSAPublicKey):
        raise WSOficioError("Este tipo de chave publica ainda nao e aceito nesta integracao.")
    serie = format(cert.serial_number, "X")
    if len(serie) % 2:
        serie = "0" + serie
    return {"SUBJECTCN": cn, "ISSUERO": atributo(cert.issuer, NameOID.ORGANIZATION_NAME),
            "EMISSOR": atributo(cert.issuer, NameOID.COMMON_NAME),
            "PUBLICKEY": chave.public_bytes(serialization.Encoding.DER,
                                             serialization.PublicFormat.PKCS1).hex().upper(),
            "SERIALNUMBER": serie,
            "VALIDUNTIL": fim.astimezone().strftime("%d/%m/%Y %H:%M:%S")}


def dados_do_login(*, cpf: str, email: str, id_parceiro: Any, certificado: dict) -> dict:
    """Os oito campos do `LoginUsuarioCertificado`, conferidos contra os tamanhos
    do manual antes de ir à rede."""
    campos = {"SUBJECTCN": certificado["SUBJECTCN"], "ISSUERO": certificado["ISSUERO"],
              "PUBLICKEY": certificado["PUBLICKEY"],
              "SERIALNUMBER": certificado["SERIALNUMBER"],
              "VALIDUNTIL": certificado["VALIDUNTIL"],
              "CPF": re.sub(r"\D", "", cpf or ""), "EMAIL": (email or "").strip(),
              "IDParceiroWS": id_parceiro}
    limites = {"SUBJECTCN": 100, "ISSUERO": 10, "PUBLICKEY": 1000, "SERIALNUMBER": 100,
               "CPF": 11, "EMAIL": 100}
    for campo, teto in limites.items():
        if not str(campos[campo] or ""):
            raise WSOficioError(f"Falta o {campo} para entrar no Ofício Eletrônico.")
        if len(str(campos[campo])) > teto:
            raise WSOficioError(f"O {campo} passa do tamanho do manual ({teto}).")
    if len(campos["CPF"]) != 11:
        raise WSOficioError("O CPF do usuário do Ofício Eletrônico precisa de 11 dígitos.")
    if not str(id_parceiro or "").strip().isdigit():
        raise WSOficioError("O IDParceiroWS é um número inteiro, dado pelo ONR.")
    return campos


# ----------------------------------------------------------- o hash e o SOAP

def hash_da_mensagem(chave: str, token: str, *, maiusculas: bool = True) -> str:
    """`SHA-1(chave + token)`, UTF-8 (manual, cap. 2). A caixa é A CONFERIR."""
    h = hashlib.sha1((str(chave) + str(token)).encode("utf-8")).hexdigest()
    return h.upper() if maiusculas else h


def _texto_do_campo(metodo: str, nome: str, valor: Any) -> str:
    """Um valor simples como o .NET o lê (RI013 B0, 25/11/2026).

    `bool` → true/false; `bytes` → base64, só em `CAMPOS_BASE64`; `date` e
    `datetime` → aaaa-mm-dd (com « hh:mm:ss» em `CAMPOS_DE_DATA_COM_HORA`), só
    nos serviços de `SERVICOS_COM_DATA_ISO`; `Decimal` e `float` → ponto e duas
    casas, que é o «XX.XX» do manual; o resto vai como texto."""
    if isinstance(valor, bool):
        return "true" if valor else "false"
    if isinstance(valor, (bytes, bytearray)):
        if nome not in CAMPOS_BASE64:
            raise WSOficioError(f"O campo {nome} de {metodo} não leva arquivo.")
        return base64.b64encode(bytes(valor)).decode("ascii")
    if isinstance(valor, (date, datetime)):
        if SERVICO_DO_METODO.get(metodo) not in SERVICOS_COM_DATA_ISO:
            raise WSOficioError(f"O formato de data de {metodo} não foi conferido: "
                                "passe o texto pronto.")
        if (metodo, nome) in CAMPOS_DE_DATA_COM_HORA:
            if not isinstance(valor, datetime):
                valor = datetime(valor.year, valor.month, valor.day)
            return valor.strftime("%Y-%m-%d %H:%M:%S")
        return valor.strftime("%Y-%m-%d")
    if isinstance(valor, float):
        valor = Decimal(str(valor))
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise WSOficioError(f"O valor de {nome} em {metodo} não é um número.")
        return format(valor.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP), "f")
    if isinstance(valor, (dict, list, tuple, set)):
        raise WSOficioError(f"O campo {nome} de {metodo} não é lista nem tipo composto.")
    return str(valor)


def _lista_do_campo(metodo: str, nome: str):
    """(nome do item, campos do item) se o campo é lista; senão `None`."""
    if (metodo, nome) in LISTAS_DO_METODO:
        return LISTAS_DO_METODO[(metodo, nome)]
    return LISTAS.get(nome)


def envelope(metodo: str, campos: dict) -> bytes:
    """O envelope SOAP 1.1, com os campos NA ORDEM do contrato. Campo que não
    está no contrato é recusado aqui — o .NET o ignoraria calado.

    LISTAS E TIPOS ANINHADOS (RI013 B0, 25/11/2026): campo de
    `LISTAS_DO_METODO` recebe uma lista; cada item é um `dict` com os campos do
    tipo do item (na ordem do WSDL, campo a mais é recusado) ou, na lista de
    texto (`ArrayOfString`), o próprio texto. Item `None` não vai."""
    ordem = CAMPOS[metodo]
    sobra = set(campos) - set(ordem)
    if sobra:
        raise WSOficioError(f"{metodo} não tem o(s) campo(s) {sorted(sobra)}.")
    partes = []
    for nome in ordem:
        if nome not in campos or campos[nome] is None:
            continue
        valor = campos[nome]
        lista = _lista_do_campo(metodo, nome)
        if lista is None:
            partes.append(f"<{nome}>{escape(_texto_do_campo(metodo, nome, valor))}</{nome}>")
            continue
        item, ordem_item = lista
        if isinstance(valor, (str, bytes, dict)) or not hasattr(valor, "__iter__"):
            raise WSOficioError(f"O campo {nome} de {metodo} é uma lista.")
        itens = []
        for d in valor:
            if d is None:
                continue
            if ordem_item is None:
                itens.append(f"<{item}>{escape(_texto_do_campo(metodo, nome, d))}</{item}>")
                continue
            if not isinstance(d, dict):
                raise WSOficioError(f"Cada item de {nome} em {metodo} tem os campos "
                                    f"{', '.join(ordem_item)}.")
            demais = set(d) - set(ordem_item)
            if demais:
                raise WSOficioError(f"O item de {nome} em {metodo} não tem o(s) campo(s) "
                                    f"{sorted(demais)}.")
            filhos = "".join(f"<{c}>{escape(_texto_do_campo(metodo, c, d[c]))}</{c}>"
                             for c in ordem_item if d.get(c) is not None)
            itens.append(f"<{item}>{filhos}</{item}>")
        partes.append(f"<{nome}>" + "".join(itens) + f"</{nome}>")
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP}"><soap:Body>'
            f'<{metodo} xmlns="{NS}"><oRequest>{"".join(partes)}</oRequest></{metodo}>'
            "</soap:Body></soap:Envelope>").encode("utf-8")


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _para_python(el: ET.Element) -> Any:
    filhos = list(el)
    if not filhos:
        texto = (el.text or "").strip()
        return {"true": True, "false": False}.get(texto, texto)
    nomes = [_local(f.tag) for f in filhos]
    if len(set(nomes)) == 1 and (nomes[0] in ("string", "int")
                                 or nomes[0].endswith("_WSResp")
                                 or _local(el.tag).startswith("ArrayOf")
                                 or len(filhos) > 1):
        return [_para_python(f) for f in filhos]
    return {_local(f.tag): _para_python(f) for f in filhos}


def ler_resposta(metodo: str, texto: str) -> dict:
    """O `<Metodo>Result` como dicionário. Fault SOAP vira erro com a frase dele."""
    try:
        raiz = ET.fromstring(texto)
    except ET.ParseError as erro:
        raise WSOficioError(f"O ONR respondeu algo que não é XML: {texto[:200]!r}") from erro
    falha = raiz.find(f".//{{{SOAP}}}Fault")
    if falha is not None:
        msg = falha.findtext("faultstring") or ET.tostring(falha, encoding="unicode")[:300]
        raise WSOficioError(f"O ONR devolveu falha SOAP em {metodo}: {msg}")
    res = raiz.find(f".//{{{NS}}}{metodo}Result")
    if res is None:
        raise WSOficioError(f"A resposta de {metodo} veio sem {metodo}Result.")
    d = _para_python(res)
    return d if isinstance(d, dict) else {"valor": d}


# ------------------------------------------- as respostas da e-Intimação (B0)
#
# `ler_resposta` devolve texto em tudo, e a lista vem em três formas: vazia
# (`<Devedores />` vira ""), com um item (um `dict`, quando o nome do item não
# acaba em `_WSResp`) ou com vários. Os leitores abaixo põem cada lista como
# lista e cada número no tipo do WSDL. Os nomes dos campos são os do WSDL —
# há teste que confere cada um contra o tipo de resposta.

#: Os campos numéricos e booleanos das respostas da e-Intimação, pelo tipo do WSDL.
INTEIROS_IN = frozenset({"IDPedido", "IDStatus", "IDCartorio", "TipoCobranca", "IDCustas",
                         "QtdeRegistros", "QtdePaginas", "CODIGOERRO"})
DECIMAIS_IN = frozenset({"Valor", "ValorServico"})
BOOLEANOS_IN = frozenset({"Pago", "RETORNO"})

#: As listas do `GetDetalhesIN_V3` e os campos de cada item, na ordem do WSDL.
LISTAS_DO_DETALHE_IN = {
    "Prenotacoes": ("Numero", "Data", "DataVencimento", "ValorServico"),
    "Devedores": ("Nome", "Participacao", "CPFCNPJ", "Email"),
    "Imoveis": ("Matricula",),
    "EnderecosIntimacoes": ("NomeDevedor", "EnderecoCompleto"),
    "Reingressos": ("Protocolo", "DataPrenotacao"),
    "Boletos": ("DataVencimento", "Valor", "URL"),
    "PrestacoesVencidas": ("Numero", "DataVencimento", "Valor"),
    "Purgas": ("DataVencimento", "Valor"),
}
#: O solicitante e o credor vêm achatados (`CredorCPFCNPJ`, `CredorCidade` …);
#: o leitor os junta, com estes sufixos («» é o nome).
SUFIXOS_DE_PESSOA_IN = ("", "CPFCNPJ", "IM", "Endereco", "Numero", "Complemento", "Bairro",
                        "Cidade", "Estado", "CEP", "DDD", "Telefone", "Email")
#: Os campos soltos do `GetDetalhesIN_V3`.
CAMPOS_DO_DETALHE_IN = ("IDPedido", "IDStatus", "Protocolo", "Estado", "Cidade", "IDCartorio",
                        "Cartorio", "NumeroContrato", "DataRemessa", "TipoCobranca")
#: Os itens das listagens.
CAMPOS_DO_PEDIDO_IN = ("IDPedido", "Protocolo", "Solicitante", "IDStatus", "DataPedido",
                       "DataStatus")
CAMPOS_DO_PAGAMENTO_IN = ("IDPedido", "IDCustas", "Protocolo", "ProtocoloPagamento",
                          "DataVencimento", "TipoCustas", "NossoNumero", "DescricaoCustas",
                          "Valor", "UsuarioEfetivou", "DataCompensacao", "DataRepasse", "Pago")


def como_lista(valor: Any) -> list:
    """A lista de uma resposta, nas três formas em que ela chega: "" ou
    `None` → []; um item só → [item]; vários → como veio."""
    if valor in (None, ""):
        return []
    if isinstance(valor, list):
        return valor
    if isinstance(valor, dict) and len(valor) == 1:
        (interno,) = valor.values()
        if isinstance(interno, (dict, list)):        # <Lista><Item>…</Item></Lista>
            return como_lista(interno) if isinstance(interno, list) else [interno]
    return [valor]


def _tipado(nome: str, valor: Any) -> Any:
    if valor is None:
        return None
    if nome in BOOLEANOS_IN:
        return valor if isinstance(valor, bool) else str(valor).strip().lower() == "true"
    texto = str(valor).strip()
    if nome in INTEIROS_IN:
        try:
            return int(texto)
        except ValueError:
            return None
    if nome in DECIMAIS_IN:
        try:
            return Decimal(texto.replace(",", ".")) if texto else None
        except InvalidOperation:
            return None
    return texto


def _itens(valor: Any, campos: tuple) -> list[dict]:
    return [{c: _tipado(c, item.get(c)) for c in campos}
            for item in como_lista(valor) if isinstance(item, dict)]


def ler_data_do_onr(texto: Any) -> date | datetime | None:
    """As datas que o ONR devolve, nas formas vistas no manual: aaaa-mm-dd,
    aaaa-mm-dd hh:mm:ss (o manual escreve sem o espaço; aceita as duas e o
    «T»), e dd/mm/aaaa [hh:mm:ss]. O que não for data → `None`."""
    t = str(texto or "").strip()
    m = re.fullmatch(r"(\d{4})-(\d{2})-(\d{2})(?:[ T]?(\d{2}):(\d{2})(?::(\d{2}))?)?(?:\.\d+)?", t)
    if not m:
        m2 = re.fullmatch(r"(\d{2})/(\d{2})/(\d{4})(?: (\d{2}):(\d{2})(?::(\d{2}))?)?", t)
        if not m2:
            return None
        d, mes, a, h, mi, s = m2.groups()
        partes = (a, mes, d, h, mi, s)
    else:
        partes = m.groups()
    a, mes, d, h, mi, s = partes
    try:
        if h is None:
            return date(int(a), int(mes), int(d))
        return datetime(int(a), int(mes), int(d), int(h), int(mi), int(s or 0))
    except ValueError:
        return None


def ler_pedidos_da_intimacao(r: dict) -> dict:
    """`ListPedidosIN` → {qtde_registros, qtde_paginas, pedidos: [...]}."""
    return {"qtde_registros": _tipado("QtdeRegistros", r.get("QtdeRegistros")) or 0,
            "qtde_paginas": _tipado("QtdePaginas", r.get("QtdePaginas")) or 0,
            "pedidos": _itens(r.get("Pedidos"), CAMPOS_DO_PEDIDO_IN)}


def ler_pagamentos_da_intimacao(r: dict) -> dict:
    """`ListPagamentoIN` → {qtde_registros, qtde_paginas, pagamentos: [...]}."""
    return {"qtde_registros": _tipado("QtdeRegistros", r.get("QtdeRegistros")) or 0,
            "qtde_paginas": _tipado("QtdePaginas", r.get("QtdePaginas")) or 0,
            "pagamentos": _itens(r.get("Pagamentos"), CAMPOS_DO_PAGAMENTO_IN)}


def ler_detalhes_da_intimacao(r: dict) -> dict:
    """`GetDetalhesIN_V3` → a ficha do pedido de intimação fiduciária.

    Os campos soltos com o nome do WSDL; `solicitante` e `credor` juntados
    (`{"Nome", "CPFCNPJ", "Cidade", …}`); `prestacao` (agência e endereço de
    pagamento); e as oito listas — prenotações, devedores (com o e-mail, que é
    o que a v3 traz a mais), imóveis, endereços de intimação, reingressos,
    boletos, prestações vencidas e purgas —, sempre como lista."""
    ficha = {c: _tipado(c, r.get(c)) for c in CAMPOS_DO_DETALHE_IN}
    for quem in ("Solicitante", "Credor"):
        ficha[quem.lower()] = {(s or "Nome"): _tipado(s, r.get(quem + s))
                               for s in SUFIXOS_DE_PESSOA_IN}
    ficha["prestacao"] = {"Agencia": _tipado("", r.get("PrestacaoAgencia")),
                          "Endereco": _tipado("", r.get("PrestacaoEndereco"))}
    for lista, campos in LISTAS_DO_DETALHE_IN.items():
        ficha[lista] = _itens(r.get(lista), campos)
    return ficha


# ------------------------------------- as escritas: só montam (RI013 B0, 25/11/2026)
#
# CADA FUNÇÃO ABAIXO SÓ MONTA O PEDIDO. Nenhuma rodada, processo, botão ou tela
# as chama, e `Sessao.chamar` recusa os métodos delas enquanto estiverem em
# `ESPERAM_O_PODE_DO_TITULAR`. Cada uma precisa, antes de ir à rede, do «pode»
# do titular e da primeira chamada em homologação; é a etapa que as usar (P2 a
# prenotação, P3 o retorno do andamento, I2/I3 a e-Intimação) que liga.

@dataclass(frozen=True)
class Pedido:
    """Um pedido montado e ainda não enviado: o método e os campos, sem o Hash."""
    metodo: str
    campos: dict

    def envelope(self, hash_: str = "") -> bytes:
        return envelope(self.metodo, dict(self.campos, Hash=hash_))


def _pedido(metodo: str, **campos) -> Pedido:
    envelope(metodo, dict(campos, Hash=""))          # recusa campo errado já aqui
    return Pedido(metodo, campos)


def _anexos(anexos, chaves: tuple[str, str], nomes_aceitos: tuple[str, str]) -> list[dict]:
    """Aceita a lista com as chaves do WSDL ou com as nossas (`nome`, `url` …)."""
    saida = []
    for a in anexos or ():
        a = dict(a)
        item = {}
        for wsdl, nosso in zip(chaves, nomes_aceitos):
            item[wsdl] = a.pop(wsdl, None) if wsdl in a else a.pop(nosso, None)
        if a:
            raise WSOficioError(f"O anexo não tem o(s) campo(s) {sorted(a)}.")
        saida.append(item)
    return saida


# -- e-Protocolo (manual 3.10). Todas precisam do «pode» do titular e de homologação.

def pedido_prenotacao_ac(id_contrato: int, *, numero: str, data: date | str,
                         vencimento: date | str, senha: str | None = None) -> Pedido:
    """`SetPrenotacaoAC` — informa ao ONR o número e o prazo da prenotação (P2).
    Precisa do «pode» do titular (a prenotação automática) e de homologação."""
    return _pedido("SetPrenotacaoAC", IDContrato=int(id_contrato), NumeroPrenotacao=str(numero),
                   DataPrenotacao=data, DataVencimento=vencimento, Senha=senha)


def pedido_prenotacao_exame_calculo_ac(id_contrato: int, *, numero: str, data: date | str,
                                       senha: str | None = None) -> Pedido:
    """`SetPrenotacaoExameCalculoAC` — a prenotação do exame e cálculo. O WSDL
    leva `Senha`, e não o `DataVencimento` do manual. Precisa do «pode» e de
    homologação."""
    return _pedido("SetPrenotacaoExameCalculoAC", IDContrato=int(id_contrato),
                   NumeroPrenotacao=str(numero), DataPrenotacao=data, Senha=senha)


def pedido_prorrogar_prenotacao_ac(id_contrato: int, *, motivo: str) -> Pedido:
    """`SetProrrogarPrenotacaoAC`. Precisa do «pode» do titular e de homologação."""
    return _pedido("SetProrrogarPrenotacaoAC", IDContrato=int(id_contrato), Motivo=motivo)


def pedido_custas_ac(id_contrato: int, valor: Decimal | str, *,
                     complementar: bool = False) -> Pedido:
    """`SetCustasAC` (ou `SetCustasComplementarAC`) — o valor dos emolumentos;
    é o que gera o boleto do apresentante. Precisa do «pode» (o selo «pago na
    Central») e de homologação."""
    return _pedido("SetCustasComplementarAC" if complementar else "SetCustasAC",
                   IDContrato=int(id_contrato), ValorCustas=Decimal(str(valor)))


def pedido_exigencia_ac(id_contrato: int, *, resposta: str, anexos=(), final: bool = False,
                        por_document_id: bool = False) -> Pedido:
    """`SetContratoExigenciaAC` (anexos por URL que o ONR vai buscar) ou
    `SetContratoExigenciaAC_DocID` (anexos já no AssinadorWeb). Cada anexo:
    `{"Nome", "URLArquivo"}` ou `{"Nome", "DocumentID"}` (ou `nome`/`url`/
    `document_id`). Precisa do «pode», de homologação e — por URL — do repasse
    de arquivo na VPS, porque esta casa não tem endereço público."""
    if por_document_id:
        itens = _anexos(anexos, ("Nome", "DocumentID"), ("nome", "document_id"))
        metodo = "SetContratoExigenciaAC_DocID"
    else:
        itens = _anexos(anexos, ("Nome", "URLArquivo"), ("nome", "url"))
        metodo = "SetContratoExigenciaAC"
    return _pedido(metodo, IDContrato=int(id_contrato), ExigenciaFinal=bool(final),
                   Resposta=resposta, Anexos=itens or None)


def pedido_cumprimento_exigencia_ri(id_contrato: int) -> Pedido:
    """`SetContratoCumprimentoExigenciaRI`. Precisa do «pode» e de homologação."""
    return _pedido("SetContratoCumprimentoExigenciaRI", IDContrato=int(id_contrato))


def pedido_averbado_ac(id_contrato: int, *, resposta: str, certidoes=(),
                       por_document_id: bool = False) -> Pedido:
    """`SetContratoAverbadoAC` (certidões por URL) ou `_DocID`. Cada certidão:
    `{"Descricao", "URLArquivo"}` ou `{"Descricao", "DocumentID"}`; a do XML de
    retorno vai com a descrição «XMLRETORNO» (manual 3.10.35). Precisa do
    «pode», de homologação e — por URL — do repasse de arquivo na VPS."""
    if por_document_id:
        itens = _anexos(certidoes, ("Descricao", "DocumentID"), ("descricao", "document_id"))
        metodo = "SetContratoAverbadoAC_DocID"
    else:
        itens = _anexos(certidoes, ("Descricao", "URLArquivo"), ("descricao", "url"))
        metodo = "SetContratoAverbadoAC"
    return _pedido(metodo, IDContrato=int(id_contrato), Resposta=resposta,
                   CertidaoAverbacao=itens or None)


def pedido_devolvido_ac(id_contrato: int, *, resposta: str) -> Pedido:
    """`SetContratoDevolvidoAC`. Precisa do «pode» do titular e de homologação."""
    return _pedido("SetContratoDevolvidoAC", IDContrato=int(id_contrato), Resposta=resposta)


def pedido_finalizar_protocolo_ac(id_contrato: int, *, resposta: str = "",
                                  anexos=()) -> Pedido:
    """`SetFinalizarProtocoloAC` — o único do e-Protocolo que leva o ARQUIVO,
    em base64, e não uma URL. Cada anexo: `{"NomeArquivo", "ArquivoBase64"}`
    (ou `nome`/`conteudo`); `bytes` viram base64 no envelope. Precisa do «pode»
    do titular e de homologação."""
    itens = _anexos(anexos, ("NomeArquivo", "ArquivoBase64"), ("nome", "conteudo"))
    for a in itens:
        if not a.get("NomeArquivo") or not a.get("ArquivoBase64"):
            raise WSOficioError("Cada anexo da finalização tem nome e conteúdo.")
    return _pedido("SetFinalizarProtocoloAC", IDContrato=int(id_contrato),
                   Resposta=resposta or None, Anexos=itens or None)


def pedido_baixa_boleto_ac(id_boleto: int, *, convenio: bool) -> Pedido:
    """`SetBaixaBoletoAC`. Precisa do «pode» do titular e de homologação."""
    return _pedido("SetBaixaBoletoAC", IDBoleto=int(id_boleto), Convenio=bool(convenio))


def pedido_baixa_custas_ac(id_custas: int) -> Pedido:
    """`SetBaixaCustasAC`. Precisa do «pode» do titular e de homologação."""
    return _pedido("SetBaixaCustasAC", IDCustas=int(id_custas))


def pedido_alterar_ac(id_contrato: int, **campos) -> Pedido:
    """`AlterarPedidoAC` — o apresentante e o endereço dele, com os nomes do
    WSDL. Os três inteiros obrigatórios vão 0 se não vierem (o que o .NET
    leria). Precisa do «pode» do titular e de homologação."""
    for obrigatorio in ("TipoDocumento", "EnderecoNumero", "EnderecoCEP"):
        campos.setdefault(obrigatorio, 0)
    return _pedido("AlterarPedidoAC", IDContrato=int(id_contrato), **campos)


# -- e-Intimação (manual 3.11). Todas precisam do «pode» do titular e de homologação.

def pedido_importar_prenotacao_in(urls_xml) -> Pedido:
    """`ImportarPrenotacaoIN` — a lista de URLs de XML que o ONR vai buscar.
    Precisa do «pode», de homologação e do repasse de arquivo na VPS."""
    itens = [{"URLXML": str(u)} for u in urls_xml or () if u]
    if not itens:
        raise WSOficioError("Nenhum XML para importar (erro 12 do manual).")
    return _pedido("ImportarPrenotacaoIN", XMLs=itens)


def pedido_mensagem_in(id_intimacao: int, *, status: int, assunto: str, mensagem: str,
                       urls_anexos=(), numero_prenotacao: str | None = None,
                       data_prenotacao: date | datetime | str | None = None,
                       vencimento_prenotacao: date | datetime | str | None = None,
                       valor_prenotacao: Decimal | str | None = None,
                       destinacao_mutuo: int = 0, determinacao_judicial: int = 0,
                       valor_servico: Decimal | str | None = None,
                       data_pagamento: date | datetime | str | None = None,
                       valor_pagamento: Decimal | str | None = None) -> Pedido:
    """`AdicionarMensagemIN` — o andamento da intimação (prenotado, intimado,
    não intimado, boleto …; `STATUS_DA_MENSAGEM_IN`). Os dois inteiros
    obrigatórios no WSDL vão 0 quando o status não os pede. Os anexos são URLs
    (`ArrayOfString`). Precisa do «pode» do titular, de homologação e — com
    anexo — do repasse de arquivo na VPS."""
    if int(status) not in STATUS_DA_MENSAGEM_IN and int(status) != 28:
        raise WSOficioError(f"O status {status} não é dos que o cartório manda (3.11.15).")
    if int(status) == 4 and not (numero_prenotacao and data_prenotacao and vencimento_prenotacao
                                 and valor_prenotacao is not None and destinacao_mutuo):
        raise WSOficioError("Com o status 4 (prenotado) o ONR pede número, data, vencimento "
                            "e valor da prenotação e a destinação do mútuo.")

    def dinheiro(v):
        return None if v is None else Decimal(str(v))
    return _pedido("AdicionarMensagemIN", IDIntimacao=int(id_intimacao), IDStatus=int(status),
                   Assunto=assunto, Mensagem=mensagem,
                   URLAnexos=[str(u) for u in urls_anexos or () if u] or None,
                   NumeroPrenotacao=numero_prenotacao, DataPrenotacao=data_prenotacao,
                   VencimentoPrenotacao=vencimento_prenotacao,
                   ValorPrenotacao=dinheiro(valor_prenotacao),
                   TipoDestinacaoMutuo=int(destinacao_mutuo),
                   TipoDeterminacaoJudicial=int(determinacao_judicial),
                   ValorServico=dinheiro(valor_servico), DataPagamento=data_pagamento,
                   ValorPagamento=dinheiro(valor_pagamento))


def pedido_emolumento_in(id_pedido: int, *, tipo: int, descricao: str,
                         valor: Decimal | str) -> Pedido:
    """`AdicionarEmolumentoIN` (tipo: `TIPO_DE_EMOLUMENTO_IN`). Precisa do
    «pode» do titular e de homologação."""
    if int(tipo) not in TIPO_DE_EMOLUMENTO_IN:
        raise WSOficioError(f"O tipo de emolumento {tipo} não existe (3.11.17).")
    return _pedido("AdicionarEmolumentoIN", IDPedido=int(id_pedido), IDStatus=int(tipo),
                   Descricao=descricao, Valor=Decimal(str(valor)))


def pedido_excluir_emolumento_in(id_emolumento: int) -> Pedido:
    """`ExcluirEmolumentoIN`. Precisa do «pode» do titular e de homologação."""
    return _pedido("ExcluirEmolumentoIN", IDEmolumento=int(id_emolumento))


def pedido_cancelamento_judicial_in(id_pedido: int, *, data_averbacao: date | str) -> Pedido:
    """`CancelamentoJudicialIN` — está no WSDL e não no manual; a data vai em
    aaaa-mm-dd, como no resto do serviço (A CONFERIR). Precisa do «pode» do
    titular e de homologação."""
    return _pedido("CancelamentoJudicialIN", IDPedido=int(id_pedido),
                   DataAverbacao=data_averbacao)


# --------------------------------------------------------------- a sessão

class Sessao:
    """Uma conversa com o WSOficio: um login, cinco tokens, e o hash de cada chamada.

    `transporte(url, corpo, soap_action) -> (status, texto)` existe para os
    testes; na casa é `centrais_http.requisitar`.
    """

    def __init__(self, *, ambiente: str = PRODUCAO, pasta=None, transporte=None,
                 certificado: dict | None = None, agora=time.time):
        if ambiente not in BASE:
            raise WSOficioError(f"O WSOficio não tem ambiente «{ambiente}».")
        cred = _ler_cred(pasta).get(ambiente) or {}
        if not str(cred.get("usuario") or "").strip() or not str(cred.get("senha") or "").strip():
            raise WSOficioError(
                "Falta a credencial do WSOficio (IDParceiroWS e chave) em "
                f"{caminho_da_credencial(pasta).name}. Ela é pedida ao ONR em "
                "oficioeletronico@onr.org.br.")
        if not cred.get("cpf") or not cred.get("email"):
            raise WSOficioError(
                "Falta dizer qual usuário do Ofício Eletrônico entra: o CPF e o e-mail "
                "com que ele está cadastrado lá.")
        self.ambiente, self._cred, self._agora = ambiente, cred, agora
        self._transporte = transporte or _transporte_da_casa
        self._certificado = certificado
        self._tokens: list[str] = []
        self._tokens_em = 0.0
        self.maiusculas: bool | None = cred.get("hash_maiusculas")
        self.usuario: dict = {}

    # -- rede
    def _bater(self, metodo: str, campos: dict) -> dict:
        servico = SERVICOS[SERVICO_DO_METODO[metodo]]
        url = f"{BASE[self.ambiente]}/{servico}"
        status, texto = self._transporte(url, envelope(metodo, campos), f"{NS}/{metodo}")
        if status >= 500 and "Fault" not in (texto or ""):
            raise WSOficioError(f"O WSOficio respondeu HTTP {status} em {metodo}.")
        return ler_resposta(metodo, texto)

    # -- login
    def entrar(self) -> dict:
        cert = self._certificado
        if cert is None and self._cred.get("certificado_publico"):
            publico = certificado_publico_do_pem(self._cred["certificado_publico"], self._cred["cpf"])
            if publico["SERIALNUMBER"] != (self._cred.get("certificado") or "").upper():
                raise WSOficioError("A serie selecionada nao corresponde ao certificado publico guardado.")
            cert = publico
        if cert is None:
            serie = (self._cred.get("certificado") or "").upper()
            opcoes = certificados_do_windows(self._cred["cpf"])
            if serie:
                opcoes = [c for c in opcoes if (c.get("SERIALNUMBER") or "").upper() == serie]
            if not opcoes:
                raise WSOficioError(
                    "Não achei, no Windows deste usuário, um certificado válido do CPF "
                    f"{self._cred['cpf']}" + (f" com a série {serie}" if serie else "") + ".")
            cert = opcoes[0]
        campos = dados_do_login(cpf=self._cred["cpf"], email=self._cred["email"],
                                id_parceiro=self._cred["usuario"], certificado=cert)
        r = self._bater("LoginUsuarioCertificado", campos)
        if r.get("RETORNO") is not True:
            raise WSOficioRecusou("LoginUsuarioCertificado", r.get("CODIGOERRO"),
                                  r.get("ERRODESCRICAO") or "")
        tokens = r.get("Tokens") or []
        self._tokens = list(tokens) if isinstance(tokens, list) else [tokens]
        self._tokens_em = self._agora()
        self.usuario = {k: r.get(k) for k in ("IDUsuario", "IDInstituicao", "Ativo")}
        return dict(self.usuario, tokens=len(self._tokens))

    def _token(self) -> str:
        if not self._tokens or self._agora() - self._tokens_em > TOKENS_VALEM_SEGUNDOS - 300:
            self.entrar()
        if not self._tokens:
            raise WSOficioError("O login do WSOficio não devolveu token.")
        return self._tokens.pop(0)

    def chamar(self, metodo: str, **campos) -> dict:
        """Uma chamada com hash. «Hash inválido» puro (nem usado, nem vencido)
        na primeira vez faz UMA tentativa com a outra caixa — ver o cabeçalho.

        O MÉTODO QUE ESPERA O «PODE» DO TITULAR NÃO SAI (RI013 B0): a recusa
        vem antes do login, e nada vai à rede."""
        if metodo in ESPERAM_O_PODE_DO_TITULAR:
            raise WSOficioError(
                f"{metodo} muda o pedido no ONR e ainda espera o «pode» do titular e a "
                "primeira chamada em homologação. Nada foi enviado.")
        tentativas = [self.maiusculas] if self.maiusculas is not None else [True, False]
        ultimo = None
        for maiusculas in tentativas:
            h = hash_da_mensagem(self._cred["senha"], self._token(), maiusculas=maiusculas)
            r = self._bater(metodo, dict(campos, Hash=h))
            if r.get("RETORNO") is True:
                self.maiusculas = maiusculas
                return r
            ultimo = WSOficioRecusou(metodo, r.get("CODIGOERRO"), r.get("ERRODESCRICAO") or "",
                                     resposta=r)
            descr = (r.get("ERRODESCRICAO") or "").strip().rstrip(".").lower()
            if descr != "hash inválido":
                break
        raise ultimo

    # -- as leituras
    def pedidos_de_oficio(self, *, de: str, ate: str, status: int = -1,
                          pagina: int = 1, por_pagina: int = 100) -> dict:
        return self.chamar("ListPedidosOE_V2", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           Protocolo="", IDInstituicao=-1, IDTipoPesquisa=-1, IDStatus=status,
                           DataSolicitacaoInicial=de, DataSolicitacaoFinal=ate,
                           DataRespostaInicial="", DataRespostaFinal="")

    def pedido_de_oficio(self, id_pedido: int) -> dict:
        return self.chamar("GetPedidoOE", IDPedido=int(id_pedido))

    def pedidos_de_penhora(self, *, de: str, ate: str, status: int = -1, tipo: int = -1,
                           pagina: int = 1, por_pagina: int = 100) -> dict:
        return self.chamar("ListPedidosPO", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           Protocolo="", IDVara=-1, IDTipoPedido=tipo, IDStatus=status,
                           DataSolicitacaoInicial=de, DataSolicitacaoFinal=ate,
                           # MEDIDO EM PRODUÇÃO, 09/10/2026: sem os dois campos de
                           # resposta o serviço estoura NullReferenceException
                           # (PenhoraOnline.asmx.vb:178). Vão presentes e vazios.
                           DataRespostaInicial="", DataRespostaFinal="")

    def pedido_de_penhora(self, id_pedido: int) -> dict:
        return self.chamar("GetPedidoPO", IDPedido=int(id_pedido))

    def arquivos_do_bdlight(self, *, de: str = "", ate: str = "", pagina: int = 1,
                            por_pagina: int = 100) -> dict:
        return self.chamar("ListArquivosXMLBDL", MaxRowPerPage=por_pagina, PageNumber=pagina,
                           DataInicial=de, DataFinal=ate)


    # -- as certidões a emitir (manual 3.6). As quatro últimas MUDAM COISA NO ONR:
    #    quem as chama é a tela, um clique por pedido, e nunca um laço.
    def certidoes_a_emitir(self, *, status: Any = "", protocolo: str = "",
                           de: str = "", ate: str = "") -> dict:
        """O XML do «Certidões a Emitir / Exportar». Código 200 do ONR
        («não foram localizados registros») vira lista vazia, e não erro."""
        try:
            return self.chamar("ObterXMLSolicitacoes_v6", Protocolo=protocolo,
                               Solicitante="", TipoCertidao="", PesquisaPor="",
                               Status=str(status or ""), TipoResposta="",
                               DataPedidoDe=de, DataPedidoAte=ate,
                               DataConferenciaDe="", DataConferenciaAte="")
        except WSOficioRecusou as e:
            if str(e.codigo) == "200":
                return {"RETORNO": True, "XML": "", "vazio": True}
            raise

    def informar_custas_da_certidao(self, protocolo: str, valor: Any) -> dict:
        return self.chamar("InformarCustasCertidao", Protocolo=str(protocolo),
                           ValorCustas=str(valor))

    def enviar_anexos_da_certidao(self, protocolo: str, anexos: list[dict]) -> dict:
        """`anexos`: [{NomeArquivo, ArquivoBase64}], só .pdf ou .p7s."""
        if not anexos:
            raise WSOficioError("Nenhum anexo para enviar.")
        for a in anexos:
            if not str(a.get("NomeArquivo") or "").lower().endswith(EXTENSOES_ACEITAS_NA_CERTIDAO):
                raise WSOficioError("O ONR só aceita anexo .pdf ou .p7s na certidão.")
            if not a.get("ArquivoBase64"):
                raise WSOficioError(f"O anexo {a.get('NomeArquivo')} está vazio.")
        if len(anexos) == 1:
            return self.chamar("EnviarAnexoCertidao", Protocolo=str(protocolo),
                               NomeArquivo=anexos[0]["NomeArquivo"],
                               ArquivoBase64=anexos[0]["ArquivoBase64"])
        return self.chamar("EnviarAnexosListCertidao", Protocolo=str(protocolo),
                           AnexoList=anexos)

    def finalizar_certidao(self, protocolo: str, *, interesse_social: bool,
                           matriculas: str = "") -> dict:
        return self.chamar("FinalizarRespostaCertidao", Protocolo=str(protocolo),
                           Matriculas=matriculas or None,
                           InteresseSocial=bool(interesse_social))

    def devolver_certidao(self, protocolo: str, motivo: str) -> dict:
        return self.chamar("DevolverCertidao", Protocolo=str(protocolo), Motivo=motivo)

    # -- o acompanhamento de títulos (manual 3.2). As leituras servem a tela de
    #    conferência; as escritas, só `onr_acompanhamento.enviar_pendentes`,
    #    que manda o que está na fila de fatos gravados — nunca texto da tela.
    def titulos_no_acompanhamento(self, *, de: str, ate: str, protocolo: str = "",
                                  tipo_status: int = -1, pagina: int = 1,
                                  por_pagina: int = 50) -> dict:
        """`ListTitulosAT`. As duas datas são obrigatórias (erros 14 e 15) e o
        mínimo por página é 10 (erro 12)."""
        return self.chamar("ListTitulosAT", MaxRowPerPage=max(10, int(por_pagina)),
                           PageNumber=int(pagina), Protocolo=str(protocolo or ""),
                           DataProtocoloInicio=de, DataProtocoloFinal=ate,
                           IDTipoStatus=int(tipo_status), Exportado=-1, Apresentante="")

    def status_no_acompanhamento(self, id_titulo: int, *, pagina: int = 1,
                                 por_pagina: int = 50) -> dict:
        """`ListStatusAT` de um título: o que o ONR mostra hoje ao apresentante."""
        return self.chamar("ListStatusAT", MaxRowPerPage=max(10, int(por_pagina)),
                           PageNumber=int(pagina), IDTitulo=int(id_titulo),
                           DataStatusInicio="", DataStatusFinal="", IDTipoStatus=-1)

    def cadastrar_titulo_no_acompanhamento(self, campos: dict) -> dict:
        """`InsertTituloAT` — o título com o status inicial. `campos` vem
        pronto de `onr_acompanhamento.campos_do_titulo`."""
        return self.chamar("InsertTituloAT", **campos)

    def cadastrar_status_no_acompanhamento(self, id_titulo: int, *, tipo_status: int,
                                           data_status: str, descricao: str) -> dict:
        """`InsertStatusAT`. A descrição é obrigatória aqui (erro 17)."""
        return self.chamar("InsertStatusAT", IDTitulo=int(id_titulo),
                           IDTipoStatus=int(tipo_status), DataStatus=data_status,
                           DescricaoStatus=descricao)

    # -- o e-Protocolo do RI (manual 3.10). SÓ LEITURA (RI013 P1, 24/11/2026):
    #    quem chama é `onr_eprotocolo`, que grava o que chegou. Nada aqui
    #    prenota, informa custas nem responde.
    def pedidos_do_eprotocolo(self, *, de: str = "", ate: str = "", status: int = -1,
                              tipo_servico: int = -1, protocolo: str = "",
                              pagina: int = 1, por_pagina: int = 50) -> dict:
        """`ListPedidosAC`. Datas em aaaa-mm-dd (erros 16 e 17); mínimo de 10
        por página (erro 12). O «-1 = todos» do `IDTipoServico` e do
        `NumeroBanco` é o que o manual diz do status e do banco — A CONFERIR na
        primeira chamada para o tipo de serviço."""
        return self.chamar("ListPedidosAC",
                           MaxRowPerPage=max(MINIMO_POR_PAGINA_EPROTOCOLO, int(por_pagina)),
                           PageNumber=int(pagina), Protocolo=str(protocolo or ""),
                           Instituicao="", IDTipoServico=int(tipo_servico),
                           IDStatus=int(status), DataSolicitacaoInicial=de,
                           DataSolicitacaoFinal=ate, NumeroBanco=-1)

    def pedido_do_eprotocolo(self, id_contrato: int) -> dict:
        """`GetPedidoAC_V8` — a ficha inteira do contrato."""
        return self.chamar("GetPedidoAC_V8", IDContrato=int(id_contrato))

    def anexos_do_eprotocolo(self, id_contrato: int) -> dict:
        """`ListAnexosAC` — os anexos de contrato, de averbação e de exigência,
        cada um com a URL. Baixar o arquivo NÃO é desta etapa."""
        return self.chamar("ListAnexosAC", IDContrato=int(id_contrato))

    def boletos_do_eprotocolo(self, id_contrato: int) -> dict:
        """`ListBoletosAC` — os boletos do contrato (para a P3, a baixa no caixa)."""
        return self.chamar("ListBoletosAC", IDContrato=int(id_contrato))

    def custas_do_eprotocolo(self, id_contrato: int) -> dict:
        """`ListCustasAC` — as custas informadas e o status delas."""
        return self.chamar("ListCustasAC", IDContrato=int(id_contrato))

    def extrato_do_eprotocolo(self, protocolo: str) -> dict:
        """`GetExtratoXMLAC` — a URL do extrato XML (Prov. 228/2026, CNN 210-C)."""
        return self.chamar("GetExtratoXMLAC", Protocolo=str(protocolo))

    def repositorio_do_eprotocolo(self, id_contrato: int, *, departamento: int = 0,
                                  cpf: str = "", vencimento_de: date | str = "",
                                  vencimento_ate: date | str = "") -> dict:
        """`ListRepositorioDocumentosAC` — os documentos do repositório ligados
        ao contrato (os filtros são opcionais no manual; o departamento é `int`
        obrigatório no WSDL e vai 0 quando não se filtra — A CONFERIR)."""
        return self.chamar("ListRepositorioDocumentosAC", IDContrato=int(id_contrato),
                           IDDepartamento=int(departamento), CPFVinculado=cpf or None,
                           DataVencimentoInicial=vencimento_de or None,
                           DataVencimentoFinal=vencimento_ate or None)

    # -- a e-Intimação (manual 3.11). SÓ AS LEITURAS (RI013 B0, 25/11/2026);
    #    quem vai chamá-las é a I2. As escritas estão em `ESPERAM_O_PODE_DO_TITULAR`.
    def status_da_intimacao(self) -> list[dict]:
        """`ListStatusIN` — a tabela de status de pedido, que só o serviço tem."""
        r = self.chamar("ListStatusIN")
        return [{"IDStatus": _tipado("IDStatus", s.get("IDStatus")),
                 "NomeStatus": _tipado("", s.get("NomeStatus"))}
                for s in como_lista(r.get("Status")) if isinstance(s, dict)]

    def pedidos_da_intimacao(self, *, de: date | str = "", ate: date | str = "",
                             status: int = 0, protocolo: str = "",
                             por_mensagem: bool = False, pagina: int = 1,
                             por_pagina: int = 50) -> dict:
        """`ListPedidosIN`, já lido (`ler_pedidos_da_intimacao`). Status 0 é
        «todos»; as datas são as do cadastro do pedido («P») ou, com
        `por_mensagem`, as da última mensagem («M»)."""
        r = self.chamar("ListPedidosIN",
                        MaxRowPerPage=max(MINIMO_POR_PAGINA_INTIMACAO, int(por_pagina)),
                        PageNumber=int(pagina), IDStatus=int(status),
                        Protocolo=str(protocolo or ""),
                        TipoDataPesquisa="M" if por_mensagem else "P",
                        DataInicial=de or "", DataFinal=ate or "")
        return ler_pedidos_da_intimacao(r)

    def detalhes_da_intimacao(self, id_pedido: int) -> dict:
        """`GetDetalhesIN_V3`, já lido (`ler_detalhes_da_intimacao`)."""
        return ler_detalhes_da_intimacao(self.chamar("GetDetalhesIN_V3", IDPedido=int(id_pedido)))

    def mensagens_da_intimacao(self, id_pedido: int, *, status: int = 0, filtro: int = 1,
                               pagina: int = 1, por_pagina: int = 50) -> dict:
        """`ListMensagensPedidoIN` (filtro: `FILTRO_DE_MENSAGEM_IN`)."""
        return self.chamar("ListMensagensPedidoIN",
                           MaxRowPerPage=max(MINIMO_POR_PAGINA_INTIMACAO, int(por_pagina)),
                           PageNumber=int(pagina), IDPedido=int(id_pedido),
                           IDStatus=int(status), Assunto="", IDFiltro=int(filtro))

    def mensagem_da_intimacao(self, id_mensagem: int) -> dict:
        """`GetMensagemIN`."""
        return self.chamar("GetMensagemIN", IDMensagem=int(id_mensagem))

    def emolumentos_da_intimacao(self, id_pedido: int) -> dict:
        """`GetEmolumentosIN`."""
        return self.chamar("GetEmolumentosIN", IDPedido=int(id_pedido))

    def pagamentos_da_intimacao(self, *, custas_de: date | str = "", custas_ate: date | str = "",
                                pago_de: date | str = "", pago_ate: date | str = "",
                                protocolo: str = "", status_pagamento: int = 0,
                                tipo_custas: int = 0, pagina: int = 1,
                                por_pagina: int = 50) -> dict:
        """`ListPagamentoIN`, já lido (`ler_pagamentos_da_intimacao`). Zero é
        «qualquer um» nos dois status."""
        r = self.chamar("ListPagamentoIN",
                        MaxRowPerPage=max(MINIMO_POR_PAGINA_INTIMACAO, int(por_pagina)),
                        PageNumber=int(pagina), Protocolo=str(protocolo or ""),
                        IDStatusPagamento=int(status_pagamento),
                        IDStatusEmolumentos=int(tipo_custas), ProtocoloPagamento="",
                        NossoNumero="", DataCustasInicial=custas_de or "",
                        DataCustasFinal=custas_ate or "", DataPagamentoInicial=pago_de or "",
                        DataPagamentoFinal=pago_ate or "")
        return ler_pagamentos_da_intimacao(r)

    # -- a matrícula online (manual 3.9). Só leitura (RI013 B0); quem vai chamar é a C2.
    def solicitacoes_da_matricula_online(self, *, de: date | str, ate: date | str,
                                         protocolo: str = "", id_pedido: str = "") -> dict:
        """`ObterXmlSolicitacoesV2` — o XML dos pedidos de visualização de
        matrícula. No máximo 30 dias por vez (erro 13); o código 14 do ONR («não
        foram encontrados resultados») vira lista vazia, e não erro."""
        d1 = de if isinstance(de, date) else ler_data_do_onr(de)
        d2 = ate if isinstance(ate, date) else ler_data_do_onr(ate)
        if not isinstance(d1, date) or not isinstance(d2, date):
            raise WSOficioError("A matrícula online pede as duas datas, em aaaa-mm-dd.")
        if isinstance(d1, datetime):
            d1 = d1.date()
        if isinstance(d2, datetime):
            d2 = d2.date()
        if not 0 <= (d2 - d1).days <= DIAS_POR_PESQUISA_MATRICULA_ONLINE:
            raise WSOficioError("A matrícula online pesquisa no máximo 30 dias de cada vez.")
        try:
            return self.chamar("ObterXmlSolicitacoesV2", Protocolo=str(protocolo or ""),
                               DataInicial=d1, DataFinal=d2, idPedido=str(id_pedido or ""))
        except WSOficioRecusou as e:
            if str(e.codigo) == "14":
                return {"RETORNO": True, "Xml": "", "vazio": True}
            raise


def _transporte_da_casa(url: str, corpo: bytes, acao: str) -> tuple[int, str]:
    # Rede fora do ar ou prazo esgotado: `CentralHttpError` é `RuntimeError`, e
    # quem chama só apanha `WSOficioError` — o balcão levava HTTP 500, e a
    # rodada do robô parava antes de assinar e enviar (27/10/2026).
    try:
        r = HTTP.requisitar("POST", url, corpo=corpo, cabecalhos={
            "Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{acao}"',
            "Accept": "text/xml"}, prazo=60, tentativas=0)
    except HTTP.CentralHttpError as erro:
        raise WSOficioError(
            f"O Ofício Eletrônico do ONR não respondeu: {erro}. Nada foi "
            f"gravado; tente de novo em alguns minutos.") from erro
    return r.status, r.texto


def main(argv=None) -> int:
    """Para o oficial rodar à mão: `python onr_wsoficio.py --testar`.

    Só entra e lista o que chegou nos últimos 30 dias — não responde nada."""
    import argparse
    import sys
    from datetime import date, timedelta
    ap = argparse.ArgumentParser(description="WSOficio do ONR — só leitura.")
    ap.add_argument("--testar", action="store_true", help="entra e lista os pedidos")
    ap.add_argument("--ambiente", default=PRODUCAO, choices=sorted(BASE))
    ap.add_argument("--cpf")
    ap.add_argument("--email")
    ap.add_argument("--certificado", help="número de série do certificado a usar")
    ap.add_argument("--trazer-do-onr-cred", action="store_true",
                    help="copia o par IDParceiroWS/chave gravado como «ONR» em produção")
    a = ap.parse_args(argv)
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:                                   # noqa: BLE001
        pass
    if a.trazer_do_onr_cred:
        print("par copiado de onr.cred:", trazer_do_onr_cred())
    if a.cpf or a.email or a.certificado:
        configurar(ambiente=a.ambiente, cpf=a.cpf, email=a.email, certificado=a.certificado)
    print("situação:", situacao(a.ambiente))
    if not a.testar:
        return 0
    s = Sessao(ambiente=a.ambiente)
    print("login:", s.entrar())
    hoje = date.today()
    de = (hoje - timedelta(days=30)).isoformat()
    for nome, f in (("ofícios", s.pedidos_de_oficio), ("penhora online", s.pedidos_de_penhora)):
        r = f(de=de, ate=hoje.isoformat())
        print(f"{nome}: {r.get('QtdeRegistros')} pedido(s) desde {de}")
    if s.maiusculas is not None:
        configurar(ambiente=a.ambiente, certificado=None)
        tudo = _ler_cred()
        tudo.setdefault(a.ambiente, {})["hash_maiusculas"] = s.maiusculas
        caminho_da_credencial().write_text(json.dumps(tudo, ensure_ascii=False),
                                           encoding="utf-8")
        import centrais_cred as _CRED
        _CRED._so_do_servico(caminho_da_credencial())
        print("hash em", "MAIÚSCULAS" if s.maiusculas else "minúsculas", "(gravado)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
