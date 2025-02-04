from tqdm import tqdm
import os
import json

# read UMLS dictionary (/Users/yangnoahlin/Downloads/2024AA/META/MRCONSO.RRF)
# 1. 確認LAT是ENG，且SAB是[ICD10,SNOMEDCT_US,LNC,RXNORM]其中一項的concept有多少筆
# 欄位範例：
# CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|SRL|SUPPRESS|CVF
# C0484730|ENG|P|L13443801|PF|S16439235|Y|A27103485||10485-1||LNC|LN|10485-1|Glucagon Ag:PrThr:Pt:Tiss:Ord:Immune stain|0|N|256|
def print_progress(line_count, handle_count, count):
    print("-" * 50)
    print("Handle Count =", handle_count)
    print("Handle Percentage =", round(handle_count / line_count * 100, 2), "%")
    print("Target Count =", count)
    print("Target Percentage =", round(count / handle_count * 100, 2), "%")
    print("-" * 50)

out_postfix = '_with_op_icd10cm.ndjson'
print(f"Opening 'MRCONSO.RRF'... (for creating 'filtered_umls{out_postfix}')")
with open('../data/dict/MRCONSO.RRF', 'r') as f:
    file_index = 1
    lines = f.readlines()
    line_count = len(lines)
    handle_count = 0
    count = 0
    count_ICD10CM = 0
    count_ICD10 = 0
    count_SNOMEDCT_US = 0
    count_LNC = 0
    count_RXNORM = 0
    lines_per_file = 500000  # 每个文件存储的行数
    max_file_size = 100 * 1024 * 1024  # 设置文件大小限制为500KB（可根据需求调整）
    current_line_count = 0  # 当前文件已写入的行数
    file_need_split = True  # 是否需要拆分文件

    output_filename = f'../data/dict/filtered_umls{f"_{file_index}" if file_need_split else ""}{out_postfix}'
    fo = open(output_filename, 'w')

    for line in tqdm(lines, total=line_count, desc="Loading"):
        handle_count += 1
        columns = line.split('|')
        # 只处理符合条件的行
        # if columns[1] == 'ENG' and columns[11] in ['ICD10CM', 'ICD10', 'SNOMEDCT_US', 'LNC', 'RXNORM']:
        if columns[1] == 'ENG' and columns[11] in ['ICD10CM']:
            count += 1
            current_line_count += 1  # 计数当前文件中的有效行
            if columns[11] == 'ICD10CM':
                count_ICD10CM += 1
            if columns[11] == 'ICD10':
                count_ICD10 += 1
            elif columns[11] == 'SNOMEDCT_US':
                count_SNOMEDCT_US += 1
            elif columns[11] == 'LNC':
                count_LNC += 1
            elif columns[11] == 'RXNORM':
                count_RXNORM += 1

            NEW_LINE = "\n"
            # 每筆資料要寫入如下的ndjson格式 (操作行+資料行)
            # { "index": { "_index": "snomedct_us" } }
            # { "CUI": "C0000052", "SAB": "SNOMEDCT_US", "TTY": "SY", "CODE": "58488005", "STR": "Branching enzyme" }
            index_dict = {
                "index": {
                    "_index": columns[11].lower()
                }
            }
            line_content = f'{json.dumps(index_dict)}{NEW_LINE}'
            fo.write(line_content)
            line_dict = {
                "CUI": columns[0],
                "SAB": columns[11],
                "TTY": columns[12],
                "CODE": columns[13],
                "STR": columns[14]
            }
            line_content = f'{json.dumps(line_dict)}{NEW_LINE}'
            fo.write(line_content)
            
            # 每500行或达到文件大小限制时，换一个文件
            fo.flush()  # 刷新缓冲区，确保文件大小获取准确
            file_size = os.path.getsize(fo.name)  # 获取当前文件大小
            
            if file_need_split and (current_line_count == lines_per_file or file_size >= max_file_size):
                fo.close()  # 关闭当前文件
                file_index += 1  # 增加文件编号
                output_filename = f'../data/dict/filtered_umls_{file_index}_with_op.ndjson'
                fo = open(output_filename, 'w')  # 打开新的文件
                current_line_count = 0  # 重置当前文件计数
    
    fo.close()  # 关闭最后一个文件


    print_progress(line_count, handle_count, count)
    print("ICD10CM Count =", count_ICD10CM)
    print("ICD10 Count =", count_ICD10)
    print("SNOMEDCT_US Count =", count_SNOMEDCT_US)
    print("LNC Count =", count_LNC)
    print("RXNORM Count =", count_RXNORM)
    print("-" * 50)
