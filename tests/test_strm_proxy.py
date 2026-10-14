"""STRM 播放代理契约测试：短链解析、标识短链、302 与错误码。

代理只由插件自有监听端口提供（短链 ``/d/<标识>?/<文件名>``），不依赖平台路由，
因此这里直接对传输无关的 ``handle_request`` 与 ``short_params`` 做断言。
"""

import unittest
from types import SimpleNamespace

from plugin_env import (
    OwnerDelegator,
    install_app_mocks,
    load_module,
    register_mock,
    register_package,
)

install_app_mocks("app.log")
register_mock("cloudsubscribefork")
_cloud = load_module(
    "cloudsubscribefork.core.cloud",
    "plugins.v2/cloudsubscribefork/core/cloud.py",
)
register_package(
    "cloudsubscribefork.core",
    OwnerDelegator=OwnerDelegator,
    CloudDriveCapability=_cloud.CloudDriveCapability,
    CloudFile=_cloud.CloudFile,
)
register_package("cloudsubscribefork.utils")
_strm = load_module(
    "cloudsubscribefork.utils.strm",
    "plugins.v2/cloudsubscribefork/utils/strm.py",
)
register_package("cloudsubscribefork.core.api")
_proxy = load_module(
    "cloudsubscribefork.core.api.strm_proxy",
    "plugins.v2/cloudsubscribefork/core/api/strm_proxy.py",
)

StrmProxyApi = _proxy.StrmProxyApi
StrmProxyServer = _proxy.StrmProxyServer
StrmGenerator = _strm.StrmGenerator
CloudDriveCapability = _cloud.CloudDriveCapability
CloudFile = _cloud.CloudFile


class StubDrive:
    """只提供直链解析与播放标识声明的网盘替身。"""

    def __init__(self, url="http://cdn.example.com/a.mkv", error=None,
                 playback_variables=("pickcode",), proxy_identifier="pickcode"):
        self.url = url
        self.error = error
        self.playback = SimpleNamespace(
            template_variables=frozenset(playback_variables),
            proxy_identifier=proxy_identifier,
        )
        self.resolved = []

    def supports(self, capability):
        return capability in {
            CloudDriveCapability.FILE_DOWNLOAD,
            CloudDriveCapability.PLAYBACK_REFERENCE,
        }

    def require(self, capability):
        if capability == CloudDriveCapability.PLAYBACK_REFERENCE:
            return self.playback
        return self

    def resolve_download_link(self, file_item):
        self.resolved.append(file_item)
        if self.error:
            raise RuntimeError(self.error)
        return self.url, {}


def build_api(config=None, drive=None):
    owner = SimpleNamespace(
        _applied_config=config if config is not None else {"strm_proxy_enabled": True},
        _cloud_drive=drive if drive is not None else StubDrive(),
    )
    return StrmProxyApi(owner)


class TestStrmProxyContract(unittest.TestCase):
    """代理核心：启用开关、能力校验、302 语义与错误码。"""

    def test_disabled_returns_503(self):
        api = build_api(config={"strm_proxy_enabled": False})
        result = api.handle_request({"pickcode": "abc"})
        self.assertEqual(result.status_code, 503)

    def test_missing_download_capability_returns_503(self):
        api = build_api(drive=SimpleNamespace(supports=lambda capability: False))
        self.assertEqual(api.handle_request({"pickcode": "abc"}).status_code, 503)

    def test_missing_identifier_returns_404(self):
        api = build_api()
        self.assertEqual(api.handle_request({"name": "movie.mkv"}).status_code, 404)

    def test_resolve_failure_returns_502(self):
        api = build_api(drive=StubDrive(error="boom"))
        self.assertEqual(api.handle_request({"pickcode": "abc"}).status_code, 502)

    def test_redirect_contract(self):
        """按网盘标识短链解析出直链，并给出 302 与中文文件名下载头。"""
        drive = StubDrive(url="https://cdn.example.com/%E5%85%B0.mkv?sign=abc")
        api = build_api(drive=drive)

        result = api.handle_request({"pickcode": "abcdefghijklmnopq", "name": "兰香如故.S01E01.mkv"})

        self.assertEqual(result.status_code, 302)
        self.assertEqual(
            result.headers["Location"], "https://cdn.example.com/%E5%85%B0.mkv?sign=abc"
        )
        self.assertIn("filename*=UTF-8''", result.headers["Content-Disposition"])
        self.assertEqual(
            drive.resolved[0].playback_values, {"pickcode": "abcdefghijklmnopq"}
        )

    def test_head_returns_headers_without_body(self):
        api = build_api()
        result = api.handle_request({"pickcode": "abc", "name": "x.mkv"}, "HEAD")
        self.assertEqual(result.status_code, 302)
        self.assertEqual(result.body, b"")
        self.assertIn("Location", result.headers)

    def test_file_id_identifier_for_other_drives(self):
        """夸克/光雅等按 file_id 取链的网盘同样只依赖标识。"""
        drive = StubDrive(playback_variables=("file_id",), proxy_identifier="file_id")
        api = build_api(drive=drive)
        result = api.handle_request({"file_id": "abc123", "name": "movie.mkv"})
        self.assertEqual(result.status_code, 302)
        self.assertEqual(drive.resolved[0].id, "abc123")

    def test_unsupported_drive_ignores_path_params(self):
        """无标识能力的网盘（如 123）不提供短链代理，也不回退路径模式。"""
        drive = StubDrive(proxy_identifier="", playback_variables=("md5",))
        api = build_api(drive=drive)
        result = api.handle_request({"path": "/a/x.mkv", "name": "x.mkv"})
        self.assertEqual(result.status_code, 404)


class TestPortCheck(unittest.TestCase):
    """端口占用检测：空闲端口可用、被占用端口给出原因。"""

    def test_free_port_is_available(self):
        import socket as socket_module

        with socket_module.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            free_port = probe.getsockname()[1]
        result = _proxy.check_port(free_port)
        self.assertTrue(result["available"])

    def test_occupied_port_reports_unavailable(self):
        import socket as socket_module

        holder = socket_module.socket()
        holder.bind(("0.0.0.0", 0))
        holder.listen(1)
        try:
            busy_port = holder.getsockname()[1]
            result = _proxy.check_port(busy_port)
            self.assertFalse(result["available"])
            self.assertTrue(result["error"])
        finally:
            holder.close()

    def test_invalid_port(self):
        self.assertFalse(_proxy.check_port(0)["available"])
        self.assertFalse(_proxy.check_port(70000)["available"])


class TestShortLinkParsing(unittest.TestCase):
    """短链解析：/d/<标识> 与 CloudDrive2 风格 ?/<文件名>。"""

    def test_short_path_maps_identifier(self):
        api = build_api()
        self.assertEqual(
            api.short_params("/d/abcdefghijklmnopq", {}),
            {"pickcode": "abcdefghijklmnopq"},
        )

    def test_clouddrive_style_query_name(self):
        api = build_api()
        params = api.short_params("/d/abcdefghijklmnopq", {"/剧集.S01E01.mkv": ""})
        self.assertEqual(params["pickcode"], "abcdefghijklmnopq")
        self.assertEqual(params["name"], "剧集.S01E01.mkv")

    def test_plain_query_keeps_name(self):
        api = build_api()
        params = api.short_params("/d/abc", {"name": "movie.mkv"})
        self.assertEqual(params, {"name": "movie.mkv", "pickcode": "abc"})

    def test_end_to_end_short_link(self):
        """短链解析 + 解析直链一体化：等价于监听端口收到的请求。"""
        drive = StubDrive()
        api = build_api(drive=drive)
        params = api.short_params("/d/cg04ctinkn3aidbzc", {"/示例.S01E01.mkv": ""})
        result = api.handle_request(params)
        self.assertEqual(result.status_code, 302)
        self.assertEqual(drive.resolved[0].playback_values, {"pickcode": "cg04ctinkn3aidbzc"})


class TestProxyTemplateSelection(unittest.TestCase):
    """代理短链模板：仅 /d/<标识>?/<文件名>，无标识则不提供。"""

    def test_declared_identifier_wins(self):
        self.assertEqual(
            StrmGenerator.proxy_identifier_variable(
                SimpleNamespace(proxy_identifier="file_id", template_variables=frozenset({"md5"}))
            ),
            "file_id",
        )
        self.assertEqual(
            StrmGenerator.proxy_identifier_variable(
                SimpleNamespace(proxy_identifier="", template_variables=frozenset({"file_id", "md5"}))
            ),
            "file_id",
        )

    def test_identifier_fallback_by_variables(self):
        self.assertEqual(
            StrmGenerator.proxy_identifier_variable(None, {"pickcode", "file_id"}), "pickcode"
        )
        self.assertEqual(StrmGenerator.proxy_identifier_variable(None, {"md5"}), "")

    def test_short_template_only_form(self):
        _, template = StrmGenerator.build_proxy_template("http://mp:9527/", "pickcode")
        self.assertEqual(template, "{base_url}/d/{pickcode}?/{file_name}")
        _, unsupported = StrmGenerator.build_proxy_template("http://mp:9527", "")
        self.assertEqual(unsupported, "")

    def test_custom_route_segment(self):
        """路由可自定义：任意单段安全前缀都可用于短链模板与解析。"""
        _, template = StrmGenerator.build_proxy_template("http://mp:9527", "file_id", "strm")
        self.assertEqual(template, "{base_url}/strm/{file_id}?/{file_name}")
        api = build_api(config={"strm_proxy_enabled": True, "strm_proxy_route": "strm"})
        api._owner._cloud_drive = StubDrive(
            playback_variables=("file_id",), proxy_identifier="file_id"
        )
        params = api.short_params("/strm/abc123", {"/movie.mkv": ""})
        self.assertEqual(params["file_id"], "abc123")
        self.assertEqual(params["name"], "movie.mkv")

    def test_route_segment_sanitized(self):
        """非法路由（多段/特殊字符）回退默认 d，避免路径穿越。"""
        self.assertEqual(StrmGenerator.proxy_route_segment("../etc"), "etc")
        self.assertEqual(StrmGenerator.proxy_route_segment(""), "d")
        self.assertEqual(StrmGenerator.proxy_route_segment("a/b"), "b")

    def test_base_url_normalized(self):
        base, _ = StrmGenerator.build_proxy_template("http://mp:9527/", "pickcode")
        self.assertEqual(base, "http://mp:9527")


class TestSharedPlaybackReference(unittest.TestCase):
    """以文件 ID 取链的网盘播放引用（阿里云盘/天翼云盘/移动云盘共用）。"""

    @classmethod
    def setUpClass(cls):
        register_mock("app.core")
        register_mock("app.core.cache")
        register_mock("app.utils")
        register_mock("app.utils.string")
        register_mock("app.log")
        register_mock("cloudsubscribefork.utils.cache")
        register_mock("cloudsubscribefork.drive")
        cls.common = load_module(
            "cloudsubscribefork.drive.common",
            "plugins.v2/cloudsubscribefork/drive/common.py",
        )

    def test_variables_and_identifier(self):
        reference = self.common.FileIdPlaybackReference()
        self.assertEqual(reference.template_variables, frozenset({"file_id"}))
        self.assertEqual(reference.proxy_identifier, "file_id")

    def test_reference_values_fall_back_to_file_id(self):
        file_item = CloudFile(id="fid-1", name="movie.mkv", is_directory=False)
        values = dict(self.common.FileIdPlaybackReference().reference_values(file_item))
        self.assertEqual(values, {"file_id": "fid-1"})


if __name__ == "__main__":
    unittest.main()
