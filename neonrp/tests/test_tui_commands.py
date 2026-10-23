"""Tests for TUI command parser."""

from neonrp.tui.commands import (
    parse_command,
    validate_command,
    get_command_suggestions,
    get_command_args_hint,
    format_help,
    COMMANDS,
)


class TestParseCommand:
    """Tests for parse_command function."""

    def test_parse_simple_command(self):
        """Parse simple command without args."""
        result = parse_command(":validate")
        assert result.command == "validate"
        assert result.args == []
        assert result.options == {}
        assert result.error is None

    def test_parse_without_colon(self):
        """Parse command without leading colon."""
        result = parse_command("validate")
        assert result.command == "validate"
        assert result.error is None

    def test_parse_with_args(self):
        """Parse command with positional args."""
        result = parse_command(":index build")
        assert result.command == "index"
        assert result.args == ["build"]

    def test_parse_find_with_keyword(self):
        """Parse find command with keyword."""
        result = parse_command(":find tokyo")
        assert result.command == "find"
        assert result.args == ["tokyo"]

    def test_parse_sandbox_new_with_options(self):
        """Parse sandbox new with --from option."""
        result = parse_command(":sandbox new test-1 --from save_001")
        assert result.command == "sandbox"
        assert result.args == ["new", "test-1"]
        assert result.options == {"from": "save_001"}

    def test_parse_context_with_limit(self):
        """Parse context with --limit option."""
        result = parse_command(":context player --limit 5")
        assert result.command == "context"
        assert result.args == ["player"]
        assert result.options == {"limit": "5"}

    def test_parse_empty_command(self):
        """Parse empty command returns error."""
        result = parse_command(":")
        assert result.error == "Empty command"

    def test_parse_quoted_args(self):
        """Parse command with quoted arguments."""
        result = parse_command(':find "multi word query"')
        assert result.command == "find"
        assert result.args == ["multi word query"]

    def test_parse_short_option(self):
        """Parse command with short option."""
        result = parse_command(":context query -n 10")
        assert result.command == "context"
        assert result.args == ["query"]
        assert result.options == {"n": "10"}

    def test_parse_flag_option(self):
        """Parse command with flag (no value) option."""
        result = parse_command(":agent run test --json")
        assert result.command == "agent"
        assert result.args == ["run", "test"]
        assert result.options == {"json": "true"}


class TestValidateCommand:
    """Tests for validate_command function."""

    def test_validate_known_command(self):
        """Known commands should validate."""
        result = parse_command(":validate")
        assert validate_command(result) is None

    def test_validate_continue_command(self):
        """/continue was deleted: it says where its job went."""
        err = validate_command(parse_command("/continue"))
        assert "已删除" in err and "/open" in err

    def test_validate_cast_command(self):
        """迎入角色的命令统一叫 cast(与其他项目一致,
        而且 new 读起来更像 create,两个词太近会糊掉「造 / 迎」的分界)。"""
        result = parse_command("/cast")
        assert validate_command(result) is None

    def test_new_is_not_a_command(self):
        """`/new` 已撤(统一叫 cast)。

        这条是守卫:改名时我曾因为一次 `git checkout` 把命令表那半还原掉,
        而 app.py 那半已经不路由 `new` —— 于是 `/new` 会被当成已知命令、
        掉进 CLI 透传。整轮测试都没抓到,因为没人断言过它**不该存在**。
        """
        error = validate_command(parse_command("/new"))
        assert error and "Unknown command" in error

    def test_retired_commands_are_gone(self):
        """sandbox 那一族与 router-mode 的概念已死,不该还能被解析成已知命令。

        sandbox 沉为引擎内部的子 agent 干跑;router-mode 的参数里还留着退役的
        fast,而执行形态由世界结构决定,不是运行时开关。"""
        for name in ("sandbox", "apply", "autoapply", "router-mode"):
            error = validate_command(parse_command(f"/{name}"))
            assert error and "Unknown command" in error, name

    def test_validate_verbose_command(self):
        """Verbose command should be treated as known."""
        result = parse_command("/verbose")
        assert validate_command(result) is None

    def test_validate_models_command(self):
        """/models was deleted: /settings."""
        assert "/settings" in validate_command(parse_command("/models"))

    def test_validate_import_command(self):
        """新形状(直接给文件)与老形状(带子命令)都得受理。"""
        assert validate_command(parse_command("/import hero.png")) is None
        assert validate_command(parse_command('/import sillytavern-card "card.png"')) is None

    def test_validate_unknown_command(self):
        """Unknown commands should return error."""
        result = parse_command(":foobar")
        error = validate_command(result)
        assert "Unknown command" in error

    def test_validate_unknown_with_suggestion(self):
        """Unknown command similar to known should suggest."""
        result = parse_command(":cas")
        error = validate_command(result)
        assert "cast" in error.lower()

    def test_validate_subcommand_required(self):
        """Commands requiring subcommand should validate."""
        result = parse_command(":mcp")
        error = validate_command(result)
        assert "requires a subcommand" in error

    def test_validate_invalid_subcommand(self):
        """Invalid subcommand should return error."""
        result = parse_command(":mcp foobar")
        error = validate_command(result)
        assert "Unknown subcommand" in error

    def test_validate_valid_subcommand(self):
        """Valid subcommand should pass."""
        result = parse_command(":mcp status")
        assert validate_command(result) is None


class TestGetCommandSuggestions:
    """Tests for get_command_suggestions function."""

    def test_empty_prefix_returns_all(self):
        """Empty prefix returns all commands."""
        suggestions = get_command_suggestions("")
        assert len(suggestions) == len(COMMANDS)

    def test_prefix_filters_commands(self):
        """Prefix filters to matching commands."""
        suggestions = get_command_suggestions("cre")
        assert "create" in suggestions

    def test_no_match_returns_empty(self):
        """Non-matching prefix returns empty list."""
        suggestions = get_command_suggestions("xyz")
        assert suggestions == []


class TestFormatHelp:
    """Tests for format_help function."""

    def test_format_help_includes_commands(self):
        """Help text includes all commands."""
        help_text = format_help()
        assert "create" in help_text
        assert "mode" in help_text
        assert "find" in help_text
        assert "cast" in help_text


class TestCommandPlaceholders:
    """Tests for command argument placeholder hints."""

    def test_mode_placeholder_is_explicit_choices(self):
        """Mode shows concrete choices — and only the player-facing two.

        M31: sandbox is engine-internal plumbing (sub-agents dry-running
        proposals), not a mode anyone switches into, so it left the
        advertised surface. It still parses; see
        ``test_mode_command_still_accepts_sandbox``.
        """
        assert get_command_args_hint("mode", COMMANDS["mode"]) == "[build|play]"

    def test_mode_command_still_accepts_sandbox(self):
        """Un-advertising sandbox must not make it unparseable."""
        parsed = parse_command("/mode sandbox")
        assert parsed.command == "mode"
        assert parsed.args == ["sandbox"]
        assert parsed.error is None

    def test_archived_command_keeps_its_subcommand_hint(self):
        """归档不等于降级:退役命令的规格仍然完整(敲出来照样能用)。"""
        from neonrp.tui.legacy_commands import LEGACY_COMMANDS

        assert get_command_args_hint("mcp", LEGACY_COMMANDS["mcp"]) == "[status|restart]"

    def test_import_placeholder_asks_for_a_file(self):
        """`/import` 合并成一个入口后,提示词该问「哪个文件」而不是「哪一类」
        —— 分类是我们的活。子命令仍受理,见
        tests/test_import_dispatch.py::test_legacy_subcommand_still_opens。"""
        assert get_command_args_hint("import", COMMANDS["import"]) == "<文件>"

    def test_all_argument_commands_have_non_empty_placeholder(self):
        """Every command that accepts arguments should provide a placeholder."""
        for cmd, spec in COMMANDS.items():
            needs_hint = ("subcommands" in spec) or spec.get("args") in {1, "?"}
            if not needs_hint:
                continue
            hint = get_command_args_hint(cmd, spec)
            assert isinstance(hint, str)
            assert hint.strip() != ""


# ── issue 回归(v0.2.15 bug report 审定后落地的三件套)────────────────────


def test_tool_summary_non_dict_params_no_crash():
    # 真凶回归:params 为 list 时(LLM 偶发形状)不得 AttributeError 崩 TUI
    # ('list' object has no attribute 'get',回滚重放渲染历史消息时触发)。
    from neonrp.tui.app import ConversationView

    assert ConversationView._tool_summary("read_file", ["not", "a", "dict"]) == "read_file"
    assert ConversationView._tool_summary("ask_user", "oops") == "ask_user"
    assert ConversationView._tool_summary("", None) == "tool"


def test_ask_user_questions_json_string_decoded():
    # 显示丢失回归:questions 被 LLM 双重编码成 JSON 字符串 → 防御性解一层。
    import json as _json

    from neonrp.tui.app import ConversationView

    payload = {"questions": _json.dumps([{"question": "去哪?", "options": []}])}
    assert ConversationView._extract_ask_user_question(payload) == "去哪?"


class TestLegacyArchive:
    """退役命令归档到一处(「可以 archive,并且打包整理到
    一个内容,方便以后删除」)。

    「归档」不是「删除」也不是「隐藏」——它有三个可验的性质:能力还在、
    不占补全、集中在一个文件。少任何一条这件事就白做了:能力没了是删,
    还在补全里是没整理,散在各处是将来删不动。
    """

    def test_retired_commands_still_execute(self):
        """能力保留:排障与集成的那几条(定留 validate / mcp / bridge / debug·verbose / stats / config)。"""
        for line in ("/validate", "/mcp status", "/bridge", "/debug", "/verbose on", "/stats", "/config"):
            assert validate_command(parse_command(line)) is None, line

    def test_retired_commands_stay_out_of_the_bare_list_but_answer_to_a_prefix(self):
        """不占心智带宽:裸 / 只读主表。补一条:敲了前缀就得
        出现(灰显、标「已归档」),不然「/auth 不在 suggestion 里」。"""
        from neonrp.tui.commands import command_kind
        from neonrp.tui.legacy_commands import LEGACY_COMMANDS

        bare = get_command_suggestions("")
        for name in LEGACY_COMMANDS:
            assert name not in COMMANDS, name
            assert name not in bare, name
            assert name in get_command_suggestions(name), name
            assert command_kind(name) == "legacy"

    def test_help_only_advertises_live_commands(self):
        help_text = format_help()
        assert "cast" in help_text
        assert "/validate" not in help_text  # only as a /dev sub-item
        assert "worlds" not in help_text

    def test_live_table_is_small(self):
        """48 → 十几条。数字本身就是这次设计的成果,掉回去应该被抓住。"""
        live = [k for k in COMMANDS if not k.startswith("_")]
        assert len(live) <= 25, f"命令面又长回去了:{sorted(live)}"  # ≤ 25

    def test_every_archived_command_says_why(self):
        """将来删它的人需要知道当初为什么留、现在为什么能删。"""
        from neonrp.tui.legacy_commands import LEGACY_COMMANDS

        for name, spec in LEGACY_COMMANDS.items():
            assert spec.get("why"), name

    def test_archive_and_deletion_are_different_things(self):
        """归档的仍可用;真删掉的必须报未知 —— 两者不能混。"""
        assert validate_command(parse_command("/validate")) is None
        for deleted in ("sandbox", "apply", "autoapply", "router-mode", "new"):
            error = validate_command(parse_command(f"/{deleted}"))
            assert error and "Unknown command" in error, deleted

    def test_unknown_is_still_unknown(self):
        """回落不能把任何乱敲都变成合法命令。"""
        error = validate_command(parse_command("/foobarbaz"))
        assert error and "Unknown command" in error
