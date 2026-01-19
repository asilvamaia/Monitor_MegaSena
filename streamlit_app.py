import streamlit as st
import pandas as pd
import requests
import numpy as np
import sqlite3
import os
import io
import urllib3
import zipfile
import itertools
import unicodedata
import json
import plotly.express as px
import plotly.graph_objects as go
from datetime import datetime
from io import BytesIO

# --- Configuração Inicial ---
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

st.set_page_config(
    page_title="Loterias Pro Ultimate",
    page_icon="🍀",
    layout="wide",
    initial_sidebar_state="expanded"
)

# --- Constantes e Configurações ---
DB_FILE = 'loterias.db'

GAME_CONFIG = {
    "Mega-Sena": {
        "slug": "megasena",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Mega-Sena",
        "range": 60, "draw": 6, "cost": 5.00,
        "min_win": 4, "cols_grid": 10,
        "labels": {4: "Quadra", 5: "Quina", 6: "Sena"},
        "est_prize": {4: 1000, 5: 50000, 6: 15000000}
    },
    "Quina": {
        "slug": "quina",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Quina",
        "range": 80, "draw": 5, "cost": 2.50,
        "min_win": 2, "cols_grid": 10,
        "labels": {2: "Duque", 3: "Terno", 4: "Quadra", 5: "Quina"},
        "est_prize": {2: 4.00, 3: 100, 4: 8000, 5: 5000000}
    },
    "Lotofácil": {
        "slug": "lotofacil",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Lotofacil",
        "range": 25, "draw": 15, "cost": 3.00,
        "min_win": 11, "cols_grid": 5,
        "labels": {11: "11 pts", 12: "12 pts", 13: "13 pts", 14: "14 pts", 15: "15 pts"},
        "est_prize": {11: 6, 12: 12, 13: 30, 14: 1500, 15: 1500000}
    }
}

# --- CSS Personalizado ---
st.markdown("""
<style>
    .ball { display: inline-block; width: 32px; height: 32px; line-height: 32px; border-radius: 50%; color: white; text-align: center; font-weight: bold; font-size: 14px; margin: 2px; }
    .ball-megasena { background-color: #209869; }
    .ball-quina { background-color: #260085; }
    .ball-lotofacil { background-color: #930089; }
    .metric-card { background-color: #f8f9fa; border: 1px solid #dee2e6; padding: 15px; border-radius: 8px; text-align: center; margin-bottom: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.05); }
    .roi-positive { color: #28a745; font-weight: bold; font-size: 1.2em; }
    .roi-negative { color: #dc3545; font-weight: bold; font-size: 1.2em; }
    div[data-testid="stColumn"] { text-align: center; }
    label[data-testid="stCheckbox"] { padding-right: 0px; }
</style>
""", unsafe_allow_html=True)

# --- Banco de Dados (SQLite) ---

def init_db():
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute('''CREATE TABLE IF NOT EXISTS draws (
                    game TEXT, concurso INTEGER, date DATE, 
                    d1 INTEGER, d2 INTEGER, d3 INTEGER, d4 INTEGER, d5 INTEGER, 
                    d6 INTEGER, d7 INTEGER, d8 INTEGER, d9 INTEGER, d10 INTEGER,
                    d11 INTEGER, d12 INTEGER, d13 INTEGER, d14 INTEGER, d15 INTEGER,
                    PRIMARY KEY (game, concurso))''')
    c.execute('''CREATE TABLE IF NOT EXISTS user_games (
                    id TEXT PRIMARY KEY, game_type TEXT, name TEXT, 
                    numbers TEXT, created_at DATE, cost REAL)''')
    conn.commit()
    conn.close()

def db_save_draws(df, game_name):
    conn = sqlite3.connect(DB_FILE)
    cfg = GAME_CONFIG[game_name]
    for i in range(cfg['draw'] + 1, 16):
        df[f'D{i}'] = 0
        
    records = []
    for _, row in df.iterrows():
        rec = [game_name, int(row['Concurso']), row['Data'].strftime('%Y-%m-%d')]
        rec.extend([int(row[f'D{i}']) for i in range(1, 16)])
        records.append(rec)
        
    conn.executemany('''INSERT OR REPLACE INTO draws VALUES 
                     (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', records)
    conn.commit()
    conn.close()

def db_get_draws(game_name):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql(f"SELECT * FROM draws WHERE game = '{game_name}' ORDER BY concurso DESC", conn)
    conn.close()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df.rename(columns={'concurso': 'Concurso', 'date': 'Data'}, inplace=True)
        for i in range(1, 16):
            df.rename(columns={f'd{i}': f'D{i}'}, inplace=True)
    return df

def db_save_user_game(game_type, name, numbers, cost):
    conn = sqlite3.connect(DB_FILE)
    gid = datetime.now().strftime("%Y%m%d%H%M%S%f")
    nums_str = json.dumps(sorted(numbers))
    conn.execute("INSERT INTO user_games VALUES (?,?,?,?,?,?)", 
              (gid, game_type, name, nums_str, datetime.now().strftime('%Y-%m-%d'), cost))
    conn.commit()
    conn.close()

def db_get_user_games(game_type):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    c.execute("SELECT * FROM user_games WHERE game_type = ? ORDER BY created_at DESC", (game_type,))
    rows = c.fetchall()
    conn.close()
    games = []
    for r in rows:
        games.append({
            "id": r[0], "type": r[1], "nome": r[2], 
            "nums": json.loads(r[3]), "date": r[4], "cost": r[5]
        })
    return games

def db_delete_user_game(gid):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM user_games WHERE id = ?", (gid,))
    conn.commit()
    conn.close()

init_db()

# --- ETL: Processamento de Dados Blindado ---

def normalize_text(text):
    if not isinstance(text, str): return str(text)
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII').lower()

def process_dataframe(df, game_name):
    cfg = GAME_CONFIG[game_name]
    
    start_row = -1
    for i in range(min(20, len(df))):
        row_values = [normalize_text(x) for x in df.iloc[i].values]
        if 'concurso' in row_values and ('data' in row_values or 'data sorteio' in row_values):
            start_row = i
            df.columns = df.iloc[i] 
            break
            
    if start_row >= 0: df = df.iloc[start_row + 1:].copy()

    new_columns = {}
    for col in df.columns:
        col_clean = normalize_text(col).strip()
        if 'concurso' in col_clean: new_columns[col] = 'Concurso'
        elif 'data' in col_clean: new_columns[col] = 'Data'
        else:
            for i in range(1, 21):
                patterns = [f"bola {i}", f"bola{i}", f"dezena {i}", f"dezena{i}", f"{i}a dezena", f"{i} dezena"]
                if any(p in col_clean for p in patterns):
                    new_columns[col] = f'D{i}'
                    break
    df.rename(columns=new_columns, inplace=True)

    try:
        cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
        required = ['Concurso', 'Data'] + cols_draw
        
        if not all(c in df.columns for c in cols_draw):
            if len(df.columns) >= len(required):
                mapper = {df.columns[0]: 'Concurso', df.columns[1]: 'Data'}
                for idx, c_name in enumerate(cols_draw): mapper[df.columns[2+idx]] = c_name
                df.rename(columns=mapper, inplace=True)
            else: return pd.DataFrame()

        for c in cols_draw:
            df[c] = df[c].astype(str).str.replace(r'[^\d]', '', regex=True)
            df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0).astype(int)
        
        df['Concurso'] = pd.to_numeric(df['Concurso'], errors='coerce').fillna(0).astype(int)
        df['Data'] = pd.to_datetime(df['Data'], dayfirst=True, errors='coerce')
        df = df.dropna(subset=['Concurso'])
        df = df[df['Concurso'] > 0]
        
        return df.sort_values('Concurso', ascending=True)
    except Exception as e:
        print(e)
        return pd.DataFrame()

def download_update_data(game_name):
    cfg = GAME_CONFIG[game_name]
    headers = {"User-Agent": "Mozilla/5.0"}
    try:
        response = requests.get(cfg['url_zip'], headers=headers, verify=False, timeout=15)
        response.raise_for_status()
        content = response.text
        try:
            j = response.json()
            if 'html' in j: content = j['html']
        except: pass
        content = content.replace('&nbsp;', '')
        dfs = pd.read_html(io.StringIO(content), decimal=',', thousands='.')
        if dfs:
            df_clean = process_dataframe(dfs[0], game_name)
            if not df_clean.empty:
                db_save_draws(df_clean, game_name)
                return True, f"Atualizado: {len(df_clean)} jogos."
    except Exception as e: return False, f"Erro: {str(e)}"
    return False, "Dados inválidos."

# --- Funções Inteligentes ---
def check_filters(numbers):
    pares = len([n for n in numbers if n % 2 == 0])
    if pares == 0 or pares == len(numbers): return False
    return True

def generate_smart_games(game_name, qtd, num_dezenas, fixos=[]):
    cfg = GAME_CONFIG[game_name]
    pool = [n for n in range(1, cfg['range'] + 1) if n not in fixos]
    games = []
    tentativas = 0
    if num_dezenas < cfg['draw']: num_dezenas = cfg['draw']
    
    while len(games) < qtd and tentativas < 5000:
        needed = num_dezenas - len(fixos)
        if needed <= len(pool):
            rnd = sorted(list(fixos) + list(np.random.choice(pool, needed, replace=False)))
            rnd = [int(x) for x in rnd]
            if check_filters(rnd): games.append(rnd)
        tentativas += 1
    return games

def calculate_roi(df_history, user_games, game_name):
    cfg = GAME_CONFIG[game_name]
    total_spent = sum(g['cost'] for g in user_games)
    total_won = 0
    wins_count = {k:0 for k in cfg['labels'].keys()}
    if df_history.empty: return 0, 0, wins_count
    
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    for game in user_games:
        game_dt = pd.to_datetime(game['date'])
        valid_draws = df_history[df_history['Data'] >= game_dt]
        game_set = set(game['nums'])
        for _, draw in valid_draws.iterrows():
            draw_set = {draw[c] for c in cols_draw}
            hits = len(game_set.intersection(draw_set))
            if hits in cfg['est_prize']:
                total_won += cfg['est_prize'][hits]
                wins_count[hits] += 1
    return total_spent, total_won, wins_count

def run_backtest(df, numbers, game_name):
    cfg = GAME_CONFIG[game_name]
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    game_set = set(numbers)
    history = []
    total_won = 0
    
    for _, row in df.iterrows():
        draw_set = {row[c] for c in cols_draw}
        hits = len(game_set.intersection(draw_set))
        if hits >= cfg['min_win']:
            prize = cfg['est_prize'].get(hits, 0)
            total_won += prize
            history.append({
                "Concurso": row['Concurso'],
                "Data": row['Data'],
                "Acertos": hits,
                "Prêmio Est.": prize
            })
    return history, total_won

def calculate_hits(df, game_nums, start_date, game_name):
    """
    Verifica acertos a partir de uma data dinâmica
    """
    cfg = GAME_CONFIG[game_name]
    if df.empty: return []
    
    try:
        # Garante que start_date seja datetime (pode vir como date do st.date_input)
        start_dt = pd.to_datetime(start_date)
    except: 
        start_dt = df['Data'].min()
    
    df_valid = df[df['Data'] >= start_dt].copy()
    hits = []
    game_set = set(game_nums)
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    
    for _, row in df_valid.iterrows():
        draw_nums = {row[c] for c in cols_draw}
        matches = game_set.intersection(draw_nums)
        qtd = len(matches)
        
        if qtd > 0:
            hits.append({
                "Concurso": row['Concurso'],
                "Data": row['Data'].strftime('%d/%m/%Y'),
                "Acertos": qtd,
                "Dezenas Sorteadas": sorted(list(draw_nums)),
                "Seus Acertos": sorted(list(matches))
            })
    
    hits.sort(key=lambda x: x['Acertos'], reverse=True)
    return hits

# --- INTERFACE ---
st.sidebar.title("Loterias Pro Ultimate")
selected_game = st.sidebar.selectbox("Modalidade", list(GAME_CONFIG.keys()))
current_cfg = GAME_CONFIG[selected_game]

# Inicializa Session State para controle de Loop
if 'last_processed_file' not in st.session_state:
    st.session_state['last_processed_file'] = None

df_data = db_get_draws(selected_game)

st.sidebar.divider()
st.sidebar.markdown("📂 **Banco de Dados**")
if not df_data.empty:
    last = df_data['Concurso'].max()
    dt_last = df_data['Data'].max().strftime('%d/%m/%Y')
    st.sidebar.success(f"Base OK: Conc {last} ({dt_last})")
else:
    st.sidebar.error("Base Vazia")

with st.sidebar.expander("🔄 Atualizar Dados"):
    if st.button("Download Automático"):
        with st.status("Baixando..."):
            ok, msg = download_update_data(selected_game)
            if ok: st.rerun()
            else: st.error(msg)
    
    st.caption("Ou upload manual:")
    up = st.file_uploader("Arquivo", type=['htm', 'html', 'xlsx', 'zip'], label_visibility="collapsed")
    
    if up:
        file_signature = f"{up.name}_{up.size}"
        if st.session_state['last_processed_file'] != file_signature:
            with st.spinner("Processando..."):
                try:
                    if up.name.endswith('.zip'):
                        with zipfile.ZipFile(up) as z:
                            fn = [n for n in z.namelist() if n.endswith(('.htm', '.html', '.xlsx'))][0]
                            with z.open(fn) as f:
                                df_raw = pd.read_excel(f, engine='openpyxl') if fn.endswith('.xlsx') else pd.read_html(f, decimal=',', thousands='.')[0]
                    elif up.name.endswith('.xlsx'):
                        df_raw = pd.read_excel(up, engine='openpyxl')
                    else:
                        df_raw = pd.read_html(up, decimal=',', thousands='.')[0]
                    
                    df_clean = process_dataframe(df_raw, selected_game)
                    if not df_clean.empty:
                        db_save_draws(df_clean, selected_game)
                        st.session_state['last_processed_file'] = file_signature
                        st.success("Atualizado!")
                        st.rerun()
                    else: st.error("Erro no layout do arquivo")
                except Exception as e: st.error(f"Erro: {e}")

page = st.sidebar.radio("Navegação", ["🏠 Home", "💸 Dashboard ROI", "📝 Meus Jogos", "🔮 Simulador", "🎲 Gerador IA", "📊 Análise"])

# --- PÁGINAS ---

if page == "🏠 Home":
    st.title(f"Resultado: {selected_game}")
    try:
        r = requests.get(f"https://servicebus2.caixa.gov.br/portaldeloterias/api/{current_cfg['slug']}/", verify=False, timeout=3).json()
        concurso, dezenas = r['numero'], [int(d) for d in r['listaDezenas']]
        data_ap, acumulou = r['dataApuracao'], r['acumulado']
    except:
        if not df_data.empty:
            lr = df_data.iloc[0]
            concurso, dezenas = lr['Concurso'], [lr[f'D{i}'] for i in range(1, current_cfg['draw']+1)]
            data_ap, acumulou = lr['Data'].strftime('%d/%m/%Y'), False
        else: concurso = None

    if concurso:
        c1, c2 = st.columns([3, 1])
        c1.markdown(f"### Concurso {concurso} - {data_ap}")
        c1.markdown("".join([f'<div class="ball ball-{current_cfg["slug"]}">{d}</div>' for d in dezenas]), unsafe_allow_html=True)
        lbl, bg = ("ACUMULOU", "#dc3545") if acumulou else ("Saiu!", "#28a745")
        c2.markdown(f"<div style='background:{bg};color:white;padding:20px;border-radius:10px;text-align:center'><h3>{lbl}</h3></div>", unsafe_allow_html=True)
    else: st.warning("Sem dados.")

elif page == "💸 Dashboard ROI":
    st.title("Performance Financeira")
    user_games = db_get_user_games(selected_game)
    if not user_games or df_data.empty:
        st.info("Cadastre jogos e atualize a base para ver o ROI.")
    else:
        spent, won, counts = calculate_roi(df_data, user_games, selected_game)
        profit = won - spent
        c1, c2, c3 = st.columns(3)
        c1.metric("Total Investido", f"R$ {spent:,.2f}")
        c2.metric("Retorno Estimado", f"R$ {won:,.2f}")
        c3.metric("Saldo Líquido", f"R$ {profit:,.2f}", delta=profit)
        st.divider()
        cols = st.columns(len(counts))
        for idx, (hits, count) in enumerate(counts.items()):
            label = current_cfg['labels'].get(hits, f"{hits} pts")
            cols[idx].markdown(f"<div class='metric-card'><div>{label}</div><h2 style='color:#209869'>{count}</h2></div>", unsafe_allow_html=True)

elif page == "📝 Meus Jogos":
    st.title(f"Carteira: {selected_game}")
    with st.expander("➕ Novo Volante", expanded=True):
        with st.form("add_game"):
            c1, c2 = st.columns([2, 1])
            nome = c1.text_input("Identificador")
            custo = c2.number_input("Custo (R$)", value=current_cfg['cost'], step=0.5)
            st.markdown("---")
            sel_nums = []
            cols = st.columns(current_cfg['cols_grid'])
            for i in range(1, current_cfg['range']+1):
                idx = (i-1) % current_cfg['cols_grid']
                if cols[idx].checkbox(f"{i:02d}", key=f"v_{i}"): sel_nums.append(i)
            if st.form_submit_button("Salvar Jogo", type="primary"):
                if len(sel_nums) < current_cfg['draw']: st.error("Números insuficientes.")
                else:
                    db_save_user_game(selected_game, nome, sel_nums, custo)
                    st.success("Salvo!"); st.rerun()

    st.divider()
    games = db_get_user_games(selected_game)
    if not games: st.info("Sem jogos.")
    for g in games:
        with st.container():
            c1, c2, c3 = st.columns([5, 1, 1])
            c1.markdown(f"**{g['nome']}**")
            c1.markdown("".join([f'<span class="ball ball-{current_cfg["slug"]}">{n}</span>' for n in g['nums']]), unsafe_allow_html=True)
            if c2.button("🗑️", key=f"d{g['id']}"): db_delete_user_game(g['id']); st.rerun()
            
            # --- ÁREA DE CONFERÊNCIA ATUALIZADA ---
            check = c3.toggle("Conferir", key=f"c{g['id']}")
            if check:
                # Seletor de Data de Início da Conferência
                st.caption("Configurações da Conferência:")
                
                # Tenta converter a data salva para datetime, senão usa hoje
                try:
                    default_date = datetime.strptime(g['date'], "%Y-%m-%d")
                except:
                    default_date = datetime.today()
                    
                check_start_date = st.date_input(
                    "Conferir a partir de:", 
                    value=default_date,
                    format="DD/MM/YYYY",
                    key=f"dt_chk_{g['id']}"
                )

                if df_data.empty: 
                    st.warning("Base vazia.")
                else:
                    # Passa a data selecionada no input, não a gravada no banco
                    results = calculate_hits(df_data, g['nums'], check_start_date, selected_game)
                    
                    if results:
                        st.markdown(f"**{len(results)} sorteios com acertos encontrados:**")
                        for r in results:
                            qtd = r['Acertos']
                            if qtd == current_cfg['draw']: color = "#28a745"
                            elif qtd >= current_cfg['draw']-2: color = "#17a2b8"
                            else: color = "#6c757d"
                            
                            st.markdown(f"""
                                <div style='border-left:4px solid {color};padding-left:8px;margin:4px;font-size:0.9em;background:#f9f9f9'>
                                    <b>{qtd} acertos</b> em {r['Data']} (Conc {r['Concurso']})<br>
                                    <span style='color:grey'>Sorteio: {r['Dezenas Sorteadas']}</span><br>
                                    <span style='color:{color};font-weight:bold'>Seus: {r['Seus Acertos']}</span>
                                </div>""", unsafe_allow_html=True)
                    else: st.info("Nenhum acerto neste período.")
        st.divider()

elif page == "🔮 Simulador":
    st.title("Máquina do Tempo 🕰️")
    if df_data.empty: st.warning("Base vazia.")
    else:
        sel_nums = []
        st.subheader("Escolha seu jogo para testar na história:")
        cols = st.columns(current_cfg['cols_grid'])
        for i in range(1, current_cfg['range']+1):
            idx = (i-1) % current_cfg['cols_grid']
            if cols[idx].checkbox(f"{i}", key=f"sim_{i}"): sel_nums.append(i)
        
        if st.button("Simular no Passado"):
            if len(sel_nums) < current_cfg['draw']: st.error("Selecione mais números.")
            else:
                hist, cash = run_backtest(df_data, sel_nums, selected_game)
                if not hist: st.info("❄️ Nunca premiado!")
                else:
                    st.success(f"🔥 Premiado {len(hist)} vezes!")
                    st.metric("Total Acumulado (Estimado)", f"R$ {cash:,.2f}")
                    df_hist = pd.DataFrame(hist)
                    df_hist['Data'] = pd.to_datetime(df_hist['Data']).dt.strftime('%d/%m/%Y')
                    st.dataframe(df_hist, hide_index=True, use_container_width=True)

elif page == "🎲 Gerador IA":
    st.title("Gerador Inteligente")
    tab1, tab2 = st.tabs(["🤖 Palpites IA", "🔒 Fechamentos"])
    with tab1:
        c1, c2, c3 = st.columns([1, 1, 2])
        qtd = c1.number_input("Qtd Jogos", 1, 50, 5)
        num_dez = c2.number_input("Dezenas/Jogo", value=current_cfg['draw'], min_value=current_cfg['draw'], max_value=18)
        fix = c3.multiselect("Fixar Dezenas", range(1, current_cfg['range']+1))
        
        if st.button("Gerar"):
            res = generate_smart_games(selected_game, qtd, num_dez, fix)
            df_res = pd.DataFrame(res, columns=[f"B{i+1}" for i in range(len(res[0]))])
            st.dataframe(df_res, use_container_width=True)
            
            buffer = BytesIO()
            with pd.ExcelWriter(buffer, engine='openpyxl') as writer: df_res.to_excel(writer, index=False)
            st.download_button("📥 Excel", buffer.getvalue(), "palpites.xlsx")
            
    with tab2:
        sel = st.multiselect("Selecione para desdobrar:", range(1, current_cfg['range']+1))
        if len(sel) >= current_cfg['draw']:
            possibilites = len(list(itertools.combinations(sel, current_cfg['draw'])))
            st.caption(f"Gerará {possibilites} jogos.")
            if st.button("Gerar Fechamento"):
                if possibilites > 5000: st.error("Muitos jogos!")
                else:
                    res = [sorted(list(c)) for c in itertools.combinations(sel, current_cfg['draw'])]
                    st.dataframe(pd.DataFrame(res), use_container_width=True)

elif page == "📊 Análise":
    st.title("Inteligência")
    if df_data.empty: st.warning("Base vazia.")
    else:
        max_c = int(df_data['Concurso'].max())
        c1, c2 = st.columns(2)
        ini = c1.number_input("Início", 1, max_c, max(1, max_c-100))
        fim = c2.number_input("Fim", 1, max_c, max_c)
        if st.button("Processar"):
            df_p = df_data[(df_data['Concurso'] >= ini) & (df_data['Concurso'] <= fim)]
            cols_draw = [f'D{i}' for i in range(1, current_cfg['draw']+1)]
            stats = []
            for n in range(1, current_cfg['range']+1):
                mask = np.zeros(len(df_p), dtype=bool)
                for c in cols_draw: mask |= (df_p[c] == n)
                stats.append({"Dezena": n, "Freq": mask.sum()})
            df_s = pd.DataFrame(stats)
            
            tab1, tab2, tab3 = st.tabs(["📊 Tabela", "🔥 Heatmap", "📐 Padrões"])
            
            with tab1:
                st.dataframe(df_s, use_container_width=True, column_config={
                    "Dezena": st.column_config.NumberColumn(format="%d"),
                    "Freq": st.column_config.BarChartColumn(y_min=0, y_max=int(df_s['Freq'].max()))
                }, hide_index=True)
                
            with tab2:
                cols_grid = current_cfg['cols_grid']
                rows_grid = (current_cfg['range'] // cols_grid) + 1
                z = np.zeros((rows_grid, cols_grid))
                txt = [["" for _ in range(cols_grid)] for _ in range(rows_grid)]
                for r in range(rows_grid):
                    for c in range(cols_grid):
                        num = r * cols_grid + c + 1
                        if num <= current_cfg['range']:
                            val = df_s.loc[df_s['Dezena']==num, 'Freq'].values[0]
                            z[r][c] = val
                            txt[r][c] = str(num)
                        else: z[r][c] = None
                fig = go.Figure(data=go.Heatmap(z=z, text=txt, texttemplate="%{text}", colorscale='Greens', xgap=2, ygap=2))
                fig.update_layout(yaxis=dict(autorange="reversed", showticklabels=False), xaxis=dict(showticklabels=False))
                st.plotly_chart(fig, use_container_width=True)
                
            with tab3:
                df_p['Pares'] = df_p[cols_draw].apply(lambda x: np.sum([n % 2 == 0 for n in x]), axis=1)
                st.plotly_chart(px.pie(names=["Pares", "Ímpares"], values=[df_p['Pares'].mean(), current_cfg['draw']-df_p['Pares'].mean()], title="Média Par/Ímpar"))
                
                if selected_game == "Mega-Sena":
                    lines_data = []
                    cols_data = []
                    for _, row in df_p.iterrows():
                        nums = [row[c] for c in cols_draw]
                        lines_data.append(len(set([(n-1)//10 for n in nums])))
                        cols_data.append(len(set([(n-1)%10 for n in nums])))
                    c1, c2 = st.columns(2)
                    c1.plotly_chart(px.histogram(x=lines_data, title="Linhas Ocupadas"), use_container_width=True)
                    c2.plotly_chart(px.histogram(x=cols_data, title="Colunas Ocupadas"), use_container_width=True)