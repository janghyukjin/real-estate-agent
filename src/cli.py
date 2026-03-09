"""CLI 엔트리포인트"""

import asyncio
import sys

from .agent import interactive_session


def main():
    """메인 실행"""
    try:
        asyncio.run(interactive_session())
    except KeyboardInterrupt:
        print("\n종료합니다.")
        sys.exit(0)


if __name__ == "__main__":
    main()
