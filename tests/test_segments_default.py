"""A big command buffer's segments are cut as before unless a switch asks otherwise: RX_VK_FINE_SEGMENTS off by default (then at
most 6 segments of ~160 draws and dispatches), RX_VK_SEG_MAX only a cap, and the dry pass's wanted points only on the early path.

    python -I -B tests/test_segments_default.py
"""
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    src = (ROOT / "gpu/vk/vk_replay.cpp").read_text(encoding="utf-8")
    bad = []

    def need(ok, what):
        if not ok:
            bad.append(what)

    fine = src[src.index("bool fine_segments() {"):]
    fine = fine[:fine.index("\n}\n")]
    need('const bool on = e && atoi(e) != 0;' in fine, "RX_VK_FINE_SEGMENTS is not off by default")
    need("hardware_concurrency" not in fine, "RX_VK_FINE_SEGMENTS decided by the thread count (on by default somewhere)")
    need(re.search(r"fine_segments\(\) \? 10 : 6;", src) is not None, "seg_cap is not 6 without the fine segments")
    need("fine_segments() ? 128 : 160;" in src, "a segment's size is not ~160 without the fine segments")
    need("std::clamp<int64_t>(total / per, 1, seg_cap());" in src, "the segment count is not capped by seg_cap()")
    m = re.search(r"constexpr int kMaxBatch = (\d+);", src)
    need(m is not None and int(m.group(1)) >= 10, "kMaxBatch is smaller than the fine segments' 10")
    need("seg_early_hook && dry_wanted_only() && !seg_early_hook->wants(dry_work, p + h.size)" in src,
         "the dry pass's wanted points are not limited to the early path's hook")
    for b in bad:
        print("FAIL:", b)
    print("segments default: %s" % ("FAILED" if bad else "ok"))
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
