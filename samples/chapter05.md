# 5장. 로봇 주행 데이터 분석하기 (가상 샘플 원고 · 검증용)

> 이 원고는 일반화 확인용으로 직접 만든 가상 샘플이에요. 3장 튜닝에 쓰지 않은 라이브러리로 구성했어요.

## 5.1 준비

Python 3.8 이상이면 이 장의 모든 예제를 실행할 수 있습니다. Python 3.8은 현재 보안 업데이트를 받고 있는 안정 버전입니다.

## 5.2 주행 로그 내려받기

```python
import requests
resp = requests.get("https://example.com/robot/log.json", timeout=10)
resp.raise_for_status()
```

## 5.3 속도 계산

```python
import numpy as np
speeds = np.array([0.4, 0.6, 0.5], dtype=np.float)
total = np.product(speeds)
```

## 5.4 회귀 모델 학습

```python
from sklearn.datasets import load_boston
X, y = load_boston(return_X_y=True)
```

## 5.5 설정 검증

```python
from pydantic import BaseModel, validator

class RobotConfig(BaseModel):
    max_speed: float

    @validator("max_speed")
    def check_speed(cls, v):
        return min(v, 2.0)

print(RobotConfig(max_speed=3.0).dict())
```

## 5.6 그래프 그리기

```python
import matplotlib.pyplot as plt
plt.style.use("seaborn")
plt.plot([1, 2, 3], [0.4, 0.6, 0.5])
```

## 5.7 배열 합계

```python
import numpy as np
print(np.array([1, 2, 3]).sum())
```

## 5.8 연구실 내부 라이다 드라이버

```python
from labx_lidar import LidarStream
stream = LidarStream(port="/dev/ttyUSB0")
```
