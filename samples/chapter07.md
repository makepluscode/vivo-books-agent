# 7장. AI·로보틱스 실습: 센서에서 경로 계획까지 (가상 샘플 원고)

> 이 원고는 블라인드 평가용으로 직접 만든 가상 기술서예요. 실제 로봇이나 고객 데이터는 사용하지 않아요.

## 7.1 실습 준비

현재 NumPy의 최신 안정 버전은 1.26.4예요.

공개 실습 패키지는 pip로 설치하는 numpy, scipy, Pillow, networkx예요. GPU, 외부 데이터 파일, 네트워크 서비스 없이 합성 데이터로 실습해요. 각 절은 별도의 실습 셀이고, 다른 절의 변수가 필요한 경우 본문에 표시해요. 한 셀에서 오류가 나더라도 다른 독립 셀은 따로 실행해요.

## 7.2 이동 로봇의 센서 배열

바퀴 속도와 측정 시각을 배열에 담아요. 이 절에서 정의한 sample_times와 wheel_speeds는 다음 절에서도 사용해요.

```python
import numpy as np

sample_times = np.array([0.0, 0.5, 1.0])
wheel_speeds = np.array([0.0, 1.0, 2.0])
features = np.column_stack((sample_times, wheel_speeds))
print(features.shape)
```

## 7.3 속도 적분으로 이동 거리 추정

앞 절의 sample_times와 wheel_speeds를 그대로 사용해 이동 거리를 구해요. 이 셀은 7.2절 실행 후 실행해요.

```python
from scipy.integrate import simps

travelled = simps(wheel_speeds, x=sample_times)
print(float(travelled))
```

## 7.4 로봇 카메라 입력 축소

단색 합성 프레임을 작은 영상으로 바꿔요. 학습 데이터 전처리의 크기 변환 단계를 흉내 낸 예제예요.

```python
from PIL import Image

frame = Image.new("RGB", (128, 96), color=(40, 120, 200))
thumbnail = frame.resize((32, 24), Image.ANTIALIAS)
print(thumbnail.size)
```

## 7.5 인접 배열에서 주행 지도 만들기

세 지점 사이의 연결 관계를 인접 배열로 표현해요.

```python
import numpy as np
import networkx as nx

adjacency = np.array([[0, 1, 0], [1, 0, 1], [0, 1, 0]])
route_graph = nx.from_numpy_matrix(adjacency)
print(sorted(route_graph.edges()))
```

## 7.6 작은 선형 시스템 풀기

대칭 양의 정부호 행렬을 이용해 두 센서의 보정량을 구해요.

```python
import numpy as np
from scipy.sparse.linalg import cg

system = np.array([[4.0, 1.0], [1.0, 3.0]])
offsets = np.array([1.0, 2.0])
correction, info = cg(system, offsets, tol=1e-8)
print(correction, info)
```

## 7.7 센서 잡음 합성

새 학습 실험에 사용할 잡음을 만들어요. 과거 실험의 난수열과 일치시킬 필요는 없어요.

```python
import numpy as np

noise_rng = np.random.RandomState(7)
sensor_noise = noise_rng.normal(loc=0.0, scale=0.01, size=8)
print(sensor_noise.shape)
```

## 7.8 평면 회전 행렬

로봇의 평면 자세에 90도 회전을 적용해요.

```python
import numpy as np

turn = np.matrix([[0.0, -1.0], [1.0, 0.0]])
position = np.matrix([[1.0], [0.0]])
print(turn * position)
```

## 7.9 삼차원 자세 변환

센서 좌표계의 x축 방향 벡터를 z축 기준으로 회전해요.

```python
from scipy.spatial.transform import Rotation

orientation = Rotation.from_euler("z", 90, degrees=True)
rotated = orientation.apply([1.0, 0.0, 0.0])
print(rotated.round(6))
```

## 7.10 가중치가 있는 주행 경로

독립적인 지도 그래프를 만들고 이동 비용의 합이 작은 경로를 선택해요.

```python
import networkx as nx

navigation = nx.Graph()
navigation.add_weighted_edges_from([("dock", "hall", 1.0), ("hall", "lab", 2.0), ("dock", "lab", 5.0)])
path = nx.shortest_path(navigation, source="dock", target="lab", weight="weight")
print(path)
```

## 7.11 내부 정책 어댑터 연결

마지막 셀은 가상 조직이 사설 인덱스에 배포했다고 가정한 내부 패키지의 예제예요. 공개 PyPI 배포물이나 공개 API 문서는 제공하지 않아요.

```python
from aster_lab_policy_bridge import PolicyAdapter

adapter = PolicyAdapter(profile="training-room")
print(adapter.describe_action_space())
```
