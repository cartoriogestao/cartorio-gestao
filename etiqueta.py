"""Medidas das etiquetas usadas no Cartório Gestão.

Reconhecimento de firma, autenticação e registro do RCPJ/RTD usam a mesma
bobina física de 100 × 30 mm. Por isso largura, altura, margem e deslocamento
do RTDPJ leem as chaves já usadas pela etiqueta de firma: uma calibração da
impressora vale para todas as impressões nessa bobina.

O conteúdo registral é mais comprido. Corpo, entrelinha e QR continuam em
chaves próprias (`etiqueta_registro_*`) para permitir uma composição compacta
sem reduzir a letra dos reconhecimentos. A etiqueta de averbação do RCPN, que
é colada na margem do livro, mantém configuração física independente.
"""
from __future__ import annotations

RECONHECIMENTO = "RECONHECIMENTO"
REGISTRO_RTDPJ = "REGISTRO_RTDPJ"
AVERBACAO_RCPN = "AVERBACAO_RCPN"

# AS MEDIDAS, com o nome que os modelos de tela usam.
#
#   **O NOME DA MEDIDA É O MESMO NAS CONFIGURAÇÕES**; o que muda é a chave
#   com que cada uma se GRAVA (ver `PREFIXO_DA_CONFIGURACAO`). Assim
#   `etiqueta.html` lê `m.etiqueta_largura_mm` sem saber de qual etiqueta é —
#   e os ajustes ficam independentes, que é o ponto.
MEDIDAS = ("etiqueta_largura_mm", "etiqueta_altura_mm", "etiqueta_margem_mm",
           "etiqueta_deslocamento_x_mm", "etiqueta_deslocamento_y_mm",
           "etiqueta_corpo_pt", "etiqueta_entrelinha", "etiqueta_qr_mm")

# O RECONHECIMENTO DE FIRMA — 100 × 30 mm.
#
#   **E AS CHAVES DE GRAVAÇÃO DELE NÃO MUDAM**: o oficial pode já ter ajustado
#   a tira dele no balcão, e renomear a chave apagaria o ajuste sem avisar.
PADRAO_DO_RECONHECIMENTO: dict[str, str] = {
    "etiqueta_largura_mm": "100",
    "etiqueta_altura_mm": "30",
    "etiqueta_margem_mm": "0.8",
    "etiqueta_deslocamento_x_mm": "0",
    "etiqueta_deslocamento_y_mm": "1",
    "etiqueta_corpo_pt": "9",
    "etiqueta_entrelinha": "1.08",
    "etiqueta_qr_mm": "12",
}

# A ETIQUETA DE REGISTRO DO RCPJ/RTD — a mesma tira física de 100 × 30 mm
# do reconhecimento, com corpo 6 para caber o teor registral.
PADRAO_DO_REGISTRO: dict[str, str] = {
    "etiqueta_largura_mm": "100",
    "etiqueta_altura_mm": "30",
    "etiqueta_margem_mm": "0.8",
    "etiqueta_deslocamento_x_mm": "0",
    "etiqueta_deslocamento_y_mm": "1",
    "etiqueta_corpo_pt": "6",
    "etiqueta_entrelinha": "1.15",
    "etiqueta_qr_mm": "16",
}

# A ETIQUETA DE AVERBAÇÃO DO RCPN — cola na margem do livro.
#
#   Mais estreita que firma/RTD: a faixa do livro é justa, e o balcão só usa
#   parte da tira. Largura/altura/margem são ajustáveis na tela; estes números
#   são o ponto de partida, não medida de térmica.
PADRAO_DA_AVERBACAO: dict[str, str] = {
    "etiqueta_largura_mm": "55",
    "etiqueta_altura_mm": "50",
    "etiqueta_margem_mm": "1.5",
    "etiqueta_deslocamento_x_mm": "0",
    "etiqueta_deslocamento_y_mm": "0",
    "etiqueta_corpo_pt": "7",
    "etiqueta_entrelinha": "1.1",
    "etiqueta_qr_mm": "0",
}

PADROES: dict[str, dict[str, str]] = {
    RECONHECIMENTO: PADRAO_DO_RECONHECIMENTO,
    REGISTRO_RTDPJ: PADRAO_DO_REGISTRO,
    AVERBACAO_RCPN: PADRAO_DA_AVERBACAO,
}

NOME_DA_CONFIGURACAO: dict[str, str] = {
    RECONHECIMENTO: "Etiqueta de reconhecimento de firma e autenticação",
    REGISTRO_RTDPJ: "Etiqueta de registro do RCPJ e do RTD",
    AVERBACAO_RCPN: "Etiqueta de averbação do RCPN (margem do livro)",
}

# COM QUE PREFIXO CADA UMA SE GRAVA NAS CONFIGURAÇÕES.
#
#   O reconhecimento fica **sem prefixo**, e isso não é assimetria por
#   descuido: as chaves dele já existem gravadas no servidor desde 27/08/2026.
#   Prefixá-las agora faria o sistema ler o padrão de fábrica por cima do
#   ajuste que o oficial fez na tira — e ninguém saberia por quê.
PREFIXO_DA_CONFIGURACAO: dict[str, str] = {
    RECONHECIMENTO: "",
    REGISTRO_RTDPJ: "registro_",
    AVERBACAO_RCPN: "averbacao_",
}

# A bobina e a calibração são as mesmas do reconhecimento. Corpo, entrelinha e
# QR continuam próprios porque o teor registral é mais comprido.
GEOMETRIA_COMPARTILHADA_RTDPJ = (
    "etiqueta_largura_mm", "etiqueta_altura_mm", "etiqueta_margem_mm",
    "etiqueta_deslocamento_x_mm", "etiqueta_deslocamento_y_mm",
)


def configuracoes() -> tuple[str, ...]:
    """As configurações que existem. Só calcula."""
    return tuple(PADROES)


def chave_gravada(configuracao: str, medida: str) -> str:
    """Com que nome aquela medida daquela etiqueta se grava. Só calcula.

    `('RECONHECIMENTO', 'etiqueta_largura_mm')` -> `etiqueta_largura_mm`
    `('REGISTRO_RTDPJ',  'etiqueta_largura_mm')` -> `etiqueta_registro_largura_mm`
    `('AVERBACAO_RCPN',  'etiqueta_largura_mm')` -> `etiqueta_averbacao_largura_mm`
    """
    prefixo = PREFIXO_DA_CONFIGURACAO.get(configuracao, "")
    if not prefixo:
        return medida
    # O prefixo entra DEPOIS de «etiqueta_», para as chaves da casa ficarem
    # todas agrupadas quando alguém abrir a tabela de configurações.
    return medida.replace("etiqueta_", "etiqueta_" + prefixo, 1)


def padrao_gravado(configuracao: str) -> dict[str, str]:
    """`{chave gravada: valor padrão}` daquela etiqueta. Só calcula.

    É o que a tela de ajuste percorre: ela precisa do nome com que grava, e não
    do nome da medida.
    """
    padroes = PADROES.get(configuracao) or {}
    return {chave_gravada(configuracao, medida): valor
            for medida, valor in padroes.items()}


def medidas(get_settings, configuracao: str = RECONHECIMENTO) -> dict[str, float]:
    """As medidas gravadas daquela etiqueta, com o padrão como rede. Só LÊ.

    **NÚMERO INVÁLIDO NAS CONFIGURAÇÕES NÃO PODE VIRAR ETIQUETA EM BRANCO**:
    alguém digita «10 mm» com a unidade junto, e a impressão do balcão para. O
    valor que não vira número cai no padrão da configuração.

    **E o zero só vale para o deslocamento (e para o QR da averbação).**
    Largura zero, corpo zero ou entrelinha zero são a tira em branco por outro
    caminho; deslocamento zero é a resposta certa — quer dizer «o driver não
    empurrou nada». QR zero na averbação quer dizer «sem QR nesta tira».
    """
    if configuracao not in PADROES:
        raise ValueError(
            f"«{configuracao}» não é uma etiqueta desta casa. São: "
            f"{', '.join(PADROES)}.")
    gravadas = get_settings()
    saida: dict[str, float] = {}
    for medida, padrao in PADROES[configuracao].items():
        bruto = str(gravadas.get(chave_gravada(configuracao, medida), "")
                    or "").replace(",", ".").strip()
        try:
            valor = float(bruto)
        except ValueError:
            valor = float(padrao)
        permite_zero = (
            medida.startswith("etiqueta_desloc")
            or (medida == "etiqueta_qr_mm" and configuracao == AVERBACAO_RCPN)
        )
        saida[medida] = (valor if valor or permite_zero else float(padrao))
    return saida


def chave_registro_rtdpj(medida: str) -> str:
    """Chave da etiqueta RTDPJ: geometria compartilhada, texto próprio."""
    configuracao = (RECONHECIMENTO if medida in GEOMETRIA_COMPARTILHADA_RTDPJ
                    else REGISTRO_RTDPJ)
    return chave_gravada(configuracao, medida)


def medidas_registro_rtdpj(get_settings) -> dict[str, float]:
    """Medidas do RTDPJ na bobina 100 x 30 usada no reconhecimento."""
    fisica = medidas(get_settings, RECONHECIMENTO)
    texto = medidas(get_settings, REGISTRO_RTDPJ)
    for medida in ("etiqueta_corpo_pt", "etiqueta_entrelinha", "etiqueta_qr_mm"):
        fisica[medida] = texto[medida]
    return fisica
