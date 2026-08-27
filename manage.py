#!/usr/bin/env python
"""Django 관리 명령 엔트리포인트."""
import os
import sys
from pathlib import Path


def main():
    # .env 로드 (있으면). python-dotenv 미설치여도 죽지 않도록 방어.
    try:
        from dotenv import load_dotenv

        load_dotenv(Path(__file__).resolve().parent / ".env")
    except ImportError:
        pass

    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")
    try:
        from django.core.management import execute_from_command_line
    except ImportError as exc:
        raise ImportError(
            "Django 를 불러올 수 없습니다. 가상환경(.venv)을 활성화했는지, "
            "requirements.txt 를 설치했는지 확인하세요."
        ) from exc
    execute_from_command_line(sys.argv)


if __name__ == "__main__":
    main()
