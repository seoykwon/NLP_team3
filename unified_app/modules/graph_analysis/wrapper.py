#!/usr/bin/env python3
"""
그래프 분석 시스템 래퍼
통합 앱에서 사용하기 위한 인터페이스
"""

import streamlit as st
import pandas as pd
from io import StringIO
import sys
from contextlib import redirect_stdout
from pathlib import Path
import logging
from typing import Optional

logger = logging.getLogger(__name__)

# 그래프 코드 경로 추가
project_root = Path(__file__).parent.parent.parent.parent
graph_code_path = project_root / "graph" / "code"
sys.path.append(str(graph_code_path))

try:
    from chat import (
        search_single_value, embed_model, client, COLLECTION_NAME, TOP_K,
        format_amount, extract_year_from_query, detect_statement_type, 
        detect_period_type, detect_breakdown_request
    )
    GRAPH_AVAILABLE = True
except ImportError as e:
    logger.warning(f"Graph analysis module not available: {e}")
    GRAPH_AVAILABLE = False

def show_graph_analysis_interface():
    """그래프 분석 인터페이스 표시"""
    st.markdown("# 🕸️ 그래프 분석 시스템")
    
    if not GRAPH_AVAILABLE:
        st.error("그래프 분석 시스템을 불러올 수 없습니다.")
        st.info("graph 폴더의 스크립트가 올바르게 설치되어 있는지 확인하세요.")
        return
    
    # 사이드바 설정
    with st.sidebar:
        st.header("⚙️ 설정")
        
        # 검색 설정
        search_type = st.radio(
            "검색 유형",
            ["자동 감지", "단일 값 조회", "계층 구조 조회"],
            help="자동 감지를 선택하면 질문 내용에 따라 자동으로 검색 유형을 결정합니다."
        )
        
        show_debug = st.checkbox("디버그 정보 표시", value=False)
        
        # 시스템 상태
        st.header("📊 시스템 상태")
        
        try:
            # LLM 상태 표시
            from chat import USE_LLM, llm
            if USE_LLM and llm is not None:
                st.success("🤖 LLaMA 모델 활성화됨")
            else:
                st.info("📊 기본 RAG 모드")
        except Exception:
            st.warning("⚠️ 모델 상태 확인 불가")
        
        # 데이터 경로 확인
        graph_data_path = project_root / "graph" / "data"
        if graph_data_path.exists():
            st.success("✅ 그래프 데이터 준비됨")
        else:
            st.error("❌ 그래프 데이터 없음")
        
        st.header("📚 사용 가이드")
        
        with st.expander("🔍 단일 값 조회 예시"):
            st.markdown("""
            - 2024년 재무상태표 상 당기 유동자산은 얼마인가?
            - 2023년 손익계산서 상 당기순이익은 얼마인가?
            - 2022년 현금흐름표 상 영업활동 현금흐름은?
            """)
        
        with st.expander("📊 계층 구조 조회 예시"):
            st.markdown("""
            - 2024년 비유동자산 하위 구조 알려줘
            - 2023년 유동자산의 세부 항목들이 뭐야?
            - 2022년 영업활동현금흐름 내역을 보여줘
            """)
    
    # 메인 영역
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
                if st.button(f"Q{i+1}", help=question, key=f"graph_quick_{i}"):
                    user_query = question
                    st.rerun()
    
    with col2:
        st.header("📊 질문 분석")
        
        if user_query:
            try:
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
            except Exception as e:
                st.error(f"질문 분석 중 오류: {e}")
    
    # 검색 실행
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
                    if pred is not None:
                        # 성공 결과 표시
                        formatted_value = format_amount(pred)
                        unit = meta.get("unit", "백만원")
                        
                        st.markdown(f"""
                        <div style="background: #f8f9fa; border-left: 5px solid #007bff; padding: 20px; margin: 20px 0; border-radius: 5px; color: #000000 !important;">
                            <h3 style="color: #000000 !important;">💰 답변: {formatted_value} {unit}</h3>
                        </div>
                        """, unsafe_allow_html=True)
                        
                        # LLM 설명이 있으면 표시
                        if "llm_explanation" in meta:
                            st.subheader("🤖 AI 분석")
                            st.markdown(f"""
                            <div style="background: #e7f3ff; border-left: 5px solid #17a2b8; padding: 15px; margin: 15px 0; border-radius: 5px; color: #000000 !important;">
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
                        <div style="background: #ffe6e6; border-left: 5px solid #dc3545; padding: 20px; margin: 20px 0; border-radius: 5px; color: #000000 !important;">
                            <h3 style="color: #000000 !important;">❌ 답변을 찾을 수 없습니다</h3>
                            <p style="color: #000000 !important;">사유: {why}</p>
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
                    logger.error(f"Graph analysis search failed: {e}")
                    if show_debug:
                        st.exception(e)
    
    # 하단 정보
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #000000; padding: 20px;">
        <p style="color: #000000 !important;">🏢 삼성전자 감사보고서 그래프 분석 시스템 | 📅 데이터 기간: 2014-2024년</p>
        <p style="color: #000000 !important;">💡 본 시스템은 감사보고서 데이터를 기반으로 하며, 정확한 정보는 원본 보고서를 확인하세요.</p>
    </div>
    """, unsafe_allow_html=True)
