# C0488050|LN|8358-4|Cuff size:Len:Pt:Blood pressure device:OrdQn
# C1317000|LN|34538-9|Orthostatic blood pressure:PressDiff:Pt:Arterial system:Qn
# C1716485|LN|45372-0|Blood pressure systolic & diastolic^post phlebotomy:Pres:Pt:Arterial system:Qn
# C1978272|LN|50402-7|Blood pressure systolic & diastolic^post transfusion:Pres:Pt:Arterial system:Qn
# C1978273|LN|50403-5|Blood pressure systolic & diastolic^pre transfusion:Pres:Pt:Arterial system:Qn
# C2925914|LN|58294-0|Age began taking high blood pressure medication:Time:Pt:^Patient:Qn
# C2925915|LN|58296-5|Age when told have high blood pressure:Time:Pt:^Patient:Qn
# C3484017|LN|71789-2|Change in systolic blood pressure:PressDiff:Pt:^Patient:Qn
# C3484100|LN|71896-5|Pediatric blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height
# C3533854|LN|72165-4|Pediatric systolic blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height
# C3533855|LN|72164-7|Pediatric diastolic blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height
# C4071506|LN|76539-6|Cuff pressure.diastolic:Pres:Pt:Blood pressure device:Qn
# C4071507|LN|76538-8|Cuff pressure.systolic:Pres:Pt:Blood pressure device:Qn
# C4071508|LN|76537-0|Cuff pressure.mean:Pres:Pt:Blood pressure device:Qn
# C4071513|LN|76532-1|Cuff pressure:Pres:Pt:Blood pressure device:Qn
# C4318513|LN|85354-9|Blood pressure panel with all children optional:-:Pt:Arterial system:Qn
# C4695385|LN|88346-2|Blood pressure with exercise & post exercise panel:-:Pt:Arterial system:Qn

# 寫一段OpenAI Embedding的程式碼，比較「Blood Pressure: 93/62mmHg」最像哪一個術語
import os
import pandas as pd
from openai import OpenAI

openai_api_key = os.getenv("OPENAI_API_KEY")
if not openai_api_key:
    raise ValueError("請設定 OPENAI_API_KEY 環境變數")
client = OpenAI(api_key=openai_api_key)

# 將所有候選術語轉換為向量後，計算與「Blood Pressure: 93/62mmHg」的相似度
concepts = [
    "Cuff size:Len:Pt:Blood pressure device:OrdQn",
    "Orthostatic blood pressure:PressDiff:Pt:Arterial system:Qn",
    "Blood pressure systolic & diastolic^post phlebotomy:Pres:Pt:Arterial system:Qn",
    "Blood pressure systolic & diastolic^post transfusion:Pres:Pt:Arterial system:Qn",
    "Blood pressure systolic & diastolic^pre transfusion:Pres:Pt:Arterial system:Qn",
    "Age began taking high blood pressure medication:Time:Pt:^Patient:Qn",
    "Age when told have high blood pressure:Time:Pt:^Patient:Qn",
    "Change in systolic blood pressure:PressDiff:Pt:^Patient:Qn",
    "Pediatric blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height",
    "Pediatric systolic blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height",
    "Pediatric diastolic blood pressure percentile:Prctl:Pt:^Patient:Qn:Per age, sex and height",
    "Cuff pressure.diastolic:Pres:Pt:Blood pressure device:Qn",
    "Cuff pressure.systolic:Pres:Pt:Blood pressure device:Qn",
    "Cuff pressure.mean:Pres:Pt:Blood pressure device:Qn",
    "Cuff pressure:Pres:Pt:Blood pressure device:Qn",
    "Blood pressure panel with all children optional:-:Pt:Arterial system:Qn",
    "Blood pressure with exercise & post exercise panel:-:Pt:Arterial system:Qn"
]
# 將concepts以pandas的DataFrame格式呈現，title為string，第二個欄位為embedding
df = pd.DataFrame(concepts, columns=["concept_string"])

def get_embedding(text, model="text-embedding-3-large"):
   return client.embeddings.create(input = [text], model=model).data[0].embedding

df['embedding'] = df.concept_string.apply(lambda x: get_embedding(x, model='text-embedding-3-large'))
df.to_csv("test_embedding.csv")
print(df.head())

# 計算「Blood Pressure: 93/62mmHg」與所有候選術語的相似度
bp_embedding = get_embedding("Blood Pressure: 93/62mmHg", model='text-embedding-3-large')

from typing import List, Optional
from scipy import spatial

df['similarity'] = df.embedding.apply(lambda x: 1 - spatial.distance.cosine(bp_embedding, x))
print(df)
print(df.sort_values("similarity", ascending=False).head(3))
