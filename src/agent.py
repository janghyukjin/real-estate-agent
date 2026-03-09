"""
부동산 AI 에이전트

Claude API를 활용하여 사용자의 재무 상태를 분석하고
맞춤 부동산 추천을 제공하는 에이전트.

Tool-use 패턴으로 Claude가 직접 API를 호출하여
실거래가 조회, 가격 분석, 추천을 수행합니다.
"""

import asyncio
import json
import os
from typing import Any

import anthropic

from .calculator import (
    AffordabilityResult,
    BuyerType,
    LoanPolicy,
    UserFinance,
    calculate_affordability,
)
from .api_client import (
    REGION_CODES,
    SEOUL_TIERS,
    fetch_recent_trades,
    fetch_recent_rents,
    filter_by_budget,
    trades_to_dataframe,
    analyze_price_trend,
)
from .alerts import (
    add_watch,
    remove_watch,
    load_watchlist,
    check_alerts,
)
from .kb_client import (
    analyze_gap,
    analyze_area_gap,
    get_kb_price_index,
)
from .building_ledger import (
    get_household_count,
    is_large_complex,
    APT_HOUSEHOLD_CACHE,
)


# Claude에게 제공할 도구(tool) 정의
TOOLS = [
    {
        "name": "calculate_budget",
        "description": (
            "사용자의 재무 상태(종잣돈, 월소득, 월지출)를 입력받아 "
            "DSR/LTV 기반으로 최대 대출 가능액과 매수 가능 집값을 계산합니다. "
            "단위는 모두 만원입니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "seed_money": {
                    "type": "integer",
                    "description": "종잣돈 (만원)",
                },
                "monthly_income": {
                    "type": "integer",
                    "description": "월소득 (만원)",
                },
                "monthly_expense": {
                    "type": "integer",
                    "description": "월지출 (만원)",
                },
                "buyer_type": {
                    "type": "string",
                    "enum": ["생애최초", "무주택", "1주택", "다주택자"],
                    "description": "매수자 유형",
                    "default": "생애최초",
                },
                "existing_debt_payment": {
                    "type": "integer",
                    "description": "기존 대출 월상환액 (만원)",
                    "default": 0,
                },
                "will_reside": {
                    "type": "boolean",
                    "description": "실거주 여부 (토허제 구역 대출에 영향)",
                    "default": True,
                },
            },
            "required": ["seed_money", "monthly_income", "monthly_expense"],
        },
    },
    {
        "name": "search_real_trades",
        "description": (
            "특정 지역의 최근 아파트 매매 실거래가를 조회합니다. "
            "예산 범위와 면적을 지정하여 필터링할 수 있습니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": f"시군구 이름. 사용 가능: {', '.join(REGION_CODES.keys())}",
                },
                "months": {
                    "type": "integer",
                    "description": "최근 몇 개월 데이터를 조회할지 (기본 6개월)",
                    "default": 6,
                },
                "min_price": {
                    "type": "integer",
                    "description": "최소 금액 (만원)",
                    "default": 0,
                },
                "max_price": {
                    "type": "integer",
                    "description": "최대 금액 (만원)",
                    "default": 999999,
                },
                "min_area": {
                    "type": "number",
                    "description": "최소 전용면적 (㎡, 기본 59)",
                    "default": 59.0,
                },
                "max_area": {
                    "type": "number",
                    "description": "최대 전용면적 (㎡, 기본 85)",
                    "default": 85.0,
                },
            },
            "required": ["region"],
        },
    },
    {
        "name": "analyze_apt_trend",
        "description": (
            "특정 아파트의 가격 추이를 분석합니다. "
            "월별 평균가, 최저가, 최고가, 거래건수를 보여줍니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "시군구 이름",
                },
                "apt_name": {
                    "type": "string",
                    "description": "아파트 이름",
                },
                "months": {
                    "type": "integer",
                    "description": "최근 몇 개월 (기본 12개월)",
                    "default": 12,
                },
            },
            "required": ["region", "apt_name"],
        },
    },
    {
        "name": "analyze_gap_investment",
        "description": (
            "특정 지역의 갭투자 분석을 수행합니다. "
            "매매 실거래가와 전세 실거래가를 비교하여 "
            "전세가율, 갭(매매-전세), 투자등급을 계산합니다. "
            "전세가율이 높으면 소액으로 갭투자 가능, 낮으면 자본금이 많이 필요합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "region": {
                    "type": "string",
                    "description": "시군구 이름",
                },
                "months": {
                    "type": "integer",
                    "description": "최근 몇 개월 데이터 (기본 6)",
                    "default": 6,
                },
                "min_area": {
                    "type": "number",
                    "description": "최소 전용면적 (㎡, 기본 59)",
                    "default": 59.0,
                },
                "max_area": {
                    "type": "number",
                    "description": "최대 전용면적 (㎡, 기본 85)",
                    "default": 85.0,
                },
            },
            "required": ["region"],
        },
    },
    {
        "name": "get_kb_trend",
        "description": (
            "KB부동산 매매/전세 가격지수 추이를 조회합니다. "
            "시장 전체의 흐름을 파악할 때 사용합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "period": {
                    "type": "integer",
                    "description": "조회 기간 (개월, 기본 12)",
                    "default": 12,
                },
            },
            "required": [],
        },
    },
    {
        "name": "watch_apartment",
        "description": (
            "관심 아파트를 등록/삭제/조회합니다. "
            "등록하면 목표가 이하 거래 발생 시 알림을 받을 수 있습니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["add", "remove", "list", "check"],
                    "description": "add: 등록, remove: 삭제, list: 목록조회, check: 급매체크",
                },
                "apt_name": {
                    "type": "string",
                    "description": "아파트명 (add/remove 시 필수)",
                },
                "region": {
                    "type": "string",
                    "description": "시군구 (add/remove 시 필수)",
                },
                "target_price": {
                    "type": "integer",
                    "description": "목표 매수가 (만원, add 시 필수)",
                },
            },
            "required": ["action"],
        },
    },
    {
        "name": "get_region_info",
        "description": (
            "서울 각 구의 부동산 등급(상급지/중상급지/중하급지/하급지)과 "
            "사용 가능한 지역 코드 목록을 조회합니다."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "조회할 내용: 'tiers' (등급분류), 'regions' (전체 지역목록)",
                    "enum": ["tiers", "regions"],
                },
            },
            "required": ["query"],
        },
    },
]

SYSTEM_PROMPT = """\
당신은 한국 부동산 내집마련 전문 AI 에이전트입니다.

역할:
1. 사용자의 재무 상태를 분석하여 매수 가능한 집값을 계산
2. 실거래가 데이터를 조회하여 예산에 맞는 아파트를 추천
3. 가격 추이를 분석하여 매수 타이밍에 대한 인사이트 제공

핵심 지식:
- 10.15 부동산 대책 반영:
  - 스트레스 DSR 가산금리 3.0% (기존 1.5%)
  - LTV: 무주택 40%, 생애최초 70% (기존 80%), 유주택 0%
  - 시가 15억 초과 대출한도 4억, 25억 초과 2억
  - 토지거래허가구역: 서울 전역 (2026.12.31까지), 2년 실거주 의무
- 서울 지역 등급: 상급지(강남3구+용산) > 중상급지 > 중하급지 > 하급지
- 2021년 고점 대비 가격 비교는 매수 판단의 중요 지표
- 전세가율: 70%+ 소액갭투자 가능, 60~70% 적정, 50% 미만 갭투자 부적합
- KB시세는 호가의 대용 지표로 활용 가능

대화 지침:
- 먼저 calculate_budget 도구로 사용자의 예산을 파악하세요
- 예산이 파악되면 적절한 지역의 실거래가를 조회하세요
- 실거래가 데이터를 기반으로 구체적인 아파트를 추천하세요
- 갭투자에 관심 있으면 analyze_gap_investment로 전세가율을 분석하세요
- KB 시장 트렌드가 필요하면 get_kb_trend를 사용하세요
- 관심 매물은 watch_apartment로 등록하여 급매 알림을 받을 수 있습니다
- 가격 추이, 층수별 가격 차이, 건축년도 등을 고려하세요
- 한국어로 응답하세요
- 금액 단위는 만원으로 통일하세요
"""


async def handle_tool_call(
    tool_name: str, tool_input: dict[str, Any]
) -> str:
    """도구 호출을 처리하고 결과를 반환"""

    if tool_name == "calculate_budget":
        buyer_map = {
            "생애최초": BuyerType.FIRST_TIME,
            "무주택": BuyerType.NO_HOUSE,
            "1주택": BuyerType.ONE_HOUSE,
            "다주택자": BuyerType.MULTI_HOME,
        }
        user = UserFinance(
            seed_money=tool_input["seed_money"],
            monthly_income=tool_input["monthly_income"],
            monthly_expense=tool_input["monthly_expense"],
            buyer_type=buyer_map.get(
                tool_input.get("buyer_type", "생애최초"),
                BuyerType.FIRST_TIME,
            ),
            existing_debt_payment=tool_input.get("existing_debt_payment", 0),
            will_reside=tool_input.get("will_reside", True),
        )
        result = calculate_affordability(user)
        return json.dumps({
            "종잣돈": f"{result.seed_money:,}만원",
            "월저축": f"{result.monthly_saving:,}만원",
            "DSR기반_최대대출_기본": f"{result.max_loan_by_dsr:,}만원",
            "DSR기반_최대대출_스트레스": f"{result.max_loan_by_dsr_stress:,}만원 (가산3%적용)",
            "DSR기반_최대집값": f"{result.max_price_by_dsr:,}만원",
            "LTV기반_최대대출": f"{result.max_loan_by_ltv:,}만원",
            "최종_최대대출": f"{result.final_max_loan:,}만원",
            "최종_매수가능집값": f"{result.final_max_price:,}만원",
            "시가별_한도": result.loan_cap_applied or "해당없음",
            "추천지역": [r.value for r in result.recommended_regions],
            "주의사항": result.warnings,
        }, ensure_ascii=False, indent=2)

    elif tool_name == "search_real_trades":
        region = tool_input["region"]
        if region not in REGION_CODES:
            return json.dumps({"error": f"지원하지 않는 지역: {region}"})

        code = REGION_CODES[region]
        months = tool_input.get("months", 6)

        trades = await fetch_recent_trades(code, months)

        # 필터링
        filtered = filter_by_budget(
            trades,
            min_price=tool_input.get("min_price", 0),
            max_price=tool_input.get("max_price", 999999),
            min_area=tool_input.get("min_area", 59.0),
            max_area=tool_input.get("max_area", 85.0),
        )

        df = trades_to_dataframe(filtered)
        if df.empty:
            return json.dumps({"message": "조건에 맞는 거래 데이터가 없습니다."})

        # 상위 20건만 반환
        summary = df.head(20).to_dict(orient="records")
        return json.dumps({
            "총_거래건수": len(filtered),
            "조회기간": f"최근 {months}개월",
            "지역": region,
            "상위_거래": summary,
        }, ensure_ascii=False, indent=2, default=str)

    elif tool_name == "analyze_apt_trend":
        region = tool_input["region"]
        if region not in REGION_CODES:
            return json.dumps({"error": f"지원하지 않는 지역: {region}"})

        code = REGION_CODES[region]
        months = tool_input.get("months", 12)
        apt_name = tool_input["apt_name"]

        trades = await fetch_recent_trades(code, months)
        trend = analyze_price_trend(trades, apt_name)

        if trend.empty:
            return json.dumps({
                "message": f"'{apt_name}' 거래 데이터가 없습니다."
            })

        return json.dumps({
            "아파트": apt_name,
            "지역": region,
            "가격추이": trend.to_dict(orient="index"),
        }, ensure_ascii=False, indent=2, default=str)

    elif tool_name == "analyze_gap_investment":
        region = tool_input["region"]
        if region not in REGION_CODES:
            return json.dumps({"error": f"지원하지 않는 지역: {region}"})

        code = REGION_CODES[region]
        months = tool_input.get("months", 6)
        min_area = tool_input.get("min_area", 59.0)
        max_area = tool_input.get("max_area", 85.0)

        # 매매 + 전세 실거래가 동시 조회
        trades = await fetch_recent_trades(code, months)
        rents = await fetch_recent_rents(code, months, jeonse_only=True)

        # 아파트별 갭 분석
        df = await analyze_area_gap(trades, rents, min_area, max_area)

        if df.empty:
            return json.dumps({
                "message": f"{region} 매매-전세 매칭 데이터가 부족합니다."
            })

        # 상위 15건
        summary = df.head(15).to_dict(orient="records")
        return json.dumps({
            "지역": region,
            "분석_아파트수": len(df),
            "전세가율_평균": f"{df['전세가율(%)'].mean():.1f}%",
            "갭투자_분석": summary,
        }, ensure_ascii=False, indent=2, default=str)

    elif tool_name == "get_kb_trend":
        period = tool_input.get("period", 12)
        try:
            df = get_kb_price_index(period=period)
            if df.empty:
                return json.dumps({"message": "KB 데이터 조회 실패"})
            # 최근 데이터 요약
            summary = df.tail(6).to_dict(orient="records")
            return json.dumps({
                "KB매매가격지수": summary,
                "조회기간": f"최근 {period}개월",
            }, ensure_ascii=False, indent=2, default=str)
        except Exception as e:
            return json.dumps({"error": f"KB 데이터 조회 오류: {str(e)}"})

    elif tool_name == "watch_apartment":
        action = tool_input["action"]
        if action == "add":
            item = add_watch(
                apt_name=tool_input["apt_name"],
                region=tool_input["region"],
                target_price=tool_input["target_price"],
            )
            return json.dumps({
                "message": f"'{item.apt_name}' 관심 등록 완료",
                "target_price": f"{item.target_price:,}만원",
            }, ensure_ascii=False)
        elif action == "remove":
            ok = remove_watch(tool_input["apt_name"], tool_input["region"])
            return json.dumps({
                "message": "삭제 완료" if ok else "해당 매물을 찾을 수 없습니다."
            }, ensure_ascii=False)
        elif action == "list":
            items = load_watchlist()
            return json.dumps([
                {"아파트": i.apt_name, "지역": i.region,
                 "목표가": f"{i.target_price:,}만", "등록일": i.created_at}
                for i in items
            ], ensure_ascii=False, indent=2)
        elif action == "check":
            alerts = await check_alerts()
            if not alerts:
                return json.dumps({"message": "새로운 급매가 없습니다."})
            return json.dumps([
                {"아파트": a.apt_name, "거래가": f"{a.found_price:,}만",
                 "목표가대비": f"-{a.price_gap:,}만", "면적": a.area,
                 "층": a.floor, "거래일": a.deal_date}
                for a in alerts
            ], ensure_ascii=False, indent=2)

    elif tool_name == "get_region_info":
        query = tool_input["query"]
        if query == "tiers":
            return json.dumps(SEOUL_TIERS, ensure_ascii=False, indent=2)
        else:
            return json.dumps(
                {k: v for k, v in REGION_CODES.items()},
                ensure_ascii=False,
                indent=2,
            )

    return json.dumps({"error": f"알 수 없는 도구: {tool_name}"})


async def run_agent(user_message: str, conversation: list | None = None):
    """에이전트 실행 - 대화형 루프"""
    client = anthropic.AsyncAnthropic()

    if conversation is None:
        conversation = []

    conversation.append({"role": "user", "content": user_message})

    while True:
        response = await client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            system=SYSTEM_PROMPT,
            tools=TOOLS,
            messages=conversation,
        )

        # 응답을 대화에 추가
        conversation.append({"role": "assistant", "content": response.content})

        # tool_use가 없으면 최종 응답
        if response.stop_reason != "tool_use":
            # 텍스트 응답 추출
            text_parts = [
                block.text
                for block in response.content
                if block.type == "text"
            ]
            return "\n".join(text_parts), conversation

        # tool_use 처리
        tool_results = []
        for block in response.content:
            if block.type == "tool_use":
                print(f"  🔧 {block.name} 호출 중...")
                result = await handle_tool_call(block.name, block.input)
                tool_results.append({
                    "type": "tool_result",
                    "tool_use_id": block.id,
                    "content": result,
                })

        conversation.append({"role": "user", "content": tool_results})


async def interactive_session():
    """대화형 세션 실행"""
    print("=" * 60)
    print("🏠 부동산 내집마련 AI 에이전트")
    print("=" * 60)
    print()
    print("종잣돈, 소득, 지출을 알려주시면")
    print("매수 가능한 집값과 추천 아파트를 찾아드립니다.")
    print()
    print("예시: '종잣돈 2억, 월소득 400만원, 월지출 200만원이야'")
    print("종료: 'quit' 또는 'q'")
    print("-" * 60)

    conversation = None

    while True:
        try:
            user_input = input("\n👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n안녕히 가세요! 👋")
            break

        if user_input.lower() in ("quit", "q", "종료"):
            print("안녕히 가세요! 👋")
            break

        if not user_input:
            continue

        try:
            response, conversation = await run_agent(user_input, conversation)
            print(f"\n🤖 Agent: {response}")
        except Exception as e:
            print(f"\n❌ 오류: {e}")
            if "API" in str(e) or "api" in str(e):
                print("   → ANTHROPIC_API_KEY 또는 DATA_GO_KR_API_KEY를 확인해주세요.")
