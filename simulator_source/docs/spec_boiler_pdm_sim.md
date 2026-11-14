# Boiler PdM Simulator v1 Spec

이 문서는 보일러(PdM 연구용) 시뮬레이터를 설계/확장하기 위한 실행형 명세입니다.

---

## v1.1 spec freeze

- Freeze 날짜: **2026-03-08**
- 버전: **v1.1.1**
- 스키마 이름: **boiler-pdm-sim-schema-v1.1**
- 고정 문서: `docs/spec_boiler_pdm_sim.md`
- 스키마 락: `label`, `truth`, `obs`, `meta` 핵심 컬럼 규약 + pipeline 계약(`calibration`, `identifiability`, `randomization`) 고정
- 변경 불가 항목(Freeze): 이벤트 로그 계약(`label/event_log*`), 고장 이벤트 포맷(`*_onset/_threshold/_trip`), 저장 메타(`provenance`) 구조
- 단일 소스 규칙: 스키마 메타(`schema_version`, `freeze_date`)는 코드 상수(`src/boiler_pdm_sim/schema.py`)와 동일해야 한다.
- 점검 명령: `python scripts/check_spec_contract.py`

## 0. 목표

- 드럼형 자연순환 보일러를 대상으로 한 **grey-box(물리+경험) 동적 시뮬레이터**를 구현한다.
- 정상/열화/고장 조건에서 **물리적으로 타당한 시계열 데이터**를 대량 생성한다.
- `fault_type`, `fault_severity`, `anomaly_flag`, `RUL`, `event_log` 라벨을 자동 생성한다.
- 추후 FMU(Modelica) 코어로 교체 가능한 구조로 개발한다.

---

## 1. 성공 기준

### A. 물리/동특성
1. 장기 시뮬레이션에서 질량·에너지 수지 발산 없이 안정 동작
2. 급수 유량 step에서 드럼 수위의 **shrink & swell** 과도 응답 재현
3. PID 제어 포함 상태에서 압력/수위의 정상 운전 추종 가능

### B. PdM 데이터 품질
1. 고장 모드별 관측 가능한 패턴 분리
2. 고장 진행(`fault_severity`)에 따른 단조 변화(특징량) 보임
3. 라벨 자동 생성

### C. 재현성/확장성
1. YAML 시나리오 기반 실행
2. CLI로 데이터셋 생성 후 Parquet/HDF5 저장
3. 랜덤 시드 고정 재현성 확보

---

## 2. 대상 시스템

### 2.1 보일러 타입
- 1차 타깃: **Drum boiler (natural circulation)**
- 2차: once-through, HRSG

### 2.2 핵심 관측치
- `drum_pressure`
- `drum_level`
- `feedwater_flow`, `feedwater_temp` / `h_fw`
- `steam_flow`
- `steam_temp`(superheated)
- `fuel_cmd`(연료 입력)
- 상시 산출 항목: `flue_gas_temp`, `O2`, `h_fw`
- 제어 trace 항목(최종 제어 값): `fuel_cmd`, `fw_cmd`, `steam_demand`

---

## 3. 디렉터리 구조

```text
boiler_pdm_sim/
  README.md
  pyproject.toml
  configs/
    base.yaml
    faults/
      fouling.yaml
      tube_leak.yaml
      valve_stiction.yaml
      sensor_drift.yaml
    scenarios/
      load_follow.yaml
      step_tests.yaml
  src/boiler_pdm_sim/
    __init__.py
    core/
      state.py
      media.py
      components/
        drum.py
        economizer.py
        evaporator.py
        superheater.py
        valves.py
        pump.py
        combustion.py
      boiler_system.py
      solver.py
    degradation/
      base.py
      fouling.py
      tube_leak.py
      valve_stiction.py
      sensor_faults.py
      scheduler.py
    sensors/
      noise.py
      dropout.py
      sensor_model.py
    control/
      pid.py
      loops.py
    scenarios/
      profile.py
      randomization.py
      scenario.py
    dataset/
      labeling.py
      writer.py
      generator.py
    validation/
      invariants.py
      step_response.py
      regression.py
    cli/
      main.py
  tests/
    test_mass_energy_balance.py
    test_shrink_swell.py
    test_fault_injection.py
    test_reproducibility.py
  notebooks/
    quickstart.ipynb
```

---

## 4. 핵심 Python API 계약

- `BoilerSystem`
  - `reset(x0, params) -> None`
  - `derivatives(t, x, u, params) -> dxdt`
  - `outputs(x, u, params) -> y_truth`
  - `invariants(x, u, params) -> dict` (질량/에너지 체크)
  - `consistent_init(x0, params=None) -> np.ndarray` (초기/이력 상태 정합)
  - `algebraic_residual(x, u, params=None) -> dict` (대수식 잔차)
  - `project_to_feasible(x, params=None) -> np.ndarray` (물리 제약 투영)
- `BoilerSystem`은 현재 6-state ODE 기반이지만, 체적 제약을 대수식 잔차로 관리하는 semi-explicit DAE 형태로 확장 가능하게 유지
- `DegradationScheduler`
  - `update(t, params) -> params_modified`
  - `truth_labels(t) -> dict`
- `SensorModel`
  - `observe(t, y_truth) -> y_obs`
- `Simulator`
  - `run(config) -> list[dict]`
- `검증/운영 도구`
  - `python scripts/check_dataset_governance.py ...` : 데이터셋 거버넌스 검사
  - `python scripts/performance_baseline_gate.py ...` : 성능 기준선/회귀 비교 자동화

출력 데이터셋 컬럼(권장):
- `time`, `scenario_id`
- `truth/*`
- `obs/*`
- `label/fault_type`, `label/fault_severity`, `label/anomaly_flag`, `label/RUL`, `label/event_log`
- `label/event_log_history`, `label/event_log_latest`
- `meta/load_cmd`, `meta/fuel_cmd`, `meta/fw_cmd`, `meta/steam_demand_cmd`, `meta/final_control_*`
- `meta/*`

---

## 5. 물리 코어 설계 (v1)

### 5.1 상태벡터(권장)
- Drum: `P_d`, `M_l`, `M_v`, `T_w_d`(선택)
- 순환/수위 보조: `m_circ`, `m_shrink`
- semi-explicit DAE 정렬(권장): 독립 상태는 `P_d`, `M_l`, `T_w_d`, `m_circ`, `m_shrink`, 대수 상태는 `M_v`로 구성된 체적 제약(선택)

### 5.2 핵심 방정식
1. 드럼 2상 질량 수지
   - `dM_l/dt`, `dM_v/dt`
   - feedwater 유입, downdrive/riser 유출, boilup/condensation, leak 반영
   - 체적 제약은 대수식 형태(`M_l/rho_l + M_v/rho_v = V_drum`)로 보정하고, `project_to_feasible`로 초기에 정합
2. 열적 상태
   - saturation 기반 `h_l, h_v, rho_l, rho_v`(`IAPWS-IF97` 기본)
   - `saturation_temperature`, latent heat 사용
3. 수위
   - 드럼 기하에서 `V_l -> L_d` 변환
4. 순환 동역학
   - `m_circ` 상태(1차 지연) 도입
5. 열교환/연료-열 입력
   - economizer/evaporator/superheater lumped 열역학식
   - `Q_in = eta * qmax * fuel_cmd`
6. 밸브
   - `m_dot = Cv * sqrt(dp)` 형태(또는 등가 모형)

### 5.3 수치해석
- 기본: `scipy.integrate.solve_ivp`의 `BDF`/`Radau`
- 실패 시 안정화 fallback: dt 축소 재시도/수치 클램프

---

## 6. 열화/고장 라이브러리

1. **fouling**
   - `UA` 감소
   - severity progression: linear/exp/condition dependent
2. **tube_leak**
   - `m_leak = k*sqrt(P_d - P_amb)`
3. **valve_stiction**
   - deadband, hysteresis, stick-slip
4. **sensor_drift**
   - bias + drift + noise
5. **burner_deg**
   - `eta_comb` 및 heat split 저하
6. **pump_wear**
   - pump max flow/헤드 저하

고장 스케줄러 출력: onset, severity(t), params 변환, 라벨용 내부 상태.

---

## 7. 센서/데이터 생성

- 가우시안 노이즈, 저주파 드리프트, 드롭아웃, block dropout, 스파이크
- timestamp jitter(선택)
- 운영 컨텍스트 기록(load, firing cmd, ambient 등)

---

## 8. 라벨 정의(권장 규칙)

- `fault_type`: 현재 활성 고장 type 목록
- `fault_severity(t)`: 0~1
- `anomaly_flag(t)`: 잔차 기반 OR fault flag
- `RUL(t)`: 고장 임계치(또는 threshold crossing)까지 남은 시간
- `event_log`: **해당 스텝에서 발생한 이벤트만**(step event) 기록  
  (`onset`, `threshold`, `trip`, 제어기 이벤트 등)
- `event_log_history`: 시작~현재 누적 이벤트 로그  
  (`event_log`의 시간 누적본)
- `event_log_latest`: `event_log`와 동일 의미의 별칭
- `event_log` 메시지 포맷 예시  
  - `fault_name_onset_t=<sec>`
  - `fault_name_threshold_t=<sec>`
  - `fault_name_trip_t=<sec>`

#### 이벤트/라벨 스키마 확정
- 라벨 표준은 `label/event_log`를 step 이벤트(현재 스텝)로 고정.
- 감사/추적성은 `label/event_log_history`로 보장.
- 스텝 이벤트만 보려면 `label/event_log` 사용,  
  시점 전체를 보려면 `label/event_log_history` 사용.

#### 분할 저장 계약
- `sim.dataset_split` 또는 `sim.train_val_test` 를 `write_dataset`에 전달할 수 있음.
- 설정 예시:

```yaml
sim:
  dataset_split:
    enabled: true
    train: 0.7
    val: 0.15
    test: 0.15
    shuffle: true
    # counts mode(대체):
    # counts:
    #   train_count: 700
    #   val_count: 150
    #   test_count: 150
```

출력 파일:
- `<stem>.parquet` (또는 `hdf5`)
- `<stem>.train.parquet`
- `<stem>.val.parquet`
- `<stem>.test.parquet`
- `<stem>.manifest.json`

---

## 9. YAML 스펙(요약)

```yaml
sim:
  dt: 0.5
  horizon_s: 86400
  solver: "bdf"
  seed: 42
boiler:
  geometry:
    drum_radius_m: 0.8
    drum_length_m: 6.0
  nominal:
    pressure_bar: 10
    steam_flow_kg_s: 2.0
  parameters:
    UA:
      economizer: 1.2e5
      evaporator: 2.5e5
      superheater: 8.0e4
    Cv:
      steam_valve: 1.0
      feedwater_valve: 1.0
    combustion:
      eta: 0.90
      qmax_MW: 10.0
control:
  drum_level_pid: { kp: 1.2, ki: 0.05, kd: 0.0, umin: 0.0, umax: 1.0 }
  pressure_pid:   { kp: 0.8, ki: 0.02, kd: 0.0, umin: 0.0, umax: 1.0 }
faults:
  - name: fouling_evap
    type: fouling
    onset_s: 20000
    severity: { kind: linear, duration_s: 40000 }
    target: UA.evaporator
    alpha: 0.35
sensors:
  drum_pressure:
    noise_std: 0.02
    bias: 0.0
    drift_per_hour: 0.0
    dropout_p: 0.0005
```

---

## 10. 검증/테스트 계획

1. 물리 불변량 테스트
- 질량/에너지 잔차 누적/평균 임계치 통과
2. 동특성 회귀
- step test에서 드럼 수위 shrink&swell 형태 확인
3. 이벤트 정합성
- `label/event_log`의 `steam_step_up/down`와 수위 응답을 교차 검증
- `check_shrink_swell_event_consistency()` 커스텀 acceptance 기준 충족
4. 고장 주입 테스트
- severity 증가에 따른 단조 변화
- RUL threshold 일관성
5. 재현성
- 같은 seed일 때 동일 결과(또는 허용오차)

- 운영 검증 항목(필수 fail-fast)
  - `validation.required_output_columns` 기본값:
    - `truth/flue_gas_temp`
    - `truth/O2`
    - `truth/h_fw`
  - 위 필수 출력이 없으면 즉시 `validation.passed=False`로 실패 처리

6. 파이프라인 회귀 게이트
- run_to_file 분할 저장 및 매니페스트 생성
- 이벤트 로그 스키마(`event_log`, `event_log_history`, `event_log_latest`) 일관성
- `flue_gas_temp`, `O2`, `h_fw`, final control trace의 값 범위/재현성 검증

---

## 11. 옵션: FMU 연계(v2)

- 현재 v1은 Python core 우선
- v2는 OpenModelica(FMU) 코어 추가
- Python에서 co-simulation interface로 대체/대조 실행
- v2 적용 시 권장 `core_backend` 설정:

```yaml
core_backend:
  type: fmu               # python | fmu | fmi
  path: "./models/boiler_core.fmu"
  library: "pyfmi"        # pyfmi 또는 fmpy 선택
  step_size: 0.1
  time_var: "time"
  variables:
    state_names: ["P_d", "M_l", "T_w_d", "m_circ", "m_shrink"]
    input_names: ["fuel_cmd", "fw_cmd", "steam_demand"]
    output_map:
      drum_pressure: "P_drum"
      drum_level: "L_drum"
      steam_flow: "m_dot_steam"
      drum_temp_sh: "T_sh"
      feedwater_flow: "m_dot_fw"
      flue_gas_temp: "T_flue_gas"
      O2: "O2_pct"
      h_fw: "h_fw"
```

---

## 12. 개발 단계

### Phase 0 — v1.1 spec freeze 및 스키마 확정
1. `v1.1` 스키마 Freeze(2026-03-08) 선언
2. 출력/라벨/이벤트 계약(`label/event_log*`) 고정
3. `SCHEMA_LOCK` 메타 데이터 기반 `manifest.provenance.schema` 수집
4. `docs/spec_boiler_pdm_sim.md`와 `src/boiler_pdm_sim/schema.py` 단일 소스 동기화 확인

### Phase 1.5 — calibration/baseline/identify/sensitivity
1. Calibration/Identifiability 조정 파이프라인 유지 (`calibration`, `identifiability`)
2. Baseline 통계 레포트 유틸: `src/boiler_pdm_sim/research/baseline.py`
3. 식별성 지표 유틸: `src/boiler_pdm_sim/research/identifiability.py`
4. Sensitivity(민감도) 유틸: `src/boiler_pdm_sim/research/sensitivity.py`
5. `sim.analysis.phase_15` 또는 `analysis` 키로 옵션 분석 실행
   - `analysis` 블록은 `baseline/identify/sensitivity/calibration` 키를 허용
   - `analysis.calibration` 은 calibration sidecar report 계약을 제어
   - `schema_strict` 또는 `phase0/schema_strict`에서 스키마 미스매치 시 오류 처리

```yaml
sim:
  collect_performance: true
analysis:
  baseline:
    enabled: true
    channels: ["obs/drum_level", "obs/drum_pressure", "obs/steam_flow"]
    compare: true
    abs_tol: 0.2
  identify:
    enabled: true
    fault_key: "label/fault_type"
  sensitivity:
    enabled: true
    signal: "obs/drum_level"
    epsilon: 1e-3
    window: 20
  calibration:
    enabled: true
    report_path: "outputs/local_pipeline.calibration.json"
```

### Phase 1 — Skeleton & 수치 안정성
1. 디렉터리/인터페이스 정립
2. Drum 2상 단독 모델 + 간단 밸브/급수입력
3. `test_mass_energy_balance` 기본 통과
4. step scenario 최소 실행

### Phase 2 — 제어 + shrink&swell
1. 순환(lift/downcomer 등가) 추가
2. 드럼 수위/압력 PID 탑재
3. shrink&swell 테스트 통과

### Phase 3 — 고장/라벨
1. fouling, leak, stiction, sensor drift 구현
2. labeling 모듈(임계치 RUL 포함)
3. fault 주입 테스트 통과

### Phase 4 — 데이터 생성
1. 랜덤화/seed 관리
2. parquet/hdf5 writer
3. train/val/test 분할
4. 재현성 테스트 통과

### Phase 5 — 연구 유틸
1. feature extractor 예시: `src/boiler_pdm_sim/research/features.py`
2. calibration 예시: `src/boiler_pdm_sim/research/calibration.py`
3. benchmark 예시: `src/boiler_pdm_sim/research/benchmark.py`
4. custom acceptance 기준: `src/boiler_pdm_sim/validation/step_response.py`

### Phase 7 — FMU backend interface adapter
1. FMU backend adaptor 인터페이스 정의
2. Python core / FMU core 전환 라우팅 (`core_backend.type`)
3. FMU 동적 적재 및 기본 매핑 문서화
4. `core_backend.variables` 스키마 검증 강화:
   - `state_names`/`input_names` 리스트 규격 확인
   - `output_map`/`invariants`/`algebraics` 매핑 값 존재 확인
   - 누락 변수는 즉시 `[FMU_MAPPING:missing_variable]` 에러로 early-fail

### Phase 6 — Validation Battery 운영 모듈
1. 시드 배치 기준 테스트 실행기 도입 (`validation_battery`)
2. 필수 KPI/경고 KPI를 분리하여 `required`와 `warning` gate로 결과 기록
3. 실행 로그(JSONL)와 `manifest`에 배치 요약(`summaries`, 실패 내역, seed별 요약) 저장
4. 운영 단계에서 `required` 실패 시 즉시 실패 처리, `warning` 위반은 경고만 남김

### Phase 8 — scalability/throughput 최적화 및 문서 최종화
1. 성능 측정 메타 수집(`provenance.pipeline.performance`)
2. 실행량 기반 병목 가설 정리 및 문서 업데이트
3. freeze 기준 문서/스펙 갱신 로그 정리
4. 대규모 실험 시 `sim.collect_performance: true` 또는 `performance.enabled: true`로 처리량을 추적
5. `scripts/performance_baseline_gate.py`로 기준선 저장/회귀 비교 운영 자동화
6. `scripts/check_dataset_governance.py`로 승인/보존/매니페스트 감사 자동화

### 6.x 운영 실행 템플릿 (phase6)

- config 예시

```yaml
validation_battery:
  enabled: true
  seeds: [42, 99]
  summary_channels:
    - truth/drum_pressure
    - truth/drum_level
    - obs/drum_pressure
    - obs/drum_level
  required_kpis:
    truth/mass_balance_residual_max_abs:
      max: 80.0
    truth/energy_balance_residual_max_abs:
      max: 3e7
  warning_kpis:
    truth/mass_balance_residual_max_abs:
      max: 120.0
    truth/energy_balance_residual_max_abs:
      max: 6e7
```

- manifest/JSONL 출력 기대값
  - `validation_battery.enabled`: bool
  - `validation_battery.status`: `passed | warning | failed | disabled`
  - `validation_battery.required.passed`: bool
  - `validation_battery.warning.passed`: bool
  - `validation_battery.seed_failures`: list
  - `validation_battery.summaries`: seed별 KPI 요약
  - `provenance.pipeline.validation_battery`: 전체 결과 링크

### 8.x 성능/확장성 대시보드 템플릿

- 기록 대상(수집 예시)
  - `pipeline.performance.batch_size`
  - `pipeline.performance.run_seconds`
  - `pipeline.performance.write_seconds`
  - `pipeline.performance.elapsed_s`
  - `pipeline.performance.stage_seconds.control_seconds`
  - `pipeline.performance.stage_seconds.model_seconds`
  - `pipeline.performance.stage_seconds.align_seconds`
  - `pipeline.performance.stage_seconds.label_seconds`
  - `pipeline.performance.stage_seconds.write_seconds`
  - `pipeline.performance.rows_per_second`
  - `pipeline.performance.memory_profile.tracemalloc_current_bytes`
  - `pipeline.performance.memory_profile.tracemalloc_peak_bytes`
  - `.jsonl` 메타: `stage_seconds`, `memory_profile`, `validation_battery`
- 권장 병목 가설 템플릿(README/docs 고정):
  - Hypothesis: `control` / `model` / `label` / `write` 중 어떤 단계가 지연인지
- 증빙: `stage_seconds` 변화량(이전 run 대비)
- 추정 원인: 수치 적분 실패 재시도, 이벤트 생성 폭증, I/O 병목
- 개선 액션: dt 증가, profile 병합 저장, 파이프라인 병렬화, 컬럼 정규화

### 8.x 거버넌스 운영 템플릿

- 데이터셋 거버넌스 정책(권장)

```yaml
governance:
  approved_by: "operator-id"
  approved_at: "2026-03-08T10:00:00Z"
  approval_status: "approved"
  classification: "internal"
  retention_days: 365
```

- 실행 체크
  - `python scripts/check_dataset_governance.py --dataset outputs/sim_dataset.parquet --policy configs/governance_policy.yaml`
  - `python scripts/check_spec_contract.py`

---

## 13. 다음 설계 질문(필수 확정)

1. 실제 적용 보일러: drum 자연순환 / 관류식 / 패키지보일러 중 최우선 타입
2. 실제 기록 센서: pressure/level/temp/flow 항목 가용성
3. 우선 반영할 고장 Top3

이 답변으로 Spec 문서를 영속화하면 다음 대화에서

```bash
cat docs/spec_boiler_pdm_sim.md
```
으로 바로 참조할 수 있습니다.
