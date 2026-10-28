#!/usr/bin/env python3
"""Copia os dados do SQLite local para um banco Postgres na nuvem.

Uso típico (na pasta do projeto, com o virtualenv ativo):

    python migrar_para_postgres.py \
        --destino "postgresql://usuario:senha@host/banco?sslmode=require"

O script cria as tabelas no destino, copia obreiros, lançamentos, usuários e
mensalidades (nessa ordem, respeitando as chaves estrangeiras) e ajusta as
sequências do Postgres. Por segurança, ele se recusa a gravar em um banco que
já tenha dados, a menos que ``--limpar`` seja informado.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from sqlalchemy import MetaData, Table, create_engine, func, select, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import OperationalError

from database import DATA_DIR, Base, _migrar_esquema, _normalizar_url

import models  # noqa: F401  # registra as tabelas no metadata

TABELAS = ("obreiros", "financeiro", "usuarios", "mensalidades")


def _criar_engine(url: str) -> Engine:
    parametros: dict = {"pool_pre_ping": True, "future": True}
    if url.startswith("sqlite"):
        parametros["connect_args"] = {"check_same_thread": False}
    elif url.startswith("postgresql+psycopg"):
        parametros["connect_args"] = {"prepare_threshold": None}
    return create_engine(url, **parametros)


def _contar(engine: Engine, tabela: str) -> int:
    with engine.connect() as conexao:
        return int(
            conexao.scalar(
                select(func.count()).select_from(Base.metadata.tables[tabela])
            )
            or 0
        )


def _limpar_destino(engine: Engine) -> None:
    with engine.begin() as conexao:
        for nome in reversed(TABELAS):
            conexao.execute(Base.metadata.tables[nome].delete())


def _copiar(origem: Engine, destino: Engine) -> None:
    metadata_origem = MetaData()
    with destino.begin() as conexao_destino:
        for nome in TABELAS:
            tabela_origem = Table(
                nome,
                metadata_origem,
                autoload_with=origem,
            )
            tabela_destino = Base.metadata.tables[nome]

            with origem.connect() as conexao_origem:
                registros = [
                    {
                        chave: valor
                        for chave, valor in linha._mapping.items()
                        if chave in tabela_destino.c
                    }
                    for linha in conexao_origem.execute(
                        select(tabela_origem)
                    ).all()
                ]

            if registros:
                conexao_destino.execute(tabela_destino.insert(), registros)
            print(f"  {nome}: {len(registros)} registro(s)")


def _resetar_sequencias(engine: Engine) -> None:
    """Ajusta as sequências do Postgres para o próximo id não colidir."""
    if engine.dialect.name != "postgresql":
        return

    with engine.begin() as conexao:
        for nome in TABELAS:
            conexao.execute(
                text(
                    "SELECT setval("
                    "pg_get_serial_sequence(:tabela, 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {nome}), 1), "
                    f"(SELECT MAX(id) FROM {nome}) IS NOT NULL"
                    ")"
                ),
                {"tabela": nome},
            )


def _resumo(engine: Engine) -> None:
    print("\nResumo do banco de destino:")
    for nome in TABELAS:
        print(f"  {nome}: {_contar(engine, nome)} registro(s)")


def _validar_origem(url: str) -> None:
    if not url.startswith("sqlite"):
        return
    caminho = url.removeprefix("sqlite:///")
    if caminho and not Path(caminho).exists():
        raise SystemExit(
            f"Banco de origem não encontrado: {caminho}\n"
            "Informe o caminho correto com --origem."
        )


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Migra os dados do SQLite local para um Postgres na nuvem."
    )
    parser.add_argument(
        "--origem",
        default=f"sqlite:///{DATA_DIR / 'loja.db'}",
        help="URL SQLAlchemy do banco de origem (padrão: SQLite local).",
    )
    parser.add_argument(
        "--destino",
        default=os.getenv("DATABASE_URL", ""),
        help=(
            "URL do Postgres de destino. Se omitida, usa a variável "
            "DATABASE_URL."
        ),
    )
    parser.add_argument(
        "--limpar",
        action="store_true",
        help="Apaga os dados existentes no destino antes de copiar.",
    )
    parser.add_argument(
        "--sim",
        action="store_true",
        help="Não pede confirmação ao usar --limpar.",
    )
    args = parser.parse_args()

    origem_url = _normalizar_url(args.origem)
    destino_url = _normalizar_url(args.destino)

    if not destino_url:
        parser.error(
            "Informe --destino ou defina DATABASE_URL com a URL do Postgres."
        )
    if destino_url.startswith("sqlite"):
        parser.error(
            "O destino deve ser um Postgres na nuvem, não um arquivo SQLite."
        )
    if origem_url == destino_url:
        parser.error("Origem e destino não podem ser o mesmo banco.")

    _validar_origem(origem_url)

    print(f"Origem:  {origem_url}")
    print(f"Destino: {destino_url.split('@')[-1]}")

    try:
        origem = _criar_engine(origem_url)
        destino = _criar_engine(destino_url)
        with origem.connect():
            pass
        with destino.connect():
            pass
    except OperationalError as erro:
        print(f"\nNão foi possível conectar ao banco: {erro}", file=sys.stderr)
        return 1

    Base.metadata.create_all(bind=destino)
    _migrar_esquema(destino)

    existentes = {nome: _contar(destino, nome) for nome in TABELAS}
    total_existente = sum(existentes.values())
    if total_existente and not args.limpar:
        print(
            "\nO banco de destino já contém dados:",
            ", ".join(f"{nome}={qtd}" for nome, qtd in existentes.items()),
            file=sys.stderr,
        )
        print(
            "Para substituir esses dados, rode novamente com --limpar.\n"
            "Se quiser preservá-los, use um banco vazio.",
            file=sys.stderr,
        )
        return 2

    if total_existente and args.limpar:
        if not args.sim:
            resposta = input(
                "Isso apagará TODOS os dados do destino. "
                "Digite MIGRAR para continuar: "
            )
            if resposta.strip().upper() != "MIGRAR":
                print("Operação cancelada.")
                return 1
        print("Limpando o banco de destino...")
        _limpar_destino(destino)

    print("\nCopiando dados:")
    try:
        _copiar(origem, destino)
        _resetar_sequencias(destino)
    except Exception as erro:  # noqa: BLE001
        print(f"\nFalha na migração: {erro}", file=sys.stderr)
        print("Nenhuma alteração parcial foi confirmada.", file=sys.stderr)
        return 1

    _resumo(destino)
    print("\nMigração concluída.")
    print("Agora configure DATABASE_URL nos Secrets do Streamlit Cloud.")
    print("As senhas atuais continuam válidas: os hashes foram copiados.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
