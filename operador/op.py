"""O `op` — o atalho único das ferramentas do superusuário. O posto gera
`./op` (e `op.cmd` no Windows), e as instruções só falam dele.

POR QUE UM ATALHO: o operador trabalha de dentro do posto, e não da pasta do
sistema; sem o atalho, cada ferramenta seria um caminho comprido, diferente em
cada servidor — e caminho comprido é onde o modelo erra.

    op consulta "SELECT ..."                       lê o banco (só leitura)
    op sql mudanca.sql --tabelas a,b --motivo "…"  grava, com cópia antes
    op nota "o que achei e por que decidi assim"   vai para o relatório
    op guardar <arquivo> [...]                     guarda o original antes de editar pelo shell
    op lembrar "fato que vale daqui para a frente" vai para a memória
    op procurar <termo>                            memória e diário, daqui e do outro servidor
    op diario [quantos]                            os últimos pedidos
    op robos quadro                                toda a automação e os robôs, e O QUE FALTA
    op robos conta <login> --cofre <item>          cria a conta de robô ou troca a senha (ela não aparece)
    op robos responsavel <login>                   define quem responde pelo robô, sem mexer na senha
    op robos ligar|desligar|rodar <código>         liga, desliga ou roda agora uma rotina
    op robos semear                                cadastra as rotinas de fábrica novas
    op rodar -- <comando>                          roda na pasta do sistema, com o ambiente da casa
    op enviar <arquivo> [...]                      devolve o arquivo ao oficial com a resposta
    op situacao                                    em que servidor estou, e em que pé ele está
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import bandeja as BANDEJA  # noqa: E402
import conhecimento as CONH  # noqa: E402
import intervencao as INT  # noqa: E402

AJUDA = __doc__.split("\n\n", 2)[2].rstrip()


def rodar(comando: list[str]) -> int:
    """Um comando na pasta do sistema, com o banco e a pasta de dados que o
    servidor tem AGORA. `python` vira o Python do próprio sistema."""
    if comando and comando[0] == "--":
        comando = comando[1:]
    if not comando:
        print("Diga o comando: op rodar -- python tools/algum.py", file=sys.stderr)
        return 2
    if comando[0].lower() in ("python", "python3", "py", "python.exe"):
        comando = [sys.executable, *comando[1:]]
    try:
        return subprocess.run(comando, cwd=str(INT.raiz_do_sistema())).returncode
    except OSError as falha:
        print(f"Não consegui rodar: {falha}", file=sys.stderr)
        return 1


def enviar(arquivos: list[str]) -> int:
    """Põe o arquivo na saída do pedido: a porta o devolve ao oficial junto
    com a resposta. Só existe quando o pedido veio pela ponte."""
    saida = (os.environ.get("OPERADOR_SAIDA") or "").strip()
    if not saida:
        print("Nesta porta (app do Claude) não há envio de arquivo: diga ao "
              "oficial o caminho inteiro do arquivo.", file=sys.stderr)
        return 1
    if not arquivos:
        print("Diga o arquivo: op enviar <arquivo>", file=sys.stderr)
        return 2
    destino = Path(saida)
    destino.mkdir(parents=True, exist_ok=True)
    for arquivo in arquivos:
        origem = Path(arquivo)
        if not origem.is_file():
            print(f"Não achei o arquivo: {arquivo}", file=sys.stderr)
            return 1
        shutil.copyfile(origem, destino / BANDEJA.nome_seguro(origem.name))
        print(f"Vai junto com a resposta: {origem.name}")
    return 0


def main(argv: list[str] | None = None) -> int:
    for saida in (sys.stdout, sys.stderr):
        try:
            saida.reconfigure(encoding="utf-8")
        except (AttributeError, OSError):
            pass
    argv = list(sys.argv[1:] if argv is None else argv)
    if not argv or argv[0] in ("-h", "--help", "ajuda"):
        print(AJUDA)
        return 0
    comando, resto = argv[0], argv[1:]
    INT.carregar_ambiente()
    if comando in ("consulta", "sql", "nota", "guardar"):
        return INT.main([comando, *resto])
    if comando in ("lembrar", "procurar", "diario", "memoria"):
        return CONH.main([comando, *resto])
    if comando == "robos":
        import robos as ROBOS        # só aqui: ele carrega os módulos da casa
        return ROBOS.main(resto)
    if comando == "rodar":
        return rodar(resto)
    if comando == "enviar":
        return enviar(resto)
    if comando == "situacao":
        print(f"Servidor {INT.servidor()} — {INT.situacao()}.")
        return 0
    print(f"Não conheço «{comando}».\n\n{AJUDA}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
