# 迁移记录：园所归属与导出历史（2026-08-28）

## 一、本次变更

| 编号 | 变更 | 说明 |
|---|---|---|
| 1 | `classroom` 表新增 `kindergarten_id` | 班级归属到园所；可空，`REFERENCES kindergartens(id)` |
| 2 | 回填现有班级 | 优先按「教师账号 → 园所」推导；推不出时归入兜底园所「待设置园所（历史数据）」，不猜测、不冲突合并 |
| 3 | 新增 `export_records` 表 | 记录每次导出（单篇/整月、docx/pdf/md、文件名、大小、落库时间），模型见 `backend/models.py` 的 `ExportRecord` |

执行脚本：`backend/migrate_frontend_features.py`（幂等，可重复运行）。

## 二、执行顺序（按项目铁律）

1. **临时库先行**：以迁移前真实库的备份副本为输入，在临时库上运行迁移脚本并验证；
2. **备份真实库**：确认临时库通过后，检查真实库备份；
3. **迁移真实库**：对真实库执行迁移。

## 三、验证结果

### 临时库（`work/mig-20260828/temp-before-mig.db`，输入为迁移前备份副本）

- 迁移后 `classroom` 列：`id, name, age_group, kindergarten_id` ✅
- 回填：无 NULL 班级（0 个未归属）✅
- `export_records` 建表成功，字段与 models.py 一致 ✅
- `PRAGMA integrity_check` = ok，`foreign_key_check` 无异常 ✅
- 幂等重跑：无报错、无重复数据 ✅
- 临时服务（8011）跑通 `python demo.py` 完整闭环 ✅
- 新功能冒烟：注册 → 取园所/班级 → 新建班级 → 导出 docx → `export_records` 正确落库 1 行 ✅

### 真实库（`backend/bangbang.db`）

- `classroom.kindergarten_id` 已存在且已回填（无 NULL）✅
- `export_records` 已建，结构正确 ✅
- 完整性/外键检查全部通过 ✅

### 后端测试

`pytest tests/`：27 个用例全部通过 ✅

## 四、备份清单

| 文件 | 时间 | 内容 |
|---|---|---|
| `backend/bangbang.db.bak-20260828` | 2026-08-27 07:33 | 迁移前的完整状态（已比对：与迁移后仅差本次迁移的改动） |
| `backend/backups/bangbang-20260828-065558-898966.db` | 2026-08-28 06:55 | 迁移完成后的快照（字节级一致，integrity ok） |

## 五、环境变化

- 演示服务（8001）已重启以加载本次代码；`BANGBANG_AI_MODE=deepseek` 保持 `.env` 原配置不变。
- 前端 `features.ts` 各开关状态沿用现状（园所、导出等已为 true，由后端支撑）。
