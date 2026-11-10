"""Verify document navigation failures and Markdown examples without application I/O."""

import importlib.util
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("check_docs", SCRIPTS / "check_docs.py")
docs = importlib.util.module_from_spec(spec)
spec.loader.exec_module(docs)


def write(root, name, content):
    path = root / name
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content)
    return path


def test_unicode_heading_duplicates_and_explicit_anchors():
    content = '# 规章 / **制度** 与 `API`\n## 重复\n## 重复\n<a id="stable"></a>'
    assert docs.heading_ids(content) == {
        "规章--制度-与-api",
        "重复",
        "重复-1",
        "stable",
    }


def test_fenced_examples_inline_code_and_comments_do_not_create_links():
    content = (
        "```md\n[missing](absent.md)\n## Example\n```\n"
        "~~~\n[missing](other.md)\n~~~\n"
        "`[example](not-a-link.md)`\n<!-- [hidden](missing.md) -->\n"
        "[`real`](target.md#正文)\n[ref]: target.md\n"
    )
    assert list(docs.destinations(content)) == ["target.md#正文", "target.md"]
    assert docs.heading_ids(content) == set()


def test_missing_file_and_heading_are_reported(tmp_path):
    write(tmp_path, "docs/README.md", "[page](page.md#absent)\n[missing](absent.md)")
    write(tmp_path, "docs/page.md", "# Page\n")
    errors, counts = docs.check(tmp_path)
    assert len(errors) == 2
    assert any("missing heading" in error for error in errors)
    assert any("missing absent.md" in error for error in errors)
    assert counts["local_links"] == 2


def test_reachable_source_readme_can_link_back_into_docs(tmp_path):
    write(tmp_path, "docs/README.md", "[module](../backend/README.md)")
    write(tmp_path, "backend/README.md", "[contract](../docs/contract.md#当前契约)")
    write(tmp_path, "docs/contract.md", "# 当前契约\n")
    assert docs.check(tmp_path)[0] == []


def test_unreachable_document_is_reported(tmp_path):
    write(tmp_path, "docs/README.md", "# Index\n")
    write(tmp_path, "docs/unlisted.md", "# Unlisted\n")
    assert docs.check(tmp_path)[0] == ["docs/unlisted.md: unreachable from docs/README.md"]


def test_archive_is_optional_and_other_external_paths_fail(tmp_path):
    root = tmp_path / "project"
    write(root, "docs/README.md", "[proof](../../niuma-crew-archive/missing.json)")
    assert docs.check(root)[0] == []
    errors, counts = docs.check(root, check_archive=True)
    assert counts["archive_links"] == 1
    assert "missing archive" in errors[0]
    write(root, "docs/README.md", "[outside](../../unrelated/missing.md)")
    assert "path outside project" in docs.check(root)[0][0]


def test_encoded_local_path_and_heading_work(tmp_path):
    write(tmp_path, "docs/README.md", "[page](a%20b.md#%E6%AD%A3%E6%96%87)")
    write(tmp_path, "docs/a b.md", "# 正文\n")
    assert docs.check(tmp_path)[0] == []


def test_generated_review_cache_is_excluded_but_project_records_are_checked(tmp_path):
    write(tmp_path, "docs/README.md", "[record](records/review.md)")
    write(tmp_path, ".impeccable/critique/review.md", "[snapshot](missing.png)")
    write(tmp_path, "docs/records/review.md", "[proof](missing.json)")
    errors, counts = docs.check(tmp_path)
    assert counts["files"] == 2
    assert errors == ["docs/records/review.md: missing missing.json"]


def test_document_site_generated_content_is_excluded(tmp_path):
    write(tmp_path, "docs/README.md", "[site](../docs-site/README.md)")
    write(tmp_path, "docs-site/README.md", "# Site\n")
    for directory in (".generated", ".source", ".next", "out"):
        write(tmp_path, f"docs-site/{directory}/generated.md", "[site route](/docs/start)")
    errors, counts = docs.check(tmp_path)
    assert errors == []
    assert counts["files"] == 2
