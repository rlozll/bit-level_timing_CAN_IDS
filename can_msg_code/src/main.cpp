#include <Arduino.h>

// 연결된 핀 (GPIO 5)
#define CAN_TX_PIN 5 

// 500kbps = 1비트당 2마이크로초(us)
#define BIT_TIME_US 2 

void setup() {
  // CAN 라이브러리 안 씀! 직접 제어!
  pinMode(CAN_TX_PIN, OUTPUT);
  digitalWrite(CAN_TX_PIN, HIGH); // 대기 상태 (1)
  
  Serial.begin(115200);
  Serial.println("데이터 수집용 신호 발사 시작!");
}

void loop() {
  // --- 1. SOF (Start) ---
  digitalWrite(CAN_TX_PIN, LOW); delayMicroseconds(BIT_TIME_US);

  // --- 2. 데이터 패턴 (010101...) ---
  // 비트 타이밍을 분석하기 가장 좋은 패턴입니다.
  for(int i=0; i<50; i++) {
      digitalWrite(CAN_TX_PIN, HIGH); delayMicroseconds(BIT_TIME_US); // 1
      digitalWrite(CAN_TX_PIN, LOW); delayMicroseconds(BIT_TIME_US);  // 0
  }

  // --- 3. 휴식 (Idle) ---
  digitalWrite(CAN_TX_PIN, HIGH); 
  delay(100); // 100ms마다 반복
}