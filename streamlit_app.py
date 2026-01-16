import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
from datetime import datetime
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Mega Mobile", layout="centered", page_icon="🎱")

# --- CSS MOBILE-FIRST ---
st.markdown("""
<style>
    /* Remove preenchimento excessivo no topo e lados para ganhar tela no celular */
    .block-container {
        padding-top: 1rem;
        padding-left: 0.5rem;
        padding-right: 0.5rem;
        padding-bottom: 5rem; /* Espaço para scroll final */
    }
    
    /* Botões do Grid de Números: Mais altos e fáceis de tocar */
    div[data-testid="stHorizontalBlock"] button {
        min-height: 45px !important;
        border-radius: 8px !important;
        margin-bottom: 4px !important;
    }
    
    /* Ajuste de gaps entre colunas */
    div[data-testid="column"] {
        padding: 0 2px !important;
    }
    
    /* Botão de Ação Principal (Salvar) */
    .stButton button[kind="primary"] {
        width: 100%;
        border-radius: 12px;
        height: 50px;
        font-size: 18px;
    }
</style>
""", unsafe_allow_html=True)

# --- BANCO DE DADOS ---
DB_FILE = "megasena.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS tracked_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT, numbers TEXT, start_date TEXT, active INTEGER DEFAULT 1, created_at TEXT)''')
    c.execute('''CREATE TABLE IF NOT EXISTS results (
            concurso INTEGER PRIMARY KEY, data_sorteio TEXT, dezenas TEXT)''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# --- LÓGICA ---
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
                except: continue
                
                try:
                    cursor.execute('INSERT OR IGNORE INTO results (concurso, data_sorteio, dezenas) VALUES (?, ?, ?)', 
                                 (concurso, data_iso, dezenas))
                    if cursor.rowcount > 0: count += 1
                except: pass
            conn.commit()
            conn.close()
            return count
    except: return 0
    return 0

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

# --- STATE ---
def toggle_number(num):
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []
    if num in st.session_state.selected_numbers:
        st.session_state.selected_numbers.remove(num)
    elif len(st.session_state.selected_numbers) < 20:
        st.session_state.selected_numbers.append(num)

def clear_selection(): st.session_state.selected_numbers = []

# --- APP ---
def main():
    init_db()
    if 'selected_numbers' not in st.session_state: st.session_state.selected_numbers = []

    # Cabeçalho Compacto
    c_title, c_refresh = st.columns([5, 1])
    with c_title:
        st.subheader("🎱 Mega Mobile")
    with c_refresh:
        if st.button("🔄"):
            with st.spinner("."): fetch_latest_results()
            st.rerun()

    # --- ÁREA DE CRIAÇÃO (EXPANDER) ---
    # Usamos expander para não ocupar espaço quando não estiver usando
    with st.expander("➕ Novo Jogo (Clique para abrir)", expanded=False):
        
        # Grid Otimizado para Celular (5 colunas x 12 linhas)
        # 5 colunas garante botões grandes o suficiente para o polegar
        cols_per_row = 5
        rows = 12 
        
        for r in range(rows):
            cols = st.columns(cols_per_row)
            for c in range(cols_per_row):
                num = (r * cols_per_row) + c + 1
                if num <= 60:
                    with cols[c]:
                        is_sel = num in st.session_state.selected_numbers
                        st.button(f"{num:02d}", key=f"b_{num}", 
                                  type="primary" if is_sel else "secondary", 
                                  on_click=toggle_number, args=(num,))
        
        # Área de confirmação Sticky-like
        st.markdown("---")
        col_info, col_clear = st.columns([3, 1])
        col_info.markdown(f"**Selecionados:** {len(st.session_state.selected_numbers)}")
        col_clear.button("Limpar", on_click=clear_selection, use_container_width=True)
        
        start_date = st.date_input("Início da verificação:", datetime.now())
        
        if st.button("💾 SALVAR JOGO", type="primary"):
            if len(st.session_state.selected_numbers) < 6:
                st.error("Mínimo 6 números.")
            else:
                conn = get_db_connection()
                conn.execute("INSERT INTO tracked_games (numbers, start_date) VALUES (?, ?)",
                            (json.dumps(sorted(st.session_state.selected_numbers)), start_date.strftime("%Y-%m-%d")))
                conn.commit()
                conn.close()
                st.success("Salvo!")
                clear_selection()
                time.sleep(0.5)
                st.rerun()

    # --- LISTA DE JOGOS (Cards Verticais) ---
    st.write("") # Espaço
    
    conn = get_db_connection()
    df = pd.read_sql_query("SELECT * FROM tracked_games WHERE active=1 ORDER BY id DESC", conn)
    conn.close()

    if df.empty:
        st.info("Nenhum jogo ativo. Abra o menu acima para criar.")
    
    for _, row in df.iterrows():
        nums = json.loads(row['numbers'])
        matches = check_game_matches(nums, row['start_date'])
        
        # Card Visual
        with st.container(border=True):
            # Cabeçalho do Card
            c1, c2 = st.columns([5, 1])
            c1.markdown(f"**Jogo #{row['id']}** • {len(nums)} dezenas")
            if c2.button("🗑️", key=f"del_{row['id']}"): # Botão de parar minimalista
                conn = get_db_connection()
                conn.execute("UPDATE tracked_games SET active=0 WHERE id=?", (row['id'],))
                conn.commit()
                conn.close()
                st.rerun()

            # Números formatados como tags
            st.markdown(" ".join([f"`{n:02d}`" for n in nums]))
            
            # Alerta de Prêmios
            wins = [m for m in matches if m['acertos'] >= 4]
            if wins:
                st.error(f"🏆 **{len(wins)} PRÊMIO(S)!**")
            elif matches:
                st.info(f"🔎 {len(matches)} sorteio(s) com acertos.")
            else:
                st.caption("Sem acertos no período.")

            # Expander para detalhes (Economiza scroll vertical)
            if matches:
                with st.expander("Ver sorteios"):
                    for m in matches:
                        cor = "orange" if m['acertos'] >= 4 else "gray"
                        icon = "🏆" if m['acertos'] >= 4 else "🎯"
                        st.markdown(f"**:{cor}[{icon} {m['acertos']} Acertos]** em {m['data']}")
                        st.caption(f"Conc: {m['concurso']} | {m['dezenas_acertadas']}")
                        st.divider()

if __name__ == "__main__":
    main()