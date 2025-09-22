#!/usr/bin/env python3
"""
NLP Team3 - 환경 설정 스크립트
팀원들이 처음 실행할 때 필요한 환경을 자동으로 설정합니다.
"""

import subprocess
import sys
import os
from pathlib import Path

def install_package(package):
    """패키지 설치"""
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", package])
        return True
    except subprocess.CalledProcessError:
        return False

def check_and_install_requirements():
    """필요한 패키지들 확인 및 설치"""
    required_packages = [
        "sentence-transformers>=2.2.0",
        "chromadb>=0.4.0", 
        "torch",
        "transformers",
        "numpy",
        "pandas",
        "tqdm",
        "scikit-learn"
    ]
    
    print("📦 필요한 패키지들을 확인하고 설치합니다...")
    
    for package in required_packages:
        package_name = package.split(">=")[0]
        try:
            __import__(package_name.replace("-", "_"))
            print(f"✅ {package_name} - 이미 설치됨")
        except ImportError:
            print(f"📥 {package_name} 설치 중...")
            if install_package(package):
                print(f"✅ {package_name} 설치 완료")
            else:
                print(f"❌ {package_name} 설치 실패")
                return False
    
    return True

def download_embedding_model():
    """임베딩 모델 사전 다운로드"""
    try:
        print("🤖 임베딩 모델 다운로드 중...")
        from sentence_transformers import SentenceTransformer
        
        model_name = "jhgan/ko-sroberta-multitask"
        model = SentenceTransformer(model_name)
        print(f"✅ {model_name} 모델 다운로드 완료")
        return True
    except Exception as e:
        print(f"❌ 모델 다운로드 실패: {e}")
        return False

def create_directories():
    """필요한 디렉토리 생성"""
    directories = [
        "vector_db",
        "logs",
        "temp"
    ]
    
    for dir_name in directories:
        dir_path = Path(dir_name)
        if not dir_path.exists():
            dir_path.mkdir(exist_ok=True)
            print(f"📁 {dir_name} 디렉토리 생성")
        else:
            print(f"✅ {dir_name} 디렉토리 존재")

def verify_data_files():
    """데이터 파일 존재 여부 확인"""
    try:
        from config import check_data_files
        missing_files = check_data_files()
        
        if missing_files:
            print(f"\n⚠️ 누락된 데이터 파일들 ({len(missing_files)}개):")
            for file in missing_files[:5]:  # 처음 5개만 표시
                print(f"  - {file}")
            if len(missing_files) > 5:
                print(f"  ... 및 {len(missing_files) - 5}개 더")
            print("\n💡 누락된 파일들을 프로젝트 폴더에 추가해주세요.")
            return False
        else:
            print("✅ 모든 데이터 파일이 존재합니다!")
            return True
    except ImportError:
        print("❌ config.py 파일을 찾을 수 없습니다.")
        return False

def main():
    """메인 설정 함수"""
    print("🚀 NLP Team3 벡터DB 환경 설정을 시작합니다...\n")
    
    # 1. 패키지 설치
    if not check_and_install_requirements():
        print("❌ 패키지 설치에 실패했습니다.")
        return False
    
    # 2. 디렉토리 생성
    create_directories()
    
    # 3. 모델 다운로드
    if not download_embedding_model():
        print("❌ 모델 다운로드에 실패했습니다.")
        return False
    
    # 4. 데이터 파일 확인
    data_files_ok = verify_data_files()
    
    print(f"\n{'='*50}")
    if data_files_ok:
        print("🎉 환경 설정이 완료되었습니다!")
        print("\n다음 명령어로 벡터DB를 실행할 수 있습니다:")
        print("  python vecDB.py")
    else:
        print("⚠️ 환경 설정은 완료되었지만 데이터 파일이 누락되었습니다.")
        print("필요한 데이터 파일들을 추가한 후 다시 실행해주세요.")
    
    return data_files_ok

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
