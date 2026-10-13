"""The map legend (frontend/src/components/Legend.tsx) restates the risk table; this keeps the two in step."""
import re
from pathlib import Path

from planner.risk import (
    NO_TRAVEL_HEAVY_LB,
    RAIN_IN_HR_EDGES,
    SEVERE_HEAVY_LB,
    SNOW_IN_HR_EDGES,
    WIND_MPH_EDGES,
)

LEGEND = Path(__file__).resolve().parents[3] / "frontend" / "src" / "components" / "Legend.tsx"


def expected_rows():
    w, r, s = WIND_MPH_EDGES, RAIN_IN_HR_EDGES, SNOW_IN_HR_EDGES
    return [
        f"wind < {w[0]:g} mph · rain < {r[0]:.2f} in/hr · snow < {s[0]:.1f} in/hr",
        f"wind {w[0]:g} to < {w[1]:g} · rain {r[0]:.2f} to < {r[1]:.2f} · snow {s[0]:.1f} to < {s[1]:.1f}",
        f"wind {w[1]:g} to < {w[2]:g} · rain {r[1]:.2f} to < {r[2]:.2f} · snow {s[1]:.1f} to < {s[2]:.1f}",
        # rain and snow No Travel is strictly above its edge, so Severe includes the edge
        f"wind {w[2]:g} to < {w[3]:g} · rain {r[2]:.2f} to {r[3]:.2f} · snow {s[2]:.1f} to {s[3]:.1f}",
        f"wind ≥ {w[3]:g} · rain > {r[3]:.2f} · snow > {s[3]:.1f}",
    ]


def test_the_legend_states_the_risk_table_the_backend_applies():
    source = LEGEND.read_text()
    block = source[source.index("const THRESHOLDS = ["):source.index("]", source.index("const THRESHOLDS = ["))]
    assert re.findall(r"'([^']*)'", block) == expected_rows()
    assert f"Over {NO_TRAVEL_HEAVY_LB:,} lb, Severe wind is No Travel" in source
    assert f"over {SEVERE_HEAVY_LB:,} lb, High wind is" in " ".join(source.split())
