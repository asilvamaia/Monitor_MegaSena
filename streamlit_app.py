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

# --- GERENCIAMENTO DE TEMA ---
if 'theme' not in st.session_state:
    st.session_state.theme = 'dark'

def toggle_theme():
    st.session_state.theme = 'light' if st.session_state.theme == 'dark' else 'dark'

# Cores do Tema
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

# --- CSS OTIMIZADO ---
st.markdown(f"""
<style>
    /* Tema Global */
    .stApp {{
        background-color: {bg_color};
        color: {text_color};
    }}
    
    .block-container {{
        padding-top: 1.5rem; /* Topo mais compacto */
        padding-left: 0.2rem;
        padding-right: 0.2rem;
        padding-bottom: 6rem;
    }}
    
    /* === GRID DE NÚMEROS === */
    /* Força colunas lado a lado no mobile */
    [data-testid="stHorizontalBlock"] {{
        flex-wrap: nowrap !important;
    }}
    div[data-testid="column"] {{
        flex: 1 !important;
        min-width: 0 !important;
        padding: 0 1px !important;
    }}
    /* Botões numéricos */
    div[data-testid="column"] button {{
        width: 100% !important;
        min-height: 42px !important;
        padding: 0px !important;
        margin: 2px 0px !important;
        border-radius: 6px !important;
        font-weight: bold;
    }}
    
    /* === BOTÕES DE CABEÇALHO (Atualizar/Tema) === */
    /* Classe CSS específica que vamos injetar nos botões do topo */
    div[data-testid="column"] .header-btn {{
        width: 100% !important;
        height: 40px !important;
        border-radius: 8px !important;
        padding: 0 !important;
        background-color: {btn_sec_bg} !important;
        color: {text_color} !important;
        border: 1px solid {border_color} !important;
        display: flex;
        align-items: center;
        justify-content: center;
    }}
    
    /* === BOTÕES PRINCIPAIS (Salvar/Gerar) === */
    .stButton button[kind="primary"] {{
        width: 100%;
        border-radius: 12px;
        height: 52px;
        font-size: 18px;
        background-color: #ff4b4b !important;
        color: white !important;
        border: none;
        margin-top: 10px;
    }}
    
    /* === ELEMENTOS VISUAIS === */
    div[data-testid="stExpander"], div[data-testid="stContainer"] {{
        background-color: {card_bg};
        border-radius: 10px;
        border: 1px solid {border_color};
        color: {text_color};
    }}
    
    /* Abas */
    .stTabs [data-baseweb="tab-list"] {{ gap: 4px; background: transparent; }}
    .stTabs [data-baseweb="tab"] {{
        height: 45px;
        background-color: {card_bg};
        border-radius: 8px;
        color: {text_color};
        flex: 1;
        padding: 4px;
        font-size: 13px;
    }}
    .stTabs [aria-selected="true"] {{
        background-color: {bg_color};
        border: 1px solid {border_color};
        border-bottom: 3px solid #ff4b4b;
    }}
    
    header[data-testid="stHeader"] {{ display: none; }}
    h3, p, span, div {{ color: {text_color}; }}
</style>
""", unsafe_allow_html=True)

# --- CONFIGURAÇÃO DO ÍCONE IOS (GITHUB RAW) ---
def setup_ios_icon():
    # Usando o Emoji Oficial do Twitter (Clover) hospedado no GitHub
    # É um arquivo estático super confiável.
    icon_url = "https://raw.githubusercontent.com/twitter/twemoji/master/assets/72x72/1f340.png"
    
    st.markdown(f"""
        <link rel="apple-touch-icon" href="{icon_url}">
        <meta name="apple-mobile-web-app-capable" content="yes">
        <meta name="apple-mobile-web-app-title" content="MegaSena">
        <meta name="apple-mobile-web-app-status-bar-style" content="black-translucent">
    """, unsafe_allow_html=True)

# --- BANCO DE DADOS ---
DB_FILE = "megasena.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS app_config (key TEXT PRIMARY KEY, value TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_games (id INTEGER PRIMARY KEY AUTOINCREMENT, numbers TEXT, start_date TEXT, active INTEGER DEFAULT 1, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS results (concurso INTEGER PRIMARY KEY, data_sorteio TEXT, dezenas TEXT)''')
    conn.commit(); conn.close()

def get_db_connection(): return sqlite3.connect(DB_FILE)

# --- LÓGICA ---
def fetch_latest_results():
    try:
        response = requests.get("https://loteriascaixa-api.herokuapp.com/api/megasena", timeout=10)
        if response.status_code == 200:
            data = response.json()
            draws = data if isinstance(data, list) else [data]
            conn = get_db_connection(); c = conn.cursor(); count = 0
            for draw in draws:
                try:
                    iso = datetime.strptime(draw.get('data'), "%d/%m/%Y").strftime("%Y-%m-%d")
                    c.execute('INSERT OR IGNORE INTO results (concurso, data_sorteio, dezenas) VALUES (?, ?, ?)', 
                             (draw.get('concurso'), iso, json.dumps([int(d) for d in draw.get('dezenas', [])])))
                    if c.rowcount > 0: count += 1
                except: continue
            conn.commit(); conn.close(); return count
    except: return 0
    return 0

def get_statistics():
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT concurso, dezenas FROM results ORDER BY concurso DESC", conn)
    conn.close()
    if df.empty: return None, None, None
    all_nums = [n for d in df['dezenas'] for n in json.loads(d)]
    counter = Counter(all_nums)
    for i in range(1, 61): counter.setdefault(i, 0)
    
    last_seen = {}
    latest = df.iloc[0]['concurso']
    for _, row in df.iterrows():
        for n in json.loads(row['dezenas']):
            if n not in last_seen: last_seen[n] = row['concurso']
        if len(last_seen) == 60: break
    
    lag = {i: latest - last_seen.get(i, latest) for i in range(1, 61)}
    return pd.DataFrame.from_dict(counter, orient='index', columns=['freq']), pd.DataFrame.from_dict(lag, orient='index', columns=['atraso']), counter

def generate_game(qtd, strategy, counter):
    nums = list(range(1, 61))
    if strategy == "random" or not counter: return sorted(random.sample(nums, qtd))
    
    weights_smart = [counter.get(n, 0)+1 for n in nums]
    weights_cold = [1/(counter.get(n, 0)+1) for n in nums]
    
    if strategy == "smart":
        sel = set(); 
        while len(sel)<qtd: sel.add(random.choices(nums, weights_smart)[0])
        return sorted(list(sel))
    elif strategy == "cold":
        sel = set(); 
        while len(sel)<qtd: sel.add(random.choices(nums, weights_cold)[0])
        return sorted(list(sel))
    elif strategy == "balanced":
        # Mista: Pega metade dos Top 30 quentes e metade dos Top 30 frios (inversos)
        sorted_nums = sorted(nums, key=lambda x: counter.get(x,0), reverse=True)
        hot_pool = sorted_nums[:30]
        cold_pool = sorted_nums[30:]
        
        sel = set()
        while len(sel) < (qtd // 2) + (qtd % 2): sel.add(random.choice(hot_pool))
        while len(sel) < qtd: 
            p = random.choice(cold_pool)
            if p not in sel: sel.add(p)
        return sorted(list(sel))
    return sorted(random.sample(nums, qtd))

def check_matches(game_nums, start_date):
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM results WHERE data_sorteio >= ? ORDER BY data_sorteio DESC", conn, params=(start_date,))
    conn.close()
    matches = []
    g_set = set(game_numbers=game_nums)
    for _, row in df.iterrows():
        d_set = set(json.loads(row['dezenas']))
        hits = g_set.intersection(d_set)
        if hits: matches.append({'concurso': row['concurso'], 'data': row['data_sorteio'], 'acertos': len(hits), 'sorteadas': sorted(list(d_set)), 'meus_acertos': sorted(list(hits))})
    return matches

def toggle_num(n):
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []
    if n in st.session_state.selected_numbers: st.session_state.selected_numbers.remove(n)
    elif len(st.session_state.selected_numbers) < 20: st.session_state.selected_numbers.append(n)

# ================= MAIN =================
def main():
    setup_ios_icon()
    init_db()
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []

    # --- CABEÇALHO OTIMIZADO (BOTÕES JUNTOS) ---
    # Usando colunas aninhadas para juntar os botões
    c_header_actions, c_header_title = st.columns([2.5, 6]) # 25% para botões, 75% para título
    
    with c_header_actions:
        # Coloca os dois botões lado a lado com gap pequeno
        b1, b2 = st.columns([1, 1], gap="small")
        with b1:
            if st.button("🔄", help="Atualizar"):
                with st.spinner("..."):
                    c = fetch_latest_results()
                    conn = get_db_connection()
                    conn.execute("INSERT OR REPLACE INTO app_config (key, value) VALUES ('last_update', ?)", (datetime.now().strftime("%Y-%m-%d"),))
                    conn.commit(); conn.close()
                st.toast(f"{c} novos!" if c > 0 else "OK!", icon="✅"); time.sleep(0.5); st.rerun()
        with b2:
            theme_icon = "🌞" if st.session_state.theme == 'dark' else "🌙"
            if st.button(theme_icon, on_click=toggle_theme): st.rerun()

    with c_header_title:
        st.subheader("Mega Mobile")

    # --- MENU DE ABAS ---
    tabs = st.tabs(["📋 Jogos", "📊 Stats", "🎲 Gerar", "⚙️ Config"])

    # ABA 1: JOGOS
    with tabs[0]:
        with st.expander("➕ Novo Jogo", expanded=False):
            # GRID 5 COLUNAS (CSS garante alinhamento)
            for r in range(12):
                cols = st.columns(5)
                for c in range(5):
                    n = (r * 5) + c + 1
                    with cols[c]:
                        type_Btn = "primary" if n in st.session_state.selected_numbers else "secondary"
                        st.button(f"{n:02d}", key=f"n{n}", type=type_Btn, on_click=toggle_num, args=(n,))
            
            st.markdown("---")
            c_inf, c_clr = st.columns([3, 1])
            c_inf.write(f"**Selecionados: {len(st.session_state.selected_numbers)}**")
            c_clr.button("Limpar", on_click=lambda: st.session_state.update(selected_numbers=[]))
            
            dt = st.date_input("Início:", date.today())
            if st.button("💾 SALVAR", type="primary"):
                if len(st.session_state.selected_numbers) < 6: st.error("Mínimo 6!")
                else:
                    conn = get_db_connection()
                    conn.execute("INSERT INTO tracked_games (numbers, start_date) VALUES (?, ?)", (json.dumps(sorted(st.session_state.selected_numbers)), dt.strftime("%Y-%m-%d")))
                    conn.commit(); conn.close()
                    st.session_state.selected_numbers = []; st.toast("Salvo!"); time.sleep(0.5); st.rerun()
        
        st.write("")
        conn = get_db_connection()
        games = pd.read_sql_query("SELECT * FROM tracked_games WHERE active=1 ORDER BY id DESC", conn)
        conn.close()
        
        if games.empty: st.info("Sem jogos ativos.")
        
        for _, row in games.iterrows():
            game_nums = json.loads(row['numbers'])
            matches = check_matches(game_nums, row['start_date'])
            gid = row['id']
            key_ed = f"ed_mode_{gid}"
            if key_ed not in st.session_state: st.session_state[key_ed] = False
            
            with st.container(border=True):
                if not st.session_state[key_ed]:
                    ca, cb, cc = st.columns([5, 1, 1])
                    ca.markdown(f"**#{gid}** ({len(game_nums)} dz)")
                    if cb.button("✏️", key=f"e{gid}"): st.session_state[key_ed]=True; st.rerun()
                    if cc.button("🗑️", key=f"d{gid}"): 
                        conn=get_db_connection(); conn.execute("UPDATE tracked_games SET active=0 WHERE id=?",(gid,)); conn.commit(); conn.close(); st.rerun()
                    
                    st.markdown(" ".join([f"`{x:02d}`" for x in game_nums]))
                    
                    wins = [m for m in matches if m['acertos']>=4]
                    if wins: st.error(f"🏆 **{len(wins)} PRÊMIO(S)!**")
                    elif matches: st.info(f"🔎 {len(matches)} acerto(s).")
                    else: st.caption("Sem acertos.")
                    
                    if matches:
                        with st.expander("Detalhes"):
                            for m in matches:
                                icon = "🏆" if m['acertos']>=4 else "🎯"
                                st.write(f"{icon} **{m['acertos']} acertos** em {m['data']}")
                                st.caption(f"Sorteadas: {m['sorteadas']}")
                                st.divider()
                else:
                    st.markdown(f"**Editar #{gid}**")
                    try: d_val = datetime.strptime(row['start_date'], "%Y-%m-%d").date()
                    except: d_val = date.today()
                    new_d = st.date_input("Nova Data:", d_val, key=f"dd{gid}")
                    c1, c2 = st.columns(2)
                    if c1.button("Salvar", key=f"sv{gid}"):
                        conn=get_db_connection(); conn.execute("UPDATE tracked_games SET start_date=? WHERE id=?",(new_d.strftime("%Y-%m-%d"), gid)); conn.commit(); conn.close(); st.session_state[key_ed]=False; st.rerun()
                    if c2.button("Cancelar", key=f"cn{gid}"): st.session_state[key_ed]=False; st.rerun()

    # ABA 2: STATS
    with tabs[1]:
        freq, lag, ctr = get_statistics()
        if freq is not None:
            st.markdown("##### ⏰ Top Atrasos")
            st.dataframe(lag.nlargest(10, 'atraso').T, use_container_width=True)
            st.divider()
            st.markdown("##### 🔥 Frequência")
            st.bar_chart(freq, color="#ff4b4b", height=200)
        else: st.warning("Atualize a base.")

    # ABA 3: GERADOR
    with tabs[2]:
        c1, c2 = st.columns([1, 2])
        qtd = c1.number_input("Qtd", 6, 20, 6)
        strat = c2.selectbox("Estratégia", ["Aleatória", "Smart (Quentes)", "Cold (Frias)", "Balanced (Mista)"])
        strat_key = {"Aleatória":"random", "Smart (Quentes)":"smart", "Cold (Frias)":"cold", "Balanced (Mista)":"balanced"}
        
        if st.button("🎲 GERAR", type="primary"):
            _, _, ctr = get_statistics()
            st.session_state.last_gen = generate_game(qtd, strat_key[strat], ctr)
            
        if 'last_gen' in st.session_state:
            g = st.session_state.last_gen
            st.markdown(" ".join([f"`{x:02d}`" for x in g]))
            if st.button("💾 Salvar"):
                conn=get_db_connection(); conn.execute("INSERT INTO tracked_games (numbers, start_date) VALUES (?, ?)", (json.dumps(g), date.today().strftime("%Y-%m-%d"))); conn.commit(); conn.close(); st.toast("Salvo!"); del st.session_state.last_gen; time.sleep(0.5); st.rerun()

    # ABA 4: CONFIG
    with tabs[3]:
        st.info("Backup dos dados")
        conn = get_db_connection()
        df = pd.read_sql_query("SELECT numbers, start_date, active, created_at FROM tracked_games", conn); conn.close()
        if not df.empty:
            st.download_button("⬇️ Baixar CSV", df.to_csv(index=False).encode('utf-8'), f"backup_{date.today()}.csv", "text/csv")
        
        up = st.file_uploader("Restaurar CSV", type=['csv'])
        if up and st.button("🔄 Restaurar"):
            try:
                dfi = pd.read_csv(up)
                conn = get_db_connection()
                for _, r in dfi.iterrows():
                    conn.execute("INSERT INTO tracked_games (numbers, start_date, active, created_at) VALUES (?,?,?,?)", (r['numbers'], r['start_date'], r.get('active',1), r.get('created_at','')))
                conn.commit(); conn.close(); st.success("Feito!"); time.sleep(1); st.rerun()
            except: st.error("Erro no CSV")

if __name__ == "__main__":
    main()