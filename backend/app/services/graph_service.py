from __future__ import annotations

import re
from uuid import UUID

import jieba
import jieba.posseg as pseg
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.db.models import Chunk, KnowledgeEntity, KnowledgeRelation

EN_STOPWORDS = {
    'the',
    'and',
    'for',
    'with',
    'from',
    'this',
    'that',
    'into',
    'then',
    'than',
    'are',
    'is',
    'was',
    'were',
    'what',
    'when',
    'where',
    'who',
    'why',
    'how',
    'can',
    'will',
    'should',
    'could',
    'would',
    'use',
    'using',
    'used',
    'data',
    'model',
}

ZH_STOPWORDS = {
    '我们', '你们', '他们', '这些', '那些', '这个', '那个',
    '以及', '或者', '可以', '进行', '因为', '所以', '通过',
    '如果', '然后', '其中', '一种', '这个', '那个', '什么',
    '怎么', '如何', '为什么', '时候', '地方', '人们', '大家',
    '自己', '没有', '有的', '还有', '一些', '其他', '可能',
}

# 需要过滤的中文实体后缀模式
ENTITY_SUFFIX_BLACKLIST = {
    # 动词后缀
    '说', '道', '曰', '云', '称', '表示', '指出', '强调', '提出', '要求', '希望', '介绍', '说明', '解释', '告诉', '问', '答', '笑', '哭', '想', '知道', '觉得', '发现', '看到', '听到', '记得', '完了', '接着', '起来', '下来', '过来', '回来', '出去', '开始', '结束', '继续', '停止', '告诉', '告诉', '想起', '感到', '看来', '起来', '下来', '上去', '过来', '过来', '回去', '出去', '进去', '出来', '回来', '过来', '下去', '住', '掉', '成', '到', '好', '完', '到', '起', '下', '上', '来', '去', '出', '进', '回', '过', '掉', '成', '好', '完',
    # 常见名词后缀
    '时候', '地方', '意思', '情况', '样子', '声音', '电话', '手表', '东西', '事情', '问题', '之后', '以前', '以后', '时候', '地方',
    # 常见形容词/副词后缀
    '这样', '那样', '怎样', '如何', '这个', '那个', '什么', '大家', '我们', '你们', '他们', '自己', '别人', '不是', '就是', '但是', '因为', '所以', '如果', '虽然', '已经', '曾经', '正在', '将要', '可能', '应该', '必须', '需要', '可以', '愿意', '喜欢', '讨厌', '害怕', '担心', '相信', '怀疑', '理解', '明白', '了解', '认识', '熟悉', '进行', '完成', '实现', '形成', '包括', '有关', '对于', '关于', '由于', '根据', '通过', '非常', '特别', '十分', '相当', '比较', '很', '真', '好', '坏', '多', '少', '大', '小', '长', '短', '高', '低', '新', '旧', '快', '慢', '早', '晚',
}

# 单字停用词（无意义的中文单字）
SINGLE_CHAR_BLACKLIST = {
    '的', '是', '在', '了', '和', '与', '或', '有', '我', '你', '他', '她', '它', '们', '这', '那', '就', '也', '都', '而', '及', '着', '被', '把', '让', '给', '向', '从', '到', '至', '对', '于', '为', '以', '如', '因', '所', '当', '时', '后', '前', '上', '下', '中', '内', '外', '里', '间', '之', '其', '可', '能', '要', '会', '应', '该', '才', '已', '曾', '将', '且', '又', '则', '但', '却', '只', '仅', '比', '等', '似', '像', '属', '含', '带', '通', '过', '做', '作', '使', '令', '叫', '请', '派', '劝', '求', '望', '盼', '很', '真', '好', '坏', '多', '少', '大', '小', '长', '短', '高', '低', '新', '旧', '快', '慢', '早', '晚', '明', '暗', '轻', '重', '软', '硬', '热', '冷', '干', '湿', '满', '空', '开', '关', '来', '去', '进', '出', '起', '落', '生', '死', '始', '终', '止', '加', '减', '乘', '除', '正', '负', '左', '右', '东', '西', '南', '北', '天', '地', '日', '月', '星', '山', '水', '火', '风', '雨', '雪', '花', '草', '树', '木', '虫', '鸟', '鱼', '兽', '人', '事', '物', '心', '手', '足', '口', '耳', '目', '头', '身', '力', '气', '血', '骨', '肉', '皮', '毛', '肝', '脾', '肺', '肾', '胃', '肠', '胆', '子', '女', '夫', '妻', '父', '母', '兄', '弟', '姐', '妹', '友', '敌', '君', '臣', '民', '官', '兵', '商', '学', '工', '农', '知', '识', '字', '文', '句', '章', '篇', '书', '报', '刊', '杂', '志', '画', '图', '像', '影', '声', '音', '乐', '曲', '歌', '诗', '词', '赋', '艺', '术', '科', '技', '法', '律', '理', '数', '化', '生', '医', '药', '政', '治', '经', '济', '贸', '金', '银', '铜', '铁', '钢', '煤', '油', '气', '电', '光', '磁', '原', '子', '核', '波', '粒', '量', '能', '功', '率', '压', '强', '温', '度', '密', '容', '积', '面', '体', '形', '色', '彩', '红', '黄', '蓝', '绿', '白', '黑', '紫', '橙', '粉', '灰', '棕', '铝', '锌', '锡', '铅', '镍', '铬', '锰', '钛', '铂', '钨', '钼', '汞', '硝', '硫', '磷', '碳', '硅', '钙', '镁', '钾', '钠', '氯', '氧', '氢', '氮', '氟', '溴', '碘', '硼',
}

CJK_ENTITY_PATTERN = re.compile(r'[\u4e00-\u9fff]{2,4}')
EN_ENTITY_PATTERN = re.compile(r'[A-Za-z][A-Za-z0-9_\-/]{2,40}')
SENTENCE_SPLIT_PATTERN = re.compile(r'[。！？!?;；\n]')

# 职位/称呼后缀模式
TITLE_SUFFIXES = {
    '市长', '副市长', '省长', '副省长', '书记', '副书记', '主席', '副主席',
    '主任', '副主任', '厅长', '副厅长', '局长', '副局长', '处长', '副处长',
    '科长', '副科长', '镇长', '副镇长', '乡长', '副乡长', '行长', '副行长',
    '总裁', '副总裁', '总经理', '副总经理', '董事长', '副董事长', '总监', '副总监',
    '院长', '副院长', '校长', '副校长', '所长', '副所长', '主席', '副主席',
    '部长', '副部长', '经理', '副经理', '书记', '副书记', '老板', '总裁',
    '主任', '副主任', '组长', '副组长', '队长', '副队长', '主席', '副主席',
    '教授', '副教授', '讲师', '助教', '老师', '医生', '护士', '医师',
}

# 常见姓氏（用于人名匹配）
COMMON_SURNAMES = {
    '王', '李', '张', '刘', '陈', '杨', '赵', '黄', '周', '吴',
    '徐', '孙', '胡', '朱', '高', '林', '何', '郭', '马', '罗',
    '梁', '宋', '郑', '谢', '韩', '唐', '冯', '于', '董', '萧',
    '程', '曹', '袁', '邓', '许', '傅', '沈', '曾', '彭', '吕',
    '苏', '卢', '蒋', '蔡', '贾', '丁', '魏', '薛', '叶', '阎',
    '余', '潘', '杜', '戴', '夏', '钟', '汪', '田', '石', '皮',
}


def normalize_entity(name: str) -> str:
    stripped = re.sub(r'\s+', ' ', name).strip()
    if not stripped:
        return ''
    if re.fullmatch(r'[A-Za-z0-9_\-/ ]+', stripped):
        return stripped.lower()
    return stripped


def resolve_entity_alias(entities: list[str]) -> dict[str, str]:
    """
    实体消歧：将包含职位称呼的实体（如"皮副市长"）映射到正式人名（如"皮杰"）
    返回 {别名: 正式名} 的映射
    """
    # 找出所有可能是人名的实体（2-3个汉字，且首字是常见姓氏）
    person_names: set[str] = set()
    for e in entities:
        if len(e) >= 2 and len(e) <= 4:
            if e[0] in COMMON_SURNAMES:
                person_names.add(e)
    
    alias_map: dict[str, str] = {}
    
    for e in entities:
        if len(e) < 3:
            continue
        # 检查是否以职位后缀结尾
        for suffix in TITLE_SUFFIXES:
            if e.endswith(suffix):
                # 提取可能的姓名部分（去掉职位后缀前的部分）
                name_part = e[:-len(suffix)]
                # 尝试匹配已知的人名
                matched_name = None
                for person in person_names:
                    # 完全匹配
                    if person == name_part:
                        matched_name = person
                        break
                    # 姓名是人名的一部分（如"朱怀镜"是"朱怀"超长匹配后的结果）
                    # 或者人名是姓名的前部分
                    if person.startswith(name_part[:2]) and len(name_part) >= 2:
                        if matched_name is None or len(person) > len(matched_name):
                            matched_name = person
                
                if matched_name:
                    alias_map[e] = matched_name
                break
    
    return alias_map


def extract_entities_from_text(text: str, *, max_entities: int = 20) -> list[str]:
    if not text:
        return []

    candidates: list[str] = []

    # 方法1：使用jieba进行词性标注分词
    words = pseg.cut(text)
    for word, flag in words:
        word = word.strip()
        if not word or len(word) < 2:
            continue
        # 筛选实体词性：nr(人名), ns(地名), nt(机构名), nz(其他专名)
        if flag in ('nr', 'ns', 'nt', 'nz') and len(word) >= 2:
            candidates.append(word)

    # 英文实体
    candidates.extend(EN_ENTITY_PATTERN.findall(text))

    # 实体消歧：将"皮副市长"等称呼映射到正式人名"皮杰"
    alias_map = resolve_entity_alias(candidates)
    if alias_map:
        # 将别名添加到候选中，消歧后的结果会在后面处理
        for alias, canonical in alias_map.items():
            if alias not in candidates:
                candidates.append(alias)
            if canonical not in candidates:
                candidates.append(canonical)

    results: list[str] = []
    seen: set[str] = set()

    # 预先建立别名到正式名的映射（用于过滤阶段）
    alias_to_canonical = resolve_entity_alias(candidates)

    for raw in candidates:
        cleaned = raw.strip(' ,.;:()[]{}"\'')
        if len(cleaned) < 2:
            continue
        
        # 如果是别名，使用正式名称
        if cleaned in alias_to_canonical:
            cleaned = alias_to_canonical[cleaned]
        
        norm = normalize_entity(cleaned)
        if not norm:
            continue
        if norm in EN_STOPWORDS or norm in ZH_STOPWORDS:
            continue
        # 过滤单字停用词
        if len(norm) == 1 and norm in SINGLE_CHAR_BLACKLIST:
            continue
        # 过滤以黑名单后缀结尾的实体（如"XXX说"、"XXX道"等）
        for suffix in ENTITY_SUFFIX_BLACKLIST:
            if norm.endswith(suffix):
                break
        else:
            # 没有匹配到黑名单后缀
            if norm.isdigit():
                continue
            if norm in seen:
                continue
            seen.add(norm)
            results.append(cleaned)
            if len(results) >= max_entities:
                break
        if len(results) >= max_entities:
            break
    return results


def extract_relations_from_text(text: str) -> list[tuple[str, str, str, str]]:
    relations: list[tuple[str, str, str, str]] = []
    for sentence in SENTENCE_SPLIT_PATTERN.split(text):
        sentence = sentence.strip()
        if not sentence:
            continue
        entities = extract_entities_from_text(sentence, max_entities=8)
        if len(entities) < 2:
            continue

        relation_type = infer_relation_type(sentence)
        for idx in range(len(entities)):
            for jdx in range(idx + 1, len(entities)):
                source = entities[idx]
                target = entities[jdx]
                if normalize_entity(source) == normalize_entity(target):
                    continue
                if normalize_entity(source) > normalize_entity(target):
                    source, target = target, source
                relations.append((source, target, relation_type, sentence[:240]))
    return relations


def infer_relation_type(sentence: str) -> str:
    lowered = sentence.lower()
    if '属于' in sentence or '是一种' in sentence or ' is a ' in lowered:
        return 'is_a'
    if '包括' in sentence or '包含' in sentence or ' consist of ' in lowered or ' includes ' in lowered:
        return 'contains'
    if '依赖' in sentence or '基于' in sentence or ' depends on ' in lowered:
        return 'depends_on'
    if '导致' in sentence or '造成' in sentence or ' causes ' in lowered:
        return 'causes'
    return 'co_occurs'


def rebuild_library_graph(db: Session, library_id: UUID) -> dict:
    # 先删除所有相关关系
    db.query(KnowledgeRelation).filter(KnowledgeRelation.library_id == library_id).delete(synchronize_session=False)
    # 删除所有相关实体
    db.query(KnowledgeEntity).filter(KnowledgeEntity.library_id == library_id).delete(synchronize_session=False)
    db.commit()

    chunks = db.query(Chunk).filter(Chunk.library_id == library_id).all()

    entity_counter: dict[str, dict] = {}
    relation_counter: dict[tuple[str, str, str], dict] = {}

    for chunk in chunks:
        chunk_entities = extract_entities_from_text(chunk.content, max_entities=20)
        for display_name in chunk_entities:
            normalized = normalize_entity(display_name)
            if normalized not in entity_counter:
                entity_counter[normalized] = {
                    'display_name': display_name,
                    'frequency': 1,
                }
            else:
                entity_counter[normalized]['frequency'] += 1

        chunk_relations = extract_relations_from_text(chunk.content)
        for source_name, target_name, relation_type, evidence in chunk_relations:
            source_norm = normalize_entity(source_name)
            target_norm = normalize_entity(target_name)
            if source_norm not in entity_counter or target_norm not in entity_counter:
                continue
            key = (source_norm, target_norm, relation_type)
            if key not in relation_counter:
                relation_counter[key] = {'weight': 1, 'evidence': [evidence]}
            else:
                relation_counter[key]['weight'] += 1
                if len(relation_counter[key]['evidence']) < 3:
                    if evidence not in relation_counter[key]['evidence']:
                        relation_counter[key]['evidence'].append(evidence)

    if not entity_counter:
        return {'library_id': library_id, 'node_count': 0, 'edge_count': 0, 'chunk_count': len(chunks)}

    # 插入新实体，使用 try-except 处理可能的并发冲突
    entities = []
    for normalized, data in entity_counter.items():
        entity = KnowledgeEntity(
            library_id=library_id,
            name=normalized,
            display_name=data['display_name'],
            entity_type='concept',
            frequency=data['frequency'],
            metadata_json={},
        )
        entities.append(entity)
    
    # 逐个插入，忽略已存在的
    for entity in entities:
        existing = db.query(KnowledgeEntity).filter(
            KnowledgeEntity.library_id == library_id,
            KnowledgeEntity.name == entity.name
        ).first()
        if not existing:
            db.add(entity)
    
    db.commit()

    entity_rows = db.query(KnowledgeEntity).filter(KnowledgeEntity.library_id == library_id).all()
    entity_id_by_name = {item.name: item.id for item in entity_rows}

    relations = []
    for (source_name, target_name, relation_type), rel_data in relation_counter.items():
        source_id = entity_id_by_name.get(source_name)
        target_id = entity_id_by_name.get(target_name)
        if not source_id or not target_id:
            continue
        relations.append(
            KnowledgeRelation(
                library_id=library_id,
                source_entity_id=source_id,
                target_entity_id=target_id,
                relation_type=relation_type,
                weight=rel_data['weight'],
                evidence_json=rel_data['evidence'],
            )
        )

    if relations:
        db.add_all(relations)
        db.commit()

    return {
        'library_id': library_id,
        'node_count': len(entity_rows),
        'edge_count': len(relations),
        'chunk_count': len(chunks),
    }


def get_library_graph_snapshot(db: Session, library_id: UUID, *, limit_nodes: int = 80, limit_edges: int = 150) -> dict:
    node_count = (
        db.query(func.count(KnowledgeEntity.id)).filter(KnowledgeEntity.library_id == library_id).scalar() or 0
    )
    edge_count = (
        db.query(func.count(KnowledgeRelation.id)).filter(KnowledgeRelation.library_id == library_id).scalar() or 0
    )

    nodes = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.library_id == library_id)
        .order_by(KnowledgeEntity.frequency.desc(), KnowledgeEntity.display_name.asc())
        .limit(limit_nodes)
        .all()
    )

    edges = (
        db.query(KnowledgeRelation)
        .filter(KnowledgeRelation.library_id == library_id)
        .order_by(KnowledgeRelation.weight.desc())
        .limit(limit_edges)
        .all()
    )

    name_by_entity_id = {node.id: node.display_name for node in nodes}
    if edges:
        edge_entity_ids = {edge.source_entity_id for edge in edges} | {edge.target_entity_id for edge in edges}
        missing_ids = [entity_id for entity_id in edge_entity_ids if entity_id not in name_by_entity_id]
        if missing_ids:
            extra_nodes = db.query(KnowledgeEntity).filter(KnowledgeEntity.id.in_(missing_ids)).all()
            for row in extra_nodes:
                name_by_entity_id[row.id] = row.display_name

    return {
        'library_id': library_id,
        'node_count': int(node_count),
        'edge_count': int(edge_count),
        'nodes': [
            {
                'id': item.id,
                'name': item.name,
                'display_name': item.display_name,
                'entity_type': item.entity_type,
                'frequency': item.frequency,
            }
            for item in nodes
        ],
        'edges': [
            {
                'id': item.id,
                'source_entity_id': item.source_entity_id,
                'source_entity': name_by_entity_id.get(item.source_entity_id, ''),
                'target_entity_id': item.target_entity_id,
                'target_entity': name_by_entity_id.get(item.target_entity_id, ''),
                'relation_type': item.relation_type,
                'weight': item.weight,
            }
            for item in edges
        ],
    }


def expand_query_terms_by_graph(db: Session, *, library_ids: list[UUID], query: str, max_terms: int = 8) -> dict:
    query_entities = extract_entities_from_text(query, max_entities=max_terms)
    if not query_entities:
        return {'expanded_terms': [], 'matched_entities': []}

    # 获取知识库中所有的实体名（用于别名匹配）
    all_entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.library_id.in_(library_ids))
        .all()
    )
    entity_names = {e.name for e in all_entities}
    entity_display_names = {e.display_name for e in all_entities}
    
    # 查询实体消歧：看查询中的实体是否能匹配知识库中的实体
    # 例如：用户输入"皮副市长"，知识库中有"皮杰"
    expanded_query_entities = []
    for qe in query_entities:
        expanded_query_entities.append(qe)
        # 如果查询实体不在知识库中，尝试找可能的别名
        if qe not in entity_names and qe not in entity_display_names:
            # 尝试去掉常见职位后缀后匹配
            for suffix in TITLE_SUFFIXES:
                if qe.endswith(suffix):
                    name_part = qe[:-len(suffix)]
                    for ent_name in entity_names:
                        if ent_name.startswith(name_part[:2]) or ent_name == name_part:
                            expanded_query_entities.append(ent_name)
                            break
                    for ent_display in entity_display_names:
                        if ent_display.startswith(name_part[:2]) or ent_display == name_part:
                            if ent_display not in expanded_query_entities:
                                expanded_query_entities.append(ent_display)
                            break

    # 去重
    expanded_query_entities = list(set(expanded_query_entities))
    normalized_query_entities = [normalize_entity(item) for item in expanded_query_entities]

    matched = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.library_id.in_(library_ids), KnowledgeEntity.name.in_(normalized_query_entities))
        .all()
    )

    if not matched:
        fuzzy_filters = [KnowledgeEntity.display_name.ilike(f'%{item}%') for item in expanded_query_entities if item]
        if fuzzy_filters:
            matched = (
                db.query(KnowledgeEntity)
                .filter(KnowledgeEntity.library_id.in_(library_ids), or_(*fuzzy_filters))
                .order_by(KnowledgeEntity.frequency.desc())
                .limit(max_terms)
                .all()
            )

    if not matched:
        return {'expanded_terms': [], 'matched_entities': []}

    matched_ids = [item.id for item in matched]
    matched_names = [item.display_name for item in matched]

    linked = (
        db.query(KnowledgeRelation)
        .filter(
            KnowledgeRelation.library_id.in_(library_ids),
            or_(
                KnowledgeRelation.source_entity_id.in_(matched_ids),
                KnowledgeRelation.target_entity_id.in_(matched_ids),
            ),
        )
        .order_by(KnowledgeRelation.weight.desc())
        .limit(80)
        .all()
    )

    expanded_entity_ids: set[UUID] = set(matched_ids)
    for rel in linked:
        expanded_entity_ids.add(rel.source_entity_id)
        expanded_entity_ids.add(rel.target_entity_id)

    expanded_entities = (
        db.query(KnowledgeEntity)
        .filter(KnowledgeEntity.id.in_(list(expanded_entity_ids)))
        .order_by(KnowledgeEntity.frequency.desc())
        .limit(max_terms)
        .all()
    )

    expanded_terms = [item.display_name for item in expanded_entities]
    return {'expanded_terms': expanded_terms, 'matched_entities': matched_names}


def summarize_graph_sources(sources: list[str]) -> str:
    if not sources:
        return 'none'
    if len(sources) == 1:
        return sources[0]
    return '_'.join(sorted(set(sources)))


def score_merge(current_score: float, increment: float) -> float:
    return round(current_score + increment, 6)
