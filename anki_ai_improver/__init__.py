try:
    from aqt import mw
except ImportError:
    mw = None

if mw:
    from . import addon as addon  # type: ignore[attr-defined, unused-ignore]
