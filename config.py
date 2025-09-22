"""
NLP Team3 - 벡터 DB 설정 파일
팀원별로 이 파일만 수정하면 됩니다.
"""

import os
from pathlib import Path

# 프로젝트 루트 디렉토리 (자동 감지)
PROJECT_ROOT = Path(__file__).parent

# 데이터 파일 경로 설정
DATA_PATHS = {
    'annotation': {
        2014: PROJECT_ROOT / "아카이브" / "감사보고서_2014_parsed.json",
        2015: PROJECT_ROOT / "아카이브" / "감사보고서_2015_parsed.json", 
        2016: PROJECT_ROOT / "아카이브" / "감사보고서_2016_parsed.json",
        2017: PROJECT_ROOT / "아카이브" / "감사보고서_2017_parsed.json",
        2018: PROJECT_ROOT / "아카이브" / "감사보고서_2018_parsed.json",
        2019: PROJECT_ROOT / "아카이브" / "감사보고서_2019_parsed.json",
        2020: PROJECT_ROOT / "아카이브" / "감사보고서_2020_parsed.json",
        2021: PROJECT_ROOT / "아카이브" / "감사보고서_2021_parsed.json",
        2022: PROJECT_ROOT / "아카이브" / "감사보고서_2022_parsed.json",
        2023: PROJECT_ROOT / "아카이브" / "감사보고서_2023_parsed.json",
        2024: PROJECT_ROOT / "아카이브" / "감사보고서_2024_parsed.json"
    },
    'financial_table': {
        2014: PROJECT_ROOT / "table_parsing" / "감사보고서_2014_parsed.json",
        2015: PROJECT_ROOT / "table_parsing" / "감사보고서_2015_parsed.json",
        2016: PROJECT_ROOT / "table_parsing" / "감사보고서_2016_parsed.json", 
        2017: PROJECT_ROOT / "table_parsing" / "감사보고서_2017_parsed.json",
        2018: PROJECT_ROOT / "table_parsing" / "감사보고서_2018_parsed.json",
        2019: PROJECT_ROOT / "table_parsing" / "감사보고서_2019_parsed.json",
        2020: PROJECT_ROOT / "table_parsing" / "감사보고서_2020_parsed.json",
        2021: PROJECT_ROOT / "table_parsing" / "감사보고서_2021_parsed.json",
        2022: PROJECT_ROOT / "table_parsing" / "감사보고서_2022_parsed.json",
        2023: PROJECT_ROOT / "table_parsing" / "감사보고서_2023_parsed.json",
        2024: PROJECT_ROOT / "table_parsing" / "감사보고서_2024_parsed.json"
    },
    'accounting_standard': {
        2024: PROJECT_ROOT / "kifrs_combined_2.json"
    }
}

# ChromaDB 설정
CHROMA_DB_PATH = PROJECT_ROOT / "vector_db"

# 임베딩 모델 설정
EMBEDDING_MODEL = "jhgan/ko-sroberta-multitask"

# 배치 크기 설정 (메모리에 따라 조정 가능)
DEFAULT_BATCH_SIZE = 25

# 파일 존재 여부 확인 함수
def check_data_files():
    """필요한 데이터 파일들이 존재하는지 확인"""
    missing_files = []
    
    for doc_type, year_files in DATA_PATHS.items():
        for year, file_path in year_files.items():
            if not file_path.exists():
                missing_files.append(f"{doc_type} - {year}: {file_path}")
    
    return missing_files

# 문자열 경로로 변환 (하위 호환성)
def get_string_paths():
    """문자열 형태의 파일 경로 반환 (기존 코드 호환용)"""
    string_paths = {}
    for doc_type, year_files in DATA_PATHS.items():
        string_paths[doc_type] = {}
        for year, file_path in year_files.items():
            string_paths[doc_type][year] = str(file_path)
    return string_paths

if __name__ == "__main__":
    # 설정 확인 스크립트
    print("🔍 NLP Team3 벡터DB 설정 확인")
    print(f"프로젝트 루트: {PROJECT_ROOT}")
    print(f"ChromaDB 경로: {CHROMA_DB_PATH}")
    
    missing = check_data_files()
    if missing:
        print(f"\n⚠️ 누락된 파일들 ({len(missing)}개):")
        for file in missing:
            print(f"  - {file}")
    else:
        print("\n✅ 모든 데이터 파일이 존재합니다!")
