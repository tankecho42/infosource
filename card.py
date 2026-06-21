"""
InfoSource 统一卡片发送
支持所有来源，单篇模式，带摘要+评价+反馈按钮。

Usage:
  python3 card.py push --uid lr:xxx --title "标题" --url "..." --summary "摘要" --score 2.5 --source linkresearcher --domains "AI,agent"
"""
import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

import httpx

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db
from engine import record_push

INFO_FLOW = "oc_3668bcaf14eb1b01ce5b5deeb13b3ab9"
CACHE_DIR = Path.home() / ".hermes" / "scripts" / "infosource" / "card_cache"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def load_env():
    env = {}
    env_path = os.path.expanduser("~/.hermes/.env")
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k] = v.strip('"').strip("'")
    return env


def get_token(env):
    r = httpx.post(
        "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal",
        json={"app_id": env["FEISHU_APP_ID"], "app_secret": env["FEISHU_APP_SECRET"]},
        timeout=10,
    )
    return r.json()["tenant_access_token"]


def _source_meta(source):
    """来源元信息：返回 (emoji, display_name, color_template)"""
    return {
        "linkresearcher": ("📰", "领研网", "blue"),
        "twitter":       ("🐦", "Twitter", "cyan"),
    }.get(source, ("📡", source or "未知", "blue"))


def build_card(uid, title, url, summary, score=0, domains=None, source="", published_at="", author="", author_url=""):
    """构造单篇文章卡片"""
    emoji, src_name, template = _source_meta(source)
    elements = []

    # 标题（可点击跳转）
    title_md = f"**[{title}]({url})**" if url else f"**{title}**"
    elements.append({
        "tag": "div",
        "text": {"tag": "lark_md", "content": title_md},
    })

    # 元信息：每项一行，图标开头
    meta_lines = []
    if author:
        author_md = f"👤 {author}" if not author_url else f"👤 [{author}]({author_url})"
        meta_lines.append(author_md)
    if published_at:
        meta_lines.append(f"🕒 {published_at}")
    if domains:
        meta_lines.append("🏷️ " + " · ".join(domains[:3]))
    if score:
        meta_lines.append(f"⭐ 兴趣匹配 {score:+.1f}")
    if meta_lines:
        meta_text = "\n".join(meta_lines)
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": f"<font color='grey'>{meta_text}</font>"},
        })

    elements.append({"tag": "hr"})

    # Echo的摘要+评价
    if summary:
        elements.append({
            "tag": "div",
            "text": {"tag": "lark_md", "content": summary},
        })

    # 按钮
    elements.append({
        "tag": "action",
        "actions": [
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "感兴趣"},
                "type": "primary",
                "value": {"action": "feedback", "rating": "good", "uid": uid},
            },
            {
                "tag": "button",
                "text": {"tag": "plain_text", "content": "不感兴趣"},
                "type": "danger",
                "value": {"action": "feedback", "rating": "bad", "uid": uid},
            },
        ],
    })

    card = {
        "config": {"wide_screen_mode": True, "enable_forward": True},
        "header": {
            "title": {"tag": "plain_text", "content": f"{emoji} {src_name}"},
            "template": template,
        },
        "elements": elements,
    }
    return card


def send_card(token, chat_id, card):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    params = {"receive_id_type": "chat_id"}
    payload = {"receive_id": chat_id, "msg_type": "interactive", "content": json.dumps(card)}
    r = httpx.post(url, params=params, json=payload, headers={"Authorization": f"Bearer {token}"}, timeout=10)
    data = r.json()
    if data.get("code") != 0:
        print(f"Send failed: {json.dumps(data, ensure_ascii=False)}", file=sys.stderr)
        return None
    return data.get("data", {}).get("message_id")


def cmd_push(args):
    if not args.uid or not args.title:
        print("需要 --uid 和 --title", file=sys.stderr)
        sys.exit(1)

    domains = [d.strip() for d in args.domains.split(",") if d.strip()] if args.domains else []
    card = build_card(args.uid, args.title, args.url, args.summary, args.score, domains, args.source, args.published_at, args.author, args.author_url)

    if args.dry_run:
        print(json.dumps(card, ensure_ascii=False, indent=2))
        return

    env = load_env()
    token = get_token(env)
    msg_id = send_card(token, args.chat, card)

    if msg_id:
        # 记录推送
        conn = get_db()
        record_push(conn, args.uid, args.source, args.title, args.url, args.score, args.summary)
        conn.close()

        # 按uid缓存卡片JSON
        safe_uid = args.uid.replace("/", "_")
        cache = CACHE_DIR / f"{safe_uid}.json"
        with open(cache, "w") as f:
            json.dump({"msg_id": msg_id, "card": card, "uid": args.uid}, f, ensure_ascii=False)
        print(f"✓ Card sent, msg_id={msg_id}")
    else:
        print("✗ Failed", file=sys.stderr)
        sys.exit(1)


def main():
    parser = argparse.ArgumentParser(description="InfoSource 统一卡片发送")
    sub = parser.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("push", help="发送单篇卡片")
    p.add_argument("--uid", required=True, help="文章UID（带来源前缀）")
    p.add_argument("--title", required=True, help="文章标题")
    p.add_argument("--url", default="", help="文章链接")
    p.add_argument("--summary", default="", help="Echo的摘要评价")
    p.add_argument("--score", type=float, default=0, help="兴趣匹配分")
    p.add_argument("--domains", default="", help="领域标签，逗号分隔")
    p.add_argument("--source", default="", help="来源key")
    p.add_argument("--published-at", default="", help="原始发布时间")
    p.add_argument("--author", default="", help="作者名/账号")
    p.add_argument("--author-url", default="", help="作者主页链接")
    p.add_argument("--chat", default=INFO_FLOW, help="目标 chat_id")
    p.add_argument("--dry-run", action="store_true", help="只打印不发送")
    args = parser.parse_args()

    if args.cmd == "push":
        cmd_push(args)


if __name__ == "__main__":
    main()
