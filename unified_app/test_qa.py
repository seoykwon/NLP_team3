#!/usr/bin/env python3
"""
각 RAG 시스템 질의응답 테스트
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

# 프로젝트 루트 경로 설정
project_root = Path(__file__).parent.parent
sys.path.append(str(project_root))
sys.path.append(str(project_root / "audit" / "scripts"))

def test_legal_qa():
    """상법 시스템 질의응답 테스트"""
    print("=== 상법 시스템 질의응답 테스트 ===")
    
    try:
        # main_simple.py에서 함수 가져오기
        sys.path.append(str(Path(__file__).parent))
        from main_simple import create_legal_rag_system
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ API 키가 없습니다.")
            return
        
        print("🔄 상법 시스템 초기화 중...")
        legal_system = create_legal_rag_system(api_key)
        
        # 테스트 질문
        questions = [
            "상법상 이사의 의무는 무엇인가요?",
            "준비금의 자본전입은 이사회에서 결정할 수 있는가?"
        ]
        
        for i, question in enumerate(questions, 1):
            print(f"\n🔄 질문 {i}: {question}")
            try:
                answer, results = legal_system.search_and_answer(question, topk=3)
                print(f"✅ 답변: {answer[:200]}...")
                print(f"📄 참조 문서 수: {len(results)}")
            except Exception as e:
                print(f"❌ 답변 생성 실패: {e}")
    
    except Exception as e:
        print(f"❌ 상법 시스템 테스트 실패: {e}")

def test_kifrs_qa():
    """K-IFRS 시스템 질의응답 테스트"""
    print("\n=== K-IFRS 시스템 질의응답 테스트 ===")
    
    try:
        # main_simple.py에서 함수 가져오기
        sys.path.append(str(Path(__file__).parent))
        from main_simple import create_kifrs_rag_system
        
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ API 키가 없습니다.")
            return
        
        print("🔄 K-IFRS 시스템 초기화 중...")
        kifrs_system = create_kifrs_rag_system(api_key)
        
        # 테스트 질문
        questions = [
            "개발비 자산 인식 요건은 무엇인가요?",
            "리스 회계처리 방법에 대해 설명해주세요"
        ]
        
        for i, question in enumerate(questions, 1):
            print(f"\n🔄 질문 {i}: {question}")
            try:
                answer, results = kifrs_system.search_and_answer(question, topk=3)
                print(f"✅ 답변: {answer[:200]}...")
                print(f"📄 참조 문서 수: {len(results)}")
            except Exception as e:
                print(f"❌ 답변 생성 실패: {e}")
    
    except Exception as e:
        print(f"❌ K-IFRS 시스템 테스트 실패: {e}")

def main():
    print("🧪 RAG 시스템 질의응답 테스트 시작\n")
    
    test_legal_qa()
    test_kifrs_qa()
    
    print("\n🎉 테스트 완료!")

if __name__ == "__main__":
    main()
