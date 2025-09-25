# -*- coding: utf-8 -*-
"""
삼성전자 감사보고서 RAG 시스템 - Streamlit 앱
단일 값 조회 및 계층 구조 조회 지원
"""

import streamlit as st
import pandas as pd
from io import StringIO
import sys
from contextlib import redirect_stdout
from chat import (
    search_single_value, embed_model, client, COLLECTION_NAME, TOP_K,
    format_amount, extract_year_from_query, detect_statement_type, 
    detect_period_type, detect_breakdown_request
)

# ==========================
# 페이지 설정
# ==========================
st.set_page_config(
    page_title="삼성전자 감사보고서 RAG 시스템",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded"
)

# ==========================
# CSS 스타일
# ==========================
st.markdown("""
<style>
    .main-header {
        font-size: 2.5em;
        font-weight: bold;
        color: #1f4e79;
        text-align: center;
        margin-bottom: 30px;
    }
    .sub-header {
        font-size: 1.2em;
        color: #666;
        text-align: center;
        margin-bottom: 40px;
    }
    .result-box {
        background-color: #f8f9fa;
        border-left: 5px solid #007bff;
        padding: 20px;
        margin: 20px 0;
        border-radius: 5px;
    }
    .error-box {
        background-color: #ffe6e6;
        border-left: 5px solid #dc3545;
        padding: 20px;
        margin: 20px 0;
        border-radius: 5px;
    }
    .info-box {
        background-color: #e7f3ff;
        border-left: 5px solid #17a2b8;
        padding: 15px;
        margin: 15px 0;
        border-radius: 5px;
    }
    .example-query {
        background-color: #f1f3f4;
        padding: 10px;
        border-radius: 5px;
        font-family: monospace;
        margin: 5px 0;
    }
</style>
""", unsafe_allow_html=True)

# ==========================
# 헤더
# ==========================
st.markdown('<div class="main-header">📊 삼성전자 감사보고서 RAG 시스템</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-header">2014-2024년 재무정보 검색 및 계층 구조 분석</div>', unsafe_allow_html=True)

# ==========================
# 사이드바 - 설정 및 도움말
# ==========================
with st.sidebar:
    st.header("⚙️ 설정")
    
    # 검색 설정
    search_type = st.radio(
        "검색 유형",
        ["자동 감지", "단일 값 조회", "계층 구조 조회"],
        help="자동 감지를 선택하면 질문 내용에 따라 자동으로 검색 유형을 결정합니다."
    )
    
    show_debug = st.checkbox("디버그 정보 표시", value=False)
    
    # LLM 상태 표시
    try:
        from chat import USE_LLM, llm
        if USE_LLM and llm is not None:
            st.success("🤖 LLaMA 모델 활성화됨")
        else:
            st.info("📊 기본 RAG 모드")
    except Exception:
        st.warning("⚠️ 모델 상태 확인 불가")
    
    st.header("📚 사용 가이드")
    
    with st.expander("🔍 단일 값 조회 예시"):
        st.markdown("""
        <div class="example-query">2024년 재무상태표 상 당기 유동자산은 얼마인가?</div>
        <div class="example-query">2023년 손익계산서 상 당기순이익은 얼마인가?</div>
        <div class="example-query">2022년 현금흐름표 상 영업활동 현금흐름은?</div>
        """, unsafe_allow_html=True)
    
    with st.expander("📊 계층 구조 조회 예시"):
        st.markdown("""
        <div class="example-query">2024년 비유동자산 하위 구조 알려줘</div>
        <div class="example-query">2023년 유동자산의 세부 항목들이 뭐야?</div>
        <div class="example-query">2022년 영업활동현금흐름 내역을 보여줘</div>
        """, unsafe_allow_html=True)
    
    with st.expander("📋 지원 정보"):
        st.markdown("""
        **지원 연도**: 2014 ~ 2024년
        
        **지원 재무제표**:
        - 재무상태표 (대차대조표)
        - 손익계산서
        - 현금흐름표
        - 포괄손익계산서
        - 자본변동표
        
        **기간 구분**:
        - 당기 (현재 년도)
        - 전기 (이전 년도)
        """)

# ==========================
# 메인 영역
# ==========================
col1, col2 = st.columns([2, 1])

with col1:
    st.header("💬 질문 입력")
    
    # 질문 입력 영역
    user_query = st.text_area(
        "재무정보에 대한 질문을 입력하세요:",
        height=100,
        placeholder="예: 2024년 재무상태표 상 당기 자산총계는 얼마인가?"
    )
    
    # 빠른 질문 버튼들
    st.subheader("🚀 빠른 질문")
    
    quick_questions = [
        "2024년 재무상태표 상 당기 자산총계는 얼마인가?",
        "2024년 손익계산서 상 당기 매출액은 얼마인가?", 
        "2024년 비유동자산 하위 구조 알려줘",
        "2023년 영업활동현금흐름 내역을 보여줘"
    ]
    
    cols = st.columns(2)
    for i, question in enumerate(quick_questions):
        with cols[i % 2]:
            if st.button(f"Q{i+1}", help=question, key=f"quick_{i}"):
                user_query = question
                st.rerun()

with col2:
    st.header("📊 질문 분석")
    
    if user_query:
        # 질문 분석
        year = extract_year_from_query(user_query)
        statement_type = detect_statement_type(user_query)
        period_type = detect_period_type(user_query)
        is_breakdown = detect_breakdown_request(user_query)
        
        analysis_data = {
            "항목": ["연도", "재무제표", "기간", "검색 유형"],
            "값": [
                year if year else "미지정",
                {
                    "balance": "재무상태표",
                    "income": "손익계산서", 
                    "cashflow": "현금흐름표",
                    "equity_changes": "자본변동표"
                }.get(statement_type, statement_type),
                {
                    "current": "당기",
                    "previous": "전기"
                }.get(period_type, "미지정"),
                "계층 구조 조회" if is_breakdown else "단일 값 조회"
            ]
        }
        
        df_analysis = pd.DataFrame(analysis_data)
        st.dataframe(df_analysis, use_container_width=True, hide_index=True)

# ==========================
# 검색 실행
# ==========================
if st.button("🔍 검색 실행", type="primary", use_container_width=True):
    if not user_query.strip():
        st.error("질문을 입력해주세요.")
    else:
        with st.spinner("검색 중..."):
            try:
                # 검색 타입 결정
                if search_type == "자동 감지":
                    is_breakdown_query = detect_breakdown_request(user_query)
                elif search_type == "계층 구조 조회":
                    is_breakdown_query = True
                else:
                    is_breakdown_query = False
                
                # 출력 캡처를 위한 설정
                output_buffer = StringIO()
                
                # 검색 실행
                with redirect_stdout(output_buffer):
                    pred, meta, why = search_single_value(
                        user_query, embed_model, client, COLLECTION_NAME, TOP_K
                    )
                
                # 캡처된 출력 가져오기
                captured_output = output_buffer.getvalue()
                
                # 결과 표시
                if is_breakdown_query or detect_breakdown_request(user_query):
                    # AI 요약이 캡처된 출력에 있는지 확인하고 먼저 표시
                    if "🤖 AI 요약" in captured_output:
                        # AI 요약 부분 추출
                        lines = captured_output.split('\n')
                        ai_summary_lines = []
                        in_ai_section = False
                        
                        for line in lines:
                            if "🤖 AI 요약" in line:
                                in_ai_section = True
                                continue
                            elif line.startswith("=") and in_ai_section:
                                if ai_summary_lines:  # AI 요약 섹션 끝
                                    break
                                continue
                            elif in_ai_section and line.strip():
                                if line.startswith("📊"):
                                    ai_summary_lines.append(line)
                        
                        if ai_summary_lines:
                            st.header("🤖 AI 요약")
                            for summary_line in ai_summary_lines:
                                if summary_line.strip():
                                    # 연도와 내용 분리
                                    if "📊" in summary_line:
                                        parts = summary_line.split(":", 1)
                                        if len(parts) == 2:
                                            year_part = parts[0].replace("📊", "").strip()
                                            content_part = parts[1].strip()
                                            st.markdown(f"""
                                            <div class="result-box">
                                                <h4>{year_part}</h4>
                                                <p>{content_part}</p>
                                            </div>
                                            """, unsafe_allow_html=True)
                            st.markdown("---")
                    
                    # 계층 구조 조회 결과
                    st.header("📊 계층 구조 조회 결과")
                    
                    # LLM 생성 답변이 있으면 먼저 표시
                    if "llm_answer" in meta:
                        st.subheader("🤖 AI 분석 결과")
                        st.markdown(f"""
                        <div class="result-box">
                            {meta["llm_answer"]}
                        </div>
                        """, unsafe_allow_html=True)
                        st.markdown("---")
                    
                    if "hierarchy_results" in meta:
                        hierarchy_data = meta["hierarchy_results"]
                        
                        if hierarchy_data:
                            # 계층 구조를 데이터프레임으로 변환
                            df_data = []
                            for item in hierarchy_data:
                                df_data.append({
                                    "계정명": item.get("account_name", ""),
                                    "당기 금액": format_amount(item.get("amount_current")),
                                    "전기 금액": format_amount(item.get("amount_previous")),
                                    "단위": item.get("unit", "백만원"),
                                    "레벨": item.get("level", ""),
                                    "주석": item.get("notes", "")
                                })
                            
                            df_hierarchy = pd.DataFrame(df_data)
                            st.dataframe(df_hierarchy, use_container_width=True, hide_index=True)
                            
                            # 다운로드 버튼
                            csv = df_hierarchy.to_csv(index=False, encoding='utf-8-sig')
                            st.download_button(
                                label="📥 CSV 다운로드",
                                data=csv,
                                file_name=f"hierarchy_result_{year}_{statement_type}.csv",
                                mime="text/csv"
                            )
                        else:
                            st.warning("해당 계정의 하위 구조를 찾을 수 없습니다.")
                    
                    # 캡처된 출력이 있으면 표시 (AI 요약 부분 제외)
                    if captured_output.strip():
                        # AI 요약 부분 제거
                        filtered_output = captured_output
                        if "🤖 AI 요약" in captured_output:
                            lines = captured_output.split('\n')
                            filtered_lines = []
                            skip_ai_section = False
                            
                            for line in lines:
                                if "🤖 AI 요약" in line:
                                    skip_ai_section = True
                                    continue
                                elif line.startswith("📝 참고:") and skip_ai_section:
                                    skip_ai_section = False
                                    filtered_lines.append(line)
                                elif not skip_ai_section:
                                    filtered_lines.append(line)
                            
                            filtered_output = '\n'.join(filtered_lines)
                        
                        if filtered_output.strip():
                            with st.expander("🔍 상세 검색 로그"):
                                st.text(filtered_output)
                
                else:
                    # 비율 계산 결과인지 확인
                    if "ratio_type" in meta:
                        # 비율 계산 결과 표시
                        st.header("📊 재무비율 계산 결과")
                        
                        ratio_info = meta
                        st.markdown(f"""
                        <div class="result-box">
                            <h3>💰 {ratio_info.get('ratio_name', '비율')}: {ratio_info.get('ratio_value', 0):.2f}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # 공식 및 계산 과정 표시
                        st.subheader("📐 계산 공식")
                        st.info(f"**{ratio_info.get('formula', 'N/A')}**")
                        
                        # 구성 요소 표시
                        col1, col2 = st.columns(2)
                        
                        numerator = ratio_info.get('numerator', {})
                        denominator = ratio_info.get('denominator', {})
                        
                        with col1:
                            st.metric(
                                label=f"분자: {numerator.get('name', 'N/A')}",
                                value=numerator.get('formatted', 'N/A'),
                                help="백만원"
                            )
                        
                        with col2:
                            st.metric(
                                label=f"분모: {denominator.get('name', 'N/A')}",
                                value=denominator.get('formatted', 'N/A'),
                                help="백만원"
                            )
                        
                        # 해석 표시
                        if ratio_info.get('interpretation'):
                            st.subheader("💡 비율 해석")
                            st.success(f"**{ratio_info['interpretation']}**")
                        
                        # 백분율 표시 (필요한 경우)
                        ratio_type = ratio_info.get('ratio_type', '')
                        if ratio_type in ['debt_ratio', 'equity_ratio']:
                            percentage = ratio_info.get('ratio_value', 0) * 100
                            st.info(f"백분율로 표시: **{percentage:.1f}%**")
                        
                        # 캡처된 출력이 있으면 표시
                        if captured_output.strip():
                            with st.expander("🔍 상세 계산 로그"):
                                st.text(captured_output)
                    
                    elif "multi_year_single_values" in meta:
                        # 다년도 단일 값 조회 결과
                        st.header("📊 연도별 비교 결과")
                        
                        multi_data = meta["multi_year_single_values"]
                        
                        # 차트 데이터 준비
                        years = []
                        values = []
                        for year in sorted(multi_data.keys()):
                            years.append(str(year))
                            values.append(multi_data[year]["value"])
                        
                        # 데이터프레임 생성
                        df_multi = pd.DataFrame({
                            "연도": years,
                            "금액": [format_amount(v) for v in values],
                            "단위": ["백만원"] * len(years)
                        })
                        
                        # 데이터 표시
                        st.dataframe(df_multi, use_container_width=True, hide_index=True)
                        
                        # 라인 차트 표시
                        if len(values) > 1:
                            chart_df = pd.DataFrame({
                                "연도": years,
                                "금액(백만원)": values
                            })
                            st.line_chart(chart_df.set_index("연도"))
                        
                        # 캡처된 출력이 있으면 표시
                        if captured_output.strip():
                            with st.expander("🔍 상세 검색 로그"):
                                st.text(captured_output)
                    
                    elif pred is not None:
                        # 성공 결과 표시
                        formatted_value = format_amount(pred)
                        unit = meta.get("unit", "백만원")
                        
                        st.markdown(f"""
                        <div class="result-box">
                            <h3>💰 답변: {formatted_value} {unit}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # LLM 설명이 있으면 표시
                        if "llm_explanation" in meta:
                            st.subheader("🤖 AI 분석")
                            st.markdown(f"""
                            <div class="info-box">
                                {meta["llm_explanation"]}
                            </div>
                            """, unsafe_allow_html=True)
                        
                        # 상세 정보
                        col1, col2, col3 = st.columns(3)
                        with col1:
                            st.metric("연도", meta.get("anchor_fiscal_year", meta.get("report_year", "N/A")))
                        with col2:
                            st.metric("재무제표", meta.get("statement_type", "N/A"))
                        with col3:
                            st.metric("기간", meta.get("period_type", "N/A"))
                        
                        # 계정 정보
                        account_info = {
                            "계정명": meta.get("account_name", "N/A"),
                            "계층": " → ".join(meta.get("hierarchy", [])),
                            "레벨": meta.get("level", "N/A"),
                            "단위": unit
                        }
                        
                        st.subheader("📋 계정 정보")
                        for key, value in account_info.items():
                            st.write(f"**{key}**: {value}")
                    
                    else:
                        # 실패 결과 표시
                        st.markdown(f"""
                        <div class="error-box">
                            <h3>❌ 답변을 찾을 수 없습니다</h3>
                            <p>사유: {why}</p>
                        </div>
                        """, unsafe_allow_html=True)
                
                # 디버그 정보 표시
                if show_debug:
                    with st.expander("🔧 디버그 정보"):
                        st.write("**검색 결과 메타데이터:**")
                        st.json(meta)
                        st.write(f"**검색 사유:** {why}")
                        if captured_output.strip():
                            st.write("**검색 로그:**")
                            st.text(captured_output)
            
            except Exception as e:
                st.error(f"검색 중 오류가 발생했습니다: {str(e)}")
                if show_debug:
                    st.exception(e)

# ==========================
# 푸터
# ==========================
st.markdown("---")
st.markdown("""
<div style="text-align: center; color: #666; padding: 20px;">
    <p>🏢 삼성전자 감사보고서 RAG 시스템 | 📅 데이터 기간: 2014-2024년</p>
    <p>💡 본 시스템은 감사보고서 데이터를 기반으로 하며, 정확한 정보는 원본 보고서를 확인하세요.</p>
</div>
""", unsafe_allow_html=True)

# ==========================
# 세션 상태 초기화
# ==========================
if 'initialized' not in st.session_state:
    st.session_state.initialized = True
    st.success("🚀 시스템이 성공적으로 초기화되었습니다!")
