import os
import sys
from datetime import datetime, timezone
import requests
from google import genai
from google.genai import types

# ----------------- 1. 配置与环境检查 -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# 可选：飞书/企业微信/钉钉/Discord 等 Webhook 地址
WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not GEMINI_API_KEY:
    print("错误: 请先设置环境变量 GEMINI_API_KEY", file=sys.stderr)
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# ----------------- 2. 动态生成 Token 优化提示词 -----------------
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# 限制范围：仅追踪核心巨头与半导体链条，防止漫无目的地检索全网海量小盘股
TICKER_SCOPE = "NVDA, MSFT, AAPL, GOOGL, AMZN, META, TSLA, TSM, ASML"

prompt = f"""
你是一名资深美股量化宏观与科技板块研究员。
当前基准日期（UTC）：{today_str}。
请检索过去 24 小时内关于以下标的的核心动态及关键宏观/行业事件：[{TICKER_SCOPE}]。

【输出硬性约束】
1. 语言：中文。
2. 筛选规则：仅挑出对股价最具实质影响的「Top 3 ~ 5 个重大事件」，剔除常规盘后波动与无意义公关稿。
3. 严格遵循以下 Markdown 结构输出，不要包含任何前言开场白或免责声明废话：

### 📅 美股科技核心晨报 ({today_str})

#### 1. 宏观与板块主线（1~2 句话概述大盘或科技板块当日流动性/利率/情绪特征）

#### 2. 核心催化剂与风险（3~5 条，每条严格按照以下固定格式）
* **[股票代码] 事件标题**
  * **影响属性**: 🟢 利好 / 🔴 利空 / ⚪ 中性
  * **核心逻辑**: 50字以内概括事件实质及其对基本面或短期估值的影响。

#### 3. 盘前情绪总结（1 句话定调多空博弈偏向）
"""

# ----------------- 3. API 调用与联网搜索配置 -----------------
def generate_briefing() -> str:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在检索并分析科技股动态...")
    
    # 使用 2.5-flash 实现极致的成本与速度平衡
    response = client.models.generate_content(
        model="gemini-2.5-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            # 开启 Google Search Grounding 实时联网
            tools=[{"google_search": {}}],
            # 压低采样温度，确保事件归纳精准、客观、不发散
            temperature=0.2,
            # 关闭思考模式（针对 2.5-flash），节省大量思考 Token 并降低 3~5 秒延迟
            thinking_config=types.ThinkingConfig(thinking_budget=0),
            # 硬性截断输出长度，防止模型过度扩写
            max_output_tokens=1500,
        ),
    )
    
    # 打印 Token 消耗明细（方便监控成本）
    if response.usage_metadata:
        usage = response.usage_metadata
        print("\n--- Token 统计 ---")
        print(f"输入 Tokens: {usage.prompt_token_count}")
        print(f"输出 Tokens: {usage.candidates_token_count}")
        print(f"总计 Tokens: {usage.total_token_count}\n")
    
    return response.text

# ----------------- 4. 推送渠道支持（以飞书 Webhook 为例） -----------------
def send_to_webhook(content: str):
    if not WEBHOOK_URL:
        print("未检测到 WEBHOOK_URL，跳过推送步骤。")
        return

    # 飞书机器人消息格式（其他平台如钉钉、企业微信仅需调整 payload 字段）
    payload = {
        "msg_type": "interactive",
        "card": {
            "header": {
                "title": {"tag": "plain_text", "content": "📊 每日科技股核心动态速递"},
                "template": "blue"
            },
            "elements": [
                {"tag": "markdown", "content": content}
            ]
        }
    }
    
    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print("消息推送成功！")
    except Exception as e:
        print(f"消息推送失败: {e}", file=sys.stderr)

# ----------------- 5. 主执行入口 -----------------
if __name__ == "__main__":
    report = generate_briefing()
    print("----- 生成内容预览 -----")
    print(report)
    print("------------------------")
    
    send_to_webhook(report)
