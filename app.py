"""Aplicação Streamlit — Gestão de Obreiros e Financeiro da Loja.

Execute com::

    streamlit run app.py
"""

from __future__ import annotations

import calendar
from datetime import date
from decimal import Decimal
from pathlib import Path
from typing import Callable

import pandas as pd
import streamlit as st

import auth
import crud
import notificacoes
import relatorios
from constants import (
    DIA_VENCIMENTO,
    GRAUS,
    MESES,
    MESES_ABREV,
    MESES_PARA_ALERTA,
    PERFIS,
    SENHA_INICIAL_PADRAO,
    STATUS_MENSALIDADE,
    STATUS_OBREIRO,
    TIPOS_LANCAMENTO,
)
from database import descricao_banco, init_db

BRAND_IMAGE = Path(__file__).resolve().parent / "assets" / "timbre.jpg"
BRAND_LARGURA = 140


def _marca() -> None:
    """Exibe o timbre da loja no lugar do logotipo azul padrão."""
    st.image(BRAND_IMAGE, width=BRAND_LARGURA)
    st.title("Gestão da Loja")


st.set_page_config(
    page_title="Gestão da Loja",
    page_icon=str(BRAND_IMAGE),
    layout="wide",
    initial_sidebar_state="expanded",
)

init_db()

VALOR_CAPITACAO_PADRAO = 50.0
PAGINA_INICIAL = "Relatórios"


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------


def brl(valor: Decimal | float | None) -> str:
    """Formata um número como moeda brasileira (R$ 1.234,56)."""
    numero = float(valor or 0)
    return f"R$ {numero:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def data_br(valor: date | None) -> str:
    return valor.strftime("%d/%m/%Y") if valor else "—"


def definir_flash(tipo: str, mensagem: str) -> None:
    """Guarda uma mensagem para exibir após o próximo rerun."""
    st.session_state["flash"] = (tipo, mensagem)


def mostrar_flash() -> None:
    flash = st.session_state.pop("flash", None)
    if not flash:
        return
    tipo, mensagem = flash
    getattr(st, tipo, st.info)(mensagem)


def _alerta_debitos() -> None:
    """Alerta vermelho para a administração: obreiros com 2+ meses vencidos."""
    devedores = crud.obreiros_em_debito()
    if not devedores:
        return

    linhas = [
        f"- **{item['obreiro']}** (CIM {item['cim']}) — "
        f"{item['quantidade']} mensalidade(s) em atraso: "
        f"{', '.join(item['competencias'])} — {brl(item['valor_total'])}"
        for item in devedores
    ]
    st.error(
        f"🚨 **{len(devedores)} obreiro(s) com {MESES_PARA_ALERTA} meses "
        "ou mais em débito**\n\n"
        + "\n".join(linhas)
    )


def _notificar_recibo(
    id_obreiro: int,
    mes: int,
    ano: int,
    valor,
    data_pagamento: date,
    numero: int | None = None,
) -> str:
    """Envia o recibo por e-mail, se possível, e devolve um complemento."""
    try:
        obreiro = crud.obter_obreiro(id_obreiro)
    except Exception:  # noqa: BLE001 - o recibo nunca bloqueia a baixa
        return ""

    if obreiro is None:
        return ""
    if not notificacoes.configurado():
        return " O recibo por e-mail não está configurado."
    if not (obreiro.get("email") or "").strip():
        return " Obreiro sem e-mail cadastrado: recibo não enviado."

    try:
        enviado, mensagem = notificacoes.enviar_recibo(
            nome=obreiro["nome"],
            email=obreiro["email"],
            cim=obreiro["cim"],
            competencia=f"{MESES[mes - 1]}/{ano}",
            valor=valor,
            data_pagamento=data_pagamento,
            numero=numero,
        )
    except Exception as erro:  # noqa: BLE001 - nunca bloqueia a baixa
        return f" Falha ao enviar o recibo: {type(erro).__name__}: {erro}"
    return f" {mensagem}"


def usuario_atual() -> dict | None:
    return st.session_state.get("usuario")


def eh_admin() -> bool:
    usuario = usuario_atual()
    return bool(usuario and usuario.get("role") == "Administrador")


def exigir_admin() -> None:
    if not eh_admin():
        st.error("Acesso restrito a administradores.")
        st.stop()


def _sair() -> None:
    st.session_state.pop("usuario", None)
    st.session_state.pop("pagina", None)


def _entrar(dados: dict) -> None:
    st.session_state["usuario"] = dados
    st.session_state["pagina"] = PAGINA_INICIAL
    st.rerun()


def opcoes_de_obreiros(obreiros: list[dict]) -> dict[str, int]:
    return {
        f"{obreiro['nome']} (CIM {obreiro['cim']})": obreiro["id"]
        for obreiro in obreiros
    }


# ---------------------------------------------------------------------------
# Tabelas
# ---------------------------------------------------------------------------


def dataframe_obreiros(
    obreiros: list[dict],
    incluir_dados_pessoais: bool = True,
    acessos: dict[int, str] | None = None,
) -> pd.DataFrame:
    linhas = []
    for obreiro in obreiros:
        linha = {
            "ID": obreiro["id"],
            "Nome": obreiro["nome"],
            "CIM": obreiro["cim"],
            "Grau": obreiro["grau"],
            "Status": obreiro["status"],
        }
        if incluir_dados_pessoais:
            linha["CPF"] = obreiro["cpf"] or "—"
            linha["Telefone"] = obreiro["telefone"] or "—"
            linha["E-mail"] = obreiro["email"] or "—"
            if acessos is not None:
                linha["Acesso"] = acessos.get(obreiro["id"], "Sem acesso")
        linhas.append(linha)
    return pd.DataFrame(linhas)


def dataframe_lancamentos(
    lancamentos: list[dict],
    incluir_id: bool = True,
) -> pd.DataFrame:
    linhas = []
    for lancamento in lancamentos:
        linha = {
            "Data": data_br(lancamento["data"]),
            "Tipo": lancamento["tipo"],
            "Descrição": lancamento["descricao"],
            "Obreiro": lancamento["obreiro"] or "—",
            "Valor (R$)": float(lancamento["valor"]),
        }
        if incluir_id:
            linha = {"ID": lancamento["id"], **linha}
        linhas.append(linha)
    return pd.DataFrame(linhas)


def tabela_lancamentos(
    lancamentos: list[dict],
    incluir_id: bool = True,
) -> None:
    st.dataframe(
        dataframe_lancamentos(lancamentos, incluir_id),
        hide_index=True,
        width="stretch",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "Valor (R$)": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def dataframe_mensalidades(
    mensalidades: list[dict],
    incluir_id: bool = True,
) -> pd.DataFrame:
    linhas = []
    for mensalidade in mensalidades:
        linha = {
            "Obreiro": mensalidade["obreiro"] or "—",
            "Competência": f"{MESES_ABREV[mensalidade['mes'] - 1]}/{mensalidade['ano']}",
            "Vencimento": data_br(
                crud.vencimento_mensalidade(
                    mensalidade["mes"], mensalidade["ano"]
                )
            ),
            "Valor (R$)": float(mensalidade["valor"]),
            "Status": mensalidade["status"],
            "Pago em": data_br(mensalidade["data_pagamento"]),
        }
        if incluir_id:
            linha = {"ID": mensalidade["id"], **linha}
        linhas.append(linha)
    return pd.DataFrame(linhas)


def tabela_mensalidades(
    mensalidades: list[dict],
    incluir_id: bool = True,
) -> None:
    st.dataframe(
        dataframe_mensalidades(mensalidades, incluir_id),
        hide_index=True,
        width="stretch",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
            "Valor (R$)": st.column_config.NumberColumn(format="%.2f"),
        },
    )


def dataframe_atrasadas(itens: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "Obreiro": item["obreiro"],
                "CIM": item["cim"],
                "Competências em atraso": ", ".join(item["competencias"]),
                "Qtd": item["quantidade"],
                "Dias em atraso": item["dias_em_atraso"],
                "Valor (R$)": float(item["valor_total"]),
            }
            for item in itens
        ]
    )


def dataframe_usuarios(usuarios: list[dict]) -> pd.DataFrame:
    return pd.DataFrame(
        [
            {
                "ID": usuario["id"],
                "Nome": usuario["nome"],
                "Usuário": usuario["usuario"],
                "Perfil": usuario["role"],
                "Obreiro vinculado": usuario["obreiro"] or "—",
                "Ativo": "Sim" if usuario["ativo"] else "Não",
                "Troca pendente": (
                    "Sim" if usuario["deve_trocar_credenciais"] else "Não"
                ),
            }
            for usuario in usuarios
        ]
    )


# ---------------------------------------------------------------------------
# Login e configuração inicial
# ---------------------------------------------------------------------------


def tela_login() -> None:
    if auth.contar_usuarios() == 0:
        configuracao_inicial()
        return

    _, centro, _ = st.columns([1, 1.1, 1])
    with centro:
        _marca()
        st.caption("Acesso restrito aos obreiros e à administração")
        st.caption(
            "No primeiro acesso, o sistema solicitará a troca do login e da "
            "senha temporários."
        )

        with st.form("form_login"):
            usuario = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            entrar = st.form_submit_button("Entrar", type="primary")

        if entrar:
            dados = auth.autenticar(usuario, senha)
            if dados is None:
                st.error("Usuário ou senha inválidos.")
            else:
                _entrar(dados)


def configuracao_inicial() -> None:
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        _marca()
        st.subheader("Configuração inicial")
        st.info(
            "Nenhum usuário cadastrado. Crie o primeiro **Administrador** "
            "para começar a usar o sistema."
        )

        with st.form("form_configuracao_inicial"):
            nome = st.text_input("Nome completo *")
            usuario = st.text_input("Usuário *", placeholder="ex.: presidente")
            senha = st.text_input(
                "Senha *",
                type="password",
                help="Mínimo de 6 caracteres.",
            )
            confirmar = st.text_input("Confirmar senha *", type="password")
            criar = st.form_submit_button("Criar administrador", type="primary")

        if criar:
            if senha != confirmar:
                st.error("As senhas não conferem.")
                return
            try:
                auth.criar_usuario(
                    nome=nome,
                    usuario=usuario,
                    senha=senha,
                    role="Administrador",
                    exigir_troca=False,
                )
            except ValueError as erro:
                st.error(str(erro))
                return

            dados = auth.autenticar(usuario, senha)
            if dados is None:
                st.error(
                    "Administrador criado, mas não foi possível entrar. "
                    "Faça login."
                )
                return
            _entrar(dados)


def tela_primeiro_acesso(usuario: dict) -> None:
    """Bloqueia o sistema até o usuário trocar login e senha temporários."""
    _, centro, _ = st.columns([1, 1.2, 1])
    with centro:
        _marca()
        st.subheader("Primeiro acesso")
        st.info(
            "Você entrou com credenciais **temporárias**. Por segurança, "
            "defina agora o seu login e a sua senha definitivos para "
            "continuar."
        )
        st.caption(
            f"Login temporário atual: **{usuario['usuario']}** — "
            f"usuário: **{usuario['nome']}**"
        )

        with st.form("form_primeiro_acesso"):
            novo_usuario = st.text_input(
                "Novo login *",
                placeholder="ex.: joao.silva",
                help=(
                    "De 3 a 30 caracteres, com letras sem acento, números, "
                    "ponto, hífen ou sublinhado. Deve ser diferente do login "
                    "temporário."
                ),
            )
            nova_senha = st.text_input(
                "Nova senha *",
                type="password",
                help=(
                    "Mínimo de 6 caracteres e diferente da senha temporária."
                ),
            )
            confirmar = st.text_input("Confirmar nova senha *", type="password")
            trocar = st.form_submit_button(
                "Salvar novas credenciais", type="primary"
            )

        if trocar:
            if nova_senha != confirmar:
                st.error("As senhas não conferem.")
                return
            try:
                atualizado = auth.trocar_credenciais(
                    usuario_id=usuario["id"],
                    novo_usuario=novo_usuario,
                    nova_senha=nova_senha,
                )
            except ValueError as erro:
                st.error(str(erro))
                return

            st.session_state["usuario"] = atualizado
            st.session_state["flash"] = (
                "success",
                "Credenciais atualizadas. Use o novo login nos próximos "
                "acessos.",
            )
            st.rerun()

        st.divider()
        st.button("Sair", on_click=_sair, width="stretch")


# ---------------------------------------------------------------------------
# Seções reutilizáveis
# ---------------------------------------------------------------------------


def _secao_obreiros(admin: bool) -> None:
    if admin:
        with st.expander(
            "Cadastrar novo obreiro",
            expanded=crud.contar_obreiros() == 0,
        ):
            with st.form("form_novo_obreiro", clear_on_submit=True):
                nome = st.text_input("Nome completo *")
                col1, col2, col3 = st.columns(3)
                cim = col1.text_input("CIM *")
                grau = col2.selectbox("Grau", GRAUS)
                status = col3.selectbox("Status", STATUS_OBREIRO)
                col4, col5 = st.columns(2)
                cpf = col4.text_input(
                    "CPF", placeholder="000.000.000-00"
                )
                telefone = col5.text_input(
                    "Telefone", placeholder="(11) 91234-5678"
                )
                email = st.text_input("E-mail", placeholder="obreiro@exemplo.com")
                enviado = st.form_submit_button("Cadastrar", type="primary")

            if enviado:
                try:
                    crud.criar_obreiro(
                        nome=nome,
                        cim=cim,
                        grau=grau,
                        status=status,
                        cpf=cpf,
                        telefone=telefone,
                        email=email,
                    )
                    definir_flash(
                        "success", f"Obreiro **{nome.strip()}** cadastrado."
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

    st.subheader("Obreiros cadastrados")
    col_busca, col_status = st.columns([3, 1])
    busca = col_busca.text_input(
        "Buscar obreiro",
        placeholder="Nome, CIM ou e-mail",
        label_visibility="collapsed",
    )
    filtro_status = col_status.selectbox(
        "Filtrar por status",
        ("Todos", *STATUS_OBREIRO),
        label_visibility="collapsed",
    )

    obreiros = crud.listar_obreiros(
        busca=busca,
        status=None if filtro_status == "Todos" else filtro_status,
    )
    st.caption(f"{len(obreiros)} obreiro(s) encontrado(s)")

    acessos = (
        {
            usuario["id_obreiro"]: usuario["usuario"]
            for usuario in auth.listar_usuarios()
            if usuario.get("id_obreiro")
        }
        if admin
        else {}
    )

    if obreiros:
        st.dataframe(
            dataframe_obreiros(
                obreiros,
                incluir_dados_pessoais=admin,
                acessos=acessos if admin else None,
            ),
            hide_index=True,
            width="stretch",
            column_config={
                "ID": st.column_config.NumberColumn(width="small"),
            },
        )
    else:
        st.info("Nenhum obreiro encontrado com os filtros atuais.")

    if not admin:
        return

    todos = crud.listar_obreiros()
    if not todos:
        return

    with st.expander("Criar acesso ao sistema"):
        st.caption(
            "O acesso é criado a partir do cadastro do obreiro, sem "
            f"redigitar dados. Login inicial: o **CIM**. Senha inicial: "
            f"**{SENHA_INICIAL_PADRAO}** — troca obrigatória no primeiro acesso."
        )
        sem_acesso = [obreiro for obreiro in todos if obreiro["id"] not in acessos]
        if not sem_acesso:
            st.info("Todos os obreiros já possuem acesso ao sistema.")
        else:
            por_id = {obreiro["id"]: obreiro for obreiro in sem_acesso}
            escolhido_id = st.selectbox(
                "Obreiro",
                list(por_id),
                format_func=lambda oid: (
                    f"{por_id[oid]['nome']} (CIM {por_id[oid]['cim']})"
                ),
                key="acesso_obreiro",
            )
            alvo = por_id[escolhido_id]
            st.caption(
                "Login inicial: **"
                f"{auth.login_a_partir_do_cim(alvo['cim'])}**"
            )
            if st.button(
                "Criar acesso",
                type="primary",
                key="btn_criar_acesso",
            ):
                try:
                    dados = auth.criar_acesso_obreiro(escolhido_id)
                except ValueError as erro:
                    st.error(str(erro))
                else:
                    st.session_state.pop("acesso_obreiro", None)
                    definir_flash(
                        "success",
                        f"Acesso criado para **{dados['nome']}**.\n\n"
                        f"- Login: `{dados['usuario']}`\n"
                        f"- Senha: `{dados['senha']}`\n\n"
                        "No primeiro acesso o sistema exigirá a troca do "
                        "login e da senha.",
                    )
                    st.rerun()

    with st.expander("Editar ou excluir obreiro"):
        por_id = {obreiro["id"]: obreiro for obreiro in todos}
        chave = st.selectbox(
            "Selecione o obreiro",
            list(por_id),
            format_func=lambda oid: (
                f"{por_id[oid]['nome']} (CIM {por_id[oid]['cim']})"
            ),
            key="obreiro_edicao",
        )
        escolhido = por_id[chave]

        with st.form("form_editar_obreiro"):
            nome_ed = st.text_input(
                "Nome completo *", value=escolhido["nome"], key=f"nome_{chave}"
            )
            col1, col2, col3 = st.columns(3)
            cim_ed = col1.text_input(
                "CIM *", value=escolhido["cim"], key=f"cim_{chave}"
            )
            grau_ed = col2.selectbox(
                "Grau",
                GRAUS,
                index=GRAUS.index(escolhido["grau"]),
                key=f"grau_{chave}",
            )
            status_ed = col3.selectbox(
                "Status",
                STATUS_OBREIRO,
                index=STATUS_OBREIRO.index(escolhido["status"]),
                key=f"status_{chave}",
            )
            col4, col5 = st.columns(2)
            cpf_ed = col4.text_input(
                "CPF",
                value=escolhido["cpf"] or "",
                placeholder="000.000.000-00",
                key=f"cpf_{chave}",
            )
            telefone_ed = col5.text_input(
                "Telefone",
                value=escolhido["telefone"] or "",
                placeholder="(11) 91234-5678",
                key=f"telefone_{chave}",
            )
            email_ed = st.text_input(
                "E-mail",
                value=escolhido["email"] or "",
                key=f"email_{chave}",
            )
            salvar = st.form_submit_button("Salvar alterações", type="primary")

        if salvar:
            try:
                crud.atualizar_obreiro(
                    obreiro_id=chave,
                    nome=nome_ed,
                    cim=cim_ed,
                    grau=grau_ed,
                    status=status_ed,
                    cpf=cpf_ed,
                    telefone=telefone_ed,
                    email=email_ed,
                )
                definir_flash("success", "Dados do obreiro atualizados.")
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))

        st.divider()
        confirmar = st.checkbox(
            "Confirmo a exclusão deste obreiro",
            key=f"confirmar_{chave}",
            help="Os lançamentos vinculados são mantidos, mas perdem o vínculo.",
        )
        if st.button(
            "Excluir obreiro",
            disabled=not confirmar,
            key=f"excluir_{chave}",
        ):
            try:
                crud.excluir_obreiro(chave)
                definir_flash(
                    "success",
                    "Obreiro excluído. Lançamentos vinculados foram mantidos.",
                )
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))


def _secao_usuarios() -> None:
    exigir_admin()

    with st.expander(
        "Novo usuário",
        expanded=auth.contar_usuarios() <= 1,
    ):
        obreiros = crud.listar_obreiros()
        opcoes_obreiro = {"— Nenhum —": None, **opcoes_de_obreiros(obreiros)}

        with st.form("form_novo_usuario", clear_on_submit=True):
            nome = st.text_input("Nome completo *")
            usuario = st.text_input("Usuário *", placeholder="ex.: joao.silva")
            col1, col2 = st.columns(2)
            senha = col1.text_input(
                "Senha *",
                type="password",
                help="Mínimo de 6 caracteres.",
            )
            confirmar = col2.text_input("Confirmar senha *", type="password")
            col3, col4 = st.columns(2)
            perfil = col3.selectbox("Perfil *", PERFIS)
            vinculo = col4.selectbox(
                "Obreiro vinculado",
                list(opcoes_obreiro),
                help="Obrigatório para o perfil Membro.",
            )
            enviado = st.form_submit_button("Criar usuário", type="primary")

        st.caption(
            "As credenciais informadas são **temporárias**: no primeiro "
            "acesso o usuário será obrigado a definir um novo login e uma "
            "nova senha."
        )

        if not obreiros:
            st.caption(
                "Cadastre um obreiro antes de criar usuários do tipo Membro."
            )

        if enviado:
            if senha != confirmar:
                st.error("As senhas não conferem.")
            else:
                try:
                    auth.criar_usuario(
                        nome=nome,
                        usuario=usuario,
                        senha=senha,
                        role=perfil,
                        id_obreiro=opcoes_obreiro.get(vinculo),
                    )
                    definir_flash(
                        "success", f"Usuário **{usuario.strip()}** criado."
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

    usuarios = auth.listar_usuarios()
    st.subheader("Usuários cadastrados")
    st.caption(f"{len(usuarios)} usuário(s)")
    st.dataframe(
        dataframe_usuarios(usuarios),
        hide_index=True,
        width="stretch",
        column_config={
            "ID": st.column_config.NumberColumn(width="small"),
        },
    )

    if not usuarios:
        return

    with st.expander("Gerenciar usuário"):
        por_id = {usuario["id"]: usuario for usuario in usuarios}
        alvo_id = st.selectbox(
            "Selecione o usuário",
            list(por_id),
            format_func=lambda uid: (
                f"{por_id[uid]['nome']} ({por_id[uid]['usuario']})"
            ),
            key="usuario_gestao",
        )
        alvo = por_id[alvo_id]

        with st.form("form_redefinir_senha"):
            nova = st.text_input(
                "Nova senha",
                type="password",
                key=f"nova_senha_{alvo_id}",
                help="Mínimo de 6 caracteres.",
            )
            confirmar_nova = st.text_input(
                "Confirmar nova senha",
                type="password",
                key=f"confirmar_senha_{alvo_id}",
            )
            exigir_troca_nova = st.checkbox(
                "Exigir troca de login e senha no próximo acesso",
                value=True,
                key=f"exigir_troca_{alvo_id}",
                help=(
                    "Recomendado ao entregar uma senha temporária. O usuário "
                    "deverá definir o próprio login e a própria senha."
                ),
            )
            redefinir = st.form_submit_button("Redefinir senha")

        if redefinir:
            if nova != confirmar_nova:
                st.error("As senhas não conferem.")
            else:
                try:
                    auth.redefinir_senha(
                        alvo_id,
                        nova,
                        exigir_troca=exigir_troca_nova,
                    )
                    definir_flash(
                        "success",
                        (
                            "Senha redefinida. O usuário deverá trocar o "
                            "login e a senha no próximo acesso."
                            if exigir_troca_nova
                            else "Senha redefinida."
                        ),
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

        st.divider()
        eh_eu = alvo_id == (usuario_atual() or {}).get("id")
        rotulo = "Desativar usuário" if alvo["ativo"] else "Reativar usuário"
        if st.button(
            rotulo,
            disabled=eh_eu,
            key=f"alternar_ativo_{alvo_id}",
        ):
            try:
                auth.definir_ativo(alvo_id, not alvo["ativo"])
                definir_flash(
                    "success",
                    (
                        "Usuário desativado."
                        if alvo["ativo"]
                        else "Usuário reativado."
                    ),
                )
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))

        if eh_eu:
            st.caption("Você não pode desativar o próprio usuário.")


def _secao_lancamentos() -> None:
    hoje = date.today()

    with st.expander(
        "Registrar receita ou despesa",
        expanded=crud.contar_lancamentos() == 0,
    ):
        with st.form("form_novo_lancamento", clear_on_submit=True):
            col1, col2, col3 = st.columns(3)
            tipo = col1.selectbox("Tipo *", TIPOS_LANCAMENTO)
            data_lancamento = col2.date_input(
                "Data *",
                value=hoje,
                format="DD/MM/YYYY",
            )
            valor = col3.number_input(
                "Valor (R$) *",
                min_value=0.01,
                step=10.0,
                format="%.2f",
            )
            descricao = st.text_input(
                "Descrição *",
                placeholder="Ex.: Compra de material",
                help=(
                    "Para capitação, use a aba **Capitação (mensalidades)**: "
                    "a baixa gera a entrada automaticamente."
                ),
            )
            obreiros = crud.listar_obreiros()
            opcoes = opcoes_de_obreiros(obreiros)
            vinculo = st.selectbox(
                "Obreiro vinculado (opcional)",
                ["— Nenhum —", *opcoes],
                help="Use para doações, taxas individuais e outros vínculos.",
            )
            enviado = st.form_submit_button("Registrar", type="primary")

        if enviado:
            try:
                crud.criar_lancamento(
                    tipo=tipo,
                    descricao=descricao,
                    valor=Decimal(str(valor)),
                    data_lancamento=data_lancamento,
                    id_obreiro=opcoes.get(vinculo),
                )
                definir_flash("success", "Lançamento registrado com sucesso.")
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))

    st.subheader("Movimentações")
    col_mes, col_ano, col_tipo = st.columns([2, 1, 1])
    mes = col_mes.selectbox(
        "Mês",
        range(1, 13),
        index=hoje.month - 1,
        format_func=lambda numero: MESES[numero - 1],
        label_visibility="collapsed",
    )
    ano = col_ano.number_input(
        "Ano",
        min_value=2000,
        max_value=2100,
        value=hoje.year,
        step=1,
        label_visibility="collapsed",
    )
    filtro_tipo = col_tipo.selectbox(
        "Tipo",
        ("Todos", *TIPOS_LANCAMENTO),
        label_visibility="collapsed",
    )

    ano = int(ano)
    inicio = date(ano, mes, 1)
    fim = date(ano, mes, calendar.monthrange(ano, mes)[1])
    resumo = crud.resumo_financeiro(inicio, fim)

    col1, col2, col3 = st.columns(3)
    col1.metric("Entradas", brl(resumo["entradas"]))
    col2.metric("Saídas", brl(resumo["saidas"]))
    col3.metric("Saldo do mês", brl(resumo["saldo"]))

    lancamentos = crud.listar_lancamentos(
        inicio=inicio,
        fim=fim,
        tipo=None if filtro_tipo == "Todos" else filtro_tipo,
    )
    st.caption(f"{len(lancamentos)} lançamento(s) em {MESES[mes - 1]} de {ano}")

    if lancamentos:
        tabela_lancamentos(lancamentos)

        with st.expander("Excluir lançamento"):
            opcoes_lancamento = {
                (
                    f"#{item['id']} — {data_br(item['data'])} — "
                    f"{item['descricao']} ({brl(item['valor'])})"
                ): item["id"]
                for item in lancamentos
            }
            alvo = st.selectbox("Selecione o lançamento", list(opcoes_lancamento))
            confirmar = st.checkbox(
                "Confirmo a exclusão deste lançamento",
                help=(
                    "Se o lançamento estiver ligado a uma capitação paga, "
                    "ela voltará para pendente."
                ),
            )
            if st.button("Excluir", disabled=not confirmar):
                try:
                    crud.excluir_lancamento(opcoes_lancamento[alvo])
                    definir_flash("success", "Lançamento excluído.")
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))
    else:
        st.info("Nenhum lançamento encontrado para o período e filtro atuais.")


def _secao_mensalidades() -> None:
    hoje = date.today()

    col_mes, col_ano = st.columns(2)
    mes = col_mes.selectbox(
        "Competência (mês)",
        range(1, 13),
        index=hoje.month - 1,
        format_func=lambda numero: MESES[numero - 1],
    )
    ano = int(
        col_ano.number_input(
            "Competência (ano)",
            min_value=2000,
            max_value=2100,
            value=hoje.year,
            step=1,
        )
    )

    resumo = crud.resumo_mensalidades(mes, ano)
    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Previsto",
        brl(resumo["previsto"]),
        help=f"{resumo['total']} mensalidade(s) na competência.",
    )
    col2.metric("Recebido", brl(resumo["recebido"]))
    col3.metric("Em aberto", brl(resumo["pendente"]))

    st.subheader("Dar baixa na capitação")
    st.caption(
        f"As capitações vencem no dia **{DIA_VENCIMENTO}** de cada mês. "
        + (
            "O recibo é enviado por e-mail automaticamente após a baixa."
            if notificacoes.configurado()
            else "Recibo por e-mail: **não configurado** (veja as instruções "
            "no fim desta seção)."
        )
    )
    obreiros = crud.listar_obreiros()
    if not obreiros:
        st.info("Cadastre obreiros na Secretaria para lançar capitações.")
    else:
        opcoes = opcoes_de_obreiros(obreiros)
        rotulo = st.selectbox(
            "Obreiro",
            list(opcoes),
            key="baixa_obreiro",
        )
        id_obreiro = opcoes[rotulo]
        mensalidade = crud.obter_mensalidade(id_obreiro, mes, ano)

        if mensalidade is None:
            st.warning(
                "Ainda não há mensalidade para este obreiro nesta competência. "
                "Informe o valor para gerar e dar baixa."
            )
            col_valor, col_data = st.columns(2)
            valor_baixa = col_valor.number_input(
                "Valor da capitação (R$)",
                min_value=0.01,
                value=VALOR_CAPITACAO_PADRAO,
                step=10.0,
                format="%.2f",
                key=f"valor_baixa_{id_obreiro}",
            )
            data_baixa = col_data.date_input(
                "Data do pagamento",
                value=hoje,
                format="DD/MM/YYYY",
                key=f"data_baixa_{id_obreiro}",
            )
            if st.button(
                "Gerar e dar baixa",
                type="primary",
                key=f"btn_gerar_baixa_{id_obreiro}",
            ):
                try:
                    baixa = crud.dar_baixa_por_obreiro(
                        id_obreiro=id_obreiro,
                        mes=mes,
                        ano=ano,
                        valor=Decimal(str(valor_baixa)),
                        data_pagamento=data_baixa,
                    )
                    recibo = _notificar_recibo(
                        id_obreiro=id_obreiro,
                        mes=mes,
                        ano=ano,
                        valor=valor_baixa,
                        data_pagamento=data_baixa,
                        numero=baixa["mensalidade_id"],
                    )
                    definir_flash(
                        "success",
                        "Capitação gerada, baixa registrada e entrada lançada "
                        f"no financeiro.{recibo}",
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

        elif mensalidade["status"] == "Paga":
            st.success(
                f"Mensalidade de {brl(mensalidade['valor'])} paga em "
                f"{data_br(mensalidade['data_pagamento'])}."
            )
            confirmar = st.checkbox(
                "Confirmo o estorno e a remoção da entrada financeira",
                key=f"confirmar_estorno_{mensalidade['id']}",
            )
            if st.button(
                "Estornar baixa",
                disabled=not confirmar,
                key=f"btn_estorno_{mensalidade['id']}",
            ):
                try:
                    crud.estornar_baixa_mensalidade(mensalidade["id"])
                    definir_flash(
                        "success",
                        "Baixa estornada. A mensalidade voltou para pendente.",
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

        else:
            st.info(
                f"Mensalidade pendente de {brl(mensalidade['valor'])}. "
                "Se o valor estiver diferente, ajuste abaixo antes da baixa."
            )
            col_valor, col_data = st.columns(2)
            valor_pendente = col_valor.number_input(
                "Valor da capitação (R$)",
                min_value=0.01,
                value=float(mensalidade["valor"]),
                step=10.0,
                format="%.2f",
                key=f"valor_pend_{id_obreiro}",
            )
            data_baixa = col_data.date_input(
                "Data do pagamento",
                value=hoje,
                format="DD/MM/YYYY",
                key=f"data_baixa_{id_obreiro}",
            )

            col_salvar, col_baixa = st.columns(2)
            if col_salvar.button(
                "Salvar valor",
                key=f"btn_salvar_valor_{mensalidade['id']}",
                help="Corrige apenas o valor, sem registrar pagamento.",
            ):
                try:
                    crud.atualizar_valor_mensalidade(
                        mensalidade["id"], valor_pendente
                    )
                    definir_flash(
                        "success",
                        f"Valor atualizado para {brl(valor_pendente)}.",
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

            if col_baixa.button(
                "Dar baixa",
                type="primary",
                key=f"btn_baixa_{id_obreiro}",
            ):
                try:
                    crud.dar_baixa_mensalidade(
                        mensalidade["id"], data_baixa, valor_pendente
                    )
                    recibo = _notificar_recibo(
                        id_obreiro=id_obreiro,
                        mes=mes,
                        ano=ano,
                        valor=valor_pendente,
                        data_pagamento=data_baixa,
                        numero=mensalidade["id"],
                    )
                    definir_flash(
                        "success",
                        "Baixa registrada e entrada lançada no financeiro."
                        f"{recibo}",
                    )
                    st.rerun()
                except ValueError as erro:
                    st.error(str(erro))

    st.divider()
    st.subheader("Mensalidades da competência")
    filtro = st.selectbox(
        "Filtrar por situação",
        ("Todas", *STATUS_MENSALIDADE),
    )
    mensalidades = crud.listar_mensalidades(mes=mes, ano=ano)
    if filtro != "Todas":
        mensalidades = [
            item for item in mensalidades if item["status"] == filtro
        ]

    st.caption(
        f"{len(mensalidades)} mensalidade(s) em {MESES[mes - 1]} de {ano}"
    )
    if mensalidades:
        tabela_mensalidades(mensalidades)
    else:
        st.info("Nenhuma mensalidade para a competência selecionada.")

    st.divider()
    with st.expander("Gerar mensalidades em lote"):
        st.caption(
            "Cria uma mensalidade pendente para cada obreiro ativo que ainda "
            "não tenha a competência selecionada."
        )
        valor_lote = st.number_input(
            "Valor por obreiro (R$)",
            min_value=0.01,
            value=VALOR_CAPITACAO_PADRAO,
            step=10.0,
            format="%.2f",
        )
        if st.button("Gerar para obreiros ativos"):
            try:
                criadas, ignoradas = crud.gerar_mensalidades(
                    mes=mes,
                    ano=ano,
                    valor=Decimal(str(valor_lote)),
                )
                if criadas == 0 and ignoradas == 0:
                    definir_flash(
                        "info",
                        "Nenhum obreiro ativo para gerar mensalidades.",
                    )
                else:
                    definir_flash(
                        "success",
                        f"{criadas} mensalidade(s) gerada(s); "
                        f"{ignoradas} já existia(m).",
                    )
                st.rerun()
            except ValueError as erro:
                st.error(str(erro))

    if not notificacoes.configurado():
        with st.expander("Configurar recibo por e-mail"):
            st.markdown(
                "Para enviar o recibo automaticamente, cadastre as variáveis "
                "abaixo em **Settings › Secrets** do Streamlit Cloud "
                "(e no arquivo `.env` para testes locais):\n\n"
                "```toml\n"
                'SMTP_HOST = "smtp.gmail.com"\n'
                "SMTP_PORT = 587\n"
                'SMTP_USER = "seuemail@gmail.com"\n'
                'SMTP_PASSWORD = "senha-de-app-do-gmail"\n'
                'SMTP_FROM = "Seu nome <seuemail@gmail.com>"\n'
                'NOME_LOJA = "Nome da Loja"\n'
                "```\n\n"
                "No Gmail, a senha precisa ser uma **senha de app** "
                "(Conta Google › Segurança › Verificação em duas etapas › "
                "Senhas de app). Depois de salvar, o app reinicia e o envio "
                "passa a valer para as próximas baixas."
            )


def _secao_minha_situacao() -> None:
    usuario = usuario_atual() or {}
    id_obreiro = usuario.get("id_obreiro")

    if not id_obreiro:
        st.warning(
            "Seu usuário não está vinculado a um obreiro. "
            "Fale com um administrador."
        )
        return

    obreiro = crud.obter_obreiro(id_obreiro)
    if obreiro is None:
        st.warning("O obreiro vinculado ao seu usuário não foi encontrado.")
        return

    st.caption(f"Obreiro: **{obreiro['nome']}** — CIM {obreiro['cim']}")

    hoje = date.today()
    anos = crud.anos_financeiros_obreiro(id_obreiro)
    ano = int(
        st.selectbox(
            "Ano de referência",
            anos,
            index=0,
            key="ano_minha_situacao",
        )
    )
    resumo = crud.resumo_mensalidades_obreiro(id_obreiro, ano)

    col1, col2, col3 = st.columns(3)
    col1.metric(
        "Mensalidades pagas",
        f"{resumo['pagas']} de {resumo['total']}",
    )
    col2.metric("Valor pago", brl(resumo["valor_pago"]))
    col3.metric("Em aberto", brl(resumo["valor_pendente"]))

    st.subheader("Minhas mensalidades")
    mensalidades = crud.listar_mensalidades(id_obreiro=id_obreiro, ano=ano)
    if mensalidades:
        tabela_mensalidades(mensalidades, incluir_id=False)
    else:
        st.info("Nenhuma mensalidade registrada para este ano.")

    st.subheader("Minhas contribuições")
    contribuicoes = crud.listar_lancamentos(
        id_obreiro=id_obreiro,
        tipo="Entrada",
        inicio=date(ano, 1, 1),
        fim=date(ano, 12, 31),
    )
    if contribuicoes:
        tabela_lancamentos(contribuicoes, incluir_id=False)
    else:
        st.info("Nenhuma contribuição registrada para este ano.")


# ---------------------------------------------------------------------------
# Páginas principais
# ---------------------------------------------------------------------------


def pagina_secretaria() -> None:
    st.title("Secretaria")
    mostrar_flash()

    if eh_admin():
        aba_obreiros, aba_acessos = st.tabs(
            ["Obreiros", "Acessos ao sistema"]
        )
        with aba_obreiros:
            _secao_obreiros(admin=True)
        with aba_acessos:
            _secao_usuarios()
    else:
        st.caption(
            "Consulta dos obreiros da Loja. Alterações são exclusivas "
            "da administração."
        )
        _secao_obreiros(admin=False)


def pagina_tesouraria() -> None:
    exigir_admin()
    st.title("Tesouraria")
    mostrar_flash()
    _alerta_debitos()

    aba_lancamentos, aba_mensalidades = st.tabs(
        ["Lançamentos", "Capitação (mensalidades)"]
    )
    with aba_lancamentos:
        _secao_lancamentos()
    with aba_mensalidades:
        _secao_mensalidades()


def _secao_demonstrativo_pdf(hoje: date) -> None:
    """Gera o demonstrativo financeiro do período em PDF."""
    st.subheader("Demonstrativo financeiro em PDF")
    st.caption(
        "Arquivo com o resumo de entradas, saídas, saldo e a lista completa "
        "de lançamentos do período. Para imprimir, abra o PDF e use Ctrl+P."
    )

    modo = st.radio(
        "Período do demonstrativo",
        ("Mês", "Personalizado"),
        horizontal=True,
        key="pdf_modo",
    )

    if modo == "Mês":
        col_mes, col_ano = st.columns(2)
        mes_pdf = col_mes.selectbox(
            "Mês",
            range(1, 13),
            index=hoje.month - 1,
            format_func=lambda numero: MESES[numero - 1],
            key="pdf_mes",
        )
        ano_pdf = int(
            col_ano.number_input(
                "Ano",
                min_value=2000,
                max_value=2100,
                value=hoje.year,
                step=1,
                key="pdf_ano",
            )
        )
        inicio = date(ano_pdf, mes_pdf, 1)
        fim = date(
            ano_pdf,
            mes_pdf,
            calendar.monthrange(ano_pdf, mes_pdf)[1],
        )
    else:
        col_ini, col_fim = st.columns(2)
        inicio = col_ini.date_input(
            "De",
            value=date(hoje.year, 1, 1),
            format="DD/MM/YYYY",
            key="pdf_inicio",
        )
        fim = col_fim.date_input(
            "Até",
            value=hoje,
            format="DD/MM/YYYY",
            key="pdf_fim",
        )

    if inicio > fim:
        st.error("A data inicial precisa ser anterior à data final.")
        return

    lancamentos = crud.listar_lancamentos(inicio=inicio, fim=fim)
    resumo = crud.resumo_financeiro(inicio, fim)
    saldo = crud.saldo_total()["saldo"]

    pdf = relatorios.gerar_demonstrativo(
        inicio=inicio,
        fim=fim,
        lancamentos=lancamentos,
        resumo=resumo,
        saldo_acumulado=saldo,
        loja=notificacoes.nome_loja(),
    )

    st.download_button(
        "📄 Baixar demonstrativo em PDF",
        data=pdf,
        file_name=(
            f"demonstrativo_{inicio:%Y-%m-%d}_a_{fim:%Y-%m-%d}.pdf"
        ),
        mime="application/pdf",
        type="primary",
        key="download_pdf",
    )
    st.caption(
        f"{len(lancamentos)} lançamento(s) · "
        f"Entradas {brl(resumo['entradas'])} · "
        f"Saídas {brl(resumo['saidas'])} · "
        f"Resultado {brl(resumo['saldo'])}"
    )


def pagina_relatorios() -> None:
    st.title("Relatórios")
    mostrar_flash()

    admin = eh_admin()
    if admin:
        _alerta_debitos()
    usuario = usuario_atual() or {}
    id_obreiro = None if admin else usuario.get("id_obreiro")
    hoje = date.today()

    saldo = crud.saldo_total()
    atrasadas = crud.listar_mensalidades_atrasadas(id_obreiro=id_obreiro)
    total_atrasado = sum(
        (item["valor_total"] for item in atrasadas),
        Decimal("0"),
    )

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("Saldo atual", brl(saldo["saldo"]))
    col2.metric("Entradas (total)", brl(saldo["entradas"]))
    col3.metric("Saídas (total)", brl(saldo["saidas"]))
    col4.metric(
        (
            "Mensalidades atrasadas"
            if admin
            else "Minhas mensalidades atrasadas"
        ),
        brl(total_atrasado),
        help=(
            f"{len(atrasadas)} obreiro(s) com competências vencidas "
            f"(pagamento após o dia {DIA_VENCIMENTO})."
        ),
    )

    st.divider()
    st.subheader("Entradas vs. saídas")
    periodo = st.selectbox(
        "Período do gráfico",
        (6, 12),
        index=0,
        format_func=lambda meses: f"Últimos {meses} meses",
        key="periodo_grafico",
    )
    dados = crud.evolucao_mensal(periodo)
    grafico = pd.DataFrame(
        [
            {
                "Mês": item["rotulo"],
                "Entradas": item["entradas"],
                "Saídas": item["saidas"],
            }
            for item in dados
        ]
    )
    st.bar_chart(
        grafico,
        x="Mês",
        y=["Entradas", "Saídas"],
        x_label="Mês",
        y_label="Valor (R$)",
        height=320,
    )

    st.divider()
    st.subheader(
        "Obreiros com mensalidade atrasada"
        if admin
        else "Minhas mensalidades atrasadas"
    )
    st.caption(
        f"Consideram-se atrasadas as competências pendentes cujo vencimento "
        f"(dia {DIA_VENCIMENTO}) já passou."
    )

    if atrasadas:
        st.dataframe(
            dataframe_atrasadas(atrasadas),
            hide_index=True,
            width="stretch",
            column_config={
                "Valor (R$)": st.column_config.NumberColumn(format="%.2f"),
                "Qtd": st.column_config.NumberColumn(width="small"),
            },
        )
    elif admin:
        st.success("Nenhuma mensalidade atrasada.")
    else:
        st.success("Você não possui mensalidades atrasadas.")

    if admin:
        st.divider()
        _secao_demonstrativo_pdf(hoje)
        return

    st.divider()
    situacao = (
        crud.resumo_mensalidades_obreiro(id_obreiro, hoje.year)
        if id_obreiro
        else None
    )
    if situacao is not None:
        em_aberto = situacao["total"] - situacao["pagas"]
        st.info(
            f"Capitações de {hoje.year}: {situacao['pagas']} paga(s) e "
            f"{em_aberto} em aberto."
        )

    with st.expander("Minha situação financeira"):
        _secao_minha_situacao()


# ---------------------------------------------------------------------------
# Navegação
# ---------------------------------------------------------------------------

PAGINAS_ADMIN: dict[str, Callable[[], None]] = {
    "Secretaria": pagina_secretaria,
    "Tesouraria": pagina_tesouraria,
    "Relatórios": pagina_relatorios,
}

PAGINAS_MEMBRO: dict[str, Callable[[], None]] = {
    "Secretaria": pagina_secretaria,
    "Relatórios": pagina_relatorios,
}

ICONES = {
    "Secretaria": "📋",
    "Tesouraria": "💰",
    "Relatórios": "📊",
}


def sidebar(
    paginas: dict[str, Callable[[], None]],
    usuario: dict,
) -> str:
    with st.sidebar:
        st.image(BRAND_IMAGE, width=BRAND_LARGURA)
        st.markdown("## Gestão da Loja")
        st.caption(f"**{usuario['nome']}**")
        st.caption(f"Perfil: {usuario['role']}")

        if st.session_state.get("pagina") not in paginas:
            st.session_state["pagina"] = (
                PAGINA_INICIAL if PAGINA_INICIAL in paginas else next(iter(paginas))
            )

        st.divider()
        pagina = st.radio(
            "Navegação",
            list(paginas),
            key="pagina",
            format_func=lambda nome: f"{ICONES.get(nome, '')} {nome}",
            label_visibility="collapsed",
        )
        st.divider()
        st.caption(f"Banco: **{descricao_banco()}**")
        st.button("Sair", on_click=_sair, width="stretch")

    return pagina


def main() -> None:
    dados_sessao = st.session_state.get("usuario")
    if not dados_sessao:
        tela_login()
        return

    # Recarrega o usuário a cada execução: mudanças de perfil ou desativação
    # feitas pelo administrador passam a valer imediatamente.
    atual = auth.obter_usuario(dados_sessao["id"])
    if atual is None or not atual["ativo"]:
        st.session_state.pop("usuario", None)
        st.session_state.pop("pagina", None)
        st.warning("Sua conta foi desativada. Fale com um administrador.")
        tela_login()
        return

    st.session_state["usuario"] = atual

    # Primeiro acesso com credenciais temporárias: nenhuma página é liberada
    # antes da definição do novo login e da nova senha.
    if atual.get("deve_trocar_credenciais"):
        tela_primeiro_acesso(atual)
        return

    paginas = PAGINAS_ADMIN if atual["role"] == "Administrador" else PAGINAS_MEMBRO
    pagina = sidebar(paginas, atual)
    paginas[pagina]()


main()
