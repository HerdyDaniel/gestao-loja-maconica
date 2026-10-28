"""Geração do demonstrativo financeiro em PDF.

Usa ReportLab (fonte padrão Helvetica, com acentuação latina) e não depende de
serviços externos. O arquivo é montado em memória e entregue ao navegador.
"""

from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from io import BytesIO
from typing import Iterable, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from notificacoes import nome_loja

AZUL = colors.HexColor("#0f172a")
CINZA = colors.HexColor("#6b7280")
CINZA_CLARO = colors.HexColor("#f3f4f6")
LINHA = colors.HexColor("#e5e7eb")
VERDE = colors.HexColor("#047857")
VERMELHO = colors.HexColor("#b91c1c")

MARGEM = 15 * mm
LARGURA_UTIL = A4[0] - 2 * MARGEM


_TRADUCOES = str.maketrans(
    {
        "\u2014": "-",   # travessão
        "\u2013": "-",   # meia-risca
        "\u2018": "'",
        "\u2019": "'",
        "\u201c": '"',
        "\u201d": '"',
        "\u2026": "...",
        "\u00a0": " ",
    }
)


def _txt(valor: object) -> str:
    """Mantém o texto dentro do conjunto de caracteres latino aceito."""
    texto = str(valor if valor is not None else "").translate(_TRADUCOES)
    return texto.encode("latin-1", "replace").decode("latin-1")


def _brl(valor: Decimal | float | None) -> str:
    numero = float(valor or 0)
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _estilos() -> dict[str, ParagraphStyle]:
    return {
        "loja": ParagraphStyle(
            "loja", fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=CINZA,
        ),
        "titulo": ParagraphStyle(
            "titulo", fontName="Helvetica-Bold", fontSize=18, leading=22,
            textColor=AZUL, spaceBefore=2,
        ),
        "subtitulo": ParagraphStyle(
            "subtitulo", fontName="Helvetica", fontSize=9, leading=13,
            textColor=CINZA,
        ),
        "secao": ParagraphStyle(
            "secao", fontName="Helvetica-Bold", fontSize=11, leading=14,
            textColor=AZUL, spaceBefore=4, spaceAfter=4,
        ),
        "celula": ParagraphStyle(
            "celula", fontName="Helvetica", fontSize=8.5, leading=11,
        ),
        "celula_negrito": ParagraphStyle(
            "celula_negrito", fontName="Helvetica-Bold", fontSize=8.5,
            leading=11,
        ),
        "celula_cabecalho": ParagraphStyle(
            "celula_cabecalho", fontName="Helvetica-Bold", fontSize=8.5,
            leading=11, textColor=colors.white,
        ),
        "vazio": ParagraphStyle(
            "vazio", fontName="Helvetica-Oblique", fontSize=9, leading=13,
            textColor=CINZA,
        ),
    }


def _tabela_resumo(
    resumo: dict, saldo_acumulado: Decimal, estilos: dict
) -> Table:
    rotulos = [
        "Entradas no período",
        "Saídas no período",
        "Resultado do período",
        "Saldo acumulado",
    ]
    valores = [
        _brl(resumo["entradas"]),
        _brl(resumo["saidas"]),
        _brl(resumo["saldo"]),
        _brl(saldo_acumulado),
    ]

    linhas = [
        [Paragraph(_txt(rotulo), estilos["subtitulo"]) for rotulo in rotulos],
        [
            Paragraph(f"<b>{_txt(valor)}</b>", estilos["celula"])
            for valor in valores
        ],
    ]

    tabela = Table(linhas, colWidths=[LARGURA_UTIL / 4] * 4, hAlign="LEFT")
    tabela.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, -1), CINZA_CLARO),
                ("BOX", (0, 0), (-1, -1), 0.5, LINHA),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, LINHA),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("TOPPADDING", (0, 0), (-1, -1), 7),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 7),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("FONTSIZE", (0, 1), (-1, 1), 12),
                ("TEXTCOLOR", (0, 1), (0, 1), VERDE),
                ("TEXTCOLOR", (1, 1), (1, 1), VERMELHO),
            ]
        )
    )
    return tabela


def _tabela_lancamentos(
    lancamentos: Iterable[dict], resumo: dict, estilos: dict
) -> Table:
    cabecalho = [
        Paragraph(titulo, estilos["celula_cabecalho"])
        for titulo in ("Data", "Tipo", "Descrição", "Obreiro", "Valor")
    ]

    linhas = [cabecalho]
    dados = sorted(
        lancamentos, key=lambda item: (item["data"], item.get("id") or 0)
    )
    for item in dados:
        linhas.append(
            [
                Paragraph(_txt(item["data"].strftime("%d/%m/%Y")), estilos["celula"]),
                Paragraph(_txt(item["tipo"]), estilos["celula"]),
                Paragraph(_txt(item.get("descricao") or ""), estilos["celula"]),
                Paragraph(_txt(item.get("obreiro") or "-"), estilos["celula"]),
                Paragraph(_txt(_brl(item["valor"])), estilos["celula"]),
            ]
        )

    linhas.append(
        [
            "",
            "",
            Paragraph("<b>Total do período</b>", estilos["celula_negrito"]),
            "",
            Paragraph(
                f"<b>{_txt(_brl(resumo['saldo']))}</b>", estilos["celula_negrito"]
            ),
        ]
    )

    larguras = [20 * mm, 18 * mm, 72 * mm, 45 * mm, 25 * mm]
    tabela = Table(linhas, colWidths=larguras, repeatRows=1, hAlign="LEFT")

    comandos = [
        ("BACKGROUND", (0, 0), (-1, 0), AZUL),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("BOX", (0, 0), (-1, -1), 0.5, LINHA),
        ("LINEBELOW", (0, 0), (-1, 0), 0.5, AZUL),
        ("INNERGRID", (0, 1), (-1, -2), 0.25, LINHA),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("ALIGN", (4, 1), (4, -1), "RIGHT"),
        ("TOPPADDING", (0, 0), (-1, -1), 5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
        ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ("RIGHTPADDING", (0, 0), (-1, -1), 6),
        ("BACKGROUND", (0, -1), (-1, -1), CINZA_CLARO),
        ("LINEABOVE", (0, -1), (-1, -1), 0.75, AZUL),
    ]

    for indice, item in enumerate(dados, start=1):
        cor = VERDE if item["tipo"] == "Entrada" else VERMELHO
        comandos.append(("TEXTCOLOR", (1, indice), (1, indice), cor))
        comandos.append(("TEXTCOLOR", (4, indice), (4, indice), cor))
        if indice % 2 == 0:
            comandos.append(("BACKGROUND", (0, indice), (-1, indice), CINZA_CLARO))

    tabela.setStyle(TableStyle(comandos))
    return tabela


def gerar_demonstrativo(
    *,
    inicio: date,
    fim: date,
    lancamentos: Iterable[dict],
    resumo: dict,
    saldo_acumulado: Decimal,
    loja: Optional[str] = None,
    gerado_em: Optional[datetime] = None,
) -> bytes:
    """Monta o PDF do demonstrativo e devolve os bytes."""
    nome = loja or nome_loja()
    emitido = gerado_em or datetime.now()
    estilos = _estilos()
    dados = list(lancamentos)

    buffer = BytesIO()
    documento = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        leftMargin=MARGEM,
        rightMargin=MARGEM,
        topMargin=18 * mm,
        bottomMargin=20 * mm,
        title="Demonstrativo financeiro",
        author=nome,
    )

    def rodape(canvas, doc):  # noqa: ANN001
        canvas.saveState()
        canvas.setFont("Helvetica", 7.5)
        canvas.setFillColor(CINZA)
        canvas.drawString(MARGEM, 12 * mm, _txt(nome))
        canvas.drawRightString(
            A4[0] - MARGEM, 12 * mm, f"Página {doc.page}"
        )
        canvas.setStrokeColor(LINHA)
        canvas.line(MARGEM, 15 * mm, A4[0] - MARGEM, 15 * mm)
        canvas.restoreState()

    historia = [
        Paragraph(_txt(nome), estilos["loja"]),
        Paragraph("Demonstrativo financeiro", estilos["titulo"]),
        Paragraph(
            "Período de "
            f"{inicio.strftime('%d/%m/%Y')} a {fim.strftime('%d/%m/%Y')}",
            estilos["subtitulo"],
        ),
        Paragraph(
            f"Emitido em {emitido.strftime('%d/%m/%Y às %H:%M')}",
            estilos["subtitulo"],
        ),
        Spacer(1, 8 * mm),
        _tabela_resumo(resumo, saldo_acumulado, estilos),
        Spacer(1, 8 * mm),
        Paragraph("Lançamentos", estilos["secao"]),
    ]

    if dados:
        historia.append(_tabela_lancamentos(dados, resumo, estilos))
    else:
        historia.append(
            Paragraph("Nenhum lançamento registrado no período.", estilos["vazio"])
        )

    historia.append(Spacer(1, 6 * mm))
    historia.append(
        Paragraph(
            f"<b>{len(dados)}</b> lançamento(s) no período.",
            estilos["subtitulo"],
        )
    )

    documento.build(historia, onFirstPage=rodape, onLaterPages=rodape)
    return buffer.getvalue()
