from pydantic import BaseModel
from openai import OpenAI

# 定义Pydantic模型结构
class Concept(BaseModel):
    id: str
    fsn: str
    text: str
    score: float
    match: float
    polarity: bool
    subject: str
    history: int
    begin: int
    end: int

class AttributeTarget(BaseModel):
    id: str
    fsn: str

class Attribute(BaseModel):
    destination: AttributeTarget
    attribute: AttributeTarget
    origin: AttributeTarget

class Relationship(BaseModel):
    origin: dict
    destination: dict

class FocusConcept(BaseModel):
    found: bool
    polarity: bool
    results: list[dict]

class FocusAttribute(BaseModel):
    found: bool
    results: list[dict]

class Focus(BaseModel):
    concepts: dict[str, FocusConcept]
    attributes: dict[str, FocusAttribute]

class JSONStructure(BaseModel):
    input: str
    formatted: str
    focus: Focus
    concepts: list[Concept]
    relationships: list[Relationship]
    attributes: list[Attribute]

# 初始化OpenAI客户端
client = OpenAI(api_key="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")

# 從data/4083.txt讀取content
content = ""
with open("../data/4083.txt", "r") as file:
    content = file.read()

# 调用API并传递模型
completion = client.beta.chat.completions.parse(
    model="gpt-4o-2024-08-06",
    messages=[
        {"role": "system", "content": "You are an expert at structured medical data extraction (SNOMED_CT, RxNorm, LONIC). You will be given unstructured text and should convert it into the given structure."},
        {"role": "user", "content": content}
    ],
    response_format=JSONStructure,
)

# 获取解析后的结构化数据
parsed_response = completion.choices[0].message.parsed

# 输出结果
print(parsed_response)
