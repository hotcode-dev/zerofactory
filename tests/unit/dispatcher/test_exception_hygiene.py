"""AST guards against unreachable or duplicate exception handlers in dispatcher."""

import ast
from pathlib import Path


def _get_dispatcher_trees():
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    dispatcher_dir = repo_root / "dispatcher"
    trees = []
    for py_file in dispatcher_dir.glob("*.py"):
        trees.append((py_file.name, ast.parse(py_file.read_text(encoding="utf-8"), filename=str(py_file))))
    return trees


def _handler_type_name(handler):
    t = handler.type
    if t is None:
        return "None"
    if isinstance(t, ast.Name):
        return t.id
    if isinstance(t, (ast.Tuple, ast.List)):
        return ",".join(e.id if isinstance(e, ast.Name) else repr(e) for e in t.elts)
    return repr(t)


def test_no_duplicate_exception_handler_types_in_dispatcher():
    """No try-block in dispatcher/*.py may repeat an exception-handler type."""
    duplicates = []
    for fname, tree in _get_dispatcher_trees():
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            seen = set()
            for handler in node.handlers:
                tname = _handler_type_name(handler)
                if tname in seen:
                    duplicates.append(
                        f"{fname}:{node.lineno} try-block has duplicate 'except {tname}' handler (line {handler.lineno})"
                    )
                seen.add(tname)
    assert duplicates == [], "\n".join(duplicates)


def test_no_orphaned_reviewer_pr_check_skip_in_commit_pr_block():
    """The author commit/PR try-block must not contain an orphaned 'Reviewer PR check skipped' log."""
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    scheduler_path = repo_root / "dispatcher" / "scheduler.py"
    lines = scheduler_path.read_text(encoding="utf-8").splitlines()

    commit_pr_generic_line = None
    for i, ln in enumerate(lines):
        if "_log.warning(\"Task %s commit/PR failed:" in ln or "commit/PR failed:" in ln:
            commit_pr_generic_line = i
            break

    if commit_pr_generic_line is not None:
        except_indent = len(lines[commit_pr_generic_line]) - len(lines[commit_pr_generic_line].lstrip())
        block_end = commit_pr_generic_line
        for i in range(commit_pr_generic_line + 1, len(lines)):
            ln = lines[i]
            if ln.strip() == "":
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= except_indent and ln.lstrip().startswith(("except ",)):
                block_end = i
            elif indent < except_indent:
                break
            else:
                block_end = i
        tail = "\n".join(lines[commit_pr_generic_line : block_end + 1])
        assert "Reviewer PR check skipped" not in tail
