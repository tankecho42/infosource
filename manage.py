"""
InfoSource 来源管理工具
注册/查看/开关/删除 信息来源。

Usage:
  python3 manage.py add <key> <name> <prefix> [--interval 30] [--config '{}']
  python3 manage.py list
  python3 manage.py toggle <key>          # 开关
  python3 manage.py remove <key>
  python3 manage.py info <key>            # 查看详情
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from db import get_db, safe_commit


def cmd_add(args):
    conn = get_db()
    existing = conn.execute("SELECT key FROM sources WHERE key=?", (args.key,)).fetchone()
    if existing:
        print(f"来源 {args.key} 已存在", file=sys.stderr)
        sys.exit(1)
    conn.execute(
        "INSERT INTO sources (key, name, prefix, check_interval, config) VALUES (?, ?, ?, ?, ?)",
        (args.key, args.name, args.prefix, args.interval, args.config),
    )
    safe_commit(conn)
    conn.close()
    print(f"✓ 来源已注册: {args.name} (key={args.key}, prefix={args.prefix}, interval={args.interval}min)")


def cmd_list():
    conn = get_db()
    rows = conn.execute("SELECT * FROM sources ORDER BY created_at").fetchall()
    if not rows:
        print("暂无注册来源")
        conn.close()
        return
    print(f"{'Key':20s} {'名称':16s} {'前缀':4s} {'开关':>4s} {'间隔':>4s} {'推送':>4s} {'反馈':>4s} {'上次检查':>20s}")
    print(f"{'─'*20} {'─'*16} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*4} {'─'*20}")
    for r in rows:
        sw = "✅" if r["enabled"] else "❌"
        print(f"{r['key']:20s} {r['name']:16s} {r['prefix']:4s} {sw:>4s} {r['check_interval']:4d} {r['total_pushed']:4d} {r['total_feedback']:4d} {r['last_check'] or '—':>20s}")
    conn.close()


def cmd_toggle(args):
    conn = get_db()
    row = conn.execute("SELECT enabled FROM sources WHERE key=?", (args.key,)).fetchone()
    if not row:
        print(f"来源 {args.key} 不存在", file=sys.stderr)
        sys.exit(1)
    new_val = 0 if row["enabled"] else 1
    conn.execute("UPDATE sources SET enabled=? WHERE key=?", (new_val, args.key))
    safe_commit(conn)
    conn.close()
    status = "开启" if new_val else "关闭"
    print(f"✓ {args.key} 已{status}")


def cmd_remove(args):
    conn = get_db()
    conn.execute("DELETE FROM sources WHERE key=?", (args.key,))
    safe_commit(conn)
    conn.close()
    print(f"✓ 来源 {args.key} 已删除（已推送的文章记录保留）")


def cmd_info(args):
    conn = get_db()
    row = conn.execute("SELECT * FROM sources WHERE key=?", (args.key,)).fetchone()
    if not row:
        print(f"来源 {args.key} 不存在", file=sys.stderr)
        sys.exit(1)
    r = dict(row)
    print(f"Key:          {r['key']}")
    print(f"名称:         {r['name']}")
    print(f"前缀:         {r['prefix']}")
    print(f"开关:         {'✅ 开启' if r['enabled'] else '❌ 关闭'}")
    print(f"检查间隔:     {r['check_interval']} 分钟")
    print(f"总推送:       {r['total_pushed']}")
    print(f"总反馈:       {r['total_feedback']}")
    print(f"上次检查:     {r['last_check'] or '—'}")
    print(f"创建时间:     {r['created_at']}")
    if r['config']:
        print(f"配置:         {r['config']}")

    # 最近推送
    recent = conn.execute(
        "SELECT title, score, feedback, pushed_at FROM pushed WHERE source=? ORDER BY pushed_at DESC LIMIT 5",
        (args.key,),
    ).fetchall()
    if recent:
        print(f"\n最近推送 ({len(recent)} 条):")
        for p in recent:
            fb = {"✅ 好": 1, "❌ 差": -1}.get(p["feedback"], "")
            print(f"  {p['pushed_at'][:16]}  {fb}  {p['title'][:40]}")
    conn.close()


def main():
    parser = argparse.ArgumentParser(description="InfoSource 来源管理")
    sub = parser.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("add", help="注册新来源")
    a.add_argument("key", help="来源唯一标识（如 linkresearcher）")
    a.add_argument("name", help="显示名称（如 领研网）")
    a.add_argument("prefix", help="UID前缀（如 lr）")
    a.add_argument("--interval", type=int, default=30, help="检查间隔（分钟）")
    a.add_argument("--config", default="{}", help="JSON配置")
    sub.add_parser("list", help="列出所有来源")
    t = sub.add_parser("toggle", help="开关来源")
    t.add_argument("key")
    rm = sub.add_parser("remove", help="删除来源")
    rm.add_argument("key")
    i = sub.add_parser("info", help="查看来源详情")
    i.add_argument("key")
    args = parser.parse_args()

    if args.cmd == "add":
        cmd_add(args)
    elif args.cmd == "list":
        cmd_list()
    elif args.cmd == "toggle":
        cmd_toggle(args)
    elif args.cmd == "remove":
        cmd_remove(args)
    elif args.cmd == "info":
        cmd_info(args)


if __name__ == "__main__":
    main()
