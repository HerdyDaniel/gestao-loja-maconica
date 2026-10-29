"""Autenticação e gestão de usuários.

As senhas nunca são armazenadas em texto puro: usamos PBKDF2-HMAC-SHA256 com
salt aleatório por usuário (formato ``pbkdf2_sha256$iterações$salt$hash``).
"""

from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import unicodedata
from typing import Optional

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import joinedload

import models
from constants import PERFIS, SENHA_INICIAL_PADRAO
from crud import sessao

ITERACOES = 260_000
_USUARIO_VALIDO = re.compile(r"^[a-z0-9._-]{3,30}$")


# ---------------------------------------------------------------------------
# Senhas
# ---------------------------------------------------------------------------


def _hash_senha(senha: str) -> str:
    sal = secrets.token_hex(16)
    digesto = hashlib.pbkdf2_hmac(
        "sha256",
        senha.encode("utf-8"),
        bytes.fromhex(sal),
        ITERACOES,
    ).hex()
    return f"pbkdf2_sha256${ITERACOES}${sal}${digesto}"


def _verificar_senha(senha: str, hash_armazenado: str) -> bool:
    try:
        algoritmo, iteracoes, sal, digesto = hash_armazenado.split("$")
        if algoritmo != "pbkdf2_sha256":
            return False
        calculado = hashlib.pbkdf2_hmac(
            "sha256",
            senha.encode("utf-8"),
            bytes.fromhex(sal),
            int(iteracoes),
        ).hex()
        return hmac.compare_digest(calculado, digesto)
    except (ValueError, AttributeError, TypeError):
        return False


def _validar_senha(senha: str) -> str:
    if not isinstance(senha, str) or len(senha) < 6:
        raise ValueError("A senha deve ter pelo menos 6 caracteres.")
    return senha


def _normalizar_usuario(usuario: str) -> str:
    limpo = (usuario or "").strip().lower()
    if not _USUARIO_VALIDO.fullmatch(limpo):
        raise ValueError(
            "Usuário inválido: use de 3 a 30 caracteres "
            "(letras sem acento, números, ponto, hífen ou sublinhado)."
        )
    return limpo


# ---------------------------------------------------------------------------
# Conversão e consultas
# ---------------------------------------------------------------------------


def _usuario_dict(registro: models.Usuario) -> dict:
    return {
        "id": registro.id,
        "nome": registro.nome,
        "usuario": registro.usuario,
        "role": registro.role,
        "id_obreiro": registro.id_obreiro,
        "obreiro": registro.obreiro.nome if registro.obreiro else None,
        "ativo": registro.ativo,
        "deve_trocar_credenciais": bool(registro.deve_trocar_credenciais),
    }


def contar_usuarios() -> int:
    with sessao() as db:
        return int(db.scalar(select(func.count(models.Usuario.id))) or 0)


def listar_usuarios() -> list[dict]:
    stmt = (
        select(models.Usuario)
        .options(joinedload(models.Usuario.obreiro))
        .order_by(models.Usuario.nome)
    )
    with sessao() as db:
        return [_usuario_dict(registro) for registro in db.scalars(stmt)]


def obter_usuario(usuario_id: int) -> Optional[dict]:
    with sessao() as db:
        registro = db.scalar(
            select(models.Usuario)
            .options(joinedload(models.Usuario.obreiro))
            .where(models.Usuario.id == usuario_id)
        )
        return _usuario_dict(registro) if registro else None


# ---------------------------------------------------------------------------
# Autenticação
# ---------------------------------------------------------------------------


def autenticar(usuario: str, senha: str) -> Optional[dict]:
    """Devolve os dados do usuário se as credenciais forem válidas."""
    login = (usuario or "").strip().lower()
    if not login or not senha:
        return None

    with sessao() as db:
        registro = db.scalar(
            select(models.Usuario)
            .options(joinedload(models.Usuario.obreiro))
            .where(models.Usuario.usuario == login)
        )
        if registro is None or not registro.ativo:
            return None
        if not _verificar_senha(senha, registro.senha_hash):
            return None
        return _usuario_dict(registro)


# ---------------------------------------------------------------------------
# Cadastro e manutenção
# ---------------------------------------------------------------------------


def login_a_partir_do_cim(cim: str) -> str:
    """Converte o CIM em um login válido (minúsculas, sem acento/espaço)."""
    base = unicodedata.normalize("NFKD", (cim or "").strip())
    base = "".join(c for c in base if not unicodedata.combining(c)).lower()
    base = re.sub(r"[^a-z0-9._-]+", ".", base).strip("._-")
    if len(base) < 3:
        base = f"obreiro.{base}".strip(".") if base else "obreiro"
    return base[:30]


def criar_acesso_obreiro(
    id_obreiro: int,
    senha: str = SENHA_INICIAL_PADRAO,
) -> dict:
    """Cria o acesso inicial de um obreiro: login = CIM, senha temporária.

    O usuário nasce com ``deve_trocar_credenciais`` ligado, então no
    primeiro acesso o sistema exige a definição de login e senha próprios.
    Devolve os dados para exibição única das credenciais.
    """
    with sessao() as db:
        obreiro = db.get(models.Obreiro, id_obreiro)
        if obreiro is None:
            raise ValueError("Obreiro não encontrado.")

        existente = db.scalar(
            select(models.Usuario).where(models.Usuario.id_obreiro == id_obreiro)
        )
        if existente is not None:
            raise ValueError(
                f"Este obreiro já possui acesso (login {existente.usuario!r})."
            )

        login = _normalizar_usuario(login_a_partir_do_cim(obreiro.cim))
        if db.scalar(select(models.Usuario.id).where(models.Usuario.usuario == login)):
            raise ValueError(
                f"O login {login!r} já está em uso por outro usuário. "
                "Cadastre o acesso manualmente em Usuários."
            )

        _validar_senha(senha)
        novo = models.Usuario(
            nome=obreiro.nome,
            usuario=login,
            senha_hash=_hash_senha(senha),
            role="Membro",
            id_obreiro=obreiro.id,
            ativo=True,
            deve_trocar_credenciais=True,
        )
        db.add(novo)
        db.flush()
        return {
            "id": novo.id,
            "nome": obreiro.nome,
            "usuario": login,
            "senha": senha,
            "cim": obreiro.cim,
            "grau": obreiro.grau,
        }


def criar_usuario(
    nome: str,
    usuario: str,
    senha: str,
    role: str,
    id_obreiro: Optional[int] = None,
    exigir_troca: bool = True,
) -> int:
    """Cria um usuário.

    Por padrão as credenciais são tratadas como temporárias: no primeiro
    acesso o usuário precisa definir um novo login e uma nova senha.
    """
    nome = (nome or "").strip()
    if not nome:
        raise ValueError("Informe o nome do usuário.")
    login = _normalizar_usuario(usuario)
    _validar_senha(senha)
    if role not in PERFIS:
        raise ValueError("Perfil inválido.")
    if role == "Membro" and id_obreiro is None:
        raise ValueError(
            "Usuários do tipo Membro precisam estar vinculados a um obreiro."
        )

    try:
        with sessao() as db:
            if id_obreiro is not None and db.get(models.Obreiro, id_obreiro) is None:
                raise ValueError("Obreiro vinculado não encontrado.")
            if db.scalar(
                select(models.Usuario.id).where(models.Usuario.usuario == login)
            ):
                raise ValueError(f"O usuário {login!r} já existe.")

            novo = models.Usuario(
                nome=nome,
                usuario=login,
                senha_hash=_hash_senha(senha),
                role=role,
                id_obreiro=id_obreiro,
                ativo=True,
                deve_trocar_credenciais=exigir_troca,
            )
            db.add(novo)
            db.flush()
            return novo.id
    except IntegrityError as erro:
        raise ValueError(f"O usuário {login!r} já existe.") from erro


def trocar_credenciais(
    usuario_id: int,
    novo_usuario: str,
    nova_senha: str,
) -> dict:
    """Define o login e a senha definitivos e encerra a troca obrigatória.

    A nova senha não pode ser igual à senha temporária atual e o novo login
    precisa ser diferente do login temporário e continuar único no sistema.
    """
    login = _normalizar_usuario(novo_usuario)
    _validar_senha(nova_senha)

    try:
        with sessao() as db:
            registro = db.get(models.Usuario, usuario_id)
            if registro is None:
                raise ValueError("Usuário não encontrado.")
            if not registro.ativo:
                raise ValueError("Usuário desativado.")
            if login == registro.usuario:
                raise ValueError(
                    "O novo login deve ser diferente do login temporário."
                )
            if _verificar_senha(nova_senha, registro.senha_hash):
                raise ValueError(
                    "A nova senha deve ser diferente da senha temporária."
                )

            existente = db.scalar(
                select(models.Usuario.id).where(
                    models.Usuario.usuario == login,
                    models.Usuario.id != usuario_id,
                )
            )
            if existente:
                raise ValueError(f"O usuário {login!r} já está em uso.")

            registro.usuario = login
            registro.senha_hash = _hash_senha(nova_senha)
            registro.deve_trocar_credenciais = False
            db.flush()
            return _usuario_dict(registro)
    except IntegrityError as erro:
        raise ValueError(f"O usuário {login!r} já está em uso.") from erro


def redefinir_senha(
    usuario_id: int,
    nova_senha: str,
    exigir_troca: bool = True,
) -> None:
    """Redefine a senha; por padrão o usuário deverá trocá-la no próximo acesso."""
    _validar_senha(nova_senha)
    with sessao() as db:
        registro = db.get(models.Usuario, usuario_id)
        if registro is None:
            raise ValueError("Usuário não encontrado.")
        registro.senha_hash = _hash_senha(nova_senha)
        registro.deve_trocar_credenciais = exigir_troca


def definir_ativo(usuario_id: int, ativo: bool) -> None:
    with sessao() as db:
        registro = db.get(models.Usuario, usuario_id)
        if registro is None:
            raise ValueError("Usuário não encontrado.")

        if not ativo and registro.role == "Administrador":
            administradores_ativos = db.scalar(
                select(func.count(models.Usuario.id)).where(
                    models.Usuario.role == "Administrador",
                    models.Usuario.ativo.is_(True),
                )
            )
            if (administradores_ativos or 0) <= 1:
                raise ValueError(
                    "Não é possível desativar o último administrador ativo."
                )

        registro.ativo = ativo


def alterar_perfil(usuario_id: int, novo_perfil: str) -> None:
    """Altera o perfil de um usuário entre Administrador e Membro.

    Permite promover um membro existente a administrador (ou rebaixar,
    respeitando a proteção do último administrador ativo) sem recriar o
    usuário.
    """
    if novo_perfil not in PERFIS:
        raise ValueError("Perfil inválido.")
    with sessao() as db:
        registro = db.get(models.Usuario, usuario_id)
        if registro is None:
            raise ValueError("Usuário não encontrado.")
        if not registro.ativo:
            raise ValueError("Usuário desativado.")
        if novo_perfil == registro.role:
            return
        if novo_perfil == "Membro" and registro.role == "Administrador":
            administradores_ativos = db.scalar(
                select(func.count(models.Usuario.id)).where(
                    models.Usuario.role == "Administrador",
                    models.Usuario.ativo.is_(True),
                )
            )
            if (administradores_ativos or 0) <= 1:
                raise ValueError(
                    "Não é possível rebaixar o último administrador ativo."
                )
        registro.role = novo_perfil
