# pip3 install requests beautifulsoup4 lxml
# python3 500.py --range "2026-01-10~2026-01-10 23:59" 参数加双引号

import requests
from bs4 import BeautifulSoup
import time
import random
import argparse
from datetime import datetime

# 请求时的通用User_Agent
USERAGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36"

# 配置目标机构 ID 和名称
TARGET_COMPANIES = {
    "1055": "平博",
    "280": "皇冠",
    "293": "威廉希尔",
    "2": "立博",
    "5": "澳门",
    "9": "易胜博",
    "3": "Bet365"
}

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

# 获取单场比赛“亚盘、大小球、欧赔”维度数据
def process_single_match(fid, league, home, away, m_time, f):
    """
    :param fid: 比赛 ID
    :param league: 联赛信息
    :param home: 主队
    :param away: 客队
    :param m_time: 赛事时间
    :param f: 文件描述符，用于文件写入
    """
    headers = {'User-Agent': USERAGENT}
    
    f.write(f"{'='*60}\n")
    f.write(f"{league} | 北京时间: {m_time} | {home} VS {away}\n") #  | ID: {fid}
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
    
    # --- 第三部分：处理欧赔 ---
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

# 获取所有比赛的“亚盘、大小球、欧赔”数据
def scrape_500_full_data(start_dt, end_dt):
    """
    根据时间范围对比赛进行筛选
    :param start_dt: 范围起始时间
    :param end_dt: 范围结束时间
    """
    base_url = "https://trade.500.com/jczq/"
    headers = {'User-Agent': USERAGENT}
    
    try:
        print("开始获取赛事列表...")
        res = requests.get(base_url, headers=headers)
        res.encoding = 'gbk'
        soup = BeautifulSoup(res.text, 'lxml')
        match_rows = soup.select('table.bet-tb-dg tr.bet-tb-tr')

        if not match_rows:
            print("未找到比赛数据。")
            return

        seen_ids = set()
        filename = f"football_500_analysis_{time.strftime('%Y%m%d_%H%M%S')}.txt"

        count = 0

        with open(filename, 'w', encoding='utf-8') as f:
            for row in match_rows:
                # 提取比赛日期和时间
                m_date = row.get('data-matchdate')
                m_time = row.get('data-matchtime')
                if not m_date or not m_time: continue

                # 将比赛时间转为对象
                match_dt = datetime.strptime(f"{m_date} {m_time}", "%Y-%m-%d %H:%M")

                # --- 时间范围筛选逻辑 ---
                if start_dt and end_dt:
                    # 包含结束时间点
                    if not (start_dt <= match_dt <= end_dt):
                        continue

                fid = row.get('data-fixtureid')
                # --- 去重逻辑 ---
                if not fid or fid in seen_ids:
                    continue # 如果 ID 已存在或为空，跳过此行
                seen_ids.add(fid)
              
                league = row.get('data-simpleleague', '未知联赛')
                home = row.get('data-homesxname', '未知主队')
                away = row.get('data-awaysxname', '未知客队')
                # m_time = f"{row.get('data-matchdate', '')} {row.get('data-matchtime', '')}"

                print(f"正在获取: [{match_dt}] {home} VS {away} 的亚盘、大小球、欧赔信息")
                # 调用单场处理函数
                process_single_match(fid, league, home, away, match_dt.strftime('%Y-%m-%d %H:%M'), f)
                count += 1
                # 礼貌性停顿，防止被封 IP
                time.sleep(random.uniform(1.0, 2.0))
        
        print(f"\n任务完成，共{count}场比赛，数据已保存至：{filename}")

    except Exception as e:
        print(f"[错误] 比赛数据获取程序意外中断: {e}")

def main():
    parser = argparse.ArgumentParser(description="500彩票网时间范围采集工具")
    # 设计参数 --range，接收如 "2026-01-10 00:00~2026-01-11 04:00"
    parser.add_argument('--range', type=str, help='时间范围。格式: "开始" 或 "开始~结束"')
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

    scrape_500_full_data(start_dt, end_dt)

if __name__ == "__main__":
    main()
