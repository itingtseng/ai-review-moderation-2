
#!/usr/bin/env python3
import sys
import json
from pathlib import Path
from typing import List, Dict, Tuple, Any
import ast
from dataclasses import dataclass

try:
    import nbformat  # type: ignore
    HAS_NBFORMAT = True
except Exception:
    HAS_NBFORMAT = False

@dataclass
class DefInfo:
    name: str
    file: str
    cell_index: int  # -1 for .py files
    line_in_cell: int  # 1-based within cell (or file for .py)
    abs_line: int  # absolute line in file (for .py) or approximated across cells
    args: str

def parse_args(func: ast.FunctionDef) -> str:
    # Build a compact signature string
    args = []
    for a in func.args.args:
        args.append(a.arg)
    if func.args.vararg:
        args.append("*" + func.args.vararg.arg)
    for a in func.args.kwonlyargs:
        args.append(a.arg + "=")
    if func.args.kwarg:
        args.append("**" + func.args.kwarg.arg)
    return "(" + ", ".join(args) + ")"

def scan_python_source(text: str, file: str, cell_index: int, base_line: int) -> List[DefInfo]:
    items: List[DefInfo] = []
    try:
        tree = ast.parse(text)
    except SyntaxError:
        return items
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            items.append(
                DefInfo(
                    name=node.name,
                    file=file,
                    cell_index=cell_index,
                    line_in_cell=getattr(node, "lineno", 1),
                    abs_line=base_line + getattr(node, "lineno", 1) - 1,
                    args=parse_args(node),
                )
            )
    return items

def load_ipynb_code(path: Path) -> List[Tuple[int, str]]:
    """Return list of (cell_index, source) for code cells."""
    cells = []
    if HAS_NBFORMAT:
        nb = nbformat.read(path, as_version=4)  # type: ignore
        for i, cell in enumerate(nb.cells):
            if cell.get("cell_type") == "code":
                src = cell.get("source") or ""
                cells.append((i, src if isinstance(src, str) else "\n".join(src)))
    else:
        # Fallback raw JSON parsing
        data = json.loads(path.read_text(encoding="utf-8"))
        for i, cell in enumerate(data.get("cells", [])):
            if cell.get("cell_type") == "code":
                src = cell.get("source") or []
                if isinstance(src, list):
                    src = "".join(src)
                cells.append((i, src))
    return cells

def scan_file(path_str: str) -> List[DefInfo]:
    path = Path(path_str)
    if not path.exists():
        print(f"[ERROR] File not found: {path}")
        return []
    if path.suffix == ".py":
        text = path.read_text(encoding="utf-8", errors="ignore")
        return scan_python_source(text, str(path), cell_index=-1, base_line=1)
    elif path.suffix == ".ipynb":
        # Build an approximate absolute line number by summing previous cell lengths
        defs: List[DefInfo] = []
        running_line = 1
        for idx, src in load_ipynb_code(path):
            items = scan_python_source(src, str(path), cell_index=idx, base_line=running_line)
            defs.extend(items)
            running_line += src.count("\n") + 1
        return defs
    else:
        print(f"[ERROR] Unsupported file type: {path.suffix}. Use .py or .ipynb")
        return []

def group_by_name(defs: List[DefInfo]) -> Dict[str, List[DefInfo]]:
    d: Dict[str, List[DefInfo]] = {}
    for info in defs:
        d.setdefault(info.name, []).append(info)
    return d

def main():
    if len(sys.argv) < 2:
        print("Usage: python find_duplicate_defs.py <file1.[py|ipynb]> [<file2.[py|ipynb]> ...]")
        sys.exit(1)

    all_defs: List[DefInfo] = []
    for p in sys.argv[1:]:
        all_defs.extend(scan_file(p))

    if not all_defs:
        print("No function definitions found.")
        sys.exit(0)

    grouped = group_by_name(all_defs)

    # Report
    print("=== Function definitions report ===")
    print(f"Total defs found: {len(all_defs)}")
    unique = len(grouped.keys())
    print(f"Unique function names: {unique}")
    dup_names = [k for k, v in grouped.items() if len(v) > 1]
    print(f"Functions with duplicates: {len(dup_names)}")
    if dup_names:
        print("\n--- Duplicates ---")
        for name in sorted(dup_names):
            entries = sorted(grouped[name], key=lambda x: (x.file, x.cell_index, x.abs_line))
            print(f"\n{name}  (count={len(entries)})")
            for e in entries:
                loc = f"cell #{e.cell_index}" if e.cell_index >= 0 else "file"
                print(f"  - {Path(e.file).name}:{e.abs_line}  [{loc} line {e.line_in_cell}]  signature: {e.name}{e.args}")
    else:
        print("\nNo duplicates found ✅")

    # Tip: write a CSV of all defs
    out_csv = Path("defs_index.csv")
    try:
        import csv  # always available
        with out_csv.open("w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "file", "cell_index", "line_in_cell", "abs_line", "signature"])
            for e in sorted(all_defs, key=lambda x: (x.file, x.cell_index, x.abs_line)):
                writer.writerow([e.name, e.file, e.cell_index, e.line_in_cell, e.abs_line, f"{e.name}{e.args}"])
        print(f"\nCSV index written to: {out_csv.resolve()}")
    except Exception as ex:
        print(f"[WARN] Failed to write CSV: {ex}")

if __name__ == "__main__":
    main()
