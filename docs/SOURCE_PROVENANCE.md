# Simulator Source Provenance (`simulator_source/`)

This document records the exact provenance, exclusions, commit status, and file-level SHA-256 hashes of `simulator_source/` inside `CAPTW/pub053-jmse-boiler-leak-warning`.

## 1. Upstream Repository & Local Base Commit Status
- **Upstream Private Development Repository**: `https://github.com/CAPTW/boiler-pdm-sim.git` (remains private; full upstream `.git` history is intentionally NOT copied into this publication repository).
- **Local Base HEAD**: `4fea4646723f04db41583cb682bac8b62c44bc05` (`2026-06-30 20:23:45 +0900`, commit message: `A5 tail: cross-model regression + 24h conservation gate`).
- **Upstream Remote Check Result**: Commit `4fea4646723f04db41583cb682bac8b62c44bc05` is **5 commits ahead** of private `origin/phase-a/revive-kickoff` (`497db42`) on the development workstation (`e2fc455d`, `3f14b0d0`, `0ac3e249`, `5c25dcca`, `25cc6379` preceded or branched locally) and returns HTTP `422` (`No commit found for SHA`) when queried against the private remote API. Accordingly, `4fea4646...` is documented strictly as the **local development base HEAD**, while this public repository's own commit SHA and the SHA-256 hashes below serve as the public verifiable reference.

## 2. Relation to Study Execution `source_copy/` (`observable_baseline_study_...zip`)
- A clean checkout of `4fea4646...` is **NOT** bit-identical to the runtime `source_copy/` used to generate the 24 manuscript episodes.
- Specifically, the study-time execution archive `observable_baseline_study_20260915T215200Z_be142b32.zip` (`source_copy/`, `analysis/`, `configs/`, `exogenous/`, `runs/`) already had **pilot and study economizer-leak patches** applied on top of `boiler_pdm_sim` and configured `dt = 2.0 s`, `horizon_s = 21600 s`, `closed_loop_source = "obs"`, and `safety.scheduler_intervention_policy = "process_protection_without_schedule_severity_oracle"`.
- By contrast, the snapshot config `simulator_source/configs/ab4_marine_aux.yaml` from base `4fea4646...` retains baseline settings (`dt = 1.0 s`, `closed_loop_source = "truth"`). Those differences are explicitly preserved rather than retroactively patching `simulator_source/` or re-applying patches twice.
- Frozen 48 binary `.npz` arrays (`data/observations/*.npz`, `data/traces/*.npz`), `data/block_design.json`, `data/original_configs/`, R2 `code/` scripts, and baseline `results/` belong to the separate R2 reanalysis archive `PUB053_Manuscript_Package_R2.zip` (external workstation).

## 3. Comparison Against Upstream Working Tree & Excluded Items
- **Included files in `simulator_source/`**: **156 files**.
- **146/156 files**: Bit-identical to git blobs at `4fea4646723f04db41583cb682bac8b62c44bc05`.
- **8/156 files** (`configs/base.yaml`, `configs/base_fmpy.yaml`, `docs/phase_a_design.md`, `src/boiler_pdm_sim/core/backend_factory.py`, `backend_protocol.py`, `boiler_system.py`, `fmu_adapter.py`, `tests/test_backend_protocol.py`): Match the local workstation working tree verbatim; differ from raw `4fea4646...` blobs solely by LF vs. CRLF line endings.
- **1/156 file** (`docs/spec_boiler_pdm_sim.md`): Matches local working tree (`17,853` bytes vs. `17,852` bytes at `4fea4646...`).
- **1/156 file** (`LICENSE`, MIT License, Copyright (c) 2026 The Boiler PdM Simulator Contributors): Copied from upstream root `LICENSE`.
- **Excluded from `simulator_source/`**:
  - `.git/`, `.github/`, `.gitignore`, `.venv/`, `.pytest_cache/` (private repo history, CI internals, and workstation environment).
  - `research/` (`302` tracked files at `4fea4646...` plus ~1.3 GB working-tree track-A/track-B research datasets), `scripts/` (`6`), `models/` (`2`), `artifacts/`, `validation/`, `calibration/`, `cli/`, `dataset/`, `interface/`, `notebooks/`, `safety/`, `analysis_report.md`, `blueprint.md` — excluded as unrelated research harnesses, unpushed bulk datasets, or duplicate/top-level scratch wrappers not needed by the core `ab4` package or PUB-053 R2 verification.

## 4. Complete File Hash Inventory (`simulator_source/`)
| Path (relative to `simulator_source/`) | Bytes | SHA-256 |
|---|---:|---|
| `configs/ab4_marine_aux.yaml` | 4503 | `2c6c330289008b27a3fc6cc3434900cb5642ee661241d4ff70a360ef1c6491df` |
| `configs/base.yaml` | 5629 | `92254b7a5b07aa2743c49525063d983c76df5b3d536d7d8a47217ac2e7f3b409` |
| `configs/base_fmpy.yaml` | 3893 | `bfe433f69bf3c2ad8a3fe120432aaf90a9f8114cc8d75afa9973f91a9ff49522` |
| `configs/base_fmpy_model_exchange.yaml` | 3215 | `c1a8436c4681f878acd0986fd747fb91c686a0cf08f8329c7e7d5f0eb44a7ddc` |
| `configs/base_fmpy_template.yaml` | 5398 | `919ec90e7a33f1b7d660a40794de24b10f45215de85516f668df30726ef06128` |
| `configs/dummy_fmpy.yaml` | 3199 | `7b8e4cafacc68b2c37e78d3f8adb2e2749aa9acc614bced3e8aa84a29fb8bdc8` |
| `configs/faults/burner_deg.yaml` | 171 | `4b129180f924dd89d9b384aba9e3f05c519266fd2fa735c39fc7bab76ffb1296` |
| `configs/faults/fouling.yaml` | 164 | `cb38748c39f03394f4151cd780bd6e16d4dd579ae87fdfd4143397fcd8ad62bc` |
| `configs/faults/pump_wear.yaml` | 145 | `d2382fe2c9039697868ccdf55602c7815e8b2ab471fce31652d897492d1e5bfa` |
| `configs/faults/sensor_drift.yaml` | 180 | `8aab14ad644f4b584d6d8c79b34ba2f3e01c8fd345eef2b06099f3ee3c8a07d9` |
| `configs/faults/tube_leak.yaml` | 162 | `2c495a191d9ce82d3b66a64d1e441918291abe50021645d6114320ca55aaaf05` |
| `configs/faults/valve_stiction.yaml` | 175 | `5668ca6c4e930435302315534169c766cf1d88e903c047dc04488c1f293c73b3` |
| `configs/governance_policy.yaml` | 644 | `96883484dd1c3aa4054f8629263662f98e56977fbd59914a90cb74d0426df62f` |
| `configs/local_pipeline.yaml` | 3475 | `5f7be0a93170cafd74736411026db2ca15399b3a52766bf902a72fb32be722a5` |
| `configs/local_pipeline_step_tests.yaml` | 3050 | `9f07a2ea63cfdd27ec835d7475f984ad1461bf2522a1b01c5386d80e800b223d` |
| `configs/scenarios/load_follow.yaml` | 113 | `b0d50fbcd2c933111290febf0f76cbec9f0b156f6d9cc10d4bb44175a980c5c5` |
| `configs/scenarios/step_tests.yaml` | 237 | `ed6f6c1c59621af93a674564bac18bc39edcb57d29a7e99770722c75e9352120` |
| `docs/phase_a_design.md` | 36558 | `483d740f99bb83af7cf5381d6575d4f9651fe9cf7a8e20f9a10800be79d1d3b0` |
| `docs/spec_boiler_pdm_sim.md` | 17853 | `ffcab396a23ae2831712647e5799581e1706a50869ae6665cb809e811956bc6a` |
| `LICENSE` | 1098 | `60bc5680ab3a98a222066d5553d45b28816a5635efefeb5503d66a3e2f335f92` |
| `pyproject.toml` | 1222 | `b19b181bb65a7cab2731c38af926fc1ae1287bf8db383eabe312a790d4659313` |
| `README.md` | 14525 | `cabe7255ddd71fd887f0b73d730b9d509929ee135176156b169c4084cdfad74e` |
| `src/boiler_pdm_sim/__init__.py` | 207 | `2e8f68fe8730c6dd30963a97e07bbb86759cdd53c55601f23588c7e402d56ca4` |
| `src/boiler_pdm_sim/calibration/__init__.py` | 486 | `c6f8ecb88bdeaa77ed405ac4485eb29a6de981ce98eaf3319ce44a91001ffdd2` |
| `src/boiler_pdm_sim/calibration/baseline.py` | 210 | `01df609f6ebb5810654df38ddf9473f0d63b425349a773381496fb68146991a4` |
| `src/boiler_pdm_sim/calibration/identify.py` | 226 | `489b9d298f57d789d469a224ac7099ba42c077d698b2387a97b2c5b18eff7dc5` |
| `src/boiler_pdm_sim/calibration/sensitivity.py` | 246 | `f8dde5f477ae290d65e3b866dbcfea589d653f7d6ae633af79ca62990f3f0ea8` |
| `src/boiler_pdm_sim/cli/main.py` | 986 | `0b3fbbf7b0d554495d25f7e3d543ac31ed06f02d7ff1aa5ab775c6f3a4b9ea36` |
| `src/boiler_pdm_sim/control/__init__.py` | 304 | `646a816fc6d7f91d115f9089d0403b06ebcb513db13502c02d026d0dda899d6d` |
| `src/boiler_pdm_sim/control/loops.py` | 3136 | `87fca53b0099024a19d880e187668d4029e1c2a06483b1aa943b315c0905aa14` |
| `src/boiler_pdm_sim/control/pid.py` | 3044 | `c9d3e43570b22679150eb69c2cf6e82414ae5c26cf5ec821c2942b1f8f8e9913` |
| `src/boiler_pdm_sim/control/three_element.py` | 13242 | `b891e95aaa0acc4389f7550f2c0ab95f9ae4d1851e759e893def19f9b407cef8` |
| `src/boiler_pdm_sim/core/__init__.py` | 172 | `8f2a0845fdead47a050dd144fccf41783de199d746fa34111ef48c55926a6fde` |
| `src/boiler_pdm_sim/core/ab4/__init__.py` | 413 | `857d7e6bccb494e04378a8c87e957df8e60a50d95b3fa336f0125b4e8f2c7382` |
| `src/boiler_pdm_sim/core/ab4/backend.py` | 15749 | `a3c5138aa271560cb2bbf842989fc38a6aa51542ba00f1a7e0d9e5d259b71ccd` |
| `src/boiler_pdm_sim/core/ab4/drum_model.py` | 9372 | `9bad1fb0764dcd9f82d6aea817281b7d0b4e7e3ee598b55ce011b44bf8f86bd0` |
| `src/boiler_pdm_sim/core/ab4/feedwater.py` | 3482 | `81c1134f168c75c776728a10183437f0988eb53bde5106f8ac196e8459d594d7` |
| `src/boiler_pdm_sim/core/ab4/furnace.py` | 8929 | `78436839e24e768188fd7ceffe48c185109c84ff48d576c5581102881e40cef1` |
| `src/boiler_pdm_sim/core/ab4/geometry.py` | 3037 | `a0d0bf53d2451ffc18a4a20868ee7c522f5ba69e247ee071de2facc0e92b3640` |
| `src/boiler_pdm_sim/core/ab4/steam_line.py` | 3337 | `49d8f6001c191f2130d38205eaa67e2db913976e8493d7ca99016b0a4f0d1e3b` |
| `src/boiler_pdm_sim/core/backend_factory.py` | 1037 | `d53e6124e85e3b0804d873c4ec33bb8c655bd6a28e28427f28a4614fb664dc59` |
| `src/boiler_pdm_sim/core/backend_protocol.py` | 12036 | `cfbe8c1a2655c34635b214ade4b9b33878017da43a9aa58d66c1415093f3631e` |
| `src/boiler_pdm_sim/core/boiler_system.py` | 33390 | `3327987323e578a3ddece226c0c2abf33133f57a1a56ca2e5a836eb380b3e998` |
| `src/boiler_pdm_sim/core/components/__init__.py` | 71 | `f5363c62b36ac457b9c7356e51f0095ba0d91bd77db48e026b4bb876cf2b9313` |
| `src/boiler_pdm_sim/core/components/combustion.py` | 214 | `c83b95b29655f109f28d7298d6b25c7321a15c15a3ebb05908a9ad0f4da6a07e` |
| `src/boiler_pdm_sim/core/components/drum.py` | 1608 | `579442a17eb11a2636a52cff0789caa42ba689d9274b4bbd60ef1e5b8ec94c10` |
| `src/boiler_pdm_sim/core/components/economizer.py` | 1256 | `37e202eb9d97156e9c1ea750e53397144e455749179ed1a1371053185897b3fc` |
| `src/boiler_pdm_sim/core/components/evaporator.py` | 249 | `2ebef520636b0ce2957c8c4a3c2021d791e2f322012065fdacb4e2c814d8da86` |
| `src/boiler_pdm_sim/core/components/pump.py` | 212 | `87e2b24bc3dc609de170a70709a607313015d8a811db1e935af0c0ac8e4bfc8d` |
| `src/boiler_pdm_sim/core/components/superheater.py` | 830 | `af8aa3b20572d6a609e4b644c93a68843cb260ff0ddecdcd69b351747268f1ab` |
| `src/boiler_pdm_sim/core/components/valves.py` | 806 | `a3d916a0623312e8bf4f491d1b34a5ad8ba6a5ea46f26c0a6c28d6cbb6b09b50` |
| `src/boiler_pdm_sim/core/fmu_adapter.py` | 37897 | `22dbe5e2157f14745bf6c8b683b36b0d98485f2858fdc9acea1675be19257680` |
| `src/boiler_pdm_sim/core/media.py` | 5984 | `28426de19fd6f1b1d7d5c58e6e728c11755751a8d8eb367d41a82de846682ad0` |
| `src/boiler_pdm_sim/core/solver.py` | 3621 | `22bcd4e933cd20479bd8508de0d1c3b3ea621729a0b2586ef9d589e34158a3ab` |
| `src/boiler_pdm_sim/core/state.py` | 1040 | `3871647f1e14535465cd59055606b119fc41cdc57e9e051de996d526283abd0e` |
| `src/boiler_pdm_sim/core/thermo/__init__.py` | 203 | `81548fc0533e246f36184657fd5569d88012d406e077656cb14bbb4f9c263350` |
| `src/boiler_pdm_sim/core/thermo/if97.py` | 197 | `dd55c41f344b99e75c7e558547d0cfe4d65cc9a2bb94803461caf767e1ba5f67` |
| `src/boiler_pdm_sim/core/thermo/steam_props.py` | 291 | `05b6a81528438caa5d97a95aa52a1bc5631f7373b3749b16456f5286880f013c` |
| `src/boiler_pdm_sim/dataset/__init__.py` | 46 | `77c1db25f876cb285bca9f01014dded90bbed9ee20a82bc795666be657c26fec` |
| `src/boiler_pdm_sim/dataset/generator.py` | 290 | `8aa2dff39c8879ba2b911fb674283979b0fc1cc61a5c26751bc314a407a58eb3` |
| `src/boiler_pdm_sim/dataset/labeling.py` | 831 | `a4a4e1f1b45b08d5539f8409a9a65034b9d9ae70d71a1c39065cfd87e84458a1` |
| `src/boiler_pdm_sim/dataset/splits.py` | 366 | `15ad350ae750b3010db6e50deaf4b4467ec1cc89f736625d8a9c828158f2ea74` |
| `src/boiler_pdm_sim/dataset/writer.py` | 10618 | `e751cc46d3cc96e60a6ae1918a2d94a6010f8d8fb5338b4f4072c5d1e5b30067` |
| `src/boiler_pdm_sim/degradation/__init__.py` | 34 | `a870086c45855bb82afd0fcdb565e39fc2b37c4e5e5e2b961eea3f1e2dbbb984` |
| `src/boiler_pdm_sim/degradation/base.py` | 291 | `e064ffb1ea6c7c6c39c9c963d14dfa88edb7120cd688da203214a272da4bd536` |
| `src/boiler_pdm_sim/degradation/burner_deg.py` | 786 | `bdef2e30efda12c3b5d75cd6935bfc420f7bcec97b7c5da0d450b5d2efa3570c` |
| `src/boiler_pdm_sim/degradation/fouling.py` | 1992 | `af6f0618d5b24f678ce2f321ce2cae19017477ca99ff9c762bbcb2097ea709df` |
| `src/boiler_pdm_sim/degradation/pump_wear.py` | 483 | `291d9ab0e2ee37432a9a7d45a891be51f4bc3202010270a73e3d9f18778a6632` |
| `src/boiler_pdm_sim/degradation/scheduler.py` | 16190 | `542d11711cbda6d29a94cc16c7e332f1d0b20521d70762d5f47a74a912e17cad` |
| `src/boiler_pdm_sim/degradation/sensor_faults.py` | 1801 | `3edce2d2e8bb737f072b8a977229361618e9e11379f416a33a04657961f29de7` |
| `src/boiler_pdm_sim/degradation/tube_leak.py` | 289 | `2d3dc38fa1c987e44e1ef06d4e116f8d68079677a05ebbcb319b54a45aabdf79` |
| `src/boiler_pdm_sim/degradation/valve_stiction.py` | 372 | `2fea504d1236c5899bb79be306382ee306ecb42d8d8be788918e4c437b2ceb36` |
| `src/boiler_pdm_sim/interface/fmu.py` | 1144 | `5fea2326cd51f9c0334410e62a7311e6017f89e3ceb81ac00e742e04d0790449` |
| `src/boiler_pdm_sim/pipeline/__init__.py` | 70 | `2fe71c3bfa291a110900d456a3b7a8686d3a183308287d662fda776f703d6b29` |
| `src/boiler_pdm_sim/pipeline/calibration.py` | 12258 | `42632ae67f5802ad773adb12e494e3198775aee8426c5668ff955a09a7226eda` |
| `src/boiler_pdm_sim/pipeline/config_types.py` | 13684 | `e8fbb30cb87467a477e14bf380462d04edf672b6a4e1986219f4fdf8e49cb5bc` |
| `src/boiler_pdm_sim/pipeline/governance.py` | 11916 | `0cace88a2cac5c6a4d3e80ae8234908e9e807e85532f4e0906e47c8679e2c04d` |
| `src/boiler_pdm_sim/pipeline/performance.py` | 6066 | `8f246f449fe5d84ffb8814dd5ed2e0160d85cda4a8be119c0a8143cb73c75441` |
| `src/boiler_pdm_sim/pipeline/postprocess.py` | 5574 | `287ccb066d5d84df459f2a69ed4af7dc972a28fa4e61c4e650ec6135d07ed475` |
| `src/boiler_pdm_sim/pipeline/run_to_file.py` | 7777 | `18c3a83b1ac740ad291a2a2172bbe7e87d3abe80b6010b98afb1e925d08e5489` |
| `src/boiler_pdm_sim/pipeline/runtime.py` | 6567 | `c1852e22d965b4a340b88e20d7bc2b53925c105e1698edc72be76b6ddc1bd3ac` |
| `src/boiler_pdm_sim/pipeline/step_loop.py` | 11463 | `ee77c0636982ee45f2025f8875ddd31bb702a13ebeae1f1d42ecd4af8b87dc83` |
| `src/boiler_pdm_sim/props/__init__.py` | 915 | `3059f85147d407255259d17f9474e0c22a117ff5d698838805e5d1914f975a30` |
| `src/boiler_pdm_sim/props/fuels.py` | 2063 | `9f8a61995b24d9a7b1ac075ea0c087380d1a0048b02a0cdde6e668b3c3afa91f` |
| `src/boiler_pdm_sim/props/gas.py` | 3919 | `9d29cea4668695236d0b0e407ee814f4e1e5a3eaacf127a2862bf37f192e17bf` |
| `src/boiler_pdm_sim/props/if97.py` | 5734 | `a6e58169036d6d93c342ff2fd17406aac6a3b96f9eccb47daf00d1566f746fb3` |
| `src/boiler_pdm_sim/research/__init__.py` | 806 | `dba4cd353f7c5e1bde1847a2fb50cb91f110f060d2d9698ee9dfeaab5e17b031` |
| `src/boiler_pdm_sim/research/baseline.py` | 3183 | `98e027d954dabb7c9e991ec933b524fcecdb986c7593790640c5a305a7953709` |
| `src/boiler_pdm_sim/research/benchmark.py` | 1781 | `0039468512b27ff2f578fc7bb057309063d771bbe3e125cab64f9fed293b9656` |
| `src/boiler_pdm_sim/research/calibration.py` | 3206 | `58726a7f56bd97953dc6b6072a6077cd9dddbc2e10b5f79c1a377829fc19e921` |
| `src/boiler_pdm_sim/research/features.py` | 1598 | `728cf667caf8f3c1697bf93181f7c140165d7ed7ba45b7d0c4f8e467f3d74bc7` |
| `src/boiler_pdm_sim/research/identifiability.py` | 3789 | `acac480ee2cbeb294fec0677ad3939c34b5be0103f4418a1a5de582e5f8871f4` |
| `src/boiler_pdm_sim/research/sensitivity.py` | 3495 | `8051c79177a0d5d1c38bd3c72242b566f096bec66704d969c4ed2a659b39cd0c` |
| `src/boiler_pdm_sim/safety/__init__.py` | 1658 | `ec7b449eb9a780f0080ef5c8b85a3afb5562f4383e94f956cdb61d235587840c` |
| `src/boiler_pdm_sim/safety/alarms.py` | 3627 | `06e58f303d28df089506eb4bfe11dfc42d1f8edaa9e0b72e3e11e3d19c59e8a2` |
| `src/boiler_pdm_sim/safety/trips.py` | 4249 | `bdb7addb15bcc53d08f9543516258450af4bb53bcab78a72f5af4f0aa67d83df` |
| `src/boiler_pdm_sim/scenarios/__init__.py` | 39 | `b035546efbede42740f56854297b884ac403d31344326e57f2e86322b8f3eef1` |
| `src/boiler_pdm_sim/scenarios/profile.py` | 2809 | `8e43890cf3c29721683065845bd093f30ff2f261638adef1e935257c6ed0276d` |
| `src/boiler_pdm_sim/scenarios/randomization.py` | 3776 | `8b59c93249cf6fc6cf710d0c3d455f9b9c2b5b8eca5d77ef53a908104f3c7457` |
| `src/boiler_pdm_sim/scenarios/scenario.py` | 487 | `07504509aa0ca878e72d8f8a907e9ba8170d440159f96f30c1649fa2be50a07b` |
| `src/boiler_pdm_sim/schema.py` | 13026 | `0e901c8cf5a9b713cae83e56eb1256eeef7a6a21a029312adfb5ab45fc46dd8e` |
| `src/boiler_pdm_sim/sensors/__init__.py` | 210 | `e9adaa98416e332d3dde8c957fa9a5a79ccce8039fff46a02a4bfa3ce69ac210` |
| `src/boiler_pdm_sim/sensors/dropout.py` | 161 | `992471acae56479ee4ae6a66b9c3af2c390e105658d23b4b74364a6aa375c63c` |
| `src/boiler_pdm_sim/sensors/drum_level_dp.py` | 7643 | `a11bcfd93e6cebdf21a25b9287d0bf15d63da9ad815059321adf4fd8d8b36a0b` |
| `src/boiler_pdm_sim/sensors/noise.py` | 177 | `18ac1f7cb2c5e021142af34e209780bde3a1a6e896dbd4440d048341c26a4b7a` |
| `src/boiler_pdm_sim/sensors/sensor_model.py` | 10082 | `7458605ba9f403c3b5b1aef194bdf60c1744fa40185da8e230cc2d81469d9410` |
| `src/boiler_pdm_sim/simulator.py` | 49137 | `e7677ef105e31662840df7d9f9b1f537b537d65dd793a223fe52d6fbf6cdc930` |
| `src/boiler_pdm_sim/validation/__init__.py` | 697 | `52a7f932a46a27695f935b3aad4ce7bf02ef4bf502d0aef3a39d72e03d1f092a` |
| `src/boiler_pdm_sim/validation/control_mode_transition.py` | 1068 | `0cb2b06b770068477d71adc63588b51cdaba244ea7a9693348105da34869b49e` |
| `src/boiler_pdm_sim/validation/fault_observability.py` | 1347 | `8702aa1debfb8743f6f8eabcad9d17f90ab151d82cb23b2d9952672ab29e846d` |
| `src/boiler_pdm_sim/validation/invariants.py` | 307 | `c28e5d9e1dffdcc96cc44b0dc89f707e5878ebf76517fbb61bd2696fd19aa5ea` |
| `src/boiler_pdm_sim/validation/level_instrumentation.py` | 1457 | `3889dcee833c1353ca7b221d4388c923267e9c7205d4047af0ea88dc80bc66a9` |
| `src/boiler_pdm_sim/validation/phase6.py` | 5239 | `17a4c1e7620e67429968aac816f7a98d4bad69ffa04033ab7c1339348d622d41` |
| `src/boiler_pdm_sim/validation/regression.py` | 6647 | `cf7ccbd8776009f2feb1e0b457786f15c586558f8f8d267a854f1019fed0e599` |
| `src/boiler_pdm_sim/validation/steady_state_map.py` | 1744 | `25fe213600bca67e8c908fa060e3a38c377c508a6d575dbcc20269269ca2b4dc` |
| `src/boiler_pdm_sim/validation/step_response.py` | 8349 | `48c238c5fe51a244dd6ceeab48fe143b73685bc7cddfbfe19d2633540b4c8ed2` |
| `tests/fixtures/dummy_boiler_fmu.py` | 7280 | `e337ca40c6ed923cb3a1d727becb3c9a0c3d30df4984ac210f21069e47b74bf7` |
| `tests/test_ab4_24h_gate.py` | 3081 | `3d81471eb395e016f13659180fa342215786e5ad15ac04fec94a5da18ff8a201` |
| `tests/test_ab4_anchoring.py` | 3812 | `cab14965d584e65afb75885532e52622441e761d1063359854b0617011369592` |
| `tests/test_ab4_backend.py` | 6208 | `6095f48e6b169924c5bab60fac136e3bcad75e46c4c40319a3e21ad6f871f886` |
| `tests/test_ab4_cross_model.py` | 3066 | `32ea5fafbba3e2c779bfb08e948a5360fe2181a2dd835330979d2ace8eee4f1a` |
| `tests/test_ab4_drum_model.py` | 5214 | `24cf2e24a22f3ce00d83f1ef21a7241e5c924fe64db89cde19a270257f1c9deb` |
| `tests/test_ab4_furnace.py` | 3417 | `b6c63dace9d93cbc16bc8a28d909b83e7d66cb687550f3fbae41d738e55a45a3` |
| `tests/test_ab4_geometry.py` | 2673 | `3933e6f1e75cfb4f172cdfb0ce19c8ad9c68068665de4974046bfc3b64a64844` |
| `tests/test_ab4_lines.py` | 4581 | `0e513dc63d6ea3e08d15062f9f460eb5ebb6d124b534fe9f7cea2a6478cd30be` |
| `tests/test_ab4_obs_closed_loop.py` | 3070 | `43c2f97bb2d283758b3403f90521d5bccb29ba041a76f719718581b631bbd1af` |
| `tests/test_ab4_pipeline.py` | 2905 | `ccdba4a391f7d7d1374e2934cea8ed4c188477a90a5f4e47808378418a2fe1b5` |
| `tests/test_backend_protocol.py` | 10649 | `7216ddbb727b79f0eb13475a7a4b76866e6a56fa17ffc8fc3a373495d3ffb72d` |
| `tests/test_compatibility_modules.py` | 2482 | `bc1d80630a949a17634d0fbb86d990e1bcc132542dc045fd714f73e8accce375` |
| `tests/test_control_mode_transition.py` | 1455 | `09b0e88df66aa75314b9f803333f606975eddf6bdbddbb861309be446c321772` |
| `tests/test_core_fmu_parity.py` | 5066 | `3f4dba57ec241eb1d5ea45d65385af436426f7b761b9229d133f86deb831ed09` |
| `tests/test_dae_closure.py` | 2588 | `6eb533ae2bd82438ed0cdb7c7e0427c31d830165c031bb807dd1b1e39b38384b` |
| `tests/test_fault_injection.py` | 1579 | `2c7eddf25550a2d42308010aa927937e654b27770cf3c883f17ce6ca8fa1469c` |
| `tests/test_fault_observability.py` | 837 | `06ee71a12a05022b4e513a6c16fd45225f78d4979aec1986c944143d50d6e9f6` |
| `tests/test_fmu_contract.py` | 4594 | `ea9ffc794541e7540618a17802bce4876c61a1c7dff059d0bb53cb34bb1d43d2` |
| `tests/test_fmu_e2e.py` | 7210 | `54b4b713cd18db1870efcb3d43b5d074acfc67cf0f979cf7883226c5a3a8c608` |
| `tests/test_governance_and_calibration_contracts.py` | 6639 | `328af97eb2648d0a4a68cd9c9eaacc36c13c23ef36d373a202c672725631fe35` |
| `tests/test_governance_policy_contracts.py` | 2883 | `f2049b1d7c7b2bd891d82c1c9f1bf601763a1cdcadf4545ab8ea412f4400ef85` |
| `tests/test_identifiability_contracts.py` | 2481 | `8c539d2e1db23791ef1560bd08e806a5eedc0481824d5cf2ad4ad5b8d04abf99` |
| `tests/test_label_and_bottleneck_contracts.py` | 3356 | `89dd9334759ff363cc3b9d98b29583e9c7662e793ee7137e16b2c23189754dde` |
| `tests/test_level_instrumentation.py` | 3428 | `7f84e9f3580eef33c05af4f38eaf8864ffcb39395cca1b83bb2c94e9469f5b0c` |
| `tests/test_manifest_integrity.py` | 3091 | `ee00118da2b4b8a7675fc9bf9689a1b6179b0c139c9d14b729acf28e03290bb8` |
| `tests/test_mass_energy_balance.py` | 1196 | `63618125d0e5e877b48c50e48b3d8a8ad8fd0ac25259fbac20fb5f3ac7d4eafc` |
| `tests/test_multirate_and_process_safety.py` | 2614 | `d6c0eca73ad059ef15d06a06e33c67d7c9e88fd2faae52d856f338439dad6e32` |
| `tests/test_pipeline_contracts.py` | 8963 | `ec28235bce065700cbe847f59c06047bd2d4467b380230b28bdaf50ed81906ab` |
| `tests/test_props_fuels_gas.py` | 2489 | `1635a46ee7870774ea6c957ffda3ac1935564f717dba50509953243abf5af8ef` |
| `tests/test_props_if97.py` | 4466 | `943b842f688fe1b6fcd0b70ce7c711450f34085f87a19a3f90375bf5427d0619` |
| `tests/test_real_fmu_e2e.py` | 4122 | `c54d3736fed272ff2dd305ef2d19e00e8a454be133266280b4fb661a049c8a6b` |
| `tests/test_real_fmu_parity.py` | 4175 | `14af86b135e27ff3a14c8cbbdd35e9a35717f7f545d541d934b3f9c4c3a6ef7a` |
| `tests/test_reproducibility.py` | 535 | `567b9b547919169e83743e027f131738963baffb0f1365e9172c197c29e917ef` |
| `tests/test_safety_hard_stop.py` | 2394 | `364522f951db38c14dcf05dfb1b19ee4e9978b95ba0f9bd0223c0b8f002cdc0b` |
| `tests/test_schema_event_grammar.py` | 1263 | `2d99066f38d2d070878efbd691d63ef8627ac29b139afa2add04cab093b7f2bd` |
| `tests/test_shrink_swell.py` | 1384 | `57ea3299c542ff17976e2ed62dae2ace516fd5d1ed0f5c13fc3e7390257d933e` |
| `tests/test_simulator_run_to_file_smoke.py` | 2890 | `1363ff15d4c5a7a4e34b994bf6c82af96c44eab311c8d2efda4b0ecf7e5fd2c9` |
| `tests/test_validation_battery.py` | 2777 | `7e3fee7695f3869f718e1786dbec26b276ff870b07c149da2ee4cc60f3206e23` |
| `tests/test_workspace_structure.py` | 379 | `960714c1f1b3f7c8526d140dce9adac637114f2cd3a075c52f07d2ac2efa4770` |
