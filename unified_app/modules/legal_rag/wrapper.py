#!/usr/bin/env python3
"""
법률 문서 RAG 시스템 래퍼
통합 앱에서 사용하기 위한 인터페이스
"""

import streamlit as st
import os
import sys
from pathlib import Path
import logging
from typing import Optional
import json
import numpy as np
import faiss
import re
from sentence_transformers import SentenceTransformer
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.metrics.pairwise import linear_kernel
from openai import OpenAI

logger = logging.getLogger(__name__)

class SimpleCommercialLawRAG:
    """상법 RAG 시스템 (간소화 버전)"""
    
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # 데이터 경로 설정 (extra 폴더 기준)
        project_root = Path(__file__).parent.parent.parent.parent
        self.base_path = project_root / "extra" / "상법 2"
        self.index_path = self.base_path / "kcc_index_json" / "kcc.index"
        self.ids_path = self.base_path / "kcc_index_json" / "ids.npy"
        self.metas_path = self.base_path / "kcc_index_json" / "metas.json"
        self.model_name = "intfloat/multilingual-e5-base"
        
        self.index = None
        self.ids = None
        self.metas = None
        self.model = None
        self.tfidf = None
        self.X_tfidf = None
        self._initialized = False
    
    def initialize(self):
        """리소스 로드"""
        if self._initialized:
            return True
        
        try:
            with st.spinner("상법 시스템 로딩 중..."):
                # 데이터 파일 존재 확인
                if not all([self.index_path.exists(), self.ids_path.exists(), self.metas_path.exists()]):
                    st.error("상법 데이터 파일을 찾을 수 없습니다.")
                    return False
                
                # 인덱스/메타 로드
                self.index = faiss.read_index(str(self.index_path))
                self.ids = np.load(self.ids_path, allow_pickle=True).tolist()
                with open(self.metas_path, "r", encoding="utf-8") as f:
                    self.metas = json.load(f)
                
                # 모델 로드
                self.model = SentenceTransformer(self.model_name)
                
                # TF-IDF 인덱스 구축
                self._build_tfidf()
                
                self._initialized = True
                st.success("✅ 상법 시스템 로딩 완료")
                return True
                
        except Exception as e:
            st.error(f"상법 시스템 로드 실패: {str(e)}")
            logger.error(f"Commercial law system load failed: {e}")
            return False
    
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
        if not self._initialized:
            if not self.initialize():
                return "시스템이 초기화되지 않았습니다.", []
        
        if not all([self.index, self.model, self.tfidf]):
            return "시스템이 완전히 로드되지 않았습니다.", []
        
        try:
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
        
        except Exception as e:
            logger.error(f"Search and answer failed: {e}")
            return f"검색 중 오류 발생: {str(e)}", []
    
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
            logger.error(f"GPT answer generation failed: {e}")
            return f"답변 생성 중 오류: {str(e)}"

class SimpleKIFRSRAG:
    """K-IFRS RAG 시스템 (간소화 버전)"""
    
    def __init__(self, openai_api_key: str):
        self.openai_api_key = openai_api_key
        self.openai_client = OpenAI(api_key=openai_api_key)
        
        # 데이터 경로 설정
        project_root = Path(__file__).parent.parent.parent.parent
        self.base_path = project_root / "extra" / "기준서 2"
        self.json_path = self.base_path / "기준서 파싱.json"
        self.cache_dir = self.base_path / "hf_cache"
        self.title_emb_path = self.cache_dir / "title_emb_intfloat_multilingual-e5-large.npy"
        self.para_emb_path = self.cache_dir / "para_emb_intfloat_multilingual-e5-large.npy"
        self.model_name = "intfloat/multilingual-e5-large"
        
        self.docs = []
        self.paragraphs = []
        self.title_vecs = None
        self.para_vecs = None
        self.model = None
        self._initialized = False
    
    def initialize(self):
        """리소스 로드"""
        if self._initialized:
            return True
        
        try:
            with st.spinner("K-IFRS 시스템 로딩 중..."):
                # 데이터 파일 존재 확인
                if not self.json_path.exists():
                    st.error("K-IFRS 데이터 파일을 찾을 수 없습니다.")
                    return False
                
                # JSON 데이터 로드
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
                
                self._initialized = True
                st.success("✅ K-IFRS 시스템 로딩 완료")
                return True
                
        except Exception as e:
            st.error(f"K-IFRS 시스템 로드 실패: {str(e)}")
            logger.error(f"K-IFRS system load failed: {e}")
            return False
    
    def search_and_answer(self, query: str, topk: int = 5):
        """검색 및 답변 생성"""
        if not self._initialized:
            if not self.initialize():
                return "시스템이 초기화되지 않았습니다.", []
        
        try:
            if self.para_vecs is not None:
                # 벡터 검색 사용
                query_emb = self.model.encode([f"query: {query}"], normalize_embeddings=True)[0]
                similarities = np.dot(self.para_vecs, query_emb)
                top_indices = np.argpartition(similarities, -topk*3)[-topk*3:]
                top_indices = top_indices[np.argsort(similarities[top_indices])[::-1][:topk]]
            else:
                # 텍스트 유사도 기반 검색
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
            logger.error(f"K-IFRS search and answer failed: {e}")
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
            logger.error(f"K-IFRS GPT answer generation failed: {e}")
            return f"답변 생성 중 오류: {str(e)}"

def show_legal_rag_interface():
    """법률 문서 RAG 인터페이스 표시"""
    st.markdown("# ⚖️ 법률 문서 RAG 시스템")
    
    # API 키 확인
    import sys
    from pathlib import Path
    sys.path.append(str(Path(__file__).parent.parent))
    from utils import load_openai_api_key
    api_key = load_openai_api_key()
    
    if not api_key:
        st.error("OpenAI API 키가 설정되지 않았습니다.")
        st.info("환경변수 OPENAI_API_KEY를 설정하거나 .env 파일에 추가하세요.")
        return
    
    # 시스템 선택
    system_choice = st.selectbox(
        "시스템 선택",
        ["상법 LLM", "K-IFRS RAG"],
        index=0
    )
    
    if system_choice == "상법 LLM":
        st.header("🏛️ 상법 LLM 시스템")
        
        # 시스템 초기화
        if 'commercial_law_rag' not in st.session_state:
            st.session_state.commercial_law_rag = SimpleCommercialLawRAG(api_key)
        
        commercial_rag = st.session_state.commercial_law_rag
        
        # 질문 입력
        query = st.text_input(
            "상법 관련 질문을 입력하세요",
            placeholder="예: 준비금의 자본전입은 이사회에서 결정할 수 있는가?"
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            topk = st.slider("검색 결과 수", 3, 10, 5)
        
        if query and st.button("질문하기", type="primary"):
            with st.spinner("검색 및 답변 생성 중..."):
                answer, results = commercial_rag.search_and_answer(query, topk)
                
                st.markdown("### 📝 답변")
                st.markdown(answer)
                
                if results:
                    st.markdown("### 🔍 참조 조문")
                    for i, result in enumerate(results, 1):
                        with st.expander(f"{i}. 상법 제{result['article_id']}조 - {result.get('title', '')} (점수: {result['score']:.3f})"):
                            content = result['content']
                            st.write(content[:800] + "..." if len(content) > 800 else content)
    
    else:  # K-IFRS RAG
        st.header("📊 K-IFRS RAG 시스템")
        
        # 시스템 초기화
        if 'kifrs_rag' not in st.session_state:
            st.session_state.kifrs_rag = SimpleKIFRSRAG(api_key)
        
        kifrs_rag = st.session_state.kifrs_rag
        
        # 질문 입력
        query = st.text_input(
            "K-IFRS 관련 질문을 입력하세요",
            placeholder="예: 개발비 자산 인식 요건은 무엇인가요?"
        )
        
        col1, col2 = st.columns([1, 4])
        with col1:
            topk = st.slider("검색 결과 수", 3, 10, 5)
        
        if query and st.button("질문하기", type="primary"):
            with st.spinner("검색 및 답변 생성 중..."):
                answer, results = kifrs_rag.search_and_answer(query, topk)
                
                st.markdown("### 📝 답변")
                st.markdown(answer)
                
                if results:
                    st.markdown("### 🔍 참조 문단")
                    for i, result in enumerate(results, 1):
                        with st.expander(f"{i}. [{result['std']}:{result['para_id']}] {result['title']} (p.{result.get('page', '?')}) - 점수: {result['score']:.3f}"):
                            st.write(result['text'])
