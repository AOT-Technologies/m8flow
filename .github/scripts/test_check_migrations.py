"""Tests for check_migrations.py (stdlib unittest; run from the repo root):

    python3 -m unittest discover -s .github/scripts -p "test_*.py"
"""
import ast
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
from pathlib import Path

sys.path.insert(0, os.path.dirname(__file__))
import check_migrations as cm  # noqa: E402

SCRIPT = Path(__file__).with_name("check_migrations.py").resolve()


def tree(src: str) -> ast.Module:
    return ast.parse(textwrap.dedent(src))


class Revisions(unittest.TestCase):
    def test_string_down_revision(self):
        self.assertEqual(cm.revisions(tree('revision = "b"\ndown_revision = "a"\n')), ("b", ["a"]))

    def test_tuple_down_revision_is_a_merge(self):
        self.assertEqual(cm.revisions(tree('revision = "m"\ndown_revision = ("a", "b")\n')), ("m", ["a", "b"]))

    def test_annotated_assignment(self):
        self.assertEqual(cm.revisions(tree('revision: str = "b"\ndown_revision: str = "a"\n')), ("b", ["a"]))

    def test_none_down_revision_is_the_root(self):
        self.assertEqual(cm.revisions(tree('revision = "a"\ndown_revision = None\n')), ("a", []))

    def test_missing_revision(self):
        self.assertEqual(cm.revisions(tree('down_revision = "a"\n')), (None, ["a"]))

    def test_malformed_literal_does_not_crash(self):
        self.assertEqual(cm.revisions(tree('revision = "b"\ndown_revision = get_parent()\n')), ("b", []))


class Destructive(unittest.TestCase):
    def found(self, src):
        return [what for _, what in cm.destructive(tree(src))]

    def test_op_drops_in_upgrade(self):
        got = self.found('''
            def upgrade():
                op.drop_table("t")
                op.drop_column("t", "c")
        ''')
        self.assertEqual(got, ["op.drop_table(...)", "op.drop_column(...)"])

    def test_destructive_sql(self):
        got = self.found('''
            def upgrade():
                op.execute("DROP TABLE legacy")
                op.execute(sa.text("TRUNCATE audit"))
                op.execute(text("delete from x"))
        ''')
        self.assertEqual(len(got), 3)  # op.execute(sa.text(..)) is reported once, by the inner text()
        self.assertTrue(all("heuristic" in g for g in got))

    def test_sql_forms(self):
        for sql in ("ALTER TABLE t DROP c",
                    "alter table t\n  drop constraint fk_x",
                    "DELETE\nFROM t",
                    "DELETE -- every row\nFROM t",
                    "DELETE /* all */ FROM t",
                    "DROP MATERIALIZED VIEW v",
                    "drop sequence s"):
            with self.subTest(sql=sql):
                self.assertEqual(len(self.found(f"def upgrade():\n    op.execute({sql!r})\n")), 1)

    def test_drop_in_another_statement_is_not_alter_table(self):
        # ALTER TABLE ... DROP must be one statement.
        self.assertEqual(self.found(
            'def upgrade():\n    op.execute("ALTER TABLE t ADD c int; SELECT drop_x()")\n'), [])

    def test_downgrade_is_not_scanned(self):
        self.assertEqual(self.found('''
            def upgrade():
                op.create_table("t")
            def downgrade():
                op.drop_table("t")
                op.execute("DROP TABLE t")
        '''), [])

    def test_non_destructive_sql(self):
        self.assertEqual(self.found('''
            def upgrade():
                op.execute("CREATE INDEX i ON t (c)")
                op.execute("UPDATE t SET c = 1")
        '''), [])

    def test_other_owners_are_ignored(self):
        self.assertEqual(self.found('''
            def upgrade():
                cache.drop_table("t")
                client.execute("DROP TABLE t")
        '''), [])


class EndToEnd(unittest.TestCase):
    """The script against a throwaway migrations directory."""

    def run_on(self, files: dict) -> subprocess.CompletedProcess:
        tmp = tempfile.mkdtemp()
        versions = Path(tmp, "m8flow-backend/migrations/versions")
        versions.mkdir(parents=True)
        for name, src in files.items():
            (versions / name).write_text(textwrap.dedent(src), encoding="utf-8")
        env = dict(os.environ, GITHUB_STEP_SUMMARY=str(Path(tmp, "summary.md")))
        return subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, env=env, capture_output=True, text=True)

    def test_linear_chain_passes(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n',
                         "b.py": 'revision = "b"\ndown_revision = "a"\n'})
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_destructive_upgrade_only_warns(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n',
                         "b.py": 'revision = "b"\ndown_revision = "a"\ndef upgrade():\n    op.drop_column("t", "c")\n'})
        self.assertEqual(r.returncode, 0, r.stdout)
        self.assertIn("::warning file=m8flow-backend/migrations/versions/b.py,line=4::", r.stdout)

    def test_two_heads_fail(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n',
                         "b.py": 'revision = "b"\ndown_revision = "a"\n',
                         "c.py": 'revision = "c"\ndown_revision = "a"\n'})
        self.assertEqual(r.returncode, 1)
        self.assertIn("expected one head, found 2", r.stdout)

    def test_merge_revision_resolves_two_heads(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n',
                         "b.py": 'revision = "b"\ndown_revision = "a"\n',
                         "c.py": 'revision = "c"\ndown_revision = "a"\n',
                         "m.py": 'revision = "m"\ndown_revision = ("b", "c")\n'})
        self.assertEqual(r.returncode, 0, r.stdout)

    def test_missing_parent_fails(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = "nope"\n'})
        self.assertEqual(r.returncode, 1)
        self.assertIn("down_revision nope does not exist", r.stdout)

    def test_duplicate_revision_fails(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n',
                         "a2.py": 'revision = "a"\ndown_revision = None\n'})
        self.assertEqual(r.returncode, 1)
        self.assertIn("duplicate revision a", r.stdout)

    def test_syntax_error_fails(self):
        r = self.run_on({"a.py": 'revision = "a"\ndef upgrade(:\n'})
        self.assertEqual(r.returncode, 1)
        self.assertIn("does not compile", r.stdout)

    def test_invalid_encoding_fails_cleanly(self):
        tmp = tempfile.mkdtemp()
        versions = Path(tmp, "m8flow-backend/migrations/versions")
        versions.mkdir(parents=True)
        (versions / "a.py").write_bytes(b'revision = "a"\ndown_revision = None\n# \xff\xfe\n')
        r = subprocess.run([sys.executable, str(SCRIPT)], cwd=tmp, capture_output=True, text=True)
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("::error file=m8flow-backend/migrations/versions/a.py::Migration cannot be read", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_null_byte_fails_cleanly(self):
        r = self.run_on({"a.py": 'revision = "a"\ndown_revision = None\n\x00\n'})
        self.assertEqual(r.returncode, 1, r.stderr)
        self.assertIn("::error file=m8flow-backend/migrations/versions/a.py", r.stdout)
        self.assertNotIn("None", r.stdout)
        self.assertNotIn("Traceback", r.stderr)

    def test_zero_base_sha_scans_everything(self):
        self.assertIsNone(cm.changed_files("0" * 40))

    def test_unknown_base_sha_scans_everything(self):
        self.assertIsNone(cm.changed_files("deadbeef" * 5))


class BaseSha(unittest.TestCase):
    """Which migrations get the destructive scan, in a real git repository."""

    def setUp(self):
        self.repo = tempfile.mkdtemp()
        self.git("init", "-q")
        versions = Path(self.repo, "m8flow-backend/migrations/versions")
        versions.mkdir(parents=True)
        (versions / "a.py").write_text('revision = "a"\ndown_revision = None\n'
                                       'def upgrade():\n    op.drop_table("old_a")\n')
        self.git("add", ".")
        self.git("commit", "-qm", "a")
        self.base = self.git("rev-parse", "HEAD").strip()
        (versions / "b.py").write_text('revision = "b"\ndown_revision = "a"\n'
                                       'def upgrade():\n    op.drop_table("old_b")\n')
        self.git("add", ".")
        self.git("commit", "-qm", "b")

    def git(self, *args):
        env = dict(os.environ, GIT_AUTHOR_NAME="t", GIT_AUTHOR_EMAIL="t@t", GIT_COMMITTER_NAME="t",
                   GIT_COMMITTER_EMAIL="t@t")
        return subprocess.run(["git", "-c", "commit.gpgsign=false", *args], cwd=self.repo, env=env,
                              check=True, capture_output=True, text=True).stdout

    def warned(self, *argv):
        r = subprocess.run([sys.executable, str(SCRIPT), *argv], cwd=self.repo, capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        return sorted(line.split("file=")[1].split(",")[0].rsplit("/", 1)[1]
                      for line in r.stdout.splitlines() if line.startswith("::warning file="))

    def test_base_sha_scans_only_changed(self):
        self.assertEqual(self.warned(self.base), ["b.py"])

    def test_zero_sha_scans_all(self):  # push of a new branch: github.event.before is all zeros
        self.assertEqual(self.warned("0" * 40), ["a.py", "b.py"])

    def test_no_base_scans_all(self):
        self.assertEqual(self.warned(), ["a.py", "b.py"])

    def test_unknown_base_scans_all(self):  # e.g. a force-push whose old head was not fetched
        self.assertEqual(self.warned("1234567" * 5 + "12345"), ["a.py", "b.py"])


if __name__ == "__main__":
    unittest.main()
