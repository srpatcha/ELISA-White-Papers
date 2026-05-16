#!/usr/bin/env python3
"""Tests for validate_latex.py"""

import os
import tempfile
import pytest
from validate_latex import (
    LaTeXValidator,
    ValidationReport,
    ValidationIssue,
    find_latex_files,
    find_bib_files,
)


@pytest.fixture
def tmp_dir():
    with tempfile.TemporaryDirectory() as d:
        yield d


class TestValidationIssue:
    def test_creation(self):
        issue = ValidationIssue("test.tex", 10, "error", "syntax", "Test message")
        assert issue.severity == "error"
        assert issue.line_number == 10

class TestValidationReport:
    def test_add_error(self):
        report = ValidationReport()
        report.add_issue(ValidationIssue("test.tex", 1, "error", "syntax", "err"))
        assert report.total_errors == 1

    def test_add_warning(self):
        report = ValidationReport()
        report.add_issue(ValidationIssue("test.tex", 1, "warning", "syntax", "warn"))
        assert report.total_warnings == 1


class TestLaTeXValidator:
    def test_detects_duplicate_labels(self, tmp_dir):
        tex = "\\label{fig:one}\n\\label{fig:one}\n"
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write(tex)
        v = LaTeXValidator(tmp_dir)
        v.validate_file("test.tex")
        errs = [i for i in v.report.issues if "Duplicate label" in i.message]
        assert len(errs) == 1

    def test_detects_undefined_ref(self, tmp_dir):
        tex = "\\ref{fig:missing}\n"
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write(tex)
        v = LaTeXValidator(tmp_dir)
        v.validate_file("test.tex")
        v.cross_validate()
        errs = [i for i in v.report.issues if "Undefined reference" in i.message]
        assert len(errs) == 1

    def test_detects_unmatched_env(self, tmp_dir):
        tex = "\\begin{figure}\nsome content\n"
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write(tex)
        v = LaTeXValidator(tmp_dir)
        v.validate_file("test.tex")
        errs = [i for i in v.report.issues if "Unclosed environment" in i.message]
        assert len(errs) == 1

    def test_missing_include(self, tmp_dir):
        tex = "\\input{nonexistent}\n"
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write(tex)
        v = LaTeXValidator(tmp_dir)
        v.validate_file("test.tex")
        errs = [i for i in v.report.issues if "not found" in i.message]
        assert len(errs) >= 1

    def test_valid_file(self, tmp_dir):
        tex = "\\begin{document}\nHello\n\\end{document}\n"
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write(tex)
        v = LaTeXValidator(tmp_dir)
        v.validate_file("test.tex")
        assert v.report.total_errors == 0


class TestFindFiles:
    def test_find_tex_files(self, tmp_dir):
        with open(os.path.join(tmp_dir, "test.tex"), "w") as f:
            f.write("content")
        files = find_latex_files(tmp_dir)
        assert len(files) == 1

    def test_find_bib_files(self, tmp_dir):
        with open(os.path.join(tmp_dir, "refs.bib"), "w") as f:
            f.write("@article{key, title={T}}")
        files = find_bib_files(tmp_dir)
        assert len(files) == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
