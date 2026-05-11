# SLURM Scripts Migration

As of 2026-05-11, all SLURM scripts have been consolidated into parameterized templates in the `slurm/` directory at the repo root.

## Migration Map

| Old Script | Replacement | Usage |
|---|---|---|
| `run_103fm_15min.slurm` | `slurm/run_pipeline.slurm` | `sbatch --export=STATION=103fm,DURATION=900 slurm/run_pipeline.slurm` |
| `run_kanbet_10min.slurm` | `slurm/run_pipeline.slurm` | `sbatch --export=STATION=kan_bet,DURATION=600 slurm/run_pipeline.slurm` |
| `run_downloaded_30min.slurm` | `slurm/run_pipeline.slurm` | `sbatch --export=STATION=103fm,DURATION=1800 slurm/run_pipeline.slurm` |
| `run_e2e_test.slurm`, `run_e2e_10min.slurm` | `slurm/run_e2e_test.slurm` | `sbatch slurm/run_e2e_test.slurm` |
| `run_gpu_test.slurm` | `slurm/run_gpu_test.slurm` | `sbatch slurm/run_gpu_test.slurm` |
| `reanalyze_ep2.slurm` | `slurm/reanalyze.slurm` | `sbatch --export=EPISODE_ID=2 slurm/reanalyze.slurm` |

## Benefits

- **DRY**: No more copy-paste of identical script logic
- **Maintainability**: Update once, all use cases benefit
- **Clarity**: Parameters are explicit in sbatch command
- **Discoverability**: All scripts in one place (`slurm/`)

## Quick Start

```bash
# Record and analyze 103FM for 15 minutes
sbatch --export=STATION=103fm,DURATION=900 slurm/run_pipeline.slurm

# Record and analyze Kan Bet for 30 minutes
sbatch --export=STATION=kan_bet,DURATION=1800 slurm/run_pipeline.slurm

# Run E2E tests
sbatch slurm/run_e2e_test.slurm

# Validate GPU setup
sbatch slurm/run_gpu_test.slurm

# Re-analyze episode 2
sbatch --export=EPISODE_ID=2 slurm/reanalyze.slurm
```
