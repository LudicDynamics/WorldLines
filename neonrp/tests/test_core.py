from neonrp.core.manifest import Manifest
from neonrp.core.paths import validate_branch_name
from neonrp.core.storage import atomic_write_json, ensure_dirs


def test_manifest_defaults():
    m = Manifest()
    assert m.version == "0.3"
    assert m.current_branch == "main"
    assert m.branches["main"].head_event == -1


def test_atomic_write(tmp_path):
    target = tmp_path / "test.json"
    data = {"foo": "bar"}
    atomic_write_json(target, data)
    assert target.exists()
    assert target.read_text(encoding="utf-8").strip() == '{\n  "foo": "bar"\n}'


def test_manifest_roundtrip():
    m = Manifest()
    data = m.model_dump()
    m2 = Manifest(**data)
    assert m2.current_branch == m.current_branch


def test_ensure_dirs_creates_rules_folder(tmp_path):
    ensure_dirs(tmp_path)
    assert (tmp_path / "rules").exists()


class TestValidateBranchName:
    """Unit tests for branch name validation."""

    def test_valid_names(self):
        for name in ("test", "my-sandbox", "feature_1", "v2.0", "A1"):
            assert validate_branch_name(name) is None, f"'{name}' should be valid"

    def test_empty(self):
        assert validate_branch_name("") is not None

    def test_path_traversal_dotdot(self):
        assert validate_branch_name("..") is not None
        assert validate_branch_name("../x") is not None
        assert validate_branch_name("a..b") is not None

    def test_slash(self):
        assert validate_branch_name("a/b") is not None

    def test_backslash(self):
        assert validate_branch_name("a\\b") is not None

    def test_drive_letter(self):
        assert validate_branch_name("C:foo") is not None

    def test_dot_only(self):
        assert validate_branch_name(".") is not None

    def test_starts_with_special(self):
        assert validate_branch_name("-bad") is not None
        assert validate_branch_name(".hidden") is not None
        assert validate_branch_name("_under") is not None

    def test_long_name(self):
        assert validate_branch_name("a" * 128) is None
        assert validate_branch_name("a" * 129) is not None
