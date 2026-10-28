"""Modelos ORM das tabelas do sistema."""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    Index,
    Numeric,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from database import Base


class Obreiro(Base):
    """Cadastro dos obreiros da Loja."""

    __tablename__ = "obreiros"
    __table_args__ = (
        CheckConstraint(
            "grau IN ('Aprendiz', 'Companheiro', 'Mestre', 'Instalado')",
            name="ck_obreiros_grau",
        ),
        CheckConstraint(
            "status IN ('Ativo', 'Inativo')",
            name="ck_obreiros_status",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    cim: Mapped[str] = mapped_column(String(20), nullable=False, unique=True, index=True)
    grau: Mapped[str] = mapped_column(String(20), nullable=False, default="Aprendiz")
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="Ativo")
    cpf: Mapped[Optional[str]] = mapped_column(String(14), nullable=True)
    telefone: Mapped[Optional[str]] = mapped_column(String(20), nullable=True)
    email: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)

    lancamentos: Mapped[list["Lancamento"]] = relationship(back_populates="obreiro")

    def __repr__(self) -> str:  # pragma: no cover - auxiliar de depuração
        return f"Obreiro(id={self.id!r}, nome={self.nome!r}, cim={self.cim!r})"


class Lancamento(Base):
    """Movimentação financeira da Loja.

    ``id_obreiro`` é opcional: só é preenchido quando o lançamento está
    vinculado a um obreiro (mensalidade, capitação, taxa etc.).
    """

    __tablename__ = "financeiro"
    __table_args__ = (
        CheckConstraint("tipo IN ('Entrada', 'Saída')", name="ck_financeiro_tipo"),
        CheckConstraint("valor > 0", name="ck_financeiro_valor_positivo"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    descricao: Mapped[str] = mapped_column(String(200), nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    data: Mapped[date] = mapped_column(Date, nullable=False, default=date.today, index=True)
    id_obreiro: Mapped[Optional[int]] = mapped_column(
        ForeignKey("obreiros.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    obreiro: Mapped[Optional["Obreiro"]] = relationship(back_populates="lancamentos")

    def __repr__(self) -> str:  # pragma: no cover - auxiliar de depuração
        return f"Lancamento(id={self.id!r}, tipo={self.tipo!r}, valor={self.valor!r})"


class Usuario(Base):
    """Usuário de acesso ao sistema.

    ``role`` define o nível de permissão. Usuários do tipo ``Membro`` devem
    estar vinculados a um obreiro para consultar o próprio financeiro.
    """

    __tablename__ = "usuarios"
    __table_args__ = (
        CheckConstraint(
            "role IN ('Administrador', 'Membro')",
            name="ck_usuarios_role",
        ),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    nome: Mapped[str] = mapped_column(String(120), nullable=False)
    usuario: Mapped[str] = mapped_column(
        String(30), nullable=False, unique=True, index=True
    )
    senha_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="Membro")
    ativo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    deve_trocar_credenciais: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )
    id_obreiro: Mapped[Optional[int]] = mapped_column(
        ForeignKey("obreiros.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )

    obreiro: Mapped[Optional["Obreiro"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - auxiliar de depuração
        return f"Usuario(id={self.id!r}, usuario={self.usuario!r}, role={self.role!r})"


class Mensalidade(Base):
    """Mensalidade mensal de um obreiro, com controle de pagamento."""

    __tablename__ = "mensalidades"
    __table_args__ = (
        UniqueConstraint("id_obreiro", "mes", "ano", name="uq_mensalidade_competencia"),
        CheckConstraint("mes BETWEEN 1 AND 12", name="ck_mensalidade_mes"),
        CheckConstraint(
            "status IN ('Pendente', 'Paga')",
            name="ck_mensalidade_status",
        ),
        CheckConstraint("valor > 0", name="ck_mensalidade_valor_positivo"),
        Index("ix_mensalidades_competencia", "ano", "mes"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    id_obreiro: Mapped[int] = mapped_column(
        ForeignKey("obreiros.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    mes: Mapped[int] = mapped_column(nullable=False)
    ano: Mapped[int] = mapped_column(nullable=False)
    valor: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    status: Mapped[str] = mapped_column(
        String(10), nullable=False, default="Pendente"
    )
    data_pagamento: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    id_lancamento: Mapped[Optional[int]] = mapped_column(
        ForeignKey("financeiro.id", ondelete="SET NULL"),
        nullable=True,
    )

    obreiro: Mapped["Obreiro"] = relationship()
    lancamento: Mapped[Optional["Lancamento"]] = relationship()

    def __repr__(self) -> str:  # pragma: no cover - auxiliar de depuração
        return (
            f"Mensalidade(id={self.id!r}, id_obreiro={self.id_obreiro!r}, "
            f"mes={self.mes!r}, ano={self.ano!r}, status={self.status!r})"
        )
