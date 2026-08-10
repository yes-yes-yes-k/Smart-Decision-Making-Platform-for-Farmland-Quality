/* 生成《大模型开发团队下一步工作建议》docx（5 模型现状版） */
const fs = require('fs');
const path = require('path');
const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  AlignmentType, LevelFormat, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageBreak,
} = require('docx');

const cellBorders = (() => {
  const b = { style: BorderStyle.SINGLE, size: 1, color: "BBBBBB" };
  return { top: b, bottom: b, left: b, right: b };
})();

const HDR_FILL = "D9E2F3";
const TOTAL_W = 9360;

// 工具函数
const h1 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_1, children: [new TextRun(t)] });
const h2 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_2, children: [new TextRun(t)] });
const h3 = (t) => new Paragraph({ heading: HeadingLevel.HEADING_3, children: [new TextRun(t)] });
const p = (t, opts = {}) => new Paragraph({
  spacing: { after: 120, line: 300 },
  children: [new TextRun({ text: t, ...opts })],
});
const bullets = (items) => items.map((t) => new Paragraph({
  numbering: { reference: "bullet-list", level: 0 },
  spacing: { after: 80, line: 300 },
  children: [new TextRun(t)],
}));
const numbered = (items, ref = "num-list") => items.map((t) => new Paragraph({
  numbering: { reference: ref, level: 0 },
  spacing: { after: 80, line: 300 },
  children: [new TextRun(t)],
}));

function cell(text, opts = {}) {
  const { header = false, width, align = AlignmentType.LEFT, bold = false } = opts;
  return new TableCell({
    borders: cellBorders,
    width: { size: width, type: WidthType.DXA },
    shading: header ? { fill: HDR_FILL, type: ShadingType.CLEAR } : undefined,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({ alignment: align, children: [new TextRun({ text, bold: header || bold })] })],
  });
}

function table(headers, rows, widths) {
  const headRow = new TableRow({
    tableHeader: true,
    children: headers.map((h, i) => cell(h, { header: true, width: widths[i], align: AlignmentType.CENTER })),
  });
  const bodyRows = rows.map((r) => new TableRow({
    children: r.map((c, i) => cell(c, { width: widths[i] })),
  }));
  return new Table({ columnWidths: widths, margins: { top: 60, bottom: 60, left: 120, right: 120 }, rows: [headRow, ...bodyRows] });
}

const M = (id, name, qt, scale, dtype, domain, impl) => [id, name, String(qt), scale, dtype, domain, impl];

// ============ 内容 ============
const children = [];

// 标题
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 120 },
  children: [new TextRun({ text: "广东耕地质量大模型", size: 40, bold: true, font: "Arial" })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 60 },
  children: [new TextRun({ text: "大模型开发团队下一步工作建议（修订版）", size: 32, bold: true })],
}));
children.push(new Paragraph({
  alignment: AlignmentType.CENTER,
  spacing: { after: 240 },
  children: [new TextRun("基于项目代码现状修订 · 5 模型体系 · 版本 4.0 · 2026 年 8 月")],
}));

// 一、背景与目标
children.push(h1("一、背景与目标"));
children.push(p("本文档基于项目代码实际探索结果全面修订，与当前 5 模型体系保持一致。项目实际共有 5 个专业 Agent（model-1 至 model-5），均已接入真实实现并注册到统一能力目录 capabilities.py。此前版本描述的 7 模型体系（含 model-2 潜力评价、历史占位桩）已废弃。"));
children.push(p("大模型开发团队的核心职责是：意图识别与路由、Agent 接口封装与调用编排、数据检索与转换、多模型任务拆解、结果展示保护、调用日志及系统级测试。本修订版的目标是在已完成的五维路由（P1）基础上，补齐工程治理闭环，重点解决可观测性不足（P9）问题。"));

// 二、项目代码现状
children.push(h1("二、项目代码现状对照"));

children.push(h2("2.1 5 模型能力与实现状态"));
children.push(p("统一能力目录 PROFESSIONAL_CAPABILITIES（framework/agents/capabilities.py）为唯一注册表，Agent 注册、路由与问题类型均从中读取。5 个模型均已完成实现："));
const modelHeader = ["Agent ID", "能力名称", "question_type", "分析尺度", "数据类型", "问题域", "实现状态"];
const modelRows = [
  M("model-1", "障碍诊断", "1", "地块", "指标数据", "problem", "已完成"),
  M("model-2", "酸化改良", "2", "地块", "处方用量", "acidification", "已完成"),
  M("model-3", "有机质培肥", "3", "县", "处方用量", "organic_matter", "已完成"),
  M("model-4", "稳定性风险", "4", "地块", "评价结果", "stability", "已完成"),
  M("model-5", "质量等级评价", "5", "地块", "评价结果", "grade", "已完成"),
];
children.push(table(modelHeader, modelRows, [1200, 2400, 900, 900, 1100, 1200, 1660]));

children.push(h2("2.2 路由系统现状（P1 已完成）"));
children.push(p("五维路由已落地并在 routing-exclusive-rules 规程中固化，核心逻辑位于 framework/agents/exclusive_rules.py 与 router.py："));
children.push(bullets([
  "统一能力映射：question_type → 单一专业 Agent 的 1:1 映射由 CAPABILITY_BY_QUESTION_TYPE 自动生成。",
  "五维排他规则：EXCLUSIVE_RULES 基于“业务任务 + 分析尺度 + 数据类型 + 预期输出 + 模型依赖”五个维度，消除 model-1/5、model-2/3 两组易混淆对的误选。",
  "关键词规则（v1）：现状评价→model-1、酸化调理剂→model-2、稳定性风险→model-4、质量等级评价→model-5。",
  "维度驱动规则（v1.1）：地块级质量等级评价→model-5；地块级障碍诊断→model-1；酸化处方用量→model-2；有机肥处方用量→model-3。",
  "冲突降级：当多条规则同时命中且无法消解时，返回“模型边界待确认”（boundary_pending），不自行选择任一易混淆模型。",
  "路由回归：test_question_type_keywords.py 已覆盖 model-1/5、model-2/3 两组混淆对的不少于 20 条正反例。",
]));

children.push(h2("2.3 工程能力现状"));
const engHeader = ["能力", "状态", "说明"];
const engRows = [
  ["五维路由", "已完成", "P1 已落地，含排他规则与边界待确认降级"],
  ["Agent 统一能力目录", "已完成", "capabilities.py 唯一注册表，5 模型全部接入"],
  ["LangSmith 追踪", "已启用", "覆盖 LLM 调用，远端 trace"],
  ["本地调用日志", "缺失", "仅 LangSmith 远端，无本地持久化路由/调用日志（P9）"],
  ["路由混淆矩阵", "缺失", "无分类性能统计（P9）"],
  ["路由回归自动化", "部分", "已有 test_question_type_keywords.py，需扩为回归套件（P9）"],
  ["路由看板", "缺失", "无正确率/混淆率/漏调用率实时展示（P9）"],
  ["结果可追溯链", "缺失", "结果无法回查数据版本/Agent 版本/参数（P9）"],
  ["统一数据对象", "缺失", "各模型输入格式沿用 parcel_id/indicators，尚未统一（P2）"],
  ["多模型任务编排", "缺失", "dependencies 仍为空，1:1 执行（P7）"],
  ["调用状态机", "缺失", "无五状态机（P3）"],
  ["结果保护模板", "缺失", "仅 prompt 软约束（P8）"],
];
children.push(table(engHeader, engRows, [2000, 1500, 5860]));

// 三、核心问题诊断
children.push(h1("三、当前核心问题诊断（修订）"));
const pHeader = ["编号", "问题", "影响级别", "当前状态", "仍需改进"];
const pRows = [
  ["P1", "五维路由升级", "严重", "已完成", "维护排他规则与回归测试"],
  ["P2", "缺少统一数据模型", "严重", "未开始", "建标准数据对象 + 适配器"],
  ["P3", "未区分在线/批量/查询", "高", "未开始", "统一三类调用框架 + 状态机"],
  ["P4", "依赖关系未编排", "高", "未开始", "恢复依赖图 + 跨期检查"],
  ["P5", "工具粒度不当", "高", "部分", "工具注册中心 + JSON Schema"],
  ["P6", "参数治理不足", "高", "未开始", "参数分类 + 确认机制"],
  ["P7", "多模型拆解缺失", "高", "未开始", "任务规划器 + 依赖链"],
  ["P8", "结果保护缺失", "高", "未开始", "模板引擎 + 禁止表述过滤"],
  ["P9", "可观测性不足", "中", "本次实施", "本地日志 + 混淆矩阵 + 看板 + 追溯链"],
];
children.push(table(pHeader, pRows, [600, 4200, 1100, 1460, 2000]));

children.push(h2("3.9 可观测性不足（P9，本次实施）"));
children.push(p("代码现状：LangSmith 已启用，覆盖 LLM 调用远端 trace，但无本地持久化调用日志、无路由混淆矩阵、无分类性能统计、无路由看板、结果不可追溯。"));
children.push(p("改进办法：实现本地路由/调用日志落库；建立 model-1/5、model-2/3 混淆矩阵测试；路由回归自动化（扩充 test_question_type_keywords.py）；路由看板（正确率、混淆率、漏调用率）；结果可追溯链（数据版本、Agent 版本、参数、调用时间）。"));

// 四、下一步开发工作
children.push(h1("四、下一步开发工作建议（按优先级）"));

children.push(h2("4.1 P9：可观测性与混淆测试体系（当前任务）"));
children.push(p("目标：在已有 LangSmith 远端追踪基础上，补齐本地调用日志、混淆矩阵、路由回归、看板与追溯链，实现“不调用或错调用”的精准定位与自动回归。"));
children.push(p("具体任务："));
children.push(numbered([
  "实现本地路由/调用日志落库：记录候选 Agent 列表、路由理由、五维上下文、排他规则命中、降级状态、耗时、失败原因与结果版本到本地存储。",
  "建立混淆矩阵测试：对 model-1/5、model-2/3 两组易混淆对各准备不少于 20 条正反例，输出混淆矩阵与分类性能统计。",
  "路由回归自动化：扩充 test_question_type_keywords.py，每次修改提示词、路由规则、接口或模型版本后自动运行并输出混淆矩阵。",
  "建立路由看板：实时展示路由正确率、重叠 Agent 混淆率、漏调用率、参数完整率等关键指标。",
  "实现结果可追溯链：每个结果均可追溯到数据版本、Agent 版本、参数与调用时间。",
]));
children.push(p("可观测性指标："));
const kpiHeader = ["指标", "定义", "目标值"];
const kpiRows = [
  ["路由正确率", "正确选择 Agent / 组合 / 不调用的比例", "≥ 95%"],
  ["重叠 Agent 混淆率", "model-1/5、model-2/3 的错选比例", "≤ 3%"],
  ["漏调用率", "需要专业计算但未调用的比例", "≤ 2%"],
  ["参数完整率", "进入 Agent 前必填字段完整比例", "≥ 98%"],
  ["接口成功率", "在线调用正常返回比例", "≥ 99%"],
  ["结果可追溯率", "能追溯到数据/Agent 版本的比例", "100%"],
];
children.push(table(kpiHeader, kpiRows, [2400, 5360, 1600]));

children.push(h2("4.2 P2：统一数据对象与适配器层"));
children.push(p("建立系统级“耕地标准数据对象”，统一 parcel_id、指标编码、农业区、地类、等级与数据年份；为 5 个模型各编写适配器；实现数据补齐与来源追溯；禁止猜测，数据缺失返回“数据缺失”。"));

children.push(h2("4.3 P3：调用状态机与参数治理"));
children.push(p("建立“可调用、需补参、结果可查询、需批任务、禁止调用”五状态机；参数分类（DB 自动取得 / 系统计算 / 用户确认 / 专业默认值）；默认参数透明展示并允许覆盖。"));

children.push(h2("4.4 P7：多模型任务编排器"));
children.push(p("恢复 dependencies 注册；实现任务拆解引擎，按“障碍诊断 → 稳定性风险 → 酸化/培肥治理 → 等级评价”拆解；实现结果复用与跨期一致性检查；合并答案标注来源、数据年份与版本。"));

children.push(h2("4.5 P8：结果保护模板与 Guardrails"));
children.push(p("建立结果展示模板引擎；实现禁止表述过滤；扩展强制伴随信息（非概率、累计量、默认参数清单）；系统级外推等级；专家复核触发。"));

// 五、里程碑
children.push(h1("五、阶段性里程碑计划（修订）"));
const msHeader = ["阶段", "主要工作", "验收物"];
const msRows = [
  ["第一阶段：路由与观测", "五维路由回归 + 本地日志 + 混淆矩阵 + 看板 + 追溯链", "P9 可观测性闭环、路由看板"],
  ["第二阶段：数据标准化", "标准数据对象 + 适配器 + 字段映射表代码化", "数据规范、适配器代码"],
  ["第三阶段：编排与状态机", "任务编排器 + 依赖图 + 五状态机", "编排器代码、状态机"],
  ["第四阶段：保护与闭环", "结果模板 + Guardrails + 端到端测试", "模板引擎、端到端测试报告"],
];
children.push(table(msHeader, msRows, [2400, 4360, 2600]));

// 六、验收指标
children.push(h1("六、验收指标（修订）"));
const accHeader = ["指标", "定义", "目标值"];
const accRows = [
  ["路由正确率", "对已标注问题正确选择 Agent / 组合 / 不调用", "≥ 95%"],
  ["重叠 Agent 混淆率", "model-1/5、model-2/3 错选比例", "≤ 3%"],
  ["漏调用率", "需要专业计算但未调用比例", "≤ 2%"],
  ["参数完整率", "必填字段、单位、数据来源、确认项完整比例", "≥ 98%"],
  ["接口成功率", "在线调用 / 批量提交 / 结果查询正常返回", "≥ 99%"],
  ["结果一致性", "相同版本与输入得到可重复结果", "100%"],
  ["默认值透明率", "默认参数完整展示及来源", "100%"],
  ["风险提示完整率", "外推 / 非概率 / 累计 / 专家复核警告不遗漏", "100%"],
  ["结果可追溯率", "每个结果可追溯到数据/Agent 版本、参数、时间", "100%"],
];
children.push(table(accHeader, accRows, [2400, 5360, 1600]));

// 七、总结
children.push(new Paragraph({ children: [new PageBreak()] }));
children.push(h1("七、总结"));
children.push(p("项目当前为 5 模型体系，五维路由（P1）已完成，排他规则与边界待确认降级机制已落地。本次工作聚焦 P9 可观测性不足：补齐本地调用日志、混淆矩阵测试、路由回归自动化、路由看板与结果追溯链，使系统具备“不调用或错调用”的精准定位与持续质量监控能力。"));
children.push(p("建议按“路由与观测 → 数据标准化 → 编排与状态机 → 保护与闭环”四阶段推进。P9 先行落地观测底座，为后续统一数据对象（P2）、多模型编排（P7）与结果保护（P8）提供可量化的质量基线。最终目标：需要专业计算时调用正确且权威的 Agent；需要多 Agent 时按依赖组合；已有结果优先查询；参数不足不猜测；默认值、单位、版本与风险对用户透明；LangSmith 远端追踪与本地调用日志并行覆盖，混淆矩阵与路由看板持续监控质量。"));

// ============ 文档装配 ============
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullet-list", levels: [{ level: 0, format: LevelFormat.BULLET, text: "•", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
      { reference: "num-list", levels: [{ level: 0, format: LevelFormat.DECIMAL, text: "%1.", alignment: AlignmentType.LEFT, style: { paragraph: { indent: { left: 720, hanging: 360 } } } }] },
    ],
  },
  styles: {
    default: { document: { run: { font: "微软雅黑", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 30, bold: true, color: "1F4E79" }, paragraph: { spacing: { before: 280, after: 160 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true, run: { size: 26, bold: true, color: "2E74B5" }, paragraph: { spacing: { before: 200, after: 120 }, outlineLevel: 1 } },
    ],
  },
  sections: [{
    properties: { page: { margin: { top: 1440, right: 1440, bottom: 1440, left: 1440 } } },
    children,
  }],
});

const outPath = path.resolve(__dirname, "..", "大模型开发团队下一步工作建议.docx");
Packer.toBuffer(doc).then((buf) => {
  fs.writeFileSync(outPath, buf);
  console.log("WROTE", outPath, buf.length, "bytes");
});