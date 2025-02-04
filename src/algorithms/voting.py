def iou(entity1, entity2):
    """
    计算两个实体的交并比（IoU）。
    """
    start_max = max(entity1['start'], entity2['start'])
    end_min = min(entity1['end'], entity2['end'])
    intersection = max(0, end_min - start_max)
    union = max(entity1['end'], entity2['end']) - min(entity1['start'], entity2['start'])
    return intersection / union if union > 0 else 0

def umls_entity_voting(predictions, iou_threshold=0.3, vote_threshold=0.5):
    """
    适用于 UMLS 概念检测的改良实体投票函数。

    参数：
    - predictions：list of lists，每个内部列表包含一个模型的实体预测结果。
                   每个实体包含 'start'、'end'、'concept_id'、'score'（可选）等字段。
    - iou_threshold：float，用于判断实体是否匹配的 IoU 阈值。
    - vote_threshold：float，实体被选入最终结果所需的最低模型支持比例。

    返回：
    - 最终的实体预测结果列表。
    """
    from collections import defaultdict
    import bisect

    num_models = len(predictions)
    all_entities = []

    # 为每个实体分配唯一的 ID，并关联所属的模型 ID
    entity_id = 0
    for model_id, model_entities in enumerate(predictions):
        for entity in model_entities:
            entity['id'] = entity_id
            entity['model_id'] = model_id
            all_entities.append(entity)
            entity_id += 1

    # 按照实体的起始位置排序，以加速比较
    all_entities.sort(key=lambda x: x['start'])

    # 构建索引，以减少比较次数
    start_positions = [entity['start'] for entity in all_entities]

    # 建立实体聚类
    clusters = []
    entity_to_cluster = {}

    for i, entity in enumerate(all_entities):
        # 仅与可能重叠的实体进行比较
        possible_matches = []
        start = entity['start']
        end = entity['end']

        # 找到开始位置在 [start, end] 区间内的实体
        left = bisect.bisect_left(start_positions, start)
        right = bisect.bisect_right(start_positions, end)

        for j in range(left, right):
            if i == j:
                continue
            other_entity = all_entities[j]
            # 仅当实体可能重叠时，计算 IoU
            if other_entity['end'] >= start:
                iou_score = iou(entity, other_entity)
                if iou_score >= iou_threshold:
                    # 检查是否需要合并到同一聚类
                    id1 = entity['id']
                    id2 = other_entity['id']
                    cluster1 = entity_to_cluster.get(id1)
                    cluster2 = entity_to_cluster.get(id2)

                    if cluster1 is None and cluster2 is None:
                        # 创建新聚类
                        new_cluster = set([id1, id2])
                        clusters.append(new_cluster)
                        entity_to_cluster[id1] = new_cluster
                        entity_to_cluster[id2] = new_cluster
                    elif cluster1 is not None and cluster2 is None:
                        # 将实体加入已有的 cluster1
                        cluster1.add(id2)
                        entity_to_cluster[id2] = cluster1
                    elif cluster1 is None and cluster2 is not None:
                        # 将实体加入已有的 cluster2
                        cluster2.add(id1)
                        entity_to_cluster[id1] = cluster2
                    elif cluster1 is not cluster2:
                        # 合并两个聚类
                        cluster1.update(cluster2)
                        for eid in cluster2:
                            entity_to_cluster[eid] = cluster1
                        clusters.remove(cluster2)
                    # 如果两个实体已经在同一聚类，无需操作

    # 将未被聚类的实体单独作为一个聚类
    all_entity_ids = set(entity['id'] for entity in all_entities)
    clustered_entity_ids = set(entity_to_cluster.keys())
    unclustered_entity_ids = all_entity_ids - clustered_entity_ids

    for eid in unclustered_entity_ids:
        new_cluster = set([eid])
        clusters.append(new_cluster)
        entity_to_cluster[eid] = new_cluster

    # 在每个聚类中进行投票
    final_entities = []
    for cluster in clusters:
        cluster_entities = [next(entity for entity in all_entities if entity['id'] == eid) for eid in cluster]
        # 计算支持模型数
        support_models = set(entity['model_id'] for entity in cluster_entities)
        support = len(support_models) / num_models
        if support >= vote_threshold:
            # 处理 UMLS 概念，投票确定概念 ID
            concept_votes = defaultdict(float)
            for entity in cluster_entities:
                # 如果有置信度分数，使用置信度加权，否则权重为1
                score = entity.get('score', 1.0)
                concept_votes[entity['concept_id']] += score
            # 选择得票最高的概念 ID
            final_concept_id = max(concept_votes.items(), key=lambda x: x[1])[0]
            # 确定实体的起始和结束位置，可以取跨度最长的实体
            start = min(entity['start'] for entity in cluster_entities)
            end = max(entity['end'] for entity in cluster_entities)
            final_entities.append({
                'start': start,
                'end': end,
                'concept_id': final_concept_id
            })

    # 按起始位置排序
    final_entities.sort(key=lambda x: x['start'])

    return final_entities

# 示例使用

src_string = "John Doe 前往紐約市。"

model_1 = [
    {'start': 0, 'end': 4, 'concept_id': 'C0012345', 'score': 0.9},  # 'John', C0012345
    {'start': 7, 'end': 10, 'concept_id': 'C0026789', 'score': 0.85}  # '紐約', C0026789
]

model_2 = [
    {'start': 0, 'end': 8, 'concept_id': 'C0012346', 'score': 0.95},  # 'John Doe', C0012346
    {'start': 7, 'end': 13, 'concept_id': 'C0026790', 'score': 0.9}   # '紐約市', C0026790
]

model_3 = [
    {'start': 5, 'end': 8, 'concept_id': 'C0012347', 'score': 0.88},  # 'Doe', C0012347
    {'start': 7, 'end': 13, 'concept_id': 'C0026790', 'score': 0.92}  # '紐約市', C0026790
]

predictions = [model_1, model_2, model_3]
final_entities = umls_entity_voting(predictions, iou_threshold=0.3, vote_threshold=0.5)
print(final_entities)
