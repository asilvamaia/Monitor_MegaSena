import streamlit as st
import pandas as pd
import requests
import sqlite3
import json
from datetime import datetime
import time

# --- CONFIGURAÇÃO DA PÁGINA ---
st.set_page_config(page_title="Monitor Mega-Sena", layout="wide")

# --- BANCO DE DADOS (SQLite) ---
DB_FILE = "megasena.db"

def init_db():
    """Inicializa o banco de dados e cria as tabelas se não existirem."""
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    
    # Tabela de Jogos Monitorados
    c.execute('''
        CREATE TABLE IF NOT EXISTS tracked_games (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numbers TEXT NOT NULL,
            start_date TEXT NOT NULL,
            active INTEGER DEFAULT 1,
            created_at TEXT
        )
    ''')
    
    # Tabela de Resultados da Mega-Sena (Cache)
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

# --- FUNÇÕES DE LÓGICA DE NEGÓCIO ---

def fetch_latest_results():
    """
    Busca resultados atualizados de uma API pública.
    Nota: APIs públicas podem mudar. Aqui usamos uma comum para loterias.
    """
    url = "https://loteriascaixa-api.herokuapp.com/api/megasena"
    
    try:
        # Busca todos os resultados (ou poderia ser paginado dependendo da API)
        # Para evitar sobrecarga, em produção idealmente busca-se apenas o último e itera para trás
        # Mas esta API retorna o último concurso por padrão ou lista.
        # Vamos usar uma abordagem robusta: Tentar pegar a lista completa ou iterar.
        # Para este exemplo, vamos assumir que queremos apenas atualizar o banco local.
        
        response = requests.get(url, timeout=10)
        if response.status_code == 200:
            data = response.json()
            
            # A estrutura da resposta depende da API. 
            # Se for uma lista:
            if isinstance(data, list):
                draws = data
            else:
                # Se for um único objeto (o último), transformamos em lista
                draws = [data]
                
            conn = get_db_connection()
            cursor = conn.cursor()
            
            new_records = 0
            for draw in draws:
                concurso = draw.get('concurso')
                data_sorteio = draw.get('data') # Formato esperado DD/MM/AAAA
                dezenas = json.dumps([int(d) for d in draw.get('dezenas', [])])
                
                # Converter data para YYYY-MM-DD para facilitar comparação SQL
                try:
                    dt_obj = datetime.strptime(data_sorteio, "%d/%m/%Y")
                    data_iso = dt_obj.strftime("%Y-%m-%d")
                except:
                    data_iso = datetime.now().strftime("%Y-%m-%d")

                try:
                    cursor.execute('''
                        INSERT OR IGNORE INTO results (concurso, data_sorteio, dezenas)
                        VALUES (?, ?, ?)
                    ''', (concurso, data_iso, dezenas))
                    if cursor.rowcount > 0:
                        new_records += 1
                except Exception as e:
                    print(f"Erro ao inserir concurso {concurso}: {e}")
            
            conn.commit()
            conn.close()
            return new_records
    except Exception as e:
        st.error(f"Erro ao buscar dados na API: {e}")
        return 0
    return 0

def check_game_matches(game_numbers, start_date_iso):
    """
    Verifica acertos para um jogo específico a partir da data de início.
    Retorna uma lista de resultados onde houve premiação (Quadra, Quina, Sena).
    """
    conn = get_db_connection()
    # Busca resultados posteriores à data de início do monitoramento
    df = pd.read_sql_query(
        "SELECT concurso, data_sorteio, dezenas FROM results WHERE data_sorteio >= ? ORDER BY data_sorteio DESC",
        conn,
        params=(start_date_iso,)
    )
    conn.close()
    
    game_set = set(game_numbers)
    matches_found = []
    
    for index, row in df.iterrows():
        draw_numbers = set(json.loads(row['dezenas']))
        hits = game_set.intersection(draw_numbers)
        num_hits = len(hits)
        
        if num_hits >= 4: # Filtra apenas se ganhou algo (Quadra ou superior)
            matches_found.append({
                'concurso': row['concurso'],
                'data': row['data_sorteio'],
                'acertos': num_hits,
                'dezenas_sorteadas': sorted(list(draw_numbers)),
                'dezenas_acertadas': sorted(list(hits))
            })
            
    return matches_found

# --- INTERFACE DO USUÁRIO ---

def main():
    init_db()
    
    st.title("🎱 Monitor de Jogos da Mega-Sena")
    
    # Sidebar para adicionar novo jogo
    with st.sidebar:
        st.header("Novo Monitoramento")
        
        with st.form("new_game_form"):
            st.write("Escolha 6 números:")
            cols = st.columns(3)
            nums = []
            for i in range(6):
                # Inputs numéricos de 1 a 60
                val = cols[i % 3].number_input(f"Nº {i+1}", min_value=1, max_value=60, step=1, key=f"n{i}")
                nums.append(val)
            
            start_date = st.date_input("Verificar a partir de:", datetime.now())
            
            submitted = st.form_submit_button("Cadastrar Jogo")
            
            if submitted:
                # Validação simples
                if len(set(nums)) < 6:
                    st.error("Os números não podem ser repetidos.")
                else:
                    nums_sorted = sorted(list(set(nums)))
                    nums_json = json.dumps(nums_sorted)
                    start_date_iso = start_date.strftime("%Y-%m-%d")
                    
                    conn = get_db_connection()
                    conn.execute("INSERT INTO tracked_games (numbers, start_date, created_at) VALUES (?, ?, ?)",
                                 (nums_json, start_date_iso, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    conn.commit()
                    conn.close()
                    st.success("Jogo cadastrado com sucesso!")
                    time.sleep(1) # Pequena pausa para refresh visual
                    st.rerun()

        st.divider()
        if st.button("🔄 Forçar Atualização da Base de Dados"):
            with st.spinner("Buscando novos resultados na Caixa..."):
                count = fetch_latest_results()
            if count > 0:
                st.success(f"{count} novos sorteios baixados!")
            else:
                st.info("Base de dados já está atualizada ou API indisponível.")

    # Área Principal: Listagem dos Jogos
    
    # Abas para separar ativos de inativos
    tab1, tab2 = st.tabs(["Jogos Ativos", "Jogos Parados"])
    
    conn = get_db_connection()
    df_games = pd.read_sql_query("SELECT * FROM tracked_games", conn)
    conn.close()
    
    # Processamento para exibição
    if not df_games.empty:
        # Converter string JSON de volta para lista
        df_games['numbers_list'] = df_games['numbers'].apply(json.loads)
        
        # Separar ativos e inativos
        active_games = df_games[df_games['active'] == 1]
        stopped_games = df_games[df_games['active'] == 0]
        
        # --- TAB 1: ATIVOS ---
        with tab1:
            if active_games.empty:
                st.info("Nenhum jogo ativo no momento.")
            else:
                for idx, row in active_games.iterrows():
                    game_id = row['id']
                    numbers = row['numbers_list']
                    start_date = row['start_date']
                    
                    # Container para o cartão do jogo
                    with st.container(border=True):
                        c1, c2, c3 = st.columns([2, 4, 1])
                        
                        with c1:
                            st.caption(f"ID: {game_id} | Início: {start_date}")
                            st.markdown(f"### {str(numbers)}")
                            
                        with c2:
                            # Verificar resultados
                            matches = check_game_matches(numbers, start_date)
                            if matches:
                                st.warning(f"⚠️ {len(matches)} sorteio(s) premiado(s) encontrado(s)!")
                                with st.expander("Ver Detalhes dos Acertos"):
                                    for m in matches:
                                        st.markdown(f"**Concurso {m['concurso']} ({m['data']})**")
                                        st.write(f"Acertos: {m['acertos']} - {m['dezenas_acertadas']}")
                            else:
                                st.success("Nenhuma premiação encontrada até agora.")
                                
                        with c3:
                            st.write("") # Espaçamento
                            if st.button("Parar", key=f"stop_{game_id}", type="primary"):
                                conn = get_db_connection()
                                conn.execute("UPDATE tracked_games SET active = 0 WHERE id = ?", (game_id,))
                                conn.commit()
                                conn.close()
                                st.rerun()

        # --- TAB 2: PARADOS ---
        with tab2:
            if stopped_games.empty:
                st.write("Nenhum jogo arquivado.")
            else:
                for idx, row in stopped_games.iterrows():
                    game_id = row['id']
                    numbers = row['numbers_list']
                    start_date = row['start_date']
                    
                    with st.container(border=True):
                        st.caption(f"ID: {game_id} | Início: {start_date} (Parado)")
                        st.text(f"Números: {numbers}")
                        if st.button("Reativar", key=f"reactivate_{game_id}"):
                            conn = get_db_connection()
                            conn.execute("UPDATE tracked_games SET active = 1 WHERE id = ?", (game_id,))
                            conn.commit()
                            conn.close()
                            st.rerun()

    else:
        st.info("Nenhum jogo cadastrado. Utilize a barra lateral para começar.")

if __name__ == "__main__":
    main()