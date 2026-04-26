import numpy as np
import pandas as pd
import joblib
import matplotlib.pyplot as plt

# ------------------------------
# 설정
# ------------------------------
MODEL_PATH = "ids_model_a_iforest.pkl"  # IDS A 모델(pkl)
BITS_PER_MSG = 128                      # 한 메시지당 비트 개수
CHUNK_ROWS_MSG = 300_000               # *_msg 계열 읽을 때 chunk 크기
TARGET_MSGS = 40                        # 파형에서 최대 몇 개 메시지를 추출할지 (너무 크면 RAM 부담)
THRESHOLD_ATTACK_RATIO = 0.30          # 30% 이상이면 "공격/다른 ECU"로 판단

# ------------------------------
# IDS A 모델 로드
# ------------------------------
print("🧠 IDS A 모델 로드 중...")
ids_a = joblib.load(MODEL_PATH)
print("✅ IDS A 모델 로드 완료:", type(ids_a))


# ------------------------------
# 공통 유틸
# ------------------------------
def iforest_to_attack01(pred):
    """IsolationForest 예측(1, -1)을 0=Normal, 1=Attack으로 변환"""
    return np.where(pred == -1, 1, 0)


def print_simple_summary(y_pred, dataset_label):
    """
    비지도 학습 전제
    - y_true 사용하지 않고, 예측 Attack 개수/비율만 출력
    """
    y_pred = np.asarray(y_pred)
    total = len(y_pred)
    num_attack = int(np.sum(y_pred == 1))
    attack_ratio = (num_attack / total * 100.0) if total > 0 else 0.0

    print("\n==============================")
    print(f"📊 [IDS 판독 결과] - {dataset_label}")
    print(f"총 테스트 샘플: {total}개")
    print(f"이상 징후(공격) 탐지: {num_attack}개")
    print(f"공격 의심 확률: {attack_ratio:.2f}%")
    print("==============================")

    if attack_ratio >= THRESHOLD_ATTACK_RATIO * 100:
        print("🚨 경고: 이 데이터는 [다른 ECU / 공격]으로 판단됩니다!")
    else:
        print("✅ 확인: 이 데이터는 [정상 ECU]로 판단됩니다!")


def plot_mean_std(X, y_pred, title):
    """
    각 샘플(메시지)의 mean/std 2D 스캐터 시각화
    X: (n_samples, n_features)
    y_pred: 0=Normal, 1=Attack
    """
    X = np.asarray(X)
    y_pred = np.asarray(y_pred)

    mean_vals = X.mean(axis=1)
    std_vals = X.std(axis=1)

    attack_ratio = np.mean(y_pred == 1) * 100.0

    plt.figure(figsize=(7, 6))
    normal_idx = y_pred == 0
    attack_idx = y_pred == 1

    if np.any(normal_idx):
        plt.scatter(
            mean_vals[normal_idx],
            std_vals[normal_idx],
            s=8,
            alpha=0.7,
            label="Predicted Normal",
        )
    if np.any(attack_idx):
        plt.scatter(
            mean_vals[attack_idx],
            std_vals[attack_idx],
            s=8,
            alpha=0.7,
            label="Predicted Attack",
        )

    plt.xlabel("Mean Bit Time (µs)")
    plt.ylabel("Std / Jitter (µs)")
    plt.title(f"{title} (Attack Ratio: {attack_ratio:.1f}%)")
    plt.legend()
    plt.grid(True, alpha=0.3)
    plt.tight_layout()
    plt.show()


# ------------------------------
# 1) *_msg / nano_attack / arduino_msg (파형 → 비트 feature)
# ------------------------------
def _pick_logic_col(df):
    """logic 컬럼 자동 선택"""
    candidates = [c for c in df.columns if "logic" in c.lower()]
    if not candidates:
        raise ValueError("logic 컬럼을 찾을 수 없습니다 (이름에 'logic'이 포함되어야 함)")
    return candidates[0]  # 첫 번째 logic 계열 사용


def msg_file_to_bit_features(file_path,
                             bits_per_msg=BITS_PER_MSG,
                             target_msgs=TARGET_MSGS,
                             chunk_rows=CHUNK_ROWS_MSG):
    """
    *_msg / nano_attack.csv / arduino_msg.csv 같이
    nanoseconds + logic 파형이 들어있는 파일을

    → 비트폭(µs) 128개짜리 메시지 여러 개로 변환해서
      (n_messages, 128) 형태의 DataFrame으로 반환
    """

    print(f"[MSG] '{file_path}'를 chunk 단위로 읽는 중 (chunk_rows={chunk_rows})")

    reader = pd.read_csv(
        file_path,
        engine="python",
        on_bad_lines="skip",
        chunksize=chunk_rows,
    )

    edge_times_all = []
    logic_col_name = None

    # 필요한 엣지 개수 (조금 여유 있게)
    target_edges = bits_per_msg * (target_msgs + 1)

    merged = np.array([])

    for i, chunk in enumerate(reader, start=1):
        print(f"  - chunk {i} 읽음 (행 {len(chunk)}개)")

        if "nanoseconds" not in chunk.columns:
            raise ValueError("nanoseconds 컬럼이 없습니다 (파형 CSV 형식이 아님)")

        if logic_col_name is None:
            logic_col_name = _pick_logic_col(chunk)
            print(f"    · logic 컬럼으로 '{logic_col_name}' 사용")

        # 0↔1 변화가 있는 지점만 엣지로 추출
        edges = chunk[chunk[logic_col_name].shift(1) != chunk[logic_col_name]].copy()
        print(f"    · 이 chunk에서 찾은 엣지 수: {len(edges)}")

        if len(edges) > 0:
            edge_times_all.append(edges["nanoseconds"].astype(float).values)
            merged = np.concatenate(edge_times_all)

        if merged.size >= target_edges:
            print(f"  → 누적 엣지 {merged.size}개로 충분, 나머지 chunk는 스킵")
            break

    if merged.size < bits_per_msg + 1:
        # 엣지가 부족한 경우: 있는 만큼으로 비트폭을 계산하고 패딩해서 1개의 메시지만 만든다
        print(
            f"⚠ 엣지가 {merged.size}개뿐이라도, "
            f"있 는 비트폭으로 1개 메시지를 만들고 패딩해서 사용합니다."
        )

        t_ns = merged
        bit_widths_us = np.diff(t_ns) / 1000.0
        total_bits = len(bit_widths_us)

        if total_bits == 0:
            raise ValueError("비트폭을 전혀 계산할 수 없습니다. 캡처 구간을 다시 확인해야 합니다.")

        # 부족한 길이만큼 마지막 값을 반복해서 패딩
        pad_len = bits_per_msg - total_bits
        if pad_len < 0:
            # 혹시라도 비트폭이 128개보다 많으면 앞에서 128개만 사용
            bit_widths_us = bit_widths_us[:bits_per_msg]
            pad_len = 0

        padded = np.pad(bit_widths_us, (0, pad_len), mode="edge")

        df_bits = pd.DataFrame(
            [padded], columns=[f"bit_{i}" for i in range(bits_per_msg)]
        )
        return df_bits


    # 엣지 간 간격 → 비트폭 (ns → µs)
    t_ns = merged
    bit_widths_us = np.diff(t_ns) / 1000.0

    total_bits = len(bit_widths_us)
    num_msgs = total_bits // bits_per_msg
    if num_msgs == 0:
        raise ValueError(
            f"비트폭 {total_bits}개로는 {bits_per_msg}개짜리 메시지를 하나도 만들 수 없습니다."
        )

    print(f"  → 추출된 비트폭 개수: {total_bits}개 → 메시지 {num_msgs}개 생성")

    msgs = []
    for i in range(num_msgs):
        start = i * bits_per_msg
        end = start + bits_per_msg
        msgs.append(bit_widths_us[start:end])

    df_bits = pd.DataFrame(
        msgs, columns=[f"bit_{i}" for i in range(bits_per_msg)]
    )
    return df_bits


# ------------------------------
# 2) 합성 feature CSV (synthetic_normal / synthetic_attack 등)
# ------------------------------
def feature_file_to_X(file_path):
    """
    synthetic_normal.csv, synthetic_attack.csv 같이
    이미 feature로 구성된 CSV를 읽어서 (n_samples, n_features) X 반환

    - 숫자형 컬럼만 사용
    - Label, ECU_ID 등은 자동 제외
    """
    print(f"[Feature Dataset] '{file_path}' 로드 중...")

    df = pd.read_csv(file_path)

    exclude = {"Label", "ECU_ID"}
    feat_cols = [
        c for c in df.columns
        if c not in exclude and np.issubdtype(df[c].dtype, np.number)
    ]

    if not feat_cols:
        raise ValueError("사용할 수 있는 숫자 feature 컬럼을 찾지 못했습니다.")

    print(f"  - 사용 feature 컬럼 수: {len(feat_cols)}개")
    X = df[feat_cols].values
    return X


# ------------------------------
# 3) 파일 타입 자동 판별 + IDS A 실행
# ------------------------------
def run_ids_a_on_file(file_path, dataset_label):
    """
    하나의 진입점
    - nanoseconds 컬럼이 있으면 *_msg / nano_attack / arduino_msg 형식으로 보고
      파형 → 비트 feature 변환 후 IDS 실행
    - 아니면 synthetic_* 같은 feature CSV로 보고 곧바로 IDS 실행
    """

    # 헤더만 잠깐 읽어서 nanoseconds 있는지 확인
    head = pd.read_csv(file_path, nrows=5)
    cols_lower = [c.lower() for c in head.columns]

    print(f"\n\n📂 파일 분석 시작: '{file_path}' ({dataset_label})")

    if "nanoseconds" in cols_lower:
        # 파형 타입
        print("  → 타입 판별: 파형(MSG) CSV 로 인식")
        X = msg_file_to_bit_features(file_path)
        title = f"{dataset_label} (MSG → Bit Features)"
    else:
        # feature 타입
        print("  → 타입 판별: Feature CSV 로 인식")
        X = feature_file_to_X(file_path)
        title = dataset_label

    # IDS A 예측
    y_pred = iforest_to_attack01(ids_a.predict(X))

    # 요약 출력
    print_simple_summary(y_pred, dataset_label)

    # 시각화
    plot_mean_std(X, y_pred, title)


# ------------------------------
# 4) 여기서 6개 파일을 하나의 코드로 실행
#    (원하는 줄만 주석 풀어서 사용)
# ------------------------------
if __name__ == "__main__":

    # 1. 합성 데이터 정상 (학습에 썼던 정상 합성 데이터)
    # run_ids_a_on_file("synthetic_normal.csv", "Synthetic Normal (Training-like)")

    # 2. 합성 공격 데이터
    # run_ids_a_on_file("synthetic_attack.csv", "Synthetic Attack")

    # 3-1. 실제 기기 정상 데이터 (ECU A)
    # run_ids_a_on_file("normal_msg.csv", "Real Device Normal (ECU A)")

    # 3-2. 실제 기기 공격 데이터 (ECU B / ESP32 등)
    # run_ids_a_on_file("attack_msg.csv", "Real Device Attack (ECU B)")

    # 4-1. 아두이노 나노 기기 데이터
     run_ids_a_on_file("nano_attack.csv", "Arduino Nano Attack")

    # 4-2. 또 다른 아두이노 기기 데이터
    # run_ids_a_on_file("arduino_msg.csv", "Another Arduino ECU")
