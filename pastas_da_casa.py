"""As pastas da casa — onde o Cartório Gestão lê e grava os seus arquivos.

HOTFIX DE 16/10/2026: NADA MAIS APONTA PARA `C:\\ARPNET`.
    `C:\\ARPNET` é a pasta do E-Ofício, o sistema anterior. O código tinha
    sete caminhos padrão lá dentro — e um deles, o das cargas do RCPN, era
    ESCRITO: a suíte de testes, rodada no servidor, gravava arquivos de
    serventia fictícia na pasta de onde o balcão sobe as cargas, e apagava os
    do dia com o mesmo prefixo.

    Agora tudo mora sob a raiz dos arquivos da casa (`archive_root`, ou
    `<pasta de dados>\\arquivos`), na convenção que o `copiar_arquivos_eoficio`
    já usava para as firmas:

        <arquivos>\\eoficio\\<nome>   o que veio do E-Ofício, só leitura
                                    (Firmas, IPDigital, CRA, ONR, IBGE_EXP…)
        <arquivos>\\rcpn\\cargas      o que o próprio sistema gera para subir

    A configuração gravada no banco continua mandando: quem escolheu outra
    pasta na tela continua com ela. Este módulo só decide o PADRÃO.
"""
from __future__ import annotations

import os
from pathlib import Path, PureWindowsPath

# O de-para do hotfix: caminho antigo do E-Ofício -> lugar novo, relativo à
# raiz dos arquivos. Usado pela correção das configurações gravadas no banco
# e pelo roteiro que move os arquivos. Do mais específico para o mais geral.
DE_PARA: tuple[tuple[str, str], ...] = (
    # As imagens do ONR JA ESTAO na pasta do Gestao (carga de 17/08/2026,
    # 10.227 arquivos): o de-para aponta para ela (19/10/2026).
    (r"C:\ARPNET\C11\ONR\IMAGENS", r"eoficio\ONR_IMAGENS"),
    (r"C:\ARPNET\C11\CARGAS_RCPN", r"rcpn\cargas"),
    (r"C:\ARPNET\C11", r"eoficio"),
    (r"C:\ARPNET\CRA", r"eoficio\CRA"),
    (r"C:\ARPNET", r"eoficio"),
)


def raiz_dos_arquivos(*, banco=None, archive_root: str | None = None) -> Path:
    """A raiz dos arquivos da casa.

    Ordem: `archive_root` configurado; senão `arquivos/` ao lado do banco (o
    banco mora na pasta de dados); senão a pasta de dados do sistema.
    """
    configurada = (archive_root or "").strip()
    if configurada:
        return Path(configurada)
    if banco:
        return Path(banco).resolve().parent / "arquivos"
    dados = os.environ.get("CARTORIO_GESTAO_DATA")
    if dados:
        return Path(dados).expanduser().resolve() / "arquivos"
    from app import get_data_dir  # tarde, para não importar o Flask à toa
    return get_data_dir() / "arquivos"


def do_eoficio(*partes: str, banco=None, archive_root: str | None = None) -> Path:
    """O que veio do E-Ofício: `<arquivos>/eoficio/<partes>`. Só leitura."""
    return raiz_dos_arquivos(banco=banco, archive_root=archive_root).joinpath("eoficio", *partes)


def cargas_rcpn(*, banco=None, archive_root: str | None = None) -> Path:
    """Onde o agente de cargas do RCPN deixa os arquivos do dia."""
    return raiz_dos_arquivos(banco=banco, archive_root=archive_root) / "rcpn" / "cargas"


class ForaDaCasa(ValueError):
    """O caminho digitado na tela não fica dentro das pastas da casa."""


def raizes_da_casa(*, data_dir, archive_root: str | None = None,
                   importacao: str = "") -> list[Path]:
    """As pastas onde um caminho DIGITADO NA TELA pode apontar. Só calcula.

    A pasta de dados, a raiz dos arquivos, a pasta do E-Ofício dentro dela e as
    pastas de importação que o oficial gravou em Configurações
    (`pastas_de_importacao`, uma por linha). Ver `dentro_da_casa`.
    """
    configurada = (archive_root or "").strip()
    arquivos = (Path(configurada).expanduser() if configurada
                else Path(data_dir) / "arquivos")
    saida = [Path(data_dir), arquivos, arquivos / "eoficio"]
    for linha in (importacao or "").splitlines():
        if linha.strip():
            saida.append(Path(linha.strip()))
    return saida


def _rede(texto: str) -> bool:
    r"""`\\maquina\...`, `//maquina/...` e os prefixos `\\?\`/`\\.\`."""
    return texto.startswith(("\\\\", "//"))


def dentro_da_casa(caminho, raizes: list[Path]) -> Path:
    r"""O caminho resolvido, se ele cai dentro de uma das `raizes`. Senão,
    `ForaDaCasa` com a mensagem pronta para o balcão.

    POR QUE (LS02 A1–A3; decisão do oficial no LX12, 19/10/2026)
        Assinaturas, Importar acervo, Livro 3 e Matrículas digitadas aceitavam
        QUALQUER caminho do servidor. O serviço roda como SYSTEM: com
        `\\maquina\pasta` ele abria SMB para fora e entregava a credencial da
        máquina; com um caminho local qualquer, lia o SQLite/JSONL que quisesse,
        trocava o acervo de onde saem as cargas do RCPN, e ligava o cartão de
        firma à imagem que o escrevente escolheu. O balcão continua com os
        campos — só que o caminho tem de morar na casa.

    COMO
        Rede se recusa ANTES de resolver: no Windows, resolver `\\maquina\x` já
        é ir à rede. Caminho relativo também (o diretório do serviço não é o do
        balcão). Depois, `realpath` — que desfaz `..` e atalho — e a
        comparação com cada raiz resolvida do mesmo jeito, sem ligar para caixa
        (o disco do Windows não liga).
    """
    texto = str(caminho or "").strip()
    if not texto:
        raise ForaDaCasa("Informe o caminho.")
    if _rede(texto) or _rede(texto.replace("/", "\\")):
        raise ForaDaCasa(
            f"O caminho {texto} é de rede. O servidor só abre pasta local, "
            f"dentro das pastas da casa — copie os arquivos para lá antes.")
    if not os.path.isabs(texto):
        raise ForaDaCasa(f"Informe o caminho completo (com a unidade): {texto}.")
    alvo = os.path.realpath(texto)
    if _rede(alvo):
        raise ForaDaCasa(f"O caminho {texto} leva para a rede. O servidor só "
                         f"abre pasta local, dentro das pastas da casa.")
    alvo_cmp = os.path.normcase(alvo)
    for raiz in raizes:
        base = os.path.normcase(os.path.realpath(str(raiz)))
        if alvo_cmp == base or alvo_cmp.startswith(base.rstrip("\\/") + os.sep):
            return Path(alvo)
    nomes = "; ".join(str(r) for r in raizes)
    raise ForaDaCasa(
        f"O caminho {texto} fica fora das pastas da casa ({nomes}). Copie os "
        f"arquivos para uma delas, ou peça ao oficial para incluir a pasta em "
        f"Configurações → «Pastas de importação».")


def novo_caminho(antigo: str, raiz: Path) -> Path | None:
    """O lugar novo de um caminho antigo do E-Ofício; None se não é dele."""
    texto = str(PureWindowsPath(antigo or ""))
    for velho, novo in DE_PARA:
        if texto.lower() == velho.lower() or texto.lower().startswith(velho.lower() + "\\"):
            resto = texto[len(velho):].lstrip("\\")
            destino = raiz.joinpath(*PureWindowsPath(novo).parts)
            return destino.joinpath(*PureWindowsPath(resto).parts) if resto else destino
    return None
