"""Test bootstrap. Installs the RTN stub when the real Rust-built package
is not available (e.g. CI workers without MSVC build tools). When the real
RTN is present, this is a no-op.
"""
import sys


def _ensure_rtn_stub():
    try:
        import RTN  # noqa: F401
    except ImportError:
        from tests import rtn_stub  # noqa: F401


_ensure_rtn_stub()
