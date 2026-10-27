"""Papéis do catálogo — Protesto.

AS PEÇAS (LF06E, 19/10/2026) — as frases que a REGRA escolhe e o oficial
escreve: o pedido da certidão, a frase da intimação no termo, a menção da cópia
no instrumento... A regra (edital × pessoal, um × vários, com × sem cópia)
continua no módulo do papel; o texto de cada frase mora na pasta, e a tela de
Modelos o mostra e deixa editar.

Cada peça é uma linha deste catálogo, com ficha própria, e não o
`<CHAVE>__<peca>` do LF06A: a tela, os elementos e a prévia põem a chave em
maiúsculas (`modelos_web`, `modelos_elementos`, `modelos_previa`...), e a peça
com o nome em minúsculas não seria achada lá — ficaria lida e não editável.
`peca` tira a frase do guarda do esqueleto (frase curta não é papel sem texto)
e `elementos_comuns: False` impede que o encerramento ou o rodapé da
atribuição entrem no meio de uma frase.
"""
from __future__ import annotations

from modelos_papeis.tipagem import TIPOS_POR_CHAVE as _TIPOS

PASTA = "protesto"
ATRIBUICAO = "Protesto"


def _peca(chave: str, modulo: str, nome: str) -> dict:
    return {'chave': chave, 'padrao': (modulo, nome), 'peca': True,
            'elementos_comuns': False}


PAPEIS: tuple[dict, ...] = (
    {'chave': 'PT_TERMO_PROTESTO', 'padrao': ('protesto_termo', 'TERMO_DO_PROTESTO')},
    # LD04 (21/10/2026): a qualificação do registro, no alto do termo (Lei
    # 9.492, arts. 21, § 4º, e 22) — peça, para valer também no termo da casa.
    _peca('PT_TERMO_QUALIFICACAO', 'protesto_termo', 'QUALIFICACAO_DO_REGISTRO'),
    _peca('PT_TERMO_INTIMACAO_EDITAL', 'protesto_termo', 'FRASE_INTIMACAO_EDITAL'),
    _peca('PT_TERMO_INTIMACAO_EDITAL_SEM_MOTIVO', 'protesto_termo',
          'FRASE_INTIMACAO_EDITAL_SEM_MOTIVO'),
    _peca('PT_TERMO_INTIMACAO_PESSOAL', 'protesto_termo', 'FRASE_INTIMACAO_PESSOAL'),
    _peca('PT_TERMO_INTIMACAO_DIGITAL', 'protesto_termo', 'FRASE_INTIMACAO_DIGITAL'),
    _peca('PT_TERMO_MOTIVOS', 'protesto_termo', 'MOTIVO_NO_LIVRO'),
    _peca('PT_TERMO_TIPOS', 'protesto_termo', 'TIPO_NO_LIVRO'),
    # LD04 (21/10/2026): o termo do cancelamento, que não existia — o ato
    # gravava a hipótese e o fundamento, e nenhum texto (Lei 9.492, art. 26, § 6º).
    {'chave': 'PT_TERMO_CANCELAMENTO', 'padrao': ('protesto_termo', 'TERMO_DO_CANCELAMENTO')},
    {'chave': 'PT_INSTRUMENTO_PROTESTO', 'padrao': ('protesto_instrumento', 'INSTRUMENTO_DE_PROTESTO')},
    _peca('PT_INSTRUMENTO_PRACA', 'protesto_instrumento', 'PRACA_NAO_INFORMADA'),
    _peca('PT_INSTRUMENTO_DESCRICAO', 'protesto_instrumento', 'DESCRICAO_DO_DOCUMENTO'),
    _peca('PT_INSTRUMENTO_COPIA_ARQUIVADA', 'protesto_instrumento',
          'MENCAO_DA_COPIA_ARQUIVADA'),
    _peca('PT_INSTRUMENTO_SEM_COPIA', 'protesto_instrumento', 'FRASE_SEM_COPIA'),
    _peca('PT_INSTRUMENTO_INTIMACAO_EDITAL', 'protesto_instrumento',
          'FRASE_INTIMACAO_EDITAL'),
    _peca('PT_INSTRUMENTO_INTIMACAO_EDITAL_SEM_MOTIVO', 'protesto_instrumento',
          'FRASE_INTIMACAO_EDITAL_SEM_MOTIVO'),
    _peca('PT_INSTRUMENTO_INTIMACAO_ENTREGUE', 'protesto_instrumento',
          'FRASE_INTIMACAO_ENTREGUE'),
    # LD04 (21/10/2026): a certidão da intimação por meio eletrônico, que o
    # instrumento não tinha — certificava «entregue no endereço do devedor».
    _peca('PT_INSTRUMENTO_INTIMACAO_DIGITAL', 'protesto_instrumento',
          'FRASE_INTIMACAO_DIGITAL'),
    _peca('PT_INSTRUMENTO_SEM_INTIMACAO', 'protesto_instrumento', 'FRASE_SEM_INTIMACAO'),
    # Tarefa 56 (23/10/2026): a menção do atraso do tríduo — CN-MA art. 913,
    # § 1º. Só sai no protesto lavrado depois do termo final.
    _peca('PT_INSTRUMENTO_ATRASO', 'protesto_instrumento', 'FRASE_ATRASO_DO_TRIDUO'),
    {'chave': 'PT_CERTIDAO_NEGATIVA', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_NEGATIVA')},
    {'chave': 'PT_CERTIDAO_POSITIVA', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_POSITIVA')},
    {'chave': 'PT_CERTIDAO_CANCELAMENTO', 'padrao': ('protesto_certidao', 'MODELO_CERTIDAO_CANCELAMENTO')},
    _peca('PT_CERTIDAO_PEDIDO_VERBAL', 'protesto_certidao', 'FRASE_PEDIDO_VERBAL'),
    _peca('PT_CERTIDAO_PEDIDO_REQUERENTE', 'protesto_certidao', 'FRASE_PEDIDO_REQUERENTE'),
    _peca('PT_CERTIDAO_PEDIDO_DEVEDOR', 'protesto_certidao', 'FRASE_PEDIDO_DEVEDOR'),
    _peca('PT_CERTIDAO_PEDIDO_JUDICIAL', 'protesto_certidao', 'FRASE_PEDIDO_JUDICIAL'),
    _peca('PT_CERTIDAO_IDENTIFICACAO', 'protesto_certidao', 'FRASE_IDENTIFICACAO'),
    _peca('PT_CERTIDAO_INSCRITO', 'protesto_certidao', 'FRASE_INSCRITO'),
    _peca('PT_CERTIDAO_CABECA', 'protesto_certidao', 'FRASE_CABECA'),
    _peca('PT_CERTIDAO_FECHO_UM', 'protesto_certidao', 'FRASE_FECHO_UM'),
    _peca('PT_CERTIDAO_FECHO_VARIOS', 'protesto_certidao', 'FRASE_FECHO_VARIOS'),
    _peca('PT_CERTIDAO_LINHA', 'protesto_certidao', 'LINHA_DO_PROTESTO'),
    {'chave': 'PT_AVISO_INTIMACAO', 'padrao': ('protesto_aviso', 'AVISO_DE_INTIMACAO')},
    _peca('PT_AVISO_ROTULOS', 'protesto_aviso', 'ROTULOS_DO_AVISO'),
    _peca('PT_AVISO_CANHOTO_TITULO', 'protesto_aviso', 'CANHOTO_TITULO'),
    _peca('PT_AVISO_CANHOTO_IDENTIFICACAO', 'protesto_aviso', 'CANHOTO_IDENTIFICACAO'),
    _peca('PT_AVISO_CANHOTO_CAMPOS', 'protesto_aviso', 'CANHOTO_CAMPOS'),
    _peca('PT_AVISO_CANHOTO_TENTATIVAS_TITULO', 'protesto_aviso',
          'CANHOTO_TENTATIVAS_TITULO'),
    _peca('PT_AVISO_CANHOTO_TENTATIVA', 'protesto_aviso', 'CANHOTO_TENTATIVA'),
    {'chave': 'PT_EDITAL_INTIMACAO', 'padrao': ('protesto_aviso', 'EDITAL_DE_INTIMACAO')},
    _peca('PT_EDITAL_ROTULOS', 'protesto_aviso', 'ROTULOS_DO_EDITAL'),
    _peca('PT_ESPECIES', 'protesto_aviso', 'ESPECIES_NO_PAPEL'),
    _peca('PT_LIVRO_PROTOCOLO', 'protesto_livros', 'OCORRENCIA_DO_ATO'),
    _peca('PT_LIVRO_PAGAMENTOS', 'protesto_livros', 'FORMAS'),
    # LD04 (21/10/2026): a quitação do título pago no tabelionato, que não
    # tinha papel (Lei 9.492, art. 19, § 2º; CN-MA art. 927).
    {'chave': 'PT_QUITACAO', 'padrao': ('protesto_livros', 'QUITACAO_DO_TITULO')},
    _peca('PT_MOLDURAS', 'protesto_pecas', 'MOLDURA_DOS_PAPEIS'),
)

# A TIPAGEM DOS PAPÉIS DO LF06E FICA AO LADO DELES: todos são texto, e a peça
# diz que é frase. Os cinco de antes continuam em `tipagem.py`.
_TIPOS.update({
    c['chave']: ('TEXTO', 'Peça — frase que a regra escolhe' if c.get('peca') else None)
    for c in PAPEIS if c['chave'] not in _TIPOS})
