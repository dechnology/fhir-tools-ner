from tqdm import tqdm

# read UMLS dictionary (/Users/yangnoahlin/Downloads/2024AA/META/MRCONSO.RRF)
# 1. 確認LAT是ENG，且SAB是[ICD10,SNOMEDCT_US,LNC,RXNORM]其中一項的concept有多少筆
# 欄位範例：
# CUI|LAT|TS|LUI|STT|SUI|ISPREF|AUI|SAUI|SCUI|SDUI|SAB|TTY|CODE|STR|SRL|SUPPRESS|CVF
# C0484730|ENG|P|L13443801|PF|S16439235|Y|A27103485||10485-1||LNC|LN|10485-1|Glucagon Ag:PrThr:Pt:Tiss:Ord:Immune stain|0|N|256|
def print_progress(line_count, handle_count, count):
    print("-" * 50)
    print("Handle Count =", handle_count)
    print("Handle Percentage =", round(handle_count / line_count * 100, 2), "%")
    print("Valid Count =", count)
    print("Valid Percentage =", round(count / handle_count * 100, 2), "%")
    print("-" * 50)

print("Opening 'MRCONSO.RRF'...")
with open('../data/dict/MRCONSO.RRF', 'r') as f:
    with open('../data/dict/filtered_data.csv', 'w') as fo:
        lines = f.readlines()
        line_count = len(lines)
        handle_count = 0
        count = 0
        count_ICD10 = 0
        count_SNOMEDCT_US = 0
        count_LNC = 0
        count_RXNORM = 0
        for line in tqdm(lines, total=line_count, desc="Loading"):
            handle_count += 1
            columns = line.split('|')
            if columns[1] == 'ENG' and columns[11] in ['ICD10', 'SNOMEDCT_US', 'LNC', 'RXNORM']:
                count += 1
                if columns[11] == 'ICD10':
                    count_ICD10 += 1
                elif columns[11] == 'SNOMEDCT_US':
                    count_SNOMEDCT_US += 1
                elif columns[11] == 'LNC':
                    count_LNC += 1
                elif columns[11] == 'RXNORM':
                    count_RXNORM += 1
                # 將符合條件的資料寫入新檔案
                fo.write(line.replace("|\n", "\n"))   # 如果source符合条件，写入到新文件中
                
    print_progress(line_count, handle_count, count)
    print("ICD10 Count =", count_ICD10)
    print("SNOMEDCT_US Count =", count_SNOMEDCT_US)
    print("LNC Count =", count_LNC)
    print("RXNORM Count =", count_RXNORM)
    print("-" * 50)

