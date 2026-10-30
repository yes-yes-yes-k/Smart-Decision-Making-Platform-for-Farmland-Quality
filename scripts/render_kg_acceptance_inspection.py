"""Publish a source-backed inspection, without amending frozen labels or sampling."""
import json,html,sys
from pathlib import Path
from collections import Counter
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from scripts.inspect_kg_acceptance_review import BASE,OUT
from scripts.experiment_kg_recall import read,write,jsonl,sha
from framework.knowledge_graph.acceptance_budget import Budget

CASES=[
 (0,'原文改字及区域误分类','模型把“土壈pH测定”改成“土壤pH测定”，同时把气候过渡地带标成standard。前者是字面绑定失败，后者是领域分类错误。不能靠修正occurrence解决。',['4.2 土壈pH测定','气候过渡地带 climate transition zone']),
 (1,'本体范围膨胀','模型将土壤肥沃、耕地、气象服务及多种定义性描述扩为可测指标或治理措施；土壤肥沃被现有严格校验拦截。',['土壤肥沃','农业气象服务 agrometeorological service']),
 (3,'结构合法但语义错误','原文为葡萄糖校准曲线，模型把试剂和加热器标成measure；该响应没有协议错误。这证明48条协议完整不能视作48条语义合格。',['葡萄糖标准使用液(5.4)','恒温加热器']),
 (4,'规范化证据缺少端点','模型把标准编号归一为题名，但所引证据只有题名、不含编号，违反当前同一证据覆盖两端的契约。跨块身份绑定如何处理需单独澄清；不能把规范化失败解释成实体无效。',['NY/T 1535—2007']),
 (6,'参考标签与候选边界不一致','候选用“编号+全称”整段，旧银标只选三个编号而未另列正文全称；二者都存在可定位的标准事实。提示要求编号、全称分别标，与旧参考清单存在待复核差异，不能把全部差异当模型凭空抽取。',['GB 15577 粉尘防爆安全规程','GB 3095 环境空气质量标准']),
 (9,'跨栏串行与自由补全','原文双栏串行把名词与说明打散，模型重组完整术语后不再是连续原文片段。这里须修解析或记录未知，不宜放宽字面绑定把重组结果直接计真。',['CC- induced increases in SOC','free particu-']),
 (16,'仪器属性误标及输出截断','电导池常数是仪器属性，电极法和振荡提取是分析步骤，均被模型扩成土壤实体或措施；实体阶段仍通过。随后关系响应被截断。',['电导池常数 cell constant','本标准规定了测定土壤电导率的电极法。']),
 (17,'分析试验与标准身份误判','干湿循环在该段用于实验室测试团聚体韧性，不自动是治理措施；模型还把Geoderma论文完整题名当standard。跨行行号使长片段无法原文绑定。',['structural resilience of aggregates','in a laboratory']),
 (22,'重复、对象及标准身份边界','候选重复选相同镉浓度片段，将植物吸收因子和生物量增长率列入土壤指标，又将未具名国家标准描述列standard。需分别判定对象和身份，不能只看字符串能否定位。',['plant uptake factor (PUF)','biomass growth rate (BioG)']),
 (31,'OCR规范化越界及漏关系待判','模型清理标准名称中的字形和标点后输出canonical_name，原文未包含该精确名称，规范化失败；后续空关系仍被保留。不能因其格式完整便认定定义中的功能关系不存在。',['土壤调理剂 soil amendments/ soil conditioners','NY/T 2272 土壤调理剂”钙,镁、硅含量的测定']),
 (46,'样品对象误标与断词重写','soil sample被标成indicator，intracellular biomolecular content被去掉原文断词及列间干扰后输出，无法绑定。细胞属性能否进入土壤指标还需领域语境裁决，不直接补成金标。',['For each soil sample, 270 spectra were collected.','bacterial metabolic activity']),
 (54,'片段放错来源块','DB23/T 3803—2024实际位于chunk，模型却声明来自document_title。各片段occurrence均为0，因此这不是序号累计错误。',['DB23/T 3803—2024']),
 (66,'过量实体与实体阶段截断','模型将水、浸提剂、指示电极、烧瓶等大量实验对象输出为措施，实体响应达到长度上限。不能仅靠增加输出额度解决语义范围失控。',['采用电位法测定土壤pH','4.4 pH 标准缓冲溶液']),
 (80,'题名信息冒充正文及方法误标','阳离子交换量只在题名出现，模型却指定chunk；模型自己的理由承认正文未出现。振荡、离心和试剂亦被标measure，涉及来源块与本体两类错误。',['HJ 889—2017','土壤样品采集和保存应按照HJ/T 166 执行。'])
]

NEW_CASES=[
 ('acceptance:105307a4b11aeb551b1b5c8c','双栏文字交错，酶活性与铁提取两种叙述混接；需页级版面复核，不能凭哈希正确就判语义可评。'),
 ('acceptance:c929b913302f848fc244ea76','正文几乎只有页脚与DOI，不提供完整土壤事实；保留为来源分布中的元数据/负例候选，不静默替换。'),
 ('acceptance:1f195897417f56c9fd5882ee','图中字形CID、倒置单词和重复标签混排；有效指标与关系须另判，不能只检查替换字符。'),
 ('acceptance:8518bd0954d1c3e21a04c4f2','方法段两列与化学符号上下标交错，部分铁形态名词被拆开；现有连续片段协议无法直接容纳重组词。'),
 ('acceptance:360e82417bd5c8e087028242','标准前言可提供标准身份，起草单位和人名不应成为土壤指标；属于合理孤立标准实体候选。'),
 ('acceptance:e9b04b4dae832e9b8693c333','原文为作物营养缺乏的植株症状，不能把叶色、株形和植物缺氮直接转为土壤质量事实。'),
 ('acceptance:a746a25c3ddee1d66ddae3bb','improves修饰影像预测精度；RMSE/R2属于模型性能，不支持治理措施改善土壤的关系。'),
 ('acceptance:352b3707525f60eed88aa629','pH及氢离子计算与造林效应叙述跨栏混接，需分开明确事实与待研究机制，不从片段拼接补关系。'),
 ('acceptance:b688aa0e1bd2fb03e156f07a','冻土地貌及土壤碳空间趋势不是具名人为治理措施；宽关键词命中不证明存在本体关系正例。'),
 ('acceptance:78d388db55a791ab42e5b399','背景叙述包含土壤碳库及气温变化，可有指标实体，但不能从Increase推断治理措施关系。'),
 ('acceptance:f8a31623cee39e816167e8ea','同段同时出现稻米镉和土壤镉阈值，须保留介质区别；食品限值不可混作土壤指标标准关系。'),
 ('acceptance:763468b22ec7ad9430ef9bc7','规范程序与鉴定报告要求本身不等于已给出具体土壤测定或改善事实。'),
 ('acceptance:beb161aedae0fe6468f1c1fb','表格OCR大量破损，仍有局部可读水文/土壤文字；任务是否可穷尽需单独评，不因部分能读就判整条可评。'),
 ('acceptance:dc8893ecae9de25f3dd30a28','MEC、MAE、RMSE是地图模型评价量；improvement指模型拟合，不是土壤改良效果。')
]

def main():
    inputs=read(BASE/'stability/inputs.jsonl');selection=read(BASE/'pool/selection.jsonl');diagnostics=read(OUT/'old-relabel-diagnostics.jsonl')
    manual=[]
    for index,kind,reason,quotes in CASES:
        visible=inputs[index];bound=[]
        for quote in quotes:
            matches=[dict(block_id=b['block_id'],text=quote,span_start=b['text'].find(quote),span_end=b['text'].find(quote)+len(quote)) for b in visible['blocks'] if quote in b['text']]
            if not matches:raise ValueError(f'manual evidence not literal: {index} {quote}')
            bound.extend(matches)
        manual.append(dict(index=index,display_number=index+1,sample_id=visible['sample_id'],kind=kind,reason=reason,evidence=bound,
            review='Codex targeted source review, not full independent arbitration',reference_modified=False))
    jsonl(OUT/'targeted-source-reviews.jsonl',manual)
    lookup={r['sample_id']:r for r in selection}
    new_manual=[dict(sample_id=sid,document_id=lookup[sid]['document_id'],track=lookup[sid]['track'],partition=lookup[sid]['partition'],
        reason=reason,review='Codex targeted visible-source inspection',not_a_final_label=True) for sid,reason in NEW_CASES]
    jsonl(OUT/'targeted-new-source-reviews.jsonl',new_manual)
    source=json.loads((OUT/'sources.json').read_text(encoding='utf-8'));sampling=json.loads((OUT/'sampling.json').read_text(encoding='utf-8'));old=json.loads((OUT/'old-relabel-summary.json').read_text(encoding='utf-8'))
    bad=[f for r in diagnostics for f in r['fragment_inspections'] if not f['bound']]
    failed_20_bindable=sum(r['literal_bindable_count'] for r in diagnostics if r['unbound_fragment_count'])
    findings=[
      dict(id='F1',severity='high',area='sampling',finding='代表性轨文档尾部覆盖为零',evidence='300条代表性样本的position_quartile仅为0/1/2，各100条，quartile=3为0；由三槽轮转从0开始导致。',action='另建v2抽样修订，按文档组轮换遗漏的四分位；校准与测试分别平衡四个位置，冻结v1不原地更换。'),
      dict(id='F2',severity='high',area='metadata',finding='语言和解析质量分层没有实际元数据',evidence=f"911篇审计文档的language、DOI均为0个有值，parse_quality已知为0；500条语言和解析质量均为unknown。",action='在旁路补充语言、解析质量及论文身份核验；DOI须来自文档身份页，不把参考文献中的任意DOI合并为同文献。'),
      dict(id='F3',severity='high',area='reference_contract',finding='协议完整不等于语义正确，旧参考边界也需复核',evidence='案例#4将试剂和加热器标measure且无协议错误；案例#7标准编号/全称切分与旧参考不一致。',action='先统一编号、全称与题名的标注单位，给旧银标另存待修订清单；不把原始实体差集全部当模型错误。'),
      dict(id='F4',severity='high',area='source',finding='字面可定位规则暴露断词、行号和跨栏串行问题',evidence=f"20条响应含40个不绑定片段，其中可通过改为首次出现修复的序号问题为{sum(f.get('first_occurrence_is_bindable',False) for f in bad)}；模型常拼接被打散的名词或改OCR。",action='定位到具体页做版面解析修订，旧快照保留；无法恢复则按任务保留未知，不能泛化模糊匹配补真值。'),
      dict(id='F5',severity='medium',area='source_flags',finding='现有质量标记漏掉显式PDF字形损坏',evidence=f"6条原文包含(cid:...)，6条均未存对应quality_flag；另有99条长英文粘连标记。标记是审查线索，不是不可读判决。",action='先旁路记录诊断，逐页复核后再决定任务掩码；不得自动剔除以提高分数。'),
      dict(id='F6',severity='high',area='challenge',finding='挑战轨目前只是宽关键词候选，不是关系覆盖集',evidence='Geoderma地图精度段因improvement进入候选；冻土碳库叙述也因increase命中。六种关系的事实数和独立文档数尚未验证。',action='新参考裁决后按类型统计30事实/10文档目标；负例和不足项单列，不将200条等同200条关系正例。'),
      dict(id='F7',severity='medium',area='sampling',finding='标准过采样且缺少总体概率权重',evidence='代表性轨论文150/标准150；615篇池为论文398/标准217；至少1篇少于3块的文档不能进入代表性轨。',action='声明这是分层诊断集；若用于总体估计，另冻概率抽样规则及权重，不据50/50设计推全库性能。'),
      dict(id='F8',severity='high',area='measurement',finding='旧复标失败不能合并成一个准确率或稳定性结论',evidence='100条尝试、48条完整、42条实体阶段失败、10条有后续阶段错误；来源仲裁0条。截断、调用失败与语义误判混在其中。',action='分别报告绑定、格式、可用性、本体、证据与参考争议；恢复时不重置预算，不混入V4.1新模型结果。')]
    report=dict(status='inconclusive',formal_acceptance_ready=False,source_integrity_passed=source['documents_checked']==144 and not source['problems'],
        programmatic_source_samples=500,original_files_verified=144,programmatic_old_relabels=100,
        targeted_old_semantic_reviews=len(manual),targeted_new_source_review_scope='14 selected examples from 4 track/partition combinations; not exhaustive semantic annotation of 500 samples',
        target_new_source_samples=['acceptance:105307a4b11aeb551b1b5c8c','acceptance:c929b913302f848fc244ea76','acceptance:1f195897417f56c9fd5882ee','acceptance:8518bd0954d1c3e21a04c4f2','acceptance:360e82417bd5c8e087028242','acceptance:e9b04b4dae832e9b8693c333','acceptance:a746a25c3ddee1d66ddae3bb','acceptance:352b3707525f60eed88aa629','acceptance:b688aa0e1bd2fb03e156f07a','acceptance:78d388db55a791ab42e5b399','acceptance:f8a31623cee39e816167e8ea','acceptance:763468b22ec7ad9430ef9bc7','acceptance:beb161aedae0fe6468f1c1fb','acceptance:dc8893ecae9de25f3dd30a28'],
        literal_fragment_diagnostics=dict(unbound_fragments=len(bad),wrong_ordinal_candidates=sum(f.get('first_occurrence_is_bindable',False) for f in bad),
            bindable_fragments_in_20_failed_samples=failed_20_bindable,not_a_recovery_or_semantic_acceptance=True),
        findings=findings,cloud_requests_added=0,new_model_assessed=False,frozen_sources_or_labels_changed=False)
    write(OUT/'inspection-report.json',report)
    e=lambda x:html.escape(str(x),quote=True)
    sections=[]
    for f in findings:sections.append(f"<section id='{f['id']}'><h2>{e(f['id'])} · {e(f['finding'])}</h2><p><b>{e(f['severity'])}</b> · {e(f['evidence'])}</p><p>建议：{e(f['action'])}</p></section>")
    cards=[]
    for c in manual:
        result=json.loads((BASE/'stability/responses'/f"{c['index']:03}.json").read_text(encoding='utf-8'))
        sources=''.join(f"<h4>{e(b['block_id'])}</h4><pre>{e(b['text'])}</pre>" for b in inputs[c['index']]['blocks'])
        outputs=''.join(f"<h4>{e(t['stage'])} · {e(t.get('finish_reason'))} · {e(t.get('error',''))}</h4><pre>{e(t['content'])}</pre>" for t in result['trace'])
        cards.append(f"<section id='case-{c['index']}'><h3>旧复标#{c['display_number']} · {e(c['kind'])}</h3><p>{e(c['reason'])}</p><p>{e(c['sample_id'])}</p><details><summary>原文与原始响应（未改写）</summary>{sources}{outputs}</details></section>")
    rows=[]
    for r in diagnostics:
        rows.append('<tr>'+''.join(f'<td>{e(x)}</td>' for x in [r['index']+1,r['state'],r['entity_fragment_count'],r['unbound_fragment_count'],json.dumps(r['errors'],ensure_ascii=False)])+'</tr>')
    page="""<!doctype html><html lang='zh-CN'><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'><title>审核页检查：来源、取样与旧复标错误</title><style>body{font:16px/1.7 system-ui;max-width:1150px;margin:32px auto;padding:0 20px;background:#f5f7f9;color:#1b3044}section,details{background:white;border:1px solid #ccd7df;padding:16px;margin:16px 0;border-radius:6px}pre{white-space:pre-wrap;overflow-wrap:anywhere;background:#edf2f6;padding:12px}table{width:100%;border-collapse:collapse}th,td{border:1px solid #cbd4dc;padding:7px;text-align:left}.banner{background:#fff0ce;padding:18px}summary{cursor:pointer}a{color:#155a9b}</style><h1>来源、取样与旧复标错误：检查结果</h1><p class='banner'>结论：来源完整性通过；正式验收准备仍不足。代表性轨遗漏文档第4四分位，旧复标还存在语义和参考边界问题。未调用模型，未修改冻结来源、标签或分数。</p><p>程序检查500条来源、144份原文件和100份旧响应；针对性精读14个新来源案例及14个旧复标案例。并未逐条完成500条语义标注或100条独立仲裁。旧响应来自DeepSeek-V4-Flash，不能作为V4.1-Flash结果。</p>"""
    new_cards=''.join(f"<section><h3>{e(c['track'])} / {e(c['partition'])} · 文档{c['document_id']}</h3><p>{e(c['reason'])}</p><details><summary>{e(c['sample_id'])} · 原文</summary><p>{e(lookup[c['sample_id']]['document_title'])}</p><pre>{e(lookup[c['sample_id']]['text'])}</pre></details></section>" for c in new_manual)
    page+=''.join(sections)+f"<h2>来源检查</h2><pre>{e(json.dumps(source,ensure_ascii=False,indent=2))}</pre><h2>抽样分布</h2><pre>{e(json.dumps(sampling,ensure_ascii=False,indent=2))}</pre><h2>旧复标错误汇总</h2><pre>{e(json.dumps(old,ensure_ascii=False,indent=2))}</pre><h2>14个新来源抽查案例</h2>{new_cards}<h2>14个旧复标原文核对案例</h2>{''.join(cards)}<h2>全部100条错误记录</h2><table><tr><th>审核序号</th><th>状态</th><th>可解析实体片段</th><th>不绑定片段</th><th>阶段错误</th></tr>{''.join(rows)}</table><p>序号从1起；JSON index从0起。可绑定片段不代表语义正确，审核结论不回写历史分数。</p></html>"
    (OUT/'index.html').write_text(page,encoding='utf-8')
    print(json.dumps(dict(findings=len(findings),targeted_old_cases=len(manual),new_source_examples=len(report['target_new_source_samples']),source_integrity=report['source_integrity_passed'],cloud_calls_added=0),ensure_ascii=False))

if __name__=='__main__':main()
