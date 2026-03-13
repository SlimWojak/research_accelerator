"""
Phase 2 Data Pre-Processing Pipeline — v2 (Native Multi-TF)
=============================================================
Reads EURUSD 1m CSV, aggregates to 5m/15m, then runs ALL detection algorithms
NATIVELY on each timeframe's bar arrays independently.

Key changes from v1:
  - FVG, swing, displacement, OB detection runs on 1m, 5m, AND 15m bars
  - A "genuine 5m FVG" means the gap exists across 3 consecutive 5m candles
  - ALL timestamps exported in NY time (UTC-5 for Jan 2024 = EST, no DST)
  - Session boundary timestamps exported for chart markers
"""

import json
import csv
from datetime import datetime, timedelta, timezone
from collections import defaultdict
import math
import os

# ─── Config ───────────────────────────────────────────────────
# Paths relative to repo root (run from pipeline/ directory)
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(SCRIPT_DIR)
CSV_PATH = os.path.join(REPO_ROOT, "data", "eurusd_1m_2024-01-07_to_2024-01-12.csv")
OUTPUT_DIR = os.path.join(REPO_ROOT, "site")

# Timezone: NY = UTC-5 in January (EST, no DST)
NY_OFFSET = timedelta(hours=-5)
NY_TZ = timezone(NY_OFFSET)

# Forex day boundary: 17:00 NY
FOREX_DAY_HOUR_NY = 17

# Session times in NY
# Asia: 19:00-00:00 NY
# LOKZ: 02:00-05:00 NY
# NYOKZ: 07:00-10:00 NY
SESSIONS_NY = {
    'asia':  (19, 24),  # 19:00-00:00 (24 = midnight)
    'lokz':  (2, 5),    # 02:00-05:00
    'nyokz': (7, 10),   # 07:00-10:00
}

# NY reversal windows (NY time)
NY_WINDOW_A_NY = (8, 9)    # 08:00-09:00 NY
NY_WINDOW_B_NY = (10, 11)  # 10:00-11:00 NY

PIP = 0.0001

# Sweep values from the brief
FVG_THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0]  # pips (for 1m)
FVG_THRESHOLDS_5M = [1.0, 2.0, 3.0, 4.0, 5.0, 7.0, 10.0]  # pips (for 5m — bigger gaps expected)
FVG_THRESHOLDS_15M = [2.0, 3.0, 5.0, 7.0, 10.0, 15.0]  # pips (for 15m)

SWING_HEIGHT_THRESHOLDS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 4.0]  # pips (for 1m)
SWING_HEIGHT_THRESHOLDS_5M = [2.0, 3.0, 5.0, 7.0, 10.0, 15.0]  # pips (for 5m)
SWING_HEIGHT_THRESHOLDS_15M = [3.0, 5.0, 7.0, 10.0, 15.0, 20.0]  # pips (for 15m)
SWING_HEIGHT_THRESHOLDS_1H = [5.0, 7.0, 10.0, 15.0, 20.0, 30.0]  # pips (for 1H)
SWING_HEIGHT_THRESHOLDS_4H = [10.0, 15.0, 20.0, 30.0, 50.0, 70.0]  # pips (for 4H)
SWING_HEIGHT_THRESHOLDS_1D = [20.0, 30.0, 50.0, 70.0, 100.0, 150.0]  # pips (for 1D)

EQUAL_HL_TOLERANCES = [0.5, 1.0, 1.5, 2.0, 2.5]  # pips (1m)
EQUAL_HL_TOLERANCES_5M = [1.0, 2.0, 3.0, 4.0, 5.0]  # pips (5m)
EQUAL_HL_TOLERANCES_15M = [2.0, 3.0, 5.0, 7.0, 10.0]  # pips (15m)
EQUAL_HL_TOLERANCES_1H = [3.0, 5.0, 7.0, 10.0, 15.0]  # pips (1H)
EQUAL_HL_TOLERANCES_4H = [5.0, 10.0, 15.0, 20.0, 30.0]  # pips (4H)
EQUAL_HL_TOLERANCES_1D = [10.0, 20.0, 30.0, 50.0, 70.0]  # pips (1D)

FVG_THRESHOLDS_1H = [3.0, 5.0, 7.0, 10.0, 15.0, 20.0]  # pips (for 1H)
FVG_THRESHOLDS_4H = [5.0, 10.0, 15.0, 20.0, 30.0, 50.0]  # pips (for 4H)
FVG_THRESHOLDS_1D = [10.0, 20.0, 30.0, 50.0, 70.0, 100.0]  # pips (for 1D)

ASIA_THRESHOLDS = [12, 15, 18, 20, 25, 30]  # pips (session-level, TF-independent)

DISP_ATR_MULTS = [1.0, 1.25, 1.5, 2.0]
DISP_BODY_RATIOS = [0.55, 0.60, 0.65, 0.70]

DISP_TF_DEFAULTS = {
    '1m':  {'atr': 1.50, 'body': 0.60, 'close_str': 0.25},
    '5m':  {'atr': 1.50, 'body': 0.60, 'close_str': 0.25},
    '15m': {'atr': 1.50, 'body': 0.60, 'close_str': 0.25},
    'H1':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
    'H4':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
    'D1':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
    # Aliases using TF_CONFIG keys
    '1H':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
    '4H':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
    '1D':  {'atr': 1.50, 'body': 0.65, 'close_str': 0.25},
}

CLUSTER2_NET_EFF_MIN = 0.65
CLUSTER2_OVERLAP_MAX = 0.35

DECISIVE_OVERRIDE = {
    'body_min': 0.75,
    'close_max': 0.10,
    'pip_floor': {
        '1m': 3.0, '5m': 5.0, '15m': 6.0,
        'H1': 8.0, 'H4': 15.0, 'D1': 20.0,
        '1H': 8.0, '4H': 15.0, '1D': 20.0,
    },
}
OB_STALENESS_BARS = [5, 10, 15, 20, 30]

SWING_N_DEFAULT = 5
SWING_STRENGTH_CAP = 20

TF_CONFIG = {
    '1m':  {'minutes': 1,  'swing_n': 5, 'fvg_thresh': FVG_THRESHOLDS,      'swing_height_thresh': SWING_HEIGHT_THRESHOLDS,      'equal_tol': EQUAL_HL_TOLERANCES},
    '5m':  {'minutes': 5,  'swing_n': 3, 'fvg_thresh': FVG_THRESHOLDS_5M,   'swing_height_thresh': SWING_HEIGHT_THRESHOLDS_5M,   'equal_tol': EQUAL_HL_TOLERANCES_5M},
    '15m': {'minutes': 15, 'swing_n': 2, 'fvg_thresh': FVG_THRESHOLDS_15M,  'swing_height_thresh': SWING_HEIGHT_THRESHOLDS_15M,  'equal_tol': EQUAL_HL_TOLERANCES_15M},
    '1H':  {'minutes': 60,  'swing_n': 2, 'fvg_thresh': FVG_THRESHOLDS_1H,  'swing_height_thresh': SWING_HEIGHT_THRESHOLDS_1H,  'equal_tol': EQUAL_HL_TOLERANCES_1H},
    '4H':  {'minutes': 240, 'swing_n': 2, 'fvg_thresh': FVG_THRESHOLDS_4H,  'swing_height_thresh': SWING_HEIGHT_THRESHOLDS_4H,  'equal_tol': EQUAL_HL_TOLERANCES_4H},
    '1D':  {'minutes': 1440, 'swing_n': 2, 'fvg_thresh': FVG_THRESHOLDS_1D, 'swing_height_thresh': SWING_HEIGHT_THRESHOLDS_1D, 'equal_tol': EQUAL_HL_TOLERANCES_1D},
    # NOTE: W1 skipped — 5-day data windows are too small for weekly aggregation
}


# ─── Utility: UTC datetime → NY time string ─────────────────
def utc_to_ny_str(dt_utc):
    """Convert a UTC datetime to NY time ISO string."""
    dt_ny = dt_utc + NY_OFFSET
    return dt_ny.strftime('%Y-%m-%dT%H:%M:%S')

def utc_to_ny_dt(dt_utc):
    """Convert a UTC datetime to NY datetime (naive, for calculations)."""
    return dt_utc + NY_OFFSET


# ─── Load Data ────────────────────────────────────────────────
def load_csv(path):
    """Load 1m OHLC CSV, return list of bar dicts with both UTC and NY datetimes."""
    bars = []
    with open(path, 'r') as f:
        reader = csv.DictReader(f)
        for row in reader:
            ts = row.get('timestamp') or row.get('time') or row.get('datetime') or row.get('date')
            bar = {
                'time_utc': ts,
                'open': float(row['open']),
                'high': float(row['high']),
                'low': float(row['low']),
                'close': float(row['close']),
            }
            # Parse timestamp (UTC)
            for fmt in ['%Y-%m-%d %H:%M:%S', '%Y-%m-%dT%H:%M:%S', '%Y-%m-%d %H:%M',
                        '%Y-%m-%dT%H:%M:%SZ', '%Y-%m-%dT%H:%M:%S+00:00']:
                try:
                    bar['dt_utc'] = datetime.strptime(ts, fmt)
                    break
                except (ValueError, TypeError):
                    continue
            if 'dt_utc' not in bar:
                raise ValueError(f"Cannot parse timestamp: {ts}")
            
            # Compute NY time
            bar['dt_ny'] = utc_to_ny_dt(bar['dt_utc'])
            bar['time'] = utc_to_ny_str(bar['dt_utc'])  # This is the primary timestamp now
            bars.append(bar)
    bars.sort(key=lambda b: b['dt_utc'])
    return bars


# ─── Forex Day Assignment (based on NY time) ─────────────────
def assign_forex_day(bars):
    """Assign each bar to a forex trading day (17:00 NY boundary)."""
    for bar in bars:
        dt_ny = bar['dt_ny']
        if dt_ny.hour >= FOREX_DAY_HOUR_NY:
            # After 17:00 NY = belongs to NEXT calendar day's forex day
            forex_date = (dt_ny + timedelta(days=1)).strftime('%Y-%m-%d')
        else:
            forex_date = dt_ny.strftime('%Y-%m-%d')
        bar['forex_day'] = forex_date
    return bars


# ─── Session Assignment (based on NY time) ────────────────────
def assign_session(bars):
    """Assign session label to each bar based on NY time."""
    for bar in bars:
        h = bar['dt_ny'].hour
        session = 'other'
        for name, (start, end) in SESSIONS_NY.items():
            if name == 'asia':
                # Asia: 19:00-00:00 NY (hour 19,20,21,22,23)
                if h >= 19:
                    session = 'asia'
                    break
            else:
                if start <= h < end:
                    session = name
                    break
        bar['session'] = session
        
        # NY reversal windows
        bar['ny_window_a'] = NY_WINDOW_A_NY[0] <= h < NY_WINDOW_A_NY[1]
        bar['ny_window_b'] = NY_WINDOW_B_NY[0] <= h < NY_WINDOW_B_NY[1]
    return bars


# ─── Timeframe Aggregation ────────────────────────────────────
def aggregate_bars(bars, period_minutes):
    """Aggregate 1m bars to Nm candles. Groups by floor(minute / period) in NY time."""
    if period_minutes == 1:
        return bars
    
    groups = defaultdict(list)
    for bar in bars:
        dt_ny = bar['dt_ny']
        # Floor to period boundary using NY time
        total_min = dt_ny.hour * 60 + dt_ny.minute
        group_min = (total_min // period_minutes) * period_minutes
        # Construct group key from NY date + floored time
        group_h = group_min // 60
        group_m = group_min % 60
        key = dt_ny.strftime('%Y-%m-%d') + f'T{group_h:02d}:{group_m:02d}:00'
        groups[key].append(bar)
    
    agg_bars = []
    for key in sorted(groups.keys()):
        group = groups[key]
        # Parse the NY group key back into a datetime for calculations
        dt_ny = datetime.strptime(key, '%Y-%m-%dT%H:%M:%S')
        dt_utc = dt_ny - NY_OFFSET  # reverse for UTC
        
        agg = {
            'time': key,  # NY time string
            'time_utc': dt_utc.strftime('%Y-%m-%dT%H:%M:%S'),
            'dt_utc': dt_utc,
            'dt_ny': dt_ny,
            'open': group[0]['open'],
            'high': max(b['high'] for b in group),
            'low': min(b['low'] for b in group),
            'close': group[-1]['close'],
            'forex_day': group[0]['forex_day'],
            'session': group[0]['session'],
            'ny_window_a': any(b.get('ny_window_a', False) for b in group),
            'ny_window_b': any(b.get('ny_window_b', False) for b in group),
            'bar_count': len(group),
        }
        agg_bars.append(agg)
    
    return agg_bars


def aggregate_bars_daily(bars):
    """Aggregate 1m bars to daily (forex day) bars. Groups by forex_day."""
    groups = defaultdict(list)
    for bar in bars:
        groups[bar['forex_day']].append(bar)

    agg_bars = []
    for forex_day in sorted(groups.keys()):
        group = groups[forex_day]
        first = group[0]
        agg = {
            'time': first['time'],
            'time_utc': first.get('time_utc', first['time']),
            'dt_utc': first['dt_utc'],
            'dt_ny': first['dt_ny'],
            'open': group[0]['open'],
            'high': max(b['high'] for b in group),
            'low': min(b['low'] for b in group),
            'close': group[-1]['close'],
            'forex_day': forex_day,
            'session': 'daily',
            'ny_window_a': any(b.get('ny_window_a', False) for b in group),
            'ny_window_b': any(b.get('ny_window_b', False) for b in group),
            'bar_count': len(group),
        }
        agg_bars.append(agg)

    return agg_bars


# ─── ATR Calculation ──────────────────────────────────────────
def compute_atr(bars, period=14):
    """Compute ATR(period) for each bar. Returns list of ATR values aligned to bars."""
    atrs = [None] * len(bars)
    trs = []
    
    for i, bar in enumerate(bars):
        if i == 0:
            tr = bar['high'] - bar['low']
        else:
            prev_close = bars[i-1]['close']
            tr = max(
                bar['high'] - bar['low'],
                abs(bar['high'] - prev_close),
                abs(bar['low'] - prev_close)
            )
        trs.append(tr)
        
        if i >= period - 1:
            if i == period - 1:
                atrs[i] = sum(trs[:period]) / period
            else:
                atrs[i] = (atrs[i-1] * (period - 1) + tr) / period
    
    return atrs


# ─── FVG Detection (runs on ANY TF bars natively) ─────────────
def detect_fvgs(bars, atrs, tf_label='1m'):
    """
    Detect FVGs natively on the given bar array.
    A genuine 5m FVG = gap exists across 3 consecutive 5m candles.
    
    Candle A = bars[i-2], B = bars[i-1], C = bars[i]
    Bullish FVG: low[C] > high[A]
    Bearish FVG: high[C] < low[A]
    """
    fvgs = []
    vis = []
    
    for i in range(2, len(bars)):
        a, b, c = bars[i-2], bars[i-1], bars[i]
        
        # ── Bullish FVG ──
        gap_bull = (c['low'] - a['high']) / PIP
        if gap_bull > 0:
            fvg = {
                'type': 'bullish',
                'bar_index': i,
                'anchor_time': a['time'],
                'detect_time': c['time'],
                'top': c['low'],
                'bottom': a['high'],
                'gap_pips': round(gap_bull, 2),
                'ce': (c['low'] + a['high']) / 2,
                'forex_day': c['forex_day'],
                'session': c['session'],
                'tf': tf_label,
            }
            fvgs.append(fvg)
        
        # ── Bearish FVG ──
        gap_bear = (a['low'] - c['high']) / PIP
        if gap_bear > 0:
            fvg = {
                'type': 'bearish',
                'bar_index': i,
                'anchor_time': a['time'],
                'detect_time': c['time'],
                'top': a['low'],
                'bottom': c['high'],
                'gap_pips': round(gap_bear, 2),
                'ce': (a['low'] + c['high']) / 2,
                'forex_day': c['forex_day'],
                'session': c['session'],
                'tf': tf_label,
            }
            fvgs.append(fvg)
        
        # ── VI (body-to-body) for confluence ──
        a_body_top = max(a['open'], a['close'])
        a_body_bot = min(a['open'], a['close'])
        c_body_top = max(c['open'], c['close'])
        c_body_bot = min(c['open'], c['close'])
        
        vi_bull_gap = (c_body_bot - a_body_top) / PIP
        if vi_bull_gap > 0:
            vis.append({'bar_index': i, 'type': 'bullish'})
        
        vi_bear_gap = (a_body_bot - c_body_top) / PIP
        if vi_bear_gap > 0:
            vis.append({'bar_index': i, 'type': 'bearish'})
    
    # Mark VI confluence
    vi_set = set((vi['bar_index'], vi['type']) for vi in vis)
    for fvg in fvgs:
        fvg['vi_confluent'] = (fvg['bar_index'], fvg['type']) in vi_set
    
    # Track invalidation events
    for fvg in fvgs:
        fvg['ce_touched_bar'] = None
        fvg['boundary_closed_bar'] = None
        fvg['ce_touched_time'] = None
        fvg['boundary_closed_time'] = None
        
        # Look ahead window scaled by TF (fewer bars on higher TF)
        look_ahead = 500 if tf_label == '1m' else 200 if tf_label == '5m' else 100
        start_idx = fvg['bar_index'] + 1
        for j in range(start_idx, min(start_idx + look_ahead, len(bars))):
            bar = bars[j]
            
            if fvg['type'] == 'bullish':
                if fvg['ce_touched_bar'] is None and bar['low'] <= fvg['ce']:
                    fvg['ce_touched_bar'] = j
                    fvg['ce_touched_time'] = bar['time']
                if fvg['boundary_closed_bar'] is None and bar['close'] < fvg['bottom']:
                    fvg['boundary_closed_bar'] = j
                    fvg['boundary_closed_time'] = bar['time']
            else:
                if fvg['ce_touched_bar'] is None and bar['high'] >= fvg['ce']:
                    fvg['ce_touched_bar'] = j
                    fvg['ce_touched_time'] = bar['time']
                if fvg['boundary_closed_bar'] is None and bar['close'] > fvg['top']:
                    fvg['boundary_closed_bar'] = j
                    fvg['boundary_closed_time'] = bar['time']
            
            if fvg['ce_touched_bar'] is not None and fvg['boundary_closed_bar'] is not None:
                break
    
    return fvgs


# ─── Swing Point Detection (runs on ANY TF bars natively) ─────
def detect_swings(bars, n=5, tf_label='1m'):
    """Detect swing highs/lows using N-bar fractal natively on given bars."""
    swings = []
    
    for i in range(n, len(bars) - n):
        # ── Swing High ──
        is_sh = True
        for j in range(i - n, i):
            if bars[i]['high'] < bars[j]['high']:
                is_sh = False
                break
        if is_sh:
            for j in range(i + 1, i + n + 1):
                if bars[i]['high'] <= bars[j]['high']:
                    is_sh = False
                    break
        
        if is_sh:
            strength = 0
            for k in range(i + n + 1, min(i + n + 1 + SWING_STRENGTH_CAP, len(bars))):
                if bars[k]['high'] > bars[i]['high']:
                    break
                strength += 1
            
            swings.append({
                'type': 'high',
                'bar_index': i,
                'time': bars[i]['time'],
                'price': bars[i]['high'],
                'strength': strength,
                'forex_day': bars[i]['forex_day'],
                'session': bars[i]['session'],
                'tf': tf_label,
            })
        
        # ── Swing Low ──
        is_sl = True
        for j in range(i - n, i):
            if bars[i]['low'] > bars[j]['low']:
                is_sl = False
                break
        if is_sl:
            for j in range(i + 1, i + n + 1):
                if bars[i]['low'] >= bars[j]['low']:
                    is_sl = False
                    break
        
        if is_sl:
            strength = 0
            for k in range(i + n + 1, min(i + n + 1 + SWING_STRENGTH_CAP, len(bars))):
                if bars[k]['low'] < bars[i]['low']:
                    break
                strength += 1
            
            swings.append({
                'type': 'low',
                'bar_index': i,
                'time': bars[i]['time'],
                'price': bars[i]['low'],
                'strength': strength,
                'forex_day': bars[i]['forex_day'],
                'session': bars[i]['session'],
                'tf': tf_label,
            })
    
    return swings


def compute_swing_height(swings):
    """Compute height (pip distance from nearest opposite swing)."""
    sorted_swings = sorted(swings, key=lambda s: s['bar_index'])
    
    for i, swing in enumerate(sorted_swings):
        min_dist = float('inf')
        for j in range(i - 1, max(i - 50, -1), -1):
            other = sorted_swings[j]
            if other['type'] != swing['type']:
                dist = abs(swing['price'] - other['price']) / PIP
                min_dist = min(min_dist, dist)
                break
        swing['height_pips'] = round(min_dist, 2) if min_dist != float('inf') else 999.0
    
    return sorted_swings


def detect_equal_levels(swings, swing_type='high', tolerances=None):
    """Legacy: detect pairs at various tolerances (kept for backward compat)."""
    if tolerances is None:
        tolerances = EQUAL_HL_TOLERANCES
    max_tol = max(tolerances)
    typed = [s for s in swings if s['type'] == swing_type]
    typed.sort(key=lambda s: s['bar_index'])
    pairs = []
    for i in range(len(typed)):
        for j in range(i + 1, min(i + 20, len(typed))):
            pip_diff = abs(typed[i]['price'] - typed[j]['price']) / PIP
            if pip_diff <= max_tol:
                pairs.append({
                    'type': swing_type,
                    'swing1_idx': typed[i]['bar_index'],
                    'swing2_idx': typed[j]['bar_index'],
                    'swing1_time': typed[i]['time'],
                    'swing2_time': typed[j]['time'],
                    'price1': typed[i]['price'],
                    'price2': typed[j]['price'],
                    'pip_diff': round(pip_diff, 2),
                    'avg_price': (typed[i]['price'] + typed[j]['price']) / 2,
                })
    return pairs


# ─── Independent EQL/EQH Detector (v0.5 rewrite) ────────────────────────────

EQL_PIVOT_LEFT = 2
EQL_PIVOT_RIGHT = 2
EQL_TOL_PIP_FLOOR = 5.0
EQL_TOL_ATR_FACTOR = 0.15
EQL_MIN_SEPARATION_MINS = 60
EQL_PULLBACK_PIP_FLOOR = 10.0
EQL_PULLBACK_ATR_FACTOR = 0.3
EQL_BREAKAWAY_ATR_FACTOR = 0.25
EQL_MIN_TOUCHES = 2

def detect_eql_pivots(bars, left=EQL_PIVOT_LEFT, right=EQL_PIVOT_RIGHT, tf_label='1m'):
    """Independent fractal pivot detector for EQL/EQH. Separate from main swings."""
    pivots = []
    for i in range(left, len(bars) - right):
        is_high = all(bars[i]['high'] >= bars[i-k]['high'] for k in range(1, left+1)) and \
                  all(bars[i]['high'] > bars[i+k]['high'] for k in range(1, right+1))
        if is_high:
            pivots.append({'type': 'high', 'bar_index': i, 'time': bars[i]['time'],
                           'price': bars[i]['high'], 'forex_day': bars[i]['forex_day'],
                           'session': bars[i]['session'], 'tf': tf_label})

        is_low = all(bars[i]['low'] <= bars[i-k]['low'] for k in range(1, left+1)) and \
                 all(bars[i]['low'] < bars[i+k]['low'] for k in range(1, right+1))
        if is_low:
            pivots.append({'type': 'low', 'bar_index': i, 'time': bars[i]['time'],
                           'price': bars[i]['low'], 'forex_day': bars[i]['forex_day'],
                           'session': bars[i]['session'], 'tf': tf_label})
    return pivots


def detect_liquidity_pools(pivots, bars, atrs, tf_minutes, tf_label='1m'):
    """Full EQL/EQH pipeline: adaptive tolerance, pullback, breakaway, touches."""
    min_sep_bars = max(1, EQL_MIN_SEPARATION_MINS // tf_minutes)
    pools_high = _match_pools([p for p in pivots if p['type'] == 'high'], bars, atrs, min_sep_bars, tf_label)
    pools_low = _match_pools([p for p in pivots if p['type'] == 'low'], bars, atrs, min_sep_bars, tf_label)
    return pools_high, pools_low


def _match_pools(typed_pivots, bars, atrs, min_sep_bars, tf_label):
    """Cluster pivots into distinct liquidity levels. One pool per level."""
    typed_pivots.sort(key=lambda p: p['bar_index'])
    if not typed_pivots:
        return []

    # Cluster pivots by price level using adaptive tolerance
    clusters = []
    used = set()
    for i, pa in enumerate(typed_pivots):
        if i in used:
            continue
        atr_at = atrs[pa['bar_index']] if atrs[pa['bar_index']] is not None else 0
        tol = max(EQL_TOL_PIP_FLOOR * PIP, EQL_TOL_ATR_FACTOR * atr_at)
        cluster = [pa]
        used.add(i)
        for j in range(i + 1, len(typed_pivots)):
            if j in used:
                continue
            if abs(typed_pivots[j]['price'] - pa['price']) <= tol:
                cluster.append(typed_pivots[j])
                used.add(j)
        if len(cluster) >= EQL_MIN_TOUCHES:
            clusters.append(cluster)

    pools = []
    for cluster in clusters:
        cluster.sort(key=lambda p: p['bar_index'])
        first, last = cluster[0], cluster[-1]
        idx_a, idx_b = first['bar_index'], last['bar_index']

        if idx_b - idx_a < min_sep_bars:
            continue

        level = sum(p['price'] for p in cluster) / len(cluster)
        atr_at = atrs[idx_a] if atrs[idx_a] is not None else 0
        tol = max(EQL_TOL_PIP_FLOOR * PIP, EQL_TOL_ATR_FACTOR * atr_at)

        # Pullback: max retrace between first and last touch
        if idx_b > idx_a + 1:
            if first['type'] == 'high':
                pullback = max((level - bars[k]['low']) for k in range(idx_a + 1, idx_b))
            else:
                pullback = max((bars[k]['high'] - level) for k in range(idx_a + 1, idx_b))
        else:
            pullback = 0
        min_pullback = max(EQL_PULLBACK_PIP_FLOOR * PIP, EQL_PULLBACK_ATR_FACTOR * atr_at)
        if pullback < min_pullback:
            continue

        pip_width = max(abs(p['price'] - level) for p in cluster) / PIP * 2
        role = 'INTERNAL' if tf_label in ['1m', '5m', '15m'] else 'EXTERNAL'
        pools.append({
            'type': first['type'],
            'swing1_idx': idx_a, 'swing2_idx': idx_b,
            'swing1_time': first['time'], 'swing2_time': last['time'],
            'price1': first['price'], 'price2': last['price'],
            'pip_diff': round(pip_width, 2),
            'avg_price': level,
            'touches': len(cluster),
            'price_width': round(pip_width, 2),
            'session': first['session'],
            'role': role,
            'pullback_pips': round(pullback / PIP, 1),
            'forex_day': first['forex_day'],
        })
    return pools


# ─── Displacement Detection (runs on ANY TF bars natively) ────
def _close_location_pass(bar, direction, threshold=0.25):
    """Close location gate: bar's close must be in the extreme % of its range."""
    rng = bar['high'] - bar['low']
    if rng == 0:
        return False
    if direction == 'bullish':
        return (bar['high'] - bar['close']) / rng <= threshold
    else:
        return (bar['close'] - bar['low']) / rng <= threshold


def _quality_grade(atr_ratio):
    if atr_ratio >= 2.0:
        return 'STRONG'
    if atr_ratio >= 1.5:
        return 'VALID'
    if atr_ratio >= 1.25:
        return 'WEAK'
    return None


def _try_cluster2(bars, i, atr):
    """Check if bars[i:i+2] form a valid 2-bar impulse cluster with all four filters."""
    if i + 2 > len(bars):
        return None
    b0, b1 = bars[i], bars[i + 1]

    dir0 = 'bullish' if b0['close'] > b0['open'] else 'bearish'
    dir1 = 'bullish' if b1['close'] > b1['open'] else 'bearish'
    if dir0 != dir1:
        return None

    r0 = b0['high'] - b0['low']
    r1 = b1['high'] - b1['low']
    if r0 == 0 or r1 == 0:
        return None

    if dir0 == 'bullish':
        if not (b1['high'] > b0['high'] and b1['low'] >= b0['low']):
            return None
    else:
        if not (b1['low'] < b0['low'] and b1['high'] <= b0['high']):
            return None

    combined_high = max(b0['high'], b1['high'])
    combined_low = min(b0['low'], b1['low'])
    combined_range = combined_high - combined_low
    if combined_range == 0:
        return None
    combined_body = abs(b1['close'] - b0['open'])
    body_ratio = combined_body / combined_range
    atr_multiple = combined_range / atr if atr > 0 else 0

    net_eff = abs(b1['close'] - b0['open']) / (r0 + r1) if (r0 + r1) > 0 else 0
    if net_eff < CLUSTER2_NET_EFF_MIN:
        return None

    overlap_top = min(b0['high'], b1['high'])
    overlap_bot = max(b0['low'], b1['low'])
    overlap = max(0, overlap_top - overlap_bot)
    smaller_range = min(r0, r1)
    overlap_ratio = overlap / smaller_range if smaller_range > 0 else 0
    if overlap_ratio > CLUSTER2_OVERLAP_MAX:
        return None

    return {
        'direction': dir0,
        'combined_range': combined_range,
        'combined_body': combined_body,
        'body_ratio': body_ratio,
        'atr_multiple': atr_multiple,
        'high': combined_high,
        'low': combined_low,
        'net_efficiency': round(net_eff, 4),
        'overlap_ratio': round(overlap_ratio, 4),
    }


def detect_displacement(bars, atrs, tf_label='1m'):
    """Detect displacement events: single candle + optional 2-bar cluster.

    Cluster_3 disabled. Cluster_2 requires all four filters:
    net efficiency >= 0.65, internal overlap <= 0.35,
    progressive extremes, same-direction bodies.
    """
    tf_defaults = DISP_TF_DEFAULTS.get(tf_label, DISP_TF_DEFAULTS['5m'])
    close_threshold = tf_defaults['close_str']
    displacements = []
    used_in_cluster = set()

    for i in range(1, len(bars)):
        if i in used_in_cluster:
            continue
        atr = atrs[i]
        if atr is None or atr == 0:
            continue

        bar = bars[i]
        bar_range = bar['high'] - bar['low']
        if bar_range == 0:
            continue
        body = abs(bar['close'] - bar['open'])
        body_ratio = body / bar_range
        atr_multiple = bar_range / atr
        direction = 'bullish' if bar['close'] > bar['open'] else 'bearish'

        cluster2 = _try_cluster2(bars, i, atr)
        is_cluster = False

        if cluster2 is not None:
            c2_close = _close_location_pass(bars[i + 1], cluster2['direction'], close_threshold)
            c2_loose = (cluster2['atr_multiple'] >= DISP_ATR_MULTS[0] or
                        cluster2['body_ratio'] >= DISP_BODY_RATIOS[0])
            if c2_loose and c2_close:
                final_bar = bars[i + 1]
                is_cluster = True
                used_atr = cluster2['atr_multiple']
                used_body = cluster2['body_ratio']
                used_dir = cluster2['direction']
                used_range = cluster2['combined_range']
                used_body_abs = cluster2['combined_body']
                close_loc = c2_close
                disp_type = 'CLUSTER_2'
                used_in_cluster.add(i + 1)

        if not is_cluster:
            final_bar = bar
            used_atr = atr_multiple
            used_body = body_ratio
            used_dir = direction
            used_range = bar_range
            used_body_abs = body
            close_loc = _close_location_pass(bar, direction, close_threshold)
            disp_type = 'SINGLE'

        # Determine qualification path
        grade = _quality_grade(used_atr)
        qual_path = 'ATR_RELATIVE'

        if disp_type == 'SINGLE' and grade is None:
            ov = DECISIVE_OVERRIDE
            pip_floor = ov['pip_floor'].get(tf_label, ov['pip_floor'].get('5m', 5.0))
            range_pips = bar_range / PIP
            override_close = _close_location_pass(bar, direction, ov['close_max'])
            if (body_ratio >= ov['body_min']
                    and override_close
                    and range_pips >= pip_floor):
                qual_path = 'DECISIVE_OVERRIDE'
                grade = 'VALID'
                close_loc = True

        disp = {
            'bar_index': i,
            'bar_index_end': i + (1 if is_cluster else 0),
            'time': bar['time'],
            'time_end': final_bar['time'],
            'direction': used_dir,
            'body_pips': round(used_body_abs / PIP, 2),
            'range_pips': round(used_range / PIP, 2),
            'body_ratio': round(used_body, 4),
            'atr_multiple': round(used_atr, 4),
            'atr_value': round(atr / PIP, 2),
            'forex_day': bar['forex_day'],
            'session': bar['session'],
            'ny_window_a': bar.get('ny_window_a', False) or final_bar.get('ny_window_a', False),
            'ny_window_b': bar.get('ny_window_b', False) or final_bar.get('ny_window_b', False),
            'tf': tf_label,
            'displacement_type': disp_type,
            'close_location_pass': close_loc,
            'quality_grade': grade,
            'qualification_path': qual_path,
            'qualifies': {},
        }

        if is_cluster and cluster2:
            disp['cluster_net_eff'] = cluster2['net_efficiency']
            disp['cluster_overlap'] = cluster2['overlap_ratio']

        is_override = qual_path == 'DECISIVE_OVERRIDE'
        for atr_m in DISP_ATR_MULTS:
            for br in DISP_BODY_RATIOS:
                meets_atr = used_atr >= atr_m
                meets_body = used_body >= br
                key = f"atr{atr_m}_br{br}"
                disp['qualifies'][key] = {
                    'and': (meets_atr and meets_body) or is_override,
                    'or': meets_atr or meets_body or is_override,
                    'atr_only': meets_atr,
                    'body_only': meets_body,
                    'and_close': ((meets_atr and meets_body) or is_override) and close_loc,
                    'override': is_override,
                }

        loosest_key = f"atr{DISP_ATR_MULTS[0]}_br{DISP_BODY_RATIOS[0]}"
        if disp['qualifies'][loosest_key]['or']:
            displacements.append(disp)

    return displacements


# ─── Asia Range (session-level, TF-independent) ──────────────
def compute_asia_ranges(bars_1m):
    """Compute Asia session range per forex day. Uses 1m bars for precision."""
    day_bars = defaultdict(list)
    for bar in bars_1m:
        if bar['session'] == 'asia':
            day_bars[bar['forex_day']].append(bar)
    
    ranges = []
    for day in sorted(day_bars.keys()):
        asia_bars = day_bars[day]
        if not asia_bars:
            continue
        high = max(b['high'] for b in asia_bars)
        low = min(b['low'] for b in asia_bars)
        range_pips = round((high - low) / PIP, 1)
        
        ranges.append({
            'forex_day': day,
            'high': high,
            'low': low,
            'range_pips': range_pips,
            'bar_count': len(asia_bars),
            'start_time': asia_bars[0]['time'],  # NY time
            'end_time': asia_bars[-1]['time'],    # NY time
            'classifications': {str(t): ('TIGHT' if range_pips < t else 'WIDE') for t in ASIA_THRESHOLDS},
        })
    
    return ranges


# ─── Session Liquidity Objects (Tier 1 — deterministic) ──────

SESSION_WINDOWS = {
    'asia':       (19, 24),
    'lokz':       (2, 5),
    'nyokz':      (7, 10),
    'pre_london': (0, 2),
    'pre_ny':     (5, 7),
    'overnight':  (17, 26),  # 17:00 (prev close) to 02:00 next = 26 (wrap)
}

def compute_session_liquidity(bars_1m, forex_days):
    """Compute session H/L for all windows per forex day."""
    levels = []
    for day in forex_days:
        day_bars = [b for b in bars_1m if b['forex_day'] == day]
        if not day_bars:
            continue

        for sess_name in ['asia', 'lokz', 'nyokz']:
            sess_bars = [b for b in day_bars if b['session'] == sess_name]
            if not sess_bars:
                continue
            h = max(b['high'] for b in sess_bars)
            l = min(b['low'] for b in sess_bars)
            levels.append({'type': f'{sess_name}_H', 'price': h, 'forex_day': day,
                           'session': sess_name, 'time': sess_bars[0]['time']})
            levels.append({'type': f'{sess_name}_L', 'price': l, 'forex_day': day,
                           'session': sess_name, 'time': sess_bars[0]['time']})

        pre_london = [b for b in day_bars
                      if 0 <= int(b['time'][11:13]) < 2]
        if pre_london:
            levels.append({'type': 'pre_london_H', 'price': max(b['high'] for b in pre_london),
                           'forex_day': day, 'session': 'pre_london', 'time': pre_london[0]['time']})
            levels.append({'type': 'pre_london_L', 'price': min(b['low'] for b in pre_london),
                           'forex_day': day, 'session': 'pre_london', 'time': pre_london[0]['time']})

        pre_ny = [b for b in day_bars
                  if 5 <= int(b['time'][11:13]) < 7]
        if pre_ny:
            levels.append({'type': 'pre_ny_H', 'price': max(b['high'] for b in pre_ny),
                           'forex_day': day, 'session': 'pre_ny', 'time': pre_ny[0]['time']})
            levels.append({'type': 'pre_ny_L', 'price': min(b['low'] for b in pre_ny),
                           'forex_day': day, 'session': 'pre_ny', 'time': pre_ny[0]['time']})

    # Previous session levels
    prev_levels = []
    for i, day in enumerate(forex_days):
        if i == 0:
            continue
        prev_day = forex_days[i - 1]
        for lv in levels:
            if lv['forex_day'] == prev_day and lv['type'].startswith(('asia_', 'lokz_')):
                prev_levels.append({**lv, 'type': 'prev_' + lv['type'], 'forex_day': day})

    return levels + prev_levels


def detect_session_gated_eql(bars_1m, atrs_1m, forex_days, tf_minutes):
    """Tier 2: EQL/EQH only within session windows. Tighter params."""
    EQL2_TOL_FLOOR = 2.0
    EQL2_ATR_FACTOR = 0.1
    EQL2_PULLBACK_FLOOR = 5.0
    EQL2_PULLBACK_ATR = 0.2
    max_prox = {1: 60, 5: 240, 15: 720}.get(tf_minutes, 240)
    max_prox_bars = max(1, max_prox // tf_minutes)

    gate_windows = ['asia', 'pre_london', 'pre_ny']
    all_pools = []

    for day in forex_days:
        for win_name in gate_windows:
            if win_name == 'asia':
                win_bars = [b for b in bars_1m if b['forex_day'] == day and b['session'] == 'asia']
            elif win_name == 'pre_london':
                win_bars = [b for b in bars_1m if b['forex_day'] == day and 0 <= int(b['time'][11:13]) < 2]
            elif win_name == 'pre_ny':
                win_bars = [b for b in bars_1m if b['forex_day'] == day and 5 <= int(b['time'][11:13]) < 7]
            else:
                continue
            if len(win_bars) < 5:
                continue

            pivots = detect_eql_pivots(win_bars, left=2, right=2, tf_label=f'{tf_minutes}m')
            highs = [p for p in pivots if p['type'] == 'high']
            lows = [p for p in pivots if p['type'] == 'low']

            for typed in [highs, lows]:
                typed.sort(key=lambda p: p['bar_index'])
                used = set()
                for i, pa in enumerate(typed):
                    if i in used:
                        continue
                    idx_a = pa['bar_index']
                    atr_at = None
                    for b in bars_1m:
                        if b['time'] == pa['time']:
                            atr_at = b.get('atr')
                            break
                    atr_val = (atr_at or 3.0) * PIP
                    tol = max(EQL2_TOL_FLOOR * PIP, EQL2_ATR_FACTOR * atr_val)
                    cluster = [pa]
                    used.add(i)
                    for j in range(i + 1, len(typed)):
                        if j in used:
                            continue
                        if abs(typed[j]['price'] - pa['price']) <= tol:
                            cluster.append(typed[j])
                            used.add(j)

                    if len(cluster) < 2:
                        continue

                    cluster.sort(key=lambda p: p['bar_index'])
                    first, last = cluster[0], cluster[-1]
                    level = sum(p['price'] for p in cluster) / len(cluster)
                    pip_width = max(abs(p['price'] - level) for p in cluster) / PIP * 2

                    all_pools.append({
                        'type': first['type'],
                        'swing1_time': first['time'], 'swing2_time': last['time'],
                        'price1': first['price'], 'price2': last['price'],
                        'pip_diff': round(pip_width, 2),
                        'avg_price': level,
                        'touches': len(cluster),
                        'window': win_name,
                        'forex_day': day,
                        'role': 'INTERNAL_STOP_POOL',
                    })

    pools_high = [p for p in all_pools if p['type'] == 'high']
    pools_low = [p for p in all_pools if p['type'] == 'low']
    return pools_high, pools_low


# ─── Session Liquidity Box Objects ─────────────────────────────────
#
# Scope: detect ranges, classify BOX vs TREND, emit levels, track interactions.
# Out of scope: sweep detection, displacement logic, FVG logic, trade entry.
# Sweep interpretation belongs to the Liquidity Sweep primitive (L2/strategy).

SESSION_BOX_CONFIG = {
    'ASIA_BOX': {
        'session_filter': lambda b: b['session'] == 'asia',
        'max_range_pip': 30,
    },
    'PRE_LONDON_BOX': {
        'session_filter': lambda b: 0 <= b['dt_ny'].hour < 2,
        'max_range_pip': 15,
    },
    'PRE_NY_BOX': {
        'session_filter': lambda b: 5 <= b['dt_ny'].hour < 7,
        'max_range_pip': 20,
    },
}

SESSION_BOX_EFF_MAX = 0.60
SESSION_BOX_MID_CROSS_MIN = 2
SESSION_BOX_BALANCE_MIN = 0.30


def _track_level_interactions(bars_1m, start_idx, day, level):
    """Track four raw price events against a single level. No sweep interpretation."""
    events = {
        'traded_above': {'occurred': False, 'first_time': None},
        'traded_below': {'occurred': False, 'first_time': None},
        'closed_above': {'occurred': False, 'first_time': None},
        'closed_below': {'occurred': False, 'first_time': None},
    }
    all_found = False
    for i in range(start_idx, len(bars_1m)):
        b = bars_1m[i]
        if b['forex_day'] != day:
            break
        if not events['traded_above']['occurred'] and b['high'] > level:
            events['traded_above'] = {'occurred': True, 'first_time': b['time']}
        if not events['traded_below']['occurred'] and b['low'] < level:
            events['traded_below'] = {'occurred': True, 'first_time': b['time']}
        if not events['closed_above']['occurred'] and b['close'] > level:
            events['closed_above'] = {'occurred': True, 'first_time': b['time']}
        if not events['closed_below']['occurred'] and b['close'] < level:
            events['closed_below'] = {'occurred': True, 'first_time': b['time']}
        if all(v['occurred'] for v in events.values()):
            break
    return events


def compute_session_boxes(bars_1m, forex_days):
    """Session liquidity box objects with four-gate classification and interaction tracking.

    Four gates for CONSOLIDATION_BOX (all must pass):
      1. range_pips <= max_range_pip (per session type)
      2. efficiency <= 0.60
      3. mid_cross_count >= 2 (rotation proof)
      4. balance_score >= 0.30 (time distribution proof)

    Interaction layer tracks raw price events per level — no sweep labels.
    """
    boxes = []
    bars_by_time = {b['time']: i for i, b in enumerate(bars_1m)}

    for day in forex_days:
        day_all = [b for b in bars_1m if b['forex_day'] == day]
        if not day_all:
            continue
        day_end_time = day_all[-1]['time']

        for box_type, cfg in SESSION_BOX_CONFIG.items():
            win_bars = [b for b in day_all if cfg['session_filter'](b)]
            if len(win_bars) < 3:
                continue

            h = max(b['high'] for b in win_bars)
            l = min(b['low'] for b in win_bars)
            mid = (h + l) / 2
            rng = (h - l) / PIP
            net = abs(win_bars[-1]['close'] - win_bars[0]['open']) / PIP
            eff = net / rng if rng > 0 else 0

            mid_crosses = 0
            for i in range(1, len(win_bars)):
                prev_c = win_bars[i - 1]['close']
                curr_c = win_bars[i]['close']
                if (prev_c < mid and curr_c > mid) or (prev_c > mid and curr_c < mid):
                    mid_crosses += 1

            above_mid = sum(1 for b in win_bars if b['close'] > mid)
            below_mid = sum(1 for b in win_bars if b['close'] < mid)
            total = len(win_bars)
            balance = min(above_mid / total, below_mid / total) if total > 0 else 0

            is_consol = (
                rng <= cfg['max_range_pip']
                and eff <= SESSION_BOX_EFF_MAX
                and mid_crosses >= SESSION_BOX_MID_CROSS_MIN
                and balance >= SESSION_BOX_BALANCE_MIN
            )
            classification = 'CONSOLIDATION_BOX' if is_consol else 'TREND_OR_EXPANSION'

            trend_dir = None
            if not is_consol:
                trend_dir = 'UP' if win_bars[-1]['close'] > win_bars[0]['open'] else 'DOWN'

            end_idx = bars_by_time.get(win_bars[-1]['time'])
            interactions = {'high': {}, 'low': {}}
            if end_idx is not None:
                scan_start = end_idx + 1
                interactions['high'] = _track_level_interactions(bars_1m, scan_start, day, h)
                interactions['low'] = _track_level_interactions(bars_1m, scan_start, day, l)

            boxes.append({
                'type': box_type,
                'forex_day': day,
                'start_time': win_bars[0]['time'],
                'end_time': win_bars[-1]['time'],
                'high': h,
                'low': l,
                'mid': mid,
                'range_pips': round(rng, 1),
                'net_change_pips': round(net, 1),
                'efficiency': round(eff, 3),
                'mid_cross_count': mid_crosses,
                'balance_score': round(balance, 3),
                'classification': classification,
                'trend_direction': trend_dir,
                'interactions': interactions,
                'line_end': day_end_time,
            })

    return boxes


# ─── HTF Liquidity Engine (v2 — SwingPoint-sourced, invalidation-aware) ────
#
# Architecture: SwingPoints → clustering with invalidation → EqualPool lifecycle.
# Dependency chain: bars → SwingPoints (fractal left=2 right=2) → HTF EQH/EQL.
# EQH/EQL is a DERIVED structure built from confirmed SwingPoint output only.
# A raw wick extreme is NOT a swing — must be a confirmed fractal pivot first.
# Status model: UNTOUCHED → TAKEN (ICT terminology).
# Invalidation during formation: if price trades through level between touches,
# pool is invalidated and never emits.

HTF_CONFIG = {
    'H1': {'minutes': 60,    'tol_pip': 2,  'max_lookback': 500, 'min_between': 6,  'pb_pip': 5,  'pb_atr': 0.25},
    'H4': {'minutes': 240,   'tol_pip': 3,  'max_lookback': 300, 'min_between': 3,  'pb_pip': 8,  'pb_atr': 0.25},
    'D1': {'minutes': 1440,  'tol_pip': 5,  'max_lookback': 180, 'min_between': 2,  'pb_pip': 12, 'pb_atr': 0.25},
    'W1': {'minutes': 10080, 'tol_pip': 10, 'max_lookback': 104, 'min_between': 2,  'pb_pip': 20, 'pb_atr': 0.25},
    'MN': {'minutes': 43200, 'tol_pip': 15, 'max_lookback': 60,  'min_between': 2,  'pb_pip': 30, 'pb_atr': 0.25},
}

HTF_MIN_TOUCHES = 2
HTF_PIVOT_LEFT = 2
HTF_PIVOT_RIGHT = 2


def _aggregate_htf(bars_1m, tf_label):
    """Aggregate 1m bars to HTF. H1/H4 via minute grouping, D1+ via forex_day/week/month."""
    if tf_label in ('H1', 'H4'):
        return aggregate_bars(bars_1m, HTF_CONFIG[tf_label]['minutes'])

    if tf_label == 'D1':
        groups = defaultdict(list)
        for b in bars_1m:
            groups[b['forex_day']].append(b)
    elif tf_label == 'W1':
        groups = defaultdict(list)
        for b in bars_1m:
            iso = b['dt_ny'].isocalendar()
            groups[f"{iso[0]}-W{iso[1]:02d}"].append(b)
    elif tf_label == 'MN':
        groups = defaultdict(list)
        for b in bars_1m:
            groups[b['dt_ny'].strftime('%Y-%m')].append(b)
    else:
        return []

    result = []
    for key in sorted(groups.keys()):
        g = groups[key]
        result.append({
            'time': g[0]['time'],
            'dt_utc': g[0]['dt_utc'],
            'dt_ny': g[0]['dt_ny'],
            'open': g[0]['open'],
            'high': max(b['high'] for b in g),
            'low': min(b['low'] for b in g),
            'close': g[-1]['close'],
            'forex_day': g[0].get('forex_day', ''),
            'session': tf_label.lower(),
        })
    return result


def _detect_htf_swings(bars):
    """Fractal SwingPoint detection for HTF bars (left=2, right=2).

    This is the INPUT STREAM for EQH/EQL. A raw wick is not a swing —
    must be confirmed fractal pivot first. Carries session metadata
    for Asia filter.
    """
    swings = []
    L, R = HTF_PIVOT_LEFT, HTF_PIVOT_RIGHT
    for i in range(L, len(bars) - R):
        is_high = all(bars[i]['high'] >= bars[i - k]['high'] for k in range(1, L + 1)) and \
                  all(bars[i]['high'] > bars[i + k]['high'] for k in range(1, R + 1))
        if is_high:
            swings.append({'type': 'high', 'bar_index': i, 'time': bars[i]['time'],
                           'price': bars[i]['high'],
                           'session': bars[i].get('session', ''),
                           'forex_day': bars[i].get('forex_day', '')})

        is_low = all(bars[i]['low'] <= bars[i - k]['low'] for k in range(1, L + 1)) and \
                 all(bars[i]['low'] < bars[i + k]['low'] for k in range(1, R + 1))
        if is_low:
            swings.append({'type': 'low', 'bar_index': i, 'time': bars[i]['time'],
                           'price': bars[i]['low'],
                           'session': bars[i].get('session', ''),
                           'forex_day': bars[i].get('forex_day', '')})
    return swings


def _check_invalidation(bars, a_idx, b_idx, level, pool_type, tol_buffer=0):
    """Check if price traded THROUGH the level between two touch bars.

    Invalidation = price violated the level beyond the tolerance zone between
    touches (excluding touch bars). Price within tol_buffer of the level is
    considered "at the level", not "through it".
    EQH invalidated: any bar.high > level + tol_buffer
    EQL invalidated: any bar.low  < level - tol_buffer
    """
    for k in range(a_idx + 1, b_idx):
        if pool_type == 'high' and bars[k]['high'] > level + tol_buffer:
            return True
        if pool_type == 'low' and bars[k]['low'] < level - tol_buffer:
            return True
    return False


def _build_htf_pools(typed_swings, bars, atrs, cfg, swing_type):
    """Cluster confirmed SwingPoints into EqualPools with invalidation gates.

    Sequence per brief:
      1. Find candidate pools within lookback + tolerance
      2. Check min_bars_between gate
      3. Check rotation (pullback) gate
      4. Check invalidation: did price trade through level between touches?
         If yes → pool invalidated, start new
      5. All gates pass + not invalidated → add touch, update median price
      6. No match → start new pool
    After clustering: merge overlapping pools within 1.5x tolerance.
    """
    typed_swings = sorted(typed_swings, key=lambda p: p['bar_index'])
    if not typed_swings:
        return []

    max_idx = len(bars) - 1
    min_idx = max(0, max_idx - cfg['max_lookback'])
    filtered = [p for p in typed_swings if p['bar_index'] >= min_idx]
    if not filtered:
        return []

    pools = []

    for swing in filtered:
        atr_at = atrs[swing['bar_index']] if swing['bar_index'] < len(atrs) and atrs[swing['bar_index']] is not None else 0
        tol = cfg['tol_pip'] * PIP
        min_pb = max(cfg['pb_pip'] * PIP, cfg['pb_atr'] * atr_at)

        candidates = []
        for pool in pools:
            if pool.get('_invalidated'):
                continue
            dist = abs(swing['price'] - pool['price'])
            if dist <= tol:
                candidates.append((dist, pool))
        candidates.sort(key=lambda x: x[0])

        matched = False
        for _, cand_pool in candidates:
            last_touch = cand_pool['_touches'][-1]
            a_idx = last_touch['bar_index']
            b_idx = swing['bar_index']

            if (last_touch.get('session') == 'asia' and swing.get('session') == 'asia'
                    and last_touch.get('forex_day') == swing.get('forex_day')):
                continue

            if b_idx - a_idx < cfg['min_between']:
                continue

            if b_idx > a_idx + 1:
                level = cand_pool['price']
                if swing_type == 'high':
                    retrace = max((level - bars[k]['low']) for k in range(a_idx + 1, b_idx))
                else:
                    retrace = max((bars[k]['high'] - level) for k in range(a_idx + 1, b_idx))
                if retrace < min_pb:
                    continue

            if _check_invalidation(bars, a_idx, b_idx, cand_pool['price'], swing_type, tol):
                cand_pool['_invalidated'] = True
                continue

            cand_pool['_touches'].append(swing)
            prices = sorted(t['price'] for t in cand_pool['_touches'])
            cand_pool['price'] = prices[len(prices) // 2]
            matched = True
            break

        if not matched:
            pools.append({
                'price': swing['price'],
                '_touches': [swing],
                '_invalidated': False,
            })

    valid = [p for p in pools if not p.get('_invalidated') and len(p['_touches']) >= HTF_MIN_TOUCHES]

    # Merge overlapping pools (same side, within 1.5x tolerance)
    if len(valid) > 1:
        valid.sort(key=lambda p: p['price'])
        merged = [valid[0]]
        for p in valid[1:]:
            prev = merged[-1]
            merge_tol = 1.5 * cfg['tol_pip'] * PIP
            if abs(p['price'] - prev['price']) <= merge_tol:
                all_touches = prev['_touches'] + p['_touches']
                all_touches.sort(key=lambda t: t['bar_index'])
                prices = sorted(t['price'] for t in all_touches)
                prev['_touches'] = all_touches
                prev['price'] = prices[len(prices) // 2]
            else:
                merged.append(p)
        valid = merged

    return valid


def compute_htf_liquidity(bars_1m):
    """HTF Liquidity Engine v2: SwingPoints → clustering with invalidation → lifecycle.

    Input: confirmed SwingPoints (fractal left=2 right=2) per TF.
    Invalidation during formation kills the pool — it never emits.
    Status: UNTOUCHED → TAKEN (price traded through after full formation).
    """
    all_pools = []
    summary = {}

    for tf_label, cfg in HTF_CONFIG.items():
        bars = _aggregate_htf(bars_1m, tf_label)
        if len(bars) < HTF_PIVOT_LEFT + HTF_PIVOT_RIGHT + 1:
            summary[tf_label] = {'bars': len(bars), 'swings': 0, 'pools': 0,
                                 'untouched': 0, 'taken': 0}
            continue

        atrs = compute_atr(bars, period=min(14, len(bars)))
        swings = _detect_htf_swings(bars)

        highs = [s for s in swings if s['type'] == 'high']
        lows = [s for s in swings if s['type'] == 'low']

        high_pools = _build_htf_pools(highs, bars, atrs, cfg, 'high')
        low_pools = _build_htf_pools(lows, bars, atrs, cfg, 'low')

        tf_pools = []
        for pd in high_pools + low_pools:
            pool_type = 'EQH' if pd['_touches'][0]['type'] == 'high' else 'EQL'
            touches = pd['_touches']
            last_idx = touches[-1]['bar_index']

            status = 'UNTOUCHED'
            taken_time = None
            for k in range(last_idx + 1, len(bars)):
                b = bars[k]
                if pool_type == 'EQH' and b['high'] > pd['price']:
                    status = 'TAKEN'
                    taken_time = b['time']
                    break
                if pool_type == 'EQL' and b['low'] < pd['price']:
                    status = 'TAKEN'
                    taken_time = b['time']
                    break

            tf_pools.append({
                'type': pool_type,
                'timeframe': tf_label,
                'price': pd['price'],
                'touches': len(touches),
                'first_touch_time': touches[0]['time'],
                'last_touch_time': touches[-1]['time'],
                'status': status,
                'taken_time': taken_time,
                'touch_prices': [t['price'] for t in touches],
                'tags': ['HTF_STRUCTURAL'],
            })

        all_pools.extend(tf_pools)
        summary[tf_label] = {
            'bars': len(bars),
            'swings': len(swings),
            'pools': len(tf_pools),
            'untouched': sum(1 for p in tf_pools if p['status'] == 'UNTOUCHED'),
            'taken': sum(1 for p in tf_pools if p['status'] == 'TAKEN'),
        }

    return all_pools, summary


# ─── Order Block Detection (MSS-gated, v0.5 architecture) ─────
def detect_order_blocks(bars, mss_events, tf_label='1m'):
    """Detect OBs as the last opposing candle before an MSS-confirmed displacement.

    v0.5 architecture: displacement alone is NOT sufficient.
    OB requires displacement + MSS (close beyond prior swing).
    Anchor: conditional 3-bar fallback (only if bars[i-1] is same-dir or neutral).
    Thin candle filter: body_pct < 0.10 → reject candidate, continue scan.
    """
    MIN_BODY_PCT = 0.10
    obs = []

    def _is_valid_ob_candle(candle, disp_dir):
        """Check opposing direction + thin candle filter."""
        is_opposing = (
            (disp_dir == 'bullish' and candle['close'] < candle['open']) or
            (disp_dir == 'bearish' and candle['close'] > candle['open'])
        )
        if not is_opposing:
            return False
        candle_range = candle['high'] - candle['low']
        if candle_range <= 0:
            return False
        body_pct = abs(candle['close'] - candle['open']) / candle_range
        return body_pct >= MIN_BODY_PCT

    for mss in mss_events:
        mss_idx = mss['bar_index']
        direction = mss['direction'].lower()

        ob_idx = None
        preceding = bars[mss_idx - 1] if mss_idx > 0 else None

        if preceding:
            if _is_valid_ob_candle(preceding, direction):
                ob_idx = mss_idx - 1
            else:
                # Conditional fallback: scan back max 3 bars
                for j in range(mss_idx - 1, max(mss_idx - 4, -1), -1):
                    if _is_valid_ob_candle(bars[j], direction):
                        ob_idx = j
                        break

        if ob_idx is None:
            continue

        ob_bar = bars[ob_idx]

        zone_wick = {'top': ob_bar['high'], 'bottom': ob_bar['low']}
        zone_body = {'top': max(ob_bar['open'], ob_bar['close']),
                     'bottom': min(ob_bar['open'], ob_bar['close'])}

        look_ahead = 100 if tf_label == '1m' else 50 if tf_label == '5m' else 30
        retests = []
        for j in range(ob_idx + 1, min(ob_idx + look_ahead, len(bars))):
            bar = bars[j]
            retested = False
            if direction == 'bullish':
                if bar['low'] <= zone_body['top']:
                    retested = True
            else:
                if bar['high'] >= zone_body['bottom']:
                    retested = True

            if retested:
                retests.append({
                    'bar_index': j,
                    'time': bar['time'],
                    'bars_since_ob': j - ob_idx,
                })

        obs.append({
            'ob_bar_index': ob_idx,
            'ob_time': ob_bar['time'],
            'disp_bar_index': mss_idx,
            'disp_time': mss['time'],
            'direction': direction,
            'zone_wick': zone_wick,
            'zone_body': zone_body,
            'forex_day': ob_bar.get('forex_day', ''),
            'retests': retests,
            'total_retests': len(retests),
            'tf': tf_label,
            'mss_direction': mss['direction'],
            'mss_break_type': mss['break_type'],
            'broken_swing': mss['broken_swing'],
        })

    return obs


# ─── Liquidity Sweep Detection (cross-primitive) ─────────────
SWEEP_SESSION_SOURCES = {'asia', 'prev_asia', 'lokz', 'prev_lokz'}

def _deduplicate_levels(levels, pip_tolerance=0.1):
    """Deduplicate levels by (source, side, price) within pip tolerance.
    Prefers current session over prev_*, higher TF over lower TF."""
    PIP_VAL = 0.0001
    seen = {}
    for lv in levels:
        key = (lv['source'], lv['side'], round(lv['price'] / (pip_tolerance * PIP_VAL)))
        if key not in seen:
            seen[key] = lv
        else:
            existing = seen[key]
            is_prev = 'prev_' in lv.get('id', '')
            existing_is_prev = 'prev_' in existing.get('id', '')
            if existing_is_prev and not is_prev:
                seen[key] = lv
    return list(seen.values())


def detect_liquidity_sweeps(bars, swings, session_levels, pdh_pdl, atrs,
                           htf_pools=None, pwh_pwl=None, session_boxes=None,
                           tf_label='5m', return_windows=None):
    """Detect sweep and continuation events against curated liquidity pool.

    CLEAN REBUILD (2026-03-07) — Curated Pool Architecture:
      Pool evaluates only pre-qualified liquidity destinations (~15-20/day).
      LTF: PDH_PDL, ASIA_H_L, LONDON_H_L, LTF_BOX (session boxes)
      HTF: HTF_EQH, HTF_EQL (from locked HTF_LIQUIDITY_MODEL), PWH, PWL
      PROMOTED_SWING: strength >= 10 AND height >= 10pip AND current forex day only
      Excluded: raw swings, low-strength fractals, micro-pivots, EQUAL_HL (deferred)
    """
    if return_windows is None:
        return_windows = [1, 2, 3]
    PIP_VAL = 0.0001
    TF_FLOORS = {
        '1m':  {'min_breach': 0.5, 'min_reclaim': 0.5},
        '5m':  {'min_breach': 0.5, 'min_reclaim': 0.5},
        '15m': {'min_breach': 1.0, 'min_reclaim': 1.0},
    }
    floors = TF_FLOORS.get(tf_label, TF_FLOORS['5m'])
    MIN_BREACH = floors['min_breach'] * PIP_VAL
    MIN_RECLAIM = floors['min_reclaim'] * PIP_VAL
    MAX_ATR_MULT = 1.5
    MIN_REJECTION_WICK_PCT = 0.40
    SWING_STALENESS = 20

    raw_levels = []

    def _session_close_time(forex_day_str, session_type):
        """Compute valid_from_time for session-based levels (session close)."""
        day = datetime.strptime(forex_day_str, '%Y-%m-%d')
        prev = day - timedelta(days=1)
        if session_type in ('asia', 'prev_asia'):
            return day.replace(hour=0, minute=0).strftime('%Y-%m-%dT%H:%M:%S')
        elif session_type in ('lokz', 'prev_lokz'):
            return day.replace(hour=5, minute=0).strftime('%Y-%m-%dT%H:%M:%S')
        return forex_day_str + 'T00:00:00'

    # Promoted HTF swings only — curated pool architecture.
    # Gate: strength >= 10 AND height >= 10pip AND current forex day only.
    # Raw swings, low-strength fractals, micro-pivots excluded.
    PS_MIN_STRENGTH = 10
    PS_MIN_HEIGHT = 10.0
    promoted_swings = []
    for s in swings:
        if s.get('strength', 0) < PS_MIN_STRENGTH:
            continue
        if s.get('height_pips', 0) < PS_MIN_HEIGHT:
            continue
        side = 'high' if s['type'] == 'high' else 'low'
        promoted_swings.append({
            'price': s['price'], 'side': side, 'source': 'PROMOTED_SWING',
            'tf_class': 'LTF',
            'id': f"PS_{s['bar_index']}_{s['type']}", 'bar_index': s['bar_index'],
            'forex_day': s.get('forex_day', ''),
            'valid_from': s.get('time', ''),
            '_strength': s.get('strength', 0),
            '_height': s.get('height_pips', 0),
        })

    # LTF: Session levels (Asia + London only)
    for lv in session_levels:
        sess_root = lv['type'].rsplit('_', 1)[0]
        if sess_root not in SWEEP_SESSION_SOURCES:
            continue
        side = 'high' if '_H' in lv['type'] else 'low'
        src = 'ASIA_H_L' if 'asia' in lv['type'] else 'LONDON_H_L'
        valid_from = _session_close_time(lv['forex_day'], sess_root)
        raw_levels.append({
            'price': lv['price'], 'side': side, 'source': src,
            'tf_class': 'LTF',
            'id': f"{lv['type']}_{lv['forex_day']}", 'bar_index': 0,
            'forex_day': lv['forex_day'],
            'valid_from': valid_from,
        })

    # LTF: PDH/PDL — valid from 17:00 NY previous day (forex day open)
    for day, vals in pdh_pdl.items():
        d = datetime.strptime(day, '%Y-%m-%d')
        prev = d - timedelta(days=1)
        valid_from = prev.replace(hour=17, minute=0).strftime('%Y-%m-%dT%H:%M:%S')
        if 'pdh' in vals:
            raw_levels.append({
                'price': vals['pdh'], 'side': 'high', 'source': 'PDH_PDL',
                'tf_class': 'LTF',
                'id': f"PDH_{day}", 'bar_index': 0, 'forex_day': day,
                'valid_from': valid_from,
            })
        if 'pdl' in vals:
            raw_levels.append({
                'price': vals['pdl'], 'side': 'low', 'source': 'PDH_PDL',
                'tf_class': 'LTF',
                'id': f"PDL_{day}", 'bar_index': 0, 'forex_day': day,
                'valid_from': valid_from,
            })

    # LTF: Session box H/L — valid from box.end_time (session window close)
    if session_boxes:
        for box in session_boxes:
            box_id = f"{box.get('type', 'BOX')}_{box.get('forex_day', '')}"
            valid_from = box.get('end_time', '')
            raw_levels.append({
                'price': box['high'], 'side': 'high', 'source': 'LTF_BOX',
                'tf_class': 'LTF',
                'id': f"{box_id}_H", 'bar_index': 0,
                'forex_day': box.get('forex_day', ''),
                'valid_from': valid_from,
            })
            raw_levels.append({
                'price': box['low'], 'side': 'low', 'source': 'LTF_BOX',
                'tf_class': 'LTF',
                'id': f"{box_id}_L", 'bar_index': 0,
                'forex_day': box.get('forex_day', ''),
                'valid_from': valid_from,
            })

    # HTF: EQH/EQL pools from locked HTF_LIQUIDITY_MODEL
    if htf_pools:
        TF_RANK = {'MN': 5, 'W1': 4, 'D1': 3, 'H4': 2, 'H1': 1}
        htf_raw = []
        for pool in htf_pools:
            if pool.get('status') == 'TAKEN':
                continue
            side = 'high' if pool['type'] == 'EQH' else 'low'
            src = 'HTF_EQH' if pool['type'] == 'EQH' else 'HTF_EQL'
            htf_raw.append({
                'price': pool['price'], 'side': side, 'source': src,
                'tf_class': 'HTF',
                'id': f"{src}_{pool['timeframe']}_{pool['price']:.5f}",
                'tf_origin': pool['timeframe'],
                'bar_index': 0, 'forex_day': '',
                'valid_from': pool.get('last_touch_time', ''),
                '_tf_rank': TF_RANK.get(pool['timeframe'], 0),
            })
        htf_raw.sort(key=lambda x: -x['_tf_rank'])
        for lv in htf_raw:
            del lv['_tf_rank']
        raw_levels.extend(htf_raw)

    # HTF: Previous week high/low — valid from week start
    if pwh_pwl:
        valid_from = '2024-01-07T17:00:00'
        if 'pwh' in pwh_pwl:
            raw_levels.append({
                'price': pwh_pwl['pwh'], 'side': 'high', 'source': 'PWH',
                'tf_class': 'HTF',
                'id': 'PWH', 'bar_index': 0, 'forex_day': '',
                'valid_from': valid_from,
            })
        if 'pwl' in pwh_pwl:
            raw_levels.append({
                'price': pwh_pwl['pwl'], 'side': 'low', 'source': 'PWL',
                'tf_class': 'HTF',
                'id': 'PWL', 'bar_index': 0, 'forex_day': '',
                'valid_from': valid_from,
            })

    # Deduplicate non-swing levels (swing levels are unique per bar_index)
    deduped = _deduplicate_levels(raw_levels)

    # Merge nearby levels into pools (1.0 pip tolerance)
    MERGE_TOL = 1.0 * PIP_VAL
    SRC_PRI = {'PROMOTED_SWING': 0, 'PDH_PDL': 1, 'PWH': 2, 'PWL': 3,
               'HTF_EQH': 4, 'HTF_EQL': 5, 'LONDON_H_L': 6, 'ASIA_H_L': 7, 'LTF_BOX': 8}

    def _merge_levels(lvs):
        if not lvs:
            return []
        by_side = {'high': [], 'low': []}
        for lv in lvs:
            by_side[lv['side']].append(lv)
        merged = []
        for side, group in by_side.items():
            group.sort(key=lambda x: x['price'])
            pools = []
            for lv in group:
                if pools and abs(lv['price'] - pools[-1]['price']) <= MERGE_TOL:
                    pools[-1]['_sources'].append(lv)
                else:
                    pools.append({**lv, '_sources': [lv]})
            for p in pools:
                srcs = p['_sources']
                srcs.sort(key=lambda x: SRC_PRI.get(x['source'], 99))
                best = srcs[0]
                merged.append({
                    'price': best['price'], 'side': best['side'],
                    'source': best['source'], 'tf_class': best.get('tf_class', 'LTF'),
                    'id': best['id'], 'bar_index': best.get('bar_index', 0),
                    'forex_day': best.get('forex_day', ''),
                    'valid_from': best.get('valid_from', ''),
                    'sources_merged': [s['source'] for s in srcs],
                    'touch_count': len(srcs),
                })
        return merged

    merged_non_swing = _merge_levels(deduped)
    levels = promoted_swings + merged_non_swing

    max_rw = max(return_windows)
    results = {rw: {'sweeps': [], 'continuations': []} for rw in return_windows}
    cont_seen = set()
    swept_levels = set()

    for i, bar in enumerate(bars):
        atr_val = atrs[i] if i < len(atrs) and atrs[i] is not None else None
        if atr_val is None:
            continue
        max_breach = MAX_ATR_MULT * atr_val
        candle_range = bar['high'] - bar['low']

        bar_time = bar.get('time', '')

        for lv in levels:
            # Consumed check: swept levels cannot be swept again
            lv_key = (lv['id'], lv['side'])
            if lv_key in swept_levels:
                continue

            # Temporal gate: level must be established before this bar
            if lv['source'] == 'PROMOTED_SWING':
                if lv['bar_index'] >= i:
                    continue
                if i - lv['bar_index'] > SWING_STALENESS:
                    continue
                bar_fd = bar.get('forex_day', '')
                if bar_fd and lv.get('forex_day', '') and lv['forex_day'] != bar_fd:
                    continue
            else:
                vf = lv.get('valid_from', '')
                if vf and bar_time < vf:
                    continue

            # BEARISH sweep candidate: wick above high-side level
            if lv['side'] == 'high' and bar['high'] > lv['price']:
                breach = bar['high'] - lv['price']
                if breach < MIN_BREACH:
                    continue
                if breach > max_breach:
                    cont_key = (lv['id'], 'BEARISH')
                    if cont_key not in cont_seen:
                        cont_seen.add(cont_key)
                        results[1]['continuations'].append({
                            'type': 'CONTINUATION', 'direction': 'BEARISH',
                            'bar_index': i, 'time': bar['time'],
                            'level_price': lv['price'], 'source': lv['source'],
                            'source_id': lv['id'], 'breach_pips': round(breach / PIP_VAL, 1),
                            'forex_day': bar.get('forex_day', ''), 'tf': tf_label,
                        })
                    continue

                for rw in return_windows:
                    closed_back = False
                    return_bar_idx = i
                    for j in range(i, min(i + rw, len(bars))):
                        if bars[j]['close'] < lv['price']:
                            closed_back = True
                            return_bar_idx = j
                            break
                    if not closed_back:
                        continue

                    actual_rw = return_bar_idx - i + 1
                    confirm_bar = bars[return_bar_idx]
                    reclaim = lv['price'] - confirm_bar['close']
                    if reclaim < MIN_RECLAIM:
                        continue
                    rej_pct = 0
                    if actual_rw == 1 and candle_range > 0:
                        rej_wick = bar['high'] - max(bar['open'], bar['close'])
                        rej_pct = rej_wick / candle_range
                        if rej_pct < MIN_REJECTION_WICK_PCT:
                            continue

                    session_name = bar.get('session', 'other')
                    kill_zone = 'LOKZ' if session_name == 'lokz' else 'NYOKZ' if session_name == 'nyokz' else 'NONE'
                    results[rw]['sweeps'].append({
                        'type': 'SWEEP', 'direction': 'BEARISH',
                        'bar_index': i, 'time': bar['time'],
                        'level_price': lv['price'], 'source': lv['source'],
                        'source_id': lv['id'], 'tf_class': lv.get('tf_class', 'LTF'),
                        'sources_merged': lv.get('sources_merged', [lv['source']]),
                        'touch_count': lv.get('touch_count', 1),
                        'breach_pips': round(breach / PIP_VAL, 1),
                        'reclaim_pips': round(reclaim / PIP_VAL, 1),
                        'rejection_wick_pct': round(rej_pct, 3),
                        'return_window_used': actual_rw,
                        'return_bar': return_bar_idx,
                        'forex_day': bar.get('forex_day', ''),
                        'session': session_name, 'kill_zone': kill_zone,
                        'tf': tf_label,
                    })
                    swept_levels.add(lv_key)

            # BULLISH sweep candidate: wick below low-side level
            if lv['side'] == 'low' and bar['low'] < lv['price']:
                breach = lv['price'] - bar['low']
                if breach < MIN_BREACH:
                    continue
                if breach > max_breach:
                    cont_key = (lv['id'], 'BULLISH')
                    if cont_key not in cont_seen:
                        cont_seen.add(cont_key)
                        results[1]['continuations'].append({
                            'type': 'CONTINUATION', 'direction': 'BULLISH',
                            'bar_index': i, 'time': bar['time'],
                            'level_price': lv['price'], 'source': lv['source'],
                            'source_id': lv['id'], 'breach_pips': round(breach / PIP_VAL, 1),
                            'forex_day': bar.get('forex_day', ''), 'tf': tf_label,
                        })
                    continue

                for rw in return_windows:
                    closed_back = False
                    return_bar_idx = i
                    for j in range(i, min(i + rw, len(bars))):
                        if bars[j]['close'] > lv['price']:
                            closed_back = True
                            return_bar_idx = j
                            break
                    if not closed_back:
                        continue

                    actual_rw = return_bar_idx - i + 1
                    confirm_bar = bars[return_bar_idx]
                    reclaim = confirm_bar['close'] - lv['price']
                    if reclaim < MIN_RECLAIM:
                        continue
                    rej_pct = 0
                    if actual_rw == 1 and candle_range > 0:
                        rej_wick = min(bar['open'], bar['close']) - bar['low']
                        rej_pct = rej_wick / candle_range
                        if rej_pct < MIN_REJECTION_WICK_PCT:
                            continue

                    session_name = bar.get('session', 'other')
                    kill_zone = 'LOKZ' if session_name == 'lokz' else 'NYOKZ' if session_name == 'nyokz' else 'NONE'
                    results[rw]['sweeps'].append({
                        'type': 'SWEEP', 'direction': 'BULLISH',
                        'bar_index': i, 'time': bar['time'],
                        'level_price': lv['price'], 'source': lv['source'],
                        'source_id': lv['id'], 'tf_class': lv.get('tf_class', 'LTF'),
                        'sources_merged': lv.get('sources_merged', [lv['source']]),
                        'touch_count': lv.get('touch_count', 1),
                        'breach_pips': round(breach / PIP_VAL, 1),
                        'reclaim_pips': round(reclaim / PIP_VAL, 1),
                        'rejection_wick_pct': round(rej_pct, 3),
                        'return_window_used': actual_rw,
                        'return_bar': return_bar_idx,
                        'forex_day': bar.get('forex_day', ''),
                        'session': session_name, 'kill_zone': kill_zone,
                        'tf': tf_label,
                    })
                    swept_levels.add(lv_key)

    results['_levels'] = levels
    results['_swept'] = swept_levels
    results['_bars'] = bars
    return results


def qualify_sweeps(sweep_results, displacements, tf_label='5m'):
    """Tag each sweep with qualified_sweep=true if displacement context exists.

    A: displacement BEFORE sweep (reversal model) — bearish disp before bullish sweep
    B: displacement AFTER sweep (continuation model) — bullish disp after bullish sweep
    """
    LOOKBACK = 10
    FORWARD = 5
    DISP_KEY = 'atr1.5_br0.6'

    disp_by_idx = {}
    for d in displacements:
        q = d['qualifies'].get(DISP_KEY, {})
        if q.get('and') or q.get('and_close') or q.get('override'):
            disp_by_idx[d['bar_index']] = d

    for rw_key, rw_data in sweep_results.items():
        if not isinstance(rw_data, dict) or 'sweeps' not in rw_data:
            continue
        for sw in rw_data['sweeps']:
            si = sw['bar_index']
            sw_dir = sw['direction']
            qualified = False
            qual_type = None

            # A: displacement BEFORE sweep moving INTO level
            opp_dir = 'bearish' if sw_dir == 'BULLISH' else 'bullish'
            for j in range(max(0, si - LOOKBACK), si):
                d = disp_by_idx.get(j)
                if d and d['direction'] == opp_dir:
                    qualified = True
                    qual_type = 'DISP_BEFORE'
                    break

            # B: displacement AFTER sweep moving AWAY from level
            if not qualified:
                same_dir = sw_dir.lower()
                for j in range(si, min(si + FORWARD + 1, si + FORWARD + 1)):
                    d = disp_by_idx.get(j)
                    if d and d['direction'] == same_dir:
                        qualified = True
                        qual_type = 'DISP_AFTER'
                        break

            sw['qualified_sweep'] = qualified
            sw['qualification_type'] = qual_type

    return sweep_results


def detect_delayed_sweeps(bars, levels, atrs, base_sweeps, swept_levels, tf_label='5m'):
    """Detect 2-bar delayed sweeps where same-bar sweep did NOT fire.

    Breach bar: wick beyond level, close does NOT return inside.
    Return bar (bar+1): close back inside with reclaim >= threshold.
    Rejection wick on breach OR return bar >= 0.30.
    Marks consumed levels as SWEPT.
    """
    PIP_VAL = 0.0001
    TF_FLOORS = {
        '1m':  {'min_breach': 0.5, 'min_reclaim': 0.5},
        '5m':  {'min_breach': 0.5, 'min_reclaim': 0.5},
        '15m': {'min_breach': 1.0, 'min_reclaim': 1.0},
    }
    floors = TF_FLOORS.get(tf_label, TF_FLOORS['5m'])
    MIN_BREACH = floors['min_breach'] * PIP_VAL
    MIN_RECLAIM = floors['min_reclaim'] * PIP_VAL
    MAX_ATR_MULT = 1.5
    MIN_DELAYED_WICK = 0.30
    SWING_STALENESS = 20

    base_keys = set()
    for sw in base_sweeps:
        base_keys.add((sw['bar_index'], sw['source_id'], sw['direction']))

    delayed = []

    for i in range(len(bars) - 1):
        bar = bars[i]
        bar1 = bars[i + 1]
        atr_val = atrs[i] if i < len(atrs) and atrs[i] else None
        if atr_val is None:
            continue
        max_breach = MAX_ATR_MULT * atr_val
        bar_time = bar.get('time', '')
        cr = bar['high'] - bar['low']
        cr1 = bar1['high'] - bar1['low']

        for lv in levels:
            lv_key = (lv['id'], lv['side'])
            if lv_key in swept_levels:
                continue
            if lv['source'] == 'PROMOTED_SWING':
                if lv['bar_index'] >= i or (i - lv['bar_index']) > SWING_STALENESS:
                    continue
                bar_fd = bar.get('forex_day', '')
                if bar_fd and lv.get('forex_day', '') and lv['forex_day'] != bar_fd:
                    continue
            else:
                vf = lv.get('valid_from', '')
                if vf and bar_time < vf:
                    continue

            # BEARISH: bar.high > level, bar.close >= level (no same-bar return)
            if lv['side'] == 'high' and bar['high'] > lv['price'] and bar['close'] >= lv['price']:
                breach = bar['high'] - lv['price']
                if breach < MIN_BREACH or breach > max_breach:
                    continue
                if (i, lv['id'], 'BEARISH') in base_keys:
                    continue
                if bar1['close'] < lv['price']:
                    reclaim = lv['price'] - bar1['close']
                    if reclaim < MIN_RECLAIM:
                        continue
                    rej_b = (bar['high'] - max(bar['open'], bar['close'])) / cr if cr > 0 else 0
                    rej_r = (bar1['high'] - max(bar1['open'], bar1['close'])) / cr1 if cr1 > 0 else 0
                    rej_best = max(rej_b, rej_r)
                    if rej_best < MIN_DELAYED_WICK:
                        continue
                    session_name = bar.get('session', 'other')
                    kz = 'LOKZ' if session_name == 'lokz' else 'NYOKZ' if session_name == 'nyokz' else 'NONE'
                    delayed.append({
                        'type': 'DELAYED_SWEEP', 'direction': 'BEARISH',
                        'bar_index': i, 'time': bar['time'],
                        'return_bar_time': bar1['time'],
                        'level_price': lv['price'], 'source': lv['source'],
                        'source_id': lv['id'], 'tf_class': lv.get('tf_class', 'LTF'),
                        'sources_merged': lv.get('sources_merged', [lv['source']]),
                        'touch_count': lv.get('touch_count', 1),
                        'breach_pips': round(breach / PIP_VAL, 1),
                        'reclaim_pips': round(reclaim / PIP_VAL, 1),
                        'rejection_wick_pct': round(rej_best, 3),
                        'forex_day': bar.get('forex_day', ''),
                        'session': session_name, 'kill_zone': kz,
                        'tf': tf_label,
                    })
                    swept_levels.add(lv_key)

            # BULLISH: bar.low < level, bar.close <= level (no same-bar return)
            if lv['side'] == 'low' and bar['low'] < lv['price'] and bar['close'] <= lv['price']:
                breach = lv['price'] - bar['low']
                if breach < MIN_BREACH or breach > max_breach:
                    continue
                if (i, lv['id'], 'BULLISH') in base_keys:
                    continue
                if bar1['close'] > lv['price']:
                    reclaim = bar1['close'] - lv['price']
                    if reclaim < MIN_RECLAIM:
                        continue
                    rej_b = (min(bar['open'], bar['close']) - bar['low']) / cr if cr > 0 else 0
                    rej_r = (min(bar1['open'], bar1['close']) - bar1['low']) / cr1 if cr1 > 0 else 0
                    rej_best = max(rej_b, rej_r)
                    if rej_best < MIN_DELAYED_WICK:
                        continue
                    session_name = bar.get('session', 'other')
                    kz = 'LOKZ' if session_name == 'lokz' else 'NYOKZ' if session_name == 'nyokz' else 'NONE'
                    delayed.append({
                        'type': 'DELAYED_SWEEP', 'direction': 'BULLISH',
                        'bar_index': i, 'time': bar['time'],
                        'return_bar_time': bar1['time'],
                        'level_price': lv['price'], 'source': lv['source'],
                        'source_id': lv['id'], 'tf_class': lv.get('tf_class', 'LTF'),
                        'sources_merged': lv.get('sources_merged', [lv['source']]),
                        'touch_count': lv.get('touch_count', 1),
                        'breach_pips': round(breach / PIP_VAL, 1),
                        'reclaim_pips': round(reclaim / PIP_VAL, 1),
                        'rejection_wick_pct': round(rej_best, 3),
                        'forex_day': bar.get('forex_day', ''),
                        'session': session_name, 'kill_zone': kz,
                        'tf': tf_label,
                    })
                    swept_levels.add(lv_key)

    return delayed


# ─── FVG ↔ Displacement Cross-Reference ──────────────────────
def cross_reference_disp_fvg(displacements, fvgs):
    """Mark displacement candles that also created an FVG."""
    fvg_b_indices = set()
    for fvg in fvgs:
        if fvg['gap_pips'] >= 0.5:
            fvg_b_indices.add(fvg['bar_index'] - 1)
    
    for d in displacements:
        d['created_fvg'] = d['bar_index'] in fvg_b_indices
    
    return displacements


# ─── NY Window Events ─────────────────────────────────────────
def collect_ny_window_events(bars, fvgs, swings, displacements, tf_label='1m'):
    """Collect events within NY reversal windows."""
    events_a = []
    events_b = []
    
    min_fvg = 1.0 if tf_label == '1m' else 2.0 if tf_label == '5m' else 3.0
    
    for fvg in fvgs:
        if fvg['gap_pips'] >= min_fvg:
            bar = bars[fvg['bar_index']]
            if bar.get('ny_window_a'):
                events_a.append({'type': 'fvg', 'subtype': fvg['type'], 'time': fvg['detect_time'],
                                 'bar_index': fvg['bar_index'], 'gap_pips': fvg['gap_pips']})
            if bar.get('ny_window_b'):
                events_b.append({'type': 'fvg', 'subtype': fvg['type'], 'time': fvg['detect_time'],
                                 'bar_index': fvg['bar_index'], 'gap_pips': fvg['gap_pips']})
    
    for s in swings:
        bar = bars[s['bar_index']]
        if bar.get('ny_window_a'):
            events_a.append({'type': 'swing', 'subtype': s['type'], 'time': s['time'],
                             'bar_index': s['bar_index'], 'price': s['price']})
        if bar.get('ny_window_b'):
            events_b.append({'type': 'swing', 'subtype': s['type'], 'time': s['time'],
                             'bar_index': s['bar_index'], 'price': s['price']})
    
    mid_key = f"atr1.5_br0.6"
    for d in displacements:
        if d['qualifies'].get(mid_key, {}).get('and', False):
            if d['ny_window_a']:
                events_a.append({'type': 'displacement', 'subtype': d['direction'], 'time': d['time'],
                                 'bar_index': d['bar_index'], 'range_pips': d['range_pips']})
            if d['ny_window_b']:
                events_b.append({'type': 'displacement', 'subtype': d['direction'], 'time': d['time'],
                                 'bar_index': d['bar_index'], 'range_pips': d['range_pips']})
    
    return events_a, events_b


# ─── MSS (Market Structure Shift) Detection ──────────────────
#
# Composite primitive: swing break + displacement + FVG tag.
# Consumes LOCKED SwingPoint, Displacement, FVG outputs. Does not re-derive.

MSS_CONFIRMATION_WINDOW = 3


def detect_mss(bars, swings, displacements, fvgs, tf_label='1m'):
    """Detect MSS with confirmation window and impulse suppression.

    1. Scan for first close beyond a swing (the break bar).
    2. Open a 3-bar confirmation window from the break bar.
    3. If displacement appears on break bar OR within window, MSS confirms.
    4. MSS anchors to the BREAK BAR (not the displacement bar).
    5. If no displacement within window, break is consumed — no MSS for this swing.
    6. After MSS fires, impulse suppression prevents re-firing in same leg.
    """
    swing_highs = sorted([s for s in swings if s['type'] == 'high'], key=lambda s: s['bar_index'])
    swing_lows = sorted([s for s in swings if s['type'] == 'low'], key=lambda s: s['bar_index'])

    disp_key = 'atr1.5_br0.6'
    disp_by_idx = {}
    for d in displacements:
        q = d['qualifies'].get(disp_key, {})
        if q.get('and') or q.get('override'):
            disp_by_idx[d['bar_index']] = d
            end_idx = d.get('bar_index_end')
            if end_idx is not None and end_idx != d['bar_index']:
                disp_by_idx[end_idx] = d

    fvg_bar_indices = set()
    for fvg in fvgs:
        if fvg['gap_pips'] >= 0.5:
            fvg_bar_indices.add(fvg['bar_index'] - 1)

    atrs = compute_atr(bars, period=14)
    mss_events = []
    suppression = None
    broken_swings = set()

    for i in range(1, len(bars)):
        bar = bars[i]

        # Suppression check
        if suppression is not None:
            if i <= suppression.get('suppress_until', suppression['start_idx']):
                continue

            atr_at = atrs[i] if i < len(atrs) and atrs[i] is not None else 0
            min_pb = max(5 * PIP, 0.25 * atr_at)
            reset = False

            if suppression['direction'] == 'BULLISH':
                retrace = suppression['extreme_price'] - bar['low']
                if retrace >= min_pb:
                    reset = True
                if bar['high'] > suppression['extreme_price']:
                    suppression['extreme_price'] = bar['high']
            else:
                retrace = bar['high'] - suppression['extreme_price']
                if retrace >= min_pb:
                    reset = True
                if bar['low'] < suppression['extreme_price']:
                    suppression['extreme_price'] = bar['low']

            opp_disp = disp_by_idx.get(i)
            if opp_disp and opp_disp['direction'] != suppression['direction'].lower():
                reset = True

            if bar['forex_day'] != suppression.get('forex_day'):
                reset = True

            if reset:
                suppression = None
            else:
                continue

        # Find most recent swings before this bar
        recent_sh = None
        for s in reversed(swing_highs):
            if s['bar_index'] < i:
                recent_sh = s
                break
        recent_sl = None
        for s in reversed(swing_lows):
            if s['bar_index'] < i:
                recent_sl = s
                break

        # Check bullish break: close > prior swing high
        if recent_sh and bar['close'] > recent_sh['price']:
            swing_id = ('high', recent_sh['bar_index'])
            if swing_id not in broken_swings:
                confirmed_disp = _find_displacement_in_window(
                    i, bars, disp_by_idx, 'bullish', MSS_CONFIRMATION_WINDOW)
                if confirmed_disp:
                    broken_swings.add(swing_id)
                    disp = confirmed_disp
                    trend_lows = [s for s in swing_lows if s['bar_index'] < recent_sh['bar_index']]
                    trend_highs = [s for s in swing_highs if s['bar_index'] < recent_sh['bar_index']]
                    prior_bearish = (len(trend_highs) >= 2 and len(trend_lows) >= 2
                                    and trend_highs[-1]['price'] < trend_highs[-2]['price'])

                    disp_end = disp.get('bar_index_end', disp['bar_index'])
                    mss_events.append({
                        'direction': 'BULLISH',
                        'break_type': 'REVERSAL' if prior_bearish else 'CONTINUATION',
                        'bar_index': i,
                        'time': bar['time'],
                        'window_used': disp['bar_index'] - i,
                        'broken_swing': {'type': 'SwingHigh', 'price': recent_sh['price'],
                                         'time': recent_sh['time'], 'bar_index': recent_sh['bar_index']},
                        'displacement': {
                            'atr_multiple': disp['atr_multiple'],
                            'body_ratio': disp['body_ratio'],
                            'quality_grade': disp.get('quality_grade', 'VALID'),
                            'path': disp.get('qualification_path', 'ATR_RELATIVE'),
                            'displacement_type': disp.get('displacement_type', 'SINGLE'),
                        },
                        'fvg_created': any(k in fvg_bar_indices for k in range(disp['bar_index'], disp_end + 1)),
                        'forex_day': bar['forex_day'],
                        'session': bar['session'],
                        'tf': tf_label,
                    })

                    suppress_end = max(i, disp_end)
                    high_range = range(i, min(suppress_end + 1, len(bars)))
                    suppression = {
                        'direction': 'BULLISH',
                        'extreme_price': max(bars[k]['high'] for k in high_range) if high_range else bar['high'],
                        'start_idx': i,
                        'suppress_until': suppress_end,
                        'forex_day': bar['forex_day'],
                    }
                    continue
                else:
                    broken_swings.add(swing_id)

        # Check bearish break: close < prior swing low
        if recent_sl and bar['close'] < recent_sl['price']:
            swing_id = ('low', recent_sl['bar_index'])
            if swing_id not in broken_swings:
                confirmed_disp = _find_displacement_in_window(
                    i, bars, disp_by_idx, 'bearish', MSS_CONFIRMATION_WINDOW)
                if confirmed_disp:
                    broken_swings.add(swing_id)
                    disp = confirmed_disp
                    trend_highs = [s for s in swing_highs if s['bar_index'] < recent_sl['bar_index']]
                    trend_lows = [s for s in swing_lows if s['bar_index'] < recent_sl['bar_index']]
                    prior_bullish = (len(trend_lows) >= 2 and len(trend_highs) >= 2
                                    and trend_lows[-1]['price'] > trend_lows[-2]['price'])

                    disp_end = disp.get('bar_index_end', disp['bar_index'])
                    mss_events.append({
                        'direction': 'BEARISH',
                        'break_type': 'REVERSAL' if prior_bullish else 'CONTINUATION',
                        'bar_index': i,
                        'time': bar['time'],
                        'window_used': disp['bar_index'] - i,
                        'broken_swing': {'type': 'SwingLow', 'price': recent_sl['price'],
                                         'time': recent_sl['time'], 'bar_index': recent_sl['bar_index']},
                        'displacement': {
                            'atr_multiple': disp['atr_multiple'],
                            'body_ratio': disp['body_ratio'],
                            'quality_grade': disp.get('quality_grade', 'VALID'),
                            'path': disp.get('qualification_path', 'ATR_RELATIVE'),
                            'displacement_type': disp.get('displacement_type', 'SINGLE'),
                        },
                        'fvg_created': any(k in fvg_bar_indices for k in range(disp['bar_index'], disp_end + 1)),
                        'forex_day': bar['forex_day'],
                        'session': bar['session'],
                        'tf': tf_label,
                    })

                    suppress_end = max(i, disp_end)
                    low_range = range(i, min(suppress_end + 1, len(bars)))
                    suppression = {
                        'direction': 'BEARISH',
                        'extreme_price': min(bars[k]['low'] for k in low_range) if low_range else bar['low'],
                        'start_idx': i,
                        'suppress_until': suppress_end,
                        'forex_day': bar['forex_day'],
                    }
                    continue
                else:
                    broken_swings.add(swing_id)

    return mss_events


def _find_displacement_in_window(break_idx, bars, disp_by_idx, direction, window):
    """Search for displacement in same direction within confirmation window.

    Also checks 1 bar back — a cluster starting at break_idx-1 whose second bar
    is the break bar is a valid displacement for this break.
    """
    search_start = max(0, break_idx - 1)
    for k in range(search_start, min(break_idx + window + 1, len(bars))):
        disp = disp_by_idx.get(k)
        if disp and disp['direction'] == direction:
            disp_end = disp.get('bar_index_end', disp['bar_index'])
            if disp_end >= break_idx or k >= break_idx:
                return disp
    return None


# ─── PDH/PDL Computation ─────────────────────────────────────
def compute_pdh_pdl(bars_1m):
    """Compute previous day high/low and midnight open per forex day."""
    day_bars = defaultdict(list)
    for bar in bars_1m:
        day_bars[bar['forex_day']].append(bar)
    
    days = sorted(day_bars.keys())
    levels = {}
    
    for i, day in enumerate(days):
        db = day_bars[day]
        day_high = max(b['high'] for b in db)
        day_low = min(b['low'] for b in db)
        
        # Midnight open: first bar at or after 00:00 NY
        midnight_open = None
        for b in db:
            if b['dt_ny'].hour >= 0 and b['dt_ny'].hour < 17:
                midnight_open = b['open']
                break
        if midnight_open is None and db:
            midnight_open = db[0]['open']
        
        levels[day] = {
            'day_high': day_high,
            'day_low': day_low,
            'midnight_open': midnight_open,
        }
        
        if i > 0:
            prev_day = days[i-1]
            levels[day]['pdh'] = levels[prev_day]['day_high']
            levels[day]['pdl'] = levels[prev_day]['day_low']
    
    return levels


# ─── Session Boundaries for Chart Markers ─────────────────────
def compute_session_boundaries(forex_days):
    """Compute session start/end timestamps for visual markers on charts.
    Returns list of {session, label, start_time, end_time, color} for each day."""
    boundaries = []
    
    SESSION_STYLES = {
        'asia':  {'label': 'Asia 19:00–00:00', 'color': 'rgba(156,39,176,0.15)', 'border': 'rgba(156,39,176,0.5)'},
        'lokz':  {'label': 'LOKZ 02:00–05:00', 'color': 'rgba(41,98,255,0.10)',  'border': 'rgba(41,98,255,0.4)'},
        'nyokz': {'label': 'NYOKZ 07:00–10:00','color': 'rgba(247,197,72,0.10)', 'border': 'rgba(247,197,72,0.4)'},
    }
    
    # NY reversal windows
    WINDOW_STYLES = {
        'ny_a': {'label': 'NY-A 08:00–09:00', 'color': 'rgba(239,83,80,0.06)',  'border': 'rgba(239,83,80,0.3)'},
        'ny_b': {'label': 'NY-B 10:00–11:00', 'color': 'rgba(38,166,154,0.06)', 'border': 'rgba(38,166,154,0.3)'},
    }
    
    for day_str in forex_days:
        day = datetime.strptime(day_str, '%Y-%m-%d')
        prev_day = day - timedelta(days=1)
        
        # Asia: 19:00-00:00 NY of the PREVIOUS calendar day (since forex day starts at 17:00 NY)
        asia_start = prev_day.replace(hour=19, minute=0, second=0)
        asia_end = day.replace(hour=0, minute=0, second=0)
        boundaries.append({
            'forex_day': day_str,
            'session': 'asia',
            'start_time': asia_start.strftime('%Y-%m-%dT%H:%M:%S'),
            'end_time': asia_end.strftime('%Y-%m-%dT%H:%M:%S'),
            **SESSION_STYLES['asia'],
        })
        
        # LOKZ: 02:00-05:00 NY
        lokz_start = day.replace(hour=2, minute=0, second=0)
        lokz_end = day.replace(hour=5, minute=0, second=0)
        boundaries.append({
            'forex_day': day_str,
            'session': 'lokz',
            'start_time': lokz_start.strftime('%Y-%m-%dT%H:%M:%S'),
            'end_time': lokz_end.strftime('%Y-%m-%dT%H:%M:%S'),
            **SESSION_STYLES['lokz'],
        })
        
        # NYOKZ: 07:00-10:00 NY
        nyokz_start = day.replace(hour=7, minute=0, second=0)
        nyokz_end = day.replace(hour=10, minute=0, second=0)
        boundaries.append({
            'forex_day': day_str,
            'session': 'nyokz',
            'start_time': nyokz_start.strftime('%Y-%m-%dT%H:%M:%S'),
            'end_time': nyokz_end.strftime('%Y-%m-%dT%H:%M:%S'),
            **SESSION_STYLES['nyokz'],
        })
        
        # NY Window A: 08:00-09:00 NY
        boundaries.append({
            'forex_day': day_str,
            'session': 'ny_a',
            'start_time': day.replace(hour=8, minute=0).strftime('%Y-%m-%dT%H:%M:%S'),
            'end_time': day.replace(hour=9, minute=0).strftime('%Y-%m-%dT%H:%M:%S'),
            **WINDOW_STYLES['ny_a'],
        })
        
        # NY Window B: 10:00-11:00 NY
        boundaries.append({
            'forex_day': day_str,
            'session': 'ny_b',
            'start_time': day.replace(hour=10, minute=0).strftime('%Y-%m-%dT%H:%M:%S'),
            'end_time': day.replace(hour=11, minute=0).strftime('%Y-%m-%dT%H:%M:%S'),
            **WINDOW_STYLES['ny_b'],
        })
    
    return boundaries


# ─── Process One Timeframe ────────────────────────────────────
def process_timeframe(bars, tf_label, forex_days):
    """Run all detection algorithms on one timeframe's bars. Returns detection results."""
    config = TF_CONFIG[tf_label]
    
    print(f"\n  ── Processing {tf_label} ({len(bars)} bars) ──")
    
    # ATR
    atrs = compute_atr(bars, period=14)
    for i, bar in enumerate(bars):
        bar['atr'] = round(atrs[i] / PIP, 2) if atrs[i] is not None else None
    
    # FVGs
    fvgs = detect_fvgs(bars, atrs, tf_label)
    print(f"    FVGs: {len(fvgs)} (bull: {sum(1 for f in fvgs if f['type']=='bullish')}, bear: {sum(1 for f in fvgs if f['type']=='bearish')})")
    
    fvg_thresholds = config['fvg_thresh']
    fvg_stats = {}
    for day in forex_days:
        day_fvgs = [f for f in fvgs if f['forex_day'] == day]
        fvg_stats[day] = {}
        for t in fvg_thresholds:
            filtered = [f for f in day_fvgs if f['gap_pips'] >= t]
            fvg_stats[day][str(t)] = {
                'count': len(filtered),
                'bullish': sum(1 for f in filtered if f['type'] == 'bullish'),
                'bearish': sum(1 for f in filtered if f['type'] == 'bearish'),
                'vi_confluent': sum(1 for f in filtered if f['vi_confluent']),
                'median_gap': round(sorted(f['gap_pips'] for f in filtered)[len(filtered)//2], 2) if filtered else 0,
            }
    
    # Swings
    swing_n = config.get('swing_n', SWING_N_DEFAULT)
    swings = detect_swings(bars, n=swing_n, tf_label=tf_label)
    swings = compute_swing_height(swings)
    print(f"    Swings: {len(swings)} (highs: {sum(1 for s in swings if s['type']=='high')}, lows: {sum(1 for s in swings if s['type']=='low')})")
    
    swing_height_thresholds = config['swing_height_thresh']
    equal_tol = config['equal_tol']
    
    equal_highs = detect_equal_levels(swings, 'high', equal_tol)
    equal_lows = detect_equal_levels(swings, 'low', equal_tol)

    eql_pivots = detect_eql_pivots(bars, left=EQL_PIVOT_LEFT, right=EQL_PIVOT_RIGHT, tf_label=tf_label)
    print(f"    EQL/EQH pivots: {len(eql_pivots)} (independent fractal left=2, right=2)")
    liq_pools_high, liq_pools_low = detect_liquidity_pools(eql_pivots, bars, atrs, config['minutes'], tf_label)
    print(f"    Liquidity pools: {len(liq_pools_high)} EQH, {len(liq_pools_low)} EQL")
    
    swing_stats = {}
    for day in forex_days:
        day_swings = [s for s in swings if s['forex_day'] == day]
        swing_stats[day] = {}
        for t in swing_height_thresholds:
            filtered = [s for s in day_swings if s['height_pips'] >= t]
            swing_stats[day][str(t)] = {
                'count': len(filtered),
                'highs': sum(1 for s in filtered if s['type'] == 'high'),
                'lows': sum(1 for s in filtered if s['type'] == 'low'),
                'avg_strength': round(sum(s['strength'] for s in filtered) / len(filtered), 1) if filtered else 0,
            }
    
    # Displacement
    displacements = detect_displacement(bars, atrs, tf_label)
    displacements = cross_reference_disp_fvg(displacements, fvgs)
    print(f"    Displacements: {len(displacements)} (FVG-creating: {sum(1 for d in displacements if d['created_fvg'])})")
    
    disp_stats = {}
    for day in forex_days:
        day_disps = [d for d in displacements if d['forex_day'] == day]
        disp_stats[day] = {}
        for atr_m in DISP_ATR_MULTS:
            for br in DISP_BODY_RATIOS:
                key = f"atr{atr_m}_br{br}"
                and_count = sum(1 for d in day_disps if d['qualifies'][key]['and'])
                or_count = sum(1 for d in day_disps if d['qualifies'][key]['or'])
                disp_stats[day][key] = {'and': and_count, 'or': or_count}
    
    # MSS (Market Structure Shift)
    mss_events = detect_mss(bars, swings, displacements, fvgs, tf_label)
    mss_rev = sum(1 for m in mss_events if m['break_type'] == 'REVERSAL')
    mss_cont = sum(1 for m in mss_events if m['break_type'] == 'CONTINUATION')
    mss_fvg = sum(1 for m in mss_events if m['fvg_created'])
    print(f"    MSS: {len(mss_events)} ({mss_rev} reversal, {mss_cont} continuation, {mss_fvg} FVG-tagged)")

    # Order Blocks (MSS-gated: displacement + swing break required)
    obs = detect_order_blocks(bars, mss_events, tf_label)
    print(f"    Order Blocks: {len(obs)} (MSS-gated, was displacement-only)")
    
    # NY Window events
    events_a, events_b = collect_ny_window_events(bars, fvgs, swings, displacements, tf_label)
    print(f"    NY Window A events: {len(events_a)}, B events: {len(events_b)}")
    
    return {
        'fvgs': fvgs,
        'fvg_thresholds': fvg_thresholds,
        'fvg_stats': fvg_stats,
        'swings': swings,
        'swing_height_thresholds': swing_height_thresholds,
        'equal_highs': equal_highs,
        'equal_lows': equal_lows,
        'equal_tolerances': equal_tol,
        'liq_pools_high': liq_pools_high,
        'liq_pools_low': liq_pools_low,
        'swing_stats': swing_stats,
        'displacements': displacements,
        'disp_stats': disp_stats,
        'mss_events': mss_events,
        'order_blocks': obs,
        'ny_events_a': events_a,
        'ny_events_b': events_b,
    }


# ─── Main Pipeline ────────────────────────────────────────────
def main():
    os.makedirs(OUTPUT_DIR, exist_ok=True)
    
    print("Loading CSV data...")
    bars_1m = load_csv(CSV_PATH)
    print(f"  Loaded {len(bars_1m)} bars")
    
    print("Assigning forex days and sessions (NY time)...")
    bars_1m = assign_forex_day(bars_1m)
    bars_1m = assign_session(bars_1m)
    
    forex_days = sorted(set(b['forex_day'] for b in bars_1m))
    print(f"  Forex days: {forex_days}")
    
    print("Aggregating to 5m, 15m, 1H, 4H, 1D...")
    bars_5m = aggregate_bars(bars_1m, 5)
    bars_15m = aggregate_bars(bars_1m, 15)
    bars_1h = aggregate_bars(bars_1m, 60)
    bars_4h = aggregate_bars(bars_1m, 240)
    bars_1d = aggregate_bars_daily(bars_1m)
    print(f"  5m: {len(bars_5m)} bars, 15m: {len(bars_15m)} bars")
    print(f"  1H: {len(bars_1h)} bars, 4H: {len(bars_4h)} bars, 1D: {len(bars_1d)} bars")
    
    # ── Run detections natively on EACH timeframe ──
    ALL_TF_LABELS = ['1m', '5m', '15m', '1H', '4H', '1D']
    all_bars = {'1m': bars_1m, '5m': bars_5m, '15m': bars_15m,
                '1H': bars_1h, '4H': bars_4h, '1D': bars_1d}
    tf_results = {}
    
    for tf_label in ALL_TF_LABELS:
        tf_results[tf_label] = process_timeframe(all_bars[tf_label], tf_label, forex_days)
    
    # ── Asia ranges (session-level, TF-independent) ──
    print("\nComputing Asia ranges...")
    asia_ranges = compute_asia_ranges(bars_1m)
    for ar in asia_ranges:
        print(f"  {ar['forex_day']}: {ar['range_pips']} pips")

    # ── Session Liquidity (Tier 1) ──
    print("Computing session liquidity levels...")
    session_levels = compute_session_liquidity(bars_1m, forex_days)
    print(f"  {len(session_levels)} session levels")

    # ── Session-gated EQL/EQH (Tier 2) — kept for backward compat ──
    print("Computing session-gated EQL/EQH...")
    gated_eqh, gated_eql = detect_session_gated_eql(bars_1m, None, forex_days, 1)
    print(f"  Tier 2: {len(gated_eqh)} EQH, {len(gated_eql)} EQL (session-gated, DEFERRED)")

    # ── Session Liquidity Boxes (replaces Tier 2 visual model) ──
    print("\nComputing session liquidity boxes...")
    session_boxes = compute_session_boxes(bars_1m, forex_days)
    for sb in session_boxes:
        cls = sb['classification']
        trend = f" {sb['trend_direction']}" if sb['trend_direction'] else ""
        print(f"  {sb['forex_day']} {sb['type']}: {sb['range_pips']}pip ε={sb['efficiency']} "
              f"mid×={sb['mid_cross_count']} bal={sb['balance_score']} → {cls}{trend}")

    # ── HTF Liquidity Engine ──
    print("\nComputing HTF liquidity pools (v2 — SwingPoint sourced)...")
    htf_pools, htf_summary = compute_htf_liquidity(bars_1m)
    for tf, s in sorted(htf_summary.items(), key=lambda x: HTF_CONFIG.get(x[0], {}).get('minutes', 0)):
        print(f"  {tf}: {s['bars']} bars, {s.get('swings', 0)} swings → "
              f"{s['pools']} pools ({s['untouched']} untouched, {s.get('taken', 0)} taken)")

    # ── PDH/PDL ──
    print("Computing PDH/PDL levels...")
    pdh_pdl = compute_pdh_pdl(bars_1m)

    # ── PWH/PWL (previous week high/low — dataset is 1 week) ──
    all_1m_highs = [b['high'] for b in bars_1m]
    all_1m_lows = [b['low'] for b in bars_1m]
    pwh_pwl = {'pwh': max(all_1m_highs), 'pwl': min(all_1m_lows)} if all_1m_highs else None
    if pwh_pwl:
        print(f"  PWH: {pwh_pwl['pwh']:.5f}, PWL: {pwh_pwl['pwl']:.5f}")

    # ── Liquidity Sweeps (cross-primitive: all level sources) ──
    print("\nComputing liquidity sweeps...")
    sweep_results = {}
    for tf_label in ALL_TF_LABELS:
        tf_bars = all_bars[tf_label]
        tf_swings = tf_results[tf_label]['swings']
        tf_atrs = compute_atr(tf_bars, period=14)
        sr = detect_liquidity_sweeps(tf_bars, tf_swings, session_levels, pdh_pdl, tf_atrs,
                                     htf_pools=htf_pools, pwh_pwl=pwh_pwl,
                                     session_boxes=session_boxes, tf_label=tf_label)
        tf_disps = tf_results[tf_label]['displacements']
        sr = qualify_sweeps(sr, tf_disps, tf_label)
        # Phase 3: delayed sweep detection — own swept set from rw=1 only
        base_sweeps_1 = sr[1]['sweeps']
        swept_by_base = set()
        for sw in base_sweeps_1:
            swept_by_base.add((sw['source_id'], 'high' if sw['direction'] == 'BEARISH' else 'low'))
        delayed = detect_delayed_sweeps(
            sr['_bars'], sr['_levels'], tf_atrs, base_sweeps_1,
            swept_by_base, tf_label)
        # Qualify delayed sweeps with same displacement logic
        DISP_KEY = 'atr1.5_br0.6'
        disp_by_idx = {}
        for d in tf_disps:
            q = d['qualifies'].get(DISP_KEY, {})
            if q.get('and') or q.get('and_close') or q.get('override'):
                disp_by_idx[d['bar_index']] = d
        for sw in delayed:
            si = sw['bar_index']
            sw_dir = sw['direction']
            qualified = False
            opp_dir = 'bearish' if sw_dir == 'BULLISH' else 'bullish'
            for j in range(max(0, si - 10), si):
                dd = disp_by_idx.get(j)
                if dd and dd['direction'] == opp_dir:
                    qualified = True; break
            if not qualified:
                same_dir = sw_dir.lower()
                for j in range(si, min(si + 6, len(sr['_bars']))):
                    dd = disp_by_idx.get(j)
                    if dd and dd['direction'] == same_dir:
                        qualified = True; break
            sw['qualified_sweep'] = qualified
        sr['delayed'] = delayed
        del sr['_levels'], sr['_swept'], sr['_bars']
        sweep_results[tf_label] = sr
        s1 = len(sr[1]['sweeps'])
        q1 = sum(1 for s in sr[1]['sweeps'] if s.get('qualified_sweep'))
        dl = len(delayed)
        c1 = len(sr[1]['continuations'])
        by_src = {}
        for sw in sr[1]['sweeps']:
            by_src[sw['source']] = by_src.get(sw['source'], 0) + 1
        src_str = ', '.join(f"{k}:{v}" for k, v in sorted(by_src.items()))
        print(f"  {tf_label}: {s1} base ({q1} qual, {dl} delayed), {c1} cont | {src_str}")

    # ── Session boundaries ──
    print("Computing session boundaries...")
    session_boundaries = compute_session_boundaries(forex_days)
    
    # ═══════════════════════════════════════════════════════════
    # Export JSON Files
    # ═══════════════════════════════════════════════════════════
    print("\n═══ Exporting JSON data files ═══")
    
    def serialize_bars(bar_list):
        """Serialize bars for JSON — strip datetime objects, keep NY time strings."""
        out = []
        for b in bar_list:
            sb = {k: v for k, v in b.items() if k not in ('dt_utc', 'dt_ny', 'time_utc')}
            out.append(sb)
        return out
    
    # 1. Candle data (per day, all TFs)
    for day in forex_days:
        day_data = {}
        for tf_label, bar_list in all_bars.items():
            day_bars = [b for b in bar_list if b['forex_day'] == day]
            day_data[tf_label] = serialize_bars(day_bars)
        
        path = os.path.join(OUTPUT_DIR, f"candles_{day}.json")
        with open(path, 'w') as f:
            json.dump(day_data, f)
        htf_info = ', '.join(f"{tf}:{len(day_data.get(tf, []))}" for tf in ['1H', '4H', '1D'])
        print(f"  candles_{day}.json  (1m:{len(day_data['1m'])}, 5m:{len(day_data['5m'])}, 15m:{len(day_data['15m'])}, {htf_info})")
    
    # 2. Per-TF detection data
    for tf_label in ALL_TF_LABELS:
        r = tf_results[tf_label]
        
        # FVG data
        fvg_export = {
            'fvgs': r['fvgs'],
            'thresholds': r['fvg_thresholds'],
            'stats': r['fvg_stats'],
        }
        path = os.path.join(OUTPUT_DIR, f"fvg_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(fvg_export, f)
        print(f"  fvg_data_{tf_label}.json ({len(r['fvgs'])} FVGs)")
        
        # Swing data
        swing_export = {
            'swings': r['swings'],
            'equal_highs': gated_eqh,
            'equal_lows': gated_eql,
            'session_levels': [lv for lv in session_levels if lv['forex_day'] in forex_days],
            'height_thresholds': r['swing_height_thresholds'],
            'equal_tolerances': r['equal_tolerances'],
            'stats': r['swing_stats'],
        }
        path = os.path.join(OUTPUT_DIR, f"swing_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(swing_export, f)
        print(f"  swing_data_{tf_label}.json ({len(r['swings'])} swings)")
        
        # Displacement data
        disp_export = {
            'displacements': r['displacements'],
            'atr_multipliers': DISP_ATR_MULTS,
            'body_ratios': DISP_BODY_RATIOS,
            'stats': r['disp_stats'],
        }
        path = os.path.join(OUTPUT_DIR, f"displacement_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(disp_export, f)
        print(f"  displacement_data_{tf_label}.json ({len(r['displacements'])} candidates)")
        
        # OB data
        ob_export = {
            'order_blocks': r['order_blocks'],
            'staleness_bars': OB_STALENESS_BARS,
        }
        path = os.path.join(OUTPUT_DIR, f"ob_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(ob_export, f)
        print(f"  ob_data_{tf_label}.json ({len(r['order_blocks'])} OBs)")
        
        # NY window events
        ny_export = {
            'window_a': r['ny_events_a'],
            'window_b': r['ny_events_b'],
            'window_a_ny': list(NY_WINDOW_A_NY),
            'window_b_ny': list(NY_WINDOW_B_NY),
        }
        path = os.path.join(OUTPUT_DIR, f"ny_windows_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(ny_export, f)
        print(f"  ny_windows_data_{tf_label}.json (A:{len(r['ny_events_a'])}, B:{len(r['ny_events_b'])})")

        # MSS data
        path = os.path.join(OUTPUT_DIR, f"mss_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump({'mss_events': r['mss_events']}, f)
        print(f"  mss_data_{tf_label}.json ({len(r['mss_events'])} events)")

        # Sweep data (all return windows in one file)
        sr = sweep_results[tf_label]
        sweep_export = {
            'return_windows': {
                str(rw): {'sweeps': sr[rw]['sweeps'], 'continuations': sr[rw]['continuations']}
                for rw in [1, 2, 3]
            },
            'delayed_sweeps': sr.get('delayed', []),
        }
        path = os.path.join(OUTPUT_DIR, f"sweep_data_{tf_label}.json")
        with open(path, 'w') as f:
            json.dump(sweep_export, f)
        s1 = len(sr[1]['sweeps'])
        c1 = len(sr[1]['continuations'])
        dl = len(sr.get('delayed', []))
        print(f"  sweep_data_{tf_label}.json ({s1} sweeps @1bar, {dl} delayed, {c1} cont)")
    
    # 3. Asia range data (TF-independent)
    with open(os.path.join(OUTPUT_DIR, "asia_data.json"), 'w') as f:
        json.dump({'ranges': asia_ranges, 'thresholds': ASIA_THRESHOLDS}, f)
    print(f"  asia_data.json ({len(asia_ranges)} sessions)")
    
    # 4. PDH/PDL levels
    with open(os.path.join(OUTPUT_DIR, "levels_data.json"), 'w') as f:
        json.dump(pdh_pdl, f)
    print(f"  levels_data.json")
    
    # 5. Session boundaries
    with open(os.path.join(OUTPUT_DIR, "session_boundaries.json"), 'w') as f:
        json.dump(session_boundaries, f)
    print(f"  session_boundaries.json ({len(session_boundaries)} markers)")
    
    # 6. Session boxes
    with open(os.path.join(OUTPUT_DIR, "session_boxes.json"), 'w') as f:
        json.dump({'boxes': session_boxes}, f)
    print(f"  session_boxes.json ({len(session_boxes)} boxes)")

    # 7. HTF liquidity pools
    with open(os.path.join(OUTPUT_DIR, "htf_liquidity.json"), 'w') as f:
        json.dump({'pools': htf_pools, 'summary': htf_summary}, f)
    print(f"  htf_liquidity.json ({len(htf_pools)} pools)")

    # 8. Metadata
    metadata = {
        'forex_days': forex_days,
        'total_bars_1m': len(bars_1m),
        'total_bars_5m': len(bars_5m),
        'total_bars_15m': len(bars_15m),
        'pip': PIP,
        'timezone': 'America/New_York (EST, UTC-5)',
        'sessions_ny': {k: list(v) for k, v in SESSIONS_NY.items()},
        'ny_windows_ny': {'a': list(NY_WINDOW_A_NY), 'b': list(NY_WINDOW_B_NY)},
        'tf_config': {
            '1m': {'fvg_thresholds': FVG_THRESHOLDS, 'swing_height_thresholds': SWING_HEIGHT_THRESHOLDS, 'equal_tolerances': EQUAL_HL_TOLERANCES},
            '5m': {'fvg_thresholds': FVG_THRESHOLDS_5M, 'swing_height_thresholds': SWING_HEIGHT_THRESHOLDS_5M, 'equal_tolerances': EQUAL_HL_TOLERANCES_5M},
            '15m': {'fvg_thresholds': FVG_THRESHOLDS_15M, 'swing_height_thresholds': SWING_HEIGHT_THRESHOLDS_15M, 'equal_tolerances': EQUAL_HL_TOLERANCES_15M},
        },
        'asia_thresholds': ASIA_THRESHOLDS,
        'disp_atr_multipliers': DISP_ATR_MULTS,
        'disp_body_ratios': DISP_BODY_RATIOS,
        'ob_staleness_bars': OB_STALENESS_BARS,
        'swing_n': {tf: cfg['swing_n'] for tf, cfg in TF_CONFIG.items()},
        'swing_strength_cap': SWING_STRENGTH_CAP,
    }
    with open(os.path.join(OUTPUT_DIR, "metadata.json"), 'w') as f:
        json.dump(metadata, f, indent=2)
    print(f"  metadata.json")
    
    # ── Also keep backward-compat files for the current charts during transition ──
    # (these will be replaced once charts are updated)
    # We write the 1m versions as the old file names too
    r1m = tf_results['1m']
    with open(os.path.join(OUTPUT_DIR, "fvg_data.json"), 'w') as f:
        json.dump({'fvgs': r1m['fvgs'], 'thresholds': r1m['fvg_thresholds'], 'stats': r1m['fvg_stats']}, f)
    with open(os.path.join(OUTPUT_DIR, "swing_data.json"), 'w') as f:
        json.dump({'swings': r1m['swings'], 'equal_highs': r1m['equal_highs'], 'equal_lows': r1m['equal_lows'],
                    'height_thresholds': r1m['swing_height_thresholds'], 'equal_tolerances': r1m['equal_tolerances'], 'stats': r1m['swing_stats']}, f)
    with open(os.path.join(OUTPUT_DIR, "displacement_data.json"), 'w') as f:
        json.dump({'displacements': r1m['displacements'], 'atr_multipliers': DISP_ATR_MULTS, 'body_ratios': DISP_BODY_RATIOS, 'stats': r1m['disp_stats']}, f)
    with open(os.path.join(OUTPUT_DIR, "ob_data.json"), 'w') as f:
        json.dump({'order_blocks': r1m['order_blocks'], 'staleness_bars': OB_STALENESS_BARS}, f)
    with open(os.path.join(OUTPUT_DIR, "ny_windows_data.json"), 'w') as f:
        json.dump({'window_a': r1m['ny_events_a'], 'window_b': r1m['ny_events_b']}, f)
    print("  (backward-compat legacy files updated)")
    
    print(f"\n✓ All data exported to {OUTPUT_DIR}")
    files = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.json')]
    print(f"  JSON files: {len(files)}")


if __name__ == '__main__':
    main()
