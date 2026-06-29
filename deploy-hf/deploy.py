"""해충 제보 Flask 앱 → Hugging Face Spaces (Docker) 배포.

하는 일:
  1) staging 폴더(.hfspace)에 '앱이 실제로 필요한 파일'만 골라 복사 (streamlit/training 파일 제외)
  2) deploy-hf/ 의 Dockerfile·README·requirements 를 staging 루트에 합침
  3) HF Space 레포 생성(없으면) 후 staging 전체 업로드

전제: huggingface_hub 설치 + HF 로그인(`hf auth login` 또는 HF_TOKEN 환경변수).
재배포: 모델 재학습/코드 수정 후 이 스크립트를 다시 실행하면 된다.

    ../.venv/Scripts/python.exe deploy-hf/deploy.py            # 기본 space 이름
    ../.venv/Scripts/python.exe deploy-hf/deploy.py my-space   # 이름 지정
"""
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent          # pest-sns/deploy-hf
SRC = HERE.parent                               # pest-sns/
STAGE = SRC / ".hfspace"                        # 업로드용 staging (gitignore)
SPACE_NAME = sys.argv[1] if len(sys.argv) > 1 else "pest-report-demo"

# 앱 구동에 실제로 필요한 것만 (streamlit app.py·train_to_tflite·csv·로그 등은 제외)
COPY_FILES = ["predict.py", "pest_info.json"]
COPY_DIRS = ["models"]
WEB_FILES = ["web/server.py"]
WEB_DIRS = ["web/templates"]
# web/static 는 추론과 무관한 infer.js(폐기된 브라우저 이식용) 빼고 선별 복사
STATIC_KEEP = ["styles.css", "app.js", "map.js", "reports.json", "geocode.json"]
DATA_KEEP = ["reports.json", "geocode.json"]
DEPLOY_FILES = ["Dockerfile", "README.md", "requirements.txt"]


def assemble():
    if STAGE.exists():
        shutil.rmtree(STAGE)
    STAGE.mkdir(parents=True)

    for f in COPY_FILES:
        shutil.copy2(SRC / f, STAGE / f)
    for d in COPY_DIRS:
        shutil.copytree(SRC / d, STAGE / d)
    for f in WEB_FILES:
        (STAGE / f).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(SRC / f, STAGE / f)
    for d in WEB_DIRS:
        shutil.copytree(SRC / d, STAGE / d)

    (STAGE / "web" / "static").mkdir(parents=True, exist_ok=True)
    for f in STATIC_KEEP:
        shutil.copy2(SRC / "web" / "static" / f, STAGE / "web" / "static" / f)
    (STAGE / "web" / "data").mkdir(parents=True, exist_ok=True)
    for f in DATA_KEEP:
        src = SRC / "web" / "data" / f
        if src.exists():
            shutil.copy2(src, STAGE / "web" / "data" / f)

    for f in DEPLOY_FILES:
        shutil.copy2(HERE / f, STAGE / f)

    files = sorted(p.relative_to(STAGE).as_posix() for p in STAGE.rglob("*") if p.is_file())
    print(f"[assemble] {len(files)} files → {STAGE}")
    for f in files:
        print("   ", f)
    return files


def upload():
    from huggingface_hub import HfApi
    api = HfApi()
    who = api.whoami()  # 로그인 안 됐으면 여기서 예외
    user = who["name"]
    repo_id = f"{user}/{SPACE_NAME}"
    print(f"[hf] user={user}  repo={repo_id}")

    api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="docker", exist_ok=True)
    api.upload_folder(folder_path=str(STAGE), repo_id=repo_id, repo_type="space",
                      commit_message="deploy pest-report demo")
    url = f"https://huggingface.co/spaces/{repo_id}"
    print(f"[done] {url}")
    print("빌드 진행: 위 Space 페이지의 'Building' 로그 참고 (수 분 소요). 완료되면 App 탭에서 접속.")


if __name__ == "__main__":
    assemble()
    try:
        upload()
    except Exception as e:
        print(f"\n[!] 업로드 단계 실패: {e}\n")
        print("HF 로그인이 필요합니다. 아래 중 하나로 로그인 후 다시 실행:")
        print("   1) 터미널에:  ! .venv\\Scripts\\hf.exe auth login   (토큰 붙여넣기)")
        print("   2) 또는 환경변수:  $env:HF_TOKEN='hf_xxx' 후 재실행")
        print("   토큰 발급: https://huggingface.co/settings/tokens  (write 권한)")
        sys.exit(1)
