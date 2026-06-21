"""
InfoSource 统一推荐引擎
打分 + 探索机制 + 反馈学习 + 分类统计

Usage:
  python3 engine.py score <source>          # 对某来源的新文章打分
  python3 engine.py record <rating> --uid X  # 记录单条反馈
  python3 engine.py prefs                    # 查看偏好与统计
  python3 engine.py stats                    # 查看分类统计
  python3 engine.py reset                    # 重置偏好
"""
import argparse
import json
import os
import random
import re
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, safe_commit, pref_get, pref_set

# 领域关键词字典
DOMAIN_KEYWORDS = {
    "AI": ["AI", "人工智能", "大模型", "GPT", "LLM", "机器学习", "深度学习", "神经网络", "ChatGPT", "Claude", "Gemini", "智能", "算法", "推理", "OpenAI", "DeepMind", "Anthropic", "脑机", "agent", "智能体"],
    "芯片": ["芯片", "半导体", "GPU", "CPU", "处理器", "光刻", "EDA", "封装", "台积电", "英伟达", "NVIDIA", "AMD", "Intel", "集成电路", "硅", "晶体管", "光模块", "算力"],
    "生物": ["基因", "DNA", "RNA", "蛋白质", "细胞", "免疫", "癌症", "疫苗", "大脑", "神经", "衰老", "寿命", "代谢", "药物", "CRISPR", "干细胞", "脑科学"],
    "物理": ["量子", "粒子", "超导", "相对论", "黑洞", "宇宙", "原子", "光子", "凝聚态", "拓扑", "纳米", "材料"],
    "航天": ["火箭", "太空", "月球", "火星", "卫星", "空间站", "航天", "宇航", "星舰", "SpaceX", "嫦娥", "神舟"],
    "能源": ["电池", "核聚变", "太阳能", "氢能", "风电", "储能", "碳中和", "排放", "气候", "清洁能源"],
    "计算": ["编程", "代码", "软件", "数据", "网络安全", "加密", "区块链", "量子计算", "云计算", "开源", "GitHub"],
    "社会": ["大学", "博士", "留学", "签证", "教授", "学术", "论文", "NSF", "NIH", "哈佛", "科研", "撤稿"],
}

DEFAULT_PREFS = {
    "domain_weights": {"AI": 1.5, "芯片": 1.2, "计算": 0.8, "航天": 0.3, "生物": 0.0, "物理": 0.0, "能源": 0.0, "社会": -0.5},
    "keyword_weights": {},
    "category_stats": {d: {"impressions": 0, "feedback_count": 0, "feedback_sum": 0.0} for d in DOMAIN_KEYWORDS},
    "exploration": {"temperature": 1.0, "decay_per_push": 0.002, "min_temperature": 0.3},
    "stats": {"total_pushed": 0, "total_feedback": 0, "positive": 0, "negative": 0},
    "feedback_history": [],
}


# ── 偏好管理 ──────────────────────────────────────────

def load_prefs(conn):
    """加载偏好，合并默认值"""
    prefs = {}
    for key in DEFAULT_PREFS:
        val = pref_get(conn, key, DEFAULT_PREFS[key])
        prefs[key] = val
    _ensure_category_stats(prefs)
    return prefs


def save_prefs(conn, prefs):
    for key, val in prefs.items():
        pref_set(conn, key, val)


def _ensure_category_stats(prefs):
    if "category_stats" not in prefs:
        prefs["category_stats"] = {}
    for d in DOMAIN_KEYWORDS:
        if d not in prefs["category_stats"]:
            prefs["category_stats"][d] = {"impressions": 0, "feedback_count": 0, "feedback_sum": 0.0}
    if "exploration" not in prefs:
        prefs["exploration"] = {"temperature": 1.0, "decay_per_push": 0.002, "min_temperature": 0.3}


# ── 分类与打分 ────────────────────────────────────────

def classify_article(title):
    scores = {}
    for domain, keywords in DOMAIN_KEYWORDS.items():
        count = sum(1 for kw in keywords if kw.lower() in title.lower())
        if count > 0:
            scores[domain] = count
    return scores


def _exploration_bonus(domain_matches, prefs):
    cat_stats = prefs.get("category_stats", {})
    exp = prefs.get("exploration", {"temperature": 1.0, "min_temperature": 0.3})
    temp = max(exp.get("temperature", 1.0), exp.get("min_temperature", 0.3))

    seen = [cat_stats.get(d, {}).get("impressions", 0) for d in DOMAIN_KEYWORDS if cat_stats.get(d, {}).get("impressions", 0) > 0]
    avg_imp = sum(seen) / len(seen) if seen else 5.0
    avg_imp = max(avg_imp, 3.0)

    bonus = 0.0
    for domain in domain_matches:
        s = cat_stats.get(domain, {})
        impressions = s.get("impressions", 0)
        fb_count = s.get("feedback_count", 0)
        fb_sum = s.get("feedback_sum", 0.0)

        if impressions < avg_imp:
            novelty = (avg_imp - impressions) / avg_imp
            bonus += 0.4 * novelty * temp

        if impressions >= 3 and fb_count / max(impressions, 1) < 0.3:
            uncertainty = 1.0 - (fb_count / max(impressions, 1))
            bonus += 0.2 * uncertainty * temp

        if fb_count >= 3 and fb_sum < -1.0:
            bonus -= 0.3

    bonus += random.uniform(0, 0.25 * temp)
    return bonus


def score_article(title, prefs, explore=True):
    _ensure_category_stats(prefs)
    score = 0.0
    domain_matches = classify_article(title)

    for domain, count in domain_matches.items():
        weight = prefs["domain_weights"].get(domain, 0)
        score += weight * count

    for kw, weight in prefs.get("keyword_weights", {}).items():
        if kw.lower() in title.lower():
            score += weight

    if len(title) > 80:
        score -= 0.3

    hot_words = ["突破", "首次", "最新", "新发现", "刷新", "迄今"]
    for hw in hot_words:
        if hw in title:
            score += 0.2

    if explore and domain_matches:
        score += _exploration_bonus(domain_matches, prefs)

    return score


# ── 反馈学习 ──────────────────────────────────────────

def extract_keywords(title):
    cn_words = re.findall(r'[\u4e00-\u9fff]{2,6}', title)
    en_words = re.findall(r'[A-Za-z]{3,}', title)
    return cn_words + en_words


def update_prefs_from_feedback(prefs, title, feedback_val):
    _ensure_category_stats(prefs)
    delta = 0.15 if feedback_val > 0 else (-0.2 if feedback_val < 0 else 0)
    if delta == 0:
        return

    domain_matches = classify_article(title)
    for domain in domain_matches:
        current = prefs["domain_weights"].get(domain, 0)
        prefs["domain_weights"][domain] = round(current + delta, 3)
        cat = prefs["category_stats"].setdefault(domain, {"impressions": 0, "feedback_count": 0, "feedback_sum": 0.0})
        cat["feedback_count"] += 1
        cat["feedback_sum"] = round(cat["feedback_sum"] + feedback_val, 3)

    keywords = extract_keywords(title)
    for kw in keywords:
        if len(kw) < 2:
            continue
        current = prefs["keyword_weights"].get(kw, 0)
        prefs["keyword_weights"][kw] = round(current + delta * 0.5, 3)

    prefs["keyword_weights"] = {k: v for k, v in prefs["keyword_weights"].items() if abs(v) >= 0.05}

    if feedback_val > 0:
        prefs["stats"]["positive"] += 1
    elif feedback_val < 0:
        prefs["stats"]["negative"] += 1


# ── 推送记录与曝光 ────────────────────────────────────

def record_push(conn, uid, source, title, url, score, summary=""):
    """记录推送 + 更新曝光 + 探索降温"""
    conn.execute(
        "INSERT INTO pushed (uid, source, title, url, summary, score) VALUES (?, ?, ?, ?, ?, ?)",
        (uid, source, title, url, summary, score),
    )
    conn.execute("UPDATE articles SET pushed=1 WHERE uid=?", (uid,))
    conn.execute("UPDATE sources SET total_pushed=total_pushed+1 WHERE key=?", (source,))

    prefs = load_prefs(conn)
    domain_matches = classify_article(title)
    for domain in domain_matches:
        cat = prefs["category_stats"].setdefault(domain, {"impressions": 0, "feedback_count": 0, "feedback_sum": 0.0})
        cat["impressions"] += 1

    exp = prefs["exploration"]
    exp["temperature"] = round(max(
        exp.get("temperature", 1.0) - exp.get("decay_per_push", 0.002),
        exp.get("min_temperature", 0.3),
    ), 4)

    prefs["stats"]["total_pushed"] += 1
    save_prefs(conn, prefs)
    safe_commit(conn)


def record_feedback(conn, uid, rating):
    """记录单条反馈"""
    val = {"good": 1, "bad": -1, "meh": 0}.get(rating, 0)
    if val == 0 and rating != "meh":
        return {"error": f"unknown rating: {rating}"}

    row = conn.execute("SELECT * FROM pushed WHERE uid=? AND feedback IS NULL ORDER BY pushed_at DESC LIMIT 1", (uid,)).fetchone()
    if not row:
        return {"error": "article not found or already rated"}

    conn.execute(
        "UPDATE pushed SET feedback=?, feedback_at=datetime('now','localtime') WHERE id=?",
        (val, row["id"]),
    )
    conn.execute("UPDATE sources SET total_feedback=total_feedback+1 WHERE key=?", (row["source"],))

    prefs = load_prefs(conn)
    update_prefs_from_feedback(prefs, row["title"], val)
    prefs["stats"]["total_feedback"] += 1
    prefs["feedback_history"].append({"date": datetime.now().isoformat(), "title": row["title"], "uid": uid, "feedback": val})
    prefs["feedback_history"] = prefs["feedback_history"][-200:]
    save_prefs(conn, prefs)
    safe_commit(conn)

    return {"ok": True, "title": row["title"], "rating": rating, "source": row["source"]}


# ── 打分命令 ──────────────────────────────────────────

def cmd_score(source=None):
    """对未推送的文章打分，输出JSON"""
    conn = get_db()
    prefs = load_prefs(conn)

    query = "SELECT * FROM articles WHERE pushed=0"
    params = []
    if source:
        query += " AND source=?"
        params.append(source)
    query += " ORDER BY fetched_at DESC"

    articles = [dict(r) for r in conn.execute(query, params).fetchall()]
    conn.close()

    if not articles:
        print(json.dumps({"articles": [], "count": 0}))
        return

    for a in articles:
        s = score_article(a["title"], prefs)
        a["score"] = round(s, 3)
        a["domains"] = list(classify_article(a["title"]).keys())

    articles.sort(key=lambda x: x["score"], reverse=True)
    print(json.dumps({"articles": articles, "count": len(articles)}, ensure_ascii=False))


def cmd_record(rating, uid):
    conn = get_db()
    result = record_feedback(conn, uid, rating)
    conn.close()
    print(json.dumps(result, ensure_ascii=False))


def cmd_prefs():
    conn = get_db()
    prefs = load_prefs(conn)

    print("📊 领域偏好权重:")
    for domain, weight in sorted(prefs["domain_weights"].items(), key=lambda x: -x[1]):
        bar = "█" * int(max(0, weight) * 5) + "░" * int(max(0, -weight) * 5)
        print(f"  {domain:6s} {weight:+.2f} {bar}")

    if prefs.get("keyword_weights"):
        print("\n📝 动态关键词权重 (Top 20):")
        for kw, weight in sorted(prefs["keyword_weights"].items(), key=lambda x: -abs(x[1]))[:20]:
            print(f"  {kw:12s} {weight:+.3f}")

    s = prefs["stats"]
    exp = prefs.get("exploration", {})
    print(f"\n📈 统计: 推送 {s['total_pushed']} 篇, 反馈 {s['total_feedback']} 条 (正{s['positive']}/负{s['negative']})")
    print(f"🔥 探索温度: {exp.get('temperature', 1.0)} (下限 {exp.get('min_temperature', 0.3)})")

    print("\n📋 分类统计:")
    print(f"  {'领域':6s} {'曝光':>4s} {'反馈':>4s} {'率':>5s} {'分':>6s} {'平均':>6s}")
    print(f"  {'─'*6} {'─'*4} {'─'*4} {'─'*5} {'─'*6} {'─'*6}")
    for domain in DOMAIN_KEYWORDS:
        cat = prefs["category_stats"].get(domain, {})
        imp = cat.get("impressions", 0)
        fb = cat.get("feedback_count", 0)
        fbs = cat.get("feedback_sum", 0.0)
        rate = f"{fb/imp*100:.0f}%" if imp > 0 else "—"
        avg = f"{fbs/fb:+.2f}" if fb > 0 else "—"
        print(f"  {domain:6s} {imp:4d} {fb:4d} {rate:>5s} {fbs:+6.2f} {avg:>6s}")

    # 来源统计
    print("\n📡 来源统计:")
    rows = conn.execute("SELECT key, name, prefix, enabled, total_pushed, total_feedback, last_check FROM sources").fetchall()
    if rows:
        print(f"  {'来源':16s} {'前缀':4s} {'开关':>4s} {'推送':>4s} {'反馈':>4s} {'上次检查':>20s}")
        for r in rows:
            sw = "✅" if r["enabled"] else "❌"
            print(f"  {r['name']:16s} {r['prefix']:4s} {sw:>4s} {r['total_pushed']:4d} {r['total_feedback']:4d} {r['last_check'] or '—':>20s}")
    else:
        print("  （暂无注册来源）")
    conn.close()


def cmd_reset():
    conn = get_db()
    for key in DEFAULT_PREFS:
        pref_set(conn, key, json.loads(json.dumps(DEFAULT_PREFS[key])))
    safe_commit(conn)
    conn.close()
    print("✓ 偏好已重置")


def main():
    parser = argparse.ArgumentParser(description="InfoSource 统一推荐引擎")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sc = sub.add_parser("score", help="对未推送文章打分")
    sc.add_argument("source", nargs="?", default=None, help="只打分某来源")
    rec = sub.add_parser("record", help="记录单条反馈")
    rec.add_argument("rating", choices=["good", "bad", "meh"])
    rec.add_argument("--uid", required=True)
    sub.add_parser("prefs", help="查看偏好与统计")
    sub.add_parser("stats", help="查看分类统计（同prefs）")
    sub.add_parser("reset", help="重置偏好")
    args = parser.parse_args()

    if args.cmd == "score":
        cmd_score(args.source)
    elif args.cmd == "record":
        cmd_record(args.rating, args.uid)
    elif args.cmd in ("prefs", "stats"):
        cmd_prefs()
    elif args.cmd == "reset":
        cmd_reset()


if __name__ == "__main__":
    main()
