#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从洪子诚《中国当代文学史》EPUB 抽取时间轴数据，合并进 data/events.js

这本书与钱理群那本不同：
  · 年表不在每章末，而是全书末尾一个统一的「中国当代文学年表（1949—2000）」
  · 年表条目更长，且大量出现「同月」「本年」承前
  · 有大量「某报某刊发表某文」的记录，刊物名常被误当成条目 → 需要专门识别

用法：
    python3 scripts/build_contemporary.py 当代文学史.epub [--merge data/events.js]

不加 --merge 时只导出到 data/events_contemporary.js 供检查。
"""
import argparse
import html
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

# 报纸/大刊：只是发表载体，不该成为条目
CARRIERS = {"人民日报", "文艺报", "文汇报", "光明日报", "解放日报", "大公报", "解放军文艺",
            "人民文学", "诗刊", "文艺学习", "文艺月报", "长江文艺", "文艺阵地", "新华日报",
            "中国青年", "收获", "十月", "当代", "花城", "钟山", "人民戏剧", "剧本", "说说唱唱",
            "北京文艺", "上海文学", "鸭绿江", "延河", "雨花", "星火", "文艺研究", "文学评论",
            "新观察", "世界文学", "译文", "萌芽", "江南", "黄河", "中国作家", "作家"}

TYPE_WORDS = [
    ("长篇小说", r"长篇小说|长篇"), ("中篇小说", r"中篇小说|中篇"),
    ("短篇小说集", r"短篇小说集|短篇集"), ("短篇小说", r"短篇小说"),
    ("小说集", r"小说集"), ("叙事诗", r"叙事诗"), ("散文诗", r"散文诗"),
    ("诗集", r"诗集|长诗|诗选"), ("散文集", r"散文集"), ("杂文集", r"杂文集|杂文"),
    ("话剧", r"话剧|剧本|歌剧|戏剧"), ("论文", r"论文|评论"),
    ("报告文学", r"报告文学"), ("散文", r"散文"),
]
TYPE_LANE = {"长篇小说": "novel", "中篇小说": "novel", "短篇小说": "novel",
             "短篇小说集": "novel", "小说集": "novel", "诗集": "poem", "叙事诗": "poem",
             "散文集": "prose", "杂文集": "prose", "散文": "prose", "散文诗": "prose",
             "报告文学": "prose", "话剧": "drama", "论文": "sichao"}

KNOWN = {
    "创业史": ("novel", "长篇小说"), "红岩": ("novel", "长篇小说"),
    "青春之歌": ("novel", "长篇小说"), "红旗谱": ("novel", "长篇小说"),
    "林海雪原": ("novel", "长篇小说"), "三家巷": ("novel", "长篇小说"),
    "山乡巨变": ("novel", "长篇小说"), "保卫延安": ("novel", "长篇小说"),
    "苦菜花": ("novel", "长篇小说"), "风云初记": ("novel", "长篇小说"),
    "三里湾": ("novel", "长篇小说"), "登记": ("novel", "短篇小说"),
    "锻炼锻炼": ("novel", "短篇小说"), "百合花": ("novel", "短篇小说"),
    "组织部新来的青年人": ("novel", "短篇小说"), "我们夫妇之间": ("novel", "短篇小说"),
    "李双双小传": ("novel", "短篇小说"), "白鹿原": ("novel", "长篇小说"),
    "废都": ("novel", "长篇小说"), "活着": ("novel", "长篇小说"),
    "许三观卖血记": ("novel", "长篇小说"), "长恨歌": ("novel", "长篇小说"),
    "平凡的世界": ("novel", "长篇小说"), "古船": ("novel", "长篇小说"),
    "活动变人形": ("novel", "长篇小说"), "洗澡": ("novel", "长篇小说"),
    "棋王": ("novel", "中篇小说"), "爸爸爸": ("novel", "中篇小说"),
    "红高粱": ("novel", "中篇小说"), "冈底斯的诱惑": ("novel", "中篇小说"),
    "烦恼人生": ("novel", "中篇小说"), "风景": ("novel", "中篇小说"),
    "你别无选择": ("novel", "中篇小说"), "人到中年": ("novel", "中篇小说"),
    "蝴蝶": ("novel", "中篇小说"),
    "茶馆": ("drama", "话剧"), "龙须沟": ("drama", "话剧"), "关汉卿": ("drama", "话剧"),
    "蔡文姬": ("drama", "话剧"), "霓虹灯下的哨兵": ("drama", "话剧"),
    "于无声处": ("drama", "话剧"), "桑树坪纪事": ("drama", "话剧"),
    "狗儿爷涅槃": ("drama", "话剧"),
    "谁是最可爱的人": ("prose", "报告文学"), "干校六记": ("prose", "散文集"),
    "随想录": ("prose", "散文集"), "文化苦旅": ("prose", "散文集"),
    "我与地坛": ("prose", "散文"), "哥德巴赫猜想": ("prose", "报告文学"),
    "回答": ("poem", "诗集"), "致橡树": ("poem", "诗集"), "草木篇": ("poem", "诗集"),
    "白雪的赞歌": ("poem", "叙事诗"), "团泊洼的秋天": ("poem", "诗集"),
    "时间开始了": ("poem", "长诗"), "杨高传": ("poem", "叙事诗"),
    "复仇的火焰": ("poem", "叙事诗"), "将军三部曲": ("poem", "叙事诗"),
    "阿诗玛": ("poem", "叙事诗"), "百鸟衣": ("poem", "叙事诗"),
    "野百合花": ("prose", "杂文"), "电影的锣鼓": ("sichao", "论文"),
    "现实主义——广阔的道路": ("sichao", "论文"),
    "论“文学是人学”": ("sichao", "论文"),
}


def _paras(raw):
    raw = re.sub(r"<span[^>]*></span>", "", raw)
    raw = re.sub(r"<img[^>]*>", "", raw)
    out = []
    for part in re.split(r"</p>", raw):
        t = re.sub(r"<[^>]+>", "", part)
        t = html.unescape(t).replace("\u3000", " ").strip()
        if t:
            out.append(t)
    return out


def load_chronology(epub):
    z = zipfile.ZipFile(epub)
    best = None
    for n in sorted(x for x in z.namelist() if x.endswith(".html")):
        ps = _paras(z.read(n).decode("utf-8", "ignore"))
        idx = next((i for i, t in enumerate(ps) if "中国当代文学年表" in t and len(t) < 60), None)
        if idx is not None and len(ps) > 200:
            best = ps[idx + 1:]
            break
    if not best:
        sys.exit("没找到「中国当代文学年表」章节")
    return best


YEAR = re.compile(r"^(\d{4})年$")
YEAR_INLINE = re.compile(r"^(\d{4})年(\d{1,2})月\s*(?:(\d{1,2})日)?\s*(.+)$")
MDR2 = re.compile(r"^(\d{1,2})[—\-－至](\d{1,2})月(\d{1,2})日\s+(.+)$")
MDR = re.compile(r"^(\d{1,2})月(\d{1,2})日\s+(.+)$")
MR = re.compile(r"^(\d{1,2})[—\-－至](\d{1,2})月\s+(.+)$")
M = re.compile(r"^(\d{1,2})月\s+(.+)$")
SAME_MD = re.compile(r"^同月(\d{1,2})日\s*(.+)$")
SAME_M = re.compile(r"^同月\s*(?:(\d{1,2})日)?\s*(.+)$")
SAME_Y = re.compile(r"^(同年|本年|年底|年初|上半年|下半年|本月|是年)\s*(.+)$")


def parse_rows(body):
    rows, y, mo, d = [], None, None, None
    for t in body:
        t = t.strip()
        if not t:
            continue
        m = YEAR.match(t)
        if m:
            y, mo, d = int(m.group(1)), None, None
            continue
        m = YEAR_INLINE.match(t)
        if m:
            y, mo = int(m.group(1)), int(m.group(2))
            d = int(m.group(3)) if m.group(3) else None
            rows.append({"y": y, "m": mo, "d": d, "text": m.group(4)})
            continue
        for rx, gm, gd, gt in [(MDR2, 1, None, 4), (MDR, 1, 2, 3), (MR, 1, None, 3),
                               (SAME_MD, None, 1, 2), (SAME_M, None, 1, 2), (SAME_Y, None, None, 2),
                               (M, 1, None, 2)]:
            m = rx.match(t)
            if not m:
                continue
            if gm is not None and m.group(gm):
                mo = int(m.group(gm))
            if gd is not None and m.group(gd):
                d = int(m.group(gd))
            rows.append({"y": y, "m": mo, "d": d, "text": m.group(gt)})
            break
        else:
            rows.append({"y": y, "m": mo, "d": d, "text": t})
    return [r for r in rows if r["y"]]


def match_type(s):
    for name, pat in TYPE_WORDS:
        if re.search(pat, s):
            return name
    return ""


def first_book(text):
    m = re.search(r"《([^》]{1,26})》", text)
    return m.group(1) if m else ""


def carrier_only(text):
    m = re.search(r"《([^》]{1,26})》", text)
    return bool(m) and m.group(1) in CARRIERS


def carrier_event_title(t):
    md = re.search(r"评[^《〈]{0,8}[《〈]([^》〉]{2,18})[》〉]", t)
    if md:
        return "评《%s》" % md.group(1)
    if re.search(r"参考书目|书目", t):
        return "文艺工作者学习书目"
    md = re.search(r"关于[《〈]?([^》〉，。]{2,20})[》〉]?[^。]{0,6}?(?:讨论|批判|论争)", t)
    if md:
        return md.group(1)[:24] + "讨论"
    md = re.search(r"展开(?:了)?(?:有关|关于)?([^。]{2,22}?)的(?:讨论|批判|论争)", t)
    if md:
        return md.group(1)[:24]
    md = re.search(r"开始(?:了)?(?:全国范围的)?对([^。]{2,22}?)的(?:批判|讨论)", t)
    if md:
        return "批判" + md.group(1)[:20]
    md = re.search(r"讨论[^《]{0,10}[《〈]([^》〉]{2,18})[》〉]", t)
    if md:
        return "《%s》讨论" % md.group(1)
    md = re.search(r"批评[^《]{0,10}[《〈]([^》〉]{2,18})[》〉]", t)
    if md:
        return "《%s》批评" % md.group(1)
    md = re.search(r"([\u4e00-\u9fa5]{2,10}问题)的(?:讨论|论争)", t)
    if md:
        return md.group(1) + "讨论"
    md = re.search(r"有关([\u4e00-\u9fa5]{2,10})的(?:讨论|论争)", t)
    if md:
        return md.group(1) + "讨论"
    md = re.search(r"以[“「]([^”」]{2,24})[”」]为题", t)
    if md:
        return md.group(1)[:24]
    md = re.search(r"[“「]([^”」]{2,24})[”」][^。]{0,14}?(?:讨论|批判|论争|座谈)", t)
    if md:
        return md.group(1)[:24]
    md = re.search(r"关于([^。]{2,20}?)的(?:讨论|批判|论争|座谈)", t)
    if md:
        return md.group(1)[:24]
    md = re.search(r"(?:批判|批评|讨论)(?:电影)?[《〈]([^》〉]{2,18})[》〉]", t)
    if md:
        return "批判《%s》" % md.group(1)
    md = re.search(r"[《〈]([^》〉]{2,18})[》〉][^。]{0,10}?(?:的批判|的讨论)", t)
    if md:
        return "《%s》批判" % md.group(1)
    md = re.search(r"刊(?:载|登)[^《]{0,10}[《〈]([^》〉]{2,20})[》〉]", t)
    if md:
        return "《%s》" % md.group(1)
    md = re.search(r"发表[^《]{0,8}[《〈]([^》〉]{2,20})[》〉]", t)
    if md:
        return "《%s》" % md.group(1)
    return re.split(r"[，。；]", t)[0][:22]


def title_of(text, lane, typ):
    t = text.strip().rstrip("。")
    m = re.search(r"《([^》]{1,26})》(创刊|复刊|改刊|停刊|终刊)", t)
    if m:
        return "《%s》%s" % (m.group(1), m.group(2))
    mc = re.match(r"^.{0,30}?《([^》]{1,24})》[^。，]{0,12}?(创刊|复刊|改刊|停刊)", t)
    if mc and re.search(r"创刊|复刊", t):
        return "《%s》%s" % (mc.group(1), mc.group(2))
    if carrier_only(t) and not re.search(r"创刊|复刊", t):
        return carrier_event_title(t)
    if lane == "kanwu":
        m = re.match(r"^(.{2,26}?)(成立|组建)", t)
        if m:
            name = re.split(r"[，。]", m.group(1))[-1].strip()
            if 2 <= len(name) <= 20:
                return name + "成立"
        m = re.search(r"《([^》]{1,24})》", t)
        if m:
            return "《%s》" % m.group(1)
    if lane == "sichao":
        m = re.search(r"(第[一二三四五六七八九十]+次[\u4e00-\u9fa5]{2,12}(?:文代会|作代会|代表大会))", t)
        if m:
            return m.group(1)
        m = re.search(r"([\u4e00-\u9fa5“”、]{4,30}?(?:代表大会|文代会|座谈会|讨论会|会议|联席会|报告会))", t)
        if m:
            name = re.sub(r"^(全国|中国|中共中央|在|由|召开|举行)", "", m.group(1))
            if len(name) >= 4:
                return name[:24]
        m = re.search(r"“([^”]{2,20})”的?(?:讨论|批判|论争|论战)", t)
        if m:
            return "“%s”讨论" % m.group(1)
        m = re.search(r"(?:批判|批评|讨论)(《[^》]{1,20}》)", t)
        if m:
            return m.group(1)
        m = re.search(r"《([^》]{2,24})》", t)
        if m:
            return "《%s》" % m.group(1)
    m = re.search(r"([\u4e00-\u9fa5]{2,30}?(?:会议|座谈会|讨论会|代表大会|联席会|工作会))", t)
    if m:
        name = re.sub(r"^(在|于|由|召开)", "", m.group(1))
        if len(name) >= 5:
            return name[:26]
    for m in re.finditer(r"《([^》]{1,26})》", t):
        if m.group(1) not in CARRIERS:
            return "《%s》" % m.group(1)
    m = re.search(r"《([^》]{1,26})》", t)
    if m:
        return "《%s》" % m.group(1)
    return re.split(r"[，。；]", t)[0][:24]


def is_noise(text, lane, typ):
    t = text.strip()
    if typ:
        return False
    if re.search(r"《[^》]+》", t) and re.search(r"发表|出版|创刊|连载|刊于|载于", t):
        return False
    if re.search(r"逝世|去世|病逝|自尽|自杀", t) and not re.search(r"发表|出版|创作|完成", t):
        return True
    if re.search(r"推选.{0,12}为.{0,8}委员|任主任|任副主任|秘书长|当选为|选举", t) and "《" not in t:
        return True
    return len(t) < 10


def lane_of(text, typ):
    if re.search(r"创刊|复刊|改刊|停刊|终刊", text):
        return "kanwu"
    if carrier_only(text) and re.search(r"讨论|批判|论争|座谈|刊载|发表|转载", text):
        return "sichao"
    if re.search(r"(成立|组建|发起|召开成立)", text) and not re.search(r"发表|出版|作《", text):
        return "kanwu"
    if re.search(r"批判|讨论|论争|论战|座谈|会议|大会|报告会|座谈会|决议|方针|政策", text) and not typ:
        return "sichao"
    if typ and typ in TYPE_LANE:
        return TYPE_LANE[typ]
    if re.search(r"《[^》]+》", text) and re.search(r"发表|出版|连载|刊于", text):
        if re.search(r"诗", text):
            return "poem"
        if re.search(r"剧", text):
            return "drama"
        if re.search(r"散文|杂文|报告文学", text):
            return "prose"
        return "novel"
    return "sichao"


PERIODS = [
    {"id": "p0", "name": "前史", "sub": "1898—1917 新文学的酝酿", "start": 1898, "end": 1917, "color": "#7a7f77"},
    {"id": "p1", "name": "第一个十年", "sub": "1917—1927 文学革命", "start": 1917, "end": 1928, "color": "#1d4f8c"},
    {"id": "p2", "name": "第二个十年", "sub": "1928—1937.6 左翼与多元", "start": 1928, "end": 1937.5, "color": "#b5533c"},
    {"id": "p3", "name": "第三个十年", "sub": "1937.7—1949 抗战与解放区", "start": 1937.5, "end": 1949.5, "color": "#8a6d3b"},
    {"id": "p4", "name": "十七年", "sub": "1949.5—1966 一体化与规范", "start": 1949.5, "end": 1966, "color": "#1f8a66"},
    {"id": "p5", "name": "文革十年", "sub": "1966—1976 分裂的文学世界", "start": 1966, "end": 1976.5, "color": "#7a7f77"},
    {"id": "p6", "name": "新时期", "sub": "1976.10—1989 归来与寻根", "start": 1976.5, "end": 1989.5, "color": "#8b7bb0"},
    {"id": "p7", "name": "九十年代", "sub": "1989.5—2000 分化与长篇小说", "start": 1989.5, "end": 2000.5, "color": "#4f7a80"},
    {"id": "p8", "name": "新世纪", "sub": "2000—", "start": 2000.5, "end": 2026, "color": "#c9a227"},
]


def period_of(date):
    p = date.split("-")
    y = int(p[0])
    m = int(p[1]) if len(p) > 1 else 6
    v = y + (m - 0.5) / 12.0
    for per in PERIODS:
        if per["start"] <= v < per["end"]:
            return per["id"]
    return PERIODS[-1]["id"] if v >= PERIODS[-1]["start"] else PERIODS[0]["id"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--merge", help="合并进现有 data/events.js")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "data", "events_contemporary.js"))
    args = ap.parse_args()

    rows = parse_rows(load_chronology(args.epub))
    out, seen = [], set()
    for r in rows:
        text = r["text"].strip()
        text = re.sub(r"^(同月|同年|本年|是年|年底|年初)\s*", "", text)
        text = re.sub(r"^\d{1,2}月(初|底|中)?\s*", "", text)
        text = re.sub(r"^\d{1,2}日[至—\-]\d{1,2}日\s*", "", text)
        text = re.sub(r"^\d{1,2}日\s*", "", text)
        if not text:
            continue
        name = first_book(text)
        if name in KNOWN:
            lane, typ = KNOWN[name]
        else:
            typ = match_type(text)
            lane = lane_of(text, typ)
        if is_noise(text, lane, typ):
            continue
        title = title_of(text, lane, typ)
        title = re.sub(r"^[\u4e00-\u9fa5]{2,4}在(?=[\u4e00-\u9fa5]{2,})", "", title)
        title = re.sub(r"^(\d+次|次|一次|等)", "", title)
        title = title.strip()
        if not title or len(title) < 2 or len(title) > 26:
            continue
        if (title, r["y"]) in seen:
            continue
        seen.add((title, r["y"]))
        date = "%d" % r["y"]
        if r["m"]:
            date += "-%02d" % r["m"]
            if r["d"]:
                date += "-%02d" % r["d"]
        out.append({
            "date": date, "title": title, "lane": lane, "period": period_of(date),
            "kind": typ, "importance": 1, "people": [], "schools": [],
            "summary": re.sub(r"\s+", "", text)[:120],
            "detail": "", "memory": "", "confuse": "", "tags": [],
            "chapter": "中国当代文学年表（1949—2000）",
            "src": "洪子诚《中国当代文学史》",
        })

    from collections import Counter
    print("当代条目 %d 条" % len(out))
    print("轨道：" + str(dict(Counter(e["lane"] for e in out))))
    print("时期：" + str(dict(Counter(e["period"] for e in out))))

    if not args.merge:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write("window.LIT_CONTEMP = " + json.dumps(out, ensure_ascii=False, indent=1) + ";\n")
        print("已写入 " + args.out)
        return

    src = open(args.merge, encoding="utf-8").read()
    D = json.loads(src[src.index("{"):src.rindex("}") + 1])
    # 只保留非当代来源的条目，避免重复合并
    base = [e for e in D["events"] if not str(e.get("src", "")).startswith("洪子诚")]
    for e in base:
        e["period"] = period_of(e["date"])
        e.setdefault("src", "钱理群等《中国现代文学三十年》")
    merged, seen2 = [], set()
    for e in base + out:
        k = (e["date"][:4], e["title"].strip("《》“”"))
        if k in seen2:
            continue
        seen2.add(k)
        merged.append(e)
    merged.sort(key=lambda e: (e["date"], -e["importance"], e["title"]))
    for i, e in enumerate(merged):
        e["id"] = "T%05d" % i
    D["events"] = merged
    D["periods"] = PERIODS
    D["meta"]["source"] = "钱理群等《中国现代文学三十年》+ 洪子诚《中国当代文学史》"
    with open(args.merge, "w", encoding="utf-8") as f:
        f.write("window.LIT_DATA = " + json.dumps(D, ensure_ascii=False, indent=1) + ";\n")
    print("合并后 %d 条，已写入 %s" % (len(merged), args.merge))


if __name__ == "__main__":
    main()
