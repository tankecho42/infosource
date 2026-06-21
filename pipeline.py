#!/usr/bin/env python3
"""
InfoSource 全自动推送 Pipeline
纯脚本实现：检查 → 打分 → 抓正文 → LLM摘要 → 发卡片
不需要 agent 参与，LLM 调用自带 Z.ai → DeepSeek fallback。

Usage:
  python3 pipeline.py                    # 完整运行
  python3 pipeline.py --dry-run          # 只打分和摘要，不发卡片
  python3 pipeline.py --score-threshold 0.8  # 自定义推送阈值
"""
import json
import os
import sys
import time
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, safe_commit
from scheduler import check_all, fetch_detail
from engine import score_article, classify_article, load_prefs, record_push
from card import build_card, send_card, load_env, get_token, INFO_FLOW

# ── LLM 配置 ──────────────────────────────────────────

def load_llm_config():
    """从 ~/.hermes/.env 和 config.yaml 读取 LLM 配置"""
    env = load_env()

    # Z.ai (primary)
    zai_key = env.get("GLM_API_KEY", "")
    # DeepSeek (fallback)
    ds_key = env.get("DEEPSEEK_API_KEY", "")

    providers = []

    if zai_key:
        providers.append({
            "name": "zai",
            "base_url": "https://open.bigmodel.cn/api/paas/v4",
            "api_key": zai_key,
            "model": "glm-4-flash",  # 摘要用 flash，快且便宜
        })

    if ds_key:
        providers.append({
            "name": "deepseek",
            "base_url": "https://api.deepseek.com/v1",
            "api_key": ds_key,
            "model": "deepseek-chat",
        })

    return providers


def llm_chat(providers, system_prompt, user_prompt, timeout=30):
    """调用 LLM，自动 fallback。返回文本或 None。"""
    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    for p in providers:
        try:
            url = p["base_url"].rstrip("/") + "/chat/completions"
            r = httpx.post(url, json={
                "model": p["model"],
                "messages": messages,
                "max_tokens": 500,
                "temperature": 0.7,
            }, headers={
                "Authorization": f"Bearer {p['api_key']}",
            }, timeout=timeout)

            data = r.json()
            if "error" in data:
                print(f"  [{p['name']}] error: {data['error'].get('message','')[:100]}", file=sys.stderr)
                continue

            content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
            if content.strip():
                return content.strip()

        except Exception as e:
            print(f"  [{p['name']}] failed: {str(e)[:100]}", file=sys.stderr)
            continue

    return None


# ── 摘要生成 ──────────────────────────────────────────

SUMMARY_SYSTEM = """你是 Echo，Tank 的数字伙伴。你在为 Tank 写新闻摘要。

你需要输出两样东西，严格按以下格式：

摘要：（2-3句话，精简到能扫一眼就懂：核心是什么事 + 为什么值得看。附上你的判断：真突破还是噱头？语气自然直接，像跟朋友说"嘿这条值得看"。不要公文腔。中文。）
标签：（2-4个标签，用英文逗号分隔。根据文章内容和主题生成，要具体。例如：AI安全,OpenAI,强化学习 / 光模块,半导体,Kioxia / 航天,SpaceX,星舰）

示例：
摘要：OpenAI发了篇研究，用强化学习训练模型在复杂对话中保持有益且安全的行为。值得关注——这不只是论文，是OpenAI在AGI安全上的实际投入。
标签：AI安全,OpenAI,强化学习,对齐"""

import re as _re

def generate_summary(providers, article, content=None):
    """为单篇文章生成摘要和标签。返回 (summary, tags)。"""
    title = article["title"]
    url = article.get("url", "")
    source = article.get("source", "")

    # 构造提示
    user_parts = [f"标题：{title}"]
    if article.get("author"):
        user_parts.append(f"作者：{article['author']}")
    if content:
        # 截取前2000字
        user_parts.append(f"正文摘要：\n{content[:2000]}")
    user_parts.append("请按格式输出摘要和标签。")

    user_prompt = "\n".join(user_parts)
    raw = llm_chat(providers, SUMMARY_SYSTEM, user_prompt)

    if not raw:
        # 所有 LLM 都挂了，用 fallback
        from engine import classify_article
        kw_domains = list(classify_article(title).keys())
        summary = f"标题党含量不确定，自己点进去看吧。来源：{source}"
        return summary, kw_domains if kw_domains else ["资讯"]

    # 解析摘要和标签
    summary = raw
    tags = []

    # 提取标签行
    tag_match = _re.search(r'标签[：:](.+)', raw)
    if tag_match:
        tag_str = tag_match.group(1).strip()
        # 同时处理中英文逗号
        raw_tags = _re.split(r'[,，、\s]+', tag_str)
        tags = [t.strip().strip("\"'""')") for t in raw_tags if t.strip()]
        # 从摘要中移除标签行
        summary = _re.sub(r'\n*标签[：:].+', '', raw).strip()

    # 如果标签太少，补充关键词匹配的领域
    if len(tags) < 2:
        from engine import classify_article
        kw_domains = list(classify_article(title).keys())
        for d in kw_domains:
            if d not in tags:
                tags.append(d)
        if len(tags) < 2:
            tags.append("资讯")

    return summary, tags


# ── Pipeline 主流程 ───────────────────────────────────

def run_pipeline(score_threshold=0.5, dry_run=False, max_pushes=30):
    """完整推送流程"""
    print(f"🚀 InfoSource Pipeline 启动 (threshold={score_threshold}, dry_run={dry_run})")

    # 1. 检查新文章
    print("\n📥 Step 1: 检查新文章...")
    results = check_all()
    total_new = sum(r.get("new", 0) for r in results)
    for r in results:
        status = f"{r.get('new',0)} 新" if r.get("new", 0) > 0 else "无新文章"
        print(f"  {r.get('source','?')}: known={r.get('known',0)} fetched={r.get('fetched',0)} → {status}")

    # 2. 打分所有未推送文章（包括积压的）
    print("\n📊 Step 2: 打分未推送文章...")
    conn = get_db()
    prefs = load_prefs(conn)

    unpushed = [dict(r) for r in conn.execute(
        "SELECT * FROM articles WHERE pushed=0 ORDER BY fetched_at DESC"
    ).fetchall()]
    conn.close()

    if not unpushed:
        print("  没有未推送的文章，pipeline 结束。")
        return {"new_fetched": total_new, "pushed": 0, "skipped": 0}

    # 打分
    for a in unpushed:
        a["score"] = score_article(a["title"], prefs)
        a["domains"] = list(classify_article(a["title"]).keys())

    # 按分数排序
    unpushed.sort(key=lambda x: x["score"], reverse=True)

    # 筛选达标的
    to_push = [a for a in unpushed if a["score"] >= score_threshold][:max_pushes]
    skipped = [a for a in unpushed if a["score"] < score_threshold]

    print(f"  未推送: {len(unpushed)} 篇")
    print(f"  达标(≥{score_threshold}): {len(to_push)} 篇")
    print(f"  不达标: {len(skipped)} 篇")

    if not to_push:
        print("  没有达标文章需要推送。")

        # 标记不达标的为已处理（避免无限积压）
        if skipped:
            conn = get_db()
            for a in skipped:
                conn.execute("UPDATE articles SET pushed=-1 WHERE uid=?", (a["uid"],))
            safe_commit(conn)
            conn.close()
            print(f"  已标记 {len(skipped)} 篇不达标文章为跳过(pushed=-1)")

        return {"new_fetched": total_new, "pushed": 0, "skipped": len(skipped)}

    if dry_run:
        print("\n🧪 DRY RUN - 不发送卡片:")
        for a in to_push:
            print(f"  [{a['score']:+.2f}] {a['title'][:50]}")
        return {"new_fetched": total_new, "pushed": 0, "skipped": len(skipped), "dry_run": True}

    # 3. 加载 LLM 配置
    print("\n🤖 Step 3: 加载 LLM 配置...")
    providers = load_llm_config()
    for p in providers:
        print(f"  {p['name']}: model={p['model']}")
    if not providers:
        print("  ❌ 没有可用的 LLM provider!")
        return {"error": "no LLM provider available"}

    # 4. 获取飞书 token
    env = load_env()
    token = get_token(env)

    # 5. 逐篇处理：抓正文 → 写摘要 → 发卡片
    print(f"\n📤 Step 4: 推送 {len(to_push)} 篇文章...")
    pushed_count = 0
    failed_count = 0

    for i, a in enumerate(to_push):
        uid = a["uid"]
        title = a["title"]
        source = a.get("source", "")
        url = a.get("url", "")
        score = a["score"]
        domains = a["domains"]
        published_at = a.get("published_at", "") or ""
        author = a.get("author", "") or ""
        author_url = a.get("author_url", "") or ""

        print(f"\n  [{i+1}/{len(to_push)}] ⭐{score:+.2f} {title[:40]}...")

        # 抓正文
        content = None
        if url:
            try:
                detail = fetch_detail(source, url)
                content = detail.get("content", "")
            except Exception as e:
                print(f"    抓正文失败: {e}")

        # LLM 摘要 + 标签
        summary, tags = generate_summary(providers, a, content)
        if summary:
            print(f"    摘要: {summary[:60]}...")
            print(f"    标签: {','.join(tags)}")
        else:
            print(f"    ⚠️ 摘要生成失败，跳过")
            failed_count += 1
            continue

        # 发卡片（用 LLM 生成的标签覆盖关键词匹配的 domains）
        card = build_card(uid, title, url, summary, score, tags, source, published_at, author, author_url)
        msg_id = send_card(token, INFO_FLOW, card)

        if msg_id:
            # 记录推送
            conn = get_db()
            record_push(conn, uid, source, title, url, score, summary)
            conn.close()
            pushed_count += 1
            print(f"    ✅ 已推送 (msg_id={msg_id[:12]}...)")
        else:
            failed_count += 1
            print(f"    ❌ 推送失败")

        # 避免 LLM 速率限制
        time.sleep(1)

    # 6. 标记不达标的
    if skipped:
        conn = get_db()
        for a in skipped:
            conn.execute("UPDATE articles SET pushed=-1 WHERE uid=?", (a["uid"],))
        safe_commit(conn)
        conn.close()

    print(f"\n{'='*50}")
    print(f"📊 Pipeline 完成:")
    print(f"  新抓取: {total_new} 篇")
    print(f"  已推送: {pushed_count} 篇")
    print(f"  推送失败: {failed_count} 篇")
    print(f"  不达标跳过: {len(skipped)} 篇")
    print(f"  剩余积压: {len(unpushed) - pushed_count} 篇")

    return {
        "new_fetched": total_new,
        "pushed": pushed_count,
        "failed": failed_count,
        "skipped": len(skipped),
    }


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="InfoSource 全自动推送 Pipeline")
    parser.add_argument("--dry-run", action="store_true", help="只打分不发送")
    parser.add_argument("--score-threshold", type=float, default=0.5, help="推送阈值")
    parser.add_argument("--max-pushes", type=int, default=30, help="单次最大推送数")
    args = parser.parse_args()

    result = run_pipeline(
        score_threshold=args.score_threshold,
        dry_run=args.dry_run,
        max_pushes=args.max_pushes,
    )
    print(json.dumps(result, ensure_ascii=False))
