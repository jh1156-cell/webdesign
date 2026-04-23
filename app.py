import math
import re
from pathlib import Path

import pandas as pd
import streamlit as st

st.set_page_config(page_title="브랜드별 단가 계산기", page_icon="🧮", layout="wide")

DATA_CANDIDATES = ["업무리스트.xlsx", "업무리스트 (1).xlsx"]
DB_SHEET_NAME = "거래처DB"
NAME_START_ROW = 3
NAME_END_ROW = 63


def normalize_text(value):
    if pd.isna(value):
        return ""
    return re.sub(r"\s+", "", str(value)).strip().lower()


def ceil_to_10000(value):
    return int(math.ceil(float(value) / 10000.0) * 10000)


def format_currency(value):
    return f"{int(round(float(value))):,}원"


@st.cache_data(show_spinner=False)
def load_vendor_db():
    existing_path = None
    for candidate in DATA_CANDIDATES:
        path = Path(candidate)
        if path.exists():
            existing_path = path
            break
    if existing_path is None:
        raise FileNotFoundError("업무리스트.xlsx 파일을 찾을 수 없습니다.")

    df = pd.read_excel(
        existing_path,
        sheet_name=DB_SHEET_NAME,
        usecols="A:H",
        header=None,
        engine="openpyxl",
    )
    sliced = df.iloc[NAME_START_ROW - 1:NAME_END_ROW].copy()
    sliced = sliced[[0, 5, 7]]
    sliced.columns = ["거래처", "기준", "비고"]
    for col in ["거래처", "기준", "비고"]:
        sliced[col] = sliced[col].fillna("").astype(str).str.strip()
    sliced = sliced[sliced["거래처"] != ""].reset_index(drop=True)
    return sliced, str(existing_path)


def detect_rule(raw_rule):
    normalized = normalize_text(raw_rule)
    if "프로젝트가x1.5+2만원" in normalized:
        return "project_15_plus_20k"
    if "국내제작x1.5+4만원" in normalized:
        return "domestic_15_plus_40k"
    if "국내제작x1.5" in normalized:
        return "domestic_15"
    if "(mat)한국ta" in normalized or "mat한국ta" in normalized:
        return "mat_korea_ta"
    if "상품코드뒤3자리x1.4" in normalized or "상품코드단가x1.4" in normalized:
        return "product_code_last3_14"
    if "단가x1.4" in normalized:
        return "unit_14"
    if "반값x1.4" in normalized or "(반값+배송비)x1.4권장판매가기준" in normalized:
        return "half_14"
    return None


def get_input_meta(rule_key):
    if rule_key in {"domestic_15", "domestic_15_plus_40k"}:
        return "국내제작(전달받은 금액으로)", "#d32f2f"
    if rule_key == "project_15_plus_20k":
        return "프로젝트가", "#1976d2"
    if rule_key == "unit_14":
        return "단가", "#222222"
    if rule_key in {"mat_korea_ta", "product_code_last3_14"}:
        return "상품코드", "#d32f2f"
    return "거래처가구가격", "#222222"


def build_margin_adjusted_result(rule_title, multiplied, base_product_price):
    min_gap = 30000
    gap = base_product_price - multiplied
    added_gap = max(0, min_gap - gap)
    final_product_price = base_product_price + added_gap
    difference = final_product_price - multiplied
    sale_price = final_product_price * 1.1
    extra_sale_from_gap = added_gap * 1.1
    return {
        "A_label": "1.4배",
        "A": multiplied,
        "base_product_label": "기본 상품가",
        "base_product_price": base_product_price,
        "B_label": "상품가",
        "B": final_product_price,
        "D_label": "차액",
        "D": difference,
        "E_label": "판매가",
        "E": sale_price,
        "added_gap": added_gap,
        "extra_sale_from_gap": extra_sale_from_gap,
        "rule_title": rule_title,
    }


def compute_values(rule_key, x_value, final_product_price_override=None):
    if rule_key == "half_14":
        purchase_price = x_value / 2
        multiplier_value = purchase_price * 1.4
        base_product_price = ceil_to_10000(multiplier_value)
        min_gap = 30000
        gap = base_product_price - purchase_price
        added_gap = max(0, min_gap - gap)
        suggested_product_price = base_product_price + added_gap
        final_product_price = suggested_product_price if final_product_price_override is None else final_product_price_override
        difference = final_product_price - purchase_price
        sale_price = final_product_price * 1.1
        extra_sale_from_gap = added_gap * 1.1
        return {
            "A_label": "매입가",
            "A": purchase_price,
            "B_label": "1.4배",
            "B": multiplier_value,
            "base_product_label": "기본 상품가",
            "base_product_price": base_product_price,
            "product_label": "상품가",
            "C": final_product_price,
            "D_label": "차액",
            "D": difference,
            "E_label": "판매가",
            "E": sale_price,
            "added_gap": added_gap,
            "extra_sale_from_gap": extra_sale_from_gap,
            "editable_product_price": added_gap > 0,
            "rule_title": "반값 x1.4",
        }

    if rule_key == "domestic_15":
        multiplied = x_value * 1.5
        product_price = ceil_to_10000(multiplied)
        return {
            "A_label": "1.5배",
            "A": multiplied,
            "B_label": "상품가",
            "B": product_price,
            "D_label": "차액",
            "D": product_price - multiplied,
            "E_label": "판매가",
            "E": product_price * 1.1,
            "rule_title": "국내제작 x1.5",
        }

    if rule_key == "domestic_15_plus_40k":
        multiplied = x_value * 1.5
        rounded = ceil_to_10000(multiplied)
        product_price = rounded + 40000
        return {
            "A_label": "1.5배",
            "A": multiplied,
            "B_label": "만원단위 올림",
            "B": rounded,
            "C_label": "상품가",
            "C": product_price,
            "D_label": "차액",
            "D": product_price - multiplied,
            "E_label": "판매가",
            "E": product_price * 1.1,
            "rule_title": "국내제작 x1.5 + 4만원",
        }

    if rule_key == "project_15_plus_20k":
        multiplied = x_value * 1.5
        rounded = ceil_to_10000(multiplied)
        product_price = rounded + 20000
        return {
            "A_label": "1.5배",
            "A": multiplied,
            "B_label": "만원단위 올림",
            "B": rounded,
            "C_label": "상품가",
            "C": product_price,
            "D_label": "차액",
            "D": product_price - multiplied,
            "E_label": "판매가",
            "E": product_price * 1.1,
            "rule_title": "프로젝트가 x1.5 + 2만원",
        }

    if rule_key == "unit_14":
        multiplied = x_value * 1.4
        product_price = ceil_to_10000(multiplied)
        return {
            "A_label": "1.4배",
            "A": multiplied,
            "B_label": "상품가",
            "B": product_price,
            "D_label": "차액",
            "D": product_price - multiplied,
            "E_label": "판매가",
            "E": product_price * 1.1,
            "rule_title": "단가 x1.4",
        }

    if rule_key == "mat_korea_ta":
        multiplied = x_value * 1.4
        base_product_price = ceil_to_10000(multiplied)
        return build_margin_adjusted_result("(MAT) 한국TA", multiplied, base_product_price)

    if rule_key == "product_code_last3_14":
        multiplied = x_value * 1.4
        base_product_price = ceil_to_10000(multiplied)
        return build_margin_adjusted_result("상품코드 뒤 3자리 x1.4 / 상품코드 단가 x1.4", multiplied, base_product_price)

    raise ValueError("지원하지 않는 계산식입니다.")


def extract_price_from_product_code(code_text, mode="mat"):
    cleaned = re.sub(r"\s+", "", str(code_text)).upper()
    if mode == "mat":
        if len(cleaned) < 6:
            return None
        segment = cleaned[3:6]
    elif mode == "last3":
        if len(cleaned) < 3:
            return None
        segment = cleaned[-3:]
    else:
        return None
    if not segment.isdigit():
        return None
    return int(segment) * 1000


def save_history(entry):
    history = st.session_state.get("calc_history", [])
    history.insert(0, entry)
    st.session_state["calc_history"] = history[:5]


def render_history():
    history = st.session_state.get("calc_history", [])
    st.subheader("최근 계산 결과")
    if not history:
        st.info("아직 저장된 계산 결과가 없습니다.")
        return
    for idx, item in enumerate(history, start=1):
        with st.expander(f"{idx}. {item['거래처']} · {item['계산식']} · {item['판매가']}", expanded=False):
            c1, c2, c3 = st.columns(3)
            c1.markdown(f"**입력값**  \n{item['입력명']}: {item['입력값']}")
            c2.markdown(f"**상품가**  \n{item['상품가']}")
            c3.markdown(f"**판매가**  \n{item['판매가']}")
            st.caption(f"정보: {item['기준문구']}")
            st.caption(f"비고: {item['비고']}")


def main():
    st.title("브랜드별 단가 계산기")
    st.caption("거래처를 검색해서 선택하면, 거래처별 정보에 맞춰 계산식을 자동 적용합니다.")

    try:
        vendor_df, loaded_path = load_vendor_db()
    except Exception as e:
        st.error(f"엑셀 파일을 읽지 못했습니다: {e}")
        st.stop()

    st.caption(f"불러온 파일: {loaded_path}")

    search_text = st.text_input("거래처 검색", placeholder="거래처 이름 일부를 입력하세요.")
    filtered = vendor_df
    if search_text.strip():
        filtered = vendor_df[vendor_df["거래처"].str.contains(search_text.strip(), case=False, na=False)]

    vendor_names = filtered["거래처"].tolist()
    if not vendor_names:
        st.warning("검색 결과가 없습니다.")
        render_history()
        st.stop()

    selected_vendor = st.selectbox("거래처 선택", vendor_names)
    selected_row = filtered[filtered["거래처"] == selected_vendor].iloc[0]
    raw_rule = selected_row["기준"]
    note_text = selected_row["비고"]
    rule_key = detect_rule(raw_rule)

    st.markdown("### 거래처 기준")
    st.write(f"**거래처:** {selected_vendor}")
    st.write(f"**정보:** {raw_rule if str(raw_rule).strip() else '(빈칸)'}")
    st.write(f"**비고:** {note_text if str(note_text).strip() else '(빈칸)'}")

    if rule_key is None:
        st.info("이 거래처는 자동 계산 대상이 아닙니다. 위 정보를 확인해주세요.")
        render_history()
        st.stop()

    input_label, input_color = get_input_meta(rule_key)
    st.markdown(
        f"""
        <style>
        div[data-testid="stNumberInput"] label p {{
            font-weight: 700;
        }}
        .input-label {{
            color: {input_color};
            font-weight: 800;
            font-size: 1rem;
            margin-bottom: 0.25rem;
        }}
        .result-card {{
            border: 2px solid #e5e7eb;
            border-radius: 16px;
            padding: 1.2rem 1.4rem;
            background: #ffffff;
            margin-bottom: 1rem;
        }}
        .sale-card {{
            border: 2px solid #111827;
            border-radius: 18px;
            padding: 1.4rem 1.6rem;
            background: #f8fafc;
            margin-bottom: 1rem;
        }}
        .sale-card .title {{
            font-size: 1rem;
            font-weight: 700;
            color: #374151;
            margin-bottom: 0.3rem;
        }}
        .sale-card .value {{
            font-size: 2.1rem;
            font-weight: 800;
            color: #111827;
        }}
        .warn {{
            color: #d32f2f;
            font-weight: 800;
        }}
        </style>
        """,
        unsafe_allow_html=True,
    )

    st.markdown(f'<div class="input-label">{input_label}</div>', unsafe_allow_html=True)
    code_text = None
    if rule_key in {"mat_korea_ta", "product_code_last3_14"}:
        placeholder = "예: TOC045P810" if rule_key == "mat_korea_ta" else "예: 658047 / ICL0135"
        code_text = st.text_input(label="", placeholder=placeholder, key=f"code_input_{rule_key}_{selected_vendor}")
        mode = "mat" if rule_key == "mat_korea_ta" else "last3"
        x_value = extract_price_from_product_code(code_text, mode=mode) if code_text.strip() else 0
        if code_text.strip() and x_value is None:
            if rule_key == "mat_korea_ta":
                st.error("상품코드의 4번째부터 6번째 문자가 숫자여야 합니다. 예: TOC045P810")
            else:
                st.error("상품코드 마지막 3자리가 숫자여야 합니다. 예: 658047 / ICL0135")
            render_history()
            st.stop()
        if x_value:
            st.caption(f"인식한 금액: {format_currency(x_value)}")
    else:
        x_value = st.number_input(
            label="",
            min_value=0,
            step=1000,
            value=0,
            format="%d",
            key=f"x_input_{rule_key}_{selected_vendor}",
        )

    final_product_price_override = None
    if rule_key == "half_14" and x_value > 0:
        preview = compute_values(rule_key, x_value)
        if preview["editable_product_price"]:
            final_product_price_override = st.number_input(
                "상품가 직접 수정",
                min_value=int(preview["base_product_price"]),
                step=10000,
                value=int(preview["C"]),
                format="%d",
                key=f"editable_c_{selected_vendor}",
            )
        else:
            st.number_input(
                "상품가 직접 수정",
                min_value=int(preview["C"]),
                step=10000,
                value=int(preview["C"]),
                format="%d",
                key=f"editable_c_locked_{selected_vendor}",
                disabled=True,
            )
            final_product_price_override = preview["C"]

    if x_value is None or x_value <= 0:
        render_history()
        st.stop()

    results = compute_values(rule_key, x_value, final_product_price_override)

    st.markdown(
        f"""
        <div class="sale-card">
            <div class="title">최종 판매가</div>
            <div class="value">{format_currency(results['E'])}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )

    if rule_key in {"half_14", "mat_korea_ta", "product_code_last3_14"}:
        if results.get("added_gap", 0) > 0:
            st.markdown(
                f'<div class="warn">차액이 30,000원 미만이라 상품가에 {format_currency(results["added_gap"])} 를 더했습니다.</div>',
                unsafe_allow_html=True,
            )
            st.markdown(
                f'<div class="warn">판매가에도 추가 반영된 금액: {format_currency(results["extra_sale_from_gap"])} </div>',
                unsafe_allow_html=True,
            )
        else:
            st.success("차액이 30,000원 이상이라 자동 보정 없이 계산되었습니다.")

    st.markdown('<div class="result-card">', unsafe_allow_html=True)
    st.markdown("### 계산 결과")
    if rule_key == "half_14":
        st.write(f"**{results['A_label']}**: {format_currency(results['A'])}")
        st.write(f"**{results['B_label']}**: {format_currency(results['B'])}")
        st.write(f"**{results['base_product_label']}**: {format_currency(results['base_product_price'])}")
        st.write(f"**{results['product_label']}**: {format_currency(results['C'])}")
        st.write(f"**{results['D_label']}**: {format_currency(results['D'])}")
        st.write(f"**{results['E_label']}**: {format_currency(results['E'])}")
    elif rule_key in {"domestic_15", "unit_14"}:
        st.write(f"**{results['A_label']}**: {format_currency(results['A'])}")
        st.write(f"**{results['B_label']}**: {format_currency(results['B'])}")
        st.write(f"**{results['D_label']}**: {format_currency(results['D'])}")
        st.write(f"**{results['E_label']}**: {format_currency(results['E'])}")
    elif rule_key in {"mat_korea_ta", "product_code_last3_14"}:
        st.write(f"**{results['A_label']}**: {format_currency(results['A'])}")
        st.write(f"**{results['base_product_label']}**: {format_currency(results['base_product_price'])}")
        st.write(f"**{results['B_label']}**: {format_currency(results['B'])}")
        st.write(f"**{results['D_label']}**: {format_currency(results['D'])}")
        st.write(f"**{results['E_label']}**: {format_currency(results['E'])}")
    else:
        st.write(f"**{results['A_label']}**: {format_currency(results['A'])}")
        st.write(f"**{results['B_label']}**: {format_currency(results['B'])}")
        st.write(f"**{results['C_label']}**: {format_currency(results['C'])}")
        st.write(f"**{results['D_label']}**: {format_currency(results['D'])}")
        st.write(f"**{results['E_label']}**: {format_currency(results['E'])}")
    st.markdown("</div>", unsafe_allow_html=True)

    if st.button("현재 계산 결과 저장"):
        product_value = results.get("C", results.get("B"))
        save_history(
            {
                "거래처": selected_vendor,
                "계산식": results["rule_title"],
                "입력명": input_label,
                "입력값": code_text.strip().upper() if rule_key in {"mat_korea_ta", "product_code_last3_14"} else format_currency(x_value),
                "상품가": format_currency(product_value),
                "판매가": format_currency(results["E"]),
                "기준문구": raw_rule if str(raw_rule).strip() else "(빈칸)",
                "비고": note_text if str(note_text).strip() else "(빈칸)",
            }
        )
        st.success("최근 계산 결과에 저장했습니다.")

    st.divider()
    with st.expander("계산식 확인", expanded=False):
        if rule_key == "half_14":
            st.markdown(
                """
                - A = 거래처가구가격 ÷ 2 = **매입가**
                - B = A × 1.4 = **1.4배**
                - C = B를 10,000원 단위 올림 = **상품가**
                - D = C - A = **차액**
                - 차액이 30,000원 미만이면 상품가를 자동 보정
                - E = C × 1.1 = **판매가**
                """
            )
        elif rule_key == "domestic_15":
            st.markdown(
                """
                - A = x × 1.5
                - B = A를 10,000원 단위 올림 = **상품가**
                - D = B - A = **차액**
                - E = B × 1.1 = **판매가**
                """
            )
        elif rule_key == "domestic_15_plus_40k":
            st.markdown(
                """
                - A = x × 1.5
                - B = A를 10,000원 단위 올림
                - C = B + 40,000원 = **상품가**
                - D = C - A = **차액**
                - E = C × 1.1 = **판매가**
                """
            )
        elif rule_key == "project_15_plus_20k":
            st.markdown(
                """
                - A = x × 1.5
                - B = A를 10,000원 단위 올림
                - C = B + 20,000원 = **상품가**
                - D = C - A = **차액**
                - E = C × 1.1 = **판매가**
                """
            )
        elif rule_key == "unit_14":
            st.markdown(
                """
                - A = x × 1.4
                - B = A를 10,000원 단위 올림 = **상품가**
                - D = B - A = **차액**
                - E = B × 1.1 = **판매가**
                """
            )
        elif rule_key == "mat_korea_ta":
            st.markdown(
                """
                - 상품코드의 4번째~6번째 숫자를 읽고 뒤에 000을 붙여 금액으로 변환
                - 예: TOC045P810 → 045 → 45,000원
                - A = x × 1.4
                - 기본 상품가 = A를 10,000원 단위 올림
                - 차액이 30,000원 미만이면 상품가를 자동 보정
                - D = 최종 상품가 - A = **차액**
                - E = 최종 상품가 × 1.1 = **판매가**
                """
            )
        elif rule_key == "product_code_last3_14":
            st.markdown(
                """
                - 상품코드 마지막 3자리를 읽고 뒤에 000을 붙여 금액으로 변환
                - 예: 658047 → 047 → 47,000원 / ICL0135 → 135 → 135,000원
                - A = x × 1.4
                - 기본 상품가 = A를 10,000원 단위 올림
                - 차액이 30,000원 미만이면 상품가를 자동 보정
                - D = 최종 상품가 - A = **차액**
                - E = 최종 상품가 × 1.1 = **판매가**
                """
            )

    render_history()


if __name__ == "__main__":
    main()
