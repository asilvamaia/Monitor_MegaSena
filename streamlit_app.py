import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
import random
from collections import Counter
from datetime import datetime, date
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Mega Mobile", layout="centered", page_icon="🎱")

# --- GERENCIAMENTO DE TEMA (CLARO/ESCURO) ---
if 'theme' not in st.session_state:
    st.session_state.theme = 'dark' # Padrão

def toggle_theme():
    if st.session_state.theme == 'dark':
        st.session_state.theme = 'light'
    else:
        st.session_state.theme = 'dark'

# Definição das cores baseadas no tema
if st.session_state.theme == 'dark':
    bg_color = "#0e1117"
    card_bg = "#262730"
    text_color = "#fafafa"
    btn_sec_bg = "#262730"
    border_color = "#3b3d45"
else:
    bg_color = "#ffffff"
    card_bg = "#f0f2f6"
    text_color = "#31333F"
    btn_sec_bg = "#ffffff"
    border_color = "#e0e0e0"

# --- CSS DINÂMICO E CORREÇÕES DE LAYOUT ---
st.markdown(f"""
<style>
    /* Aplica o tema ao fundo global */
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
    }}
    
    /* Ajuste fino do container principal para mobile */
    .block-container {{
        padding-top: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        padding-bottom: 6rem;
    }}
    
    /* CORREÇÃO DO GRID DE NÚMEROS */
    /* Garante que os botões dentro das colunas ocupem largura total e altura fixa */
    div[data-testid="column"] button {{
        width: 100% !important;
        min-height: 45px !important;
        max-height: 45px !important;
        padding: 0px !important;
        margin: 2px 0px !important; /* Pequeno espaçamento vertical */
        font-weight: bold;
        border-radius: 8px !important;
    }}
    
    /* Remove espaçamentos laterais excessivos das colunas do Streamlit */
    div[data-testid="column"] {{
        padding: 0 2px !important;
        min-width: 0 !important;
    }}
    
    /* Botões de Ação Principais (Salvar, Gerar) */
    .stButton button[kind="primary"] {{
        width: 100%;
        border-radius: 12px;
        height: 50px;
        font-size: 18px;
        font-weight: 600;
        margin-top: 10px;
        background-color: #ff4b4b !important;
        color: white !important;
        border: none;
    }}
    
    /* Botões do Cabeçalho (Atualizar e Tema) */
    .header-btn button {{
        background-color: {btn_sec_bg} !important;
        color: {text_color} !important;
        border: 1px solid {border_color} !important;
        border-radius: 8px;
        height: 40px;
        width: 100%;
    }}
    
    /* Estilo dos Cards (Expander e Containers) */
    div[data-testid="stExpander"], div[data-testid="stContainer"] {{
        background-color: {card_bg};
        border-radius: 10px;
        border: 1px solid {border_color};
        color: {text_color};
    }}
    
    /* Abas */
    .stTabs [data-baseweb="tab-list"] {{
        gap: 4px;
        background-color: transparent;
    }}
    .stTabs [data-baseweb="tab"] {{
        height: 45px;
        background-color: {card_bg};
        border-radius: 8px;
        color: {text_color};
        flex: 1;
        font-size: 13px;
        padding: 4px;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {bg_color};
        border: 1px solid {border_color};
        border-bottom: 3px solid #ff4b4b;
        font-weight: bold;
    }}
    
    /* Esconde Header Padrão */
    header[data-testid="stHeader"] {{ display: none; }}
    
    /* Ajuste de Texto */
    h3, p, span, div {{
        color: {text_color};
    }}
</style>
""", unsafe_allow_html=True)

# --- CONFIGURAÇÃO DO ÍCONE IOS ---
def setup_ios_icon():
    icon_url = "https://img.icons8.com/color/480/clover--v1.png"
    st.markdown(f"""
        <link rel="apple-touch-icon" href="{icon_url}">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-title" content="MegaApp">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS ---
DB_FILE = "megasena.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS app_config (
            key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numbers TEXT, start_date TEXT, active INTEGER DEFAULT 1, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS results (
            concurso INTEGER PRIMARY KEY, data_sorteio TEXT, dezenas TEXT)''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# --- LÓGICA DE DADOS ---
def fetch_latest_results():
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            draws = data if isinstance(data, list) else [data]
            conn = get_db_connection()
            cursor = conn.cursor()
            count = 0
            for draw in draws:
                concurso = draw.get('concurso')
                data_sorteio = draw.get('data')
                dezenas = json.dumps([int(d) for d in draw.get('dezenas', [])])
                try:
                    dt_obj = datetime.strptime(data_sorteio, "%d/%m/%Y")
                    data_iso = dt_obj.strftime("%Y-%m-%d")
                    cursor.execute('INSERT OR IGNORE INTO results (concurso, data_sorteio, dezenas) VALUES (?, ?, ?)', 
                                 (concurso, data_iso, dezenas))
                    if cursor.rowcount > 0: count += 1
                except: continue
            conn.commit()
            conn.close()
            return count
    except: return 0
    return 0

def get_statistics():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT concurso, dezenas FROM results ORDER BY concurso DESC", conn)
    conn.close()
    if df.empty: return None, None, None
    all_numbers = []
    for d in df['dezenas']: all_numbers.extend(json.loads(d))
    counter = Counter(all_numbers)
    for i in range(1, 61):
        if i not in counter: counter[i] = 0
    df_freq = pd.DataFrame.from_dict(counter, orient='index', columns=['frequencia']).sort_index()
    last_seen = {}
    latest_concurso = df.iloc[0]['concurso']
    for index, row in df.iterrows():
        nums = json.loads(row['dezenas'])
        for n in nums:
            if n not in last_seen: last_seen[n] = row['concurso']
        if len(last_seen) == 60: break
    lag_data = {}
    for i in range(1, 61):
        if i in last_seen: lag_data[i] = latest_concurso - last_seen[i]
        else: lag_data[i] = latest_concurso 
    df_lag = pd.DataFrame.from_dict(lag_data, orient='index', columns=['atraso'])
    return df_freq, df_lag, counter

def generate_game(qtd, strategy="random", counter=None):
    if strategy == "random" or not counter:
        return sorted(random.sample(range(1, 61), qtd))
    numbers = list(counter.keys())
    if strategy == "smart":
        weights = [counter[n] + 1 for n in numbers]
        selection = set()
        while len(selection) < qtd: selection.add(random.choices(numbers, weights=weights, k=1)[0])
        return sorted(list(selection))
    elif strategy == "cold":
        weights = [1/(counter[n]+1) for n in numbers]
        selection = set()
        while len(selection) < qtd: selection.add(random.choices(numbers, weights=weights, k=1)[0])
        return sorted(list(selection))
    elif strategy == "balanced":
        qtd_hot = (qtd // 2) + (qtd % 2)
        sorted_by_freq = sorted(numbers, key=lambda x: counter[x], reverse=True)
        mid_point = len(sorted_by_freq) // 2
        hot_pool = sorted_by_freq[:mid_point]
        cold_pool = sorted_by_freq[mid_point:]
        selection = set()
        while len(selection) < qtd_hot: selection.add(random.choice(hot_pool))
        while len(selection) < qtd:
            pick = random.choice(cold_pool)
            if pick not in selection: selection.add(pick)
        return sorted(list(selection))
    return sorted(random.sample(range(1, 61), qtd))

def check_game_matches(game_numbers, start_date_iso):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM results WHERE data_sorteio >= ? ORDER BY data_sorteio DESC", conn, params=(start_date_iso,))
    conn.close()
    game_set = set(game_numbers)
    matches = []
    for _, row in df.iterrows():
        draw_nums = set(json.loads(row['dezenas']))
        hits = game_set.intersection(draw_nums)
        if len(hits) > 0:
            matches.append({
                'concurso': row['concurso'], 'data': row['data_sorteio'],
                'acertos': len(hits), 'dezenas_sorteadas': sorted(list(draw_nums)),
                'dezenas_acertadas': sorted(list(hits))
            })
    return matches

def toggle_number(num):
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []
    if num in st.session_state.selected_numbers:
        st.session_state.selected_numbers.remove(num)
    elif len(st.session_state.selected_numbers) < 20:
        st.session_state.selected_numbers.append(num)

def clear_selection(): st.session_state.selected_numbers = []

# ==========================================
# APP MAIN
# ==========================================
def main():
    setup_ios_icon()
    init_db()
    
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []

    # --- CABEÇALHO ---
    # Colunas: [Atualizar] [Tema] [Título]
    c_btn1, c_btn2, c_title = st.columns([1.5, 1.5, 6])
    
    # Adicionando classe CSS para estilização específica
    with c_btn1:
        st.markdown('<div class="header-btn">', unsafe_allow_html=True)
        if st.button("🔄", help="Atualizar Base"):
            with st.spinner("."):
                count = fetch_latest_results()
                conn = get_db_connection()
                conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES ('last_update', ?)", (datetime.now().strftime("%Y-%m-%d"),))
                conn.commit(); conn.close()
            if count > 0: st.toast(f"{count} novos!", icon="✅")
            else: st.toast("Tudo OK!", icon="👍")
            time.sleep(0.5); st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with c_btn2:
        st.markdown('<div class="header-btn">', unsafe_allow_html=True)
        # Ícone muda conforme o tema
        theme_icon = "🌞" if st.session_state.theme == 'dark' else "🌙"
        if st.button(theme_icon, on_click=toggle_theme, help="Mudar Tema"):
            st.rerun()
        st.markdown('</div>', unsafe_allow_html=True)

    with c_title:
        st.subheader("Mega Mobile")

    # --- ABAS ---
    tab_games, tab_stats, tab_gen, tab_config = st.tabs(["📋 Jogos", "📊 Stats", "🎲 Gerar", "⚙️ Config"])

    # --- ABA JOGOS ---
    with tab_games:
        with st.expander("➕ Novo Jogo Manual", expanded=False):
            # Lógica corrigida do Grid:
            # Usamos st.columns dentro de um loop, e o CSS garante o alinhamento
            cols_per_row = 5
            rows = 12 
            
            for r in range(rows):
                cols = st.columns(cols_per_row)
                for c in range(cols_per_row):
                    num = (r * cols_per_row) + c + 1
                    if num <= 60:
                        with cols[c]:
                            is_sel = num in st.session_state.selected_numbers
                            # O estilo primary/secondary define a cor (vermelho/cinza)
                            st.button(f"{num:02d}", key=f"b_{num}", 
                                      type="primary" if is_sel else "secondary", 
                                      on_click=toggle_number, args=(num,))
            
            st.markdown("---")
            c_info, c_clear = st.columns([3, 1])
            c_info.markdown(f"**Selecionados:** {len(st.session_state.selected_numbers)}")
            c_clear.button("Limpar", on_click=clear_selection, use_container_width=True)
            
            start_date = st.date_input("Início da verificação:", date.today(), key="date_manual")
            if st.button("💾 SALVAR MANUAL", type="primary"):
                if len(st.session_state.selected_numbers) < 6: st.error("Mínimo 6 números.")
                else:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO tracked_games (numbers, start_date) VALUES (?, ?)", 
                                (json.dumps(sorted(st.session_state.selected_numbers)), start_date.strftime("%Y-%m-%d")))
                    conn.commit(); conn.close()
                    st.success("Salvo!"); clear_selection(); time.sleep(0.5); st.rerun()
        
        st.write("") 
        
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT * FROM tracked_games WHERE active=1 ORDER BY id DESC", conn)
        conn.close()
        
        if df.empty: st.info("Nenhum jogo ativo.")
        
        for _, row in df.iterrows():
            nums = json.loads(row['numbers'])
            matches = check_game_matches(nums, row['start_date'])
            game_id = row['id']
            edit_key = f"edit_mode_{game_id}"
            if edit_key not in st.session_state: st.session_state[edit_key] = False

            with st.container(border=True):
                if not st.session_state[edit_key]:
                    c1, c2, c3 = st.columns([5, 1, 1])
                    c1.markdown(f"**Jogo #{game_id}** • {len(nums)} dz")
                    if c2.button("✏️", key=f"ed_{game_id}"): st.session_state[edit_key] = True; st.rerun()
                    if c3.button("🗑️", key=f"del_{game_id}"): 
                        conn = get_db_connection(); conn.execute("UPDATE tracked_games SET active=0 WHERE id=?", (game_id,)); conn.commit(); conn.close(); st.rerun()
                    st.markdown(" ".join([f"`{n:02d}`" for n in nums]))
                    wins = [m for m in matches if m['acertos'] >= 4]
                    if wins: st.error(f"🏆 **{len(wins)} PRÊMIO(S)!**")
                    elif matches: st.info(f"🔎 {len(matches)} acerto(s).")
                    else: st.caption("Sem acertos.")
                    if matches:
                        with st.expander("Ver sorteios"):
                            for m in matches:
                                color = "orange" if m['acertos'] >= 4 else "gray"
                                icon = "🏆" if m['acertos'] >= 4 else "🎯"
                                st.markdown(f"**:{color}[{icon} {m['acertos']} Acertos]** em {m['data']}")
                                st.caption(f"Conc: {m['concurso']} | {m['dezenas_acertadas']}"); st.divider()
                else:
                    st.markdown(f"**📝 Editar Jogo #{game_id}**")
                    try: cur_date = datetime.strptime(row['start_date'], "%Y-%m-%d").date()
                    except: cur_date = date.today()
                    new_date = st.date_input("Nova Data:", value=cur_date, key=f"dt_{game_id}")
                    if st.button("Salvar", key=f"sv_{game_id}", type="primary"):
                        conn = get_db_connection(); conn.execute("UPDATE tracked_games SET start_date = ? WHERE id = ?", (new_date.strftime("%Y-%m-%d"), game_id)); conn.commit(); conn.close(); st.session_state[edit_key] = False; st.rerun()
                    if st.button("Cancelar", key=f"cn_{game_id}"): st.session_state[edit_key] = False; st.rerun()

    # --- ABA ESTATÍSTICAS ---
    with tab_stats:
        df_stats, df_lag, counter = get_statistics()
        if not df_stats is None:
            st.markdown("#### ⏰ Top Atrasos")
            top_lag = df_lag.nlargest(10, 'atraso')
            st.dataframe(top_lag.T, use_container_width=True)
            st.divider()
            st.markdown("#### 🔥 Frequência")
            st.bar_chart(df_stats, color="#ff4b4b", height=200)
            with st.expander("Ver Tabela Completa"): st.dataframe(df_stats.T, use_container_width=True)
        else: st.warning("Sem dados.")

    # --- ABA GERADOR ---
    with tab_gen:
        c_qtd, c_strat = st.columns([1, 2])
        with c_qtd: qtd_dezenas = st.number_input("Qtd", 6, 20, 6)
        with c_strat: strategy = st.selectbox("Estratégia", ["Aleatória", "Inteligente (Quentes)", "Ousada (Frias)", "Equilibrada (Mista)"])
        strat_map = {"Aleatória": "random", "Inteligente (Quentes)": "smart", "Ousada (Frias)": "cold", "Equilibrada (Mista)": "balanced"}
        if st.button("🎲 GERAR JOGO", type="primary"):
            _, _, counter_stats = get_statistics()
            cur_strat = strat_map[strategy]
            if cur_strat != "random" and not counter_stats: cur_strat = "random"
            st.session_state['last_generated'] = generate_game(qtd_dezenas, cur_strat, counter_stats)
        if 'last_generated' in st.session_state:
            gen_nums = st.session_state['last_generated']
            st.divider()
            st.markdown(" ".join([f"<span style='background:#e0e2e6;padding:5px;border-radius:4px;font-weight:bold;color:black'>{n:02d}</span>" for n in gen_nums]), unsafe_allow_html=True)
            if st.button("💾 Salvar Gerado"):
                conn = get_db_connection()
                conn.execute("INSERT INTO tracked_games (numbers, start_date) VALUES (?, ?)", 
                            (json.dumps(gen_nums), date.today().strftime("%Y-%m-%d")))
                conn.commit(); conn.close()
                st.toast("Salvo!", icon="✅"); del st.session_state['last_generated']; time.sleep(0.5); st.rerun()

    # --- ABA CONFIG ---
    with tab_config:
        st.header("💾 Backup")
        st.info("Salve seus jogos antes de limpar o celular.")
        conn = get_db_connection()
        df_export = pd.read_sql_query("SELECT numbers, start_date, active, created_at FROM tracked_games", conn)
        conn.close()
        if not df_export.empty:
            csv = df_export.to_csv(index=False).encode('utf-8')
            st.download_button(label="⬇️ Baixar CSV", data=csv, file_name=f"backup_mega_{date.today()}.csv", mime='text/csv', type='primary')
        else: st.warning("Sem dados para backup.")
        st.divider()
        st.write("Restaurar:")
        uploaded_file = st.file_uploader("Arquivo CSV", type=['csv'])
        if uploaded_file is not None:
            if st.button("🔄 Restaurar Dados"):
                try:
                    df_import = pd.read_csv(uploaded_file)
                    if not {'numbers', 'start_date'}.issubset(df_import.columns): st.error("CSV inválido.")
                    else:
                        conn = get_db_connection()
                        count = 0
                        for _, row in df_import.iterrows():
                            active = row['active'] if 'active' in row else 1
                            created = row['created_at'] if 'created_at' in row else datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                            check = conn.execute("SELECT id FROM tracked_games WHERE numbers = ? AND start_date = ?", (row['numbers'], row['start_date'])).fetchone()
                            if not check:
                                conn.execute("INSERT INTO tracked_games (numbers, start_date, active, created_at) VALUES (?, ?, ?, ?)", 
                                           (row['numbers'], row['start_date'], active, created))
                                count += 1
                        conn.commit(); conn.close(); st.success(f"Restaurado: {count} jogos."); time.sleep(1); st.rerun()
                except Exception as e: st.error(f"Erro: {e}")

if __name__ == "__main__":
    main()