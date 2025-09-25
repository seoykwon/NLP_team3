#!/usr/bin/env python3
"""
통합 RAG 시스템 공통 유틸리티
"""

import os
from typing import Optional
import logging

logger = logging.getLogger(__name__)

def load_openai_api_key() -> Optional[str]:
    """OpenAI API 키 로드"""
    # 환경변수에서 API 키 확인
    api_key = os.getenv("OPENAI_API_KEY")
    if api_key:
        return api_key
    
    # .env 파일에서 API 키 확인
    try:
        from dotenv import load_dotenv
        load_dotenv()
        api_key = os.getenv("OPENAI_API_KEY")
        if api_key:
            return api_key
    except ImportError:
        pass
    
    return None

def check_data_paths():
    """데이터 경로 확인"""
    from pathlib import Path
    
    project_root = Path(__file__).parent.parent.parent
    
    paths = {
        "audit_data": project_root / "audit" / "storage",
        "extra_data": project_root / "extra",
        "graph_data": project_root / "graph" / "data"
    }
    
    status = {}
    for name, path in paths.items():
        status[name] = path.exists()
    
    return status

def format_amount(value, unit="백만원"):
    """금액 포맷팅"""
    if value is None:
        return "N/A"
    
    try:
        if isinstance(value, str):
            # 문자열에서 숫자 추출
            import re
            numbers = re.findall(r'-?\d+(?:,\d{3})*(?:\.\d+)?', value.replace(',', ''))
            if numbers:
                value = float(numbers[0])
            else:
                return value
        
        # 숫자 포맷팅
        if abs(value) >= 1000000:
            return f"{value/1000000:.1f}조 {unit}"
        elif abs(value) >= 1000:
            return f"{value/1000:.1f}억 {unit}"
        else:
            return f"{value:,.0f} {unit}"
    
    except (ValueError, TypeError):
        return str(value)

def get_system_status():
    """시스템 상태 확인"""
    status = {
        "api_key": load_openai_api_key() is not None,
        "data_paths": check_data_paths()
    }
    return status
