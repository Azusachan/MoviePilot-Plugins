<template>
  <div class="region-media-map-field">
    <div v-if="field.hint" class="text-caption text-medium-emphasis mb-2">{{ field.hint }}</div>
    <v-text-field
      :model-value="summary"
      :label="field.label"
      readonly
      density="compact"
      variant="outlined"
      hide-details="auto"
      append-inner-icon="mdi-chevron-down"
      class="cursor-pointer"
      @click="dialogVisible = true" />

    <!-- 主配置弹窗 -->
    <v-dialog v-model="dialogVisible" max-width="560" scrollable>
      <v-card class="compact-config-dialog rounded-xl">
        <!-- 头部导航 -->
        <div class="dialog-header d-flex align-center px-4 py-3">
          <div class="dialog-header-icon mr-2">
            <v-icon :icon="field.icon || (isListMode ? 'mdi-sort-ascending' : 'mdi-view-grid-plus-outline')" size="18"
                    color="primary" />
          </div>
          <div>
            <div class="dialog-header-title">{{ field.label }}</div>
            <div class="dialog-header-subtitle text-caption text-medium-emphasis">
              {{ isListMode ? (isFansubMode ? "按优先级自上而下排列（首位最高优先），支持编辑规则与调序" : "按优先级自上而下排列（首位最高优先），支持拖拽或上下按钮调序") : "按平台选择要监听的媒体类型"
              }}
            </div>
          </div>
          <v-spacer />
          <v-chip size="small" variant="tonal" color="primary" class="font-weight-medium px-2 mr-1">
            已配置 {{ currentCount }} 项
          </v-chip>
          <v-btn icon="mdi-close" variant="text" size="small" class="dialog-close-btn ml-1"
                 title="关闭" @click="dialogVisible = false" />
        </div>

        <v-divider />

        <v-card-text class="pt-3 pb-2 px-4">
          <!-- 模式一：纯优先级列表模式 (List Mode - 字幕组/搜索源) -->
          <div v-if="isListMode">
            <!-- 顶部添加工具栏：从预设快速添加 + 自定义新建弹窗按钮（仅字幕组支持自定义规则） -->
            <div class="d-flex align-center ga-2 mb-3">
              <v-select
                v-model="presetSelected"
                :items="unselectedOptions"
                :placeholder="presetPlaceholder"
                item-title="title"
                return-object
                density="compact"
                variant="outlined"
                hide-details
                clearable
                class="flex-grow-1"
                prepend-inner-icon="mdi-bookmark-outline"
                @update:model-value="onPresetSelect" />

              <v-btn
                v-if="isFansubMode"
                color="primary"
                variant="tonal"
                size="small"
                class="px-3"
                height="40"
                prepend-icon="mdi-plus"
                @click="openAddDialog">
                新建规则
              </v-btn>
            </div>

            <!-- 空状态 -->
            <div v-if="rulesList.length === 0" class="text-center py-8 text-medium-emphasis">
              <v-icon icon="mdi-tray-remove" size="36" class="mb-2 opacity-40" />
              <div class="text-caption">{{ emptyHint }}</div>
            </div>

            <!-- 紧凑独立的优先级滚动列表 -->
            <div v-else class="priority-list-container">
              <div
                v-for="(item, index) in rulesList"
                :key="item.title + index"
                draggable="true"
                class="priority-item-row"
                :class="{
                  'priority-item--dragging': draggingIndex === index,
                  'priority-item--dragover': dragOverIndex === index,
                }"
                @dragstart="onDragStart(index, $event)"
                @dragover="onDragOver(index, $event)"
                @dragleave="onDragLeave(index)"
                @drop="onDrop(index, $event)"
                @dragend="onDragEnd">
                <!-- 拖拽手柄 -->
                <v-icon
                  icon="mdi-drag-vertical"
                  size="18"
                  class="drag-handle cursor-grab mr-1 text-medium-emphasis"
                  title="按住拖拽调整顺序" />

                <!-- 排名微型徽章 -->
                <span
                  class="rank-badge mr-2 font-weight-bold"
                  :class="{
                    'rank-badge--first': index === 0,
                    'rank-badge--second': index === 1,
                    'rank-badge--third': index === 2,
                  }">
                  #{{ index + 1 }}
                </span>

                <!-- 字幕组名称与匹配规则展示 / 选项名称展示 -->
                <div class="d-flex flex-column flex-grow-1 min-w-0 mr-3">
                  <span class="font-weight-medium text-body-2 text-truncate" :title="item.title">
                    {{ item.title }}
                  </span>
                  <span
                    v-if="isFansubMode || (item.value && item.value !== item.title)"
                    class="rule-pattern-text text-truncate"
                    :title="item.value">
                    {{ item.value }}
                  </span>
                </div>

                <!-- 宽敞舒适的操作按钮组：编辑（仅字幕组）、上移、下移、删除 -->
                <div class="item-actions d-flex align-center ga-1 ml-auto">
                  <v-btn
                    v-if="isFansubMode"
                    icon="mdi-pencil-outline"
                    variant="text"
                    color="primary"
                    size="small"
                    class="action-icon-btn action-icon-btn--edit"
                    title="编辑规则"
                    @click="openEditDialog(index)" />

                  <div class="d-flex align-center ga-1 sort-action-group">
                    <v-btn
                      icon="mdi-arrow-up"
                      variant="text"
                      size="small"
                      :disabled="index === 0"
                      class="action-icon-btn"
                      title="上移"
                      @click="moveItem(index, index - 1)" />
                    <v-btn
                      icon="mdi-arrow-down"
                      variant="text"
                      size="small"
                      :disabled="index === rulesList.length - 1"
                      class="action-icon-btn"
                      title="下移"
                      @click="moveItem(index, index + 1)" />
                  </div>

                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    size="small"
                    color="error"
                    class="action-icon-btn action-icon-btn--delete ml-1"
                    title="移除"
                    @click="removeItem(index)" />
                </div>
              </div>
            </div>
          </div>

          <!-- 模式二：字典映射模式 (Map Mode - 网播热度平台×类型，不改变顺序、无排序徽章) -->
          <div v-else>
            <!-- 平台选择下拉框 -->
            <v-autocomplete
              :model-value="selectedRegions"
              :items="field.items || []"
              label="选择要监听的平台"
              multiple
              item-title="title"
              item-value="value"
              chips
              closable-chips
              density="compact"
              variant="outlined"
              hide-details
              class="mb-3"
              @update:model-value="onMapRegionsUpdate" />

            <!-- 空状态 -->
            <div v-if="selectedRegions.length === 0" class="text-center py-8 text-medium-emphasis">
              <v-icon icon="mdi-television-off" size="36" class="mb-2 opacity-40" />
              <div class="text-caption">未选择任何平台，请在上方选择平台</div>
            </div>

            <!-- 平台媒体类型卡片列表（不可拖拽、无序号） -->
            <div v-else class="map-cards-container">
              <div
                v-for="region in selectedRegions"
                :key="region"
                class="map-card-item">
                <div class="d-flex align-center justify-space-between mb-2">
                  <div class="d-flex align-center ga-2">
                    <v-icon icon="mdi-television" size="18" color="primary" />
                    <span class="font-weight-bold text-body-2">{{ regionLabel(region) }}</span>
                  </div>
                  <v-btn
                    icon="mdi-close"
                    variant="text"
                    size="x-small"
                    density="compact"
                    color="error"
                    title="移除此平台"
                    @click="removeRegion(region)" />
                </div>

                <!-- 媒体类型胶囊切换 -->
                <div class="d-flex flex-wrap ga-1 pt-1">
                  <v-btn
                    v-for="column in field.columns || []"
                    :key="column.value"
                    size="x-small"
                    rounded="pill"
                    :variant="values(region).includes(column.value) ? 'tonal' : 'outlined'"
                    :color="values(region).includes(column.value) ? 'primary' : undefined"
                    @click="toggleValue(region, column.value)">
                    {{ column.title }}
                  </v-btn>
                </div>
              </div>
            </div>
          </div>
        </v-card-text>

        <v-divider />
        <v-card-actions class="px-4 py-2">
          <v-btn variant="text" size="small" color="error" @click="clearAll">清空全部</v-btn>
          <v-spacer />
          <v-btn color="primary" variant="flat" size="small" class="px-5 font-weight-medium"
                 @click="dialogVisible = false">完成
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>

    <!-- 独立的 Title 和 Value 编辑/新增规则子弹窗（仅字幕组规则模式） -->
    <v-dialog v-if="isFansubMode" v-model="editDialogVisible" max-width="440">
      <v-card class="rounded-xl">
        <v-card-title class="d-flex align-center py-3 px-4 text-subtitle-1 font-weight-bold">
          <v-icon :icon="editingIndex === -1 ? 'mdi-plus-circle' : 'mdi-pencil-circle'" color="primary" class="mr-2"
                  size="20" />
          {{ editingIndex === -1 ? "新增字幕组规则" : "编辑字幕组规则" }}
          <v-spacer />
          <v-btn icon="mdi-close" variant="text" size="small" class="dialog-close-btn"
                 title="关闭" @click="editDialogVisible = false" />
        </v-card-title>
        <v-divider />
        <v-card-text class="pt-4 px-4">
          <!-- 字幕组名称 (Title) -->
          <v-text-field
            v-model="editForm.title"
            label="字幕组名称 (Title)"
            placeholder="例如：喵萌奶茶屋、ANI、NC-Raws"
            density="compact"
            variant="outlined"
            class="mb-3"
            hide-details="auto"
            :rules="[v => !!String(v || '').trim() || '请输入字幕组名称']"
            @input="onEditTitleInput" />

          <!-- 匹配规则/正则表达式 (Value) -->
          <v-text-field
            v-model="editForm.value"
            label="匹配规则 / 正则表达式 (Value)"
            placeholder="例如：喵萌奶茶|Nekomoe、\bANI\b|ANi、NC-Raws"
            density="compact"
            variant="outlined"
            class="mb-2"
            hide-details="auto"
            :rules="[v => !!String(v || '').trim() || '请输入匹配规则']" />
          <div class="text-caption text-medium-emphasis mb-2">
            提示：支持正则表达式或关键词，动漫资源标题中命中即视为该字幕组。
          </div>

          <!-- 推荐规则一键填充 -->
          <div v-if="recommendedValue && recommendedValue !== editForm.value" class="d-flex align-center mt-2">
            <span class="text-caption text-medium-emphasis mr-1">推荐规则：</span>
            <v-chip
              size="x-small"
              color="primary"
              variant="tonal"
              class="cursor-pointer"
              @click="editForm.value = recommendedValue">
              应用推荐：{{ recommendedValue }}
            </v-chip>
          </div>
        </v-card-text>
        <v-divider />
        <v-card-actions class="px-4 py-2">
          <v-spacer />
          <v-btn variant="text" size="small" @click="editDialogVisible = false">取消</v-btn>
          <v-btn color="primary" variant="flat" size="small" class="px-5 font-weight-medium" @click="saveEditRule">
            确定
          </v-btn>
        </v-card-actions>
      </v-card>
    </v-dialog>
  </div>
</template>

<script setup>
import {computed, ref} from "vue";

const props = defineProps({
  modelValue: {type: [Object, Array, String], default: () => []},
  field: {type: Object, required: true},
});

const emit = defineEmits(["update:modelValue"]);
const dialogVisible = ref(false);
const editDialogVisible = ref(false);
const editingIndex = ref(-1);
const presetSelected = ref(null);

const editForm = ref({
  title: "",
  value: "",
});

const draggingIndex = ref(-1);
const dragOverIndex = ref(-1);

// 判定模式：优先级排序 (List) 还是 平台映射 (Map)
const isListMode = computed(() => {
  if (props.field.type === "priority-order") return true;
  if (props.field.type === "region-media-map") return false;
  if (props.field.columns && props.field.columns.length > 0) return false;
  return Array.isArray(props.modelValue) || typeof props.modelValue === "string";
});

// 判定是否是字幕组规则模式（仅字幕组支持自定义新增正则规则与编辑）
const isFansubMode = computed(() => {
  return Boolean(
    props.field?.allowCustomRules ||
    String(props.field?.key || "").includes("fansub"),
  );
});

// 是否是单纯标识符/字符串列表（如搜索渠道、资源类型）
const isSimpleValueList = computed(() => {
  return isListMode.value && !isFansubMode.value;
});

const presetPlaceholder = computed(() => {
  if (isFansubMode.value) return "从预设字幕组选择";
  const fieldName = props.field?.label?.replace("优先级", "").trim() || "项目";
  return `从可选${fieldName}选择添加`;
});

const emptyHint = computed(() => {
  if (isFansubMode.value) return "暂无字幕组规则，请点击上方“新建规则”或从预设选择添加";
  return "暂无优先级配置，请从上方下拉列表选择添加";
});

/**
 * 强力名称提取：无论传入的是旧正则还是带反斜杠的字符串，统一返回纯净友好名称
 */
function resolveFriendlyTitle(val) {
  if (!val) return "";
  if (typeof val === "object" && val !== null) {
    if (val.title) return String(val.title).trim();
    val = val.value || "";
  }
  const s = String(val).trim();

  // 1. 在 field.items 中寻找匹配
  const items = props.field.items || [];
  const matched = items.find((item) => String(item.value) === s || String(item.title) === s);
  if (matched && matched.title) return matched.title;

  // 2. 正则特征强力匹配
  const stripped = s.replace(/[\b\\()\[\]^$*+?]/g, "").trim();
  if (/ANI/i.test(stripped)) return "ANI";
  if (/喵萌奶茶|Nekomoe/i.test(stripped)) return "喵萌奶茶屋";
  if (/VCB/i.test(stripped)) return "VCB-Studio";
  if (/LoliHouse/i.test(stripped)) return "LoliHouse";
  if (/Nix-Raws/i.test(stripped)) return "Nix-Raws";
  if (/SweetSub/i.test(stripped)) return "SweetSub";
  if (/千夏/i.test(stripped)) return "千夏字幕组";
  if (/动漫国|DMG/i.test(stripped)) return "动漫国字幕组";
  if (/极影|KTXP/i.test(stripped)) return "极影字幕社";
  if (/樱都|桜都|Sakurato/i.test(stripped)) return "樱都字幕组";
  if (/诸神|Kamigami/i.test(stripped)) return "诸神字幕组";
  if (/北宇治|Kitauji/i.test(stripped)) return "北宇治字幕组";
  if (/悠哈璃羽|UHA/i.test(stripped)) return "悠哈璃羽字幕社";
  if (/爱恋字幕|KissSub/i.test(stripped)) return "爱恋字幕社";
  if (/拨雪寻春/i.test(stripped)) return "拨雪寻春";
  if (/Haru.*Hana/i.test(stripped)) return "HaruHana";
  if (/澄空|Sumisora/i.test(stripped)) return "澄空学园";
  if (/华盟|CASO/i.test(stripped)) return "华盟字幕社";
  if (/霜庭云花|STYH/i.test(stripped)) return "霜庭云花";
  if (/豌豆|Dymy/i.test(stripped)) return "豌豆字幕组";
  if (/Lilith/i.test(stripped)) return "Lilith-Raws";
  if (/DBD/i.test(stripped)) return "DBD制作组";
  if (/NC-Raws/i.test(stripped)) return "NC-Raws";
  if (/雪飘|FLsnow/i.test(stripped)) return "雪飘工作室";
  if (/幻樱|HYSub/i.test(stripped)) return "幻樱字幕组";

  if (s.includes("|")) {
    const firstWord = s.split("|")[0].replace(/[\b\\()\[\]^$*+?]/g, "").trim();
    if (firstWord) return firstWord;
  }
  return stripped || s;
}

/**
 * 规则列表数据规范化：无论外部传入的是纯规则字符串数组，还是对象数组，
 * 均在组件内统一规范化为包含 title 和 value 的标准对象数组
 */
const rulesList = computed(() => {
  const val = props.modelValue;
  let rawList = [];
  if (Array.isArray(val)) {
    rawList = val;
  } else if (typeof val === "string" && val.trim()) {
    rawList = val.split(/[,，\n]+/).map((s) => s.trim()).filter(Boolean);
  }

  return rawList.map((item) => {
    if (item && typeof item === "object") {
      const title = item.title ? String(item.title).trim() : resolveFriendlyTitle(item.value);
      const value = item.value ? String(item.value).trim() : title;
      return {title, value};
    }
    const str = String(item || "").trim();
    const title = resolveFriendlyTitle(str);
    return {title, value: str};
  }).filter((item) => Boolean(item.title && item.value));
});

// 字典映射模式下的数据规范化
const normalizedMap = computed(() => {
  const value = props.modelValue;
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
});

const selectedRegions = computed(() => Object.keys(normalizedMap.value));

const currentCount = computed(() => (isListMode.value ? rulesList.value.length : selectedRegions.value.length));

// 未添加进优先级的预设选项（供下拉单选快速添加）
const unselectedOptions = computed(() => {
  const items = props.field.items || [];
  const selectedTitles = new Set(rulesList.value.map((r) => r.title));
  const selectedValues = new Set(rulesList.value.map((r) => r.value));

  return items
    .filter((item) => !selectedValues.has(item.value) && !selectedTitles.has(item.title))
    .map((item) => ({
      title: item.title,
      value: item.value,
    }));
});

// Summary 概览（展示前 3 个纯净名称）
const summary = computed(() => {
  if (isListMode.value) {
    if (!rulesList.value.length) return "未配置（默认）";
    const labels = rulesList.value.slice(0, 3).map((v, i) => `${i + 1}. ${v.title}`);
    const suffix = rulesList.value.length > 3 ? ` 等共 ${rulesList.value.length} 项` : "";
    return labels.join("、") + suffix;
  }
  if (!selectedRegions.value.length) return "未选择";
  return selectedRegions.value.map((region) => `${regionLabel(region)} (${values(region).length})`).join("、");
});

function regionLabel(region) {
  const match = props.field.items?.find((item) => String(item.value) === String(region));
  return match?.title || region;
}

function values(region) {
  const val = normalizedMap.value[region];
  return Array.isArray(val) ? val : [];
}

function availableValues(region) {
  const normalizedRegion = String(region);
  return (props.field.columns || [])
    .filter((column) => !Array.isArray(column.rows) || column.rows.some((row) => String(row) === normalizedRegion))
    .map((column) => column.value);
}

// 推荐规则计算
const recommendedValue = computed(() => {
  if (!editForm.value.title) return "";
  const t = editForm.value.title.trim();
  const items = props.field.items || [];
  const matched = items.find((item) => item.title === t || resolveFriendlyTitle(item.value) === t);
  return matched ? matched.value : "";
});

function onEditTitleInput() {
  if (editingIndex.value === -1 && !editForm.value.value && recommendedValue.value) {
    editForm.value.value = recommendedValue.value;
  }
}

// 打开新增规则子弹窗
function openAddDialog() {
  editingIndex.value = -1;
  editForm.value = {
    title: "",
    value: "",
  };
  editDialogVisible.value = true;
}

// 打开编辑规则子弹窗
function openEditDialog(index) {
  editingIndex.value = index;
  const current = rulesList.value[index];
  if (current) {
    editForm.value = {
      title: current.title,
      value: current.value,
    };
    editDialogVisible.value = true;
  }
}

// 保存更新列表：自动区分纯字符串数组与自定义规则对象数组
function emitListUpdate(nextList) {
  if (isSimpleValueList.value) {
    emit(
      "update:modelValue",
      nextList.map((item) => (item && typeof item === "object" ? item.value : item)),
    );
  } else {
    emit("update:modelValue", nextList);
  }
}

// 保存编辑/新增的规则
function saveEditRule() {
  const title = String(editForm.value.title || "").trim();
  const value = String(editForm.value.value || "").trim();
  if (!title || !value) return;

  const next = [...rulesList.value];
  if (editingIndex.value === -1) {
    // 新增
    next.push({title, value});
  } else if (editingIndex.value >= 0 && editingIndex.value < next.length) {
    // 编辑
    next[editingIndex.value] = {title, value};
  }

  emitListUpdate(next);
  editDialogVisible.value = false;
}

// 从预设下拉直接添加
function onPresetSelect(preset) {
  if (!preset) return;
  const title = preset.title;
  const value = preset.value;

  const already = rulesList.value.some((r) => r.title === title || r.value === value);
  if (!already) {
    emitListUpdate([...rulesList.value, {title, value}]);
  }
  presetSelected.value = null;
}

function removeItem(index) {
  const next = [...rulesList.value];
  next.splice(index, 1);
  emitListUpdate(next);
}

// 模式二：平台更新
function onMapRegionsUpdate(items) {
  const arr = Array.isArray(items) ? items : [];
  const selectedKeys = arr.map((item) => (item && typeof item === "object" ? item.value || item.title : String(item))).filter(Boolean);
  const next = {};
  for (const region of selectedKeys) {
    next[region] = Object.prototype.hasOwnProperty.call(normalizedMap.value, region)
      ? [...values(region)]
      : availableValues(region);
  }
  emit("update:modelValue", next);
}

function removeRegion(region) {
  const next = {...normalizedMap.value};
  delete next[region];
  emit("update:modelValue", next);
}

function toggleValue(region, value) {
  const selected = values(region);
  const nextValues = selected.includes(value) ? selected.filter((item) => item !== value) : [...selected, value];
  if (!nextValues.length) {
    removeRegion(region);
    return;
  }
  emit("update:modelValue", {...normalizedMap.value, [region]: nextValues});
}

function clearAll() {
  emit("update:modelValue", isListMode.value ? [] : {});
}

// 拖拽与移动排序
function moveItem(fromIndex, toIndex) {
  if (!isListMode.value) return;
  const list = [...rulesList.value];
  if (fromIndex < 0 || fromIndex >= list.length || toIndex < 0 || toIndex >= list.length) return;
  const [moved] = list.splice(fromIndex, 1);
  list.splice(toIndex, 0, moved);
  emitListUpdate(list);
}

function onDragStart(index, event) {
  if (!isListMode.value) return;
  draggingIndex.value = index;
  if (event.dataTransfer) {
    event.dataTransfer.effectAllowed = "move";
    event.dataTransfer.setData("text/plain", String(index));
  }
}

function onDragOver(index, event) {
  if (!isListMode.value) return;
  event.preventDefault();
  if (event.dataTransfer) {
    event.dataTransfer.dropEffect = "move";
  }
  if (dragOverIndex.value !== index) {
    dragOverIndex.value = index;
  }
}

function onDragLeave(index) {
  if (dragOverIndex.value === index) {
    dragOverIndex.value = -1;
  }
}

function onDrop(index, event) {
  if (!isListMode.value) return;
  event.preventDefault();
  const from = draggingIndex.value;
  const to = index;
  if (from !== -1 && from !== to) {
    moveItem(from, to);
  }
  draggingIndex.value = -1;
  dragOverIndex.value = -1;
}

function onDragEnd() {
  draggingIndex.value = -1;
  dragOverIndex.value = -1;
}
</script>

<style scoped>
.region-media-map-field {
  min-width: 0;
}

.cursor-pointer {
  cursor: pointer;
}

.cursor-grab {
  cursor: grab;
}

.cursor-grab:active {
  cursor: grabbing;
}

/* 弹窗精致头部 */
.dialog-header {
  background: linear-gradient(180deg, rgba(var(--v-theme-primary), 0.06) 0%, rgba(var(--v-theme-surface), 1) 100%);
}

.dialog-header-icon {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  border-radius: 8px;
  background-color: rgba(var(--v-theme-primary), 0.12);
}

.dialog-header-title {
  font-size: 0.95rem;
  font-weight: 600;
  line-height: 1.2;
}

.dialog-header-subtitle {
  font-size: 0.75rem;
  line-height: 1.2;
  margin-top: 2px;
}

.dialog-close-btn {
  display: inline-flex !important;
  align-items: center !important;
  justify-content: center !important;
  width: 32px !important;
  height: 32px !important;
  min-width: 32px !important;
  border-radius: 50% !important;
  color: rgba(var(--v-theme-on-surface), 0.6) !important;
  transition: all 0.2s cubic-bezier(0.4, 0, 0.2, 1) !important;
}

.dialog-close-btn:hover {
  color: rgba(var(--v-theme-on-surface), 0.95) !important;
  background-color: rgba(var(--v-theme-on-surface), 0.08) !important;
  transform: rotate(90deg);
}

.dialog-close-btn:active {
  transform: rotate(90deg) scale(0.92);
}

/* 优先级列表容器：独立滚动、限制高度 */
.priority-list-container {
  display: flex;
  flex-direction: column;
  gap: 6px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}

/* 滚动条 */
.priority-list-container::-webkit-scrollbar,
.map-cards-container::-webkit-scrollbar {
  width: 5px;
}

.priority-list-container::-webkit-scrollbar-thumb,
.map-cards-container::-webkit-scrollbar-thumb {
  background-color: rgba(var(--v-theme-on-surface), 0.15);
  border-radius: 4px;
}

.priority-list-container::-webkit-scrollbar-thumb:hover,
.map-cards-container::-webkit-scrollbar-thumb:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.3);
}

/* 单行规则卡片 */
.priority-item-row {
  display: flex;
  align-items: center;
  padding: 6px 10px;
  min-height: 48px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 8px;
  background-color: rgb(var(--v-theme-surface));
  transition: all 0.15s ease;
  user-select: none;
}

.priority-item-row:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
  background-color: rgba(var(--v-theme-primary), 0.02);
}

.priority-item--dragging {
  opacity: 0.35;
  border: 1px dashed rgb(var(--v-theme-primary));
}

.priority-item--dragover {
  border: 2px solid rgb(var(--v-theme-primary));
  background-color: rgba(var(--v-theme-primary), 0.08);
  transform: translateY(1px);
}

.drag-handle {
  opacity: 0.4;
  transition: opacity 0.2s;
}

.drag-handle:hover {
  opacity: 1;
}

/* 操作按钮组：独立触控区与高品质悬浮态 */
.item-actions {
  flex-shrink: 0;
}

.action-icon-btn {
  width: 30px !important;
  height: 30px !important;
  min-width: 30px !important;
  border-radius: 8px !important;
  transition: all 0.2s ease;
}

.action-icon-btn:hover {
  background-color: rgba(var(--v-theme-on-surface), 0.08);
}

.action-icon-btn--edit:hover {
  background-color: rgba(var(--v-theme-primary), 0.12);
}

.action-icon-btn--delete:hover {
  background-color: rgba(var(--v-theme-error), 0.12);
}

.sort-action-group {
  padding: 0 1px;
}

/* 规则模式小文字 */
.rule-pattern-text {
  font-size: 0.72rem;
  color: rgba(var(--v-theme-on-surface), 0.45);
  font-family: Consolas, Monaco, monospace;
}

/* 排名微型徽章 */
.rank-badge {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  font-size: 0.72rem;
  min-width: 28px;
  height: 20px;
  padding: 0 5px;
  border-radius: 10px;
  background-color: rgba(var(--v-theme-on-surface), 0.08);
  color: rgb(var(--v-theme-on-surface));
}

.rank-badge--first {
  background: linear-gradient(135deg, #f59e0b, #d97706);
  color: #fff;
  box-shadow: 0 1px 4px rgba(245, 158, 11, 0.3);
}

.rank-badge--second {
  background: linear-gradient(135deg, #6366f1, #4f46e5);
  color: #fff;
}

.rank-badge--third {
  background: linear-gradient(135deg, #0ea5e9, #0284c7);
  color: #fff;
}

/* 模式二：字典映射列表（网播热度平台×类型） */
.map-cards-container {
  display: flex;
  flex-direction: column;
  gap: 8px;
  max-height: 380px;
  overflow-y: auto;
  padding-right: 4px;
}

.map-card-item {
  padding: 10px 12px;
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  border-radius: 10px;
  background-color: rgb(var(--v-theme-surface));
}

.map-card-item:hover {
  border-color: rgba(var(--v-theme-primary), 0.3);
}
</style>
