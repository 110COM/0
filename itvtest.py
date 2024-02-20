import os
import re
import time
import asyncio
import aiohttp
import concurrent.futures
import subprocess
import json
import requests
import threading
import logging


from queue import Queue

# 线程安全的队列，用于存储下载任务
task_queue = Queue()

# 线程安全的列表，用于存储结果
results = []
channels = []
error_channels = []




# 读取频道信息
channels = []
with open('itv.txt', 'r', encoding='utf-8') as file:
    for line in file:
        line = line.strip()
        if line and ',' in line:
            try:
                channel_name, channel_url = line.split(',')
                channels.append((channel_name.strip(), channel_url.strip()))
                # 输出获取到的频道信息
                print(f"Channel Name: {channel_name.strip()}, Channel URL: {channel_url.strip()}")
            except ValueError:
                continue



# Function to get resolution using ffprobe
def get_resolution(name, url, timeout=10):
    process = None
    try:
        cmd = ['ffprobe', '-print_format', 'json', '-show_streams', '-select_streams', 'v', url]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=timeout)
        info = json.loads(stdout.decode())
        width = int(info['streams'][0]['width'])
        height = int(info['streams'][0]['height'])
        if width >= 1920 and height >= 1080:
            return name, url
    except subprocess.TimeoutExpired:
        process.kill()
    except Exception as e:
        pass
    finally:
        if process:
            process.wait()
    return None

def worker():
    while True:
        channel_name, channel_url = task_queue.get()
        try:
            resolution_info = get_resolution(channel_name, channel_url, timeout=15)
            if resolution_info:
                results.append(resolution_info)
        except Exception as e:
            error_channels.append((channel_name, channel_url))
        task_queue.task_done()




# Number of worker threads
num_threads = 10
for _ in range(num_threads):
    t = threading.Thread(target=worker, daemon=True)
    t.start()

# Add download tasks to the queue
for channel in channels:
    task_queue.put(channel)

# Wait for all tasks to complete
task_queue.join()



# 对结果进行排序和合并
sorted_results = sorted(results, key=lambda x: (int(re.search(r'\d+', x[0]).group()) if re.search(r'\d+', x[0]) else float('inf'), x[0] != 'CCTV5'))

# 分类频道
cctv_channels = []
satellite_channels = []
other_channels = []

for channel_name, channel_url in sorted_results:
    if 'CCTV' in channel_name:
        cctv_channels.append((channel_name, channel_url))
    elif '卫视' in channel_name:
        satellite_channels.append((channel_name, channel_url))
    else:
        other_channels.append((channel_name, channel_url))



# 对CCTV频道进行合并、排序、限制数量
#cctv_channels.sort(key=lambda x: int(re.search(r'\d+', x[0]).group()) if re.search(r'\d+', x[0]) else float('inf'))

cctv_merged = []
channel_counters = {}
result_counter = 7  # 每个频道需要的个数

for channel_name, channel_url in cctv_channels:
   if channel_name in channel_counters:
       if channel_counters[channel_name] >= result_counter:
           continue
       else:
           cctv_merged.append((channel_name, channel_url))
           channel_counters[channel_name] += 1
   else:
       cctv_merged.append((channel_name, channel_url))
       channel_counters[channel_name] = 1


# 对卫视频道进行合并、排序、限制数量
satellite_merged = {}
channel_counters = {}
result_counter = 7  # 每个频道需要的个数

for channel_name, channel_url in satellite_channels:
    prefix = channel_name.split(' ')[0]
    if prefix in satellite_merged:
        if channel_name not in channel_counters:
            channel_counters[channel_name] = 0

        if channel_counters[channel_name] < result_counter:
            satellite_merged[prefix].append((channel_name, channel_url))
            channel_counters[channel_name] += 1
    else:
        satellite_merged[prefix] = [(channel_name, channel_url)]
        channel_counters[channel_name] = 1

    
# 对其他频道进行合并和排序
other_merged = {}
channel_counters = {}
result_counter = 4  # 每个频道需要的个数

for channel_name, channel_url in other_channels:
    prefix = channel_name.split(' ')[0]
    if prefix in other_merged:
        other_merged[prefix].append((channel_name, channel_url))
    else:
        other_merged[prefix] = [(channel_name, channel_url)]

    if channel_name not in channel_counters:
        channel_counters[channel_name] = 0

    if channel_counters[channel_name] < result_counter:
        channel_counters[channel_name] += 1

# 对 other_channels 进行排序
other_channels_sorted = []
for prefix in sorted(other_merged.keys()):
    for channel_name, channel_url in other_merged[prefix]:
        other_channels_sorted.append((channel_name, channel_url))



# 将分类后的结果写入文件
with open("itvlist.txt", 'w', encoding='utf-8') as file:
    # 写入CCTV频道
    file.write('央视频道,#genre#\n')
    for channel_name, channel_url in cctv_merged:
        file.write(f"{channel_name},{channel_url}\n")
    
    # 写入卫视频道
    file.write('卫视频道,#genre#\n')
    for prefix in sorted(satellite_merged.keys()):
        for channel_name, channel_url in satellite_merged[prefix]:
            file.write(f"{channel_name},{channel_url}\n")
    
    # 写入其他频道
    file.write('其他频道,#genre#\n')
    for prefix in sorted(other_merged.keys()):
        for channel_name, channel_url in other_merged[prefix]:    
            file.write(f"{channel_name},{channel_url}\n")

    


# 将分类后的结果写入  央视.txt
with open("hysd.txt", 'w', encoding='utf-8') as file:
    # 写入CCTV频道
    file.write('央视频道,#genre#\n')
    for channel_name, channel_url in cctv_merged:
        file.write(f"{channel_name},{channel_url}\n")



# 创建新的m3u文件并写入数据
with open("itvlist.m3u", 'w', encoding='utf-8') as file:
    file.write('#EXTM3U\n')
    
    # 写入央视频道
    for channel_name, channel_url in cctv_merged:
        file.write(f"#EXTINF:-1 group-title=\"央视频道\",{channel_name}\n")
        file.write(f"{channel_url}\n")

    # 写入卫视频道
    for prefix in sorted(satellite_merged.keys()):
        for channel_name, channel_url in satellite_merged[prefix]:
            file.write(f"#EXTINF:-1 group-title=\"卫视频道\",{channel_name}\n")
            file.write(f"{channel_url}\n")

    # 写入其他频道
    for prefix in sorted(other_merged.keys()):
        for channel_name, channel_url in other_merged[prefix]:
            file.write(f"#EXTINF:-1 group-title=\"其他频道\",{channel_name}\n")
            file.write(f"{channel_url}\n")



# 创建新的m3u文件并写入数据
with open("hysd.m3u", 'w', encoding='utf-8') as file:
    file.write('#EXTM3U\n')
    
    # 写入央视频道
    for channel_name, channel_url in cctv_merged:
        file.write(f"#EXTINF:-1 group-title=\"央视频道\",{channel_name}\n")
        file.write(f"{channel_url}\n")



