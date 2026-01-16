import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
from datetime import datetime
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Monitor Mega-Sena", layout="wide")

# --- CSS CUSTOMIZADO PARA MELHORAR O GRID ---
st.markdown("""
<style>
    div[data-testid="stHorizontalBlock"] {
        gap: 0.2rem !important;
    }
    div[data-testid="column"] {
        min-width: 0px !important;
        padding: 0px !important;
    }
    button[kind="secondary"] {
        padding-left: 5px !important;
        padding-right: 5px !important;
        font-weight: bold;
    }
    button[kind="primary"] {
        padding-left: 5px !important;
        padding-right: 5px !important;
        font-weight: bold;
    }
</style>
""", unsafe_allow_html=True)

# --- BANCO DE DADOS (SQLite) ---
DB_FILE = "megasena.db"

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS tracked_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numbers TEXT NOT NULL,
            start_date TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    c.execute('''
        CREATE TABLE IF NOT EXISTS results (
            concurso INTEGER PRIMARY KEY,
            data_sorteio TEXT,
            dezenas TEXT
        )
    ''')
    conn.commit()
    conn.close()

def get_db_connection():
    return sqlite3.connect(DB_FILE)

# --- FUNÇÕES DE LÓGICA ---

def fetch_latest_results():
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
    try:
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            draws = data if isinstance(data, list) else [data]
                
            conn = get_db_connection()
            cursor = conn.cursor()
            new_records = 0
            for draw in draws:
                concurso = draw.get('concurso')
                data_sorteio = draw.get('data')
                dezenas = json.dumps([int(d) for d in draw.get('dezenas', [])])
                try:
                    dt_obj = datetime.strptime(data_sorteio, "%d/%m/%Y")
                    data_iso = dt_obj.strftime("%Y-%m-%d")
                except:
                    data_iso = datetime.now().strftime("%Y-%m-%d")

                try:
                    cursor.execute('INSERT OR IGNORE INTO results (concurso, data_sorteio, dezenas) VALUES (?, ?, ?)', 
                                 (concurso, data_iso, dezenas))
                    if cursor.rowcount > 0:
                        new_records += 1
                except Exception:
                    pass
            conn.commit()
            conn.close()
            return new_records
    except Exception as e:
        st.error(f"Erro na API: {e}")
        return 0
    return 0

def check_game_matches(game_numbers, start_date_iso):
    conn = get_db_connection()
    # Pega resultados a partir da data informada
    df = pd.read_sql_query(
        "SELECT concurso, data_sorteio, dezenas FROM results WHERE data_sorteio >= ? ORDER BY data_sorteio DESC",
        conn, params=(start_date_iso,)
    )
    conn.close()
    
    game_set = set(game_numbers)
    matches_found = []
    
    for index, row in df.iterrows():
        draw_numbers = set(json.loads(row['dezenas']))
        hits = game_set.intersection(draw_numbers)
        num_hits = len(hits)
        
        # ALTERAÇÃO AQUI: Agora exibe se tiver pelo menos 1 acerto
        if num_hits > 0:
            matches_found.append({
                'concurso': row['concurso'],
                'data': row['data_sorteio'],
                'acertos': num_hits,
                'dezenas_sorteadas': sorted(list(draw_numbers)),
                'dezenas_acertadas': sorted(list(hits))
            })
    return matches_found

# --- GERENCIAMENTO DE ESTADO PARA SELEÇÃO DE NÚMEROS ---
def toggle_number(num):
    if 'selected_numbers' not in st.session_state:
        st.session_state.selected_numbers = []
    
    if num in st.session_state.selected_numbers:
        st.session_state.selected_numbers.remove(num)
    else:
        if len(st.session_state.selected_numbers) < 20:
            st.session_state.selected_numbers.append(num)
        else:
            st.toast("Limite máximo de 20 números atingido!", icon="⚠️")

def clear_selection():
    st.session_state.selected_numbers = []

# --- INTERFACE PRINCIPAL ---

def main():
    init_db()
    
    if 'selected_numbers' not in st.session_state:
        st.session_state.selected_numbers = []
    
    st.title("🎱 Monitor Mega-Sena")
    
    # --- SIDEBAR (Cadastro com Grid) ---
    with st.sidebar:
        st.header("Novo Jogo")
        st.write("Clique para selecionar (Min: 6):")
        
        grid_container = st.container(border=True)
        with grid_container:
            for row in range(6):
                cols = st.columns(10)
                for col_idx in range(10):
                    num = (row * 10) + col_idx + 1
                    with cols[col_idx]:
                        is_selected = num in st.session_state.selected_numbers
                        btn_type = "primary" if is_selected else "secondary"
                        st.button(
                            f"{num:02d}", 
                            key=f"btn_{num}", 
                            type=btn_type, 
                            on_click=toggle_number, 
                            args=(num,)
                        )

        qtd_selecionada = len(st.session_state.selected_numbers)
        st.markdown(f"**Selecionados:** {qtd_selecionada} / 20")
        st.text(f"{sorted(st.session_state.selected_numbers)}")
        
        c_clear, c_dummy = st.columns([1, 2])
        if c_clear.button("Limpar", on_click=clear_selection):
            pass

        st.divider()

        start_date = st.date_input("Verificar a partir de:", datetime.now())
        
        if st.button("💾 Cadastrar Jogo", type="primary", use_container_width=True):
            if qtd_selecionada < 6:
                st.error("Selecione pelo menos 6 números.")
            else:
                nums_sorted = sorted(st.session_state.selected_numbers)
                nums_json = json.dumps(nums_sorted)
                start_date_iso = start_date.strftime("%Y-%m-%d")
                
                conn = get_db_connection()
                conn.execute("INSERT INTO tracked_games (numbers, start_date, created_at) VALUES (?, ?, ?)",
                                (nums_json, start_date_iso, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                conn.commit()
                conn.close()
                
                st.success("Cadastrado!")
                clear_selection()
                time.sleep(1)
                st.rerun()

        st.divider()
        if st.button("🔄 Atualizar Base de Dados"):
            with st.spinner("Atualizando..."):
                count = fetch_latest_results()
            if count > 0:
                st.success(f"{count} novos!")
            else:
                st.info("Base atualizada.")

    # --- ÁREA PRINCIPAL (Visualização) ---
    
    tab1, tab2 = st.tabs(["Jogos Ativos", "Jogos Parados"])
    
    conn = get_db_connection()
    df_games = pd.read_sql_query("SELECT * FROM tracked_games ORDER BY id DESC", conn)
    conn.close()
    
    if not df_games.empty:
        df_games['numbers_list'] = df_games['numbers'].apply(json.loads)
        
        active_games = df_games[df_games['active'] == 1]
        stopped_games = df_games[df_games['active'] == 0]
        
        with tab1:
            if active_games.empty:
                st.info("Nenhum jogo ativo.")
            else:
                for idx, row in active_games.iterrows():
                    game_id = row['id']
                    numbers = row['numbers_list']
                    start_date = row['start_date']
                    
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 5, 1])
                        with c1:
                            st.caption(f"ID: {game_id} | Início: {start_date}")
                            st.markdown(f"**{len(numbers)} Dezenas**")
                            st.markdown(" ".join([f"`{n:02d}`" for n in numbers]))
                        
                        with c2:
                            matches = check_game_matches(numbers, start_date)
                            if matches:
                                # Verifica se houve ALGUM prêmio real
                                wins = [m for m in matches if m['acertos'] >= 4]
                                
                                if wins:
                                    st.error(f"🏆 PARABÉNS! {len(wins)} prêmio(s) encontrado(s)!")
                                else:
                                    st.info(f"🔎 {len(matches)} sorteio(s) com acertos (sem prêmio).")

                                with st.expander("Ver Detalhes dos Sorteios"):
                                    for m in matches:
                                        acertos = m['acertos']
                                        
                                        # Lógica de exibição do prêmio
                                        if acertos == 6:
                                            texto_premio = "🏆 SENA (Vencedor)"
                                            cor = ":red"
                                        elif acertos == 5:
                                            texto_premio = "🥈 QUINA"
                                            cor = ":orange"
                                        elif acertos == 4:
                                            texto_premio = "🥉 QUADRA"
                                            cor = ":orange"
                                        else:
                                            texto_premio = "🎯 Não Premiado"
                                            cor = ":grey"

                                        st.markdown(f"**Concurso {m['concurso']} ({m['data']})**")
                                        st.markdown(f"{cor}[{texto_premio}] - Você acertou **{acertos}** números.")
                                        st.caption(f"Seus acertos: {m['dezenas_acertadas']}")
                                        st.divider()
                            else:
                                st.write("Nenhum acerto registrado neste período.")
                        
                        with c3:
                            st.write("")
                            if st.button("Arquivar", key=f"stop_{game_id}"):
                                conn = get_db_connection()
                                conn.execute("UPDATE tracked_games SET active = 0 WHERE id = ?", (game_id,))
                                conn.commit()
                                conn.close()
                                st.rerun()

        with tab2:
            if stopped_games.empty:
                st.write("Nenhum jogo arquivado.")
            else:
                for idx, row in stopped_games.iterrows():
                    game_id = row['id']
                    with st.container(border=True):
                        c1, c2 = st.columns([6, 1])
                        with c1:
                            st.caption(f"ID: {game_id} (Arquivado)")
                            st.text(f"{row['numbers_list']}")
                        with c2:
                            if st.button("Reativar", key=f"react_{game_id}"):
                                conn = get_db_connection()
                                conn.execute("UPDATE tracked_games SET active = 1 WHERE id = ?", (game_id,))
                                conn.commit()
                                conn.close()
                                st.rerun()
    else:
        st.info("Utilize o painel lateral para cadastrar seus jogos.")

if __name__ == "__main__":
    main()