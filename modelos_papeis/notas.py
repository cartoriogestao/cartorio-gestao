"""Papéis do catálogo — Tabelionato de Notas."""
from __future__ import annotations

PASTA = "notas"
ATRIBUICAO = "Tabelionato de Notas"

PAPEIS: tuple[dict, ...] = (
    {'chave': 'NOTAS_TRASLADO', 'padrao': ('notas_web', 'MODELO_TRASLADO')},
    {'chave': 'NOTAS_TERMO_LIVRO', 'padrao': ('notas_web', 'MODELO_TERMO_LIVRO')},
    # A CERTIDÃO DAS NOTAS (15/10/2026): sem precedente de texto no E-Ofício,
    # e afirmação jurídica num papel assinado — o texto é do oficial.
    {'chave': 'NOTAS_CERTIDAO_INTEIRO_TEOR', 'padrao': ('notas_certidao', 'MODELO_INTEIRO_TEOR')},
    {'chave': 'NOTAS_CERTIDAO_POSITIVA', 'padrao': ('notas_certidao', 'MODELO_POSITIVA')},
    {'chave': 'NOTAS_CERTIDAO_NEGATIVA', 'padrao': ('notas_certidao', 'MODELO_NEGATIVA')},
    # LD02 (21/10/2026): a certidão em breve relato — a cópia RESUMIDA do art.
    # 851 do Código de Normas, que a casa não emitia. Texto sem precedente: do
    # oficial, como o das outras três.
    {'chave': 'NOTAS_CERTIDAO_BREVE_RELATO', 'padrao': ('notas_certidao', 'MODELO_BREVE_RELATO')},
    {'chave': 'NOTAS_CARTAO_FICHA', 'padrao': ('notas_web', 'MODELO_CARTAO_FICHA')},
    # LF06D (19/10/2026): os textos das Notas que ainda eram montados no
    # código. **SÃO PEDAÇOS DE PAPEL, E NÃO PAPÉIS INTEIROS** — a fórmula da
    # etiqueta, a abertura do teor, a qualificação da parte —, e por isso:
    #   · `elementos_comuns: False` — o encerramento e o rodapé da atribuição
    #     não podem entrar no meio de um teor;
    #   · `so_claros_do_padrao` — o ajuste da casa só usa os claros que o
    #     montador preenche (a tela recusa o inventado).
    # Onde o texto não tinha nome de constante, `padrao` diz a função que o
    # monta e que o lê daqui. As frases que a regra escolhe são peças
    # (`<CHAVE>__<peca>.txt`), na pasta ao lado.
    {'chave': 'NOTAS_RECONHECIMENTO_SEMELHANCA', 'padrao': ('notas_schema', 'texto_reconhecimento'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_RECONHECIMENTO_AUTENTICIDADE', 'padrao': ('notas_schema', 'texto_reconhecimento'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_RECONHECIMENTO_SINAL', 'padrao': ('notas_schema', 'texto_reconhecimento_sinal'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_AUTENTICACAO', 'padrao': ('notas_schema', 'TIPOS_AUTENTICACAO["PADRAO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_AUTENTICACAO_INTERNET', 'padrao': ('notas_schema', 'TIPOS_AUTENTICACAO["INTERNET"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ETIQUETA_FECHO', 'padrao': ('notas_schema', 'FECHO_ETIQUETA'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_TERMO_COMPARECIMENTO', 'padrao': ('notas_livro', 'texto_termo_comparecimento'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_LIVRO_ABERTURA', 'padrao': ('notas_livro', 'texto_termo_abertura'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_LIVRO_ENCERRAMENTO', 'padrao': ('notas_livro', 'texto_termo_encerramento'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_INUTILIZACAO', 'padrao': ('notas_inutilizacao', 'dizer'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_INUTILIZACAO_FACE', 'padrao': ('notas_inutilizacao', 'html_da_face'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ANOTACAO_MARGEM', 'padrao': ('notas_anotacoes', 'texto_padrao'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ABERTURA_ESCRITURA', 'padrao': ('notas_teor', 'ABERTURAS["ESCRITURA"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ABERTURA_PROCURACAO', 'padrao': ('notas_teor', 'ABERTURAS["PROCURACAO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ABERTURA_SUBSTABELECIMENTO', 'padrao': ('notas_teor', 'ABERTURAS["SUBSTABELECIMENTO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ABERTURA_REVOGACAO', 'padrao': ('notas_teor', 'ABERTURAS["REVOGACAO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_ABERTURA_ATA', 'padrao': ('notas_teor', 'ABERTURAS["ATA"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_FECHO_ESCRITURA', 'padrao': ('notas_teor', 'FECHOS["ESCRITURA"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_FECHO_PROCURACAO', 'padrao': ('notas_teor', 'FECHOS["PROCURACAO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_FECHO_SUBSTABELECIMENTO', 'padrao': ('notas_teor', 'FECHOS["SUBSTABELECIMENTO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_FECHO_REVOGACAO', 'padrao': ('notas_teor', 'FECHOS["REVOGACAO"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_FECHO_ATA', 'padrao': ('notas_teor', 'FECHOS["ATA"]'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_QUALIFICACAO_PF', 'padrao': ('notas_teor', 'qualificar'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_QUALIFICACAO_PJ', 'padrao': ('notas_teor', 'qualificar'), 'elementos_comuns': False, 'so_claros_do_padrao': True},
    {'chave': 'NOTAS_TRASLADO_CABECALHO', 'padrao': ('notas_web', 'MODELO_TRASLADO_CABECALHO'), 'elementos_comuns': False},
    # LG04 (19/10/2026): a pública forma — o tabelião transcreve o documento e
    # certifica a conformidade. Sem precedente no E-Ofício: o texto é do oficial.
    {'chave': 'NOTAS_PUBLICA_FORMA', 'padrao': ('nt_publica_forma', 'MODELO_PUBLICA_FORMA')},
)
