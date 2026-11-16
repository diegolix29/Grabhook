"""The Builders' "Needs N GB" follows what the game folder already holds. It said 45 GB for every build, an update too: the
whole first build's (the game data 24.4 GB, the shader caches, the build files), though an update builds from the game files
kept in the folder (.hookshot_exefs and romfs) and a build from the same .nup does not read it again (make_game.py's
.hookshot_romfs stamp). A player with the game built could not tell how much an update really takes.

Checked: the Python Builder's core.needed and the Linux Builder's needed_gb on the same folders, and that the Windows Builder's
Needed (MainWindow.xaml.cs) and each window's line use them.

    python -I -B tests/test_builder_space_needed.py
"""
import importlib.util
import os
from pathlib import Path
import sys
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "builder/py"))
from hookshot_builder import core   # noqa: E402


def load_linux():
    for name in ("tkinter", "tkinter.filedialog", "tkinter.messagebox", "tkinter.ttk"):
        if name not in sys.modules:
            sys.modules[name] = types.ModuleType(name)
    tk = sys.modules["tkinter"]
    tk.Tk = type("Tk", (), {})
    tk.filedialog = sys.modules["tkinter.filedialog"]
    tk.messagebox = sys.modules["tkinter.messagebox"]
    tk.ttk = sys.modules["tkinter.ttk"]
    spec = importlib.util.spec_from_file_location("hookshot_builder_space_needed", ROOT / "builder" / "linux" / "hookshot_builder.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


linux = load_linux()
GB = 1 << 30
FULL, OVER_GAME = 45, 10


def both(folder, nup, picked):
    """core.needed in GB and needed_gb, which must agree"""
    qt = core.needed(str(folder), None if nup is None else str(nup), picked)
    tk = linux.needed_gb(str(folder), None if nup is None else str(nup), picked)
    assert qt == tk * GB, (qt, tk)
    return tk


class Needed(unittest.TestCase):
    def setUp(self):
        temporary = tempfile.TemporaryDirectory(prefix="hookshot-need-")
        self.addCleanup(temporary.cleanup)
        self.root = Path(temporary.name)
        self.out = self.root / "Hookshot"
        self.out.mkdir()
        self.nup = self.root / "game.nup"
        self.nup.write_bytes(b"authored stand-in package")

    def built(self, stamp_for=None):
        (self.out / ".hookshot_exefs").mkdir()
        (self.out / "romfs").mkdir()
        if stamp_for is not None:
            (self.out / ".hookshot_romfs").write_text(
                "unpacked by this builder: %s %d\n" % (stamp_for.name, stamp_for.stat().st_size), encoding="utf-8")

    def test_an_empty_folder_needs_a_whole_build(self):
        self.assertEqual(both(self.out, self.nup, True), FULL)
        self.assertEqual(both(self.out, self.nup, False), FULL)
        self.assertEqual(both(self.root / "not there yet", self.nup, False), FULL)

    def test_an_update_from_the_kept_game_files_needs_the_build_files_only(self):
        self.built()
        self.assertEqual(both(self.out, None, False), OVER_GAME)

    def test_the_same_nup_again_needs_the_build_files_only(self):
        self.built(stamp_for=self.nup)
        self.assertEqual(both(self.out, self.nup, True), OVER_GAME)

    def test_another_nup_needs_a_whole_build(self):
        other = self.root / "other.nup"
        other.write_bytes(b"another authored stand-in package, longer")
        self.built(stamp_for=other)
        self.assertEqual(both(self.out, self.nup, True), FULL)

    def test_the_same_name_with_another_size_needs_a_whole_build(self):
        self.built(stamp_for=self.nup)
        self.nup.write_bytes(b"authored stand-in package, a new version")
        self.assertEqual(both(self.out, self.nup, True), FULL)

    def test_folders_picked_or_no_stamp_need_a_whole_build(self):
        self.built()
        self.assertEqual(both(self.out, None, True), FULL)        # (romfs and exefs folders picked: copied or linked again)
        self.assertEqual(both(self.out, self.nup, True), FULL)    # (no stamp: the folder's copy came from folders)

    def test_a_stamp_that_does_not_decode_needs_a_whole_build(self):
        self.built()
        (self.out / ".hookshot_romfs").write_bytes(b"unpacked by this builder: \xff\xfe 1\n")
        self.assertEqual(both(self.out, self.nup, True), FULL)

    def test_only_the_game_copy_half_there_needs_a_whole_build(self):
        (self.out / "romfs").mkdir()
        self.assertEqual(both(self.out, None, False), FULL)


class Windows(unittest.TestCase):
    """The Windows Builder's Needed keeps the same rules (MainWindow.xaml.cs; .NET is not needed to read it)"""
    src = (ROOT / "builder/HookshotBuilder/MainWindow.xaml.cs").read_text(encoding="utf-8")

    def test_the_same_amounts(self):
        self.assertIn("const long NeededBytes = 45L << 30;", self.src)
        self.assertIn("const long NeededOverGameBytes = 10L << 30;", self.src)
        self.assertEqual((FULL, OVER_GAME), (core.NEEDED_BYTES // GB, core.NEEDED_OVER_GAME_BYTES // GB))
        self.assertEqual((FULL, OVER_GAME), (linux.NEEDED_GB, linux.NEEDED_OVER_GAME_GB))

    def test_the_same_stamp_and_folders(self):
        body = self.src[self.src.index("static long Needed("):]
        body = body[:body.index("\n    }\n") + 6]
        for need in ('".hookshot_exefs"', '"romfs"', '".hookshot_romfs"', "if (!picked) return NeededOverGameBytes;",
                     '$"unpacked by this builder: {System.IO.Path.GetFileName(nup)} {new FileInfo(nup).Length}"'):
            self.assertIn(need, body)

    def test_each_window_shows_the_need(self):
        self.assertIn("Needed(OutPath.Text, romfs == null ? chosenNup : null, sourcePicked)", self.src)
        self.assertNotIn('"Needs 45 GB', self.src)
        qt = (ROOT / "builder/py/hookshot_builder/window.py").read_text(encoding="utf-8")
        self.assertIn("core.needed(self.out_path.text(), None if self.romfs else self.chosen_nup, self.source_picked)", qt)
        self.assertNotIn('"Needs 45 GB', qt)
        tk = (ROOT / "builder/linux/hookshot_builder.py").read_text(encoding="utf-8")
        self.assertIn("needed_gb(os.path.expanduser(self.out.get().strip()), nup, self.source_picked)", tk)
        self.assertNotIn('"Needs 45 GB', tk)


if __name__ == "__main__":
    raise SystemExit(unittest.main(verbosity=1))
