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

# --- SISTEMA DE TEMAS E LAYOUT ---
def inject_custom_css(theme_mode, is_mobile):
    if theme_mode == "Escuro":
        bg_color = "#0e1117"
        text_color = "#fafafa"
        card_bg = "#262730"
    else:
        bg_color = "#ffffff"
        text_color = "#000000"
        card_bg = "#f8f9fa"

    col_align = "center"
    font_size_checkbox = "18px" if is_mobile else "14px"

    st.markdown(f"""
    <style>
        .stApp {{ background-color: {bg_color}; color: {text_color}; }}
        .metric-card {{ background-color: {card_bg}; border: 1px solid #444; padding: 10px; border-radius: 8px; text-align: center; margin-bottom: 5px; }}
        .ball {{ display: inline-block; width: 35px; height: 35px; line-height: 35px; border-radius: 50%; color: white; text-align: center; font-weight: bold; font-size: 15px; margin: 3px; box-shadow: 1px 1px 2px rgba(0,0,0,0.3); }}
        .ball-megasena {{ background-color: #209869; }}
        .ball-quina {{ background-color: #260085; }}
        .ball-lotofacil {{ background-color: #930089; }}
        div[data-testid="stColumn"] {{ text-align: {col_align}; }}
        label[data-testid="stCheckbox"] {{ font-size: {font_size_checkbox} !important; padding: 5px; width: 100%; justify-content: center; }}
    </style>
    """, unsafe_allow_html=True)

# --- Constantes ---
DB_FILE = 'loterias.db'

BASE_CONFIG = {
    "Mega-Sena": {
        "slug": "megasena",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Mega-Sena",
        "range": 60, "draw": 6, "cost": 5.00, "min_win": 4, 
        "cols_pc": 10, "cols_mobile": 5,
        "labels": {4: "Quadra", 5: "Quina", 6: "Sena"},
        "est_prize": {4: 1000, 5: 50000, 6: 15000000}
    },
    "Quina": {
        "slug": "quina",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Quina",
        "range": 80, "draw": 5, "cost": 2.50, "min_win": 2, 
        "cols_pc": 10, "cols_mobile": 5,
        "labels": {2: "Duque", 3: "Terno", 4: "Quadra", 5: "Quina"},
        "est_prize": {2: 4.00, 3: 100, 4: 8000, 5: 5000000}
    },
    "Lotofácil": {
        "slug": "lotofacil",
        "url_zip": "https://servicebus2.caixa.gov.br/portaldeloterias/api/resultados/download?modalidade=Lotofacil",
        "range": 25, "draw": 15, "cost": 3.00, "min_win": 11, 
        "cols_pc": 5, "cols_mobile": 5,
        "labels": {11: "11 pts", 12: "12 pts", 13: "13 pts", 14: "14 pts", 15: "15 pts"},
        "est_prize": {11: 6, 12: 12, 13: 30, 14: 1500, 15: 1500000}
    }
}

# --- Banco de Dados ---

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
    cfg = BASE_CONFIG[game_name]
    for i in range(cfg['draw'] + 1, 16):
        df[f'D{i}'] = 0
    records = []
    for _, row in df.iterrows():
        rec = [game_name, int(row['Concurso']), row['Data'].strftime('%Y-%m-%d')]
        rec.extend([int(row[f'D{i}']) for i in range(1, 16)])
        records.append(rec)
    conn.executemany('''INSERT OR REPLACE INTO draws VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''', records)
    conn.commit()
    conn.close()

def db_get_draws(game_name):
    conn = sqlite3.connect(DB_FILE)
    df = pd.read_sql(f"SELECT * FROM draws WHERE game = '{game_name}' ORDER BY concurso DESC", conn)
    conn.close()
    if not df.empty:
        df['date'] = pd.to_datetime(df['date'])
        df.rename(columns={'concurso': 'Concurso', 'date': 'Data'}, inplace=True)
        for i in range(1, 16): df.rename(columns={f'd{i}': f'D{i}'}, inplace=True)
    return df

def db_save_user_game(game_type, name, numbers, cost, date=None):
    conn = sqlite3.connect(DB_FILE)
    gid = datetime.now().strftime("%Y%m%d%H%M%S%f")
    nums_str = json.dumps(sorted(numbers))
    dt_save = date if date else datetime.now().strftime('%Y-%m-%d')
    conn.execute("INSERT INTO user_games VALUES (?,?,?,?,?,?)", (gid, game_type, name, nums_str, dt_save, cost))
    conn.commit()
    conn.close()

def db_get_user_games(game_type=None):
    conn = sqlite3.connect(DB_FILE)
    c = conn.cursor()
    if game_type:
        c.execute("SELECT * FROM user_games WHERE game_type = ? ORDER BY created_at DESC", (game_type,))
    else:
        c.execute("SELECT * FROM user_games ORDER BY created_at DESC") # Pega tudo para backup
    rows = c.fetchall()
    conn.close()
    games = []
    for r in rows:
        games.append({"id": r[0], "type": r[1], "nome": r[2], "nums": json.loads(r[3]), "date": r[4], "cost": r[5]})
    return games

def db_delete_user_game(gid):
    conn = sqlite3.connect(DB_FILE)
    conn.execute("DELETE FROM user_games WHERE id = ?", (gid,))
    conn.commit()
    conn.close()

# --- Backup System ---
def export_games_json():
    games = db_get_user_games(None) # Pega de todas modalidades
    return json.dumps(games, indent=2)

def import_games_json(json_file):
    try:
        data = json.load(json_file)
        count = 0
        for g in data:
            # Salva novamente (vai gerar novos IDs para evitar colisão)
            db_save_user_game(g['type'], g['nome'], g['nums'], g['cost'], g['date'])
            count += 1
        return True, count
    except Exception as e:
        return False, str(e)

init_db()

# --- ETL ---
def normalize_text(text):
    if not isinstance(text, str): return str(text)
    return unicodedata.normalize('NFKD', text).encode('ASCII', 'ignore').decode('ASCII').lower()

def process_dataframe(df, game_name):
    cfg = BASE_CONFIG[game_name]
    start_row = -1
    for i in range(min(20, len(df))):
        row_values = [normalize_text(x) for x in df.iloc[i].values]
        if 'concurso' in row_values and ('data' in row_values or 'data sorteio' in row_values):
            start_row = i
            df.columns = df.iloc[i]; break
    if start_row >= 0: df = df.iloc[start_row + 1:].copy()

    new_columns = {}
    for col in df.columns:
        col_clean = normalize_text(col).strip()
        if 'concurso' in col_clean: new_columns[col] = 'Concurso'
        elif 'data' in col_clean: new_columns[col] = 'Data'
        else:
            for i in range(1, 21):
                patterns = [f"bola {i}", f"bola{i}", f"dezena {i}", f"dezena{i}", f"{i}a dezena", f"{i} dezena"]
                if any(p in col_clean for p in patterns): new_columns[col] = f'D{i}'; break
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
        return df.dropna(subset=['Concurso']).sort_values('Concurso', ascending=True)
    except: return pd.DataFrame()

def download_update_data(game_name):
    cfg = BASE_CONFIG[game_name]
    try:
        r = requests.get(cfg['url_zip'], headers={"User-Agent": "Mozilla/5.0"}, verify=False, timeout=15)
        r.raise_for_status()
        content = r.text.replace('&nbsp;', '')
        try: 
            j = r.json(); 
            if 'html' in j: content = j['html']
        except: pass
        dfs = pd.read_html(io.StringIO(content), decimal=',', thousands='.')
        if dfs:
            df_clean = process_dataframe(dfs[0], game_name)
            if not df_clean.empty:
                db_save_draws(df_clean, game_name)
                return True, f"Atualizado: {len(df_clean)}"
    except Exception as e: return False, str(e)
    return False, "Erro"

# --- Lógica ---
def check_filters(numbers):
    p = len([n for n in numbers if n % 2 == 0])
    return False if p == 0 or p == len(numbers) else True

def generate_smart_games(game_name, qtd, num_dezenas, fixos=[]):
    cfg = BASE_CONFIG[game_name]
    pool = [n for n in range(1, cfg['range'] + 1) if n not in fixos]
    games = []
    tentativas = 0
    if num_dezenas < cfg['draw']: num_dezenas = cfg['draw']
    while len(games) < qtd and tentativas < 5000:
        needed = num_dezenas - len(fixos)
        if needed <= len(pool):
            rnd = sorted(list(fixos) + list(np.random.choice(pool, needed, replace=False)))
            if check_filters([int(x) for x in rnd]): games.append([int(x) for x in rnd])
        tentativas += 1
    return games

def calculate_roi(df_history, user_games, game_name):
    cfg = BASE_CONFIG[game_name]
    total_spent = sum(g['cost'] for g in user_games)
    total_won = 0
    wins_count = {k:0 for k in cfg['labels'].keys()}
    if df_history.empty: return 0, 0, wins_count
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    for game in user_games:
        game_dt = pd.to_datetime(game['date'])
        valid = df_history[df_history['Data'] >= game_dt]
        game_set = set(game['nums'])
        for _, draw in valid.iterrows():
            hits = len(game_set.intersection({draw[c] for c in cols_draw}))
            if hits in cfg['est_prize']:
                total_won += cfg['est_prize'][hits]; wins_count[hits] += 1
    return total_spent, total_won, wins_count

def run_backtest(df, numbers, game_name):
    cfg = BASE_CONFIG[game_name]
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    game_set, hist, won = set(numbers), [], 0
    for _, row in df.iterrows():
        hits = len(game_set.intersection({row[c] for c in cols_draw}))
        if hits >= cfg['min_win']:
            prize = cfg['est_prize'].get(hits, 0); won += prize
            hist.append({"Concurso": row['Concurso'], "Data": row['Data'], "Acertos": hits, "Prêmio": prize})
    return hist, won

def calculate_hits(df, game_nums, start_date, game_name):
    cfg = BASE_CONFIG[game_name]
    if df.empty: return []
    try: start_dt = pd.to_datetime(start_date)
    except: start_dt = df['Data'].min()
    valid = df[df['Data'] >= start_dt].copy()
    hits = []
    game_set = set(game_nums)
    cols_draw = [f'D{i}' for i in range(1, cfg['draw'] + 1)]
    for _, row in valid.iterrows():
        matches = game_set.intersection({row[c] for c in cols_draw})
        if len(matches) > 0:
            hits.append({"Concurso": row['Concurso'], "Data": row['Data'].strftime('%d/%m/%Y'), "Acertos": len(matches), "Dezenas Sorteadas": sorted(list({row[c] for c in cols_draw})), "Seus Acertos": sorted(list(matches))})
    hits.sort(key=lambda x: x['Acertos'], reverse=True)
    return hits

# --- INTERFACE ---
st.sidebar.title("Loterias Ultimate")
st.sidebar.markdown("### ⚙️ Visual")
layout_mode = st.sidebar.radio("Dispositivo:", ["🖥️ PC", "📱 Celular"], horizontal=True)
theme_mode = st.sidebar.radio("Tema:", ["Escuro", "Claro"], horizontal=True)
is_mobile = (layout_mode == "📱 Celular")
inject_custom_css(theme_mode, is_mobile)
selected_game = st.sidebar.selectbox("Modalidade", list(BASE_CONFIG.keys()))
current_cfg = BASE_CONFIG[selected_game]
active_cols_grid = current_cfg['cols_mobile'] if is_mobile else current_cfg['cols_pc']

if 'last_processed_file' not in st.session_state: st.session_state['last_processed_file'] = None
df_data = db_get_draws(selected_game)

st.sidebar.divider()
st.sidebar.markdown("📂 **Banco de Dados**")
if not df_data.empty:
    st.sidebar.success(f"Base OK: Conc {df_data['Concurso'].max()}")
else: st.sidebar.error("Base Vazia")

with st.sidebar.expander("🔄 Atualizar"):
    if st.button("Download Auto"):
        with st.status("Baixando..."):
            ok, msg = download_update_data(selected_game)
            if ok: st.rerun()
            else: st.error(msg)
    up = st.file_uploader("Upload Manual", type=['htm','html','xlsx','zip'], label_visibility="collapsed")
    if up:
        sig = f"{up.name}_{up.size}"
        if st.session_state['last_processed_file'] != sig:
            with st.spinner("Lendo..."):
                try:
                    if up.name.endswith('.zip'):
                        with zipfile.ZipFile(up) as z:
                            fn = [n for n in z.namelist() if n.endswith(('.htm','.html','.xlsx'))][0]
                            with z.open(fn) as f: df_raw = pd.read_excel(f, engine='openpyxl') if fn.endswith('.xlsx') else pd.read_html(f, decimal=',', thousands='.')[0]
                    elif up.name.endswith('.xlsx'): df_raw = pd.read_excel(up, engine='openpyxl')
                    else: df_raw = pd.read_html(up, decimal=',', thousands='.')[0]
                    df_clean = process_dataframe(df_raw, selected_game)
                    if not df_clean.empty:
                        db_save_draws(df_clean, selected_game)
                        st.session_state['last_processed_file'] = sig
                        st.success("OK!"); st.rerun()
                except Exception as e: st.error(str(e))

page = st.sidebar.radio("Navegação", ["🏠 Home", "📝 Meus Jogos", "💸 Dashboard ROI", "🔮 Simulador", "🎲 Gerador IA", "📊 Análise"])

if page == "🏠 Home":
    st.title(f"Resultado: {selected_game}")
    try:
        r = requests.get(f"https://servicebus2.caixa.gov.br/portaldeloterias/api/{current_cfg['slug']}/", verify=False, timeout=3).json()
        concurso, dezenas = r['numero'], [int(d) for d in r['listaDezenas']]
        data_ap, acumulou = r['dataApuracao'], r['acumulado']
    except:
        if not df_data.empty:
            lr = df_data.iloc[0]; concurso, dezenas = lr['Concurso'], [lr[f'D{i}'] for i in range(1, current_cfg['draw']+1)]
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
    st.title("ROI")
    ug = db_get_user_games(selected_game)
    if not ug or df_data.empty: st.info("Sem dados.")
    else:
        spent, won, counts = calculate_roi(df_data, ug, selected_game)
        profit = won - spent
        c1,c2,c3 = st.columns(3)
        c1.metric("Investido", f"R$ {spent:,.2f}"); c2.metric("Retorno", f"R$ {won:,.2f}"); c3.metric("Saldo", f"R$ {profit:,.2f}", delta=profit)
        st.divider()
        cols = st.columns(len(counts))
        for idx, (h, c) in enumerate(counts.items()):
            cols[idx].markdown(f"<div class='metric-card'><div>{current_cfg['labels'].get(h,f'{h}pts')}</div><h2>{c}</h2></div>", unsafe_allow_html=True)

elif page == "📝 Meus Jogos":
    st.title(f"Carteira: {selected_game}")
    
    # --- ÁREA DE BACKUP E RESTAURAÇÃO ---
    with st.expander("💾 Backup / Restaurar Jogos", expanded=False):
        c1, c2 = st.columns(2)
        with c1:
            st.markdown("#### 1. Salvar em Arquivo")
            json_data = export_games_json()
            st.download_button(
                label="📥 Baixar Meus Jogos (.json)",
                data=json_data,
                file_name=f"backup_loterias_{datetime.now().strftime('%Y%m%d')}.json",
                mime="application/json",
            )
            st.caption("Salve este arquivo no seu PC/Celular para não perder seus jogos.")
        
        with c2:
            st.markdown("#### 2. Restaurar Backup")
            uploaded_json = st.file_uploader("Carregar arquivo .json", type=["json"])
            if uploaded_json:
                ok, count = import_games_json(uploaded_json)
                if ok:
                    st.success(f"{count} jogos restaurados com sucesso!")
                    st.rerun()
                else:
                    st.error(f"Erro ao restaurar: {count}")

    st.divider()

    with st.expander("➕ Novo Volante", expanded=True):
        with st.form("add"):
            c1, c2 = st.columns([2, 1])
            nome = c1.text_input("Nome"); custo = c2.number_input("Custo", value=current_cfg['cost'])
            sel_nums = []
            cols = st.columns(active_cols_grid)
            for i in range(1, current_cfg['range']+1):
                idx = (i-1)%active_cols_grid
                if cols[idx].checkbox(f"{i:02d}", key=f"v_{i}"): sel_nums.append(i)
            if st.form_submit_button("Salvar", type="primary"):
                if len(sel_nums) < current_cfg['draw']: st.error("Erro nos números.")
                else: db_save_user_game(selected_game, nome, sel_nums, custo); st.success("Salvo!"); st.rerun()
    
    games = db_get_user_games(selected_game)
    if not games: st.info("Sem jogos.")
    for g in games:
        with st.container():
            c1,c2,c3 = st.columns([5,1,1])
            c1.markdown(f"**{g['nome']}**"); c1.markdown("".join([f'<span class="ball ball-{current_cfg["slug"]}">{n}</span>' for n in g['nums']]), unsafe_allow_html=True)
            if c2.button("🗑️", key=f"d{g['id']}"): db_delete_user_game(g['id']); st.rerun()
            if c3.toggle("Conferir", key=f"c{g['id']}"):
                try: d = datetime.strptime(g['date'], "%Y-%m-%d")
                except: d = datetime.today()
                chk_dt = st.date_input("Desde:", value=d, key=f"k{g['id']}")
                if df_data.empty: st.warning("Sem base.")
                else:
                    res = calculate_hits(df_data, g['nums'], chk_dt, selected_game)
                    if res:
                        st.markdown(f"**{len(res)} acertos:**")
                        for r in res:
                            q = r['Acertos']; cor = "#28a745" if q==current_cfg['draw'] else "#17a2b8" if q>=current_cfg['draw']-2 else "#6c757d"
                            st.markdown(f"<div style='border-left:4px solid {cor};padding-left:8px;margin:4px;font-size:0.9em;background:#333'><b>{q}</b> em {r['Data']} (Conc {r['Concurso']})<br><span style='color:grey'>{r['Dezenas Sorteadas']}</span></div>", unsafe_allow_html=True)
                    else: st.info("Nada.")
        st.divider()

elif page == "🔮 Simulador":
    st.title("Máquina do Tempo")
    if df_data.empty: st.warning("Base vazia.")
    else:
        sel = []
        cols = st.columns(active_cols_grid)
        for i in range(1, current_cfg['range']+1):
            if cols[(i-1)%active_cols_grid].checkbox(f"{i}", key=f"s{i}"): sel.append(i)
        if st.button("Simular"):
            if len(sel) < current_cfg['draw']: st.error("Poucos números.")
            else:
                h, c = run_backtest(df_data, sel, selected_game)
                if not h: st.info("Nunca premiado.")
                else:
                    st.success(f"{len(h)} prêmios! Total: R$ {c:,.2f}")
                    dfh = pd.DataFrame(h); dfh['Data'] = pd.to_datetime(dfh['Data']).dt.strftime('%d/%m/%Y')
                    st.dataframe(dfh, hide_index=True, use_container_width=True)

elif page == "🎲 Gerador IA":
    st.title("Gerador IA")
    t1, t2 = st.tabs(["IA", "Fechamentos"])
    with t1:
        c1, c2, c3 = st.columns([1, 1, 2])
        q = c1.number_input("Qtd", 1, 50, 5); n = c2.number_input("Dezenas", current_cfg['draw'], 18); f = c3.multiselect("Fixos", range(1, current_cfg['range']+1))
        if st.button("Gerar"):
            r = generate_smart_games(selected_game, q, n, f)
            df = pd.DataFrame(r, columns=[f"B{i+1}" for i in range(len(r[0]))])
            st.dataframe(df, use_container_width=True)
            b = BytesIO(); 
            with pd.ExcelWriter(b, engine='openpyxl') as w: df.to_excel(w, index=False)
            st.download_button("Excel", b.getvalue(), "jogos.xlsx")
    with t2:
        s = st.multiselect("Números:", range(1, current_cfg['range']+1))
        if len(s) >= current_cfg['draw']:
            st.caption(f"{len(list(itertools.combinations(s, current_cfg['draw'])))} jogos.")
            if st.button("Gerar Fechamento"):
                st.dataframe(pd.DataFrame([sorted(list(x)) for x in itertools.combinations(s, current_cfg['draw'])]), use_container_width=True)

elif page == "📊 Análise":
    st.title("Inteligência")
    if df_data.empty: st.warning("Base vazia.")
    else:
        mx = int(df_data['Concurso'].max())
        c1, c2 = st.columns(2); i = c1.number_input("Início", 1, mx, max(1, mx-100)); f = c2.number_input("Fim", 1, mx, mx)
        if st.button("Analisar"):
            dfp = df_data[(df_data['Concurso'] >= i) & (df_data['Concurso'] <= f)]
            cd = [f'D{k}' for k in range(1, current_cfg['draw']+1)]
            stt = []
            for num in range(1, current_cfg['range']+1):
                m = np.zeros(len(dfp), dtype=bool)
                for c in cd: m |= (dfp[c] == num)
                stt.append({"Dezena": num, "Freq": m.sum()})
            dfs = pd.DataFrame(stt)
            t1, t2 = st.tabs(["Tabela", "Heatmap"])
            with t1: st.dataframe(dfs, use_container_width=True)
            with t2:
                cg = active_cols_grid; rg = (current_cfg['range']//cg)+1
                z = np.zeros((rg, cg)); tx = [["" for _ in range(cg)] for _ in range(rg)]
                for r in range(rg):
                    for c in range(cg):
                        n = r*cg+c+1
                        if n <= current_cfg['range']:
                            z[r][c] = dfs.loc[dfs['Dezena']==n, 'Freq'].values[0]; tx[r][c] = str(n)
                        else: z[r][c] = None
                fig = go.Figure(data=go.Heatmap(z=z, text=tx, texttemplate="%{text}", colorscale='Greens', xgap=2, ygap=2))
                fig.update_layout(yaxis=dict(autorange="reversed", showticklabels=False), xaxis=dict(showticklabels=False), paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)')
                st.plotly_chart(fig, use_container_width=True)