#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
从《中国现代文学三十年》（修订本）EPUB 抽取时间轴数据 → data/events.js

原理：本书每一章末尾都有「本章年表」，格式规整（年份行 + 月日行 + 事件文本），
天然是结构化的时间点。本脚本解析这 29 个年表，并：
  · 按文本特征判定轨道（思潮/社团刊物/小说/诗歌/散文/戏剧）
  · 用全书正文词频给条目打重要度（1/2/3）
  · 回到正文找讲这条的段落，作为「考点」
  · 记录条目出自哪一章，作为「出处」

用法：
    python3 scripts/build_from_epub.py 书.epub
    python3 scripts/build_from_epub.py 书.epub --csv 数据源.csv   # 同时导出可编辑 CSV

注意：抽取是启发式的，结果需要人工过一遍。改数据请改 CSV 后跑 import_csv.py。
"""
import argparse
import csv
import html
import json
import os
import re
import sys
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)

PERIODS = [
    {"id": "p0", "name": "前史", "sub": "1898—1917 新文学的酝酿", "start": 1898, "end": 1917, "color": "#7a7f77"},
    {"id": "p1", "name": "第一个十年", "sub": "1917—1927 文学革命", "start": 1917, "end": 1928, "color": "#1d4f8c"},
    {"id": "p2", "name": "第二个十年", "sub": "1928—1937.6 左翼与多元", "start": 1928, "end": 1937.5, "color": "#b5533c"},
    {"id": "p3", "name": "第三个十年", "sub": "1937.7—1949 抗战与解放区", "start": 1937.5, "end": 1949.5, "color": "#8a6d3b"},
    {"id": "p4", "name": "延伸", "sub": "1949— 当代（本书之外）", "start": 1949.5, "end": 2000, "color": "#1f8a66"},
]
LANES = [
    {"id": "sichao", "name": "思潮 · 论争", "color": "#b5533c"},
    {"id": "kanwu", "name": "社团 · 刊物", "color": "#8a6d3b"},
    {"id": "novel", "name": "小说", "color": "#1d4f8c"},
    {"id": "poem", "name": "诗歌", "color": "#1f8a66"},
    {"id": "prose", "name": "散文", "color": "#4f7a80"},
    {"id": "drama", "name": "戏剧", "color": "#8b7bb0"},
]
LANE_CN = {"sichao": "思潮 · 论争", "kanwu": "社团 · 刊物", "novel": "小说",
           "poem": "诗歌", "prose": "散文", "drama": "戏剧"}

# ---------- EPUB 解析 ----------
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


def load_blocks(epub):
    z = zipfile.ZipFile(epub)
    files = sorted(x for x in z.namelist() if x.endswith(".html"))
    H1 = re.compile(r"^第[一二三]编")
    H2 = re.compile(r"^第[一二三四五六七八九十]+章")
    H3 = re.compile(r"^([一二三四五六七八九十]+)\s*\S")
    ctx = {"bian": "", "zhang": "", "sec": "（前页）"}
    blocks, cur = [], []
    for n in files:
        for t in _paras(z.read(n).decode("utf-8", "ignore")):
            if H1.match(t) and len(t) < 40:
                if cur:
                    blocks.append(dict(ctx, text=cur))
                cur = []
                ctx["bian"], ctx["zhang"], ctx["sec"] = t, "", ""
            elif H2.match(t) and len(t) < 40:
                if cur:
                    blocks.append(dict(ctx, text=cur))
                cur = []
                ctx["zhang"], ctx["sec"] = t, ""
            elif (H3.match(t) or t.startswith("附录")) and len(t) < 40:
                if cur:
                    blocks.append(dict(ctx, text=cur))
                cur = []
                ctx["sec"] = t
            else:
                cur.append(t)
    if cur:
        blocks.append(dict(ctx, text=cur))
    return blocks


# ---------- 年表行解析 ----------
YEAR = re.compile(r"^(\d{4})年$")
YEAR_INLINE = re.compile(r"^(\d{4})年\s+(.+)$")
MD = re.compile(r"^(\d{1,2})月(\d{1,2})日\s+(.+)$")
MDR = re.compile(r"^(\d{1,2})月(\d{1,2})[—\-－至](\d{1,2})日\s+(.+)$")
MR = re.compile(r"^(\d{1,2})[—\-－至](\d{1,2})月\s+(.+)$")
M = re.compile(r"^(\d{1,2})月\s+(.+)$")
SAME_MD = re.compile(r"^同月(\d{1,2})日\s*(.+)$")
SAME_M = re.compile(r"^同月\s*(?:(\d{1,2})日)?\s*(.+)$")
SAME_Y = re.compile(r"^(同年|本年|是年|年底|年初|上半年|下半年|本月)\s*(.+)$")
SEASON = re.compile(r"^(春|夏|秋|冬|初春|初秋|深秋)\s+(.+)$")


def parse_nian(texts):
    rows = []
    year = month = day = None
    for t in texts:
        t = t.strip()
        if not t:
            continue
        m = YEAR.match(t)
        if m:
            year, month, day = int(m.group(1)), None, None
            continue
        m = YEAR_INLINE.match(t)
        if m:
            year, month, day = int(m.group(1)), None, None
            rows.append({"y": year, "m": None, "d": None, "text": m.group(2)})
            continue
        for rx, g_m, g_d, g_t in [
            (MDR, 1, 2, 4), (MD, 1, 2, 3), (MR, 1, None, 3),
            (SAME_MD, None, 1, 2), (SAME_M, None, 1, 2), (SAME_Y, None, None, 2),
            (SEASON, None, None, 2), (M, 1, None, 2),
        ]:
            m = rx.match(t)
            if not m:
                continue
            if g_m is not None and m.group(g_m):
                month = int(m.group(g_m))
            if g_d is not None and m.group(g_d):
                day = int(m.group(g_d))
            rows.append({"y": year, "m": month, "d": day, "text": m.group(g_t)})
            break
        else:
            rows.append({"y": year, "m": month, "d": day, "text": t})
    return [r for r in rows if r["y"]]


# ---------- 类型 / 轨道 ----------
TYPED = re.compile(r"《([^》〈〉]{1,30})》\s*[（(]([^）)]{2,16})[）)]")
TYPE_WORDS = [
    ("长篇小说", r"长篇小说|长篇"), ("中篇小说", r"中篇小说|中篇"),
    ("短篇小说集", r"短篇小说集|短篇集"), ("短篇小说", r"短篇小说"),
    ("小说集", r"小说集|小说戏剧集|小说散文集"),
    ("叙事诗", r"叙事诗"), ("散文诗", r"散文诗集|散文诗"),
    ("诗集", r"诗集|诗歌集|诗歌戏曲散文集|诗合集"),
    ("散文集", r"散文集"), ("杂文集", r"杂文集|杂文"),
    ("话剧", r"话剧|剧本|歌剧|戏剧|独幕剧|多幕剧|剧曲"),
    ("论文", r"论文|评论|文论"),
    ("报告文学", r"报告文学|回忆录|游记"),
    ("散文", r"散文|随笔|小品"),
]
TYPE_LANE = {"长篇小说": "novel", "中篇小说": "novel", "短篇小说": "novel",
             "短篇小说集": "novel", "小说集": "novel", "诗集": "poem", "叙事诗": "poem",
             "散文集": "prose", "杂文集": "prose", "散文": "prose", "散文诗": "prose",
             "报告文学": "prose", "话剧": "drama", "论文": "sichao"}


def match_type(s):
    for name, pat in TYPE_WORDS:
        if re.search(pat, s):
            return name
    return ""


def build_type_dict(main_text, rows):
    typed = {}
    for m in TYPED.finditer(main_text):
        t = match_type(m.group(2))
        if t:
            typed.setdefault(m.group(1), t)
    for r in rows:
        for m in TYPED.finditer(r["text"]):
            t = match_type(m.group(2))
            if t:
                typed.setdefault(m.group(1), t)
    return typed


def infer_type(name, typed, main_text, local_text=""):
    """体裁判定：优先本行自带的括号标注，其次全书标注字典，最后才看正文最近邻。"""
    if local_text:
        for m in TYPED.finditer(local_text):
            if m.group(1) == name:
                t = match_type(m.group(2))
                if t:
                    return t
    if name in typed:
        return typed[name]
    for m in re.finditer(re.escape("《" + name + "》"), main_text):
        t = match_type(main_text[max(0, m.start() - 30):m.start()] + "|" + main_text[m.end():m.end() + 45])
        if t:
            return t
    return ""


JOURNAL_NAMES = {"新青年", "新潮", "每周评论", "小说月报", "创造", "创造月刊", "语丝", "现代评论", "新月",
                 "北斗", "文学", "文学季刊", "作家", "抗战文艺", "文艺阵地", "七月", "希望", "诗创作",
                 "解放日报", "新华日报", "晨报", "晨报副刊", "京报副刊", "学灯", "觉悟", "少年中国",
                 "戏剧", "南国", "莽原", "未名", "沉钟", "浅草", "弥洒", "现代", "论语", "人间世",
                 "宇宙风", "太白", "文季月刊", "光明", "中流", "译文", "抗战戏剧", "戏剧春秋", "野草",
                 "文艺生活", "文哨", "文艺报", "人民文学", "中国新诗", "诗", "歌谣", "国故", "甲寅",
                 "学衡", "努力周报", "改造"}


def lane_of(text, zhang, typ):
    if re.search(r"(创刊|复刊|改刊|停刊|终刊|独立印行|更名)", text):
        return "kanwu"
    if re.search(r"(成立|组建|发起组织|发起成立|组织成立|结社|组成)", text) and not re.search(r"发表|出版|作《", text):
        return "kanwu"
    if re.search(r"论争|论战|争论|大讨论|论辩", text) and not typ:
        return "sichao"
    if typ and typ in TYPE_LANE:
        return TYPE_LANE[typ]
    # 没有体裁但明显是作品（含书名号 + 出版/发表），按章节体裁落位
    if re.search(r"《[^》]+》", text) and re.search(r"出版|发表|连载|载|作《|写成|完成", text):
        cg = chapter_genre(zhang)
        if cg:
            return cg[0]
        if re.search(r"诗", text): return "poem"
        if re.search(r"剧", text): return "drama"
        if re.search(r"散文|杂文", text): return "prose"
        return "novel"
    bm = re.search(r"《([^》]{1,26})》", text)
    if bm and bm.group(1) in JOURNAL_NAMES:
        return "kanwu"
    z = zhang or ""
    if re.search(r"新诗", z): return "poem"
    if re.search(r"散文", z): return "prose"
    if re.search(r"戏剧", z): return "drama"
    if re.search(r"小说", z): return "novel"
    if re.search(r"思潮与运动", z): return "sichao"
    return "sichao"   # 兜底：剩余条目基本是文学史事件/论争


# ---------- 标题 / 噪声 ----------
def title_of(text, lane, typ):
    t = text.strip().rstrip("。")
    m = re.search(r"《([^》]{1,24})》(创刊|复刊|改刊|停刊|终刊)", t)
    if m:
        return "《%s》%s" % (m.group(1), m.group(2))
    if lane == "sichao":
        m = re.search(r"“([^”]{2,16})”的?(?:论争|论战|讨论)", t)
        if m:
            return "“%s”论争" % m.group(1)
        m = re.search(r"([\u4e00-\u9fa5]{2,10})(论争|论战)", t)
        if m:
            return m.group(1) + m.group(2)
    if lane == "kanwu":
        m = re.match(r"^(.{2,26}?)(成立|组建|发起组织|组成)", t)
        if m:
            name = re.split(r"[，。]", m.group(1))[-1].strip()
            name = re.sub(r"^(由|在|于|是)", "", name)
            if 2 <= len(name) <= 20:
                return name + "成立"
        m = re.search(r"《([^》]{1,24})》", t)
        if m:
            return "《%s》" % m.group(1)
    m = re.match(r"^([\u4e00-\u9fa5]{2,4})(?:等)?《([^》]{1,26})》", t)
    if m:
        return "《%s》" % m.group(2)
    m = re.search(r"^[^，。]{0,14}?《([^》]{1,26})》", t)
    if m:
        return "《%s》" % m.group(1)
    return re.split(r"[，。；]", t)[0][:24]


BIO = re.compile(r"^(入|转入|毕业|肄业|考入|就读|留学|回国|抵|离京|离沪|离港|赴日本|至|调|兼任|获准|被聘|应聘|"
                 r"升入|回到|经|随|偕|返|北上|南下|西行|东渡|出生|诞生|生于|卒于|定居|迁居|结束|离开|任|被任命)")


AUTHOR_CH = re.compile(r"章\s*(鲁迅|郭沫若|茅盾|老舍|巴金|沈从文|曹禺|赵树理|艾青)")
# 明显的生平行：以行迹动词开头，且不含「发表/出版/创刊/成立/论争/作《」
LIFE_VERB = re.compile(r"^(诞生|生于|出生|入|转入|毕业|肄业|考入|就读|留学|回国|抵|离|赴|至|任|被聘|应聘|升入|回到|经|随|偕|返|北上|南下|西行|东渡|调|兼任|获准|定居|迁居|结束|到达)")
LIT_ACTION = re.compile(r"发表|出版|创刊|复刊|成立|论争|论战|作《|写《|译《|编剧|首演|公演|主编|发起")


LIFE_ANY = re.compile(r"毕业后|退学|肄业|考入|入.{0,6}学习|任教|就任|任.{0,10}(校长|教员|教授|部长|科长|编辑|主编)"
                       r"|被聘|应聘|获准|调任|调离|定居|迁居|出生|诞生|逝世|结婚|团聚|病逝")
LIT_STRONG = re.compile(r"发表|出版|创刊|复刊|成立|论争|论战|首演|公演|《[^》]+》")


def is_life_record(text):
    """纯生平：讲的是一个人的行迹，不是文学事件"""
    t = text.strip()
    if LIT_STRONG.search(t):
        return False
    return bool(LIFE_VERB.match(t) or LIFE_ANY.search(t))


def is_noise(text, lane, typ, zhang=""):
    t = text.strip()
    if typ:
        return False
    if re.search(r"逝世|病逝|遇害|被捕|自杀|去世|牺牲|安葬|追悼", t):
        return False
    if is_life_record(t):
        return True
    if len(t) < 9:
        return True
    return False


MUST = set("""狂人日记 阿Q正传 呐喊 彷徨 野草 朝花夕拾 女神 子夜 家 骆驼祥子 边城 雷雨 日出 北京人
小二黑结婚 李有才板话 王贵与李香香 白毛女 围城 传奇 呼兰河传 生死场 莎菲女士的日记 沉沦 尝试集
寄小读者 背影 荷塘月色 雨巷 再别康桥 死水 大堰河——我的保姆 向太阳 火把 我爱这土地 暴风骤雨
太阳照在桑干河上 荷花淀 华威先生 在其香居茶馆里 上海屋檐下 屈原 升官图 漳河水 新儿女英雄传
吕梁英雄传 高干大 种谷记 铜墙铁壁 三千里江山 谁是最可爱的人 组织部新来的青年人 百合花 青春之歌
红岩 创业史 茶馆 关汉卿 蔡文姬 林海雪原 红旗谱 苦菜花 三家巷 山乡巨变 锻炼锻炼 登记 三里湾""".split())


CHAPTER_GENRE = [
    (re.compile(r"新诗"), ("poem", "诗集")),
    (re.compile(r"散文（"), ("prose", "散文")),
    (re.compile(r"戏剧（"), ("drama", "话剧")),
    (re.compile(r"小说（|通俗小说"), ("novel", "")),
]


def chapter_genre(zhang):
    """本书按体裁分章：新诗/散文/戏剧/小说章 → 体裁约束。
    作家专章（鲁迅、郭沫若、艾青……）不约束，作家什么都写。"""
    z = zhang or ""
    for rx, g in CHAPTER_GENRE:
        if rx.search(z):
            return g
    return None


# 已知名作的体裁（教材公认，用于纠正正文最近邻的误判）
KNOWN_GENRE = {
    "尝试集": ("poem", "诗集"), "女神": ("poem", "诗集"), "星空": ("poem", "诗集"),
    "死水": ("poem", "诗集"), "红烛": ("poem", "诗集"), "雨巷": ("poem", "诗集"),
    "再别康桥": ("poem", "诗集"), "大堰河——我的保姆": ("poem", "诗集"), "向太阳": ("poem", "诗集"),
    "火把": ("poem", "诗集"), "我爱这土地": ("poem", "诗集"), "王贵与李香香": ("poem", "叙事诗"),
    "漳河水": ("poem", "叙事诗"), "给战斗者": ("poem", "诗集"), "十四行集": ("poem", "诗集"),
    "白毛女": ("drama", "话剧"), "升官图": ("drama", "话剧"), "蔡文姬": ("drama", "话剧"),
    "茶馆": ("drama", "话剧"), "雷雨": ("drama", "话剧"), "日出": ("drama", "话剧"),
    "上海屋檐下": ("drama", "话剧"), "屈原": ("drama", "话剧"), "压迫": ("drama", "话剧"),
    "华威先生": ("novel", "短篇小说"), "在其香居茶馆里": ("novel", "短篇小说"),
    "小二黑结婚": ("novel", "短篇小说"), "李有才板话": ("novel", "中篇小说"),
    "登记": ("novel", "短篇小说"), "锻炼锻炼": ("novel", "短篇小说"),
    "三里湾": ("novel", "长篇小说"), "太阳照在桑干河上": ("novel", "长篇小说"),
    "种谷记": ("novel", "长篇小说"), "高干大": ("novel", "长篇小说"),
    "新儿女英雄传": ("novel", "长篇小说"), "吕梁英雄传": ("novel", "长篇小说"),
    "呼兰河传": ("novel", "长篇小说"), "生死场": ("novel", "中篇小说"),
    "围城": ("novel", "长篇小说"), "传奇": ("novel", "短篇小说集"),
    "憩园": ("novel", "中篇小说"), "家": ("novel", "长篇小说"),
    "子夜": ("novel", "长篇小说"), "骆驼祥子": ("novel", "长篇小说"),
    "边城": ("novel", "中篇小说"), "阿Q正传": ("novel", "中篇小说"),
    "狂人日记": ("novel", "短篇小说"), "呐喊": ("novel", "短篇小说集"),
    "彷徨": ("novel", "短篇小说集"), "沉沦": ("novel", "短篇小说集"),
    "莎菲女士的日记": ("novel", "短篇小说"), "野草": ("prose", "散文诗"),
    "朝花夕拾": ("prose", "散文集"), "寄小读者": ("prose", "散文集"),
    "背影": ("prose", "散文"), "荷塘月色": ("prose", "散文"), "桨声灯影里的秦淮河": ("prose", "散文"),
    "人的文学": ("sichao", "论文"), "文学改良刍议": ("sichao", "论文"), "文学革命论": ("sichao", "论文"),
}


def period_of(y, m):
    v = y + ((m or 6) - 0.5) / 12
    if v < 1917: return "p0"
    if v < 1928: return "p1"
    if v < 1937.5: return "p2"
    if v < 1949.5: return "p3"
    return "p4"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("epub")
    ap.add_argument("--csv", help="同时导出可编辑 CSV")
    ap.add_argument("-o", "--out", default=os.path.join(ROOT, "data", "events.js"))
    args = ap.parse_args()

    blocks = load_blocks(args.epub)
    main_text = "\n".join(t for b in blocks if not b["sec"].startswith("附录") for t in b["text"])
    paras = [(t, b["zhang"]) for b in blocks if not b["sec"].startswith("附录")
             for t in b["text"] if 60 <= len(t) <= 320]

    rows = []
    for b in blocks:
        if not (b["sec"].startswith("附录") and len("".join(b["text"])) > 200):
            continue
        for r in parse_nian(b["text"]):
            r["zhang"] = b["zhang"]
            rows.append(r)

    typed = build_type_dict(main_text, rows)
    out, seen = [], set()
    for r in rows:
        text = re.sub(r"^(同月|同年|是年|本年|本月)", "", r["text"].strip()).strip()
        text = re.sub(r"^\d{1,2}月(初|底|中)?\s*", "", text)
        text = re.sub(r"^(始|又|并|另)\s*", "", text).strip()
        if not text:
            continue
        bm = re.search(r"《([^》]{1,26})》", text)
        typ = infer_type(bm.group(1), typed, main_text, text) if bm else ""
        lane = lane_of(text, r["zhang"], typ)
        if is_noise(text, lane, typ, r["zhang"]):
            continue
        # 刊物名优先：是刊物就归「社团 · 刊物」，不参与体裁判定
        if bm and bm.group(1) in JOURNAL_NAMES and not re.search(r"（[^）]*(小说|诗|散文|话剧|戏剧)", text):
            lane, typ = "kanwu", ""
        # 已知名作体裁优先（最可靠）
        elif bm and bm.group(1) in KNOWN_GENRE:
            gl, gt = KNOWN_GENRE[bm.group(1)]
            lane, typ = gl, gt
        # 章节体裁优先于正文最近邻推断（正文里常提到别的体裁）
        cg = chapter_genre(r["zhang"])
        if cg and typ:
            gl, gt = cg
            ok = {"poem": ("诗集", "叙事诗", "散文诗"), "prose": ("散文", "散文集", "杂文集", "报告文学"),
                  "drama": ("话剧",), "novel": ("长篇小说", "中篇小说", "短篇小说", "短篇小说集", "小说集")}
            if typ not in ok.get(gl, ()) and gl in ("poem", "drama"):
                typ = gt
                lane = gl
        title = title_of(text, lane, typ)
        if not title or len(title) < 2 or len(title) > 26:
            continue
        if re.match(r"^(的|在|由|于|和|与|及|为)", title):
            continue
        if (title, r["y"]) in seen:
            continue
        seen.add((title, r["y"]))

        k = title.strip("《》“”")
        # 频次只算「作为作品被讨论」的次数：
        # 刊物/社团的名字天然高频，不能据此判定必背
        f = main_text.count("《" + k + "》") if len(k) > 1 else 0
        if lane == "kanwu":
            imp = 3 if re.search(r"创刊|成立", text) and f >= 8 else 2 if f >= 4 else 1
        else:
            imp = 3 if f >= 12 else 2 if f >= 4 else 1
        if k in MUST:
            imp = 3
        # 同一标题在本年表里出现多次（如《故乡》《离婚》），只有最接近该章正文讨论的那条算必背
        if len(k) >= 2:
            n_same = sum(1 for r2 in rows if k in r2["text"])
            if n_same >= 3 and f < 30:
                imp = min(imp, 2)
        # 体裁存疑（刊物名被标成散文/话剧）的降级
        if typ in ("散文", "话剧", "杂文集") and re.search(r"创刊|复刊|月刊|周刊|季刊|副刊", text):
            imp = min(imp, 2)
        # 全集/选集/文集不是单篇作品，不给必背
        if re.search(r"全集|选集|文集|作品集|丛书", title):
            imp = min(imp, 2)

        # 考点：正文里讲这条的段落
        cands = [(p.count(k) * 3 + (2 if z == r["zhang"] else 0), len(p), p)
                 for p, z in paras if p.count(k)]
        detail = ""
        if cands:
            cands.sort(key=lambda x: (-x[0], x[1]))
            detail = cands[0][2][:170]

        date = "%d" % r["y"]
        if r["m"]:
            date += "-%02d" % r["m"]
            if r["d"]:
                date += "-%02d" % r["d"]

        out.append({
            "date": date, "title": title, "lane": lane,
            "period": period_of(r["y"], r["m"]), "kind": typ, "importance": imp,
            "people": [], "schools": [],
            "summary": re.sub(r"\s+", "", text)[:120],
            "detail": detail, "memory": "", "confuse": "",
            "tags": (["必背"] if imp == 3 else []) + (["高频"] if f >= 20 else []),
            "chapter": r["zhang"],
        })

    out.sort(key=lambda e: (e["date"], -e["importance"]))
    for i, e in enumerate(out):
        e["id"] = "L%05d" % i

    data = {
        "meta": {
            "title": "中国现当代文学时间轴",
            "source": os.path.basename(args.epub),
            "updated": __import__("datetime").date.today().isoformat(),
            "minYear": 1898, "maxYear": 2000,
        },
        "periods": PERIODS, "lanes": LANES, "events": out,
    }

    from collections import Counter
    print("条目 %d 条" % len(out))
    print("轨道：" + "，".join("%s %d" % (LANE_CN[l["id"]], sum(1 for e in out if e["lane"] == l["id"])) for l in LANES))
    print("重要度：" + "，".join("%d %d条" % (k, v) for k, v in sorted(Counter(e["importance"] for e in out).items())))
    print("有考点 %d 条" % sum(1 for e in out if e["detail"]))

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w", encoding="utf-8") as f:
        f.write("/* 由 scripts/build_from_epub.py 从 EPUB 各章「本章年表」抽取生成，勿手改。\n")
        f.write("   改数据请改 数据源.csv 后运行 scripts/import_csv.py。 */\n")
        f.write("window.LIT_DATA = " + json.dumps(data, ensure_ascii=False, indent=1) + ";\n")
    print("已写入 " + args.out)

    if args.csv:
        cols = ["日期", "标题", "轨道", "类型", "重要度", "人物", "流派",
                "一句话", "考点", "记忆钩子", "易混", "标签", "出处"]
        with open(args.csv, "w", encoding="utf-8-sig", newline="") as f:
            w = csv.DictWriter(f, fieldnames=cols)
            w.writeheader()
            for e in out:
                w.writerow({"日期": e["date"], "标题": e["title"], "轨道": LANE_CN[e["lane"]],
                            "类型": e["kind"], "重要度": e["importance"],
                            "人物": "、".join(e["people"]), "流派": "、".join(e["schools"]),
                            "一句话": e["summary"], "考点": e["detail"],
                            "记忆钩子": e["memory"], "易混": e["confuse"],
                            "标签": "、".join(e["tags"]), "出处": e["chapter"]})
        print("已导出 " + args.csv)


if __name__ == "__main__":
    main()
