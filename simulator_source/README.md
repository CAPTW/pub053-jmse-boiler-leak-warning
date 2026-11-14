# Boiler PdM Simulator (Grey-box)

자연순환식 드럼 보일러를 단순화한 물리 기반(그레이박스) 시뮬레이터입니다. 드럼 동역학 + 센서 모델 + 이상 탐지 라벨링을 포함합니다.
PdM(Predictive Maintenance) 데이터셋 생성을 목적으로, 부하 변화, 제어 루프, 고장 진전, 센서 이상, 라벨 생성까지 한 번에 실행할 수 있습니다.

> **주의**: 본 시뮬레이터의 물리 코어는 PdM 연구용 저차원 grey-box 모델입니다. 실제 선박/플랜트 보일러의
> 엔지니어링급 시뮬레이션을 위한 물리 엔진 재구축 계획은 [docs/phase_a_design.md](docs/phase_a_design.md)를 참고하세요.

## 지원 기능

- 저차원 드럼 보일러 상태 모델 (`pressure`, `liquid mass`, `vapor mass`, `wall temperature`, `circulation`, `shrink/swell state`)
- PID 기반 압력/드럼 수위 제어
- 시나리오 타입
  - `load_follow`
  - `step_tests`
- 열화(고장) 스케줄러
  - Fouling (전열면 오염)
  - Tube leak (누설)
  - Valve stiction (밸브 스틱션)
  - Sensor drift (센서 드리프트/노이즈/드롭아웃)
- 시드 고정 기반 재현 가능한 데이터 생성
- 라벨/메타데이터 포함 출력
  - `label/fault_type`
  - `label/fault_severity`
  - `label/anomaly_flag`
  - `label/RUL`
- 출력 포맷
  - `parquet`
  - `hdf5`

## 프로젝트 구조

```
src/boiler_pdm_sim/   # 시뮬레이터 핵심 코드
configs/               # 기본/시나리오/고장 설정 YAML
tests/                 # 계약/물리 제약 테스트
notebooks/             # quickstart 예시
```

## 설치

```bash
python -m venv .venv
.venv\Scripts\activate
python -m pip install -e .
```

`iapws`는 필수 의존성입니다(IAPWS-IF97 물성). 미설치 환경에서는 경량 근사 물성으로 동작하며
경고가 출력됩니다. 근사 물성 사용을 차단하려면 환경변수 `BOILER_STRICT_PROPS=1`을 설정하세요.

## 실행

```bash
python -m boiler_pdm_sim.cli.main --config configs/base.yaml --out outputs/sim_dataset.parquet --format parquet --seed 42
```

기타 예시:

```bash
python -m boiler_pdm_sim.cli.main --config configs/base.yaml --out outputs/sim_dataset.h5 --format hdf5 --seed 123
```

## 테스트

```bash
python -m pytest -q
```

## 출력 컬럼

- `time`, `scenario_id`
- `truth/*`: 상태/파생 물리량
- `obs/*`: 센서 관측값(노이즈/드롭아웃 반영)
- `label/*`: 고장 라벨/심각도/RUL/이상 플래그
- `meta/*`: 시드/스텝 정보

### 예시 출력 스키마

| 계층 | 컬럼 | 설명 |
|---|---|---|
| 공통 | `time` | 시뮬레이션 시간(초) |
| 공통 | `scenario_id` | 사용한 시나리오 타입(`load_follow`, `step_tests` 등) |
| Truth | `truth/drum_pressure` | 드럼 압력(bar) |
| Truth | `truth/drum_level` | 드럼 수위(m) |
| Truth | `truth/steam_flow` | 증기 유량(제어 신호 기반, kg/s 기준 스케일) |
| Truth | `truth/steam_flow_true` | 실제 모델 유량 상태값 |
| Truth | `truth/drum_temp_sh` | 과열기 출구(급수/증기측) 온도 기준값(°C) |
| Truth | `truth/feedwater_flow` | 급수 유량(kg/s) |
| Truth | `truth/m_boil` | 증발 유량(kg/s) |
| Truth | `truth/m_leak` | 누설 유량(kg/s) |
| Truth | `truth/wall_temp` | 배럴/벽면 온도(°C) |
| Truth | `truth/vapor_mass` | 증기 질량(kg) |
| Obs | `obs/drum_pressure` | 센서 노이즈/드롭아웃 반영 압력 |
| Obs | `obs/drum_level` | 센서 노이즈/드롭아웃 반영 수위 |
| Obs | `obs/steam_flow` | 센서 노이즈/드롭아웃 반영 증기유량 |
| Obs | `obs/drum_temp_sh` | 센서 노이즈/드롭아웃 반영 과열기 온도 |
| Label | `label/fault_type` | 현재 활성 고장 타입 |
| Label | `label/fault_severity` | 통합 고장 심각도(0~1 근사) |
| Label | `label/anomaly_flag` | 이상 발생 플래그(0/1) |
| Label | `label/RUL` | 고장 한계치 대비 잔여 수명 추정치 |
| Meta | `meta/seed` | 시뮬레이션 시드 |
| Meta | `meta/step` | 타임스텝 인덱스 |

## 설정 파라미터 안내

| 섹션 | 키 | 의미 |
|---|---|---|
| `sim` | `dt` | 시뮬레이션 적분 간격(초) |
| `sim` | `horizon_s` | 시뮬레이션 총 시간(초) |
| `sim` | `solver` | 적분기 `euler`, `BDF`, `Radau` 등 SciPy 지원(대소문자 무관) |
| `sim` | `seed` | 재현용 랜덤 시드 |
| `sim` | `format` | 기본 출력 포맷(`parquet`/`hdf5`) |
| `boiler.geometry` | `drum_radius_m` | 드럼 반경(m) |
| `boiler.geometry` | `drum_length_m` | 드럼 길이(m) |
| `boiler.nominal` | `pressure_bar` | 정상 동작 기준 압력 |
| `boiler.nominal` | `steam_flow_kg_s` | 정격 증기 유량(참조) |
| `boiler.nominal` | `feedwater_mass_kg` | 총 급수 질량(참조) |
| `boiler.nominal` | `level_fraction` | 초기 수위 비율 |
| `boiler.parameters.UA` | `economizer` | 절탄기 전열 계수 |
| `boiler.parameters.UA` | `evaporator` | 증발기 전열 계수(파울링 고장 영향) |
| `boiler.parameters.UA` | `superheater` | 과열기 전열 계수 |
| `boiler.parameters.Cv` | `steam_valve` | 증기 밸브 유량 계수 |
| `boiler.parameters.Cv` | `feedwater_valve` | 급수 밸브 유량 계수 |
| `boiler.parameters.combustion` | `eta` | 연소 효율 |
| `boiler.parameters.combustion` | `qmax_MW` | 최대 입열(MW) |
| `boiler.parameters.losses` | `wall_loss_W` | 벽면 손실(W) |
| `boiler.parameters.dynamics` | `pressure_gain` | 체적 오차 기반 압력 응답 계수 |
| `boiler.parameters.dynamics` | `pressure_mass_gain` | 질량 불균형 기반 압력 응답 계수 |
| `boiler.parameters.dynamics` | `circum_tau_s` | 순환계 1차 지연 |
| `boiler.parameters.dynamics` | `circ_tau_s` | 순환계 1차 지연(호환 스키마로 사용) |
| `boiler.parameters.dynamics` | `shrink_tau_s` | shrink/swell 상태 지연 |
| `boiler.parameters.dynamics` | `wall_tau_K` | 벽 열용량 시간상수 스케일 |
| `boiler.parameters.limits` | `mdot_fw_max_kg_s` | 급수 최대 유량 |
| `boiler.parameters.limits` | `mdot_s_nom_kg_s` | 정격 증기 유량 |
| `control.drum_level_pid` | `kp,ki,kd` | 드럼 수위 PID 계수 |
| `control.drum_level_pid` | `setpoint_level_m` | 드럼 수위 목표치 |
| `control.drum_level_pid` | `out_feedforward` | 피드포워드 기준값 |
| `control.pressure_pid` | `kp,ki,kd` | 압력 PID 계수 |
| `control.pressure_pid` | `setpoint_pressure_bar` | 압력 목표치 |
| `sensors.*` | `noise_std` | 센서 가우시안 노이즈 표준편차 |
| `sensors.*` | `bias` | 바이어스 오프셋 |
| `sensors.*` | `drift_per_hour` | 시간 경과 드리프트 |
| `sensors.*` | `dropout_p` | 드롭아웃 확률 |
| `sensors.drum_pressure` | `spike_p`, `spike_std` | 스파이크 주입 확률 및 크기 |
| `randomization` | `enable` | 랜덤화 여부 |
| `randomization.drift_std_pct` | `UA_evap` | 증발기 UA 확률적 편차 |
| `randomization.drift_std_pct` | `combustion_eta` | 연소 효율 편차 |
| `randomization.drift_std_pct` | `feedwater_max` | 급수 최대 유량 편차 |

## 참고

- `configs/base.yaml`을 기준으로 기본 파라미터를 구성할 수 있습니다.
- 설정값이 문자열 수치로 들어와도 실행 경로에서 정규화가 일어나도록 방어 코드를 넣어두었습니다.
- 본 프로젝트는 **공정 제어/학습용 샘플링 모델**이므로, 실제 설비 제어/안전 검증용 정밀 모델로 쓰이지 않습니다.

## Data format updates (2026-03-07)

- Dependencies now explicitly include:
  - `pyarrow>=12.0`
  - `tables>=3.8`
- Label schema normalization:
  - `label/fault_type` is always a string (`"none"` or one fault type).
  - Additional fault list is still available as `label/fault_types` for compatibility.
- Event logs now include extra trace entries:
  - `*_onset_t=...`
  - `*_threshold_t=...`
  - `*_trip_t=...`
  - `sat_level_pid_*`, `sat_pressure_pid_*` when PID saturation occurs.

## Solver and controller notes

- `integrate_step` now retries with reduced step sizes when SciPy integration fails and falls back to Euler.
- Solver method names are case-insensitive (`bdf` → `BDF`); unknown names fail fast instead of silently falling back.
- PID controllers include back-calculation anti-windup via `antiwindup_gain` in control config (default `1.0`).

## Local pipeline quickstart

### Local run matrix

| Mode | Config | Dataset output | Perf log | Baseline | Primary use |
|---|---|---|---|---|---|
| Normal pipeline | `configs/local_pipeline.yaml` | `outputs/local_pipeline.parquet` | `outputs/local_pipeline.perf.jsonl` | `outputs/baseline_perf.jsonl` | 일반 로컬 개발, governance, calibration, baseline 비교 |
| Step tests | `configs/local_pipeline_step_tests.yaml` | `outputs/local_pipeline_step_tests.parquet` | `outputs/local_pipeline_step_tests.perf.jsonl` | `outputs/baseline_step_tests.perf.jsonl` | controller step response, shrink/swell, step regression |

Current local perf note (2026-03-09): `step_tests` with `calibration.enabled=false` profiles at about `0.97s` total (`derivatives 0.346s`, `outputs 0.157s`, `invariants 0.198s`, `observe 0.103s`), and both local baseline compares are currently passing.
Phase 8 perf milestone: the current tuning cycle keeps both normal and step-tests baseline gates green while holding the short `step_tests` profile under `1.0s` total with `invariants()` around `0.198s`.

### Normal pipeline

Generate a local development dataset with calibration, governance metadata, and performance logging enabled:

```powershell
python -m boiler_pdm_sim.cli.main --config configs/local_pipeline.yaml --out outputs/local_pipeline.parquet --format parquet
```

Run governance checks for the generated artifact:

```powershell
python scripts/check_dataset_governance.py --dataset outputs/local_pipeline.parquet --policy configs/governance_policy.yaml
```

Initialize a local performance baseline from the latest run:

```powershell
python scripts/performance_baseline_gate.py --current outputs/local_pipeline.perf.jsonl --baseline outputs/baseline_perf.jsonl --mode init
```

Compare a new run against the saved local baseline:

```powershell
python scripts/performance_baseline_gate.py --current outputs/local_pipeline.perf.jsonl --baseline outputs/baseline_perf.jsonl --mode compare --min-rows-ratio 0.90 --max-stage-ratio 1.30
```

### step_tests pipeline

Generate a short step-response dataset for local controller and shrink/swell checks:

```powershell
python -m boiler_pdm_sim.cli.main --config configs/local_pipeline_step_tests.yaml --out outputs/local_pipeline_step_tests.parquet --format parquet
```

Run governance checks for the step-tests artifact:

```powershell
python scripts/check_dataset_governance.py --dataset outputs/local_pipeline_step_tests.parquet --policy configs/governance_policy.yaml
```

Initialize the dedicated `step_tests` performance baseline:

```powershell
python scripts/performance_baseline_gate.py --current outputs/local_pipeline_step_tests.perf.jsonl --baseline outputs/baseline_step_tests.perf.jsonl --mode init
```

Compare a new `step_tests` run against that dedicated baseline:

```powershell
python scripts/performance_baseline_gate.py --current outputs/local_pipeline_step_tests.perf.jsonl --baseline outputs/baseline_step_tests.perf.jsonl --mode compare --min-rows-ratio 0.90 --max-stage-ratio 1.30
```

### Local automation shortcut

Run the full local pipeline, governance gate, optional baseline handling, and summary generation in one command:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local_pipeline.ps1 -Config configs/local_pipeline.yaml -InitBaseline
```

### FMU config roles

Use the two FMU configs for different purposes:

| Config | Role | Typical use |
|---|---|---|
| `configs/base_fmpy.yaml` | External FMU target config | Use this when you have a real vendor or external `.fmu` and want the parity/e2e suite to run against that artifact. |
| `configs/dummy_fmpy.yaml` | Synthetic FMU harness config | Use this for local FMU adapter and parity harness validation with the generated dummy `models/boiler_core.fmu`. |

Current real-FMU test suite entry points:

- `tests/test_real_fmu_parity.py`
- `tests/test_real_fmu_e2e.py`

To switch the existing suite to an external FMU, point the suite at `configs/base_fmpy.yaml` and either update `core_backend.path` there or override the path with an environment variable:

```powershell
$env:BOILER_REAL_FMU_CONFIG = "configs/base_fmpy.yaml"
$env:BOILER_REAL_FMU_PATH = "C:\path\to\external\boiler_model.fmu"
python -m pytest -q -rs tests/test_real_fmu_parity.py tests/test_real_fmu_e2e.py
```

Notes:

- `BOILER_REAL_FMU_CONFIG` selects which FMU config the suite reads.
- `BOILER_REAL_FMU_PATH` overrides `core_backend.path` in that config.
- If neither override is set, the suite falls back to the path defined in the selected config file.
- Keep `configs/dummy_fmpy.yaml` for synthetic harness validation; use `configs/base_fmpy.yaml` for actual external FMU runs.

Step-tests variant:

```powershell
powershell -ExecutionPolicy Bypass -File scripts/run_local_pipeline.ps1 -Config configs/local_pipeline_step_tests.yaml
```

Generate a standalone performance summary report from an existing log:

```powershell
python scripts/performance_summary_report.py --current outputs/local_pipeline_step_tests.perf.jsonl --baseline outputs/baseline_step_tests.perf.jsonl --output outputs/local_pipeline_step_tests.perf.summary.md --format markdown
```

## Operational templates (validation_battery + performance)

- Add `validation_battery` in run config to execute seed-sweep KPI checks.
- Split KPI gate:
  - `required_kpis`: fail the job when violated.
  - `warning_kpis`: record warnings only (`RuntimeWarning`).
- Results are written to:
  - Manifest: `provenance.validation_battery`
  - JSONL: configured `performance.validation_battery.log_path` (or `<out>.validation_battery.jsonl`).
- Performance logging fields now include:
  - `batch_size`, `run_seconds`, `write_seconds`, `stage_seconds` (control/model/align/label/write), `memory_profile`.
- For bottleneck review, keep a simple template in docs:
  - Hypothesis, evidence (`stage_seconds` delta), root cause, action plan, impact.

## Local verification tests

Run the targeted local regression tests after pipeline/config/schema changes:

```powershell
python -m pytest -q tests/test_simulator_run_to_file_smoke.py tests/test_schema_event_grammar.py tests/test_governance_policy_contracts.py tests/test_manifest_integrity.py
```
