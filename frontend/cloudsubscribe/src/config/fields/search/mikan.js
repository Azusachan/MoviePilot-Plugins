export function createMikanGroups() {
  return [{tab: "mikan", title: "蜜柑", icon: "mdi-magnet",
    hint: "公开搜索无需账号。按标题匹配磁力资源，复用订阅规则与115离线下载。",
    fields: [
      {key: "mikan_base_url", label: "服务地址", cols: 12},
      {key: "test_mikan", label: "测试搜索", type: "test-source", source: "mikan", cols: 12},
      {key: "mikan_result_limit", label: "候选上限", type: "number", min: 1, max: 200, cols: 4},
      {key: "mikan_request_interval", label: "请求间隔", type: "number", min: 1, max: 30, suffix: "秒", cols: 4},
      {key: "mikan_timeout", label: "请求超时", type: "number", min: 5, max: 60, suffix: "秒", cols: 4},
    ]}];
}
