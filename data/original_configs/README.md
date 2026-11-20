# Base simulator configuration

[Home](../../README.md) · [Quick start](../../REPRODUCIBILITY.md) · [Documentation](../../docs/README.md)

[ab4_marine_aux.yaml](ab4_marine_aux.yaml) is a reference copy of the [public simulator configuration](../../simulator_source/configs/ab4_marine_aux.yaml). It preserves the base model's geometry, operating point, control settings, actuator limits, sensor specifications and protection settings.

## Base and study configurations

| Setting | Public base YAML | Study-time configuration |
|---|---|---|
| Time step | `1.0 s` | `2.0 s` |
| Closed-loop source | `truth` | `obs` |
| Study horizon | See base YAML | `21,600 s` |
| Intervention policy | See base YAML | `process_protection_without_schedule_severity_oracle` |

The study used pilot and economizer-leak patches in addition to its runtime settings. This YAML therefore does not, by itself, recreate the 24 study episodes.

Per-episode `*_config_applied.json` files belong to the external R2 package's `data/original_configs/` directory. They are not bundled here.

## Related inputs

- [Block design](../block_design.json) records the development and evaluation schedule.
- [Reconstructed plant and sensor parameters](../reconstructed_inputs/plant_parameters_table1_table2_from_source.json) support Tables 1–2.
- [Source provenance](../../docs/SOURCE_PROVENANCE.md) explains the development snapshot and study-patched source.
- [Data provenance](../../docs/DATA_PROVENANCE.md) identifies the original simulation and R2 packages.
