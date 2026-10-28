"""Regras de acesso e validação dos dados.

A interface (``app.py``) só conversa com o banco por meio destas funções.
Cada função abre e fecha a própria sessão, o que evita estado compartilhado
entre reruns do Streamlit.
"""

from __future__ import annotations

import re
from contextlib import contextmanager
from datetime import date
from decimal import Decimal
from typing import Iterator, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, joinedload

import models
from constants import (
    DIA_VENCIMENTO,
    GRAUS,
    MESES_ABREV,
    MESES_PARA_ALERTA,
    STATUS_OBREIRO,
    TIPOS_LANCAMENTO,
)
from database import SessionLocal


@contextmanager
def sessao() -> Iterator[Session]:
    """Sessão transacional: commit no sucesso, rollback no erro."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Conversão para estruturas simples (a interface não recebe objetos ORM)
# ---------------------------------------------------------------------------


def _obreiro_dict(obreiro: models.Obreiro) -> dict:
    return {
        "id": obreiro.id,
        "nome": obreiro.nome,
        "cim": obreiro.cim,
        "grau": obreiro.grau,
        "status": obreiro.status,
        "cpf": obreiro.cpf,
        "telefone": obreiro.telefone,
        "email": obreiro.email,
    }


def _lancamento_dict(lancamento: models.Lancamento) -> dict:
    return {
        "id": lancamento.id,
        "tipo": lancamento.tipo,
        "descricao": lancamento.descricao,
        "valor": lancamento.valor,
        "data": lancamento.data,
        "id_obreiro": lancamento.id_obreiro,
        "obreiro": lancamento.obreiro.nome if lancamento.obreiro else None,
    }


# ---------------------------------------------------------------------------
# Validações compartilhadas
# ---------------------------------------------------------------------------


def _texto_obrigatorio(valor: Optional[str], campo: str) -> str:
    limpo = (valor or "").strip()
    if not limpo:
        raise ValueError(f"Informe {campo}.")
    return limpo


def _validar_obreiro(nome: str, cim: str, grau: str, status: str) -> tuple[str, str]:
    nome = _texto_obrigatorio(nome, "o nome do obreiro")
    cim = _texto_obrigatorio(cim, "o CIM do obreiro")
    if grau not in GRAUS:
        raise ValueError(f"Grau inválido: {grau!r}.")
    if status not in STATUS_OBREIRO:
        raise ValueError(f"Status inválido: {status!r}.")
    return nome, cim


def _email_opcional(email: Optional[str]) -> Optional[str]:
    limpo = (email or "").strip()
    return limpo or None


def _cpf_valido(digitos: str) -> bool:
    """Confere os dois dígitos verificadores do CPF."""
    if len(digitos) != 11 or len(set(digitos)) == 1:
        return False
    for tamanho in (9, 10):
        soma = sum(int(digitos[i]) * (tamanho + 1 - i) for i in range(tamanho))
        resto = (soma * 10) % 11
        if resto == 10:
            resto = 0
        if resto != int(digitos[tamanho]):
            return False
    return True


def _cpf_opcional(cpf: Optional[str]) -> Optional[str]:
    """Valida o CPF (opcional) e devolve no formato 000.000.000-00."""
    digitos = re.sub(r"\D", "", cpf or "")
    if not digitos:
        return None
    if not _cpf_valido(digitos):
        raise ValueError("CPF inválido: confira os 11 dígitos.")
    return f"{digitos[:3]}.{digitos[3:6]}.{digitos[6:9]}-{digitos[9:]}"


def _telefone_opcional(telefone: Optional[str]) -> Optional[str]:
    """Valida o telefone (opcional) e devolve no formato (00) 00000-0000."""
    digitos = re.sub(r"\D", "", telefone or "")
    if not digitos:
        return None
    if len(digitos) not in (10, 11):
        raise ValueError(
            "Telefone inválido: informe DDD + número (10 ou 11 dígitos)."
        )
    ddd, numero = digitos[:2], digitos[2:]
    corte = 5 if len(numero) == 9 else 4
    return f"({ddd}) {numero[:corte]}-{numero[corte:]}"


# ---------------------------------------------------------------------------
# Obreiros
# ---------------------------------------------------------------------------


def criar_obreiro(
    nome: str,
    cim: str,
    grau: str = "Aprendiz",
    status: str = "Ativo",
    cpf: Optional[str] = None,
    telefone: Optional[str] = None,
    email: Optional[str] = None,
) -> int:
    """Cadastra um obreiro e devolve o ID gerado."""
    nome, cim = _validar_obreiro(nome, cim, grau, status)
    cpf = _cpf_opcional(cpf)
    telefone = _telefone_opcional(telefone)

    try:
        with sessao() as db:
            if db.scalar(select(models.Obreiro.id).where(models.Obreiro.cim == cim)):
                raise ValueError(f"Já existe um obreiro com o CIM {cim}.")
            if cpf and db.scalar(
                select(models.Obreiro.id).where(models.Obreiro.cpf == cpf)
            ):
                raise ValueError(f"Já existe um obreiro com o CPF {cpf}.")
            obreiro = models.Obreiro(
                nome=nome,
                cim=cim,
                grau=grau,
                status=status,
                cpf=cpf,
                telefone=telefone,
                email=_email_opcional(email),
            )
            db.add(obreiro)
            db.flush()
            return obreiro.id
    except IntegrityError as erro:
        raise ValueError(f"Já existe um obreiro com o CIM {cim}.") from erro


def atualizar_obreiro(
    obreiro_id: int,
    nome: str,
    cim: str,
    grau: str,
    status: str,
    cpf: Optional[str] = None,
    telefone: Optional[str] = None,
    email: Optional[str] = None,
) -> None:
    """Atualiza os dados cadastrais de um obreiro."""
    nome, cim = _validar_obreiro(nome, cim, grau, status)
    cpf = _cpf_opcional(cpf)
    telefone = _telefone_opcional(telefone)

    try:
        with sessao() as db:
            obreiro = db.get(models.Obreiro, obreiro_id)
            if obreiro is None:
                raise ValueError("Obreiro não encontrado.")

            duplicado = db.scalar(
                select(models.Obreiro.id).where(
                    models.Obreiro.cim == cim,
                    models.Obreiro.id != obreiro_id,
                )
            )
            if duplicado:
                raise ValueError(f"O CIM {cim} já pertence a outro obreiro.")

            if cpf and db.scalar(
                select(models.Obreiro.id).where(
                    models.Obreiro.cpf == cpf,
                    models.Obreiro.id != obreiro_id,
                )
            ):
                raise ValueError(f"O CPF {cpf} já pertence a outro obreiro.")

            obreiro.nome = nome
            obreiro.cim = cim
            obreiro.grau = grau
            obreiro.status = status
            obreiro.cpf = cpf
            obreiro.telefone = telefone
            obreiro.email = _email_opcional(email)
    except IntegrityError as erro:
        raise ValueError(f"Já existe um obreiro com o CIM {cim}.") from erro


def excluir_obreiro(obreiro_id: int) -> None:
    """Exclui um obreiro; lançamentos vinculados ficam sem o vínculo."""
    with sessao() as db:
        obreiro = db.get(models.Obreiro, obreiro_id)
        if obreiro is None:
            raise ValueError("Obreiro não encontrado.")
        db.delete(obreiro)


def listar_obreiros(
    busca: str = "",
    status: Optional[str] = None,
) -> list[dict]:
    """Lista obreiros por nome; filtra por texto (nome/CIM/e-mail) e status."""
    stmt = select(models.Obreiro).order_by(models.Obreiro.nome)
    termo = (busca or "").strip()
    if termo:
        padrao = f"%{termo}%"
        stmt = stmt.where(
            or_(
                models.Obreiro.nome.ilike(padrao),
                models.Obreiro.cim.ilike(padrao),
                models.Obreiro.cpf.ilike(padrao),
                models.Obreiro.telefone.ilike(padrao),
                models.Obreiro.email.ilike(padrao),
            )
        )
    if status:
        stmt = stmt.where(models.Obreiro.status == status)

    with sessao() as db:
        return [_obreiro_dict(obreiro) for obreiro in db.scalars(stmt)]


def obter_obreiro(obreiro_id: int) -> Optional[dict]:
    with sessao() as db:
        obreiro = db.get(models.Obreiro, obreiro_id)
        return _obreiro_dict(obreiro) if obreiro else None


def contar_obreiros(status: Optional[str] = None) -> int:
    stmt = select(func.count(models.Obreiro.id))
    if status:
        stmt = stmt.where(models.Obreiro.status == status)
    with sessao() as db:
        return int(db.scalar(stmt) or 0)


def contar_obreiros_ativos() -> int:
    return contar_obreiros(status="Ativo")


# ---------------------------------------------------------------------------
# Financeiro
# ---------------------------------------------------------------------------


def criar_lancamento(
    tipo: str,
    descricao: str,
    valor: Decimal | float | str,
    data_lancamento: date,
    id_obreiro: Optional[int] = None,
) -> int:
    """Registra uma entrada ou saída e devolve o ID gerado."""
    if tipo not in TIPOS_LANCAMENTO:
        raise ValueError(f"Tipo de lançamento inválido: {tipo!r}.")
    descricao = _texto_obrigatorio(descricao, "a descrição do lançamento")
    if not isinstance(data_lancamento, date):
        raise ValueError("Informe uma data válida para o lançamento.")

    try:
        valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"))
    except Exception as erro:  # noqa: BLE001 - converte erro de conversão em regra
        raise ValueError("Valor inválido.") from erro
    if valor_decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")

    with sessao() as db:
        if id_obreiro is not None and db.get(models.Obreiro, id_obreiro) is None:
            raise ValueError("Obreiro vinculado não encontrado.")

        lancamento = models.Lancamento(
            tipo=tipo,
            descricao=descricao,
            valor=valor_decimal,
            data=data_lancamento,
            id_obreiro=id_obreiro,
        )
        db.add(lancamento)
        db.flush()
        return lancamento.id


def excluir_lancamento(lancamento_id: int) -> None:
    """Exclui um lançamento e reabre a mensalidade vinculada, se houver."""
    with sessao() as db:
        lancamento = db.get(models.Lancamento, lancamento_id)
        if lancamento is None:
            raise ValueError("Lançamento não encontrado.")

        mensalidade = db.scalar(
            select(models.Mensalidade).where(
                models.Mensalidade.id_lancamento == lancamento_id
            )
        )
        if mensalidade is not None:
            mensalidade.status = "Pendente"
            mensalidade.data_pagamento = None
            mensalidade.id_lancamento = None

        db.delete(lancamento)


def listar_lancamentos(
    inicio: Optional[date] = None,
    fim: Optional[date] = None,
    tipo: Optional[str] = None,
    id_obreiro: Optional[int] = None,
    limit: Optional[int] = None,
) -> list[dict]:
    """Lista lançamentos no período informado, do mais recente ao mais antigo."""
    stmt = (
        select(models.Lancamento)
        .options(joinedload(models.Lancamento.obreiro))
        .order_by(models.Lancamento.data.desc(), models.Lancamento.id.desc())
    )
    if inicio:
        stmt = stmt.where(models.Lancamento.data >= inicio)
    if fim:
        stmt = stmt.where(models.Lancamento.data <= fim)
    if tipo:
        stmt = stmt.where(models.Lancamento.tipo == tipo)
    if id_obreiro is not None:
        stmt = stmt.where(models.Lancamento.id_obreiro == id_obreiro)
    if limit:
        stmt = stmt.limit(limit)

    with sessao() as db:
        return [_lancamento_dict(lancamento) for lancamento in db.scalars(stmt)]


def resumo_financeiro(inicio: date, fim: date) -> dict[str, Decimal]:
    """Totais de entradas, saídas e saldo no período."""
    stmt = (
        select(models.Lancamento.tipo, func.sum(models.Lancamento.valor))
        .where(
            models.Lancamento.data >= inicio,
            models.Lancamento.data <= fim,
        )
        .group_by(models.Lancamento.tipo)
    )
    with sessao() as db:
        totais = {tipo: Decimal("0") for tipo in TIPOS_LANCAMENTO}
        for tipo, total in db.execute(stmt):
            totais[tipo] = Decimal(str(total or 0))

    return {
        "entradas": totais["Entrada"],
        "saidas": totais["Saída"],
        "saldo": totais["Entrada"] - totais["Saída"],
    }


def saldo_total() -> dict[str, Decimal]:
    """Saldo acumulado da Loja desde o primeiro lançamento."""
    stmt = select(
        models.Lancamento.tipo,
        func.coalesce(func.sum(models.Lancamento.valor), 0),
    ).group_by(models.Lancamento.tipo)
    with sessao() as db:
        totais = {tipo: Decimal("0") for tipo in TIPOS_LANCAMENTO}
        for tipo, total in db.execute(stmt):
            totais[tipo] = Decimal(str(total or 0))

    return {
        "entradas": totais["Entrada"],
        "saidas": totais["Saída"],
        "saldo": totais["Entrada"] - totais["Saída"],
    }


def contar_lancamentos() -> int:
    with sessao() as db:
        return int(db.scalar(select(func.count(models.Lancamento.id))) or 0)


def evolucao_mensal(meses: int = 6) -> list[dict]:
    """Entradas e saídas dos últimos ``meses`` meses, para o gráfico."""
    hoje = date.today()
    ano, mes = hoje.year, hoje.month

    periodo: list[tuple[int, int]] = []
    for _ in range(max(1, meses)):
        periodo.append((ano, mes))
        mes -= 1
        if mes == 0:
            mes = 12
            ano -= 1
    periodo.reverse()

    inicio = date(periodo[0][0], periodo[0][1], 1)
    stmt = select(
        models.Lancamento.data,
        models.Lancamento.tipo,
        models.Lancamento.valor,
    ).where(models.Lancamento.data >= inicio)

    acumulado = {
        chave: {"entradas": Decimal("0"), "saidas": Decimal("0")} for chave in periodo
    }
    with sessao() as db:
        for data_lancamento, tipo, valor in db.execute(stmt):
            chave = (data_lancamento.year, data_lancamento.month)
            if chave not in acumulado:
                continue
            if tipo == "Entrada":
                acumulado[chave]["entradas"] += valor
            else:
                acumulado[chave]["saidas"] += valor

    return [
        {
            "rotulo": f"{MESES_ABREV[mes - 1]}/{str(ano)[2:]}",
            "entradas": float(valores["entradas"]),
            "saidas": float(valores["saidas"]),
        }
        for (ano, mes), valores in acumulado.items()
    ]


# ---------------------------------------------------------------------------
# Mensalidades
# ---------------------------------------------------------------------------


def _mensalidade_dict(mensalidade: models.Mensalidade) -> dict:
    return {
        "id": mensalidade.id,
        "id_obreiro": mensalidade.id_obreiro,
        "obreiro": mensalidade.obreiro.nome if mensalidade.obreiro else None,
        "mes": mensalidade.mes,
        "ano": mensalidade.ano,
        "valor": mensalidade.valor,
        "status": mensalidade.status,
        "data_pagamento": mensalidade.data_pagamento,
        "id_lancamento": mensalidade.id_lancamento,
    }


def gerar_mensalidades(
    mes: int,
    ano: int,
    valor: Decimal | float | str,
) -> tuple[int, int]:
    """Gera mensalidades pendentes para os obreiros ativos.

    Retorna ``(criadas, ignoradas)``; competências já existentes não são
    duplicadas.
    """
    if not 1 <= int(mes) <= 12:
        raise ValueError("Mês inválido.")
    if not 2000 <= int(ano) <= 2100:
        raise ValueError("Ano inválido.")

    try:
        valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"))
    except Exception as erro:  # noqa: BLE001
        raise ValueError("Valor inválido.") from erro
    if valor_decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")

    with sessao() as db:
        ativos = db.scalars(
            select(models.Obreiro.id).where(models.Obreiro.status == "Ativo")
        ).all()
        existentes = set(
            db.scalars(
                select(models.Mensalidade.id_obreiro).where(
                    models.Mensalidade.mes == mes,
                    models.Mensalidade.ano == ano,
                )
            ).all()
        )

        criadas = 0
        for id_obreiro in ativos:
            if id_obreiro in existentes:
                continue
            db.add(
                models.Mensalidade(
                    id_obreiro=id_obreiro,
                    mes=mes,
                    ano=ano,
                    valor=valor_decimal,
                    status="Pendente",
                )
            )
            criadas += 1

        return criadas, len(ativos) - criadas


def listar_mensalidades(
    mes: Optional[int] = None,
    ano: Optional[int] = None,
    status: Optional[str] = None,
    id_obreiro: Optional[int] = None,
) -> list[dict]:
    stmt = (
        select(models.Mensalidade)
        .options(joinedload(models.Mensalidade.obreiro))
        .order_by(
            models.Mensalidade.ano,
            models.Mensalidade.mes,
            models.Mensalidade.id,
        )
    )
    if mes is not None:
        stmt = stmt.where(models.Mensalidade.mes == mes)
    if ano is not None:
        stmt = stmt.where(models.Mensalidade.ano == ano)
    if status:
        stmt = stmt.where(models.Mensalidade.status == status)
    if id_obreiro is not None:
        stmt = stmt.where(models.Mensalidade.id_obreiro == id_obreiro)

    with sessao() as db:
        return [_mensalidade_dict(item) for item in db.scalars(stmt)]


def vencimento_mensalidade(mes: int, ano: int) -> date:
    """Data de vencimento da competência (sempre no dia configurado)."""
    return date(int(ano), int(mes), DIA_VENCIMENTO)


def listar_mensalidades_atrasadas(
    id_obreiro: Optional[int] = None,
    hoje: Optional[date] = None,
) -> list[dict]:
    """Obreiros com competências pendentes já vencidas.

    A mensalidade vence no dia ``DIA_VENCIMENTO`` do próprio mês; a partir do
    dia seguinte ela passa a contar como atrasada. O resultado é agrupado por
    obreiro, com a quantidade de competências em atraso, o valor total, os
    dias de atraso e a lista de competências.
    """
    referencia = hoje or date.today()
    stmt = (
        select(models.Mensalidade)
        .options(joinedload(models.Mensalidade.obreiro))
        .where(models.Mensalidade.status == "Pendente")
        .order_by(models.Mensalidade.ano, models.Mensalidade.mes)
    )
    if id_obreiro is not None:
        stmt = stmt.where(models.Mensalidade.id_obreiro == id_obreiro)

    with sessao() as db:
        registros = [
            mensalidade
            for mensalidade in db.scalars(stmt)
            if vencimento_mensalidade(mensalidade.mes, mensalidade.ano)
            < referencia
        ]

    agrupado: dict[int, dict] = {}
    for mensalidade in registros:
        vencimento = vencimento_mensalidade(mensalidade.mes, mensalidade.ano)
        atraso = (referencia - vencimento).days
        item = agrupado.setdefault(
            mensalidade.id_obreiro,
            {
                "id_obreiro": mensalidade.id_obreiro,
                "obreiro": (
                    mensalidade.obreiro.nome if mensalidade.obreiro else "—"
                ),
                "cim": mensalidade.obreiro.cim if mensalidade.obreiro else "—",
                "email": mensalidade.obreiro.email if mensalidade.obreiro else None,
                "quantidade": 0,
                "valor_total": Decimal("0"),
                "dias_em_atraso": 0,
                "ultimo_vencimento": vencimento,
                "competencias": [],
            },
        )
        item["quantidade"] += 1
        item["valor_total"] += mensalidade.valor
        item["dias_em_atraso"] = max(item["dias_em_atraso"], atraso)
        item["ultimo_vencimento"] = max(item["ultimo_vencimento"], vencimento)
        item["competencias"].append(
            f"{MESES_ABREV[mensalidade.mes - 1]}/{mensalidade.ano}"
        )

    return sorted(
        agrupado.values(),
        key=lambda item: (-item["quantidade"], item["obreiro"]),
    )


def obreiros_em_debito(
    minimo_meses: int = MESES_PARA_ALERTA,
    id_obreiro: Optional[int] = None,
    hoje: Optional[date] = None,
) -> list[dict]:
    """Obreiros com pelo menos ``minimo_meses`` competências vencidas.

    É a base do alerta vermelho exibido para a administração.
    """
    return [
        item
        for item in listar_mensalidades_atrasadas(
            id_obreiro=id_obreiro, hoje=hoje
        )
        if item["quantidade"] >= minimo_meses
    ]


def resumo_mensalidades(mes: int, ano: int) -> dict:
    """Totais de uma competência (mês/ano)."""
    with sessao() as db:
        registros = db.execute(
            select(
                models.Mensalidade.status,
                func.count(models.Mensalidade.id),
                func.coalesce(func.sum(models.Mensalidade.valor), 0),
            )
            .where(
                models.Mensalidade.mes == mes,
                models.Mensalidade.ano == ano,
            )
            .group_by(models.Mensalidade.status)
        ).all()

    recebido = Decimal("0")
    pendente = Decimal("0")
    pagas = 0
    total = 0
    for status, quantidade, soma in registros:
        valor = Decimal(str(soma or 0))
        total += int(quantidade)
        if status == "Paga":
            recebido += valor
            pagas = int(quantidade)
        else:
            pendente += valor

    return {
        "previsto": recebido + pendente,
        "recebido": recebido,
        "pendente": pendente,
        "pagas": pagas,
        "total": total,
    }


def obter_mensalidade(id_obreiro: int, mes: int, ano: int) -> Optional[dict]:
    """Mensalidade de um obreiro em uma competência, se existir."""
    with sessao() as db:
        mensalidade = db.scalar(
            select(models.Mensalidade)
            .options(joinedload(models.Mensalidade.obreiro))
            .where(
                models.Mensalidade.id_obreiro == id_obreiro,
                models.Mensalidade.mes == mes,
                models.Mensalidade.ano == ano,
            )
        )
        return _mensalidade_dict(mensalidade) if mensalidade else None


def _registrar_baixa(
    db: Session,
    mensalidade: models.Mensalidade,
    data_pagamento: date,
) -> models.Lancamento:
    """Cria a entrada financeira e marca a mensalidade como paga."""
    obreiro = db.get(models.Obreiro, mensalidade.id_obreiro)
    if obreiro is None:
        raise ValueError("Obreiro da mensalidade não encontrado.")

    lancamento = models.Lancamento(
        tipo="Entrada",
        descricao=(
            f"Mensalidade {MESES_ABREV[mensalidade.mes - 1]}/"
            f"{mensalidade.ano} — {obreiro.nome}"
        ),
        valor=mensalidade.valor,
        data=data_pagamento,
        id_obreiro=mensalidade.id_obreiro,
    )
    db.add(lancamento)
    db.flush()

    mensalidade.status = "Paga"
    mensalidade.data_pagamento = data_pagamento
    mensalidade.id_lancamento = lancamento.id
    return lancamento


def atualizar_valor_mensalidade(
    mensalidade_id: int,
    valor: Decimal | float | str,
) -> None:
    """Altera o valor de uma mensalidade ainda pendente.

    Mensalidades já pagas precisam de estorno antes da alteração, para que a
    entrada lançada no financeiro não fique com valor divergente.
    """
    try:
        valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"))
    except Exception as erro:  # noqa: BLE001
        raise ValueError("Valor inválido.") from erro
    if valor_decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")

    with sessao() as db:
        mensalidade = db.get(models.Mensalidade, mensalidade_id)
        if mensalidade is None:
            raise ValueError("Mensalidade não encontrada.")
        if mensalidade.status != "Pendente":
            raise ValueError(
                "Esta mensalidade já está paga. Estorne a baixa para "
                "poder alterar o valor."
            )
        mensalidade.valor = valor_decimal


def dar_baixa_mensalidade(
    mensalidade_id: int,
    data_pagamento: date,
    valor: Decimal | float | str | None = None,
) -> int:
    """Marca uma mensalidade existente como paga e lança a entrada.

    ``valor`` é opcional: quando informado, atualiza o valor da competência
    antes de registrar a entrada no financeiro.
    """
    if not isinstance(data_pagamento, date):
        raise ValueError("Informe uma data de pagamento válida.")

    valor_decimal: Optional[Decimal] = None
    if valor is not None:
        try:
            valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"))
        except Exception as erro:  # noqa: BLE001
            raise ValueError("Valor inválido.") from erro
        if valor_decimal <= 0:
            raise ValueError("O valor deve ser maior que zero.")

    with sessao() as db:
        mensalidade = db.get(models.Mensalidade, mensalidade_id)
        if mensalidade is None:
            raise ValueError("Mensalidade não encontrada.")
        if mensalidade.status == "Paga":
            raise ValueError("Esta mensalidade já está paga.")
        if valor_decimal is not None:
            mensalidade.valor = valor_decimal
        return _registrar_baixa(db, mensalidade, data_pagamento).id


def dar_baixa_por_obreiro(
    id_obreiro: int,
    mes: int,
    ano: int,
    valor: Decimal | float | str,
    data_pagamento: date,
) -> dict:
    """Dá baixa na capitação de um obreiro, criando a mensalidade se preciso.

    Retorna ``{"mensalidade_id", "lancamento_id", "criada"}``.
    """
    if not 1 <= int(mes) <= 12:
        raise ValueError("Mês inválido.")
    if not 2000 <= int(ano) <= 2100:
        raise ValueError("Ano inválido.")
    if not isinstance(data_pagamento, date):
        raise ValueError("Informe uma data de pagamento válida.")

    try:
        valor_decimal = Decimal(str(valor)).quantize(Decimal("0.01"))
    except Exception as erro:  # noqa: BLE001
        raise ValueError("Valor inválido.") from erro
    if valor_decimal <= 0:
        raise ValueError("O valor deve ser maior que zero.")

    with sessao() as db:
        obreiro = db.get(models.Obreiro, id_obreiro)
        if obreiro is None:
            raise ValueError("Obreiro não encontrado.")

        mensalidade = db.scalar(
            select(models.Mensalidade).where(
                models.Mensalidade.id_obreiro == id_obreiro,
                models.Mensalidade.mes == mes,
                models.Mensalidade.ano == ano,
            )
        )
        criada = False
        if mensalidade is None:
            mensalidade = models.Mensalidade(
                id_obreiro=id_obreiro,
                mes=mes,
                ano=ano,
                valor=valor_decimal,
                status="Pendente",
            )
            db.add(mensalidade)
            db.flush()
            criada = True

        if mensalidade.status == "Paga":
            raise ValueError("Esta mensalidade já está paga.")

        lancamento = _registrar_baixa(db, mensalidade, data_pagamento)
        return {
            "mensalidade_id": mensalidade.id,
            "lancamento_id": lancamento.id,
            "criada": criada,
        }


def estornar_baixa_mensalidade(mensalidade_id: int) -> None:
    """Desfaz a baixa: remove a entrada e devolve a mensalidade a pendente."""
    with sessao() as db:
        mensalidade = db.get(models.Mensalidade, mensalidade_id)
        if mensalidade is None:
            raise ValueError("Mensalidade não encontrada.")
        if mensalidade.status != "Paga":
            raise ValueError("Esta mensalidade não está paga.")

        if mensalidade.id_lancamento is not None:
            lancamento = db.get(models.Lancamento, mensalidade.id_lancamento)
            if lancamento is not None:
                db.delete(lancamento)

        mensalidade.status = "Pendente"
        mensalidade.data_pagamento = None
        mensalidade.id_lancamento = None


def resumo_mensalidades_obreiro(id_obreiro: int, ano: int) -> dict:
    """Situação das mensalidades de um obreiro em um ano."""
    with sessao() as db:
        registros = db.execute(
            select(
                models.Mensalidade.status,
                func.count(models.Mensalidade.id),
                func.coalesce(func.sum(models.Mensalidade.valor), 0),
            )
            .where(
                models.Mensalidade.id_obreiro == id_obreiro,
                models.Mensalidade.ano == ano,
            )
            .group_by(models.Mensalidade.status)
        ).all()

    valor_pago = Decimal("0")
    valor_pendente = Decimal("0")
    pagas = 0
    total = 0
    for status, quantidade, soma in registros:
        valor = Decimal(str(soma or 0))
        total += int(quantidade)
        if status == "Paga":
            valor_pago += valor
            pagas = int(quantidade)
        else:
            valor_pendente += valor

    return {
        "pagas": pagas,
        "total": total,
        "valor_pago": valor_pago,
        "valor_pendente": valor_pendente,
    }


def anos_financeiros_obreiro(id_obreiro: int) -> list[int]:
    """Anos com movimentação do obreiro (inclui o ano atual)."""
    with sessao() as db:
        anos = set(
            db.scalars(
                select(models.Mensalidade.ano)
                .where(models.Mensalidade.id_obreiro == id_obreiro)
                .distinct()
            ).all()
        )
        datas = db.scalars(
            select(models.Lancamento.data).where(
                models.Lancamento.id_obreiro == id_obreiro
            )
        ).all()
        anos |= {data_lancamento.year for data_lancamento in datas}

    anos.add(date.today().year)
    return sorted(anos, reverse=True)
