#ターミナルで入力
#cd study_app
#python -m streamlit run app.py

import random
import streamlit as st
from notion_client import Client
from datetime import date


token = st.secrets["TOKEN"]
source_id = st.secrets["DATA_SOURCE_ID"]


notion = Client(auth = token)


#関数設定
def get_text_from_title(property_data):
    title_list = property_data.get("title",[])

    if not title_list:
        return ""

    return title_list[0].get("plain_text", "")

def get_text_from_rich_text(property_data):
    text_list = property_data.get("rich_text",[])

    if not text_list:
        return ""

    return text_list[0].get("plain_text","")

def get_multi_select_names(property_data):
    items = property_data.get("multi_select",[])

    if not items:
        return []

    return [item.get("name", "") for item in items]

def get_number(property_data):
    number = property_data.get("number")

    if number is None:
        return 0

    return number

def get_date(property_data):
    date_data = property_data.get("date")

    if date_data is None:
        return None

    return date_data.get("start")



@st.cache_data
def load_words_from_notion():

    all_results = []

    response = notion.data_sources.query(
        data_source_id=source_id
    )

    all_results.extend(response["results"])

    while response.get("has_more"):

        response = notion.data_sources.query(
            data_source_id=source_id,
            start_cursor=response["next_cursor"]
        )

        all_results.extend(response["results"])



    words = []

    for row in all_results:

        properties = row["properties"]

        word = get_text_from_title(properties["用語"])
        description = get_text_from_rich_text(properties["説明"])
        categories = get_multi_select_names(properties["種別"])
        wrong_count = get_number(properties["数値"])
        learning_date = get_date(properties["学習日"])

        if not word or not description:
            continue

        words.append({
            "page_id": row["id"],
            "word": word,
            "description": description,
            "categories": categories,
            "wrong_count": wrong_count,
            "learning_date": learning_date
        })

    return words



def update_wrong_count(page_id, current_wrong_count):
    notion.pages.update(
        page_id=page_id,
        properties={
            "数値": {
                "number": current_wrong_count + 1
            }
        }
    )


def update_learning_date(page_id):
    today = date.today().isoformat()

    notion.pages.update(
        page_id=page_id,
        properties={"学習日": {"date": {"start": today}}}
    )


def create_question(words):

    #学習日が空欄の単語を抽出
    unlearned_words = [
        item
        for item in words
        if item.get("learning_date") is None
    ]

    #学習日が空欄の問題があれば優先出題
    if len(unlearned_words) > 0:

        question = random.choice(unlearned_words)

    else:
        sorted_words = sorted(words, key=lambda x: x["learning_date"])
        question = random.choice(sorted_words[:20])
        

    correct_word = question["word"]

    other_words = [
        item["word"]
        for item in words
        if item["word"] != correct_word
    ]

    choices = random.sample(other_words, 3)

    choices.append(correct_word)

    random.shuffle(choices)

    return question, choices



# streamlit画面
st.title("Notion単語クイズ")

#CSSでデザイン
st.markdown("""
<style>

/* 全体背景 */
[data-testid="stAppViewContainer"] {
    background-color: #f8fafc;
}

/* ボタン */
.stButton > button {
    border-radius: 12px;
    height: 50px;
    font-size: 18px;
    font-weight: bold;
}

</style>
""", unsafe_allow_html=True)

#初期化
words= load_words_from_notion()


unlearned_count = len([
    item
    for item in words
    if item["learning_date"] is None
])

learned_count = len(words) - unlearned_count

progress = (
    learned_count / len(words)
    if len(words) > 0
    else 0
)


if "correct_count" not in st.session_state:
    st.session_state.correct_count = 0
if "wrong_count" not in st.session_state:
    st.session_state.wrong_count = 0

if "answered" not in st.session_state:
    st.session_state.answered = False
if "question" not in st.session_state:
    question, choices = create_question(words)
if "result" not in st.session_state:
    st.session_state.result = ""

    st.session_state.question = question
    st.session_state.choices = choices



total = (st.session_state.correct_count + st.session_state.wrong_count)
accurary = (round(st.session_state.correct_count / total * 100, 1)
            if total > 0
            else 0
            )

st.markdown("### 学習進捗")
st.progress(progress)

st.write(
    f"📚学習済: {learned_count} / {len(words)}"
)

col1, col2, col3 = st.columns(3)

with col1:
    st.metric(
        "正解", st.session_state.correct_count
    )
with col2:
    st.metric(
        "不正解", st.session_state.wrong_count
        )
with col3:
    st.metric(
        "正解率", f"{accurary}%"
    )

st.write("Notionの単語帳データを使って、4択クイズを出題します。")



if len(words) < 4:
    st.error("4択クイズを作るには、用語と説明が入ったデータが4件以上必要です。")
    st.stop()

st.success(f"読み込み成功:{len(words)}件の単語を取得しました。")


if "question" not in st.session_state:
    quesition, choices = create_question(words)
    st.session_state["question"] = quesition
    st.session_state["choices"] = choices
    st.session_state_answered = False

question = st.session_state.question
choices = st.session_state.choices

st.divider()

st.subheader("問題")

st.markdown(f"""
<div style="
    background-color:#191970;
    color:#f8fafc;
    padding:15px;
    border-radius:6px;
    font-size:20px;
    font-weight:normal;
">
{question["description"]}
</div>
""", unsafe_allow_html=True)

st.markdown("""
<div style=
    margin-bottom:30px;
">
</div>
""", unsafe_allow_html=True)

answer = st.radio(
    "正しい用語を選んでください",
    choices,
    key="answer"
)

#回答ボタン、次の問題へボタン
col1, col2 = st.columns(2)

with col1:
    if st.button("回答する", key="answer_button"):

        st.session_state.answered = True

        if answer == question["word"]:
            st.session_state.result = "正解！"
            st.session_state.correct_count += 1

            update_learning_date(page_id=question["page_id"])

        else:
            st.session_state.result = (f"不正解…正解は「{question['word']}」です。")
            st.session_state.wrong_count += 1

            update_wrong_count(
                page_id=question["page_id"],
                current_wrong_count=question["wrong_count"]
            )

            st.warning("Notionの数値列を+1しました。")

if st.session_state.answered:

    if st.session_state.result.startswith("正"):
        st.success(st.session_state.result)

    else:
        st.error(st.session_state.result)


with col2:
    if st.button("次の問題へ", key="next_button", disabled=not st.session_state.get("answered", False)):
        question, choices = create_question(words)
        st.session_state.question = question
        st.session_state.choices = choices
        st.session_state.answered = False
        st.session_state.result = ""

        st.cache_data.clear()

        st.rerun()