export function createMikanGroups() {
  return [{tab: "mikan", title: "蜜柑", icon: "mdi-magnet",
    hint: "公开搜索无需账号。仅接受标注中文字幕及字幕组的资源；排除无字幕与仅压制组资源。偏好：SweetSub/千夏/拨雪/喵萌 → 诸神/澄空/华盟/北宇治/霜庭 → 桜都/豌豆/动漫国/极影 → 其他明确字幕组。同梯队不分先后。",
    fields: [
      {key: "mikan_base_url", label: "服务地址", cols: 12},
      {key: "test_mikan", label: "测试搜索", type: "test-source", source: "mikan", cols: 12},
      {key: "mikan_result_limit", label: "候选上限", type: "number", min: 1, max: 200, cols: 4},
      {key: "mikan_request_interval", label: "请求间隔", type: "number", min: 1, max: 30, suffix: "秒", cols: 4},
      {key: "mikan_timeout", label: "请求超时", type: "number", min: 5, max: 60, suffix: "秒", cols: 4},
    ]}];
}
