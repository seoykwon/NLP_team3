#!/usr/bin/env python3
"""
웹사이트에서 실제 RAG 시스템 테스트
"""

import os
import sys
from pathlib import Path

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# 프로젝트 루트 경로 설정 (unified_app의 부모 디렉토리)
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "audit" / "scripts"))

def test_web_systems():
    """웹사이트에서 사용하는 것과 동일한 방식으로 테스트"""
    print("🌐 웹사이트 RAG 시스템 테스트")
    
    # main_simple.py에서 함수들 import
    sys.path.append(str(Path(__file__).parent))
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ API 키가 없습니다.")
        return
    
    print(f"✅ API 키 확인됨: {api_key[:10]}...")
    print(f"📁 프로젝트 루트: {project_root.absolute()}")
    
    # 경로 확인
    extra_path = project_root / "extra"
    audit_path = project_root / "audit" / "scripts"
    
    print(f"📂 Extra 폴더 존재: {extra_path.exists()}")
    print(f"📂 Audit 스크립트 존재: {audit_path.exists()}")
    
    if extra_path.exists():
        print(f"📂 상법 폴더 존재: {(extra_path / '상법 2').exists()}")
        print(f"📂 K-IFRS 폴더 존재: {(extra_path / '기준서 2').exists()}")
    
    # 실제 함수들 import 및 테스트
    try:
        from main_simple import process_legal_question, process_kifrs_question
        
        print("\n=== 상법 시스템 테스트 ===")
        legal_answer = process_legal_question("상법상 이사의 의무는 무엇인가요?", api_key)
        print(f"상법 답변: {legal_answer[:100]}...")
        
        print("\n=== K-IFRS 시스템 테스트 ===")
        kifrs_answer = process_kifrs_question("개발비 자산 인식 요건은 무엇인가요?", api_key)
        print(f"K-IFRS 답변: {kifrs_answer[:100]}...")
        
    except Exception as e:
        print(f"❌ 시스템 테스트 실패: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_web_systems()
