import streamlit as st
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import os
import urllib.request
import matplotlib.font_manager as fm

pd.set_option('future.no_silent_downcasting', True)

@st.cache_resource
def load_japanese_font():
    """Google Fontsから日本語フォントをダウンロードし、Matplotlibに設定します"""
    font_url = 'https://github.com/googlefonts/morisawa-biz-ud-gothic/raw/main/fonts/ttf/BIZUDGothic-Regular.ttf'
    font_path = 'BIZUDGothic-Regular.ttf'
    
    # フォントファイルが存在しない場合のみダウンロード
    if not os.path.exists(font_path):
        urllib.request.urlretrieve(font_url, font_path)
        
    # ダウンロードしたフォントをMatplotlibに追加して標準設定にする
    fm.fontManager.addfont(font_path)
    plt.rcParams['font.family'] = 'BIZ UDGothic'
    plt.rcParams['font.size'] = 10

# アプリ起動時にフォントを読み込む
load_japanese_font()

@st.cache_data
def load_and_process_data():
    """
    前処理済みの統合処方データとマスタデータを読み込み、集計を行います。
    """
    # データの読み込み
    prescription_file = 'integrated_prescription_data.csv'
    master_file = 'integrated_drug_master.csv'

    if not os.path.exists(prescription_file):
        st.error(f"処方データ '{prescription_file}' が見つかりません。データ統合スクリプトを実行してアップロードしてください。")
        return pd.DataFrame()
    
    if not os.path.exists(master_file):
        st.error(f"医薬品マスタ '{master_file}' が見つかりません。")
        return pd.DataFrame()
    
    prescription_df = pd.read_csv(prescription_file, dtype={'薬価基準収載医薬品コード': str})
    master_df = pd.read_csv(master_file, dtype={'薬価基準収載医薬品コード': str})

    # 薬価基準収載医薬品コードの整形
    prescription_df['薬価基準収載医薬品コード'] = prescription_df['薬価基準収載医薬品コード'].str.strip().str.upper()
    master_df['薬価基準収載医薬品コード'] = master_df['薬価基準収載医薬品コード'].str.strip().str.upper()

    # 医薬品マスタの重複排除
    master_df = master_df.drop_duplicates(subset=['薬価基準収載医薬品コード'], keep='first')

    # 医薬品マスタと処方データの結合
    merged_df = pd.merge(prescription_df, master_df, on='薬価基準収載医薬品コード', how='left', suffixes=('', '_master'))

    # 販売中止などでマスタにない場合、医薬品名から一般名を抽出
    missing_generic = merged_df['一般名'].isna()
    if missing_generic.any():
        guessed_names = merged_df.loc[missing_generic, '医薬品名'].copy()
        # カギ括弧のメーカー名を削除
        guessed_names = guessed_names.str.replace(r'[「（\(].*?[」）\)]', '', regex=True)
        # 規格（数字＋単位）以降を削除
        guessed_names = guessed_names.str.replace(r'[０-９0-9\.．]+(?:ｍｇ|mg|ｇ|g|ｍＬ|mL|μｇ|μg|％|%|万単位|単位|ｍEｑ|mEq|管|瓶|袋|シート|枚).*', '', regex=True)
        # 残った末尾の剤形を削除
        guessed_names = guessed_names.str.replace(r'(?:ＯＤ|口腔内崩壊|徐放|腸溶|チュアブル|糖衣|無水)?(?:錠|カプセル|散|顆粒|細粒|ドライシロップ|シロップ|内用液|液|注|静注|筋注|皮下注|軟膏|クリーム|テープ|パッチ|ゲル|ローション|点眼液|点眼剤|点鼻液|点鼻剤|吸入剤|スプレー|キット|シリンジ|ペン|エキス)(?:・|付)?$', '', regex=True)
        # 抽出した一般名を代入
        merged_df.loc[missing_generic, '一般名'] = guessed_names.str.strip()

        def extract_form_from_yakkacode(code):
            code_str = str(code).strip()
            if len(code_str) >= 8:
                route_str = code_str[4:7]
                if route_str.isdigit():
                    route_num = int(route_str)
                    form_char = code_str[7].upper()
                    
                    if 1 <= route_num <= 399:
                        if form_char in 'ABCDE': return '内服薬（散・顆粒等）'
                        if form_char in 'FGHIJKL': return '内服薬（錠剤）'
                        if form_char in 'MNOP': return '内服薬（カプセル）'
                        if form_char in 'QRS': return '内服薬（液・シロップ等）'
                        return '内服薬（その他）'
                    elif 400 <= route_num <= 699:
                        return '注射薬'
                    elif 700 <= route_num <= 999:
                        return '外用薬'
            return '不明／その他'

        missing_form = missing_generic & (merged_df['剤形'].isna() | (merged_df['剤形'] == '不明／その他'))
        merged_df.loc[missing_form, '剤形'] = merged_df.loc[missing_form, '薬価基準収載医薬品コード'].apply(extract_form_from_yakkacode)

    if '剤形' not in merged_df.columns:
        merged_df['剤形'] = '不明／その他'
    else:
        merged_df['剤形'] = merged_df['剤形'].fillna('不明／その他')

    if '薬効分類名称' not in merged_df.columns:
        merged_df['薬効分類名称'] = '不明／その他'
    else:
        merged_df['薬効分類名称'] = merged_df['薬効分類名称'].fillna('不明／その他')

    sum_cols = [col for col in merged_df.columns if col == '総計(処方数量)' or str(col).startswith('男_') or str(col).startswith('女_')]

    agg_df = merged_df.groupby(['薬効分類名称', '一般名', '剤形'])[sum_cols].sum().reset_index()
    agg_df = agg_df.sort_values(by='総計(処方数量)', ascending=False)

    return agg_df

def format_number(x, pos):
    abs_x = abs(x)
    if abs_x >= 100000000:
        return f"{abs_x / 100000000:.1f}億".replace('.0億', '億')
    elif abs_x >= 10000:
        return f"{int(abs_x / 10000):,}万"
    else:
        return f"{int(abs_x):,}"

def plot_category_bar_chart(category_df, category_name, top_n=10):
    """指定された薬効分類内の一般名別処方数量を横並び棒グラフで描画します"""
    summed_df = category_df.groupby('一般名')['総計(処方数量)'].sum().reset_index()
    summed_df = summed_df.sort_values('総計(処方数量)', ascending=False).head(top_n)
    summed_df = summed_df.sort_values('総計(処方数量)', ascending=True)

    fig, ax = plt.subplots(figsize=(3, 3))
    ax.barh(summed_df['一般名'], summed_df['総計(処方数量)'], color='teal')
    ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_number))

    ax.tick_params(axis='x', labelsize=6)
    ax.tick_params(axis='y', labelsize=6)
    ax.set_xlabel('処方数量', fontsize=6)

    ax.set_title(f"【{category_name}】処方数量トップ{top_n}", fontsize=6)

    current_max = summed_df['総計(処方数量)'].max()
    if pd.notna(current_max) and current_max > 0:
        ax.set_xlim(0, current_max * 1.05)

    fig.subplots_adjust(left=0.35, right=0.95, top=0.9, bottom=0.1)
    st.pyplot(fig, width='content')

def plot_combined_pyramid(filtered_df, target_generic_name, selected_forms):
    """選択された剤形のデータを合算してピラミッドグラフを描画します"""
    summed_data = filtered_df.sum(numeric_only=True)
    total_count = summed_data.get('総計(処方数量)', 0)

    age_classes = [
        '0～4歳', '5～9歳', '10～14歳', '15～19歳', '20～24歳', '25～29歳', 
        '30～34歳', '35～39歳', '40～44歳', '45～49歳', '50～54歳', '55～59歳', 
        '60～64歳', '65～69歳', '70～74歳', '75～79歳', '80～84歳', '85～89歳', 
        '90～94歳', '95～99歳', '100歳以上'
    ]

    male_values = [summed_data.get(f"男_{age}", 0) for age in age_classes]
    female_values = [summed_data.get(f"女_{age}", 0) for age in age_classes]
    male_values_negative = [-val for val in male_values]

    fig, ax = plt.subplots(figsize=(4, 3))
    y_pos = range(len(age_classes))

    ax.barh(y_pos, male_values_negative, color='royalblue', label='男性')
    ax.barh(y_pos, female_values, color='lightcoral', label='女性')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(age_classes, fontsize=6)
    ax.tick_params(axis='x', labelsize=6)

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(format_number))

    ax.set_xlabel('処方数量', fontsize=6)
    ax.set_ylabel('年齢階級', fontsize=6)

    forms_str = " + ".join(selected_forms)
    ax.set_title(f"【{forms_str}】{target_generic_name}\n選択剤形の総処方数量：{total_count:,.0f}", fontsize=6)
    ax.legend(loc='best', fontsize=6)

    max_val = max(max(male_values, default=0), max(female_values, default=0))
    if max_val > 0:
        ax.set_xlim(-max_val * 1.1, max_val * 1.1)

    fig.tight_layout()
    st.pyplot(fig, width='content')

def main():
    st.set_page_config(page_title="処方データ分析", layout="wide")
    st.title("処方データ分析")

    st.caption("""第10回NDBオープンデータ（2023年度レセプト情報）の公費レセプトを含むデータから抽出・集計しています。「処方数量」は錠剤などの数量であり、処方回数とは必ずしも一致しません。内容の正確性には十分な注意を払っていますが、誤りを含む可能性があります。""")

    with st.spinner("データを読み込み中..."):
        df = load_and_process_data()

    if df.empty:
        st.warning("データが読み込めませんでした。")
        return

    st.sidebar.header("検索条件")

    if 'search_query' not in st.session_state:
        st.session_state.search_query = ""

    def clear_search():
        st.session_state.search_query = ""

    search_query = st.sidebar.text_input("🔍 一般名で検索 (部分一致)", key="search_query")
    is_category_all = False
    generic_df = pd.DataFrame()

    if search_query:
        st.sidebar.button("検索をクリア", on_click=clear_search)

        search_results = df[df['一般名'].str.contains(search_query, regex=False, na=False)]
        if search_results.empty:
            st.sidebar.warning("該当する一般名が見つかりませんでした。")
            return
        
        unique_search_generics = sorted(search_results['一般名'].unique())
        selected_generic = st.sidebar.selectbox("検索結果から一般名を選択", unique_search_generics)

        generic_df = df[df['一般名'] == selected_generic]

    else:
        unique_catergories = sorted(df['薬効分類名称'].dropna().unique())
        selected_category = st.sidebar.selectbox("1. 薬効分類を選択", unique_catergories)

        category_df = df[df['薬効分類名称'] == selected_category]

        unique_generics = ["すべて"] + sorted(category_df['一般名'].dropna().unique())
        selected_generic = st.sidebar.selectbox("2. 一般名を選択", unique_generics)

        if selected_generic == "すべて":
            is_category_all = True
        else:
            generic_df = category_df[category_df['一般名'] == selected_generic]

    col_left, col_right = st.columns([1, 3])

    if is_category_all:
        with col_left:
            st.markdown("#### 処方数量まとめ")
            total_sum = category_df['総計(処方数量)'].sum()
            st.metric(label="📊 分類全体の合計", value=f"{total_sum:,.0f}")
        with col_right:
            st.markdown("#### 医薬品別 処方数量トップ20")
            plot_category_bar_chart(category_df, selected_category)
    else:
        available_forms = generic_df['剤形'].unique()

        st.sidebar.write("3. 剤形を選択")
        selected_forms = []
        for form in available_forms:
            if st.sidebar.checkbox(form, value=True):
                selected_forms.append(form)

        if not selected_forms:
            st.info("← 左のメニューから剤形を1つ以上選択してください。")
            return
        
        filtered_df = generic_df[generic_df['剤形'].isin(selected_forms)]     

        with col_left:
            st.markdown("#### 処方数量まとめ")
            total_sum = 0
            for form in selected_forms:
                form_count = filtered_df[filtered_df['剤形'] == form]['総計(処方数量)'].sum()
                total_sum += form_count
                st.metric(label=f"💊 {form}", value=f"{form_count:,.0f}")
    
            st.divider()
            st.metric(label="📊 選択した剤形の合計", value=f"{total_sum:,.0f}")

        with col_right:
            st.markdown("#### 男女別・年齢階級別 処方数ピラミッド")
            plot_combined_pyramid(filtered_df, selected_generic, selected_forms)

if __name__ == "__main__":
    main()