# -*- coding: utf-8 -*-
"""
RAG Numeric QA (anchor_fiscal_year 기반, period/current-previous 지원)
- 단일 값 질의 전용(계층 브레이크다운 아님)
- 질의: 임베딩 + Qdrant 필터(anchor_fiscal_year, statement_type, period_type)로 1개 값 도출
- 출력: 천 단위 콤마, 음수 괄호표기, 콘솔 비교표

필수 파이썬 패키지:
    qdrant-client, sentence-transformers, numpy

작성자: 석재 워크플로우용
"""

import re
import numpy as np
from pathlib import Path
from typing import Optional, Dict, Any, Tuple, List

from qdrant_client import QdrantClient
from qdrant_client.http import models as qmodels
from sentence_transformers import SentenceTransformer


# ==========================
# 환경 설정
# ==========================
EMBED_MODEL_NAME = "dragonkue/bge-m3-ko"
QDRANT_PATH = "/Users/dan/Desktop/snu_project/git_제출용/data/vector_store/final-sjchunk/bge-ko-qdrant_db"
COLLECTION_NAME = "audit_chunks"
TOP_K = 40   # 벡터 검색 후보 수

# LLaMA 모델 설정
LLAMA_MODEL_PATH = "/Users/dan/Desktop/snu_project/models/zephyr-7b-beta.Q4_K_M.gguf"
USE_LLM = True  # LLM 사용 여부


# ==========================
# 클라이언트/모델
# ==========================
embed_model = SentenceTransformer(EMBED_MODEL_NAME)

# Qdrant 클라이언트를 필요할 때 생성하는 함수
def get_qdrant_client():
    """Qdrant 클라이언트를 lazy loading으로 생성"""
    global _qdrant_client
    if '_qdrant_client' not in globals():
        _qdrant_client = QdrantClient(path=QDRANT_PATH)
    return _qdrant_client

# 호환성을 위해 client 변수 유지 (첫 번째 접근 시 초기화)
try:
    client = get_qdrant_client()
except Exception as e:
    print(f"⚠️  초기 Qdrant 클라이언트 생성 실패: {e}")
    client = None

# LLaMA 모델 초기화 (선택적)
llm = None
if USE_LLM:
    try:
        from llama_cpp import Llama
        
        model_path = Path(LLAMA_MODEL_PATH)
        if model_path.exists():
            llm = Llama(
                model_path=str(model_path),
                n_ctx=4096,
                n_threads=8,
                n_gpu_layers=35,
                chat_format="zephyr",
                verbose=False
            )
            print("✅ LLaMA 모델 로드 완료")
        else:
            print(f"⚠️  LLaMA 모델 파일을 찾을 수 없습니다: {model_path}")
    except ImportError:
        print("⚠️  llama-cpp-python이 설치되지 않았습니다. pip install llama-cpp-python")
    except Exception as e:
        print(f"⚠️  LLaMA 모델 로드 실패: {e}")


# ==========================
# 유틸
# ==========================
KOREAN_SPACE_RE = re.compile(r"(?:[가-힣]\s)+(?:[가-힣])")

def collapse_ko_spaced(s: str) -> str:
    """'유  동  자  산' -> '유동자산' 같은 인위적 공백 제거"""
    if not s:
        return s
    return s.replace(" ", "") if KOREAN_SPACE_RE.fullmatch(s) else s

def extract_year_from_query(query: str) -> Optional[int]:
    m = re.search(r"(20\d{2}|19\d{2})", query)
    return int(m.group(1)) if m else None

def extract_multiple_years_from_query(query: str) -> List[int]:
    """쿼리에서 여러 연도를 추출 (예: 2014, 2015, 2016, 2017)"""
    years = re.findall(r"(20\d{2}|19\d{2})", query)
    return [int(year) for year in years] if years else []

def detect_multi_year_request(query: str) -> bool:
    """여러 년도 요청인지 감지"""
    years = extract_multiple_years_from_query(query)
    return len(years) > 1

def detect_statement_type(query: str) -> str:
    q = query.replace(" ", "")
    if "재무상태표" in q or "대차대조표" in q: return "balance"
    if "손익계산서" in q or "포괄손익" in q: return "income"
    if "현금흐름표" in q: return "cashflow"
    if "자본변동표" in q: return "equity_changes"
    return "balance"

def detect_period_type(query: str) -> Optional[str]:
    q = query.replace(" ", "")
    if "당기" in q: return "current"
    if "전기" in q: return "previous"
    return None

def detect_breakdown_request(query: str) -> bool:
    """하위 구조/세부 정보 요청인지 감지"""
    q = query.replace(" ", "")
    breakdown_keywords = [
        "하위", "세부", "구조", "구성", "내역", "항목", "분류", "breakdown", 
        "구성요소", "세부항목", "하위항목", "구성내역", "세부구조"
    ]
    return any(keyword in q for keyword in breakdown_keywords)


def extract_account_name(query: str) -> Optional[str]:
    """질문에서 계정명 추출"""
    q = query.replace(" ", "")
    
    # 주요 계정명들 (긴 것부터 정렬하여 정확한 매칭)
    account_names = [
        "비유동자산", "유동자산", "자산총계", "자산", 
        "비유동부채", "유동부채", "부채총계", "부채",
        "자본총계", "자본", "자기자본",
        "영업활동현금흐름", "투자활동현금흐름", "재무활동현금흐름",
        "당기순이익", "매출총이익", "영업이익", "매출액",
        "유형자산", "무형자산", "재고자산", "현금및현금성자산",
        "매출채권", "단기금융상품", "종속기업투자", "관계기업투자"
    ]
    
    # 정확한 매칭을 위해 특별 처리
    # 먼저 정확한 키워드로 매칭 시도
    if "유동자산" in q and "비유동자산" not in q:
        return "유동자산"
    elif "비유동자산" in q:
        return "비유동자산"
    elif "유동부채" in q and "비유동부채" not in q:
        return "유동부채"
    elif "비유동부채" in q:
        return "비유동부채"
    
    # 나머지는 일반적인 매칭
    # 길이 순으로 정렬 (긴 것부터 매칭)
    sorted_accounts = sorted(account_names, key=len, reverse=True)
    
    for account in sorted_accounts:
        if account in q:
            return account
    
    return None

def format_amount(value: Optional[float]) -> str:
    """숫자 포맷: 천단위 콤마, 음수는 괄호"""
    if value is None:
        return "-"
    try:
        v = float(value)
        if v < 0:
            return f"({int(abs(v)):,})"
        return f"{int(v):,}"
    except Exception:
        # 숫자형이 아니면 문자열 그대로
        return str(value)

def normalize_numeric_str(s: str) -> Optional[int]:
    """문자열 '(1,234)' → -1234, '1,234' → 1234 비교용"""
    if s is None or s == "-":
        return None
    ss = str(s).strip()
    neg = False
    if ss.startswith("(") and ss.endswith(")"):
        neg = True
        ss = ss[1:-1]
    ss = ss.replace(",", "")
    if not ss or not re.match(r"^-?\d+$", ss):
        return None
    n = int(ss)
    return -n if neg else n


# ==========================
# Qdrant Filter 빌더 (anchor_fiscal_year 우선)
# ==========================
def build_filter(
    anchor_year: Optional[int] = None,
    year: Optional[int] = None,                 # fallback (report_year)
    statement_type: Optional[str] = None,
    period_type: Optional[str] = None,
    must_have_hierarchy: Optional[str] = None,
    parent_id: Optional[str] = None,
    account_id: Optional[str] = None,
    min_level: Optional[int] = None,
    exclude_totals: bool = False,               # 단일값 QA: 총계/소계도 허용
    exclude_subtotals: bool = False
) -> Optional[qmodels.Filter]:
    must: List[qmodels.FieldCondition] = []

    if anchor_year is not None:
        must.append(qmodels.FieldCondition(key="anchor_fiscal_year", match=qmodels.MatchValue(value=anchor_year)))
    elif year is not None:
        must.append(qmodels.FieldCondition(key="report_year", match=qmodels.MatchValue(value=year)))

    if statement_type:
        must.append(qmodels.FieldCondition(key="statement_type", match=qmodels.MatchValue(value=statement_type)))
    if period_type:
        must.append(qmodels.FieldCondition(key="period_type", match=qmodels.MatchValue(value=period_type)))
    if must_have_hierarchy:
        must.append(qmodels.FieldCondition(key="hierarchy", match=qmodels.MatchAny(any=[must_have_hierarchy])))
    if parent_id:
        must.append(qmodels.FieldCondition(key="parent_id", match=qmodels.MatchValue(value=parent_id)))
    if account_id:
        must.append(qmodels.FieldCondition(key="account_id", match=qmodels.MatchValue(value=account_id)))
    if min_level is not None:
        must.append(qmodels.FieldCondition(key="level", range=qmodels.Range(gte=min_level)))
    if exclude_totals:
        must.append(qmodels.FieldCondition(key="is_total", match=qmodels.MatchValue(value=False)))
    if exclude_subtotals:
        must.append(qmodels.FieldCondition(key="is_subtotal", match=qmodels.MatchValue(value=False)))

    return qmodels.Filter(must=must) if must else None


# ==========================
# 단일 값 검색
# ==========================
VALUE_KEYS = ["value", "value_current", "value_previous", "amount_current", "amount_prev", "당기", "전기"]

def _pick_value(meta: Dict[str, Any]) -> Optional[float]:
    for k in VALUE_KEYS:
        if k in meta and meta[k] not in (None, ""):
            v = meta[k]
            if isinstance(v, (int, float)):
                return float(v)
            if isinstance(v, str):
                # "1,234" → 1234
                s = v.replace(",", "")
                try:
                    return float(s)
                except Exception:
                    continue
    return None

def _name_match_boost(query: str, meta: Dict[str, Any]) -> float:
    """계정명/계층과 질의의 문자열 매칭으로 보정 점수"""
    qn = collapse_ko_spaced(query.replace(" ", ""))
    name = collapse_ko_spaced(str(meta.get("account_name", "")))
    last = ""
    h = meta.get("hierarchy", [])
    if isinstance(h, list) and h:
        last = collapse_ko_spaced(str(h[-1]))
    boost = 0.0
    if name and (name in qn or qn in name):
        boost += 0.06
    if last and (last in qn or qn in last):
        boost += 0.05
    # 주요 키워드 가산(간단)
    kw = ["유동자산","비유동자산","자산총계","영업활동","투자활동","재무활동","당기순이익","매출총이익"]
    if any(k in qn for k in kw) and (name in kw or last in kw):
        boost += 0.02
    return boost

def search_single_value(query: str, model: SentenceTransformer, client: QdrantClient,
                        collection_name: str, top_k: int = TOP_K) -> Tuple[Optional[float], Dict[str, Any], Optional[str]]:
    """
    질의 → 단일 값(숫자) 예측 또는 하위 구조 조회 또는 비율 계산
    반환: (value, best_meta, debug_reason)
    """
    # 클라이언트가 None인 경우 재생성
    if client is None:
        try:
            client = get_qdrant_client()
        except Exception as e:
            print(f"❌ Qdrant 클라이언트 생성 실패: {e}")
            return None, {}, "client_error"
    # 여러 년도 요청인지 확인
    if detect_multi_year_request(query):
        if detect_breakdown_request(query):
            return search_multi_year_hierarchy(query, model, client, collection_name)
        else:
            # 여러 년도 단일 값 조회
            return search_multi_year_single_values(query, model, client, collection_name)
    
    # 하위 구조 요청인지 확인 (단일 년도)
    if detect_breakdown_request(query):
        return search_hierarchy_structure(query, model, client, collection_name, top_k)
    
    anchor_year = extract_year_from_query(query)
    statement_type = detect_statement_type(query)
    period_type = detect_period_type(query)  # None이면 미지정(=둘 다 가능)

    qv = model.encode("query: " + query, normalize_embeddings=True).tolist()
    filt = build_filter(
        anchor_year=anchor_year,
        statement_type=statement_type,
        period_type=period_type,          # 특정되면 고정, 아니면 None
        exclude_totals=False,             # 총계/소계 포함
        exclude_subtotals=False
    )

    res = client.query_points(
        collection_name=collection_name,
        query=qv,
        limit=top_k,
        with_payload=True,
        query_filter=filt
    )

    if not res.points:
        return None, {}, "no_points"

    # 후보 점수 계산(임베딩 스코어 + 문자열 매칭 보정)
    best = None
    best_score = -1e9
    best_val = None
    reason = ""

    for p in res.points:
        payload = p.payload or {}
        meta = payload.get("metadata", payload)
        val = _pick_value(meta)
        if val is None:
            # 텍스트에서 보조 추출(옵션). 지금은 보수적으로 스킵.
            continue

        s = float(getattr(p, "score", 0.0) or 0.0)
        s += _name_match_boost(query, meta)

        # period_type 맞으면 살짝 가산
        if period_type and meta.get("period_type") == period_type:
            s += 0.02

        # statement_type 맞음 가산
        if statement_type and meta.get("statement_type") == statement_type:
            s += 0.01

        if s > best_score:
            best_score = s
            best = meta
            best_val = val

    if best is None:
        return None, {}, "no_value_pick"

    # LLM으로 간단한 설명 추가 (선택적)
    if USE_LLM and llm is not None:
        try:
            account_name = best.get("account_name", "")
            formatted_value = format_amount(best_val)
            
            prompt = f"""삼성전자 {anchor_year}년 {account_name}은 {formatted_value} 백만원입니다.

위 정보를 "삼성전자 [연도]년 [계정명]은 [금액] 백만원입니다" 형태로 한 문장으로만 답변해주세요."""

            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": "한국어로만 답변하세요. 주어진 형태 그대로만 답변하고 추가 설명은 절대 하지 마세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=50,
                temperature=0.1
            )
            
            best["llm_explanation"] = response['choices'][0]['message']['content'].strip()
            
        except Exception as e:
            print(f"LLM 설명 생성 실패: {e}")

    return best_val, best, f"score={best_score:.4f}"


def calculate_financial_ratio(query: str, model: SentenceTransformer, client: QdrantClient, 
                             collection_name: str, ratio_type: str) -> Tuple[Optional[float], Dict[str, Any], str]:
    """재무비율 계산"""
    anchor_year = extract_year_from_query(query)
    statement_type = detect_statement_type(query) or "balance_sheet"  # 비율 계산은 주로 재무상태표
    if not anchor_year:
        return None, {}, "no_year_found"
    
    ratio_formulas = {
        "current_ratio": {
            "name": "유동비율",
            "formula": "유동자산 ÷ 유동부채",
            "numerator": "유동자산",
            "denominator": "유동부채",
            "description": "단기 채무 상환 능력을 나타내는 지표"
        },
        "debt_ratio": {
            "name": "부채비율",
            "formula": "부채총계 ÷ 자본총계", 
            "numerator": "부채총계",
            "denominator": "자본총계",
            "description": "기업의 재무구조와 안정성을 나타내는 지표"
        },
        "quick_ratio": {
            "name": "당좌비율",
            "formula": "(유동자산 - 재고자산) ÷ 유동부채",
            "numerator": "당좌자산",
            "denominator": "유동부채", 
            "description": "현금화가 용이한 자산으로 단기채무 상환능력을 측정"
        },
        "equity_ratio": {
            "name": "자기자본비율",
            "formula": "자본총계 ÷ 자산총계",
            "numerator": "자본총계",
            "denominator": "자산총계",
            "description": "총자산 중 자기자본이 차지하는 비율"
        }
    }
    
    if ratio_type not in ratio_formulas:
        return None, {}, "unknown_ratio_type"
    
    ratio_info = ratio_formulas[ratio_type]
    
    print(f"🔍 {anchor_year}년 {ratio_info['name']} 계산")
    print("="*80)
    print(f"📐 공식: {ratio_info['formula']}")
    print(f"📝 설명: {ratio_info['description']}")
    print("="*80)
    
    # 분자 값 조회 - 리트리버 방식으로 정확한 데이터 가져오기
    numerator_val, numerator_meta = retrieve_exact_financial_data(
        anchor_year, ratio_info['numerator'], statement_type, "current", 
        model, client, collection_name
    )
    
    # 분모 값 조회 - 리트리버 방식으로 정확한 데이터 가져오기  
    denominator_val, denominator_meta = retrieve_exact_financial_data(
        anchor_year, ratio_info['denominator'], statement_type, "current",
        model, client, collection_name
    )
    
    if numerator_val is None or denominator_val is None:
        missing = []
        if numerator_val is None:
            missing.append(ratio_info['numerator'])
        if denominator_val is None:
            missing.append(ratio_info['denominator'])
        
        print(f"❌ 데이터를 찾을 수 없습니다: {', '.join(missing)}")
        return None, {}, "missing_data"
    
    if denominator_val == 0:
        print(f"❌ {ratio_info['denominator']}이 0이므로 계산할 수 없습니다.")
        return None, {}, "division_by_zero"
    
    # 비율 계산
    ratio_value = numerator_val / denominator_val
    
    # 결과 출력
    print(f"📊 계산 결과:")
    print(f"  • {ratio_info['numerator']}: {format_amount(numerator_val)} 백만원")
    print(f"  • {ratio_info['denominator']}: {format_amount(denominator_val)} 백만원")
    print(f"  • {ratio_info['name']}: {ratio_value:.2f}")
    
    # 백분율로도 표시 (부채비율, 자기자본비율)
    if ratio_type in ["debt_ratio", "equity_ratio"]:
        percentage = ratio_value * 100
        print(f"  • {ratio_info['name']} (%): {percentage:.1f}%")
    
    print("="*80)
    
    # 비율 해석
    interpretation = ""
    if ratio_type == "current_ratio":
        if ratio_value >= 2.0:
            interpretation = "우수한 단기 유동성"
        elif ratio_value >= 1.5:
            interpretation = "양호한 단기 유동성"
        elif ratio_value >= 1.0:
            interpretation = "보통 수준의 단기 유동성"
        else:
            interpretation = "단기 유동성 부족"
    elif ratio_type == "debt_ratio":
        if ratio_value <= 0.3:
            interpretation = "매우 안전한 재무구조"
        elif ratio_value <= 0.6:
            interpretation = "안전한 재무구조"
        elif ratio_value <= 1.0:
            interpretation = "보통 수준의 재무구조"
        else:
            interpretation = "위험한 재무구조"
    
    if interpretation:
        print(f"💡 해석: {interpretation}")
        print("="*80)
    
    result_meta = {
        "ratio_type": ratio_type,
        "ratio_name": ratio_info['name'],
        "formula": ratio_info['formula'],
        "numerator": {
            "name": ratio_info['numerator'],
            "value": numerator_val,
            "formatted": format_amount(numerator_val),
            "meta": numerator_meta
        },
        "denominator": {
            "name": ratio_info['denominator'],
            "value": denominator_val,
            "formatted": format_amount(denominator_val),
            "meta": denominator_meta
        },
        "ratio_value": ratio_value,
        "interpretation": interpretation,
        "year": anchor_year
    }
    
    return ratio_value, result_meta, f"calculated_{ratio_type}"


def search_multi_year_single_values(query: str, model: SentenceTransformer, client: QdrantClient,
                                   collection_name: str) -> Tuple[None, Dict[str, Any], str]:
    """여러 년도의 단일 값을 동시에 조회"""
    # 클라이언트가 None인 경우 재생성
    if client is None:
        try:
            client = get_qdrant_client()
        except Exception as e:
            print(f"❌ Qdrant 클라이언트 생성 실패: {e}")
            return None, {}, "client_error"
            
    years = extract_multiple_years_from_query(query)

    if not years:
        return None, {}, "invalid_multi_year_query"

    print(f"🔍 {', '.join(map(str, years))}년 연도별 비교")
    print("="*80)

    results = {}
    for year in sorted(years):
        # 원래 쿼리에서 연도만 바꿔서 단일 값 조회
        year_query = re.sub(r"(20\d{2}|19\d{2})", str(year), query, count=1)

        statement_type = detect_statement_type(year_query)
        period_type = detect_period_type(year_query) or "current"

        qv = model.encode("query: " + year_query, normalize_embeddings=True).tolist()
        filt = build_filter(
            anchor_year=year,
            statement_type=statement_type,
            period_type=period_type,
            exclude_totals=False,
            exclude_subtotals=False
        )

        res = client.query_points(
            collection_name=collection_name,
            query=qv,
            limit=TOP_K,
            with_payload=True,
            query_filter=filt
        )

        best = None
        best_score = 0
        best_val = None

        for p in res.points:
            payload = p.payload or {}
            meta = payload.get("metadata", payload)

            # 스코어링 로직 (간단화)
            s = p.score or 0

            # period_type 맞으면 가산
            if period_type and meta.get("period_type") == period_type:
                s += 0.02

            # statement_type 맞음 가산  
            if statement_type and meta.get("statement_type") == statement_type:
                s += 0.01

            if s > best_score:
                best_score = s
                best = meta
                best_val = _pick_value(meta)

        if best and best_val is not None:
            results[year] = {
                "value": best_val,
                "meta": best,
                "formatted_value": format_amount(best_val)
            }
            print(f"📊 {year}년: {format_amount(best_val)} 백만원")
        else:
            print(f"❌ {year}년: 데이터를 찾을 수 없습니다")

    print("="*80)

    return None, {"multi_year_single_values": results}, f"found_{len(results)}_years"


def retrieve_exact_financial_data(year: int, account_name: str, statement_type: str, period_type: str,
                                  model: SentenceTransformer, client: QdrantClient, 
                                  collection_name: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """정확한 재무 데이터를 리트리버 방식으로 조회"""
    
    # 계정명 매핑 (정확한 검색을 위해)
    account_mapping = {
        "유동자산": "유동자산",
        "유동부채": "유동부채", 
        "부채총계": "부채총계",
        "자본총계": "자본총계",
        "자산총계": "자산총계"
    }
    
    target_account = account_mapping.get(account_name, account_name)
    
    # 직접 필터링으로 정확한 데이터 조회
    filt = build_filter(
        anchor_year=year,
        statement_type=statement_type,
        period_type=period_type,
        exclude_totals=False,
        exclude_subtotals=False
    )
    
    # 스크롤로 모든 데이터 가져오기
    points, _ = client.scroll(
        collection_name=collection_name,
        scroll_filter=filt,
        with_payload=True,
        with_vectors=False,
        limit=1000
    )
    
    best_match = None
    best_value = None
    best_score = 0
    
    for point in points:
        payload = point.payload or {}
        meta = payload.get("metadata", payload)
        
        point_account = meta.get("account_name", "")
        
        # 정확한 계정명 매칭
        if point_account == target_account:
            # level 확인 (주요 계정은 보통 level이 낮음)
            level = meta.get("level", 999)
            
            # 계정명이 정확히 일치하고, level이 낮을수록 높은 점수
            score = 100 - level
            
            if score > best_score:
                best_score = score
                best_match = meta
                best_value = _pick_value(meta)
    
    print(f"  🔍 {target_account} 조회: {format_amount(best_value) if best_value else 'N/A'} 백만원")
    
    return best_value, best_match or {}


def search_basic_single_value(query: str, model: SentenceTransformer, client: QdrantClient,
                             collection_name: str) -> Tuple[Optional[float], Dict[str, Any]]:
    """기본 단일 값 조회 (비율 계산용, 재귀 호출 방지)"""
    anchor_year = extract_year_from_query(query)
    statement_type = detect_statement_type(query)
    period_type = detect_period_type(query) or "current"

    qv = model.encode("query: " + query, normalize_embeddings=True).tolist()
    filt = build_filter(
        anchor_year=anchor_year,
        statement_type=statement_type,
        period_type=period_type,
        exclude_totals=False,
        exclude_subtotals=False
    )

    res = client.query_points(
        collection_name=collection_name,
        query=qv,
        limit=TOP_K,
        with_payload=True,
        query_filter=filt
    )

    best = None
    best_score = 0
    best_val = None

    for p in res.points:
        payload = p.payload or {}
        meta = payload.get("metadata", payload)
        
        s = p.score or 0
        
        # 기본적인 스코어 부스트
        if period_type and meta.get("period_type") == period_type:
            s += 0.02
        if statement_type and meta.get("statement_type") == statement_type:
            s += 0.01
        
        if s > best_score:
            best_score = s
            best = meta
            best_val = _pick_value(meta)

    return best_val, best or {}


def search_multi_year_hierarchy(query: str, model: SentenceTransformer, client: QdrantClient,
                                collection_name: str) -> Tuple[None, Dict[str, Any], str]:
    """여러 년도의 계층 구조를 동시에 조회"""
    years = extract_multiple_years_from_query(query)
    account_name = extract_account_name(query)
    statement_type = detect_statement_type(query)
    
    if not years or not account_name:
        return None, {}, "invalid_multi_year_query"
    
    print(f"🔍 {', '.join(map(str, years))}년 {account_name} 연도별 비교")
    print("="*80)
    
    all_results = {}
    for year in sorted(years):
        print(f"\n📊 {year}년 {account_name}:")
        print("-"*60)
        
        # 각 연도별로 부모 계정 찾기
        parent_meta = resolve_parent_node(
            query=f"{year}년 {account_name}",
            client=client,
            collection_name=collection_name,
            year=year,
            statement_type=statement_type,
            period_type="current"
        )
        
        if not parent_meta:
            print(f"❌ {year}년 {account_name} 데이터를 찾을 수 없습니다.")
            continue
        
        # 부모 계정의 총계 값 표시
        parent_value = parent_meta.get("value")
        if parent_value:
            formatted_parent_value = format_amount(parent_value)
            print(f"💰 총계: {formatted_parent_value} 백만원")
        
        # 하위 항목들 조회 (당기만)
        parent_id = parent_meta.get("account_id")
        if account_name == "유동자산":
            parent_id = "자산_유동자산"
        elif account_name == "비유동자산":
            parent_id = "자산_비유동자산"
        elif account_name == "유동부채":
            parent_id = "부채_유동부채"
        elif account_name == "비유동부채":
            parent_id = "부채_비유동부채"
        
        children_results = scroll_children_by_parent(
            client=client,
            collection_name=collection_name,
            year=year,
            parent_id=parent_id,
            statement_type=statement_type,
            period_type="current"
        )
        
        if children_results:
            children_rows = build_children_view(children_results)
            all_results[year] = {
                "parent_meta": parent_meta,
                "children": children_rows,
                "total_value": parent_value
            }
            
            # 모든 항목 표시
            for i, item in enumerate(children_rows):
                account = item["account_name"]
                value = format_amount(item.get("amount_current"))
                prefix = "  ├─" if i < len(children_rows) - 1 else "  └─"
                print(f"{prefix} {account}: {value} 백만원")
                
            # AI 요약은 all_results에 저장해서 나중에 별도 출력
            if USE_LLM and llm is not None and children_rows:
                try:
                    context_lines = []
                    for item in children_rows[:7]:  # 상위 7개 항목만 사용
                        name = item["account_name"]
                        value = format_amount(item.get("amount_current"))
                        context_lines.append(f"- {name}: {value} 백만원")
                    
                    context_text = "\n".join(context_lines)
                    
                    prompt = f"""삼성전자 {year}년 {account_name}의 구성 항목:

{context_text}

위 항목들의 이름을 정확히 그대로 쉼표로 구분해서 나열하고 마지막에 "로 구성되어 있습니다"를 붙여서 한 문장으로 답변해주세요."""

                    response = llm.create_chat_completion(
                        messages=[
                            {"role": "system", "content": "한국어로만 답변하세요. 주어진 항목 이름만 나열하고 추가 설명이나 해석은 절대 하지 마세요."},
                            {"role": "user", "content": prompt}
                        ],
                        max_tokens=150,
                        temperature=0.1
                    )
                    
                    llm_answer = response['choices'][0]['message']['content'].strip()
                    all_results[year]["llm_summary"] = llm_answer
                    
                except Exception as e:
                    all_results[year]["llm_summary"] = f"AI 요약 생성 실패: {e}"
        else:
            print(f"❌ {year}년 하위 항목을 찾을 수 없습니다.")
    
    # AI 요약 별도 섹션으로 출력
    ai_summaries = {}
    for year, result in all_results.items():
        if "llm_summary" in result:
            ai_summaries[year] = result["llm_summary"]
    
    if ai_summaries:
        print("\n" + "="*80)
        print("🤖 AI 요약")
        print("="*80)
        for year in sorted(ai_summaries.keys()):
            print(f"📊 {year}년: {ai_summaries[year]}")
        print("="*80)
    
    print("\n📝 참고: 각 연도별 상세 내역은 개별 조회를 이용하세요.")
    print("="*80)
    
    return None, {"multi_year_results": all_results}, f"found_{len(all_results)}_years"

def search_hierarchy_structure(query: str, model: SentenceTransformer, client: QdrantClient,
                               collection_name: str, top_k: int = TOP_K) -> Tuple[None, Dict[str, Any], str]:
    """
    하위 구조 조회 전용 함수 (노트북의 LLaMA 구현 방식 참고)
    """
    anchor_year = extract_year_from_query(query)
    statement_type = detect_statement_type(query)
    period_type = detect_period_type(query) or "current"
    account_name = extract_account_name(query)
    
    if not anchor_year or not account_name:
        return None, {}, "insufficient_info"
    
    print(f"\n🔍 {anchor_year}년 {account_name} 하위 구조 조회")
    print("="*80)
    
    # 1. 부모 노드 탐색 (노트북의 resolve_parent_node 방식)
    parent_meta = resolve_parent_node(
        query=query,
        client=client,
        collection_name=collection_name,
        year=anchor_year,
        statement_type=statement_type,
        period_type=period_type
    )
    
    if not parent_meta:
        print("❌ 부모 계정을 찾을 수 없습니다.")
        return None, {}, "no_parent_found"
    
    parent_name = parent_meta.get("account_name", account_name)
    parent_id = parent_meta.get("account_id")
    
    # 실제 데이터에서 parent_id 형식에 맞게 수정
    if parent_name == "유동자산":
        parent_id = "자산_유동자산"
    elif parent_name == "비유동자산":
        parent_id = "자산_비유동자산"
    elif parent_name == "유동부채":
        parent_id = "부채_유동부채"
    elif parent_name == "비유동부채":
        parent_id = "부채_비유동부채"
    
    # 2. 자식 노드들 검색 - 당기와 전기 모두 가져오기
    children_current = scroll_children_by_parent(
        client=client,
        collection_name=collection_name,
        year=anchor_year,
        parent_id=parent_id,
        statement_type=statement_type,
        period_type="current"
    )
    
    children_previous = scroll_children_by_parent(
        client=client,
        collection_name=collection_name,
        year=anchor_year,
        parent_id=parent_id,
        statement_type=statement_type,
        period_type="previous"
    )
    
    # 당기와 전기 데이터 병합
    children_results = children_current + children_previous
    
    if not children_results:
        print(f"❌ {parent_name}의 하위 항목을 찾을 수 없습니다.")
        return None, {}, "no_children_found"
    
    # 3. 구조화된 뷰 생성 (노트북의 build_children_view 방식)
    children_rows = build_children_view(children_results)
    
    # 4. 출력 (LLM 사용 가능하면 자연어 생성 추가)
    # 부모 계정의 총계 값 표시
    parent_value = parent_meta.get("value")
    if parent_value:
        formatted_parent_value = format_amount(parent_value)
        print(f"📊 {anchor_year}년 {parent_name} 총계: {formatted_parent_value} 백만원")
        print("="*80)
        print(f"📋 {parent_name} 하위 구성 항목:")
        print("="*80)
    else:
        print(f"📊 {anchor_year}년 {statement_type} {period_type} - {parent_name} 하위 구조")
        print("="*80)
    
    # LLM으로 자연어 설명 생성 (선택적) 
    llm_answer = None
    if USE_LLM and llm is not None and children_rows:
        try:
            # 간단한 컨텍스트 구성
            context_lines = []
            for item in children_rows[:10]:  # 상위 10개만 사용
                name = item["account_name"]
                value = format_amount(item.get("amount_current"))
                context_lines.append(f"- {name}: {value} 백만원")
            
            context_text = "\n".join(context_lines)
            
            prompt = f"""삼성전자 {anchor_year}년 {parent_name}의 구성 항목:

{context_text}

위 항목들의 이름을 정확히 그대로 쉼표로 구분해서 나열하고 마지막에 "로 구성되어 있습니다"를 붙여서 한 문장으로 답변해주세요."""

            response = llm.create_chat_completion(
                messages=[
                    {"role": "system", "content": "한국어로만 답변하세요. 주어진 항목 이름만 나열하고 추가 설명이나 해석은 절대 하지 마세요."},
                    {"role": "user", "content": prompt}
                ],
                max_tokens=150,
                temperature=0.1
            )
            
            llm_answer = response['choices'][0]['message']['content'].strip()
            print("🤖 AI 분석:")
            print(llm_answer)
            print("="*80)
            
        except Exception as e:
            print(f"⚠️  LLM 생성 실패: {e}")
    
    for item in children_rows:
        account_name = item["account_name"]
        current_value = item.get("amount_current")
        previous_value = item.get("amount_previous")
        unit = item.get("unit", "백만원")
        notes = item.get("notes", "")
        notes_str = f" (주석: {notes})" if notes else ""
        
        # 당기와 전기 값 모두 표시
        current_str = format_amount(current_value) if current_value else "-"
        previous_str = format_amount(previous_value) if previous_value else "-"
        
        print(f"├─ {account_name}: 당기 {current_str} / 전기 {previous_str} {unit}{notes_str}")
    
    print("─"*80)
    print(f"📝 참고: 정확한 총합은 감사보고서 원본을 확인하세요.")
    print("="*80)
    
    result_meta = {"hierarchy_results": children_rows}
    if llm_answer:
        result_meta["llm_answer"] = llm_answer
    
    return None, result_meta, f"found_{len(children_rows)}_items"


# ==========================
# 노트북 스타일 헬퍼 함수들 (LLaMA 구현 방식)
# ==========================
def resolve_parent_node(query: str, client: QdrantClient, collection_name: str,
                        year: int, statement_type: str = "balance", period_type: str = "current",
                        level: int = 2, top_k: int = 10):
    """
    질의에서 부모 노드를 자동으로 찾아 반환 (노트북 방식)
    """
    filt = build_filter(
        anchor_year=year,
        statement_type=statement_type,
        period_type=period_type,
        min_level=level,
        exclude_totals=True,
        exclude_subtotals=False,
    )
    
    qv = embed_model.encode("query: " + query, normalize_embeddings=True).tolist()
    res = client.query_points(
        collection_name=collection_name,
        query=qv,
        limit=top_k,
        with_payload=True,
        query_filter=filt
    )

    q_norm = collapse_ko_spaced(query.replace(" ", ""))
    best = None
    best_score = 0
    
    # 정확한 매칭을 위한 우선순위 처리
    target_keywords = {
        "유동자산": ["유동자산"],
        "비유동자산": ["비유동자산"],
        "유동부채": ["유동부채"],
        "비유동부채": ["비유동부채"],
        "영업활동현금흐름": ["영업활동"],
        "투자활동현금흐름": ["투자활동"],
        "재무활동현금흐름": ["재무활동"]
    }
    
    for p in res.points:
        payload = p.payload or {}
        meta = payload.get("metadata", payload)
        name = collapse_ko_spaced(str(meta.get("account_name", "")))
        
        hier = meta.get("hierarchy", [])
        last_h = ""
        if isinstance(hier, list) and len(hier) > 0:
            last_h = collapse_ko_spaced(str(hier[-1]))
        
        # 정확한 계정명 매칭 우선
        score = 0
        for target_name, keywords in target_keywords.items():
            if name == target_name:
                for kw in keywords:
                    if kw in q_norm:
                        score = 100  # 최고 우선순위
                        break
                break
        
        # 일반적인 문자열 매칭
        if score == 0:
            if name and name in q_norm:
                score = 50
            elif last_h and last_h in q_norm:
                score = 30
        
        if score > best_score:
            best_score = score
            best = meta
            if score == 100:  # 정확한 매칭이면 즉시 반환
                break

    if not best and res.points:
        best_payload = res.points[0].payload or {}
        best = best_payload.get("metadata", best_payload)

    return best

def scroll_children_by_parent(client: QdrantClient, collection_name: str, year: int,
                             parent_id: str, statement_type: str = "balance", 
                             period_type: str = "current", min_level: int = 3,
                             exclude_totals: bool = True, exclude_subtotals: bool = False,
                             limit: int = 256):
    """
    부모 ID로 자식들을 전량 회수 (노트북의 scroll 방식)
    """
    filt = build_filter(
        anchor_year=year,
        statement_type=statement_type,
        period_type=period_type,
        parent_id=parent_id,
        min_level=min_level,
        exclude_totals=exclude_totals,
        exclude_subtotals=exclude_subtotals
    )
    
    out = []
    next_offset = None
    while True:
        points, next_offset = client.scroll(
            collection_name=collection_name,
            scroll_filter=filt,
            with_payload=True,
            with_vectors=False,
            limit=limit,
            offset=next_offset
        )
        
        for p in points:
            payload = p.payload or {}
            text = payload.get("text")
            if not text:
                continue
            meta = payload.get("metadata", {})
            if not meta:
                meta = {k: v for k, v in payload.items() if k != "text"}
            
            item = {"score": None, "text": text}
            item.update(meta)
            out.append(item)
            
        if not next_offset:
            break
    
    out.sort(key=lambda x: (x.get("level", 999), str(x.get("account_name", ""))))
    return out

def build_children_view(results: list):
    """
    검색 결과를 구조화된 자식 뷰로 변환 (노트북 방식)
    """
    AMOUNT_KEYS_CUR = ["value", "value_current", "amount_current", "당기"]
    AMOUNT_KEYS_PREV = ["value_previous", "amount_prev", "전기"]
    NOTE_KEYS = ["note", "notes", "주석", "footnote", "footnotes"]
    
    def _pick(payload: dict, keys):
        for k in keys:
            if k in payload and payload[k] not in (None, ""):
                v = payload[k]
                if isinstance(v, str):
                    vs = v.replace(",", "")
                    if vs.replace("-", "").isdigit():
                        try:
                            return float(vs)
                        except Exception:
                            return v
                return v
        return None
    
    def _parse_amounts_from_text(text: str):
        if not text: return (None, None)
        import re
        nums = re.findall(r"(\d{1,3}(?:,\d{3})+|\d{4,})", text)
        cur = None; prev = None
        if "당기" in text:
            m = re.search(r"당기[^0-9]*([\\d,]+)", text)
            if m: cur = m.group(1)
        if "전기" in text:
            m = re.search(r"전기[^0-9]*([\\d,]+)", text)
            if m: prev = m.group(1)
        if cur is None and nums:
            cur = nums[0]
        if prev is None and len(nums) >= 2:
            prev = nums[1]
        def to_num(x):
            if x is None: return None
            try: return float(x.replace(",", ""))
            except: return x
        return to_num(cur), to_num(prev)
    
    # 계정별로 당기/전기 데이터를 병합
    account_data = {}
    for r in results:
        aid = r.get("account_id")
        if not aid:
            continue
            
        if aid not in account_data:
            account_data[aid] = {
                "account_id": aid,
                "account_name": r.get("account_name"),
                "parent_id": r.get("parent_id"),
                "level": r.get("level"),
                "hierarchy": r.get("hierarchy"),
                "report_year": r.get("report_year"),
                "unit": r.get("unit", "백만원"),
                "amount_current": None,
                "amount_previous": None,
                "notes": None
            }
        
        # period_type에 따라 값 할당
        period_type = r.get("period_type")
        value = r.get("value")
        notes = _pick(r, NOTE_KEYS)
        
        if period_type == "current":
            account_data[aid]["amount_current"] = value
        elif period_type == "previous":
            account_data[aid]["amount_previous"] = value
            
        if notes and not account_data[aid]["notes"]:
            account_data[aid]["notes"] = notes
    
    rows = list(account_data.values())
    

    rows.sort(key=lambda x: (x.get("level", 999), str(x.get("account_name") or "")))
    return rows


# ==========================
# 계층 구조 검색 (하위 항목 조회)
# ==========================
def search_hierarchy_breakdown(parent_account: str, year: int, period_type: str = "current",
                               statement_type: str = "balance", model: SentenceTransformer = None,
                               client: QdrantClient = None, collection_name: str = COLLECTION_NAME,
                               top_k: int = 50) -> List[Dict[str, Any]]:
    """
    특정 계정의 하위 항목들을 조회
    예: "비유동자산" → [유형자산, 무형자산, 투자자산, 기타비유동자산, ...]
    """
    if model is None:
        model = embed_model
    if client is None:
        client = globals()['client']
    
    # 부모 계정을 먼저 찾아서 account_id 확인
    parent_query = f"{year}년 {statement_type} {period_type} {parent_account}"
    qv = model.encode("query: " + parent_query, normalize_embeddings=True).tolist()
    
    filt = build_filter(
        anchor_year=year,
        statement_type=statement_type,
        period_type=period_type
    )
    
    res = client.query_points(
        collection_name=collection_name,
        query=qv,
        limit=top_k,
        with_payload=True,
        query_filter=filt
    )
    
    parent_id = None
    parent_level = None
    
    # 부모 계정 찾기
    for p in res.points:
        payload = p.payload or {}
        meta = payload.get("metadata", payload)
        account_name = meta.get("account_name", "")
        
        if parent_account in account_name or account_name in parent_account:
            parent_id = meta.get("account_id")
            parent_level = meta.get("level", 0)
            break
    
    if not parent_id:
        return []
    
    # 하위 항목들 검색 (parent_id 기반)
    child_filter = build_filter(
        anchor_year=year,
        statement_type=statement_type,
        period_type=period_type,
        parent_id=parent_id,
        min_level=parent_level + 1 if parent_level is not None else None
    )
    
    # 하위 항목들을 위한 더 넓은 검색
    child_res = client.scroll(
        collection_name=collection_name,
        scroll_filter=child_filter,
        limit=100,
        with_payload=True
    )
    
    results = []
    seen_accounts = set()  # 중복 제거용
    
    for p in child_res[0]:  # scroll returns (points, next_page_offset)
        payload = p.payload or {}
        meta = payload.get("metadata", payload)
        
        account_name = meta.get("account_name", "")
        account_id = meta.get("account_id", "")
        
        if not account_name or account_name == parent_account:
            continue
            
        # 계정명+ID 조합으로 중복 체크
        unique_key = f"{account_name}_{account_id}"
        if unique_key in seen_accounts:
            continue
        seen_accounts.add(unique_key)
            
        value = _pick_value(meta)
        if value is not None:
            results.append({
                "account_name": account_name,
                "value": value,
                "formatted_value": format_amount(value),
                "level": meta.get("level", 0),
                "unit": meta.get("unit", ""),
                "hierarchy": meta.get("hierarchy", []),
                "account_id": account_id
            })
    
    # 레벨과 계정명으로 정렬
    results.sort(key=lambda x: (x["level"], x["account_name"]))
    return results


def print_hierarchy_breakdown(parent_account: str, year: int, period_type: str = "current",
                             statement_type: str = "balance"):
    """비유동자산 하위 항목들을 예쁘게 출력"""
    print(f"\n{'='*80}")
    print(f"📊 {year}년 {statement_type} {period_type} - {parent_account} 하위 구조")
    print(f"{'='*80}")
    
    breakdown = search_hierarchy_breakdown(
        parent_account=parent_account,
        year=year,
        period_type=period_type,
        statement_type=statement_type
    )
    
    if not breakdown:
        print(f"❌ {parent_account}의 하위 항목을 찾을 수 없습니다.")
        return
    
    for item in breakdown:
        level = item["level"]
        indent = "  " * max(0, level - 2)  # 적절한 들여쓰기
        account_name = item["account_name"]
        formatted_value = item["formatted_value"]
        unit = item["unit"]
        
        print(f"{indent}├─ {account_name}: {formatted_value} {unit}")
    
    print(f"{'─'*80}")
    print(f"📝 참고: 정확한 총합은 감사보고서 원본을 확인하세요.")
    print(f"{'='*80}")


# ==========================
# 테스트 러너
# ==========================
def run_batch(questions: list, answers: list = None, title: str = "Batch"):
    print("\n" + "="*110)
    print(f"[{title}] 총 {len(questions)}개 질문")
    print("="*110)

    ok = 0
    for i, q in enumerate(questions, 1):
        pred, meta, why = search_single_value(q, embed_model, client, COLLECTION_NAME, top_k=TOP_K)
        pred_str = format_amount(pred)

        # 메타 디버그
        acct = meta.get("account_name", "-")
        stmt = meta.get("statement_type", "-")
        period = meta.get("period_type", "-")
        year = meta.get("anchor_fiscal_year", meta.get("report_year", "-"))
        unit = meta.get("unit", "")

        # 정답 비교(있을 때만)
        if answers is not None and i <= len(answers):
            gt = answers[i-1]
            # '-'는 미제시로 취급
            pnorm = normalize_numeric_str(pred_str)
            gtnorm = normalize_numeric_str(gt)
            match = (pnorm == gtnorm)
            mark = "✅" if match else "❌"
            if match: ok += 1
            print(f"{i:2d}. Q: {q}")
            print(f"    → 예측: {pred_str}   (단위: {unit})   {mark}")
            print(f"      정답: {gt}")
        else:
            print(f"{i:2d}. Q: {q}")
            print(f"    → 예측: {pred_str}   (단위: {unit})")

        print(f"      매칭: [{year}] {stmt}/{period}  계정명='{acct}'  ({why})")
        print("-"*110)

    if answers is not None:
        print(f"정답 일치: {ok}/{len(questions)} ({ok/len(questions)*100:.1f}%)")


# ==========================
# 메인 (질문/정답 + 추가질문)
# ==========================
if __name__ == "__main__":
    print("🚀 삼성전자 감사보고서 RAG 시스템 초기화 완료")
    print("💡 사용 방법:")
    print("  - 단일 값 조회: '2024년 재무상태표 상 당기 유동자산은 얼마인가?'")
    print("  - 계층 구조 조회: '2024년 비유동자산 하위 구조 알려줘'")
    print("  - 지원 연도: 2014-2024")
    print("  - 지원 재무제표: 재무상태표, 손익계산서, 현금흐름표, 포괄손익계산서, 자본변동표")
    if USE_LLM and llm is not None:
        print("🤖 LLaMA 모델 활성화됨 - AI 분석 제공")
    else:
        print("📊 기본 RAG 모드")
    print("\n" + "="*80)
    
    # 간단한 작동 테스트
    test_queries = [
        "2024년 재무상태표 상 당기 자산총계는 얼마인가?",
        "2024년 비유동자산 하위 구조 알려줘"
    ]
    
    for test_query in test_queries:
        print(f"\n📋 테스트: {test_query}")
        pred, meta, why = search_single_value(test_query, embed_model, client, COLLECTION_NAME, TOP_K)
        if pred is not None:
            formatted_value = format_amount(pred)
            print(f"✅ 답변: {formatted_value} 백만원")
        else:
            print(f"결과: {why}")
    
    print("="*80)
    
    # 원본 테스트들은 주석 처리
    """
    questions = [
        "2014년 재무상태표 상 당기 유동자산은 얼마인가?",
        "2014년 현금흐름표 상 당기 영업활동 현금흐름은 얼마인가?",
        "2015년 당기 비유동자산은 재무상태표에서 얼마인가?",
        "2015년 손익계산서 상 당기순이익은 얼마인가?",
        "2016년 재무상태표 상 당기 단기금융상품은 얼마인가요?",
        "2016년 포괄손익계산서 상 당기 총포괄이익은 얼마니?",
        "2016년 자본변동표 상 자기주식의 취득은 얼마인가?",
        "2017년 당기 매출채권은 재무상태표에 따르면 얼마냐?",
        "2017년 재무상태표상 전기 현금및현금성자산은 얼마입니까?",
        "2018년 당기 미수금은 재무상태표에서 얼마인가?",
        "2018년 손익계산서상 매출총이익은 얼마인가요?",
        "2019년 재무상태표상 종속기업, 관계기업 및 공동기업 투자는 얼마인가요?",
        "2019년 현금흐름표 상 이익잉여금 배당은 얼마인가요?",
        "2019년 손익계산서상 기본주당이익은 얼마인가요?",
        "2020년 재무상태표 상 자산총계는?",
        "2020년 손익계산서 상 판매비와관리비는 얼마인가요?",
        "2021년 재무상태표상 당기 기타포괄손익-공정가치금융자산은 얼마인가요?",
        # "2021년 재무상태표에서 당기 유동비율을 계산하면 얼마인가요?",  # 계산형은 별도 경로 필요
        "2021년 손익계산서 상 당기 금융비용은 얼마인가요?",
        "2022년 재무상태표상 당기 비유동부채는 얼마인가?",
        "2022년 손익계산서 상 당기 법인세비용은 얼마니?",
        "2022년 당기 현금흐름표 상 투자활동 현금흐름은 얼마인가?",
        "2023년 재무상태표 상 재고자산은 얼마인가?",
        "2023년 손익계산서 상 당기 영업이익은 얼마인가?",
        "2024년에는 재무상태표상 당기 무형자산이 얼마야?",
        "2024년 재무상태표 상 당기 우선주자본금은 얼마인가?",
        "2024년 손익계산서상 당기 법인세비용은 얼마야?",
        "2017년 재무상태표상 당기 매각예정분류자산은 얼마인가요?",
    ]

    answers = [
        "62,054,773",
        "18,653,817",
        "101,967,575",
        "12,238,469",
        "30,170,656",
        "11,887,806",
        "(7,707,938)",
        "27,881,777",
        "3,778,371",
        "1,515,079",
        "68,715,364",
        "56,571,252",
        "(9,618,210)",
        "2,260",
        "229,664,427",
        "29,038,798",
        "1,662,532",
        "3,698,675",
        "4,581,512",
        "4,273,142",
        "(28,123,886)",
        "29,338,151",
        "(11,526,297)",
        "10,496,956",
        "119,467",
        "(1,832,987)",
        "-"
    ]

    # 기본 배치 실행 (정답 비교)
    run_batch(questions, answers, title="Given QA (with Ground Truth)")

    # ==========================
    # 추가 테스트 질문 (정답 미지정 → 예측만 확인)
    # ==========================
    extra_questions = [
        "2014년 재무상태표 상 전기 유동자산은 얼마인가?",
        "2018년 현금흐름표 상 당기 재무활동 현금흐름은 얼마인가?",
        "2017년 재무상태표 상 당기 기타유동자산은 얼마인가?",
        "2019년 포괄손익계산서 상 당기 총포괄이익은 얼마인가?",
        "2021년 재무상태표 상 전기 비유동부채는 얼마인가?",
        "2022년 손익계산서 상 전기 법인세비용은 얼마니?",
        "2023년 재무상태표 상 당기 현금및현금성자산은 얼마인가?",
        "2016년 손익계산서 상 전기 당기순이익은 얼마인가?",
        "2018년 현금흐름표 상 전기 영업활동 현금흐름은 얼마인가?",
        "2020년 재무상태표 상 전기 자산총계는 얼마인가?",
        "2017년 손익계산서 상 당기 매출액은 얼마인가?",
        "2020년 현금흐름표 상 당기 투자활동 현금흐름은 얼마인가?"
    ]
    run_batch(extra_questions, answers=None, title="Extra QA (Prediction Only)")
    
    # ==========================
    # 비유동자산 하위 구조 조회 테스트
    # ==========================
    print("\n" + "🔍 비유동자산 하위 구조 분석을 시작합니다...")
    
    # 여러 연도의 비유동자산 하위 구조 조회
    test_years = [2020, 2021, 2022, 2023, 2024]
    
    for year in test_years:
        print_hierarchy_breakdown("비유동자산", year, "current", "balance")
        
    # 추가로 다른 계정도 테스트
    print("\n" + "🔍 추가 계정 구조 분석...")
    print_hierarchy_breakdown("유동자산", 2024, "current", "balance")
    print_hierarchy_breakdown("영업활동현금흐름", 2024, "current", "cashflow")
    """
