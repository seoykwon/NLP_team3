#!/usr/bin/env python3
"""
각 RAG 시스템 테스트 스크립트
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

def test_audit_system():
    """감사보고서 시스템 테스트"""
    print("=== 감사보고서 시스템 테스트 ===")
    try:
        # 경로 추가
        audit_scripts_path = project_root / "audit" / "scripts"
        if str(audit_scripts_path) not in sys.path:
            sys.path.insert(0, str(audit_scripts_path))
        
        from hierarchy_rag_qa_system import HierarchyRAGQASystem
        
        # API 키 확인
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OpenAI API 키가 설정되지 않았습니다.")
            return False
        
        print("✅ 모듈 import 성공")
        
        # 시스템 초기화 테스트
        print("🔄 시스템 초기화 중...")
        rag_system = HierarchyRAGQASystem(openai_api_key=api_key)
        print("✅ 시스템 초기화 성공")
        
        # 간단한 질문 테스트
        print("🔄 질문 테스트 중...")
        result = rag_system.ask_question("유동자산은 얼마인가요?", top_k=5, score_threshold=0.5)
        print(f"✅ 답변 생성 성공: {result['answer'][:100]}...")
        
        return True
        
    except Exception as e:
        print(f"❌ 감사보고서 시스템 오류: {e}")
        return False

def test_legal_system():
    """상법 시스템 테스트"""
    print("\n=== 상법 시스템 테스트 ===")
    try:
        import json
        import numpy as np
        import faiss
        from sentence_transformers import SentenceTransformer
        from openai import OpenAI
        
        # API 키 확인
        api_key = os.getenv("OPENAI_API_KEY")
        if not api_key:
            print("❌ OpenAI API 키가 설정되지 않았습니다.")
            return False
        
        # 데이터 경로 확인
        base_path = project_root / "extra" / "상법 2"
        index_path = base_path / "kcc_index_json" / "kcc.index"
        ids_path = base_path / "kcc_index_json" / "ids.npy"
        metas_path = base_path / "kcc_index_json" / "metas.json"
        
        print(f"📁 데이터 경로: {base_path}")
        print(f"📄 인덱스 파일 존재: {index_path.exists()}")
        print(f"📄 IDs 파일 존재: {ids_path.exists()}")
        print(f"📄 메타 파일 존재: {metas_path.exists()}")
        
        if not all([index_path.exists(), ids_path.exists(), metas_path.exists()]):
            print("❌ 상법 데이터 파일이 없습니다.")
            return False
        
        # 파일 로드 테스트
        print("🔄 데이터 로드 중...")
        index = faiss.read_index(str(index_path))
        ids = np.load(ids_path, allow_pickle=True).tolist()
        with open(metas_path, "r", encoding="utf-8") as f:
            metas = json.load(f)
        
        print(f"✅ 인덱스 로드 성공: {index.ntotal}개 벡터")
        print(f"✅ 메타데이터 로드 성공: {len(metas)}개 문서")
        
        return True
        
    except Exception as e:
        print(f"❌ 상법 시스템 오류: {e}")
        return False

def test_kifrs_system():
    """K-IFRS 시스템 테스트"""
    print("\n=== K-IFRS 시스템 테스트 ===")
    try:
        import json
        import numpy as np
        
        # 데이터 경로 확인
        base_path = project_root / "extra" / "기준서 2"
        json_path = base_path / "기준서 파싱.json"
        cache_dir = base_path / "hf_cache"
        para_emb_path = cache_dir / "para_emb_intfloat_multilingual-e5-large.npy"
        
        print(f"📁 데이터 경로: {base_path}")
        print(f"📄 JSON 파일 존재: {json_path.exists()}")
        print(f"📄 임베딩 파일 존재: {para_emb_path.exists()}")
        
        if not json_path.exists():
            print("❌ K-IFRS 데이터 파일이 없습니다.")
            return False
        
        # JSON 파일 로드 테스트
        print("🔄 JSON 데이터 로드 중...")
        with json_path.open(encoding='utf-8') as f:
            data = json.load(f)
        
        docs = data.get('documents', [])
        paragraphs = []
        for d in docs:
            for p in d.get('paragraphs', []):
                paragraphs.append(p)
        
        print(f"✅ JSON 로드 성공: {len(docs)}개 문서, {len(paragraphs)}개 문단")
        
        # 임베딩 파일 로드 테스트 (있는 경우)
        if para_emb_path.exists():
            print("🔄 임베딩 파일 로드 중...")
            para_vecs = np.load(para_emb_path)
            print(f"✅ 임베딩 로드 성공: {para_vecs.shape}")
        else:
            print("⚠️ 임베딩 파일 없음 (실시간 임베딩 사용)")
        
        return True
        
    except Exception as e:
        print(f"❌ K-IFRS 시스템 오류: {e}")
        return False

def main():
    print("🧪 RAG 시스템 테스트 시작\n")
    
    results = {
        "audit": test_audit_system(),
        "legal": test_legal_system(),
        "kifrs": test_kifrs_system()
    }
    
    print("\n" + "="*50)
    print("📊 테스트 결과 요약")
    print("="*50)
    
    for system, result in results.items():
        status = "✅ 성공" if result else "❌ 실패"
        print(f"{system:10} : {status}")
    
    all_success = all(results.values())
    if all_success:
        print("\n🎉 모든 시스템이 정상 작동합니다!")
    else:
        print("\n⚠️ 일부 시스템에 문제가 있습니다.")
    
    return all_success

if __name__ == "__main__":
    main()
