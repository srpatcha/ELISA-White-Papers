#!/usr/bin/env python3
"""LaTeX Build Validator for ELISA White Papers.

Validates LaTeX documents for common errors, cross-reference issues,
bibliography problems, and missing files.
"""

import argparse
import os
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


@dataclass
class ValidationIssue:
    """A single validation issue found in a LaTeX file."""
    file_path: str
    line_number: int
    severity: str  # "error", "warning", "info"
    category: str
    message: str


@dataclass
class ValidationReport:
    """Overall validation report."""
    issues: List[ValidationIssue] = field(default_factory=list)
    files_checked: int = 0
    total_errors: int = 0
    total_warnings: int = 0
    total_info: int = 0

    def add_issue(self, issue: ValidationIssue):
        self.issues.append(issue)
        if issue.severity == "error":
            self.total_errors += 1
        elif issue.severity == "warning":
            self.total_warnings += 1
        else:
            self.total_info += 1


class LaTeXValidator:
    """Validates LaTeX documents for common issues."""

    # Common LaTeX errors patterns
    COMMON_ERRORS = [
        (r'\\being\{', "Typo: \\being should be \\begin"),
        (r'\\enchapter', "Typo: \\enchapter should be \\chapter"),
        (r'\\beign\{', "Typo: \\beign should be \\begin"),
        (r'\\ednote', "Possible typo: \\ednote - did you mean \\endnote?"),
        (r'[^\\]%[^ ]', "Comment without space after % - may be intentional"),
        (r'\\begin\{document\}.*\\begin\{document\}', "Duplicate \\begin{document}"),
    ]

    # Patterns for extracting references
    LABEL_PATTERN = re.compile(r'\\label\{([^}]+)\}')
    REF_PATTERN = re.compile(r'\\(?:ref|eqref|pageref|autoref|cref|Cref)\{([^}]+)\}')
    CITE_PATTERN = re.compile(r'\\cite[tp]?\{([^}]+)\}')
    BIB_ENTRY_PATTERN = re.compile(r'@\w+\{(\w+),')
    INCLUDE_PATTERN = re.compile(r'\\(?:include|input)\{([^}]+)\}')
    GRAPHICS_PATTERN = re.compile(r'\\includegraphics(?:\[[^\]]*\])?\{([^}]+)\}')
    BIBRESOURCE_PATTERN = re.compile(r'\\(?:bibliography|addbibresource)\{([^}]+)\}')
    USEPACKAGE_PATTERN = re.compile(r'\\usepackage(?:\[[^\]]*\])?\{([^}]+)\}')

    def __init__(self, base_dir: str):
        self.base_dir = Path(base_dir)
        self.report = ValidationReport()
        self.labels: Dict[str, Tuple[str, int]] = {}
        self.refs: List[Tuple[str, str, int]] = []
        self.citations: List[Tuple[str, str, int]] = []
        self.bib_entries: Set[str] = set()

    def validate_file(self, file_path: str) -> None:
        """Validate a single LaTeX file."""
        full_path = self.base_dir / file_path
        if not full_path.exists():
            self.report.add_issue(ValidationIssue(
                file_path=file_path, line_number=0,
                severity="error", category="missing_file",
                message=f"File not found: {file_path}"
            ))
            return

        self.report.files_checked += 1
        try:
            content = full_path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            try:
                content = full_path.read_text(encoding="latin-1")
                self.report.add_issue(ValidationIssue(
                    file_path=file_path, line_number=0,
                    severity="warning", category="encoding",
                    message="File is not UTF-8 encoded, using latin-1 fallback"
                ))
            except Exception as e:
                self.report.add_issue(ValidationIssue(
                    file_path=file_path, line_number=0,
                    severity="error", category="encoding",
                    message=f"Cannot read file: {e}"
                ))
                return

        self._check_common_errors(file_path, content)
        self._extract_labels(file_path, content)
        self._extract_refs(file_path, content)
        self._extract_citations(file_path, content)
        self._check_includes(file_path, content)
        self._check_graphics(file_path, content)
        self._check_encoding_issues(file_path, content)
        self._check_unmatched_environments(file_path, content)

    def _check_common_errors(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for pattern, message in self.COMMON_ERRORS:
                if re.search(pattern, line):
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="warning", category="syntax",
                        message=message
                    ))

    def _extract_labels(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for match in self.LABEL_PATTERN.finditer(line):
                label = match.group(1)
                if label in self.labels:
                    prev_file, prev_line = self.labels[label]
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="error", category="cross_reference",
                        message=f"Duplicate label '{label}' (first defined in {prev_file}:{prev_line})"
                    ))
                else:
                    self.labels[label] = (file_path, line_num)

    def _extract_refs(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for match in self.REF_PATTERN.finditer(line):
                ref = match.group(1)
                self.refs.append((ref, file_path, line_num))

    def _extract_citations(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for match in self.CITE_PATTERN.finditer(line):
                keys = match.group(1)
                for key in keys.split(","):
                    key = key.strip()
                    if key:
                        self.citations.append((key, file_path, line_num))

    def _check_includes(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for match in self.INCLUDE_PATTERN.finditer(line):
                included = match.group(1)
                if not included.endswith(".tex"):
                    included += ".tex"
                inc_path = self.base_dir / included
                if not inc_path.exists():
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="error", category="missing_file",
                        message=f"Included file not found: {included}"
                    ))

    def _check_graphics(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            for match in self.GRAPHICS_PATTERN.finditer(line):
                img_path = match.group(1)
                # Check with and without common extensions
                found = False
                candidates = [img_path]
                if "." not in os.path.basename(img_path):
                    candidates.extend([f"{img_path}.{ext}" for ext in ["png", "jpg", "jpeg", "pdf", "eps", "svg"]])
                for candidate in candidates:
                    if (self.base_dir / candidate).exists():
                        found = True
                        break
                if not found:
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="warning", category="missing_file",
                        message=f"Graphics file not found: {img_path}"
                    ))

    def _check_encoding_issues(self, file_path: str, content: str) -> None:
        for line_num, line in enumerate(content.splitlines(), 1):
            # Check for non-ASCII characters that might cause issues
            for i, ch in enumerate(line):
                if ord(ch) > 127:
                    # Common problematic characters
                    if ch in '\u201c\u201d\u2018\u2019':
                        self.report.add_issue(ValidationIssue(
                            file_path=file_path, line_number=line_num,
                            severity="info", category="encoding",
                            message=f"Smart quote detected (char {i}): consider using LaTeX quotes"
                        ))
                        break  # one per line

    def _check_unmatched_environments(self, file_path: str, content: str) -> None:
        env_stack: List[Tuple[str, int]] = []
        begin_re = re.compile(r'\\begin\{(\w+)\}')
        end_re = re.compile(r'\\end\{(\w+)\}')

        for line_num, line in enumerate(content.splitlines(), 1):
            # Skip comments
            stripped = re.sub(r'(?<!\\)%.*', '', line)
            for match in begin_re.finditer(stripped):
                env_stack.append((match.group(1), line_num))
            for match in end_re.finditer(stripped):
                env_name = match.group(1)
                if env_stack and env_stack[-1][0] == env_name:
                    env_stack.pop()
                elif env_stack:
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="error", category="syntax",
                        message=f"Mismatched environment: \\end{{{env_name}}} but expected \\end{{{env_stack[-1][0]}}}"
                    ))
                    env_stack.pop()
                else:
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="error", category="syntax",
                        message=f"Unexpected \\end{{{env_name}}} without matching \\begin"
                    ))

        for env_name, line_num in env_stack:
            self.report.add_issue(ValidationIssue(
                file_path=file_path, line_number=line_num,
                severity="error", category="syntax",
                message=f"Unclosed environment: \\begin{{{env_name}}} never closed"
            ))

    def validate_bibliography(self, bib_file: str) -> None:
        """Parse a .bib file and collect entries."""
        bib_path = self.base_dir / bib_file
        if not bib_path.exists():
            self.report.add_issue(ValidationIssue(
                file_path=bib_file, line_number=0,
                severity="error", category="bibliography",
                message=f"Bibliography file not found: {bib_file}"
            ))
            return

        content = bib_path.read_text(encoding="utf-8", errors="replace")
        for match in self.BIB_ENTRY_PATTERN.finditer(content):
            self.bib_entries.add(match.group(1))

    def cross_validate(self) -> None:
        """Check cross-references and citations after all files are parsed."""
        # Check undefined references
        for ref, file_path, line_num in self.refs:
            if ref not in self.labels:
                self.report.add_issue(ValidationIssue(
                    file_path=file_path, line_number=line_num,
                    severity="error", category="cross_reference",
                    message=f"Undefined reference: \\ref{{{ref}}}"
                ))

        # Check unreferenced labels
        referenced = {ref for ref, _, _ in self.refs}
        for label, (file_path, line_num) in self.labels.items():
            if label not in referenced:
                self.report.add_issue(ValidationIssue(
                    file_path=file_path, line_number=line_num,
                    severity="info", category="cross_reference",
                    message=f"Label '{label}' is defined but never referenced"
                ))

        # Check undefined citations
        if self.bib_entries:
            for cite_key, file_path, line_num in self.citations:
                if cite_key not in self.bib_entries:
                    self.report.add_issue(ValidationIssue(
                        file_path=file_path, line_number=line_num,
                        severity="error", category="bibliography",
                        message=f"Undefined citation: \\cite{{{cite_key}}}"
                    ))


def find_latex_files(base_dir: str) -> List[str]:
    """Find all .tex files in the directory."""
    tex_files = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".tex"):
                rel = os.path.relpath(os.path.join(root, f), base_dir)
                tex_files.append(rel)
    return sorted(tex_files)


def find_bib_files(base_dir: str) -> List[str]:
    """Find all .bib files in the directory."""
    bib_files = []
    for root, dirs, files in os.walk(base_dir):
        for f in files:
            if f.endswith(".bib"):
                rel = os.path.relpath(os.path.join(root, f), base_dir)
                bib_files.append(rel)
    return sorted(bib_files)


def print_report(report: ValidationReport) -> None:
    """Print formatted validation report."""
    print("\n" + "=" * 60)
    print("LATEX VALIDATION REPORT")
    print("=" * 60)
    print(f"Files checked: {report.files_checked}")
    print(f"Errors:   {report.total_errors}")
    print(f"Warnings: {report.total_warnings}")
    print(f"Info:     {report.total_info}")
    print()

    by_category = defaultdict(list)
    for issue in report.issues:
        by_category[issue.category].append(issue)

    for category, issues in sorted(by_category.items()):
        print(f"[{category}]")
        for issue in issues:
            icon = {"error": "E", "warning": "W", "info": "I"}.get(issue.severity, "?")
            loc = f"{issue.file_path}:{issue.line_number}" if issue.line_number else issue.file_path
            print(f"  [{icon}] {loc}: {issue.message}")
        print()


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Validate LaTeX documents")
    parser.add_argument("directory", nargs="?", default=".", help="Base directory to scan")
    parser.add_argument("--files", nargs="+", help="Specific .tex files to check")
    parser.add_argument("--strict", action="store_true", help="Treat warnings as errors")
    args = parser.parse_args()

    base_dir = os.path.abspath(args.directory)
    validator = LaTeXValidator(base_dir)

    if args.files:
        tex_files = args.files
    else:
        tex_files = find_latex_files(base_dir)

    if not tex_files:
        print("No .tex files found.")
        sys.exit(0)

    print(f"Validating {len(tex_files)} LaTeX file(s)...")
    for tf in tex_files:
        validator.validate_file(tf)

    bib_files = find_bib_files(base_dir)
    for bf in bib_files:
        validator.validate_bibliography(bf)

    validator.cross_validate()
    print_report(validator.report)

    if validator.report.total_errors > 0:
        sys.exit(1)
    if args.strict and validator.report.total_warnings > 0:
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
