# ============================================================
# IDS A Training Script
#  - 학습: normal_only.csv (합성 정상)
#  - 검증: normal_only 일부 + attack_only.csv 전체
#  - 평가: synthetic_can_timing_dataset.csv (있으면)
#  - 저장: ids_model_a_iforest.pkl
# ============================================================

import os
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from sklearn.preprocessing import StandardScaler
from sklearn.pipeline import Pipeline
from sklearn.model_selection import train_test_split, ParameterGrid
from sklearn.metrics import (
    classification_report,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
import joblib

# ------------------------------------------------------------
# 1. 파일 경로 및 저장 경로 설정
# ------------------------------------------------------------
NORMAL_FILE = "normal_only.csv"                   # 합성 정상만
ATTACK_FILE = "attack_only.csv"                   # 합성 공격만
FULL_SYNTH_FILE = "synthetic_can_timing_dataset.csv"  # 전체 합성 (정상+공격)
MODEL_SAVE_PATH = "ids_model_a_iforest.pkl"       # IDS A 최종 모델

# ------------------------------------------------------------
# 2. normal_only / attack_only 로드
# ------------------------------------------------------------
print("🧠 [IDS A] 학습용 데이터 로드 시작...")

df_normal = pd.read_csv(NORMAL_FILE)
df_attack = pd.read_csv(ATTACK_FILE)

print(f"  - normal_only.shape = {df_normal.shape}")
print(f"  - attack_only.shape = {df_attack.shape}")

# 공통 feature 컬럼: 숫자형이면서 Label / ECU_ID 제외
exclude_cols = {"Label", "ECU_ID"}
feature_cols = [
    c for c in df_normal.columns
    if c not in exclude_cols and np.issubdtype(df_normal[c].dtype, np.number)
]

X_normal = df_normal[feature_cols].values
X_attack = df_attack[feature_cols].values

print(f"  - 사용 특징 차원 수: {len(feature_cols)}")

# ------------------------------------------------------------
# 3. 학습/검증 데이터 구성
#    - 학습: normal_only 일부(70%)
#    - 검증: normal_only 나머지(30%) + attack_only 전체
# ------------------------------------------------------------
X_train_norm, X_val_norm = train_test_split(
    X_normal, test_size=0.3, random_state=42
)

X_val = np.vstack([X_val_norm, X_attack])
y_val = np.concatenate([
    np.zeros(len(X_val_norm), dtype=int),   # 검증 정상 = 0
    np.ones(len(X_attack), dtype=int)       # 검증 공격 = 1
])

print(f"  - 학습용 정상 샘플: {len(X_train_norm)}")
print(f"  - 검증용 정상: {len(X_val_norm)}, 검증용 공격: {len(X_attack)}")

# ------------------------------------------------------------
# 4. 하이퍼파라미터 그리드 정의 (간단 튜닝)
# ------------------------------------------------------------
param_grid = {
    "clf__n_estimators": [200, 400],
    "clf__max_samples": ["auto", 0.8],
    "clf__contamination": [0.2, 0.25, 0.3],   # 공격 비율 후보
}

grid = list(ParameterGrid(param_grid))
print(f"\n🧪 하이퍼파라미터 후보 조합 수: {len(grid)}")

best_f1 = -1.0
best_params = None
best_model = None

# ------------------------------------------------------------
# 5. 그리드 서치 (정상으로만 학습 → 검증셋에서 Attack F1 측정)
# ------------------------------------------------------------
for i, params in enumerate(grid, 1):
    print(f"\n[{i}/{len(grid)}] 파라미터: {params}")

    model = Pipeline([
        ("scaler", StandardScaler()),
        ("clf", IsolationForest(
            n_estimators=params["clf__n_estimators"],
            max_samples=params["clf__max_samples"],
            contamination=params["clf__contamination"],
            random_state=42,
            n_jobs=-1,
        ))
    ])

    # 학습: 정상 데이터만
    model.fit(X_train_norm)

    # 검증: 정상 + 공격 섞인 X_val
    y_pred_if = model.predict(X_val)           # 1(정상), -1(이상)
    y_pred = np.where(y_pred_if == -1, 1, 0)   # 1=Attack, 0=Normal

    f1_att = f1_score(y_val, y_pred, pos_label=1)
    rec_att = recall_score(y_val, y_pred, pos_label=1)
    prec_att = precision_score(y_val, y_pred, pos_label=1)

    print(f"  -> Attack F1: {f1_att:.4f},  Precision: {prec_att:.4f},  Recall: {rec_att:.4f}")

    if f1_att > best_f1:
        best_f1 = f1_att
        best_params = params
        best_model = model
        print("  ✅ 현재까지 최고 성능 갱신")

print("\n🎯 [튜닝 결과] 최적 파라미터:", best_params)
print(f"🎯 [튜닝 결과] 최적 Attack F1 (검증 기준): {best_f1:.4f}")

# ------------------------------------------------------------
# 6. 최적 파라미터로 IDS A 최종 학습 (정상 전체 사용)
# ------------------------------------------------------------
final_model = Pipeline([
    ("scaler", StandardScaler()),
    ("clf", IsolationForest(
        n_estimators=best_params["clf__n_estimators"],
        max_samples=best_params["clf__max_samples"],
        contamination=best_params["clf__contamination"],
        random_state=42,
        n_jobs=-1,
    ))
])

print("\n🚀 [IDS A] 최종 재학습 (normal_only 전체 사용)...")
final_model.fit(X_normal)
print("✅ [IDS A] 재학습 완료")

# ------------------------------------------------------------
# 7. 합성 데이터 전체에 대한 성능 평가
#    - synthetic_can_timing_dataset.csv 가 있으면 그걸 쓰고,
#      없으면 normal_only + attack_only 를 합쳐서 대신 사용
# ------------------------------------------------------------
if os.path.exists(FULL_SYNTH_FILE):
    print("\n📂 synthetic_can_timing_dataset.csv 로 전체 성능 평가")
    df_full = pd.read_csv(FULL_SYNTH_FILE)
    feature_cols_full = [
        c for c in df_full.columns
        if c not in exclude_cols and np.issubdtype(df_full[c].dtype, np.number)
    ]
    X_full = df_full[feature_cols_full].values
    y_full = df_full["Label"].astype(int).values
else:
    print("\n⚠️ synthetic_can_timing_dataset.csv 가 없어 "
          "normal_only + attack_only 를 합쳐서 전체 성능 평가를 대신 진행함")
    df_full = pd.concat([df_normal, df_attack], ignore_index=True)
    feature_cols_full = [
        c for c in df_full.columns
        if c not in exclude_cols and np.issubdtype(df_full[c].dtype, np.number)
    ]
    X_full = df_full[feature_cols_full].values
    y_full = np.concatenate([
        np.zeros(len(df_normal), dtype=int),
        np.ones(len(df_attack), dtype=int),
    ])

print(f"  - 전체 평가 샘플 수: {len(X_full)}")

y_pred_if_full = final_model.predict(X_full)
y_pred_full = np.where(y_pred_if_full == -1, 1, 0)   # 1=Attack, 0=Normal

print("\n📊 [IDS A] 합성 전체 데이터 최종 성능")
print("\n--- Classification Report ---")
print(classification_report(
    y_full, y_pred_full,
    target_names=["Normal(0)", "Attack(1)"],
    zero_division=0,
))

print("\n--- Confusion Matrix (행=실제, 열=예측) ---")
print(confusion_matrix(y_full, y_pred_full))

f1_att_full = f1_score(y_full, y_pred_full, pos_label=1)
rec_att_full = recall_score(y_full, y_pred_full, pos_label=1)
prec_att_full = precision_score(y_full, y_pred_full, pos_label=1)

print(f"\n최종 Attack F1: {f1_att_full:.4f}")
print(f"최종 Attack Recall(탐지율): {rec_att_full:.4f}")
print(f"최종 Attack Precision(공격 예측 중 진짜 공격 비율): {prec_att_full:.4f}")

# ------------------------------------------------------------
# 8. IDS A 모델 저장
# ------------------------------------------------------------
joblib.dump(final_model, MODEL_SAVE_PATH)
print(f"\n💾 IDS A 최종 모델이 '{MODEL_SAVE_PATH}' 로 저장되었습니다.")
