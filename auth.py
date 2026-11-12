"""
auth.py
Portao de autenticacao chamado no topo de toda pagina do app (inclusive a
inicial). Enquanto a sessao do navegador nao estiver autenticada, mostra a
tela de login (ou o cadastro da primeira conta, se ainda nao existir
nenhum usuario) e interrompe a execucao da pagina com st.stop().

IMPORTANTE: isto restringe o acesso a UM login compartilhado por sessao de
navegador (st.session_state), nao e um sistema de permissoes por papel
(todo usuario logado ve e edita todos os dados). E adequado para manter
pessoas nao autorizadas fora do app, nao para segregar dados entre
professores diferentes usando a mesma instalacao.
"""

import streamlit as st

from db import count_usuarios, create_usuario, init_db, verificar_login


def exigir_login():
    """Chame logo apos st.set_page_config() no topo de cada pagina.
    Se ja autenticado, apenas mostra o status/botao de sair na barra lateral
    e retorna. Caso contrario, mostra o formulario de login (ou de
    cadastro da primeira conta) e interrompe a pagina com st.stop()."""
    init_db()

    if st.session_state.get("autenticado") and count_usuarios() == 0:
        # sistema zerado (sem usuarios): invalida a sessao e forca o cadastro da primeira conta
        st.session_state["autenticado"] = False
        st.session_state.pop("usuario_logado", None)

    if st.session_state.get("autenticado"):
        with st.sidebar:
            st.caption(f"Logado como **{st.session_state.get('usuario_logado', '')}**")
            if st.button("Sair", key="botao_sair_sidebar"):
                st.session_state["autenticado"] = False
                st.session_state.pop("usuario_logado", None)
                st.rerun()
        return

    st.title("Corretor de Gabarito — Login")

    if count_usuarios() == 0:
        st.info(
            "Nenhum usuário cadastrado ainda. Crie a primeira conta (com acesso completo ao "
            "sistema) para começar a usar o app."
        )
        with st.form("bootstrap_form"):
            username = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            senha2 = st.text_input("Confirme a senha", type="password")
            enviar = st.form_submit_button("Criar conta e entrar")
            if enviar:
                if not username.strip() or not senha:
                    st.error("Preencha usuário e senha.")
                elif len(senha) < 6:
                    st.error("Use uma senha com pelo menos 6 caracteres.")
                elif senha != senha2:
                    st.error("As senhas não coincidem.")
                else:
                    create_usuario(username, senha)
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = username.strip()
                    st.rerun()
    else:
        with st.form("login_form"):
            username = st.text_input("Usuário")
            senha = st.text_input("Senha", type="password")
            enviar = st.form_submit_button("Entrar")
            if enviar:
                if verificar_login(username, senha):
                    st.session_state["autenticado"] = True
                    st.session_state["usuario_logado"] = username.strip()
                    st.rerun()
                else:
                    st.error("Usuário ou senha incorretos.")

    st.stop()