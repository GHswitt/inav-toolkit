#!/usr/bin/env python3
"""
INAV Toolkit test suite.

Run:  python3 -m pytest tests/ -v
  or: python3 tests/test_smoke.py          (standalone, no pytest needed)

Requires: pip install -e ".[test]"
"""
import json
import os
import subprocess
import sys

import numpy as np
import pytest

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_DIR = os.path.dirname(SCRIPT_DIR)
TESTS_DIR = SCRIPT_DIR
FIXTURES_DIR = os.path.join(TESTS_DIR, "fixtures")
sys.path.insert(0, PROJECT_DIR)


# ─── Helpers ──────────────────────────────────────────────────────────────────

def run_module(module, *args):
    """Run a toolkit module via python -m, return (stdout, stderr, rc)."""
    result = subprocess.run(
        [sys.executable, "-m", module, *args],
        capture_output=True, text=True, cwd=PROJECT_DIR)
    return result.stdout, result.stderr, result.returncode


def run_entry(cmd, *args):
    """Run an entry point command, return (stdout, stderr, rc)."""
    result = subprocess.run(
        [cmd, *args],
        capture_output=True, text=True, cwd=PROJECT_DIR)
    return result.stdout, result.stderr, result.returncode


# ═════════════════════════════════════════════════════════════════════════════
# Filter Math (parametrized)
# ═════════════════════════════════════════════════════════════════════════════

class TestFilterMath:
    """Unit tests for filter phase shift calculations."""

    @pytest.mark.parametrize("ftype,freq,cutoff,expected", [
        ("PT1",    100, 100, -45.0),
        ("PT2",    100, 100, -90.0),
        ("PT3",    100, 100, -135.0),
        ("PT1",    50,  100, -26.6),
        ("PT1",    200, 100, -63.4),
    ])
    def test_phase_shift(self, ftype, freq, cutoff, expected):
        from inav_toolkit.blackbox_analyzer import _phase_shift
        result = _phase_shift(ftype, freq, cutoff)
        assert abs(result - expected) < 1.0, f"{ftype} at {freq}Hz: got {result}, expected {expected}"

    @pytest.mark.parametrize("q,expected", [
        (0.5,  -90.0),
        (250,  -90.0),
    ])
    def test_biquad_at_cutoff(self, q, expected):
        from inav_toolkit.blackbox_analyzer import _phase_shift
        result = _phase_shift("BIQUAD", 100, 100, q=q)
        assert abs(result - expected) < 0.1

    def test_biquad_below_cutoff(self):
        from inav_toolkit.blackbox_analyzer import _phase_shift
        result = _phase_shift("BIQUAD", 10, 100, q=0.5)
        assert abs(result) < 15

    def test_filter_phase_lag_returns_dict(self):
        from inav_toolkit.blackbox_analyzer import estimate_filter_phase_lag
        lag = estimate_filter_phase_lag(65, 50, "PT1")
        assert "degrees" in lag and "ms" in lag
        assert abs(lag["degrees"] - (-37.6)) < 1

    def test_filter_phase_lag_zero_cutoff(self):
        from inav_toolkit.blackbox_analyzer import estimate_filter_phase_lag
        lag = estimate_filter_phase_lag(0, 50, "PT1")
        assert lag["degrees"] == 0.0 and lag["ms"] == 0.0


# ═════════════════════════════════════════════════════════════════════════════
# Version Flags
# ═════════════════════════════════════════════════════════════════════════════

class TestVersionFlags:
    """Verify --version works on all entry points."""

    @pytest.mark.parametrize("entry_point", [
        "inav-analyze", "inav-params", "inav-msp", "inav-toolkit",
    ])
    def test_entry_point_version(self, entry_point):
        out, _, rc = run_entry(entry_point, "--version")
        assert rc == 0
        from inav_toolkit import __version__
        assert __version__ in out

    def test_module_version_consistent(self):
        """All modules should have the same version as __init__."""
        from inav_toolkit import __version__
        from inav_toolkit.blackbox_analyzer import REPORT_VERSION
        assert REPORT_VERSION == __version__


# ═════════════════════════════════════════════════════════════════════════════
# Blackbox Analyzer: Imports
# ═════════════════════════════════════════════════════════════════════════════

class TestBlackboxImports:

    def test_report_version(self):
        from inav_toolkit.blackbox_analyzer import REPORT_VERSION
        assert REPORT_VERSION is not None

    def test_fingerprint_callable(self):
        from inav_toolkit.blackbox_analyzer import fingerprint_noise, format_noise_fingerprint_terminal
        assert callable(fingerprint_noise) and callable(format_noise_fingerprint_terminal)


# ═════════════════════════════════════════════════════════════════════════════
# Noise Fingerprinting
# ═════════════════════════════════════════════════════════════════════════════

class TestNoiseFingerprinting:

    def test_empty_results(self):
        from inav_toolkit.blackbox_analyzer import fingerprint_noise
        result = fingerprint_noise([None, None, None], {})
        assert result["dominant_source"] == "none"
        assert result["peaks"] == []

    def test_with_peaks(self):
        from inav_toolkit.blackbox_analyzer import fingerprint_noise
        fake_noise = [
            {
                "axis": "Roll",
                "peaks": [
                    {"freq_hz": 160.0, "power_db": -8.0, "prominence": 15.0},
                    {"freq_hz": 55.0, "power_db": -15.0, "prominence": 10.0},
                ],
                "noise_start_freq": 120.0,
                "rms_low": -20, "rms_mid": -15, "rms_high": -10,
                "freqs": np.array([0]), "psd_db": np.array([0]),
            },
            {
                "axis": "Pitch",
                "peaks": [
                    {"freq_hz": 158.0, "power_db": -9.0, "prominence": 14.0},
                ],
                "noise_start_freq": 115.0,
                "rms_low": -22, "rms_mid": -16, "rms_high": -12,
                "freqs": np.array([0]), "psd_db": np.array([0]),
            },
            None,
        ]
        result = fingerprint_noise(fake_noise, {"_n_motors": 4})
        assert len(result["peaks"]) >= 1
        assert result["dominant_source"] not in ("none", "clean")
        for p in result["peaks"]:
            for key in ("freq_hz", "source", "confidence", "detail"):
                assert key in p

    def test_prop_harmonics_matching(self):
        from inav_toolkit.blackbox_analyzer import fingerprint_noise
        fake_noise = [{
            "axis": "Roll",
            "peaks": [{"freq_hz": 250.0, "power_db": -5.0, "prominence": 20.0}],
            "noise_start_freq": 200.0,
            "rms_low": -30, "rms_mid": -20, "rms_high": -5,
            "freqs": np.array([0]), "psd_db": np.array([0]),
        }]
        harmonics = [{"harmonic": 1, "min_hz": 200, "max_hz": 300, "label": "fundamental"}]
        result = fingerprint_noise(fake_noise, {"_n_motors": 4}, prop_harmonics=harmonics)
        matched = [p for p in result["peaks"] if p["source"] == "prop_harmonics"]
        assert len(matched) >= 1
        assert matched[0]["confidence"] == "high"

    def test_cross_axis_structural(self):
        from inav_toolkit.blackbox_analyzer import fingerprint_noise
        fake_noise = []
        for axis in ["Roll", "Pitch", "Yaw"]:
            fake_noise.append({
                "axis": axis,
                "peaks": [{"freq_hz": 85.0, "power_db": -12.0, "prominence": 10.0}],
                "noise_start_freq": 60.0,
                "rms_low": -18, "rms_mid": -14, "rms_high": -20,
                "freqs": np.array([0]), "psd_db": np.array([0]),
            })
        result = fingerprint_noise(fake_noise, {"_n_motors": 4})
        structural = [p for p in result["peaks"] if p["source"] == "structural"]
        assert len(structural) >= 1

    def test_fingerprint_has_remedies(self):
        """Enhanced fingerprinting should include remedy suggestions."""
        from inav_toolkit.blackbox_analyzer import fingerprint_noise
        fake_noise = [{
            "axis": "Roll",
            "peaks": [{"freq_hz": 160.0, "power_db": -8.0, "prominence": 15.0}],
            "noise_start_freq": 120.0,
            "rms_low": -20, "rms_mid": -15, "rms_high": -10,
            "freqs": np.array([0]), "psd_db": np.array([0]),
        }]
        result = fingerprint_noise(fake_noise, {"_n_motors": 4})
        for p in result["peaks"]:
            assert "remedy" in p, f"Peak at {p['freq_hz']}Hz missing remedy field"
            assert len(p["remedy"]) > 0


# ═════════════════════════════════════════════════════════════════════════════
# RPM / Prop Harmonics
# ═════════════════════════════════════════════════════════════════════════════

class TestRPMEstimation:

    def test_rpm_range(self):
        from inav_toolkit.blackbox_analyzer import estimate_rpm_range
        idle, maxrpm = estimate_rpm_range(motor_kv=900, cell_count=6)
        assert 0 < idle < maxrpm
        assert 15000 < maxrpm < 25000

    def test_prop_harmonics(self):
        from inav_toolkit.blackbox_analyzer import estimate_prop_harmonics
        h = estimate_prop_harmonics((3000, 20000), n_blades=3)
        assert len(h) == 3
        assert h[0]["label"] == "fundamental"
        assert h[0]["min_hz"] < h[0]["max_hz"]
        assert abs(h[0]["max_hz"] - 1000) < 1


# ═════════════════════════════════════════════════════════════════════════════
# Frame Profiles (parametrized)
# ═════════════════════════════════════════════════════════════════════════════

class TestFrameProfiles:

    @pytest.mark.parametrize("size", [5, 7, 10, 12, 15])
    def test_profile_exists(self, size):
        from inav_toolkit.blackbox_analyzer import get_frame_profile
        p = get_frame_profile(size)
        assert p["frame_inches"] == size
        for key in ("gyro_lpf_range", "ok_overshoot", "dterm_lpf_range", "filter_safety"):
            assert key in p

    def test_larger_frame_wider_filters(self):
        """Larger frames should have lower filter cutoffs."""
        from inav_toolkit.blackbox_analyzer import get_frame_profile
        p5 = get_frame_profile(5)
        p10 = get_frame_profile(10)
        assert p10["gyro_lpf_range"][0] < p5["gyro_lpf_range"][0]


# ═════════════════════════════════════════════════════════════════════════════
# Filter Recommendation Engine
# ═════════════════════════════════════════════════════════════════════════════

class TestFilterRecommendation:

    def test_compute_recommended_filter_basic(self):
        from inav_toolkit.blackbox_analyzer import compute_recommended_filter, get_frame_profile
        freqs = np.linspace(0, 250, 500)
        psd = np.full_like(freqs, -45.0)
        psd[freqs > 80] = -20.0

        noise_results = [{
            "axis": "Roll", "freqs": freqs, "psd_db": psd,
            "peaks": [{"freq_hz": 120.0, "power_db": -15.0, "prominence": 10.0}],
            "noise_start_freq": 80.0,
            "rms_low": -40, "rms_mid": -20, "rms_high": -25,
        }]
        profile = get_frame_profile(5)
        result = compute_recommended_filter(noise_results, 100, "gyro", profile)
        assert result is not None
        assert 40 <= result <= 90

    def test_clean_spectrum_no_change(self):
        from inav_toolkit.blackbox_analyzer import compute_recommended_filter, get_frame_profile
        freqs = np.linspace(0, 250, 500)
        psd = np.full_like(freqs, -50.0)
        noise_results = [{
            "axis": "Roll", "freqs": freqs, "psd_db": psd,
            "peaks": [],
            "noise_start_freq": 250.0,
            "rms_low": -50, "rms_mid": -50, "rms_high": -50,
        }]
        profile = get_frame_profile(5)
        result = compute_recommended_filter(noise_results, 100, "gyro", profile)
        assert result is None or result >= 80

    def test_compute_filter_recommendations(self):
        """Comprehensive filter recommendation with notch suggestions."""
        from inav_toolkit.blackbox_analyzer import compute_filter_recommendations, get_frame_profile
        freqs = np.linspace(0, 250, 500)
        psd = np.full_like(freqs, -45.0)
        spike_idx = np.argmin(np.abs(freqs - 160))
        psd[spike_idx - 2:spike_idx + 3] = -5.0

        noise_results = [{
            "axis": "Roll", "freqs": freqs, "psd_db": psd,
            "peaks": [{"freq_hz": 160.0, "power_db": -5.0, "prominence": 20.0}],
            "noise_start_freq": 80.0,
            "rms_low": -40, "rms_mid": -20, "rms_high": -25,
        }]
        profile = get_frame_profile(5)
        recs = compute_filter_recommendations(noise_results, {"_n_motors": 4}, profile)
        assert recs is not None
        assert "gyro_lpf_hz" in recs


# ═════════════════════════════════════════════════════════════════════════════
# Param Analyzer
# ═════════════════════════════════════════════════════════════════════════════

class TestParamAnalyzer:

    @pytest.mark.parametrize("frame_size", ["5", "7", "10"])
    def test_setup_mode(self, frame_size):
        out, err, rc = run_module("inav_toolkit.param_analyzer", "--setup", frame_size, "--voltage", "6S")
        assert rc == 0
        assert "mc_p_roll" in out.lower() or "set mc_p_roll" in out.lower()

    def test_setup_json(self):
        out, err, rc = run_module("inav_toolkit.param_analyzer", "--setup", "10", "--json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, dict)

    def test_diff_analysis(self):
        diff_path = os.path.join(TESTS_DIR, "test_basic_diff.txt")
        if not os.path.exists(diff_path):
            pytest.skip("Fixture not found")
        out, err, rc = run_module("inav_toolkit.param_analyzer", diff_path)
        assert rc == 0
        assert "SUMMARY" in out


# ═════════════════════════════════════════════════════════════════════════════
# VTOL Configurator
# ═════════════════════════════════════════════════════════════════════════════

class TestVTOLConfigurator:

    def test_non_vtol_diff(self):
        diff_path = os.path.join(TESTS_DIR, "test_basic_diff.txt")
        if not os.path.exists(diff_path):
            pytest.skip("Fixture not found")
        out, err, rc = run_module("inav_toolkit.vtol_configurator", diff_path)
        assert rc == 0

    def test_vtol_analysis(self):
        diff_path = os.path.join(TESTS_DIR, "test_vtol_diff.txt")
        if not os.path.exists(diff_path):
            pytest.skip("Fixture not found")
        out, err, rc = run_module("inav_toolkit.vtol_configurator", diff_path)
        assert rc == 0
        assert "TRICOPTER" in out

    def test_vtol_json(self):
        diff_path = os.path.join(TESTS_DIR, "test_vtol_diff.txt")
        if not os.path.exists(diff_path):
            pytest.skip("Fixture not found")
        out, err, rc = run_module("inav_toolkit.vtol_configurator", diff_path, "--json")
        assert rc == 0
        data = json.loads(out)
        assert isinstance(data, list)


# ═════════════════════════════════════════════════════════════════════════════
# End-to-End Pipeline Tests (using synthetic fixtures)
# ═════════════════════════════════════════════════════════════════════════════

class TestE2EPipeline:
    """End-to-end analysis pipeline tests using synthetic CSV data."""

    def test_parse_clean_hover(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log
        csv_path = os.path.join(FIXTURES_DIR, "clean_hover.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        assert data["n_rows"] == 4000
        assert abs(data["sample_rate"] - 500.0) < 10.0
        for key in ("gyro_roll", "gyro_pitch", "gyro_yaw",
                     "setpoint_roll", "motor0", "motor1"):
            assert key in data

    def test_noise_analysis_clean(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log, analyze_noise
        csv_path = os.path.join(FIXTURES_DIR, "clean_hover.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        sr = data["sample_rate"]
        roll_noise = analyze_noise(data, "Roll", "gyro_roll", sr)
        assert roll_noise is not None
        strong_peaks = [p for p in roll_noise["peaks"] if p["power_db"] > -10 and p["freq_hz"] > 20]
        assert len(strong_peaks) == 0, f"Clean hover shouldn't have strong peaks above 20Hz: {strong_peaks}"

    def test_noise_analysis_noisy(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log, analyze_noise
        csv_path = os.path.join(FIXTURES_DIR, "noisy_motors.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        sr = data["sample_rate"]
        roll_noise = analyze_noise(data, "Roll", "gyro_roll", sr)
        assert roll_noise is not None
        peak_freqs = [p["freq_hz"] for p in roll_noise["peaks"]]
        found_160 = any(140 <= f <= 180 for f in peak_freqs)
        found_85 = any(70 <= f <= 100 for f in peak_freqs)
        assert found_160, f"Expected peak near 160Hz, got: {peak_freqs}"
        assert found_85, f"Expected peak near 85Hz, got: {peak_freqs}"

    def test_full_fingerprint_on_noisy_data(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log, analyze_noise, fingerprint_noise
        csv_path = os.path.join(FIXTURES_DIR, "noisy_motors.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        sr = data["sample_rate"]
        noise_results = []
        for axis, key in [("Roll", "gyro_roll"), ("Pitch", "gyro_pitch"), ("Yaw", "gyro_yaw")]:
            noise_results.append(analyze_noise(data, axis, key, sr))
        fp = fingerprint_noise(noise_results, {"_n_motors": 4})
        assert fp["dominant_source"] != "none"
        assert len(fp["peaks"]) >= 1
        for p in fp["peaks"]:
            assert "remedy" in p

    def test_short_flight_survives(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log, analyze_noise
        csv_path = os.path.join(FIXTURES_DIR, "short_flight.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        assert data["n_rows"] == 600
        sr = data["sample_rate"]
        roll_noise = analyze_noise(data, "Roll", "gyro_roll", sr)
        assert roll_noise is not None

    def test_motor_analysis(self):
        from inav_toolkit.blackbox_analyzer import parse_csv_log, analyze_motors
        csv_path = os.path.join(FIXTURES_DIR, "noisy_motors.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        motor_result = analyze_motors(data, data["sample_rate"])
        assert motor_result is not None
        assert "balance_spread_pct" in motor_result

    def test_filter_recommendation_pipeline(self):
        from inav_toolkit.blackbox_analyzer import (
            parse_csv_log, analyze_noise, compute_recommended_filter, get_frame_profile
        )
        csv_path = os.path.join(FIXTURES_DIR, "noisy_motors.csv")
        if not os.path.exists(csv_path):
            pytest.skip("Run generate_fixtures.py first")
        data = parse_csv_log(csv_path)
        sr = data["sample_rate"]
        noise_results = []
        for axis, key in [("Roll", "gyro_roll"), ("Pitch", "gyro_pitch"), ("Yaw", "gyro_yaw")]:
            noise_results.append(analyze_noise(data, axis, key, sr))
        profile = get_frame_profile(5)
        rec = compute_recommended_filter(noise_results, 100, "gyro", profile)
        assert rec is not None
        assert 30 <= rec <= 200


# ═════════════════════════════════════════════════════════════════════════════
# Multi-flight Trend Analysis
# ═════════════════════════════════════════════════════════════════════════════

class TestTrendAnalysis:

    def test_trend_data_generation(self):
        import tempfile
        from inav_toolkit.flight_db import FlightDB
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FlightDB(os.path.join(tmpdir, "test.db"))
            for i, score in enumerate([55, 62, 68, 75]):
                plan = {
                    "scores": {
                        "overall": score, "noise": score + 5, "pid": score - 5,
                        "pid_measurable": True, "motor": 80, "gyro_oscillation": score,
                    },
                    "verdict": "OK" if score > 60 else "NEEDS_WORK",
                    "verdict_text": "Test flight",
                    "actions": [],
                    "noise_fingerprint": {"peaks": [], "dominant_source": "clean", "summary": ""},
                }
                config = {"craft_name": "TEST_QUAD", "_duration_s": 120 + i * 10,
                          "_n_motors": 4, "looptime": "1000"}
                # 200 s+ per flight: below 60 s get_progression reports
                # "insufficient" by design, so a 2 s fixture never exercised the
                # trend logic these tests were written for.
                data = {"sample_rate": 500.0,
                        "time_s": np.arange(100000 + i * 500) / 500.0}
                hover_osc = [
                    {"axis": "Roll", "severity": "low", "gyro_rms": 3.0 - i * 0.3, "gyro_p2p": 8.0},
                    {"axis": "Pitch", "severity": "low", "gyro_rms": 2.8 - i * 0.2, "gyro_p2p": 7.0},
                    {"axis": "Yaw", "severity": "low", "gyro_rms": 1.5, "gyro_p2p": 4.0},
                ]
                db.store_flight(plan, config, data, hover_osc=hover_osc)
            prog = db.get_progression("TEST_QUAD")
            assert prog["trend"] in ("improving", "stable"), f"Got: {prog}"
            assert len(prog["flights"]) >= 2
            assert all(f["confidence"] == "good" for f in prog["flights"])
            db.close()

    def test_short_flights_do_not_drive_a_trend(self):
        """A 56 s log has fewer step events and less hover than a 523 s one, so a
        direction must not be declared from short flights alone."""
        import tempfile
        from inav_toolkit.flight_db import FlightDB
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FlightDB(os.path.join(tmpdir, "short.db"))
            for i, score in enumerate((55, 75)):
                plan = {"scores": {"overall": score, "noise": score, "pid": score,
                                   "pid_measurable": True, "motor": 80,
                                   "gyro_oscillation": score},
                        "verdict": "OK", "verdict_text": "t", "actions": [],
                        "noise_fingerprint": {"peaks": [], "dominant_source": "clean",
                                              "summary": ""}}
                config = {"craft_name": "SHORTY", "_n_motors": 4, "looptime": "1000"}
                # distinct lengths: the DB dedups on (craft, frames, duration)
                data = {"sample_rate": 500.0,
                        "time_s": np.arange(15000 + i * 2000) / 500.0}   # 30 s, 34 s
                db.store_flight(plan, config, data)
            prog = db.get_progression("SHORTY")
            assert prog["trend"] == "insufficient"
            assert all(f["confidence"] == "low" for f in prog["flights"])
            assert any(c.get("type") == "low_confidence" for c in prog["changes"])
            db.close()

    def test_confidence_bands(self):
        from inav_toolkit.blackbox_analyzer import flight_confidence
        assert flight_confidence(56)[0] == "low"
        assert flight_confidence(135)[0] == "limited"
        assert flight_confidence(417)[0] == "good"
        assert flight_confidence(56)[1] < flight_confidence(417)[1]

    def test_generate_trend_html(self):
        """Test HTML trend report generation."""
        import tempfile
        from inav_toolkit.flight_db import FlightDB
        try:
            from inav_toolkit.blackbox_analyzer import generate_trend_report
        except ImportError:
            pytest.skip("generate_trend_report not yet implemented")
        with tempfile.TemporaryDirectory() as tmpdir:
            db = FlightDB(os.path.join(tmpdir, "test.db"))
            for i, score in enumerate([55, 62, 68, 75, 80]):
                plan = {
                    "scores": {
                        "overall": score, "noise": score + 5, "pid": score - 5,
                        "pid_measurable": True, "motor": 80, "gyro_oscillation": score,
                    },
                    "verdict": "OK",
                    "verdict_text": "Test flight",
                    "actions": [],
                    "noise_fingerprint": {"peaks": [], "dominant_source": "clean", "summary": ""},
                }
                config = {"craft_name": "TEST_QUAD", "_duration_s": 120 + i * 30,
                          "_n_motors": 4, "looptime": "1000"}
                # 200 s+ per flight: below 60 s get_progression reports
                # "insufficient" by design, so a 2 s fixture never exercised the
                # trend logic these tests were written for.
                data = {"sample_rate": 500.0,
                        "time_s": np.arange(100000 + i * 500) / 500.0}
                hover_osc = [
                    {"axis": "Roll", "severity": "low", "gyro_rms": 3.0 - i * 0.2, "gyro_p2p": 8.0},
                    {"axis": "Pitch", "severity": "low", "gyro_rms": 2.8 - i * 0.15, "gyro_p2p": 7.0},
                    {"axis": "Yaw", "severity": "low", "gyro_rms": 1.5, "gyro_p2p": 4.0},
                ]
                db.store_flight(plan, config, data, hover_osc=hover_osc)
            prog = db.get_progression("TEST_QUAD", limit=20)
            html_path = os.path.join(tmpdir, "trend.html")
            generate_trend_report(prog, "TEST_QUAD", html_path)
            assert os.path.exists(html_path)
            with open(html_path) as f:
                html = f.read()
            assert "TEST_QUAD" in html
            assert "Score" in html or "score" in html
            db.close()


class TestSanityCheck:
    """Test pre-flight sanity check engine."""

    def _make_diff(self, **overrides):
        """Build a minimal diff all text with overrides."""
        lines = [
            "# INAV/TESTBOARD 9.0.1 Feb 22 2026 / 12:00:00 (abc123)",
        ]
        settings = {
            "name": "TEST_QUAD",
            "platform_type": "MULTIROTOR",
            "motor_pwm_protocol": "DSHOT300",
            "failsafe_procedure": "RTH",
            "mc_p_roll": 40, "mc_p_pitch": 44,
            "mc_d_roll": 25, "mc_d_pitch": 25,
            "roll_rate": 50, "pitch_rate": 50, "yaw_rate": 40,
            "gyro_main_lpf_hz": 110, "dterm_lpf_hz": 110,
            "looptime": 500,
        }
        settings.update(overrides)
        for k, v in settings.items():
            if isinstance(v, bool):
                lines.append(f"set {k} = {'ON' if v else 'OFF'}")
            else:
                lines.append(f"set {k} = {v}")
        # GPS UART by default
        lines.append("serial 1 2 115200 57600 0 115200")
        # RX UART
        lines.append("serial 0 64 115200 57600 0 115200")
        # ARM mode
        lines.append("aux 0 0 1 1800 2100")
        # ANGLE mode
        lines.append("aux 1 1 2 1800 2100")
        # RTH mode
        lines.append("aux 2 11 3 1800 2100")
        return "\n".join(lines)

    def test_good_config_passes(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff()
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        fails = [i for i in items if i.status == SanityItem.FAIL]
        assert len(fails) == 0, f"Unexpected fails: {fails}"

    def test_no_arm_switch(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff()
        # Remove aux lines (no ARM)
        diff = "\n".join(l for l in diff.splitlines() if not l.startswith("aux"))
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        arm_fails = [i for i in items if i.category == "Arming" and i.status == SanityItem.FAIL]
        assert len(arm_fails) >= 1

    def test_drop_failsafe_fails(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(failsafe_procedure="DROP")
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        fs_fails = [i for i in items if i.category == "Failsafe" and i.status == SanityItem.FAIL]
        assert len(fs_fails) >= 1

    def test_inverted_battery_fails(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(bat_voltage_cell_min=450, bat_voltage_cell_max=420)
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        batt_fails = [i for i in items if i.category == "Battery" and i.status == SanityItem.FAIL]
        assert len(batt_fails) >= 1

    def test_motor_inverted_asks(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(motor_direction_inverted=True)
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        motor_asks = [i for i in items if i.category == "Motors" and i.status == SanityItem.ASK]
        assert len(motor_asks) >= 1

    def test_zero_p_term_fails(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(mc_p_roll=0)
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        pid_fails = [i for i in items if i.category == "PIDs" and i.status == SanityItem.FAIL]
        assert len(pid_fails) >= 1

    def test_extreme_pids_fails(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(mc_p_roll=150, mc_p_pitch=150)
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        pid_fails = [i for i in items if i.category == "PIDs" and i.status == SanityItem.FAIL]
        assert len(pid_fails) >= 1

    def test_nav_without_gps_fails(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff()
        # Remove GPS UART
        diff = "\n".join(l for l in diff.splitlines()
                         if not (l.startswith("serial 1") and "2 115200" in l))
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, interactive=False)
        nav_fails = [i for i in items if i.category == "Navigation" and i.status == SanityItem.FAIL]
        assert len(nav_fails) >= 1

    def test_pid_frame_mismatch_asks(self):
        from inav_toolkit.param_analyzer import parse_diff_all, run_sanity_check, SanityItem
        diff = self._make_diff(mc_p_roll=44, mc_p_pitch=46)
        parsed = parse_diff_all(diff)
        items = run_sanity_check(parsed, frame_inches=10, interactive=False)
        pid_asks = [i for i in items if i.category == "PIDs" and i.status == SanityItem.ASK]
        assert len(pid_asks) >= 1

    def test_json_output(self):
        out, err, rc = run_module(
            "inav_toolkit.param_analyzer", "--check", "--no-interactive",
            "--json", os.path.join(TESTS_DIR, "test_basic_diff.txt"))
        data = json.loads(out)
        assert isinstance(data, list)
        assert len(data) > 0
        assert all("status" in i and "category" in i for i in data)

    def test_check_exit_code_clean(self):
        """Good config returns exit code 0."""
        import tempfile
        diff = self._make_diff()
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(diff)
            f.flush()
            out, err, rc = run_module(
                "inav_toolkit.param_analyzer", "--check", "--no-interactive", f.name)
        os.unlink(f.name)
        assert rc == 0, f"Expected rc=0, got {rc}\n{out}"

    def test_check_exit_code_bad(self):
        """Bad config returns exit code 1."""
        import tempfile
        diff = self._make_diff(failsafe_procedure="DROP", mc_p_roll=0)
        with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False) as f:
            f.write(diff)
            f.flush()
            out, err, rc = run_module(
                "inav_toolkit.param_analyzer", "--check", "--no-interactive", f.name)
        os.unlink(f.name)
        assert rc == 1, f"Expected rc=1, got {rc}\n{out}"


class TestComparison:
    """Test comparative flight analysis."""

    def test_analyze_for_compare(self):
        """Test the comparison analysis pipeline with synthetic data."""
        from inav_toolkit.blackbox_analyzer import (
            _analyze_for_compare, generate_action_plan, analyze_noise,
            analyze_pid_response, analyze_motors, analyze_dterm_noise,
            detect_hover_oscillation, fingerprint_noise,
        )
        fixture = os.path.join(FIXTURES_DIR, "clean_hover.csv")
        if not os.path.exists(fixture):
            pytest.skip("clean_hover.csv fixture not found (run generate_fixtures.py)")

        # Create a minimal args namespace
        class Args:
            frame = 5
            props = None
            blades = 3
            cells = None
            kv = None
        args = Args()

        result = _analyze_for_compare(fixture, args)
        assert "plan" in result
        assert "scores" in result["plan"]
        assert "noise_results" in result
        assert "pid_results" in result
        assert "data" in result

    def test_comparison_noise_chart(self):
        """Test comparison noise overlay chart generation."""
        from inav_toolkit.blackbox_analyzer import (
            _create_comparison_noise_chart, analyze_noise
        )
        # Create minimal noise results
        n = 1000
        sr = 500.0
        freqs = np.fft.rfftfreq(256, 1.0 / sr)
        psd_db = -40 + np.random.randn(len(freqs)) * 5

        nr_a = [{"axis": ax, "freqs": freqs, "psd_db": psd_db,
                  "peaks": [{"freq_hz": 150, "power_db": -20}]}
                 for ax in ["Roll", "Pitch", "Yaw"]]
        nr_b = [{"axis": ax, "freqs": freqs, "psd_db": psd_db - 3,
                  "peaks": [{"freq_hz": 150, "power_db": -23}]}
                 for ax in ["Roll", "Pitch", "Yaw"]]

        chart = _create_comparison_noise_chart(nr_a, nr_b, "Flight A", "Flight B")
        assert isinstance(chart, str)
        assert len(chart) > 100  # valid base64

    def test_comparison_html(self):
        """Test comparison HTML generation structure."""
        from inav_toolkit.blackbox_analyzer import _generate_comparison_html

        def _make_res(score, logfile="test.bbl"):
            return {
                "plan": {
                    "scores": {"overall": score, "noise": score + 5, "pid": score - 5, "motor": 80},
                    "verdict_text": "Test verdict",
                    "actions": [],
                },
                "config": {"craft_name": "TEST", "roll_p": 40, "gyro_lowpass_hz": 110},
                "data": {"time_s": np.array([0, 60])},
                "noise_results": [None, None, None],
                "pid_results": [None, None, None],
                "logfile": logfile,
            }

        html = _generate_comparison_html(
            _make_res(60, "A.bbl"), _make_res(75, "B.bbl"),
            {}, "A", "B")
        assert "INAV Flight Comparison" in html
        assert "60" in html
        assert "75" in html


class TestReplay:
    """Test interactive replay HTML generation."""

    def test_downsample(self):
        from inav_toolkit.blackbox_analyzer import _downsample
        arr = np.arange(10000)
        ds = _downsample(arr, 1000)
        assert len(ds) <= 1100  # approximately 1000
        assert ds[0] == 0

    def test_downsample_short(self):
        from inav_toolkit.blackbox_analyzer import _downsample
        arr = np.arange(50)
        ds = _downsample(arr, 1000)
        assert len(ds) == 50  # no downsampling needed

    def test_replay_html_generation(self):
        """Test replay HTML output contains expected Plotly.js elements."""
        from inav_toolkit.blackbox_analyzer import _generate_replay_html

        n = 2000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n) * 10,
            "gyro_pitch": np.random.randn(n) * 10,
            "gyro_yaw": np.random.randn(n) * 5,
            "setpoint_roll": np.random.randn(n) * 10,
            "setpoint_pitch": np.random.randn(n) * 10,
            "setpoint_yaw": np.random.randn(n) * 5,
            "motor0": np.random.uniform(1000, 2000, n),
            "motor1": np.random.uniform(1000, 2000, n),
            "motor2": np.random.uniform(1000, 2000, n),
            "motor3": np.random.uniform(1000, 2000, n),
            "throttle": np.random.uniform(1000, 1800, n),
            "n_rows": n, "sample_rate": sr,
            "_slow_frames": [],
        }
        config = {"craft_name": "TEST_QUAD", "firmware_revision": "INAV 9.0"}
        html = _generate_replay_html(config, data, sr)

        # Plotly.js instead of Chart.js
        assert "plotly" in html.lower()
        assert "TEST_QUAD" in html
        # Plotly div IDs
        assert "plotRoll" in html
        assert "plotMotors" in html
        # Synced x-axis across all panels
        assert "plotly_relayout" in html
        # Flight mode overlay bar
        assert "modeBar" in html
        # Spectrogram waterfall (gyro data present so spectrogram computed)
        assert "plotSpectro" in html
        # WebGL rendering
        assert "scattergl" in html

    def test_replay_with_spectrogram(self):
        """Test replay HTML includes noise spectrogram waterfall."""
        from inav_toolkit.blackbox_analyzer import _generate_replay_html, _compute_spectrogram

        n = 2000
        sr = 500.0
        gyro = np.random.randn(n) * 10
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": gyro,
            "n_rows": n, "sample_rate": sr,
            "_slow_frames": [],
        }

        html = _generate_replay_html({"craft_name": "T"}, data, sr)
        assert "plotSpectro" in html
        assert "heatmap" in html

        # Also test spectrogram computation directly
        times, freqs, power = _compute_spectrogram(gyro, sr, nperseg=256)
        assert len(times) > 0
        assert len(freqs) > 0
        assert len(power) == len(freqs)
        assert len(power[0]) == len(times)
        assert max(freqs) <= 500

    def test_replay_flight_modes(self):
        """Test flight mode extraction from slow frames."""
        from inav_toolkit.blackbox_analyzer import _extract_flight_modes

        sr = 500.0
        n = 5000
        # Values as INAV 9.1 logs them (taken from a real flight): flightModeFlags
        # is the switch mask (boxId_e), activeFlightModeFlags the modes in effect
        # (flightModeFlags_e). PosHold implies Angle and AltHold in the latter.
        data = {
            "time_s": np.arange(n) / sr,
            "n_rows": n, "sample_rate": sr,
            "_slow_frames": [
                (0, {"flightModeFlags": 1, "activeFlightModeFlags": 0}),        # armed, Acro
                (1000, {"flightModeFlags": 11, "activeFlightModeFlags": 9}),    # Angle+AltHold
                (3000, {"flightModeFlags": 513, "activeFlightModeFlags": 41}),  # PosHold (box 9)
            ],
        }
        modes = _extract_flight_modes(data, sr)
        assert len(modes) == 3
        assert "ARM" in modes[0]["label"] and "ACRO" in modes[0]["label"]
        assert "ANGLE" in modes[1]["label"] and "NAV ALTHOLD" in modes[1]["label"]
        assert "NAV POSHOLD" in modes[2]["label"]
        assert "MANUAL" not in modes[2]["label"]

    def test_replay_flight_modes_switch_mask_fallback(self):
        """Logs without activeFlightModeFlags fall back to the switch mask,
        numbered by boxId_e: RTH is box 8, PosHold box 9 (BOXCAMSTAB is 7)."""
        from inav_toolkit.blackbox_analyzer import _extract_flight_modes

        sr = 500.0
        n = 3000
        data = {
            "time_s": np.arange(n) / sr,
            "n_rows": n, "sample_rate": sr,
            "_slow_frames": [
                (0, {"flightModeFlags": 1 | (1 << 9)}),     # ARM + NAV POSHOLD box
                (1500, {"flightModeFlags": 1 | (1 << 8)}),  # ARM + NAV RTH box
            ],
        }
        modes = _extract_flight_modes(data, sr)
        assert "NAV POSHOLD" in modes[0]["label"]
        assert "NAV RTH" in modes[1]["label"]



class TestLogQuality:
    """Tests for log quality scorer."""

    def test_good_log(self):
        """Test that a well-formed log gets GOOD grade."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 5000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n) * 50,
            "gyro_pitch": np.random.randn(n) * 50,
            "gyro_yaw": np.random.randn(n) * 20,
            "setpoint_roll": np.random.randn(n) * 30,
            "motor0": np.random.uniform(1000, 2000, n),
            "motor1": np.random.uniform(1000, 2000, n),
            "throttle": np.random.uniform(1100, 1800, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll", "gyro_pitch", "gyro_yaw",
                              "setpoint_roll", "motor0", "motor1", "throttle"],
        }
        q = assess_log_quality(data)
        assert q["usable"] is True
        assert q["grade"] == "GOOD"
        assert q["stats"]["has_gyro"] is True

    def test_too_short(self):
        """Test that a very short log is UNUSABLE."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 100
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll"],
        }
        q = assess_log_quality(data)
        assert q["grade"] == "UNUSABLE"
        assert q["usable"] is False
        assert any("short" in i["message"] or "only" in i["message"].lower() for i in q["issues"])

    def test_no_gyro(self):
        """Test that missing gyro data is UNUSABLE."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 5000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "motor0": np.random.uniform(1000, 2000, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["motor0"],
        }
        q = assess_log_quality(data)
        assert q["usable"] is False
        assert any("gyro" in i["message"].lower() for i in q["issues"])

    def test_low_sample_rate(self):
        """Test that low sample rate is flagged."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 500
        sr = 50.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n) * 50,
            "setpoint_roll": np.random.randn(n) * 30,
            "motor0": np.random.uniform(1000, 2000, n),
            "throttle": np.random.uniform(1100, 1800, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll", "setpoint_roll", "motor0", "throttle"],
        }
        q = assess_log_quality(data)
        assert any("sample rate" in i["message"].lower() for i in q["issues"])

    def test_ground_only_detection(self):
        """Test detection of no-flight (ground-only) logs."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 5000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n) * 50,
            "setpoint_roll": np.zeros(n),      # no stick movement
            "setpoint_pitch": np.zeros(n),
            "throttle": np.ones(n) * 1000,     # throttle at minimum
            "motor0": np.random.uniform(1000, 2000, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll", "setpoint_roll", "setpoint_pitch",
                              "throttle", "motor0"],
        }
        q = assess_log_quality(data)
        assert any("stick" in i["message"].lower() or "ground" in i["message"].lower()
                    for i in q["issues"])

    def test_corrupt_frames(self):
        """Test corrupt frame detection from decoder stats."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 5000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.random.randn(n) * 50,
            "setpoint_roll": np.random.randn(n) * 30,
            "motor0": np.random.uniform(1000, 2000, n),
            "throttle": np.random.uniform(1100, 1800, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll", "setpoint_roll", "motor0", "throttle"],
            "_decoder_stats": {"i_frames": 100, "p_frames": 200, "errors": 150},
        }
        q = assess_log_quality(data)
        assert any("corrupt" in i["message"].lower() for i in q["issues"])

    def test_all_zeros_gyro(self):
        """Test dead sensor detection."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality

        n = 5000
        sr = 500.0
        data = {
            "time_s": np.arange(n) / sr,
            "gyro_roll": np.zeros(n),
            "gyro_pitch": np.random.randn(n) * 50,
            "setpoint_roll": np.random.randn(n) * 30,
            "motor0": np.random.uniform(1000, 2000, n),
            "throttle": np.random.uniform(1100, 1800, n),
            "n_rows": n, "sample_rate": sr,
            "found_columns": ["gyro_roll", "gyro_pitch", "setpoint_roll",
                              "motor0", "throttle"],
        }
        q = assess_log_quality(data)
        assert any("zeros" in i["message"].lower() and "roll" in i["message"].lower()
                    for i in q["issues"])


class TestMarkdownReport:
    """Tests for Markdown report generation."""

    def test_basic_report(self):
        """Test markdown report contains expected sections."""
        from inav_toolkit.blackbox_analyzer import generate_markdown_report, get_frame_profile

        profile = get_frame_profile(5, 5, 3)
        config = {"craft_name": "TestQuad", "firmware_revision": "INAV 9.0.0"}
        data = {
            "time_s": np.arange(5000) / 500.0,
            "sample_rate": 500.0,
        }
        noise_results = [None, None, None]
        pid_results = [
            {"tracking_delay_ms": 3.5, "avg_overshoot_pct": 12.0},
            {"tracking_delay_ms": 4.0, "avg_overshoot_pct": 8.0},
            {"tracking_delay_ms": None, "avg_overshoot_pct": None},
        ]
        motor_analysis = None
        plan = {
            "scores": {"overall": 72, "noise": 85, "pid": 60, "motor": 90},
            "verdict": "NEEDS_WORK",
            "verdict_text": "Room for improvement",
            "findings": [
                {"severity": "warning", "message": "Roll delay slightly high"},
            ],
            "noise_fingerprint": [],
            "actions": [
                {"action": "Lower P gain", "param": "mc_p_pitch", "current": "44",
                 "new": "38", "reason": "Reduce overshoot"},
            ],
        }

        md = generate_markdown_report(plan, config, data, noise_results,
                                      pid_results, motor_analysis, profile)
        assert "TestQuad" in md
        assert "72/100" in md
        assert "mc_p_pitch" in md
        assert "Recommended Changes" in md
        assert "set mc_p_pitch = 38" in md
        assert "INAV Toolkit" in md

    def test_report_with_quality(self):
        """Test markdown report includes quality info when provided."""
        from inav_toolkit.blackbox_analyzer import generate_markdown_report, get_frame_profile

        profile = get_frame_profile(5, 5, 3)
        config = {"craft_name": "T", "firmware_revision": "INAV 9"}
        data = {"time_s": np.arange(1000) / 500.0, "sample_rate": 500.0}
        plan = {"scores": {"overall": 50}, "verdict": "OK", "verdict_text": "OK",
                "findings": [], "noise_fingerprint": [], "actions": []}
        quality = {
            "grade": "MARGINAL",
            "issues": [{"severity": "WARN", "message": "Short log"}],
        }

        md = generate_markdown_report(plan, config, data, [None]*3, [None]*3,
                                      None, profile, quality)
        assert "MARGINAL" in md
        assert "Short log" in md

    def test_report_with_deferred_actions(self):
        """Test markdown report shows deferred actions separately."""
        from inav_toolkit.blackbox_analyzer import generate_markdown_report, get_frame_profile

        profile = get_frame_profile(5, 5, 3)
        config = {"craft_name": "T", "firmware_revision": "INAV 9"}
        data = {"time_s": np.arange(5000) / 500.0, "sample_rate": 500.0}
        plan = {
            "scores": {"overall": 80}, "verdict": "GOOD", "verdict_text": "Good tune",
            "findings": [], "noise_fingerprint": [],
            "actions": [
                {"action": "Lower D", "param": "mc_d_roll", "current": "30",
                 "new": "25", "reason": "D-term noise"},
                {"action": "Enable RPM filter", "param": "rpm_filter_enabled",
                 "current": "OFF", "new": "ON", "reason": "Better filtering",
                 "deferred": True},
            ],
        }

        md = generate_markdown_report(plan, config, data, [None]*3, [None]*3,
                                      None, profile)
        assert "mc_d_roll" in md
        assert "Deferred" in md
        assert "rpm_filter_enabled" in md


class TestI18n:
    """Tests for localization system."""

    def test_english_default(self):
        """Test that English is the default locale."""
        from inav_toolkit.i18n import t, set_locale, get_locale
        set_locale("en")
        assert get_locale() == "en"
        assert t("verdict.dialed_in") != "verdict.dialed_in"  # not raw key
        assert "fly" in t("verdict.dialed_in").lower()

    def test_portuguese_translation(self):
        """Test pt_BR translations load and work."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("pt_BR")
        result = t("verdict.dialed_in")
        assert result != "verdict.dialed_in"
        assert "voar" in result.lower() or "perfeito" in result.lower()
        # Reset
        set_locale("en")

    def test_spanish_translation(self):
        """Test es translations load and work."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("es")
        result = t("verdict.dialed_in")
        assert result != "verdict.dialed_in"
        assert "volar" in result.lower() or "perfecto" in result.lower()
        set_locale("en")

    def test_format_substitution(self):
        """Test that {placeholders} are substituted."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("en")
        result = t("quality.too_short", duration="1.2")
        assert "1.2" in result
        assert "{duration}" not in result

    def test_format_substitution_pt_br(self):
        """Test substitution works in translated strings."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("pt_BR")
        result = t("quality.too_short", duration="3.5")
        assert "3.5" in result
        assert "{duration}" not in result
        set_locale("en")

    def test_missing_key_fallback(self):
        """Test that missing keys fall back to key itself."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("en")
        result = t("nonexistent.key.that.does.not.exist")
        assert result == "nonexistent.key.that.does.not.exist"

    def test_locale_fallback_to_english(self):
        """Test that unknown locale falls back to English."""
        from inav_toolkit.i18n import t, set_locale
        set_locale("xx_XX")  # nonexistent locale
        result = t("verdict.dialed_in")
        assert "fly" in result.lower()  # should get English
        set_locale("en")

    def test_available_locales(self):
        """Test that locale listing works."""
        from inav_toolkit.i18n import available_locales
        locales = available_locales()
        assert "en" in locales
        assert "pt_BR" in locales
        assert "es" in locales

    def test_locale_catalogs_in_sync(self):
        """All locale catalogs must have exactly the same keys as en.json.

        A missing key silently falls back to English, so drift is
        invisible at runtime — this test makes it visible.
        """
        import json
        import os
        import inav_toolkit
        locales_dir = os.path.join(os.path.dirname(inav_toolkit.__file__), "locales")
        catalogs = {}
        for fname in os.listdir(locales_dir):
            if fname.endswith(".json"):
                with open(os.path.join(locales_dir, fname), encoding="utf-8") as f:
                    catalogs[fname[:-5]] = set(k for k in json.load(f) if k != "_meta")
        assert "en" in catalogs
        en_keys = catalogs["en"]
        for loc, keys in catalogs.items():
            if loc == "en":
                continue
            missing = en_keys - keys
            extra = keys - en_keys
            assert not missing, f"{loc} missing keys: {sorted(missing)[:10]}"
            assert not extra, f"{loc} has extra keys: {sorted(extra)[:10]}"

    def test_quality_messages_translated(self):
        """Test that quality scorer messages use t() and translate."""
        from inav_toolkit.blackbox_analyzer import assess_log_quality
        from inav_toolkit.i18n import set_locale

        set_locale("pt_BR")
        n = 50
        data = {
            "time_s": np.arange(n) / 500.0,
            "gyro_roll": np.random.randn(n),
            "n_rows": n, "sample_rate": 500.0,
            "found_columns": ["gyro_roll"],
        }
        q = assess_log_quality(data)
        # Should have Portuguese messages
        has_pt = any("apenas" in i["message"].lower() or "necessário" in i["message"].lower()
                     or "análise" in i["message"].lower()
                     for i in q["issues"])
        assert has_pt, f"Expected Portuguese messages, got: {[i['message'] for i in q['issues']]}"
        set_locale("en")

    def test_markdown_report_translated(self):
        """Test markdown report uses translated section headers."""
        from inav_toolkit.blackbox_analyzer import generate_markdown_report, get_frame_profile
        from inav_toolkit.i18n import set_locale

        set_locale("pt_BR")
        profile = get_frame_profile(5, 5, 3)
        config = {"craft_name": "TestQuad", "firmware_revision": "INAV 9"}
        data = {"time_s": np.arange(5000) / 500.0, "sample_rate": 500.0}
        plan = {
            "scores": {"overall": 72}, "verdict": "OK",
            "verdict_text": "Test", "findings": [],
            "noise_fingerprint": {}, "actions": [],
        }
        md = generate_markdown_report(plan, config, data, [None]*3, [None]*3,
                                      None, profile)
        assert "Pontuações" in md or "Pontuação" in md  # Portuguese "Scores"
        assert "Analisador" in md  # Portuguese "Analyzer"
        set_locale("en")


class TestFlightTools:
    """Tests for anonymizer, range analysis, and postmortem forensics."""

    def _base_data(self, n=3000, sr=100.0):
        rng = np.random.default_rng(42)
        t = np.arange(n) / sr
        data = {
            "n_rows": n, "sample_rate": sr, "time_s": t,
            "gyro_roll": rng.normal(0, 5, n), "gyro_pitch": rng.normal(0, 5, n),
            "gyro_yaw": rng.normal(0, 5, n),
            "motor0": 1500 + rng.normal(0, 60, n), "motor1": 1500 + rng.normal(0, 60, n),
            "motor2": 1500 + rng.normal(0, 60, n), "motor3": 1500 + rng.normal(0, 60, n),
            "throttle": np.full(n, 1500.0),
            "rc_roll": 1500 + rng.normal(0, 30, n), "rc_pitch": 1500 + rng.normal(0, 30, n),
            "rc_yaw": 1500 + rng.normal(0, 30, n),
            "vbat": np.full(n, 1660.0),                 # 16.6V (4S), 0.01V units
            "amperage": np.full(n, 1000.0),             # 10A, 0.01A units
            "_slow_frames": [], "_gps_frames": [],
        }
        return data

    def _add_gps(self, data, sr, speed_ms=10.0, hz=1.0):
        """Northbound cruise at speed_ms; one fix per 1/hz seconds."""
        n = data["n_rows"]
        frames = []
        lat0, lon0 = 47.0, 8.0
        step = int(sr / hz)
        for i in range(0, n, step):
            t = i / sr
            lat = lat0 + (speed_ms * t) / 111320.0
            frames.append((i, {"GPS_coord[0]": lat * 1e7, "GPS_coord[1]": lon0 * 1e7,
                               "GPS_speed": speed_ms * 100, "GPS_altitude": 120.0,
                               "GPS_numSat": 14}))
        data["_gps_frames"] = frames
        return data

    def test_anonymize_strips_gps_and_name(self, tmp_path):
        from inav_toolkit.flight_tools import anonymize_log
        data = self._add_gps(self._base_data(), 100.0)
        out = str(tmp_path / "shared.csv")
        s = anonymize_log(data, out, craft_name="MyQuad")
        assert os.path.isfile(out)
        text = open(out).read()
        assert "GPS_coord" not in text and "470000000" not in text
        header_line = next(l for l in text.splitlines() if not l.startswith("#"))
        cols = [c.strip().lower() for c in header_line.split(",")]
        assert not any(c.startswith("gps_coord") or c in ("gps_lat", "gps_lon") for c in cols)
        assert "MyQuad" not in text
        assert "pos_north_m" in text and "gyroADC[0]" in text
        assert any("GPS" in x for x in s["stripped"])
        assert any("craft" in x for x in s["stripped"])

    def test_anonymize_roundtrip_parses(self, tmp_path):
        from inav_toolkit.flight_tools import anonymize_log
        from inav_toolkit.blackbox_analyzer import parse_csv_log
        data = self._base_data(n=1500)
        out = str(tmp_path / "rt.csv")
        anonymize_log(data, out)
        parsed = parse_csv_log(out)
        assert "gyro_roll" in parsed and parsed["n_rows"] == 1500

    def test_range_basic(self):
        from inav_toolkit.flight_tools import analyze_range
        sr = 100.0
        data = self._add_gps(self._base_data(n=6000, sr=sr), sr, speed_ms=10.0)
        r = analyze_range(data, sr, config={}, capacity_mah=5000)
        assert r is not None
        # 10A at 36 km/h → 10000mA / 36km/h ≈ 278 mAh/km
        assert 230 <= r["mah_per_km"] <= 330, r["mah_per_km"]
        assert r["projected_range_km"] and 15 <= r["projected_range_km"] <= 22
        assert r["projected_range_70_km"] < r["projected_range_km"]

    def test_range_no_gps_returns_none(self):
        from inav_toolkit.flight_tools import analyze_range
        assert analyze_range(self._base_data(), 100.0) is None

    def test_postmortem_motor_failure(self):
        from inav_toolkit.flight_tools import analyze_postmortem
        sr = 100.0
        data = self._base_data(n=3000, sr=sr)
        data["motor2"][-800:] = 1050.0          # M2 flatlines for last 8s
        data["motor0"][-800:] += 250            # others compensate
        pm = analyze_postmortem(data, sr, window_s=10)
        causes = [v["cause"] for v in pm["verdicts"]]
        assert "motor_esc_failure" in causes
        v = next(v for v in pm["verdicts"] if v["cause"] == "motor_esc_failure")
        assert "M2" in " ".join(v["evidence"])

    def test_postmortem_voltage_collapse(self):
        from inav_toolkit.flight_tools import analyze_postmortem
        sr = 100.0
        data = self._base_data(n=3000, sr=sr)
        data["vbat"][-1000:] = np.linspace(1660, 1050, 1000)   # 6.1V drop in 10s
        pm = analyze_postmortem(data, sr, window_s=10)
        assert "voltage_collapse" in [v["cause"] for v in pm["verdicts"]]

    def test_postmortem_rx_loss(self):
        from inav_toolkit.flight_tools import analyze_postmortem
        sr = 100.0
        data = self._base_data(n=3000, sr=sr)
        for k in ("rc_roll", "rc_pitch", "rc_yaw"):
            data[k][-600:] = 1500.0                            # frozen 6s
        pm = analyze_postmortem(data, sr, window_s=10)
        assert "rx_loss" in [v["cause"] for v in pm["verdicts"]]

    def test_postmortem_clean_log(self):
        from inav_toolkit.flight_tools import analyze_postmortem
        data = self._base_data()
        data["throttle"][-50:] = 1000.0                        # normal wind-down
        pm = analyze_postmortem(data, 100.0, window_s=10)
        assert pm["verdicts"] == []
        assert pm["abrupt_end"] is False

    def test_abrupt_end_detection(self):
        from inav_toolkit.flight_tools import detect_abrupt_end
        data = self._base_data()
        assert detect_abrupt_end(data, 100.0) is True          # throttle 1500 at end
        data["throttle"][-50:] = 1000.0
        assert detect_abrupt_end(data, 100.0) is False


# ═════════════════════════════════════════════════════════════════════════════
# Standalone runner (works without pytest)
# ═════════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    test_items = []
    for name, obj in sorted(globals().items()):
        if isinstance(obj, type) and name.startswith("Test"):
            for method_name in sorted(dir(obj)):
                if method_name.startswith("test_"):
                    method = getattr(obj, method_name)
                    if callable(method):
                        test_items.append((f"{name}.{method_name}", obj, method_name))

    passed = failed = skipped = 0
    print("=" * 60)
    print("  INAV Toolkit -- Test Suite")
    print("=" * 60)

    current_class = ""
    for full_name, cls, method_name in test_items:
        class_name = full_name.split(".")[0]
        if class_name != current_class:
            current_class = class_name
            print(f"\n-- {class_name} --")
        try:
            import inspect
            method = getattr(cls(), method_name)
            sig = inspect.signature(method)
            params = [p for p in sig.parameters if p != "self"]
            if params:
                skipped += 1
                print(f"  ~ {method_name} (parametrized, use pytest)")
                continue
            method()
            passed += 1
            print(f"  + {method_name}")
        except (SystemExit,):
            skipped += 1
            print(f"  ~ {method_name} (skipped)")
        except Exception as e:
            failed += 1
            print(f"  X {method_name}")
            print(f"    {e}")

    print(f"\n{'=' * 60}")
    if failed == 0:
        print(f"  {passed} PASSED, {skipped} skipped")
    else:
        print(f"  {passed} passed, {skipped} skipped, {failed} FAILED")
    print(f"{'=' * 60}")
    sys.exit(1 if failed else 0)


class TestAirborneSpan:
    """Ground time -- armed with props turning -- is not flight and swamps the
    noise and vibration metrics, so it is excluded."""

    def _log(self, sr=1000, ground_s=5, flight_s=60, land_s=4):
        n = int((ground_s + flight_s + land_s) * sr)
        alt = np.zeros(n)
        alt[int(ground_s * sr):int((ground_s + flight_s) * sr)] = 2000.0   # 20 m
        mot = np.full(n, 1100.0)
        mot[int(ground_s * sr):int((ground_s + flight_s) * sr)] = 1400.0
        return {"n_rows": n, "time_s": np.arange(n) / sr, "sample_rate": sr,
                "baro_alt": alt, "motor0": mot, "motor1": mot,
                "motor2": mot, "motor3": mot}

    def test_excludes_ground_time(self):
        from inav_toolkit.blackbox_analyzer import find_airborne_span
        sr = 1000
        span = find_airborne_span(self._log(sr=sr), sr)
        assert span is not None
        start, end = span
        assert 5.0 * sr <= start <= 7.0 * sr      # takeoff at 5 s, plus margin
        assert 63.0 * sr <= end <= 65.5 * sr      # landing at 65 s, minus margin

    def test_survives_a_baro_spike_at_sample_zero(self):
        """A single-sample spike must not mark the whole log airborne."""
        from inav_toolkit.blackbox_analyzer import find_airborne_span
        sr = 1000
        data = self._log(sr=sr)
        data["baro_alt"] = data["baro_alt"].copy()
        data["baro_alt"][0] = 5000.0
        start, _ = find_airborne_span(data, sr)
        assert start >= 4.0 * sr

    def test_falls_back_to_motors_without_baro(self):
        from inav_toolkit.blackbox_analyzer import find_airborne_span
        sr = 1000
        data = self._log(sr=sr)
        del data["baro_alt"]
        span = find_airborne_span(data, sr)
        assert span is not None and span[0] >= 4.0 * sr

    def test_returns_none_when_too_short_to_judge(self):
        from inav_toolkit.blackbox_analyzer import find_airborne_span
        sr = 1000
        assert find_airborne_span(self._log(sr=sr, flight_s=3), sr) is None

    def test_restrict_slices_only_per_sample_arrays(self):
        from inav_toolkit.blackbox_analyzer import restrict_to_span
        sr = 1000
        data = self._log(sr=sr)
        data["_slow_frames"] = [(0, {"activeFlightModeFlags": 0})]
        out = restrict_to_span(data, (1000, 3000))
        assert out["n_rows"] == 2000
        assert len(out["baro_alt"]) == 2000
        assert out["_slow_frames"] is data["_slow_frames"]   # aux frames untouched
        assert len(data["baro_alt"]) == int(69 * sr)          # original unchanged


class TestCompassWindow:
    """Compass health is measured where the FC holds heading, not across Acro."""

    SR = 1000.0

    def _log(self, n, modes, heading, **extra):
        from inav_toolkit.blackbox_analyzer import FM_ANGLE, FM_NAV_POSHOLD
        data = {
            "n_rows": n,
            "time_s": np.arange(n) / self.SR,
            "att_heading": np.asarray(heading, dtype=float),
            "att_roll": np.zeros(n),
            "att_pitch": np.zeros(n),
            "gyro_roll": np.zeros(n),
            "gyro_pitch": np.zeros(n),
            "gyro_yaw": np.zeros(n),
            "setpoint_yaw": np.zeros(n),
            "active_modes": np.asarray(modes, dtype=np.int64),
            "motor0": np.full(n, 1500.0), "motor1": np.full(n, 1500.0),
            "motor2": np.full(n, 1500.0), "motor3": np.full(n, 1500.0),
        }
        data.update(extra)
        return data

    def test_contiguous_runs_splits_on_gaps(self):
        from inav_toolkit.blackbox_analyzer import contiguous_runs
        mask = np.zeros(1000, dtype=bool)
        mask[0:300] = True
        mask[400:900] = True
        runs = contiguous_runs(mask, 100.0, 1.0)  # >= 100 samples
        assert runs == [(0, 300), (400, 900)]

    def test_contiguous_runs_drops_short_ones(self):
        from inav_toolkit.blackbox_analyzer import contiguous_runs
        mask = np.zeros(1000, dtype=bool)
        mask[10:20] = True        # too short
        mask[100:900] = True
        assert contiguous_runs(mask, 100.0, 1.0) == [(100, 900)]

    def test_acro_is_excluded_from_the_window(self):
        from inav_toolkit.blackbox_analyzer import compass_steady_mask, FM_NAV_POSHOLD
        n = 40000
        modes = np.zeros(n, dtype=np.int64)          # first half Acro (no bits)
        modes[n // 2:] = 1 << FM_NAV_POSHOLD
        mask, label = compass_steady_mask(self._log(n, modes, np.zeros(n)), self.SR)
        assert mask is not None
        assert not mask[: n // 2].any()
        assert mask[n // 2:].all()
        assert "nav hold" in label

    def test_althold_needs_hover_not_just_the_mode(self):
        """AltHold holds altitude only -- a banked turn in it is flying, not drift."""
        from inav_toolkit.blackbox_analyzer import (compass_steady_mask,
                                                    FM_NAV_ALTHOLD, FM_ANGLE)
        n = 40000
        modes = np.full(n, (1 << FM_NAV_ALTHOLD) | (1 << FM_ANGLE), dtype=np.int64)
        d = self._log(n, modes, np.zeros(n))
        d["att_roll"] = np.zeros(n)
        d["att_roll"][: n // 2] = 350.0   # 35 deg of bank, in decidegrees
        mask, _ = compass_steady_mask(d, self.SR)
        assert mask is not None
        assert not mask[: n // 2].any()
        assert mask[n // 2:].all()

    def test_commanded_yaw_is_not_jitter(self):
        from inav_toolkit.blackbox_analyzer import compass_steady_mask, FM_NAV_POSHOLD
        n = 40000
        modes = np.full(n, 1 << FM_NAV_POSHOLD, dtype=np.int64)
        d = self._log(n, modes, np.zeros(n))
        d["setpoint_yaw"][: n // 2] = 200.0
        mask, _ = compass_steady_mask(d, self.SR)
        assert mask is not None
        assert not mask[: n // 2].any()

    def test_averaging_beats_decimation_on_quantised_heading(self):
        """0.1 deg LSB differentiated over 1/50 s is 5 deg/s of pure alias."""
        from inav_toolkit.blackbox_analyzer import heading_rate_series
        n = 40000
        # A heading genuinely holding still, logged in decidegrees: the only
        # movement is the quantiser dithering between two adjacent codes.
        rng = np.random.default_rng(7)
        hdg = np.round(1000 + rng.normal(0, 0.4, n)) / 10.0
        rate, ds = heading_rate_series(hdg, [(0, n)], self.SR)
        assert ds == 20
        decimated = np.diff(np.unwrap(np.deg2rad(hdg[::ds]))) * (self.SR / ds)
        assert np.std(rate) < np.std(np.rad2deg(decimated)) / 2

    def test_no_mode_data_falls_back_to_whole_log(self):
        from inav_toolkit.blackbox_analyzer import analyze_compass_health
        n = 40000
        d = self._log(n, np.zeros(n), np.zeros(n))
        del d["active_modes"]
        r = analyze_compass_health(d, self.SR)
        assert r["heading_jitter_deg"] is not None
        assert "whole log" in r["window"]

    def test_drift_is_measured_only_while_the_gate_is_open(self):
        """Heading turned between two holds must not be charged as drift."""
        from inav_toolkit.blackbox_analyzer import analyze_compass_health, FM_NAV_POSHOLD
        n = 60000
        modes = np.zeros(n, dtype=np.int64)
        modes[:20000] = 1 << FM_NAV_POSHOLD
        modes[40000:] = 1 << FM_NAV_POSHOLD          # Acro turn in between
        hdg = np.zeros(n)
        hdg[20000:40000] = np.linspace(0, 900, 20000)  # 90 deg turn, decidegrees
        hdg[40000:] = 900.0
        r = analyze_compass_health(self._log(n, modes, hdg), self.SR)
        assert r["heading_drift_dps"] is not None
        assert abs(r["heading_drift_dps"]) < 0.01


class TestBaroSpikes:
    """A baro spike is pressure the craft's motion cannot explain."""

    SR = 1000.0

    def _log(self, alt):
        n = len(alt)
        return {
            "n_rows": n,
            "time_s": np.arange(n) / self.SR,
            "baro_alt": np.asarray(alt, dtype=float),
            "motor0": np.full(n, 1500.0), "motor1": np.full(n, 1500.0),
            "motor2": np.full(n, 1500.0), "motor3": np.full(n, 1500.0),
        }

    def _dive(self, n=60000):
        """A 10 m/s descent with a pull-out -- constant-acceleration flight."""
        t = np.arange(n) / self.SR
        return 8000.0 - 1000.0 * t + 120.0 * t ** 2

    def test_threshold_events_merges_close_crossings(self):
        from inav_toolkit.blackbox_analyzer import threshold_events
        flag = np.zeros(1000, dtype=bool)
        flag[100:110] = True
        flag[140:150] = True     # 30 ms later at 1 kHz -> same disturbance
        flag[600:610] = True
        assert threshold_events(flag, self.SR, 0.15) == [(100, 150), (600, 610)]
        assert len(threshold_events(flag, self.SR, 0.0)) == 3

    def test_quadratic_baseline_tracks_a_dive(self):
        """The old 0.5 Hz lowpass charges its own lag to the barometer."""
        from inav_toolkit.blackbox_analyzer import baro_detrend
        alt = self._dive()
        res, method = baro_detrend(alt, self.SR)
        assert method == "local quadratic"
        # Constant acceleration is fit exactly: residual is numerical noise only.
        assert np.std(res) < 1.0

    def test_dive_alone_raises_no_spikes(self):
        from inav_toolkit.blackbox_analyzer import analyze_baro_quality
        r = analyze_baro_quality(self._log(self._dive()), self.SR)
        assert r["spikes"] == 0

    def test_injected_spikes_are_all_found(self):
        from inav_toolkit.blackbox_analyzer import analyze_baro_quality
        alt = self._dive()
        rng = np.random.default_rng(11)
        idx = sorted(rng.choice(np.arange(6000, len(alt) - 6000), 8, replace=False))
        for i in idx:
            alt[i:i + 50] += 150.0      # 50 ms of 1.5 m false altitude
        r = analyze_baro_quality(self._log(alt), self.SR)
        assert r["spikes"] == 8
        assert r["worst_spike_cm"] > 100

    def test_spike_finding_names_the_threshold(self):
        from inav_toolkit.blackbox_analyzer import analyze_baro_quality
        alt = self._dive()
        for i in range(6000, 54000, 6000):
            alt[i:i + 50] += 200.0
        r = analyze_baro_quality(self._log(alt), self.SR)
        msgs = [m for lvl, m in r["findings"] if "spike" in m]
        assert msgs and "cm off the craft's own vertical motion" in msgs[0]
        assert "open-cell foam" in msgs[0]


class TestToiletBowl:
    """A toilet bowl has to actually go round."""

    SR = 1000.0

    def _path(self, kind, dur=70.0, f=0.1, r=300.0, noise=30.0, seed=1):
        rng = np.random.default_rng(seed)
        t = np.arange(int(dur * self.SR)) / self.SR
        if kind == "bowl":
            en, ee = r * np.cos(2*np.pi*f*t), r * np.sin(2*np.pi*f*t)
        elif kind == "spiral":                  # the classic expanding bowl
            g = r * (0.3 + t / t[-1])
            en, ee = g * np.cos(2*np.pi*f*t), g * np.sin(2*np.pi*f*t)
        elif kind == "slosh":                   # straight line, same frequency
            en, ee = r * np.cos(2*np.pi*f*t), 0.7 * r * np.cos(2*np.pi*f*t)
        elif kind == "drift":                   # random walk, no periodicity
            en = np.cumsum(rng.normal(0, 3, len(t)))
            ee = np.cumsum(rng.normal(0, 3, len(t)))
        return (en + rng.normal(0, noise, len(t)),
                ee + rng.normal(0, noise, len(t)))

    def _fires(self, res):
        from inav_toolkit.blackbox_analyzer import (TB_MIN_RADIUS_CM,
            TB_MIN_REVOLUTIONS, TB_MIN_CONSISTENCY)
        return (res is not None and res["radius_cm"] > TB_MIN_RADIUS_CM
                and abs(res["net_rev"]) >= TB_MIN_REVOLUTIONS
                and res["consistency"] >= TB_MIN_CONSISTENCY)

    def test_detects_a_circular_orbit(self):
        from inav_toolkit.blackbox_analyzer import orbit_test
        r = orbit_test(*self._path("bowl"), self.SR)
        assert self._fires(r)
        assert abs(r["period_s"] - 10.0) < 0.5      # 0.1 Hz
        assert r["consistency"] > 0.9

    def test_detects_an_expanding_spiral(self):
        from inav_toolkit.blackbox_analyzer import orbit_test
        assert self._fires(orbit_test(*self._path("spiral"), self.SR))

    def test_rejects_linear_sloshing(self):
        """Same frequency and amplitude, but not circular -- the old PSD test
        summed the two components and so could not tell the difference."""
        from inav_toolkit.blackbox_analyzer import orbit_test
        r = orbit_test(*self._path("slosh"), self.SR)
        assert not self._fires(r)
        assert r["consistency"] < 0.65

    def test_rejects_random_walk_drift_across_seeds(self):
        from inav_toolkit.blackbox_analyzer import orbit_test
        fired = sum(self._fires(orbit_test(*self._path("drift", seed=s), self.SR))
                    for s in range(20))
        assert fired == 0

    def test_rotation_direction_is_reported(self):
        from inav_toolkit.blackbox_analyzer import orbit_test
        ccw = orbit_test(*self._path("bowl"), self.SR)
        en, ee = self._path("bowl")
        cw = orbit_test(en, -ee, self.SR)          # mirror -> opposite sense
        assert ccw["clockwise"] is not cw["clockwise"]

    def test_idle_phase_is_not_position_hold(self):
        from inav_toolkit.blackbox_analyzer import (POSITION_HELD_NAV_IDS,
            NAV_PID_IDLE, NAV_PID_ALTHOLD_IN_PROGRESS,
            NAV_PID_POSHOLD_3D_IN_PROGRESS)
        assert NAV_PID_IDLE not in POSITION_HELD_NAV_IDS
        assert NAV_PID_ALTHOLD_IN_PROGRESS not in POSITION_HELD_NAV_IDS
        assert NAV_PID_POSHOLD_3D_IN_PROGRESS in POSITION_HELD_NAV_IDS

    def test_unrecorded_target_is_refused(self):
        """navTgtPos all-zero for the whole log means it was never recorded."""
        from inav_toolkit.blackbox_analyzer import analyze_position_hold
        n = 40000
        t = np.arange(n) / self.SR
        data = {
            "n_rows": n,
            "time_s": t,
            "nav_pos_n": 5000.0 * np.sin(2*np.pi*0.02*t),   # +-50 m of flying
            "nav_pos_e": 5000.0 * np.cos(2*np.pi*0.02*t),
            "nav_tgt_n": np.zeros(n),
            "nav_tgt_e": np.zeros(n),
        }
        r = analyze_position_hold(data, self.SR)
        assert r["stale_target"] is True
        assert r["cep_cm"] is None
        assert r["toilet_bowl"] is False

    def test_a_held_target_that_sits_still_is_still_analysed(self):
        """A stationary target is what a hold point IS. Refusing to analyse it
        would suppress the genuine case of a craft drifting off a good target."""
        from inav_toolkit.blackbox_analyzer import analyze_position_hold
        n = 40000
        t = np.arange(n) / self.SR
        en, ee = self._path("bowl", dur=n / self.SR)
        data = {
            "n_rows": n,
            "time_s": t,
            "nav_pos_n": 2000.0 + en,      # orbiting a fixed, non-zero hold point
            "nav_pos_e": -3000.0 + ee,
            "nav_tgt_n": np.full(n, 2000.0),
            "nav_tgt_e": np.full(n, -3000.0),
        }
        r = analyze_position_hold(data, self.SR)
        assert r["stale_target"] is False
        assert r["cep_cm"] is not None
        assert r["toilet_bowl"] is True     # and the orbit is still caught

    def test_single_sample_gps_jump_is_called_out(self):
        """One bad fix must not be reported as hold performance."""
        from inav_toolkit.blackbox_analyzer import analyze_position_hold
        n = 40000
        rng = np.random.default_rng(5)
        pn = 2000.0 + rng.normal(0, 30, n)
        pe = -3000.0 + rng.normal(0, 30, n)
        pn[20000] += 4200.0                      # 42 m, one sample
        data = {
            "n_rows": n, "time_s": np.arange(n) / self.SR,
            "nav_pos_n": pn, "nav_pos_e": pe,
            "nav_tgt_n": np.full(n, 2000.0), "nav_tgt_e": np.full(n, -3000.0),
        }
        r = analyze_position_hold(data, self.SR)
        assert r["max_drift_cm"] > 4000
        assert r["drift_p99_cm"] < 200            # the flight itself is tight
        assert r["position_discontinuity_cm"] > 4000
        msgs = [m for lvl, m in r["findings"] if "discontinuity" in m]
        assert msgs, r["findings"]


class TestLogIntegrity:
    """Physically impossible samples must never reach a metric."""

    SR = 1000.0

    def _clean(self, n=40000):
        t = np.arange(n) / self.SR
        rng = np.random.default_rng(3)
        return {
            "n_rows": n, "time_s": t,
            "gyro_roll": 50 * np.sin(2*np.pi*3*t) + rng.normal(0, 2, n),
            "gyro_pitch": 40 * np.cos(2*np.pi*3*t) + rng.normal(0, 2, n),
            "gyro_yaw": 20 * np.sin(2*np.pi*2*t) + rng.normal(0, 2, n),
            "nav_pos_n": 1000 + rng.normal(0, 20, n),
            "nav_pos_e": 2000 + rng.normal(0, 20, n),
            "att_heading": np.full(n, 900.0),
        }

    def test_clean_log_is_untouched(self):
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        before = d["gyro_roll"].copy()
        assert sanitize_decoded_data(d, self.SR) is None
        assert np.array_equal(d["gyro_roll"], before)

    def test_impossible_gyro_is_repaired(self):
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["gyro_yaw"][20000:20015] = -5423494.0     # the real failure, 15 samples
        rep = sanitize_decoded_data(d, self.SR)
        assert rep is not None
        assert rep["culprit_fields"]["gyro_yaw"] == 15
        assert np.abs(d["gyro_yaw"]).max() < 2500
        assert np.all(np.isfinite(d["gyro_yaw"]))    # interpolated, not NaN

    def test_repair_is_cross_field(self):
        """One bad point in the file damages several fields at once, so a field
        that stays in range at that instant is not thereby trustworthy."""
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["gyro_yaw"][20000:20015] = -5423494.0
        d["nav_pos_n"][20000] += 4200.0             # in range, but same instant
        sanitize_decoded_data(d, self.SR)
        assert abs(d["nav_pos_n"][20000] - 1000) < 200   # repaired too

    def test_spectra_stay_valid_after_repair(self):
        """compute_psd() has no NaN handling: blanking would be worse than the
        spike it replaces."""
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data, compute_psd
        d = self._clean()
        d["gyro_yaw"][20000:20015] = -5423494.0
        sanitize_decoded_data(d, self.SR)
        _, psd = compute_psd(d["gyro_yaw"], self.SR)
        assert np.all(np.isfinite(psd))

    def test_long_dropout_is_blanked_not_invented(self):
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["gyro_yaw"][10000:22000] = 9e6            # 12 s, beyond repair
        rep = sanitize_decoded_data(d, self.SR)
        assert rep["blanked_samples"] > 0
        assert np.isnan(d["gyro_yaw"][16000])

    def test_episode_is_reported_with_time_and_culprit(self):
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["gyro_yaw"][20000:20015] = -5423494.0
        rep = sanitize_decoded_data(d, self.SR)
        assert len(rep["episodes"]) == 1
        assert abs(rep["episodes"][0]["start_s"] - 19.95) < 0.1
        assert "gyro_yaw" in rep["culprit_fields"]

    def test_out_of_range_heading_and_motors_caught(self):
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["att_heading"][5000] = 65535.0
        rep = sanitize_decoded_data(d, self.SR)
        assert "att_heading" in rep["culprit_fields"]

    def test_attitude_wrap_through_inverted_is_not_corruption(self):
        """attitude[] wraps at +-1800 decidegrees and INAV emits -1801 doing it.
        Flagging that discards real loop data and invents a replacement."""
        from inav_toolkit.blackbox_analyzer import sanitize_decoded_data
        d = self._clean()
        d["att_roll"] = np.zeros(d["n_rows"])
        d["att_roll"][9998:10000] = [-1793.0, -1801.0]      # passing inverted
        d["att_roll"][10000:10002] = [1791.0, 1783.0]
        assert sanitize_decoded_data(d, self.SR) is None
        assert d["att_roll"][9999] == -1801.0                # untouched


class TestNoiseAmplitudeVeto:
    """A dB figure with no reference must not drive CRITICAL on its own."""

    def test_amplitude_recovered_from_psd(self):
        """A known sinusoid's amplitude must come back out of the dB PSD."""
        from inav_toolkit.blackbox_analyzer import compute_psd, noise_amplitude_dps
        sr, n = 1000.0, 40000
        t = np.arange(n) / sr
        amp = 10.0                                  # deg/s peak -> 7.07 RMS
        sig = amp * np.sin(2 * np.pi * 350 * t)
        freqs, psd_db = compute_psd(sig, sr)
        got = noise_amplitude_dps(freqs, psd_db, 300)
        assert abs(got - amp / np.sqrt(2)) < 1.0

    def test_quiet_peak_does_not_get_severity_language(self):
        from inav_toolkit.blackbox_analyzer import _noise_remedy
        loud = _noise_remedy("prop_harmonics", 120.0, -2.0, 3, amplitude_dps=20.0)
        quiet = _noise_remedy("prop_harmonics", 120.0, -2.0, 3, amplitude_dps=1.7)
        assert "CRITICAL" in loud
        assert "CRITICAL" not in quiet
        assert "1.7 deg/s" in quiet

    def test_severity_still_fires_when_amplitude_is_real(self):
        from inav_toolkit.blackbox_analyzer import _noise_remedy
        r = _noise_remedy("motor_imbalance", 62.0, -2.0, 3, amplitude_dps=25.0)
        assert "CRITICAL" in r

    def test_unknown_amplitude_preserves_old_behaviour(self):
        from inav_toolkit.blackbox_analyzer import _noise_remedy
        r = _noise_remedy("prop_harmonics", 120.0, -2.0, 3)
        assert "CRITICAL" in r

    def test_analyze_noise_reports_absolute_amplitudes(self):
        from inav_toolkit.blackbox_analyzer import analyze_noise
        sr, n = 1000.0, 40000
        t = np.arange(n) / sr
        d = {"gyro_roll": 6.0 * np.sin(2 * np.pi * 350 * t)}
        r = analyze_noise(d, "Roll", "gyro_roll", sr)
        for k in ("rms_low_dps", "rms_mid_dps", "rms_high_dps", "rms_gt50_dps"):
            assert k in r
        assert abs(r["rms_high_dps"] - 6.0 / np.sqrt(2)) < 1.0
        assert r["rms_low_dps"] < 1.0                # nothing down there


class TestAccelVibrationScaling:
    """accSmooth is scaled by acc_1G, and vibration is not the pilot's manoeuvres."""

    SR = 1000.0

    def _data(self, n=40000, acc_1g=2048.0, vib_g=0.0, manoeuvre_g=0.0):
        t = np.arange(n) / self.SR
        z = np.ones(n) * acc_1g                       # 1 g of gravity
        if manoeuvre_g:
            z = z + manoeuvre_g * acc_1g * np.sin(2*np.pi*0.5*t)   # loops, 0.5 Hz
        if vib_g:
            z = z + vib_g * acc_1g * np.sqrt(2) * np.sin(2*np.pi*120*t)
        return {
            # 0.0 is "no accel lowpass configured"; None would mean unknown, which
            # is a different case and has its own test.
            "n_rows": n, "time_s": t, "_acc_1g": acc_1g, "_acc_lpf_hz": 0.0,
            "acc_x": np.zeros(n), "acc_y": np.zeros(n), "acc_z": z,
        }

    def test_hovering_quad_reads_one_g(self):
        """The scaling sanity check: /981 would make a hover read 2.2 g."""
        d = self._data()
        assert abs(np.mean(d["acc_z"]) / d["_acc_1g"] - 1.0) < 0.01

    def test_acc_1g_is_read_not_assumed(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(acc_1g=512.0, vib_g=0.30)
        r = analyze_accel_vibration(d, self.SR)
        assert r["acc_1g"] == 512.0
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert abs(z["rms_vib_g"] - 0.30) < 0.05     # right answer at a different scale

    def test_manoeuvres_are_not_vibration(self):
        """0.3 g of 0.5 Hz flying must not be reported as vibration."""
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(manoeuvre_g=0.30)
        r = analyze_accel_vibration(d, self.SR)
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert z["rms_broadband_g"] > 0.15           # the flying is in there
        assert z["rms_vib_g"] < 0.02                 # but not called vibration
        assert not any("vibration" in f["text"].lower()
                       for f in z["findings"] if f["level"] == "WARNING")

    def test_real_vibration_is_still_caught(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.70)
        r = analyze_accel_vibration(d, self.SR)
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert z["rms_vib_g"] > 0.5
        assert any(f["level"] == "WARNING" and "High vibration" in f["text"]
                   for f in z["findings"])

    def test_findings_name_the_band(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.70)
        r = analyze_accel_vibration(d, self.SR)
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        txt = [f["text"] for f in z["findings"]
               if f.get("source") in ("rms_high", "rms_moderate")][0]
        assert "above 5Hz" in txt

    def test_fc_vibration_field_is_used_when_present(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data()
        d["acc_vib"] = np.full(d["n_rows"], 0.25 * 2048.0)
        r = analyze_accel_vibration(d, self.SR)
        assert abs(r["fc_vib_mean_g"] - 0.25) < 0.01

    def test_absent_acc_lpf_is_unknown_not_zero(self):
        """A truncated header omits acc_lpf_hz. Treating absent as 0 claims full
        bandwidth for data that may have been lowpassed at 15 Hz."""
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.70)
        d["_acc_lpf_hz"] = None
        r = analyze_accel_vibration(d, self.SR)
        assert r["acc_lpf_unknown"] is True
        assert r["band_limited"] is True
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert not any(f.get("source") in ("rms_high", "rms_moderate")
                       for f in z["findings"])
        assert any("unknown" in f["text"] for f in r["findings"])

    def test_band_limited_accel_does_not_produce_a_verdict(self):
        """accSmooth is logged after acc_lpf_hz. At 15Hz it has no content at prop
        frequencies, so a figure from it measures the filter, not the airframe."""
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.70)
        d["_acc_lpf_hz"] = 15.0
        r = analyze_accel_vibration(d, self.SR)
        assert r["band_limited"] is True
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert not any(f.get("source") in ("rms_high", "rms_moderate")
                       for f in z["findings"])

    def test_wide_band_accel_still_produces_a_verdict(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.70)
        d["_acc_lpf_hz"] = 0.0          # no accel lowpass configured
        r = analyze_accel_vibration(d, self.SR)
        assert r["band_limited"] is False
        z = [a for a in r["axes"] if a["axis"] == "Z"][0]
        assert any(f.get("source") == "rms_high" for f in z["findings"])

    def test_fc_vib_drives_the_verdict_when_present(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data()
        d["_acc_lpf_hz"] = 15.0
        d["acc_vib"] = np.full(d["n_rows"], 2.0 * 2048.0)     # 2 g, genuinely bad
        r = analyze_accel_vibration(d, self.SR)
        assert any(f.get("source") == "fc_vib" and f["level"] == "WARNING"
                   for f in r["findings"])
        assert r["score"] < 100

    def test_quiet_fc_vib_raises_nothing(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data()
        d["_acc_lpf_hz"] = 15.0
        d["acc_vib"] = np.full(d["n_rows"], 0.2 * 2048.0)
        r = analyze_accel_vibration(d, self.SR)
        assert not any(f.get("source") == "fc_vib" for f in r["findings"])

    def test_band_limited_without_accvib_says_so(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        d = self._data(vib_g=0.7)
        d["_acc_lpf_hz"] = 15.0
        r = analyze_accel_vibration(d, self.SR)
        assert any(f.get("source") == "vib_unavailable" for f in r["findings"])

    def test_asymmetry_needs_an_absolute_floor(self):
        """A 3x ratio between 0.075g and 0.024g is noise over noise."""
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        n = 40000
        t = np.arange(n) / self.SR
        d = {"n_rows": n, "time_s": t, "_acc_1g": 2048.0, "_acc_lpf_hz": 0.0,
             "acc_x": 0.075 * 2048 * np.sqrt(2) * np.sin(2*np.pi*120*t),
             "acc_y": 0.024 * 2048 * np.sqrt(2) * np.sin(2*np.pi*120*t),
             "acc_z": np.ones(n) * 2048.0}
        r = analyze_accel_vibration(d, self.SR)
        assert not any("higher than the other" in f["text"] for f in r["findings"])

    def test_asymmetry_still_reported_when_real(self):
        from inav_toolkit.blackbox_analyzer import analyze_accel_vibration
        n = 40000
        t = np.arange(n) / self.SR
        d = {"n_rows": n, "time_s": t, "_acc_1g": 2048.0, "_acc_lpf_hz": 0.0,
             "acc_x": 0.60 * 2048 * np.sqrt(2) * np.sin(2*np.pi*120*t),
             "acc_y": 0.10 * 2048 * np.sqrt(2) * np.sin(2*np.pi*120*t),
             "acc_z": np.ones(n) * 2048.0}
        r = analyze_accel_vibration(d, self.SR)
        assert any("higher than the other" in f["text"] for f in r["findings"])


NAV_IDLE = 1
NAV_POSHOLD = 7


class TestPosHoldSegments:
    """A hold is only as good as its poorest segment."""

    SR = 1000.0

    def _log(self, ceps_cm, seg_s=40.0, gap_s=20.0):
        """Build a log with one held segment per requested CEP."""
        segs, held, pos_n, pos_e, tgt_n, tgt_e, states = [], [], [], [], [], [], []
        rng = np.random.default_rng(4)
        idx = 0
        for cep in ceps_cm:
            g = int(gap_s * self.SR)
            pos_n.append(np.full(g, 1000.0)); pos_e.append(np.full(g, 2000.0))
            tgt_n.append(np.zeros(g)); tgt_e.append(np.zeros(g))
            states.append(np.full(g, NAV_IDLE))
            idx += g
            n = int(seg_s * self.SR)
            sigma = cep / 1.1774        # CEP50 of a 2-D Gaussian
            pos_n.append(1000.0 + rng.normal(0, sigma, n))
            pos_e.append(2000.0 + rng.normal(0, sigma, n))
            tgt_n.append(np.full(n, 1000.0)); tgt_e.append(np.full(n, 2000.0))
            states.append(np.full(n, NAV_POSHOLD))
            held.append((idx, idx + n, NAV_POSHOLD))
            idx += n
        cat = lambda xs: np.concatenate(xs)
        n_tot = idx
        return {
            "n_rows": n_tot, "time_s": np.arange(n_tot) / self.SR,
            "nav_pos_n": cat(pos_n), "nav_pos_e": cat(pos_e),
            "nav_tgt_n": cat(tgt_n), "nav_tgt_e": cat(tgt_e),
        }, held

    def test_headline_is_the_worst_segment_not_the_longest(self):
        from inav_toolkit.blackbox_analyzer import analyze_position_hold_segments
        d, held = self._log([30.0, 180.0])
        r = analyze_position_hold_segments(d, self.SR, held)
        assert r["worst_cep_cm"] > 100
        assert r["best_cep_cm"] < 60
        assert r["cep_cm"] == r["worst_cep_cm"]

    def test_every_segment_is_reported(self):
        from inav_toolkit.blackbox_analyzer import analyze_position_hold_segments
        d, held = self._log([30.0, 100.0, 180.0])
        r = analyze_position_hold_segments(d, self.SR, held)
        assert r["segments"] == 3
        assert len(r["segments_detail"]) == 3
        assert all(s["cep_cm"] is not None for s in r["segments_detail"])
        msg = [m for lvl, m in r["findings"] if "segments" in m][0]
        assert "worst" in msg and "best" in msg

    def test_large_spread_is_flagged(self):
        from inav_toolkit.blackbox_analyzer import analyze_position_hold_segments
        d, held = self._log([30.0, 180.0])
        r = analyze_position_hold_segments(d, self.SR, held)
        assert any("varies" in m for lvl, m in r["findings"])

    def test_consistent_segments_are_not_flagged(self):
        from inav_toolkit.blackbox_analyzer import analyze_position_hold_segments
        d, held = self._log([40.0, 45.0])
        r = analyze_position_hold_segments(d, self.SR, held)
        assert not any("varies" in m for lvl, m in r["findings"])

    def test_single_segment_still_reports_provenance(self):
        from inav_toolkit.blackbox_analyzer import analyze_position_hold_segments
        d, held = self._log([40.0])
        r = analyze_position_hold_segments(d, self.SR, held)
        assert r["segments"] == 1
        assert any("1 held segment" in m for lvl, m in r["findings"])


class TestFrameCadenceArtifact:
    """An I-frame-cadence artifact must not be diagnosed as a mechanical fault."""

    SR = 1000.0
    PERIOD = 16

    def _log(self, n=64000, cadence_pp=2.0, same_shape=True, real_peak_hz=None,
             real_amp=3.0, seed=2):
        rng = np.random.default_rng(seed)
        t = np.arange(n) / self.SR
        # one deterministic sawtooth per I-frame period
        saw = np.zeros(self.PERIOD)
        saw[11] = cadence_pp * 0.7
        saw[3:10] = -cadence_pp * 0.3
        tile = np.tile(saw, n // self.PERIOD + 1)[:n]
        d = {"n_rows": n, "time_s": t,
             "_decoder_stats": {"i_frames": n // self.PERIOD,
                                "p_frames": n - n // self.PERIOD}}
        for i, axis in enumerate(("roll", "pitch", "yaw")):
            base = rng.normal(0, 2.0, n)
            art = tile if same_shape else np.roll(tile, 5 * i) * (1.0 + i)
            sig = base + art
            if real_peak_hz:
                sig = sig + real_amp * np.sin(2 * np.pi * real_peak_hz * t)
            d[f"gyro_raw_{axis}"] = sig
            d[f"gyro_{axis}"] = sig
        return d

    def test_cadence_is_derived_from_frame_counts(self):
        from inav_toolkit.blackbox_analyzer import frame_cadence_hz
        d = self._log()
        assert abs(frame_cadence_hz(d, self.SR) - self.SR / self.PERIOD) < 1.0

    def test_cadence_is_not_hardcoded(self):
        """A different I-frame interval must give a different cadence."""
        from inav_toolkit.blackbox_analyzer import frame_cadence_hz
        d = self._log()
        d["_decoder_stats"] = {"i_frames": 1000, "p_frames": 31000}   # every 32
        assert abs(frame_cadence_hz(d, self.SR) - self.SR / 32) < 1.0

    def test_identical_waveform_across_axes_is_confirmed(self):
        from inav_toolkit.blackbox_analyzer import detect_frame_cadence_artifact
        r = detect_frame_cadence_artifact(self._log(same_shape=True), self.SR)
        assert r is not None and r["confirmed"] is True
        assert r["cross_axis_corr"] > 0.8
        assert max(r["amplitude_dps"].values()) > 0.5

    def test_axis_asymmetric_content_is_not_confirmed(self):
        """A real mechanical source excites axes differently -- must NOT be
        suppressed just because it sits near the cadence."""
        from inav_toolkit.blackbox_analyzer import detect_frame_cadence_artifact
        r = detect_frame_cadence_artifact(self._log(same_shape=False), self.SR)
        assert r is None or r["confirmed"] is False

    def test_harmonics_are_recognised(self):
        from inav_toolkit.blackbox_analyzer import is_frame_cadence_peak
        for f in (62.5, 125.0, 187.5, 312.5):
            assert is_frame_cadence_peak(f, 62.5)
        for f in (40.0, 95.0, 220.0):
            assert not is_frame_cadence_peak(f, 62.5)

    def test_cadence_peak_is_tagged_not_called_mechanical(self):
        from inav_toolkit.blackbox_analyzer import _noise_remedy
        r = _noise_remedy("frame_cadence", 62.5, -2.0, 3, amplitude_dps=20.0)
        assert "CRITICAL" not in r
        assert "decoding artifact" in r

    def test_no_decoder_stats_means_no_detection(self):
        from inav_toolkit.blackbox_analyzer import detect_frame_cadence_artifact
        d = self._log()
        del d["_decoder_stats"]
        assert detect_frame_cadence_artifact(d, self.SR) is None

    def test_cadence_is_refined_to_a_whole_frame_period(self):
        """A raw ratio of 16.13 gives 62.0 Hz, whose 6th harmonic misses a real
        375 Hz peak by 3 Hz. The period is an integer, so sr/period is exact."""
        from inav_toolkit.blackbox_analyzer import (detect_frame_cadence_artifact,
                                                    is_frame_cadence_peak)
        d = self._log()
        # frame counts that give a non-integer ratio, as a real log does
        d["_decoder_stats"] = {"i_frames": 25876, "p_frames": 391396}
        r = detect_frame_cadence_artifact(d, self.SR)
        assert r is not None
        assert abs(r["cadence_hz"] - 62.5) < 0.01
        for f in (62.5, 125.0, 187.5, 250.0, 312.5, 375.0, 437.5):
            assert is_frame_cadence_peak(f, r["cadence_hz"]), f

    def test_subtraction_removes_the_artifact_not_real_vibration(self):
        """Only content locked to the I-frame phase may be removed."""
        from inav_toolkit.blackbox_analyzer import (detect_frame_cadence_artifact,
                                                    remove_cadence_artifact)
        n = 64000
        t = np.arange(n) / self.SR
        real_hz = 97.0                       # off-cadence, must survive
        d = self._log(n=n, real_peak_hz=real_hz, real_amp=4.0)
        before = {k: d[k].copy() for k in d if k.startswith("gyro_raw_")}
        cad = detect_frame_cadence_artifact(d, self.SR)
        assert cad and cad["confirmed"]
        assert remove_cadence_artifact(d, self.SR, cad) > 0

        def amp_at(sig, hz):
            w = np.hanning(len(sig))
            sp = np.abs(np.fft.rfft((sig - sig.mean()) * w))
            fr = np.fft.rfftfreq(len(sig), 1 / self.SR)
            return sp[np.argmin(np.abs(fr - hz))]

        for k in before:
            # the cadence line is reduced hard ...
            b = amp_at(before[k], cad["cadence_hz"])
            a = amp_at(d[k], cad["cadence_hz"])
            assert a < b * 0.5, (k, b, a)
            # ... while the genuine 97 Hz peak is essentially untouched
            rb = amp_at(before[k], real_hz)
            ra = amp_at(d[k], real_hz)
            assert ra > rb * 0.9, (k, rb, ra)

    def test_subtraction_is_a_noop_when_unconfirmed(self):
        from inav_toolkit.blackbox_analyzer import remove_cadence_artifact
        d = self._log()
        before = d["gyro_raw_roll"].copy()
        assert remove_cadence_artifact(d, self.SR, {"confirmed": False}) == 0
        assert np.array_equal(d["gyro_raw_roll"], before)


class TestNoisePeakFloor:
    """0 Hz is not a vibration frequency."""

    SR = 1000.0

    def _psd(self, hz_list, dc=True):
        from inav_toolkit.blackbox_analyzer import compute_psd
        n = 40000
        t = np.arange(n) / self.SR
        sig = np.zeros(n)
        if dc:
            sig += 50.0                       # DC offset
            sig += 30.0 * np.sin(2 * np.pi * 0.7 * t)   # slow pilot input
        for hz in hz_list:
            sig += 8.0 * np.sin(2 * np.pi * hz * t)
        return compute_psd(sig, self.SR)

    def test_dc_and_pilot_input_are_not_peaks(self):
        from inav_toolkit.blackbox_analyzer import find_noise_peaks
        freqs, psd = self._psd([])
        peaks = find_noise_peaks(freqs, psd)
        assert all(p["freq_hz"] >= 5.0 for p in peaks), [p["freq_hz"] for p in peaks]

    def test_real_peaks_still_found(self):
        from inav_toolkit.blackbox_analyzer import find_noise_peaks
        freqs, psd = self._psd([120.0])
        peaks = find_noise_peaks(freqs, psd)
        assert any(abs(p["freq_hz"] - 120.0) < 3 for p in peaks), [p["freq_hz"] for p in peaks]

    def test_propwash_band_is_not_suppressed(self):
        """Propwash is real and lives at 10-40 Hz, above the floor."""
        from inav_toolkit.blackbox_analyzer import find_noise_peaks
        freqs, psd = self._psd([22.0])
        peaks = find_noise_peaks(freqs, psd)
        assert any(abs(p["freq_hz"] - 22.0) < 3 for p in peaks), [p["freq_hz"] for p in peaks]

    def test_info_items_use_the_schema_the_report_prints(self):
        """print_terminal_report reads item['text']; a 'title' key crashed every
        short flight with KeyError and produced no report at all."""
        import inspect
        from inav_toolkit import blackbox_analyzer as B
        src = inspect.getsource(B)
        i = src.index("Short flight (")
        block = src[max(0, i - 300):i + 200]
        assert '"text": f"Short flight' in block, block[-260:]

    def test_recipe_needs_loud_harmonics_not_merely_present(self):
        """has_prop_harmonics is presence, not magnitude, and the KV-derived bands
        span 233-2331 Hz so nearly any high peak lands inside one. A quiet craft
        must not be handed an aggressive filter stack."""
        from inav_toolkit.blackbox_analyzer import (generate_tuning_recipe,
                                                    get_frame_profile,
                                                    NOISE_AMPLITUDE_OK_DPS)
        prof = get_frame_profile(7)
        fp = {"peaks": [{"freq_hz": 300.0, "power_db": -25.0,
                         "source": "prop_harmonics", "axes": ["Roll"],
                         "n_axes": 1, "prominence": 8.0}],
              "dominant_source": "prop_harmonics", "summary": ""}
        cfg = {"_n_motors": 4, "gyro_main_lpf_hz": 90}

        def mk(dps):
            return [{"axis": a, "rms_high": -19.0, "rms_high_dps": dps,
                     "rms_low": -15.0, "rms_mid": -18.0, "peaks": [],
                     "freqs": np.array([0.0]), "psd_db": np.array([-60.0]),
                     "noise_start_freq": 500.0}
                    for a in ("Roll", "Pitch", "Yaw")]

        quiet = generate_tuning_recipe(mk(NOISE_AMPLITUDE_OK_DPS - 1.0), fp, cfg, prof)
        loud = generate_tuning_recipe(mk(NOISE_AMPLITUDE_OK_DPS + 10.0), fp, cfg, prof)
        assert quiet["recipe_name"] != "Harmonic Defense", quiet["recipe_name"]
        assert loud["recipe_name"] == "Harmonic Defense", loud["recipe_name"]


class TestNoiseScoreCalibration:
    """The noise score must track amplitude a pilot can reason about."""

    def _score(self, dps):
        from inav_toolkit.blackbox_analyzer import (NOISE_SCORE_GOOD_DPS,
                                                    NOISE_SCORE_BAD_DPS)
        import numpy as _np
        return float(_np.clip((dps - NOISE_SCORE_BAD_DPS)
                              / (NOISE_SCORE_GOOD_DPS - NOISE_SCORE_BAD_DPS) * 100, 0, 100))

    def test_clean_craft_scores_well(self):
        """2.87 deg/s scored 0/100 on the old dB scale."""
        assert self._score(2.87) > 70
        assert self._score(0.81) > 90

    def test_genuinely_noisy_craft_scores_badly(self):
        from inav_toolkit.blackbox_analyzer import NOISE_AMPLITUDE_BAD_DPS
        assert self._score(NOISE_AMPLITUDE_BAD_DPS) == 0.0
        assert self._score(20.0) == 0.0

    def test_monotonic_in_amplitude(self):
        vals = [self._score(d) for d in (0.5, 1.0, 2.0, 4.0, 8.0, 12.0)]
        assert vals == sorted(vals, reverse=True), vals

    def test_falls_back_when_amplitude_missing(self):
        """Pre-2.23.9 results carry no rms_high_dps."""
        import inspect
        from inav_toolkit import blackbox_analyzer as B
        src = inspect.getsource(B)
        i = src.index("dps = nr.get(\"rms_high_dps\")")
        assert "else:" in src[i:i + 700] and "rms_high" in src[i:i + 700]

    def test_rpm_filter_not_recommended_on_a_quiet_craft(self):
        """Its only condition used to be "the filter is off", so it fired on every
        log -- including one at 96/100 noise whose dominant source was propwash,
        which an RPM filter cannot touch, on a craft that had already flown the
        experiment and measured ~0 dB benefit."""
        from inav_toolkit.blackbox_analyzer import (generate_action_plan,
                                                    get_frame_profile,
                                                    NOISE_AMPLITUDE_OK_DPS)
        prof = get_frame_profile(7)

        def plan_for(dps, source):
            nr = [{"axis": a, "rms_high": -25.0, "rms_high_dps": dps,
                   "rms_low": -20.0, "rms_mid": -22.0,
                   "peaks": [{"freq_hz": 300.0, "power_db": -15.0, "prominence": 9.0}],
                   "freqs": np.array([0.0, 300.0]), "psd_db": np.array([-60.0, -15.0]),
                   "noise_start_freq": 300.0} for a in ("Roll", "Pitch", "Yaw")]
            fp = {"peaks": [{"freq_hz": 300.0, "power_db": -15.0, "source": source,
                             "axes": ["Roll"], "n_axes": 1, "prominence": 9.0}],
                  "dominant_source": source, "summary": ""}
            data = {"time_s": np.arange(300000) / 1000.0, "sample_rate": 1000.0}
            cfg = {"_n_motors": 4, "rpm_filter_enabled": "OFF",
                   "dyn_notch_enabled": "ON", "dyn_notch_min_hz": 60,
                   "gyro_main_lpf_hz": 90}
            return generate_action_plan(nr, [None]*3, None, None, cfg, data,
                                        prof, noise_fp=fp)

        def has_rpm(plan):
            return any("rpm_gyro_filter_enabled" in str(a.get("action", ""))
                       for a in plan["actions"])

        # quiet craft, rotational source -> no recommendation
        assert not has_rpm(plan_for(NOISE_AMPLITUDE_OK_DPS - 1.0, "prop_harmonics"))
        # loud but aerodynamic -> RPM filter cannot help, so no recommendation
        assert not has_rpm(plan_for(NOISE_AMPLITUDE_OK_DPS + 10.0, "propwash"))
        # loud and rotational -> recommend it
        assert has_rpm(plan_for(NOISE_AMPLITUDE_OK_DPS + 10.0, "prop_harmonics"))
