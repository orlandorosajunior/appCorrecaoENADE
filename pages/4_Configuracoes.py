"""
Pagina: Configuracoes - chave de API do Gemini, modelo padrao, sensibilidade
padrao de leitura do OMR e nota maxima padrao da questao discursiva.
"""

import streamlit as st

from auth import exigir_login

from config import CONFIG_PATH, load_config, save_config
from db import alterar_senha, create_usuario, delete_usuario, list_usuarios
from gemini_grading import DEFAULT_MODEL

st.set_page_config(page_title="Configurações", layout="wide")

exigir_login()

st.title("Configurações")
st.caption(
    f"Salvas localmente em `{CONFIG_PATH}` — separado do banco de simulados e correções. "
    "As demais páginas já carregam esses valores como padrão automaticamente."
)

cfg = load_config()

# ---------------------------------------------------------------------------
# IA: provedor, chaves e modelos
# ---------------------------------------------------------------------------
from ai_grading import PROVEDORES, IAGradingError, resolver_ia, testar_conexao

st.subheader("Inteligência artificial (leitura da discursiva e identificação de alunos)")
st.caption(
    "Escolha o provedor padrão e cadastre as chaves aqui. As páginas de correção usam estas chaves "
    "automaticamente e **não** mostram nem pedem a chave — nelas você só pode trocar o provedor e o "
    "modelo para aquela tela."
)

chaves_prov = list(PROVEDORES)
ia_provider = st.radio(
    "Provedor padrão", chaves_prov, index=chaves_prov.index(cfg["ia_provider"]) if cfg["ia_provider"] in chaves_prov else 0,
    format_func=lambda k: PROVEDORES[k], horizontal=True,
)

col_g, col_q = st.columns(2)
with col_g:
    st.markdown("**Google Gemini**")
    api_key = st.text_input(
        "Chave de API do Gemini", value=cfg["gemini_api_key"], type="password",
        help="Disponível em aistudio.google.com → \"Get API key\". Para dados reais de alunos, "
        "prefira uma chave com cobrança vinculada (veja a observação de privacidade no README).",
    )
    modelo = st.text_input("Modelo do Gemini", value=cfg["gemini_model"])
with col_q:
    st.markdown("**Groq**")
    groq_api_key = st.text_input(
        "Chave de API da Groq", value=cfg["groq_api_key"], type="password",
        help="Disponível em console.groq.com → API Keys. O modelo precisa aceitar imagens "
        "(veja a lista de modelos com visão em console.groq.com/docs/vision).",
    )
    groq_model = st.text_input("Modelo da Groq (com visão)", value=cfg["groq_model"])

st.caption(
    "Salve as configurações (botão no fim da página) antes de testar. O teste usa os valores salvos."
)
col_t1, col_t2 = st.columns(2)
for coluna, prov in ((col_t1, "gemini"), (col_t2, "groq")):
    if coluna.button(f"Testar {PROVEDORES[prov]}", key=f"testar_{prov}"):
        ia_teste = resolver_ia(load_config(), prov)
        if not ia_teste["api_key"]:
            coluna.error("Cadastre e salve uma chave antes de testar.")
        else:
            with coluna:
                with st.spinner(f"Testando {PROVEDORES[prov]}..."):
                    try:
                        usado = testar_conexao(ia_teste)
                        st.success(f"Conexão funcionando — o modelo {usado} respondeu normalmente.")
                    except IAGradingError as e:
                        st.error(f"Falha ao testar: {e}")

st.divider()

# ---------------------------------------------------------------------------
# Leitura do cartão de respostas (OMR)
# ---------------------------------------------------------------------------
st.subheader("Leitura do cartão de respostas (OMR)")
st.caption(
    "Valores padrão usados ao processar as folhas (gabarito e provas dos alunos). "
    "Continuam ajustáveis manualmente em cada tela, se precisar de exceções."
)
col1, col2 = st.columns(2)
fill_threshold = col1.slider(
    "Sensibilidade mínima de preenchimento (padrão)", 0.10, 0.80, float(cfg["fill_threshold"]), step=0.05
)
relative_margin = col2.slider(
    "Margem relativa (padrão)", 1.05, 2.0, float(cfg["relative_margin"]), step=0.05
)

st.divider()

# ---------------------------------------------------------------------------
# Questão discursiva
# ---------------------------------------------------------------------------
st.subheader("Questão discursiva")
discursiva_nota_max = st.number_input(
    "Nota máxima padrão (quando o simulado não tem rubrica cadastrada)",
    0.0,
    100.0,
    float(cfg["discursiva_nota_max_padrao"]),
    step=0.5,
    help="Escala em que você pontua a discursiva manualmente (ex.: 10). Não é a mesma coisa "
    "que o peso dela na nota final — isso é definido logo abaixo.",
)

st.markdown("**Peso da discursiva na nota final (0-1000)**")
st.caption(
    "Quantos dos 1000 pontos totais a questão discursiva vale. Os pontos restantes são "
    "divididos igualmente entre as 31 questões objetivas."
)
peso_discursiva_pontos = st.number_input(
    "Peso da discursiva (pontos de 1000)",
    0.0,
    1000.0,
    float(cfg["peso_discursiva_pontos"]),
    step=10.0,
    label_visibility="collapsed",
)
pontos_por_objetiva_preview = (1000.0 - peso_discursiva_pontos) / 31
st.caption(
    f"Com esse peso: cada questão objetiva vale **{pontos_por_objetiva_preview:.2f}** pontos "
    f"(31 questões × {pontos_por_objetiva_preview:.2f} = {31*pontos_por_objetiva_preview:.1f}) "
    f"e a discursiva vale até **{peso_discursiva_pontos:.0f}** pontos — soma máxima: "
    f"{31*pontos_por_objetiva_preview + peso_discursiva_pontos:.0f} / 1000."
)

st.divider()

if st.button("Salvar configurações", type="primary"):
    save_config(
        {
            "ia_provider": ia_provider,
            "gemini_api_key": api_key.strip(),
            "gemini_model": modelo.strip() or DEFAULT_MODEL,
            "groq_api_key": groq_api_key.strip(),
            "groq_model": groq_model.strip() or "qwen/qwen3.8-27b",
            "fill_threshold": fill_threshold,
            "relative_margin": relative_margin,
            "discursiva_nota_max_padrao": discursiva_nota_max,
            "peso_discursiva_pontos": peso_discursiva_pontos,
        }
    )
    st.success("Configurações salvas.")
    st.rerun()

with st.expander("Onde os dados ficam salvos"):
    st.markdown(
        f"""
- **Configurações (esta página):** `{CONFIG_PATH}`
- **Simulados, gabaritos e correções:** `data/gabarito_app.db`
- **Fotos das respostas discursivas:** `data/discursivas/`
"""
    )

st.divider()

# ---------------------------------------------------------------------------
# Usuários (login)
# ---------------------------------------------------------------------------
st.subheader("Usuários")
st.caption(
    "Contas que têm acesso ao sistema. Qualquer usuário logado vê e edita todos os dados — "
    "isso controla QUEM entra, não o que cada um pode fazer dentro do app."
)

usuarios_df = list_usuarios()
view_usuarios = usuarios_df.rename(columns={"id": "ID", "username": "Usuário", "data_criacao": "Criado em"})
st.dataframe(view_usuarios[["ID", "Usuário", "Criado em"]], width='stretch', hide_index=True)

with st.expander("Criar novo usuário"):
    with st.form("novo_usuario_form", clear_on_submit=True):
        novo_username = st.text_input("Usuário")
        nova_senha_criar = st.text_input("Senha", type="password")
        nova_senha_criar2 = st.text_input("Confirme a senha", type="password")
        criar = st.form_submit_button("Criar usuário")
        if criar:
            if not novo_username.strip() or not nova_senha_criar:
                st.error("Preencha usuário e senha.")
            elif len(nova_senha_criar) < 6:
                st.error("Use uma senha com pelo menos 6 caracteres.")
            elif nova_senha_criar != nova_senha_criar2:
                st.error("As senhas não coincidem.")
            else:
                try:
                    create_usuario(novo_username, nova_senha_criar)
                    st.success(f'Usuário "{novo_username}" criado.')
                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

with st.expander("Alterar minha senha"):
    with st.form("alterar_senha_form", clear_on_submit=True):
        senha_atual = st.text_input("Senha atual", type="password")
        nova_senha = st.text_input("Nova senha", type="password")
        nova_senha2 = st.text_input("Confirme a nova senha", type="password")
        alterar = st.form_submit_button("Alterar senha")
        if alterar:
            if len(nova_senha) < 6:
                st.error("Use uma senha com pelo menos 6 caracteres.")
            elif nova_senha != nova_senha2:
                st.error("As senhas não coincidem.")
            else:
                usuario_atual = st.session_state.get("usuario_logado", "")
                if alterar_senha(usuario_atual, senha_atual, nova_senha):
                    st.success("Senha alterada com sucesso.")
                else:
                    st.error("Senha atual incorreta.")

with st.expander("Excluir um usuário"):
    if len(usuarios_df) <= 1:
        st.info("Não é possível excluir o único usuário cadastrado.")
    else:
        opcoes_usuario = {f"#{row.id} — {row.username}": row.id for row in usuarios_df.itertuples()}
        escolha_usuario = st.selectbox("Usuário", list(opcoes_usuario.keys()), key="del_usuario_select")
        confirmar_usuario = st.checkbox("Confirmo a exclusão deste usuário.", key="del_usuario_confirm")
        if st.button("Excluir usuário", disabled=not confirmar_usuario):
            username_excluido = escolha_usuario.split("— ", 1)[1]
            delete_usuario(opcoes_usuario[escolha_usuario])
            st.success("Usuário excluído.")
            if username_excluido == st.session_state.get("usuario_logado"):
                st.session_state["autenticado"] = False
                st.session_state.pop("usuario_logado", None)
            st.rerun()

st.divider()

# ---------------------------------------------------------------------------
# Dados do sistema: dataset de exemplo e limpeza total
# ---------------------------------------------------------------------------
from sample_data import apagar_todos_os_dados, inserir_dataset_exemplo

st.subheader("Dados do sistema")

st.markdown("**Dataset sintético de exemplo**")
st.caption(
    "Insere 3 simulados, 2 turmas, 20 alunos e 60 correções (com discursiva avaliada, horários e "
    "temas por questão) — nomes e notas inventados, só para testar dashboards, relatórios em PDF e "
    "a evolução por aluno. Tudo aparece com \"EXEMPLO\" no nome. Não apaga nada que já exista."
)
if st.button("Inserir dataset de exemplo", key="btn_inserir_exemplo"):
    with st.spinner("Inserindo dados de exemplo..."):
        res_ex = inserir_dataset_exemplo()
    st.success(
        f"Inseridos: {res_ex['simulados']} simulados, {res_ex['turmas']} turmas, "
        f"{res_ex['alunos']} alunos e {res_ex['correcoes']} correções."
    )

st.markdown("**Apagar todos os dados**")
st.caption(
    "Exclui, de forma definitiva, todas as correções (provas), as fotos das discursivas, os alunos, "
    "as turmas e os simulados. As configurações (chave de API, pesos) são mantidas. Faça um backup "
    "antes (por exemplo, exportando em Exportar) se precisar dos dados."
)
apagar_usuarios_tb = st.checkbox(
    "Apagar também os usuários (reset completo: no próximo acesso será preciso criar um novo "
    "usuário e senha)",
    key="apagar_usuarios_tb",
)
confirmacao_texto = st.text_input('Para confirmar, digite APAGAR', key="apagar_confirmacao")
if st.button(
    "Apagar todos os dados",
    type="primary",
    disabled=confirmacao_texto.strip() != "APAGAR",
    key="btn_apagar_tudo",
):
    contagem = apagar_todos_os_dados(apagar_usuarios=apagar_usuarios_tb)
    for k in list(st.session_state.keys()):
        if k.startswith(("lote_", "hist_", "recorrigir_", "corrigir_")):
            del st.session_state[k]
    if apagar_usuarios_tb:
        st.session_state["autenticado"] = False
        st.session_state.pop("usuario_logado", None)
    else:
        st.session_state["apagou_msg"] = (
            f"Dados apagados: {contagem['correcoes']} correções, {contagem['alunos']} alunos, "
            f"{contagem['turmas']} turmas, {contagem['simulados']} simulados e "
            f"{contagem['fotos_discursivas']} foto(s) de discursiva."
        )
    st.rerun()

if "apagou_msg" in st.session_state:
    st.success(st.session_state.pop("apagou_msg"))
