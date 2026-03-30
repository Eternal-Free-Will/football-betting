# pip3 install requests beautifulsoup4 lxml
# python3 500.py --range "2026-01-10~2026-01-10 23:59" 参数加双引号

import requests
from bs4 import BeautifulSoup
import time
import random
import argparse
from datetime import datetime
import re # 用于清理非法文件名字符
import os

# --- 可方便获取历史数据或当日数据 ---
BASE_URL = "https://trade.500.com/jczq/"

# --- 路径自适应配置 ---
# 无论从哪里启动脚本，BASE_DIR 永远指向 500.py 所在的那个文件夹
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

# 请求时的通用User_Agent
USERAGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

# 配置目标联赛名称
# TARGET_LEAGUES = ["英超", "英冠", "欧冠"]
TARGET_LEAGUES = []

# 配置目标机构 ID 和名称
TARGET_COMPANIES = {
    "1055": "平博",
    "3": "Bet365",
    "280": "皇冠",
    "5": "澳门",
    "293": "威廉希尔",
    "2": "立博",
    "4": "Interwetten",
    "1": "竞彩官方",
    "651": "利记",
}

# 专门处理竞彩让球格式
def format_handicap(hc):
    """
    专门处理竞彩让球格式：
    1  -> +1
    -1 -> -1
    0  -> 0
    """
    try:
        # 先转换为整数（竞彩让球通常是整数）
        val = int(float(hc)) 
        if val > 0:
            return f"+{val}"
        else:
            # 负数自带负号，0直接返回字符串
            return str(val)
    except (ValueError, TypeError):
        return str(hc) # 如果抓到的是非数字，原样返回

def sanitize_filename(name):
    """
    清理文件名中的非法字符，防止报错
    """
    return re.sub(r'[\\/:*?"<>|]', '_', name)

def parse_custom_time(time_str):
    """
    解析用户输入的时间字符串。
    支持格式: '2026-01-10' (补全为 00:00) 或 '2026-01-10 04:00'
    """
    time_str = time_str.strip()
    try:
        if len(time_str) <= 10: # 只有日期
            return datetime.strptime(time_str, "%Y-%m-%d")
        else: # 日期 + 时间
            return datetime.strptime(time_str, "%Y-%m-%d %H:%M")
    except ValueError as e:
        print(f"时间格式错误: {time_str}，请确保格式为 YYYY-MM-DD 或 YYYY-MM-DD HH:MM")
        return None

# --- Start 获取“数据分析”页面数据 ---

import re

def adjust_team_format(text):
    # 正则表达式拆解：
    # ^(\[\d+\])      : 必须以 [数字] 开头 (捕获组1: 主队排名)
    # (.*?)           : 匹配主队名，直到遇到分隔符 (捕获组2: 主队名)
    # \s*(VS|\d+:\d+)\s* : 匹配分隔符，支持 "VS" 或 "3:2" 这种比分格式 (捕获组3: 分隔符)
    # (.*)            : 匹配剩下的所有内容 (捕获组4: 客队名+客队排名)
    pattern = r'^(\[\d+\])(.*?)\s*(VS|\d+:\d+)\s*(.*)'
    
    match = re.search(pattern, text)
    
    if match:
        home_rank = match.group(1)      # 例如: [10]
        home_name = match.group(2).strip() # 例如: 德国
        separator = match.group(3)      # 例如: VS 或 3:2
        away_part = match.group(4).strip() # 例如: 加纳[77]
        
        # 返回格式：主队名 + 主队排名 + 分隔符 + 客队部分
        return f"{home_name}{home_rank} {separator} {away_part}"
    
    # 如果不匹配（说明主队没有排名，或者格式不对），直接返回原始文本
    return text

# 通用清理函数：剔除 style='display: none' 的标签
def clean_hidden_tags(element):
    if element:
        # 1. 剔除 style 包含 display:none 的
        pattern = re.compile(r'display\s*:\s*none', re.IGNORECASE)
        for hidden in element.find_all(style=pattern):
            hidden.decompose()
            
        # 2. 500网常用的隐藏类名（根据实际源码调整）
        # 比如有的排名虽然没写 style，但它是 hidden 类
        for hidden in element.find_all(class_='gray'): 
             # 注意：只有当你确定 gray 类全是你想删的内容时才这么做
             hidden.decompose()
    return element

# 1. 获取赛事轮次、排名及比分信息
def get_league_round_info(soup):
    results = {"league_round": "", "current_score": "", "home": {"this_season": "", "last_league": "", "last_rank": ""}, "away": {"this_season": "", "last_league": "", "last_rank": ""}}
    # 定位核心容器
    header_cont = soup.find('div', class_='odds_hd_cont')
    if not header_cont:
        return results

    # , recursive=False
    # 逐级找到 tr (因为 td 在 tr 下面)
    # 注意：find 会自动向下找，所以可以直接跳过 table/tbody 找到 tr
    target_tr = header_cont.find('tr')
    tds = target_tr.find_all('td', recursive=False)

    if len(tds) < 5: 
        return results

    # --- 1. 解析联赛、轮次及比分 (第三个td) ---
    round_link = tds[2].find('a', class_='hd_name')
    if round_link: results["league_round"] = round_link.get_text(strip=True)

    score_p = tds[2].find('p', class_='odds_hd_bf')
    if score_p and score_p.find('strong'):
        txt = score_p.find('strong').get_text(strip=True).replace(" ", "")
        # 提取 strong 标签内的文本，可能是 "VS" 或 "2:1"
        results["current_score"] = "" if txt.upper() == "VS" else txt

    # 排名逻辑
    def parse_rank(td_node, need_adjust = None):
        # 新增：存储上赛季联赛名称、名次
        this_season, last_season_num, last_season_league = "", "", ""
        lis = td_node.find_all('li')
        if len(lis) >= 2:
            rank_li = lis[1]

            # 1. 提取本赛季排名 (span.red)
            span_red = rank_li.find('span', class_='red')
            if span_red:
                this_season = span_red.get_text(strip=True)
            # 2. 提取上赛季联赛名称和排名数字
            li_text = rank_li.get_text()
            # 哪怕没有“赛前排名”，split 也会返回原字符串
            last_season_part = li_text.split("赛前排名")[0]
            if need_adjust:
                last_season_part = li_text.split("赛前排名")[1]
            # match.group(1) 是联赛名，match.group(2) 是排名数字
            last_match = re.search(r'上赛季(.*?)排名:\s*(\d+)', last_season_part)
            if last_match: 
                last_season_league, last_season_num = last_match.group(1).strip(), last_match.group(2)

        return {"this_season": this_season, "last_league": last_season_league, "last_rank": last_season_num}

    results["home"] = parse_rank(tds[0])
    results["away"] = parse_rank(tds[4], True)

    return results

# 2. 获取两支球队的赛前联赛积分排名数据
def get_pre_match_rank(soup):
    """
    输出格式严格对应：比赛、胜、平、负、进、失、净、积分、排名、胜率
    fields = ["matches", "win", "draw", "loss", "goal", "lost", "net", "points", "rank", "win_rate"]
    """
    results = {
        "home_rank": {"total": [], "home": [], "away": []},
        "away_rank": {"total": [], "home": [], "away": []}
    }

    # 1. 精准定位容器：查找标题为“赛前联赛积分排名”的 M_box
    target_box = None
    all_boxes = soup.find_all('div', class_='M_box')
    for box in all_boxes:
        title = box.find('h4')
        if title and "赛前联赛积分排名" in title.get_text():
            target_box = box
            break
    
    if not target_box:
        return results

    # 2. 定义映射关系：team_a 为主队，team_b 为客队
    mapping = {
        "team_a": "home_rank",
        "team_b": "away_rank"
    }

    for class_name, key in mapping.items():
        team_div = target_box.find('div', class_=class_name)
        if not team_div:
            continue

        table = team_div.find('table', class_='pub_table')
        if not table:
            continue

        # 3. 获取所有 tr（第0行表头，1-3行为总、主、客）
        rows = table.find_all('tr')
        if len(rows) < 4:
            continue

        # 对应的行索引与存储键名
        row_map = {1: "total", 2: "home", 3: "away"}

        for idx, row_key in row_map.items():
            tds = rows[idx].find_all('td')
            if len(tds) < 11:
                # 如果某行数据缺失，填充空字符串保证位置对齐
                results[key][row_key] = [""] * 10
                continue
            
            # 严格按照要求的 10 个字段顺序提取数据：
            # tds[1]=比赛, tds[2]=胜, tds[3]=平, tds[4]=负, tds[5]=进, 
            # tds[6]=失, tds[7]=净, tds[8]=积分, tds[9]=排名, tds[10]=胜率
            row_data = []
            for i in range(1, 11):
                val = tds[i].get_text(strip=True).replace(" ", "")
                row_data.append(val)
            
            results[key][row_key] = row_data

    return results

# 3. 获取两队交战历史数据
def get_battle_history(soup):
    results = {"summary": "", "records": []}
    # 定位交战历史容器
    container = soup.find('div', id='team_jiaozhan')
    if not container: return results

    # --- 1. 提取概览信息 ---
    title_div = container.find('div', class_='M_title')
    if title_div:
        results["summary"] = title_div.get_text(" ", strip=True)
    
    # --- 2. 提取详细表格数据 ---
    table = container.find('table', class_='pub_table')
    if table:
        # 仅获取 class 为 tr1 或 tr2 的行 (过滤掉 tr3 和 th)
        rows = table.find_all('tr', class_=lambda x: x in ['tr1', 'tr2'])
        for row in rows:
            # 预先移除所有 style="display: none;" 的标签（如赛前排名 [20]）
            # row = clean_hidden_tags(row)

            tds = row.find_all('td')
            # 联赛、日期、对阵(主队 比分 客队)、半场、赛果、欧指(胜/平/负)、亚指(水位 盘口 水位)、盘路(赢/输/走)、大小(大/小)
            if len(tds) >= 10:
                results["records"].append([
                    adjust_team_format(tds[0].get_text(strip=True)),
                    tds[1].get_text(strip=True),
                    tds[2].get_text(strip=True).replace(" : ", ":"),
                    tds[3].get_text(strip=True).replace(" : ", ":"),
                    tds[4].get_text(strip=True),
                    tds[5].get_text("/", strip=True),
                    tds[6].get_text(strip=True),
                    tds[7].get_text(strip=True),
                    tds[8].get_text(strip=True)])

    return results

# 4. 获取主客队近期10场比赛记录及统计概览
def get_recent_10_records(soup):
    results = {
        "home": {"summary": "", "records": []},
        "away": {"summary": "", "records": []}
    }
    # 映射 ID：1_1 为主队，1_0 为客队
    mapping = {"team_zhanji1_1": "home", "team_zhanji1_0": "away"}

    for container_id, key in mapping.items():
        container = soup.find('div', id=container_id)
        if not container: continue

        table = container.find('table', class_='pub_table')
        if not table: continue
        # --- 1. 过滤行逻辑 ---
        # 只需要 tr1 和 tr2，排除 tr3 (本场)
        rows = table.find_all('tr', class_=lambda x: x in ['tr1', 'tr2'])
        for row in rows:
            # 预处理：剔除所有 style="display: none;" 的标签（如赛前排名 [11]）
            # row = clean_hidden_tags(row)

            # --- 2. 区分【统计行】与【比赛记录行】 ---
            # 比赛记录行带有 fid 属性，统计行没有
            if not row.has_attr('fid'):
                results[key]["summary"] = row.get_text(" ", strip=True)
            else:
                # --- 3. 解析比赛记录行 ---
                tds = row.find_all('td')
                # 赛事、比赛日期、主队 比分 客队、半场、赛果、欧指、亚指、盘路、大小、备注
                if len(tds) >= 10:
                    results[key]["records"].append([
                        tds[0].get_text(strip=True),
                        tds[1].get_text(strip=True),
                        adjust_team_format(tds[2].get_text(strip=True).replace(" : ", ":")),
                        tds[3].get_text(strip=True).replace(" : ", ":"),
                        tds[4].get_text(strip=True),
                        tds[5].get_text("/", strip=True), # 欧指使用/分隔（如 2.2/3.15/2.84）
                        tds[6].get_text(strip=True),
                        tds[7].get_text(strip=True),
                        tds[8].get_text(strip=True)])
    return results

# 5. 获取主队在主场、客队在客场的近期比赛数据
def get_venue_records(soup):
    results = {
        "home_at_home": {"summary": "", "records": []},
        "away_at_away": {"summary": "", "records": []}
    }

    # ID 映射：zhanji2_1 是主队主场，zhanji2_0 是客队客场
    mapping = {
        "team_zhanji2_1": "home_at_home",
        "team_zhanji2_0": "away_at_away"
    }

    for container_id, key in mapping.items():
        container = soup.find('div', id=container_id)
        if not container: continue

        # --- 1. 提取底部概览统计信息 ---
        bottom_info = container.find('div', class_='bottom_info')
        if bottom_info:
            results[key]["summary"] = bottom_info.find('p').get_text(" ", strip=True)
        
        # --- 2. 提取表格详细比赛记录 ---
        table = container.find('table', class_='pub_table')
        if not table: continue

        # 过滤行：只需要 tr1 和 tr2，排除 tr3 和表头
        rows = table.find_all('tr', class_=lambda x: x in ['tr1', 'tr2'])
        for row in rows:
            # row = clean_hidden_tags(row)
            tds = row.find_all('td')

            # 此类表格固定为 8 个 td：赛事、比赛日期、对阵(主队 比分 客队)、盘口、半场、赛果、盘路、大小
            if len(tds) >= 8:
                results[key]["records"].append([
                        tds[0].get_text(strip=True),
                        tds[1].get_text(strip=True),
                        adjust_team_format(tds[2].get_text(strip=True).replace(" : ", ":")),
                        tds[3].get_text(strip=True),
                        tds[4].get_text(strip=True).replace(" : ", ":"),
                        tds[5].get_text(strip=True),
                        tds[6].get_text(strip=True),
                        tds[7].get_text(strip=True)])
    return results

# 6. 获取未来赛事数据
def get_future_matches(soup):
    results = {"home": [], "away": []}

    # 1. 定位第一个 div.M_box.integral (未来赛事模块)
    future_box = soup.find('div', class_='M_box integral')
    if not future_box: return results

    # 2. 定义映射关系：team_a 对应主队，team_b 对应客队
    mapping = {"team_a": "home", "team_b": "away"}
    for class_name, key in mapping.items():
        team_div = future_box.find('div', class_=class_name)
        if not team_div:
            continue
        
        table = team_div.find('table', class_='pub_table')

        rows = table.find_all('tr', class_=lambda x: x in ['tr1', 'tr2'])
        for row in rows:
            tds = row.find_all('td')
            if len(tds) < 4:
                continue
            # 赛事名称、比赛日期、主队VS客队、相隔天数
            results[key].append([tds[0].text.strip(), 
                    tds[1].text.strip(), 
                    tds[2].get_text(" ", strip=True).replace(" VS ", "VS"), 
                    tds[3].text.strip()])
    return results

# 在 process_single_match 中增加的数据分析页面处理逻辑
def handle_data_analysis_section(fid, f, headers):
    f.write("\n【 数据分析：赛事轮次、队伍排名、联赛积分、交战历史、近期数据 】\n")
    data_analysis_url = f"https://odds.500.com/fenxi/shuju-{fid}.shtml"
    try:
        res = requests.get(data_analysis_url, headers=headers, timeout=5)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'lxml')

        # 1. 获取联赛轮次、排名及比分信息
        l_r_info = get_league_round_info(soup)
        f.write("\n  联赛轮次、队伍排名：\n")
        f.write(f"  联赛轮次: {l_r_info['league_round']}\n")
        # 判断比分是否为空（之前逻辑是VS则为空）
        if l_r_info['current_score']:
            f.write(f"  比分: {l_r_info['current_score']}\n")
            
        # 主队排名处理
        h_this = l_r_info['home']['this_season'] if l_r_info['home']['this_season'] else '无'
        h_last_l = l_r_info['home']['last_league']
        h_last_r = l_r_info['home']['last_rank'] if l_r_info['home']['last_rank'] else '无'
        f.write(f"  主队本赛季排名: {h_this}\n")
        f.write(f"  主队上赛季{h_last_l}排名: {h_last_r}\n")
        
        # 客队排名处理
        a_this = l_r_info['away']['this_season'] if l_r_info['away']['this_season'] else '无'
        a_last_l = l_r_info['away']['last_league']
        a_last_r = l_r_info['away']['last_rank'] if l_r_info['away']['last_rank'] else '无'
        f.write(f"  客队本赛季排名: {a_this}\n")
        f.write(f"  客队上赛季{a_last_l}排名: {a_last_r}\n")
        f.write("  " + "-"*50 + "\n")

        # 2. 获取两支球队的赛前联赛积分排名数据
        p_m_rank = get_pre_match_rank(soup)
        # 比赛、胜、平、负、进、失、净、积分、排名、胜率
        f.write("\n  赛前联赛积分排名数据：\n")
        # 内部辅助函数简化代码
        def write_rank_row(title, data_list):
            if data_list:
                f.write(f"  {title+'：':\u3000<4} 比赛{data_list[0]+'场':\u3000<6} 胜{data_list[1]+'场':\u3000<6} 平{data_list[2]+'场':\u3000<6} 负{data_list[3]+'场':\u3000<4} 进球{data_list[4]:<4} 失球{data_list[5]:<4} 净胜球{data_list[6]:<4} 积分{data_list[7]:<4} 排名{data_list[8]:<4} 胜率{data_list[9]:<4}\n")
        if p_m_rank['home_rank']['total'][0]:
            f.write("  主队数据：\n")
            write_rank_row("总成绩", p_m_rank['home_rank']['total'])
            write_rank_row("主场", p_m_rank['home_rank']['home'])
            write_rank_row("客场", p_m_rank['home_rank']['away'])
        else: 
            f.write("  主队数据：暂无\n")

        if p_m_rank['away_rank']['total'][0]:
            f.write("  客队数据：\n")
            write_rank_row("总成绩", p_m_rank['away_rank']['total'])
            write_rank_row("主场", p_m_rank['away_rank']['home'])
            write_rank_row("客场", p_m_rank['away_rank']['away'])
        else:
            f.write("  客队数据：暂无\n")
        f.write("  " + "-"*50 + "\n")

        # 3. 获取两队交战历史数据
        b_h = get_battle_history(soup)
        if len(b_h['records']): 
            f.write("\n  两队交战历史数据：\n")

            f.write(f"  数据概览：{b_h['summary']}\n")
            # 联赛、日期、对阵(主队 比分 客队)、半场、赛果、欧指(胜/平/负)、亚指(水位 盘口 水位)、盘路(赢/输/走)、大小(大/小)
            for r in b_h['records']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<16} 半场{r[3]:<6} {r[4]+'(赛果)':\u3000<6} {r[5]+'(平均欧赔)':\u3000<22} {r[6]+'(盘口)':\u3000<20} {r[7]+'(盘路)':\u3000<6} {r[8]+'(大小)':\u3000<6}\n")
        else:
            f.write("\n  两队交战历史数据：暂无\n")
        f.write("  " + "-"*50 + "\n")

        # 4. 获取主客队近期10场比赛记录及统计概览
        r_10 = get_recent_10_records(soup)
        f.write("\n  主客队近期10场比赛记录及统计概览：\n")        
        if len(r_10['home']['records']):
            f.write(f"  主队近期10场比赛记录：\n")
            f.write(f"  数据概览：{r_10['home']['summary']}\n")
            f.write("  数据详情：\n")
            # 赛事、比赛日期、主队 比分 客队、半场、赛果、欧指、亚指、盘路、大小
            for r in r_10['home']['records']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<16} 半场{r[3]:<6} {r[4]+'(赛果)':\u3000<6} {r[5]+'(平均欧赔)':\u3000<22} {r[6]+'(盘口)':\u3000<20} {r[7]+'(盘路)':\u3000<6} {r[8]+'(大小)':\u3000<6}\n")
        else:
            f.write(f"  主队近期10场比赛记录：暂无\n")
        
        if len(r_10['away']['records']):
            f.write(f"  客队近期10场比赛记录：\n")
            f.write(f"  数据概览：{r_10['away']['summary']}\n")
            f.write("  数据详情：\n")
            for r in r_10['away']['records']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<16} 半场{r[3]:<6} {r[4]+'(赛果)':\u3000<6} {r[5]+'(平均欧赔)':\u3000<22} {r[6]+'(盘口)':\u3000<20} {r[7]+'(盘路)':\u3000<6} {r[8]+'(大小)':\u3000<6}\n")
        else:
            f.write(f"  客队近期10场比赛记录：暂无\n")
        f.write("  " + "-"*50 + "\n")

        # 5. 获取主队在主场、客队在客场的近期比赛数据
        f.write("\n  主队在主场、客队在客场的近期比赛数据：\n")
        v_r = get_venue_records(soup)
        if len(v_r['home_at_home']['records']):
            f.write(f"  主队在主场近期比赛记录：\n")
            f.write(f"  数据概览：{v_r['home_at_home']['summary']}\n")
            f.write("  数据详情：\n")
            # 赛事、比赛日期、对阵(主队 比分 客队)、盘口、半场、赛果、盘路、大小
            for r in v_r['home_at_home']['records']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<16} {r[3]+'(盘口)':\u3000<10} 半场{r[4]:<6} {r[5]+'(赛果)':\u3000<6} {r[6]+'(盘路)':\u3000<6} {r[7]+'(大小)':\u3000<6}\n")
        else:
            f.write(f"  主队在主场近期比赛记录：暂无\n")
        
        if len(v_r['away_at_away']['records']):
            f.write(f"  客队在客场近期比赛记录：\n")
            f.write(f"  数据概览：{v_r['away_at_away']['summary']}\n")
            f.write("  数据详情：\n")
            # 赛事、比赛日期、对阵(主队 比分 客队)、盘口、半场、赛果、盘路、大小
            for r in v_r['away_at_away']['records']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<16} {r[3]+'(盘口)':\u3000<10} 半场{r[4]:<6} {r[5]+'(赛果)':\u3000<6} {r[6]+'(盘路)':\u3000<6} {r[7]+'(大小)':\u3000<6}\n")
        else:
            f.write(f"  客队在主场近期比赛记录：暂无\n")
        f.write("  " + "-"*50 + "\n")

        # 6. 获取未来赛事数据
        f_m = get_future_matches(soup)
        f.write("\n  主队、客队未来赛事数据：\n")        

        f.write(f"  主队未来赛事：\n")
        if f_m['home']:
            # 赛事名称、比赛日期、主队VS客队、相隔天数
            for r in f_m['home']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<12} 距离天数{r[3]:<4}\n")
        else:
            f.write("  主队未来暂无赛事！\n")
        
        f.write(f"  客队未来赛事：\n")
        if f_m['away']:
            for r in f_m['away']:
                f.write(f"  {r[0]:\u3000<6} {r[1]:<12} {r[2]:\u3000<12} 距离天数{r[3]:<4}\n")
        else:
            f.write("  客队未来暂无赛事！\n")
        f.write("  " + "-"*50 + "\n")

    except Exception as e:
        f.write(f"  数据分析页面访问异常: {e}\n")

# --- End 获取“数据分析”页面数据 ---

# 获取“让球指数”页面数据
def get_rangqiu_detail(fid, comp_id, data_time, handicap_line, max_retries=15):
    """
    获取具体机构在特定让球数下的赔率变动
    :param fid: 比赛 ID
    :param comp_id: 机构 ID
    :param data-time: 机构特定的更新时间
    :param handicap_line: 让球数，如 -1, -2, 1
    :param max_retries: 最大重试次数
    """

    t_ms = int(time.time() * 1000)
    formatted_time = data_time.replace(' ', '+')
    
    # 构造让球盘专用的 Ajax URL
    ajax_url = (f"https://odds.500.com/fenxi1/json/rspf.php?"
                f"_={t_ms}&fid={fid}&cid={comp_id}&r=1&time={formatted_time}"
                f"&handicapline={handicap_line}&type=rspf")
    
    headers = {
        'User-Agent': USERAGENT,
        'Referer': f'https://odds.500.com/fenxi/rangqiu-{fid}.shtml',
        'X-Requested-With': 'XMLHttpRequest'
    }

    for i in range(max_retries):
        try:
            response = requests.get(ajax_url, headers=headers, timeout=5)
            if response.status_code == 200:
                data_list = response.json()
                if data_list:
                    details = []
                    # 数据结构: [胜, 平, 负, 返还率, 更新时间, ...]
                    for item in data_list:
                        if len(item) >= 5:
                            details.append(f"  [{item[4]}] 让球:{format_handicap(handicap_line):<4} 胜:{item[0]:<6} 平:{item[1]:<6} 负:{item[2]:<6}")
                    return details
            print(f"  [ID:{comp_id}|让:{format_handicap(handicap_line)}] 第 {i+1} 次获取为空，重试...")
        except Exception as e:
            print(f"  网络错误: {e}")
        time.sleep(0.5 + random.random())
    return []

# 在 process_single_match 中增加的让球处理逻辑
def handle_rangqiu_section(fid, f, headers):
    f.write("\n【 竞足让球变动（包含多重让球） 】\n")
    rangqiu_url = f"https://odds.500.com/fenxi/rangqiu-{fid}.shtml"
    try:
        res = requests.get(rangqiu_url, headers=headers, timeout=5)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'lxml')
        table = soup.find('table', id='datatb')
        if table:
            # 1. 扫描所有机构和对应的让球线
            # 结构: {cid: {"name": "机构名", "time": "更新时间", "lines": set(让球数)}}
            comp_map = {}
            rows = table.find_all('tr', id=True)
            for tr in rows:
                # 优先获取 cid 属性，如果没有则获取 id 属性，最后进行清洗
                raw_id = tr.get('cid') or tr.get('id') or ""
                cid = raw_id.replace('tr_', '').replace('tr', '')
                h_line = tr.get('handicapline') # 获取关键属性：让球数
                d_time = tr.get('data-time')
                
                if cid in TARGET_COMPANIES and h_line:
                    if cid not in comp_map:
                        comp_map[cid] = {"time": d_time, "lines": set()}
                    comp_map[cid]["lines"].add(h_line)

            # 2. 遍历收集到的机构和线路进行抓取
            for cid, info in comp_map.items():
                f.write(f"  机构: {TARGET_COMPANIES[cid]}\n")
                for line in sorted(info["lines"]): # 排序让球数，例如 -2, -1
                    history = get_rangqiu_detail(fid, cid, info["time"], line)
                    f.write("\n".join(history) + "\n" if history else "    (多次尝试该机构暂无让球历史变动数据)\n")
                f.write("  " + "-"*50 + "\n")
        else:
            f.write("  未在页面找到让球数据表 table#datatb\n")
    except Exception as e:
        f.write(f"  让球指数页面访问异常: {e}\n")

# 获取“亚盘对比”页面数据
def get_yazhi_detail(fid, comp_id, max_retries=15):
    """
    获取具体机构的亚盘变动详情，带重试机制
    :param fid: 比赛 ID
    :param comp_id: 机构 ID
    :param max_retries: 最大重试次数
    """
    t = int(time.time() * 1000)
    # 增加 r 参数的随机性（有时 500 网会根据 r 值做简单的频率控制）random.random()
    ajax_url = f"https://odds.500.com/fenxi1/inc/yazhiajax.php?fid={fid}&id={comp_id}&t={t}&r=1"
    
    headers = {
        'User-Agent': USERAGENT,
        'Referer': f'https://odds.500.com/fenxi/yazhi-{fid}.shtml',
        'X-Requested-With': 'XMLHttpRequest' # 模拟 Ajax 请求必备
    }

    for i in range(max_retries):
        try:
            # 增加超时控制，防止死等
            response = requests.get(ajax_url, headers=headers, timeout=5)
            
            # 如果状态码正常且返回内容不是空的 []
            if response.status_code == 200:
                data_list = response.json()
                if data_list and len(data_list) > 0:
                    # 成功获取到数据，开始解析
                    details = []
                    for html_row in data_list:
                        row_soup = BeautifulSoup(html_row, 'html.parser')
                        tds = row_soup.find_all('td')
                        if len(tds) >= 4:
                            home_water = tds[0].get_text(strip=True)
                            handicap = tds[1].get_text(strip=True)
                            away_water = tds[2].get_text(strip=True)
                            update_time = tds[3].get_text(strip=True)
                            details.append(f"  [{update_time}] 上:{home_water:<6} 盘:{handicap:<8} 下:{away_water:<6}")
                    return details
            
            # 如果代码执行到这里，说明返回了空数据或 code 不对
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取亚盘详情为空，正在重试...")
            
        except Exception as e:
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取亚盘详情，网络错误: {e}")

        # 重试前的等待：基础 0.5 秒 + 随机 0.5 秒，模拟真人点击间隔
        time.sleep(0.5 + random.random())
    
    return [] # 超过最大重试次数依然无果，返回空

# 获取“大小指数”页面数据
def get_daxiao_detail(fid, comp_id, max_retries=15):
    """
    获取具体机构的大小球盘口变动详情，带重试机制
    :param fid: 比赛 ID
    :param comp_id: 机构 ID
    :param max_retries: 最大重试次数
    """
    t = int(time.time() * 1000)
    ajax_url = f"https://odds.500.com/fenxi1/inc/daxiaoajax.php?fid={fid}&id={comp_id}&t={t}"
    headers = {
        'User-Agent': USERAGENT,
        'Referer': f'https://odds.500.com/fenxi/daxiao-{fid}.shtml',
        'X-Requested-With': 'XMLHttpRequest'
    }
    for i in range(max_retries):
        try:
            # 增加超时控制，防止死等
            response = requests.get(ajax_url, headers=headers, timeout=5)
            if response.status_code == 200:
                data_list = response.json()
                if data_list and len(data_list) > 0:
                    # 成功获取到数据，开始解析
                    details = []
                    for html_row in data_list:
                        row_soup = BeautifulSoup(html_row, 'html.parser')
                        tds = row_soup.find_all('td')
                        if len(tds) >= 4:
                            details.append(f"  [{tds[3].get_text(strip=True)}] 大:{tds[0].get_text(strip=True):<6} 盘:{tds[1].get_text(strip=True):<8} 小:{tds[2].get_text(strip=True):<6}")
                    return details
            # 如果代码执行到这里，说明返回了空数据或 code 不对
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取大小球盘详情为空，正在重试...")


        except Exception as e:
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取大小球盘详情，网络错误: {e}")

        # 重试前的等待：基础 0.5 秒 + 随机 0.5 秒，模拟真人点击间隔
        time.sleep(0.5 + random.random())

    return [] # 超过最大重试次数依然无果，返回空

# 获取“百家欧赔”页面数据
def get_ouzhi_detail(fid, comp_id, data_time, max_retries=15):
    """
    获取具体机构的欧赔变动详情，带重试机制
    :param fid: 比赛 ID
    :param comp_id: 机构 ID
    :param data-time: 机构特定的更新时间
    :param max_retries: 最大重试次数
    """
    # 构造参数
    t_ms = int(time.time() * 1000)
    # 500网要求时间格式中的空格转为 + 号
    formatted_time = data_time.replace(' ', '+')
    
    # 这里的 _ 是时间戳，time 是格式化的时间字符串
    ajax_url = f"https://odds.500.com/fenxi1/json/ouzhi.php?_={t_ms}&fid={fid}&cid={comp_id}&r=1&time={formatted_time}&type=europe" # europe是欧赔，kelly是凯利
    
    headers = {
        'User-Agent': USERAGENT,
        'Referer': f'https://odds.500.com/fenxi/ouzhi-{fid}.shtml',
        'X-Requested-With': 'XMLHttpRequest'
    }

    for i in range(max_retries):
        try:
            # 增加超时控制，防止死等
            response = requests.get(ajax_url, headers=headers, timeout=5)
            # 如果状态码正常且返回内容不是空的 []
            if response.status_code == 200:
                data_list = response.json()
                if data_list and len(data_list) > 0:
                    # 成功获取到数据，开始解析
                    details = []
                    # 数据结构: [胜, 平, 负, 返还率, 更新时间, ...]
                    for item in data_list:
                        if len(item) >= 5:
                            win = item[0]
                            draw = item[1]
                            loss = item[2]
                            update_time = item[4]
                            details.append(f"  [{update_time}] 胜:{win:<6} 平:{draw:<6} 负:{loss:<6}")
                    return details
            # 如果代码执行到这里，说明返回了空数据或 code 不对
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取欧赔详情为空，正在重试...")

        except Exception as e:
            print(f"  [ID:{comp_id}] 第 {i+1} 次尝试获取欧赔详情，网络错误: {e}")

        # 重试前的等待：基础 0.5 秒 + 随机 0.5 秒，模拟真人点击间隔
        time.sleep(0.5 + random.random())

    return [] # 超过最大重试次数依然无果，返回空

# 获取单场比赛“亚盘、大小球、让球、欧赔”维度数据
def process_single_match(fid, league, home, away, m_time, folder_path):
    """
    :param fid: 比赛 ID
    :param league: 联赛信息
    :param home: 主队
    :param away: 客队
    :param m_time: 赛事时间
    :param folder_path: 单场比赛数据存入单个文件
    """
    # 构造专属文件名：[18-30]英超_阿森纳VS曼联.txt (取时间的分秒部分)
    time_short = m_time.split(' ')[1].replace(':', '-')
    # 构造绝对路径文件夹
    full_folder_path = os.path.join(BASE_DIR, folder_path, f"[{time_short}]{league}_{home}VS{away}")

    if not os.path.exists(full_folder_path):
        os.makedirs(full_folder_path)
        print(f"已创建文件夹: {full_folder_path}")
    
    file_name_h = f"[{time_short}]{league}_{home}VS{away}_历史数据.txt"
    file_name_h = sanitize_filename(file_name_h)
    file_path_h = os.path.join(full_folder_path, file_name_h)

    file_name_y = f"[{time_short}]{league}_{home}VS{away}_亚盘.txt"
    file_name_y = sanitize_filename(file_name_y)
    file_path_y = os.path.join(full_folder_path, file_name_y)

    file_name_o = f"[{time_short}]{league}_{home}VS{away}_欧赔.txt"
    file_name_o = sanitize_filename(file_name_o)
    file_path_o = os.path.join(full_folder_path, file_name_o)

    file_name_s = f"[{time_short}]{league}_{home}VS{away}_大小球.txt"
    file_name_s = sanitize_filename(file_name_s)
    file_path_s = os.path.join(full_folder_path, file_name_s)

    file_name_r = f"[{time_short}]{league}_{home}VS{away}_让球.txt"
    file_name_r = sanitize_filename(file_name_r)
    file_path_r = os.path.join(full_folder_path, file_name_r)

    headers = {'User-Agent': USERAGENT}
    
    # 写入历史数据文件
    with open(file_path_h, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
        f.write(f"{'='*60}\n")

        # --- 第零部分：数据分析 ---
        handle_data_analysis_section(fid, f, headers)
        f.write("\n\n")
        print(f"  [完成] 数据已存至: {file_path_h}")

    # 写入亚盘文件
    with open(file_path_y, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
        f.write(f"{'='*60}\n")

        # --- 第一部分：处理亚盘 ---
        f.write("\n【 亚盘指数变动 】\n")
        yazhi_url = f"https://odds.500.com/fenxi/yazhi-{fid}.shtml"
        try:
            y_res = requests.get(yazhi_url, headers=headers, timeout=5)
            y_res.encoding = 'gbk'
            y_soup = BeautifulSoup(y_res.text, 'lxml')
            y_table = y_soup.find('table', id='datatb')
            if y_table:
                rows = y_table.find_all('tr', id=True)
                for tr in rows:
                    cid = tr.get('id')
                    if cid in TARGET_COMPANIES:
                        f.write(f"  机构: {TARGET_COMPANIES[cid]}\n")
                        history = get_yazhi_detail(fid, cid)
                        f.write("\n".join(history) + "\n" if history else "    (多次尝试该机构暂无亚盘历史变动数据)\n")
                        f.write("  " + "-"*50 + "\n")
            else:
                f.write("  未在页面找到亚盘盘口数据表 table#datatb\n")
        except Exception as e:
            f.write(f"  亚盘对比页面访问异常: {e}\n")
        
        f.write("\n\n")
        print(f"  [完成] 数据已存至: {file_name_y}")
    
    # 写入欧赔文件
    with open(file_path_o, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
        f.write(f"{'='*60}\n")

        # --- 第四部分：处理欧赔 ---
        f.write("\n【 欧赔指数变动 】\n")
        ouzhi_url = f"https://odds.500.com/fenxi/ouzhi-{fid}.shtml"
        try:
            o_res = requests.get(ouzhi_url, headers=headers, timeout=5)
            o_res.encoding = 'gbk'
            o_soup = BeautifulSoup(o_res.text, 'lxml')
            o_table = o_soup.find('table', id='datatb')
            if o_table:
                # 找到页面上所有的机构行
                rows = o_table.find_all('tr', id=True)
                for tr in rows:
                    # 500网欧赔页面的id有时带有 tr_ 前缀，需要清洗
                    raw_id = tr.get('id')
                    cid = raw_id.replace('tr_', '').replace('tr', '')

                    # 【关键逻辑】：提取该机构在页面上显示的最后更新时间
                    row_data_time = tr.get('data-time')
                    
                    if cid in TARGET_COMPANIES and row_data_time:
                        f.write(f"  机构: {TARGET_COMPANIES[cid]} (最近更新: {row_data_time})\n")

                        # 传入从 HTML 属性中拿到的 row_data_time
                        history = get_ouzhi_detail(fid, cid, row_data_time)
                        f.write("\n".join(history) + "\n" if history else "    (多次尝试该机构暂无欧赔历史变动数据)\n")
                        f.write("  " + "-"*50 + "\n")
            else:
                f.write("  未在页面找到欧赔数据表 table#datatb\n")
        except Exception as e:
            f.write(f"  百家欧赔页面访问异常: {e}\n")
        
        f.write("\n\n")
        print(f"  [完成] 数据已存至: {file_name_o}")
   
    # 写入大小球文件
    with open(file_path_s, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
        f.write(f"{'='*60}\n")

        # --- 第二部分：处理大小球 ---
        f.write("\n【 大小球指数变动 】\n")
        daxiao_url = f"https://odds.500.com/fenxi/daxiao-{fid}.shtml"
        try:
            d_res = requests.get(daxiao_url, headers=headers, timeout=5)
            d_res.encoding = 'gbk'
            d_soup = BeautifulSoup(d_res.text, 'lxml')
            d_table = d_soup.find('table', id='datatb')
            if d_table:
                rows = d_table.find_all('tr', id=True)
                for tr in rows:
                    cid = tr.get('id')
                    if cid in TARGET_COMPANIES:
                        f.write(f"  机构: {TARGET_COMPANIES[cid]}\n")
                        history = get_daxiao_detail(fid, cid)
                        f.write("\n".join(history) + "\n" if history else "    (多次尝试该机构暂无大小球盘历史变动数据)\n")
                        f.write("  " + "-"*50 + "\n")
            else:
                f.write("  未在页面找到大小球盘口数据表 table#datatb\n")
        except Exception as e:
            f.write(f"  大小指数页面访问异常: {e}\n")
        
        f.write("\n\n")
        print(f"  [完成] 数据已存至: {file_name_s}")

    # 写入让球文件
    with open(file_path_r, 'w', encoding='utf-8') as f:
        f.write(f"{'='*60}\n")
        f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
        f.write(f"{'='*60}\n")

        # --- 第三部分：处理让球 ---
        handle_rangqiu_section(fid, f, headers)
        f.write("\n\n")
        print(f"  [完成] 数据已存至: {file_name_r}")

# 获取所有比赛的“亚盘、大小球、让球、欧赔”数据
def scrape_500_full_data(start_dt, end_dt, target_fids=None):
    """
    根据时间范围对比赛进行筛选
    :param start_dt: 范围起始时间
    :param end_dt: 范围结束时间
    :param target_fids: 指定的比赛 ID 列表 (list)
    """
    headers = {'User-Agent': USERAGENT}
    
    try:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] 正在连接 500.com 赛事列表...")
        res = requests.get(BASE_URL, headers=headers, timeout=10)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'lxml')
        match_rows = soup.select('table.bet-tb-dg tr.bet-tb-tr')

        if not match_rows:
            print("未找到比赛数据，请检查网络或 URL 是否有效。")
            return
        
        # --- 新增：创建本次运行的专属文件夹 ---
        dir_name = f"analysis_{time.strftime('%Y%m%d_%H%M%S')}"
        full_folder_path = os.path.join(BASE_DIR, dir_name)
        if not os.path.exists(full_folder_path):
            os.makedirs(full_folder_path)
            print(f"已创建文件夹: {full_folder_path}")

        seen_ids = set()
        count = 0

        file_path_all = os.path.join(BASE_DIR, dir_name, '全部赛事信息.txt')
        with open(file_path_all, 'w', encoding='utf-8') as f:
            for row in match_rows:
                # 去重逻辑
                fid = row.get('data-fixtureid')
                if not fid or fid in seen_ids:
                    continue # 如果 ID 已存在或为空，跳过此行

                # 提取联赛名并过滤 (增加 strip 防止空格干扰)
                league = row.get('data-simpleleague', '未知联赛').strip()
                # 提取比赛日期和时间
                home = row.get('data-homesxname', '未知主队')
                away = row.get('data-awaysxname', '未知客队')
                m_date = row.get('data-matchdate')
                m_time = row.get('data-matchtime')
                # 将比赛时间转为对象
                match_dt_str = f"{m_date} {m_time}".strip()
                
                # 解析时间用于范围判断
                current_match_dt = None
                try:
                    if m_date and m_time:
                        current_match_dt = datetime.strptime(match_dt_str, "%Y-%m-%d %H:%M")
                except:
                    pass

                # --- 筛选逻辑开始 ---
                should_scrape = False
                if target_fids:
                    # 如果指定了 FID 列表，只抓取列表内的 ID，忽略日期和联赛过滤
                    if fid in target_fids:
                        should_scrape = True
                else: 
                    # 按联赛和时间范围过滤
                    league_match = True
                    if TARGET_LEAGUES and not any(name in league for name in TARGET_LEAGUES):
                        league_match = False
                    
                    time_match = True
                    # --- 时间范围筛选逻辑 ---
                    if start_dt and end_dt:
                        # 包含结束时间点
                        if not current_match_dt or not (start_dt <= current_match_dt <= end_dt):
                            time_match = False
                    
                    if league_match and time_match:
                        should_scrape = True
                # --- 筛选逻辑结束 ---

                # 执行抓取
                if should_scrape:
                    seen_ids.add(fid)
                    
                    f.write(f"{'='*60}\n")
                    f.write(f"{league} | 比赛时间: {m_time} | {home} VS {away} | ID: {fid}\n")
                    f.write(f"{'='*60}\n")
                    f.write("Whoscored赛事网址：\n\n")
                    f.write("Transfermarkt赛事网址：\n\n")
                    f.write("Whoscored预计阵容：\n")
                    f.write("主队阵容：\n\n")
                    f.write("客队阵容：\n\n")                    
                    f.write("Transfermarkt伤停信息：\n")
                    f.write("主队伤停：\n\n")
                    f.write("客队伤停：\n\n")
                    f.write("-"*60 + "\n")
                    f.write("\n\n")                    
                    print(f"正在获取: [{match_dt_str}] {home} VS {away} 的亚盘、大小球、让球、欧赔信息")
                    # 调用单场处理函数
                    process_single_match(fid, league, home, away, match_dt_str, dir_name)
                    count += 1
                    # 礼貌性停顿，防止被封 IP
                    time.sleep(random.uniform(1.5, 3.0))
            
            if count == 0:
                print(f"未匹配到任何比赛。")
            else:
                print(f"\n任务完成！共处理 {count} 场比赛，存入: {dir_name}")

        print(f"\n所有比赛信息已写入全部赛事信息.txt")

    except Exception as e:
        import traceback
        print(f"[错误] 比赛数据获取程序意外中断: {e}")
        traceback.print_exc() # 打印具体的错误堆栈，方便调试

def main():
    parser = argparse.ArgumentParser(description="500彩票网数据采集工具")
    # 设计参数 --range，接收如 "2026-01-10 00:00~2026-01-11 04:00"
    parser.add_argument('--range', type=str, help='时间范围。格式: "开始" 或 "开始~结束"')
    # 设计参数 --fids, 接收如 "1222857,1199642,1205939,1199645,1202542,1216016"
    parser.add_argument('--fids', type=str, help='指定比赛 ID 列表，逗号分隔。例如: 1222857,1199642')

    args = parser.parse_args()

    # 1. 解析时间范围
    start_dt = None
    end_dt = None
    if args.range:
        if '~' in args.range:
            # 情况 1: 用户传了 "开始~结束"
            parts = args.range.split('~')
            start_dt = parse_custom_time(parts[0])
            end_dt = parse_custom_time(parts[1])
        else:
            # 情况 2: 用户只传了 "开始"
            start_dt = parse_custom_time(args.range)
            # 设置一个极大的结束时间，代表“之后所有”
            end_dt = datetime(9999, 12, 31, 23, 59)

        if start_dt and end_dt:
            print(f"筛选区间: {start_dt} 之后的所有比赛" if end_dt.year == 9999 
                  else f"筛选区间: {start_dt} 至 {end_dt}")
    
    # 解析比赛id
    target_fids = None
    if args.fids:
        # 将 "123,456" 转换为 ["123", "456"]
        target_fids = [fid.strip() for fid in args.fids.split(',')]
        print(f"指定抓取 赛事ID 模式: {target_fids}")

    scrape_500_full_data(start_dt, end_dt, target_fids=target_fids)

if __name__ == "__main__":
    main()
