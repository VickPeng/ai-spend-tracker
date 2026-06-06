"""
CollectorRegistry — 自动发现并注册所有可用的数据采集器。

发现路径：
1. ai_spend_tracker/collectors/ 下的 .py 文件 → 内置 collector（正常 import）
2. ~/.ai-spend/collectors/ 下的 .py 文件 → 用户自定义 collector（file import）
"""

from __future__ import annotations

import importlib
import importlib.util
import inspect
import sys
from pathlib import Path
from types import ModuleType
from typing import Optional

from ai_spend_tracker.collectors.base import BaseCollector


def _builtin_dir() -> Path:
    return Path(__file__).parent.resolve()


def _user_dir() -> Path:
    return Path.home() / ".ai-spend" / "collectors"


def _import_user_module(file_path: Path) -> Optional[ModuleType]:
    """从文件路径导入用户自定义模块。"""
    try:
        module_name = f"_custom_collector_{file_path.stem}"
        spec = importlib.util.spec_from_file_location(module_name, file_path)
        if spec is None or spec.loader is None:
            return None
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        return module
    except Exception:
        return None


def _find_collectors_in_module(
    module: ModuleType, base_module: str = ""
) -> list[BaseCollector]:
    """在模块中找出所有 BaseCollector 的非抽象子类实例。"""
    collectors: list[BaseCollector] = []
    for _name, obj in inspect.getmembers(module, inspect.isclass):
        if (
            issubclass(obj, BaseCollector)
            and obj is not BaseCollector
            and not inspect.isabstract(obj)
        ):
            try:
                collectors.append(obj())
            except Exception:
                continue
    return collectors


def get_all_collectors() -> list[BaseCollector]:
    """返回所有可用的采集器（内置 + 用户自定义）。"""
    collectors: list[BaseCollector] = []

    # 1. 内置 collector — 通过正常 import 发现
    builtin_dir = _builtin_dir()
    if builtin_dir.exists():
        for file_path in sorted(builtin_dir.iterdir()):
            if (
                not file_path.name.endswith(".py")
                or file_path.name == "__init__.py"
                or file_path.name == "base.py"
            ):
                continue
            module_name = f"ai_spend_tracker.collectors.{file_path.stem}"
            try:
                module = importlib.import_module(module_name)
                collectors.extend(_find_collectors_in_module(module))
            except Exception:
                continue

    # 2. 用户自定义 collector — 通过文件路径导入
    user_dir = _user_dir()
    if user_dir.exists():
        for file_path in sorted(user_dir.iterdir()):
            if (
                not file_path.name.endswith(".py")
                or file_path.name == "__init__.py"
            ):
                continue
            module = _import_user_module(file_path)
            if module:
                collectors.extend(_find_collectors_in_module(module))

    return collectors


def get_collector(name: str) -> Optional[BaseCollector]:
    for c in get_all_collectors():
        if c.name() == name:
            return c
    return None
