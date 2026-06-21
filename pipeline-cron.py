#!/usr/bin/env python3
"""
InfoSource Pipeline Cron Wrapper
cron 调用的入口脚本 — 静默模式，只在有推送时才输出。
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from pipeline import run_pipeline

result = run_pipeline(score_threshold=0.5, dry_run=False, max_pushes=20)

pushed = result.get("pushed", 0)
new = result.get("new_fetched", 0)

if pushed > 0:
    print(f"\n📊 本轮推送 {pushed} 篇（新抓取 {new} 篇）")
elif new > 0:
    # 有新文章但都不达标，静默
    pass
else:
    # 啥也没有，静默
    pass

# 如果推送失败或有错误，输出让 cron 通知
if result.get("failed", 0) > 0:
    print(f"\n⚠️ {result['failed']} 篇推送失败")
if result.get("error"):
    print(f"\n❌ Pipeline 错误: {result['error']}")
