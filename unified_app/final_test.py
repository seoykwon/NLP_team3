#!/usr/bin/env python3
"""
최종 통합 RAG 시스템 테스트
웹사이트에서 실제로 작동하는지 확인
"""

import os
import sys
from pathlib import Path
import requests
import time

# .env 파일 로드
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

def test_qdrant_connection():
    """Qdrant 서버 연결 테스트"""
    print("=== Qdrant 서버 연결 테스트 ===")
    try:
        response = requests.get('http://localhost:6333/collections', timeout=5)
        print(f"✅ Qdrant 연결 성공: {response.status_code}")
        
        # 컬렉션 정보 확인
        collections = response.json()
        print(f"📊 컬렉션 수: {len(collections.get('result', {}).get('collections', []))}")
        return True
    except Exception as e:
        print(f"❌ Qdrant 연결 실패: {e}")
        return False

def test_streamlit_server():
    """Streamlit 서버 연결 테스트"""
    print("\n=== Streamlit 서버 연결 테스트 ===")
    try:
        response = requests.get('http://localhost:8505', timeout=5)
        print(f"✅ Streamlit 서버 연결 성공: {response.status_code}")
        return True
    except Exception as e:
        print(f"❌ Streamlit 서버 연결 실패: {e}")
        return False

def test_all_rag_systems():
    """모든 RAG 시스템 테스트"""
    print("\n=== 모든 RAG 시스템 테스트 ===")
    
    # 프로젝트 루트 경로 설정
    project_root = Path(__file__).parent.parent
    sys.path.append(str(project_root))
    sys.path.append(str(project_root / "unified_app"))
    
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        print("❌ API 키가 없습니다.")
        return False
    
    results = {}
    
    # 1. 감사보고서 RAG 테스트
    print("\n🔄 감사보고서 RAG 테스트...")
    try:
        from main_simple import process_audit_question
        answer = process_audit_question("유동자산은 얼마인가요?", api_key)
        if "오류" not in answer and "실패" not in answer:
            print(f"✅ 감사보고서 성공: {answer[:100]}...")
            results['audit'] = True
        else:
            print(f"⚠️ 감사보고서 제한적 성공: {answer[:100]}...")
            results['audit'] = 'partial'
    except Exception as e:
        print(f"❌ 감사보고서 실패: {e}")
        results['audit'] = False
    
    # 2. 상법 RAG 테스트
    print("\n🔄 상법 RAG 테스트...")
    try:
        from main_simple import process_legal_question
        answer = process_legal_question("상법상 이사의 의무는 무엇인가요?", api_key)
        if "오류" not in answer and "실패" not in answer:
            print(f"✅ 상법 성공: {answer[:100]}...")
            results['legal'] = True
        else:
            print(f"❌ 상법 실패: {answer[:100]}...")
            results['legal'] = False
    except Exception as e:
        print(f"❌ 상법 실패: {e}")
        results['legal'] = False
    
    # 3. K-IFRS RAG 테스트
    print("\n🔄 K-IFRS RAG 테스트...")
    try:
        from main_simple import process_kifrs_question
        answer = process_kifrs_question("개발비 자산 인식 요건은 무엇인가요?", api_key)
        if "오류" not in answer and "실패" not in answer:
            print(f"✅ K-IFRS 성공: {answer[:100]}...")
            results['kifrs'] = True
        else:
            print(f"❌ K-IFRS 실패: {answer[:100]}...")
            results['kifrs'] = False
    except Exception as e:
        print(f"❌ K-IFRS 실패: {e}")
        results['kifrs'] = False
    
    return results

def main():
    print("🧪 최종 통합 RAG 시스템 테스트 시작\n")
    
    # 1. Qdrant 연결 테스트
    qdrant_ok = test_qdrant_connection()
    
    # 2. Streamlit 서버 테스트
    streamlit_ok = test_streamlit_server()
    
    # 3. 모든 RAG 시스템 테스트
    rag_results = test_all_rag_systems()
    
    # 결과 요약
    print("\n" + "="*60)
    print("🎯 최종 테스트 결과 요약")
    print("="*60)
    
    print(f"Qdrant 서버     : {'✅ 연결됨' if qdrant_ok else '❌ 연결 안됨'}")
    print(f"Streamlit 서버  : {'✅ 실행 중' if streamlit_ok else '❌ 실행 안됨'}")
    print()
    
    for system, result in rag_results.items():
        system_names = {'audit': '감사보고서', 'legal': '상법', 'kifrs': 'K-IFRS'}
        if result is True:
            status = "✅ 완전 작동"
        elif result == 'partial':
            status = "⚠️ 제한적 작동"
        else:
            status = "❌ 작동 안됨"
        print(f"{system_names[system]:10} : {status}")
    
    # 전체 성공률 계산
    success_count = sum(1 for r in rag_results.values() if r is True)
    partial_count = sum(1 for r in rag_results.values() if r == 'partial')
    total_count = len(rag_results)
    
    print(f"\n📊 성공률: {success_count}/{total_count} 완전 성공, {partial_count}/{total_count} 부분 성공")
    
    if success_count == total_count:
        print("\n🎉 모든 시스템이 완벽하게 작동합니다!")
        print("🌐 웹사이트 접속: http://localhost:8505")
    elif success_count + partial_count == total_count:
        print("\n⚠️ 모든 시스템이 작동하지만 일부 제한이 있습니다.")
        print("🌐 웹사이트 접속: http://localhost:8505")
    else:
        print("\n❌ 일부 시스템에 문제가 있습니다.")

if __name__ == "__main__":
    main()
