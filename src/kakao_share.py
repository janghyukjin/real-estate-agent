"""
카카오톡 공유 버튼 컴포넌트

Kakao JS SDK를 사용하여 카카오톡 공유 버튼을 생성한다.
KAKAO_JS_KEY가 설정되지 않으면 클립보드 복사 버튼으로 폴백한다.

TODO: Kakao Developers 콘솔에서 플랫폼 도메인 등록 필요
      (내 애플리케이션 > 앱 설정 > 플랫폼 > Web 사이트 도메인)
      등록할 도메인: https://my-zpt.streamlit.app
"""

import os

APP_URL = "https://my-zpt.streamlit.app"


def get_kakao_js_key():
    """환경변수에서 카카오 JS 키를 가져온다. 없으면 빈 문자열."""
    return (os.environ.get("KAKAO_JS_KEY") or "").strip()


def build_kakao_share_html(seed_억: float, loan_억: float, budget_억: float, top_apt: str = ""):
    """카카오톡 공유 버튼 HTML을 생성한다.

    Parameters
    ----------
    seed_억 : float  - 종잣돈 (억 단위)
    loan_억 : float  - 대출 (억 단위)
    budget_억 : float - 총 예산 (억 단위)
    top_apt : str     - 1위 추천 아파트 이름 (선택)

    Returns
    -------
    str : HTML string (st.components.v1.html 또는 st.markdown용)
    """
    js_key = get_kakao_js_key()
    title = "집피티 — 내 예산으로 살 수 있는 아파트"
    desc = f"종잣돈 {seed_억:.1f}억 + 대출 {loan_억:.1f}억 = {budget_억:.1f}억 예산으로 찾은 TOP 추천"
    if top_apt:
        desc += f" | 1위: {top_apt}"

    if js_key:
        return _build_kakao_sdk_html(js_key, title, desc)
    else:
        return _build_fallback_html(title, desc)


def _build_kakao_sdk_html(js_key: str, title: str, desc: str):
    """Kakao JS SDK를 이용한 공유 버튼 HTML."""
    # NOTE: Kakao JS SDK는 도메인 등록이 필요하다.
    # 등록 전에는 "허용되지 않는 도메인" 에러가 뜰 수 있다.
    return f"""
    <div id="kakao-share-wrapper" style="text-align:center;margin:12px 0 4px 0;">
        <a id="kakao-share-btn" href="javascript:void(0)"
           style="display:inline-flex;align-items:center;gap:6px;
                  background:#FEE500;color:#191919;
                  padding:8px 18px;border-radius:8px;
                  font-size:0.85rem;font-weight:600;
                  text-decoration:none;transition:opacity 0.2s;"
           onmouseover="this.style.opacity='0.85'"
           onmouseout="this.style.opacity='1'">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path fill="#191919" d="M9 1C4.58 1 1 3.8 1 7.23c0 2.2 1.46 4.13 3.66 5.23
                    -.1.38-.37 1.38-.4 1.48-.04.13-.01.27.07.36a.3.3 0 00.22.09c.04 0 .08-.01.12-.03
                    .56-.32 2.04-1.18 2.88-1.67.47.07.96.1 1.45.1 4.42 0 8-2.8 8-6.23S13.42 1 9 1z"/>
            </svg>
            카카오톡 공유
        </a>
    </div>
    <script src="https://t1.kakaocdn.net/kakao_js_sdk/2.7.4/kakao.min.js"
            integrity="sha384-DKYJZ8NLiK8MN4/C5P2dtSmLQ4KwPaoqAfyA/DfmEc1VDxu4yyC7wy6K1Hs90nk"
            crossorigin="anonymous"></script>
    <script>
        if (!Kakao.isInitialized()) {{
            Kakao.init('{js_key}');
        }}
        document.getElementById('kakao-share-btn').addEventListener('click', function() {{
            Kakao.Share.sendDefault({{
                objectType: 'feed',
                content: {{
                    title: '{_escape_js(title)}',
                    description: '{_escape_js(desc)}',
                    imageUrl: '',
                    link: {{
                        mobileWebUrl: '{APP_URL}',
                        webUrl: '{APP_URL}',
                    }},
                }},
                buttons: [
                    {{
                        title: '나도 추천받기',
                        link: {{
                            mobileWebUrl: '{APP_URL}',
                            webUrl: '{APP_URL}',
                        }},
                    }},
                ],
            }});
        }});
    </script>
    """


def _build_fallback_html(title: str, desc: str):
    """카카오 JS 키가 없을 때 URL 복사 + 카카오톡 웹 공유 폴백."""
    share_text = f"{title}\\n{desc}\\n{APP_URL}"
    # 카카오톡 공유는 URL scheme 대신 클립보드 복사 + 안내로 처리
    return f"""
    <div id="share-fallback" style="text-align:center;margin:12px 0 4px 0;">
        <a id="share-copy-btn" href="javascript:void(0)"
           style="display:inline-flex;align-items:center;gap:6px;
                  background:#FEE500;color:#191919;
                  padding:8px 18px;border-radius:8px;
                  font-size:0.85rem;font-weight:600;
                  text-decoration:none;transition:opacity 0.2s;"
           onmouseover="this.style.opacity='0.85'"
           onmouseout="this.style.opacity='1'">
            <svg width="18" height="18" viewBox="0 0 18 18" fill="none">
                <path fill="#191919" d="M9 1C4.58 1 1 3.8 1 7.23c0 2.2 1.46 4.13 3.66 5.23
                    -.1.38-.37 1.38-.4 1.48-.04.13-.01.27.07.36a.3.3 0 00.22.09c.04 0 .08-.01.12-.03
                    .56-.32 2.04-1.18 2.88-1.67.47.07.96.1 1.45.1 4.42 0 8-2.8 8-6.23S13.42 1 9 1z"/>
            </svg>
            추천 결과 공유하기
        </a>
        <div id="share-toast" style="display:none;margin-top:8px;font-size:0.8rem;color:#51CF66;">
            링크가 복사되었습니다!
        </div>
    </div>
    <script>
        document.getElementById('share-copy-btn').addEventListener('click', function() {{
            var text = "{_escape_js(share_text)}";
            if (navigator.clipboard) {{
                navigator.clipboard.writeText(text).then(function() {{
                    var toast = document.getElementById('share-toast');
                    toast.style.display = 'block';
                    setTimeout(function() {{ toast.style.display = 'none'; }}, 2000);
                }});
            }} else {{
                // 폴백: textarea 복사
                var ta = document.createElement('textarea');
                ta.value = text;
                document.body.appendChild(ta);
                ta.select();
                document.execCommand('copy');
                document.body.removeChild(ta);
                var toast = document.getElementById('share-toast');
                toast.style.display = 'block';
                setTimeout(function() {{ toast.style.display = 'none'; }}, 2000);
            }}
        }});
    </script>
    """


def _escape_js(s: str) -> str:
    """JavaScript 문자열 리터럴에 안전하게 삽입할 수 있도록 이스케이프한다."""
    return s.replace("\\", "\\\\").replace("'", "\\'").replace('"', '\\"').replace("\n", "\\n")
