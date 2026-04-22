import math
from collections import deque
from pathlib import Path

import openpyxl
import streamlit as st

st.set_page_config(page_title="브랜드별 단가계산기", page_icon="🧮", layout="centered")

SHEET_NAME = "거래처DB"
VENDOR_START_ROW = 3
VENDOR_END_ROW = 63
DATA_FILE_CANDIDATES = [
    "업무리스트.xlsx",
    "업무리스트 (1).xlsx",
]


def find_data_file() -> Path:
    base_dir = Path(__file__).parent
    for filename in DATA_FILE_CANDIDATES:
        candidate = base_dir / filename
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "엑셀 파일을 찾지 못했습니다. 업무리스트.xlsx 또는 업무리스트 (1).xlsx 파일을 앱 폴더에 넣어주세요."
    )


def normalize_text(value):
    if value is None:
        return ""
    return "".join(str(value).split()).lower()


@st.cache_data
def load_vendor_data(file_path_str: str):
    file_path = Path(file_path_str)
    workbook = openpyxl.load_workbook(file_path, read_only=True, data_only=True)
    try:
        if SHEET_NAME not in workbook.sheetnames:
            raise ValueError(f"'{SHEET_NAME}' 시트를 찾지 못했습니다.")

        ws = workbook[SHEET_NAME]
        rows = []
        for row in range(VENDOR_START_ROW, VENDOR_END_ROW + 1):
            vendor_name = ws[f"A{row}"].value
            rule_text = ws[f"F{row}"].value

            vendor_name = "" if vendor_name is None else str(vendor_name).strip()
            rule_text = "" if rule_text is None else str(rule_text).strip()

            if vendor_name:
                rows.append({"거래처": vendor_name, "기준정보": rule_text})
        return rows
    finally:
        workbook.close()



def round_up_to_10000(value):
    return int(math.ceil(value / 10000.0) * 10000)



def won(value):
    return f"{int(round(value)):,}원"



def calculate_values(x_value, c_value):
    purchase_price = x_value / 2
    markup_price = purchase_price * 1.4
    difference = purchase_price - c_value
    selling_price = c_value * 1.1
    return {
        "매입가": purchase_price,
        "1.4배": markup_price,
        "상품가": c_value,
        "차액": difference,
        "판매가": selling_price,
    }



def push_history(entry):
    history = st.session_state.setdefault("calc_history", deque(maxlen=5))
    history.appendleft(entry)



def render_history():
    history = list(st.session_state.get("calc_history", []))
    st.markdown("### 최근 계산 결과")
    if not history:
        st.caption("아직 저장된 계산 결과가 없습니다.")
        return

    for idx, item in enumerate(history, start=1):
        with st.expander(f"{idx}. {item['거래처']} / x={won(item['x'])}", expanded=(idx == 1)):
            st.write(f"**기준정보:** {item['기준정보']}")
            if item["보정값"] > 0:
                st.markdown(
                    f"<p style='color:red; font-weight:700;'>자동 보정 반영: {won(item['보정값'])}</p>",
                    unsafe_allow_html=True,
                )
            else:
                st.write("자동 보정 없음")

            col1, col2 = st.columns(2)
            with col1:
                st.metric("매입가", won(item["매입가"]))
                st.metric("1.4배", won(item["1.4배"]))
                st.metric("상품가", won(item["상품가"]))
            with col2:
                st.metric("차액", won(item["차액"]))
                st.metric("판매가", won(item["판매가"]))


# 초기 상태
if "saved_signature" not in st.session_state:
    st.session_state["saved_signature"] = None

try:
    data_file = find_data_file()
    vendor_rows = load_vendor_data(str(data_file))
except Exception as exc:
    st.error(f"데이터를 불러오는 중 오류가 발생했습니다: {exc}")
    st.stop()

if not vendor_rows:
    st.error("거래처 데이터를 찾지 못했습니다. 엑셀 범위(A3:A63, F3:F63)를 확인해 주세요.")
    st.stop()

st.title("브랜드별 단가계산기")
st.caption("거래처명을 일부 입력해서 선택하고, 계산 가능 여부를 바로 확인할 수 있습니다.")
st.caption(f"현재 데이터 파일: {data_file.name}")

search_text = st.text_input("거래처 검색", placeholder="예: FM, 꼬모도, 현대컴퍼니")
search_keyword = search_text.strip().lower()

if search_keyword:
    filtered_rows = [
        row for row in vendor_rows
        if search_keyword in row["거래처"].lower()
    ]
else:
    filtered_rows = vendor_rows[:]

if not filtered_rows:
    st.warning("검색 결과가 없습니다. 다른 키워드로 다시 검색해 주세요.")
    render_history()
    st.stop()

selected_vendor = st.selectbox(
    "거래처 선택",
    [row["거래처"] for row in filtered_rows],
    index=0,
)
selected_row = next(row for row in vendor_rows if row["거래처"] == selected_vendor)
rule_text = selected_row["기준정보"]
normalized_rule = normalize_text(rule_text)

st.markdown("### 선택된 거래처 정보")
st.write(f"**거래처명:** {selected_vendor}")
st.write(f"**F열 기준정보:** {rule_text if rule_text else '(빈칸)'}")

if "반값x1.4" not in normalized_rule:
    st.info("이 거래처는 자동 계산 대상이 아닙니다.")
    if rule_text:
        st.write(f"해당 기준정보: **{rule_text}**")
    else:
        st.write("해당 기준정보: **빈칸**")
    render_history()
    st.stop()

st.success("이 거래처는 `반값 x1.4` 규칙으로 계산할 수 있습니다.")

x_value = st.number_input("x 입력", min_value=0, value=0, step=1000)

purchase_price = x_value / 2
markup_price = purchase_price * 1.4
base_product_price = round_up_to_10000(markup_price)
base_difference = purchase_price - base_product_price
adjustment_needed = 30000 - base_difference

st.markdown("### 계산 결과")

if adjustment_needed > 0:
    auto_adjusted_c = base_product_price + adjustment_needed
    st.markdown(
        f"<p style='color:red; font-weight:700;'>30000 - 차액 = {won(adjustment_needed)} → 상품가에 자동으로 더해졌습니다.</p>",
        unsafe_allow_html=True,
    )
    c_value = st.number_input(
        "상품가 (수정 가능)",
        min_value=0,
        value=int(auto_adjusted_c),
        step=10000,
        help="필요 보정값이 자동 반영되어 있으며, 직접 수정할 수 있습니다.",
    )
else:
    c_value = int(base_product_price)
    st.number_input(
        "상품가 (수정 불가)",
        min_value=0,
        value=int(base_product_price),
        step=10000,
        disabled=True,
    )

result = calculate_values(x_value, c_value)

col1, col2 = st.columns(2)
with col1:
    st.metric("매입가", won(result["매입가"]))
    st.metric("1.4배", won(result["1.4배"]))
    st.metric("상품가", won(result["상품가"]))
with col2:
    st.metric("차액", won(result["차액"]))
    st.metric("판매가", won(result["판매가"]))

current_signature = (
    selected_vendor,
    rule_text,
    int(x_value),
    int(c_value),
    int(result["차액"]),
    int(adjustment_needed if adjustment_needed > 0 else 0),
)

if st.button("현재 계산 결과 저장"):
    if st.session_state.get("saved_signature") != current_signature:
        push_history(
            {
                "거래처": selected_vendor,
                "기준정보": rule_text if rule_text else "(빈칸)",
                "x": int(x_value),
                "보정값": int(adjustment_needed if adjustment_needed > 0 else 0),
                **{k: int(v) for k, v in result.items()},
            }
        )
        st.session_state["saved_signature"] = current_signature
        st.success("최근 계산 결과에 저장했습니다.")
    else:
        st.info("같은 계산 결과는 이미 저장되어 있습니다.")

render_history()

with st.expander("계산식 보기"):
    st.write("A = x / 2")
    st.write("B = (x / 2) × 1.4")
    st.write("C = B를 10,000원 단위 올림")
    st.write("D = A - C")
    st.write("E = C × 1.1")
