"""内部方法引用完整性守护：组件经委托访问的 self.<name>() 必须在插件内存在。

插件各职责组件（OwnerDelegator）会把未定义属性委托给插件本体，
因此一旦出现 ``self._helper()`` 而项目里没有任何定义，运行期才会炸。
本测试用 AST 静态扫描提前发现这类问题。
"""

import ast
import pathlib
import unittest

PLUGIN_ROOT = pathlib.Path(__file__).resolve().parent.parent / "plugins.v2" / "cloudsubscribefork"

# 由外部基类提供、插件内不定义的成员（MP 插件基类 / 代理工具基类 / http.server）
EXTERNAL_MEMBERS = frozenset({
    "get_config",  # MoviePilot 插件基类
    "run_blocking",  # MoviePilot 代理工具基类
    "send_tool_message",  # MoviePilot 代理工具基类
    "send_response",  # http.server.BaseHTTPRequestHandler
    "send_header",  # http.server.BaseHTTPRequestHandler
    "end_headers",  # http.server.BaseHTTPRequestHandler
})


def iter_plugin_sources():
    for path in PLUGIN_ROOT.rglob("*.py"):
        if "__pycache__" in path.parts:
            continue
        yield path


def collect_defined_names() -> set:
    """收集项目中定义过的方法名与实例属性名。"""
    defined: set = set()
    for path in iter_plugin_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                defined.add(node.name)
                for decorator in node.decorator_list:
                    if isinstance(decorator, ast.Name):
                        defined.add(decorator.id)
            elif isinstance(node, ast.Assign):
                for target in node.targets:
                    if (
                            isinstance(target, ast.Attribute)
                            and isinstance(target.value, ast.Name)
                            and target.value.id == "self"
                    ):
                        defined.add(target.attr)
            elif isinstance(node, ast.AnnAssign):
                target = node.target
                if (
                        isinstance(target, ast.Attribute)
                        and isinstance(target.value, ast.Name)
                        and target.value.id == "self"
                ):
                    defined.add(target.attr)
            elif isinstance(node, ast.ClassDef):
                for statement in node.body:
                    if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        defined.add(statement.name)
    return defined


def collect_self_calls() -> dict:
    """收集 ``self.<name>()`` 直接调用（按文件聚合）。"""
    calls: dict = {}
    for path in iter_plugin_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            func = node.func
            if (
                    isinstance(func, ast.Attribute)
                    and isinstance(func.value, ast.Name)
                    and func.value.id == "self"
            ):
                calls.setdefault(func.attr, []).append(path.name)
    return calls


def is_property_accessor(node: ast.AST) -> bool:
    """属性 getter/setter/deleter 合法同名，不计入重复。"""
    for decorator in getattr(node, "decorator_list", []):
        if isinstance(decorator, ast.Attribute) and decorator.attr in {"setter", "getter", "deleter"}:
            return True
    return False


def collect_duplicate_methods() -> dict:
    """类内重复定义的方法（后者会静默覆盖前者，属于编辑事故）。"""
    duplicates: dict = {}
    for path in iter_plugin_sources():
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in tree.body:
            if not isinstance(node, ast.ClassDef):
                continue
            names = [
                statement.name
                for statement in node.body
                if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef))
                   and not is_property_accessor(statement)
            ]
            repeated = sorted({name for name in names if names.count(name) > 1})
            if repeated:
                duplicates[f"{path.name}:{node.name}"] = repeated
    return duplicates


class TestInternalMethodReferences(unittest.TestCase):
    def test_all_self_calls_are_defined(self):
        defined = collect_defined_names()
        missing = {
            name: sorted(set(files))
            for name, files in collect_self_calls().items()
            if name not in defined
               and name not in EXTERNAL_MEMBERS
               and not name.startswith("__")
        }
        self.assertEqual(missing, {}, f"存在未定义的内部方法引用：{missing}")

    def test_no_duplicate_method_definitions(self):
        duplicates = collect_duplicate_methods()
        self.assertEqual(duplicates, {}, f"存在类内重复方法定义：{duplicates}")


if __name__ == "__main__":
    unittest.main()
