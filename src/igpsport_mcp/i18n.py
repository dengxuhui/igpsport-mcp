"""Minimal i18n: dict-based string catalogs for zh/en.

No external dependencies — a flat ``_CATALOG`` keyed by language code with
``str.format(**kwargs)`` interpolation for parameterised strings.
"""

from __future__ import annotations

from typing import Any

_SUPPORTED = frozenset({"zh", "en"})

_CATALOG: dict[str, dict[str, str]] = {
    "zh": {
        # ── CLI output (__main__.py) ──
        "unknown_args": "未知参数: {args}",
        "check_failed": "❌ 自检失败:{exc}",
        "check_failed_unexpected": "❌ 自检失败(未预期错误):{exc}",
        "check_success": "✅ 登录成功,凭证可用(账号 {username})。",
        # ── Setup wizard (config.py) ──
        "setup_banner": "\n🔧 igpsport-mcp 首次配置\n",
        "setup_desc": "需要你的 iGPSport 账号信息(仅保存在本地,不上传):\n",
        "setup_region_prompt": "  选择你的 iGPSport 账号区域:",
        "setup_region_option_cn": "    1. 国服 (app.igpsport.cn)           ← 中国区账号",
        "setup_region_option_intl": "    2. 国际版 (app.igpsport.com)        ← 全球区账号\n",
        "setup_region_input": "  请输入 1 或 2 (默认 1): ",
        "setup_username_prompt": "  手机号/邮箱: ",
        "setup_password_prompt": "  密码:        ",
        "setup_optional_hint": "\n  以下两项可直接回车跳过(不填自动从 iGPSport 读取):\n",
        "setup_ftp_prompt": "  FTP 功率阈值/瓦(1h 最大功率)(可选,回车跳过) [{default}]: ",
        "setup_lthr_prompt": "  LTHR 乳酸阈心率/bpm(可选,回车跳过) [{default}]: ",
        "setup_empty_credentials": "❌ 手机号和密码不能为空,配置未保存。请重新运行。",
        "setup_saved": "✅ 配置已保存到 {path}\n",
        "mcp_config_header": "📋 复制以下 JSON 到 Claude Desktop 的配置文件:",
        "mcp_config_path": "   路径: {path}\n",
        "mcp_config_add": '   在 "mcpServers" 中添加:',
        "mcp_config_tip_stored": "  💡 凭证已保存在本地 config.json,无需在 env 里重复填写。\n",
        "mcp_config_tip_cc": "  📖 Claude Code 用户也可用:",
        # ── Workout intensity labels (workout/ics.py) ──
        "intensity_warmup": "热身",
        "intensity_active": "主课",
        "intensity_rest": "休息",
        "intensity_cooldown": "放松",
        # ── Workout target labels (workout/ics.py) ──
        "target_power_zone": "功率区间",
        "target_power_custom": "功率",
        "target_power_percent_ftp": "%FTP",
        "target_hr_zone": "心率区间",
        "target_hr_custom": "心率",
        "target_cadence": "踏频",
        "target_speed": "速度",
        # ── Workout format strings (workout/ics.py) ──
        "workout_summary": "{title} · {n} 步 · 约 {m} 分钟",
        "repeat_times": "重复 {n} 次",
        "lap_button": "按圈键结束",
        "minute_unit": "{n} 分钟",
        "second_unit": "{n} 秒",
    },
    "en": {
        # ── CLI output ──
        "unknown_args": "Unknown arguments: {args}",
        "check_failed": "❌ Check failed: {exc}",
        "check_failed_unexpected": "❌ Check failed (unexpected error): {exc}",
        "check_success": "✅ Login successful, credentials valid (account {username}).",
        # ── Setup wizard ──
        "setup_banner": "\n🔧 igpsport-mcp First-Time Setup\n",
        "setup_desc": "Enter your iGPSport account details (local only, never uploaded):\n",
        "setup_region_prompt": "  Select your iGPSport account region:",
        "setup_region_option_cn": "    1. China (app.igpsport.cn)    ← Chinese accounts",
        "setup_region_option_intl": "    2. International (app.igpsport.com)  ← Global accounts\n",
        "setup_region_input": "  Enter 1 or 2 (default 1): ",
        "setup_username_prompt": "  Phone / Email: ",
        "setup_password_prompt": "  Password:      ",
        "setup_optional_hint": (
            "\n  Next two are optional (leave blank to auto-read from your iGPSport profile):\n"
        ),
        "setup_ftp_prompt": (
            "  FTP threshold / watts (1h max) (optional, Enter to skip) [{default}]: "
        ),
        "setup_lthr_prompt": (
            "  LTHR lactate threshold HR / bpm (optional, Enter to skip) [{default}]: "
        ),
        "setup_empty_credentials": (
            "❌ Phone/Email and password cannot be empty. Not saved. Re-run."
        ),
        "setup_saved": "✅ Config saved to {path}\n",
        "mcp_config_header": "📋 Copy the JSON below into your Claude Desktop config:",
        "mcp_config_path": "   Path: {path}\n",
        "mcp_config_add": '   Add under "mcpServers":',
        "mcp_config_tip_stored": (
            "  💡 Credentials stored in local config.json — no env vars needed.\n"
        ),
        "mcp_config_tip_cc": "  📖 Claude Code users can also use:",
        # ── Workout intensity labels ──
        "intensity_warmup": "Warmup",
        "intensity_active": "Main Set",
        "intensity_rest": "Rest",
        "intensity_cooldown": "Cooldown",
        # ── Workout target labels ──
        "target_power_zone": "Power Zone",
        "target_power_custom": "Power",
        "target_power_percent_ftp": "%FTP",
        "target_hr_zone": "HR Zone",
        "target_hr_custom": "HR",
        "target_cadence": "Cadence",
        "target_speed": "Speed",
        # ── Workout format strings ──
        "workout_summary": "{title} · {n} steps · ~{m} min",
        "repeat_times": "Repeat {n}x",
        "lap_button": "Lap button",
        "minute_unit": "{n} min",
        "second_unit": "{n} sec",
    },
}


def t(key: str, lang: str = "zh", **kwargs: Any) -> str:
    """Look up a translation by *key* in *lang*, formatting with *kwargs*.

    Falls back to the ``zh`` catalog for missing keys so a missing English
    entry never crashes the application.
    """
    catalog = _CATALOG.get(lang, _CATALOG["zh"])
    template = catalog.get(key)
    if template is None:
        template = _CATALOG["zh"].get(key, key)
    if kwargs:
        return template.format(**kwargs)
    return template


def supported(lang: str) -> bool:
    """Return ``True`` if *lang* is a supported locale code."""
    return lang in _SUPPORTED
