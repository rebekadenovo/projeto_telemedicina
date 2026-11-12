import os
from pathlib import Path

from dotenv import load_dotenv
from neo4j import GraphDatabase

PASTA = Path(__file__).resolve().parent


def ler_comandos(caminho):
    """Lê o arquivo .cypher, remove os comentários e separa os comandos por ponto e vírgula."""
    linhas = [
        linha for linha in caminho.read_text(encoding="utf-8").splitlines()
        if not linha.strip().startswith("//")
    ]
    return [comando.strip() for comando in "\n".join(linhas).split(";") if comando.strip()]


def main():
    load_dotenv(PASTA / ".env")
    uri = os.getenv("NEO4J_URI")
    usuario = os.getenv("NEO4J_USERNAME")
    senha = os.getenv("NEO4J_PASSWORD")
    if not (uri and usuario and senha):
        raise SystemExit("Preencha NEO4J_URI, NEO4J_USERNAME e NEO4J_PASSWORD no arquivo .env.")
    banco = os.getenv("NEO4J_DATABASE") or None

    comandos = ler_comandos(PASTA / "grafo_clinico.cypher")
    with GraphDatabase.driver(uri, auth=(usuario, senha)) as driver:
        driver.verify_connectivity()
        for comando in comandos:
            driver.execute_query(comando, database_=banco)

        registros, _, _ = driver.execute_query(
            "MATCH (n) RETURN labels(n)[0] AS tipo, count(*) AS total ORDER BY tipo",
            database_=banco,
        )
        relacoes, _, _ = driver.execute_query(
            "MATCH ()-[r]->() RETURN type(r) AS tipo, count(*) AS total ORDER BY tipo",
            database_=banco,
        )

    print(f"Comandos executados: {len(comandos)}.")
    print("Nós:", ", ".join(f"{r['tipo']} {r['total']}" for r in registros))
    print("Relações:", ", ".join(f"{r['tipo']} {r['total']}" for r in relacoes))


if __name__ == "__main__":
    main()
