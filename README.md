# Bit-Level Timing Based CAN ECU Intrusion Detection System

> **합성 데이터와 5차원 물리적 특징 벡터를 통한 차량 ECU 인증 시스템**

---

## 📌 Overview

현대 차량의 내부 네트워크 표준인 CAN(Controller Area Network) 버스는 본질적으로 **송신 ECU를 인증하는 메커니즘이 없다**. 이 구조적 취약점은 공격자가 임의의 ECU인 것처럼 위장하여 메시지를 주입하는 **스푸핑(Spoofing) 공격**을 가능하게 한다.

기존 연구는 ECU별 고유 전압 파형을 물리적 지문(Physical Fingerprint)으로 활용해 송신 장치를 식별하는 방식을 제안하였다. 그러나 이 접근은 오실로스코프 등 수백만 원대의 고가 계측 장비를 필요로 하여, 실차 환경에서의 재현성과 확장성에 한계가 있었다.

본 프로젝트는 이 문제를 해결하기 위해, **전압 대신 비트 단위 타이밍(Bit-Level Timing) 정보**를 ECU의 하드웨어 지문으로 활용하는 새로운 접근을 제안한다. 각 ECU의 내부 클록 발진기(oscillator)는 고유한 주파수 편차(clock drift)와 지터(jitter) 특성을 가지며, 이 차이가 CAN 버스 위의 비트 폭(bit width) 패턴으로 나타난다. 저비용 로직 애널라이저(Logic Analyzer)만으로도 나노초 단위의 이 타이밍 정보를 수집할 수 있어, 실용적인 ECU 식별 시스템 구현이 가능하다.

비지도 학습(Unsupervised Learning) 기반의 **Isolation Forest** 모델을 채택하여, 공격 레이블 데이터 없이 정상 ECU의 타이밍 패턴만으로 이상 탐지를 수행함으로써, 실차 환경에서의 라벨링 비용 문제를 원천적으로 해소한다.

---

## 🧩 System Architecture

본 시스템은 방법론적 타당성 검증과 실용적 구현 가능성 검증을 분리하기 위해 **IDS A**와 **IDS B** 두 개의 독립된 파이프라인을 병렬로 구성한다.

```
┌─────────────────────────────────────────────────────────┐
│                   CAN Bus Signal                        │
│              (Logic Analyzer 수집)                       │
└──────────────────────┬──────────────────────────────────┘
                       │
          ┌────────────┴────────────┐
          │                         │
          ▼                         ▼
┌──────────────────┐       ┌──────────────────────┐
│     IDS A        │       │       IDS B          │
│ (합성 데이터 기반) │       │   (실측 신호 기반)     │
│                  │       │                      │
│ 정규분포 기반      │       │   ESP32 실측 신호     │
│ 합성 타이밍 데이터 │       │   5차원 통계 지문 벡터  │
│                  │       │    - Mean            │
│  • Mean Shift    │       │    - Std Dev         │
│  • Jitter 증가    │       │    - Range           │
│    탐지           │       │    - Skewness        │
│                  │       │    - Kurtosis        │
└────────┬─────────┘       └──────────┬───────────┘
         │                           │
         └─────────────┬─────────────┘
                       ▼
         ┌─────────────────────────┐
         │   Isolation Forest      │
         │  (Unsupervised IDS)     │
         │                         │
         │  정상 ECU: Normal (0)   │
         │  공격 ECU: Attack (1)   │
         └─────────────────────────┘
```

---

## 🔬 Methodology

### 1. 물리적 특징 벡터 (Physical Feature Vector)

각 CAN 메시지의 비트 스트림에서 아래 5가지 통계적 특징을 추출한다. 이 벡터는 특정 ECU 하드웨어의 클록 특성을 반영하는 **하드웨어 지문**으로 기능한다.

| Feature | 의미 | 탐지 타겟 |
|---|---|---|
| **Mean** | 비트폭의 평균 (µs) | 클록 주파수 편차 (clock offset) |
| **Std Dev** | 비트폭의 표준편차 | 타이밍 지터(jitter) 크기 |
| **Range** | 비트폭의 최대-최소 차이 | 타이밍 변동 폭 |
| **Skewness** | 비트폭 분포의 비대칭도 | 클록 편향 방향성 |
| **Kurtosis** | 비트폭 분포의 첨도 | 이상 비트 돌출 빈도 |

정상 ECU는 안정적이고 일관된 클록으로 인해 이 5개 값이 좁은 범위에 분포한다. 반면, 다른 하드웨어 특성을 가진 **공격 ECU**는 평균 이동(mean shift), 지터 증가(jitter elevation), 또는 클록 특성의 차이로 인해 이 분포에서 **이상치(outlier)**로 나타난다.

### 2. IDS A — 합성 데이터 기반 방법론 검증

**목적**: 타이밍 기반 IDS 접근법의 방법론적 타당성 검증

- **데이터 생성**: 정규분포(μ, σ 모델링)를 기반으로 정상 ECU와 공격 ECU의 타이밍 데이터를 합성
  - 정상 데이터: `normal_only.csv` (고정된 μ, 작은 σ)
  - 공격 데이터: `attack_only.csv` (평균 이동 또는 σ 증가로 시뮬레이션)
- **학습**: 정상 데이터의 70%로 Isolation Forest 훈련 (정상 패턴 학습)
- **평가**: 나머지 정상 30% + 공격 데이터 전체로 검증
- **하이퍼파라미터 튜닝**: Grid Search로 `n_estimators`, `max_samples`, `contamination` 최적화
- **탐지 기준**: Anomaly Score가 임계값(contamination)을 초과하면 Attack으로 판정

**탐지 대상 공격 패턴**:
- **Mean Shift**: 공격 ECU의 클록 주파수가 달라 비트폭 평균이 이동
- **Jitter 증가**: 공격 ECU의 불안정한 발진으로 타이밍 변동 폭이 확대

### 3. IDS B — 실측 신호 기반 구현 가능성 검증

**목적**: 실제 하드웨어(ESP32)에서 수집한 신호로 ECU 식별 가능성 실증

- **데이터 수집**: ESP32 마이크로컨트롤러를 CAN 노드로 구성하여 로직 애널라이저로 비트 타이밍 캡처
- **하드웨어**: ESP32 (정상 ECU 역할), Arduino Nano (공격 ECU 역할)
- **신호 처리**: 나노초 단위 엣지 타임스탬프에서 비트폭(µs) 시퀀스 추출
- **특징 추출**: 메시지당 128비트 폭 벡터에서 5차원 통계 지문 계산
- **모델**: 학습된 Isolation Forest를 적용하여 정상/공격 ECU 분류
- **판정 기준**: 전체 메시지 중 공격 의심 비율이 30% 이상이면 "공격/다른 ECU"로 최종 판정

---

## 📁 Repository Structure

```
bit-level_timing_CAN_IDS/
│
├── ids_a_train.py          # IDS A 학습 스크립트 (합성 데이터 기반)
│                           # - Isolation Forest 하이퍼파라미터 튜닝
│                           # - 최종 모델 저장 (.pkl)
│
├── ids_a_run.py            # IDS A 추론/탐지 스크립트
│                           # - 파형 CSV (nanoseconds) 자동 감지
│                           # - Feature CSV 직접 입력 지원
│                           # - 탐지 결과 시각화 (Mean-Std 산점도)
│
├── ids_model_b.ipynb       # IDS B 모델 학습 노트북 (ESP32 실측 데이터)
│                           # - 5차원 통계 특징 추출 파이프라인
│                           # - Isolation Forest 훈련
│
├── ids_b_detection.ipynb   # IDS B 탐지 실행 노트북
│                           # - 실측 신호 로드 및 전처리
│                           # - 정상/공격 ECU 분류 결과 출력
│
├── ids_model_a_iforest.pkl # IDS A 사전 학습된 모델 (StandardScaler + IForest Pipeline)
│
├── ids_model_b_pkl/        # IDS B 사전 학습된 모델 파일
│
└── can_msg_code/           # ESP32/Arduino용 CAN 메시지 송수신 펌웨어 코드 (C++)
```

---

## ⚙️ Technical Details

### 데이터 파이프라인 — 파형 → 피처 변환

로직 애널라이저로 수집된 파형 CSV는 다음 파이프라인을 통해 피처 벡터로 변환된다:

```
Raw CSV (nanoseconds, logic_signal)
        │
        ▼
 엣지(Edge) 타임스탬프 추출
 (logic 값이 0→1 또는 1→0으로 전환되는 시점)
        │
        ▼
 연속 엣지 간 시간 차이 계산 (ns → µs)
 = 비트폭(Bit Width) 시퀀스
        │
        ▼
 128비트 단위로 메시지 분할
 shape: (n_messages, 128)
        │
        ▼
 5차원 통계 지문 추출
 (Mean, Std, Range, Skewness, Kurtosis)
        │
        ▼
 Isolation Forest 입력
```

### 모델 구성

```python
Pipeline([
    ("scaler", StandardScaler()),         # 특징 정규화
    ("clf", IsolationForest(
        n_estimators=200~400,             # 앙상블 트리 수
        max_samples="auto" or 0.8,        # 서브샘플링 비율
        contamination=0.2~0.3,            # 예상 이상치 비율
        random_state=42,
        n_jobs=-1
    ))
])
```

**IsolationForest 출력 변환**:
- 모델 출력 `1` (정상) → `0` (Normal)
- 모델 출력 `-1` (이상) → `1` (Attack)

### 공격 판정 로직

```python
THRESHOLD_ATTACK_RATIO = 0.30  # 기본값 30%

if (공격으로 분류된 메시지 수 / 전체 메시지 수) >= 0.30:
    → "다른 ECU / 공격으로 판단"
else:
    → "정상 ECU로 판단"
```

---

## 🚀 Getting Started

### Prerequisites

```bash
pip install numpy pandas scikit-learn joblib matplotlib scipy
```

### IDS A — 모델 학습

정상 ECU 타이밍 데이터(합성 또는 실측)로 모델을 학습한다.

```bash
# 학습 데이터 준비
# - normal_only.csv  : 정상 ECU 타이밍 피처 CSV
# - attack_only.csv  : 공격 ECU 타이밍 피처 CSV (검증용)

python ids_a_train.py
# 출력: ids_model_a_iforest.pkl
```

### IDS A — 실시간 탐지

```bash
# 학습된 모델로 새로운 데이터를 탐지한다.
# ids_a_run.py 내 하단의 run_ids_a_on_file() 호출 부분에서
# 분석할 파일 경로와 레이블을 지정한 후 실행.

python ids_a_run.py
```

**입력 파일 형식 — 파형 CSV** (로직 애널라이저 출력):
```
nanoseconds,logic_0
1000,0
1125,1
2250,0
...
```

**입력 파일 형식 — 피처 CSV** (사전 추출된 통계 지문):
```
Mean,Std,Range,Skewness,Kurtosis,Label
0.512,0.021,0.18,0.03,2.91,0
0.634,0.055,0.41,0.42,4.12,1
...
```

### IDS B — 실측 신호 탐지

Jupyter Notebook 환경에서 순서대로 실행한다.

```
1. ids_model_b.ipynb      # 모델 학습 (ESP32 정상 신호로 Isolation Forest 훈련)
2. ids_b_detection.ipynb  # 탐지 실행 (새 신호 입력 → 정상/공격 판정)
```

---

## 📊 Results

### IDS A — 합성 데이터 탐지 결과

합성 데이터 실험에서 Isolation Forest는 **평균 이동(Mean Shift)** 및 **지터 증가(Jitter Elevation)**로 시뮬레이션된 공격 패턴을 효과적으로 탐지하였다. 타이밍 분포의 통계적 변화만으로도 정상/공격 ECU를 구분할 수 있음을 수치적으로 확인하였다.

| 지표 | 값 |
|---|---|
| 탐지 대상 | Mean Shift, Jitter 증가 패턴 |
| 평가 방법 | Attack F1-Score 기준 Grid Search |
| 모델 | Isolation Forest + StandardScaler |

### IDS B — 실측 신호 탐지 결과

ESP32(정상 ECU)와 Arduino Nano(공격 ECU)를 실제 하드웨어로 구성하여 신호를 수집한 실험에서, 두 장치 간의 클록 특성 차이가 5차원 통계 지문 벡터에서 명확하게 구분되었다. 저비용 로직 애널라이저만으로도 하드웨어 지문 기반 ECU 식별이 가능함을 실증하였다.

| 항목 | 내용 |
|---|---|
| 정상 ECU | ESP32 (환경별 정상 신호 수집) |
| 공격 ECU | Arduino Nano (스푸핑 시뮬레이션) |
| 특징 벡터 | 5차원 통계 지문 (Mean, Std, Range, Skewness, Kurtosis) |
| 탐지 방식 | Isolation Forest Anomaly Score |

---

## 💡 Key Contributions

- **저비용 구현 가능성 제시**: 오실로스코프 없이 수만 원대 로직 애널라이저만으로 ECU 지문 수집 가능
- **레이블 불필요 탐지**: 비지도 학습 기반으로, 공격 사례 수집 없이 정상 패턴만으로 이상 탐지 가능
- **이중 검증 구조**: 합성 데이터(IDS A)로 방법론을 통제 검증하고, 실측 데이터(IDS B)로 실용성을 독립 검증하는 투트랙 설계
- **자동 입력 감지**: 파형 CSV와 피처 CSV를 자동으로 구분하여 처리하는 유연한 추론 파이프라인

---

## 🔮 Limitations & Future Work

- **클록 온도 의존성**: ECU 온도 변화에 따른 클록 드리프트가 오탐(False Positive)을 유발할 수 있음. 온도 보정 메커니즘 연구 필요
- **실차 환경 검증**: 현재는 통제된 환경에서의 검증이며, 다수 ECU가 동시 통신하는 실제 차량 환경에서의 추가 검증 필요
- **온라인 탐지**: 현재 오프라인 배치 탐지 방식으로, 실시간 스트리밍 탐지 파이프라인으로의 확장 연구 필요
- **멀티 ECU 지문 DB**: 여러 ECU의 하드웨어 지문을 데이터베이스화하여 송신 ECU를 양성(positive) 식별하는 방향으로 확장 가능

---

## 👥 Team

**SWING** — 2026 INC0GNITO

| 이름 | 역할 |
|---|---|
| 함은지 | IDS B 개발, 하드웨어 구성 및 실측 신호 수집 |
| 김효주 | IDS A 개발, 합성데이터 생성 및 환경 설계 |

---

## 📄 License

This project is for academic and research purposes.

---

## 🖇️ Contact

- hej@swu.ac.kr
- agneshyoju@swu.ac.kr