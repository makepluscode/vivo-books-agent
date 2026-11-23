# 3장. 파이썬으로 만드는 첫 AI 로봇 비서 (가상 샘플 원고)

> 이 원고는 데모용으로 직접 만든 가상 샘플이에요. 실제 출간 원고가 아니에요.

## 3.1 환경 준비

이 장의 예제는 2024년 1월 기준 최신 버전에서 테스트했습니다. ROS 2는 현재 최신 LTS인 Humble을 사용합니다.

```bash
pip install langchain==0.1.0 openai==0.28 pandas==1.5.3 torch==2.1.0
```

## 3.2 LLM 체인 만들기

```python
from langchain.chains import LLMChain
from langchain.prompts import PromptTemplate
from langchain_openai import ChatOpenAI

prompt = PromptTemplate.from_template("{topic}에 대해 한 문장으로 설명해 줘")
chain = LLMChain(llm=ChatOpenAI(model="gpt-4o-mini"), prompt=prompt)
print(chain.run(topic="로봇 운영체제"))
```

LCEL 방식으로도 같은 일을 할 수 있습니다.

```python
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

chain = ChatPromptTemplate.from_template("{topic} 설명") | ChatOpenAI(model="gpt-4o-mini")
print(chain.invoke({"topic": "SLAM"}).content)
```

## 3.3 OpenAI API 직접 호출

```python
import openai
openai.api_key = "YOUR_KEY"
resp = openai.ChatCompletion.create(
    model="gpt-3.5-turbo",
    messages=[{"role": "user", "content": "안녕"}],
)
print(resp["choices"][0]["message"]["content"])
```

## 3.4 센서 로그 정리

```python
import pandas as pd
log = pd.DataFrame(columns=["t", "lidar"])
log = log.append({"t": 0.1, "lidar": 3.2}, ignore_index=True)
```

## 3.5 혼합 정밀도 학습

```python
import torch
with torch.cuda.amp.autocast():
    out = model(x)
```

## 3.6 사내 로봇 SDK 연결

```python
from vivo_robot_sdk import Arm
arm = Arm.connect("192.168.0.10")
```
