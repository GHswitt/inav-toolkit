# Changelog

All notable changes to this fork, relative to the verbatim upstream import.

Format: each entry corresponds to one commit. See `git log` for full reasoning and the
measurements behind each change.

## [2.23.1] — 2026-09-21

Continuation of `inav-toolkit` 2.23.0 by agoliveira. Eight changes, all found while
analysing logs from a 7" quadcopter on INAV 9.1.0 (SpeedyBee F7 V3, 6S, 1050 KV).

### Fixed

- **Crash on `sub_actions = None`.** Actions are constructed as
  `"sub_actions": sub if sub else None`, so the key exists holding `None`. Two readers
  tested only for key presence and raised
  `TypeError: 'NoneType' object is not iterable`, aborting with exit 1 and no report.

- **Motor protocol enum was Betaflight's.** INAV has no `ONESHOT42`, so every DSHOT rate
  was reported one position low — DSHOT300 shown as DSHOT150.

- **Filter type enum was Betaflight's.** A phantom duplicate `PT1` shifted `PT2`/`PT3`
  down one — `dterm_lpf_type = PT3` shown as PT2.

- **Impossible per-cell voltages.** `analyze_power()` ran ~120 lines before
  `config["_cell_count"]` was assigned, so it fell back to `round(max_v / 4.2)`, which
  under-counts any pack that is not fully charged. A 6S at 23.05 V guessed 5 cells and
  printed a healthy 3.69 V/cell as 4.45 V/cell. `--cells` was passed and still ignored.

- **Baro "spikes" counted samples, not excursions.** At 1 kHz a single one-second
  excursion scored 1000. One flight reported "1209 baro spikes" for 33 excursions
  totalling 1.21 s of 386 s, the largest of them at takeoff.

### Changed

- **Sub-3 Hz wobble is no longer attributed to P-term on frames under 10 inches.** The
  wind-buffeting classification was gated on `frame_inches >= 10`, so smaller frames got
  a 30 % P-cut recommendation at top priority for what is wind, pilot input or
  position-hold correction. Measured on a 7": 95 % of gyro energy at 0.4–3 Hz with 0.60
  coherence against the rate setpoint, versus 0.06 % at 20–50 Hz where a P oscillation
  would actually be. The downstream scoring and action code already handled
  `wind_buffeting` correctly; the gate simply prevented small frames from reaching it.

### Added

- **`gyroRaw[]` is now mapped.** INAV logs it whenever the GYRO_RAW blackbox field is
  enabled, specifically so the filter chain can be evaluated against `gyroADC[]`. It was
  never decoded, so all noise assessment ran on the already-filtered signal. Changes no
  existing output.

- **Dynamic gyro LPF read from `--config`.** Under `gyro_filter_mode = DYNAMIC` the static
  `gyro_main_lpf_hz` is inert, but the blackbox header cannot express the mode or the
  sweep range, so the analyzer recommended changing a setting the FC ignores.
  `CLI_TO_CONFIG` now maps `gyro_filter_mode`, `gyro_dyn_lpf_min_hz` and
  `gyro_dyn_lpf_max_hz`, and both emitters (the action list and the "Tuning Recipe" paste
  block, which previously disagreed with each other) report the equivalent cutoff as
  information instead of a no-op command.

  Pass `dump all`, not `diff all` — a diff omits settings at their default, which
  produces a false "RPM filter enabled but no ESC telemetry port configured" critical.

## [2.23.0] — upstream

Last release by agoliveira, imported verbatim from the PyPI source distribution.
See the original README for the project's own history.
