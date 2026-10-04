# C0 맥(·리눅스) 런처 공용 함수 — 각 *.command 가 `source` 한다. 직접 실행하는 파일이 아니다.
#
#   univus_base_python            시스템 python (3.10 이상, 3.12 우선) 경로를 찍는다. 없으면 설치 안내 후 실패
#   univus_venv DIR [REQ] [--chromium]
#                                 DIR 가상환경을 만들고 REQ 패키지·Chromium 을 맞춘 뒤 그 python 경로를 UNIVUS_PY 에 넣는다
#                                 (실제 일은 python -m osenv venv — Windows setup.cmd 와 같은 단계, 다시 불러도 안전)
#
# 로직은 Python(osenv) 쪽에 두고 여기는 python 을 찾아 넘기기만 한다 (WE-Meet_데스크톱앱_맥지원_계획.md 3절).

UNIVUS_C0="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIVUS_ROOT="$(dirname "$UNIVUS_C0")"
export PYTHONUTF8=1

univus_base_python() {
  local c
  for c in python3.12 python3.13 python3.11 python3.14 python3.10 python3; do
    if command -v "$c" >/dev/null 2>&1 && "$c" -c 'import sys; sys.exit(sys.version_info < (3, 10))' 2>/dev/null; then
      command -v "$c"
      return 0
    fi
  done
  echo "" >&2
  echo "  Python 3.10 이상을 찾지 못했습니다 (3.12 권장)." >&2
  echo "  설치: https://www.python.org/downloads/macos/  또는  brew install python@3.12" >&2
  echo "  python.org 설치판이면 설치 후 '/Applications/Python 3.12/Install Certificates.command' 도 한 번 실행하세요." >&2
  return 1
}

univus_venv() {
  local dir="$1"; shift
  local base
  base="$(univus_base_python)" || return 1
  local args=(venv "$dir")
  if [ -n "$1" ] && [ "$1" != "--chromium" ]; then args+=(-r "$1"); shift; fi
  if [ "$1" = "--chromium" ]; then args+=(--chromium); fi
  PYTHONPATH="$UNIVUS_C0${PYTHONPATH:+:$PYTHONPATH}" "$base" -m osenv "${args[@]}" >/dev/null || return 1
  UNIVUS_PY="$dir/bin/python"
  [ -x "$UNIVUS_PY" ]
}
