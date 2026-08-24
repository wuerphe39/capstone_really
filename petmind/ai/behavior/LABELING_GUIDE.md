# 행동 인식 라벨링 가이드

## 1. LabelImg 설치

```bash
pip install labelImg
labelImg
```

## 2. LabelImg 설정

1. 실행 후 **[Open Dir]** → `data/raw/images/` 선택
2. **[Change Save Dir]** → `data/raw/labels/` 선택
3. 상단 메뉴 **[Format]** → **YOLO** 선택 (중요)
4. **[Edit > Create predefined classes]** → `predefined_classes.txt` 경로 지정

## 3. 라벨링 단축키

| 키 | 동작 |
|---|---|
| `W` | 박스 그리기 시작 |
| `D` | 다음 이미지 |
| `A` | 이전 이미지 |
| `Ctrl+S` | 저장 |
| `Del` | 선택 박스 삭제 |

## 4. 클래스 기준

| 라벨 | 판단 기준 |
|---|---|
| `happy` | 꼬리를 세게 흔들거나 입을 벌리고 활발히 움직임 |
| `anxious` | 몸을 웅크리거나 귀를 뒤로 젖힘, 시선을 피함 |
| `playing` | 앞발을 땅에 짚고 엎드린 자세(play bow), 활발히 뛰는 모습 |
| `resting` | 옆으로 눕거나 엎드려 쉬는 상태, 눈을 감거나 반쯤 뜸 |
| `alert` | 귀를 세우고 한 방향을 응시, 몸이 경직됨 |
| `sick_suspect` | 장시간 미동 없이 웅크림, 무기력한 자세 |
| `hungry` | 밥그릇 주변을 서성이거나 보호자를 향해 앉아 바라봄 |

> **주의**: `resting`과 `sick_suspect`는 시각적으로 유사합니다.
> 움직임이 전혀 없는 장시간 자세 → `sick_suspect`
> 편안해 보이는 휴식 자세 → `resting`

## 5. 라벨링 완료 후

```bash
# 1. raw 데이터를 train/val/test로 분할
python split.py --ratio 0.7 0.2 0.1

# 2. 학습 데이터 증강 (4배)
python augment.py

# 3. 클래스별 샘플 수 확인
python check_dataset.py
```

## 6. 권장 최소 샘플 수

| 클래스 | 권장 원본 이미지 수 |
|---|---|
| happy | 200장 이상 |
| anxious | 150장 이상 |
| playing | 150장 이상 |
| resting | 150장 이상 |
| alert | 150장 이상 |
| sick_suspect | 100장 이상 (수집 어려움) |
| hungry | 100장 이상 |

증강 포함 시 각 클래스당 최소 500장 이상 확보 목표.
