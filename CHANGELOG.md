# Changelog

All notable changes to this fork, relative to the verbatim upstream import.

Format: each entry corresponds to one commit. See `git log` for full reasoning and the
measurements behind each change.

## [2.23.7] — 2026-09-27

### Fixed

- **Position-hold analysis ran on an IDLE phase, and the toilet-bowl test could not work.**
  A log produced `Oscillatory position drift detected at 0.05Hz (20.0s) - possible toilet bowl,
  check compass` on a craft whose compass was independently confirmed healthy. Four separate
  defects:

  1. **The phase was not a hold.** The caller gated on *whether* a nav phase existed
     (`state_val > 1`) and then chose `max(phases)` over **all** of them, selecting a 74 s
     `NAV_PID_IDLE` span — the navigation controller was not running. Meanwhile the two
     genuine `POSHOLD_3D_IN_PROGRESS` segments in the same log (39.5 s and 30.6 s) were never
     examined. Selection is now made from phases whose `navState` is in
     `POSITION_HELD_NAV_IDS` (PosHold, RTH loiter, WP hold time — states with a *stationary*
     hold point; RTH-head-home and WP-enroute are excluded because the target is moving).
  2. **The target was not yet set.** `navTgtPos` is a step function written once when a hold
     point is taken (9–11 unique values across a 417 s log), but a phase span begins at the
     INITIALIZE state, before that write. Leading samples compared position against a target
     of 0 while the craft was 128 m from the origin. The unset sentinel is now excluded, along
     with a 2 s settling window after each target step, since right after a new point is taken
     the craft is travelling *to* it.
  3. **The spectral test was structurally incapable.** It searched 0.05–0.5 Hz using
     `nperseg = 20*sr`, whose frequency resolution is exactly 0.05 Hz — so the lowest bin in
     the band *was* the band edge, and every slow drift peaked there. Dominance was judged
     against the sum of only ~9 bins, which red noise passes routinely (measured: 0.532 against
     a 0.4 trigger). It also summed the two error components' PSDs, discarding the phase
     relationship that *defines* circular motion — so linear sloshing was indistinguishable
     from an orbit. And a 20 s "period" in a 70 s record is 3.5 cycles, which no periodogram
     can separate from drift.
  4. **Angles were unwrapped across excluded gaps**, making each join count as rotation.

  `orbit_test()` replaces the spectral approach with the direct physical measurement: a toilet
  bowl is a steadily rotating error vector, so count net revolutions and directional
  consistency on an unbroken stretch. Thresholds: radius > 100 cm, ≥ 1.5 turns, ≥ 65 %
  consistent. On synthetic cases it detects a 0.1 Hz orbit (6.95 turns, 99 % consistent) and an
  expanding spiral, while rejecting equal-amplitude linear sloshing (50 % consistent) and
  random-walk drift (**0 false positives across 40 seeds**). A rotary-spectrum test on the
  complex path was tried first and discarded: it separated orbit from slosh perfectly
  (circularity 1.000 vs 0.000) but scored random-walk drift at 0.54, because at 3.5 cycles
  chance one-sidedness in a single bin is not distinguishable from a real orbit.

  Same log, after: **CEP 7895 → 31.9 cm**, no toilet bowl, PosHold score 75 → 100, measured
  over 39.5 s of `navState 7` with the provenance reported.

- **`max_drift_cm` could be set by one bad GPS fix.** At a 1 kHz log rate a single sample
  defines it. The same log reported 44 m max drift against a 32 cm CEP: `navPos` stepped 42 m
  in **one 1 ms sample** (21891 m/s implied) and spent 0.032 s above 40 m. `drift_p95_cm` and
  `drift_p99_cm` are now reported, and when the max exceeds 10× p99 the finding says it is an
  isolated position-estimate discontinuity rather than hold performance, and points at GPS fix
  quality instead of the nav PIDs.

- **A stale-target guard added earlier in this work was itself wrong** and is corrected here
  before release: it compared target travel against craft travel, but in a real hold the target
  is *supposed* to sit still, so that test would have suppressed the genuine catastrophic case
  of a craft drifting far from a correctly held target. It now tests the unambiguous condition
  — `navTgtPos` all-zero for the whole log, i.e. never recorded — and a test asserts that a
  stationary non-zero target is still analysed and its orbit still caught.

## [2.23.6] — 2026-09-27

### Fixed

- **"Baro spike events" were mostly the detrend filter's own lag.** Spikes were counted
  against a 0.5 Hz lowpass "trend", which cannot follow a fast descent — it lags by more than
  the 1 m threshold, and the lag is then charged to the barometer. On one 417 s log with 211 s
  of Acro this reported **47 spike events**, of which **44 occurred while the craft was moving
  faster than 1 m/s vertically** (median 10 m/s during events; 0.8 m/s over the flight). The
  two largest were the takeoff transient and a 10 m/s dive. The same lag inflated the noise
  figure from 6 cm to 23 cm, and because the threshold is `max(5σ, 100 cm)` derived from that
  noise, the metric also became **insensitive to real spikes: it found only 4 of 12 synthetic
  1.5 m spikes injected into that log**.

  `baro_detrend()` now fits a local quadratic (Savitzky-Golay, order 2, 0.4 s) instead, which
  tracks constant-acceleration flight exactly while leaving a short disturbance intact. Spike
  detection also runs on the airborne span only (the takeoff transient was the single largest
  "spike", at 102 cm against a 100 cm threshold), and `threshold_events()` merges crossings
  within 150 ms so one disturbance counts once rather than once per crossing.

  Same log, after: **0 spike events**, noise 23.4 → 5.9 cm. With 12 synthetic spikes injected:
  **exactly 12 detected**. The warning now names the threshold and the worst excursion, and
  says what to do about it ("cover the barometer with open-cell foam").

- **Compass health was measured across Acro.** `analyze_compass_health()` ran over the whole
  log, so on a 417 s flight that was 211 s of aggressive Acro with loops, the "heading jitter"
  statistic was mostly the pilot's yaw stick. It reported 8.4 deg/s RMS, tripping the
  `> 5.0` WARNING ("check compass mounting") and scoring the compass 45/100 on a compass that
  was fine. Heading is now measured only where the flight controller holds it: nav modes that
  own position or course (PosHold, RTH, WP, CourseHold) unconditionally, plus Angle, Horizon
  and AltHold while the craft is actually hovering (tilt ≤ 12°, body rates ≤ 30 deg/s).
  AltHold is deliberately in the hover-gated tier rather than the nav tier — it holds
  altitude only, so a banked turn in AltHold is flying, not drift. Pilot-commanded yaw
  (|rcCommand[2]| > 20) and pre-takeoff/post-landing ground time are excluded throughout.
  The measurement window is now reported alongside the figure in both the console and HTML
  output, so the number can be read in context.

- **Heading jitter double-counted its own quantisation.** The 1 kHz-to-50 Hz reduction picked
  every 19th sample instead of averaging them. `attitude[2]` is logged in decidegrees, so one
  0.1° quantiser step differentiated over a 1/50 s interval reads as **5.3 deg/s** — decimation
  folds that alias straight into the passband, on a craft whose real hover jitter is under
  2 deg/s. Box-averaging each block attenuates it instead. Measured over the same hover
  windows of one log: 2.60 deg/s decimated vs 1.81 deg/s averaged, i.e. 1.87 deg/s of the
  original figure was pure alias.

- **Derivatives were taken across excluded stretches.** Masking a boolean selection and then
  calling `np.diff` joins the two sides of every gap and reports the join as a data step.
  `contiguous_runs()` now splits the selection into runs and statistics are pooled across
  them, and heading drift is summed per run — heading changed while the gate was open is
  drift, heading changed in between was the pilot turning.

Net effect on one 417 s log (LOG00007, QMC5883L on a Foxeer M10Q 250): jitter 8.37 → 3.41
deg/s, drift 1.06 → 0.38 deg/s, compass score 45 → 85, spurious mounting WARNING gone.

## [2.23.5] — 2026-09-27

### Fixed

- **Deceleration overshoot was measured outside nav modes.** The position-hold, altitude-hold
  and velocity-controller sections of `analyze_nav_performance()` mask to the relevant mode;
  the deceleration section did not. Outside nav control `navTgtPos` is stale, so the
  "position error" is just distance flown since. On a log that was 83 % Acro this produced an
  average overshoot of 6744 cm, a worst case of 26762 cm — from an Acro pass at 22.7 m/s —
  and a recommendation to reduce `nav_mc_vel_xy_p` from 40 to 28. After the fix the same log
  reports 72 cm average, 131 cm worst, no recommendation, and the nav score rises from 50 to
  80. Events are also discarded if the craft leaves nav control during the settling window.

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
