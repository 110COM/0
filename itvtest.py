import os
import re
import time
import asyncio
import aiohttp
import concurrent.futures
import subprocess
import json
import requests


# 功能1 - 检测有效直播源、测速、排序

channels = []
error_channels = []
results = []

current_folder = os.path.dirname(os.path.abspath(__file__))
itv_file_path = os.path.join(current_folder, 'itv.txt')

# 读取频道信息
with open(itv_file_path, 'r', encoding='utf-8') as file:
    for line in file:
        line = line.strip()
        if line and ',' in line:
            try:
                channel_name, channel_url = line.split(',')
                channels.append((channel_name.strip(), channel_url.strip()))
            except ValueError:
                continue

# 异步下载函数
async def download(channel_name, channel_url):
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(channel_url) as response:
                if response.status == 200:
                    content = await response.read()
                    file_size = len(content)
                    response_time = response.content.total_bytes / 1024 / 1024  # response_time in MB
                    download_speed = file_size / response_time / 1024
                    normalized_speed = min(max(download_speed / 1024, 0.001), 100)
                    result = channel_name, channel_url, f"{normalized_speed:.3f} MB/s"
                    results.append(result)
                    numberx = (len(results) + len(error_channels)) / len(channels) * 100
                    print(f"可用频道：{len(results)} 个 , 不可用频道：{len(error_channels)} 个 , 总频道：{len(channels)} 个 ,总进度：{numberx:.2f} %。")
                else:
                    error_channel = channel_name, channel_url
                    error_channels.append(error_channel)
    except Exception as e:
        error_channel = channel_name, channel_url
        error_channels.append(error_channel)
        numberx = (len(results) + len(error_channels)) / len(channels) * 100
        print(f"可用频道：{len(results)} 个 , 不可用频道：{len(error_channels)} 个 , 总频道：{len(channels)} 个 ,总进度：{numberx:.2f} %。")

# 执行异步任务
async def main():
    tasks = [download(channel_name, channel_url) for channel_name, channel_url in channels]
    await asyncio.gather(*tasks)

# 运行异步任务
asyncio.run(main())

# 对频道进行排序
def channel_key(channel_name):
    match = re.search(r'\d+', channel_name)
    if match:
        return int(match.group())
    else:
        return float('inf')  # 返回一个无穷大的数字作为关键字

results.sort(key=lambda x: (x[0], -float(x[2].split()[0])))
results.sort(key=lambda x: channel_key(x[0]))

# 将结果写入文件
itv_results_file_path = os.path.join(current_folder, "itv_results.txt")
with open(itv_results_file_path, 'w', encoding='utf-8') as file:
    for result in results:
        channel_name, channel_url, speed = result
        file.write(f"{channel_name},{channel_url},{speed}\n")

itv_speed_file_path = os.path.join(current_folder, "itv_speed.txt")
with open(itv_speed_file_path, 'w', encoding='utf-8') as file:
    for result in results:
        channel_name, channel_url, speed = result
        file.write(f"{channel_name},{channel_url}\n")





# 功能2 - 检测分辨率，并删除1080P以下分辨率直播源
CONNECTION_LIMIT = 1000

def get_resolution(name, url, timeout=10):
    process = None
    try:
        response = requests.get(url, timeout=timeout)
        if response.status_code == 200:
            # 使用ffprobe获取视频信息
            cmd = ['ffprobe', '-print_format', 'json', '-show_streams', '-select_streams', 'v', url]
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
            stdout, stderr = process.communicate(timeout=timeout)  # 设置超时时间
            # 解析ffprobe输出的JSON格式信息
            info = json.loads(stdout.decode())
            width = int(info['streams'][0]['width'])
            height = int(info['streams'][0]['height'])
            if width >= 1920 and height >= 1080:
                return name, url
    except subprocess.TimeoutExpired:
        process.kill()  # 超时则终止进程
    except Exception as e:
        pass  # 不输出异常信息
    finally:
        if process:
            process.wait()  # 等待子进程执行完毕
    return None

def process_urls(input_file, output_file):
    urls = []
    names = []
    with open(input_file, 'r', encoding='utf-8') as file:
        for line in file:
            line = line.strip()
            # 跳过包含多个逗号的行
            if ',' not in line or line.count(',') > 1:
                continue
            name, url = line.split(',', 1)
            names.append(name)
            urls.append(url)

    total_tasks = len(urls)
    completed_tasks = 0
    valid_tasks = 0  # 有效数据数量
    valid_urls = []

    start_time = time.time()
    print(f"开始时间: {time.strftime('%H:%M:%S')}")

    with concurrent.futures.ThreadPoolExecutor(max_workers=10) as executor:
        futures = []
        for name, url in zip(names, urls):
            future = executor.submit(get_resolution, name, url, timeout=15)  # 设置任务超时时间为15秒
            futures.append(future)

        for future in concurrent.futures.as_completed(futures):
            result = future.result()
            completed_tasks += 1
            # 打印执行进度
            progress = completed_tasks / total_tasks * 100
            print(f"已检测量: {completed_tasks}/{total_tasks}, 完成百分比: {progress:.2f}%, 有效数据数量: {valid_tasks}", end='\r', flush=True)
            if result:
                valid_tasks += 1  # 有效数据数量增加
                valid_urls.append(result)

    end_time = time.time()
    print(f"\n结束时间: {time.strftime('%H:%M:%S')}")

    with open(output_file, 'w', encoding='utf-8') as file:
        for name, url in valid_urls:
            file.write(f"{name},{url}\n")

    print(f"已完成！！！ {output_file}")
    print(f"总用时: {end_time - start_time:.2f} seconds")


if __name__ == "__main__":
    current_directory = os.path.dirname(os.path.abspath(__file__))
    input_file_path = os.path.join(current_directory, "itv_speed.txt")
    output_file_path = os.path.join(current_directory, "高清.txt")

    process_urls(input_file_path, output_file_path)
	
	
	
	


# 功能 - 3：生成 全部.txt
# 获取当前脚本所在文件夹路径
current_folder = os.path.dirname(os.path.abspath(__file__))
file_path = os.path.join(current_folder, '高清.txt')

# 定义要分类的列表
cctv_channels = []
other_channels = []
satellite_channels = []

# 尝试不同的编码格式打开文件
encodings = ['utf-8', 'gbk', 'iso-8859-1']
for encoding in encodings:
    try:
        # 读取文件并分类
        with open(file_path, 'r', encoding=encoding) as file:
            lines = file.readlines()
            for line in lines:
                name, url = line.strip().split(',')
                channel_name = name.split(' ')[0]  # 获取频道名字，即逗号前的名字
                if 'CCTV' in channel_name:
                    cctv_channels.append((name, url))
                elif '卫视' in channel_name:
                    satellite_channels.append((name, url))
                else:
                    other_channels.append((name, url))

        # 如果成功打开文件并读取内容，则跳出循环
        break
    except UnicodeDecodeError:
        # 如果使用当前编码格式解码文件内容失败，则尝试下一个编码格式
        continue

# 对 cctv_channels 进行排序
cctv_channels.sort(key=lambda x: (int(re.search(r'\d+', x[0]).group()) if 'CCTV' in x[0] and re.search(r'\d+', x[0]) else float('inf'), x[0] != 'CCTV5'))

# 对 satellite_channels 中相同名字的频道进行分组，并限制每个相同名称的频道不超过5个
satellite_channels_dict = {}
for name, url in satellite_channels:
    prefix = name.split(' ')[0]
    if prefix in satellite_channels_dict:
        satellite_channels_dict[prefix].append((name, url))
    else:
        satellite_channels_dict[prefix] = [(name, url)]

# 对 satellite_channels 进行排序
satellite_channels_sorted = []
for prefix in sorted(satellite_channels_dict.keys()):
    satellite_channels_sorted.extend(satellite_channels_dict[prefix])

# 对 other_channels 中相同名字的频道进行分组，并限制每个相同名称的频道不超过5个
other_channels_dict = {}
for name, url in other_channels:
    prefix = name.split(' ')[0]
    if prefix in other_channels_dict:
        other_channels_dict[prefix].append((name, url))
    else:
        other_channels_dict[prefix] = [(name, url)]

# 对 other_channels 进行排序
other_channels_sorted = []
for prefix in sorted(other_channels_dict.keys()):
    other_channels_sorted.extend(other_channels_dict[prefix])


# 将分类结果保存到文件
output_file_path_all = os.path.join(current_folder, '全部.txt')
with open(output_file_path_all, 'w', encoding='utf-8') as output_file:
    output_file.write("央视频道,#genre#\n")
    for name, url in cctv_channels:
        output_file.write(f"{name},{url}\n")

    output_file.write("\n卫视频道,#genre#\n")
    for name, url in satellite_channels_sorted:
        output_file.write(f"{name},{url}\n")

    output_file.write("\n其它,#genre#\n")
    for name, url in other_channels_sorted:
        output_file.write(f"{name},{url}\n")

print("2.已生成：全部.txt")

# 新生成一个已整理.txt文件，其中每个相同的频道名称数量不超过 7-7-4个
output_file_path_arranged = os.path.join(current_folder, '已整理.txt')
with open(output_file_path_arranged, 'w', encoding='utf-8') as output_file:
    output_file.write("央视频道,#genre#\n")
    count_per_name = {}
    for name, url in cctv_channels:
        prefix = name.split(' ')[0]
        count_per_name[prefix] = count_per_name.get(prefix, 0) + 1
        if count_per_name[prefix] <= 7:  # 限制央视每个相同名称的频道不超过7个
            output_file.write(f"{name},{url}\n")

    output_file.write("\n卫视频道,#genre#\n")
    count_per_name = {}
    for name, url in satellite_channels_sorted:
        prefix = name.split(' ')[0]
        count_per_name[prefix] = count_per_name.get(prefix, 0) + 1
        if count_per_name[prefix] <= 7:  # 限制卫视每个相同名称的频道不超过7个
            output_file.write(f"{name},{url}\n")

    output_file.write("\n其它,#genre#\n")
    count_per_name = {}
    for name, url in other_channels_sorted:
        prefix = name.split(' ')[0]
        count_per_name[prefix] = count_per_name.get(prefix, 0) + 1
        if count_per_name[prefix] <= 4:  # 限制其它每个相同名称的频道不超过4个
            output_file.write(f"{name},{url}\n")

print("3.已生成：已整理.txt")






# 功能 -3：生成 已整理.m3u
# 获取当前脚本文件所在的目录
current_folder = os.path.dirname(os.path.abspath(__file__))

# 输入文件路径
input_file_path = os.path.join(current_folder, "已整理.txt")
# 输出文件路径
output_file_path = os.path.join(current_folder, "已整理.m3u")

# 规则字典，根据频道名中的关键词确定所属分组
rules = {
    "CCTV": "央视频道",
    "卫视": "卫视频道",
    "测试": "测试频道"
}

# 创建新的m3u文件并写入数据
with open(input_file_path, 'r', encoding='utf-8') as input_file, open(output_file_path, 'w', encoding='utf-8') as output_file:
    output_file.write('#EXTM3U\n')  # 写入第一行
    channel_counters = {}
    skip_lines = {"央视频道,#genre#", "卫视频道,#genre#", "其它,#genre#"}
    for line in input_file:
        line = line.strip()
        if line and line not in skip_lines:  # 如果行不为空且不是跳过的分类行
            parts = line.split(',')  # 假设每行的格式是：频道名,频道URL[,速度]
            channel_name = parts[0]
            channel_url = parts[1]
            speed = parts[2] if len(parts) > 2 else ''  # 如果有速度字段则提取，否则设为空字符串
            group_title = None
            for keyword, group in rules.items():
                if keyword in channel_name:
                    group_title = group
                    break
            if group_title:  # 如果频道名在规则字典中
                if channel_name in channel_counters:
                    channel_counters[channel_name] += 1
                else:
                    channel_counters[channel_name] = 1
                output_file.write(f"#EXTINF:-1 group-title=\"{group_title}\",{channel_name}\n")
                output_file.write(f"{channel_url}\n")
            else:
                output_file.write(f"#EXTINF:-1 group-title=\"其他频道\",{channel_name}\n")
                output_file.write(f"{channel_url}\n")


print("4.已生成：已整理.m3u")





# 获取当前脚本文件所在的目录
current_folder = os.path.dirname(os.path.abspath(__file__))

# 输入文件路径
input_file_path = os.path.join(current_folder, "已整理.txt")
# 输出文件路径
output_file_path = os.path.join(current_folder, "央视.txt")

# 读取已整理.txt文件并截取信息
with open(input_file_path, 'r', encoding='utf-8') as input_file, open(output_file_path, 'w', encoding='utf-8') as output_file:
    # 找到分割点
    for line in input_file:
        if '卫视频道,#genre#' in line:
            break
        output_file.write(line)

# 打印已生成的央视.txt
print("5.已生成：央视.txt")




# 获取当前脚本文件所在的目录
current_folder = os.path.dirname(os.path.abspath(__file__))

# 输入文件路径
input_file_path = os.path.join(current_folder, "央视.txt")
# 输出文件路径
output_file_path = os.path.join(current_folder, "央视.m3u")

# 创建新的m3u文件并写入数据
with open(input_file_path, 'r', encoding='utf-8') as input_file, open(output_file_path, 'w', encoding='utf-8') as output_file:
    output_file.write('#EXTM3U\n')  # 写入第一行
    channel_counters = {}
    for line in input_file:
        line = line.strip()
        if line and '央视频道,#genre#' not in line:  # 如果行不为空且不包含指定行
            parts = line.split(',')  # 假设每行的格式是：频道名,频道URL[,速度]
            channel_name = parts[0]
            channel_url = parts[1]
            speed = parts[2] if len(parts) > 2 else ''  # 如果有速度字段则提取，否则设为空字符串
            group_title = "央视频道"  # 默认分组标题为央视频道
            if channel_name in channel_counters:
                channel_counters[channel_name] += 1
            else:
                channel_counters[channel_name] = 1
            output_file.write(f"#EXTINF:-1 group-title=\"{group_title}\",{channel_name}\n")
            output_file.write(f"{channel_url}\n")

# 打印已生成的央视.m3u
print("6.已生成：央视.m3u")
print("---------------------------全部完成")	
