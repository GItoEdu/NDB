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

    # 一般名の補完
    missing_generic = merged_df['一般名'].isna()
    merged_df.loc[missing_generic, '一般名'] = '※未登録：' + merged_df.loc[missing_generic, '医薬品名']

    if '剤形' not in merged_df.columns:
        merged_df['剤形'] = '不明／その他'

    if '薬効分類名称' not in merged_df.columns:
        merged_df['薬効分類名称'] = '不明／その他'
    else:
        merged_df['薬効分類名称'] = merged_df['薬効分類名称'].fillna('不明／その他')

    sum_cols = [col for col in merged_df.columns if col == '総計(処方数量)' or str(col).startswith('男_') or str(col).startswith('女_')]

    agg_df = merged_df.groupby(['薬効分類名称', '一般名', '剤形'])[sum_cols].sum().reset_index()
    agg_df = agg_df.sort_values(by='総計(処方数量)', ascending=False)

    return agg_df

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

    fig, ax = plt.subplots(figsize=(10, 8))
    y_pos = range(len(age_classes))

    ax.barh(y_pos, male_values_negative, color='royalblue', label='男性')
    ax.barh(y_pos, female_values, color='lightcoral', label='女性')

    ax.set_yticks(y_pos)
    ax.set_yticklabels(age_classes)

    ax.xaxis.set_major_formatter(ticker.FuncFormatter(lambda x, pos: f"{abs(int(x)):,}"))

    ax.set_xlabel('処方数量')
    ax.set_ylabel('年齢階級')

    forms_str = " + ".join(selected_forms)
    ax.set_title(f"【{forms_str}】{target_generic_name}\n選択剤形の総処方数量：{total_count:,.0f}", fontsize=14)
    ax.legend(loc='upper right')

    max_val = max(max(male_values, default=0), max(female_values, default=0))
    if max_val > 0:
        ax.set_xlim(-max_val * 1.1, max_val * 1.1)

    fig.tight_layout()
    st.pyplot(fig)

def main():
    st.set_page_config(page_title="処方データ分析ダッシュボード", layout="wide")
    st.title("処方データ分析ダッシュボード")

    with st.spinner("データを読み込み中..."):
        df = load_and_process_data()

    if df.empty:
        st.warning("データが読み込めませんでした。")
        return
    
    st.sidebar.header("検索条件")

    unique_catergories = sorted(df['薬効分類名称'].dropna().unique())
    selected_categories = st.sidebar.selectbox("1. 薬効分類を選択してください", unique_catergories)

    category_df = df[df['薬効分類名称'] == selected_categories]

    unique_generics = sorted(category_df['一般名'].dropna().unique())
    selected_generic = st.sidebar.selectbox("2. 一般名を選択してください", unique_generics)

    generic_df = category_df[category_df['一般名'] == selected_generic]
    available_forms = generic_df['剤形'].unique()

    st.sidebar.subheader("3. 剤形を選択")
    selected_forms = []
    for form in available_forms:
        if st.sidebar.checkbox(form, value=True):
            selected_forms.append(form)
    
    st.subheader(f"■ {selected_generic} の処方状況")

    if not selected_forms:
        st.info("← 左のメニューから剤形を1つ以上選択してください。")
        return
    
    filtered_df = generic_df[generic_df['剤形'].isin(selected_forms)]

    st.markdown("### 処方数量まとめ")
    cols = st.columns(len(selected_forms) + 1)

    total_sum = 0
    for i, form in enumerate(selected_forms):
        form_count = filtered_df[filtered_df['剤形'] == form]['総計(処方数量)'].sum()
        total_sum += form_count
        cols[i].metric(label=f"💊 {form}", value=f"{form_count:,.0f}")
    
    cols[-1].metric(label="📊 選択した剤形の合計", value=f"{total_sum:,.0f}")
    st.divider()

    st.markdown("### 男女別・年齢階級別 処方数ピラミッド")
    plot_combined_pyramid(filtered_df, selected_generic, selected_forms)

if __name__ == "__main__":
    main()