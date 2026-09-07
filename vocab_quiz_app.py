# ターミナルで実行
# cd study_app
# python -m streamlit run vocab_quiz_app_v2.py

import time
import random
from datetime import date

import streamlit as st
from notion_client import Client

TOKEN = st.secrets["TOKEN"]
DATA_SOURCE_ID = st.secrets["DATA_SOURCE_ID"]
notion = Client(auth=TOKEN)

MASTERED_CORRECT_COUNT = 5
REVIEW_WRONG_COUNT = 3


def get_text_from_title(property_data):
    title_list = property_data.get("title", [])
    if not title_list:
        return ""
    return title_list[0].get("plain_text", "")


def get_text_from_rich_text(property_data):
    text_list = property_data.get("rich_text", [])
    if not text_list:
        return ""
    return text_list[0].get("plain_text", "")


def get_multi_select_names(property_data):
    items = property_data.get("multi_select", [])
    return [item.get("name", "") for item in items] if items else []


def get_number(property_data):
    number = property_data.get("number")
    return 0 if number is None else number


def get_date(property_data):
    date_data = property_data.get("date")
    return None if date_data is None else date_data.get("start")


@st.cache_data
def load_words_from_notion():
    all_results = []
    response = notion.data_sources.query(data_source_id=DATA_SOURCE_ID)
    all_results.extend(response["results"])

    while response.get("has_more"):
        response = notion.data_sources.query(
            data_source_id=DATA_SOURCE_ID,
            start_cursor=response["next_cursor"],
        )
        all_results.extend(response["results"])

    words = []
    for row in all_results:
        properties = row["properties"]
        word = get_text_from_title(properties["用語"])
        description = get_text_from_rich_text(properties["説明"])
        categories = get_multi_select_names(properties["種別"])
        correct_count = get_number(properties["正解数"])
        wrong_count = get_number(properties["不正解数"])
        learning_date = get_date(properties["学習日"])

        if not word or not description:
            continue

        words.append(
            {
                "page_id": row["id"],
                "word": word,
                "description": description,
                "categories": categories,
                "correct_count": correct_count,
                "wrong_count": wrong_count,
                "learning_date": learning_date,
            }
        )
    return words


def increment_count(page_id, property_name, current_count):
    notion.pages.update(
        page_id=page_id,
        properties={property_name: {"number": current_count + 1}},
    )


def update_learning_date(page_id):
    today = date.today().isoformat()
    notion.pages.update(
        page_id=page_id,
        properties={"学習日": {"date": {"start": today}}},
    )


def get_question_candidates(words):
    """正解数が5未満の用語だけを問題候補にする。"""
    return [
        item
        for item in words
        if item.get("correct_count", 0) < MASTERED_CORRECT_COUNT
    ]


def create_question(words):
    candidates = get_question_candidates(words)
    if not candidates:
        return None, []

    # 優先順位1: 学習日が空欄の用語
    unlearned_words = [
        item for item in candidates if item.get("learning_date") is None
    ]
    if unlearned_words:
        question = random.choice(unlearned_words)
    else:
        # 優先順位2: 不正解数が3以上の復習対象
        review_words = [
            item
            for item in candidates
            if item.get("wrong_count", 0) >= REVIEW_WRONG_COUNT
        ]
        if review_words:
            # 不正解数が多い順。同数なら学習日が古い順の上位から選ぶ。
            review_words.sort(
                key=lambda item: (
                    -item.get("wrong_count", 0),
                    item.get("learning_date") or "9999-12-31",
                )
            )
            highest_wrong_count = review_words[0]["wrong_count"]
            top_review_words = [
                item
                for item in review_words
                if item["wrong_count"] == highest_wrong_count
            ]
            oldest_date = min(item["learning_date"] for item in top_review_words)
            oldest_review_words = [
                item
                for item in top_review_words
                if item["learning_date"] == oldest_date
            ]
            question = random.choice(oldest_review_words)
        else:
            # 優先順位3: 学習日が古い用語
            oldest_date = min(item["learning_date"] for item in candidates)
            oldest_words = [
                item for item in candidates if item["learning_date"] == oldest_date
            ]
            question = random.choice(oldest_words)

    correct_word = question["word"]

    # 正解数5以上の用語も、問題そのものではなく誤答候補としては利用する。
    # これにより、問題候補が4件未満でも単語帳全体が4件以上なら4択を作れる。
    other_words = list(
        dict.fromkeys(
            item["word"] for item in words if item["word"] != correct_word
        )
    )
    if len(other_words) < 3:
        return question, []

    choices = random.sample(other_words, 3)
    choices.append(correct_word)
    random.shuffle(choices)
    return question, choices


def reset_question(words):
    question, choices = create_question(words)
    st.session_state.question = question
    st.session_state.choices = choices
    st.session_state.answered = False
    st.session_state.result = ""
    st.session_state.selected_answer = None


st.set_page_config(page_title="Notion単語クイズ", page_icon="📚")
st.title("📚 Notion単語クイズ")

st.markdown(
    """
    <style>
    [data-testid="stAppViewContainer"] {
        background-color: #f8fafc;
    }
    .stButton > button {
        border-radius: 6px;
        height: 50px;
        font-size: 18px;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

words = load_words_from_notion()

if len(words) < 4:
    st.error("4択クイズを作るには、用語と説明が入ったデータが4件以上必要です。")
    st.stop()

question_candidates = get_question_candidates(words)
mastered_count = len(words) - len(question_candidates)
unlearned_count = sum(
    1
    for item in question_candidates
    if item.get("learning_date") is None
)
review_count = sum(
    1
    for item in question_candidates
    if item.get("learning_date") is not None
    and item.get("wrong_count", 0) >= REVIEW_WRONG_COUNT
)
progress = mastered_count / len(words) if words else 0

for key, default_value in {
    "correct_count": 0,
    "wrong_count": 0,
    "answered": False,
    "result": "",
}.items():
    if key not in st.session_state:
        st.session_state[key] = default_value

if "question" not in st.session_state or "choices" not in st.session_state:
    reset_question(words)

st.markdown("### 学習進捗")
st.progress(progress)
st.write(f"🏆 習得済み: {mastered_count} / {len(words)}")
st.caption(
    f"未学習: {unlearned_count}件 | 優先復習: {review_count}件 | 出題対象: {len(question_candidates)}件"
)

col1, col2, col3 = st.columns(3)
session_total = st.session_state.correct_count + st.session_state.wrong_count
accuracy = (
    round(st.session_state.correct_count / session_total * 100, 1)
    if session_total > 0
    else 0
)
with col1:
    st.metric("今回の正解", st.session_state.correct_count)
with col2:
    st.metric("今回の不正解", st.session_state.wrong_count)
with col3:
    st.metric("今回の正解率", f"{accuracy}%")

st.write("Notionの単語帳データを使って、4択クイズを出題します。")
st.success(f"読み込み成功: {len(words)}件の単語を取得しました。")

if not question_candidates:
    st.balloons()
    st.success("すべての用語が正解数5回に到達しました。全問習得です！")
    st.stop()

question = st.session_state.question
choices = st.session_state.choices

if question is None:
    st.info("現在、出題対象の用語はありません。")
    st.stop()

if len(choices) < 4:
    st.error("4択を作るための重複しない用語が不足しています。")
    st.stop()

st.divider()
st.subheader("問題")
st.markdown(
    f"""
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
    <div style="margin-bottom:30px;"></div>
    """,
    unsafe_allow_html=True,
)

answer = st.radio(
    "正しい用語を選んでください",
    choices,
    key="selected_answer",
    disabled=st.session_state.answered,
)

col1,  = st.columns(1)
with col1:
    if st.button(
        "回答する",
        key="answer_button",
        disabled=st.session_state.answered,
        use_container_width=True,
    ):
        st.session_state.answered = True
        if answer == question["word"]:
            st.session_state.result = "正解！"
            st.session_state.correct_count += 1
            increment_count(
                page_id=question["page_id"],
                property_name="正解数",
                current_count=question["correct_count"],
            )
            update_learning_date(page_id=question["page_id"])
        else:
            st.session_state.result = (
                f"不正解…正解は「{question['word']}」です。"
            )
            st.session_state.wrong_count += 1
            increment_count(
                page_id=question["page_id"],
                property_name="不正解数",
                current_count=question["wrong_count"],
            )

if st.session_state.answered:
    if st.session_state.result.startswith("正解"):
        st.success(st.session_state.result)
        if question["correct_count"] + 1 >= MASTERED_CORRECT_COUNT:
            st.info("この用語は正解数5回に到達したため、次回から問題対象外です。")
    else:
        st.error(st.session_state.result)
        if question["wrong_count"] + 1 >= REVIEW_WRONG_COUNT:
            st.warning("不正解数が3回以上になったため、優先復習の対象です。")

#1.5秒後に自動で次の問題
    time.sleep(1.0)

    st.cache_data.clear()
    refreshed_words = load_words_from_notion()
    reset_question(refreshed_words)

    st.rerun()
