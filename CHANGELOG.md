# Changelog

All notable changes to this fork, relative to the verbatim upstream import.

Format: each entry corresponds to one commit. See `git log` for full reasoning and the
measurements behind each change.

## [2.23.26] — 2026-09-29

### Fixed

- **A "mild" hover oscillation generated a filter change.** For a 7-inch the bands are
  `none < 2.0`, `mild < 5.0` deg/s RMS, so "mild" begins only 33 % above "nothing to see" — and
  a flight at **2.67 deg/s RMS** produced `reduce D-term LPF from 80Hz to 48Hz, D from 40 to 28`,
  which costs real phase margin. 2.23.12 established 4 deg/s as the point below which filtering
  is not the limiting factor; the same bar now applies here. The measurement is still reported as
  an observation. A moderate oscillation still acts — there is a test for both.

### Note

- The 38 Hz on that flight is **real** and survives the hover-FFT fix in 2.23.22
  (`dominant_freq_hz = 38.3`, prominence 4.3 against a threshold of 3). An earlier claim in
  conversation that it had become `None` was wrong: it came from reading a key name that does not
  exist (`gyro_freq_hz` rather than `dominant_freq_hz`), so `.get()` returned None. The frequency
  is genuine; it is the *amplitude* that does not justify acting.

## [2.23.25] — 2026-09-29

### Fixed

- **PID advice was generated from as little as 12 s of Acro.** `MIN_ACRO_SECONDS_FOR_STEPS` (10 s)
  is the bar for *computing* a step-response figure; acting on one needs more. The same aircraft,
  with **identical PIDs** (P=53, D=40, FF=187), measured roll overshoot of:

  | Acro span | steps | roll overshoot | pitch overshoot |
  |---|---|---|---|
  | 334 s | 31 | **7.5 %** | 6.1 % |
  | 211 s | 32 | **15.0 %** | 13.3 % |
  | **12 s** | ~11 | **48.6 %** | **63.6 %** |

  The figure rises monotonically as the span shrinks — the estimate degrading, not the tune
  changing. On that 12 s flight it produced `Reduce FF 187→142, Reduce P 53→49, Increase D 40→48`
  marked IMPORTANT, on an aircraft the pilot reported as flying well.

  PID actions now require `MIN_ACRO_SECONDS_FOR_ADVICE` (60 s) **and** `MIN_STEPS_FOR_PID_ADVICE`
  (20). Below either, the measurement is still reported and an info item explains why it is not
  being acted on, quoting the three spans above. A 211 s / 32-step flight still gets advice —
  there is a test for that, so this is a bar rather than a mute.

## [2.23.24] — 2026-09-29

### Changed

- **Altitude-hold findings quote p99 instead of the raw maximum**, in all four reporting sites
  (two finding texts, the terminal line, the HTML table). A **29 ms transient** at the instant
  the altitude target re-latches was headlining **711 cm** beside a **48 cm RMS** — 0.03 % of
  held time, against p95 106 cm and p99 156 cm. 2.23.21 added the percentiles to the data but
  left every display reading the extreme.

  `Altitude hold: RMS 47cm, p99 156cm (90s)` replaces `RMS 48cm, max 711cm`. `max_error_cm` is
  still in the data for anyone who wants it.

## [2.23.23] — 2026-09-29

### Fixed

- **Hover peak-to-peak was set by the single worst sample.** One hover reported **234 deg/s
  peak-to-peak against 3.65 deg/s RMS** — a ratio of 64:1 where a sinusoid gives 2.83 — because
  **11 samples out of 179,000 (11 ms)** exceeded 50 deg/s. The finding then paired a "mild"
  severity with "peak-to-peak 212°/s", which reads as alarming and lent weight to a D-term cut.
  `gyro_p2p` is now the p0.1–p99.9 spread with the true extreme kept as `gyro_p2p_max`: roll on
  that flight reads **21 deg/s** instead of 212.

  Severity itself was always classified on RMS, so no verdict changes — only the number a reader
  judges it by.

  Combined with the hover-FFT fix in 2.23.22, the dominant frequency on that flight becomes
  `None` on all three axes: the 38 Hz that justified *"D-term noise amplification causing
  oscillation during hover"* came from the concatenation joins, not the aircraft. **That
  recommendation is gone.**

## [2.23.22] — 2026-09-29

### Fixed

Four instances of one defect: `np.diff`, `np.unwrap` or an FFT applied to an array assembled
from non-contiguous pieces, where every join is read as signal. An audit of all 21
diff/unwrap/gradient sites and every FFT found three beyond the one that prompted it.

- **The corrected toilet-bowl test was fed stitched segments.** 2.23.21 replaced the detector in
  `analyze_nav_performance` with revolution counting but left it reading `pos_n[poshold_mask]`.
  One log's two hold segments (14 s and 15 s) produced a "toilet bowl" of **18.5 s period —
  longer than either segment that supposedly contained it**. Now counts turns on the longest
  unbroken run. Three real logs: one false positive → none.

- **`detect_hover_oscillation` FFT'd a concatenation.** `hover_gyro = np.concatenate([gy[s:e] …])`
  stitches separate hover periods and the transform ran on the result, so each join injected
  broadband energy into the spectrum that determines the oscillation frequency and severity —
  and the `gyro_oscillation` score. The transform now uses the longest single segment; RMS and
  peak-to-peak still pool everything, since neither involves a derivative.

- **`analyze_gps_quality` counted NaN gaps as position jumps.** `np.diff(pos_n[valid])` joins
  both sides of a missing-data stretch, so a legitimate position change across a 2 s gap read as
  a single-sample teleport.

- **`analyze_position_hold`'s discontinuity check had the same flaw** — in code added by 2.23.7.

### Known

- `generate_charts` decimates heading with `hdg[::ds]` for display, the aliasing issue 2.23.6
  fixed in the metric. Chart only; the reported figure is correct.

## [2.23.21] — 2026-09-29

### Fixed

- **`analyze_nav_performance` carried its own copy of the toilet-bowl detector**, matching
  dominant FFT peaks between the N and E axes — the approach replaced in
  `analyze_position_hold()` by 2.23.7 because it fires on drift. Left unfixed it contradicted the
  corrected test on the same flight, declaring a **16 cm-radius "toilet bowl"** and telling the
  pilot to check a compass that was fine, while `orbit_test()` measured **−0.297 revolutions** in
  101 s. Both now count turns.

- **Altitude-hold error counted the pilot flying.** Altitude hold is *suspended* while the
  throttle stick is off centre: the craft climbs on command, `navTgtPos[2]` stays put, and the
  target re-latches when the stick returns. So the target is a step function and "error" grows
  for as long as the pilot is flying. On one flight this reported **137 cm RMS** over 186 s for a
  hold the pilot experienced as steady. Filtering to samples inside the craft's own
  `alt_hold_deadband` gives **47 cm RMS over 90 s** — which matches what was felt.

  Two earlier attempts are recorded in the code because both were wrong: filtering on target
  *rate* excluded nothing (the target does not ramp), and skipping a settling window after each
  step made it worse (1.37 → 1.58 m) because the error *precedes* the step. The discriminator is
  the stick — and specifically `rcData[3]`, not `rcCommand[3]`, which in AltHold is the altitude
  controller's output and barely moves (std 23 against 56).

- **`max_error_cm` was set by a 29 ms transient** — 7.11 m, 0.032 % of held time, at the instant
  the target re-latches. `p95_error_cm` and `p99_error_cm` are now reported alongside: 1.06 m and
  1.56 m against that 7.11 m maximum.

- **The altitude oscillation test ran across gaps.** Held time arrives in separate runs (40 s,
  35 s, 9 s on that flight) and the FFT was taken over a boolean-masked concatenation, treating
  every join as signal — the defect corrected for heading in 2.23.6. It now runs on the longest
  unbroken run and requires the peak to survive `ALTHOLD_MIN_OSC_CYCLES` (8). The 0.14 Hz warning
  on 47 cm RMS does not survive either condition.

## [2.23.20] — 2026-09-29

### Fixed

- **A log whose header lost its final newline decoded to zero frames.** Real damage: 199 bytes
  vanished mid-line at `H waypoints:0,0`, taking the terminating newline and the following nine
  header lines with them, so binary frame data began immediately after `H waypoints:0`.
  `_find_binary_start()` searched each line for a newline, found none for megabytes, gave up
  (`nl == -1`) and returned the **start of that line** — so the decoder read header text as
  frames and reported nothing for an intact **232 s** flight.

  The line scan now stops at the first control byte, since header text is printable ASCII, and
  locates the binary start at the frame marker just before it. `'H'` is excluded there: it is a
  valid frame type (GPS Home) *and* the first character of every header line, so matching it
  returned the line start. The damaged log now decodes to 232,166 frames with no repair needed.

- **`decode_blackbox_native()` called `sys.exit(1)` from library code**, and under `quiet=True`
  did so with no message — a damaged log produced a bare `SystemExit` with nothing to act on. It
  now raises `BlackboxDecodeError` carrying the decoder stats and header-key count, with a hint
  pointing at header damage when the header looks short. The CLI keeps its exit-1-with-a-message
  behaviour by catching it at the entry point.

## [2.23.19] — 2026-09-28

### Fixed

- **"Consider enabling RPM filter" was recommended on every log.** Its only condition was that
  the filter is off — no check on whether there was noise worth removing, whether the noise was
  of a kind an RPM filter can address, or whether ESC telemetry exists. On one flight it was
  recommended while the noise score was **96/100** (1.7 deg/s above 300 Hz) and the dominant
  source it cited in its own reason string was **propwash at 44 Hz**, which is aerodynamic and
  cannot be tracked by a filter that follows motor rotation.

  That craft had also already flown the experiment: with RPM **ON** and live telemetry at
  ~8000 RPM, attenuation at the filter's own target band changed by **~0 dB on roll and 2.6 dB on
  pitch** against RPM off.

  Now requires the noise amplitude to reach `NOISE_AMPLITUDE_OK_DPS` **and** a rotational source
  to be present (`prop_harmonics`, `motor_imbalance`, `motor_noise`, `bearing_wear`).
  `generate_action_plan()` takes `noise_fp` so it can see the classification. Tests pin all three
  cases: quiet + rotational → no, loud + propwash → no, loud + rotational → yes.

## [2.23.18] — 2026-09-28

### Changed

- **The noise score is computed from amplitude, not dB.** ⚠ **Scores from earlier versions are
  not comparable.** The old scale ran linearly from good = −40 dB to bad = −20 dB and saturated
  at zero above −20, so one log measuring **2.87 deg/s** of filtered gyro noise above 300 Hz
  scored **0/100** while having the best PID (84) and motor (89) scores of seven flights.

  dB re 1 (deg/s)²/Hz is also **bandwidth-dependent**: at a 1 kHz log rate `rms_high` integrates
  over 200 Hz, and the same craft logged at 2 kHz integrates over 700 Hz and reads a different dB
  for identical noise. Re-tuning the endpoints would have fixed today's logs and broken silently
  on a `blackbox_rate_denom` change. Amplitude has neither problem.

  Endpoints are anchored on the constants established for the escalation veto rather than
  invented: `NOISE_SCORE_BAD_DPS = 12.0` matches `NOISE_AMPLITUDE_BAD_DPS` ("genuinely reaches the
  PIDs"), and `NOISE_SCORE_GOOD_DPS = 0.5` is an excellent filtered signal. Results without
  `rms_high_dps` (pre-2.23.9) fall back to the old formula.

  Seven real logs move from 0–51 to **81–99**. The spread compresses because the craft is
  genuinely clean at 0.8–2.9 deg/s throughout — a flight at 6 deg/s scores 52 and at 12 scores 0,
  so the mid-range still discriminates. Noise simply stops being a useful axis for comparing
  flights that are all quiet.

### Fixed

- **"Harmonic Defense" selected on six of seven logs**, across noise scores from 17 to 51. Its
  condition was `has_prop_harmonics and not rpm_enabled` — presence, not magnitude — and presence
  is near-automatic, because the prop-harmonic bands derived from KV span **233–1554 Hz** (2nd)
  and **350–2331 Hz** (3rd), so almost any high-frequency peak falls inside one. With RPM off the
  branch reduced to that alone. Now also requires `worst_recipe_dps >= NOISE_AMPLITUDE_OK_DPS`,
  matching the veto 2.23.12 applied to the sibling branch. All seven logs now select "Balanced";
  a test pins that a genuinely loud craft still gets "Harmonic Defense".

## [2.23.17] — 2026-09-28

### Fixed

- **The short-flight notice added in 2.23.16 crashed the report.** `info_items` entries are
  printed as `item['text']`; it used `title`, so `print_terminal_report` raised
  `KeyError: 'text'`. The item is only appended when confidence is not "good", so it failed on
  **exactly the flights it was meant to help** — every log under 180 s produced no report at all,
  while the four longer ones passed. The full suite passed too, because nothing exercises
  `print_terminal_report` with a short-flight plan.

- **Peaks below 5 Hz were classified as vibration.** `find_noise_peaks()` searched the whole
  spectrum with no lower bound, so the DC bin and sub-flight-band content — stick input, attitude
  changes — entered the peak list and were reported as `Vibration at 0Hz on Pitch, Roll`. The
  accelerometer path filtered `>= 5 Hz` after calling it, but the gyro path passed peaks straight
  to the fingerprinter. The floor now lives inside `find_noise_peaks` so every caller inherits it.

  Not cosmetic: the phantom source fed dominant-source selection and recipe choice. LOG00002 moves
  from "Harmonic Defense" to "Balanced" once it is removed. `NOISE_PEAK_MIN_HZ = 5.0` keeps
  propwash (10–40 Hz) and frame resonance; tests pin that 0.7 Hz pilot input and DC produce no
  peaks while 22 Hz and 120 Hz still do.

### Known

- No test renders a report end-to-end per confidence band, which is why the `title`/`text` slip
  shipped. The added test pins that one key, not the next one.
- **LOG00002 scores noise 0** — a hard bottom-of-scale value on a flight with the best PID and
  motor scores of seven. Unverified; suspect a clamp.
- **Six of seven logs select "Harmonic Defense"**, spanning noise scores 17 to 51. A recipe that
  selects almost regardless of input is describing its threshold rather than the flight.

## [2.23.16] — 2026-09-28

### Added

- **Flight duration now carries a confidence label, and short flights no longer drive trends.**
  Scores were compared across flights of 56 s and 523 s as if they were equal evidence. A short
  log has fewer step events, less throttle variety and less hover, so a single manoeuvre moves
  its score — and on one craft the 56 s flight sat at the top of the table with the best overall
  score of seven.

  `flight_confidence()` labels a flight **low** (<60 s), **limited** (<180 s) or **good**, with a
  weight for aggregation. The label and `duration_s` are stored in the scores dict and surfaced
  as an info item on short flights. **A flight's own scores are never altered** — they are what
  they are — only labelled.

  `FlightDB.get_progression()` now computes the trend from flights that are not low-confidence,
  and when there are fewer than two of those it reports `insufficient` with an explanation rather
  than declaring a direction from short flights.

### Fixed

- The trend tests built synthetic flights of **2–5 seconds** and asserted a trend direction, so
  they never exercised the logic they were written for. Lengthened to 200 s+, with new tests
  pinning that short flights yield `insufficient` and that the confidence bands match the real
  logs (56 s low, 135 s limited, 417 s good).

### Known

- Rejecting one bad P-frame in 2.23.15 changed `total_frames` by one, and the flight DB dedups on
  `(craft, total_frames, duration, firmware)` — so re-analysing a log already in the DB inserts a
  **duplicate row** rather than updating. LOG00002 currently appears twice.

## [2.23.15] — 2026-09-28

### Fixed

- **Root cause of the corruption episodes: P-frames were never validated.** I-frames were
  sanity-checked and rejected on failure; P-frames were appended unconditionally. So one
  mis-parsed P-frame became the predictor baseline for every frame after it, cascading for
  ~200 ms until an I-frame reset the state — producing `gyro_yaw` of **−5,423,494 deg/s** against
  a ±2000 sensor, while the decoder reported `errors: 0`, called no resync and failed no
  validation.

  Proven with an independent decoder: `orangebox` reads the same bytes and finds **zero**
  impossible values in the whole log, with normal ±200 deg/s exactly where we produced −5.4 M.
  The bytes were always sound; the corruption was manufactured here.

  `_validate_p_frame()` now rejects a frame whose gyro exceeds sensor full scale, whose motor
  output is outside throttle range, or whose `loopIteration` goes backwards, then rewinds and
  resyncs. **One bad P-frame is caught per log**, and that is enough:

  | log | before | after |
  |---|---|---|
  | LOG00002 | 212 samples, 1 episode | **0, 0** |
  | LOG00007 | 208 samples, 1 episode | **0, 0** |
  | LOG00005 | 302 samples, 2 episodes | 201 samples, 1 episode |

- **Predictor state now resets on `LOGGING_RESUME`**, since frame history predating a logging
  pause cannot meaningfully predict across it. Note these events do not occur in the sample logs
  (`logging_resumes: 0`), so this is correctness rather than a fix for the above.

### Known

- **LOG00005 retains one episode** (201 samples): values wrong but within the validator's bounds.
  Tightening the bounds risks rejecting real data, so this needs the specific mis-parse located
  first.
- **~40 % of frames differ from `orangebox` by exactly 1**, plus ~3 % by 5–99. The ±1 bulk is
  consistent with a rounding-convention difference — the C reference truncates toward zero
  (2.23.13) while `orangebox` may floor — in which case ours is correct per the reference. **Not
  proven**, and the 5–99 tail does not fit that explanation. Open.
- A divergence test run earlier compared against *sanitized* output and so could not have located
  the episodes; the 2.23.8 sanitizer had already repaired them. Method error, recorded so it is
  not repeated.

## [2.23.14] — 2026-09-28

### Fixed

- **`INC` prediction hardcoded +1 and discarded the delta**, and **`loopIteration` was never
  mapped** (the same gap `gyroRaw` had before 2.23.0). `values[i] = prev[i] + 1` advanced the
  iteration counter once per logged frame instead of once per `P interval`, and each I-frame's
  absolute value then corrected the shortfall — producing a step histogram of 15x1 followed by
  1x17, and an apparent **222 s of "missed logging" on a 417 s flight** that was entirely this
  bug. Now `raw[i] + prev[i] + iter_increment`, with the increment derived from the header's
  `P interval`. LOG00007's histogram collapses to **417,059 steps of exactly 2**.

- ⚠ **Correction to 2.23.13's release note and to the timebase concern generally.** It was
  claimed that the synthetic timebase made every reported frequency wrong by ~5 % and flight
  durations unreliable. **Both were overstated.** With `INC` fixed, `loopIteration` implies
  **998.8–999.9 Hz** against the assumed 1000 — accurate to ~0.1 %. The 947 Hz figure quoted from
  the `orangebox` reference was a median-of-diffs artifact on a field containing I-frame jumps,
  not a measured rate. The synthetic 1 kHz grid was very nearly right all along.

### Changed

- `loop_iteration` is now available to analyses, giving a real **stream-desynchronisation
  detector**: a step other than `P interval` means the decoder lost the frame boundary.

### Known

- **Corruption episodes are decoder desynchronisation, not bad data or dropped frames.** With
  `INC` fixed, 98–99.5 % of all irregular iteration steps fall inside a ~200 ms window around a
  corruption episode (LOG00007 209/212, LOG00005 302/308, LOG00002 213/214), the nearest at
  exactly the episode's start. The reader is interpreting bytes at the wrong offsets for that
  span, which is why `gyro_yaw` reached −5,423,494 and why the episodes survived the arithmetic
  fix in 2.23.13. Root cause not yet located; the next step is byte-level inspection at the frame
  index where sync is lost.
- A few genuinely isolated gaps exist separately (LOG00007 t=3.27 s, 892 iterations), consistent
  with real logging interruptions rather than desync.
- `STRAIGHT_LINE` prediction and the `CLAMP = 2**31` fallback remain broken for the `time` field.
  Lower priority now: `loop_iteration` supplies a sound timebase and gap detection by an easier
  route.

## [2.23.13] — 2026-09-28

### Fixed

- **`AVERAGE_2` prediction floored instead of truncating — the root cause of the "62 Hz
  motor/prop imbalance".** C integer division truncates toward zero; Python's `//` floors toward
  −∞. They differ by exactly 1 whenever the sum is negative and odd, so the decoder carried a
  systematic one-LSB bias that accumulated through each P-frame run and reset at every I-frame:
  a sawtooth at the I-frame cadence. With `gyro_scale = 1.0` that is 1 deg/s per LSB, against the
  1.9–2.4 deg/s peak-to-peak observed.

  It affected every field using predictor 3 — `gyroADC`, `gyroRaw`, `accSmooth`, `attitude` —
  which is why the artifact appeared with an *identical waveform on all three gyro axes*
  (cross-axis r = 0.98) and was diagnosed as a rotating imbalance with harmonics at
  122/184/312/375/438 Hz, all multiples of the reset cadence.

  | | before | after | `orangebox` reference |
  |---|---|---|---|
  | LOG00002 roll p-p | — | **0.325** | 0.317 |
  | LOG00002 pitch | — | **0.095** | 0.079 |
  | LOG00002 yaw | — | **0.087** | 0.078 |
  | LOG00007 roll | 1.918 | **0.434** | — |
  | LOG00007 pitch | 2.419 | **0.362** | — |
  | cross-axis r | 0.98 | **−0.37** | no similarity |

  Our output now agrees with an independent decoder to within 0.02 deg/s, which is stronger
  evidence than the artifact merely disappearing. 2.23.12's cadence detection correctly reports
  `confirmed = False` and is retained as a dormant guard.

  Knock-on effects: noise 20 → 23, PID 31 → 38, and the PID action changed from
  `mc_p_pitch 53 → 66` alone to `mc_p_pitch 66` plus `mc_p_roll 57`. **Every noise and PID figure
  produced before this release was computed with the bias present.**

### Known

- The **corruption episodes are unaffected** (LOG00007 still shows 208 impossible samples at
  t=333.9 s), so they are a separate defect.
- `STRAIGHT_LINE` prediction and the `CLAMP = 2**31` fallback remain broken for the `time` field:
  timestamps go negative from the second sample, 42.5 % of deltas are negative, and the span reads
  2147 s on a 417 s flight. The synthetic uniform timebase is therefore still in use. Fixing this
  is the prerequisite for using the logged timebase.

## [2.23.12] — 2026-09-28

### Fixed

- **A blackbox decoding artifact was being reported as motor/prop imbalance.** Our native decoder
  leaves a periodic artifact locked to the **I-frame cadence**: on one log 1.9–2.4 deg/s
  peak-to-peak with the *same waveform on all three gyro axes* (cross-axis r = 0.98), including a
  +1.2…+1.6 deg/s spike at one phase. It was diagnosed as *"Motor/prop imbalance (strong) at
  62Hz"* with *"Propeller harmonics"* at 122/184/312 Hz — which are simply its 2nd, 3rd and 5th
  multiples — and it drove a recommendation to change `dynamic_gyro_notch_min_hz`.

  Confirmed as ours, not the firmware: decoding the same file with an independent reference
  decoder (`orangebox`) and folding on actual I-frame boundaries gives **0.08–0.32 deg/s of
  formless noise with no cross-axis similarity**, against our 1.9–2.4 deg/s coherent sawtooth.

  The discriminator is **cross-axis similarity**: a rotating imbalance excites axes differently,
  so a near-identical waveform on all three is a logging artifact. A test feeds axis-*asymmetric*
  content at the same frequency and asserts it is **not** suppressed.

  The artifact reached the output through **four independent consumers**, each found only by
  fixing the previous one:

  | consumer | reads | fix |
  |---|---|---|
  | peak classification | tagged peaks | `source: "frame_cadence"`, excluded from dominant source |
  | notch/RPM advice, filter-cutoff chooser | the raw peak list | `flag_cadence_peaks()` marks `is_cadence` at source |
  | recipe selection | the dB noise floor, never peaks | amplitude veto (see below) |
  | propwash display | its own event list | **still open** |

  `frame_cadence_hz()` derives the cadence from `_decoder_stats` and is **never hardcoded** — it
  depends on `blackbox_rate_denom` and the firmware's I-frame interval. It is then **refined to a
  whole frame period**, because the raw frame-count ratio (16.13 → 62.0 Hz) is inexact and the
  error multiplies with harmonic number: 6 × 62.0 = 372 Hz missed a real 375 Hz peak (= 6 × 62.5)
  by 3 Hz, leaving 375 and 437.5 Hz classified as prop harmonics — which selected a recipe that
  set `dynamic_gyro_notch_min_hz = 40`. `sr / round(sr/cadence)` is exact.

  `remove_cadence_artifact()` subtracts the measured per-phase waveform before any noise
  measurement, since the aggregate floor never consults a peak list. What is subtracted is the
  per-phase mean over thousands of periods with its own mean removed, so only the periodic shape
  goes; a test puts a genuine 97 Hz peak alongside and asserts the cadence line drops by >50 %
  while the 97 Hz peak keeps >90 % of its amplitude.

- **Recipe selection had no amplitude check.** `elif noise_floor_db > -35` selected an aggressive
  "Noise Suppression" recipe — gyro lowpass to 60 Hz, notch floor to 30 Hz — for a log measuring
  **−19 dB at 1.7–2.7 deg/s**. 2.23.8 put an amplitude veto on *actions*; recipes are a separate
  path and the same false positive walked straight through. Now gated on
  `worst_noise_dps >= NOISE_AMPLITUDE_OK_DPS`.

  Net on that log: recipe "Noise Suppression" → **"Balanced"**, and no
  `dynamic_gyro_notch_min_hz` recommendation at all.

### Known

- The **propwash display** still prints cadence-frequency events (e.g. "17.9°/s RMS at 62Hz"); it
  builds its own event list and needs the cadence plumbed in separately. Display only, no
  recommendation attached.
- The **noise score** still derives from dB alone, so that log still reads Noise:20 at 2.7 deg/s.
  Unchanged deliberately — scores are recorded per flight downstream.

## [2.23.11] — 2026-09-28

### Fixed

- **An absent `acc_lpf_hz` header field was read as 0, i.e. "no filter".** Absent means
  *unknown*. One log (LOG00005) has a **truncated header** — 47 lines, no sentinel — so the field
  is simply missing, and 2.23.9 concluded full accelerometer bandwidth and produced a vibration
  verdict from data that may have been lowpassed at 15 Hz. Unknown now sets `acc_lpf_unknown` and
  is treated as band-limited, declining the verdict rather than guessing, and the finding says
  "accelerometer lowpass is unknown (header incomplete)". A truncated header is common enough
  (§8) that absent-vs-zero has to be distinguished explicitly.

## [2.23.10] — 2026-09-27

### Fixed

- **Position hold reported only its longest segment.** 2.23.7 fixed *which* phase was analysed
  but still collapsed the result to a single span, and the headline was the longest one. On one
  log that meant reporting **CEP 31.9 cm** while the same flight also held at **98.2 cm**, and
  another flight at **181.1 cm** and 64.7 cm — so a position loop with metre-scale excursions
  read as holding to a foot. It also hid a consistent **0.09–0.21 Hz** oscillation in the
  position error (27–60 % of the 0.05–2 Hz band), which is precisely the symptom a
  "`nav_mc_pos_xy_p` too high" warning describes, and which had therefore been dismissed as
  contradicted by the data.

  `analyze_position_hold_segments()` now measures every held segment. The headline `cep_cm` is
  the **worst** segment, not the longest or the best: a hold is only as good as its poorest
  showing, and an optimistic headline is what caused the misreading. `worst_cep_cm`,
  `best_cep_cm` and a per-segment `segments_detail` (start, duration, navState, CEP, p95, max,
  bowl) are reported alongside, `toilet_bowl` is true if **any** segment shows one, and the
  segments are listed inline in a finding (`40s@32cm, 31s@98cm`).

  When segments disagree by ≥2× the spread is called out explicitly, with the advice to compare
  wind and stick activity before treating it as a tuning problem — a hold that varies 3× between
  segments is more likely conditions than gains, and the point of this change is an honest
  figure, not a pessimistic one.

### Known

- Nav scoring still penalises only above CEP 200 cm, so a 181 cm hold scores 100/100. Left
  unchanged for the same reason as the noise score: scores are recorded per flight downstream.

## [2.23.9] — 2026-09-27

### Fixed

- **Accelerometer vibration was overstated ~60x, by three compounding errors.** One clean 7-inch
  log reported `Z: High vibration (0.66g RMS)`.

  1. **Wrong unit.** The code divided `accSmooth` by 981 "because INAV accel is in cm/s²". It is
     not: the firmware writes `accADC[i] = accADCf[i] * acc_1G` (`blackbox.c:1645`) with
     `accADCf` already in g, and the header publishes `acc_1G` (2048 here). Checked against
     physics — mean `acc_z` over an airborne span is 2156 raw, which is **1.053 g** at `acc_1G`
     and **2.198 g** at 981; a hovering quad reads 1 g. `acc_1G` is sensor-dependent, so it is
     now read, never assumed (a test runs the whole analysis at `acc_1g = 512`).
  2. **Manoeuvres counted as vibration.** `rms_g` was broadband about the mean. Sub-5 Hz was
     excluded from *peak* detection but not from the RMS the findings used, so on a log with
     211 s of Acro including loops, Z measured 0.314 g broadband of which **0.287 g was below
     5 Hz**. Vibration is now judged on the 5 Hz high-passed signal, matching INAV's own method
     (`acceleration.c`: 5 Hz PT1 floor, squared difference smoothed at 2 Hz, vector-summed).
  3. **The logged signal cannot see vibration at all when `acc_lpf_hz` is low.** `accSmooth` is
     written *after* the accel soft LPF and notch, while INAV computes `accVib` *before* them
     (`acceleration.c:607` vs `:616`). With the default `acc_lpf_hz = 15` there is no content at
     prop frequencies, so a figure from it measures the filter's stopband: that log read
     **0.011 g "above 50 Hz"** through a 15 Hz lowpass while INAV's own `accVib` reported
     **0.644 g**. Logs below `ACC_LPF_TRUSTWORTHY_HZ` are now marked `band_limited` and yield no
     verdict from `accSmooth`.

  **`accVib` is now mapped and authoritative.** INAV logs its own pre-filter, 3-axis vibration
  level and nothing read the field (same gap as `gyroRaw` in 2.23.0). It drives the verdict, with
  mean/p95/max reported. Thresholds 0.6 g moderate / 1.5 g warning, set below ArduPilot's ~1.5 g
  acceptable / ~3 g problematic for its equivalent VIBE, since this is a flight mean. A
  band-limited log with no `accVib` now says the assessment is unavailable and points at the gyro
  spectrum, instead of inventing a number.

- **X/Y asymmetry was a ratio with no floor.** `max/min` over two near-zero figures: one log
  reported "X-axis vibration 3.1× higher" from X=0.075 g against Y=0.024 g, while another at
  2.9× on 0.055/0.019 stayed silent — a knife-edge on quantities too small to mean anything.
  Now requires the louder axis to reach `ASYMMETRY_MIN_G` and the log not to be band-limited,
  since no mechanical claim can rest on the filter's passband.

  Across three real logs: `accVib` mean **0.357 g** (gentle flight) vs **0.644 / 0.669 g**
  (aggressive Acro), i.e. the figure tracks how hard the craft is flown rather than a fixed
  airframe resonance. The spurious "High vibration" and asymmetry warnings are gone; a
  proportionate "Moderate vibration 0.64g RMS (INAV accVib, mean; peak 3.33g)" remains.

## [2.23.8] — 2026-09-27

### Fixed

- **Physically impossible samples reached every metric.** One 417 s log contained `gyro_yaw`
  readings of **−5,423,494 deg/s** against a sensor full scale of ±2000 — a single 208 ms
  episode whose magnitude decayed by exactly a factor of 3 per 16 ms (62.5 Hz ringing, Q ≈ 2.9),
  0.050 % of samples. Consequences: the filtered yaw noise figure read **958 deg/s RMS above
  50 Hz against 3.3 for the raw signal**, which is impossible since a lowpass cannot amplify;
  and the only two `navPos` steps over 5 m in the whole log sat at the same instant, producing
  a phantom "42 m GPS jump" at an implied 21891 m/s.

  `find_impossible_samples()` / `sanitize_decoded_data()` now run once in the decode path, so
  every downstream analysis inherits the repair. Limits are deliberately generous — the job is
  catching the impossible, not validating. Repair is **cross-field and episode-based**: once any
  field proves corruption, a ±50 ms window is treated as suspect for all per-sample fields,
  because the evidence is that one bad point in the file damages several at once. Short gaps are
  **interpolated, not blanked** — `compute_psd()` has no NaN handling, so blanking would poison
  every FFT and be worse than the spike; gaps beyond 1 s are left NaN rather than inventing a
  second of flight. After: yaw 958 → **1.383** deg/s (below its raw 3.312, as it must be),
  `navPos` steps over 5 m **2 → 0**, roll and pitch unchanged to three decimals.

  Attitude is excluded from tight bounds because it **wraps**: INAV clamps `attitude[]` to
  ±1800 decidegrees but was observed emitting −1801 while passing through inverted
  (−1793 → −1801 → +1791). A limit of 1800 flagged three Acro passes as corruption and would
  have interpolated away ~0.3 s of genuine loop data. The limit is twice full scale, which
  still catches gross corruption.

- **A dB figure with no reference drove CRITICAL.** `rms_high` is the mean of `psd_db` above
  300 Hz, i.e. dB relative to 1 (deg/s)²/Hz — a quantity no pilot can judge — and the
  per-frame-size thresholds sit close together. A real 7-inch log measured **−19.0 dB on roll
  against a −20 dB "bad" threshold** and was reported CRITICAL, *"severe and likely causing
  visible oscillation"* — **1 dB over the line**, for an actual amplitude of **1.712 deg/s RMS**.
  The same craft's *unfiltered* gyro measures ~13 deg/s in that band, so the filters were
  removing 87 % of it and the result was still called severe.

  `noise_amplitude_dps()` recovers deg/s RMS by integrating the PSD, and `analyze_noise()` now
  reports `rms_low_dps` / `rms_mid_dps` / `rms_high_dps` / `rms_gt50_dps` beside the dB figures.
  Escalation now requires the amplitude to agree, at both paths — the LPF action (capped at
  IMPORTANT below 12 deg/s, dropped below 4) and the noise-fingerprint remedies (a separate
  per-peak `power_db` metric, whose severity language is withheld and replaced with the measured
  amplitude). Where amplitude is unknown, previous behaviour is preserved. Reason strings now
  name the amplitude, so "High-freq noise at −19 dB avg" reads "… (1.7 deg/s RMS above 300Hz)".

  Verified not over-reaching: on that log both CRITICALs become "Low amplitude (2.7 deg/s RMS)"
  while the structural `dynamic_gyro_notch_min_hz: 60 → 40` recommendation survives as the top
  action — the craft's 1P sits at 62 Hz, 2 Hz above the notch floor.

### Known

- The **noise score itself** still derives from `rms_high` in dB alone, so that log still scores
  Noise:20 despite 2.7 deg/s of actual noise. Left unchanged deliberately: the score is recorded
  per flight in downstream tuning logs, and changing the formula would break comparability with
  every historical row.

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
