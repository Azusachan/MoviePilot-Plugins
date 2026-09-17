<template>
  <div class="multi-select-dialog-field">
    <div v-if="field.hint" class="text-caption text-medium-emphasis mb-2">{{ field.hint }}</div>

    <!-- 表单外层触发器输入框 -->
    <div
      class="trigger-field d-flex align-center px-3 py-2 rounded-lg"
      :class="{ 'is-disabled': disabled, 'has-values': selectedList.length > 0 }"
      @click="openDialog">
      <v-icon
        :icon="field.icon || 'mdi-checkbox-multiple-marked-outline'"
        size="18"
        class="mr-2 text-medium-emphasis flex-shrink-0" />

      <div class="trigger-content flex-grow-1 overflow-hidden">
        <div class="text-caption text-medium-emphasis trigger-label">{{ field.label }}</div>

        <!-- 未选中任何项 -->
        <div v-if="selectedList.length === 0" class="text-body-2 text-disabled text-truncate">
          {{ field.placeholder || "点击选择..." }}
        </div>

        <!-- 已选中的选项胶囊展示（紧凑优雅，最多展示前3项，超出的以 +N 项徽章汇总） -->
        <div v-else class="d-flex align-center flex-wrap ga-1 mt-1">
          <v-chip
            v-for="item in visibleChips"
            :key="item.value"
            size="x-small"
            variant="tonal"
            color="primary"
            class="font-weight-medium">
            {{ item.title }}
          </v-chip>
          <v-chip
            v-if="remainingCount > 0"
            size="x-small"
            variant="flat"
            color="primary"
            class="font-weight-bold">
            +{{ remainingCount }} 项
          </v-chip>
        </div>
      </div>

      <!-- 右侧操作图标 -->
      <div class="trigger-actions d-flex align-center ga-1 ml-2 flex-shrink-0">
        <v-btn
          v-if="selectedList.length > 0 && !disabled"
          icon="mdi-close-circle"
          variant="text"
          size="x-small"
          density="compact"
          color="medium-emphasis"
          title="清空已选项"
          class="clear-trigger-btn"
          @click.stop="clearSelection" />
        <v-icon icon="mdi-chevron-down" size="18" class="text-medium-emphasis" />
      </div>
    </div>

    <!-- 弹窗多选选择器 -->
    <v-dialog v-model="dialogVisible" max-width="580" scrollable>
      <v-card class="multi-select-dialog rounded-xl">
        <!-- 头部导航 -->
        <div class="dialog-header d-flex align-center px-4 py-3">
          <div class="dialog-header-icon mr-2">
            <v-icon
              :icon="field.icon || 'mdi-checkbox-multiple-marked-outline'"
              size="20"
              color="primary" />
          </div>
          <div class="flex-grow-1 overflow-hidden">
            <div class="dialog-header-title text-subtitle-1 font-weight-bold text-truncate">
              {{ field.label }}
            </div>
            <div class="dialog-header-subtitle text-caption text-medium-emphasis text-truncate">
              {{ field.hint || "支持多选，点击卡片直接勾选或取消" }}
            </div>
          </div>
          <v-chip size="small" variant="tonal" color="primary" class="font-weight-medium px-2 mr-1 flex-shrink-0">
            已选择 {{ tempSelection.length }} / {{ normalizedItems.length }} 项
          </v-chip>
          <v-btn
            icon="mdi-close"
            variant="text"
            size="small"
            class="dialog-close-btn ml-1 flex-shrink-0"
            title="关闭"
            @click="dialogVisible = false" />
        </div>

        <v-divider />

        <!-- 工具栏：搜索与批量操作 -->
        <div class="dialog-toolbar px-4 pt-3 pb-2 d-flex align-center justify-space-between ga-2">
          <!-- 搜索条（仅当选项较多时展示，扁平微胶囊风格） -->
          <div v-if="showSearch" class="search-box-wrapper flex-grow-1">
            <v-text-field
              v-model="searchKeyword"
              placeholder="快速过滤选项..."
              density="compact"
              variant="solo-filled"
              flat
              rounded="pill"
              prepend-inner-icon="mdi-magnify"
              hide-details
              clearable
              class="compact-search-input" />
          </div>
          <div v-else class="text-caption text-medium-emphasis">
            共 {{ normalizedItems.length }} 项可选
          </div>

          <!-- 批量操作微胶囊组 -->
          <div class="toolbar-actions d-flex align-center ga-1 flex-shrink-0">
            <v-btn
              variant="tonal"
              size="small"
              rounded="pill"
              color="primary"
              class="action-btn px-2 text-caption font-weight-medium"
              prepend-icon="mdi-check-all"
              @click="selectAll">
              全选
            </v-btn>
            <v-btn
              variant="tonal"
              size="small"
              rounded="pill"
              color="primary"
              class="action-btn px-2 text-caption font-weight-medium"
              prepend-icon="mdi-swap-horizontal"
              @click="invertSelection">
              反选
            </v-btn>
            <v-btn
              variant="text"
              size="small"
              rounded="pill"
              class="action-btn action-btn--clear px-2 text-caption font-weight-medium"
              prepend-icon="mdi-trash-can-outline"
              @click="clearTemp">
              清空
            </v-btn>
          </div>
        </div>

        <!-- 选项列表主体（双列卡片网格布局，消除右侧空洞感） -->
        <v-card-text class="pt-1 pb-2 px-4">
          <!-- 空匹配状态 -->
          <div v-if="filteredItems.length === 0" class="text-center py-8 text-medium-emphasis">
            <v-icon icon="mdi-file-search-outline" size="36" class="mb-2 opacity-40" />
            <div class="text-caption">没有匹配的选项</div>
          </div>

          <!-- 双列自适应网格 -->
          <div v-else class="options-grid-container">
            <div
              v-for="item in filteredItems"
              :key="item.value"
              class="option-card d-flex align-center px-3 py-2 rounded-lg cursor-pointer"
              :class="{ 'is-selected': isTempSelected(item.value) }"
              @click="toggleItem(item.value)">
              <!-- 精准对齐的勾选框图标 -->
              <v-icon
                :icon="isTempSelected(item.value) ? 'mdi-checkbox-marked' : 'mdi-checkbox-blank-outline'"
                :color="isTempSelected(item.value) ? 'primary' : 'medium-emphasis'"
                size="20"
                class="mr-2 flex-shrink-0 option-checkbox" />

              <div class="option-info flex-grow-1 overflow-hidden">
                <div
                  class="option-title font-weight-medium text-body-2 text-truncate"
                  :class="{ 'text-primary font-weight-bold': isTempSelected(item.value) }">
                  {{ item.title }}
                </div>
                <div v-if="item.hint" class="option-hint text-caption text-medium-emphasis text-truncate">
                  {{ item.hint }}
                </div>
              </div>
            </div>
          </div>
        </v-card-text>

        <v-divider />

        <!-- 底部操作栏 -->
        <v-card-actions class="px-4 py-2">
          <div class="text-caption text-medium-emphasis">
            已勾选 <span class="font-weight-bold text-primary">{{ tempSelection.length }}</span> 个选项
          </div>
          <v-spacer />
          <v-btn variant="text" size="small" class="px-4" @click="dialogVisible = false">
            取消
          </v-btn>
          <v-btn
            color="primary"
            variant="flat"
            size="small"
            class="px-5 font-weight-medium"
            @click="applySelection">
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
  modelValue: {
    type: [Array, String],
    default: () => [],
  },
  field: {
    type: Object,
    default: () => ({}),
  },
  disabled: {
    type: Boolean,
    default: false,
  },
});

const emit = defineEmits(["update:modelValue"]);

const dialogVisible = ref(false);
const searchKeyword = ref("");
const tempSelection = ref([]);

// 规范化所有候选项目为标准格式 [{ title, value, hint }]
const normalizedItems = computed(() => {
  const items = props.field?.items || [];
  if (!Array.isArray(items)) return [];

  return items.map((item) => {
    if (typeof item === "string" || typeof item === "number") {
      return {title: String(item), value: item, hint: ""};
    }
    if (item && typeof item === "object") {
      const title = item.title ?? item.label ?? item.name ?? String(item.value ?? "");
      const value = item.value ?? item.title ?? item.label ?? "";
      const hint = item.hint ?? item.subtitle ?? item.desc ?? "";
      return {title, value, hint};
    }
    return {title: String(item), value: item, hint: ""};
  });
});

// 已选项目的对象列表
const selectedList = computed(() => {
  const current = Array.isArray(props.modelValue) ? props.modelValue : (props.modelValue ? [props.modelValue] : []);
  const map = new Map(normalizedItems.value.map((i) => [String(i.value), i]));
  return current.map((val) => map.get(String(val)) || {title: String(val), value: val});
});

// 触发器中最多展示前 3 个 Chip
const visibleChips = computed(() => selectedList.value.slice(0, 3));
const remainingCount = computed(() => Math.max(0, selectedList.value.length - 3));

// 是否展示搜索栏（选项大于 8 项或配置了 searchable）
const showSearch = computed(() => {
  return normalizedItems.value.length > 8 || Boolean(props.field?.searchable);
});

// 过滤后的候选项目
const filteredItems = computed(() => {
  const kw = String(searchKeyword.value || "").trim().toLowerCase();
  if (!kw) return normalizedItems.value;
  return normalizedItems.value.filter((item) => {
    return (
      String(item.title || "").toLowerCase().includes(kw) ||
      String(item.value || "").toLowerCase().includes(kw) ||
      String(item.hint || "").toLowerCase().includes(kw)
    );
  });
});

function openDialog() {
  if (props.disabled) return;
  const current = Array.isArray(props.modelValue) ? props.modelValue : (props.modelValue ? [props.modelValue] : []);
  tempSelection.value = [...current];
  searchKeyword.value = "";
  dialogVisible.value = true;
}

function isTempSelected(val) {
  return tempSelection.value.some((v) => String(v) === String(val));
}

function toggleItem(val) {
  const index = tempSelection.value.findIndex((v) => String(v) === String(val));
  if (index !== -1) {
    tempSelection.value.splice(index, 1);
  } else {
    tempSelection.value.push(val);
  }
}

function selectAll() {
  const allValues = filteredItems.value.map((i) => i.value);
  const currentSet = new Set(tempSelection.value.map(String));
  for (const val of allValues) {
    currentSet.add(String(val));
  }
  // 按照候选顺序重排
  tempSelection.value = normalizedItems.value
    .filter((i) => currentSet.has(String(i.value)))
    .map((i) => i.value);
}

function invertSelection() {
  const visibleValues = new Set(filteredItems.value.map((i) => String(i.value)));
  const currentSet = new Set(tempSelection.value.map(String));
  const newSet = new Set();

  for (const v of tempSelection.value) {
    if (!visibleValues.has(String(v))) {
      newSet.add(String(v));
    }
  }
  for (const i of filteredItems.value) {
    if (!currentSet.has(String(i.value))) {
      newSet.add(String(i.value));
    }
  }

  tempSelection.value = normalizedItems.value
    .filter((i) => newSet.has(String(i.value)))
    .map((i) => i.value);
}

function clearTemp() {
  tempSelection.value = [];
}

function applySelection() {
  emit("update:modelValue", [...tempSelection.value]);
  dialogVisible.value = false;
}

function clearSelection() {
  if (props.disabled) return;
  emit("update:modelValue", []);
}
</script>

<style scoped>
.multi-select-dialog-field {
  width: 100%;
}

/* 触发器输入框样式：类似 Vuetify outlined 紧凑输入框 */
.trigger-field {
  border: 1px solid rgba(var(--v-border-color), var(--v-border-opacity));
  background-color: rgb(var(--v-theme-surface));
  min-height: 48px;
  cursor: pointer;
  transition: border-color 0.2s, box-shadow 0.2s, background-color 0.2s;
  user-select: none;
}

.trigger-field:hover:not(.is-disabled) {
  border-color: rgba(var(--v-theme-primary), 0.65);
  background-color: rgba(var(--v-theme-primary), 0.02);
}

.trigger-field.is-disabled {
  opacity: 0.6;
  cursor: not-allowed;
  pointer-events: none;
}

.trigger-label {
  line-height: 1.1;
}

.clear-trigger-btn {
  opacity: 0.7;
  transition: opacity 0.2s;
}

.clear-trigger-btn:hover {
  opacity: 1;
}

/* 弹窗头部与高颜值关闭按钮 */
.dialog-header {
  min-height: 52px;
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

/* 搜索框与操作工具栏 */
.compact-search-input :deep(.v-field) {
  height: 32px !important;
  min-height: 32px !important;
  font-size: 0.8rem;
  background-color: rgba(var(--v-theme-on-surface), 0.05) !important;
}

.compact-search-input :deep(.v-field__input) {
  min-height: 32px !important;
  padding-top: 0 !important;
  padding-bottom: 0 !important;
}

.compact-search-input :deep(.v-field__prepend-inner) {
  padding-top: 0 !important;
  align-items: center;
}

.action-btn {
  height: 28px !important;
  min-height: 28px !important;
}

.action-btn--clear {
  color: rgba(var(--v-theme-on-surface), 0.6) !important;
}

.action-btn--clear:hover {
  color: rgb(var(--v-theme-error)) !important;
  background-color: rgba(var(--v-theme-error), 0.08) !important;
}

/* 选项双列网格布局：紧凑饱满、告别单列空洞 */
.options-grid-container {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 8px;
  max-height: 380px;
  overflow-y: auto;
  padding: 4px 2px 8px 2px;
}

@media (max-width: 520px) {
  .options-grid-container {
    grid-template-columns: 1fr;
  }
}

.option-card {
  border: 1px solid rgba(var(--v-border-color), 0.16);
  background-color: rgb(var(--v-theme-surface));
  min-height: 42px;
  box-sizing: border-box;
  transition: all 0.18s cubic-bezier(0.4, 0, 0.2, 1);
  user-select: none;
}

.option-card:hover {
  border-color: rgba(var(--v-theme-primary), 0.45);
  background-color: rgba(var(--v-theme-primary), 0.03);
  transform: translateY(-1px);
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.04);
}

.option-card.is-selected {
  border-color: rgba(var(--v-theme-primary), 0.75);
  background-color: rgba(var(--v-theme-primary), 0.07);
}

.option-checkbox {
  transition: transform 0.15s ease;
}

.option-card:active .option-checkbox {
  transform: scale(0.9);
}
</style>
