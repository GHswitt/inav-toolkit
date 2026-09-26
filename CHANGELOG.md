# Changelog

All notable changes to this fork, relative to the verbatim upstream import.

Format: each entry corresponds to one commit. See `git log` for full reasoning and the
measurements behind each change.

## [2.23.4] — 2026-09-26

### Fixed

- **Ground time contaminated the noise, vibration and PID metrics.** Seconds spent armed on
  the ground with the props turning were averaged in with the flight. On a real 523 s log
  pitch and yaw read −4 dB over the first ten seconds against −24/−29 dB in flight, pushing
  the whole-log noise score from 14 to 1 even though the flying was slightly cleaner than
  the previous flight. `find_airborne_span()` now detects the flight span from barometric
  altitude (falling back to motor output), and noise, D-term noise, accelerometer vibration,
  motor statistics, hover oscillation and PID response are measured on it. Nav analysis,
  flight modes, the map and power analysis still use the whole log, and the report prints
  what was excluded. Half-second smoothing before thresholding stops a single-sample baro
  spike from marking an entire log as airborne.

## [2.23.3] — 2026-09-22

### Fixed

- **Flight modes were decoded from the wrong field with the wrong bit layout.** INAV
  logs two slow-frame mode fields: `flightModeFlags` is the *switch* mask (`boxId_e`),
  `activeFlightModeFlags` the modes in effect (`flightModeFlags_e`). Everything read the
  switch mask through tables missing `BOXCAMSTAB`, so from bit 7 up each mode was one
  position off. Consequences: PosHold nav analysis never ran (its mask was always empty),
  PosHold was labelled "MANUAL" in the mode overlay and flight map, failsafe RTH detection
  read the camera-stab box, and the crash postmortem reported **RX loss for every PosHold
  selection** (switch bit 9 is PosHold, not failsafe). All consumers now use
  `activeFlightModeFlags`, with the switch mask kept for the arm switch and as a fallback
  for older logs. Verified against INAV 9.1.0 source and a real log.
- `vtol_configurator.INAV_MODE_NAMES` (aux permanent IDs) corrected — RTH/PosHold were
  swapped, among others. Unreferenced, so no behaviour change.

## [2.23.2] — 2026-09-22

### Fixed

- **CLI dumps were parsed without regard to profiles.** A `dump all` lists every control,
  mixer and battery profile; flattening them kept control profile 3's defaults for every
  per-profile key. With `--config`, a board flying P 53 / I 95 / D 40 was reported as
  P 40 / I 30 / D 23, with a false "STALE DATA — 14 parameters differ" warning. The parser
  now returns master settings plus the *active* profiles, and three duplicate parsing loops
  in `blackbox_analyzer` share it.

- **Step response measured against the wrong signal, in the wrong modes.** Overshoot was
  computed as gyro (°/s) against stick position (`rcCommand`, ±500) — off by `rate / 50`,
  i.e. 1.4× at rate 70 — and over the whole log, including Angle and nav modes where the
  stick commands an attitude rather than a rate. It now uses the logged rate setpoint
  `axisRate[]` and, when a log has ≥ 10 s of Acro, only the Acro segments, identified from
  `activeFlightModeFlags`. The report prints the flight-mode breakdown and what the step
  figures were computed against. On the log that exposed it, pitch overshoot went from
  59 % to 6 % (the pilot saw no pitch problem) and yaw from 37 % to 68 % (the pilot did see
  yaw overshoot).

- **Per-module version strings.** 2.23.1 bumped `__init__` and `pyproject.toml` but left
  the hard-coded `VERSION` / `REPORT_VERSION` in six modules at 2.23.0, so the CLI tools
  still reported 2.23.0 and `test_module_version_consistent` failed. All now agree.

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
