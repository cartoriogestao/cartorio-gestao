"""O registro único da navegação do layout novo. Só calcula: não lê banco nem tela.

POR QUE UM REGISTRO
    O menu de `base.html` tem mais de mil linhas de condição, e dele não dá para
    tirar o botão Novo, a busca, as migalhas nem as subabas: cada um seria uma
    segunda lista, e lista escrita à mão noutro arquivo envelhece na tarde em que
    se escreve. Aqui cada entrada diz endereço, rótulo, módulo, seção e papéis, e
    tudo o que a tela mostra sai daqui.

    É A MESMA LÓGICA DE `modulos.py`: regra que serve a vários lugares não mora em
    template. E `tests/test_navegacao_registro.py` compara, papel por papel, este
    registro com o menu antigo: **nenhum destino pode se perder na troca**.

O QUE ELE NÃO FAZ
    Não recusa ninguém. Quem tranca a porta é o `roles_required` da rota; aqui só
    se deixa de oferecer o que aquela pessoa não pode fazer.
"""
from __future__ import annotations

import unicodedata
from typing import Any, Callable

from modulos import POR_CHAVE, clarear, modulo_da_tela

TODOS: tuple[str, ...] | None = None
AMU = ("ADMIN", "MANAGER", "USER")
AM = ("ADMIN", "MANAGER")
AMA = ("ADMIN", "MANAGER", "AUDITOR")
A = ("ADMIN",)
AA = ("ADMIN", "AUDITOR")
QUATRO = ("ADMIN", "MANAGER", "USER", "AUDITOR")
SEM_GESTAO = ("USER", "AUDITOR")

# O desenho de cada ícone: traço próprio, 24 x 24, sem nada de fora.
ICONES: dict[str, str] = {
    "casa": '<path d="M3 11.5 12 4l9 7.5"/><path d="M5.5 10v9.5h13V10"/><path d="M10 19.5v-5.5h4v5.5"/>',
    "pena": '<path d="M20 4c-7 .5-12 4.5-13.5 11L5 20l5-1.5C16.5 17 19.5 11 20 4Z"/><path d="M5 20 13 11"/>',
    "predio": '<path d="M4 20.5h16"/><path d="M6 20.5V6.5L13 3.5v17"/><path d="M13 9.5l5 2v9"/><path d="M9 8.5h1M9 12h1M9 15.5h1"/>',
    "pessoas": '<circle cx="9" cy="8" r="3.2"/><path d="M3.5 19.5c.5-3.6 2.7-5.5 5.5-5.5s5 1.9 5.5 5.5"/><circle cx="17" cy="9.5" r="2.4"/><path d="M16.5 14.2c2.3.2 3.7 1.8 4 4.3"/>',
    "martelo": '<path d="m13.5 4.5 6 6"/><path d="m11 7 6 6"/><path d="m9.5 8.5 5.5 5.5"/><path d="m11.5 11.5-7.5 7.5"/><path d="M13 20.5h8"/>',
    "maleta": '<rect x="3.5" y="8" width="17" height="11.5" rx="2"/><path d="M9 8V6a1.5 1.5 0 0 1 1.5-1.5h3A1.5 1.5 0 0 1 15 6v2"/><path d="M3.5 13h17"/>',
    "caixa": '<rect x="3.5" y="6" width="17" height="12.5" rx="2"/><path d="M3.5 10h17"/><path d="M7 15h3"/>',
    "balao": '<path d="M4 6.5A2.5 2.5 0 0 1 6.5 4h11A2.5 2.5 0 0 1 20 6.5v7a2.5 2.5 0 0 1-2.5 2.5H10l-4.5 4v-4A2.5 2.5 0 0 1 4 13.5Z"/>',
    "pasta": '<path d="M3.5 7A2 2 0 0 1 5.5 5h4l2 2.5h7a2 2 0 0 1 2 2V17a2 2 0 0 1-2 2h-13a2 2 0 0 1-2-2Z"/>',
    "livro": '<path d="M5 5.5A1.5 1.5 0 0 1 6.5 4H19v14H6.5A1.5 1.5 0 0 0 5 19.5Z"/><path d="M5 19.5A1.5 1.5 0 0 0 6.5 21H19v-3"/>',
    "selo": '<circle cx="12" cy="10" r="6"/><path d="M8.5 15 7 21l5-2.5L17 21l-1.5-6"/>',
    "escudo": '<path d="M12 3.5 19.5 6v5.5c0 4.5-3 7.8-7.5 9-4.5-1.2-7.5-4.5-7.5-9V6Z"/><path d="m9 12 2.2 2.2L15.5 10"/>',
    "mais": '<path d="M12 5v14M5 12h14"/>',
    "busca": '<circle cx="11" cy="11" r="6.5"/><path d="m16 16 4.5 4.5"/>',
    "sino": '<path d="M6 16.5V11a6 6 0 1 1 12 0v5.5l1.5 2h-15Z"/><path d="M10 21h4"/>',
    "desce": '<path d="m6 9 6 6 6-6"/>',
    "alerta": '<path d="M12 4 2.8 20h18.4Z"/><path d="M12 10v4.5M12 17.3v.2"/>',
}


def _i(rotulo: str, endpoint: str, papeis: tuple[str, ...] | None = TODOS, *,
       quando: str = "", antigo: str = "", termos: str = "", **args: Any) -> dict:
    """Uma entrada. `antigo` é o nome no menu de hoje: a busca acha pelos dois."""
    return {"rotulo": rotulo, "endpoint": endpoint, "papeis": papeis, "quando": quando,
            "antigo": antigo, "termos": termos, "args": args}


# A ORDEM DOS MÓDULOS É A DO MOVIMENTO, medido em selos de 90 dias: Registro Civil
# (429) antes de Protesto (43). `grupo` é o título de seção dentro do módulo, usado
# só na Gestão, que tem catorze seções.
MODULOS_DA_BARRA: tuple[dict, ...] = (
    {"chave": "INICIO", "curto": "Início", "nome": "Início", "cor": "", "icone": "casa",
     "lavra": False, "secoes": ()},
    {"chave": "NOTAS", "curto": "Notas", "nome": "Tabelionato de Notas", "cor": "NOTAS",
     "icone": "pena", "lavra": True, "secoes": (
         ("Painel do dia", (
             _i("Painel do tabelionato", "notas_painel"),)),
         ("Balcão", (
             # O RECONHECIMENTO VEM PRIMEIRO PORQUE É METADE DA CASA, medido em selos.
             _i("Reconhecer firma", "notas_reconhecimento", termos="assinatura firma"),
             _i("Autenticar cópia", "notas_autenticacao", termos="autenticacao xerox copia"),
             _i("Certidões", "notas_certidoes"),
             _i("Pública forma", "notas_publica_forma"),
             _i("Venda de veículo", "notas_veiculos", antigo="Comunicação de venda de veículo",
                termos="detran carro moto"),
             _i("Reconhecer sinal", "notas_sinal_reconhecimento", termos="sinal publico"),)),
         ("Procurações", (
             _i("Procurações", "notas_atos", tipo="PROCURACAO", termos="mandato outorga procurador lavrar"),
             _i("Fins previdenciários", "notas_atos", tipo="PROCURACAO_PREVIDENCIARIA", termos="inss procuracao"),
             _i("Substabelecimentos", "notas_atos", tipo="SUBSTABELECIMENTO", termos="procuracao"),
             _i("Revogações", "notas_atos", tipo="REVOGACAO", termos="cancelar procuracao revogar"),
             _i("Renúncias", "notas_atos", tipo="RENUNCIA", termos="procuracao renunciar"),
             _i("Todos os atos de livro", "notas_atos", antigo="Atos de livro"),)),
         ("Escrituras", (
             _i("Escrituras públicas", "notas_escrituras", termos="compra venda doacao"),
             _i("Pendências das escrituras", "notas_escrituras_pendentes", termos="doi"),)),
         ("Atas notariais", (
             _i("Atas notariais", "notas_atas"),)),
         ("Testamentos", (
             _i("Testamentos públicos", "notas_atos", tipo="TESTAMENTO"),
             _i("Testamentos cerrados", "notas_atos", tipo="TESTAMENTO_CERRADO"),)),
         ("Cartões de autógrafo", (
             _i("Cartões de autógrafo", "notas_cartoes", termos="ficha firma assinatura"),
             _i("Sinais públicos", "notas_sinais"),)),
         ("Centrais", (
             _i("Remessa às centrais", "notas_remessas", termos="censec cep cesdi"),
             _i("Cadastro no CCN", "notas_ccn", AM),
             _i("Consulta ao CCN", "notas_ccn_consultas"),)),
         ("Livros e modelos", (
             _i("Livros do tabelionato", "notas_livros", AM),
             _i("Modelos dos documentos", "notas_modelos_papeis", AMU, antigo="Modelos dos documentos das Notas"),
             _i("Ajustar etiqueta", "notas_etiqueta_ajuste", AM),)),
     )},
    {"chave": "RI", "curto": "Registro de Imóveis", "nome": "Registro de Imóveis", "cor": "RI",
     "icone": "predio", "lavra": True, "secoes": (
         ("Protocolo", (
             _i("Protocolo / prenotação", "ri_protocolo", termos="prenotar titulo exigencia"),
             _i("Pedidos em andamento", "ri_pedidos"),)),
         ("Matrículas", (
             _i("Matrículas", "ri_matriculas", termos="ficha imovel"),)),
         ("Certidões", (
             _i("Certidões", "ri_certidoes", termos="certidao imovel inteiro teor"),
             _i("ONR: certidões a emitir", "onr_certidoes", AMU, antigo="ONR — certidões a emitir"),
             _i("ONR: acompanhamento de títulos", "onr_acompanhamento", QUATRO, antigo="ONR — acompanhamento de títulos"),)),
         ("Para revisar", (
             _i("Rascunhos de ato", "ri_rascunhos"),
             _i("O que revisar antes de selar", "ri_revisoes"),
             _i("Numeração dentro do teor", "ri_numeracao_no_teor"),)),
         ("Processos longos", (
             _i("Usucapião extrajudicial", "usucapiao_processos"),
             _i("Retificação de área", "ri_retificacoes"),
             _i("O que o Código de Normas exige", "usucapiao_codigo_de_normas", antigo="Usucapião — o que o Código de Normas exige"),)),
         ("Livro 3", (
             _i("Registros", "livro3_registros", antigo="Registros do Livro 3", termos="registro auxiliar"),
             _i("Minutas a revisar", "livro3_minutas", antigo="Livro 3 — minutas a revisar"),
             _i("O que revisar antes de selar", "livro3_revisoes", antigo="Livro 3 — o que revisar antes de selar"),
             _i("O que falta conferir", "livro3_por_conferir", antigo="Livro 3 — o que falta conferir"),
             _i("Certidões", "atribuicoes_certidoes", atribuicao="LIVRO3", antigo="Certidões do Livro 3"),
             _i("Modelos", "livro3_modelos", antigo="Livro 3 — modelos (ficha e certidão)"),)),
         ("Consulta", (
             _i("Indicador Real", "ri_indicador_real"),
             _i("Indicador Pessoal", "ri_indicador_pessoal"),)),
         ("Centrais e obrigações", (
             _i("DOI", "ri_doi", AMA, antigo="DOI — Receita Federal", termos="receita federal declaracao"),
             _i("CTP", "ri_ctp", AMA, antigo="CTP — prefeituras", termos="prefeitura sefin"),
             _i("ONR: índice real e editais", "ri_onr_painel", antigo="ONR — índice real e editais"),
             _i("ONR: endereços a conferir", "ri_onr_enderecos", AMU, antigo="ONR — endereços a conferir"),
             _i("Exportação ONR", "ri_onr", AM),
             _i("Carga do Next Cloud SAS", "ri_onr_next_cloud", AM),
             _i("CNIB", "ri_cnib", antigo="CNIB — indisponibilidade", termos="indisponibilidade"),
             _i("CNIB: o que espera seu okay", "ri_cnib_pendentes", antigo="CNIB — o que espera seu okay"),
             _i("CNIB: a cópia local e a Central", "cnib_central", antigo="CNIB — a cópia local e a Central"),
             _i("Selos e emolumentos", "ri_selos", AMA),)),
         ("Acervo e modelos", (
             _i("Fichas digitalizadas", "ri_resolver_imagens", AM),
             _i("Transcrições em lote (IA)", "ri_transcricoes_lote", AM, antigo="Revisar transcrições em lote (IA)"),
             _i("Matrículas em Word", "ri_matriculas_doc", AMU),
             _i("Atas de ocorrência", "ri_expurgos", AMA),
             _i("Modelos de atos", "ri_modelos_atos"),
             _i("Modelos de documento do RI", "modelos", AMU, atribuicao="Registro de Imóveis"),
             _i("Modelos dos documentos", "ri_modelos_papeis", AMU, antigo="Modelos dos documentos do RI"),
             _i("Delegatários", "ri_delegatarios", AM),
             _i("Numeração das matrículas", "ri_numeracao", AM),)),
     )},
    {"chave": "RCPN", "curto": "Registro Civil Naturais", "nome": "Registro Civil das Pessoas Naturais",
     "cor": "RCPN", "icone": "pessoas", "lavra": True, "secoes": (
         ("Balcão", (
             _i("Assentos", "rcpn_assentos"),
             _i("Importar pré-cadastros", "rcpn_importar"),)),
         ("Nascimento", (
             _i("Novo registro", "rcpn_assento_novo", especie_url="nascimento", antigo="Novo registro de nascimento"),
             _i("Digitar já lavrado", "rcpn_assento_novo", especie_url="nascimento", do_acervo=1, antigo="Digitar nascimento já lavrado"),
             _i("Teores", "rcpn_formulario", chave="NASCIMENTO", antigo="Teores do nascimento"),
             _i("Registro tardio", "rcpn_registro_tardio"),
             _i("Gêmeos", "rcpn_gemeos"),
             _i("CPF do registrado", "rcpn_cpf"),)),
         ("Casamento", (
             _i("1 · Habilitação", "rcpn_habilitacoes", termos="casamento proclamas"),
             _i("2 · Edital de proclamas", "rcpn_habilitacoes", situacao="EDITAL_PUBLICADO"),
             _i("2b · Enviar ao e-Proclamas", "rcpn_proclamas"),
             _i("3 · Prontas para casar", "rcpn_habilitacoes", situacao="HABILITADO"),
             _i("Registro do casamento", "rcpn_assento_novo", especie_url="casamento"),
             _i("Digitar já lavrado", "rcpn_assento_novo", especie_url="casamento", do_acervo=1, antigo="Digitar casamento já lavrado"),
             _i("Teores", "rcpn_formulario", chave="CASAMENTO", antigo="Teores do casamento"),)),
         ("Óbito", (
             _i("Novo registro", "rcpn_assento_novo", especie_url="obito", antigo="Novo registro de óbito"),
             _i("Digitar já lavrado", "rcpn_assento_novo", especie_url="obito", do_acervo=1, antigo="Digitar óbito já lavrado"),
             _i("Teores", "rcpn_formulario", chave="OBITO", antigo="Teores do óbito"),
             _i("Comunicações mensais", "rcpn_comunicacoes"),
             _i("O que falta perguntar", "rcpn_marcas_do_obito"),)),
         ("Certidões", (
             _i("Certidões", "rcpn_certidoes", termos="segunda via certidao civil"),
             _i("Pedidos da Central", "rcpn_pedidos"),
             _i("Materializar de outra serventia", "rcpn_materializacoes", antigo="Materializar certidão de outra serventia"),
             _i("Folhas de segurança", "rcpn_papel"),)),
         ("Assento lavrado", (
             _i("Averbações", "rcpn_averbacoes", termos="divorcio"),
             _i("Retificação e suprimento", "rcpn_retificacoes"),
             _i("Atos sem checklist", "rcpn_checklist_pendente"),
             _i("Termos a escrever", "rcpn_termos_a_escrever"),
             _i("Termos a digitalizar", "rcpn_termos_a_digitalizar"),
             _i("Informações importadas", "rcpn_informacoes_importadas"),
             _i("CPF nos assentos antigos", "rcpn_dados_cadastrais"),
             _i("Matrículas", "rcpn_matriculas"),
             _i("Conferência da filiação", "rcpn_filiacao"),)),
         ("Comunicações", (
             _i("O que comunicar hoje", "rcpn_painel"),
             _i("Remessa do SIRC", "rcpn_sirc"),
             _i("Comunicação à FUNAI", "rcpn_funai"),
             _i("Carga da CRC", "rcpn_crc"),
             _i("Anotações devidas", "rcpn_anotacoes"),
             _i("Anotação da CRC", "rcpn_anotacao_crc"),
             _i("Remessa do IBGE", "rcpn_ibge"),)),
         ("Modelos", (
             _i("Documentos avulsos", "rcpn_modelos", antigo="Documentos avulsos (modelos do sistema antigo)"),
             _i("Papéis da casa", "rcpn_modelos_papeis", AMU, antigo="Modelos dos documentos (papéis da casa)"),)),
     )},
    {"chave": "PROTESTO", "curto": "Protesto", "nome": "Protesto", "cor": "PROTESTO",
     "icone": "martelo", "lavra": True, "escondivel": "PROTESTO", "secoes": (
         ("Roteiro do dia", (
             _i("O roteiro das Centrais", "protesto_painel"),)),
         ("Títulos", (
             _i("Títulos", "protesto_titulos"),)),
         ("Dia da CRA", (
             _i("Remessa", "protesto_remessas", antigo="Remessa da CRA"),
             _i("Imagens dos títulos", "protesto_imagens"),
             _i("Avisos e editais", "protesto_avisos"),
             _i("AR digital", "protesto_ar", antigo="AR digital (Correios)"),
             _i("Desistências", "protesto_desistencias"),
             _i("Pedidos da CRA", "protesto_cra_pedidos"),
             _i("A protestar", "protesto_a_protestar"),
             _i("Retorno", "protesto_retornos", antigo="Retorno à CRA"),
             _i("Falar pela API", "protesto_cra_api", AMU, antigo="CRA — falar pela API"),)),
         ("Dia da CENPROT", (
             _i("Pendências", "protesto_pendencias", antigo="Pendências da CENPROT"),
             _i("Intimação Digital", "protesto_resolve"),
             _i("Chave", "protesto_cenprot", antigo="Chave do CENPROT"),
             _i("Conferência", "protesto_cenprot_conferencia", antigo="Conferência CENPROT × sistema"),)),
         ("Balcão", (
             _i("Certidões", "protesto_certidoes"),
             _i("Instrumentos", "protesto_instrumentos"),
             _i("Devedores", "protesto_devedores"),
             _i("Boletos", "protesto_boletos"),)),
         ("Livros e repasses", (
             _i("Livro de Pagamentos", "protesto_livro", qual="pagamentos"),
             _i("Livro de Protocolo", "protesto_livro", qual="protocolo"),
             _i("Repasses ao apresentante", "protesto_repasses", AMU),
             _i("Certidão diária em relação", "protesto_relacao_diaria", AMU),)),
         ("Modelos e decisões", (
             _i("Modelos dos documentos", "protesto_modelos_papeis", AMU, antigo="Modelos dos documentos do Protesto"),
             _i("Afirmações expressas", "protesto_afirmacoes", A),
             _i("Correções de ofício", "correcoes_de_oficio_lista", A, atribuicao="PROTESTO", antigo="Correções de ofício do Protesto"),)),
     )},
    {"chave": "RCPJ", "curto": "RCPJ e RTD", "nome": "RCPJ e RTD: Pessoas Jurídicas, Títulos e Documentos",
     "cor": "RCPJ_RTD", "icone": "maleta", "lavra": True, "secoes": (
         ("Títulos apresentados", (
             _i("RTD", "rcpj_rtd_titulos", atribuicao=4, antigo="RTD — títulos apresentados"),
             _i("RCPJ", "rcpj_rtd_titulos", atribuicao=3, antigo="RCPJ — títulos apresentados"),)),
         ("Registros lavrados", (
             _i("RCPJ", "rcpj_rtd_registros", atribuicao=3, antigo="RCPJ — registros lavrados"),
             _i("RTD", "rcpj_rtd_registros", atribuicao=4, antigo="RTD — registros lavrados"),
             _i("Últimos atos praticados", "rcpj_rtd_ultimos_atos"),)),
         ("Notificações", (
             _i("Notificações extrajudiciais", "rcpj_rtd_notificacoes", antigo="RTD — notificações extrajudiciais"),)),
         ("Livros contábeis", (
             _i("Autenticação de livros", "rcpj_rtd_livro_contabil_lista", antigo="RCPJ — autenticação de livros"),)),
         ("Central ONRTDPJ", (
             _i("A fila de lá", "rcpj_rtd_onrtdpj", AMU, antigo="Central ONRTDPJ — a fila de lá"),)),
         ("Certidões", (
             _i("Certidões de inteiro teor", "atribuicoes_certidoes"),)),
         ("Etiquetas e modelos", (
             _i("Etiquetas de selos externos", "rcpj_rtd_etiquetas_selos_externos", AMU),
             _i("Ajustar a etiqueta de registro", "rcpj_rtd_etiqueta_ajuste", AM),
             _i("Modelos dos documentos", "rcpj_rtd_modelos_papeis", AMU, antigo="Modelos dos documentos do RCPJ"),)),
     )},
    {"chave": "CAIXA", "curto": "Caixa e Protocolo", "nome": "Caixa e Protocolo", "cor": "ADM",
     "icone": "caixa", "lavra": False, "secoes": (
         ("Caixa do dia", (
             _i("Caixa", "caixa"),)),
         ("Protocolo geral", (
             _i("Protocolo geral", "caixa_protocolos"),
             _i("Protocolos parados", "caixa_protocolos_parados"),)),
         ("Depósito prévio", (
             _i("Depósito prévio", "caixa_depositos"),)),
         ("Recibos e NFS-e", (
             _i("Recibos", "caixa_recibos", AMA),
             _i("NFS-e", "nfse_fila", termos="nota fiscal"),)),
         ("Cobrança por boleto", (
             _i("Cobrança por boleto", "cobranca_lista"),)),
         ("Tabela de emolumentos", (
             _i("Emolumentos", "caixa_emolumentos", AMA, termos="custas tabela preco"),)),
         ("Modelos do caixa", (
             _i("Modelos do caixa", "caixa_modelos_papeis", AMU),)),
     )},
    {"chave": "ATEND", "curto": "Atendimento", "nome": "Atendimento", "cor": "ADM",
     "icone": "balao", "lavra": False, "secoes": (
         ("Senhas", (
             _i("Atendimento / senhas", "service_queue"),
             _i("Espera e atendimento", "senhas_relatorio", AMA, antigo="Senhas: espera e atendimento"),)),
         ("WhatsApp", (
             _i("WhatsApp", "whatsapp_lista", termos="mensagem conversa"),)),
         ("Portal do cliente", (
             _i("Portal do cliente", "caixa_portal_cliente", AM),)),
         ("Avisos ao cliente", (
             _i("Avisos de andamento", "andamento_fila", AM, antigo="Avisos ao cliente (andamento)"),)),
         ("Ouvidoria", (
             _i("Ouvidoria", "ouvidoria_lista"),)),
         ("Satisfação", (
             _i("Pesquisa de satisfação", "satisfacao_relatorio", AMA),
             _i("Convite para avaliar", "satisfacao_convite", ("USER",)),)),
     )},
    {"chave": "MALOTE", "curto": "Processos e Malote", "nome": "Processos e Malote", "cor": "MALOTE",
     "icone": "pasta", "lavra": True, "secoes": (
         ("Processos", (
             _i("Processos", "processos_lista", termos="tarefa expediente malote"),)),
         ("Inspeções", (
             _i("Inspeções", "inspections", termos="correicao"),)),
         ("O que ficou pelo caminho", (
             _i("O que ficou pelo caminho", "inacabados_lista", termos="inacabado parado"),)),
         ("Rascunhos", (
             _i("Rascunhos", "rascunhos"),)),
         ("Checklists", (
             _i("Checklists", "checklists"),)),
         ("Obrigações recorrentes", (
             _i("Obrigações recorrentes", "recurrences", AM),)),
     )},
    {"chave": "LIVROS", "curto": "Livros e Acervo", "nome": "Livros e Acervo", "cor": "LIVROS",
     "icone": "livro", "lavra": True, "secoes": (
         ("Livros e termos", (
             _i("Livros e termos", "nucleo_livros"),)),
         ("Encerramento diário", (
             _i("Encerramento diário", "nucleo_encerramento_diario"),)),
         ("Numeração", (
             _i("Numeração dos livros", "nucleo_numeracao", AM),)),
         ("O que falta informar", (
             _i("O que falta informar", "implantacao", AM),)),
         ("Importar", (
             _i("Importar de outro sistema", "importar_padrao_tela", AMU),
             _i("Importar matrícula do RI", "importar_padrao_tela", ("USER",), especie="RI_MATRICULA"),)),
         ("Livros obrigatórios", (
             _i("Livros obrigatórios", "livros_obrigatorios", AMA),)),
     )},
    {"chave": "FIN", "curto": "Finanças e Selos", "nome": "Finanças e Selos", "cor": "ADM",
     "icone": "selo", "lavra": False, "secoes": (
         ("Selos", (
             _i("Selos emitidos", "selos_emitidos_lista", AMA),
             _i("Selo e caixa", "selo_cobertura"),
             _i("Selos × caixa (conferência)", "selo_conferencia", AM),
             _i("Selos cancelados", "selo_cancelamentos", AMA, antigo="Selos cancelados (pedido ao TJMA)"),)),
         ("Gratuidades", (
             _i("Gratuidades (Portal do Selo)", "selo_gratuidades_portal", AMA),)),
         ("Despesas", (
             _i("Despesas", "despesas_lista", QUATRO),)),
         ("Livro Diário", (
             _i("Livro Diário Auxiliar", "livro_diario", AMA),)),
         ("Caixas para o visto", (
             _i("Caixas para o visto", "gestor_caixas", AM),)),
         ("Produtividade", (
             _i("Produtividade", "produtividade_lista"),)),
         ("Relatórios", (
             _i("Relatórios", "reports"),)),
         ("Carnê-leão", (
             _i("Carnê-leão", "carne_leao", A),)),
     )},
    {"chave": "GESTAO", "curto": "Gestão", "nome": "Gestão", "cor": "ADM",
     "icone": "escudo", "lavra": False, "secoes": (
         ("·Conformidade", ()),
         ("Envios às Centrais", (
             _i("Envios às Centrais", "gestor_envios"),)),
         ("Erros e correções", (
             _i("Problemas do sistema", "ajuda_problemas", AM),
             _i("Os problemas que você relatou", "ajuda_problemas", SEM_GESTAO),
             _i("Correções de ofício", "correcoes_de_oficio_lista"),
             _i("Relatório de erros", "gestor_erros", A),
             _i("Avisos da serventia", "nu_avisos_lista"),)),
         ("Fraudes", (
             _i("Consultar fraudes", "fraude_consultar"),
             _i("Atenção para fraudes", "fraudes", AM),)),
         ("PLD / COAF", (
             _i("PLD / COAF", "pld_painel", A, antigo="PLD / COAF (sigiloso)"),)),
         ("LGPD e auditoria", (
             _i("LGPD e governança", "lgpd"),
             _i("Auditoria", "audit_logs", AA),
             _i("Integridade", "integrity", AA),
             _i("Relatório anual de IA", "gestor_relatorio_ia", A),)),
         ("·Automação e IA", ()),
         ("Rotinas e robôs", (
             _i("Automação (rotinas)", "automacao_lista", AM),
             _i("Robôs", "robos_lista"),)),
         ("Agente e leituras", (
             _i("Leitura dos textos (IA)", "gestor_leituras"),
             _i("Ajuda do sistema", "ajuda_consultar", quando="ajuda_liberada"),
             _i("O que a ajuda sabe do projeto", "ajuda_projeto", AM),
             _i("Base de conhecimento da ajuda", "ajuda_base", AM),
             _i("Ajuda: configurar", "ajuda_configurar", A, antigo="Ajuda — configurar"),
             _i("Agente do sistema", "agente_console", A, quando="agente_no_menu"),
             _i("Agente: configurar", "agente_configurar", A, quando="agente_no_menu", antigo="Agente — configurar"),)),
         ("·Configuração", ()),
         ("Usuários e acesso", (
             _i("Usuários", "users", A),
             _i("Verificação em duas etapas", "gestor_dois_fatores", A, antigo="Verificação em duas etapas — Gestor"),)),
         ("Configurações", (
             _i("Configurações", "settings", A),
             _i("Selador", "selador_config", AM, antigo="Selador — configuração"),
             _i("Rede / acesso", "network_status", AM),
             _i("TI e infraestrutura", "assets"),
             _i("Integrações do Protesto", "gestor_protesto_integracoes", A),
             _i("Corrigir dado do acervo", "acervo_corrigir", A),
             _i("Painel no celular", "painel_celular", A),
             _i("Apostila de Haia", "apostila_lista", quando="apostila_visivel"),
             _i("Apostila de Haia (desligada)", "apostila_configuracao", A, quando="apostila_escondida"),
             _i("Projetos", "dev_projetos_lista", A),)),
         ("Modelos da casa", (
             _i("Modelos dos documentos", "modelos", AMU),)),
         ("Atualizações", (
             _i("Correções e atualizações", "updates", A),)),
     )},
)

# O INÍCIO NÃO TEM SEÇÕES, por ordem de 13/10/2026: a fila ocupa toda a largura. Mas a
# busca acha por ele, inclusive pelo nome de hoje.
ENTRADA_DO_INICIO = _i("Início", "dashboard", antigo="Visão geral", termos="painel geral fila")

# O QUE ENTROU NO MENU POR ESTE REGISTRO, e não estava no antigo: filtros de uma tela
# que já existia. A lista é fechada, para o teste de paridade não aceitar qualquer coisa.
ENTRADAS_NOVAS: frozenset[tuple[str, tuple]] = frozenset({
    ("notas_atos", (("tipo", "PROCURACAO"),)),
    ("notas_atos", (("tipo", "PROCURACAO_PREVIDENCIARIA"),)),
    ("notas_atos", (("tipo", "SUBSTABELECIMENTO"),)),
    ("notas_atos", (("tipo", "REVOGACAO"),)),
    ("notas_atos", (("tipo", "RENUNCIA"),)),
    ("notas_atos", (("tipo", "TESTAMENTO"),)),
    ("notas_atos", (("tipo", "TESTAMENTO_CERRADO"),)),
})

# A FICHA DE UM ATO NÃO TEM ENTRADA PRÓPRIA: ela pertence à seção da lista de onde se
# chega nela. Sem isto a tela abriria com o menu fechado — o defeito que `modulos.py`
# existe para impedir.
PAI: dict[str, tuple[str, str]] = {
    # Notas
    "notas_ato_novo": ("NOTAS", "Procurações"),
    "notas_leituras": ("NOTAS", "Procurações"),
    "notas_anotacoes_pendentes": ("NOTAS", "Painel do dia"),
    "notas_reconhecimentos": ("NOTAS", "Balcão"),
    "notas_reconhecimento_ver": ("NOTAS", "Balcão"),
    "notas_certidao": ("NOTAS", "Balcão"),
    "notas_publica_forma_ver": ("NOTAS", "Balcão"),
    "notas_veiculo": ("NOTAS", "Balcão"),
    "notas_veiculo_nova": ("NOTAS", "Balcão"),
    "notas_sinal": ("NOTAS", "Cartões de autógrafo"),
    "notas_sinal_reconhecimento_ver": ("NOTAS", "Balcão"),
    "notas_cartao": ("NOTAS", "Cartões de autógrafo"),
    "notas_assinaturas": ("NOTAS", "Cartões de autógrafo"),
    "notas_ccn_consulta": ("NOTAS", "Centrais"),
    "notas_ccn_lote": ("NOTAS", "Centrais"),
    "notas_remessa_pendencias": ("NOTAS", "Centrais"),
    "notas_modelos_de_atos": ("NOTAS", "Livros e modelos"),
    "notas_publica_forma_configuracao": ("NOTAS", "Livros e modelos"),
    "notas_veiculo_configuracao": ("NOTAS", "Livros e modelos"),
    "notas_importar": ("LIVROS", "Importar"),
    # Registro de Imóveis
    "ri_ficha": ("RI", "Matrículas"),
    "ri_conferir_ficha": ("RI", "Matrículas"),
    "ri_editar_matricula": ("RI", "Matrículas"),
    "ri_nova_matricula": ("RI", "Matrículas"),
    "ri_preencher_modelo": ("RI", "Matrículas"),
    "ri_rascunho_ver": ("RI", "Para revisar"),
    "ri_situacao_juridica": ("RI", "Matrículas"),
    "ri_protocolo_ver": ("RI", "Protocolo"),
    "ri_nota_devolutiva": ("RI", "Protocolo"),
    "ri_qualificacao_ia_ver": ("RI", "Protocolo"),
    "onr_auto_fila": ("RI", "Certidões"),
    "onr_auto_pedido": ("RI", "Certidões"),
    "onr_certidao_ficha": ("RI", "Certidões"),
    "ri_retificacao": ("RI", "Processos longos"),
    "ri_retificacao_nova": ("RI", "Processos longos"),
    "ri_retificacao_normas": ("RI", "Processos longos"),
    "ri_onr_edital": ("RI", "Processos longos"),
    "usucapiao_processo": ("RI", "Processos longos"),
    "usucapiao_dossie": ("RI", "Processos longos"),
    "usucapiao_manual_notificacao": ("RI", "Processos longos"),
    "usucapiao_notificacao_papel": ("RI", "Processos longos"),
    "livro3_registro": ("RI", "Livro 3"),
    "livro3_registro_novo": ("RI", "Livro 3"),
    "livro3_como_ficara": ("RI", "Livro 3"),
    "livro3_conferir": ("RI", "Livro 3"),
    "livro3_importar_acervo": ("LIVROS", "Importar"),
    "ri_busca_no_acervo": ("RI", "Consulta"),
    "ri_onr_endereco": ("RI", "Centrais e obrigações"),
    "ri_onr_indicador": ("RI", "Centrais e obrigações"),
    "ri_expurgar_ato": ("RI", "Acervo e modelos"),
    "ri_fichas_do_disco": ("RI", "Acervo e modelos"),
    "ri_transcricoes_lote_ver": ("RI", "Acervo e modelos"),
    "ri_importar": ("LIVROS", "Importar"),
    "ri_importacoes": ("LIVROS", "Importar"),
    "ri_importacao_manual": ("LIVROS", "Importar"),
    # Registro Civil
    "rcpn_assento": ("RCPN", "Assento lavrado"),
    "rcpn_assento_editar": ("RCPN", "Assento lavrado"),
    "rcpn_anotar": ("RCPN", "Assento lavrado"),
    "rcpn_averbar": ("RCPN", "Assento lavrado"),
    "rcpn_averbacao_modelo": ("RCPN", "Assento lavrado"),
    "rcpn_checklist": ("RCPN", "Assento lavrado"),
    "rcpn_folha": ("RCPN", "Assento lavrado"),
    "rcpn_folha_papel": ("RCPN", "Assento lavrado"),
    "rcpn_retificacao": ("RCPN", "Assento lavrado"),
    "rcpn_retificacao_nova": ("RCPN", "Assento lavrado"),
    "rcpn_retificar": ("RCPN", "Assento lavrado"),
    "rcpn_termo": ("RCPN", "Assento lavrado"),
    "rcpn_leitura": ("RCPN", "Balcão"),
    "rcpn_leitura_ficha": ("RCPN", "Balcão"),
    "rcpn_importar_acervo": ("LIVROS", "Importar"),
    "rcpn_habilitacao": ("RCPN", "Casamento"),
    "rcpn_habilitacao_nova": ("RCPN", "Casamento"),
    "rcpn_proclama": ("RCPN", "Casamento"),
    "rcpn_certidao": ("RCPN", "Certidões"),
    "rcpn_certidao_previa": ("RCPN", "Certidões"),
    "rcpn_certidao_eletronica_nova": ("RCPN", "Certidões"),
    "rcpn_pedido": ("RCPN", "Certidões"),
    "rcpn_anotacao_oficio": ("RCPN", "Comunicações"),
    "rcpn_crc_historico": ("RCPN", "Comunicações"),
    "rcpn_funai_oficio": ("RCPN", "Comunicações"),
    "rcpn_etiqueta_averbacao_ajuste": ("RCPN", "Modelos"),
    "rcpn_modelo": ("RCPN", "Modelos"),
    "rcpn_modelo_converter": ("RCPN", "Modelos"),
    "rcpn_modelo_emitir": ("RCPN", "Modelos"),
    "rcpn_modelos_do_assento": ("RCPN", "Modelos"),
    "rcpn_comunicacao": ("RCPN", "Óbito"),
    # Protesto
    "protesto_titulo": ("PROTESTO", "Títulos"),
    "protesto_titulo_novo": ("PROTESTO", "Títulos"),
    "protesto_titulos_irmaos": ("PROTESTO", "Títulos"),
    "protesto_certidao": ("PROTESTO", "Balcão"),
    "protesto_devedor": ("PROTESTO", "Balcão"),
    "protesto_pix_lista": ("PROTESTO", "Balcão"),
    "protesto_avisos_lote": ("PROTESTO", "Dia da CRA"),
    "protesto_desistencia": ("PROTESTO", "Dia da CRA"),
    "protesto_desistencia_conferir": ("PROTESTO", "Dia da CRA"),
    "protesto_resolve_pdfs_do_lote": ("PROTESTO", "Dia da CENPROT"),
    "protesto_remessa": ("PROTESTO", "Dia da CRA"),
    "protesto_retornos_protocolos": ("PROTESTO", "Dia da CRA"),
    "protesto_cenprot_xml": ("PROTESTO", "Dia da CENPROT"),
    "protesto_pendencia": ("PROTESTO", "Dia da CENPROT"),
    "protesto_resolve_ficha": ("PROTESTO", "Dia da CENPROT"),
    "protesto_repasse_guia": ("PROTESTO", "Livros e repasses"),
    "protesto_importar_eoficio": ("LIVROS", "Importar"),
    # RCPJ e RTD
    "rcpj_rtd_titulo": ("RCPJ", "Títulos apresentados"),
    "rcpj_rtd_titulo_novo": ("RCPJ", "Títulos apresentados"),
    "rcpj_rtd_titulo_nota": ("RCPJ", "Títulos apresentados"),
    "rcpj_rtd_registro": ("RCPJ", "Registros lavrados"),
    "rcpj_rtd_registro_novo": ("RCPJ", "Registros lavrados"),
    "rcpj_rtd_notificacao": ("RCPJ", "Notificações"),
    "rcpj_rtd_notificacao_nova": ("RCPJ", "Notificações"),
    "rcpj_rtd_notificacao_certidao_ver": ("RCPJ", "Notificações"),
    "rcpj_rtd_livro_contabil_configuracao": ("RCPJ", "Livros contábeis"),
    "rcpj_rtd_livro_contabil_ficha": ("RCPJ", "Livros contábeis"),
    "rcpj_rtd_livro_contabil_novo": ("RCPJ", "Livros contábeis"),
    "rcpj_rtd_livro_contabil_papel": ("RCPJ", "Livros contábeis"),
    "atribuicoes_certidao": ("RCPJ", "Certidões"),
    # Caixa
    "caixa_protocolo": ("CAIXA", "Protocolo geral"),
    "caixa_protocolos_novo": ("CAIXA", "Protocolo geral"),
    "caixa_exigencias": ("CAIXA", "Protocolo geral"),
    "andamento_protocolo_geral": ("CAIXA", "Protocolo geral"),
    "andamento_prenotacao": ("RI", "Protocolo"),
    "notas_leitura_ficha": ("NOTAS", "Procurações"),
    "cobranca_ficha": ("CAIXA", "Cobrança por boleto"),
    "cobranca_nova": ("CAIXA", "Cobrança por boleto"),
    "cobranca_configuracao": ("CAIXA", "Cobrança por boleto"),
    "configuracoes_cobranca": ("CAIXA", "Cobrança por boleto"),
    "nfse_apuracao": ("CAIXA", "Recibos e NFS-e"),
    "nfse_recibo": ("CAIXA", "Recibos e NFS-e"),
    "caixa_importar": ("LIVROS", "Importar"),
    # Atendimento
    "senhas_imprimir": ("ATEND", "Senhas"),
    "senhas_painel_config": ("ATEND", "Senhas"),
    "whatsapp_conversa": ("ATEND", "WhatsApp"),
    "whatsapp_atendente": ("ATEND", "WhatsApp"),
    "whatsapp_config": ("ATEND", "WhatsApp"),
    "whatsapp_painel": ("ATEND", "WhatsApp"),
    "ouvidoria_ficha": ("ATEND", "Ouvidoria"),
    "ouvidoria_relatorio": ("ATEND", "Ouvidoria"),
    # Processos
    "checklist_run": ("MALOTE", "Checklists"),
    "inspection_detail": ("MALOTE", "Inspeções"),
    "inacabados_anotar": ("MALOTE", "O que ficou pelo caminho"),
    "recurrence_detail": ("MALOTE", "Obrigações recorrentes"),
    "expediente_detail": ("MALOTE", "Processos"),
    "expedientes": ("MALOTE", "Processos"),
    "expedientes_prontos": ("MALOTE", "Processos"),
    "task_detail": ("MALOTE", "Processos"),
    "task_dossier": ("MALOTE", "Processos"),
    "tasks": ("MALOTE", "Processos"),
    # Livros
    "atribuicoes_importar": ("LIVROS", "Importar"),
    "nucleo_livro": ("LIVROS", "Livros e termos"),
    "livro_deposito_previo": ("LIVROS", "Livros obrigatórios"),
    "livro_visitas": ("LIVROS", "Livros obrigatórios"),
    "livro_visitas_imprimir": ("LIVROS", "Livros obrigatórios"),
    # Finanças
    "carne_leao_configuracao": ("FIN", "Carnê-leão"),
    "despesas_configuracao": ("FIN", "Despesas"),
    "despesas_ficha": ("FIN", "Despesas"),
    "despesas_nova": ("FIN", "Despesas"),
    "despesas_recorrente": ("FIN", "Despesas"),
    "despesas_recorrentes": ("FIN", "Despesas"),
    "despesas_relatorio": ("FIN", "Despesas"),
    "gratuidade_comprovantes": ("FIN", "Gratuidades"),
    "selo_portal_remessa": ("FIN", "Gratuidades"),
    "livro_diario_versao": ("FIN", "Livro Diário"),
    "relatos_diarios": ("FIN", "Produtividade"),
    # Gestão
    "agente_sessao": ("GESTAO", "Agente e leituras"),
    "gestor_relatorio_ia_papel": ("GESTAO", "LGPD e auditoria"),
    "minuta_ia_pedido": ("GESTAO", "Agente e leituras"),
    "ajuda_consulta": ("GESTAO", "Agente e leituras"),
    "nu_avisos_detalhe": ("GESTAO", "Erros e correções"),
    "nu_avisos_admin_editar": ("GESTAO", "Erros e correções"),
    "nu_avisos_admin_novo": ("GESTAO", "Erros e correções"),
    "nfse_gestor": ("GESTAO", "Configurações"),
    "gestor_ia": ("GESTAO", "Configurações"),
    "ri_qualificacao_ia_configuracao": ("GESTAO", "Configurações"),
    "asset_detail": ("GESTAO", "Configurações"),
    "dev_projetos_detalhe": ("GESTAO", "Configurações"),
    "centrais_status": ("GESTAO", "Envios às Centrais"),
    "correcoes_de_oficio_ficha": ("GESTAO", "Erros e correções"),
    "correcoes_de_oficio_propor": ("GESTAO", "Erros e correções"),
    "painel_retrato_tela": ("GESTAO", "Configurações"),
    "robos_testar": ("GESTAO", "Rotinas e robôs"),
    "correcoes_de_oficio_nova": ("GESTAO", "Erros e correções"),
    "lgpd_detail": ("GESTAO", "LGPD e auditoria"),
    "modelos_editor_editar": ("GESTAO", "Modelos da casa"),
    "modelos_editor_lista": ("GESTAO", "Modelos da casa"),
    "apostila_certidao": ("GESTAO", "Configurações"),
    "apostila_controle": ("GESTAO", "Configurações"),
    "apostila_pedido": ("GESTAO", "Configurações"),
    "pld_caso": ("GESTAO", "PLD / COAF"),
    "pld_nao_ocorrencia": ("GESTAO", "PLD / COAF"),
    "automacao_cofre": ("GESTAO", "Rotinas e robôs"),
    "automacao_cofre_desbloquear": ("GESTAO", "Rotinas e robôs"),
    "automacao_configuracao": ("GESTAO", "Rotinas e robôs"),
    "automacao_execucao": ("GESTAO", "Rotinas e robôs"),
    "automacao_processo": ("GESTAO", "Rotinas e robôs"),
    "malote_robo_codigo": ("GESTAO", "Rotinas e robôs"),
    "robos_config": ("GESTAO", "Rotinas e robôs"),
    "robos_editar": ("GESTAO", "Rotinas e robôs"),
    "robos_novo": ("GESTAO", "Rotinas e robôs"),
}

SECAO_DO_TIPO_DE_ATO: dict[str, str] = {
    "ESCRITURA": "Escrituras",
    "ATA": "Atas notariais",
    "ATA_USUCAPIAO": "Atas notariais",
    "TESTAMENTO": "Testamentos",
    "TESTAMENTO_CERRADO": "Testamentos",
}

# O MÓDULO DE QUEM NÃO ESTÁ NO REGISTRO NEM EM `PAI`, pela regra de `modulos.py`.
_MODULO_DO_ANTIGO = {"NOTAS": "NOTAS", "RI": "RI", "RCPN": "RCPN", "PROTESTO": "PROTESTO",
                     "RCPJ_RTD": "RCPJ", "MALOTE": "MALOTE", "LIVROS": "LIVROS", "ADM": "GESTAO"}

# O BOTÃO NOVO. `abre_ato` abre o ato direto: é o «clique fácil» que faltava para lavrar
# procuração pública. O ato nasce em lavratura, sem livro nem folha, e pode ser descartado.
NOVO: tuple[dict, ...] = (
    {"grupo": "Tabelionato de Notas", "cor": "NOTAS", "itens": (
        {"rotulo": "Reconhecer firma", "letra": "F", "endpoint": "notas_reconhecimento"},
        {"rotulo": "Autenticar cópia", "letra": "A", "endpoint": "notas_autenticacao"},
        {"rotulo": "Procuração pública", "letra": "P", "papeis": AMU,
         "abre_ato": {"tipo": "PROCURACAO", "modelo_codigo": "NT-PROC-PUBLICA"},
         "termos": "mandato outorga procurador lavrar"},
        {"rotulo": "Escritura pública", "letra": "E", "papeis": AMU, "endpoint": "notas_ato_novo",
         "args": {"familia": "escrituras"}, "termos": "compra venda doacao lavrar"},
        {"rotulo": "Ata notarial", "papeis": AMU, "endpoint": "notas_ato_novo", "args": {"familia": "atas"}},
        {"rotulo": "Substabelecimento", "papeis": AMU,
         "abre_ato": {"tipo": "SUBSTABELECIMENTO", "modelo_codigo": "NT-SUBSTABELECIMENTO"}, "termos": "procuracao"},
        {"rotulo": "Revogação de procuração", "papeis": AMU,
         "abre_ato": {"tipo": "REVOGACAO", "modelo_codigo": "NT-REVOGACAO-MANDATO"}, "termos": "cancelar revogar"},
        {"rotulo": "Testamento e outros atos", "papeis": AMU, "endpoint": "notas_ato_novo"},
        {"rotulo": "Certidão de Notas", "endpoint": "notas_certidoes"},)},
    {"grupo": "Registro de Imóveis", "cor": "RI", "itens": (
        {"rotulo": "Prenotar título", "letra": "T", "endpoint": "ri_protocolo", "termos": "protocolo prenotacao"},
        {"rotulo": "Certidão de imóvel", "letra": "C", "endpoint": "ri_certidoes"},
        {"rotulo": "Abrir matrícula", "papeis": AMU, "endpoint": "ri_nova_matricula"},)},
    {"grupo": "Registro Civil", "cor": "RCPN", "itens": (
        {"rotulo": "Nascimento", "letra": "N", "endpoint": "rcpn_assento_novo", "args": {"especie_url": "nascimento"}},
        {"rotulo": "Habilitação de casamento", "papeis": AMU, "endpoint": "rcpn_habilitacao_nova"},
        {"rotulo": "Óbito", "endpoint": "rcpn_assento_novo", "args": {"especie_url": "obito"}},
        {"rotulo": "Certidão civil", "endpoint": "rcpn_certidoes", "termos": "segunda via"},
        {"rotulo": "Averbação", "endpoint": "rcpn_averbacoes", "termos": "divorcio"},)},
    {"grupo": "Protesto", "cor": "PROTESTO", "escondivel": "PROTESTO", "itens": (
        {"rotulo": "Título no balcão", "papeis": AMU, "endpoint": "protesto_titulo_novo"},
        {"rotulo": "Certidão de protesto", "endpoint": "protesto_certidoes"},)},
    {"grupo": "RCPJ e RTD", "cor": "RCPJ_RTD", "itens": (
        {"rotulo": "Título do RTD", "endpoint": "rcpj_rtd_titulos", "args": {"atribuicao": 4}},
        {"rotulo": "Título do RCPJ", "endpoint": "rcpj_rtd_titulos", "args": {"atribuicao": 3}},
        {"rotulo": "Notificação", "papeis": AMU, "endpoint": "rcpj_rtd_notificacao_nova"},)},
    {"grupo": "Caixa e processos", "cor": "ADM", "itens": (
        {"rotulo": "Protocolo geral", "letra": "G", "papeis": AMU, "endpoint": "caixa_protocolos_novo"},
        {"rotulo": "Lançamento no caixa", "endpoint": "caixa"},
        {"rotulo": "Processo interno", "endpoint": "processos_lista", "termos": "tarefa expediente"},
        {"rotulo": "Despesa", "papeis": QUATRO, "endpoint": "despesas_lista"},)},
)

# ONDE A BUSCA PROCURA um nome ou um número digitado. Cada uma é a lista que já
# aceita `?busca=`; a busca não lê banco, ela leva até a tela que lê.
PROCURAR_EM: tuple[dict, ...] = (
    {"rotulo": "Matrículas", "endpoint": "ri_matriculas", "campo": "busca"},
    {"rotulo": "Atos de Notas", "endpoint": "notas_atos", "campo": "busca"},
    {"rotulo": "Cartões de autógrafo", "endpoint": "notas_cartoes", "campo": "busca"},
    {"rotulo": "Assentos do Registro Civil", "endpoint": "rcpn_assentos", "campo": "q"},
    {"rotulo": "Títulos de protesto", "endpoint": "protesto_titulos", "campo": "q"},
    {"rotulo": "Protocolo geral", "endpoint": "caixa_protocolos", "campo": "busca"},
)


def _modulo(chave: str) -> dict | None:
    return next((m for m in MODULOS_DA_BARRA if m["chave"] == chave), None)


def cor_do_modulo(modulo: dict) -> tuple[str, str]:
    """A cor do módulo e a versão clara dela. Sai de `modulos.py`: nunca se escreve aqui."""
    base = POR_CHAVE.get(modulo.get("cor") or "")
    if not base:
        return "#0b5cad", "#e7f0fa"
    return base["cor"], clarear(base["cor"], 0.88)


def _ve(entrada: dict, papel: str, flags: dict) -> bool:
    papeis = entrada.get("papeis")
    if papeis is not None and papel not in papeis:
        return False
    quando = entrada.get("quando")
    return not quando or bool(flags.get(quando))


def _flags(ajuda_liberada: Any, agente_no_menu: Any, escondidos: Any) -> dict:
    fora = set(escondidos or ())
    return {"ajuda_liberada": bool(ajuda_liberada), "agente_no_menu": bool(agente_no_menu),
            "apostila_visivel": "APOSTILA" not in fora, "apostila_escondida": "APOSTILA" in fora,
            "_escondidos": fora}


def entradas(papel: str, flags: dict | None = None) -> list[dict]:
    """Todas as entradas que aquele papel vê, com módulo e seção. Só calcula."""
    flags = flags if flags is not None else _flags(True, True, ())
    fora = []
    for m in MODULOS_DA_BARRA:
        if m.get("escondivel") and m["escondivel"] in flags.get("_escondidos", ()):
            continue
        for nome, itens in m["secoes"]:
            for item in itens:
                if _ve(item, papel, flags):
                    fora.append({**item, "modulo": m["chave"], "secao": nome})
    return fora


def _bate(item: dict, args: dict) -> bool:
    return all(str(args.get(k)) == str(v) for k, v in item["args"].items())


def localizar(endpoint: str, args: dict, papel: str, flags: dict,
              tipo_do_ato: str = "") -> tuple[str, str, dict | None]:
    """Em que módulo e seção a tela está, e qual entrada a representa."""
    candidatos = [e for e in entradas(papel, flags)
                  if e["endpoint"] == endpoint and _bate(e, args)]
    if candidatos:
        melhor = max(candidatos, key=lambda e: len(e["args"]))
        return melhor["modulo"], melhor["secao"], melhor
    if endpoint == "notas_ato":
        return "NOTAS", SECAO_DO_TIPO_DE_ATO.get(tipo_do_ato or "", "Procurações"), None
    if endpoint in PAI:
        modulo, secao = PAI[endpoint]
        return modulo, secao, None
    if endpoint == "dashboard" or not endpoint:
        return "INICIO", "", None
    antigo = modulo_da_tela(endpoint, args.get("atribuicao", ""))
    return _MODULO_DO_ANTIGO.get(antigo, "GESTAO"), "", None


def sem_acento(texto: Any) -> str:
    decomposto = unicodedata.normalize("NFD", str(texto or ""))
    return "".join(c for c in decomposto if unicodedata.category(c) != "Mn").lower()


def montar(endpoint: str, args: dict, papel: str, gerar_url: Callable[..., str], *,
           escondidos: Any = (), ajuda_liberada: Any = False, agente_no_menu: Any = False,
           tipo_do_ato: str = "") -> dict:
    """Tudo o que a casca desenha naquela tela. Só calcula.

    `gerar_url` é o `url_for`. Entrada cujo endereço não se monta some em vez de
    derrubar a página: um módulo desligado não pode tirar o menu do ar.
    """
    flags = _flags(ajuda_liberada, agente_no_menu, escondidos)

    def _url(entrada: dict) -> str | None:
        try:
            return gerar_url(entrada["endpoint"], **entrada.get("args", {}))
        except Exception:                                              # noqa: BLE001
            return None

    onde_mod, onde_sec, onde_item = localizar(endpoint, args, papel, flags, tipo_do_ato)
    barra, secoes, subabas, indice = [], [], [], []
    url_do_inicio = _url(ENTRADA_DO_INICIO)
    if url_do_inicio:
        indice.append({"r": ENTRADA_DO_INICIO["rotulo"], "s": "", "u": url_do_inicio, "k": "ir",
                       "t": sem_acento(" ".join((ENTRADA_DO_INICIO["rotulo"], ENTRADA_DO_INICIO["antigo"], ENTRADA_DO_INICIO["termos"])))})
    atual = _modulo(onde_mod) or MODULOS_DA_BARRA[0]
    nome_grupo = ""
    for m in MODULOS_DA_BARRA:
        if m.get("escondivel") and m["escondivel"] in flags["_escondidos"]:
            continue
        entrada_do_modulo = None
        for nome, itens in m["secoes"]:
            if nome.startswith("·"):
                nome_grupo = nome[1:]
                continue
            visiveis = []
            for item in itens:
                if not _ve(item, papel, flags):
                    continue
                url = _url(item)
                if url is None:
                    continue
                visiveis.append({"rotulo": item["rotulo"], "url": url,
                                 "atual": onde_item is not None and item is _original(onde_item)})
                indice.append({"r": item["rotulo"], "s": f'{m["curto"]} › {nome}', "u": url, "k": "ir",
                               "t": sem_acento(" ".join((item["rotulo"], nome, m["nome"], item["antigo"], item["termos"])))})
            if not visiveis:
                continue
            entrada_do_modulo = entrada_do_modulo or visiveis[0]["url"]
            if m is atual:
                eh_esta = nome == onde_sec
                secoes.append({"nome": nome, "url": visiveis[0]["url"], "atual": eh_esta,
                               "grupo": nome_grupo})
                nome_grupo = ""
                if eh_esta and len(visiveis) > 1:
                    subabas = visiveis
        cor, clara = cor_do_modulo(m)
        if m["chave"] == "INICIO":
            entrada_do_modulo = _url({"endpoint": "dashboard"})
        if entrada_do_modulo:
            barra.append({"chave": m["chave"], "curto": m["curto"], "nome": m["nome"], "cor": cor,
                          "clara": clara, "icone": m["icone"], "lavra": m["lavra"],
                          "url": entrada_do_modulo, "atual": m is atual})
    cor, clara = cor_do_modulo(atual)
    novo = []
    for grupo in NOVO:
        if grupo.get("escondivel") and grupo["escondivel"] in flags["_escondidos"]:
            continue
        itens_novo = []
        for item in grupo["itens"]:
            if not _ve(item, papel, flags):
                continue
            if item.get("abre_ato"):
                url = _url({"endpoint": "notas_ato_novo"})
            else:
                url = _url(item)
            if url is None:
                continue
            form_id = f'cg-novo-{sem_acento(item["rotulo"]).replace(" ", "-")}' if item.get("abre_ato") else ""
            itens_novo.append({"rotulo": item["rotulo"], "letra": item.get("letra", ""), "url": url,
                               "abre_ato": item.get("abre_ato"), "form_id": form_id})
            indice.append({"r": item["rotulo"], "s": "Novo", "u": url, "k": "novo", "f": form_id,
                           "t": sem_acento(" ".join((item["rotulo"], grupo["grupo"], item.get("termos", ""))))})
        if itens_novo:
            base_cor = POR_CHAVE.get(grupo["cor"])
            novo.append({"grupo": grupo["grupo"], "cor": base_cor["cor"] if base_cor else cor, "itens": itens_novo})
    # Só onde a pessoa entra: opção que leva à recusa seria clique perdido, e o
    # Protesto fechado para o balcão é o caso de todo dia.
    ao_alcance = {e["endpoint"] for e in entradas(papel, flags)}
    procurar = []
    for p in PROCURAR_EM:
        url = _url({"endpoint": p["endpoint"]}) if p["endpoint"] in ao_alcance else None
        if url:
            procurar.append({"r": p["rotulo"], "u": url, "c": p["campo"]})
    migalhas = []
    if atual["chave"] != "INICIO":
        migalhas.append({"rotulo": atual["nome"], "url": next((b["url"] for b in barra if b["chave"] == atual["chave"]), None)})
        if onde_sec:
            secao_atual = next((s for s in secoes if s["nome"] == onde_sec), None)
            migalhas.append({"rotulo": onde_sec, "url": secao_atual["url"] if secao_atual else None})
    return {"barra": barra, "secoes": secoes, "subabas": subabas, "modulo": atual["chave"],
            "modulo_nome": atual["nome"], "cor": cor, "clara": clara, "migalhas": migalhas,
            "novo": novo, "indice": indice, "procurar": procurar, "icones": ICONES}


def _original(entrada: dict) -> dict | None:
    """A entrada do registro de onde saiu a cópia que `entradas` devolve."""
    m = _modulo(entrada["modulo"])
    if not m:
        return None
    for nome, itens in m["secoes"]:
        if nome == entrada["secao"]:
            for item in itens:
                if (item["endpoint"], item["args"], item["rotulo"]) == (
                        entrada["endpoint"], entrada["args"], entrada["rotulo"]):
                    return item
    return None
