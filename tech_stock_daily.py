import os
import sys
from datetime import datetime, timezone
import requests
from google import genai
from google.genai import types

# ----------------- 1. 配置与环境检查 -----------------
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

WEBHOOK_URL = os.getenv("WEBHOOK_URL")

if not GEMINI_API_KEY:
    print("错误: 请先设置环境变量 GEMINI_API_KEY", file=sys.stderr)
    sys.exit(1)

client = genai.Client(api_key=GEMINI_API_KEY)

# ----------------- 2. 动态生成 Token 优化提示词 -----------------
today_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")

# 限制范围：仅追踪核心巨头与半导体链条，防止漫无目的地检索全网海量小盘股
TICKER_SCOPE = "NVDA, MSFT, AAPL, GOOGL, AMZN, META, TSLA, ASML, AVGO"

prompt = f"""
你是一名资深美股量化宏观与科技板块研究员。
当前基准日期（UTC）：{today_str}。
请检索过去 24 小时内关于以下标的的核心动态及关键宏观/行业事件：[{TICKER_SCOPE}]。

【输出硬性约束】
1. 语言：中文。
2. 筛选规则：仅挑出对股价最具实质影响的「Top 3 ~ 5 个重大事件」，剔除常规盘后波动与无意义公关稿。
3. 多空判定硬性标准（必须严格执行）：
   - 统一以「美股开盘后 1~3 个交易日内的市场情绪与估值预期」为唯一基准，禁止从中长期视角定性短期新闻。
   - 🟢 利好：超预期财报/业绩指引上调、大行评级上调、重大商业/技术落地。
   - 🔴 利空：反垄断/监管立案处罚、财报不及预期/下调指引、高管大额减持、核心业务份额流失。
   - ⚪ 中性/分歧：多空交织、短期影响不明确或市场已有充分预期的事件。
4. 严格遵循以下 Markdown 结构输出，不要包含任何前言开场白或免责声明废话：

### 📅 美股科技核心晨报 ({today_str})

#### 1. 宏观与板块主线（1~2 句话概述大盘或科技板块当日流动性/利率/情绪特征）

#### 2. 核心催化剂与风险（3~5 条，每条严格按照以下固定格式）
* **[股票代码] 事件标题**
  * **影响属性**: 🟢 利好 / 🔴 利空 / ⚪ 中性
  * **核心逻辑**: 50字以内概括事件实质及其对短期开盘情绪的具体影响。

#### 3. 盘前情绪总结（1 句话定调多空博弈偏向）
"""
# ----------------- 3. API 调用与联网搜索配置 -----------------
def generate_briefing() -> str:
    print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在检索并分析科技股动态...")
    
    # 使用 2.5-flash 实现极致的成本与速度平衡
    response = client.models.generate_content(
        model="gemini-3.6-flash",
        contents=prompt,
        config=types.GenerateContentConfig(
            # 开启 Google Search Grounding 实时联网
            tools=[{"google_search": {}}],
            # 压低采样温度，确保事件归纳精准、客观、不发散
            temperature=0.0,
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

# ----------------- 4. Discord 专属 Webhook 推送 -----------------
def send_to_webhook(content: str):
    if not WEBHOOK_URL:
        print("未检测到 WEBHOOK_URL，跳过推送步骤。")
        return

    # Discord Embed 格式：排版整洁、支持 Markdown，且单条最大支持 4096 字符
    payload = {
        "embeds": [
            {
                "title": "❤️ Hello",
                "description": content[:4000],  # 截断防止超出 Discord 4096 限制
                "color": 1710618,  # 卡片左侧装饰条颜色（黑金）
            }
        ]
    }
    
    try:
        res = requests.post(WEBHOOK_URL, json=payload, timeout=10)
        res.raise_for_status()
        print("Discord 消息推送成功！")
    except Exception as e:
        print(f"Discord 消息推送失败: {e}", file=sys.stderr)
        if hasattr(e, 'response') and e.response is not None:
            print(f"Discord 接口返回详细信息: {e.response.text}", file=sys.stderr)

# ----------------- 5. 写入 GitHub Actions 页面摘要 (Summary) -----------------
def write_github_summary(content: str):
    summary_path = os.getenv("GITHUB_STEP_SUMMARY")
    if summary_path:
        try:
            with open(summary_path, "a", encoding="utf-8") as f:
                f.write(content + "\n")
            print("已成功写入 GitHub Actions Summary 摘要看板！")
        except Exception as e:
            print(f"写入 GitHub Summary 失败: {e}", file=sys.stderr)
    else:
        print("本地运行环境，未检测到 GITHUB_STEP_SUMMARY 变量。")

# ----------------- 6. 写入仓库首页 README.md (新加进去) -----------------
def update_readme(content: str):
    readme_template = f"""# 📈 每日美股科技板块核心研报

> 🤖 本页面由 Google Gemini + GitHub Actions 每天在美股开盘前自动检索、分析并更新。

{content}

---
*免责声明：以上内容由 AI 自动搜集公开市场资讯生成，仅供技术研究与信息参考，不构成任何投资建议。*
"""
    try:
        with open("README.md", "w", encoding="utf-8") as f:
            f.write(readme_template)
        print("已成功写入 README.md 文件！")
    except Exception as e:
        print(f"写入 README.md 失败: {e}", file=sys.stderr)
        
# ----------------- 7. 主执行入口 -----------------
if __name__ == "__main__":
    # 1. 生成科技股简报
    report = generate_briefing()
    
    # 2. 控制台打印预览
    print("----- 生成内容预览 -----")
    print(report)
    print("------------------------")
    
    # 3. 写入 GitHub 网页端摘要（只要在 Actions 中跑就会自动渲染）
    write_github_summary(report)
    
    # 4. 覆盖更新仓库首页 README
    update_readme(report)
    
    # 5. 如果配置了 Webhook，推送到手机/聊天软件
    send_to_webhook(report)
