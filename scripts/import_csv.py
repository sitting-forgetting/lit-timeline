#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CSV → data/events.js

用法：
    python3 scripts/import_csv.py 数据源.csv          # 生成 data/events.js
    python3 scripts/import_csv.py 数据源.csv --check  # 只校验，不写文件

CSV 至少需要「日期 / 标题 / 轨道」三列，其余可留空。
支持的列名（中英文均可，见 COLUMN_ALIASES）：
    日期, 标题, 轨道, 类型, 重要度, 人物, 流派, 一句话, 考点, 记忆钩子, 易混, 标签, 时期

分隔符自动识别（逗号 / 制表符），编码自动兼容 UTF-8 BOM 与 GBK。
"""
import argparse
import csv
import io
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PERIODS = [
    {"id": "p1", "name": "第一个十年", "sub": "文学革命 1917—1927", "start": 1917, "end": 1927.5, "color": "#1d4f8c"},
    {"id": "p2", "name": "第二个十年", "sub": "左翼与多元 1927.5—1937.5", "start": 1927.5, "end": 1937.5, "color": "#b5533c"},
    {"id": "p3", "name": "第三个十年", "sub": "抗战与解放区 1937.5—1949", "start": 1937.5, "end": 1949.5, "color": "#8a6d3b"},
    {"id": "p4", "name": "十七年", "sub": "1949—1966", "start": 1949.5, "end": 1966, "color": "#1f8a66"},
    {"id": "p5", "name": "文革十年", "sub": "1966—1976", "start": 1966, "end": 1976, "color": "#7a7f77"},
    {"id": "p6", "name": "新时期", "sub": "1977—1989", "start": 1976, "end": 1989.5, "color": "#8b7bb0"},
    {"id": "p7", "name": "九十年代", "sub": "1990—1999", "start": 1989.5, "end": 1999.5, "color": "#4f7a80"},
    {"id": "p8", "name": "新世纪", "sub": "2000—", "start": 1999.5, "end": 2026, "color": "#c9a227"},
]

LANES = [
    {"id": "sichao", "name": "思潮 · 论争", "color": "#b5533c"},
    {"id": "kanwu", "name": "社团 · 刊物", "color": "#8a6d3b"},
    {"id": "novel", "name": "小说", "color": "#1d4f8c"},
    {"id": "poem", "name": "诗歌", "color": "#1f8a66"},
    {"id": "prose", "name": "散文", "color": "#4f7a80"},
    {"id": "drama", "name": "戏剧", "color": "#8b7bb0"},
    {"id": "event", "name": "事件 · 人物", "color": "#c92820"},
]

# 中文列名 / 别名 → 规范字段
COLUMN_ALIASES = {
    "日期": "date", "时间": "date", "年份": "date", "date": "date",
    "标题": "title", "条目": "title", "名称": "title", "title": "title",
    "轨道": "lane", "栏目": "lane", "分类": "lane", "lane": "lane",
    "类型": "kind", "体裁": "kind", "kind": "kind",
    "重要度": "importance", "重要": "importance", "星级": "importance", "importance": "importance",
    "人物": "people", "作者": "people", "people": "people",
    "流派": "schools", "思潮": "schools", "社团": "schools", "schools": "schools",
    "一句话": "summary", "摘要": "summary", "简介": "summary", "summary": "summary",
    "考点": "detail", "详解": "detail", "说明": "detail", "detail": "detail",
    "记忆钩子": "memory", "口诀": "memory", "记忆": "memory", "memory": "memory",
    "易混": "confuse", "辨析": "confuse", "易混辨析": "confuse", "confuse": "confuse",
    "标签": "tags", "tags": "tags",
    "时期": "period", "阶段": "period", "period": "period",
    "出处": "chapter", "章节": "chapter", "来源": "chapter", "chapter": "chapter",
}

# 轨道中文名 → id
LANE_MAP = {
    "思潮": "sichao", "论争": "sichao", "思潮论争": "sichao", "思潮 · 论争": "sichao", "运动": "sichao",
    "社团": "kanwu", "刊物": "kanwu", "社团刊物": "kanwu", "社团 · 刊物": "kanwu", "期刊": "kanwu",
    "小说": "novel", "小说家": "novel",
    "诗歌": "poem", "诗": "poem", "诗派": "poem",
    "散文": "prose", "散文诗": "prose",
    "戏剧": "drama", "话剧": "drama", "戏曲": "drama",
    "事件": "event", "人物": "event", "事件人物": "event", "事件 · 人物": "event",
}
LANE_IDS = {l["id"] for l in LANES}
PERIOD_NAME_MAP = {p["name"]: p["id"] for p in PERIODS}
PERIOD_NAME_MAP.update({"文学革命": "p1", "左翼": "p2", "抗战": "p3", "十七年": "p4",
                        "文革": "p5", "新时期": "p6", "90年代": "p7", "九十年代": "p7"})

TAG_SPLIT = re.compile(r"[，,、;；/\s]+")


def norm(s):
    return re.sub(r"\s+", "", (s or "")).strip()


LANE_MAP_NORM = {norm(k): v for k, v in LANE_MAP.items()}


def make_period_of(periods):
    """按「年 + 月」的小数年份落位，与 build_from_epub.py 保持一致。
    只用整数年会出错：1937 年 7 月是第三个十年的起点，整数年判不出这半天。"""
    def period_of(year, month=None):
        v = year + ((month or 6) - 0.5) / 12.0
        for p in periods:
            if p["start"] <= v < p["end"]:
                return p["id"]
        return periods[-1]["id"] if v >= periods[-1]["start"] else periods[0]["id"]
    return period_of


def year_of(date_str):
    m = re.match(r"^\s*(\d{4})", str(date_str))
    return int(m.group(1)) if m else None


def month_of(date_str):
    m = re.match(r"^\s*\d{4}-(\d{1,2})", str(date_str))
    return int(m.group(1)) if m else None


def split_list(s):
    s = (s or "").strip()
    if not s:
        return []
    return [x.strip() for x in re.split(r"[、,，;；/\s]+", s) if x.strip()]


def normalize_date(raw):
    """1917 / 1917-3 / 1917.3 / 1917年3月 / 1917-03-15 → 规范字符串"""
    s = str(raw or "").strip()
    if not s:
        return None
    s = s.replace("年", "-").replace("月", "-").replace("日", "").replace("/", "-").replace(".", "-")
    s = re.sub(r"-+$", "", s)
    parts = [p for p in s.split("-") if p != ""]
    if not parts or not re.match(r"^\d{4}$", parts[0]):
        return None
    out = parts[0]
    if len(parts) > 1 and parts[1].isdigit():
        out += "-%02d" % int(parts[1])
        if len(parts) > 2 and parts[2].isdigit():
            out += "-%02d" % int(parts[2])
    return out


def read_rows(path):
    raw = open(path, "rb").read()
    for enc in ("utf-8-sig", "utf-8", "gb18030"):
        try:
            text = raw.decode(enc)
            break
        except UnicodeDecodeError:
            continue
    else:
        sys.exit("无法识别文件编码，请另存为 UTF-8")
    first = text.splitlines()[0] if text.splitlines() else ""
    delim = "\t" if first.count("\t") > first.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delim)
    return list(reader)


def load_existing(out_path):
    """读现有 data/events.js，继承它的 periods / lanes / meta。
    这样用 CSV 往返不会把时期划分、轨道和出处字段冲掉。"""
    if not os.path.exists(out_path):
        return None
    try:
        raw = open(out_path, encoding="utf-8").read()
        i = raw.index("window.LIT_DATA")
        body = raw[raw.index("{", i):raw.rindex("}") + 1]
        return json.loads(body)
    except Exception as e:
        print("  ! 现有数据读不出来，用内置默认（%s）" % e)
        return None


def build(path, existing=None):
    rows = read_rows(path)
    if not rows:
        sys.exit("CSV 是空的")
    # 结构以现有数据为准，没有则用内置默认
    periods = (existing or {}).get("periods") or PERIODS
    lanes = (existing or {}).get("lanes") or LANES
    lane_ids = {l["id"] for l in lanes}
    period_ids = {p["id"] for p in periods}
    period_name_map = {p["name"]: p["id"] for p in periods}
    period_of = make_period_of(periods)
    events, problems = [], []
    fieldnames = [f for f in rows[0].keys() if f]

    def key_of(row, canonical):
        for k in fieldnames:
            if COLUMN_ALIASES.get(norm(k)) == canonical:
                if row.get(k):
                    return str(row.get(k)).strip()
        return ""

    for i, row in enumerate(rows, start=2):
        title = key_of(row, "title")
        if not title:
            if any((v or "").strip() for v in row.values()):
                problems.append("第 %d 行：缺标题，已跳过" % i)
            continue
        date = normalize_date(key_of(row, "date"))
        if not date:
            problems.append("第 %d 行《%s》：日期无法解析（%r），已跳过" % (i, title, key_of(row, "date")))
            continue
        year = year_of(date)
        month = month_of(date)

        lane_raw = norm(key_of(row, "lane"))
        lane = LANE_MAP_NORM.get(lane_raw)
        if not lane:
            if lane_raw in lane_ids:
                lane = lane_raw
            else:
                lane = lanes[0]["id"]
                problems.append("第 %d 行《%s》：轨道「%s」无法识别，归入「%s」"
                                % (i, title, lane_raw or "(空)", lanes[0]["name"]))

        try:
            imp = int(float(key_of(row, "importance") or 2))
        except ValueError:
            imp = 2
        imp = min(3, max(1, imp))

        p_raw = norm(key_of(row, "period"))
        period = period_name_map.get(p_raw) or (p_raw if p_raw in period_ids else period_of(year, month))

        ev = {
            "date": date,
            "title": title,
            "lane": lane,
            "period": period,
            "kind": key_of(row, "kind") or "",
            "importance": imp,
            "people": split_list(key_of(row, "people")),
            "schools": split_list(key_of(row, "schools")),
            "summary": key_of(row, "summary"),
            "detail": key_of(row, "detail"),
            "memory": key_of(row, "memory"),
            "confuse": key_of(row, "confuse"),
            "tags": [t for t in TAG_SPLIT.split(key_of(row, "tags")) if t],
        }
        chapter = key_of(row, "chapter")
        if chapter:
            ev["chapter"] = chapter
        ev["id"] = "e%s-%02d" % (date.replace("-", ""), i)
        events.append(ev)

    events.sort(key=lambda e: (e["date"], -e["importance"], e["title"]))
    years = [year_of(e["date"]) for e in events]
    meta = dict((existing or {}).get("meta") or {})
    meta.update({
        "title": meta.get("title") or "中国现当代文学时间轴",
        "updated": __import__("datetime").date.today().isoformat(),
        "minYear": min(years) - 1,
        "maxYear": max(max(years) + 1, 2026),
    })
    data = {"meta": meta, "periods": periods, "lanes": lanes, "events": events}
    return data, problems


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("csv", help="CSV 文件路径")
    ap.add_argument("--check", action="store_true", help="只校验，不写文件")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "data", "events.js"))
    args = ap.parse_args()

    existing = load_existing(args.out)
    data, problems = build(args.csv, existing)
    if not data["events"]:
        sys.exit("没有可用条目，请检查 CSV 表头是否为：日期,标题,轨道")

    for p in problems[:40]:
        print("  ! " + p)
    if len(problems) > 40:
        print("  …… 另有 %d 条提示" % (len(problems) - 40))

    lanes_used = {}
    for e in data["events"]:
        lanes_used[e["lane"]] = lanes_used.get(e["lane"], 0) + 1
    print("条目 %d 条，时间跨度 %s—%s" % (len(data["events"]), data["meta"]["minYear"], data["meta"]["maxYear"]))
    print("轨道分布：" + "，".join("%s %d" % (l["name"], lanes_used.get(l["id"], 0)) for l in data["lanes"]))
    if args.check:
        print("（--check：未写入）")
        return

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    body = json.dumps(data, ensure_ascii=False, indent=1)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("/* 由 scripts/import_csv.py 从 %s 生成，勿手改；改数据请改 CSV 后重新运行 */\n" % os.path.basename(args.csv))
        f.write("window.LIT_DATA = " + body + ";\n")
    print("已写入 " + args.out)


if __name__ == "__main__":
    main()
