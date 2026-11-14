# Phase A 상세 설계 — 선박 보조보일러 물리 코어 재구축

- 문서 버전: v1.1 (2026-06-11) — 4-agent 적대적 리뷰(물리/아키텍처/실행성/수정검증) blocking 14건 반영
- 대상 독자: boiler_pdm_sim 개발자
- 선행 문서: [blueprint.md](../blueprint.md), 전수조사 결과(2026-06-11 멀티에이전트 감사)
- 상태: 구현 착수 가능

---

## 1. 목적과 범위

### 1.1 목표

현재의 5-상태 grey-box 코어(부피오차 게인 기반 압력, placeholder 열교환기, 경험적 순환/shrink-swell)를
**에너지 보존 기반의 물리 코어**로 교체하여, 선박 보조보일러(7~18 bar, 1~10 t/h, MGO/HFO)의
PdM 데이터 생성이 **물리적으로 외삽 가능한 기반** 위에서 이루어지게 한다.

Phase A 완료 시점의 정의(Definition of Done) — 각 항목에 대응 게이트를 명시:

| # | DoD | 판정 게이트 |
|---|---|---|
| 1 | Åström–Bell 4-상태 모델이 새 백엔드(`ab4`)로 동작, 보존 잔차 통과 | §7.1 |
| 2 | 물성 계층이 IF97 region 1/2/4를 0.5~120 bar에서 제공, 근사 폴백 차단 | §7.0 |
| 3 | 연료→공기→연소→연도가스 경로가 질량·에너지 수지로 닫힘 | §7.1 가스측 잔차 게이트 |
| 4 | 제어/안전 루프가 config 플래그로 obs를 소비 가능 | §7.6 truth/obs KPI 비교 |
| 5 | AB 벤치마크 회귀 + datasheet anchoring이 CI에서 동작 | §7.2, §7.3 |
| 6 | 기존 grey-box 백엔드와 PdM 파이프라인이 깨지지 않음 | A1 golden-row bit-parity + 기존 52 테스트 그린 |

### 1.2 비범위 (Phase B 이후로 명시적 연기)

- 가스측 다중 노드 열교환기 캐스케이드(furnace 복사/대류 분할, 튜브뱅크별 ε-NTU) → **Phase B**
  (Phase A는 단일 furnace 노드 + LMTD 기반 총괄 UA로 닫는다 — §3.3)
- downcomer/riser 운동량 ODE 기반 자연순환 → **Phase B**
  (Phase A의 순환은 Åström–Bell의 정적 균형식 — 경험 지연이 아닌 물리식이지만 1-노드)
- 60 bar급 주보일러, 과열기 금속온도/attemperation → **Phase C**
- 선체 운동(roll/pitch), composite/EGE, BOG → **Phase D**
- 실시간 런타임/HIL, BMS 시퀀스(purge/ignition) → Tier 2 별도 트랙
- 스키마 v2 (Phase A는 v1.1 컬럼 계약 유지, truth 채널 additive 추가만 — §8)

단, **blowdown은 Phase A에 포함**한다(리뷰 반영): 선박 보조보일러의 일상 운전 항목이고
구현 비용이 `q_leak` 재사용 수준이므로 연기할 이유가 없다(§3.5).

### 1.3 완료된 선행 작업 (2026-06-11)

- git 저장소 초기화, 베이스라인 커밋, README 인코딩 복구, 루트 임시파일 제거
- `solver: "bdf"` 오타 수정(4개 config + 기본값 + spec 예시) + 솔버명 케이스 정규화/fail-fast,
  run() 시작 시점 사전 검증
- iapws 폴백 RuntimeWarning(원인 예외 포함) + `BOILER_STRICT_PROPS=1` hard-fail
- CI pytest job(strict props), `[test]`/`[fmu]` extras, conformal 구간순서 버그 수정
- 전체 테스트 52/52 통과 (venv, iapws+fmpy 설치)

---

## 2. 목표 아키텍처

### 2.1 백엔드 계약 재정의 (A1)

현재 문제: `pipeline/step_loop.py:136-143`이 백엔드와 무관하게 상태벡터를 5원소 경계로
`np.clip`하므로 상태 차원이 다른 코어는 즉시 깨진다. 또한 제어·안전이 truth를 직접 소비한다.

**현재 호출 패턴 (계약 설계의 전제 — 리뷰에서 확인된 실제 call site):**

| call site | 호출 | 의미 |
|---|---|---|
| step_loop.py:39 | `system.state` | 루프 진입 시 초기 상태 취득 |
| step_loop.py:41 | `outputs(x, control, params)` | 초기 y (un-faulted params) |
| step_loop.py:86 | `invariants(x, control, params_faulted)` | 스텝 전 상태 + **인터록 적용 전** control |
| step_loop.py:112 | `outputs(x, control, params_faulted)` | y_truth — 스텝 전 상태 + **인터록 적용 후** control |
| step_loop.py:121 | `set_prev_steam_demand(...)` | shrink/swell 펄스용 이전 demand 추적 |
| step_loop.py:148 | `outputs(x_next, control, params_faulted)` | next_y — 스텝 후 상태 (다음 iteration controller 입력) |
| simulator.py:355-372 | `align_algebraic_state(...)` | 매 스텝 projection + meta/algebraic_* 컬럼 생산 |
| simulator.py:540 | `step(t, x, control, dt)` (FMU) / `derivatives` (python) | 적분 |

**새 계약** — `core/backend_protocol.py`. 무인자 `outputs()`는 위 패턴(스텝 전 상태 + 새 control로
2회, 스텝 후 상태로 1회)을 표현할 수 없으므로(리뷰 blocking), **명시적 인자형**으로 정의한다:

```python
class CoreBackend(Protocol):
    """Opaque-state physics backend contract.

    The orchestration layer never inspects or clips the state vector;
    bounds, projection/alignment, and consistency are the backend's
    responsibility and are reported via StepReport.
    """

    def reset(self, x0: Mapping[str, float] | None, params: Mapping[str, Any]) -> None: ...
    def advance(self, t: float, dt: float, inputs: BackendInputs,
                params: Mapping[str, Any], *, method: str = "BDF") -> StepReport: ...
    def outputs(self, inputs: BackendInputs,
                params: Mapping[str, Any]) -> dict[str, float]: ...
    def invariants(self, inputs: BackendInputs,
                   params: Mapping[str, Any]) -> dict[str, float]: ...
    @property
    def state_names(self) -> list[str]: ...   # 로깅 전용
```

- **명명 결정 (A1 구현에서 확정)**: 스테핑 메서드는 `step`이 아니라 **`advance`**다.
  FMUCoreAdapter가 FMI 의미론의 공개 `step(t, x, u, dt)`를 이미 노출하고 기존 테스트가 이를
  직접 호출하며, 구 `_step_system`의 디스패치가 `getattr(system, "step", None)`이었으므로 같은
  이름을 재사용하면 디스패치 의미가 조용히 바뀐다. solver method는 `advance`의 키워드 인자.
- `outputs`/`invariants`는 **백엔드의 현재 내부 상태**를 기준으로 주어진 (inputs, params)에서
  대수 출력을 평가한다. step() 전 호출 = 스텝 전 truth, step() 후 호출 = 스텝 후 truth.
  → 기존 row 의미론(위 표)이 그대로 보존된다. **temporal contract**: truth row는
  "스텝 전 상태 × 인터록 적용 후 control"(y_truth)이며, 다음 iteration의 controller 입력은
  "스텝 후 상태"(next_y) — 이 의미를 바꾸지 않는 것이 A1 수용 기준이다.
- `set_prev_steam_demand`는 protocol에서 제거: `BackendInputs.steam_demand`가 매 스텝
  전달되므로 이전값 추적은 백엔드 내부 책임으로 흡수한다.

```python
@dataclass(frozen=True)
class BackendInputs:
    fuel_cmd: float          # 0..1 정규화 명령 (기존 계약 유지)
    fw_cmd: float            # = 급수밸브 opening (§3.5에서 확정)
    steam_demand: float
    boundary: Mapping[str, float] = field(default_factory=dict)
    # Phase A 예약 키: "T_fw_C", "T_air_C", "P_downstream_bar",
    #                  "P_feedtank_bar", "lambda_excess_air"
    # Phase B+ 예약 키: "exh_gas_T_C", "exh_gas_mdot_kg_s", "list_deg", "roll_deg"

@dataclass
class StepReport:
    x_after: np.ndarray              # 로깅용 (불투명 — 루프는 해석하지 않음)
    solver: dict[str, Any]           # requested_method/solver_used/retry_count/fallback_used
    alignment: dict[str, Any]        # residual_before_m3/residual_after_m3/iterations/feasible/source
    events: list[str]                # state_clamp_t=*/algebraic_*_t=*/solver_* — 기존 포맷 유지
```

**마이그레이션 규칙** (리뷰 반영 — "클립 위치만 이동"은 등가가 아니므로 폐기):

1. **alignment + clip + 이벤트 감지를 통째로** `BoilerSystem.step()`(신규 작성) 내부로 이동한다.
   순서(`_step_system → align → clip → 이벤트 감지`)와 이벤트 문자열 포맷
   (`state_clamp_t=*`, `algebraic_*` — SCHEMA_LOCK event_patterns, meta/solver_correction_count에
   연결됨)을 보존하고, **golden-row bit-parity 테스트**(동일 config/seed에서 리팩터 전후
   parquet row가 bit-identical)를 A1 수용 기준으로 한다.
2. legacy 멤버(`state`, `consistent_init`, `dae_partition`, `algebraic_state_names`,
   `align_algebraic_state`)는 **`LegacyStateBackend` 확장 protocol**로 분리한다.
   `BoilerSystem`과 `FMUCoreAdapter`는 CoreBackend + LegacyStateBackend를 모두 구현하고
   (기존 테스트 — test_dae_closure, test_fmu_e2e:179의 `dae_partition()["algebraic"]==[5]` —
   를 깨지 않기 위함), `ab4`는 CoreBackend만 구현한다. 루프는 CoreBackend만 사용하고
   legacy 멤버는 capability 검사 후에만 접근한다.
3. **FMU adapter shim이 A1 범위에 포함된다**: FMUCoreAdapter의 구 시그니처
   `step(t, x, control, dt)`를 새 `step(t, dt, inputs, params)`로 감싸는 어댑터 작업.
   (ADR-2의 "FMU는 Phase C 재심사"는 *고충실도 외부 FMU 도입*에 대한 것이고,
   기존 FMU 백엔드의 **인터페이스 호환 유지**는 A1 범위다.)
4. `simulator._step_system` / `_extract_algebraic_alignment`의 silent `except: pass`는 제거하고
   StepReport로 승격한다 (현재 except가 새 시그니처의 TypeError까지 삼킬 수 있어 특히 위험).
5. `backend_factory.build_core_backend`에 `"ab4"` 분기 추가. `"python"`/`"fmu"` 분기 유지 —
   기존 grey-box는 fast backend로 보존되어 PdM 대량 생성과 cross-model 회귀에 쓰인다.

### 2.2 모듈 배치

```
src/boiler_pdm_sim/core/
  backend_protocol.py      # 신규: CoreBackend / LegacyStateBackend / BackendInputs / StepReport
  backend_factory.py       # 수정: "ab4" 분기 추가
  boiler_system.py         # 유지: 기존 grey-box (step() 신규 작성 — alignment/clip/이벤트 내재화)
  ab4/                     # 신규: Phase A 물리 코어
    drum_model.py          # Åström–Bell 4-상태 ODE (§3.1)
    furnace.py             # 연소·연도가스 수지 (§3.3)
    feedwater.py           # 급수 라인: 펌프 곡선 ∩ 밸브 (§3.5)
    steam_line.py          # 증기 라인: 밸브/부하/blowdown (§3.5)
    geometry.py            # 수평 원통 드럼 비선형 level-volume (§3.4)
  props/                   # 신규: 물성 계층 (§3.2)
    if97.py                # iapws 기반 스플라인 테이블 + 도함수 (캐시 정책 §3.2)
    gas.py                 # 연도가스 enthalpy h_gas(T) 테이블 (§3.3)
    fuels.py               # MGO/HFO 연료 물성 객체
  media.py                 # 유지(legacy 전용) — grey-box만 사용, props로 신규 코드 유입 금지
  thermo/                  # 기존 호환 shim (media 재수출) — deprecated 표기 후 Phase B에서 제거,
                           #   props/와의 혼동 방지를 위해 모듈 docstring에 명시
```

---

## 3. 물리 모델 설계

### 3.1 드럼보일러 코어 — Åström–Bell 4-상태 모델

기준 문헌: K.J. Åström, R.D. Bell, "Drum-boiler dynamics", *Automatica* 36 (2000) 363–378.
선정 이유: (1) 에너지 보존 기반이라 용량/압력대 외삽에 물리적 근거가 있고, (2) shrink/swell
비최소위상 거동이 **구조에서 자연히 발생**하며(현재의 tanh hack 불필요), (3) 논문에
**160 MW 실플랜트(P16-G16, Öresundsverket)** 실측 응답이 수록되어 있어 구현 검증 기준으로
쓸 수 있고, (4) 4 상태라 PdM 대량 생성 throughput과 양립한다.

상태벡터:

| 상태 | 기호 | 의미 |
|---|---|---|
| `p` | p | 드럼 압력 [Pa] |
| `V_wt` | V_wt | 계 전체 물(액상) 체적 [m³] |
| `alpha_r` | α_r | riser 출구 증기 질량 분율 [-] |
| `V_sd` | V_sd | 드럼 수면 아래 증기 체적 [m³] |

지배방정식 (Åström–Bell Eq.(1)–(5) 정합 — 리뷰 물리 검증 통과):

**(E1) 전역 질량 보존**

```
d/dt [ρ_s·V_st + ρ_w·V_wt] = q_f − q_s − q_leak − q_bd
```

**(E2) 전역 에너지 보존**

```
d/dt [ρ_s·h_s·V_st + ρ_w·h_w·V_wt − p·V_t + m_t·C_p·t_s]
    = Q + q_f·h_f − q_s·h_s − (q_leak + q_bd)·h_w
```

- `V_st = V_t − V_wt`, `t_s = Tsat(p)`: 금속온도는 포화온도를 따른다(Åström–Bell 가정 —
  기존 코어의 "T_w 280°C 고정" 문제가 구조적으로 사라짐)
- `q_leak`: tube_leak 고장 주입점, `q_bd`: blowdown(§3.5) — 둘 다 포화수 엔탈피 동반 유출
- 금속 질량은 `m_t`(전체) 외에 riser 식의 `m_r`, 드럼 응축항의 `m_d` 분할이 필요하다
  — 소싱 절차는 §9 A3 (벤더 GA/전열면적/circulation ratio 역산)

**(E3) riser 증기 분율 동역학** — riser 질량·에너지 수지에서 α_r ODE 유도.
평균 보이드율 `ᾱ_v(α_r, p)`는 논문 Eq.(19) 해석식 사용.
증발 열입력 `Q`는 furnace 노드(§3.3)가 공급.

**(E4) 드럼 수면 아래 증기 체적**

```
dV_sd/dt = (응축/수면 통과 항: ρ_s, β 기반) − (V_sd − V_sd⁰)/T_d 완화항
```

- `T_d`(드럼 증기 체류시간), `β`(수면 통과 증기 계수), `V_sd⁰`: 경험 파라미터.
  **P16 값을 이식하지 않는다**(85 bar에서 식별된 값 — 7 bar는 ρ_w/ρ_s가 ~17배 달라 무효).
  T_d는 물리 정의 `T_d ≈ ρ_s·V_sd⁰/q_s,rated`에서 marine 정격으로 직접 산출하고,
  β/V_sd⁰는 §7.4의 저압 sanity test와 `research/sensitivity.py` 스크리닝으로 범위를 잡는다.

**순환 유량** (정적 균형 대수식 — Phase A):

```
q_dc = sqrt( 2·ρ_w·A_dc·(ρ_w − ρ_s)·g·ᾱ_v·V_r / k_friction )
```

Phase B에서 운동량 ODE로 승격하며, 구동수두 항에 선체 경사(`g → g·cos θ`)가 들어갈 자리를
이때 마련한다.

**드럼 수위 출력** (비최소위상이 자연 발생):

```
l = level_from_volume(V_wd + V_sd)          # §3.4 비선형 기하
V_wd = V_wt − V_dc − (1−ᾱ_v)·V_r
```

ODE는 질량행렬 형태 `M(x)·dx/dt = f(x,u)`로 정리한다. M(x)에는 포화선 물성 도함수가
들어가며 §3.2가 **C1-연속**으로 제공한다(BDF Jacobian 전제 — §3.2 캐시 정책 참조).

### 3.2 물성 계층 — `props/if97.py`

| 항목 | 사양 |
|---|---|
| 범위 | 0.5~120 bar (Phase C 마진), 포화선 + 과열 region 2 |
| 제공 물성 | Tsat, ρ_w, ρ_s, h_w, h_s, u_w, u_s, cp + 포화선 도함수 ∂ρ_w/∂p, ∂ρ_s/∂p, ∂h_w/∂p, ∂h_s/∂p, ∂Tsat/∂p |
| 백엔드 | `iapws` (필수 의존성) — 빌드타임에 테이블 생성 |
| **평활성** | **ab4 RHS 경로에 rounding cache 금지.** iapws 직접 호출 대신 0.5~120 bar 구간 **cubic spline 사전 테이블**(생성 시 iapws 호출, 이후 spline 평가)로 물성과 도함수를 함께 제공한다. 도함수는 **spline 미분**으로(중앙차분 불필요·격자 오염 없음). 근거: 기존 media.py의 1e-3 bar 반올림 lru_cache는 RHS를 p에 대해 계단함수로 만들어 BDF의 FD Jacobian(섭동 ~0.01 Pa ≪ 격자 100 Pa)을 0/스파이크로 망가뜨린다 — R2를 설계가 자초하는 구조라 금지(리뷰 blocking #4). |
| 정확도 게이트 | §7.0: IF97 reference point 대조(스플라인 보간 오차 < 0.1%), 도함수 정확도, 경계(0.5/120 bar) 동작, iapws 부재 시 import 실패 |
| 폴백 | 없음 — `props/`는 iapws 없이 import 자체가 실패. media.py의 폴백은 legacy grey-box 전용으로 격리 |

CoolProp은 Phase B 프로파일링 후 옵션 백엔드로 검토(스플라인 테이블 생성기만 교체하면 됨).

### 3.3 연소·연도가스 경로 — `core/ab4/furnace.py`

**연료 객체** (`props/fuels.py`) — AFR은 독립 필드가 아니라 **조성에서 유도**한다
(리뷰: 문서값 14.6/14.0은 자체 조성과 1.6~2.9% 불일치 — λ↔O2 자기모순 원인):

```python
@dataclass(frozen=True)
class Fuel:
    name: str            # "MGO", "HFO"
    LHV_MJ_kg: float     # MGO 42.7, HFO 40.5
    C_mass: float        # MGO 0.866, HFO 0.86
    H_mass: float        # MGO 0.128, HFO 0.105
    S_mass: float        # MGO 0.001, HFO 0.025

    @property
    def O2_stoich_kg_per_kg(self) -> float:
        return 2.664 * self.C_mass + 7.937 * self.H_mass + 0.998 * self.S_mass

    @property
    def AFR_stoich(self) -> float:          # MGO ≈ 14.4, HFO ≈ 13.6
        return self.O2_stoich_kg_per_kg / 0.232
```

**가스측 수지** — quasi-steady, **enthalpy 기반**(cp·ΔT 형태 금지 — 온도 의존 cp에서
에너지 불폐합을 만들고 §7.1 게이트가 즉시 잡는다. 리뷰 blocking #3):

```
q_fuel  = fuel_cmd · q_fuel_max
λ       = boundary.get("lambda_excess_air", config 기본 1.15)
q_air   = λ · AFR_stoich · q_fuel
q_gas   = q_air + q_fuel

연소열    Q_comb = q_fuel · LHV · η_comb            # η_comb: 연소 완전도 (burner_deg 주입점)
단열온도   T_ad: Q_comb = q_gas · [h_gas(T_ad) − h_gas(T_air)] 에서 역산
          # h_gas(T): 조성(CO2/H2O/N2/O2/SO2) 몰가중 enthalpy 테이블, 범위 25~2,200°C
수측 전달  Q_to_water = UA_eff · LMTD(T_ad → T_stack ; Tsat)   # 단일 노드, T_stack은 수지로 닫힘
배기손실   L_stack = q_gas · [h_gas(T_stack) − h_gas(T_air)]
벽손실    L_wall = f_wall · Q_comb (config 상수 분율, 기본 0.015) — 수측 Q에서 차감하여 출구 명시:
          Q_to_drum = Q_to_water − L_wall
폐합     Q_comb = Q_to_water + L_stack  (가스측 수지 잔차 → invariants, §7.1 게이트)
```

**효율** — 분모는 **연료 투입열**(벤더 datasheet 기준과 일치, 리뷰 blocking #2):

```
직접법:   η_boiler = Q_to_drum / (q_fuel · LHV)
간접법(검산): η_boiler = 1 − (L_stack + L_wall + L_unburned) / (q_fuel · LHV)
          L_unburned = q_fuel · LHV · (1 − η_comb)
```

이 정의에서 burner_deg(η_comb↓)가 η_boiler에 직접 나타난다(기존 정의는 분모가 Q_comb라
열화 시그니처가 상쇄 — 리뷰 지적).

**O2 (건가스 몰수지, 불완전연소 반영)** — 차원 불일치 스케치식은 폐기(리뷰):

```
연소된 연료분  q_burn = η_comb · q_fuel  →  O2 소비/CO2·H2O·SO2 생성은 q_burn 기준 몰수지
잔여 O2 몰분율(dry basis) = [공급 O2 − 소비 O2] / 건가스 총 몰수
```

→ λ 고정이어도 η_comb↓ 시 O2가 상승하여 **burner_deg의 O2 관측성이 성립**한다
(§5 매핑의 성립 조건).

이 구조로 fouling(UA_eff↓ → T_stack↑ → η↓), burner_deg(η_comb↓ → O2↑·η↓), 연료 전환
(MGO↔HFO 조성/LHV)이 전부 물리 인과로 데이터에 나타난다.

### 3.4 드럼 기하 — 수평 원통 비선형 level-volume

```
V(l) = L · [ r²·acos((r−l)/r) − (r−l)·sqrt(2rl − l²) ]
```

수위는 `l = V⁻¹(V_wd + V_sd)`를 Newton 1~2회로 역산(초기값: 직전 수위).
**가드**: l→0, l→2r에서 dV/dl→0이므로 Newton 스텝에 [l_min, l_max] bracket과
bisection 폴백을 둔다(리뷰 지적).

### 3.5 급수/증기 라인 — `feedwater.py`, `steam_line.py`

**급수 라인 (닫는 식 명시 — 리뷰 blocking)**:

- 역할 확정: **`fw_cmd` = 급수밸브 opening**, 펌프 속도 N = 1.0 고정(Phase A).
- 펌프 곡선: `ΔP_pump(q) = a0 − a1·q²` (정격점 + 차단양정 2점으로 결정).
  `pump_wear`는 `a0·(1−wear)`로 매핑 — 제어기가 밸브를 더 열어 보상하는 PdM 시그니처가
  자연 발생.
- 급수유량은 직렬 압력 균형에서 대수적으로 결정:

```
P_feedtank + ΔP_pump(q_fw) = P_drum + ΔP_valve(q_fw, opening)
ΔP_valve = (q_fw / (Cv_SI · opening))² / ρ_w        # SI 정합 (기존 bar 단위 혼용 수정)
```

- boundary 예약 키: `"P_feedtank_bar"` (기본 1.2), `"T_fw_C"` (기본 60).

**증기 라인**:

- `steam_demand`(0..1) → 하류압 `P_downstream`과 밸브 개도로 환산(기존 명령 의미 보존).
- 임계압력비: 포화증기 k ≈ 1.135 기준 **0.577** (기존 0.55는 과열증기 값 — 리뷰 수정).
  비임계: `q = Cv_SI·opening·sqrt(Δp·ρ_s)`, 임계: `q = C_choked·Cv_SI·opening·p`.

**Blowdown** (Phase A 포함 — §1.2):

- config 스케줄(주기/지속/유량 분율) 기반 `q_bd`, (E1)(E2)에서 h_w 동반 유출.
- PdM 효과: 정상 운전 패턴(주기적 수위 강하 + 급수 증가)이 데이터에 존재해야
  이를 누설로 오분류하는 false-positive 소스가 제거된다.

---

## 4. 제어·안전 재배선 (obs 기반 closed-loop)

리뷰 blocking(실행 순서/초기화/플래그 충돌) 반영하여 다음으로 확정:

- config: `control.closed_loop_source: "truth" | "obs"` (기본 `"truth"`),
  `safety.evaluation_source: "truth" | "obs"` (기본 `"truth"`) — **분리된 플래그**.
  기본 설계 결정: control만 obs로 전환하고 **safety는 truth 유지**. obs 기반 safety는
  노이즈성 trip이 `label/safety_state`(라벨 계약)에 들어가 데이터셋 의미를 바꾸므로
  명시적 opt-in으로만 허용한다 (ADR-6).
- **타이밍**: controller/safety는 **직전 스텝의 obs**를 소비한다(1-step measurement delay).
  `observe()`는 현행대로 스텝당 1회 유지 → **RNG 소비 순서가 보존**되어 기존 bit-exact
  재현 테스트와 truth/obs 동일-시드 KPI 비교가 성립한다.
- **초기화**: i=0과 첫 유효 샘플 이전의 NaN은 config 초기값(truth at t0)을 사용.
- **품질 플래그**: dropout-hold는 기존 `bad`를 재사용, `stale`은 sample-period hold 의미
  그대로 유지(기존 체계와 충돌 금지 — sensor_model.py:133-143 현행 의미 보존).
- **채널 커버리지**: obs 모드 config는 제어가 소비하는 4채널(drum_level, drum_pressure,
  steam_flow, feedwater_flow) 전부에 sensor 항목을 정의해야 한다. 현재 대부분 config에
  feedwater_flow sensor가 없어 truth pass-through가 되므로(3-element 루프가 사실상 truth를
  보게 됨), obs 모드 기본 config에 4채널 노이즈 정의를 추가한다.
- **검증 KPI** (§7.6): 동일 시드 truth vs obs 모드의 (a) drum level 분산 차이가 센서 노이즈
  수준과 정합, (b) **alarm/trip count 비교**(chattering 검출), (c) sensor_drift 고장 시 제어
  성능 열화(level 분산 증가)가 데이터에 나타남 — PdM 라벨 2차 효과 확보.

---

## 5. 고장 모델 재연결 매핑

fault scheduler(스케줄링/라벨링 기계)는 유지, 주입점만 교체:

| Fault | 현재 주입점 | ab4 주입점 | 비고 |
|---|---|---|---|
| fouling | ua_scale+qmax_scale+eta_comb 동시 하향 | `UA_eff·(1−α_foul·sev)` 단일 | T_stack↑·η↓는 수지에서 자동 발생 |
| tube_leak | 드럼 질량수지 m_leak | (E1)(E2)의 q_leak (h_w 동반) | 에너지 영향 최초 반영 |
| burner_deg | eta/qmax 멱법칙 | `η_comb` 하향 + `q_fuel_max` 하향 | O2↑는 §3.3의 **불완전연소 몰수지**가 전제 — λ만으로는 불변(리뷰 수정) |
| pump_wear | max_flow·(1−wear) | 펌프 곡선 `a0·(1−wear)` | 제어 보상 패턴 자동 발생 |
| valve_stiction | deadband+gain | 동일 (actuator chain) | 변경 없음 |
| sensor_drift | 센서 모델 | 동일 | 변경 없음 |

라벨 계약(`label/*` v1.1) 변경 없음.

---

## 6. 수치 전략

- **솔버**: `solve_ivp(method="BDF")`, RHS는 M⁻¹f. rtol/atol config 노출,
  `atol = [1e2, 1e-4, 1e-5, 1e-5]` 상태별 벡터.
- **성능 — 측정 우선** (리뷰 반영, 주장 완화): 'bdf' 오타 수정 후 테스트 슈트 14.5s→142s는
  BDF 실구동 비용. BDF 한 dt당 RHS 평가는 Newton×FD-Jacobian으로 수십 회이므로
  **A3 첫 작업 = RHS 1회 평가의 물성 비용 프로파일링**. 스플라인 테이블(§3.2)이 1차 완화책.
- **Persistent integrator는 조건부**: control이 controller_dt마다, params_faulted가 매 스텝
  바뀌므로 RHS 불연속이 일상적이고, BDF의 multistep history는 연속성을 전제한다 —
  **현재의 스텝별 재시작은 순수 오버헤드가 아니라 부분적으로 올바른 불연속 처리**다(리뷰).
  채택한다면: (a) **restart-on-discontinuity 정책** — control/param 변화량 임계 기반
  warm-restart, fault onset/모드 전환/trip은 강제 재시작, (b) scipy 스텝 구동 메커니즘
  (dense_output 보간 vs t_bound 갱신)을 A3 프로파일링 후 결정해 ADR로 기록.
  프로파일링 결과 물성이 지배 비용이면 persistent 경로는 보류한다.
- **성능 목표 기준선 명시**: "기존 grey-box(BDF) 대비 3배 이내" — 기준선은
  `performance.bottleneck.baseline_log_path` 메커니즘으로 고정한 grey-box+BDF 로그
  (Euler 기준선 142s↔14.5s 혼동 방지).
- **클램프 정책**: 미분 클램프·projection 전면 폐지. (a) 물리 가드(V_wt ∈ [0.05, 0.95]·V_t
  위반 시 이벤트 + 중단 옵션), (b) 보존 잔차를 invariants로 기록하고 §7.1 게이트로 강제.
- **재현성**: bit-exact seed 재현 테스트를 ab4에 복제 적용.

---

## 7. 검증 계획 및 수용 게이트

### 7.0 물성 게이트 (`tests/test_props_if97.py`) — DoD 2 대응 (리뷰 신설)

- IF97 reference point 대조: 1/7/10/50/100 bar에서 Tsat, ρ_w, ρ_s, h_w, h_s 절대 오차 < 0.1%
- 도함수 정확도: spline 도함수 vs iapws 미세차분(eps 1e-2 bar) 상대 오차 < 0.5%
- 경계 동작: 0.5/120 bar에서 정의된 값 반환, 범위 밖 입력은 ValueError (클램프 금지)
- iapws 부재 환경에서 `props` import가 ImportError로 실패 (monkeypatch 테스트)

### 7.1 보존 게이트 (매 시뮬레이션, CI 강제)

| 게이트 | 현재 | Phase A 목표 |
|---|---|---|
| 수/증기측 질량 잔차 | < 50 kg/s (정격의 25배!) | **< 1% of 정격 증기유량** (marine aux: 0.014 kg/s) |
| 수/증기측 에너지 잔차 | < 3e7 W (정격의 3배) | **< 1% of 운전점 입열 Q_op** (리뷰: Q_max 기준이면 운전점에서 ~2.9% 허용이 되어 무력화) |
| **가스측 질량/에너지 잔차** | 없음 | **< 0.5% of Q_comb** (DoD 3 대응 — 리뷰 신설) |
| solver fallback | silent | **0건** (발생 = 실패) |
| state_clamp 이벤트 | 다수 | **0건** (ab4) |

### 7.2 Åström–Bell 벤치마크 회귀 (`tests/test_ab4_benchmark.py`)

대상: 논문 §5의 **P16-G16 (160 MW, Öresundsverket; 실험 시 드럼압 ~8.5 MPa)** — 리뷰 정정.

**목적 한정** (리뷰): 이 벤치마크는 utility-scale에서의 **AB-4 구현 code-level 검증**이다.
marine aux 스케일 타당성 검증이 아니며, 후자는 §7.3 anchoring + §7.4 저압 sanity가 담당한다.

기준 데이터 2단계:

1. **1차(결정적): code-to-code** — 논문 Table의 P16 파라미터로 본 구현을 구성하고, 동일
   파라미터로 독립 구현한 reference 스크립트(논문 식 직접 전사)와 상태 궤적 대조.
2. **2차: 디지타이즈 트레이스 overlay** — Fig.4(연료 스텝)/Fig.9 디지타이즈 데이터
   (`tests/data/ab2000_fig*.csv`, 디지타이즈 작업은 WBS A4, 판독 오차 5~10%는 R8로 등재).

정량 메트릭(±20% 포락선의 대상 명시 — 리뷰):

- 연료 스텝(+10%) 후 [0, 300 s] 구간 드럼압력 상승률 [Pa/s]
- 증기밸브 스텝 후 수위 swell **피크 크기 [m]와 피크 시각 [s]**, 이후 정착 방향 부호
- 급수 스텝 후 shrink(응축 기인) 초기 방향 부호와 최대 편차

### 7.3 정상상태 anchoring (`tests/test_ab4_steady_state.py`)

`marine_aux_boiler.yaml` 정격점(7 bar, 1.4 kg/s ≈ 3.5 MW, MGO, λ=1.15)에서 **동일 운전점
동시 평가** (리뷰: 게이트 모서리 비정합 제거 — λ=1.15·벽손실 1.5%에서 η 0.93↔T_stack 180°C는
양립 불가했음):

- 보일러 효율 η ∈ [0.88, 0.92] (직접법, 연료 투입열 기준)
- 배기 O2 ∈ [2.5%, 4%] **dry basis** (λ=1.15→2.9%, λ=1.2→3.7% 정합 확인됨)
- T_stack ∈ [180, 250]°C
- 정격 연료유량 = Q_steam/(LHV·η) ±2% 자기일관성

참고: anchoring 벤더(Aalborg OS-TCi, Miura HB, Kangrim PA/PB)는 수직 원통형이라 η/O2/T_stack
대조에는 유효하나 AB의 drum–riser–downcomer 토폴로지와는 형식이 다름을 명시해 둔다.

### 7.4 저압 과도응답 sanity (`tests/test_ab4_low_pressure_transient.py`) — 리뷰 신설

경험 파라미터는 85 bar(P16)에서 7 bar로 이전되지 않으므로(§3.1), 목표 압력대의 동특성을
hand-calc 수준에서 고정한다:

- 7 bar에서 증기밸브 스텝 시 swell **방향**(상승)과 **크기 order-of-magnitude**가
  ρ_w/ρ_s ≈ 200 기반 수계산 추정과 일치
- 급수 스텝 시 shrink 방향 재현
- shrink/swell 크기가 저압에서 고압(85 bar 설정)보다 큰 단조성 확인

### 7.5 Cross-model 회귀

grey-box(`python`) vs `ab4` 동일 시나리오 KPI 비교 리포트(parity harness 골격 재사용) —
게이트가 아닌 **관측 문서**. 두 모델의 의도된 차이를 정량화해 Phase B 우선순위 근거로 사용.

### 7.6 obs closed-loop 검증 — DoD 4 대응

§4의 KPI 3종(level 분산 정합, alarm/trip count, sensor_drift 2차 효과)을 validation battery에
추가.

### 7.7 검증 데이터 소싱 (한계 명시)

- 1차: Åström–Bell 논문 (식 + P16 파라미터 + 실측 그림)
- 2차: 벤더 datasheet 정상상태 (Aalborg OS-TCi 1.2~8 t/h, Miura HB, Kangrim PA/PB)
- 3차(Phase B 이후): OpenModelica ThermoPower 드럼보일러와 code-to-code
- **실선 운전 데이터 없음** — 주장 범위를 "보존 법칙 + 공개 벤치마크 포락선 + datasheet 정합"
  으로 한정(R5). calibration 훅(`research/calibration.py`)을 ab4 파라미터(T_d, β, k_friction,
  UA_eff)에 연결(WBS A5).

---

## 8. 스키마/데이터 계약 영향

- **additive 안전성의 실제 근거** (리뷰 정정): `SCHEMA_LOCK.core_columns`가 `truth/*`
  와일드카드이고(schema.py:89) label 계약 검증은 `label/*`만 강제하므로 truth 채널 추가는
  안전하다. ~~check_spec_contract.py로 확인~~ — 이 스크립트는 spec 문서의 버전 문자열만
  검사하므로 근거가 아님. 대신 **ab4 row를 `validate_label_contract_row` + `_validate_rows`에
  통과시키는 신규 테스트**를 A1 산출물로 추가한다.
- **ab4가 구현해야 할 truth 채널 전수 계약** (리뷰: 5개 나열은 불완전):
  - `outputs()` 15채널: drum_pressure, drum_level, steam_flow, steam_flow_true, drum_temp_sh,
    feedwater_flow, feedwater_temp, m_boil, m_leak, vapor_mass, wall_temp(→Tsat 별칭),
    drum_temp, flue_gas_temp, O2, h_fw
  - `invariants()` 9키: mass/energy_balance_residual, m_total, dM_total,
    volume_algebraic_residual, *_nonnegative, pressure_in_range, sat_temperature_C 등
    (+신규: gas_mass_residual, gas_energy_residual)
  - `_validate_rows` 기본 필수 컬럼: truth/flue_gas_temp, truth/O2, truth/h_fw
    (→ **A3 스텁이 산출해야 함**, §9), `truth/level_true` alias, SensorModel의 채널명 의존
    (drum_level DP 경로) 유지
  - 신규 추가: fuel_flow_kg_s, air_flow_kg_s, lambda_excess_air, T_stack_C,
    boiler_efficiency, q_dc_circulation_kg_s, alpha_r_quality, q_blowdown_kg_s
- manifest provenance에 `core_backend: "ab4"`, props 테이블 버전/해시 기록 (WBS A5).

---

## 9. WBS 및 일정 (1~2인 + AI 보조)

| WP | 내용 | 산출물 | 견적 |
|---|---|---|---|
| A1 | 백엔드 계약 재정의: protocol + temporal contract, alignment/clip/이벤트의 BoilerSystem.step() 내재화, **FMU shim**, silent except 제거, **golden-row bit-parity 테스트**, additive 스키마 테스트 | backend_protocol.py, step_loop 리팩터, 기존 52 테스트 + parity 그린 | **2.5~4 pw** (리뷰 상향) |
| A2 | 물성 계층: 스플라인 테이블 + 도함수 + PropsBundle + fuels + gas enthalpy + §7.0 게이트 | props/, test_props_if97 | 1.5~2 pw |
| A3 | ab4 드럼 코어: 4-상태 ODE + 기하 + 급수/증기/blowdown 라인 + **연소 스텁(fuel_cmd→Q + placeholder 필수 채널 flue_gas_temp/O2/h_fw)** + **RHS 물성 비용 프로파일링(첫 작업)** + marine 기하 파라미터 소싱(벤더 GA/전열면적/circulation ratio 10~30 역산 절차 문서화) | core/ab4/, §7.1 게이트 통과 | 4~5 pw |
| A4 | 연소/연도가스 enthalpy 정식화(스텁 교체) + 고장 재연결 + **AB 벤치마크(레퍼런스 전사 + Fig 디지타이즈)** | furnace.py, test_ab4_benchmark, tests/data/ab2000_*.csv | 2.5~3.5 pw |
| A5 | obs closed-loop(§4) + §7.3/7.4/7.6 게이트 + cross-model 리포트 + calibration 훅 + media→props 위임 + manifest provenance + 문서화 | 테스트 4종, CI 통합(마커 분리), README/blueprint 갱신 | 3.5~4.5 pw |
| **합계** | | | **14~19 pw** (v1.0 12.5~17에서 리뷰 반영 상향) |

순서: A1 → A3 (A2 병행 가능), A4는 A3 후, A5는 A3/A4 후.
**중간 마일스톤** (리뷰 수정 — A3 단독으로는 필수 컬럼 부재로 검증 불가):
"**A3 완료 시점**: 연소 스텁 포함 ab4로 24h marine aux 시나리오가 §7.1 수/증기측 게이트를
통과하며 돈다. **A4 완료 시점**: 가스측 게이트 포함 전체 §7.1~7.4 통과."

## 10. 리스크 레지스터

| # | 리스크 | 확률/영향 | 완화 |
|---|---|---|---|
| R1 | AB-4 경험 파라미터(T_d, β, V_sd⁰, k_friction)의 marine 정격 식별 실패 | 중/중 | T_d는 물리 정의에서 직접 산출(§3.1), sensitivity 스크리닝, §7.4 저압 sanity로 방향/크기 고정 |
| R2 | 질량행렬 stiff 결합으로 BDF 수렴 실패 | 중/고 | C1-연속 스플라인 물성(§3.2), atol 벡터, 조건수 모니터링, fail-loud |
| R3 | 성능 회귀(BDF 실구동 10x 이미 관측) | 고/중 | A3 첫 작업 프로파일링, 스플라인 물성, 기준선 명시(§6), perf gate 재기준선 |
| R4 | A1 리팩터가 기존 테스트/row 의미 파손 | 중/중 | temporal contract 명문화 + golden-row bit-parity를 수용 기준으로 |
| R5 | 검증 데이터 부재로 정확도 주장 불가 | 확실/중 | 주장 범위 한정(§7.7), calibration 훅 준비 |
| R6 | 일정/bus factor: A1→A3→A4→A5 단일 critical path, 1인 기준 3~4개월 (리뷰 신설) | 중/고 | A2 병행으로 경로 단축, WP 단위 커밋/문서화로 인수인계 비용 최소화 |
| R7 | CI wall-time 증가: 142s 슈트 + ab4 벤치마크/24h 시나리오 (리뷰 신설) | 고/저 | pytest marker로 `slow`/`benchmark` 분리, PR은 핵심 게이트만·nightly에 전체 |
| R8 | 디지타이즈 기준 데이터 품질(판독 오차 5~10%가 ±20% 포락선 잠식) (리뷰 신설) | 중/중 | 1차 기준을 code-to-code 전사로(§7.2), 디지타이즈는 2차 overlay로 강등 |
| R9 | marine 기하/금속 파라미터(V_r, V_dc, A_dc, m_r/m_d) 소싱 실패 (리뷰 신설) | 중/중 | 벤더 GA/전열면적/circulation ratio 역산 절차(A3), 감도분석으로 허용범위 명시 |

## 11. 결정 기록 (ADR 요약)

1. **Åström–Bell 채택, 자체 5-상태 확장 기각** — 압력식이 에너지 비보존 게인이라 확장 불가.
   AB는 공개 검증 기준(160 MW P16) 보유.
2. **Python 코어 신작, Modelica 연기** — aux PdM-grade에서는 fault 주입·라벨링 통합이 지배
   요인. Modelica/FMU는 Phase C 게이트에서 재심사. 단 **기존 FMU 백엔드의 인터페이스 호환
   shim은 A1 범위**(리뷰 정정).
3. **iapws 유지 + 스플라인 사전 테이블, CoolProp 연기** — RHS 경로 rounding cache 금지(ADR-7).
4. **가스측 1-노드 quasi-steady + enthalpy 기반** — cp·ΔT 형태 금지, 캐스케이드는 Phase B.
5. **기존 grey-box 보존** — fast backend + cross-model 회귀 기준.
6. **obs closed-loop은 control만, safety는 truth 기본** (리뷰 신설) — 노이즈성 trip이 라벨
   의미를 바꾸는 것을 방지. safety obs 소비는 명시적 opt-in.
7. **ab4 RHS 경로 rounding cache 금지** (리뷰 신설) — BDF FD-Jacobian 평활성 전제.
   C1-연속 스플라인으로 물성+도함수 동시 제공. rounding cache는 legacy 전용.
