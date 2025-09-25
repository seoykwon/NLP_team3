#!/usr/bin/env python3
"""
통합 RAG QA 시스템 - 간단 버전
기준서, 상법, 감사보고서 RAG 기반 질의응답
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Optional
import pandas as pd
import re

# 프로젝트 루트 경로 설정 (절대 경로 사용)
project_root = Path("/Users/kwonseoyoung/Desktop/comb")
sys.path.append(str(project_root))
sys.path.append(str(project_root / "audit" / "scripts"))
sys.path.append(str(project_root / "extra" / "스트림릿"))
sys.path.append(str(project_root / "graph" / "code"))

# 로깅 설정
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 페이지 설정
st.set_page_config(
    page_title="통합 RAG QA 시스템",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# CSS 스타일 - 보라색-핑크색-흰색 테마
st.markdown("""
<style>
    /* 전체 앱 스타일 - 애니메이션 배경 */
    .stApp {
        background: linear-gradient(135deg, #f8f5ff 0%, #ffe8f7 30%, #f0e6ff 60%, #ffffff 100%);
        background-size: 400% 400%;
        animation: gradientShift 10s ease infinite;
        color: #000000 !important;
        min-height: 100vh;
    }
    
    @keyframes gradientShift {
        0% { background-position: 0% 50%; }
        50% { background-position: 100% 50%; }
        100% { background-position: 0% 50%; }
    }
    
    /* 모든 텍스트 검정색 */
    * {
        color: #000000 !important;
    }
    
    /* 메인 헤더 - 글로우 효과와 애니메이션 */
    .main-title {
        background: linear-gradient(135deg, #9c27b0 0%, #e91e63 30%, #f48fb1 70%, #f8bbd9 100%);
        background-size: 300% 300%;
        animation: headerGlow 8s ease-in-out infinite;
        color: white !important;
        padding: 2.8rem;
        border-radius: 25px;
        text-align: center;
        margin-bottom: 2rem;
        box-shadow: 0 12px 45px rgba(156, 39, 176, 0.4), 
                    inset 0 1px 0 rgba(255, 255, 255, 0.3);
        border: 2px solid rgba(255, 255, 255, 0.3);
        backdrop-filter: blur(15px);
        position: relative;
        overflow: hidden;
    }
    
    .main-title::before {
        content: '';
        position: absolute;
        top: -50%;
        left: -50%;
        width: 200%;
        height: 200%;
        background: linear-gradient(45deg, transparent, rgba(255, 255, 255, 0.15), transparent);
        animation: shimmer 4s infinite;
        pointer-events: none;
    }
    
    @keyframes headerGlow {
        0%, 100% { 
            background-position: 0% 50%;
            box-shadow: 0 12px 45px rgba(156, 39, 176, 0.4), 
                        inset 0 1px 0 rgba(255, 255, 255, 0.3);
        }
        50% { 
            background-position: 100% 50%;
            box-shadow: 0 18px 55px rgba(233, 30, 99, 0.5), 
                        inset 0 1px 0 rgba(255, 255, 255, 0.4);
        }
    }
    
    @keyframes shimmer {
        0% { transform: translateX(-100%) translateY(-100%) rotate(45deg); }
        100% { transform: translateX(100%) translateY(100%) rotate(45deg); }
    }
    
    .main-title h1, .main-title p {
        color: white !important;
        text-shadow: 2px 2px 4px rgba(0, 0, 0, 0.3);
    }
    
    /* 시스템 선택 버튼 */
    .system-buttons {
        display: flex;
        justify-content: center;
        gap: 1.5rem;
        margin: 2rem 0;
        flex-wrap: wrap;
    }
    
    .system-btn {
        background: linear-gradient(135deg, #ffffff 0%, #fdf2f8 100%);
        border: 2px solid #e91e63;
        color: #000000 !important;
        padding: 1.2rem 2.5rem;
        border-radius: 15px;
        cursor: pointer;
        transition: all 0.3s ease;
        font-weight: bold;
        text-decoration: none;
        display: inline-block;
        box-shadow: 0 4px 15px rgba(233, 30, 99, 0.2);
    }
    
    .system-btn:hover {
        background: linear-gradient(135deg, #e91e63 0%, #9c27b0 100%);
        color: white !important;
        transform: translateY(-3px);
        box-shadow: 0 8px 25px rgba(156, 39, 176, 0.4);
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
    }
    
    .system-btn.active {
        background: linear-gradient(135deg, #9c27b0 0%, #e91e63 100%);
        color: white !important;
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
        box-shadow: 0 6px 20px rgba(156, 39, 176, 0.3);
    }
    
    /* 샘플 질문 박스 */
    .sample-questions {
        background: linear-gradient(135deg, #ffffff 0%, #fdf2f8 50%, #f8f5ff 100%);
        padding: 2rem;
        border-radius: 18px;
        margin: 1.5rem 0;
        box-shadow: 0 6px 25px rgba(156, 39, 176, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.8);
        border-left: 6px solid #e91e63;
        border-top: 2px solid #f8bbd9;
        position: relative;
        overflow: hidden;
        transition: all 0.3s ease;
    }
    
    .sample-questions:hover {
        transform: translateY(-3px);
        box-shadow: 0 10px 35px rgba(156, 39, 176, 0.25),
                    inset 0 1px 0 rgba(255, 255, 255, 0.9);
    }
    
    .sample-question-btn {
        background: linear-gradient(135deg, #ffffff 0%, #fdf2f8 100%);
        border: 2px solid rgba(233, 30, 99, 0.3);
        color: #000000 !important;
        padding: 0.7rem 1.2rem;
        margin: 0.4rem;
        border-radius: 10px;
        cursor: pointer;
        display: inline-block;
        transition: all 0.3s ease;
        font-size: 0.9rem;
        box-shadow: 0 2px 8px rgba(156, 39, 176, 0.1);
    }
    
    .sample-question-btn:hover {
        background: linear-gradient(135deg, #f8bbd9 0%, #fce4ec 100%);
        border-color: #e91e63;
        transform: translateY(-2px);
        box-shadow: 0 4px 15px rgba(156, 39, 176, 0.2);
    }
    
    /* 채팅 영역 */
    .chat-container {
        background: linear-gradient(135deg, #ffffff 0%, #fdf2f8 50%, #f8f5ff 100%);
        border-radius: 20px;
        padding: 2.5rem;
        margin: 1.5rem 0;
        box-shadow: 0 8px 30px rgba(156, 39, 176, 0.2),
                    inset 0 1px 0 rgba(255, 255, 255, 0.8);
        min-height: 500px;
        border: 2px solid rgba(233, 30, 99, 0.3);
        transition: all 0.3s ease;
        position: relative;
        overflow: hidden;
    }
    
    .chat-container:hover {
        box-shadow: 0 12px 40px rgba(156, 39, 176, 0.25),
                    inset 0 1px 0 rgba(255, 255, 255, 0.9);
        border-color: rgba(233, 30, 99, 0.4);
    }
    
    /* 답변 박스 */
    .answer-box {
        background: linear-gradient(135deg, #f3e5f5 0%, #fce4ec 100%);
        border-left: 6px solid #9c27b0;
        border-top: 2px solid #e91e63;
        padding: 1.5rem;
        margin: 1.5rem 0;
        border-radius: 12px;
        color: #000000 !important;
        box-shadow: 0 4px 15px rgba(156, 39, 176, 0.1);
    }
    
    /* 에러 박스 */
    .error-box {
        background: linear-gradient(135deg, #ffeaea 0%, #fff0f0 100%);
        border-left: 6px solid #f44336;
        border-top: 2px solid #ff6b6b;
        padding: 1.5rem;
        margin: 1.5rem 0;
        border-radius: 12px;
        color: #000000 !important;
        box-shadow: 0 4px 15px rgba(244, 67, 54, 0.15);
    }
    
    /* Streamlit 요소들 스타일 오버라이드 */
    .stChatMessage {
        color: #000000 !important;
        background: rgba(248, 245, 255, 0.8);
        border: 1px solid rgba(233, 30, 99, 0.2);
        border-radius: 12px;
    }
    
    .stButton > button {
        background: linear-gradient(90deg, #9c27b0 0%, #e91e63 50%, #f8bbd9 100%);
        color: white !important;
        border: none;
        border-radius: 10px;
        padding: 0.7rem 1.2rem;
        font-weight: bold;
        box-shadow: 0 4px 15px rgba(156, 39, 176, 0.3);
        text-shadow: 1px 1px 2px rgba(0, 0, 0, 0.2);
        transition: all 0.3s ease;
    }
    
    .stButton > button:hover {
        background: linear-gradient(90deg, #8e24aa 0%, #d81b60 50%, #f48fb1 100%);
        transform: translateY(-2px);
        box-shadow: 0 6px 20px rgba(156, 39, 176, 0.4);
    }
    
    .stTextInput > div > div > input {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9) !important;
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    .stTextInput > div > div > input:focus {
        border-color: #e91e63;
        box-shadow: 0 0 10px rgba(233, 30, 99, 0.3);
    }
    
    .stSelectbox > div > div > select {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9) !important;
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    .stTextArea > div > div > textarea {
        color: #000000 !important;
        background: rgba(255, 255, 255, 0.9) !important;
        border: 2px solid rgba(233, 30, 99, 0.3);
        border-radius: 8px;
    }
    
    .stTextArea > div > div > textarea:focus {
        border-color: #e91e63;
        box-shadow: 0 0 10px rgba(233, 30, 99, 0.3);
    }
    
    /* 스피너 */
    .stSpinner > div {
        border-color: #e91e63 transparent transparent transparent;
    }
    
    /* 프로그래스 바 */
    .stProgress > div > div {
        background-color: #e91e63;
    }
</style>
""", unsafe_allow_html=True)

def load_openai_api_key() -> Optional[str]:
    """OpenAI API 키 로드"""
    # .env 파일 먼저 로드
    try:
        from dotenv import load_dotenv
        load_dotenv()
    except ImportError:
        pass
    
    api_key = os.getenv("OPENAI_API_KEY")
    return api_key

def get_sample_questions(system_type):
    """시스템별 샘플 질문 반환"""
    samples = {
        "audit": [
            "삼성전자의 매출액 변화 추이를 알려주세요",
            "2016년부터 2023년까지 영업이익의 연도별 변화 추이를 보여주세요", 
            "유동자산의 최근 몇 년간 증감 현황을 연도별로 알려주세요"
        ],
        "legal": [
            "준비금의 자본전입은 이사회에서 결정할 수 있는가?",
            "상법상 이사의 의무는 무엇인가요?",
            "주식회사의 설립 절차에 대해 알려주세요"
        ],
        "kifrs": [
            "개발비 자산 인식 요건은 무엇인가요?",
            "리스 회계처리 방법에 대해 설명해주세요",
            "금융자산의 분류 기준은 무엇인가요?"
        ]
    }
    return samples.get(system_type, [])

def extract_years_from_question(question: str):
    """질문에서 연도들을 추출"""
    years = re.findall(r"(20\d{2}|19\d{2})", question)
    return [int(year) for year in years] if years else []

def format_amount(value):
    """금액을 천 단위 콤마로 포맷"""
    if value is None:
        return "N/A"
    try:
        if value < 0:
            return f"({abs(value):,})"
        return f"{value:,}"
    except:
        return str(value)

def should_show_chart(question: str, answer: str):
    """차트를 표시해야 하는지 판단"""
    # 연도별, 추이, 변화 등의 키워드가 있으면 차트 표시
    chart_keywords = ["연도별", "추이", "변화", "증감", "비교", "년부터", "까지"]
    years = extract_years_from_question(question)
    
    # 여러 연도가 언급되거나 차트 관련 키워드가 있으면 차트 표시
    return len(years) > 1 or any(keyword in question for keyword in chart_keywords)

def extract_financial_data_from_answer(answer: str):
    """답변에서 재무 데이터를 추출하여 차트용 데이터로 변환"""
    try:
        data = {}
        
        # 다양한 패턴으로 연도와 금액을 추출
        patterns = [
            # "2024년: 82,320,322백만원" 또는 "- 2024년: 82,320,322백만원"
            r"(?:^|\s|-)\s*(20\d{2})년?\s*:?\s*([0-9,]+)(?:백만원|원)?",
            # "2024년 82,320,322백만원"
            r"(20\d{2})년?\s+([0-9,]+)(?:백만원|원)?",
            # "2024: 82,320,322"
            r"(20\d{2})\s*:\s*([0-9,]+)",
            # 표 형태: "2024    82,320,322"
            r"(20\d{2})\s+([0-9,]+)(?:\s|$)",
            # 괄호 안의 음수: "2024년: (1,234,567)백만원"
            r"(?:^|\s|-)\s*(20\d{2})년?\s*:?\s*\(([0-9,]+)\)(?:백만원|원)?",
        ]
        
        for pattern in patterns:
            matches = re.findall(pattern, answer, re.MULTILINE | re.IGNORECASE)
            for year_str, amount_str in matches:
                try:
                    year = int(year_str)
                    # 2014-2024 범위 내의 연도만 처리
                    if 2014 <= year <= 2024:
                        # 콤마 제거하고 숫자로 변환
                        amount = int(amount_str.replace(",", ""))
                        # 괄호 패턴은 음수로 처리
                        if "()" in pattern:
                            amount = -amount
                        data[year] = amount
                except (ValueError, IndexError):
                    continue
        
        # 디버깅을 위한 로그
        logger.info(f"추출된 재무 데이터: {data}")
        
        # 최소 2개 연도 이상의 데이터가 있어야 차트 표시
        return data if len(data) >= 2 else None
        
    except Exception as e:
        logger.error(f"Financial data extraction error: {e}")
        return None

def enhance_question_for_comprehensive_data(question: str) -> str:
    """질문을 더 포괄적인 데이터 검색을 위해 개선"""
    # 연도별 데이터 요청이면 더 구체적으로 만들기
    if any(keyword in question for keyword in ["연도별", "추이", "모든 연도", "표로"]):
        enhanced = f"{question} 삼성전자 연결재무제표 기준으로 2014년, 2015년, 2016년, 2017년, 2018년, 2019년, 2020년, 2021년, 2022년, 2023년, 2024년 각 연도별 데이터를 모두 포함해서 답변해주세요."
        return enhanced
    return question

def extract_sales_data_from_json(question: str) -> str:
    """JSON 파일에서 직접 매출액 데이터 추출"""
    try:
        import json
        
        sales_data = {}
        processed_dir = project_root / "audit" / "data" / "processed"
        
        # 2014년부터 2024년까지 데이터 수집
        for year in range(2014, 2025):
            json_file = processed_dir / f"감사보고서_{year}_rag_optimized.json"
            if json_file.exists():
                try:
                    with open(json_file, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    
                    # 손익계산서에서 매출액 찾기
                    for item in data:
                        if (item.get('note_title') == '손익계산서' and 
                            'tables' in item):
                            
                            for table_key, table in item['tables'].items():
                                if ('data' in table and 
                                    'Ⅰ. 매출액' in table['data']):
                                    
                                    sales_info = table['data']['Ⅰ. 매출액']
                                    
                                    # 당기 데이터 찾기
                                    for key, value in sales_info.items():
                                        if '당' in key and value != '':
                                            # 콤마 제거하고 숫자로 변환
                                            clean_value = value.replace(',', '')
                                            if clean_value.isdigit():
                                                sales_data[year] = int(clean_value)
                                                break
                                    break
                            if year in sales_data:
                                break
                                
                except Exception as e:
                    logger.error(f"Error reading {year} data: {e}")
                    continue
        
        if len(sales_data) >= 5:  # 5개 이상 연도 데이터가 있으면
            # 답변 생성
            answer = "## 삼성전자 연도별 매출액 분석\n\n"
            answer += "### 📊 연도별 매출액 (단위: 백만원)\n\n"
            
            years = sorted(sales_data.keys())
            for year in years:
                formatted_amount = f"{sales_data[year]:,}"
                answer += f"- **{year}년**: {formatted_amount}백만원\n"
            
            answer += f"\n### 📈 주요 분석\n"
            answer += f"- **최고 매출액**: {max(years)}년 {sales_data[max(years, key=sales_data.get)]:,}백만원\n"
            answer += f"- **최저 매출액**: {min(years)}년 {sales_data[min(years, key=sales_data.get)]:,}백만원\n"
            answer += f"- **데이터 기간**: {min(years)}년 ~ {max(years)}년 ({len(sales_data)}개 연도)\n"
            
            # 차트 데이터를 세션 상태에 저장
            if should_show_chart(question, answer):
                st.session_state.chart_data = {
                    "years": [str(year) for year in years],
                    "values": [sales_data[year] for year in years],
                    "question": question
                }
            
            return answer
            
    except Exception as e:
        logger.error(f"JSON 데이터 추출 실패: {e}")
        return None
    
    return None

def process_audit_question(question: str, api_key: str):
    """감사보고서 RAG 처리 - 기존 audit 폴더의 JSON 데이터 직접 활용"""
    try:
        # 먼저 기존 Qdrant RAG 시스템 시도
        audit_scripts_path = project_root / "audit" / "scripts"
        audit_scripts_abs = str(audit_scripts_path.absolute())
        if audit_scripts_abs not in sys.path:
            sys.path.insert(0, audit_scripts_abs)
        
        from hierarchy_rag_qa_system import HierarchyRAGQASystem
        
        if 'audit_rag_system' not in st.session_state:
            with st.spinner("감사보고서 RAG 시스템 초기화 중..."):
                st.session_state.audit_rag_system = HierarchyRAGQASystem(openai_api_key=api_key)
        
        # 질문을 더 포괄적으로 개선
        enhanced_question = enhance_question_for_comprehensive_data(question)
        logger.info(f"원본 질문: {question}")
        logger.info(f"개선된 질문: {enhanced_question}")
        
        # 먼저 JSON 데이터에서 직접 매출액 데이터 추출 시도
        if any(keyword in question.lower() for keyword in ["매출액", "매출", "sales", "revenue"]):
            direct_answer = extract_sales_data_from_json(question)
            if direct_answer:
                return direct_answer
        
        with st.spinner("답변 생성 중..."):
            # Qdrant RAG 시스템으로 답변 생성
            result = st.session_state.audit_rag_system.ask_question(enhanced_question, top_k=50, score_threshold=0.1)
            answer = result.get("answer", "답변을 생성할 수 없습니다.")
            
            # Qdrant 연결 오류 체크
            if "관련 정보를 찾을 수 없습니다" in answer:
                return "⚠️ 감사보고서 데이터베이스 연결에 문제가 있습니다. Qdrant 서버가 실행되지 않았거나 데이터가 로드되지 않았을 수 있습니다."
            
            # 차트 표시 여부 판단 및 처리
            chart_displayed = False
            if should_show_chart(question, answer):
                financial_data = extract_financial_data_from_answer(answer)
                
                if financial_data:
                    # 답변에 차트 정보 추가
                    answer += "\n\n📊 **데이터 시각화**\n"
                    
                    # 데이터프레임 생성
                    years = sorted(financial_data.keys())
                    values = [financial_data[year] for year in years]
                    
                    df = pd.DataFrame({
                        "연도": [str(year) for year in years],
                        "금액": [format_amount(v) for v in values],
                        "단위": ["백만원"] * len(years)
                    })
                    
                    # 데이터 테이블을 텍스트로 추가
                    answer += "\n**📋 데이터 테이블:**\n"
                    for _, row in df.iterrows():
                        answer += f"- {row['연도']}년: {row['금액']} {row['단위']}\n"
                    
                    # 데이터 제한 사항 안내
                    if len(values) < 10:  # 전체 연도(2014-2024)보다 적으면
                        answer += f"\n⚠️ **데이터 제한**: 현재 벡터 데이터베이스에서 {len(values)}개 연도의 데이터만 검색되었습니다. "
                        answer += "전체 기간(2014-2024)의 데이터가 필요한 경우, 원본 감사보고서를 직접 확인하시기 바랍니다."
                    
                    # 차트는 별도로 표시할 것을 표시
                    answer += "\n💡 *아래에서 시각화 차트를 확인하세요.*"
                    
                    # 세션 상태에 차트 데이터 저장
                    st.session_state.chart_data = {
                        "years": [str(year) for year in years],
                        "values": values,
                        "question": question
                    }
                    chart_displayed = True
            
            return answer
    
    except Exception as e:
        logger.error(f"Audit RAG error: {e}")
        return f"감사보고서 시스템 오류: {str(e)}"

def process_legal_question(question: str, api_key: str):
    """상법 RAG 처리"""
    try:
        # 상법 시스템 초기화
        if 'legal_rag_system' not in st.session_state:
            st.session_state.legal_rag_system = create_legal_rag_system(api_key)
        
        with st.spinner("상법 답변 생성 중..."):
            answer, results = st.session_state.legal_rag_system.search_and_answer(question, topk=5)
            return answer
    
    except Exception as e:
        logger.error(f"Legal RAG error: {e}")
        return f"상법 시스템 오류: {str(e)}"

def create_legal_rag_system(api_key: str):
    """상법 RAG 시스템 생성"""
    import json
    import numpy as np
    import faiss
    import re
    from sentence_transformers import SentenceTransformer
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import linear_kernel
    from openai import OpenAI
    
    class SimpleCommercialLawRAG:
        def __init__(self):
            # 상법 데이터 경로 (extra 폴더 기준으로 수정)
            self.base_path = project_root / "extra" / "상법 2"
            self.index_path = self.base_path / "kcc_index_json" / "kcc.index"
            self.ids_path = self.base_path / "kcc_index_json" / "ids.npy"
            self.metas_path = self.base_path / "kcc_index_json" / "metas.json"
            self.model_name = "intfloat/multilingual-e5-base"
            
            self.openai_client = OpenAI(api_key=api_key)
            self.index = None
            self.ids = None
            self.metas = None
            self.model = None
            self.tfidf = None
            self.X_tfidf = None
            
            self.load_resources()
        
        def load_resources(self):
            """리소스 로드"""
            try:
                # 파일 존재 확인
                if not all([self.index_path.exists(), self.ids_path.exists(), self.metas_path.exists()]):
                    raise FileNotFoundError("상법 데이터 파일을 찾을 수 없습니다.")
                
                # 인덱스/메타 로드
                self.index = faiss.read_index(str(self.index_path))
                self.ids = np.load(self.ids_path, allow_pickle=True).tolist()
                with open(self.metas_path, "r", encoding="utf-8") as f:
                    self.metas = json.load(f)
                
                # 모델 로드
                self.model = SentenceTransformer(self.model_name)
                
                # TF-IDF 인덱스 구축
                self._build_tfidf()
                
            except Exception as e:
                raise Exception(f"상법 시스템 로드 실패: {str(e)}")
        
        def _build_tfidf(self):
            """TF-IDF 인덱스 구축"""
            texts = []
            for m in self.metas:
                alias = " ".join(m.get("aliases", []))
                raw = m.get("raw_text", "")
                texts.append((alias + " " + raw).strip())
            
            self.tfidf = TfidfVectorizer(ngram_range=(1,2), min_df=1, max_df=0.95)
            self.X_tfidf = self.tfidf.fit_transform(texts)
        
        def normalize_query(self, q: str):
            """질의 정규화"""
            qn = q.strip()
            # 조문 번호 정규화
            m = re.search(r"(\d+)\s*의\s*(\d+)", qn)
            if m:
                qn += f" {m.group(1)}-{m.group(2)} 제{m.group(1)}조의{m.group(2)}"
            return qn
        
        def search_and_answer(self, query: str, topk: int = 5):
            """검색 및 답변 생성"""
            if not all([self.index, self.model, self.tfidf]):
                return "시스템이 초기화되지 않았습니다.", []
            
            # 질의 정규화 및 임베딩
            qn = self.normalize_query(query)
            qv = self.model.encode([qn], convert_to_numpy=True, normalize_embeddings=True)
            
            # FAISS 검색
            D, I = self.index.search(qv, topk*3)
            I, D = I[0], D[0]
            
            # TF-IDF 검색
            qv_t = self.tfidf.transform([qn])
            S_t = linear_kernel(qv_t, self.X_tfidf).ravel()
            
            # 하이브리드 결합
            results = []
            seen = set()
            
            # 임베딩 결과 추가
            for i, score in zip(I, D):
                if i >= 0 and i not in seen:
                    m = self.metas[int(i)]
                    results.append({
                        "id": self.ids[int(i)],
                        "article_id": m.get("article_id"),
                        "title": m.get("title"),
                        "content": m.get("raw_text", ""),
                        "score": float(score)
                    })
                    seen.add(i)
            
            # TF-IDF 상위 결과 보완
            tfidf_top = S_t.argsort()[::-1][:topk]
            for i in tfidf_top:
                if i not in seen and len(results) < topk:
                    m = self.metas[i]
                    results.append({
                        "id": self.ids[i],
                        "article_id": m.get("article_id"),
                        "title": m.get("title"),
                        "content": m.get("raw_text", ""),
                        "score": float(S_t[i])
                    })
                    seen.add(i)
            
            # 상위 결과만 선택
            results = results[:topk]
            
            # GPT 답변 생성
            answer = self._generate_answer(query, results)
            
            return answer, results
        
        def _generate_answer(self, query, results):
            """GPT 답변 생성"""
            # 컨텍스트 구성
            context_parts = []
            for r in results:
                article_id = str(r["article_id"])
                header = f"상법 제{article_id}조"
                if "의" in article_id:
                    header = f"상법 제{article_id.replace('의', '조의')}"
                
                title = r.get("title", "")
                if title:
                    header += f"({title})"
                
                content = r.get("content", "")[:500]  # 길이 제한
                context_parts.append(f"### {header}\n{content}")
            
            context = "\n\n".join(context_parts)
            
            system_msg = (
                "너는 한국 상법 전문가야. 제공된 조문들을 근거로 정확하고 간결하게 답변해. "
                "답변 끝에 참조한 조문 번호를 명시해."
            )
            
            user_msg = f"질문: {query}\n\n근거 조문:\n{context}"
            
            try:
                resp = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg}
                    ]
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                return f"답변 생성 중 오류: {str(e)}"
    
    return SimpleCommercialLawRAG()

def process_kifrs_question(question: str, api_key: str):
    """K-IFRS RAG 처리"""
    try:
        # K-IFRS 시스템 초기화
        if 'kifrs_rag_system' not in st.session_state:
            st.session_state.kifrs_rag_system = create_kifrs_rag_system(api_key)
        
        with st.spinner("K-IFRS 답변 생성 중..."):
            answer, results = st.session_state.kifrs_rag_system.search_and_answer(question, topk=5)
            return answer
    
    except Exception as e:
        logger.error(f"K-IFRS RAG error: {e}")
        return f"K-IFRS 시스템 오류: {str(e)}"

def create_kifrs_rag_system(api_key: str):
    """K-IFRS RAG 시스템 생성"""
    import json
    import numpy as np
    from sentence_transformers import SentenceTransformer
    from openai import OpenAI
    
    class SimpleKIFRSRAG:
        def __init__(self):
            # K-IFRS 데이터 경로
            self.base_path = project_root / "extra" / "기준서 2"
            self.json_path = self.base_path / "기준서 파싱.json"
            self.cache_dir = self.base_path / "hf_cache"
            self.para_emb_path = self.cache_dir / "para_emb_intfloat_multilingual-e5-large.npy"
            self.model_name = "intfloat/multilingual-e5-large"
            
            self.openai_client = OpenAI(api_key=api_key)
            self.docs = []
            self.paragraphs = []
            self.para_vecs = None
            self.model = None
            
            self.load_resources()
        
        def load_resources(self):
            """리소스 로드"""
            try:
                # JSON 데이터 로드
                if not self.json_path.exists():
                    raise FileNotFoundError("K-IFRS 데이터 파일을 찾을 수 없습니다.")
                
                with self.json_path.open(encoding='utf-8') as f:
                    data = json.load(f)
                
                self.docs = data.get('documents', [])
                
                # 문단 데이터 구성
                for d in self.docs:
                    std = d.get('standard_no')
                    title = d.get('title', '')
                    for p in d.get('paragraphs', []):
                        self.paragraphs.append({
                            "std": std,
                            "title": title,
                            "para_id": p.get('para_id'),
                            "text": p.get('text', ''),
                            "page": p.get('page')
                        })
                
                # 임베딩 로드 (있는 경우)
                if self.para_emb_path.exists():
                    self.para_vecs = np.load(self.para_emb_path)
                
                # 모델 로드
                self.model = SentenceTransformer(self.model_name)
                
            except Exception as e:
                raise Exception(f"K-IFRS 시스템 로드 실패: {str(e)}")
        
        def search_and_answer(self, query: str, topk: int = 5):
            """검색 및 답변 생성"""
            try:
                if self.para_vecs is not None:
                    # 벡터 검색 사용
                    query_emb = self.model.encode([f"query: {query}"], normalize_embeddings=True)[0]
                    similarities = np.dot(self.para_vecs, query_emb)
                    top_indices = np.argpartition(similarities, -topk*3)[-topk*3:]
                    top_indices = top_indices[np.argsort(similarities[top_indices])[::-1][:topk]]
                else:
                    # 텍스트 유사도 기반 검색 (임베딩 파일이 없는 경우)
                    query_emb = self.model.encode([query], normalize_embeddings=True)[0]
                    similarities = []
                    for para in self.paragraphs:
                        para_emb = self.model.encode([para["text"]], normalize_embeddings=True)[0]
                        sim = np.dot(query_emb, para_emb)
                        similarities.append(sim)
                    
                    similarities = np.array(similarities)
                    top_indices = similarities.argsort()[::-1][:topk]
                
                results = []
                for idx in top_indices:
                    para = self.paragraphs[idx]
                    results.append({
                        "std": para["std"],
                        "title": para["title"],
                        "para_id": para["para_id"],
                        "text": para["text"],
                        "page": para.get("page"),
                        "score": float(similarities[idx]) if isinstance(similarities, np.ndarray) else 0.0
                    })
                
                # GPT 답변 생성
                answer = self._generate_answer(query, results)
                
                return answer, results
            
            except Exception as e:
                return f"검색 중 오류 발생: {str(e)}", []
        
        def _generate_answer(self, query, results):
            """GPT 답변 생성"""
            # 컨텍스트 구성
            context_parts = []
            for r in results:
                header = f"[{r['std']}:{r['para_id']}] {r['title']} (p.{r.get('page', '?')})"
                text = r['text'][:500]  # 길이 제한
                context_parts.append(f"{header}\n{text}")
            
            context = "\n\n".join(context_parts)
            
            system_msg = (
                "너는 K-IFRS 회계기준 전문가야. 제공된 문단들을 근거로 정확하고 간결하게 답변해. "
                "답변 끝에 참조한 기준서 번호를 명시해."
            )
            
            user_msg = f"질문: {query}\n\n근거 문단:\n{context}"
            
            try:
                resp = self.openai_client.chat.completions.create(
                    model="gpt-4o-mini",
                    temperature=0.2,
                    messages=[
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": user_msg}
                    ]
                )
                return resp.choices[0].message.content.strip()
            except Exception as e:
                return f"답변 생성 중 오류: {str(e)}"
    
    return SimpleKIFRSRAG()

def main():
    # 메인 헤더
    st.markdown("""
    <div class="main-title">
        <h1>🤖 통합 RAG QA 시스템</h1>
        <p>감사보고서, 상법, K-IFRS 기준서 지능형 질의응답</p>
    </div>
    """, unsafe_allow_html=True)
    
    # API 키 확인
    api_key = load_openai_api_key()
    if not api_key:
        st.error("⚠️ OpenAI API 키가 설정되지 않았습니다. .env 파일을 확인해주세요.")
        st.stop()
    
    # 세션 상태 초기화
    if 'selected_system' not in st.session_state:
        st.session_state.selected_system = 'audit'
    if 'messages' not in st.session_state:
        st.session_state.messages = []
    
    # 시스템 선택 버튼
    st.markdown("### 📚 시스템 선택")
    
    col1, col2, col3 = st.columns(3)
    
    with col1:
        if st.button("📊 감사보고서", use_container_width=True, type="primary" if st.session_state.selected_system == 'audit' else "secondary"):
            st.session_state.selected_system = 'audit'
            st.session_state.messages = []  # 시스템 변경 시 채팅 초기화
            st.rerun()
    
    with col2:
        if st.button("⚖️ 상법", use_container_width=True, type="primary" if st.session_state.selected_system == 'legal' else "secondary"):
            st.session_state.selected_system = 'legal'
            st.session_state.messages = []
            st.rerun()
    
    with col3:
        if st.button("📋 K-IFRS 기준서", use_container_width=True, type="primary" if st.session_state.selected_system == 'kifrs' else "secondary"):
            st.session_state.selected_system = 'kifrs'
            st.session_state.messages = []
            st.rerun()
    
    # 현재 선택된 시스템 표시
    system_names = {
        'audit': '📊 감사보고서',
        'legal': '⚖️ 상법',
        'kifrs': '📋 K-IFRS 기준서'
    }
    
    st.markdown(f"**현재 선택된 시스템**: {system_names[st.session_state.selected_system]}")
    
    # 샘플 질문 표시
    st.markdown("### 💡 샘플 질문")
    sample_questions = get_sample_questions(st.session_state.selected_system)
    
    cols = st.columns(3)
    for i, question in enumerate(sample_questions):
        with cols[i]:
            if st.button(f"Q{i+1}: {question[:20]}...", key=f"sample_{i}", help=question, use_container_width=True):
                # 샘플 질문을 채팅에 추가
                st.session_state.messages.append({"role": "user", "content": question})
                
                # 답변 생성
                if st.session_state.selected_system == 'audit':
                    answer = process_audit_question(question, api_key)
                elif st.session_state.selected_system == 'legal':
                    answer = process_legal_question(question, api_key)
                else:  # kifrs
                    answer = process_kifrs_question(question, api_key)
                
                st.session_state.messages.append({"role": "assistant", "content": answer})
                st.rerun()
    
    # 채팅 영역
    st.markdown("### 💬 채팅")
    
    # 채팅 기록 표시
    chat_container = st.container()
    with chat_container:
        for i, message in enumerate(st.session_state.messages):
            if message["role"] == "user":
                with st.chat_message("user"):
                    st.markdown(f"**질문**: {message['content']}")
            else:
                with st.chat_message("assistant"):
                    st.markdown(f"""
                    <div class="answer-box">
                        {message['content']}
                    </div>
                    """, unsafe_allow_html=True)
                    
                    # 감사보고서 답변이고 차트 데이터가 있으면 차트 표시
                    if (st.session_state.selected_system == 'audit' and 
                        hasattr(st.session_state, 'chart_data') and 
                        st.session_state.chart_data and
                        i == len(st.session_state.messages) - 1):  # 최신 메시지인 경우만
                        
                        chart_data = st.session_state.chart_data
                        
                        # 라인 차트 표시
                        if len(chart_data['values']) > 1:
                            chart_df = pd.DataFrame({
                                "연도": chart_data['years'],
                                "금액(백만원)": chart_data['values']
                            })
                            st.line_chart(chart_df.set_index("연도"))
                        
                        # 데이터 테이블 표시
                        df_display = pd.DataFrame({
                            "연도": chart_data['years'],
                            "금액": [format_amount(v) for v in chart_data['values']],
                            "단위": ["백만원"] * len(chart_data['years'])
                        })
                        st.dataframe(df_display, use_container_width=True, hide_index=True)
    
    # 채팅 입력
    user_input = st.chat_input("질문을 입력하세요...")
    
    if user_input:
        # 사용자 메시지 추가
        st.session_state.messages.append({"role": "user", "content": user_input})
        
        # 답변 생성
        with st.spinner("답변 생성 중..."):
            if st.session_state.selected_system == 'audit':
                answer = process_audit_question(user_input, api_key)
            elif st.session_state.selected_system == 'legal':
                answer = process_legal_question(user_input, api_key)
            else:  # kifrs
                answer = process_kifrs_question(user_input, api_key)
        
        # 답변 추가
        st.session_state.messages.append({"role": "assistant", "content": answer})
        st.rerun()
    
    # 하단 정보
    st.markdown("---")
    st.markdown("""
    <div style="text-align: center; color: #666; padding: 1rem;">
        <p><strong>🤖 통합 RAG QA 시스템</strong> | 감사보고서, 상법, K-IFRS 기준서 통합 검색</p>
        <p>💡 정확한 정보는 원본 문서를 확인하세요</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()
