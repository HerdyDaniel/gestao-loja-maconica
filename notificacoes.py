"""Envio de recibos por e-mail.

A configuração é lida de variáveis de ambiente ou dos *secrets* do Streamlit:
``SMTP_HOST``, ``SMTP_PORT``, ``SMTP_USER``, ``SMTP_PASSWORD`` e,
opcionalmente, ``SMTP_FROM``. Sem essas variáveis o envio fica desativado e o
resto do sistema continua funcionando normalmente.
"""

from __future__ import annotations

import os
import smtplib
import ssl
from datetime import date
from decimal import Decimal
from email.message import EmailMessage
from email.utils import formataddr
from typing import Optional

NOME_LOJA = "ARLM.'. Alquimia da Razão nº 278, Rito Moderno"
ASSUNTO_PADRAO = "Recibo de capitação"


def _segredo(nome: str) -> Optional[str]:
    """Lê a configuração do ambiente (.env) ou dos secrets do Streamlit."""
    valor = os.getenv(nome)
    if not valor:
        try:  # pragma: no cover - depende do runtime do Streamlit
            import streamlit as st

            valor = st.secrets.get(nome)
        except Exception:  # noqa: BLE001
            valor = None
    if valor is None:
        return None
    limpo = str(valor).strip()
    return limpo or None


def configuracao() -> Optional[dict]:
    """Devolve os parâmetros de SMTP ou ``None`` se não estiver configurado."""
    host = _segredo("SMTP_HOST")
    usuario = _segredo("SMTP_USER")
    senha = _segredo("SMTP_PASSWORD")
    if not (host and usuario and senha):
        return None

    try:
        porta = int(_segredo("SMTP_PORT") or 587)
    except ValueError:
        porta = 587

    return {
        "host": host,
        "porta": porta,
        "usuario": usuario,
        "senha": senha,
        "remetente": _segredo("SMTP_FROM") or usuario,
        "loja": _segredo("NOME_LOJA") or NOME_LOJA,
    }


def configurado() -> bool:
    return configuracao() is not None


def nome_loja() -> str:
    """Nome usado nos documentos (recibo e relatórios)."""
    return _segredo("NOME_LOJA") or NOME_LOJA


def _remetente(config: dict) -> str:
    """Monta o cabeçalho ``From`` sem formatar o nome duas vezes.

    Aceita tanto um endereço simples (``loja@gmail.com``) quanto um já
    formatado (``Loja <loja@gmail.com>``). O ``formataddr`` só aceita
    endereços ASCII, por isso o nome com acentos precisa ir apenas como
    nome de exibição.
    """
    bruto = (config.get("remetente") or "").strip()
    if "<" in bruto and ">" in bruto:
        return bruto
    return formataddr((config.get("loja", ""), bruto))


def _brl(valor: Decimal | float) -> str:
    numero = float(valor or 0)
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _html(
    *,
    loja: str,
    nome: str,
    cim: str,
    competencia: str,
    valor: Decimal | float,
    data_pagamento: date,
    numero: Optional[int],
) -> str:
    recibo = f"#{numero}" if numero else "—"
    return f"""\
<div style="font-family:Arial,Helvetica,sans-serif;max-width:560px;margin:0 auto;
            color:#1f2937;">
  <div style="background:#0f172a;color:#fff;padding:20px 24px;border-radius:8px 8px 0 0;">
    <h2 style="margin:0;font-size:18px;">{loja}</h2>
    <p style="margin:4px 0 0;font-size:13px;opacity:.8;">{ASSUNTO_PADRAO}</p>
  </div>
  <div style="border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;
              padding:24px;">
    <p style="margin:0 0 16px;">Olá, <strong>{nome}</strong>.</p>
    <p style="margin:0 0 16px;">
      Recebemos o pagamento da sua capitação. Segue o recibo:
    </p>
    <table style="width:100%;border-collapse:collapse;font-size:14px;">
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Recibo</td>
        <td style="padding:8px 0;text-align:right;">{recibo}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Obreiro</td>
        <td style="padding:8px 0;text-align:right;">{nome}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">CIM</td>
        <td style="padding:8px 0;text-align:right;">{cim}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Competência</td>
        <td style="padding:8px 0;text-align:right;">{competencia}</td>
      </tr>
      <tr>
        <td style="padding:8px 0;color:#6b7280;">Data do pagamento</td>
        <td style="padding:8px 0;text-align:right;">
          {data_pagamento.strftime("%d/%m/%Y")}
        </td>
      </tr>
      <tr>
        <td style="padding:12px 0 0;border-top:1px solid #e5e7eb;font-weight:bold;">
          Valor recebido
        </td>
        <td style="padding:12px 0 0;border-top:1px solid #e5e7eb;
                   text-align:right;font-weight:bold;font-size:16px;">
          {_brl(valor)}
        </td>
      </tr>
    </table>
    <p style="margin:20px 0 0;font-size:12px;color:#6b7280;">
      Situação: <strong style="color:#047857;">Pago</strong>.
    </p>
    <p style="margin:16px 0 0;font-size:12px;color:#9ca3af;">
      Este recibo foi gerado automaticamente pelo sistema de gestão da Loja.
    </p>
  </div>
</div>
"""


def _texto(
    *,
    loja: str,
    nome: str,
    cim: str,
    competencia: str,
    valor: Decimal | float,
    data_pagamento: date,
    numero: Optional[int],
) -> str:
    recibo = f"#{numero}" if numero else "—"
    return (
        f"{loja}\n{ASSUNTO_PADRAO}\n\n"
        f"Olá, {nome}.\n\n"
        "Recebemos o pagamento da sua capitação.\n\n"
        f"Recibo: {recibo}\n"
        f"Obreiro: {nome}\n"
        f"CIM: {cim}\n"
        f"Competência: {competencia}\n"
        f"Data do pagamento: {data_pagamento.strftime('%d/%m/%Y')}\n"
        f"Valor recebido: {_brl(valor)}\n"
        "Situação: Pago\n\n"
        "Recibo gerado automaticamente pelo sistema de gestão da Loja.\n"
    )


def enviar_recibo(
    *,
    nome: str,
    email: str,
    competencia: str,
    valor: Decimal | float,
    data_pagamento: date,
    cim: str = "",
    numero: Optional[int] = None,
) -> tuple[bool, str]:
    """Envia o recibo para o e-mail do obreiro.

    Devolve ``(enviado, mensagem)``. Nunca levanta exceção: falhas de e-mail
    não podem impedir o registro do pagamento.
    """
    config = configuracao()
    if config is None:
        return False, "Envio de recibo por e-mail não está configurado."

    destino = (email or "").strip()
    if "@" not in destino:
        return False, "O obreiro não tem e-mail válido cadastrado."

    contexto = ssl.create_default_context()
    try:
        mensagem = EmailMessage()
        mensagem["Subject"] = (
            f"{ASSUNTO_PADRAO} — {competencia} — {config['loja']}"
        )
        mensagem["From"] = _remetente(config)
        mensagem["To"] = destino
        mensagem.set_content(
            _texto(
                loja=config["loja"],
                nome=nome,
                cim=cim,
                competencia=competencia,
                valor=valor,
                data_pagamento=data_pagamento,
                numero=numero,
            )
        )
        mensagem.add_alternative(
            _html(
                loja=config["loja"],
                nome=nome,
                cim=cim,
                competencia=competencia,
                valor=valor,
                data_pagamento=data_pagamento,
                numero=numero,
            ),
            subtype="html",
        )

        if config["porta"] == 465:
            with smtplib.SMTP_SSL(
                config["host"], config["porta"], timeout=20, context=contexto
            ) as servidor:
                servidor.login(config["usuario"], config["senha"])
                servidor.send_message(mensagem)
        else:
            with smtplib.SMTP(
                config["host"], config["porta"], timeout=20
            ) as servidor:
                servidor.ehlo()
                servidor.starttls(context=contexto)
                servidor.ehlo()
                servidor.login(config["usuario"], config["senha"])
                servidor.send_message(mensagem)
    except Exception as erro:  # noqa: BLE001
        return False, (
            "Falha ao enviar o recibo: "
            f"{type(erro).__name__}: {erro}"
        )

    return True, f"Recibo enviado para {destino}."
