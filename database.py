"""Conexão e inicialização do banco de dados.

Por padrão usa SQLite local (``data/loja.db``). Para migrar para a nuvem,
basta definir a variável de ambiente ``DATABASE_URL`` com uma URL compatível
com SQLAlchemy, por exemplo::

    DATABASE_URL=postgresql+psycopg://usuario:senha@host:5432/loja

Nenhum código da aplicação depende de SQL específico do SQLite.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event, inspect, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
DATA_DIR.mkdir(exist_ok=True)

# .env é opcional: se python-dotenv estiver instalado, carrega as variáveis.
try:  # pragma: no cover - dependência opcional
    from dotenv import load_dotenv

    load_dotenv(BASE_DIR / ".env")
except ImportError:  # pragma: no cover
    pass

def _normalizar_url(url: str) -> str:
    """Aceita a URL copiada do provedor e usa o driver psycopg (v3).

    Neon, Supabase e Render costumam entregar ``postgresql://...`` ou
    ``postgres://...``. O SQLAlchemy, sem driver explícito, tentaria o
    psycopg2. Convertemos para ``postgresql+psycopg://``.
    """
    url = (url or "").strip()
    if url.startswith("postgres://"):
        return "postgresql+psycopg://" + url[len("postgres://") :]
    if url.startswith("postgresql://"):
        return "postgresql+psycopg://" + url[len("postgresql://") :]
    return url


def _url_do_banco() -> str:
    """Resolve a URL do banco: variável de ambiente, segredos ou SQLite local.

    A ordem permite usar o mesmo código no computador da Loja (SQLite) e em
    um servidor na nuvem (por exemplo, Postgres), sem alterar a aplicação.
    """
    url = os.getenv("DATABASE_URL")
    if url:
        return _normalizar_url(url)

    # st.secrets é opcional: em execução fora do Streamlit (scripts e testes)
    # a leitura simplesmente falha e seguimos para o SQLite local.
    try:  # pragma: no cover - depende do ambiente do Streamlit
        import streamlit as st

        url = st.secrets.get("DATABASE_URL")
    except Exception:  # noqa: BLE001
        url = None
    if url:
        return _normalizar_url(str(url))

    return f"sqlite:///{DATA_DIR / 'loja.db'}"


DATABASE_URL = _url_do_banco()

_parametros_engine: dict = {
    "pool_pre_ping": True,
    "future": True,
}
if DATABASE_URL.startswith("sqlite"):
    _parametros_engine["connect_args"] = {"check_same_thread": False}
elif DATABASE_URL.startswith("postgresql+psycopg"):
    # Evita conexões ociosas derrubadas pelo provedor (Neon/Supabase).
    _parametros_engine["pool_recycle"] = 300
    # Compatibilidade com poolers (PgBouncer em modo transaction), usados
    # pelas connection strings "pooled" de Neon e Supabase.
    _parametros_engine["connect_args"] = {"prepare_threshold": None}

engine = create_engine(DATABASE_URL, **_parametros_engine)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    """Base declarativa dos modelos."""


if DATABASE_URL.startswith("sqlite"):

    @event.listens_for(engine, "connect")
    def _habilitar_chaves_estrangeiras(dbapi_connection, _record):  # noqa: ANN001
        """SQLite ignora chaves estrangeiras por padrão; habilita por conexão."""
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()


def _adicionar_coluna(alvo, tabela: str, coluna: str, tipo: str) -> None:
    """Adiciona uma coluna se ainda não existir (idempotente)."""
    colunas = {c["name"] for c in inspect(alvo).get_columns(tabela)}
    if coluna in colunas:
        return
    try:
        with alvo.begin() as conexao:
            conexao.execute(
                text(f"ALTER TABLE {tabela} ADD COLUMN {coluna} {tipo}")
            )
    except Exception:
        # Duas sessões podem iniciar ao mesmo tempo; se outra já aplicou
        # a coluna, a migração está concluída. Caso contrário, propague.
        atuais = {c["name"] for c in inspect(alvo).get_columns(tabela)}
        if coluna not in atuais:
            raise


def _sqlite_reconstruir_obreiros(alvo) -> None:
    """Recria a tabela ``obreiros`` no SQLite para atualizar o CHECK de grau.

    O SQLite não permite alterar uma CHECK constraint existente. A recriação
    preserva os dados e os vínculos: ``legacy_alter_table`` evita que o
    ``RENAME`` reescreva as chaves estrangeiras das tabelas filhas.
    """
    from sqlalchemy.schema import CreateTable

    import models

    ddl = str(CreateTable(models.Obreiro.__table__).compile(dialect=alvo.dialect))
    colunas = ", ".join(c.name for c in models.Obreiro.__table__.columns)

    bruto = alvo.raw_connection()
    try:
        cursor = bruto.cursor()
        cursor.execute("PRAGMA foreign_keys=OFF")
        cursor.execute("PRAGMA legacy_alter_table=ON")
        cursor.execute("BEGIN")
        try:
            cursor.execute("ALTER TABLE obreiros RENAME TO obreiros_antigo")
            cursor.execute(ddl)
            cursor.execute(
                f"INSERT INTO obreiros ({colunas}) "
                f"SELECT {colunas} FROM obreiros_antigo"
            )
            cursor.execute("DROP TABLE obreiros_antigo")
        except Exception:
            cursor.execute("ROLLBACK")
            raise
        cursor.execute("COMMIT")
        cursor.execute("PRAGMA legacy_alter_table=OFF")
        cursor.execute("PRAGMA foreign_keys=ON")
    finally:
        bruto.close()


def _atualizar_graus(alvo) -> None:
    """Garante que o CHECK de ``grau`` aceite todos os valores de ``GRAUS``."""
    from constants import GRAUS

    alvo_sql = ", ".join(f"'{grau}'" for grau in GRAUS)

    if alvo.dialect.name == "sqlite":
        with alvo.connect() as conexao:
            ddl = conexao.execute(
                text(
                    "SELECT sql FROM sqlite_master "
                    "WHERE type = 'table' AND name = 'obreiros'"
                )
            ).scalar()
        if ddl and all(f"'{grau}'" in ddl for grau in GRAUS):
            return
        _sqlite_reconstruir_obreiros(alvo)
        return

    if alvo.dialect.name != "postgresql":
        return

    with alvo.begin() as conexao:
        definicao = conexao.execute(
            text(
                "SELECT pg_get_constraintdef(oid) FROM pg_constraint "
                "WHERE conname = 'ck_obreiros_grau'"
            )
        ).scalar()
        if definicao and all(f"'{grau}'" in definicao for grau in GRAUS):
            return
        conexao.execute(
            text("ALTER TABLE obreiros DROP CONSTRAINT IF EXISTS ck_obreiros_grau")
        )
        conexao.execute(
            text(
                "ALTER TABLE obreiros ADD CONSTRAINT ck_obreiros_grau "
                f"CHECK (grau IN ({alvo_sql}))"
            )
        )


def _migrar_esquema(engine_alvo=None) -> None:
    """Aplica alterações aditivas em bancos criados por versões anteriores.

    ``create_all`` não altera tabelas existentes. Aqui garantimos as colunas
    novas sem perder dados. Cada passo é idempotente e seguro para reexecução.
    ``engine_alvo`` permite aplicar a migração também no banco de destino do
    script de cópia.
    """
    alvo = engine_alvo or engine
    inspetor = inspect(alvo)
    tabelas = inspetor.get_table_names()

    if "usuarios" in tabelas:
        _adicionar_coluna(
            alvo,
            "usuarios",
            "deve_trocar_credenciais",
            "BOOLEAN NOT NULL DEFAULT FALSE",
        )

    if "obreiros" in tabelas:
        _adicionar_coluna(alvo, "obreiros", "cpf", "VARCHAR(14)")
        _adicionar_coluna(alvo, "obreiros", "telefone", "VARCHAR(20)")
        _atualizar_graus(alvo)


def init_db() -> None:
    """Cria as tabelas que ainda não existem e aplica migrações (idempotente)."""
    import models  # noqa: F401  # registra os modelos no metadata

    Base.metadata.create_all(bind=engine)
    _migrar_esquema()


def descricao_banco() -> str:
    """Rótulo amigável do banco em uso, exibido na interface."""
    if engine.dialect.name == "sqlite":
        return "SQLite local"
    if engine.dialect.name == "postgresql":
        return "PostgreSQL"
    return engine.dialect.name.capitalize()
