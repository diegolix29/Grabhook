"""Game-free: an update's extraction hard-links the last unpack's unchanged romfs files rather than writing them again
(a new game version took the whole romfs, 40 GB and more, beside the copy it replaces), and takes nothing whose hash
does not match the package's:
python -I -B nx2/test_nup_reuse.py"""

import hashlib
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import nup

SAME = nup.ZSTD + b"authored member the update keeps"
CHANGED_OLD = nup.ZSTD + b"authored member, first version"
CHANGED_NEW = nup.ZSTD + b"authored member, second version"   # (the same size: only the hash tells them apart)
UNHASHED = b"authored member without a listed hash"
DAMAGED = b"\x00\x00\x00\x00authored damaged member"
NEW = {"Model/same.bntx.zs": SAME, "Model/changed.bntx.zs": CHANGED_NEW, "Data/unhashed.txt": UNHASHED,
       "Model/damaged.bntx.zs": DAMAGED, "Data/added.txt": b"authored member only in the update"}
OLD = {"Model/same.bntx.zs": SAME, "Model/changed.bntx.zs": CHANGED_OLD, "Data/unhashed.txt": UNHASHED,
       "Model/damaged.bntx.zs": DAMAGED, "Data/removed.txt": b"authored member the update drops"}


class Package:
    """The update's members, each with the hash a package lists for it (none for unhashed.txt)"""
    def __init__(self):
        self.files = [("romfs", rel, len(data), 0, len(data), 0) for rel, data in NEW.items()]
        self.file_details = [(bytes(32) if rel == "Data/unhashed.txt" else hashlib.sha256(data).digest(), 0, b"")
                             for rel, data in NEW.items()]
        self.written = []

    def walk(self, part):
        for record in self.files:
            yield record[1], record

    def copy_to(self, record, output, name):
        self.written.append(record[1])
        output.write(NEW[record[1]])


class Reuse(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        root = Path(temporary.name)
        self.old = root / "romfs"
        for rel, data in OLD.items():
            (self.old / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.old / rel).write_bytes(data)
        self.out = root / ".game"
        self.package = Package()

    def extract(self):
        return nup.extract(self.package, {"romfs": 0}, str(self.out), only="romfs", quiet=True, reuse=str(self.old))

    def test_only_what_the_update_changed_is_written(self):
        n, _ = self.extract()
        self.assertEqual(sorted(self.package.written), ["Data/added.txt", "Data/unhashed.txt", "Model/changed.bntx.zs"])
        self.assertEqual(n, 3)
        for rel in ("Model/same.bntx.zs", "Model/damaged.bntx.zs"):
            self.assertTrue(os.path.samefile(self.out / "romfs" / rel, self.old / rel), rel)
        for rel, data in NEW.items():
            self.assertEqual((self.out / "romfs" / rel).read_bytes(), data, rel)
        self.assertFalse((self.out / "romfs" / "Data/removed.txt").exists())

    def test_the_last_unpack_is_left_as_it_was(self):
        self.extract()
        for rel, data in OLD.items():
            self.assertEqual((self.old / rel).read_bytes(), data, rel)
        self.assertFalse(os.path.samefile(self.out / "romfs/Model/changed.bntx.zs", self.old / "Model/changed.bntx.zs"))

    def test_a_kept_file_is_still_checked_for_damage(self):
        self.extract()
        self.assertEqual(nup.read_heads(str(self.out / nup.HEADS_NAME)), ["Model/damaged.bntx.zs"])

    def test_without_hard_links_everything_is_written(self):
        with mock.patch.object(nup.os, "link", side_effect=OSError("authored: no hard links here")) as link:
            n, _ = self.extract()
        self.assertEqual(link.call_count, 1)   # (tried once, then left off)
        self.assertEqual(n, len(NEW))
        for rel, data in NEW.items():
            self.assertEqual((self.out / "romfs" / rel).read_bytes(), data, rel)

    def test_a_link_in_the_last_unpack_is_not_taken(self):
        target = self.old / "Model/same.bntx.zs"
        target.rename(self.old / "elsewhere.bin")
        try:
            os.symlink(self.old / "elsewhere.bin", target)
        except OSError:
            self.skipTest("no symbolic links here")
        self.extract()
        self.assertIn("Model/same.bntx.zs", self.package.written)

    def test_without_a_last_unpack_everything_is_written(self):
        n, _ = nup.extract(self.package, {"romfs": 0}, str(self.out), only="romfs", quiet=True,
                           reuse=str(self.old / "missing"))
        self.assertEqual(n, len(NEW))


if __name__ == "__main__":
    unittest.main()
